import json
import re
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from app import config
from app.http import responses as http_responses
from core.settings_store import default_app_settings, load_app_settings

HTML_PAGE_PATHS = {"/", "/index.html", "/privacy", "/report"}
HTML_INCLUDE_RE = re.compile(r"^[ \t]*<!--\s*include:([A-Za-z0-9_./-]+)\s*-->\s*$", re.MULTILINE)
APP_SETTINGS_BOOTSTRAP_TOKEN = "<!-- app-settings-bootstrap -->"
PAGE_HEAD_METADATA_TOKEN = "<!-- page-head-metadata -->"
PAGE_STRUCTURED_DATA_TOKEN = "<!-- page-structured-data -->"
PAGE_TITLE_KEY_TOKEN = "{{PAGE_TITLE_KEY}}"
PAGE_DESCRIPTION_KEY_TOKEN = "{{PAGE_DESCRIPTION_KEY}}"
HOME_DESCRIPTION = (
    "Mapa zgłoszeń pojazdów długo stojących lub nieużytkowanych. Zobacz lokalizacje i dokumentację "
    "zdjęciową albo dodaj obserwację do weryfikacji."
)
PAGE_METADATA = {
    "/": {
        "title": "IleStoi.pl – mapa pojazdów długo stojących",
        "description": HOME_DESCRIPTION,
        "canonical_path": "/",
        "robots": "index,follow,max-snippet:-1,max-image-preview:large,max-video-preview:-1",
        "title_key": "meta.title",
        "description_key": "meta.description",
    },
    "/privacy": {
        "title": "Prywatność – IleStoi.pl",
        "description": "Informacje o przetwarzaniu zdjęć, anonimizacji, retencji i zgłoszeniach korekty.",
        "canonical_path": "/privacy",
        "robots": "noindex,follow",
        "title_key": "page.privacy.title",
        "description_key": "page.privacy.description",
    },
    "/report": {
        "title": "Zgłoś problem – IleStoi.pl",
        "description": "Formularz żądania usunięcia, anonimizacji albo korekty publicznego wpisu lub zdjęcia.",
        "canonical_path": "/report",
        "robots": "noindex,follow",
        "title_key": "page.report.title",
        "description_key": "page.report.description",
    },
}
PAGE_METADATA["/index.html"] = PAGE_METADATA["/"]
WEB_ASSET_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".webp": "image/webp",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".woff2": "font/woff2",
    ".xml": "application/xml; charset=utf-8",
}


def app_settings_bootstrap_json() -> str:
    try:
        settings = load_app_settings()
    except Exception:
        settings = default_app_settings()
    return json.dumps(
        {"map_view": settings.get("map_view")},
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")


def page_head_metadata(page_path: str) -> str:
    metadata = PAGE_METADATA[page_path]
    title = escape(metadata["title"], quote=True)
    description = escape(metadata["description"], quote=True)
    canonical_url = f"{config.CANONICAL_PUBLIC_ORIGIN}{metadata['canonical_path']}"
    robots = escape(metadata["robots"], quote=True)
    return "\n    ".join(
        (
            f"<title>{title}</title>",
            f'<meta name="description" content="{description}">',
            f'<meta name="robots" content="{robots}">',
            f'<link rel="canonical" href="{canonical_url}">',
            '<meta property="og:type" content="website">',
            '<meta property="og:locale" content="pl_PL">',
            '<meta property="og:locale:alternate" content="en_US">',
            '<meta property="og:site_name" content="IleStoi.pl">',
            f'<meta property="og:title" content="{title}">',
            f'<meta property="og:description" content="{description}">',
            f'<meta property="og:url" content="{canonical_url}">',
            '<meta name="twitter:card" content="summary">',
            f'<meta name="twitter:title" content="{title}">',
            f'<meta name="twitter:description" content="{description}">',
        )
    )


def page_structured_data(page_path: str) -> str:
    if page_path not in {"/", "/index.html"}:
        return ""
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{config.CANONICAL_PUBLIC_ORIGIN}/#website",
                "url": f"{config.CANONICAL_PUBLIC_ORIGIN}/",
                "name": "IleStoi.pl",
                "alternateName": "Ile Stoi",
                "description": HOME_DESCRIPTION,
                "inLanguage": "pl-PL",
            },
            {
                "@type": "WebApplication",
                "@id": f"{config.CANONICAL_PUBLIC_ORIGIN}/#application",
                "url": f"{config.CANONICAL_PUBLIC_ORIGIN}/",
                "name": "IleStoi.pl",
                "description": HOME_DESCRIPTION,
                "applicationCategory": "UtilitiesApplication",
                "operatingSystem": "Any",
                "isAccessibleForFree": True,
                "inLanguage": ["pl-PL", "en"],
            },
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/ld+json">{encoded}</script>'


def send_file(
    handler,
    path: Path,
    content_type: str,
    *,
    cache_control: str = "no-store",
    include_body: bool = True,
    download_name: str | None = None,
) -> None:
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise FileNotFoundError("Nie znaleziono pliku.") from exc
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", cache_control)
    if download_name:
        safe_name = Path(str(download_name).replace("\\", "/")).name.replace('"', "")
        encoded_name = quote(safe_name)
        handler.send_header(
            "Content-Disposition", f"attachment; filename=\"{safe_name}\"; filename*=UTF-8''{encoded_name}"
        )
    handler.end_headers()
    if include_body:
        http_responses.write_body(handler, body)


def send_bytes(
    handler,
    body: bytes,
    content_type: str,
    *,
    cache_control: str = "no-store",
    include_body: bool = True,
) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", cache_control)
    handler.end_headers()
    if include_body:
        http_responses.write_body(handler, body)


def send_web_file(handler, file_name: str, *, include_body: bool = True) -> None:
    path = config.WEB_DIR / file_name
    send_file(handler, path, "text/html; charset=utf-8", include_body=include_body)


def safe_web_relative_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise FileNotFoundError("Nieprawidłowa ścieżka partiala HTML.")
    return path


def render_web_template(
    file_name: str,
    *,
    page_path: str = "/",
    _seen: frozenset[str] = frozenset(),
) -> str:
    relative_path = safe_web_relative_path(file_name)
    key = relative_path.as_posix()
    if key in _seen:
        raise FileNotFoundError("Wykryto cykliczny include HTML.")
    path = config.WEB_DIR / relative_path
    try:
        template = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError("Nie znaleziono pliku HTML.") from exc

    def replace_include(match: re.Match[str]) -> str:
        include_path = safe_web_relative_path(match.group(1)).as_posix()
        return render_web_template(include_path, page_path=page_path, _seen=_seen | {key})

    rendered = HTML_INCLUDE_RE.sub(replace_include, template)
    if APP_SETTINGS_BOOTSTRAP_TOKEN in rendered:
        rendered = rendered.replace(
            APP_SETTINGS_BOOTSTRAP_TOKEN,
            f"<script>window.WRECKSCANNER_APP_SETTINGS={app_settings_bootstrap_json()};</script>",
        )
    resolved_page_path = page_path if page_path in PAGE_METADATA else "/"
    metadata = PAGE_METADATA[resolved_page_path]
    return (
        rendered.replace(PAGE_HEAD_METADATA_TOKEN, page_head_metadata(resolved_page_path))
        .replace(PAGE_STRUCTURED_DATA_TOKEN, page_structured_data(resolved_page_path))
        .replace(PAGE_TITLE_KEY_TOKEN, metadata["title_key"])
        .replace(PAGE_DESCRIPTION_KEY_TOKEN, metadata["description_key"])
    )


def send_web_page(
    handler,
    file_name: str = "index.html",
    *,
    page_path: str = "/",
    include_body: bool = True,
) -> None:
    body = render_web_template(file_name, page_path=page_path).encode("utf-8")
    send_bytes(handler, body, "text/html; charset=utf-8", include_body=include_body)


def translate_path(path: str) -> str:
    request_path = unquote(urlsplit(path).path)
    if request_path == "/":
        return str(config.WEB_DIR / "index.html")

    base_dir = config.WEB_DIR
    relative_path = request_path.lstrip("/")
    parts = [part for part in relative_path.split("/") if part and part not in {".", ".."}]
    return str(base_dir.joinpath(*parts))


def handle_web_page(handler, path: str, *, include_body: bool = True) -> bool:
    if path in HTML_PAGE_PATHS:
        send_web_page(handler, "index.html", page_path=path, include_body=include_body)
        return True
    return False


def handle_web_asset(handler, path: str, *, include_body: bool = True) -> bool:
    if path in HTML_PAGE_PATHS:
        return False
    relative_path = unquote(urlsplit(path).path).lstrip("/")
    try:
        relative = safe_web_relative_path(relative_path)
    except FileNotFoundError:
        return False
    content_type = WEB_ASSET_CONTENT_TYPES.get(relative.suffix.lower())
    if not content_type:
        return False
    asset_path = config.WEB_DIR / relative
    if not asset_path.is_file():
        return False
    send_file(handler, asset_path, content_type, cache_control="no-store", include_body=include_body)
    return True
