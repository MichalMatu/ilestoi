import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const root = new URL('../../', import.meta.url);
const source = readFileSync(new URL('web/app/vehicle_gallery.js', root), 'utf8');

function buildDock() {
    const storage = new Map();
    const dock = { hidden: true, dataset: {} };
    const panel = { hidden: true };
    const toggle = { textContent: '', setAttribute() {} };
    const menu = { checked: true };
    const elements = {
        'vehicle-gallery-dock': dock,
        'vehicle-gallery-panel': panel,
        'vehicle-gallery-dock-toggle': toggle,
        'map-gallery-toggle': menu,
    };
    const context = {
        MAP_GALLERY_VISIBLE_STORAGE_KEY: 'test.gallery',
        MAP_DOCK_MODE_STORAGE_KEY: 'test.dock',
        PUBLIC_FEATURE_KEYS: { vehicleGallery: 'vehicle_gallery' },
        publicFeatureAllowed: () => true,
        t: key => key,
        map: { on() {} },
        document: { getElementById: id => elements[id] || null, addEventListener() {} },
        window: { clearTimeout() {}, setTimeout() { return 1; } },
        localStorage: {
            getItem: key => storage.get(key) ?? null,
            setItem: (key, value) => storage.set(key, String(value)),
        },
        applyMapSourceSliderVisibility() {},
    };
    vm.runInNewContext(source, context);
    return { context, dock, panel, toggle, menu, storage };
}

test('dock cycles between map, gallery, clean map without changing existing slider markup', () => {
    const { context, dock, panel, storage } = buildDock();
    assert.equal(context.vehicleGalleryDockMode(), 'map');
    assert.equal(panel.hidden, true);
    context.cycleVehicleGalleryDockMode();
    assert.equal(context.vehicleGalleryDockMode(), 'gallery');
    assert.equal(panel.hidden, false);
    context.cycleVehicleGalleryDockMode();
    assert.equal(context.vehicleGalleryDockMode(), 'none');
    assert.equal(panel.hidden, true);
    context.cycleVehicleGalleryDockMode();
    assert.equal(context.vehicleGalleryDockMode(), 'map');
    assert.equal(dock.hidden, false);
    assert.equal(storage.get('test.dock'), 'map');
    const html = readFileSync(new URL('web/partials/app_shell.html', root), 'utf8');
    assert.match(html, /id="year-slider"/);
    assert.match(html, /id="year-range"/);
    assert.match(html, /id="vehicle-gallery-dock"/);
    const galleryCss = readFileSync(new URL('web/styles/vehicle_gallery.css', root), 'utf8');
    assert.doesNotMatch(galleryCss, /#year-slider/);
});

test('gallery can be turned off without hiding or restyling map slider', () => {
    const { context, dock, menu, storage } = buildDock();
    context.setVehicleGalleryDockMode('gallery');
    context.setVehicleGalleryEnabled(false);
    assert.equal(dock.hidden, true);
    assert.equal(menu.checked, false);
    assert.equal(storage.get('test.gallery'), 'false');
    context.setVehicleGalleryEnabled(true);
    assert.equal(dock.hidden, false);
    assert.equal(menu.checked, true);
});

test('existing photo grid gets admin overlay only for nominated vehicle previews', () => {
    const popupJs = readFileSync(new URL('web/app/popups.js', root), 'utf8');
    const vehicleJs = readFileSync(new URL('web/app/vehicle_layer.js', root), 'utf8');
    assert.match(popupJs, /if \(!nomination \|\| !adminAuthenticated \|\| !photo\.photoId\) return preview;/);
    assert.match(popupJs, /map-popup-nomination-wrap/);
    assert.match(vehicleJs, /nomination: adminAuthenticated/);
});
