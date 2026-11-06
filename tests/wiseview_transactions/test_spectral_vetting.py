import copy
import threading
import unittest
from types import SimpleNamespace
from unittest import mock
from mocaviz.wiseview_review import runtime as server


BEFORE={'vetting':None,'types':[{'id':90,'ignored':0}],
        'spectra':[{'moca_specid':100,'ignored':0}]}
AFTER={'vetting':{'classification':'bad','sources':'web'},'types':[{'id':90,'ignored':1}],
       'spectra':[{'moca_specid':100,'ignored':1}]}
MOTION={'classification':'clear motion, red detection','classification_integer':6.0}


class Cursor:
    def __init__(self,fail_motion=False):self.ops=[];self.fail_motion=fail_motion
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,values=()):
        self.ops.append((sql,values))
        if self.fail_motion and 'INSERT INTO pcat_wiseview_visual_vetting' in sql:
            raise RuntimeError('motion write failed')
    def fetchone(self):return {'moca_oid':4}


class Conn:
    def __init__(self,fail_motion=False):self.cur=Cursor(fail_motion);self.commits=0;self.rollbacks=0
    def cursor(self):return self.cur
    def commit(self):self.commits+=1
    def rollback(self):self.rollbacks+=1
    def close(self):pass


def session():
    return {'mode':'sublime','lock':threading.RLock(),'state':'ready','oids':[4],
        'object_cache':{},'fit_cache':{},'snapshots':{4:None},
        'spectral_snapshots':{4:{'spiffstacker':None}},'undo':[],
        'args':SimpleNamespace(reclass=False,reviewer='Gagne',source_table='pcat_sublime_candidates_v2')}


class TestSpectralVetting(unittest.TestCase):
    def test_oversized_undo_receipt_rolls_back_before_commit(self):
        state=session();conn=Conn();state['validate_undo']=mock.Mock(side_effect=ValueError('receipt too large'))
        with mock.patch.object(server,'get_object',return_value=(4,SimpleNamespace(ra_deg=12.,dec_deg=8.))), \
             mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',side_effect=[None,MOTION]):
            with self.assertRaisesRegex(ValueError,'receipt too large'):
                server.save_decision(state,0,'6','')
        self.assertEqual((conn.commits,conn.rollbacks),(0,1))
        self.assertEqual(state['undo'],[])

    def multi_state(self):
        state=session();lanes=list(server.spectral_vetting.LANES)
        state['spectral_snapshots'][4]={lane:None for lane in lanes}
        choices=[{'lane':lane,'classification':'bad' if i==1 else 'good','specid':100+i}
                 for i,lane in enumerate(lanes)]
        before=[{'vetting':None,'types':[{'id':90+i,'ignored':0}],
                 'spectra':[{'moca_specid':100+i,'ignored':0}]} for i in range(3)]
        after=copy.deepcopy(before)
        for i,choice in enumerate(choices):
            after[i]['vetting']={'classification':choice['classification'],'sources':'web'}
            if i==1:after[i]['types'][0]['ignored']=after[i]['spectra'][0]['ignored']=1
        return state,choices,before,after

    def test_three_lane_save_and_undo_are_one_transaction_each(self):
        state,choices,before,after=self.multi_state();save,undo=Conn(),Conn()
        with mock.patch.object(server,'get_object',return_value=(4,SimpleNamespace(ra_deg=12.,dec_deg=8.))), \
             mock.patch.object(server.review,'_connect_db',side_effect=[save,undo]), \
             mock.patch.object(server,'snapshot',side_effect=[None,MOTION,MOTION,None]), \
             mock.patch.object(server.spectral_vetting,'snapshot',side_effect=before+after+after), \
             mock.patch.object(server,'invalidate_sublime_stats'):
            result=server.save_decision(state,0,'6','',spectral_reviews=choices)
            self.assertEqual(result['spectral_saved_reviews'],choices)
            self.assertEqual(len(state['undo'][0]['spectral_reviews']),3)
            server.undo_decision(state)
        for lane in server.spectral_vetting.LANES:
            table=server.spectral_vetting.LANES[lane][0]
            self.assertTrue(any('INSERT INTO `'+table+'`' in sql for sql,_ in save.cur.ops))
            self.assertTrue(any('DELETE FROM `'+table+'`' in sql for sql,_ in undo.cur.ops))
        self.assertEqual((save.commits,undo.commits,save.rollbacks,undo.rollbacks),(1,1,0,0))
        self.assertEqual(state['undo'],[])

    def test_second_lane_failure_rolls_back_first_and_saves_no_motion(self):
        state,choices,before,_=self.multi_state();conn=Conn()
        with mock.patch.object(server,'get_object',return_value=(4,SimpleNamespace(ra_deg=12.,dec_deg=8.))), \
             mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',return_value=None), \
             mock.patch.object(server.spectral_vetting,'snapshot',side_effect=before+[before[0]]), \
             mock.patch.object(server.spectral_vetting,'apply',side_effect=[2,RuntimeError('second lane failed')]) as apply:
            with self.assertRaisesRegex(RuntimeError,'second lane failed'):
                server.save_decision(state,0,'6','',spectral_reviews=choices)
        self.assertEqual(apply.call_count,2)
        self.assertEqual((conn.commits,conn.rollbacks),(0,1));self.assertEqual(state['undo'],[])
        self.assertFalse(any('INSERT INTO pcat_wiseview' in sql for sql,_ in conn.cur.ops))

    def test_stale_second_lane_refuses_all_writes(self):
        state,choices,before,_=self.multi_state();conn=Conn()
        state['spectral_snapshots'][4][choices[1]['lane']]={'classification':'good'}
        with mock.patch.object(server,'get_object',return_value=(4,None)), \
             mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',return_value=None), \
             mock.patch.object(server.spectral_vetting,'snapshot',side_effect=before), \
             mock.patch.object(server.spectral_vetting,'apply') as apply:
            with self.assertRaisesRegex(ValueError,'Spectral review changed'):
                server.save_decision(state,0,'6','',spectral_reviews=choices)
        apply.assert_not_called();self.assertEqual(conn.rollbacks,1)

    def test_stale_second_lane_refuses_entire_undo(self):
        state,choices,before,after=self.multi_state();conn=Conn()
        state['undo']=[{'oid':4,'index':0,'before':None,'after':MOTION,'spectral_reviews':[
            {'lane':c['lane'],'before':b,'after':a,'nrows':2} for c,b,a in zip(choices,before,after)]}]
        with mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',return_value=MOTION), \
             mock.patch.object(server.spectral_vetting,'snapshot',side_effect=[after[0],before[1]]), \
             mock.patch.object(server.spectral_vetting,'restore') as restore:
            with self.assertRaisesRegex(ValueError,'Spectral review or spectrum state changed'):
                server.undo_decision(state)
        restore.assert_not_called();self.assertEqual(conn.rollbacks,1);self.assertEqual(len(state['undo']),1)

    def test_duplicate_or_invalid_lane_choices_never_connect(self):
        state,choices,_,_=self.multi_state()
        for invalid in ([choices[0],choices[0]],[{**choices[0],'specid':True}],
                        [{**choices[0],'lane':'unknown'}],[{**choices[0],'classification':'unknown'}]):
            with self.subTest(invalid=invalid),mock.patch.object(server,'get_object',return_value=(4,None)), \
                 mock.patch.object(server.review,'_connect_db') as connect:
                with self.assertRaises(ValueError):server.save_decision(state,0,'6','',spectral_reviews=invalid)
                connect.assert_not_called()

    def test_combined_save_and_undo_commit_both_tables_and_restore_flags(self):
        state=session();save,undo=Conn(),Conn();obj=SimpleNamespace(ra_deg=12.,dec_deg=8.)
        with mock.patch.object(server,'get_object',return_value=(4,obj)), \
             mock.patch.object(server.review,'_connect_db',side_effect=[save,undo]), \
             mock.patch.object(server,'snapshot',side_effect=[None,MOTION,MOTION,None]), \
             mock.patch.object(server.spectral_vetting,'snapshot',side_effect=[copy.deepcopy(BEFORE),copy.deepcopy(AFTER),copy.deepcopy(AFTER)]), \
             mock.patch.object(server,'invalidate_sublime_stats'):
            result=server.save_decision(state,0,'6','note','bad','spiffstacker',100)
            self.assertEqual(result['spectral_saved'],'bad')
            self.assertEqual((save.commits,save.rollbacks),(1,0))
            self.assertEqual(len(state['undo']),1)
            server.undo_decision(state)
        sql=[text for text,_ in save.cur.ops]
        self.assertTrue(any('INSERT INTO `pcat_spherex_spiffstacker_visual_vetting`' in text for text in sql))
        self.assertTrue(any('INSERT INTO pcat_wiseview_visual_vetting' in text for text in sql))
        self.assertTrue(any('UPDATE moca_spectra SET ignored=1' in text for text in sql))
        self.assertTrue(any('UPDATE data_spectral_types SET ignored=%s' in text and values[0]==1 for text,values in save.cur.ops))
        self.assertTrue(any('DELETE FROM `pcat_spherex_spiffstacker_visual_vetting`' in text for text,_ in undo.cur.ops))
        self.assertTrue(any('UPDATE moca_spectra SET ignored=%s' in text and values==(0,100,4) for text,values in undo.cur.ops))
        self.assertEqual((undo.commits,undo.rollbacks),(1,0));self.assertEqual(state['undo'],[])

    def test_motion_failure_rolls_back_spectral_write_too(self):
        state=session();conn=Conn(fail_motion=True);obj=SimpleNamespace(ra_deg=12.,dec_deg=8.)
        with mock.patch.object(server,'get_object',return_value=(4,obj)), \
             mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',return_value=None), \
             mock.patch.object(server.spectral_vetting,'snapshot',side_effect=[copy.deepcopy(BEFORE),copy.deepcopy(AFTER)]):
            with self.assertRaisesRegex(RuntimeError,'motion write failed'):
                server.save_decision(state,0,'6','','bad','spiffstacker',100)
        self.assertEqual((conn.commits,conn.rollbacks),(0,1));self.assertEqual(state['undo'],[])

    def test_changed_spectral_review_refuses_combined_save(self):
        state=session();state['spectral_snapshots'][4]['spiffstacker']={'classification':'good','sources':'someone else'}
        conn=Conn();obj=SimpleNamespace(ra_deg=12.,dec_deg=8.)
        with mock.patch.object(server,'get_object',return_value=(4,obj)), \
             mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',return_value=None), \
             mock.patch.object(server.spectral_vetting,'snapshot',return_value=copy.deepcopy(BEFORE)):
            with self.assertRaisesRegex(ValueError,'Spectral review changed'):
                server.save_decision(state,0,'6','','good','spiffstacker',100)
        self.assertEqual((conn.commits,conn.rollbacks),(0,1))
        self.assertFalse(any('INSERT INTO' in text for text,_ in conn.cur.ops))

    def test_changed_displayed_spectrum_refuses_spectral_write(self):
        cur=Cursor()
        with self.assertRaisesRegex(ValueError,'Displayed spectrum changed'):
            server.spectral_vetting.apply(cur,4,'spiffstacker','good',99,'Gagne',copy.deepcopy(BEFORE))
        self.assertEqual(cur.ops,[])

    def test_usable_label_keeps_ignored_spectra_untouched(self):
        cur=Cursor();before=copy.deepcopy(BEFORE);before['types'][0]['ignored']=1
        before['spectra'].append({'moca_specid':99,'ignored':1})
        changed=server.spectral_vetting.apply(cur,4,'spiffstacker','good',100,'Gagne',before)
        self.assertEqual(changed,2)
        self.assertTrue(any('UPDATE data_spectral_types' in sql and values==(0,90,4) for sql,values in cur.ops))
        self.assertFalse(any('UPDATE moca_spectra' in sql for sql,_ in cur.ops))

    def test_spectral_write_failure_rolls_back_without_saving_motion(self):
        state=session();conn=Conn();obj=SimpleNamespace(ra_deg=12.,dec_deg=8.)
        with mock.patch.object(server,'get_object',return_value=(4,obj)), \
             mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',return_value=None), \
             mock.patch.object(server.spectral_vetting,'snapshot',return_value=copy.deepcopy(BEFORE)), \
             mock.patch.object(server.spectral_vetting,'apply',side_effect=RuntimeError('spectral write failed')):
            with self.assertRaisesRegex(RuntimeError,'spectral write failed'):
                server.save_decision(state,0,'6','','good','spiffstacker',100)
        self.assertEqual((conn.commits,conn.rollbacks),(0,1));self.assertEqual(state['undo'],[])
        self.assertFalse(any('INSERT INTO pcat_wiseview' in text for text,_ in conn.cur.ops))

    def test_undo_refuses_changed_spectral_state_before_restoring_either_review(self):
        state=session();state['undo']=[{'oid':4,'index':0,'before':None,'after':MOTION,
            'spectral':{'lane':'spiffstacker','before':copy.deepcopy(BEFORE),'after':copy.deepcopy(AFTER),'nrows':3}}]
        conn=Conn()
        with mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',return_value=MOTION), \
             mock.patch.object(server.spectral_vetting,'snapshot',return_value=copy.deepcopy(BEFORE)):
            with self.assertRaisesRegex(ValueError,'Spectral review or spectrum state changed'):
                server.undo_decision(state)
        self.assertEqual((conn.commits,conn.rollbacks),(0,1));self.assertEqual(len(state['undo']),1)
        self.assertFalse(any('UPDATE ' in sql or 'DELETE ' in sql for sql,_ in conn.cur.ops))


if __name__=='__main__':unittest.main()


_auth_patch = None
def setUpModule():
    global _auth_patch
    _auth_patch=mock.patch.object(server, "current_auth", return_value={"user":"management"})
    _auth_patch.start()
def tearDownModule():
    _auth_patch.stop()
