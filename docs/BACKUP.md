# Backup I Restore

Aktywny stan aplikacji tworza `wreckscanner.sqlite3`, publiczne pochodne w
`zdjecia_terenowe/` i prywatne oryginaly w `prywatne_zdjecia/`. Historyczne
`settings.json` oraz `zgloszenia_prywatnosci/` nie sa zrodlem prawdy i nie
wchodza do aktywnego backupu ani restore.

## Restic

Lokalne repozytorium restic znajduje sie w `.backups/wreckscanner-restic`, a
jego haslo w `.restic_password`. Plik hasla ma miec tryb `0600` i musi miec
osobna, bezpieczna kopie. Repozytorium na tym samym dysku nie chroni przed
awaria hosta; produkcja wymaga dodatkowej, szyfrowanej kopii off-host oraz
monitorowanego harmonogramu.

Backup restic tworzy najpierw samodzielny snapshot SQLite przez Backup API i
sprawdza jego integralnosc. Nie kopiuje na zywo plikow DB/WAL/SHM. Zakres:

- spójny `wreckscanner.sqlite3`,
- `zdjecia_terenowe/`,
- `prywatne_zdjecia/`,
- `analiza/data_diagnostics.json`.

Domyslnie backup nie zawiera `.admin_password` ani `.restic_password`.
Haslo administratora mozna dolaczyc tylko swiadomie flaga
`--include-admin-password`; haslo repozytorium restic nigdy nie jest jego
czescia.

```bash
cd /home/test/Desktop/WreckScanner

./.venv/bin/python scripts/backup_data.py run \
  --repo .backups/wreckscanner-restic \
  --password-file .restic_password \
  --strict

./.venv/bin/python scripts/backup_data.py snapshots \
  --repo .backups/wreckscanner-restic \
  --password-file .restic_password

./.venv/bin/python scripts/backup_data.py check \
  --repo .backups/wreckscanner-restic \
  --password-file .restic_password
```

## Prosty Tryb Dla Tego Projektu

Przy sporadycznym dodawaniu zdjec nie ma potrzeby codziennie kopiowac calego
zbioru. Restic zapisuje zmiany przyrostowo i deduplikuje niezmienione zdjecia.
Nie podmieniaj ani nie usuwaj recznie plikow w `.backups/wreckscanner-restic`.

Po zakonczeniu spaceru i dodawania nowej partii zdjec wykonaj:

```bash
make backup-restic
make list-restic
```

Raz w tygodniu to samo robi lokalny timer uzytkownika. Jego szablony sa w
`deploy/systemd/`. Instalacja nie wymaga uprawnien roota:

```bash
systemctl --user link "$PWD/deploy/systemd/wreckscanner-backup.service"
systemctl --user link "$PWD/deploy/systemd/wreckscanner-backup.timer"
systemctl --user daemon-reload
systemctl --user enable --now wreckscanner-backup.timer
systemctl --user list-timers wreckscanner-backup.timer
```

Timer jest `Persistent=true`: jezeli komputer byl wylaczony albo sesja
uzytkownika nie dzialala, wykona zalegly backup po kolejnym zalogowaniu. Reczny
backup razem z rotacja i kontrola repozytorium mozna uruchomic przez:

```bash
systemctl --user start wreckscanner-backup.service
systemctl --user status wreckscanner-backup.service --no-pager
```

Rotacja zachowuje 8 punktow tygodniowych i 6 miesiecznych; specjalne snapshoty
recovery nie sa przez nia usuwane. `make check-restic` sprawdza repozytorium bez
tworzenia nowej kopii. Lokalny Restic chroni przed pomylka i przypadkowym
usunieciem, ale nie przed awaria dysku. Wystarczy raz na kilka miesiecy albo po
waznej partii zdjec skopiowac zaszyfrowane repozytorium na osobny nosnik, a haslo
zachowac osobno.

Snapshot SQLite jest spójny podczas pracy serwera. Aby uzyskac jeden punkt w
czasie takze dla DB i wszystkich plikow zdjec, na produkcji zatrzymaj jedyny
supervisor przed backupem i uruchom go po sukcesie:

```bash
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

Nie lacz tej procedury z make'owym sentinelem lub watcherem.

## RPO, RTO, harmonogram i monitoring

Minimalny cel operacyjny przed produkcja:

- RPO: najwyzej 24 godziny utraconych zmian;
- RTO: przywrocenie sprawdzonej uslugi w 4 godziny;
- retencja restic: 14 kopii dziennych, 8 tygodniowych i 12 miesiecznych;
- codzienny backup off-host, cotygodniowe `forget --prune`, `check` i probny
  restore co najmniej raz na kwartal.

Backup uruchamiaj codziennie z timera systemd z `Persistent=true` i
`RandomizedDelaySec`, np. `wreckscanner-backup.timer` o 02:30. Jednostka backupu
musi zawsze (takze po bledzie) ponownie uruchomic `wreckscanner.service`, a sama
komende `backup_data.py run --strict` wykonywac jako uzytkownik aplikacji.
W skrypcie wywolywanym przez jednostke zachowaj kolejnosc:

```bash
set -u
backup_status=0
systemctl stop wreckscanner.service || exit $?
trap 'systemctl start wreckscanner.service' EXIT
sudo -u test /home/test/Desktop/WreckScanner/.venv/bin/python \
  /home/test/Desktop/WreckScanner/scripts/backup_data.py run \
  --root-dir /home/test/Desktop/WreckScanner \
  --repo /home/test/Desktop/WreckScanner/.backups/wreckscanner-restic \
  --password-file /home/test/Desktop/WreckScanner/.restic_password \
  --strict || backup_status=$?
if systemctl start wreckscanner.service; then
  trap - EXIT
else
  backup_status=$?
fi
curl -fsS http://127.0.0.1:8001/api/health/ready || backup_status=$?
exit "$backup_status"
```

Minimalny timer:

```ini
[Unit]
Description=Codzienny backup IleStoi.pl

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
RandomizedDelaySec=15m
Unit=wreckscanner-backup.service

[Install]
WantedBy=timers.target
```

Timer i jednostke utworz poza repozytorium dopiero w kroku operatorskim; po
instalacji sprawdz `systemctl list-timers wreckscanner-backup.timer` oraz reczny
start `systemctl start wreckscanner-backup.service`. Ustaw `OnFailure=` na
lokalny kanal alarmowy. Monitoring ma alarmowac, gdy:

- jednostka lub readiness konczy sie bledem;
- najnowszy snapshot ma ponad 26 godzin;
- `restic check` nie przechodzi;
- repozytorium off-host nie zostalo zsynchronizowane.

Cotygodniowa retencja i kontrola:

```bash
./.venv/bin/python scripts/backup_data.py forget \
  --repo .backups/wreckscanner-restic \
  --password-file .restic_password \
  --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune
./.venv/bin/python scripts/backup_data.py check \
  --repo .backups/wreckscanner-restic \
  --password-file .restic_password
```

Sukces lokalnego snapshotu nie spelnia RPO, dopoki zaszyfrowane repozytorium nie
ma potwierdzonej kopii off-host. Nie kopiuj osobno niezaszyfrowanych prywatnych
plikow ani pliku hasla razem z repozytorium.

## Snapshot ZIP V2

`make backup-data` tworzy snapshot `wreckscanner-data-snapshot-v2` w
`kopie_zapasowe/`. Ta komenda jest przeznaczona dla lokalnego watchera i pamieta
jego poprzedni stan. Na produkcji sterowanej przez systemd uzyj procedury
stop/backup/start pokazanej wyzej i wywolaj bezposrednio. Makefile rozpoznaje
jednostke przypisana do katalogu i blokuje target watchera przed zatrzymaniem
procesu, aby sentinel nie wywolal petli restartow systemd:

```bash
./.venv/bin/python scripts/backup_data.py zip \
  --root-dir /home/test/Desktop/WreckScanner \
  --output-dir kopie_zapasowe \
  --strict
```

Po backupie komenda czeka na readiness procesu podniesionego przez watcher.
Brak gotowego serwera daje niezerowy kod wyjscia; `make` nie uruchamia wtedy
recznej instancji i nie ukrywa bledu ponownego startu. Wrapper czeka tez na
faktyczne zakonczenie starego procesu i przy przerwaniu operacji probuje
przywrocic poprzedni stan watchera.

ZIP zawiera spójny snapshot SQLite, oba katalogi zdjec, diagnostyke oraz
`manifest.json` z rozmiarami i hashami SHA256. Plik wynikowy ma tryb `0600`.
ZIP nie jest szyfrowany i zawiera prywatne zdjecia, dlatego musi byc przenoszony
i przechowywany jak dane wrazliwe.

Sekrety sa domyslnie wykluczone. Tylko jesli szyfrowanie i miejsce docelowe sa
kontrolowane, mozna jawnie utworzyc archiwum z `.admin_password` i
`.restic_password`:

```bash
./.venv/bin/python scripts/backup_data.py zip --include-secrets --strict
```

Nie traktuj nieszyfrowanego ZIP-a z sekretami jako zwyklej kopii przenosnej.

## Restore ZIP

Restore akceptuje wylacznie format `wreckscanner-data-snapshot-v2`, weryfikuje
limity archiwum, sciezki, typy wpisow, manifest, rozmiary, hashe i integralnosc
SQLite. Starszy format nie ma fallbacku. Przed podmiana aktywny stan trafia do
`kopie_zapasowe/przed_odtworzeniem/`, a blad uruchamia rollback.

Domyslnie sekrety z archiwum nie sa odtwarzane. Ich restore wymaga jawnej flagi
`--restore-secrets` i archiwum, ktore rzeczywiscie je zawiera.

Lokalny watcher:

```bash
make list-backups
make restore-data BACKUP=kopie_zapasowe/wreckscanner-snapshot-YYYYMMDD_HHMMSS.zip
```

Produkcja z systemd:

```bash
sudo systemctl stop wreckscanner.service
restore_status=0
./.venv/bin/python scripts/backup_data.py restore-zip \
  --root-dir /home/test/Desktop/WreckScanner \
  --archive kopie_zapasowe/wreckscanner-snapshot-YYYYMMDD_HHMMSS.zip || restore_status=$?
if [ "$restore_status" -eq 0 ]; then
  ./.venv/bin/python scripts/diagnose_data.py --strict || restore_status=$?
  ./.venv/bin/python scripts/migrate_json_to_db.py --validate-only || restore_status=$?
fi
sudo systemctl start wreckscanner.service
curl -fsS http://127.0.0.1:8001/api/health/ready
test "$restore_status" -eq 0
```

`--validate-only` sprawdza aktywne SQLite przez `quick_check`,
`foreign_key_check`, stan migracji i wszystkie odwolania do plikow. Nie
porownuje danych z historycznymi JSON-ami.

## Proba Restore Restic

Probe wykonuj w katalogu tymczasowym, bez podmiany aktywnych danych:

```bash
mkdir -p /tmp/wreckscanner-restore-test
RESTIC_REPOSITORY=/home/test/Desktop/WreckScanner/.backups/wreckscanner-restic \
RESTIC_PASSWORD_FILE=/home/test/Desktop/WreckScanner/.restic_password \
restic restore latest --target /tmp/wreckscanner-restore-test

./.venv/bin/python scripts/diagnose_data.py --strict \
  --field-photos-dir /tmp/wreckscanner-restore-test/zdjecia_terenowe \
  --private-photos-dir /tmp/wreckscanner-restore-test/prywatne_zdjecia

./.venv/bin/python scripts/migrate_json_to_db.py \
  --root-dir /tmp/wreckscanner-restore-test \
  --database /tmp/wreckscanner-restore-test/wreckscanner.sqlite3 \
  --validate-only
```

Po kazdym restore potwierdz `quick_check: ok`, brak naruszen kluczy obcych,
komplet migracji, `Brakujace sciezki: 0` i readiness `200` przed dopuszczeniem
ruchu.

## Ręczny eksport SQLite na Samsungu do przeniesienia poza telefon

**Utworzony i zweryfikowany 29.10.2026**, przed wydaniem PR #2–#5.
Nie jest to katalog projektu, katalog produkcyjny ani magazyn Restic.

- Katalog bazowy: `/data/data/com.termux/files/home/IleStoi-Backups/`
  (skrót Termuxa: `~/IleStoi-Backups/`).
- Konkretna kopia: `~/IleStoi-Backups/pre-release-20261029-104843/`.
- Baza: `wreckscanner.sqlite3` — spójny snapshot przez SQLite Backup API,
  **nie** surowe kopiowanie działających plików WAL/SHM.
- `manifest.json` — data, rozmiar, migracje, liczniki i SHA-256.
- `SHA256SUMS` — suma kontrolna do weryfikacji po skopiowaniu.
- `README-TRANSFER.txt` — instrukcja dla operatora w tym samym katalogu.
- `migration-006-dry-run.json` — wynik próby migracji nowego indeksu na
  **odizolowanym duplikacie** tego snapshotu, nie na produkcji.

Utworzony plik SQLite ma 512000 bajtów. SHA-256:
`c216879cfeed9cd171d574e5eb6bbe4b1417f01292b43461b6ba6b591b0dbba2`.
Przy eksporcie: 306 `field_photos`, 4 `settings`, 0 `privacy_requests`;
`PRAGMA integrity_check=ok` i brak błędów `foreign_key_check`.

Dostęp wyłącznie dla właściciela Termuxa: katalog `0700`, pliki `0600`.
Aby samodzielnie znaleźć i sprawdzić kopię na telefonie:

```sh
cd "$HOME/IleStoi-Backups/pre-release-20261029-104843"
ls -la
sha256sum -c SHA256SUMS
```

Po przeniesieniu folderu poza telefon uruchom `sha256sum -c SHA256SUMS`
także na docelowym komputerze. **Nie usuwaj** lokalnej kopii do czasu
potwierdzenia bezpiecznego eksportu.

**Ograniczenie:** ta ręczna kopia zawiera *wyłącznie SQLite* — bez
`zdjecia_terenowe/` i `prywatne_zdjecia/`. Do pełnego odtworzenia serwisu
potrzebna jest także szyfrowana kopia Restic obu katalogów zdjęć.
SQLite zawiera dane wrażliwe i **nie jest szyfrowany**. Do kopiowania
poza telefon użyj zabezpieczonego połączenia/nośnika i zaszyfruj plik
w miejscu docelowym. Samej kopii na telefonie nie wolno traktować jako
wykonanego backupu off-host. Hasła Restic trzymaj oddzielnie.
