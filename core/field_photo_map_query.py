"""Read-only, projected SQLite query for map photos.

The legacy list_field_photos prepares every full record, including private EXIF
and redaction metadata. This route reads only the public map projection and
repairs individual stale records only if their public derivatives are missing.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core import config
from core.database import connect_database_read_only
from core.field_photo_groups import same_vehicle_photo_group
from core.geo import lon_meters_per_degree
from core.field_photo_serialization import field_photo_summary
from core.field_photo_store import database_path_for
from core.field_photos import load_field_photo_record
from core.photo_privacy import safe_existing_child

# No original paths, owner credentials, EXIF or redaction payloads are read.
_MAP_COLUMNS = (
    "id",
    "created_at",
    "submitted_at",
    "captured_at",
    "format",
    "public_width",
    "public_height",
    "public_review_status",
    "reviewed_at",
    "issue_type",
    "vehicle_insurance_status",
    "vehicle_insurance_checked_at",
    "vehicle_resolution_status",
    "vehicle_resolution_updated_at",
    "vehicle_gallery_priority",
    "lat",
    "lon",
    "coordinate_source",
    "position_updated_at",
    "links_json",
    "public_image_file",
    "public_thumb_file",
)


def _map_photo(record: dict[str, Any], storage_dir: Path, private_dir: Path | None) -> dict[str, Any]:
    photo_id = str(record["id"])
    # Existing application data can predate generated derivatives. Repair that
    # one record, not the whole table; new writes prepare these files eagerly.
    if record["public_review_status"] == "approved":
        photo_dir = storage_dir / photo_id
        if not safe_existing_child(photo_dir, record.get("public_image_file")) or not safe_existing_child(
            photo_dir, record.get("public_thumb_file")
        ):
            repaired = load_field_photo_record(photo_id, storage_dir, private_dir=private_dir)
            return field_photo_summary(repaired)
    elif record.get("public_image_file") or record.get("public_thumb_file"):
        # Historic pending records might still have public derivatives.
        repaired = load_field_photo_record(photo_id, storage_dir, private_dir=private_dir)
        return field_photo_summary(repaired)

    record["links"] = json.loads(str(record.pop("links_json") or "{}"))
    return field_photo_summary(record)


def map_visibility_conditions(
    approved_types: tuple[str, ...] | None, pending_visible: bool
) -> tuple[list[str], list[Any]]:
    """Shared review and public layer restrictions for all read-only map SQL."""
    conditions = ["public_review_status IN ('approved', 'pending')"]
    params: list[Any] = []
    if approved_types is None:
        return conditions, params
    clauses: list[str] = []
    if approved_types:
        slots = ", ".join("?" for _ in approved_types)
        clauses.append(f"(public_review_status = 'approved' AND issue_type IN ({slots}))")
        params.extend(approved_types)
    if pending_visible:
        clauses.append("public_review_status = 'pending'")
    if not clauses:
        return ["0"], []
    conditions.append("(" + " OR ".join(clauses) + ")")
    return conditions, params


def list_map_field_photos(
    storage_dir: Path,
    *,
    bounds: tuple[float, float, float, float] | None = None,
    limit: int | None = None,
    after: tuple[str, str] | None = None,
    approved_types: tuple[str, ...] | None = None,
    pending_visible: bool = True,
    private_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], tuple[str, str] | None]:
    """Map summaries with optional bounds and deterministic keyset pagination.

    approved_types=None means an authenticated administrator. Otherwise SQL
    removes hidden approved layers; pending is controlled by one public switch.
    The cursor is created from the last returned database row, never an offset.
    """
    conditions, params = map_visibility_conditions(approved_types, pending_visible)
    if conditions == ["0"]:
        return [], None

    if bounds is not None:
        west, south, east, north = bounds
        conditions.append("lat >= ? AND lat <= ?")
        params.extend((south, north))
        if west <= east:
            conditions.append("lon >= ? AND lon <= ?")
        else:
            conditions.append("(lon >= ? OR lon <= ?)")
        params.extend((west, east))

    if after is not None:
        conditions.append("(created_at < ? OR (created_at = ? AND id < ?))")
        params.extend((after[0], after[0], after[1]))

    sql = (
        f"SELECT {', '.join(_MAP_COLUMNS)} FROM field_photos "
        + "WHERE "
        + " AND ".join(conditions)
        + " ORDER BY created_at DESC, id DESC"
    )
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit + 1)

    connection = connect_database_read_only(database_path_for(storage_dir))
    try:
        rows = [dict(row) for row in connection.execute(sql, params)]
    finally:
        connection.close()

    has_next = limit is not None and len(rows) > limit
    candidates = rows[:limit] if limit is not None else rows
    result = []
    for record in candidates:
        try:
            result.append(_map_photo(record, storage_dir, private_dir))
        except (OSError, ValueError, FileNotFoundError, json.JSONDecodeError):
            # Keep the historical list behavior for a damaged photo row.
            continue
    if not has_next or not candidates:
        return result, None
    last = candidates[-1]
    return result, (str(last["created_at"]), str(last["id"]))



_GALLERY_MIN_OBSERVATION = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _gallery_observation_date(record: dict[str, Any], now: datetime) -> datetime | None:
    """Use actual capture time when valid; otherwise first upload/submission."""
    for key in ("captured_at", "created_at", "submitted_at"):
        raw = record.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        text = raw.strip()
        if len(text) < 10 or text[4:5] != "-" or text[7:8] != "-":
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        if _GALLERY_MIN_OBSERVATION <= parsed <= now + timedelta(minutes=5):
            return parsed
    return None


def _gallery_group_first_observed(
    connection: Any, nominated: dict[str, Any], now: datetime,
) -> str | None:
    """Oldest documented observation of this *group*, not its cover photo."""
    lat, lon = float(nominated["lat"]), float(nominated["lon"])
    radius = config.FIELD_PHOTO_GROUP_RADIUS_M
    lat_margin = radius / 111_320.0 * 1.1
    lon_margin = radius / max(abs(lon_meters_per_degree(lat)), 0.000001) * 1.1
    candidates = connection.execute(
        """SELECT issue_type, lat, lon, captured_at, created_at, submitted_at
           FROM field_photos WHERE issue_type = 'vehicle'
             AND public_review_status = 'approved'
             AND vehicle_resolution_status = 'active'
             AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?""",
        (lat - lat_margin, lat + lat_margin, lon - lon_margin, lon + lon_margin),
    )
    dates = [
        observed for record in candidates
        if same_vehicle_photo_group(nominated, dict(record))
        for observed in [_gallery_observation_date(dict(record), now)]
        if observed is not None
    ]
    earliest = min(dates, default=None)
    return earliest.isoformat().replace("+00:00", "Z") if earliest is not None else None


def _gallery_sort_key(photo: dict[str, Any]) -> tuple[int, datetime, str]:
    raw = photo.get("first_observed_at")
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else datetime.max.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        observed = datetime.max.replace(tzinfo=timezone.utc)
    return (-int(photo["vehicle_gallery_priority"]), observed, str(photo["id"]))


def list_map_vehicle_gallery(
    storage_dir: Path, *, bounds: tuple[float, float, float, float], private_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Bounded read-only public gallery, independent of normal map zoom."""
    west, south, east, north = bounds
    conditions = [
        "issue_type = 'vehicle'", "public_review_status = 'approved'",
        "vehicle_resolution_status = 'active'", "vehicle_gallery_priority > 0",
        "lat >= ? AND lat <= ?",
    ]
    params: list[Any] = [south, north]
    conditions.append("lon >= ? AND lon <= ?" if west <= east else "(lon >= ? OR lon <= ?)")
    params.extend([west, east])
    sql = (
        f"SELECT {', '.join(_MAP_COLUMNS)} FROM field_photos WHERE "
        + " AND ".join(conditions)
        + " ORDER BY vehicle_gallery_priority DESC, created_at ASC, id ASC LIMIT 100"
    )
    connection = connect_database_read_only(database_path_for(storage_dir))
    try:
        rows = [dict(row) for row in connection.execute(sql, params)]
        now = datetime.now(timezone.utc)
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                public_photo = _map_photo(row, storage_dir, private_dir)
                public_photo["first_observed_at"] = _gallery_group_first_observed(connection, row, now)
                result.append(public_photo)
            except (OSError, ValueError, FileNotFoundError, json.JSONDecodeError):
                continue
    finally:
        connection.close()
    return sorted(result, key=_gallery_sort_key)
