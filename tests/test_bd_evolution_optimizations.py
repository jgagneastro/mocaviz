from __future__ import annotations

import gzip
import json
import unittest

import bd_colors_fast.app as app_module

from bd_colors_fast.app import app


def decoded_json(response):
    body = response.data
    if response.headers.get("Content-Encoding") == "gzip":
        body = gzip.decompress(body)
    return json.loads(body)


class BdEvolutionOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_object_payload_can_exclude_tracks_and_is_compressed(self):
        response = self.client.get(
            "/api/bd-evolution/data?mock=1&include_tracks=0&max_objects=40",
            headers={"Accept-Encoding": "gzip"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Encoding"), "gzip")
        self.assertIn("max-age=60", response.headers.get("Cache-Control", ""))
        payload = decoded_json(response)
        self.assertTrue(payload["ok"])
        self.assertNotIn("tracks", payload)
        self.assertGreater(len(payload["rows"]), 0)

    def test_track_payload_is_separate_and_longer_lived(self):
        response = self.client.get(
            "/api/bd-evolution/tracks?mock=1",
            headers={"Accept-Encoding": "gzip"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Encoding"), "gzip")
        self.assertIn("max-age=900", response.headers.get("Cache-Control", ""))
        payload = decoded_json(response)
        self.assertTrue(payload["ok"])
        self.assertGreater(len(payload["tracks"]), 0)
        self.assertEqual(payload["meta"]["track_count"], len(payload["tracks"]))

    def test_js_mount_api_routes_and_non_json_guard(self):
        script = (app_module.STATIC_DIR / "bd_evolution.js").read_text(encoding="utf-8")
        url_helper = script.split("function bdeAppUrl(path)", 1)[1].split(
            "async function initBdEvolution",
            1,
        )[0]
        self.assertIn("new URL(normalized, bdeAppBaseUrl)", url_helper)
        self.assertNotIn("window.location.origin", url_helper)
        self.assertIn('if (!payload || typeof payload !== "object")', script)
        self.assertIn("Expected a JSON response", script)

        data_response = self.client.get("/js/api/bd-evolution/data?mock=1&include_tracks=0")
        tracks_response = self.client.get("/js/api/bd-evolution/tracks?mock=1")
        self.assertTrue(decoded_json(data_response)["ok"])
        self.assertTrue(decoded_json(tracks_response)["ok"])

    def test_legacy_data_response_still_includes_tracks(self):
        response = self.client.get("/api/bd-evolution/data?mock=1&max_objects=20")
        self.assertEqual(response.status_code, 200)
        payload = decoded_json(response)
        self.assertIn("tracks", payload)
        self.assertGreater(len(payload["tracks"]), 0)

    def test_versioned_plotly_is_compressed_and_immutable(self):
        response = self.client.get(
            "/plotly.min.js?v=plotly-5.9.0",
            headers={"Accept-Encoding": "gzip"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Content-Encoding"), "gzip")
        self.assertIn("immutable", response.headers.get("Cache-Control", ""))
        self.assertLess(len(response.data), 1_500_000)


if __name__ == "__main__":
    unittest.main()
