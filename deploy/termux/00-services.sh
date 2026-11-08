#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot owns one idempotent service orchestration; runit owns processes.
set -u
HOME=/data/data/com.termux/files/home
PREFIX=/data/data/com.termux/files/usr
PATH="$PREFIX/bin:/system/bin:/system/xbin"
SVDIR="$PREFIX/var/service"
LOGDIR="$PREFIX/var/log"
STATE="$HOME/.local/state/ilestoi-ops"
export HOME PREFIX PATH SVDIR LOGDIR
umask 077
mkdir -p "$STATE"
exec 9>"$STATE/boot.lock"
if ! "$PREFIX/bin/flock" -n 9; then
  exit 0  # Another boot orchestration is already running.
fi

log() {
  printf '%s %s\n' "$(date -Is 2>/dev/null || date)" "$*" >> "$HOME/boot-services.log"
}
# Keep diagnostic logs bounded across repeated Android restarts.
if [ -f "$HOME/boot-services.log" ]; then
  size=$(wc -c < "$HOME/boot-services.log")
  if [ "$size" -gt 262144 ]; then
    mv -f "$HOME/boot-services.log" "$STATE/boot-services.previous.log"
  fi
fi
boot_id=unavailable
if [ -r /proc/sys/kernel/random/boot_id ]; then
  read -r boot_id < /proc/sys/kernel/random/boot_id || :
fi
log "boot orchestration begin boot_id=$boot_id"
if ! "$PREFIX/bin/timeout" -k 2s 8s "$PREFIX/bin/termux-wake-lock" >/dev/null 2>&1; then
  log "wake-lock request unavailable; inspect Android power restrictions"
fi

# A stopped service still returns status 0 when its runsv supervisor is alive.
manager_ready() {
  "$PREFIX/bin/sv" status "$SVDIR/wreckscanner" >/dev/null 2>&1
}
if ! manager_ready; then
  log "runit manager not ready; requesting standard service-daemon"
  "$PREFIX/bin/service-daemon" start >> "$HOME/boot-services.log" 2>&1 ||
    log "service-daemon start request returned failure"
fi
tries=0
until manager_ready; do
  tries=$((tries+1))
  if [ "$tries" -ge 30 ]; then
    log "runit manager unavailable after 60 seconds"
    printf 'boot_id=%s status=supervisor_unavailable\n' "$boot_id" > "$STATE/boot-last.tmp"
    mv -f "$STATE/boot-last.tmp" "$STATE/boot-last"
    exit 1
  fi
  sleep 2
done
log "runit manager available"

# Preserve intentional runit down markers and do not launch duplicate daemons.
for name in sshd mosquitto wreckscanner cloudflared wreckscanner-backup ilestoi-healthwatch; do
  svc="$SVDIR/$name"
  if [ ! -d "$svc" ]; then
    log "$name missing service definition"
    continue
  fi
  if [ -e "$svc/down" ]; then
    log "$name explicitly disabled; preserving down marker"
    continue
  fi
  if "$PREFIX/bin/sv" up "$svc" >> "$HOME/boot-services.log" 2>&1; then
    log "$name supervised start requested"
  else
    log "$name supervised start request failed"
  fi
done

# The network may initialize after Termux:Boot. A failed public check must
# not stop runit or relaunch cloudflared outside its supervisor.
local_code=unavailable
public_code=unavailable
cloud_status=unavailable
tries=0
deadline=$((SECONDS+90))
while [ "$SECONDS" -lt "$deadline" ]; do
  tries=$((tries+1))
  cloud_status=$("$PREFIX/bin/sv" status "$SVDIR/cloudflared" 2>/dev/null || :)
  local_code=$("$PREFIX/bin/curl" --max-time 4 --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:8001/api/health/ready 2>/dev/null || :)
  if [ "$local_code" = 200 ]; then
    case "$cloud_status" in
      run:*)
        public_code=$("$PREFIX/bin/curl" --max-time 5 --silent --output /dev/null --write-out '%{http_code}' https://ilestoi.pl/api/health/live 2>/dev/null || :)
        case "$public_code" in
          200|403) break ;;  # 403 may be Cloudflare's anti-bot protection.
        esac
        ;;
    esac
  fi
  sleep 3
done

result=degraded
case "$cloud_status" in
  run:*)
    if [ "$local_code" = 200 ]; then
      case "$public_code" in 200|403) result=healthy ;; esac
    fi
    ;;
esac
if [ -e "$SVDIR/cloudflared/down" ]; then
  result=cloudflared_disabled
fi
printf 'boot_id=%s status=%s ready=%s public=%s probes=%s\n' \
  "$boot_id" "$result" "$local_code" "$public_code" "$tries" > "$STATE/boot-last.tmp"
mv -f "$STATE/boot-last.tmp" "$STATE/boot-last"
log "boot orchestration end result=$result ready=$local_code public=$public_code probes=$tries"
