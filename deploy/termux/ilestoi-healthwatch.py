#!/data/data/com.termux/files/usr/bin/python3
"""Bounded runit health monitor for IleStoi on Termux.

Never creates an unsupervised cloudflared process or removes a runit down marker.
Android force-stop/OS process eviction is outside the reach of an in-app monitor.
"""

import json
import math
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CHECK_INTERVAL_SECONDS = 90
FAILURE_THRESHOLD = 3
DOWN_THRESHOLD = 2
RESTART_COOLDOWN_SECONDS = 1800
PUBLIC_TUNNEL_ERRORS = frozenset(("502", "503", "504", "520", "521", "522", "523", "524", "530"))
HOME = Path("/data/data/com.termux/files/home")
STATE = HOME / ".local/state/ilestoi-ops"
SERVICE = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr")) / "var/service/cloudflared"
TUNNEL_CONFIG = HOME / ".cloudflared/config.yml"
LOCAL_READY_URL = "http://127.0.0.1:8001/api/health/ready"
PUBLIC_HEALTH_URL = "https://ilestoi.pl/api/health/live"


def eligible_tunnel_failure(ready, public, internet, disabled):
    return not disabled and ready == "200" and internet == "ok" and public in PUBLIC_TUNNEL_ERRORS


def probe(url):
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "IleStoi-HealthWatch/2"})
        with urllib.request.urlopen(request, timeout=8) as response:
            return str(response.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except Exception as exc:
        return type(exc).__name__


def internet_probe():
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=4):
            return "ok"
    except Exception as exc:
        return type(exc).__name__


def runit_status(service=SERVICE):
    try:
        result = subprocess.run(
            ["sv", "status", str(service)],
            capture_output=True,
            text=True,
            timeout=7,
            check=False,
        )
    except Exception:
        return "supervisor_unavailable"
    if result.returncode:
        return "supervisor_unavailable"
    if result.stdout.startswith("run:"):
        return "run"
    if result.stdout.startswith("down:"):
        return "down"
    return "unknown"


def decide_recovery(ready, public, internet, disabled, runit, public_failures, down_failures, now, last_restart):
    """Return one supervised command; intentional shutdown and cooldown always win."""
    if disabled or ready != "200" or internet != "ok" or runit == "supervisor_unavailable":
        return None
    if last_restart > 0 and now - last_restart < RESTART_COOLDOWN_SECONDS:
        return None
    if runit == "down" and down_failures >= DOWN_THRESHOLD:
        return "up"
    if runit == "run" and public_failures >= FAILURE_THRESHOLD:
        return "restart"
    return None


def boot_id():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except Exception:
        return "unknown"


def load_previous():
    try:
        value = json.loads((STATE / "health-last.json").read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def prior_timestamp(previous, now):
    try:
        then = datetime.fromisoformat(previous["utc"]).timestamp()
        return round(max(0.0, now - then), 1) if 0 <= then <= now else None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def atomic_write(value):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = STATE / "health-last.json"
    temporary = STATE / "health-last.json.tmp"
    with temporary.open("w", encoding="utf-8") as output:
        os.chmod(temporary, 0o600)
        json.dump(value, output, ensure_ascii=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, target)


def note(message):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = STATE / "health-watch.log"
    if path.exists() and path.stat().st_size > 256000:
        path.replace(STATE / "health-watch.previous.log")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(datetime.now(timezone.utc).isoformat() + " " + message + "\n")


def safe_number(value):
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) and parsed >= 0 else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def cycle(previous, *, now=None, current_boot=None):
    now = time.time() if now is None else now
    current_boot = boot_id() if current_boot is None else current_boot
    same_boot = previous.get("boot_id") == current_boot
    old_public = (
        min(FAILURE_THRESHOLD, int(safe_number(previous.get("consecutive_public_failures")))) if same_boot else 0
    )
    old_down = min(DOWN_THRESHOLD, int(safe_number(previous.get("consecutive_runit_down")))) if same_boot else 0
    last_restart = safe_number(previous.get("last_restart_epoch"))
    if last_restart > now:
        last_restart = now  # Wall clock corrected backwards; retain bounded cooldown.

    ready = probe(LOCAL_READY_URL)
    public = probe(PUBLIC_HEALTH_URL)
    internet = internet_probe()
    disabled = (SERVICE / "down").exists()
    runit = runit_status()
    eligible = eligible_tunnel_failure(ready, public, internet, disabled)
    public_failures = min(FAILURE_THRESHOLD, old_public + 1) if eligible else 0
    down_eligible = not disabled and ready == "200" and internet == "ok" and runit == "down"
    down_failures = min(DOWN_THRESHOLD, old_down + 1) if down_eligible else 0
    command = decide_recovery(
        ready, public, internet, disabled, runit, public_failures, down_failures, now, last_restart
    )
    action = "observe"
    if disabled:
        action = "cloudflared_explicitly_disabled"
    elif runit == "supervisor_unavailable":
        action = "cloudflared_supervisor_unavailable"
    elif command:
        if not TUNNEL_CONFIG.is_file():
            action = "cloudflared_config_missing"
        else:
            try:
                result = subprocess.run(
                    ["sv", command, str(SERVICE)],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                action = "cloudflared_" + command + ("_requested" if result.returncode == 0 else "_failed")
            except Exception as exc:
                action = "cloudflared_" + command + "_" + type(exc).__name__
            last_restart = now
            public_failures = 0
            down_failures = 0

    age = prior_timestamp(previous, now)
    gap = age is not None and age > CHECK_INTERVAL_SECONDS * 3 and same_boot
    max_gap = safe_number(previous.get("max_monitor_gap_seconds")) if same_boot else 0
    if same_boot and age is not None:
        max_gap = max(max_gap, age)
    gap_events = int(safe_number(previous.get("monitor_gap_events"))) if same_boot else 0
    first_check = previous.get("monitor_first_utc") if same_boot else None
    if not isinstance(first_check, str) or not first_check:
        first_check = datetime.fromtimestamp(now, timezone.utc).isoformat()
    result = {
        "utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "boot_id": current_boot,
        "ready": ready,
        "public": public,
        "internet": internet,
        "cloudflared_disabled_marker": disabled,
        "cloudflared_runit": runit,
        "consecutive_public_failures": public_failures,
        "consecutive_runit_down": down_failures,
        "last_restart_epoch": last_restart,
        "monitor_gap_seconds": age,
        "max_monitor_gap_seconds": max_gap,
        "monitor_gap_events": min(1000000, gap_events + int(gap)),
        "monitor_first_utc": first_check,
        "action": action,
    }
    atomic_write(result)
    if (
        (action != "observe" and action != previous.get("action"))
        or action.startswith(("cloudflared_up_", "cloudflared_restart_"))
        or gap
        or any(result.get(key) != previous.get(key) for key in ("ready", "public", "internet", "cloudflared_runit"))
    ):
        note(
            f"ready={ready} public={public} internet={internet} runit={runit} "
            f"disabled={disabled} gap_seconds={age} action={action}"
        )
    return result


def main():
    previous = load_previous()
    while True:
        try:
            previous = cycle(previous)
        except Exception as exc:
            # Runit continues to supervise the monitor; no duplicate processes.
            note("monitor_cycle_error=" + type(exc).__name__)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
