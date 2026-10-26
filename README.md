# IleStoi.pl

IleStoi.pl to lokalna aplikacja mapowa do dokumentowania pojazdow zalegajacych w przestrzeni publicznej. Wynik aplikacji jest materialem pomocniczym do weryfikacji, a nie decyzja o stanie prawnym pojazdu.

Aktualne wydanie: `v4.0`.

Status projektu: wersja utrzymaniowa. Repo zostaje odchudzone do kodu, testow i podstawowej dokumentacji potrzebnej do uruchomienia, backupu i pozniejszego serwisu.

## Plan Dalszego Utrzymania

To poboczny projekt o niskim priorytecie, utrzymywany glownie jako prywatna mapa
uzupelniana podczas spacerow. Kolejne prace wybieramy wedlug stosunku zysku do
nakladu, a nie dla samego domkniecia wszystkich mozliwych usprawnien.

### Teraz

- Zachowywac sprawdzony stan na `work/dirty`; przed checkpointem uruchamiac
  `scripts/check.sh`.
- Po wiekszej sesji dodawania zdjec wykonywac `make backup-restic`. Tygodniowy
  timer utrzymuje 8 kopii tygodniowych i 6 miesiecznych.
- Nie dodawac nowych funkcji bez konkretnej potrzeby wynikajacej z korzystania
  z mapy.

### Kolejne Male Poprawki

- Raz na kilka miesiecy skopiowac zaszyfrowane repozytorium Restic na osobny
  nosnik i sprawdzic kopie; haslo przechowywac osobno. Przy tej okazji wykonac
  pelny `restic check --read-data` i izolowana probe restore.
- Przy kolejnej zmianie ZIP ujednolicic `BACKUP_DIR` z katalogiem kopii stanu
  sprzed restore; obecnie niestandardowy `BACKUP_DIR` dotyczy tworzenia i listy.
- Przy okazji zmian uslugi dodac produkcyjny `EnvironmentFile`, `UMask=0077`,
  `NoNewPrivileges=true`, `PrivateTmp=true` i trwaly sekret sesji.
- Utrzymywac DNS starych hostow `wreckscanner.pl`, `dlugostoi.pl` i ich
  wariantow `www`, aby stale przekierowywaly do kanonicznego `ilestoi.pl`.
- Przygotowac squash na `main` i tag dopiero przy swiadomym kolejnym wydaniu.

### Tylko Jesli Projekt Zyska Ruch

- Zautomatyzowac kopie off-host, monitoring wieku backupu i okresowy restore.
- Usunac `'unsafe-inline'` z CSP.
- Dalej podnosic coverage, dzielic wieksze moduly i optymalizowac UX na podstawie
  realnych problemow uzytkownikow.

## Start

CI sprawdza Python `3.11` i `3.13`; obecny Termux z Pythonem `3.14` przeszedł pełne testy jednostkowe. Oficjalne macierze CI pozostają na 3.11/3.13. Node.js `20+` jest potrzebny tylko do
kontroli frontendu; CI uzywa Node.js 22. Przygotowanie lokalnego srodowiska:

```bash
cd /home/test/Desktop/WreckScanner
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
```

Reczne uruchomienie na hoscie bez aktywnego supervisora:

```bash
cd /home/test/Desktop/WreckScanner
./.venv/bin/python server.py
```

Aplikacja dziala pod:

```text
http://127.0.0.1:8001
```

`make help` wykrywa lokalny watcher albo produkcyjny `wreckscanner.service`.
Polecenia zmieniajace proces przez `make` sa tylko dla watchera; na systemd
koncza sie bezpiecznym bledem z poprawna komenda operatorska. Szczegoly sa w
[docs/START.md](docs/START.md).

## Zakres

- mapa Leaflet z podkladami `POL`, `OSM` oraz rocznikami Wroclawia `2020-2025`,
- zdjecia terenowe w SQLite z typem obserwacji, lokalizacja, kolejka zatwierdzania, anonimizacja i publicznymi kopiami bez EXIF,
- warstwa pojazdow budowana z zatwierdzonych zdjec terenowych, z recznym statusem OC/UFG dla grupy wraku,
- automatyczne miniatury historyczne pobierane z WMS podczas generowania zgloszenia,
- raporty PDF generowane na zadanie z wybranych zdjec terenowych, bez zapisu stalego rekordu sprawy,
- panel administratora dla zdjec, zgloszen prywatnosci, retencji oryginalow i widocznosci warstw,
- warstwa dzialek KIEG/EGiB,
- lokalny backup danych przez `restic`.

## Prywatnosc

Publiczne API zwraca tylko `public_image` i `public_thumb`; nie zwraca lokalnych sciezek ani prywatnych oryginalow. Oryginaly sa dostepne tylko przez endpointy administracyjne. Publiczne kopie zdjec sa publikowane dopiero po review i anonimizacji.

Haslo administratora pochodzi z `WRECKSCANNER_ADMIN_PASSWORD` albo z lokalnego pliku `.admin_password`. Plik jest ignorowany przez Git.

## Dokumentacja

- [docs/START.md](docs/START.md) - uruchamianie, zatrzymanie, smoke test i haslo administratora.
- [docs/CURRENT_MODEL.md](docs/CURRENT_MODEL.md) - aktualny model danych, endpointy i audyt braku starych artefaktow.
- [docs/DATABASE.md](docs/DATABASE.md) - aktualny kontrakt SQLite, migracje i walidacja integralnosci.
- [docs/PUBLIC_RUNTIME.md](docs/PUBLIC_RUNTIME.md) - porty publicznych uslug i konfiguracja Cloudflare Tunnel.
- [docs/BACKUP.md](docs/BACKUP.md) - lokalny backup i restore danych.
- [docs/DEPLOY.md](docs/DEPLOY.md) - produkcyjny deploy, sekrety, systemd i rollback.
- [docs/TERMUX.md](docs/TERMUX.md) - aktualny host Android, runit, backup i restart.

## Git Flow

- `main` jest linia release-only: jeden commit `Release vX.Y baseline` na wydanie i pasujacy tag, np. `v3.1`.
- `work/dirty` jest galezia robocza do codziennego rozwoju, poprawek i eksperymentow.
- Po weryfikacji stan z `work/dirty` trafia na `main` jako squash release baseline.

## Lokalne Dane

Te katalogi i pliki sa lokalna baza aplikacji albo cache i nie powinny trafic do repozytorium:

- `analiza/` - lokalne raporty diagnostyczne uruchamiane przez `scripts/check.sh`,
- `wreckscanner.sqlite3` - aktywny stan aplikacji: zdjecia terenowe, ustawienia i zgloszenia prywatnosci,
- `zdjecia_terenowe/` - publiczne pochodne zdjec terenowych i katalogi plikow,
- `prywatne_zdjecia/` - prywatne oryginaly zdjec,
- `zgloszenia_prywatnosci/` i `settings.json` - historyczny/importowy format JSON,
- `.cache/` i `.backups/` - cache oraz lokalne repozytorium backupu.

`prywatne_zgloszenia/` to wycofany katalog starych, trwale zapisanych pakietow
raportow. Nie jest aktywnym storage aplikacji; `scripts/diagnose_data.py` traktuje
jego obecnosc jako blad danych przed release candidate.

## Kontrole

```bash
scripts/check.sh
make smoke
make e2e-report
```

`scripts/check.sh` uruchamia compile, Ruff, testy, frontend lint, diagnostyki i `git diff --check`. `make smoke` sprawdza dzialajacy serwer, a `make e2e-report` wykonuje przeplyw upload -> review -> mapa -> raport PDF z OC/UFG.
