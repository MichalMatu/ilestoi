import json
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from app.http import health
from core.database import apply_migrations, connect_database, validate_readiness_database


class FakeHandler:
    def __init__(self):
        self.client_address = ("127.0.0.1", 12345)
        self.command = "GET"
        self.headers = {}
        self.path = "/api/health/ready"
        self.response_headers = []
        self.status = None
        self.wfile = BytesIO()

    @property
    def payload(self) -> dict:
        return json.loads(self.wfile.getvalue().decode("utf-8"))

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        return None


class HttpHealthContractTests(unittest.TestCase):
    def test_liveness_is_minimal(self):
        handler = FakeHandler()

        health.handle_liveness(handler)

        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.payload, {"status": "ok"})

    def test_readiness_checks_database_and_storage_without_paths(self):
        handler = FakeHandler()
        disk = SimpleNamespace(free=10 * 1024**3)

        with (
            patch.object(health, "validate_readiness_database", return_value=None),
            patch.object(health.shutil, "disk_usage", return_value=disk),
            patch.object(health.os, "access", return_value=True),
        ):
            health.handle_readiness(handler)

        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.payload, {"status": "ok", "checks": {"database": "ok", "storage": "ok"}})
        self.assertNotIn("field_photos", json.dumps(handler.payload))
        self.assertNotIn("privacy_requests", json.dumps(handler.payload))
        self.assertNotIn("free_bytes", json.dumps(handler.payload))
        self.assertNotIn("dir", json.dumps(handler.payload))
        self.assertNotIn("path", json.dumps(handler.payload))

    def test_readiness_returns_sanitized_503_on_failure(self):
        handler = FakeHandler()

        with (
            patch.object(health, "validate_readiness_database", side_effect=ValueError("/secret/path corrupt")),
            patch.object(health.http_responses, "log_exception") as log_exception,
        ):
            health.handle_readiness(handler)

        self.assertEqual(handler.status, 503)
        self.assertNotIn("/secret/path", json.dumps(handler.payload))
        self.assertEqual(handler.payload["status"], "error")
        log_exception.assert_called_once()

    def test_readiness_database_fast_probe_checks_schema_without_file_audit(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "test.sqlite3"
            with self.assertRaises(ValueError):
                validate_readiness_database(database_path=db)
            connection = connect_database(db)
            try:
                apply_migrations(connection)
            finally:
                connection.close()
            # No photo directories exist: the full integrity check can remain
            # a separate audit, while the readiness probe stays lightweight.
            validate_readiness_database(database_path=db)

    def test_readiness_database_rejects_missing_migration(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.sqlite3"
            connection = connect_database(db)
            try:
                apply_migrations(connection)
                with connection:
                    connection.execute("DELETE FROM schema_migrations")
            finally:
                connection.close()
            with self.assertRaisesRegex(ValueError, "migracje"):
                validate_readiness_database(database_path=db)


if __name__ == "__main__":
    unittest.main()
