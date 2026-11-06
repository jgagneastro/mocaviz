import random
import sqlite3
import statistics
import unittest
from unittest.mock import patch

from mocaviz import spherex_queue_metrics as metrics


class PixelMetricsTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE data_spectra(moca_specid INTEGER,wavelength_angstrom REAL,flux_flambda REAL,flux_flambda_unc REAL,ignored INTEGER)')
        self.calls=[]

    def tearDown(self):self.db.close()

    def read(self,cur,sql,params):
        self.calls.append((sql,params))
        return [dict(row) for row in self.db.execute(sql.replace('%s','?'),params)]

    def test_linear_filter_matches_true_even_and_odd_medians(self):
        rng=random.Random(90210)
        values={oid:[rng.randrange(-20,80)/2 for _ in range(rng.randrange(1,24))] for oid in range(1,121)}
        values.update({121:[-1,5],122:[1,2,100],123:[1,3,3,100],124:[0,0]})
        for oid,snr in values.items():
            self.db.executemany('INSERT INTO data_spectra VALUES(?,15000,?,1,0)',[(oid,value) for value in snr])
            self.db.executemany('INSERT INTO data_spectra VALUES(?,15000,10000,?,?)',[(oid,0,0),(oid,-1,0),(oid,1,1)])
        for threshold in (0,1,2,2.5,3,7.5,15,30):
            with self.subTest(threshold=threshold),patch.object(metrics,'PIXEL_BATCH',13):
                expected={oid for oid,snr in values.items() if statistics.median(snr)>=threshold}
                actual=metrics.passing_snr(None,list(values),threshold,None,self.read)
                self.assertEqual(actual,expected)
        self.assertTrue(all('ROW_NUMBER' not in sql for sql,_ in self.calls))

    def test_page_reads_only_needed_coarse_groups_and_advances_past_cursor(self):
        candidates=[]
        for oid,subtype,snr in [(1,20,9),(2,20,5),(3,20,1),(4,19,100),(5,18,1000)]:
            self.db.execute('INSERT INTO data_spectra VALUES(?,15000,?,1,0)',(oid,snr))
            candidates.append(dict(moca_specid=oid,moca_oid=oid,sort_cnn_bin=0,sort_subtype=subtype))
        page=metrics.page(None,candidates,minimum=0,wavelength_range=None,order='cnn_spt_snr',cursor=None,limit=2,read=self.read)
        self.assertEqual([row['moca_oid'] for row in page],[1,2,3])
        self.assertTrue(all(set(params[:3])<={1,2,3} for sql,params in self.calls if 'ROW_NUMBER' in sql))
        self.calls.clear()
        cursor=dict(moca_oid=2,cnn_bin=0,spectral_subtype=20,snr_1_2=5)
        page=metrics.page(None,candidates,minimum=0,wavelength_range=None,order='cnn_spt_snr',cursor=cursor,limit=2,read=self.read)
        self.assertEqual([row['moca_oid'] for row in page],[3,4,5])

    def test_threshold_rejects_first_group_without_losing_later_groups(self):
        rows=[dict(moca_specid=oid,moca_oid=oid,sort_cnn_bin=0,sort_subtype=30-oid) for oid in range(1,5)]
        for oid,snr in [(1,0),(2,0),(3,10),(4,20)]:self.db.execute('INSERT INTO data_spectra VALUES(?,15000,?,1,0)',(oid,snr))
        page=metrics.page(None,rows,minimum=5,wavelength_range=None,order='cnn_spt_snr',cursor=None,limit=1,read=self.read)
        self.assertEqual([r['moca_oid'] for r in page],[3,4])


if __name__=='__main__':unittest.main()
