from __future__ import annotations

import hashlib
import math
import re
import secrets
import shutil
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from core import config
from core.field_photo_deletion import delete_loaded_field_photos as _delete_loaded_field_photos
from core.field_photo_insurance import (
    set_vehicle_insurance as _set_vehicle_insurance,
)
from core.field_photo_insurance import (
    vehicle_insurance_checked_at_for_status as _vehicle_insurance_checked_at_for_status,
)
from core.field_photo_metadata import (
    issue_type as _issue_type,
)
from core.field_photo_metadata import (
    validated_vehicle_insurance_update as _validated_vehicle_insurance_update,
)
from core.field_photo_metadata import (
    vehicle_insurance_checked_at as _vehicle_insurance_checked_at,
)
from core.field_photo_metadata import (
    vehicle_insurance_status as _vehicle_insurance_status,
)
from core.field_photo_metadata import (
    vehicle_resolution_status as _vehicle_resolution_status,
)
from core.field_photo_metadata import (
    vehicle_resolution_updated_at as _vehicle_resolution_updated_at,
)
from core.field_photo_review import review_field_photo_record as _review_field_photo_record
from core.field_photo_serialization import (
    admin_review_item as _admin_review_item,
)
from core.field_photo_serialization import (
    field_photo_summary as _summary,
)
from core.field_photo_serialization import (
    owner_review_item as _owner_review_item,
)
from core.field_photo_store import (
    FIELD_PHOTO_ID_RE as _FIELD_PHOTO_ID_RE,
)
from core.field_photo_store import (
    delete_field_records as _delete_field_records,
)
from core.field_photo_store import (
    list_field_records as _list_field_records,
)
from core.field_photo_store import (
    load_field_record_by_id as _load_field_record_by_id,
)
from core.field_photo_store import (
    save_field_record as _save_field_record,
)
from core.field_photo_store import (
    save_field_records as _save_field_records,
)
from core.field_photo_store import (
    validate_photo_id as _validate_photo_id,
)
from core.field_photo_upload import validated_upload_image, write_bytes_atomic
from core.geo import external_map_links
from core.photo_privacy import (
    REVIEW_STATUSES,
    apply_review_update,
    ensure_review_fields,
    generate_public_derivatives,
    is_approved,
    remove_public_derivatives,
    review_status,
    safe_child,
    safe_existing_child,
)
from core.photo_tokens import new_photo_edit_token_hash, normalize_photo_edit_token, verify_photo_edit_token
from core.uploads import UploadedFile

FIELD_PHOTO_ID_RE = _FIELD_PHOTO_ID_RE
_FIELD_PHOTO_MUTATION_LOCK = RLock()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _now_iso() -> str:
    return _now_utc().isoformat().replace("+00:00", "Z")


def _safe_original_name(raw_name: str, ext: str) -> str:
    stem = Path(raw_name or "").stem or "zdjecie"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "zdjecie"
    return f"{stem[:80]}{ext}"


def _record_dir_for(photo_id: str, storage_dir: Path) -> Path:
    photo_id = _validate_photo_id(photo_id)
    root = storage_dir.resolve()
    record_dir = (storage_dir / photo_id).resolve()
    if root != record_dir and root not in record_dir.parents:
        raise ValueError("Nieprawidłowa ścieżka zdjęcia.")
    return record_dir


def _coord_float(value: Any, label: str) -> float:
    try:
        coord = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Nieprawidłowa wartość {label}.") from exc
    if not math.isfinite(coord):
        raise ValueError(f"Nieprawidłowa wartość {label}.")
    return coord


def _map_coordinates_from(map_lat: Any = None, map_lon: Any = None) -> tuple[float, float, Literal["map"]]:
    if map_lat is None or map_lon is None or str(map_lat).strip() == "" or str(map_lon).strip() == "":
        raise ValueError("Wskaż punkt zdjęcia na mapie i spróbuj ponownie.")
    lat = _coord_float(map_lat, "map_lat")
    lon = _coord_float(map_lon, "map_lon")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Nieprawidłowe współrzędne punktu mapy.")
    return lat, lon, "map"


def _validated_lat_lon(lat_value: Any, lon_value: Any) -> tuple[float, float]:
    lat = _coord_float(lat_value, "lat")
    lon = _coord_float(lon_value, "lon")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Nieprawidłowe współrzędne zdjęcia terenowego.")
    return lat, lon


def _links(lat: float, lon: float) -> dict[str, str]:
    return external_map_links(lat, lon)


def _photo_id(upload: UploadedFile) -> str:
    stamp = _now_utc().strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha1(
        f"{upload.filename}:{len(upload.data)}:{secrets.token_urlsafe(12)}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:8]
    return f"photo_{stamp}_{digest}"


def _private_dir(private_dir: Path | None) -> Path:
    return private_dir or config.PRIVATE_PHOTOS_DIR


def _prepare_field_record(record_dir: Path, record: dict[str, Any], private_dir: Path) -> bool:
    changed = ensure_review_fields(record)
    issue_type = _issue_type(record.get("issue_type"))
    vehicle_insurance_status = _vehicle_insurance_status(issue_type, record.get("vehicle_insurance_status"))
    if record.get("vehicle_insurance_status") != vehicle_insurance_status:
        record["vehicle_insurance_status"] = vehicle_insurance_status
        changed = True
    vehicle_insurance_checked_at = _vehicle_insurance_checked_at(
        issue_type,
        vehicle_insurance_status,
        record.get("vehicle_insurance_checked_at"),
    )
    if record.get("vehicle_insurance_checked_at") != vehicle_insurance_checked_at:
        record["vehicle_insurance_checked_at"] = vehicle_insurance_checked_at
        changed = True
    vehicle_resolution_status = _vehicle_resolution_status(issue_type, record.get("vehicle_resolution_status"))
    if record.get("vehicle_resolution_status") != vehicle_resolution_status:
        record["vehicle_resolution_status"] = vehicle_resolution_status
        changed = True
    vehicle_resolution_updated_at = _vehicle_resolution_updated_at(
        issue_type,
        vehicle_resolution_status,
        record.get("vehicle_resolution_updated_at"),
    )
    if record.get("vehicle_resolution_updated_at") != vehicle_resolution_updated_at:
        record["vehicle_resolution_updated_at"] = vehicle_resolution_updated_at
        changed = True
    if not is_approved(record):
        remove_public_derivatives(record, record_dir)
    elif not safe_existing_child(record_dir, record.get("public_image_file")) or not safe_existing_child(
        record_dir, record.get("public_thumb_file")
    ):
        generate_public_derivatives(
            record,
            record_dir,
            private_dir,
            thumb_max_edge=config.FIELD_PHOTO_THUMBNAIL_MAX_EDGE_PX,
            thumb_quality=config.FIELD_PHOTO_THUMBNAIL_JPEG_QUALITY,
        )
        changed = True
    return changed


def _load_field_record(record_dir: Path, private_dir: Path) -> dict[str, Any]:
    record = _load_field_record_by_id(record_dir.name, record_dir.parent)
    if _prepare_field_record(record_dir, record, private_dir):
        _save_field_record(record_dir.parent, record)
    return record


def field_photo_record_dir(photo_id: str, storage_dir: Path) -> Path:
    return _record_dir_for(photo_id, storage_dir)


def load_field_photo_record(
    photo_id: str,
    storage_dir: Path,
    *,
    private_dir: Path | None = None,
) -> dict[str, Any]:
    record_dir = _record_dir_for(photo_id, storage_dir)
    return _load_field_record(record_dir, _private_dir(private_dir))


def list_field_photo_records(
    storage_dir: Path,
    *,
    private_dir: Path | None = None,
    prepare: bool = True,
) -> list[dict[str, Any]]:
    private_root = _private_dir(private_dir)
    records: list[dict[str, Any]] = []
    for record in _list_field_records(storage_dir):
        record_dir = _record_dir_for(str(record["id"]), storage_dir)
        if prepare and _prepare_field_record(record_dir, record, private_root):
            _save_field_record(storage_dir, record)
        records.append(record)
    return records


def save_field_photo_record(record: dict[str, Any], storage_dir: Path) -> None:
    _save_field_record(storage_dir, record)


def _require_edit_token(record: dict[str, Any], edit_token: Any) -> None:
    if not verify_photo_edit_token(edit_token, record.get("edit_token_salt"), record.get("edit_token_hash")):
        raise PermissionError("Nieprawidłowy token edycji zdjęcia.")


def validated_field_photo_ids(photo_ids: list[Any], empty_message: str) -> list[str]:
    if len(photo_ids) > config.MAX_OWNER_PHOTO_IDS:
        raise ValueError(f"Jedna operacja może objąć maksymalnie {config.MAX_OWNER_PHOTO_IDS} zdjęć.")
    requested_ids: list[str] = []
    for raw_photo_id in photo_ids:
        photo_id = str(raw_photo_id or "").strip()
        if photo_id and photo_id not in requested_ids:
            requested_ids.append(_validate_photo_id(photo_id))
    if not requested_ids:
        raise ValueError(empty_message)
    return requested_ids


def list_field_photos(storage_dir: Path, *, private_dir: Path | None = None) -> list[dict[str, Any]]:
    private_root = _private_dir(private_dir)
    records: list[dict[str, Any]] = []
    for record in _list_field_records(storage_dir):
        try:
            record_dir = _record_dir_for(str(record["id"]), storage_dir)
            if _prepare_field_record(record_dir, record, private_root):
                _save_field_record(storage_dir, record)
        except (OSError, ValueError, FileNotFoundError):
            continue
        status = review_status(record)
        if isinstance(record, dict) and record.get("id") and status not in {"draft", "rejected"}:
            records.append(_summary(record))
    return sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def list_owner_field_photo_review_items(
    photo_ids: list[Any],
    edit_token: Any,
    storage_dir: Path,
    *,
    private_dir: Path | None = None,
) -> list[dict[str, Any]]:
    normalize_photo_edit_token(edit_token)
    private_root = _private_dir(private_dir)
    requested_ids = validated_field_photo_ids(photo_ids, "Wskaż zdjęcie do edycji.")

    items: list[dict[str, Any]] = []
    for photo_id in requested_ids:
        record_dir = _record_dir_for(photo_id, storage_dir)
        try:
            record = _load_field_record(record_dir, private_root)
        except FileNotFoundError:
            continue
        try:
            _require_edit_token(record, edit_token)
        except PermissionError:
            continue
        items.append(_owner_review_item(record))
    if not items:
        raise PermissionError("Nieprawidłowy token edycji zdjęcia.")
    return sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def list_field_photo_review_items(storage_dir: Path, *, private_dir: Path | None = None) -> list[dict[str, Any]]:
    private_root = _private_dir(private_dir)
    records: list[dict[str, Any]] = []
    for record in _list_field_records(storage_dir):
        try:
            record_dir = _record_dir_for(str(record["id"]), storage_dir)
            if _prepare_field_record(record_dir, record, private_root):
                _save_field_record(storage_dir, record)
        except (OSError, ValueError, FileNotFoundError):
            continue
        if not isinstance(record, dict) or not record.get("id") or review_status(record) == "draft":
            continue
        records.append(_admin_review_item(record))
    return sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def save_field_photo(
    upload: UploadedFile,
    storage_dir: Path,
    *,
    map_lat: Any = None,
    map_lon: Any = None,
    issue_type: Any = None,
    private_dir: Path | None = None,
    submission_owner: str | None = None,
    edit_token: Any = None,
    public_review_status: Any = "pending",
    vehicle_insurance_status: Any = None,
) -> dict[str, Any]:
    private_root = _private_dir(private_dir)
    if upload.field_name != "photo":
        raise ValueError("Nie znaleziono pola pliku 'photo'.")
    size = len(upload.data)
    if size <= 0:
        raise ValueError("Dodaj zdjęcie do uploadu.")
    if size > config.MAX_FIELD_PHOTO_BYTES:
        raise ValueError("Zdjęcie przekracza limit 10 MB.")
    issue_type_text = _issue_type(issue_type)
    review_status_text = str(public_review_status or "pending").strip()
    if review_status_text not in REVIEW_STATUSES:
        raise ValueError("Nieprawidłowy status przeglądu zdjęcia.")

    image_format, width, height, captured_at, limited_exif = validated_upload_image(upload)
    lat, lon, coordinate_source = _map_coordinates_from(map_lat, map_lon)

    ext, content_type = config.ALLOWED_UPLOAD_IMAGE_FORMATS[image_format]
    photo_id = _photo_id(upload)
    record_dir = storage_dir / photo_id

    private_original_file = f"field_photos/{photo_id}/original{ext}"
    vehicle_insurance_status_text = _vehicle_insurance_status(issue_type_text, vehicle_insurance_status)
    record = {
        "id": photo_id,
        "created_at": _now_iso(),
        "original_filename": _safe_original_name(upload.filename, ext),
        "content_type": content_type,
        "format": image_format,
        "size_bytes": size,
        "image_width": width,
        "image_height": height,
        "issue_type": issue_type_text,
        "vehicle_insurance_status": vehicle_insurance_status_text,
        "vehicle_insurance_checked_at": _vehicle_insurance_checked_at_for_status(vehicle_insurance_status_text),
        "vehicle_resolution_status": config.DEFAULT_FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS,
        "vehicle_resolution_updated_at": None,
        "lat": lat,
        "lon": lon,
        "coordinate_source": coordinate_source,
        "captured_at": captured_at,
        "exif": limited_exif,
        "private_original_file": private_original_file,
        "public_review_status": review_status_text,
        "redactions": [],
        "reviewed_at": None,
        "submission_owner": submission_owner,
        "links": _links(lat, lon),
    }
    if edit_token is not None and str(edit_token).strip():
        record.update(new_photo_edit_token_hash(edit_token))
        record["edit_token_created_at"] = _now_iso()
    with _FIELD_PHOTO_MUTATION_LOCK:
        original_path = safe_child(private_root, private_original_file)
        try:
            record_dir.mkdir(parents=True, exist_ok=False)
            if private_root.is_symlink():
                raise ValueError("Katalog prywatnych zdjęć nie może być dowiązaniem symbolicznym.")
            private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            private_root.chmod(0o700)
            original_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            (private_root / "field_photos").chmod(0o700)
            original_path.parent.chmod(0o700)
            write_bytes_atomic(original_path, upload.data)
            _save_field_record(storage_dir, record)
        except Exception:
            with suppress(Exception):
                _delete_field_records(storage_dir, [photo_id])
            with suppress(OSError):
                shutil.rmtree(record_dir)
            with suppress(OSError):
                original_path.unlink()
            with suppress(OSError):
                original_path.parent.rmdir()
            with suppress(OSError):
                (private_root / "field_photos").rmdir()
            raise
    return {"status": "ok", "photo": _summary(record)}


def update_field_photo_location(
    photo_id: str,
    storage_dir: Path,
    *,
    lat: Any,
    lon: Any,
    private_dir: Path | None = None,
) -> dict[str, Any]:
    with _FIELD_PHOTO_MUTATION_LOCK:
        record_dir = _record_dir_for(photo_id, storage_dir)
        record = _load_field_record(record_dir, _private_dir(private_dir))
        lat_float, lon_float = _validated_lat_lon(lat, lon)
        record["lat"] = lat_float
        record["lon"] = lon_float
        record["coordinate_source"] = "manual"
        record["position_updated_at"] = _now_iso()
        record["links"] = _links(lat_float, lon_float)
        _save_field_record(storage_dir, record)
        return {"status": "ok", "photo": _summary(record)}


def delete_field_photo(photo_id: str, storage_dir: Path, *, private_dir: Path | None = None) -> dict[str, Any]:
    with _FIELD_PHOTO_MUTATION_LOCK:
        record_dir = _record_dir_for(photo_id, storage_dir)
        private_root = _private_dir(private_dir)
        record = _load_field_record(record_dir, private_root)
        deleted = _delete_loaded_field_photos(
            [(photo_id, record_dir, record)],
            storage_dir,
            private_root=private_root,
        )
        return {"status": "ok", "deleted": deleted[0]}


def field_photo_asset(
    photo_id: str,
    storage_dir: Path,
    asset: Literal["public-image", "public-thumb", "original"],
    *,
    private_dir: Path | None = None,
) -> tuple[Path, str]:
    record_dir = _record_dir_for(photo_id, storage_dir)
    private_root = _private_dir(private_dir)
    record = _load_field_record(record_dir, private_root)
    if asset == "public-thumb":
        if not is_approved(record):
            raise FileNotFoundError("Nie znaleziono publicznej miniatury zdjęcia.")
        file_name = str(record.get("public_thumb_file") or "")
        content_type = "image/jpeg"
        path = safe_child(record_dir, file_name)
    elif asset == "public-image":
        if not is_approved(record):
            raise FileNotFoundError("Nie znaleziono publicznej kopii zdjęcia.")
        file_name = str(record.get("public_image_file") or "")
        content_type = "image/jpeg"
        path = safe_child(record_dir, file_name)
    else:
        file_name = str(record.get("private_original_file") or "")
        content_type = str(record.get("content_type") or "application/octet-stream")
        path = safe_child(private_root, file_name)
    if not path.exists():
        raise FileNotFoundError("Nie znaleziono pliku zdjęcia terenowego.")
    return path, content_type


def field_photo_owner_original_asset(
    photo_id: str,
    edit_token: Any,
    storage_dir: Path,
    *,
    private_dir: Path | None = None,
) -> tuple[Path, str]:
    record_dir = _record_dir_for(photo_id, storage_dir)
    private_root = _private_dir(private_dir)
    record = _load_field_record(record_dir, private_root)
    _require_edit_token(record, edit_token)
    return field_photo_asset(photo_id, storage_dir, "original", private_dir=private_root)


def review_field_photo(
    photo_id: str,
    storage_dir: Path,
    *,
    status: Any = None,
    redactions: Any = None,
    vehicle_insurance_status: Any = None,
    vehicle_resolution_status: Any = None,
    vehicle_gallery_priority: Any = None,
    private_dir: Path | None = None,
) -> dict[str, Any]:
    with _FIELD_PHOTO_MUTATION_LOCK:
        record_dir = _record_dir_for(photo_id, storage_dir)
        private_root = _private_dir(private_dir)
        record = _load_field_record(record_dir, private_root)
        return _review_field_photo_record(
            record,
            record_dir,
            storage_dir,
            private_root,
            status=status,
            redactions=redactions,
            vehicle_insurance_status=vehicle_insurance_status,
            vehicle_resolution_status=vehicle_resolution_status,
            vehicle_gallery_priority=vehicle_gallery_priority,
        )


def review_field_photo_by_owner(
    photo_id: str,
    edit_token: Any,
    storage_dir: Path,
    *,
    redactions: Any,
    vehicle_insurance_status: Any = None,
    private_dir: Path | None = None,
) -> dict[str, Any]:
    with _FIELD_PHOTO_MUTATION_LOCK:
        record_dir = _record_dir_for(photo_id, storage_dir)
        private_root = _private_dir(private_dir)
        record = _load_field_record(record_dir, private_root)
        _require_edit_token(record, edit_token)
        validated_vehicle_insurance_status = _validated_vehicle_insurance_update(record, vehicle_insurance_status)
        status = "draft" if review_status(record) == "draft" else "pending"
        apply_review_update(
            record,
            record_dir,
            private_root,
            status=status,
            redactions=redactions,
            thumb_max_edge=config.FIELD_PHOTO_THUMBNAIL_MAX_EDGE_PX,
            thumb_quality=config.FIELD_PHOTO_THUMBNAIL_JPEG_QUALITY,
        )
        if validated_vehicle_insurance_status is not None:
            _set_vehicle_insurance(
                record,
                validated_vehicle_insurance_status,
                _vehicle_insurance_checked_at_for_status(validated_vehicle_insurance_status),
            )
        record["owner_redactions_updated_at"] = _now_iso()
        _save_field_record(storage_dir, record)
        return {"status": "ok", "photo": _summary(record)}


def submit_field_photos_by_owner(
    photo_ids: list[Any],
    edit_token: Any,
    storage_dir: Path,
    *,
    private_dir: Path | None = None,
) -> dict[str, Any]:
    normalize_photo_edit_token(edit_token)
    private_root = _private_dir(private_dir)
    requested_ids = validated_field_photo_ids(photo_ids, "Wskaż zdjęcie do wysłania.")

    photos: list[dict[str, Any]] = []
    with _FIELD_PHOTO_MUTATION_LOCK:
        records_to_save: list[dict[str, Any]] = []
        for photo_id in requested_ids:
            record_dir = _record_dir_for(photo_id, storage_dir)
            try:
                record = _load_field_record(record_dir, private_root)
            except FileNotFoundError:
                continue
            try:
                _require_edit_token(record, edit_token)
            except PermissionError:
                continue
            status = review_status(record)
            if status == "draft":
                record["public_review_status"] = "pending"
                record["submitted_at"] = _now_iso()
                record["reviewed_at"] = None
                remove_public_derivatives(record, record_dir)
                records_to_save.append(record)
                status = "pending"
            if status == "pending":
                photos.append(_summary(record))
        if records_to_save:
            _save_field_records(storage_dir, records_to_save)
    if not photos:
        raise PermissionError("Nieprawidłowy token edycji zdjęcia albo zdjęcie nie jest szkicem.")
    return {"status": "ok", "photos": sorted(photos, key=lambda item: str(item.get("created_at") or ""), reverse=True)}
