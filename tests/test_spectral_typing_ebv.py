import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "mocaviz" / "static"


class SpectralTypingEbvTests(unittest.TestCase):
    def test_extinction_annotation_displays_derived_color_excess(self):
        source = (STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")
        annotation = source.split("function metricAnnotation(entry, payload = null)", 1)[1].split(
            "function spectralRvIsFixed",
            1,
        )[0]

        self.assertIn("const colorExcess = spectralColorExcess(av, rv)", annotation)
        self.assertIn('fitLabel("E(B-V)", index)', annotation)
        self.assertIn("formatNumber(colorExcess, 2)", annotation)

    def test_color_excess_is_included_in_exported_best_parameters(self):
        source = (STATIC_DIR / "spectral_typing.js").read_text(encoding="utf-8")
        best_parameters = source.split("function spectralTypingBestParameters(entry)", 1)[1].split(
            "function spectralColorExcess",
            1,
        )[0]

        self.assertIn("spectralColorExcess(av, regionRv)", best_parameters)
        self.assertIn("E(B-V)_${index + 1}=${formatNumber(colorExcess, 4)}", best_parameters)

    def test_page_cache_busts_color_excess_display(self):
        html = (STATIC_DIR / "spectral_typing.html").read_text(encoding="utf-8")

        self.assertIn("ebv-20260723a", html)


if __name__ == "__main__":
    unittest.main()
