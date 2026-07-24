import unittest
from pathlib import Path

from mocaviz import app as app_module


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "mocaviz" / "static"


class SpectralTypingFieldFilterTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_page_exposes_field_only_checkbox_and_persists_it(self):
        html = (STATIC_DIR / "spectral_typing.html").read_text(encoding="utf-8")
        source = (STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")

        self.assertIn('id="spt-only-field"', html)
        self.assertIn("Only consider field, solar-metallicity objects", html)
        self.assertIn('params.set("only_field", "1")', source)
        self.assertIn("only_field: onlyFieldObjectsEnabled()", source)
        self.assertIn(
            'sptEl["spt-only-field"].addEventListener("change", reloadSpectralStandards)',
            source,
        )

    def test_mock_moca_grid_is_limited_to_field_templates(self):
        response = self.client.get(
            "/api/spectral-typing/grid?mock=1&standards_source=moca&only_field=1"
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["options"], [{"label": "field", "value": "field"}])
        self.assertEqual({row["grid"] for row in payload["gridData"]}, {"field"})
        self.assertTrue(payload["meta"]["only_field_objects"])

    def test_mock_pickles_grid_is_limited_to_solar_dwarfs(self):
        response = self.client.get(
            "/api/spectral-typing/grid?mock=1&standards_source=pickles&only_field_objects=true"
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["options"],
            [{"label": "V solar M/H", "value": "V solar M/H"}],
        )
        self.assertEqual(
            {row["grid"] for row in payload["gridData"]},
            {"V solar M/H"},
        )
        self.assertTrue(payload["meta"]["only_field_objects"])
        self.assertEqual(
            payload["meta"]["pickles_template_count"],
            len(payload["gridData"]),
        )


if __name__ == "__main__":
    unittest.main()
