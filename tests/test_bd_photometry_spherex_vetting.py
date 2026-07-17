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
        rows_by_oid = {row["moca_oid"]: row["classification"] for row in payload["rows"]}
        self.assertEqual(rows_by_oid[900000], "good")  # specpack 54
        self.assertEqual(rows_by_oid[900001], "bad")  # specpack 55
        self.assertEqual(rows_by_oid[900003], "missing")  # specpack 63
        self.assertEqual(rows_by_oid[900005], "missing")  # specpack 90
        self.assertEqual(rows_by_oid[900006], "missing")  # unlisted specpack

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
        self.assertIn("function toggleSpherexVettingClassification(classification)", script)
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
