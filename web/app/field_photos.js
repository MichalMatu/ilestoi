let fieldPhotoMarkers = [];
let fieldPhotoLayerData = [];
let fieldPhotoLoadRevision = 0;
let fieldPhotoLoadAbortController = null;

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
    const safeCount = Number.isFinite(count) ? count : 0;
    const tooltip = t(tooltipKey, { n: safeCount });
    badge.textContent = String(safeCount);
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
    fieldPhotoLoadAbortController?.abort();
    const requestController = new AbortController();
    fieldPhotoLoadAbortController = requestController;
    setFieldPhotoLoadState('loading');
    try {
        const data = await apiJson(`${FIELD_PHOTOS_URL}?ts=${Date.now()}`, {
            cache: 'no-store',
            signal: requestController.signal,
        });
        if (requestRevision !== fieldPhotoLoadRevision) return;
        if (data.status !== 'ok' || !Array.isArray(data.photos)) {
            throw new Error(fieldPhotoLoadText('fieldPhoto.loadError', 'Nie udało się odświeżyć zgłoszeń.'));
        }
        fieldPhotoLayerData = data.photos;
        placeFieldPhotos(fieldPhotoLayerData);
        placeVehicleMarkers();
        updateLayerCounters();
        setFieldPhotoLoadState(fieldPhotoLayerData.length ? 'ready' : 'empty');
    } catch (error) {
        if (requestRevision !== fieldPhotoLoadRevision || error?.payload?.code === 'cancelled') return;
        setFieldPhotoLoadState('error');
    } finally {
        if (fieldPhotoLoadAbortController === requestController) fieldPhotoLoadAbortController = null;
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
