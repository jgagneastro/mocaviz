"""Selection, missing-data and read-only endpoint regressions; no live database."""
import copy
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

from mocaviz import sublime_findings as sf
from mocaviz import sublime_findings_inspector as inspector


class FindingsTests(unittest.TestCase):
    def setUp(self):self.client=sf.create_app().test_client()

    def test_invalid_filters_rejected_without_opening_database(self):
        for filters in ({'sources':[]},{'sources':['not-a-table']},{'min_spt':float('nan')},
                        {'min_spt':20,'max_spt':10},{'byw':'maybe'},{'min_cnn':1.1},
                        {'min_motion':True},{'include_spiff':['good']},{'quality_any':'invented_mode'},{'unknown':'x'}):
            with self.subTest(filters=filters),patch.object(sf.sr,'connection') as conn:
                response=self.client.post('/api/findings/load',json={'filters':filters})
                self.assertEqual(response.status_code,400);conn.assert_not_called()

    def test_mock_never_authenticates_or_opens_database(self):
        with patch.object(sf.sr,'connection') as conn,patch.object(sf.sr,'credentials') as auth:
            response=self.client.post('/api/findings/load',json={'mock':True,'filters':{'min_spt':10}})
            self.assertEqual(response.status_code,200)
            data=response.get_json();self.assertTrue(data['complete'])
            self.assertEqual(data['quality_definition_version'],2)
            self.assertGreater(len(data['rows']),10)
            self.assertEqual(len(data['rows']),len({r['moca_oid'] for r in data['rows']}))
            self.assertEqual([r['spt'] for r in data['rows']],sorted([r['spt'] for r in data['rows']],reverse=True))
            conn.assert_not_called();auth.assert_not_called()

    def test_missing_credentials_rejected(self):
        self.assertEqual(self.client.post('/api/findings/load',json={'filters':{}}).status_code,403)

    def test_no_database_write_operations_exist(self):
        for operation in ('submit','classify','preview','undo','delete'):
            with patch.object(sf.sr,'connection') as conn:
                response=self.client.post('/api/findings/'+operation,json={})
                self.assertEqual(response.status_code,404);conn.assert_not_called()

    def test_default_sample_and_catalog_memberships(self):
        f=sf.parse_filters({})
        self.assertEqual(f['sources'],['other','redmovers','sublime1','sublime2'])
        self.assertEqual({key:f[key] for key in sf.TRI},{key:'either' for key in sf.TRI})

    def test_new_quality_modes_accept_mock_requests(self):
        for mode in ('one_good','all_good','all_good_candidate'):
            with self.subTest(mode=mode):
                response=self.client.post('/api/findings/load',json={'mock':True,'filters':{'quality_any':mode}})
                self.assertEqual(response.status_code,200)
                self.assertGreater(len(response.get_json()['rows']),0)

    def test_quality_modes_sql_and_rows_agree_on_available_reductions(self):
        # Quality order is SPIFF, SPIFFStacker, SUBLIME aperture. The expected
        # columns are any good/candidate, any good family, all good family,
        # and all good/candidate. Available unreviewed lanes must fail both all cuts.
        cases=[
            ((None,None,None),(),(),(False,False,False,False)),
            (('good',None,None),(0,),(),(True,True,True,True)),
            (('good','good_candidate',None),(0,1),(),(True,True,False,True)),
            (('good',None,None),(0,1),(),(True,True,False,False)),
            (('good_candidate',None,None),(0,),(),(True,False,False,True)),
            (('good','bad',None),(0,1),(),(True,True,False,False)),
            (('bad',None,None),(0,),(),(False,False,False,False)),
            (('good','bad',None),(0,),(1,),(True,True,True,True)),
            (('good','bad',None),(1,),(0,),(True,True,False,False)),
            (('good',None,None),(),(0,),(True,True,False,False)),
            (('good','good','good'),(0,1,2),(),(True,True,True,True)),
            (('good','peculiar_ucd',None),(0,1),(),(True,True,True,True)),
            (('contaminated_ucd',None,None),(0,),(),(True,True,True,True)),
            ((None,'peculiar_ucd',None),(1,),(),(True,True,True,True)),
            ((None,None,'good_plus_star'),(2,),(),(True,True,True,True)),
            (('good_candidate','contaminated_ucd',None),(0,1),(),(True,True,False,True)),
            (('contaminated_ucd',None,None),(0,1),(),(True,True,False,False)),
            (('good_reddened','weird','incomplete_but_promising'),(0,1,2),(),(False,False,False,False)),
        ]
        modes=('good','one_good','all_good','all_good_candidate')
        db=sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.execute('CREATE TABLE moca_objects (moca_oid INTEGER)')
        db.execute('CREATE TABLE moca_spectra (moca_oid INTEGER,moca_specpackid INTEGER,ignored INTEGER)')
        for cfg in sf.sr.LANES.values():db.execute('CREATE TABLE '+cfg['table']+' (moca_oid INTEGER,classification TEXT)')
        records=[]
        for oid,(quality,active,ignored,expected) in enumerate(cases,1):
            db.execute('INSERT INTO moca_objects VALUES (?)',(oid,))
            r={key:False for key in sf.TRI}
            r.update(moca_oid=oid,duplicate=False,cutout_scores=[],cutout_classes=[])
            for i,(lane,cfg) in enumerate(sf.sr.LANES.items()):
                if quality[i] is not None:
                    r[lane+'_quality']=quality[i]
                    db.execute('INSERT INTO '+cfg['table']+' VALUES (?,?)',(oid,quality[i]))
                if i in active or i in ignored:
                    db.execute('INSERT INTO moca_spectra VALUES (?,?,?)',(oid,cfg['pack'],int(i in ignored)))
                if i in active or i in ignored:
                    r[lane+'_specid']=oid*10+i
                    r[lane+'_ignored']=i in ignored
            records.append((r,expected))
        for index,mode in enumerate(modes):
            with self.subTest(mode=mode):
                expected={r['moca_oid'] for r,values in records if values[index]}
                sql='SELECT mo.moca_oid FROM moca_objects mo WHERE ('+sf.quality_condition(mode)+')'
                sql_ids={r[0] for r in db.execute(sql)}
                row_ids={r['moca_oid'] for r,_ in records if sf.passes(r,sf.parse_filters({'quality_any':mode}))}
                self.assertEqual(sql_ids,expected)
                self.assertEqual(row_ids,expected)

    def test_per_lane_good_includes_ucd_variants_but_not_candidate(self):
        for lane in sf.LANES:
            f=sf.parse_filters({'known':'either','quality_any':'any','include_'+lane:'good'})
            self.assertEqual(set(f['include_'+lane]),set(sf.GOOD_QUALITY))
            for quality in (*sf.GOOD_QUALITY,'good_candidate','bad'):
                r=sf.demo_rows(sf.parse_filters({'known':'either','quality_any':'any'}))[1]
                r[lane+'_quality']=quality
                self.assertEqual(sf.passes(r,f),quality in sf.GOOD_QUALITY)
            excluded=sf.parse_filters({'known':'either','exclude_'+lane:'good'})
            self.assertEqual(excluded['exclude_'+lane],['good'])

    def test_memberships_and_confirmed_duplicate_side(self):
        f=sf.parse_filters({'known':'either'})
        r=sf.demo_rows(f)[1]
        for key in sf.TRI:
            yes=dict(f,**{key:'yes'});no=dict(f,**{key:'no'})
            self.assertNotEqual(sf.passes(r,yes),sf.passes(r,no))
        dup=dict(r,duplicate=True)
        self.assertFalse(sf.passes(dup,dict(f,duplicates='exclude')))
        self.assertTrue(sf.passes(dup,dict(f,duplicates='only')))

    def test_missing_numeric_values_do_not_pass_enabled_cuts(self):
        f=sf.parse_filters({'known':'either'})
        r=sf.demo_rows(f)[1]
        r['motion']=None;r['spiffstacker_snr']=None;r['cutout_scores']=[]
        self.assertTrue(sf.passes(r,f))
        self.assertFalse(sf.passes(r,dict(f,min_motion=3)))
        self.assertFalse(sf.passes(r,dict(f,min_snr=1)))
        self.assertFalse(sf.passes(r,dict(f,min_cutout=1)))

    def test_known_recovered_bypasses_only_motion_quality(self):
        f=sf.parse_filters({'min_motion':2,'max_motion':4,'motion_classes':'clear motion'})
        r=sf.demo_rows(sf.parse_filters({}))[1]
        for score, motion_class in ((None,None),(1,'clear motion'),(5,'clear motion'),(3,'still')):
            with self.subTest(score=score, motion_class=motion_class):
                candidate=dict(r,known=False,motion=score,motion_class=motion_class)
                known=dict(candidate,known=True)
                self.assertFalse(sf.passes(candidate,f))
                self.assertTrue(sf.passes(known,f))
                self.assertFalse(sf.passes(known,dict(f,min_snr=1000)))

    def test_cutout_any_all_and_missing_scores(self):
        f=sf.parse_filters({'known':'either','min_cutout':4})
        r=sf.demo_rows(dict(f,min_cutout=None))[1]
        r['cutout_scores']=[4,3]
        self.assertFalse(sf.passes(r,f))
        self.assertTrue(sf.passes(r,dict(f,cutout_policy='any')))
        r['cutout_scores']=[4,None]
        self.assertFalse(sf.passes(r,f))
        self.assertTrue(sf.passes(r,dict(f,cutout_policy='any')))

    def test_review_class_none_and_exclude(self):
        f=sf.parse_filters({'known':'either','quality_any':'any','include_spiff':'none'})
        r=sf.demo_rows(dict(f,include_spiff=[]))[1]
        r['spiff_quality']=None
        self.assertTrue(sf.passes(r,f))
        self.assertFalse(sf.passes(r,dict(f,exclude_spiff=['none'])))
        r['spiff_quality']='good'
        self.assertFalse(sf.passes(r,f))

    def test_sql_values_are_parameters_and_no_row_multiplication(self):
        f=sf.parse_filters({'sources':['sublime1','sublime2'],'min_spt':10,'include_spiff':"good'); DROP TABLE x; --"})
        sql,params=sf.selected_sql(f)
        self.assertNotIn('DROP TABLE',sql)
        self.assertIn("good'); drop table x; --",params)
        self.assertIn(' UNION ',sql)
        self.assertIn('MAX(id)',sql)
        self.assertIn('mo.ignored=0',sql)
        self.assertIn('potential_duplicated_moca_oid=mo.moca_oid',sql)

    def test_absolute_magnitudes_and_nonpositive_parallax_not_invented(self):
        f=sf.parse_filters({})
        r={'moca_oid':1,'best_spt_source':'spiff','sublime1':True,'redmovers':False,'sublime2':False,
           'distance_pc':20,'distance_kind':'nonphotometric','w2':15,'synthetic_w2':16,
           'w2_unc':.1,'parallax':None}
        result=sf.photometry(MagicMock(),[r],f)[0]
        self.assertAlmostEqual(result['M_w2'],13.49485002168)
        self.assertAlmostEqual(result['M_synthetic_w2'],14.49485002168)
        self.assertIsNone(result['M_w2_unc'])
        r=copy.deepcopy(r);r.pop('distance_pc')
        self.assertIsNone(sf.photometry(MagicMock(),[r],f)[0]['M_w2'])

    def test_distance_plot_uses_adopted_values_independently_of_cmd(self):
        filters = sf.parse_filters({})
        objects = [{'moca_oid': oid, 'best_spt_source': 'spiff', 'known': False} for oid in (1, 2, 3)]
        parallaxes = [{'id': 5, 'moca_oid': 1, 'parallax_mas': 50, 'parallax_mas_unc': 1}]
        adopted = [
            {'id': 7, 'moca_oid': 1, 'distance_pc': 21, 'parallax_id': 5, 'photometric_estimate': 0},
            {'id': 8, 'moca_oid': 2, 'distance_pc': 18, 'parallax_id': None, 'photometric_estimate': 1},
        ]
        for mode in ('astrometric', 'include_photometric'):
            with self.subTest(mode=mode), patch.object(sf, 'fetch', side_effect=[parallaxes, adopted, []]):
                trig, photo, missing = sf.photometry(MagicMock(), copy.deepcopy(objects), dict(filters, distance_mode=mode))
                self.assertEqual(trig['adopted_distance_pc'], 21)
                self.assertEqual(trig['adopted_distance_kind'], 'trigonometric')
                self.assertEqual(trig['distance_pc'], 20)
                self.assertEqual(photo['adopted_distance_pc'], 18)
                self.assertEqual(photo['adopted_distance_kind'], 'photometric')
                self.assertEqual(photo.get('distance_pc'), 18 if mode == 'include_photometric' else None)
                self.assertIsNone(missing.get('adopted_distance_pc'))

    def test_body_limits_and_spectrum_identifiers(self):
        self.assertEqual(self.client.post('/api/findings/spectra',json={'mock':True,'items':[{}]*11}).status_code,400)
        self.assertEqual(self.client.post('/api/findings/spectra',json={'mock':True,'items':[{'moca_oid':1,'moca_specid':'oops'}]}).status_code,400)
        response=self.client.post('/api/findings/load',data='x'*33000,content_type='application/json')
        self.assertEqual(response.status_code,413)

    def test_cutout_paths_cannot_escape_roots(self):
        for value in ('1:../../private:0','1:1/2:3','1:NaN:0','1:400:0','1:12:-91'):
            self.assertEqual(inspector.cutout_paths(value),[])
        paths=inspector.cutout_paths('127:12.3456:-4.5678')
        self.assertTrue(paths)
        self.assertEqual(paths[0].name,'127_12.3456_-4.5678_deep_cutout.png')

    def test_no_query_credentials_or_state_in_external_surveys(self):
        with patch.object(inspector,'remote_text',return_value='') as remote:
            data=inspector.survey('2mass',12,-4,60)
            self.assertIn('irsa.ipac.caltech.edu',data['url'])
            self.assertIn('survey=2mass',data['url'])
            self.assertNotIn('user',data['url']);remote.assert_not_called()
        with self.assertRaises(ValueError):inspector.survey('bad',12,-4,60)
        with self.assertRaises(ValueError):inspector.survey('ps1',12,-4,9999)

    def test_other_unpublished_uses_classification_status_not_object_visibility(self):
        f=sf.parse_filters({'sources':['other'],'min_spt':10})
        sql,_=sf.selected_sql(f)
        self.assertNotIn('mo.is_public=0',sql)
        self.assertIn('d.public_adopted=1',sql)
        self.assertIn('d.photometric_estimate=0',sql)
        self.assertIn('dup.potential_duplicated_moca_oid=mo.moca_oid',sql)
        self.assertIn('dup.moca_oid=mo.moca_oid',sql)
        self.assertIn('mo.moca_oid NOT IN (SELECT c.moca_oid FROM `pcat_sublime_candidates`',sql)
        self.assertIn('WHERE c.moca_oid IS NOT NULL',sql)

    def test_other_requires_private_adopted_m0_and_current_spherex_type(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('''
                CREATE TABLE moca_objects(moca_oid INTEGER PRIMARY KEY, designation TEXT, ra REAL, dec REAL, ignored INT, is_public INT);
                CREATE TABLE data_spectral_types(id INTEGER PRIMARY KEY, moca_oid INT, spectral_type_number REAL,
                    adopted INT, public_adopted INT, ignored INT, photometric_estimate INT, calculation_method TEXT);
                CREATE TABLE pcat_sublime_candidates(id INT, moca_oid INT, detection_snr REAL);
                CREATE TABLE pcat_sublime_candidates_v2(id INT, moca_oid INT, detection_snr REAL, autotype_spectral_type_number REAL,
                    visual_nn_good_probability REAL, visual_nn_classification TEXT, autotype_reduced_chi2 REAL);
                CREATE TABLE pcat_catwise2020_red_movers(moca_oid INT);
                CREATE TABLE pcat_duplicated_vetting(moca_oid INT, potential_duplicated_moca_oid INT, classification TEXT);
            ''')
            db.executemany("INSERT INTO moca_objects VALUES (?, 'Fixture', 0, 0, 0, 1)", [(oid,) for oid in range(1, 10)])
            for cfg in sf.sr.LANES.values():
                db.execute('CREATE TABLE ' + cfg['table'] + '(moca_oid INT, classification TEXT)')
            db.executemany("INSERT INTO pcat_spherex_visual_vetting VALUES (?, 'good')", [(oid,) for oid in range(1, 10)])
            db.execute("INSERT INTO pcat_sublime_candidates VALUES (1, 8, 10)")
            db.executemany('INSERT INTO data_spectral_types VALUES (NULL, ?, ?, ?, ?, ?, 0, NULL)', [
                (1, 0, 1, 0, 0), (2, 12, 0, 0, 0), (3, -1, 1, 0, 0),
                (4, 11, 1, 0, 1), (5, 11, 1, 0, 0), (6, 11, 1, 0, 0),
                (7, 11, 1, 1, 0), (9, 11, 1, 0, 0),
            ])
            db.executemany('INSERT INTO data_spectral_types VALUES (NULL, ?, ?, 0, 0, ?, 0, ?)', [
                (oid, 14, int(oid == 5), 'spherex_autotype') for oid in range(1, 9)
            ])
            db.execute("INSERT INTO data_spectral_types VALUES (NULL, 6, NULL, 0, 0, 0, 0, 'spherex_autotype')")
            db.execute("INSERT INTO data_spectral_types VALUES (NULL, 9, 19, 0, 0, 0, 0, 'spherex_sublimeap_autotype')")

            def oids(**filters):
                sql, params = sf.selected_sql(sf.parse_filters({'sources':['other'], **filters}))
                return [row[0] for row in db.execute(sql.replace('%s', '?'), params)]

            self.assertEqual(oids(), [1, 9])
            self.assertEqual(oids(quality_any='any', spt_source='adopted'), [1, 9])
            self.assertEqual(oids(quality_any='any', spt_source='adopted', min_spt=10), [9])
            self.assertEqual(oids(min_spt=10, max_spt=16), [9])
            self.assertEqual(oids(sources=['other', 'sublime1']), [1, 8, 9])
            # A missing SUBLIME2 detection must not be replaced by SUBLIME1 S/N.
            db.execute('INSERT INTO pcat_sublime_candidates VALUES (100,1,88)')
            db.execute("INSERT INTO pcat_sublime_candidates_v2 VALUES (100,1,NULL,14,.9,'good',1)")
            sql,params=sf.selected_sql(sf.parse_filters({'sources':['sublime2'],'quality_any':'any'}))
            db.row_factory=sqlite3.Row
            row=db.execute(sql.replace('%s','?'),params).fetchone()
            self.assertEqual(row['detection_snr'],88)
            self.assertIsNone(row['sublime2_detection_snr'])
            db.execute('UPDATE pcat_sublime_candidates_v2 SET detection_snr=22 WHERE id=100')
            self.assertEqual(db.execute(sql.replace('%s','?'),params).fetchone()['sublime2_detection_snr'],22)

    def test_ignored_spectrum_response_keeps_raw_data_when_fit_is_impossible(self):
        spectrum=[{'wavelength_angstrom':10000,'flux_flambda':1,'flux_flambda_unc':.1,'ignored':0}]
        conn,cur=MagicMock(),MagicMock()
        with patch.object(sf.sr,'credentials',return_value={}),patch.object(sf.sr,'connection') as context, \
             patch.object(sf.sr,'spectrum_metadata',return_value={'moca_oid':1,'moca_specid':2,'ignored':1}), \
             patch.object(sf,'fetch',side_effect=[spectrum,[]]),patch.object(sf.sr,'fit_spectrum',side_effect=ValueError('Too few usable pixels')):
            context.return_value.__enter__.return_value=(conn,cur)
            response=self.client.post('/api/findings/spectra',json={'items':[{'moca_oid':1,'moca_specid':2}],'lane':'spiff'})
            self.assertEqual(response.status_code,200)
            item=response.get_json()['items'][0]
            self.assertEqual(item['object']['ignored'],1)
            self.assertEqual(item['raw_spectrum'],spectrum)
            self.assertIsNone(item['fit'])
            self.assertIn('Too few',item['warning'])
            cur.execute.assert_any_call('START TRANSACTION READ ONLY')

    def test_only_one_best_template_is_returned(self):
        response=self.client.post('/api/findings/spectra',json={'mock':True,'items':[{'moca_oid':1001,'moca_specid':11001}],'lane':'spiff'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.get_json()['items'][0]['fit']['overlays']),1)

    def test_nsc_preview_handles_namespace_and_orientation(self):
        xml="""<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE><TABLE>
        <FIELD name="preview"/><FIELD name="prodtype"/><FIELD name="obs_bandpass"/><FIELD name="date_obs"/><FIELD name="seeing"/>
        <DATA><TABLEDATA><TR><TD>https://example.org/preview.png</TD><TD>image</TD><TD>z</TD><TD>2019-01-01T00:00:00</TD><TD>1.1</TD></TR></TABLEDATA></DATA>
        </TABLE></RESOURCE></VOTABLE>"""
        with patch.object(inspector,'remote_text',return_value=xml):result=inspector.survey('nsc',12,-4,60)
        self.assertEqual(result['url'],'https://example.org/preview.png')
        self.assertTrue(result['flip_x']);self.assertFalse(result['crosshair'])
        self.assertIn('2019-01-01',result['label'])

    def test_wiseview_auxiliary_lookups_are_fixed_public_paths(self):
        response=self.client.options('/xref',headers={'Origin':'null','Access-Control-Request-Headers':'X-Requested-With'})
        self.assertEqual(response.status_code,204)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'],'*')
        with patch.object(inspector,'remote_text',return_value='[]') as remote:
            response=self.client.get('/xref?ra=12&dec=-4')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.get_json(),[])
            self.assertTrue(remote.call_args[0][0].startswith('http://byw.tools/xref?'))
        with patch.object(inspector,'remote_text') as remote:
            self.assertEqual(self.client.get('/xref?ra=12&dec=-4&url=https://other.example/').status_code,400)
            self.assertEqual(self.client.get('/xref?ra=nan&dec=-4').status_code,400)
            remote.assert_not_called()

    def test_private_headers_and_asset_allowlist(self):
        response=self.client.post('/api/findings/load',json={'mock':True})
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.headers['Referrer-Policy'],'no-referrer')
        self.assertEqual(self.client.get('/wiseview-assets/not-allowed').status_code,404)


if __name__=='__main__':unittest.main()
