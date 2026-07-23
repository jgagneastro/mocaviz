import unittest

import numpy as np

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
        "measurement_epoch_yr_unc": 0.0,
        "single_epoch": 1,
        "pm_corrected": 0,
        "plx_corrected": 0,
        "point_of_view": "Earth",
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

    def test_uniform_volume_parallax_prior_transform(self):
        prior = app_module._astrometry_uniform_volume_parallax_prior(
            {
                "kind": "uniform_volume",
                "minDistancePc": 0.1,
                "maxDistancePc": 10_000.0,
            }
        )
        self.assertIsNotNone(prior)
        self.assertAlmostEqual(
            app_module._astrometry_uniform_volume_parallax_transform(0.0, prior),
            10_000.0,
        )
        self.assertAlmostEqual(
            app_module._astrometry_uniform_volume_parallax_transform(1.0, prior),
            0.1,
        )
        median_parallax = app_module._astrometry_uniform_volume_parallax_transform(
            0.5,
            prior,
        )
        median_distance = 1000.0 / median_parallax
        expected_median_distance = (
            0.5 * (0.1**3 + 10_000.0**3)
        ) ** (1.0 / 3.0)
        self.assertAlmostEqual(median_distance, expected_median_distance)

    def test_uniform_volume_prior_requires_finite_increasing_distance_bounds(self):
        with self.assertRaisesRegex(ValueError, "maxDistancePc"):
            app_module._astrometry_uniform_volume_parallax_prior(
                {
                    "kind": "uniform_volume",
                    "minDistancePc": 10.0,
                    "maxDistancePc": 10.0,
                }
            )

    def test_parallax_bounds_reuse_the_null_model_bounds(self):
        body = astrometry_fit_body(
            [
                astrometry_row(f"row-{index}", 2010.0 + index, index, -index)
                for index in range(6)
            ]
        )
        body["mode"] = "pm_plx"
        arrays = app_module._astrometry_fit_arrays(body)
        prior = app_module._astrometry_uniform_volume_parallax_prior(
            {
                "kind": "uniform_volume",
                "minDistancePc": 0.1,
                "maxDistancePc": 10_000.0,
            }
        )
        common = [(-1.0, 1.0), (-2.0, 2.0), (-3.0, 3.0), (-4.0, 4.0)]
        bounds = app_module._astrometry_ultranest_bounds(
            arrays,
            [0.0, 0.0, 0.0, 0.0, 1.0],
            common_bounds=common,
            parallax_prior=prior,
        )
        self.assertEqual(bounds[:4], common)
        self.assertEqual(bounds[4], (0.1, 10_000.0))

    def test_stationary_evidence_is_marginalized_with_model_prior(self):
        logz, uncertainty = app_module._astrometry_marginal_log_evidence(
            [-10.0, -10.0],
            [0.9, 0.1],
            [0.2, 0.2],
        )
        self.assertAlmostEqual(logz, -10.0)
        self.assertAlmostEqual(
            uncertainty,
            ((0.9 * 0.2) ** 2 + (0.1 * 0.2) ** 2) ** 0.5,
        )

    def test_ra_star_parallax_factor_has_no_second_cosine_declination(self):
        equator, _ = app_module._astrometry_parallax_factors(
            120.0,
            0.0,
            np.array([2015.5]),
        )
        high_dec, _ = app_module._astrometry_parallax_factors(
            120.0,
            75.0,
            np.array([2015.5]),
        )
        self.assertAlmostEqual(float(equator[0]), float(high_dec[0]))

    def test_fit_rejects_ineligible_coordinate_semantics(self):
        good = astrometry_row("good", 2010.0, 0.0, 0.0)
        rows = [
            good,
            {**astrometry_row("merged", 2011.0, 1.0, 1.0), "single_epoch": 0},
            {**astrometry_row("pm", 2012.0, 2.0, 2.0), "pm_corrected": 1},
            {**astrometry_row("plx", 2013.0, 3.0, 3.0), "plx_corrected": 1},
            {**astrometry_row("space", 2014.0, 4.0, 4.0), "point_of_view": "Gaia"},
            astrometry_row("good-2", 2015.0, 5.0, 5.0),
        ]
        body = astrometry_fit_body(rows, error_floor=False)
        body["outlierMixture"] = False
        arrays = app_module._astrometry_fit_arrays(body)
        self.assertEqual(list(arrays["ids"]), ["good", "good-2"])

    def test_epoch_uncertainty_is_propagated_along_motion(self):
        rows = []
        for index, epoch in enumerate(range(2010, 2021)):
            row = astrometry_row(
                f"row-{index}",
                epoch,
                100.0 * (epoch - 2015.0),
                0.0,
                uncertainty=1.0,
            )
            row["measurement_epoch_yr_unc"] = 0.1
            rows.append(row)
        body = astrometry_fit_body(rows, error_floor=False)
        body["outlierMixture"] = False
        fit = app_module._run_astrometry_fit(body, {})["fit"]
        self.assertAlmostEqual(fit["pmra"], 100.0, places=6)
        responsibility = fit["responsibilities"][0]
        self.assertGreater(responsibility["effectiveRaUncertaintyMas"], 10.0)
        self.assertAlmostEqual(
            responsibility["effectiveDecUncertaintyMas"],
            1.0,
            places=6,
        )

    def test_same_group_duplicates_do_not_add_information(self):
        single_rows = []
        duplicate_rows = []
        for index, epoch in enumerate(range(2010, 2016)):
            row = astrometry_row(
                f"row-{index}",
                epoch,
                2.0 * (epoch - 2012.5),
                -3.0 * (epoch - 2012.5),
                uncertainty=1.0,
            )
            row["independent_group"] = f"group-{index}"
            single_rows.append(row)
            for duplicate in range(4):
                duplicate_rows.append(
                    {
                        **row,
                        "id": f"row-{index}-{duplicate}",
                    }
                )
        single_body = astrometry_fit_body(single_rows, error_floor=False)
        duplicate_body = astrometry_fit_body(duplicate_rows, error_floor=False)
        single_body["outlierMixture"] = False
        duplicate_body["outlierMixture"] = False
        single_fit = app_module._run_astrometry_fit(single_body, {})["fit"]
        duplicate_fit = app_module._run_astrometry_fit(duplicate_body, {})["fit"]
        self.assertEqual(duplicate_fit["nIndependentGroups"], 6)
        self.assertAlmostEqual(
            single_fit["pmraUnc"],
            duplicate_fit["pmraUnc"],
            places=8,
        )

    def test_fixed_object_floor_and_parameter_covariance_are_reported(self):
        rows = [
            astrometry_row(
                f"row-{index}",
                2010.0 + index,
                float(index),
                -float(index),
                uncertainty=1.0,
            )
            for index in range(6)
        ]
        body = astrometry_fit_body(rows, error_floor=False)
        body["outlierMixture"] = False
        body["objectErrorFloor"] = {
            "raMas": 3.0,
            "decMas": 4.0,
            "source": "object-floor-test",
        }
        fit = app_module._run_astrometry_fit(body, {})["fit"]
        self.assertEqual(fit["objectErrorFloorRa"], 3.0)
        self.assertEqual(fit["objectErrorFloorDec"], 4.0)
        self.assertEqual(fit["objectErrorFloorSource"], "object-floor-test")
        self.assertEqual(
            np.asarray(fit["parameterCovariance"]).shape,
            (4, 4),
        )
        self.assertAlmostEqual(
            fit["responsibilities"][0]["effectiveRaUncertaintyMas"],
            np.hypot(1.0, 3.0),
        )

    def test_parallax_uncertainty_becomes_shared_gaussian_constraint(self):
        rows = [
            astrometry_row(
                f"row-{index}",
                2010.0 + index,
                float(index),
                -float(index),
                uncertainty=10.0,
            )
            for index in range(6)
        ]
        body = astrometry_fit_body(rows, error_floor=False)
        body["outlierMixture"] = False
        body["parallax"] = {"value": 25.0, "uncertainty": 2.0}
        fit = app_module._run_astrometry_fit(body, {})["fit"]
        self.assertIsNotNone(fit["plx"])
        self.assertIsNotNone(fit["plxUnc"])
        self.assertEqual(fit["parallaxPrior"]["kind"], "gaussian")
        self.assertEqual(len(fit["parameterNames"]), 5)
        self.assertEqual(
            np.asarray(fit["parameterCovariance"]).shape,
            (5, 5),
        )


if __name__ == "__main__":
    unittest.main()
