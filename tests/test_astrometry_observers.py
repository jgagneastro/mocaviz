import json
import unittest

import numpy as np

from mocaviz.astrometry_observers import (
    apply_observers,
    attach_observers,
    state_from_row,
)


def jwst_row(epoch=2024.0):
    state = {
        "body": "jwst",
        "origin": "ssb",
        "frame": "icrf",
        "epoch_mjd_utc": 51544.5 + (epoch - 2000) * 365.25,
        "position_au": [1.0, 0.0, 0.0],
        "velocity_au_per_day": [0.0, 0.017, 0.0],
    }
    return {
        "point_of_view": "jwst",
        "measurement_epoch_yr": epoch,
        "comments": json.dumps(
            {"observer": state, "independent_group": "JWST:visit:detector"}
        ),
    }


class ObserverTests(unittest.TestCase):
    def test_mixed_geometry_sign_and_derivative(self):
        row = jwst_row()
        zero = np.zeros(2)
        result = apply_observers(
            [{"point_of_view": "earth"}, row], 90.0, 0.0, zero, zero, zero, zero
        )
        np.testing.assert_allclose(result[0], [0, 1], atol=1e-12)
        self.assertAlmostEqual(result[1][1], 0.0)
        row = jwst_row()
        result = apply_observers(
            [row], 0.0, 0.0, np.zeros(1), np.zeros(1), np.zeros(1), np.zeros(1)
        )
        self.assertAlmostEqual(result[2][0], -0.017 * 365.25)

    def test_stale_missing_wrong_units_not_earth(self):
        for change in ("epoch", "missing", "units", "frame"):
            row = jwst_row()
            state = json.loads(row["comments"])["observer"]
            if change == "epoch":
                state["epoch_mjd_utc"] += 1
            if change == "units":
                state["position_au"] = [1.5e8, 0, 0]
            if change == "frame":
                state["frame"] = "ecliptic"
            row["observer"] = state
            if change == "missing":
                row.pop("observer")
                row["comments"] = "{}"
            with self.assertRaises(ValueError):
                state_from_row(row)

    def test_attach_and_missing_state_annotation(self):
        row = jwst_row()
        bad = {
            "point_of_view": "jwst",
            "measurement_epoch_yr": 2024.0,
            "comments": "{}",
        }
        result = attach_observers([row, bad])
        self.assertEqual(result[0]["observer"]["body"], "jwst")
        self.assertEqual(result[0]["independent_group"], "JWST:visit:detector")
        self.assertIsNone(result[1]["observer"])

    def test_backend_fit_includes_jwst_and_not_earth_factors(self):
        from mocaviz import app as app_module

        rows = []
        for i in range(3):
            row = jwst_row(2023.0 + i)
            row.update(
                id=i,
                single_epoch=1,
                pm_corrected=0,
                plx_corrected=0,
                base_rel_ra=float(i),
                base_rel_dec=float(i),
                ra_unc_mas=1.0,
                dec_unc_mas=1.0,
            )
            rows.append(row)
        arrays = app_module._astrometry_fit_arrays(
            {
                "mode": "pm_plx",
                "reference": {"ra": 90.0, "dec": 0.0, "epoch": 2024.0},
                "rows": rows,
            }
        )
        np.testing.assert_allclose(arrays["pra"], [1, 1, 1], atol=1e-12)
        self.assertEqual(len(arrays["ids"]), 3)


if __name__ == "__main__":
    unittest.main()
