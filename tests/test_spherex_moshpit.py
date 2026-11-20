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
        import zlib
        self.db.create_function("COMPRESS", 1, lambda s: len(s).to_bytes(4, "little")+zlib.compress(s.encode()))
        self.db.create_function("JSON_VALUE", 2, lambda s,k: json.loads(s).get(k[2:]))
        self.db.executescript("""
            CREATE TABLE pcat_moshpit_candidates(id INTEGER PRIMARY KEY,source_key TEXT,origin TEXT,moca_oid INTEGER,
                ra_deg REAL,dec_deg REAL,spectral_type TEXT,selection_route TEXT,median_snr REAL,p_accept REAL,
                spectrum_json TEXT,spectral_review TEXT,review_history TEXT);
            CREATE TABLE moca_changelog(user TEXT,modified_tables TEXT,nrows_modified INTEGER,user_description TEXT,is_public INTEGER,rls TEXT);
            CREATE TABLE moca_objects(moca_oid INTEGER,designation TEXT,ignored INTEGER);
            INSERT INTO moca_objects VALUES(42,'Known L dwarf',0);
            CREATE TABLE data_spectral_types(id INTEGER,moca_oid INTEGER,spectral_type TEXT,complete_spectral_type TEXT,moca_pid TEXT,origin TEXT,adopted INTEGER,public_adopted INTEGER,ignored INTEGER,spectral_type_number REAL,photometric_estimate INTEGER,is_public INTEGER,calculation_method TEXT);
            INSERT INTO data_spectral_types VALUES(1,42,'L3','L3','Ref1','test',1,0,0,13,0,1,NULL);
            CREATE TABLE moca_spherex_templates(moca_spherex_template_id INTEGER,spectral_type_number REAL,spectral_type TEXT);
            INSERT INTO moca_spherex_templates VALUES(1,13,'L3');
            CREATE TABLE pcat_sublime_candidates_v2(moca_oid INTEGER,detection_snr REAL,visual_nn_good_probability REAL);
            INSERT INTO pcat_sublime_candidates_v2 VALUES(42,9,.7);
            CREATE TABLE pcat_wiseview_visual_vetting(id INTEGER,moca_oid INTEGER,classification TEXT,classification_integer REAL,comments TEXT,reviewer TEXT,ra_deg REAL,dec_deg REAL,wiseview_url TEXT,source_table TEXT,origin TEXT,modified_timestamp TEXT);
            INSERT INTO pcat_wiseview_visual_vetting(id,moca_oid,classification_integer) VALUES(1,42,5);
            CREATE TABLE pcat_duplicated_vetting(potential_duplicated_moca_oid INTEGER,classification TEXT);
            CREATE TABLE pcat_spherex_visual_vetting(moca_oid INTEGER,classification TEXT);
            CREATE TABLE pcat_spherex_spiffstacker_visual_vetting(moca_oid INTEGER,classification TEXT);
            CREATE TABLE pcat_spherex_sublimeaperture_visual_vetting(moca_oid INTEGER,classification TEXT);
            INSERT INTO pcat_spherex_spiffstacker_visual_vetting VALUES(42,'good');
        """)
        wave = [1 + x / 8 for x in range(16)]
        product = json.dumps({"wavelength_um": wave, "flux_ujy": [-1, None] + [4 + i for i in range(14)], "error_ujy": [1] * 16, "template_id":1, "template_ujy":[-1,None]+[4+i for i in range(14)]})
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

    def test_shared_filters_and_all_orders(self):
        base = {"lane":"moshpit","missing_vetting":"all","limit":1}
        for order in sorted(review.metrics.PRIORITY_ORDERS | {"oid_asc","oid_desc","spt_asc","spt_desc"}):
            q = dict(base, queue_order=order)
            ids = []
            while True:
                page = self.api("queue",q).get_json()
                self.assertTrue(page["ok"],page)
                ids.extend(r["candidate_id"] for r in page["items"])
                if not page["has_more"]:
                    break
                q["after"] = page["next_after"]
            self.assertEqual(sorted(ids), [1,2,3])
            if order in ("oid_asc","oid_desc","spt_asc","spt_desc"):
                self.assertEqual(ids, [2,3,1])
        for opts, expected in [
            ({"min_sptn":10},2), ({"adopted_spt_source":"public","min_sptn":10},0),
            ({"adopted_spt_source":"survey","min_sptn":10},3),
            ({"min_spectral_cnn_probability":.95},0), ({"moca_oids":[42]},2),
            ({"adopted_spt_moca_pids":["Ref1"]},2), ({"no_known":True},1),
            ({"no_wiseview_score":True},1), ({"min_wiseview_score":5},2),
            ({"exclude_duplicates":True},3), ({"vetting_classification":"good"},1),
            ({"missing_vetting":"both"},1), ({"missing_vetting":"viable_elsewhere"},1),
            ({"min_abs_galactic_latitude":88},0),
            ({"snr_wavelength_range":"4-5","min_snr":0},0),
            ({"snr_wavelength_range":"1-2.5","max_snr":0},0),
            ({"min_snr":3,"max_snr":20,"snr_wavelength_range":"1-2.5"},3),
            ({"max_reduced_chi2":1},3), ({"min_sublime2_snr":8,"min_cnn_probability":.5},2),
        ]:
            with self.subTest(opts=opts):
                q = {**base, **opts, "queue_order":"snr_bin_spt","limit":10}
                self.assertEqual(self.api("queue-count",q).get_json()["total"],expected)
                self.assertEqual(len(self.api("queue",q).get_json()["items"]),expected)
        bypass = {**base,"candidate_id":1,"min_snr":10000,"oid_status":"assigned"}
        self.assertEqual(self.api("queue",bypass).get_json()["items"][0]["candidate_id"],1)

    def test_motion_requires_current_oid_and_uses_candidate_position(self):
        base = {"lane":"moshpit","candidate_id":2,"moca_oid":42}
        context = self.api("motion-context",base).get_json()
        self.assertEqual(context["object"]["ra"],20)
        self.assertIsNone(context["object"]["moca_specid"])
        body = {**base,"classification":context["choices"][0]["key"],"revision":context["revision"],"allow_replace":True}
        plan = self.api("motion-preview", body).get_json()["plan"]
        self.assertEqual(plan["row"]["source_table"],"pcat_moshpit_candidates")
        self.assertEqual(plan["object"]["candidate_id"],2)
        self.assertEqual(self.api("motion-context",{**base,"moca_oid":24}).status_code,409)
        unlinked = {"lane":"moshpit","candidate_id":1,"moca_oid":None}
        preview = self.api("motion-context", unlinked).get_json()
        self.assertEqual(preview["object"]["dec"],30)
        self.assertEqual(self.api("motion-preview",{**body,**unlinked,"revision":preview["revision"]}).status_code,409)
