from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path

from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.test import Client
from werkzeug.wrappers import Response

from mocaviz.app import EPHEMERIDES_DIR, STATIC_DIR, app


PAGE_NAME = "page_occultation_2026"
PAGE_DIR = EPHEMERIDES_DIR / PAGE_NAME


class _LocalImageReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "img" and attributes.get("src", "").startswith("assets/"):
            self.references.add(str(attributes["src"]))
        if attributes.get("data-image", "").startswith("assets/"):
            self.references.add(str(attributes["data-image"]))


class EphemeridesPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app.test_client()

    def test_occultation_page_is_available_but_absent_from_the_site_index(self) -> None:
        with self.client.get(f"/ephemerides/{PAGE_NAME}/") as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "text/html")
            html = response.get_data(as_text=True)
        self.assertIn("Occultation de Jupiter — Montréal", html)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', html)

        site_index = (STATIC_DIR / "js_index.html").read_text(encoding="utf-8")
        self.assertNotIn(PAGE_NAME, site_index)

    def test_page_route_enforces_a_trailing_slash_for_relative_assets(self) -> None:
        response = self.client.get(f"/ephemerides/{PAGE_NAME}")
        self.assertEqual(response.status_code, 308)
        self.assertTrue(response.headers["Location"].endswith(f"/ephemerides/{PAGE_NAME}/"))

    def test_js_alias_supports_standalone_local_testing(self) -> None:
        with self.client.get(f"/js/ephemerides/{PAGE_NAME}/") as page:
            self.assertEqual(page.status_code, 200)
        with self.client.get(
            f"/js/ephemerides/{PAGE_NAME}/assets/champs_instruments_montreal_2026-09-08.png"
        ) as image:
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image.mimetype, "image/png")

    def test_page_and_assets_work_through_the_production_js_mount(self) -> None:
        root_app = Flask("ephemerides-mount-test")
        mounted_client = Client(
            DispatcherMiddleware(root_app.wsgi_app, {"/js": app}),
            Response,
        )
        page = mounted_client.get(f"/js/ephemerides/{PAGE_NAME}/")
        image = mounted_client.get(
            f"/js/ephemerides/{PAGE_NAME}/assets/champs_instruments_montreal_2026-09-08.png"
        )
        try:
            self.assertEqual(page.status_code, 200)
            self.assertIn("La Lune occulte Jupiter", page.get_data(as_text=True))
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image.mimetype, "image/png")
        finally:
            page.close()
            image.close()

    def test_every_packaged_png_is_referenced_and_served(self) -> None:
        parser = _LocalImageReferenceParser()
        parser.feed((PAGE_DIR / "index.html").read_text(encoding="utf-8"))
        packaged = {
            path.relative_to(PAGE_DIR).as_posix()
            for path in PAGE_DIR.rglob("*.png")
        }
        self.assertEqual(parser.references, packaged)
        self.assertEqual(len(packaged), 43)

        for reference in sorted(packaged):
            with self.subTest(reference=reference):
                with self.client.get(f"/ephemerides/{PAGE_NAME}/{reference}") as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, "image/png")
                    self.assertTrue(response.data.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_unknown_page_and_asset_return_not_found(self) -> None:
        self.assertEqual(self.client.get("/ephemerides/not-a-page/").status_code, 404)
        self.assertEqual(
            self.client.get(f"/ephemerides/{PAGE_NAME}/assets/not-an-image.png").status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/ephemerides/%2E%2E/index.html").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
