let fieldPhotoMarkers = [];
let fieldPhotoLayerData = [];
let fieldPhotoLoadRevision = 0;
let fieldPhotoLoadAbortController = null;
let fieldPhotoViewportDebounceTimer = null;
let fieldPhotoLoadedViewportKey = '';
let fieldPhotoRequestedViewportKey = '';
let fieldPhotoLoadedViewportCoverage = null;
let fieldPhotoPopupOpen = false;

const FIELD_PHOTO_VIEWPORT_PAGE_SIZE = 500;
const FIELD_PHOTO_VIEWPORT_MAX_PAGES = 40;
const FIELD_PHOTO_VIEWPORT_DEBOUNCE_MS = 250;
const FIELD_PHOTO_VIEWPORT_PADDING_RATIO = 0.125;

/**
 * Leaflet can return unwrapped longitudes (e.g. 170..190). Convert them into
 * the backend's west,south,east,north contract, preserving dateline crossings.
 */
function fieldPhotoLongitude(lon) {
    const normalized = ((lon + 180) % 360 + 360) % 360 - 180;
    return normalized === -180 && lon > 0 ? 180 : normalized;
}

function fieldPhotoViewportQuery() {
    const bounds = map.getBounds();
    const west = Number(bounds.getWest());
    const south = Number(bounds.getSouth());
    const east = Number(bounds.getEast());
    const north = Number(bounds.getNorth());
    if (![west, south, east, north].every(Number.isFinite) || south > north || east < west) {
        throw new Error('Nieprawidłowy obszar mapy.');
    }
    const latitudePadding = (north - south) * FIELD_PHOTO_VIEWPORT_PADDING_RATIO;
    const paddedSouth = Math.max(-90, south - latitudePadding);
    const paddedNorth = Math.min(90, north + latitudePadding);
    const longitudePadding = (east - west) * FIELD_PHOTO_VIEWPORT_PADDING_RATIO;
    const width = east - west + 2 * longitudePadding;
    const paddedWest = width >= 360 ? -180 : fieldPhotoLongitude(west - longitudePadding);
    const paddedEast = width >= 360 ? 180 : fieldPhotoLongitude(east + longitudePadding);
    const bbox = [paddedWest, paddedSouth, paddedEast, paddedNorth].map(value => value.toFixed(8)).join(',');
    return {
        bbox,
        key: bbox,
        visible: { west, south, east, north },
        coverage: {
            west: west - longitudePadding,
            south: paddedSouth,
            east: east + longitudePadding,
            north: paddedNorth,
        },
    };
}

function fieldPhotoViewportInsideLoadedCoverage(viewport, mode) {
    const coverage = fieldPhotoLoadedViewportCoverage;
    if (!coverage || coverage.mode !== mode) return false;
    const { west, south, east, north } = viewport.visible;
    if (south < coverage.south || north > coverage.north) return false;
    if (coverage.east - coverage.west >= 360) return true;
    // Leaflet can report the same viewport shifted by a full world wrap.
    const longitudeShift = 360 * Math.round(
        (coverage.west + coverage.east - west - east) / 720
    );
    return west + longitudeShift >= coverage.west && east + longitudeShift <= coverage.east;
}

function scheduleFieldPhotoViewportLoad() {
    window.clearTimeout(fieldPhotoViewportDebounceTimer);
    fieldPhotoViewportDebounceTimer = null;
    // A Leaflet popup auto-pans the map. Replacing its marker closes it.
    if (fieldPhotoPopupOpen) return;
    const viewport = fieldPhotoViewportQuery();
    const mode = fieldPhotoLoadMode();
    const key = `${mode}:${viewport.key}`;
    if (fieldPhotoViewportInsideLoadedCoverage(viewport, mode)
        || key === fieldPhotoLoadedViewportKey || key === fieldPhotoRequestedViewportKey) return;
    fieldPhotoViewportDebounceTimer = window.setTimeout(() => {
        fieldPhotoViewportDebounceTimer = null;
        if (!fieldPhotoPopupOpen) loadFieldPhotos();
    }, FIELD_PHOTO_VIEWPORT_DEBOUNCE_MS);
}

async function fetchFieldPhotoViewportPages(viewport, signal) {
    const photos = [];
    const seenCursors = new Set();
    let cursor = null;
    for (let page = 0; page < FIELD_PHOTO_VIEWPORT_MAX_PAGES; page++) {
        const query = new URLSearchParams({
            bbox: viewport.bbox,
            limit: String(FIELD_PHOTO_VIEWPORT_PAGE_SIZE),
        });
        if (cursor !== null) query.set('cursor', cursor);
        const data = await apiJson(`${FIELD_PHOTOS_URL}?${query}`, {
            cache: 'no-store',
            signal,
        });
        if (data.status !== 'ok' || !Array.isArray(data.photos)
            || data.photos.length > FIELD_PHOTO_VIEWPORT_PAGE_SIZE) {
            throw new Error(fieldPhotoLoadText('fieldPhoto.loadError', 'Nie udało się odświeżyć zgłoszeń.'));
        }
        photos.push(...data.photos);
        if (data.next_cursor === null) return photos;
        if (typeof data.next_cursor !== 'string' || !data.next_cursor
            || seenCursors.has(data.next_cursor)) {
            throw new Error('Nieprawidłowa paginacja zgłoszeń.');
        }
        seenCursors.add(data.next_cursor);
        cursor = data.next_cursor;
    }
    throw new Error(fieldPhotoLoadText('fieldPhoto.viewportLimit', 'Przybliż mapę, aby wyświetlić zgłoszenia.'));
}

function fieldPhotoLoadText(key, fallback) {
    if (typeof t !== 'function') return fallback;
    const translated = t(key);
    return translated && translated !== key ? translated : fallback;
}

function fieldPhotoLoadIndicator() {
    let indicator = document.getElementById('field-photo-load-state');
    if (indicator) return indicator;
    indicator = document.createElement('div');
    indicator.id = 'field-photo-load-state';
    indicator.className = 'map-data-status';
    indicator.setAttribute('role', 'status');
    indicator.setAttribute('aria-live', 'polite');
    indicator.hidden = true;
    const message = document.createElement('span');
    message.className = 'map-data-status-message';
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'map-data-status-retry';
    retry.addEventListener('click', () => loadFieldPhotos());
    indicator.replaceChildren(message, retry);
    document.body.append(indicator);
    return indicator;
}

function setFieldPhotoLoadState(state) {
    const indicator = fieldPhotoLoadIndicator();
    const message = indicator.querySelector('.map-data-status-message');
    const retry = indicator.querySelector('.map-data-status-retry');
    indicator.className = `map-data-status map-data-status--${state}`;
    indicator.hidden = state === 'ready';
    if (retry) {
        retry.hidden = state !== 'error';
        retry.textContent = fieldPhotoLoadText('fieldPhoto.loadRetry', 'Ponów');
    }
    if (!message) return;
    const messages = {
        loading: fieldPhotoLoadText('fieldPhoto.loading', 'Ładowanie zgłoszeń…'),
        empty: fieldPhotoLoadText('fieldPhoto.empty', 'Brak zgłoszeń dla bieżących warstw.'),
        error: fieldPhotoLoadText('fieldPhoto.loadError', 'Nie udało się odświeżyć zgłoszeń.'),
        ready: '',
    };
    message.textContent = messages[state] || '';
}

function clearFieldPhotoMarkers() {
    fieldPhotoMarkers.forEach(m => map.removeLayer(m));
    fieldPhotoMarkers = [];
}

function safeFieldPhotoId(value) {
    return String(value ?? '').replace(/[^A-Za-z0-9_-]/g, '');
}

function fieldPhotoIssueType(photo) {
    const issueType = String(photo?.issue_type || FIELD_PHOTO_ISSUE_TYPE_VEHICLE);
    return FIELD_PHOTO_ISSUE_TYPES.has(issueType) ? issueType : FIELD_PHOTO_ISSUE_TYPE_VEHICLE;
}

function fieldPhotoIssueLabel(issueType) {
    return t(`fieldPhoto.issueType.${FIELD_PHOTO_ISSUE_TYPES.has(issueType) ? issueType : FIELD_PHOTO_ISSUE_TYPE_VEHICLE}`);
}

function fieldPhotoIssueAllowed(issueType) {
    const safeIssueType = FIELD_PHOTO_ISSUE_TYPES.has(issueType) ? issueType : FIELD_PHOTO_ISSUE_TYPE_VEHICLE;
    return publicLayerAllowed(fieldPhotoPublicLayerKey(safeIssueType));
}

function fieldPhotoAnyIssueAllowed() {
    return Array.from(FIELD_PHOTO_ISSUE_TYPES).some(issueType => fieldPhotoIssueAllowed(issueType));
}

function fieldPhotoIssueVisible(issueType) {
    const safeIssueType = FIELD_PHOTO_ISSUE_TYPES.has(issueType) ? issueType : FIELD_PHOTO_ISSUE_TYPE_VEHICLE;
    return fieldPhotoIssueAllowed(safeIssueType) && fieldPhotoIssueFilters[safeIssueType] !== false;
}

function fieldPhotoReviewStatus(photo) {
    const status = String(photo?.public_review_status || 'approved');
    return status === 'pending' || status === 'rejected' ? status : 'approved';
}

function fieldPhotoGroupKind(photo) {
    const status = fieldPhotoReviewStatus(photo);
    if (status === 'pending') return adminAuthenticated ? 'admin-pending' : 'public-pending';
    return 'approved';
}

function fieldPhotoGroupReviewStatus(group) {
    return group?.reviewStatus === 'pending' ? 'pending' : 'approved';
}

function pendingFieldPhotoLayerAllowed() {
    return pendingFieldPhotoLayerVisible && publicLayerAllowed(PUBLIC_LAYER_KEYS.fieldPhotoPending);
}

function pendingVehiclePhotoAttachedToApprovedGroup(photo, approvedVehicleGroups = []) {
    if (fieldPhotoIssueType(photo) !== FIELD_PHOTO_ISSUE_TYPE_VEHICLE || fieldPhotoReviewStatus(photo) !== 'pending') {
        return false;
    }
    const lat = Number(photo.lat);
    const lon = Number(photo.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
    return (approvedVehicleGroups || []).some(group =>
        metersBetween(group.lat, group.lon, lat, lon) <= FIELD_PHOTO_GROUP_RADIUS_M
    );
}

function updateFieldPhotoIssueOptions() {
    const select = document.getElementById('field-photo-issue-type');
    if (!(select instanceof HTMLSelectElement)) return;
    let firstEnabled = '';
    Array.from(select.options).forEach(option => {
        const issueType = FIELD_PHOTO_ISSUE_TYPES.has(option.value) ? option.value : FIELD_PHOTO_ISSUE_TYPE_VEHICLE;
        const enabled = fieldPhotoIssueAllowed(issueType);
        option.disabled = !enabled;
        option.hidden = !enabled;
        if (enabled && !firstEnabled) firstEnabled = option.value;
    });
    select.disabled = !firstEnabled;
    if (firstEnabled && (!FIELD_PHOTO_ISSUE_TYPES.has(select.value) || select.selectedOptions[0]?.disabled)) {
        select.value = firstEnabled;
    }
    if (typeof updateFieldPhotoVehicleInsuranceUi === 'function') updateFieldPhotoVehicleInsuranceUi();
}

function filteredFieldPhotos(photos = fieldPhotoLayerData, options = {}) {
    const approvedVehicleGroups = Array.isArray(options.approvedVehicleGroups) ? options.approvedVehicleGroups : [];
    return (photos || []).filter(photo => {
        const issueType = fieldPhotoIssueType(photo);
        const reviewStatus = fieldPhotoReviewStatus(photo);
        if (reviewStatus === 'pending') {
            return pendingFieldPhotoLayerAllowed() && !pendingVehiclePhotoAttachedToApprovedGroup(photo, approvedVehicleGroups);
        }
        if (issueType === FIELD_PHOTO_ISSUE_TYPE_VEHICLE) return false;
        return fieldPhotoIssueVisible(issueType);
    });
}

function groupFieldPhotos(photos) {
    const groups = [];
    const index = createFieldPhotoSpatialIndex(groups);
    (photos || []).forEach(photo => {
        const lat = Number(photo.lat);
        const lon = Number(photo.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        const issueType = fieldPhotoIssueType(photo);
        const reviewStatus = fieldPhotoReviewStatus(photo);
        const groupKind = fieldPhotoGroupKind(photo);
        let group = index.candidates(lat, lon).find(candidate =>
            candidate.issueType === issueType
            && candidate.groupKind === groupKind
            && metersBetween(candidate.lat, candidate.lon, lat, lon) <= FIELD_PHOTO_GROUP_RADIUS_M
        );
        if (!group) {
            group = { lat, lon, issueType, reviewStatus, groupKind, photos: [] };
            groups.push(group);
            index.add(group);
        }
        group.photos.push(photo);
        const count = group.photos.length;
        group.lat = ((group.lat * (count - 1)) + lat) / count;
        group.lon = ((group.lon * (count - 1)) + lon) / count;
        index.update(group);
    });
    return groups;
}

function countVehicleLayerGroups() {
    if (!publicLayerAllowed(PUBLIC_LAYER_KEYS.vehicles)) return 0;
    return visibleVehicleGroups().length;
}

function countFieldPhotoIssueLayerGroups(issueType) {
    if (!publicLayerAllowed(fieldPhotoPublicLayerKey(issueType))) return 0;
    return groupFieldPhotos((fieldPhotoLayerData || []).filter(photo =>
        fieldPhotoIssueType(photo) === issueType
        && fieldPhotoReviewStatus(photo) !== 'pending'
    )).length;
}

function countPendingFieldPhotoLayerGroups() {
    if (!publicLayerAllowed(PUBLIC_LAYER_KEYS.fieldPhotoPending)) return 0;
    return groupFieldPhotos((fieldPhotoLayerData || []).filter(photo =>
        fieldPhotoReviewStatus(photo) === 'pending'
    )).length;
}

function updateLayerCountBadge(id, count, tooltipKey) {
    const badge = document.getElementById(id);
    if (!badge) return;
    const overview = fieldPhotoOverviewActive;
    const safeCount = Number.isFinite(count) ? count : 0;
    const tooltip = overview
        ? t('map.overviewCountsUnavailable')
        : `${t(tooltipKey, { n: safeCount })} ${t('layers.viewportCountSuffix')}`;
    badge.textContent = overview ? '–' : String(safeCount);
    badge.title = tooltip;
    badge.setAttribute('aria-label', tooltip);
}

function updateLayerCounters() {
    updateLayerCountBadge('layer-count-vehicles', countVehicleLayerGroups(), 'layers.countVehiclesTooltip');
    updateVehicleFilterControlsAndCounts();
    updateLayerCountBadge(
        'layer-count-field-photo-infrastructure',
        countFieldPhotoIssueLayerGroups('infrastructure'),
        'layers.countFieldPhotoInfrastructureTooltip'
    );
    updateLayerCountBadge(
        'layer-count-field-photo-smoke',
        countFieldPhotoIssueLayerGroups('smoke'),
        'layers.countFieldPhotoSmokeTooltip'
    );
    updateLayerCountBadge(
        'layer-count-field-photo-pending',
        countPendingFieldPhotoLayerGroups(),
        'layers.countFieldPhotoPendingTooltip'
    );
}

function placeFieldPhotos(photos = fieldPhotoLayerData) {
    clearFieldPhotoMarkers();
    clearFieldPhotoOverviewMarkers();
    if (fieldPhotoOverviewActive) {
        placeFieldPhotoOverviewMarkers();
        return;
    }
    const approvedVehicleGroups = vehicleLayerAllowed() ? visibleVehicleGroups(photos) : [];
    groupFieldPhotos(filteredFieldPhotos(photos, { approvedVehicleGroups })).forEach(group => {
        const reviewStatus = fieldPhotoGroupReviewStatus(group);
        const marker = L.marker([group.lat, group.lon], {
            icon: reviewStatus === 'pending' ? pendingSubmissionIcon() : fieldPhotoIcon(group.photos.length, group.issueType),
            zIndexOffset: 1400,
            draggable: adminAuthenticated,
            autoPan: adminAuthenticated,
        }).addTo(map).bindPopup(fieldPhotoGroupPopup(group), mapPopupOptions());
        if (adminAuthenticated) {
            marker.on('dragstart', () => marker.closePopup());
            marker.on('dragend', () => updateFieldPhotoGroupLocation(group, marker));
        }
        fieldPhotoMarkers.push(marker);
    });
}

async function loadFieldPhotos() {
    const requestRevision = ++fieldPhotoLoadRevision;
    window.clearTimeout(fieldPhotoViewportDebounceTimer);
    fieldPhotoViewportDebounceTimer = null;
    fieldPhotoLoadAbortController?.abort();
    const requestController = new AbortController();
    fieldPhotoLoadAbortController = requestController;
    setFieldPhotoLoadState('loading');
    let viewportKey = '';
    try {
        const viewport = fieldPhotoViewportQuery();
        const mode = fieldPhotoLoadMode();
        viewportKey = `${mode}:${viewport.key}`;
        fieldPhotoRequestedViewportKey = viewportKey;
        const data = mode === 'overview'
            ? await fetchFieldPhotoOverview(viewport, requestController.signal)
            : await fetchFieldPhotoViewportPages(viewport, requestController.signal);
        if (requestRevision !== fieldPhotoLoadRevision) return;
        if (mode !== fieldPhotoLoadMode()) {
            await loadFieldPhotos();
            return;
        }
        // Never replace the marker underneath a visible popup, including
        // when a request was already in flight before the popup opened.
        if (fieldPhotoPopupOpen) return;
        fieldPhotoOverviewActive = mode === 'overview';
        fieldPhotoOverviewCells = fieldPhotoOverviewActive ? data : [];
        fieldPhotoOverviewBbox = fieldPhotoOverviewActive ? viewport.bbox : '';
        fieldPhotoLayerData = fieldPhotoOverviewActive ? [] : data;
        fieldPhotoLoadedViewportKey = viewportKey;
        fieldPhotoLoadedViewportCoverage = { ...viewport.coverage, mode };
        placeFieldPhotos(fieldPhotoLayerData);
        placeVehicleMarkers();
        updateLayerCounters();
        setFieldPhotoLoadState(data.length ? 'ready' : 'empty');
    } catch (error) {
        if (requestRevision !== fieldPhotoLoadRevision || error?.payload?.code === 'cancelled') return;
        setFieldPhotoLoadState('error');
    } finally {
        if (fieldPhotoLoadAbortController === requestController) fieldPhotoLoadAbortController = null;
        if (fieldPhotoRequestedViewportKey === viewportKey) fieldPhotoRequestedViewportKey = '';
    }
}

function toggleFieldPhotoIssueFilter(issueType, visible) {
    const safeIssueType = FIELD_PHOTO_ISSUE_TYPES.has(issueType) ? issueType : FIELD_PHOTO_ISSUE_TYPE_VEHICLE;
    fieldPhotoIssueFilters[safeIssueType] = Boolean(visible);
    placeFieldPhotos(fieldPhotoLayerData);
    updateFieldPhotoIssueOptions();
    updateLayerCounters();
}

function togglePendingFieldPhotoLayer(visible) {
    pendingFieldPhotoLayerVisible = Boolean(visible);
    placeFieldPhotos(fieldPhotoLayerData);
    updateLayerCounters();
}
