import importlib.util
import math
import sys
import unittest


if sys.version_info < (3, 11) or importlib.util.find_spec("mosaic") is None:
    raise unittest.SkipTest("The local MOSAIC reviewer needs Python 3.11+ and MOSAIC's src on PYTHONPATH.")

try:
    from mocaviz.mosaic_review import comparison_point, literature_baseline
    from mocaviz.mosaic_review_fit import fit_target, input_choices, selected_rows
    from mosaic.prepare import parallax_motion
except ModuleNotFoundError as exc:
    if exc.name.startswith("mosaic."):
        raise unittest.SkipTest("Add the MOSAIC src directory to PYTHONPATH.") from exc
    raise


def synthetic_target():
    ra, dec, t0 = 120.0, -30.0, 2020.0
    scale = 3_600_000
    rows = []
    for i in range(34):
        year = t0 + i * .091
        second = i >= 17
        mission = "Second" if second else "First"
        factor_ra, factor_dec = parallax_motion(ra, dec, year)
        dra = 80 * (year - t0) + 39 * factor_ra + (38 if second else 0)
        ddec = -72 * (year - t0) + 39 * factor_dec - (17 if second else 0)
        rows.append(dict(
            id=i+1, mission=mission, mission_name=mission, ignored=0,
            measurement_epoch_yr=year, measurement_epoch_yr_unc=0.0,
            ra=ra + dra/(scale*math.cos(math.radians(dec))), dec=dec + ddec/scale,
            ra_unc_mas=1.0, dec_unc_mas=1.0, calibration_method="test",
            single_epoch=1, pm_corrected=0, plx_corrected=0, point_of_view="earth",
        ))
    return dict(target={"moca_oid":602}, reference={"ra":ra,"dec":dec,"measurement_epoch_yr":t0}, rows=rows)


class MosaicReviewFitTests(unittest.TestCase):
    def test_recovers_pm_parallax_and_both_mission_offsets(self):
        result = fit_target(synthetic_target(), offsets=True, calibrated=True)
        self.assertEqual(result["preferred"], "pm_plx")
        fit = result["fits"]["pm_plx"]
        self.assertAlmostEqual(fit["pmra"], 80, delta=.05)
        self.assertAlmostEqual(fit["pmdec"], -72, delta=.05)
        self.assertAlmostEqual(fit["plx"], 39, delta=.05)
        self.assertAlmostEqual(fit["surveyOffsets"]["values"]["Second"]["raMas"], 38, delta=.05)
        self.assertAlmostEqual(fit["surveyOffsets"]["values"]["Second"]["decMas"], -17, delta=.05)
        self.assertEqual(len(result["measurements"]), 34)
        self.assertEqual(len(fit["weights"]), 34)

    def test_weak_epoch_coverage_keeps_pm_without_parallax(self):
        target = synthetic_target()
        target["rows"] = target["rows"][:6]
        result = fit_target(target, offsets=True, calibrated=False)
        self.assertEqual(set(result["fits"]), {"pm"})
        self.assertIn("10 independent", result["parallaxReason"])
        self.assertEqual(result["fits"]["pm"]["surveyOffsets"]["values"], {})

    def test_invalid_and_duplicate_catalog_rows_are_excluded(self):
        payload = synthetic_target()
        rows = payload["rows"]
        rows += [
            dict(rows[0], id=200),
            dict(rows[1], id=201, ignored=1),
            dict(rows[2], id=202, mission="SMSS DR4", mission_name="SMSS", data_release="DR4", moca_psid="smss_gmag"),
            dict(rows[3], id=203, mission="VHS DR6", mission_name="VHS", data_release="DR6"),
        ]
        self.assertEqual([row["id"] for row in selected_rows(rows)], list(range(1,35)))


    def test_explicit_survey_and_band_selection_overrides_the_default_priority(self):
        base = synthetic_target()["rows"][0]
        untimely = dict(base, id=101, mission="WISE unTimely", mission_name="WISE",
                       data_release="unTimely", moca_psid="wise_w1mag")
        motion = dict(base, id=102, mission="WISE unWISEMotion W1", mission_name="WISE",
                      data_release="unWISEMotion W1", moca_psid="wise_w1mag")
        rows = [untimely, motion]
        choices = input_choices(rows, only_recalibrated=True)
        self.assertEqual({item["label"]:item["default"] for item in choices["missions"]},
                         {"WISE unTimely":False,"WISE unWISEMotion W1":True})
        self.assertEqual(list(selected_rows(rows)), [motion])
        self.assertEqual(list(selected_rows(rows, missions=["WISE unTimely"])), [untimely])
        self.assertEqual(list(selected_rows(rows, missions=["WISE unTimely"], bands=[["WISE unTimely","wise_w1mag"]])), [])

    def test_optional_unrecalibrated_rows_and_manual_exclusion_are_recorded(self):
        target = synthetic_target()
        target["rows"][0]["calibration_method"] = None
        default_fit = fit_target(target, offsets=True, calibrated=True)
        self.assertNotIn(1, [row["id"] for row in default_fit["measurements"]])
        selection = {"excluded":[2]}
        alternate = fit_target(target, offsets=True, calibrated=True, only_recalibrated=False, selection=selection)
        ids = [row["id"] for row in alternate["measurements"]]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)
        self.assertEqual(alternate["settings"]["selection"], selection)

    def test_propagates_fit_and_adopted_trajectory_errors(self):
        target = synthetic_target()
        target["reference"].update(ra_unc_mas=2, dec_unc_mas=3, plx_corrected=1)
        target["pm"] = {"pmra_masyr":80, "pmdec_masyr":-72, "pmra_masyr_unc":.9, "pmdec_masyr_unc":1.1}
        target["parallax"] = {"parallax_mas":39, "parallax_mas_unc":.4}
        result = fit_target(target, offsets=True, calibrated=True)
        self.assertAlmostEqual(result["fits"]["pm"]["baselineYears"], 33*.091)
        for fit in result["fits"].values():
            self.assertEqual(len(fit["curve"]["sigmaRa"]), len(fit["curve"]["year"]))
            self.assertTrue(all(value>0 for value in fit["curve"]["sigmaDec"]))
        adopted = result["adoptedTrajectory"]
        self.assertAlmostEqual(adopted["sigmaRa"][0], math.hypot(2,.4*parallax_motion(120,-30,2020)[0]), delta=.001)
        self.assertGreater(adopted["sigmaDec"][-1], adopted["sigmaDec"][0])

    def test_comparison_uses_reported_or_nominal_literature_span(self):
        self.assertEqual(literature_baseline({"epoch":2016.0}), (None,None))
        self.assertEqual(literature_baseline({"moca_pid":"gaiadr2"})[0],22/12)
        self.assertEqual(literature_baseline({"mission_name":"Gaia","data_release":"DR3"})[0],34/12)
        adopted = {"comments":"time baseline: 18 months","pmra_masyr":2,"pmdec_masyr":3,
                   "pmra_masyr_unc":3,"pmdec_masyr_unc":4}
        fit = {"pmra":3,"pmdec":1,"pmraUnc":.3,"pmdecUnc":.4,"baselineYears":11}
        point = comparison_point(11,fit,adopted)
        self.assertEqual((point["dx"],point["dy"],point["literatureBaseline"]),(1,-2,1.5))
        self.assertEqual((point["mosaicBaseline"],point["mosaicError"],point["literatureError"]),(11,.5,5))
