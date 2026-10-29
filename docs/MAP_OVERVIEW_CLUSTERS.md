# Serwerowe agregaty mapy (widok ogólny)

## Kontrakt

`GET /api/field-photos/clusters?bbox=west,south,east,north`

Odpowiedź `200` zawiera `{"status":"ok","clusters":[...]}`. Każde pole
siatki ma współrzędne `lat`, `lon` **środka pola**, a także liczbę
`total` i liczniki `vehicles`, `infrastructure`, `smoke`, `pending`.
Wszystkie liczniki oznaczają **zdjęcia**, nie pojazdy ani grupy oddalone
o 1 m. Nie zwracamy identyfikatorów zdjęć, ścieżek, tokenów ani faktycznych
współrzędnych pojedynczego zdjęcia. Stała siatka 16 × 16 daje maksymalnie
256 obiektów, niezależnie od liczby rekordów w bazie.

`bbox` jest wymagany, w tej samej postaci co w API stronicowanych zdjęć
z PR #3. Prostokąty przekraczające południk 180° są obsługiwane. Puste,
wielokrotne lub nieprawidłowe parametry zwracają `400`.

## Ochrona danych

Zapytanie wykonuje grupowanie w **trybie SQLite tylko do odczytu**. Stosuje
dokładnie te same SQL-owe zasady warstw i zatwierdzenia co dotychczasowe
`GET /api/field-photos`: dla gościa wyłączona warstwa nie jest liczona;
`pending` jest liczone wyłącznie przy włączonej warstwie oczekujących;
`draft` i `rejected` nigdy nie trafiają do wyniku. Administrator widzi
dopuszczone wszystkie kategorie. Wynik nie sprawdza odrębnie na dysku
pochodnych plików zdjęcia, ponieważ agregacja nie otwiera zdjęć.

Nie jest potrzebna nowa tabela, indeks ani migracja bazy. Query pozostaje
ograniczone do wskazanego `bbox`; nie pobiera publicznych obrazów ani pełnej
projekcji rekordów.

## Kolejność wdrożenia

Ta funkcja jest dodatkiem backendowym do PR #3. **Nie zastępuje jeszcze
wyświetlania pinezek w frontendzie**. Przed podłączeniem mapy do agregatów
potrzebny jest osobny krok UX: syntetyczne pinezki, obsługa kliknięcia
przybliżającego mapę, różnica między liczbą zdjęć a liczbą pojazdów,
zachowanie filtrów i przejście do szczegółowego API przy większym zoomie.

Wydanie z PR #2–#6 powinno być testowane i wdrażane w ustalonej kolejności;
ten endpoint nie może powodować automatycznego restartu, migracji ani
zmiany produkcyjnego `main` przed przyjęciem wydania.
