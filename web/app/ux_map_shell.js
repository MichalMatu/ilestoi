/* Responsive IleStoi map shell. The existing map, filters and upload handlers stay authoritative. */
const UX_MAP_PANEL_NAMES = ['vehicles', 'layers', 'tools'];
const uxMapPanelMedia = window.matchMedia('(max-width: 720px)');
let uxMapPanelActive = 'vehicles';
let uxMapSheetExpanded = false;

function updateUxMapPanelState() {
    const isMobile = uxMapPanelMedia.matches;
    document.querySelectorAll('[data-ux-tab]').forEach(button => {
        const selected = button.dataset.uxTab === uxMapPanelActive;
        button.setAttribute('aria-selected', String(selected));
        button.tabIndex = selected ? 0 : -1;
    });
    document.querySelectorAll('[data-ux-panel]').forEach(panel => {
        const active = panel.dataset.uxPanel === uxMapPanelActive;
        panel.hidden = isMobile && !active;
        panel.setAttribute('role', isMobile ? 'tabpanel' : 'region');
        panel.setAttribute('aria-labelledby', isMobile
            ? 'ux-tab-' + panel.dataset.uxPanel
            : 'ux-heading-' + panel.dataset.uxPanel);
    });
    const toolsNav = document.querySelector('.ux-tools-nav');
    if (toolsNav) toolsNav.hidden = isMobile && uxMapPanelActive !== 'tools';
}

function setUxMapPanelTab(tab, options = {}) {
    if (!UX_MAP_PANEL_NAMES.includes(tab)) return false;
    uxMapPanelActive = tab;
    updateUxMapPanelState();
    if (options.focus) document.getElementById('ux-tab-' + tab)?.focus();
    return true;
}

function setUxMapSheetExpanded(expanded) {
    uxMapSheetExpanded = Boolean(expanded);
    document.body?.classList.toggle('ux-sheet-expanded', uxMapSheetExpanded);
    const handle = document.getElementById('ux-sheet-handle');
    if (!handle) return;
    handle.setAttribute('aria-expanded', String(uxMapSheetExpanded));
    const label = t(uxMapSheetExpanded ? 'ux.collapseSheet' : 'ux.expandSheet');
    handle.setAttribute('aria-label', label);
    handle.title = label;
}

document.querySelectorAll('[data-ux-tab]').forEach(button => {
    button.addEventListener('click', () => setUxMapPanelTab(button.dataset.uxTab));
    button.addEventListener('keydown', event => {
        if (!uxMapPanelMedia.matches) return;
        const current = UX_MAP_PANEL_NAMES.indexOf(uxMapPanelActive);
        let next = current;
        if (event.key === 'ArrowRight') next = (current + 1) % UX_MAP_PANEL_NAMES.length;
        else if (event.key === 'ArrowLeft') next = (current + UX_MAP_PANEL_NAMES.length - 1) % UX_MAP_PANEL_NAMES.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = UX_MAP_PANEL_NAMES.length - 1;
        else return;
        event.preventDefault();
        setUxMapPanelTab(UX_MAP_PANEL_NAMES[next], { focus: true });
    });
});

document.getElementById('ux-sheet-handle')?.addEventListener('click', () => {
    setUxMapSheetExpanded(!uxMapSheetExpanded);
});
document.getElementById('ux-sheet-close')?.addEventListener('click', () => closeAppMenu());
document.getElementById('map-add-field-photo')?.addEventListener('click', () => {
    openFieldPhotoUploadFromPanel();
});
document.getElementById('map-open-filters')?.addEventListener('click', () => {
    setUxMapPanelTab('vehicles');
    setAppMenuOpen(true);
});

uxMapPanelMedia.addEventListener('change', updateUxMapPanelState);
document.addEventListener('langchange', () => setUxMapSheetExpanded(uxMapSheetExpanded));
updateUxMapPanelState();
setUxMapSheetExpanded(false);
