import json
import unittest
from io import BytesIO
from unittest.mock import patch

from app.http import admin as http_admin
from core import config as core_config


class FakeHandler:
    def __init__(self):
        self.client_address = ("127.0.0.1", 12345)
        self.command = "PATCH"
        self.headers = {}
        self.path = "/api/admin/photos/field/photo_20260704T080000Z_12345678/review"
        self.response_headers = []
        self.status = None
        self.wfile = BytesIO()

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        return None

    def payload(self) -> dict:
        return json.loads(self.wfile.getvalue().decode("utf-8"))


class HttpAdminContractTests(unittest.TestCase):
    def test_review_photo_accepts_resolution_only_payload(self):
        handler = FakeHandler()

        with (
            patch.object(http_admin.http_admin_session, "require_admin", return_value=True),
            patch.object(
                http_admin.http_request_body,
                "read_json_body",
                return_value={"vehicle_resolution_status": "removed"},
            ),
            patch.object(
                http_admin,
                "review_field_photo",
                return_value={
                    "status": "ok",
                    "vehicle_resolution_updated_photo_ids": ["photo_20260704T080000Z_12345678"],
                },
            ) as review_field_photo,
        ):
            http_admin.handle_review_photo(handler, ("field", ("photo_20260704T080000Z_12345678",)))

        review_field_photo.assert_called_once_with(
            "photo_20260704T080000Z_12345678",
            core_config.FIELD_PHOTOS_DIR,
            status=None,
            redactions=None,
            vehicle_insurance_status=None,
            vehicle_resolution_status="removed",
            vehicle_gallery_priority=None,
            private_dir=core_config.PRIVATE_PHOTOS_DIR,
        )
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.payload()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
