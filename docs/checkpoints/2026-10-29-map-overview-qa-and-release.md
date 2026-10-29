# IleStoi.pl — checkpoint mapy (2026-10-29)

Status: **historyczny checkpoint przed wdrożeniem** — stan opisany poniżej dokumentuje etap przedprodukcyjny. Wydanie zostało później wdrożone i zaakceptowane. Aktualny wynik: [końcowy checkpoint golden](2026-10-29-golden-release-closeout.md).

## Zakres

Połączono w odłączonym worktree gałęzie PR #2–#8, w tym:
- #2 indeksowane wyszukiwanie szczegółów;
- #3 projekcja SQL mapy, bbox/cursor i migracja indeksu seek;
- #4 porządek kontraktów jakości;
- #5 zoptymalizowane grupowanie zdjęć;
- #6 stronicowanie dla widocznego obszaru;
- #7 siatka agregatów SQLite 16 × 16 z ochroną warstw;
- #8 widok agregatów przy zoom ≤10, szczegół przy zoom ≥11.

PR #8 ma bazę w PR #6 i **zależy także od siostrzanego PR #7**.
Nie wdrażać go pojedynczo. Wszystkie PR pozostają draft.

## Weryfikacja

Kandydat integracyjny w oddzielnym Termux worktree:
`6625e5230c254adcd71caadc09d82e5320a4e5b7`.

- Python **338/338 PASS**, w tym rzeczywisty Chromium.
- JavaScript **41/41 PASS**.
- Kontrola architektury **7/7 PASS**.
- Ruff lint PASS; Ruff format PASS (140 plików); ESLint PASS.
- `git diff --check` PASS.
- Produkcyjny `main@666d9db71264dcf3389dbc59b46185fc37cb331d` czysty.
- Produkcyjne HTTP `/api/health/live` i `/api/health/ready` = 200.
- Bez restartu, migracji ani wdrożenia na żywo.

## Warunki bezpiecznego wydania

1. Ustalić jeden niezmienny commit release candidate zawierający wszystkie
   wymagane PR i ponownie potwierdzić stan bazy produkcyjnej.
2. Zweryfikować spójny snapshot SQLite w oddzielnym folderze Samsunga,
   lokalny szyfrowany Restic ze zdjęciami, miejsce na dysku i rollback.
   Właściciel 29.10.2026 odstąpił od wymogu kopii off-host; akceptuje ryzyko
   utraty wszystkich kopii w razie utraty telefonu.
3. Zaplanować indeks z `database/migrations/006_field_photo_map_seek.sql`
   i kontrolowany cutover w runit bez drugiej instancji aplikacji.
4. Smoke: publiczne przełączniki warstw, zoom 10↔11, skupiska, link do
   zdjęcia, admin, upload/review/usuwanie, oba endpointy mapy, tunnel i health.
5. Dopiero po przyjęciu wydania: awansować `main` do identycznego SHA,
   oznaczyć tagiem i zabezpieczyć historię. Bez GitHub Actions/Work/Codex.

**W chwili zapisu tej części checkpointu** nie było jeszcze produkcyjnego
wdrożenia. Późniejszy preflight z 29.10.2026 przez Local Agent wykazał:
czysty `main@666d9db7`, sześć usług runit działających, live/ready 200,
SQLite w `~/IleStoi-Backups/pre-release-20261029-104843/` (SHA256,
quick_check, FK PASS; 306 rekordów), `restic check` PASS oraz selektywny
restore SQLite i próbę migracji `006`/rollbacku na duplikacie PASS.
Kopia SQLite pozostaje w oddzielnym folderze Samsunga, lokalny Restic
zachowuje zdjęcia. Zewnętrzna kopia nie jest bramką wydania zgodnie z
nową decyzją właściciela. Wynik właściwego cutoveru trzeba zapisać osobno.
Patrz `docs/TERMUX_DEVELOPMENT_FLOW.md` i `docs/BACKUP.md`.
