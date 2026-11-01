import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import core.settings_store as settings_store
from core.settings_store import (
    map_view_settings_from_dict,
    public_feature_settings_from_dict,
    public_layer_settings_from_dict,
)


class PublicLayerSettingsTests(unittest.TestCase):
    def test_missing_public_layer_settings_default_to_visible(self):
        self.assertEqual(
            public_layer_settings_from_dict({}),
            {
                "vehicles": True,
                "field_photo_infrastructure": True,
                "field_photo_smoke": True,
                "field_photo_pending": True,
                "cadastral": True,
                "base_map_osm": True,
            },
        )

    def test_public_layer_settings_accept_booleans_per_layer(self):
        self.assertEqual(
            public_layer_settings_from_dict({"vehicles": False, "field_photo_smoke": False}),
            {
                "vehicles": False,
                "field_photo_infrastructure": True,
                "field_photo_smoke": False,
                "field_photo_pending": True,
                "cadastral": True,
                "base_map_osm": True,
            },
        )


class PublicFeatureSettingsTests(unittest.TestCase):
    def test_missing_public_feature_settings_default_to_enabled(self):
        self.assertEqual(
            public_feature_settings_from_dict({}),
            {
                "report_pdfs": True,
                "photo_uploads": True,
                "vehicle_gallery": True,
            },
        )

    def test_public_feature_settings_accept_booleans_per_feature(self):
        self.assertEqual(
            public_feature_settings_from_dict({"report_pdfs": False, "photo_uploads": False}),
            {
                "report_pdfs": False,
                "photo_uploads": False,
                "vehicle_gallery": True,
            },
        )


class MapViewSettingsTests(unittest.TestCase):
    def test_missing_map_view_defaults_to_wroclaw(self):
        self.assertEqual(
            map_view_settings_from_dict({}),
            {
                "lat": 51.107883,
                "lon": 17.038538,
                "zoom": 13,
            },
        )

    def test_map_view_settings_accept_valid_coordinates_and_zoom(self):
        self.assertEqual(
            map_view_settings_from_dict({"lat": "51.1091234", "lon": "17.0419876", "zoom": "14.4"}),
            {
                "lat": 51.109123,
                "lon": 17.041988,
                "zoom": 14,
            },
        )

    def test_map_view_settings_reject_out_of_range_values_together(self):
        default = map_view_settings_from_dict({})
        self.assertEqual(map_view_settings_from_dict({"lat": 91, "lon": 17, "zoom": 14}), default)
        self.assertEqual(map_view_settings_from_dict({"lat": 51, "lon": 181, "zoom": 14}), default)
        self.assertEqual(map_view_settings_from_dict({"lat": 51, "lon": 17, "zoom": 23}), default)


class AppSettingsPersistenceTests(unittest.TestCase):
    def test_save_app_settings_writes_complete_database_rows(self):
        with TemporaryDirectory() as tmp:
            database_path = Path(tmp) / "wreckscanner.sqlite3"

            with patch.object(settings_store, "DATABASE_PATH", database_path):
                saved = settings_store.save_app_settings({"public_layers": {"vehicles": False}})

            connection = sqlite3.connect(database_path)
            try:
                rows = dict(connection.execute("SELECT key, value_json FROM settings"))
            finally:
                connection.close()
            self.assertEqual(set(rows), set(saved))
            self.assertIn('"vehicles":false', rows["public_layers"])

    def test_save_app_settings_preserves_existing_database_when_replace_fails(self):
        with TemporaryDirectory() as tmp:
            database_path = Path(tmp) / "wreckscanner.sqlite3"

            with patch.object(settings_store, "DATABASE_PATH", database_path):
                original = settings_store.save_app_settings({"public_layers": {"vehicles": True}})
                loaded = settings_store.load_app_settings()

            self.assertEqual(loaded, original)


if __name__ == "__main__":
    unittest.main()
