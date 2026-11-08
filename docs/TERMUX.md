# IleStoi.pl na Termuxie (Samsung Android)

Stan operacyjny: 29.10.2026, po migracji startu na `runit`.
Katalog produkcyjny: `~/WreckScanner/WreckScanner`; zatwierdzona produkcja
odzwierciedlona przez `main` (zamiast wycofanej gałęzi `work/dirty`). Python Termuxa 3.14, poza macierzą CI 3.11/3.13.

## Autostart i własność procesów

`~/.termux/boot/00-services` jest jedynym skryptem bootowania
**aplikacji i pomocniczych usług**. Zawiera wake lock, w razie potrzeby
uruchamia standardowy `service-daemon` Termux Services i wysyła
idempotentne `sv up`, bez `nohup` i ręcznie forkujących procesów.

Pod standardowym `$PREFIX/var/service` działają dokładnie następujące
usługi `runit`:

| Usługa | Rola |
| --- | --- |
| `wreckscanner` | serwer HTTP 127.0.0.1:8001 |
| `wreckscanner-backup` | lokalne kopie Restic |
| `cloudflared` | nazwany tunel `ilestoi-phone` |
| `sshd` | SSH Termuxa na porcie 8022 |
| `mosquitto` | MQTT tylko na 127.0.0.1:1883 |
| `ilestoi-healthwatch` | cykliczny health-check i ograniczone samonaprawianie tunelu |

**Nie modyfikować** `~/.termux/boot/90-local-agent`: to osobny
uruchamiacz oddzielnego `runsvdir` Local Agent, nie supervisor IleStoi.
Dwa niezależne drzewa runit są zamierzone; dla każdej usługi aplikacji
jest natomiast tylko jeden właściciel procesu.

Wersjonowane odpowiedniki plików produkcyjnych:
`deploy/termux/00-services.sh`,
`deploy/termux/cloudflared.run`,
`deploy/termux/mosquitto.run`,
`deploy/termux/ilestoi-healthwatch.run` i
`deploy/termux/ilestoi-healthwatch.py`.
Skrypty nie zawierają sekretów; rzeczywiste poświadczenia tunelu
pozostają wyłącznie na telefonie. Aktualizacja pliku źródłowego w Git
**nie aktualizuje** działającej konfiguracji telefonu.

## Diagnostyka

```sh
for service in wreckscanner wreckscanner-backup cloudflared sshd mosquitto ilestoi-healthwatch; do
  sv status "$PREFIX/var/service/$service"
done

curl -fsS http://127.0.0.1:8001/api/health/live
curl -fsS http://127.0.0.1:8001/api/health/ready
cat "$HOME/.local/state/ilestoi-ops/health-last.json"
tail -n 30 "$HOME/.local/state/ilestoi-ops/health-watch.log"
tail -n 30 "$HOME/boot-services.log"
```

`live=200` oznacza działający proces HTTP, `ready=200` szybki odczyt SQLite,
zgodność migracji, dostępność wymaganych tabel i wolne miejsce. Pełną integralność
SQLite, klucze obce i istnienie plików zdjęć weryfikuje osobna diagnostyka
`python scripts/diagnose_data.py --strict` przed wydaniem i podczas backupu. Z zewnątrz `https://ilestoi.pl/` powinno dawać 200,
a `wreckscanner.pl` i `dlugostoi.pl` — 308 do `ilestoi.pl`.
Automatyczne zapytania z telefonu mogą otrzymać antybotowe 403 nawet,
gdy publiczna strona działa; **nie traktować samego 403 jako awarii**.

`healthwatch` sprawdza co 180 sekund lokalny readiness, publiczny URL
i dostęp do Internetu. Automatyczny restart **tylko `cloudflared`**
może nastąpić dopiero po trzech kolejnych odpowiedziach
502/503/504/520–524/530 z publicznego URL, przy lokalnym `ready=200`
i działającym wyjściu TCP 443; odstęp między restartami wynosi
minimum 30 minut. 403, timeout DNS lub utrata Wi-Fi nie wyzwalają
restartu. Znacznik `$PREFIX/var/service/cloudflared/down` jest traktowany
jako **jawne wyłączenie**: healthwatch rejestruje ten stan w health-last.json
i logu, ale nie usuwa znacznika i nie restartuje tunelu. Przywrócenie
po niezamierzonym wyłączeniu wymaga zweryfikowania przyczyny oraz
kontrolowanego `sv up` po usunięciu znacznika z zachowaniem dowodu.
Oddzielna kontrola publiczna z zewnątrz działa co godzinę,
z powiadomieniem tylko o potwierdzonym błędzie.

Restart pojedynczej usługi jedynie gdy jest konieczny:

```sh
sv restart "$PREFIX/var/service/cloudflared"
sv restart "$PREFIX/var/service/wreckscanner"
```

Nigdy nie uruchamiaj drugiej kopii `server.py`, `cloudflared`,
`mosquitto` ani `sshd` poleceniem `nohup`, gdy `runit` je nadzoruje.
Po ponownym podłączeniu Wi-Fi sam `cloudflared` powinien nawiązać
połączenie bez restartu całego telefonu.

## Cloudflare CDN i szybkie wdrożenia

Statyczne pliki CSS/JS są udostępniane pod adresami z wersją zawartości
(`/app/...js?v=<hash>`, `/styles.css?v=<hash>`). Importy wewnątrz
`styles.css` również otrzymują osobne hashe. Jedynie URL z **aktualnym,
prawidłowym** hashem otrzymuje
`Cache-Control: public, max-age=31536000, immutable`. URL bez hasha lub
ze starym hashem nadal ma `no-store`. Po każdym `git switch` na wydanie
HTML (zawsze `no-store`) automatycznie wskazuje nowe URL-e; nie potrzeba
purge Cloudflare ani restartu serwera tylko z powodu zmiany statycznych plików.

Nie wolno ustawiać w Cloudflare reguły „Ignore Query String” ani „No Query String”
dla CSS/JS: parametr `v` musi uczestniczyć w kluczu cache (Caching level:
**Standard**). W razie globalnych reguł bypass albo Development Mode
`CF-Cache-Status` może nadal pokazywać `BYPASS` mimo nagłówka `public`.
Reguły stron HTML, `/api/`, obszaru admina i zdjęć prywatnych pozostają
bez cache.

Kafle publicznej ortofotomapy mają lokalny cache dyskowy i poprawne kafle
odpowiadają z `public, max-age=86400`. Ponieważ `/tile_proxy/` i
`/wms_proxy/` nie mają rozszerzenia pliku, wymagają **osobnej,
precyzyjnej reguły Cloudflare Cache Rules** (nie jest to konfiguracja
`cloudflared` w Termuxie):

- Match: `http.host eq "ilestoi.pl" and
  (starts_with(http.request.uri.path, "/tile_proxy/geoportal-standard/")
  or starts_with(http.request.uri.path, "/wms_proxy/"))`.
- Cache eligibility: **Eligible for cache**. Origin Cache Control:
  **Respect origin headers**; nie wymuszaj Edge Cache TTL ani cache 200
  niezależnie od nagłówka.
- Cache key: **include all query strings** (`enhancementSettings` zmienia
  obraz). Nie dodawaj tej reguły dla HTML, API, statusu zdrowia, uploadów
  czy prywatnych zdjęć.
- Odpowiedzi zastępcze (BUSY/UPSTREAM_ERROR/IN_FLIGHT) mają `no-store`
  i **nie mogą** trafić do cache CDN.

Regułę na koncie Cloudflare należy dodać osobno przez dashboard/API z
uprawnieniami strefy (sam GitHub Connector i tunel nie zarządzają strefą).
Przed i po zmianie sprawdź `CF-Cache-Status` dla tego samego, bezpiecznego
adresu dwukrotnie oraz `Cache-Control`; nie testuj przeciążeniowo produkcji.

## Zweryfikowane i otwarte kontrole

26.10.2026: autoryzowany switch Cloudflare (nowa rejestracja tunelu,
publiczne HTTP 200), Mosquitto port 1883 i SSH ponownie uwierzytelnione
przez LAN oraz USB; oryginalne procesy zatrzymane. Healthwatch uruchomiony,
wszystkie usługi nadzorowane, backend live/ready 200. Wykonano
idempotentny **ręczny przebieg skryptu** Termux:Boot bez restartowania
usług i bez zmiany PID. Nie oznacza to jeszcze PASS rzeczywistego
rebootu z zablokowanym ekranem / Android Doze.

Android może zakończyć Termuxa (poprzednio odnotowano
`TOO MANY EMPTY PROCS` i `LOW_MEMORY`), nawet z wyjątkiem
optymalizacji baterii. Weryfikacja po pełnym fizycznym restarcie
i test kilkugodzinny z wygaszonym ekranem pozostają odrębne.

## Autostart po restarcie i stan uśpienia — 2026-11-08

Wersjonowany skrypt `deploy/termux/00-services.sh` korzysta z blokady
`~/.local/state/ilestoi-ops/boot.lock` i nie tworzy drugich procesów
aplikacji. Uruchamia jedynie nadzór `service-daemon` (gdy niedostępny)
oraz wysyła `sv up` do istniejących usług bez znacznika `down`.
Próba `termux-wake-lock` ma limit 8 sekund i nie blokuje startu,
gdy Android odrzuci/nie obsłuży żądania. Następnie skrypt czeka maksymalnie
90 sekund na lokalny backend i tunel, akceptując publiczne 200 albo
antybotowe 403. Wynik zapisuje w
`~/.local/state/ilestoi-ops/boot-last` razem z `boot_id`.
Zapis jest dowodem uruchomienia *skryptu*, a nie potwierdzeniem, że
Termux:Boot został wywołany podczas każdego rebootu.

`ilestoi-healthwatch` działa pod tym samym standardowym `runit`.
Co 90 sekund aktualizuje `health-last.json`, zapisuje identyfikator
bieżącego uruchomienia Androida, rzeczywiste odstępy między pomiarami
(`monitor_gap_seconds`) i stan nadzoru tunelu. Potwierdzony błąd
502–504/520–524/530 powoduje maksymalnie jedną próbę restartu po
trzech pomiarach; niedziałający nadzorowany proces (bez `down`)
powoduje `sv up` po dwóch pomiarach. Licznik limitu 30 minut pozostaje
w pliku stanu po restarcie samego monitora. 403, utrata Internetu i
niedostępny lokalny backend nie wyzwalają restartu. Automat nigdy nie
usuwa `down`, nie uruchamia `cloudflared` ręcznie i nie próbuje
naprawiać niedziałającego całego menedżera `runit` z poziomu jego
własnej usługi.

**Wymagana konfiguracja Androida:** Termux:Boot musi być zainstalowany
z tym samym podpisem co Termux i przynajmniej raz otwarty z ikony
programu (warunek aktywacji odbiornika boot). W ustawieniach baterii
Samsunga ustaw dla **Termux i Termux:Boot** działanie bez ograniczeń;
usuń je z listy aplikacji w głębokim uśpieniu. Jeśli Android oferuje
opcję ograniczania procesów potomnych, sprawdź ją osobno w Opcjach
programisty. Sam wake lock nie chroni przed wymuszonym zatrzymaniem
aplikacji, limitem procesów potomnych ani ubiciem procesu przez system
pod presją pamięci. W takich stanach nie istnieje niezawodny
samorestart realizowany wyłącznie przez aplikację Termux.
Dokumentacja Termux:Boot: https://github.com/termux/termux-boot

Odbiór po fizycznym restarcie telefonu:
1. Nie uruchamiaj strony drugim `nohup`; zachowaj standardowe `runit`.
2. Po starcie Androida sprawdź `boot-last`, `boot_id`, `sv status`
   dla `wreckscanner`, `cloudflared` i `ilestoi-healthwatch`,
   następnie lokalne i publiczne health.
3. Wygasz ekran na co najmniej 2 godziny; po odblokowaniu sprawdź
   świeżość `health-last.json`, `monitor_gap_seconds`, identyfikatory
   boot i komunikaty `LOW_MEMORY` / `TOO MANY EMPTY PROCS` w logach.
4. Jeśli Android zakończy Termux, sam monitor nie może zgłosić awarii.
   Wtedy potrzebny jest niezależny monitor z innego urządzenia
   albo przeniesienie tunelu/serwera na host z gwarantowanym autostartem.

Dostępny jest read-only odbiór z kodem wyjścia i JSON:
```sh
python3 -B deploy/termux/ilestoi-reliability-check.py --require-boot-record
python3 -B deploy/termux/ilestoi-reliability-check.py \
  --require-boot-record --min-coverage-seconds 7200 --max-gap-seconds 300
```
Narzędzie raportuje niezgodny `boot_id`, nieświeży heartbeat,
przerwę w monitorowaniu i zatrzymane procesy; publiczne 403 oznacza
`public_edge_antibot_ambiguous=true` i wymaga dodatkowego
zewnętrznego testu. Sam licznik 7200 sekund nie dowodzi, że ekran był
wygaszony przez ten czas — sprawdź to podczas kontrolowanego testu
na telefonie.

Nie traktuj manualnego wykonania `00-services` ani testu
symulowanego `runit` jako dowodu fizycznego rebootu lub dwugodzinnego
testu z wygaszonym ekranem. Te dwie bramki muszą mieć osobną datę i
rzeczywiste odczyty po wykonaniu.

## Incydent tunelu 2026-11-08

Na S22 backend odpowiadał `ready=200`, a publiczny adres `530`.
O godzinie 11:41:54 UTC proces `cloudflared` został zatrzymany przez
`SIGTERM`, przy zachowanym starszym znaczniku `cloudflared/down`.
Po zachowaniu i usunięciu znacznika ujawniła się druga przyczyna:
aktywny wariant `--token-file` wskazywał na **nieistniejący plik**
(ponowne wyjścia procesu i komunikat użycia). Stary skrypt zachowano
prywatnie w `~/.local/state/ilestoi-ops/`, bez publikowania sekretów.

Przywrócono usługę przez istniejące `~/.cloudflared/config.yml`
i zgodne lokalne poświadczenia JSON. Ingress przeszedł walidację;
runit potwierdził stabilny PID, backend i publiczny URL zwróciły HTTP 200
o 15:54 UTC. Skrypt wersjonowany w
`deploy/termux/cloudflared.run` używa odtąd tej samej jawnej konfiguracji,
bez zależności od nieistniejącego pliku tokenu.

Przed każdą zmianą definicji usługi sprawdzaj obecność wymaganych plików,
`ingress validate`, znacznik `down` i zachowaj starą definicję.
Nie przywracaj starego skryptu tokenowego automatycznie po restarcie
telefonu. Odbiór rzeczywistego rebootu i długiego okresu z wygaszonym
ekranem nadal pozostaje odrębnym testem.

## Cofnięcie zmian

Prywatny punkt przywracania operacji:
`~/.local/state/ilestoi-ops/cutover-20261026-v1/`.
`backup/` zawiera oryginalne pliki `00-services`, trzy wcześniejsze
znaczniki `down`, stary `cloudflared/run` oraz `mosquitto/run`,
w tym potencjalnie poufne wartości konfiguracyjne.
Nie dodawać tych kopii ani zrzutów tokenów do Git.

Rollback usług wykonuje operator przez niezależne SSH/USB:
najpierw zapewnia alternatywny kanał do telefonu, zatrzymuje
właściwy nadzorowany proces, przywraca skrypt i właściwy znacznik
`down`, następnie uruchamia poprzedni nadzorowany/manualny wariant
i weryfikuje HTTP 200. **Nie przywracać tylko starego boot skryptu**,
zostawiając nowe usługi `runit` włączone — dałoby to duplikaty przy
starcie. Nie ruszać prywatnego `90-local-agent`, bazy SQLite,
katalogów zdjęć ani snapshotów Restic.

## Backup danych

`wreckscanner-backup` zapisuje dane przez Restic w
`.backups/wreckscanner-restic` z niezależnym
`.restic_password` (uprawnienia 0600), co 24 godziny z ponowieniem
co godzinę przy niepowodzeniu; retencja 7 dziennych, 8 tygodniowych
i 6 miesięcznych punktów odtworzenia, chroniona blokadą
`~/.local/state/ilestoi-restic.lock`. Lokalny Restic i weryfikowana
kopia SQLite w osobnym folderze telefonu są wymaganymi zabezpieczeniami
tego wydania. Właściciel 29.10.2026 zrezygnował z wymogu kopii off-host
jako bramki wdrożenia. Utrata telefonu może oznaczać utratę obu kopii.

```sh
sv status "$PREFIX/var/service/wreckscanner-backup"
tail -n 30 "$HOME/wreckscanner-backup.log"
```

## Osobna kopia SQLite na Samsungu

Zachowana, zweryfikowana kopia sprzed produkcyjnego wydania PR #9:

`~/IleStoi-Backups/pre-release-20261029-104843/wreckscanner.sqlite3`

Bezpośrednio przed wdrożeniem wykonano też drugi niezależny snapshot:
`~/IleStoi-Backups/pre-deploy-pr9-20261029/wreckscanner.sqlite3`.
Oba pozostają na telefonie, poza katalogiem aplikacji i Restic. Manifesty
oraz sumy SHA-256 są obok plików. Szczegóły w [docs/BACKUP.md](BACKUP.md).
Kopia pozostaje na telefonie w oddzielnym folderze; nie przenosić jej
ani nie usuwać w ramach wdrożenia. Nie zawiera katalogów zdjęć i nie jest
zaszyfrowana. Zdjęcia obejmuje istniejące lokalne repozytorium Restic.
Kopia off-host nie jest wymagana do wydania na wyraźne życzenie właściciela.
