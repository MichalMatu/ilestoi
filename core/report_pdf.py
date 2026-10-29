from __future__ import annotations

import html
import io
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as ReportImage
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core import config
from core.photo_privacy import is_approved

PAGE_BG = colors.white
CARD_BG = colors.white
CARD_BORDER = colors.HexColor("#cbd5e1")
TEXT = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#475569")
LINK = colors.HexColor("#2563eb")
URL_RE = re.compile(r"https?://[^\s<]+")

PAGE_MARGIN = 14 * mm
GAP = 6 * mm
PHOTO_COLUMNS = 2
CROP_COLUMNS = 3
PHOTO_HEIGHT = 48 * mm
CROP_HEIGHT = 40 * mm

FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"


@dataclass(frozen=True)
class PdfPhoto:
    label: str
    data: bytes


def _font_path(*, bold: bool = False) -> Path | None:
    names = ("DejaVuSans-Bold.ttf", "Arial Bold.ttf") if bold else ("DejaVuSans.ttf", "Arial.ttf")
    prefix = os.environ.get("PREFIX")
    roots = (
        *((Path(prefix) / "share/fonts/TTF",) if prefix else ()),
        Path("/data/data/com.termux/files/usr/share/fonts/TTF"),
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/msttcorefonts"),
        Path("/Library/Fonts"),
        Path("C:/Windows/Fonts"),
    )
    for root in roots:
        for name in names:
            path = root / name
            if path.is_file():
                return path
    return None


def _register_fonts() -> None:
    registered = set(pdfmetrics.getRegisteredFontNames())
    if FONT_REGULAR not in registered or FONT_BOLD not in registered:
        regular = _font_path()
        bold = _font_path(bold=True)
        if not regular or not bold:
            raise RuntimeError("Brak czcionek TrueType z polskimi znakami do wygenerowania PDF.")
        if FONT_REGULAR not in registered:
            pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular)))
        if FONT_BOLD not in registered:
            pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold)))
    # Inline <b> must use the embedded TrueType bold font too, not Helvetica.
    pdfmetrics.registerFontFamily(FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD)


def _font_name(*, bold: bool = False) -> str:
    _register_fonts()
    return FONT_BOLD if bold else FONT_REGULAR


def _styles() -> dict[str, ParagraphStyle]:
    regular = _font_name()
    bold = _font_name(bold=True)
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            fontName=bold,
            fontSize=16,
            leading=20,
            textColor=TEXT,
            spaceAfter=6,
            alignment=TA_CENTER,
        ),
        "right": ParagraphStyle(
            "ReportRight",
            fontName=regular,
            fontSize=9,
            leading=11.2,
            textColor=TEXT,
            spaceAfter=6,
            alignment=TA_RIGHT,
        ),
        "heading": ParagraphStyle(
            "ReportHeading",
            fontName=bold,
            fontSize=15,
            leading=18,
            textColor=TEXT,
            spaceBefore=4,
            spaceAfter=6,
            keepWithNext=1,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            fontName=regular,
            fontSize=9,
            leading=11.2,
            textColor=TEXT,
            spaceAfter=6,
            allowWidows=0,
            allowOrphans=0,
        ),
        "muted": ParagraphStyle(
            "ReportMuted",
            fontName=regular,
            fontSize=8.8,
            leading=11,
            textColor=MUTED,
            spaceAfter=6,
        ),
        "caption": ParagraphStyle(
            "ReportCaption",
            fontName=regular,
            fontSize=8,
            leading=10,
            textColor=MUTED,
            spaceBefore=4,
        ),
    }


def _safe_child(base_dir: Path, relative_path: str) -> Path:
    root = base_dir.resolve()
    path = (base_dir / relative_path).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Nieprawidłowa ścieżka w sprawie pojazdu.")
    return path


def _compact_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "brak danych"
    return text.replace("T", " ").removesuffix("Z")


def _report_datetime_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "brak danych"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _compact_datetime(text)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%d.%m.%Y, godz. %H:%M")


def _report_date_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "brak daty"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _compact_datetime(text)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.strftime("%d.%m.%Y r.")


def _recipient_lines(recipient: str) -> list[str]:
    if recipient == config.REPORT_RECIPIENT:
        return [
            "Straż Miejska Wrocławia",
            "ul. Na Grobli 14/16, 50-421 Wrocław",
            recipient,
        ]
    return [recipient]


def _reporter_lines(reporter: dict[str, Any]) -> list[str]:
    return [
        str(reporter.get("reporter_name") or "").strip(),
        str(reporter.get("reporter_address") or "").strip(),
        str(reporter.get("reporter_email") or "").strip(),
        str(reporter.get("reporter_phone") or "").strip(),
    ]


def _escape_text(value: Any) -> str:
    return html.escape(str(value or ""), quote=False)


def _url_label(raw_url: str) -> str:
    if "photo=" in raw_url and ("lat=" in raw_url or "lon=" in raw_url):
        return "Otwórz miejsce w IleStoi.pl"
    return raw_url


def _paragraph_text(value: str) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    parts: list[str] = []
    last = 0
    for match in URL_RE.finditer(text):
        raw_url = match.group(0)
        parts.append(_escape_text(text[last : match.start()]))
        escaped_href = html.escape(raw_url, quote=True)
        escaped_label = _escape_text(_url_label(raw_url))
        parts.append(f'<a href="{escaped_href}" color="{LINK.hexval()}">{escaped_label}</a>')
        last = match.end()
    parts.append(_escape_text(text[last:]))
    return "".join(parts).replace("\n", "<br/>")


def _mail_body_flowables(mail_body: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    normalized = str(mail_body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = [block.strip() for block in normalized.split("\n\n") if block.strip()]
    if not blocks:
        return []

    paragraphs = [Paragraph(_paragraph_text(block), styles["body"]) for block in blocks]
    if len(paragraphs) >= 2:
        return [*paragraphs[:-2], KeepTogether(paragraphs[-2:])]
    return paragraphs


def _lines_paragraph(lines: list[str]) -> str:
    escaped = []
    for line in lines:
        text = str(line or "").strip()
        if not text:
            continue
        escaped_text = _escape_text(text)
        if "@" in text and " " not in text:
            escaped_mail = html.escape(text, quote=True)
            escaped_text = f'<a href="mailto:{escaped_mail}" color="{LINK.hexval()}">{escaped_text}</a>'
        escaped.append(escaped_text)
    return "<br/>".join(escaped)


def _office_header(
    *,
    recipient: str,
    reporter: dict[str, Any],
    created_at: Any,
    styles: dict[str, ParagraphStyle],
    content_width: float,
) -> list[Any]:
    left = Paragraph(f"<b>Adresat</b><br/>{_lines_paragraph(_recipient_lines(recipient))}", styles["body"])
    right = Paragraph(f"<b>Zgłaszający</b><br/>{_lines_paragraph(_reporter_lines(reporter))}", styles["body"])
    table = Table(
        [[left, right]],
        colWidths=[(content_width - GAP) / 2, (content_width - GAP) / 2],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )
    return [
        Paragraph(f"Wrocław, dnia {_report_date_text(created_at)}", styles["right"]),
        Spacer(1, 5 * mm),
        table,
        Spacer(1, 10 * mm),
    ]


def _page_background(canvas, _doc) -> None:
    canvas.saveState()
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.restoreState()


def _photo_bytes_from_record(record_dir: Path, photo: dict[str, Any]) -> PdfPhoto | None:
    if not is_approved(photo):
        return None
    public_rel = str(photo.get("public_image_file") or "")
    thumb_rel = str(photo.get("public_thumb_file") or "")
    rel = public_rel or thumb_rel
    if not rel:
        return None
    path = _safe_child(record_dir, rel)
    if not path.exists():
        return None
    label = str(photo.get("original_filename") or photo.get("id") or "zdjęcie z miejsca")
    return PdfPhoto(label=label, data=path.read_bytes())


def _attached_photos(record: dict[str, Any], record_dir: Path) -> list[PdfPhoto]:
    photos = record.get("attached_photos") if isinstance(record.get("attached_photos"), list) else []
    prepared = []
    for photo in photos:
        if isinstance(photo, dict):
            pdf_photo = _photo_bytes_from_record(record_dir, photo)
            if pdf_photo:
                prepared.append(pdf_photo)
    return prepared


def _evidence_photos(evidence: dict[str, Any], evidence_base_dir: Path) -> list[PdfPhoto]:
    evidence_rel = str(evidence.get("path") or "")
    evidence_dir = _safe_child(evidence_base_dir, evidence_rel)
    prepared = []
    for crop in evidence.get("crops") or []:
        if not isinstance(crop, dict):
            continue
        rel = str(crop.get("file") or "")
        if not rel:
            continue
        path = _safe_child(evidence_dir, rel)
        if path.exists():
            prepared.append(PdfPhoto(label=str(crop.get("label") or path.stem), data=path.read_bytes()))
    return prepared


def _prepare_image(data: bytes, *, max_edge: int = 1400) -> tuple[bytes, int, int] | None:
    try:
        with Image.open(io.BytesIO(data)) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.save(out, "JPEG", quality=86, optimize=True)
            return out.getvalue(), image.width, image.height
    except (OSError, UnidentifiedImageError):
        return None


def _image_flowable(photo: PdfPhoto, width: float, height: float) -> ReportImage | Paragraph:
    prepared = _prepare_image(photo.data)
    if not prepared:
        return Paragraph("Nie można odczytać zdjęcia.", _styles()["caption"])
    data, image_width, image_height = prepared
    scale = min(width / max(image_width, 1), height / max(image_height, 1))
    draw_width = image_width * scale
    draw_height = image_height * scale
    image = ReportImage(io.BytesIO(data), width=draw_width, height=draw_height)
    image.hAlign = "CENTER"
    return image


def _photo_card(photo: PdfPhoto, width: float, image_height: float, styles: dict[str, ParagraphStyle]) -> Table:
    image = _image_flowable(photo, width - 8 * mm, image_height)
    caption = Paragraph(_paragraph_text(photo.label or "zdjęcie"), styles["caption"])
    card = Table(
        [[image], [caption]],
        colWidths=[width],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
                ("BOX", (0, 0), (-1, -1), 0.5, CARD_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
            ]
        ),
    )
    card.keepTogether = True
    return card


def _image_grid(
    photos: list[PdfPhoto],
    *,
    columns: int,
    image_height: float,
    styles: dict[str, ParagraphStyle],
    content_width: float,
) -> Table | None:
    if not photos:
        return None
    cell_width = (content_width - (GAP * (columns - 1))) / columns
    rows = []
    for start in range(0, len(photos), columns):
        row_photos = photos[start : start + columns]
        row = [_photo_card(photo, cell_width, image_height, styles) for photo in row_photos]
        while len(row) < columns:
            row.append("")
        rows.append(row)
    table = Table(
        rows,
        colWidths=[cell_width] * columns,
        hAlign="LEFT",
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), GAP),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), GAP),
            ]
        ),
    )
    return table


def _evidence_section(
    title: str,
    photos: list[PdfPhoto],
    *,
    columns: int,
    image_height: float,
    styles: dict[str, ParagraphStyle],
    content_width: float,
) -> list[Any]:
    grid = _image_grid(
        photos,
        columns=columns,
        image_height=image_height,
        styles=styles,
        content_width=content_width,
    )
    if not grid:
        return []
    return [Paragraph(_escape_text(title), styles["heading"]), grid, Spacer(1, 4 * mm)]


def build_report_pdf(
    *,
    record: dict[str, Any],
    evidence: dict[str, Any],
    record_dir: Path,
    evidence_base_dir: Path,
    recipient: str,
    reporter: dict[str, Any],
    subject: str,
    mail_body: str,
) -> bytes:
    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        pageCompression=0,
        title=subject,
        author="IleStoi.pl",
    )
    styles = _styles()
    content_width = A4[0] - (PAGE_MARGIN * 2)
    attached_photos = _attached_photos(record, record_dir)
    evidence_images = _evidence_photos(evidence, evidence_base_dir)

    story: list[Any] = [
        *_office_header(
            recipient=recipient,
            reporter=reporter,
            created_at=evidence.get("created_at"),
            styles=styles,
            content_width=content_width,
        ),
        Paragraph("Zgłoszenie dotyczące pojazdu nieużytkowanego", styles["title"]),
        Spacer(1, 4 * mm),
        *_mail_body_flowables(mail_body, styles),
    ]

    evidence_story = []
    evidence_story.extend(
        _evidence_section(
            "Zdjęcia z miejsca",
            attached_photos,
            columns=PHOTO_COLUMNS,
            image_height=PHOTO_HEIGHT,
            styles=styles,
            content_width=content_width,
        )
    )
    evidence_story.extend(
        _evidence_section(
            "Miniatury historyczne",
            evidence_images,
            columns=CROP_COLUMNS,
            image_height=CROP_HEIGHT,
            styles=styles,
            content_width=content_width,
        )
    )
    if evidence_story:
        story.append(Spacer(1, 4 * mm))
        story.extend(evidence_story)

    doc.build(story, onFirstPage=_page_background, onLaterPages=_page_background)
    return out.getvalue()
