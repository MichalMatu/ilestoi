from __future__ import annotations

from typing import Any, Literal

from core.field_photo_metadata import (
    issue_type,
    vehicle_insurance_checked_at,
    vehicle_insurance_status,
    vehicle_resolution_status,
    vehicle_resolution_updated_at,
    vehicle_gallery_priority,
)
from core.photo_privacy import is_approved, review_status


def public_file_url(photo_id: str, asset: Literal["public-image", "public-thumb"]) -> str:
    return f"/api/field-photos/{photo_id}/{asset}"


def field_photo_summary(record: dict[str, Any]) -> dict[str, Any]:
    photo_id = str(record["id"])
    issue_type_text = issue_type(record.get("issue_type"))
    summary = {
        "id": photo_id,
        "created_at": record.get("created_at"),
        "submitted_at": record.get("submitted_at"),
        "format": record.get("format"),
        "public_width": record.get("public_width"),
        "public_height": record.get("public_height"),
        "public_review_status": review_status(record),
        "reviewed_at": record.get("reviewed_at"),
        "issue_type": issue_type_text,
        "vehicle_insurance_status": vehicle_insurance_status(
            issue_type_text,
            record.get("vehicle_insurance_status"),
        ),
        "vehicle_insurance_checked_at": vehicle_insurance_checked_at(
            issue_type_text,
            record.get("vehicle_insurance_status"),
            record.get("vehicle_insurance_checked_at"),
        ),
        "vehicle_gallery_priority": vehicle_gallery_priority(issue_type_text, record.get("vehicle_gallery_priority", 0)),
        "vehicle_resolution_status": vehicle_resolution_status(
            issue_type_text,
            record.get("vehicle_resolution_status"),
        ),
        "vehicle_resolution_updated_at": vehicle_resolution_updated_at(
            issue_type_text,
            record.get("vehicle_resolution_status"),
            record.get("vehicle_resolution_updated_at"),
        ),
        "lat": record.get("lat"),
        "lon": record.get("lon"),
        "coordinate_source": record.get("coordinate_source"),
        "position_updated_at": record.get("position_updated_at"),
        "captured_at": record.get("captured_at"),
        "links": record.get("links") or {},
    }
    if is_approved(record):
        summary["public_image"] = public_file_url(photo_id, "public-image")
        summary["public_thumb"] = public_file_url(photo_id, "public-thumb")
    return summary


def owner_review_item(record: dict[str, Any]) -> dict[str, Any]:
    item = review_item(record)
    item["original_image"] = f"/api/field-photos/{item['photo_id']}/owner-original"
    return item


def admin_review_item(record: dict[str, Any]) -> dict[str, Any]:
    item = review_item(record)
    item["original_image"] = f"/api/admin/photos/field/{item['photo_id']}/original"
    return item


def review_item(record: dict[str, Any]) -> dict[str, Any]:
    photo_id = str(record["id"])
    issue_type_text = issue_type(record.get("issue_type"))
    return {
        "scope": "field",
        "id": f"field:{photo_id}",
        "photo_id": photo_id,
        "created_at": record.get("created_at"),
        "original_filename": record.get("original_filename"),
        "issue_type": issue_type_text,
        "vehicle_insurance_status": vehicle_insurance_status(
            issue_type_text,
            record.get("vehicle_insurance_status"),
        ),
        "vehicle_insurance_checked_at": vehicle_insurance_checked_at(
            issue_type_text,
            record.get("vehicle_insurance_status"),
            record.get("vehicle_insurance_checked_at"),
        ),
        "vehicle_gallery_priority": vehicle_gallery_priority(issue_type_text, record.get("vehicle_gallery_priority", 0)),
        "vehicle_resolution_status": vehicle_resolution_status(
            issue_type_text,
            record.get("vehicle_resolution_status"),
        ),
        "vehicle_resolution_updated_at": vehicle_resolution_updated_at(
            issue_type_text,
            record.get("vehicle_resolution_status"),
            record.get("vehicle_resolution_updated_at"),
        ),
        "lat": record.get("lat"),
        "lon": record.get("lon"),
        "captured_at": record.get("captured_at"),
        "public_review_status": record.get("public_review_status"),
        "reviewed_at": record.get("reviewed_at"),
        "redactions": record.get("redactions") or [],
        "public_image": public_file_url(photo_id, "public-image") if is_approved(record) else None,
        "public_thumb": public_file_url(photo_id, "public-thumb") if is_approved(record) else None,
    }
