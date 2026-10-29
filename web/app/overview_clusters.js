// Coarse map view: synthetic centers represent photo counts, never car positions.
let fieldPhotoOverviewActive = false;
let fieldPhotoOverviewCells = [];
let fieldPhotoOverviewMarkers = [];
let fieldPhotoOverviewBbox = '';
const FIELD_PHOTO_OVERVIEW_MAX_ZOOM = 10;
const FIELD_PHOTO_OVERVIEW_GRID_SIZE = 16;

function fieldPhotoLoadMode() {
    if (typeof map.getZoom !== 'function' || map.getZoom() > FIELD_PHOTO_OVERVIEW_MAX_ZOOM) return 'photos';
    if (adminAuthenticated || pendingVehiclePhotoFocusId) return 'photos';
    if (vehicleInsuranceFilter !== VEHICLE_FILTER_ALL
        || vehicleStandingFilterDays !== VEHICLE_STANDING_FILTER_OFF
        || vehiclePhotoFilter !== VEHICLE_PHOTO_FILTER_OFF
        || vehicleResolutionFilter !== VEHICLE_FILTER_ALL) return 'photos';
    return 'overview';
}

function clearFieldPhotoOverviewMarkers() {
    fieldPhotoOverviewMarkers.forEach(marker => map.removeLayer(marker));
    fieldPhotoOverviewMarkers = [];
}

function visibleOverviewPhotoCount(cell) {
    let count = 0;
    if (vehicleLayerAllowed()) count += cell.vehicles;
    if (fieldPhotoIssueVisible('infrastructure')) count += cell.infrastructure;
    if (fieldPhotoIssueVisible('smoke')) count += cell.smoke;
    if (pendingFieldPhotoLayerAllowed()) count += cell.pending;
    return count;
}

function overviewDisplayLongitude(lon, bbox = fieldPhotoOverviewBbox) {
    const [west, , east] = bbox.split(',').map(Number);
    const longitudeSpan = east >= west ? east - west : east + 360 - west;
    const mapLongitude = map.getCenter?.().lng;
    const reference = Number.isFinite(mapLongitude) ? mapLongitude : west + longitudeSpan / 2;
    return lon + 360 * Math.round((reference - lon) / 360);
}

function overviewCellBounds(cell, bbox = fieldPhotoOverviewBbox) {
    const [west, south, east, north] = bbox.split(',').map(Number);
    const latStep = (north - south) / FIELD_PHOTO_OVERVIEW_GRID_SIZE;
    const lonStep = (east >= west ? east - west : east + 360 - west) / FIELD_PHOTO_OVERVIEW_GRID_SIZE;
    const longitude = overviewDisplayLongitude(cell.lon, bbox);
    const centerLat = cell.lat;
    return [
        [centerLat - latStep / 2, longitude - lonStep / 2],
        [centerLat + latStep / 2, longitude + lonStep / 2],
    ];
}

async function fetchFieldPhotoOverview(viewport, signal) {
    const params = new URLSearchParams({ bbox: viewport.bbox });
    const data = await apiJson(`${FIELD_PHOTOS_URL}/clusters?${params}`, { cache: 'no-store', signal });
    if (data.status !== 'ok' || !Array.isArray(data.clusters) || data.clusters.length > 256
        || data.clusters.some(cell => !Number.isFinite(cell.lat) || !Number.isFinite(cell.lon)
            || !Number.isSafeInteger(cell.total) || cell.total < 1
            || ['vehicles', 'infrastructure', 'smoke', 'pending'].some(key =>
                !Number.isSafeInteger(cell[key]) || cell[key] < 0)
            || cell.total !== cell.vehicles + cell.infrastructure + cell.smoke + cell.pending)) {
        throw new Error(fieldPhotoLoadText('fieldPhoto.loadError', 'Nie udało się odświeżyć zgłoszeń.'));
    }
    return data.clusters;
}

function placeFieldPhotoOverviewMarkers() {
    fieldPhotoOverviewCells.forEach(cell => {
        const count = visibleOverviewPhotoCount(cell);
        if (!count) return;
        const tooltip = t('map.overviewPhotoCount', { n: count });
        const marker = L.marker([cell.lat, overviewDisplayLongitude(cell.lon)], {
            icon: overviewPhotoIcon(count),
            keyboard: true,
            alt: tooltip,
            zIndexOffset: 1400,
        }).addTo(map);
        marker.getElement()?.setAttribute('aria-label', tooltip);
        marker.bindTooltip(tooltip, { direction: 'top', opacity: 0.96 });
        marker.on('click', () => map.fitBounds(overviewCellBounds(cell), { padding: [24, 24] }));
        fieldPhotoOverviewMarkers.push(marker);
    });
}
