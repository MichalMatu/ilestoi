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

`live=200` oznacza działający proces HTTP, `ready=200` gotowość SQLite,
plików i dysku. Z zewnątrz `https://ilestoi.pl/` powinno dawać 200,
a `wreckscanner.pl` i `dlugostoi.pl` — 308 do `ilestoi.pl`.
Automatyczne zapytania z telefonu mogą otrzymać antybotowe 403 nawet,
gdy publiczna strona działa; **nie traktować samego 403 jako awarii**.

`healthwatch` sprawdza co 180 sekund lokalny readiness, publiczny URL
i dostęp do Internetu. Automatyczny restart **tylko `cloudflared`**
może nastąpić dopiero po trzech kolejnych odpowiedziach
502/503/504/520–524 z publicznego URL, przy lokalnym `ready=200`
i działającym wyjściu TCP 443; odstęp między restartami wynosi
minimum 30 minut. 403, timeout DNS lub utrata Wi-Fi nie wyzwalają
restartu. Oddzielna kontrola publiczna z zewnątrz działa co godzinę,
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
