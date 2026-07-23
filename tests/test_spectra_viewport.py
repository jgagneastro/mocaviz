import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "mocaviz" / "static"


class SpectraViewportTests(unittest.TestCase):
    def test_plotly_ui_revision_preserves_zoom_across_display_option_renders(self):
        source = (STATIC_DIR / "spectra.js").read_text(encoding="utf-8")
        layout = source.split("function spectraLayout(processed, viewport = null)", 1)[1].split(
            "function spectraYAxisValues",
            1,
        )[0]

        self.assertIn("uirevision: spectraPlotUiRevision()", layout)
        self.assertIn("(speState.selected || [])", layout)
        self.assertIn('"spe-xrange-min", "spe-xrange-max"', layout)
        self.assertIn("applySpectraViewportToAxis(xaxis, viewport?.x)", layout)
        self.assertIn("applySpectraViewportToAxis(yaxis, viewport?.y", layout)
        self.assertIn("restoreSpectraViewportAfterRender(renderPromise, preservedViewport, renderToken)", source)
        self.assertIn("return Plotly.relayout(speEl[\"spe-plot\"], update)", source)

    def test_display_checkboxes_request_viewport_preservation(self):
        source = (STATIC_DIR / "spectra.js").read_text(encoding="utf-8")
        controls = source.split("function bindSpectraControls()", 1)[1].split(
            "function positionSpectraSearchPopup",
            1,
        )[0]

        self.assertIn("preserveViewport: true", controls)
        self.assertIn('["spe-snr", "spe-fnu", "spe-normalize"].includes(id)', controls)
        self.assertIn(
            'speEl["spe-hide-ignored"].addEventListener("change", () => loadSpectra({ preserveViewport: true }))',
            controls,
        )

    def test_spectra_page_cache_busts_the_viewport_fix(self):
        html = (STATIC_DIR / "spectra.html").read_text(encoding="utf-8")

        self.assertIn("preserve-zoom-20260723c", html)


if __name__ == "__main__":
    unittest.main()
