"""Spectral-review changes inside the caller's motion-review transaction."""
from .lane_utils import AUTOTYPE_USABLE_VETTING_CLASSIFICATIONS

LANES = {
    'spiff': ('pcat_spherex_visual_vetting',55,('spherex_autotype',)),
    'spiffstacker': ('pcat_spherex_spiffstacker_visual_vetting',62,('spiff_stacker_autotype',)),
    'sublimeaperture': ('pcat_spherex_sublimeaperture_visual_vetting',76,
                        ('sublimeaperture_autotype','spherex_sublimeap_autotype')),
}


def rows_for_object(cur, oid):
    sql=' UNION ALL '.join(f"SELECT '{lane}' AS lane,classification,sources FROM `{table}` WHERE moca_oid=%s"
                           for lane,(table,_,_) in LANES.items())
    cur.execute(sql,(oid,)*len(LANES))
    rows={lane:None for lane in LANES}
    for row in cur.fetchall():rows[row['lane']]={key:row[key] for key in ('classification','sources')}
    return rows


def vetting_row(cur, oid, lane, *, lock=False):
    table,_,_=LANES[lane]
    cur.execute(f'SELECT classification,sources FROM `{table}` WHERE moca_oid=%s'+
                (' FOR UPDATE' if lock else ''),(oid,))
    return cur.fetchone()


def snapshot(cur, oid, lane):
    _,pack,methods=LANES[lane]
    row=vetting_row(cur,oid,lane,lock=True)
    cur.execute('SELECT id,ignored FROM data_spectral_types WHERE moca_oid=%s AND calculation_method IN ('+
                ','.join(['%s']*len(methods))+') ORDER BY id FOR UPDATE',(oid,*methods))
    types=list(cur.fetchall())
    cur.execute('SELECT moca_specid,ignored FROM moca_spectra WHERE moca_oid=%s AND moca_specpackid=%s ORDER BY moca_specid FOR UPDATE',(oid,pack))
    return {'vetting':row,'types':types,'spectra':list(cur.fetchall())}


def apply(cur, oid, lane, classification, specid, reviewer, before):
    table,_,_=LANES[lane]
    active=[row['moca_specid'] for row in before['spectra'] if row['ignored']==0]
    if not active or max(active)!=specid:
        raise ValueError('Displayed spectrum changed; reload it before saving both classifications')
    sources=f'wiseview_web/server.py; specid={specid}; reviewer={str(reviewer or "")[:32]}'
    cur.execute(f'''INSERT INTO `{table}` (moca_oid,classification,sources) VALUES (%s,%s,%s)
        ON DUPLICATE KEY UPDATE classification=VALUES(classification),sources=VALUES(sources)''',
        (oid,classification,sources))
    changed=1
    ignored=0 if classification in AUTOTYPE_USABLE_VETTING_CLASSIFICATIONS else 1
    for row in before['types']:
        if row['ignored']==ignored:continue
        cur.execute('UPDATE data_spectral_types SET ignored=%s WHERE id=%s AND moca_oid=%s',
                    (ignored,row['id'],oid))
        changed+=1
    if ignored:
        for row in before['spectra']:
            if row['ignored']!=1:
                cur.execute('UPDATE moca_spectra SET ignored=1 WHERE moca_specid=%s AND moca_oid=%s',
                            (row['moca_specid'],oid))
                changed+=1
    return changed


def restore(cur, oid, lane, before, after):
    table,_,_=LANES[lane]
    row=before['vetting']
    if row is None:
        cur.execute(f'DELETE FROM `{table}` WHERE moca_oid=%s',(oid,))
    else:
        cur.execute(f'UPDATE `{table}` SET classification=%s,sources=%s WHERE moca_oid=%s',
                    (row['classification'],row['sources'],oid))
    for row in before['types']:
        if row in after['types']:continue
        cur.execute('UPDATE data_spectral_types SET ignored=%s WHERE id=%s AND moca_oid=%s',
                    (row['ignored'],row['id'],oid))
    for row in before['spectra']:
        if row in after['spectra']:continue
        cur.execute('UPDATE moca_spectra SET ignored=%s WHERE moca_specid=%s AND moca_oid=%s',
                    (row['ignored'],row['moca_specid'],oid))
