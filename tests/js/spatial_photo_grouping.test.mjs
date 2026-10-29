import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import vm from 'node:vm';

const ROOT = process.cwd();
const RADIUS_M = 1;
const METRES_PER_LATITUDE_DEGREE = 111_320;

function distance(lat1, lon1, lat2, lon2) {
    const dLat = (lat1 - lat2) * METRES_PER_LATITUDE_DEGREE;
    const dLon = (lon1 - lon2) * METRES_PER_LATITUDE_DEGREE * Math.cos(lat1 * Math.PI / 180);
    return Math.sqrt(dLat * dLat + dLon * dLon);
}

function referenceFieldGroups(photos, isAdmin = false) {
    const groups = [];
    for (const photo of photos) {
        const lat = Number(photo.lat);
        const lon = Number(photo.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
        const issueType = photo.issue_type || 'vehicle';
        const reviewStatus = photo.public_review_status === 'pending' ? 'pending' : 'approved';
        const groupKind = reviewStatus === 'pending'
            ? (isAdmin ? 'admin-pending' : 'public-pending') : 'approved';
        let group = groups.find(candidate =>
            candidate.issueType === issueType
            && candidate.groupKind === groupKind
            && distance(candidate.lat, candidate.lon, lat, lon) <= RADIUS_M
        );
        if (!group) {
            group = { lat, lon, issueType, reviewStatus, groupKind, photos: [] };
            groups.push(group);
        }
        group.photos.push(photo);
        const count = group.photos.length;
        group.lat = ((group.lat * (count - 1)) + lat) / count;
        group.lon = ((group.lon * (count - 1)) + lon) / count;
    }
    return groups;
}

function referenceVehicleGroups(photos) {
    const groups = [];
    const nearest = (lat, lon) => {
        let best = null;
        for (const group of groups) {
            const metres = distance(group.lat, group.lon, lat, lon);
            if (metres <= RADIUS_M && (!best || metres < best.metres)) best = { group, metres };
        }
        return best?.group || null;
    };
    for (const photo of photos) {
        if (photo.issue_type !== 'vehicle' || photo.public_review_status !== 'approved') continue;
        const lat = Number(photo.lat);
        const lon = Number(photo.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
        let group = nearest(lat, lon);
        if (!group) {
            group = { lat, lon, photos: [], pendingPhotos: [] };
            groups.push(group);
        }
        group.photos.push(photo);
        const count = group.photos.length;
        group.lat = ((group.lat * (count - 1)) + lat) / count;
        group.lon = ((group.lon * (count - 1)) + lon) / count;
    }
    for (const photo of photos) {
        if (photo.issue_type !== 'vehicle' || photo.public_review_status !== 'pending') continue;
        const lat = Number(photo.lat);
        const lon = Number(photo.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
        nearest(lat, lon)?.pendingPhotos.push(photo);
    }
    return groups;
}

function makeContext(isAdmin = false) {
    const context = vm.createContext({
        URLSearchParams,
        window: { location: { search: '' } },
        adminAuthenticated: isAdmin,
        pendingFieldPhotoLayerVisible: true,
        PUBLIC_LAYER_KEYS: { fieldPhotoPending: 'field_photo_pending', vehicles: 'vehicles' },
        FIELD_PHOTO_ISSUE_TYPE_VEHICLE: 'vehicle',
        FIELD_PHOTO_ISSUE_TYPES: new Set(['vehicle', 'infrastructure', 'smoke']),
        FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN: 'unknown',
        FIELD_PHOTO_GROUP_RADIUS_M: RADIUS_M,
        METERS_PER_DEGREE_LAT: METRES_PER_LATITUDE_DEGREE,
        VEHICLE_LONG_STANDING_DAY_OPTIONS: [30, 90],
        loadVehicleStandingFilterDays() { return 0; },
        publicLayerAllowed() { return true; },
    });
    for (const path of ['web/map_helpers.js', 'web/app/vehicle_layer.js', 'web/app/field_photos.js']) {
        vm.runInContext(readFileSync(join(ROOT, path), 'utf8'), context, { filename: path });
    }
    return context;
}

function summarize(groups) {
    return JSON.parse(JSON.stringify(groups.map(group => ({
        lat: group.lat,
        lon: group.lon,
        issueType: group.issueType,
        groupKind: group.groupKind,
        ids: group.photos.map(photo => photo.id),
        pendingIds: (group.pendingPhotos || []).map(photo => photo.id),
    }))));
}

function photo(id, lat, lon, issue_type = 'vehicle', public_review_status = 'approved') {
    return { id: String(id), lat, lon, issue_type, public_review_status };
}

function seededRandom(seed) {
    let x = seed >>> 0;
    return () => {
        x = (1664525 * x + 1013904223) >>> 0;
        return x / 2 ** 32;
    };
}

test('spatial grouping is identical to the first matching legacy group and centroid drift', () => {
    const photos = [
        photo(1, 51.100000, 17.400000, 'smoke'),
        photo(2, 51.100005, 17.400000, 'smoke'),
        photo(3, 51.100010, 17.400000, 'smoke'),
        photo(4, 51.100000, 17.400000, 'infrastructure'),
        photo(5, 51.100000, 17.400000, 'smoke', 'pending'),
        photo(6, 51.100000, 17.400000, 'smoke'),
    ];
    const context = makeContext();
    context.photos = photos;
    const grouped = vm.runInContext('groupFieldPhotos(photos)', context);
    assert.deepEqual(summarize(grouped), summarize(referenceFieldGroups(photos)));
});

test('indexed vehicle nearest-match and pending attachments preserve legacy order', () => {
    const photos = [
        photo(1, 51.1, 17.4),
        photo(2, 51.100018, 17.4),
        photo(3, 51.100009, 17.4),
        photo(4, 51.100011, 17.4, 'vehicle', 'pending'),
        photo(5, 51.100002, 17.4, 'vehicle', 'pending'),
        photo(6, 51.1, 17.4, 'smoke'),
    ];
    const context = makeContext();
    context.photos = photos;
    const grouped = vm.runInContext('buildVehicleGroups(photos)', context);
    assert.deepEqual(summarize(grouped), summarize(referenceVehicleGroups(photos)));
});

test('index remains exact across polar fallback, invalid ranges and raw dateline separation', () => {
    const photos = [
        photo(1, 83.999999, 17), photo(2, 84.000001, 17),
        photo(3, 89.999999, 17), photo(4, 89.999999, 19),
        photo(5, -89.999999, -1), photo(6, -89.999999, -2),
        photo(7, 51.1, 179.999999), photo(8, 51.1, -179.999999),
        photo(9, 51.1, 181), photo(10, 51.1, 181.000002),
        photo(11, 95, 17), photo(12, 95, 17.000001),
        photo(13, NaN, 17), photo(14, 51.1, Infinity),
    ];
    const context = makeContext();
    context.photos = photos;
    assert.deepEqual(summarize(vm.runInContext('groupFieldPhotos(photos)', context)), summarize(referenceFieldGroups(photos)));
    assert.deepEqual(summarize(vm.runInContext('buildVehicleGroups(photos)', context)), summarize(referenceVehicleGroups(photos)));
});

test('seeded mixed national-scale locations keep both grouping contracts', () => {
    for (const seed of [1, 23, 112358]) {
        const random = seededRandom(seed);
        const photos = [];
        for (let idx = 0; idx < 420; idx++) {
            const cluster = Math.floor(random() * 65);
            const lat = 49.0 + (cluster % 13) * 0.22 + (random() - 0.5) * 0.000025;
            const lon = 14.0 + Math.floor(cluster / 13) * 0.45 + (random() - 0.5) * 0.000025;
            const issue = ['vehicle', 'smoke', 'infrastructure'][Math.floor(random() * 3)];
            const review = random() < 0.2 ? 'pending' : 'approved';
            photos.push(photo(idx, lat, lon, issue, review));
        }
        const context = makeContext(seed % 2 === 0);
        context.photos = photos;
        assert.deepEqual(
            summarize(vm.runInContext('groupFieldPhotos(photos)', context)),
            summarize(referenceFieldGroups(photos, seed % 2 === 0)),
        );
        assert.deepEqual(
            summarize(vm.runInContext('buildVehicleGroups(photos)', context)),
            summarize(referenceVehicleGroups(photos)),
        );
    }
});

test('sparse groups avoid quadratic distance calculations', () => {
    const context = makeContext();
    let calls = 0;
    const oldDistance = context.metersBetween;
    context.metersBetween = (...args) => {
        calls++;
        return oldDistance(...args);
    };
    context.photos = Array.from({ length: 1600 }, (_, idx) =>
        photo(idx, 49.0 + Math.floor(idx / 40) * 0.02, 14 + (idx % 40) * 0.02, 'smoke'),
    );
    const groups = vm.runInContext('groupFieldPhotos(photos)', context);
    assert.equal(groups.length, 1600);
    assert.ok(calls < 1600 * 5, `expected spatial candidate pruning, got ${calls} comparisons`);
});
