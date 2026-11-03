"""Selection, missing-data and read-only endpoint regressions; no live database."""
import copy
import unittest
from unittest.mock import patch, MagicMock

from mocaviz import sublime_findings as sf
from mocaviz import sublime_findings_inspector as inspector


class FindingsTests(unittest.TestCase):
    def setUp(self):self.client=sf.create_app().test_client()

    def test_invalid_filters_rejected_without_opening_database(self):
        for filters in ({'sources':[]},{'sources':['not-a-table']},{'min_spt':float('nan')},
                        {'min_spt':20,'max_spt':10},{'byw':'maybe'},{'min_cnn':1.1},
                        {'min_motion':True},{'include_spiff':['good']},{'unknown':'x'}):
            with self.subTest(filters=filters),patch.object(sf.sr,'connection') as conn:
                response=self.client.post('/api/findings/load',json={'filters':filters})
                self.assertEqual(response.status_code,400);conn.assert_not_called()

    def test_mock_never_authenticates_or_opens_database(self):
        with patch.object(sf.sr,'connection') as conn,patch.object(sf.sr,'credentials') as auth:
            response=self.client.post('/api/findings/load',json={'mock':True,'filters':{'min_spt':10}})
            self.assertEqual(response.status_code,200)
            data=response.get_json();self.assertTrue(data['complete'])
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

    def test_spectrum_response_keeps_raw_data_when_fit_is_impossible(self):
        spectrum=[{'wavelength_angstrom':10000,'flux_flambda':1,'flux_flambda_unc':.1,'ignored':0}]
        conn,cur=MagicMock(),MagicMock()
        with patch.object(sf.sr,'credentials',return_value={}),patch.object(sf.sr,'connection') as context, \
             patch.object(sf.sr,'spectrum_metadata',return_value={'moca_oid':1,'moca_specid':2,'ignored':0}), \
             patch.object(sf,'fetch',side_effect=[spectrum,[]]),patch.object(sf.sr,'fit_spectrum',side_effect=ValueError('Too few usable pixels')):
            context.return_value.__enter__.return_value=(conn,cur)
            response=self.client.post('/api/findings/spectra',json={'items':[{'moca_oid':1,'moca_specid':2}],'lane':'spiff'})
            self.assertEqual(response.status_code,200)
            item=response.get_json()['items'][0]
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

    def test_private_headers_and_asset_allowlist(self):
        response=self.client.post('/api/findings/load',json={'mock':True})
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.headers['Referrer-Policy'],'no-referrer')
        self.assertEqual(self.client.get('/wiseview-assets/not-allowed').status_code,404)


if __name__=='__main__':unittest.main()
