"""Offline reboot, Doze-gap and runit recovery tests; never touch live services."""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "deploy/termux/00-services.sh"
WATCH = ROOT / "deploy/termux/ilestoi-healthwatch.py"


def load_watch():
    spec = importlib.util.spec_from_file_location("testable_ilestoi_watch", WATCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecoveryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.watch = load_watch()

    def test_public_530_three_strikes_restarts_only_supervised_running_tunnel(self):
        decide = self.watch.decide_recovery
        self.assertEqual(decide("200", "530", "ok", False, "run", 3, 0, 10000, 0), "restart")
        self.assertIsNone(decide("200", "530", "ok", False, "run", 2, 0, 10000, 0))

    def test_stopped_runit_service_is_recovered_only_after_two_observations(self):
        decide = self.watch.decide_recovery
        self.assertEqual(decide("200", "403", "ok", False, "down", 0, 2, 10000, 0), "up")
        self.assertIsNone(decide("200", "403", "ok", False, "down", 0, 1, 10000, 0))

    def test_cooldown_survives_monitor_restart(self):
        decide = self.watch.decide_recovery
        self.assertIsNone(decide("200", "530", "ok", False, "run", 3, 0, 10000, 9900))
        self.assertIsNone(decide("200", "530", "ok", False, "down", 3, 2, 10000, 9900))
        self.assertEqual(decide("200", "530", "ok", False, "run", 3, 0, 11800, 9900), "restart")

    def test_never_override_down_marker_or_unhealthy_backend_or_no_network(self):
        decide = self.watch.decide_recovery
        for disabled, ready, internet, runit in [
            (True, "200", "ok", "down"),
            (False, "503", "ok", "run"),
            (False, "200", "TimeoutError", "run"),
            (False, "200", "ok", "supervisor_unavailable"),
        ]:
            with self.subTest(disabled=disabled, ready=ready, internet=internet, runit=runit):
                self.assertIsNone(decide(ready, "530", internet, disabled, runit, 3, 2, 10000, 0))

    def test_malformed_persisted_state_never_blocks_watchdog(self):
        self.assertEqual(self.watch.safe_number("not-a-number"), 0)
        self.assertEqual(self.watch.safe_number(float("nan")), 0)
        self.assertEqual(self.watch.safe_number(-3), 0)
        self.assertEqual(self.watch.safe_number(None), 0)

    def test_monitor_gap_after_doze_detected(self):
        previous = {"utc": datetime.fromtimestamp(8000, timezone.utc).isoformat()}
        self.assertEqual(self.watch.prior_timestamp(previous, 9000), 1000.0)
        self.assertIsNone(self.watch.prior_timestamp({"utc": "invalid"}, 9000))

    def test_runit_status_parsing(self):
        cases = [
            (0, "run: /tmp/cloudflared: (pid 55) 4s", "run"),
            (0, "down: /tmp/cloudflared: 100s", "down"),
            (1, "fail: /tmp/cloudflared", "supervisor_unavailable"),
        ]
        for rc, out, expected in cases:
            with self.subTest(out=out), patch.object(
                self.watch.subprocess, "run", return_value=SimpleNamespace(returncode=rc, stdout=out)
            ):
                self.assertEqual(self.watch.runit_status(Path("/tmp/cloudflared")), expected)


class RecoveryCycleTests(unittest.TestCase):
    def setUp(self):
        self.watch = load_watch()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.service = self.state / "cloudflared"
        self.service.mkdir()
        self.config = self.state / "config.yml"
        self.config.write_text("tunnel: fake-fixture-not-live\n")
        for name, value in [("STATE", self.state), ("SERVICE", self.service), ("TUNNEL_CONFIG", self.config)]:
            patcher = patch.object(self.watch, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cycle(self, previous, *, ready="200", public="530", internet="ok", runit="run", now=10000):
        with (
            patch.object(self.watch, "probe", side_effect=[ready, public]),
            patch.object(self.watch, "internet_probe", return_value=internet),
            patch.object(self.watch, "runit_status", return_value=runit),
            patch.object(
                self.watch.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0),
            ) as runner,
        ):
            result = self.watch.cycle(previous, now=now, current_boot="test-boot")
        self.assertEqual(json.loads((self.state / "health-last.json").read_text())["action"], result["action"])
        self.assertEqual(oct((self.state / "health-last.json").stat().st_mode & 0o777), "0o600")
        return result, runner.call_args_list

    def test_three_consecutive_530_restart_and_persist_cooldown(self):
        last = {"boot_id": "test-boot", "consecutive_public_failures": 2}
        result, calls = self.run_cycle(last)
        self.assertEqual(result["action"], "cloudflared_restart_requested")
        self.assertEqual(result["last_restart_epoch"], 10000)
        self.assertEqual(len(calls), 1)
        after, calls2 = self.run_cycle(result, now=10090)
        self.assertEqual(after["action"], "observe")
        self.assertEqual(len(calls2), 0)

    def test_runit_down_recovery_even_with_cloudflare_antibot_403(self):
        last = {"boot_id": "test-boot", "consecutive_runit_down": 1}
        result, calls = self.run_cycle(last, public="403", runit="down")
        self.assertEqual(result["action"], "cloudflared_up_requested")
        self.assertEqual(len(calls), 1)

    def test_explicit_disable_does_not_touch_runit(self):
        (self.service / "down").touch()
        result, calls = self.run_cycle({}, public="530", runit="down")
        self.assertEqual(result["action"], "cloudflared_explicitly_disabled")
        self.assertEqual(len(calls), 0)

    def test_configuration_missing_blocks_restart(self):
        self.config.unlink()
        result, calls = self.run_cycle(
            {"boot_id": "test-boot", "consecutive_public_failures": 2}
        )
        self.assertEqual(result["action"], "cloudflared_config_missing")
        self.assertEqual(len(calls), 0)

    def test_resume_after_screen_off_reports_long_interval(self):
        last = {"boot_id": "test-boot", "utc": datetime.fromtimestamp(8000, timezone.utc).isoformat()}
        result, _ = self.run_cycle(last, public="403", now=9000)
        self.assertEqual(result["monitor_gap_seconds"], 1000)
        self.assertIn("gap_seconds=1000", (self.state / "health-watch.log").read_text())

    def test_clock_correction_and_invalid_counters(self):
        last = {
            "boot_id": "test-boot",
            "consecutive_public_failures": "invalid",
            "consecutive_runit_down": -1,
            "last_restart_epoch": 999999999,
        }
        result, calls = self.run_cycle(last)
        self.assertEqual(result["consecutive_public_failures"], 1)
        self.assertEqual(result["last_restart_epoch"], 10000)
        self.assertEqual(len(calls), 0)


class BootEntrypointTests(unittest.TestCase):
    def test_shell_syntax(self):
        completed = subprocess.run(
            ["bash", "-n", str(BOOT)], capture_output=True, text=True, timeout=8, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_boot_does_not_override_intentional_shutdown(self):
        script = BOOT.read_text()
        self.assertIn('if [ -e "$svc/down" ]', script)
        self.assertIn('"$PREFIX/bin/sv" up "$svc"', script)
        self.assertIn('"$PREFIX/bin/flock" -n 9', script)
        self.assertNotIn("cloudflared tunnel run", script)

    def test_simulated_boot_is_idempotent_and_preserves_down_markers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home"
            prefix = root / "usr"
            binary = prefix / "bin"
            binary.mkdir(parents=True)
            home.mkdir()
            for name in ("date", "flock", "mkdir", "mv", "wc", "sleep", "timeout"):
                target = shutil.which(name)
                if not target:
                    self.skipTest(f"{name} binary unavailable")
                (binary / name).symlink_to(target)
            services = prefix / "var/service"
            for name in (
                "sshd",
                "mosquitto",
                "wreckscanner",
                "cloudflared",
                "wreckscanner-backup",
                "ilestoi-healthwatch",
            ):
                (services / name).mkdir(parents=True)
            (services / "sshd/down").touch()
            (binary / "termux-wake-lock").write_text("#!/bin/sh\nexit 0\n")
            (binary / "curl").write_text("#!/bin/sh\nprintf 200\n")
            (binary / "sv").write_text(
                '#!/bin/sh\n'
                'if [ "$1" = status ]; then printf "run: mock-service (pid 100) 10s\\n"; exit 0; fi\n'
                'if [ "$1" = up ]; then echo "$2" >> "$MOCK_SERVICE_UP_LOG"; exit 0; fi\n'
                'exit 1\n'
            )
            (binary / "service-daemon").write_text("#!/bin/sh\nexit 0\n")
            for name in ("termux-wake-lock", "curl", "sv", "service-daemon"):
                (binary / name).chmod(0o700)
            source = BOOT.read_text().replace(
                "HOME=/data/data/com.termux/files/home", f"HOME={home}"
            ).replace("PREFIX=/data/data/com.termux/files/usr", f"PREFIX={prefix}")
            script = root / "boot.sh"
            script.write_text(source)
            events = root / "up.log"
            env = dict(os.environ, MOCK_SERVICE_UP_LOG=str(events))
            for _ in range(2):
                done = subprocess.run(
                    ["bash", str(script)], env=env, capture_output=True, text=True, timeout=20, check=False
                )
                self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(len(events.read_text().splitlines()), 10)
            self.assertNotIn("/sshd", events.read_text())
            self.assertIn("status=healthy", (home / ".local/state/ilestoi-ops/boot-last").read_text())
            self.assertTrue((services / "sshd/down").exists())


if __name__ == "__main__":
    unittest.main()
