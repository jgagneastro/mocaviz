from __future__ import annotations

import inspect
import unittest

import bd_colors_fast.app as app_module


class BdPhotometryParallaxTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_bootstrap_objects_include_requested_parallax_fields(self):
        payload = self.client.get("/api/bootstrap?mock=1").get_json()

        self.assertTrue(payload["ok"])
        row = payload["catalog"]["objects"][0]
        self.assertIsInstance(row["parallax_mas"], float)
        self.assertIsInstance(row["parallax_mas_error"], float)
        self.assertTrue(row["parallax_ref"])
        self.assertTrue(any(candidate["parallax_mas"] is None for candidate in payload["catalog"]["objects"]))

    def test_object_query_uses_only_the_adopted_parallax(self):
        source = " ".join(inspect.getsource(app_module._load_bootstrap_from_db).split())

        self.assertIn("dplx.parallax_mas", source)
        self.assertIn("dplx.parallax_mas_unc AS parallax_mas_error", source)
        self.assertIn("dplx.bibcode AS parallax_ref", source)
        self.assertIn(
            "LEFT JOIN data_parallaxes dplx ON dplx.moca_oid = dst.moca_oid AND dplx.adopted = 1",
            source,
        )

    def test_table_and_exports_include_parallax_columns(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        table_block = script.split("function renderTable(oids)", 1)[1].split(
            "function bdTableMarkerHtml", 1
        )[0]
        export_block = script.split("const exportColumns = [", 1)[1].split("];", 1)[0]

        for column in ("parallax_mas", "parallax_mas_error", "parallax_ref"):
            self.assertIn(f'tableColumn("{column}")', table_block)
            self.assertIn(f'"{column}"', export_block)

    def test_photometric_distance_option_is_the_inverse_parallax_filter(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        html = self.client.get("/js/bd-colors").get_data(as_text=True)
        build_rows_block = script.split("function buildRows()", 1)[1].split(
            "function associationHighlightForObject", 1
        )[0]

        self.assertIn('id="include-photdist" type="checkbox"', html)
        self.assertNotIn('id="only-trig-parallaxes"', html)
        self.assertNotIn("only-trig-parallaxes", script)
        self.assertIn('params.delete("trigplx")', script)
        self.assertNotIn("function updatePhotdistControl", script)
        self.assertIn('state.manualPhotdistChoice = params.has("photdist")', script)
        self.assertIn("function applyPhotometricDistanceDefault()", script)
        self.assertIn("const checked = !hasAbsoluteMagnitudeAxis()", script)
        self.assertIn("const includePhotdist = includePhotometricDistances()", build_rows_block)
        self.assertIn("const usePhotdistForAxes = usePhotometricDistancesForAxes()", build_rows_block)
        self.assertIn(
            "is_photometric_distance: usePhotdistForAxes &&",
            build_rows_block,
        )
        self.assertIn(
            "if (!includePhotdist && !Number.isFinite(numericValue(object.parallax_mas))) continue;",
            build_rows_block,
        )

    def test_capped_selection_prioritizes_objects_with_all_axis_photometry(self):
        args = {
            "spt_range": "L0+",
            "photspt": "1",
            "max_objects": "5000",
            "xaxis_type": "spectral_type",
            "yaxis_type": "color",
            "yaxis_value_1": "euclid_ymag",
            "yaxis_value_2": "euclid_hmag",
        }

        priority_sql, priority_params = app_module._axis_photometry_priority_sql(args)
        selection_sql = app_module._selected_oids_subquery_sql(
            "dst.adopted = 1",
            "\n            LIMIT 5000",
            priority_sql,
        )

        self.assertEqual(
            priority_params,
            {
                "axis_photometry_priority_0": "euclid_ymag",
                "axis_photometry_priority_1": "euclid_hmag",
            },
        )
        self.assertEqual(priority_sql.count("EXISTS ("), 2)
        self.assertIn("dp_priority_0.moca_oid = dst.moca_oid", priority_sql)
        self.assertIn("dp_priority_1.moca_oid = dst.moca_oid", priority_sql)
        self.assertIn("dp_priority_0.magnitude_unc IS NOT NULL", priority_sql)
        order_sql = selection_sql.split("ORDER BY", 1)[1]
        self.assertLess(order_sql.index("CASE WHEN"), order_sql.index("dst.spectral_type_number"))
        self.assertLess(order_sql.index("CASE WHEN"), order_sql.index("LIMIT 5000"))


if __name__ == "__main__":
    unittest.main()
