"""Find and review potential duplicates of catalogued L0+ objects."""
import math

import numpy as np
from scipy.spatial import cKDTree

from . import spherex_review as sr

RADIUS_ARCSEC = 100
BATCH_SIZE = 1500
PUBLISHED_TYPE = """s.ignored=0 AND s.is_public=1 AND s.photometric_estimate=0
    AND s.calculation_method IS NULL AND s.spectral_type_number>=10 AND s.spectral_type IS NOT NULL"""
PM_FIELDS = """pm.pmra_masyr, pm.pmdec_masyr, pm.pmra_masyr_unc, pm.pmdec_masyr_unc,
    pm.moca_pid AS pm_pid, pm.mission_name AS pm_mission, pm.data_release AS pm_release"""
PM_JOIN = """LEFT JOIN data_proper_motions pm ON pm.id=(SELECT p.id FROM data_proper_motions p
    WHERE p.moca_oid=mo.moca_oid AND p.adopted=1 AND p.ignored=0 ORDER BY p.id DESC LIMIT 1)"""


def placeholders(ids):
    return ','.join(['%s'] * len(ids))


def targets(cur, ids):
    return sr.rows(cur, f"""SELECT mo.moca_oid,mo.designation,de.ra,de.`dec`,de.measurement_epoch_yr,
        sp.spectral_type AS adopted_type,{PM_FIELDS}
        FROM moca_objects mo
        JOIN data_equatorial_coordinates de ON de.moca_oid=mo.moca_oid AND de.adopt_as_reference=1
        LEFT JOIN data_spectral_types sp ON sp.moca_oid=mo.moca_oid AND sp.adopted=1 AND sp.ignored=0
        {PM_JOIN}
        WHERE mo.ignored=0 AND de.ra IS NOT NULL AND de.`dec` IS NOT NULL
          AND mo.moca_oid IN ({placeholders(ids)})""", ids)


def known_details(cur, ids):
    return sr.rows(cur, f"""SELECT mo.moca_oid,mo.designation,mo.ra,mo.`dec`,de.measurement_epoch_yr,
        s.spectral_type,s.moca_pid,s.origin,pub.`name` AS reference_name,pub.bibcode,
        EXISTS (SELECT 1 FROM pcat_byw_mar9_2026 b WHERE b.moca_oid=mo.moca_oid)
          OR EXISTS (SELECT 1 FROM pcat_backyard_worlds b WHERE b.moca_oid=mo.moca_oid) AS in_byw,
        {PM_FIELDS}
        FROM moca_objects mo
        JOIN data_spectral_types s ON s.id=(SELECT s.id FROM data_spectral_types s
            WHERE s.moca_oid=mo.moca_oid AND {PUBLISHED_TYPE}
            ORDER BY s.public_adopted DESC,s.adopted DESC,s.id DESC LIMIT 1)
        LEFT JOIN moca_publications pub ON pub.moca_pid=s.moca_pid
        LEFT JOIN data_equatorial_coordinates de ON de.moca_oid=mo.moca_oid AND de.adopt_as_reference=1
        {PM_JOIN}
        WHERE mo.ignored=0 AND mo.ra IS NOT NULL AND mo.`dec` IS NOT NULL
          AND mo.moca_oid IN ({placeholders(ids)})""", ids)


def vectors(objects):
    """Cartesian unit vectors avoid special cases at the RA seam and poles."""
    coords = np.asarray([(row['ra'], row['dec']) for row in objects], dtype=float)
    ra, dec = np.radians(coords).T
    return np.column_stack((np.cos(dec)*np.cos(ra), np.cos(dec)*np.sin(ra), np.sin(dec)))


def arcseconds(chord):
    return math.degrees(2 * math.asin(min(1, chord / 2))) * 3600


def scan(cur, ids):
    if not ids:
        return [], 0
    sample = targets(cur, ids)
    if not sample:
        return [], 0
    known = sr.rows(cur, f"""SELECT mo.moca_oid,mo.ra,mo.`dec`
        FROM (SELECT DISTINCT s.moca_oid FROM data_spectral_types s WHERE {PUBLISHED_TYPE}) typed
        JOIN moca_objects mo ON mo.moca_oid=typed.moca_oid
        WHERE mo.ignored=0 AND mo.ra IS NOT NULL AND mo.`dec` IS NOT NULL""")
    if not known:
        return [], len(sample)
    known_vectors = vectors(known)
    sample_vectors = vectors(sample)
    radius = 2 * math.sin(math.radians(RADIUS_ARCSEC / 3600) / 2)
    hits = cKDTree(known_vectors).query_ball_point(sample_vectors, radius)
    pairs = []
    for target, point, neighbors in zip(sample, sample_vectors, hits):
        for i in neighbors:
            primary = known[i]['moca_oid']
            if primary != target['moca_oid']:
                pairs.append((target, primary, arcseconds(np.linalg.norm(point - known_vectors[i]))))
    if not pairs:
        return [], len(sample)

    primary_ids = sorted({primary for _, primary, _ in pairs})
    details = {}
    for start in range(0, len(primary_ids), BATCH_SIZE):
        for row in known_details(cur, primary_ids[start:start + BATCH_SIZE]):
            details[row['moca_oid']] = row
    decision_ids = sorted(set(ids) | set(primary_ids))
    existing = {}
    for start in range(0, len(decision_ids), BATCH_SIZE):
        batch = decision_ids[start:start + BATCH_SIZE]
        for row in sr.rows(cur, f"""SELECT moca_oid,potential_duplicated_moca_oid,classification,applied
            FROM pcat_duplicated_vetting WHERE potential_duplicated_moca_oid IN ({placeholders(batch)})""", batch):
            key = row['potential_duplicated_moca_oid'], row['moca_oid']
            existing[key] = row
    already_matched = {oid: row for (oid, _), row in existing.items() if row['classification'] == 'y'}
    matches = []
    for target, primary, separation in pairs:
        oid = target['moca_oid']
        if primary not in details:
            continue
        matches.append({'target':target, 'known':details[primary], 'separation_arcsec':separation,
                        'decision':existing.get((oid, primary)), 'target_decision':already_matched.get(oid),
                        'known_decision':already_matched.get(primary)})
    return matches, len(sample)


def declare(conn, cur, auth, oid, primary_oid):
    if oid == primary_oid:
        raise sr.ReviewError('Select two distinct MOCAdb objects.')
    ids = sorted((oid, primary_oid))
    locked = sr.rows(cur, """SELECT moca_oid FROM moca_objects WHERE ignored=0 AND moca_oid IN (%s,%s)
        ORDER BY moca_oid FOR UPDATE""", ids)
    if len(locked) != 2:
        raise sr.ReviewError('An object is no longer active. Rescan the sample.', 409)
    candidates, counterparts = targets(cur, [oid]), known_details(cur, [primary_oid])
    if not candidates or not counterparts:
        raise sr.ReviewError('Reference coordinates or the published L0+ type changed. Rescan the sample.', 409)
    target, known = candidates[0], counterparts[0]
    a, b = vectors((target, known))
    if arcseconds(np.linalg.norm(a - b)) > RADIUS_ARCSEC:
        raise sr.ReviewError('These objects are now more than 100″ apart. Rescan the sample.', 409)
    decisions = sr.rows(cur, """SELECT moca_oid,potential_duplicated_moca_oid FROM pcat_duplicated_vetting
        WHERE potential_duplicated_moca_oid IN (%s,%s)
          AND (classification='y' OR (potential_duplicated_moca_oid=%s AND moca_oid=%s)) FOR UPDATE""",
        (oid, primary_oid, oid, primary_oid))
    if decisions:
        raise sr.ReviewError('A duplicate decision already exists for this pair or one of its objects. Rescan the sample.', 409)
    cur.execute("""INSERT INTO pcat_duplicated_vetting
        (moca_oid,potential_duplicated_moca_oid,classification,original_designation,
         potential_duplicated_designation,original_spectral_type,potential_duplicated_spectral_type)
        VALUES (%s,%s,'y',%s,%s,%s,%s)""",
        (primary_oid, oid, known['designation'], target['designation'], known['spectral_type'], target['adopted_type']))
    cur.execute("""INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls)
        VALUES (%s,'pcat_duplicated_vetting',1,%s,0,'gagne')""",
        (auth['user'], f'sublime_findings_duplicates.py: duplicate {oid} of {primary_oid}'))
    conn.commit()
    return {'moca_oid':primary_oid, 'potential_duplicated_moca_oid':oid, 'classification':'y', 'applied':False}
