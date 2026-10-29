import json
import os
import sqlite3
import stat
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from core.data_backup import (
    ResticOptions,
    restic_check,
    restic_forget,
    restic_init,
    run_backup,
)
from core.database import apply_migrations, connect_database
from core.field_photos import save_field_photo_record
from core.zip_backup import ZipRestoreLimits, create_zip_backup, restore_zip_backup

ROOT_DIR = Path(__file__).resolve().parent.parent


class RecordingRunner:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.calls = []
        self.staged_database_exists = False
        self.staged_database_mode = None
        self.staged_probe_values = []
        self.asserted_integrity = None

    def __call__(self, command, *, cwd, env, check):
        cwd_path = Path(cwd)
        self.calls.append({"command": command, "cwd": cwd_path, "env": env, "check": check})
        if len(command) > 1 and command[1] == "backup":
            staged_database = cwd_path / "wreckscanner.sqlite3"
            self.staged_database_exists = staged_database.is_file()
            if self.staged_database_exists:
                self.staged_database_mode = stat.S_IMODE(staged_database.stat().st_mode)
                connection = sqlite3.connect(staged_database)
                try:
                    self.asserted_integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                    try:
                        rows = connection.execute("SELECT value FROM backup_probe ORDER BY value").fetchall()
                    except sqlite3.OperationalError:
                        rows = []
                    self.staged_probe_values = [str(row[0]) for row in rows]
                finally:
                    connection.close()
        return subprocess.CompletedProcess(command, self.returncode)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def prepare_root(root: Path) -> Path:
    (root / "zdjecia_terenowe").mkdir()
    (root / "prywatne_zdjecia").mkdir()
    (root / "zgloszenia_prywatnosci").mkdir()
    write_json(root / "settings.json", {"enhancement": {"enabled": True}})
    password_file = root / ".restic_password"
    password_file.write_text("secret\n", encoding="utf-8")
    return password_file


def create_valid_database(root: Path) -> None:
    connection = connect_database(root / "wreckscanner.sqlite3")
    try:
        apply_migrations(connection)
    finally:
        connection.close()


def command_has_path(command: list[str], relative_path: str) -> bool:
    return any(argument == relative_path or argument.endswith(f"/{relative_path}") for argument in command)


def rewrite_zip_member(source: Path, destination: Path, member_name: str, replacement: bytes) -> None:
    with zipfile.ZipFile(source) as source_zip, zipfile.ZipFile(destination, "w") as destination_zip:
        for member in source_zip.infolist():
            payload = replacement if member.filename == member_name else source_zip.read(member)
            destination_zip.writestr(member, payload)


def field_photo_record(photo_id: str = "photo_20260604T200730Z_37885295") -> dict:
    return {
        "id": photo_id,
        "created_at": "2026-06-04T20:07:30Z",
        "original_filename": "teren.jpg",
        "content_type": "image/jpeg",
        "format": "JPEG",
        "size_bytes": 123,
        "image_width": 48,
        "image_height": 32,
        "issue_type": "vehicle",
        "lat": 51.1,
        "lon": 17.2,
        "coordinate_source": "map",
        "private_original_file": f"field_photos/{photo_id}/missing.jpg",
        "public_review_status": "pending",
        "redactions": [],
        "links": {},
    }


def fake_restic(path: Path) -> Path:
    script = path / "fake_restic.py"
    script.write_text(
        f"#!{sys.executable}\n"
        """import json
import os
import sqlite3
import sys
from pathlib import Path

database = Path.cwd() / "wreckscanner.sqlite3"
database_integrity = None
if database.is_file():
    connection = sqlite3.connect(database)
    try:
        database_integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()
payload = {
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "repo": os.environ.get("RESTIC_REPOSITORY"),
    "password_file": os.environ.get("RESTIC_PASSWORD_FILE"),
    "database_exists": database.is_file(),
    "database_integrity": database_integrity,
}
log = Path(os.environ["FAKE_RESTIC_LOG"])
log.write_text(json.dumps(payload), encoding="utf-8")
sys.exit(0)
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


class DataBackupTests(unittest.TestCase):
    def test_run_backup_writes_diagnostics_and_calls_restic_with_default_paths(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            password_file = prepare_root(root)
            create_valid_database(root)
            runner = RecordingRunner()
            options = ResticOptions(
                root_dir=root, restic_bin="restic", repository=str(root / "repo"), password_file=password_file
            )

            result = run_backup(options=options, check_images=False, runner=runner)

            self.assertEqual(result.status, "ok")
            self.assertEqual(result.diagnostics_status, "ok")
            self.assertTrue((root / "analiza" / "data_diagnostics.json").exists())
            self.assertEqual(len(runner.calls), 1)
            command = runner.calls[0]["command"]
            self.assertEqual(command[:2], ["restic", "backup"])
            self.assertIn("--group-by", command)
            self.assertIn("host,tags", command)
            self.assertIn("--tag", command)
            self.assertIn("wreckscanner", command)
            self.assertTrue(command_has_path(command, "wreckscanner.sqlite3"))
            self.assertTrue(command_has_path(command, "zdjecia_terenowe"))
            self.assertTrue(command_has_path(command, "prywatne_zdjecia"))
            self.assertTrue(command_has_path(command, "analiza/data_diagnostics.json"))
            self.assertFalse(command_has_path(command, "wreckscanner.sqlite3-wal"))
            self.assertFalse(command_has_path(command, "wreckscanner.sqlite3-shm"))
            self.assertFalse(command_has_path(command, "zgloszenia_prywatnosci"))
            self.assertFalse(command_has_path(command, "settings.json"))
            self.assertFalse(command_has_path(command, ".admin_password"))
            self.assertTrue(runner.staged_database_exists)
            self.assertEqual(runner.asserted_integrity, "ok")
            self.assertEqual(runner.staged_database_mode, 0o600)
            self.assertFalse(runner.calls[0]["cwd"].exists())
            self.assertIn(root / "wreckscanner.sqlite3", result.backup_paths)
            self.assertEqual(runner.calls[0]["env"]["RESTIC_REPOSITORY"], str(root / "repo"))
            self.assertEqual(runner.calls[0]["env"]["RESTIC_PASSWORD_FILE"], str(password_file))
            self.assertEqual(runner.calls[0]["env"]["RESTIC_CACHE_DIR"], str(root / ".cache" / "restic"))

    def test_run_backup_can_include_admin_password_and_extra_path(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            password_file = prepare_root(root)
            create_valid_database(root)
            (root / ".admin_password").write_text("admin-secret\n", encoding="utf-8")
            write_json(root / "custom.json", {"ok": True})
            runner = RecordingRunner()
            options = ResticOptions(
                root_dir=root, restic_bin="restic", repository=str(root / "repo"), password_file=password_file
            )

            result = run_backup(
                options=options,
                include_admin_password=True,
                extra_paths=[Path("custom.json")],
                check_images=False,
                runner=runner,
            )

            self.assertEqual(result.status, "ok")
            command = runner.calls[0]["command"]
            self.assertTrue(command_has_path(command, ".admin_password"))
            self.assertTrue(command_has_path(command, "custom.json"))

    def test_run_backup_uses_consistent_staged_database_and_excludes_live_journals(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            password_file = prepare_root(root)
            create_valid_database(root)
            connection = sqlite3.connect(root / "wreckscanner.sqlite3")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("CREATE TABLE backup_probe (value TEXT NOT NULL)")
            connection.execute("INSERT INTO backup_probe (value) VALUES ('committed-in-wal')")
            connection.commit()
            runner = RecordingRunner()
            options = ResticOptions(
                root_dir=root, restic_bin="restic", repository=str(root / "repo"), password_file=password_file
            )

            try:
                result = run_backup(options=options, check_images=False, runner=runner)
            finally:
                connection.close()

            self.assertEqual(result.status, "ok")
            command = runner.calls[0]["command"]
            self.assertTrue(command_has_path(command, "wreckscanner.sqlite3"))
            self.assertFalse(command_has_path(command, "wreckscanner.sqlite3-wal"))
            self.assertFalse(command_has_path(command, "wreckscanner.sqlite3-shm"))
            self.assertEqual(runner.staged_probe_values, ["committed-in-wal"])
            self.assertFalse(runner.calls[0]["cwd"].exists())

    def test_run_backup_cleans_staging_after_restic_failure(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            password_file = prepare_root(root)
            create_valid_database(root)
            runner = RecordingRunner(returncode=17)
            options = ResticOptions(
                root_dir=root, restic_bin="restic", repository=str(root / "repo"), password_file=password_file
            )

            result = run_backup(options=options, check_images=False, runner=runner)

            self.assertEqual(result.status, "failed")
            self.assertEqual(result.restic.returncode, 17)
            self.assertFalse(runner.calls[0]["cwd"].exists())

    def test_run_backup_blocks_extra_path_covering_live_database_or_secrets(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            password_file = prepare_root(root)
            create_valid_database(root)
            runner = RecordingRunner()
            options = ResticOptions(
                root_dir=root, restic_bin="restic", repository=str(root / "repo"), password_file=password_file
            )

            result = run_backup(
                options=options,
                extra_paths=[Path(".")],
                check_images=False,
                runner=runner,
            )

            self.assertEqual(result.status, "blocked")
            self.assertIn("aktywnej bazy", result.message)
            self.assertEqual(runner.calls, [])

    def test_run_backup_blocks_when_diagnostics_has_errors(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            password_file = prepare_root(root)
            save_field_photo_record(field_photo_record(), root / "zdjecia_terenowe")
            runner = RecordingRunner()
            options = ResticOptions(
                root_dir=root, restic_bin="restic", repository=str(root / "repo"), password_file=password_file
            )

            result = run_backup(options=options, check_images=False, runner=runner)

            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.diagnostics_status, "error")
            self.assertIn("błędy", result.message)
            self.assertEqual(runner.calls, [])

    def test_run_backup_strict_blocks_warnings(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            password_file = prepare_root(root)
            (root / "zdjecia_terenowe" / "orphan.bin").write_bytes(b"orphan")
            runner = RecordingRunner()
            options = ResticOptions(
                root_dir=root, restic_bin="restic", repository=str(root / "repo"), password_file=password_file
            )

            result = run_backup(options=options, strict=True, check_images=False, runner=runner)

            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.diagnostics_status, "warning")
            self.assertEqual(runner.calls, [])

    def test_restic_helper_commands_use_repository_and_password_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            password_file = prepare_root(root)
            options = ResticOptions(root_dir=root, restic_bin="restic", repository="repo", password_file=password_file)
            runner = RecordingRunner()

            self.assertEqual(restic_init(options, runner=runner).command, ["restic", "init"])
            self.assertEqual(restic_check(options, runner=runner).command, ["restic", "check"])
            forget = restic_forget(
                options,
                keep_daily=7,
                keep_weekly=4,
                keep_monthly=2,
                prune=True,
                runner=runner,
            )

            self.assertIn("--keep-daily", forget.command)
            self.assertIn("7", forget.command)
            self.assertIn("--prune", forget.command)
            self.assertEqual(
                forget.command[1:6],
                ["forget", "--group-by", "host,tags", "--tag", "wreckscanner,data"],
            )
            self.assertEqual(runner.calls[0]["env"]["RESTIC_REPOSITORY"], str(root / "repo"))

    def test_backup_data_cli_runs_fake_restic_end_to_end(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            password_file = prepare_root(root)
            create_valid_database(root)
            restic_bin = fake_restic(root)
            restic_log = root / "restic-log.json"
            env = os.environ.copy()
            env["FAKE_RESTIC_LOG"] = str(restic_log)

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT_DIR / "scripts" / "backup_data.py"),
                    "run",
                    "--root-dir",
                    str(root),
                    "--restic-bin",
                    str(restic_bin),
                    "--repo",
                    str(root / "repo"),
                    "--password-file",
                    str(password_file),
                    "--no-image-check",
                    "--dry-run",
                ],
                cwd=ROOT_DIR,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Diagnostyka zapisana", result.stdout)
            payload = json.loads(restic_log.read_text(encoding="utf-8"))
            self.assertEqual(payload["argv"][0], "backup")
            self.assertIn("--dry-run", payload["argv"])
            self.assertNotIn("zidentyfikowane_wraki", payload["argv"])
            self.assertTrue(command_has_path(payload["argv"], "wreckscanner.sqlite3"))
            self.assertTrue(command_has_path(payload["argv"], "prywatne_zdjecia"))
            self.assertFalse(command_has_path(payload["argv"], "zgloszenia_prywatnosci"))
            self.assertFalse(command_has_path(payload["argv"], "settings.json"))
            self.assertTrue(payload["database_exists"])
            self.assertEqual(payload["database_integrity"], "ok")
            self.assertFalse(Path(payload["cwd"]).exists())
            self.assertEqual(payload["repo"], str(root / "repo"))
            self.assertEqual(payload["password_file"], str(password_file))

    def test_create_zip_backup_excludes_legacy_data_and_secrets_by_default(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_root(root)
            create_valid_database(root)
            (root / ".admin_password").write_text("admin-secret\n", encoding="utf-8")
            (root / "zdjecia_terenowe" / "public.txt").write_text("public photo placeholder", encoding="utf-8")
            (root / "prywatne_zdjecia" / "private.txt").write_text("private photo placeholder", encoding="utf-8")

            result = create_zip_backup(root_dir=root, check_images=False)

            self.assertEqual(result.status, "ok")
            self.assertIsNotNone(result.archive_path)
            with zipfile.ZipFile(result.archive_path) as archive:
                names = set(archive.namelist())
                self.assertIn("wreckscanner.sqlite3", names)
                self.assertIn("zdjecia_terenowe/public.txt", names)
                self.assertIn("prywatne_zdjecia/private.txt", names)
                self.assertNotIn("settings.json", names)
                self.assertFalse(any(name.startswith("zgloszenia_prywatnosci/") for name in names))
                self.assertNotIn(".admin_password", names)
                self.assertNotIn(".restic_password", names)
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

            self.assertEqual(stat.S_IMODE(result.archive_path.stat().st_mode), 0o600)
            self.assertEqual(manifest["format"], "wreckscanner-data-snapshot-v2")
            self.assertFalse(manifest["secrets_included"])
            self.assertEqual(manifest["secret_entries"], [])
            self.assertNotIn("source_root", manifest)

    def test_restore_zip_backup_replaces_only_current_data_and_keeps_safety_copy(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_root(root)
            create_valid_database(root)
            (root / ".admin_password").write_text("original-admin\n", encoding="utf-8")
            (root / "zdjecia_terenowe" / "snapshot.txt").write_text("snapshot public", encoding="utf-8")
            (root / "prywatne_zdjecia" / "snapshot.txt").write_text("snapshot private", encoding="utf-8")
            (root / "settings.json").write_text('{"version":"snapshot"}\n', encoding="utf-8")
            backup = create_zip_backup(root_dir=root, check_images=False)

            self.assertEqual(backup.status, "ok")
            (root / ".admin_password").write_text("changed-admin\n", encoding="utf-8")
            (root / "zdjecia_terenowe" / "changed.txt").write_text("changed public", encoding="utf-8")
            (root / "prywatne_zdjecia" / "changed.txt").write_text("changed private", encoding="utf-8")
            (root / "settings.json").write_text('{"version":"changed"}\n', encoding="utf-8")

            result = restore_zip_backup(root_dir=root, archive_path=backup.archive_path)

            self.assertEqual(result.status, "ok")
            self.assertIsNotNone(result.safety_path)
            self.assertEqual((root / ".admin_password").read_text(encoding="utf-8"), "changed-admin\n")
            self.assertTrue((root / "zdjecia_terenowe" / "snapshot.txt").exists())
            self.assertTrue((root / "prywatne_zdjecia" / "snapshot.txt").exists())
            self.assertFalse((root / "zdjecia_terenowe" / "changed.txt").exists())
            self.assertFalse((root / "prywatne_zdjecia" / "changed.txt").exists())
            self.assertEqual((root / "settings.json").read_text(encoding="utf-8"), '{"version":"changed"}\n')
            self.assertFalse((result.safety_path / "settings.json").exists())
            self.assertTrue((result.safety_path / "zdjecia_terenowe" / "changed.txt").exists())
            self.assertEqual(stat.S_IMODE((root / "zdjecia_terenowe" / "snapshot.txt").stat().st_mode), 0o600)

    def test_zip_backup_and_restore_require_explicit_secret_flags_and_set_mode_0600(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_root(root)
            create_valid_database(root)
            admin_password = root / ".admin_password"
            restic_password = root / ".restic_password"
            admin_password.write_text("original-admin\n", encoding="utf-8")
            restic_password.write_text("original-restic\n", encoding="utf-8")

            backup = create_zip_backup(root_dir=root, include_secrets=True, check_images=False)

            self.assertEqual(backup.status, "ok")
            with zipfile.ZipFile(backup.archive_path) as archive:
                names = set(archive.namelist())
                self.assertIn(".admin_password", names)
                self.assertIn(".restic_password", names)
                manifest = json.loads(archive.read("manifest.json"))
            self.assertTrue(manifest["secrets_included"])
            self.assertEqual(set(manifest["secret_entries"]), {".admin_password", ".restic_password"})

            admin_password.write_text("changed-admin\n", encoding="utf-8")
            restic_password.write_text("changed-restic\n", encoding="utf-8")
            admin_password.chmod(0o644)
            restic_password.chmod(0o644)

            restored = restore_zip_backup(
                root_dir=root,
                archive_path=backup.archive_path,
                restore_secrets=True,
            )

            self.assertEqual(restored.status, "ok")
            self.assertEqual(admin_password.read_text(encoding="utf-8"), "original-admin\n")
            self.assertEqual(restic_password.read_text(encoding="utf-8"), "original-restic\n")
            self.assertEqual(stat.S_IMODE(admin_password.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(restic_password.stat().st_mode), 0o600)
            self.assertEqual(
                (restored.safety_path / ".admin_password").read_text(encoding="utf-8"),
                "changed-admin\n",
            )

    def test_restore_zip_validates_manifest_sha256_before_active_swap(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_root(root)
            create_valid_database(root)
            snapshot_file = root / "zdjecia_terenowe" / "snapshot.txt"
            snapshot_file.write_text("trusted snapshot", encoding="utf-8")
            backup = create_zip_backup(root_dir=root, check_images=False)
            tampered_archive = root / "tampered.zip"
            rewrite_zip_member(
                backup.archive_path,
                tampered_archive,
                "zdjecia_terenowe/snapshot.txt",
                b"altered snapshot",
            )
            snapshot_file.write_text("current active data", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "SHA-256"):
                restore_zip_backup(root_dir=root, archive_path=tampered_archive)

            self.assertEqual(snapshot_file.read_text(encoding="utf-8"), "current active data")
            self.assertFalse((root / "kopie_zapasowe" / "przed_odtworzeniem").exists())

    def test_restore_zip_rejects_high_compression_ratio_before_active_swap(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_root(root)
            create_valid_database(root)
            active_marker = root / "zdjecia_terenowe" / "active.txt"
            active_marker.write_text("active", encoding="utf-8")
            bomb_archive = root / "compression-bomb.zip"
            with zipfile.ZipFile(bomb_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("bomb.bin", b"A" * 100_000)
                archive.writestr("manifest.json", b"{}")

            with self.assertRaisesRegex(ValueError, "Współczynnik kompresji"):
                restore_zip_backup(
                    root_dir=root,
                    archive_path=bomb_archive,
                    limits=ZipRestoreLimits(
                        max_members=10,
                        max_total_uncompressed_bytes=200_000,
                        max_compression_ratio=10,
                        max_manifest_bytes=10_000,
                    ),
                )

            self.assertEqual(active_marker.read_text(encoding="utf-8"), "active")
            self.assertFalse((root / "kopie_zapasowe" / "przed_odtworzeniem").exists())

    def test_restore_zip_enforces_member_count_and_total_size_limits(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_root(root)
            create_valid_database(root)
            backup = create_zip_backup(root_dir=root, check_images=False)
            cases = (
                (
                    "member count",
                    ZipRestoreLimits(max_members=1),
                    "za dużo wpisów",
                ),
                (
                    "total size",
                    ZipRestoreLimits(max_total_uncompressed_bytes=1),
                    "Łączny rozmiar",
                ),
            )

            for label, limits, message in cases:
                with self.subTest(label=label), self.assertRaisesRegex(ValueError, message):
                    restore_zip_backup(
                        root_dir=root,
                        archive_path=backup.archive_path,
                        limits=limits,
                    )

    def test_restore_zip_rejects_old_snapshot_contract(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_root(root)
            create_valid_database(root)
            backup = create_zip_backup(root_dir=root, check_images=False)
            with zipfile.ZipFile(backup.archive_path) as archive:
                manifest = json.loads(archive.read("manifest.json"))
            manifest["format"] = "wreckscanner-data-snapshot-v1"
            old_archive = root / "old-format.zip"
            rewrite_zip_member(
                backup.archive_path,
                old_archive,
                "manifest.json",
                json.dumps(manifest).encode("utf-8"),
            )

            with self.assertRaisesRegex(ValueError, "wreckscanner-data-snapshot-v2"):
                restore_zip_backup(root_dir=root, archive_path=old_archive)


if __name__ == "__main__":
    unittest.main()
