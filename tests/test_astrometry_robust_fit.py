import unittest

from mocaviz import app as app_module


def astrometry_fit_body(rows, *, error_floor=True):
    return {
        "mode": "pm",
        "fitter": "scipy",
        "outlierMixture": True,
        "errorFloor": error_floor,
        "reference": {"ra": 120.0, "dec": -30.0, "epoch": 2015.0},
        "fixedPlx": 0.0,
        "rows": rows,
    }


def astrometry_row(row_id, epoch, ra, dec, uncertainty=0.4):
    return {
        "id": row_id,
        "mission": "Synthetic",
        "plot_epoch_abs": epoch,
        "base_rel_ra": ra,
        "base_rel_dec": dec,
        "ra_unc_mas": uncertainty,
        "dec_unc_mas": uncertainty,
    }


class AstrometryRobustFitTests(unittest.TestCase):
    def run_fit(self, rows):
        return app_module._run_astrometry_fit(astrometry_fit_body(rows), {})["fit"]

    def test_slow_mover_does_not_activate_stationary_source_model(self):
        residuals = [0.05, -0.08, 0.02, 0.09, -0.04, -0.02, 0.06, -0.07, 0.03, -0.01, 0.04]
        rows = []
        for index, epoch in enumerate(range(2010, 2021)):
            dt = epoch - 2015.0
            noise = residuals[index]
            rows.append(astrometry_row(
                f"slow-{index}",
                epoch,
                10.0 + 0.05 * dt + noise,
                -5.0 - 0.03 * dt - 0.5 * noise,
            ))

        fit = self.run_fit(rows)

        self.assertFalse(fit["stationaryModelActive"])
        self.assertEqual(fit["nStationarySources"], 0)
        self.assertEqual(fit["nOutliers"], 0)
        self.assertLess(fit["stationarySeparation"], app_module.ASTROMETRY_STATIONARY_MIN_SEPARATION)
        self.assertAlmostEqual(fit["pmra"], 0.05, delta=0.05)
        self.assertAlmostEqual(fit["pmdec"], -0.03, delta=0.05)

    def test_repeated_distinct_stationary_locus_is_selected(self):
        rows = []
        for index, epoch in enumerate(range(2010, 2021)):
            dt = epoch - 2015.0
            jitter = (index % 3 - 1) * 0.08
            rows.append(astrometry_row(
                f"moving-{index}",
                epoch,
                5.0 + 18.0 * dt + jitter,
                -3.0 - 11.0 * dt - 0.5 * jitter,
            ))
        for index, (epoch, jitter) in enumerate(((2011.5, -0.08), (2015.5, 0.04), (2019.5, 0.07))):
            rows.append(astrometry_row(
                f"stationary-{index}",
                epoch,
                42.0 + jitter,
                27.0 - 0.5 * jitter,
            ))

        fit = self.run_fit(rows)

        self.assertTrue(fit["stationaryModelActive"])
        self.assertEqual(set(fit["stationarySourceIds"]), {"stationary-0", "stationary-1", "stationary-2"})
        self.assertAlmostEqual(fit["pmra"], 18.0, delta=0.2)
        self.assertAlmostEqual(fit["pmdec"], -11.0, delta=0.2)
        self.assertGreaterEqual(fit["stationarySeparation"], app_module.ASTROMETRY_STATIONARY_MIN_SEPARATION)

    def test_single_gross_failure_is_not_promoted_to_stationary_source(self):
        rows = []
        for index, epoch in enumerate(range(2010, 2021)):
            dt = epoch - 2015.0
            rows.append(astrometry_row(
                f"moving-{index}",
                epoch,
                -2.0 + 7.0 * dt,
                4.0 - 3.0 * dt,
            ))
        rows.append(astrometry_row("failure", 2016.25, 320.0, -280.0))

        fit = self.run_fit(rows)

        self.assertFalse(fit["stationaryModelActive"])
        self.assertEqual(fit["nStationarySources"], 0)
        self.assertIn("failure", fit["measurementFailureIds"])
        self.assertAlmostEqual(fit["pmra"], 7.0, delta=0.15)
        self.assertAlmostEqual(fit["pmdec"], -3.0, delta=0.15)

    def test_page_distinguishes_failure_and_stationary_classifications(self):
        script = (app_module.STATIC_DIR / "astrometry.js").read_text(encoding="utf-8")
        html = (app_module.STATIC_DIR / "astrometry.html").read_text(encoding="utf-8")

        self.assertIn('component: "measurement_failure"', script)
        self.assertIn('component: "stationary_source"', script)
        self.assertIn("measurementFailureProbability", script)
        self.assertIn("stationaryProbability", script)
        self.assertIn("stationaryModelActive", script)
        self.assertIn("Robust measurement failures and stationary-source contaminants", html)


if __name__ == "__main__":
    unittest.main()
