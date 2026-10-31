import unittest

from core.report_mail import build_mail_draft


class ReportMailTests(unittest.TestCase):
    def test_build_mail_draft_includes_evidence_labels_without_technical_noise(self):
        subject, body = build_mail_draft(
            {
                "id": "wreck_51100000_17200000",
                "lat": 51.1,
                "lon": 17.2,
                "links": {"street_view": "https://example.test/street"},
                "vehicle_insurance_status": "uninsured",
                "vehicle_insurance_checked_at": "2026-07-05T12:30:00Z",
                "report_history": [
                    {
                        "created_at": "2026-06-01T10:00:00Z",
                        "report_id": "report_20260601T100000Z_deadbeef",
                        "public": True,
                    }
                ],
            },
            {"labels_present": ["2024", "2025"]},
            {
                "reporter_name": "Jan Kowalski",
                "reporter_address": "ul. Testowa 1, Wrocław",
                "reporter_phone": "500 600 700",
                "reporter_email": "jan@example.com",
                "location_description": "ul. Długa 10, parking przy szkole",
                "observed_at": "2026-06-02T12:30",
                "vehicle_description": "Pojazd zabrudzony, długo stoi w tym samym miejscu.",
            },
        )

        self.assertEqual(subject, "Zgłoszenie pojazdu nieużytkowanego - ul. Długa 10, parking przy szkole")
        self.assertTrue(body.startswith("Zgłaszam pojazd"))
        self.assertNotIn("Dzień dobry", body)
        self.assertNotIn("Dane zgłaszającego", body)
        self.assertNotIn("- Imię i nazwisko: Jan Kowalski", body)
        self.assertIn("Adres zamieszkania: ul. Testowa 1, Wrocław", body)
        self.assertIn("E-mail: jan@example.com", body)
        self.assertIn("Telefon: 500 600 700", body)
        self.assertNotIn("- E-mail: jan@example.com", body)
        self.assertNotIn("- Telefon: 500 600 700", body)
        self.assertIn("02.06.2026, godz. 12:30", body)
        self.assertNotIn("2026-06-02T12:30", body)
        self.assertIn("może spełniać przesłanki z art. 50a ust. 1", body)
        self.assertIn("Informacja pomocnicza o OC", body)
        self.assertIn("- Ręczne sprawdzenie w UFG: brak OC", body)
        self.assertIn("- Data sprawdzenia w UFG: 05.07.2026, godz. 14:30", body)
        self.assertIn("Proszę potraktować tę informację pomocniczo", body)
        self.assertIn("Załączniki:", body)
        self.assertIn("- zdjęcia z miejsca", body)
        self.assertIn("- materiał pomocniczy z miniaturami historycznymi ortofoto z lat: 2024, 2025", body)
        self.assertIn("nie zastępują oględzin w terenie", body)
        self.assertIn("przekazanie zgłoszenia właściwej jednostce", body)
        self.assertIn("właściwego zarządcy/podmiotu", body)
        self.assertNotIn("Zakres oczekiwanej odpowiedzi", body)
        self.assertNotIn("art. 241 Kodeksu postępowania administracyjnego", body)
        self.assertNotIn("art. 237 § 1 oraz art. 244 § 1 i § 2", body)
        self.assertNotIn("Źródła prawne i pomocnicze", body)
        self.assertNotIn("pakiet dowodowy ZIP", body)
        self.assertNotIn("Historia działań", body)
        self.assertNotIn("report_20260601T100000Z_deadbeef", body)
        self.assertNotIn("lokalna sprawa", body)
        self.assertNotIn("wreck_51100000_17200000", body)
        self.assertNotIn("Linki do weryfikacji", body)
        self.assertNotIn("Street View", body)
        self.assertNotIn("https://example.test/street", body)

    def test_build_mail_draft_shortens_subject_at_word_boundary(self):
        subject, body = build_mail_draft(
            {
                "id": "wreck_51100000_17200000",
                "lat": 51.1,
                "lon": 17.2,
                "links": {},
                "parcel": {
                    "parcel_number": "87",
                    "parcel_id": "026401_1.0022.AR_27.87",
                    "district": "Południe",
                    "municipality": "Wrocław",
                    "county": "Wrocław",
                    "voivodeship": "dolnośląskie",
                    "contour": "B",
                    "published_at": "2026-06-05",
                },
            },
            {"labels_present": []},
            {
                "reporter_name": "Jan Kowalski",
                "reporter_address": "ul. Testowa 1, Wrocław",
                "reporter_phone": "500 600 700",
                "reporter_email": "jan@example.com",
                "location_description": (
                    "Pojazd stoi przy wewnętrznym ciągu komunikacyjnym obok parkingu "
                    "osiedlowego, w bezpośrednim sąsiedztwie przejścia dla pieszych"
                ),
                "observed_at": "2026-06-02T12:30",
                "vehicle_description": "Pojazd długo stoi w tym samym miejscu.",
            },
        )

        location_part = subject.removeprefix("Zgłoszenie pojazdu nieużytkowanego - ")
        self.assertLessEqual(len(location_part), 90)
        self.assertTrue(location_part.endswith("..."))
        self.assertIn("parkingu osiedlowego...", location_part)
        self.assertNotIn(" w...", location_part)
        self.assertNotIn("bezpośredni...", location_part)

        self.assertIn("Teren według ewidencji gruntów (pomocniczo)", body)
        self.assertIn(
            "Teren według ewidencji gruntów (pomocniczo): B - tereny mieszkaniowe (działka 87).",
            body,
        )
        self.assertNotIn("026401_1.0022.AR_27.87", body)
        self.assertNotIn("Obręb:", body)
        self.assertNotIn("Powiat:", body)
        self.assertNotIn("Województwo:", body)
        self.assertNotIn("proszę jednak o Państwa własną ocenę", body)
        self.assertNotIn("na drodze publicznej, w strefie zamieszkania albo w strefie ruchu", body)

    def test_build_mail_draft_uses_nearest_address_when_available(self):
        subject, body = build_mail_draft(
            {
                "id": "wreck_51087994_17039629",
                "lat": 51.087994,
                "lon": 17.039629,
                "links": {},
                "address": {
                    "formatted": "ul. św. Jerzego 11, 50-518, Wrocław",
                    "source_label": "PRG/GUGiK",
                    "distance_m": "26",
                },
            },
            {"labels_present": ["2024", "2025"]},
            {
                "reporter_name": "Jan Kowalski",
                "reporter_address": "ul. Testowa 1, Wrocław",
                "reporter_phone": "500 600 700",
                "reporter_email": "jan@example.com",
                "location_description": (
                    "Miejsce wskazane na mapie przy współrzędnych GPS 51.087994, 17.039629. "
                    "Pojazd znajduje się w lokalizacji widocznej na załączonych zdjęciach."
                ),
                "observed_at": "2026-06-02T12:30",
                "vehicle_description": "Pojazd długo stoi w tym samym miejscu.",
            },
        )

        self.assertEqual(
            subject,
            "Zgłoszenie pojazdu nieużytkowanego - ul. św. Jerzego 11, 50-518, Wrocław",
        )
        self.assertIn(
            "Najbliższy adres według PRG/GUGiK: ul. św. Jerzego 11, 50-518, Wrocław (ok. 26 m od wskazanego punktu).",
            body,
        )
        self.assertNotIn("Miejsce wskazane na mapie przy współrzędnych GPS", body)
        self.assertNotIn("Pojazd znajduje się w lokalizacji widocznej na załączonych zdjęciach", body)
        self.assertIn(
            "Miejsce pojazdu:\n"
            "Najbliższy adres według PRG/GUGiK: ul. św. Jerzego 11, 50-518, Wrocław "
            "(ok. 26 m od wskazanego punktu).\n\n"
            "Współrzędne GPS:",
            body,
        )
        self.assertIn("Współrzędne GPS:\n51.087994, 17.039629", body)

    def test_build_mail_draft_preserves_prefilled_address_when_backend_address_differs(self):
        _subject, body = build_mail_draft(
            {
                "id": "wreck_51087994_17039629",
                "lat": 51.087994,
                "lon": 17.039629,
                "links": {},
                "address": {
                    "formatted": "Świętego Jerzego, 50-518, Wrocław",
                    "source_label": "OpenStreetMap/Nominatim",
                    "distance_m": "93",
                },
            },
            {"labels_present": ["2024", "2025"]},
            {
                "reporter_name": "Jan Kowalski",
                "reporter_address": "ul. Testowa 1, Wrocław",
                "reporter_phone": "500 600 700",
                "reporter_email": "jan@example.com",
                "location_description": "Najbliższy adres: ul. św. Jerzego 11, 50-518, Wrocław.",
                "observed_at": "2026-06-02T12:30",
                "vehicle_description": "Pojazd długo stoi w tym samym miejscu.",
            },
        )

        self.assertIn("Najbliższy adres: ul. św. Jerzego 11, 50-518, Wrocław.", body)
        self.assertNotIn("OpenStreetMap/Nominatim", body)
        self.assertNotIn("Świętego Jerzego, 50-518, Wrocław", body)

    def test_build_mail_draft_omits_insurance_check_date_when_status_is_unknown(self):
        _subject, body = build_mail_draft(
            {
                "id": "wreck_51100000_17200000",
                "lat": 51.1,
                "lon": 17.2,
                "links": {},
                "vehicle_insurance_status": "unknown",
                "vehicle_insurance_checked_at": None,
            },
            {"labels_present": []},
            {
                "reporter_name": "Jan Kowalski",
                "reporter_address": "ul. Testowa 1, Wrocław",
                "reporter_phone": "500 600 700",
                "reporter_email": "jan@example.com",
                "location_description": "ul. Długa 10, parking przy szkole",
                "observed_at": "2026-06-02T12:30",
                "vehicle_description": "Pojazd długo stoi w tym samym miejscu.",
            },
        )

        self.assertNotIn("Informacja pomocnicza o OC", body)
        self.assertNotIn("Ręczne sprawdzenie w UFG", body)
        self.assertNotIn("Data sprawdzenia w UFG", body)


if __name__ == "__main__":
    unittest.main()
