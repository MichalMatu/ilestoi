# Start I Utrzymanie

## Runtime I Instalacja

- Python `3.11-3.13` (CI sprawdza 3.11 i 3.13),
- Node.js `20+` do lintowania frontendu (CI uzywa Node.js 22).

```bash
cd /home/test/Desktop/WreckScanner
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
```

Reczne uruchomienie jest przeznaczone tylko dla hosta bez aktywnego watchera i
bez jednostki systemd:

```bash
./.venv/bin/python server.py
```

Adres lokalny:

```text
http://127.0.0.1:8001
```

## Jeden Supervisor

`make help`, `make status`, `make start`, `make health`, `make logs` i
`make autostart-status` wykrywaja, czy ten katalog obsluguje lokalny watcher,
czy `wreckscanner.service`. Detekcja obejmuje zarowno bezposredni
`WorkingDirectory`, jak i utwardzona jednostke, ktora montuje `server.py` z tego
katalogu przez `BindPaths` albo `BindReadOnlyPaths`. `make start` jest
informacyjnym aliasem statusu i nie uruchamia procesu. `make status` oraz
`make health` koncza sie bledem, gdy brakuje procesu, liveness albo readiness.

Nie uruchamiaj drugiej kopii recznie, jesli proces juz dziala. Polecenia
zmieniajace stan przez `make` sa przeznaczone wylacznie dla lokalnego watchera:

Sprawdzenie:

```bash
pgrep -af "/home/test/Desktop/WreckScanner/server.py"
```

Restart:

```bash
make restart
```

Zatrzymanie:

```bash
make stop
```

Wylaczenie autostartu:

```bash
make serwerstop
```

Ponowne wlaczenie:

```bash
make serwerstart
```

Ta komenda usuwa blokade autostartu i tylko czeka na zewnetrzny watcher. Jesli
watcher nie podniesie gotowego procesu, komenda konczy sie bledem i nie uruchamia
recznej ani drugiej instancji `server.py`.

Na hoscie produkcyjnym jedynym supervisorem jest `wreckscanner.service`.
Nie uzywaj tam `make stop`, `make restart`, `make serwerstop`, `make serwerstart`
ani awaryjnego `nohup`; Makefile wykrywa ten tryb i blokuje targety watchera,
zanim zmienia sentinel albo proces. Steruj usluga wylacznie przez:

```bash
sudo systemctl stop wreckscanner.service
sudo systemctl start wreckscanner.service
sudo systemctl restart wreckscanner.service
systemctl status wreckscanner.service --no-pager
```

## Haslo Administratora

Haslo pochodzi z `WRECKSCANNER_ADMIN_PASSWORD` albo z lokalnego pliku `.admin_password`. Zmienna srodowiskowa ma pierwszenstwo przed plikiem `.admin_password`.

Utworzenie lokalnego hasla:

```bash
openssl rand -base64 24 > .admin_password
chmod 600 .admin_password
```

Po zmianie hasla stare sesje administratora przestaja przechodzic walidacje.

## Kontrole

Pelny lokalny zestaw:

```bash
scripts/check.sh
```

Smoke test dzialajacego serwera:

```bash
make smoke
```

E2E mapy i raportu dzialajacego serwera:

```bash
make e2e-report
```

Ten test wymaga `.admin_password`, dzialajacego serwera, Chromium oraz dostepu do
WMS. Dodaje male zdjecie testowe, zatwierdza je, sprawdza publiczny kontrakt mapy,
generuje PDF z tymczasowymi cropami mapy oraz statusem OC/UFG, zapisuje w
`analiza/` zrzuty: desktop PL, tablet EN, mobile PL i widok EN przy efektywnym
powiekszeniu 200%, a na koncu wylogowuje administratora oraz usuwa testowy rekord
i pliki.

Liveness odpowiada tylko na pytanie, czy proces HTTP dziala. Readiness sprawdza
aktywne SQLite, migracje, odwolania do plikow i bezpieczna rezerwe dysku; tylko
wynik readiness `200` dopuszcza ruch po starcie lub restarcie:

```bash
curl -fsS http://127.0.0.1:8001/api/health/live
curl -fsS http://127.0.0.1:8001/api/health/ready
```

## Backup

Backup i restore opisuje [BACKUP.md](BACKUP.md). Pliku `.restic_password` nie nadpisuj przy rotacji hasla administratora, chyba ze swiadomie zmieniasz haslo repozytorium backupu.

## Deploy

Produkcyjny deploy, zmienne srodowiskowe, systemd i rollback opisuje
[DEPLOY.md](DEPLOY.md).
