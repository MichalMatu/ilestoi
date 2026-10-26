refreshAdminStatus().finally(() => {
    loadFieldPhotos().finally(() => window.setTimeout(maybeStartOnboardingTour, 450));
});
document.addEventListener('langchange', updateLayerCounters);
