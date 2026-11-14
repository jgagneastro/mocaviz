"""Bounded, read-only pixel queries after spectrum selection.

Filter medians need no window sort: a majority on either side decides the
threshold, except for an even split, where the two central values decide it.
The 1–2 µm ordering median is computed only within needed coarse-priority groups.
"""
from itertools import groupby
from math import floor

PIXEL_BATCH = 4000
SNR_BIN_ORDER = "gal_cnn_snr_bin_spt"
GALACTIC_ORDERS = {"gal_cnn_spt_snr", SNR_BIN_ORDER}
PRIORITY_ORDERS = GALACTIC_ORDERS | {"cnn_spt_snr"}


def chunks(values):
    for start in range(0, len(values), PIXEL_BATCH):
        yield values[start:start + PIXEL_BATCH]


def passing_snr(cur, specids, minimum, wavelength_range, read, *, maximum=None):
    if minimum is None and maximum is None:
        return set(specids)

    snr = 'd.flux_flambda/d.flux_flambda_unc'
    cuts, thresholds = [], []
    for threshold, passing_op, failing_op, passing_edge, failing_edge in (
        (minimum, '>=', '<', 'MIN', 'MAX'),
        (maximum, '<=', '>', 'MAX', 'MIN'),
    ):
        if threshold is None:
            continue
        matching = f'SUM(CASE WHEN {snr}{passing_op}%s THEN 1 ELSE 0 END)'
        # On an even split, average the closest sample on each side.
        cuts.append(f"""(2*{matching}>COUNT(*) OR (2*{matching}=COUNT(*) AND
            ({passing_edge}(CASE WHEN {snr}{passing_op}%s THEN {snr} END)+
             {failing_edge}(CASE WHEN {snr}{failing_op}%s THEN {snr} END))/2.0{passing_op}%s))""")
        thresholds.extend([threshold] * 5)

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
        sql = f"""SELECT d.moca_specid FROM data_spectra d
            WHERE {' AND '.join(conditions)} GROUP BY d.moca_specid
            HAVING {' AND '.join(cuts)}"""
        passing.update(row['moca_specid'] for row in read(cur, sql, (*params, *thresholds)))
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


def descending(value):
    return value is None, -value if value is not None else 0


def coarse_key(row, galactic, snr_first):
    key = ((row['sort_galactic_bin'],) if galactic else ()) + (row['sort_cnn_bin'],)
    return key if snr_first else key + descending(row['sort_subtype'])


def priority_key(row, galactic, snr_first):
    snr = row.get('sort_snr_1_2')
    key = coarse_key(row, galactic, snr_first)
    if snr_first:
        # A signed median in [n, n+1) belongs to bin n. Rebuild the
        # same bin from the cursor's median when paging.
        key += descending(floor(snr) if snr is not None else None)
        key += descending(row['sort_subtype'])
    return key + descending(snr) + (row['moca_oid'],)


def page(cur, candidates, *, minimum, wavelength_range, order, cursor, limit, read, maximum=None):
    priority = order in PRIORITY_ORDERS
    galactic = order in GALACTIC_ORDERS
    snr_first = order == SNR_BIN_ORDER
    after_key = None
    if priority:
        if cursor is not None:
            after = dict(moca_oid=cursor['moca_oid'],sort_cnn_bin=cursor['cnn_bin'],
                sort_subtype=cursor['spectral_subtype'],sort_snr_1_2=cursor['snr_1_2'])
            if galactic: after['sort_galactic_bin']=cursor['galactic_bin']
            after_key = priority_key(after, galactic, snr_first)
            after_group = coarse_key(after, galactic, snr_first)
            candidates = [row for row in candidates if coarse_key(row, galactic, snr_first) >= after_group]
        group_key = lambda row: coarse_key(row, galactic, snr_first)
        candidates.sort(key=group_key)
        groups = (list(group) for _, group in groupby(candidates, key=group_key))
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
        eligible=passing_snr(cur,ids,minimum,wavelength_range,read,maximum=maximum)
        group=[row for row in group if row['moca_specid'] in eligible]
        snr=ordering_snr(cur,[row['moca_specid'] for row in group],read) if priority else {}
        for row in group:row['sort_snr_1_2']=snr.get(row['moca_specid'])
        if priority:
            group.sort(key=lambda row: priority_key(row, galactic, snr_first))
            if after_key is not None:
                group = [row for row in group if priority_key(row, galactic, snr_first) > after_key]
        selected.extend(group[:limit+1-len(selected)])
        if len(selected)>limit:break
    return selected
