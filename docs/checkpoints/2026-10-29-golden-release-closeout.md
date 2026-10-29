# IleStoi.pl — golden closeout wydania mapy (29.10.2026)

## Status i zakres

**Wydanie produkcyjne zaakceptowane.** Zintegrowany kod aplikacji PR #2–#8
został wdrożony i zweryfikowany na Samsungu/Termuxie jako
`ecc14c1591fac142db1888917714dbb312bef3aa` (PR #9).
Wcześniejszy produkcyjny commit: `666d9db71264dcf3389dbc59b46185fc37cb331d`.
Po wydaniu wolno dodawać dokumentację bez zmiany plików wykonywalnych,
ale `main` i produkcyjny checkout telefonu muszą pozostać zsynchronizowane.
Nie tworzono nowej funkcji ani dodatkowego API w sprincie zamykającym.

### Dokładnie wdrożone zmiany aplikacji

1. `app/http/observation_pages.py`: indeksowany odczyt pojedynczej obserwacji
   po identyfikatorze zamiast przeglądania całej kolekcji.
2. `core/field_photo_map_query.py`, `app/http/public_data.py`: wąska publiczna
   projekcja SQL, parametry `bbox`, `limit` (1–500), `cursor`, deterministyczne
   `created_at DESC, id DESC` i filtrowanie uprawnień/warstw.
3. `database/migrations/006_field_photo_map_seek.sql`: indeks
   `idx_field_photos_map_seek`, zastosowany na produkcji.
4. `web/map_helpers.js`, `web/app/vehicle_layer.js`,
   `web/app/field_photos.js`: indeks przestrzenny do grupowania zdjęć
   i pojazdów z zachowaniem dotychczasowego promienia i semantyki grup.
5. `web/app/field_photos.js`: paginacja widocznego obszaru z 12,5%
   marginesem, debounce 250 ms, anulowaniem nieaktualnych żądań,
   limitem 40 stron oraz błędem zamiast ukrytego obcięcia danych.
6. `core/field_photo_clusters.py`, `web/app/overview_clusters.js`:
   maksymalnie 16 × 16 skupisk, liczby **zdjęć**, nie pojazdów;
   gość przy zoom ≤10 widzi skupiska, zoom ≥11 daje szczegółowe zdjęcia.
   Administracja, deep linki i aktywne zaawansowane filtry zachowują
   tryb szczegółowy także przy małym zoomie.
7. Obsługa granicy ±180°, filtrów warstw, przejścia zoom 10/11,
   stanów błędu, statusów dostępności oraz polskich/angielskich opisów UI.

### Jak sprawdzić ręcznie

1. Otwórz [https://ilestoi.pl/](https://ilestoi.pl/) w nowym oknie.
   Przy oddalonej mapie (zoom 7–10) zobacz skupiska z liczbą zdjęć;
   kliknięcie przybliża obszar, a zoom 11+ pokazuje szczegółowe pinezki.
2. Otwórz narzędzia przeglądarki → **Network**. Przy dalekim zoomie
   powinien wystąpić `GET /api/field-photos/clusters?bbox=...`;
   przy bliskim: `GET /api/field-photos?bbox=...&limit=500` oraz
   opcjonalny `cursor`. Brak wielkiego nieograniczonego żądania
   w zwykłym trybie publicznej mapy.
3. Przesuń szybko mapę, włącz/wyłącz pojazdy, infrastrukturę, powietrze
   i warstwę oczekujących. Liczniki skupisk powinny reagować na widoczność,
   a odpowiedź poprzedniego obszaru nie może zastąpić nowej mapy.
4. Kliknij kilka zbliżonych zdjęć, sprawdź tooltip/popup oraz przejście
   między skupiskiem a szczegółem. Porównaj na telefonie i desktopie.
5. Sprawdź administratora i filtry pojazdów wyłącznie odczytowo,
   bez tworzenia testowych zdjęć i zgłoszeń w produkcyjnej SQLite.

## Potwierdzone testy i dowody

- **Wdrożenie:** Local Agent Samsung, `ilestoi-prod-pr9-cutover-20261029-v1`:
  gotowa osobna kopia przedwdrożeniowa, poprawny `006`, 306 rekordów,
  nowy `wreckscanner` pod runit, `live=200`, `ready=200`.
- **Baza i backup:** `~/IleStoi-Backups/pre-release-20261029-104843/`
  oraz `~/IleStoi-Backups/pre-deploy-pr9-20261029/` pozostają poza
  katalogiem produkcji; SHA256, `quick_check`, FK PASS.
  `restic check` 6 snapshotów PASS, selektywny restore SQLite PASS.
  Migrację `006` i rollback sprawdzono na duplikacie SQLite (PASS).
- **Python:** 338 testów, 0 failures, 0 errors; 6 testów przeglądarkowych
  pominiętych na Androidzie z powodu niezgodnego binarnie Chromium.
  Te 6 testów wykonano **oddzielnie na Macu w rzeczywistym Google Chrome**
  na dokładnym produkcyjnym SHA: 6/6 PASS, bez pominięć.
- **JS i jakość:** po `npm ci --ignore-scripts` w odizolowanym worktree:
  `npm run test:web` **41/41 PASS**, `npm run lint:web` PASS,
  `git diff --check` PASS. Pełne Ruff/architektura były PASS na
  identycznym kodzie w pierwotnym gate PR #9; nie deklarujemy nowego
  przebiegu Ruff na telefonie, gdzie binarka jest niedostępna.
- **Rzeczywiste API:** strona główna, `/observations`, zdrowie, ustawienia
  i status admina HTTP 200. Publiczna paginacja `bbox=14,49,25,55`
  pobrała **276 unikalnych zdjęć w 6 stronach**; SQL agregatów zwrócił
  dokładnie **276**. Brak prywatnych pól EXIF, oryginałów i tokenów
  edycji w publicznej projekcji.
- **Edge cases HTTP:** błędne/nienumeryczne/wielokrotne `bbox`,
  odwrócone granice, niedozwolone parametry agregatów, `limit=0/501`
  i błędny cursor → 400; przekroczenie południka 180° i globalny `bbox`
  z limitem → 200. Testy JS obejmują nieaktualne odpowiedzi, powtórzony
  cursor, ekstremalny viewport, zoom, filtry i grupowanie.
- **Stan usługi po porządkowaniu:** produkcyjny `git status` czysty,
  `wreckscanner`, `wreckscanner-backup`, `cloudflared`, `sshd`,
  `mosquitto`, `ilestoi-healthwatch` pod runit działają; readiness 200.

## Artefakty, worktree i Git

- Repozytorium GitHub: 280 pozycji w drzewie głównym przed końcowym
  checkpointem; brak śledzonych plików cache, prywatnych backupów,
  WAL, logów testowych czy snapshotów bazy.
- Usunięto **9 czystych lokalnych worktree** ze zintegrowaną historią,
  w tym ostatni worktree wydania po zakończeniu regresji. Pozostały wyłącznie
  trzy lokalne worktree z historią niezawartą w `main`; zachowano je celowo.
- Opublikowano tag wydania `v2026.10.29-map-scalability`, wskazujący
  oryginalny, wdrożony SHA `ecc14c1591fac142db1888917714dbb312bef3aa`.
- Usunięto **8 zdalnych gałęzi** w pełni zawartych w `main`,
  z kontrolą aktualnego SHA przed każdą operacją.
- **Domknięcie 29.10.2026:** usunięto także trzy rozbieżne zdalne gałęzie
  `work/dirty`, `work/interactive-onboarding-20261026` oraz
  `work/ai-public-observations-20261028` po zapisaniu na GitHub dokładnych
  historycznych HEAD jako lekkich tagów:
  `archive/2026-10-29/work-dirty` (`f47bff65d046`),
  `archive/2026-10-29/work-interactive-onboarding-20261026` (`a873af32e3d4`),
  `archive/2026-10-29/work-ai-public-observations-20261028` (`e8f5627e59d8`).
  Każdy tag zweryfikowano przed skasowaniem gałęzi; nie utracono historii.
  Zdalnie pozostaje tylko `main`. Trzy rozbieżne lokalne worktree
  pozostawiono celowo, bez ingerencji w ich dane.
- **Końcowa synchronizacja dokumentacji:** wyłącznie cztery pliki `docs/`
  zmienione po tagu wydania; wykonano fast-forward lokalnego `main` na
  Samsungu do zdalnego `main`, bez restartu procesu. Po operacji produkcyjny
  Git pozostał czysty, a `wreckscanner` miał `live=200`, `ready=200`.
- Nie usuwano produkcyjnych SQLite, WAL/SHM, zdjęć, sekretów,
  `.venv`, `node_modules` produkcyjnego, `.backups` ani danych
  Local Agenta. Brak force-push, squash i GitHub Actions.

## Znane ograniczenia / ryzyko zaakceptowane

1. **Backup jest tylko na Samsungu.** Właściciel 29.10.2026 zniósł wymóg
   off-host dla wdrożenia. Utrata telefonu może oznaczać utratę danych.
   Kopie w `IleStoi-Backups` i szyfrowany lokalny Restic są zachowane.
   Nie przeprowadzono pełnego odtworzenia wszystkich zdjęć.
2. Termux Chromium ma błąd linkowania biblioteki Androida; właściwy
   przebieg przeglądarkowy zrobiono na Macu, bez naprawiania toolchainu telefonu.
3. Przy dalekim zoomie admin/zaawansowane filtry pobierają szczegóły
   z ograniczeniem 40 stron. Historyczny endpoint bez `bbox` pozostaje
   dla zgodności ze starszymi klientami. Nie jest to gwarancja nieograniczonej
   skali w tych specjalnych trybach.
4. Testy produkcyjne są **odczytowe**. Nie wysyłano prawdziwych/próbnych
   zdjęć, nie usuwano rekordów i nie wykonywano produkcyjnego rollbacku.
   Te mutujące przepływy są objęte wcześniejszymi testami izolowanymi,
   ale ręczny smoke administratora pozostaje możliwy.
5. Nie przeprowadzono 24–48-godzinnej obserwacji; bieżący health i
   smoke nie zastępują monitoringu długoterminowego.

## Werdykt

Wydanie mapy jest **przyjętym produkcyjnym baseline jakościowym**.
Zestaw kodu, kontraktów i migracji jest bez nowych zmian po akceptacji;
spójność API, prywatność projekcji, stronicowanie, filtry i widok mapy
mają dowody testowe. Wymienione ograniczenia są jawne, a dalszy rozwój
powinien zaczynać się od aktualnego `main`, bez odtwarzania usuniętych
gałęzi eksperymentalnych.
