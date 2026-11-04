import json
from urllib.parse import urlsplit

from app import config
from app.http import responses as http_responses
from core.uploads import UploadedFile, parse_multipart_stream


class PayloadTooLargeError(ValueError):
    pass


def _media_type(handler) -> str:
    return str(handler.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()


def reject_wrong_content_type(handler, expected: str) -> bool:
    if _media_type(handler) == expected:
        return False
    http_responses.send_json(
        handler,
        415,
        {"error": f"Endpoint wymaga Content-Type: {expected}."},
    )
    return True


def _same_host_origin(handler, origin: str) -> bool:
    try:
        origin_parts = urlsplit(origin)
    except ValueError:
        return False
    request_host = str(handler.headers.get("Host") or "").strip().lower()
    return (
        origin_parts.scheme in {"http", "https"} and bool(request_host) and origin_parts.netloc.lower() == request_host
    )


def reject_unsafe_request(handler) -> bool:
    """Reject browser-initiated cross-site mutations before reading their body."""

    origin = str(handler.headers.get("Origin") or "").strip()
    fetch_site = str(handler.headers.get("Sec-Fetch-Site") or "").strip().lower()
    allowed_origins = {value.rstrip("/") for value in config.CORS_ALLOWED_ORIGINS}
    origin_allowed = not origin or origin.rstrip("/") in allowed_origins or _same_host_origin(handler, origin)
    if origin_allowed and fetch_site != "cross-site":
        return False
    http_responses.send_json(handler, 403, {"error": "Odrzucono żądanie z obcego źródła."})
    return True


def content_length(handler) -> int:
    raw_length = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise ValueError("Nieprawidłowy nagłówek Content-Length.") from exc
    if length < 0:
        raise ValueError("Nieprawidłowy nagłówek Content-Length.")
    return length


def reject_oversized_json_body(handler) -> bool:
    try:
        length = content_length(handler)
    except ValueError as exc:
        http_responses.send_json(handler, 400, {"error": str(exc)})
        return True
    if length <= config.MAX_JSON_BODY_BYTES:
        return False
    http_responses.send_json(
        handler,
        413,
        {
            "error": f"Payload JSON przekracza limit {config.MAX_JSON_BODY_BYTES} bajtów.",
            "limit_bytes": config.MAX_JSON_BODY_BYTES,
        },
    )
    return True


def dispatch_json_request(handler, route_handler, *args) -> None:
    if reject_wrong_content_type(handler, "application/json"):
        return
    if reject_oversized_json_body(handler):
        return
    route_handler(*args)


def read_json_body(handler) -> dict:
    length = content_length(handler)
    body = handler.rfile.read(length) if length else b""
    data = json.loads(body.decode("utf-8")) if body.strip() else {}
    if not isinstance(data, dict):
        raise ValueError("Payload musi być obiektem JSON.")
    return data


def read_multipart_form(handler, max_body_bytes: int) -> tuple[dict[str, str], list[UploadedFile]]:
    content_type = handler.headers.get("Content-Type", "")
    if _media_type(handler) != "multipart/form-data":
        raise ValueError("Formularz wymaga Content-Type: multipart/form-data.")
    length = content_length(handler)
    if length <= 0:
        raise ValueError("Brak danych formularza.")
    if length > max_body_bytes:
        raise PayloadTooLargeError("Formularz przekracza limit rozmiaru pakietu.")
    return parse_multipart_stream(content_type, handler.rfile, length, max_body_bytes=max_body_bytes)
