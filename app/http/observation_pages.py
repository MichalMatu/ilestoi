"""Public, server-rendered observation pages for crawlers and visitors.

All outputs use only approved public derivatives and honor public layer switches.
"""
from __future__ import annotations

import math
import re
from html import escape
from urllib.parse import parse_qs, quote, urlsplit
from xml.sax.saxutils import escape as xml_escape

from app import config
from app.http import access
from app.http import responses as http_responses
from app.http import static_files as http_static_files
from core import config as core_config
from core.field_photos import list_field_photos

PHOTO_ID = re.compile(r"[A-Za-z0-9_-]{3,96}\Z")
DISCLAIMER = (
    "To dokumentacja obserwacji, a nie urzędowe ustalenie dotyczące stanu "
    "prawnego pojazdu, ubezpieczenia ani jego właściciela."
)


def public_observations() -> list[dict]:
    """Never use admin session privileges for crawler-facing pages."""
    layers = access.public_layer_settings()
    result = []
    for photo in list_field_photos(core_config.FIELD_PHOTOS_DIR):
        if (photo.get("public_review_status") != "approved"
                or not photo.get("public_image")
                or not photo.get("public_thumb")
                or photo.get("vehicle_resolution_status") == "removed"):
            continue
        layer_key = access.field_photo_issue_layer_key(photo.get("issue_type"))
        if layers.get(layer_key, True):
            result.append(photo)
    return result


def _base(title: str, description: str, path: str, body: str, *,
          image_url: str = "") -> bytes:
    canonical = config.CANONICAL_PUBLIC_ORIGIN + path
    meta_image = (
        '<meta property="og:image" content="' + escape(
            config.CANONICAL_PUBLIC_ORIGIN + image_url, quote=True
        ) + '">'
    ) if image_url else ""
    html = (
        '<!doctype html><html lang="pl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="index,follow,max-image-preview:large">'
        f'<title>{escape(title)}</title>'
        f'<meta name="description" content="{escape(description, quote=True)}">'
        f'<link rel="canonical" href="{escape(canonical, quote=True)}">'
        '<meta property="og:type" content="article">'
        f'<meta property="og:title" content="{escape(title, quote=True)}">'
        f'<meta property="og:description" content="{escape(description, quote=True)}">'
        + meta_image +
        '</head><body><header><a href="/">IleStoi.pl – mapa</a> | '
        '<a href="/observations">Obserwacje publiczne</a></header>'
        f'<main>{body}</main><footer><p>{escape(DISCLAIMER)}</p>'
        '<p><a href="/privacy">Prywatność</a> | '
        '<a href="/report">Zgłoś korektę lub usunięcie zdjęcia</a></p>'
        '</footer></body></html>'
    )
    return html.encode("utf-8")


def _distance_m(photo: dict, lat: float, lon: float) -> float:
    p_lat = math.radians(float(photo["lat"]))
    p_lon = math.radians(float(photo["lon"]))
    c_lat = math.radians(lat)
    c_lon = math.radians(lon)
    a = math.sin((p_lat - c_lat) / 2) ** 2
    a += math.cos(p_lat) * math.cos(c_lat) * math.sin((p_lon - c_lon) / 2) ** 2
    return 6371000.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def _nearby(photos: list[dict], query: str) -> tuple[list[dict], str]:
    params = parse_qs(query)
    if "lat" not in params or "lon" not in params:
        return photos, ""
    try:
        lat = float(params["lat"][0])
        lon = float(params["lon"][0])
        radius = float(params.get("radius", ["50"])[0])
        if (not all(map(math.isfinite, (lat, lon, radius))) or
                not -90 <= lat <= 90 or not -180 <= lon <= 180 or
                radius < 1 or radius > 500):
            raise ValueError
        found = []
        for photo in photos:
            try:
                distance = _distance_m(photo, lat, lon)
            except (TypeError, ValueError, KeyError):
                continue
            if distance <= radius:
                found.append((distance, photo))
        return [photo for _, photo in sorted(found, key=lambda item: item[0])], (
            f"Najbliższe obserwacje w promieniu {radius:g} m od "
            f"{lat:.6f}, {lon:.6f}."
        )
    except (ValueError, IndexError, OverflowError):
        return [], "Nieprawidłowe współrzędne lub promień (1–500 m)."


def _index(handler, *, include_body: bool) -> None:
    photos, note = _nearby(public_observations(), urlsplit(handler.path).query)
    links = []
    for photo in photos[:1500]:
        pid = str(photo["id"])
        title = "Zdjęcie terenowe " + str(photo.get("captured_at") or photo.get("created_at") or "")
        links.append(
            f'<li><a href="/observations/{quote(pid)}">{escape(title)}</a>'
            f' ({escape(str(photo.get("issue_type") or "observation"))}, '
            f'{escape(str(photo.get("lat")))}, {escape(str(photo.get("lon")))})</li>'
        )
    body = (
        "<h1>Zatwierdzone obserwacje terenowe</h1>"
        "<p>Wyłącznie publiczne, zatwierdzone zdjęcia; bez prywatnych oryginałów.</p>"
        + (f"<p>{escape(note)}</p>" if note else "")
        + f"<p>Wyniki: {len(photos)}.</p><ol>"
        + "".join(links) + "</ol>"
    )
    http_static_files.send_bytes(
        handler,
        _base("Obserwacje terenowe – IleStoi.pl", DISCLAIMER, "/observations", body),
        "text/html; charset=utf-8",
        cache_control="public, max-age=60",
        include_body=include_body,
    )


def _insurance(photo: dict) -> str:
    status = str(photo.get("vehicle_insurance_status") or "unknown")
    checked = str(photo.get("vehicle_insurance_checked_at") or "")
    if status not in {"insured", "uninsured"}:
        return "Status OC: niezweryfikowany."
    label = "ubezpieczony" if status == "insured" else "nieubezpieczony"
    suffix = f" (ręcznie zapisany wynik z {escape(checked)})" if checked else " (brak daty sprawdzenia)"
    return "Status OC w aplikacji: " + label + suffix + ". Wynik nie jest sprawdzany na żywo."


def _detail(handler, photo_id: str, *, include_body: bool) -> None:
    if not PHOTO_ID.fullmatch(photo_id):
        http_responses.send_text_error(handler, 404, "Nie znaleziono obserwacji.", include_body=include_body)
        return
    photo = next((p for p in public_observations() if p.get("id") == photo_id), None)
    if photo is None:
        http_responses.send_text_error(handler, 404, "Nie znaleziono obserwacji.", include_body=include_body)
        return
    created = str(photo.get("created_at") or "brak")
    captured = str(photo.get("captured_at") or "brak")
    lat, lon = float(photo["lat"]), float(photo["lon"])
    thumb, full = str(photo["public_thumb"]), str(photo["public_image"])
    body = (
        "<article><h1>Zatwierdzona obserwacja terenowa</h1>"
        f'<p>Identyfikator: <code>{escape(photo_id)}</code></p>'
        f'<p>Typ: {escape(str(photo.get("issue_type") or "observation"))}</p>'
        f'<p>Data zdjęcia: {escape(captured)}. Dodano: {escape(created)}.</p>'
        f'<p>Położenie: {lat:.6f}, {lon:.6f}.</p>'
        f'<p>{_insurance(photo) if photo.get("issue_type") == "vehicle" else ""}</p>'
        f'<p><img src="{escape(thumb, quote=True)}" '
        f'alt="Publiczne zdjęcie zatwierdzonej obserwacji {escape(photo_id, quote=True)}" '
        'loading="lazy" style="max-width:100%;height:auto"></p>'
        f'<p><a href="{escape(full, quote=True)}">Zobacz publiczne zdjęcie w pełnej rozdzielczości</a></p>'
        f'<p><a href="/?photo={quote(photo_id)}">Pokaż na interaktywnej mapie</a></p>'
        "</article>"
    )
    http_static_files.send_bytes(
        handler,
        _base(
            "Obserwacja " + photo_id + " – IleStoi.pl",
            "Publiczne zdjęcie terenowe z datą, lokalizacją i ręcznym statusem weryfikacji.",
            "/observations/" + quote(photo_id),
            body,
            image_url=full,
        ),
        "text/html; charset=utf-8",
        cache_control="public, max-age=60",
        include_body=include_body,
    )


def _sitemap(handler, *, include_body: bool) -> None:
    entries = [
        "<url><loc>" + xml_escape(config.CANONICAL_PUBLIC_ORIGIN + "/observations/"
                               + quote(str(photo["id"]))) + "</loc></url>"
        for photo in public_observations()[:1500]
    ]
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>" + xml_escape(config.CANONICAL_PUBLIC_ORIGIN + "/observations")
        + "</loc></url>" + "".join(entries) + "</urlset>"
    ).encode("utf-8")
    http_static_files.send_bytes(
        handler, body, "application/xml; charset=utf-8",
        cache_control="public, max-age=60", include_body=include_body,
    )


def handle_public_route(handler, path: str, *, include_body: bool = True) -> bool:
    if path == "/observations":
        _index(handler, include_body=include_body)
        return True
    if path == "/sitemap-observations.xml":
        _sitemap(handler, include_body=include_body)
        return True
    if path.startswith("/observations/"):
        segments = path.split("/")
        if len(segments) == 3:
            _detail(handler, segments[-1], include_body=include_body)
        else:
            http_responses.send_text_error(
                handler, 404, "Nie znaleziono obserwacji.", include_body=include_body
            )
        return True
    return False
