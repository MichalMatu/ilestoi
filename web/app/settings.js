// Filtr ortofoto jest prywatnym ustawieniem przeglądarki. Panel admina nadal
// zapisuje globalne widoczności warstw i funkcji na backendzie.
const enhancementControls = {
    enabled: document.getElementById('enhancement-enabled'),
    clahe: document.getElementById('enhancement-clahe'),
    tile: document.getElementById('enhancement-tile'),
    pLow: document.getElementById('enhancement-p-low'),
    pHigh: document.getElementById('enhancement-p-high'),
    outLow: document.getElementById('enhancement-out-low'),
    outHigh: document.getElementById('enhancement-out-high'),
    decast: document.getElementById('enhancement-decast'),
};
const enhancementControlFields = {
    clahe: 'clahe_clip_limit',
    tile: 'clahe_tile_grid_size',
    pLow: 'l_percentile_low',
    pHigh: 'l_percentile_high',
    outLow: 'l_output_low',
    outHigh: 'l_output_high',
    decast: 'decast_strength',
};

const publicLayerControls = {
    [PUBLIC_LAYER_KEYS.vehicles]: document.getElementById('admin-layer-vehicles'),
    [PUBLIC_LAYER_KEYS.fieldPhotoInfrastructure]: document.getElementById('admin-layer-field-photo-infrastructure'),
    [PUBLIC_LAYER_KEYS.fieldPhotoSmoke]: document.getElementById('admin-layer-field-photo-smoke'),
    [PUBLIC_LAYER_KEYS.fieldPhotoPending]: document.getElementById('admin-layer-field-photo-pending'),
    [PUBLIC_LAYER_KEYS.cadastral]: document.getElementById('admin-layer-cadastral'),
    [PUBLIC_LAYER_KEYS.baseMapOsm]: document.getElementById('admin-layer-base-map-osm'),
};
const publicFeatureControls = {
    [PUBLIC_FEATURE_KEYS.reportPdfs]: document.getElementById('admin-feature-report-pdfs'),
    [PUBLIC_FEATURE_KEYS.photoUploads]: document.getElementById('admin-feature-photo-uploads'),
    [PUBLIC_FEATURE_KEYS.vehicleGallery]: document.getElementById('admin-feature-vehicle-gallery'),
};
const publicLayerToggleRows = {
    [PUBLIC_LAYER_KEYS.vehicles]: document.getElementById('toggle-vehicles')?.closest('.layer-toggle'),
    [PUBLIC_LAYER_KEYS.fieldPhotoInfrastructure]: document.getElementById('toggle-field-photo-infrastructure')?.closest('.layer-toggle'),
    [PUBLIC_LAYER_KEYS.fieldPhotoSmoke]: document.getElementById('toggle-field-photo-smoke')?.closest('.layer-toggle'),
    [PUBLIC_LAYER_KEYS.fieldPhotoPending]: document.getElementById('toggle-field-photo-pending')?.closest('.layer-toggle'),
    [PUBLIC_LAYER_KEYS.cadastral]: document.getElementById('toggle-cadastral-parcels')?.closest('.layer-toggle'),
};
const adminSettingsControls = [
    document.getElementById('photo-retention-refresh'),
    document.getElementById('photo-retention-dry-run'),
    document.getElementById('photo-retention-apply'),
    document.getElementById('admin-public-layers-save'),
    document.getElementById('admin-public-features-save'),
    ...Object.values(publicLayerControls),
    ...Object.values(publicFeatureControls),
    ...mapViewAdminControls(),
].filter(Boolean);
let publicLayerSettings = Object.fromEntries(Object.values(PUBLIC_LAYER_KEYS).map(key => [key, true]));
let publicFeatureSettings = Object.fromEntries(Object.values(PUBLIC_FEATURE_KEYS).map(key => [key, true]));
let publicLayerSettingsLoaded = false;
let publicFeatureSettingsLoaded = false;
let fieldPhotoIssueFilters = Object.fromEntries(Array.from(FIELD_PHOTO_ISSUE_TYPES, issueType => [issueType, true]));
let pendingFieldPhotoLayerVisible = true;
let photoRetentionState = {};
let settingsSaveInFlight = false;
let photoRetentionRunInFlight = false;
let photoRetentionLoadRevision = 0;
let photoRetentionLoadAbortController = null;

function updateSettingsAccess() {
    const locked = !adminAuthenticated;
    adminSettingsControls.forEach(control => { control.disabled = locked; });
    updatePublicLayerAccess();
    updatePublicFeatureAccess();
}

function normalizePublicLayerSettings(settings) {
    const normalized = Object.fromEntries(Object.values(PUBLIC_LAYER_KEYS).map(key => [key, true]));
    if (!settings || typeof settings !== 'object') return normalized;
    Object.keys(normalized).forEach(key => {
        if (key in settings) normalized[key] = Boolean(settings[key]);
    });
    return normalized;
}

function fieldPhotoPublicLayerKey(issueType) {
    const safeIssueType = FIELD_PHOTO_ISSUE_TYPES.has(issueType) ? issueType : FIELD_PHOTO_ISSUE_TYPE_VEHICLE;
    return FIELD_PHOTO_PUBLIC_LAYER_KEYS[safeIssueType] || PUBLIC_LAYER_KEYS.vehicles;
}

function publicLayerAllowed(layerKey) {
    if (adminAuthenticated) return true;
    if (!publicLayerSettingsLoaded) return false;
    return publicLayerSettings[layerKey] !== false;
}

function normalizePublicFeatureSettings(settings) {
    const normalized = Object.fromEntries(Object.values(PUBLIC_FEATURE_KEYS).map(key => [key, true]));
    if (!settings || typeof settings !== 'object') return normalized;
    Object.keys(normalized).forEach(key => {
        if (key in settings) normalized[key] = Boolean(settings[key]);
    });
    return normalized;
}

function publicFeatureAllowed(featureKey) {
    if (adminAuthenticated) return true;
    if (!publicFeatureSettingsLoaded) return false;
    return publicFeatureSettings[featureKey] !== false;
}

function publicLayerFormSettings() {
    const settings = {};
    Object.entries(publicLayerControls).forEach(([key, control]) => {
        settings[key] = control ? Boolean(control.checked) : publicLayerSettings[key] !== false;
    });
    return normalizePublicLayerSettings(settings);
}

function publicFeatureFormSettings() {
    const settings = {};
    Object.entries(publicFeatureControls).forEach(([key, control]) => {
        settings[key] = control ? Boolean(control.checked) : publicFeatureSettings[key] !== false;
    });
    return normalizePublicFeatureSettings(settings);
}

function updateAdminPublicLayerControls() {
    Object.entries(publicLayerControls).forEach(([key, control]) => {
        if (!control) return;
        control.checked = publicLayerSettings[key] !== false;
        control.disabled = !adminAuthenticated;
    });
}

function updateAdminPublicFeatureControls() {
    Object.entries(publicFeatureControls).forEach(([key, control]) => {
        if (!control) return;
        control.checked = publicFeatureSettings[key] !== false;
        control.disabled = !adminAuthenticated;
    });
}

function updatePublicLayerControlVisibility() {
    Object.entries(publicLayerToggleRows).forEach(([key, row]) => {
        if (!row) return;
        const allowed = publicLayerAllowed(key);
        row.hidden = !allowed;
        const input = row.querySelector('input');
        if (input) {
            input.disabled = !allowed;
        }
    });
    const contextIdentifyParcelButton = document.getElementById('context-identify-parcel');
    if (contextIdentifyParcelButton) {
        contextIdentifyParcelButton.hidden = !publicLayerAllowed(PUBLIC_LAYER_KEYS.cadastral);
    }
    document.getElementById('map-layer-controls')?.classList.toggle(
        'is-loading-public-layers',
        !publicLayerSettingsLoaded && !adminAuthenticated
    );
}

function updatePublicLayerAccess() {
    updateAdminPublicLayerControls();
    updatePublicLayerControlVisibility();
    updateFieldPhotoIssueOptions();
    updatePublicFeatureControlVisibility();
}

function updatePublicFeatureControlVisibility() {
    const photoUploadsAllowed = publicFeatureAllowed(PUBLIC_FEATURE_KEYS.photoUploads);
    const contextFieldPhotoButton = document.getElementById('context-add-field-photos');
    const fieldPhotoUploadAvailable = photoUploadsAllowed && fieldPhotoAnyIssueAllowed();
    if (contextFieldPhotoButton) contextFieldPhotoButton.hidden = !fieldPhotoUploadAvailable;
    const panelPhotoUploadButton = document.getElementById('panel-add-field-photo');
    if (panelPhotoUploadButton) {
        panelPhotoUploadButton.hidden = !fieldPhotoUploadAvailable;
        panelPhotoUploadButton.disabled = !fieldPhotoUploadAvailable;
    }
    if (!fieldPhotoUploadAvailable) cancelFieldPhotoLocationPick({ clearStatus: true });
}

function updatePublicFeatureAccess() {
    updateAdminPublicFeatureControls();
    updatePublicFeatureControlVisibility();
    if (typeof updateVehicleGalleryAvailability === 'function') updateVehicleGalleryAvailability();
}

function applyPublicFeatureSettings(settings) {
    publicFeatureSettingsLoaded = true;
    publicFeatureSettings = normalizePublicFeatureSettings(settings);
    updatePublicFeatureAccess();
}

function applyPublicLayerSettings(settings) {
    publicLayerSettingsLoaded = true;
    publicLayerSettings = normalizePublicLayerSettings(settings);
    updatePublicLayerAccess();
    setCadastralLayerVisible(cadastralLayerVisible);
    updateMapSourceAvailability();
    if (vehicleLayerVisible && publicLayerAllowed(PUBLIC_LAYER_KEYS.vehicles)) {
        placeVehicleMarkers();
    } else {
        clearVehicleMarkers();
    }
    placeFieldPhotos(fieldPhotoLayerData);
    updateLayerCounters();
}

function setControlValue(id, value) {
    const el = enhancementControls[id];
    if (!el || value === undefined || value === null) return;
    if (el.type === 'checkbox') el.checked = Boolean(value);
    else el.value = String(value);
}

function enhancementFormSettings() {
    return {
        enabled: enhancementControls.enabled.checked,
        clahe_clip_limit: parseFloat(enhancementControls.clahe.value),
        clahe_tile_grid_size: parseInt(enhancementControls.tile.value),
        l_percentile_low: parseFloat(enhancementControls.pLow.value),
        l_percentile_high: parseFloat(enhancementControls.pHigh.value),
        l_output_low: parseFloat(enhancementControls.outLow.value),
        l_output_high: parseFloat(enhancementControls.outHigh.value),
        decast_strength: parseFloat(enhancementControls.decast.value),
    };
}

function applyEnhancementSettings(settings) {
    if (!settings) return;
    setControlValue('enabled', settings.enabled);
    setControlValue('clahe', settings.clahe_clip_limit);
    setControlValue('tile', settings.clahe_tile_grid_size);
    setControlValue('pLow', settings.l_percentile_low);
    setControlValue('pHigh', settings.l_percentile_high);
    setControlValue('outLow', settings.l_output_low);
    setControlValue('outHigh', settings.l_output_high);
    setControlValue('decast', settings.decast_strength);
    updateEnhancementLabels();
    updateEnhancementDefaultTicks();
}

function updateEnhancementLabels() {
    document.getElementById('enhancement-clahe-value').textContent = Number(enhancementControls.clahe.value).toFixed(1);
    document.getElementById('enhancement-tile-value').textContent = enhancementControls.tile.value;
    document.getElementById('enhancement-p-low-value').textContent = Number(enhancementControls.pLow.value).toFixed(1).replace('.0', '');
    document.getElementById('enhancement-p-high-value').textContent = Number(enhancementControls.pHigh.value).toFixed(1).replace('.0', '');
    document.getElementById('enhancement-out-low-value').textContent = enhancementControls.outLow.value;
    document.getElementById('enhancement-out-high-value').textContent = enhancementControls.outHigh.value;
    document.getElementById('enhancement-decast-value').textContent = Number(enhancementControls.decast.value).toFixed(2).replace(/0$/, '').replace(/\.$/, '');
}

function updateEnhancementDefaultTicks() {
    if (!defaultEnhancementSettings) return;
    Object.entries(enhancementControlFields).forEach(([controlId, field]) => {
        const control = enhancementControls[controlId];
        if (!control) return;
        const min = parseFloat(control.min);
        const max = parseFloat(control.max);
        const value = parseFloat(defaultEnhancementSettings[field]);
        const pct = max > min ? ((value - min) / (max - min)) * 100 : 0;
        control.style.setProperty('--default-pos', `${Math.max(0, Math.min(100, pct))}%`);
    });
}

function snapEnhancementControlToDefault(control) {
    if (!defaultEnhancementSettings || control.type !== 'range') return;
    const controlId = Object.keys(enhancementControls).find(key => enhancementControls[key] === control);
    const field = enhancementControlFields[controlId];
    if (!field) return;

    const current = parseFloat(control.value);
    const defaultValue = parseFloat(defaultEnhancementSettings[field]);
    const min = parseFloat(control.min);
    const max = parseFloat(control.max);
    const step = parseFloat(control.step || '1');
    const snapDistance = Math.max(step * 1.1, (max - min) * 0.015);
    if (Math.abs(current - defaultValue) <= snapDistance) {
        control.value = String(defaultValue);
    }
}

function normalizedEnhancementNumber(raw, field, controlId, options = {}) {
    const control = enhancementControls[controlId];
    const fallback = parseFloat(defaultEnhancementSettings?.[field] ?? control?.defaultValue ?? control?.value ?? '0');
    let value = parseFloat(raw?.[field]);
    if (!Number.isFinite(value)) value = fallback;

    const min = parseFloat(control?.min ?? value);
    const max = parseFloat(control?.max ?? value);
    if (Number.isFinite(min)) value = Math.max(min, value);
    if (Number.isFinite(max)) value = Math.min(max, value);
    return options.integer ? Math.round(value) : value;
}

function normalizeEnhancementSettings(settings) {
    const raw = settings && typeof settings === 'object' ? settings : {};
    const defaultsEnabled = defaultEnhancementSettings?.enabled ?? enhancementControls.enabled?.defaultChecked ?? true;
    const normalized = {
        enabled: 'enabled' in raw ? Boolean(raw.enabled) : Boolean(defaultsEnabled),
        clahe_clip_limit: normalizedEnhancementNumber(raw, 'clahe_clip_limit', 'clahe'),
        clahe_tile_grid_size: normalizedEnhancementNumber(raw, 'clahe_tile_grid_size', 'tile', { integer: true }),
        l_percentile_low: normalizedEnhancementNumber(raw, 'l_percentile_low', 'pLow'),
        l_percentile_high: normalizedEnhancementNumber(raw, 'l_percentile_high', 'pHigh'),
        l_output_low: normalizedEnhancementNumber(raw, 'l_output_low', 'outLow'),
        l_output_high: normalizedEnhancementNumber(raw, 'l_output_high', 'outHigh'),
        decast_strength: normalizedEnhancementNumber(raw, 'decast_strength', 'decast'),
    };

    if (normalized.l_percentile_low >= normalized.l_percentile_high) {
        normalized.l_percentile_low = normalizedEnhancementNumber(defaultEnhancementSettings, 'l_percentile_low', 'pLow');
        normalized.l_percentile_high = normalizedEnhancementNumber(defaultEnhancementSettings, 'l_percentile_high', 'pHigh');
    }
    if (normalized.l_output_low >= normalized.l_output_high) {
        normalized.l_output_low = normalizedEnhancementNumber(defaultEnhancementSettings, 'l_output_low', 'outLow');
        normalized.l_output_high = normalizedEnhancementNumber(defaultEnhancementSettings, 'l_output_high', 'outHigh');
    }
    return normalized;
}

function encodeEnhancementSettings(settings) {
    try {
        return btoa(JSON.stringify(normalizeEnhancementSettings(settings)))
            .replace(/\+/g, '-')
            .replace(/\//g, '_')
            .replace(/=+$/, '');
    } catch (_) {
        return '';
    }
}

function decodeEnhancementSettings(token) {
    if (!token || typeof token !== 'string') return null;
    try {
        const base64 = token.replace(/-/g, '+').replace(/_/g, '/');
        const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
        return JSON.parse(atob(padded));
    } catch (_) {
        return null;
    }
}

function readStoredEnhancementSettings() {
    try {
        return decodeEnhancementSettings(localStorage.getItem(ENHANCEMENT_SETTINGS_STORAGE_KEY));
    } catch (_) {
        return null;
    }
}

function persistEnhancementSettings(settings) {
    const token = encodeEnhancementSettings(settings);
    enhancementSettingsRevision = token;
    try {
        localStorage.setItem(ENHANCEMENT_SETTINGS_STORAGE_KEY, token);
    } catch (_) {
        // Brak localStorage nie blokuje użycia filtra w bieżącej sesji.
    }
}

function saveLocalEnhancementSettings(options = {}) {
    const previousRevision = enhancementSettingsRevision;
    const settings = normalizeEnhancementSettings(enhancementFormSettings());
    applyEnhancementSettings(settings);
    persistEnhancementSettings(settings);

    if (options.refresh !== false && previousRevision !== enhancementSettingsRevision) {
        refreshOrthoLayer();
    }
    const status = document.getElementById('settings-save-status');
    if (status) status.textContent = t('modal.settings.enhancementHint');
}

async function loadAppSettings() {
    let loadedPublicLayers = false;
    try {
        const data = await apiJson(SETTINGS_URL);
        defaultEnhancementSettings = data.defaults?.enhancement || data.enhancement;
        applyEnhancementSettings(readStoredEnhancementSettings() || defaultEnhancementSettings || data.enhancement);
        saveLocalEnhancementSettings({ refresh: false });
        applyMapViewSettings(data.map_view);
        setDefaultMapView(data.map_view);
        applyPublicLayerSettings(data.public_layers);
        applyPublicFeatureSettings(data.public_features);
        loadedPublicLayers = true;
    } catch (_) {
        const storedSettings = readStoredEnhancementSettings();
        if (storedSettings) {
            applyEnhancementSettings(storedSettings);
            saveLocalEnhancementSettings({ refresh: false });
        } else {
            updateEnhancementLabels();
            saveLocalEnhancementSettings({ refresh: false });
        }
        applyMapViewSettings(window.WRECKSCANNER_APP_SETTINGS?.map_view);
    }
    if (!loadedPublicLayers) {
        publicLayerSettingsLoaded = true;
        publicFeatureSettingsLoaded = true;
        updatePublicLayerAccess();
        updatePublicFeatureAccess();
    }
}

async function saveSettings(payload, onSaved, options = {}) {
    const status = options.statusId ? document.getElementById(options.statusId) : null;
    if (!adminAuthenticated || settingsSaveInFlight) {
        updateSettingsAccess();
        return;
    }
    settingsSaveInFlight = true;
    adminSettingsControls.forEach(control => { control.disabled = true; });
    try {
        const data = await apiPostJson(SETTINGS_URL, payload);
        onSaved(data);
    } catch (err) {
        if (status) status.textContent = apiErrorMessage(err, options.errorMessage || t('modal.settings.saveError'));
    } finally {
        settingsSaveInFlight = false;
        updateSettingsAccess();
    }
}

async function savePublicLayerSettings() {
    await saveSettings({ public_layers: publicLayerFormSettings() }, data => {
        applyPublicLayerSettings(data.public_layers);
        const status = document.getElementById('admin-public-layers-status');
        if (status) status.textContent = t('modal.adminPanel.publicLayersSaved');
        loadFieldPhotos();
        updateMapSourceAvailability();
    }, {
        statusId: 'admin-public-layers-status',
        errorMessage: t('modal.adminPanel.publicLayersSaveError'),
    });
}

async function savePublicFeatureSettings() {
    await saveSettings({ public_features: publicFeatureFormSettings() }, data => {
        applyPublicFeatureSettings(data.public_features);
        const status = document.getElementById('admin-public-features-status');
        if (status) status.textContent = t('modal.adminPanel.publicFeaturesSaved');
        loadFieldPhotos();
    }, {
        statusId: 'admin-public-features-status',
        errorMessage: t('modal.adminPanel.publicFeaturesSaveError'),
    });
}

async function saveMapViewSettings() {
    await saveSettings({ map_view: mapViewFormSettings() }, data => {
        applyMapViewSettings(data.map_view);
        setDefaultMapView(data.map_view);
        const status = document.getElementById('admin-map-view-status');
        if (status) status.textContent = t('modal.adminPanel.mapStartSaved');
    }, {
        statusId: 'admin-map-view-status',
        errorMessage: t('modal.adminPanel.mapStartSaveError'),
    });
}

function retentionReportTotals(report) {
    const field = report.field_photos || {};
    return {
        scanned: Number(field.scanned || 0),
        replaced: Number(field.replaced || 0),
        deleted: Number(field.deleted || 0),
        skipped: Number(field.skipped || 0),
    };
}

function formatRetentionFinishedAt(value) {
    if (!value) return '-';
    const finishedAt = new Date(value);
    if (Number.isNaN(finishedAt.getTime())) return value;
    return new Intl.DateTimeFormat(document.documentElement.lang || 'pl', {
        dateStyle: 'medium',
        timeStyle: 'short',
    }).format(finishedAt);
}

function retentionMetric(labelKey, value, variant = '') {
    const item = document.createElement('div');
    item.className = `photo-retention-metric${variant ? ` photo-retention-metric--${variant}` : ''}`;

    const number = document.createElement('strong');
    number.textContent = String(value);

    const label = document.createElement('span');
    label.textContent = t(labelKey);

    item.replaceChildren(number, label);
    return item;
}

function renderPhotoRetentionReport(status, report, state = {}) {
    if (!report) {
        status.textContent = t('modal.settings.photoRetentionIdle');
        return;
    }

    const totals = retentionReportTotals(report);
    const card = document.createElement('div');
    card.className = 'photo-retention-card';

    const header = document.createElement('div');
    header.className = 'photo-retention-card-header';

    const title = document.createElement('strong');
    title.textContent = t('modal.settings.photoRetentionLastRun');

    const mode = document.createElement('span');
    mode.className = `photo-retention-mode${report.dry_run ? '' : ' photo-retention-mode--applied'}`;
    mode.textContent = t(report.dry_run
        ? 'modal.settings.photoRetentionModeDryRun'
        : 'modal.settings.photoRetentionModeApplied');

    header.replaceChildren(title, mode);

    const finished = document.createElement('div');
    finished.className = 'photo-retention-finished';
    const finishedLabel = document.createElement('span');
    finishedLabel.textContent = t('modal.settings.photoRetentionFinishedAt');
    const finishedValue = document.createElement('strong');
    finishedValue.textContent = formatRetentionFinishedAt(state.last_finished_at || report.generated_at);
    finished.replaceChildren(finishedLabel, finishedValue);

    const metrics = document.createElement('div');
    metrics.className = 'photo-retention-metrics';
    metrics.replaceChildren(
        retentionMetric('modal.settings.photoRetentionScanned', totals.scanned),
        retentionMetric('modal.settings.photoRetentionReplaced', totals.replaced, 'positive'),
        retentionMetric('modal.settings.photoRetentionDeleted', totals.deleted, 'danger'),
        retentionMetric('modal.settings.photoRetentionSkipped', totals.skipped),
    );

    card.replaceChildren(header, finished, metrics);
    if (totals.replaced === 0 && totals.deleted === 0) {
        const note = document.createElement('p');
        note.className = 'photo-retention-note';
        note.textContent = t('modal.settings.photoRetentionNoChanges');
        card.append(note);
    }
    status.replaceChildren(card);
}

function updatePhotoRetentionStatus(state = {}) {
    const status = document.getElementById('photo-retention-status');
    if (!status) return;
    photoRetentionState = state;
    if (state.running) {
        status.textContent = t('modal.settings.photoRetentionRunning');
        return;
    }
    if (state.last_error) {
        status.textContent = t('modal.settings.photoRetentionLastError', { error: state.last_error });
        return;
    }
    renderPhotoRetentionReport(status, state.last_report, state);
}

document.addEventListener('langchange', () => updatePhotoRetentionStatus(photoRetentionState));

async function loadPhotoRetentionStatus() {
    if (!adminAuthenticated && !(await ensureAdmin())) return;
    const requestRevision = ++photoRetentionLoadRevision;
    photoRetentionLoadAbortController?.abort();
    const requestController = new AbortController();
    photoRetentionLoadAbortController = requestController;
    const status = document.getElementById('photo-retention-status');
    if (status) status.textContent = t('modal.settings.photoRetentionLoading');
    try {
        const data = await apiJson(`${ADMIN_PHOTO_RETENTION_URL}?ts=${Date.now()}`, {
            cache: 'no-store',
            signal: requestController.signal,
        });
        if (requestRevision !== photoRetentionLoadRevision) return;
        if (data.status !== 'ok') {
            throw new Error(data.error || t('modal.settings.photoRetentionLoadError'));
        }
        updatePhotoRetentionStatus(data.retention || {});
    } catch (err) {
        if (requestRevision !== photoRetentionLoadRevision || err?.payload?.code === 'cancelled') return;
        if (status) status.textContent = apiErrorMessage(err, t('modal.settings.photoRetentionLoadError'));
    } finally {
        if (photoRetentionLoadAbortController === requestController) photoRetentionLoadAbortController = null;
    }
}

async function runPhotoRetention(dryRun = true) {
    if (photoRetentionRunInFlight) return;
    photoRetentionRunInFlight = true;
    adminSettingsControls.forEach(control => { control.disabled = true; });
    try {
        if (!adminAuthenticated && !(await ensureAdmin())) return;
        if (!dryRun) {
            const confirmed = await confirmAction({
                title: t('modal.settings.photoRetentionApplyTitle'),
                message: t('modal.settings.photoRetentionApplyConfirm'),
                confirmLabel: t('modal.settings.photoRetentionApply'),
            });
            if (!confirmed) return;
        }
        const status = document.getElementById('photo-retention-status');
        if (status) status.textContent = t('modal.settings.photoRetentionRunning');
        const data = await apiPostJson(`${ADMIN_PHOTO_RETENTION_URL}/run`, { dry_run: Boolean(dryRun) });
        if (data.status !== 'ok') {
            throw new Error(data.error || t('modal.settings.photoRetentionRunError'));
        }
        updatePhotoRetentionStatus(data.retention || { last_report: data.report });
    } catch (err) {
        const status = document.getElementById('photo-retention-status');
        if (status) status.textContent = apiErrorMessage(err, t('modal.settings.photoRetentionRunError'));
    } finally {
        photoRetentionRunInFlight = false;
        updateSettingsAccess();
    }
}

document.getElementById('modal-photo-retention')?.addEventListener('modalclose', () => {
    photoRetentionLoadRevision += 1;
    photoRetentionLoadAbortController?.abort();
    photoRetentionLoadAbortController = null;
});

function queueEnhancementSettingsSave(event = null) {
    if (event?.target instanceof HTMLInputElement) {
        snapEnhancementControlToDefault(event.target);
    }
    updateEnhancementLabels();
    if (settingsSaveTimer) clearTimeout(settingsSaveTimer);
    settingsSaveTimer = setTimeout(saveLocalEnhancementSettings, ENHANCEMENT_SETTINGS_SAVE_DEBOUNCE_MS);
}

Object.values(enhancementControls).forEach(control => {
    if (!control) return;
    const eventName = control.type === 'checkbox' ? 'change' : 'input';
    control.addEventListener(eventName, queueEnhancementSettingsSave);
});
document.getElementById('enhancement-reset')?.addEventListener('click', () => {
    applyEnhancementSettings(defaultEnhancementSettings || {});
    if (settingsSaveTimer) clearTimeout(settingsSaveTimer);
    saveLocalEnhancementSettings();
});

updateSettingsAccess();
loadAppSettings();
setCadastralLayerVisible(cadastralLayerVisible);
