refreshAdminStatus().finally(() => {
    map.on('moveend', scheduleFieldPhotoViewportLoad);
    map.on('popupopen', () => { fieldPhotoPopupOpen = true; });
    map.on('popupclose', () => {
        fieldPhotoPopupOpen = false;
        scheduleFieldPhotoViewportLoad();
    });
    loadFieldPhotos().finally(() => window.setTimeout(maybeStartOnboardingTour, 450));
});
document.addEventListener('langchange', updateLayerCounters);
