"""Regression checks for the public street-label overlay and admin login form."""

import unittest
from pathlib import Path

from app.http.responses import security_response_headers
from app.http.static_files import render_web_template

ROOT = Path(__file__).resolve().parents[1]


class PublicMapOverlayContracts(unittest.TestCase):
    def test_map_uses_gugik_wms_street_labels_without_carto_key(self):
        config_js = (ROOT / "web/config.js").read_text(encoding="utf-8")
        map_js = (ROOT / "web/app/map_sources.js").read_text(encoding="utf-8")

        self.assertIn(
            "const STREET_LABELS_WMS_URL = 'https://mapy.geoportal.gov.pl/wss/ext/KrajowaIntegracjaNumeracjiAdresowej';",
            config_js,
        )
        self.assertIn("return L.tileLayer.wms(STREET_LABELS_WMS_URL, {", map_js)
        self.assertIn("layers: 'A08_Ulice'", map_js)
        self.assertIn("transparent: true", map_js)
        self.assertIn("format: 'image/png'", map_js)
        self.assertNotIn("basemaps.cartocdn.com", config_js + map_js)
        self.assertNotIn("CARTO_LABELS_TILE_URL", config_js + map_js)

    def test_strict_csp_allows_official_image_service_only(self):
        csp = security_response_headers()["Content-Security-Policy"]
        image_directive = csp.split("img-src ", 1)[1].split(";", 1)[0]
        self.assertIn("https://mapy.geoportal.gov.pl", image_directive)
        self.assertNotIn("basemaps.cartocdn.com", csp)
        self.assertIn("connect-src 'self'", csp)

    def test_osm_source_sends_allowed_origin_referer_and_displays_license(self):
        headers = security_response_headers()
        self.assertEqual(headers["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertIn("https://*.openstreetmap.org", headers["Content-Security-Policy"])
        config_js = (ROOT / "web/config.js").read_text(encoding="utf-8")
        self.assertIn("https://tile.openstreetmap.org/{z}/{x}/{y}.png", config_js)
        self.assertIn('https://www.openstreetmap.org/copyright', config_js)
        self.assertIn("labelsOverlay: false", config_js)
        self.assertNotIn('Referrer-Policy": "same-origin"', (ROOT / "app/http/responses.py").read_text(encoding="utf-8"))

    def test_map_swap_retains_last_good_map_on_failed_tile_load(self):
        js = (ROOT / "web/app/map_sources.js").read_text(encoding="utf-8")
        self.assertIn("let mapSourcePendingLayer = null;", js)
        self.assertIn("let mapSourceStableIndex = currentMapSourceIndex;", js)
        self.assertIn("successfulTile = true;", js)
        self.assertIn("leaflet-tile--retrying", js)
        self.assertIn("if (finished || swapToken !== mapSourceSwapToken || !successfulTile) return;", js)
        self.assertIn("currentMapSourceIndex = mapSourceStableIndex;", js)
        self.assertNotIn("setTimeout(() => {\\n        finishSwap();", js)

    def test_password_form_has_hidden_autocomplete_username(self):
        html = render_web_template("index.html")
        start = html.index('id="admin-login-form"')
        end = html.index("</form>", start)
        form = html[start:end]
        self.assertIn('name="username" autocomplete="username" value="admin"', form)
        self.assertIn('hidden tabindex="-1" aria-hidden="true"', form)
        self.assertIn('id="admin-password-input"', form)
        self.assertIn('autocomplete="current-password"', form)


if __name__ == "__main__":
    unittest.main()
