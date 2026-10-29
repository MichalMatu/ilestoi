import unittest
from io import BytesIO
from unittest.mock import patch
from xml.etree import ElementTree

from app.http import observation_pages


class Handler:
    def __init__(self, path):
        self.path = path
        self.wfile = BytesIO()
        self.headers = {}
        self.headers_sent = []
        self.status = None

    def send_response(self, code):
        self.status = code

    def send_header(self, key, value):
        self.headers_sent.append((key, value))

    def end_headers(self):
        pass


class ObservationPagesTests(unittest.TestCase):
    def setUp(self):
        self.approved = {
            "id": "photo_20260604T184016Z_fc121f84",
            "public_review_status": "approved", "issue_type": "vehicle",
            "public_image": "/api/field-photos/photo_20260604T184016Z_fc121f84/public-image",
            "public_thumb": "/api/field-photos/photo_20260604T184016Z_fc121f84/public-thumb",
            "lat": 51.086872, "lon": 17.041330, "captured_at": "2026-06-04",
            "created_at": "2026-06-04", "vehicle_insurance_status": "uninsured",
            "vehicle_insurance_checked_at": "2026-07-05",
            "vehicle_resolution_status": "active",
        }
        self.pending = {**self.approved, "id": "pending", "public_review_status": "pending"}
        self.removed = {**self.approved, "id": "removed", "vehicle_resolution_status": "removed"}
        self.hidden = {**self.approved, "id": "hidden", "issue_type": "smoke"}

    def _patch(self, layers=None):
        return (
            patch.object(observation_pages, "list_field_photos", return_value=[
                self.approved, self.pending, self.removed, self.hidden
            ]),
            patch.object(observation_pages.access, "public_layer_settings", return_value=layers or {
                "vehicles": True, "field_photo_smoke": False
            })
        )

    def test_public_list_excludes_pending_removed_and_disabled_layers(self):
        a, b = self._patch()
        with a, b:
            items = observation_pages.public_observations()
        self.assertEqual([p["id"] for p in items], [self.approved["id"]])

    def test_server_rendered_observation_has_public_image_metadata_and_manual_oc(self):
        a, b = self._patch()
        h = Handler("/observations/" + self.approved["id"])
        with a, b, patch.object(
            observation_pages, "load_field_photo_record", return_value=self.approved
        ):
            self.assertTrue(observation_pages.handle_public_route(h, h.path))
        txt = h.wfile.getvalue().decode()
        self.assertEqual(h.status, 200)
        self.assertIn("public-thumb", txt)
        self.assertIn("public-image", txt)
        self.assertIn("2026-07-05", txt)
        self.assertIn("nie jest sprawdzany na żywo", txt)
        self.assertNotIn("owner-original", txt)
        self.assertNotIn("admin/photos", txt)

    def test_detail_looks_up_one_record_without_scanning_photo_list(self):
        h = Handler("/observations/" + self.approved["id"])
        with (
            patch.object(observation_pages, "list_field_photos", side_effect=AssertionError("full scan")) as scan,
            patch.object(observation_pages, "load_field_photo_record", return_value=self.approved) as lookup,
            patch.object(observation_pages.access, "public_layer_settings", return_value={"vehicles": True}),
        ):
            self.assertTrue(observation_pages.handle_public_route(h, h.path))
        self.assertEqual(h.status, 200)
        scan.assert_not_called()
        lookup.assert_called_once_with(self.approved["id"], observation_pages.core_config.FIELD_PHOTOS_DIR)

    def test_detail_hides_unapproved_removed_and_disabled_observations(self):
        cases = [
            ({**self.approved, "public_review_status": "draft"}, {"vehicles": True}),
            ({**self.approved, "public_review_status": "pending"}, {"vehicles": True}),
            ({**self.approved, "public_review_status": "rejected"}, {"vehicles": True}),
            ({**self.approved, "vehicle_resolution_status": "removed"}, {"vehicles": True}),
            ({**self.approved, "issue_type": "smoke"}, {"field_photo_smoke": False}),
        ]
        for record, layers in cases:
            with self.subTest(record=record["public_review_status"], layers=layers):
                h = Handler("/observations/" + self.approved["id"])
                with (
                    patch.object(observation_pages, "load_field_photo_record", return_value=record),
                    patch.object(observation_pages.access, "public_layer_settings", return_value=layers),
                ):
                    observation_pages.handle_public_route(h, h.path)
                self.assertEqual(h.status, 404)
                self.assertNotIn(b"owner-original", h.wfile.getvalue())

    def test_detail_missing_record_returns_404_without_full_scan(self):
        h = Handler("/observations/" + self.approved["id"])
        with (
            patch.object(observation_pages, "list_field_photos", side_effect=AssertionError("full scan")),
            patch.object(observation_pages, "load_field_photo_record", side_effect=FileNotFoundError),
        ):
            observation_pages.handle_public_route(h, h.path)
        self.assertEqual(h.status, 404)

    def test_geo_query_and_head(self):
        a, b = self._patch()
        h = Handler("/observations?lat=51.086893&lon=17.041340&radius=15")
        with a, b:
            self.assertTrue(observation_pages.handle_public_route(h, "/observations", include_body=False))
        self.assertEqual(h.status, 200)
        self.assertFalse(h.wfile.getvalue())
        a, b = self._patch()
        h2 = Handler(h.path)
        with a, b:
            observation_pages.handle_public_route(h2, "/observations")
        self.assertIn(self.approved["id"], h2.wfile.getvalue().decode())

    def test_sitemap_and_missing_public_photo(self):
        a, b = self._patch()
        h = Handler("/sitemap-observations.xml")
        with a, b:
            observation_pages.handle_public_route(h, h.path)
        xml = h.wfile.getvalue().decode()
        ElementTree.fromstring(xml)
        self.assertIn(self.approved["id"], xml)
        self.assertNotIn(">pending<", xml)
        a, b = self._patch()
        h2 = Handler("/observations/pending")
        with a, b, patch.object(
            observation_pages, "load_field_photo_record", return_value=self.pending
        ):
            observation_pages.handle_public_route(h2, h2.path)
        self.assertEqual(h2.status, 404)

    def test_robot_rules_are_scoped_to_read_only_public_assets(self):
        from pathlib import Path
        robots = (Path(__file__).resolve().parents[1] / "web/robots.txt").read_text()
        for rule in (
            "Allow: /api/field-photos$",
            "Allow: /api/field-photos/*/public-image$",
            "Allow: /api/field-photos/*/public-thumb$",
            "Disallow: /api/",
            "Sitemap: https://ilestoi.pl/sitemap-observations.xml",
        ):
            self.assertIn(rule, robots)
        self.assertNotIn("Allow: /api/field-photos/\n", robots)


if __name__ == "__main__":
    unittest.main()
