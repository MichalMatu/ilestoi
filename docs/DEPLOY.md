# Deploy Produkcyjny

Dla aktualnego serwera Android Termux użyj [docs/TERMUX.md](TERMUX.md); poniżej opisano alternatywny wdrożeniowy tryb systemd na Raspberry Pi.

Ten runbook opisuje lokalny deploy IleStoi.pl na Raspberry Pi za tunelem
Cloudflare. Aktywnym stanem aplikacji jest SQLite oraz pliki zdjec na dysku.

## Sekrety i zmienne

Minimalny zestaw produkcyjny:

```bash
WRECKSCANNER_HOST=127.0.0.1
WRECKSCANNER_PORT=8001
WRECKSCANNER_ADMIN_PASSWORD=...
WRECKSCANNER_ADMIN_SESSION_SECRET=...
WRECKSCANNER_ADMIN_COOKIE_SECURE=1
WRECKSCANNER_CORS_ALLOWED_ORIGINS=https://ilestoi.pl
WRECKSCANNER_TRUSTED_PROXY_ADDRESSES=127.0.0.1,::1
WRECKSCANNER_PUBLIC_HOSTS=wreckscanner.pl,www.wreckscanner.pl,ilestoi.pl,www.ilestoi.pl,dlugostoi.pl,www.dlugostoi.pl
WRECKSCANNER_PHOTO_RETENTION_AUTORUN=1
```

`WRECKSCANNER_ADMIN_SESSION_SECRET` musi byc stalym, losowym sekretem
produkcyjnym i powinien byc rotowany tylko swiadomie. Aktywne sesje sa dodatkowo
rejestrowane w pamieci procesu: logout natychmiast uniewaznia konkretny token, a
restart procesu celowo uniewaznia wszystkie sesje administratora.

`.admin_password` jest dopuszczalny lokalnie, ale w usludze systemd wygodniej
uzyc `EnvironmentFile` z `WRECKSCANNER_ADMIN_PASSWORD`. Nie commituj zadnego
pliku z sekretami.

## Systemd

Przyklad jednostki:

```ini
[Unit]
Description=IleStoi.pl
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/home/test/Desktop/WreckScanner
EnvironmentFile=/home/test/Desktop/WreckScanner/.env.production
ExecStart=/home/test/Desktop/WreckScanner/.venv/bin/python /home/test/Desktop/WreckScanner/server.py
Restart=on-failure
RestartSec=3
User=test
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Po zmianie jednostki:

```bash
rm -f /home/test/Desktop/WreckScanner/.dev/server.autostart.disabled
sudo systemctl daemon-reload
sudo systemctl enable --now wreckscanner.service
systemctl status wreckscanner.service --no-pager
```

Cloudflare Tunnel i publiczne hosty sa opisane w
[PUBLIC_RUNTIME.md](PUBLIC_RUNTIME.md).

Na produkcji `wreckscanner.service` jest jedynym supervisorem procesu. Nie lacz
go z make'owym watcherem, sentinelem autostartu ani recznym `nohup`. Wszystkie
operacje start/stop/restart wykonuj przez `systemctl`. Lokalny watcher opisuje
[START.md](START.md).

Przy starcie aplikacja dodatkowo ustawia procesowy `umask 0077`, katalog
`prywatne_zdjecia/` na `0700` oraz istniejące pliki SQLite/WAL/SHM na `0600`.
Po pierwszym starcie zweryfikuj właściciela i tryby bez odczytywania zawartości:

```bash
stat -c '%U:%G %a %n' prywatne_zdjecia wreckscanner.sqlite3
```

## Przed Deployem

```bash
git status --short --branch
test -z "$(git status --porcelain)"
git describe --exact-match --tags HEAD
./scripts/check.sh
./.venv/bin/python scripts/diagnose_data.py --strict
./.venv/bin/python scripts/migrate_json_to_db.py --validate-only
sudo systemctl stop wreckscanner.service
backup_status=0
./.venv/bin/python scripts/backup_data.py run \
  --repo .backups/wreckscanner-restic \
  --password-file .restic_password \
  --strict || backup_status=$?
sudo systemctl start wreckscanner.service
curl -fsS http://127.0.0.1:8001/api/health/ready
test "$backup_status" -eq 0
```

Deployuj wylacznie czysty, otagowany baseline z `main`. Walidacja
`migrate_json_to_db.py --validate-only` sprawdza aktywne SQLite przez
`quick_check`, `foreign_key_check`, komplet migracji i odwolania do plikow;
historyczne JSON-y nie sa zrodlem prawdy.

Przed pierwszym publicznym wdrozeniem wykonaj tez probe restore wedlug
[BACKUP.md](BACKUP.md).

## Po Deployu

```bash
sudo systemctl restart wreckscanner.service
curl -fsS http://127.0.0.1:8001/api/health/live
curl -fsS http://127.0.0.1:8001/api/health/ready
make smoke
make e2e-report
```

Liveness potwierdza dzialanie procesu. Dopiero readiness `200` potwierdza, ze
baza, migracje, pliki i przestrzen dyskowa pozwalaja bezpiecznie kierowac ruch.

`make e2e-report` wymaga dzialajacego WMS i Chromium. Test tworzy tymczasowe
zdjecie, generuje raport PDF z cropami mapy i statusem OC/UFG, a potem usuwa
testowe pliki po sobie.

## Rollback

1. Zatrzymaj usluge: `sudo systemctl stop wreckscanner.service`.
2. Przywroc poprzedni otagowany baseline kodu i jego zaleznosci do osobnego
   katalogu release.
3. Jesli wydanie zmienilo dane, odtworz snapshot restic do katalogu
   tymczasowego wedlug [BACKUP.md](BACKUP.md).
4. Zweryfikuj odtworzone dane przez `diagnose_data.py --strict` i
   `migrate_json_to_db.py --validate-only`.
5. Po potwierdzeniu zamien `wreckscanner.sqlite3`, `zdjecia_terenowe/` i
   `prywatne_zdjecia/` na odtworzone wersje.
6. Przelacz `ExecStart`/symlink release na poprzedni baseline i uruchom usluge:
   `sudo systemctl start wreckscanner.service`.
7. Wykonaj `make smoke` i `make e2e-report`.
