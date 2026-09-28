#!/usr/bin/env python3
"""Install a complete offline RV timing grid into the one shared SQLite cache.

Accepts plain/gzipped JSON from a path or stdin. Never creates cache copies,
model files, sidecars or per-user products. Run as the cache's service owner.
"""
import argparse
import gzip
import json
import math
from pathlib import Path
import sys
import uuid
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gnirs_wsgi  # Reuse the existing read-only astronomy configuration.
from mocaviz.gnirs_planner import cache

def validate(grid):
    fractions=[.25,.5,.75,.9,.95];slits=[.1,.15,.2,.3,.45,.675,1.]
    types=[10,12,14,16,18,20,22,23,24,26,28,30]
    expected={(m,b,s,x,n) for m in ('b12','b3high','b3cloud') for b in ('j','h','k') for s in slits for x in (1.5,2.) for n in types}
    seen=set()
    for row in grid['rows']:
        key=(row['mode'],row['band'],row['slit'],row['airmass'],row['sptn'])
        if key in seen:raise ValueError('Duplicate setup')
        seen.add(key)
        if row['center_um']!={'j':1.3,'h':1.65,'k':2.3}[row['band']]:raise ValueError('Wrong band center')
        if row['photometry_band']!=('j' if row['band']=='h' else row['band']):raise ValueError('Wrong normalization band')
        if [c['frame_seconds'] for c in row['curves']]!=[60,120,180,240,300]:raise ValueError('Missing frame curves')
        for c in row['curves']:
            prior=None
            for f in fractions:
                values=c['log_seconds'][str(f)]
                if len(values)!=65:raise ValueError('Incomplete magnitude grid')
                if any(v is None for v in values):
                    if not all(v is None for v in values):raise ValueError('Partial unsupported criterion')
                else:
                    if not all(math.isfinite(v) for v in values):raise ValueError('Nonfinite timing')
                    if any(b<a-1e-6 for a,b in zip(values,values[1:])):raise ValueError('Nonmonotonic magnitude timing')
                if prior is not None:
                    if any(a is None and b is not None or (a is not None and b is not None and b<a-1e-6) for a,b in zip(prior,values)):raise ValueError('Nonmonotonic coverage timing')
                prior=values
    if grid.get('magnitude_start')!=8. or grid.get('magnitude_step')!=.25:raise ValueError('Unexpected magnitude sampling')
    if grid.get('coverage_fractions')!=fractions:raise ValueError('Unexpected coverage settings')
    if set(grid.get('slits',[]))!=set(slits):raise ValueError('Unexpected slit settings')
    if seen!=expected:raise ValueError(f'Incomplete setup matrix: {len(seen)} / {len(expected)}')
    return len(seen)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--grid',default='-',help='JSON or gzip JSON path; default stdin');p.add_argument('--check',action='store_true')
    a=p.parse_args();raw=sys.stdin.buffer.read() if a.grid=='-' else Path(a.grid).read_bytes()
    grid=json.loads(gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw);count=validate(grid)
    cache.validate_ready(a.cache)
    if a.check:print(f'Validated {count} RV configurations; no writes');return
    lease=cache.acquire_rebuild(a.cache)
    if lease is None:raise RuntimeError('A catalog rebuild is active; retry after it completes')
    try:
        with cache.writer(a.cache,lease=lease) as db:
            meta=cache.get(db,'catalog');meta['grid']=grid;meta['revision']=uuid.uuid4().hex
            cache.put(db,'catalog',meta);cache.put(db,'revision',meta['revision'])
        print(f'Published {count} RV configurations into the existing shared cache')
    finally:cache.release_rebuild(lease)

if __name__=='__main__':main()
