"""Spectral-review changes inside the caller's motion-review transaction."""
from .lane_utils import AUTOTYPE_USABLE_VETTING_CLASSIFICATIONS

LANES = {
    'spiff': ('pcat_spherex_visual_vetting',55,('spherex_autotype',)),
    'spiffstacker': ('pcat_spherex_spiffstacker_visual_vetting',62,('spiff_stacker_autotype',)),
    'sublimeaperture': ('pcat_spherex_sublimeaperture_visual_vetting',76,
                        ('sublimeaperture_autotype','spherex_sublimeap_autotype')),
}


TABLE = 'pcat_spherex_spectrum_reviews'


def rows_for_object(cur, oid):
    """Match the exact active spectrum selected by spectrum_data for each panel."""
    result = {lane: None for lane in LANES}
    packs = {pack: lane for lane, (_, pack, _) in LANES.items()}
    import pymysql
    try:
        cur.execute(f"""SELECT shown.pack, v.classification, v.sources
            FROM (SELECT moca_specpackid AS pack, MAX(moca_specid) AS specid
                  FROM moca_spectra WHERE moca_oid=%s AND ignored=0
                  AND moca_specpackid IN (55,62,76) GROUP BY moca_specpackid) shown
            JOIN {TABLE} v ON v.moca_specid=shown.specid AND v.review_kind='quality'""", (oid,))
    except pymysql.err.ProgrammingError as exc:
        # Motion review remains available during the spectrum-schema rollout.
        if exc.args[0] == 1146 and TABLE in str(exc):
            return result
        raise
    for row in cur.fetchall():
        result[packs[row['pack']]] = {key: row[key] for key in ('classification', 'sources')}
    return result


def snapshot(cur, oid, lane, specid, *, require_displayed=False):
    _, pack, methods = LANES[lane]
    if require_displayed:
        cur.execute("""SELECT moca_specid FROM moca_spectra WHERE moca_oid=%s
            AND moca_specpackid=%s AND ignored=0 ORDER BY moca_specid DESC LIMIT 1 FOR UPDATE""",
            (oid, pack))
        current = cur.fetchone()
        if not current or current['moca_specid'] != specid:
            raise ValueError('Displayed spectrum changed; reload it before saving')
    cur.execute("""SELECT moca_specid,ignored FROM moca_spectra WHERE moca_oid=%s
        AND moca_specpackid=%s AND moca_specid=%s FOR UPDATE""", (oid, pack, specid))
    spectra = list(cur.fetchall())
    if not spectra:
        raise ValueError('Spectrum moved to a different target; reload it')
    cur.execute(f"SELECT classification,sources FROM {TABLE} WHERE moca_specid=%s AND review_kind='quality' FOR UPDATE",
                (specid,))
    vetting = cur.fetchone()
    slots = ','.join(['%s'] * len(methods))
    cur.execute(f"""SELECT id,ignored FROM data_spectral_types WHERE moca_oid=%s
        AND moca_specid=%s AND calculation_method IN ({slots}) ORDER BY id FOR UPDATE""",
        (oid, specid, *methods))
    return {'vetting': vetting, 'types': list(cur.fetchall()), 'spectra': spectra}


def apply(cur, oid, lane, classification, specid, reviewer, before):
    if not any(r['moca_specid'] == specid and r['ignored'] == 0 for r in before['spectra']):
        raise ValueError('Displayed spectrum changed; reload it before saving both classifications')
    sources=f'wiseview_web/server.py; specid={specid}; reviewer={str(reviewer or "")[:32]}'
    cur.execute(f"""INSERT INTO {TABLE} (moca_specid,classification,sources) VALUES (%s,%s,%s)
        ON DUPLICATE KEY UPDATE classification=VALUES(classification),sources=VALUES(sources)""",
        (specid,classification,sources))
    changed=1
    ignored=0 if classification in AUTOTYPE_USABLE_VETTING_CLASSIFICATIONS else 1
    for row in before['types']:
        if row['ignored']==ignored:continue
        cur.execute('UPDATE data_spectral_types SET ignored=%s WHERE id=%s AND moca_oid=%s',
                    (ignored,row['id'],oid))
        changed+=1
    if ignored:
        for row in before['spectra']:
            if row['moca_specid']==specid and row['ignored']!=1:
                cur.execute('UPDATE moca_spectra SET ignored=1 WHERE moca_specid=%s AND moca_oid=%s',
                            (row['moca_specid'],oid))
                changed+=1
    return changed


def restore(cur, oid, lane, before, after):
    specid=before['spectra'][0]['moca_specid']
    row=before['vetting']
    if row is None:
        cur.execute(f"DELETE FROM {TABLE} WHERE moca_specid=%s AND review_kind='quality'",(specid,))
    else:
        cur.execute(f"UPDATE {TABLE} SET classification=%s,sources=%s WHERE moca_specid=%s AND review_kind='quality'",
                    (row['classification'],row['sources'],specid))
    for row in before['types']:
        if row in after['types']:continue
        cur.execute('UPDATE data_spectral_types SET ignored=%s WHERE id=%s AND moca_oid=%s',
                    (row['ignored'],row['id'],oid))
    for row in before['spectra']:
        if row in after['spectra']:continue
        cur.execute('UPDATE moca_spectra SET ignored=%s WHERE moca_specid=%s AND moca_oid=%s',
                    (row['ignored'],row['moca_specid'],oid))
