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

    def test_trigonometric_parallax_filter_is_default_off_and_url_addressable(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        html = self.client.get("/js/bd-colors").get_data(as_text=True)
        build_rows_block = script.split("function buildRows()", 1)[1].split(
            "function associationHighlightForObject", 1
        )[0]

        self.assertIn('id="only-trig-parallaxes" type="checkbox"', html)
        self.assertNotIn('id="only-trig-parallaxes" type="checkbox" checked', html)
        self.assertIn("Plot only objects with trigonometric parallaxes", html)
        self.assertIn('params.get("trigplx")', script)
        self.assertIn('params.set("trigplx", el["only-trig-parallaxes"].checked ? "1" : "0")', script)
        self.assertIn("const onlyTrigParallaxes", build_rows_block)
        self.assertIn("!Number.isFinite(numericValue(object.parallax_mas))", build_rows_block)


if __name__ == "__main__":
    unittest.main()
