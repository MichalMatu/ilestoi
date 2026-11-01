import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const script = readFileSync(new URL('../../web/app/intro_overlay.js', import.meta.url), 'utf8');
const index = readFileSync(new URL('../../web/index.html', import.meta.url), 'utf8');
const intro = readFileSync(new URL('../../web/intro.html', import.meta.url), 'utf8');
test('four scenes use one adaptive layout, without duplicate HTML pages', () => {
    assert.equal((intro.match(/class="photo(?: active)?"/g) || []).length, 4);
    assert.match(intro, /@media\(max-width:850px\)/);
    assert.match(intro, /DURATION=13600/);
    assert.match(index, /id="ilestoi-intro-overlay"/);
});
function setup({ stored = null, path = '/', search = '', hash = '' } = {}) {
    let frame;
    const listeners = {};
    const recorded = {};
    const overlay = { hidden: true, append(x) { frame = x; } };
    const context = {
        localStorage: { getItem: () => stored, setItem: (k, v) => { recorded[k] = v; } },
        location: { pathname: path, search, hash, origin: 'https://ilestoi.pl' },
        document: {
            activeElement: { isConnected: false },
            createElement: () => ({ contentWindow: {}, setAttribute() {}, addEventListener() {}, remove() { frame = null; } }),
            getElementById: (id) => id === 'ilestoi-intro-overlay' ? overlay : null,
        },
        window: { addEventListener(k, fn) { listeners[k] = fn; } },
        CURRENT_LANG: 'pl',
    };
    vm.createContext(context);
    vm.runInContext(script, context);
    return { overlay, listeners, recorded, get frame() { return frame; }, context };
}
test('only the initial plain homepage shows intro', () => {
    assert.equal(setup().overlay.hidden, false);
    assert.equal(setup({ stored: '1' }).overlay.hidden, true);
    assert.equal(setup({ hash: '#photo=1' }).overlay.hidden, true);
    assert.equal(setup({ search: '?photo=1' }).overlay.hidden, true);
});
test('a same-origin message from the exact iframe is required', () => {
    const x = setup(); const frameWindow = x.frame.contentWindow;
    x.listeners.message({ origin: 'https://example.invalid', source: frameWindow, data: { type: 'ilestoi:intro:dismiss' } });
    assert.equal(x.overlay.hidden, false);
    x.listeners.message({ origin: 'https://ilestoi.pl', source: {}, data: { type: 'ilestoi:intro:dismiss' } });
    assert.equal(x.overlay.hidden, false);
    x.listeners.message({ origin: 'https://ilestoi.pl', source: frameWindow, data: { type: 'ilestoi:intro:dismiss' } });
    assert.equal(x.overlay.hidden, true);
    assert.equal(x.recorded['ilestoi-intro-v1-seen'], '1');
});
test('once shown the automatic guided tour is suppressed', () => {
    const x = setup({ stored: '1' });
    assert.equal(vm.runInContext('ileStoiIntroSuppressAutomaticTour()', x.context), true);
});
