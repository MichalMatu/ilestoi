const VEHICLE_RESOLUTION_FILTER_ACTIVE = FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_ACTIVE;
const VEHICLE_RESOLUTION_FILTER_ALL = 'all';
const VEHICLE_RESOLUTION_FILTER_REMOVED = FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_REMOVED;
const VEHICLE_RESOLUTION_FILTERS = new Set([
    VEHICLE_RESOLUTION_FILTER_ACTIVE,
    VEHICLE_RESOLUTION_FILTER_ALL,
    VEHICLE_RESOLUTION_FILTER_REMOVED,
]);
const VEHICLE_RESOLUTION_FILTER_CYCLE = [
    VEHICLE_RESOLUTION_FILTER_ACTIVE,
    VEHICLE_RESOLUTION_FILTER_ALL,
    VEHICLE_RESOLUTION_FILTER_REMOVED,
];
let vehicleResolutionFilter = loadVehicleResolutionFilter();

function vehicleResolutionStatus(value) {
    const status = String(value || FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_ACTIVE).trim();
    return FIELD_PHOTO_VEHICLE_RESOLUTION_STATUSES.has(status)
        ? status
        : FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_ACTIVE;
}

function vehicleGroupResolutionStatus(group) {
    const statuses = (group.photos || []).map(photo => vehicleResolutionStatus(photo.vehicle_resolution_status));
    return statuses.length && statuses.every(status => status === FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_REMOVED)
        ? FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_REMOVED
        : FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_ACTIVE;
}

function vehicleGroupIsRemoved(group) {
    return vehicleGroupResolutionStatus(group) === FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_REMOVED;
}

function vehicleGroupResolutionUpdatedAt(group) {
    if (!vehicleGroupIsRemoved(group)) return '';
    const updatedAtValues = (group.photos || [])
        .filter(photo => vehicleResolutionStatus(photo.vehicle_resolution_status) === FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_REMOVED)
        .map(photo => String(photo.vehicle_resolution_updated_at || '').trim())
        .filter(Boolean);
    return updatedAtValues.sort().at(-1) || '';
}

function vehicleResolutionHeaderBadge(group) {
    if (!vehicleGroupIsRemoved(group)) return null;
    const updatedText = humanDateTimeText(vehicleGroupResolutionUpdatedAt(group));
    return popupHeaderBadge(t('vehicle.resolution.badgeRemoved'), 'resolution', {
        title: updatedText
            ? t('vehicle.resolution.removedAt', { date: updatedText })
            : t('vehicle.resolution.removed'),
    });
}

function vehicleGroupResolutionAction(group, encodedApprovedPhotoIds) {
    const isRemoved = vehicleGroupIsRemoved(group);
    const nextStatus = isRemoved
        ? FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_ACTIVE
        : FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_REMOVED;
    return adminAuthenticated && encodedApprovedPhotoIds
        ? mapPopupIconAction(
            isRemoved ? 'map-popup-action--primary' : 'map-popup-action--success',
            t(isRemoved ? 'fieldPhoto.markActive' : 'fieldPhoto.markRemoved'),
            `updateFieldPhotoGroupResolution('${encodedApprovedPhotoIds}', '${nextStatus}', this)`,
            isRemoved
                ? 'M12 5V2L7 7l5 5V9a5 5 0 1 1-5 5H5a7 7 0 1 0 7-7V5z'
                : 'M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z'
        )
        : '';
}

function normalizeVehicleResolutionFilter(filter) {
    const safeFilter = String(filter || '');
    return VEHICLE_RESOLUTION_FILTERS.has(safeFilter) ? safeFilter : VEHICLE_RESOLUTION_FILTER_ACTIVE;
}

function loadVehicleResolutionFilter() {
    try {
        return normalizeVehicleResolutionFilter(localStorage.getItem(VEHICLE_RESOLUTION_FILTER_STORAGE_KEY));
    } catch (_) {
        return VEHICLE_RESOLUTION_FILTER_ACTIVE;
    }
}

function saveVehicleResolutionFilter(filter) {
    try {
        localStorage.setItem(VEHICLE_RESOLUTION_FILTER_STORAGE_KEY, normalizeVehicleResolutionFilter(filter));
    } catch (_) {}
}

function vehicleGroupMatchesResolutionFilter(group, filter = vehicleResolutionFilter) {
    switch (normalizeVehicleResolutionFilter(filter)) {
        case VEHICLE_RESOLUTION_FILTER_REMOVED:
            return vehicleGroupIsRemoved(group);
        case VEHICLE_RESOLUTION_FILTER_ALL:
            return true;
        case VEHICLE_RESOLUTION_FILTER_ACTIVE:
        default:
            return !vehicleGroupIsRemoved(group);
    }
}

function vehicleResolutionFilterLabel(filter) {
    switch (normalizeVehicleResolutionFilter(filter)) {
        case VEHICLE_RESOLUTION_FILTER_REMOVED:
            return t('layers.vehicleResolutionCycleRemoved');
        case VEHICLE_RESOLUTION_FILTER_ALL:
            return t('layers.vehicleResolutionCycleAll');
        case VEHICLE_RESOLUTION_FILTER_ACTIVE:
        default:
            return t('layers.vehicleResolutionCycleActive');
    }
}

function vehicleResolutionFilterCount(counts, filter = vehicleResolutionFilter) {
    switch (normalizeVehicleResolutionFilter(filter)) {
        case VEHICLE_RESOLUTION_FILTER_REMOVED:
        case VEHICLE_RESOLUTION_FILTER_ACTIVE:
            return counts.removed;
        case VEHICLE_RESOLUTION_FILTER_ALL:
        default:
            return null;
    }
}

function vehicleResolutionFilterDotClass(filter = vehicleResolutionFilter) {
    return normalizeVehicleResolutionFilter(filter) === VEHICLE_RESOLUTION_FILTER_ALL
        ? 'vehicle-filter-off-dot'
        : 'vehicle-resolution-dot';
}

function setVehicleResolutionFilter(filter) {
    const nextFilter = normalizeVehicleResolutionFilter(filter);
    if (nextFilter === vehicleResolutionFilter) {
        updateVehicleFilterControlsAndCounts();
        return;
    }
    vehicleResolutionFilter = nextFilter;
    saveVehicleResolutionFilter(vehicleResolutionFilter);
    refreshVehicleLayer();
}

function cycleVehicleResolutionFilter() {
    setVehicleResolutionFilter(nextVehicleCycleValue(VEHICLE_RESOLUTION_FILTER_CYCLE, vehicleResolutionFilter));
}
