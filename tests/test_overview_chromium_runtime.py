"""Real Chromium smoke test for aggregate photo markers and drill-down."""

import unittest

from test_ui_accessibility_runtime import CHROMIUM, ROOT_DIR, run_chromium_document


@unittest.skipUnless(CHROMIUM, "Chromium is required for overview marker runtime validation")
class OverviewChromiumRuntimeTests(unittest.TestCase):
    def test_overview_clusters_render_and_zoom_in_real_chromium(self):
        marker_js = (ROOT_DIR / "web" / "app" / "map_markers.js").read_text(encoding="utf-8")
        photo_js = (ROOT_DIR / "web" / "app" / "field_photos.js").read_text(encoding="utf-8")
        overview_js = (ROOT_DIR / "web" / "app" / "overview_clusters.js").read_text(encoding="utf-8")
        marker_js = marker_js.replace("</script", r"<\/script")
        photo_js = photo_js.replace("</script", r"<\/script")
        overview_js = overview_js.replace("</script", r"<\/script")
        document = (
            """<!doctype html><html><head><title>pending</title></head><body>
            <main id="map"></main>
            <script>
                const FIELD_PHOTOS_URL = '/api/field-photos';
                let adminAuthenticated = false;
                let pendingVehiclePhotoFocusId = '';
                let vehicleInsuranceFilter = 'all';
                let vehicleStandingFilterDays = 0;
                let vehiclePhotoFilter = 'off';
                let vehicleResolutionFilter = 'all';
                const VEHICLE_FILTER_ALL = 'all';
                const VEHICLE_STANDING_FILTER_OFF = 0;
                const VEHICLE_PHOTO_FILTER_OFF = 'off';
                let zoom = 8;
                const markers = [];
                const fits = [];
                const requests = [];
                const map = {
                    getZoom: () => zoom,
                    getBounds: () => ({
                        getWest: () => 16, getSouth: () => 50,
                        getEast: () => 18, getNorth: () => 52,
                    }),
                    getCenter: () => ({ lat: 51, lng: 17 }),
                    fitBounds: bounds => fits.push(bounds),
                    removeLayer() {},
                };
                const L = {
                    divIcon: options => options,
                    marker: (point, options) => {
                        const handlers = {};
                        return {
                            point, options, handlers,
                            addTo() { markers.push(this); return this; },
                            bindTooltip() { return this; },
                            getElement: () => document.createElement('span'),
                            on(event, callback) { handlers[event] = callback; return this; },
                        };
                    },
                };
                function t(key, params = {}) { return key + (params.n ?? ''); }
                function apiJson(url) {
                    requests.push(url);
                    return Promise.resolve({
                        status: 'ok', clusters: [{
                            lat: 51, lon: 17, total: 5, vehicles: 2,
                            infrastructure: 1, smoke: 1, pending: 1,
                        }],
                    });
                }
            </script><script>"""
            + marker_js
            + """</script><script>"""
            + photo_js
            + """</script><script>"""
            + overview_js
            + """</script><script>
                vehicleLayerAllowed = () => true;
                fieldPhotoIssueVisible = () => true;
                pendingFieldPhotoLayerAllowed = () => true;
                placeVehicleMarkers = () => {};
                updateLayerCounters = () => {};
                (async () => {
                    await loadFieldPhotos();
                    const marker = markers[0];
                    marker.handlers.click();
                    const result = {
                        overview: fieldPhotoOverviewActive,
                        count: markers.length,
                        html: marker.options.icon.html,
                        requests,
                        fits,
                        loadState: document.getElementById('field-photo-load-state').hidden,
                    };
                    document.title = 'RESULT:' + btoa(JSON.stringify(result));
                })().catch(error => {
                    document.title = 'ERROR:' + btoa(String(error.stack || error));
                });
            </script></body></html>"""
        )
        result = run_chromium_document(document, prefix="ilestoi-overview-browser-", virtual_time_budget=2500)
        self.assertTrue(result["overview"])
        self.assertEqual(result["count"], 1)
        self.assertIn("map-overview-cluster", result["html"])
        self.assertIn(">5</", result["html"])
        self.assertEqual(len(result["requests"]), 1)
        self.assertIn("/api/field-photos/clusters?bbox=", result["requests"][0])
        self.assertEqual(len(result["fits"]), 1)
        self.assertTrue(result["loadState"])

