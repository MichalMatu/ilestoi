const MAP_POPUP_LEAFLET_OPTIONS = Object.freeze({ maxWidth: 540 });
const MAP_POPUP_AGE_MIN_TIMESTAMP_MS = Date.UTC(2000, 0, 1);
const MAP_POPUP_AGE_FUTURE_GRACE_MS = 5 * 60 * 1000;

function mapPopupOptions() {
    return { ...MAP_POPUP_LEAFLET_OPTIONS };
}

function mapPopupClasses(modifiers = []) {
    const modifierList = Array.isArray(modifiers) ? modifiers : [modifiers];
    const classes = ['map-popup'];
    modifierList.forEach(modifier => {
        String(modifier || '').trim().split(/\s+/).forEach(className => {
            if (className) classes.push(className);
        });
    });
    return classes.join(' ');
}

function mapPopup(content, modifiers = []) {
    return `<div class="${escapeHtml(mapPopupClasses(modifiers))}">${content}</div>`;
}

function popupCompactLink(href, label, title) {
    if (!href) return '';
    return `<a href="${escapeHtml(href)}" target="_blank" rel="noopener" title="${escapeHtml(title || label)}">${escapeHtml(label)}</a>`;
}

function popupHeaderBadge(label, variant = '', options = {}) {
    const text = String(label || '').trim();
    if (!text) return null;
    return {
        label: text,
        variant: String(variant || '').replace(/[^A-Za-z0-9_-]/g, ''),
        href: String(options.href || '').trim(),
        title: String(options.title || '').trim(),
        ariaLabel: String(options.ariaLabel || '').trim(),
    };
}

function popupHeaderBadgeHtml(value) {
    const badge = value && typeof value === 'object'
        ? popupHeaderBadge(value.label, value.variant, value)
        : popupHeaderBadge(value);
    if (!badge) return '';
    const variantClass = badge.variant ? ` map-popup-head-value--${badge.variant}` : '';
    const title = badge.title || '';
    const ariaLabel = badge.ariaLabel || title;
    if (badge.href) {
        return `<a class="map-popup-head-value${variantClass}" href="${escapeHtml(badge.href)}" target="_blank" rel="noopener" title="${escapeHtml(title || badge.label)}" aria-label="${escapeHtml(ariaLabel || badge.label)}">${escapeHtml(badge.label)}</a>`;
    }
    const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
    const ariaAttr = ariaLabel ? ` aria-label="${escapeHtml(ariaLabel)}"` : '';
    return `<span class="map-popup-head-value${variantClass}"${titleAttr}${ariaAttr}>${escapeHtml(badge.label)}</span>`;
}

function popupHeader(title, value = '') {
    const values = (Array.isArray(value) ? value : [value])
        .map(item => popupHeaderBadgeHtml(item))
        .filter(Boolean);
    const valueHtml = values.length ? `<span class="map-popup-head-values">${values.join('')}</span>` : '';
    return `
        <div class="map-popup-head">
            <strong>${escapeHtml(title)}</strong>
            ${valueHtml}
        </div>
    `;
}

function popupMeta(parts) {
    const items = (parts || []).filter(part => part !== undefined && part !== null && String(part).trim() !== '');
    if (!items.length) return '';
    return `<div class="map-popup-meta">${items.map(part => `<span>${escapeHtml(part)}</span>`).join('')}</div>`;
}

function popupLinks(links) {
    const items = (links || []).filter(Boolean);
    if (!items.length) return '';
    return `
        <div class="map-popup-links">
            ${items.map(link => `<span class="map-popup-link-item">${link}</span>`).join('')}
        </div>
    `;
}

function popupActions(actions) {
    const html = (actions || []).filter(Boolean).join('');
    return html ? `<div class="map-popup-actions">${html}</div>` : '';
}

function humanDatePartsFromPhotoText(value) {
    const text = String(value || '').trim();
    const match = text.match(/(20\d{2})[-_:.]?([01]\d)[-_:.]?([0-3]\d)(?:[T _.-]?([0-2]\d)[:_.-]?([0-5]\d))?/);
    if (!match) return null;
    const [, year, month, day, hour, minute] = match;
    const date = `${day}.${month}.${year}`;
    return {
        date,
        dateTime: `${date}${hour && minute ? `, ${hour}:${minute}` : ''}`,
    };
}

function popupTimestampMs(value, nowMs = Date.now()) {
    const text = String(value || '').trim();
    // Date.parse accepts numbers such as "4" as dates in 2001. Only accept actual
    // ISO calendar dates from field-photo capture/upload/submission metadata.
    const match = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?)?$/);
    if (!match) return null;
    const [, year, month, day] = match.map(Number);
    const calendar = new Date(Date.UTC(year, month - 1, day));
    if (calendar.getUTCFullYear() !== year || calendar.getUTCMonth() !== month - 1
        || calendar.getUTCDate() !== day) return null;
    const timestampMs = Date.parse(text);
    if (!Number.isFinite(timestampMs)) return null;
    if (timestampMs < MAP_POPUP_AGE_MIN_TIMESTAMP_MS || timestampMs > nowMs + MAP_POPUP_AGE_FUTURE_GRACE_MS) {
        return null;
    }
    return timestampMs;
}

function fieldPhotoObservationTimestamp(photo, nowMs = Date.now()) {
    // The capture date describes the observation; upload and submission describe processing.
    // Choose a fallback per photo so one recent submission cannot hide older evidence.
    return popupTimestampMs(photo?.captured_at, nowMs)
        ?? popupTimestampMs(photo?.created_at, nowMs)
        ?? popupTimestampMs(photo?.submitted_at, nowMs);
}

function fieldPhotoGroupStartTimestamp(photos, nowMs = Date.now()) {
    const timestamps = (Array.isArray(photos) ? photos : [])
        .map(photo => fieldPhotoObservationTimestamp(photo, nowMs))
        .filter(timestampMs => Number.isFinite(timestampMs));
    return timestamps.length ? Math.min(...timestamps) : null;
}

function popupElapsedUnitText(elapsedMs) {
    const elapsedMinutes = Math.max(0, Math.floor(elapsedMs / 60000));
    if (elapsedMinutes < 1) return t('popup.ageNow');
    if (elapsedMinutes < 60) return t('popup.ageMinutes', { n: elapsedMinutes });
    const elapsedHours = Math.floor(elapsedMinutes / 60);
    if (elapsedHours < 24) return t('popup.ageHours', { n: elapsedHours });
    const elapsedDays = Math.floor(elapsedHours / 24);
    if (elapsedDays < 60) return t('popup.ageDays', { n: elapsedDays });
    const elapsedMonths = Math.floor(elapsedDays / 30);
    if (elapsedMonths < 24) return t('popup.ageMonths', { n: Math.max(1, elapsedMonths) });
    return t('popup.ageYears', { n: Math.max(1, Math.floor(elapsedDays / 365)) });
}

function popupElapsedAgeText(photos, nowMs = Date.now()) {
    const startTimestampMs = fieldPhotoGroupStartTimestamp(photos, nowMs);
    if (!Number.isFinite(startTimestampMs)) return '';
    return t('popup.agePrefix', {
        age: popupElapsedUnitText(Math.max(0, nowMs - startTimestampMs)),
    });
}

function popupElapsedAgeTitle(photos, nowMs = Date.now()) {
    const startTimestampMs = fieldPhotoGroupStartTimestamp(photos, nowMs);
    if (!Number.isFinite(startTimestampMs)) return '';
    return t('popup.ageTitle', { date: humanDateTimeText(new Date(startTimestampMs).toISOString()) });
}

function popupElapsedAgeBadge(photos, nowMs = Date.now()) {
    return popupHeaderBadge(popupElapsedAgeText(photos, nowMs), 'age', {
        title: popupElapsedAgeTitle(photos, nowMs),
    });
}

function humanNameFromFilename(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const base = raw.split(/[\\/]/).pop().replace(/\.[A-Za-z0-9]{1,5}$/, '');
    const cleaned = base.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim();
    if (!cleaned || /^\d+$/.test(cleaned)) return '';
    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function humanDateTimeText(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    const timestampMs = Date.parse(text);
    if (!Number.isFinite(timestampMs)) return text.replace('T', ' ').replace(/Z$/, '');
    const date = new Date(timestampMs);
    const pad = number => String(number).padStart(2, '0');
    return [
        `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`,
        `${pad(date.getHours())}:${pad(date.getMinutes())}`,
    ].join(' ');
}

function humanDateText(value) {
    const dateTime = humanDateTimeText(value);
    return dateTime.split(' ')[0] || dateTime;
}

function fieldPhotoLocalDateParts(value) {
    const timestampMs = popupTimestampMs(value);
    if (!Number.isFinite(timestampMs)) return null;
    const date = new Date(timestampMs);
    const pad = number => String(number).padStart(2, '0');
    const text = `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()}`;
    return { date: text, dateTime: `${text}, ${pad(date.getHours())}:${pad(date.getMinutes())}` };
}

function photoPreviewDisplay(photo, index = 0) {
    const source = String(photo?.source || '');
    const rawLabel = String(photo?.label || '').trim();
    const detail = rawLabel;
    const year = rawLabel.match(/^(?:19|20)\d{2}$/)?.[0] || '';
    if ((source === 'evidence' || source === 'inspect') && year) {
        return {
            name: t('modal.photoPreview.mapCropYear', { year }),
            badge: year,
            detail,
        };
    }
    const humanDate = source === 'field'
        ? fieldPhotoLocalDateParts(rawLabel)
        : humanDatePartsFromPhotoText(rawLabel);
    if (humanDate) {
        const addedDate = source === 'field' && photo?.date_kind === 'added';
        return {
            name: t(addedDate ? 'modal.photoPreview.photoAdded' : 'modal.photoPreview.photoDated', { date: humanDate.dateTime }),
            badge: addedDate ? t('modal.photoPreview.addedBadge', { date: humanDate.date }) : humanDate.date,
            detail,
        };
    }
    const humanName = humanNameFromFilename(rawLabel);
    return {
        name: humanName || t('modal.photoPreview.photoNumber', { n: index + 1 }),
        detail,
    };
}

function photoPreviewGalleryItems(previews) {
    return Array.isArray(previews)
        ? previews.filter(photo => photo && photo.public_thumb).map((photo, index) => {
            const display = photoPreviewDisplay(photo, index);
            return {
                url: String(photo.public_image || photo.public_thumb || ''),
                thumb: String(photo.public_thumb || ''),
                title: String(display.name || ''),
                badge: String(display.badge || display.name || ''),
                detail: String(display.detail || ''),
            };
        }).filter(item => item.url && item.thumb)
        : [];
}

function vehicleInsuranceStatus(value) {
    const status = String(value || FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN).trim();
    return FIELD_PHOTO_VEHICLE_INSURANCE_STATUSES.has(status)
        ? status
        : FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN;
}

function vehicleInsuranceStatusLabel(status) {
    return t(`fieldPhoto.vehicleInsurance.${vehicleInsuranceStatus(status)}`);
}

function vehicleInsuranceHeaderBadge(rawStatus, checkedAt = '') {
    if (!String(rawStatus || '').trim()) return null;
    const status = vehicleInsuranceStatus(rawStatus);
    const label = vehicleInsuranceStatusLabel(status);
    const checkedText = humanDateTimeText(checkedAt);
    const checkedDate = humanDateText(checkedAt);
    const badgeLabel = status === FIELD_PHOTO_VEHICLE_INSURANCE_STATUS_UNKNOWN
        ? t('fieldPhoto.vehicleInsurance.badge.unknown')
        : t(checkedDate ? 'fieldPhoto.vehicleInsurance.badge.checked' : 'fieldPhoto.vehicleInsurance.badge.checkedMissing', {
            date: checkedDate,
        });
    const title = checkedText
        ? t('fieldPhoto.vehicleInsurance.ufgCheckedTitle', { status: label, date: checkedText })
        : t('fieldPhoto.vehicleInsurance.ufgTitle', { status: label });
    return popupHeaderBadge(badgeLabel, `insurance-${status}`, {
        href: UFG_OC_CHECK_URL,
        title,
        ariaLabel: t('fieldPhoto.vehicleInsurance.ufgAria', { status: label }),
    });
}

function popupVisiblePhotoCount(previews, { max = MAP_POPUP_PREVIEW_MAX_IMAGES } = {}) {
    const maxItems = Number.isFinite(Number(max)) ? Math.max(0, Number(max)) : MAP_POPUP_PREVIEW_MAX_IMAGES;
    return Math.min(photoPreviewGalleryItems(previews).length, maxItems);
}

function popupPhotoCountToken(count) {
    const numericCount = Math.max(0, Math.floor(Number(count) || 0));
    return numericCount >= 5 ? 'many' : String(numericCount);
}

function mapPopupMediaModifiers(previews, modifiers = [], options = {}) {
    return [
        'map-popup--media',
        `map-popup--media-count-${popupPhotoCountToken(popupVisiblePhotoCount(previews, options))}`,
        ...(Array.isArray(modifiers) ? modifiers : [modifiers]).filter(Boolean),
    ];
}

function popupPhotoGrid(previews, { className = '', max = MAP_POPUP_PREVIEW_MAX_IMAGES } = {}) {
    const maxItems = Number.isFinite(Number(max)) ? Math.max(0, Number(max)) : MAP_POPUP_PREVIEW_MAX_IMAGES;
    const galleryItems = photoPreviewGalleryItems(previews);
    const photos = galleryItems.slice(0, maxItems);
    if (!photos.length) return '';
    const classAttr = [
        'map-popup-photo-grid',
        `map-popup-photo-grid--count-${popupPhotoCountToken(photos.length)}`,
        className,
    ].filter(Boolean).join(' ');
    const galleryAttr = escapeHtml(JSON.stringify(galleryItems.map(item => ({
        url: item.url,
        title: item.title,
        badge: item.badge,
        detail: item.detail,
    }))));
    return `
        <div class="${classAttr}" data-photo-gallery="${galleryAttr}">
            ${photos.map((photo, index) => {
                const thumbUrl = escapeHtml(photo.thumb || '');
                const publicUrl = escapeHtml(photo.url || '');
                const label = escapeHtml(photo.title || '');
                const badge = escapeHtml(photo.badge || photo.title || '');
                const detail = escapeHtml(photo.detail || '');
                return `
                    <button type="button" class="map-popup-photo" data-photo-preview-url="${publicUrl}" data-photo-preview-title="${label}" data-photo-preview-detail="${detail}" data-photo-gallery-index="${index}" title="${detail || label}" aria-label="${label || escapeHtml(t('modal.photoPreview.title'))}">
                        <img src="${thumbUrl}" loading="lazy" alt="">
                        ${badge ? `<span>${badge}</span>` : ''}
                    </button>
                `;
            }).join('')}
        </div>
    `;
}

let photoPreviewGallery = [];
let photoPreviewIndex = 0;

function renderPhotoPreviewModal() {
    const item = photoPreviewGallery[photoPreviewIndex] || null;
    if (!item?.url) return;
    const titleText = String(item.title || t('modal.photoPreview.title'));
    const detailText = String(item.detail || '');
    const titleEl = document.getElementById('photo-preview-title');
    const imageEl = document.getElementById('photo-preview-image');
    const downloadEl = document.getElementById('photo-preview-download');
    const detailEl = document.getElementById('photo-preview-detail');
    const counterEl = document.getElementById('photo-preview-counter');
    const prevButton = document.getElementById('photo-preview-prev');
    const nextButton = document.getElementById('photo-preview-next');
    if (titleEl) titleEl.textContent = titleText;
    if (imageEl) {
        imageEl.alt = titleText;
        imageEl.src = item.url;
    }
    if (downloadEl) {
        downloadEl.href = item.url;
        downloadEl.download = '';
    }
    if (detailEl) {
        detailEl.textContent = detailText;
        detailEl.hidden = !detailText || detailText === titleText;
    }
    if (counterEl) {
        counterEl.textContent = `${photoPreviewIndex + 1}/${photoPreviewGallery.length}`;
        counterEl.hidden = photoPreviewGallery.length <= 1;
    }
    [prevButton, nextButton].forEach(button => {
        if (button) button.disabled = photoPreviewGallery.length <= 1;
    });
}

function openPhotoPreviewModal(url, title = '', gallery = null, index = 0) {
    const fallbackUrl = String(url || '');
    const items = Array.isArray(gallery) && gallery.length
        ? gallery
        : [{ url: fallbackUrl, title: String(title || ''), detail: '' }];
    photoPreviewGallery = items.filter(item => item?.url);
    if (!photoPreviewGallery.length) return;
    photoPreviewIndex = Math.min(Math.max(0, Number(index) || 0), photoPreviewGallery.length - 1);
    renderPhotoPreviewModal();
    openModal('modal-photo-preview', { preserveOpen: true });
}

function movePhotoPreview(delta) {
    if (photoPreviewGallery.length <= 1) return;
    photoPreviewIndex = (photoPreviewIndex + delta + photoPreviewGallery.length) % photoPreviewGallery.length;
    renderPhotoPreviewModal();
}

function photoPreviewGalleryFromButton(activeButton) {
    const grid = activeButton.closest('.map-popup-photo-grid');
    if (grid?.dataset.photoGallery) {
        try {
            const items = JSON.parse(grid.dataset.photoGallery)
                .map(item => ({
                    url: String(item?.url || ''),
                    title: String(item?.title || ''),
                    detail: String(item?.detail || ''),
                }))
                .filter(item => item.url);
            if (items.length) {
                const rawIndex = Number(activeButton.dataset.photoGalleryIndex);
                const activeIndex = Number.isFinite(rawIndex)
                    ? Math.min(Math.max(0, rawIndex), items.length - 1)
                    : 0;
                return { items, activeIndex };
            }
        } catch (_) {}
    }
    const buttons = Array.from(grid?.querySelectorAll('[data-photo-preview-url]') || [activeButton]);
    const items = [];
    let activeIndex = 0;
    buttons.forEach(button => {
        const url = button.dataset.photoPreviewUrl || '';
        if (!url) return;
        if (button === activeButton) activeIndex = items.length;
        items.push({
            url,
            title: button.dataset.photoPreviewTitle || '',
            detail: button.dataset.photoPreviewDetail || '',
        });
    });
    return { items, activeIndex };
}

document.addEventListener('click', event => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest('[data-photo-preview-url]');
    if (!button) return;
    event.preventDefault();
    const { items, activeIndex } = photoPreviewGalleryFromButton(button);
    openPhotoPreviewModal(button.dataset.photoPreviewUrl, button.dataset.photoPreviewTitle, items, activeIndex);
});

document.addEventListener('keydown', event => {
    const modal = document.getElementById('modal-photo-preview');
    if (!modal || modal.hidden) return;
    if (event.key === 'ArrowLeft') {
        event.preventDefault();
        movePhotoPreview(-1);
    } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        movePhotoPreview(1);
    }
});

document.getElementById('modal-photo-preview')?.addEventListener('modalclose', () => {
    const imageEl = document.getElementById('photo-preview-image');
    if (imageEl) imageEl.removeAttribute('src');
    photoPreviewGallery = [];
    photoPreviewIndex = 0;
});

function popupPhotoSection(title, previews, options = {}) {
    const { total = null, showHeader = true, ...gridOptions } = options || {};
    const grid = popupPhotoGrid(previews, gridOptions);
    if (!grid) return '';
    const maxItems = Number.isFinite(Number(gridOptions.max))
        ? Math.max(0, Number(gridOptions.max))
        : MAP_POPUP_PREVIEW_MAX_IMAGES;
    const available = Array.isArray(previews)
        ? previews.filter(photo => photo && photo.public_thumb).length
        : 0;
    const visibleCount = Math.min(available, maxItems);
    const numericTotal = Number(total);
    const totalCount = Number.isFinite(numericTotal) && numericTotal > 0 ? numericTotal : available;
    const countText = totalCount > visibleCount ? `${visibleCount}/${totalCount}` : String(totalCount);
    const header = showHeader ? `
        <div class="map-popup-section-title">
            <span>${escapeHtml(title)}</span>
            <span class="map-popup-section-count">${escapeHtml(countText)}</span>
        </div>
    ` : '';
    return `
        <section class="map-popup-photo-section">
            ${header}
            ${grid}
        </section>
    `;
}

function mapPopupIconAction(className, title, onclick, path) {
    return `
        <button type="button" class="map-popup-action ${className}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}" onclick="${onclick}">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>
        </button>
    `;
}
