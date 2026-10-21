from contextlib import contextmanager
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from mocaviz import app as api


class AstrometryManagementTests(unittest.TestCase):
    args = {"user": "management", "pwd": "synthetic-test-password", "dbase": "mocadb_private_tables"}

    def rows(self):
        return [dict(id=i, moca_oid=432, ignored=int(i == 3), comments=comment,
                     modified_timestamp="2026-10-21 12:00:00", mission_name="Survey",
                     data_release="DR1", measurement_epoch_yr=2010 + i,
                     is_public=int(i != 2), rls="gagne" if i == 2 else "public")
                for i, comment in ((1, None), (2, "Existing\n"), (3, "Previous"))]

    @contextmanager
    def database(self, rows=None):
        engine, conn = MagicMock(), MagicMock()
        engine.begin.return_value.__enter__.return_value = conn
        conn.execute.return_value.rowcount = 1
        cache = {"old": "cached payload"}

        def read_rows(connection, sql, expanding, ids, params):
            result = [dict(row) for row in (rows if rows is not None else self.rows())]
            if "SELECT id, ignored, comments FROM" in sql:
                updates = {call.args[1]["id"]: call for call in conn.execute.call_args_list}
                for row in result:
                    if row["id"] in updates:
                        call = updates[row["id"]]
                        row["ignored"] = 1
                        if "comments =" in str(call.args[0]):
                            row["comments"] = call.args[1]["comments"]
            return pd.DataFrame(result)

        with patch.object(api, "_engine", return_value=engine), \
                patch.object(api, "_read_sql_expanding", side_effect=read_rows) as read, \
                patch.object(api, "_db_table_exists", return_value=True), \
                patch.object(api, "_astrometry_insert_row", return_value=123) as audit, \
                patch.object(api, "_ASTROMETRY_OBJECT_CACHE", cache):
            yield engine, conn, read, audit, cache

    def body(self, **values):
        return {"moca_oid": 432, "selectedIds": [1, 2, 3], "appendComments": "Added note", **values}

    def test_preview_is_read_only_and_apply_appends_comments_and_audits_visibility(self):
        with self.database() as (engine, conn, read, audit, cache):
            preview = api._ignore_selected_astrometry_measurements(self.args, self.body())
            self.assertEqual(preview["wouldUpdateCount"], 3)
            self.assertEqual(preview["updatedCount"], 0)
            self.assertEqual(preview["newlyIgnoredCount"], 2)
            self.assertEqual(preview["alreadyIgnoredCount"], 1)
            self.assertEqual(len(preview["examples"]), 3)
            conn.execute.assert_not_called()
            audit.assert_not_called()
            self.assertTrue(cache)
            self.assertNotIn("FOR UPDATE", read.call_args.args[1])
            result = api._ignore_selected_astrometry_measurements(self.args, self.body(
                dryRun=False, expectedRevision=preview["revision"]))
            self.assertEqual(result["updatedCount"], 3)
            self.assertTrue(any("FOR UPDATE" in call.args[1] for call in read.call_args_list))
            updates = conn.execute.call_args_list
            self.assertEqual(len(updates), 3)
            self.assertEqual([call.args[1]["comments"] for call in updates],
                             ["Added note", "Existing\nAdded note", "Previous\nAdded note"])
            for call in updates:
                sql = str(call.args[0])
                self.assertIn("WHERE id = :id AND moca_oid = :oid", sql)
                self.assertNotIn("JOIN", sql)
                self.assertNotIn("adopt", sql)
                self.assertEqual(call.args[1]["oid"], 432)
            self.assertEqual(audit.call_count, 2)
            audit_rows = [call.args[2] for call in audit.call_args_list]
            self.assertEqual({(row["is_public"], row["rls"]) for row in audit_rows}, {(1, "public"), (0, "gagne")})
            self.assertEqual(sum(row["nrows_modified"] for row in audit_rows), 3)
            self.assertTrue(all("Added note" in row["user_description"] for row in audit_rows))
            self.assertFalse(cache)

    def test_blank_comments_preserve_existing_text_and_skip_already_ignored_rows(self):
        with self.database() as (_, conn, _, audit, _):
            body = self.body(appendComments="  ")
            preview = api._ignore_selected_astrometry_measurements(self.args, body)
            result = api._ignore_selected_astrometry_measurements(self.args,
                {**body, "dryRun": False, "expectedRevision": preview["revision"]})
            self.assertEqual(result["updatedCount"], 2)
            for call in conn.execute.call_args_list:
                self.assertNotIn("comments =", str(call.args[0]))
                self.assertIn(call.args[1]["id"], (1, 2))

    def test_missing_or_foreign_target_ids_abort_before_any_write(self):
        with self.database(self.rows()[:2]) as (_, conn, _, audit, _):
            with self.assertRaisesRegex(ValueError, "do not belong"):
                api._ignore_selected_astrometry_measurements(self.args, self.body(dryRun=False))
            conn.execute.assert_not_called()
            audit.assert_not_called()

    def test_stale_preview_and_changed_comment_are_rejected(self):
        with self.database() as (_, conn, read, audit, _):
            preview = api._ignore_selected_astrometry_measurements(self.args, self.body())
            changed_rows = self.rows()
            changed_rows[0]["comments"] = "Concurrent edit"
            read.side_effect = None
            read.return_value = pd.DataFrame(changed_rows)
            with self.assertRaisesRegex(ValueError, "changed since the preview"):
                api._ignore_selected_astrometry_measurements(self.args, self.body(
                    dryRun=False, expectedRevision=preview["revision"]))
            conn.execute.assert_not_called()
            audit.assert_not_called()

    def test_failed_update_rolls_back_and_does_not_clear_cache_or_log_success(self):
        with self.database() as (engine, conn, _, audit, cache):
            preview = api._ignore_selected_astrometry_measurements(self.args, self.body())
            conn.execute.side_effect = RuntimeError("simulated database failure")
            with self.assertRaises(RuntimeError):
                api._ignore_selected_astrometry_measurements(self.args, self.body(
                    dryRun=False, expectedRevision=preview["revision"]))
            self.assertIs(engine.begin.return_value.__exit__.call_args.args[0], RuntimeError)
            audit.assert_not_called()
            self.assertTrue(cache)

    def test_failed_readback_rolls_back_before_logging_success(self):
        with self.database() as (engine, conn, read, audit, cache):
            preview = api._ignore_selected_astrometry_measurements(self.args, self.body())
            read.side_effect = None
            read.return_value = pd.DataFrame(self.rows())
            with self.assertRaisesRegex(RuntimeError, "could not be verified"):
                api._ignore_selected_astrometry_measurements(self.args, self.body(
                    dryRun=False, expectedRevision=preview["revision"]))
            self.assertIs(engine.begin.return_value.__exit__.call_args.args[0], RuntimeError)
            audit.assert_not_called()
            self.assertTrue(cache)

    def test_invalid_payloads_are_rejected_before_opening_the_database(self):
        for body in (self.body(selectedIds=[]), self.body(selectedIds=[True]),
                     self.body(selectedIds=["1 OR 1=1"]), self.body(moca_oid=0),
                     self.body(appendComments="x" * 4097)):
            with self.subTest(body_keys=list(body)), patch.object(api, "_engine") as engine:
                with self.assertRaises(ValueError):
                    api._ignore_selected_astrometry_measurements(self.args, body)
                engine.assert_not_called()

    def test_endpoint_blocks_non_management_public_and_mock_requests(self):
        urls = [
            "?user=collaborators&pwd=synthetic&dbase=mocadb_private_tables",
            "?user=management&pwd=synthetic&dbase=mocadb",
            "?user=management&pwd=synthetic&dbase=mocadb_private_tables&mock=1",
            "?user=management&pwd=synthetic&dbase=mocadb_private_tables&mock=TRUE",
        ]
        with patch.object(api, "_engine") as engine:
            client = api.app.test_client()
            for query in urls:
                with self.subTest(query=query):
                    response = client.post("/api/astrometry/measurements/ignore" + query, json=self.body())
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json["updatedCount"], 0)
            engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
