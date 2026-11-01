from __future__ import annotations

from typing import Any

from core import config


def issue_type(value: Any) -> str:
    issue_type_text = str(value or config.DEFAULT_FIELD_PHOTO_ISSUE_TYPE).strip()
    if issue_type_text not in config.FIELD_PHOTO_ISSUE_TYPES:
        raise ValueError("Nieprawidłowy typ pinezki terenowej.")
    return issue_type_text


def vehicle_insurance_status(issue_type_text: str, value: Any = None) -> str:
    status = str(value or config.DEFAULT_FIELD_PHOTO_VEHICLE_INSURANCE_STATUS).strip()
    if status not in config.FIELD_PHOTO_VEHICLE_INSURANCE_STATUSES:
        raise ValueError("Nieprawidłowy status OC pojazdu.")
    if issue_type_text != config.DEFAULT_FIELD_PHOTO_ISSUE_TYPE:
        if status != config.DEFAULT_FIELD_PHOTO_VEHICLE_INSURANCE_STATUS:
            raise ValueError("Status OC dotyczy tylko zdjęć pojazdu.")
        return config.DEFAULT_FIELD_PHOTO_VEHICLE_INSURANCE_STATUS
    return status


def vehicle_insurance_status_from_record(record: dict[str, Any]) -> str:
    return vehicle_insurance_status(issue_type(record.get("issue_type")), record.get("vehicle_insurance_status"))


def vehicle_resolution_status(issue_type_text: str, value: Any = None) -> str:
    status = str(value or config.DEFAULT_FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS).strip()
    if status not in config.FIELD_PHOTO_VEHICLE_RESOLUTION_STATUSES:
        raise ValueError("Nieprawidłowy status usunięcia pojazdu.")
    if issue_type_text != config.DEFAULT_FIELD_PHOTO_ISSUE_TYPE:
        if status != config.DEFAULT_FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS:
            raise ValueError("Status usunięcia dotyczy tylko zdjęć pojazdu.")
        return config.DEFAULT_FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS
    return status


def vehicle_resolution_status_from_record(record: dict[str, Any]) -> str:
    return vehicle_resolution_status(issue_type(record.get("issue_type")), record.get("vehicle_resolution_status"))


def vehicle_resolution_updated_at(issue_type_text: str, status: Any, value: Any = None) -> str | None:
    vehicle_resolution_status(issue_type_text, status)
    if issue_type_text != config.DEFAULT_FIELD_PHOTO_ISSUE_TYPE:
        return None
    text = str(value or "").strip()
    return text or None


def vehicle_resolution_updated_at_from_record(record: dict[str, Any]) -> str | None:
    return vehicle_resolution_updated_at(
        issue_type(record.get("issue_type")),
        record.get("vehicle_resolution_status"),
        record.get("vehicle_resolution_updated_at"),
    )


def vehicle_insurance_checked_at(issue_type_text: str, status: Any, value: Any = None) -> str | None:
    safe_status = vehicle_insurance_status(issue_type_text, status)
    if issue_type_text != config.DEFAULT_FIELD_PHOTO_ISSUE_TYPE:
        return None
    if safe_status == config.DEFAULT_FIELD_PHOTO_VEHICLE_INSURANCE_STATUS:
        return None
    text = str(value or "").strip()
    return text or None


def vehicle_insurance_checked_at_from_record(record: dict[str, Any]) -> str | None:
    return vehicle_insurance_checked_at(
        issue_type(record.get("issue_type")),
        record.get("vehicle_insurance_status"),
        record.get("vehicle_insurance_checked_at"),
    )


def grouped_vehicle_insurance_status(records: list[dict[str, Any]]) -> str:
    statuses: list[str] = []
    for record in records:
        try:
            statuses.append(vehicle_insurance_status_from_record(record))
        except ValueError:
            continue
    if "uninsured" in statuses:
        return "uninsured"
    if "insured" in statuses:
        return "insured"
    return config.DEFAULT_FIELD_PHOTO_VEHICLE_INSURANCE_STATUS


def grouped_vehicle_insurance_checked_at(records: list[dict[str, Any]]) -> str | None:
    grouped_status = grouped_vehicle_insurance_status(records)
    if grouped_status == config.DEFAULT_FIELD_PHOTO_VEHICLE_INSURANCE_STATUS:
        return None
    checked_at_values: list[str] = []
    for record in records:
        try:
            if vehicle_insurance_status_from_record(record) != grouped_status:
                continue
            checked_at = vehicle_insurance_checked_at_from_record(record)
        except ValueError:
            continue
        if checked_at:
            checked_at_values.append(checked_at)
    return max(checked_at_values) if checked_at_values else None


def vehicle_insurance_status_label(value: Any) -> str:
    status = vehicle_insurance_status(config.DEFAULT_FIELD_PHOTO_ISSUE_TYPE, value)
    return config.FIELD_PHOTO_VEHICLE_INSURANCE_STATUSES[status]


def validated_vehicle_insurance_update(record: dict[str, Any], value: Any) -> str | None:
    if value is None:
        return None
    return vehicle_insurance_status(issue_type(record.get("issue_type")), value)


def vehicle_gallery_priority(issue_type_text: str, value: Any = 0) -> int:
    if type(value) is not int or value not in (0, 1, 2, 3):
        raise ValueError("Nieprawidłowy priorytet galerii.")
    if issue_type_text != config.DEFAULT_FIELD_PHOTO_ISSUE_TYPE and value:
        raise ValueError("Galeria dotyczy tylko pojazdów.")
    return value


def vehicle_gallery_priority_from_record(record: dict[str, Any]) -> int:
    return vehicle_gallery_priority(issue_type(record.get("issue_type")), record.get("vehicle_gallery_priority", 0))


def validated_vehicle_gallery_priority_update(record: dict[str, Any], value: Any) -> int | None:
    if value is None:
        return None
    if str(record.get("public_review_status")) != "approved":
        raise ValueError("Wyróżniać można tylko zatwierdzone zdjęcia.")
    if vehicle_resolution_status_from_record(record) != "active":
        raise ValueError("Nie można wyróżniać usuniętego pojazdu.")
    return vehicle_gallery_priority(issue_type(record.get("issue_type")), value)


def validated_vehicle_resolution_update(record: dict[str, Any], value: Any) -> str | None:
    if value is None:
        return None
    return vehicle_resolution_status(issue_type(record.get("issue_type")), value)
