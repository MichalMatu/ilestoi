/* IleStoi guided tour: real Leaflet/UI targets, no simulated uploads or API mutations. */
const ONBOARDING_TOUR_STORAGE_KEY = 'ilestoi-onboarding-v1-complete';
const onboardingTourRoot = document.getElementById('onboarding-tour');
const onboardingTourState = {
    active: false,
    steps: [],
    index: 0,
    marker: null,
    previewOpened: false,
    originalView: null,
    originalPopup: null,
    returnFocus: null,
    dismissedThisSession: false,
    positionFrame: null,
    stepRevision: 0,
};

function onboardingTourSeen() {
    if (onboardingTourState.dismissedThisSession) return true;
    try { return localStorage.getItem(ONBOARDING_TOUR_STORAGE_KEY) === '1'; } catch (_) { return false; }
}

function onboardingTourRemember() {
    onboardingTourState.dismissedThisSession = true;
    try { localStorage.setItem(ONBOARDING_TOUR_STORAGE_KEY, '1'); } catch (_) {}
}

function onboardingTourTarget(selector) {
    const target = typeof selector === 'function' ? selector() : document.querySelector(selector);
    if (!(target instanceof HTMLElement) || target.closest('[hidden]')) return null;
    if (!target.isConnected || !target.getClientRects().length) return null;
    return target;
}

/* The Leaflet icon is a 34px anchor; at low zoom its visible dot is
   translated inside that box. Measure the actual rendered pin, not the anchor. */
function onboardingTourMarkerTarget(marker) {
    const icon = marker?.getElement?.() || marker?._icon;
    return icon?.querySelector('.vehicle-pin') || icon || null;
}

function onboardingTourExampleMarker() {
    if (typeof vehicleMarkers === 'undefined' || !Array.isArray(vehicleMarkers)) return null;
    const active = vehicleMarkers.filter(marker => map.hasLayer(marker) && marker.getPopup());
    const center = map.getCenter();
    active.sort((a, b) => {
        const aReport = String(a.getPopup().getContent()).includes('map-popup-action--report') ? 0 : 1;
        const bReport = String(b.getPopup().getContent()).includes('map-popup-action--report') ? 0 : 1;
        return aReport - bReport || center.distanceTo(a.getLatLng()) - center.distanceTo(b.getLatLng());
    });
    return active[0] || null;
}

function onboardingTourSteps(marker) {
    const steps = [
        { title: 'tour.welcomeTitle', description: 'tour.welcomeBody' },
        {
            title: 'tour.mapTitle',
            description: marker ? 'tour.mapBody' : 'tour.mapEmptyBody',
            focusMarker: Boolean(marker),
            target: () => onboardingTourMarkerTarget(marker) || document.getElementById('map'),
        },
    ];
    if (marker) {
        steps.push(
            {
                title: 'tour.vehicleTitle',
                description: 'tour.vehicleBody',
                popup: true,
                target: () => document.querySelector('.leaflet-popup .map-popup') ||
                    document.querySelector('.leaflet-popup'),
            },
            {
                title: 'tour.reportTitle',
                description: 'tour.reportBody',
                popup: true,
                target: () => document.querySelector('.leaflet-popup .map-popup-action--report') ||
                    document.querySelector('.leaflet-popup'),
            }
        );
    }
    steps.push(
        {
            title: 'tour.addTitle',
            description: 'tour.addBody',
            menu: true,
            target: () => onboardingTourTarget('#panel-add-field-photo') ||
                document.getElementById('app-menu-drawer'),
        },
        {
            title: 'tour.layersTitle',
            description: 'tour.layersBody',
            menu: true,
            target: () => document.querySelector('#map-layer-controls .layer-toggle--vehicle') ||
                document.getElementById('map-layer-controls'),
        },
        {
            title: 'tour.sourcesTitle',
            description: 'tour.sourcesBody',
            menu: true,
            target: '#panel-map-source',
        },
        { title: 'tour.doneTitle', description: 'tour.doneBody' }
    );
    return steps;
}

/* Pure viewport geometry used for desktop and narrow mobile viewports. */
function onboardingTourPlacement(targetRect, tooltipRect, width, height) {
    const margin = 12;
    const gap = 18;
    const w = Math.max(0, Math.min(tooltipRect.width, width - 2 * margin));
    const h = Math.max(0, Math.min(tooltipRect.height, height - 2 * margin));
    const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
    if (!targetRect) {
        return { left: clamp((width - w) / 2, margin, width - w - margin),
            top: clamp((height - h) / 2, margin, height - h - margin) };
    }
    const left = clamp(targetRect.left + (targetRect.width - w) / 2, margin, width - w - margin);
    const bottomSpace = height - targetRect.bottom;
    const topSpace = targetRect.top;
    let top;
    if (bottomSpace >= h + gap + margin) top = targetRect.bottom + gap;
    else if (topSpace >= h + gap + margin) top = targetRect.top - h - gap;
    else if (bottomSpace >= topSpace) top = height - h - margin;
    else top = margin;
    return { left, top: clamp(top, margin, height - h - margin) };
}

function positionOnboardingTour() {
    if (!onboardingTourState.active || !onboardingTourRoot) return;
    const step = onboardingTourState.steps[onboardingTourState.index];
    const target = step.target ? onboardingTourTarget(step.target) : null;
    const spotlight = onboardingTourRoot.querySelector('.onboarding-tour-spotlight');
    const card = onboardingTourRoot.querySelector('.onboarding-tour-card');
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let rect = null;
    if (target) {
        const box = target.getBoundingClientRect();
        if (box.width > 0 && box.height > 0 && box.right > 0 && box.bottom > 0 && box.left < vw && box.top < vh) {
            const left = Math.max(8, box.left - 6);
            const top = Math.max(8, box.top - 6);
            const right = Math.min(vw - 8, box.right + 6);
            const bottom = Math.min(vh - 8, box.bottom + 6);
            if (right > left && bottom > top) {
                rect = { left, top, right, bottom, width: right - left, height: bottom - top };
            }
        }
    }
    onboardingTourRoot.classList.toggle('onboarding-tour--centered', !rect);
    spotlight.hidden = !rect;
    if (rect) {
        spotlight.style.left = rect.left + 'px';
        spotlight.style.top = rect.top + 'px';
        spotlight.style.width = rect.width + 'px';
        spotlight.style.height = rect.height + 'px';
    }
    const position = onboardingTourPlacement(rect, card.getBoundingClientRect(), vw, vh);
    card.style.left = position.left + 'px';
    card.style.top = position.top + 'px';
}

function scheduleOnboardingTourPosition() {
    if (!onboardingTourState.active || onboardingTourState.positionFrame !== null) return;
    onboardingTourState.positionFrame = requestAnimationFrame(() => {
        onboardingTourState.positionFrame = null;
        positionOnboardingTour();
    });
}

function showOnboardingTourStep(index) {
    if (!onboardingTourState.active) return;
    const state = onboardingTourState;
    state.index = Math.max(0, Math.min(index, state.steps.length - 1));
    const step = state.steps[state.index];
    const revision = ++state.stepRevision;
    if (step.menu) {
        if (state.previewOpened) {
            map.closePopup();
            state.previewOpened = false;
        }
        if (!isAppMenuOpen()) setAppMenuOpen(true, { restoreFocus: false });
    } else if (isAppMenuOpen()) {
        closeAppMenu({ restoreFocus: false });
    }
    if (step.focusMarker && state.marker && map.hasLayer(state.marker)) {
        map.panTo(state.marker.getLatLng(), { animate: false });
    }
    if (step.popup && state.marker && map.hasLayer(state.marker)) {
        state.marker.openPopup();
        state.previewOpened = true;
    } else if (state.previewOpened && !step.popup) {
        map.closePopup();
        state.previewOpened = false;
    }

    const root = onboardingTourRoot;
    root.querySelector('#onboarding-tour-progress').textContent =
        t('tour.progress', { current: state.index + 1, total: state.steps.length });
    root.querySelector('#onboarding-tour-title').textContent = t(step.title);
    const descriptionKey = step.title === 'tour.addTitle' && !onboardingTourTarget('#panel-add-field-photo')
        ? 'tour.addUnavailableBody' : step.description;
    root.querySelector('#onboarding-tour-description').textContent = t(descriptionKey);
    const back = root.querySelector('#onboarding-tour-back');
    back.textContent = t('tour.back');
    back.hidden = state.index === 0;
    root.querySelector('#onboarding-tour-skip').textContent = t('tour.skip');
    const next = root.querySelector('#onboarding-tour-next');
    next.textContent = t(state.index === state.steps.length - 1 ? 'tour.finish' : 'tour.next');

    if (typeof syncPageIsolation === 'function') syncPageIsolation();
    requestAnimationFrame(() => {
        if (!state.active || state.stepRevision !== revision) return;
        const target = step.target ? onboardingTourTarget(step.target) : null;
        if (target && step.menu) target.scrollIntoView({ behavior: 'instant', block: 'nearest' });
        requestAnimationFrame(() => {
            if (!state.active || state.stepRevision !== revision) return;
            positionOnboardingTour();
            next.focus({ preventScroll: true });
        });
    });
}

function finishOnboardingTour(event) {
    // Never allow Skip / Finish clicks to reach map or underlying controls.
    event?.preventDefault();
    event?.stopPropagation();
    const state = onboardingTourState;
    if (!state.active) return;
    onboardingTourRemember();
    state.active = false;
    ++state.stepRevision;
    if (state.positionFrame !== null) cancelAnimationFrame(state.positionFrame);
    state.positionFrame = null;
    onboardingTourRoot.hidden = true;
    onboardingTourRoot.classList.remove('onboarding-tour--centered');
    if (state.previewOpened) map.closePopup();
    state.previewOpened = false;
    if (isAppMenuOpen()) closeAppMenu({ restoreFocus: false });
    if (state.originalView) {
        map.setView(state.originalView.center, state.originalView.zoom, { animate: false });
    }
    if (state.originalPopup) map.openPopup(state.originalPopup);
    state.originalPopup = null;
    state.originalView = null;
    if (typeof syncPageIsolation === 'function') syncPageIsolation();
    const focus = state.returnFocus;
    state.returnFocus = null;
    if (focus instanceof HTMLElement && focus.isConnected && !focus.closest('[hidden], [inert]')) {
        focus.focus({ preventScroll: true });
    } else {
        document.getElementById('app-menu-toggle')?.focus({ preventScroll: true });
    }
}

function startOnboardingTour() {
    if (!onboardingTourRoot || onboardingTourState.active) return false;
    if (typeof topOpenModalBackdrop === 'function' && topOpenModalBackdrop()) return false;
    const state = onboardingTourState;
    state.originalView = { center: map.getCenter(), zoom: map.getZoom() };
    // Leaflet retains map._popup after it closes: only restore an actually
    // visible popup, otherwise Skip would unexpectedly open a vehicle card.
    const popup = map._popup;
    state.originalPopup = popup && map.hasLayer(popup) ? popup : null;
    state.returnFocus = document.activeElement;
    state.marker = onboardingTourExampleMarker();
    state.steps = onboardingTourSteps(state.marker);
    state.index = 0;
    state.previewOpened = false;
    state.active = true;
    onboardingTourRoot.hidden = false;
    showOnboardingTourStep(0);
    return true;
}

function maybeStartOnboardingTour() {
    const path = window.location.pathname;
    if (path !== '/' && path !== '/index.html') return;
    if (new URLSearchParams(window.location.search).has('photo')) return;
    if (onboardingTourSeen() || isAppMenuOpen()) return;
    if (typeof topOpenModalBackdrop === 'function' && topOpenModalBackdrop()) return;
    startOnboardingTour();
}

onboardingTourRoot?.querySelector('#onboarding-tour-next')?.addEventListener('click', () => {
    if (onboardingTourState.index === onboardingTourState.steps.length - 1) finishOnboardingTour();
    else showOnboardingTourStep(onboardingTourState.index + 1);
});
onboardingTourRoot?.querySelector('#onboarding-tour-back')?.addEventListener('click', () => {
    showOnboardingTourStep(onboardingTourState.index - 1);
});
onboardingTourRoot?.querySelector('#onboarding-tour-skip')?.addEventListener('click', finishOnboardingTour);

window.addEventListener('keydown', event => {
    if (!onboardingTourState.active) return;
    if (event.key === 'Escape') {
        event.preventDefault();
        event.stopImmediatePropagation();
        finishOnboardingTour();
        return;
    }
    if (event.key !== 'Tab') return;
    const buttons = [
        onboardingTourRoot.querySelector('#onboarding-tour-skip'),
        onboardingTourRoot.querySelector('#onboarding-tour-back'),
        onboardingTourRoot.querySelector('#onboarding-tour-next'),
    ].filter(button => button && !button.hidden);
    if (!buttons.length) return;
    const current = buttons.indexOf(document.activeElement);
    const targetIndex = event.shiftKey
        ? (current <= 0 ? buttons.length - 1 : current - 1)
        : (current < 0 || current === buttons.length - 1 ? 0 : current + 1);
    event.preventDefault();
    event.stopImmediatePropagation();
    buttons[targetIndex].focus({ preventScroll: true });
}, true);
window.addEventListener('resize', scheduleOnboardingTourPosition);
window.addEventListener('scroll', scheduleOnboardingTourPosition, true);
map.on('moveend popupopen popupclose', scheduleOnboardingTourPosition);
document.addEventListener('langchange', () => {
    if (onboardingTourState.active) showOnboardingTourStep(onboardingTourState.index);
});
