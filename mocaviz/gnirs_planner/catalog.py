"""GNIRS RV/SXD selection and timing, adapted without local-server dependencies."""
from collections import Counter, OrderedDict
from pathlib import Path
import hashlib
import json
import math
import threading
import time
import numpy as np
from .timing import curves, estimate, band3_science_seconds
from .visibility import unpack
from .cache import reader as connect
ROOT=Path(__file__).resolve().parent
DEFAULTS=json.loads((ROOT/'defaults.json').read_text())
DEFAULTS.update(observingMode='rv',snrUnit='pixel',coverageFraction=.75,timeMetric='science')
SXD_DEFAULTS={**DEFAULTS,**json.loads((ROOT/'sxd_defaults.json').read_text())}
DEFAULT_AID_EXCLUSIONS=('CRIUS','OCSN','HSC','CWNU','HURE')
STAT=np.dtype([('oid','i8'),('science','f8'),('program','f8'),('telescope','f8'),('visits','i4'),('ra','f8'),('sptn','f8'),('age','f8'),('teff','f8'),('gnirs_data','?')])
def normalized_filters(incoming):
    if incoming.get('observingMode','rv') not in ['rv','sxd']:raise ValueError('Unknown observing mode')
    base=SXD_DEFAULTS if incoming.get('observingMode')=='sxd' else DEFAULTS
    f={**base,**{k:v for k,v in incoming.items() if k in DEFAULTS}}
    for k,v in DEFAULTS.items():
        if isinstance(v,bool):f[k]=bool(f[k])
        elif isinstance(v,(int,float)):
            f[k]=float(f[k])
            if not math.isfinite(f[k]):raise ValueError('Non-finite filter value')
    for k in ['includeOids','bypassNoMeasuredRvOids','excludeOids']:f[k]=sorted({int(x) for x in (f[k] or [])})[:5000]
    for k in ['aids','observables']:
        if f[k] is not None:f[k]=sorted(set(map(str,f[k])))
    if f['mode']=='b3wide':f['mode']='b3high'
    if f['mode'] not in ['b12','b3high','b3cloud']:raise ValueError('Unknown mode')
    if f['snrUnit'] not in ['pixel','resolution'] or f['coverageFraction'] not in [.5,.75,.9]:raise ValueError('Unsupported S/N criterion')
    if f['timeMetric'] not in ['science','program','telescope']:raise ValueError('Unknown time cutoff')
    if f['observingMode']=='rv':f.update(snrUnit='pixel',coverageFraction=.75,timeMetric='science')
    if f['calibrationMinutes']<0 or f['maxScience']<=0 or f['minWindow']<0:raise ValueError('Invalid duration')
    if str(f['airmass']) not in ['auto','1.5','2','2.0']:raise ValueError('Unsupported ITC airmass')
    if not 0<f['snr']<=1000 or not 0<f['margin']<=100 or not .25<=f['maxVisit']<=24:raise ValueError('Invalid time-model values')
    return f

def selection_sql(f):
    checks=[];params=[];membership=[];mp=[]
    def check(sql,*values):checks.append(sql);params.extend(values)
    def member(sql,*values):membership.append(sql);mp.extend(values)
    if f['rvMode']=='none':
        bypass=f['bypassNoMeasuredRvOids']
        if bypass:check('(has_rv=0 OR oid IN ('+','.join('?' for _ in bypass)+'))',*bypass)
        else:check('has_rv=0')
    elif f['rvMode']=='measured':check('has_rv=1')
    if f['rvMaxErrorEnabled']:check('rv_unc IS NOT NULL AND rv_unc<=?',f['rvMaxError'])
    if f['membershipEnabled']:member(('summed' if f['probKind']=='summed' else 'individual')+'>=?',f['prob'])
    if f['realAssociation']:member("real='1'")
    if f['uncontaminated']:member('contam=0')
    if f['uvwEnabled']:member('uvw<=?',f['uvw'])
    if f['uvwLooseEnabled']:member('loose<=?',f['uvwLoose'])
    if f['ageEnabled']:member(('(age IS NULL OR age BETWEEN ? AND ?)' if f['unknownAge']=='include' else 'age BETWEEN ? AND ?'),f['ageMin'],f['ageMax'])
    if f['associationDistanceEnabled']:member('assoc_distance<=?',f['associationDistanceMax'])
    if membership:
        sql='('+' AND '.join('('+c+')' for c in membership)+')'
        if f['referenceBypass'] and f['rvMode']!='none':sql+=' OR has_rv=1'
        standards=f['bypassNoMeasuredRvOids']
        if standards:
            sql+=' OR oid IN ('+','.join('?' for _ in standards)+')'
            mp.extend(standards)
        check('('+sql+')',*mp)
    if f['observables'] is not None:
        check('obs IN ('+','.join('?' for _ in f['observables'])+')',*f['observables'])
    check('sptn BETWEEN ? AND ?',f['sptMin'],f['sptMax'])
    if f['teffEnabled']:check('teff BETWEEN ? AND ?',f['teffMin'],f['teffMax'])
    if f['distanceEnabled']:check('(distance IS NULL OR distance<=?)' if f['unknownDistance']=='include' else 'distance<=?',f['distanceMax'])
    for name,column in [('excludePhotometricSpt','photometric'),('excludePhotometricDistance','photo_distance'),('rejectDuplicates','dupe'),('ignoreMultiples','unresolved'),('excludeSubdwarfs','subdwarf')]:
        if f[name]:check(f'COALESCE({column},0)<>1')
    if f['excludeBadSpiff']:check('NOT (COALESCE(photometric,0)=1 AND spiff_bad=1)')
    if f['requireLowg']:check('lowg=1')
    if f['conditionalLowg']:check('(age IS NULL OR age>=? OR sptn>? OR lowg=1)',f['lowgAge'],f['lowgSpt'])
    if f['hostMin']>0:check('(host IS NULL OR host>=?)',f['hostMin']*1000)
    if f['quality']!='all':check('quality IN ('+','.join('?' for _ in f['quality'])+')',*f['quality'])
    if f['manualTypesOnly']:check('automated=0')
    if f['excludeArchive']:check('archive_r<?',f['archiveResolution'])
    if f['excludePlanned']:check('planned=0')
    if f['restrictDec']:check('dec>-37 AND dec<90')
    if f['restrictRa']:check('ra_accessible=1')
    if f['excludeRestrictedAccess']:check('ra>=90 AND ra<=345 AND dec>=-30 AND dec<=73')
    if f['bestAirmassEnabled']:check('best_airmass<=?',f['bestAirmass'])
    where=' AND '.join('('+c+')' for c in checks) or '1'
    if f['includeOids']:
        where='('+where+') OR oid IN ('+','.join('?' for _ in f['includeOids'])+')';params+=f['includeOids']
    if f['excludeOids']:
        where='('+where+') AND oid NOT IN ('+','.join('?' for _ in f['excludeOids'])+')';params+=f['excludeOids']
    return where,params

class Catalog:
    def __init__(self, db_path, meta):
        self.db_path=db_path
        self.meta=meta
        self.meta['semester']['availability_note']=self.meta['semester']['availability_note'].replace(
            'This tool models natural-seeing short-blue 111 l/mm non-XD only.',
            'The planner includes natural-seeing long-blue 111 l/mm RV spectroscopy and short-blue 32 l/mm SXD spectroscopy.')
        self.meta['defaults']=DEFAULTS
        self.meta['mode_defaults']={'rv':DEFAULTS,'sxd':SXD_DEFAULTS}
        self.jobs=OrderedDict()
        self.lock=threading.RLock()
        self.revision=meta['revision']

    def start(self,raw):
        f=normalized_filters(raw)
        if f['aids'] is None:
            f['aids']=[aid for aid in self.meta['associations'] if f['observingMode']=='sxd' or not aid.startswith(DEFAULT_AID_EXCLUSIONS)]
        if f['observables'] is None:
            f['observables']=[obs for obs in self.meta['observables'] if f['observingMode']=='sxd' or obs!='pm']
        if f['observingMode']=='sxd' and self.meta.get('sxd_grid') is None:
            raise ValueError('SXD exposure cache is not published yet')
        key=hashlib.sha256(json.dumps([self.revision,f],sort_keys=True).encode()).hexdigest()[:24]
        # One computation at a time per worker; at most four bounded RAM results.
        # Requests carry their filters so any Passenger worker can reproduce a job.
        with self.lock:
            if key in self.jobs:
                self.jobs.move_to_end(key)
                return key
            job={'status':'running','scanned':0,'filters':f}
            self.select(key,job)
            self.jobs[key]=job
            while len(self.jobs)>4:self.jobs.popitem(last=False)
        return key

    def select(self,key,job):
        start=time.monotonic();f=job['filters'];grid=self.meta['sxd_grid'] if f['observingMode']=='sxd' else self.meta['grid']
        model=curves(grid,f['mode'])
        band3_model=curves(grid,'b3high') if f['excludeFastBand3'] else None
        where,params=selection_sql(f);forced=set(f['includeOids']);standards=set(f['bypassNoMeasuredRvOids']);aids=set(f['aids']) if f['aids'] is not None else None
        counts=Counter();stats=[];totals={'science':0.,'program':0.,'telescope':0.,'visits':0,'unknown':0,'measured_rv':0,'gnirs_data':0,'planned':0,'unplotted_age':0,'unplotted_teff':0}
        try:
            with connect(self.db_path) as db:
                cur=db.execute('SELECT oid,aid,ra,sptn,age,teff,has_rv,archive_r,planned,j,k,win15,win2,hist15,hist2 FROM targets INDEXED BY idx_filter_cover WHERE '+where,params)
                for index,r in enumerate(cur):
                    t=estimate(r,f,model);override=r['oid'] in forced
                    if not override:
                        win=r['win15'] if t['airmass']==1.5 else r['win2']
                        if f['minWindow']>0 and win<f['minWindow']:continue
                        metric=f['timeMetric']
                        if f['timeEnabled'] and (t[metric] is None or t[metric]>=f['maxScience']*3600):continue
                        if f['requireVisitFit'] and not t['fit']:continue
                        if band3_model is not None:
                            band3_science=band3_science_seconds(r,f,band3_model)
                            if band3_science is not None and band3_science<f['maxScience']*3600:continue
                    counts[r['aid']]+=1
                    if not override and r['oid'] not in standards and aids is not None and r['aid'] not in aids:continue
                    def val(k):return float(t[k]) if t[k] is not None else math.nan
                    stats.append((r['oid'],val('science'),val('program'),val('telescope'),int(t['visits'] or 0),r['ra'],r['sptn'],r['age'] if r['age'] is not None else math.inf,r['teff'] if r['teff'] is not None else math.nan,r['archive_r'] is not None and r['archive_r']>0))
                    for k in ['science','program','telescope','visits']:
                        if t[k] is not None:totals[k]+=t[k]
                    totals['unknown']+=t['telescope'] is None;totals['measured_rv']+=r['has_rv'];totals['gnirs_data']+=r['archive_r'] is not None and r['archive_r']>0;totals['planned']+=bool(r['planned'])
                    totals['unplotted_age']+=r['age'] is None or r['age']<=0
                    totals['unplotted_teff']+=r['age'] is None or r['age']<=0 or r['teff'] is None
                    if index%5000==0:job['scanned']=index
            array=np.array(stats,dtype=STAT);del stats
            order=np.lexsort((-array['teff'],array['age']))
            plot_ids=array['oid'][::max(1,math.ceil(len(array)/12000))].tolist()
            plot=self.plot_rows(plot_ids)
            result={'count':len(array),'total_count':self.meta['catalog_count'],'totals':totals,'association_counts':dict(counts),
                'plot':plot,'plot_sampled':len(array)>12000,'elapsed_seconds':round(time.monotonic()-start,3)}
            job.update(status='complete',result=result,stats=array,age_order=order,orders={},model=model)
        except Exception:job.update(status='error',error='The cached selection could not be calculated.')

    def plot_rows(self,ids):
        rows=[]
        with connect(self.db_path) as db:
            for i in range(0,len(ids),900):
                chunk=ids[i:i+900]
                for r in db.execute('SELECT oid,name,aid,spt,sptn,age,teff,lowg,has_rv,obs,individual,summed,best_airmass FROM targets WHERE oid IN ('+','.join('?' for _ in chunk)+')',chunk):
                    rows.append({'moca_oid':r['oid'],'designation':r['name'],'moca_aid':None if r['aid']=='FIELD / unknown' else r['aid'],
                        'spt':r['spt'],'sptn':r['sptn'],'age_myr':r['age'],'teff':r['teff'],'lowg_like':r['lowg'],'has_rv':bool(r['has_rv']),
                        'observables':r['obs'],'individual_prob':r['individual'],'summed_young_prob':r['summed'],'visibility':{'best_airmass':r['best_airmass']}})
        return rows

    def target(self,oid,job=None,db=None):
        if db is None:
            with connect(self.db_path) as connection:return self.target(oid,job,connection)
        r=db.execute('SELECT * FROM targets WHERE oid=?',(int(oid),)).fetchone()
        if r is None:return None
        row=unpack(r['payload']);row['visibility']=unpack(r['visibility']);row['_detail']=True
        if job:
            row['_timing']=estimate(r,job['filters'],job['model']);row['_timing']['photometry']=row['photometry'].get(row['_timing']['band'])
        return row

    def listed(self,job,query,sort,offset,gnirs_only=False,limit=100):
        if sort not in {'time','ra','spt','age'}:sort='time'
        stats=job['stats']
        if query.isdigit():
            row=self.target(int(query),job)
            return {'rows':[row] if row else [],'count':int(row is not None),'offset':0}
        if sort not in job['orders']:
            field={'time':'program','ra':'ra','spt':'sptn','age':'age'}.get(sort,'program')
            job['orders'][sort]=job['age_order'] if sort=='age' else np.argsort(stats[field],kind='stable')
        ids=stats['oid'][job['orders'][sort]]
        if gnirs_only:ids=ids[stats['gnirs_data'][job['orders'][sort]]]
        if query:
            with connect(self.db_path) as db:matches={r[0] for r in db.execute('SELECT oid FROM targets INDEXED BY idx_search WHERE name LIKE ? OR aid LIKE ?',('%'+query+'%','%'+query+'%'))}
            ids=np.array([oid for oid in ids if int(oid) in matches],dtype='i8')
        selected=ids[offset:offset+limit]
        with connect(self.db_path) as db:
            return {'rows':[self.target(int(oid),job,db) for oid in selected],'count':len(ids),'offset':offset}
