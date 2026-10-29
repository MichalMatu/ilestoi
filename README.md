# IleStoi.pl

IleStoi.pl to lokalna aplikacja mapowa do dokumentowania pojazdow zalegajacych w przestrzeni publicznej. Wynik aplikacji jest materialem pomocniczym do weryfikacji, a nie decyzja o stanie prawnym pojazdu.

Aktualna linia produkcyjna: `main` (stan wdrożony na Termuxie, oznaczany tagiem produkcyjnym). Historyczna wersja `v4.0` pozostaje zachowana w historii.

Status projektu: wersja utrzymaniowa. Repo zostaje odchudzone do kodu, testow i podstawowej dokumentacji potrzebnej do uruchomienia, backupu i pozniejszego serwisu.

## Kierunek i tryb pracy

Projekt jest rozwijany z myślą o możliwym ruchu ogólnopolskim. Bieżąca infrastruktura
Termux pozostaje pojedynczą instalacją; optymalizacje i migracje wymagają pomiarów
oraz osobnych zmian, a nie domniemania, że dzisiejszy serwer obsłuży dużą skalę.

`main` odzwierciedla **zaakceptowaną wersję produkcyjną**. Zmiany powstają
w izolowanych, krótkotrwałych `feature/*` lub `fix/*`, są testowane przez
Local Agent na Termuxie i wdrażane w kontrolowany sposób. Dopiero zaakceptowany
commit staje się nowym `main`; nie utrzymujemy osobnej stałej gałęzi
`work/dirty` ani nie wdrażamy automatycznie po każdym pushu.

Przed zmianami kodu zachowujemy spójny snapshot SQLite i szyfrowany backup
Restic wraz ze zdjęciami. Szczegóły: [przepływ Git/Termux](docs/TERMUX_DEVELOPMENT_FLOW.md)
i [backup/restore](docs/BACKUP.md).

## Start

Wspierany runtime to Python `3.11-3.13` (sprawdzany w CI). Termux z Pythonem `3.14` przeszedł pełne testy jednostkowe, ale nie należy do macierzy CI. Node.js `20+` jest potrzebny tylko do
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
- [docs/TERMUX_DEVELOPMENT_FLOW.md](docs/TERMUX_DEVELOPMENT_FLOW.md) - obowiązujący Git flow, Local Agent i wdrożenie.

## Git Flow

- `main` = dokładnie zaakceptowany stan produkcyjny, nie bieżący plac budowy.
- `feature/*` / `fix/*` = krótkotrwałe gałęzie dla pojedynczego celu.
- Przegląd/testy → kontrolowane wdrożenie kandydata → weryfikacja produkcji
  → fast-forward `main` do tego samego SHA → tag → usunięcie gałęzi roboczej.
- Nie używamy trwałej gałęzi `work/dirty`; archiwum starych HEAD może pozostać
  w tagach, bez mnożenia gałęzi aktywnych.

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
