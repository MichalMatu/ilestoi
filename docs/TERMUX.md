# IleStoi.pl na Termuxie (Samsung Android)

Stan operacyjny: 26.10.2026, po migracji startu na `runit`.
Katalog produkcyjny: `~/WreckScanner/WreckScanner`; kod utrzymaniowy:
`work/dirty`. Python Termuxa 3.14, poza macierzą CI 3.11/3.13.

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
`~/.local/state/ilestoi-restic.lock`. Trzeba nadal utrzymywać
zaszyfrowaną kopię off-host i próbny restore, gdyż backup na tym
samym telefonie nie chroni przed jego utratą.

```sh
sv status "$PREFIX/var/service/wreckscanner-backup"
tail -n 30 "$HOME/wreckscanner-backup.log"
```
