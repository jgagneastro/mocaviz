from __future__ import annotations

import unittest

from werkzeug.test import Client
from werkzeug.wrappers import Response

from app import application


PRODUCTION_PAGE_PATHS = (
    "/bd-colors",
    "/bd-evolution",
    "/companion-explorer",
    "/exoplanets-explorer",
    "/gaia-cmd",
    "/moca-explorer",
    "/banyan-sigma",
    "/group-hierarchy",
    "/spectral-typing",
    "/spectra",
    "/spectral-index-explorer",
    "/sed",
    "/retrieval-explorer",
    "/astrometry",
    "/xyz",
    "/xyz-dual",
    "/age-pdfs",
    "/moca-flows",
    "/rvbam-explorer",
    "/moranta26-rotation",
)


class RootRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Client(application, Response)

    def test_root_and_js_mount_serve_the_same_landing_page(self) -> None:
        with self.client.get("/?mock=1") as root:
            with self.client.get("/js/?mock=1") as compatibility:
                self.assertEqual(root.status_code, 200)
                self.assertEqual(compatibility.status_code, 200)
                self.assertEqual(root.data, compatibility.data)
                html = root.get_data(as_text=True)
                self.assertIn("MOCAdb data visualizations", html)
                self.assertNotIn('href="/js/', html)

    def test_every_production_page_works_at_root_and_through_js(self) -> None:
        for path in PRODUCTION_PAGE_PATHS:
            with self.subTest(path=path):
                with self.client.get(f"{path}?mock=1") as root:
                    with self.client.get(f"/js{path}?mock=1") as compatibility:
                        self.assertEqual(root.status_code, 200)
                        self.assertEqual(compatibility.status_code, 200)
                        self.assertEqual(root.mimetype, "text/html")
                        self.assertEqual(compatibility.mimetype, "text/html")
                        self.assertEqual(root.data, compatibility.data)

    def test_static_assets_work_at_root_and_through_js(self) -> None:
        with self.client.get("/static/styles.css") as root:
            with self.client.get("/js/static/styles.css") as compatibility:
                self.assertEqual(root.status_code, 200)
                self.assertEqual(compatibility.status_code, 200)
                self.assertEqual(root.mimetype, "text/css")
                self.assertEqual(root.data, compatibility.data)

    def test_get_api_and_query_string_work_through_both_prefixes(self) -> None:
        query = "dbase=mocadb_private_tables&user=collaborators&mock=1"
        with self.client.get(f"/api/js-home/context?{query}") as root:
            with self.client.get(f"/js/api/js-home/context?{query}") as compatibility:
                self.assertEqual(root.status_code, 200)
                self.assertEqual(compatibility.status_code, 200)
                self.assertEqual(root.json, compatibility.json)
                self.assertEqual(root.json["meta"]["database"], "mocadb_private_tables")

    def test_post_api_works_through_both_prefixes(self) -> None:
        with self.client.post("/api/spectra/cache/clear") as root:
            with self.client.post("/js/api/spectra/cache/clear") as compatibility:
                self.assertEqual(root.status_code, 200)
                self.assertEqual(compatibility.status_code, 200)
                self.assertTrue(root.json["ok"])
                self.assertTrue(compatibility.json["ok"])

    def test_deprecated_dash_paths_redirect_to_production_equivalents(self) -> None:
        cases = {
            "/mcmc-rvs": "/legacy-radial-velocities?mock=1",
            "/oage-pdfs": "/age-pdfs?mock=1",
            "/trueflow-age-pdfs": "/age-pdfs?mock=1",
        }
        for old_path, expected_location in cases.items():
            with self.subTest(old_path=old_path):
                with self.client.get(f"{old_path}?mock=1") as root:
                    with self.client.get(f"/js{old_path}?mock=1") as compatibility:
                        self.assertEqual(root.status_code, 302)
                        self.assertEqual(compatibility.status_code, 302)
                        self.assertEqual(root.headers["Location"], expected_location)
                        self.assertEqual(compatibility.headers["Location"], expected_location)


if __name__ == "__main__":
    unittest.main()
