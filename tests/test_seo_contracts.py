import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from app.http import static_files

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"


class SeoContractTests(unittest.TestCase):
    def test_home_exposes_canonical_brand_metadata_and_semantic_landmarks(self):
        html = static_files.render_web_template("index.html", page_path="/")
        head = html.split("</head>", 1)[0]

        self.assertIn("<title>IleStoi.pl – mapa pojazdów długo stojących</title>", head)
        self.assertIn('<link rel="canonical" href="https://ilestoi.pl/">', head)
        self.assertIn('<meta property="og:site_name" content="IleStoi.pl">', head)
        self.assertIn('<meta property="og:url" content="https://ilestoi.pl/">', head)
        self.assertIn('<link rel="icon" href="/favicon.svg" type="image/svg+xml" sizes="any">', head)
        self.assertIn('<link rel="manifest" href="/site.webmanifest">', head)
        self.assertNotIn("data:image/svg+xml", head)
        self.assertIn('<h1 class="visually-hidden">IleStoi.pl</h1>', html)
        self.assertIn('<main id="map" tabindex="0"', html)
        self.assertNotIn('<main id="map" role=', html)

        structured_data_match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            head,
            re.DOTALL,
        )
        self.assertIsNotNone(structured_data_match)
        structured_data = json.loads(structured_data_match.group(1))
        graph = {node["@type"]: node for node in structured_data["@graph"]}
        self.assertEqual(graph["WebSite"]["name"], "IleStoi.pl")
        self.assertEqual(graph["WebSite"]["alternateName"], "Ile Stoi")
        self.assertEqual(graph["WebSite"]["url"], "https://ilestoi.pl/")
        self.assertEqual(graph["WebApplication"]["url"], "https://ilestoi.pl/")
        self.assertTrue(graph["WebApplication"]["isAccessibleForFree"])

    def test_privacy_and_report_routes_have_unique_server_rendered_metadata(self):
        privacy = static_files.render_web_template("index.html", page_path="/privacy")
        report = static_files.render_web_template("index.html", page_path="/report")
        privacy_head = privacy.split("</head>", 1)[0]
        report_head = report.split("</head>", 1)[0]

        self.assertIn("<title>Prywatność – IleStoi.pl</title>", privacy_head)
        self.assertIn('<link rel="canonical" href="https://ilestoi.pl/privacy">', privacy_head)
        self.assertIn('<meta name="robots" content="noindex,follow">', privacy_head)
        self.assertIn('data-i18n-title="page.privacy.title"', privacy)
        self.assertIn("<title>Zgłoś problem – IleStoi.pl</title>", report_head)
        self.assertIn('<link rel="canonical" href="https://ilestoi.pl/report">', report_head)
        self.assertIn('<meta name="robots" content="noindex,follow">', report_head)
        self.assertIn('data-i18n-title="page.report.title"', report)
        self.assertNotIn('type="application/ld+json"', privacy_head + report_head)

    def test_crawler_files_use_only_canonical_urls_and_valid_formats(self):
        robots = (WEB_DIR / "robots.txt").read_text(encoding="utf-8")
        sitemap = (WEB_DIR / "sitemap.xml").read_text(encoding="utf-8")
        llms = (WEB_DIR / "llms.txt").read_text(encoding="utf-8")
        manifest = json.loads((WEB_DIR / "site.webmanifest").read_text(encoding="utf-8"))
        favicon_root = ET.parse(WEB_DIR / "favicon.svg").getroot()

        self.assertIn("User-agent: OAI-SearchBot", robots)
        self.assertIn("User-agent: *", robots)
        self.assertIn("Sitemap: https://ilestoi.pl/sitemap.xml", robots)
        sitemap_root = ET.fromstring(sitemap)
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        sitemap_urls = {element.text for element in sitemap_root.findall("s:url/s:loc", namespace)}
        self.assertEqual(sitemap_urls, {"https://ilestoi.pl/"})
        self.assertNotIn("wreckscanner.pl", sitemap + llms)
        self.assertNotIn("dlugostoi.pl", sitemap + llms)
        self.assertIn("Canonical website: https://ilestoi.pl/", llms)
        self.assertIn("not legal determinations", llms)
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["icons"][0]["src"], "/favicon.svg")
        self.assertEqual(favicon_root.attrib["viewBox"], "0 0 48 48")
        self.assertEqual(static_files.WEB_ASSET_CONTENT_TYPES[".txt"], "text/plain; charset=utf-8")
        self.assertEqual(static_files.WEB_ASSET_CONTENT_TYPES[".xml"], "application/xml; charset=utf-8")
        self.assertEqual(
            static_files.WEB_ASSET_CONTENT_TYPES[".webmanifest"],
            "application/manifest+json; charset=utf-8",
        )

    def test_default_language_is_polish_until_user_explicitly_selects_english(self):
        i18n_runtime = (WEB_DIR / "i18n.js").read_text(encoding="utf-8")

        self.assertNotIn("navigator.language", i18n_runtime)
        self.assertNotIn("navigator.userLanguage", i18n_runtime)
        self.assertIn("return 'pl';", i18n_runtime)


if __name__ == "__main__":
    unittest.main()
