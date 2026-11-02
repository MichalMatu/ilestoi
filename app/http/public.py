import json
from threading import BoundedSemaphore

from app import config as app_config
from app.http import access
from app.http import admin_session as http_admin_session
from app.http import request_body as http_request_body
from app.http import responses as http_responses
from app.http import static_files as http_static_files
from app.http.public_data import lookup_cadastral_parcel, lookup_nearest_address
from core import config as core_config
from core.field_photo_owner_actions import delete_field_photos_by_owner, discard_field_photo_drafts_by_owner
from core.field_photos import (
    field_photo_owner_original_asset,
    list_owner_field_photo_review_items,
    review_field_photo_by_owner,
    save_field_photo,
    submit_field_photos_by_owner,
)
from core.privacy_requests import create_privacy_request
from core.report_pdfs import create_field_photo_report_pdf, validate_field_photo_report_selection
from core.uploads import UploadedFile

OWNER_DELETABLE_REVIEW_STATUSES = {"draft", "pending"}
_REPORT_REQUEST_SEMAPHORE = BoundedSemaphore(app_config.REPORT_MAX_CONCURRENT_REQUESTS)


def reject_report_pdf_files(files: list[UploadedFile]) -> None:
    if any(file.filename or file.data for file in files):
        raise ValueError(
            "Raport można wygenerować tylko z zatwierdzonych zdjęć terenowych. "
            "Dodaj i zanonimizuj zdjęcia na mapie przed wygenerowaniem raportu."
        )


def _report_photo_ids(fields: dict[str, str]) -> list[str]:
    raw = fields.get("photo_ids") or ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in raw.split(",") if item.strip()]
    if not isinstance(parsed, list):
        raise ValueError("Nieprawidłowa lista zdjęć terenowych.")
    if len(parsed) > core_config.MAX_REPORT_PHOTOS:
        raise ValueError(f"Raport może zawierać maksymalnie {core_config.MAX_REPORT_PHOTOS} zdjęć.")
    photo_ids = [str(item or "").strip() for item in parsed if str(item or "").strip()]
    return photo_ids


def _report_cadastral_context(lat: str | None, lon: str | None) -> tuple[dict | None, str]:
    try:
        lat_float = float(lat or "")
        lon_float = float(lon or "")
    except ValueError:
        return None, ""
    try:
        return lookup_cadastral_parcel(lat_float, lon_float), ""
    except LookupError as exc:
        return None, str(exc)
    except Exception:
        return None, "Nie udało się automatycznie pobrać danych działki ewidencyjnej."


def _report_address_context(lat: str | None, lon: str | None) -> dict | None:
    try:
        lat_float = float(lat or "")
        lon_float = float(lon or "")
    except ValueError:
        return None
    try:
        return lookup_nearest_address(lat_float, lon_float)
    except Exception:
        return None


def _owner_photo_ids(data: dict, empty_message: str = "Wskaż zdjęcie.") -> list[str]:
    raw_photo_ids = data.get("photo_ids") if isinstance(data.get("photo_ids"), list) else []
    if len(raw_photo_ids) > core_config.MAX_OWNER_PHOTO_IDS:
        raise ValueError(f"Jedna operacja może objąć maksymalnie {core_config.MAX_OWNER_PHOTO_IDS} zdjęć.")
    photo_ids: list[str] = []
    for raw_photo_id in raw_photo_ids:
        photo_id = str(raw_photo_id or "").strip()
        if photo_id and photo_id not in photo_ids:
            photo_ids.append(photo_id)
    if not photo_ids:
        raise ValueError(empty_message)
    return photo_ids


def _delete_field_photos_by_owner(photo_ids: list[str], edit_token: object) -> dict:
    return delete_field_photos_by_owner(
        photo_ids,
        edit_token,
        core_config.FIELD_PHOTOS_DIR,
        private_dir=core_config.PRIVATE_PHOTOS_DIR,
        allowed_review_statuses=OWNER_DELETABLE_REVIEW_STATUSES,
    )


def handle_create_privacy_request(handler) -> None:
    try:
        data = http_request_body.read_json_body(handler)
        result = create_privacy_request(data)
        http_responses.send_json(handler, 200, result)
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Privacy request creation failed",
            exc,
            public_error="Nie udało się zapisać zgłoszenia prywatności.",
        )


def handle_claim_field_photos(handler) -> None:
    try:
        data = http_request_body.read_json_body(handler)
        photo_ids = _owner_photo_ids(data, "Wskaż zdjęcie do edycji.")
        photos = list_owner_field_photo_review_items(
            photo_ids,
            data.get("edit_token"),
            core_config.FIELD_PHOTOS_DIR,
            private_dir=core_config.PRIVATE_PHOTOS_DIR,
        )
        http_responses.send_json(handler, 200, {"status": "ok", "photos": photos})
    except PermissionError as e:
        http_responses.send_json(handler, 403, {"error": str(e)})
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Field photo owner claim failed",
            exc,
            public_error="Nie udało się odblokować edycji zdjęcia.",
        )


def handle_submit_field_photos(handler) -> None:
    try:
        data = http_request_body.read_json_body(handler)
        photo_ids = _owner_photo_ids(data, "Wskaż zdjęcie do wysłania.")
        result = submit_field_photos_by_owner(
            photo_ids,
            data.get("edit_token"),
            core_config.FIELD_PHOTOS_DIR,
            private_dir=core_config.PRIVATE_PHOTOS_DIR,
        )
        http_responses.send_json(handler, 200, result)
    except PermissionError as e:
        http_responses.send_json(handler, 403, {"error": str(e)})
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Field photo owner submit failed",
            exc,
            public_error="Nie udało się wysłać zdjęć do weryfikacji.",
        )


def handle_discard_field_photo_drafts(handler) -> None:
    try:
        data = http_request_body.read_json_body(handler)
        photo_ids = _owner_photo_ids(data, "Wskaż zdjęcie do porzucenia.")
        result = discard_field_photo_drafts_by_owner(
            photo_ids,
            data.get("edit_token"),
            core_config.FIELD_PHOTOS_DIR,
            private_dir=core_config.PRIVATE_PHOTOS_DIR,
        )
        http_responses.send_json(handler, 200, result)
    except PermissionError as e:
        http_responses.send_json(handler, 403, {"error": str(e)})
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Field photo draft discard failed",
            exc,
            public_error="Nie udało się porzucić szkicu zdjęć.",
        )


def handle_delete_field_photos_by_owner(handler) -> None:
    try:
        data = http_request_body.read_json_body(handler)
        result = _delete_field_photos_by_owner(
            _owner_photo_ids(data, "Wskaż zdjęcie do usunięcia."), data.get("edit_token")
        )
        http_responses.send_json(handler, 200, result)
    except PermissionError as e:
        http_responses.send_json(handler, 403, {"error": str(e)})
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Field photo owner delete failed",
            exc,
            public_error="Nie udało się usunąć zdjęć.",
        )


def _ai_report_fields(handler) -> dict[str, str]:
    """Accept a small, explicit JSON contract; never accept uploaded/private photos."""
    data = http_request_body.read_json_body(handler)
    allowed = {
        "photo_ids",
        "lat",
        "lon",
        "reporter_name",
        "reporter_email",
        "reporter_phone",
        "reporter_address",
        "location_description",
        "observed_at",
        "vehicle_description",
        "crop_m",
    }
    if set(data) - allowed:
        raise ValueError("Nieznane pola formularza zgłoszenia.")
    if not isinstance(data.get("photo_ids"), list):
        raise ValueError("photo_ids musi być tablicą identyfikatorów zdjęć.")
    if any(not isinstance(item, str) for item in data["photo_ids"]):
        raise ValueError("Identyfikatory zdjęć muszą być tekstem.")
    fields = {"photo_ids": json.dumps(data["photo_ids"])}
    for key in allowed - {"photo_ids"}:
        value = data.get(key)
        if value is not None:
            if key in {"lat", "lon", "crop_m"} and type(value) in {int, float}:
                fields[key] = str(value)
            elif isinstance(value, str):
                fields[key] = value
            else:
                raise ValueError(f"Nieprawidłowy typ pola {key}.")
    return fields


def _handle_report_pdf(handler, *, json_input: bool) -> None:
    if not access.require_public_feature(
        handler, "report_pdfs", "Generowanie raportów przez niezalogowanych jest teraz wyłączone."
    ):
        return
    request_slot_acquired = False
    try:
        if json_input:
            fields = _ai_report_fields(handler)
        else:
            fields, files = http_request_body.read_multipart_form(handler, core_config.MAX_REPORT_PDF_BODY_BYTES)
            reject_report_pdf_files(files)
        if not _REPORT_REQUEST_SEMAPHORE.acquire(blocking=False):
            http_responses.send_json(
                handler,
                503,
                {"error": "Generator raportów jest zajęty. Spróbuj ponownie za chwilę."},
                {"Retry-After": "5"},
            )
            return
        request_slot_acquired = True
        photo_ids = _report_photo_ids(fields)
        validate_field_photo_report_selection(
            photo_ids,
            lat=fields.get("lat"),
            lon=fields.get("lon"),
            field_photos_dir=core_config.FIELD_PHOTOS_DIR,
        )
        parcel, parcel_error = _report_cadastral_context(fields.get("lat"), fields.get("lon"))
        address = _report_address_context(fields.get("lat"), fields.get("lon"))
        result = create_field_photo_report_pdf(
            fields,
            photo_ids,
            lat=fields.get("lat"),
            lon=fields.get("lon"),
            parcel=parcel,
            parcel_error=parcel_error,
            address=address,
            field_photos_dir=core_config.FIELD_PHOTOS_DIR,
        )
        http_responses.send_json(handler, 200, result)
    except http_request_body.PayloadTooLargeError as e:
        http_responses.send_json(handler, 413, {"error": str(e)})
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except (ValueError, TypeError) as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Field photo report PDF creation failed",
            exc,
            public_error="Nie udało się przygotować raportu ze zdjęć terenowych.",
        )
    finally:
        if request_slot_acquired:
            _REPORT_REQUEST_SEMAPHORE.release()


def handle_field_photo_report_pdf(handler) -> None:
    _handle_report_pdf(handler, json_input=False)


def handle_ai_report_pdf(handler) -> None:
    _handle_report_pdf(handler, json_input=True)


def handle_create_field_photo(handler) -> None:
    if not access.require_public_feature(
        handler, "photo_uploads", "Dodawanie zdjec przez niezalogowanych jest teraz wylaczone."
    ):
        return
    try:
        fields, files = http_request_body.read_multipart_form(handler, core_config.FIELD_PHOTO_MAX_BODY_BYTES)
        photo_files = [file for file in files if file.field_name == "photo"]
        if len(photo_files) != 1:
            raise ValueError("Dodaj dokładnie jedno zdjęcie w polu 'photo'.")
        is_admin = http_admin_session.is_admin(handler)
        issue_type = fields.get("issue_type")
        if not is_admin and not access.require_public_layer(
            handler,
            access.field_photo_issue_layer_key(issue_type),
            "Ta kategoria zdjec terenowych jest teraz wylaczona dla niezalogowanych.",
        ):
            return
        edit_token = fields.get("edit_token")
        if not is_admin and not str(edit_token or "").strip():
            raise ValueError("Nie udało się przygotować tokenu edycji zdjęcia. Spróbuj ponownie.")
        if not is_admin:
            access.ensure_public_submission_quota(
                handler,
                additional_bytes=len(photo_files[0].data),
                additional_items=1,
            )
        result = save_field_photo(
            photo_files[0],
            core_config.FIELD_PHOTOS_DIR,
            map_lat=fields.get("map_lat"),
            map_lon=fields.get("map_lon"),
            issue_type=issue_type,
            vehicle_insurance_status=fields.get("vehicle_insurance_status"),
            private_dir=core_config.PRIVATE_PHOTOS_DIR,
            submission_owner=None if is_admin else access.submission_owner(handler),
            edit_token=None if is_admin else edit_token,
            public_review_status="pending" if is_admin else "draft",
        )
        http_responses.send_json(handler, 200, result)
    except http_request_body.PayloadTooLargeError as e:
        http_responses.send_json(handler, 413, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Field photo upload failed",
            exc,
            public_error="Nie udało się zapisać zdjęcia terenowego.",
        )


def handle_field_photo_owner_original(handler, photo_id: str) -> None:
    try:
        data = http_request_body.read_json_body(handler)
        file_path, content_type = field_photo_owner_original_asset(
            photo_id,
            data.get("edit_token"),
            core_config.FIELD_PHOTOS_DIR,
            private_dir=core_config.PRIVATE_PHOTOS_DIR,
        )
        http_static_files.send_file(handler, file_path, content_type)
    except PermissionError as e:
        http_responses.send_json(handler, 403, {"error": str(e)})
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Field photo owner original lookup failed",
            exc,
            public_error="Nie udało się pobrać oryginału zdjęcia.",
        )


def handle_owner_review_field_photo(handler, photo_id: str) -> None:
    try:
        data = http_request_body.read_json_body(handler)
        result = review_field_photo_by_owner(
            photo_id,
            data.get("edit_token"),
            core_config.FIELD_PHOTOS_DIR,
            redactions=data.get("redactions") or [],
            vehicle_insurance_status=data.get("vehicle_insurance_status"),
            private_dir=core_config.PRIVATE_PHOTOS_DIR,
        )
        http_responses.send_json(handler, 200, result)
    except PermissionError as e:
        http_responses.send_json(handler, 403, {"error": str(e)})
    except FileNotFoundError as e:
        http_responses.send_json(handler, 404, {"error": str(e)})
    except ValueError as e:
        http_responses.send_json(handler, 400, {"error": str(e)})
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            500,
            "Field photo owner review update failed",
            exc,
            public_error="Nie udało się zapisać anonimizacji zdjęcia.",
        )
