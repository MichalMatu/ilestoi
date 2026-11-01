/* First-visit IleStoi story. Real map loads below the overlay. */
const ILESTOI_INTRO_STORAGE_KEY = 'ilestoi-intro-v1-seen';
const ileStoiIntroState = { active: false, frame: null, seenOnEntry: false, lastFocus: null };
function hasSeenIleStoiIntro() {
    try { return localStorage.getItem(ILESTOI_INTRO_STORAGE_KEY) === '1'; } catch (_) { return false; }
}
ileStoiIntroState.seenOnEntry = hasSeenIleStoiIntro();
function shouldShowIleStoiIntro() {
    if (location.pathname !== '/' && location.pathname !== '/index.html') return false;
    if (location.search || location.hash) return false; // Do not interrupt photo/deep links.
    return !hasSeenIleStoiIntro();
}
function ileStoiIntroSuppressAutomaticTour() {
    return ileStoiIntroState.active || ileStoiIntroState.seenOnEntry || hasSeenIleStoiIntro();
}
function dismissIleStoiIntro() {
    if (!ileStoiIntroState.active) return;
    try { localStorage.setItem(ILESTOI_INTRO_STORAGE_KEY, '1'); } catch (_) {}
    const overlay = document.getElementById('ilestoi-intro-overlay');
    ileStoiIntroState.frame?.remove();
    ileStoiIntroState.frame = null;
    ileStoiIntroState.active = false;
    if (overlay) overlay.hidden = true;
    const focus = ileStoiIntroState.lastFocus;
    ileStoiIntroState.lastFocus = null;
    if (focus?.isConnected && typeof focus.focus === 'function') focus.focus({ preventScroll: true });
}
function startIleStoiIntro(force = false) {
    if (ileStoiIntroState.active || (!force && !shouldShowIleStoiIntro())) return false;
    const overlay = document.getElementById('ilestoi-intro-overlay');
    if (!overlay) return false;
    const iframe = document.createElement('iframe');
    const lang = typeof CURRENT_LANG !== 'undefined' && CURRENT_LANG === 'en' ? 'en' : 'pl';
    iframe.title = lang === 'en' ? 'How IleStoi works' : 'Jak działa IleStoi';
    iframe.src = '/intro?lang=' + lang;
    iframe.setAttribute('referrerpolicy', 'same-origin');
    iframe.addEventListener('load', () => { if (ileStoiIntroState.frame === iframe) iframe.focus(); });
    ileStoiIntroState.lastFocus = document.activeElement;
    ileStoiIntroState.frame = iframe;
    ileStoiIntroState.active = true;
    overlay.hidden = false;
    overlay.append(iframe);
    return true;
}
window.addEventListener('message', (event) => {
    if (!ileStoiIntroState.active || event.origin !== location.origin) return;
    if (event.source !== ileStoiIntroState.frame?.contentWindow) return;
    if (event.data?.type === 'ilestoi:intro:dismiss') dismissIleStoiIntro();
});
startIleStoiIntro();
