.DEFAULT_GOAL := menu
MAKEFLAGS += --no-print-directory
SUBMAKE := $(MAKE)

.PHONY: menu help start stop restart status logs check test lint smoke e2e-report health wait-server require-local-watcher autostart-start autostart-stop autostart-status serwerstart serwerstop backup-data restore-data list-backups backup-restic prune-restic check-restic list-restic

PYTHON ?= $(shell if [ -x ./.venv/bin/python ]; then printf './.venv/bin/python'; elif command -v python3 >/dev/null 2>&1; then command -v python3; else command -v python; fi)
HOST ?= 127.0.0.1
PORT ?= 8001
SERVER_URL := http://$(HOST):$(PORT)
SERVER_LIVE_URL := $(SERVER_URL)/api/health/live
SERVER_READY_URL := $(SERVER_URL)/api/health/ready
BACKUP_DIR ?= kopie_zapasowe
RESTIC_REPO ?= .backups/wreckscanner-restic
RESTIC_PASSWORD_FILE ?= .restic_password
SYSTEMD_UNIT ?= wreckscanner.service
SYSTEMCTL ?= systemctl
JOURNALCTL ?= journalctl
SERVER_PATTERN := [p]ython[^[:space:]]*[[:space:]].*$(CURDIR)/server\.py([[:space:]]|$$)
SERVER_WAIT_SECONDS ?= 15
SERVER_STOP_WAIT_SECONDS ?= 10
SERVER_AUTOSTART_WAIT_SECONDS ?= 15
SERVER_PROBE_TIMEOUT_SECONDS ?= 5
SERVER_LOG ?= .dev/server.log
AUTOSTART_DISABLED_FILE ?= .dev/server.autostart.disabled
SYSTEMD_WORKING_DIRECTORY := $(shell $(SYSTEMCTL) show "$(SYSTEMD_UNIT)" --property=WorkingDirectory --value 2>/dev/null)
SYSTEMD_MOUNT_PATHS := $(shell $(SYSTEMCTL) show "$(SYSTEMD_UNIT)" --property=BindPaths --property=BindReadOnlyPaths --value 2>/dev/null)
SYSTEMD_CHECKOUT_MOUNTS := $(filter $(CURDIR):% $(CURDIR)/server.py:%,$(SYSTEMD_MOUNT_PATHS))
SYSTEMD_MANAGED ?= $(if $(or $(filter $(CURDIR),$(SYSTEMD_WORKING_DIRECTORY)),$(SYSTEMD_CHECKOUT_MOUNTS)),1,0)
RUNIT_SERVICE ?= $(PREFIX)/var/service/wreckscanner
RUNIT_MANAGED ?= $(if $(and $(PREFIX),$(filter $(HOME)/WreckScanner/WreckScanner,$(CURDIR)),$(wildcard $(RUNIT_SERVICE)/run)),1,0)

menu:
	@printf '%s\n' \
		'WreckScanner - menu:' \
		'  Supervisor: $(if $(filter 1,$(RUNIT_MANAGED)),runit (wreckscanner),$(if $(filter 1,$(SYSTEMD_MANAGED)),systemd ($(SYSTEMD_UNIT)),lokalny watcher))' \
		'' \
		'  1. Status serwera' \
		'  2. Restart serwera (watcher)' \
		'  3. Wylacz autostart i zatrzymaj (watcher)' \
		'  4. Wlacz autostart serwera (watcher)' \
		'  5. Pelny check aplikacji' \
		'  6. Stworz snapshot danych ZIP (watcher)' \
		'  7. Odtworz dane z kopii ZIP (watcher)' \
		'  8. Pokaz lokalne kopie ZIP' \
		'  9. Pokaz logi' \
		'  0. Wyjscie' \
		''
	@printf 'Wybor: '; \
	read choice; \
	case "$$choice" in \
		1) $(SUBMAKE) status ;; \
		2) $(SUBMAKE) restart ;; \
		3) $(SUBMAKE) serwerstop ;; \
		4) $(SUBMAKE) serwerstart ;; \
		5) $(SUBMAKE) check ;; \
		6) $(SUBMAKE) backup-data ;; \
		7) printf 'Sciezka do ZIP: '; read backup; \
			if [ -z "$$backup" ]; then echo 'Brak sciezki do ZIP.'; exit 2; fi; \
			$(SUBMAKE) restore-data BACKUP="$$backup" ;; \
		8) $(SUBMAKE) list-backups ;; \
		9) $(SUBMAKE) logs ;; \
		0) exit 0 ;; \
		*) echo 'Nieznany wybor.'; exit 2 ;; \
	esac

help:
	@printf '%s\n' \
		'WreckScanner - komendy:' \
		'Supervisor: $(if $(filter 1,$(RUNIT_MANAGED)),runit (wreckscanner),$(if $(filter 1,$(SYSTEMD_MANAGED)),systemd ($(SYSTEMD_UNIT)),lokalny watcher))' \
		'' \
		'Serwer:'
	@printf '  %-24s %s\n' \
		'make start' 'pokaz PID + health; nie uruchamia procesu' \
		'make stop' 'zatrzymaj biezacy proces (tylko lokalny watcher)' \
		'make restart' 'restart i readiness (tylko lokalny watcher)' \
		'make serwerstop' 'wylacz watcher + zatrzymaj proces' \
		'make serwerstart' 'wlacz watcher i czekaj na readiness' \
		'make autostart-status' 'supervisor + autostart + PID + health'
	@if [ "$(RUNIT_MANAGED)" = '1' ]; then \
		printf '%s\n' '  Na Termuxie: sv restart $(RUNIT_SERVICE)'; \
	fi
	@if [ "$(SYSTEMD_MANAGED)" = '1' ]; then \
		printf '%s\n' 
			'' \
			'  Ten katalog obsluguje systemd. Zmiany stanu wykonuj przez:' \
			'  sudo systemctl stop|start|restart $(SYSTEMD_UNIT)' \
			'  sudo systemctl disable --now $(SYSTEMD_UNIT)' \
			'  sudo systemctl enable --now $(SYSTEMD_UNIT)'; \
	fi
	@printf '%s\n' '' 'Diagnostyka:'
	@printf '  %-24s %s\n' \
		'make status' 'PID + health' \
		'make logs' 'ostatnie logi' \
		'make check' 'pelny check' \
		'make test' 'testy Python' \
		'make lint' 'lint + kontrola formatowania' \
		'make smoke' 'runtime smoke dzialajacego serwera' \
		'make e2e-report' 'E2E z tymczasowym rekordem, PDF i screenshotami' \
		'make health' 'alias status'
	@printf '%s\n' '' 'Backup:'
	@printf '  %-36s %s\n' \
		'make backup-restic' 'szyfrowany snapshot przyrostowy po dodaniu zdjec' \
		'make list-restic' 'pokaz snapshoty Restic' \
		'make check-restic' 'sprawdz strukture repozytorium Restic' \
		'make prune-restic' 'zachowaj 8 tygodniowych i 6 miesiecznych kopii' \
		'make backup-data' 'snapshot ZIP danych bez sekretow (tylko watcher)' \
		'make restore-data BACKUP=plik.zip' 'odtworz dane z ZIP (tylko watcher)' \
		'make list-backups' 'pokaz lokalne kopie ZIP'

start:
	@$(SUBMAKE) status

require-local-watcher:
	@if [ "$(RUNIT_MANAGED)" = '1' ]; then \
		echo 'Ten katalog jest nadzorowany przez runit. Uzyj sv stop|start|restart $(RUNIT_SERVICE).'; \
		exit 2; \
	fi
	@if [ "$(SYSTEMD_MANAGED)" = '1' ]; then \
		echo 'Ta komenda jest przeznaczona tylko dla lokalnego watchera.'; \
		echo 'Ten katalog obsluguje systemd: $(SYSTEMD_UNIT).'; \
		echo 'Sterowanie procesem: sudo systemctl stop|start|restart $(SYSTEMD_UNIT)'; \
		echo 'Backup/restore z zatrzymaniem uslugi: docs/BACKUP.md'; \
		exit 2; \
	fi

stop: require-local-watcher
	@pids="$$(pgrep -f '$(SERVER_PATTERN)' || true)"; \
	if [ -z "$$pids" ]; then \
		echo 'server.py nie dziala.'; \
	else \
		echo "Zatrzymuje server.py: $$pids"; \
		kill $$pids || exit $$?; \
		i=0; \
		while [ "$$i" -lt "$(SERVER_STOP_WAIT_SECONDS)" ]; do \
			alive=0; \
			for pid in $$pids; do \
				if kill -0 "$$pid" 2>/dev/null; then alive=1; fi; \
			done; \
			if [ "$$alive" -eq 0 ]; then \
				echo 'Zatrzymany poprzedni proces server.py.'; \
				exit 0; \
			fi; \
			i=$$((i + 1)); \
			sleep 1; \
		done; \
		echo 'Poprzedni proces server.py nie zatrzymal sie w ciagu $(SERVER_STOP_WAIT_SECONDS)s.'; \
		exit 1; \
	fi
restart: require-local-watcher
	@if [ -f "$(AUTOSTART_DISABLED_FILE)" ]; then \
		echo 'Nie mozna wykonac restartu: lokalny watcher jest wylaczony.'; \
		echo 'Uzyj make serwerstart.'; \
		exit 1; \
	fi
	@$(SUBMAKE) stop
	@$(SUBMAKE) wait-server

wait-server:
	@if ! command -v curl >/dev/null 2>&1; then \
		echo 'curl jest wymagany do sprawdzenia readiness server.py.'; \
		exit 1; \
	fi; \
	i=0; \
	while [ "$$i" -lt "$(SERVER_WAIT_SECONDS)" ]; do \
		if pgrep -af '$(SERVER_PATTERN)' >/dev/null; then \
			if curl -fsS --max-time "$(SERVER_PROBE_TIMEOUT_SECONDS)" "$(SERVER_READY_URL)" >/dev/null 2>&1; then \
				echo 'server.py dziala:'; \
				pgrep -af '$(SERVER_PATTERN)'; \
				echo 'Readiness OK'; \
				exit 0; \
			fi; \
		fi; \
		i=$$((i + 1)); \
		sleep 1; \
	done; \
	echo 'Autostart nie podniosl zdrowego server.py w ciagu $(SERVER_WAIT_SECONDS)s.'; \
	echo 'Sprawdz konfiguracje i logi watchera.'; \
	exit 1

autostart-stop: require-local-watcher
	@mkdir -p "$(dir $(AUTOSTART_DISABLED_FILE))"
	@printf 'disabled\n' > "$(AUTOSTART_DISABLED_FILE)"
	@echo 'Autostart server.py wylaczony.'
	@$(SUBMAKE) stop

autostart-start: require-local-watcher
	@rm -f "$(AUTOSTART_DISABLED_FILE)"
	@echo 'Autostart server.py wlaczony. Czekam na readiness procesu podniesionego przez watcher.'
	@if $(SUBMAKE) SERVER_WAIT_SECONDS=$(SERVER_AUTOSTART_WAIT_SECONDS) wait-server; then \
		exit 0; \
	fi; \
	echo 'Watcher nie podniosl server.py. Reczna instancja nie zostala uruchomiona.'; \
	echo 'Sprawdz konfiguracje watchera i ponow make serwerstart.'; \
	exit 1

autostart-status:
	@if [ "$(RUNIT_MANAGED)" = '1' ]; then \
		echo 'Supervisor server.py: runit'; \
		sv status '$(RUNIT_SERVICE)' || exit 1; \
	elif [ "$(SYSTEMD_MANAGED)" = '1' ]; then \
		enabled="$$( $(SYSTEMCTL) is-enabled "$(SYSTEMD_UNIT)" 2>/dev/null || true )"; \
		active="$$( $(SYSTEMCTL) is-active "$(SYSTEMD_UNIT)" 2>/dev/null || true )"; \
		echo 'Supervisor server.py: systemd ($(SYSTEMD_UNIT))'; \
		echo "Autostart systemd: $${enabled:-nieznany}"; \
		echo "Stan uslugi: $${active:-nieznany}"; \
	elif [ -f "$(AUTOSTART_DISABLED_FILE)" ]; then \
		echo 'Supervisor server.py: lokalny watcher'; \
		echo 'Autostart server.py: wylaczony'; \
		echo 'Blokada:' "$(AUTOSTART_DISABLED_FILE)"; \
	else \
		echo 'Supervisor server.py: lokalny watcher'; \
		echo 'Autostart server.py: wlaczony'; \
	fi
	@$(SUBMAKE) status

serwerstop: autostart-stop

serwerstart: autostart-start

status:
	@status=0; \
	if [ "$(RUNIT_MANAGED)" = '1' ]; then \
		echo 'Supervisor: runit ($(RUNIT_SERVICE))'; \
		if ! sv status '$(RUNIT_SERVICE)'; then status=1; fi; \
	elif [ "$(SYSTEMD_MANAGED)" = '1' ]; then \
		active="$$( $(SYSTEMCTL) is-active "$(SYSTEMD_UNIT)" 2>/dev/null || true )"; \
		main_pid="$$( $(SYSTEMCTL) show "$(SYSTEMD_UNIT)" --property=MainPID --value 2>/dev/null || true )"; \
		echo "Supervisor: systemd ($(SYSTEMD_UNIT)), stan: $${active:-nieznany}"; \
		if [ "$$active" != 'active' ]; then status=1; fi; \
		printf '%s\n' 'Procesy server.py:'; \
		if [ -n "$$main_pid" ] && [ "$$main_pid" != '0' ]; then \
			echo "$$main_pid ($(SYSTEMD_UNIT))"; \
		else \
			echo 'brak'; \
			status=1; \
		fi; \
	else \
		echo 'Supervisor: lokalny watcher'; \
		printf '%s\n' 'Procesy server.py:'; \
		if ! pgrep -af '$(SERVER_PATTERN)'; then \
			echo 'brak'; \
			status=1; \
		fi; \
	fi; \
	printf '\n%s\n' 'Liveness:'; \
	if command -v curl >/dev/null 2>&1; then \
		if ! curl -fsS --max-time "$(SERVER_PROBE_TIMEOUT_SECONDS)" "$(SERVER_LIVE_URL)"; then status=1; fi; \
	else \
		echo 'curl niedostepny'; \
		status=1; \
	fi; \
	printf '\n%s\n' 'Readiness:'; \
	if command -v curl >/dev/null 2>&1; then \
		if ! curl -fsS --max-time "$(SERVER_PROBE_TIMEOUT_SECONDS)" "$(SERVER_READY_URL)"; then status=1; fi; \
	else \
		echo 'curl niedostepny'; \
		status=1; \
	fi; \
	printf '\n'; \
	exit "$$status"

logs:
	@if [ "$(RUNIT_MANAGED)" = '1' ]; then \
		tail -n 80 '$(HOME)/wreckscanner.log'; \
	elif [ "$(SYSTEMD_MANAGED)" = '1' ]; then \
		if ! command -v "$(JOURNALCTL)" >/dev/null 2>&1; then \
			echo 'journalctl jest wymagany do logow uslugi $(SYSTEMD_UNIT).'; \
			exit 1; \
		fi; \
		"$(JOURNALCTL)" --unit "$(SYSTEMD_UNIT)" --lines 80 --no-pager; \
	elif [ -f "$(SERVER_LOG)" ]; then \
		tail -n 80 "$(SERVER_LOG)"; \
	else \
		echo 'Brak logu lokalnego watchera: $(SERVER_LOG).'; \
	fi

check:
	@./scripts/check.sh

test:
	@"$(PYTHON)" -m unittest discover -s tests

lint:
	@"$(PYTHON)" -m ruff check app core scripts tests server.py
	@"$(PYTHON)" -m ruff format --check app core scripts tests server.py
	@if ! command -v npm >/dev/null 2>&1; then \
		echo 'error: npm jest wymagany do lintowania calego frontendu'; \
		exit 1; \
	fi
	@npm run lint:web

smoke:
	@"$(PYTHON)" scripts/smoke_runtime.py --base-url "$(SERVER_URL)"

e2e-report:
	@"$(PYTHON)" scripts/e2e_field_photo_report.py --base-url "$(SERVER_URL)"

health: status

backup-data: require-local-watcher
	@was_disabled=0; \
	if [ -f "$(AUTOSTART_DISABLED_FILE)" ]; then was_disabled=1; fi; \
	finish() { \
		status=$$?; \
		restart_status=0; \
		trap - EXIT HUP INT TERM; \
		if [ "$$was_disabled" -eq 0 ]; then \
			$(SUBMAKE) autostart-start || restart_status=$$?; \
			if [ "$$status" -eq 0 ] && [ "$$restart_status" -ne 0 ]; then status=$$restart_status; fi; \
		else \
			echo 'Autostart byl wylaczony przed backupem; zostawiam wylaczony.'; \
		fi; \
		exit "$$status"; \
	}; \
	trap finish EXIT; \
	trap 'exit 130' HUP INT TERM; \
	$(SUBMAKE) autostart-stop || exit $$?; \
	"$(PYTHON)" scripts/backup_data.py zip --root-dir "$(CURDIR)" --output-dir "$(BACKUP_DIR)" --strict

restore-data: require-local-watcher
	@if [ -z "$(BACKUP)" ]; then \
		echo 'Podaj plik kopii: make restore-data BACKUP=kopie_zapasowe/plik.zip'; \
		exit 2; \
	fi
	@was_disabled=0; \
	if [ -f "$(AUTOSTART_DISABLED_FILE)" ]; then was_disabled=1; fi; \
	finish() { \
		status=$$?; \
		restart_status=0; \
		trap - EXIT HUP INT TERM; \
		if [ "$$was_disabled" -eq 0 ]; then \
			$(SUBMAKE) autostart-start || restart_status=$$?; \
			if [ "$$status" -eq 0 ] && [ "$$restart_status" -ne 0 ]; then status=$$restart_status; fi; \
		else \
			echo 'Autostart byl wylaczony przed odtwarzaniem; zostawiam wylaczony.'; \
		fi; \
		exit "$$status"; \
	}; \
	trap finish EXIT; \
	trap 'exit 130' HUP INT TERM; \
	$(SUBMAKE) autostart-stop || exit $$?; \
	"$(PYTHON)" scripts/backup_data.py restore-zip --root-dir "$(CURDIR)" --archive "$(BACKUP)"

list-backups:
	@"$(PYTHON)" scripts/backup_data.py list-zips --root-dir "$(CURDIR)" --output-dir "$(BACKUP_DIR)"

backup-restic:
	@"$(PYTHON)" scripts/backup_data.py run --root-dir "$(CURDIR)" --repo "$(RESTIC_REPO)" --password-file "$(RESTIC_PASSWORD_FILE)" --strict

prune-restic:
	@"$(PYTHON)" scripts/backup_data.py forget --root-dir "$(CURDIR)" --repo "$(RESTIC_REPO)" --password-file "$(RESTIC_PASSWORD_FILE)" --keep-daily 0 --keep-weekly 8 --keep-monthly 6 --prune

check-restic:
	@"$(PYTHON)" scripts/backup_data.py check --root-dir "$(CURDIR)" --repo "$(RESTIC_REPO)" --password-file "$(RESTIC_PASSWORD_FILE)"

list-restic:
	@"$(PYTHON)" scripts/backup_data.py snapshots --root-dir "$(CURDIR)" --repo "$(RESTIC_REPO)" --password-file "$(RESTIC_PASSWORD_FILE)"
