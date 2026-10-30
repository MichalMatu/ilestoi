import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../../web/app/map_sources.js', import.meta.url), 'utf8');
const shell = fs.readFileSync(new URL('../../web/partials/app_shell.html', import.meta.url), 'utf8');
const config = fs.readFileSync(new URL('../../web/config.js', import.meta.url), 'utf8');
const pl = fs.readFileSync(new URL('../../web/i18n/pl.js', import.meta.url), 'utf8');
const en = fs.readFileSync(new URL('../../web/i18n/en.js', import.meta.url), 'utf8');
const start = source.indexOf('function buildMapLabelLayer()');
const end = source.indexOf('\nfunction renderMapSourceTicks(', start);
assert.ok(start >= 0 && end > start);

function harness(initialVisible = true) {
    const active = new Set();
    const stored = new Map();
    const state = { supported: true, disabledClass: false, options: null, calls: 0 };
    const row = { classList: { toggle(name, flag) {
        assert.equal(name, 'is-disabled');
        state.disabledClass = flag;
    } } };
    const checkbox = {
        checked: initialVisible,
        disabled: false,
        closest(selector) { assert.equal(selector, '.layer-toggle'); return row; },
    };
    const unavailable = { hidden: true };
    const ctx = {
        initialVisible,
        MAX_MAP_ZOOM: 22,
        STREET_LABELS_WMS_URL: 'https://example.test/wms',
        MAP_STREET_LABELS_VISIBLE_STORAGE_KEY: 'street-labels-test',
        document: { getElementById(id) {
            if (id === 'toggle-street-labels') return checkbox;
            if (id === 'street-labels-unavailable') return unavailable;
            assert.fail('unexpected element id: ' + id);
        } },
        localStorage: { setItem(key, value) { stored.set(key, value); } },
        activeMapSource: () => ({ labelsOverlay: state.supported }),
        map: {
            hasLayer(layer) { return active.has(layer); },
            removeLayer(layer) { active.delete(layer); },
        },
        L: { tileLayer: { wms(url, options) {
            state.calls += 1;
            assert.equal(url, 'https://example.test/wms');
            state.options = options;
            return { addTo() { active.add(this); return this; } };
        } } },
    };
    vm.runInNewContext(
        'let mapLabelLayer = null; let mapLabelsVisible = initialVisible;\n' +
        source.slice(start, end) +
        '\nthis.api = { updateMapLabelLayer, toggleMapLabelLayer };',
        ctx
    );
    return { ctx, state, active, stored, checkbox, unavailable };
}

test('street-label WMS has reduced opacity and unchanged GUGiK source', () => {
    const h = harness();
    h.ctx.api.updateMapLabelLayer();
    assert.equal(h.state.options.layers, 'A08_Ulice');
    assert.equal(h.state.options.opacity, 0.6);
    assert.equal(h.state.options.transparent, true);
    assert.equal(h.active.size, 1);
    assert.equal(h.checkbox.checked, true);
    assert.equal(h.checkbox.disabled, false);
});

test('street-label switch removes/reuses overlay and saves preference', () => {
    const h = harness();
    h.ctx.api.updateMapLabelLayer();
    h.ctx.api.toggleMapLabelLayer(false);
    assert.equal(h.active.size, 0);
    assert.equal(h.stored.get('street-labels-test'), '0');
    assert.equal(h.checkbox.checked, false);
    h.ctx.api.toggleMapLabelLayer(true);
    assert.equal(h.active.size, 1);
    assert.equal(h.state.calls, 1, 'do not create a new WMS layer for each toggle');
    assert.equal(h.stored.get('street-labels-test'), '1');
});

test('OSM disables switch and hides separate overlay while keeping preference', () => {
    const h = harness();
    h.ctx.api.updateMapLabelLayer();
    h.state.supported = false;
    h.ctx.api.updateMapLabelLayer();
    assert.equal(h.active.size, 0);
    assert.equal(h.checkbox.disabled, true);
    assert.equal(h.state.disabledClass, true);
    assert.equal(h.unavailable.hidden, false);
    assert.equal(h.checkbox.checked, true, 'retain preference for aerial maps');
    h.state.supported = true;
    h.ctx.api.updateMapLabelLayer();
    assert.equal(h.active.size, 1);
    assert.equal(h.checkbox.disabled, false);
    assert.equal(h.state.disabledClass, false);
    assert.equal(h.unavailable.hidden, true);
});

test('saved disabled preference is respected when switching map sources', () => {
    const h = harness(false);
    h.ctx.api.updateMapLabelLayer();
    assert.equal(h.active.size, 0);
    assert.equal(h.checkbox.checked, false);
    h.state.supported = false;
    h.ctx.api.updateMapLabelLayer();
    h.state.supported = true;
    h.ctx.api.updateMapLabelLayer();
    assert.equal(h.active.size, 0);
    assert.equal(h.state.calls, 0);
});

test('map filter and translations exist without changing cadastral settings', () => {
    assert.match(shell, /id="toggle-street-labels" checked/);
    assert.match(shell, /onchange="toggleMapLabelLayer\(this.checked\)"/);
    assert.match(shell, /data-i18n="layers.streetLabels"/);
    assert.match(pl, /'layers.streetLabels': 'Nazwy ulic'/);
    assert.match(en, /'layers.streetLabels': 'Street names'/);
    assert.match(config, /MAP_STREET_LABELS_VISIBLE_STORAGE_KEY/);
    assert.match(source, /localStorage.getItem\(MAP_STREET_LABELS_VISIBLE_STORAGE_KEY\)/);
    assert.match(shell, /id="toggle-cadastral-parcels"/);
});
