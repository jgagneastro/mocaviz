from __future__ import annotations

import copy
import math
import os
import random
import re
import time
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
from flask import Flask, Response, jsonify, request, send_from_directory
from sqlalchemy import create_engine, text


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

DEFAULT_HOST = "104.248.106.21"
DEFAULT_USERNAME = "public"
DEFAULT_PASSWORD = "z@nUg_2h7_%?31y88"
DEFAULT_DBNAME = "mocadb"

CACHE_SECONDS = int(os.environ.get("BD_COLORS_FAST_CACHE_SECONDS", "900"))
BROAD_QUERY_MAX_OBJECTS = 1000000
OPTIONAL_QUERY_MAX_OBJECTS = max(
    int(os.environ.get("BD_COLORS_FAST_OPTIONAL_MAX_OBJECTS", str(BROAD_QUERY_MAX_OBJECTS))),
    BROAD_QUERY_MAX_OBJECTS,
)
DEFAULT_PHOTOMETRY_PSIDS = ("mko_jmag", "mko_kmag")
SIMPLE_PHOTOMETRY_PREFIX = "simple:"
SIMPLE_PHOTOMETRY_BANDS = ("g", "r", "i", "z", "y", "J", "H", "K", "W1", "W2", "W3", "W4")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:+-]+$")
AXIS_TYPES = {"spectral_type", "color", "absolute_magnitude", "spectral_index", "equivalent_width"}
DEFAULT_AXIS_SPECS = {
    "x": ("color", "simple:J", "simple:K"),
    "y": ("absolute_magnitude", "simple:J", ""),
}

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

_BOOTSTRAP_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_FEATURE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PLOTLY_JS: str | None = None


def _db_config(args: dict[str, Any]) -> dict[str, str]:
    return {
        "host": args.get("host") or os.environ.get("MOCA_HOST", DEFAULT_HOST),
        "username": args.get("user") or os.environ.get("MOCA_USERNAME", DEFAULT_USERNAME),
        "password": args.get("pwd") or os.environ.get("MOCA_PASSWORD", DEFAULT_PASSWORD),
        "dbname": args.get("dbase") or os.environ.get("MOCA_DBNAME", DEFAULT_DBNAME),
    }


def _is_private_db(args: dict[str, Any]) -> bool:
    return str(_db_config(args)["dbname"]).strip("`").lower() == "mocadb_private_tables"


def _connection_string(args: dict[str, Any]) -> str:
    cfg = _db_config(args)
    password = quote_plus(cfg["password"])
    return f"mysql+pymysql://{cfg['username']}:{password}@{cfg['host']}/{cfg['dbname']}"


@lru_cache(maxsize=8)
def _engine(connection_string: str):
    return create_engine(connection_string, pool_pre_ping=True, pool_recycle=1800)


def _parse_spt_label(label: str | None) -> float | None:
    if not label:
        return None
    label = label.strip().upper()
    classes = {"O": 0, "B": 10, "A": 20, "F": 30, "G": 40, "K": 50, "M": 60, "L": 70, "T": 80, "Y": 90}
    if len(label) < 2 or label[0] not in classes:
        return None
    try:
        return classes[label[0]] + float(label[1:]) - 60
    except ValueError:
        return None


def _spt_window(args: dict[str, Any]) -> tuple[float, float | None, str]:
    raw = (args.get("spt_range") or "L2+").replace("_", "-").strip()
    raw_upper = raw.upper()
    if raw_upper.startswith(">="):
        raw_upper = raw_upper[2:].strip() + "+"
    if raw_upper.endswith("+"):
        spt_min = _parse_spt_label(raw_upper[:-1])
        if spt_min is None:
            return 12.0, None, "L2+"
        return spt_min, None, f"{raw_upper[:-1].strip()}+"
    if "-" not in raw:
        spt_min = _parse_spt_label(raw_upper)
        if spt_min is None:
            return 12.0, None, "L2+"
        return spt_min, None, f"{raw_upper}+"
    start, end = raw.split("-", 1)
    spt_min = _parse_spt_label(start)
    spt_max = _parse_spt_label(end)
    if spt_min is None or spt_max is None or spt_min > spt_max:
        return 12.0, None, "L2+"
    return spt_min, spt_max, f"{start.strip().upper()}-{end.strip().upper()}"


def _highlight_oids(args: dict[str, Any]) -> list[int]:
    raw = args.get("moca_oid") or args.get("oid") or ""
    oids: list[int] = []
    for item in raw.split(","):
        item = item.strip()
        if item.isdigit():
            oids.append(int(item))
    return oids


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _include_photometric_spt(args: dict[str, Any]) -> bool:
    return any(
        _as_bool(args.get(key))
        for key in ("photspt", "include_photspt", "include_photometric_spt")
    )


def _include_photometric_dist(args: dict[str, Any]) -> bool:
    return any(
        _as_bool(args.get(key))
        for key in ("photdist", "include_photdist", "include_photometric_dist")
    )


def _object_limit(args: dict[str, Any], spt_min: float, include_photometric_spt: bool) -> int | None:
    is_broad_query = include_photometric_spt or spt_min < 10
    raw = args.get("max_objects") or os.environ.get("BD_COLORS_FAST_MAX_OBJECTS")
    if raw is None and is_broad_query:
        raw = str(OPTIONAL_QUERY_MAX_OBJECTS)
    if raw is None:
        return None
    if str(raw).strip().lower() in {"0", "none", "uncapped", "all"}:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = OPTIONAL_QUERY_MAX_OBJECTS
    if is_broad_query:
        value = max(value, OPTIONAL_QUERY_MAX_OBJECTS)
    return max(1, min(value, 1000000))


def _range_sql(args: dict[str, Any]) -> tuple[str, dict[str, Any], str, bool, float]:
    spt_min, spt_max, label = _spt_window(args)
    include_photometric_spt = _include_photometric_spt(args)
    oids = _highlight_oids(args)
    if spt_max is None:
        spt_clause = "dst.spectral_type_number >= :spt_min"
        params = {"spt_min": spt_min}
    else:
        spt_clause = "dst.spectral_type_number BETWEEN :spt_min AND :spt_max"
        params = {"spt_min": spt_min, "spt_max": spt_max}
    phot_clause = "1 = 1" if include_photometric_spt else "dst.photometric_estimate = 0"
    oid_clause = ""
    if oids:
        oid_clause = " OR dst.moca_oid IN (" + ",".join(str(oid) for oid in oids) + ")"
    return f"(({spt_clause} AND {phot_clause}){oid_clause})", params, label, include_photometric_spt, spt_min


def _oid_filter_sql(alias: str, oids: list[int]) -> str:
    if not oids:
        return "0 = 1"
    oid_list = ",".join(str(int(oid)) for oid in oids)
    return f"{alias}.moca_oid IN ({oid_list})"


def _simple_band_option_rows(counts: dict[str, int] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for band in SIMPLE_PHOTOMETRY_BANDS:
        row: dict[str, Any] = {
            "value": f"{SIMPLE_PHOTOMETRY_PREFIX}{band}",
            "system_band_simple": band,
            "label": band,
        }
        if counts is not None:
            row["n_data"] = int(counts.get(band, 0))
        rows.append(row)
    return rows


def _normalize_simple_band(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if raw.startswith(SIMPLE_PHOTOMETRY_PREFIX):
        raw = raw[len(SIMPLE_PHOTOMETRY_PREFIX):]
    aliases = {band.lower(): band for band in SIMPLE_PHOTOMETRY_BANDS}
    return aliases.get(raw.lower())


def _requested_photometry_psids(args: dict[str, Any]) -> list[str]:
    requested: list[str] = []
    raw_psids = args.get("psids")
    if raw_psids:
        requested.extend(item.strip() for item in raw_psids.split(","))
    else:
        for axis in ("x", "y"):
            axis_type = args.get(f"{axis}axis_type")
            value1 = args.get(f"{axis}axis_value_1")
            value2 = args.get(f"{axis}axis_value_2")
            if axis_type in {"color", "absolute_magnitude"} and value1:
                requested.append(value1)
            if axis_type == "color" and value2:
                requested.append(value2)
        if not requested:
            requested.extend(DEFAULT_PHOTOMETRY_PSIDS)

    clean: list[str] = []
    for psid in requested:
        if (
            psid
            and not _normalize_simple_band(psid)
            and SAFE_ID_RE.match(psid)
            and psid not in clean
        ):
            clean.append(psid)
    return clean


def _requested_photometry_simplebands(args: dict[str, Any]) -> list[str]:
    requested: list[str] = []
    raw_simplebands = args.get("simplebands")
    if raw_simplebands:
        requested.extend(item.strip() for item in raw_simplebands.split(","))
    else:
        for axis in ("x", "y"):
            axis_type = args.get(f"{axis}axis_type")
            value1 = args.get(f"{axis}axis_value_1")
            value2 = args.get(f"{axis}axis_value_2")
            if axis_type in {"color", "absolute_magnitude"} and value1:
                requested.append(value1)
            if axis_type == "color" and value2:
                requested.append(value2)
        if not requested:
            requested.extend(("simple:J", "simple:K"))

    clean: list[str] = []
    for value in requested:
        band = _normalize_simple_band(value)
        if band and band not in clean:
            clean.append(band)
    return clean


def _request_all_photometry(args: dict[str, Any]) -> bool:
    return str(args.get("psids") or "").strip().lower() in {"all", "*"}


def _request_all_spectral_indices(args: dict[str, Any]) -> bool:
    return _as_bool(args.get("bulk")) or str(args.get("siids") or "").strip().lower() in {"all", "*"}


def _request_all_sequences(args: dict[str, Any]) -> bool:
    return _as_bool(args.get("bulk")) or str(args.get("sequences") or "").strip().lower() in {"all", "*"}


def _requested_spectral_index_ids(args: dict[str, Any]) -> list[str]:
    if _request_all_spectral_indices(args):
        return []
    requested: list[str] = []
    for axis in ("x", "y"):
        axis_type = args.get(f"{axis}axis_type")
        value1 = args.get(f"{axis}axis_value_1")
        if axis_type == "spectral_index" and value1:
            requested.append(value1)
    clean: list[str] = []
    for siid in requested:
        if siid and SAFE_ID_RE.match(siid) and siid not in clean:
            clean.append(siid)
    return clean


def _axis_spec(args: dict[str, Any], axis: str) -> tuple[str, str, str]:
    default_type, default_value1, default_value2 = DEFAULT_AXIS_SPECS[axis]
    axis_type = args.get(f"{axis}axis_type") or default_type
    if axis_type not in AXIS_TYPES:
        axis_type = default_type
    value1 = args.get(f"{axis}axis_value_1") or default_value1
    value2 = args.get(f"{axis}axis_value_2") or default_value2
    if not SAFE_ID_RE.match(value1):
        value1 = default_value1
    if value2 and not SAFE_ID_RE.match(value2):
        value2 = default_value2
    return axis_type, value1, value2


def _sequence_key(args: dict[str, Any]) -> str:
    return "|".join(",".join(_axis_spec(args, axis)) for axis in ("x", "y"))


def _sequence_filter_sql(args: dict[str, Any]) -> tuple[str, dict[str, str]]:
    clauses: list[str] = []
    params: dict[str, str] = {}
    for axis in ("x", "y"):
        axis_type, value1, value2 = _axis_spec(args, axis)
        params[f"{axis}_type"] = axis_type
        clauses.append(f"ms.{axis}axis_type_bdcolapp = :{axis}_type")
        if axis_type != "spectral_type":
            clauses.append(_sequence_value_filter_sql(axis, 1, value1, params))
        if axis_type == "color":
            clauses.append(_sequence_value_filter_sql(axis, 2, value2, params))
    return " AND ".join(clauses), params


def _sequence_value_filter_sql(axis: str, index: int, value: str, params: dict[str, str]) -> str:
    column = f"ms.{axis}axis_value_{index}_bdcolapp"
    value_key = f"{axis}_value{index}"
    params[value_key] = value
    simple_band = _normalize_simple_band(value)
    if not simple_band:
        return f"{column} = :{value_key}"

    band_key = f"{axis}_simpleband{index}"
    params[band_key] = simple_band
    return f"""(
        {column} = :{value_key}
        OR {column} IN (
            SELECT ps.moca_psid
            FROM moca_photometry_systems ps
            WHERE ps.system_band_simple = :{band_key}
        )
    )"""


def _psid_filter_sql(alias: str, psids: list[str]) -> tuple[str, dict[str, str]]:
    if not psids:
        return "1 = 1", {}
    params = {f"psid_{idx}": psid for idx, psid in enumerate(psids)}
    placeholders = ",".join(f":psid_{idx}" for idx in range(len(psids)))
    return f"{alias}.moca_psid IN ({placeholders})", params


def _photometry_filter_sql(alias: str, psids: list[str], simplebands: list[str]) -> tuple[str, dict[str, str]]:
    clauses: list[str] = []
    params: dict[str, str] = {}
    if psids:
        psid_filter, psid_params = _psid_filter_sql(alias, psids)
        clauses.append(psid_filter)
        params.update(psid_params)
    if simplebands:
        band_params = {f"simpleband_{idx}": band for idx, band in enumerate(simplebands)}
        placeholders = ",".join(f":simpleband_{idx}" for idx in range(len(simplebands)))
        clauses.append(
            f"({alias}.adopted_simpleband = 1 AND {alias}.system_band_simple IN ({placeholders}))"
        )
        params.update(band_params)
    if not clauses:
        return "0 = 1", {}
    return "(" + " OR ".join(clauses) + ")", params


def _safe_id_filter_sql(alias: str, column: str, values: list[str], prefix: str) -> tuple[str, dict[str, str]]:
    clean = [value for value in values if value and SAFE_ID_RE.match(value)]
    if not clean:
        return "1 = 1", {}
    params = {f"{prefix}_{idx}": value for idx, value in enumerate(clean)}
    placeholders = ",".join(f":{prefix}_{idx}" for idx in range(len(clean)))
    return f"{alias}.{column} IN ({placeholders})", params


def _cache_key(args: dict[str, Any]) -> str:
    cfg = _db_config(args)
    spt_min, spt_max, _label = _spt_window(args)
    oids = ",".join(str(oid) for oid in _highlight_oids(args))
    limit = _object_limit(args, spt_min, _include_photometric_spt(args))
    return "|".join([
        cfg["host"],
        cfg["username"],
        cfg["dbname"],
        str(spt_min),
        str(spt_max),
        str(_include_photometric_spt(args)),
        str(_include_photometric_dist(args)),
        str(limit),
        (
            "all-photometry"
            if _request_all_photometry(args)
            else ",".join(_requested_photometry_psids(args))
            + "|simple:"
            + ",".join(_requested_photometry_simplebands(args))
        ),
        _sequence_key(args),
        oids,
    ])


def _pythonize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, Decimal)):
        value = float(value)
        return value if math.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    clean = df.replace({np.nan: None})
    output: list[dict[str, Any]] = []
    for row in clean.to_dict(orient="records"):
        output.append({key: _pythonize(value) for key, value in row.items()})
    return output


def _read_sql(conn, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    return pd.read_sql_query(text(sql), conn, params=params or {})


def _selection_sql_parts(args: dict[str, Any]) -> tuple[str, dict[str, Any], str, bool, int | None]:
    range_clause, range_params, spt_label, include_photometric_spt, spt_min = _range_sql(args)
    object_limit = _object_limit(args, spt_min, include_photometric_spt)
    limit_clause = f"\n            LIMIT {object_limit}" if object_limit is not None else ""
    return range_clause, range_params, spt_label, include_photometric_spt, object_limit, limit_clause


def _selected_oids_from_db(conn, args: dict[str, Any]) -> list[int]:
    range_clause, range_params, _spt_label, _include_photometric_spt, _object_limit, limit_clause = _selection_sql_parts(args)
    rows = _records(_read_sql(conn, """
        SELECT dst.moca_oid
        FROM data_spectral_types dst
        WHERE dst.adopted = 1
            AND dst.spectral_type_number IS NOT NULL
            AND {range_clause}
        ORDER BY dst.spectral_type_number, dst.moca_oid{limit_clause}
    """.format(range_clause=range_clause, limit_clause=limit_clause), range_params))
    return [int(row["moca_oid"]) for row in rows if row.get("moca_oid") is not None]


def _load_bootstrap_from_db(args: dict[str, Any]) -> dict[str, Any]:
    cache_key = _cache_key(args)
    now = time.time()
    cached = _BOOTSTRAP_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = dict(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    range_clause, range_params, spt_label, include_photometric_spt, object_limit, limit_clause = _selection_sql_parts(args)
    with engine.connect() as conn:
        timings: dict[str, float | int] = {}

        def read_records(name: str, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            started = time.time()
            rows = _records(_read_sql(conn, sql, params))
            timings[name] = round(time.time() - started, 3)
            timings[f"{name}_rows"] = len(rows)
            return rows

        photometry_options = read_records("photometry_options", """
            SELECT moca_psid, name, system_band_simple
            FROM moca_photometry_systems
            ORDER BY name, moca_psid
        """)

        spectral_index_options = read_records("spectral_index_options", """
            SELECT moca_siid, description
            FROM moca_spectral_indices
            ORDER BY description, moca_siid
        """)

        equivalent_width_options = read_records("equivalent_width_options", """
            SELECT moca_spid, description
            FROM moca_chemical_species
            ORDER BY description, moca_spid
        """)

        objects = read_records("objects", """
            SELECT
                dst.moca_oid,
                mo.designation AS designation,
                dst.spectral_type_number,
                dst.spectral_type_unc,
                dst.spectral_class,
                dst.suffix,
                dst.gravity_class,
                dst.complete_spectral_type,
                dst.photometric_estimate AS spectral_type_photometric_estimate,
                COALESCE(spt_pub.name, CAST(spt_pub.moca_pid AS CHAR), dst.origin, 'No reference') AS spt_ref,
                mopc.all_prop_confidences
            FROM data_spectral_types dst
            JOIN moca_objects mo
                ON mo.moca_oid = dst.moca_oid
            LEFT JOIN moca_publications spt_pub
                ON spt_pub.moca_pid = dst.moca_pid
            LEFT JOIN mechanics_object_properties_combined mopc
                ON mopc.moca_oid = dst.moca_oid
            WHERE dst.adopted = 1
                AND dst.spectral_type_number IS NOT NULL
                AND {range_clause}
            ORDER BY dst.spectral_type_number, dst.moca_oid{limit_clause}
        """.format(range_clause=range_clause, limit_clause=limit_clause), range_params)

        selected_oids = [int(row["moca_oid"]) for row in objects if row.get("moca_oid") is not None]
        dd_oid_filter = _oid_filter_sql("dd", selected_oids)
        include_photometric_dist = _include_photometric_dist(args)
        dd_phot_filter = "1 = 1" if include_photometric_dist else "dd.photometric_estimate = 0"
        dp_oid_filter = _oid_filter_sql("dp", selected_oids)
        if _request_all_photometry(args):
            photometry_psids = [
                str(row["moca_psid"])
                for row in photometry_options
                if row.get("moca_psid") is not None
            ]
            photometry_simplebands = list(SIMPLE_PHOTOMETRY_BANDS)
        else:
            photometry_psids = _requested_photometry_psids(args)
            photometry_simplebands = _requested_photometry_simplebands(args)
        dp_phot_filter, dp_phot_params = _photometry_filter_sql("dp", photometry_psids, photometry_simplebands)

        distances = read_records("distances", """
            SELECT
                dd.id,
                dd.moca_oid,
                dd.distance_pc,
                dd.distance_pc_unc,
                dd.dmod,
                dd.dmod_unc,
                dd.photometric_estimate,
                COALESCE(
                    distance_pub.name,
                    CAST(distance_pub.moca_pid AS CHAR),
                    parallax_pub.name,
                    CAST(parallax_pub.moca_pid AS CHAR),
                    dplx.origin,
                    dd.calculation_method,
                    dd.origin,
                    'No reference'
                ) AS distance_ref
            FROM data_distances dd
            LEFT JOIN moca_publications distance_pub
                ON distance_pub.moca_pid = dd.moca_pid
            LEFT JOIN data_parallaxes dplx
                ON dplx.id = dd.parallax_id
            LEFT JOIN moca_publications parallax_pub
                ON parallax_pub.moca_pid = dplx.moca_pid
            WHERE dd.adopted = 1
                AND dd.distance_pc IS NOT NULL
                AND {dd_phot_filter}
                AND {dd_oid_filter}
            ORDER BY dd.moca_oid, dd.photometric_estimate
        """.format(dd_oid_filter=dd_oid_filter, dd_phot_filter=dd_phot_filter))

        photometry = read_records("photometry", """
            SELECT
                dp.moca_oid,
                dp.moca_psid,
                MIN(dp.system_band_simple) AS system_band_simple,
                MAX(dp.adopted_simpleband) AS adopted_simpleband,
                MIN(dp.magnitude) AS magnitude,
                MIN(dp.magnitude_unc) AS magnitude_unc,
                MIN(ps.name) AS name,
                MIN(COALESCE(
                    phot_pub.name,
                    CAST(phot_pub.moca_pid AS CHAR),
                    dp.origin,
                    dp.calculation_method,
                    'No reference'
                )) AS photometry_ref
            FROM data_photometry dp
            JOIN moca_photometry_systems ps
                ON ps.moca_psid = dp.moca_psid
            LEFT JOIN moca_publications phot_pub
                ON phot_pub.moca_pid = dp.moca_pid
            WHERE dp.adopted = 1
                AND dp.magnitude IS NOT NULL
                AND dp.magnitude_unc IS NOT NULL
                AND {dp_phot_filter}
                AND {dp_oid_filter}
            GROUP BY dp.moca_oid, dp.moca_psid
            ORDER BY dp.moca_oid, dp.moca_psid
        """.format(dp_oid_filter=dp_oid_filter, dp_phot_filter=dp_phot_filter), dp_phot_params)

        median_colors = read_records("median_colors", """
            SELECT
                moca_pid,
                moca_psid1,
                moca_psid2,
                spectral_type_number,
                color_mag,
                n_obj
            FROM data_median_colors
            WHERE moca_pid = 'Best18'
                AND spectral_type_number IS NOT NULL
                AND color_mag IS NOT NULL
            ORDER BY moca_psid1, moca_psid2, spectral_type_number
        """)

        sequence_filter, sequence_params = _sequence_filter_sql(args)
        sequences = read_records("sequences", """
            SELECT
                ms.moca_seqid,
                ms.name_bdcolapp,
                ms.xaxis_type_bdcolapp,
                ms.yaxis_type_bdcolapp,
                ms.xaxis_value_1_bdcolapp,
                ms.xaxis_value_2_bdcolapp,
                ms.yaxis_value_1_bdcolapp,
                ms.yaxis_value_2_bdcolapp,
                das.xdata,
                das.ydata,
                das.yerror
            FROM moca_sequences ms
            JOIN data_astro_sequences das
                ON das.moca_seqid = ms.moca_seqid
            WHERE ms.display_in_bdcolapp = 1
                AND ms.xaxis_type_bdcolapp IS NOT NULL
                AND ms.yaxis_type_bdcolapp IS NOT NULL
                AND {sequence_filter}
            ORDER BY ms.moca_seqid, das.xdata
        """.format(sequence_filter=sequence_filter), sequence_params)

    payload = {
        "options": {
            "photometry": photometry_options,
            "simplePhotometry": _simple_band_option_rows(),
            "spectralIndices": spectral_index_options,
            "equivalentWidths": equivalent_width_options,
        },
        "catalog": {
            "objects": objects,
            "distances": distances,
            "photometry": photometry,
            "designations": [],
            "spectralIndices": [],
            "equivalentWidths": [],
            "ages": [],
            "medianColors": median_colors,
            "sequences": sequences,
        },
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "spt_range": spt_label,
            "include_photometric_spt": include_photometric_spt,
            "include_photometric_dist": include_photometric_dist,
            "max_objects": object_limit,
            "object_limit_applied": object_limit is not None and len(objects) >= object_limit,
            "object_count": len(objects),
            "photometry_count": len(photometry),
            "photometry_psids": photometry_psids,
            "photometry_simplebands": photometry_simplebands,
            "sequence_key": _sequence_key(args),
            "lazy_features": ["designations", "spectralIndices", "equivalentWidths", "ages"],
            "timings": timings,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _BOOTSTRAP_CACHE[cache_key] = (now, payload)
    return payload


def _load_feature_from_db(args: dict[str, Any], feature: str) -> dict[str, Any]:
    if feature not in {"distances", "photometry", "photometryOptions", "sequences", "designations", "spectralIndices", "equivalentWidths", "ages"}:
        raise ValueError(f"Unknown feature: {feature}")

    cache_key = f"{_cache_key(args)}|{feature}"
    now = time.time()
    cached = _FEATURE_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = dict(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    feature_meta: dict[str, Any] = {}
    with engine.connect() as conn:
        if feature == "sequences":
            selected_oids = []
            if _request_all_sequences(args):
                sequence_filter, sequence_params = "1 = 1", {}
                feature_meta["all_sequences_loaded"] = True
            else:
                sequence_filter, sequence_params = _sequence_filter_sql(args)
            rows = _records(_read_sql(conn, """
                SELECT
                    ms.moca_seqid,
                    ms.name_bdcolapp,
                    ms.xaxis_type_bdcolapp,
                    ms.yaxis_type_bdcolapp,
                    ms.xaxis_value_1_bdcolapp,
                    ms.xaxis_value_2_bdcolapp,
                    ms.yaxis_value_1_bdcolapp,
                    ms.yaxis_value_2_bdcolapp,
                    das.xdata,
                    das.ydata,
                    das.yerror
                FROM moca_sequences ms
                JOIN data_astro_sequences das
                    ON das.moca_seqid = ms.moca_seqid
                WHERE ms.display_in_bdcolapp = 1
                    AND ms.xaxis_type_bdcolapp IS NOT NULL
                    AND ms.yaxis_type_bdcolapp IS NOT NULL
                    AND {sequence_filter}
                ORDER BY ms.moca_seqid, das.xdata
            """.format(sequence_filter=sequence_filter), sequence_params))
        else:
            selected_oids = _selected_oids_from_db(conn, args)
            oid_filter = {
                "distances": _oid_filter_sql("dd", selected_oids),
                "photometry": _oid_filter_sql("dp", selected_oids),
                "photometryOptions": _oid_filter_sql("dp", selected_oids),
                "designations": _oid_filter_sql("mad", selected_oids),
                "spectralIndices": _oid_filter_sql("dsi", selected_oids),
                "equivalentWidths": _oid_filter_sql("dew", selected_oids),
                "ages": _oid_filter_sql("cbs", selected_oids),
            }[feature]
        if feature == "sequences":
            pass
        elif feature == "designations":
            rows = _records(_read_sql(conn, """
                SELECT
                    mad.moca_oid,
                    mad.designation
                FROM mechanics_all_designations mad
                WHERE mad.designation IS NOT NULL
                    AND mad.designation <> ''
                    AND {oid_filter}
                ORDER BY mad.moca_oid, mad.designation
            """.format(oid_filter=oid_filter)))
        elif feature == "photometryOptions":
            rows = _records(_read_sql(conn, """
                SELECT
                    ps.moca_psid,
                    ps.name,
                    ps.system_band_simple,
                    COUNT(DISTINCT dp.moca_oid) AS n_data
                FROM moca_photometry_systems ps
                JOIN data_photometry dp
                    ON dp.moca_psid = ps.moca_psid
                WHERE dp.adopted = 1
                    AND dp.magnitude IS NOT NULL
                    AND dp.magnitude_unc IS NOT NULL
                    AND {oid_filter}
                GROUP BY ps.moca_psid, ps.name, ps.system_band_simple
                HAVING n_data > 0
                ORDER BY ps.name, ps.moca_psid
            """.format(oid_filter=oid_filter)))
            simple_filter, simple_params = _safe_id_filter_sql(
                "dp",
                "system_band_simple",
                list(SIMPLE_PHOTOMETRY_BANDS),
                "simpleband",
            )
            simple_rows = _records(_read_sql(conn, """
                SELECT
                    dp.system_band_simple,
                    COUNT(DISTINCT dp.moca_oid) AS n_data
                FROM data_photometry dp
                WHERE dp.adopted = 1
                    AND dp.magnitude IS NOT NULL
                    AND dp.magnitude_unc IS NOT NULL
                    AND dp.adopted_simpleband = 1
                    AND {simple_filter}
                    AND {oid_filter}
                GROUP BY dp.system_band_simple
            """.format(simple_filter=simple_filter, oid_filter=oid_filter), simple_params))
            simple_counts = {
                _normalize_simple_band(str(row["system_band_simple"])): int(row["n_data"])
                for row in simple_rows
                if _normalize_simple_band(str(row.get("system_band_simple") or ""))
            }
            feature_meta["simple_photometry_options"] = _simple_band_option_rows(simple_counts)
        elif feature == "distances":
            include_photometric_dist = _include_photometric_dist(args)
            phot_filter = "1 = 1" if include_photometric_dist else "dd.photometric_estimate = 0"
            rows = _records(_read_sql(conn, """
                SELECT
                    dd.id,
                    dd.moca_oid,
                    dd.distance_pc,
                    dd.distance_pc_unc,
                    dd.dmod,
                    dd.dmod_unc,
                    dd.photometric_estimate,
                    COALESCE(
                        distance_pub.name,
                        CAST(distance_pub.moca_pid AS CHAR),
                        parallax_pub.name,
                        CAST(parallax_pub.moca_pid AS CHAR),
                        dplx.origin,
                        dd.calculation_method,
                        dd.origin,
                        'No reference'
                    ) AS distance_ref
                FROM data_distances dd
                LEFT JOIN moca_publications distance_pub
                    ON distance_pub.moca_pid = dd.moca_pid
                LEFT JOIN data_parallaxes dplx
                    ON dplx.id = dd.parallax_id
                LEFT JOIN moca_publications parallax_pub
                    ON parallax_pub.moca_pid = dplx.moca_pid
                WHERE dd.adopted = 1
                    AND dd.distance_pc IS NOT NULL
                    AND {phot_filter}
                    AND {oid_filter}
                ORDER BY dd.moca_oid, dd.photometric_estimate
            """.format(phot_filter=phot_filter, oid_filter=oid_filter)))
        elif feature == "photometry":
            if _request_all_photometry(args):
                photometry_psids = []
                photometry_simplebands = list(SIMPLE_PHOTOMETRY_BANDS)
                psid_filter, psid_params = "1 = 1", {}
            else:
                photometry_psids = _requested_photometry_psids(args)
                photometry_simplebands = _requested_photometry_simplebands(args)
                psid_filter, psid_params = _photometry_filter_sql("dp", photometry_psids, photometry_simplebands)
            feature_meta["photometry_psids"] = photometry_psids
            feature_meta["photometry_simplebands"] = photometry_simplebands
            rows = _records(_read_sql(conn, """
                SELECT
                    dp.moca_oid,
                    dp.moca_psid,
                    MIN(dp.system_band_simple) AS system_band_simple,
                    MAX(dp.adopted_simpleband) AS adopted_simpleband,
                    MIN(dp.magnitude) AS magnitude,
                    MIN(dp.magnitude_unc) AS magnitude_unc,
                    MIN(ps.name) AS name,
                    MIN(COALESCE(
                        phot_pub.name,
                        CAST(phot_pub.moca_pid AS CHAR),
                        dp.origin,
                        dp.calculation_method,
                        'No reference'
                    )) AS photometry_ref
                FROM data_photometry dp
                JOIN moca_photometry_systems ps
                    ON ps.moca_psid = dp.moca_psid
                LEFT JOIN moca_publications phot_pub
                    ON phot_pub.moca_pid = dp.moca_pid
                WHERE dp.adopted = 1
                    AND dp.magnitude IS NOT NULL
                    AND dp.magnitude_unc IS NOT NULL
                    AND {psid_filter}
                    AND {oid_filter}
                GROUP BY dp.moca_oid, dp.moca_psid
                ORDER BY dp.moca_oid, dp.moca_psid
            """.format(psid_filter=psid_filter, oid_filter=oid_filter), psid_params))
        elif feature == "spectralIndices":
            spectral_index_ids = _requested_spectral_index_ids(args)
            siid_filter, siid_params = _safe_id_filter_sql("dsi", "moca_siid", spectral_index_ids, "siid")
            feature_meta["spectral_index_siids"] = spectral_index_ids
            rows = _records(_read_sql(conn, """
                SELECT
                    dsi.moca_oid,
                    dsi.moca_siid,
                    MIN(dsi.index_value) AS index_value,
                    MIN(dsi.index_value_unc) AS index_value_unc,
                    MIN(msi.description) AS description,
                    MIN(COALESCE(
                        si_pub.name,
                        CAST(si_pub.moca_pid AS CHAR),
                        dsi.origin,
                        dsi.calculation_method,
                        'No reference'
                    )) AS spectral_index_ref
                FROM data_spectral_indices dsi
                JOIN moca_spectral_indices msi
                    ON msi.moca_siid = dsi.moca_siid
                LEFT JOIN moca_publications si_pub
                    ON si_pub.moca_pid = dsi.moca_pid
                WHERE dsi.ignored = 0
                    AND dsi.index_value IS NOT NULL
                    AND {siid_filter}
                    AND {oid_filter}
                GROUP BY dsi.moca_oid, dsi.moca_siid
                ORDER BY dsi.moca_oid, dsi.moca_siid
            """.format(siid_filter=siid_filter, oid_filter=oid_filter), siid_params))
        elif feature == "equivalentWidths":
            rows = _records(_read_sql(conn, """
                SELECT
                    dew.moca_oid,
                    dew.moca_spid,
                    MIN(dew.ew_angstrom) AS ew_angstrom,
                    MIN(dew.ew_angstrom_unc) AS ew_angstrom_unc,
                    MIN(mcs.description) AS description,
                    MIN(COALESCE(
                        ew_pub.name,
                        CAST(ew_pub.moca_pid AS CHAR),
                        dew.origin,
                        dew.calculation_method,
                        'No reference'
                    )) AS equivalent_width_ref
                FROM data_equivalent_widths dew
                JOIN moca_chemical_species mcs
                    ON mcs.moca_spid = dew.moca_spid
                LEFT JOIN moca_publications ew_pub
                    ON ew_pub.moca_pid = dew.moca_pid
                WHERE dew.ignored = 0
                    AND dew.ew_angstrom IS NOT NULL
                    AND {oid_filter}
                GROUP BY dew.moca_oid, dew.moca_spid
                ORDER BY dew.moca_oid, dew.moca_spid
            """.format(oid_filter=oid_filter)))
        else:
            rows = _records(_read_sql(conn, """
                SELECT
                    cbs.moca_oid,
                    MIN(daa.age_myr) AS age_myr
                FROM calc_banyan_sigma cbs
                JOIN data_association_ages daa
                    ON daa.moca_aid = cbs.moca_aid
                WHERE cbs.max_observables = 1
                    AND cbs.moca_aid IS NOT NULL
                    AND cbs.ya_prob >= 80
                    AND daa.age_myr IS NOT NULL
                    AND daa.adopted = 1
                    AND cbs.moca_bsmdid = (
                        SELECT moca_bsmdid
                        FROM moca_banyan_sigma_models
                        WHERE adopted = 1
                        LIMIT 1
                    )
                    AND {oid_filter}
                GROUP BY cbs.moca_oid
            """.format(oid_filter=oid_filter)))

    payload = {
        "feature": feature,
        "rows": rows,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "object_count": len(selected_oids),
            "row_count": len(rows),
            **feature_meta,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _FEATURE_CACHE[cache_key] = (now, payload)
    return payload


def _preload_args(args: dict[str, Any]) -> dict[str, Any]:
    out = dict(args)
    if _is_private_db(args):
        out["photspt"] = "0"
        out["include_photspt"] = "0"
        out["include_photometric_spt"] = "0"
    else:
        out["photspt"] = "1"
        out["include_photspt"] = "1"
        out["include_photometric_spt"] = "1"
    out["photdist"] = "1"
    out["include_photdist"] = "1"
    out["psids"] = "all"
    out["siids"] = "all"
    out["sequences"] = "all"
    out["bulk"] = "1"
    return out


def _load_preload_from_db(args: dict[str, Any]) -> dict[str, Any]:
    bulk_args = _preload_args(args)
    include_photometric_spt = _include_photometric_spt(bulk_args)
    payload = copy.deepcopy(_load_bootstrap_from_db(bulk_args))
    catalog = payload["catalog"]
    feature_timings: dict[str, float] = {}
    for feature in ("sequences", "designations", "spectralIndices", "equivalentWidths", "ages"):
        started = time.time()
        feature_payload = _load_feature_from_db(bulk_args, feature)
        catalog[feature] = feature_payload["rows"]
        feature_timings[feature] = round(time.time() - started, 3)

    photometry_psids = sorted({
        str(row["moca_psid"])
        for row in payload.get("options", {}).get("photometry", [])
        if row.get("moca_psid") is not None
    })
    spectral_index_siids = sorted({
        str(row["moca_siid"])
        for row in payload.get("options", {}).get("spectralIndices", [])
        if row.get("moca_siid") is not None
    })
    equivalent_width_spids = sorted({
        str(row["moca_spid"])
        for row in catalog.get("equivalentWidths", [])
        if row.get("moca_spid") is not None
    })

    timings = dict(payload.get("meta", {}).get("timings") or {})
    timings.update({f"preload_{key}": value for key, value in feature_timings.items()})
    timings["preload_total"] = round(sum(feature_timings.values()), 3)

    payload["meta"] = {
        **payload["meta"],
        "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "include_photometric_spt": include_photometric_spt,
        "preload_omitted_photometric_spt": not include_photometric_spt,
        "include_photometric_dist": True,
        "bulk_preloaded": True,
        "all_sequences_loaded": True,
        "lazy_features": [],
        "photometry_psids": photometry_psids,
        "photometry_simplebands": list(SIMPLE_PHOTOMETRY_BANDS),
        "spectral_index_siids": spectral_index_siids,
        "equivalent_width_spids": equivalent_width_spids,
        "sequence_key": "all",
        "timings": timings,
    }
    payload["cache"] = {"hit": False, "ttl_seconds": CACHE_SECONDS}
    return payload


def _mock_payload() -> dict[str, Any]:
    rng = random.Random(42)
    phot_opts = [
        {"moca_psid": "mko_jmag", "name": "MKO J", "system_band_simple": "J"},
        {"moca_psid": "mko_hmag", "name": "MKO H", "system_band_simple": "H"},
        {"moca_psid": "mko_kmag", "name": "MKO K", "system_band_simple": "K"},
        {"moca_psid": "wise_w1", "name": "WISE W1", "system_band_simple": "W1"},
        {"moca_psid": "wise_w2", "name": "WISE W2", "system_band_simple": "W2"},
    ]
    si_opts = [
        {"moca_siid": "h2o_j", "description": "H2O-J spectral index"},
        {"moca_siid": "ch4_h", "description": "CH4-H spectral index"},
    ]
    ew_opts = [
        {"moca_spid": "li", "description": "Lithium 6708"},
        {"moca_spid": "na_i_8190", "description": "Na I 8190"},
    ]

    objects = []
    distances = []
    photometry = []
    designations = []
    spectral_indices = []
    equivalent_widths = []
    ages = []

    for i in range(240):
        oid = 900000 + i
        spt = 6 + (26 * i / 239.0)
        spectral_class = "M" if spt < 10 else "L" if spt < 20 else "T" if spt < 30 else "Y"
        subtype = int(round(spt % 10))
        gravity = "VL-G" if i % 17 == 0 else None
        suffix = "sd" if i % 29 == 0 else None
        binary_flag = "multiple_system:C" if i % 23 == 0 else None
        objects.append({
            "moca_oid": oid,
            "designation": f"MOCK J{i:04d}",
            "spectral_type_number": round(spt, 2),
            "spectral_type_unc": 0.5,
            "spectral_class": spectral_class,
            "suffix": suffix,
            "gravity_class": gravity,
            "complete_spectral_type": f"{spectral_class}{subtype}{' VL-G' if gravity else ''}",
            "spectral_type_photometric_estimate": 1 if i % 31 == 0 else 0,
            "spt_ref": "mock",
            "all_prop_confidences": binary_flag,
        })
        designations.extend([
            {"moca_oid": oid, "designation": f"MOCK J{i:04d}"},
            {"moca_oid": oid, "designation": f"2MASS J{i:04d}+{(i * 7) % 10000:04d}"},
        ])
        if i % 5 == 0:
            designations.append({"moca_oid": oid, "designation": f"WISEA J{i:04d}"})

        dist = 8 + rng.random() * 70
        dmod = 5 * math.log10(dist) - 5
        distances.append({
            "moca_oid": oid,
            "distance_pc": round(dist, 3),
            "distance_pc_unc": round(0.04 * dist, 3),
            "dmod": round(dmod, 4),
            "dmod_unc": 0.08,
            "photometric_estimate": 1 if i % 19 == 0 else 0,
            "distance_ref": "mock",
        })
        if i % 19 == 0:
            distances.append({
                "moca_oid": oid,
                "distance_pc": round(dist * 1.08, 3),
                "distance_pc_unc": round(0.12 * dist, 3),
                "dmod": round(5 * math.log10(dist * 1.08) - 5, 4),
                "dmod_unc": 0.25,
                "photometric_estimate": 0,
                "distance_ref": "mock parallax",
            })

        abs_j = 9.5 + 0.23 * spt + rng.gauss(0, 0.35)
        colors = {
            "mko_jmag": 0.0,
            "mko_hmag": -(0.55 + 0.02 * spt),
            "mko_kmag": -(0.95 + 0.035 * spt),
            "wise_w1": -(1.2 + 0.045 * spt),
            "wise_w2": -(1.35 + 0.06 * spt),
        }
        for opt in phot_opts:
            psid = opt["moca_psid"]
            mag = abs_j + dmod + colors[psid] + rng.gauss(0, 0.06)
            photometry.append({
                "moca_oid": oid,
                "moca_psid": psid,
                "system_band_simple": opt["system_band_simple"],
                "adopted_simpleband": 1,
                "magnitude": round(mag, 4),
                "magnitude_unc": round(0.02 + rng.random() * 0.08, 4),
                "name": opt["name"],
                "photometry_ref": "mock",
            })

        spectral_indices.append({
            "moca_oid": oid,
            "moca_siid": "h2o_j",
            "index_value": round(0.95 - 0.015 * spt + rng.gauss(0, 0.02), 4),
            "index_value_unc": 0.02,
            "description": "H2O-J spectral index",
            "spectral_index_ref": "mock",
        })
        spectral_indices.append({
            "moca_oid": oid,
            "moca_siid": "ch4_h",
            "index_value": round(1.05 - 0.012 * spt + rng.gauss(0, 0.02), 4),
            "index_value_unc": 0.025,
            "description": "CH4-H spectral index",
            "spectral_index_ref": "mock",
        })
        equivalent_widths.append({
            "moca_oid": oid,
            "moca_spid": "li",
            "ew_angstrom": round(max(0, rng.gauss(0.25 if spt > 16 else 0.05, 0.08)), 4),
            "ew_angstrom_unc": 0.03,
            "description": "Lithium 6708",
            "equivalent_width_ref": "mock",
        })
        equivalent_widths.append({
            "moca_oid": oid,
            "moca_spid": "na_i_8190",
            "ew_angstrom": round(max(0, rng.gauss(2.0 - 0.03 * spt, 0.25)), 4),
            "ew_angstrom_unc": 0.12,
            "description": "Na I 8190",
            "equivalent_width_ref": "mock",
        })
        if i % 7 == 0:
            ages.append({"moca_oid": oid, "age_myr": round(10 ** rng.uniform(1.0, 3.2), 2)})

    median_colors = []
    for psid1, psid2 in [("mko_jmag", "mko_kmag"), ("mko_jmag", "mko_hmag"), ("mko_hmag", "mko_kmag")]:
        for spt in range(6, 33):
            base = {"mko_jmag": 0, "mko_hmag": -0.55 - 0.02 * spt, "mko_kmag": -0.95 - 0.035 * spt}
            median_colors.append({
                "moca_pid": "Best18",
                "moca_psid1": psid1,
                "moca_psid2": psid2,
                "spectral_type_number": spt,
                "color_mag": round(base[psid1] - base[psid2], 4),
                "n_obj": 20,
            })

    return {
        "options": {
            "photometry": phot_opts,
            "simplePhotometry": _simple_band_option_rows(),
            "spectralIndices": si_opts,
            "equivalentWidths": ew_opts,
        },
        "catalog": {
            "objects": objects,
            "distances": distances,
            "photometry": photometry,
            "designations": designations,
            "spectralIndices": spectral_indices,
            "equivalentWidths": equivalent_widths,
            "ages": ages,
            "medianColors": median_colors,
            "sequences": [],
        },
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "object_count": len(objects),
            "photometry_count": len(photometry),
            "photometry_simplebands": list(SIMPLE_PHOTOMETRY_BANDS),
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/plotly.min.js")
def plotly_js():
    global _PLOTLY_JS
    if _PLOTLY_JS is None:
        from plotly.offline import get_plotlyjs

        _PLOTLY_JS = get_plotlyjs()
    return Response(_PLOTLY_JS, mimetype="application/javascript")


@app.get("/api/bootstrap")
def bootstrap():
    args = dict(request.args)
    if args.get("mock") in {"1", "true", "yes"}:
        payload = _mock_payload()
        return jsonify({"ok": True, "source": "mock", **payload})

    try:
        payload = _load_bootstrap_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        payload = _mock_payload()
        return jsonify({
            "ok": False,
            "source": "mock",
            "error": f"{type(exc).__name__}: {exc}",
            **payload,
        })


@app.get("/api/preload")
def preload():
    args = dict(request.args)
    if args.get("mock") in {"1", "true", "yes"}:
        payload = _mock_payload()
        catalog = payload["catalog"]
        include_photometric_spt = not _is_private_db(args)
        if not include_photometric_spt:
            keep_oids = {
                int(row["moca_oid"])
                for row in catalog["objects"]
                if int(row.get("spectral_type_photometric_estimate") or 0) != 1
            }
            catalog["objects"] = [row for row in catalog["objects"] if int(row["moca_oid"]) in keep_oids]
            for key in ("distances", "photometry", "designations", "spectralIndices", "equivalentWidths", "ages"):
                catalog[key] = [row for row in catalog[key] if int(row["moca_oid"]) in keep_oids]
        payload["meta"] = {
            **payload["meta"],
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "object_count": len(catalog["objects"]),
            "photometry_count": len(catalog["photometry"]),
            "include_photometric_spt": include_photometric_spt,
            "preload_omitted_photometric_spt": not include_photometric_spt,
            "include_photometric_dist": True,
            "bulk_preloaded": True,
            "all_sequences_loaded": True,
            "lazy_features": [],
            "photometry_psids": sorted({
                row["moca_psid"] for row in payload["options"]["photometry"] if row.get("moca_psid") is not None
            }),
            "photometry_simplebands": list(SIMPLE_PHOTOMETRY_BANDS),
            "spectral_index_siids": sorted({
                row["moca_siid"] for row in payload["options"]["spectralIndices"] if row.get("moca_siid") is not None
            }),
            "equivalent_width_spids": sorted({
                row["moca_spid"] for row in catalog["equivalentWidths"] if row.get("moca_spid") is not None
            }),
            "sequence_key": "all",
        }
        return jsonify({"ok": True, "source": "mock", **payload})

    try:
        started = time.time()
        payload = _load_preload_from_db(args)
        payload["meta"]["timings"]["preload_total"] = round(time.time() - started, 3)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "catalog": {},
            "options": {},
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
            "cache": {"hit": False, "ttl_seconds": 0},
        })


@app.post("/api/cache/clear")
def clear_cache():
    bootstrap_count = len(_BOOTSTRAP_CACHE)
    feature_count = len(_FEATURE_CACHE)
    _BOOTSTRAP_CACHE.clear()
    _FEATURE_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {
            "bootstrap": bootstrap_count,
            "features": feature_count,
        },
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
    })


@app.get("/api/feature/<feature>")
def feature(feature: str):
    feature_map = {
        "distances": "distances",
        "photometry": "photometry",
        "photometry-options": "photometryOptions",
        "sequences": "sequences",
        "designations": "designations",
        "spectral-indices": "spectralIndices",
        "spectralIndices": "spectralIndices",
        "equivalent-widths": "equivalentWidths",
        "equivalentWidths": "equivalentWidths",
        "ages": "ages",
    }
    feature_name = feature_map.get(feature)
    if feature_name is None:
        return jsonify({"ok": False, "source": "none", "error": f"Unknown feature: {feature}"}), 404

    args = dict(request.args)
    if args.get("mock") in {"1", "true", "yes"}:
        payload = _mock_payload()
        if feature_name == "photometryOptions":
            counts: dict[str, int] = {}
            simple_counts: dict[str, int] = {}
            option_by_psid = {row["moca_psid"]: row for row in payload["options"]["photometry"]}
            for row in payload["catalog"]["photometry"]:
                psid = row["moca_psid"]
                counts[psid] = counts.get(psid, 0) + 1
                if int(row.get("adopted_simpleband") or 0) == 1 and row.get("system_band_simple"):
                    band = str(row["system_band_simple"])
                    simple_counts[band] = simple_counts.get(band, 0) + 1
            rows = [
                {
                    "moca_psid": psid,
                    "name": option_by_psid.get(psid, {}).get("name", psid),
                    "system_band_simple": option_by_psid.get(psid, {}).get("system_band_simple"),
                    "n_data": count,
                }
                for psid, count in counts.items()
                if count > 0
            ]
        else:
            rows = payload["catalog"][feature_name]
        if feature_name == "photometry" and not _request_all_photometry(args):
            psids = set(_requested_photometry_psids(args))
            simplebands = set(_requested_photometry_simplebands(args))
            rows = [
                row for row in rows
                if row.get("moca_psid") in psids
                or (
                    int(row.get("adopted_simpleband") or 0) == 1
                    and row.get("system_band_simple") in simplebands
                )
            ]
        meta = {"object_count": payload["meta"]["object_count"], "row_count": len(rows)}
        if feature_name == "photometryOptions":
            meta["simple_photometry_options"] = _simple_band_option_rows(simple_counts)
        if feature_name == "photometry":
            meta["photometry_psids"] = _requested_photometry_psids(args)
            meta["photometry_simplebands"] = _requested_photometry_simplebands(args)
        if feature_name == "spectralIndices":
            siids = _requested_spectral_index_ids(args)
            if siids:
                rows = [row for row in rows if row.get("moca_siid") in set(siids)]
                meta["row_count"] = len(rows)
            meta["spectral_index_siids"] = siids
        return jsonify({
            "ok": True,
            "source": "mock",
            "feature": feature_name,
            "rows": rows,
            "meta": meta,
            "cache": {"hit": False, "ttl_seconds": 0},
        })

    try:
        payload = _load_feature_from_db(args, feature_name)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "feature": feature_name,
            "error": f"{type(exc).__name__}: {exc}",
            "rows": [],
            "meta": {"row_count": 0},
            "cache": {"hit": False, "ttl_seconds": 0},
        })


if __name__ == "__main__":
    port = int(os.environ.get("BD_COLORS_FAST_PORT", "8061"))
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)
