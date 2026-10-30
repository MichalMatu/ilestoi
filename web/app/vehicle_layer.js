let vehicleMarkers = [];
let vehicleLayerVisible = true;
const VEHICLE_FILTER_ALL = 'all';
const VEHICLE_INSURANCE_FILTER_INSURED = 'insured';
const VEHICLE_INSURANCE_FILTER_UNINSURED = 'uninsured';
const VEHICLE_INSURANCE_FILTER_UNKNOWN = FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN;
const VEHICLE_INSURANCE_FILTERS = new Set([VEHICLE_FILTER_ALL, VEHICLE_INSURANCE_FILTER_INSURED, VEHICLE_INSURANCE_FILTER_UNINSURED, VEHICLE_INSURANCE_FILTER_UNKNOWN]);
const VEHICLE_STANDING_FILTER_OFF = 0;
const VEHICLE_PHOTO_FILTER_OFF = 'off';
const VEHICLE_PHOTO_FILTER_UP_TO_6 = 'up_to_6';
const VEHICLE_PHOTO_FILTER_ABOVE_6 = 'above_6';
const VEHICLE_PHOTO_FILTER_CYCLE = [VEHICLE_PHOTO_FILTER_OFF, VEHICLE_PHOTO_FILTER_UP_TO_6, VEHICLE_PHOTO_FILTER_ABOVE_6];
const VEHICLE_MARKER_BASE_Z_INDEX = 1200;
let vehicleInsuranceFilter = VEHICLE_FILTER_ALL;
let vehicleStandingFilterDays = loadVehicleStandingFilterDays();
let vehiclePhotoFilter = VEHICLE_PHOTO_FILTER_OFF;
let pendingVehiclePhotoFocusId = '';
let vehiclePhotoFocusDone = false;

try {
    pendingVehiclePhotoFocusId = String(new URLSearchParams(window.location.search).get('photo') || '')
        .replace(/[^A-Za-z0-9_-]/g, '');
    vehiclePhotoFocusDone = !pendingVehiclePhotoFocusId;
} catch (_) {
    pendingVehiclePhotoFocusId = '';
    vehiclePhotoFocusDone = true;
}

function clearVehicleMarkers() {
    vehicleMarkers.forEach(marker => map.removeLayer(marker));
    vehicleMarkers = [];
}

function vehicleLayerAllowed() {
    return vehicleLayerVisible && publicLayerAllowed(PUBLIC_LAYER_KEYS.vehicles);
}

function vehiclePhotoIsApproved(photo) {
    return fieldPhotoIssueType(photo) === FIELD_PHOTO_ISSUE_TYPE_VEHICLE
        && fieldPhotoReviewStatus(photo) === 'approved';
}

function emptyVehicleGroup(lat, lon) {
    return { lat, lon, photos: [], pendingPhotos: [] };
}

function nearestVehicleGroup(groups, lat, lon, index = null) {
    let nearest = null;
    const candidates = index ? index.candidates(lat, lon) : groups;
    candidates.forEach(group => {
        const distanceM = metersBetween(group.lat, group.lon, lat, lon);
        if (distanceM > FIELD_PHOTO_GROUP_RADIUS_M) return;
        if (!nearest || distanceM < nearest.distanceM) nearest = { group, distanceM };
    });
    return nearest?.group || null;
}

function addVehiclePhotoToGroup(group, photo, lat, lon) {
    group.photos.push(photo);
    const count = group.photos.length;
    group.lat = ((group.lat * (count - 1)) + lat) / count;
    group.lon = ((group.lon * (count - 1)) + lon) / count;
}

function vehiclePendingPhotoIsVisible(photo) {
    return fieldPhotoIssueType(photo) === FIELD_PHOTO_ISSUE_TYPE_VEHICLE
        && fieldPhotoReviewStatus(photo) === 'pending'
        && pendingFieldPhotoLayerAllowed();
}

function attachPendingVehiclePhotosToGroups(groups, photos = fieldPhotoLayerData, index = null) {
    if (!groups.length || !pendingFieldPhotoLayerAllowed()) return groups;
    (photos || []).filter(vehiclePendingPhotoIsVisible).forEach(photo => {
        const lat = Number(photo.lat);
        const lon = Number(photo.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        const group = nearestVehicleGroup(groups, lat, lon, index);
        if (group) group.pendingPhotos.push(photo);
    });
    return groups;
}

function buildVehicleGroups(photos = fieldPhotoLayerData) {
    const groups = [];
    const index = createFieldPhotoSpatialIndex(groups);
    (photos || []).filter(vehiclePhotoIsApproved).forEach(photo => {
        const lat = Number(photo.lat);
        const lon = Number(photo.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        let group = nearestVehicleGroup(groups, lat, lon, index);
        if (!group) {
            group = emptyVehicleGroup(lat, lon);
            groups.push(group);
            index.add(group);
        }
        addVehiclePhotoToGroup(group, photo, lat, lon);
        index.update(group);
    });
    return attachPendingVehiclePhotosToGroups(groups, photos, index);
}

function vehicleGroupPhotoCount(group) {
    return Array.isArray(group?.photos) ? group.photos.length : 0;
}

function vehicleGroupPendingPhotos(group) {
    return Array.isArray(group?.pendingPhotos) ? group.pendingPhotos : [];
}

function vehicleGroupPendingPhotoCount(group) {
    return vehicleGroupPendingPhotos(group).length;
}

function vehicleGroupHasPhotoId(group, photoId) {
    const safePhotoId = String(photoId || '').replace(/[^A-Za-z0-9_-]/g, '');
    return Boolean(safePhotoId)
        && [...(group.photos || []), ...vehicleGroupPendingPhotos(group)]
            .some(photo => safeFieldPhotoId(photo.id) === safePhotoId);
}

function focusVehicleMarkerFromUrl(group, marker) {
    if (vehiclePhotoFocusDone || !pendingVehiclePhotoFocusId || !vehicleGroupHasPhotoId(group, pendingVehiclePhotoFocusId)) {
        return;
    }
    vehiclePhotoFocusDone = true;
    requestAnimationFrame(() => {
        if (!map.hasLayer(marker)) return;
        const targetZoom = Math.max(Number(map.getZoom()) || 0, 19);
        map.setView([group.lat, group.lon], targetZoom, { animate: false });
        marker.openPopup();
    });
}

function vehicleLoosePhotoActions(group, { includeReport = true, includeUpload = true } = {}) {
    const photos = group.photos || [];
    const editablePhotos = [...photos, ...vehicleGroupPendingPhotos(group)];
    if (!photos.length) return [];
    const lat = Number(group.lat);
    const lon = Number(group.lon);
    const encodedApprovedPhotoIds = encodedFieldPhotoIdsForGroup({ photos });
    const encodedEditablePhotoIds = encodedFieldPhotoIdsForGroup({ photos: editablePhotos });
    const coordinatesOk = Number.isFinite(lat) && Number.isFinite(lon) && encodedApprovedPhotoIds;
    const isRemoved = vehicleGroupIsRemoved(group);
    const canCreateReport = includeReport
        && coordinatesOk
        && !isRemoved
        && publicFeatureAllowed(PUBLIC_FEATURE_KEYS.reportPdfs);
    const canAddFieldPhotosHere = includeUpload
        && coordinatesOk
        && publicFeatureAllowed(PUBLIC_FEATURE_KEYS.photoUploads)
        && fieldPhotoIssueAllowed(FIELD_PHOTO_ISSUE_TYPE_VEHICLE);
    const ownerButton = encodedEditablePhotoIds
        ? mapPopupIconAction(
            'map-popup-action--primary',
            t('fieldPhoto.editMyPhoto'),
            `openFieldPhotoOwnerEditor('${encodedEditablePhotoIds}')`,
            'M11 17h2v-6h-2v6zm0-8h2V7h-2v2zm1-7a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16z'
        )
        : '';
    const reportButton = canCreateReport
        ? mapPopupIconAction(
            'map-popup-action--report',
            t('fieldPhoto.reportPdf'),
            `openFieldPhotoGroupReport(${lat}, ${lon}, '${encodedApprovedPhotoIds}', this)`,
            'M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm1 7V3.5L18.5 9H15zM8 13h8v2H8v-2zm0 4h8v2H8v-2z'
        )
        : '';
    const photoButton = canAddFieldPhotosHere
        ? mapPopupIconAction(
            'map-popup-action--primary',
            t('fieldPhoto.addPhotosHere'),
            `openFieldPhotoGroupPhotoUpload(${lat}, ${lon}, '${encodedApprovedPhotoIds}', '${FIELD_PHOTO_ISSUE_TYPE_VEHICLE}', this)`,
            'M5 7h2.8L9.4 5h5.2l1.6 2H19c1.1 0 2 .9 2 2v10c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V9c0-1.1.9-2 2-2zm7 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm5-5h-2v2h-2v2h2v2h2v-2h2v-2h-2v-2z'
        )
        : '';
    const reviewButton = adminAuthenticated && encodedEditablePhotoIds
        ? mapPopupIconAction(
            'map-popup-action--primary',
            t('fieldPhoto.reviewPhotos'),
            `openPhotoReviewForFieldPhotoGroup('${encodedEditablePhotoIds}')`,
            'M4 5h16v14H4V5zm2 2v10h12V7H6zm2 8h8l-2.5-3.2-1.8 2.2-1.3-1.5L8 15zm10-9.5 1.1-1.1 1.5 1.5-1.1 1.1-1.5-1.5zm-6.5 6.5L18 5.5 19.5 7 13 13.5H11.5V12z'
        )
        : '';
    const resolutionButton = vehicleGroupResolutionAction(group, encodedApprovedPhotoIds);
    const deleteButton = adminAuthenticated && encodedApprovedPhotoIds
        ? mapPopupIconAction(
            'map-popup-action--danger',
            t('fieldPhoto.delete'),
            `deleteFieldPhotoGroup('${encodedApprovedPhotoIds}', this)`,
            'M9 3v1H4v2h16V4h-5V3H9zm-3 5l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13H6zm4 3h1v9h-1v-9zm3 0h1v9h-1v-9z'
        )
        : '';
    return [ownerButton, reportButton, photoButton, reviewButton, resolutionButton, deleteButton];
}

function vehicleGroupPreviews(group) {
    return fieldPhotoGroupPreviews(group.photos);
}

function vehicleGroupLinks(group) {
    const photos = group.photos || [];
    return fieldPhotoGroupLinks(group, photos);
}

function vehicleGroupActions(group) {
    return vehicleLoosePhotoActions(group);
}

function vehicleGroupInsuranceStatus(group) {
    const statuses = (group.photos || []).map(photo => vehicleInsuranceStatus(photo.vehicle_insurance_status));
    if (statuses.includes('uninsured')) return 'uninsured';
    if (statuses.includes('insured')) return 'insured';
    return statuses.length ? FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN : '';
}

function vehicleGroupInsuranceCheckedAt(group) {
    const status = vehicleGroupInsuranceStatus(group);
    if (status === FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN) return '';
    const checkedAtValues = (group.photos || [])
        .filter(photo => vehicleInsuranceStatus(photo.vehicle_insurance_status) === status)
        .map(photo => String(photo.vehicle_insurance_checked_at || '').trim())
        .filter(Boolean);
    return checkedAtValues.sort().at(-1) || '';
}

function normalizeVehicleStandingFilterDays(days) {
    const safeDays = Number(days);
    if (safeDays === VEHICLE_STANDING_FILTER_OFF) return VEHICLE_STANDING_FILTER_OFF;
    return VEHICLE_LONG_STANDING_DAY_OPTIONS.includes(safeDays) ? safeDays : VEHICLE_STANDING_FILTER_OFF;
}

function normalizeVehiclePhotoFilter(filter) {
    const safeFilter = String(filter || '');
    return VEHICLE_PHOTO_FILTER_CYCLE.includes(safeFilter) ? safeFilter : VEHICLE_PHOTO_FILTER_OFF;
}

function loadVehicleStandingFilterDays() {
    try {
        return normalizeVehicleStandingFilterDays(localStorage.getItem(VEHICLE_STANDING_FILTER_DAYS_STORAGE_KEY));
    } catch (_) {
        return VEHICLE_STANDING_FILTER_OFF;
    }
}

function saveVehicleStandingFilterDays(days) {
    try {
        localStorage.setItem(VEHICLE_STANDING_FILTER_DAYS_STORAGE_KEY, String(days));
    } catch (_) {}
}

function activeVehicleLongStandingDays() {
    return vehicleStandingFilterDays || VEHICLE_LONG_STANDING_DEFAULT_DAYS;
}

function vehicleLongStandingMs(days = activeVehicleLongStandingDays()) {
    return days * 24 * 60 * 60 * 1000;
}

function vehicleGroupIsLongStanding(group, nowMs = Date.now(), days = activeVehicleLongStandingDays()) {
    const startTimestampMs = fieldPhotoGroupStartTimestamp(group.photos, nowMs);
    return Number.isFinite(startTimestampMs) && nowMs - startTimestampMs >= vehicleLongStandingMs(days);
}

function normalizeVehicleInsuranceFilter(filter) {
    const safeFilter = String(filter || '');
    return VEHICLE_INSURANCE_FILTERS.has(safeFilter) ? safeFilter : VEHICLE_FILTER_ALL;
}

function vehicleGroupMatchesInsuranceFilter(group, filter = vehicleInsuranceFilter) {
    switch (normalizeVehicleInsuranceFilter(filter)) {
        case VEHICLE_INSURANCE_FILTER_INSURED:
            return vehicleGroupInsuranceStatus(group) === 'insured';
        case VEHICLE_INSURANCE_FILTER_UNINSURED:
            return vehicleGroupInsuranceStatus(group) === 'uninsured';
        case VEHICLE_INSURANCE_FILTER_UNKNOWN:
            return vehicleGroupInsuranceStatus(group) === FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN;
        case VEHICLE_FILTER_ALL:
        default:
            return true;
    }
}

function vehicleGroupMatchesStandingFilter(group, days = vehicleStandingFilterDays) {
    const safeDays = normalizeVehicleStandingFilterDays(days);
    return safeDays === VEHICLE_STANDING_FILTER_OFF || vehicleGroupIsLongStanding(group, Date.now(), safeDays);
}

function vehicleGroupMatchesPhotoFilter(group, filter = vehiclePhotoFilter) {
    const safeFilter = normalizeVehiclePhotoFilter(filter);
    if (safeFilter === VEHICLE_PHOTO_FILTER_UP_TO_6) return vehicleGroupPhotoCount(group) <= 6;
    if (safeFilter === VEHICLE_PHOTO_FILTER_ABOVE_6) return vehicleGroupPhotoCount(group) > 6;
    return true;
}

function vehicleGroupMatchesFilters(group) {
    return vehicleGroupMatchesInsuranceFilter(group)
        && vehicleGroupMatchesStandingFilter(group)
        && vehicleGroupMatchesPhotoFilter(group)
        && vehicleGroupMatchesResolutionFilter(group);
}

function visibleVehicleGroups(photos = fieldPhotoLayerData) {
    if (!publicLayerAllowed(PUBLIC_LAYER_KEYS.vehicles)) return [];
    return buildVehicleGroups(photos).filter(group =>
        vehicleGroupPhotoCount(group) > 0
        && vehicleGroupMatchesFilters(group)
    );
}

function vehicleGroupStatusPriority(group) {
    const insuranceStatus = vehicleGroupInsuranceStatus(group);
    let priority = 0;
    if (insuranceStatus === 'insured') priority += 10;
    if (insuranceStatus === FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN) priority += 20;
    if (vehicleGroupIsRemoved(group)) priority += 30;
    if (vehicleGroupIsLongStanding(group)) priority += 40;
    if (insuranceStatus === 'uninsured') priority += 80;
    return priority;
}

function vehicleGroupZIndexOffset(group) {
    return VEHICLE_MARKER_BASE_Z_INDEX + vehicleGroupStatusPriority(group);
}

function prioritizedVehicleGroups(photos = fieldPhotoLayerData) {
    return visibleVehicleGroups(photos).sort((a, b) => vehicleGroupStatusPriority(a) - vehicleGroupStatusPriority(b));
}

function setVehicleInsuranceFilter(filter) {
    const nextFilter = normalizeVehicleInsuranceFilter(filter);
    if (nextFilter === vehicleInsuranceFilter) {
        updateVehicleFilterSelectors();
        return;
    }
    vehicleInsuranceFilter = nextFilter;
    refreshVehicleLayer();
}

function setVehicleStandingFilterDays(days) {
    const nextDays = normalizeVehicleStandingFilterDays(days);
    if (nextDays === vehicleStandingFilterDays) {
        updateVehicleFilterSelectors();
        return;
    }
    vehicleStandingFilterDays = nextDays;
    saveVehicleStandingFilterDays(vehicleStandingFilterDays);
    refreshVehicleLayer();
}

function setVehiclePhotoFilter(filter) {
    const nextFilter = normalizeVehiclePhotoFilter(filter);
    if (nextFilter === vehiclePhotoFilter) {
        updateVehicleFilterSelectors();
        return;
    }
    vehiclePhotoFilter = nextFilter;
    refreshVehicleLayer();
}

function vehicleMarkerTooltip(group) {
    const status = vehicleInsuranceStatus(vehicleGroupInsuranceStatus(group));
    const parts = [
        t('vehicle.markerTooltipPhotos', { n: vehicleGroupPhotoCount(group) }),
    ];
    if (vehicleGroupIsRemoved(group)) parts.push(t('vehicle.markerTooltipRemoved'));
    const pendingCount = vehicleGroupPendingPhotoCount(group);
    if (pendingCount) parts.push(t('vehicle.markerTooltipPendingPhotos', { n: pendingCount }));
    const age = popupElapsedAgeText(group.photos);
    if (age) parts.push(t('vehicle.markerTooltipAge', { age }));
    parts.push(t('vehicle.markerTooltipInsurance', {
        status: t(`vehicle.markerInsuranceShort.${status}`),
    }));
    return parts.join(', ');
}

function updateVehicleFilterSelectors() {
    // Refresh restored preferences without counting every marker again.
    const values = {
        'vehicle-insurance-select': vehicleInsuranceFilter,
        'vehicle-standing-select': String(vehicleStandingFilterDays),
        'vehicle-photo-select': vehiclePhotoFilter,
        'vehicle-resolution-select': vehicleResolutionFilter,
    };
    Object.entries(values).forEach(([id, value]) => {
        const select = document.getElementById(id);
        if (select && select.value !== value) select.value = value;
    });
}

function vehiclePhotoPopup(group) {
    const photoCount = vehicleGroupPhotoCount(group);
    const pendingCount = vehicleGroupPendingPhotoCount(group);
    const title = photoCount > 1
        ? t('vehicle.popup.photoGroupTitle', { n: photoCount })
        : t('vehicle.popup.photoTitle');
    const previews = vehicleGroupPreviews(group);
    const insuranceStatus = vehicleGroupInsuranceStatus(group);
    const insuranceCheckedAt = vehicleGroupInsuranceCheckedAt(group);
    return mapPopup(`
            ${popupHeader(title, [
                vehicleResolutionHeaderBadge(group),
                vehicleInsuranceHeaderBadge(insuranceStatus, insuranceCheckedAt),
                popupElapsedAgeBadge(group.photos),
                pendingCount ? popupHeaderBadge(t('vehicle.popup.pendingBadge', { n: pendingCount }), 'status') : '',
            ])}
            ${popupPhotoSection('', previews, { className: 'map-popup-photo-grid--field', total: photoCount, showHeader: false })}
            ${vehicleGroupLinks(group)}
            ${popupActions(vehicleGroupActions(group))}
    `, mapPopupMediaModifiers(previews, 'map-popup--vehicle-photo'));
}

function vehicleGroupPopup(group) {
    return vehiclePhotoPopup(group);
}

function placeVehicleMarkers() {
    clearVehicleMarkers();
    if (fieldPhotoOverviewActive || !vehicleLayerAllowed()) return;
    prioritizedVehicleGroups().forEach(group => {
        const canDrag = adminAuthenticated && group.photos.length > 0;
        const markerTooltip = vehicleMarkerTooltip(group);
        const marker = L.marker([group.lat, group.lon], {
            icon: vehicleIcon(
                vehicleGroupPhotoCount(group),
                'approved',
                vehicleGroupInsuranceStatus(group),
                vehicleGroupIsLongStanding(group),
                vehicleGroupPendingPhotoCount(group),
                vehicleGroupResolutionStatus(group)
            ),
            zIndexOffset: vehicleGroupZIndexOffset(group),
            draggable: canDrag,
            autoPan: canDrag,
            alt: markerTooltip,
        }).addTo(map).bindPopup(vehicleGroupPopup(group), mapPopupOptions());
        marker.getElement()?.setAttribute('aria-label', markerTooltip);
        marker.bindTooltip(markerTooltip, {
            className: 'vehicle-marker-tooltip',
            direction: 'top',
            opacity: 0.96,
            sticky: true,
        });
        if (canDrag) {
            marker.on('dragstart', () => marker.closePopup());
            marker.on('dragend', () => updateFieldPhotoGroupLocation(
                { ...group, issueType: FIELD_PHOTO_ISSUE_TYPE_VEHICLE },
                marker
            ));
        }
        vehicleMarkers.push(marker);
        focusVehicleMarkerFromUrl(group, marker);
    });
}

function refreshVehicleLayer() {
    if ((fieldPhotoLoadMode() === 'overview') !== fieldPhotoOverviewActive) return loadFieldPhotos();
    if (fieldPhotoOverviewActive) placeFieldPhotos(fieldPhotoLayerData);
    else placeVehicleMarkers();
    updateLayerCounters();
}

function toggleVehicleLayer(visible) {
    vehicleLayerVisible = Boolean(visible);
    refreshVehicleLayer();
}
