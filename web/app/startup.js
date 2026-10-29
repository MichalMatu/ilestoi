refreshAdminStatus().finally(() => {
    map.on('moveend', scheduleFieldPhotoViewportLoad);
    loadFieldPhotos().finally(() => window.setTimeout(maybeStartOnboardingTour, 450));
});
document.addEventListener('langchange', updateLayerCounters);
