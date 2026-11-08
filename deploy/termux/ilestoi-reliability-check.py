#!/data/data/com.termux/files/usr/bin/python3
"""Read-only Termux boot and screen-off acceptance gate (no daemon restarts)."""

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path("/data/data/com.termux/files/home")
STATE = HOME / ".local/state/ilestoi-ops"
SVDIR = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr")) / "var/service"


def status(name):
    try:
        command = subprocess.run(
            ["sv", "status", str(SVDIR / name)], capture_output=True, text=True, timeout=8, check=False
        )
        return "run" if command.returncode == 0 and command.stdout.startswith("run:") else "down"
    except Exception:
        return "supervisor_unavailable"


def http(url):
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "IleStoi-ReliabilityCheck/1"}), timeout=8
        ) as response:
            return str(response.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception as exc:
        return type(exc).__name__


def load(name):
    try:
        value = json.loads((STATE / name).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def current_boot():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def acceptance(health, *, boot_id, now, min_coverage_seconds=0, max_gap_seconds=300):
    checks = {
        "monitor_boot_matches": bool(boot_id and health.get("boot_id") == boot_id),
        "monitor_ready": health.get("ready") == "200",
        "monitor_tunnel_enabled": health.get("cloudflared_disabled_marker") is False,
    }
    try:
        heartbeat_age = now - datetime.fromisoformat(health["utc"]).timestamp()
        coverage = now - datetime.fromisoformat(health["monitor_first_utc"]).timestamp()
        gap = float(health.get("max_monitor_gap_seconds") or 0)
        gap_events = int(health.get("monitor_gap_events") or 0)
    except (KeyError, ValueError, TypeError, OverflowError):
        heartbeat_age, coverage, gap, gap_events = float("inf"), 0, float("inf"), -1
    checks["monitor_fresh"] = 0 <= heartbeat_age <= 240
    checks["monitor_coverage"] = coverage >= min_coverage_seconds
    checks["no_excessive_gap"] = 0 <= gap <= max_gap_seconds and gap_events == 0
    return checks, {
        "heartbeat_age_seconds": round(heartbeat_age, 1),
        "coverage_seconds": round(coverage, 1),
        "max_gap_seconds": gap,
        "gap_events": gap_events,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-coverage-seconds", type=int, default=0)
    parser.add_argument("--max-gap-seconds", type=int, default=300)
    parser.add_argument("--require-boot-record", action="store_true")
    args = parser.parse_args()

    now = time.time()
    boot_id = current_boot()
    health = load("health-last.json")
    checks, metrics = acceptance(
        health,
        boot_id=boot_id,
        now=now,
        min_coverage_seconds=args.min_coverage_seconds,
        max_gap_seconds=args.max_gap_seconds,
    )
    boot = {}
    path = STATE / "boot-last"
    if path.is_file():
        boot = dict(entry.split("=", 1) for entry in path.read_text().split() if "=" in entry)
    checks["boot_record"] = not args.require_boot_record or (
        boot.get("boot_id") == boot_id and boot.get("status") == "healthy"
    )
    services = {name: status(name) for name in ("wreckscanner", "cloudflared", "ilestoi-healthwatch")}
    checks["services_run"] = all(value == "run" for value in services.values())
    checks["no_down_marker"] = not (SVDIR / "cloudflared/down").exists()
    local = http("http://127.0.0.1:8001/api/health/ready")
    public = http("https://ilestoi.pl/api/health/live")
    checks["local_ready"] = local == "200"
    checks["public_edge"] = public in ("200", "403")  # 403 may be Cloudflare bot protection.
    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "checks": checks,
        "metrics": metrics,
        "services": services,
        "local_ready": local,
        "public_edge": public,
        "public_edge_antibot_ambiguous": public == "403",
        "boot_record_status": boot.get("status", "not_present"),
    }
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()
