"""Expanded managed-package routing uses synthetic rows, never a live database."""
import unittest
from unittest.mock import patch

from mocaviz import spectrum_compare as server


PACKAGES = {
    118: "nires_keck", 119: "nirspec_keck", 120: "osiris_soar",
    121: "arcoiris_ctio_blanco", 122: "tspec_soar", 123: "tspec_palomar",
    124: "triplespec_apo", 125: "niri_gemini_north", 126: "crires_vlt",
    127: "isaac_vlt", 128: "mosfire_keck", 129: "nirspec_jwst",
    130: "miri_jwst",
}


class ManagedPackageTests(unittest.TestCase):
    def test_new_packages_are_current_and_not_legacy_candidates(self):
        for package in PACKAGES:
            self.assertIn(package, server.MANAGED_PACKAGES)
            self.assertIn(package, server.EXCLUDED_LEGACY_PACKAGES)
            self.assertEqual(server.package_selection(str(package)), package)
        self.assertNotIn(110, server.EXCLUDED_LEGACY_PACKAGES)
        self.assertNotIn(115, server.EXCLUDED_LEGACY_PACKAGES)

    def test_menu_preserves_empty_packages_and_distinct_instrument_sites(self):
        database_rows = [
            {"moca_specpackid": package, "moca_instid": instrument,
             "instrument_name": "Shared instrument name",
             "active_spectra": 2 if package == 118 else 0}
            for package, instrument in PACKAGES.items()
        ]
        with patch.object(server, "readonly_rows", return_value=database_rows) as query:
            rows = server.package_rows()
        self.assertTrue(set(PACKAGES).issubset(query.call_args.args[1]))
        self.assertIn("LEFT JOIN", query.call_args.args[0])
        self.assertEqual(rows[0]["moca_specpackid"], "all")
        self.assertEqual(rows[0]["active_spectra"], 2)
        self.assertEqual([row["moca_specpackid"] for row in rows[1:]], list(PACKAGES))
        for row in rows[1:]:
            self.assertIn(row["moca_instid"], row["description"])
            if row["moca_specpackid"] != 118:
                self.assertIn("0 spectra", row["description"])

    def test_specific_and_all_camera_queries_include_new_packages(self):
        for selection in (*PACKAGES, None):
            with self.subTest(selection=selection):
                with patch.object(server, "readonly_rows", return_value=[]) as query:
                    self.assertEqual(server.spectrum_index(selection), [])
                parameters = query.call_args.args[1]
                self.assertEqual(parameters[:len(server.EXCLUDED_LEGACY_PACKAGES)],
                                 server.EXCLUDED_LEGACY_PACKAGES)
                selected = parameters[len(server.EXCLUDED_LEGACY_PACKAGES):]
                self.assertEqual(selected, server.MANAGED_PACKAGES if selection is None else (selection,))

    def test_new_package_spectrum_metadata_is_selectable(self):
        for package in PACKAGES:
            row = {"moca_specid": 42, "moca_specpackid": package}
            with patch.object(server, "readonly_rows", return_value=[row]) as query:
                self.assertEqual(server._spectrum_metadata(42)["moca_specpackid"], package)
            self.assertEqual(query.call_args.args[1][0], 42)
            self.assertIn(package, query.call_args.args[1][1:])


if __name__ == "__main__":
    unittest.main()
