from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesFeedParser, BytesParser
from typing import BinaryIO


@dataclass(frozen=True)
class UploadedFile:
    field_name: str
    filename: str
    content_type: str
    data: bytes


def _form_parts(message) -> tuple[dict[str, str], list[UploadedFile]]:
    if not message.is_multipart():
        raise ValueError("Nieprawidłowy formularz multipart.")
    fields: dict[str, str] = {}
    files: list[UploadedFile] = []
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename is None:
            charset = part.get_content_charset() or "utf-8"
            fields[str(name)] = payload.decode(charset, errors="replace")
            continue
        files.append(
            UploadedFile(
                field_name=str(name),
                filename=str(filename),
                content_type=part.get_content_type(),
                data=payload,
            )
        )
    return fields, files


def _multipart_headers(content_type: str) -> bytes:
    if not content_type.lower().startswith("multipart/form-data"):
        raise ValueError("Payload musi być multipart/form-data.")
    return f"Content-Type: {content_type}\r\n\r\n".encode()


def parse_multipart_form(
    content_type: str,
    body: bytes,
    *,
    max_body_bytes: int | None = None,
) -> tuple[dict[str, str], list[UploadedFile]]:
    if not body:
        raise ValueError("Brak danych formularza.")
    if max_body_bytes is not None and len(body) > max_body_bytes:
        raise ValueError("Formularz przekracza limit rozmiaru pakietu.")
    message = BytesParser(policy=policy.default).parsebytes(_multipart_headers(content_type) + body)
    return _form_parts(message)


def parse_multipart_stream(
    content_type: str,
    stream: BinaryIO,
    content_length: int,
    *,
    max_body_bytes: int,
) -> tuple[dict[str, str], list[UploadedFile]]:
    """Incrementally feed a bounded HTTP body without first allocating its copy."""
    if content_length <= 0:
        raise ValueError("Brak danych formularza.")
    if content_length > max_body_bytes:
        raise ValueError("Formularz przekracza limit rozmiaru pakietu.")
    parser = BytesFeedParser(policy=policy.default)
    parser.feed(_multipart_headers(content_type))
    remaining = content_length
    while remaining:
        chunk = stream.read(min(64 * 1024, remaining))
        if not chunk:
            raise ValueError("Niekompletny formularz multipart.")
        remaining -= len(chunk)
        parser.feed(chunk)
    return _form_parts(parser.close())
