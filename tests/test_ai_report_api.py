"""Regression tests for the AI-facing JSON PDF adapter (no live DB or WMS)."""
import io
import json
import unittest
from unittest.mock import patch

from app.http import ai_api, public, rate_limit


class FakeRequest:
    def __init__(self, data):
        raw = json.dumps(data).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)


class AiReportApiTests(unittest.TestCase):
    def test_schema_contains_read_and_generate_contract(self):
        paths = ai_api.OPENAPI["paths"]
        self.assertIn("get", paths["/api/field-photos"])
        self.assertIn("post", paths["/api/ai/report-pdf"])
        self.assertNotIn("send-email", json.dumps(paths).lower())

    def test_ai_and_browser_pdf_routes_share_one_rate_limit_bucket(self):
        a = rate_limit.matching_rule('POST', '/api/ai/report-pdf')
        b = rate_limit.matching_rule('POST', '/api/field-photo-reports/report-pdf')
        self.assertIsNotNone(a)
        self.assertEqual(a.name, b.name)
        self.assertEqual(a.limit, 12)

    def test_json_form_is_normalized_for_existing_generator(self):
        request = FakeRequest({
            "photo_ids": ["photo_1", "photo_2"],
            "lat": 51.09, "lon": 17.03,
            "reporter_name": "Test",
            "location_description": "Test location",
        })
        fields = public._ai_report_fields(request)
        self.assertEqual(json.loads(fields["photo_ids"]), ["photo_1", "photo_2"])
        self.assertEqual(public._report_photo_ids(fields), ["photo_1", "photo_2"])
        self.assertEqual(fields["lat"], "51.09")

    def test_rejects_unrecognized_fields(self):
        with self.assertRaisesRegex(ValueError, "Nieznane"):
            public._ai_report_fields(FakeRequest({"photo_ids": ["photo_1"], "send_email": True}))

    def test_rejects_non_string_ids(self):
        with self.assertRaisesRegex(ValueError, "tekst"):
            public._ai_report_fields(FakeRequest({"photo_ids": [123]}))

    def test_rejects_non_string_field_values(self):
        with self.assertRaisesRegex(ValueError, "typ"):
            public._ai_report_fields(FakeRequest({"photo_ids": ["photo_1"], "reporter_name": 123}))

    def test_json_handler_uses_shared_generator_and_never_sends_email(self):
        payload = {
            "photo_ids": ["photo_1"], "lat": "51.09", "lon": "17.03",
            "reporter_name": "Example Reporter",
            "reporter_email": "example@example.com",
            "reporter_phone": "123456789",
            "reporter_address": "Test Address",
            "location_description": "Test Location",
            "observed_at": "2026-10-28T10:00",
            "vehicle_description": "Test Vehicle",
        }
        handler = FakeRequest(payload)
        with (
            patch.object(public.access, "require_public_feature", return_value=True),
            patch.object(public, "validate_field_photo_report_selection"),
            patch.object(public, "_report_cadastral_context", return_value=(None, "")),
            patch.object(public, "_report_address_context", return_value=None),
            patch.object(public, "create_field_photo_report_pdf",
                         return_value={"status": "ok", "pdf_base64": "JVBERg==",
                                       "pdf_filename": "report.pdf"}) as render,
            patch.object(public.http_responses, "send_json") as send,
        ):
            public.handle_ai_report_pdf(handler)
        self.assertEqual(render.call_count, 1)
        self.assertEqual(send.call_args.args[1], 200)
        self.assertEqual(send.call_args.args[2]["pdf_filename"], "report.pdf")


if __name__ == "__main__":
    unittest.main()
