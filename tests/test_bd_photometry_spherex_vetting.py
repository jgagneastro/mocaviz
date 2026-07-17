from __future__ import annotations

import unittest

import bd_colors_fast.app as app_module


class BdPhotometrySpherexVettingTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_axis_detection_handles_spherex_photometry_and_indices(self):
        photometry, indices = app_module._spherex_axis_observables({
            "xaxis_type": "color",
            "xaxis_value_1": "spherex_smag",
            "xaxis_value_2": "mko_jmag",
            "yaxis_type": "spectral_index",
            "yaxis_value_1": "spx_co2",
        })

        self.assertEqual(photometry, ["spherex_smag"])
        self.assertEqual(indices, ["spx_co2"])
        self.assertEqual(
            app_module._spherex_axis_observables({
                "xaxis_type": "spectral_index",
                "xaxis_value_1": "h2o_j",
                "yaxis_type": "absolute_magnitude",
                "yaxis_value_1": "mko_jmag",
            }),
            ([], []),
        )

    def test_query_routes_specpacks_and_maps_unvetted_sources_to_missing(self):
        sql, params = app_module._spherex_vetting_query_sql(
            {
                "xaxis_type": "absolute_magnitude",
                "xaxis_value_1": "spherex_smag",
                "yaxis_type": "spectral_index",
                "yaxis_value_1": "spx_ch4",
            },
            "source_rows.moca_oid IN (10,20)",
        )

        self.assertEqual(params, {
            "spherex_psid_0": "spherex_smag",
            "spherex_siid_0": "spx_ch4",
        })
        self.assertIn("WHEN 54 THEN 'good'", sql)
        self.assertIn("WHEN 55 THEN COALESCE", sql)
        self.assertIn("WHEN 62 THEN COALESCE", sql)
        self.assertIn("WHEN 76 THEN COALESCE", sql)
        self.assertIn("ELSE 'missing'", sql)
        self.assertNotIn("WHEN 63", sql)
        self.assertNotIn("WHEN 90", sql)
        for table in app_module.BDPHOT_SPHEREX_VETTING_TABLES.values():
            self.assertIn(f"LEFT JOIN {table}", sql)
        self.assertIn("dp.moca_oid IN (10,20)", sql)
        self.assertIn("dsi.moca_oid IN (10,20)", sql)
        self.assertIn("source_rows.moca_specid", sql)
        self.assertIn("SELECT dp.moca_oid, dp.moca_specid", sql)
        self.assertIn("SELECT dsi.moca_oid, dsi.moca_specid", sql)

    def test_measurement_vetting_is_inside_the_best_candidate_set(self):
        args = {
            "dbase": "mocadb_private_tables",
            "user": "management",
            "pwd": "mock",
            "xaxis_type": "spectral_type",
            "yaxis_type": "spectral_index",
            "yaxis_value_1": "spx_ch4",
            "spherex_classification": "good",
            "best_measurement": "1",
        }
        vetting_sql, vetting_params = app_module._spherex_measurement_vetting_filter_sql(
            args,
            alias="dsi",
            quantity_column="moca_siid",
            observable_values=["spx_ch4"],
            param_prefix="spectral_index_vetting",
        )
        sql = app_module._spectral_index_measurement_query_sql(
            args,
            oid_filter="dsi.moca_oid IN (10,20)",
            siid_filter="dsi.moca_siid = :siid_0",
            vetting_filter_sql=vetting_sql,
        )
        ranked_block = sql.split("FROM (", 1)[1].split(") ranked_measurements", 1)[0]

        self.assertEqual(vetting_params, {
            "spectral_index_vetting_observable_0": "spx_ch4",
            "spectral_index_vetting_classification_0": "good",
        })
        self.assertIn("dsi.moca_siid NOT IN (:spectral_index_vetting_observable_0)", ranked_block)
        self.assertIn("vetting_spectrum.moca_specid = dsi.moca_specid", ranked_block)
        self.assertIn("pcat_spherex_spiffstacker_visual_vetting", ranked_block)
        self.assertIn("ROW_NUMBER() OVER", ranked_block)
        self.assertIn("WHERE dsi.ignored = 0", ranked_block)

        inactive_sql, inactive_params = app_module._spherex_measurement_vetting_filter_sql(
            {**args, "spherex_classification": ""},
            alias="dsi",
            quantity_column="moca_siid",
            observable_values=["spx_ch4"],
            param_prefix="spectral_index_vetting",
        )
        self.assertEqual((inactive_sql, inactive_params), ("1 = 1", {}))
        frontend_sql, frontend_params = app_module._spherex_measurement_vetting_filter_sql(
            {**args, "best_measurement": "0"},
            alias="dsi",
            quantity_column="moca_siid",
            observable_values=["spx_ch4"],
            param_prefix="spectral_index_vetting",
        )
        self.assertEqual((frontend_sql, frontend_params), ("1 = 1", {}))
        self.assertNotEqual(
            app_module._cache_key(args),
            app_module._cache_key({**args, "spherex_classification": "bad"}),
        )
        self.assertEqual(
            app_module._cache_key({**args, "best_measurement": "0"}),
            app_module._cache_key({
                **args,
                "best_measurement": "0",
                "spherex_classification": "bad",
            }),
        )

    def test_mock_good_filter_precedes_best_spx_measurement_selection(self):
        common = (
            "/api/feature/spectral-indices?mock=1"
            "&dbase=mocadb_private_tables&user=management&pwd=mock"
            "&xaxis_type=spectral_type&yaxis_type=spectral_index&yaxis_value_1=spx_ch4"
            "&best_measurement=1"
        )
        unfiltered = self.client.get(common).get_json()
        good = self.client.get(f"{common}&spherex_classification=good").get_json()

        unfiltered_row = next(row for row in unfiltered["rows"] if row["moca_oid"] == 900000)
        good_row = next(row for row in good["rows"] if row["moca_oid"] == 900000)
        self.assertEqual((unfiltered_row["id"], unfiltered_row["moca_specpackid"]), (2_000_005, 62))
        self.assertEqual((good_row["id"], good_row["moca_specpackid"]), (2_000_001, 54))

        frontend_rows = self.client.get(
            common.replace("&best_measurement=1", "") + "&spherex_classification=good"
        ).get_json()["rows"]
        frontend_oid_rows = {row["id"] for row in frontend_rows if row["moca_oid"] == 900000}
        self.assertEqual(frontend_oid_rows, {2_000_001, 2_000_005})

        vetting = self.client.get(
            "/api/feature/spherex-vetting?mock=1"
            "&dbase=mocadb_private_tables&user=management&pwd=mock"
            "&xaxis_type=spectral_type&yaxis_type=spectral_index&yaxis_value_1=spx_ch4"
            "&spherex_classification=good"
        ).get_json()
        oid_classifications = {
            row["classification"] for row in vetting["rows"] if row["moca_oid"] == 900000
        }
        self.assertEqual(oid_classifications, {"bad", "good"})
        oid_specids = {
            row["moca_specid"] for row in vetting["rows"] if row["moca_oid"] == 900000
        }
        self.assertEqual(oid_specids, {1_140_000, 1_160_000})

    def test_mock_private_feature_includes_dynamic_classifications_and_missing(self):
        common = (
            "/api/feature/spherex-vetting?mock=1"
            "&dbase=mocadb_private_tables&user=management&pwd=mock"
            "&xaxis_type=spectral_type&yaxis_type=spectral_index&yaxis_value_1=spx_ch4"
        )
        payload = self.client.get(common).get_json()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["meta"]["available"])
        self.assertEqual(payload["meta"]["missing_value"], "missing")
        self.assertIn("good", payload["meta"]["classifications"])
        self.assertIn("bad", payload["meta"]["classifications"])
        self.assertIn("missing", payload["meta"]["classifications"])
        rows_by_oid = {}
        for row in payload["rows"]:
            rows_by_oid.setdefault(row["moca_oid"], set()).add(row["classification"])
        self.assertEqual(rows_by_oid[900000], {"good", "bad"})  # specpacks 54 and 62
        self.assertEqual(rows_by_oid[900001], {"bad"})  # specpack 55
        self.assertEqual(rows_by_oid[900003], {"missing"})  # specpack 63
        self.assertEqual(rows_by_oid[900005], {"missing"})  # specpack 90
        self.assertEqual(rows_by_oid[900006], {"missing"})  # unlisted specpack

        public_payload = self.client.get(
            "/api/feature/spherex-vetting?mock=1&dbase=mocadb&user=public"
            "&xaxis_type=spectral_index&xaxis_value_1=spx_ch4"
        ).get_json()
        self.assertFalse(public_payload["meta"]["available"])
        self.assertEqual(public_payload["rows"], [])

    def test_private_axis_panel_and_client_filter_are_wired(self):
        html = self.client.get("/js/bd-colors").get_data(as_text=True)
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        styles = (app_module.STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        build_params_block = script.split("function buildBootstrapParams()", 1)[1].split(
            "function updateUrlFromControls",
            1,
        )[0]
        toggle_block = script.split("function toggleSpherexVettingClassification(classification)", 1)[1].split(
            "function updateSpherexVettingControl",
            1,
        )[0]

        self.assertIn('id="spherex-vetting-panel"', html)
        self.assertIn('id="spherex-vetting-classifications"', html)
        self.assertIn('class="gcmd-multiselect spherex-vetting-listbox"', html)
        self.assertIn('role="listbox"', html)
        self.assertIn("<code>spherex_classification</code>", html)
        self.assertIn('const spherexMissingVettingClassification = "missing";', script)
        self.assertIn('{ value: "missing", label: "Missing" }', script)
        self.assertIn('{ value: "peculiar_ucd", label: "Good but peculiar" }', script)
        self.assertIn('{ value: "good_reddened", label: "Good with extinction" }', script)
        self.assertIn('{ value: "contaminated_ucd", label: "Good but contaminated" }', script)
        self.assertIn("function orderedSpherexVettingClassifications(values)", script)
        self.assertIn("function applySpherexVettingParams(params)", script)
        self.assertIn('if (type === "spectral_index") return value1.startsWith("spx")', script)
        self.assertIn("return applySpherexVettingParams(params)", build_params_block)
        self.assertIn("function toggleSpherexVettingClassification(classification)", script)
        self.assertIn('if (el["only-best-measurement"].checked)', toggle_block)
        self.assertIn("scheduleBootstrapReload({ resetAxisRange: true })", toggle_block)
        self.assertIn("state.forceFreshPlot = true", toggle_block)
        self.assertIn("function spherexVettingAllowsMeasurement(row)", script)
        self.assertIn("function spherexVettedMeasurementRows(rows, observable, kind)", script)
        self.assertIn("spherexVettingBySpecid", script)
        self.assertIn('event.key === "ArrowDown"', script)
        self.assertIn('event.key === "Home"', script)
        self.assertIn('state.forceFreshPlot = true;', script)
        self.assertIn('class="spherex-vetting-option-count">(${option.count.toLocaleString()})', script)
        self.assertIn("function spherexVettingPanelEligible()", script)
        self.assertIn("function spherexVettingAllowsObject(oid)", script)
        self.assertIn("if (!spherexVettingAllowsObject(oid)) continue;", script)
        self.assertIn("api/feature/spherex-vetting", script)
        self.assertIn(".spherex-vetting-option-missing", styles)
        self.assertIn(".spherex-vetting-option-count", styles)


if __name__ == "__main__":
    unittest.main()
