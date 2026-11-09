import importlib.util
import math
import sys
import unittest


if sys.version_info < (3, 11) or importlib.util.find_spec("mosaic") is None:
    raise unittest.SkipTest("The local MOSAIC reviewer needs Python 3.11+ and MOSAIC's src on PYTHONPATH.")

try:
    from mocaviz.mosaic_review_fit import fit_target, selected_rows
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
