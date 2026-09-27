"""Launcher and comparison smoke tests runnable in the local Python 3.8 env."""

import unittest
from unittest import mock


class LauncherCompatibilityTests(unittest.TestCase):
    def test_local_launcher_imports_and_serves_pages_without_a_database(self):
        with mock.patch("pymysql.connect", side_effect=AssertionError("Unexpected DB connection")):
            from bd_colors_fast.app import app

            with app.test_client() as client:
                for route in ("/js", "/spectrum-compare", "/js/spectrum-compare"):
                    with self.subTest(route=route):
                        response = client.get(route)
                        self.assertEqual(response.status_code, 200)
                        response.close()

    def test_normalization_and_payload_work_on_the_launcher_python(self):
        from mocaviz import spectrum_compare as server

        current = {"moca_specid": 1}
        legacy = {"moca_specid": 2}
        samples = {
            1: ([(1.0, 2.0), (2.0, 4.0), (3.0, 6.0)], [], []),
            2: ([(1.0, 4.0), (2.0, 8.0), (3.0, 12.0)], [], []),
        }
        with mock.patch.object(server, "_spectrum_metadata", return_value=current):
            with mock.patch.object(server, "_legacy_metadata", return_value=[legacy]):
                with mock.patch.object(server, "_spectral_samples_for_specids_by_quality", return_value=samples):
                    payload = server.spectrum_payload(1)
                    self.assertEqual(len(payload["traces"]), 2)
                    self.assertAlmostEqual(
                        payload["traces"][1]["normalization_scale"]
                        / payload["traces"][0]["normalization_scale"],
                        2.0,
                    )
                    for scales, details in (([], []), ([1.0, 2.0], []), ([1.0], [{}, {}])):
                        with self.subTest(scales=scales, details=details):
                            with mock.patch.object(server, "reference_normalization_details", return_value=(scales, details)):
                                with self.assertRaisesRegex(ValueError, "mismatched lengths"):
                                    server.spectrum_payload(1)


if __name__ == "__main__":
    unittest.main()
