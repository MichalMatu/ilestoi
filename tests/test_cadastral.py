import unittest
from unittest.mock import patch

from app.http import public_data
from core.cadastral import cadastral_code_label, cadastral_feature_info_params, parse_cadastral_feature_info


class CadastralFeatureInfoTests(unittest.TestCase):
    def test_parse_kieg_feature_info_table(self):
        html = """
        <table class="getfeatureinfo-egib">
            <tr><td>Identyfikator działki</td><td>026401_1.0022.AR_27.87</td></tr>
            <tr><td>Nazwa gminy</td><td>Wrocław</td></tr>
            <tr><td>Nazwa obrębu</td><td>Południe</td></tr>
            <tr><td>Numer działki</td><td>87</td></tr>
            <tr><td>Pole pow. w ewidencji gruntów (ha)</td><td>0.5964</td></tr>
            <tr><td>Grupa rejestrowa</td><td>7.1</td></tr>
            <tr><td>Data publikacji danych</td><td>2026-06-05</td></tr>
        </table>
        """

        parcel = parse_cadastral_feature_info(html)

        self.assertEqual(parcel["parcel_id"], "026401_1.0022.AR_27.87")
        self.assertEqual(parcel["municipality"], "Wrocław")
        self.assertEqual(parcel["district"], "Południe")
        self.assertEqual(parcel["parcel_number"], "87")
        self.assertEqual(parcel["area_ha"], "0.5964")
        self.assertEqual(parcel["registry_group"], "7.1")
        self.assertEqual(parcel["published_at"], "2026-06-05")
        self.assertEqual(parcel["raw_fields"]["Numer działki"], "87")

    def test_feature_info_params_use_fixed_kieg_query_shape(self):
        params = cadastral_feature_info_params(51.089742, 17.03894)

        self.assertEqual(params["SERVICE"], "WMS")
        self.assertEqual(params["REQUEST"], "GetFeatureInfo")
        self.assertEqual(params["VERSION"], "1.3.0")
        self.assertEqual(params["LAYERS"], "dzialki")
        self.assertEqual(params["QUERY_LAYERS"], "dzialki")
        self.assertEqual(params["CRS"], "EPSG:3857")
        self.assertEqual(params["I"], "256")
        self.assertEqual(params["J"], "256")
        self.assertIn("1896", params["BBOX"])

    def test_identify_decodes_gugik_utf8_html_without_charset(self):
        class GUGiKResponse:
            headers = {"Content-Type": "text/html"}
            encoding = "ISO-8859-1"

            def raise_for_status(self):
                pass

            def iter_content(self, chunk_size):
                del chunk_size
                yield (
                    "<table class='getfeatureinfo-egib'>"
                    "<tr><td>Identyfikator działki</td><td>026401_1.0022.2351</td></tr>"
                    "<tr><td>Numer działki</td><td>2351</td></tr>"
                    "<tr><td>Nazwa obrębu</td><td>Południe</td></tr>"
                    "</table>"
                ).encode()

            def close(self):
                pass

        class FakeSession:
            def get(self, _url, **_kwargs):
                return GUGiKResponse()

        with patch.object(public_data.map_downloads, "get_http_session", return_value=FakeSession()):
            parcel = public_data.lookup_cadastral_parcel(51.08803145, 17.03804076)

        self.assertEqual(parcel["parcel_id"], "026401_1.0022.2351")
        self.assertEqual(parcel["parcel_number"], "2351")
        self.assertEqual(parcel["district"], "Południe")

    def test_cadastral_falls_back_to_verified_official_gugik_service(self):
        from app import config

        self.assertIn("services.gugik.gov.pl", config.CADASTRAL_WMS_FALLBACK_URL)

        class Response:
            headers = {"Content-Type": "text/html"}
            encoding = "ISO-8859-1"

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                del chunk_size
                yield (
                    "<table><tr><td>Identyfikator działki</td><td>026401_1.0022.2351</td></tr>"
                    "<tr><td>Numer działki</td><td>2351</td></tr></table>"
                ).encode()

            def close(self):
                return None

        urls = []

        class Session:
            def get(self, url, **_kwargs):
                urls.append(url)
                if len(urls) == 1:
                    raise OSError("Main WMS unavailable")
                return Response()

        with patch.object(public_data.map_downloads, "get_http_session", return_value=Session()):
            parcel = public_data.lookup_cadastral_parcel(51.08803145, 17.03804076)

        self.assertEqual(urls, [config.CADASTRAL_WMS_URL, config.CADASTRAL_WMS_FALLBACK_URL])
        self.assertEqual(parcel["parcel_number"], "2351")

    def test_cadastral_code_label_expands_land_type_codes(self):
        self.assertEqual(cadastral_code_label("B"), "B - tereny mieszkaniowe")
        self.assertEqual(cadastral_code_label("Bi"), "Bi - inne tereny zabudowane")


if __name__ == "__main__":
    unittest.main()
