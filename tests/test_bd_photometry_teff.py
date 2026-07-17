from __future__ import annotations

import unittest

import bd_colors_fast.app as app_module


class BdPhotometryTeffTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_teff_is_an_axis_without_a_quantity_selector(self):
        self.assertIn("teff", app_module.AXIS_TYPES)
        self.assertEqual(
            app_module._axis_spec({"xaxis_type": "teff"}, "x"),
            ("teff", "", ""),
        )
        sequence_sql, sequence_params = app_module._sequence_filter_sql({
            "xaxis_type": "teff",
            "yaxis_type": "spectral_type",
        })
        self.assertEqual(sequence_params, {"x_type": "teff", "y_type": "spectral_type"})
        self.assertNotIn("xaxis_value", sequence_sql)
        self.assertNotIn("yaxis_value", sequence_sql)

    def test_default_teff_query_ranks_adopted_rows_per_object(self):
        sql = app_module._teff_measurement_query_sql(
            {},
            oid_filter="dt.moca_oid IN (10,20)",
        )
        ranked_block = sql.split("ROW_NUMBER() OVER", 1)[1].split(") AS teff_rank", 1)[0]

        self.assertIn("dt.adopted = 1", sql)
        self.assertNotIn("dt.moca_pid IN ('Sang23', 'Fili15')", sql)
        self.assertIn("PARTITION BY dt.moca_oid", ranked_block)
        self.assertIn("CASE UPPER(TRIM(COALESCE(dt.quality, '')))", ranked_block)
        self.assertIn("COALESCE(dt.teff_k_unc, 1.0e308)", ranked_block)
        self.assertLess(ranked_block.index("WHEN 'A'"), ranked_block.index("WHEN 'B'"))
        self.assertLess(ranked_block.index("WHEN 'B'"), ranked_block.index("COALESCE(dt.teff_k_unc"))
        self.assertLess(ranked_block.index("COALESCE(dt.teff_k_unc"), ranked_block.index("dt.id"))
        self.assertIn("ranked_teff.teff_rank = 1", sql)

    def test_sed_teff_query_switches_candidates_but_keeps_ranking(self):
        sql = app_module._teff_measurement_query_sql(
            {"sed_teff": "1"},
            oid_filter="dt.moca_oid IN (10,20)",
        )

        self.assertIn("dt.moca_pid IN ('Sang23', 'Fili15')", sql)
        self.assertNotIn("dt.adopted = 1", sql)
        self.assertIn("COALESCE(dt.ignored, 0) = 0", sql)
        self.assertIn("dt.moca_oid IN (10,20)", sql)
        self.assertIn("PARTITION BY dt.moca_oid", sql)
        self.assertIn("ranked_teff.teff_rank = 1", sql)

    def test_mock_teff_feature_is_always_unique_by_oid(self):
        base_query = "mock=1&xaxis_type=teff&yaxis_type=spectral_type"
        adopted = self.client.get(f"/api/feature/teffs?{base_query}").get_json()
        sed = self.client.get(f"/api/feature/teffs?{base_query}&sed_teff=1").get_json()

        adopted_oids = [row["moca_oid"] for row in adopted["rows"]]
        sed_oids = [row["moca_oid"] for row in sed["rows"]]
        self.assertEqual(len(adopted_oids), len(set(adopted_oids)))
        self.assertEqual(len(sed_oids), len(set(sed_oids)))
        self.assertTrue(all(row["adopted"] == 1 for row in adopted["rows"]))
        self.assertTrue(all(row["moca_pid"] in {"Sang23", "Fili15"} for row in sed["rows"]))
        first_sed = next(row for row in sed["rows"] if row["moca_oid"] == 900000)
        self.assertEqual((first_sed["id"], first_sed["quality"], first_sed["teff_k_unc"]), (4_000_003, "A", 25.0))
        self.assertFalse(adopted["meta"]["only_sed_teff"])
        self.assertTrue(sed["meta"]["only_sed_teff"])

    def test_teff_checkbox_and_lazy_feature_are_wired_to_the_page(self):
        html = self.client.get("/js/bd-colors").get_data(as_text=True)
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="sed-teff-line" class="checkline" hidden', html)
        self.assertIn('id="only-sed-teff" type="checkbox"', html)
        self.assertIn("Only plot <i>T</i><sub>eff</sub> values obtained from SED analysis", html)
        self.assertIn('id="teff-jitter" type="range" min="0" max="200"', html)
        self.assertIn('step="5" value="30"', html)
        self.assertIn('id="x-teff-log" type="checkbox"', html)
        self.assertIn('id="y-teff-log" type="checkbox"', html)
        self.assertIn('{ value: "teff", label: "Teff" }', script)
        self.assertIn('if (sedTeffRequested()) params.set("sed_teff", "1")', script)
        self.assertIn('params.set(`${axis}axis_log`, "1")', script)
        self.assertIn('params.set("teff_jitter", String(jitterK))', script)
        self.assertIn("const teffJitterDefaultK = 30", script)
        self.assertIn('if (type === "teff") return "100"', script)
        self.assertIn('value === "teff" ? changedAxis : ""', script)
        self.assertIn('applyAxisErrorDefaults({}, forceErrorDefaultAxis)', script)
        self.assertIn('if (spec.type === "teff")', script)
        self.assertIn('teffs: "teffs"', script)
        self.assertIn('const teffAxisLabelHtml = "<i>T</i><sub>eff</sub>"', script)
        self.assertIn('label: `${teffAxisLabelHtml} (K)`', script)
        self.assertIn('teff_ref: row.moca_pid || ""', script)
        self.assertIn('tableColumn("teff_ref")', script)
        export_block = script.split("const exportColumns = [", 1)[1].split("];", 1)[0]
        self.assertIn('"teff_ref"', export_block)

    def test_teff_axis_orientation_log_and_jitter_are_wired(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        layout_block = script.split("function axisLayout(axis, label, rows, initialRange)", 1)[1].split(
            "function axisTitleLabel",
            1,
        )[0]

        self.assertIn('const isReversedTeffX = axis === "x" && isTeff', layout_block)
        self.assertIn('if (isLogTeff) layout.type = "log"', layout_block)
        self.assertIn('layout.autorange = "reversed"', layout_block)
        self.assertIn('if (axisType === "teff") return value + deterministicTeffJitter', script)
        self.assertIn('spec.type === "teff" ? `jitter:${teffJitterK()}`', script)


if __name__ == "__main__":
    unittest.main()
