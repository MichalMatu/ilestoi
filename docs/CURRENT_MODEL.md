# Current Data And UX Model

Ten dokument opisuje aktualny wzorzec dzialania IleStoi.pl po usunieciu starego
modelu trwalych spraw pojazdow.

## Zrodlo prawdy

- `wreckscanner.sqlite3` - aktywny stan aplikacji: `field_photos`,
  `settings`, `privacy_requests`.
- `zdjecia_terenowe/` - publiczne pliki zdjec terenowych i katalogi robocze
  pochodnych obrazow.
- `prywatne_zdjecia/field_photos/` - prywatne oryginaly zdjec terenowych.
- `settings.json` i `zgloszenia_prywatnosci/` - format importu/migracji i
  backup historyczny, nie aktywny runtime.

Kazde zdjecie terenowe musi miec jawne `issue_type`. Warstwa pojazdow jest
budowana z zatwierdzonych zdjec terenowych o `issue_type: "vehicle"`.
Status OC/UFG jest recznie zapisywany jako `vehicle_insurance_status`:
`unknown`, `insured` albo `uninsured`. Dla recznie sprawdzonych statusow
`insured` i `uninsured` aplikacja zapisuje tez `vehicle_insurance_checked_at`,
czyli date zapisania wyniku sprawdzenia w UFG. Aplikacja nie pobiera danych z UFG automatycznie
i nie zapisuje tablic ani VIN.

Status skutecznosci zgłoszenia pojazdu jest zapisany bez osobnej encji sprawy
jako `vehicle_resolution_status`: `active` albo `removed`. Domyslnie kazde
zdjecie pojazdu jest `active`; przy zmianie statusu aplikacja zapisuje
`vehicle_resolution_updated_at`. Usuniety pojazd moze pozostac na mapie jako
zanonimizowany wpis sukcesu ukryty domyslnie filtrem warstwy pojazdow.

## Aktualne przeplywy

- Dodanie materialu tworzy rekord `field_photos` w SQLite z tokenem edycji.
- Publiczny upload uzytkownika najpierw tworzy szkic `draft`; wlasciciel moze
  go zanonimizowac, wyslac do weryfikacji albo usunac tokenem.
- Po wyslaniu do weryfikacji rekord przechodzi do `pending`. Pozostaje widoczny
  na mapie zgodnie z ustawieniami warstw, a wlasciciel z poprawnym tokenem moze
  nadal edytowac anonimizacje albo usunac swoje oczekujace zgloszenie.
- Administrator zatwierdza albo odrzuca zdjecia w jednej kolejce photo review.
- Ostateczna decyzja `approved` albo `rejected` usuwa identyfikator wlasciciela
  i hash tokenu; token nie moze ponownie otworzyc zakonczonej moderacji.
- Pojazdy na mapie sa grupami zatwierdzonych zdjec terenowych, nie osobnymi
  rekordami spraw.
- Zmiana OC/UFG w panelu admina aktualizuje wszystkie zdjecia pojazdu w tej
  samej grupie mapy. Edycja wlasciciela przez token dotyczy tylko jego zdjecia
  i wraca do kolejki review.
- Administrator moze oznaczyc grupe pojazdu jako usunieta albo przywrocic ja
  jako aktywna. Grupa jest traktowana jako usunieta tylko wtedy, gdy wszystkie
  zatwierdzone zdjecia pojazdu w tej grupie maja `vehicle_resolution_status:
  "removed"`.
- Publiczna mapa domyslnie ukrywa usuniete pojazdy, ale tray filtrow warstwy
  `Pojazdy` pozwala je pokazac albo wyswietlic tylko usuniete.
- Administrator może wyróżnić wybrane zatwierdzone zdjęcie pojazdu do publicznej galerii
  przez gwiazdkę na miniaturze w popupie mapy. Wyróżnienie ma poziom 1–3 i
  automatycznie zastępuje poprzednią okładkę w istniejącej grupie zdjęć;
  zdjęcia pojazdów usuniętych nie pojawiają się w galerii.
- Publiczna galeria pobiera maksymalnie 100 kandydatów z bbox w odczycie SQLite,
  po czym prezentuje maksymalnie 10 reprezentatywnych miniatur.
- Zgloszenie PDF jest generowane na zadanie z listy `field_photo.id` i
  wspolrzednych grupy.
- Backend odrzuca mieszane grupy, usuniete pojazdy, wspolrzedne inne niz
  polozenie grupy oraz przekroczenie limitu liczby lub rozmiaru zdjec.
- Zgloszenie zawiera tekstowy wynik recznego sprawdzenia OC/UFG oraz date
  sprawdzenia w tresci PDF.
- Zgloszenie PDF nie jest generowane dla grupy oznaczonej w calosci jako
  usunieta.
- Miniatury ortofoto sa dowodem generowanym podczas tworzenia raportu PDF.
- Raporty PDF i cropy mapy nie sa zapisywane w DB ani w stalym
  katalogu runtime.
- Dane kontaktowe i tresc zakonczonych zgloszen prywatnosci sa automatycznie
  zerowane po 90 dniach; pozostaje minimalny rekord statusu i dat obslugi.

## Endpointy domenowe

Ponizsza tabela jest pelnym kontraktem routingu aplikacji. "Publiczny" oznacza
brak wymaganej sesji administratora; wlaczniki funkcji publicznych, limity i token
edycji nadal moga ograniczyc operacje.

| Metoda | Sciezka | Dostep | Zastosowanie |
| --- | --- | --- | --- |
| `GET` | `/api/ai/openapi.json` | publiczny | schemat OpenAPI generatora dla klientow AI |
| `POST` | `/api/ai/report-pdf` | publiczny lub administrator | JSON -> PDF Base64 przez istniejacy zweryfikowany generator |
| `GET` | `/api/health/live` | publiczny | liveness procesu HTTP |
| `GET` | `/api/health/ready` | publiczny | szybki odczyt SQLite, zgodnosc migracji i tabel, prawa katalogu, wolne miejsce; bez audytu plikow zdjec |
| `GET` | `/api/settings` | publiczny | aktywne ustawienia i wartosci domyslne |
| `POST` | `/api/settings` | administrator | zapis ustawien aplikacji |
| `GET` | `/api/admin/status` | publiczny | stan logowania bez ujawniania sekretow |
| `POST` | `/api/admin/login` | publiczny | rozpoczecie sesji administratora |
| `POST` | `/api/admin/logout` | publiczny (cookie opcjonalne) | uniewaznienie biezacego tokenu i cookie |
| `GET` | `/api/field-photos` | publiczny | mapa bez szkicow i odrzuconych; administrator omija publiczne filtry warstw |
| `GET` | `/api/field-photos/gallery?bbox=...` | publiczny | wyróżnione, zatwierdzone aktywne pojazdy w obszarze mapy; funkcja może być wyłączona |
| `GET` | `/api/field-photos/:id/public-image` | publiczny | zatwierdzony obraz publiczny |
| `GET` | `/api/field-photos/:id/public-thumb` | publiczny | zatwierdzona miniatura publiczna |
| `POST` | `/api/field-photos` | publiczny lub administrator | pojedynczy upload `multipart/form-data`; funkcja publiczna moze byc wylaczona |
| `POST` | `/api/field-photos/owner-claim` | token edycji | pobranie szkicow wlasciciela do edycji |
| `POST` | `/api/field-photos/owner-submit` | token edycji | atomowe wyslanie szkicow do moderacji |
| `POST` | `/api/field-photos/owner-discard` | token edycji | porzucenie szkicow |
| `POST` | `/api/field-photos/owner-delete` | token edycji | usuniecie wlasnych szkicow lub oczekujacych zdjec |
| `POST` | `/api/field-photos/:id/owner-original` | token edycji | pobranie prywatnego oryginalu przez wlasciciela |
| `PATCH` | `/api/field-photos/:id/owner-review` | token edycji | zapis anonimizacji i OC/UFG przez wlasciciela |
| `PATCH` | `/api/field-photos/:id/location` | administrator | korekta lokalizacji zdjecia |
| `POST` | `/api/field-photo-reports/report-pdf` | publiczny lub administrator | raport PDF z zatwierdzonych zdjec; funkcja publiczna moze byc wylaczona |
| `GET` | `/api/address/reverse?lat=:lat&lon=:lon` | publiczny | adres PRG z kontrolowanym fallbackiem Nominatim |
| `GET` | `/api/cadastral/identify?lat=:lat&lon=:lon` | publiczny lub administrator | identyfikacja dzialki; warstwa publiczna moze byc wylaczona |
| `POST` | `/api/inspect` | publiczny | tymczasowe wycinki ortofoto dla wskazanego punktu |
| `POST` | `/api/privacy-requests` | publiczny | utworzenie zgloszenia prywatnosci |
| `GET` | `/api/admin/photos` | administrator | filtrowana kolejka moderacji |
| `GET` | `/api/admin/photos/field/:id/original` | administrator | prywatny oryginal do moderacji |
| `PATCH` | `/api/admin/photos/field/:id/review` | administrator | decyzja, anonimizacja, OC/UFG i rozwiazanie grupy |
| `DELETE` | `/api/admin/photos/field/:id` | administrator | kanoniczne usuniecie zdjecia i jego plikow |
| `GET` | `/api/admin/privacy-requests` | administrator | kolejka zgloszen prywatnosci |
| `PATCH` | `/api/admin/privacy-requests/:id` | administrator | obsluga zgloszenia prywatnosci |
| `GET` | `/api/admin/photo-retention` | administrator | stan automatycznej retencji |
| `POST` | `/api/admin/photo-retention/run` | administrator | reczny dry-run albo wykonanie retencji |
| `GET` | `/wms_proxy/OGC_ortofoto_:year/MapServer/WMSServer?...` | publiczny | ograniczony proxy `GetMap` dla lat 2020-2025 |
| `GET` | `/tile_proxy/geoportal-standard/:z/:x/:y?...` | publiczny | ograniczony proxy kafli WMTS Geoportalu |

`HEAD` jest obslugiwany dla stron, statycznych zasobow i tras `GET /api/*` z
takim samym statusem oraz naglowkami, ale bez body; kosztowne lookupy zuzywaja
ten sam limit co `GET`. `OPTIONS` zwraca `204`.
Nieznane trasy API zwracaja JSON `404`, a `PUT`, `TRACE` i `CONNECT` - `405`.

Kazda mutacja przechodzi kontrole same-origin na podstawie `Origin` i
`Sec-Fetch-Site`. Trasy JSON wymagaja `application/json` i maja limit body 1 MiB;
upload zdjecia i przegladarkowy generator PDF przyjmuja `multipart/form-data` i
maja osobne, nizsze limity domenowe. Nowy adapter AI przyjmuje `application/json` z limitem 1 MiB, korzysta z tych samych ograniczen i walidacji generatora. Limity per klient wynosza: logowanie 5/10
min, upload 30/h, operacje tokenu wlasciciela 120/15 min, zgloszenia prywatnosci
10/h, raporty 12/15 min, lookupy mapowe 180/10 min, kafle proxy 2400/10 min.

`PATCH /api/admin/photos/field/:id/review` moze zapisac sama decyzje
`vehicle_resolution_status` bez zmiany statusu moderacji lub redakcji. Taka
aktualizacja obejmuje cala grupe pojazdu w promieniu grupowania mapy.

Nie ma publicznego ani administracyjnego API `/api/wrecks`. Kontrakt AI: [AI_API.md](AI_API.md).

## Zakazane artefakty

Te nazwy nie powinny wystepowac w kodzie runtime ani dokumentacji aktualnego
modelu:

- `/api/wrecks`
- `WRECKS_DIR`, `WRECKS_URL`, `WRECKS_ROUTE`
- `zidentyfikowane_wraki`
- `wreck_photos`
- `attached_wreck`
- `saved_wrecks`
- `wreck_review`
- `manual_wrecks`
- `vehicle case` jako encja aplikacji

Wyjatkiem sa testy antyregresyjne, ktore sprawdzaja, ze te nazwy nie wracaja,
oraz [aktualny kontrakt bazy](DATABASE.md), ktory wymienia wycofane tabele jako
niedozwolone.

## Audyt domkniecia

```bash
rg -n -i '(/api/wrecks|zidentyfikowane_wraki|wreck_photos|attached_wreck|saved_wreck|saved-wreck|manual_wreck|WRECKS_DIR|WRECKS_URL|WRECKS_ROUTE|saved_wrecks|wreck_review)' app core scripts web README.md pyproject.toml

test ! -e zidentyfikowane_wraki
test ! -e prywatne_zdjecia/wreck_photos
test ! -e prywatne_zgloszenia

./.venv/bin/python scripts/migrate_json_to_db.py --validate-only

./scripts/check.sh
```

Oczekiwany wynik: walidacja aktywnej SQLite pokazuje `quick_check: ok`, komplet
migracji, brak naruszen kluczy obcych i `Brakujace sciezki: 0`. Historyczne
JSON-y nie sa porownywane z baza. Katalogi starego modelu nie istnieja,
diagnostyka danych nie widzi starych pakietow raportow, a `scripts/check.sh`
konczy sie statusem OK.
