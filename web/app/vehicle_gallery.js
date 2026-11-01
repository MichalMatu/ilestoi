/* Gallery dock is deliberately additive: the existing year slider markup and CSS stay intact. */
let vehicleGalleryEnabled = true;
let vehicleGalleryMode = 'map';
let vehicleGalleryRequest = null;
let vehicleGalleryDebounce = null;
let vehicleGalleryRevision = 0;
try {
    vehicleGalleryEnabled = localStorage.getItem(MAP_GALLERY_VISIBLE_STORAGE_KEY) !== 'false';
    const stored = localStorage.getItem(MAP_DOCK_MODE_STORAGE_KEY);
    if (['map', 'gallery', 'none'].includes(stored)) vehicleGalleryMode = stored;
} catch (_) {}

function vehicleGalleryIsAvailable() {
    return vehicleGalleryEnabled && publicFeatureAllowed(PUBLIC_FEATURE_KEYS.vehicleGallery);
}

function vehicleGalleryDockMode() {
    return vehicleGalleryMode;
}

function updateVehicleGalleryAvailability() {
    const dock = document.getElementById('vehicle-gallery-dock');
    if (!dock) return;
    const allowed = vehicleGalleryIsAvailable();
    const control = document.getElementById('map-gallery-toggle');
    if (control) control.checked = vehicleGalleryEnabled;
    dock.hidden = !allowed || vehicleGalleryMode !== 'gallery';
    if (!allowed) {
        vehicleGalleryRequest?.abort();
        applyMapSourceSliderVisibility();
        return;
    }
    dock.dataset.mode = vehicleGalleryMode;
    const panel = document.getElementById('vehicle-gallery-panel');
    if (panel) panel.hidden = vehicleGalleryMode !== 'gallery';
    renderVehicleGalleryMapDots();
    applyMapSourceSliderVisibility();
    if (vehicleGalleryMode === 'gallery') scheduleVehicleGalleryLoad(true);
    else vehicleGalleryRequest?.abort();
}

function setVehicleGalleryEnabled(enabled) {
    vehicleGalleryEnabled = Boolean(enabled);
    try { localStorage.setItem(MAP_GALLERY_VISIBLE_STORAGE_KEY, String(vehicleGalleryEnabled)); } catch (_) {}
    updateVehicleGalleryAvailability();
}

function setVehicleGalleryDockMode(mode) {
    if (!['map', 'gallery', 'none'].includes(mode)) return;
    vehicleGalleryMode = mode;
    try { localStorage.setItem(MAP_DOCK_MODE_STORAGE_KEY, mode); } catch (_) {}
    updateVehicleGalleryAvailability();
}

function openVehicleGalleryFromMenu() {
    if (!publicFeatureAllowed(PUBLIC_FEATURE_KEYS.vehicleGallery)) return;
    if (!vehicleGalleryEnabled) setVehicleGalleryEnabled(true);
    setVehicleGalleryDockMode('gallery');
    closeAppMenu();
}

function renderVehicleGalleryMapDots() {
    const holder = document.getElementById('vehicle-gallery-map-dots');
    if (!holder) return;
    holder.hidden = !mapSourceSliderVisible;
    if (!mapSourceSliderVisible) return;
    const selected = currentMapSourceIndex;
    const fragment = document.createDocumentFragment();
    visibleMapSourceIndices().forEach(index => {
        const source = MAP_SOURCES[index];
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'vehicle-gallery-map-dot';
        button.classList.toggle('is-active', index === selected);
        button.title = source.label;
        button.setAttribute('aria-label', source.label);
        button.setAttribute('aria-pressed', String(index === selected));
        button.addEventListener('click', () => setMapSource(index));
        fragment.append(button);
    });
    holder.replaceChildren(fragment);
}

function scheduleVehicleGalleryLoad(immediate = false) {
    window.clearTimeout(vehicleGalleryDebounce);
    if (!vehicleGalleryIsAvailable() || vehicleGalleryMode !== 'gallery') return;
    vehicleGalleryDebounce = window.setTimeout(loadVehicleGallery, immediate ? 0 : 250);
}

async function loadVehicleGallery() {
    if (!vehicleGalleryIsAvailable() || vehicleGalleryMode !== 'gallery') return;
    vehicleGalleryRequest?.abort();
    const controller = new AbortController();
    vehicleGalleryRequest = controller;
    const revision = ++vehicleGalleryRevision;
    const list = document.getElementById('vehicle-gallery-items');
    if (list && !list.children.length) list.textContent = t('gallery.loading');
    try {
        const bbox = fieldPhotoViewportQuery().bbox;
        const data = await apiJson(`${FIELD_PHOTOS_URL}/gallery?bbox=${encodeURIComponent(bbox)}`, {
            signal: controller.signal, cache: 'no-store',
        });
        if (revision !== vehicleGalleryRevision || !vehicleGalleryIsAvailable()
            || vehicleGalleryMode !== 'gallery') return;
        if (data.status !== 'ok' || !Array.isArray(data.photos) || data.photos.length > 100) {
            throw new Error(t('gallery.error'));
        }
        const unique = [];
        for (const photo of data.photos) {
            if (Number(photo.vehicle_gallery_priority) < 1 || !photo.public_thumb) continue;
            const lat = Number(photo.lat), lon = Number(photo.lon);
            if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
            if (unique.some(previous => metersBetween(lat, lon, Number(previous.lat), Number(previous.lon)) <= FIELD_PHOTO_GROUP_RADIUS_M)) continue;
            unique.push(photo);
            if (unique.length >= 10) break;
        }
        renderVehicleGalleryItems(unique);
    } catch (_error) {
        if (revision !== vehicleGalleryRevision || controller.signal.aborted) return;
        if (list) list.textContent = t('gallery.error');
    }
}

function renderVehicleGalleryItems(photos) {
    const list = document.getElementById('vehicle-gallery-items');
    if (!list) return;
    list.replaceChildren();
    if (!photos.length) {
        list.textContent = t('gallery.empty');
        return;
    }
    const fragment = document.createDocumentFragment();
    const keys = { 1: 'gallery.featured', 2: 'gallery.high', 3: 'gallery.urgent' };
    photos.forEach(photo => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'vehicle-gallery-card';
        button.setAttribute('role', 'listitem');
        const img = document.createElement('img');
        img.src = photo.public_thumb;
        img.loading = 'lazy';
        img.alt = '';
        const copy = document.createElement('span');
        copy.textContent = t(keys[photo.vehicle_gallery_priority] || 'gallery.featured');
        button.append(img, copy);
        button.addEventListener('click', () => focusVehicleGalleryPhoto(photo));
        fragment.append(button);
    });
    list.append(fragment);
}

function focusVehicleGalleryPhoto(photo) {
    const lat = Number(photo.lat), lon = Number(photo.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    pendingVehiclePhotoFocusId = safeFieldPhotoId(photo.id);
    vehiclePhotoFocusDone = false;
    setVehicleGalleryDockMode(mapSourceSliderVisible ? 'map' : 'none');
    map.setView([lat, lon], Math.max(17, map.getZoom()), { animate: false });
    loadFieldPhotos();
}

let vehicleGalleryNominationClose = null;
function closeVehicleGalleryNomination() {
    vehicleGalleryNominationClose?.();
    vehicleGalleryNominationClose = null;
}

function openVehicleGalleryNomination(button) {
    if (!adminAuthenticated || !button?.dataset?.galleryPhotoId) return;
    closeVehicleGalleryNomination();
    const menu = document.createElement('div');
    menu.className = 'vehicle-gallery-nomination-menu';
    menu.setAttribute('role', 'menu');
    const photoId = button.dataset.galleryPhotoId;
    const options = [
        [0, 'gallery.none'], [1, 'gallery.featured'], [2, 'gallery.high'], [3, 'gallery.urgent'],
    ];
    for (const [priority, key] of options) {
        const item = document.createElement('button');
        item.type = 'button';
        item.setAttribute('role', 'menuitem');
        item.textContent = `${priority ? '★' : '☆'} ${t(key)}`;
        item.addEventListener('click', async event => {
            event.stopPropagation();
            closeVehicleGalleryNomination();
            button.disabled = true;
            try {
                const data = await apiPatchJson(`${ADMIN_PHOTOS_URL}/field/${encodeURIComponent(photoId)}/review`, {
                    vehicle_gallery_priority: priority,
                });
                if (data.status !== 'ok') throw new Error(data.error || t('gallery.error'));
                const target = fieldPhotoLayerData.find(photo => String(photo.id) === photoId);
                if (target) {
                    fieldPhotoLayerData.forEach(photo => {
                        if (fieldPhotoIssueType(photo) === FIELD_PHOTO_ISSUE_TYPE_VEHICLE
                            && fieldPhotoReviewStatus(photo) === 'approved'
                            && metersBetween(Number(photo.lat), Number(photo.lon), Number(target.lat), Number(target.lon)) <= FIELD_PHOTO_GROUP_RADIUS_M) {
                            photo.vehicle_gallery_priority = String(photo.id) === photoId ? priority : 0;
                        }
                    });
                }
                const popup = button.closest('.map-popup');
                popup?.querySelectorAll('.map-popup-nomination').forEach(star => {
                    if (star !== button) {
                        star.dataset.galleryPriority = '0';
                        star.textContent = '☆';
                    }
                });
                button.dataset.galleryPriority = String(priority);
                button.textContent = priority ? '★' : '☆';
                scheduleVehicleGalleryLoad(true);
                map.once('popupclose', () => window.setTimeout(loadFieldPhotos, 0));
            } catch (error) {
                const status = document.getElementById('status');
                if (status) status.textContent = error.message || t('gallery.error');
            } finally {
                button.disabled = false;
            }
        });
        menu.append(item);
    }
    document.body.append(menu);
    const bounds = button.getBoundingClientRect();
    const width = menu.offsetWidth;
    const height = menu.offsetHeight;
    menu.style.left = `${Math.max(8, Math.min(window.innerWidth - width - 8, bounds.right - width))}px`;
    menu.style.top = `${Math.max(8, Math.min(window.innerHeight - height - 8, bounds.bottom + 4))}px`;
    const outside = event => { if (!menu.contains(event.target) && event.target !== button) closeVehicleGalleryNomination(); };
    const escape = event => { if (event.key === 'Escape') closeVehicleGalleryNomination(); };
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('keydown', escape, true);
    vehicleGalleryNominationClose = () => {
        document.removeEventListener('pointerdown', outside, true);
        document.removeEventListener('keydown', escape, true);
        menu.remove();
    };
}

map.on('moveend zoomend', () => scheduleVehicleGalleryLoad());
document.addEventListener('langchange', () => {
    updateVehicleGalleryAvailability();
});
updateVehicleGalleryAvailability();
