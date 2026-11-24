"""Focused regression for source priority, classification tiers and type cuts."""
import itertools
import sqlite3
import unittest
from mocaviz import sublime_findings as sf


class TypePriorityTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE moca_objects(moca_oid INTEGER PRIMARY KEY,designation TEXT,ra REAL,dec REAL,ignored INT,is_public INT);
            CREATE TABLE data_spectral_types(id INTEGER PRIMARY KEY,moca_oid INT,spectral_type_number REAL,adopted INT,
                public_adopted INT,ignored INT,photometric_estimate INT,calculation_method TEXT,moca_specid INT,origin TEXT,created_timestamp TEXT);
            CREATE TABLE moca_spectra(moca_specid INTEGER PRIMARY KEY,moca_oid INT,moca_specpackid INT,created_timestamp TEXT);
            CREATE TABLE pcat_spherex_spectrum_reviews(moca_specid INT,classification TEXT,review_kind TEXT);
            CREATE INDEX reviews_by_id ON pcat_spherex_spectrum_reviews(moca_specid);
            CREATE INDEX type_by_oid ON data_spectral_types(moca_oid);
            CREATE TABLE pcat_sublime_candidates(id INT,moca_oid INT,detection_snr REAL);
            CREATE TABLE pcat_sublime_candidates_v2(id INT,moca_oid INT,detection_snr REAL,autotype_spectral_type_number REAL,
                visual_nn_good_probability REAL,visual_nn_classification TEXT,autotype_reduced_chi2 REAL);
            CREATE TABLE pcat_sublime_candidates_v3c(id INT,moca_oid INT,ra_deg REAL,dec_deg REAL,
                autotype_spectral_type_number REAL,status TEXT,cnn_acceptance_probability REAL,median_raw_snr REAL);
            CREATE TABLE pcat_catwise2020_red_movers(moca_oid INT);
            CREATE TABLE pcat_duplicated_vetting(moca_oid INT,potential_duplicated_moca_oid INT,classification TEXT);
        """)
        for cfg in sf.LANE_CONFIG.values():
            self.db.execute("CREATE TABLE "+cfg["table"]+"(moca_oid INT PRIMARY KEY,classification TEXT)")

            self.db.execute(f"""CREATE TRIGGER review_{cfg['pack']} AFTER INSERT ON {cfg['table']} BEGIN
                INSERT INTO pcat_spherex_spectrum_reviews VALUES(NEW.moca_oid*1000+{cfg['pack']},NEW.classification,'quality'); END""")

    def add_object(self,oid):
        self.db.execute("INSERT INTO moca_objects VALUES (?,'Fixture',0,0,0,0)",(oid,))
        self.db.execute("INSERT INTO pcat_sublime_candidates VALUES (?,?,10)",(oid,oid))

    def add_type(self,oid,spt,*,lane=None,adopted=0,public=0,photo=0,ignored=0):
        method=sf.sr.LANES[lane]["methods"][0] if lane else None
        specid=None
        if lane:
            pack=sf.LANE_CONFIG[lane]['pack'];specid=oid*1000+pack
            self.db.execute('INSERT OR IGNORE INTO moca_spectra (moca_specid,moca_oid,moca_specpackid) VALUES(?,?,?)',(specid,oid,pack))
        self.db.execute("INSERT INTO data_spectral_types (id,moca_oid,spectral_type_number,adopted,public_adopted,ignored,photometric_estimate,calculation_method,moca_specid) VALUES (NULL,?,?,?,?,?,?,?,?)",
                        (oid,spt,adopted,public,ignored,photo,method,specid))

    def select(self,**cuts):
        filters=sf.parse_filters({"sources":["sublime1"],"quality_any":"any",**cuts})
        sql,values=sf.selected_sql(filters)
        return {r["moca_oid"]:dict(r) for r in self.db.execute(sql.replace("%s","?"),values)}

    def test_all_classification_pairs_and_three_way_ties(self):
        priority=("spiffstacker","spiff","sublimeaperture")
        ranks={"good":0,"peculiar_ucd":0,"late_M":3,"contaminated_ucd":1,"good_plus_star":1,
               "good_candidate":2,"incomplete_but_promising":3,"weird":3,"bad":4,None:4}
        expected={}
        oid=0
        for classes in itertools.product(ranks,repeat=3):
            oid+=1
            self.add_object(oid)
            for i,lane in enumerate(priority):
                self.add_type(oid,10+i,lane=lane)
                if classes[i] is not None:
                    self.db.execute("INSERT INTO "+sf.sr.LANES[lane]["table"]+" VALUES (?,?)",(oid,classes[i]))
            best=min(range(3),key=lambda i:(ranks[classes[i]],i))
            expected[oid]=(10+best,priority[best]) if ranks[classes[best]]<4 else (None,None)
        rows=self.select()
        self.assertEqual({oid:(r["spt"],r["best_spt_source"]) for oid,r in rows.items()},expected)

    def test_legacy_autotype_requires_one_contemporaneous_reviewed_spectrum(self):
        for oid in range(1,8):
            self.add_object(oid)
            self.db.execute("INSERT INTO moca_spectra VALUES (?,?,62,'2026-10-01')",(oid*1000+62,oid))
            self.db.execute("INSERT INTO pcat_spherex_spiffstacker_visual_vetting VALUES (?,?)",
                            (oid,'bad' if oid==6 else 'good'))
            self.db.execute("""INSERT INTO data_spectral_types
                (moca_oid,spectral_type_number,adopted,public_adopted,ignored,photometric_estimate,
                 calculation_method,origin,created_timestamp)
                VALUES (?,17,0,0,0,0,'spiff_stacker_autotype',?,?)""",
                (oid,'another_tool.py' if oid==5 else 'spherex_autotype.py',
                 '2026-09-01' if oid==3 else '2026-10-02'))
        # Two same-lane spectra make the legacy type ambiguous even if one was rejected.
        self.db.execute("INSERT INTO moca_spectra VALUES (9999,2,62,'2026-09-01')")
        self.db.execute("INSERT INTO pcat_spherex_spectrum_reviews VALUES (9999,'bad','quality')")
        self.add_type(4,8,lane='spiffstacker')
        self.add_type(7,14,lane='spiff')
        self.db.execute("INSERT INTO pcat_spherex_visual_vetting VALUES (7,'good_candidate')")
        rows=self.select()
        self.assertEqual((rows[1]['spt'],rows[1]['best_spt_source']),(17,'spiffstacker'))
        self.assertEqual({oid:rows[oid]['spt'] for oid in (2,3,4,5,6)},
                         {2:None,3:None,4:8,5:None,6:None})
        self.assertEqual((rows[7]['spt'],rows[7]['best_spt_source']),(14,'spiff'))
        self.assertEqual(set(self.select(min_spt=10)),{1,7})
        self.assertEqual(set(self.select(min_spt=10,spt_source='spiffstacker')),{1,7})

    def test_preferred_spectrum_uses_ranked_type_and_available_literature_fallback(self):
        spectra = {lane+'_specid':i+1 for i,lane in enumerate(sf.TYPE_LANE_ORDER)}
        for classes,expected in [
            (('weird','good_candidate','good'),'sublimeaperture'),
            (('good_candidate','good','weird'),'spiff'),
            (('good','peculiar_ucd','late_M'),'spiffstacker'),
            ((None,None,None),'spiffstacker'),
            (('bad','incomplete_but_promising','weird'),'spiff'),
        ]:
            row = {**spectra,'best_spt_source':'published',
                   **{lane+'_quality':value for lane,value in zip(sf.TYPE_LANE_ORDER,classes)}}
            with self.subTest(classes=classes):
                self.assertEqual(sf.preferred_spectrum_lane(row),expected)
        row = {**spectra,'best_spt_source':'sublimeaperture',
               'spiff_quality':'good','sublimeaperture_quality':'good_candidate'}
        self.assertEqual(sf.preferred_spectrum_lane(row),'sublimeaperture')
        row['sublimeaperture_specid'] = None
        self.assertEqual(sf.preferred_spectrum_lane(row),'spiff')
        self.assertIsNone(sf.preferred_spectrum_lane({'best_spt_source':'adopted'}))

    def test_missing_ignored_null_and_no_sublime_catalog_fallback(self):
        for oid in range(1,5):self.add_object(oid)
        self.add_type(1,23,lane="spiffstacker",ignored=1)
        self.add_type(1,10,lane="sublimeaperture")
        self.add_type(2,None,lane="spiffstacker")
        self.add_type(2,15,lane="spiff")
        self.db.execute("INSERT INTO pcat_sublime_candidates_v2 VALUES (3,3,10,29,.9,'good',1)")
        self.add_type(4,20,lane="spiffstacker")
        self.add_type(4,10,lane="sublimeaperture")
        self.db.execute("INSERT INTO pcat_spherex_sublimeaperture_visual_vetting VALUES (4,'good_candidate')")
        rows=self.select()
        self.assertEqual((rows[1]["spt"],rows[1]["best_spt_source"]),(None,None))
        self.assertEqual((rows[2]["spt"],rows[2]["best_spt_source"]),(None,None))
        self.assertEqual((rows[3]["spt"],rows[3]["best_spt_source"]),(None,None))
        self.assertEqual((rows[4]["spt"],rows[4]["best_spt_source"]),(10,"sublimeaperture"))
        self.assertNotIn(4,self.select(min_spt=15))
        self.assertIn(4,self.select(max_spt=12))

    def test_literature_adopted_then_public_then_lane_and_minimum_superset(self):
        for oid in range(1,5):self.add_object(oid)
        self.add_type(1,13,adopted=1)
        self.add_type(1,21,public=1)
        self.add_type(1,28,lane="spiffstacker")
        self.add_type(2,8,adopted=1,photo=1)
        self.add_type(2,19,public=1)
        self.add_type(2,28,lane="spiff")
        self.add_type(3,24,lane="spiffstacker",adopted=1)
        self.add_type(3,10,lane="sublimeaperture")
        self.db.execute("INSERT INTO pcat_spherex_spiffstacker_visual_vetting VALUES (3,'weird')")
        self.db.execute("INSERT INTO pcat_spherex_sublimeaperture_visual_vetting VALUES (3,'good_candidate')")
        self.add_type(4,18,adopted=1)
        rows=self.select()
        self.assertEqual((rows[1]["spt"],rows[1]["best_spt_source"]),(13,"adopted"))
        self.assertEqual((rows[2]["spt"],rows[2]["best_spt_source"]),(19,"published"))
        self.assertEqual((rows[3]["spt"],rows[3]["best_spt_source"]),(10,"sublimeaperture"))
        self.assertIn(4,self.select(min_spt=17))
        self.assertNotIn(1,self.select(min_spt=17))

if __name__=="__main__":unittest.main()
