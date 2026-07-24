import unittest
from pathlib import Path

import numpy as np

from mocaviz import app as app_module


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "mocaviz" / "static"


class SpectralTypingExtinctionTests(unittest.TestCase):
    def test_cardelli_optical_branch_matches_ccm89_polynomial(self):
        wavelengths = np.array([0.55, 0.70, 0.90])

        a_coeff, b_coeff = app_module._spt_cardelli_ab(wavelengths)

        np.testing.assert_allclose(
            a_coeff,
            [0.9996765324843310, 0.8683706682637410, 0.6800919442290243],
            rtol=0.0,
            atol=1e-12,
        )
        np.testing.assert_allclose(
            b_coeff,
            [-0.0025622410495426, -0.3664115589512073, -0.6239816760697836],
            rtol=0.0,
            atol=1e-12,
        )

    def test_cardelli_near_ir_branch_is_preserved(self):
        wavelength = np.array([1.25])
        x = 1.0 / wavelength

        a_coeff, b_coeff = app_module._spt_cardelli_ab(wavelength)

        np.testing.assert_allclose(a_coeff, 0.574 * x**1.61)
        np.testing.assert_allclose(b_coeff, -0.527 * x**1.61)

    def test_red_optical_label_preserves_existing_preset_value(self):
        html = (STATIC_DIR / "spectral_typing.html").read_text(encoding="utf-8")
        source = (STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")

        self.assertIn('<option value="red-visible">Red-optical</option>', html)
        self.assertIn('value: "red-visible", label: "Red-optical"', source)
        self.assertNotIn(">Red-visible</option>", html)
        self.assertNotIn('label: "Red-visible"', source)


if __name__ == "__main__":
    unittest.main()
