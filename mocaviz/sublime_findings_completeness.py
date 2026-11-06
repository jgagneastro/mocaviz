"""Read-only UCD census and cached empirical references for the findings atlas.

The density transcription is Best et al. 2024, ApJ 967, 115, Table 3,
individual spectral bins; errors are the published Poisson column. These
are source/system counts (unresolved close multiples count once).
"""
from __future__ import annotations
import json
import math
import os
import threading
import time
from pathlib import Path
import numpy as np
from scipy.stats import chi2

VERSION = 1
CACHE = Path(os.environ.get('MOCAVIZ_COMPLETENESS_CACHE',
    str(Path.home()/'Library/Caches/MOCAviz/sublime-completeness-v1.json')))
TTL = 7*86400
LOCK = threading.Lock()
MEMORY_REFERENCE = None
# rho, negative error, positive error, all in 10^-3 pc^-3 per listed bin.
DENSITIES = [
    (.36,.10,.10),(.63,.13,.15),(.48,.11,.12),(.60,.21,.29),(.50,.11,.13),
    (.72,.14,.16),(.44,.13,.15),(.41,.12,.20),(.49,.12,.13),(.46,.13,.15),
    (.20,.07,.09),(.18,.07,.07),(.41,.13,.19),(.20,.07,.07),(.40,.12,.14),
    (1.06,.19,.21),(1.28,.28,.30),(1.98,.43,.49),(3.35,.61,.63),(1.81,.46,.57),
    (3.45,1.03,1.35),(1.31,.51,.69),(15.92,1.80,30.05),
]
REFERENCES = [
    {'label':'Best et al. (2024), Table 3', 'url':'https://ui.adsabs.harvard.edu/abs/2024ApJ...967..115B/abstract',
     'data_url':'https://arxiv.org/html/2401.09535v1#S3.T3',
     'role':'Completeness-corrected spectral-type space densities and Poisson errors; close binaries are unresolved source counts.'},
    {'label':'Kirkpatrick et al. (2024)', 'url':'https://ui.adsabs.harvard.edu/abs/2024ApJS..271...55K/abstract',
     'role':'Comparison census; its principal density table is in effective-temperature bins, so no uncertain temperature-to-type remapping is used.'},
    {'label':'Bock et al. (2026), §5.7 / Figures 5 and 19', 'url':'https://ui.adsabs.harvard.edu/abs/2026ApJ...999..139B/abstract',
     'role':'In-flight per-channel performance projects four surveys over two years. It is not a current synthetic J/W2 limit.'},
]

def bins():
    result=[]
    for i,(rho,minus,plus) in enumerate(DENSITIES):
        lo=10+i
        label=('L'+str(i) if i<10 else 'T'+str(i-10) if i<20 else 'Y'+str(i-20))
        result.append(dict(label=label,lo=lo,hi=lo+1 if lo<32 else 32.000001,
                           center=lo+.5 if lo<32 else 32,
                           rho=rho/1000,rho_minus=minus/1000,rho_plus=plus/1000,
                           sparse=lo>=30))
    return result


def fetch(cur, sql, params=()):
    cur.execute(sql, params)
    return list(cur.fetchall())


def depth_summary(rows):
    """Newest measurement per object/band; no detection S/N or visual cut.

    Magnitude errors are converted using their differential flux-error relation.
    This is a sample-conditioned empirical noise-depth estimate, not a sky map.
    """
    values={'j':[], 'w2':[]}
    seen=set()
    for row in rows:
        band=str(row['system_band_simple']).lower()
        if band not in values:continue
        key=(row['moca_oid'],band)
        if key in seen:continue
        mag,unc=row['magnitude'],row['magnitude_unc']
        if mag is None or unc is None:continue
        mag,unc=float(mag),float(unc)
        if not math.isfinite(mag) or not math.isfinite(unc) or unc<=0:continue
        seen.add(key)
        depth=mag-2.5*math.log10(3*unc*math.log(10)/2.5)
        values[band].append(depth)
    return {band:dict(n=len(data),p16=float(np.percentile(data,16)),median=float(np.median(data)),
                      p84=float(np.percentile(data,84))) if data else dict(n=0,p16=None,median=None,p84=None)
            for band,data in values.items()}


def reference_data(cur, refresh=False, *, persist=True):
    global MEMORY_REFERENCE
    with LOCK:
        if not persist and not refresh and MEMORY_REFERENCE and time.time()-MEMORY_REFERENCE['cached_at']<TTL:
            return MEMORY_REFERENCE
        if persist and not refresh:
            try:
                data=json.loads(CACHE.read_text())
                if data['version']==VERSION and time.time()-data['cached_at']<TTL:return data
            except (OSError,ValueError,KeyError):pass
        sequences={}
        for band,seqid in (('j','sptn_mj_field'),('w2','sptn_mw2_aw_field')):
            meta=fetch(cur,'SELECT moca_seqid,moca_pid,xname,yname,valid_xrange_min,valid_xrange_max,yscatter,bibcode'
                       ' FROM moca_sequences WHERE moca_seqid=%s AND ignored=0',(seqid,))
            points=fetch(cur,'SELECT xdata,ydata,yerror FROM data_astro_sequences WHERE moca_seqid=%s'
                         ' AND ignored=0 AND xdata IS NOT NULL AND ydata IS NOT NULL ORDER BY xdata',(seqid,))
            if not meta or not points:raise ValueError('The required MOCAdb magnitude sequence is unavailable.')
            sequences[band]={**meta[0],'points':[[float(p['xdata']),float(p['ydata']),float(p['yerror']) if p['yerror'] is not None else None] for p in points]}
        # Seed from the small SPHEREx spectrum set; STRAIGHT_JOIN avoids scanning all photometry.
        measurements=fetch(cur,"""SELECT STRAIGHT_JOIN p.id,p.moca_oid,p.system_band_simple,p.magnitude,p.magnitude_unc
            FROM moca_spectra s JOIN data_photometry p ON p.moca_specid=s.moca_specid
            JOIN moca_objects mo ON mo.moca_oid=p.moca_oid
            WHERE s.moca_specpackid IN (55,62,76) AND s.ignored=0 AND mo.ignored=0
              AND p.ignored=0 AND p.is_synthetic=1 AND p.system_band_simple IN ('J','W2')
              AND p.magnitude IS NOT NULL AND p.magnitude_unc>0
            ORDER BY p.moca_oid,p.system_band_simple,p.id DESC""")
        data=dict(version=VERSION,cached_at=time.time(),literature_checked='2026-11-06',
                  bins=bins(),references=REFERENCES,sequences=sequences,depths=depth_summary(measurements),
                  depth_method='m_3σ = m − 2.5 log10(3 σ_m ln(10)/2.5); newest valid measurement per object and band; no quality or S/N cuts.',
                  density_population='Unresolved sources/systems, not individually resolved close binary components.')
        # Cache only references and aggregate depths, never credentials or object records.
        from .spherex_review import clean
        data=clean(data)
        if not persist:
            MEMORY_REFERENCE=data
            return data
        try:
            CACHE.parent.mkdir(parents=True,exist_ok=True)
            temp=CACHE.with_suffix('.tmp')
            temp.write_text(json.dumps(data,allow_nan=False));temp.chmod(0o600);temp.replace(CACHE)
        except OSError:
            data['cache_warning']='Reference data loaded, but the on-disk cache could not be saved.'
        return data


def confirmed(row):
    from .sublime_findings import GOOD_QUALITY, LANES
    motion=row.get('motion')
    return motion is not None and float(motion)>=5 and any(
        str(row.get(lane+'_quality') or '').strip().lower() in GOOD_QUALITY for lane in LANES)


def count_interval(n):
    alpha=1-0.682689492137
    return [0.0 if n==0 else float(chi2.ppf(alpha/2,2*n)/2),
            float(chi2.ppf(1-alpha/2,2*(n+1))/2)]


def summarize(rows, sources):
    """Unique OIDs in the union and once in each (overlapping) input catalog."""
    rows=list({r['moca_oid']:r for r in rows}.values())
    summaries={}
    for source in ['union',*sources]:
        sample=rows if source=='union' else [r for r in rows if r.get(source)]
        records=[]
        for bin_ in bins():
            selected=[r for r in sample if r.get('spt') is not None and bin_['lo']<=float(r['spt'])<bin_['hi']]
            known=sum(bool(r.get('known')) for r in selected)
            candidate=sum(not r.get('known') and bool(r.get('known_candidate')) for r in selected)
            secure=sum(bool(r.get('known')) or confirmed(r) for r in selected)
            claimed=sum(not r.get('known') and not r.get('known_candidate') and any(r.get(k) for k in ('byw','byw_claim','yadu','azul','smdet')) for r in selected)
            records.append(dict(n=len(selected),known=known,known_candidate=candidate,claimed=claimed,
                                secure=secure,interval=count_interval(len(selected)),secure_interval=count_interval(secure)))
        summaries[source]=dict(total=len(sample),bins=records,
                               outside_density_bins=len(sample)-sum(r['n'] for r in records))
    return summaries


def census_filters(filters):
    from . import sublime_findings as sf
    filters=dict(filters)
    filters.update({key:'either' for key in sf.TRI})
    filters.update(min_spt=10,max_spt=None,spt_source='best',duplicates='exclude')
    for lane in sf.LANES:
        filters['min_'+lane+'_spt']=None
        filters['max_'+lane+'_spt']=None
    return filters


def census(cur, filters):
    from . import sublime_findings as sf
    # Keep quality settings but include all publication/claim populations.
    filters=census_filters(filters)
    sources=filters['sources']
    sql,params=sf.selected_sql(filters)
    rows=sf.fetch(cur,sql,params)
    if len(rows)>sf.MAX_OBJECTS:raise sf.sr.ReviewError('The catalog census exceeds 100,000 objects; select fewer input catalogs.',422)
    rows=list({r['moca_oid']:r for r in rows}.values())
    rows=[r for r in sf.enrich(cur,rows) if sf.passes(r,filters)]
    for r in rows:r['other']=not any(r.get(s) for s in sf.SOURCES) and not r.get('known')
    return summarize(rows,sources)


def demo_reference():
    # Explicit synthetic fixtures; never persisted or substituted for live values.
    sequences={band:dict(moca_seqid='synthetic_demo_'+band,moca_pid='Demo only',valid_xrange_min=10,
                         valid_xrange_max=31,yscatter=.4,
                         points=[[s,10+(s-10)*slope,.4] for s in range(10,32)])
               for band,slope in (('j',.5),('w2',.25))}
    return dict(version=VERSION,cached_at=time.time(),literature_checked='2026-11-06',bins=bins(),
                references=REFERENCES,sequences=sequences,
                depths={band:dict(n=180,p16=m-.5,median=m,p84=m+.5) for band,m in (('j',19),('w2',16))},
                depth_method='Synthetic demo depths and relations; not measured survey performance.')
