from urllib.parse import parse_qs, urlsplit

from app import config
from app.http import admin_session as http_admin_session
from app.http import auth
from app.http import request_body as http_request_body
from app.http import responses as http_responses
from core import config as core_config
from core.field_photos import (
    delete_field_photo,
    list_field_photo_review_items,
    review_field_photo,
    update_field_photo_location,
)
from core.privacy_requests import list_privacy_requests, update_privacy_request
from core.submission_limits import pending_submission_usage

_ADMIN_PHOTO_SEARCH_FIELDS = ("id", "photo_id", "original_filename", "issue_type")


def handle_admin_status(handler) -> None:
    try:
        authenticated = http_admin_session.is_admin(handler)
        payload = {
            "status": "ok",
            "admin_enabled": auth.admin_enabled(),
            "authenticated": authenticated,
        }
        if authenticated:
            payload["pending_submissions"] = pending_submission_usage(
                owner=None,
                field_photos_dir=core_config.FIELD_PHOTOS_DIR,
                private_dir=core_config.PRIVATE_PHOTOS_DIR,
            )
        http_responses.send_json(handler, 200, payload)
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Admin status lookup failed",
            exc,
            public_error="Nie udało się pobrać statusu panelu administratora.",
        )


def handle_admin_login(handler) -> None:
    password = auth.admin_password()
    if not password:
        http_responses.send_json(
            handler,
            503,
            {"error": "Brak hasla administratora. Ustaw WRECKSCANNER_ADMIN_PASSWORD albo plik .admin_password."},
        )
        return
    try:
        data = http_request_body.read_json_body(handler)
    except Exception as exc:
        http_responses.send_json(handler, 400, {"error": str(exc)})
        return
    candidate = str(data.get("password", ""))
    if not auth.password_matches(candidate, password):
        http_responses.send_json(handler, 401, {"error": "Nieprawidlowe haslo administratora."})
        return
    token = auth.make_admin_token(password)
    cookie = http_admin_session.admin_cookie_header(handler, token, max_age=config.ADMIN_SESSION_SECONDS)
    http_responses.send_json(
        handler,
        200,
        {"status": "ok", "authenticated": True},
        {"Set-Cookie": cookie},
    )


def handle_admin_logout(handler) -> None:
    auth.revoke_admin_token(http_admin_session.admin_token_from_cookie(handler))
    cookie = http_admin_session.admin_cookie_header(handler, "", max_age=0)
    http_responses.send_json(handler, 200, {"status": "ok", "authenticated": False}, {"Set-Cookie": cookie})


def admin_photo_review_items() -> list[dict]:
    return list_field_photo_review_items(core_config.FIELD_PHOTOS_DIR)


def admin_photo_exact_ids(query: dict[str, list[str]]) -> set[str]:
    return {item.strip().lower() for raw in query.get("ids", []) for item in str(raw).split(",") if item.strip()}


def filter_admin_photos_by_status(photos: list[dict], status_filter: str) -> list[dict]:
    if status_filter not in {"pending", "approved", "rejected"}:
        return photos
    return [photo for photo in photos if photo.get("public_review_status") == status_filter]


def filter_admin_photos_by_issue(photos: list[dict], issue_filter: str) -> list[dict]:
    if issue_filter == "all":
        return photos
    return [photo for photo in photos if photo.get("issue_type") == issue_filter]


def filter_admin_photos_by_ids(photos: list[dict], exact_photo_ids: set[str]) -> list[dict]:
    if not exact_photo_ids:
        return photos
    return [
        photo
        for photo in photos
        if str(photo.get("photo_id") or "").lower() in exact_photo_ids
        or str(photo.get("id") or "").lower() in exact_photo_ids
    ]


def admin_photo_search_text(photo: dict) -> str:
    return " ".join(str(photo.get(key) or "") for key in _ADMIN_PHOTO_SEARCH_FIELDS).lower()


def filter_admin_photos_by_search(photos: list[dict], search: str) -> list[dict]:
    if not search:
        return photos
    return [photo for photo in photos if search in admin_photo_search_text(photo)]


def filter_admin_photos(photos: list[dict], query: dict[str, list[str]]) -> list[dict]:
    status_filter = (query.get("status") or ["all"])[0]
    issue_filter = (query.get("issue_type") or ["all"])[0]
    search = str((query.get("q") or [""])[0]).strip().lower()

    photos = filter_admin_photos_by_status(photos, status_filter)
    photos = filter_admin_photos_by_issue(photos, issue_filter)
    photos = filter_admin_photos_by_ids(photos, admin_photo_exact_ids(query))
    return filter_admin_photos_by_search(photos, search)


def handle_admin_photos(handler) -> None:
    if not http_admin_session.require_admin(handler):
        return
    query = parse_qs(urlsplit(handler.path).query)
    try:
        photos = filter_admin_photos(admin_photo_review_items(), query)
        http_responses.send_json(handler, 200, {"status": "ok", "photos": photos})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Admin photo queue lookup failed",
            exc,
            public_error="Nie udało się pobrać kolejki zdjęć.",
        )


def handle_admin_privacy_requests(handler) -> None:
    if not http_admin_session.require_admin(handler):
        return
    query = parse_qs(urlsplit(handler.path).query)
    status_filter = query.get("status", ["all"])[0]
    try:
        requests = list_privacy_requests(status=status_filter)
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
        return
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Privacy request queue lookup failed",
            exc,
            public_error="Nie udało się pobrać zgłoszeń prywatności.",
        )
        return
    http_responses.send_json(handler, 200, {"status": "ok", "requests": requests})


def handle_photo_retention_status(handler, retention: dict) -> None:
    if not http_admin_session.require_admin(handler):
        return
    http_responses.send_json(handler, 200, {"status": "ok", "retention": retention})


def handle_delete_admin_photo(handler, route: tuple[str, tuple[str, ...]]) -> None:
    if not http_admin_session.require_admin(handler):
        return
    try:
        scope, ids = route
        if scope != "field":
            raise ValueError("Nieprawidłowy zakres zdjęcia.")
        result = delete_field_photo(
            ids[0],
            core_config.FIELD_PHOTOS_DIR,
            private_dir=core_config.PRIVATE_PHOTOS_DIR,
        )
        http_responses.send_json(handler, 200, result)
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Admin photo delete failed",
            exc,
            public_error="Nie udało się usunąć zdjęcia.",
        )


def handle_review_photo(handler, route: tuple[str, tuple[str, ...]]) -> None:
    if not http_admin_session.require_admin(handler):
        return
    try:
        data = http_request_body.read_json_body(handler)
        scope, ids = route
        if scope != "field":
            raise ValueError("Nieprawidłowy zakres zdjęcia.")
        result = review_field_photo(
            ids[0],
            core_config.FIELD_PHOTOS_DIR,
            status=data.get("public_review_status") if "public_review_status" in data else None,
            redactions=data.get("redactions") if "redactions" in data else None,
            vehicle_insurance_status=data.get("vehicle_insurance_status"),
            vehicle_resolution_status=data.get("vehicle_resolution_status"),
            vehicle_gallery_priority=data.get("vehicle_gallery_priority"),
            private_dir=core_config.PRIVATE_PHOTOS_DIR,
        )
        http_responses.send_json(handler, 200, result)
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Photo review update failed",
            exc,
            public_error="Nie udało się zapisać decyzji przeglądu zdjęcia.",
        )


def handle_update_field_photo_location(handler, photo_id: str) -> None:
    if not http_admin_session.require_admin(handler):
        return
    try:
        data = http_request_body.read_json_body(handler)
        result = update_field_photo_location(
            photo_id,
            core_config.FIELD_PHOTOS_DIR,
            lat=data.get("lat"),
            lon=data.get("lon"),
            private_dir=core_config.PRIVATE_PHOTOS_DIR,
        )
        http_responses.send_json(handler, 200, result)
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Field photo location update failed",
            exc,
            public_error="Nie udało się zapisać lokalizacji zdjęcia.",
        )


def handle_update_privacy_request(handler, request_id: str) -> None:
    if not http_admin_session.require_admin(handler):
        return
    try:
        data = http_request_body.read_json_body(handler)
        result = update_privacy_request(request_id, data)
        http_responses.send_json(handler, 200, result)
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Privacy request update failed",
            exc,
            public_error="Nie udało się zaktualizować zgłoszenia prywatności.",
        )
