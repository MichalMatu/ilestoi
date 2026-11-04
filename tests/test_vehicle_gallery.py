from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.database import apply_migrations, connect_database, connect_database_read_only
from core.field_photo_map_query import list_map_vehicle_gallery
from core.field_photo_metadata import vehicle_gallery_priority
from core.field_photo_review import review_field_photo_record
from core.field_photo_store import load_field_record_by_id


class VehicleGalleryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.storage = self.root / "zdjecia_terenowe"
        self.storage.mkdir()
        self.private = self.root / "prywatne_zdjecia"
        self.private.mkdir()
        self.connection = connect_database(self.root / "wreckscanner.sqlite3")
        apply_migrations(self.connection)
        self.addCleanup(self.connection.close)

    def seed(
        self,
        suffix: str,
        *,
        priority: int = 0,
        lat: float = 51.1,
        lon: float = 17.0,
        status: str = "approved",
        resolution: str = "active",
        created_at: str = "2026-11-01T09:00:00Z",
        captured_at: str | None = None,
    ) -> str:
        photo_id = f"photo_20261101T090000Z_{suffix}"
        folder = self.storage / photo_id
        folder.mkdir()
        (folder / "public.jpg").write_bytes(b"public-fixture")
        (folder / "thumb.jpg").write_bytes(b"thumb-fixture")
        with self.connection:
            self.connection.execute(
                """INSERT INTO field_photos
                    (id, created_at, captured_at, issue_type, lat, lon, coordinate_source,
                     public_review_status, vehicle_resolution_status, vehicle_gallery_priority,
                     original_filename, content_type, format, size_bytes, public_image_file, public_thumb_file)
                   VALUES (?, ?, ?, 'vehicle', ?, ?, 'map', ?, ?, ?,
                           'test.jpg', 'image/jpeg', 'JPEG', 20, 'public.jpg', 'thumb.jpg')""",
                (photo_id, created_at, captured_at, lat, lon, status, resolution, priority),
            )
        return photo_id

    def test_priority_validation(self) -> None:
        self.assertEqual(vehicle_gallery_priority("vehicle", 3), 3)
        for invalid in (True, "3", -1, 4, 1.5):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                vehicle_gallery_priority("vehicle", invalid)
        with self.assertRaises(ValueError):
            vehicle_gallery_priority("smoke", 2)

    def test_bounded_gallery_excludes_pending_and_removed(self) -> None:
        selected = self.seed("aaaaaaaa", priority=2)
        self.seed("bbbbbbbb", priority=3, lon=17.002, status="pending")
        self.seed("cccccccc", priority=3, lon=17.004, resolution="removed")
        rows = list_map_vehicle_gallery(self.storage, bounds=(16.99, 51.09, 17.01, 51.11))
        self.assertEqual([row["id"] for row in rows], [selected])
        self.assertEqual(rows[0]["vehicle_gallery_priority"], 2)
        self.assertEqual(rows[0]["public_thumb"], f"/api/field-photos/{selected}/public-thumb")
        self.assertEqual(list_map_vehicle_gallery(self.storage, bounds=(18, 51, 19, 52)), [])

    def test_nominating_another_photo_replaces_previous_one_in_group(self) -> None:
        first = self.seed("aaaaaaaa", priority=1)
        second = self.seed("bbbbbbbb", lon=17.000002)
        record = load_field_record_by_id(second, self.storage)
        result = review_field_photo_record(
            record,
            self.storage / second,
            self.storage,
            self.private,
            vehicle_gallery_priority=3,
        )
        self.assertEqual(result["photo"]["vehicle_gallery_priority"], 3)
        self.assertEqual(load_field_record_by_id(first, self.storage)["vehicle_gallery_priority"], 0)
        self.assertEqual(load_field_record_by_id(second, self.storage)["vehicle_gallery_priority"], 3)
        review_field_photo_record(
            load_field_record_by_id(second, self.storage),
            self.storage / second,
            self.storage,
            self.private,
            vehicle_resolution_status="removed",
        )
        self.assertEqual(load_field_record_by_id(second, self.storage)["vehicle_gallery_priority"], 0)
        self.assertEqual(list_map_vehicle_gallery(self.storage, bounds=(16, 50, 18, 52)), [])

    def test_priority_first_then_longest_documented_standing(self) -> None:
        older_high = self.seed("agehigha", priority=2, lon=17.001, created_at="2026-09-20T10:00:00Z")
        newer_high = self.seed("agehighb", priority=2, lon=17.003, created_at="2026-10-20T10:00:00Z")
        urgent = self.seed("ageurgent", priority=3, lon=17.005, created_at="2026-10-31T10:00:00Z")
        featured = self.seed("agefeat0", priority=1, lon=17.007, created_at="2025-01-01T10:00:00Z")
        rows = list_map_vehicle_gallery(self.storage, bounds=(16.9, 51.0, 17.1, 51.2))
        self.assertEqual([r["id"] for r in rows], [urgent, older_high, newer_high, featured])
        self.assertEqual(rows[1]["first_observed_at"], "2026-09-20T10:00:00Z")

    def test_cover_photo_does_not_reset_group_age(self) -> None:
        old_evidence = self.seed(
            "oldgroup", lon=17.002000, created_at="2026-08-01T12:00:00Z", captured_at="2026-04-01T12:00:00Z"
        )
        cover = self.seed("newcover", priority=2, lon=17.002002, created_at="2026-10-20T12:00:00Z")
        other = self.seed("othercar", priority=2, lon=17.005, created_at="2026-06-01T12:00:00Z")
        rows = list_map_vehicle_gallery(self.storage, bounds=(16.9, 51.0, 17.1, 51.2))
        self.assertEqual([r["id"] for r in rows], [cover, other])
        self.assertEqual(rows[0]["first_observed_at"], "2026-04-01T12:00:00Z")
        self.assertNotEqual(rows[0]["id"], old_evidence)

    def test_invalid_or_future_capture_falls_back_to_upload_date(self) -> None:
        first = self.seed(
            "future00", priority=2, lon=17.001, created_at="2026-05-01T00:00:00Z", captured_at="2099-01-01T00:00:00Z"
        )
        second = self.seed(
            "invalid0", priority=2, lon=17.003, created_at="2026-07-01T00:00:00Z", captured_at="not-a-date"
        )
        rows = list_map_vehicle_gallery(self.storage, bounds=(16.9, 51.0, 17.1, 51.2))
        self.assertEqual([r["id"] for r in rows], [first, second])
        self.assertEqual(rows[0]["first_observed_at"], "2026-05-01T00:00:00Z")

    def test_gallery_uses_one_batched_age_query_for_multiple_covers(self) -> None:
        for index in range(12):
            self.seed(f"{index:08x}", priority=1, lon=17.0 + index * 0.001)
        statements: list[str] = []
        def monitored_connection(path):
            connection = connect_database_read_only(path)
            connection.set_trace_callback(statements.append)
            return connection

        with patch("core.field_photo_map_query.connect_database_read_only", side_effect=monitored_connection):
            rows = list_map_vehicle_gallery(self.storage, bounds=(16.9, 51.0, 17.2, 51.2))
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(item["first_observed_at"] == "2026-11-01T09:00:00Z" for item in rows))
        sql_statements = [statement for statement in statements if "SELECT" in statement.upper()]
        self.assertEqual(len(sql_statements), 2)
        self.assertEqual(sum("WITH covers" in statement for statement in sql_statements), 1)

    def test_pending_cannot_be_nominated(self) -> None:
        photo_id = self.seed("dddddddd", status="pending")
        with self.assertRaises(ValueError):
            review_field_photo_record(
                load_field_record_by_id(photo_id, self.storage),
                self.storage / photo_id,
                self.storage,
                self.private,
                vehicle_gallery_priority=1,
            )


if __name__ == "__main__":
    unittest.main()
