import unittest
from pathlib import Path
from unittest.mock import patch
from mocaviz import spherex_review as review
from mocaviz import spherex_native_fit as native

class NativeDispatchTests(unittest.TestCase):
    def test_only_explicit_native_metadata_selects_new_fitter(self):
        meta = {"moca_specpackid": 76, "data_reduction_pipeline": "SUBLIME3C native DR1 cube aperture extraction"}
        with patch.object(review, "native_fit_spectrum_rows", return_value="native") as new, patch.object(review, "fit_spectrum", return_value="legacy") as old:
            self.assertEqual(review.spectrum_fit(meta, [], [], {}), "native")
            self.assertEqual(review.spectrum_fit({"moca_specpackid": 76}, [], [], {}), "legacy")
            self.assertEqual(review.spectrum_fit({**meta, "moca_specpackid": 62}, [], [], {}), "legacy")
            self.assertEqual(new.call_count, 1)
            self.assertEqual(old.call_count, 2)
        self.assertNotEqual(review.data_fingerprint(meta, [], []), review.data_fingerprint({}, [], []))

    def test_shared_numeric_source_is_identical(self):
        other = Path(__file__).resolve().parents[2] / "sublime/sublime/native_spectral_fit.py"
        if not other.exists():
            self.skipTest("Sibling campaign checkout unavailable")
        self.assertEqual(other.read_bytes(), Path(native.__file__).read_bytes())

if __name__ == "__main__":
    unittest.main()
