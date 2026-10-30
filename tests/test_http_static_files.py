import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import config
from app.http import static_files


class FakeHandler:
    def __init__(self):
        self.status = None
        self.headers = []
        self.wfile = BytesIO()

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))

    def end_headers(self) -> None:
        return None


class HttpStaticFilesContractTests(unittest.TestCase):
    def test_send_file_can_omit_head_body(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.html"
            path.write_text("<html>ok</html>", encoding="utf-8")
            handler = FakeHandler()

            static_files.send_file(handler, path, "text/html; charset=utf-8", include_body=False)

        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.wfile.getvalue(), b"")
        self.assertIn(("Content-Length", "15"), handler.headers)

    def test_send_file_can_set_download_filename(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.zip"
            path.write_bytes(b"zip")
            handler = FakeHandler()

            static_files.send_file(handler, path, "application/zip", download_name="raport_20260702_142516.zip")

        self.assertEqual(handler.status, 200)
        self.assertIn(
            (
                "Content-Disposition",
                "attachment; filename=\"raport_20260702_142516.zip\"; filename*=UTF-8''raport_20260702_142516.zip",
            ),
            handler.headers,
        )

    def test_translate_path_sanitizes_dot_segments_inside_web_dir(self):
        with TemporaryDirectory() as tmp:
            web_dir = Path(tmp) / "web"
            root_dir = Path(tmp)

            with (
                patch.object(config, "WEB_DIR", web_dir),
                patch.object(config, "ROOT_DIR", root_dir),
            ):
                translated = static_files.translate_path("/../app.js")

        self.assertEqual(translated, str(web_dir / "app.js"))

    def test_render_web_template_expands_safe_partials(self):
        with TemporaryDirectory() as tmp:
            web_dir = Path(tmp) / "web"
            (web_dir / "partials").mkdir(parents=True)
            (web_dir / "index.html").write_text(
                "<main>\n<!-- include:partials/body.html -->\n</main>\n",
                encoding="utf-8",
            )
            (web_dir / "partials" / "body.html").write_text("<p>OK</p>\n", encoding="utf-8")

            with patch.object(config, "WEB_DIR", web_dir):
                rendered = static_files.render_web_template("index.html")

        self.assertEqual(rendered, "<main>\n<p>OK</p>\n\n</main>\n")

    def test_render_web_template_injects_map_view_bootstrap(self):
        with TemporaryDirectory() as tmp:
            web_dir = Path(tmp) / "web"
            web_dir.mkdir()
            (web_dir / "index.html").write_text(
                '<script src="/i18n.js"></script>\n<!-- app-settings-bootstrap -->\n<script src="/config.js"></script>\n',
                encoding="utf-8",
            )

            with (
                patch.object(config, "WEB_DIR", web_dir),
                patch.object(
                    static_files,
                    "load_app_settings",
                    return_value={"map_view": {"lat": 51.107883, "lon": 17.038538, "zoom": 13}},
                ),
            ):
                rendered = static_files.render_web_template("index.html")

        self.assertIn(
            '<script>window.WRECKSCANNER_APP_SETTINGS={"map_view":{"lat":51.107883,"lon":17.038538,"zoom":13}};</script>',
            rendered,
        )
        self.assertLess(
            rendered.index("WRECKSCANNER_APP_SETTINGS"), rendered.index('<script src="/config.js"></script>')
        )

    def test_render_web_template_rejects_unsafe_partials(self):
        with TemporaryDirectory() as tmp:
            web_dir = Path(tmp) / "web"
            web_dir.mkdir()
            (web_dir / "index.html").write_text("<!-- include:../secret.html -->\n", encoding="utf-8")

            with (
                patch.object(config, "WEB_DIR", web_dir),
                self.assertRaises(FileNotFoundError),
            ):
                static_files.render_web_template("index.html")

    def test_handle_web_page_serves_rendered_index_without_head_body(self):
        with TemporaryDirectory() as tmp:
            web_dir = Path(tmp) / "web"
            (web_dir / "partials").mkdir(parents=True)
            (web_dir / "index.html").write_text(
                "<html>\n<!-- include:partials/app.html -->\n</html>\n",
                encoding="utf-8",
            )
            (web_dir / "partials" / "app.html").write_text("<body>app</body>\n", encoding="utf-8")
            handler = FakeHandler()
            expected_body = b"<html>\n<body>app</body>\n\n</html>\n"

            with patch.object(config, "WEB_DIR", web_dir):
                handled = static_files.handle_web_page(handler, "/privacy", include_body=False)

        self.assertTrue(handled)
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.wfile.getvalue(), b"")
        self.assertIn(("Content-Length", str(len(expected_body))), handler.headers)

    def test_handle_web_asset_serves_app_asset_without_cache(self):
        with TemporaryDirectory() as tmp:
            web_dir = Path(tmp) / "web"
            (web_dir / "styles").mkdir(parents=True)
            (web_dir / "styles" / "panel.css").write_text(".panel{}", encoding="utf-8")
            handler = FakeHandler()

            with patch.object(config, "WEB_DIR", web_dir):
                handled = static_files.handle_web_asset(handler, "/styles/panel.css")

        self.assertTrue(handled)
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.wfile.getvalue(), b".panel{}")
        self.assertIn(("Content-Type", "text/css; charset=utf-8"), handler.headers)
        self.assertIn(("Cache-Control", "no-store"), handler.headers)

    def test_content_versioned_css_js_cache_and_unversioned_urls_bypass(self):
        import re

        with TemporaryDirectory() as tmp:
            web_dir = Path(tmp) / "web"
            (web_dir / "styles").mkdir(parents=True)
            (web_dir / "app").mkdir()
            (web_dir / "index.html").write_text(
                '<html><link rel="stylesheet" href="/styles.css">'
                '<script src="/app/page.js"></script></html>', encoding="utf-8",
            )
            (web_dir / "styles.css").write_text(
                '@import url("/styles/panel.css");', encoding="utf-8",
            )
            (web_dir / "styles" / "panel.css").write_text(".panel{color:red}", encoding="utf-8")
            (web_dir / "app" / "page.js").write_text("console.log('old')", encoding="utf-8")

            with patch.object(config, "WEB_DIR", web_dir):
                initial = static_files.render_web_template("index.html")
                css_url = re.search(r'href="(/styles\.css\?v=[0-9a-f]{16})"', initial).group(1)
                js_url = re.search(r'src="(/app/page\.js\?v=[0-9a-f]{16})"', initial).group(1)

                for url, expected_content_type in (
                    (css_url, "text/css; charset=utf-8"),
                    (js_url, "text/javascript; charset=utf-8"),
                ):
                    handler = FakeHandler()
                    handler.path = url
                    handled = static_files.handle_web_asset(handler, url.split("?")[0])
                    self.assertTrue(handled)
                    self.assertEqual(handler.status, 200)
                    self.assertIn(("Content-Type", expected_content_type), handler.headers)
                    self.assertIn(("Cache-Control", static_files.VERSIONED_WEB_ASSET_CACHE_CONTROL), handler.headers)
                    if url.startswith("/styles.css"):
                        self.assertRegex(handler.wfile.getvalue().decode(), r'/styles/panel\.css\?v=[0-9a-f]{16}')

                unversioned = FakeHandler()
                unversioned.path = "/app/page.js"
                static_files.handle_web_asset(unversioned, "/app/page.js")
                self.assertIn(("Cache-Control", "no-store"), unversioned.headers)

                tampered = FakeHandler()
                tampered.path = "/app/page.js?v=0000000000000000"
                static_files.handle_web_asset(tampered, "/app/page.js")
                self.assertIn(("Cache-Control", "no-store"), tampered.headers)

                # Same contents must produce the same URLs, avoiding cache misses.
                self.assertEqual(initial, static_files.render_web_template("index.html"))
                (web_dir / "styles" / "panel.css").write_text(".panel{color:blue}", encoding="utf-8")
                (web_dir / "app" / "page.js").write_text("console.log('new')", encoding="utf-8")
                after = static_files.render_web_template("index.html")
                self.assertNotEqual(css_url, re.search(r'href="(/styles\.css\?v=[0-9a-f]{16})"', after).group(1))
                self.assertNotEqual(js_url, re.search(r'src="(/app/page\.js\?v=[0-9a-f]{16})"', after).group(1))
                stale = FakeHandler()
                stale.path = js_url
                static_files.handle_web_asset(stale, "/app/page.js")
                self.assertIn(("Cache-Control", "no-store"), stale.headers)

                page = FakeHandler()
                static_files.send_web_page(page)
                self.assertIn(("Cache-Control", "no-store"), page.headers)

    def test_imported_stylesheets_are_versioned_and_only_valid_versions_cache(self):
        import re

        with TemporaryDirectory() as tmp:
            web_dir = Path(tmp) / "web"
            (web_dir / "styles").mkdir(parents=True)
            (web_dir / "styles" / "panel.css").write_text(".panel{}", encoding="utf-8")
            (web_dir / "styles.css").write_text('@import url("/styles/panel.css");', encoding="utf-8")

            with patch.object(config, "WEB_DIR", web_dir):
                root_body = static_files._versioned_stylesheet().decode()
                imported_url = re.search(r'/styles/panel\.css\?v=[0-9a-f]{16}', root_body).group(0)
                handler = FakeHandler()
                handler.path = imported_url
                static_files.handle_web_asset(handler, "/styles/panel.css")
                self.assertIn(("Cache-Control", static_files.VERSIONED_WEB_ASSET_CACHE_CONTROL), handler.headers)
                self.assertEqual(handler.wfile.getvalue(), b".panel{}")
                handler = FakeHandler()
                handler.path = "/styles/panel.css"
                static_files.handle_web_asset(handler, "/styles/panel.css")
                self.assertIn(("Cache-Control", "no-store"), handler.headers)

    def test_handle_web_asset_rejects_unsafe_or_non_asset_paths(self):
        with TemporaryDirectory() as tmp:
            web_dir = Path(tmp) / "web"
            web_dir.mkdir()
            (web_dir / "index.html").write_text("<html></html>", encoding="utf-8")

            with patch.object(config, "WEB_DIR", web_dir):
                self.assertFalse(static_files.handle_web_asset(FakeHandler(), "/../secret.js"))
                self.assertFalse(static_files.handle_web_asset(FakeHandler(), "/index.html"))


if __name__ == "__main__":
    unittest.main()
