"""Any-lane pending-spectrum counters; SQLite fixtures, no live database."""
import sqlite3
import unittest
from types import SimpleNamespace
from unittest import mock
from mocaviz.wiseview_review import runtime as server


class PendingSpectrumCounts(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
          CREATE TABLE moca_objects(moca_oid INT,ignored INT);
          CREATE TABLE pcat_sublime_candidates_v2(moca_oid INT);
          CREATE TABLE pcat_catwise2020_red_movers(moca_oid INT);
          CREATE TABLE pcat_wiseview_visual_vetting(moca_oid INT,classification_integer REAL);
          CREATE TABLE pcat_duplicated_vetting(potential_duplicated_moca_oid INT,classification TEXT);
        ''')
        for table,_,_ in server.spectral_vetting.LANES.values():
            self.db.execute('CREATE TABLE '+table+'(moca_oid INT,classification TEXT)')
        class Cursor:
            def execute(inner,sql,params=()):inner.result=self.db.execute(sql.replace('%s','?'),params)
            def fetchall(inner):return [dict(row) for row in inner.result]
        self.cur=Cursor()

    def tearDown(self):self.db.close()

    def object(self,oid,*,ignored=0,sample='pcat_sublime_candidates_v2'):
        self.db.execute('INSERT INTO moca_objects VALUES (?,?)',(oid,ignored))
        self.db.execute('INSERT INTO '+sample+' VALUES (?)',(oid,))

    def review(self,oid,quality,lane='spiff'):
        table=server.spectral_vetting.LANES[lane][0]
        self.db.execute('INSERT INTO '+table+' VALUES (?,?)',(oid,quality))

    def counts(self,sample='pcat_sublime_candidates_v2',known=(),claimed=()):
        return server.summarize_pending_spectra(server.pending_spectral_rows(self.cur,sample),set(known),set(claimed))

    def test_every_requested_quality_in_each_lane_and_inclusive_candidate_count(self):
        oid=0
        for lane in server.spectral_vetting.LANES:
            for quality in (*server.PENDING_CANDIDATE_CLASSES,'bad','weird',None):
                oid+=1;self.object(oid);self.review(oid,quality,lane)
        self.assertEqual(self.counts(),{'pending_good_spectra':15,'pending_candidate_spectra':18})

    def test_deduplication_new_exclusions_and_any_motion_review(self):
        for oid in range(1,19):self.object(oid,ignored=int(oid==9))
        self.db.execute('INSERT INTO pcat_sublime_candidates_v2 VALUES (1)')
        for oid,quality in [(1,'good'),(2,'good_candidate'),(3,'good_reddened'),(4,'peculiar_ucd'),
                            (5,'contaminated_ucd'),(6,'good_plus_star'),(7,'good'),(8,'good'),
                            (9,'good'),(10,'good'),(11,'good'),(12,'good'),(13,'good'),
                            (14,'good'),(15,'bad'),(17,None),(18,' GOOD_CANDIDATE ')]:self.review(oid,quality)
        self.review(1,'bad','spiffstacker');self.review(1,'good_candidate','sublimeaperture')
        self.db.execute('INSERT INTO pcat_duplicated_vetting VALUES (10,\'y\')')
        self.db.executemany('INSERT INTO pcat_wiseview_visual_vetting VALUES (?,?)',[(11,0),(12,-1),(13,None)])
        self.db.execute('DELETE FROM pcat_sublime_candidates_v2 WHERE moca_oid IN (14,16)')
        self.db.execute('INSERT INTO pcat_catwise2020_red_movers VALUES (16)');self.review(16,'good')
        self.assertEqual(self.counts(known={7},claimed={8}),{'pending_good_spectra':5,'pending_candidate_spectra':7})
        self.db.execute('INSERT INTO pcat_wiseview_visual_vetting VALUES (3,6)')
        self.assertEqual(self.counts(known={7},claimed={8}),{'pending_good_spectra':4,'pending_candidate_spectra':6})
        self.assertEqual(self.counts(server.REDMOVER_SOURCE),{'pending_good_spectra':1,'pending_candidate_spectra':1})
        with self.assertRaises(ValueError):server.pending_spectral_rows(self.cur,'untrusted_table')

    def test_any_saved_motion_value_excludes_a_good_spectrum(self):
        for oid,value in enumerate([None,-1,0,1,1.5,2,3,4,5,6],start=1):
            self.object(oid);self.review(oid,'good','sublimeaperture')
            self.db.execute('INSERT INTO pcat_wiseview_visual_vetting VALUES (?,?)',(oid,value))
        self.assertEqual(self.counts(),{'pending_good_spectra':0,'pending_candidate_spectra':0})

    def test_stats_scope_known_checks_to_pending_objects_without_a_type_cut(self):
        cur=mock.MagicMock();cur.fetchone.return_value={'total':10,'classified':0,'rejected':0};cur.fetchall.return_value=[]
        conn=mock.MagicMock();conn.cursor.return_value.__enter__.return_value=cur
        aut=SimpleNamespace(fetch_known_nonphotometric_late_type_oids=mock.Mock(return_value=set()),fetch_claimed_oids=mock.Mock(return_value={3}))
        pending=[{'moca_oid':2,'spectral_class':'good_reddened'},{'moca_oid':3,'spectral_class':'good_candidate'}]
        with mock.patch.dict(server.STATS_CACHE,{'entries':{},'generation':0},clear=True), \
             mock.patch.object(server.review,'_connect_db',return_value=conn) as connect, \
             mock.patch.object(server.review,'_autotype_review',return_value=aut), \
             mock.patch.object(server,'pending_spectral_rows',side_effect=[pending,[]]) as fetch:
            result=server.sublime_stats()
            self.assertEqual((result['pending_good_spectra'],result['pending_candidate_spectra']),(1,1))
            aut.fetch_known_nonphotometric_late_type_oids.assert_called_once_with(source_oids={2,3})
            self.assertEqual(server.sublime_stats(),result);self.assertEqual(connect.call_count,1)
            server.invalidate_sublime_stats()
            result=server.sublime_stats()
            self.assertEqual((result['pending_good_spectra'],result['pending_candidate_spectra']),(0,0))
            self.assertEqual(fetch.call_count,2)

    def test_catwise_counts_use_the_same_sample_and_any_spectral_lane(self):
        cur=mock.MagicMock();cur.fetchall.return_value=[]
        conn=mock.MagicMock();conn.cursor.return_value.__enter__.return_value=cur
        aut=SimpleNamespace(fetch_known_nonphotometric_late_type_oids=mock.Mock(return_value=set()),fetch_claimed_oids=mock.Mock(return_value=set()))
        with mock.patch.dict(server.STATS_CACHE,{'entries':{},'generation':0},clear=True), \
             mock.patch.dict(server.RED_SAMPLE_CACHE,{},clear=True), \
             mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server.review,'_autotype_review',return_value=aut), \
             mock.patch.object(server,'redmover_oids',return_value={16}), \
             mock.patch.object(server,'fetch_duplicate_oids',return_value=set()), \
             mock.patch.object(server,'pending_spectral_rows',return_value=[{'moca_oid':16,'spectral_class':'good'}, {'moca_oid':17,'spectral_class':'good'}]):
            result=server.redmover_stats('spiffstacker')
            self.assertEqual((result['pending_good_spectra'],result['pending_candidate_spectra']),(1,1))
            aut.fetch_known_nonphotometric_late_type_oids.assert_called_once_with(source_oids={16})


if __name__=='__main__':unittest.main()
