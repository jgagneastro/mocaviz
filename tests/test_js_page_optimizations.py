from __future__ import annotations

import gzip
import json
import unittest

from bd_colors_fast.app import (
    GAIA_CMD_MEMBERSHIP_DOWNLOAD_FLOOR,
    _BoundedCache,
    _ENCODED_RESPONSE_CACHE,
    _ENCODED_RESPONSE_CACHE_LOCK,
    _gaia_cmd_cache_key,
    _gaia_cmd_selection,
    app,
)


def decoded_json(response):
    body = response.data
    if response.headers.get("Content-Encoding") == "gzip":
        body = gzip.decompress(body)
    return json.loads(body)


class JsPageOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with _ENCODED_RESPONSE_CACHE_LOCK:
            _ENCODED_RESPONSE_CACHE.clear()

    def test_bounded_cache_evicts_least_recently_used_entry(self):
        cache = _BoundedCache(2)
        cache["a"] = 1
        cache["b"] = 2
        self.assertEqual(cache.get("a"), 1)
        cache["c"] = 3
        self.assertIn("a", cache)
        self.assertIn("c", cache)
        self.assertNotIn("b", cache)

    def test_gaia_samples_are_split_and_floor_is_fifty_percent(self):
        self.assertEqual(GAIA_CMD_MEMBERSHIP_DOWNLOAD_FLOOR, 50.0)
        field = decoded_json(self.client.get(
            "/api/gaia-cmd/data?mock=1&asso=ABDMG&sample_part=field&max_objects=80"
        ))
        associations = decoded_json(self.client.get(
            "/api/gaia-cmd/data?mock=1&asso=ABDMG&sample_part=associations&max_objects=80"
        ))
        self.assertTrue(field["rows"])
        self.assertTrue(associations["rows"])
        self.assertTrue(all(not row.get("moca_aid") for row in field["rows"]))
        self.assertTrue(all(row.get("moca_aid") or row.get("highlighted") for row in associations["rows"]))
        self.assertTrue(field["sequences"])
        self.assertFalse(associations["sequences"])
        self.assertEqual(field["selection"]["membership_download_floor"], 50.0)

    def test_gaia_field_cache_key_ignores_associations_and_highlights(self):
        first_args = {
            "mock": "1",
            "sample_part": "field",
            "asso": "ABDMG",
            "oid": "800021",
            "max_objects": "80",
        }
        second_args = {
            "mock": "1",
            "sample_part": "field",
            "asso": "THA",
            "oid": "800042",
            "max_objects": "80",
        }
        first = _gaia_cmd_selection(first_args)
        second = _gaia_cmd_selection(second_args)
        self.assertEqual(
            _gaia_cmd_cache_key(first_args, first),
            _gaia_cmd_cache_key(second_args, second),
        )

    def test_gaia_association_cache_is_per_aid_and_ignores_highlights(self):
        tha_args = {
            "mock": "1",
            "sample_part": "associations",
            "asso": "THA",
            "oid": "800021",
            "max_objects": "80",
        }
        tha_other_highlight_args = {**tha_args, "oid": "800042"}
        abdm_args = {**tha_args, "asso": "ABDMG"}
        tha_key = _gaia_cmd_cache_key(tha_args, _gaia_cmd_selection(tha_args))
        self.assertEqual(
            tha_key,
            _gaia_cmd_cache_key(
                tha_other_highlight_args,
                _gaia_cmd_selection(tha_other_highlight_args),
            ),
        )
        self.assertNotEqual(
            tha_key,
            _gaia_cmd_cache_key(abdm_args, _gaia_cmd_selection(abdm_args)),
        )

    def test_gaia_highlights_are_loaded_separately_without_sequences(self):
        highlights = decoded_json(self.client.get(
            "/api/gaia-cmd/data?mock=1&sample_part=highlights&oid=800021"
            "&gaia_quality=off&filter_wd=0&max_objects=80"
        ))
        self.assertTrue(highlights["rows"])
        self.assertTrue(all(row.get("highlighted") for row in highlights["rows"]))
        self.assertFalse(highlights["sequences"])

    def test_moca_explorer_returns_only_active_view_columns(self):
        cmd = decoded_json(self.client.get(
            "/api/moca-explorer/data?mock=1&view=cmd&max_objects=20"
        ))
        xyz = decoded_json(self.client.get(
            "/api/moca-explorer/data?mock=1&view=xyz&max_objects=20"
        ))
        cmd_row = cmd["members"][0]
        xyz_row = xyz["members"][0]
        self.assertIn("gmag", cmd_row)
        self.assertNotIn("x", cmd_row)
        self.assertIn("x", xyz_row)
        self.assertNotIn("gmag", xyz_row)
        self.assertFalse(cmd["models"])
        self.assertTrue(xyz["models"])
        self.assertEqual(xyz["selection"]["view"], "xyz")

    def test_json_is_gzipped_and_encoded_response_is_reused(self):
        path = "/api/moca-explorer/data?mock=1&view=prot&max_objects=12"
        first = self.client.get(path, headers={"Accept-Encoding": "gzip"})
        second = self.client.get(path, headers={"Accept-Encoding": "gzip"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers.get("Content-Encoding"), "gzip")
        self.assertEqual(first.headers.get("X-MOCA-Response-Cache"), "MISS")
        self.assertEqual(second.headers.get("X-MOCA-Response-Cache"), "HIT")
        self.assertEqual(first.data, second.data)

    def test_home_page_does_not_advertise_plotly_xyz_variants(self):
        response = self.client.get("/js/")
        try:
            html = response.get_data(as_text=True)
            self.assertNotIn("/js/xyz-plotly", html)
            self.assertNotIn("/js/xyz-dual-plotly", html)
        finally:
            response.close()


if __name__ == "__main__":
    unittest.main()
