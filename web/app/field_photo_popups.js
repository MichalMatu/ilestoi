function cacheBustedUrl(url, ts = Date.now()) {
    if (!url) return '';
    const separator = String(url).includes('?') ? '&' : '?';
    return `${url}${separator}ts=${ts}`;
}

function fieldPhotoPreview(photo, index = 0, ts = Date.now()) {
    const publicThumb = photo?.public_thumb || '';
    if (!publicThumb) return null;
    const publicUrl = photo.public_image || publicThumb;
    const capturedAt = popupTimestampMs(photo?.captured_at) === null ? '' : String(photo.captured_at);
    const addedAt = popupTimestampMs(photo?.created_at) !== null
        ? String(photo.created_at)
        : (popupTimestampMs(photo?.submitted_at) !== null ? String(photo.submitted_at) : '');
    return {
        source: 'field',
        label: capturedAt || addedAt || String(index + 1),
        date_kind: capturedAt ? 'captured' : (addedAt ? 'added' : 'unknown'),
        public_image: cacheBustedUrl(publicUrl, ts),
        public_thumb: cacheBustedUrl(publicThumb, ts),
    };
}

function fieldPhotoGroupPreviews(photos) {
    const ts = Date.now();
    return (photos || [])
        .map((photo, index) => fieldPhotoPreview(photo, index, ts))
        .filter(Boolean);
}

function fieldPhotoGroupLinks(group, photos) {
    const firstPhoto = photos[0] || {};
    const links = firstPhoto.links || group.links || {};
    return popupLinks([
        popupCompactLink(links.street_view, t('popup.streetView'), t('popup.streetView')),
        popupCompactLink(links.google_maps_satellite, t('popup.gmapsSat'), t('popup.gmapsSat')),
    ]);
}

function encodedFieldPhotoIdsForGroup(group) {
    return encodeURIComponent(JSON.stringify(photoIdsForGroup(group)));
}

function fieldPhotoGroupActions(group) {
    const lat = Number(group.lat);
    const lon = Number(group.lon);
    const encodedPhotoIds = encodedFieldPhotoIdsForGroup(group);
    const coordinatesOk = Number.isFinite(lat) && Number.isFinite(lon) && encodedPhotoIds;
    const reportPdfsAllowed = publicFeatureAllowed(PUBLIC_FEATURE_KEYS.reportPdfs);
    const issueType = FIELD_PHOTO_ISSUE_TYPES.has(group.issueType) ? group.issueType : FIELD_PHOTO_ISSUE_TYPE_VEHICLE;
    const canCreateVehicleReport = coordinatesOk && reportPdfsAllowed && issueType === FIELD_PHOTO_ISSUE_TYPE_VEHICLE;
    const canAddFieldPhotosHere = coordinatesOk
        && publicFeatureAllowed(PUBLIC_FEATURE_KEYS.photoUploads)
        && fieldPhotoIssueAllowed(issueType);
    const ownerButton = encodedPhotoIds
        ? mapPopupIconAction(
            'map-popup-action--primary',
            t('fieldPhoto.editMyPhoto'),
            `openFieldPhotoOwnerEditor('${encodedPhotoIds}')`,
            'M11 17h2v-6h-2v6zm0-8h2V7h-2v2zm1-7a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16z'
        )
        : '';
    const reportButton = canCreateVehicleReport
        ? mapPopupIconAction(
            'map-popup-action--report',
            t('fieldPhoto.reportPdf'),
            `openFieldPhotoGroupReport(${lat}, ${lon}, '${encodedPhotoIds}', this)`,
            'M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm1 7V3.5L18.5 9H15zM8 13h8v2H8v-2zm0 4h8v2H8v-2z'
        )
        : '';
    const photoButton = canAddFieldPhotosHere
        ? mapPopupIconAction(
            'map-popup-action--primary',
            t('fieldPhoto.addPhotosHere'),
            `openFieldPhotoGroupPhotoUpload(${lat}, ${lon}, '${encodedPhotoIds}', '${issueType}', this)`,
            'M5 7h2.8L9.4 5h5.2l1.6 2H19c1.1 0 2 .9 2 2v10c0 1.1-.9 2-2 2H5c-1.1 0-2-.9-2-2V9c0-1.1.9-2 2-2zm7 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm5-5h-2v2h-2v2h2v2h2v-2h2v-2h-2v-2z'
        )
        : '';
    const reviewButton = adminAuthenticated && encodedPhotoIds
        ? mapPopupIconAction(
            'map-popup-action--primary',
            t('fieldPhoto.reviewPhotos'),
            `openPhotoReviewForFieldPhotoGroup('${encodedPhotoIds}')`,
            'M4 5h16v14H4V5zm2 2v10h12V7H6zm2 8h8l-2.5-3.2-1.8 2.2-1.3-1.5L8 15zm10-9.5 1.1-1.1 1.5 1.5-1.1 1.1-1.5-1.5zm-6.5 6.5L18 5.5 19.5 7 13 13.5H11.5V12z'
        )
        : '';
    const deleteButton = adminAuthenticated && encodedPhotoIds
        ? mapPopupIconAction(
            'map-popup-action--danger',
            t('fieldPhoto.delete'),
            `deleteFieldPhotoGroup('${encodedPhotoIds}', this)`,
            'M9 3v1H4v2h16V4h-5V3H9zm-3 5l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13H6zm4 3h1v9h-1v-9zm3 0h1v9h-1v-9z'
        )
        : '';
    return popupActions([ownerButton, reportButton, photoButton, reviewButton, deleteButton]);
}

function fieldPhotoPendingReviewPopup(group) {
    const photos = group.photos || [];
    const lat = Number(group.lat);
    const lon = Number(group.lon);
    const encodedPhotoIds = encodedFieldPhotoIdsForGroup(group);
    const issueLabel = fieldPhotoIssueLabel(group.issueType);
    const title = photos.length > 1
        ? t('fieldPhoto.pendingReview.groupTitle', { n: photos.length })
        : t('fieldPhoto.pendingReview.title');
    const reviewButton = encodedPhotoIds
        ? mapPopupIconAction(
            'map-popup-action--primary',
            t('fieldPhoto.reviewPhotos'),
            `openPhotoReviewForFieldPhotoGroup('${encodedPhotoIds}')`,
            'M4 5h16v14H4V5zm2 2v10h12V7H6zm2 8h8l-2.5-3.2-1.8 2.2-1.3-1.5L8 15zm10-9.5 1.1-1.1 1.5 1.5-1.1 1.1-1.5-1.5zm-6.5 6.5L18 5.5 19.5 7 13 13.5H11.5V12z'
        )
        : '';
    const rejectButton = encodedPhotoIds
        ? mapPopupIconAction(
            'map-popup-action--danger',
            t('modal.photoReview.reject'),
            `rejectFieldPhotoGroup('${encodedPhotoIds}', this)`,
            'M18.3 5.7 16.9 4.3 12 9.2 7.1 4.3 5.7 5.7 10.6 10.6 5.7 15.5 7.1 16.9 12 12 16.9 16.9 18.3 15.5 13.4 10.6 18.3 5.7z'
        )
        : '';
    const deleteButton = encodedPhotoIds
        ? mapPopupIconAction(
            'map-popup-action--danger',
            t('fieldPhoto.delete'),
            `deleteFieldPhotoGroup('${encodedPhotoIds}', this)`,
            'M9 3v1H4v2h16V4h-5V3H9zm-3 5l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13H6zm4 3h1v9h-1v-9zm3 0h1v9h-1v-9z'
        )
        : '';
    return mapPopup(`
            ${popupHeader(title, [popupElapsedAgeBadge(photos), popupHeaderBadge(t('pendingSubmission.status'), 'status')])}
            ${popupMeta([
                issueLabel,
                t('fieldPhoto.pendingReview.hint'),
                t('pendingSubmission.coords', { lat: lat.toFixed(6), lon: lon.toFixed(6) }),
            ])}
            ${popupActions([reviewButton, rejectButton, deleteButton])}
    `, 'map-popup--field-photo-pending-review');
}

function fieldPhotoGroupPopup(group) {
    const reviewStatus = fieldPhotoGroupReviewStatus(group);
    if (reviewStatus === 'pending') {
        return adminAuthenticated
            ? fieldPhotoPendingReviewPopup(group)
            : pendingFieldPhotoPopup(group);
    }
    const photos = group.photos || [];
    const isGroup = photos.length > 1;
    const issueType = group.issueType || fieldPhotoIssueType(photos[0]);
    const issueLabel = fieldPhotoIssueLabel(issueType);
    const title = isGroup
        ? t('fieldPhoto.popup.groupTitleWithType', { type: issueLabel, n: photos.length })
        : issueLabel;
    const previews = fieldPhotoGroupPreviews(photos);
    return mapPopup(`
            ${popupHeader(title, popupElapsedAgeBadge(photos))}
            ${popupPhotoSection('', previews, { className: 'map-popup-photo-grid--field', total: photos.length, showHeader: false })}
            ${fieldPhotoGroupLinks(group, photos)}
            ${fieldPhotoGroupActions({ ...group, issueType })}
    `, mapPopupMediaModifiers(previews, isGroup ? 'map-popup--field-photo-group' : 'map-popup--field-photo'));
}

function fieldPhotoPopup(photo) {
    return fieldPhotoGroupPopup({ photos: [photo] });
}
