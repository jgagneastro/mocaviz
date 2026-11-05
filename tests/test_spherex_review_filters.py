"""Execute queue SQL on scientific edge cases without a database or review writes."""
import re
import sqlite3
import unittest
from unittest.mock import MagicMock
from mocaviz import spherex_review as sr


class FilterSelectionTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        def regex_substr(text, pattern):
            match = re.search(pattern.replace('[[:space:]]', r'\s'), text or '')
            return match.group() if match else ''
        def substring_index(text, delimiter, count):
            parts = (text or '').split(delimiter)
            return delimiter.join(parts[:count] if count > 0 else parts[count:])
        self.db.create_function('REGEXP_SUBSTR', 2, regex_substr)
        self.db.create_function('SUBSTRING_INDEX', 3, substring_index)
        self.db.executescript('''
            CREATE TABLE moca_objects(moca_oid INTEGER PRIMARY KEY,ignored INTEGER,designation TEXT);
            CREATE TABLE moca_spectra(moca_specid INTEGER PRIMARY KEY,moca_oid INTEGER,moca_specpackid INTEGER,ignored INTEGER,median_snr_per_pix REAL);
            CREATE TABLE data_spectra(moca_specid INTEGER,wavelength_angstrom REAL,flux_flambda REAL,flux_flambda_unc REAL,ignored INTEGER);
            CREATE TABLE data_spectral_types(id INTEGER PRIMARY KEY,moca_oid INTEGER,moca_specid INTEGER,calculation_method TEXT,comments TEXT,ignored INTEGER,adopted INTEGER,public_adopted INTEGER,photometric_estimate INTEGER,spectral_type_number REAL,is_public INTEGER DEFAULT 0);
            CREATE TABLE pcat_sublime_candidates_v2(moca_oid INTEGER,detection_snr REAL,visual_nn_good_probability REAL);
            CREATE TABLE pcat_sublime_candidates(moca_oid INTEGER);
            CREATE TABLE pcat_catwise2020_red_movers(moca_oid INTEGER);
            CREATE TABLE calc_galactic_coordinates(moca_oid INTEGER,adopt_as_reference INTEGER,gb REAL);
            CREATE TABLE pcat_wiseview_visual_vetting(moca_oid INTEGER,classification_integer REAL);
            CREATE TABLE pcat_duplicated_vetting(moca_oid INTEGER,potential_duplicated_moca_oid INTEGER,classification TEXT);
        ''')
        for lane in sr.LANES.values():
            self.db.execute('CREATE TABLE '+lane['table']+'(moca_oid INTEGER,classification TEXT)')
        for oid, spt in enumerate([20,10,20,None,15,25,15,5],1):
            self.db.execute('INSERT INTO moca_objects VALUES(?,?,?)',(oid,int(oid==8),'Object '+str(oid)))
            self.db.execute('INSERT INTO moca_spectra VALUES(?,?,62,0,999)',(100+oid,oid))
            self.db.execute('INSERT INTO data_spectra VALUES(?,15000,?,1,0)',(100+oid,1 if oid==2 else 3))
            self.db.execute('INSERT INTO data_spectral_types(id,moca_oid,moca_specid,calculation_method,comments,ignored,adopted,public_adopted,photometric_estimate,spectral_type_number) VALUES(?,?,?, ?,?,0,1,?, ?,?)',
                            (oid,oid,100+oid,'literature' if oid==7 else 'spiff_stacker_autotype',
                             'robust_reduced_chi2_10pct_cap=1.5; reduced_chi2=20;',int(oid in (5,6)),int(oid==6),spt))
            self.db.execute('INSERT INTO calc_galactic_coordinates VALUES(?,1,?)',(oid,-15 if oid==2 else 15))
        self.db.executemany('INSERT INTO pcat_sublime_candidates_v2 VALUES(?,?,?)',
                            [(1,7,.8),(1,1,.99),(2,6.9,.9),(3,9,.79),(4,20,.99),(5,9,.9)])
        self.db.executemany('INSERT INTO pcat_sublime_candidates VALUES(?)',[(2,),(3,),(6,)])
        self.db.executemany('INSERT INTO pcat_catwise2020_red_movers VALUES(?)',[(1,),(1,),(4,),(7,)])
        self.db.executemany('INSERT INTO pcat_wiseview_visual_vetting VALUES(?,?)',[(1,0),(2,None),(3,-1),(5,5)])
        self.db.executemany('INSERT INTO pcat_duplicated_vetting VALUES(?,?,?)',[(1,6,'y'),(2,7,'n')])
        self.db.execute('UPDATE calc_galactic_coordinates SET gb=14.9 WHERE moca_oid=3')
        self.db.execute('UPDATE calc_galactic_coordinates SET gb=NULL WHERE moca_oid=4')
        self.db.execute('UPDATE calc_galactic_coordinates SET adopt_as_reference=0 WHERE moca_oid=5')
        class Cursor:
            def execute(inner,sql,params): inner.current=self.db.execute(sql.replace('%s','?'),params)
            def fetchall(inner): return [dict(row) for row in inner.current.fetchall()]
        self.cur=Cursor()

    def tearDown(self): self.db.close()
    def queue(self, **cuts): return sr.queue(self.cur, {'lane':'spiffstacker',**cuts})
    def oids(self, **cuts): return [r['moca_oid'] for r in self.queue(**cuts)['items']]

    def test_samples_use_membership_without_duplicate_rows(self):
        self.assertEqual(self.oids(review_sample='sublime2'),[1,2,3,4,5])
        self.assertEqual(self.oids(review_sample='sublime1'),[2,3,6])
        self.assertEqual(self.oids(review_sample='catwiseredmovers'),[1,4,7])
        self.assertEqual(self.oids(review_sample='public-ucd'),[6])

    def test_detection_and_cnn_are_separate_from_spectrum_snr(self):
        self.assertEqual(self.oids(min_sublime2_snr=7,min_cnn_probability=.8),[1,4,5])
        self.assertEqual(self.oids(min_sublime2_snr=7,min_cnn_probability=.9),[4,5])
        self.assertEqual(self.oids(min_snr=2),[1,3,4,5,6,7])  # stored median is deliberately 999

    def test_galactic_latitude_requires_private_reference_and_absolute_value(self):
        self.assertEqual(self.oids(min_abs_galactic_latitude=15),[1,2,6,7])
        self.assertEqual(self.oids(min_abs_galactic_latitude=15.1),[])

    def test_unscored_accepts_null_but_never_zero_or_negative_scores(self):
        self.assertEqual(self.oids(no_wiseview_score=True),[2,4,6,7])
        self.assertEqual(self.oids(min_wiseview_score=0),[1,5])
        with self.assertRaises(sr.ReviewError):self.queue(no_wiseview_score=True,min_wiseview_score=0)

    def test_duplicate_target_column_and_only_yes_judgments(self):
        self.assertEqual(self.oids(exclude_duplicates=True),[1,2,3,4,5,7])
        self.assertIn(6,self.oids(exclude_duplicates=False))

    def test_published_auto_types_are_known_but_unpublished_auto_types_remain(self):
        self.assertEqual(self.oids(no_known=True),[1,2,3,4,6])
        self.db.execute('UPDATE data_spectral_types SET is_public=1 WHERE moca_oid=3')
        self.assertNotIn(3,self.oids(no_known=True))  # published but not public-adopted
        self.db.execute('UPDATE data_spectral_types SET ignored=1 WHERE moca_oid=5')
        self.assertIn(5,self.oids(no_known=True))

    def test_snr_bands_even_median_signed_flux_and_invalid_pixels(self):
        self.db.execute('DELETE FROM data_spectra WHERE moca_specid=101')
        self.db.executemany('INSERT INTO data_spectra VALUES(101,?,?,?,?)',[
            (10000,-1,1,0),(20000,5,1,0),(30000,10,1,0),(45000,20,1,0),
            (15000,1000,1,1),(15000,1000,0,0),(15000,1000,-1,0),
            (None,1000,1,0),(-1,1000,1,0),(15000,None,1,0)])
        self.assertEqual(self.oids(moca_oids=[1],min_snr=7.5),[1])
        self.assertEqual(self.oids(moca_oids=[1],min_snr=7.6),[])
        for band,minimum,expected in [('1-2.5',2,[1]),('1-2.5',2.1,[]),('2.5-4',10,[1]),('4-5',20,[1]),('1-5',7.5,[1])]:
            self.assertEqual(self.oids(moca_oids=[1],min_snr=minimum,snr_wavelength_range=band),expected)
        self.assertEqual(self.oids(moca_oids=[2],min_snr=0,snr_wavelength_range='4-5'),[])

    def test_chi2_uses_latest_exact_spectrum_and_metric_priority(self):
        self.assertEqual(self.oids(moca_oids=[1],max_reduced_chi2=1.5),[1])
        self.assertEqual(self.oids(moca_oids=[1],max_reduced_chi2=1.49),[])
        self.db.execute("INSERT INTO data_spectral_types VALUES(100,1,101,'spiff_stacker_autotype','reduced_chi2=2;',0,0,0,0,20,0)")
        self.assertEqual(self.oids(moca_oids=[1],max_reduced_chi2=1.5),[])
        self.db.execute("UPDATE data_spectral_types SET comments='robust_reduced_chi2_10pct_cap=NULL; reduced_chi2_10pct_cap=1.2e0; reduced_chi2=10;' WHERE id=100")
        self.assertEqual(self.oids(moca_oids=[1],max_reduced_chi2=1.5),[1])
        self.db.execute("UPDATE data_spectral_types SET moca_specid=9999 WHERE id IN (1,100)")
        self.assertEqual(self.oids(moca_oids=[1],max_reduced_chi2=1.5),[])

    def test_malformed_or_missing_chi2_never_becomes_zero(self):
        for value in ['not_reduced_chi2=0;', 'reduced_chi2=oops;', 'reduced_chi2=NULL;',
                      'reduced_chi2=nan;', 'reduced_chi2=-1;', 'reduced_chi2=0garbage;', None]:
            self.db.execute('UPDATE data_spectral_types SET comments=? WHERE id=1',(value,))
            self.assertEqual(self.oids(moca_oids=[1],max_reduced_chi2=1.5),[],value)
        self.db.execute("UPDATE data_spectral_types SET comments='reduced_chi2=.5;' WHERE id=1")
        self.assertEqual(self.oids(moca_oids=[1],max_reduced_chi2=1.5),[1])

    def test_all_orders_ties_nulls_and_cursor_page_without_offset(self):
        for order,expected in [('spt_desc',[6,1,3,5,7,2,4]),('spt_asc',[2,5,7,1,3,6,4]),
                               ('oid_desc',[7,6,5,4,3,2,1]),('oid_asc',[1,2,3,4,5,6,7])]:
            with self.subTest(order=order):
                after=0;actual=[]
                while True:
                    page=self.queue(queue_order=order,after=after,limit=2)
                    actual.extend(row['moca_oid'] for row in page['items'])
                    if not page['has_more']:break
                    after=page['next_after']
                self.assertEqual(actual,expected)
        first=self.queue(queue_order='spt_desc',limit=2)
        self.db.execute("INSERT INTO pcat_spherex_spiffstacker_visual_vetting VALUES(6,'good')")
        self.assertEqual(self.oids(queue_order='spt_desc',after=first['next_after']),[3,5,7,2,4])
        self.assertEqual(self.oids(queue_order='spt_desc',after={'moca_oid':4,'spectral_type_number':None}),[])

    def test_count_uses_all_cuts_but_ignores_pagination(self):
        cuts=dict(review_sample='sublime2',min_sublime2_snr=7,min_cnn_probability=.8,
                  min_abs_galactic_latitude=15,min_snr=2,max_reduced_chi2=1.5,
                  exclude_duplicates=True,no_wiseview_score=False,queue_order='spt_desc')
        self.assertEqual(self.oids(**cuts),[1])
        self.assertEqual(sr.queue(self.cur,{**cuts,'after':{'moca_oid':1,'spectral_type_number':20},'limit':1},count_only=True),{'total':1})
        self.assertEqual(self.oids(**{**cuts,'no_wiseview_score':True}),[])

    def test_catalog_cuts_combine_with_viable_elsewhere_and_total(self):
        self.db.execute("INSERT INTO pcat_spherex_visual_vetting VALUES(1,'good')")
        cuts=dict(missing_vetting='viable_elsewhere',review_sample='sublime2',min_sublime2_snr=7,
                  min_cnn_probability=.8,min_abs_galactic_latitude=15,min_snr=2,
                  max_reduced_chi2=1.5,exclude_duplicates=True,queue_order='spt_desc')
        self.assertEqual(self.oids(**cuts),[1])
        self.assertEqual(sr.queue(self.cur,cuts,count_only=True),{'total':1})

    def test_invalid_inputs_rejected_before_database_execution(self):
        invalid=[{'review_sample':[]},{'review_sample':'unsafe'},{'snr_wavelength_range':[]},
                 {'snr_wavelength_range':'0-100'},{'queue_order':'spt; DROP'},
                 {'queue_order':'spt_desc','after':123},{'no_wiseview_score':'yes'},
                 {'exclude_duplicates':[]},{'min_cnn_probability':1.01},{'min_abs_galactic_latitude':91}]
        invalid += [{key:value} for key in ('min_snr','min_sublime2_snr','min_cnn_probability','min_abs_galactic_latitude','max_reduced_chi2')
                    for value in (True,'nan','1 OR 1=1',-1)]
        for cuts in invalid:
            with self.subTest(cuts=cuts):
                cur=MagicMock()
                with self.assertRaises(sr.ReviewError):sr.queue(cur,cuts)
                cur.execute.assert_not_called()

if __name__=='__main__':unittest.main()
