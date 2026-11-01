# IleStoi — checkpoint wydania: domyślna galeria zamiast suwaka

Data: **2026-11-01**. Tryb: GitHub Connector + Local Agent Samsung/Termux.
Przedmiot: tylko początkowy tryb dolnego panelu `gallery / map / none` oraz dokumentacja/testy. Brak migracji SQL, zmian w API, zdjęciach, sekretach, usługach runit lub kodzie intro.

## Stan bazowy

- Ostatni potwierdzony produkcyjny `main` przed sprintem: `db60a8b73f1e1f7734af3905d5ffbc8ffc8459b3`, poprzednie intro PR #31.
- Prace wyłącznie na `feature/gallery-default-20261101` (PR #32), w izolowanym worktree Termuxa; produkcyjny checkout `~/WreckScanner/WreckScanner` pozostaje na `main` podczas testów.
- Trzy dotychczasowe tryby, pamięć `wreckscanner.bottomDockMode.v1` i świadomy wybór użytkownika pozostają zachowane.

## Decyzja UX i kontrakt

1. Bez prawidłowej zapisanej preferencji pierwszą prezentacją jest **galeria pojazdów**, zarówno mobilnie, jak i na większych ekranach.
2. Świadomy zapis `map`, `gallery` lub `none` zawsze wygrywa z nowym domyślnym stanem.
3. Tylko **prawidłowa odpowiedź API z pustą listą po filtracji** na domyślnym wejściu uruchamia jednorazowe przejście do oryginalnego suwaka; nie zapisuje fallbacku w localStorage. Błąd HTTP/JSON nie jest utożsamiany z brakiem pojazdów.
4. Gdy publiczna funkcja jest niedostępna, niezapisane domyślne wejście pokazuje suwak. Wcześniej zapisany wybór galerii zachowuje istniejące zasady dostępu.
5. Istniejące ikony, przyciski, kropki podkładów, responsywne ramki, popupy i dostępność na telefonie nie zmieniają działania. Nie tworzymy drugiego układu ani nowych kluczy localStorage.

## Dowody QA — komendy i niezmienne task IDs

- Read-only preflight: `termux-ilestoi-gallery-default-preflight-20261101-v1`.
- Izolowane QA źródła: `termux-ilestoi-gallery-default-qa-20261101-v1` — `node --test tests/js/vehicle_gallery.test.mjs`, `npm ci`, `npm run lint:web`, `npm run test:web`, frontend Python, testy field photos, compile, diff-check, potwierdzenie produkcyjnego HEAD i runit.
- Testy regresji obejmują pierwszy widok, istniejące preferencje, prawidłowo pustą galerię, brak utrwalania fallbacku, ręcznie wybraną galerię i wyłączoną funkcję publiczną.
- **Nie uznawać samoistnego wysłania zadania za PASS.** Akceptację stanowią dopiero opublikowane `task-results/<id>.json` z `status=done`, `rc=0` oraz wynikiem bramek.

## Bramki wydania i rollback

1. Potwierdzenie SHA kandydata, ancestry względem bazy, czystego prod i izolowanego worktree oraz pozytywnych testów.
2. Aktualny Restic: zaszyfrowana kopia obu katalogów zdjęć, sprawdzenie integralności; osobny, prywatny snapshot SQLite przez Backup API z `integrity_check`, `foreign_key_check`, SHA-256. Zachować stare kopie bez usuwania.
3. Przed cutover zachować dokładny rollback SHA `db60a8b7` i listę zmienionych plików; nie dotykać prywatnych danych.
4. Jedno chronione przełączenie `git merge --ff-only <SHA>` na prod `main`, jeśli dotychczasowy HEAD jest oczekiwany, z testem local `/api/health/live`, `/api/health/ready`, `/`, plików galerii i stanu wszystkich usług runit. Nie uruchamiać drugiego serwera. Przy błędzie odtworzyć dokładny poprzedni commit **wyłącznie pod własną blokadą i po sprawdzeniu bieżącego HEAD**.
5. Dopiero po realnym PASS: przesunąć GitHub `main` do **tego samego** SHA (fast-forward, expected-SHA), opublikować nieprzepisywany tag przez autoryzowanego Mac Local Agenta, zweryfikować lokalny produkcyjny HEAD i publiczne endpointy.
6. Posprzątać tylko zintegrowaną gałąź `feature/gallery-default-20261101` i jej czysty izolowany worktree. Gałęzi z unikalnymi commitami lub archiwów nie usuwać; nie używać `git clean -fdx` w produkcji.

## Weryfikacja fizyczna i akceptacja produkcyjna (2026-11-01)

- **DEPLOY_LOCAL_PASS**, zadanie Termux Local Agent: `termux-ilestoi-gallery-default-guarded-release-20261101-v2`, status `done`, exit code `0`. Bazowy HEAD `db60a8b73f1e1f7734af3905d5ffbc8ffc8459b3` -> wdrożony i czysty produkcyjny HEAD `d46e67ccd55cd54dc88812dce8f942e9c6d9b28d` przez `git merge --ff-only`, bez nowego procesu serwera i bez restartu.
- Testy kandydata **na Samsung/Termux**: 24/24 celowane JS, 102/102 całe `npm run test:web`, 37/37 frontend Python, 43/43 field photo Python, `npm ci`, `lint:web`, kompilacja Python, `git diff --check` — **PASS**.
- Kopie: Restic 8 snapshotów, najnowszy miał 10,84 godziny, obejmował `zdjecia_terenowe` i `prywatne_zdjecia`, `restic check` zakończony **no errors**. Niezależny snapshot SQLite przez Backup API w `~/IleStoi-Backups/predeploy-gallery-default-20261101-v2/wreckscanner.sqlite3`, 622592 B, SHA-256 `d7e25dbcb8320c9485d5ce3593bb51692a6b3fa7715b377d542a5ca73cfb42e3`, integralność i klucze obce **OK**.
- Kod sprzed wdrożenia zachowany pod `~/.local/state/ilestoi-ops/gallery-default-20261101-v2/`. Dokładny rollback SHA: `db60a8b73f1e1f7734af3905d5ffbc8ffc8459b3`.
- Odbiór HTTP po cutover: `/`, `/app/vehicle_gallery.js`, `/styles.css`, `/api/health/live`, `/api/health/ready` → **200**. Wszystkie 6 usług `runit` online, te same PID przed i po.
- Wcześniejszy kandydat `2b80206` zatrzymał się na przestarzałym oczekiwaniu JS w teście mobilnego odsunięcia zoomu, **przed jakąkolwiek zmianą produkcji**. Poprawka testu na `d46e67c` przeszła ponownie 24/24 oraz pełną bramkę. Te negatywne próby pozostają w niezmiennych wynikach Local Agenta, nie są oznaczane PASS.
- Docelowa nazwa tagu wydania: `v2026.11.01-gallery-first-view`. Dokładny finalny commit dokumentacyjny musi być również wdrożony na Samsungu, a tag nie może być opublikowany przed weryfikacją identycznych HEAD `main` i produkcji. Potwierdzeniem tagowania i porządku gałęzi są osobne wyniki Local Agenta na Macu i Termuxie.

## Granice zamknięcia

Nie wykonano testów modyfikujących dane produkcyjne, próbnego restore całej galerii ani nowego pomiaru FPS. Publiczne wejście `https://ilestoi.pl/` odpowiada; widok mobilny/desktop zachowuje ten sam komponent. Dane, Restic, historyczne kopie, archiwa, Local Agent i cudze projekty pozostają nienaruszone.

Dalsze czyszczenie dotyczy wyłącznie czystych worktree związanych z intro i tym wydaniem oraz krótkotrwałej gałęzi po pełnym potwierdzeniu jej przynależności do `main`. Nie usuwać historycznych wyników QA ani archiwalnych kopii.
