# IleStoi.pl — końcowy audyt starej nazwy WreckScanner, S22

Status: **PASS (tylko odczyt)** · 14 listopada 2026 · S22 pozostawiony bez zmian · brak autostartu nowych usług, schedulera, backupu i migracji nazwy.

## Ustalony stan i zależności

- Produkt i domena kanoniczna: **IleStoi.pl**. `WreckScanner` jest *historyczną nazwą techniczną tego samego produktu*; repozytorium `MichalMatu/WreckScanner` przekierowuje na `MichalMatu/ilestoi`.
- Działający katalog S22: `~/WreckScanner/WreckScanner`. Wersja lokalnego checkoutu: `b31b8f57684a1ff0e916de5f6e6146a78faaa831` na `main`. **GitHub `main` był na `ea1b300351d6519ba387d08cb22d6aea2b204d2c` — 16 commitów za produkcją**, potwierdzone porównaniem GitHub. To rozbieżność stanu źródeł, nie potwierdzona awaria runtime. Nie scalać jej automatycznie z gałęzią tej dokumentacji; nie zmieniać HEAD produkcyjnego.
- Runit S22: `wreckscanner` RUN (główny Python/HTTP na 127.0.0.1:8001); `ilestoi-healthwatch`, `cloudflared`, `sshd`, `mosquitto` RUN; `wreckscanner-backup` DOWN; usługi `pockethost-panel` i `pockethost-panel-watch` nie są zarejestrowane. Autostart `~/.termux/boot/00-services` nadal wspomina `wreckscanner`; `90-local-agent` pozostaje osobny.
- Baza danych: `~/WreckScanner/WreckScanner/wreckscanner.sqlite3`, 667 648 B i **393 rekordy field_photos** w odczycie SQLite `mode=ro`. Katalogi `zdjecia_terenowe/` i `prywatne_zdjecia/` istnieją. **Nie zmieniać nazwy bazy ani katalogów** bez zaplanowanej migracji danych i ścieżek.
- `WRECKSCANNER_*`: 15 identyfikatorów środowiskowych w śledzonym kodzie, m.in. host, port, proxy, administrator, CORS i ustawienia cache. Prefiks jest kontraktem konfiguracji; samo masowe zastąpienie może zepsuć uruchamianie.
- Śledzone źródła: **64 pliki** zawierały `wreckscanner`, 50 — `ilestoi`. To nie oznacza 64 miejsc wymagających refaktoryzacji: obejmuje też dokumentację i testy.
- Cloudflare ingress na S22 zawiera `ilestoi.pl`, `wreckscanner.pl`, `dlugostoi.pl` i port backendu 8001. Stare domeny to zgodne aliasy/redirecty; zmiana wymagałaby zsynchronizowania ingress, DNS, aplikacji i SEO. **Nie usuwać aliasów.**
- Po audycie loopback `/api/health/live` i `/api/health/ready` zwróciły **200**. Nie wykonywano żądań zapisujących, restartów ani zmian konfiguracji.

## Backup — historyczny opis a obecny stan

- Restic nie działa: `wreckscanner-backup` jest DOWN, `.backups/wreckscanner-restic` i `.restic_password` **nie istnieją**.
- Właściciel usunął z Android Downloads foldery `Termux-Recovery/Plain-20261114-v1` i `Termux-Recovery/Project-Native-20261114-v1`, opróżnił kosz; kontrola potwierdziła nieobecność tych ścieżek.
- Prywatny `~/IleStoi-Backups` **nadal istnieje** (historyczne kopie SQLite, bez kompletnej aktualnej kolekcji zdjęć). Nie traktować tego jako aktualnego punktu pełnego odtworzenia ani jako kopii off-device. Nie ma potwierdzonej aktualnej kompletnej kopii IleStoi poza telefonem — jawne ryzyko utraty danych w razie awarii urządzenia.
- Stare sekcje `docs/TERMUX.md`, `docs/BACKUP.md` i wcześniejsze zasady `AGENTS.md` opisywały aktywny Restic/timer i mogły wprowadzić w błąd. Ta dokumentacja aktualizuje opis stanu, **nie** instaluje alternatywnego backupu i nie uruchamia schedulera.

## Ocena zmiany nazwy i decyzja końcowa

Pełna migracja `WreckScanner` → `IleStoi` jest **trudna operacyjnie** (szacunkowo 7/10), bo dotyka bazy, ścieżek, runit/Boot, zmiennych środowiskowych, healthwatch i starych domen. Ryzyka: niedostępność backendu, nieodczytana baza, utrata autostartu po reboot, regresja domen/SEO, trudny rollback przy braku potwierdzonej pełnej kopii poza S22. Wartość dla użytkownika jest dziś przede wszystkim kosmetyczna.

**Decyzja:** zachować `WreckScanner` jako historyczne wewnętrzne ID, a `IleStoi` jako nazwę produktu; **nie przeprowadzać migracji teraz**. Nie uruchamiać więcej zadań na S22 dla PocketHost. Ten dokument jest zapisem odczytu, a nie bramką do zmiany produkcyjnego SHA.

## Dalszy kierunek

PocketHost będzie instalowany od zera na **Samsung Galaxy A8**, wyłącznie przez jego istniejącego Local Agenta. [Checkpoint S22/PocketHost](https://github.com/MichalMatu/PocketHost/blob/main/docs/checkpoints/2026-11-14-s22-retired-a8-bootstrap-handoff.md) i [handoff A8](https://github.com/MichalMatu/PocketHost/blob/main/docs/HANDOFF_NEXT_CHAT.md). Produkcyjne PhotoMap i jego niezależna kopia pozostają na Raspberry Pi Zero 2 W.
