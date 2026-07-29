from __future__ import annotations

import unittest

import mocaviz.app as app_module


class BdErrorThresholdTests(unittest.TestCase):
    def test_threshold_inputs_wait_for_blur_and_debounce_rendering(self):
        script = (app_module.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        handler_block = script.split('for (const id of ["xerr-max", "yerr-max"]) {', 1)[1].split(
            'for (const id of ["show-errors", "include-binaries"])',
            1,
        )[0]
        scheduler_block = script.split("function scheduleErrorThresholdRender()", 1)[1].split(
            "function scheduleBootstrapReload",
            1,
        )[0]

        self.assertIn("const errorThresholdRenderDelayMs = 500;", script)
        self.assertIn("errorThresholdRenderTimer: null", script)
        self.assertIn('el[id].addEventListener("input"', handler_block)
        self.assertIn("cancelScheduledErrorThresholdRender();", handler_block)
        self.assertIn('el[id].addEventListener("blur"', handler_block)
        self.assertIn("scheduleErrorThresholdRender();", handler_block)
        self.assertIn('if (event.key === "Enter") el[id].blur();', handler_block)
        self.assertNotIn("render();", handler_block)
        self.assertIn("window.setTimeout(() => {", scheduler_block)
        self.assertIn("if (activeElement === el[\"xerr-max\"]", scheduler_block)
        self.assertIn("requestInitialAxisRange();", scheduler_block)
        self.assertIn("render();", scheduler_block)
        self.assertIn("}, errorThresholdRenderDelayMs);", scheduler_block)


if __name__ == "__main__":
    unittest.main()
