import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../../web/app/map_sources.js', import.meta.url), 'utf8');
const start = source.indexOf('function swapMapSourceLayer(');
const end = source.indexOf('\nfunction setMapSource(', start);
assert.ok(start >= 0 && end > start, 'map source swap function must exist');

function layer(name) {
    const callbacks = new Map();
    return {
        name,
        on(kind, callback) {
            const entries = callbacks.get(kind) || new Set();
            entries.add(callback);
            callbacks.set(kind, entries);
            return this;
        },
        off(kind, callback) { callbacks.get(kind)?.delete(callback); return this; },
        addTo(map) { map.active.add(this); return this; },
        emit(kind, event = {}) {
            for (const callback of [...(callbacks.get(kind) || [])]) callback(event);
        },
    };
}

function harness() {
    const base = layer('stable');
    const timers = [];
    let refreshes = 0;
    const ctx = {
        mapSourceSwapToken: 0,
        mapSourcePendingLayer: null,
        mapSourceStableIndex: 7,
        currentMapSourceIndex: 7,
        mapSourceLayer: base,
        ORTHO_LAYER_SWAP_FALLBACK_MS: 20,
        map: {
            active: new Set([base]),
            hasLayer(next) { return this.active.has(next); },
            removeLayer(next) { this.active.delete(next); },
        },
        setTimeout(fn) { timers.push(fn); },
        updateMapSourceUi() { refreshes += 1; },
    };
    vm.runInNewContext(source.slice(start, end) + '\nthis.swap = swapMapSourceLayer;', ctx);
    return { ctx, base, timers, get refreshes() { return refreshes; } };
}

test('failed replacement preserves the last functioning map and selected source', () => {
    const { ctx, base, timers } = harness();
    const broken = layer('broken');
    ctx.currentMapSourceIndex = 6;
    ctx.swap(broken);
    assert.equal(ctx.map.hasLayer(base), true);
    broken.emit('tileload', { tile: { classList: { contains: () => true } } });
    broken.emit('load');
    assert.equal(ctx.map.hasLayer(base), true, 'proxy placeholder is not a valid base layer');

    timers.at(-1)();
    assert.equal(ctx.map.hasLayer(broken), false);
    assert.equal(ctx.map.hasLayer(base), true);
    assert.equal(ctx.currentMapSourceIndex, 7);
    assert.equal(ctx.mapSourceLayer, base);
});

test('successful replacement removes prior map only after a real tile finishes', () => {
    const { ctx, base } = harness();
    const working = layer('working');
    ctx.currentMapSourceIndex = 6;
    ctx.swap(working);
    assert.equal(ctx.map.hasLayer(base), true);
    working.emit('tileload', { tile: { classList: { contains: () => false } } });
    working.emit('load');
    assert.equal(ctx.map.hasLayer(working), true);
    assert.equal(ctx.map.hasLayer(base), false);
    assert.equal(ctx.mapSourceStableIndex, 6);
    assert.equal(ctx.mapSourceLayer, working);
});

test('new selection cancels stale pending replacement without dropping stable map', () => {
    const { ctx, base } = harness();
    const stale = layer('stale');
    const latest = layer('latest');
    ctx.currentMapSourceIndex = 6;
    ctx.swap(stale);
    ctx.currentMapSourceIndex = 5;
    ctx.swap(latest);
    assert.equal(ctx.map.hasLayer(stale), false);
    assert.equal(ctx.map.hasLayer(base), true);
    stale.emit('tileload', { tile: { classList: { contains: () => false } } });
    stale.emit('load');
    assert.equal(ctx.map.hasLayer(base), true);
    latest.emit('tileload', { tile: { classList: { contains: () => false } } });
    latest.emit('load');
    assert.equal(ctx.map.hasLayer(base), false);
    assert.equal(ctx.mapSourceLayer, latest);
    assert.equal(ctx.mapSourceStableIndex, 5);
});
