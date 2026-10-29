// odległość w metrach między dwoma punktami GPS (mała skala)
function metersBetween(lat1, lon1, lat2, lon2) {
    const dLat = (lat1 - lat2) * METERS_PER_DEGREE_LAT;
    const dLon = (lon1 - lon2) * METERS_PER_DEGREE_LAT * Math.cos(lat1 * Math.PI/180);
    return Math.sqrt(dLat*dLat + dLon*dLon);
}

function readStoredMapView() {
    const params = new URLSearchParams(window.location.search);
    if (params.has('lat') && params.has('lon') && params.has('z')) {
        const urlLat = Number(params.get('lat'));
        const urlLon = Number(params.get('lon'));
        const urlZoom = Number(params.get('z'));
        if (
            Number.isFinite(urlLat) && urlLat >= -90 && urlLat <= 90 &&
            Number.isFinite(urlLon) && urlLon >= -180 && urlLon <= 180 &&
            Number.isFinite(urlZoom) && urlZoom >= 0 && urlZoom <= MAX_MAP_ZOOM
        ) {
            return { center: [urlLat, urlLon], zoom: urlZoom };
        }
    }

    try {
        const stored = JSON.parse(localStorage.getItem(MAP_VIEW_STORAGE_KEY) || 'null');
        if (!stored) return DEFAULT_MAP_VIEW;

        const lat = Number(stored.lat);
        const lon = Number(stored.lon);
        const zoom = Number(stored.zoom);
        if (
            Number.isFinite(lat) && lat >= -90 && lat <= 90 &&
            Number.isFinite(lon) && lon >= -180 && lon <= 180 &&
            Number.isFinite(zoom) && zoom >= 0 && zoom <= MAX_MAP_ZOOM
        ) {
            return { center: [lat, lon], zoom };
        }
    } catch (err) {
        console.warn('Nie udało się odczytać zapisanej pozycji mapy.', err);
    }
    return DEFAULT_MAP_VIEW;
}

function saveMapView() {
    try {
        const center = map.getCenter();
        localStorage.setItem(MAP_VIEW_STORAGE_KEY, JSON.stringify({
            lat: center.lat,
            lon: center.lng,
            zoom: map.getZoom(),
        }));
    } catch (err) {
        console.warn('Nie udało się zapisać pozycji mapy.', err);
    }
}

function appPlaceUrl(lat, lon, zoom, options = {}) {
    const url = new URL(window.location.href);
    const placeLat = Number(lat);
    const placeLon = Number(lon);
    const placeZoom = Number(zoom);
    const photoId = String(options.photoId ?? '').replace(/[^A-Za-z0-9_-]/g, '');
    url.searchParams.set('lat', Number.isFinite(placeLat) ? placeLat.toFixed(6) : DEFAULT_MAP_VIEW.center[0].toFixed(6));
    url.searchParams.set('lon', Number.isFinite(placeLon) ? placeLon.toFixed(6) : DEFAULT_MAP_VIEW.center[1].toFixed(6));
    url.searchParams.set('z', String(Number.isFinite(placeZoom) ? Math.round(placeZoom) : DEFAULT_MAP_VIEW.zoom));
    if (photoId) url.searchParams.set('photo', photoId);
    else url.searchParams.delete('photo');
    return url.toString();
}

function metersBetweenLatLng(latlng1, latlng2) {
    const lat_m = METERS_PER_DEGREE_LAT;
    const lon_m = METERS_PER_DEGREE_LAT * Math.cos(latlng1.lat * Math.PI / 180);
    const dLat = (latlng1.lat - latlng2.lat) * lat_m;
    const dLon = (latlng1.lng - latlng2.lng) * lon_m;
    return { dLat: Math.abs(dLat), dLon: Math.abs(dLon) };
}

function squareBounds(start, end) {
    const lat_m = METERS_PER_DEGREE_LAT;
    const lon_m = METERS_PER_DEGREE_LAT * Math.cos(start.lat * Math.PI / 180);
    const dLatM = (end.lat - start.lat) * lat_m;
    const dLonM = (end.lng - start.lng) * lon_m;
    const sizeM = Math.max(Math.abs(dLatM), Math.abs(dLonM));
    const lat2 = start.lat + Math.sign(dLatM || 1) * sizeM / lat_m;
    const lng2 = start.lng + Math.sign(dLonM || 1) * sizeM / lon_m;
    return L.latLngBounds(start, L.latLng(lat2, lng2));
}

/**
 * An exact candidate index for the existing metre-based grouping semantics.
 *
 * Retain all groups in insertion order: field photos choose the FIRST match,
 * vehicles choose the nearest match (first group wins distance ties).
 * Near the poles or outside geographic bounds, fall back to the full scan.
 * The longitude buckets deliberately use a conservative latitude bound:
 * metersBetween() scales longitude by cos(candidate-group latitude).
 */
function createFieldPhotoSpatialIndex(groups, radiusM = FIELD_PHOTO_GROUP_RADIUS_M) {
    const maxLatitude = 84;
    const validScale = Number.isFinite(radiusM) && radiusM > 0
        && Number.isFinite(METERS_PER_DEGREE_LAT) && METERS_PER_DEGREE_LAT > 0;
    if (!validScale) {
        return { add() {}, update() {}, candidates() { return groups; } };
    }

    const latitudeStep = radiusM / METERS_PER_DEGREE_LAT * 1.001;
    const longitudeStep = radiusM / (METERS_PER_DEGREE_LAT * Math.cos(maxLatitude * Math.PI / 180)) * 1.001;
    const buckets = new Map();
    const positions = new Map();
    const overflow = new Set();
    const insertionOrder = new Map();

    function cell(lat, lon) {
        if (!Number.isFinite(lat) || !Number.isFinite(lon)
            || Math.abs(lat) >= maxLatitude || Math.abs(lon) > 180) return null;
        const y = Math.floor(lat / latitudeStep);
        const x = Math.floor(lon / longitudeStep);
        return { x, y, key: y + ':' + x };
    }

    function addToCell(group, location) {
        if (!location) {
            overflow.add(group);
        } else {
            if (!buckets.has(location.key)) buckets.set(location.key, new Set());
            buckets.get(location.key).add(group);
        }
        positions.set(group, location);
    }

    function removeFromCell(group, location) {
        if (!location) {
            overflow.delete(group);
        } else {
            const bucket = buckets.get(location.key);
            bucket?.delete(group);
            if (bucket?.size === 0) buckets.delete(location.key);
        }
    }

    return {
        add(group) {
            if (insertionOrder.has(group)) return;
            insertionOrder.set(group, insertionOrder.size);
            addToCell(group, cell(group.lat, group.lon));
        },
        update(group) {
            if (!insertionOrder.has(group)) return;
            const previous = positions.get(group);
            const current = cell(group.lat, group.lon);
            if (previous?.key === current?.key) return;
            removeFromCell(group, previous);
            addToCell(group, current);
        },
        candidates(lat, lon) {
            const position = cell(lat, lon);
            if (!position) return groups;
            const found = new Set(overflow);
            for (let y = position.y - 1; y <= position.y + 1; y++) {
                for (let x = position.x - 1; x <= position.x + 1; x++) {
                    const bucket = buckets.get(y + ':' + x);
                    if (bucket) for (const group of bucket) found.add(group);
                }
            }
            return Array.from(found).sort((a, b) => insertionOrder.get(a) - insertionOrder.get(b));
        },
    };
}
