import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const get = name => readFileSync(new URL('../../web/' + name, import.meta.url), 'utf8');
const html = get('partials/app_shell.html');
const js = get('app/ux_map_shell.js');
const css = get('styles/ux_map_shell.css');

test('new responsive shell keeps every existing vehicle and map control exactly once', () => {
    for (const id of [
        'toggle-vehicles', 'vehicle-insurance-select', 'vehicle-standing-select',
        'vehicle-photo-select', 'vehicle-resolution-select', 'toggle-field-photo-infrastructure',
        'toggle-field-photo-smoke', 'toggle-field-photo-pending', 'toggle-cadastral-parcels',
        'toggle-street-labels', 'map-source-slider-toggle', 'map-gallery-toggle',
        'panel-add-field-photo', 'map-add-field-photo',
    ]) {
        assert.equal(html.split('id="' + id + '"').length - 1, 1, id);
    }
    assert.match(get('index.html'), /<script src="\/app\/ux_map_shell\.js"><\/script>/);
    assert.match(get('styles.css'), /@import url\("\/styles\/ux_map_shell\.css"\)/);
});

test('mobile map panel has three distinct accessible tabs and sections', () => {
    for (const name of ['vehicles', 'layers', 'tools']) {
        assert.match(html, new RegExp('data-ux-tab="' + name + '"'));
        assert.match(html, new RegExp('data-ux-panel="' + name + '"'));
        assert.match(html, new RegExp('id="ux-panel-' + name + '"'));
    }
    assert.match(html, /class="ux-panel-tabs" role="tablist"/);
    assert.match(css, /@media \(max-width: 720px\)/);
    assert.match(css, /height: min\(67dvh, 650px\)/);
});

test('responsive shell changes visibility without losing state or rebuilding Leaflet', () => {
    const mobile = { matches: true, addEventListener: () => {} };
    const desktop = { matches: false, addEventListener: () => {} };
    const tabNames = ['vehicles', 'layers', 'tools'];
    function el(name, dataKey, dataValue) {
        const attributes = {};
        return {
            id: name,
            dataset: { [dataKey]: dataValue },
            hidden: false, tabIndex: 0,
            attributes,
            setAttribute(k, v) { attributes[k] = v; },
            addEventListener: () => {},
            focus() { this.focused = true; },
        };
    }
    const tabs = tabNames.map(n => el('ux-tab-' + n, 'uxTab', n));
    const panels = tabNames.map(n => el('ux-panel-' + n, 'uxPanel', n));
    const toolsNav = { hidden: false };
    const handle = el('ux-sheet-handle', 'none', '');
    const byId = new Map([...tabs, handle].map(e => [e.id, e]));
    const document = {
        querySelectorAll(selector) { return selector === '[data-ux-tab]' ? tabs : panels; },
        querySelector(selector) { return selector === '.ux-tools-nav' ? toolsNav : null; },
        getElementById(id) { return byId.get(id) || null; },
        addEventListener() {},
        body: { classList: { toggle() {} } },
    };
    let dockOpened = false;
    const ctx = {
        document,
        window: { matchMedia: query => query.includes('max-width') ? mobile : desktop },
        t: k => k,
        isAppMenuOpen: () => dockOpened,
        setAppMenuOpen: () => { dockOpened = true; },
        updateAppMenuState: () => {},
        syncPageIsolation: () => {},
        requestAnimationFrame: callback => callback(),
    };
    vm.createContext(ctx);
    vm.runInContext(js, ctx);
    assert.deepEqual(panels.map(p => p.hidden), [false, true, true]);
    assert.equal(toolsNav.hidden, true);
    assert.equal(vm.runInContext("setUxMapPanelTab('tools')", ctx), true);
    assert.deepEqual(panels.map(p => p.hidden), [true, true, false]);
    assert.equal(toolsNav.hidden, false);
    assert.equal(tabs[2].attributes['aria-selected'], 'true');
    mobile.matches = false;
    vm.runInContext('updateUxMapPanelState()', ctx);
    assert.deepEqual(panels.map(p => p.hidden), [false, false, false]);
    assert.equal(vm.runInContext("setUxMapPanelTab('unknown')", ctx), false);
    desktop.matches = true;
    vm.runInContext('updateUxMapResponsiveLayout()', ctx);
    assert.equal(dockOpened, true, 'large desktop activates the persistent dock');
});


test('quick report action reuses authorized upload flow and public feature gate', () => {
    assert.match(js, /openFieldPhotoUploadFromPanel\(\)/);
    assert.match(get('app/settings.js'), /\['panel-add-field-photo', 'map-add-field-photo'\]/);
    assert.match(get('app/field_photo_upload.js'), /\['panel-add-field-photo', 'map-add-field-photo'\]/);
    assert.match(get('app/onboarding_tour.js'), /setUxMapPanelTab\(step\.tab \|\| 'vehicles'\)/);
    assert.doesNotMatch(js, /fetch\(|localStorage|new L\.|L\.map\(/);
});
