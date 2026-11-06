"""Catalog joins, protected-source cuts and union identity regression tests."""
import sqlite3
import unittest
from mocaviz import sublime_findings as sf
from mocaviz import sublime_findings_completeness as c

class KnownSourceTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript('''
        CREATE TABLE moca_objects(moca_oid INTEGER PRIMARY KEY,designation TEXT,ra REAL,dec REAL,ignored INT,is_public INT);
        CREATE TABLE data_spectral_types(id INTEGER PRIMARY KEY,moca_oid INT,spectral_type_number REAL,adopted INT,public_adopted INT,ignored INT,photometric_estimate INT,calculation_method TEXT);
        CREATE TABLE pcat_sublime_candidates(id INT,moca_oid INT,detection_snr REAL);
        CREATE TABLE pcat_sublime_candidates_v2(id INT,moca_oid INT,detection_snr REAL,autotype_spectral_type_number REAL,visual_nn_good_probability REAL,visual_nn_classification TEXT,autotype_reduced_chi2 REAL);
        CREATE TABLE pcat_catwise2020_red_movers(moca_oid INT);
        CREATE TABLE pcat_duplicated_vetting(moca_oid INT,potential_duplicated_moca_oid INT,classification TEXT);
        CREATE TABLE pcat_wiseview_visual_vetting(moca_oid INT,classification_integer REAL);
        CREATE TABLE mechanics_all_designations(moca_oid INT,designation TEXT);
        CREATE TABLE moca_spectra(moca_oid INT,moca_specpackid INT,ignored INT);
        ''')
        for table in ('pcat_byw_mar9_2026','pcat_schneider_claim_list_byw','pcat_kirkpatrick_yadu_2026_claim','pcat_azul_byw_sample_jul16_2026'):
            self.db.execute('CREATE TABLE '+table+'(moca_oid INT)')
        for cfg in sf.sr.LANES.values():self.db.execute('CREATE TABLE '+cfg['table']+'(moca_oid INT PRIMARY KEY,classification TEXT)')
        for oid in range(1,6):
            self.db.execute("INSERT INTO moca_objects VALUES (?,'Fixture',0,0,0,1)",(oid,))
            self.db.execute('INSERT INTO pcat_sublime_candidates VALUES (?,?,NULL)',(oid,oid))
            self.db.execute('INSERT INTO pcat_sublime_candidates_v2 VALUES (?,?,NULL,NULL,NULL,NULL,NULL)',(oid,oid))
        # 1: published spectroscopy, 2: photometric known, 3: claimed, 4: new, 5: ignored published type.
        for oid,public,photo,ignored in [(1,1,0,0),(2,1,1,0),(3,0,0,0),(4,0,0,0),(5,1,0,1)]:
            self.db.execute('INSERT INTO data_spectral_types VALUES (NULL,?,25,1,?,?,?,NULL)',(oid,public,ignored,photo))
        self.db.execute('INSERT INTO pcat_schneider_claim_list_byw VALUES (3)')

    def select(self,**kwargs):
        f=sf.parse_filters(dict(sources=['sublime1','sublime2'],min_spt=10,**kwargs))
        sql,params=sf.selected_sql(f)
        return [dict(r) for r in self.db.execute(sql.replace('%s','?'),params)]

    def test_catalog_join_needs_no_spectrum_motion_or_cutout(self):
        rows=self.select(min_motion=6,include_spiff='good',min_detection_snr=999,min_cnn=.99,max_chi2=.1)
        self.assertEqual([r['moca_oid'] for r in rows],[1,2,3])
        self.assertEqual(rows[1]['published_candidate_spt'],25)
        for source in ['sublime1','sublime2']:
            self.assertTrue(all(r[source] for r in rows))
        # Type-only selection still preserves a new object; ignored published values never seed a known source.
        self.assertEqual([r['moca_oid'] for r in self.select(quality_any='any')],[1,2,3,4])

    def test_published_type_does_not_require_a_literature_method_or_spectrum(self):
        self.db.execute("UPDATE data_spectral_types SET calculation_method='published_custom_method' WHERE moca_oid=1")
        rows=self.select()
        self.assertIn(1,[r['moca_oid'] for r in rows])

    def test_switches_reinstate_sql_cuts_independently(self):
        cases=[dict(apply_known_quality=True),dict(apply_known_motion=True,min_motion=1),
               dict(apply_known_detection=True,min_detection_snr=1),dict(apply_known_detection=True,min_cnn=.5),
               dict(apply_known_detection=True,cnn_classes='good'),dict(apply_known_chi2=True,max_chi2=3),
               dict(apply_known_spiff=True,include_spiff='good')]
        for cuts in cases:
            with self.subTest(cuts=cuts):self.assertEqual(self.select(**cuts),[])

    def test_multiple_published_rows_and_catalogs_do_not_multiply_objects(self):
        self.db.execute('INSERT INTO data_spectral_types VALUES (NULL,1,26,0,1,0,0,NULL)')
        self.db.execute('INSERT INTO pcat_sublime_candidates_v2 VALUES (99,1,NULL,NULL,NULL,NULL,NULL)')
        rows=self.select();self.assertEqual([r['moca_oid'] for r in rows],[1,2,3])
        self.assertEqual(rows[0]['published_spt'],26)

    def test_runtime_exemptions_and_population_filters(self):
        for membership in ['known','known_candidate','byw','byw_claim','yadu','azul','smdet']:
            row=dict(moca_oid=1,duplicate=False,cutout_scores=[],cutout_classes=[],**{membership:True})
            f=sf.parse_filters(dict(min_motion=5,min_snr=10,min_cutout=4,include_spiff='good'))
            with self.subTest(membership=membership):
                self.assertTrue(sf.passes(row,f))
                for group in ['quality','motion','snr','cutout','spiff']:
                    self.assertFalse(sf.passes(row,dict(f,**{sf.QUALITY_SWITCHES[group]:True})))
                self.assertFalse(sf.passes(row,dict(f,**{membership:'no'})))
        self.assertFalse(sf.passes(dict(row,duplicate=True),f))

    def test_census_keeps_quality_switches_but_restores_known_populations(self):
        f=sf.parse_filters(dict(known='no',known_candidate='no',byw='no',min_spt=25,max_spt=29,
                                min_motion=5,apply_known_motion=True))
        cfilters=c.census_filters(f)
        self.assertEqual(cfilters['min_motion'],5)
        self.assertTrue(cfilters['apply_known_motion'])
        self.assertTrue(all(cfilters[k]=='either' for k in sf.TRI))
        self.assertEqual(cfilters['min_spt'],10);self.assertIsNone(cfilters['max_spt'])
        response=sf.create_app().test_client().post('/api/findings/completeness',json={'mock':True,'filters':{'sources':['sublime1','sublime2'],'known':'no','known_candidate':'no'}})
        self.assertEqual(response.status_code,200)
        self.assertGreater(sum(r['known'] for r in response.get_json()['summaries']['union']['bins']),0)

    def test_cache_depth_conversion_and_newest_measurement(self):
        # m=15 and sigma_m=(2.5/ln10)/10 implies S/N=10, hence depth=16.3072.
        data=[dict(moca_oid=1,system_band_simple='J',magnitude=15,magnitude_unc=(2.5/__import__('math').log(10))/10),
              dict(moca_oid=1,system_band_simple='j',magnitude=99,magnitude_unc=1)]
        result=c.depth_summary(data)
        self.assertEqual(result['j']['n'],1);self.assertAlmostEqual(result['j']['median'],16.30719686)
        self.assertEqual(result['w2']['n'],0)

    def test_census_union_bin_boundaries_and_zero_count_limits(self):
        rows=[dict(moca_oid=1,spt=10.99,sublime1=True,sublime2=True,known=True),
              dict(moca_oid=2,spt=11,sublime2=True,known_candidate=True)]
        result=c.summarize(rows+[rows[0]],['sublime1','sublime2'])
        self.assertEqual(result['union']['total'],2)
        self.assertEqual([r['n'] for r in result['union']['bins'][:2]],[1,1])
        self.assertEqual(result['sublime1']['total'],1);self.assertEqual(result['sublime2']['total'],2)
        self.assertEqual(c.count_interval(0)[0],0);self.assertGreater(c.count_interval(0)[1],1)

if __name__=='__main__':unittest.main()
