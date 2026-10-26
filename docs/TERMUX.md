# IleStoi.pl na Termuxie (Android)

Stan produkcji: `~/WreckScanner/WreckScanner` (gałąź `work/dirty`).
Python 3.14 działa w bieżącym środowisku Termuxa; główne CI sprawdza 3.11/3.13.

## Nadzór i autostart

Runit `runsvdir` jest uruchamiany przy restarcie telefonu przez Termux:Boot
(`~/.termux/boot/90-local-agent`). Usługa `$PREFIX/var/service/wreckscanner`
używa `deploy/termux/wreckscanner.run`; proces nie jest uruchamiany przez
`nohup` ani przez drugiego watchera.

```sh
sv status "$PREFIX/var/service/wreckscanner"
sv restart "$PREFIX/var/service/wreckscanner"
curl -fsS http://127.0.0.1:8001/api/health/ready
```

Przy tworzeniu usługi jednorazowo należy ją skopiować, nadać `chmod 700`
plikowi `run`, zostawić tylko jednego supervisora i usunąć dawny autostart
`nohup ... server.py` ze skryptu `00-services`. Trzymaj kopię starego
skryptu startowego z uprawnieniami 0600.

Nie restartuj całego telefonu, procesu Local Agent ani tunelu Cloudflare
w ramach zwykłego wdrożenia. Aby zastosować nowy kod Pythona:
`sv restart "$PREFIX/var/service/wreckscanner"`.

## Kopie zapasowe

Restic powinien używać lokalnego repozytorium
`.backups/wreckscanner-restic` i pliku `.restic_password` z `0600`.
Hasło przechowuj też niezależnie od telefonu. Nie zapisuj klucza w Git,
logach, w katalogu zdjęć ani w nieszyfrowanym archiwum.

```sh
cd ~/WreckScanner/WreckScanner
./.venv/bin/python scripts/backup_data.py run \
  --repo .backups/wreckscanner-restic \
  --password-file .restic_password --strict
./.venv/bin/python scripts/backup_data.py check \
  --repo .backups/wreckscanner-restic \
  --password-file .restic_password
```

Kopie na tym samym telefonie chronią przed przypadkowym usunięciem plików,
ale **nie** przed zgubieniem/uszkodzeniem telefonu. Dla ochrony danych
potrzebna jest dodatkowa zaszyfrowana kopia poza telefonem i próba restore.
Przywracanie archiwum do żywej bazy wymaga wyłączenia jedynej usługi
`wreckscanner` i kontroli spójności SQLite po restore.
