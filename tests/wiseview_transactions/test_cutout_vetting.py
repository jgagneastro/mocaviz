import copy
import unittest
from types import SimpleNamespace
from unittest import mock
from mocaviz.wiseview_review import runtime as server
from .test_spectral_vetting import BEFORE, AFTER, MOTION, Conn, Cursor, session

IMAGES=[{'source_key':key,'cutout_path':'/cutouts/'+key+'.png',
         'source_tables':['pcat_sublime_candidates_v2']} for key in ('a','b')]
PATHS=[image['cutout_path'] for image in IMAGES]


def row(row_id,path,classification='bad/halo',number=-1):
    return {'id':row_id,'classification':classification,'classification_integer':number,
        'comments':'old notes','reviewer':'previous reviewer','ra_deg':12.,'dec_deg':8.,
        'source_key':path[-5] if path else None,'cutout_path':path,
        'source_table':'pcat_sublime_candidates_v2','origin':'desktop'}


OLD=[row(11,PATHS[0])]
NEW=[row(11,PATHS[0],'Good centered on PSF and isolated',4),row(22,PATHS[1],'Good centered on PSF and isolated',4)]


def state():
    value=session();value['cutout_snapshots']={4:{'images':copy.deepcopy(IMAGES),'rows':copy.deepcopy(OLD)}}
    return value


class TestCutoutVetting(unittest.TestCase):
    def test_all_three_review_types_commit_and_undo_as_one_action(self):
        value=state();save,undo=Conn(),Conn();obj=SimpleNamespace(ra_deg=12.,dec_deg=8.)
        with mock.patch.object(server,'get_object',return_value=(4,obj)), \
             mock.patch.object(server.review,'_connect_db',side_effect=[save,undo]), \
             mock.patch.object(server,'snapshot',side_effect=[None,MOTION,MOTION,None]), \
             mock.patch.object(server.spectral_vetting,'snapshot',side_effect=[copy.deepcopy(BEFORE),copy.deepcopy(AFTER),copy.deepcopy(AFTER)]), \
             mock.patch.object(server.cutout_vetting,'rows_for_object',side_effect=[copy.deepcopy(OLD),copy.deepcopy(NEW),copy.deepcopy(NEW)]), \
             mock.patch.object(server.cutout_vetting,'per_path_ready',return_value=True), \
             mock.patch.object(server,'invalidate_sublime_stats'):
            result=server.save_decision(value,0,'6','note','bad','spiffstacker',100,'4',PATHS)
            self.assertEqual(result['cutouts_saved'],2)
            self.assertEqual((save.commits,save.rollbacks),(1,0));self.assertEqual(len(value['undo']),1)
            server.undo_decision(value)
        inserts=[values for sql,values in save.cur.ops if 'INSERT INTO `pcat_spherex_cutout_visual_vetting`' in sql]
        self.assertEqual([values[8] for values in inserts],PATHS)
        self.assertTrue(all(values[2]==4 and values[4]=='Gagne' for values in inserts))
        self.assertTrue(any('INSERT INTO pcat_wiseview_visual_vetting' in sql for sql,_ in save.cur.ops))
        self.assertTrue(any('INSERT INTO `pcat_spherex_spiffstacker_visual_vetting`' in sql for sql,_ in save.cur.ops))
        self.assertTrue(any('UPDATE `pcat_spherex_cutout_visual_vetting`' in sql and values[-2:]==(11,4) for sql,values in undo.cur.ops))
        deletes=[values for sql,values in undo.cur.ops if 'DELETE FROM `pcat_spherex_cutout_visual_vetting`' in sql]
        self.assertEqual(deletes,[(22,4)])
        self.assertEqual((undo.commits,undo.rollbacks),(1,0));self.assertEqual(value['undo'],[])

    def test_second_cutout_failure_rolls_back_spectral_and_all_cutout_writes(self):
        value=state();conn=Conn();original=conn.cur.execute
        def fail_second(sql,values=()):
            original(sql,values)
            if 'INSERT INTO `pcat_spherex_cutout_visual_vetting`' in sql and values[8]==PATHS[1]:
                raise RuntimeError('second cutout failed')
        conn.cur.execute=fail_second
        with mock.patch.object(server,'get_object',return_value=(4,SimpleNamespace(ra_deg=12.,dec_deg=8.))), \
             mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',return_value=None), \
             mock.patch.object(server.spectral_vetting,'snapshot',side_effect=[copy.deepcopy(BEFORE),copy.deepcopy(AFTER)]), \
             mock.patch.object(server.cutout_vetting,'rows_for_object',return_value=copy.deepcopy(OLD)), \
             mock.patch.object(server.cutout_vetting,'per_path_ready',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'second cutout failed'):
                server.save_decision(value,0,'6','','bad','spiffstacker',100,'4',PATHS)
        self.assertEqual((conn.commits,conn.rollbacks),(0,1));self.assertEqual(value['undo'],[])
        self.assertTrue(any('INSERT INTO `pcat_spherex_spiffstacker_visual_vetting`' in sql for sql,_ in conn.cur.ops))
        self.assertFalse(any('INSERT INTO pcat_wiseview_visual_vetting' in sql for sql,_ in conn.cur.ops))

    def test_stale_cutout_review_refuses_motion_save(self):
        value=state();conn=Conn();changed=copy.deepcopy(OLD);changed[0]['comments']='another reviewer'
        with mock.patch.object(server,'get_object',return_value=(4,SimpleNamespace())), \
             mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',return_value=None), \
             mock.patch.object(server.cutout_vetting,'rows_for_object',return_value=changed):
            with self.assertRaisesRegex(ValueError,'Cutout review changed'):
                server.save_decision(value,0,'6','',cutout_key='4',cutout_paths=PATHS)
        self.assertEqual((conn.commits,conn.rollbacks),(0,1))
        self.assertFalse(any('INSERT INTO' in sql for sql,_ in conn.cur.ops))

    def test_paths_must_match_all_loaded_paths_and_red_movers_are_rejected(self):
        for mode,paths in [('sublime',[PATHS[0]]),('sublime',['/unserved.png']),('redmovers',PATHS)]:
            with self.subTest(mode=mode,paths=paths):
                value=state();value['mode']=mode
                with mock.patch.object(server,'get_object',return_value=(4,SimpleNamespace())), \
                     mock.patch.object(server.review,'_connect_db') as connect:
                    with self.assertRaises(ValueError):server.save_decision(value,0,'6','',cutout_key='4',cutout_paths=paths)
                    connect.assert_not_called()

    def test_undo_refuses_concurrently_changed_cutout_without_any_writes(self):
        value=state();before=server.cutout_vetting.selected_rows(OLD,PATHS);after=server.cutout_vetting.selected_rows(NEW,PATHS)
        value['undo']=[{'oid':4,'index':0,'before':None,'after':MOTION,'cutout':{'paths':PATHS,'before':before,'after':after}}]
        conn=Conn()
        with mock.patch.object(server.review,'_connect_db',return_value=conn), \
             mock.patch.object(server,'snapshot',return_value=MOTION), \
             mock.patch.object(server.cutout_vetting,'rows_for_object',return_value=copy.deepcopy(OLD)):
            with self.assertRaisesRegex(ValueError,'Cutout review changed'):
                server.undo_decision(value)
        self.assertEqual((conn.commits,conn.rollbacks),(0,1));self.assertEqual(len(value['undo']),1)
        self.assertFalse(any('UPDATE ' in sql or 'DELETE ' in sql for sql,_ in conn.cur.ops))

    def test_old_object_unique_key_blocks_cutout_writes(self):
        cur=Cursor()
        with mock.patch.object(server.cutout_vetting,'per_path_ready',return_value=False):
            with self.assertRaisesRegex(ValueError,'Per-cutout storage needs'):
                server.cutout_vetting.apply(cur,4,server.cutout_vetting.CLASSIFICATION_SPECS[0],IMAGES,SimpleNamespace(),SimpleNamespace(),'')
        self.assertEqual(cur.ops,[])

    def test_compression_variants_match_same_review_without_inventing_legacy_paths(self):
        saved=row(11,PATHS[0]+'.bz2');legacy=row(12,None)
        self.assertEqual(server.cutout_vetting.selected_rows([saved,legacy],PATHS),{PATHS[0]:saved,PATHS[1]:None})


if __name__=='__main__':unittest.main()


_auth_patch = None
def setUpModule():
    global _auth_patch
    _auth_patch=mock.patch.object(server, "current_auth", return_value={"user":"management"})
    _auth_patch.start()
def tearDownModule():
    _auth_patch.stop()
