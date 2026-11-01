import re
import unittest

from app.http.static_files import render_web_template


class ScriptOrderContracts(unittest.TestCase):
    def test_inspection_loads_after_field_photo_actions(self):
        html = re.sub(r"(\.js)\?v=[a-f0-9]{16}(?=\")", r"\1", render_web_template("index.html"))

        self.assertLess(
            html.index('<script src="/app/field_photo_actions.js"></script>'),
            html.index('<script src="/app/location_inspection.js"></script>'),
        )
        self.assertLess(
            html.index('<script src="/app/vehicle_layer.js"></script>'),
            html.index('<script src="/app/location_inspection.js"></script>'),
        )


if __name__ == "__main__":
    unittest.main()
