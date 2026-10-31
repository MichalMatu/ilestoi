from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from core import config
from core.cadastral import cadastral_code_label
from core.field_photo_metadata import vehicle_insurance_status_label

DANGLING_SUBJECT_WORDS = {"i", "o", "u", "w", "z", "do", "na", "od", "po"}
REPORT_TIMEZONE = ZoneInfo("Europe/Warsaw")
AUTO_LOCATION_MARKERS = (
    "miejsce wskazane na mapie przy współrzędnych gps",
    "location indicated on the map at gps coordinates",
)
AUTO_ADDRESS_PREFIXES = (
    "najbliższy adres:",
    "nearest address:",
)


def _first_line(value: str, max_len: int = 90) -> str:
    text = " ".join(value.split())
    if not text:
        return "lokalizacja"
    if len(text) <= max_len:
        return text
    suffix = "..."
    limit = max(max_len - len(suffix), 1)
    trimmed = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    if not trimmed:
        trimmed = text[:limit].rstrip(" ,.;:-")
    words = trimmed.rsplit(" ", 1)
    if len(words) == 2 and words[1].lower().strip(" ,.;:-") in DANGLING_SUBJECT_WORDS:
        trimmed = words[0].rstrip(" ,.;:-")
    return f"{trimmed}{suffix}" if trimmed else "lokalizacja"


def _labels_text(record: dict[str, Any], evidence: dict[str, Any]) -> str:
    labels = record.get("labels_present") or evidence.get("labels_present") or []
    return ", ".join(str(label) for label in labels) or "brak danych"


def _terrain_type(parcel: dict[str, Any]) -> str:
    return cadastral_code_label(parcel.get("land_use") or parcel.get("contour"))


def _parcel_short_note(parcel: dict[str, Any]) -> str:
    number = str(parcel.get("parcel_number") or "").strip()
    parcel_id = str(parcel.get("parcel_id") or "").strip()
    if number:
        return f" (działka {number})"
    if parcel_id:
        return f" (identyfikator działki {parcel_id})"
    return ""


def _parcel_context_text(record: dict[str, Any]) -> str:
    parcel = record.get("parcel") if isinstance(record.get("parcel"), dict) else {}
    if parcel:
        terrain_type = _terrain_type(parcel)
        if terrain_type:
            return f"Teren według ewidencji gruntów (pomocniczo): {terrain_type}{_parcel_short_note(parcel)}."
        return (
            f"Działka ewidencyjna (pomocniczo): brak automatycznie ustalonego typu użytku{_parcel_short_note(parcel)}."
        )
    parcel_error = str(record.get("parcel_error") or "").strip()
    if parcel_error:
        return (
            "Dane działki ewidencyjnej (pomocniczo): nie udało się automatycznie pobrać danych "
            f"działki ({parcel_error}); proszę o Państwa własną ocenę statusu miejsca."
        )
    return ""


def _address_context_text(record: dict[str, Any]) -> str:
    address = record.get("address") if isinstance(record.get("address"), dict) else {}
    formatted = str(address.get("formatted") or "").strip()
    if not formatted:
        return ""
    source_label = str(address.get("source_label") or address.get("source") or "").strip()
    source_clause = f" według {source_label}" if source_label else ""
    distance_text = str(address.get("distance_m") or "").strip()
    distance_clause = f" (ok. {distance_text} m od wskazanego punktu)" if distance_text else ""
    return f"Najbliższy adres{source_clause}: {formatted}{distance_clause}."


def _compact_lower(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _is_auto_map_location_description(value: Any) -> bool:
    text = _compact_lower(value)
    return any(marker in text for marker in AUTO_LOCATION_MARKERS)


def _is_auto_address_description(value: Any) -> bool:
    text = _compact_lower(value)
    return any(text.startswith(prefix) for prefix in AUTO_ADDRESS_PREFIXES)


def _location_section(record: dict[str, Any], fields: dict[str, str]) -> str:
    description = str(fields["location_description"] or "").strip()
    address_context = _address_context_text(record)
    if not address_context:
        return description
    if _is_auto_map_location_description(description):
        return address_context
    address = record.get("address") if isinstance(record.get("address"), dict) else {}
    formatted = _compact_lower(address.get("formatted"))
    if _is_auto_address_description(description):
        return address_context if formatted and formatted in _compact_lower(description) else description
    if formatted and formatted in _compact_lower(description):
        return description
    return f"{description}\n\n{address_context}" if description else address_context


def _subject_location(record: dict[str, Any], fields: dict[str, str]) -> str:
    address = record.get("address") if isinstance(record.get("address"), dict) else {}
    return str(address.get("formatted") or fields["location_description"])


def _field_datetime_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "brak danych"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(REPORT_TIMEZONE)
    return parsed.strftime("%d.%m.%Y, godz. %H:%M")


def _vehicle_insurance_context_text(record: dict[str, Any]) -> str:
    status = str(record.get("vehicle_insurance_status") or config.DEFAULT_FIELD_PHOTO_VEHICLE_INSURANCE_STATUS)
    if status == config.DEFAULT_FIELD_PHOTO_VEHICLE_INSURANCE_STATUS:
        return ""
    lines = [
        "Informacja pomocnicza o OC:",
        f"- Ręczne sprawdzenie w UFG: {vehicle_insurance_status_label(status)}",
    ]
    lines.append(f"- Data sprawdzenia w UFG: {_field_datetime_text(record.get('vehicle_insurance_checked_at'))}")
    lines.append("- Proszę potraktować tę informację pomocniczo i zweryfikować ją we własnym zakresie.")
    return "\n".join(lines)


def _optional_section(value: str) -> str:
    text = str(value or "").strip()
    return f"\n{text}\n" if text else ""


def build_mail_draft(record: dict[str, Any], evidence: dict[str, Any], fields: dict[str, str]) -> tuple[str, str]:
    lat = float(record.get("lat"))
    lon = float(record.get("lon"))
    labels = _labels_text(record, evidence)
    location_section = _location_section(record, fields)
    parcel_context = _parcel_context_text(record)
    parcel_section = _optional_section(parcel_context)
    insurance_section = _optional_section(_vehicle_insurance_context_text(record))
    subject = f"Zgłoszenie pojazdu nieużytkowanego - {_first_line(_subject_location(record, fields))}"
    body = f"""Zgłaszam pojazd, który według mojej obserwacji może spełniać przesłanki z art. 50a ust. 1 Prawa o ruchu drogowym.

Miejsce pojazdu:
{location_section}

Współrzędne GPS:
{lat:.6f}, {lon:.6f}

Data i godzina obserwacji:
{_field_datetime_text(fields["observed_at"])}

Opis stanu pojazdu:
{fields["vehicle_description"]}
{insurance_section}{parcel_section}
Załączniki:
- zdjęcia z miejsca,
- materiał pomocniczy z miniaturami historycznymi ortofoto z lat: {labels}.

Miniatury historyczne mogą wskazywać na długotrwałą obecność pojazdu w tym rejonie, ale nie zastępują oględzin w terenie.

Proszę o weryfikację przez patrol i podjęcie czynności przewidzianych prawem. Jeżeli miejsce nie należy do właściwości Straży Miejskiej, uprzejmie proszę o przekazanie zgłoszenia właściwej jednostce albo o wskazanie właściwego zarządcy/podmiotu.

Z poważaniem,
{fields["reporter_name"]}
Adres zamieszkania: {fields["reporter_address"]}
E-mail: {fields["reporter_email"]}
Telefon: {fields["reporter_phone"]}
"""
    return subject, body
