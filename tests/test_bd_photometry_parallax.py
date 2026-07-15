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


if __name__ == "__main__":
    unittest.main()
