import base64
import io
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

import core.report_pdf as report_pdf
from app.http import public as http_public
from app.http.public import reject_report_pdf_files
from core.database import migrate_json_to_database
from core.report_assets import report_pdf_download_name
from core.report_models import validate_report_fields
from core.report_pdfs import create_field_photo_report_pdf, validate_field_photo_report_selection
from core.uploads import UploadedFile


def image_bytes(fmt: str = "JPEG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (32, 24), (120, 80, 40)).save(out, fmt)
    return out.getvalue()


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def valid_fields() -> dict[str, str]:
    return {
        "reporter_name": "Jan Kowalski",
        "reporter_address": "ul. Testowa 1, Wrocław",
        "reporter_phone": "500 600 700",
        "reporter_email": "jan@example.com",
        "location_description": "ul. Długa 10, przy parkingu",
        "observed_at": "2026-06-02T12:30",
        "vehicle_description": "Pojazd zabrudzony, długo stoi w tym samym miejscu.",
    }


def fake_save_location_crops(lat: float, lon: float, output_dir: Path, **kwargs):
    output_dir.mkdir(parents=True, exist_ok=True)
    for year in (2024, 2025):
        (output_dir / f"{year}.jpg").write_bytes(image_bytes())
    crop_m = float(kwargs.get("crop_m", 7.5))
    return (
        [{"label": "2024", "file": "2024.jpg"}, {"label": "2025", "file": "2025.jpg"}],
        {
            "center_lat": lat,
            "center_lon": lon,
            "crop_meters": crop_m,
            "years": [2024, 2025],
            "source": "wroclaw_wms_location_crops",
        },
    )


def create_field_photo_fixture(
    root: Path,
    *,
    photo_id: str = "photo_20260604T201000Z_11111111",
    lat: float = 51.1,
    lon: float = 17.2,
    issue_type: str = "vehicle",
    status: str = "approved",
    vehicle_insurance_status: str = "insured",
    vehicle_resolution_status: str = "active",
) -> tuple[Path, str]:
    field_dir = root / "zdjecia_terenowe"
    photo_dir = field_dir / photo_id
    photo_dir.mkdir(parents=True, exist_ok=True)
    (photo_dir / "public.jpg").write_bytes(image_bytes())
    (photo_dir / "public_thumb.jpg").write_bytes(image_bytes())
    private_rel = f"field_photos/{photo_id}/original.jpg"
    (root / "prywatne_zdjecia" / private_rel).parent.mkdir(parents=True, exist_ok=True)
    (root / "prywatne_zdjecia" / private_rel).write_bytes(image_bytes())
    write_json(
        photo_dir / "record.json",
        {
            "id": photo_id,
            "created_at": "2026-06-04T20:10:00Z",
            "original_filename": "teren.jpg",
            "content_type": "image/jpeg",
            "format": "JPEG",
            "size_bytes": len(image_bytes()),
            "image_width": 32,
            "image_height": 24,
            "issue_type": issue_type,
            "vehicle_insurance_status": (vehicle_insurance_status if issue_type == "vehicle" else "unknown"),
            "vehicle_insurance_checked_at": (
                "2026-07-05T12:30:00Z" if issue_type == "vehicle" and vehicle_insurance_status != "unknown" else None
            ),
            "vehicle_resolution_status": (vehicle_resolution_status if issue_type == "vehicle" else "active"),
            "vehicle_resolution_updated_at": (
                "2026-07-05T12:35:00Z" if issue_type == "vehicle" and vehicle_resolution_status == "removed" else None
            ),
            "lat": lat,
            "lon": lon,
            "coordinate_source": "map",
            "captured_at": "2026-06-04T20:00:00",
            "private_original_file": private_rel,
            "public_review_status": status,
            "redactions": [],
            "reviewed_at": "2026-06-04T20:12:00Z" if status == "approved" else None,
            "public_image_file": "public.jpg",
            "public_thumb_file": "public_thumb.jpg",
            "public_width": 32,
            "public_height": 24,
            "links": {},
        },
    )
    migrate_json_to_database(root_dir=root, database_path=root / "wreckscanner.sqlite3", require_backup=False)
    return field_dir, photo_id


class ReportPdfTests(unittest.TestCase):
    def test_http_photo_id_lists_reject_oversized_raw_inputs_before_deduplication(self):
        too_many = ["photo_20260604T201000Z_11111111"] * (http_public.core_config.MAX_OWNER_PHOTO_IDS + 1)

        with self.assertRaisesRegex(ValueError, "maksymalnie"):
            http_public._owner_photo_ids({"photo_ids": too_many})
        with self.assertRaisesRegex(ValueError, "maksymalnie"):
            http_public._report_photo_ids({"photo_ids": json.dumps(too_many)})

    def test_report_pdf_download_name_uses_readable_timestamp(self):
        self.assertEqual(
            report_pdf_download_name("report_20260702T142516Z_0b05a053"),
            "raport_20260702_142516.pdf",
        )
        with self.assertRaisesRegex(ValueError, "identyfikator"):
            report_pdf_download_name("bad")

    def test_validate_report_fields_requires_clean_email_and_short_values(self):
        fields = valid_fields()
        fields["reporter_name"] = "  Jan\x00 Kowalski  "

        validated = validate_report_fields(fields)

        self.assertEqual(validated["reporter_name"], "Jan Kowalski")

        with self.assertRaisesRegex(ValueError, "adres e-mail"):
            validate_report_fields({**valid_fields(), "reporter_email": "jan.example.com"})

        with self.assertRaisesRegex(ValueError, "wymagane pola"):
            validate_report_fields({**valid_fields(), "reporter_phone": ""})

        with self.assertRaisesRegex(ValueError, "zbyt długie"):
            validate_report_fields({**valid_fields(), "vehicle_description": "x" * 4001})

        with self.assertRaisesRegex(ValueError, "tekst zastępczy"):
            validate_report_fields({
                **valid_fields(),
                "reporter_address": "[UZUPEŁNIJ PRZED WYSŁANIEM]",
            })

        with self.assertRaisesRegex(ValueError, "prawidłową datę"):
            validate_report_fields({**valid_fields(), "observed_at": "2026-13-40T88:99"})

        with self.assertRaisesRegex(ValueError, "z przyszłości"):
            validate_report_fields({**valid_fields(), "observed_at": "2099-01-01T12:00"})

    def test_reject_report_pdf_files_rejects_uploaded_files(self):
        with self.assertRaisesRegex(ValueError, "zatwierdzonych zdjęć terenowych"):
            reject_report_pdf_files([UploadedFile("photos", "car.jpg", "image/jpeg", b"x")])

        reject_report_pdf_files([])

    def test_report_cadastral_context_is_best_effort(self):
        with patch("app.http.public.lookup_cadastral_parcel", return_value={"parcel_number": "87"}):
            parcel, error = http_public._report_cadastral_context("51.1", "17.2")

        self.assertEqual(parcel, {"parcel_number": "87"})
        self.assertEqual(error, "")

        with patch("app.http.public.lookup_cadastral_parcel", side_effect=RuntimeError("upstream")):
            parcel, error = http_public._report_cadastral_context("51.1", "17.2")

        self.assertIsNone(parcel)
        self.assertIn("automatycznie pobrać", error)

    def test_report_address_context_is_best_effort(self):
        with patch("app.http.public.lookup_nearest_address", return_value={"formatted": "ul. Testowa 1"}):
            address = http_public._report_address_context("51.1", "17.2")

        self.assertEqual(address, {"formatted": "ul. Testowa 1"})

        with patch("app.http.public.lookup_nearest_address", side_effect=RuntimeError("upstream")):
            address = http_public._report_address_context("51.1", "17.2")

        self.assertIsNone(address)

    def test_create_field_photo_report_pdf_uses_field_photo_group_without_archived_case(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            field_dir, photo_id = create_field_photo_fixture(root)
            parcel = {
                "parcel_number": "87",
                "parcel_id": "026401_1.0022.AR_27.87",
                "district": "Południe",
                "municipality": "Wrocław",
                "county": "Wrocław",
                "voivodeship": "dolnośląskie",
                "area_ha": "0.5964",
                "registry_group": "7.1",
                "contour": "B",
                "published_at": "2026-06-05",
            }

            with patch("core.report_evidence.save_location_crops", side_effect=fake_save_location_crops):
                result = create_field_photo_report_pdf(
                    valid_fields(),
                    [photo_id],
                    lat=51.1,
                    lon=17.2,
                    parcel=parcel,
                    address={"formatted": "ul. Testowa 1, 50-000, Wrocław", "source_label": "PRG/GUGiK"},
                    field_photos_dir=field_dir,
                )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["photo_count"], 1)
            self.assertEqual(result["pdf_filename"], report_pdf_download_name(result["report_id"]))
            self.assertEqual(
                result["subject"],
                "Zgłoszenie pojazdu nieużytkowanego - ul. Testowa 1, 50-000, Wrocław",
            )
            self.assertNotIn("body", result)
            self.assertNotIn("zip_filename", result)
            self.assertNotIn("zip_base64", result)
            self.assertNotIn("zip_size_bytes", result)
            self.assertNotIn("zip_url", result)
            self.assertNotIn("pdf_url", result)
            pdf_bytes = base64.b64decode(result["pdf_base64"])
            self.assertEqual(pdf_bytes[:5], b"%PDF-")
            self.assertGreater(result["pdf_size_bytes"], 1000)
            self.assertFalse((root / "zidentyfikowane_wraki").exists())

    def test_create_field_photo_report_pdf_requires_approved_vehicle_photos(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            field_dir, photo_id = create_field_photo_fixture(root, status="pending")

            with self.assertRaisesRegex(ValueError, "zatwierdzonych"):
                create_field_photo_report_pdf(
                    valid_fields(), [photo_id], lat=51.1, lon=17.2, field_photos_dir=field_dir
                )

            field_dir, photo_id = create_field_photo_fixture(root, issue_type="smoke")
            with self.assertRaisesRegex(ValueError, "pojazdów"):
                create_field_photo_report_pdf(
                    valid_fields(), [photo_id], lat=51.1, lon=17.2, field_photos_dir=field_dir
                )

    def test_create_field_photo_report_pdf_requires_active_vehicle_group(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            field_dir, photo_id = create_field_photo_fixture(root, vehicle_resolution_status="removed")

            with self.assertRaisesRegex(ValueError, "aktywnego pojazdu"):
                create_field_photo_report_pdf(
                    valid_fields(), [photo_id], lat=51.1, lon=17.2, field_photos_dir=field_dir
                )

    def test_report_selection_rejects_client_coordinates_outside_photo_group(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            field_dir, photo_id = create_field_photo_fixture(root)

            with self.assertRaisesRegex(ValueError, "nie odpowiadają"):
                validate_field_photo_report_selection(
                    [photo_id], lat=-33.8688, lon=151.2093, field_photos_dir=field_dir
                )

    def test_report_selection_rejects_cross_group_and_removed_photos(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            field_dir, first_id = create_field_photo_fixture(root)
            _, second_id = create_field_photo_fixture(
                root,
                photo_id="photo_20260604T202000Z_22222222",
                lat=51.2,
                lon=17.3,
            )

            with self.assertRaisesRegex(ValueError, "tej samej grupy"):
                validate_field_photo_report_selection(
                    [first_id, second_id], lat=51.1, lon=17.2, field_photos_dir=field_dir
                )

            _, removed_id = create_field_photo_fixture(
                root,
                photo_id="photo_20260604T203000Z_33333333",
                lat=51.100001,
                lon=17.200001,
                vehicle_resolution_status="removed",
            )
            with self.assertRaisesRegex(ValueError, "aktywnego pojazdu"):
                validate_field_photo_report_selection(
                    [first_id, removed_id], lat=51.1, lon=17.2, field_photos_dir=field_dir
                )

    def test_report_selection_enforces_count_and_public_size_limits(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            field_dir, photo_id = create_field_photo_fixture(root)

            with self.assertRaisesRegex(ValueError, "maksymalnie"):
                validate_field_photo_report_selection([photo_id] * 26, lat=51.1, lon=17.2, field_photos_dir=field_dir)

            with (
                patch("core.report_pdfs.config.MAX_REPORT_PUBLIC_PHOTO_BYTES", 1),
                self.assertRaisesRegex(ValueError, "rozmiar zdjęć"),
            ):
                validate_field_photo_report_selection([photo_id], lat=51.1, lon=17.2, field_photos_dir=field_dir)

    def test_report_selection_rejects_non_finite_coordinates(self):
        with TemporaryDirectory() as tmp:
            field_dir, photo_id = create_field_photo_fixture(Path(tmp))

            with self.assertRaisesRegex(ValueError, "lat"):
                validate_field_photo_report_selection([photo_id], lat="nan", lon=17.2, field_photos_dir=field_dir)

    def test_create_field_photo_report_pdf_handles_unknown_insurance_status(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            field_dir, photo_id = create_field_photo_fixture(root, vehicle_insurance_status="unknown")

            with patch("core.report_evidence.save_location_crops", side_effect=fake_save_location_crops):
                result = create_field_photo_report_pdf(
                    valid_fields(), [photo_id], lat=51.1, lon=17.2, field_photos_dir=field_dir
                )

            pdf_bytes = base64.b64decode(result["pdf_base64"])
            self.assertEqual(pdf_bytes[:5], b"%PDF-")

    def test_report_pdf_starts_with_formal_letter_before_evidence(self):
        with TemporaryDirectory() as tmp:
            record_dir = Path(tmp)
            pdf_bytes = report_pdf.build_report_pdf(
                record={
                    "id": "field_photo_group_test",
                    "status": "field_photo_group",
                    "lat": 51.1,
                    "lon": 17.2,
                    "labels_present": ["2024", "2025"],
                    "first_seen_year": 2024,
                    "last_seen_year": 2025,
                    "links": {},
                    "attached_photos": [],
                },
                evidence={
                    "id": "report_test",
                    "labels_present": ["2024", "2025"],
                    "path": "evidence/report_test",
                    "crops": [],
                    "links": {},
                },
                record_dir=record_dir,
                evidence_base_dir=record_dir,
                recipient="interwencje@example.test",
                reporter={
                    "reporter_name": "Jan Kowalski",
                    "reporter_address": "ul. Testowa 1, Wrocław",
                    "reporter_email": "jan@example.com",
                    "reporter_phone": "500 600 700",
                },
                subject="Zgłoszenie",
                mail_body="Treść zgłoszenia",
            )

        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))

    def test_termux_font_directory_is_discovered(self):
        with TemporaryDirectory() as tmp:
            fonts = Path(tmp) / "share/fonts/TTF"
            fonts.mkdir(parents=True)
            regular = fonts / "DejaVuSans.ttf"
            bold = fonts / "DejaVuSans-Bold.ttf"
            regular.write_bytes(b"test-regular")
            bold.write_bytes(b"test-bold")
            with patch.dict(os.environ, {"PREFIX": tmp}):
                self.assertEqual(report_pdf._font_path(), regular)
                self.assertEqual(report_pdf._font_path(bold=True), bold)

    def test_missing_unicode_fonts_fail_closed(self):
        with (
            patch.object(report_pdf.pdfmetrics, "getRegisteredFontNames", return_value=[]),
            patch.object(report_pdf, "_font_path", return_value=None),
            self.assertRaisesRegex(RuntimeError, "Brak czcionek TrueType"),
        ):
            report_pdf._font_name()

    def test_report_embeds_unicode_fonts_for_polish_text(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_bytes = report_pdf.build_report_pdf(
                record={"attached_photos": []},
                evidence={"crops": []},
                record_dir=root,
                evidence_base_dir=root,
                recipient="interwencje@example.test",
                reporter={"reporter_name": "Żaneta Łącka", "reporter_address": "Wrocław, Łąkowa 3"},
                subject="Zgłoszenie",
                mail_body="Zażółć gęślą jaźń. ĄĆĘŁŃÓŚŹŻ ąćęłńóśźż.",
            )
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertIn(b"/FontFile2", pdf_bytes)
        self.assertIn(b"/ToUnicode", pdf_bytes)
        self.assertEqual(report_pdf._font_name(), report_pdf.FONT_REGULAR)
        self.assertEqual(report_pdf._font_name(bold=True), report_pdf.FONT_BOLD)


if __name__ == "__main__":
    unittest.main()
