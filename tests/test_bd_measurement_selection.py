from __future__ import annotations

import unittest

import bd_colors_fast.app as app_module


class BdMeasurementSelectionTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_control_is_off_by_default_and_round_trips_through_url(self):
        html = self.client.get("/js/bd-colors").get_data(as_text=True)
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="only-best-measurement" type="checkbox"', html)
        self.assertNotIn('id="only-best-measurement" type="checkbox" checked', html)
        self.assertIn("Only plot the best measurement per brown dwarf", html)
        self.assertIn('params.get("best_measurement")', script)
        self.assertIn('params.set("best_measurement", el["only-best-measurement"].checked ? "1" : "0")', script)
        self.assertIn('el["only-best-measurement"].addEventListener("change"', script)
        self.assertIn("scheduleBootstrapReload({ resetAxisRange: true })", script)

    def test_raw_spectral_index_query_keeps_measurement_rows_intact(self):
        sql = app_module._spectral_index_measurement_query_sql(
            {},
            oid_filter="dsi.moca_oid IN (10,20)",
            siid_filter="dsi.moca_siid = :siid_0",
        )

        self.assertIn("dsi.id", sql)
        self.assertIn("dsi.index_value", sql)
        self.assertIn("dsi.index_value_unc", sql)
        self.assertNotIn("ROW_NUMBER()", sql)
        self.assertNotIn("GROUP BY", sql)
        self.assertNotIn("MIN(dsi.", sql)
        self.assertIn("ORDER BY dsi.moca_oid, dsi.moca_siid, dsi.id", sql)

    def test_best_query_ranks_filtered_candidates_by_uncertainty_then_id(self):
        sql = app_module._spectral_index_measurement_query_sql(
            {"best_measurement": "1"},
            oid_filter="dsi.moca_oid IN (10,20)",
            siid_filter="dsi.moca_siid = :siid_0",
        )
        ranked_block = sql.split("FROM (", 1)[1].split(") ranked_measurements", 1)[0]

        self.assertIn("PARTITION BY dsi.moca_oid, dsi.moca_siid", ranked_block)
        self.assertIn("ORDER BY COALESCE(dsi.index_value_unc, 1.0e308), dsi.id", ranked_block)
        self.assertIn("dsi.moca_oid IN (10,20)", ranked_block)
        self.assertIn("dsi.moca_siid = :siid_0", ranked_block)
        self.assertIn("ranked_measurements.measurement_rank = 1", sql)
        self.assertLess(sql.index("ranked_measurements.measurement_rank = 1"), sql.index("JOIN moca_spectral_indices"))

    def test_equivalent_width_and_photometry_use_the_same_deterministic_rule(self):
        ew_sql = app_module._equivalent_width_measurement_query_sql(
            {"best_measurement": "1"},
            oid_filter="dew.moca_oid IN (10,20)",
        )
        phot_sql = app_module._photometry_measurement_query_sql(
            {"best_measurement": "1"},
            source_from_sql="data_photometry dp",
            candidate_filter_sql="dp.adopted = 1 AND dp.moca_oid IN (10,20)",
        )

        self.assertIn("PARTITION BY dew.moca_oid, dew.moca_spid", ew_sql)
        self.assertIn("COALESCE(dew.ew_angstrom_unc, 1.0e308), dew.id", ew_sql)
        self.assertIn("PARTITION BY dp.moca_oid, dp.moca_psid", phot_sql)
        self.assertIn("COALESCE(dp.magnitude_unc, 1.0e308), dp.id", phot_sql)
        self.assertIn("dp.moca_oid IN (10,20)", phot_sql.split(") ranked_measurements", 1)[0])

    def test_mock_api_exposes_duplicates_by_default_and_best_row_on_request(self):
        query = "mock=1&xaxis_type=spectral_type&yaxis_type=spectral_index&yaxis_value_1=h2o_j"
        raw = self.client.get(f"/api/feature/spectral-indices?{query}").get_json()
        best = self.client.get(f"/api/feature/spectral-indices?{query}&best_measurement=1").get_json()

        raw_rows = [row for row in raw["rows"] if row["moca_oid"] == 900000]
        best_rows = [row for row in best["rows"] if row["moca_oid"] == 900000]
        self.assertEqual([(row["id"], row["index_value_unc"]) for row in raw_rows], [
            (2_000_000, 0.02),
            (2_000_003, 0.01),
            (2_000_004, None),
        ])
        self.assertEqual([(row["id"], row["index_value_unc"]) for row in best_rows], [
            (2_000_003, 0.01),
        ])
        self.assertFalse(raw["meta"]["only_best_measurement"])
        self.assertTrue(best["meta"]["only_best_measurement"])

    def test_mock_ties_use_the_lowest_id_and_null_uncertainty_ranks_last(self):
        rows = [
            {"id": 9, "moca_oid": 1, "moca_siid": "x", "index_value_unc": None},
            {"id": 8, "moca_oid": 1, "moca_siid": "x", "index_value_unc": 0.2},
            {"id": 7, "moca_oid": 1, "moca_siid": "x", "index_value_unc": 0.2},
        ]
        selected = app_module._mock_best_measurement_rows(
            rows,
            key_fields=("moca_oid", "moca_siid"),
            uncertainty_field="index_value_unc",
        )

        self.assertEqual([row["id"] for row in selected], [7])

    def test_frontend_maps_quantity_rows_to_arrays_and_expands_measurements(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        nested_block = script.split("function addNestedRows", 1)[1].split("function dataCountBy", 1)[0]
        build_block = script.split("function buildRows()", 1)[1].split("function associationHighlightForObject", 1)[0]

        self.assertIn("target.get(oid).get(key).push(row)", nested_block)
        self.assertIn("const xMeasurements = axisValues", build_block)
        self.assertIn("const yMeasurements = axisValues", build_block)
        self.assertIn("for (const [x, y] of measurementPairs)", build_block)
        self.assertIn("function axisMeasurementPairs", script)
        self.assertIn("return xMeasurements.flatMap((x) => yMeasurements.map((y) => [x, y]))", script)

    def test_frontend_selection_uses_hidden_measurement_row_ids(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        table_block = script.split("function renderTable(rowIds)", 1)[1].split(
            "function bdTableMarkerHtml",
            1,
        )[0]
        export_block = script.split("const exportColumns = [", 1)[1].split("];", 1)[0]

        self.assertIn("row_id: measurementKey", script)
        self.assertIn("customdata: rows.map((row) => row.row_id)", script)
        self.assertIn("function selectedPlotRowIds(event)", script)
        self.assertIn("function clickedPlotRowId(event)", script)
        self.assertIn("state.selectedRowIds = [rowId]", script)
        self.assertIn("rowIds.includes(row.row_id)", table_block)
        self.assertIn("state.selectedRowIds.includes(row.row_id)", script)
        self.assertNotIn("selectedOids", script)
        self.assertNotIn("customdata: rows.map((row) => row.moca_oid)", script)
        self.assertNotIn('tableColumn("row_id")', table_block)
        self.assertNotIn('"row_id"', export_block)


if __name__ == "__main__":
    unittest.main()
