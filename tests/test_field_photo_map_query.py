"""Contract and query-plan regressions for the opt-in SQLite map listing."""

import json
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.http import public_data
from core.field_photo_clusters import list_map_photo_clusters
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
                            pid,
                            created,
                            issue,
                            lat,
                            lon,
                            status,
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
        settings = (
            {
                "vehicles": True,
                "field_photo_smoke": True,
                "field_photo_infrastructure": False,
                "field_photo_pending": False,
            }
            if layers is None
            else layers
        )
        with (
            patch.object(
                public_data,
                "list_map_field_photos",
                side_effect=lambda _storage, **kwargs: list_map_field_photos(self.storage, **kwargs),
            ),
            patch.object(public_data.http_admin_session, "is_admin", return_value=is_admin),
            patch.object(public_data.access, "public_layer_settings", return_value=settings),
        ):
            public_data.handle_field_photos(h)
        return h

    def _cluster_request(self, path, *, is_admin=False, layers=None):
        handler = Handler(path)
        settings = (
            {
                "vehicles": True,
                "field_photo_smoke": True,
                "field_photo_infrastructure": False,
                "field_photo_pending": False,
            }
            if layers is None
            else layers
        )
        with (
            patch.object(
                public_data,
                "list_map_photo_clusters",
                side_effect=lambda _storage, **kwargs: list_map_photo_clusters(self.storage, **kwargs),
            ),
            patch.object(public_data.http_admin_session, "is_admin", return_value=is_admin),
            patch.object(public_data.access, "public_layer_settings", return_value=settings),
        ):
            public_data.handle_field_photo_clusters(handler)
        return handler

    def test_overview_is_bounded_and_contains_only_aggregate_fields(self):
        response = self._cluster_request("/api/field-photos/clusters?bbox=-180,-90,180,90", is_admin=True)
        self.assertEqual(response.status, 200)
        clusters = response.payload()["clusters"]
        self.assertLessEqual(len(clusters), 256)
        self.assertEqual(sum(c["total"] for c in clusters), 4)
        self.assertEqual(sum(c["vehicles"] for c in clusters), 1)
        self.assertEqual(sum(c["smoke"] for c in clusters), 1)
        self.assertEqual(sum(c["infrastructure"] for c in clusters), 1)
        self.assertEqual(sum(c["pending"] for c in clusters), 1)
        for cluster in clusters:
            self.assertEqual(set(cluster), {"lat", "lon", "total", "vehicles", "smoke", "infrastructure", "pending"})
            self.assertEqual(
                cluster["total"],
                cluster["vehicles"] + cluster["smoke"] + cluster["infrastructure"] + cluster["pending"],
            )
        self.assertNotIn(self.records["vehicle"][0], json.dumps(clusters))
        self.assertNotIn("https://example.test", json.dumps(clusters))

    def test_guest_overview_respects_every_disabled_public_layer(self):
        normal = self._cluster_request("/api/field-photos/clusters?bbox=-180,-90,180,90")
        self.assertEqual(normal.status, 200)
        clusters = normal.payload()["clusters"]
        self.assertEqual(sum(c["total"] for c in clusters), 2)
        self.assertEqual(sum(c["infrastructure"] for c in clusters), 0)
        self.assertEqual(sum(c["pending"] for c in clusters), 0)
        disabled = self._cluster_request(
            "/api/field-photos/clusters?bbox=-180,-90,180,90",
            layers={
                "vehicles": False,
                "field_photo_smoke": False,
                "field_photo_infrastructure": False,
                "field_photo_pending": False,
            },
        )
        self.assertEqual(disabled.payload()["clusters"], [])

    def test_pending_can_be_aggregated_only_if_visible_to_guest(self):
        response = self._cluster_request(
            "/api/field-photos/clusters?bbox=16,50,18,52",
            layers={
                "vehicles": False,
                "field_photo_smoke": False,
                "field_photo_infrastructure": False,
                "field_photo_pending": True,
            },
        )
        self.assertEqual(response.status, 200)
        clusters = response.payload()["clusters"]
        self.assertEqual(sum(c["total"] for c in clusters), 1)
        self.assertEqual(sum(c["pending"] for c in clusters), 1)

    def test_cross_dateline_both_longitudes_share_one_cell_when_nearby(self):
        response = self._cluster_request("/api/field-photos/clusters?bbox=178,50,-178,52", is_admin=True)
        clusters = response.payload()["clusters"]
        self.assertEqual(sum(c["total"] for c in clusters), 2)
        self.assertEqual(sum(c["smoke"] for c in clusters), 1)
        self.assertEqual(sum(c["infrastructure"] for c in clusters), 1)
        self.assertTrue(all(abs(cluster["lon"]) >= 178 for cluster in clusters))

    def test_overview_bbox_is_required_and_invalid_inputs_never_query_sqlite(self):
        for query in (
            "",
            "?ts=1",
            "?bbox=nan,0,1,1",
            "?bbox=1,2,3",
            "?bbox=0,2,1,1",
            "?bbox=1,1,2,2&limit=1",
            "?bbox=1,1,2,2&bbox=1,1,2,2",
            "?bbox=1,1,2,2&cursor=x",
        ):
            with self.subTest(query=query):
                with patch.object(public_data, "list_map_photo_clusters", side_effect=AssertionError("queried")):
                    result = self._cluster_request("/api/field-photos/clusters" + query)
                self.assertEqual(result.status, 400)

    def test_dense_grid_is_bounded_and_counts_photos_not_vehicle_groups(self):
        con = connection_for(self.storage)
        try:
            with con:
                for n in range(330):
                    con.execute(
                        """
                        INSERT INTO field_photos (
                            id, created_at, issue_type, lat, lon, coordinate_source,
                            public_review_status, original_filename, content_type,
                            format, size_bytes, links_json
                        ) VALUES (?, '2026-10-29', 'vehicle', 51.1, 17.1, 'map',
                                  'pending', 'source.jpg', 'image/jpeg', 'JPEG', 1, '{}')
                        """,
                        (f"photo_20261029T010101Z_{n:08x}",),
                    )
        finally:
            con.close()
        response = self._cluster_request("/api/field-photos/clusters?bbox=16,50,18,52", is_admin=True)
        clusters = response.payload()["clusters"]
        self.assertLessEqual(len(clusters), 256)
        self.assertEqual(sum(c["total"] for c in clusters), 332)
        self.assertEqual(sum(c["pending"] for c in clusters), 331)

    def test_exact_point_bounds_never_move_the_synthetic_center_outside_bbox(self):
        response = self._cluster_request("/api/field-photos/clusters?bbox=17,51,17,51", is_admin=True)
        self.assertEqual(response.status, 200)
        clusters = response.payload()["clusters"]
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["total"], 2)
        self.assertEqual((clusters[0]["lat"], clusters[0]["lon"]), (51, 17))

    def test_cluster_endpoint_is_registered_with_the_safe_get_dispatch(self):
        from app.http import dispatch

        handler = Handler("/api/field-photos/clusters?bbox=0,0,1,1")
        with patch.object(public_data, "handle_field_photo_clusters") as cluster_route:
            self.assertTrue(dispatch.handle_static_api_get(handler, "/api/field-photos/clusters"))
        cluster_route.assert_called_once_with(handler)

    def test_empty_viewport_never_leaks_an_unbounded_list(self):
        response = self._cluster_request("/api/field-photos/clusters?bbox=0,0,1,1", is_admin=True)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload(), {"status": "ok", "clusters": []})

    def test_unbounded_contract_and_guest_layer_filters(self):
        h = self._request("/api/field-photos?ts=123")
        self.assertEqual(h.status, 200)
        p = h.payload()
        self.assertEqual(set(p), {"status", "photos"})
        self.assertEqual(
            [r["id"] for r in p["photos"]],
            [
                self.records["smoke"][0],
                self.records["vehicle"][0],
            ],
        )
        self.assertEqual(p["photos"][0]["links"], {"map": "https://example.test"})
        self.assertNotIn("private_original_file", p["photos"][0])
        self.assertNotIn("exif", p["photos"][0])
        self.assertNotIn("edit_token_hash", p["photos"][0])

    def test_admin_sees_pending_but_not_drafts_or_rejected(self):
        h = self._request("/api/field-photos", is_admin=True)
        self.assertEqual(h.status, 200)
        self.assertEqual(
            {r["id"] for r in h.payload()["photos"]},
            {
                self.records["vehicle"][0],
                self.records["smoke"][0],
                self.records["infrastructure"][0],
                self.records["pending"][0],
            },
        )

    def test_bbox_crosses_dateline_and_is_inclusive(self):
        h = self._request("/api/field-photos?bbox=178,50,-178,52", is_admin=True)
        self.assertEqual(h.status, 200)
        self.assertEqual(
            {r["id"] for r in h.payload()["photos"]},
            {
                self.records["smoke"][0],
                self.records["infrastructure"][0],
            },
        )
        limited = self._request("/api/field-photos?bbox=17,51,17,51", is_admin=True)
        self.assertEqual(
            {r["id"] for r in limited.payload()["photos"]},
            {
                self.records["vehicle"][0],
                self.records["pending"][0],
            },
        )

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
        self.assertEqual(
            observed,
            [
                self.records["pending"][0],
                self.records["smoke"][0],
                self.records["vehicle"][0],
                self.records["infrastructure"][0],
            ],
        )
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
            "bbox=nan,0,1,1",
            "bbox=0,2,1,1",
            "bbox=0,1,2",
            "bbox=1,1,2,2&bbox=1,1,2,2",
            "limit=-1",
            "limit=0",
            "limit=501",
            "limit=1.0",
            "cursor=abc",
            "limit=1&cursor=bad",
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
            "id": pid,
            "issue_type": "vehicle",
            "public_review_status": "approved",
            "public_image_file": "public.jpg",
            "public_thumb_file": "public_thumb.jpg",
        }
        with patch("core.field_photo_map_query.load_field_photo_record", return_value=record) as repair:
            photos, _ = list_map_field_photos(self.storage, approved_types=("vehicle",), pending_visible=False)
        self.assertEqual([item["id"] for item in photos], [pid])
        repair.assert_called_once_with(pid, self.storage, private_dir=None)

    def test_all_disabled_guest_layers_return_no_rows(self):
        h = self._request(
            "/api/field-photos",
            layers={
                "vehicles": False,
                "field_photo_smoke": False,
                "field_photo_infrastructure": False,
                "field_photo_pending": False,
            },
        )
        self.assertEqual(h.payload()["photos"], [])


if __name__ == "__main__":
    unittest.main()
