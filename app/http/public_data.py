import base64
import binascii
import json
import math
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qs, urlsplit

from app import config, map_downloads
from app.http import access
from app.http import admin_session as http_admin_session
from app.http import responses as http_responses
from core import config as core_config
from core.cadastral import cadastral_feature_info_params, parse_cadastral_feature_info
from core.field_photo_map_query import list_map_field_photos
from core.field_photo_store import validate_photo_id
from core.geo import validate_coordinates
from core.http_response import read_limited_response_bytes, response_content_type
from core.prg_addresses import parse_prg_address_features, prg_address_wfs_params
from core.reverse_geocoding import normalize_reverse_geocode_result


def _close_response(response) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _upstream_text(response, *, max_bytes: int, allowed_content_types: set[str], encoding: str | None = None) -> str:
    response.raise_for_status()
    content_type = response_content_type(response)
    if content_type not in allowed_content_types:
        raise ValueError(f"Nieoczekiwany typ odpowiedzi upstreamu: {content_type or 'brak'}.")
    payload = read_limited_response_bytes(response, max_bytes=max_bytes)
    selected_encoding = str(encoding or getattr(response, "encoding", None) or "utf-8")
    try:
        return payload.decode(selected_encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        raise ValueError("Nie udało się odczytać kodowania odpowiedzi upstreamu.") from exc


def _field_photo_list_query(
    path: str,
) -> tuple[tuple[float, float, float, float] | None, int | None, tuple[str, str] | None]:
    params = parse_qs(urlsplit(path).query, keep_blank_values=True)
    bbox = None
    if "bbox" in params:
        if len(params["bbox"]) != 1:
            raise ValueError("Parametr bbox musi wystąpić dokładnie raz.")
        values = params["bbox"][0].split(",")
        if len(values) != 4:
            raise ValueError("bbox musi zawierać west,south,east,north.")
        try:
            west, south, east, north = (float(item) for item in values)
        except ValueError as exc:
            raise ValueError("Nieprawidłowe współrzędne bbox.") from exc
        if not (
            all(map(math.isfinite, (west, south, east, north)))
            and -180 <= west <= 180
            and -180 <= east <= 180
            and -90 <= south <= north <= 90
        ):
            raise ValueError("Nieprawidłowy zakres bbox.")
        # A west > east box intentionally crosses the 180th meridian.
        bbox = west, south, east, north

    limit = None
    if "limit" in params:
        if len(params["limit"]) != 1:
            raise ValueError("Parametr limit musi wystąpić dokładnie raz.")
        raw = params["limit"][0]
        if not raw.isascii() or not raw.isdecimal():
            raise ValueError("Nieprawidłowy limit.")
        limit = int(raw)
        if not 1 <= limit <= 500:
            raise ValueError("Limit musi być w zakresie 1–500.")

    after = None
    if "cursor" in params:
        if limit is None or len(params["cursor"]) != 1:
            raise ValueError("Cursor wymaga pojedynczego parametru limit.")
        token = params["cursor"][0]
        if not token or len(token) > 256:
            raise ValueError("Nieprawidłowy cursor.")
        try:
            decoded = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
            value = json.loads(decoded)
            if (
                not isinstance(value, list)
                or len(value) != 2
                or not isinstance(value[0], str)
                or not 1 <= len(value[0]) <= 80
                or any(ord(char) < 32 for char in value[0])
                or not isinstance(value[1], str)
            ):
                raise ValueError
            after = value[0], validate_photo_id(value[1])
        except (ValueError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as exc:
            raise ValueError("Nieprawidłowy cursor.") from exc
    return bbox, limit, after


def _field_photo_cursor(key: tuple[str, str]) -> str:
    payload = json.dumps(list(key), ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def handle_field_photos(handler) -> None:
    try:
        bounds, limit, after = _field_photo_list_query(handler.path)
    except ValueError as exc:
        http_responses.send_json(handler, 400, {"status": "error", "error": str(exc)})
        return
    try:
        is_admin = http_admin_session.is_admin(handler)
        approved_types = None
        pending_visible = True
        if not is_admin:
            layers = access.public_layer_settings()
            approved_types = tuple(
                issue
                for issue in core_config.FIELD_PHOTO_ISSUE_TYPES
                if layers.get(access.field_photo_issue_layer_key(issue), True)
            )
            pending_visible = layers.get("field_photo_pending", True)
        photos, next_key = list_map_field_photos(
            core_config.FIELD_PHOTOS_DIR,
            bounds=bounds,
            limit=limit,
            after=after,
            approved_types=approved_types,
            pending_visible=pending_visible,
        )
        payload = {"status": "ok", "photos": photos}
        if limit is not None:
            payload["next_cursor"] = _field_photo_cursor(next_key) if next_key else None
        http_responses.send_json(handler, 200, payload)
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Field photo list lookup failed",
            exc,
            public_error="Nie udało się pobrać zdjęć terenowych.",
        )


def lookup_cadastral_parcel(lat: float, lon: float) -> dict[str, Any]:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Współrzędne poza zakresem.")

    params = cadastral_feature_info_params(lat, lon)
    last_error: Exception | None = None
    html = None
    for upstream_url in (config.CADASTRAL_WMS_URL, config.CADASTRAL_WMS_FALLBACK_URL):
        response = None
        try:
            response = map_downloads.get_http_session().get(
                upstream_url,
                params=params,
                timeout=config.CADASTRAL_WMS_TIMEOUT,
                stream=True,
            )
            html = _upstream_text(
                response,
                max_bytes=config.CADASTRAL_MAX_RESPONSE_BYTES,
                allowed_content_types={"text/html"},
                # KIEG returns UTF-8 HTML without charset; requests otherwise assumes Latin-1.
                encoding="utf-8",
            )
            break
        except Exception as exc:
            last_error = exc
        finally:
            if response is not None:
                _close_response(response)
    if html is None:
        raise RuntimeError("Nie udało się pobrać danych działki.") from last_error

    parcel = parse_cadastral_feature_info(html)
    if not parcel.get("parcel_id") and not parcel.get("parcel_number"):
        raise LookupError("Nie znaleziono działki w tym punkcie.")
    return parcel


@lru_cache(maxsize=512)
def _lookup_prg_address_cached(lat: float, lon: float) -> dict[str, Any]:
    response = map_downloads.get_http_session().get(
        config.PRG_ADDRESS_WFS_URL,
        params=prg_address_wfs_params(
            lat,
            lon,
            radius_m=config.PRG_ADDRESS_SEARCH_RADIUS_M,
            count=config.PRG_ADDRESS_MAX_FEATURES,
        ),
        timeout=config.PRG_ADDRESS_WFS_TIMEOUT,
        stream=True,
    )
    try:
        xml_text = _upstream_text(
            response,
            max_bytes=config.PRG_ADDRESS_MAX_RESPONSE_BYTES,
            allowed_content_types={"application/gml+xml", "application/xml", "text/xml"},
        )
    finally:
        _close_response(response)
    return parse_prg_address_features(xml_text, query_lat=lat, query_lon=lon)


@lru_cache(maxsize=512)
def _lookup_nominatim_address_cached(lat: float, lon: float) -> dict[str, Any]:
    response = map_downloads.get_http_session().get(
        config.NOMINATIM_REVERSE_URL,
        params={
            "format": "jsonv2",
            "lat": f"{lat:.8f}",
            "lon": f"{lon:.8f}",
            "addressdetails": "1",
            "zoom": "18",
            "accept-language": "pl",
        },
        headers={
            "User-Agent": config.NOMINATIM_USER_AGENT,
            "Accept": "application/json",
        },
        timeout=config.NOMINATIM_TIMEOUT,
        stream=True,
    )
    try:
        json_text = _upstream_text(
            response,
            max_bytes=config.NOMINATIM_MAX_RESPONSE_BYTES,
            allowed_content_types={"application/json"},
        )
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise LookupError("Nie udało się odczytać odpowiedzi Nominatim.") from exc
    finally:
        _close_response(response)
    return normalize_reverse_geocode_result(payload, query_lat=lat, query_lon=lon)


def lookup_nearest_address(lat: float, lon: float) -> dict[str, Any]:
    lat, lon = validate_coordinates(lat, lon)
    rounded_lat = round(lat, 6)
    rounded_lon = round(lon, 6)
    try:
        return _lookup_prg_address_cached(rounded_lat, rounded_lon)
    except Exception:
        return _lookup_nominatim_address_cached(rounded_lat, rounded_lon)


def _query_coordinates(handler) -> tuple[float, float]:
    query = parse_qs(urlsplit(handler.path).query)
    return validate_coordinates((query.get("lat") or [""])[0], (query.get("lon") or [""])[0])


def handle_cadastral_identify(handler) -> None:
    if not access.require_public_layer(
        handler, "cadastral", "Warstwa dzialek jest teraz wylaczona dla niezalogowanych."
    ):
        return
    try:
        lat, lon = _query_coordinates(handler)
    except ValueError:
        http_responses.send_json(handler, 400, {"status": "error", "error": "Nieprawidłowe współrzędne."})
        return

    try:
        parcel = lookup_cadastral_parcel(lat, lon)
    except ValueError as exc:
        http_responses.send_json(handler, 400, {"status": "error", "error": str(exc)})
        return
    except LookupError as exc:
        http_responses.send_json(handler, 404, {"status": "not_found", "error": str(exc)})
        return
    except RuntimeError as exc:
        http_responses.send_internal_error(
            handler,
            502,
            "Cadastral upstream request failed",
            exc,
            public_error="Nie udało się pobrać danych działki.",
        )
        return
    http_responses.send_json(handler, 200, {"status": "ok", "parcel": parcel})


def handle_reverse_address(handler) -> None:
    try:
        lat, lon = _query_coordinates(handler)
    except ValueError:
        http_responses.send_json(handler, 400, {"status": "error", "error": "Nieprawidłowe współrzędne."})
        return

    try:
        address = lookup_nearest_address(lat, lon)
    except LookupError as exc:
        http_responses.send_json(handler, 404, {"status": "not_found", "error": str(exc)})
        return
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            502,
            "Reverse geocoding upstream request failed",
            exc,
            public_error="Nie udało się pobrać adresu.",
        )
        return
    http_responses.send_json(handler, 200, {"status": "ok", "address": address})
