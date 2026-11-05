import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from mocaviz import sublime_findings as sf
from mocaviz import sublime_findings_diagnostics as diag


class DiagnosticsTests(unittest.TestCase):
    def test_snr_mean_median_boundaries_masking_and_missing_values(self):
        pairs=[(.9,9),(1,2),(2,4),(2.49,100),(2.5,8),(3.9,10),(4,12),(5,14),(5.1,16),(1.3,-3)]
        points=[dict(wavelength_angstrom=w*10000,flux_flambda=v,flux_flambda_unc=1) for w,v in pairs]
        for extra in [dict(ignored=1),dict(flux_flambda_unc=0),dict(flux_flambda_unc=-1),dict(flux_flambda=None),
                      dict(wavelength_angstrom=float('nan')),dict(flux_flambda=float('inf'))]:
            points.append({**points[1],**extra})
        result=diag.summarize(points)
        self.assertEqual(result['all'],{'mean':17.2,'median':9.5,'count':10})
        self.assertEqual(result['nir'],{'mean':25.75,'median':3,'count':4})
        self.assertEqual(result['mid'],{'mean':9,'median':9,'count':2})
        self.assertEqual(result['red'],{'mean':13,'median':13,'count':2})
        self.assertTrue(all(row=={'mean':None,'median':None,'count':0} for row in diag.summarize([]).values()))

    def test_exact_sidecar_identity_and_probability_validation(self):
        item={'moca_oid':10,'moca_specid':25,'lane':'spiffstacker'}
        payload={'schema':'spherex_autotype_result','schema_version':1,
                 'source':{'moca_oid':10,'moca_specid':25,'moca_specpackid':62},
                 'generator':{'calculation_method':'spiff_stacker_autotype'},
                 'best_match':{'display_reduced_chi2':1.25,'reduced_chi2':7},'cnn':{'probabilities':{'good':0}}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(diag,'candidate_directories',return_value=[Path(tmp)]):
            path=Path(tmp)/'spherex_autotype_moca_oid_10.json'
            path.write_text(json.dumps(payload));self.assertEqual(diag.sidecar_metrics(item)['cnn'],0)
            self.assertEqual(diag.sidecar_metrics(item)['chi2'],1.25)
            for key,value in [('moca_oid',11),('moca_specid',26),('moca_specpackid',55)]:
                changed=json.loads(json.dumps(payload));changed['source'][key]=value;path.write_text(json.dumps(changed))
                self.assertIsNone(diag.sidecar_metrics(item)['chi2'])
            payload['cnn']['probabilities']['good']=1.1;path.write_text(json.dumps(payload))
            self.assertIsNone(diag.sidecar_metrics(item)['cnn'])

    def test_chi2_fields_use_exact_names_and_valid_fallbacks(self):
        self.assertEqual(diag.comment_chi2('red_chi2_10pct=99; reduced_chi2=4; robust_reduced_chi2_10pct_cap=2'),2)
        self.assertEqual(diag.comment_chi2('reduced_chi2=3; robust_reduced_chi2_10pct_cap=NULL'),3)
        self.assertIsNone(diag.comment_chi2('red_reduced_chi2=4; reduced_chi2=nan'))

    def test_bulk_query_only_uses_active_matching_spectra(self):
        db=sqlite3.connect(':memory:');self.addCleanup(db.close);db.row_factory=sqlite3.Row
        db.executescript('''CREATE TABLE moca_objects(moca_oid INT,ignored INT);
            CREATE TABLE moca_spectra(moca_specid INT,moca_oid INT,moca_specpackid INT,ignored INT);
            CREATE TABLE data_spectra(moca_specid INT,wavelength_angstrom REAL,flux_flambda REAL,flux_flambda_unc REAL,ignored INT);
            CREATE TABLE data_spectral_types(id INT,moca_specid INT,calculation_method TEXT,comments TEXT,ignored INT);''')
        db.executemany('INSERT INTO moca_objects VALUES (?,?)',[(1,0),(2,1)])
        db.executemany('INSERT INTO moca_spectra VALUES (?,?,?,?)',[(10,1,62,0),(11,1,55,1),(12,2,55,0)])
        db.executemany('INSERT INTO data_spectra VALUES (?,?,?,?,?)',[(10,15000,8,2,0),(10,15000,1000,1,1)])
        db.executemany('INSERT INTO data_spectral_types VALUES (?,?,?,?,?)',[(1,10,'spherex_autotype','reduced_chi2=100',0),(2,10,'spiff_stacker_autotype','reduced_chi2=2',0)])
        class Cursor:
            def execute(self,sql,params):self.result=db.execute(sql.replace('%s','?'),params)
            def fetchall(self):return [dict(r) for r in self.result.fetchall()]
        with patch.object(diag,'sidecar_metrics',return_value={'chi2':None,'cnn':None,'fit_source':None,'cnn_source':None}):
            result=diag.load(Cursor(),[{'moca_oid':1,'moca_specid':10,'lane':'spiffstacker'},
                {'moca_oid':1,'moca_specid':10,'lane':'spiff'},{'moca_oid':1,'moca_specid':11,'lane':'spiff'},
                {'moca_oid':2,'moca_specid':12,'lane':'spiff'}])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['snr']['all']['mean'],4)
        self.assertEqual(result[0]['chi2'],2)

    def test_mock_endpoint_and_invalid_batches_never_open_database(self):
        client=sf.create_app().test_client()
        with patch.object(sf.sr,'connection') as connection,patch.object(sf.sr,'credentials') as auth:
            response=client.post('/api/findings/diagnostics',json={'mock':True,'items':[{'moca_oid':1,'moca_specid':10,'lane':'spiff'}]})
            self.assertEqual(response.status_code,200)
            self.assertGreater(response.get_json()['items'][0]['snr']['all']['count'],0)
            for items in [None,[{}],[{}]*97,[{'moca_oid':True,'moca_specid':10,'lane':'spiff'}]]:
                self.assertEqual(client.post('/api/findings/diagnostics',json={'items':items}).status_code,400)
            connection.assert_not_called();auth.assert_not_called()
