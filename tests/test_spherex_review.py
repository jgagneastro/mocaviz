"""File-free/credential/transaction regression tests; no live DB required."""
from __future__ import annotations

import ast
import builtins
import copy
import io
import json
import os
from pathlib import Path
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import numpy as np
import pymysql
from werkzeug.test import Client
from werkzeug.wrappers import Response

from app import application
from mocaviz.app import app
from mocaviz import spherex_review as review
from mocaviz import spherex_autotype_core as core


AUTH = {"user": "management", "password": "test-placeholder", "database": review.PRIVATE_DB}
HEADERS = {"X-MOCA-User": AUTH["user"], "X-MOCA-Password": AUTH["password"], "X-MOCA-Database": AUTH["database"]}


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def post(self, operation, body=None, headers=None):
        return self.client.post("/api/spherex-review/" + operation, json=body or {}, headers=headers or {})

    def test_pages_on_both_wsgi_mounts_and_security_headers(self):
        client = Client(application, Response)
        for prefix in ("", "/js"):
            for page in ("spherex-autotype", "spherex-review"):
                result = client.get(prefix + "/" + page)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.headers["Cache-Control"], "no-store")
                self.assertEqual(result.headers["Referrer-Policy"], "no-referrer")
                self.assertNotIn("auth_theme.js", result.get_data(as_text=True))
                result.close()

    def test_environment_credentials_never_authorize_any_live_endpoint(self):
        with patch.dict(os.environ, {"MOCA_USERNAME": "management", "MOCA_PASSWORD": "not-allowed",
                                     "MOCA_DBNAME": review.PRIVATE_DB}), patch.object(review.pymysql, "connect") as connect:
            for op in ("context", "queue", "analyze", "preview", "submit", "undo"):
                self.assertEqual(self.post(op).status_code, 403, op)
            # A client-controlled JSON body cannot select a write account.
            self.assertEqual(self.post("submit", {"user": "management", "pwd": "not-allowed"}).status_code, 403)
            connect.assert_not_called()

    def test_collaborator_and_public_cannot_reach_any_write_path(self):
        with patch.object(review.pymysql, "connect") as connect:
            for user in ("collaborators", "public", "Management", ""):
                for op in ("preview", "submit", "undo"):
                    headers = {**HEADERS, "X-MOCA-User": user}
                    self.assertEqual(self.post(op, headers=headers).status_code, 403, (op, user))
            connect.assert_not_called()

    def test_mock_never_allows_writes_even_with_management(self):
        with patch.object(review.pymysql, "connect") as connect:
            for op in ("preview", "submit", "undo"):
                self.assertEqual(self.post(op, {"mock": True}, HEADERS).status_code, 403)
            connect.assert_not_called()

    def test_aliases_exact_host_and_no_missing_credential_fallback(self):
        with app.test_request_context("/?username=management&password=test-placeholder&database=mocadb_private_tables"):
            self.assertEqual(review.credentials(), AUTH)
        with app.test_request_context("/?user=management&dbase=mocadb_private_tables"):
            with self.assertRaises(review.ReviewError):
                review.credentials()
        for url in ("?host=attacker.example", "?port=3307", "?user=collaborators"):
            with app.test_request_context("/" + url, headers=HEADERS):
                with self.assertRaises(review.ReviewError):
                    review.credentials()

    def test_request_connection_closed_and_not_retained_in_engine_cache(self):
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = {"authenticated_user": "management@%"}
        with patch.object(review.pymysql, "connect", return_value=conn) as connect:
            response = self.post("context", headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["can_write"])
        self.assertEqual(connect.call_args.kwargs["host"], "mocadb.ca")
        self.assertFalse(connect.call_args.kwargs["autocommit"])
        self.assertEqual(connect.call_args.kwargs["password"], AUTH["password"])
        conn.close.assert_called_once()
        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()

    def test_server_checks_authenticated_database_identity(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {"authenticated_user": "collaborators@%"}
        with patch.object(review.pymysql, "connect", return_value=conn):
            response = self.post("context", headers=HEADERS)
        self.assertEqual(response.status_code, 403)

    def test_db_exception_never_exposes_credentials_or_sql(self):
        with patch.object(review.pymysql, "connect", side_effect=pymysql.OperationalError(2003, "secret db URL " + AUTH["password"])):
            response = self.post("context", headers=HEADERS)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(AUTH["password"], response.get_data(as_text=True))

    def test_json_size_and_validation(self):
        self.assertEqual(self.client.post("/api/spherex-review/queue", data="x").status_code, 415)
        self.assertEqual(self.client.post("/api/spherex-review/queue", data="{", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/api/spherex-review/queue", data=" " * (review.MAX_BODY + 1),
                                          content_type="application/json").status_code, 413)
        self.assertEqual(self.post("queue", [1, 2]).status_code, 400)

    def test_receipt_tampering_expiry_kind_and_other_password(self):
        token = review.seal(AUTH, "plan", {"moca_oid": 123})
        self.assertEqual(review.unseal(dict(AUTH), token, "plan"), {"moca_oid": 123})
        for value, auth, kind in (
            (token + "x", AUTH, "plan"), (token, AUTH, "undo"),
            (token, {**AUTH, "password": "another"}, "plan"),
            (review.seal(AUTH, "plan", {}, lifetime=-1), AUTH, "plan"),
        ):
            with self.assertRaises(review.ReviewError):
                review.unseal(auth, value, kind)

    def test_queue_filters_are_bound_and_lane_allowlisted(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        body = {"lane": "sublimeaperture", "moca_oids": [100], "min_snr": 5, "min_sptn": 10, "no_known": True}
        review.queue(cursor, body)
        sql, params = cursor.execute.call_args.args
        self.assertIn("pcat_spherex_sublimeaperture_visual_vetting", sql)
        self.assertIn("mo.ignored=0", sql)
        self.assertIn("v.moca_oid IS NULL", sql)
        self.assertIn(100, params)
        with self.assertRaises(review.ReviewError):
            review.queue(cursor, {"lane": "x; DROP TABLE moca_spectra"})
        with self.assertRaises(review.ReviewError):
            review.queue(cursor, {"moca_oids": ["1 OR 1=1"]})

    def test_spectrum_must_belong_to_oid_and_lane(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        with self.assertRaises(review.ReviewError) as caught:
            review.dataset(cursor, review.LANES["spiff"], 10, 20)
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(cursor.execute.call_args.args[1], (20, 10, 55))

    def test_mock_fit_and_no_disk_writes_with_shared_cache_enabled(self):
        real_open = builtins.open
        def read_only_open(file, mode="r", *args, **kwargs):
            if any(c in str(mode) for c in "wax+"):
                raise AssertionError("Request tried to write a file: " + str(file))
            return real_open(file, mode, *args, **kwargs)
        with patch("builtins.open", side_effect=read_only_open), patch("io.open", side_effect=read_only_open), \
             patch.object(Path, "mkdir", side_effect=AssertionError("mkdir")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("write_bytes")), \
             patch.object(Path, "write_text", side_effect=AssertionError("write_text")), \
             patch.object(review.pymysql, "connect") as connect:
            for lane in review.LANES:
                response = self.post("analyze", {"mock": True, "lane": lane})
                self.assertEqual(response.status_code, 200, response.json)
                self.assertEqual(response.json["fit"]["best"]["spectral_type"], "L3")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertNotIn("X-MOCA-Response-Cache", response.headers)
            connect.assert_not_called()

    def test_runtime_assets_only_read_files(self):
        for path in ("/plotly.min.js", "/static/spherex_review.js", "/static/spherex_review.css"):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.data), 100)

    def test_pixel_locks_are_limited_to_the_selected_spectrum(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"id": 12}]
        review.lock_source_pixels(cursor, 55)
        sql, params = cursor.execute.call_args.args
        self.assertIn("WHERE moca_specid=%s", sql)
        self.assertIn("LIMIT 10001 FOR UPDATE", sql)
        self.assertEqual(params, (55,))
        self.assertNotIn("template", sql)


def make_item(lane="spiffstacker"):
    item = review.demo_item({"lane": lane})
    item["state"] = {"vet": [], "spt": [], "spectra": [
        {"moca_specid": 11001, "ignored": 0, "modified_timestamp": "2026-09-26T00:00:00"}
    ]}
    item["revision"] = review.fingerprint(item["state"])
    item["data_revision"] = review.fingerprint([item["raw_spectrum"], []])
    return item


class TransactionTests(unittest.TestCase):
    def setUp(self):
        # Lock SQL is verified separately; transaction tests focus on mutations.
        patcher = patch.object(review, "lock_source_pixels")
        patcher.start()
        self.addCleanup(patcher.stop)

    def body(self, item, action="classify", classification="good"):
        return {"lane": item["lane"], "moca_oid": 1001, "moca_specid": 11001,
                "revision": item["revision"], "data_revision": item["data_revision"],
                "action": action, "classification": classification, "is_public": 0, "rls": "gagne"}

    def prepare(self, item, body):
        with patch.object(review, "analyze", return_value=item):
            return review.prepare(MagicMock(), body, AUTH)

    def test_prepare_all_lanes_uses_correct_tables_and_methods_without_writes(self):
        for key, lane in review.LANES.items():
            item = make_item(key)
            cursor = MagicMock()
            with patch.object(review, "analyze", return_value=item):
                prepared = review.prepare(cursor, self.body(item), AUTH)
            cursor.execute.assert_not_called()
            self.assertEqual(prepared["row_counts"], {lane["table"]: 1, "data_spectral_types": 1})
            spt = prepared["plan"]["operations"][1]["rows"][0]
            self.assertEqual(spt["calculation_method"], lane["method"])
            self.assertEqual(spt["spectral_type"], "L3")
            self.assertEqual(spt["ignored"], 0)
            self.assertEqual(spt["is_public"], 0)
            self.assertEqual(spt["rls"], "gagne")
            self.assertNotIn("adopted", spt)

    def test_bad_class_ignores_spectra_and_preserves_existing_spectral_type(self):
        item = make_item()
        item["state"]["spt"] = [{"id": 42, "spectral_type": "T5", "ignored": 0}]
        item["revision"] = review.fingerprint(item["state"])
        prepared = self.prepare(item, self.body(item, classification="bad"))
        ops = prepared["plan"]["operations"]
        self.assertEqual(ops[1]["rows"], [{"id": 42, "ignored": 1}])
        self.assertEqual(ops[2]["rows"], [{"moca_specid": 11001, "ignored": 1}])

    def test_quality_can_be_rejected_without_a_valid_fit(self):
        item = make_item()
        item["fit"] = None
        prepared = self.prepare(item, self.body(item, classification="bad"))
        self.assertNotIn("data_spectral_types", prepared["row_counts"])

    def test_preview_requires_explicit_visibility_and_replacement(self):
        item = make_item()
        body = self.body(item)
        del body["is_public"]
        with self.assertRaises(review.ReviewError):
            self.prepare(item, body)
        item["state"]["vet"] = [{"id": 2, "classification": "bad", "sources": None}]
        item["revision"] = review.fingerprint(item["state"])
        with self.assertRaises(review.ReviewError):
            self.prepare(item, self.body(item))
        prepared = self.prepare(item, {**self.body(item), "allow_replace": True, "is_public": 1})
        self.assertEqual(prepared["plan"]["operations"][1]["rows"][0]["rls"], "public")

    def test_stale_preview_cannot_overwrite_new_data(self):
        item = make_item()
        with self.assertRaises(review.ReviewError):
            self.prepare(item, {**self.body(item), "data_revision": "older"})

    def test_legacy_sublime_method_is_updated_without_creating_duplicate(self):
        item = make_item("sublimeaperture")
        item["state"]["spt"] = [{"id": 7, "calculation_method": "spherex_sublimeap_autotype"}]
        item["revision"] = review.fingerprint(item["state"])
        prepared = self.prepare(item, {**self.body(item, action="upsert_spt"), "allow_replace": True})
        self.assertEqual(prepared["plan"]["operations"][0]["rows"][0]["calculation_method"],
                         "spherex_sublimeap_autotype")

    def test_bad_pixel_plan_and_undo_are_scoped_to_selected_spectrum(self):
        item = make_item()
        item["fit"]["bad_pixel_ids"] = [1, 2]
        prepared = self.prepare(item, self.body(item, action="bad_pixels"))
        self.assertEqual(prepared["row_counts"], {"data_spectra": 2})
        changed = copy.deepcopy(item["raw_spectrum"])
        changed[0]["ignored"] = changed[1]["ignored"] = 1
        conn, cur = MagicMock(), MagicMock()
        with patch.object(review, "lock_object"), patch.object(review, "snapshot", return_value=item["state"]), \
             patch.object(review, "dataset", side_effect=[
                 (item["object"], item["raw_spectrum"], []), (item["object"], changed, [])]):
            result = review.submit(conn, cur, AUTH, {"receipt": prepared["receipt"]})
        updates = [call.args for call in cur.execute.call_args_list if call.args[0].startswith("UPDATE data_spectra")]
        self.assertEqual([args[1] for args in updates], [(1, 11001), (2, 11001)])
        saved = review.unseal(AUTH, result["undo_receipt"], "undo")
        self.assertEqual(saved["pixels"], [{"id": 1, "ignored": 0}, {"id": 2, "ignored": 0}])
        cur.reset_mock()
        with patch.object(review, "lock_object"), patch.object(review, "snapshot", return_value=item["state"]), \
             patch.object(review, "dataset", return_value=(item["object"], changed, [])):
            review.undo(conn, cur, AUTH, {"receipt": result["undo_receipt"]})
        self.assertEqual(cur.execute.call_args_list[0].args[1], (0, 1, 11001))
        self.assertEqual(cur.execute.call_args_list[1].args[1], (0, 2, 11001))

    def test_submit_transaction_includes_vetting_spt_and_changelog(self):
        item = make_item()
        prepared = self.prepare(item, self.body(item))
        conn, cur = MagicMock(), MagicMock()
        after = copy.deepcopy(item["state"])
        after["vet"] = [{"id": 1, "classification": "good", "sources": "mocaviz"}]
        with patch.object(review, "lock_object"), \
             patch.object(review, "snapshot", side_effect=[item["state"], after]), \
             patch.object(review, "dataset", return_value=(item["object"], item["raw_spectrum"], [])):
            result = review.submit(conn, cur, AUTH, {"receipt": prepared["receipt"]})
        conn.commit.assert_called_once()
        sql = [c.args[0] for c in cur.execute.call_args_list]
        self.assertIn("pcat_spherex_spiffstacker_visual_vetting", sql[0])
        self.assertIn("data_spectral_types", sql[1])
        self.assertIn("moca_changelog", sql[2])
        self.assertTrue(result["submitted"])
        saved = review.unseal(AUTH, result["undo_receipt"], "undo")
        self.assertEqual(saved["before"], item["state"])
        self.assertEqual(saved["after"], after)

    def test_submit_rejects_changed_spectrum_before_any_write(self):
        item = make_item()
        prepared = self.prepare(item, self.body(item))
        conn, cur = MagicMock(), MagicMock()
        with patch.object(review, "lock_object"), patch.object(review, "snapshot", return_value=item["state"]), \
             patch.object(review, "dataset", return_value=(item["object"], [], [])):
            with self.assertRaises(review.ReviewError):
                review.submit(conn, cur, AUTH, {"receipt": prepared["receipt"]})
        conn.commit.assert_not_called()
        cur.execute.assert_not_called()

    def test_failure_rolls_back_whole_request_and_never_commits(self):
        item = make_item()
        prepared = self.prepare(item, self.body(item))
        conn = MagicMock()
        cur = conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value = {"authenticated_user": "management@%"}
        cur.execute.side_effect = [None, None, pymysql.IntegrityError(1452, "private SQL details")]
        with patch.object(review.pymysql, "connect", return_value=conn), patch.object(review, "lock_object"), \
             patch.object(review, "snapshot", return_value=item["state"]), \
             patch.object(review, "dataset", return_value=(item["object"], item["raw_spectrum"], [])):
            response = app.test_client().post("/api/spherex-review/submit",
                json={"receipt": prepared["receipt"]}, headers=HEADERS)
        self.assertEqual(response.status_code, 503)
        conn.commit.assert_not_called()
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_undo_conflict_and_success(self):
        item = make_item()
        before = item["state"]
        after = copy.deepcopy(before)
        after["vet"] = [{"id": 4, "classification": "bad", "sources": "mocaviz"}]
        saved = {"lane": item["lane"], "moca_oid": 1001, "moca_specid": 11001,
            "before": before, "after": after, "pixels": [], "after_data": review.fingerprint(item["raw_spectrum"]),
            "operations": [{"table": review.LANES[item["lane"]]["table"], "rows": [after["vet"][0]]}],
            "is_public": 0, "rls": "gagne"}
        token = review.seal(AUTH, "undo", saved)
        conn, cur = MagicMock(), MagicMock()
        with patch.object(review, "lock_object"), patch.object(review, "snapshot", return_value=before), \
             patch.object(review, "dataset", return_value=(item["object"], item["raw_spectrum"], [])):
            with self.assertRaises(review.ReviewError):
                review.undo(conn, cur, AUTH, {"receipt": token})
        conn.commit.assert_not_called()
        with patch.object(review, "lock_object"), patch.object(review, "snapshot", return_value=after), \
             patch.object(review, "dataset", return_value=(item["object"], item["raw_spectrum"], [])):
            result = review.undo(conn, cur, AUTH, {"receipt": token})
        self.assertTrue(result["undone"])
        self.assertIn("DELETE FROM pcat_spherex_spiffstacker_visual_vetting", cur.execute.call_args_list[0].args[0])
        conn.commit.assert_called_once()


class FitTests(unittest.TestCase):
    def test_empty_spectrum_gives_a_reviewable_warning(self):
        with self.assertRaisesRegex(ValueError, "No spectral data"):
            core.fit_spectrum([], [])

    def test_known_scale_and_exact_template(self):
        w = np.linspace(9000, 42000, 30)
        f = np.linspace(1e-17, 4e-17, 30)
        result = core._compute_chi2(w, 2 * f, f / 10, w, f, 5, 5)
        self.assertAlmostEqual(result["scale_s"], 2.0)
        self.assertAlmostEqual(result["selection_score"] if "selection_score" in result else result["reduced_chi2"], 0.0)

    def test_ignored_points_are_not_resurrected(self):
        item = make_item()
        raw = item["raw_spectrum"]
        for row in raw:
            row["ignored"] = 1
        template = [{"moca_spherex_template_id": 1, "spectral_type": "L3", "spectral_type_number": 13,
                     "grid_type": "field", "wavelength_angstrom": r["wavelength_angstrom"],
                     "flux_flambda": r["flux_flambda"]} for r in raw]
        with self.assertRaisesRegex(ValueError, "non-ignored"):
            core.fit_spectrum(raw, template)


if __name__ == "__main__":
    unittest.main()
