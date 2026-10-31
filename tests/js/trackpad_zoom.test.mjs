import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../../web/app/trackpad_zoom.js', import.meta.url), 'utf8');
const bootstrap = fs.readFileSync(new URL('../../web/app/bootstrap.js', import.meta.url), 'utf8');
const startup = fs.readFileSync(new URL('../../web/app/startup.js', import.meta.url), 'utf8');
const index = fs.readFileSync(new URL('../../web/index.html', import.meta.url), 'utf8');

function point(x, y) {
    return {
        x, y,
        subtract(other) { return point(this.x - other.x, this.y - other.y); },
        add(other) { return point(this.x + other.x, this.y + other.y); },
        multiplyBy(factor) { return point(this.x * factor, this.y * factor); },
        divideBy(divisor) { return point(this.x / divisor, this.y / divisor); },
    };
}

function harness(initialZoom = 12) {
    let eventListener = null;
    const frames = new Map();
    const timers = new Map();
    let sequence = 0;
    const counters = { starts: 0, moves: 0, ends: 0, stops: 0, handlers: 0 };
    let wheelEnabled = true;
    const map = {
        options: { zoomSnap: 1 },
        zoom: initialZoom,
        scrollWheelZoom: { enabled: () => wheelEnabled },
        getContainer() {
            return {
                addEventListener(type, callback, options) {
                    assert.equal(type, 'wheel');
                    assert.equal(options.capture, true);
                    assert.equal(options.passive, false);
                    eventListener = callback;
                    counters.handlers += 1;
                },
                removeEventListener(type, callback, options) {
                    assert.equal(type, 'wheel');
                    assert.equal(options.capture, true);
                    assert.equal(eventListener, callback);
                    eventListener = null;
                    counters.handlers -= 1;
                },
            };
        },
        getZoom() { return this.zoom; },
        getMinZoom() { return 5; },
        getMaxZoom() { return 18; },
        getZoomScale(next, current) { return 2 ** (next - current); },
        getSize() { return point(800, 600); },
        mouseEventToContainerPoint(event) { return point(event.clientX, event.clientY); },
        containerPointToLatLng(p) { return { lat: p.y, lng: p.x }; },
        stop() { counters.stops += 1; },
        _moveStart() { counters.starts += 1; },
        _move(_center, zoom, options) {
            assert.equal(options.pinch, true);
            assert.equal(options.round, false);
            this.zoom = zoom;
            counters.moves += 1;
        },
        _moveEnd() { counters.ends += 1; },
    };
    const mockWindow = {
        requestAnimationFrame(cb) { const id = ++sequence; frames.set(id, cb); return id; },
        cancelAnimationFrame(id) { frames.delete(id); },
        setTimeout(cb) { const id = ++sequence; timers.set(id, cb); return id; },
        clearTimeout(id) { timers.delete(id); },
    };
    const context = vm.createContext({ window: mockWindow, Number, Math });
    vm.runInContext(source, context);
    const uninstall = vm.runInContext('installSmoothTrackpadZoom', context)(map);
    function wheel(deltaY, ctrlKey = false, deltaMode = 0) {
        let prevented = false;
        let stopped = false;
        eventListener?.({
            deltaMode, deltaY, ctrlKey, clientX: 180, clientY: 140,
            preventDefault() { prevented = true; },
            stopImmediatePropagation() { stopped = true; },
        });
        return { prevented, stopped };
    }
    function flushFrames(max = 120) {
        let iterations = 0;
        while (frames.size) {
            assert.ok(iterations++ < max, 'rAF zoom must converge');
            const [id, cb] = frames.entries().next().value;
            frames.delete(id);
            cb();
        }
    }
    function settle() {
        flushFrames();
        for (const [id, cb] of [...timers]) {
            timers.delete(id);
            cb();
        }
        flushFrames();
        assert.equal(frames.size, 0);
        assert.equal(timers.size, 0);
    }
    function settleWithoutFrames() {
        for (const [id, cb] of [...timers]) {
            timers.delete(id);
            cb();
        }
        assert.equal(frames.size, 0, 'an idle timeout must cancel stalled frames');
        assert.equal(timers.size, 0);
    }
    return { map, counters, wheel, flushFrames, settle, settleWithoutFrames, uninstall, setWheelEnabled(enabled) { wheelEnabled = enabled; } };
}

test('Mac pinch uses continuous fractional zoom and one final zoomend', () => {
    const h = harness();
    for (let i = 0; i < 12; i++) {
        assert.deepEqual(h.wheel(-12, true), { prevented: true, stopped: true });
        h.flushFrames();
    }
    assert.ok(h.map.getZoom() > 12.5);
    assert.ok(h.map.getZoom() < 13);
    assert.equal(h.counters.ends, 0, 'must not re-layout markers during pinch');
    assert.ok(h.counters.moves >= 12);
    assert.equal(h.map.options.zoomSnap, 0);
    h.settle();
    assert.equal(h.counters.starts, 1);
    assert.equal(h.counters.stops, 0, 'an idle map must not fire an extra moveend via stop()');
    assert.equal(h.counters.ends, 1);
    assert.equal(h.map.options.zoomSnap, 1);
});

test('fine scroll zooms out then back in without stalls or 0.25 steps', () => {
    const h = harness(13);
    for (let i = 0; i < 16; i++) { h.wheel(12); h.flushFrames(); }
    h.settle();
    assert.ok(h.map.getZoom() < 12.1);
    const afterOut = h.map.getZoom();
    for (let i = 0; i < 16; i++) { h.wheel(-12); h.flushFrames(); }
    h.settle();
    assert.ok(h.map.getZoom() > afterOut + 0.8);
    assert.ok(Math.abs(h.map.getZoom() - 13) < 0.001);
    assert.equal(h.counters.ends, 2);
});

test('coarse mouse wheel and line-mode events stay with native Leaflet', () => {
    const h = harness();
    assert.deepEqual(h.wheel(-100), { prevented: false, stopped: false });
    assert.deepEqual(h.wheel(3, false, 1), { prevented: false, stopped: false });
    assert.equal(h.counters.starts, 0);
    assert.equal(h.counters.ends, 0);
    assert.equal(h.map.getZoom(), 12);
    assert.equal(h.map.options.zoomSnap, 1);
});

test('large deltas clamp and bounds stop zoom without getting stuck', () => {
    const h = harness(17.95);
    h.wheel(-1000, true);
    h.settle();
    assert.equal(h.map.getZoom(), 18);
    h.wheel(12, true);
    h.settle();
    assert.ok(h.map.getZoom() < 18);
    assert.equal(h.map.options.zoomSnap, 1);
    assert.equal(h.counters.ends, 2);
});

test('disabling Leaflet wheel zoom terminates the gesture and restores snap', () => {
    const h = harness();
    h.wheel(-12, true);
    h.flushFrames();
    h.setWheelEnabled(false);
    h.wheel(-12, true);
    h.settle();
    assert.equal(h.map.options.zoomSnap, 1);
    assert.equal(h.counters.ends, 1);
});

test('unmount cleans up pending frames, listener and original zoom snap', () => {
    const h = harness();
    h.wheel(-12, true);
    h.flushFrames();
    h.uninstall();
    h.settle();
    assert.equal(h.map.options.zoomSnap, 1);
    assert.equal(h.counters.ends, 1);
    assert.equal(h.counters.handlers, 0);
});

test('only one controller is mounted and viewport redraw happens on moveend', () => {
    assert.ok(bootstrap.includes('const map = L.map('));
    assert.ok(index.indexOf('/app/trackpad_zoom.js') > index.indexOf('/app/bootstrap.js'));
    assert.ok(index.indexOf('/app/trackpad_zoom.js') < index.indexOf('/app/startup.js'));
    assert.match(startup, /^installSmoothTrackpadZoom\(map\);/);
    assert.match(startup, /map\.on\('moveend', scheduleFieldPhotoViewportLoad\)/);
    assert.doesNotMatch(source, /setZoomAround\(/);
    assert.doesNotMatch(source, /setZoom\(/);
});

test('idle timeout commits target and emits zoomend even if rAF never fires', () => {
    const h = harness();
    h.wheel(-36, true);
    h.settleWithoutFrames();
    assert.ok(Math.abs(h.map.getZoom() - 12.18) < 0.0001);
    assert.equal(h.counters.starts, 1);
    assert.equal(h.counters.ends, 1);
    assert.equal(h.map.options.zoomSnap, 1);
});

test('interrupts an active prior Leaflet zoom animation before a new trackpad gesture', () => {
    const h = harness();
    h.map._animatingZoom = true;
    h.wheel(-12, true);
    h.flushFrames();
    h.settle();
    assert.equal(h.counters.stops, 1);
    assert.equal(h.counters.ends, 1);
});
