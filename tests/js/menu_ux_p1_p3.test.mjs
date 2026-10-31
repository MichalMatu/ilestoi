import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const get = filename => fs.readFileSync(new URL('../../web/' + filename, import.meta.url), 'utf8');
const html = get('partials/app_shell.html');
const settings = get('partials/admin_modals.html');
const panel = get('styles/panel.css');
const layers = get('styles/map_layers.css');
const modals = get('styles/modals.css');
const maps = get('app/map_sources.js');
const vehicles = get('app/vehicle_layer.js');
const pl = get('i18n/pl.js');
const en = get('i18n/en.js');

test('drawer has a separately scrolling center with fixed header and footer', () => {
    const first = html.indexOf('class="app-menu-drawer-header"');
    const scrollStart = html.indexOf('class="app-menu-drawer-scroll"');
    const map = html.indexOf('class="app-menu-map-panel"');
    const nav = html.indexOf('class="app-menu-drawer-section"');
    const footer = html.indexOf('class="app-menu-drawer-footer"');
    assert.ok(first >= 0 && first < scrollStart && scrollStart < map && map < nav && nav < footer);
    assert.match(html.slice(nav, footer), /<\/nav>\s*<\/div>/);
    assert.match(panel, /\.app-menu-drawer-scroll\s*\{[^}]*overflow-y:\s*auto/s);
    assert.match(panel, /\.app-menu-drawer\s*\{[^}]*overflow:\s*hidden/s);
    assert.match(panel, /\.app-menu-drawer-footer\s*\{[^}]*flex:\s*0 0 auto/s);
});

test('map menu has no redundant section headings and preserves the existing control order', () => {
    const vehicle = html.indexOf('id="toggle-vehicles"');
    const pending = html.indexOf('id="toggle-field-photo-pending"');
    const source = html.indexOf('id="map-source-slider-toggle"');
    const cadastral = html.indexOf('id="toggle-cadastral-parcels"');
    const streets = html.indexOf('id="toggle-street-labels"');
    assert.ok(vehicle >= 0 && vehicle < pending && pending < source &&
        source < cadastral && cadastral < streets);
    assert.doesNotMatch(html, /app-menu-group-title|layers\.reportsGroup|layers\.appearanceGroup/);
    assert.doesNotMatch(panel, /\.app-menu-group-title/);
    for (const bundle of [pl, en]) {
        assert.doesNotMatch(bundle, /'layers\.(?:reportsGroup|appearanceGroup)'/);
    }
    assert.match(html, /data-i18n="panel.baseMap">Pokaż wybór podkładu/);
    assert.match(html, /onchange="setMapSourceSliderVisible\(this.checked\)"/);
    assert.match(maps, /function setMapSourceSliderVisible\(visible\)/);
    assert.match(html, /id="street-labels-unavailable"[^>]*hidden/);
    assert.match(maps, /unavailable\.hidden = supported/);
});

test('vehicle filters use exactly four always-visible accessible selectors', () => {
    assert.match(html, /<div class="vehicle-filter-choice-grid" role="group"/);
    assert.match(html, /data-i18n-attr="aria-label:layers.vehicleFilters"/);
    for (const [id, handler] of [
        ['vehicle-insurance-select', 'setVehicleInsuranceFilter'],
        ['vehicle-standing-select', 'setVehicleStandingFilterDays'],
        ['vehicle-photo-select', 'setVehiclePhotoFilter'],
        ['vehicle-resolution-select', 'setVehicleResolutionFilter'],
    ]) {
        assert.equal(html.split('id="' + id + '"').length - 1, 1);
        assert.ok(html.includes('onchange="' + handler + '('), id);
        assert.ok(vehicles.includes("'" + id + "':"), id);
    }
    assert.doesNotMatch(html, /vehicle-(?:cycle-filter|filter-details|filter-tray)/);
    assert.doesNotMatch(html, /<details[^>]*vehicle/);
    assert.doesNotMatch(vehicles, /function (?:cycleVehicle|vehicleFilterCounts|updateVehicleFilterButton)/);
    assert.match(layers, /\.vehicle-filter-choice-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/s);
    assert.match(layers, /@media \(max-width: 350px\)\s*\{\s*\.vehicle-filter-choice-grid\s*\{\s*grid-template-columns:\s*minmax\(0, 1fr\)/s);
    assert.match(layers, /\.vehicle-filter-choice-grid select\s*\{[^}]*min-height:\s*40px/s);
});

test('persisted filter values appear in selects without rebuilding marker counts', () => {
    const start = vehicles.indexOf('function updateVehicleFilterSelectors()');
    const end = vehicles.indexOf('\nfunction vehiclePhotoPopup(', start);
    assert.ok(start > 0 && end > start);
    const controls = new Map(['vehicle-insurance-select', 'vehicle-standing-select',
        'vehicle-photo-select', 'vehicle-resolution-select'].map(id => [id, { value: '' }]));
    const ctx = {
        document: { getElementById(id) { return controls.get(id) || null; } },
    };
    vm.runInNewContext(`let vehicleInsuranceFilter = 'uninsured';
        let vehicleStandingFilterDays = 60;
        let vehiclePhotoFilter = 'above_6';
        let vehicleResolutionFilter = 'removed';
        ${vehicles.slice(start, end)}
        this.sync = updateVehicleFilterSelectors;`, ctx);
    ctx.sync();
    assert.deepEqual([...controls.values()].map(el => el.value),
        ['uninsured', '60', 'above_6', 'removed']);
    assert.doesNotMatch(vehicles, /function (?:vehicleFilterCounts|emptyVehicleFilterCounts|updateVehicleFilterButton)/);
    assert.doesNotMatch(vehicles, /updateVehicleFilterControlsAndCounts/);
    assert.doesNotMatch(get('app/vehicle_resolution.js'), /cycleVehicleResolutionFilter/);
    assert.match(get('app/field_photos.js'), /updateVehicleFilterSelectors\(\)/);
});

test('orthophoto advanced options are collapsed without disabling any existing inputs', () => {
    assert.match(settings, /<details class="settings-advanced" id="settings-advanced">/);
    assert.match(settings, /<summary data-i18n="modal.settings.advanced">/);
    for (const id of ['enhancement-enabled', 'enhancement-clahe', 'enhancement-tile',
        'enhancement-p-low', 'enhancement-p-high', 'enhancement-out-low',
        'enhancement-out-high', 'enhancement-decast', 'enhancement-reset']) {
        assert.ok(settings.includes('id="' + id + '"'), id);
    }
    assert.match(modals, /\.settings-advanced summary:focus-visible/);
});

test('translations and touch/focus affordances exist in both languages', () => {
    for (const key of ['layers.vehicleInsuranceFull','layers.vehicleStandingFull','layers.vehiclePhotosFull',
        'layers.vehicleRemovedFull','layers.streetLabelsUnavailable','modal.settings.advanced']) {
        assert.ok(pl.includes("'" + key + "':"), 'pl '+key);
        assert.ok(en.includes("'" + key + "':"), 'en '+key);
    }
    assert.match(panel, /\.app-menu-footer-icon\s*\{[^}]*width:\s*var\(--control-hit-target\)/s);
    assert.match(panel, /\.app-menu-footer-icon:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--primary\)/s);
    assert.match(modals, /\.modal-close:focus-visible/);
});

test('mouse hover is subtle while keyboard focus stays visible across menu controls', () => {
    const styleFor = selector => {
        const found = panel.split(selector + ' {')[1];
        assert.ok(found, 'missing selector: ' + selector);
        return found.split('}')[0];
    };
    for (const control of [
        '.app-menu-button',
        '.app-menu-drawer-item',
        '.app-menu-footer-link',
        '.app-menu-footer-icon',
    ]) {
        const hover = styleFor(control + ':hover');
        const focus = styleFor(control + ':focus-visible');
        assert.doesNotMatch(hover, /\boutline(?:-color|-width|-style)?\s*:/, control + ':hover must not draw a focus ring');
        assert.match(focus, /outline:\s*2px solid var\(--primary\)/, control + ':focus-visible must retain a visible keyboard indicator');
        assert.match(focus, /outline-offset:\s*2px/, control + ':focus-visible must not clip against the control');
    }
    assert.match(styleFor('.app-menu-drawer-item:hover'), /background:\s*var\(--surface-control-strong\)/);
    assert.match(styleFor('.app-menu-footer-icon:hover'), /border-color:\s*var\(--border-strong\)/);
});

test('no other mouse hover in the app styles draws a keyboard focus outline', () => {
    const stylesDir = new URL('../../web/styles/', import.meta.url);
    for (const name of fs.readdirSync(stylesDir).filter(name => name.endsWith('.css'))) {
        const sheet = fs.readFileSync(new URL(name, stylesDir), 'utf8');
        for (const match of sheet.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
            const [, selector, declarations] = match;
            if (!selector.includes(':hover')) continue;
            const visibleOutline = /\boutline(?:-width)?\s*:\s*(?!none\b|0(?:px)?\b)[^;]+;?/i;
            assert.doesNotMatch(declarations, visibleOutline, name + ' / ' + selector.trim());
        }
    }
});
