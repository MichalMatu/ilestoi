from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

REPORT_TIMEZONE = ZoneInfo("Europe/Warsaw")

REQUIRED_REPORT_FIELDS = {
    "reporter_name": "imię i nazwisko",
    "reporter_address": "adres zamieszkania",
    "reporter_phone": "telefon",
    "reporter_email": "adres e-mail",
    "location_description": "dokładne miejsce pojazdu",
    "observed_at": "data i godzina obserwacji",
    "vehicle_description": "opis stanu pojazdu",
}


def safe_text(value: Any, max_len: int = 4000) -> str:
    text = str(value or "").replace("\x00", "").strip()
    if len(text) > max_len:
        raise ValueError("Jedno z pól formularza jest zbyt długie.")
    return text


def validate_report_fields(raw_fields: dict[str, str]) -> dict[str, str]:
    fields = {key: safe_text(raw_fields.get(key)) for key in REQUIRED_REPORT_FIELDS}
    missing = [label for key, label in REQUIRED_REPORT_FIELDS.items() if not fields[key]]
    if missing:
        raise ValueError("Uzupełnij wymagane pola: " + ", ".join(missing) + ".")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", fields["reporter_email"]):
        raise ValueError("Podaj prawidłowy adres e-mail zgłaszającego.")
    for key in ("reporter_name", "reporter_address", "reporter_phone", "reporter_email"):
        if re.search(r"\bUZUPEŁNIJ\b", fields[key], re.IGNORECASE):
            raise ValueError("Uzupełnij dane zgłaszającego zamiast pozostawiać tekst zastępczy.")
    observed = fields["observed_at"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?", observed):
        raise ValueError("Podaj prawidłową datę i godzinę obserwacji.")
    try:
        observed_dt = datetime.fromisoformat(observed).replace(tzinfo=REPORT_TIMEZONE)
    except ValueError as exc:
        raise ValueError("Podaj prawidłową datę i godzinę obserwacji.") from exc
    if observed_dt > datetime.now(REPORT_TIMEZONE) + timedelta(minutes=5):
        raise ValueError("Data obserwacji nie może być z przyszłości.")
    return fields
