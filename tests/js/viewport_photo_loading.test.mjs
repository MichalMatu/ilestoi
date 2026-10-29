import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync('web/app/field_photos.js', 'utf8');

function harness(respond) {
    const requests = [];
    const updates = [];
    const states = [];
    const timers = new Map();
    let nextTimer = 0;
    const bounds = { west: 16.9, south: 51.0, east: 17.1, north: 51.2 };
    const context = vm.createContext({
        URLSearchParams,
        AbortController,
        FIELD_PHOTOS_URL: '/api/field-photos',
        window: {
            setTimeout(fn) { const id = ++nextTimer; timers.set(id, fn); return id; },
            clearTimeout(id) { timers.delete(id); },
        },
        map: {
            getBounds() {
                return {
                    getWest: () => bounds.west,
                    getSouth: () => bounds.south,
                    getEast: () => bounds.east,
                    getNorth: () => bounds.north,
                };
            },
        },
        apiJson(url, options) {
            requests.push({ url, options });
            return respond(url, options, requests.length);
        },
        t(key) { return key; },
    });
    vm.runInContext(source, context, { filename: 'web/app/field_photos.js' });
    context.setFieldPhotoLoadState = state => states.push(state);
    context.placeFieldPhotos = photos => updates.push({ layer: 'photos', ids: photos.map(item => item.id) });
    context.placeVehicleMarkers = () => updates.push({ layer: 'vehicles' });
    context.updateLayerCounters = () => updates.push({ layer: 'counts' });
    const run = expression => vm.runInContext(expression, context);
    return { bounds, requests, updates, states, timers, run };
}

function photo(id) {
    return { id: String(id), lat: 51.1, lon: 17, public_review_status: 'approved', issue_type: 'vehicle' };
}

test('viewport query is padded, clamped and normalized for the backend contract', () => {
    const h = harness(async () => ({ status: 'ok', photos: [], next_cursor: null }));
    const q = h.run('fieldPhotoViewportQuery()');
    assert.equal(q.bbox, '16.87500000,50.97500000,17.12500000,51.22500000');
    h.bounds.west = 170;
    h.bounds.east = 190;
    assert.equal(h.run('fieldPhotoViewportQuery().bbox').split(',')[0], '167.50000000');
    assert.equal(h.run('fieldPhotoViewportQuery().bbox').split(',')[2], '-167.50000000');
    h.bounds.west = -250;
    h.bounds.east = 250;
    assert.equal(h.run('fieldPhotoViewportQuery().bbox').split(',')[0], '-180.00000000');
    assert.equal(h.run('fieldPhotoViewportQuery().bbox').split(',')[2], '180.00000000');
    h.bounds.south = -95;
    h.bounds.north = 95;
    assert.equal(h.run('fieldPhotoViewportQuery().bbox').split(',')[1], '-90.00000000');
    assert.equal(h.run('fieldPhotoViewportQuery().bbox').split(',')[3], '90.00000000');
});

test('client commits once after all pages, with no unbounded listing', async () => {
    const h = harness(async (url, _, n) => n === 1
        ? { status: 'ok', photos: [photo('a')], next_cursor: 'opaque-token' }
        : { status: 'ok', photos: [photo('b')], next_cursor: null });
    await h.run('loadFieldPhotos()');
    assert.equal(h.requests.length, 2);
    const first = new URL(h.requests[0].url, 'https://example.test');
    const second = new URL(h.requests[1].url, 'https://example.test');
    assert.equal(first.searchParams.get('limit'), '500');
    assert.ok(first.searchParams.has('bbox'));
    assert.equal(first.searchParams.has('cursor'), false);
    assert.equal(second.searchParams.get('cursor'), 'opaque-token');
    assert.equal(second.searchParams.get('bbox'), first.searchParams.get('bbox'));
    assert.deepEqual(JSON.parse(JSON.stringify(h.updates)), [
        { layer: 'photos', ids: ['a', 'b'] }, { layer: 'vehicles' }, { layer: 'counts' },
    ]);
    assert.deepEqual(h.states, ['loading', 'ready']);
    assert.deepEqual(Array.from(h.run('fieldPhotoLayerData.map(photo => photo.id)')), ['a', 'b']);
});

test('stale responses cannot replace more recent view and old request is aborted', async () => {
    let oldResolve;
    const old = new Promise(resolve => { oldResolve = resolve; });
    const h = harness(async (url, _, n) => n === 1
        ? old
        : { status: 'ok', photos: [photo('new')], next_cursor: null });
    const one = h.run('loadFieldPhotos()');
    const firstSignal = h.requests[0].options.signal;
    h.bounds.west = 20;
    h.bounds.east = 21;
    const two = h.run('loadFieldPhotos()');
    assert.equal(firstSignal.aborted, true);
    await two;
    oldResolve({ status: 'ok', photos: [photo('stale')], next_cursor: null });
    await one;
    assert.deepEqual(Array.from(h.run('fieldPhotoLayerData.map(photo => photo.id)')), ['new']);
    assert.equal(h.updates.filter(v => v.layer === 'photos').length, 1);
});

test('invalid or repeating cursors reject partial pages and leave rendered data untouched', async () => {
    const h = harness(async (_url, _options, n) => n === 1
        ? { status: 'ok', photos: [photo('first')], next_cursor: 'repeat' }
        : { status: 'ok', photos: [photo('second')], next_cursor: 'repeat' });
    await h.run('loadFieldPhotos()');
    assert.equal(h.states.at(-1), 'error');
    assert.deepEqual(Array.from(h.run('fieldPhotoLayerData')), []);
    assert.equal(h.updates.length, 0);
});

test('malformed and overfull API pages never publish partial results', async () => {
    const failures = [
        { status: 'error', photos: [], next_cursor: null },
        { status: 'ok', photos: null, next_cursor: null },
        { status: 'ok', photos: Array.from({ length: 501 }, (_, n) => photo(n)), next_cursor: null },
        { status: 'ok', photos: [], next_cursor: '' },
    ];
    for (const response of failures) {
        const h = harness(async () => response);
        await h.run('loadFieldPhotos()');
        assert.equal(h.states.at(-1), 'error');
        assert.deepEqual(h.updates, []);
    }
});

test('panning is debounced and does not reload an unchanged successful viewport', async () => {
    const h = harness(async () => ({ status: 'ok', photos: [photo('a')], next_cursor: null }));
    await h.run('loadFieldPhotos()');
    h.run('scheduleFieldPhotoViewportLoad()');
    assert.equal(h.timers.size, 0);
    h.bounds.east = 17.2;
    h.run('scheduleFieldPhotoViewportLoad()');
    assert.equal(h.timers.size, 1);
    h.bounds.east = 17.3;
    h.run('scheduleFieldPhotoViewportLoad()');
    assert.equal(h.timers.size, 1);
    const callback = [...h.timers.values()][0];
    callback();
    await Promise.resolve();
    await Promise.resolve();
    assert.equal(h.requests.length, 2);
});

test('excessively large viewport errors rather than silently truncating results', async () => {
    let page = 0;
    const h = harness(async () => ({
        status: 'ok', photos: [], next_cursor: `next-${++page}`,
    }));
    await h.run('loadFieldPhotos()');
    assert.equal(page, 40);
    assert.equal(h.states.at(-1), 'error');
    assert.equal(h.updates.length, 0);
});

test('startup attaches viewport handler only after admin bootstrap', async () => {
    const startup = readFileSync('web/app/startup.js', 'utf8');
    let resolveAdmin;
    const boot = new Promise(resolve => { resolveAdmin = resolve; });
    const registered = [];
    const context = vm.createContext({
        document: { addEventListener() {} },
        window: { setTimeout() {} },
        refreshAdminStatus: () => boot,
        map: { on: (...args) => registered.push(args) },
        scheduleFieldPhotoViewportLoad() {},
        loadFieldPhotos: () => Promise.resolve(),
        maybeStartOnboardingTour() {},
        updateLayerCounters() {},
    });
    vm.runInContext(startup, context);
    assert.equal(registered.length, 0);
    resolveAdmin();
    await boot;
    await Promise.resolve();
    assert.deepEqual(registered.map(args => args[0]), ['moveend']);
});
