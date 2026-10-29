import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class ToolingContractTests(unittest.TestCase):
    def run_make(
        self,
        target: str,
        *variables: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        process_env = os.environ.copy()
        if env is not None:
            process_env.update(env)
        return subprocess.run(
            ["make", "--no-print-directory", target, *variables],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
            env=process_env,
        )

    def write_hardened_systemctl_fixture(self, directory: Path) -> Path:
        systemctl = directory / "systemctl-fixture"
        systemctl.write_text(
            f"""#!/bin/sh
case "$1" in
    show)
        case "$*" in
            *--property=WorkingDirectory*)
                printf '%s\\n' '/var/lib/wreckscanner'
                ;;
            *--property=BindReadOnlyPaths*)
                printf '%s\\n' '{ROOT_DIR}/server.py:/var/lib/wreckscanner/server.py:rbind'
                ;;
            *--property=MainPID*)
                printf '%s\\n' '4242'
                ;;
            *)
                exit 1
                ;;
        esac
        ;;
    is-active)
        printf '%s\\n' 'active'
        ;;
    is-enabled)
        printf '%s\\n' 'enabled'
        ;;
    *)
        exit 1
        ;;
esac
""",
            encoding="utf-8",
        )
        systemctl.chmod(0o700)
        return systemctl

    def test_opencv_uses_the_published_python_distribution_pin(self):
        requirements = (ROOT_DIR / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("opencv-python==5.0.0.93", requirements.splitlines())
        self.assertNotIn("opencv-python==5.0.0", requirements.splitlines())

    def test_numpy_pin_covers_every_supported_python_runtime(self):
        requirements = (ROOT_DIR / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn('numpy==2.3.5; python_version < "3.12"', requirements.splitlines())
        self.assertIn('numpy==2.5.0; python_version >= "3.12"', requirements.splitlines())
        self.assertNotIn("numpy==2.5.0", requirements.splitlines())

    def test_make_lint_delegates_to_recursive_frontend_linter(self):
        makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")
        lint_target = makefile.split("lint:\n", 1)[1].split("\nsmoke:", 1)[0]

        self.assertIn("npm run lint:web", lint_target)
        self.assertNotIn("eslint web/*.js", lint_target)
        self.assertIn("npm jest wymagany", lint_target)

    def test_ci_covers_supported_python_runtime_endpoints(self):
        workflow = (ROOT_DIR / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")

        self.assertIn("fail-fast: false", workflow)
        self.assertIn('python-version: ["3.11", "3.13"]', workflow)
        self.assertIn("python-version: ${{ matrix.python-version }}", workflow)

    def test_check_script_annotates_the_exact_failing_ci_command(self):
        check_script = (ROOT_DIR / "scripts" / "check.sh").read_text(encoding="utf-8")

        self.assertIn('[[ "${GITHUB_ACTIONS:-}" == "true" ]]', check_script)
        self.assertIn("::error title=check.sh command failed::", check_script)
        self.assertIn("::error title=check.sh failure output::", check_script)
        self.assertIn("tail -n 80", check_script)
        self.assertIn('run_with_failure_tail "$PYTHON_BIN" -m coverage run', check_script)
        self.assertIn('report_failure "$status" "$@"', check_script)

    def test_ci_actions_are_pinned_to_immutable_commit_shas(self):
        workflow = (ROOT_DIR / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")

        self.assertIn("actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4", workflow)
        self.assertIn("actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5", workflow)
        self.assertIn("actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4", workflow)
        action_lines = [line.strip() for line in workflow.splitlines() if "uses: actions/" in line]
        self.assertEqual(len(action_lines), 3)
        for line in action_lines:
            self.assertRegex(line, r"uses: actions/[^@]+@[0-9a-f]{40}(?:\s+#\s+v\d+)?$")

    def test_make_uses_readiness_to_admit_traffic(self):
        makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")

        self.assertIn("/api/health/live", makefile)
        self.assertIn("/api/health/ready", makefile)
        self.assertIn('curl -fsS --max-time "$(SERVER_PROBE_TIMEOUT_SECONDS)" "$(SERVER_READY_URL)"', makefile)
        self.assertIn("curl jest wymagany do sprawdzenia readiness", makefile)
        self.assertNotIn("Sprawdz watcher albo uruchom tymczasowo", makefile)

    def test_autostart_never_falls_back_to_a_manual_server(self):
        makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")
        autostart = makefile.split("autostart-start: require-local-watcher\n", 1)[1].split("\nautostart-status:", 1)[0]

        self.assertIn("$(SUBMAKE) SERVER_WAIT_SECONDS=$(SERVER_AUTOSTART_WAIT_SECONDS) wait-server", autostart)
        self.assertIn("Reczna instancja nie zostala uruchomiona", autostart)
        self.assertNotIn("pgrep", autostart)
        self.assertNotIn("nohup", autostart)
        self.assertNotIn("server.pid", makefile)
        self.assertNotIn("$(SUBMAKE) autostart-start || true", makefile)

    def test_make_dry_run_cannot_execute_recursive_recipes(self):
        makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")
        recipes = makefile.split("menu:\n", 1)[1]

        self.assertIn("SUBMAKE := $(MAKE)", makefile)
        self.assertNotIn("$(MAKE)", recipes)

    def test_make_guards_watcher_mutations_on_a_systemd_host(self):
        makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")

        self.assertIn("SYSTEMD_WORKING_DIRECTORY := $(shell $(SYSTEMCTL) show", makefile)
        self.assertIn("--property=BindPaths --property=BindReadOnlyPaths", makefile)
        self.assertIn("SYSTEMD_CHECKOUT_MOUNTS :=", makefile)
        self.assertIn("stop: require-local-watcher", makefile)
        self.assertIn("restart: require-local-watcher", makefile)
        self.assertIn("backup-data: require-local-watcher", makefile)
        self.assertIn("restore-data: require-local-watcher", makefile)
        self.assertIn("sudo systemctl stop|start|restart", makefile)

    def test_make_reads_logs_from_the_detected_supervisor(self):
        makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")
        logs = makefile.split("logs:\n", 1)[1].split("\ncheck:", 1)[0]

        self.assertIn('"$(JOURNALCTL)" --unit "$(SYSTEMD_UNIT)"', logs)
        self.assertIn('tail -n 80 "$(SERVER_LOG)"', logs)

    def test_make_health_propagates_process_and_endpoint_failures(self):
        makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")
        status = makefile.split("status:\n", 1)[1].split("\nlogs:", 1)[0]

        self.assertIn("status=1", status)
        self.assertIn('exit "$$status"', status)
        self.assertNotIn('"$(SERVER_LIVE_URL)" || true', status)

    def test_make_status_returns_nonzero_for_a_missing_server(self):
        result = self.run_make(
            "status",
            "SYSTEMD_MANAGED=0",
            "PORT=1",
            "SERVER_PATTERN=[p]ython-impossible-wreckscanner-contract",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Procesy server.py:\nbrak", result.stdout)

    def test_make_refuses_watcher_stop_when_systemd_is_detected(self):
        result = self.run_make("stop", "SYSTEMD_MANAGED=1")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("przeznaczona tylko dla lokalnego watchera", result.stdout)
        self.assertIn("sudo systemctl stop|start|restart", result.stdout)

    def test_make_detects_hardened_systemd_unit_from_read_only_repo_bind(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_systemctl = self.write_hardened_systemctl_fixture(Path(directory))

            result = self.run_make("stop", f"SYSTEMCTL={fake_systemctl}")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Ten katalog obsluguje systemd: wreckscanner.service.", result.stdout)
        self.assertIn("sudo systemctl stop|start|restart", result.stdout)

    def test_make_status_uses_systemd_main_pid_without_local_process_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            fake_systemctl = self.write_hardened_systemctl_fixture(fixture_dir)
            pgrep_marker = fixture_dir / "pgrep-called"

            fake_pgrep = fixture_dir / "pgrep"
            fake_pgrep.write_text(
                '#!/bin/sh\n: > "$PGREP_MARKER"\nexit 99\n',
                encoding="utf-8",
            )
            fake_pgrep.chmod(0o700)

            fake_curl = fixture_dir / "curl"
            fake_curl.write_text(
                "#!/bin/sh\nprintf '%s\\n' '{\"status\": \"ok\"}'\n",
                encoding="utf-8",
            )
            fake_curl.chmod(0o700)

            result = self.run_make(
                "status",
                f"SYSTEMCTL={fake_systemctl}",
                env={
                    "PATH": f"{fixture_dir}{os.pathsep}{os.environ['PATH']}",
                    "PGREP_MARKER": str(pgrep_marker),
                },
            )
            pgrep_was_called = pgrep_marker.exists()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Supervisor: systemd (wreckscanner.service), stan: active", result.stdout)
        self.assertIn("4242", result.stdout)
        self.assertFalse(pgrep_was_called, "systemd status must not use the watcher pgrep pattern")

    def test_make_logs_uses_journalctl_in_systemd_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_journalctl = Path(directory) / "journalctl-fixture"
            fake_journalctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*"\n', encoding="utf-8")
            fake_journalctl.chmod(0o700)

            result = self.run_make(
                "logs",
                "SYSTEMD_MANAGED=1",
                "SYSTEMD_UNIT=audit.service",
                f"JOURNALCTL={fake_journalctl}",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "--unit audit.service --lines 80 --no-pager")

    def test_make_exposes_incremental_restic_backup_and_rotation(self):
        makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")

        self.assertIn("backup-restic:", makefile)
        self.assertIn("prune-restic:", makefile)
        self.assertIn("check-restic:", makefile)
        self.assertIn("list-restic:", makefile)
        self.assertIn("--keep-daily 0 --keep-weekly 8 --keep-monthly 6 --prune", makefile)
        self.assertIn("scripts/backup_data.py run", makefile)
        self.assertIn("--strict", makefile)

    def test_user_backup_timer_runs_backup_rotation_and_check(self):
        unit_dir = ROOT_DIR / "deploy" / "systemd"
        service = (unit_dir / "wreckscanner-backup.service").read_text(encoding="utf-8")
        timer = (unit_dir / "wreckscanner-backup.timer").read_text(encoding="utf-8")

        self.assertIn("Type=oneshot", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("ExecStart=/usr/bin/make backup-restic", service)
        self.assertIn("ExecStart=/usr/bin/make prune-restic", service)
        self.assertIn("ExecStart=/usr/bin/make check-restic", service)
        self.assertIn("OnCalendar=Sun *-*-* 04:00:00", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("RandomizedDelaySec=30m", timer)


if __name__ == "__main__":
    unittest.main()
