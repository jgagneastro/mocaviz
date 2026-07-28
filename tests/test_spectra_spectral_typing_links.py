import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "mocaviz" / "static"


class SpectraSpectralTypingLinkTests(unittest.TestCase):
    def test_table_rows_link_to_spectral_typing_with_auth_context(self):
        source = (STATIC_DIR / "spectra.js").read_text(encoding="utf-8")
        helper = source.split("function spectralTypingLinkHtml(specid)", 1)[1].split(
            "function renderSpectraTable",
            1,
        )[0]

        self.assertIn("const params = apiParams()", helper)
        self.assertIn('params.set("specid", String(parsedSpecid))', helper)
        self.assertIn('speAppUrl(`spectral-typing?${params.toString()}`)', helper)
        self.assertIn("target=\"_blank\"", helper)
        self.assertIn("rel=\"noopener noreferrer\"", helper)
        self.assertIn(">Spectral type</a>", helper)

        table_renderer = source.split("function renderSpectraTable()", 1)[1].split(
            "function spectraColorForSpecid",
            1,
        )[0]
        self.assertEqual(table_renderer.count("typing: spectralTypingLinkHtml("), 2)
        self.assertEqual(table_renderer.count('"typing"'), 4)

    def test_spectra_page_cache_busts_spectral_typing_link(self):
        html = (STATIC_DIR / "spectra.html").read_text(encoding="utf-8")

        self.assertIn("spectral-typing-link-20260728a", html)


if __name__ == "__main__":
    unittest.main()
