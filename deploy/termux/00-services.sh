#!/data/data/com.termux/files/usr/bin/bash
set -u
HOME=/data/data/com.termux/files/home
PREFIX=/data/data/com.termux/files/usr
PATH="$PREFIX/bin:/system/bin:/system/xbin"
SVDIR="$PREFIX/var/service"
LOGDIR="$PREFIX/var/log"
export HOME PREFIX PATH SVDIR LOGDIR
umask 077
termux-wake-lock >/dev/null 2>&1 || true
log() { printf '%s %s\n' "$(date -Is 2>/dev/null || date)" "$*" >> "$HOME/boot-services.log"; }
log "runit boot orchestration begin"
if ! "$PREFIX/bin/sv" status "$SVDIR/wreckscanner" >/dev/null 2>&1; then
  "$PREFIX/bin/service-daemon" start >> "$HOME/boot-services.log" 2>&1 || log "runit manager start failed"
fi
n=0
while ! "$PREFIX/bin/sv" status "$SVDIR/wreckscanner" >/dev/null 2>&1; do
  n=$((n+1))
  if [ "$n" -ge 25 ]; then log "runit manager unavailable"; exit 1; fi
  sleep 1
done
for name in sshd mosquitto wreckscanner cloudflared wreckscanner-backup ilestoi-healthwatch; do
  svc="$SVDIR/$name"
  [ -d "$svc" ] || continue
  if [ -f "$svc/down" ]; then log "$name intentionally disabled"; continue; fi
  "$PREFIX/bin/sv" up "$svc" >> "$HOME/boot-services.log" 2>&1 || log "$name start request failed"
done
log "runit boot orchestration end"
