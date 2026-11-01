# IleStoi — skonsolidowany checkpoint galerii, zoomu i wydajności
Data: 2026-11-01 | Release: PR #30 | Procedura: Termux Local Agent + GitHub Connector

## Scope i punkt odniesienia
- Poprzednie wdrożone zmiany PR #24–29 obejmują galerię pojazdów, trzy wyłączne tryby dolnego panelu `map/gallery/none`, prawidłową obsługę popupów, priorytety 0–3 i sortowanie według najstarszej udokumentowanej obserwacji. Nie dublować ani nie cofać tej funkcjonalności.
- Produkcja przed release: `main` / Samsung Termux `1abb6fbf6953ee2a54b8efcfc0d5d7aa8baf812b`, czysty checkout i sześć usług runit, `/api/health/ready` HTTP 200.
- Gałąź wydania `fix/final-mobile-gallery-zoom-clearance-20261101`; zmiany reaudytu bazowały na niezmiennym `05ad1d8896afd78a2c0f18f67b1ad985d7a67f5e`. Końcowy SHA po formatowaniu/checkpoincie musi być osobno zatwierdzony w protokole cutover; nie przyjmować SHA z treści checkpointu.

## Domknięte elementy kandydata
1. Widoczny mobilny pasek galerii nie zasłania Leaflet +/−; po otwarciu popupu lub przejściu `map/none` styl automatycznie wraca do starego dolnego marginesu.
2. Oryginalny suwak mapy bez zmiany swojej implementacji; dane galerii sortowane według priorytetu administracyjnego i pierwszej obserwacji grupy, bez napisów pod miniaturami.
3. Żądania galerii identycznego bbox: współdzielenie poprawnego wyniku przez 5 sekund, brak duplikatów w locie, abort poprzedniego obszaru. Zmiana nominacji/języka unieważnia pamięć.
4. Źródła kafelków oraz przezroczysta warstwa nazw ulic: `updateWhenZooming: false` i `updateWhenIdle: true`; mniejsza liczba zapytań w trakcie gestu kosztem możliwego opóźnienia nowych kafelków podczas ciągłego przesuwania. Algorytm płynnego zoomu i przybliżenie pod kursorem bez zmian.
5. Oczyszczenie starszych asercji JS/Python, formatowanie Ruff w izolowanym worktree i dokumentacja publicznego kontraktu galerii.

## Dowody QA bazowego SHA 05ad1d8 (przed końcowym formatowaniem)
- Local Agent Samsung `ilestoi-gallery-perf-consolidated-qa-20261101-v1`: `npm ci` PASS, `lint:web` PASS, 94/94 JS PASS, Python galeria 7/7, frontend 37/37, field photo 43/43 PASS, architektura strict PASS, `git diff --check` PASS.
- Lokalny Ruff 0.17.3 w izolowanej ścieżce Termuxa: `ruff check` PASS; `ruff format --check` wykrył dokładnie 9 plików wymagających uporządkowania. Sformatowanie i recheck na nowym SHA są osobną bezwzględną bramką.
- Pełny Python `unittest discover`: 348 testów, 6 uruchomień Chromium nie przeszło wyłącznie przez lokalny dynamiczny linker Termuxa (`__ndk1::__hash_memory`), pozostałe 342 bez błędów. Na Macu na tym samym SHA **6/6 real Chrome PASS** (`ilestoi-gallery-perf-mac-browser-20261101-v1`).
- Mac Chrome — realny pomiar prostokątów z rzeczywistym CSS na minimalnym HTML: 320×568 i 390×844 PASS, przycisk +/- klikany i odsunięty od galerii o 48 px, po ukryciu galerii inset 56 px (`ilestoi-mobile-gallery-geometry-chrome-20261101-v1`). Nie jest to pełny E2E ze wszystkimi kafelkami ani pomiar FPS.
- Weryfikacja produkcji przed i po izolowanym QA: HEAD stabilny, drzewo czyste, gotowość HTTP 200.

## Otwarte ryzyka i dalszy backlog (nie blokuje samego UI, ale monitorować)
- `core/field_photo_map_query.py`: agregacja wieku grupy jest osobnym zapytaniem na nominację (N+1), a `LIMIT 100` jest stosowany przed finalnym sortowaniem po wieku grupy. Powyżej 100 nominacji poprawność rankingu wymaga osobnego redesignu i testu; dziś pięć nominacji.
- Rekonstrukcja markerów może kosztować czas CPU przy dużym bbox; należy wykonać porównawcze profile FPS/network w pełnej aplikacji na urządzeniu.
- Przed deployem sprawdzić, że brak zmiany schematu SQLite, konfiguracji runit, źródła suwaka i plików prywatnych. Unikać fałszywego twierdzenia, że funkcjonalny PASS dowodzi lepszych FPS.

## Kolejność wydania i gwarancje
1. Zatwierdzić **nowy** końcowy SHA po `ruff format`, dokumentacji i pełnej walidacji: Ruff lint/format, 94 JS, 342 Python bez lokalnego Chromium, 6 Chrome na Macu, architektura i diff.
2. Skontrolować czystość produkcji, runit, dysk, zgodność GitHub `main` i lokalnego `main` z bazą.
3. Przed cięciem zrobić spójny snapshot SQLite **przez SQLite Backup API** do `~/IleStoi-Backups/`, sprawdzić hash, `integrity_check` i FK oraz istniejący **zaszyfrowany** Restic z katalogami zdjęć. Zachować kod poprzedniej wersji i rollback.
4. Wyłącznie po PASS zatrzymać jedną usługę `wreckscanner`, wykonać chroniony fast-forward do dokładnego kandydata, ponownie uruchomić usługę i sprawdzić local live/ready, publiczną stronę, galerię i pozostałe pięć usług. Przy porażce powrócić do starego kodu i gotowości.
5. Dopiero po zaakceptowanym deployu przesunąć GitHub `main` do **dokładnie** wdrożonego SHA, nadać zweryfikowany, nieprzepisywany tag produkcyjny przez uprawniony Mac Local Agent i zakończyć PR.
6. Sprzątanie gałęzi: usuwać tylko ancestory `main`; unikalne rollbacki oznaczyć niezmiennymi tagami `archive/` przed usunięciem; gałąź `archive/restore-work-dirty-20261101` zachować jako archiwum, nie łączyć bez audytu. Lokalnie usuwać wyłącznie nieużywane, czyste i bezpiecznie zarchiwizowane gałęzie/worktree. Dane produkcyjne, kopie i sekrety pozostają nietknięte.

## Bezpieczeństwo i zakres
Brak GitHub Actions, Codex i ChatGPT Work. Wszystkie testy kodu Termux poza produkcyjnym checkoutem, Chrome na odrębnym Macu. Wdrożenie i czyszczenie wyłącznie pod kontrolą inwariantów HEAD/status/backup/runit.
