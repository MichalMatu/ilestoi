import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

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

test('layer groups separate reports from presentation without changing layer controls', () => {
    const report = html.indexOf('data-i18n="layers.reportsGroup"');
    const vehicle = html.indexOf('id="toggle-vehicles"');
    const pending = html.indexOf('id="toggle-field-photo-pending"');
    const appearance = html.indexOf('data-i18n="layers.appearanceGroup"');
    const source = html.indexOf('id="map-source-slider-toggle"');
    const cadastral = html.indexOf('id="toggle-cadastral-parcels"');
    const streets = html.indexOf('id="toggle-street-labels"');
    assert.ok(report < vehicle && vehicle < pending && pending < appearance &&
        appearance < source && source < cadastral && cadastral < streets);
    assert.match(html, /data-i18n="panel.baseMap">Pokaż wybór podkładu/);
    assert.match(html, /onchange="setMapSourceSliderVisible\(this.checked\)"/);
    assert.match(maps, /function setMapSourceSliderVisible\(visible\)/);
    assert.match(html, /id="street-labels-unavailable"[^>]*hidden/);
    assert.match(maps, /unavailable\.hidden = supported/);
});

test('vehicle selectors are accessible, optional, and synchronized with cycle state', () => {
    assert.match(html, /<details class="vehicle-filter-details"/);
    for (const [id, handler] of [
        ['vehicle-insurance-select', 'setVehicleInsuranceFilter'],
        ['vehicle-standing-select', 'setVehicleStandingFilterDays'],
        ['vehicle-photo-select', 'setVehiclePhotoFilter'],
        ['vehicle-resolution-select', 'setVehicleResolutionFilter'],
    ]) {
        assert.ok(html.includes('id="' + id + '"'));
        assert.ok(html.includes('onchange="' + handler + '('));
        assert.ok(vehicles.includes("'" + id + "':"));
    }
    assert.match(layers, /\.vehicle-cycle-filter\s*\{[^}]*min-height:\s*36px/s);
    assert.match(layers, /\.vehicle-filter-choice-grid select\s*\{[^}]*min-height:\s*40px/s);
    assert.match(html, /id="vehicle-insurance-cycle-filter"/);
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
    for (const key of ['layers.reportsGroup','layers.appearanceGroup','layers.vehicleChooseFilters',
        'layers.vehicleInsuranceFull','layers.vehicleStandingFull','layers.vehiclePhotosFull',
        'layers.vehicleRemovedFull','layers.streetLabelsUnavailable','modal.settings.advanced']) {
        assert.ok(pl.includes("'" + key + "':"), 'pl '+key);
        assert.ok(en.includes("'" + key + "':"), 'en '+key);
    }
    assert.match(panel, /\.app-menu-footer-icon\s*\{[^}]*width:\s*var\(--control-hit-target\)/s);
    assert.match(panel, /\.app-menu-footer-icon:hover,\s*\.app-menu-footer-icon:focus-visible\s*\{[^}]*outline:\s*3px/s);
    assert.match(modals, /\.modal-close:focus-visible/);
});
