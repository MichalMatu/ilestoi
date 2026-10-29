import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class DocumentationContractTests(unittest.TestCase):
    def test_readme_documents_current_production_flow_and_essential_docs(self):
        readme = (ROOT_DIR / "README.md").read_text(encoding="utf-8")

        # The current release baseline is the exact deployed commit on main,
        # not the retired long-lived development branch or the historical v4.0.
        self.assertIn("Aktualna linia produkcyjna: `main`", readme)
        self.assertIn("`main` odzwierciedla **zaakceptowaną wersję produkcyjną**", readme)
        self.assertIn("`feature/*` / `fix/*`", readme)
        self.assertIn("Nie używamy trwałej gałęzi `work/dirty`", readme)
        self.assertNotIn("`work/dirty` jest galezia robocza", readme)
        self.assertIn("Status projektu: wersja utrzymaniowa.", readme)
        for path in (
            "docs/START.md", "docs/CURRENT_MODEL.md", "docs/DATABASE.md",
            "docs/BACKUP.md", "docs/DEPLOY.md", "docs/TERMUX.md",
            "docs/TERMUX_DEVELOPMENT_FLOW.md",
        ):
            self.assertIn(path, readme)
        self.assertIn("Python `3.11-3.13`", readme)
        self.assertIn("OC/UFG", readme)
        self.assertIn("raport PDF z OC/UFG", readme)
        self.assertIn("szyfrowany backup", readme)
        self.assertIn("backup/restore", readme)
        self.assertIn("scripts/check.sh", readme)
        self.assertNotIn("raport ZIP/PDF", readme)
        self.assertNotIn("docs/AUDIT.md", readme)
        self.assertNotIn("docs/README.en.md", readme)
        self.assertNotIn("RUNTIME_SMOKE", readme)
        self.assertNotIn("ROADMAP", readme.upper())

    def test_start_doc_has_runtime_admin_and_smoke_basics(self):
        doc = (ROOT_DIR / "docs" / "START.md").read_text(encoding="utf-8")

        self.assertIn("./.venv/bin/python server.py", doc)
        self.assertIn("make restart", doc)
        self.assertIn("WRECKSCANNER_ADMIN_PASSWORD", doc)
        self.assertIn("ma pierwszenstwo przed plikiem `.admin_password`", doc)
        self.assertIn("scripts/check.sh", doc)
        self.assertIn("make smoke", doc)
        self.assertIn("make e2e-report", doc)
        self.assertIn("statusem OC/UFG", doc)
        self.assertIn("Python `3.11-3.13`", doc)
        self.assertIn("jedynym supervisorem jest `wreckscanner.service`", doc)
        self.assertIn("nie uruchamia", doc)
        self.assertIn("drugiej instancji `server.py`", doc)
        self.assertIn("/api/health/live", doc)
        self.assertIn("/api/health/ready", doc)
        self.assertIn("BACKUP.md", doc)
        self.assertIn("DEPLOY.md", doc)

    def test_deploy_doc_has_production_secret_and_verification_checklist(self):
        doc = (ROOT_DIR / "docs" / "DEPLOY.md").read_text(encoding="utf-8")

        self.assertIn("WRECKSCANNER_ADMIN_PASSWORD", doc)
        self.assertIn("WRECKSCANNER_ADMIN_SESSION_SECRET", doc)
        self.assertIn("WRECKSCANNER_CORS_ALLOWED_ORIGINS", doc)
        self.assertIn("systemctl enable --now wreckscanner.service", doc)
        self.assertIn("./scripts/check.sh", doc)
        self.assertIn("scripts/backup_data.py run", doc)
        self.assertIn("git describe --exact-match --tags HEAD", doc)
        self.assertIn("scripts/migrate_json_to_db.py --validate-only", doc)
        self.assertIn("historyczne JSON-y nie sa zrodlem prawdy", doc)
        self.assertIn("/api/health/live", doc)
        self.assertIn("/api/health/ready", doc)
        self.assertIn("make smoke", doc)
        self.assertIn("make e2e-report", doc)
        self.assertIn("Rollback", doc)

    def test_public_runtime_validates_cloudflare_ingress_before_restart(self):
        doc = (ROOT_DIR / "docs" / "PUBLIC_RUNTIME.md").read_text(encoding="utf-8")

        validate = "cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate"
        restart = "sudo systemctl restart cloudflared.service"
        self.assertIn(validate, doc)
        self.assertIn(restart, doc)
        self.assertLess(doc.index(validate), doc.index(restart))
        self.assertIn("www.wreckscanner.pl", doc)
        self.assertIn("www.ilestoi.pl", doc)
        self.assertIn("www.dlugostoi.pl", doc)
        self.assertNotIn("3b59bac9-6bb6-47bf-a532-6e44caa9855b", doc)

    def test_backup_doc_has_restore_validation_commands(self):
        doc = (ROOT_DIR / "docs" / "BACKUP.md").read_text(encoding="utf-8")

        self.assertIn("restic restore latest --target /tmp/wreckscanner-restore-test", doc)
        self.assertIn("scripts/diagnose_data.py --strict", doc)
        self.assertIn("--field-photos-dir /tmp/wreckscanner-restore-test/zdjecia_terenowe", doc)
        self.assertIn("scripts/migrate_json_to_db.py", doc)
        self.assertIn("--validate-only", doc)
        self.assertIn("wreckscanner-data-snapshot-v2", doc)
        self.assertIn("--include-secrets", doc)
        self.assertIn("--restore-secrets", doc)
        self.assertIn("sekrety z archiwum nie sa odtwarzane", doc)
        self.assertIn("nie ukrywa bledu ponownego startu", doc)
        self.assertIn("RPO: najwyzej 24 godziny", doc)
        self.assertIn("RTO: przywrocenie sprawdzonej uslugi w 4 godziny", doc)
        self.assertIn("wreckscanner-backup.timer", doc)
        self.assertIn("Persistent=true", doc)
        self.assertIn("--keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune", doc)
        self.assertIn("najnowszy snapshot ma ponad 26 godzin", doc)
        self.assertIn("kopii off-host", doc)
        self.assertIn("Prosty Tryb Dla Tego Projektu", doc)
        self.assertIn("make backup-restic", doc)
        self.assertIn("make list-restic", doc)
        self.assertIn("make check-restic", doc)
        self.assertIn("Restic zapisuje zmiany przyrostowo i deduplikuje", doc)
        self.assertIn("systemctl --user enable --now wreckscanner-backup.timer", doc)
        self.assertIn("8 punktow tygodniowych i 6 miesiecznych", doc)
        self.assertNotIn("- `settings.json`", doc)
        self.assertNotIn("- `zgloszenia_prywatnosci/`", doc)

    def test_current_model_doc_names_active_flow_and_retired_artifact_audit(self):
        doc = (ROOT_DIR / "docs" / "CURRENT_MODEL.md").read_text(encoding="utf-8")
        normalized_doc = " ".join(doc.replace("`", "").replace("|", " ").split())

        self.assertIn("`wreckscanner.sqlite3` - aktywny stan aplikacji", doc)
        self.assertIn("`zdjecia_terenowe/` - publiczne pliki zdjec terenowych", doc)
        self.assertIn("Kazde zdjecie terenowe musi miec jawne `issue_type`", doc)
        self.assertIn("`vehicle_insurance_status`", doc)
        self.assertIn("`vehicle_insurance_checked_at`", doc)
        self.assertIn("`vehicle_resolution_status`", doc)
        self.assertIn("`vehicle_resolution_updated_at`", doc)
        self.assertIn("Aplikacja nie pobiera danych z UFG automatycznie", doc)
        self.assertIn("Zmiana OC/UFG w panelu admina aktualizuje wszystkie zdjecia pojazdu", doc)
        self.assertIn("usunieta tylko wtedy, gdy wszystkie", doc)
        self.assertIn("Publiczna mapa domyslnie ukrywa usuniete pojazdy", doc)
        self.assertIn("Zgloszenie PDF jest generowane", doc)
        self.assertIn("sprawdzenia w tresci PDF", doc)
        self.assertIn("nie jest generowane dla grupy oznaczonej w calosci jako", doc)
        self.assertIn("POST /api/field-photo-reports/report-pdf", normalized_doc)
        self.assertIn("moze zapisac sama decyzje", doc)
        self.assertIn("Raporty PDF i cropy mapy nie sa zapisywane w DB ani w stalym", doc)
        self.assertIn("Nie ma publicznego ani administracyjnego API `/api/wrecks`.", doc)
        self.assertIn("test ! -e zidentyfikowane_wraki", doc)
        self.assertIn("test ! -e prywatne_zgloszenia", doc)
        self.assertIn("scripts/migrate_json_to_db.py --validate-only", doc)
        self.assertIn("quick_check: ok", doc)
        self.assertIn("Historyczne", doc)
        self.assertIn("scripts/check.sh", doc)

        active_endpoints = (
            "GET /api/health/live",
            "GET /api/health/ready",
            "GET /api/settings",
            "POST /api/settings",
            "GET /api/admin/status",
            "POST /api/admin/login",
            "POST /api/admin/logout",
            "GET /api/field-photos",
            "GET /api/field-photos/:id/public-image",
            "GET /api/field-photos/:id/public-thumb",
            "POST /api/field-photos",
            "POST /api/field-photos/owner-claim",
            "POST /api/field-photos/owner-submit",
            "POST /api/field-photos/owner-discard",
            "POST /api/field-photos/owner-delete",
            "POST /api/field-photos/:id/owner-original",
            "PATCH /api/field-photos/:id/owner-review",
            "PATCH /api/field-photos/:id/location",
            "POST /api/field-photo-reports/report-pdf",
            "GET /api/address/reverse?lat=:lat&lon=:lon",
            "GET /api/cadastral/identify?lat=:lat&lon=:lon",
            "POST /api/inspect",
            "POST /api/privacy-requests",
            "GET /api/admin/photos",
            "GET /api/admin/photos/field/:id/original",
            "PATCH /api/admin/photos/field/:id/review",
            "DELETE /api/admin/photos/field/:id",
            "GET /api/admin/privacy-requests",
            "PATCH /api/admin/privacy-requests/:id",
            "GET /api/admin/photo-retention",
            "POST /api/admin/photo-retention/run",
            "GET /wms_proxy/OGC_ortofoto_:year/MapServer/WMSServer?...",
            "GET /tile_proxy/geoportal-standard/:z/:x/:y?...",
        )
        for endpoint in active_endpoints:
            self.assertIn(endpoint, normalized_doc, endpoint)
        self.assertNotIn("DELETE /api/field-photos/:id", normalized_doc)

    def test_release_candidate_archive_stays_removed(self):
        self.assertFalse((ROOT_DIR / "docs" / "RELEASE_CANDIDATE.md").exists())

    def test_removed_development_docs_stay_removed(self):
        removed = (
            "ADMIN_PASSWORD_ROTATION.md",
            "AUDIT.md",
            "COMMERCIAL_GRADE_GOAL_PROMPT.md",
            "FUTURE_DATABASE.md",
            "GEOTIFF_RUNBOOK.md",
            "PHOTO_UPLOAD_RUNBOOK.md",
            "README.en.md",
            "RELEASE_CANDIDATE.md",
            "RUNTIME_SMOKE.md",
            "claudflare.md",
            "todo.md",
        )

        for name in removed:
            self.assertFalse((ROOT_DIR / "docs" / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
