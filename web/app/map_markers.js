function countBadge(count, className) {
    const numericCount = Math.max(0, Math.floor(Number(count) || 0));
    if (numericCount <= 0) return '';
    return `<span class="map-pin-count ${className}">${numericCount}</span>`;
}

function vehicleIcon(
    photoCount = 0,
    reviewStatus = 'approved',
    insuranceStatus = FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN,
    isLongStanding = false,
    pendingCount = 0,
    resolutionStatus = FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_ACTIVE
) {
    const numericCount = Math.max(0, Math.floor(Number(photoCount) || 0));
    const numericPendingCount = Math.max(0, Math.floor(Number(pendingCount) || 0));
    const badge = countBadge(numericCount, 'vehicle-pin-count');
    const safeStatus = reviewStatus === 'pending' || reviewStatus === 'rejected' ? reviewStatus : 'approved';
    const safeInsuranceStatus = FIELD_PHOTO_VEHICLE_INSURANCE_STATUSES.has(insuranceStatus)
        ? insuranceStatus
        : FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN;
    const safeResolutionStatus = FIELD_PHOTO_VEHICLE_RESOLUTION_STATUSES.has(resolutionStatus)
        ? resolutionStatus
        : FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_ACTIVE;
    const classes = ['vehicle-pin', `vehicle-pin--${safeStatus}`];
    if (numericCount > 0) classes.push('vehicle-pin--with-photos');
    if (safeStatus === 'approved') classes.push(`vehicle-pin--insurance-${safeInsuranceStatus}`);
    if (safeStatus === 'approved' && safeResolutionStatus === FIELD_PHOTO_VEHICLE_RESOLUTION_STATUS_REMOVED) {
        classes.push('vehicle-pin--removed');
    }
    if (safeStatus === 'approved' && isLongStanding) classes.push('vehicle-pin--long-standing');
    if (safeStatus === 'approved' && numericPendingCount > 0) classes.push('vehicle-pin--mixed-pending');
    const className = classes.join(' ');
    const pendingIndicator = numericPendingCount > 0
        ? '<span class="vehicle-pin-pending-indicator" aria-hidden="true"></span>'
        : '';
    const html = `<div class="${className}"><span class="vehicle-pin-glyph" aria-hidden="true"></span>${pendingIndicator}${badge}</div>`;
    return L.divIcon({ html, className: 'map-pin-icon', iconSize: [34,34], iconAnchor:[17,34] });
}

function fieldPhotoIcon(count = 1, issueType = FIELD_PHOTO_ISSUE_TYPE_VEHICLE) {
    const photoCount = Math.max(1, Number(count) || 1);
    const badge = photoCount > 1 ? countBadge(photoCount, 'field-photo-pin-count') : '';
    const safeIssueType = FIELD_PHOTO_ISSUE_TYPES.has(issueType) ? issueType : FIELD_PHOTO_ISSUE_TYPE_VEHICLE;
    const html = `<div class="field-photo-pin field-photo-pin--${safeIssueType}">${badge}</div>`;
    return L.divIcon({ html, className: 'map-pin-icon', iconSize: [34,34], iconAnchor:[17,34] });
}

function pendingSubmissionIcon() {
    const html = '<div class="pending-submission-pin"></div>';
    return L.divIcon({ html, className: 'map-pin-icon', iconSize: [34,34], iconAnchor:[17,34] });
}

function pendingFieldPhotoPopup(group) {
    const lat = Number(group.lat);
    const lon = Number(group.lon);
    const encodedPhotoIds = encodedFieldPhotoIdsForGroup(group);
    const ownerButton = encodedPhotoIds
        ? mapPopupIconAction(
            'map-popup-action--primary',
            t('fieldPhoto.editMyPhoto'),
            `openFieldPhotoOwnerEditor('${encodedPhotoIds}')`,
            'M11 17h2v-6h-2v6zm0-8h2V7h-2v2zm1-7a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 18a8 8 0 1 1 0-16 8 8 0 0 1 0 16z'
        )
        : '';
    return mapPopup(`
            ${popupHeader(t('pendingSubmission.photoTitle'), [
                popupElapsedAgeBadge(group.photos),
                popupHeaderBadge(t('pendingSubmission.status'), 'status'),
            ])}
            ${popupMeta([
                t('fieldPhoto.pendingPublicHint'),
                t('pendingSubmission.coords', { lat: lat.toFixed(6), lon: lon.toFixed(6) }),
            ])}
            ${popupActions([ownerButton])}
    `, 'map-popup--pending-submission');
}

// Aggregate markers deliberately use a different symbol from a vehicle pin.
function overviewPhotoIcon(count) {
    const html = `<div class="map-overview-cluster">${Math.floor(count)}</div>`;
    return L.divIcon({ html, className: 'map-pin-icon', iconSize: [46, 46], iconAnchor: [23, 23] });
}
