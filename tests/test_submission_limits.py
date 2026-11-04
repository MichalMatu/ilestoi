import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.database import migrate_json_to_database
from core.field_photo_store import connection_for
from core.submission_limits import pending_submission_usage


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class PendingSubmissionLimitTests(unittest.TestCase):
    def test_counts_only_pending_items_for_owner(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_dir = root / "prywatne_zdjecia"
            field_dir = root / "zdjecia_terenowe"
            (private_dir / "field_photos/pending/original.jpg").parent.mkdir(parents=True)
            (private_dir / "field_photos/pending/original.jpg").write_bytes(b"a" * 10)
            (private_dir / "field_photos/rejected/original.jpg").parent.mkdir(parents=True)
            (private_dir / "field_photos/rejected/original.jpg").write_bytes(b"b" * 20)
            write_json(
                field_dir / "photo_20260704T080000Z_11111111" / "record.json",
                {
                    "id": "photo_20260704T080000Z_11111111",
                    "created_at": "2026-07-04T08:00:00Z",
                    "original_filename": "pending.jpg",
                    "content_type": "image/jpeg",
                    "format": "JPEG",
                    "size_bytes": 10,
                    "image_width": 10,
                    "image_height": 8,
                    "issue_type": "vehicle",
                    "lat": 51.1,
                    "lon": 17.2,
                    "coordinate_source": "map",
                    "public_review_status": "pending",
                    "submission_owner": "public:a",
                    "private_original_file": "field_photos/pending/original.jpg",
                    "redactions": [],
                    "links": {},
                },
            )
            write_json(
                field_dir / "photo_20260704T080001Z_22222222" / "record.json",
                {
                    "id": "photo_20260704T080001Z_22222222",
                    "created_at": "2026-07-04T08:00:01Z",
                    "original_filename": "rejected.jpg",
                    "content_type": "image/jpeg",
                    "format": "JPEG",
                    "size_bytes": 20,
                    "image_width": 10,
                    "image_height": 8,
                    "issue_type": "vehicle",
                    "lat": 51.1,
                    "lon": 17.2,
                    "coordinate_source": "map",
                    "public_review_status": "rejected",
                    "submission_owner": "public:a",
                    "private_original_file": "field_photos/rejected/original.jpg",
                    "redactions": [],
                    "links": {},
                },
            )
            migrate_json_to_database(root_dir=root, database_path=root / "wreckscanner.sqlite3", require_backup=False)

            usage = pending_submission_usage(
                owner="public:a",
                field_photos_dir=field_dir,
                private_dir=private_dir,
            )

            self.assertEqual(usage["items"], 1)
            self.assertEqual(usage["bytes"], 10)


    def test_uses_read_only_sqlite_projection_for_drafts_and_pending(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_dir = root / "prywatne_zdjecia"
            field_dir = root / "zdjecia_terenowe"
            private_dir.mkdir()
            field_dir.mkdir()

            for filename, payload in (("draft.jpg", b"a" * 5), ("other.jpg", b"b" * 9)):
                (private_dir / filename).write_bytes(payload)

            rows = [
                ("pending", "public:a", "draft.jpg"),
                ("draft", " public:a ", "missing.jpg"),
                ("pending", "public:b", "other.jpg"),
                ("approved", "public:a", "other.jpg"),
                ("rejected", "public:a", "other.jpg"),
            ]
            conn = connection_for(field_dir)
            try:
                with conn:
                    for index, (status, owner, original) in enumerate(rows):
                        conn.execute(
                            """INSERT INTO field_photos (
                                id, created_at, issue_type, lat, lon, coordinate_source,
                                public_review_status, original_filename, content_type,
                                format, size_bytes, submission_owner, private_original_file
                            ) VALUES (?, ?, 'vehicle', 51.1, 17.2, 'map', ?, 'source.jpg',
                                      'image/jpeg', 'JPEG', 1, ?, ?)""",
                            (
                                f"photo_20261104T010101Z_{index:08x}",
                                "2026-11-04T01:01:01Z",
                                status,
                                owner,
                                original,
                            ),
                        )
            finally:
                conn.close()

            # No record.json or public derivative files exist; this path must not
            # load full photo records, repair files or write to the database.
            owned = pending_submission_usage(owner="public:a", field_photos_dir=field_dir, private_dir=private_dir)
            everyone = pending_submission_usage(owner=None, field_photos_dir=field_dir, private_dir=private_dir)
            injected = pending_submission_usage(
                owner="public:a' OR '1'='1", field_photos_dir=field_dir, private_dir=private_dir
            )

            self.assertEqual((owned["items"], owned["bytes"]), (2, 5))
            self.assertEqual((everyone["items"], everyone["bytes"]), (3, 14))
            self.assertEqual((injected["items"], injected["bytes"]), (0, 0))
            self.assertEqual(list(field_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
