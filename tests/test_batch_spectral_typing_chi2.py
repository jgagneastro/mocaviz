from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mocaviz import app as app_module
from scripts import batch_spectral_typing_chi2 as batch


class FakeSpectralTypingApi:
    def __init__(self) -> None:
        self.search_calls: list[int] = []
        self.specid_search_calls: list[int] = []
        self.compare_calls: list[tuple[int, ...]] = []

    def search_spectra(self, moca_oid: int) -> list[dict[str, int]]:
        self.search_calls.append(moca_oid)
        if moca_oid == 602:
            return [
                {"moca_oid": 602, "moca_specid": 450},
                {"moca_oid": 602, "moca_specid": 451},
            ]
        return []

    def search_spectrum(self, moca_specid: int) -> list[dict[str, int]]:
        self.specid_search_calls.append(moca_specid)
        if moca_specid in {450, 451}:
            return [{"moca_oid": 602, "moca_specid": moca_specid}]
        return []

    def compare(self, specids, settings):
        selected = tuple(sorted(int(specid) for specid in specids))
        self.compare_calls.append(selected)
        return {
            "ok": True,
            "comparisonMetadata": {"moca_oid": 602},
            "entries": [
                {
                    "moca_specid": 800001,
                    "moca_oid": 700001,
                    "grid": "field",
                    "spectral_type": "L8",
                    "spectral_type_number": 18.0,
                    "reduced_chi2": 2.5,
                    "designation": "Standard A",
                    "bibcode": "2026Mock....1A",
                },
                {
                    "moca_specid": 800002,
                    "moca_oid": 700002,
                    "grid": "low gravity",
                    "spectral_type": "L9",
                    "spectral_type_number": 19.0,
                    "reduced_chi2": 3.5,
                    "designation": "Standard B",
                    "bibcode": "2026Mock....2B",
                },
            ],
            "meta": {
                "specid": selected[0] if len(selected) == 1 else None,
                "specids": list(selected),
                "summary_only": True,
            },
        }


class PublicFallbackApi:
    def __init__(self) -> None:
        self.search_calls: list[int] = []

    def search_spectra(self, moca_oid: int):
        self.search_calls.append(moca_oid)
        raise batch.ApiError(
            "Private database access was not confirmed.",
            error_code="private_database_not_confirmed",
        )


class BatchSpectralTypingChi2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app_module.app.test_client()

    def test_compare_summary_only_omits_spectral_arrays(self):
        summary = self.client.post(
            "/api/spectral-typing/compare?mock=1",
            json={"specid": 450, "bins": 200, "summary_only": True},
        ).get_json()
        full = self.client.post(
            "/api/spectral-typing/compare?mock=1",
            json={"specid": 450, "bins": 200},
        ).get_json()

        self.assertTrue(summary["ok"])
        self.assertTrue(summary["meta"]["summary_only"])
        self.assertEqual(summary["comparison"], [])
        self.assertTrue(summary["entries"])
        self.assertIn("reduced_chi2", summary["entries"][0])
        for field in app_module._SPT_CHI2_SUMMARY_ENTRY_EXCLUDED_FIELDS:
            self.assertNotIn(field, summary["entries"][0])

        self.assertTrue(full["comparison"])
        self.assertTrue(full["entries"][0]["spectrum"])
        self.assertNotIn("summary_only", full["meta"])

    def test_batch_credentials_are_accepted_from_headers(self):
        captured = {}

        def fake_search(args, query, selected_specid, **kwargs):
            captured.update(args)
            return {"options": [], "value": None, "meta": {"row_count": 0}}

        with patch.object(app_module, "_search_spt_spectra_from_db", side_effect=fake_search):
            response = self.client.get(
                "/api/spectral-typing/search?moca_oid=602",
                headers={
                    "X-MOCA-User": "collaborators",
                    "X-MOCA-Password": "secret",
                    "X-MOCA-Database": "mocadb_private_tables",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["user"], "collaborators")
        self.assertEqual(captured["pwd"], "secret")
        self.assertEqual(captured["dbase"], "mocadb_private_tables")

    def test_batch_credentials_partition_the_encoded_response_cache(self):
        path = "/api/spectral-typing/search?moca_oid=602"
        with app_module.app.test_request_context(
            path,
            headers={
                "X-MOCA-User": "collaborators",
                "X-MOCA-Password": "first",
                "X-MOCA-Database": "mocadb_private_tables",
            },
        ):
            first_key = app_module._encoded_response_cache_key()
        with app_module.app.test_request_context(
            path,
            headers={
                "X-MOCA-User": "collaborators",
                "X-MOCA-Password": "second",
                "X-MOCA-Database": "mocadb_private_tables",
            },
        ):
            second_key = app_module._encoded_response_cache_key()

        self.assertNotEqual(first_key, second_key)

    def test_api_client_keeps_credentials_out_of_request_url(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "ok": True,
                    "options": [],
                    "meta": {"private_db": True},
                }).encode("utf-8")

        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["timeout"] = timeout
            return FakeResponse()

        api = batch.SpectralTypingApi(
            "https://dataviz.mocadb.ca",
            user="collaborators",
            password="secret",
            dbase="mocadb_private_tables",
        )
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            api.search_spectra(602)

        self.assertNotIn("secret", captured["url"])
        self.assertNotIn("collaborators", captured["url"])
        self.assertEqual(captured["headers"]["X-moca-user"], "collaborators")
        self.assertEqual(captured["headers"]["X-moca-password"], "secret")
        self.assertEqual(captured["headers"]["X-moca-database"], "mocadb_private_tables")

    def test_api_client_rejects_public_or_unconfirmed_private_database_access(self):
        api = batch.SpectralTypingApi(
            "https://dataviz.mocadb.ca",
            user="collaborators",
            password="secret",
            dbase="mocadb_private_tables",
        )
        settings = {
            "bins": 200,
            "norm": batch.DEFAULT_NORM,
            "deredden": False,
            "cloud": False,
            "cloud_alpha": 1.7,
            "fit_cloud_alpha": False,
            "standards_source": "moca",
            "only_field": False,
            "fix_rv": None,
        }

        for meta in ({"private_db": False, "standard_count": 6}, {}):
            with self.subTest(meta=meta), patch.object(
                api,
                "_request",
                return_value={"ok": True, "entries": [], "meta": meta},
            ):
                with self.assertRaises(batch.ApiError) as raised:
                    api.compare([1195448], settings)
                self.assertEqual(
                    raised.exception.error_code,
                    "private_database_not_confirmed",
                )
                self.assertIn(
                    "Refusing to write incomplete public-grid results",
                    str(raised.exception),
                )

    def test_mock_api_client_does_not_require_private_database_confirmation(self):
        api = batch.SpectralTypingApi(
            "https://dataviz.mocadb.ca",
            dbase="mocadb_private_tables",
            mock=True,
        )
        settings = {
            "bins": 200,
            "norm": batch.DEFAULT_NORM,
            "deredden": False,
            "cloud": False,
            "cloud_alpha": 1.7,
            "fit_cloud_alpha": False,
            "standards_source": "moca",
            "only_field": False,
            "fix_rv": None,
        }
        payload = {"ok": True, "entries": [], "meta": {"private_db": False}}

        with patch.object(api, "_request", return_value=payload):
            self.assertIs(api.compare([451], settings), payload)

    def test_search_response_reports_effective_database_access(self):
        response = self.client.get(
            "/api/spectral-typing/search?mock=1&moca_oid=990602",
            headers={"X-MOCA-Database": "mocadb_private_tables"},
        ).get_json()

        self.assertTrue(response["ok"])
        self.assertTrue(response["meta"]["private_db"])

    def test_input_reader_accepts_header_and_oid_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oids.csv"
            path.write_text("moca_oid\n602\noid10995\n602\n", encoding="utf-8")
            self.assertEqual(batch.load_moca_oids(path, [700], ""), [700, 602, 10995])

    def test_specid_input_reader_accepts_csv_labels_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "specids.csv"
            path.write_text(
                "name,spec_id\nfirst,specid451\nsecond,450\nthird,451\n",
                encoding="utf-8",
            )

            self.assertEqual(
                batch.load_moca_specids(path, [452, 450], ""),
                [452, 450, 451],
            )
            path.write_text(
                "name,target_spectrum\nfirst,451\nsecond,450\n",
                encoding="utf-8",
            )
            self.assertEqual(
                batch.load_moca_specids(path, [], "target_spectrum"),
                [451, 450],
            )

    def test_policy_selection_is_explicit_and_deterministic(self):
        options = [
            {"moca_oid": 602, "moca_specid": 451},
            {"moca_oid": 602, "moca_specid": 450},
        ]
        all_tasks = batch.comparison_tasks(602, options, "all")
        first_task = batch.comparison_tasks(602, options, "first")
        composite_task = batch.comparison_tasks(602, options, "composite")

        self.assertEqual([task.specids for task in all_tasks], [(450,), (451,)])
        self.assertEqual(first_task[0].specids, (450,))
        self.assertEqual(composite_task[0].specids, (450, 451))

    def test_specific_comparison_task_selects_only_requested_specid(self):
        options = [
            {"moca_oid": 602, "moca_specid": 450},
            {"moca_oid": 602, "moca_specid": 451},
        ]

        task = batch.specific_comparison_task(451, options)

        self.assertEqual(task, batch.BatchTask(602, (451,), "specific"))
        self.assertIsNone(batch.specific_comparison_task(999, options))

    def test_specid_cli_types_only_the_explicit_spectrum(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "output"
            args = batch.parse_args([
                "--specid", "451",
                "--spec-id", "451",
                "--output-dir", str(output_dir),
                "--mock",
                "--pause", "0",
            ])
            api = FakeSpectralTypingApi()

            self.assertEqual(batch.run_batch(args, api=api), 0)
            self.assertEqual(api.search_calls, [])
            self.assertEqual(api.specid_search_calls, [451])
            self.assertEqual(api.compare_calls, [(451,)])

            with (output_dir / "combined_chi2.csv").open(
                newline="",
                encoding="utf-8",
            ) as handle:
                combined = list(csv.DictReader(handle))
            self.assertEqual(len(combined), 2)
            self.assertEqual(
                {row["comparison_specid"] for row in combined},
                {"451"},
            )
            self.assertEqual(
                {row["spectrum_policy"] for row in combined},
                {"specific"},
            )
            self.assertEqual(
                {row["requested_moca_oid"] for row in combined},
                {"602"},
            )

    def test_specid_csv_types_each_listed_spectrum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "specids.csv"
            output_dir = root / "output"
            input_path.write_text(
                "moca_specid\n451\n450\n451\n",
                encoding="utf-8",
            )
            args = batch.parse_args([
                "--specid-csv", str(input_path),
                "--output-dir", str(output_dir),
                "--mock",
                "--pause", "0",
            ])
            api = FakeSpectralTypingApi()

            self.assertEqual(batch.run_batch(args, api=api), 0)
            self.assertEqual(api.search_calls, [])
            self.assertEqual(api.specid_search_calls, [451, 450])
            self.assertEqual(api.compare_calls, [(451,), (450,)])

            with (output_dir / "combined_chi2.csv").open(
                newline="",
                encoding="utf-8",
            ) as handle:
                combined = list(csv.DictReader(handle))
            self.assertEqual(len(combined), 4)
            self.assertEqual(
                {row["comparison_specid"] for row in combined},
                {"450", "451"},
            )
            self.assertEqual(
                {row["spectrum_policy"] for row in combined},
                {"specific"},
            )

    def test_batch_writes_per_spectrum_combined_manifest_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "oids.csv"
            output_dir = root / "output"
            input_path.write_text("moca_oid\n602\n603\n", encoding="utf-8")
            args = batch.parse_args([
                str(input_path),
                "--output-dir", str(output_dir),
                "--mock",
                "--pause", "0",
                "--workers", "2",
            ])
            first_api = FakeSpectralTypingApi()

            self.assertEqual(batch.run_batch(args, api=first_api), 0)
            self.assertEqual(sorted(first_api.compare_calls), [(450,), (451,)])
            self.assertEqual(len(list((output_dir / "chi2").glob("*_chi2.csv"))), 2)

            with (output_dir / "combined_chi2.csv").open(newline="", encoding="utf-8") as handle:
                combined = list(csv.DictReader(handle))
            self.assertEqual(len(combined), 4)
            self.assertEqual({row["requested_moca_oid"] for row in combined}, {"602"})
            self.assertEqual({row["reduced_chi2"] for row in combined}, {"2.5", "3.5"})

            with (output_dir / "manifest.csv").open(newline="", encoding="utf-8") as handle:
                manifest = list(csv.DictReader(handle))
            self.assertEqual([row["status"] for row in manifest].count("success"), 2)
            self.assertEqual([row["status"] for row in manifest].count("no_spectra"), 1)

            resumed_api = FakeSpectralTypingApi()
            self.assertEqual(batch.run_batch(args, api=resumed_api), 0)
            self.assertEqual(resumed_api.compare_calls, [])

    def test_combined_only_avoids_individual_csvs_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "output"
            args = batch.parse_args([
                "--oid", "602",
                "--output-dir", str(output_dir),
                "--combined-only",
                "--mock",
                "--pause", "0",
                "--workers", "2",
            ])
            first_api = FakeSpectralTypingApi()

            self.assertTrue(args.combined_only)
            self.assertEqual(batch.run_batch(args, api=first_api), 0)
            self.assertEqual(sorted(first_api.compare_calls), [(450,), (451,)])
            self.assertFalse((output_dir / "chi2").exists())

            with (output_dir / "combined_chi2.csv").open(
                newline="",
                encoding="utf-8",
            ) as handle:
                combined = list(csv.DictReader(handle))
            self.assertEqual(len(combined), 4)

            with (output_dir / "manifest.csv").open(
                newline="",
                encoding="utf-8",
            ) as handle:
                manifest = list(csv.DictReader(handle))
            successful = [row for row in manifest if row["status"] == "success"]
            self.assertEqual(
                {row["output_csv"] for row in successful},
                {"combined_chi2.csv"},
            )

            resumed_api = FakeSpectralTypingApi()
            self.assertEqual(batch.run_batch(args, api=resumed_api), 0)
            self.assertEqual(resumed_api.compare_calls, [])

            (output_dir / "combined_chi2.csv").unlink()
            rebuilt_api = FakeSpectralTypingApi()
            self.assertEqual(batch.run_batch(args, api=rebuilt_api), 0)
            self.assertEqual(sorted(rebuilt_api.compare_calls), [(450,), (451,)])

    def test_batch_stops_after_first_unconfirmed_private_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "oids.csv"
            output_dir = root / "output"
            input_path.write_text("moca_oid\n602\n603\n", encoding="utf-8")
            args = batch.parse_args([
                str(input_path),
                "--output-dir", str(output_dir),
                "--mock",
            ])
            api = PublicFallbackApi()

            with self.assertRaisesRegex(SystemExit, "not confirmed"):
                batch.run_batch(args, api=api)

            self.assertEqual(api.search_calls, [602])
            self.assertEqual(list((output_dir / "chi2").glob("*_chi2.csv")), [])


if __name__ == "__main__":
    unittest.main()
