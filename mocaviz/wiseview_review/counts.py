"""Distinct-object discovery counts, requiring saved spectral vetting."""
from decimal import Decimal

CONFIRMED_SPECTRAL_CLASSES = frozenset(('good','peculiar_ucd','contaminated_ucd','good_reddened'))


def summarize_discoveries(rows, known, claimed, *, spectral_only_confirmed=False, **_legacy):
    counts = {'confirmed_l0':0,'confirmed_t0':0,'candidate_l0':0,'candidate_t0':0}
    objects = {}
    for row in rows:
        oid = int(row['moca_oid'])
        if oid in known or oid in claimed:
            continue
        spt, motion = row.get('autotype_spectral_type_number'), row.get('motion')
        if spt is None or float(spt)<10 or motion==Decimal('1.5'):
            continue
        values = [row.get('spectral_class'), *(row.get(lane+'_class') for lane in ('spiff','spiffstacker','sublimeaperture'))]
        classes = {str(value).strip().lower() for value in values if value}
        strong = bool(classes & CONFIRMED_SPECTRAL_CLASSES)
        confirmed = strong and (motion in (5,6) or spectral_only_confirmed and motion is None)
        candidate = strong and motion in (1,2,3,4) or (
            'good_candidate' in classes and (motion is None or motion>=0))
        if not (confirmed or candidate):
            continue
        previous=objects.get(oid)
        kind='confirmed' if confirmed or previous and previous[0]=='confirmed' else 'candidate'
        objects[oid]=(kind,max(float(spt),previous[1] if previous else float(spt)))
    for kind,spt in objects.values():
        counts[kind+'_l0']+=1
        if spt>=20:counts[kind+'_t0']+=1
    return counts
