# Aktualny Kontrakt Bazy Danych

Ten dokument opisuje produkcyjny model SQLite uzywany przez IleStoi.pl.
Aktywnym zrodlem prawdy jest `wreckscanner.sqlite3`; historyczne JSON-y nie sa
czescia biezacego runtime ani bramka zgodnosci danych.

## Storage

SQLite dziala w trybie WAL:

- jeden lokalny operator i lokalny katalog zdjec nie wymagaja PostgreSQL,
- baza, publiczne pochodne i prywatne oryginaly tworza jeden logiczny stan,
- migracje SQL sa wersjonowane w `database/migrations/`,
- runtime nie tworzy tabel poza tym kontraktem.

Pliki obrazow pozostaja na dysku. Baza przechowuje ich bezpieczne sciezki
wzgledne, metadane i stan review. Hash tokenu autora istnieje tylko do
ostatecznej decyzji moderacyjnej.

## Tabele Domenowe

`field_photos`

- `id`, `created_at`, `submitted_at`, `captured_at`,
- `issue_type`,
- `vehicle_insurance_status`, `vehicle_insurance_checked_at`,
- `vehicle_resolution_status`, `vehicle_resolution_updated_at`,
- `vehicle_gallery_priority` (`0` = bez wyróżnienia, `1` = wyróżniony, `2` = wysoki priorytet, `3` = pilny),
- `lat`, `lon`, `coordinate_source`, `position_updated_at`,
- `public_review_status`, `reviewed_at`, `redactions_json`,
- metadane oryginalu i publicznych pochodnych,
- `submission_owner`, hash i salt tokenu edycji,
- `links_json`, `updated_at`.

`settings`

- `key`,
- `value_json`,
- `updated_at`.

`privacy_requests`

- `id`, `created_at`, `updated_at`,
- `status`,
- `email`, `target`, `reason`,
- `handled_at`, `admin_note`.

Po 90 dniach od zamkniecia albo odrzucenia zgłoszenia pola `email`, `target`,
`reason` i `admin_note` sa zerowane przez wspolny przebieg retencji.

`schema_migrations` jest jedyna tabela techniczna dopuszczona obok tabel
domenowych. Rejestruje dokladnie migracje dostepne w `database/migrations/`.

## Czego Nie Modelowac

Nastepujace rzeczy nie sa tabelami ani trwalym API bazy:

- `reports`,
- `report_packages`,
- `public_report_packages`,
- `map_crops`, `report_crops`, `evidence_crops`,
- `wrecks`, `vehicle_cases`, `cases`,
- `evidences`.

Raport PDF i cropy mapy sa jednorazowym wynikiem skladanym z aktualnych danych
zdjec terenowych. Nie tworza osobnej encji ani stalego katalogu runtime.

## Walidacja Produkcyjna

```bash
./.venv/bin/python scripts/migrate_json_to_db.py --validate-only
```

Mimo historycznej nazwy skryptu tryb `--validate-only` nie czyta JSON-ow i nie
modyfikuje bazy. Sprawdza:

- `PRAGMA quick_check`,
- `PRAGMA foreign_key_check`,
- zgodnosc `schema_migrations` z plikami migracji,
- istnienie wszystkich plikow wskazanych przez rekordy `field_photos`,
- liczniki aktywnych tabel domenowych.

Brakujaca, nadmiarowa lub uszkodzona migracja oraz brak wskazanego pliku blokuja
walidacje.

## Jawny Import Legacy

Import `record.json`, `settings.json` i `zgloszenia_prywatnosci/` jest dostepny
wylacznie jako kontrolowana operacja historyczna:

```bash
./.venv/bin/python scripts/migrate_json_to_db.py --migrate-legacy-json
```

Import wymaga istniejacego snapshotu restic. Flaga `--skip-backup-check` jest
przeznaczona tylko dla izolowanych testow lub przygotowanego restore dry-run.
Nie uruchamiaj importu w zwyklym deployu, backupie ani diagnostyce produkcyjnej.
Po migracji SQLite pozostaje jedynym zrodlem prawdy.
