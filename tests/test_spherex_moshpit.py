"""MOSHPIT uses a candidate ID even when its OID is missing or later changes."""
import hashlib
import json
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from flask import Flask
from mocaviz import spherex_review as review


class CandidateInputTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = lambda cur, row: dict(zip((col[0] for col in cur.description), row))
        self.db.create_function("SHA2", 2, lambda s, bits: hashlib.sha256(s.encode()).hexdigest())
        self.db.executescript("""
            CREATE TABLE pcat_moshpit_candidates(id INTEGER PRIMARY KEY,source_key TEXT,origin TEXT,moca_oid INTEGER,
                ra_deg REAL,dec_deg REAL,spectral_type TEXT,selection_route TEXT,median_snr REAL,p_accept REAL,
                spectrum_json TEXT,spectral_review TEXT,review_history TEXT);
            CREATE TABLE moca_changelog(user TEXT,modified_tables TEXT,nrows_modified INTEGER,user_description TEXT,is_public INTEGER,rls TEXT);
            CREATE TABLE moca_objects(moca_oid INTEGER,designation TEXT,ignored INTEGER);
            INSERT INTO moca_objects VALUES(42,'Known L dwarf',0);
        """)
        wave = [1 + x / 8 for x in range(16)]
        product = json.dumps({"wavelength_um": wave, "flux_ujy": [-1, None] + [4 + i for i in range(14)], "error_ujy": [1] * 16})
        self.db.executemany("INSERT INTO pcat_moshpit_candidates VALUES(?,?,?, ?,20,30,'L3','catalog_first',7,.91,?,?,NULL)",
            [(1,"mp:A","moshpit/native_dr1",None,product,None), (2,"mp:B","moshpit/native_dr1",42,product,None),
             (3,"mp:C","moshpit/native_dr1",42,product,"good"), (4,"mp:D","injection",None,product,None),
             (5,"mp:E","moshpit/native_dr1",None,None,None)])
        self.db.commit()

        class Cursor:
            def execute(inner, sql, params=()):
                inner.cursor = self.db.execute(sql.replace("%s", "?").replace(" FOR UPDATE", ""), params)
            def fetchone(inner):
                return inner.cursor.fetchone()
            def fetchall(inner):
                return inner.cursor.fetchall()

        @contextmanager
        def connection(_):
            yield self.db, Cursor()
        db_patch = patch.object(review, "connection", connection)
        db_patch.start()
        self.addCleanup(db_patch.stop)
        templates = [{"moca_spherex_template_id": i, "spectral_type": name, "spectral_type_number": num, "grid_type": "field",
                      "wavelength_angstrom": w * 1e4, "flux_flambda": (k + 1 if i == 1 else 17 - k) / w**2}
                     for i, name, num in [(1,"L3",13), (2,"M6",6)] for k, w in enumerate(wave)]
        grid_patch = patch.object(review, "template_rows", return_value=templates)
        grid_patch.start()
        self.addCleanup(grid_patch.stop)
        app = Flask(__name__)
        app.register_blueprint(review.review)
        self.client = app.test_client()

    def api(self, action, payload=None, role="management"):
        return self.client.post("/api/spherex-review/" + action, json=payload or {},
            headers={"X-MOCA-User":role, "X-MOCA-Password":"unit-test", "X-MOCA-Database":review.PRIVATE_DB})

    def test_native_queue_pages_count_identity_and_units(self):
        base = {"review_sample":"moshpit", "limit":1}
        first = self.api("queue",base).get_json()
        self.assertEqual(first["items"][0]["candidate_id"],1)
        self.assertIsNone(first["items"][0]["moca_oid"])
        self.assertEqual(self.api("queue",{**base,"after":first["next_after"]}).get_json()["items"][0]["candidate_id"],2)
        self.assertEqual(self.api("queue-count",base).get_json()["total"],2)
        self.assertEqual(self.api("queue-count",{**base,"pending_only":False}).get_json()["total"],3)
        self.assertEqual(self.api("queue-count",{**base,"oid_status":"assigned"}).get_json()["total"],1)
        self.assertEqual(self.api("queue",{**base,"candidate_id":3}).get_json()["items"][0]["candidate_id"],3)
        self.assertEqual(self.api("queue",base,"collaborators").status_code,403)
        self.assertEqual(self.api("queue",{**base,"mock":True}).status_code,403)
        for cid, name in ((1, "mp:A"),(2, "Known L dwarf")):
            item = self.api("analyze", {"lane":"moshpit","candidate_id":cid}).get_json()
            self.assertTrue(item["ok"], item)
            self.assertEqual(item["object"]["designation"],name)
            self.assertIsNone(item["object"]["moca_specid"])
            self.assertEqual(item["fit"]["fit_version"], "native_signed_student4_v1")
            self.assertEqual(len(item["raw_spectrum"]), 15)
            self.assertAlmostEqual(item["raw_spectrum"][0]["flux_flambda"] / -2.99792458e-22, 1)
            self.assertEqual(item["raw_spectrum"][0]["ignored"],0)

    def test_candidate_review_conflict_and_undo_preserve_oid_and_other_history(self):
        base = {"lane":"moshpit","candidate_id":1}
        item = self.api("analyze", base).get_json()
        body = {**base,"action":"classify","classification":"good_candidate","revision":item["revision"],
                "data_revision":item["data_revision"]}
        preview = self.api("preview",body).get_json()
        self.assertEqual(preview["row_counts"],{"pcat_moshpit_candidates":1})
        self.assertEqual(self.api("preview",{**body,"action":"upsert_spt"}).status_code,400)
        self.db.execute("UPDATE pcat_moshpit_candidates SET moca_oid=42 WHERE id=1")
        submitted = self.api("submit",{"receipt":preview["receipt"]}).get_json()
        self.assertTrue(submitted["submitted"])
        self.assertEqual(self.api("submit",{"receipt":preview["receipt"]}).status_code,409)
        history = json.loads(self.db.execute("SELECT review_history FROM pcat_moshpit_candidates WHERE id=1").fetchone()["review_history"])
        history.append({"id":"independent","lane":"cutout","label":"good"})
        self.db.execute("UPDATE pcat_moshpit_candidates SET review_history=? WHERE id=1",(json.dumps(history),))
        self.assertTrue(self.api("undo",{"receipt":submitted["undo_receipt"]}).get_json()["undone"])
        row = self.db.execute("SELECT * FROM pcat_moshpit_candidates WHERE id=1").fetchone()
        self.assertIsNone(row["spectral_review"])
        self.assertEqual(row["moca_oid"],42)
        self.assertEqual([v["lane"] for v in json.loads(row["review_history"])],["spectral","cutout","spectral"])
        self.assertEqual(self.api("undo",{"receipt":submitted["undo_receipt"]}).status_code,409)
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM moca_changelog").fetchone()["n"],2)
