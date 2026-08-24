from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import mocaviz.app as app_module

from mocaviz.app import (
    GAIA_CMD_MEMBERSHIP_DOWNLOAD_FLOOR,
    GAIA_CMD_SEQUENCE_MAX_POINTS,
    _BoundedCache,
    _ENCODED_RESPONSE_CACHE,
    _ENCODED_RESPONSE_CACHE_LOCK,
    _companion_explorer_layer_cache_key,
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
    _rvbam_selected_run_id,
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
            "&gaia_quality=strict&filter_wd=0&max_objects=80"
        ))
        self.assertTrue(highlights["rows"])
        self.assertIn(800021, {row.get("moca_oid") for row in highlights["rows"]})
        self.assertTrue(all(row.get("highlighted") for row in highlights["rows"]))
        self.assertFalse(highlights["sequences"])

    def test_gaia_photometry_quality_off_is_explicit_and_unfiltered(self):
        script = (app_module.STATIC_DIR / "gaia_cmd.js").read_text(encoding="utf-8")
        html = self.client.get("/js/gaia-cmd").get_data(as_text=True)
        api_params_block = script.split("function gaiaCmdApiParams()", 1)[1].split(
            "function updateGaiaCmdUrl()",
            1,
        )[0]
        self.assertIn('params.set("gaia_quality", gaiaQuality);', api_params_block)
        self.assertNotIn('gaiaQuality !== "off"', api_params_block)
        self.assertIn("Gaia photometry quality filter", html)
        self.assertNotIn("Gaia source quality", html)

        payloads = {}
        for mode in ("off", "soft", "strict"):
            payloads[mode] = decoded_json(self.client.get(
                "/api/gaia-cmd/data?mock=1&sample_part=associations&asso=HYA"
                f"&gaia_quality={mode}&filter_wd=0&max_objects=200"
            ))
            self.assertEqual(payloads[mode]["selection"]["gaia_quality"], mode)
        self.assertGreater(len(payloads["off"]["rows"]), len(payloads["soft"]["rows"]))
        self.assertGreater(len(payloads["soft"]["rows"]), len(payloads["strict"]["rows"]))

    def test_gaia_highlights_bypass_photometry_quality_filter(self):
        source = Path(app_module.__file__).read_text(encoding="utf-8")
        quality_assignments = source.split(
            'field_gaia_quality_filter = _gaia_cmd_gaia_quality_filter_sql',
            1,
        )[1].split("field_sql_selection =", 1)[0]
        self.assertIn(
            'association_gaia_quality_filter = _gaia_cmd_gaia_quality_filter_sql',
            quality_assignments,
        )
        self.assertIn('highlight_gaia_quality_filter = ""', quality_assignments)
        self.assertNotIn(
            'highlight_gaia_quality_filter = _gaia_cmd_gaia_quality_filter_sql',
            quality_assignments,
        )

    def test_gaia_extinction_correction_is_opt_in_and_disabled_for_raw_photometry(self):
        html = self.client.get("/js/gaia-cmd").get_data(as_text=True)
        script = (app_module.STATIC_DIR / "gaia_cmd.js").read_text(encoding="utf-8")
        self.assertIn('<input id="gcmd-extcorr-only" type="checkbox">', html)
        self.assertIn("<span>Require extinction correction</span>", html)
        self.assertIn("extinctionCorrectedParam === null ? false", script)
        self.assertIn('input.disabled = disabled;', script)
        self.assertIn('classList.toggle("is-disabled", disabled)', script)
        self.assertIn(
            '!gcmdEl["gcmd-raw-gaia"].checked && gcmdEl["gcmd-extcorr-only"].checked',
            script,
        )
        update_url_block = script.split("function updateGaiaCmdUrl()", 1)[1].split(
            "function clampGaiaCmdMembershipProb",
            1,
        )[0]
        extcorr_url_block = update_url_block.split(
            'if (gcmdEl["gcmd-extcorr-only"].checked)',
            1,
        )[1].split('if (!gcmdEl["gcmd-extcorr-vectors"].checked)', 1)[0]
        self.assertIn('params.set("extinction_corrected", "1");', extcorr_url_block)
        self.assertIn('params.delete("extinction_corrected");', extcorr_url_block)
        self.assertFalse(_gaia_cmd_selection({})["extinction_corrected_only"])
        self.assertFalse(_gaia_cmd_selection({"extinction_corrected": "0"})["extinction_corrected_only"])
        self.assertTrue(_gaia_cmd_selection({"extinction_corrected": "1"})["extinction_corrected_only"])

    def test_gaia_membership_basis_sources_defaults_and_union(self):
        default_selection = _gaia_cmd_selection({})
        literature_selection = _gaia_cmd_selection({"membership_basis": "literature_claims"})
        union_selection = _gaia_cmd_selection({"membership_basis": "union"})
        self.assertEqual(default_selection["membership_basis"], "banyan_sigma")
        self.assertEqual(default_selection["membership_download_floor"], 50.0)
        self.assertEqual(literature_selection["membership_download_floor"], 0.0)
        self.assertEqual(union_selection["membership_download_floor"], 0.0)

        banyan_sql = app_module._gaia_cmd_association_candidates_sql(
            default_selection,
            ":aid",
            True,
        )
        literature_sql = app_module._gaia_cmd_association_candidates_sql(
            literature_selection,
            ":aid",
            True,
        )
        union_sql = app_module._gaia_cmd_association_candidates_sql(
            union_selection,
            ":aid",
            True,
        )
        self.assertIn("FROM calc_banyan_sigma", banyan_sql)
        self.assertNotIn("FROM data_memberships", banyan_sql)
        self.assertIn("FROM data_memberships", literature_sql)
        self.assertIn("LEFT JOIN", literature_sql)
        self.assertIn("FROM calc_banyan_sigma", literature_sql)
        self.assertIn("canonical_banyan.ya_prob", literature_sql)
        self.assertNotIn("dm.is_public", literature_sql)
        self.assertNotIn("dm.is_public", union_sql)
        self.assertIn("UNION ALL", union_sql)
        self.assertIn("GROUP BY candidate_rows.moca_oid, candidate_rows.moca_aid", union_sql)

        common = (
            "/api/gaia-cmd/data?mock=1&sample_part=associations&asso=HYA"
            "&gaia_quality=off&filter_wd=0&max_objects=240"
        )
        banyan = decoded_json(self.client.get(common))
        literature = decoded_json(self.client.get(f"{common}&membership_basis=literature_claims"))
        union = decoded_json(self.client.get(f"{common}&membership_basis=union"))
        self.assertTrue(all(row["has_banyan_sigma"] == 1 for row in banyan["rows"]))
        self.assertTrue(all(row["has_literature_claim"] == 1 for row in literature["rows"]))
        self.assertTrue(any(row["ya_prob"] is not None for row in literature["rows"]))
        self.assertTrue(any(row["ya_prob"] is None for row in literature["rows"]))
        self.assertGreater(len(union["rows"]), len(banyan["rows"]))
        self.assertGreater(len(union["rows"]), len(literature["rows"]))
        self.assertEqual(len({(row["moca_aid"], row["moca_oid"]) for row in union["rows"]}), len(union["rows"]))
        self.assertTrue(all(row["has_banyan_sigma"] or row["has_literature_claim"] for row in union["rows"]))
        self.assertTrue(any(row["has_banyan_sigma"] and row["has_literature_claim"] for row in union["rows"]))

        html = self.client.get("/js/gaia-cmd").get_data(as_text=True)
        script = (app_module.STATIC_DIR / "gaia_cmd.js").read_text(encoding="utf-8")
        self.assertIn('<option value="banyan_sigma" selected>BANYAN Σ</option>', html)
        self.assertIn('<option value="literature_claims">Literature claims</option>', html)
        self.assertIn('<option value="union">Union of BANYAN Σ and literature</option>', html)
        self.assertIn("literature_claims: 0", script)
        self.assertIn("union: 0", script)
        self.assertIn("input.disabled = false;", script)
        self.assertIn("if (minimumProbability <= 0) return true;", script)

    def test_gaia_vetted_membership_missing_option_and_filter(self):
        options = decoded_json(self.client.get("/api/gaia-cmd/options?mock=1"))
        option_values = [row["value"] for row in options["vetted_mtids"]]
        missing_index = option_values.index("missing")
        self.assertEqual(option_values[missing_index - 1:missing_index + 2], ["CM", "missing", "LM"])
        self.assertEqual(options["vetted_mtids"][missing_index]["label"], "Missing")
        self.assertTrue(options["vetted_mtids"][missing_index]["italic"])

        missing = decoded_json(self.client.get(
            "/api/gaia-cmd/data?mock=1&sample_part=associations&asso=HYA"
            "&gaia_quality=off&filter_wd=0&vetted_mtid=missing&max_objects=200"
        ))
        self.assertTrue(missing["rows"])
        self.assertTrue(all(not row.get("vetted_moca_mtids") for row in missing["rows"]))

        combined = decoded_json(self.client.get(
            "/api/gaia-cmd/data?mock=1&sample_part=all&asso=HYA"
            "&gaia_quality=off&filter_wd=0&vetted_mtid=HM&max_objects=200"
        ))
        field_rows = [row for row in combined["rows"] if not row.get("moca_aid")]
        association_rows = [row for row in combined["rows"] if row.get("moca_aid")]
        self.assertTrue(field_rows)
        self.assertTrue(association_rows)
        self.assertTrue(all("HM" in row.get("vetted_moca_mtids", "").split(",") for row in association_rows))

        selection = {
            "vetted_mtids": ["missing"],
            "filter_giants": False,
            "filter_wd": False,
        }
        sql = app_module._gaia_cmd_object_filter_sql(
            "cbs",
            selection,
            "`mocadb_private_tables`",
            "NULL",
            "cbs.moca_aid",
            "",
            "x",
            "y",
        )
        self.assertIn("NOT EXISTS", sql)
        self.assertIn("mechanics_memberships_vetted mmv_missing", sql)
        self.assertNotIn("moca_mtid IN", sql)

        field_sql = app_module._gaia_cmd_object_filter_sql(
            "g",
            selection,
            "`mocadb_private_tables`",
            "NULL",
            None,
            "",
            "x",
            "y",
        )
        self.assertEqual(field_sql, "")

        script = (app_module.STATIC_DIR / "gaia_cmd.js").read_text(encoding="utf-8")
        styles = (app_module.STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        self.assertIn('const gcmdMissingVettedMtid = "missing";', script)
        self.assertIn("const matchesMissing = Boolean(row?.moca_aid)", script)
        self.assertIn("selected.includes(gcmdMissingVettedMtid)", script)
        self.assertIn("!selected.length || !row?.moca_aid || row._highlighted", script)
        self.assertIn(".gcmd-vetted-mtid-missing", styles)
        self.assertIn("font-style: italic", styles)

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
        with patch.object(app_module, "_db_table_exists", return_value=True):
            with patch.object(
                app_module,
                "_db_table_columns",
                side_effect=lambda _conn, table: table_columns.get(table, set()),
            ):
                sql, _params = app_module._companion_explorer_common_ctes(object(), {})
        self.assertNotIn("ROW_NUMBER()", sql)
        self.assertIn("STRAIGHT_JOIN data_distances dd", sql)
        self.assertIn("STRAIGHT_JOIN data_spectral_types dst", sql)
        self.assertIn("STRAIGHT_JOIN data_masses dm", sql)

    def test_companion_layer_cache_ignores_pure_display_controls(self):
        first = {
            "database": "mocadb",
            "layer": "companions",
            "max_rows": "80000",
            "x": "sep_au",
            "y": "mass_ratio_q",
            "xlog": "1",
            "comover_probability_min": "50",
            "spt_range": "L0-T9",
        }
        second = {
            **first,
            "color_age": "1",
            "errors": "1",
            "hover_text": "0",
        }
        self.assertEqual(
            _companion_explorer_layer_cache_key(first, "companions"),
            _companion_explorer_layer_cache_key(second, "companions"),
        )
        self.assertNotEqual(
            _companion_explorer_layer_cache_key(first, "companions"),
            _companion_explorer_layer_cache_key({**first, "max_rows": "1000"}, "companions"),
        )
        self.assertNotEqual(
            _companion_explorer_layer_cache_key(first, "companions"),
            _companion_explorer_layer_cache_key({**first, "comover_probability_min": "90"}, "companions"),
        )

    def test_companion_mock_layers_are_independent_and_unfiltered(self):
        companions = decoded_json(self.client.get(
            "/api/companion-explorer/data?mock=1&layer=companions&comover_probability_min=99"
        ))
        exoplanets = decoded_json(self.client.get(
            "/api/companion-explorer/data?mock=1&layer=exoplanets"
        ))
        tess = decoded_json(self.client.get(
            "/api/companion-explorer/data?mock=1&layer=tess_candidates"
        ))
        self.assertTrue(companions["rows"])
        self.assertFalse(companions["exoplanets"])
        self.assertFalse(companions["tess_candidates"])
        self.assertTrue(exoplanets["exoplanets"])
        self.assertFalse(exoplanets["rows"])
        self.assertFalse(exoplanets["tess_candidates"])
        self.assertTrue(tess["tess_candidates"])
        self.assertFalse(tess["rows"])
        self.assertFalse(tess["exoplanets"])
        self.assertTrue(companions["meta"]["server_filtered"])

    def test_companion_display_controls_render_without_data_refetch(self):
        source = (app_module.STATIC_DIR / "companion_explorer.js").read_text(encoding="utf-8")
        controls = source.split("function bindCompanionControls()", 1)[1].split(
            "function readCompanionUrlState",
            1,
        )[0]
        self.assertIn('renderCompanionExplorer()', controls)
        self.assertIn('scheduleCompanionRender()', controls)
        self.assertNotIn('scheduleCompanionDataLoad()', controls)
        self.assertIn('loadMissingCompanionOverlaysOrRender()', controls)
        self.assertIn("companionCoverageCoversControls()", source)
        self.assertIn('params.set("layer", layer)', source)
        self.assertNotIn("ensureCompanionDesignationIndex", source)
        search = source.split("async function searchCompanionTargets", 1)[1].split(
            "function localCompanionSearchResults",
            1,
        )[0]
        self.assertIn("localCompanionSearchResults(query)", search)
        self.assertIn("api/companion-explorer/search", search)
        self.assertNotIn("api/companion-explorer/designations", search)

    def test_companion_client_uses_js_mount_and_guards_non_json_responses(self):
        source = (app_module.STATIC_DIR / "companion_explorer.js").read_text(encoding="utf-8")
        html = (app_module.STATIC_DIR / "companion_explorer.html").read_text(encoding="utf-8")
        url_helper = source.split("function cexAppUrl(path)", 1)[1].split(
            "async function initCompanionExplorer",
            1,
        )[0]
        self.assertIn("new URL(normalized, cexAppBaseUrl)", url_helper)
        self.assertNotIn("window.location.origin", url_helper)
        self.assertIn("Expected a JSON response", source)
        self.assertIn("companion_explorer.js?v=api-routing-20260710a", html)

        response = self.client.get("/js/api/companion-explorer/data?mock=1&layer=companions")
        self.assertTrue(decoded_json(response)["ok"])

    def test_maintained_clients_keep_api_requests_under_js_mount(self):
        script_names = (
            "app.js",
            "astrometry.js",
            "banyan_sigma.js",
            "bd_evolution.js",
            "companion_explorer.js",
            "exoplanets_explorer.js",
            "gaia_cmd.js",
            "group_hierarchy.js",
            "moca_explorer.js",
            "moca_flows.js",
            "moranta26_rotation.js",
            "retrieval_explorer.js",
            "rvbam_explorer.js",
            "sed.js",
            "spectra.js",
            "spectral_index_explorer.js",
            "spectral_typing.js",
            "trueflow_age_pdfs.js",
            "xyzuvw.js",
            "xyzuvw_three.js",
        )
        for script_name in script_names:
            with self.subTest(script_name=script_name):
                source = (app_module.STATIC_DIR / script_name).read_text(encoding="utf-8")
                self.assertNotIn('normalized.startsWith("api/")', source)

        html_names = (
            "astrometry.html",
            "banyan_sigma.html",
            "exoplanets_explorer.html",
            "gaia_cmd.html",
            "group_hierarchy.html",
            "index.html",
            "moca_explorer.html",
            "moca_flows.html",
            "moranta26_rotation.html",
            "retrieval_explorer.html",
            "rvbam_explorer.html",
            "sed.html",
            "spectra.html",
            "spectral_index_explorer.html",
            "spectral_typing.html",
            "trueflow_age_pdfs.html",
            "xyz2.html",
            "xyz2_three.html",
            "xyzuvw.html",
            "xyzuvw_three.html",
        )
        for html_name in html_names:
            with self.subTest(html_name=html_name):
                html = (app_module.STATIC_DIR / html_name).read_text(encoding="utf-8")
                self.assertIn("api-routing-20260710a", html)

        legacy_rv = (app_module.STATIC_DIR / "legacy_radial_velocities.js").read_text(encoding="utf-8")
        self.assertNotIn("api-routing-20260710a", legacy_rv)

    def test_moca_flows_mock_exposes_pdf_summaries_and_run_timestamps(self):
        payload = decoded_json(self.client.get(
            "/api/moca-flows/data?mock=1&target=association&moca_aid=THOR"
            "&stack_mode=hbm&mh_treatment=db&curve_role=posterior"
        ))
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["panels"])
        created = []
        modified = []
        for panel in payload["panels"]:
            metadata = panel["metadata"]
            for key in (
                "peak_age_myr",
                "age_lo_myr",
                "age_hi_myr",
                "peak_log10_age_myr",
                "log10_age_lo",
                "log10_age_hi",
                "created_timestamp",
                "modified_timestamp",
            ):
                self.assertIsNotNone(metadata[key], (panel["result_key"], key))
            self.assertLessEqual(metadata["age_lo_myr"], metadata["peak_age_myr"])
            self.assertLessEqual(metadata["peak_age_myr"], metadata["age_hi_myr"])
            self.assertLessEqual(metadata["log10_age_lo"], metadata["peak_log10_age_myr"])
            self.assertLessEqual(metadata["peak_log10_age_myr"], metadata["log10_age_hi"])
            created.append(metadata["created_timestamp"])
            modified.append(metadata["modified_timestamp"])
        self.assertEqual(payload["meta"]["global_created_timestamp"], min(created))
        self.assertEqual(payload["meta"]["global_modified_timestamp"], max(modified))

    def test_moca_flows_client_uses_axis_specific_peak_and_68_percent_region(self):
        source = (app_module.STATIC_DIR / "moca_flows.js").read_text(encoding="utf-8")
        marker = source.split("function mocaFlowsCurveMarkerShapes", 1)[1].split(
            "function mocaFlowsPanelPeakAge",
            1,
        )[0]
        self.assertIn("const peak = stats?.peak", marker)
        self.assertIn("const lo = stats?.bandLo", marker)
        self.assertIn("const hi = stats?.bandHi", marker)
        self.assertNotIn("stats?.mean", marker)
        self.assertIn('"PDF peak (log age)"', source)
        self.assertIn('"PDF peak (linear age)"', source)
        self.assertNotIn("log₁₀(age/yr)", source)
        self.assertIn("mflowsPeakPlateauRelativeTolerance = 0.002", source)
        self.assertIn("function mocaFlowsPeakPlateau", source)
        self.assertIn("const peakCoord = 0.5 * (loCoord + hiCoord)", source)
        self.assertIn("global created:", source)
        self.assertIn("global modified:", source)
        panel_info = source.split("function mocaFlowsPanelInfoHtml", 1)[1].split(
            "function renderMocaFlowsRunMetadata",
            1,
        )[0]
        self.assertIn('"created"', panel_info)
        self.assertIn('"modified"', panel_info)

    def test_moca_flows_log_axis_keeps_likelihood_in_raw_relative_space(self):
        source = (app_module.STATIC_DIR / "moca_flows.js").read_text(encoding="utf-8")
        displayed_value = source.split("function mocaFlowsDisplayedPdfValue", 1)[1].split(
            "function mocaFlowsPeakContainingInterval",
            1,
        )[0]
        self.assertIn('normalizeMocaFlowsCurveRole(curveRole) === "likelihood"', displayed_value)
        self.assertIn("perLogAge && !isLikelihood ? pdf * age * Math.LN10 : pdf", displayed_value)
        self.assertIn('const curveRole = mocaFlowsPanelCurveRole(panel);', source)
        self.assertIn('text: isLikelihood', source)
        self.assertIn('"Relative likelihood"', source)

    def test_moca_flows_defaults_to_v2_and_hides_its_mh_pane(self):
        source = (app_module.STATIC_DIR / "moca_flows.js").read_text(encoding="utf-8")
        html = (app_module.STATIC_DIR / "moca_flows.html").read_text(encoding="utf-8")
        self.assertIn('const mflowsDefaultModelVersion = "v2.0";', source)
        self.assertIn("|| mflowsDefaultModelVersion,", source)
        self.assertIn("function updateMocaFlowsModelControls()", source)
        self.assertIn('mflowsEl["mflows-mh-section"].hidden = version === "v2.0";', source)
        self.assertIn('id="mflows-mh-section"', html)

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

    def test_xyzuvw_single_and_dual_views_reuse_axis_meshes(self):
        base = {
            "members": [],
            "models": [{"moca_aid": "ABDMG", "coeff_index": 0}],
            "objects": [],
            "meta": {"member_count": 0, "model_count": 1, "object_count": 0},
            "cache": {"hit": False, "ttl_seconds": 900},
        }
        single = _parse_xyzuvw_selection({"axes": "xyz", "checkbox": "models"})
        dual = _parse_xyzuvw_selection({"axes": "xyz", "dual": "1", "checkbox": "models"})
        app_module._XYZUVW_SURFACE_CACHE.clear()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(app_module, "SHARED_PAGE_CACHE_DIR", Path(directory)):
                with patch.object(
                    app_module,
                    "_xyzuvw_model_surfaces",
                    side_effect=lambda _models, axes: [{"axes": "".join(axes)}],
                ) as generator:
                    _xyzuvw_payload_from_base(single, base, "single-surface-test", 1.0)
                    payload = _xyzuvw_payload_from_base(dual, base, "dual-surface-test", 1.0)
        app_module._XYZUVW_CACHE.clear()
        app_module._XYZUVW_SURFACE_CACHE.clear()
        self.assertEqual(generator.call_count, 2)
        self.assertEqual(payload["meta"]["surface_cache_hits"], 1)
        self.assertEqual(payload["modelSurfacesByAxes"]["xyz"], [{"axes": "xyz"}])
        self.assertEqual(payload["modelSurfacesByAxes"]["uvw"], [{"axes": "uvw"}])

    def test_xyz_and_spectral_startup_requests_are_parallelized(self):
        xyz_source = (app_module.STATIC_DIR / "xyzuvw_three.js").read_text(encoding="utf-8")
        xyz_init = xyz_source.split("async function initXyzuvwThree()", 1)[1].split(
            "function collectXyzuvwElements",
            1,
        )[0]
        self.assertIn("const optionsPromise = loadXyzuvwOptions()", xyz_init)
        self.assertIn("await loadXyzuvwData()", xyz_init)
        self.assertIn("await optionsPromise", xyz_init)

        spectral_source = (app_module.STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")
        spectral_init = spectral_source.split("async function initSpectralTyping()", 1)[1].split(
            "function collectSpectralElements",
            1,
        )[0]
        self.assertIn("Promise.all([authPromise, gridPromise])", spectral_init)
        self.assertIn("loadSelectedSpectrumLabels()", spectral_init)
        self.assertIn("computeSpectralComparison()", spectral_init)

    def test_xyz_association_removal_carves_loaded_payload_without_refetch(self):
        for filename in ("xyzuvw.js", "xyzuvw_three.js"):
            source = (app_module.STATIC_DIR / filename).read_text(encoding="utf-8")
            remove_handler = source.split("function renderAssociationList()", 1)[1].split(
                "async function searchXyzuvwAssociations",
                1,
            )[0]
            self.assertIn("carveAssociationFromLoadedXyzuvwData(aid)", remove_handler)
            self.assertNotIn("loadXyzuvwData()", remove_handler)

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

    def test_rvbam_private_mode_uses_requested_dataset_as_default(self):
        runs = [
            {
                "moca_rv_sample_run_id": 91,
                "moca_specid": 60000,
                "template_name": "models_other.h5",
                "pipeline_version": "rvbam_other",
            },
            {
                "moca_rv_sample_run_id": 77,
                "moca_specid": 50949,
                "template_name": "/models/models_sonora_diamondback.h5",
                "pipeline_version": "rvbam_2026_02_g395h",
            },
        ]
        self.assertEqual(
            _rvbam_selected_run_id({"dbase": "mocadb_private_tables"}, runs),
            77,
        )
        self.assertEqual(_rvbam_selected_run_id({"dbase": "mocadb"}, runs), 91)
        self.assertEqual(
            _rvbam_selected_run_id(
                {"dbase": "mocadb_private_tables", "run_id": "91"},
                runs,
            ),
            91,
        )

    def test_rvbam_posterior_controls_live_inside_posterior_tab(self):
        html = self.client.get("/js/rvbam-explorer").get_data(as_text=True)
        sidebar, remainder = html.split("</aside>", 1)
        posterior_panel = remainder.split('id="rvb-tab-posterior"', 1)[1].split(
            'id="rvb-tab-params"',
            1,
        )[0]
        for control_id in (
            "rvb-param-x",
            "rvb-param-y",
            "rvb-max-points",
            "rvb-load-posterior",
        ):
            self.assertNotIn(f'id="{control_id}"', sidebar)
            self.assertIn(f'id="{control_id}"', posterior_panel)

    def test_spectral_typing_loaders_have_panel_specific_labels(self):
        html = self.client.get("/js/spectral-typing").get_data(as_text=True)
        upper_loader = html.split('id="spt-plot-loader"', 1)[1].split("</div>", 3)[:3]
        lower_loader = html.split('id="spt-chi2-loader"', 1)[1].split("</div>", 3)[:3]
        self.assertIn("Loading best-fit comparison", "".join(upper_loader))
        self.assertIn("Loading χ² map", "".join(lower_loader))

    def test_spectral_pages_share_extended_lty_feature_catalog(self):
        catalog = (app_module.STATIC_DIR / "brown_dwarf_spectral_features.js").read_text(encoding="utf-8")
        for formula in (
            'feature("MgH"',
            'feature("CaOH"',
            'feature("Li I"',
            'feature("CrH"',
            'feature("CH4"',
            'feature("NH3"',
            'feature("LiCl"',
            'feature("H2 CIA far-IR"',
        ):
            self.assertIn(formula, catalog)
        self.assertIn("[0.4215, 0.4240]", catalog)
        self.assertIn("[20.0000, 50.0000]", catalog)
        self.assertIn('"Y model"', catalog)

        for html_name, script_name in (
            ("spectra.html", "spectra.js"),
            ("spectral_typing.html", "spectral_typing.js"),
        ):
            with self.subTest(html_name=html_name):
                html = (app_module.STATIC_DIR / html_name).read_text(encoding="utf-8")
                source = (app_module.STATIC_DIR / script_name).read_text(encoding="utf-8")
                self.assertIn("Show L/T/Y chemical features (0.4–50 μm)", html)
                self.assertLess(
                    html.index("brown_dwarf_spectral_features.js"),
                    html.index(script_name),
                )
                self.assertIn("mocaBrownDwarfSpectralFeatureBands", source)
                self.assertIn("mocaBrownDwarfSpectralFeatureBandsInRange", source)

        typing_source = (app_module.STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")
        self.assertIn('norm: "0.400-50.000", bins: 50', typing_source)
        self.assertIn("featureShapes(xRange)", typing_source)
        self.assertIn("featureAnnotations(xRange)", typing_source)

    def test_spectral_typing_has_global_chi2_rank_navigation(self):
        html = self.client.get("/js/spectral-typing").get_data(as_text=True)
        source = (app_module.STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")
        self.assertIn('id="spt-next-best-chi2"', html)
        self.assertIn('id="spt-next-worse-chi2"', html)
        self.assertIn("Next best χ²", html)
        self.assertIn("Next worse χ²", html)
        self.assertIn("function globalChi2Ranking()", source)
        self.assertIn(".filter((candidate) => finiteNumber(candidate.entry.reduced_chi2))", source)
        self.assertIn("a.reducedChi2 - b.reducedChi2", source)
        self.assertIn("function moveChi2Rank(delta)", source)
        self.assertIn('sptEl["spt-grid-select"].value = next.grid', source)

    def test_spectral_typing_has_dedicated_chi2_csv_download(self):
        html = self.client.get("/js/spectral-typing").get_data(as_text=True)
        source = (app_module.STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")
        chi2_plot_index = html.index('id="spt-chi2-plot"')
        chi2_export_index = html.index('id="spt-export-chi2-csv"')
        self.assertGreater(chi2_export_index, chi2_plot_index)
        self.assertIn("Download χ² table (CSV)", html)
        self.assertIn('sptEl["spt-export-chi2-csv"].addEventListener("click", exportSpectralChi2Csv)', source)
        self.assertIn("function exportSpectralChi2Csv()", source)
        self.assertIn('.filter((row) => row.row_type === "chi2_grid")', source)
        self.assertIn('"reduced_chi2"', source)
        self.assertIn("mocadb_spectral_typing_chi2_${comparisonIdentifier()}", source)

    def test_gaia_xp_resolution_curve_matches_published_ecs_values(self):
        fwhm_um = app_module._spt_gaia_xp_fwhm_um([0.86, 0.88, 0.90, 0.92])
        np.testing.assert_allclose(
            fwhm_um,
            np.asarray([13.85, 14.50, 15.47, 16.07]) / 1000.0,
            rtol=0,
            atol=1e-12,
        )

    def test_spectral_typing_degrades_high_resolution_standard_to_gaia_xp_lsf(self):
        wavelength = np.arange(0.84, 0.941, 0.0005)
        flux = 1.0 + np.exp(-0.5 * ((wavelength - 0.90) / 0.0006) ** 2)
        standard = pd.DataFrame({
            "wv": wavelength,
            "sp": flux,
            "esp": np.full_like(wavelength, 0.01),
        })
        matched, info = app_module._spt_match_standard_resolution(
            standard,
            2000.0,
            58.0,
            standard_metadata={},
            comparison_metadata={
                "instrument_mode_name": "Gaia DR3 externally calibrated XP continuous mean spectrum",
            },
            comparison_wavelengths=np.arange(0.86, 0.921, 0.002),
        )
        line = matched["sp"].to_numpy(dtype=float) - 1.0
        above_half_max = wavelength[line >= 0.5 * float(np.nanmax(line))]
        measured_fwhm = float(above_half_max[-1] - above_half_max[0])
        self.assertTrue(info["applied"])
        self.assertEqual(info["mode"], "gaia_xp_wavelength_dependent_lsf")
        self.assertAlmostEqual(info["comparison_resolving_power"], 58.0)
        self.assertLessEqual(info["target_fwhm_max_nm"], 16.08)
        self.assertGreater(measured_fwhm, 0.013)
        self.assertLess(measured_fwhm, 0.018)
        self.assertLess(float(np.nanmax(line)), 0.15)

    def test_spectral_typing_does_not_smooth_standard_below_target_resolution(self):
        wavelength = np.arange(0.86, 0.94, 0.002)
        standard = pd.DataFrame({
            "wv": wavelength,
            "sp": 1.0 + 0.1 * np.sin(100.0 * wavelength),
            "esp": np.full_like(wavelength, 0.02),
        })
        matched, info = app_module._spt_match_standard_resolution(
            standard,
            30.0,
            58.0,
        )
        np.testing.assert_allclose(matched["sp"], standard["sp"], rtol=0, atol=0)
        self.assertFalse(info["applied"])
        self.assertEqual(info["reason"], "standard_not_higher_resolution")

    def test_spectral_typing_prefers_stored_resolution_over_sampling_density(self):
        wavelength = np.arange(0.86, 0.921, 0.002)
        sampling_resolution = app_module._spt_average_resolving_power(wavelength)
        payload = {
            "metadata": {
                "moca_specid": 800572,
                "moca_oid": 2513,
                "median_spectral_resolving_power": 58.0,
                "pix_per_res_element": 6.5,
                "instrument_mode_name": "Gaia DR3 externally calibrated XP continuous mean spectrum",
            },
            "spectrum": [
                {"moca_specid": 800572, "wv": float(wv), "sp": 1.0, "esp": 0.02}
                for wv in wavelength
            ],
            "meta": {
                "average_resolving_power": 58.0,
                "instrumental_resolving_power": 58.0,
                "median_spectral_resolving_power": 58.0,
                "sampling_resolving_power": sampling_resolution,
            },
        }
        comparison = app_module._spt_comparison_from_payloads([payload], 200)
        self.assertEqual(comparison["instrumental_resolving_power"], 58.0)
        self.assertEqual(comparison["average_resolving_power"], 58.0)
        self.assertAlmostEqual(comparison["sampling_resolving_power"], sampling_resolution)
        self.assertGreater(comparison["sampling_resolving_power"], 400.0)

    def test_spectral_typing_reports_resolution_matching_in_standard_metadata(self):
        source = (app_module.STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")
        self.assertIn("resolutionMatch?.applied", source)
        self.assertIn("Gaia XP wavelength-dependent LSF", source)
        self.assertIn("maximum smoothing-kernel FWHM", source)
        self.assertIn("standard <i>R</i> &asymp;", source)
        self.assertIn("comparison <i>R</i> &asymp;", source)

    def test_spectral_typing_composite_stitching_is_order_independent(self):
        def spectrum_payload(specid, start, stop, factor):
            wavelength = np.arange(start, stop + 0.0001, 0.01)
            intrinsic = 1.0 + 0.15 * wavelength + 0.03 * np.sin(8.0 * wavelength)
            return {
                "metadata": {
                    "moca_specid": specid,
                    "moca_oid": 602,
                    "designation": "Composite target",
                    "label": f"specid{specid}: Composite target",
                },
                "spectrum": [
                    {
                        "moca_specid": specid,
                        "wv": float(wv),
                        "sp": float(flux * factor),
                        "esp": float(0.01 * factor),
                    }
                    for wv, flux in zip(wavelength, intrinsic)
                ],
                "meta": {"average_resolving_power": 150.0},
            }

        payloads = [
            spectrum_payload(101, 0.82, 1.30, 4.0),
            spectrum_payload(102, 1.10, 1.62, 0.5),
            spectrum_payload(103, 1.45, 1.90, 2.5),
        ]
        forward = app_module._spt_comparison_from_payloads(payloads, 100)
        reverse = app_module._spt_comparison_from_payloads(list(reversed(payloads)), 100)
        pd.testing.assert_frame_equal(
            forward["comparison_raw"].reset_index(drop=True),
            reverse["comparison_raw"].reset_index(drop=True),
        )
        self.assertTrue(forward["stitching"]["composite"])
        self.assertEqual(len(forward["stitching"]["components"]), 1)
        self.assertGreaterEqual(len(forward["stitching"]["overlaps"]), 2)
        self.assertTrue(any(row["source_count"] > 1 for _, row in forward["comparison_raw"].iterrows()))

    def test_spectral_typing_composite_warns_for_disconnected_components(self):
        def payload(specid, start, stop, factor):
            wavelength = np.arange(start, stop + 0.0001, 0.01)
            return {
                "metadata": {"moca_specid": specid, "moca_oid": 602, "designation": "Target"},
                "spectrum": [
                    {"moca_specid": specid, "wv": float(wv), "sp": float(factor * (1 + wv)), "esp": 0.02}
                    for wv in wavelength
                ],
                "meta": {"average_resolving_power": 120.0},
            }

        result = app_module._spt_comparison_from_payloads([
            payload(201, 0.82, 1.10, 3.0),
            payload(202, 1.50, 1.80, 0.4),
        ], 100)
        self.assertEqual(len(result["stitching"]["components"]), 2)
        self.assertTrue(result["stitching"]["warnings"])
        self.assertTrue(all(row["method"] == "independent_median" for row in result["stitching"]["components"]))

    def test_spectral_typing_composite_requires_one_object(self):
        def payload(specid, oid):
            return {
                "metadata": {"moca_specid": specid, "moca_oid": oid, "designation": "Target"},
                "spectrum": [
                    {"moca_specid": specid, "wv": float(wv), "sp": float(1 + wv), "esp": 0.02}
                    for wv in np.arange(0.90, 1.21, 0.01)
                ],
                "meta": {"average_resolving_power": 120.0},
            }

        with self.assertRaisesRegex(ValueError, "same moca_oid"):
            app_module._spt_comparison_from_payloads([
                payload(301, 602),
                payload(302, 603),
            ], 100)

    def test_spectral_typing_mock_api_accepts_composite_specids(self):
        payload = decoded_json(self.client.post(
            "/api/spectral-typing/compare?mock=1",
            json={"specids": [451, 450], "bins": 200},
        ))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["meta"]["specids"], [450, 451])
        self.assertTrue(payload["meta"]["composite"])
        self.assertIsNone(payload["meta"]["specid"])
        self.assertIsNone(payload["comparisonMetadata"]["moca_specid"])
        self.assertEqual(payload["comparisonMetadata"]["moca_oid"], 990602)
        self.assertTrue(any(row.get("source_specids") == "450,451" for row in payload["comparison"]))

    def test_spectral_typing_composite_search_is_scoped_and_excludes_selected_specids(self):
        payload = decoded_json(self.client.get(
            "/api/spectral-typing/search?mock=1&moca_oid=990602&exclude_specids=450"
        ))
        self.assertTrue(payload["ok"])
        self.assertEqual([row["moca_specid"] for row in payload["options"]], [451, 452])
        self.assertEqual(payload["meta"]["required_moca_oid"], 990602)
        self.assertEqual(payload["meta"]["excluded_specids"], [450])

        other_object = decoded_json(self.client.get(
            "/api/spectral-typing/search?mock=1&q=13510&moca_oid=990602&exclude_specids=450,451"
        ))
        self.assertTrue(other_object["ok"])
        self.assertEqual(other_object["options"], [])

    def test_spectral_typing_composite_push_uses_null_specid_and_provenance_comment(self):
        specids, specid, composite = app_module._spt_push_comparison_selection({
            "moca_specid": None,
            "moca_specids": [451, 450],
        })
        self.assertEqual(specids, [450, 451])
        self.assertIsNone(specid)
        self.assertTrue(composite)
        comments = app_module._spt_push_comments(
            {
                "moca_specids": [451, 450],
                "stitching_summary": "overlap_graph, scales=450:1,451:2",
            },
            {
                "moca_specid": 9001,
                "grid": "field",
                "moca_sptgridhid": 77,
                "designation": "Standard",
            },
        )
        self.assertIn("combined_moca_specids=450,451", comments)
        self.assertIn("stitching=overlap_graph, scales=450:1,451:2", comments)

    def test_spectral_typing_composite_controls_are_progressively_disclosed(self):
        html = self.client.get("/js/spectral-typing").get_data(as_text=True)
        source = (app_module.STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")
        self.assertIn('id="spt-start-composite"', html)
        self.assertIn('id="spt-selected-spectra"', html)
        self.assertIn('id="spt-compute-composite"', html)
        self.assertIn("addSpectrumToComposite(result)", source)
        self.assertIn("specids.length > 1 ? { specids }", source)
        self.assertIn("moca_specid: comparisonSpecid", source)
        self.assertIn("moca_specids: comparisonSpecids", source)
        self.assertIn('params.set("moca_oid", requiredOid)', source)
        self.assertIn('params.set("exclude_specids", [...selectedSpecids].join(","))', source)

    def test_banyan_sigma_page_uses_greek_sigma_and_has_empty_plot_guidance(self):
        html = self.client.get("/js/banyan-sigma").get_data(as_text=True)
        script = (app_module.STATIC_DIR / "banyan_sigma.js").read_text(encoding="utf-8")
        self.assertIn(
            'Click "Load" to populate astrometry data, then "Run BANYAN Σ" to compute membership probabilities',
            html,
        )
        self.assertIn("Run BANYAN Σ", html)
        self.assertNotIn("BANYAN Sigma", html)
        self.assertNotIn("BANYAN Sigma", script)

    def test_moca_explorer_max_rows_uses_grouped_display_value(self):
        html = self.client.get("/js/moca-explorer").get_data(as_text=True)
        script = (app_module.STATIC_DIR / "moca_explorer.js").read_text(encoding="utf-8")
        self.assertIn('id="mex-max-objects" type="text" inputmode="numeric"', html)
        self.assertIn('value="80,000"', html)
        self.assertIn("formatMocaExplorerMaxObjectsInput()", script)
        self.assertIn("parseMocaExplorerMaxObjects()", script)

    def test_moca_explorer_projection_axes_and_hover_include_phase_space(self):
        script = (app_module.STATIC_DIR / "moca_explorer.js").read_text(encoding="utf-8")
        projection = script.split("function buildMocaExplorerProjectionPlot", 1)[1].split(
            "function buildMocaExplorer3dPlot",
            1,
        )[0]
        hover = script.split("function hoverText", 1)[1].split("function axisTitle", 1)[0]
        self.assertIn("includePhaseSpaceHover: true", projection)
        self.assertIn("title: { text: axisTitle(xAxis), standoff: 8", projection)
        self.assertIn("title: { text: axisTitle(yAxis), standoff: 8", projection)
        self.assertEqual(projection.count("automargin: true"), 2)
        self.assertIn('`XYZ (pc): X=${value("x")}, Y=${value("y")}, Z=${value("z")}`', hover)
        self.assertIn('`UVW (km/s): U=${value("u")}, V=${value("v")}, W=${value("w")}`', hover)

    def test_moca_explorer_association_removal_filters_complete_payload_in_browser(self):
        script = (app_module.STATIC_DIR / "moca_explorer.js").read_text(encoding="utf-8")
        remove_handler = script.split("function renderMocaExplorerAidChips()", 1)[1].split(
            "function setMocaExplorerAssociations",
            1,
        )[0]
        carve = script.split("function carveMocaExplorerAssociationsFromLoadedData", 1)[1].split(
            "function mocaExplorerPayloadMatchesControls",
            1,
        )[0]
        self.assertIn("setMocaExplorerAssociations(", remove_handler)
        self.assertNotIn("loadMocaExplorerData()", remove_handler)
        self.assertIn("payload.members = (payload.members || []).filter", carve)
        self.assertIn("payload.models = (payload.models || []).filter", carve)
        self.assertIn("payload.labels = (payload.labels || []).filter", carve)
        self.assertIn("!wasTruncated", carve)
        self.assertIn("retainedMembers.length >= maxObjects", carve)
        self.assertIn("members (filtered locally)", carve)

    def test_gaia_field_loader_has_gray_caption_and_tracks_field_request(self):
        html = self.client.get("/js/gaia-cmd").get_data(as_text=True)
        script = (app_module.STATIC_DIR / "gaia_cmd.js").read_text(encoding="utf-8")
        styles = (app_module.STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        caption = "Loading field data set and reference sequences"
        self.assertIn(f'aria-label="{caption}"', html)
        self.assertIn(f'<div class="plot-loader-label">{caption}</div>', html)
        self.assertIn(".gcmd-field-loader .plot-loader-label", styles)
        self.assertIn("color: #77717b", styles)

        load_block = script.split("async function loadGaiaCmdData()", 1)[1].split(
            "function gaiaCmdDataUrl",
            1,
        )[0]
        self.assertIn("setGaiaCmdLoader(!fieldWasCached)", load_block)
        partial_block = load_block.split("if (!fieldEntry.payload", 1)[1].split(
            "const fieldPayload",
            1,
        )[0]
        self.assertNotIn("setGaiaCmdLoader(false)", partial_block)

    def test_gaia_cmd_selected_rows_have_plot_marker_overlay(self):
        script = (app_module.STATIC_DIR / "gaia_cmd.js").read_text(encoding="utf-8")
        trace_block = script.split("function selectedGaiaCmdPointTrace", 1)[1].split(
            "function updateGaiaCmdSelectedPointMarker",
            1,
        )[0]
        events_block = script.split("function bindPlotEventsOnce", 1)[1].split(
            "function rowFromPoint",
            1,
        )[0]
        self.assertIn('uid: "selected-point-marker"', trace_block)
        self.assertIn('symbol: "star"', trace_block)
        self.assertIn('color: "#ffffff"', trace_block)
        self.assertIn('line: { color: "#d69e00", width: 3.2 }', trace_block)
        self.assertEqual(events_block.count("updateGaiaCmdSelectedPointMarker();"), 3)

    def test_gaia_cmd_field_rows_are_not_selectable(self):
        script = (app_module.STATIC_DIR / "gaia_cmd.js").read_text(encoding="utf-8")
        events_block = script.split("function bindPlotEventsOnce", 1)[1].split(
            "function rowFromGaiaCmdClick",
            1,
        )[0]
        click_resolution_block = script.split("function rowFromGaiaCmdClick", 1)[1].split(
            "function rowFromPoint",
            1,
        )[0]
        row_from_point_block = script.split("function rowFromPoint", 1)[1].split(
            "function uniqueRows",
            1,
        )[0]
        self.assertIn("rowFromGaiaCmdClick(event, plot)", events_block)
        self.assertIn("points.map(rowFromPoint).find(Boolean)", click_resolution_block)
        self.assertIn("nearestSelectableGaiaCmdRow(points[0], plot)", click_resolution_block)
        self.assertIn("gcmdSelectableClickRadiusPx ** 2", click_resolution_block)
        self.assertIn(
            "return row && (row.moca_aid || row._highlighted) ? row : null;",
            row_from_point_block,
        )

    def test_all_maintained_scatter_pages_have_default_preserving_symbol_size_control(self):
        scatter_pages = (
            "index.html",
            "gaia_cmd.html",
            "moca_explorer.html",
            "bd_evolution.html",
            "companion_explorer.html",
            "exoplanets_explorer.html",
            "spectral_typing.html",
            "astrometry.html",
            "spectra.html",
            "spectral_index_explorer.html",
            "sed.html",
            "xyzuvw_three.html",
            "xyz2_three.html",
            "xyzuvw.html",
            "xyz2.html",
            "moranta26_rotation.html",
            "rvbam_explorer.html",
            "retrieval_explorer.html",
        )
        for filename in scatter_pages:
            with self.subTest(filename=filename):
                html = (app_module.STATIC_DIR / filename).read_text(encoding="utf-8")
                self.assertEqual(html.count("data-scatter-symbol-size>"), 1)
                self.assertIn('value="100" data-scatter-symbol-size', html)
                self.assertIn("data-scatter-symbol-size-output>100%</output>", html)
                self.assertIn("static/scatter_symbol_size.js?v=20260710b", html)

        legacy_rv = (app_module.STATIC_DIR / "legacy_radial_velocities.html").read_text(encoding="utf-8")
        self.assertNotIn("data-scatter-symbol-size", legacy_rv)

    def test_symbol_size_helper_scales_plotly_and_three_markers_proportionally(self):
        script = (app_module.STATIC_DIR / "scatter_symbol_size.js").read_text(encoding="utf-8")
        self.assertIn('for (const method of ["newPlot", "react"])', script)
        self.assertIn('update = { "marker.size": [scaledSize(baseline.marker, scale)] }', script)
        self.assertIn('update["selected.marker.size"]', script)
        self.assertIn("prepareRestyle(graph, update, indexes)", script)
        self.assertIn("prepareAddedTraces(graph, traces, indexes)", script)
        self.assertIn("removeTraceBaselines(graph, indexes)", script)
        self.assertIn("registerThreeMaterial", script)
        self.assertIn("unregisterThreeMaterial", script)

        three_script = (app_module.STATIC_DIR / "xyzuvw_three.js").read_text(encoding="utf-8")
        self.assertIn("registerThreeMaterial?.(material, xuvMemberPointSize)", three_script)
        self.assertIn('document.addEventListener("scatter-symbol-size-change"', three_script)
        self.assertIn("dataset.scatterSymbolSize", three_script)

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

    def test_home_page_advertises_moca_explorer(self):
        response = self.client.get("/js/")
        try:
            html = response.get_data(as_text=True)
            self.assertIn(
                '<a data-js-page href="/moca-explorer">MOCA Explorer</a>',
                html,
            )
            self.assertNotIn(
                '<li hidden>\n          <a data-js-page href="/moca-explorer"',
                html,
            )
        finally:
            response.close()


if __name__ == "__main__":
    unittest.main()
