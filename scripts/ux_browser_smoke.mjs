#!/usr/bin/env node
/* Browser-only map shell regression, zero production HTTP writes or data access.
   Requires a local Chrome/Chromium executable; run outside the unit-test suite. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtempSync, readFileSync, rmSync, statSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../web');
const chrome = process.env.CHROME_BIN ||
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
assert.ok(existsSync(chrome), 'Set CHROME_BIN to a Chrome or Chromium executable');

const probe = `
(() => {
    try {
        const mobile = matchMedia('(max-width: 720px)').matches;
        const drawer = document.getElementById('app-menu-drawer');
        const tabs = Array.from(document.querySelectorAll('[data-ux-tab]'));
        const panels = Array.from(document.querySelectorAll('[data-ux-panel]'));
        if (drawer.hidden) document.getElementById('app-menu-toggle').click();
        const open = !drawer.hidden;
        const before = panels.map(panel => panel.hidden);
        document.getElementById('ux-tab-layers').click();
        const after = panels.map(panel => panel.hidden);
        document.getElementById('ux-sheet-handle').click();
        const expanded = document.body.classList.contains('ux-sheet-expanded');
        const rect = drawer.getBoundingClientRect();
        const source = document.getElementById('map-source-slider-toggle');
        const report = document.getElementById('map-add-field-photo');
        window.__uxProbe = {
            mobile, open, before, after, expanded,
            viewport: innerWidth, drawerWidth: Math.round(rect.width),
            drawerBottom: Math.round(innerHeight - rect.bottom),
            mapLeft: Math.round(document.getElementById('map').getBoundingClientRect().left),
            scrimHidden: document.getElementById('app-menu-scrim').hidden,
            tabSelected: tabs.map(tab => tab.getAttribute('aria-selected')),
            controlsIntact: Boolean(source && report && document.getElementById('vehicle-insurance-select')),
            browserErrors: (window.__uxSmokeErrors || []).slice(0, 6)
        };
    } catch (caught) {
        window.__uxProbe = { failure: String(caught) };
    }
    const output = document.createElement('pre');
    output.id = 'ux-smoke-result';
    output.textContent = JSON.stringify(window.__uxProbe);
    document.body.appendChild(output);
})();
`;

function page() {
    let html = readFileSync(path.join(root, 'index.html'), 'utf8');
    html = html.replace(/<!-- include:([A-Za-z0-9_./-]+) -->/g, (match, name) => {
        const file = path.resolve(root, name);
        assert.ok(file.startsWith(root + path.sep), 'unsafe include');
        return readFileSync(file, 'utf8');
    });
    const firstVisitDisabled = `<script>
        localStorage.setItem('ilestoi-intro-v1-seen', '1');
        localStorage.setItem('ilestoi-onboarding-v1-complete', '1');
        window.WRECKSCANNER_APP_SETTINGS = { map_view: { center: [51.107883, 17.038538], zoom: 13 } };
        window.__uxSmokeErrors = [];
        window.addEventListener('error', e => window.__uxSmokeErrors.push(String(e.message).slice(0, 160)));
        window.addEventListener('unhandledrejection', e => window.__uxSmokeErrors.push(String(e.reason).slice(0, 160)));
    </script>`;
    html = html.replace('<!-- app-settings-bootstrap -->', firstVisitDisabled);
    html = html.replace('<!-- page-head-metadata -->', '<title>IleStoi UX browser smoke</title>');
    html = html.replace('<!-- page-structured-data -->', '');
    html = html.replace('</body>', `<script>setTimeout(() => { ${probe} }, 900)</script></body>`);
    return html;
}

const html = page();
const server = createServer((req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    if (pathname === '/' || pathname === '/index.html') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(html);
        return;
    }
    if (pathname.startsWith('/api/')) {
        const payload = pathname === '/api/admin/status'
            ? { authenticated: false }
            : pathname === '/api/field-photos'
                ? { items: [], next_cursor: null }
                : pathname === '/api/field-photos/clusters'
                    ? { clusters: [] }
                    : { layers: {}, features: {}, map_view: { center: [51.107883, 17.038538], zoom: 13 } };
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify(payload));
        return;
    }
    const file = path.resolve(root, pathname.replace(/^\/+/, ''));
    if (!file.startsWith(root + path.sep) || !existsSync(file) || !statSync(file).isFile()) {
        res.writeHead(404);
        res.end();
        return;
    }
    const ext = path.extname(file);
    const contentType = { '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
        '.png': 'image/png', '.json': 'application/json', '.webmanifest': 'application/manifest+json' }[ext]
        || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(readFileSync(file));
});

function launch(url, width, height, dir) {
    return new Promise((resolve, reject) => {
        const args = [
            '--headless=new', '--no-first-run', '--no-default-browser-check',
            '--disable-extensions', '--disable-gpu', '--hide-scrollbars',
            '--disable-background-networking', '--disable-features=Translate',
            '--user-data-dir=' + dir,
            '--window-size=' + width + ',' + height,
            '--virtual-time-budget=6500', '--dump-dom', url,
        ];
        const child = spawn(chrome, args, { stdio: ['ignore', 'pipe', 'pipe'] });
        let stdout = '';
        let stderr = '';
        const timeout = setTimeout(() => child.kill('SIGKILL'), 35000);
        child.stdout.on('data', data => { stdout += String(data); });
        child.stderr.on('data', data => { stderr = (stderr + String(data)).slice(-4000); });
        child.on('error', error => { clearTimeout(timeout); reject(error); });
        child.on('close', code => {
            clearTimeout(timeout);
            const match = stdout.match(/<pre id="ux-smoke-result">([^<]*)<\/pre>/);
            if (!match) return reject(new Error('Browser probe missing, exit ' + code +
                ': ' + stderr.slice(-1200)));
            try { resolve(JSON.parse(match[1].replaceAll('&amp;', '&'))); }
            catch (error) { reject(error); }
        });
    });
}

const dir = mkdtempSync(path.join(tmpdir(), 'ilestoi-ux-chrome-'));
try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const url = `http://127.0.0.1:${server.address().port}/?ux_smoke=1`;
    for (const [name, width, height] of [['mobile', 390, 844], ['desktop', 1400, 900]]) {
        const result = await launch(url, width, height, path.join(dir, name));
        assert.equal(result.failure, undefined, JSON.stringify(result));
        assert.equal(result.open, true);
        assert.equal(result.controlsIntact, true);
        assert.deepEqual(result.tabSelected, ['false', 'true', 'false']);
        if (name === 'mobile') {
            assert.equal(result.mobile, true);
            assert.deepEqual(result.before, [false, true, true]);
            assert.deepEqual(result.after, [true, false, true]);
            assert.equal(result.expanded, true);
            assert.equal(result.scrimHidden, false);
            assert.ok(result.drawerWidth >= result.viewport - 2, JSON.stringify(result));
            assert.ok(Math.abs(result.drawerBottom) <= 2, JSON.stringify(result));
        } else {
            assert.equal(result.mobile, false);
            assert.deepEqual(result.after, [false, false, false]);
            assert.ok(result.drawerWidth >= 350, JSON.stringify(result));
            assert.ok(result.mapLeft >= 350, JSON.stringify(result));
            assert.equal(result.scrimHidden, true);
        }
        console.log('PASS', name, JSON.stringify(result));
    }
} finally {
    server.close();
    rmSync(dir, { recursive: true, force: true });
}
