"""Association review calculations, bounded read caches, and conflict-checked writes."""
from __future__ import annotations
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
import threading
import time
import pymysql
from .audit import build_audits, apply_robust_point_scores, phase_space_metrics
from .repository import AssociationRepository

FIELDS = ('moca_aid','parent_aid','moca_pid','partial_subgroup_overlap','complete_parent_overlap','comments','is_public','rls','ignored')
COLUMNS = 'id, moca_aid, parent_aid, moca_pid, partial_subgroup_overlap, complete_parent_overlap, comments, is_public, rls, ignored, modified_timestamp, bibcode'

def clean(x):
    if isinstance(x, dict): return {k: clean(v) for k,v in x.items()}
    if isinstance(x, (list,tuple)): return [clean(v) for v in x]
    if isinstance(x, (datetime,date)): return x.isoformat()
    if isinstance(x, Decimal): x=float(x)
    if isinstance(x,float) and not math.isfinite(x): return None
    return x

def digest(value):
    return hashlib.sha256(json.dumps(clean(value),sort_keys=True,separators=(',',':')).encode()).hexdigest()

class Problem(Exception):
    def __init__(self, message, status=400): super().__init__(message); self.status=status

READ_DISCONNECTS = {2006, 2013, 2055}


def read_transaction(open_read_db, load, report=None):
    """Retry a lost read-only transaction once, from a new connection/snapshot."""
    for attempt in range(2):
        try:
            with open_read_db() as db:
                return load(db)
        except pymysql.MySQLError as exc:
            if attempt or not exc.args or exc.args[0] not in READ_DISCONNECTS:
                raise
            if report:
                report('Database connection dropped; reconnecting and retrying this read…')


class ReviewRepository(AssociationRepository):
    def direct_relationships(self):
        return self.database.query(f'SELECT {COLUMNS} FROM data_association_relationships ORDER BY id')

    def sampled_member_points(self, association_ids, max_points_per_association=800, chunk_size=20, report=None):
        # The private calculation is explicit: never mix public/private coordinate solutions.
        grouped={aid:[] for aid in association_ids}
        for start in range(0,len(association_ids),chunk_size):
            ids=association_ids[start:start+chunk_size]; marks=','.join(['%s']*len(ids))
            if report: report(f'Loading member coordinates for groups {start+1}–{start+len(ids)} of {len(association_ids)}…')
            result=self.database.query(f'''
                WITH members AS (
                  SELECT DISTINCT dm.moca_aid, dm.moca_oid FROM data_memberships dm
                  JOIN moca_objects mo ON mo.moca_oid=dm.moca_oid AND mo.ignored=0
                  WHERE dm.ignored=0 AND dm.moca_mtid <> 'R' AND dm.moca_aid IN ({marks})
                ), ranked AS (
                  SELECT m.*, ROW_NUMBER() OVER(PARTITION BY moca_aid
                    ORDER BY CRC32(CONCAT(moca_oid, ':moca-association-audit'))) AS rn FROM members m
                )
                SELECT m.moca_aid,m.moca_oid,MAX(mo.designation) AS designation,
                  MAX(x.x_pc) AS x_pc,MAX(x.y_pc) AS y_pc,MAX(x.z_pc) AS z_pc,
                  MAX(v.u_kms) AS u_kms,MAX(v.v_kms) AS v_kms,MAX(v.w_kms) AS w_kms
                FROM ranked m JOIN moca_objects mo ON mo.moca_oid=m.moca_oid
                LEFT JOIN calc_xyz x ON x.moca_oid=m.moca_oid AND x.ignored=0 AND x.is_public=0
                LEFT JOIN calc_uvw v ON v.moca_oid=m.moca_oid AND v.adopted=1 AND v.ignored=0 AND v.is_public=0
                WHERE m.rn<=%s GROUP BY m.moca_aid,m.moca_oid ORDER BY m.moca_aid,m.moca_oid
            ''',[*ids,max_points_per_association])
            for row in result: grouped[row['moca_aid']].append(row)
        return grouped

class Store:
    def __init__(self):
        self.lock=threading.RLock(); self.pool=ThreadPoolExecutor(max_workers=2)
        self.inventory=None; self.inventory_time=0; self.inventory_lock=threading.Lock()
        self.points=OrderedDict(); self.point_time={}; self.audits=OrderedDict(); self.jobs={}
        self.job_progress={}

    def invalidate(self):
        with self.lock:
            self.inventory = None
            self.inventory_time = 0
            self.audits.clear()
            for future in self.jobs.values():
                future.cancel()
            self.jobs.clear()
            self.job_progress.clear()

    def catalog(self, read, refresh=False, report=None):
        with self.inventory_lock:
            if self.inventory is not None and not refresh and time.time()-self.inventory_time<300:
                return self.inventory
            def load(db):
                say=report or (lambda message: None)
                repo=ReviewRepository(db)
                say('Loading association summaries…'); summaries=repo.summaries()
                say('Counting direct memberships across MOCAdb…'); sizes=repo.direct_membership_sizes()
                say('Loading recorded relationships…'); direct=repo.direct_relationships(); hierarchy=repo.relationships()
                basic=db.query('SELECT moca_aid, name FROM moca_associations ORDER BY moca_aid')
                return summaries,sizes,direct,hierarchy,basic
            summaries,sizes,direct,hierarchy,basic=read(load,report)
            indexed={r['moca_aid']:r for r in summaries}
            for row in basic: indexed.setdefault(row['moca_aid'],row)
            inventory={'summaries':list(indexed.values()),'sizes':sizes,'direct':direct,'hierarchy':hierarchy,
                       'fetched_at':datetime.now().astimezone().isoformat()}
            with self.lock:
                if refresh:
                    self.invalidate(); self.points.clear(); self.point_time.clear()
                self.inventory=inventory; self.inventory_time=time.time()
            return inventory

    def public_catalog(self, read, refresh=False):
        c=self.catalog(read,refresh)
        return {'groups':[{'moca_aid':r['moca_aid'],'name':r.get('name'),'aliases':r.get('other_names'),'members':c['sizes'].get(r['moca_aid'],0)} for r in c['summaries']],
                'relationships':c['direct'],'fetched_at':c['fetched_at']}

    def point_rows(self, repo, ids, report=None):
        with self.lock: missing=[a for a in ids if a not in self.points or time.time()-self.point_time.get(a,0)>300]
        fresh=repo.sampled_member_points(missing,report=report) if missing else {}
        with self.lock:
            self.points.update(fresh)
            self.point_time.update({a:time.time() for a in fresh})
            result={a:self.points.get(a,[]) for a in ids}
            for a in ids:
                if a in self.points: self.points.move_to_end(a)
            while len(self.points)>192:
                old,_=self.points.popitem(last=False); self.point_time.pop(old,None)
        return result

    def build(self, read, aid, extra=None, report=None):
        begun=time.monotonic(); say=report or (lambda message: None)
        # Navigate the same inventory snapshot shown in the browser. Do not repeat
        # global counts just because a group is opened after the five-minute TTL.
        with self.lock: c=self.inventory
        if c is None: c=self.catalog(read,report=say)
        summaries=c['summaries']; indexed={r['moca_aid']:r for r in summaries}
        if aid not in indexed: raise Problem('Association not found.',404)
        if extra and (extra not in indexed or extra==aid): raise Problem('Select a different existing association.')
        def load(db):
            repo=ReviewRepository(db)
            say(f'Checking shared members for {aid}…'); overlaps=repo.membership_overlaps([aid])
            say('Ranking candidate associations…')
            audits=build_audits(summaries,[aid],c['sizes'],overlaps,c['hierarchy'],max_candidates=24)
            audit=audits[0]
            # All recorded pairs are accessible, even ignored rows or same-prefix records.
            related={r['parent_aid'] if r['moca_aid']==aid else r['moca_aid'] for r in c['direct']
                     if aid in (r['moca_aid'],r['parent_aid'])}
            if extra: related.add(extra)
            existing={r['candidate_aid'] for r in audit['candidates']}
            overlap_map={r['candidate_aid']:int(r['overlap_n']) for r in overlaps}
            for other in sorted(related-existing):
                if other not in indexed or other==aid: continue
                n=overlap_map.get(other,0); tn=c['sizes'].get(aid,0); cn=c['sizes'].get(other,0)
                audit['candidates'].append({'candidate_aid':other,'candidate_name':indexed[other].get('name'),
                  'summary':indexed[other],'phase_space':phase_space_metrics(indexed[aid],indexed[other]),
                  'membership_overlap':{'overlap_n':n,'target_n':tn,'candidate_n':cn,
                    'target_containment':n/tn if tn else None,'candidate_containment':n/cn if cn else None},
                  'known_relationships':[],'priority':'manual' if other==extra else 'known'})
            ids=[aid]+[r['candidate_aid'] for r in audit['candidates']]
            points=self.point_rows(repo,ids,report=say)
            return audit,points
        audit,points=read(load,say)
        say('Preparing robust scores and plots…')
        # Retain every prepared candidate, including explicit manual comparisons.
        audit=apply_robust_point_scores([audit],points,max(24,len(audit['candidates'])))[0]
        for row in audit['candidates']:
            other=row['candidate_aid']; row['direct_rows']=[r for r in c['direct']
              if (r['moca_aid']==aid and r['parent_aid']==other) or (r['moca_aid']==other and r['parent_aid']==aid)]
        for row in audit['candidates']: row['row_revision']=digest(row['direct_rows'])
        audit['points']={a:[[p['moca_oid'],p.get('designation'),*[p.get(f) for f in ('x_pc','y_pc','z_pc','u_kms','v_kms','w_kms')]] for p in rows] for a,rows in points.items()}
        audit['fetched_at']=c['fetched_at']; audit['seconds']=round(time.monotonic()-begun,2)
        return clean(audit)

    def request_audit(self, read, aid, extra=None):
        key=(aid,extra)
        with self.lock:
            if key in self.audits and time.time()-self.audits[key][0]<300:
                self.audits.move_to_end(key); return {'state':'ready','audit':self.audits[key][1]}
            for old,f in list(self.jobs.items()):
                if f.done() and old!=key:
                    try: self.audits[old]=(time.time(),f.result())
                    except Exception: pass
                    del self.jobs[old]; self.job_progress.pop(old,None)
            while len(self.audits)>16: self.audits.popitem(last=False)
            future=self.jobs.get(key)
            if future and future.done():
                del self.jobs[key]; self.job_progress.pop(key,None)
                result=future.result(); self.audits[key]=(time.time(),result)
                while len(self.audits)>16: self.audits.popitem(last=False)
                return {'state':'ready','audit':result}
            if future is None:
                if len(self.jobs)>=6: raise Problem('Other groups are loading. Try again shortly.',429)
                info={'phase':'Queued for loading…','started':time.monotonic()}
                self.job_progress[key]=info
                def report(message):
                    with self.lock:
                        if self.job_progress.get(key) is info: info['phase']=message
                self.jobs[key]=self.pool.submit(self.build,read,aid,extra,report)
            info=self.job_progress.get(key,{})
            return {'state':'loading','phase':info.get('phase','Loading…'),
                    'elapsed_seconds':round(time.monotonic()-info.get('started',time.monotonic()),1)}


def validate_row(raw):
    if not isinstance(raw,dict) or set(raw)-set(FIELDS): raise Problem('Unexpected relationship fields.')
    row={k:raw.get(k) for k in FIELDS}
    for k in ('moca_aid','parent_aid'):
        value=row[k]
        if value is None and k=='parent_aid': continue
        if not isinstance(value,str) or not 1<=len(value)<=40 or any(ord(c)<32 for c in value): raise Problem('Select valid association identifiers.')
    if row['parent_aid']==row['moca_aid']: raise Problem('An association cannot be its own parent.')
    for k in ('partial_subgroup_overlap','complete_parent_overlap','is_public','ignored'):
        if type(row[k]) is not int or row[k] not in (0,1): raise Problem(f'{k} must be 0 or 1.')
    for k,limit in (('moca_pid',20),('rls',20),('comments',10000)):
        if row[k] is not None and (not isinstance(row[k],str) or len(row[k])>limit): raise Problem(f'Invalid {k}.')
    if row['is_public']==1: row['rls']='public'
    elif not row['rls'] or not row['rls'].strip(): raise Problem('Choose the private RLS for this relationship.')
    if row['moca_pid']=='': row['moca_pid']=None
    return row

def pair_snapshot(cur, child, parent, lock=False):
    cur.execute(f'SELECT {COLUMNS} FROM data_association_relationships WHERE (moca_aid=%s AND parent_aid <=> %s) OR (moca_aid=%s AND parent_aid=%s) ORDER BY id'+(' FOR UPDATE' if lock else ''),(child,parent,parent,child))
    return clean(list(cur.fetchall()))

def make_preview(cur, body):
    row=validate_row(body.get('row')); selected=body.get('id')
    if selected is not None and (type(selected) is not int or selected<1): raise Problem('Invalid existing row ID.')
    for aid in {row['moca_aid'],row['parent_aid']}-{None}:
        cur.execute('SELECT moca_aid FROM moca_associations WHERE moca_aid=%s',(aid,))
        if cur.fetchone() is None: raise Problem('Association no longer exists.',409)
    if row['moca_pid']:
        cur.execute('SELECT moca_pid FROM moca_publications WHERE moca_pid=%s',(row['moca_pid'],))
        if cur.fetchone() is None: raise Problem('Publication key does not exist.')
    existing=pair_snapshot(cur,row['moca_aid'],row['parent_aid'])
    if digest(existing)!=body.get('revision'): raise Problem('Relationship data changed. Refresh the database list before staging again.',409)
    if selected:
        before=next((r for r in existing if r['id']==selected),None)
        if before is None: raise Problem('Select a row from this pair before updating.',409)
    else:
        before=None
        if any(r['moca_aid']==row['moca_aid'] and r['parent_aid']==row['parent_aid'] for r in existing):
            raise Problem('This directed pair already has rows. Select the existing row to update instead of inserting a duplicate.',409)
    if before and before['moca_aid']!=row['moca_aid'] or before and before['parent_aid']!=row['parent_aid']:
        raise Problem('Changing row direction requires staging a separate row; choose the matching directed record.')
    if not row['ignored'] and not row['partial_subgroup_overlap'] and not row['complete_parent_overlap'] and row['parent_aid']:
        cur.execute('SELECT id,moca_aid,parent_aid FROM data_association_relationships WHERE ignored=0 AND partial_subgroup_overlap=0 AND complete_parent_overlap=0')
        graph={}
        for r in cur.fetchall():
            if r['id']!=selected: graph.setdefault(r['moca_aid'],[]).append(r['parent_aid'])
        todo=[row['parent_aid']]; visited=set()
        while todo:
            a=todo.pop()
            if a==row['moca_aid']: raise Problem('This containment would create a parent cycle. Check the direction and overlap flags.',409)
            if a not in visited: visited.add(a); todo.extend(graph.get(a,[]))
    return {'row':row,'id':selected,'before':before,'revision':digest(existing),'operation':'update' if selected else 'insert'}

def apply_plan(conn, cur, plan):
    # Lock both parent records to serialize inserts in a table without a pair UNIQUE key.
    row=plan['row']; ids=sorted({row['moca_aid'],row['parent_aid']}-{None})
    for aid in ids:
        cur.execute('SELECT moca_aid FROM moca_associations WHERE moca_aid=%s FOR UPDATE',(aid,))
        if cur.fetchone() is None: raise Problem('Association disappeared.',409)
    existing=pair_snapshot(cur,row['moca_aid'],row['parent_aid'],lock=True)
    if digest(existing)!=plan['revision']: raise Problem('Another change occurred after preview. Create a fresh preview.',409)
    # Revalidate the directed graph within this transaction.
    checked=make_preview(cur,{'row':row,'id':plan['id'],'revision':plan['revision']})
    if plan['id'] and all(checked['before'][key] == row[key] for key in FIELDS):
        return {'saved':True,'id':plan['id']}
    if plan['id']:
        cur.execute('UPDATE data_association_relationships SET '+','.join('`'+k+'`=%s' for k in FIELDS)+' WHERE id=%s',(*[row[k] for k in FIELDS],plan['id']))
        saved_id=plan['id']
    else:
        cur.execute('INSERT INTO data_association_relationships ('+','.join('`'+k+'`' for k in FIELDS)+') VALUES ('+','.join(['%s']*len(FIELDS))+')',tuple(row[k] for k in FIELDS))
        saved_id=cur.lastrowid
    cur.execute('INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls) VALUES (CURRENT_USER(),%s,1,%s,%s,%s)',
      ('data_association_relationships',f'Association audit reviewer: {checked["operation"]} row {saved_id}, {row["moca_aid"]} -> {row["parent_aid"]}',row['is_public'],row['rls']))
    conn.commit()
    return {'saved':True,'id':saved_id}
