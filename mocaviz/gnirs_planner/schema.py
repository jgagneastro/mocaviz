"""Indexed GNIRS cache schema and unchanged selection-column packing."""
import zlib
from .visibility import pack
SCHEMA = 'CREATE TABLE IF NOT EXISTS targets (\n oid INTEGER PRIMARY KEY,name TEXT,aid TEXT,obs TEXT,spt TEXT,sptn REAL,\n photometric INTEGER,lowg INTEGER,subdwarf INTEGER,quality TEXT,automated INTEGER,\n dupe INTEGER,host REAL,real TEXT,contam INTEGER,individual REAL,summed REAL,\n uvw REAL,loose REAL,age REAL,distance REAL,photo_distance INTEGER,assoc_distance REAL,\n teff REAL,has_rv INTEGER,rv_unc REAL,spiff_bad INTEGER,archive_r REAL,planned INTEGER,\n ra REAL,dec REAL,ra_accessible INTEGER,best_airmass REAL,unresolved INTEGER,\n j REAL,k REAL,win15 REAL,win2 REAL,hist15 BLOB,hist2 BLOB,payload BLOB,visibility BLOB)'

def records(rows):
    records=[]
    for r in rows:
        def hist(key):
            counts=bytearray(169)
            for n,c in r['visibility']['windows'][key]['duration_counts']:counts[n]=c
            return zlib.compress(bytes(counts),1)
        v=r.pop('visibility');r['visibility']=v
        hist15,hist2=hist('1.5'),hist('2')
        payload={k:val for k,val in r.items() if k!='visibility'}
        bad=1 if str(r['spiff_vetting_classification']).lower() in ['early','unclear','bad','late_m','star','scatter','reddened','galaxy','snr','weird','giant','risky_andromeda'] else 0
        records.append((r['moca_oid'],r['designation'],r['moca_aid'] or 'FIELD / unknown',r['observables'],r['spt'],r['sptn'],
            r['photometric_estimate'],r['lowg_like'],r['subdwarf_like'],r['spt_quality'],int(r['spt_calculation_method'] is not None),
            r['likely_duplicate'],r['host_separation'],r['is_real'],r['highly_contaminated'],r['individual_prob'],r['summed_young_prob'],
            r['uvw_sep'],r['uvw_sep_loose'],r['age_myr'],r['distance_pc'],r['distance_photometric_estimate'],r['association_mean_distance_pc'],
            r['teff'],int(r['has_rv']),r['rv']['radial_velocity_kms_unc'] if r['rv'] else None,bad,r['archive_max_R'],int(r['planned_reduction_highres']),
            r['ra'],r['dec'],int(r['ra_accessible']),v['best_airmass'],int('+' in (r['spt'] or '')),
            (r['photometry']['j'] or {}).get('magnitude'),(r['photometry']['k'] or {}).get('magnitude'),
            v['windows']['1.5']['max_hours'],v['windows']['2']['max_hours'],hist15,hist2,pack(payload),pack(v)))
    return records

def create_indexes(db):
    for name,cols in [('selection','photometric,has_rv,individual'),('aid','aid'),('spt','sptn'),('name','name COLLATE NOCASE'),('visibility','best_airmass')]:
        db.execute(f'CREATE INDEX idx_{name} ON targets ({cols})')
    light=['real','contam','has_rv','individual']
    light += [r[1] for r in db.execute('PRAGMA table_info(targets)') if r[1] not in light+['payload','visibility','name','spt']]
    db.execute('CREATE INDEX idx_filter_cover ON targets ('+','.join(light)+')')
    db.execute('CREATE INDEX idx_search ON targets (name COLLATE NOCASE,aid)')
