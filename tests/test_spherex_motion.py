"""Transactional optional-motion tests; never connect to a real database."""
import copy
import sqlite3
import unittest
from unittest.mock import patch, MagicMock
from flask import Flask
from mocaviz import spherex_motion as motion, spherex_review as sr

AUTH = {"user": "management", "password": "synthetic-test", "database": sr.PRIVATE_DB}
HEADERS = {
    "X-MOCA-User": AUTH["user"],
    "X-MOCA-Password": AUTH["password"],
    "X-MOCA-Database": AUTH["database"],
}
OBJ = {
    "moca_oid": 1001,
    "moca_specid": 11001,
    "ra": 123.4,
    "dec": -17.5,
    "designation": "Test object",
}
BODY = {"lane": "spiffstacker", "moca_oid": 1001, "moca_specid": 11001}


class Cursor:
    def __init__(self, conn):
        self.conn = conn
        self.sql = []
        self.result = None

    def execute(self, sql, args=()):
        self.sql.append(sql)
        self.result = self.conn.execute(
            sql.replace("%s", "?").replace(" FOR UPDATE", ""), args
        )

    def fetchall(self):
        return [dict(row) for row in self.result.fetchall()]


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.cur = Cursor(self.conn)
        cols = ",".join(
            "`%s` %s"
            % (
                f,
                "INTEGER UNIQUE"
                if f == "moca_oid"
                else "REAL"
                if f in ("classification_integer", "ra_deg", "dec_deg")
                else "TEXT",
            )
            for f in motion.FIELDS
        )
        self.conn.execute(
            "CREATE TABLE "
            + motion.TABLE
            + " (id INTEGER PRIMARY KEY,"
            + cols
            + ',modified_timestamp TEXT DEFAULT "initial")'
        )
        self.conn.execute(
            "CREATE TABLE moca_changelog (`user` TEXT,modified_tables TEXT,nrows_modified INTEGER,user_description TEXT,is_public INTEGER,rls TEXT)"
        )
        self.conn.execute(
            "CREATE TABLE moca_objects (moca_oid INTEGER PRIMARY KEY,ignored INTEGER)"
        )
        self.conn.execute("INSERT INTO moca_objects VALUES (1001,0)")
        self.conn.commit()
        patcher = patch.object(sr, "spectrum_metadata", return_value=copy.deepcopy(OBJ))
        self.meta = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.conn.close)

    def preview(self, **values):
        ctx = motion.context(self.cur, BODY)
        return motion.prepare(
            self.cur,
            AUTH,
            {**BODY, "revision": ctx["revision"], "classification": "6", **values},
        )

    def save(self, **values):
        preview = self.preview(**values)
        return motion.submit(self.conn, self.cur, AUTH, {"receipt": preview["receipt"]})

    def test_context_and_preview_read_only(self):
        result = self.preview()
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["row_counts"], {motion.TABLE: 1})
        self.assertTrue(all(sql.startswith("SELECT") for sql in self.cur.sql))

    def test_insert_and_undo_touch_no_spectral_tables(self):
        result = self.save(comments="human decision")
        row = motion.snapshot(self.cur, 1001)
        self.assertEqual(row["classification_integer"], 6)
        self.assertEqual(row["classification"], "clear motion, red detection")
        self.assertIn("moca_specid=11001", row["origin"])
        self.assertIn("ra=123.4", row["wiseview_url"])
        motion.undo(self.conn, self.cur, AUTH, {"receipt": result["undo_receipt"]})
        self.assertIsNone(motion.snapshot(self.cur, 1001))
        changed = [sql for sql in self.cur.sql if not sql.startswith("SELECT")]
        self.assertTrue(
            all(motion.TABLE in sql or "moca_changelog" in sql for sql in changed)
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM moca_changelog").fetchone()[0], 2
        )

    def test_existing_needs_explicit_replace_and_undo_restores_original(self):
        self.save(comments="original")
        with self.assertRaises(sr.ReviewError):
            self.preview(classification="0")
        saved = self.save(classification="0", allow_replace=True, comments="changed")
        self.assertEqual(motion.snapshot(self.cur, 1001)["classification_integer"], 0)
        motion.undo(self.conn, self.cur, AUTH, {"receipt": saved["undo_receipt"]})
        self.assertEqual(motion.snapshot(self.cur, 1001)["comments"], "original")
        self.assertEqual(motion.snapshot(self.cur, 1001)["classification_integer"], 6)

    def test_stale_preview_and_undo_refuse_overwrite(self):
        preview = self.preview()
        saved = self.save()
        with self.assertRaises(sr.ReviewError):
            motion.submit(self.conn, self.cur, AUTH, {"receipt": preview["receipt"]})
        self.conn.execute("UPDATE " + motion.TABLE + ' SET comments="someone else"')
        self.conn.commit()
        with self.assertRaises(sr.ReviewError):
            motion.undo(self.conn, self.cur, AUTH, {"receipt": saved["undo_receipt"]})
        self.assertEqual(motion.snapshot(self.cur, 1001)["comments"], "someone else")

    def test_position_change_after_preview_blocks_save(self):
        preview = self.preview()
        self.meta.return_value["ra"] = 124.0
        with self.assertRaises(sr.ReviewError):
            motion.submit(self.conn, self.cur, AUTH, {"receipt": preview["receipt"]})
        self.assertIsNone(motion.snapshot(self.cur, 1001))

    def test_input_validation_and_target_binding(self):
        for value in ("7", None, [], {"bad": True}):
            with self.assertRaises(sr.ReviewError):
                self.preview(classification=value)
        for value in (float("nan"), float("inf"), -1):
            self.meta.return_value["ra"] = value
            with self.assertRaises(sr.ReviewError):
                self.preview()
        self.meta.return_value = copy.deepcopy(OBJ)
        self.preview()
        args = self.meta.call_args.args
        self.assertEqual(args[1:3], (11001, 1001))
        self.assertEqual(args[3], sr.LANES["spiffstacker"])
        self.meta.side_effect = sr.ReviewError("Mismatch", 404)
        with self.assertRaises(sr.ReviewError):
            self.preview()

    def test_signed_tokens_cannot_be_replayed_as_other_operation(self):
        p = self.preview()
        with self.assertRaises(sr.ReviewError):
            motion.submit(self.conn, self.cur, AUTH, {"receipt": p["receipt"] + "x"})
        with self.assertRaises(sr.ReviewError):
            motion.undo(self.conn, self.cur, AUTH, {"receipt": p["receipt"]})

    def test_route_authorization_and_mock_never_write(self):
        app = Flask(__name__)
        app.register_blueprint(sr.review)
        client = app.test_client()
        with patch.object(sr, "connection") as connect:
            for operation in ("motion-preview", "motion-submit", "motion-undo"):
                for user in ("collaborators", "public", ""):
                    result = client.post(
                        "/api/spherex-review/" + operation,
                        json={},
                        headers={**HEADERS, "X-MOCA-User": user},
                    )
                    self.assertEqual(result.status_code, 403)
                result = client.post(
                    "/api/spherex-review/" + operation,
                    json={"mock": True},
                    headers=HEADERS,
                )
                self.assertEqual(result.status_code, 403)
            connect.assert_not_called()
        response = client.post(
            "/api/spherex-review/motion-context", json={"mock": True, **BODY}
        )
        self.assertEqual(response.json["motion_policy_version"], 1)

    def test_frame_only_fixed_assets_and_anonymous_coordinates(self):
        fixture = '<head><base href="./"><script>var a="/pawnstars",b=\'/xref\';</script></head>'
        with patch(
            "mocaviz.sublime_findings_inspector.wiseview_html", return_value=fixture
        ):
            html = motion.frame_html("/js")
        self.assertIn("/js/sublime-findings/pawnstars", html)
        self.assertIn("/js/sublime-findings/xref", html)
        self.assertIn("TargetCrosshair.install", html)
        self.assertNotIn(AUTH["password"], html)
        self.assertNotIn("moca_specid", html)


if __name__ == "__main__":
    unittest.main()
