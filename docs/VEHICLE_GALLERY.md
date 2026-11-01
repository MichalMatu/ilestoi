# Galeria pojazdów — dolny panel

Dolny panel jest przełącznikiem trójstanowym: `map`, `gallery`, `none`. To **jedyne źródło prawdy** o widoczności. Dwa checkboxy w istniejącym menu pokazują stan, nie osobne preferencje. Kliknięcie wybranej opcji wyłącza ją, a kliknięcie drugiej automatycznie odznacza poprzednią. Stan zapamiętany jest przez `MAP_DOCK_MODE_STORAGE_KEY` (localStorage).

- `map`: oryginalny suwak podkładów (bez zmian HTML/CSS suwaka).
- `gallery`: galeria pojazdów; oryginalny suwak ukryty; dolna linia kropek podkładów jako pomocnicza kontrolka, bez drugiego zaznaczenia w menu.
- `none`: oba panele ukryte, czysta mapa.

## Domyślny panel po wejściu (wydanie 2026-11-01)

Przy **braku zapisanej preferencji** początkowym panelem jest `gallery`, na telefonie i desktopie. Zdjęcia są ładowane z bieżącego zasięgu mapy, bez osobnego zapytania dla intro. Suwak podkładów pozostaje pod istniejącym przełącznikiem oraz pod kropkami w galerii.

- Jeżeli w localStorage istnieje prawidłowy tryb `map`, `gallery` lub `none`, użytkownik zachowuje ten wybór — nie nadpisujemy go nową wartością domyślną.
- Kiedy serwer **poprawnie zwróci pustą** galerię w pierwszym domyślnym widoku (brak zatwierdzonych/wyróżnionych zdjęć w bbox), zamiast pustego panelu pokazujemy istniejący suwak. Automatyczne przełączenie jest tylko na bieżącą wizytę i **nie zapisuje** ustawienia. Kolejne wejście nadal próbuje galerii.
- Gdy galeria jest wyłączona przez ustawienia publiczne, pierwsze wejście pokazuje suwak; późniejsze przywrócenie dostępności może ponownie udostępnić domyślną galerię. Zachowany, świadomy wybór `gallery` ma dotychczasową politykę dostępności.
- Błąd sieci albo ręczny wybór galerii **nie** wywołuje automatycznego fallbacku na suwak. Przełącznik trybów i zachowanie popupów pozostają bez zmian.

W menu użytkownika: **„Galeria pojazdów”**. Bez osobnego przycisku otwierania i bez pływającej gwiazdki. Brak dostępu do funkcji publicznej wyłącza wybór galerii; widok może wrócić do `none`, lecz nie pokazuje zablokowanych danych. Poprzednie niezależne klucze `mapSourceSliderVisible` i `vehicleGalleryVisible` nie są już odczytywane.

Administrator wyróżnia zdjęcie bezpośrednio w popupie pojazdu. Każda miniatura korzysta z tego samego zakotwiczonego przycisku SVG w prawym górnym rogu (stały rozmiar i margines). Priorytety: 0 = poza galerią, 1 = wyróżniony, 2 = wysoki, 3 = pilny. Zaznaczenie jednej zatwierdzonej fotografii zastępuje poprzednie wyróżnienie w istniejącej 1-metrowej grupie. Publiczna galeria pokazuje maksymalnie 10 pozycji w bieżącym bbox, a endpoint zwraca najwyżej 100 kandydatów. Nie ujawnia niezatwierdzonych ani oryginalnych zdjęć.

Testy regresyjne obejmują przejścia stanów, odświeżenie, brak dostępu, synchronizację checkboxów, oznaczenia zdjęć, SVG i układ mobilny. Na produkcję tylko po izolowanym QA w Termuxie, backupie i akceptacji.

## Zachowanie przy interakcji z mapą

Wybrany tryb `gallery` jest trwałą preferencją. Dotknięcie mapy ani miniatury w galerii **nie** przełącza trybu na `none`. Wybranie miniatury ustawia cel na mapie i otwiera istniejący popup pojazdu; na czas widocznego popupu galeria zostaje **tymczasowo ukryta** (bez odznaczania checkboxa i bez zapisu innego trybu). Zdarzenie Leaflet `popupclose` przywraca ten sam panel. Tryb `none` lub `map` można wybrać tylko z istniejącego menu. Zmiana trybu podczas popupu ma pierwszeństwo nad automatycznym przywróceniem. Oryginalny suwak i jego CSS bez zmian.

## Kolejność i podpisy w galerii

Galeria pokazuje **wyłącznie fotografie**, bez stałych podpisów priorytetu pod miniaturami (etykieta pozostaje dostępna dla czytników ekranu). Kolejność od lewej do prawej: poziom administracyjny `3` (pilny), `2` (wysoki), `1` (wyróżniony); w obrębie poziomu starsza **najwcześniejsza udokumentowana obserwacja pojazdu** jest pierwsza. Data bierze się z zatwierdzonych, aktywnych zdjęć w tej samej grupie (1 m): prawidłowy czas wykonania zdjęcia, a jeśli go brak — dodanie lub zgłoszenie. Nie utożsamiać wieku dokumentacji z nieprzerwanym postojem. Brak poprawnej daty daje miejsce za autami z udokumentowaną datą w obrębie tego samego priorytetu. Tę samą kolejność egzekwują publiczny endpoint i klient (również przed deduplikacją); rozstrzygnięcie pełnego remisu po identyfikatorze. Nie zmienia to struktury suwaka ani ustawień mapy.

## Wydajność galerii i zoomu — kandydat PR #30

- Frontend ponownie wykorzystuje poprawną odpowiedź dla identycznego bbox przez maksymalnie 5 sekund, pomija równoległe identyczne odpytywanie i nadal anuluje nieaktualne żądania po przejściu do innego obszaru.
- Zmiana nominacji administratora i języka unieważnia pamięć wyniku. Wyłączenie panelu nie zmienia zapisanej preferencji.
- Kafelki podkładów (OSM/POL/ortofoto WMS) i opcjonalnej warstwy nazw ulic nie pobierają nowych kafelków podczas ruchu ani nie przeliczają siatki w trakcie animacji przybliżania; aktualizują je po zakończeniu gestu. To celowy kompromis: przy bardzo długim przeciąganiu może być widoczny poprzedni zestaw kafelków do momentu zwolnienia mapy. Sam kontroler płynnego zoomu nie zmienia algorytmu ani czasu gestu.
- Są to optymalizacje kandydata, a nie potwierdzony wynik pomiarów produkcyjnych. Przed wdrożeniem potrzebna jest izolowana walidacja Chrome, liczby żądań kafelków, działania wszystkich podkładów oraz JS/Python QA.
- Osobny długoterminowy punkt: zapytanie historii grup w API galerii wykonywane jest dziś dla każdego wyróżnienia, a kolejność po najstarszej obserwacji ustalana jest dopiero po SQL LIMIT 100. Przy większej liczbie nominacji potrzebna jest wydajniejsza agregacja zachowująca poprawną kolejność.
