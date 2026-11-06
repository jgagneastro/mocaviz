"""Classification policy and lane-scoped mutation/Undo checks; no live DB access."""
import copy
import sqlite3
import unittest
from unittest.mock import MagicMock, patch
from mocaviz import spherex_review as sr

AUTH={'user':'management','password':'fixture','database':sr.PRIVATE_DB}
GOOD={'good','peculiar_ucd','contaminated_ucd','good_reddened','good_plus_star'}
CANDIDATE={'good_candidate','incomplete_but_promising','weird'}
BAD={'bad','early','galaxy','reddened','scatter','snr','star','unclear','risky_andromeda','giant'}


def item_for(lane):
    item=sr.demo_item({'lane':lane})
    item['state']={'vet':[],'spt':[],'spectra':[{'moca_specid':11001,'ignored':1}]}
    return item


def prepare(item,classification,action='classify'):
    item['revision']=sr.fingerprint(item['state'])
    item['data_revision']=sr.fingerprint([item['raw_spectrum'],[]])
    body=dict(lane=item['lane'],moca_oid=1001,moca_specid=11001,action=action,
              classification=classification,revision=item['revision'],data_revision=item['data_revision'],
              is_public=0,rls='gagne',allow_replace=True)
    with patch.object(sr,'analyze',return_value=item):return sr.prepare(MagicMock(),body,AUTH)


class ClassificationPolicyTests(unittest.TestCase):
    def test_complete_validated_mapping(self):
        for label in GOOD|CANDIDATE|BAD:
            with self.subTest(label=label):
                expected={'ignored':int(label in BAD)}
                if label in GOOD|CANDIDATE:expected['photometric_estimate']=int(label in CANDIDATE)
                self.assertEqual(sr.classification_flags(label),expected)
        self.assertEqual(sr.classification_flags('late_M'),{'ignored':0})

    def test_each_lane_reactivates_existing_and_new_good_candidate_types_and_spectra(self):
        for lane in sr.LANES:
            base=item_for(lane)
            for label in GOOD|CANDIDATE:
                for existing in (False,True):
                    with self.subTest(lane=lane,label=label,existing=existing):
                        item=copy.deepcopy(base)
                        if existing:item['state']['spt']=[dict(id=42,ignored=1,photometric_estimate=1-int(label in CANDIDATE),spectral_type='T8')]
                        result=prepare(item,label)
                        ops={op['table']:op for op in result['plan']['operations']}
                        row=ops['data_spectral_types']['rows'][0]
                        self.assertEqual(row['ignored'],0)
                        self.assertEqual(row['photometric_estimate'],int(label in CANDIDATE))
                        self.assertEqual(ops['moca_spectra']['rows'],[{'moca_specid':11001,'ignored':0}])
                        self.assertEqual(row.get('spectral_type','T8'),'T8' if existing else base['fit']['best']['display_type'])
                        if existing:self.assertEqual(set(row),{'id','ignored','photometric_estimate'})

    def test_unchanged_flags_are_omitted_from_classification_plan(self):
        item=item_for('spiffstacker')
        item['state']['spt']=[dict(id=42,ignored=0,photometric_estimate=0)]
        item['state']['spectra'][0]['ignored']=0
        result=prepare(item,'good')
        self.assertEqual(result['row_counts'],{'pcat_spherex_spiffstacker_visual_vetting':1})
        item['state']['spt'][0]['photometric_estimate']=1
        row=prepare(item,'good')['plan']['operations'][1]['rows'][0]
        self.assertEqual(row,{'id':42,'photometric_estimate':0})

    def test_giant_rejection_and_legacy_risky_save_preserve_photometric_flag(self):
        for lane in sr.LANES:
            item=item_for(lane)
            item['state']['spectra'][0]['ignored']=0
            item['state']['spt']=[dict(id=42,ignored=0,photometric_estimate=1,calculation_method=sr.LANES[lane]['method'])]
            result=prepare(item,'giant')
            self.assertEqual(result['plan']['operations'][1]['rows'],[{'id':42,'ignored':1}])
            self.assertEqual(result['plan']['operations'][2]['rows'],[{'moca_specid':11001,'ignored':1}])
            item['state']['vet']=[{'classification':'risky_andromeda'}]
            result=prepare(item,None,'upsert_spt')
            row=result['plan']['operations'][0]['rows'][0]
            self.assertEqual((row['ignored'],row['photometric_estimate']),(1,1))
            self.assertEqual(result['plan']['operations'][1]['rows'],[{'moca_specid':11001,'ignored':1}])

    def test_save_type_uses_stored_classification_to_reactivate_lane(self):
        item=item_for('sublimeaperture')
        item['state']['vet']=[{'classification':'good_candidate'}]
        item['state']['spt']=[dict(id=42,ignored=1,photometric_estimate=0,calculation_method='spherex_sublimeap_autotype')]
        row=prepare(item,None,'upsert_spt')['plan']['operations'][0]['rows'][0]
        self.assertEqual((row['ignored'],row['photometric_estimate']),(0,1))
        self.assertEqual(row['calculation_method'],'spherex_sublimeap_autotype')

    def test_stale_write_policy_receipts_fail_before_mutation(self):
        result=prepare(item_for('spiffstacker'),'good')
        plan=copy.deepcopy(result['plan']);plan.pop('write_policy_version')
        conn,cur=MagicMock(),MagicMock()
        with self.assertRaisesRegex(sr.ReviewError,'policy changed'):
            sr.submit(conn,cur,AUTH,{'receipt':sr.seal(AUTH,'plan',plan)})
        cur.execute.assert_not_called();conn.commit.assert_not_called()


class SQLiteFlagTransactionTests(unittest.TestCase):
    def test_submit_and_undo_restore_type_and_spectrum_flags_without_touching_other_lanes(self):
        for lane,config in sr.LANES.items():
            with self.subTest(lane=lane),sqlite3.connect(':memory:') as db:
                db.row_factory=sqlite3.Row
                columns=[]
                for field in sr.SPT_FIELDS:
                    kind='INTEGER' if field in ('moca_oid','moca_specid','ignored','is_public','photometric_estimate') else 'TEXT'
                    columns.append(f'`{field}` {kind}')
                db.execute('CREATE TABLE data_spectral_types(id INTEGER PRIMARY KEY,'+','.join(columns)+',modified_timestamp TEXT)')
                db.execute('CREATE TABLE moca_spectra(moca_specid INTEGER PRIMARY KEY,moca_oid INTEGER,moca_specpackid INTEGER,ignored INTEGER,modified_timestamp TEXT)')
                for other in sr.LANES.values():db.execute(f"CREATE TABLE {other['table']}(id INTEGER PRIMARY KEY,moca_oid INTEGER UNIQUE,classification TEXT,sources TEXT,modified_timestamp TEXT)")
                other=next(value for key,value in sr.LANES.items() if key!=lane)
                for row_id,oid,method in [(42,1001,config['method']),(43,1001,other['method']),(44,1002,config['method'])]:
                    db.execute('INSERT INTO data_spectral_types(id,moca_oid,calculation_method,spectral_type,photometric_estimate,ignored,is_public,rls) VALUES(?,?,?,\'T8\',0,1,0,\'gagne\')',(row_id,oid,method))
                db.executemany('INSERT INTO moca_spectra VALUES(?,?,?,?,NULL)',[(11001,1001,config['pack'],1),(11002,1001,other['pack'],1),(11003,1002,config['pack'],1),(11004,1001,config['pack'],1)])
                class Cursor:
                    def execute(self,sql,params=()):self.result=db.execute(sql.replace('%s','?').replace(' FOR UPDATE',''),params)
                    def fetchall(self):return [dict(row) for row in self.result.fetchall()]
                cur=Cursor();item=item_for(lane)
                item['state']=sr.snapshot(cur,config,1001)
                before=copy.deepcopy(item['state'])
                result=prepare(item,'good_candidate')
                def upsert(cursor,table,row,fields):
                    self.assertEqual(table,config['table'])
                    cursor.execute(f'INSERT INTO {table}(moca_oid,classification,sources) VALUES (%s,%s,%s) ON CONFLICT(moca_oid) DO UPDATE SET classification=excluded.classification,sources=excluded.sources',(row['moca_oid'],row['classification'],row['sources']))
                conn=MagicMock();conn.commit.side_effect=db.commit
                with patch.object(sr,'lock_object'),patch.object(sr,'lock_source_pixels'),patch.object(sr,'upsert',side_effect=upsert),patch.object(sr,'changelog') as changelog,patch.object(sr,'dataset',return_value=(item['object'],item['raw_spectrum'],[])):
                    saved=sr.submit(conn,cur,AUTH,{'receipt':result['receipt']})
                    self.assertEqual(tuple(db.execute('SELECT photometric_estimate,ignored FROM data_spectral_types WHERE id=42').fetchone()),(1,0))
                    self.assertEqual([tuple(row) for row in db.execute('SELECT photometric_estimate,ignored FROM data_spectral_types WHERE id IN (43,44) ORDER BY id')],[(0,1),(0,1)])
                    self.assertEqual([tuple(row) for row in db.execute('SELECT moca_specid,ignored FROM moca_spectra ORDER BY moca_specid')],[(11001,0),(11002,1),(11003,1),(11004,0)])
                    sr.undo(conn,cur,AUTH,{'receipt':saved['undo_receipt']})
                    self.assertEqual(sr.snapshot(cur,config,1001),before)
                    self.assertEqual(conn.commit.call_count,2);self.assertEqual(changelog.call_count,2)
