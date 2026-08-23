import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from mocaviz import app as app_module


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "mocaviz" / "static"


class SpectralTypingOverlapTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_log_wavelength_overlap_uses_comparison_coverage(self):
        wavelength = np.exp(np.linspace(0.0, 1.0, 101))
        comparison = pd.DataFrame({"wv": wavelength})
        standard = pd.DataFrame({"wv": wavelength[10:91]})

        overlap = app_module._spt_log_wavelength_overlap_percent(
            comparison,
            standard,
            [(1.0, float(np.e))],
        )

        self.assertAlmostEqual(overlap, 80.0, places=10)

    def test_log_wavelength_overlap_equally_averages_window_percentages(self):
        broad_window = np.exp(np.linspace(0.0, 2.0, 201))
        narrow_window = np.exp(np.linspace(3.0, 4.0, 101))
        comparison = pd.DataFrame({
            "wv": np.concatenate([broad_window, narrow_window]),
        })
        standard = pd.DataFrame({
            "wv": np.concatenate([broad_window[100:], narrow_window]),
        })

        overlap = app_module._spt_log_wavelength_overlap_percent(
            comparison,
            standard,
            [
                (1.0, float(np.exp(2.0))),
                (float(np.exp(3.0)), float(np.exp(4.0))),
            ],
        )

        self.assertAlmostEqual(overlap, 75.0, places=10)

    def test_t0_beta_window_mean_clears_default_threshold(self):
        comparison_ranges = [
            (0.860588, 1.345588),
            (1.44823, 1.79823),
            (2.01318, 2.39818),
        ]
        standard_ranges = [
            (1.015588, 1.345588),
            (1.46323, 1.79323),
            (2.01318, 2.38818),
        ]
        comparison = pd.DataFrame({
            "wv": np.concatenate([
                np.geomspace(start, stop, 101)
                for start, stop in comparison_ranges
            ]),
        })
        standard = pd.DataFrame({
            "wv": np.concatenate([
                np.geomspace(start, stop, 101)
                for start, stop in standard_ranges
            ]),
        })

        overlap = app_module._spt_log_wavelength_overlap_percent(
            comparison,
            standard,
            app_module.SPT_DEFAULT_NORM_REGIONS,
        )
        expected = np.mean([
            100.0 * np.log(standard_stop / standard_start)
            / np.log(comparison_stop / comparison_start)
            for (comparison_start, comparison_stop), (standard_start, standard_stop)
            in zip(comparison_ranges, standard_ranges, strict=True)
        ])

        self.assertAlmostEqual(overlap, expected, places=10)
        self.assertGreater(overlap, 80.0)

    def test_overlap_parser_defaults_and_clamps_to_percent_range(self):
        self.assertEqual(
            app_module._spt_min_log_wavelength_overlap_percent({}),
            80.0,
        )
        self.assertEqual(
            app_module._spt_min_log_wavelength_overlap_percent(
                {"min_overlap": "-5"}
            ),
            0.0,
        )
        self.assertEqual(
            app_module._spt_min_log_wavelength_overlap_percent(
                {},
                {"min_log_wavelength_overlap_percent": 120},
            ),
            100.0,
        )

    def test_mock_compare_excludes_template_below_requested_overlap(self):
        grid_payload = app_module._mock_spt_grid_payload(
            standards_source=app_module.SPT_STANDARDS_SOURCE_MOCA,
            only_field_objects=True,
        )
        template = grid_payload["gridData"][0]
        template_specid = int(template["moca_specid"])
        short_grid_payload = {
            **grid_payload,
            "gridData": [template],
            "gridSpectra": [
                row
                for row in grid_payload["gridSpectra"]
                if int(row["moca_specid"]) == template_specid
                and float(row["wv"]) <= 1.5
            ],
            "meta": {
                **grid_payload["meta"],
                "standard_count": 1,
                "spectrum_row_count": 1,
            },
        }

        with patch.object(
            app_module,
            "_mock_spt_grid_payload",
            return_value=short_grid_payload,
        ):
            excluded = self.client.post(
                "/api/spectral-typing/compare?mock=1",
                json={
                    "specid": 450,
                    "only_field": True,
                    "min_overlap": 80,
                },
            ).get_json()
            included = self.client.post(
                "/api/spectral-typing/compare?mock=1",
                json={
                    "specid": 450,
                    "only_field": True,
                    "min_overlap": 0,
                },
            ).get_json()

        self.assertTrue(excluded["ok"])
        self.assertEqual(excluded["meta"]["min_log_wavelength_overlap_percent"], 80.0)
        self.assertEqual(excluded["meta"]["chi2_standard_count"], 0)
        self.assertFalse(excluded["entries"][0]["chi2_eligible"])
        self.assertIsNone(excluded["entries"][0]["reduced_chi2"])
        self.assertLess(excluded["entries"][0]["log_wavelength_overlap_percent"], 80)

        self.assertTrue(included["ok"])
        self.assertEqual(included["meta"]["chi2_standard_count"], 1)
        self.assertTrue(included["entries"][0]["chi2_eligible"])
        self.assertIsNotNone(included["entries"][0]["reduced_chi2"])

    def test_page_exposes_and_persists_overlap_slider(self):
        html = (STATIC_DIR / "spectral_typing.html").read_text(encoding="utf-8")
        source = (STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")

        self.assertIn(
            'id="spt-min-overlap" type="range" min="0" max="100" value="80"',
            html,
        )
        self.assertIn("Minimum mean log-wavelength overlap", html)
        self.assertIn('params.set("min_overlap"', source)
        self.assertIn(
            "min_overlap: minimumLogWavelengthOverlapPercent()",
            source,
        )
        self.assertIn(
            'sptEl["spt-min-overlap"].addEventListener("change"',
            source,
        )


if __name__ == "__main__":
    unittest.main()
