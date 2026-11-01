L.control.zoom({ position: 'bottomright' }).addTo(map);

(() => {
    const range = document.getElementById('year-range');
    range.step = 1;
    updateMapSourceUi();
    range.addEventListener('input', e => setMapSourceByVisiblePosition(e.target.value));
    document.getElementById('year-prev').addEventListener('click', () => moveMapSource(-1));
    document.getElementById('year-next').addEventListener('click', () => moveMapSource(1));
    document.addEventListener('keydown', e => {
        if (e.target.matches('input, select, textarea')) return;
        if (document.querySelector('.modal-backdrop:not([hidden])')) return;
        if (!isMapSourceSliderVisible()) return;
        if (e.key === 'ArrowLeft') { moveMapSource(-1); e.preventDefault(); }
        else if (e.key === 'ArrowRight') { moveMapSource(1); e.preventDefault(); }
    });
})();
