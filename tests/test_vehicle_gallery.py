from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.database import apply_migrations, connect_database
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

    def seed(self, suffix: str, *, priority: int = 0, lat: float = 51.1, lon: float = 17.0,
             status: str = "approved", resolution: str = "active") -> str:
        photo_id = f"photo_20261101T090000Z_{suffix}"
        folder = self.storage / photo_id
        folder.mkdir()
        (folder / "public.jpg").write_bytes(b"public-fixture")
        (folder / "thumb.jpg").write_bytes(b"thumb-fixture")
        with self.connection:
            self.connection.execute(
                """INSERT INTO field_photos
                    (id, created_at, issue_type, lat, lon, coordinate_source,
                     public_review_status, vehicle_resolution_status, vehicle_gallery_priority,
                     original_filename, content_type, format, size_bytes, public_image_file, public_thumb_file)
                   VALUES (?, '2026-11-01T09:00:00Z', 'vehicle', ?, ?, 'map', ?, ?, ?,
                           'test.jpg', 'image/jpeg', 'JPEG', 20, 'public.jpg', 'thumb.jpg')""",
                (photo_id, lat, lon, status, resolution, priority),
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
            record, self.storage / second, self.storage, self.private, vehicle_gallery_priority=3,
        )
        self.assertEqual(result["photo"]["vehicle_gallery_priority"], 3)
        self.assertEqual(load_field_record_by_id(first, self.storage)["vehicle_gallery_priority"], 0)
        self.assertEqual(load_field_record_by_id(second, self.storage)["vehicle_gallery_priority"], 3)
        review_field_photo_record(
            load_field_record_by_id(second, self.storage),
            self.storage / second, self.storage, self.private, vehicle_resolution_status="removed",
        )
        self.assertEqual(load_field_record_by_id(second, self.storage)["vehicle_gallery_priority"], 0)
        self.assertEqual(list_map_vehicle_gallery(self.storage, bounds=(16, 50, 18, 52)), [])

    def test_pending_cannot_be_nominated(self) -> None:
        photo_id = self.seed("dddddddd", status="pending")
        with self.assertRaises(ValueError):
            review_field_photo_record(
                load_field_record_by_id(photo_id, self.storage),
                self.storage / photo_id, self.storage, self.private, vehicle_gallery_priority=1,
            )


if __name__ == "__main__":
    unittest.main()
