from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import bd_colors_fast.app as app_module

from bd_colors_fast.app import (
    GAIA_CMD_MEMBERSHIP_DOWNLOAD_FLOOR,
    GAIA_CMD_SEQUENCE_MAX_POINTS,
    _BoundedCache,
    _ENCODED_RESPONSE_CACHE,
    _ENCODED_RESPONSE_CACHE_LOCK,
    _gaia_cmd_cache_key,
    _gaia_cmd_downsample_sequence,
    _gaia_cmd_filter_field_classes,
    _gaia_cmd_shared_cache_clear,
    _gaia_cmd_shared_cache_load,
    _gaia_cmd_shared_cache_store,
    _gaia_cmd_selection,
    _page_payload_cache_get,
    _page_payload_cache_store,
    _parse_xyzuvw_selection,
    _shared_page_cache_clear,
    _xyzuvw_payload_from_base,
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

    def test_gaia_compact_field_payload_is_columnar(self):
        field = decoded_json(self.client.get(
            "/api/gaia-cmd/data?mock=1&sample_part=field&compact=1&max_objects=80"
        ))
        self.assertEqual(field["rows"], [])
        self.assertEqual(field["meta"]["payload_format"], "gaia-field-columnar-v1")
        self.assertEqual(len(field["field_columns"]["x"]), field["meta"]["row_count"])
        self.assertLessEqual(len(field["field_columns"]), 12)
        self.assertEqual(field["field_defaults"]["sample"], "Field")

    def test_gaia_sequences_are_downsampled_with_endpoints_preserved(self):
        values = list(range(GAIA_CMD_SEQUENCE_MAX_POINTS * 4))
        sequence = {
            "x": values.copy(),
            "y": values.copy(),
            "yerror": values.copy(),
        }
        result = _gaia_cmd_downsample_sequence(sequence)
        self.assertEqual(len(result["x"]), GAIA_CMD_SEQUENCE_MAX_POINTS)
        self.assertEqual(result["x"][0], values[0])
        self.assertEqual(result["x"][-1], values[-1])

    def test_gaia_field_class_filters_are_vectorized_and_only_apply_to_mocadb_matches(self):
        field = pd.DataFrame([
            {"moca_oid": 1, "x": 0.5, "y": 2.0},
            {"moca_oid": 2, "x": 0.5, "y": 0.5},
            {"moca_oid": None, "x": 0.5, "y": 2.0},
        ])
        separator = pd.DataFrame([
            {"xdata": 0.0, "ydata": 1.0},
            {"xdata": 1.0, "ydata": 1.0},
        ])
        selection = {
            "filter_wd": True,
            "filter_giants": False,
            "max_objects": 10,
        }
        with patch.object(app_module, "_read_sql", return_value=separator):
            result = _gaia_cmd_filter_field_classes(object(), field, selection)
        self.assertEqual(result["moca_oid"].fillna(-1).tolist(), [2.0, -1.0])

    def test_gaia_shared_cache_survives_process_local_cache_boundaries(self):
        payload = {
            "selection": {"sample_part": "field"},
            "rows": [],
            "field_columns": {"x": [1.0], "y": [2.0]},
            "meta": {"row_count": 1},
            "cache": {"hit": False, "ttl_seconds": 900},
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(app_module, "GAIA_CMD_SHARED_CACHE_DIR", Path(directory)):
                _gaia_cmd_shared_cache_store("field-key", payload)
                loaded = _gaia_cmd_shared_cache_load("field-key")
                self.assertIsNotNone(loaded)
                self.assertTrue(loaded["cache"]["hit"])
                self.assertTrue(loaded["cache"]["shared"])
                self.assertEqual(loaded["field_columns"]["x"], [1.0])
                self.assertEqual(_gaia_cmd_shared_cache_clear(), 1)

    def test_shared_page_cache_survives_process_local_cache_boundaries(self):
        payload = {
            "rows": [{"value": 1}],
            "meta": {"row_count": 1},
            "cache": {"hit": False, "ttl_seconds": 900},
        }
        local_cache = _BoundedCache(2)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(app_module, "SHARED_PAGE_CACHE_DIR", Path(directory)):
                _page_payload_cache_store(local_cache, "test-page", "payload-key", payload)
                local_cache.clear()
                loaded = _page_payload_cache_get(local_cache, "test-page", "payload-key")
                self.assertIsNotNone(loaded)
                self.assertTrue(loaded["cache"]["hit"])
                self.assertTrue(loaded["cache"]["shared"])
                self.assertEqual(loaded["rows"], [{"value": 1}])
                self.assertEqual(_shared_page_cache_clear("test-page"), 1)

    def test_companion_common_ctes_do_not_rank_globally_unique_adopted_rows(self):
        table_columns = {
            "moca_banyan_sigma_models": {"moca_bsmdid", "adopted", "public_adopted"},
            "calc_banyan_sigma": {"moca_oid", "moca_bsmdid", "max_observables", "is_public"},
        }
        with (
            patch.object(app_module, "_db_table_exists", return_value=True),
            patch.object(app_module, "_db_table_columns", side_effect=lambda _conn, table: table_columns.get(table, set())),
        ):
            sql, _params = app_module._companion_explorer_common_ctes(object(), {})
        self.assertNotIn("ROW_NUMBER()", sql)
        self.assertIn("STRAIGHT_JOIN data_distances dd", sql)
        self.assertIn("STRAIGHT_JOIN data_spectral_types dst", sql)
        self.assertIn("STRAIGHT_JOIN data_masses dm", sql)

    def test_xyzuvw_dual_payload_builds_both_surface_slots_from_one_base(self):
        selection = _parse_xyzuvw_selection({"axes": "xyz", "dual": "1", "checkbox": "models"})
        base = {
            "members": [],
            "models": [],
            "objects": [],
            "meta": {"member_count": 0, "model_count": 0, "object_count": 0},
            "cache": {"hit": False, "ttl_seconds": 900},
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(app_module, "SHARED_PAGE_CACHE_DIR", Path(directory)):
                payload = _xyzuvw_payload_from_base(selection, base, "dual-test", 1.0)
                app_module._XYZUVW_CACHE.clear()
        self.assertTrue(payload["selection"]["dual"])
        self.assertEqual(set(payload["modelSurfacesByAxes"]), {"xyz", "uvw"})
        self.assertEqual(payload["modelSurfacesByAxes"]["xyz"], [])
        self.assertEqual(payload["modelSurfacesByAxes"]["uvw"], [])

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
