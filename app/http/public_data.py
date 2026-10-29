import json
from functools import lru_cache
from typing import Any
from urllib.parse import parse_qs, urlsplit

from app import config, map_downloads
from app.http import access
from app.http import admin_session as http_admin_session
from app.http import responses as http_responses
from core import config as core_config
from core.cadastral import cadastral_feature_info_params, parse_cadastral_feature_info
from core.field_photos import list_field_photos
from core.geo import validate_coordinates
from core.http_response import read_limited_response_bytes, response_content_type
from core.prg_addresses import parse_prg_address_features, prg_address_wfs_params
from core.reverse_geocoding import normalize_reverse_geocode_result


def _close_response(response) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


def _upstream_text(
    response, *, max_bytes: int, allowed_content_types: set[str], encoding: str | None = None
) -> str:
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


def handle_field_photos(handler) -> None:
    try:
        photos = list_field_photos(core_config.FIELD_PHOTOS_DIR)
        if not http_admin_session.is_admin(handler):
            layer_settings = access.public_layer_settings()
            photos = [
                photo for photo in photos
                if access.public_field_photo_allowed(handler, photo, layer_settings=layer_settings)
            ]
        http_responses.send_json(handler, 200, {"status": "ok", "photos": photos})
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
