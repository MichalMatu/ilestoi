import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const sources = ['web/app/field_photos.js', 'web/app/overview_clusters.js', 'web/app/map_markers.js']
    .map(path => ({ path, source: readFileSync(path, 'utf8') }));

function harness(respond, startZoom = 8) {
    const requests = [];
    const markers = [];
    const bounds = { west: 16, south: 50, east: 18, north: 52 };
    let zoom = startZoom;
    const fits = [];
    const states = [];
    const removed = [];
    let vehicleVisible = true;
    const categories = { infrastructure: true, smoke: true };
    let pendingVisible = true;
    const map = {
        getZoom: () => zoom,
        getBounds: () => ({
            getWest: () => bounds.west, getEast: () => bounds.east,
            getSouth: () => bounds.south, getNorth: () => bounds.north,
        }),
        removeLayer: marker => removed.push(marker),
        fitBounds: (target, options) => fits.push({ target, options }),
    };
    const context = vm.createContext({
        URLSearchParams,
        AbortController,
        map,
        FIELD_PHOTOS_URL: '/api/field-photos',
        adminAuthenticated: false,
        pendingVehiclePhotoFocusId: '',
        vehicleInsuranceFilter: 'all',
        vehicleStandingFilterDays: 0,
        vehiclePhotoFilter: 'off',
        vehicleResolutionFilter: 'all',
        VEHICLE_FILTER_ALL: 'all',
        VEHICLE_STANDING_FILTER_OFF: 0,
        VEHICLE_PHOTO_FILTER_OFF: 'off',
        window: { setTimeout: () => 1, clearTimeout() {} },
        L: {
            divIcon: options => options,
            marker(point, options) {
                const handlers = {};
                const m = {
                    point, options, handlers,
                    addTo() { markers.push(this); return this; },
                    bindTooltip(text) { this.tooltip = text; return this; },
                    getElement() { return { setAttribute() {} }; },
                    on(name, handler) { handlers[name] = handler; return this; },
                };
                return m;
            },
        },
        apiJson(url, options) {
            requests.push({ url, options });
            return respond(url, options, requests.length);
        },
        t: (key, params) => key + (params?.n ?? ''),
    });
    for (const file of sources) vm.runInContext(file.source, context, { filename: file.path });
    context.setFieldPhotoLoadState = state => states.push(state);
    context.clearVehicleMarkers = () => {};
    context.placeVehicleMarkers = () => {};
    context.updateLayerCounters = () => {};
    context.vehicleLayerAllowed = () => vehicleVisible;
    context.fieldPhotoIssueVisible = issue => categories[issue];
    context.pendingFieldPhotoLayerAllowed = () => pendingVisible;
    const run = code => vm.runInContext(code, context);
    return {
        requests, markers, removed, bounds, fits, states, context, run,
        setZoom: value => { zoom = value; },
        setVehicleVisible: value => { vehicleVisible = value; },
        setPending: value => { pendingVisible = value; },
        setCategory: (name, value) => { categories[name] = value; },
    };
}

const sample = (vehicles = 4, infrastructure = 2, smoke = 1, pending = 3) => ({
    lat: 51, lon: 17, total: vehicles + infrastructure + smoke + pending,
    vehicles, infrastructure, smoke, pending,
});

test('zoomed out visitors request only a bounded aggregate endpoint and render photo-count marker', async () => {
    const h = harness(async () => ({ status: 'ok', clusters: [sample()] }));
    await h.run('loadFieldPhotos()');
    assert.equal(h.requests.length, 1);
    assert.ok(h.requests[0].url.startsWith('/api/field-photos/clusters?bbox='));
    assert.equal(h.run('fieldPhotoOverviewActive'), true);
    assert.deepEqual(Array.from(h.run('fieldPhotoLayerData')), []);
    assert.equal(h.markers.length, 1);
    assert.match(h.markers[0].options.icon.html, /map-overview-cluster/);
    assert.match(h.markers[0].options.icon.html, />10</);
    assert.match(h.markers[0].tooltip, /10/);
    assert.deepEqual(h.states, ['loading', 'ready']);
    h.markers[0].handlers.click();
    assert.equal(h.fits.length, 1);
    assert.equal(h.fits[0].target.length, 2);
    const [sw, ne] = h.fits[0].target;
    assert.ok(sw[0] < 51 && ne[0] > 51);
    assert.ok(sw[1] < 17 && ne[1] > 17);
});

test('switching to detail zoom fetches paginated records, not aggregate positions', async () => {
    const h = harness(async url => url.includes('/clusters?')
        ? { status: 'ok', clusters: [sample()] }
        : { status: 'ok', photos: [{ id: 'real', lat: 51, lon: 17 }], next_cursor: null });
    await h.run('loadFieldPhotos()');
    h.setZoom(11);
    h.context.placeFieldPhotos = photos => h.markers.push({ detailIds: photos.map(p => p.id) });
    await h.run('loadFieldPhotos()');
    assert.equal(h.requests.length, 2);
    assert.ok(h.requests[1].url.includes('?bbox='));
    assert.ok(!h.requests[1].url.includes('/clusters?'));
    assert.equal(h.run('fieldPhotoOverviewActive'), false);
    assert.deepEqual(Array.from(h.run('fieldPhotoLayerData.map(x => x.id)')), ['real']);
    assert.deepEqual(Array.from(h.markers.at(-1).detailIds), ['real']);
});

test('admin, deep link and advanced vehicle filter bypass overview mode', () => {
    const h = harness(async () => ({ status: 'ok', clusters: [] }));
    assert.equal(h.run('fieldPhotoLoadMode()'), 'overview');
    h.context.adminAuthenticated = true;
    assert.equal(h.run('fieldPhotoLoadMode()'), 'photos');
    h.context.adminAuthenticated = false;
    h.context.pendingVehiclePhotoFocusId = 'photo_1';
    assert.equal(h.run('fieldPhotoLoadMode()'), 'photos');
    h.context.pendingVehiclePhotoFocusId = '';
    for (const [key, value] of [
        ['vehicleInsuranceFilter', 'uninsured'],
        ['vehicleStandingFilterDays', 14],
        ['vehiclePhotoFilter', 'above_6'],
        ['vehicleResolutionFilter', 'removed'],
    ]) {
        h.context[key] = value;
        assert.equal(h.run('fieldPhotoLoadMode()'), 'photos');
        h.context[key] = key.includes('Days') ? 0 : key === 'vehiclePhotoFilter' ? 'off' : 'all';
    }
    assert.equal(h.run('fieldPhotoLoadMode()'), 'overview');
});

test('public and local layer switches adjust counts without server requests', async () => {
    const h = harness(async () => ({ status: 'ok', clusters: [sample()] }));
    await h.run('loadFieldPhotos()');
    assert.equal(h.markers.at(-1).tooltip, 'map.overviewPhotoCount10');
    h.setVehicleVisible(false);
    h.setPending(false);
    h.setCategory('smoke', false);
    h.run('placeFieldPhotos()');
    assert.equal(h.requests.length, 1);
    assert.equal(h.markers.at(-1).tooltip, 'map.overviewPhotoCount2');
    assert.equal(h.removed.length, 1);
    h.setCategory('infrastructure', false);
    h.run('placeFieldPhotos()');
    assert.equal(h.markers.length, 2);
    assert.equal(h.removed.length, 2);
});

test('invalid or oversized aggregate response cannot replace an existing detailed layer', async () => {
    for (const clusters of [Array.from({ length: 257 }, () => sample()), [sample(-2, 0, 0, 0)], [{ ...sample(), total: 100 }]]) {
        const h = harness(async () => ({ status: 'ok', clusters }));
        await h.run('loadFieldPhotos()');
        assert.equal(h.states.at(-1), 'error');
        assert.equal(h.run('fieldPhotoOverviewActive'), false);
        assert.equal(h.markers.length, 0);
    }
});

test('stale overview response never replaces a newer detail request', async () => {
    let resolveOld;
    const held = new Promise(resolve => { resolveOld = resolve; });
    const h = harness(async (url) => url.includes('/clusters?')
        ? held : { status: 'ok', photos: [], next_cursor: null });
    const older = h.run('loadFieldPhotos()');
    const originalSignal = h.requests[0].options.signal;
    h.setZoom(11);
    await h.run('loadFieldPhotos()');
    assert.equal(originalSignal.aborted, true);
    resolveOld({ status: 'ok', clusters: [sample()] });
    await older;
    assert.equal(h.run('fieldPhotoOverviewActive'), false);
    assert.equal(h.markers.length, 0);
    assert.equal(h.requests.length, 2);
});

test('marker follows an unwrapped Leaflet map center after the 180th meridian', async () => {
    const h = harness(async () => ({ status: 'ok', clusters: [{ ...sample(1, 0, 0, 0), lon: -175 }] }));
    h.bounds.west = 183;
    h.bounds.east = 187;
    h.context.map.getCenter = () => ({ lng: 185 });
    await h.run('loadFieldPhotos()');
    assert.equal(h.markers.length, 1);
    assert.equal(h.markers[0].point[1], 185);
    h.markers[0].handlers.click();
    const [southWest, northEast] = h.fits[0].target;
    assert.ok(southWest[1] < 185 && northEast[1] > 185);
});

test('cross-dateline aggregate fits the exact unwrapped geographic cell', async () => {
    const h = harness(async () => ({ status: 'ok', clusters: [{ ...sample(1, 0, 0, 0), lon: -179.5 }] }));
    h.bounds.west = 178;
    h.bounds.east = 182;
    await h.run('loadFieldPhotos()');
    h.markers[0].handlers.click();
    const [sw, ne] = h.fits[0].target;
    assert.ok(sw[1] > 180 && ne[1] > sw[1]);
    assert.ok(sw[1] <= 180.5 && ne[1] >= 180.5);
});
