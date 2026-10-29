import hashlib

from app.http import admin_session as http_admin_session
from app.http import responses as http_responses
from app.http.rate_limit import client_key
from core import config as core_config
from core.settings_store import DEFAULT_PUBLIC_FEATURES, DEFAULT_PUBLIC_LAYERS, load_app_settings
from core.submission_limits import assert_pending_submission_quota

_FIELD_PHOTO_PUBLIC_LAYER_KEYS = {
    "vehicle": "vehicles",
    "infrastructure": "field_photo_infrastructure",
    "smoke": "field_photo_smoke",
}


def submission_owner(handler) -> str:
    ip = client_key(handler)
    ua = str(handler.headers.get("User-Agent") or "")
    digest = hashlib.sha256(f"{ip}|{ua}".encode()).hexdigest()[:24]
    return f"public:{digest}"


def ensure_public_submission_quota(handler, *, additional_bytes: int = 0, additional_items: int = 1) -> None:
    if http_admin_session.is_admin(handler):
        return
    assert_pending_submission_quota(
        owner=submission_owner(handler),
        additional_bytes=additional_bytes,
        additional_items=additional_items,
        field_photos_dir=core_config.FIELD_PHOTOS_DIR,
        private_dir=core_config.PRIVATE_PHOTOS_DIR,
    )


def public_layer_settings() -> dict[str, bool]:
    raw = load_app_settings().get("public_layers", {})
    if not isinstance(raw, dict):
        return DEFAULT_PUBLIC_LAYERS.copy()
    settings = DEFAULT_PUBLIC_LAYERS.copy()
    for key in settings:
        settings[key] = bool(raw.get(key, settings[key]))
    return settings


def public_layer_allowed(handler, key: str) -> bool:
    return http_admin_session.is_admin(handler) or public_layer_settings().get(key, True)


def require_public_layer(handler, key: str, message: str) -> bool:
    if public_layer_allowed(handler, key):
        return True
    http_responses.send_json(handler, 403, {"error": message})
    return False


def public_feature_settings() -> dict[str, bool]:
    raw = load_app_settings().get("public_features", {})
    if not isinstance(raw, dict):
        return DEFAULT_PUBLIC_FEATURES.copy()
    settings = DEFAULT_PUBLIC_FEATURES.copy()
    for key in settings:
        settings[key] = bool(raw.get(key, settings[key]))
    return settings


def public_feature_allowed(handler, key: str) -> bool:
    return http_admin_session.is_admin(handler) or public_feature_settings().get(key, True)


def require_public_feature(handler, key: str, message: str) -> bool:
    if public_feature_allowed(handler, key):
        return True
    http_responses.send_json(handler, 403, {"error": message})
    return False


def public_field_photo_allowed(handler, photo: dict, *, layer_settings: dict[str, bool] | None = None) -> bool:
    if http_admin_session.is_admin(handler):
        return True
    if str(photo.get("public_review_status") or "").strip() == "draft":
        return False
    if layer_settings is None:
        layer_settings = public_layer_settings()
    if str(photo.get("public_review_status") or "approved") == "pending":
        return layer_settings.get("field_photo_pending", True)
    issue_type = str(photo.get("issue_type") or "vehicle")
    key = _FIELD_PHOTO_PUBLIC_LAYER_KEYS.get(issue_type, "vehicles")
    return layer_settings.get(key, True)


def field_photo_issue_layer_key(issue_type: object) -> str:
    issue_type_text = str(issue_type or core_config.DEFAULT_FIELD_PHOTO_ISSUE_TYPE).strip()
    if issue_type_text not in core_config.FIELD_PHOTO_ISSUE_TYPES:
        raise ValueError("Nieprawidłowy typ pinezki terenowej.")
    return _FIELD_PHOTO_PUBLIC_LAYER_KEYS.get(issue_type_text, "vehicles")
