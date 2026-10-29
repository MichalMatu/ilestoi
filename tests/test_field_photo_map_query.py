"""Contract and query-plan regressions for the opt-in SQLite map listing."""

import json
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.http import public_data
from core import config
from core.field_photo_map_query import list_map_field_photos
from core.field_photo_store import connection_for


class Handler:
    def __init__(self, path):
        self.path = path
        self.headers = {}
        self.wfile = BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        pass

    def end_headers(self):
        pass

    def payload(self):
        return json.loads(self.wfile.getvalue())


class MapQueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.storage = self.root / "zdjecia_terenowe"
        self.storage.mkdir()
        self.records = {
            "vehicle": ("photo_20261029T000001Z_00000001", "approved", "vehicle", 51, 17, "2026-10-02"),
            "smoke": ("photo_20261029T000002Z_00000002", "approved", "smoke", 51, 179, "2026-10-02"),
            "infrastructure": ("photo_20261029T000003Z_00000003", "approved", "infrastructure", 51, -179, "2026-10-01"),
            "pending": ("photo_20261029T000004Z_00000004", "pending", "vehicle", 51, 17, "2026-10-03"),
            "draft": ("photo_20261029T000005Z_00000005", "draft", "vehicle", 51, 17, "2026-10-04"),
            "rejected": ("photo_20261029T000006Z_00000006", "rejected", "vehicle", 51, 17, "2026-10-05"),
        }
        con = connection_for(self.storage)
        try:
            with con:
                for pid, status, issue, lat, lon, created in self.records.values():
                    con.execute(
                        """
                        INSERT INTO field_photos (
                            id, created_at, issue_type, lat, lon, coordinate_source,
                            public_review_status, original_filename, content_type,
                            format, size_bytes, public_image_file, public_thumb_file,
                            links_json
                        ) VALUES (?, ?, ?, ?, ?, 'map', ?, 'source.jpg',
                                  'image/jpeg', 'JPEG', 1000, ?, ?, ?)
                        """,
                        (
                            pid, created, issue, lat, lon, status,
                            "public.jpg" if status == "approved" else None,
                            "public_thumb.jpg" if status == "approved" else None,
                            '{"map":"https://example.test"}',
                        ),
                    )
                    if status == "approved":
                        directory = self.storage / pid
                        directory.mkdir()
                        (directory / "public.jpg").write_bytes(b"image")
                        (directory / "public_thumb.jpg").write_bytes(b"thumb")
        finally:
            con.close()

    def _request(self, path, *, is_admin=False, layers=None):
        h = Handler(path)
        settings = {
            "vehicles": True,
            "field_photo_smoke": True,
            "field_photo_infrastructure": False,
            "field_photo_pending": False,
        } if layers is None else layers
        with (
            patch.object(public_data.core_config, "FIELD_PHOTOS_DIR", self.storage),
            patch.object(public_data.http_admin_session, "is_admin", return_value=is_admin),
            patch.object(public_data.access, "public_layer_settings", return_value=settings),
        ):
            public_data.handle_field_photos(h)
        return h

    def test_unbounded_contract_and_guest_layer_filters(self):
        h = self._request("/api/field-photos?ts=123")
        self.assertEqual(h.status, 200)
        p = h.payload()
        self.assertEqual(set(p), {"status", "photos"})
        self.assertEqual([r["id"] for r in p["photos"]], [
            self.records["smoke"][0], self.records["vehicle"][0],
        ])
        self.assertEqual(p["photos"][0]["links"], {"map": "https://example.test"})
        self.assertNotIn("private_original_file", p["photos"][0])
        self.assertNotIn("exif", p["photos"][0])
        self.assertNotIn("edit_token_hash", p["photos"][0])

    def test_admin_sees_pending_but_not_drafts_or_rejected(self):
        h = self._request("/api/field-photos", is_admin=True)
        self.assertEqual(h.status, 200)
        self.assertEqual({r["id"] for r in h.payload()["photos"]}, {
            self.records["vehicle"][0], self.records["smoke"][0],
            self.records["infrastructure"][0], self.records["pending"][0],
        })

    def test_bbox_crosses_dateline_and_is_inclusive(self):
        h = self._request("/api/field-photos?bbox=178,50,-178,52", is_admin=True)
        self.assertEqual(h.status, 200)
        self.assertEqual({r["id"] for r in h.payload()["photos"]}, {
            self.records["smoke"][0], self.records["infrastructure"][0],
        })
        limited = self._request("/api/field-photos?bbox=17,51,17,51", is_admin=True)
        self.assertEqual({r["id"] for r in limited.payload()["photos"]}, {
            self.records["vehicle"][0], self.records["pending"][0],
        })

    def test_cursor_pages_are_stable_with_equal_timestamps(self):
        observed = []
        cursor = None
        for _ in range(4):
            url = "/api/field-photos?limit=1"
            if cursor:
                url += "&cursor=" + cursor
            h = self._request(url, is_admin=True)
            self.assertEqual(h.status, 200)
            data = h.payload()
            observed.extend(r["id"] for r in data["photos"])
            cursor = data["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(observed, [
            self.records["pending"][0],
            self.records["smoke"][0],
            self.records["vehicle"][0],
            self.records["infrastructure"][0],
        ])
        self.assertIsNone(cursor)

    def test_guest_cursor_does_not_page_through_hidden_records(self):
        first = self._request("/api/field-photos?limit=1")
        self.assertEqual(first.status, 200)
        cursor = first.payload()["next_cursor"]
        self.assertIsNotNone(cursor)
        second = self._request("/api/field-photos?limit=1&cursor=" + cursor)
        self.assertEqual(second.status, 200)
        self.assertEqual([x["id"] for x in second.payload()["photos"]], [self.records["vehicle"][0]])
        self.assertIsNone(second.payload()["next_cursor"])

    def test_invalid_query_never_scans_or_writes(self):
        for query in (
            "bbox=nan,0,1,1", "bbox=0,2,1,1", "bbox=0,1,2",
            "bbox=1,1,2,2&bbox=1,1,2,2",
            "limit=-1", "limit=0", "limit=501", "limit=1.0",
            "cursor=abc", "limit=1&cursor=bad",
            "limit=1&cursor=123&cursor=456",
        ):
            with self.subTest(query=query):
                with patch.object(public_data, "list_map_field_photos", side_effect=AssertionError("query ran")):
                    h = self._request("/api/field-photos?" + query)
                self.assertEqual(h.status, 400)

    def test_corrupt_public_derivative_repairs_only_one_selected_record(self):
        pid = self.records["vehicle"][0]
        (self.storage / pid / "public_thumb.jpg").unlink()
        record = {
            "id": pid, "issue_type": "vehicle", "public_review_status": "approved",
            "public_image_file": "public.jpg", "public_thumb_file": "public_thumb.jpg",
        }
        with patch("core.field_photo_map_query.load_field_photo_record", return_value=record) as repair:
            photos, _ = list_map_field_photos(
                self.storage, approved_types=("vehicle",), pending_visible=False
            )
        self.assertEqual([item["id"] for item in photos], [pid])
        repair.assert_called_once_with(pid, self.storage, private_dir=None)

    def test_all_disabled_guest_layers_return_no_rows(self):
        h = self._request("/api/field-photos", layers={
            "vehicles": False, "field_photo_smoke": False,
            "field_photo_infrastructure": False, "field_photo_pending": False,
        })
        self.assertEqual(h.payload()["photos"], [])


if __name__ == "__main__":
    unittest.main()
