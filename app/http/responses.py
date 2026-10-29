import json
import logging
import secrets
from urllib.parse import urlsplit

from app import config

logger = logging.getLogger("wreckscanner.server")

_REQUEST_ID_SAFE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


def cors_response_headers(origin: str | None) -> dict[str, str]:
    origin_text = str(origin or "").strip()
    if not origin_text or origin_text not in config.CORS_ALLOWED_ORIGINS:
        return {}
    return {
        "Access-Control-Allow-Origin": origin_text,
        "Access-Control-Allow-Methods": "GET, HEAD, POST, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Request-ID",
        "Access-Control-Expose-Headers": "X-Request-ID",
        "Vary": "Origin",
    }


def security_response_headers() -> dict[str, str]:
    return {
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://unpkg.com; "
            "img-src 'self' data: blob: https://unpkg.com https://*.openstreetmap.org "
            "https://mapy.geoportal.gov.pl https://integracja.gugik.gov.pl "
            "https://integracja01.gugik.gov.pl; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'self'"
        ),
        "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Frame-Options": "SAMEORIGIN",
    }


def write_body(handler, body: bytes) -> bool:
    if getattr(handler, "_suppress_response_body", False):
        return True
    try:
        handler.wfile.write(body)
        return True
    except (BrokenPipeError, ConnectionResetError):
        return False


def request_id(handler) -> str:
    cached_request_id = getattr(handler, "_cached_request_id", None)
    if cached_request_id:
        return cached_request_id

    raw_request_id = str(handler.headers.get("X-Request-ID", "")).strip()
    safe_request_id = "".join(char for char in raw_request_id[:80] if char in _REQUEST_ID_SAFE_CHARS)
    if not safe_request_id:
        safe_request_id = secrets.token_hex(8)
    handler._cached_request_id = safe_request_id
    return safe_request_id


def log_exception(
    handler,
    message: str,
    exc: BaseException,
    *,
    status: int | None = None,
    level: int = logging.ERROR,
) -> None:
    request_path = urlsplit(getattr(handler, "path", "")).path
    client_address = getattr(handler, "client_address", ("-",))
    client_host = client_address[0] if client_address else "-"
    logger.log(
        level,
        "%s request_id=%s method=%s path=%s status=%s client=%s error=%s",
        message,
        request_id(handler),
        getattr(handler, "command", "-"),
        request_path,
        status if status is not None else "-",
        client_host,
        exc,
        exc_info=True,
    )


def send_json(
    handler,
    status: int,
    payload: dict,
    extra_headers: dict[str, str] | None = None,
    *,
    include_body: bool = True,
) -> None:
    current_request_id = request_id(handler)
    response_payload = payload
    if "error" in payload:
        response_payload = {
            **payload,
            "request_id": str(payload.get("request_id") or current_request_id),
        }
        current_request_id = response_payload["request_id"]
    body = json.dumps(response_payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Request-ID", current_request_id)
    for key, value in (extra_headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    if include_body:
        write_body(handler, body)


def send_internal_error(
    handler,
    status: int,
    log_message: str,
    exc: BaseException,
    *,
    public_error: str = "Wystąpił nieoczekiwany błąd serwera.",
    payload: dict | None = None,
    include_body: bool = True,
    level: int = logging.ERROR,
) -> None:
    log_exception(handler, log_message, exc, status=status, level=level)
    response_payload = {"status": "error", "error": public_error}
    if payload:
        response_payload.update(payload)
    send_json(handler, status, response_payload, include_body=include_body)


def send_text_error(handler, status: int, message: str, *, include_body: bool = True) -> None:
    body = f"{message}\n".encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Request-ID", request_id(handler))
    handler.end_headers()
    if include_body:
        write_body(handler, body)


def send_api_not_found(handler, *, include_body: bool = True) -> None:
    send_json(handler, 404, {"error": "Nie znaleziono endpointu."}, include_body=include_body)


def send_method_not_allowed(handler, *, include_body: bool = True) -> None:
    send_json(
        handler,
        405,
        {"error": "Metoda HTTP nie jest obsługiwana."},
        {"Allow": "GET, HEAD, POST, PATCH, DELETE, OPTIONS"},
        include_body=include_body,
    )
