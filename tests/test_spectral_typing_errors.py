import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from mocaviz import app as app_module


class SpectralTypingErrorTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_loader_distinguishes_missing_specid_from_empty_spectrum(self):
        engine = MagicMock()
        engine.connect.return_value.__enter__.return_value = MagicMock()
        empty = pd.DataFrame()

        with (
            patch.object(app_module, "_engine", return_value=engine),
            patch.object(app_module, "_spectra_resolution_metadata_select", return_value="NULL AS median_spectral_resolving_power"),
            patch.object(app_module, "_read_sql", side_effect=[empty, empty]),
        ):
            with self.assertRaises(app_module._SptSpectrumDataError) as caught:
                app_module._load_spt_spectrum_from_db({}, 991001)

        self.assertEqual(caught.exception.error_code, "specid_not_found")
        self.assertEqual(str(caught.exception), "Specid 991001 does not exist.")

        metadata = pd.DataFrame([{"moca_specid": 991002, "spectrum_ignored": 1}])
        with (
            patch.object(app_module, "_engine", return_value=engine),
            patch.object(app_module, "_spectra_resolution_metadata_select", return_value="NULL AS median_spectral_resolving_power"),
            patch.object(app_module, "_read_sql", side_effect=[metadata, empty]),
        ):
            with self.assertRaises(app_module._SptSpectrumDataError) as caught:
                app_module._load_spt_spectrum_from_db({}, 991002)

        self.assertEqual(caught.exception.error_code, "specid_no_valid_data")
        self.assertEqual(str(caught.exception), "Specid 991002 contains no valid data.")

    def test_range_validation_distinguishes_invalid_and_outside_data(self):
        invalid_payload = {
            "metadata": {"moca_specid": 991003},
            "spectrum": [{"moca_specid": 991003, "wv": 0.7, "sp": None}],
        }
        with self.assertRaises(app_module._SptSpectrumDataError) as caught:
            app_module._spt_validate_spectrum_payload_for_regions(
                invalid_payload,
                [(0.52, 0.9)],
            )
        self.assertEqual(caught.exception.error_code, "specid_no_valid_data")

        outside_payload = {
            "metadata": {"moca_specid": 991004},
            "spectrum": [
                {"moca_specid": 991004, "wv": 1.05, "sp": 0.9},
                {"moca_specid": 991004, "wv": 1.10, "sp": 1.0},
            ],
        }
        with self.assertRaises(app_module._SptSpectrumDataError) as caught:
            app_module._spt_validate_spectrum_payload_for_regions(
                outside_payload,
                [(0.52, 0.9)],
            )
        self.assertEqual(
            caught.exception.error_code,
            "specid_no_data_in_wavelength_range",
        )
        self.assertEqual(
            str(caught.exception),
            "Specid 991004 contains valid data only outside the wavelength range 0.520-0.900 μm.",
        )

        valid_payload = {
            "metadata": {"moca_specid": 991005},
            "spectrum": [{"moca_specid": 991005, "wv": 0.75, "sp": 1.0}],
        }
        app_module._spt_validate_spectrum_payload_for_regions(
            valid_payload,
            [(0.52, 0.9)],
        )

    def test_compare_api_returns_structured_spectrum_errors(self):
        cases = (
            ("specid_not_found", 404, "Specid 991006 does not exist."),
            ("specid_no_valid_data", 422, "Specid 991006 contains no valid data."),
            (
                "specid_no_data_in_wavelength_range",
                422,
                "Specid 991006 contains valid data only outside the wavelength range 0.520-0.900 μm.",
            ),
        )
        for error_code, status, message in cases:
            regions = [(0.52, 0.9)] if error_code.endswith("wavelength_range") else None
            error = app_module._SptSpectrumDataError(
                error_code,
                991006,
                regions,
            )
            with self.subTest(error_code=error_code), patch.object(
                app_module,
                "_precompute_spt_comparison",
                side_effect=error,
            ):
                response = self.client.post(
                    "/api/spectral-typing/compare",
                    json={"specid": 991006, "norm": "0.520-0.900"},
                )

            payload = response.get_json()
            self.assertEqual(response.status_code, status)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_code"], error_code)
            self.assertEqual(payload["error"], message)
            self.assertEqual(payload["error_details"]["moca_specid"], 991006)


if __name__ == "__main__":
    unittest.main()
