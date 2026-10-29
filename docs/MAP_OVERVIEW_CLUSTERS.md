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

## Zintegrowany widok mapy (PR #7 i #8)

Backend agregatów z PR #7 i frontend z PR #8 znajdują się już razem w
[kandydacie PR #9](https://github.com/MichalMatu/ilestoi/pull/9).
Przy zoomie ≤10 gość widzi syntetyczne pinezki z liczbą zdjęć;
kliknięcie przybliża odpowiednie pole siatki. Przy zoomie ≥11
mapa pobiera stronicowane zdjęcia widocznego obszaru i pokazuje szczegóły.
Administrator, bezpośredni link do zdjęcia i zaawansowane filtry pojazdów
korzystają z trybu szczegółowego również przy małym zoomie.

Przełączniki warstw ograniczają liczbę zdjęć prezentowaną w skupiskach.
Skupiska nie oznaczają liczby pojazdów. Liczniki grup podczas widoku
ogólnego pokazują pauzę, ponieważ API agregatów nie zwraca liczby grup.

## Zasady wydania

Sam endpoint agregatów nie wymaga dodatkowej migracji. Połączony PR #9
wymaga jednak indeksu z migracji `006_field_photo_map_seek`
dla stronicowanego API zdjęć. Backend i frontend należy wdrożyć razem,
dopiero po weryfikacji backupu, możliwości restore i rollbacku na Samsungu.
Do tego czasu `main` nadal odpowiada zaakceptowanej produkcji.
