"""Headless review helpers ported from the maintained SPHEREx pipeline.

Only browser-runtime dependencies are included; no desktop GUI or workers.
"""
from __future__ import annotations


import os


import pathlib


import re


from collections.abc import Iterable


from typing import Optional


import pymysql


from .lane_utils import default_autotype_queue_table


SPIFFVIZ_MISSING_TOKEN = "none"


SOULEYMANE_CANDIDATES_TABLE = "pcat_souleymane_candidates_may20_2026_v1"


NOCLAIM_TABLE = "pcat_byw_mar9_2026"


NOCLAIM_YADU_TABLE = "pcat_kirkpatrick_yadu_2026_claim"


NOCLAIM_DISC_TOKENS = ("yadu", "tom", "bickle", "sarah", "azul", "eastonh")


GAIA_CATALOG_TABLES = ("cat_gaiadr3", "cat_gaiadr2")


DEFAULT_AUTOTYPE_CALCULATION_METHOD = "spherex_autotype"


STACKER_AUTOTYPE_CALCULATION_METHOD = "spiff_stacker_autotype"


DEFAULT_REDUCED_SPECPACKID = 55


STACKER_REDUCED_SPECPACKID = 62


SUBLIMEAPERTURE_REDUCED_SPECPACKID = 76


SUBLIMEAPERTURE_AUTOTYPE_CALCULATION_METHODS = (
    "sublimeaperture_autotype",
    "spherex_sublimeap_autotype",
)


KNOWN_FILTER_MIN_SPECTRAL_TYPE_NUMBER = 0


AUTOTYPE_CHI2_COMMENT_KEYS = (
    "robust_reduced_chi2_10pct_cap",
    "reduced_chi2_10pct_cap",
    "reduced_chi2",
)


PRIMARY_SUBLIME_CUTOUT_ROOT = pathlib.Path(os.environ.get("MOCAVIZ_SUBLIME_CUTOUT_ROOT", "/nonexistent/mocaviz-sublime-cutouts"))


FALLBACK_SUBLIME_CUTOUT_ROOT = pathlib.Path(os.environ.get("MOCAVIZ_SUBLIME_CUTOUT_FALLBACK", "/nonexistent/mocaviz-sublime-cutouts"))


PRIMARY_SUBLIME_CUTOUT_SUBDIR = "winning_spectra"


FALLBACK_SUBLIME_CUTOUT_SUBDIR = "winning_source_spectra"


BUTTON_SPECS = [
    ("bad", "0", "bad"),
    ("good", "1", "good"),
    ("good_candidate", "2", "good_candidate"),
    ("peculiar_ucd", "3", "peculiar_ucd"),
    ("contaminated_ucd", "4", "contaminated_ucd"),
    ("incomplete_but_promising", "5", "incomplete_but_promising"),
    ("unclear", "6", "unclear"),
    ("good_plus_star", "7", "good_plus_star"),
    ("good_reddened", "8", "good_reddened"),
    ("weird", "9", "weird"),
    ("galaxy", "g", "bad/galaxy"),
    ("halo", "h", "bad/halo"),
    ("reddened", "r", "bad/reddened"),
    ("snr", "s", "bad/snr"),
    ("scatter", "c", "bad/scatter"),
    ("star", "t", "bad/star"),
    ("giant", "i", "bad/giant"),
    ("early", "e", "bad/early"),
]


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default


def _mocadb_ssl_options(host):
    if str(host or "").strip().lower() in {"localhost", "127.0.0.1", "::1"}:
        return None
    return {"verify_mode": False, "check_hostname": False}


def _load_base_db_config():
    from .context import current_auth
    auth=current_auth()
    return dict(host='mocadb.ca',port=3306,user=auth['user'],password=auth['password'],database=auth['database'])


def _parse_id_list(raw: Optional[str]) -> Optional[set[int]]:
    if raw is None:
        return None
    parts = re.split(r"[\s,]+", str(raw).strip())
    out: set[int] = set()
    for part in parts:
        if not part:
            continue
        out.add(int(part))
    return out


def default_sublime_cutout_root(
    *,
    primary_root: Optional[pathlib.Path] = None,
    fallback_root: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    primary = pathlib.Path(primary_root or PRIMARY_SUBLIME_CUTOUT_ROOT)
    if primary.is_dir():
        return primary
    return pathlib.Path(fallback_root or FALLBACK_SUBLIME_CUTOUT_ROOT)


def sublime_cutout_subdir_for_root(cutout_root: pathlib.Path) -> str:
    root_path = pathlib.Path(cutout_root)
    if (
        root_path == PRIMARY_SUBLIME_CUTOUT_ROOT
        or root_path.name == PRIMARY_SUBLIME_CUTOUT_ROOT.name
    ):
        return PRIMARY_SUBLIME_CUTOUT_SUBDIR
    return FALLBACK_SUBLIME_CUTOUT_SUBDIR


def sublime_cutout_path_from_source_key(
    source_key: str,
    *,
    root: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    parts = [part.strip() for part in str(source_key).split(":")]
    if len(parts) != 3 or any(not part for part in parts):
        raise ValueError(f"Unexpected SUBLIME source_key format: {source_key!r}")
    tile_text, ra_text, dec_text = parts
    try:
        tile_int = int(tile_text)
    except ValueError as exc:
        raise ValueError(f"Unexpected SUBLIME source_key tile: {source_key!r}") from exc
    filename = f"{tile_int}_{ra_text}_{dec_text}_deep_cutout.png"
    first_root = default_sublime_cutout_root() if root is None else pathlib.Path(root)
    roots = [first_root]
    if root is None and first_root != FALLBACK_SUBLIME_CUTOUT_ROOT:
        roots.append(FALLBACK_SUBLIME_CUTOUT_ROOT)
    first_path = None
    for cutout_root in roots:
        preferred = sublime_cutout_subdir_for_root(cutout_root)
        other = "winning_source_spectra" if preferred == "winning_spectra" else "winning_spectra"
        for subdir in (preferred, other):
            plain = cutout_root / f"tile_{tile_int:05d}" / subdir / filename
            if first_path is None:
                first_path = plain
            for candidate in (plain, plain.with_name(plain.name + ".bz2")):
                if candidate.is_file():
                    return candidate
    return first_path


def fetch_queue_oids(*, stacker: bool, sublimeaperture: bool = False) -> set[int]:
    cfg = _load_base_db_config()
    queue_table = default_autotype_queue_table(
        stacker=stacker,
        sublimeaperture=sublimeaperture,
    )
    conn = pymysql.connect(
        host=str(cfg["host"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database="mocadb_private_tables",
        port=int(cfg["port"]),
        ssl=_mocadb_ssl_options(cfg["host"]),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=300,
        write_timeout=300,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT moca_oid
                FROM `{queue_table}`
                WHERE moca_oid IS NOT NULL
                """
            )
            return {int(row["moca_oid"]) for row in cur.fetchall() if row.get("moca_oid") is not None}
    finally:
        conn.close()


def fetch_souleymane_oids() -> set[int]:
    cfg = _load_base_db_config()
    conn = pymysql.connect(
        host=str(cfg["host"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database="mocadb_private_tables",
        port=int(cfg["port"]),
        ssl=_mocadb_ssl_options(cfg["host"]),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=300,
        write_timeout=300,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT mo.moca_oid
                FROM moca_objects mo
                JOIN `{SOULEYMANE_CANDIDATES_TABLE}` sou USING(moca_oid)
                WHERE mo.moca_oid IS NOT NULL
                  AND mo.ignored=0
                """,
                (),
            )
            return {int(row["moca_oid"]) for row in cur.fetchall() if row.get("moca_oid") is not None}
    finally:
        conn.close()


def fetch_claimed_oids() -> set[int]:
    cfg = _load_base_db_config()
    like_clauses = " OR ".join(["byw9.disc LIKE %s"] * len(NOCLAIM_DISC_TOKENS))
    like_patterns = tuple(f"%{token}%" for token in NOCLAIM_DISC_TOKENS)
    conn = pymysql.connect(
        host=str(cfg["host"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database="mocadb_private_tables",
        port=int(cfg["port"]),
        ssl=_mocadb_ssl_options(cfg["host"]),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=300,
        write_timeout=300,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT byw9.moca_oid
                FROM `{NOCLAIM_TABLE}` byw9
                WHERE byw9.moca_oid IS NOT NULL
                    AND byw9.disc IS NOT NULL
                    AND ({like_clauses})
                """,
                like_patterns,
            )
            claimed = {int(row["moca_oid"]) for row in cur.fetchall() if row.get("moca_oid") is not None}
            cur.execute(
                f"SELECT DISTINCT moca_oid FROM `{NOCLAIM_YADU_TABLE}` WHERE moca_oid IS NOT NULL",
                (),
            )
            claimed.update(int(row["moca_oid"]) for row in cur.fetchall() if row.get("moca_oid") is not None)
            return claimed
    finally:
        conn.close()


def _chunked_oids(values: Iterable[int], chunk_size: int = 1000) -> Iterable[tuple[int, ...]]:
    ordered_values = sorted({int(value) for value in values})
    for start in range(0, len(ordered_values), int(chunk_size)):
        yield tuple(ordered_values[start:start + int(chunk_size)])


def fetch_known_late_type_oids(
    *,
    photometric_estimate: bool,
    adoption_column: str = "public_adopted",
    source_oids: Optional[Iterable[int]] = None,
) -> set[int]:
    if adoption_column not in {"adopted", "public_adopted"}:
        raise ValueError(f"Unsupported spectral-type adoption column: {adoption_column!r}")
    photometric_flag = 1 if photometric_estimate else 0
    source_oid_set: Optional[set[int]] = None
    if source_oids is not None:
        source_oid_set = {int(oid) for oid in source_oids}
        if not source_oid_set:
            return set()
    cfg = _load_base_db_config()
    conn = pymysql.connect(
        host=str(cfg["host"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database="mocadb_private_tables",
        port=int(cfg["port"]),
        ssl=_mocadb_ssl_options(cfg["host"]),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=300,
        write_timeout=300,
    )
    try:
        with conn.cursor() as cur:
            if source_oid_set is not None:
                out: set[int] = set()
                for chunk in _chunked_oids(source_oid_set):
                    placeholders = ", ".join(["%s"] * len(chunk))
                    cur.execute(
                        f"""
                        SELECT DISTINCT known.moca_oid
                        FROM (
                            SELECT spt.moca_oid AS moca_oid
                            FROM data_spectral_types spt
                            WHERE spt.moca_oid IN ({placeholders})
                                AND spt.{adoption_column} = 1
                                AND spt.photometric_estimate = %s
                                AND spt.spectral_type_number >= {KNOWN_FILTER_MIN_SPECTRAL_TYPE_NUMBER}
                            UNION
                            SELECT dup.potential_duplicated_moca_oid AS moca_oid
                            FROM pcat_duplicated_vetting dup
                            JOIN data_spectral_types dup_spt
                                ON dup_spt.moca_oid = dup.moca_oid
                                AND dup_spt.{adoption_column} = 1
                                AND dup_spt.photometric_estimate = %s
                                AND dup_spt.spectral_type_number >= {KNOWN_FILTER_MIN_SPECTRAL_TYPE_NUMBER}
                            WHERE dup.potential_duplicated_moca_oid IN ({placeholders})
                                AND dup.classification = 'y'
                            UNION
                            SELECT dup.moca_oid AS moca_oid
                            FROM pcat_duplicated_vetting dup
                            JOIN data_spectral_types dup_reverse_spt
                                ON dup_reverse_spt.moca_oid = dup.potential_duplicated_moca_oid
                                AND dup_reverse_spt.{adoption_column} = 1
                                AND dup_reverse_spt.photometric_estimate = %s
                                AND dup_reverse_spt.spectral_type_number >= {KNOWN_FILTER_MIN_SPECTRAL_TYPE_NUMBER}
                            WHERE dup.moca_oid IN ({placeholders})
                                AND dup.classification = 'y'
                        ) known
                        WHERE known.moca_oid IS NOT NULL
                        """,
                        tuple([*chunk, photometric_flag, photometric_flag, *chunk, photometric_flag, *chunk]),
                    )
                    out.update(
                        int(row["moca_oid"])
                        for row in cur.fetchall()
                        if row.get("moca_oid") is not None
                    )
                return out
            cur.execute(
                f"""
                SELECT DISTINCT known.moca_oid
                FROM (
                    SELECT spt.moca_oid AS moca_oid
                    FROM data_spectral_types spt
                    WHERE spt.moca_oid IS NOT NULL
                        AND spt.{adoption_column} = 1
                        AND spt.photometric_estimate = %s
                        AND spt.spectral_type_number >= {KNOWN_FILTER_MIN_SPECTRAL_TYPE_NUMBER}
                    UNION
                    SELECT dup.potential_duplicated_moca_oid AS moca_oid
                    FROM pcat_duplicated_vetting dup
                    LEFT JOIN data_spectral_types dup_spt
                        ON dup_spt.moca_oid = dup.moca_oid
                        AND dup_spt.{adoption_column} = 1
                        AND dup_spt.photometric_estimate = %s
                        AND dup_spt.spectral_type_number >= {KNOWN_FILTER_MIN_SPECTRAL_TYPE_NUMBER}
                    WHERE dup.potential_duplicated_moca_oid IS NOT NULL
                        AND dup.classification = 'y'
                        AND dup_spt.moca_oid IS NOT NULL
                    UNION
                    SELECT dup.moca_oid AS moca_oid
                    FROM pcat_duplicated_vetting dup
                    LEFT JOIN data_spectral_types dup_reverse_spt
                        ON dup_reverse_spt.moca_oid = dup.potential_duplicated_moca_oid
                        AND dup_reverse_spt.{adoption_column} = 1
                        AND dup_reverse_spt.photometric_estimate = %s
                        AND dup_reverse_spt.spectral_type_number >= {KNOWN_FILTER_MIN_SPECTRAL_TYPE_NUMBER}
                    WHERE dup.moca_oid IS NOT NULL
                        AND dup.classification = 'y'
                        AND dup_reverse_spt.moca_oid IS NOT NULL
                ) known
                WHERE known.moca_oid IS NOT NULL
                """,
                (photometric_flag, photometric_flag, photometric_flag),
            )
            return {int(row["moca_oid"]) for row in cur.fetchall() if row.get("moca_oid") is not None}
    finally:
        conn.close()


def fetch_known_nonphotometric_late_type_oids(
    source_oids: Optional[Iterable[int]] = None,
) -> set[int]:
    return fetch_known_late_type_oids(
        photometric_estimate=False,
        source_oids=source_oids,
    )


def fetch_known_photometric_late_type_oids(
    source_oids: Optional[Iterable[int]] = None,
) -> set[int]:
    return fetch_known_late_type_oids(
        photometric_estimate=True,
        source_oids=source_oids,
    )


def fetch_gaia_catalog_oids(source_oids: Optional[Iterable[int]] = None) -> set[int]:
    source_oid_set: Optional[set[int]] = None
    if source_oids is not None:
        source_oid_set = {int(oid) for oid in source_oids}
        if not source_oid_set:
            return set()
    cfg = _load_base_db_config()
    conn = pymysql.connect(
        host=str(cfg["host"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database="mocadb_private_tables",
        port=int(cfg["port"]),
        ssl=_mocadb_ssl_options(cfg["host"]),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=300,
        write_timeout=300,
    )
    try:
        with conn.cursor() as cur:
            out: set[int] = set()
            for table in GAIA_CATALOG_TABLES:
                if source_oid_set is None:
                    cur.execute(
                        f"""
                        SELECT DISTINCT moca_oid
                        FROM `{table}`
                        WHERE moca_oid IS NOT NULL
                        """,
                        (),
                    )
                    out.update(
                        int(row["moca_oid"])
                        for row in cur.fetchall()
                        if row.get("moca_oid") is not None
                    )
                    continue
                for chunk in _chunked_oids(source_oid_set):
                    placeholders = ", ".join(["%s"] * len(chunk))
                    cur.execute(
                        f"""
                        SELECT DISTINCT moca_oid
                        FROM `{table}`
                        WHERE moca_oid IN ({placeholders})
                        """,
                        tuple(chunk),
                    )
                    out.update(
                        int(row["moca_oid"])
                        for row in cur.fetchall()
                        if row.get("moca_oid") is not None
                    )
            return out
    finally:
        conn.close()


def fetch_sublime2_oids(
    *,
    cnn_classes: Iterable[str] = (),
    snr_min: Optional[float] = None,
    cnnprob_min: Optional[float] = None,
    sptn_min: Optional[float] = None,
) -> set[int]:
    class_values = tuple(
        str(classification).strip()
        for classification in cnn_classes
        if str(classification).strip()
    )
    if not class_values and snr_min is None and cnnprob_min is None and sptn_min is None:
        return set()

    where_parts = ["moca_oid IS NOT NULL"]
    params: list[object] = []
    if class_values:
        placeholders = ", ".join(["%s"] * len(class_values))
        where_parts.append(f"visual_nn_classification IN ({placeholders})")
        params.extend(class_values)
    if snr_min is not None:
        where_parts.append("detection_snr >= %s")
        params.append(float(snr_min))
    if cnnprob_min is not None:
        where_parts.append("visual_nn_good_probability >= %s")
        params.append(float(cnnprob_min))
    if sptn_min is not None:
        where_parts.append("autotype_spectral_type_number >= %s")
        params.append(float(sptn_min))

    cfg = _load_base_db_config()
    conn = pymysql.connect(
        host=str(cfg["host"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database="mocadb_private_tables",
        port=int(cfg["port"]),
        ssl=_mocadb_ssl_options(cfg["host"]),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=300,
        write_timeout=300,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT moca_oid
                FROM `pcat_sublime_candidates_v2`
                WHERE """ + " AND ".join(where_parts),
                tuple(params),
            )
            return {int(row["moca_oid"]) for row in cur.fetchall() if row.get("moca_oid") is not None}
    finally:
        conn.close()


def _review_autotype_calculation_methods(*, stacker: bool, sublimeaperture: bool) -> tuple[str, ...]:
    if sublimeaperture:
        return SUBLIMEAPERTURE_AUTOTYPE_CALCULATION_METHODS
    if stacker:
        return (STACKER_AUTOTYPE_CALCULATION_METHOD,)
    return (DEFAULT_AUTOTYPE_CALCULATION_METHOD,)


def _review_reduced_specpackid(*, stacker: bool, sublimeaperture: bool) -> int:
    if sublimeaperture:
        return SUBLIMEAPERTURE_REDUCED_SPECPACKID
    if stacker:
        return STACKER_REDUCED_SPECPACKID
    return DEFAULT_REDUCED_SPECPACKID


def _comment_numeric_value_sql(key: str) -> str:
    return (
        f"CASE WHEN comments LIKE '%%{key}=%%' THEN "
        f"CAST(NULLIF(TRIM(SUBSTRING_INDEX(SUBSTRING_INDEX(comments, '{key}=', -1), ';', 1)), "
        "'NULL') AS DECIMAL(20,6)) "
        "ELSE NULL END"
    )


def fetch_autotype_chi2_oids(
    chi2_max: Optional[float] = None,
    *,
    chi2_min: Optional[float] = None,
    stacker: bool,
    sublimeaperture: bool,
) -> set[int]:
    if chi2_min is None and chi2_max is None:
        return set()

    calculation_methods = _review_autotype_calculation_methods(
        stacker=stacker,
        sublimeaperture=sublimeaperture,
    )
    method_placeholders = ", ".join(["%s"] * len(calculation_methods))
    chi2_value_sql = "COALESCE(" + ", ".join(
        _comment_numeric_value_sql(key) for key in AUTOTYPE_CHI2_COMMENT_KEYS
    ) + ")"
    chi2_where_parts = [
        f"{chi2_value_sql} IS NOT NULL",
    ]
    chi2_params: list[object] = []
    if chi2_min is not None:
        chi2_where_parts.append(f"{chi2_value_sql} >= %s")
        chi2_params.append(float(chi2_min))
    if chi2_max is not None:
        chi2_where_parts.append(f"{chi2_value_sql} <= %s")
        chi2_params.append(float(chi2_max))

    cfg = _load_base_db_config()
    conn = pymysql.connect(
        host=str(cfg["host"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database="mocadb_private_tables",
        port=int(cfg["port"]),
        ssl=_mocadb_ssl_options(cfg["host"]),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=300,
        write_timeout=300,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT moca_oid
                FROM data_spectral_types
                WHERE moca_oid IS NOT NULL
                    AND calculation_method IN ({method_placeholders})
                    AND comments IS NOT NULL
                    AND {" AND ".join(chi2_where_parts)}
                """,
                tuple([*calculation_methods, *chi2_params]),
            )
            return {int(row["moca_oid"]) for row in cur.fetchall() if row.get("moca_oid") is not None}
    finally:
        conn.close()


def parse_spiffviz_class_list(value: Optional[str], *, option_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    classes: list[str] = []
    seen: set[str] = set()
    for raw_part in str(value).split(","):
        class_value = raw_part.strip()
        if not class_value:
            continue
        if class_value in seen:
            continue
        seen.add(class_value)
        classes.append(class_value)
    if not classes:
        raise ValueError(f"{option_name} requires at least one non-empty class")
    return tuple(classes)


def _split_missing_spiffviz_token(classes: Iterable[str]) -> tuple[tuple[str, ...], bool]:
    real_classes: list[str] = []
    include_missing = False
    for class_value in classes:
        if class_value.lower() == SPIFFVIZ_MISSING_TOKEN:
            include_missing = True
        else:
            real_classes.append(class_value)
    return tuple(real_classes), include_missing


def _normalize_visual_vetting_tables(visual_vetting_tables: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(table).strip()
            for table in visual_vetting_tables
            if str(table).strip()
        )
    )


def fetch_spiffviz_oids(
    classifications: Iterable[str],
    *,
    option_name: str,
    visual_vetting_tables: Iterable[str],
) -> set[int]:
    class_values = tuple(
        str(classification).strip()
        for classification in classifications
        if str(classification).strip()
    )
    if not class_values:
        raise ValueError(f"{option_name} requires at least one non-empty classification")
    if any(class_value.lower() == SPIFFVIZ_MISSING_TOKEN for class_value in class_values):
        raise ValueError(f"{option_name} none is handled by the local PNG missing-entry filter")
    table_names = _normalize_visual_vetting_tables(visual_vetting_tables)
    if not table_names:
        raise ValueError(f"{option_name} requires at least one visual-vetting table")
    cfg = _load_base_db_config()
    out: set[int] = set()
    conn = pymysql.connect(
        host=str(cfg["host"]),
        user=str(cfg["user"]),
        password=str(cfg["password"]),
        database="mocadb_private_tables",
        port=int(cfg["port"]),
        ssl=_mocadb_ssl_options(cfg["host"]),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=300,
        write_timeout=300,
    )
    try:
        with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(class_values))
            for visual_vetting_table in table_names:
                cur.execute(
                    f"""
                    SELECT DISTINCT moca_oid
                    FROM `{visual_vetting_table}`
                    WHERE moca_oid IS NOT NULL
                      AND classification IN ({placeholders})
                    """,
                    class_values,
                )
                out.update(
                    int(row["moca_oid"])
                    for row in cur.fetchall()
                    if row.get("moca_oid") is not None
                )
            return out
    finally:
        conn.close()
