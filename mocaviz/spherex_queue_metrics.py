"""Bounded, read-only pixel queries after spectrum selection.

Filter medians need no window sort: a majority on either side decides the
threshold, except for an even split, where the two central values decide it.
The 1–2 µm ordering median is computed only within needed coarse-priority groups.
"""
from itertools import groupby
from math import floor

PIXEL_BATCH = 4000
SNR_TYPE_ORDER = "snr_bin_spt"
SNR_BIN_ORDER = "gal_cnn_snr_bin_spt"
GALACTIC_ORDERS = {"gal_cnn_spt_snr", SNR_BIN_ORDER}
CNN_ORDERS = GALACTIC_ORDERS | {"cnn_spt_snr"}
PRIORITY_ORDERS = CNN_ORDERS | {SNR_TYPE_ORDER}


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


def coarse_key(row, order):
    if order == SNR_TYPE_ORDER:
        return ()
    key = ((row['sort_galactic_bin'],) if order in GALACTIC_ORDERS else ()) + (row['sort_cnn_bin'],)
    return key if order == SNR_BIN_ORDER else key + descending(row['sort_subtype'])


def priority_rank(row, order):
    snr = row.get('sort_snr_1_2')
    key = coarse_key(row, order)
    if order in (SNR_BIN_ORDER, SNR_TYPE_ORDER):
        # A signed median in [n, n+1) belongs to bin n. Rebuild the
        # same bin from the cursor's median when paging.
        key += descending(floor(snr) if snr is not None else None)
        key += descending(row['sort_subtype'])
    return key + descending(snr)


def priority_key(row, order):
    return priority_rank(row, order) + (row['moca_oid'], row.get('moca_specid', 0))


def plain_key(row, order):
    oid, specid = row['moca_oid'], row['moca_specid']
    if order.startswith('spt_'):
        spt = row['sort_spt']
        value = descending(spt) if order == 'spt_desc' else (spt is None, spt)
        return value + (oid, specid)
    return (-oid if order == 'oid_desc' else oid, specid)


def page(cur, candidates, *, minimum, wavelength_range, order, cursor, limit, read, maximum=None):
    priority = order in PRIORITY_ORDERS
    after_key = None
    if priority:
        if cursor is not None:
            after = dict(moca_oid=cursor['moca_oid'], sort_subtype=cursor['spectral_subtype'],
                         sort_snr_1_2=cursor['snr_1_2'])
            # Old cursors have a unique object ID per lane.
            after['moca_specid'] = cursor.get('moca_specid', float('inf'))
            if order in CNN_ORDERS:
                after['sort_cnn_bin'] = cursor['cnn_bin']
            if order in GALACTIC_ORDERS:
                after['sort_galactic_bin'] = cursor['galactic_bin']
            after_key = priority_key(after, order)
            after_group = coarse_key(after, order)
            candidates = [row for row in candidates if coarse_key(row, order) >= after_group]
        group_key = lambda row: coarse_key(row, order)
        candidates.sort(key=group_key)
        groups = (list(group) for _, group in groupby(candidates, key=group_key))
    else:
        candidates.sort(key=lambda row: plain_key(row, order))
        groups=chunks(candidates)
    selected=[]
    for group in groups:
        ids=[row['moca_specid'] for row in group]
        eligible=passing_snr(cur,ids,minimum,wavelength_range,read,maximum=maximum)
        group=[row for row in group if row['moca_specid'] in eligible]
        snr=ordering_snr(cur,[row['moca_specid'] for row in group],read) if priority else {}
        for row in group:row['sort_snr_1_2']=snr.get(row['moca_specid'])
        if priority:
            group.sort(key=lambda row: priority_key(row, order))
            if after_key is not None:
                group = [row for row in group if priority_key(row, order) > after_key]
        selected.extend(group[:limit+1-len(selected)])
        if len(selected)>limit:break
    return selected
