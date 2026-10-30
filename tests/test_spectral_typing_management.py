import unittest
from unittest.mock import MagicMock, patch

from mocaviz import app as app_module


class SpectralTypingManagementTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.url = (
            "/api/spectral-typing/push-spectral-type"
            "?dbase=mocadb_private_tables&user=management&pwd=test-only"
        )
        self.body = {
            "moca_specid": 450,
            "spectral_standard_moca_specid": 9001,
            "moca_sptgridhid": 77,
            "spectral_type": "L5",
            "spectral_type_number": 15,
            "grid": "field",
        }

    def push(self, body, *, standard_type="L5", duplicate=None):
        engine = MagicMock()
        conn = engine.begin.return_value.__enter__.return_value
        comparison = MagicMock()
        comparison.mappings.return_value.all.return_value = [
            {"moca_specid": specid, "moca_oid": 602, "designation": "Target"}
            for specid in body.get("moca_specids", [450])
        ]
        standard = MagicMock()
        standard.mappings.return_value.first.return_value = {
            "moca_specid": 9001,
            "moca_sptgridhid": 77,
            "spectral_type": standard_type,
            "spectral_type_number": 15,
            "grid": "field",
            "designation": "Standard",
        }
        existing = MagicMock()
        existing.mappings.return_value.first.return_value = duplicate
        inserted = MagicMock(lastrowid=1234)
        conn.execute.side_effect = [comparison, standard, existing, inserted]
        columns = {
            "moca_oid", "moca_specid", "spectral_type", "spectral_type_number",
            "spectral_type_unc", "quality_flag", "moca_sptgridhid",
            "spectral_standard_moca_specid", "suffix", "simple_spectral_type",
            "complete_spectral_type", "comments", "is_public", "rls",
        }
        with (
            patch.object(app_module, "_engine", return_value=engine),
            patch.object(app_module, "_db_table_exists", side_effect=lambda conn, name: name == "data_spectral_types"),
            patch.object(app_module, "_db_table_columns", return_value=columns),
            patch.object(app_module, "_clear_spectral_type_write_caches", return_value={}),
        ):
            response = self.client.post(self.url, json=body)
        return response, conn

    def test_push_stores_suffix_and_appends_it_to_both_spectral_types(self):
        for specids in ([450], [450, 451]):
            with self.subTest(specids=specids):
                response, conn = self.push({
                    **self.body,
                    "moca_specids": specids,
                    "peculiarities": "  pec (red)  ",
                    "comments": "  Observer's note: weak CH4; check S/N.\nCompare J & K.  ",
                })
                self.assertEqual(response.status_code, 200, response.get_json())
                row = conn.execute.call_args.args[1]
                self.assertEqual(row["suffix"], "pec (red)")
                self.assertEqual(row["spectral_type"], "L5 pec (red)")
                self.assertEqual(row["complete_spectral_type"], "L5 pec (red)")
                self.assertEqual(row["simple_spectral_type"], "L5")
                self.assertEqual(row["spectral_type_number"], 15)
                self.assertIn("standard_moca_specid=9001", row["comments"])
                self.assertTrue(row["comments"].endswith(
                    "User comments: Observer's note: weak CH4; check S/N.\nCompare J & K."
                ))
                if len(specids) > 1:
                    self.assertIsNone(row["moca_specid"])
                    self.assertIn("combined_moca_specids=450,451", row["comments"])
                self.assertEqual(row["is_public"], 0)
                duplicate_params = conn.execute.call_args_list[2].args[1]
                self.assertEqual(duplicate_params["spectral_type"], "L5 pec (red)")

    def test_empty_optional_fields_preserve_existing_classification(self):
        for standard_type, expected_suffix in (("L5", None), ("sdL5", "sd")):
            for notes in ({}, {"peculiarities": "  ", "comments": "\n "}):
                with self.subTest(standard_type=standard_type, notes=notes):
                    response, conn = self.push(
                        {**self.body, "spectral_type": standard_type, **notes},
                        standard_type=standard_type,
                    )
                    self.assertEqual(response.status_code, 200, response.get_json())
                    row = conn.execute.call_args.args[1]
                    self.assertEqual(row.get("suffix"), expected_suffix)
                    self.assertEqual(row["spectral_type"], standard_type)
                    self.assertEqual(row["complete_spectral_type"], standard_type)
                    self.assertNotIn("User comments:", row["comments"])

    def test_overlong_peculiarities_are_rejected_before_connecting(self):
        with patch.object(app_module, "_engine") as engine:
            response = self.client.post(self.url, json={
                **self.body, "peculiarities": "x" * 21,
            })
        self.assertEqual(response.status_code, 400)
        self.assertIn("20 characters", response.get_json()["error"])
        engine.assert_not_called()

    def test_peculiarities_do_not_bypass_standard_validation(self):
        response, conn = self.push({
            **self.body, "spectral_type": "T5", "peculiarities": "pec (red)",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("does not match", response.get_json()["error"])
        self.assertEqual(conn.execute.call_count, 2)

    def test_matching_annotated_classification_is_still_rejected(self):
        response, conn = self.push(
            {**self.body, "peculiarities": "pec (red)"},
            duplicate={"id": 1234},
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.get_json()["duplicate"])
        self.assertEqual(conn.execute.call_count, 3)


if __name__ == "__main__":
    unittest.main()
