"""Exercise real queue SQL, morphology association and metadata without writes."""
import re
import unittest
from unittest.mock import MagicMock
import test_spherex_review_filters as base_filters
from mocaviz import spherex_review as sr
from mocaviz import spherex_morphology as psf


class MorphologyTests(unittest.TestCase):
    def setUp(self):
        base_filters.FilterSelectionTests.setUp(self)
        self.db.create_function("CONCAT", -1, lambda *args: "".join(map(str, args)))
        for definition in ("spectrum_name TEXT", "data_reduction_pipeline TEXT"):
            self.db.execute("ALTER TABLE moca_spectra ADD COLUMN " + definition)
        self.db.execute("""CREATE TABLE pcat_sublime_candidates_v3c(
            id INTEGER PRIMARY KEY,moca_oid INTEGER,source_key TEXT,status TEXT,
            psf_morphology_status TEXT,psf_point_source_pass INTEGER,
            psf_morphology_version TEXT,psf_morphology_json TEXT)""")
        states = [("pass",1),("fail",0),("undetermined",None),(None,None),("pass",None),("fail",0),("unknown",1)]
        for oid,(status,flag) in enumerate(states,1):
            self.db.execute("INSERT INTO pcat_sublime_candidates_v3c VALUES(?,?,?,?,?,?,?,?)",
                (oid,oid,"s3c:1:"+str(oid),sr.SUBLIME3C_SELECTION_PREFIX,status,flag,"shape_v1",'{"bands":{"deep":{"status":"fail","reason":"elongated"}}}'))
            self.db.execute("UPDATE moca_spectra SET moca_specpackid=76,spectrum_name=?,data_reduction_pipeline=? WHERE moca_oid=?",
                ("SUBLIME3C_s3c_1_"+str(oid)+"_DR1_cube",psf.PIPELINE,oid))
            self.db.execute("INSERT INTO moca_spectra VALUES(?,?,62,0,5,NULL,NULL)",(200+oid,oid))
        # A different passing detection must not rescue the selected failed one.
        self.db.execute("INSERT INTO pcat_sublime_candidates_v3c VALUES(9,6,'s3c:2:6',?,'pass',1,'shape_v1',NULL)",(sr.SUBLIME3C_SELECTION_PREFIX,))
        self.db.execute("INSERT INTO moca_spectra VALUES(96,6,76,0,5,'SUBLIME3C_s3c_2_6_DR1_cube',?)",(psf.PIPELINE,))
        # OID membership alone is insufficient: the exact detection is missing.
        self.db.execute("UPDATE moca_spectra SET spectrum_name='unmatched' WHERE moca_specid=107")
        self.db.execute("ALTER TABLE pcat_sublime_candidates_v3c ADD COLUMN visual_nn_classification TEXT")
        self.db.execute("ALTER TABLE pcat_sublime_candidates_v3c ADD COLUMN visual_nn_good_probability REAL")
        outer=self
        class Cursor:
            def execute(self,sql,params):
                sql=sql.replace('%s','?')
                sql=re.sub(r'LEFT\(([\w.]+),\?\)',r'SUBSTR(\1,1,?)',sql)
                self.current=outer.db.execute(sql,params)
            def fetchall(self): return [dict(row) for row in self.current.fetchall()]
        self.cur=Cursor()

    def tearDown(self): self.db.close()

    def body(self, mode="all", **kwargs):
        return dict(lane="sublimeaperture",review_sample="sublime3c",missing_vetting="all",
                    cnn_priority_source="sublime2",sublime3c_psf_morphology=mode,**kwargs)

    def oids(self,mode="all",**kwargs):
        return [row['moca_oid'] for row in sr.queue(self.cur,self.body(mode,**kwargs))['items']]

    def test_categories_partition_queue_and_count_without_writes(self):
        before=self.db.total_changes
        groups={"all":[1,2,3,4,5,6,6,7],"pass":[1,6],"fail":[2,6],"undefined":[3,4,5,7],"not_pass":[2,3,4,5,6,7]}
        for mode,expected in groups.items():
            self.assertEqual(self.oids(mode),expected)
            self.assertEqual(sr.queue(self.cur,self.body(mode),count_only=True),{"total":len(expected)})
        self.assertEqual(before,self.db.total_changes)

    def test_pagination_snr_and_sorted_queues_apply_same_filter(self):
        for order in ("oid_asc","spt_desc","cnn_spt_snr"):
            body=self.body("not_pass",limit=2,queue_order=order,min_snr=0)
            all_rows=[]
            while True:
                page=sr.queue(self.cur,body);all_rows.extend(page['items'])
                if not page['has_more']:break
                body['after']=page['next_after']
            self.assertEqual(sorted(x['moca_oid'] for x in all_rows),[2,3,4,5,6,7])

    def test_displayed_flag_and_filter_use_same_exact_native_detection(self):
        for oid,status in [(1,"pass"),(2,"fail"),(3,"undefined"),(4,"undefined"),(5,"undefined"),(6,"fail"),(7,"undefined")]:
            info=psf.metadata(self.cur,100+oid,sr.rows)
            self.assertEqual(info['status'],status)
            self.assertEqual(info['scope'],"This native cube detection")
        old=psf.metadata(self.cur,96,sr.rows)
        self.assertEqual(old['status'],'pass')
        self.assertEqual(old['candidate_id'],9)
        self.assertEqual(psf.metadata(self.cur,102,sr.rows)['bands']['deep']['reason'],'elongated')

    def test_other_lanes_use_latest_active_native_detection(self):
        body={**self.body('pass'), 'lane':'spiffstacker'}
        self.assertEqual([x['moca_oid'] for x in sr.queue(self.cur,body)['items']],[1])
        self.assertEqual(psf.metadata(self.cur,206,sr.rows)['status'],'fail')
        self.db.execute('UPDATE moca_spectra SET ignored=1 WHERE moca_specid=106')
        info=psf.metadata(self.cur,206,sr.rows)
        self.assertEqual(info['status'],'pass')
        self.assertEqual(info['candidate_id'],9)

    def test_spectral_and_shape_pass_must_belong_to_same_detection(self):
        self.db.execute("UPDATE pcat_sublime_candidates_v3c SET status='AUTO_SELECTION_FAIL' WHERE id=1")
        self.db.execute("INSERT INTO pcat_sublime_candidates_v3c VALUES(10,1,'s3c:2:1',?,'fail',0,'shape_v1',NULL,NULL,NULL)",(sr.SUBLIME3C_SELECTION_PREFIX,))
        self.assertEqual(self.oids('pass'),[1,6])
        self.assertEqual(self.oids('pass',sublime3c_selection_pass_only=True),[6])

    def test_invalid_modes_fail_before_database_and_other_samples_unaffected(self):
        for value in (None,True,[],{},"bad","pass' OR 1=1"):
            cur=MagicMock()
            with self.assertRaises(sr.ReviewError):sr.queue(cur,self.body(value))
            cur.execute.assert_not_called()
        body={**self.body('pass'),'review_sample':'all'}
        self.assertEqual(sr.queue(self.cur,body),sr.queue(self.cur,{**body,'sublime3c_psf_morphology':'all'}))

    def test_malformed_details_and_unknown_states_stay_undefined(self):
        self.db.execute("UPDATE pcat_sublime_candidates_v3c SET psf_morphology_json='broken' WHERE id=4")
        info=psf.metadata(self.cur,104,sr.rows)
        self.assertEqual(info['status'],'undefined');self.assertEqual(info['bands'],{})
        self.db.execute("UPDATE pcat_sublime_candidates_v3c SET psf_morphology_status='unexpected',psf_point_source_pass=1 WHERE id=1")
        self.assertEqual(self.oids('pass'),[6])
        self.assertEqual(psf.metadata(self.cur,101,sr.rows)['status'],'undefined')
