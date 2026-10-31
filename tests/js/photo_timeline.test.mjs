import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const popups = readFileSync('web/app/popups.js', 'utf8');
const fieldPopups = readFileSync('web/app/field_photo_popups.js', 'utf8');
const context = vm.createContext({
    Date,
    t(key, params = {}) {
        const labels = {
            'modal.photoPreview.photoDated': params.date,
            'modal.photoPreview.photoAdded': `Dodano ${params.date}`,
            'modal.photoPreview.addedBadge': `dod. ${params.date}`,
            'modal.photoPreview.photoNumber': `Zdjęcie ${params.n}`,
            'popup.agePrefix': `od ${params.age}`,
            'popup.ageMonths': `${params.n} mies.`,
            'popup.ageDays': `${params.n} dni`,
            'popup.ageHours': `${params.n} h`,
        };
        return labels[key] || key;
    },
});
vm.runInContext(popups, context, { filename: 'popups.js' });
vm.runInContext(fieldPopups, context, { filename: 'field_photo_popups.js' });
const run = expression => vm.runInContext(expression, context);

test('new photo and unknown OC never reset the earliest captured observation', () => {
    const photos = [
        { captured_at: '2026-06-05T20:31:17', created_at: '2026-06-06T01:22:14Z', submitted_at: null, vehicle_insurance_status: 'unknown' },
        { captured_at: '2026-06-05T20:31:32', created_at: '2026-06-06T01:22:15Z', submitted_at: null, vehicle_insurance_status: 'unknown' },
        { captured_at: '2026-10-30T21:16:56', created_at: '2026-10-30T20:17:21Z', submitted_at: '2026-10-30T20:17:26Z', vehicle_insurance_status: 'unknown' },
    ];
    context.photos = photos;
    context.nowMs = Date.parse('2026-10-31T20:00:00Z');
    assert.equal(run('fieldPhotoGroupStartTimestamp(photos, nowMs)'), Date.parse('2026-06-05T20:31:17'));
    const badge = run('popupElapsedAgeText(photos, nowMs)');
    assert.equal(badge, 'od 4 mies.');
    assert.ok(run('fieldPhotoGroupStartTimestamp(photos, nowMs)') < Date.parse('2026-10-30T20:17:26Z'));
});

test('each photo uses its own capture date, falling back to upload only when necessary', () => {
    context.photos = [
        { captured_at: null, created_at: '2026-06-06T12:00:00Z', submitted_at: null },
        { captured_at: '2026-10-30T18:00:00', created_at: '2026-10-31T12:00:00Z', submitted_at: '2026-10-31T12:10:00Z' },
    ];
    context.nowMs = Date.parse('2026-11-01T10:00:00Z');
    assert.equal(run('fieldPhotoGroupStartTimestamp(photos, nowMs)'), Date.parse('2026-06-06T12:00:00Z'));
    context.photos = [{ captured_at: null, created_at: null, submitted_at: '2026-06-05T12:00:00Z' }];
    assert.equal(run('fieldPhotoGroupStartTimestamp(photos, nowMs)'), Date.parse('2026-06-05T12:00:00Z'));
});

test('invalid and future photo timestamps are rejected, without inventing observation age', () => {
    context.photos = [
        { captured_at: '2099-12-31T12:00:00Z', created_at: '2026-06-10T12:00:00Z', submitted_at: '2026-10-30T12:00:00Z' },
        { captured_at: 'not-a-date', created_at: '', submitted_at: '' },
    ];
    context.nowMs = Date.parse('2026-10-31T12:00:00Z');
    assert.equal(run('fieldPhotoGroupStartTimestamp(photos, nowMs)'), Date.parse('2026-06-10T12:00:00Z'));
    context.photos = [{ captured_at: 'bad', created_at: null, submitted_at: null }];
    assert.equal(run('fieldPhotoGroupStartTimestamp(photos, nowMs)'), null);
});

test('gallery displays a real capture date when present', () => {
    context.photo = {
        captured_at: '2026-06-05T20:31:17',
        created_at: '2026-06-06T01:22:14Z',
        public_thumb: '/thumb.jpg',
    };
    const result = run('photoPreviewDisplay(fieldPhotoPreview(photo))');
    assert.equal(result.badge, '05.06.2026');
    assert.equal(result.name.startsWith('Dodano'), false);
});

test('photos lacking capture EXIF show clearly distinguished upload dates', () => {
    context.photo = { captured_at: null, created_at: '2026-06-06T12:00:00Z', public_thumb: '/thumb.jpg' };
    const result = run('photoPreviewDisplay(fieldPhotoPreview(photo))');
    assert.match(result.name, /^Dodano /);
    assert.match(result.badge, /^dod\. /);
    assert.notEqual(result.name, 'Zdjęcie 1');

    context.photo = { captured_at: null, created_at: null, submitted_at: '2026-06-06T12:00:00Z', public_thumb: '/thumb.jpg' };
    assert.match(run('photoPreviewDisplay(fieldPhotoPreview(photo)).name'), /^Dodano /);
});

test('when no trustworthy photo timestamp exists, UI keeps the neutral photo label', () => {
    context.photo = { captured_at: null, created_at: null, submitted_at: null, public_thumb: '/thumb.jpg' };
    const result = run('photoPreviewDisplay(fieldPhotoPreview(photo, 3), 3)');
    assert.equal(result.name, 'Zdjęcie 4');
});
