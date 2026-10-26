const modalFocusStack = [];
const pageIsolationRecords = new Map();
let appMenuReturnFocus = null;
let modalTitleSequence = 0;

function visibleFocusableElements(container) {
    if (!(container instanceof Element)) return [];
    const selector = [
        'a[href]',
        'button:not([disabled])',
        'input:not([disabled]):not([type="hidden"])',
        'select:not([disabled])',
        'textarea:not([disabled])',
        '[contenteditable="true"]',
        '[tabindex]:not([tabindex="-1"])',
    ].join(',');
    return Array.from(container.querySelectorAll(selector)).filter(element => {
        if (!(element instanceof HTMLElement) || element.closest('[hidden], [inert]')) return false;
        const style = window.getComputedStyle(element);
        return style.display !== 'none' && style.visibility !== 'hidden';
    });
}

function elementCanReceiveFocus(element) {
    if (!(element instanceof HTMLElement) || !element.isConnected || element.closest('[hidden], [inert]')) return false;
    const style = window.getComputedStyle(element);
    return style.display !== 'none' && style.visibility !== 'hidden';
}

function focusWithoutScroll(element) {
    if (!elementCanReceiveFocus(element)) return false;
    element.focus({ preventScroll: true });
    return document.activeElement === element;
}

function rememberAndIsolate(element) {
    if (!(element instanceof HTMLElement) || element.tagName === 'SCRIPT') return;
    if (!pageIsolationRecords.has(element)) {
        pageIsolationRecords.set(element, {
            inert: element.inert,
            ariaHidden: element.getAttribute('aria-hidden'),
        });
    }
    element.inert = true;
    element.setAttribute('aria-hidden', 'true');
}

function restorePageIsolation() {
    pageIsolationRecords.forEach((state, element) => {
        if (!element.isConnected) return;
        element.inert = state.inert;
        if (state.ariaHidden === null) element.removeAttribute('aria-hidden');
        else element.setAttribute('aria-hidden', state.ariaHidden);
    });
    pageIsolationRecords.clear();
}

function syncPageIsolation() {
    restorePageIsolation();
    const topModal = topOpenModalBackdrop();
    const tour = document.getElementById('onboarding-tour');
    const tourOpen = tour && !tour.hidden;
    let allowed = null;
    if (topModal) {
        topModal.setAttribute('aria-hidden', 'false');
        allowed = new Set([topModal]);
    } else if (isAppMenuOpen()) {
        // Keep both the active menu and its guided tour reachable by assistive technology.
        allowed = new Set([
            document.getElementById('app-menu'),
            document.getElementById('app-menu-scrim'),
            document.getElementById('app-menu-drawer'),
            tourOpen ? tour : null,
        ].filter(Boolean));
    } else if (tourOpen) {
        allowed = new Set([tour]);
    }
    if (!allowed) return;
    Array.from(document.body?.children || []).forEach(element => {
        if (!allowed.has(element)) rememberAndIsolate(element);
    });
}

function restoreOverlayFocus(preferred = null) {
    const topModal = topOpenModalBackdrop();
    const modalDialog = topModal?.querySelector('.modal');
    const fallback = modalDialog || document.getElementById('app-menu-toggle') || document.getElementById('map');
    requestAnimationFrame(() => {
        if (!focusWithoutScroll(preferred)) focusWithoutScroll(fallback);
    });
}

function cycleOverlayFocus(event, elements) {
    const focusable = elements.filter(elementCanReceiveFocus);
    if (!focusable.length) return false;
    const currentIndex = focusable.indexOf(document.activeElement);
    let nextIndex;
    if (event.shiftKey) {
        nextIndex = currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1;
    } else {
        nextIndex = currentIndex < 0 || currentIndex >= focusable.length - 1 ? 0 : currentIndex + 1;
    }
    event.preventDefault();
    focusWithoutScroll(focusable[nextIndex]);
    return true;
}

// ─── APP MENU ───────────────────────────────────
function isAppMenuOpen() {
    return Boolean(document.body?.classList.contains('app-menu-open'));
}

function updateAppMenuState() {
    const isOpen = isAppMenuOpen();
    const toggle = document.getElementById('app-menu-toggle');
    const drawer = document.getElementById('app-menu-drawer');
    const scrim = document.getElementById('app-menu-scrim');
    if (toggle) {
        const label = isOpen ? t('appMenu.close') : t('appMenu.open');
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        toggle.setAttribute('aria-label', label);
        toggle.title = label;
    }
    if (drawer) drawer.hidden = !isOpen;
    if (scrim) scrim.hidden = !isOpen;
}

function setAppMenuOpen(open, options = {}) {
    const nextOpen = Boolean(open);
    const wasOpen = isAppMenuOpen();
    if (nextOpen && !wasOpen) {
        appMenuReturnFocus = elementCanReceiveFocus(document.activeElement)
            ? document.activeElement
            : document.getElementById('app-menu-toggle');
    }
    document.body?.classList.toggle('app-menu-open', nextOpen);
    updateAppMenuState();
    syncPageIsolation();
    if (nextOpen && !wasOpen) {
        const drawer = document.getElementById('app-menu-drawer');
        const initialFocus = visibleFocusableElements(drawer)[0];
        requestAnimationFrame(() => focusWithoutScroll(initialFocus));
    } else if (!nextOpen && wasOpen && options.restoreFocus !== false && !topOpenModalBackdrop()) {
        restoreOverlayFocus(appMenuReturnFocus || document.getElementById('app-menu-toggle'));
    }
}

function toggleAppMenu() {
    setAppMenuOpen(!isAppMenuOpen());
}

function closeAppMenu(options = {}) {
    setAppMenuOpen(false, options);
}

updateAppMenuState();
document.addEventListener('langchange', updateAppMenuState);

// ─── LANGUAGE TOGGLE ───────────────────────────
function toggleLang() {
    setLang(CURRENT_LANG === 'pl' ? 'en' : 'pl');
}

function updateLangLabel() {
    document.querySelectorAll('.lang-label').forEach(el => {
        el.textContent = CURRENT_LANG === 'pl' ? 'PL' : 'EN';
    });
}

updateLangLabel();
document.addEventListener('langchange', updateLangLabel);

// ─── PARKING COSTS INFO ────────────────────────
function setParkingCostsTab(tab) {
    const selectedTab = String(tab || 'owner');
    document.querySelectorAll('[data-parking-costs-tab]').forEach(button => {
        const isActive = button.dataset.parkingCostsTab === selectedTab;
        button.classList.toggle('is-active', isActive);
        button.setAttribute('aria-selected', isActive ? 'true' : 'false');
        button.tabIndex = isActive ? 0 : -1;
    });
    document.querySelectorAll('[data-parking-costs-panel]').forEach(panel => {
        const isActive = panel.dataset.parkingCostsPanel === selectedTab;
        panel.classList.toggle('is-active', isActive);
        panel.hidden = !isActive;
    });
}

function openParkingCostsModal() {
    setParkingCostsTab('owner');
    openModal('modal-parking-costs', { initialFocus: '#parking-costs-tab-owner' });
}

document.querySelector('.parking-costs-tabs')?.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const tabs = Array.from(document.querySelectorAll('[data-parking-costs-tab]'))
        .filter(button => !button.disabled && !button.hidden);
    if (!tabs.length) return;
    const currentIndex = Math.max(0, tabs.indexOf(document.activeElement));
    let nextIndex = currentIndex;
    if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    else if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = tabs.length - 1;
    event.preventDefault();
    event.stopPropagation();
    setParkingCostsTab(tabs[nextIndex].dataset.parkingCostsTab);
    focusWithoutScroll(tabs[nextIndex]);
});

setParkingCostsTab(document.querySelector('[data-parking-costs-tab][aria-selected="true"]')?.dataset.parkingCostsTab);

// ─── MODALS ───────────────────────────────────────
let pendingConfirmResolve = null;

function prepareModalAccessibility() {
    document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
        const dialog = backdrop.querySelector('.modal');
        if (!dialog) return;
        dialog.setAttribute('role', 'dialog');
        dialog.setAttribute('aria-modal', 'true');
        if (!dialog.hasAttribute('tabindex')) dialog.tabIndex = -1;
        const title = dialog.querySelector('.modal-header h2');
        if (title) {
            if (!title.id) {
                modalTitleSequence += 1;
                title.id = `${backdrop.id || 'modal'}-title-${modalTitleSequence}`;
            }
            dialog.setAttribute('aria-labelledby', title.id);
        }
        backdrop.setAttribute('aria-hidden', backdrop.hidden ? 'true' : 'false');
    });
}

function modalFocusState(backdrop) {
    return modalFocusStack.find(state => state.backdrop === backdrop) || null;
}

function removeModalFocusState(backdrop) {
    const index = modalFocusStack.findIndex(state => state.backdrop === backdrop);
    if (index < 0) return null;
    return modalFocusStack.splice(index, 1)[0];
}

function modalInitialFocus(modal, initialFocus) {
    if (initialFocus instanceof HTMLElement) return initialFocus;
    if (typeof initialFocus === 'string') return modal.querySelector(initialFocus);
    return modal.querySelector('[autofocus]') || modal.querySelector('.modal');
}

function openModal(id, options = {}) {
    const modal = document.getElementById(id);
    if (!modal) return;
    const preserveOpen = Boolean(options.preserveOpen);
    const previousState = modalFocusState(modal);
    const previousTop = topOpenModalBackdrop();
    let returnFocus = previousState?.returnFocus || document.activeElement;
    if (!preserveOpen && previousTop && previousTop !== modal) {
        returnFocus = modalFocusState(previousTop)?.returnFocus || returnFocus;
    }
    if (!preserveOpen) {
        document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
            if (backdrop !== modal) hideModalBackdrop(backdrop, { restoreFocus: false });
        });
    }
    removeModalFocusState(modal);
    modalFocusStack.push({ backdrop: modal, returnFocus });
    modal.hidden = false;
    modal.setAttribute('aria-hidden', 'false');
    syncPageIsolation();
    const initialFocus = modalInitialFocus(modal, options.initialFocus);
    requestAnimationFrame(() => {
        if (topOpenModalBackdrop() === modal) focusWithoutScroll(initialFocus);
    });
}

function openModalBackdrops() {
    return Array.from(document.querySelectorAll('.modal-backdrop:not([hidden])'));
}

function topOpenModalBackdrop() {
    for (let index = modalFocusStack.length - 1; index >= 0; index -= 1) {
        const backdrop = modalFocusStack[index].backdrop;
        if (backdrop?.isConnected && !backdrop.hidden) return backdrop;
    }
    return openModalBackdrops().at(-1) || null;
}

function hideModalBackdrop(backdrop, options = {}) {
    if (!(backdrop instanceof Element) || !backdrop.classList.contains('modal-backdrop') || backdrop.hidden) return;
    const wasTop = topOpenModalBackdrop() === backdrop;
    const state = removeModalFocusState(backdrop);
    backdrop.dispatchEvent(new CustomEvent('modalclose', { detail: { id: backdrop.id } }));
    backdrop.hidden = true;
    backdrop.setAttribute('aria-hidden', 'true');
    syncPageIsolation();
    if (wasTop && options.restoreFocus !== false) restoreOverlayFocus(state?.returnFocus);
}

function closeModal(target) {
    if (target instanceof Element && target.classList.contains('modal-backdrop')) {
        hideModalBackdrop(target);
    } else {
        hideModalBackdrop(topOpenModalBackdrop());
    }
}

document.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const topModal = topOpenModalBackdrop();
    if (topModal) {
        const dialog = topModal.querySelector('.modal');
        const focusable = visibleFocusableElements(topModal);
        if (!focusable.length && dialog) focusable.push(dialog);
        cycleOverlayFocus(event, focusable);
        return;
    }
    if (!isAppMenuOpen()) return;
    const toggle = document.getElementById('app-menu-toggle');
    const drawer = document.getElementById('app-menu-drawer');
    cycleOverlayFocus(event, [toggle, ...visibleFocusableElements(drawer)].filter(Boolean));
}, true);

document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const confirmModal = document.getElementById('modal-confirm');
    if (confirmModal && !confirmModal.hidden && topOpenModalBackdrop() === confirmModal) {
        closeConfirmModal(false);
        return;
    }
    const adminModal = document.getElementById('modal-admin-login');
    if (adminModal && !adminModal.hidden && topOpenModalBackdrop() === adminModal) {
        closeAdminLoginModal(false);
        return;
    }
    if (topOpenModalBackdrop()) {
        closeModal();
        return;
    }
    if (isAppMenuOpen()) closeAppMenu();
});

function confirmAction({ title, message, confirmLabel } = {}) {
    if (pendingConfirmResolve) {
        pendingConfirmResolve(false);
        pendingConfirmResolve = null;
    }
    return new Promise(resolve => {
        pendingConfirmResolve = resolve;
        const titleEl = document.getElementById('confirm-title');
        const messageEl = document.getElementById('confirm-message');
        const submit = document.getElementById('confirm-submit');
        const cancel = document.getElementById('confirm-cancel');
        if (titleEl) titleEl.textContent = title || t('modal.confirm.title');
        if (messageEl) messageEl.textContent = message || '';
        if (submit) submit.textContent = confirmLabel || t('modal.confirm.confirm');
        if (cancel) cancel.textContent = t('modal.confirm.cancel');
        openModal('modal-confirm', { preserveOpen: true, initialFocus: '#confirm-submit' });
    });
}

function closeConfirmModal(confirmed = false, target = null) {
    if (target instanceof Element && !target.classList.contains('modal-backdrop')) return;
    const modal = document.getElementById('modal-confirm');
    if (modal) hideModalBackdrop(modal);
    if (pendingConfirmResolve) {
        pendingConfirmResolve(Boolean(confirmed));
        pendingConfirmResolve = null;
    }
}

function submitConfirmAction(event) {
    event.preventDefault();
    closeConfirmModal(true);
}

function initializeGlobalStatusToast() {
    const status = document.getElementById('status');
    if (!status || typeof MutationObserver !== 'function') return;
    let clearTimer = null;
    const observer = new MutationObserver(() => {
        if (clearTimer) window.clearTimeout(clearTimer);
        if (!status.textContent.trim()) return;
        clearTimer = window.setTimeout(() => {
            status.textContent = '';
            status.className = 'global-status-toast';
        }, 7000);
    });
    observer.observe(status, { childList: true, characterData: true, subtree: true });
}

prepareModalAccessibility();
initializeGlobalStatusToast();
