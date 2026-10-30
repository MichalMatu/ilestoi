import json
import unittest
from io import BytesIO
from unittest.mock import patch

from app.http import dispatch
from app.http import request_body as http_request_body


class FakeHandler:
    def __init__(self, path: str):
        self.client_address = ("127.0.0.1", 12345)
        self.command = "GET"
        self.headers = {}
        self.path = path
        self.response_headers = []
        self.status = None
        self.wfile = BytesIO()

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        return None

    def payload(self) -> dict:
        return json.loads(self.wfile.getvalue().decode("utf-8"))


class HttpDispatchContractTests(unittest.TestCase):
    def test_get_unknown_api_is_handled_as_json_404(self):
        handler = FakeHandler("/api/missing")

        handled = dispatch.handle_get(handler)

        self.assertTrue(handled)
        self.assertEqual(handler.status, 404)
        self.assertEqual(handler.payload()["error"], "Nie znaleziono endpointu.")

    def test_get_web_asset_is_served_with_no_store_cache_header(self):
        handler = FakeHandler("/app.js")

        handled = dispatch.handle_get(handler)

        self.assertTrue(handled)
        self.assertEqual(handler.status, 200)
        self.assertIn(("Content-Type", "text/javascript; charset=utf-8"), handler.response_headers)
        self.assertIn(("Cache-Control", "no-store"), handler.response_headers)

    def test_head_web_asset_omits_body_and_sets_no_store_cache_header(self):
        handler = FakeHandler("/i18n/en.js")

        handled = dispatch.handle_head(handler)

        self.assertTrue(handled)
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.wfile.getvalue(), b"")
        self.assertIn(("Content-Type", "text/javascript; charset=utf-8"), handler.response_headers)
        self.assertIn(("Cache-Control", "no-store"), handler.response_headers)

    def test_get_tile_proxy_routes_to_geoportal_proxy(self):
        handler = FakeHandler("/tile_proxy/geoportal-standard/7/65/42?enhancementSettings=123")

        with patch.object(dispatch.http_wms_proxy, "handle_geoportal_tile_proxy") as tile_proxy:
            handled = dispatch.handle_get(handler)

        self.assertTrue(handled)
        tile_proxy.assert_called_once_with(handler)

    def test_get_reverse_address_routes_to_public_data_handler(self):
        handler = FakeHandler("/api/address/reverse?lat=51.1&lon=17.1")

        with patch.object(dispatch.http_public_data, "handle_reverse_address") as reverse_address:
            handled = dispatch.handle_get(handler)

        self.assertTrue(handled)
        reverse_address.assert_called_once_with(handler)

    def test_report_route_serves_app_shell_with_problem_report_modal(self):
        handler = FakeHandler("/report")

        handled = dispatch.handle_get(handler)

        self.assertTrue(handled)
        self.assertEqual(handler.status, 200)
        self.assertIn(("Content-Type", "text/html; charset=utf-8"), handler.response_headers)
        body = handler.wfile.getvalue().decode("utf-8")
        self.assertIn('id="modal-problem-report"', body)
        self.assertIn('<script src="/app/problem_report.js"></script>', body)

    def test_post_settings_uses_json_dispatch_preflight(self):
        handler = FakeHandler("/api/settings")

        with patch.object(http_request_body, "dispatch_json_request") as dispatch_json:
            dispatch.handle_post(handler)

        dispatch_json.assert_called_once_with(handler, dispatch.http_settings.handle_save_settings, handler)

    def test_head_unknown_api_omits_body(self):
        handler = FakeHandler("/api/missing")
        handler.command = "HEAD"

        handled = dispatch.handle_head(handler)

        self.assertTrue(handled)
        self.assertEqual(handler.status, 404)
        self.assertEqual(handler.wfile.getvalue(), b"")

    def test_head_known_api_matches_get_status_and_headers_but_omits_body(self):
        handler = FakeHandler("/api/health/live")
        handler.command = "HEAD"

        handled = dispatch.handle_head(handler)

        self.assertTrue(handled)
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.wfile.getvalue(), b"")
        self.assertIn(("Content-Type", "application/json"), handler.response_headers)
        self.assertGreater(int(dict(handler.response_headers)["Content-Length"]), 0)

    def test_head_costly_api_uses_the_same_rate_limit_bucket_as_get(self):
        handler = FakeHandler("/api/address/reverse?lat=51.1&lon=17.1")
        handler.command = "HEAD"

        def reject_with_response(limited_handler, method, path):
            self.assertTrue(limited_handler._suppress_response_body)
            dispatch.http_responses.send_json(limited_handler, 429, {"error": "limit"})
            return True

        with (
            patch.object(
                dispatch.http_rate_limit, "reject_limited", side_effect=reject_with_response
            ) as reject_limited,
            patch.object(dispatch.http_public_data, "handle_reverse_address") as reverse_address,
        ):
            handled = dispatch.handle_head(handler)

        self.assertTrue(handled)
        self.assertEqual(handler.status, 429)
        self.assertEqual(handler.wfile.getvalue(), b"")
        reject_limited.assert_called_once_with(handler, "GET", "/api/address/reverse")
        reverse_address.assert_not_called()

    def test_options_sets_empty_response(self):
        handler = FakeHandler("/api/settings")

        with patch.object(handler, "send_header") as send_header:
            dispatch.handle_options(handler)

        self.assertEqual(handler.status, 204)
        send_header.assert_any_call("Content-Length", "0")

    def test_delete_uses_only_canonical_admin_photo_route(self):
        handler = FakeHandler("/api/admin/photos/field/photo-1")
        handler.command = "DELETE"

        with (
            patch.object(dispatch.http_request_body, "reject_unsafe_request", return_value=False),
            patch.object(dispatch.http_admin, "handle_delete_admin_photo") as delete_photo,
        ):
            dispatch.handle_delete(handler)

        delete_photo.assert_called_once_with(handler, ("field", ("photo-1",)))

    def test_delete_rejects_retired_field_photo_shortcut(self):
        handler = FakeHandler("/api/field-photos/photo-1")
        handler.command = "DELETE"

        with (
            patch.object(dispatch.http_request_body, "reject_unsafe_request", return_value=False),
            patch.object(dispatch.http_admin, "handle_delete_admin_photo") as delete_photo,
            patch.object(dispatch.http_responses, "send_api_not_found") as not_found,
        ):
            dispatch.handle_delete(handler)

        delete_photo.assert_not_called()
        not_found.assert_called_once_with(handler)


if __name__ == "__main__":
    unittest.main()
