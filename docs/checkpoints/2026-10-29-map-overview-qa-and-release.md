# IleStoi.pl — checkpoint mapy (2026-10-29)

Status: **prace kodowe oraz testy PASS; bez wydania produkcyjnego**.

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
2. Sprawdzić spójny snapshot SQLite, szyfrowany Restic ze zdjęciami,
   miejsce na dysku, rollback i **potwierdzoną kopię off-host**. Nie zakładać,
   że lokalny backup na telefonie wystarczy.
3. Zaplanować indeks z `database/migrations/006_field_photo_map_seek.sql`
   i kontrolowany cutover w runit bez drugiej instancji aplikacji.
4. Smoke: publiczne przełączniki warstw, zoom 10↔11, skupiska, link do
   zdjęcia, admin, upload/review/usuwanie, oba endpointy mapy, tunnel i health.
5. Dopiero po przyjęciu wydania: awansować `main` do identycznego SHA,
   oznaczyć tagiem i zabezpieczyć historię. Bez GitHub Actions/Work/Codex.

**Nie wykonano tutaj** produkcyjnego wdrożenia ani potwierdzenia off-host
backupu. Patrz `docs/TERMUX_DEVELOPMENT_FLOW.md` i `docs/BACKUP.md`.
