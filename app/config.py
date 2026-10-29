from __future__ import annotations

import os
import secrets
from pathlib import Path

from core.config import (
    BYTES_PER_GIB,
    BYTES_PER_MIB,
    ORTHO_WMS_BASE,
    ORTHO_WMS_TIMEOUT,
    ORTHO_YEARS,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"

HOST = os.environ.get("WRECKSCANNER_HOST", "127.0.0.1")
PORT = int(os.environ.get("WRECKSCANNER_PORT", "8001"))

WMS_UPSTREAM_BASE = ORTHO_WMS_BASE
WMS_TIMEOUT = ORTHO_WMS_TIMEOUT
GEOPORTAL_STANDARD_WMTS_URL = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMTS/StandardResolution"

# Cache tile'i po wspólnym filtrze ortofoto. Większy limit przyspiesza mapę,
# ale rośnie zużycie dysku pod `.cache/wms_tiles`.
WMS_TILE_CACHE_DIR = ROOT_DIR / ".cache" / "wms_tiles"
WMS_TILE_CACHE_MAX_BYTES = int(float(os.environ.get("WRECKSCANNER_WMS_TILE_CACHE_GB", "8")) * BYTES_PER_GIB)
WMS_TILE_CACHE_MIN_FREE_BYTES = int(
    float(os.environ.get("WRECKSCANNER_WMS_TILE_CACHE_MIN_FREE_GB", "2")) * BYTES_PER_GIB
)
WMS_TILE_CACHE_CLEANUP_INTERVAL_SECONDS = 60
WMS_TILE_CACHE_CONTROL = "public, max-age=86400"
WMS_ALLOWED_YEARS = frozenset(ORTHO_YEARS)
WMS_MAX_CONCURRENT_REQUESTS = 8

CADASTRAL_WMS_URL = "https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow"
CADASTRAL_WMS_FALLBACK_URL = "https://services.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow"
CADASTRAL_WMS_TIMEOUT = (10, 30)
PRG_ADDRESS_WFS_URL = os.environ.get(
    "WRECKSCANNER_PRG_ADDRESS_WFS_URL",
    "https://mapy.geoportal.gov.pl/wss/ext/KrajowaIntegracjaNumeracjiAdresowej",
)
PRG_ADDRESS_WFS_TIMEOUT = (3, 10)
PRG_ADDRESS_SEARCH_RADIUS_M = 160.0
PRG_ADDRESS_MAX_FEATURES = 50
PRG_ADDRESS_MAX_RESPONSE_BYTES = 2 * BYTES_PER_MIB
NOMINATIM_REVERSE_URL = os.environ.get(
    "WRECKSCANNER_NOMINATIM_REVERSE_URL",
    "https://nominatim.openstreetmap.org/reverse",
)
NOMINATIM_TIMEOUT = (3, 8)
NOMINATIM_MAX_RESPONSE_BYTES = 256 * 1024
NOMINATIM_USER_AGENT = os.environ.get(
    "WRECKSCANNER_NOMINATIM_USER_AGENT",
    "IleStoi-WreckScanner/1.0 (https://ilestoi.pl)",
)

PHOTO_RETENTION_AUTORUN_ENABLED = os.environ.get("WRECKSCANNER_PHOTO_RETENTION_AUTORUN", "1").strip() not in {
    "0",
    "false",
    "False",
    "no",
}
PHOTO_RETENTION_STARTUP_DELAY_SECONDS = 5
PHOTO_RETENTION_INTERVAL_SECONDS = 24 * 60 * 60

ADMIN_PASSWORD_FILE = ROOT_DIR / ".admin_password"
ADMIN_COOKIE_NAME = "wreckscanner_admin"
ADMIN_SESSION_SECONDS = 12 * 60 * 60
ADMIN_SESSION_CLOCK_SKEW_SECONDS = 60
ADMIN_MAX_ACTIVE_SESSIONS = 256
ADMIN_SESSION_SECRET = os.environ.get("WRECKSCANNER_ADMIN_SESSION_SECRET") or secrets.token_urlsafe(32)
ADMIN_COOKIE_SECURE = os.environ.get("WRECKSCANNER_ADMIN_COOKIE_SECURE", "1").strip().lower() not in {
    "0",
    "false",
    "no",
}
CORS_ALLOWED_ORIGINS = tuple(
    origin.strip()
    for origin in os.environ.get(
        "WRECKSCANNER_CORS_ALLOWED_ORIGINS",
        "https://ilestoi.pl",
    ).split(",")
    if origin.strip()
)
TRUSTED_PROXY_ADDRESSES = tuple(
    address.strip()
    for address in os.environ.get("WRECKSCANNER_TRUSTED_PROXY_ADDRESSES", "127.0.0.1,::1").split(",")
    if address.strip()
)
PUBLIC_HOSTS = tuple(
    hostname.strip().lower().rstrip(".")
    for hostname in os.environ.get(
        "WRECKSCANNER_PUBLIC_HOSTS",
        "wreckscanner.pl,www.wreckscanner.pl,ilestoi.pl,www.ilestoi.pl,dlugostoi.pl,www.dlugostoi.pl",
    ).split(",")
    if hostname.strip()
)
CANONICAL_PUBLIC_HOST = "ilestoi.pl"
CANONICAL_PUBLIC_ORIGIN = f"https://{CANONICAL_PUBLIC_HOST}"

# JSON endpointy przenoszą małe komendy i ustawienia. Większe payloady zdjęć
# idą przez multipart i mają osobne limity w core.config.
MAX_JSON_BODY_BYTES = BYTES_PER_MIB
MAX_HTTP_CONCURRENT_REQUESTS = 32
HTTP_SOCKET_TIMEOUT_SECONDS = 30
REPORT_MAX_CONCURRENT_REQUESTS = 2

INSPECT_JPEG_QUALITY = 95
CADASTRAL_MAX_RESPONSE_BYTES = 2 * BYTES_PER_MIB
