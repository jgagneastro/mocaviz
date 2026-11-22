"""Spectrum identity and quality for read-only SUBLIME selections."""
GOOD = ('good', 'peculiar_ucd', 'contaminated_ucd', 'good_plus_star', 'good_reddened')
USABLE = (*GOOD, 'good_candidate', 'incomplete_but_promising', 'late_m', 'weird')
TABLE = 'pcat_spherex_spectrum_reviews'


def has_spectrum_reviews(cur):
    cur.execute("SELECT COUNT(*) AS present FROM information_schema.tables "
                "WHERE table_schema=DATABASE() AND table_name=%s", (TABLE,))
    return bool(cur.fetchone()['present'])


def labels_sql(values):
    # Only fixed, application-defined labels may be passed here.
    return ','.join("'" + value + "'" for value in values)


def reviews_sql(table, pack, canonical, *, with_sources=False):
    """One row per matched extraction. Old OID labels need migration-grade evidence."""
    columns = "v.classification,v.sources" if with_sources else "v.classification"
    if canonical:
        return (f"(SELECT s.moca_oid,s.moca_specid,{columns} FROM {TABLE} v "
                f"JOIN moca_spectra s ON s.moca_specid=v.moca_specid WHERE v.review_kind='quality' "
                f"AND s.moca_specpackid={int(pack)})")
    token = ("REGEXP_SUBSTR(LOWER(COALESCE(v.sources,'')),"
             "'(^|[^a-z0-9_])(moca_specid|specid)[[:space:]]*[=:][[:space:]]*[0-9]+')")
    return (f"(SELECT s.moca_oid,s.moca_specid,{columns} FROM `{table}` v "
            f"JOIN moca_spectra s ON s.moca_oid=v.moca_oid AND s.moca_specpackid={int(pack)} "
            f"WHERE CASE WHEN {token}<>'' THEN s.moca_specid=CAST(REGEXP_SUBSTR({token},'[0-9]+$') AS UNSIGNED) "
            "ELSE s.created_timestamp<=v.modified_timestamp AND NOT EXISTS "
            "(SELECT 1 FROM moca_spectra sibling WHERE sibling.moca_oid=s.moca_oid "
            "AND sibling.moca_specpackid=s.moca_specpackid AND sibling.moca_specid<>s.moca_specid) END)")


def displayable_sql(spectrum='s', review='v'):
    return (f"(LOWER({review}.classification) IN ({labels_sql(USABLE)}) OR "
            f"({review}.classification IS NULL AND {spectrum}.ignored=0))")
