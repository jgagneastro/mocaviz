"""Bounded, read-only pixel queries after spectrum selection.

Filter medians need no window sort: a majority on either side decides the
threshold, except for an even split, where the two central values decide it.
The 1–2 µm ordering median is computed only within needed coarse-priority groups.
"""
from itertools import groupby

PIXEL_BATCH = 4000


def chunks(values):
    for start in range(0, len(values), PIXEL_BATCH):
        yield values[start:start + PIXEL_BATCH]


def passing_snr(cur, specids, minimum, wavelength_range, read):
    if minimum is None:
        return set(specids)
    passing = set()
    for batch in chunks(specids):
        conditions = ['d.moca_specid IN ('+','.join(['%s']*len(batch))+')',
                      'd.ignored=0', 'd.wavelength_angstrom>0',
                      'd.flux_flambda IS NOT NULL', 'd.flux_flambda_unc>0']
        params = list(batch)
        if wavelength_range is not None:
            low, high = wavelength_range
            conditions.append('d.wavelength_angstrom BETWEEN %s AND %s')
            params.extend((low*10000, high*10000))
        snr = 'd.flux_flambda/d.flux_flambda_unc'
        above = f'SUM(CASE WHEN {snr}>=%s THEN 1 ELSE 0 END)'
        # On an even split the upper/lower central samples are respectively
        # MIN(above) and MAX(below). Their average is the exact even median.
        sql = f"""SELECT d.moca_specid FROM data_spectra d
            WHERE {' AND '.join(conditions)} GROUP BY d.moca_specid
            HAVING 2*{above}>COUNT(*) OR (2*{above}=COUNT(*) AND
              (MAX(CASE WHEN {snr}<%s THEN {snr} END)+
               MIN(CASE WHEN {snr}>=%s THEN {snr} END))/2.0>=%s)"""
        passing.update(row['moca_specid'] for row in read(cur,sql,tuple([*params,*([minimum]*5)])))
    return passing


def ordering_snr(cur, specids, read):
    result = {}
    for batch in chunks(specids):
        sql = f"""WITH samples AS (
            SELECT d.moca_specid,d.flux_flambda/d.flux_flambda_unc AS snr,
              ROW_NUMBER() OVER (PARTITION BY d.moca_specid ORDER BY d.flux_flambda/d.flux_flambda_unc) AS sample_rank,
              COUNT(*) OVER (PARTITION BY d.moca_specid) AS sample_count
            FROM data_spectra d WHERE d.moca_specid IN ({','.join(['%s']*len(batch))})
              AND d.ignored=0 AND d.wavelength_angstrom BETWEEN 10000 AND 20000
              AND d.flux_flambda IS NOT NULL AND d.flux_flambda_unc>0
        ) SELECT moca_specid,AVG(snr) AS sort_snr_1_2 FROM samples
          WHERE sample_rank IN (FLOOR((sample_count+1)/2.0),FLOOR((sample_count+2)/2.0))
          GROUP BY moca_specid"""
        result.update((row['moca_specid'],row['sort_snr_1_2']) for row in read(cur,sql,tuple(batch)))
    return result


def coarse_key(row, galactic):
    subtype = row['sort_subtype']
    return ((row['sort_galactic_bin'],) if galactic else ()) + (
        row['sort_cnn_bin'], subtype is None, -subtype if subtype is not None else 0)


def priority_key(row, galactic):
    snr = row.get('sort_snr_1_2')
    return coarse_key(row,galactic) + (snr is None, -snr if snr is not None else 0, row['moca_oid'])


def page(cur, candidates, *, minimum, wavelength_range, order, cursor, limit, read):
    priority = order in ('cnn_spt_snr','gal_cnn_spt_snr')
    galactic = order == 'gal_cnn_spt_snr'
    after_key = None
    if priority:
        if cursor is not None:
            after = dict(moca_oid=cursor['moca_oid'],sort_cnn_bin=cursor['cnn_bin'],
                sort_subtype=cursor['spectral_subtype'],sort_snr_1_2=cursor['snr_1_2'])
            if galactic: after['sort_galactic_bin']=cursor['galactic_bin']
            after_key=priority_key(after,galactic)
            candidates=[row for row in candidates if coarse_key(row,galactic)>=coarse_key(after,galactic)]
        candidates.sort(key=lambda row:coarse_key(row,galactic))
        groups=(list(group) for _,group in groupby(candidates,key=lambda row:coarse_key(row,galactic)))
    else:
        if order.startswith('spt_'):
            direction = -1 if order=='spt_desc' else 1
            candidates.sort(key=lambda row:(row['sort_spt'] is None,
                direction*row['sort_spt'] if row['sort_spt'] is not None else 0,row['moca_oid']))
        else:
            candidates.sort(key=lambda row:row['moca_oid'],reverse=order=='oid_desc')
        groups=chunks(candidates)
    selected=[]
    for group in groups:
        ids=[row['moca_specid'] for row in group]
        eligible=passing_snr(cur,ids,minimum,wavelength_range,read)
        group=[row for row in group if row['moca_specid'] in eligible]
        snr=ordering_snr(cur,[row['moca_specid'] for row in group],read) if priority else {}
        for row in group:row['sort_snr_1_2']=snr.get(row['moca_specid'])
        if priority:
            group.sort(key=lambda row:priority_key(row,galactic))
            if after_key is not None:group=[row for row in group if priority_key(row,galactic)>after_key]
        selected.extend(group[:limit+1-len(selected)])
        if len(selected)>limit:break
    return selected
