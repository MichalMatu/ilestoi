from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core import config
from core.config import DEFAULT_ENHANCEMENT_SETTINGS, EnhancementSettings
from core.database import apply_migrations, connect_database, json_text, now_iso

DATABASE_PATH = Path(__file__).resolve().parent.parent / config.DATABASE_PATH
DEFAULT_PUBLIC_LAYERS: dict[str, bool] = {
    "vehicles": True,
    "field_photo_infrastructure": True,
    "field_photo_smoke": True,
    "field_photo_pending": True,
    "cadastral": True,
    "base_map_osm": True,
}
DEFAULT_PUBLIC_FEATURES: dict[str, bool] = {
    "report_pdfs": True,
    "photo_uploads": True,
    "vehicle_gallery": True,
}
DEFAULT_MAP_VIEW: dict[str, float | int] = {
    "lat": 51.107883,
    "lon": 17.038538,
    "zoom": 13,
}

_ENHANCEMENT_LIMITS: dict[str, tuple[float, float]] = {
    "clahe_clip_limit": (0.1, 5.0),
    "clahe_tile_grid_size": (1, 32),
    "l_percentile_low": (0.0, 40.0),
    "l_percentile_high": (60.0, 100.0),
    "l_output_low": (0.0, 120.0),
    "l_output_high": (135.0, 255.0),
    "l_min_percentile_span": (1.0, 50.0),
    "decast_strength": (0.0, 1.0),
}


def enhancement_settings_to_dict(settings: EnhancementSettings) -> dict[str, Any]:
    return asdict(settings)


def enhancement_settings_from_dict(raw: Any) -> EnhancementSettings:
    defaults = enhancement_settings_to_dict(DEFAULT_ENHANCEMENT_SETTINGS)
    if not isinstance(raw, dict):
        return DEFAULT_ENHANCEMENT_SETTINGS

    data = defaults.copy()
    if "enabled" in raw:
        data["enabled"] = bool(raw["enabled"])

    for key, (min_value, max_value) in _ENHANCEMENT_LIMITS.items():
        if key not in raw:
            continue
        try:
            value = float(raw[key])
        except (TypeError, ValueError):
            continue
        value = max(min_value, min(max_value, value))
        data[key] = int(round(value)) if key == "clahe_tile_grid_size" else value

    if data["l_percentile_low"] >= data["l_percentile_high"]:
        data["l_percentile_low"] = defaults["l_percentile_low"]
        data["l_percentile_high"] = defaults["l_percentile_high"]
    if data["l_output_low"] >= data["l_output_high"]:
        data["l_output_low"] = defaults["l_output_low"]
        data["l_output_high"] = defaults["l_output_high"]

    return EnhancementSettings(**data)


def default_app_settings() -> dict[str, Any]:
    return {
        "enhancement": enhancement_settings_to_dict(DEFAULT_ENHANCEMENT_SETTINGS),
        "map_view": DEFAULT_MAP_VIEW.copy(),
        "public_layers": DEFAULT_PUBLIC_LAYERS.copy(),
        "public_features": DEFAULT_PUBLIC_FEATURES.copy(),
    }


def map_view_settings_from_dict(raw: Any) -> dict[str, float | int]:
    settings = DEFAULT_MAP_VIEW.copy()
    if not isinstance(raw, dict):
        return settings

    try:
        lat = float(raw.get("lat"))
        lon = float(raw.get("lon"))
        zoom = int(round(float(raw.get("zoom"))))
    except (TypeError, ValueError):
        return settings

    if -90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= zoom <= 22:
        settings["lat"] = round(lat, 6)
        settings["lon"] = round(lon, 6)
        settings["zoom"] = zoom
    return settings


def public_layer_settings_from_dict(raw: Any) -> dict[str, bool]:
    settings = DEFAULT_PUBLIC_LAYERS.copy()
    if not isinstance(raw, dict):
        return settings

    for key in settings:
        if key in raw:
            settings[key] = bool(raw[key])
    return settings


def public_feature_settings_from_dict(raw: Any) -> dict[str, bool]:
    settings = DEFAULT_PUBLIC_FEATURES.copy()
    if not isinstance(raw, dict):
        return settings

    for key in settings:
        if key in raw:
            settings[key] = bool(raw[key])
    return settings


def _connection():
    connection = connect_database(DATABASE_PATH)
    apply_migrations(connection)
    return connection


def _settings_rows() -> dict[str, Any]:
    connection = _connection()
    try:
        rows = connection.execute("SELECT key, value_json FROM settings")
        settings: dict[str, Any] = {}
        for row in rows:
            try:
                settings[str(row["key"])] = json.loads(str(row["value_json"]))
            except json.JSONDecodeError:
                continue
        return settings
    finally:
        connection.close()


def load_app_settings() -> dict[str, Any]:
    raw = _settings_rows()
    if not raw:
        return default_app_settings()

    settings = default_app_settings()
    settings["enhancement"] = enhancement_settings_to_dict(enhancement_settings_from_dict(raw.get("enhancement")))
    settings["map_view"] = map_view_settings_from_dict(raw.get("map_view"))
    settings["public_layers"] = public_layer_settings_from_dict(raw.get("public_layers"))
    settings["public_features"] = public_feature_settings_from_dict(raw.get("public_features"))
    return settings


def save_app_settings(raw: dict[str, Any]) -> dict[str, Any]:
    current = load_app_settings()
    if "enhancement" in raw:
        current["enhancement"] = enhancement_settings_to_dict(enhancement_settings_from_dict(raw["enhancement"]))
    if "map_view" in raw:
        current["map_view"] = map_view_settings_from_dict(raw["map_view"])
    if "public_layers" in raw:
        current["public_layers"] = public_layer_settings_from_dict(raw["public_layers"])
    if "public_features" in raw:
        current["public_features"] = public_feature_settings_from_dict(raw["public_features"])

    connection = _connection()
    try:
        with connection:
            for key, value in sorted(current.items()):
                connection.execute(
                    """
                    INSERT INTO settings (key, value_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    (key, json_text(value, {}), now_iso()),
                )
    finally:
        connection.close()

    return current
