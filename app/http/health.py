import os
import shutil

from app import config
from app.http import responses as http_responses
from core import config as core_config
from core.database import validate_readiness_database


def handle_liveness(handler) -> None:
    http_responses.send_json(handler, 200, {"status": "ok"})


def _readiness_payload() -> dict:
    validate_readiness_database(database_path=core_config.DATABASE_PATH)
    disk = shutil.disk_usage(config.ROOT_DIR)
    if disk.free < config.WMS_TILE_CACHE_MIN_FREE_BYTES:
        raise RuntimeError("Za mało wolnego miejsca na dysku danych.")
    if not os.access(config.ROOT_DIR, os.R_OK | os.W_OK | os.X_OK):
        raise RuntimeError("Katalog danych aplikacji nie jest dostępny do zapisu.")
    return {
        "status": "ok",
        "checks": {
            "database": "ok",
            "storage": "ok",
        },
    }


def handle_readiness(handler) -> None:
    try:
        http_responses.send_json(handler, 200, _readiness_payload())
    except Exception as exc:
        http_responses.send_internal_error(
            handler,
            503,
            "Readiness check failed",
            exc,
            public_error="Serwer nie jest gotowy do obsługi żądań.",
            payload={"checks": {"database": "error", "storage": "error"}},
        )
