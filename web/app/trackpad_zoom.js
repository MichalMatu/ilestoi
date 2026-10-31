// Continuous Mac trackpad zoom, adapted from PhotoMap's verified Leaflet 1.9 controller.
// Keep mouse wheel and phone touch gestures on their native Leaflet paths.
const SMOOTH_TRACKPAD_ZOOM = Object.freeze({
    idleResetMs: 240,
    maxEventDeltaPx: 120,
    zoomPerPixel: 1 / 200,
    smoothingFactor: 0.6,
    settleEpsilon: 0.001,
    maxSmoothScrollDeltaPx: 40,
});

function isSmoothTrackpadWheelEvent(event, gestureActive = false) {
    return event.deltaMode === 0
        && Number.isFinite(event.deltaY)
        && event.deltaY !== 0
        && (event.ctrlKey || gestureActive || Math.abs(event.deltaY) < SMOOTH_TRACKPAD_ZOOM.maxSmoothScrollDeltaPx);
}

function trackpadTargetZoom(currentTarget, deltaY, minZoom, maxZoom) {
    if (!Number.isFinite(currentTarget) || !Number.isFinite(deltaY) || deltaY === 0) return currentTarget;
    const boundedDelta = Math.max(-SMOOTH_TRACKPAD_ZOOM.maxEventDeltaPx,
        Math.min(SMOOTH_TRACKPAD_ZOOM.maxEventDeltaPx, deltaY));
    return Math.max(minZoom, Math.min(maxZoom,
        currentTarget - boundedDelta * SMOOTH_TRACKPAD_ZOOM.zoomPerPixel));
}

function approachTrackpadZoom(current, target) {
    if (Math.abs(target - current) <= SMOOTH_TRACKPAD_ZOOM.settleEpsilon) return target;
    const next = current + (target - current) * SMOOTH_TRACKPAD_ZOOM.smoothingFactor;
    return Math.abs(target - next) <= SMOOTH_TRACKPAD_ZOOM.settleEpsilon ? target : next;
}

function installSmoothTrackpadZoom(map) {
    const container = map.getContainer();
    let targetZoom = null;
    let anchor = null;
    let originalSnap = null;
    let frameId = null;
    let resetTimer = null;
    let started = false;
    let gestureEnded = false;

    function endGesture() {
        if (frameId !== null) {
            window.cancelAnimationFrame(frameId);
            frameId = null;
        }
        if (resetTimer !== null) {
            window.clearTimeout(resetTimer);
            resetTimer = null;
        }
        if (started) {
            started = false;
            map._moveEnd(true);
        }
        if (originalSnap !== null) {
            map.options.zoomSnap = originalSnap;
            originalSnap = null;
        }
        targetZoom = null;
        anchor = null;
        gestureEnded = false;
    }

    function animateZoom() {
        frameId = null;
        if (targetZoom === null || anchor === null) return;
        if (!map.scrollWheelZoom.enabled()) {
            endGesture();
            return;
        }
        const current = map.getZoom();
        const next = approachTrackpadZoom(current, targetZoom);
        if (next !== current) {
            if (!started) {
                map.stop();
                map._moveStart(true);
                started = true;
            }

            // Project around the cursor without generating zoomend/moveend per frame.
            // Leaflet's _move keeps tile/marker positions live until a single _moveEnd.
            const scale = map.getZoomScale(next, current);
            const half = map.getSize().divideBy(2);
            const offset = anchor.subtract(half).multiplyBy(1 - 1 / scale);
            const center = map.containerPointToLatLng(half.add(offset));
            map._move(center, next, { pinch: true, round: false });
        }
        if (next !== targetZoom) {
            frameId = window.requestAnimationFrame(animateZoom);
        } else if (gestureEnded) {
            endGesture();
        }
    }

    function handleWheel(event) {
        if (!isSmoothTrackpadWheelEvent(event, originalSnap !== null)) {
            if (originalSnap !== null) endGesture();
            return;
        }
        event.preventDefault();
        event.stopImmediatePropagation();

        if (!map.scrollWheelZoom.enabled()) {
            endGesture();
            return;
        }
        if (originalSnap === null) {
            originalSnap = map.options.zoomSnap ?? 1;
            map.options.zoomSnap = 0;
        }
        if (resetTimer !== null) window.clearTimeout(resetTimer);
        gestureEnded = false;
        targetZoom = trackpadTargetZoom(
            targetZoom ?? map.getZoom(), event.deltaY, map.getMinZoom(), map.getMaxZoom()
        );
        anchor = map.mouseEventToContainerPoint(event);
        if (frameId === null) frameId = window.requestAnimationFrame(animateZoom);
        resetTimer = window.setTimeout(() => {
            resetTimer = null;
            gestureEnded = true;
            if (frameId === null) endGesture();
        }, SMOOTH_TRACKPAD_ZOOM.idleResetMs);
    }

    // Capture before Leaflet's native wheel listener. Wheel stays passive:false
    // so Safari can cancel page zoom for pinch gestures over the map.
    container.addEventListener('wheel', handleWheel, { capture: true, passive: false });
    return () => {
        container.removeEventListener('wheel', handleWheel, { capture: true });
        endGesture();
    };
}
