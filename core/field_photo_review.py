from __future__ import annotations

import shutil
from contextlib import contextmanager, suppress
from copy import deepcopy
from pathlib import Path
from secrets import token_hex
from typing import Any

from core import config
from core.field_photo_groups import vehicle_photo_group_records
from core.field_photo_insurance import apply_vehicle_insurance_group_update
from core.field_photo_metadata import (
    validated_vehicle_gallery_priority_update,
    validated_vehicle_insurance_update,
    validated_vehicle_resolution_update,
)
from core.field_photo_resolution import apply_vehicle_resolution_group_update
from core.field_photo_serialization import field_photo_summary
from core.field_photo_store import list_field_records, save_field_records
from core.photo_privacy import (
    PUBLIC_IMAGE_FILE,
    PUBLIC_THUMB_FILE,
    apply_review_update,
    is_approved,
    review_status,
    safe_child,
)

_OWNER_CREDENTIAL_FIELDS = (
    "submission_owner",
    "edit_token_salt",
    "edit_token_hash",
    "edit_token_created_at",
)


def _public_derivative_paths(record: dict[str, Any], record_dir: Path) -> list[Path]:
    relative_paths = {
        PUBLIC_IMAGE_FILE,
        PUBLIC_THUMB_FILE,
        str(record.get("public_image_file") or ""),
        str(record.get("public_thumb_file") or ""),
    }
    paths: list[Path] = []
    for relative_path in relative_paths:
        if not relative_path:
            continue
        try:
            path = safe_child(record_dir, relative_path)
        except ValueError:
            continue
        if path not in paths:
            paths.append(path)
    return paths


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


@contextmanager
def _reversible_public_derivatives(record: dict[str, Any], record_dir: Path, *, enabled: bool):
    if not enabled:
        yield
        return

    original_record = deepcopy(record)
    backups: list[tuple[Path, Path]] = []
    staging_complete = False
    token = token_hex(12)
    try:
        for active_path in _public_derivative_paths(original_record, record_dir):
            if not active_path.exists() and not active_path.is_symlink():
                continue
            backup_path = active_path.with_name(f".{active_path.name}.review-backup-{token}")
            active_path.replace(backup_path)
            backups.append((active_path, backup_path))
        staging_complete = True
        yield
    except Exception:
        if staging_complete:
            for active_path in _public_derivative_paths(record, record_dir):
                with suppress(OSError):
                    _remove_path(active_path)
        for active_path, backup_path in reversed(backups):
            if backup_path.exists() or backup_path.is_symlink():
                backup_path.replace(active_path)
        record.clear()
        record.update(original_record)
        raise
    else:
        for _, backup_path in backups:
            with suppress(OSError):
                _remove_path(backup_path)


def _clear_finalized_owner_credentials(record: dict[str, Any]) -> None:
    if review_status(record) not in {"approved", "rejected"}:
        return
    for field in _OWNER_CREDENTIAL_FIELDS:
        record[field] = None


def _records_with_anchor_snapshot(storage_dir: Path, anchor_record: dict[str, Any]) -> list[dict[str, Any]]:
    anchor_id = str(anchor_record["id"])
    records: list[dict[str, Any]] = []
    anchor_seen = False
    for record in list_field_records(storage_dir):
        if str(record["id"]) == anchor_id:
            records.append(anchor_record)
            anchor_seen = True
        else:
            records.append(record)
    if not anchor_seen:
        raise FileNotFoundError("Nie znaleziono zdjęcia kotwiczącego grupę.")
    return records


def review_field_photo_record(
    record: dict[str, Any],
    record_dir: Path,
    storage_dir: Path,
    private_root: Path,
    *,
    status: Any = None,
    redactions: Any = None,
    vehicle_insurance_status: Any = None,
    vehicle_resolution_status: Any = None,
    vehicle_gallery_priority: Any = None,
) -> dict[str, Any]:
    validated_vehicle_insurance_status = validated_vehicle_insurance_update(record, vehicle_insurance_status)
    validated_vehicle_resolution_status = validated_vehicle_resolution_update(record, vehicle_resolution_status)
    validated_gallery_priority = validated_vehicle_gallery_priority_update(record, vehicle_gallery_priority)
    review_updated = status is not None
    if (
        not review_updated
        and validated_vehicle_insurance_status is None
        and validated_vehicle_resolution_status is None
        and validated_gallery_priority is None
    ):
        raise ValueError("Brak decyzji do zapisania.")
    with _reversible_public_derivatives(record, record_dir, enabled=review_updated):
        if review_updated:
            apply_review_update(
                record,
                record_dir,
                private_root,
                status=status,
                redactions=record.get("redactions") if redactions is None else redactions,
                thumb_max_edge=config.FIELD_PHOTO_THUMBNAIL_MAX_EDGE_PX,
                thumb_quality=config.FIELD_PHOTO_THUMBNAIL_JPEG_QUALITY,
            )
        _clear_finalized_owner_credentials(record)

        group_update_requested = (
            validated_vehicle_insurance_status is not None or validated_vehicle_resolution_status is not None
            or validated_gallery_priority is not None
        )
        records = _records_with_anchor_snapshot(storage_dir, record) if group_update_requested else [record]
        records_to_save = {str(record["id"]): record}

        insurance_updated_ids: list[str] = []
        if validated_vehicle_insurance_status is not None:
            insurance_records = apply_vehicle_insurance_group_update(
                records,
                record,
                validated_vehicle_insurance_status,
            )
            insurance_updated_ids = [str(updated["id"]) for updated in insurance_records]
            records_to_save.update((str(updated["id"]), updated) for updated in insurance_records)

        resolution_updated_ids: list[str] = []
        if validated_vehicle_resolution_status is not None:
            resolution_records = apply_vehicle_resolution_group_update(
                records,
                record,
                validated_vehicle_resolution_status,
            )
            resolution_updated_ids = [str(updated["id"]) for updated in resolution_records]
            records_to_save.update((str(updated["id"]), updated) for updated in resolution_records)

        if validated_gallery_priority is not None:
            for item in vehicle_photo_group_records(records, record):
                item["vehicle_gallery_priority"] = validated_gallery_priority if item["id"] == record["id"] else 0
                records_to_save[str(item["id"])] = item
        if validated_vehicle_resolution_status == "removed":
            for item in records_to_save.values():
                item["vehicle_gallery_priority"] = 0
        save_field_records(storage_dir, list(records_to_save.values()))

    result = {"status": "ok", "photo": field_photo_summary(record) if is_approved(record) else {"id": record["id"]}}
    if validated_vehicle_insurance_status is not None:
        result["vehicle_insurance_updated_photo_ids"] = insurance_updated_ids
    if validated_vehicle_resolution_status is not None:
        result["vehicle_resolution_updated_photo_ids"] = resolution_updated_ids
    return result
