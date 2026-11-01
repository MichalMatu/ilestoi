import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const root = new URL('../../', import.meta.url);
const gallerySource = readFileSync(new URL('web/app/vehicle_gallery.js', root), 'utf8');
const mapSource = readFileSync(new URL('web/app/map_sources.js', root), 'utf8');
const start = mapSource.indexOf('function isMapSourceSliderVisible()');
const end = mapSource.indexOf('function updateMapSourceUi()', start);
assert.ok(start >= 0 && end > start);
const mapSourceVisibilityFns = mapSource.slice(start, end);

function buildDock({ saved = {}, galleryAllowed = true } = {}) {
    const storage = new Map(Object.entries(saved));
    const galleryRow = { hidden: false };
    const gallery = { checked: false, disabled: false, closest: () => galleryRow };
    const selector = { checked: false };
    const slider = { hidden: false };
    const dock = { hidden: true, dataset: {} };
    const panel = { hidden: true };
    const elements = {
        'map-gallery-toggle': gallery,
        'map-source-slider-toggle': selector,
        'year-slider': slider,
        'vehicle-gallery-dock': dock,
        'vehicle-gallery-panel': panel,
    };
    const access = { galleryAllowed };
    const mapHandlers = new Map();
    const documentHandlers = new Map();
    const context = {
        MAP_DOCK_MODE_STORAGE_KEY: 'test.dock',
        PUBLIC_FEATURE_KEYS: { vehicleGallery: 'vehicle_gallery' },
        publicFeatureAllowed: () => access.galleryAllowed,
        t: key => key,
        map: { on: (name, handler) => mapHandlers.set(name, handler) },
        document: {
            getElementById: id => elements[id] || null,
            addEventListener: (name, handler) => documentHandlers.set(name, handler),
        },
        window: { clearTimeout() {}, setTimeout() { return 1; } },
        localStorage: {
            getItem: key => storage.get(key) ?? null,
            setItem: (key, value) => storage.set(key, String(value)),
        },
    };
    vm.runInNewContext(mapSourceVisibilityFns, context);
    vm.runInNewContext(gallerySource, context);
    const state = () => ({
        mode: context.vehicleGalleryDockMode(),
        gallery: gallery.checked,
        slider: selector.checked,
        sliderHidden: slider.hidden,
        dockHidden: dock.hidden,
        panelHidden: panel.hidden,
    });
    return { context, access, storage, galleryRow, gallery, selector, slider, dock, panel, mapHandlers, documentHandlers, state };
}

test('default map mode preserves original slider and unchecks gallery', () => {
    const ui = buildDock();
    assert.deepEqual(ui.state(), {
        mode: 'map', gallery: false, slider: true,
        sliderHidden: false, dockHidden: true, panelHidden: true,
    });
});

test('gallery selection immediately opens gallery, replaces map and never checks both', () => {
    const ui = buildDock();
    ui.context.setVehicleGalleryEnabled(true);
    assert.deepEqual(ui.state(), {
        mode: 'gallery', gallery: true, slider: false,
        sliderHidden: true, dockHidden: false, panelHidden: false,
    });
    assert.equal(ui.storage.get('test.dock'), 'gallery');
    ui.context.setMapSourceSliderVisible(true);
    assert.equal(ui.state().mode, 'map');
    assert.equal(ui.state().gallery, false);
    assert.equal(ui.state().slider, true);
    assert.equal(ui.state().sliderHidden, false);
});

test('unchecking either option results in clean map; another option still opens normally', () => {
    const ui = buildDock();
    ui.context.setMapSourceSliderVisible(false);
    assert.equal(ui.state().mode, 'none');
    assert.equal(ui.state().gallery, false);
    assert.equal(ui.state().slider, false);
    ui.context.setVehicleGalleryEnabled(true);
    assert.equal(ui.state().mode, 'gallery');
    ui.context.setVehicleGalleryEnabled(false);
    assert.equal(ui.state().mode, 'none');
    assert.equal(ui.state().dockHidden, true);
    ui.context.setMapSourceSliderVisible(true);
    assert.equal(ui.state().mode, 'map');
});

test('reload remembers only one state even when old legacy checkbox flags both say true', () => {
    const ui = buildDock({
        saved: {
            'test.dock': 'gallery',
            'wreckscanner.mapSourceSliderVisible.v1': 'true',
            'wreckscanner.vehicleGalleryVisible.v1': 'true',
        },
    });
    assert.equal(ui.state().mode, 'gallery');
    assert.equal(ui.state().gallery, true);
    assert.equal(ui.state().slider, false);
    ui.context.setVehicleGalleryEnabled(false);
    const reloaded = buildDock({ saved: Object.fromEntries(ui.storage) });
    assert.equal(reloaded.state().mode, 'none');
    assert.equal(reloaded.state().gallery, false);
    assert.equal(reloaded.state().slider, false);
    assert.equal(ui.storage.has('test.gallery'), false);
});

test('unavailable gallery cannot be opened; access restoration restores only stored active choice', () => {
    const ui = buildDock({ saved: { 'test.dock': 'gallery' }, galleryAllowed: false });
    assert.equal(ui.state().mode, 'none');
    assert.equal(ui.state().gallery, false);
    assert.equal(ui.gallery.disabled, true);
    assert.equal(ui.galleryRow.hidden, true);
    ui.context.setVehicleGalleryEnabled(true);
    assert.equal(ui.state().mode, 'none');
    ui.access.galleryAllowed = true;
    ui.context.updateVehicleGalleryAvailability();
    assert.equal(ui.state().mode, 'gallery');
    ui.context.setMapSourceSliderVisible(true);
    ui.access.galleryAllowed = false;
    ui.context.updateVehicleGalleryAvailability();
    assert.equal(ui.state().mode, 'map');
    assert.equal(ui.state().slider, true);
});

test('gallery hide/show buttons and popup focus update the single panel mode', () => {
    const ui = buildDock();
    ui.context.setVehicleGalleryDockMode('gallery');
    ui.context.setVehicleGalleryDockMode('none');
    assert.equal(ui.state().mode, 'none');
    ui.context.setVehicleGalleryDockMode('gallery');
    ui.context.setVehicleGalleryDockMode('map');
    assert.equal(ui.state().mode, 'map');
    assert.equal(ui.storage.get('test.dock'), 'map');
});

test('headerless gallery can be closed from map or Escape without changing other modes', () => {
    const ui = buildDock();
    const mapTap = ui.mapHandlers.get('click');
    const onKeyDown = ui.documentHandlers.get('keydown');
    assert.equal(typeof mapTap, 'function');
    assert.equal(typeof onKeyDown, 'function');
    ui.context.setVehicleGalleryDockMode('gallery');
    mapTap();
    assert.equal(ui.state().mode, 'none');
    assert.equal(ui.storage.get('test.dock'), 'none');
    ui.context.setVehicleGalleryDockMode('gallery');
    onKeyDown({ key: 'Enter' });
    assert.equal(ui.state().mode, 'gallery');
    onKeyDown({ key: 'Escape' });
    assert.equal(ui.state().mode, 'none');
    ui.context.setVehicleGalleryDockMode('map');
    mapTap();
    onKeyDown({ key: 'Escape' });
    assert.equal(ui.state().mode, 'map');
});

test('mobile gallery is photo-first: no header, broad dock and larger scrolling cards', () => {
    const html = readFileSync(new URL('web/partials/app_shell.html', root), 'utf8');
    const css = readFileSync(new URL('web/styles/vehicle_gallery.css', root), 'utf8');
    assert.match(html, /id="vehicle-gallery-items"[^>]*role="list"/);
    assert.match(html, /id="vehicle-gallery-map-dots"/);
    assert.doesNotMatch(html, /vehicle-gallery-header|vehicle-gallery-actions/);
    assert.doesNotMatch(css, /\.vehicle-gallery-header|\.vehicle-gallery-actions/);
    assert.match(css, /@media \(max-width: 600px\) \{[\s\S]*?width: calc\(100vw - 16px\)/);
    assert.match(css, /\.vehicle-gallery-card img \{ width: 128px; height: 96px; \}/);
    assert.match(css, /\.vehicle-gallery-items \{[\s\S]*?overflow-x: auto/);
});

test('menu has exactly two exclusive selectors, simple name and no second gallery opener', () => {
    const html = readFileSync(new URL('web/partials/app_shell.html', root), 'utf8');
    assert.match(html, /id="map-source-slider-toggle"[\s\S]*?onchange="setMapSourceSliderVisible\(this\.checked\)"/);
    assert.match(html, /id="map-gallery-toggle"[\s\S]*?onchange="setVehicleGalleryEnabled\(this\.checked\)"/);
    assert.match(html, /Galeria pojazdów/);
    assert.doesNotMatch(html, /vehicle-gallery-menu-open|vehicle-gallery-dock-toggle|openVehicleGalleryFromMenu/);
    const pl = readFileSync(new URL('web/i18n/pl.js', root), 'utf8');
    assert.match(pl, /'gallery\.menuToggle': 'Galeria pojazdów'/);
    const config = readFileSync(new URL('web/config.js', root), 'utf8');
    assert.doesNotMatch(config, /MAP_SOURCE_SLIDER_VISIBLE_STORAGE_KEY|MAP_GALLERY_VISIBLE_STORAGE_KEY/);
});

test('star icons are identical anchored SVG geometry for filled and outline priority', () => {
    const popup = readFileSync(new URL('web/app/popups.js', root), 'utf8');
    const css = readFileSync(new URL('web/styles/popups.css', root), 'utf8');
    assert.match(popup, /data-gallery-priority="\$\{level\}"[\s\S]*?<svg viewBox="0 0 24 24"/);
    assert.match(css, /map-popup-nomination-wrap\s*\{[\s\S]*?aspect-ratio: 4 \/ 3;/);
    assert.match(css, /\.map-popup-nomination svg\s*\{[\s\S]*?width: 20px;[\s\S]*?height: 20px;/);
    assert.match(css, /\[data-gallery-priority\]:not\(\[data-gallery-priority="0"\]\) svg \{ fill: currentColor; \}/);
    assert.doesNotMatch(popup, /\$\{level \? '★' : '☆'\}/);
    assert.doesNotMatch(gallerySource, /button\.textContent = priority \? '★' : '☆'/);
});

test('original slider stylesheet stays unchanged and mobile zoom remains accessible', () => {
    const css = readFileSync(new URL('web/styles/vehicle_gallery.css', root), 'utf8');
    assert.doesNotMatch(css, /^\s*#year-slider\b/m);
    const sliderCss = readFileSync(new URL('web/styles/map_controls.css', root), 'utf8');
    assert.match(sliderCss, /#year-slider\s*\{\s*position: fixed;/);
    const mapCss = readFileSync(new URL('web/styles/map.css', root), 'utf8');
    assert.match(mapCss, /#map \.leaflet-bottom\.leaflet-right\s*\{\s*bottom: calc\(56px/);
});
