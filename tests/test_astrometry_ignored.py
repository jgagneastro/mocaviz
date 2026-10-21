import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from mocaviz import app as app_module
from test_astrometry_robust_fit import astrometry_fit_body, astrometry_row


class AstrometryIgnoredTests(unittest.TestCase):
    def test_ignored_rows_never_reach_either_sampler(self):
        active = [astrometry_row(i, 2010 + i, 7 * i, -3 * i) for i in range(6)]
        for mode in ("pm", "pm_plx"):
            for flag in (1, "1", True):
                with self.subTest(mode=mode, flag=flag):
                    body = astrometry_fit_body(active)
                    body["mode"] = mode
                    expected = app_module._astrometry_fit_arrays(body)
                    body["rows"] = active + [dict(astrometry_row("ignored", 2300, 1e9, -1e9), ignored=flag)]
                    actual = app_module._astrometry_fit_arrays(body)
                    for key in ("ids", "t", "dt", "y_ra", "y_dec", "s_ra", "s_dec", "pra", "pdec"):
                        np.testing.assert_array_equal(actual[key], expected[key])
                    self.assertEqual(actual["t0"], expected["t0"])

    def test_ignored_outlier_does_not_change_scipy_solution(self):
        rows = [astrometry_row(i, 2010 + i, 7 * i, -3 * i) for i in range(6)]
        body = astrometry_fit_body(rows, error_floor=False)
        body["outlierMixture"] = False
        expected = app_module._run_astrometry_fit(body, {})["fit"]
        body["rows"] = rows + [dict(astrometry_row("ignored", 2500, 1e10, -1e10), ignored=1)]
        actual = app_module._run_astrometry_fit(body, {})["fit"]
        self.assertEqual(actual["nRows"], len(rows))
        for key in ("pmra", "pmdec", "posRa", "posDec", "chi2"):
            self.assertAlmostEqual(actual[key], expected[key])

    def load_rows(self, rows):
        engine = MagicMock()
        statements = []

        def read_sql(conn, sql, params):
            if "JOIN moca_missions mm" in sql:
                statements.append(sql)
                return pd.DataFrame(rows)
            return pd.DataFrame()

        with patch.object(app_module, "_engine", return_value=engine), \
                patch.object(app_module, "_read_sql", side_effect=read_sql), \
                patch.object(app_module, "_db_table_exists", return_value=False), \
                patch.object(app_module, "_db_table_columns", return_value=set()), \
                patch.object(app_module, "_ASTROMETRY_OBJECT_CACHE", {}):
            payload = app_module._load_astrometry_object_from_db({}, 432)
        self.assertIn("deq.ignored", statements[0])
        self.assertNotIn("deq.ignored = 0", statements[0])
        return payload

    def test_loader_keeps_ignored_rows_but_uses_active_reference(self):
        rows = [
            dict(id=1, ignored=0, ra=120.0, dec=-30.0, measurement_epoch_yr=2015.0,
                 mission="Survey DR1", mission_name="Survey", data_release="DR1", moca_psid="J", airmass=1.234),
            dict(id=2, ignored=1, ra=200.0, dec=60.0, measurement_epoch_yr=2300.0, mission="Survey DR1"),
        ]
        payload = self.load_rows(rows)
        self.assertEqual(len(payload["rows"]), 2)
        self.assertEqual(payload["rows"][1]["ignored"], 1)
        self.assertEqual(payload["reference"]["id"], 1)
        for key in ("mission_name", "data_release", "moca_psid", "airmass"):
            self.assertEqual(payload["rows"][0][key], rows[0][key])

    def test_all_ignored_rows_are_not_a_fallback_reference(self):
        payload = self.load_rows([dict(id=1, ignored=1, ra=200.0, dec=60.0,
                                       measurement_epoch_yr=2300.0, mission="Survey")])
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["reference"], {})


if __name__ == "__main__":
    unittest.main()
