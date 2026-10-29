"""Read-only, projected SQLite query for map photos.

The legacy list_field_photos prepares every full record, including private EXIF
and redaction metadata. This route reads only the public map projection and
repairs individual stale records only if their public derivatives are missing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.database import connect_database_read_only
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
