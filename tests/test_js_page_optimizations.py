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
            "&gaia_quality=off&filter_wd=0&max_objects=80"
        ))
        self.assertTrue(highlights["rows"])
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

        script = (app_module.STATIC_DIR / "gaia_cmd.js").read_text(encoding="utf-8")
        styles = (app_module.STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        self.assertIn('const gcmdMissingVettedMtid = "missing";', script)
        self.assertIn("const matchesMissing = Boolean(row?.moca_aid)", script)
        self.assertIn("selected.includes(gcmdMissingVettedMtid)", script)
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
        with (
            patch.object(app_module, "_db_table_exists", return_value=True),
            patch.object(app_module, "_db_table_columns", side_effect=lambda _conn, table: table_columns.get(table, set())),
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
            with (
                patch.object(app_module, "SHARED_PAGE_CACHE_DIR", Path(directory)),
                patch.object(
                    app_module,
                    "_xyzuvw_model_surfaces",
                    side_effect=lambda _models, axes: [{"axes": "".join(axes)}],
                ) as generator,
            ):
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
        self.assertIn("searchSpectra(\"\", { selectedSpecid", spectral_init)
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


if __name__ == "__main__":
    unittest.main()
