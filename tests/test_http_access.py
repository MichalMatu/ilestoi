import json
import unittest
from io import BytesIO
from unittest.mock import patch

from app.http import access


class FakeHandler:
    def __init__(self):
        self.client_address = ("127.0.0.1", 12345)
        self.headers = {"User-Agent": "contract-test"}
        self.status = None
        self.response_headers = []
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


class HttpAccessContractTests(unittest.TestCase):
    def test_public_feature_gate_blocks_disabled_guest_feature(self):
        handler = FakeHandler()

        with (
            patch.object(access.http_admin_session, "is_admin", return_value=False),
            patch.object(access, "load_app_settings", return_value={"public_features": {"photo_uploads": False}}),
        ):
            allowed = access.require_public_feature(handler, "photo_uploads", "disabled")

        self.assertFalse(allowed)
        self.assertEqual(handler.status, 403)
        self.assertEqual(handler.payload["error"], "disabled")
        self.assertIn("request_id", handler.payload)

    def test_admin_bypasses_public_feature_gate(self):
        handler = FakeHandler()

        with (
            patch.object(access.http_admin_session, "is_admin", return_value=True),
            patch.object(access, "load_app_settings", return_value={"public_features": {"photo_uploads": False}}),
        ):
            allowed = access.require_public_feature(handler, "photo_uploads", "disabled")

        self.assertTrue(allowed)
        self.assertIsNone(handler.status)

    def test_field_photo_issue_type_maps_to_layer_key(self):
        self.assertEqual(access.field_photo_issue_layer_key("vehicle"), "vehicles")
        self.assertEqual(access.field_photo_issue_layer_key("smoke"), "field_photo_smoke")

        with self.assertRaises(ValueError):
            access.field_photo_issue_layer_key("unknown")

    def test_pending_field_photo_access_uses_pending_layer_only(self):
        handler = FakeHandler()
        pending_vehicle_photo = {"issue_type": "vehicle", "public_review_status": "pending"}

        with (
            patch.object(access.http_admin_session, "is_admin", return_value=False),
            patch.object(
                access,
                "load_app_settings",
                return_value={"public_layers": {"vehicles": False, "field_photo_pending": True}},
            ),
        ):
            self.assertTrue(access.public_field_photo_allowed(handler, pending_vehicle_photo))

        with (
            patch.object(access.http_admin_session, "is_admin", return_value=False),
            patch.object(
                access,
                "load_app_settings",
                return_value={"public_layers": {"vehicles": True, "field_photo_pending": False}},
            ),
        ):
            self.assertFalse(access.public_field_photo_allowed(handler, pending_vehicle_photo))

    def test_draft_field_photo_is_not_publicly_visible(self):
        handler = FakeHandler()
        draft_photo = {"issue_type": "vehicle", "public_review_status": "draft"}

        with (
            patch.object(access.http_admin_session, "is_admin", return_value=False),
            patch.object(
                access,
                "load_app_settings",
                return_value={"public_layers": {"vehicles": True, "field_photo_pending": True}},
            ),
        ):
            self.assertFalse(access.public_field_photo_allowed(handler, draft_photo))

    def test_public_field_photo_batch_can_reuse_settings_without_reloading(self):
        handler = FakeHandler()
        settings = {"vehicles": True, "field_photo_pending": False, "field_photo_smoke": False}
        with (
            patch.object(access.http_admin_session, "is_admin", return_value=False),
            patch.object(access, "load_app_settings", side_effect=AssertionError("should not reload")),
        ):
            self.assertTrue(
                access.public_field_photo_allowed(
                    handler, {"issue_type": "vehicle", "public_review_status": "approved"}, layer_settings=settings
                )
            )
            self.assertFalse(
                access.public_field_photo_allowed(
                    handler, {"issue_type": "vehicle", "public_review_status": "pending"}, layer_settings=settings
                )
            )
            self.assertFalse(
                access.public_field_photo_allowed(
                    handler, {"issue_type": "smoke", "public_review_status": "approved"}, layer_settings=settings
                )
            )

    def test_public_submission_quota_uses_hashed_owner(self):
        handler = FakeHandler()

        with (
            patch.object(access.http_admin_session, "is_admin", return_value=False),
            patch.object(access, "assert_pending_submission_quota") as quota,
        ):
            access.ensure_public_submission_quota(handler, additional_bytes=12, additional_items=2)

        kwargs = quota.call_args.kwargs
        self.assertTrue(kwargs["owner"].startswith("public:"))
        self.assertEqual(kwargs["additional_bytes"], 12)
        self.assertEqual(kwargs["additional_items"], 2)

    def test_submission_owner_uses_trusted_proxy_client_identity(self):
        handler = FakeHandler()
        handler.headers["CF-Connecting-IP"] = "203.0.113.9"

        with patch.object(access, "client_key", return_value="203.0.113.9"):
            first_owner = access.submission_owner(handler)
        with patch.object(access, "client_key", return_value="203.0.113.10"):
            second_owner = access.submission_owner(handler)

        self.assertTrue(first_owner.startswith("public:"))
        self.assertNotEqual(first_owner, second_owner)


if __name__ == "__main__":
    unittest.main()
