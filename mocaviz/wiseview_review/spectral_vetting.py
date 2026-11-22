"""Spectral-review changes inside the caller's motion-review transaction."""
from .lane_utils import AUTOTYPE_USABLE_VETTING_CLASSIFICATIONS

from .. import spectrum_quality as quality

LANES = {
    'spiff': ('pcat_spherex_visual_vetting',55,('spherex_autotype',)),
    'spiffstacker': ('pcat_spherex_spiffstacker_visual_vetting',62,('spiff_stacker_autotype',)),
    'sublimeaperture': ('pcat_spherex_sublimeaperture_visual_vetting',76,
                        ('sublimeaperture_autotype','spherex_sublimeap_autotype')),
}


TABLE = 'pcat_spherex_spectrum_reviews'


def rows_for_object(cur, oid):
    """Remember the review seen for each available spectrum, including unreviewed targets."""
    canonical = quality.has_spectrum_reviews(cur)
    result = {'by_specid': {}, 'can_save': canonical}
    for lane, (table, pack, _) in LANES.items():
        source = quality.reviews_sql(table, pack, canonical, with_sources=True)
        cur.execute(f"""SELECT s.moca_specid,v.classification,v.sources FROM moca_spectra s
                    LEFT JOIN {source} v ON v.moca_specid=s.moca_specid
                    WHERE s.moca_oid=%s AND s.moca_specpackid=%s AND {quality.displayable_sql()}
                    ORDER BY s.moca_specid DESC""", (oid, pack))
        for row in cur.fetchall():
            label = {k:row[k] for k in ('classification','sources')} if row['classification'] else None
            result['by_specid'][str(row['moca_specid'])] = label
            result.setdefault(lane, label)
    return result


def snapshot(cur, oid, lane, specid, *, require_displayed=False):
    _, pack, methods = LANES[lane]
    cur.execute("""SELECT moca_specid,ignored FROM moca_spectra WHERE moca_oid=%s
        AND moca_specpackid=%s AND moca_specid=%s FOR UPDATE""", (oid, pack, specid))
    spectra = list(cur.fetchall())
    if not spectra:
        raise ValueError('Spectrum moved to a different target; reload it')
    cur.execute(f"SELECT classification,sources FROM {TABLE} WHERE moca_specid=%s AND review_kind='quality' FOR UPDATE",
                (specid,))
    vetting = cur.fetchone()
    if require_displayed and vetting and vetting['classification'].lower() not in quality.USABLE:
        raise ValueError('Displayed spectrum changed; reload it before saving')
    slots = ','.join(['%s'] * len(methods))
    cur.execute(f"""SELECT id,ignored FROM data_spectral_types WHERE moca_oid=%s
        AND moca_specid=%s AND calculation_method IN ({slots}) ORDER BY id FOR UPDATE""",
        (oid, specid, *methods))
    return {'vetting': vetting, 'types': list(cur.fetchall()), 'spectra': spectra}


def apply(cur, oid, lane, classification, specid, reviewer, before):
    if not any(r['moca_specid'] == specid and (r['ignored'] == 0 or (before['vetting'] or {}).get('classification','').lower() in quality.USABLE) for r in before['spectra']):
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
