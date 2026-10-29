from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT_DIR = Path(__file__).resolve().parents[1]
CHROMIUM = next(
    (binary for name in ("google-chrome", "chromium", "chromium-browser") if (binary := shutil.which(name))),
    None,
)
CHROMIUM_TIMEOUT_SECONDS = 20
CHROMIUM_DUMP_TIMEOUT_MS = 10_000


def run_chromium_document(document: str, *, prefix: str, virtual_time_budget: int) -> dict:
    with TemporaryDirectory(prefix=prefix) as tmp:
        html_path = Path(tmp) / "runtime.html"
        profile_path = Path(tmp) / "chromium-profile"
        html_path.write_text(document, encoding="utf-8")
        completed = subprocess.run(
            [
                CHROMIUM,
                "--headless=new",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                f"--user-data-dir={profile_path}",
                f"--timeout={CHROMIUM_DUMP_TIMEOUT_MS}",
                f"--virtual-time-budget={virtual_time_budget}",
                "--dump-dom",
                html_path.as_uri(),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=CHROMIUM_TIMEOUT_SECONDS,
        )

    if completed.returncode:
        raise AssertionError(completed.stderr)
    error = re.search(r"<title>ERROR:([^<]+)</title>", completed.stdout)
    if error:
        raise AssertionError(base64.b64decode(error.group(1)).decode("utf-8"))
    match = re.search(r"<title>RESULT:([^<]+)</title>", completed.stdout)
    if not match:
        titles = re.findall(r"<title>[^<]*</title>", completed.stdout)
        raise AssertionError(f"titles={titles} stderr={completed.stderr}")
    return json.loads(base64.b64decode(match.group(1)).decode("utf-8"))


def assert_ui_focus_result(test: unittest.TestCase, result: dict) -> None:
    test.assertEqual(result["modal"]["active"], "modal-first")
    test.assertEqual(result["modal"]["role"], "dialog")
    test.assertEqual(result["modal"]["ariaModal"], "true")
    test.assertTrue(result["modal"]["labelled"])
    test.assertTrue(result["modal"]["mapInert"])
    test.assertEqual(result["modalWrap"], "modal-first")
    test.assertEqual(result["nested"], {"top": "modal-confirm", "active": "confirm-submit", "parentInert": True})
    test.assertEqual(
        result["nestedRestore"],
        {"top": "modal-a", "active": "modal-first", "parentInert": False},
    )
    test.assertEqual(result["modalRestore"], "opener")
    test.assertEqual(result["drawer"], {"active": "drawer-first", "mapInert": True})
    test.assertEqual(result["drawerWrap"], "app-menu-toggle")
    test.assertEqual(result["drawerRestore"], {"active": "app-menu-toggle", "mapInert": False})
    test.assertEqual(
        result["tabs"],
        {"active": "parking-costs-tab-risk", "selected": "parking-costs-tab-risk", "tabIndexes": [-1, 0]},
    )


@unittest.skipUnless(CHROMIUM, "Chromium is required for the executable focus-management test")
class UiAccessibilityRuntimeTests(unittest.TestCase):
    def test_photo_review_canvas_supports_keyboard_editing_in_a_real_dom(self):
        canvas_js = (ROOT_DIR / "web" / "app" / "photo_review_canvas.js").read_text(encoding="utf-8")
        canvas_js = canvas_js.replace("</script", "<\\/script")
        document = (
            """<!doctype html><html><head><title>pending</title></head><body>
            <canvas id="photo-review-canvas" width="400" height="300"></canvas>
            <script>
                let photoReviewImage = {};
                let photoReviewRedactions = [];
                let activePhotoReviewRedactionIndex = -1;
                let photoReviewDraftRect = null;
                let photoReviewDrawing = false;
                function t(key) { return key; }
                HTMLCanvasElement.prototype.getContext = () => ({
                    clearRect() {}, drawImage() {}, beginPath() {}, moveTo() {}, lineTo() {},
                    closePath() {}, fill() {}, stroke() {}, arc() {}, fillRect() {}, strokeRect() {},
                });
                HTMLCanvasElement.prototype.getBoundingClientRect = () => ({
                    left: 0, top: 0, width: 400, height: 300,
                });
            </script><script>"""
            + canvas_js
            + """</script><script>
                const canvas = document.getElementById('photo-review-canvas');
                const key = (value, options = {}) => canvas.dispatchEvent(new KeyboardEvent(
                    'keydown', { key: value, bubbles: true, cancelable: true, ...options }
                ));
                canvas.focus();
                key('Enter');
                const created = {
                    count: photoReviewRedactions.length,
                    active: activePhotoReviewRedactionIndex,
                    x: photoReviewRedactions[0].points[0].x,
                };
                key('ArrowRight');
                const movedX = photoReviewRedactions[0].points[0].x;
                const widthBefore = photoReviewRedactions[0].points[1].x - photoReviewRedactions[0].points[0].x;
                key('ArrowRight', { ctrlKey: true });
                const widthAfter = photoReviewRedactions[0].points[1].x - photoReviewRedactions[0].points[0].x;
                key('Enter');
                key('PageUp');
                const selectedAfterPageUp = activePhotoReviewRedactionIndex;
                key('Delete');
                const result = {
                    role: canvas.getAttribute('role'),
                    describedBy: canvas.getAttribute('aria-describedby'),
                    activeElement: document.activeElement.id,
                    created,
                    movedX,
                    grew: widthAfter > widthBefore,
                    selectedAfterPageUp,
                    remaining: photoReviewRedactions.length,
                    statusRole: document.getElementById('photo-review-canvas-status').getAttribute('role'),
                };
                document.title = 'RESULT:' + btoa(JSON.stringify(result));
            </script></body></html>"""
        )

        result = run_chromium_document(
            document,
            prefix="wreckscanner-canvas-keyboard-",
            virtual_time_budget=500,
        )

        self.assertEqual(result["role"], "application")
        self.assertEqual(result["describedBy"], "photo-review-canvas-help")
        self.assertEqual(result["activeElement"], "photo-review-canvas")
        self.assertEqual(result["created"]["count"], 1)
        self.assertEqual(result["created"]["active"], 0)
        self.assertGreater(result["movedX"], result["created"]["x"])
        self.assertTrue(result["grew"])
        self.assertEqual(result["selectedAfterPageUp"], 0)
        self.assertEqual(result["remaining"], 1)
        self.assertEqual(result["statusRole"], "status")

    def test_modal_drawer_and_tabs_manage_focus_in_a_real_dom(self):
        ui_js = (ROOT_DIR / "web" / "ui.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
        document = (
            """<!doctype html><html><head><title>pending</title></head><body>
            <button id="opener">Open</button>
            <div class="app-menu" id="app-menu"><button id="app-menu-toggle">Menu</button></div>
            <button id="app-menu-scrim" hidden tabindex="-1">Close</button>
            <aside id="app-menu-drawer" hidden>
                <button id="drawer-first">First</button><button id="drawer-last">Last</button>
            </aside>
            <div id="status"></div><div id="map" tabindex="0"></div>
            <div class="modal-backdrop" id="modal-a" hidden>
                <div class="modal"><div class="modal-header"><h2>Dialog A</h2></div>
                    <button id="modal-first">First</button><button id="modal-last">Last</button>
                </div>
            </div>
            <div class="modal-backdrop" id="modal-confirm" hidden>
                <form class="modal"><div class="modal-header"><h2 id="confirm-title">Confirm</h2></div>
                    <p id="confirm-message"></p><button id="confirm-cancel" type="button">Cancel</button>
                    <button id="confirm-submit" type="submit">Confirm</button>
                </form>
            </div>
            <div class="modal-backdrop" id="modal-admin-login" hidden>
                <div class="modal"><div class="modal-header"><h2>Login</h2></div></div>
            </div>
            <div class="modal-backdrop" id="modal-parking-costs" hidden>
                <div class="modal"><div class="modal-header"><h2>Parking</h2></div>
                    <div class="parking-costs-tabs" role="tablist">
                        <button id="parking-costs-tab-owner" role="tab" aria-selected="true"
                            data-parking-costs-tab="owner">Owner</button>
                        <button id="parking-costs-tab-risk" role="tab" aria-selected="false"
                            data-parking-costs-tab="risk">Risk</button>
                    </div>
                    <section data-parking-costs-panel="owner"></section>
                    <section data-parking-costs-panel="risk" hidden></section>
                </div>
            </div>
            <script>
                let CURRENT_LANG = 'en';
                function t(key) { return key; }
                function setLang() {}
                function closeAdminLoginModal() {}
                window.requestAnimationFrame = callback => window.setTimeout(() => callback(performance.now()), 0);
            </script><script>"""
            + ui_js
            + """</script><script>
            (async () => {
                const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                const result = {};
                const opener = document.getElementById('opener');

                opener.focus();
                openModal('modal-a', { initialFocus: '#modal-first' });
                await frame();
                const dialog = document.querySelector('#modal-a .modal');
                result.modal = {
                    active: document.activeElement.id,
                    role: dialog.getAttribute('role'),
                    ariaModal: dialog.getAttribute('aria-modal'),
                    labelled: Boolean(dialog.getAttribute('aria-labelledby')),
                    mapInert: document.getElementById('map').inert,
                };
                document.getElementById('modal-last').focus();
                document.getElementById('modal-last').dispatchEvent(
                    new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
                );
                result.modalWrap = document.activeElement.id;

                document.getElementById('modal-first').focus();
                const pendingConfirm = confirmAction({ message: 'Sure?' });
                await frame();
                result.nested = {
                    top: topOpenModalBackdrop().id,
                    active: document.activeElement.id,
                    parentInert: document.getElementById('modal-a').inert,
                };
                closeConfirmModal(false);
                await pendingConfirm;
                await frame();
                result.nestedRestore = {
                    top: topOpenModalBackdrop().id,
                    active: document.activeElement.id,
                    parentInert: document.getElementById('modal-a').inert,
                };
                closeModal();
                await frame();
                result.modalRestore = document.activeElement.id;

                document.getElementById('app-menu-toggle').focus();
                toggleAppMenu();
                await frame();
                result.drawer = {
                    active: document.activeElement.id,
                    mapInert: document.getElementById('map').inert,
                };
                document.getElementById('drawer-last').focus();
                document.getElementById('drawer-last').dispatchEvent(
                    new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
                );
                result.drawerWrap = document.activeElement.id;
                closeAppMenu();
                await frame();
                result.drawerRestore = {
                    active: document.activeElement.id,
                    mapInert: document.getElementById('map').inert,
                };

                openParkingCostsModal();
                await frame();
                const firstTab = document.getElementById('parking-costs-tab-owner');
                firstTab.dispatchEvent(
                    new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true })
                );
                result.tabs = {
                    active: document.activeElement.id,
                    selected: document.querySelector('[role="tab"][aria-selected="true"]').id,
                    tabIndexes: Array.from(document.querySelectorAll('[role="tab"]')).map(tab => tab.tabIndex),
                };
                document.title = 'RESULT:' + btoa(JSON.stringify(result));
            })().catch(error => { document.title = 'ERROR:' + btoa(String(error.stack || error)); });
            </script></body></html>"""
        )

        result = run_chromium_document(document, prefix="wreckscanner-ui-runtime-", virtual_time_budget=2500)
        assert_ui_focus_result(self, result)

    def test_field_photo_location_picker_supports_keyboard_in_a_real_dom(self):
        upload_js = (
            (ROOT_DIR / "web" / "app" / "field_photo_upload.js")
            .read_text(encoding="utf-8")
            .replace("</script", "<\\/script")
        )
        document = (
            """<!doctype html><html><head><title>pending</title></head><body>
            <button id="app-menu-toggle">Menu</button>
            <aside id="drawer"><button id="panel-add-field-photo"><span data-panel-add-photo-label></span></button></aside>
            <div id="status"></div>
            <div id="map" role="region" tabindex="0" aria-label="Map"><button id="map-control">Zoom</button></div>
            <div id="map-field-photo-pick-hint" hidden><span data-map-pick-hint-label></span></div>
            <div id="modal-field-photo-upload" hidden><form id="field-photo-form">
                <select id="field-photo-issue-type"><option value="vehicle">Vehicle</option></select>
                <select id="field-photo-insurance-status"><option value="unknown">Unknown</option></select>
                <input id="field-photo-files" type="file"><span data-file-summary-for="field-photo-files"></span>
                <div id="field-photo-queue"></div><button id="field-photo-retry"></button>
                <button id="field-photo-submit"><span></span></button><p id="field-photo-status"></p>
            </form></div>
            <script>
                const FIELD_PHOTO_ISSUE_TYPE_VEHICLE = 'vehicle';
                const FIELD_PHOTO_ISSUE_TYPES = new Set(['vehicle']);
                const FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN = 'unknown';
                const PUBLIC_FEATURE_KEYS = { photoUploads: 'photo_uploads' };
                let adminAuthenticated = false;
                let openedModal = '';
                const statusEl = document.getElementById('status');
                const mapContainer = document.getElementById('map');
                const map = {
                    getContainer: () => mapContainer,
                    getCenter: () => ({ lat: 51.125, lng: 17.025 }),
                    on() {}, off() {},
                };
                const L = { latLng: (lat, lng) => ({ lat: Number(lat), lng: Number(lng) }) };
                function t(key) { return key; }
                function publicFeatureAllowed() { return true; }
                function fieldPhotoAnyIssueAllowed() { return true; }
                function closeMapContextMenu() {}
                function closeAppMenu() { document.getElementById('drawer').hidden = true; }
                function updateFieldPhotoIssueOptions() {}
                function updateFilePickerSummary() {}
                function openModal(id) { openedModal = id; }
                window.requestAnimationFrame = callback => window.setTimeout(() => callback(performance.now()), 0);
            </script><script>"""
            + upload_js
            + """</script><script>
            (async () => {
                const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                const panelButton = document.getElementById('panel-add-field-photo');
                const drawer = document.getElementById('drawer');
                const key = (value, target = mapContainer) => target.dispatchEvent(
                    new KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true })
                );
                panelButton.focus();
                startFieldPhotoLocationPick();
                await frame();
                const started = {
                    active: document.activeElement.id,
                    describedBy: mapContainer.getAttribute('aria-describedby'),
                    shortcuts: mapContainer.getAttribute('aria-keyshortcuts'),
                    label: mapContainer.getAttribute('aria-label'),
                };
                key('Escape');
                await frame();
                const cancelled = {
                    active: document.activeElement.id,
                    status: statusEl.textContent,
                    picking: isFieldPhotoLocationPickActive(),
                };
                drawer.hidden = false;
                panelButton.focus();
                startFieldPhotoLocationPick();
                await frame();
                const controlEnterAllowed = key('Enter', document.getElementById('map-control'));
                const controlKeptPicker = isFieldPhotoLocationPickActive();
                const spacePrevented = !key(' ');
                await frame();
                const spaceOpenedModal = openedModal;
                openedModal = '';
                drawer.hidden = false;
                panelButton.focus();
                startFieldPhotoLocationPick();
                await frame();
                const enterPrevented = !key('Enter');
                await frame();
                const selected = {
                    controlEnterAllowed,
                    controlKeptPicker,
                    spaceOpenedModal,
                    spacePrevented,
                    enterOpenedModal: openedModal,
                    enterPrevented,
                    point: { lat: fieldPhotoUploadMapLatLng.lat, lng: fieldPhotoUploadMapLatLng.lng },
                    picking: isFieldPhotoLocationPickActive(),
                    shortcuts: mapContainer.getAttribute('aria-keyshortcuts'),
                };
                document.title = 'RESULT:' + btoa(JSON.stringify({ started, cancelled, selected }));
            })().catch(error => { document.title = 'ERROR:' + btoa(String(error.stack || error)); });
            </script></body></html>"""
        )

        result = run_chromium_document(document, prefix="wreckscanner-map-picker-", virtual_time_budget=1500)
        self.assertEqual(
            result["started"],
            {
                "active": "map",
                "describedBy": "map-field-photo-pick-hint",
                "shortcuts": "Enter Space Escape",
                "label": "panel.addPhotoPickMapLabel",
            },
        )
        self.assertEqual(
            result["cancelled"],
            {"active": "app-menu-toggle", "status": "panel.addPhotoPickCancelled", "picking": False},
        )
        self.assertEqual(
            result["selected"],
            {
                "controlEnterAllowed": True,
                "controlKeptPicker": True,
                "spaceOpenedModal": "modal-field-photo-upload",
                "spacePrevented": True,
                "enterOpenedModal": "modal-field-photo-upload",
                "enterPrevented": True,
                "point": {"lat": 51.125, "lng": 17.025},
                "picking": False,
                "shortcuts": None,
            },
        )

    def test_partial_upload_stays_open_and_mixed_batch_keeps_valid_files(self):
        upload_js = (
            (ROOT_DIR / "web" / "app" / "field_photo_upload.js")
            .read_text(encoding="utf-8")
            .replace("</script", "<\\/script")
        )
        document = (
            """<!doctype html><html><head><title>pending</title></head><body>
            <div class="modal-backdrop" id="modal-field-photo-upload">
                <form id="field-photo-form">
                    <select id="field-photo-issue-type"><option value="vehicle" selected>Vehicle</option></select>
                    <select id="field-photo-insurance-status"><option value="unknown" selected>Unknown</option></select>
                    <input id="field-photo-files" type="file" multiple>
                    <span data-file-summary-for="field-photo-files"></span>
                    <div id="field-photo-queue" hidden></div>
                    <button id="field-photo-submit"><span>Submit</span></button>
                    <button id="field-photo-retry" hidden>Retry</button>
                    <p id="field-photo-status"></p>
                </form>
            </div>
            <div id="modal-field-photo-thanks" hidden></div>
            <script>
                const FIELD_PHOTO_ISSUE_TYPE_VEHICLE = 'vehicle';
                const FIELD_PHOTO_ISSUE_TYPES = new Set(['vehicle']);
                const FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN = 'unknown';
                const FIELD_PHOTO_MAX_BYTES = 1024;
                const FIELD_PHOTO_MAX_FILES = 25;
                const FIELD_PHOTO_ALLOWED_TYPES = new Set(['image/jpeg']);
                const FIELD_PHOTO_EDIT_TOKEN_MIN_LENGTH = 16;
                const FIELD_PHOTO_EDIT_TOKEN_MAX_LENGTH = 80;
                const PUBLIC_FEATURE_KEYS = { photoUploads: 'photo_uploads' };
                let adminAuthenticated = false;
                let thanksCalls = 0;
                let capturedUploads = [];
                function t(key) { return key; }
                function vehicleInsuranceStatus(value) { return value || 'unknown'; }
                function safeFieldPhotoId(value) { return String(value || '').replace(/[^A-Za-z0-9_-]/g, ''); }
                function escapeHtml(value) { return String(value); }
                function publicFeatureAllowed() { return true; }
                function fieldPhotoIssueAllowed() { return true; }
                function updateFieldPhotoIssueOptions() {}
                function updateFilePickerSummary() {}
                function openFieldPhotoThanksModal() { thanksCalls += 1; }
                function closeModal() {}
                function loadFieldPhotos() { return Promise.resolve(); }
            </script><script>"""
            + upload_js
            + """</script><script>
            (async () => {
                const input = document.getElementById('field-photo-files');
                fieldPhotoUploadEditToken = 'abcdefghijklmnopqrstuvwx';
                fieldPhotoUploadItems = [
                    { file: new File(['ok'], 'ok.jpg', { type: 'image/jpeg' }), status: 'saved',
                        validationError: false, photo: { id: 'photo_ok' }, editToken: fieldPhotoUploadEditToken },
                    { file: new File(['bad'], 'retry.jpg', { type: 'image/jpeg' }), status: 'error',
                        validationError: false, message: 'HTTP 503' },
                ];
                renderFieldPhotoQueue(false);
                completeFieldPhotoUpload(input, fieldPhotoUploadSummary(), fieldPhotoUploadEditToken);
                const partial = {
                    uploadHidden: document.getElementById('modal-field-photo-upload').hidden,
                    thanksCalls,
                    retryHidden: document.getElementById('field-photo-retry').hidden,
                    savedIds: fieldPhotoUploadSavedDraftPhotoIds(),
                };

                fieldPhotoUploadItems = [];
                const files = new DataTransfer();
                files.items.add(new File(['ok'], 'valid.jpg', { type: 'image/jpeg' }));
                files.items.add(new File(['bad'], 'invalid.txt', { type: 'text/plain' }));
                input.files = files.files;
                uploadFieldPhotoItems = async items => { capturedUploads = items.map(item => item.file.name); };
                fieldPhotoUploadMapLatLng = { lat: 51.1, lng: 17.1 };
                await submitFieldPhotoUpload({ preventDefault() {} });
                const mixed = {
                    capturedUploads,
                    queue: fieldPhotoUploadItems.map(item => ({ name: item.file.name, status: item.status })),
                };
                const cryptoDescriptor = Object.getOwnPropertyDescriptor(window, 'crypto');
                let secureRandomError = '';
                Object.defineProperty(window, 'crypto', { value: {}, configurable: true });
                try { randomFieldPhotoEditToken(); }
                catch (error) { secureRandomError = error.message; }
                if (cryptoDescriptor) Object.defineProperty(window, 'crypto', cryptoDescriptor);
                document.title = 'RESULT:' + btoa(JSON.stringify({ partial, mixed, secureRandomError }));
            })().catch(error => { document.title = 'ERROR:' + btoa(String(error.stack || error)); });
            </script></body></html>"""
        )

        result = run_chromium_document(document, prefix="wreckscanner-upload-runtime-", virtual_time_budget=1000)

        self.assertEqual(
            result["partial"],
            {"uploadHidden": False, "thanksCalls": 0, "retryHidden": False, "savedIds": ["photo_ok"]},
        )
        self.assertEqual(result["mixed"]["capturedUploads"], ["valid.jpg"])
        self.assertEqual(
            result["mixed"]["queue"],
            [{"name": "valid.jpg", "status": "pending"}, {"name": "invalid.txt", "status": "error"}],
        )
        self.assertEqual(result["secureRandomError"], "modal.fieldPhoto.secureRandomUnavailable")


    def test_viewport_map_move_fetches_new_area_in_a_real_browser(self):
        photo_js = (ROOT_DIR / "web" / "app" / "field_photos.js").read_text(encoding="utf-8")
        startup_js = (ROOT_DIR / "web" / "app" / "startup.js").read_text(encoding="utf-8")
        photo_js = photo_js.replace("</script", "<\\/script")
        startup_js = startup_js.replace("</script", "<\\/script")
        document = (
            """<!doctype html><html><head><title>pending</title></head><body>
            <main id="map"></main>
            <script>
                const FIELD_PHOTOS_URL = '/api/field-photos';
                let bounds = { west: 16.9, south: 51.0, east: 17.1, north: 51.2 };
                const moveHandlers = [];
                const map = {
                    getBounds: () => ({
                        getWest: () => bounds.west,
                        getSouth: () => bounds.south,
                        getEast: () => bounds.east,
                        getNorth: () => bounds.north,
                    }),
                    on: (event, handler) => {
                        if (event === 'moveend') moveHandlers.push(handler);
                    },
                };
                const requests = [];
                const rendered = [];
                function t(key) { return key; }
                function refreshAdminStatus() { return Promise.resolve(); }
                function maybeStartOnboardingTour() {}
                function apiJson(url) {
                    const parsed = new URL(url, document.location.href);
                    const bbox = parsed.searchParams.get('bbox');
                    requests.push({ bbox, limit: parsed.searchParams.get('limit') });
                    return Promise.resolve({
                        status: 'ok',
                        photos: [{ id: bbox, issue_type: 'infrastructure',
                                   public_review_status: 'approved', lat: 51.1, lon: 17 }],
                        next_cursor: null,
                    });
                }
            </script><script>"""
            + photo_js
            + """</script><script>
                placeFieldPhotos = photos => rendered.push(photos.map(photo => photo.id));
                placeVehicleMarkers = () => {};
                updateLayerCounters = () => {};
            </script><script>"""
            + startup_js
            + """</script><script>
                (async () => {
                    const delay = ms => new Promise(resolve => window.setTimeout(resolve, ms));
                    await delay(80);
                    bounds.east = 17.25;
                    moveHandlers.forEach(handler => handler());
                    await delay(50);
                    bounds.east = 17.35;
                    moveHandlers.forEach(handler => handler());
                    await delay(470);
                    const result = {
                        handlers: moveHandlers.length,
                        requests,
                        rendered,
                        loadState: document.getElementById('field-photo-load-state').hidden,
                        storedPhotos: fieldPhotoLayerData.map(photo => photo.id),
                    };
                    document.title = 'RESULT:' + btoa(JSON.stringify(result));
                })().catch(error => {
                    document.title = 'ERROR:' + btoa(String(error.stack || error));
                });
            </script></body></html>"""
        )

        result = run_chromium_document(
            document,
            prefix="ilestoi-viewport-browser-",
            virtual_time_budget=3500,
        )
        self.assertEqual(result["handlers"], 1)
        self.assertEqual(len(result["requests"]), 2)
        self.assertEqual(len(result["rendered"]), 2)
        self.assertEqual([item["limit"] for item in result["requests"]], ["500", "500"])
        self.assertNotEqual(result["requests"][0]["bbox"], result["requests"][1]["bbox"])
        self.assertEqual(result["storedPhotos"], result["rendered"][-1])
        self.assertTrue(result["loadState"])


if __name__ == "__main__":
    unittest.main()
