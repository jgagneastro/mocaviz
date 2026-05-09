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
_SPT_GRID_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SPT_SPECTRUM_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SPT_COMPARE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PLOTLY_JS: str | None = None

SPT_WV_MIN = 0.85
SPT_WV_MAX = 2.4
SPT_MASKED_REGIONS = ((1.367, 1.424), (1.86, 2.0))
SPT_DEFAULT_NORM_REGIONS = ((0.86, 1.35), (1.445, 1.8), (2.01, 2.4))
SPT_PRE_SMOOTHING_MIN_BINS_PER_MICRON = 200
SPT_DEFAULT_BINS_PER_MICRON = 200


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


def _request_host_name() -> str:
    raw_host = (request.host or "").split(",", 1)[0].strip().lower()
    if raw_host.startswith("[") and "]" in raw_host:
        return raw_host[1:].split("]", 1)[0]
    if raw_host.count(":") == 1:
        return raw_host.rsplit(":", 1)[0]
    return raw_host


def _is_local_app_request() -> bool:
    host = _request_host_name()
    return (
        host == "localhost"
        or host == "::1"
        or host.startswith("127.")
        or host.endswith(".localhost")
    )


def _include_photometric_spt(args: dict[str, Any]) -> bool:
    return any(
        _as_bool(args.get(key))
        for key in ("photspt", "include_photspt", "include_photometric_spt")
    )


def _include_risky_photometric_spt(args: dict[str, Any]) -> bool:
    return any(
        _as_bool(args.get(key))
        for key in ("risky_photspt", "include_risky_photspt", "include_risky_photometric_spt")
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
    if include_photometric_spt and _is_private_db(args) and not _include_risky_photometric_spt(args):
        phot_clause = "(dst.photometric_estimate = 0 OR (dst.photometric_estimate = 1 AND dst.public_adopted = 1))"
    elif include_photometric_spt:
        phot_clause = "1 = 1"
    else:
        phot_clause = "dst.photometric_estimate = 0"
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
        str(_is_private_db(args) and _include_risky_photometric_spt(args)),
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
            "include_risky_photometric_spt": _is_private_db(args) and _include_risky_photometric_spt(args),
            "include_photometric_dist": include_photometric_dist,
            "private_db": _is_private_db(args),
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
    out["photspt"] = "1"
    out["include_photspt"] = "1"
    out["include_photometric_spt"] = "1"
    out["risky_photspt"] = "0"
    out["include_risky_photspt"] = "0"
    out["include_risky_photometric_spt"] = "0"
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
        "include_risky_photometric_spt": _include_risky_photometric_spt(bulk_args),
        "preload_omitted_photometric_spt": not include_photometric_spt,
        "preload_omitted_risky_photometric_spt": _is_private_db(args),
        "include_photometric_dist": True,
        "private_db": _is_private_db(args),
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
        photometric_spt = 1 if i % 31 == 0 else 0
        objects.append({
            "moca_oid": oid,
            "designation": f"MOCK J{i:04d}",
            "spectral_type_number": round(spt, 2),
            "spectral_type_unc": 0.5,
            "spectral_class": spectral_class,
            "suffix": suffix,
            "gravity_class": gravity,
            "complete_spectral_type": f"{spectral_class}{subtype}{' VL-G' if gravity else ''}",
            "spectral_type_photometric_estimate": photometric_spt,
            "spectral_type_public_adopted": 0 if photometric_spt and i % 2 else 1,
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
            "include_photometric_spt": True,
            "include_risky_photometric_spt": False,
            "private_db": False,
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _spt_db_cache_key(args: dict[str, Any]) -> str:
    cfg = _db_config(args)
    return "|".join([cfg["host"], cfg["username"], cfg["dbname"]])


def _spt_parse_norm_regions(raw: str | None) -> list[tuple[float, float]]:
    if not raw:
        return [tuple(region) for region in SPT_DEFAULT_NORM_REGIONS]
    text_value = re.sub(r"[\[\](){}]", " ", str(raw).strip())
    chunks = [chunk for chunk in re.split(r"[;,]+|\s{2,}", text_value) if chunk.strip()]
    regions: list[tuple[float, float]] = []
    for chunk in chunks:
        parts = [part for part in re.split(r"\s*[-:,]\s*|\s+", chunk) if part.strip()]
        if len(parts) < 2:
            continue
        try:
            start = float(parts[0])
            end = float(parts[1])
        except ValueError:
            continue
        lo, hi = (start, end) if start <= end else (end, start)
        lo = max(lo, SPT_WV_MIN)
        hi = min(hi, SPT_WV_MAX)
        if hi > lo:
            regions.append((round(lo, 6), round(hi, 6)))
    return regions or [tuple(region) for region in SPT_DEFAULT_NORM_REGIONS]


def _spt_format_norm_regions(regions: list[tuple[float, float]] | tuple[tuple[float, float], ...]) -> str:
    return ", ".join(f"{start:.3f}-{end:.3f}" for start, end in regions)


def _spt_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _spt_average_resolving_power(wavelengths: Any) -> float | None:
    wv = np.asarray(wavelengths, dtype=float)
    wv = np.unique(np.sort(wv[np.isfinite(wv)]))
    if wv.size < 2:
        return None
    dwv = np.diff(wv)
    mid = 0.5 * (wv[1:] + wv[:-1])
    valid = np.isfinite(dwv) & (dwv > 0) & np.isfinite(mid) & (mid > 0)
    if not np.any(valid):
        return None
    return float(np.nanmean(mid[valid] / dwv[valid]))


def _spt_weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not np.any(valid):
        finite = values[np.isfinite(values)]
        return float(np.nanmedian(finite)) if finite.size else float("nan")
    values = values[valid]
    weights = weights[valid]
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    return float(values[order[np.searchsorted(cumulative, 0.5 * cumulative[-1])]])


def _spt_median_smooth(df: pd.DataFrame, bins_per_micron: int) -> pd.DataFrame:
    if df.empty or bins_per_micron <= 0:
        return df
    wv_min = _spt_float(df["wv"].min())
    wv_max = _spt_float(df["wv"].max())
    if wv_min is None or wv_max is None or wv_max <= wv_min:
        return df
    bin_size = 1.0 / bins_per_micron
    bins = np.arange(wv_min, wv_max + bin_size, bin_size)
    if bins.size < 2:
        return df
    out = df.copy()
    out["wv_bin"] = pd.cut(out["wv"], bins, labels=bins[:-1], include_lowest=True)
    out = out.groupby("wv_bin", as_index=False, observed=True).median(numeric_only=True)
    out = out.rename(columns={"wv_bin": "wv"})
    out["wv"] = out["wv"].astype(float)
    return out


def _spt_apply_wavelength_mask(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for start, end in SPT_MASKED_REGIONS:
        out.loc[out["wv"].between(start, end), "sp"] = np.nan
    return out


def _spt_prepare_errors(flux_values: Any, error_values: Any | None) -> np.ndarray:
    flux = np.asarray(flux_values, dtype=float)
    if error_values is None:
        err = np.full_like(flux, np.nan, dtype=float)
    else:
        err = np.asarray(error_values, dtype=float)
        if err.shape != flux.shape:
            err = np.full_like(flux, np.nan, dtype=float)
    err = np.where(np.isfinite(err), np.abs(err), np.nan)
    finite_err = np.isfinite(err) & (err > 0)
    if not np.any(finite_err):
        finite_flux = flux[np.isfinite(flux)]
        if finite_flux.size >= 2:
            dif = finite_flux[1:] - finite_flux[:-1]
            mad = np.nanmedian(np.abs(dif - np.nanmedian(dif))) if dif.size else np.nan
            if np.isfinite(mad) and mad > 0:
                err = np.where(np.isfinite(flux), mad, np.nan)
                finite_err = np.isfinite(err) & (err > 0)
    floor_flux = 1e-4 * np.abs(flux)
    err = np.where(finite_err, np.fmax(err, floor_flux), err)
    finite_pos = err[np.isfinite(err) & (err > 0)]
    if finite_pos.size:
        floor_med = 0.8 * float(np.nanmedian(finite_pos))
        if np.isfinite(floor_med) and floor_med > 0:
            err = np.where(np.isfinite(err), np.fmax(err, floor_med), err)
    return err


def _spt_scale_to_reference(
    x_ref: Any,
    y_ref: Any,
    e_ref: Any,
    x_target: Any,
    y_target: Any,
    e_target: Any,
) -> float:
    x_ref = np.asarray(x_ref, dtype=float)
    y_ref = np.asarray(y_ref, dtype=float)
    e_ref = np.asarray(e_ref, dtype=float)
    x_target = np.asarray(x_target, dtype=float)
    y_target = np.asarray(y_target, dtype=float)
    e_target = np.asarray(e_target, dtype=float)
    y_ref_interp = np.interp(x_target, x_ref, y_ref, left=np.nan, right=np.nan)
    e_ref_interp = np.interp(x_target, x_ref, e_ref, left=np.nan, right=np.nan)
    denom = np.sqrt(e_ref_interp**2 + e_target**2)
    valid = (
        np.isfinite(y_ref_interp)
        & np.isfinite(y_target)
        & np.isfinite(denom)
        & (denom > 0)
    )
    if not np.any(valid):
        return float("nan")
    numerator = np.nansum((y_ref_interp[valid] * y_target[valid]) / denom[valid])
    denominator = np.nansum((y_target[valid] * y_target[valid]) / denom[valid])
    if not np.isfinite(denominator) or denominator == 0:
        return float("nan")
    return float(numerator / denominator)


def _spt_interp_without_large_gaps(x_values: Any, y_values: Any, target_wv: Any) -> np.ndarray:
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    target = np.asarray(target_wv, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    if not np.any(valid):
        return np.full_like(target, np.nan, dtype=float)
    x = x[valid]
    y = y[valid]
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    if x.size == 1:
        return np.full_like(target, np.nan, dtype=float)
    out = np.interp(target, x, y, left=np.nan, right=np.nan)
    source_steps = np.diff(x)
    source_steps = source_steps[np.isfinite(source_steps) & (source_steps > 0)]
    target_steps = np.diff(np.sort(np.unique(target[np.isfinite(target)])))
    target_steps = target_steps[np.isfinite(target_steps) & (target_steps > 0)]
    if source_steps.size == 0:
        return out
    source_step = float(np.nanmedian(source_steps))
    target_step = float(np.nanmedian(target_steps)) if target_steps.size else source_step
    gap_limit = max(3.5 * source_step, 6.0 * target_step)
    if not np.isfinite(gap_limit) or gap_limit <= 0:
        return out
    for left, right in zip(x[:-1], x[1:]):
        if right - left > gap_limit:
            out[(target > left) & (target < right)] = np.nan
    return out


def _spt_cardelli_extinction_law(wavelength: Any, r_v: float) -> np.ndarray:
    wv = np.asarray(wavelength, dtype=float)
    x = 1.0 / wv
    a = np.zeros_like(x)
    b = np.zeros_like(x)
    opt_nir = (x >= 0.3) & (x < 3.3)
    if np.any(opt_nir):
        y = x[opt_nir]
        a[opt_nir] = 0.574 * y**1.61
        b[opt_nir] = -0.527 * y**1.61
    mid_ir = x < 0.3
    if np.any(mid_ir):
        a[mid_ir] = 0.574 * (0.3**1.61)
        b[mid_ir] = -0.527 * (0.3**1.61)
    return a + b / r_v


def _spt_deredden_spectrum(spectrum: pd.DataFrame, a_v: float, r_v: float) -> pd.DataFrame:
    out = spectrum.copy()
    extinction = _spt_cardelli_extinction_law(out["wv"].to_numpy(dtype=float), r_v)
    factor = 10 ** (0.4 * a_v * extinction)
    median_factor = np.nanmedian(factor)
    if not np.isfinite(median_factor) or median_factor == 0:
        return out
    out["spn"] = (out["spn"].to_numpy(dtype=float) * factor) / median_factor
    return out


def _spt_optimize_av_rv(
    observed_spectrum: pd.DataFrame,
    reference_spectrum: pd.DataFrame,
    fixed_r_v: float | None = None,
) -> tuple[float, float]:
    from scipy.optimize import minimize, minimize_scalar

    def loss_for(a_v: float, r_v: float) -> float:
        dereddened = _spt_deredden_spectrum(observed_spectrum, a_v, r_v)
        ref = reference_spectrum["spn"].to_numpy(dtype=float)
        der = dereddened["spn"].to_numpy(dtype=float)
        valid = np.isfinite(ref) & np.isfinite(der)
        if not np.any(valid):
            return float("inf")
        ratios = ref[valid] / der[valid]
        ratios = ratios[np.isfinite(ratios)]
        if ratios.size == 0:
            return float("inf")
        scale = np.nanmedian(ratios)
        residual = scale * der[valid] - ref[valid]
        return float(np.nansum(residual**2))

    if fixed_r_v is not None and math.isfinite(fixed_r_v) and fixed_r_v > 0:
        result = minimize_scalar(lambda a_v: loss_for(float(a_v), float(fixed_r_v)), bounds=(-50, 50), method="bounded")
        return float(result.x), float(fixed_r_v)

    result = minimize(
        lambda params: loss_for(float(params[0]), float(params[1])),
        [1.0, 3.1],
        bounds=[(-50, 50), (0.01, 50.5)],
        method="L-BFGS-B",
    )
    return float(result.x[0]), float(result.x[1])


def _spt_bin_to_grid(region: pd.DataFrame, target_wv: np.ndarray) -> pd.DataFrame:
    if region.empty or target_wv.size == 0:
        return pd.DataFrame(columns=["wv", "spn", "espn", "moca_specid"])
    target_wv = np.asarray(target_wv, dtype=float)
    if target_wv.size == 1:
        width = 0.001
        edges = np.asarray([target_wv[0] - width, target_wv[0] + width])
    else:
        half_steps = (target_wv[1:] - target_wv[:-1]) / 2.0
        edges = np.concatenate([[target_wv[0] - half_steps[0]], target_wv[:-1] + half_steps, [target_wv[-1] + half_steps[-1]]])
    work = region.copy()
    work["wv_bin"] = pd.cut(work["wv"], bins=edges, labels=target_wv, include_lowest=True)
    agg = {"spn": "median"}
    if "espn" in work.columns:
        agg["espn"] = lambda series: np.nan if len(series) == 0 else float(np.sqrt(np.nansum(np.asarray(series, dtype=float) ** 2)) / max(1, np.sqrt(len(series))))
    if "moca_specid" in work.columns:
        agg["moca_specid"] = "first"
    out = work.groupby("wv_bin", as_index=False, observed=True).agg(agg)
    out = out.rename(columns={"wv_bin": "wv"})
    out["wv"] = out["wv"].astype(float)
    return out.dropna(subset=["wv", "spn"])


def _spt_process_spectrum(
    df: pd.DataFrame,
    bins_per_micron: int | None = None,
    common_wv: np.ndarray | None = None,
    norm_regions_param: list[tuple[float, float]] | None = None,
) -> pd.DataFrame:
    if df.empty or "wv" not in df.columns or "sp" not in df.columns:
        return pd.DataFrame(columns=["wv", "spn", "espn", "moca_specid"])
    bins = int(bins_per_micron or SPT_DEFAULT_BINS_PER_MICRON)
    bins = max(1, bins)
    norm_regions_local = norm_regions_param or [tuple(region) for region in SPT_DEFAULT_NORM_REGIONS]
    work = df.copy()
    for column in ("wv", "sp", "esp"):
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors="coerce")
    if "esp" not in work.columns:
        work["esp"] = np.nan
    work = _spt_apply_wavelength_mask(work)

    normalized_parts: list[pd.DataFrame] = []
    for region_min, region_max in norm_regions_local:
        region = work[work["wv"].between(region_min, region_max)].copy()
        region = region.dropna(subset=["wv", "sp"])
        if region.empty:
            continue
        pre_bins = max(bins, SPT_PRE_SMOOTHING_MIN_BINS_PER_MICRON)
        smoothed = _spt_median_smooth(region, pre_bins)
        values = smoothed["sp"].to_numpy(dtype=float)
        weights = np.nan_to_num(values**2, nan=0.0, posinf=0.0, neginf=0.0)
        norm_value = _spt_weighted_median(values, weights)
        if not np.isfinite(norm_value) or norm_value == 0:
            continue
        region["spn"] = region["sp"] / norm_value
        region["espn"] = region["esp"] / norm_value
        normalized_parts.append(region)

    if not normalized_parts:
        return pd.DataFrame(columns=["wv", "spn", "espn", "moca_specid"])

    processed = pd.concat(normalized_parts, ignore_index=True).dropna(subset=["wv", "spn"])
    processed = processed.sort_values("wv")
    finite_wv = np.unique(processed["wv"].to_numpy(dtype=float)[np.isfinite(processed["wv"].to_numpy(dtype=float))])
    current_res = float(np.nanmedian(np.diff(finite_wv))) if finite_wv.size >= 2 else float("inf")

    if common_wv is None:
        bin_size = 1.0 / bins
        if current_res >= bin_size:
            return processed[["wv", "spn", "espn", "moca_specid"] if "moca_specid" in processed.columns else ["wv", "spn", "espn"]]
        out_parts: list[pd.DataFrame] = []
        for region_min, region_max in norm_regions_local:
            region = processed[processed["wv"].between(region_min, region_max)].copy()
            if region.empty:
                continue
            target = np.arange(float(region["wv"].min()), float(region["wv"].max()) + bin_size, bin_size)
            out_parts.append(_spt_bin_to_grid(region, target))
        return pd.concat(out_parts, ignore_index=True).sort_values("wv") if out_parts else pd.DataFrame(columns=["wv", "spn", "espn", "moca_specid"])

    common_wv = np.asarray(common_wv, dtype=float)
    common_wv = np.sort(common_wv[np.isfinite(common_wv)])
    if common_wv.size == 0:
        return pd.DataFrame(columns=["wv", "spn", "espn", "moca_specid"])
    common_res = float(np.nanmedian(np.diff(common_wv))) if common_wv.size >= 2 else float("inf")
    out_parts = []
    for region_min, region_max in norm_regions_local:
        target = common_wv[(common_wv >= region_min) & (common_wv <= region_max)]
        region = processed[processed["wv"].between(region_min, region_max)].copy()
        if target.size == 0 or region.empty:
            continue
        if current_res >= common_res:
            interp_spn = _spt_interp_without_large_gaps(region["wv"], region["spn"], target)
            interp_espn = _spt_interp_without_large_gaps(region["wv"], region["espn"], target)
            part = pd.DataFrame({"wv": target, "spn": interp_spn, "espn": interp_espn})
            if "moca_specid" in region.columns and not region["moca_specid"].empty:
                part["moca_specid"] = region["moca_specid"].iloc[0]
            out_parts.append(part.dropna(subset=["wv", "spn"]))
        else:
            out_parts.append(_spt_bin_to_grid(region, target))
    return pd.concat(out_parts, ignore_index=True).sort_values("wv") if out_parts else pd.DataFrame(columns=["wv", "spn", "espn", "moca_specid"])


def _spt_spectrum_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    keep = [column for column in ("wv", "sp", "esp", "spn", "espn", "moca_specid") if column in df.columns]
    clean = df[keep].replace({np.nan: None})
    rows: list[dict[str, Any]] = []
    for row in clean.to_dict(orient="records"):
        compact: dict[str, Any] = {}
        for key, value in row.items():
            value = _pythonize(value)
            if isinstance(value, float):
                compact[key] = round(value, 8 if key != "wv" else 6)
            else:
                compact[key] = value
        rows.append(compact)
    return rows


def _load_spt_grid_from_db(args: dict[str, Any], include_spectra: bool = True) -> dict[str, Any]:
    cache_key = f"{_spt_db_cache_key(args)}|grid|spectra:{int(include_spectra)}"
    now = time.time()
    cached = _SPT_GRID_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    private_public_clause = ""
    if _is_private_db(args):
        private_public_clause = """
            AND COALESCE(dstg.is_public, 1) IN (0, 1)
            AND NOT EXISTS (
                SELECT 1
                FROM data_spectral_typing_grids dstg2
                WHERE dstg2.ignored = 0
                    AND dstg2.moca_specid IS NOT NULL
                    AND dstg2.moca_sptgridid = dstg.moca_sptgridid
                    AND dstg2.grid_index = dstg.grid_index
                    AND COALESCE(dstg2.is_public, 1) IN (0, 1)
                    AND COALESCE(dstg2.is_public, 1) < COALESCE(dstg.is_public, 1)
            )
        """

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        grid_rows = _records(_read_sql(conn, f"""
            SELECT
                dstg.moca_sptgridid AS grid,
                dstg.moca_sptgridhid,
                dstg.moca_specid,
                dstg.moca_oid,
                dstg.object_designation,
                dstg.comments,
                dstg.bibcode,
                dstg.spectral_type,
                dstg.spectral_type_number,
                dstg.short_object_designation AS designation,
                CONCAT(dstg.spectral_type, ' (', dstg.short_object_designation, ')') AS label,
                CASE WHEN mstg.moca_sptgridid = 'extremely low gravity' THEN 'delta'
                     WHEN mstg.moca_sptgridid = 'very low gravity' THEN 'gamma'
                     WHEN mstg.moca_sptgridid = 'intermediate gravity' THEN 'beta'
                     WHEN mstg.moca_sptgridid = 'field' THEN 'alpha'
                     ELSE NULL
                END AS gravity_class
            FROM data_spectral_typing_grids dstg
            JOIN moca_spectral_typing_grids mstg USING(moca_sptgridid)
            JOIN moca_spectra ms ON ms.moca_specid = dstg.moca_specid
            WHERE dstg.ignored = 0
                AND mstg.ignored = 0
                AND dstg.moca_specid IS NOT NULL
                AND COALESCE(ms.ignored, 0) = 0
                {private_public_clause}
            ORDER BY mstg.display_order, dstg.grid_index
        """))
        specids = sorted({
            int(row["moca_specid"])
            for row in grid_rows
            if row.get("moca_specid") is not None
        })
        if include_spectra and specids:
            specid_clause = ",".join(str(specid) for specid in specids)
            spectra_df = _read_sql(conn, f"""
                SELECT
                    ds.moca_specid,
                    ds.wavelength_angstrom * 1e-4 AS wv,
                    ds.flux_flambda AS sp,
                    ds.flux_flambda_unc AS esp
                FROM data_spectra ds
                WHERE ds.moca_specid IN ({specid_clause})
                    AND ds.ignored = 0
                    AND ds.flux_flambda IS NOT NULL
                    AND ds.wavelength_angstrom IS NOT NULL
                ORDER BY ds.moca_specid, ds.wavelength_angstrom
            """)
        else:
            spectra_df = pd.DataFrame(columns=["moca_specid", "wv", "sp", "esp"])

    if not spectra_df.empty:
        spectra_df["sp_median"] = spectra_df.groupby("moca_specid")["sp"].transform("median")
        spectra_df["sp_median"] = spectra_df["sp_median"].replace(0, np.nan)
        spectra_df["esp"] = spectra_df["esp"] / spectra_df["sp_median"]
        spectra_df["sp"] = spectra_df["sp"] / spectra_df["sp_median"]
        spectra_df = spectra_df.drop(columns=["sp_median"])

    grids = []
    seen_grids: set[str] = set()
    for row in grid_rows:
        grid = str(row.get("grid") or "")
        if grid and grid not in seen_grids:
            seen_grids.add(grid)
            grids.append({"label": grid, "value": grid})

    payload = {
        "options": grids,
        "gridData": grid_rows,
        "gridSpectra": _records(spectra_df),
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "grid_count": len(grids),
            "standard_count": len(grid_rows),
            "spectrum_row_count": int(len(spectra_df)),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _SPT_GRID_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _load_spt_spectrum_from_db(args: dict[str, Any], specid: int) -> dict[str, Any]:
    cache_key = f"{_spt_db_cache_key(args)}|spectrum|{int(specid)}"
    now = time.time()
    cached = _SPT_SPECTRUM_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        metadata_rows = _records(_read_sql(conn, """
            SELECT
                ms.moca_specid,
                ms.moca_oid,
                ms.moca_instid,
                ms.instrument_mode_name,
                ms.spectrum_name,
                ms.data_collection_date,
                mo.designation,
                spt.spectral_type
            FROM moca_spectra ms
            LEFT JOIN moca_objects mo USING(moca_oid)
            LEFT JOIN (
                SELECT moca_oid, spectral_type
                FROM data_spectral_types
                WHERE adopted = 1
            ) spt USING(moca_oid)
            WHERE ms.moca_specid = :specid
                AND COALESCE(ms.ignored, 0) = 0
            LIMIT 1
        """, {"specid": int(specid)}))
        rows_df = _read_sql(conn, """
            SELECT
                ds.moca_specid,
                ds.wavelength_angstrom * 1e-4 AS wv,
                ds.flux_flambda AS sp,
                ds.flux_flambda_unc AS esp
            FROM moca_spectra ms
            JOIN data_spectra ds
                ON ds.moca_specid = ms.moca_specid
                AND ds.ignored = 0
            WHERE ds.moca_specid = :specid
                AND COALESCE(ms.ignored, 0) = 0
                AND ds.flux_flambda IS NOT NULL
                AND ds.wavelength_angstrom IS NOT NULL
            ORDER BY ds.wavelength_angstrom
        """, {"specid": int(specid)})

    if not rows_df.empty:
        median = float(np.nanmedian(rows_df["sp"].to_numpy(dtype=float)))
        if np.isfinite(median) and median != 0:
            rows_df["esp"] = rows_df["esp"] / median
            rows_df["sp"] = rows_df["sp"] / median

    meta = metadata_rows[0] if metadata_rows else {"moca_specid": int(specid)}
    designation = meta.get("designation") or meta.get("spectrum_name") or f"specid{int(specid)}"
    spt = meta.get("spectral_type")
    inst = meta.get("moca_instid")
    mode = meta.get("instrument_mode_name")
    label = f"specid{int(specid)}"
    if meta.get("moca_oid") is not None:
        label += f",oid{int(meta['moca_oid'])}"
    label += f": {designation}"
    if spt:
        label += f" ({spt})"
    if inst:
        label += f" with {inst}"
    if mode:
        label += f" in {mode} mode"

    payload = {
        "metadata": {**meta, "label": label},
        "spectrum": _records(rows_df),
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "row_count": int(len(rows_df)),
            "average_resolving_power": _spt_average_resolving_power(rows_df["wv"].to_numpy(dtype=float)) if not rows_df.empty else None,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _SPT_SPECTRUM_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _search_spt_spectra_from_db(args: dict[str, Any], query: str | None, selected_specid: int | None = None) -> dict[str, Any]:
    search_text = (query or "").strip()
    if not search_text and selected_specid is None:
        return {"options": [], "value": None, "meta": {"row_count": 0}}
    search_int: int | None = None
    if search_text.isdigit():
        search_int = int(search_text)
    engine = _engine(_connection_string(args))
    base_query = """
        SELECT
            ms.moca_specid,
            ms.moca_oid,
            ms.moca_instid,
            ms.instrument_mode_name,
            ms.spectrum_name,
            ms.data_collection_date,
            mo.designation,
            spt.spectral_type,
            CONCAT(
                'specid', ms.moca_specid,
                COALESCE(CONCAT(',oid', ms.moca_oid), ''),
                ': ',
                COALESCE(
                    CONCAT(
                        mo.designation,
                        COALESCE(CONCAT(' (', spt.spectral_type, ')'), ''),
                        COALESCE(CONCAT(' with ', ms.moca_instid), ''),
                        COALESCE(CONCAT(' in ', ms.instrument_mode_name, ' mode'), ''),
                        COALESCE(CONCAT(' (', ms.data_collection_date, ')'), '')
                    ),
                    ms.spectrum_name,
                    CONCAT('specid', ms.moca_specid)
                )
            ) AS label
        FROM moca_spectra ms
        LEFT JOIN moca_objects mo USING(moca_oid)
        LEFT JOIN (
            SELECT moca_oid, spectral_type
            FROM data_spectral_types
            WHERE adopted = 1
        ) spt USING(moca_oid)
        WHERE (ms.moca_specpackid != 1 OR ms.moca_specpackid IS NULL)
            AND COALESCE(ms.ignored, 0) = 0
    """
    rows: list[dict[str, Any]] = []
    with engine.connect() as conn:
        if search_text:
            rows = _records(_read_sql(conn, base_query + """
                AND (
                    (:search_int IS NOT NULL AND (ms.moca_specid = :search_int OR ms.moca_oid = :search_int))
                    OR CONCAT('specid', ms.moca_specid) LIKE :search_prefix
                    OR CONCAT('oid', ms.moca_oid) LIKE :search_prefix
                    OR COALESCE(mo.designation, '') LIKE :search_prefix
                    OR COALESCE(ms.spectrum_name, '') LIKE :search_like
                    OR COALESCE(ms.moca_instid, '') LIKE :search_like
                    OR COALESCE(ms.instrument_mode_name, '') LIKE :search_like
                    OR EXISTS (
                        SELECT 1
                        FROM mechanics_all_designations mad
                        WHERE mad.moca_oid = ms.moca_oid
                            AND mad.designation LIKE :search_prefix
                    )
                )
                ORDER BY
                    CASE
                        WHEN :search_int IS NOT NULL AND ms.moca_specid = :search_int THEN 0
                        WHEN :search_int IS NOT NULL AND ms.moca_oid = :search_int THEN 1
                        ELSE 2
                    END,
                    ms.moca_specid
                LIMIT 100
            """, {
                "search_int": search_int,
                "search_prefix": f"{search_text}%",
                "search_like": f"%{search_text}%",
            }))
        if selected_specid is not None and all(int(row["moca_specid"]) != int(selected_specid) for row in rows if row.get("moca_specid") is not None):
            selected_rows = _records(_read_sql(conn, base_query + """
                AND ms.moca_specid = :specid
                LIMIT 1
            """, {"specid": int(selected_specid)}))
            rows = selected_rows + rows

    seen: set[int] = set()
    options = []
    for row in rows:
        if row.get("moca_specid") is None:
            continue
        specid = int(row["moca_specid"])
        if specid in seen:
            continue
        seen.add(specid)
        options.append({**row, "value": specid, "label": row.get("label") or f"specid{specid}"})
    value = int(selected_specid) if selected_specid is not None and int(selected_specid) in seen else None
    return {"options": options, "value": value, "meta": {"row_count": len(options)}}


def _precompute_spt_comparison(
    args: dict[str, Any],
    specid: int,
    bins_per_micron: int,
    norm_regions_param: list[tuple[float, float]],
    deredden: bool,
    fixed_r_v: float | None,
) -> dict[str, Any]:
    bins = max(1, min(int(bins_per_micron or SPT_DEFAULT_BINS_PER_MICRON), 2000))
    norm_key = _spt_format_norm_regions(norm_regions_param)
    fixed_key = "" if fixed_r_v is None else f"{fixed_r_v:.6g}"
    cache_key = f"{_spt_db_cache_key(args)}|compare|{int(specid)}|{bins}|{norm_key}|{int(deredden)}|{fixed_key}"
    now = time.time()
    cached = _SPT_COMPARE_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    grid_payload = _load_spt_grid_from_db(args)
    spectrum_payload = _load_spt_spectrum_from_db(args, specid)
    comparison_raw = pd.DataFrame(spectrum_payload["spectrum"])
    grid_raw = pd.DataFrame(grid_payload["gridSpectra"])
    grid_data = pd.DataFrame(grid_payload["gridData"])
    if comparison_raw.empty:
        raise ValueError(f"No spectrum data found for moca_specid={int(specid)}")
    if grid_raw.empty or grid_data.empty:
        raise ValueError("No spectral typing grid data found")

    comparison_df = _spt_process_spectrum(
        comparison_raw,
        bins_per_micron=bins,
        norm_regions_param=norm_regions_param,
    )
    if comparison_df.empty:
        raise ValueError("Selected comparison spectrum has no usable data in the normalization regions")
    comparison_df["esp_calc"] = _spt_prepare_errors(comparison_df["spn"], comparison_df.get("espn"))
    common_wv = np.sort(comparison_df["wv"].dropna().unique())

    results: list[dict[str, Any]] = []
    for _, row in grid_data.iterrows():
        std_specid = row.get("moca_specid")
        if pd.isna(std_specid):
            continue
        std_specid = int(std_specid)
        std_raw = grid_raw[grid_raw["moca_specid"].astype(int) == std_specid]
        if std_raw.empty or float(np.nansum(std_raw["sp"].to_numpy(dtype=float))) == 0:
            continue
        std_df = _spt_process_spectrum(
            std_raw,
            common_wv=common_wv,
            norm_regions_param=norm_regions_param,
        )
        if std_df.empty:
            continue
        std_df["esp_calc"] = _spt_prepare_errors(std_df["spn"], std_df.get("espn"))

        for region_min, region_max in norm_regions_param:
            std_seg = std_df[std_df["wv"].between(region_min, region_max)]
            comp_seg = comparison_df[comparison_df["wv"].between(region_min, region_max)]
            if std_seg.empty or comp_seg.empty:
                continue
            merged = comp_seg[["wv", "spn", "esp_calc"]].merge(
                std_seg[["wv", "spn", "esp_calc"]],
                on="wv",
                suffixes=("_comp", "_std"),
            )
            if merged.empty:
                continue
            valid = (
                np.isfinite(merged["spn_comp"].to_numpy(dtype=float))
                & np.isfinite(merged["spn_std"].to_numpy(dtype=float))
                & np.isfinite(merged["esp_calc_comp"].to_numpy(dtype=float))
                & (merged["esp_calc_comp"].to_numpy(dtype=float) > 0)
                & np.isfinite(merged["esp_calc_std"].to_numpy(dtype=float))
                & (merged["esp_calc_std"].to_numpy(dtype=float) > 0)
            )
            if not np.any(valid):
                continue
            scale = _spt_scale_to_reference(
                merged["wv"].to_numpy(dtype=float)[valid],
                merged["spn_comp"].to_numpy(dtype=float)[valid],
                merged["esp_calc_comp"].to_numpy(dtype=float)[valid],
                merged["wv"].to_numpy(dtype=float)[valid],
                merged["spn_std"].to_numpy(dtype=float)[valid],
                merged["esp_calc_std"].to_numpy(dtype=float)[valid],
            )
            if np.isfinite(scale):
                mask = std_df["wv"].between(region_min, region_max)
                std_df.loc[mask, "spn"] *= scale
                if "espn" in std_df.columns:
                    std_df.loc[mask, "espn"] *= scale
                std_df.loc[mask, "esp_calc"] *= scale

        spectrum_original = _spt_spectrum_records(std_df)
        spectrum_dereddened: list[dict[str, Any]] | None = None
        av_list = [None] * len(norm_regions_param)
        rv_list = [None] * len(norm_regions_param)
        metric_df = std_df
        if deredden:
            std_df_dered = std_df.copy()
            try:
                for index, (region_min, region_max) in enumerate(norm_regions_param):
                    std_seg = std_df[std_df["wv"].between(region_min, region_max)].copy()
                    comp_seg = comparison_df[comparison_df["wv"].between(region_min, region_max)].copy()
                    if std_seg.empty or comp_seg.empty:
                        continue
                    interp_spn = np.interp(comp_seg["wv"], std_seg["wv"], std_seg["spn"], left=np.nan, right=np.nan)
                    std_interp = pd.DataFrame({"wv": comp_seg["wv"].to_numpy(dtype=float), "spn": interp_spn})
                    valid = np.isfinite(std_interp["spn"].to_numpy(dtype=float)) & np.isfinite(comp_seg["spn"].to_numpy(dtype=float))
                    if not np.any(valid):
                        continue
                    a_v, r_v = _spt_optimize_av_rv(
                        std_interp.loc[valid, ["wv", "spn"]],
                        comp_seg.loc[valid, ["wv", "spn"]],
                        fixed_r_v=fixed_r_v,
                    )
                    av_list[index] = a_v
                    rv_list[index] = r_v
                    dered_seg = _spt_deredden_spectrum(std_seg[["wv", "spn"]], a_v, r_v)
                    mask = std_df_dered["wv"].between(region_min, region_max)
                    std_df_dered.loc[mask, "spn"] = dered_seg["spn"].to_numpy(dtype=float)
                std_df_dered["esp_calc"] = _spt_prepare_errors(std_df_dered["spn"], std_df_dered.get("espn"))
                for region_min, region_max in norm_regions_param:
                    std_seg = std_df_dered[std_df_dered["wv"].between(region_min, region_max)]
                    comp_seg = comparison_df[comparison_df["wv"].between(region_min, region_max)]
                    if std_seg.empty or comp_seg.empty:
                        continue
                    merged = comp_seg[["wv", "spn", "esp_calc"]].merge(
                        std_seg[["wv", "spn", "esp_calc"]],
                        on="wv",
                        suffixes=("_comp", "_std"),
                    )
                    if merged.empty:
                        continue
                    valid = (
                        np.isfinite(merged["spn_comp"].to_numpy(dtype=float))
                        & np.isfinite(merged["spn_std"].to_numpy(dtype=float))
                        & np.isfinite(merged["esp_calc_comp"].to_numpy(dtype=float))
                        & (merged["esp_calc_comp"].to_numpy(dtype=float) > 0)
                        & np.isfinite(merged["esp_calc_std"].to_numpy(dtype=float))
                        & (merged["esp_calc_std"].to_numpy(dtype=float) > 0)
                    )
                    if not np.any(valid):
                        continue
                    scale = _spt_scale_to_reference(
                        merged["wv"].to_numpy(dtype=float)[valid],
                        merged["spn_comp"].to_numpy(dtype=float)[valid],
                        merged["esp_calc_comp"].to_numpy(dtype=float)[valid],
                        merged["wv"].to_numpy(dtype=float)[valid],
                        merged["spn_std"].to_numpy(dtype=float)[valid],
                        merged["esp_calc_std"].to_numpy(dtype=float)[valid],
                    )
                    if np.isfinite(scale):
                        mask = std_df_dered["wv"].between(region_min, region_max)
                        std_df_dered.loc[mask, "spn"] *= scale
                        if "espn" in std_df_dered.columns:
                            std_df_dered.loc[mask, "espn"] *= scale
                        std_df_dered.loc[mask, "esp_calc"] *= scale
                metric_df = std_df_dered
                spectrum_dereddened = _spt_spectrum_records(std_df_dered)
            except Exception:
                metric_df = std_df
                spectrum_dereddened = None
                av_list = [None] * len(norm_regions_param)
                rv_list = [None] * len(norm_regions_param)

        residuals: list[np.ndarray] = []
        for region_min, region_max in norm_regions_param:
            comp_seg = comparison_df[comparison_df["wv"].between(region_min, region_max)]
            std_seg = metric_df[metric_df["wv"].between(region_min, region_max)]
            if comp_seg.empty or std_seg.empty:
                continue
            interp_std = np.interp(comp_seg["wv"], std_seg["wv"], std_seg["spn"], left=np.nan, right=np.nan)
            diff = comp_seg["spn"].to_numpy(dtype=float) - interp_std
            diff = diff[np.isfinite(diff)]
            if diff.size:
                residuals.append(diff)
        if residuals:
            all_residuals = np.concatenate(residuals)
            n_bands = len(norm_regions_param)
            params = 3 * n_bands if deredden else n_bands
            dof = len(all_residuals) - params if len(all_residuals) > params else len(all_residuals)
            reduced_chi2 = float(1e3 * np.nansum(all_residuals**2) / dof) if dof > 0 else None
            mad = float(1e3 * np.nanmedian(np.abs(all_residuals)))
        else:
            reduced_chi2 = None
            mad = None

        results.append({
            "grid": row.get("grid"),
            "moca_sptgridhid": _pythonize(row.get("moca_sptgridhid")),
            "moca_specid": std_specid,
            "moca_oid": _pythonize(row.get("moca_oid")),
            "label": row.get("label"),
            "spectral_type": row.get("spectral_type"),
            "spectral_type_number": _pythonize(row.get("spectral_type_number")),
            "designation": row.get("designation"),
            "object_designation": row.get("object_designation"),
            "comments": row.get("comments"),
            "bibcode": row.get("bibcode"),
            "gravity_class": row.get("gravity_class"),
            "spectrum": spectrum_original,
            "spectrum_dered": spectrum_dereddened,
            "A_V": [_pythonize(value) for value in av_list],
            "R_V": [_pythonize(value) for value in rv_list],
            "reduced_chi2": _pythonize(reduced_chi2),
            "mad": _pythonize(mad),
        })

    payload = {
        "comparison": _spt_spectrum_records(comparison_df),
        "comparisonMetadata": spectrum_payload["metadata"],
        "entries": results,
        "options": grid_payload["options"],
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "specid": int(specid),
            "bins_per_micron": bins,
            "norm_regions": norm_regions_param,
            "norm_regions_text": _spt_format_norm_regions(norm_regions_param),
            "deredden": bool(deredden),
            "fixed_r_v": fixed_r_v,
            "average_resolving_power": spectrum_payload.get("meta", {}).get("average_resolving_power"),
            "standard_count": len(results),
            "grid_count": len(grid_payload["options"]),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _SPT_COMPARE_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _mock_spt_grid_payload() -> dict[str, Any]:
    rows = []
    spectra = []
    grids = [
        ("field", 0.0),
        ("low gravity", -0.7),
    ]
    specid = 800000
    for grid_name, offset in grids:
        for index, sptn in enumerate(np.linspace(7, 30, 16)):
            specid += 1
            label = _spt_label_from_number(float(sptn))
            designation = f"MOCK-{grid_name[:2].upper()}-{index:02d}"
            rows.append({
                "grid": grid_name,
                "moca_sptgridhid": 9000 + index,
                "moca_specid": specid,
                "moca_oid": 990000 + index,
                "object_designation": designation,
                "comments": "mock standard",
                "bibcode": None,
                "spectral_type": label,
                "spectral_type_number": round(float(sptn), 2),
                "designation": designation,
                "label": f"{label} ({designation})",
                "gravity_class": "alpha" if grid_name == "field" else "beta",
            })
            wv = np.arange(0.82, 2.45, 0.002)
            water = 0.18 * np.exp(-0.5 * ((wv - 1.4) / 0.04) ** 2) + 0.22 * np.exp(-0.5 * ((wv - 1.9) / 0.06) ** 2)
            methane = max(0, (sptn - 18) / 14) * (0.18 * np.exp(-0.5 * ((wv - 1.63) / 0.06) ** 2) + 0.2 * np.exp(-0.5 * ((wv - 2.22) / 0.08) ** 2))
            slope = 1.0 + 0.08 * np.sin(wv * 5 + sptn / 5) + 0.04 * (sptn - 18 + offset) * (wv - 1.55)
            flux = np.clip(slope - water - methane, 0.02, None)
            for x, y in zip(wv, flux):
                spectra.append({"moca_specid": specid, "wv": round(float(x), 6), "sp": round(float(y), 8), "esp": 0.02})
    return {
        "options": [{"label": grid, "value": grid} for grid, _offset in grids],
        "gridData": rows,
        "gridSpectra": spectra,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "grid_count": len(grids),
            "standard_count": len(rows),
            "spectrum_row_count": len(spectra),
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _spt_label_from_number(value: float) -> str:
    adjusted = value + 60
    classes = ["O", "B", "A", "F", "G", "K", "M", "L", "T", "Y"]
    class_index = int(adjusted // 10)
    subtype = adjusted % 10
    if 0 <= class_index < len(classes):
        return f"{classes[class_index]}{subtype:.1f}".rstrip("0").rstrip(".")
    return f"{value:g}"


def _mock_spt_spectrum_payload(specid: int) -> dict[str, Any]:
    wv = np.arange(0.82, 2.45, 0.002)
    sptn = 18.5
    water = 0.18 * np.exp(-0.5 * ((wv - 1.4) / 0.04) ** 2) + 0.22 * np.exp(-0.5 * ((wv - 1.9) / 0.06) ** 2)
    methane = 0.08 * np.exp(-0.5 * ((wv - 1.63) / 0.06) ** 2)
    flux = np.clip(1.0 + 0.08 * np.sin(wv * 5 + 0.3) + 0.04 * (sptn - 18) * (wv - 1.55) - water - methane, 0.02, None)
    rows = [{"moca_specid": int(specid), "wv": round(float(x), 6), "sp": round(float(y), 8), "esp": 0.025} for x, y in zip(wv, flux)]
    return {
        "metadata": {
            "moca_specid": int(specid),
            "moca_oid": 990602,
            "designation": "MOCK comparison",
            "spectral_type": "L8.5",
            "label": f"specid{int(specid)},oid990602: MOCK comparison (L8.5)",
        },
        "spectrum": rows,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "row_count": len(rows),
            "average_resolving_power": _spt_average_resolving_power(wv),
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _mock_spt_compare(args: dict[str, Any], specid: int, bins: int, norm_regions_param: list[tuple[float, float]], deredden: bool, fixed_r_v: float | None) -> dict[str, Any]:
    grid_payload = _mock_spt_grid_payload()
    spectrum_payload = _mock_spt_spectrum_payload(specid)
    temp_args = dict(args)
    temp_args["mock"] = "0"
    grid_cache_key = f"mock|grid"
    spectrum_cache_key = f"mock|spectrum|{int(specid)}"
    _SPT_GRID_CACHE[grid_cache_key] = (time.time(), grid_payload)
    _SPT_SPECTRUM_CACHE[spectrum_cache_key] = (time.time(), spectrum_payload)

    comparison_raw = pd.DataFrame(spectrum_payload["spectrum"])
    grid_raw = pd.DataFrame(grid_payload["gridSpectra"])
    grid_data = pd.DataFrame(grid_payload["gridData"])
    comparison_df = _spt_process_spectrum(comparison_raw, bins_per_micron=bins, norm_regions_param=norm_regions_param)
    comparison_df["esp_calc"] = _spt_prepare_errors(comparison_df["spn"], comparison_df.get("espn"))
    common_wv = np.sort(comparison_df["wv"].dropna().unique())
    results = []
    for _, row in grid_data.iterrows():
        std_raw = grid_raw[grid_raw["moca_specid"].astype(int) == int(row["moca_specid"])]
        std_df = _spt_process_spectrum(std_raw, common_wv=common_wv, norm_regions_param=norm_regions_param)
        if std_df.empty:
            continue
        std_df["esp_calc"] = _spt_prepare_errors(std_df["spn"], std_df.get("espn"))
        residuals = []
        for region_min, region_max in norm_regions_param:
            comp_seg = comparison_df[comparison_df["wv"].between(region_min, region_max)]
            std_seg = std_df[std_df["wv"].between(region_min, region_max)]
            if comp_seg.empty or std_seg.empty:
                continue
            scale = _spt_scale_to_reference(
                comp_seg["wv"], comp_seg["spn"], comp_seg["esp_calc"],
                std_seg["wv"], std_seg["spn"], std_seg["esp_calc"],
            )
            if np.isfinite(scale):
                mask = std_df["wv"].between(region_min, region_max)
                std_df.loc[mask, "spn"] *= scale
            interp_std = np.interp(comp_seg["wv"], std_seg["wv"], std_seg["spn"], left=np.nan, right=np.nan)
            diff = comp_seg["spn"].to_numpy(dtype=float) - interp_std
            diff = diff[np.isfinite(diff)]
            if diff.size:
                residuals.append(diff)
        if residuals:
            all_residuals = np.concatenate(residuals)
            reduced_chi2 = float(1e3 * np.nansum(all_residuals**2) / max(1, len(all_residuals) - len(norm_regions_param)))
        else:
            reduced_chi2 = None
        results.append({
            **row.to_dict(),
            "spectrum": _spt_spectrum_records(std_df),
            "spectrum_dered": None,
            "A_V": [None] * len(norm_regions_param),
            "R_V": [None] * len(norm_regions_param),
            "reduced_chi2": _pythonize(reduced_chi2),
            "mad": None,
        })
    return {
        "comparison": _spt_spectrum_records(comparison_df),
        "comparisonMetadata": spectrum_payload["metadata"],
        "entries": _records(pd.DataFrame(results)) if results else [],
        "options": grid_payload["options"],
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "specid": int(specid),
            "bins_per_micron": bins,
            "norm_regions": norm_regions_param,
            "norm_regions_text": _spt_format_norm_regions(norm_regions_param),
            "deredden": bool(deredden),
            "fixed_r_v": fixed_r_v,
            "average_resolving_power": spectrum_payload["meta"]["average_resolving_power"],
            "standard_count": len(results),
            "grid_count": len(grid_payload["options"]),
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _spt_grid_response_payload(payload: dict[str, Any], include_spectra: bool) -> dict[str, Any]:
    out = copy.deepcopy(payload)
    if not include_spectra:
        out["gridSpectra"] = []
    return out


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/spectral-typing")
@app.get("/spectral_typing")
@app.get("/spectral-typing-fast")
@app.get("/spectral_typing_fast")
def spectral_typing_fast_page():
    return send_from_directory(STATIC_DIR, "spectral_typing.html")


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
    if not _is_local_app_request():
        return jsonify({
            "ok": False,
            "source": "none",
            "error": "Bulk preload is only available when the app is served from localhost.",
            "catalog": {},
            "options": {},
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 403

    args = dict(request.args)
    if args.get("mock") in {"1", "true", "yes"}:
        payload = _mock_payload()
        catalog = payload["catalog"]
        private_db = _is_private_db(args)
        include_photometric_spt = True
        include_risky_photometric_spt = False
        if private_db:
            keep_oids = {
                int(row["moca_oid"])
                for row in catalog["objects"]
                if (
                    int(row.get("spectral_type_photometric_estimate") or 0) != 1
                    or int(row.get("spectral_type_public_adopted") or 0) == 1
                )
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
            "include_risky_photometric_spt": include_risky_photometric_spt,
            "preload_omitted_photometric_spt": not include_photometric_spt,
            "preload_omitted_risky_photometric_spt": private_db,
            "include_photometric_dist": True,
            "private_db": private_db,
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


@app.get("/api/spectral-typing/grid")
def spectral_typing_grid():
    args = dict(request.args)
    include_spectra = _as_bool(args.get("include_spectra"))
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            payload = _spt_grid_response_payload(_mock_spt_grid_payload(), include_spectra)
            return jsonify({"ok": True, "source": "mock", **payload})
        payload = _load_spt_grid_from_db(args, include_spectra=include_spectra)
        payload = _spt_grid_response_payload(payload, include_spectra)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "options": [],
            "gridData": [],
            "gridSpectra": [],
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/spectral-typing/search")
def spectral_typing_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    selected_specid = None
    raw_specid = args.get("specid") or args.get("moca_specid")
    if raw_specid is not None:
        try:
            selected_specid = int(raw_specid)
        except (TypeError, ValueError):
            selected_specid = None
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            options = [{
                "moca_specid": 602,
                "moca_oid": 990602,
                "designation": "MOCK comparison",
                "spectral_type": "L8.5",
                "label": "specid602,oid990602: MOCK comparison (L8.5)",
                "value": 602,
            }]
            value = selected_specid if selected_specid == 602 else None
            return jsonify({"ok": True, "source": "mock", "options": options, "value": value, "meta": {"row_count": len(options)}})
        payload = _search_spt_spectra_from_db(args, query, selected_specid)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "options": [],
            "value": None,
            "meta": {"row_count": 0},
        }), 500


@app.get("/api/spectral-typing/spectrum/<int:specid>")
def spectral_typing_spectrum(specid: int):
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_spt_spectrum_payload(specid)})
        payload = _load_spt_spectrum_from_db(args, specid)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "metadata": {"moca_specid": specid},
            "spectrum": [],
            "meta": {"row_count": 0},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/spectral-typing/compare")
def spectral_typing_compare():
    args = dict(request.args)
    body = request.get_json(silent=True) or {}
    raw_specid = body.get("specid") or body.get("moca_specid") or args.get("specid") or args.get("moca_specid")
    try:
        specid = int(raw_specid)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "source": "none", "error": "A numeric specid is required"}), 400
    try:
        bins = int(body.get("bins") or body.get("bins_per_micron") or args.get("bins") or SPT_DEFAULT_BINS_PER_MICRON)
    except (TypeError, ValueError):
        bins = SPT_DEFAULT_BINS_PER_MICRON
    bins = max(1, min(bins, 2000))
    norm_text = body.get("norm") or body.get("norm_regions") or args.get("norm")
    norm_regions_param = _spt_parse_norm_regions(norm_text)
    deredden = _as_bool(body.get("deredden")) or _as_bool(args.get("deredden"))
    fixed_r_v = _spt_float(body.get("fix_rv") if body.get("fix_rv") is not None else args.get("fix_rv"))
    if fixed_r_v is not None and fixed_r_v <= 0:
        fixed_r_v = None
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            payload = _mock_spt_compare(args, specid, bins, norm_regions_param, deredden, fixed_r_v)
            return jsonify({"ok": True, "source": "mock", **payload})
        started = time.time()
        payload = _precompute_spt_comparison(args, specid, bins, norm_regions_param, deredden, fixed_r_v)
        payload["meta"]["timings"] = {"compare_total": round(time.time() - started, 3)}
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "comparison": [],
            "comparisonMetadata": {"moca_specid": specid},
            "entries": [],
            "options": [],
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "specid": specid,
                "bins_per_micron": bins,
                "norm_regions": norm_regions_param,
                "norm_regions_text": _spt_format_norm_regions(norm_regions_param),
                "deredden": deredden,
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/spectral-typing/cache/clear")
def spectral_typing_clear_cache():
    grid_count = len(_SPT_GRID_CACHE)
    spectrum_count = len(_SPT_SPECTRUM_CACHE)
    compare_count = len(_SPT_COMPARE_CACHE)
    _SPT_GRID_CACHE.clear()
    _SPT_SPECTRUM_CACHE.clear()
    _SPT_COMPARE_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {
            "spectralTypingGrid": grid_count,
            "spectralTypingSpectra": spectrum_count,
            "spectralTypingComparisons": compare_count,
        },
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.post("/api/cache/clear")
def clear_cache():
    bootstrap_count = len(_BOOTSTRAP_CACHE)
    feature_count = len(_FEATURE_CACHE)
    spt_grid_count = len(_SPT_GRID_CACHE)
    spt_spectrum_count = len(_SPT_SPECTRUM_CACHE)
    spt_compare_count = len(_SPT_COMPARE_CACHE)
    _BOOTSTRAP_CACHE.clear()
    _FEATURE_CACHE.clear()
    _SPT_GRID_CACHE.clear()
    _SPT_SPECTRUM_CACHE.clear()
    _SPT_COMPARE_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {
            "bootstrap": bootstrap_count,
            "features": feature_count,
            "spectralTypingGrid": spt_grid_count,
            "spectralTypingSpectra": spt_spectrum_count,
            "spectralTypingComparisons": spt_compare_count,
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
