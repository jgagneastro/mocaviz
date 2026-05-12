from __future__ import annotations

import copy
import hashlib
import math
import os
import random
import re
import time
import zlib
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
from flask import Flask, Response, jsonify, redirect, request, send_from_directory
from sqlalchemy import bindparam, create_engine, text


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
_SPT_STANDARD_PROCESS_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_ASTROMETRY_OBJECT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SPECTRA_EXPLORER_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_XYZUVW_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_TRUEFLOW_AGE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_GAIA_CMD_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PLOTLY_JS: str | None = None

SPT_WV_MIN = 0.85
SPT_WV_MAX = 2.4
SPT_MASKED_REGIONS = ((1.367, 1.424), (1.86, 2.0))
SPT_DEFAULT_NORM_REGIONS = ((0.86, 1.35), (1.445, 1.8), (2.01, 2.4))
SPT_PRE_SMOOTHING_MIN_BINS_PER_MICRON = 200
SPT_DEFAULT_BINS_PER_MICRON = 200
SPT_DEFAULT_CLOUD_ALPHA = float(os.environ.get("SPT_CLOUD_ALPHA", "1.7"))
SPT_DEFAULT_CLOUD_LAMBDA0 = float(os.environ.get("SPT_CLOUD_LAMBDA0", "1.25"))
SPECTRA_EXPLORER_DEFAULT_SPECIDS = (13510,)
SPECTRA_EXPLORER_MAX_SELECTED = int(os.environ.get("SPECTRA_EXPLORER_MAX_SELECTED", "30"))
SPECTRA_EXPLORER_DEFAULT_BINS_PER_MICRON = int(os.environ.get("SPECTRA_EXPLORER_BINS_PER_MICRON", "200"))
XYZUVW_DEFAULT_AIDS = ("HYA", "TWA", "THA")
XYZUVW_DEFAULT_MTIDS = ("BF", "HM", "CM")
XYZUVW_C_VALUE = 8.0
XYZUVW_MAX_OBJECTS = int(os.environ.get("XYZUVW_FAST_MAX_OBJECTS", "60000"))
XYZUVW_MODEL_GRID_POINTS = int(os.environ.get("XYZUVW_FAST_MODEL_GRID_POINTS", "100"))
XYZUVW_MODEL_SIGMA_SCALE = float(os.environ.get("XYZUVW_FAST_MODEL_SIGMA_SCALE", "5"))
XYZUVW_MODEL_CONTOURS = (
    ("99%", 0.99, 0.07),
    ("95%", 0.95, 0.15),
    ("68%", 0.68, 0.30),
)
TRUEFLOW_AGE_DEFAULT_OID = int(os.environ.get("TRUEFLOW_AGE_DEFAULT_OID", "11266"))
TRUEFLOW_AGE_CACHE_SCHEMA = "target-title-v3"
GAIA_CMD_DEFAULT_MAX_OBJECTS = int(os.environ.get("GAIA_CMD_FAST_MAX_OBJECTS", "20000"))
GAIA_CMD_HARD_MAX_OBJECTS = int(os.environ.get("GAIA_CMD_FAST_HARD_MAX_OBJECTS", "1000000"))
GAIA_CMD_SIMPLE_BANDS = {
    "G": {"label": "G", "psid": "gaiadr3_gmag", "simple_band": "g"},
    "GBP": {"label": "G_BP", "psid": "gaiadr3_bpmag", "simple_band": "b"},
    "GRP": {"label": "G_RP", "psid": "gaiadr3_rpmag", "simple_band": "r"},
    "GRVS": {"label": "G_RVS", "psid": "gaiadr3_grvsmag", "simple_band": "grvs"},
}
GAIA_CMD_ALLOWED_PSIDS = (
    "gaiadr1_gmag",
    "gaiadr2_bpmag",
    "gaiadr2_gmag",
    "gaiadr2_rpmag",
    "gaiadr3_bpmag",
    "gaiadr3_gmag",
    "gaiadr3_grvsmag",
    "gaiadr3_rpmag",
)
GAIA_CMD_PSID_BANDS = {
    "gaiadr1_gmag": "G",
    "gaiadr2_bpmag": "GBP",
    "gaiadr2_gmag": "G",
    "gaiadr2_rpmag": "GRP",
    "gaiadr3_bpmag": "GBP",
    "gaiadr3_gmag": "G",
    "gaiadr3_grvsmag": "GRVS",
    "gaiadr3_rpmag": "GRP",
}
GAIA_CMD_SEQUENCE_SUFFIXES = ("field", "mel5", "abdmg", "tha", "bpmg", "twa", "etac")


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


def _as_false(value: Any) -> bool:
    if value is False:
        return True
    if value is True:
        return False
    return str(value or "").strip().lower() in {"0", "false", "no", "off", "free", "fit"}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


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


def _db_table_exists(conn, table_name: str) -> bool:
    query = text("""
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
            AND table_name = :table_name
    """)
    return int(conn.execute(query, {"table_name": table_name}).scalar() or 0) > 0


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


def _spt_cardelli_ab(wavelength: Any) -> tuple[np.ndarray, np.ndarray]:
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
    return a, b


def _spt_cardelli_extinction_law(wavelength: Any, r_v: float) -> np.ndarray:
    a, b = _spt_cardelli_ab(wavelength)
    return a + b / r_v


def _spt_median_normalized_factor_apply(base_flux: Any, log_factor: Any) -> np.ndarray:
    base = np.asarray(base_flux, dtype=float)
    log_factor = np.asarray(log_factor, dtype=float)
    if base.shape != log_factor.shape:
        return base.copy()
    factor = np.exp(np.clip(log_factor, -80.0, 80.0))
    median_factor = np.nanmedian(factor[np.isfinite(factor)])
    if not np.isfinite(median_factor) or median_factor == 0:
        return base.copy()
    return base * factor / median_factor


def _spt_deredden_flux_values(
    flux_values: Any,
    a_v: float,
    r_v: float,
    a_coeff: Any,
    b_coeff: Any,
) -> np.ndarray:
    a_coeff = np.asarray(a_coeff, dtype=float)
    b_coeff = np.asarray(b_coeff, dtype=float)
    r_v = max(float(r_v), 0.01)
    extinction = a_coeff + b_coeff / r_v
    log_factor = 0.4 * math.log(10.0) * float(a_v) * extinction
    return _spt_median_normalized_factor_apply(flux_values, log_factor)


def _spt_deredden_spectrum(spectrum: pd.DataFrame, a_v: float, r_v: float) -> pd.DataFrame:
    out = spectrum.copy()
    a_coeff, b_coeff = _spt_cardelli_ab(out["wv"].to_numpy(dtype=float))
    out["spn"] = _spt_deredden_flux_values(out["spn"].to_numpy(dtype=float), a_v, r_v, a_coeff, b_coeff)
    return out


def _spt_nanmedian_with_derivative(values: np.ndarray, derivatives: np.ndarray) -> tuple[float, np.ndarray]:
    values = np.asarray(values, dtype=float)
    derivatives = np.asarray(derivatives, dtype=float)
    if derivatives.ndim == 1:
        derivatives = derivatives[:, np.newaxis]
    valid = np.isfinite(values) & np.all(np.isfinite(derivatives), axis=1)
    if not np.any(valid):
        return float("nan"), np.full(derivatives.shape[1], np.nan, dtype=float)
    values_valid = values[valid]
    deriv_valid = derivatives[valid]
    order = np.argsort(values_valid, kind="mergesort")
    values_sorted = values_valid[order]
    deriv_sorted = deriv_valid[order]
    count = values_sorted.size
    middle = count // 2
    if count % 2:
        return float(values_sorted[middle]), deriv_sorted[middle].astype(float)
    return (
        float(0.5 * (values_sorted[middle - 1] + values_sorted[middle])),
        0.5 * (deriv_sorted[middle - 1] + deriv_sorted[middle]),
    )


def _spt_scaled_residual_loss_and_grad(
    base_flux: Any,
    reference_flux: Any,
    log_factor: Any,
    dlog_factor: Any,
) -> tuple[float, np.ndarray]:
    base = np.asarray(base_flux, dtype=float)
    reference = np.asarray(reference_flux, dtype=float)
    log_factor = np.asarray(log_factor, dtype=float)
    dlog = np.asarray(dlog_factor, dtype=float)
    if dlog.ndim == 1:
        dlog = dlog[:, np.newaxis]
    n_params = dlog.shape[1]
    bad = np.full(n_params, 0.0, dtype=float)
    if base.size == 0 or reference.size != base.size or log_factor.size != base.size or dlog.shape[0] != base.size:
        return 1e300, bad

    raw_factor = np.exp(log_factor)
    raw_derivative = raw_factor[:, np.newaxis] * dlog
    median_factor, median_derivative = _spt_nanmedian_with_derivative(raw_factor, raw_derivative)
    if not math.isfinite(median_factor) or median_factor == 0:
        return 1e300, bad

    corrected = base * raw_factor / median_factor
    corrected_derivative = corrected[:, np.newaxis] * (dlog - median_derivative[np.newaxis, :] / median_factor)
    residual_mask = np.isfinite(reference) & np.isfinite(corrected)
    if not np.any(residual_mask):
        return 1e300, bad

    ratio_mask = residual_mask & (corrected != 0)
    ratios = reference[ratio_mask] / corrected[ratio_mask]
    ratio_derivative = -ratios[:, np.newaxis] * (corrected_derivative[ratio_mask] / corrected[ratio_mask, np.newaxis])
    ratio_finite = np.isfinite(ratios) & np.all(np.isfinite(ratio_derivative), axis=1)
    if not np.any(ratio_finite):
        return 1e300, bad
    scale, scale_derivative = _spt_nanmedian_with_derivative(ratios[ratio_finite], ratio_derivative[ratio_finite])
    if not math.isfinite(scale):
        return 1e300, bad

    corrected_valid = corrected[residual_mask]
    reference_valid = reference[residual_mask]
    corrected_derivative_valid = corrected_derivative[residual_mask]
    residual = scale * corrected_valid - reference_valid
    residual_derivative = (
        scale_derivative[np.newaxis, :] * corrected_valid[:, np.newaxis]
        + scale * corrected_derivative_valid
    )
    loss = float(np.nansum(residual**2))
    gradient = 2.0 * np.nansum(residual[:, np.newaxis] * residual_derivative, axis=0)
    if not math.isfinite(loss) or not np.all(np.isfinite(gradient)):
        return 1e300, bad
    return loss, gradient.astype(float)


def _spt_scaled_residual_ls_loss_and_grad(
    base_flux: Any,
    reference_flux: Any,
    log_factor: Any,
    dlog_factor: Any,
) -> tuple[float, np.ndarray]:
    base = np.asarray(base_flux, dtype=float)
    reference = np.asarray(reference_flux, dtype=float)
    log_factor = np.asarray(log_factor, dtype=float)
    dlog = np.asarray(dlog_factor, dtype=float)
    if dlog.ndim == 1:
        dlog = dlog[:, np.newaxis]
    n_params = dlog.shape[1] if dlog.ndim == 2 else 1
    bad = np.full(n_params, 0.0, dtype=float)
    if base.size == 0 or reference.size != base.size or log_factor.size != base.size or dlog.shape[0] != base.size:
        return 1e300, bad

    unclipped = np.isfinite(log_factor) & (log_factor >= -80.0) & (log_factor <= 80.0)
    factor = np.exp(np.clip(log_factor, -80.0, 80.0))
    dlog = np.where(unclipped[:, np.newaxis], dlog, 0.0)
    corrected = base * factor
    corrected_derivative = corrected[:, np.newaxis] * dlog
    valid = (
        np.isfinite(reference)
        & np.isfinite(corrected)
        & np.all(np.isfinite(corrected_derivative), axis=1)
    )
    if np.count_nonzero(valid) < 2:
        return 1e300, bad

    corrected_valid = corrected[valid]
    reference_valid = reference[valid]
    corrected_derivative_valid = corrected_derivative[valid]
    denominator = float(np.nansum(corrected_valid * corrected_valid))
    if not math.isfinite(denominator) or denominator <= 0:
        return 1e300, bad
    numerator = float(np.nansum(corrected_valid * reference_valid))
    scale = numerator / denominator
    dnumerator = np.nansum(corrected_derivative_valid * reference_valid[:, np.newaxis], axis=0)
    ddenominator = 2.0 * np.nansum(corrected_valid[:, np.newaxis] * corrected_derivative_valid, axis=0)
    scale_derivative = (dnumerator * denominator - numerator * ddenominator) / (denominator * denominator)
    residual = scale * corrected_valid - reference_valid
    residual_derivative = (
        scale_derivative[np.newaxis, :] * corrected_valid[:, np.newaxis]
        + scale * corrected_derivative_valid
    )
    loss = float(np.nansum(residual**2))
    gradient = 2.0 * np.nansum(residual[:, np.newaxis] * residual_derivative, axis=0)
    if not math.isfinite(loss) or not np.all(np.isfinite(gradient)):
        return 1e300, bad
    return loss, gradient.astype(float)


def _spt_batch_ls_losses(
    base_matrix: Any,
    reference_flux: Any,
    log_factor_grid: Any,
    min_points: int = 2,
    block_size: int = 32,
) -> np.ndarray:
    base = np.asarray(base_matrix, dtype=float)
    reference = np.asarray(reference_flux, dtype=float)
    log_grid = np.asarray(log_factor_grid, dtype=float)
    if base.ndim == 1:
        base = base[np.newaxis, :]
    if log_grid.ndim == 1:
        log_grid = log_grid[np.newaxis, :]
    if base.ndim != 2 or log_grid.ndim != 2 or reference.ndim != 1:
        return np.full((0, 0), np.inf, dtype=float)
    if base.shape[1] != reference.size or log_grid.shape[1] != reference.size:
        return np.full((log_grid.shape[0], base.shape[0]), np.inf, dtype=float)

    valid = np.isfinite(base) & np.isfinite(reference)[np.newaxis, :]
    point_counts = np.count_nonzero(valid, axis=1)
    base0 = np.where(valid, base, 0.0)
    reference0 = np.where(valid, reference[np.newaxis, :], 0.0)
    reference2 = np.nansum(reference0 * reference0, axis=1)
    losses = np.full((log_grid.shape[0], base.shape[0]), np.inf, dtype=float)
    for start in range(0, log_grid.shape[0], max(1, int(block_size))):
        stop = min(start + max(1, int(block_size)), log_grid.shape[0])
        factor = np.exp(np.clip(log_grid[start:stop], -80.0, 80.0))
        factor = np.where(np.isfinite(factor), factor, 0.0)
        corrected = factor[:, np.newaxis, :] * base0[np.newaxis, :, :]
        numerator = np.einsum("bnp,np->bn", corrected, reference0, optimize=True)
        denominator = np.einsum("bnp,bnp->bn", corrected, corrected, optimize=True)
        block_loss = reference2[np.newaxis, :] - (numerator * numerator) / np.where(denominator > 0, denominator, np.nan)
        block_loss = np.where(
            (denominator > 0) & (point_counts[np.newaxis, :] >= int(min_points)) & np.isfinite(block_loss),
            np.maximum(block_loss, 0.0),
            np.inf,
        )
        losses[start:stop] = block_loss
    return losses


def _spt_grid_parabolic_minima(grid_values: Any, losses: Any) -> np.ndarray:
    grid = np.asarray(grid_values, dtype=float)
    loss_grid = np.asarray(losses, dtype=float)
    if grid.ndim != 1 or loss_grid.ndim != 2 or loss_grid.shape[0] != grid.size or grid.size == 0:
        return np.asarray([], dtype=float)
    estimates = np.full(loss_grid.shape[1], np.nan, dtype=float)
    if grid.size == 1:
        has_value = np.any(np.isfinite(loss_grid), axis=0)
        estimates[has_value] = grid[0]
        return estimates
    step = float(np.nanmedian(np.diff(grid)))
    for column in range(loss_grid.shape[1]):
        column_losses = loss_grid[:, column]
        finite = np.isfinite(column_losses)
        if not np.any(finite):
            continue
        finite_losses = np.where(finite, column_losses, np.inf)
        best = int(np.argmin(finite_losses))
        estimate = float(grid[best])
        if 0 < best < grid.size - 1:
            y0, y1, y2 = column_losses[best - 1], column_losses[best], column_losses[best + 1]
            denominator = y0 - 2.0 * y1 + y2
            if np.isfinite(denominator) and denominator > 0 and np.isfinite(step):
                offset = 0.5 * step * (y0 - y2) / denominator
                if np.isfinite(offset) and abs(offset) <= abs(step):
                    estimate = float(grid[best] + offset)
        estimates[column] = float(np.clip(estimate, np.nanmin(grid), np.nanmax(grid)))
    return estimates


def _spt_batch_fixed_extinction_fit(
    base_matrix: Any,
    reference_flux: Any,
    extinction: Any,
    bounds: tuple[float, float] = (-50.0, 50.0),
    grid_size: int = 501,
) -> np.ndarray:
    grid = np.linspace(float(bounds[0]), float(bounds[1]), int(grid_size))
    extinction = np.asarray(extinction, dtype=float)
    log_factor_grid = (0.4 * math.log(10.0)) * grid[:, np.newaxis] * extinction[np.newaxis, :]
    losses = _spt_batch_ls_losses(base_matrix, reference_flux, log_factor_grid)
    return _spt_grid_parabolic_minima(grid, losses)


def _spt_batch_fixed_cloud_fit(
    base_matrix: Any,
    reference_flux: Any,
    wavelength_ratio: Any,
    alpha: float,
    bounds: tuple[float, float] = (-20.0, 20.0),
    grid_size: int = 501,
) -> np.ndarray:
    grid = np.linspace(float(bounds[0]), float(bounds[1]), int(grid_size))
    ratio = np.asarray(wavelength_ratio, dtype=float)
    alpha = max(float(alpha), 0.05)
    power = np.power(np.clip(ratio, 1e-6, None), -alpha)
    log_factor_grid = -grid[:, np.newaxis] * (power[np.newaxis, :] - 1.0)
    losses = _spt_batch_ls_losses(base_matrix, reference_flux, log_factor_grid)
    return _spt_grid_parabolic_minima(grid, losses)


def _spt_minimize_with_gradient(value_and_gradient, initial: list[float], bounds: list[tuple[float, float]]):
    from scipy.optimize import minimize

    cache: dict[str, Any] = {"x": None, "value": None, "gradient": None}

    def evaluate(params: Any) -> tuple[float, np.ndarray]:
        x = np.asarray(params, dtype=float)
        if cache["x"] is None or not np.array_equal(x, cache["x"]):
            value, gradient = value_and_gradient(x)
            cache["x"] = x.copy()
            cache["value"] = float(value)
            cache["gradient"] = np.asarray(gradient, dtype=float)
        return float(cache["value"]), np.asarray(cache["gradient"], dtype=float)

    def value(params: Any) -> float:
        return evaluate(params)[0]

    def jac(params: Any) -> np.ndarray:
        return evaluate(params)[1]

    return minimize(
        value,
        initial,
        jac=jac,
        bounds=bounds,
        method="L-BFGS-B",
    )


def _spt_optimize_av_rv_arrays(
    wavelength: Any,
    base_flux: Any,
    reference_flux: Any,
    fixed_r_v: float | None = None,
    initial_a_v: float | None = None,
    initial_r_v: float = 3.1,
    precomputed_ab: tuple[Any, Any] | None = None,
) -> tuple[float, float]:
    wv = np.asarray(wavelength, dtype=float)
    base = np.asarray(base_flux, dtype=float)
    reference = np.asarray(reference_flux, dtype=float)
    if precomputed_ab is None:
        a_coeff, b_coeff = _spt_cardelli_ab(wv)
    else:
        a_coeff = np.asarray(precomputed_ab[0], dtype=float)
        b_coeff = np.asarray(precomputed_ab[1], dtype=float)
    valid = (
        np.isfinite(wv)
        & np.isfinite(base)
        & np.isfinite(reference)
        & np.isfinite(a_coeff)
        & np.isfinite(b_coeff)
    )
    if np.count_nonzero(valid) < 2:
        fallback_rv = float(fixed_r_v) if fixed_r_v is not None and math.isfinite(float(fixed_r_v)) else float(initial_r_v)
        return 0.0, fallback_rv
    wv = wv[valid]
    base = base[valid]
    reference = reference[valid]
    a_coeff = a_coeff[valid]
    b_coeff = b_coeff[valid]
    log10_factor = 0.4 * math.log(10.0)

    def loss_and_grad_for(a_v: float, r_v: float) -> tuple[float, np.ndarray]:
        r_v = max(float(r_v), 0.01)
        extinction = a_coeff + b_coeff / r_v
        log_factor = log10_factor * float(a_v) * extinction
        dlog_da = log10_factor * extinction
        dlog_drv = log10_factor * float(a_v) * (-b_coeff / (r_v * r_v))
        return _spt_scaled_residual_ls_loss_and_grad(base, reference, log_factor, np.column_stack([dlog_da, dlog_drv]))

    if fixed_r_v is not None and math.isfinite(fixed_r_v) and fixed_r_v > 0:
        r_v = float(fixed_r_v)
        if initial_a_v is None or not math.isfinite(float(initial_a_v)):
            extinction = a_coeff + b_coeff / r_v
            warm = _spt_batch_fixed_extinction_fit(base[np.newaxis, :], reference, extinction)
            initial_a_v = float(warm[0]) if warm.size and np.isfinite(warm[0]) else 1.0
        initial_a_v = float(np.clip(float(initial_a_v), -50.0, 50.0))

        def fixed_value_and_gradient(params: np.ndarray) -> tuple[float, np.ndarray]:
            value, gradient = loss_and_grad_for(float(params[0]), r_v)
            return value, np.asarray([gradient[0]], dtype=float)

        result = _spt_minimize_with_gradient(
            fixed_value_and_gradient,
            [initial_a_v],
            [(-50, 50)],
        )
        return float(result.x[0]), r_v

    try:
        initial_r_v = float(initial_r_v)
    except (TypeError, ValueError):
        initial_r_v = 3.1
    initial_r_v = initial_r_v if math.isfinite(initial_r_v) and initial_r_v > 0 else 3.1
    if initial_a_v is None or not math.isfinite(float(initial_a_v)):
        warm_rv = float(np.clip(initial_r_v, 0.01, 50.5))
        extinction = a_coeff + b_coeff / warm_rv
        warm = _spt_batch_fixed_extinction_fit(base[np.newaxis, :], reference, extinction)
        initial_a_v = float(warm[0]) if warm.size and np.isfinite(warm[0]) else 1.0
    initial_a_v = float(np.clip(float(initial_a_v), -50.0, 50.0))
    initial_r_v = float(np.clip(initial_r_v, 0.01, 50.5))
    result = _spt_minimize_with_gradient(
        lambda params: loss_and_grad_for(float(params[0]), float(params[1])),
        [initial_a_v, initial_r_v],
        [(-50, 50), (0.01, 50.5)],
    )
    return float(result.x[0]), float(result.x[1])


def _spt_optimize_av_rv(
    observed_spectrum: pd.DataFrame,
    reference_spectrum: pd.DataFrame,
    fixed_r_v: float | None = None,
    initial_a_v: float | None = None,
) -> tuple[float, float]:
    return _spt_optimize_av_rv_arrays(
        observed_spectrum["wv"].to_numpy(dtype=float),
        observed_spectrum["spn"].to_numpy(dtype=float),
        reference_spectrum["spn"].to_numpy(dtype=float),
        fixed_r_v=fixed_r_v,
        initial_a_v=initial_a_v,
    )


def _spt_cloud_correct_flux_values(
    flux_values: Any,
    tau0: float,
    alpha: float = SPT_DEFAULT_CLOUD_ALPHA,
    wavelength_ratio: Any | None = None,
    wavelength: Any | None = None,
    lambda0: float = SPT_DEFAULT_CLOUD_LAMBDA0,
) -> np.ndarray:
    try:
        alpha = float(alpha)
    except (TypeError, ValueError):
        alpha = SPT_DEFAULT_CLOUD_ALPHA
    if not math.isfinite(alpha) or alpha <= 0:
        alpha = SPT_DEFAULT_CLOUD_ALPHA
    if wavelength_ratio is None:
        try:
            lambda0 = float(lambda0)
        except (TypeError, ValueError):
            lambda0 = SPT_DEFAULT_CLOUD_LAMBDA0
        lambda0 = lambda0 if math.isfinite(lambda0) and lambda0 > 0 else SPT_DEFAULT_CLOUD_LAMBDA0
        wavelength_ratio = np.asarray(wavelength, dtype=float) / lambda0
    ratio = np.clip(np.asarray(wavelength_ratio, dtype=float), 1e-6, None)
    exponent = -float(tau0) * (np.power(ratio, -alpha) - 1.0)
    return _spt_median_normalized_factor_apply(flux_values, exponent)


def _spt_cloud_correct_spectrum(
    spectrum: pd.DataFrame,
    tau0: float,
    alpha: float = SPT_DEFAULT_CLOUD_ALPHA,
    lambda0: float = SPT_DEFAULT_CLOUD_LAMBDA0,
) -> pd.DataFrame:
    out = spectrum.copy()
    out["spn"] = _spt_cloud_correct_flux_values(
        out["spn"].to_numpy(dtype=float),
        tau0,
        alpha=alpha,
        wavelength=out["wv"].to_numpy(dtype=float),
        lambda0=lambda0,
    )
    return out


def _spt_optimize_cloud_params_arrays(
    wavelength: Any,
    base_flux: Any,
    reference_flux: Any,
    fixed_alpha: float | None = SPT_DEFAULT_CLOUD_ALPHA,
    lambda0: float = SPT_DEFAULT_CLOUD_LAMBDA0,
    initial_alpha: float = SPT_DEFAULT_CLOUD_ALPHA,
    initial_tau0: float | None = None,
    precomputed_ratio: Any | None = None,
    precomputed_log_ratio: Any | None = None,
) -> tuple[float, float]:
    wv = np.asarray(wavelength, dtype=float)
    base = np.asarray(base_flux, dtype=float)
    reference = np.asarray(reference_flux, dtype=float)
    try:
        lambda0 = float(lambda0)
    except (TypeError, ValueError):
        lambda0 = SPT_DEFAULT_CLOUD_LAMBDA0
    lambda0 = lambda0 if math.isfinite(lambda0) and lambda0 > 0 else SPT_DEFAULT_CLOUD_LAMBDA0
    if precomputed_ratio is None:
        wavelength_ratio = np.clip(wv / lambda0, 1e-6, None)
    else:
        wavelength_ratio = np.clip(np.asarray(precomputed_ratio, dtype=float), 1e-6, None)
    if precomputed_log_ratio is None:
        log_wavelength_ratio = np.log(wavelength_ratio)
    else:
        log_wavelength_ratio = np.asarray(precomputed_log_ratio, dtype=float)
    valid = (
        np.isfinite(wv)
        & np.isfinite(base)
        & np.isfinite(reference)
        & np.isfinite(wavelength_ratio)
        & np.isfinite(log_wavelength_ratio)
    )
    if np.count_nonzero(valid) < 2:
        fallback_alpha = float(fixed_alpha) if fixed_alpha is not None and math.isfinite(float(fixed_alpha)) else float(initial_alpha)
        return 0.0, fallback_alpha
    base = base[valid]
    reference = reference[valid]
    wavelength_ratio = wavelength_ratio[valid]
    log_wavelength_ratio = log_wavelength_ratio[valid]

    def loss_and_grad_for(tau0: float, alpha: float) -> tuple[float, np.ndarray]:
        tau0 = float(tau0)
        alpha = max(float(alpha), 0.05)
        power = np.power(wavelength_ratio, -alpha)
        exponent = -tau0 * (power - 1.0)
        unclipped = np.isfinite(exponent) & (exponent >= -80.0) & (exponent <= 80.0)
        log_factor = np.clip(exponent, -80.0, 80.0)
        dlog_dtau = -(power - 1.0)
        dlog_dalpha = tau0 * power * log_wavelength_ratio
        dlog_dtau = np.where(unclipped, dlog_dtau, 0.0)
        dlog_dalpha = np.where(unclipped, dlog_dalpha, 0.0)
        return _spt_scaled_residual_ls_loss_and_grad(base, reference, log_factor, np.column_stack([dlog_dtau, dlog_dalpha]))

    if fixed_alpha is not None and math.isfinite(float(fixed_alpha)) and float(fixed_alpha) > 0:
        alpha = float(fixed_alpha)
        if initial_tau0 is None or not math.isfinite(float(initial_tau0)):
            warm = _spt_batch_fixed_cloud_fit(base[np.newaxis, :], reference, wavelength_ratio, alpha)
            initial_tau0 = float(warm[0]) if warm.size and np.isfinite(warm[0]) else 0.0
        initial_tau0 = float(np.clip(float(initial_tau0), -20.0, 20.0))

        def fixed_value_and_gradient(params: np.ndarray) -> tuple[float, np.ndarray]:
            value, gradient = loss_and_grad_for(float(params[0]), alpha)
            return value, np.asarray([gradient[0]], dtype=float)

        result = _spt_minimize_with_gradient(
            fixed_value_and_gradient,
            [initial_tau0],
            [(-20.0, 20.0)],
        )
        return float(result.x[0]), alpha

    try:
        initial_alpha = float(initial_alpha)
    except (TypeError, ValueError):
        initial_alpha = SPT_DEFAULT_CLOUD_ALPHA
    initial_alpha = initial_alpha if math.isfinite(initial_alpha) and initial_alpha > 0 else SPT_DEFAULT_CLOUD_ALPHA
    if initial_tau0 is None or not math.isfinite(float(initial_tau0)):
        warm = _spt_batch_fixed_cloud_fit(base[np.newaxis, :], reference, wavelength_ratio, initial_alpha)
        initial_tau0 = float(warm[0]) if warm.size and np.isfinite(warm[0]) else 0.0
    initial_tau0 = float(np.clip(float(initial_tau0), -20.0, 20.0))

    result = _spt_minimize_with_gradient(
        lambda params: loss_and_grad_for(float(params[0]), float(params[1])),
        [initial_tau0, initial_alpha],
        [(-20.0, 20.0), (0.05, 8.0)],
    )
    tau0, alpha = result.x
    return float(tau0), float(alpha)


def _spt_optimize_cloud_params(
    observed_spectrum: pd.DataFrame,
    reference_spectrum: pd.DataFrame,
    fixed_alpha: float | None = SPT_DEFAULT_CLOUD_ALPHA,
    lambda0: float = SPT_DEFAULT_CLOUD_LAMBDA0,
    initial_alpha: float = SPT_DEFAULT_CLOUD_ALPHA,
    initial_tau0: float | None = None,
) -> tuple[float, float]:
    return _spt_optimize_cloud_params_arrays(
        observed_spectrum["wv"].to_numpy(dtype=float),
        observed_spectrum["spn"].to_numpy(dtype=float),
        reference_spectrum["spn"].to_numpy(dtype=float),
        fixed_alpha=fixed_alpha,
        lambda0=lambda0,
        initial_alpha=initial_alpha,
        initial_tau0=initial_tau0,
    )


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


def _spt_common_wavelength_key(common_wv: Any) -> str:
    wv = np.asarray(common_wv, dtype=float)
    wv = np.sort(wv[np.isfinite(wv)])
    if wv.size == 0:
        return "empty"
    rounded = np.round(wv, 6).astype(np.float64)
    return hashlib.sha1(rounded.tobytes()).hexdigest()[:16]


def _spt_processed_standard_from_cache(
    args: dict[str, Any],
    std_specid: int,
    std_raw: pd.DataFrame,
    common_wv: np.ndarray,
    norm_regions_param: list[tuple[float, float]],
    bins_per_micron: int,
) -> pd.DataFrame:
    cache_key = "|".join([
        _spt_db_cache_key(args),
        "standard-process",
        str(int(std_specid)),
        str(int(bins_per_micron)),
        _spt_format_norm_regions(norm_regions_param),
        _spt_common_wavelength_key(common_wv),
    ])
    now = time.time()
    cached = _SPT_STANDARD_PROCESS_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1].copy(deep=True)
    processed = _spt_process_spectrum(
        std_raw,
        bins_per_micron=bins_per_micron,
        common_wv=common_wv,
        norm_regions_param=norm_regions_param,
    )
    if not processed.empty:
        processed["esp_calc"] = _spt_prepare_errors(processed["spn"], processed.get("espn"))
    _SPT_STANDARD_PROCESS_CACHE[cache_key] = (now, processed.copy(deep=True))
    return processed


def _spt_rescale_standard_to_comparison(
    std_df: pd.DataFrame,
    comparison_df: pd.DataFrame,
    norm_regions_param: list[tuple[float, float]],
) -> pd.DataFrame:
    if std_df.empty or comparison_df.empty:
        return std_df
    if "esp_calc" not in std_df.columns:
        std_df["esp_calc"] = _spt_prepare_errors(std_df["spn"], std_df.get("espn"))
    if "esp_calc" not in comparison_df.columns:
        comparison_df["esp_calc"] = _spt_prepare_errors(comparison_df["spn"], comparison_df.get("espn"))
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
    return std_df


def _spt_comparison_regions(
    comparison_df: pd.DataFrame,
    norm_regions_param: list[tuple[float, float]],
    cloud_lambda0: float,
) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    lambda0 = float(cloud_lambda0) if math.isfinite(float(cloud_lambda0)) and float(cloud_lambda0) > 0 else SPT_DEFAULT_CLOUD_LAMBDA0
    for index, (region_min, region_max) in enumerate(norm_regions_param):
        comp_seg = comparison_df[comparison_df["wv"].between(region_min, region_max)].copy()
        wv = comp_seg["wv"].to_numpy(dtype=float) if not comp_seg.empty else np.asarray([], dtype=float)
        a_coeff, b_coeff = _spt_cardelli_ab(wv)
        ratio = np.clip(wv / lambda0, 1e-6, None) if wv.size else np.asarray([], dtype=float)
        regions.append({
            "index": index,
            "min": float(region_min),
            "max": float(region_max),
            "df": comp_seg,
            "wv": wv,
            "spn": comp_seg["spn"].to_numpy(dtype=float) if not comp_seg.empty else np.asarray([], dtype=float),
            "esp_calc": comp_seg["esp_calc"].to_numpy(dtype=float) if not comp_seg.empty and "esp_calc" in comp_seg.columns else np.asarray([], dtype=float),
            "a_coeff": a_coeff,
            "b_coeff": b_coeff,
            "cloud_ratio": ratio,
            "cloud_log_ratio": np.log(ratio) if ratio.size else np.asarray([], dtype=float),
        })
    return regions


def _spt_standard_segments(
    std_df: pd.DataFrame,
    comparison_regions: list[dict[str, Any]],
    cloud_lambda0: float,
) -> list[dict[str, Any] | None]:
    segments: list[dict[str, Any] | None] = []
    lambda0 = float(cloud_lambda0) if math.isfinite(float(cloud_lambda0)) and float(cloud_lambda0) > 0 else SPT_DEFAULT_CLOUD_LAMBDA0
    for region in comparison_regions:
        if std_df.empty or region["wv"].size == 0:
            segments.append(None)
            continue
        mask = std_df["wv"].between(region["min"], region["max"])
        std_seg = std_df.loc[mask]
        if std_seg.empty:
            segments.append(None)
            continue
        std_wv = std_seg["wv"].to_numpy(dtype=float)
        std_spn = std_seg["spn"].to_numpy(dtype=float)
        interp_spn = _spt_interp_without_large_gaps(std_wv, std_spn, region["wv"])
        valid = np.isfinite(interp_spn) & np.isfinite(region["spn"])
        if not np.any(valid):
            segments.append(None)
            continue
        std_a, std_b = _spt_cardelli_ab(std_wv)
        std_ratio = np.clip(std_wv / lambda0, 1e-6, None)
        segments.append({
            "mask": mask,
            "std_wv": std_wv,
            "std_spn": std_spn,
            "interp_spn": interp_spn,
            "valid": valid,
            "std_a_coeff": std_a,
            "std_b_coeff": std_b,
            "std_cloud_ratio": std_ratio,
            "std_cloud_log_ratio": np.log(std_ratio),
        })
    return segments


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


def _spt_sql_wavelength_region_filter(regions: list[tuple[float, float]] | tuple[tuple[float, float], ...] | None) -> str:
    if not regions:
        return ""
    clauses = []
    for region_min, region_max in regions:
        lo = _spt_float(region_min)
        hi = _spt_float(region_max)
        if lo is None or hi is None:
            continue
        if hi < lo:
            lo, hi = hi, lo
        clauses.append(f"(ds.wavelength_angstrom BETWEEN {lo * 10000:.6f} AND {hi * 10000:.6f})")
    if not clauses:
        return ""
    return "AND (" + " OR ".join(clauses) + ")"


def _load_spt_grid_from_db(
    args: dict[str, Any],
    include_spectra: bool = True,
    wavelength_regions: list[tuple[float, float]] | tuple[tuple[float, float], ...] | None = None,
    bins_per_micron: int | None = None,
    standard_specids: list[int] | tuple[int, ...] | None = None,
) -> dict[str, Any]:
    region_key = _spt_format_norm_regions(list(wavelength_regions or [])) if wavelength_regions else "all"
    bins_key = max(1, min(int(bins_per_micron or 0), 2000)) if bins_per_micron else 0
    standard_specid_key = "all"
    standard_specid_set: set[int] = set()
    if standard_specids:
        standard_specid_set = {
            int(specid)
            for specid in standard_specids
            if specid is not None and math.isfinite(float(specid))
        }
        if standard_specid_set:
            standard_specid_key = ",".join(str(specid) for specid in sorted(standard_specid_set))
    cache_key = f"{_spt_db_cache_key(args)}|grid|spectra:{int(include_spectra)}|standards:{standard_specid_key}|regions:{region_key}|bins:{bins_key}"
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
        spectra_specids = sorted(set(specids) & standard_specid_set) if standard_specid_set else specids
        if include_spectra and spectra_specids:
            specid_clause = ",".join(str(specid) for specid in spectra_specids)
            region_filter = _spt_sql_wavelength_region_filter(wavelength_regions)
            if bins_key:
                bin_factor = bins_key / 10000.0
                spectra_df = _read_sql(conn, f"""
                    SELECT
                        ds.moca_specid,
                        AVG(ds.wavelength_angstrom) * 1e-4 AS wv,
                        AVG(ds.flux_flambda) AS sp,
                        CASE
                            WHEN COUNT(ds.flux_flambda_unc) = 0 THEN NULL
                            ELSE SQRT(AVG(ds.flux_flambda_unc * ds.flux_flambda_unc))
                        END AS esp
                    FROM data_spectra ds
                    WHERE ds.moca_specid IN ({specid_clause})
                        AND ds.ignored = 0
                        AND ds.flux_flambda IS NOT NULL
                        AND ds.wavelength_angstrom IS NOT NULL
                        {region_filter}
                    GROUP BY ds.moca_specid, FLOOR(ds.wavelength_angstrom * {bin_factor:.12g})
                    ORDER BY NULL
                """)
                if not spectra_df.empty:
                    spectra_df = spectra_df.sort_values(["moca_specid", "wv"], kind="mergesort").reset_index(drop=True)
            else:
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
                        {region_filter}
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
            "spectrum_regions": list(wavelength_regions or []),
            "spectrum_bins_per_micron": bins_key or None,
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
        LEFT JOIN data_spectral_types spt
            ON spt.moca_oid = ms.moca_oid
            AND spt.adopted = 1
        WHERE COALESCE(ms.ignored, 0) = 0
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
    cloud_correction: bool = False,
    cloud_alpha: float = SPT_DEFAULT_CLOUD_ALPHA,
    cloud_alpha_fixed: bool = True,
    cloud_lambda0: float = SPT_DEFAULT_CLOUD_LAMBDA0,
    only_standard_specid: int | None = None,
    priority_standard_specid: int | None = None,
) -> dict[str, Any]:
    bins = max(1, min(int(bins_per_micron or SPT_DEFAULT_BINS_PER_MICRON), 2000))
    norm_key = _spt_format_norm_regions(norm_regions_param)
    fixed_key = "" if fixed_r_v is None else f"{fixed_r_v:.6g}"
    if cloud_correction:
        deredden = False
    try:
        cloud_alpha = float(cloud_alpha)
    except (TypeError, ValueError):
        cloud_alpha = SPT_DEFAULT_CLOUD_ALPHA
    try:
        cloud_lambda0 = float(cloud_lambda0)
    except (TypeError, ValueError):
        cloud_lambda0 = SPT_DEFAULT_CLOUD_LAMBDA0
    cloud_alpha = cloud_alpha if math.isfinite(cloud_alpha) and cloud_alpha > 0 else SPT_DEFAULT_CLOUD_ALPHA
    cloud_lambda0 = cloud_lambda0 if math.isfinite(cloud_lambda0) and cloud_lambda0 > 0 else SPT_DEFAULT_CLOUD_LAMBDA0
    cloud_key = f"{int(cloud_correction)}|{int(cloud_alpha_fixed)}|{float(cloud_alpha):.6g}|{float(cloud_lambda0):.6g}"
    only_key = "" if only_standard_specid is None else str(int(only_standard_specid))
    cache_key = f"{_spt_db_cache_key(args)}|compare|{int(specid)}|{bins}|{norm_key}|{int(deredden)}|{fixed_key}|cloud|{cloud_key}|only|{only_key}"
    now = time.time()
    cached = _SPT_COMPARE_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    grid_payload = _load_spt_grid_from_db(
        args,
        wavelength_regions=norm_regions_param,
        bins_per_micron=bins,
        standard_specids=[int(only_standard_specid)] if only_standard_specid is not None else None,
    )
    spectrum_payload = _load_spt_spectrum_from_db(args, specid)
    comparison_raw = pd.DataFrame(spectrum_payload["spectrum"])
    grid_raw = pd.DataFrame(grid_payload["gridSpectra"])
    grid_data = pd.DataFrame(grid_payload["gridData"])
    if only_standard_specid is not None and not grid_data.empty and "moca_specid" in grid_data.columns:
        grid_data = grid_data[pd.to_numeric(grid_data["moca_specid"], errors="coerce") == int(only_standard_specid)].copy()
    if comparison_raw.empty:
        raise ValueError(f"No spectrum data found for moca_specid={int(specid)}")
    if grid_raw.empty or grid_data.empty:
        raise ValueError("No spectral typing grid data found")
    grid_data = grid_data.copy()
    grid_data["_spt_original_order"] = np.arange(len(grid_data))
    if priority_standard_specid is not None and "moca_specid" in grid_data.columns:
        priority_value = int(priority_standard_specid)
        grid_data["_spt_priority"] = (
            pd.to_numeric(grid_data["moca_specid"], errors="coerce") != priority_value
        ).astype(int)
        grid_data = grid_data.sort_values(["_spt_priority", "_spt_original_order"], kind="mergesort")

    comparison_df = _spt_process_spectrum(
        comparison_raw,
        bins_per_micron=bins,
        norm_regions_param=norm_regions_param,
    )
    if comparison_df.empty:
        raise ValueError("Selected comparison spectrum has no usable data in the normalization regions")
    comparison_df["esp_calc"] = _spt_prepare_errors(comparison_df["spn"], comparison_df.get("espn"))
    common_wv = np.sort(comparison_df["wv"].dropna().unique())

    comparison_regions = _spt_comparison_regions(comparison_df, norm_regions_param, cloud_lambda0)
    grid_raw_by_specid: dict[int, pd.DataFrame] = {}
    if "moca_specid" in grid_raw.columns:
        for raw_specid, raw_group in grid_raw.groupby("moca_specid", sort=False):
            if pd.isna(raw_specid):
                continue
            grid_raw_by_specid[int(raw_specid)] = raw_group.copy()

    standard_items: list[dict[str, Any]] = []
    for _, row in grid_data.iterrows():
        std_specid = row.get("moca_specid")
        if pd.isna(std_specid):
            continue
        std_specid = int(std_specid)
        std_raw = grid_raw_by_specid.get(std_specid)
        if std_raw is None or std_raw.empty:
            continue
        raw_flux = pd.to_numeric(std_raw.get("sp"), errors="coerce").to_numpy(dtype=float)
        if raw_flux.size == 0 or float(np.nansum(raw_flux)) == 0:
            continue
        std_df = _spt_processed_standard_from_cache(
            args,
            std_specid,
            std_raw,
            common_wv,
            norm_regions_param,
            bins,
        )
        if std_df.empty:
            continue
        std_df = _spt_rescale_standard_to_comparison(std_df.copy(deep=True), comparison_df, norm_regions_param)
        standard_items.append({
            "row": row,
            "std_specid": std_specid,
            "std_df": std_df,
            "segments": _spt_standard_segments(std_df, comparison_regions, cloud_lambda0),
            "spectrum_original": _spt_spectrum_records(std_df),
            "av_list": [None] * len(norm_regions_param),
            "rv_list": [None] * len(norm_regions_param),
            "cloud_tau_list": [None] * len(norm_regions_param),
            "cloud_alpha_list": [None] * len(norm_regions_param),
        })

    fixed_rv_value = _spt_float(fixed_r_v)
    if deredden and fixed_rv_value is not None and fixed_rv_value > 0:
        for index, region in enumerate(comparison_regions):
            fit_items: list[dict[str, Any]] = []
            base_rows: list[np.ndarray] = []
            for item in standard_items:
                segment = item["segments"][index]
                if segment is None:
                    continue
                base = np.asarray(segment["interp_spn"], dtype=float).copy()
                base[~segment["valid"]] = np.nan
                fit_items.append(item)
                base_rows.append(base)
            if not base_rows or region["spn"].size == 0:
                continue
            extinction = region["a_coeff"] + region["b_coeff"] / fixed_rv_value
            av_values = _spt_batch_fixed_extinction_fit(np.vstack(base_rows), region["spn"], extinction)
            for item, a_v in zip(fit_items, av_values):
                if np.isfinite(a_v):
                    item["av_list"][index] = float(a_v)
                    item["rv_list"][index] = float(fixed_rv_value)

    if cloud_correction and cloud_alpha_fixed:
        fixed_alpha = float(cloud_alpha)
        for index, region in enumerate(comparison_regions):
            fit_items = []
            base_rows = []
            for item in standard_items:
                segment = item["segments"][index]
                if segment is None:
                    continue
                base = np.asarray(segment["interp_spn"], dtype=float).copy()
                base[~segment["valid"]] = np.nan
                fit_items.append(item)
                base_rows.append(base)
            if not base_rows or region["spn"].size == 0:
                continue
            tau_values = _spt_batch_fixed_cloud_fit(np.vstack(base_rows), region["spn"], region["cloud_ratio"], fixed_alpha)
            for item, tau0 in zip(fit_items, tau_values):
                if np.isfinite(tau0):
                    item["cloud_tau_list"][index] = float(tau0)
                    item["cloud_alpha_list"][index] = float(fixed_alpha)

    results: list[dict[str, Any]] = []
    for item in standard_items:
        row = item["row"]
        std_specid = int(item["std_specid"])
        std_df = item["std_df"]
        spectrum_original = item["spectrum_original"]
        spectrum_dereddened: list[dict[str, Any]] | None = None
        spectrum_cloud: list[dict[str, Any]] | None = None
        av_list = list(item["av_list"])
        rv_list = list(item["rv_list"])
        cloud_tau_list = list(item["cloud_tau_list"])
        cloud_alpha_list = list(item["cloud_alpha_list"])
        metric_df = std_df
        if deredden:
            std_df_dered = std_df.copy()
            try:
                for index, region in enumerate(comparison_regions):
                    segment = item["segments"][index]
                    if segment is None:
                        continue
                    valid = segment["valid"]
                    if not np.any(valid):
                        continue
                    a_v = av_list[index]
                    r_v = rv_list[index]
                    if not (a_v is not None and r_v is not None and np.isfinite(float(a_v)) and np.isfinite(float(r_v))):
                        warm_rv = fixed_rv_value if fixed_rv_value is not None and fixed_rv_value > 0 else 3.1
                        warm_extinction = region["a_coeff"][valid] + region["b_coeff"][valid] / warm_rv
                        warm = _spt_batch_fixed_extinction_fit(
                            segment["interp_spn"][valid][np.newaxis, :],
                            region["spn"][valid],
                            warm_extinction,
                        )
                        initial_a_v = float(warm[0]) if warm.size and np.isfinite(warm[0]) else None
                        a_v, r_v = _spt_optimize_av_rv_arrays(
                            region["wv"][valid],
                            segment["interp_spn"][valid],
                            region["spn"][valid],
                            fixed_r_v=fixed_rv_value if fixed_rv_value is not None and fixed_rv_value > 0 else None,
                            initial_a_v=initial_a_v,
                            initial_r_v=warm_rv,
                            precomputed_ab=(region["a_coeff"][valid], region["b_coeff"][valid]),
                        )
                    av_list[index] = a_v
                    rv_list[index] = r_v
                    std_df_dered.loc[segment["mask"], "spn"] = _spt_deredden_flux_values(
                        segment["std_spn"],
                        float(a_v),
                        float(r_v),
                        segment["std_a_coeff"],
                        segment["std_b_coeff"],
                    )
                std_df_dered["esp_calc"] = _spt_prepare_errors(std_df_dered["spn"], std_df_dered.get("espn"))
                _spt_rescale_standard_to_comparison(std_df_dered, comparison_df, norm_regions_param)
                metric_df = std_df_dered
                spectrum_dereddened = _spt_spectrum_records(std_df_dered)
            except Exception:
                metric_df = std_df
                spectrum_dereddened = None
                av_list = [None] * len(norm_regions_param)
                rv_list = [None] * len(norm_regions_param)
        elif cloud_correction:
            std_df_cloud = std_df.copy()
            try:
                for index, region in enumerate(comparison_regions):
                    segment = item["segments"][index]
                    if segment is None:
                        continue
                    valid = segment["valid"]
                    if not np.any(valid):
                        continue
                    tau0 = cloud_tau_list[index]
                    fitted_alpha = cloud_alpha_list[index]
                    if not (tau0 is not None and fitted_alpha is not None and np.isfinite(float(tau0)) and np.isfinite(float(fitted_alpha))):
                        warm_alpha = float(cloud_alpha)
                        warm = _spt_batch_fixed_cloud_fit(
                            segment["interp_spn"][valid][np.newaxis, :],
                            region["spn"][valid],
                            region["cloud_ratio"][valid],
                            warm_alpha,
                        )
                        initial_tau0 = float(warm[0]) if warm.size and np.isfinite(warm[0]) else None
                        tau0, fitted_alpha = _spt_optimize_cloud_params_arrays(
                            region["wv"][valid],
                            segment["interp_spn"][valid],
                            region["spn"][valid],
                            fixed_alpha=warm_alpha if cloud_alpha_fixed else None,
                            lambda0=float(cloud_lambda0),
                            initial_alpha=warm_alpha,
                            initial_tau0=initial_tau0,
                            precomputed_ratio=region["cloud_ratio"][valid],
                            precomputed_log_ratio=region["cloud_log_ratio"][valid],
                        )
                    cloud_tau_list[index] = tau0
                    cloud_alpha_list[index] = fitted_alpha
                    std_df_cloud.loc[segment["mask"], "spn"] = _spt_cloud_correct_flux_values(
                        segment["std_spn"],
                        float(tau0),
                        alpha=float(fitted_alpha),
                        wavelength_ratio=segment["std_cloud_ratio"],
                    )
                std_df_cloud["esp_calc"] = _spt_prepare_errors(std_df_cloud["spn"], std_df_cloud.get("espn"))
                _spt_rescale_standard_to_comparison(std_df_cloud, comparison_df, norm_regions_param)
                metric_df = std_df_cloud
                spectrum_cloud = _spt_spectrum_records(std_df_cloud)
            except Exception:
                metric_df = std_df
                spectrum_cloud = None
                cloud_tau_list = [None] * len(norm_regions_param)
                cloud_alpha_list = [None] * len(norm_regions_param)

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
            if deredden:
                params = 3 * n_bands
            elif cloud_correction:
                params = (2 if cloud_alpha_fixed else 3) * n_bands
            else:
                params = n_bands
            dof = len(all_residuals) - params if len(all_residuals) > params else len(all_residuals)
            reduced_chi2 = float(1e3 * np.nansum(all_residuals**2) / dof) if dof > 0 else None
            mad = float(1e3 * np.nanmedian(np.abs(all_residuals)))
        else:
            reduced_chi2 = None
            mad = None

        results.append({
            "_spt_original_order": _pythonize(row.get("_spt_original_order")),
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
            "spectrum_cloud": spectrum_cloud,
            "A_V": [_pythonize(value) for value in av_list],
            "R_V": [_pythonize(value) for value in rv_list],
            "cloud_tau0": [_pythonize(value) for value in cloud_tau_list],
            "cloud_alpha": _pythonize(float(cloud_alpha)),
            "cloud_alpha_values": [_pythonize(value) for value in cloud_alpha_list],
            "cloud_alpha_fixed": bool(cloud_alpha_fixed),
            "cloud_lambda0": _pythonize(float(cloud_lambda0)),
            "reduced_chi2": _pythonize(reduced_chi2),
            "mad": _pythonize(mad),
        })

    results.sort(key=lambda entry: int(entry.get("_spt_original_order") if entry.get("_spt_original_order") is not None else 10**12))
    for entry in results:
        entry.pop("_spt_original_order", None)

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
            "cloud_correction": bool(cloud_correction),
            "cloud_alpha": _pythonize(float(cloud_alpha)),
            "cloud_alpha_fixed": bool(cloud_alpha_fixed),
            "cloud_lambda0": _pythonize(float(cloud_lambda0)),
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


def _mock_spt_compare(
    args: dict[str, Any],
    specid: int,
    bins: int,
    norm_regions_param: list[tuple[float, float]],
    deredden: bool,
    fixed_r_v: float | None,
    cloud_correction: bool = False,
    cloud_alpha: float = SPT_DEFAULT_CLOUD_ALPHA,
    cloud_alpha_fixed: bool = True,
    cloud_lambda0: float = SPT_DEFAULT_CLOUD_LAMBDA0,
    only_standard_specid: int | None = None,
    priority_standard_specid: int | None = None,
) -> dict[str, Any]:
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
    if only_standard_specid is not None:
        grid_data = grid_data[pd.to_numeric(grid_data["moca_specid"], errors="coerce") == int(only_standard_specid)].copy()
    if priority_standard_specid is not None and not grid_data.empty:
        grid_data = grid_data.copy()
        grid_data["_spt_original_order"] = np.arange(len(grid_data))
        grid_data["_spt_priority"] = (
            pd.to_numeric(grid_data["moca_specid"], errors="coerce") != int(priority_standard_specid)
        ).astype(int)
        grid_data = grid_data.sort_values(["_spt_priority", "_spt_original_order"], kind="mergesort")
    for _, row in grid_data.iterrows():
        std_raw = grid_raw[grid_raw["moca_specid"].astype(int) == int(row["moca_specid"])]
        std_df = _spt_process_spectrum(std_raw, common_wv=common_wv, norm_regions_param=norm_regions_param)
        if std_df.empty:
            continue
        std_df["esp_calc"] = _spt_prepare_errors(std_df["spn"], std_df.get("espn"))
        spectrum_original = _spt_spectrum_records(std_df)
        spectrum_cloud = None
        cloud_tau = [None] * len(norm_regions_param)
        cloud_alpha_values = [None] * len(norm_regions_param)
        metric_df = std_df
        if cloud_correction:
            std_df_cloud = std_df.copy()
            for index, (region_min, region_max) in enumerate(norm_regions_param):
                mask = std_df_cloud["wv"].between(region_min, region_max)
                tau0 = 0.18 * (index + 1)
                alpha_value = float(cloud_alpha) if cloud_alpha_fixed else float(cloud_alpha) + 0.15 * index
                cloud_tau[index] = tau0
                cloud_alpha_values[index] = alpha_value
                cloud_seg = _spt_cloud_correct_spectrum(
                    std_df_cloud.loc[mask, ["wv", "spn"]],
                    tau0,
                    alpha=alpha_value,
                    lambda0=cloud_lambda0,
                )
                if not cloud_seg.empty:
                    std_df_cloud.loc[mask, "spn"] = cloud_seg["spn"].to_numpy(dtype=float)
            metric_df = std_df_cloud
            spectrum_cloud = _spt_spectrum_records(std_df_cloud)
        residuals = []
        for region_min, region_max in norm_regions_param:
            comp_seg = comparison_df[comparison_df["wv"].between(region_min, region_max)]
            std_seg = metric_df[metric_df["wv"].between(region_min, region_max)]
            if comp_seg.empty or std_seg.empty:
                continue
            scale = _spt_scale_to_reference(
                comp_seg["wv"], comp_seg["spn"], comp_seg["esp_calc"],
                std_seg["wv"], std_seg["spn"], std_seg["esp_calc"],
            )
            if np.isfinite(scale):
                mask = metric_df["wv"].between(region_min, region_max)
                metric_df.loc[mask, "spn"] *= scale
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
            "spectrum": spectrum_original,
            "spectrum_dered": None,
            "spectrum_cloud": _spt_spectrum_records(metric_df) if cloud_correction else spectrum_cloud,
            "A_V": [None] * len(norm_regions_param),
            "R_V": [None] * len(norm_regions_param),
            "cloud_tau0": [_pythonize(value) for value in cloud_tau],
            "cloud_alpha": _pythonize(float(cloud_alpha)),
            "cloud_alpha_values": [_pythonize(value) for value in cloud_alpha_values],
            "cloud_alpha_fixed": bool(cloud_alpha_fixed),
            "cloud_lambda0": _pythonize(float(cloud_lambda0)),
            "reduced_chi2": _pythonize(reduced_chi2),
            "mad": None,
        })
    results.sort(key=lambda entry: int(entry.get("_spt_original_order") if entry.get("_spt_original_order") is not None else 10**12))
    for entry in results:
        entry.pop("_spt_original_order", None)
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
            "cloud_correction": bool(cloud_correction),
            "cloud_alpha": _pythonize(float(cloud_alpha)),
            "cloud_alpha_fixed": bool(cloud_alpha_fixed),
            "cloud_lambda0": _pythonize(float(cloud_lambda0)),
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


def _parse_spectra_explorer_specids(args: dict[str, Any]) -> list[int]:
    raw = args.get("specids") or args.get("moca_specid") or args.get("specid") or ""
    specids: list[int] = []
    for item in str(raw).replace(";", ",").split(","):
        item = item.strip()
        if item.isdigit():
            specid = int(item)
            if specid not in specids:
                specids.append(specid)
    if not specids:
        specids = list(SPECTRA_EXPLORER_DEFAULT_SPECIDS)
    return specids[:max(1, SPECTRA_EXPLORER_MAX_SELECTED)]


def _spectra_explorer_cache_key(args: dict[str, Any], specids: list[int]) -> str:
    bins = _spectra_explorer_bins_per_micron(args)
    return f"{_spt_db_cache_key(args)}|spectra-explorer|bins:{bins or 'raw'}|" + ",".join(str(int(specid)) for specid in specids)


def _spectra_explorer_bins_per_micron(args: dict[str, Any]) -> int:
    raw = args.get("bins") or args.get("bins_per_micron") or args.get("spe_bins")
    if raw is None or raw == "":
        raw = SPECTRA_EXPLORER_DEFAULT_BINS_PER_MICRON
    try:
        bins = int(raw)
    except (TypeError, ValueError):
        bins = SPECTRA_EXPLORER_DEFAULT_BINS_PER_MICRON
    return max(0, min(bins, 20000))


def _spectra_explorer_label(row: dict[str, Any]) -> str:
    specid = int(row["moca_specid"]) if row.get("moca_specid") is not None else "unknown"
    designation = row.get("designation") or row.get("spectrum_name") or f"specid{specid}"
    label = f"specid{specid}"
    if row.get("moca_oid") is not None:
        label += f",oid{int(row['moca_oid'])}"
    label += f": {designation}"
    if row.get("spectral_type"):
        label += f" ({row['spectral_type']})"
    if row.get("moca_instid"):
        label += f" with {row['moca_instid']}"
    if row.get("instrument_mode_name"):
        label += f" in {row['instrument_mode_name']} mode"
    if row.get("data_collection_date"):
        label += f" ({row['data_collection_date']})"
    return label


def _search_spectra_explorer_from_db(args: dict[str, Any], query: str | None, selected_specids: list[int] | None = None) -> dict[str, Any]:
    search_text = (query or "").strip()
    selected_specids = selected_specids or []
    if not search_text and not selected_specids:
        return {"options": [], "values": [], "meta": {"row_count": 0}}

    search_int: int | None = None
    if search_text.isdigit():
        search_int = int(search_text)

    base_query = """
        SELECT
            ms.moca_specid,
            ms.moca_oid,
            ms.moca_instid,
            ms.instrument_mode_name,
            ms.spectrum_name,
            ms.data_collection_date,
            COALESCE(ms.flux_units, 'NO_UNITS') AS flux_units,
            mo.designation,
            spt.spectral_type
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
    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        if selected_specids:
            specid_clause = ",".join(str(int(specid)) for specid in selected_specids)
            rows.extend(_records(_read_sql(conn, base_query + f"""
                AND ms.moca_specid IN ({specid_clause})
                ORDER BY FIELD(ms.moca_specid, {specid_clause})
            """)))
        if search_text:
            rows.extend(_records(_read_sql(conn, base_query + """
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
            })))

    seen: set[int] = set()
    options = []
    for row in rows:
        if row.get("moca_specid") is None:
            continue
        specid = int(row["moca_specid"])
        if specid in seen:
            continue
        seen.add(specid)
        options.append({**row, "value": specid, "label": _spectra_explorer_label(row)})
    values = [specid for specid in selected_specids if specid in seen]
    return {"options": options, "values": values, "meta": {"row_count": len(options)}}


def _load_spectra_explorer_from_db(args: dict[str, Any], specids: list[int]) -> dict[str, Any]:
    clean_specids = [int(specid) for specid in specids if int(specid) > 0]
    if not clean_specids:
        raise ValueError("At least one numeric moca_specid is required")
    bins_per_micron = _spectra_explorer_bins_per_micron(args)
    cache_key = _spectra_explorer_cache_key(args, clean_specids)
    now = time.time()
    cached = _SPECTRA_EXPLORER_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    specid_clause = ",".join(str(int(specid)) for specid in clean_specids)
    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        metadata_rows = _records(_read_sql(conn, f"""
            SELECT
                ms.moca_specid,
                ms.moca_oid,
                ms.moca_instid,
                ms.instrument_mode_name,
                ms.spectrum_name,
                ms.data_collection_date,
                COALESCE(ms.flux_units, 'NO_UNITS') AS flux_units,
                mo.designation,
                spt.spectral_type
            FROM moca_spectra ms
            LEFT JOIN moca_objects mo USING(moca_oid)
            LEFT JOIN data_spectral_types spt
                ON spt.moca_oid = ms.moca_oid
                AND spt.adopted = 1
            WHERE ms.moca_specid IN ({specid_clause})
                AND COALESCE(ms.ignored, 0) = 0
            ORDER BY FIELD(ms.moca_specid, {specid_clause})
        """))
        valid_specids = [
            int(row["moca_specid"])
            for row in metadata_rows
            if row.get("moca_specid") is not None
        ] or clean_specids
        valid_specid_clause = ",".join(str(int(specid)) for specid in valid_specids)
        if bins_per_micron:
            bin_factor = bins_per_micron / 10000.0
            rows_df = _read_sql(conn, f"""
                SELECT
                    ds.moca_specid,
                    AVG(ds.wavelength_angstrom) * 1e-4 AS lam,
                    AVG(ds.flux_flambda) AS sp,
                    SQRT(AVG(ds.flux_flambda_unc * ds.flux_flambda_unc)) AS esp
                FROM data_spectra ds
                WHERE ds.moca_specid IN ({valid_specid_clause})
                    AND ds.ignored = 0
                    AND ds.wavelength_angstrom IS NOT NULL
                    AND ds.flux_flambda IS NOT NULL
                GROUP BY ds.moca_specid, FLOOR(ds.wavelength_angstrom * {bin_factor:.12g})
                ORDER BY ds.moca_specid, lam
            """)
        else:
            rows_df = _read_sql(conn, f"""
                SELECT
                    ds.moca_specid,
                    ds.wavelength_angstrom * 1e-4 AS lam,
                    ds.flux_flambda AS sp,
                    ds.flux_flambda_unc AS esp
                FROM data_spectra ds
                WHERE ds.moca_specid IN ({valid_specid_clause})
                    AND ds.ignored = 0
                    AND ds.wavelength_angstrom IS NOT NULL
                    AND ds.flux_flambda IS NOT NULL
                ORDER BY ds.moca_specid, ds.wavelength_angstrom
            """)

    metadata_by_specid: dict[int, dict[str, Any]] = {}
    for row in metadata_rows:
        if row.get("moca_specid") is None:
            continue
        row = {**row, "label": _spectra_explorer_label(row)}
        metadata_by_specid[int(row["moca_specid"])] = row

    spectra = []
    total_rows = 0
    for specid in clean_specids:
        spec_rows = rows_df[rows_df["moca_specid"].astype(int) == int(specid)] if not rows_df.empty else pd.DataFrame()
        metadata = metadata_by_specid.get(int(specid), {"moca_specid": int(specid), "label": f"specid{int(specid)}"})
        average_resolving_power = (
            _spt_average_resolving_power(spec_rows["lam"].to_numpy(dtype=float))
            if not spec_rows.empty else None
        )
        row_records = _records(spec_rows)
        total_rows += len(row_records)
        spectra.append({
            "moca_specid": int(specid),
            "metadata": metadata,
            "rows": row_records,
            "meta": {
                "row_count": len(row_records),
                "average_resolving_power": _pythonize(average_resolving_power),
                "bins_per_micron": bins_per_micron or None,
            },
        })

    payload = {
        "spectra": spectra,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "specid_count": len(spectra),
            "row_count": total_rows,
            "bins_per_micron": bins_per_micron or None,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _SPECTRA_EXPLORER_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _mock_spectra_explorer_search(query: str | None, selected_specids: list[int] | None = None) -> dict[str, Any]:
    selected_specids = selected_specids or []
    rows = [
        {"moca_specid": 59595, "moca_oid": 602, "designation": "SIMP J013656.5+093347.3", "spectral_type": "T2.5", "moca_instid": "SpeX", "instrument_mode_name": "prism", "data_collection_date": "2013-10-20", "spectrum_name": "mock SpeX prism", "flux_units": "W/m2/A"},
        {"moca_specid": 13510, "moca_oid": 10995, "designation": "2MASS J05591914-1404488", "spectral_type": "T4.5", "moca_instid": "SpeX", "instrument_mode_name": "prism", "data_collection_date": "2006-11-03", "spectrum_name": "mock SpeX prism", "flux_units": "W/m2/A"},
        {"moca_specid": 8168, "moca_oid": 2616, "designation": "2MASS J03552337+1133437", "spectral_type": "L5 gamma", "moca_instid": "NIRSPEC", "instrument_mode_name": "low-res", "data_collection_date": "2016-09-18", "spectrum_name": "mock NIRSPEC", "flux_units": "W/m2/A"},
    ]
    q = str(query or "").strip().lower()
    if selected_specids:
        rows = [row for row in rows if int(row["moca_specid"]) in set(map(int, selected_specids))]
    elif q:
        rows = [
            row for row in rows
            if q in _spectra_explorer_label(row).lower()
            or q in str(row.get("moca_oid") or "").lower()
            or q in str(row.get("designation") or "").lower()
        ]
    options = [{**row, "value": row["moca_specid"], "label": _spectra_explorer_label(row)} for row in rows]
    return {
        "options": options,
        "values": [specid for specid in selected_specids if specid in {row["moca_specid"] for row in rows}],
        "meta": {"row_count": len(options)},
    }


def _mock_spectra_explorer_payload(specids: list[int]) -> dict[str, Any]:
    selected = specids or list(SPECTRA_EXPLORER_DEFAULT_SPECIDS)
    search_payload = _mock_spectra_explorer_search("", selected)
    metadata_by_specid = {int(row["moca_specid"]): row for row in search_payload["options"]}
    rng = np.random.default_rng(1234)
    spectra = []
    total_rows = 0
    for index, specid in enumerate(selected):
        specid = int(specid)
        low_res = index == 2 or specid == 8168
        step = 0.055 if low_res else 0.0025
        wave = np.arange(0.82, 2.48, step)
        water = 0.18 * np.exp(-0.5 * ((wave - 1.4) / 0.045) ** 2) + 0.24 * np.exp(-0.5 * ((wave - 1.9) / 0.07) ** 2)
        methane = (0.08 + 0.04 * index) * np.exp(-0.5 * ((wave - 1.65) / 0.08) ** 2)
        slope = 1.0 + 0.12 * np.sin(wave * (4.8 + index)) + 0.08 * (index - 1) * (wave - 1.55)
        flux_flambda_um = np.clip(slope - water - methane, 0.04, None) * (1.2 + 0.3 * index) * 1e-15
        flux_flambda_a = flux_flambda_um / 10000.0
        err = np.abs(flux_flambda_a) * (0.03 + 0.02 * index)
        noise = rng.normal(0.0, np.nanmedian(err), size=wave.size)
        rows = [
            {
                "moca_specid": specid,
                "lam": round(float(x), 6),
                "sp": float(y + dy),
                "esp": float(e),
            }
            for x, y, dy, e in zip(wave, flux_flambda_a, noise, err)
        ]
        metadata = metadata_by_specid.get(specid) or {
            "moca_specid": specid,
            "moca_oid": 900000 + specid,
            "designation": f"Mock spectrum {specid}",
            "spectral_type": "L/T",
            "moca_instid": "mock",
            "instrument_mode_name": "synthetic",
            "spectrum_name": f"mock spectrum {specid}",
            "flux_units": "W/m2/A",
        }
        spectra.append({
            "moca_specid": specid,
            "metadata": {**metadata, "label": _spectra_explorer_label(metadata)},
            "rows": rows,
            "meta": {
                "row_count": len(rows),
                "average_resolving_power": _spt_average_resolving_power(wave),
            },
        })
        total_rows += len(rows)
    return {
        "spectra": spectra,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "specid_count": len(spectra),
            "row_count": total_rows,
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _gaia_cmd_band_value(raw: Any, default_key: str) -> str:
    value = str(raw or "").strip()
    if not value:
        value = default_key
    if value.startswith(SIMPLE_PHOTOMETRY_PREFIX):
        value = value[len(SIMPLE_PHOTOMETRY_PREFIX):]
    normalized = value.upper().replace("_", "").replace("-", "")
    aliases = {
        "BP": "GBP",
        "GBP": "GBP",
        "G BP": "GBP",
        "RP": "GRP",
        "GRP": "GRP",
        "G RP": "GRP",
        "G": "G",
        "GRVS": "GRVS",
        "G RVS": "GRVS",
        "RVS": "GRVS",
    }
    simple_key = aliases.get(normalized)
    if simple_key in GAIA_CMD_SIMPLE_BANDS:
        return GAIA_CMD_SIMPLE_BANDS[simple_key]["psid"]
    raw_lower = value.lower()
    band_key = GAIA_CMD_PSID_BANDS.get(raw_lower)
    if band_key in GAIA_CMD_SIMPLE_BANDS:
        return GAIA_CMD_SIMPLE_BANDS[band_key]["psid"]
    return GAIA_CMD_SIMPLE_BANDS[default_key]["psid"]


def _gaia_cmd_psid_label(psid: str) -> str:
    band = GAIA_CMD_PSID_BANDS.get(psid)
    if band and band in GAIA_CMD_SIMPLE_BANDS:
        label = GAIA_CMD_SIMPLE_BANDS[band]["label"]
        release = psid.split("_", 1)[0].replace("gaiadr", "Gaia DR")
        return f"{label} ({release})" if psid != GAIA_CMD_SIMPLE_BANDS[band]["psid"] else label
    return psid


def _gaia_cmd_parse_float(raw: Any, default: float | None) -> float | None:
    if raw is None or str(raw).strip() == "":
        return default
    if str(raw).strip().lower() in {"0", "none", "off", "false", "all"}:
        return None
    value = _safe_float(raw)
    return value if value is not None and value > 0 else default


def _gaia_cmd_parse_max_objects(raw: Any) -> int:
    if raw is None or str(raw).strip() == "":
        return max(1, min(GAIA_CMD_DEFAULT_MAX_OBJECTS, GAIA_CMD_HARD_MAX_OBJECTS))
    if str(raw).strip().lower() in {"0", "none", "uncapped", "all"}:
        return GAIA_CMD_HARD_MAX_OBJECTS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = GAIA_CMD_DEFAULT_MAX_OBJECTS
    return max(1, min(value, GAIA_CMD_HARD_MAX_OBJECTS))


def _gaia_cmd_parse_aids(args: dict[str, Any]) -> list[str]:
    raw = (
        args.get("asso")
        or args.get("association")
        or args.get("associations")
        or args.get("moca_aid")
        or args.get("aid")
        or ""
    )
    aids: list[str] = []
    for item in str(raw or "").replace(";", ",").split(","):
        value = item.strip()
        if value and SAFE_ID_RE.match(value) and value not in aids:
            aids.append(value)
    return aids[:80]


def _gaia_cmd_parse_oids(args: dict[str, Any]) -> list[int]:
    raw = (
        args.get("oids")
        or args.get("oid")
        or args.get("moca_oids")
        or args.get("moca_oid")
        or args.get("highlight_oids")
        or args.get("highlight_oid")
        or ""
    )
    oids: list[int] = []
    for item in str(raw or "").replace(";", ",").split(","):
        value = item.strip()
        if value.isdigit():
            oid = int(value)
            if oid not in oids:
                oids.append(oid)
    return oids[:100]


def _gaia_cmd_raw_column(psid: str) -> str:
    return {
        "gaiadr3_bpmag": "phot_bp_mean_mag",
        "gaiadr3_gmag": "phot_g_mean_mag",
        "gaiadr3_rpmag": "phot_rp_mean_mag",
        "gaiadr3_grvsmag": "grvs_mag",
    }.get(str(psid or "").lower(), "phot_g_mean_mag")


def _gaia_cmd_selection(args: dict[str, Any]) -> dict[str, Any]:
    x1 = _gaia_cmd_band_value(args.get("x1") or args.get("xaxis_value_1"), "GBP")
    x2 = _gaia_cmd_band_value(args.get("x2") or args.get("xaxis_value_2"), "GRP")
    y = _gaia_cmd_band_value(args.get("y") or args.get("yaxis_value_1"), "G")
    raw_gaia = any(
        _as_bool(args.get(key))
        for key in ("raw_gaia", "raw_photometry", "use_raw_gaia", "use_raw_gaia_photometry")
    )
    extinction_corrected_only = any(
        _as_bool(args.get(key))
        for key in ("extinction_corrected", "extcorr", "extinction_corrected_only")
    )
    show_extinction_vectors = any(
        _as_bool(args.get(key))
        for key in ("extinction_vectors", "extcorr_vectors", "show_extinction_vectors")
    )
    show_sequences = not any(
        _as_false(args.get(key))
        for key in ("sequences", "display_sequences", "age_sequences", "show_sequences")
    )
    return {
        "x1": x1,
        "x2": x2,
        "y": y,
        "x_label": _gaia_cmd_psid_label(x1),
        "x2_label": _gaia_cmd_psid_label(x2),
        "y_label": _gaia_cmd_psid_label(y),
        "ruwe_max": _gaia_cmd_parse_float(args.get("ruwe") or args.get("ruwe_max"), 1.4),
        "max_objects": _gaia_cmd_parse_max_objects(args.get("max_objects") or args.get("limit")),
        "color_by_age": _as_bool(args.get("color_age") or args.get("color_by_age") or args.get("age")),
        "raw_gaia": raw_gaia,
        "extinction_corrected_only": extinction_corrected_only,
        "show_extinction_vectors": show_extinction_vectors,
        "show_sequences": show_sequences,
        "associations": _gaia_cmd_parse_aids(args),
        "highlight_oids": _gaia_cmd_parse_oids(args),
    }


def _gaia_cmd_cache_key(args: dict[str, Any], selection: dict[str, Any]) -> str:
    cfg = _db_config(args)
    return "|".join([
        cfg["host"],
        cfg["username"],
        cfg["dbname"],
        selection["x1"],
        selection["x2"],
        selection["y"],
        str(selection["ruwe_max"]),
        str(selection["max_objects"]),
        str(int(selection["color_by_age"])),
        str(int(selection["raw_gaia"])),
        str(int(selection["extinction_corrected_only"])),
        str(int(selection["show_extinction_vectors"])),
        str(int(selection["show_sequences"])),
        ",".join(selection["associations"]),
        ",".join(str(oid) for oid in selection["highlight_oids"]),
    ])


def _gaia_cmd_band_key(psid: str) -> str | None:
    return GAIA_CMD_PSID_BANDS.get(str(psid or "").lower())


def _gaia_cmd_sequence_ids(selection: dict[str, Any]) -> list[str]:
    if not selection.get("show_sequences", True):
        return []
    x1_band = _gaia_cmd_band_key(selection["x1"])
    x2_band = _gaia_cmd_band_key(selection["x2"])
    y_band = _gaia_cmd_band_key(selection["y"])
    if y_band != "G":
        return []
    prefix = None
    if x1_band == "GBP" and x2_band == "GRP":
        prefix = "bprp"
    elif x1_band == "G" and x2_band == "GRP":
        prefix = "grp"
    if prefix is None:
        return []
    return [f"{prefix}_mg_gaiadr3_ext_{suffix}" for suffix in GAIA_CMD_SEQUENCE_SUFFIXES]


def _load_gaia_cmd_options_from_db(args: dict[str, Any]) -> dict[str, Any]:
    cache_key = f"{_spt_db_cache_key(args)}|gaia-cmd-options"
    now = time.time()
    cached = _GAIA_CMD_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    simple_options = [
        {
            "value": row["psid"],
            "simple_value": key,
            "label": row["label"],
            "moca_psid": row["psid"],
            "system_band_simple": row["simple_band"],
        }
        for key, row in GAIA_CMD_SIMPLE_BANDS.items()
    ]
    payload = {
        "photometry": {
            "simple": simple_options,
            "advanced": [],
        },
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "default": {"x1": "gaiadr3_bpmag", "x2": "gaiadr3_rpmag", "y": "gaiadr3_gmag"},
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _GAIA_CMD_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _load_gaia_cmd_from_db(args: dict[str, Any]) -> dict[str, Any]:
    selection = _gaia_cmd_selection(args)
    cache_key = _gaia_cmd_cache_key(args, selection)
    now = time.time()
    cached = _GAIA_CMD_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    params: dict[str, Any] = {
        "x1_psid": selection["x1"],
        "x2_psid": selection["x2"],
        "y_psid": selection["y"],
    }
    x1_raw_col = _gaia_cmd_raw_column(selection["x1"])
    x2_raw_col = _gaia_cmd_raw_column(selection["x2"])
    y_raw_col = _gaia_cmd_raw_column(selection["y"])
    aid_clause = "NULL"
    aid_params: dict[str, Any] = {}
    if selection["associations"]:
        aid_clause, aid_params = _sql_in_clause("gcmd_aid", selection["associations"])
        params.update(aid_params)
    oid_clause = "NULL"
    oid_params: dict[str, Any] = {}
    if selection["highlight_oids"]:
        oid_clause = ",".join(str(int(oid)) for oid in selection["highlight_oids"])
    private_public_filter = "AND cbs.is_public = 0" if _is_private_db(args) else ""
    phot_extcorr_filter = {
        alias: f"AND {alias}.extinction_corrected = 1"
        for alias in ("px1", "px2", "py")
    } if selection["extinction_corrected_only"] else {alias: "" for alias in ("px1", "px2", "py")}
    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        started = time.time()
        frames: list[pd.DataFrame] = []
        field_table = "pcat_gaiadr3_100pc_field" if _is_private_db(args) else "cat_gaiadr3_100pc_field"
        field_table_available = _db_table_exists(conn, field_table)
        if field_table_available:
            field_df = _read_sql(conn, f"""
                SELECT
                    g.moca_oid,
                    COALESCE(mo.designation, field.designation) AS designation,
                    field.source_id,
                    'Field' AS sample,
                    NULL AS moca_aid,
                    NULL AS ya_prob,
                    0 AS highlighted,
                    CASE
                        WHEN mopc.all_prop_confidences LIKE '%multiple_system:C%'
                            OR mopc.all_prop_confidences LIKE '%multiple_system:Y%'
                        THEN 1 ELSE 0
                    END AS is_binary,
                    '{field_table}' AS photometry_source,
                    field.ruwe,
                    1000 / field.parallax AS distance_pc,
                    1000 * field.parallax_error / (field.parallax * field.parallax) AS distance_pc_unc,
                    0 AS distance_photometric_estimate,
                    field.{x1_raw_col} AS x1_mag,
                    NULL AS x1_mag_unc,
                    field.{x2_raw_col} AS x2_mag,
                    NULL AS x2_mag_unc,
                    field.{y_raw_col} AS y_mag,
                    NULL AS y_mag_unc,
                    :x1_psid AS x1_psid,
                    :x2_psid AS x2_psid,
                    :y_psid AS y_psid,
                    field.{x1_raw_col} - field.{x2_raw_col} AS x,
                    field.{y_raw_col} - 5 * LOG10(1000 / field.parallax) + 5 AS y,
                    NULL AS x1_extinction_a,
                    NULL AS x2_extinction_a,
                    NULL AS y_extinction_a,
                    NULL AS x_original,
                    NULL AS y_original,
                    NULL AS age_myr,
                    CASE
                        WHEN g.moca_oid IS NULL THEN NULL
                        ELSE CONCAT('https://mocadb.ca/search/results?search-query=oid%28', g.moca_oid, '%29&search-type=star')
                    END AS report_url
                FROM {field_table} field
                LEFT JOIN cat_gaiadr3 g
                    ON g.source_id = field.source_id
                LEFT JOIN moca_objects mo
                    ON mo.moca_oid = g.moca_oid
                LEFT JOIN mechanics_object_properties_combined mopc
                    ON mopc.moca_oid = g.moca_oid
                WHERE field.parallax IS NOT NULL
                    AND field.parallax > 0
                    AND (field.ruwe IS NULL OR field.ruwe < 1.4)
                    AND field.{x1_raw_col} IS NOT NULL
                    AND field.{x2_raw_col} IS NOT NULL
                    AND field.{y_raw_col} IS NOT NULL
                LIMIT {selection["max_objects"]}
            """, params)
            frames.append(field_df)

        if selection["associations"]:
            if selection["raw_gaia"]:
                association_sql = f"""
                    SELECT
                        cbs.moca_oid,
                        COALESCE(mo.designation, g.designation, CONCAT('oid', cbs.moca_oid)) AS designation,
                        g.source_id,
                        cbs.moca_aid AS sample,
                        cbs.moca_aid,
                        cbs.ya_prob,
                        0 AS highlighted,
                        CASE
                            WHEN mopc.all_prop_confidences LIKE '%multiple_system:C%'
                                OR mopc.all_prop_confidences LIKE '%multiple_system:Y%'
                            THEN 1 ELSE 0
                        END AS is_binary,
                        'cat_gaiadr3' AS photometry_source,
                        g.ruwe,
                        dd.distance_pc,
                        dd.distance_pc_unc,
                        0 AS distance_photometric_estimate,
                        g.{x1_raw_col} AS x1_mag,
                        NULL AS x1_mag_unc,
                        g.{x2_raw_col} AS x2_mag,
                        NULL AS x2_mag_unc,
                        g.{y_raw_col} AS y_mag,
                        NULL AS y_mag_unc,
                        :x1_psid AS x1_psid,
                        :x2_psid AS x2_psid,
                        :y_psid AS y_psid,
                        g.{x1_raw_col} - g.{x2_raw_col} AS x,
                        g.{y_raw_col} - 5 * LOG10(dd.distance_pc) + 5 AS y,
                        NULL AS x1_extinction_a,
                        NULL AS x2_extinction_a,
                        NULL AS y_extinction_a,
                        NULL AS x_original,
                        NULL AS y_original,
                        daa.age_myr,
                        CONCAT('https://mocadb.ca/search/results?search-query=oid%28', cbs.moca_oid, '%29&search-type=star') AS report_url
                    FROM calc_banyan_sigma cbs
                    JOIN cat_gaiadr3 g
                        ON g.moca_oid = cbs.moca_oid
                    JOIN data_distances dd
                        ON dd.moca_oid = cbs.moca_oid
                        AND dd.adopted = 1
                        AND dd.photometric_estimate = 0
                        AND dd.distance_pc IS NOT NULL
                        AND dd.distance_pc > 0
                    LEFT JOIN data_association_ages daa
                        ON daa.moca_aid = cbs.moca_aid
                        AND daa.adopted = 1
                    LEFT JOIN moca_objects mo
                        ON mo.moca_oid = cbs.moca_oid
                    LEFT JOIN mechanics_object_properties_combined mopc
                        ON mopc.moca_oid = cbs.moca_oid
                    WHERE cbs.moca_aid IN ({aid_clause})
                        AND cbs.ya_prob >= 90
                        AND cbs.max_observables = 1
                        AND cbs.moca_bsmdid = (
                            SELECT moca_bsmdid
                            FROM moca_banyan_sigma_models
                            WHERE adopted = 1
                            ORDER BY moca_bsmdid DESC
                            LIMIT 1
                        )
                        {private_public_filter}
                        AND g.{x1_raw_col} IS NOT NULL
                        AND g.{x2_raw_col} IS NOT NULL
                        AND g.{y_raw_col} IS NOT NULL
                    ORDER BY cbs.moca_aid, cbs.moca_oid
                    LIMIT {selection["max_objects"]}
                """
            else:
                association_sql = f"""
                    SELECT
                        cbs.moca_oid,
                        COALESCE(mo.designation, g.designation, CONCAT('oid', cbs.moca_oid)) AS designation,
                        g.source_id,
                        cbs.moca_aid AS sample,
                        cbs.moca_aid,
                        cbs.ya_prob,
                        0 AS highlighted,
                        CASE
                            WHEN mopc.all_prop_confidences LIKE '%multiple_system:C%'
                                OR mopc.all_prop_confidences LIKE '%multiple_system:Y%'
                            THEN 1 ELSE 0
                        END AS is_binary,
                        'data_photometry' AS photometry_source,
                        g.ruwe,
                        dd.distance_pc,
                        dd.distance_pc_unc,
                        0 AS distance_photometric_estimate,
                        px1.magnitude AS x1_mag,
                        px1.magnitude_unc AS x1_mag_unc,
                        px2.magnitude AS x2_mag,
                        px2.magnitude_unc AS x2_mag_unc,
                        py.magnitude AS y_mag,
                        py.magnitude_unc AS y_mag_unc,
                        px1.moca_psid AS x1_psid,
                        px2.moca_psid AS x2_psid,
                        py.moca_psid AS y_psid,
                        px1.magnitude - px2.magnitude AS x,
                        py.magnitude - 5 * LOG10(dd.distance_pc) + 5 AS y,
                        px1.extinction_a AS x1_extinction_a,
                        px2.extinction_a AS x2_extinction_a,
                        py.extinction_a AS y_extinction_a,
                        CASE
                            WHEN px1.extinction_corrected = 1
                                AND px2.extinction_corrected = 1
                                AND py.extinction_corrected = 1
                                AND px1.extinction_a IS NOT NULL
                                AND px2.extinction_a IS NOT NULL
                                AND py.extinction_a IS NOT NULL
                            THEN (px1.magnitude + px1.extinction_a) - (px2.magnitude + px2.extinction_a)
                            ELSE NULL
                        END AS x_original,
                        CASE
                            WHEN px1.extinction_corrected = 1
                                AND px2.extinction_corrected = 1
                                AND py.extinction_corrected = 1
                                AND px1.extinction_a IS NOT NULL
                                AND px2.extinction_a IS NOT NULL
                                AND py.extinction_a IS NOT NULL
                            THEN (py.magnitude + py.extinction_a) - 5 * LOG10(dd.distance_pc) + 5
                            ELSE NULL
                        END AS y_original,
                        daa.age_myr,
                        CONCAT('https://mocadb.ca/search/results?search-query=oid%28', cbs.moca_oid, '%29&search-type=star') AS report_url
                    FROM calc_banyan_sigma cbs
                    JOIN data_distances dd
                        ON dd.moca_oid = cbs.moca_oid
                        AND dd.adopted = 1
                        AND dd.photometric_estimate = 0
                        AND dd.distance_pc IS NOT NULL
                        AND dd.distance_pc > 0
                    JOIN data_photometry px1
                        ON px1.moca_oid = cbs.moca_oid
                        AND px1.moca_psid = :x1_psid
                        AND px1.adopted = 1
                        {phot_extcorr_filter["px1"]}
                        AND px1.magnitude IS NOT NULL
                    JOIN data_photometry px2
                        ON px2.moca_oid = cbs.moca_oid
                        AND px2.moca_psid = :x2_psid
                        AND px2.adopted = 1
                        {phot_extcorr_filter["px2"]}
                        AND px2.magnitude IS NOT NULL
                    JOIN data_photometry py
                        ON py.moca_oid = cbs.moca_oid
                        AND py.moca_psid = :y_psid
                        AND py.adopted = 1
                        {phot_extcorr_filter["py"]}
                        AND py.magnitude IS NOT NULL
                    LEFT JOIN cat_gaiadr3 g
                        ON g.moca_oid = cbs.moca_oid
                    LEFT JOIN data_association_ages daa
                        ON daa.moca_aid = cbs.moca_aid
                        AND daa.adopted = 1
                    LEFT JOIN moca_objects mo
                        ON mo.moca_oid = cbs.moca_oid
                    LEFT JOIN mechanics_object_properties_combined mopc
                        ON mopc.moca_oid = cbs.moca_oid
                    WHERE cbs.moca_aid IN ({aid_clause})
                        AND cbs.ya_prob >= 90
                        AND cbs.max_observables = 1
                        AND cbs.moca_bsmdid = (
                            SELECT moca_bsmdid
                            FROM moca_banyan_sigma_models
                            WHERE adopted = 1
                            ORDER BY moca_bsmdid DESC
                            LIMIT 1
                        )
                        {private_public_filter}
                    ORDER BY cbs.moca_aid, cbs.moca_oid
                    LIMIT {selection["max_objects"]}
                """
            frames.append(_read_sql(conn, association_sql, params))

        if selection["highlight_oids"]:
            if selection["raw_gaia"]:
                highlight_sql = f"""
                    SELECT
                        g.moca_oid,
                        COALESCE(mo.designation, g.designation, CONCAT('oid', g.moca_oid)) AS designation,
                        g.source_id,
                        'Highlighted' AS sample,
                        NULL AS moca_aid,
                        NULL AS ya_prob,
                        1 AS highlighted,
                        CASE
                            WHEN mopc.all_prop_confidences LIKE '%multiple_system:C%'
                                OR mopc.all_prop_confidences LIKE '%multiple_system:Y%'
                            THEN 1 ELSE 0
                        END AS is_binary,
                        'cat_gaiadr3' AS photometry_source,
                        g.ruwe,
                        COALESCE(dd.distance_pc, 1000 / g.parallax) AS distance_pc,
                        dd.distance_pc_unc,
                        0 AS distance_photometric_estimate,
                        g.{x1_raw_col} AS x1_mag,
                        NULL AS x1_mag_unc,
                        g.{x2_raw_col} AS x2_mag,
                        NULL AS x2_mag_unc,
                        g.{y_raw_col} AS y_mag,
                        NULL AS y_mag_unc,
                        :x1_psid AS x1_psid,
                        :x2_psid AS x2_psid,
                        :y_psid AS y_psid,
                        g.{x1_raw_col} - g.{x2_raw_col} AS x,
                        g.{y_raw_col} - 5 * LOG10(COALESCE(dd.distance_pc, 1000 / g.parallax)) + 5 AS y,
                        NULL AS x1_extinction_a,
                        NULL AS x2_extinction_a,
                        NULL AS y_extinction_a,
                        NULL AS x_original,
                        NULL AS y_original,
                        NULL AS age_myr,
                        CONCAT('https://mocadb.ca/search/results?search-query=oid%28', g.moca_oid, '%29&search-type=star') AS report_url
                    FROM cat_gaiadr3 g
                    LEFT JOIN data_distances dd
                        ON dd.moca_oid = g.moca_oid
                        AND dd.adopted = 1
                        AND dd.photometric_estimate = 0
                        AND dd.distance_pc IS NOT NULL
                        AND dd.distance_pc > 0
                    LEFT JOIN moca_objects mo
                        ON mo.moca_oid = g.moca_oid
                    LEFT JOIN mechanics_object_properties_combined mopc
                        ON mopc.moca_oid = g.moca_oid
                    WHERE g.moca_oid IN ({oid_clause})
                        AND COALESCE(dd.distance_pc, 1000 / g.parallax) > 0
                        AND g.{x1_raw_col} IS NOT NULL
                        AND g.{x2_raw_col} IS NOT NULL
                        AND g.{y_raw_col} IS NOT NULL
                """
            else:
                highlight_sql = f"""
                    SELECT
                        g.moca_oid,
                        COALESCE(mo.designation, g.designation, CONCAT('oid', g.moca_oid)) AS designation,
                        g.source_id,
                        'Highlighted' AS sample,
                        NULL AS moca_aid,
                        NULL AS ya_prob,
                        1 AS highlighted,
                        CASE
                            WHEN mopc.all_prop_confidences LIKE '%multiple_system:C%'
                                OR mopc.all_prop_confidences LIKE '%multiple_system:Y%'
                            THEN 1 ELSE 0
                        END AS is_binary,
                        'data_photometry' AS photometry_source,
                        g.ruwe,
                        COALESCE(dd.distance_pc, 1000 / g.parallax) AS distance_pc,
                        dd.distance_pc_unc,
                        0 AS distance_photometric_estimate,
                        px1.magnitude AS x1_mag,
                        px1.magnitude_unc AS x1_mag_unc,
                        px2.magnitude AS x2_mag,
                        px2.magnitude_unc AS x2_mag_unc,
                        py.magnitude AS y_mag,
                        py.magnitude_unc AS y_mag_unc,
                        px1.moca_psid AS x1_psid,
                        px2.moca_psid AS x2_psid,
                        py.moca_psid AS y_psid,
                        px1.magnitude - px2.magnitude AS x,
                        py.magnitude - 5 * LOG10(COALESCE(dd.distance_pc, 1000 / g.parallax)) + 5 AS y,
                        px1.extinction_a AS x1_extinction_a,
                        px2.extinction_a AS x2_extinction_a,
                        py.extinction_a AS y_extinction_a,
                        CASE
                            WHEN px1.extinction_corrected = 1
                                AND px2.extinction_corrected = 1
                                AND py.extinction_corrected = 1
                                AND px1.extinction_a IS NOT NULL
                                AND px2.extinction_a IS NOT NULL
                                AND py.extinction_a IS NOT NULL
                            THEN (px1.magnitude + px1.extinction_a) - (px2.magnitude + px2.extinction_a)
                            ELSE NULL
                        END AS x_original,
                        CASE
                            WHEN px1.extinction_corrected = 1
                                AND px2.extinction_corrected = 1
                                AND py.extinction_corrected = 1
                                AND px1.extinction_a IS NOT NULL
                                AND px2.extinction_a IS NOT NULL
                                AND py.extinction_a IS NOT NULL
                            THEN (py.magnitude + py.extinction_a) - 5 * LOG10(COALESCE(dd.distance_pc, 1000 / g.parallax)) + 5
                            ELSE NULL
                        END AS y_original,
                        NULL AS age_myr,
                        CONCAT('https://mocadb.ca/search/results?search-query=oid%28', g.moca_oid, '%29&search-type=star') AS report_url
                    FROM cat_gaiadr3 g
                    JOIN data_photometry px1
                        ON px1.moca_oid = g.moca_oid
                        AND px1.moca_psid = :x1_psid
                        AND px1.adopted = 1
                        {phot_extcorr_filter["px1"]}
                        AND px1.magnitude IS NOT NULL
                    JOIN data_photometry px2
                        ON px2.moca_oid = g.moca_oid
                        AND px2.moca_psid = :x2_psid
                        AND px2.adopted = 1
                        {phot_extcorr_filter["px2"]}
                        AND px2.magnitude IS NOT NULL
                    JOIN data_photometry py
                        ON py.moca_oid = g.moca_oid
                        AND py.moca_psid = :y_psid
                        AND py.adopted = 1
                        {phot_extcorr_filter["py"]}
                        AND py.magnitude IS NOT NULL
                    LEFT JOIN data_distances dd
                        ON dd.moca_oid = g.moca_oid
                        AND dd.adopted = 1
                        AND dd.photometric_estimate = 0
                        AND dd.distance_pc IS NOT NULL
                        AND dd.distance_pc > 0
                    LEFT JOIN moca_objects mo
                        ON mo.moca_oid = g.moca_oid
                    LEFT JOIN mechanics_object_properties_combined mopc
                        ON mopc.moca_oid = g.moca_oid
                    WHERE g.moca_oid IN ({oid_clause})
                        AND COALESCE(dd.distance_pc, 1000 / g.parallax) > 0
                """
            frames.append(_read_sql(conn, highlight_sql, params))

        nonempty_frames = [frame for frame in frames if frame is not None and not frame.empty]
        rows_df = pd.concat(nonempty_frames, ignore_index=True) if nonempty_frames else pd.DataFrame()
        query_seconds = round(time.time() - started, 3)
        for column, digits in {
            "ruwe": 5,
            "distance_pc": 5,
            "distance_pc_unc": 5,
            "x1_mag": 5,
            "x1_mag_unc": 5,
            "x1_extinction_a": 5,
            "x2_mag": 5,
            "x2_mag_unc": 5,
            "x2_extinction_a": 5,
            "y_mag": 5,
            "y_mag_unc": 5,
            "y_extinction_a": 5,
            "x": 5,
            "y": 5,
            "x_original": 5,
            "y_original": 5,
            "age_myr": 3,
            "ya_prob": 3,
        }.items():
            if column in rows_df.columns:
                rows_df[column] = pd.to_numeric(rows_df[column], errors="coerce").round(digits)

        seqids = _gaia_cmd_sequence_ids(selection)
        sequences: list[dict[str, Any]] = []
        if seqids:
            seq_clause, seq_params = _sql_in_clause("seqid", seqids)
            sequence_rows = _records(_read_sql(conn, f"""
                SELECT
                    ms.moca_seqid,
                    COALESCE(ms.name_bdcolapp, ms.moca_seqid) AS name,
                    das.xdata,
                    das.ydata,
                    das.yerror
                FROM moca_sequences ms
                JOIN data_astro_sequences das
                    ON das.moca_seqid = ms.moca_seqid
                WHERE ms.moca_seqid IN ({seq_clause})
                    AND ms.display_in_bdcolapp = 1
                    AND ms.ignored = 0
                    AND das.ignored = 0
                    AND das.xdata IS NOT NULL
                    AND das.ydata IS NOT NULL
                ORDER BY ms.moca_seqid, das.xdata
            """, seq_params))
            by_seqid: dict[str, dict[str, Any]] = {}
            for row in sequence_rows:
                seqid = str(row.get("moca_seqid") or "")
                if not seqid:
                    continue
                item = by_seqid.setdefault(seqid, {
                    "moca_seqid": seqid,
                    "name": row.get("name") or seqid,
                    "x": [],
                    "y": [],
                    "yerror": [],
                })
                item["x"].append(round(float(row["xdata"]), 5) if row.get("xdata") is not None else None)
                item["y"].append(round(float(row["ydata"]), 5) if row.get("ydata") is not None else None)
                item["yerror"].append(round(float(row["yerror"]), 5) if row.get("yerror") is not None else None)
            sequences = list(by_seqid.values())

    rows = _records(rows_df)
    payload = {
        "selection": selection,
        "rows": rows,
        "sequences": sequences,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "row_count": len(rows),
            "sequence_count": len(sequences),
            "sequence_ids": _gaia_cmd_sequence_ids(selection),
            "truncated": len(rows) >= selection["max_objects"],
            "max_objects": selection["max_objects"],
            "query_seconds": query_seconds,
            "field_table": field_table,
            "field_table_available": field_table_available,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _GAIA_CMD_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _mock_gaia_cmd_payload(args: dict[str, Any]) -> dict[str, Any]:
    selection = _gaia_cmd_selection(args)
    rng = np.random.default_rng(433)
    rows = []
    for index in range(min(selection["max_objects"], 2500)):
        bp_rp = float(rng.uniform(-0.2, 4.8))
        abs_g = 2.2 + 3.1 * bp_rp + 0.65 * bp_rp * bp_rp + float(rng.normal(0, 0.35))
        dist = float(10 ** rng.uniform(0.65, 2.8))
        gmag = abs_g + 5 * math.log10(dist) - 5
        selected_aids = selection["associations"]
        aid = selected_aids[index % len(selected_aids)] if selected_aids and index % 12 == 0 else None
        age = 10 ** rng.uniform(1.0, 3.1) if aid else None
        moca_oid = 800000 + index if aid or index % 21 == 0 else None
        x1_mag = gmag + bp_rp * 0.55
        x2_mag = gmag - bp_rp * 0.45
        y_mag = gmag
        has_mock_extinction = bool(aid and not selection["raw_gaia"])
        x1_extinction_a = round(float(rng.uniform(0.08, 0.35)), 4) if has_mock_extinction else None
        x2_extinction_a = round(float(rng.uniform(0.04, 0.22)), 4) if has_mock_extinction else None
        y_extinction_a = round(float(rng.uniform(0.05, 0.28)), 4) if has_mock_extinction else None
        x_original = (x1_mag + x1_extinction_a) - (x2_mag + x2_extinction_a) if has_mock_extinction else None
        y_original = (y_mag + y_extinction_a) - 5 * math.log10(dist) + 5 if has_mock_extinction else None
        rows.append({
            "moca_oid": moca_oid,
            "designation": f"Mock Gaia CMD star {index}",
            "source_id": str(6000000000000000000 + index),
            "sample": aid or "Field",
            "moca_aid": aid,
            "ya_prob": round(float(rng.uniform(90, 100)), 2) if aid else None,
            "highlighted": 1 if moca_oid in selection["highlight_oids"] else 0,
            "is_binary": 1 if index % 17 == 0 else 0,
            "photometry_source": "data_photometry" if aid and not selection["raw_gaia"] else "pcat_gaiadr3_100pc_field",
            "ruwe": round(float(rng.uniform(0.75, 2.2)), 3),
            "distance_pc": round(dist, 3),
            "distance_pc_unc": round(0.03 * dist, 3),
            "distance_photometric_estimate": 0,
            "x1_mag": round(x1_mag, 4),
            "x1_mag_unc": 0.015,
            "x1_extinction_a": x1_extinction_a,
            "x2_mag": round(x2_mag, 4),
            "x2_mag_unc": 0.014,
            "x2_extinction_a": x2_extinction_a,
            "y_mag": round(y_mag, 4),
            "y_mag_unc": 0.012,
            "y_extinction_a": y_extinction_a,
            "x1_psid": selection["x1"],
            "x2_psid": selection["x2"],
            "y_psid": selection["y"],
            "x": round(bp_rp, 5),
            "y": round(abs_g, 5),
            "x_original": round(x_original, 5) if x_original is not None else None,
            "y_original": round(y_original, 5) if y_original is not None else None,
            "age_myr": round(age, 2) if age else None,
            "report_url": f"https://mocadb.ca/search/results?search-query=oid%28{moca_oid}%29&search-type=star" if moca_oid else None,
        })
    sequences = []
    for seqid in _gaia_cmd_sequence_ids(selection):
        x = np.linspace(-0.1, 4.7, 120)
        offset = {"field": 0.0, "mel5": -0.7, "abdmg": -0.45, "tha": -0.55, "bpmg": -0.6, "twa": -0.75, "etac": -0.8}.get(seqid.rsplit("_", 1)[-1], 0.0)
        y = 2.2 + 3.1 * x + 0.65 * x * x + offset
        sequences.append({"moca_seqid": seqid, "name": seqid, "x": x.round(4).tolist(), "y": y.round(4).tolist(), "yerror": [None] * len(x)})
    return {
        "selection": selection,
        "rows": rows,
        "sequences": sequences,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "row_count": len(rows),
            "sequence_count": len(sequences),
            "sequence_ids": _gaia_cmd_sequence_ids(selection),
            "truncated": False,
            "max_objects": selection["max_objects"],
            "query_seconds": 0,
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _parse_xyzuvw_csv_ids(raw: Any, default: tuple[str, ...] = ()) -> list[str]:
    values: list[str] = []
    for item in str(raw or "").replace(";", ",").split(","):
        value = item.strip()
        if value and SAFE_ID_RE.match(value) and value not in values:
            values.append(value)
    return values or list(default)


def _parse_xyzuvw_oids(raw: Any) -> list[int]:
    oids: list[int] = []
    for item in str(raw or "").replace(";", ",").split(","):
        value = item.strip()
        if value.isdigit():
            oid = int(value)
            if oid not in oids:
                oids.append(oid)
    return oids[:100]


def _parse_xyzuvw_selection(args: dict[str, Any]) -> dict[str, Any]:
    axes_raw = str(args.get("axes") or "xyz").lower()
    axes = [axis for axis in axes_raw if axis in {"x", "y", "z", "u", "v", "w"}]
    if len(axes) != 3 or len(set(axes)) != 3:
        axes = ["x", "y", "z"]
    aids = _parse_xyzuvw_csv_ids(
        args.get("asso") or args.get("moca_aid") or args.get("aid"),
        XYZUVW_DEFAULT_AIDS,
    )
    mtids = _parse_xyzuvw_csv_ids(args.get("mtid"), XYZUVW_DEFAULT_MTIDS)
    oids = _parse_xyzuvw_oids(args.get("oid") or args.get("moca_oid"))
    has_checkbox_param = args.get("checkbox") is not None
    checkbox_values = {
        item.strip().lower()
        for item in str(args.get("checkbox") or "").replace(";", ",").split(",")
        if item.strip()
    }
    for key in ("models", "errors", "hover", "assmem", "likely", "asscen"):
        if _as_bool(args.get(key)):
            checkbox_values.add(key)
    if not has_checkbox_param and args.get("likely") is None:
        checkbox_values.add("likely")
    bsmdid_raw = str(args.get("bsmdid") or args.get("banyan_version") or "latest").strip()
    bsmdid = bsmdid_raw if bsmdid_raw == "latest" or bsmdid_raw.isdigit() else "latest"
    return {
        "axes": axes,
        "aids": aids,
        "mtids": mtids,
        "oids": oids,
        "bsmdid": bsmdid,
        "likely": "likely" in checkbox_values,
        "labels": "asscen" in checkbox_values,
        "checkboxes": sorted(checkbox_values),
    }


def _sql_in_clause(prefix: str, values: list[str]) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    placeholders = []
    for index, value in enumerate(values):
        key = f"{prefix}_{index}"
        placeholders.append(f":{key}")
        params[key] = value
    return ",".join(placeholders) or "NULL", params


def _xyzuvw_covariance_key(axis1: str, axis2: str) -> str:
    order = ["x", "y", "z", "u", "v", "w"]
    sorted_axes = sorted([axis1, axis2], key=order.index)
    return f"{sorted_axes[0]}{sorted_axes[1]}_covar"


def _xyzuvw_db_cache_key(args: dict[str, Any], selection: dict[str, Any]) -> str:
    cfg = _db_config(args)
    return "|".join([
        cfg["host"],
        cfg["username"],
        cfg["dbname"],
        "".join(selection["axes"]),
        ",".join(selection["aids"]),
        ",".join(selection["mtids"]),
        ",".join(str(oid) for oid in selection["oids"]),
        str(selection["bsmdid"]),
        str(int(selection["likely"])),
        str(int(selection["labels"])),
        str(int("models" in selection["checkboxes"])),
        str(int("errors" in selection["checkboxes"])),
    ])


def _load_xyzuvw_options_from_db(args: dict[str, Any]) -> dict[str, Any]:
    selection = _parse_xyzuvw_selection(args)
    option_aids = list(dict.fromkeys([*selection["aids"], *XYZUVW_DEFAULT_AIDS]))
    cache_key = f"{_spt_db_cache_key(args)}|xyzuvw-options|{','.join(option_aids)}"
    now = time.time()
    cached = _XYZUVW_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    aid_clause, aid_params = _sql_in_clause("option_aid", option_aids)
    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        associations = _records(_read_sql(conn, """
            SELECT ma.moca_aid, ma.name
            FROM moca_associations ma
            WHERE ma.moca_aid IN ({aid_clause})
            ORDER BY ma.moca_aid
        """.format(aid_clause=aid_clause), aid_params))
        mtids = _records(_read_sql(conn, """
            SELECT mt.moca_mtid, mt.name, mt.description
            FROM moca_membership_types mt
            ORDER BY mt.level DESC, mt.moca_mtid
        """))
        versions = _records(_read_sql(conn, """
            SELECT DISTINCT dbs.moca_bsmdid
            FROM data_banyan_sigma_models dbs
            WHERE dbs.moca_bsmdid IS NOT NULL
            ORDER BY dbs.moca_bsmdid DESC
        """))

    payload = {
        "associations": [
            {
                "value": row.get("moca_aid"),
                "label": f"{row.get('moca_aid')} - {row.get('name')}" if row.get("name") else row.get("moca_aid"),
            }
            for row in associations
            if row.get("moca_aid")
        ],
        "mtids": [
            {
                "value": row.get("moca_mtid"),
                "label": f"{row.get('moca_mtid')} - {row.get('name')}" if row.get("name") else row.get("moca_mtid"),
                "description": row.get("description"),
            }
            for row in mtids
            if row.get("moca_mtid")
        ],
        "versions": [{"value": "latest", "label": "Latest available"}] + [
            {"value": str(row["moca_bsmdid"]), "label": str(row["moca_bsmdid"])}
            for row in versions
            if row.get("moca_bsmdid") is not None
        ],
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _XYZUVW_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _search_xyzuvw_associations_from_db(args: dict[str, Any], query: str) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {"options": [], "meta": {"row_count": 0}}
    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        rows = _records(_read_sql(conn, """
            SELECT ma.moca_aid, ma.name
            FROM moca_associations ma
            WHERE ma.moca_aid LIKE :prefix
                OR ma.name LIKE :contains
            ORDER BY
                CASE WHEN ma.moca_aid LIKE :prefix THEN 0 ELSE 1 END,
                ma.moca_aid
            LIMIT 80
        """, {"prefix": f"{query}%", "contains": f"%{query}%"}))
    options = [
        {
            "value": row.get("moca_aid"),
            "label": f"{row.get('moca_aid')} - {row.get('name')}" if row.get("name") else row.get("moca_aid"),
        }
        for row in rows
        if row.get("moca_aid")
    ]
    return {"options": options, "meta": {"row_count": len(options)}}


def _xyzuvw_model_query(selection: dict[str, Any], aid_clause: str) -> str:
    columns = """
        dbs2.moca_aid,
        dbs2.moca_bsmdid,
        dbs2.coeff_index,
        dbs2.coeff_amplitude,
        dbs2.x_cen,
        dbs2.y_cen,
        dbs2.z_cen,
        dbs2.u_cen,
        dbs2.v_cen,
        dbs2.w_cen,
        dbs2.xx_covar,
        dbs2.xy_covar,
        dbs2.xz_covar,
        dbs2.xu_covar,
        dbs2.xv_covar,
        dbs2.xw_covar,
        dbs2.yy_covar,
        dbs2.yz_covar,
        dbs2.yu_covar,
        dbs2.yv_covar,
        dbs2.yw_covar,
        dbs2.zz_covar,
        dbs2.zu_covar,
        dbs2.zv_covar,
        dbs2.zw_covar,
        dbs2.uu_covar,
        dbs2.uv_covar,
        dbs2.uw_covar,
        dbs2.vv_covar,
        dbs2.vw_covar,
        dbs2.ww_covar
    """
    if selection["bsmdid"] == "latest":
        return f"""
            SELECT {columns}
            FROM data_banyan_sigma_models dbs2
            JOIN (
                SELECT MAX(dbs.moca_bsmdid) AS moca_bsmdid, dbs.moca_aid
                FROM data_banyan_sigma_models dbs
                WHERE dbs.moca_aid IN ({aid_clause})
                GROUP BY dbs.moca_aid
            ) inq USING(moca_aid, moca_bsmdid)
            ORDER BY dbs2.moca_aid, dbs2.coeff_index
        """
    return f"""
        SELECT {columns}
        FROM data_banyan_sigma_models dbs2
        WHERE dbs2.moca_aid IN ({aid_clause})
            AND dbs2.moca_bsmdid = :bsmdid
        ORDER BY dbs2.moca_aid, dbs2.coeff_index
    """


def _xyzuvw_scale_value(axis: str, value: Any) -> float | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return numeric * XYZUVW_C_VALUE if axis in {"u", "v", "w"} else numeric


def _xyzuvw_scale_covar(axis1: str, axis2: str, value: Any) -> float | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    kin1 = axis1 in {"u", "v", "w"}
    kin2 = axis2 in {"u", "v", "w"}
    if kin1 and kin2:
        return numeric * XYZUVW_C_VALUE * XYZUVW_C_VALUE
    if kin1 or kin2:
        return numeric * XYZUVW_C_VALUE
    return numeric


def _xyzuvw_model_components(models: list[dict[str, Any]], axes: list[str]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for model in models:
        mean_values = [_xyzuvw_scale_value(axis, model.get(f"{axis}_cen")) for axis in axes]
        if any(value is None for value in mean_values):
            continue
        covariance_values = [
            [
                _xyzuvw_scale_covar(axis1, axis2, model.get(_xyzuvw_covariance_key(axis1, axis2)))
                for axis2 in axes
            ]
            for axis1 in axes
        ]
        if any(value is None for row in covariance_values for value in row):
            continue
        covariance = np.asarray(covariance_values, dtype=float)
        covariance = 0.5 * (covariance + covariance.T)
        try:
            eigenvalues = np.linalg.eigvalsh(covariance)
        except np.linalg.LinAlgError:
            continue
        if not np.all(np.isfinite(eigenvalues)) or np.any(eigenvalues <= 0):
            continue
        weight = _safe_float(model.get("coeff_amplitude"))
        components.append({
            "mean": np.asarray(mean_values, dtype=float),
            "covariance": covariance,
            "weight": float(weight if weight is not None and weight > 0 else 1.0),
        })
    return components


def _xyzuvw_density_threshold(density: np.ndarray, contour: float) -> float | None:
    sorted_density = np.sort(density.ravel())[::-1]
    sorted_density = sorted_density[np.isfinite(sorted_density) & (sorted_density > 0)]
    if sorted_density.size == 0:
        return None
    cumulative = np.cumsum(sorted_density)
    total = cumulative[-1]
    if not np.isfinite(total) or total <= 0:
        return None
    cumulative /= total
    index = int(np.searchsorted(cumulative, contour, side="left"))
    index = min(max(index, 0), sorted_density.size - 1)
    level = float(sorted_density[index])
    min_value = float(np.nanmin(density))
    max_value = float(np.nanmax(density))
    if not math.isfinite(level) or level <= min_value or level >= max_value:
        eps = max((max_value - min_value) * 1e-6, 1e-300)
        level = min(max(level, min_value + eps), max_value - eps)
    return level if math.isfinite(level) and min_value < level < max_value else None


def _xyzuvw_model_surfaces(models: list[dict[str, Any]], axes: list[str]) -> list[dict[str, Any]]:
    try:
        from skimage.measure import marching_cubes
    except Exception:
        return []

    grid_points = max(24, min(120, int(XYZUVW_MODEL_GRID_POINTS)))
    surfaces: list[dict[str, Any]] = []
    models_by_aid: dict[str, list[dict[str, Any]]] = {}
    for model in models:
        aid = str(model.get("moca_aid") or "")
        if aid:
            models_by_aid.setdefault(aid, []).append(model)

    for aid, aid_models in models_by_aid.items():
        components = _xyzuvw_model_components(aid_models, axes)
        if not components:
            continue
        means = np.asarray([component["mean"] for component in components], dtype=float)
        sigmas = np.asarray([
            np.sqrt(np.maximum(np.diag(component["covariance"]), 1e-12))
            for component in components
        ], dtype=float)
        lower = np.min(means - XYZUVW_MODEL_SIGMA_SCALE * sigmas, axis=0)
        upper = np.max(means + XYZUVW_MODEL_SIGMA_SCALE * sigmas, axis=0)
        if not np.all(np.isfinite(lower)) or not np.all(np.isfinite(upper)) or np.any(upper <= lower):
            continue

        axis_vectors = [np.linspace(float(lower[index]), float(upper[index]), grid_points) for index in range(3)]
        grid = np.meshgrid(*axis_vectors, indexing="ij")
        points = np.column_stack([grid[0].ravel(), grid[1].ravel(), grid[2].ravel()])
        density_flat = np.zeros(points.shape[0], dtype=float)
        for component in components:
            try:
                inverse = np.linalg.inv(component["covariance"])
                determinant = float(np.linalg.det(component["covariance"]))
            except np.linalg.LinAlgError:
                continue
            if not math.isfinite(determinant) or determinant <= 0:
                continue
            delta = points - component["mean"]
            q = np.einsum("ij,jk,ik->i", delta, inverse, delta, optimize=True)
            norm = component["weight"] / (((2 * math.pi) ** 1.5) * math.sqrt(determinant))
            density_flat += norm * np.exp(-0.5 * np.clip(q, 0, 200))
        density = density_flat.reshape((grid_points, grid_points, grid_points))
        if not np.isfinite(density).any() or float(np.nanmax(density)) <= 0:
            continue

        for label, contour, opacity in XYZUVW_MODEL_CONTOURS:
            level = _xyzuvw_density_threshold(density, contour)
            if level is None:
                continue
            try:
                verts, faces, _, _ = marching_cubes(density, level=level)
            except Exception:
                continue
            if len(verts) == 0 or len(faces) == 0:
                continue
            verts_real = np.column_stack([
                np.interp(verts[:, 0], (0, grid_points - 1), (axis_vectors[0][0], axis_vectors[0][-1])),
                np.interp(verts[:, 1], (0, grid_points - 1), (axis_vectors[1][0], axis_vectors[1][-1])),
                np.interp(verts[:, 2], (0, grid_points - 1), (axis_vectors[2][0], axis_vectors[2][-1])),
            ])
            surfaces.append({
                "moca_aid": aid,
                "label": label,
                "contour": contour,
                "opacity": opacity,
                "x": np.round(verts_real[:, 0].astype(float), 4).tolist(),
                "y": np.round(verts_real[:, 1].astype(float), 4).tolist(),
                "z": np.round(verts_real[:, 2].astype(float), 4).tolist(),
                "i": faces[:, 0].astype(int).tolist(),
                "j": faces[:, 1].astype(int).tolist(),
                "k": faces[:, 2].astype(int).tolist(),
            })
    return surfaces


def _load_xyzuvw_from_db(args: dict[str, Any]) -> dict[str, Any]:
    selection = _parse_xyzuvw_selection(args)
    cache_key = _xyzuvw_db_cache_key(args, selection)
    now = time.time()
    cached = _XYZUVW_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    aid_clause, aid_params = _sql_in_clause("aid", selection["aids"])
    mtid_clause, mtid_params = _sql_in_clause("mtid", selection["mtids"])
    params: dict[str, Any] = {**aid_params, **mtid_params}
    if selection["bsmdid"] != "latest":
        params["bsmdid"] = int(selection["bsmdid"])

    include_covariances = "errors" in selection["checkboxes"]
    covariance_columns = ""
    covariance_joins = ""
    if include_covariances:
        spatial_covariances = {"xx_covar", "yy_covar", "zz_covar", "xy_covar", "xz_covar", "yz_covar"}
        requested_covariances = []
        for axis_index, axis1 in enumerate(selection["axes"]):
            for axis2 in selection["axes"][axis_index:]:
                key = _xyzuvw_covariance_key(axis1, axis2)
                if key not in requested_covariances:
                    requested_covariances.append(key)
        xyz_covariances = [key for key in requested_covariances if key in spatial_covariances]
        uvw_covariances = [key for key in requested_covariances if key not in spatial_covariances]
        covariance_columns = "\n".join(
            [f"                xyz.{key}," for key in xyz_covariances]
            + [f"                uvw.{key}," for key in uvw_covariances]
        )
        if covariance_columns:
            covariance_columns += "\n"
        join_parts = []
        if xyz_covariances:
            join_parts.append("""
            LEFT JOIN calc_xyz xyz
                ON xyz.moca_oid = sam.moca_oid
                {xyz_public_filter}
            """)
        if uvw_covariances:
            join_parts.append("""
            LEFT JOIN calc_uvw uvw
                ON uvw.moca_oid = sam.moca_oid
                AND uvw.moca_aid = sam.moca_aid
                {uvw_public_filter}
            """)
        covariance_joins = "".join(join_parts).format(
            xyz_public_filter="AND xyz.is_public = 0" if _is_private_db(args) else "",
            uvw_public_filter="AND uvw.is_public = 0" if _is_private_db(args) else "",
        )

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        active_model_rows = _records(_read_sql(conn, """
            SELECT mbsm.moca_bsmdid
            FROM moca_banyan_sigma_models mbsm
            WHERE mbsm.adopted = 1
            ORDER BY mbsm.moca_bsmdid DESC
            LIMIT 1
        """))
        params["active_bsmdid"] = (
            int(selection["bsmdid"])
            if selection["bsmdid"] != "latest"
            else active_model_rows[0].get("moca_bsmdid") if active_model_rows else None
        )
        cbs_public_filter = "AND cbs.is_public = 0" if _is_private_db(args) else ""
        if selection["likely"]:
            members_df = _read_sql(conn, f"""
                SELECT
                    sam.designation,
                    cbs.moca_aid,
                    sam.moca_mtid,
                    sam.spectral_type AS spt,
                    sam.dr3_ruwe,
                    cbs.moca_oid,
                    sam.x_pc AS x,
                    sam.y_pc AS y,
                    sam.z_pc AS z,
                    {covariance_columns}
                    {XYZUVW_C_VALUE} * sam.u_kms AS u,
                    {XYZUVW_C_VALUE} * sam.v_kms AS v,
                    {XYZUVW_C_VALUE} * sam.w_kms AS w,
                    cbsd.x_opt,
                    cbsd.y_opt,
                    cbsd.z_opt,
                    {XYZUVW_C_VALUE} * cbsd.u_opt AS u_opt,
                    {XYZUVW_C_VALUE} * cbsd.v_opt AS v_opt,
                    {XYZUVW_C_VALUE} * cbsd.w_opt AS w_opt,
                    cbs.ya_prob,
                    cbs.uvw_sep,
                    cbs.xyz_sep,
                    cbs.observables
                FROM calc_banyan_sigma cbs
                JOIN summary_all_members sam
                    ON sam.moca_oid = cbs.moca_oid
                    AND sam.moca_aid = cbs.moca_aid
                    AND sam.moca_mtid IN ({mtid_clause})
                {covariance_joins}
                LEFT JOIN calc_banyan_sigma_details cbsd
                    ON cbs.id = cbsd.cbs_id
                    AND cbsd.moca_aid = cbs.moca_aid
                WHERE cbs.moca_aid IN ({aid_clause})
                    AND cbs.moca_bsmdid = :active_bsmdid
                    AND cbs.max_observables = 1
                    {cbs_public_filter}
                    AND cbs.ya_prob >= 90
                ORDER BY cbs.moca_aid, sam.moca_mtid, cbs.moca_oid
                LIMIT {XYZUVW_MAX_OBJECTS}
            """, params)
        else:
            members_df = _read_sql(conn, f"""
                SELECT
                    sam.designation,
                    sam.moca_aid,
                    sam.moca_mtid,
                    sam.spectral_type AS spt,
                    sam.dr3_ruwe,
                    sam.moca_oid,
                    sam.x_pc AS x,
                    sam.y_pc AS y,
                    sam.z_pc AS z,
                    {covariance_columns}
                    {XYZUVW_C_VALUE} * sam.u_kms AS u,
                    {XYZUVW_C_VALUE} * sam.v_kms AS v,
                    {XYZUVW_C_VALUE} * sam.w_kms AS w,
                    cbsd.x_opt,
                    cbsd.y_opt,
                    cbsd.z_opt,
                    {XYZUVW_C_VALUE} * cbsd.u_opt AS u_opt,
                    {XYZUVW_C_VALUE} * cbsd.v_opt AS v_opt,
                    {XYZUVW_C_VALUE} * cbsd.w_opt AS w_opt,
                    COALESCE(sam.banyan_prob, cbs.ya_prob) AS ya_prob,
                    cbs.uvw_sep,
                    cbs.xyz_sep,
                    cbs.observables
                FROM summary_all_members sam
                {covariance_joins}
                LEFT JOIN calc_banyan_sigma cbs
                    ON cbs.moca_oid = sam.moca_oid
                    AND cbs.moca_aid = sam.moca_aid
                    AND cbs.moca_bsmdid = :active_bsmdid
                    AND cbs.max_observables = 1
                    {cbs_public_filter}
                LEFT JOIN calc_banyan_sigma_details cbsd
                    ON cbs.id = cbsd.cbs_id
                    AND cbsd.moca_aid = sam.moca_aid
                WHERE sam.moca_aid IN ({aid_clause})
                    AND sam.moca_mtid IN ({mtid_clause})
                ORDER BY sam.moca_aid, sam.moca_mtid, sam.moca_oid
                LIMIT {XYZUVW_MAX_OBJECTS}
            """, params)
        models_df = _read_sql(conn, _xyzuvw_model_query(selection, aid_clause), params)

        objects_df = pd.DataFrame()
        if selection["oids"]:
            oid_clause = ",".join(str(int(oid)) for oid in selection["oids"])
            objects_df = _read_sql(conn, f"""
                SELECT
                    mo.designation,
                    COALESCE(mv.moca_aid, 'N/A') AS moca_aid,
                    'N/A' AS moca_mtid,
                    cspt.spectral_type AS spt,
                    dr3.RUWE AS dr3_ruwe,
                    mo.moca_oid,
                    xyz.x_pc AS x,
                    xyz.y_pc AS y,
                    xyz.z_pc AS z,
                    {XYZUVW_C_VALUE} * uvw.u_kms AS u,
                    {XYZUVW_C_VALUE} * uvw.v_kms AS v,
                    {XYZUVW_C_VALUE} * uvw.w_kms AS w,
                    mo.ra,
                    mo.`dec`,
                    dpm.pmra_masyr,
                    dpm.pmdec_masyr,
                    cdist.distance_pc,
                    crvc.radial_velocity_kms
                FROM moca_objects mo
                LEFT JOIN calc_banyan_sigma_best mv
                    ON mv.moca_oid = mo.moca_oid
                LEFT JOIN calc_xyz xyz
                    ON xyz.moca_oid = mo.moca_oid
                LEFT JOIN calc_uvw_raw uvw
                    ON uvw.moca_oid = mo.moca_oid
                LEFT JOIN calc_radial_velocities_corrected crvc
                    ON crvc.moca_oid = mo.moca_oid
                    AND crvc.moca_aid = mv.moca_aid
                LEFT JOIN cat_gaiadr3 dr3
                    ON dr3.moca_oid = mo.moca_oid
                LEFT JOIN data_spectral_types cspt
                    ON cspt.moca_oid = mo.moca_oid
                    AND cspt.adopted = 1
                LEFT JOIN data_distances cdist
                    ON cdist.moca_oid = mo.moca_oid
                    AND cdist.adopted = 1
                LEFT JOIN data_proper_motions dpm
                    ON dpm.moca_oid = mo.moca_oid
                    AND dpm.adopted = 1
                WHERE mo.moca_oid IN ({oid_clause})
                ORDER BY FIELD(mo.moca_oid, {oid_clause})
            """)

    members = _records(members_df)
    models = _records(models_df)
    model_surfaces = _xyzuvw_model_surfaces(models, selection["axes"]) if "models" in selection["checkboxes"] else []
    labels = []
    if selection["labels"] and members:
        by_aid: dict[str, list[dict[str, Any]]] = {}
        for row in members:
            by_aid.setdefault(str(row.get("moca_aid")), []).append(row)
        for aid, rows in by_aid.items():
            label_row: dict[str, Any] = {"moca_aid": aid}
            for axis in ("x", "y", "z", "u", "v", "w"):
                finite_values = [
                    float(row[axis])
                    for row in rows
                    if row.get(axis) is not None and math.isfinite(float(row[axis]))
                ]
                label_row[axis] = float(np.nanmedian(finite_values)) if finite_values else None
            labels.append(label_row)

    payload = {
        "selection": selection,
        "members": members,
        "models": models,
        "modelSurfaces": model_surfaces,
        "objects": _records(objects_df),
        "labels": labels,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "member_count": len(members),
            "model_count": len(models),
            "model_surface_count": len(model_surfaces),
            "object_count": int(len(objects_df)),
            "truncated": int(len(members_df)) >= XYZUVW_MAX_OBJECTS,
            "max_objects": XYZUVW_MAX_OBJECTS,
            "c_value": XYZUVW_C_VALUE,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _XYZUVW_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _search_xyzuvw_objects_from_db(args: dict[str, Any], query: str) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {"options": [], "meta": {"row_count": 0}}
    search_int = int(query) if query.isdigit() else None
    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        rows = _records(_read_sql(conn, """
            SELECT mo.moca_oid, mo.designation
            FROM moca_objects mo
            WHERE (:search_int IS NOT NULL AND mo.moca_oid = :search_int)
                OR mo.designation LIKE :prefix
                OR EXISTS (
                    SELECT 1
                    FROM mechanics_all_designations mad
                    WHERE mad.moca_oid = mo.moca_oid
                        AND mad.designation LIKE :prefix
                )
            ORDER BY
                CASE WHEN :search_int IS NOT NULL AND mo.moca_oid = :search_int THEN 0 ELSE 1 END,
                mo.designation,
                mo.moca_oid
            LIMIT 40
        """, {"search_int": search_int, "prefix": f"{query}%"}))
    options = [
        {
            "value": int(row["moca_oid"]),
            "moca_oid": int(row["moca_oid"]),
            "designation": row.get("designation"),
            "label": f"oid{int(row['moca_oid'])}: {row.get('designation') or 'MOCAdb object'}",
        }
        for row in rows
        if row.get("moca_oid") is not None
    ]
    return {"options": options, "meta": {"row_count": len(options)}}


def _search_gaia_cmd_objects_from_db(args: dict[str, Any], query: str) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {"options": [], "meta": {"row_count": 0}}
    search_int = int(query) if query.isdigit() else None
    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        rows = _records(_read_sql(conn, """
            SELECT
                matches.moca_oid,
                matches.canonical_designation,
                matches.matched_designation,
                matches.match_rank
            FROM (
                SELECT
                    mo.moca_oid,
                    mo.designation AS canonical_designation,
                    mo.designation AS matched_designation,
                    0 AS match_rank
                FROM moca_objects mo
                WHERE :search_int IS NOT NULL
                    AND mo.moca_oid = :search_int
                UNION ALL
                SELECT
                    mo.moca_oid,
                    mo.designation AS canonical_designation,
                    mo.designation AS matched_designation,
                    1 AS match_rank
                FROM moca_objects mo
                WHERE mo.designation LIKE :prefix
                UNION ALL
                SELECT
                    mad.moca_oid,
                    mo.designation AS canonical_designation,
                    mad.designation AS matched_designation,
                    2 AS match_rank
                FROM mechanics_all_designations mad
                LEFT JOIN moca_objects mo
                    ON mo.moca_oid = mad.moca_oid
                WHERE mad.designation IS NOT NULL
                    AND mad.designation <> ''
                    AND mad.designation LIKE :prefix
            ) matches
            WHERE matches.moca_oid IS NOT NULL
            ORDER BY matches.match_rank, matches.matched_designation, matches.moca_oid
            LIMIT 120
        """, {"search_int": search_int, "prefix": f"{query}%"}))
    options: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        if row.get("moca_oid") is None:
            continue
        oid = int(row["moca_oid"])
        if oid in seen:
            continue
        seen.add(oid)
        matched = row.get("matched_designation") or row.get("canonical_designation") or f"oid{oid}"
        options.append({
            "value": oid,
            "moca_oid": oid,
            "designation": matched,
            "canonical_designation": row.get("canonical_designation"),
            "label": matched,
        })
        if len(options) >= 80:
            break
    return {"options": options, "meta": {"row_count": len(options)}}


def _mock_xyzuvw_options() -> dict[str, Any]:
    aids = ["HYA", "CBER", "TWA", "THA", "BPMG", "ABDMG"]
    return {
        "associations": [{"value": aid, "label": f"{aid} - Mock association"} for aid in aids],
        "mtids": [{"value": mtid, "label": f"{mtid} - Mock membership"} for mtid in ["BF", "HM", "CM", "LM"]],
        "versions": [{"value": "latest", "label": "Latest available"}, {"value": "16", "label": "16"}],
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "private_db": False},
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _mock_xyzuvw_payload(args: dict[str, Any]) -> dict[str, Any]:
    selection = _parse_xyzuvw_selection(args)
    rng = np.random.default_rng(42)
    members = []
    models = []
    labels = []
    for aid_index, aid in enumerate(selection["aids"]):
        center = np.asarray([
            -30 + 45 * aid_index,
            20 - 25 * aid_index,
            -10 + 12 * aid_index,
            XYZUVW_C_VALUE * (-10 + 3 * aid_index),
            XYZUVW_C_VALUE * (-18 + 2 * aid_index),
            XYZUVW_C_VALUE * (-6 + aid_index),
        ], dtype=float)
        spread = np.asarray([18, 12, 10, 4 * XYZUVW_C_VALUE, 3 * XYZUVW_C_VALUE, 2.5 * XYZUVW_C_VALUE], dtype=float)
        label = {"moca_aid": aid, "x": center[0], "y": center[1], "z": center[2], "u": center[3], "v": center[4], "w": center[5]}
        labels.append(label)
        models.append({
            "moca_aid": aid,
            "moca_bsmdid": 16,
            "coeff_index": 0,
            "coeff_amplitude": 1.0,
            "x_cen": center[0],
            "y_cen": center[1],
            "z_cen": center[2],
            "u_cen": center[3] / XYZUVW_C_VALUE,
            "v_cen": center[4] / XYZUVW_C_VALUE,
            "w_cen": center[5] / XYZUVW_C_VALUE,
            "xx_covar": spread[0] ** 2,
            "yy_covar": spread[1] ** 2,
            "zz_covar": spread[2] ** 2,
            "uu_covar": (spread[3] / XYZUVW_C_VALUE) ** 2,
            "vv_covar": (spread[4] / XYZUVW_C_VALUE) ** 2,
            "ww_covar": (spread[5] / XYZUVW_C_VALUE) ** 2,
            "xy_covar": 0,
            "xz_covar": 0,
            "yz_covar": 0,
            "uv_covar": 0,
            "uw_covar": 0,
            "vw_covar": 0,
            "xu_covar": 0,
            "xv_covar": 0,
            "xw_covar": 0,
            "yu_covar": 0,
            "yv_covar": 0,
            "yw_covar": 0,
            "zu_covar": 0,
            "zv_covar": 0,
            "zw_covar": 0,
        })
        for index in range(52):
            coords = center + rng.normal(0, spread, size=6)
            oid = 900000 + aid_index * 1000 + index
            mtid = selection["mtids"][index % max(1, len(selection["mtids"]))]
            members.append({
                "designation": f"Mock {aid} member {index:02d}",
                "moca_aid": aid,
                "moca_mtid": mtid,
                "spt": ["M5", "L1", "T2"][index % 3],
                "dr3_ruwe": round(float(rng.uniform(0.9, 1.6)), 2),
                "moca_oid": oid,
                "x": coords[0],
                "y": coords[1],
                "z": coords[2],
                "u": coords[3],
                "v": coords[4],
                "w": coords[5],
                "x_opt": 0.7 * coords[0] + 0.3 * center[0],
                "y_opt": 0.7 * coords[1] + 0.3 * center[1],
                "z_opt": 0.7 * coords[2] + 0.3 * center[2],
                "u_opt": 0.7 * coords[3] + 0.3 * center[3],
                "v_opt": 0.7 * coords[4] + 0.3 * center[4],
                "w_opt": 0.7 * coords[5] + 0.3 * center[5],
                "xx_covar": 9,
                "yy_covar": 9,
                "zz_covar": 9,
                "uu_covar": 4,
                "vv_covar": 4,
                "ww_covar": 4,
                "ya_prob": round(float(rng.uniform(45, 99)), 1),
                "observables": "XYZUVW",
            })
    objects = []
    for oid in selection["oids"]:
        objects.append({
            "designation": f"Highlighted mock oid{oid}",
            "moca_aid": "N/A",
            "moca_mtid": "N/A",
            "spt": "L/T",
            "dr3_ruwe": 1.1,
            "moca_oid": int(oid),
            "x": 5,
            "y": -10,
            "z": 18,
            "u": None,
            "v": None,
            "w": None,
            "ra": 24.0,
            "dec": 9.5,
            "pmra_masyr": 1200,
            "pmdec_masyr": -450,
            "distance_pc": 6.2,
            "radial_velocity_kms": None,
        })
    if selection["likely"]:
        members = [row for row in members if float(row.get("ya_prob") or 0) >= 80]
    return {
        "selection": selection,
        "members": members,
        "models": models,
        "objects": objects,
        "labels": labels if selection["labels"] else [],
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "member_count": len(members),
            "model_count": len(models),
            "object_count": len(objects),
            "truncated": False,
            "max_objects": XYZUVW_MAX_OBJECTS,
            "c_value": XYZUVW_C_VALUE,
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


class _TfAgeCurve:
    __slots__ = ("key", "label", "source", "age_myr", "pdf_age", "metadata")

    def __init__(
        self,
        key: str,
        label: str,
        source: str,
        age_myr: np.ndarray,
        pdf_age: np.ndarray,
        metadata: dict[str, Any],
    ) -> None:
        self.key = key
        self.label = label
        self.source = source
        self.age_myr = age_myr
        self.pdf_age = pdf_age
        self.metadata = metadata


def _tfage_scope(args: dict[str, Any]) -> str:
    raw = str(args.get("target") or args.get("scope") or args.get("mode") or "").strip().lower()
    if raw in {"association", "associations", "assoc", "aid"}:
        return "association"
    if raw in {"object", "objects", "oid"}:
        return "object"
    if args.get("moca_aid") or args.get("aid"):
        return "association"
    return "object"


def _tfage_target(args: dict[str, Any], scope: str) -> int | str | None:
    if scope == "association":
        aid = str(args.get("moca_aid") or args.get("aid") or "").strip().upper()
        return aid or None
    raw_oid = args.get("moca_oid") or args.get("oid") or args.get("target_oid") or TRUEFLOW_AGE_DEFAULT_OID
    try:
        return int(raw_oid)
    except (TypeError, ValueError):
        return None


def _tfage_load_posteriors(args: dict[str, Any]) -> bool:
    checkbox = {part.strip().lower() for part in str(args.get("checkbox") or "").split(",") if part.strip()}
    return _as_bool(args.get("posteriors")) or _as_bool(args.get("posterior")) or "posteriors" in checkbox


def _tfage_db_config(args: dict[str, Any], scope: str) -> dict[str, str]:
    if scope == "object":
        return {
            "host": (
                args.get("host")
                or os.environ.get("ATM_HOST")
                or os.environ.get("MOCA_HOST")
                or DEFAULT_HOST
            ),
            "username": (
                args.get("user")
                or args.get("username")
                or os.environ.get("ATM_USERNAME")
                or os.environ.get("ATM_USER")
                or os.environ.get("MOCA_USERNAME")
                or DEFAULT_USERNAME
            ),
            "password": (
                args.get("pwd")
                or args.get("password")
                or os.environ.get("ATM_PASSWORD")
                or os.environ.get("MOCA_PASSWORD")
                or DEFAULT_PASSWORD
            ),
            "dbname": (
                args.get("dbase")
                or args.get("db")
                or args.get("database")
                or os.environ.get("MOCA_DBNAME")
                or "mocadb_private_tables"
            ),
            "port": args.get("port") or os.environ.get("ATM_PORT") or os.environ.get("MOCA_PORT") or "3306",
        }
    return {
        "host": args.get("host") or os.environ.get("MOCA_HOST") or DEFAULT_HOST,
        "username": args.get("user") or args.get("username") or os.environ.get("MOCA_USERNAME") or DEFAULT_USERNAME,
        "password": args.get("pwd") or args.get("password") or os.environ.get("MOCA_PASSWORD") or DEFAULT_PASSWORD,
        "dbname": (
            args.get("dbase")
            or args.get("db")
            or args.get("database")
            or os.environ.get("MOCA_DBNAME")
            or DEFAULT_DBNAME
        ),
        "port": args.get("port") or os.environ.get("MOCA_PORT") or "3306",
    }


def _tfage_connection_string(args: dict[str, Any], scope: str) -> str:
    cfg = _tfage_db_config(args, scope)
    password = quote_plus(cfg["password"])
    return f"mysql+pymysql://{cfg['username']}:{password}@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"


def _tfage_cache_key(args: dict[str, Any], scope: str, target: int | str | None) -> str:
    cfg = _tfage_db_config(args, scope)
    return "|".join([
        cfg["host"],
        cfg["username"],
        cfg["dbname"],
        cfg["port"],
        TRUEFLOW_AGE_CACHE_SCHEMA,
        scope,
        str(target or ""),
        str(int(_tfage_load_posteriors(args))),
    ])


def _tfage_table_exists(engine, table_name: str) -> bool:
    query = text("""
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
            AND table_name = :table_name
    """)
    with engine.connect() as conn:
        return int(conn.execute(query, {"table_name": table_name}).scalar() or 0) > 0


def _tfage_columns(engine, table_name: str) -> set[str]:
    query = text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
            AND table_name = :table_name
    """)
    with engine.connect() as conn:
        return {str(row[0]) for row in conn.execute(query, {"table_name": table_name})}


def _tfage_qid(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return f"`{name}`"


def _tfage_fetch_age_rows(engine, scope: str, target: int | str) -> pd.DataFrame:
    age_table = "data_object_ages" if scope == "object" else "data_association_ages"
    target_col = "moca_oid" if scope == "object" else "moca_aid"
    if not _tfage_table_exists(engine, age_table):
        return pd.DataFrame()
    cols = _tfage_columns(engine, age_table)
    order_terms = []
    for col in ("adopted", "public_adopted", "adopt_asis", "public_adopt_asis"):
        if col in cols:
            order_terms.append(f"{_tfage_qid(col)} DESC")
    for col in ("modified_timestamp", "created_timestamp", "id"):
        if col in cols:
            order_terms.append(f"{_tfage_qid(col)} DESC")
    order_sql = ", ".join(order_terms) if order_terms else "1"
    query = text(f"""
        SELECT *
        FROM {_tfage_qid(age_table)}
        WHERE {_tfage_qid(target_col)} = :target
        ORDER BY {order_sql}
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {"target": target}).mappings().all()
    return pd.DataFrame(rows)


def _tfage_dtype(dtype: str | None, byte_order: str | None) -> np.dtype:
    dtype = dtype or "float32"
    byte_order = byte_order or "little"
    if dtype not in {"float32", "float64"}:
        dtype = "float32"
    prefix = "<" if byte_order != "big" else ">"
    return np.dtype(prefix + ("f4" if dtype == "float32" else "f8"))


def _tfage_decode_array(
    blob: bytes | memoryview,
    *,
    n_values: int,
    dtype: str | None,
    byte_order: str | None,
    compression: str | None,
    expected_sha256: str | None = None,
) -> np.ndarray:
    raw_blob = bytes(blob)
    raw = raw_blob if compression == "none" else zlib.decompress(raw_blob)
    if expected_sha256:
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected_sha256:
            raise ValueError("Blob SHA256 check failed")
    values = np.frombuffer(raw, dtype=_tfage_dtype(dtype, byte_order), count=int(n_values))
    return values.astype(float, copy=True)


def _tfage_normalize_pdf(age_myr: np.ndarray, pdf: np.ndarray) -> np.ndarray:
    age_myr = np.asarray(age_myr, dtype=float)
    pdf = np.asarray(pdf, dtype=float)
    ok = np.isfinite(age_myr) & np.isfinite(pdf) & (age_myr > 0)
    out = np.zeros_like(pdf, dtype=float)
    if np.count_nonzero(ok) < 2:
        return out
    clipped = np.clip(pdf[ok], 0.0, None)
    norm = float(np.trapz(clipped, age_myr[ok]))
    if not math.isfinite(norm) or norm <= 0:
        return out
    out[ok] = clipped / norm
    return out


def _tfage_cdf_from_pdf(age_myr: np.ndarray, pdf: np.ndarray) -> np.ndarray:
    age_myr = np.asarray(age_myr, dtype=float)
    pdf = _tfage_normalize_pdf(age_myr, pdf)
    cdf = np.zeros_like(pdf, dtype=float)
    if age_myr.size < 2:
        return cdf
    order = np.argsort(age_myr)
    age_sorted = age_myr[order]
    pdf_sorted = pdf[order]
    increments = 0.5 * (pdf_sorted[1:] + pdf_sorted[:-1]) * np.diff(age_sorted)
    cdf_sorted = np.concatenate([[0.0], np.cumsum(increments)])
    if cdf_sorted[-1] > 0:
        cdf_sorted = cdf_sorted / cdf_sorted[-1]
    cdf[order] = np.clip(cdf_sorted, 0.0, 1.0)
    return cdf


def _tfage_percentiles(age_myr: np.ndarray, pdf: np.ndarray) -> tuple[float, float, float] | None:
    age_myr = np.asarray(age_myr, dtype=float)
    pdf = _tfage_normalize_pdf(age_myr, pdf)
    ok = np.isfinite(age_myr) & np.isfinite(pdf) & (age_myr > 0)
    if np.count_nonzero(ok) < 2:
        return None
    age = age_myr[ok]
    cdf = _tfage_cdf_from_pdf(age, pdf[ok])
    if not np.any(np.diff(cdf) > 0):
        return None
    return tuple(float(np.interp(p, cdf, age)) for p in (0.16, 0.5, 0.84))


def _tfage_log10_age_log_pdf_to_age_pdf(
    log10_age_grid: np.ndarray,
    log_pdf: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    log10_age_grid = np.asarray(log10_age_grid, dtype=float)
    log_pdf = np.asarray(log_pdf, dtype=float)
    ok = np.isfinite(log10_age_grid) & np.isfinite(log_pdf)
    if np.count_nonzero(ok) < 2:
        return np.array([], dtype=float), np.array([], dtype=float)
    log10_age_grid = log10_age_grid[ok]
    log_pdf = log_pdf[ok]
    order = np.argsort(log10_age_grid)
    log10_age_grid = log10_age_grid[order]
    log_pdf = log_pdf[order]
    log_age_pdf = np.exp(log_pdf - float(np.nanmax(log_pdf)))
    log_norm = float(np.trapz(log_age_pdf, log10_age_grid))
    if not math.isfinite(log_norm) or log_norm <= 0:
        return np.array([], dtype=float), np.array([], dtype=float)
    log_age_pdf /= log_norm
    age_myr = np.power(10.0, log10_age_grid)
    age_pdf = log_age_pdf / (age_myr * np.log(10.0))
    return age_myr, _tfage_normalize_pdf(age_myr, age_pdf)


def _tfage_blob_curve_sort_key(curve: _TfAgeCurve) -> tuple[Any, ...]:
    meta = curve.metadata or {}
    return (
        meta.get("age_id"),
        meta.get("result_key"),
        meta.get("pdf_space"),
        meta.get("used_colors"),
    )


def _tfage_deduplicate_blob_curves(curves: list[_TfAgeCurve], *, prefer_posteriors: bool) -> list[_TfAgeCurve]:
    by_key: dict[tuple[Any, ...], _TfAgeCurve] = {}
    for curve in curves:
        key = _tfage_blob_curve_sort_key(curve)
        current = by_key.get(key)
        if current is None:
            by_key[key] = curve
            continue
        role = (curve.metadata or {}).get("curve_role")
        current_role = (current.metadata or {}).get("curve_role")
        if prefer_posteriors and role == "posterior" and current_role != "posterior":
            by_key[key] = curve
        elif not prefer_posteriors and role == "likelihood" and current_role != "likelihood":
            by_key[key] = curve
    return list(by_key.values())


def _tfage_curve_from_log_pdf_row(data: dict[str, Any], age_meta: dict[Any, dict[str, Any]]) -> _TfAgeCurve | None:
    try:
        grid = _tfage_decode_array(
            data["grid_blob"],
            n_values=int(data["grid_n_grid"]),
            dtype=data.get("grid_dtype"),
            byte_order=data.get("grid_byte_order"),
            compression=data.get("grid_compression"),
            expected_sha256=data.get("grid_sha256"),
        )
        if data.get("grid_coordinate") in (None, "", "log10_age_myr"):
            log10_age = grid
        elif data.get("grid_coordinate") in {"age_myr", "age"}:
            log10_age = np.log10(grid)
        else:
            log10_age = grid
        log_pdf = _tfage_decode_array(
            data["log_pdf_blob"],
            n_values=int(data["grid_n_grid"]),
            dtype=data.get("dtype"),
            byte_order=data.get("byte_order"),
            compression=data.get("compression"),
            expected_sha256=data.get("log_pdf_sha256"),
        )
        age, pdf = _tfage_log10_age_log_pdf_to_age_pdf(log10_age, log_pdf)
    except Exception as exc:
        return _TfAgeCurve(
            key=f"blob-decode-error-{data.get('id')}",
            label=f"Blob decode error id={data.get('id')}",
            source="MOCAFlows error",
            age_myr=np.array([], dtype=float),
            pdf_age=np.array([], dtype=float),
            metadata={"error": str(exc), "age_id": data.get("age_id")},
        )
    if age.size < 2 or not np.any(pdf > 0):
        return None

    meta = age_meta.get(data["age_id"], {})
    row_method = meta.get("calculation_method") or meta.get("method") or meta.get("method_detailed") or ""
    result_key = data.get("result_key") or row_method or "age_pdf"
    role = data.get("curve_role") or "posterior"
    extras = []
    if data.get("used_colors"):
        extras.append(str(data["used_colors"]))
    if data.get("n_contributors") is not None:
        extras.append(f"N={data['n_contributors']}")
    if data.get("prior_id") is not None:
        extras.append(f"prior={data['prior_id']}")
    label = f"{result_key} {role} (age_id={data['age_id']})"
    if row_method and row_method != result_key:
        label = f"{label}; {row_method}"
    if extras:
        label = f"{label}; {', '.join(extras)}"
    return _TfAgeCurve(
        key=f"blob-{data.get('id')}-{data.get('age_id')}-{data.get('result_key')}",
        label=label,
        source="MOCAFlows",
        age_myr=age,
        pdf_age=pdf,
        metadata={**data, "scalar_row": meta},
    )


def _tfage_fetch_blob_curves(
    engine,
    scope: str,
    age_rows: pd.DataFrame,
    *,
    load_posteriors: bool = False,
) -> list[_TfAgeCurve]:
    if age_rows.empty or "id" not in age_rows:
        return []
    blob_table = "calc_object_age_pdf_blobs" if scope == "object" else "calc_association_age_pdf_blobs"
    if not (_tfage_table_exists(engine, blob_table) and _tfage_table_exists(engine, "calc_age_pdf_grids")):
        return []

    age_ids = [int(v) for v in age_rows["id"].dropna().astype(int).unique()]
    if not age_ids:
        return []

    blob_cols = _tfage_columns(engine, blob_table)
    required = {"id", "age_id", "grid_id", "result_key", "curve_role", "pdf_space", "log_pdf_blob"}
    if not required.issubset(blob_cols):
        return []

    wanted_blob_cols = [
        "id",
        "age_id",
        "grid_id",
        "result_key",
        "curve_role",
        "pdf_space",
        "dtype",
        "byte_order",
        "compression",
        "compression_level",
        "log_pdf_sha256",
        "log_pdf_blob",
        "peak_age_myr",
        "age_lo_myr",
        "age_hi_myr",
        "n_contributors",
        "used_colors",
        "metadata_json",
        "eps_peak",
        "eps_mean",
        "eps_lo",
        "eps_hi",
        "prior_id",
    ]
    select_blob = ",\n               ".join(
        f"b.{_tfage_qid(col)} AS {_tfage_qid(col)}" for col in wanted_blob_cols if col in blob_cols
    )
    role_values = ("posterior", "likelihood") if load_posteriors else ("likelihood",)
    query = text(f"""
        SELECT {select_blob},
               g.id AS grid_row_id,
               g.coordinate AS grid_coordinate,
               g.n_grid AS grid_n_grid,
               g.dtype AS grid_dtype,
               g.byte_order AS grid_byte_order,
               g.compression AS grid_compression,
               g.grid_sha256 AS grid_sha256,
               g.grid_blob AS grid_blob
        FROM {_tfage_qid(blob_table)} AS b
        JOIN calc_age_pdf_grids AS g
            ON g.id = b.grid_id
        WHERE b.age_id IN :age_ids
            AND b.curve_role IN :role_values
        ORDER BY b.age_id, b.result_key, b.curve_role, b.id
    """).bindparams(bindparam("age_ids", expanding=True), bindparam("role_values", expanding=True))
    with engine.connect() as conn:
        rows = conn.execute(query, {"age_ids": age_ids, "role_values": role_values}).mappings().all()

    age_meta = age_rows.set_index("id", drop=False).to_dict(orient="index")
    curves = []
    for row in rows:
        curve = _tfage_curve_from_log_pdf_row(dict(row), age_meta)
        if curve is not None:
            curves.append(curve)
    return _tfage_deduplicate_blob_curves(curves, prefer_posteriors=load_posteriors)


def _tfage_fetch_legacy_pdf_curves(engine, scope: str, age_rows: pd.DataFrame) -> list[_TfAgeCurve]:
    if age_rows.empty or "id" not in age_rows:
        return []
    pdf_table = "calc_object_age_pdfs" if scope == "object" else "calc_association_age_pdfs"
    if not _tfage_table_exists(engine, pdf_table):
        return []
    cols = _tfage_columns(engine, pdf_table)
    if not {"age_id", "age_myr", "log_probability_density"}.issubset(cols):
        return []
    age_ids = [int(v) for v in age_rows["id"].dropna().astype(int).unique()]
    if not age_ids:
        return []
    query = text(f"""
        SELECT age_id, age_myr, log_probability_density
        FROM {_tfage_qid(pdf_table)}
        WHERE age_id IN :age_ids
        ORDER BY age_id, age_myr
    """).bindparams(bindparam("age_ids", expanding=True))
    with engine.connect() as conn:
        rows = conn.execute(query, {"age_ids": age_ids}).mappings().all()
    pdf_rows = pd.DataFrame(rows)
    if pdf_rows.empty:
        return []
    age_meta = age_rows.set_index("id", drop=False).to_dict(orient="index")
    curves = []
    for age_id, sub in pdf_rows.groupby("age_id", sort=False):
        sub = sub.dropna(subset=["age_myr", "log_probability_density"]).copy()
        sub = sub[sub["age_myr"] > 0]
        if sub.shape[0] < 2:
            continue
        sub.sort_values("age_myr", inplace=True)
        age = sub["age_myr"].to_numpy(dtype=float)
        log_pdf = sub["log_probability_density"].to_numpy(dtype=float)
        pdf = np.exp(log_pdf - float(np.nanmax(log_pdf)))
        pdf = _tfage_normalize_pdf(age, pdf)
        if not np.any(pdf > 0):
            continue
        meta = age_meta.get(age_id, {})
        method = meta.get("calculation_method") or meta.get("method") or meta.get("method_detailed") or "legacy age PDF"
        curves.append(_TfAgeCurve(
            key=f"legacy-{age_id}",
            label=f"{method} legacy PDF (age_id={age_id})",
            source="Legacy",
            age_myr=age,
            pdf_age=pdf,
            metadata={"age_id": age_id, "scalar_row": meta},
        ))
    return curves


def _tfage_first_number(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        if name in row:
            value = _safe_float(row.get(name))
            if value is not None:
                return value
    return None


def _tfage_scalar_age_summary(row: dict[str, Any]) -> tuple[float, float, float, str] | None:
    center = _tfage_first_number(row, ("age_myr", "age", "age_value_myr", "best_age_myr"))
    note = "stored uncertainty"
    if center is None:
        log_age_yr = _tfage_first_number(row, ("log_age_yr", "log10_age_yr"))
        if log_age_yr is not None:
            center = 10.0**log_age_yr / 1e6
    if center is None or center <= 0:
        return None

    lo_unc = _tfage_first_number(row, ("age_myr_unc_neg", "age_myr_err_neg", "age_myr_minus", "age_unc_neg", "age_err_neg"))
    hi_unc = _tfage_first_number(row, ("age_myr_unc_pos", "age_myr_err_pos", "age_myr_plus", "age_unc_pos", "age_err_pos"))
    sym_unc = _tfage_first_number(row, ("age_myr_unc", "age_unc", "age_err", "uncertainty_myr"))
    if lo_unc is None and hi_unc is None and sym_unc is not None:
        lo_unc = sym_unc
        hi_unc = sym_unc

    log_center = math.log10(center * 1e6)
    log_lo = _tfage_first_number(row, ("log_age_unc_neg", "log_age_yr_unc_neg", "log10_age_yr_unc_neg"))
    log_hi = _tfage_first_number(row, ("log_age_unc_pos", "log_age_yr_unc_pos", "log10_age_yr_unc_pos"))
    log_sym = _tfage_first_number(row, ("log_age_unc", "log_age_yr_unc", "log10_age_yr_unc"))
    if log_lo is None and log_hi is None and log_sym is not None:
        log_lo = log_sym
        log_hi = log_sym
    if lo_unc is None and log_lo is not None:
        lo_unc = center - (10.0 ** (log_center - abs(log_lo)) / 1e6)
    if hi_unc is None and log_hi is not None:
        hi_unc = (10.0 ** (log_center + abs(log_hi)) / 1e6) - center

    if lo_unc is None or lo_unc <= 0:
        lo_unc = 0.10 * center
        note = "fallback 10% uncertainty"
    if hi_unc is None or hi_unc <= 0:
        hi_unc = 0.10 * center
        note = "fallback 10% uncertainty"
    return float(center), float(abs(lo_unc)), float(abs(hi_unc)), note


def _tfage_gaussian_grid(age_rows: pd.DataFrame, stored_curves: list[_TfAgeCurve]) -> np.ndarray:
    candidates: list[float] = []
    for curve in stored_curves:
        if curve.age_myr.size:
            good = curve.age_myr[np.isfinite(curve.age_myr) & (curve.age_myr > 0)]
            if good.size:
                candidates.extend([float(np.nanmin(good)), float(np.nanmax(good))])
    for row in age_rows.to_dict(orient="records"):
        summary = _tfage_scalar_age_summary(row)
        if not summary:
            continue
        center, lo_unc, hi_unc, _ = summary
        candidates.extend([max(center - 6.0 * lo_unc, 0.02), center + 6.0 * hi_unc])
    if not candidates:
        return np.geomspace(0.5, 20000.0, 1200)
    amin = max(0.02, min(candidates))
    amax = max(amin * 10.0, max(candidates))
    amin = max(0.02, amin / 1.5)
    amax = min(50000.0, amax * 1.5)
    return np.geomspace(amin, amax, 1400)


def _tfage_stored_pdf_age_ids(stored_curves: list[_TfAgeCurve]) -> set[int]:
    age_ids: set[int] = set()
    for curve in stored_curves:
        meta = curve.metadata or {}
        age_id = meta.get("age_id")
        if age_id is None:
            scalar = meta.get("scalar_row") or {}
            age_id = scalar.get("id")
        try:
            if age_id is not None:
                age_ids.add(int(age_id))
        except (TypeError, ValueError):
            continue
    return age_ids


def _tfage_all_stored_pdf_age_ids(engine, scope: str, age_rows: pd.DataFrame) -> set[int]:
    if age_rows.empty or "id" not in age_rows:
        return set()
    age_ids = [int(v) for v in age_rows["id"].dropna().astype(int).unique()]
    if not age_ids:
        return set()
    out: set[int] = set()
    for table_name in (
        "calc_object_age_pdf_blobs" if scope == "object" else "calc_association_age_pdf_blobs",
        "calc_object_age_pdfs" if scope == "object" else "calc_association_age_pdfs",
    ):
        if not _tfage_table_exists(engine, table_name):
            continue
        cols = _tfage_columns(engine, table_name)
        if "age_id" not in cols:
            continue
        query = text(f"""
            SELECT DISTINCT age_id
            FROM {_tfage_qid(table_name)}
            WHERE age_id IN :age_ids
        """).bindparams(bindparam("age_ids", expanding=True))
        with engine.connect() as conn:
            out.update(int(row[0]) for row in conn.execute(query, {"age_ids": age_ids}))
    return out


def _tfage_scalar_gaussian_curves(
    age_rows: pd.DataFrame,
    stored_curves: list[_TfAgeCurve],
    skip_age_ids: set[int] | None = None,
) -> list[_TfAgeCurve]:
    if age_rows.empty:
        return []
    skip_age_ids = skip_age_ids or set()
    grid = _tfage_gaussian_grid(age_rows, stored_curves)
    curves = []
    for row in age_rows.to_dict(orient="records"):
        age_id_raw = row.get("id")
        try:
            age_id_int = int(age_id_raw) if age_id_raw is not None else None
        except (TypeError, ValueError):
            age_id_int = None
        if age_id_int is not None and age_id_int in skip_age_ids:
            continue
        summary = _tfage_scalar_age_summary(row)
        if not summary:
            continue
        center, lo_unc, hi_unc, note = summary
        sigma = np.where(grid < center, lo_unc, hi_unc)
        pdf = np.exp(-0.5 * ((grid - center) / sigma) ** 2)
        pdf = _tfage_normalize_pdf(grid, pdf)
        if not np.any(pdf > 0):
            continue
        method = row.get("calculation_method") or row.get("method") or row.get("method_detailed") or "scalar age"
        age_id = row.get("id", "unknown")
        curves.append(_TfAgeCurve(
            key=f"gaussian-{age_id}",
            label=f"{method} asymmetric Gaussian (age_id={age_id})",
            source="Scalar Gaussian",
            age_myr=grid,
            pdf_age=pdf,
            metadata={
                "age_id": age_id,
                "age_myr": center,
                "age_myr_unc_neg": lo_unc,
                "age_myr_unc_pos": hi_unc,
                "uncertainty_note": note,
                "scalar_row": row,
            },
        ))
    return curves


def _tfage_is_hbm_mocaflows_curve(curve: _TfAgeCurve) -> bool:
    meta = curve.metadata or {}
    scalar = meta.get("scalar_row") or {}
    values = [
        meta.get("result_key"),
        meta.get("metadata_json"),
        scalar.get("calculation_method"),
        scalar.get("method"),
        scalar.get("method_detailed"),
        scalar.get("comments"),
        scalar.get("origin"),
    ]
    text_blob = " ".join(str(value).lower() for value in values if value not in (None, ""))
    calc_method = str(scalar.get("calculation_method") or "").lower()
    return (
        calc_method.startswith("mfhbm")
        or "hbm" in text_blob
        or "hierarchical bayesian" in text_blob
        or "hierarchical_bayesian" in text_blob
        or "outlier rejection" in text_blob
    )


def _tfage_load_curves(
    engine,
    scope: str,
    target: int | str,
    *,
    load_blob_posteriors: bool = False,
) -> tuple[pd.DataFrame, list[_TfAgeCurve]]:
    age_rows = _tfage_fetch_age_rows(engine, scope, target)
    blob_curves = _tfage_fetch_blob_curves(engine, scope, age_rows, load_posteriors=load_blob_posteriors)
    legacy_curves = _tfage_fetch_legacy_pdf_curves(engine, scope, age_rows)
    stored_curves = blob_curves + legacy_curves
    skip_age_ids = _tfage_all_stored_pdf_age_ids(engine, scope, age_rows)
    skip_age_ids.update(_tfage_stored_pdf_age_ids(stored_curves))
    scalar_curves = _tfage_scalar_gaussian_curves(age_rows, stored_curves, skip_age_ids=skip_age_ids)
    return age_rows, blob_curves + legacy_curves + scalar_curves


def _tfage_curve_summary_row(curve: _TfAgeCurve) -> dict[str, Any]:
    pct = _tfage_percentiles(curve.age_myr, curve.pdf_age)
    meta = curve.metadata or {}
    scalar = meta.get("scalar_row") or {}
    if pct:
        age16, age50, age84 = pct
        age_text = f"{age50:.3g} (+{age84 - age50:.3g}/-{age50 - age16:.3g}) Myr"
    else:
        age_text = ""
    return {
        "curve": curve.label,
        "source": curve.source,
        "age": age_text,
        "calculation_method": scalar.get("calculation_method", ""),
        "moca_pid": scalar.get("moca_pid", ""),
        "adopted": scalar.get("adopted", ""),
        "public_adopted": scalar.get("public_adopted", ""),
        "comments": scalar.get("comments", ""),
    }


def _tfage_curve_payload(curve: _TfAgeCurve) -> dict[str, Any]:
    meta = curve.metadata or {}
    scalar = meta.get("scalar_row") or {}
    age = np.asarray(curve.age_myr, dtype=float)
    pdf = _tfage_normalize_pdf(age, np.asarray(curve.pdf_age, dtype=float))
    ok = np.isfinite(age) & np.isfinite(pdf) & (age > 0)
    age = age[ok]
    pdf = pdf[ok]
    return {
        "key": curve.key,
        "label": curve.label,
        "source": curve.source,
        "age_myr": [float(value) for value in age],
        "pdf_age": [float(value) for value in pdf],
        "is_hbm_mocaflows": bool(_tfage_is_hbm_mocaflows_curve(curve)),
        "summary": _tfage_curve_summary_row(curve),
        "metadata": {
            "age_id": _pythonize(meta.get("age_id") if meta.get("age_id") is not None else scalar.get("id")),
            "result_key": _pythonize(meta.get("result_key")),
            "curve_role": _pythonize(meta.get("curve_role")),
            "used_colors": _pythonize(meta.get("used_colors")),
            "n_contributors": _pythonize(meta.get("n_contributors")),
            "moca_pid": _pythonize(scalar.get("moca_pid")),
            "calculation_method": _pythonize(scalar.get("calculation_method")),
        },
    }


def _tfage_object_info_from_engine(engine, target: int) -> dict[str, Any]:
    info: dict[str, Any] = {"moca_oid": int(target)}
    has_objects = _tfage_table_exists(engine, "moca_objects")
    has_designations = _tfage_table_exists(engine, "mechanics_all_designations")
    if not has_objects and not has_designations:
        return info
    with engine.connect() as conn:
        if has_objects and has_designations:
            rows = _records(_read_sql(conn, """
                SELECT
                    mo.moca_oid,
                    COALESCE(NULLIF(mo.designation, ''), mad.designation) AS designation
                FROM moca_objects mo
                LEFT JOIN (
                    SELECT moca_oid, MIN(designation) AS designation
                    FROM mechanics_all_designations
                    WHERE designation IS NOT NULL
                        AND designation <> ''
                    GROUP BY moca_oid
                ) mad
                    ON mad.moca_oid = mo.moca_oid
                WHERE mo.moca_oid = :target
                LIMIT 1
            """, {"target": int(target)}))
        elif has_objects:
            rows = _records(_read_sql(conn, """
                SELECT mo.moca_oid, mo.designation
                FROM moca_objects mo
                WHERE mo.moca_oid = :target
                LIMIT 1
            """, {"target": int(target)}))
        else:
            rows = _records(_read_sql(conn, """
                SELECT
                    mad.moca_oid,
                    MIN(mad.designation) AS designation
                FROM mechanics_all_designations mad
                WHERE mad.moca_oid = :target
                    AND mad.designation IS NOT NULL
                    AND mad.designation <> ''
                GROUP BY mad.moca_oid
                LIMIT 1
            """, {"target": int(target)}))
    if rows:
        info.update(rows[0])
        info["moca_oid"] = int(info.get("moca_oid") or target)
    return info


def _tfage_metadata_object_info(args: dict[str, Any], target: int) -> dict[str, Any]:
    metadata_args = dict(args)
    for key in ("dbase", "db", "database"):
        metadata_args.pop(key, None)
    try:
        metadata_engine = _engine(_connection_string(metadata_args))
        return _tfage_object_info_from_engine(metadata_engine, int(target))
    except Exception:
        return {"moca_oid": int(target)}


def _tfage_resolve_object_info(engine, args: dict[str, Any], target: int) -> dict[str, Any]:
    info = _tfage_object_info_from_engine(engine, int(target))
    if not str(info.get("designation") or "").strip():
        metadata_info = _tfage_metadata_object_info(args, int(target))
        if str(metadata_info.get("designation") or "").strip():
            info.update(metadata_info)
    return info


def _tfage_object_option(row: dict[str, Any]) -> dict[str, Any]:
    oid = int(row["moca_oid"])
    designation = row.get("designation")
    return {
        "value": oid,
        "moca_oid": oid,
        "designation": designation,
        "label": f"oid{oid}: {designation or 'MOCAdb object'}",
    }


def _tfage_target_info(engine, scope: str, target: int | str | None, args: dict[str, Any] | None = None) -> dict[str, Any]:
    if target in (None, ""):
        return {}
    if scope == "object":
        if args is not None:
            return _tfage_resolve_object_info(engine, args, int(target))
        return _tfage_object_info_from_engine(engine, int(target))
    with engine.connect() as conn:
        if _tfage_table_exists(engine, "moca_associations"):
            rows = _records(_read_sql(conn, """
                SELECT ma.moca_aid, ma.name
                FROM moca_associations ma
                WHERE ma.moca_aid = :target
                LIMIT 1
            """, {"target": str(target)}))
            return rows[0] if rows else {"moca_aid": str(target)}
    return {"moca_aid": str(target)}


def _load_tfage_options_from_db(args: dict[str, Any]) -> dict[str, Any]:
    scope = "association"
    cache_key = f"{_tfage_cache_key(args, scope, 'options')}|options"
    now = time.time()
    cached = _TRUEFLOW_AGE_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_tfage_connection_string(args, scope))
    associations: list[dict[str, Any]] = []
    if _tfage_table_exists(engine, "data_association_ages"):
        with engine.connect() as conn:
            if _tfage_table_exists(engine, "moca_associations"):
                rows = _records(_read_sql(conn, """
                    SELECT DISTINCT daa.moca_aid, ma.name
                    FROM data_association_ages daa
                    LEFT JOIN moca_associations ma
                        ON ma.moca_aid = daa.moca_aid
                    WHERE daa.moca_aid IS NOT NULL
                    ORDER BY daa.moca_aid
                """))
            else:
                rows = _records(_read_sql(conn, """
                    SELECT DISTINCT daa.moca_aid, NULL AS name
                    FROM data_association_ages daa
                    WHERE daa.moca_aid IS NOT NULL
                    ORDER BY daa.moca_aid
                """))
        associations = [
            {
                "value": row.get("moca_aid"),
                "label": f"{row.get('moca_aid')} - {row.get('name')}" if row.get("name") else row.get("moca_aid"),
            }
            for row in rows
            if row.get("moca_aid")
        ]
    payload = {
        "associations": associations,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "association_count": len(associations),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _TRUEFLOW_AGE_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _search_tfage_objects_from_db(args: dict[str, Any], query: str, selected_oid: int | None = None) -> dict[str, Any]:
    scope = "object"
    engine = _engine(_tfage_connection_string(args, scope))
    has_objects = _tfage_table_exists(engine, "moca_objects")
    has_designations = _tfage_table_exists(engine, "mechanics_all_designations")
    if selected_oid is not None:
        info = _tfage_resolve_object_info(engine, args, int(selected_oid))
        return {
            "options": [_tfage_object_option(info)],
            "value": int(selected_oid),
            "meta": {"row_count": 1},
        }
    with engine.connect() as conn:
        query = (query or "").strip()
        if not query:
            query = str(TRUEFLOW_AGE_DEFAULT_OID)
        if query.isdigit():
            rows = [_tfage_resolve_object_info(engine, args, int(query))]
        elif has_objects and has_designations:
            params = {"prefix": f"{query}%"}
            rows = _records(_read_sql(conn, """
                SELECT mo.moca_oid, mo.designation
                FROM moca_objects mo
                WHERE mo.designation LIKE :prefix
                    OR EXISTS (
                        SELECT 1
                        FROM mechanics_all_designations mad
                        WHERE mad.moca_oid = mo.moca_oid
                            AND mad.designation LIKE :prefix
                    )
                ORDER BY mo.designation, mo.moca_oid
                LIMIT 40
            """, params))
        elif has_objects:
            rows = _records(_read_sql(conn, """
                SELECT mo.moca_oid, mo.designation
                FROM moca_objects mo
                WHERE mo.designation LIKE :prefix
                ORDER BY mo.designation, mo.moca_oid
                LIMIT 40
            """, {"prefix": f"{query}%"}))
        elif has_designations:
            rows = _records(_read_sql(conn, """
                SELECT mad.moca_oid, mad.designation
                FROM mechanics_all_designations mad
                WHERE mad.designation LIKE :prefix
                ORDER BY mad.designation, mad.moca_oid
                LIMIT 40
            """, {"prefix": f"{query}%"}))
        else:
            rows = []
    options = [_tfage_object_option(row) for row in rows if row.get("moca_oid") is not None]
    return {"options": options, "value": selected_oid if selected_oid and options else None, "meta": {"row_count": len(options)}}


def _load_tfage_payload_from_db(args: dict[str, Any]) -> dict[str, Any]:
    scope = _tfage_scope(args)
    target = _tfage_target(args, scope)
    load_posteriors = _tfage_load_posteriors(args)
    cache_key = _tfage_cache_key(args, scope, target)
    now = time.time()
    cached = _TRUEFLOW_AGE_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload
    if target in (None, ""):
        return {
            "selection": {"scope": scope, "target": None, "load_posteriors": load_posteriors},
            "target": {},
            "curves": [],
            "tableRows": [],
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "age_row_count": 0,
                "curve_count": 0,
                "displayable_curve_count": 0,
                "load_posteriors": load_posteriors,
            },
            "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
        }

    started = time.time()
    engine = _engine(_tfage_connection_string(args, scope))
    age_rows, curves = _tfage_load_curves(engine, scope, target, load_blob_posteriors=load_posteriors)
    displayable = [
        curve for curve in curves
        if curve.source != "MOCAFlows error" and curve.age_myr.size > 1 and np.any(curve.pdf_age > 0)
    ]
    curve_payloads = [_tfage_curve_payload(curve) for curve in displayable]
    target_info = _tfage_target_info(engine, scope, target, args)
    payload = {
        "selection": {
            "scope": scope,
            "target": target,
            "moca_oid": int(target) if scope == "object" else None,
            "moca_aid": str(target) if scope == "association" else None,
            "load_posteriors": load_posteriors,
        },
        "target": target_info,
        "curves": curve_payloads,
        "tableRows": [row["summary"] for row in curve_payloads],
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "age_row_count": int(len(age_rows)),
            "curve_count": int(len(curves)),
            "displayable_curve_count": int(len(curve_payloads)),
            "load_posteriors": load_posteriors,
            "source_counts": {
                source: sum(1 for curve in curve_payloads if curve["source"] == source)
                for source in sorted({curve["source"] for curve in curve_payloads})
            },
            "timings": {"load_total": round(time.time() - started, 3)},
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _TRUEFLOW_AGE_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _mock_tfage_options() -> dict[str, Any]:
    associations = [
        {"value": "ABDMG", "label": "ABDMG - AB Doradus moving group"},
        {"value": "BPMG", "label": "BPMG - beta Pictoris moving group"},
        {"value": "TWA", "label": "TWA - TW Hydrae association"},
        {"value": "THA", "label": "THA - Tucana-Horologium association"},
    ]
    return {
        "associations": associations,
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "association_count": len(associations)},
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _mock_tfage_payload(args: dict[str, Any]) -> dict[str, Any]:
    scope = _tfage_scope(args)
    target = _tfage_target(args, scope)
    age = np.geomspace(1.0, 5000.0, 900)
    specs = [
        ("mocaflows-young-likelihood", "MOCAFlows color likelihood (age_id=101)", "MOCAFlows", 35.0, 0.22, False),
        ("mocaflows-hbm-likelihood", "mfhbm posterior-like likelihood (age_id=102); HBM", "MOCAFlows", 55.0, 0.28, True),
        ("legacy-lithium", "lithium boundary legacy PDF (age_id=88)", "Legacy", 130.0, 0.32, False),
        ("gaussian-kinematic", "kinematic age asymmetric Gaussian (age_id=77)", "Scalar Gaussian", 45.0, 0.18, False),
    ]
    curves = []
    for key, label, source, center, sigma, is_hbm in specs:
        log_age = np.log(age)
        pdf = np.exp(-0.5 * ((log_age - math.log(center)) / sigma) ** 2)
        pdf = _tfage_normalize_pdf(age, pdf)
        fake_curve = _TfAgeCurve(
            key=key,
            label=label,
            source=source,
            age_myr=age,
            pdf_age=pdf,
            metadata={
                "age_id": key.rsplit("-", 1)[-1],
                "curve_role": "likelihood",
                "result_key": key,
                "scalar_row": {
                    "calculation_method": "mfhbm mock" if is_hbm else f"{source} mock",
                    "moca_pid": "mock",
                    "adopted": 1,
                    "public_adopted": 1,
                    "comments": "Synthetic smoke-test curve",
                },
            },
        )
        payload = _tfage_curve_payload(fake_curve)
        payload["is_hbm_mocaflows"] = is_hbm
        curves.append(payload)
    if scope == "association":
        target_info = {"moca_aid": target or "TWA", "name": "Mock association"}
    else:
        target_info = {"moca_oid": int(target or TRUEFLOW_AGE_DEFAULT_OID), "designation": "Mock age-PDF target"}
    return {
        "selection": {
            "scope": scope,
            "target": target,
            "moca_oid": int(target) if scope == "object" and target is not None else None,
            "moca_aid": str(target) if scope == "association" and target is not None else None,
            "load_posteriors": _tfage_load_posteriors(args),
        },
        "target": target_info,
        "curves": curves,
        "tableRows": [curve["summary"] for curve in curves],
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "age_row_count": 4,
            "curve_count": len(curves),
            "displayable_curve_count": len(curves),
            "load_posteriors": _tfage_load_posteriors(args),
            "source_counts": {"MOCAFlows": 2, "Legacy": 1, "Scalar Gaussian": 1},
            "timings": {"load_total": 0.02},
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _astrometry_db_cache_key(args: dict[str, Any], oid: int) -> str:
    cfg = _db_config(args)
    return "|".join([
        cfg["host"],
        cfg["username"],
        cfg["dbname"],
        str(int(oid)),
        str(_include_merged_astrometry(args)),
    ])


def _include_merged_astrometry(args: dict[str, Any]) -> bool:
    return any(_as_bool(args.get(key)) for key in ("display_merged", "include_merged", "merged"))


def _format_astrometry_reference(row: dict[str, Any] | None, prefix: str) -> str:
    if not row:
        return f"No adopted {prefix}"
    source = row.get("publication_name") or row.get("moca_pid") or row.get("origin") or f"No adopted {prefix}"
    mission = " ".join(
        str(part).strip()
        for part in (row.get("mission_name"), row.get("data_release"))
        if part is not None and str(part).strip()
    )
    return f"{source}, {mission}" if mission else str(source)


def _search_astrometry_objects_from_db(args: dict[str, Any], query: str, selected_oid: int | None) -> dict[str, Any]:
    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        if selected_oid is not None:
            rows = _records(_read_sql(conn, """
                SELECT mo.moca_oid, mo.designation
                FROM moca_objects mo
                WHERE mo.moca_oid = :oid
                LIMIT 1
            """, {"oid": selected_oid}))
            options = [
                {
                    "value": row["moca_oid"],
                    "moca_oid": row["moca_oid"],
                    "designation": row.get("designation"),
                    "label": f"oid{row['moca_oid']}: {row.get('designation') or 'MOCAdb object'}",
                }
                for row in rows
            ]
            return {"options": options, "value": selected_oid if options else None, "meta": {"row_count": len(options)}}

        query = (query or "").strip()
        if not query:
            query = "602"
        if query.isdigit():
            rows = _records(_read_sql(conn, """
                SELECT mo.moca_oid, mo.designation
                FROM moca_objects mo
                WHERE mo.moca_oid = :oid
                LIMIT 1
            """, {"oid": int(query)}))
        else:
            params = {"prefix": f"{query}%"}
            object_rows = _records(_read_sql(conn, """
                SELECT mo.moca_oid, mo.designation
                FROM moca_objects mo
                WHERE mo.designation LIKE :prefix
                ORDER BY mo.designation, mo.moca_oid
                LIMIT 15
            """, params))
            if object_rows:
                rows = object_rows
            else:
                rows = _records(_read_sql(conn, """
                    SELECT mad.moca_oid, mad.designation
                    FROM mechanics_all_designations mad
                    WHERE mad.designation LIKE :prefix
                    ORDER BY mad.designation, mad.moca_oid
                    LIMIT 30
                """, params))
    options = [
        {
            "value": row["moca_oid"],
            "moca_oid": row["moca_oid"],
            "designation": row.get("designation"),
            "label": f"oid{row['moca_oid']}: {row.get('designation') or 'MOCAdb object'}",
        }
        for row in rows
    ]
    return {"options": options, "value": options[0]["value"] if options else None, "meta": {"row_count": len(options)}}


def _load_astrometry_object_from_db(args: dict[str, Any], oid: int) -> dict[str, Any]:
    cache_key = _astrometry_db_cache_key(args, oid)
    include_merged = _include_merged_astrometry(args)
    single_epoch_filter = "1 = 1" if include_merged else "deq.single_epoch = 1"
    now = time.time()
    cached = _ASTROMETRY_OBJECT_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        target_rows = _records(_read_sql(conn, """
            SELECT mo.moca_oid, mo.designation
            FROM moca_objects mo
            WHERE mo.moca_oid = :oid
            LIMIT 1
        """, {"oid": oid}))
        designation_rows = _records(_read_sql(conn, """
            SELECT mad.designation
            FROM mechanics_all_designations mad
            WHERE mad.moca_oid = :oid
            ORDER BY mad.designation
            LIMIT 80
        """, {"oid": oid}))
        reference_rows = _records(_read_sql(conn, """
            SELECT
                deq.id,
                deq.ra,
                deq.`dec`,
                deq.ra - IFNULL(
                    deq.calibration_delta_ra_mas / (3600 * 1000 * COS(deq.`dec` * PI() / 180)),
                    0
                ) AS raw_ra,
                deq.`dec` - IFNULL(deq.calibration_delta_dec_mas / (3600 * 1000), 0) AS raw_dec,
                deq.measurement_epoch_yr,
                deq.adopt_as_reference,
                deq.bibcode,
                deq.moca_pid,
                deq.mission_name,
                deq.data_release,
                deq.origin,
                deq.comments,
                deq.pm_corrected,
                deq.plx_corrected
            FROM data_equatorial_coordinates deq
            WHERE deq.moca_oid = :oid
                AND deq.ignored = 0
                AND deq.adopt_as_reference = 1
            ORDER BY deq.measurement_epoch_yr DESC, deq.id DESC
            LIMIT 1
        """, {"oid": oid}))
        pm_rows = _records(_read_sql(conn, """
            SELECT
                dpm.pmra_masyr,
                dpm.pmdec_masyr,
                dpm.pmra_masyr_unc,
                dpm.pmdec_masyr_unc,
                dpm.moca_pid,
                dpm.origin,
                dpm.mission_name,
                dpm.data_release,
                mp.name AS publication_name
            FROM data_proper_motions dpm
            LEFT JOIN moca_publications mp ON mp.moca_pid = dpm.moca_pid
            WHERE dpm.moca_oid = :oid
                AND dpm.adopted = 1
            LIMIT 1
        """, {"oid": oid}))
        plx_rows = _records(_read_sql(conn, """
            SELECT
                dplx.parallax_mas,
                dplx.parallax_mas_unc,
                dplx.moca_pid,
                dplx.origin,
                dplx.mission_name,
                dplx.data_release,
                mp.name AS publication_name
            FROM data_parallaxes dplx
            LEFT JOIN moca_publications mp ON mp.moca_pid = dplx.moca_pid
            WHERE dplx.moca_oid = :oid
                AND dplx.adopted = 1
            LIMIT 1
        """, {"oid": oid}))
        rows_df = _read_sql(conn, """
            SELECT
                deq.id,
                deq.ra,
                deq.`dec`,
                deq.ra - IFNULL(
                    deq.calibration_delta_ra_mas / (3600 * 1000 * COS(deq.`dec` * PI() / 180)),
                    0
                ) AS raw_ra,
                deq.`dec` - IFNULL(deq.calibration_delta_dec_mas / (3600 * 1000), 0) AS raw_dec,
                deq.measurement_epoch_yr,
                deq.single_epoch,
                deq.ra_unc_mas,
                deq.dec_unc_mas,
                COALESCE(deq.measurement_epoch_yr_unc, 0) AS measurement_epoch_yr_unc,
                CASE
                    WHEN deq.mission_name IS NULL OR TRIM(deq.mission_name) = ''
                        THEN COALESCE(CAST(deq.moca_pid AS CHAR), 'No mission')
                    WHEN TRIM(COALESCE(deq.data_release, '')) = ''
                        THEN TRIM(deq.mission_name)
                    ELSE TRIM(CONCAT(deq.mission_name, ' ', deq.data_release))
                END AS mission,
                deq.moca_pid,
                deq.mission_name,
                deq.data_release,
                deq.origin,
                deq.comments,
                deq.airmass,
                deq.moca_psid,
                deq.calibration_delta_ra_mas,
                deq.calibration_delta_dec_mas,
                deq.nstars_calibration,
                deq.calibration_method,
                COALESCE(mm.include_in_recalibrated_display, 0) AS include_in_recalibrated_display
            FROM data_equatorial_coordinates deq
            LEFT JOIN moca_missions mm
                ON mm.mission_name = deq.mission_name
                AND mm.data_release = deq.data_release
            WHERE deq.moca_oid = :oid
                AND deq.ignored = 0
                AND {single_epoch_filter}
            ORDER BY deq.measurement_epoch_yr, deq.id
            LIMIT 20000
        """.format(single_epoch_filter=single_epoch_filter), {"oid": oid})

    rows = _records(rows_df)
    reference = reference_rows[0] if reference_rows else None
    if reference is None and rows:
        finite_rows = [
            row for row in rows
            if row.get("ra") is not None and row.get("dec") is not None and row.get("measurement_epoch_yr") is not None
        ]
        if finite_rows:
            median_index = len(finite_rows) // 2
            reference = {
                "id": finite_rows[median_index].get("id"),
                "ra": finite_rows[median_index].get("ra"),
                "dec": finite_rows[median_index].get("dec"),
                "measurement_epoch_yr": finite_rows[median_index].get("measurement_epoch_yr"),
                "fallback": True,
            }

    target = target_rows[0] if target_rows else {"moca_oid": int(oid), "designation": None}
    pm = pm_rows[0] if pm_rows else {}
    pm["reference"] = _format_astrometry_reference(pm_rows[0] if pm_rows else None, "PM")
    plx = plx_rows[0] if plx_rows else {}
    plx["reference"] = _format_astrometry_reference(plx_rows[0] if plx_rows else None, "parallax")
    mission_counts: dict[str, int] = {}
    for row in rows:
        mission = str(row.get("mission") or "No mission")
        mission_counts[mission] = mission_counts.get(mission, 0) + 1
    missions = [
        {"value": mission, "label": f"{mission} ({count})", "count": count}
        for mission, count in sorted(mission_counts.items(), key=lambda item: item[0].lower())
    ]
    payload = {
        "target": {
            "moca_oid": int(oid),
            "designation": target.get("designation"),
            "designations": [row.get("designation") for row in designation_rows if row.get("designation")],
        },
        "reference": reference or {},
        "pm": pm,
        "parallax": plx,
        "missions": missions,
        "rows": rows,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "row_count": len(rows),
            "mission_count": len(missions),
            "private_db": _is_private_db(args),
            "include_merged_astrometry": include_merged,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _ASTROMETRY_OBJECT_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _mock_astrometry_search(query: str, selected_oid: int | None = None) -> dict[str, Any]:
    options = [
        {"value": 602, "moca_oid": 602, "designation": "SIMP J013656.5+093347.3", "label": "oid602: SIMP J013656.5+093347.3"},
        {"value": 10995, "moca_oid": 10995, "designation": "Mock high-motion dwarf", "label": "oid10995: Mock high-motion dwarf"},
    ]
    if selected_oid is not None:
        options = [row for row in options if int(row["moca_oid"]) == int(selected_oid)]
    elif query:
        q = str(query).lower()
        options = [row for row in options if q in str(row["label"]).lower()]
    return {"options": options, "value": options[0]["value"] if options else None, "meta": {"row_count": len(options)}}


def _mock_astrometry_object(oid: int, include_merged: bool = False) -> dict[str, Any]:
    rng = np.random.default_rng(int(oid) % 10000)
    base_ra = 24.2354
    base_dec = 9.5631
    epoch_ref = 2016.0
    pmra = 1230.0
    pmdec = -430.0
    plx = 163.0
    missions = [("CFHT WIRCam", "2010"), ("UKIRT WFCAM", "2015"), ("Gaia", "DR3"), ("JWST", "2023")]
    epochs = np.sort(rng.uniform(2008.0, 2025.3, 90))
    rows = []
    for index, epoch in enumerate(epochs):
        mission_name, release = missions[index % len(missions)]
        dra_mas = pmra * (epoch - epoch_ref) + rng.normal(0, 18)
        ddec_mas = pmdec * (epoch - epoch_ref) + rng.normal(0, 14)
        ra = base_ra + dra_mas / (math.cos(math.radians(base_dec)) * 3600 * 1000)
        dec = base_dec + ddec_mas / (3600 * 1000)
        calibrated = index % 5 != 0
        rows.append({
            "id": index + 1,
            "ra": round(ra, 9),
            "dec": round(dec, 9),
            "raw_ra": round(ra - (0.008 if calibrated else 0.0) / (math.cos(math.radians(base_dec)) * 3600 * 1000), 9),
            "raw_dec": round(dec + (0.006 if calibrated else 0.0) / (3600 * 1000), 9),
            "measurement_epoch_yr": round(float(epoch), 6),
            "single_epoch": 1,
            "ra_unc_mas": round(float(rng.uniform(8, 32)), 3),
            "dec_unc_mas": round(float(rng.uniform(8, 32)), 3),
            "measurement_epoch_yr_unc": 0.0,
            "mission": f"{mission_name} {release}",
            "moca_pid": "mock",
            "mission_name": mission_name,
            "data_release": release,
            "origin": "mock_astrometry",
            "comments": "Synthetic astrometry for local smoke testing",
            "airmass": None,
            "moca_psid": None,
            "calibration_delta_ra_mas": 0.008 if calibrated else None,
            "calibration_delta_dec_mas": -0.006 if calibrated else None,
            "nstars_calibration": int(rng.integers(20, 180)) if calibrated else None,
            "calibration_method": "mock recalibration" if calibrated else None,
            "include_in_recalibrated_display": 1 if "Gaia" in mission_name else 0,
        })
    if include_merged:
        for merged_index, epoch in enumerate(np.linspace(2011.5, 2023.5, 10)):
            moca_pid = "mock_merged_pub_a" if merged_index < 5 else "mock_merged_pub_b"
            dra_mas = pmra * (epoch - epoch_ref) + rng.normal(0, 10)
            ddec_mas = pmdec * (epoch - epoch_ref) + rng.normal(0, 10)
            ra = base_ra + dra_mas / (math.cos(math.radians(base_dec)) * 3600 * 1000)
            dec = base_dec + ddec_mas / (3600 * 1000)
            rows.append({
                "id": f"merged-{merged_index + 1}",
                "ra": round(ra, 9),
                "dec": round(dec, 9),
                "raw_ra": round(ra, 9),
                "raw_dec": round(dec, 9),
                "measurement_epoch_yr": round(float(epoch), 6),
                "single_epoch": 0,
                "ra_unc_mas": round(float(rng.uniform(12, 28)), 3),
                "dec_unc_mas": round(float(rng.uniform(12, 28)), 3),
                "measurement_epoch_yr_unc": 0.0,
                "mission": moca_pid,
                "moca_pid": moca_pid,
                "mission_name": None,
                "data_release": None,
                "origin": "mock_merged_astrometry",
                "comments": "Synthetic merged astrometry for local smoke testing",
                "airmass": None,
                "moca_psid": None,
                "calibration_delta_ra_mas": None,
                "calibration_delta_dec_mas": None,
                "nstars_calibration": None,
                "calibration_method": None,
                "include_in_recalibrated_display": 0,
            })
    mission_counts: dict[str, int] = {}
    for row in rows:
        mission_counts[row["mission"]] = mission_counts.get(row["mission"], 0) + 1
    return {
        "target": {
            "moca_oid": int(oid),
            "designation": "SIMP J013656.5+093347.3" if int(oid) == 602 else "Mock high-motion dwarf",
            "designations": ["SIMP J013656.5+093347.3", "2MASS J01365662+0933473"],
        },
        "reference": {
            "id": 1,
            "ra": base_ra,
            "dec": base_dec,
            "measurement_epoch_yr": epoch_ref,
            "adopt_as_reference": 1,
            "bibcode": "2026Mock....1A",
            "moca_pid": "mock",
            "mission_name": "Mock Reference Survey",
            "data_release": "DR1",
            "origin": "mock_astrometry",
            "comments": "Synthetic adopted reference astrometry for local smoke testing",
        },
        "pm": {
            "pmra_masyr": pmra,
            "pmdec_masyr": pmdec,
            "pmra_masyr_unc": 4.0,
            "pmdec_masyr_unc": 5.0,
            "reference": "Mock adopted PM",
        },
        "parallax": {
            "parallax_mas": plx,
            "parallax_mas_unc": 3.0,
            "reference": "Mock adopted parallax",
        },
        "missions": [
            {"value": mission, "label": f"{mission} ({count})", "count": count}
            for mission, count in sorted(mission_counts.items())
        ],
        "rows": rows,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "row_count": len(rows),
            "mission_count": len(mission_counts),
            "private_db": False,
            "include_merged_astrometry": include_merged,
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


@app.get("/")
def index():
    if str(request.script_root or "").rstrip("/").endswith("/js"):
        return send_from_directory(STATIC_DIR, "js_index.html")
    prefix = str(request.script_root or "").rstrip("/")
    target = f"{prefix}/js/"
    query = request.query_string.decode("utf-8")
    return redirect(f"{target}?{query}" if query else target, code=302)


@app.get("/js")
@app.get("/js/")
def js_index_page():
    return send_from_directory(STATIC_DIR, "js_index.html")


@app.get("/bd-colors")
@app.get("/bd_colors")
@app.get("/bd-colors-fast")
@app.get("/bd_colors_fast")
@app.get("/js/bd-colors")
@app.get("/js/bd_colors")
@app.get("/js/bd-colors-fast")
@app.get("/js/bd_colors_fast")
def bd_colors_fast_page():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/gaia-cmd")
@app.get("/gaia_cmd")
@app.get("/stellar-gaia-cmd")
@app.get("/stellar_gaia_cmd")
@app.get("/js/gaia-cmd")
@app.get("/js/gaia_cmd")
@app.get("/js/stellar-gaia-cmd")
@app.get("/js/stellar_gaia_cmd")
def gaia_cmd_fast_page():
    return send_from_directory(STATIC_DIR, "gaia_cmd.html")


@app.get("/spectral-typing")
@app.get("/spectral_typing")
@app.get("/spectral-typing-fast")
@app.get("/spectral_typing_fast")
@app.get("/js/spectral-typing")
@app.get("/js/spectral_typing")
@app.get("/js/spectral-typing-fast")
@app.get("/js/spectral_typing_fast")
def spectral_typing_fast_page():
    return send_from_directory(STATIC_DIR, "spectral_typing.html")


@app.get("/astrometry")
@app.get("/astrometry-fast")
@app.get("/astrometry_fast")
@app.get("/js/astrometry")
@app.get("/js/astrometry-fast")
@app.get("/js/astrometry_fast")
def astrometry_fast_page():
    return send_from_directory(STATIC_DIR, "astrometry.html")


@app.get("/spectra")
@app.get("/spectra-fast")
@app.get("/spectra_fast")
@app.get("/js/spectra")
@app.get("/js/spectra-fast")
@app.get("/js/spectra_fast")
def spectra_fast_page():
    return send_from_directory(STATIC_DIR, "spectra.html")


@app.get("/xyzuvw")
@app.get("/xyzuvw-fast")
@app.get("/xyzuvw_fast")
@app.get("/spatial-kinematics")
@app.get("/spatial-kinematics-fast")
@app.get("/js/xyzuvw")
@app.get("/js/xyzuvw-fast")
@app.get("/js/xyzuvw_fast")
@app.get("/js/spatial-kinematics")
@app.get("/js/spatial-kinematics-fast")
def xyzuvw_fast_page():
    return send_from_directory(STATIC_DIR, "xyzuvw.html")


@app.get("/xyzuvw-three")
@app.get("/xyzuvw_three")
@app.get("/js/xyzuvw-three")
@app.get("/js/xyzuvw_three")
def xyzuvw_three_page():
    return send_from_directory(STATIC_DIR, "xyzuvw_three.html")


@app.get("/xyz2-three")
@app.get("/xyz2_three")
@app.get("/js/xyz2-three")
@app.get("/js/xyz2_three")
def xyz2_three_page():
    return send_from_directory(STATIC_DIR, "xyz2_three.html")


@app.get("/xyz2")
@app.get("/js/xyz2")
def xyz2_fast_page():
    return send_from_directory(STATIC_DIR, "xyz2.html")


def _redirect_with_query(path: str):
    query = request.query_string.decode("utf-8", "ignore")
    return redirect(f"{path}?{query}" if query else path, code=302)


@app.get("/trueflow-age-pdfs")
@app.get("/trueflow_age_pdfs")
@app.get("/trueflow-agepdfs")
def age_pdfs_legacy_redirect():
    return _redirect_with_query("/age-pdfs")


@app.get("/js/trueflow-age-pdfs")
@app.get("/js/trueflow_age_pdfs")
@app.get("/js/trueflow-agepdfs")
def js_age_pdfs_legacy_redirect():
    return _redirect_with_query("/js/age-pdfs")


@app.get("/age-pdfs")
@app.get("/age-pdfs-fast")
@app.get("/js/age-pdfs")
@app.get("/js/age-pdfs-fast")
def trueflow_age_pdfs_fast_page():
    return send_from_directory(STATIC_DIR, "trueflow_age_pdfs.html")


@app.get("/plotly.min.js")
@app.get("/js/plotly.min.js")
def plotly_js():
    global _PLOTLY_JS
    if _PLOTLY_JS is None:
        from plotly.offline import get_plotlyjs

        _PLOTLY_JS = get_plotlyjs()
    return Response(_PLOTLY_JS, mimetype="application/javascript")


@app.get("/js/static/<path:filename>")
def js_static_files(filename: str):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/js/api/<path:api_path>", methods=["GET", "POST"])
def js_api_alias(api_path: str):
    query = request.query_string.decode("utf-8", "ignore")
    target = f"/api/{api_path.lstrip('/')}"
    return redirect(f"{target}?{query}" if query else target, code=307)


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
            mock_specid = int(selected_specid or 450)
            mock_oid = 10995 if mock_specid == 13510 else 990000 + mock_specid
            mock_designation = "2MASS J05591914-1404488" if mock_specid == 13510 else "MOCK comparison"
            mock_spt = "T4.5" if mock_specid == 13510 else "L8.5"
            options = [{
                "moca_specid": mock_specid,
                "moca_oid": mock_oid,
                "designation": mock_designation,
                "spectral_type": mock_spt,
                "label": f"specid{mock_specid},oid{mock_oid}: {mock_designation} ({mock_spt})",
                "value": mock_specid,
            }]
            value = mock_specid if selected_specid is not None else None
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
    cloud_correction = (
        _as_bool(body.get("cloud_correction"))
        or _as_bool(body.get("cloud"))
        or _as_bool(args.get("cloud_correction"))
        or _as_bool(args.get("cloud"))
    )
    if deredden and cloud_correction:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": "Dereddening and brown dwarf cloud correction cannot be used simultaneously.",
        }), 400
    fixed_r_v = _spt_float(body.get("fix_rv") if body.get("fix_rv") is not None else args.get("fix_rv"))
    if fixed_r_v is not None and fixed_r_v <= 0:
        fixed_r_v = None
    raw_cloud_alpha = body.get("cloud_alpha") if body.get("cloud_alpha") is not None else args.get("cloud_alpha")
    cloud_alpha = _spt_float(raw_cloud_alpha)
    cloud_lambda0 = _spt_float(body.get("cloud_lambda0") if body.get("cloud_lambda0") is not None else args.get("cloud_lambda0"))
    cloud_alpha = cloud_alpha if cloud_alpha is not None and cloud_alpha > 0 else SPT_DEFAULT_CLOUD_ALPHA
    cloud_lambda0 = cloud_lambda0 if cloud_lambda0 is not None and cloud_lambda0 > 0 else SPT_DEFAULT_CLOUD_LAMBDA0
    raw_cloud_alpha_fixed = body.get("cloud_alpha_fixed") if body.get("cloud_alpha_fixed") is not None else args.get("cloud_alpha_fixed")
    cloud_alpha_fixed = not _as_false(raw_cloud_alpha_fixed) if raw_cloud_alpha_fixed is not None else True
    if raw_cloud_alpha is not None and _as_false(raw_cloud_alpha):
        cloud_alpha_fixed = False
    if (
        _as_bool(body.get("cloud_fit_alpha"))
        or _as_bool(args.get("cloud_fit_alpha"))
        or _as_bool(body.get("fit_cloud_alpha"))
        or _as_bool(args.get("fit_cloud_alpha"))
    ):
        cloud_alpha_fixed = False
    priority_standard_specid = None
    raw_priority_standard_specid = (
        body.get("priority_standard_specid")
        or body.get("current_standard_specid")
        or args.get("priority_standard_specid")
    )
    try:
        priority_standard_specid = int(raw_priority_standard_specid)
    except (TypeError, ValueError):
        priority_standard_specid = None
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            payload = _mock_spt_compare(
                args,
                specid,
                bins,
                norm_regions_param,
                deredden,
                fixed_r_v,
                cloud_correction,
                cloud_alpha,
                cloud_alpha_fixed,
                cloud_lambda0,
            )
            return jsonify({"ok": True, "source": "mock", **payload})
        started = time.time()
        payload = _precompute_spt_comparison(
            args,
            specid,
            bins,
            norm_regions_param,
            deredden,
            fixed_r_v,
            cloud_correction=cloud_correction,
            cloud_alpha=cloud_alpha,
            cloud_alpha_fixed=cloud_alpha_fixed,
            cloud_lambda0=cloud_lambda0,
            priority_standard_specid=priority_standard_specid,
        )
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
                "cloud_correction": cloud_correction,
                "cloud_alpha": cloud_alpha,
                "cloud_alpha_fixed": cloud_alpha_fixed,
                "cloud_lambda0": cloud_lambda0,
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/spectral-typing/standard")
def spectral_typing_standard():
    args = dict(request.args)
    body = request.get_json(silent=True) or {}
    raw_specid = body.get("specid") or body.get("moca_specid") or args.get("specid") or args.get("moca_specid")
    raw_standard_specid = (
        body.get("standard_specid")
        or body.get("moca_standard_specid")
        or body.get("current_standard_specid")
        or args.get("standard_specid")
    )
    try:
        specid = int(raw_specid)
        standard_specid = int(raw_standard_specid)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "source": "none", "error": "Numeric specid and standard_specid are required"}), 400
    try:
        bins = int(body.get("bins") or body.get("bins_per_micron") or args.get("bins") or SPT_DEFAULT_BINS_PER_MICRON)
    except (TypeError, ValueError):
        bins = SPT_DEFAULT_BINS_PER_MICRON
    bins = max(1, min(bins, 2000))
    norm_text = body.get("norm") or body.get("norm_regions") or args.get("norm")
    norm_regions_param = _spt_parse_norm_regions(norm_text)
    deredden = _as_bool(body.get("deredden")) or _as_bool(args.get("deredden"))
    cloud_correction = (
        _as_bool(body.get("cloud_correction"))
        or _as_bool(body.get("cloud"))
        or _as_bool(args.get("cloud_correction"))
        or _as_bool(args.get("cloud"))
    )
    if deredden and cloud_correction:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": "Dereddening and brown dwarf cloud correction cannot be used simultaneously.",
        }), 400
    fixed_r_v = _spt_float(body.get("fix_rv") if body.get("fix_rv") is not None else args.get("fix_rv"))
    if fixed_r_v is not None and fixed_r_v <= 0:
        fixed_r_v = None
    raw_cloud_alpha = body.get("cloud_alpha") if body.get("cloud_alpha") is not None else args.get("cloud_alpha")
    cloud_alpha = _spt_float(raw_cloud_alpha)
    cloud_lambda0 = _spt_float(body.get("cloud_lambda0") if body.get("cloud_lambda0") is not None else args.get("cloud_lambda0"))
    cloud_alpha = cloud_alpha if cloud_alpha is not None and cloud_alpha > 0 else SPT_DEFAULT_CLOUD_ALPHA
    cloud_lambda0 = cloud_lambda0 if cloud_lambda0 is not None and cloud_lambda0 > 0 else SPT_DEFAULT_CLOUD_LAMBDA0
    raw_cloud_alpha_fixed = body.get("cloud_alpha_fixed") if body.get("cloud_alpha_fixed") is not None else args.get("cloud_alpha_fixed")
    cloud_alpha_fixed = not _as_false(raw_cloud_alpha_fixed) if raw_cloud_alpha_fixed is not None else True
    if raw_cloud_alpha is not None and _as_false(raw_cloud_alpha):
        cloud_alpha_fixed = False
    if (
        _as_bool(body.get("cloud_fit_alpha"))
        or _as_bool(args.get("cloud_fit_alpha"))
        or _as_bool(body.get("fit_cloud_alpha"))
        or _as_bool(args.get("fit_cloud_alpha"))
    ):
        cloud_alpha_fixed = False
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            payload = _mock_spt_compare(
                args,
                specid,
                bins,
                norm_regions_param,
                deredden,
                fixed_r_v,
                cloud_correction,
                cloud_alpha,
                cloud_alpha_fixed,
                cloud_lambda0,
                only_standard_specid=standard_specid,
            )
            return jsonify({"ok": True, "source": "mock", **payload})
        started = time.time()
        payload = _precompute_spt_comparison(
            args,
            specid,
            bins,
            norm_regions_param,
            deredden,
            fixed_r_v,
            cloud_correction=cloud_correction,
            cloud_alpha=cloud_alpha,
            cloud_alpha_fixed=cloud_alpha_fixed,
            cloud_lambda0=cloud_lambda0,
            only_standard_specid=standard_specid,
        )
        payload["meta"]["timings"] = {"standard_total": round(time.time() - started, 3)}
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
                "standard_specid": standard_specid,
                "bins_per_micron": bins,
                "norm_regions": norm_regions_param,
                "norm_regions_text": _spt_format_norm_regions(norm_regions_param),
                "deredden": deredden,
                "cloud_correction": cloud_correction,
                "cloud_alpha": cloud_alpha,
                "cloud_alpha_fixed": cloud_alpha_fixed,
                "cloud_lambda0": cloud_lambda0,
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/spectral-typing/cache/clear")
def spectral_typing_clear_cache():
    grid_count = len(_SPT_GRID_CACHE)
    spectrum_count = len(_SPT_SPECTRUM_CACHE)
    compare_count = len(_SPT_COMPARE_CACHE)
    standard_process_count = len(_SPT_STANDARD_PROCESS_CACHE)
    _SPT_GRID_CACHE.clear()
    _SPT_SPECTRUM_CACHE.clear()
    _SPT_COMPARE_CACHE.clear()
    _SPT_STANDARD_PROCESS_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {
            "spectralTypingGrid": grid_count,
            "spectralTypingSpectra": spectrum_count,
            "spectralTypingComparisons": compare_count,
            "spectralTypingProcessedStandards": standard_process_count,
        },
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.get("/api/spectra/search")
def spectra_explorer_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    selected_specids = _parse_spectra_explorer_specids(args) if (args.get("specids") or args.get("moca_specid") or args.get("specid")) else []
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            payload = _mock_spectra_explorer_search(query, selected_specids)
            return jsonify({"ok": True, "source": "mock", **payload})
        payload = _search_spectra_explorer_from_db(args, query, selected_specids)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "options": [],
            "values": [],
            "meta": {"row_count": 0},
        }), 500


@app.get("/api/spectra/load")
def spectra_explorer_load():
    args = dict(request.args)
    specids = _parse_spectra_explorer_specids(args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_spectra_explorer_payload(specids)})
        payload = _load_spectra_explorer_from_db(args, specids)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "spectra": [],
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "specid_count": 0,
                "row_count": 0,
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/spectra/cache/clear")
def spectra_explorer_clear_cache():
    spectra_count = len(_SPECTRA_EXPLORER_CACHE)
    _SPECTRA_EXPLORER_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {"spectraExplorer": spectra_count},
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.get("/api/gaia-cmd/options")
@app.get("/js/api/gaia-cmd/options")
def gaia_cmd_options():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({
                "ok": True,
                "source": "mock",
                "photometry": {
                    "simple": [
                        {
                            "value": row["psid"],
                            "simple_value": key,
                            "label": row["label"],
                            "moca_psid": row["psid"],
                            "system_band_simple": row["simple_band"],
                        }
                        for key, row in GAIA_CMD_SIMPLE_BANDS.items()
                    ],
                    "advanced": [],
                },
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "private_db": False,
                    "default": {"x1": "gaiadr3_bpmag", "x2": "gaiadr3_rpmag", "y": "gaiadr3_gmag"},
                },
                "cache": {"hit": False, "ttl_seconds": 0},
            })
        payload = _load_gaia_cmd_options_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "photometry": {"simple": [], "advanced": []},
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/gaia-cmd/search")
@app.get("/js/api/gaia-cmd/search")
def gaia_cmd_object_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            q = str(query or "").lower()
            options = [
                {"value": 602, "moca_oid": 602, "designation": "SIMP J013656.5+093347.3", "label": "SIMP J013656.5+093347.3"},
                {"value": 10995, "moca_oid": 10995, "designation": "2MASS J05591914-1404488", "label": "2MASS J05591914-1404488"},
                {"value": 506921, "moca_oid": 506921, "designation": "V* V2502 Oph", "label": "V* V2502 Oph"},
            ]
            if q:
                options = [
                    row for row in options
                    if q in str(row["label"]).lower()
                    or q in str(row["moca_oid"])
                    or q in str(row["designation"]).lower()
                ]
            return jsonify({"ok": True, "source": "mock", "options": options[:80], "meta": {"row_count": len(options[:80])}})
        payload = _search_gaia_cmd_objects_from_db(args, query)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "options": [],
            "meta": {"row_count": 0},
        }), 500


@app.get("/api/gaia-cmd/associations/search")
@app.get("/js/api/gaia-cmd/associations/search")
def gaia_cmd_association_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            q = str(query or "").lower()
            options = [
                {"value": "THA", "label": "THA - TW Hydrae Association"},
                {"value": "BPMG", "label": "BPMG - Beta Pictoris moving group"},
                {"value": "HYA", "label": "HYA - Hyades"},
                {"value": "TWA", "label": "TWA - TW Hydrae Association"},
            ]
            if q:
                options = [row for row in options if q in row["label"].lower()]
            return jsonify({"ok": True, "source": "mock", "options": options[:80], "meta": {"row_count": len(options[:80])}})
        payload = _search_xyzuvw_associations_from_db(args, query)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "options": [],
            "meta": {"row_count": 0},
        }), 500


@app.get("/api/gaia-cmd/data")
@app.get("/js/api/gaia-cmd/data")
def gaia_cmd_data():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_gaia_cmd_payload(args)})
        payload = _load_gaia_cmd_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "selection": _gaia_cmd_selection(args),
            "rows": [],
            "sequences": [],
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "row_count": 0,
                "sequence_count": 0,
                "truncated": False,
                "max_objects": _gaia_cmd_parse_max_objects(args.get("max_objects") or args.get("limit")),
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/gaia-cmd/cache/clear")
@app.post("/js/api/gaia-cmd/cache/clear")
def gaia_cmd_clear_cache():
    gaia_count = len(_GAIA_CMD_CACHE)
    _GAIA_CMD_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {"gaiaCmd": gaia_count},
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.get("/api/xyzuvw/options")
def xyzuvw_options():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_xyzuvw_options()})
        payload = _load_xyzuvw_options_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "associations": [],
            "mtids": [],
            "versions": [{"value": "latest", "label": "Latest available"}],
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/xyzuvw/search")
def xyzuvw_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            q = str(query or "").lower()
            options = [
                {"value": 602, "moca_oid": 602, "designation": "SIMP J013656.5+093347.3", "label": "oid602: SIMP J013656.5+093347.3"},
                {"value": 10995, "moca_oid": 10995, "designation": "Mock moving-group candidate", "label": "oid10995: Mock moving-group candidate"},
            ]
            if q:
                options = [row for row in options if q in row["label"].lower()]
            return jsonify({"ok": True, "source": "mock", "options": options, "meta": {"row_count": len(options)}})
        payload = _search_xyzuvw_objects_from_db(args, query)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "options": [],
            "meta": {"row_count": 0},
        }), 500


@app.get("/api/xyzuvw/associations/search")
def xyzuvw_association_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            q = str(query or "").lower()
            options = _mock_xyzuvw_options()["associations"]
            if q:
                options = [row for row in options if q in str(row.get("label") or row.get("value") or "").lower()]
            return jsonify({"ok": True, "source": "mock", "options": options[:80], "meta": {"row_count": len(options[:80])}})
        payload = _search_xyzuvw_associations_from_db(args, query)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "options": [],
            "meta": {"row_count": 0},
        }), 500


@app.get("/api/xyzuvw/data")
def xyzuvw_data():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_xyzuvw_payload(args)})
        payload = _load_xyzuvw_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "selection": _parse_xyzuvw_selection(args),
            "members": [],
            "models": [],
            "objects": [],
            "labels": [],
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "member_count": 0,
                "model_count": 0,
                "object_count": 0,
                "truncated": False,
                "max_objects": XYZUVW_MAX_OBJECTS,
                "c_value": XYZUVW_C_VALUE,
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/xyzuvw/cache/clear")
def xyzuvw_clear_cache():
    xyzuvw_count = len(_XYZUVW_CACHE)
    _XYZUVW_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {"xyzuvw": xyzuvw_count},
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.get("/api/trueflow-age-pdfs/options")
@app.get("/api/age-pdfs/options")
@app.get("/js/api/trueflow-age-pdfs/options")
@app.get("/js/api/age-pdfs/options")
def trueflow_age_pdfs_options():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_tfage_options()})
        payload = _load_tfage_options_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "associations": [],
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "association_count": 0},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/trueflow-age-pdfs/search")
@app.get("/api/age-pdfs/search")
@app.get("/js/api/trueflow-age-pdfs/search")
@app.get("/js/api/age-pdfs/search")
def trueflow_age_pdfs_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    selected_oid = None
    raw_oid = args.get("moca_oid") or args.get("oid")
    if raw_oid is not None:
        try:
            selected_oid = int(raw_oid)
        except (TypeError, ValueError):
            selected_oid = None
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            options = [
                {
                    "value": TRUEFLOW_AGE_DEFAULT_OID,
                    "moca_oid": TRUEFLOW_AGE_DEFAULT_OID,
                    "designation": "Mock age-PDF target",
                    "label": f"oid{TRUEFLOW_AGE_DEFAULT_OID}: Mock age-PDF target",
                },
                {"value": 602, "moca_oid": 602, "designation": "SIMP J013656.5+093347.3", "label": "oid602: SIMP J013656.5+093347.3"},
            ]
            q = str(query or "").strip().lower()
            if q:
                options = [row for row in options if q in row["label"].lower()]
            return jsonify({"ok": True, "source": "mock", "options": options, "value": selected_oid, "meta": {"row_count": len(options)}})
        payload = _search_tfage_objects_from_db(args, query, selected_oid)
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


@app.get("/api/trueflow-age-pdfs/data")
@app.get("/api/age-pdfs/data")
@app.get("/js/api/trueflow-age-pdfs/data")
@app.get("/js/api/age-pdfs/data")
def trueflow_age_pdfs_data():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_tfage_payload(args)})
        payload = _load_tfage_payload_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "selection": {
                "scope": _tfage_scope(args),
                "target": _tfage_target(args, _tfage_scope(args)),
                "load_posteriors": _tfage_load_posteriors(args),
            },
            "target": {},
            "curves": [],
            "tableRows": [],
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "age_row_count": 0,
                "curve_count": 0,
                "displayable_curve_count": 0,
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/trueflow-age-pdfs/cache/clear")
@app.post("/api/age-pdfs/cache/clear")
@app.post("/js/api/trueflow-age-pdfs/cache/clear")
@app.post("/js/api/age-pdfs/cache/clear")
def trueflow_age_pdfs_clear_cache():
    age_count = len(_TRUEFLOW_AGE_CACHE)
    _TRUEFLOW_AGE_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {"trueflowAgePdfs": age_count},
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.get("/api/astrometry/search")
def astrometry_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    selected_oid = None
    raw_oid = args.get("moca_oid") or args.get("oid")
    if raw_oid is not None:
        try:
            selected_oid = int(raw_oid)
        except (TypeError, ValueError):
            selected_oid = None
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            payload = _mock_astrometry_search(query, selected_oid)
            return jsonify({"ok": True, "source": "mock", **payload})
        payload = _search_astrometry_objects_from_db(args, query, selected_oid)
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


@app.get("/api/astrometry/object/<int:oid>")
def astrometry_object(oid: int):
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_astrometry_object(oid, _include_merged_astrometry(args))})
        payload = _load_astrometry_object_from_db(args, oid)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "target": {"moca_oid": int(oid), "designation": None, "designations": []},
            "reference": {},
            "pm": {},
            "parallax": {},
            "missions": [],
            "rows": [],
            "meta": {"row_count": 0, "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/astrometry/cache/clear")
def astrometry_clear_cache():
    object_count = len(_ASTROMETRY_OBJECT_CACHE)
    _ASTROMETRY_OBJECT_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {"astrometryObjects": object_count},
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.post("/api/cache/clear")
def clear_cache():
    bootstrap_count = len(_BOOTSTRAP_CACHE)
    feature_count = len(_FEATURE_CACHE)
    spt_grid_count = len(_SPT_GRID_CACHE)
    spt_spectrum_count = len(_SPT_SPECTRUM_CACHE)
    spt_compare_count = len(_SPT_COMPARE_CACHE)
    spt_standard_process_count = len(_SPT_STANDARD_PROCESS_CACHE)
    astrometry_count = len(_ASTROMETRY_OBJECT_CACHE)
    spectra_explorer_count = len(_SPECTRA_EXPLORER_CACHE)
    xyzuvw_count = len(_XYZUVW_CACHE)
    trueflow_age_count = len(_TRUEFLOW_AGE_CACHE)
    gaia_cmd_count = len(_GAIA_CMD_CACHE)
    _BOOTSTRAP_CACHE.clear()
    _FEATURE_CACHE.clear()
    _SPT_GRID_CACHE.clear()
    _SPT_SPECTRUM_CACHE.clear()
    _SPT_COMPARE_CACHE.clear()
    _SPT_STANDARD_PROCESS_CACHE.clear()
    _ASTROMETRY_OBJECT_CACHE.clear()
    _SPECTRA_EXPLORER_CACHE.clear()
    _XYZUVW_CACHE.clear()
    _TRUEFLOW_AGE_CACHE.clear()
    _GAIA_CMD_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {
            "bootstrap": bootstrap_count,
            "features": feature_count,
            "spectralTypingGrid": spt_grid_count,
            "spectralTypingSpectra": spt_spectrum_count,
            "spectralTypingComparisons": spt_compare_count,
            "spectralTypingProcessedStandards": spt_standard_process_count,
            "astrometryObjects": astrometry_count,
            "spectraExplorer": spectra_explorer_count,
            "xyzuvw": xyzuvw_count,
            "trueflowAgePdfs": trueflow_age_count,
            "gaiaCmd": gaia_cmd_count,
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
