import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


class MapPinStyleContracts(unittest.TestCase):
    def test_vehicle_pin_and_filter_selects_match_current_ui(self):
        html = (ROOT_DIR / "web" / "partials" / "app_shell.html").read_text(encoding="utf-8")
        css = (ROOT_DIR / "web" / "styles" / "map_pins.css").read_text(encoding="utf-8")
        layer_css = (ROOT_DIR / "web" / "styles" / "map_layers.css").read_text(encoding="utf-8")
        markers_js = (ROOT_DIR / "web" / "app" / "map_markers.js").read_text(encoding="utf-8")
        vehicle_layer_js = (ROOT_DIR / "web" / "app" / "vehicle_layer.js").read_text(encoding="utf-8")
        resolution_js = (ROOT_DIR / "web" / "app" / "vehicle_resolution.js").read_text(encoding="utf-8")
        field_photos_js = (ROOT_DIR / "web" / "app" / "field_photos.js").read_text(encoding="utf-8")

        # The visible selectors replaced the retired cycling filter buttons.
        self.assertIn('class="vehicle-filter-choice-grid"', html)
        selectors = (
            ("vehicle-insurance-select", "setVehicleInsuranceFilter(this.value)", vehicle_layer_js),
            ("vehicle-standing-select", "setVehicleStandingFilterDays(Number(this.value))", vehicle_layer_js),
            ("vehicle-photo-select", "setVehiclePhotoFilter(this.value)", vehicle_layer_js),
            ("vehicle-resolution-select", "setVehicleResolutionFilter(this.value)", resolution_js),
        )
        for control, handler, source in selectors:
            with self.subTest(control=control):
                self.assertIn(f'id="{control}"', html)
                self.assertIn(f'onchange="{handler}"', html)
                self.assertIn(f"function {handler.split('(')[0]}", source)
        self.assertNotIn('class="vehicle-cycle-filter"', html)
        self.assertIn(".vehicle-filter-choice-grid select {", layer_css)
        self.assertIn("function updateVehicleFilterSelectors()", vehicle_layer_js)
        self.assertIn("updateVehicleFilterSelectors();", field_photos_js)

        # Filtering must not discard status/ring signals from rendered markers.
        self.assertIn("function vehicleIcon(", markers_js)
        self.assertIn("vehicle-pin--insurance-${safeInsuranceStatus}", markers_js)
        self.assertIn("function vehicleGroupInsuranceStatus", vehicle_layer_js)
        self.assertIn("vehicleGroupInsuranceStatus(group)", vehicle_layer_js)
        self.assertIn("vehicle-pin--long-standing", markers_js + css)
        self.assertIn("vehicle-pin--removed", markers_js + css)
        self.assertIn("function vehicleGroupMatchesResolutionFilter", resolution_js)
        self.assertIn("prioritizedVehicleGroups().forEach", vehicle_layer_js)

    def test_low_zoom_dot_mode_uses_distinct_shapes_for_place_types(self):
        css = (ROOT_DIR / "web" / "styles" / "map_pins.css").read_text(encoding="utf-8")

        self.assertIn(".marker-detail--dots .vehicle-pin {", css)
        self.assertIn("width: 16px;", css)
        self.assertIn("border: 3px solid var(--pin-vehicle-current-ring);", css)
        self.assertIn(".marker-detail--dots .field-photo-pin--infrastructure {", css)
        self.assertIn("transform: translate(10px, 27px) rotate(45deg);", css)
        self.assertIn(".marker-detail--dots .field-photo-pin--smoke {", css)
        self.assertIn("height: 10px;", css)
        self.assertIn("border-radius: var(--radius-full);", css)
        self.assertIn(".marker-detail--dots .pending-submission-pin {", css)
        self.assertIn("border: 2px dashed var(--pin-pending-ring);", css)
        self.assertNotIn("width: 12px;\n    height: 12px;\n    border-radius: 50%;", css)

    def test_pending_vehicle_photos_decorate_existing_vehicle_pin(self):
        css = (ROOT_DIR / "web" / "styles" / "map_pins.css").read_text(encoding="utf-8")
        markers_js = (ROOT_DIR / "web" / "app" / "map_markers.js").read_text(encoding="utf-8")
        field_photos_js = (ROOT_DIR / "web" / "app" / "field_photos.js").read_text(encoding="utf-8")
        vehicle_layer_js = (ROOT_DIR / "web" / "app" / "vehicle_layer.js").read_text(encoding="utf-8")
        vehicle_resolution_js = (ROOT_DIR / "web" / "app" / "vehicle_resolution.js").read_text(encoding="utf-8")
        i18n_js = "\n".join(
            (ROOT_DIR / "web" / path).read_text(encoding="utf-8") for path in ("i18n/pl.js", "i18n/en.js")
        )

        self.assertIn("pendingCount = 0", markers_js)
        self.assertIn("vehicle-pin--mixed-pending", markers_js + css)
        self.assertIn("vehicle-pin-pending-indicator", markers_js + css)
        self.assertIn("function attachPendingVehiclePhotosToGroups", vehicle_layer_js)
        self.assertIn("pendingPhotos.push(photo)", vehicle_layer_js)
        self.assertIn("function pendingVehiclePhotoAttachedToApprovedGroup", field_photos_js)
        self.assertIn("!pendingVehiclePhotoAttachedToApprovedGroup(photo, approvedVehicleGroups)", field_photos_js)
        self.assertIn(
            "const approvedVehicleGroups = vehicleLayerAllowed() ? visibleVehicleGroups(photos) : [];", field_photos_js
        )
        self.assertIn("encodedApprovedPhotoIds", vehicle_layer_js + vehicle_resolution_js)
        self.assertIn("encodedEditablePhotoIds", vehicle_layer_js)
        self.assertIn("vehicle.popup.pendingBadge", i18n_js)
        self.assertIn("vehicle.markerTooltipPendingPhotos", i18n_js)
