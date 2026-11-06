"""Persistent, resumable Gaia DR3 30-arcsecond neighbor counts.

Counts exclude the object's exact matched Gaia source, when available. A
missing, failed, ambiguous, or stale lookup is never interpreted as zero.
"""
from __future__ import annotations

import math
import fcntl
import sqlite3
import time
from pathlib import Path

CACHE_PATH = Path(__import__('os').environ.get('MOCAVIZ_GAIA_CROWDING_CACHE', '/nonexistent/mocaviz-gaia-crowding.sqlite3'))
RADIUS_ARCSEC = 30.0
TAP_URL = 'https://gaia.ari.uni-heidelberg.de/tap'
SCHEMA_VERSION = 'gaia-dr3-30arcsec-exclude-matched-v1'




def open_readonly(path=CACHE_PATH):
    path=Path(path).resolve()
    conn=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=30)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA busy_timeout=30000')
    row=conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
    if not row or row['value'] != SCHEMA_VERSION:
        conn.close();raise ValueError('Incompatible Gaia cache version')
    return conn


def normalize_target(oid, ra, dec, gaia_ids, sample_mask):
    ids=sorted({str(x).strip() for x in (gaia_ids or ()) if x is not None and str(x).strip()})
    valid_coords=(ra is not None and dec is not None and math.isfinite(float(ra)) and math.isfinite(float(dec))
                  and 0 <= float(ra) < 360 and -90 <= float(dec) <= 90
                  and not (float(ra)==0 and float(dec)==0))
    valid_ids=all(x.isdecimal() and 0 < int(x) < 2**63 for x in ids)
    valid=valid_coords and valid_ids and len(ids)<=1
    return (int(oid),float(ra) if valid_coords else None,float(dec) if valid_coords else None,
            ids[0] if len(ids)==1 and valid_ids else None,int(sample_mask),
            'pending' if valid else 'invalid',time.time(),
            None if valid else 'Invalid reference coordinates or ambiguous Gaia match')












def available_counts(conn, specs):
    """Return counts matching the same reference coordinates and Gaia ID."""
    out={}
    for oid,ra,dec,gaia_ids in specs:
        normalized=normalize_target(oid,ra,dec,gaia_ids,0)
        if normalized[5]=='invalid': continue
        row=conn.execute('SELECT ra,dec,gaia_id,neighbors,state FROM targets WHERE oid=?',(int(oid),)).fetchone()
        if row and row['state']=='complete' and row['ra']==normalized[1] and row['dec']==normalized[2] and row['gaia_id']==normalized[3]:
            out[int(oid)]=int(row['neighbors'])
    return out






def status(path=CACHE_PATH, *, sample_mask=1):
    if not Path(path).is_file():return {'indexed':0,'complete':0,'pending':0,'working':0,'error':0,'invalid':0,'indexing':False,'building':False}
    conn=open_readonly(path)
    try:
        result={'indexed':0,'complete':0,'pending':0,'working':0,'error':0,'invalid':0}
        for row in conn.execute('SELECT state,COUNT(*) n FROM targets WHERE (sample_mask & ?) != 0 GROUP BY state',(sample_mask,)):
            result[row['state']]=int(row['n']);result['indexed']+=int(row['n'])
        row=conn.execute("SELECT value FROM metadata WHERE key='indexing'").fetchone()
        lock_path=Path(str(path)+'.lock')
        active=False
        if lock_path.exists():
            with lock_path.open('r') as lock:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:active=True
                else:fcntl.flock(lock,fcntl.LOCK_UN)
        result['indexing']=bool(row and row['value']=='1' and active)
        result['building']=active
        return result
    finally:conn.close()
