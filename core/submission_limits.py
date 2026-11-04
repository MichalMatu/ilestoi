from __future__ import annotations

from pathlib import Path

from core import config
from core.database import connect_database_read_only
from core.field_photo_store import database_path_for
from core.photo_privacy import safe_child


def _private_size(private_original_file: str | None, private_dir: Path) -> int:
    try:
        path = safe_child(private_dir, private_original_file)
    except (TypeError, ValueError):
        return 0
    try:
        return path.stat().st_size if path.exists() else 0
    except OSError:
        return 0


def pending_submission_usage(
    *,
    owner: str | None,
    field_photos_dir: Path,
    private_dir: Path,
) -> dict[str, int]:
    """Read only matching quota rows; never decode or repair unrelated photos."""
    owner = str(owner or "").strip()
    where = "public_review_status IN ('draft', 'pending')"
    params: list[str] = []
    if owner:
        where += " AND TRIM(COALESCE(submission_owner, '')) = ?"
        params.append(owner)

    connection = connect_database_read_only(database_path_for(field_photos_dir))
    try:
        originals = [
            row["private_original_file"]
            for row in connection.execute(f"SELECT private_original_file FROM field_photos WHERE {where}", params)
        ]
    finally:
        connection.close()

    return {
        "bytes": sum(_private_size(original, private_dir) for original in originals),
        "items": len(originals),
        "max_bytes": config.PENDING_SUBMISSION_MAX_BYTES,
        "max_items": config.PENDING_SUBMISSION_MAX_ITEMS,
    }


def assert_pending_submission_quota(
    *,
    owner: str,
    additional_bytes: int = 0,
    additional_items: int = 1,
    field_photos_dir: Path,
    private_dir: Path,
) -> dict[str, int]:
    usage = pending_submission_usage(
        owner=owner,
        field_photos_dir=field_photos_dir,
        private_dir=private_dir,
    )
    next_bytes = usage["bytes"] + max(0, int(additional_bytes or 0))
    next_items = usage["items"] + max(0, int(additional_items or 0))
    if next_bytes > usage["max_bytes"]:
        raise ValueError(
            "Przekroczono limit miejsca dla materiałów oczekujących na moderację "
            f"({usage['max_bytes'] // config.BYTES_PER_MIB} MB)."
        )
    if next_items > usage["max_items"]:
        raise ValueError(f"Przekroczono limit liczby materiałów oczekujących na moderację ({usage['max_items']}).")
    usage["next_bytes"] = next_bytes
    usage["next_items"] = next_items
    return usage
