// Wroclaw and Geoportal sources are preview-only base layers; reports fetch
// their own small historical crops by location.
let currentMapSourceIndex = Math.max(0, MAP_SOURCES.findIndex(source => source.key === DEFAULT_MAP_SOURCE_KEY));
let mapSourceLayer = null;
let mapSourceSwapToken = 0;
let mapSourcePendingLayer = null;
let mapSourceStableIndex = currentMapSourceIndex;
let mapLabelLayer = null;
let mapLabelsVisible = true;
try {
    mapLabelsVisible = localStorage.getItem(MAP_STREET_LABELS_VISIBLE_STORAGE_KEY) !== '0';
} catch (_) {
    mapLabelsVisible = true;
}
let mapSourceSliderVisible = true;
try {
    mapSourceSliderVisible = localStorage.getItem(MAP_SOURCE_SLIDER_VISIBLE_STORAGE_KEY) !== 'false';
} catch (_) {
    mapSourceSliderVisible = true;
}
const TILE_FALLBACK_DATA_URL = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#d1d8e0"/></svg>'
)}`;
const RETRYABLE_TILE_CACHE_STATUSES = new Set(['BUSY', 'IN_FLIGHT', 'UPSTREAM_ERROR', 'ENCODE_ERROR']);

function retryTileDelayMs(attempt) {
    return Math.min(30000, 1500 * (2 ** Math.min(attempt, 5)));
}

function isRetryableProxyTileUrl(url) {
    return typeof url === 'string' && (url.startsWith('/tile_proxy/') || url.startsWith('/wms_proxy/'));
}

const retryingTileMixin = {
    createTile(coords, done) {
        if (!window.fetch || !window.URL || !window.Blob) {
            return L.TileLayer.prototype.createTile.call(this, coords, done);
        }

        const tile = document.createElement('img');
        let settled = false;
        let retryTimer = null;
        let currentObjectUrl = '';
        let currentRequestController = null;
        let stopped = false;

        tile.alt = '';
        tile.decoding = 'async';
        tile.setAttribute('role', 'presentation');

        const settle = error => {
            if (settled) return;
            settled = true;
            done(error || null, tile);
        };
        const clearRetryTimer = () => {
            if (!retryTimer) return;
            clearTimeout(retryTimer);
            retryTimer = null;
        };
        const cleanup = () => {
            stopped = true;
            clearRetryTimer();
            currentRequestController?.abort();
            currentRequestController = null;
            if (currentObjectUrl) {
                URL.revokeObjectURL(currentObjectUrl);
                currentObjectUrl = '';
            }
            this.off('tileunload', handleTileUnload);
        };
        const handleTileUnload = event => {
            if (event.tile === tile) cleanup();
        };
        const showFallback = () => {
            tile.classList.add('leaflet-tile--retrying');
            if (currentObjectUrl) {
                URL.revokeObjectURL(currentObjectUrl);
                currentObjectUrl = '';
            }
            tile.src = TILE_FALLBACK_DATA_URL;
            settle();
        };
        const scheduleRetry = attempt => {
            clearRetryTimer();
            retryTimer = setTimeout(() => loadTile(attempt + 1), retryTileDelayMs(attempt));
        };
        const shouldContinueRetrying = attempt => {
            if (stopped || !this._map) return false;
            return attempt === 0 || tile.isConnected;
        };
        const loadBlob = blob => {
            const nextObjectUrl = URL.createObjectURL(blob);
            const previousObjectUrl = currentObjectUrl;
            currentObjectUrl = nextObjectUrl;
            tile.onload = () => {
                if (previousObjectUrl) URL.revokeObjectURL(previousObjectUrl);
                tile.onload = null;
                tile.onerror = null;
                tile.classList.remove('leaflet-tile--retrying');
                settle();
            };
            tile.onerror = () => {
                if (nextObjectUrl === currentObjectUrl) currentObjectUrl = '';
                URL.revokeObjectURL(nextObjectUrl);
                tile.onload = null;
                tile.onerror = null;
                showFallback();
                scheduleRetry(0);
            };
            tile.src = nextObjectUrl;
        };
        const loadTile = async attempt => {
            if (!shouldContinueRetrying(attempt)) return;
            currentRequestController?.abort();
            const requestController = new AbortController();
            currentRequestController = requestController;
            const timeoutId = window.setTimeout(() => requestController.abort(), 10000);
            try {
                const response = await fetch(this.getTileUrl(coords), {
                    cache: 'default',
                    signal: requestController.signal,
                });
                const cacheStatus = response.headers.get('X-WMS-Cache') || '';
                if (!response.ok || RETRYABLE_TILE_CACHE_STATUSES.has(cacheStatus)) {
                    showFallback();
                    scheduleRetry(attempt);
                    return;
                }
                const blob = await response.blob();
                loadBlob(blob);
            } catch (_) {
                if (stopped) return;
                showFallback();
                scheduleRetry(attempt);
            } finally {
                window.clearTimeout(timeoutId);
                if (currentRequestController === requestController) currentRequestController = null;
            }
        };

        this.on('tileunload', handleTileUnload);
        loadTile(0);
        return tile;
    },
};

const RetryingTileLayer = L.TileLayer.extend(retryingTileMixin);
const RetryingWmsLayer = L.TileLayer.WMS.extend(retryingTileMixin);

function retryingTileLayer(url, options) {
    return new RetryingTileLayer(url, options);
}

retryingTileLayer.wms = function wms(url, options) {
    return new RetryingWmsLayer(url, options);
};

function activeMapSource() {
    return MAP_SOURCES[currentMapSourceIndex] || MAP_SOURCES[0];
}

function mapSourceAllowed(source) {
    return !source?.publicLayerKey || publicLayerAllowed(source.publicLayerKey);
}

function visibleMapSourceIndices() {
    return MAP_SOURCES.map((source, index) => ({ source, index }))
        .filter(item => mapSourceAllowed(item.source))
        .map(item => item.index);
}

function fallbackMapSourceIndex(visibleIndices = visibleMapSourceIndices()) {
    const defaultIndex = MAP_SOURCES.findIndex(source => source.key === DEFAULT_MAP_SOURCE_KEY);
    if (visibleIndices.includes(defaultIndex)) return defaultIndex;
    return visibleIndices[0] ?? Math.max(0, defaultIndex);
}

function mapSourceVisiblePosition(index = currentMapSourceIndex, visibleIndices = visibleMapSourceIndices()) {
    const position = visibleIndices.indexOf(index);
    return position >= 0 ? position : Math.max(0, visibleIndices.indexOf(fallbackMapSourceIndex(visibleIndices)));
}

function buildMapSourceLayer(source) {
    if (source.type === 'wroclaw') {
        return retryingTileLayer.wms(`/wms_proxy/OGC_ortofoto_${source.year}/MapServer/WMSServer`, {
            layers: '1',
            format: 'image/png',
            transparent: false,
            version: '1.3.0',
            enhancementSettings: enhancementSettingsRevision,
            maxZoom: MAX_MAP_ZOOM,
            attribution: `Geoportal Wroclawia · ${source.year} · enhanced`,
        });
    }
    if (source.type === 'wms') {
        const factory = isRetryableProxyTileUrl(source.url) ? retryingTileLayer.wms : L.tileLayer.wms;
        return factory(source.url, {
            layers: source.layers,
            styles: source.styles || '',
            format: 'image/png',
            transparent: false,
            version: source.version || '1.3.0',
            maxZoom: MAX_MAP_ZOOM,
            attribution: source.attribution || 'Geoportal.gov.pl / GUGiK',
        });
    }
    if (source.type === 'tile') {
        const factory = isRetryableProxyTileUrl(source.url) ? retryingTileLayer : L.tileLayer;
        return factory(source.url, {
            maxZoom: MAX_MAP_ZOOM,
            maxNativeZoom: source.maxNativeZoom || MAX_MAP_ZOOM,
            enhancementSettings: enhancementSettingsRevision,
            attribution: source.attribution || '',
        });
    }
    throw new Error(`Unsupported map source type: ${source.type}`);
}

function buildMapLabelLayer() {
    return L.tileLayer.wms(STREET_LABELS_WMS_URL, {
        layers: 'A08_Ulice',
        styles: '',
        format: 'image/png',
        transparent: true,
        version: '1.3.0',
        maxZoom: MAX_MAP_ZOOM,
        opacity: 0.6,
        pane: 'overlayPane',
        attribution: 'GUGiK · Państwowy Rejestr Granic – ulice',
    });
}

function updateMapLabelLayer() {
    const supported = activeMapSource().labelsOverlay !== false;
    const toggle = document.getElementById('toggle-street-labels');
    if (toggle) {
        toggle.checked = mapLabelsVisible;
        toggle.disabled = !supported;
        toggle.closest('.layer-toggle')?.classList.toggle('is-disabled', !supported);
    }
    const shouldShow = mapLabelsVisible && supported;
    if (shouldShow) {
        if (!mapLabelLayer) mapLabelLayer = buildMapLabelLayer();
        if (!map.hasLayer(mapLabelLayer)) mapLabelLayer.addTo(map);
        return;
    }
    if (mapLabelLayer && map.hasLayer(mapLabelLayer)) {
        map.removeLayer(mapLabelLayer);
    }
}

function toggleMapLabelLayer(visible) {
    mapLabelsVisible = Boolean(visible);
    try {
        localStorage.setItem(MAP_STREET_LABELS_VISIBLE_STORAGE_KEY, mapLabelsVisible ? '1' : '0');
    } catch (_) {}
    updateMapLabelLayer();
}

function renderMapSourceTicks(visibleIndices = visibleMapSourceIndices()) {
    const ticks = document.getElementById('year-ticks');
    if (!ticks) return;
    ticks.innerHTML = '';
    visibleIndices.forEach(index => {
        const source = MAP_SOURCES[index];
        const tick = document.createElement('button');
        tick.type = 'button';
        tick.className = 'year-tick' + (index === currentMapSourceIndex ? ' active' : '');
        tick.dataset.index = index;
        tick.textContent = source.shortLabel;
        tick.title = source.label;
        tick.addEventListener('click', () => setMapSource(index));
        ticks.appendChild(tick);
    });
}

function isMapSourceSliderVisible() {
    return mapSourceSliderVisible;
}

function applyMapSourceSliderVisibility() {
    const slider = document.getElementById('year-slider');
    if (slider) slider.hidden = !mapSourceSliderVisible;
    const toggle = document.getElementById('map-source-slider-toggle');
    if (toggle) toggle.checked = mapSourceSliderVisible;
}

function setMapSourceSliderVisible(visible) {
    mapSourceSliderVisible = Boolean(visible);
    try {
        localStorage.setItem(MAP_SOURCE_SLIDER_VISIBLE_STORAGE_KEY, mapSourceSliderVisible ? 'true' : 'false');
    } catch (_) {}
    applyMapSourceSliderVisibility();
}

function updateMapSourceUi() {
    const visibleIndices = visibleMapSourceIndices();
    const source = activeMapSource();
    const currentLabel = document.getElementById('year-current');
    if (currentLabel) {
        currentLabel.textContent = source.shortLabel;
        currentLabel.title = source.label;
    }
    const menuBadge = document.getElementById('map-source-current-badge');
    if (menuBadge) {
        menuBadge.textContent = source.shortLabel;
        menuBadge.title = source.label;
    }
    const range = document.getElementById('year-range');
    if (range) {
        range.min = 0;
        range.max = Math.max(0, visibleIndices.length - 1);
        range.value = mapSourceVisiblePosition(currentMapSourceIndex, visibleIndices);
        range.setAttribute('aria-valuetext', source.label);
    }
    renderMapSourceTicks(visibleIndices);
    applyMapSourceSliderVisibility();
    document.getElementById('year-prev')?.toggleAttribute('disabled', mapSourceVisiblePosition(currentMapSourceIndex, visibleIndices) <= 0);
    document.getElementById('year-next')?.toggleAttribute(
        'disabled',
        mapSourceVisiblePosition(currentMapSourceIndex, visibleIndices) >= visibleIndices.length - 1
    );
    updateMapLabelLayer();
}

function swapMapSourceLayer(nextLayer) {
    const swapToken = ++mapSourceSwapToken;
    const previousLayer = mapSourceLayer;
    if (mapSourcePendingLayer && map.hasLayer(mapSourcePendingLayer)) {
        map.removeLayer(mapSourcePendingLayer);
    }
    mapSourcePendingLayer = nextLayer;
    let successfulTile = false;
    let finished = false;
    const onTileLoad = event => {
        // A proxy placeholder counts as a Leaflet tile, but not as a usable map.
        if (!event.tile?.classList?.contains('leaflet-tile--retrying')) {
            successfulTile = true;
        }
    };
    const cleanup = () => {
        nextLayer.off('tileload', onTileLoad);
        nextLayer.off('load', onLayerLoad);
    };
    const onLayerLoad = () => {
        if (finished || swapToken !== mapSourceSwapToken || !successfulTile) return;
        finished = true;
        cleanup();
        mapSourcePendingLayer = null;
        mapSourceLayer = nextLayer;
        mapSourceStableIndex = currentMapSourceIndex;
        if (previousLayer && map.hasLayer(previousLayer)) map.removeLayer(previousLayer);
    };
    nextLayer.on('tileload', onTileLoad);
    nextLayer.on('load', onLayerLoad);
    nextLayer.addTo(map);
    // On failure keep the last working map rather than removing it unconditionally.
    setTimeout(() => {
        if (finished || swapToken !== mapSourceSwapToken) return;
        finished = true;
        cleanup();
        if (map.hasLayer(nextLayer)) map.removeLayer(nextLayer);
        mapSourcePendingLayer = null;
        currentMapSourceIndex = mapSourceStableIndex;
        updateMapSourceUi();
    }, Math.max(12000, ORTHO_LAYER_SWAP_FALLBACK_MS));
}

function setMapSource(index) {
    const nextIndex = Math.max(0, Math.min(MAP_SOURCES.length - 1, parseInt(index, 10)));
    if (!Number.isFinite(nextIndex) || nextIndex === currentMapSourceIndex || !mapSourceAllowed(MAP_SOURCES[nextIndex])) return;
    currentMapSourceIndex = nextIndex;
    const nextLayer = buildMapSourceLayer(activeMapSource());
    swapMapSourceLayer(nextLayer);
    updateMapSourceUi();
}

function setMapSourceByVisiblePosition(position) {
    const visibleIndices = visibleMapSourceIndices();
    if (!visibleIndices.length) return;
    const nextPosition = Math.max(0, Math.min(visibleIndices.length - 1, parseInt(position, 10)));
    setMapSource(visibleIndices[nextPosition]);
}

function moveMapSource(delta) {
    const visibleIndices = visibleMapSourceIndices();
    const nextPosition = mapSourceVisiblePosition(currentMapSourceIndex, visibleIndices) + delta;
    setMapSourceByVisiblePosition(nextPosition);
}

function updateMapSourceAvailability() {
    if (mapSourceAllowed(activeMapSource())) {
        updateMapSourceUi();
        return;
    }
    currentMapSourceIndex = fallbackMapSourceIndex();
    const nextLayer = buildMapSourceLayer(activeMapSource());
    swapMapSourceLayer(nextLayer);
    updateMapSourceUi();
}

function refreshOrthoLayer() {
    const nextLayer = buildMapSourceLayer(activeMapSource());
    swapMapSourceLayer(nextLayer);
}

mapSourceLayer = buildMapSourceLayer(activeMapSource()).addTo(map);
