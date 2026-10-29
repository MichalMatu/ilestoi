"""Contract checks for accessible map-native first-visit walkthrough."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class GuidedTourContracts(unittest.TestCase):
    def test_native_tour_is_loaded_before_startup(self):
        index = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("<!-- include:partials/onboarding_tour.html -->", index)
        self.assertIn('src="/app/onboarding_tour.js"', index)
        self.assertLess(index.index('src="/app/onboarding_tour.js"'), index.index('src="/app/startup.js"'))
        self.assertIn('@import url("/styles/onboarding_tour.css");', (WEB / "styles.css").read_text(encoding="utf-8"))

    def test_first_visit_is_replayable_and_has_skip_keyboard_support(self):
        tour = (WEB / "app" / "onboarding_tour.js").read_text(encoding="utf-8")
        shell = (WEB / "partials" / "app_shell.html").read_text(encoding="utf-8")
        markup = (WEB / "partials" / "onboarding_tour.html").read_text(encoding="utf-8")
        startup = (WEB / "app" / "startup.js").read_text(encoding="utf-8")
        ui = (WEB / "ui.js").read_text(encoding="utf-8")
        self.assertIn("ONBOARDING_TOUR_STORAGE_KEY", tour)
        self.assertIn("function maybeStartOnboardingTour()", tour)
        self.assertIn("function startOnboardingTour()", tour)
        self.assertIn("function finishOnboardingTour(event)", tour)
        self.assertIn("loadFieldPhotos().finally(", startup)
        self.assertIn('id="app-menu-open-tour"', shell)
        self.assertIn('id="onboarding-tour-skip"', markup)
        self.assertIn('role="dialog" aria-modal="true"', markup)
        self.assertIn("event.key === 'Escape'", tour)
        self.assertIn("event.key !== 'Tab'", tour)
        self.assertIn("else if (tourOpen)", ui)

    def test_tour_never_submits_or_changes_filters(self):
        tour = (WEB / "app" / "onboarding_tour.js").read_text(encoding="utf-8")
        for mutation in (
            "submitReportPdf(",
            "apiPostJson(",
            "apiJson(",
            "toggleVehicleLayer(",
            "toggleCadastralLayer(",
            "openFieldPhotoUploadModal(",
            "map.setZoom(",
        ):
            self.assertNotIn(mutation, tour)
        self.assertIn("state.marker.openPopup()", tour)

    def test_translations_are_complete(self):
        for language in ("pl", "en"):
            dict_source = (WEB / "i18n" / f"{language}.js").read_text(encoding="utf-8")
            for key in (
                "tour.reopen",
                "tour.progress",
                "tour.next",
                "tour.back",
                "tour.skip",
                "tour.finish",
                "tour.welcomeTitle",
                "tour.welcomeBody",
                "tour.mapTitle",
                "tour.mapBody",
                "tour.mapEmptyBody",
                "tour.vehicleTitle",
                "tour.vehicleBody",
                "tour.reportTitle",
                "tour.reportBody",
                "tour.addTitle",
                "tour.addBody",
                "tour.addUnavailableBody",
                "tour.layersTitle",
                "tour.layersBody",
                "tour.sourcesTitle",
                "tour.sourcesBody",
                "tour.doneTitle",
                "tour.doneBody",
            ):
                self.assertIn(f"'{key}':", dict_source)


if __name__ == "__main__":
    unittest.main()
