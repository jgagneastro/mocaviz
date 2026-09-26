from __future__ import annotations

import gzip
import json
import unittest
from datetime import datetime
from unittest import mock

from mocaviz import spectrum_compare as server


class DownsampleTest(unittest.TestCase):
    def test_package_rows_prepend_all_cameras_with_combined_count(self) -> None:
        database_rows = [
            {
                "moca_specpackid": 106,
                "moca_instid": "gnirs_gemini_north",
                "instrument_name": "GNIRS",
                "package_name": "GNIRS reductions",
                "active_spectra": 3,
            },
            {
                "moca_specpackid": 109,
                "moca_instid": "fire_magellan",
                "instrument_name": "FIRE",
                "package_name": "FIRE reductions",
                "active_spectra": 7,
            },
        ]
        with mock.patch.object(server, "readonly_rows", return_value=database_rows):
            rows = server.package_rows()

        self.assertEqual(rows[0]["moca_specpackid"], "all")
        self.assertEqual(rows[0]["active_spectra"], 10)
        self.assertEqual(rows[0]["description"], "All Cameras — 10 spectra")
        self.assertEqual([row["moca_specpackid"] for row in rows[1:]], [106, 109])

    def test_all_cameras_index_uses_every_managed_package(self) -> None:
        with mock.patch.object(server, "readonly_rows", return_value=[]) as query:
            self.assertEqual(server.spectrum_index(None), [])

        sql, parameters = query.call_args.args
        self.assertIn("s.moca_specpackid IN", sql)
        self.assertIn("s.moca_specpackid", sql)
        self.assertEqual(parameters[-len(server.MANAGED_PACKAGES) :], server.MANAGED_PACKAGES)

    def test_all_cameras_dropdown_value_is_parsed_without_coercing_to_nan(self) -> None:
        self.assertIsNone(server.package_selection("all"))
        self.assertEqual(server.package_selection("109"), 109)

    def test_package_roles_keep_managed_reductions_current_and_archives_legacy(
        self,
    ) -> None:
        self.assertIn(113, server.MANAGED_PACKAGES)
        self.assertNotIn(110, server.MANAGED_PACKAGES)
        self.assertEqual(server.IGRINS_ARCHIVE_LEGACY_PACKAGE, 110)
        self.assertNotIn(
            server.IGRINS_ARCHIVE_LEGACY_PACKAGE,
            server.EXCLUDED_LEGACY_PACKAGES,
        )
        self.assertIn(114, server.MANAGED_PACKAGES)
        self.assertNotIn(112, server.MANAGED_PACKAGES)
        self.assertEqual(server.ESO_ARCHIVE_LEGACY_PACKAGE, 115)
        self.assertNotIn(
            server.ESO_ARCHIVE_LEGACY_PACKAGE,
            server.EXCLUDED_LEGACY_PACKAGES,
        )
        self.assertEqual(
            server.EXCLUDED_LEGACY_PACKAGES,
            server.MANAGED_PACKAGES,
        )

    def test_short_series_is_unchanged(self) -> None:
        samples = [(1.0, 2.0), (2.0, 3.0)]
        self.assertIs(server.minmax_downsample(samples, 10), samples)

    def test_normalization_uses_only_the_shared_wavelength_range(self) -> None:
        short = [(5.0, 2.0), (6.0, 2.0), (7.0, 2.0), (8.0, 2.0)]
        long = [
            (1.0, 100.0),
            (2.0, 100.0),
            (3.0, 100.0),
            (4.0, 100.0),
            (5.0, 4.0),
            (6.0, 4.0),
            (7.0, 4.0),
            (8.0, 4.0),
            (9.0, 4.0),
        ]

        shared_range, scales = server.shared_normalization([short, long])

        self.assertEqual(shared_range, [5.0, 8.0])
        self.assertEqual(scales, [2.0, 4.0])

    def test_normalization_falls_back_per_trace_without_overlap(self) -> None:
        shared_range, scales = server.shared_normalization(
            [[(1.0, 2.0), (2.0, 4.0)], [(3.0, 10.0), (4.0, 20.0)]]
        )

        self.assertIsNone(shared_range)
        self.assertEqual(scales, [3.0, 15.0])

    def test_normalization_equally_weights_only_jointly_populated_windows(
        self,
    ) -> None:
        first = [
            (1.0, 2.0),
            (1.1, 2.0),
            (1.2, 2.0),
            (1.3, 2.0),
            (1.4, 2.0),
            (1.5, 2.0),
            (8.9, 20.0),
            (9.0, 20.0),
        ]
        second = [
            (1.0, 4.0),
            (1.1, 4.0),
            (8.5, 40.0),
            (8.6, 40.0),
            (8.7, 40.0),
            (8.8, 40.0),
            (8.9, 40.0),
            (9.0, 40.0),
        ]

        shared_range, scales, windows = server.shared_normalization_details(
            [first, second]
        )

        self.assertEqual(shared_range, [1.0, 9.0])
        self.assertEqual(windows, [[1.0, 3.0], [7.0, 9.0]])
        self.assertEqual(scales, [11.0, 22.0])

    def test_normalization_uses_paired_window_ratios_against_new_trace(
        self,
    ) -> None:
        first = [(1.0, 1.0), (2.0, 1.0), (8.0, 100.0), (9.0, 100.0)]
        second = [(1.0, 2.0), (2.0, 2.0), (8.0, 300.0), (9.0, 300.0)]

        _, scales, windows = server.shared_normalization_details([first, second])

        self.assertEqual(windows, [[1.0, 5.0], [5.0, 9.0]])
        self.assertEqual(scales, [50.5, 126.25])

    def test_each_legacy_arm_uses_its_full_pairwise_overlap(self) -> None:
        reference = [
            (index / 10, 10.0 if index < 50 else 100.0)
            for index in range(101)
        ]
        left = [
            (wavelength, flux * (4.0 if wavelength >= 4.5 else 2.0))
            for wavelength, flux in reference
            if wavelength <= 5.5
        ]
        right = [
            (wavelength, flux * (4.0 if wavelength <= 5.5 else 3.0))
            for wavelength, flux in reference
            if wavelength >= 4.5
        ]

        scales, details = server.reference_normalization_details(
            [reference, left, right]
        )

        self.assertAlmostEqual(scales[1] / scales[0], 2.0)
        self.assertAlmostEqual(scales[2] / scales[0], 3.0)
        self.assertEqual(details[1]["range_angstrom"], [0.0, 5.5])
        self.assertEqual(details[2]["range_angstrom"], [4.5, 10.0])
        self.assertEqual(details[1]["method"], "paired_overlap_windows")
        self.assertEqual(details[2]["method"], "paired_overlap_windows")

    def test_multiple_legacy_arms_do_not_report_a_false_single_range(self) -> None:
        current = {"moca_specid": 1}
        legacy = [{"moca_specid": 2}, {"moca_specid": 3}]
        samples = [
            ([(1.0, 2.0), (2.0, 4.0), (3.0, 6.0)], [], []),
            ([(1.0, 4.0), (2.0, 8.0)], [], []),
            ([(2.0, 12.0), (3.0, 18.0)], [], []),
        ]
        with (
            mock.patch.object(server, "_spectrum_metadata", return_value=current),
            mock.patch.object(server, "_legacy_metadata", return_value=legacy),
            mock.patch.object(
                server,
                "_spectral_samples_for_specids_by_quality",
                return_value={1: samples[0], 2: samples[1], 3: samples[2]},
            ),
        ):
            payload = server.spectrum_payload(1)

        self.assertIsNone(payload["normalization_range_angstrom"])
        self.assertEqual(payload["normalization_windows_angstrom"], [])
        self.assertEqual(len(payload["normalization_details"]), 3)
        self.assertEqual(
            [trace["normalization_range_angstrom"] for trace in payload["traces"]],
            [[1.0, 3.0], [1.0, 2.0], [2.0, 3.0]],
        )
        self.assertAlmostEqual(
            payload["traces"][1]["normalization_scale"]
            / payload["traces"][0]["normalization_scale"],
            2.0,
        )
        self.assertAlmostEqual(
            payload["traces"][2]["normalization_scale"]
            / payload["traces"][0]["normalization_scale"],
            3.0,
        )

    def test_spectral_samples_are_split_by_ignored_flag(self) -> None:
        rows = [
            {
                "wavelength_angstrom": 1.0,
                "flux_flambda": 2.0,
                "flux_flambda_unc": 0.5,
                "ignored": 0,
            },
            {
                "wavelength_angstrom": 2.0,
                "flux_flambda": 200.0,
                "flux_flambda_unc": 2.0,
                "ignored": 1,
            },
            {
                "wavelength_angstrom": 3.0,
                "flux_flambda": float("nan"),
                "flux_flambda_unc": 1.0,
                "ignored": 1,
            },
        ]
        with mock.patch.object(server, "readonly_rows", return_value=rows) as query:
            valid, ignored, snr = server._spectral_samples_by_quality(42, None, None)

        self.assertEqual(valid, [(1.0, 2.0)])
        self.assertEqual(ignored, [(2.0, 200.0)])
        self.assertEqual(snr, [(1.0, 4.0)])
        sql = query.call_args.args[0]
        self.assertIn("ignored", sql)
        self.assertIn("flux_flambda_unc", sql)
        self.assertNotIn("ignored=0", sql)

    def test_snr_excludes_ignored_missing_and_nonpositive_uncertainties(self) -> None:
        rows = [
            {"wavelength_angstrom": 1.0, "flux_flambda": 6.0, "flux_flambda_unc": 2.0, "ignored": 0},
            {"wavelength_angstrom": 2.0, "flux_flambda": 6.0, "flux_flambda_unc": 2.0, "ignored": 1},
            {"wavelength_angstrom": 3.0, "flux_flambda": 6.0, "flux_flambda_unc": None, "ignored": 0},
            {"wavelength_angstrom": 4.0, "flux_flambda": 6.0, "flux_flambda_unc": 0.0, "ignored": 0},
            {"wavelength_angstrom": 5.0, "flux_flambda": -2.0, "flux_flambda_unc": 0.5, "ignored": 0},
        ]
        with mock.patch.object(server, "readonly_rows", return_value=rows):
            _, _, snr = server._spectral_samples_by_quality(42, None, None)

        self.assertEqual(snr, [(1.0, 3.0), (5.0, -4.0)])

    def test_displayed_spectra_are_loaded_in_one_grouped_query(self) -> None:
        rows = [
            {"moca_specid": 1, "wavelength_angstrom": 1.0, "flux_flambda": 2.0, "flux_flambda_unc": 1.0, "ignored": 0},
            {"moca_specid": 2, "wavelength_angstrom": 1.5, "flux_flambda": 6.0, "flux_flambda_unc": 2.0, "ignored": 0},
        ]
        with mock.patch.object(server, "readonly_rows", return_value=rows) as query:
            samples = server._spectral_samples_for_specids_by_quality([1, 2], None, None)

        self.assertEqual(samples[1][0], [(1.0, 2.0)])
        self.assertEqual(samples[2][2], [(1.5, 3.0)])
        self.assertEqual(query.call_count, 1)
        sql, parameters = query.call_args.args
        self.assertIn("moca_specid IN (%s,%s)", sql)
        self.assertEqual(parameters, [1, 2])

    def test_payload_returns_ignored_points_but_excludes_them_from_scaling(self) -> None:
        current = {"moca_specid": 1}
        legacy = [{"moca_specid": 2}]
        samples = [
            ([(1.0, 2.0), (2.0, 4.0)], [(1.5, 20_000.0)], [(1.0, 5.0)]),
            ([(1.0, 10.0), (2.0, 20.0)], [(1.5, -20_000.0)], []),
        ]
        with (
            mock.patch.object(server, "_spectrum_metadata", return_value=current),
            mock.patch.object(server, "_legacy_metadata", return_value=legacy),
            mock.patch.object(
                server,
                "_spectral_samples_for_specids_by_quality",
                return_value={1: samples[0], 2: samples[1]},
            ),
        ):
            payload = server.spectrum_payload(1)

        self.assertEqual(payload["normalization_range_angstrom"], [1.0, 2.0])
        self.assertEqual(payload["normalization_windows_angstrom"], [[1.0, 2.0]])
        self.assertEqual(
            [trace["normalization_scale"] for trace in payload["traces"]],
            [3.0, 15.0],
        )
        self.assertEqual(payload["traces"][0]["original_ignored_points"], 1)
        self.assertEqual(payload["traces"][0]["ignored_points"], [(1.5, 20_000.0)])
        self.assertEqual(payload["traces"][0]["original_snr_points"], 1)
        self.assertEqual(payload["traces"][0]["snr_points"], [(1.0, 5.0)])
        self.assertEqual(payload["traces"][0]["smoothing_points"], samples[0][0])
        self.assertEqual(payload["max_points"], server.DEFAULT_MAX_POINTS)

    def test_payload_overplots_at_most_three_legacy_spectra(self) -> None:
        current = {"moca_specid": 1}
        legacy = [{"moca_specid": specid} for specid in range(2, 7)]
        samples = {
            specid: ([(1.0, float(specid)), (2.0, float(specid))], [], [])
            for specid in range(1, 7)
        }
        with (
            mock.patch.object(server, "_spectrum_metadata", return_value=current),
            mock.patch.object(server, "_legacy_metadata", return_value=legacy),
            mock.patch.object(
                server,
                "_spectral_samples_for_specids_by_quality",
                return_value={specid: samples[specid] for specid in range(1, 5)},
            ) as grouped_samples,
        ):
            payload = server.spectrum_payload(1)

        self.assertEqual(payload["legacy_count"], 3)
        self.assertEqual(payload["total_legacy_count"], 5)
        self.assertEqual(
            [trace["metadata"]["moca_specid"] for trace in payload["traces"]],
            [1, 2, 3, 4],
        )
        self.assertEqual(grouped_samples.call_args.args[0], [1, 2, 3, 4])

    def test_payload_keeps_native_smoothing_samples_before_display_downsampling(
        self,
    ) -> None:
        current = {"moca_specid": 1, "moca_oid": None}
        native = [(float(index), float(index % 5)) for index in range(100)]
        with (
            mock.patch.object(server, "_spectrum_metadata", return_value=current),
            mock.patch.object(server, "_legacy_metadata", return_value=[]),
            mock.patch.object(
                server,
                "_spectral_samples_for_specids_by_quality",
                return_value={1: (native, [], [])},
            ),
        ):
            payload = server.spectrum_payload(1, max_points=20)

        trace = payload["traces"][0]
        self.assertEqual(trace["smoothing_points"], native)
        self.assertEqual(trace["original_points"], 100)
        self.assertLessEqual(len(trace["points"]), 20)
        self.assertEqual(payload["max_points"], 20)

    def test_payload_adds_one_approximate_trace_only_when_exact_match_is_absent(
        self,
    ) -> None:
        current = {
            "moca_specid": 1,
            "moca_oid": 88,
            "moca_instid": "new_camera",
        }
        approximate = {
            "moca_specid": 9,
            "moca_oid": 88,
            "moca_instid": "legacy_camera",
            "approximate_match_basis": "different instrument",
        }
        with (
            mock.patch.object(server, "_spectrum_metadata", return_value=current),
            mock.patch.object(server, "_legacy_metadata", return_value=[]),
            mock.patch.object(
                server, "_approximate_legacy_metadata", return_value=approximate
            ) as fallback,
            mock.patch.object(
                server,
                "_spectral_samples_for_specids_by_quality",
                return_value={
                    1: ([(1.0, 2.0)], [], []),
                    9: ([(1.0, 4.0)], [], []),
                },
            ),
        ):
            payload = server.spectrum_payload(1)

        fallback.assert_called_once_with(current)
        self.assertEqual(payload["legacy_count"], 0)
        self.assertEqual(payload["approximate_legacy_count"], 1)
        self.assertEqual(payload["approximate_legacy"], approximate)
        self.assertEqual(
            [trace["kind"] for trace in payload["traces"]],
            ["new", "approximate_legacy"],
        )

    def test_exact_legacy_match_suppresses_approximate_lookup(self) -> None:
        current = {"moca_specid": 1}
        exact = {"moca_specid": 2}
        with (
            mock.patch.object(server, "_spectrum_metadata", return_value=current),
            mock.patch.object(server, "_legacy_metadata", return_value=[exact]),
            mock.patch.object(server, "_approximate_legacy_metadata") as fallback,
            mock.patch.object(
                server,
                "_spectral_samples_for_specids_by_quality",
                return_value={
                    1: ([(1.0, 2.0)], [], []),
                    2: ([(1.0, 4.0)], [], []),
                },
            ),
        ):
            payload = server.spectrum_payload(1)

        fallback.assert_not_called()
        self.assertEqual(payload["legacy_count"], 1)
        self.assertEqual(payload["approximate_legacy_count"], 0)
        self.assertIsNone(payload["approximate_legacy"])

    def test_downsample_is_bounded_sorted_and_preserves_edges(self) -> None:
        samples = [(float(index), float((index % 13) - 6)) for index in range(10_000)]
        result = server.minmax_downsample(samples, 500)
        self.assertLessEqual(len(result), 500)
        self.assertEqual(result[0], samples[0])
        self.assertEqual(result[-1], samples[-1])
        self.assertEqual(result, sorted(result))

    def test_observing_night_expression_uses_requested_alias(self) -> None:
        expression = server.observing_night("legacy")
        self.assertIn("legacy.data_collection_date", expression)
        self.assertIn("legacy.epoch_mjd", expression)

    def test_object_name_expression_has_canonical_and_unmatched_fallbacks(self) -> None:
        expression = server.object_name_sql("s", "object_row")
        self.assertIn("object_row.designation", expression)
        self.assertIn("s.object_designation", expression)
        self.assertIn("s.telescope_object_name", expression)
        self.assertIn("s.spectrum_name", expression)
        self.assertIn("s.moca_specid", expression)

    def test_spectrum_index_requests_pipeline_version_and_modification_date(self) -> None:
        with mock.patch.object(server, "readonly_rows", return_value=[]) as query:
            server.spectrum_index(106)
        sql = query.call_args.args[0]
        self.assertIn("s.data_reduction_pipeline_version", sql)
        self.assertIn("s.modified_timestamp AS modification_date", sql)

    def test_spectrum_metadata_requests_resolution_and_native_sampling(self) -> None:
        with mock.patch.object(server, "readonly_rows", return_value=[]) as query:
            with self.assertRaisesRegex(ValueError, "does not exist"):
                server._spectrum_metadata(1)
        sql = query.call_args.args[0]
        self.assertIn("s.median_spectral_resolving_power", sql)
        self.assertIn("s.pix_per_res_element", sql)

    def test_spectrum_metadata_exposes_qa_warnings_without_raw_comment_payload(self) -> None:
        row = {
            "moca_specid": 1,
            "comments": "QA_WARNING_CODES=MISSING_EXPOSURE; RV_WCS_QA=WARN",
            "fits_header": "SCIQA   = 'NEEDS_REVIEW'",
        }
        with mock.patch.object(server, "readonly_rows", return_value=[row]) as query:
            metadata = server._spectrum_metadata(1)

        sql = query.call_args.args[0]
        self.assertIn("s.comments", sql)
        self.assertIn("s.fits_header", sql)
        self.assertEqual(
            metadata["qa_warnings"],
            ["MISSING_EXPOSURE", "RV_WCS_QA=WARN", "SCIQA=NEEDS_REVIEW"],
        )
        self.assertNotIn("comments", metadata)
        self.assertNotIn("fits_header", metadata)

    def test_qa_warning_extraction_combines_live_metadata_formats(self) -> None:
        comments = (
            "QA_WARNING_CODES=MISSING_INDIVIDUAL_EXTRACTIONS,SECONDARY_TRACE_DETECTED; "
            "RV_WCS_QA=WARN; TELLURIC_QA=QA_FAILED; "
            "A0_STANDARD_WARNING_FLAGS=NONE; "
            "CALIBRATION_WARNING=DROPPED_INVALID_ECHELLE_ORDERS; "
            "WARNING: relative flux"
        )
        fits_header = (
            "NQAWARN =                    2\n"
            "QAWARN  = 'SECONDARY_TRACE_DETECTED,OH_VALIDATION_WEAK'\n"
            "SCIQA   = 'NEEDS_REVIEW'\n"
        )

        self.assertEqual(
            server.spectrum_qa_warnings(comments, fits_header),
            [
                "MISSING_INDIVIDUAL_EXTRACTIONS",
                "SECONDARY_TRACE_DETECTED",
                "CALIBRATION_WARNING=DROPPED_INVALID_ECHELLE_ORDERS",
                "RV_WCS_QA=WARN",
                "TELLURIC_QA=QA_FAILED",
                "relative flux",
                "OH_VALIDATION_WEAK",
                "SCIQA=NEEDS_REVIEW",
            ],
        )

    def test_qa_warning_extraction_ignores_pass_and_empty_flags(self) -> None:
        comments = (
            "SCIQA=PASS; SEEING_QA=PASS; A0_STANDARD_WARNING_FLAGS=; "
            "CALIBRATION_WARNING=NONE; SECONDARY_TRACE_QA=UNKNOWN"
        )
        fits_header = "NQAWARN = 0\nSCIQA = 'PASS'"

        self.assertEqual(server.spectrum_qa_warnings(comments, fits_header), [])

    def test_qa_warning_extraction_deduplicates_compact_fits_aliases(self) -> None:
        comments = "RV_WCS_QA=FAIL; SEEING_QA=WARN_PARTIAL"
        fits_header = "RVWCSQA = 'FAIL'\nSEEQA = 'WARN_PARTIAL'"

        self.assertEqual(
            server.spectrum_qa_warnings(comments, fits_header),
            ["RV_WCS_QA=FAIL", "SEEING_QA=WARN_PARTIAL"],
        )

    def test_xshooter_pypeit_package_is_selectable_but_retired_package_is_not(self) -> None:
        with mock.patch.object(server, "readonly_rows", return_value=[]):
            self.assertEqual(server.spectrum_index(114), [])
        with self.assertRaisesRegex(ValueError, "package 112 is not managed"):
            server.spectrum_index(112)

    def test_json_default_serializes_database_timestamps(self) -> None:
        payload = json.dumps(
            {"modification_date": datetime(2026, 8, 26, 12, 34, 56)},
            default=server._json_default,
        )
        self.assertIn("2026-08-26T12:34:56", payload)

    def test_large_json_responses_are_gzipped_when_the_browser_accepts_it(self) -> None:
        payload = {"points": [[index, index / 3] for index in range(2_000)]}

        compressed, encoding = server.encoded_json(payload, "br, gzip")
        plain, plain_encoding = server.encoded_json(payload, "identity")

        self.assertEqual(encoding, "gzip")
        self.assertIsNone(plain_encoding)
        self.assertEqual(gzip.decompress(compressed), plain)
        self.assertLess(len(compressed), len(plain))

    def test_mode_sql_requires_label_or_physical_signature(self) -> None:
        expression = server.mode_compatible_sql("current", "legacy")
        self.assertIn(
            "LOWER(TRIM(legacy.instrument_mode_name))="
            "LOWER(TRIM(current.instrument_mode_name))",
            expression,
        )
        self.assertIn("current.slit_width_as", expression)
        self.assertIn("legacy.slit_width_as", expression)
        self.assertIn("0.5*LEAST", expression)

    def test_mode_labels_are_case_and_whitespace_insensitive_without_slit(self) -> None:
        current = {
            "instrument_mode_name": "prism",
            "slit_width_as": 0.8,
            "min_wavelength_angstrom": 8121.27,
            "max_wavelength_angstrom": 25129.89,
        }
        legacy = {
            "instrument_mode_name": " Prism ",
            "slit_width_as": None,
            "min_wavelength_angstrom": 8071.0,
            "max_wavelength_angstrom": 25310.0,
        }
        self.assertTrue(server.rows_mode_compatible(current, legacy))

    def test_equivalent_historical_mode_label_is_accepted(self) -> None:
        current = {
            "instrument_mode_name": "new",
            "slit_width_as": 0.72,
            "min_wavelength_angstrom": 9000,
            "max_wavelength_angstrom": 25000,
        }
        legacy = {
            "instrument_mode_name": None,
            "slit_width_as": 0.718,
            "min_wavelength_angstrom": 9100,
            "max_wavelength_angstrom": 24000,
        }
        self.assertTrue(server.rows_mode_compatible(current, legacy))

    def test_other_xshooter_arm_is_rejected(self) -> None:
        current = {
            "instrument_mode_name": "ECHELLE",
            "slit_width_as": 1.2,
            "min_wavelength_angstrom": 5300,
            "max_wavelength_angstrom": 10200,
        }
        legacy = {
            "instrument_mode_name": "NIR",
            "slit_width_as": 1.2,
            "min_wavelength_angstrom": 10280,
            "max_wavelength_angstrom": 24700,
        }
        self.assertFalse(server.rows_mode_compatible(current, legacy))

    @staticmethod
    def _approximate_current() -> dict[str, object]:
        return {
            "moca_specid": 1,
            "moca_oid": 77,
            "moca_instid": "camera_a",
            "observing_night": "2026-08-30",
            "epoch_mjd": 61282.0,
            "min_wavelength_angstrom": 10_000.0,
            "max_wavelength_angstrom": 20_000.0,
            "median_spectral_resolving_power": 2_000.0,
        }

    def test_approximate_match_prefers_same_instrument_on_a_different_night(
        self,
    ) -> None:
        current = self._approximate_current()
        candidates = [
            {
                "moca_specid": 20,
                "moca_oid": 77,
                "moca_instid": "camera_b",
                "observing_night": "2026-08-30",
                "epoch_mjd": 61282.0,
                "min_wavelength_angstrom": 10_000.0,
                "max_wavelength_angstrom": 20_000.0,
                "median_spectral_resolving_power": 2_000.0,
            },
            {
                "moca_specid": 10,
                "moca_oid": 77,
                "moca_instid": "camera_a",
                "observing_night": "2024-01-05",
                "epoch_mjd": 60314.0,
                "min_wavelength_angstrom": 11_000.0,
                "max_wavelength_angstrom": 19_000.0,
                "median_spectral_resolving_power": 1_800.0,
            },
            {
                "moca_specid": 11,
                "moca_oid": 77,
                "moca_instid": "camera_a",
                "observing_night": None,
                "min_wavelength_angstrom": 10_000.0,
                "max_wavelength_angstrom": 20_000.0,
                "median_spectral_resolving_power": 2_000.0,
            },
        ]

        selected = server.select_approximate_legacy(current, candidates)

        self.assertIsNotNone(selected)
        self.assertEqual(selected["moca_specid"], 10)
        self.assertEqual(
            selected["approximate_match_tier"], "same_instrument_different_night"
        )
        self.assertAlmostEqual(selected["wavelength_overlap_fraction"], 1.0)

    def test_same_instrument_unknown_night_precedes_other_instruments(
        self,
    ) -> None:
        current = self._approximate_current()
        candidates = [
            {
                "moca_specid": 10,
                "moca_oid": 77,
                "moca_instid": "camera_a",
                "observing_night": "2026-08-30",
                "min_wavelength_angstrom": 10_000.0,
                "max_wavelength_angstrom": 20_000.0,
            },
            {
                "moca_specid": 11,
                "moca_oid": 77,
                "moca_instid": "camera_a",
                "observing_night": None,
                "min_wavelength_angstrom": 10_000.0,
                "max_wavelength_angstrom": 20_000.0,
            },
            {
                "moca_specid": 20,
                "moca_oid": 77,
                "moca_instid": "camera_b",
                "observing_night": "2025-01-01",
                "min_wavelength_angstrom": 10_000.0,
                "max_wavelength_angstrom": 20_000.0,
                "median_spectral_resolving_power": 2_000.0,
            },
        ]

        selected = server.select_approximate_legacy(current, candidates)

        self.assertIsNotNone(selected)
        self.assertEqual(selected["moca_specid"], 11)
        self.assertEqual(
            selected["approximate_match_tier"], "same_instrument_unknown_night"
        )
        self.assertEqual(
            selected["approximate_match_basis"],
            "same instrument; observing night unavailable",
        )

    def test_same_instrument_known_same_night_is_not_an_approximate_match(
        self,
    ) -> None:
        current = self._approximate_current()
        same_night = {
            "moca_specid": 10,
            "moca_oid": 77,
            "moca_instid": "camera_a",
            "observing_night": "2026-08-30",
            "min_wavelength_angstrom": 10_000.0,
            "max_wavelength_angstrom": 20_000.0,
        }

        self.assertIsNone(server.select_approximate_legacy(current, [same_night]))

    def test_cross_instrument_approximate_requires_overlap_and_balances_r_and_coverage(
        self,
    ) -> None:
        current = self._approximate_current()
        candidates = [
            {
                "moca_specid": 21,
                "moca_oid": 77,
                "moca_instid": "camera_b",
                "observing_night": "2020-01-01",
                "min_wavelength_angstrom": 10_000.0,
                "max_wavelength_angstrom": 20_000.0,
                "median_spectral_resolving_power": 4_000.0,
            },
            {
                "moca_specid": 22,
                "moca_oid": 77,
                "moca_instid": "camera_c",
                "observing_night": "2019-01-01",
                "min_wavelength_angstrom": 12_000.0,
                "max_wavelength_angstrom": 18_000.0,
                "median_spectral_resolving_power": 2_000.0,
            },
            {
                "moca_specid": 23,
                "moca_oid": 77,
                "moca_instid": "camera_d",
                "observing_night": "2026-08-29",
                "min_wavelength_angstrom": 21_000.0,
                "max_wavelength_angstrom": 25_000.0,
                "median_spectral_resolving_power": 2_000.0,
            },
        ]

        selected = server.select_approximate_legacy(current, candidates)

        self.assertIsNotNone(selected)
        self.assertEqual(selected["moca_specid"], 22)
        self.assertEqual(selected["approximate_match_tier"], "different_instrument")
        self.assertAlmostEqual(selected["wavelength_coverage_similarity"], 0.6)
        self.assertAlmostEqual(selected["resolving_power_ratio"], 1.0)

    def test_approximate_match_never_crosses_objects(self) -> None:
        current = self._approximate_current()
        wrong_object = {
            "moca_specid": 21,
            "moca_oid": 99,
            "moca_instid": "camera_b",
            "observing_night": "2020-01-01",
            "min_wavelength_angstrom": 10_000.0,
            "max_wavelength_angstrom": 20_000.0,
            "median_spectral_resolving_power": 2_000.0,
        }

        self.assertIsNone(server.select_approximate_legacy(current, [wrong_object]))

    def test_cross_instrument_fallback_requires_a_known_instrument(self) -> None:
        current = self._approximate_current()
        unknown_instrument = {
            "moca_specid": 21,
            "moca_oid": 77,
            "moca_instid": None,
            "observing_night": "2020-01-01",
            "min_wavelength_angstrom": 10_000.0,
            "max_wavelength_angstrom": 20_000.0,
            "median_spectral_resolving_power": 2_000.0,
        }

        self.assertIsNone(
            server.select_approximate_legacy(current, [unknown_instrument])
        )

    def test_approximate_query_is_same_object_and_excludes_managed_packages(
        self,
    ) -> None:
        current = self._approximate_current()
        with mock.patch.object(server, "readonly_rows", return_value=[]) as query:
            self.assertIsNone(server._approximate_legacy_metadata(current))

        sql, parameters = query.call_args.args
        self.assertIn("legacy.moca_oid=%s", sql)
        self.assertIn("legacy.moca_specpackid NOT IN", sql)
        self.assertIn("legacy.median_spectral_resolving_power", sql)
        self.assertEqual(parameters[-1], 77)


if __name__ == "__main__":
    unittest.main()
