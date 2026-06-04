from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import json
import math
import os
import random
import re
import sys
import tempfile
import time
import traceback
import types
import zlib
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Mapping, Sequence
from urllib.parse import quote_plus

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
os.environ["MPLBACKEND"] = "Agg"

_LOCAL_BANYAN_SIGMA_SRC = Path(
    os.environ.get(
        "BANYAN_SIGMA_SRC",
        str(Path(__file__).resolve().parents[2] / "banyan_sigma" / "src"),
    )
)
if _LOCAL_BANYAN_SIGMA_SRC.is_dir():
    sys.path.insert(0, str(_LOCAL_BANYAN_SIGMA_SRC))

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
SAFE_SCHEMA_RE = re.compile(r"^[A-Za-z0-9_]+$")
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
_MOCA_EXPLORER_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_GROUP_HIERARCHY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LEGACY_RV_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_MORANTA26_ROTATION_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_RVBAM_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_RVBAM_ARRAY_CACHE: dict[str, tuple[float, np.ndarray]] = {}
_BANYAN_SIGMA_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_BANYAN_HYPOTHESES_CACHE: dict[str, Any] | None = None
_BANYAN_LNP_LOCK = Lock()
_DB_TABLE_EXISTS_CACHE: dict[tuple[str, str, str, str, str], bool] = {}
_DB_COLUMNS_CACHE: dict[tuple[str, str, str, str, str], set[str]] = {}
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
SPECTRA_EXPLORER_DEFAULT_BINS_PER_MICRON = int(os.environ.get("SPECTRA_EXPLORER_BINS_PER_MICRON", "0"))
XYZUVW_DEFAULT_AIDS = ("HYA", "TWA", "THA")
XYZUVW_DEFAULT_MTIDS = ("BF", "HM", "CM")
MOCA_EXPLORER_DEFAULT_AIDS = ("ABDMG", "BPMG", "TWA", "THA")
MOCA_EXPLORER_DEFAULT_MTIDS = ("BF", "HM", "CM")
MOCA_EXPLORER_DEFAULT_MAX_OBJECTS = int(os.environ.get("MOCA_EXPLORER_MAX_OBJECTS", "80000"))
MOCA_EXPLORER_HARD_MAX_OBJECTS = int(os.environ.get("MOCA_EXPLORER_HARD_MAX_OBJECTS", "250000"))
BANYAN_SIGMA_DEFAULT_TOP_N = int(os.environ.get("BANYAN_SIGMA_DEFAULT_TOP_N", "4"))
BANYAN_SIGMA_MAX_TOP_N = int(os.environ.get("BANYAN_SIGMA_MAX_TOP_N", "50"))
BANYAN_SIGMA_CACHE_SCHEMA = "banyan-sigma-web-v3"
BANYAN_SIGMA_DISTANCE_RANGE_UNBOUNDED_MAX_PC = float(
    os.environ.get("BANYAN_SIGMA_DISTANCE_RANGE_UNBOUNDED_MAX_PC", "1000000000")
)
BANYAN_SIGMA_PARALLAX_RANGE_INFLATE_PERCENT = float(
    os.environ.get("BANYAN_SIGMA_PARALLAX_RANGE_INFLATE_PERCENT", "10")
)
BANYAN_SIGMA_PARALLAX_RANGE_INFLATE_PC = float(
    os.environ.get("BANYAN_SIGMA_PARALLAX_RANGE_INFLATE_PC", "10")
)
BANYAN_SIGMA_PARALLAX_RANGE_MIN_UPPER_PC = float(
    os.environ.get("BANYAN_SIGMA_PARALLAX_RANGE_MIN_UPPER_PC", "75")
)
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
GAIA_CMD_SPT_AXIS_SEQUENCE_IDS = {
    ("GBP", "GRP"): "sptn_bprp_gaiaedr3_field",
    ("G", "GRP"): "sptn_grp_gaiaedr3_field",
}


def _db_config(args: dict[str, Any]) -> dict[str, str]:
    username = args.get("user") or os.environ.get("MOCA_USERNAME", DEFAULT_USERNAME)
    dbname = args.get("dbase") or os.environ.get("MOCA_DBNAME", DEFAULT_DBNAME)
    if str(username).strip().lower() == "public":
        dbname = "mocadb"
    return {
        "host": args.get("host") or os.environ.get("MOCA_HOST", DEFAULT_HOST),
        "username": username,
        "password": args.get("pwd") or os.environ.get("MOCA_PASSWORD", DEFAULT_PASSWORD),
        "dbname": dbname,
    }


def _is_private_db(args: dict[str, Any]) -> bool:
    return str(_db_config(args)["dbname"]).strip("`").lower() == "mocadb_private_tables"


def _db_schema_identifier(args: dict[str, Any]) -> str:
    dbname = str(_db_config(args)["dbname"]).strip("`")
    if not SAFE_SCHEMA_RE.fullmatch(dbname):
        raise ValueError(f"Unsafe database name: {dbname!r}")
    return f"`{dbname}`"


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


def _db_metadata_cache_key(conn, name: str) -> tuple[str, str, str, str, str]:
    try:
        url = conn.engine.url
        return (
            str(getattr(url, "drivername", "") or ""),
            str(getattr(url, "username", "") or ""),
            str(getattr(url, "host", "") or ""),
            str(getattr(url, "database", "") or ""),
            str(name),
        )
    except Exception:
        return ("", "", "", "", str(name))


def _db_table_exists(conn, table_name: str) -> bool:
    cache_key = _db_metadata_cache_key(conn, table_name)
    cached = _DB_TABLE_EXISTS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    query = text("""
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
            AND table_name = :table_name
    """)
    exists = int(conn.execute(query, {"table_name": table_name}).scalar() or 0) > 0
    _DB_TABLE_EXISTS_CACHE[cache_key] = exists
    return exists


def _db_table_columns(conn, table_name: str) -> set[str]:
    cache_key = _db_metadata_cache_key(conn, table_name)
    cached = _DB_COLUMNS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    rows = conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
            AND table_name = :table_name
    """), {"table_name": table_name}).fetchall()
    columns = {str(row[0]) for row in rows}
    _DB_COLUMNS_CACHE[cache_key] = columns
    return columns


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
        spectra_oid_filter = _oid_filter_sql("ms", selected_oids)
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

        spectra = read_records("spectra", """
            SELECT
                ms.moca_oid,
                ms.moca_specid
            FROM moca_spectra ms
            WHERE ms.moca_specid IS NOT NULL
                AND ms.moca_oid IS NOT NULL
                AND (ms.moca_specpackid != 1 OR ms.moca_specpackid IS NULL)
                AND COALESCE(ms.ignored, 0) = 0
                AND {spectra_oid_filter}
            ORDER BY ms.moca_oid, ms.moca_specid
        """.format(spectra_oid_filter=spectra_oid_filter))

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
            "spectra": spectra,
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
            "spectra_count": len(spectra),
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
                    MIN(dsi.moca_specid) AS moca_specid,
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
                    MIN(dew.moca_specid) AS moca_specid,
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
    spectra = []
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

        for specid in [200000 + oid, 210000 + oid, 220000 + oid, 230000 + oid, 240000 + oid]:
            spectra.append({"moca_oid": oid, "moca_specid": specid})

        spectral_indices.append({
            "moca_oid": oid,
            "moca_siid": "h2o_j",
            "moca_specid": 200000 + oid,
            "index_value": round(0.95 - 0.015 * spt + rng.gauss(0, 0.02), 4),
            "index_value_unc": 0.02,
            "description": "H2O-J spectral index",
            "spectral_index_ref": "mock",
        })
        spectral_indices.append({
            "moca_oid": oid,
            "moca_siid": "ch4_h",
            "moca_specid": 210000 + oid,
            "index_value": round(1.05 - 0.012 * spt + rng.gauss(0, 0.02), 4),
            "index_value_unc": 0.025,
            "description": "CH4-H spectral index",
            "spectral_index_ref": "mock",
        })
        equivalent_widths.append({
            "moca_oid": oid,
            "moca_spid": "li",
            "moca_specid": 220000 + oid,
            "ew_angstrom": round(max(0, rng.gauss(0.25 if spt > 16 else 0.05, 0.08)), 4),
            "ew_angstrom_unc": 0.03,
            "description": "Lithium 6708",
            "equivalent_width_ref": "mock",
        })
        equivalent_widths.append({
            "moca_oid": oid,
            "moca_spid": "na_i_8190",
            "moca_specid": 230000 + oid,
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
            "spectra": spectra,
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
            "spectra_count": len(spectra),
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


def _gaia_cmd_spt_axis_sequence_id(selection: dict[str, Any]) -> str | None:
    x1_band = _gaia_cmd_band_key(selection["x1"])
    x2_band = _gaia_cmd_band_key(selection["x2"])
    return GAIA_CMD_SPT_AXIS_SEQUENCE_IDS.get((x1_band, x2_band))


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
                ORDER BY field.random_index
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
        spt_axis: dict[str, Any] | None = None
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

        spt_axis_seqid = _gaia_cmd_spt_axis_sequence_id(selection)
        if spt_axis_seqid:
            spt_axis_rows = _records(_read_sql(conn, """
                SELECT
                    ms.moca_seqid,
                    COALESCE(ms.name_bdcolapp, ms.moca_seqid) AS name,
                    ms.xname,
                    ms.yname,
                    ms.valid_xrange_min,
                    ms.valid_xrange_max,
                    ms.valid_yrange_min,
                    ms.valid_yrange_max,
                    das.xdata AS sptn,
                    das.ydata AS color
                FROM moca_sequences ms
                JOIN data_astro_sequences das
                    ON das.moca_seqid = ms.moca_seqid
                WHERE ms.moca_seqid = :spt_axis_seqid
                    AND COALESCE(ms.ignored, 0) = 0
                    AND COALESCE(das.ignored, 0) = 0
                    AND das.xdata IS NOT NULL
                    AND das.ydata IS NOT NULL
                ORDER BY das.xdata
            """, {"spt_axis_seqid": spt_axis_seqid}))
            if spt_axis_rows:
                first = spt_axis_rows[0]
                spt_axis = {
                    "moca_seqid": spt_axis_seqid,
                    "name": first.get("name") or spt_axis_seqid,
                    "xname": first.get("xname"),
                    "yname": first.get("yname"),
                    "valid_xrange_min": _pythonize(first.get("valid_xrange_min")),
                    "valid_xrange_max": _pythonize(first.get("valid_xrange_max")),
                    "valid_yrange_min": _pythonize(first.get("valid_yrange_min")),
                    "valid_yrange_max": _pythonize(first.get("valid_yrange_max")),
                    "sptn": [
                        round(float(row["sptn"]), 5)
                        for row in spt_axis_rows
                        if row.get("sptn") is not None and row.get("color") is not None
                    ],
                    "color": [
                        round(float(row["color"]), 5)
                        for row in spt_axis_rows
                        if row.get("sptn") is not None and row.get("color") is not None
                    ],
                }

    rows = _records(rows_df)
    payload = {
        "selection": selection,
        "rows": rows,
        "sequences": sequences,
        "spt_axis": spt_axis,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "row_count": len(rows),
            "sequence_count": len(sequences),
            "sequence_ids": _gaia_cmd_sequence_ids(selection),
            "spt_axis_sequence_id": spt_axis["moca_seqid"] if spt_axis else None,
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
    spt_axis_seqid = _gaia_cmd_spt_axis_sequence_id(selection)
    spt_axis = None
    if spt_axis_seqid:
        sptn = np.linspace(-35, 5, 161)
        if spt_axis_seqid == "sptn_grp_gaiaedr3_field":
            color = 0.25 + (sptn + 35) * 0.031
        else:
            color = 0.25 + (sptn + 35) * 0.078
        spt_axis = {
            "moca_seqid": spt_axis_seqid,
            "name": spt_axis_seqid,
            "xname": "spectral_type_number",
            "yname": "gaia_color",
            "sptn": sptn.round(4).tolist(),
            "color": color.round(4).tolist(),
        }
    return {
        "selection": selection,
        "rows": rows,
        "sequences": sequences,
        "spt_axis": spt_axis,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "row_count": len(rows),
            "sequence_count": len(sequences),
            "sequence_ids": _gaia_cmd_sequence_ids(selection),
            "spt_axis_sequence_id": spt_axis["moca_seqid"] if spt_axis else None,
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
    agecolor_aliases = {"age", "agecolor", "age_color", "color_age", "color-by-age", "color_by_age", "colorbyage"}
    if checkbox_values.intersection(agecolor_aliases):
        checkbox_values.difference_update(agecolor_aliases)
        checkbox_values.add("agecolor")
    for key in ("models", "errors", "hover", "assmem", "likely", "asscen", "subgroups", "agecolor"):
        if _as_bool(args.get(key)):
            checkbox_values.add(key)
    if any(_as_bool(args.get(key)) for key in ("color_age", "color_by_age", "age_color")):
        checkbox_values.add("agecolor")
    if not has_checkbox_param and args.get("likely") is None:
        checkbox_values.add("likely")
    if not has_checkbox_param and args.get("subgroups") is None:
        checkbox_values.add("subgroups")
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
        "subgroups": "subgroups" in checkbox_values,
        "color_by_age": "agecolor" in checkbox_values,
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
        "folded-subgroups-v1",
        "".join(selection["axes"]),
        ",".join(selection["aids"]),
        ",".join(selection["mtids"]),
        ",".join(str(oid) for oid in selection["oids"]),
        str(selection["bsmdid"]),
        str(int(selection["likely"])),
        str(int(selection["labels"])),
        str(int(selection["subgroups"])),
        str(int(selection["color_by_age"])),
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


def _xyzuvw_requested_aids_query(selection: dict[str, Any]) -> str:
    requested_aids = "\n                UNION\n".join(
        f"                SELECT :aid_{index} AS moca_aid FROM DUAL"
        for index, _aid in enumerate(selection["aids"])
    ) or "                SELECT NULL AS moca_aid FROM DUAL"
    return requested_aids


def _xyzuvw_member_aids_query(selection: dict[str, Any], requested_aids_query: str, aid_clause: str) -> str:
    if not selection["subgroups"]:
        return f"""
                SELECT requested_aids.moca_aid, requested_aids.moca_aid AS member_moca_aid
                FROM (
{requested_aids_query}
                ) requested_aids
        """
    return f"""
                SELECT requested_aids.moca_aid, requested_aids.moca_aid AS member_moca_aid
                FROM (
{requested_aids_query}
                ) requested_aids
                UNION
                SELECT mar.parent AS moca_aid, mar.moca_aid AS member_moca_aid
                FROM mechanics_all_association_relationships mar
                WHERE mar.parent IN ({aid_clause})
    """


def _xyzuvw_association_age_query() -> str:
    return """
        SELECT daa.moca_aid, MIN(daa.age_myr) AS age_myr
        FROM data_association_ages daa
        WHERE daa.adopted = 1
            AND daa.age_myr IS NOT NULL
        GROUP BY daa.moca_aid
    """


def _xyzuvw_model_query(selection: dict[str, Any], selected_aids_query: str) -> str:
    columns = """
        dbs2.moca_aid,
        daa.age_myr,
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
                JOIN (
{selected_aids_query}
                ) selected_aids
                    ON selected_aids.moca_aid = dbs.moca_aid
                GROUP BY dbs.moca_aid
            ) inq USING(moca_aid, moca_bsmdid)
            LEFT JOIN (
{_xyzuvw_association_age_query()}
            ) daa
                ON daa.moca_aid = dbs2.moca_aid
            ORDER BY dbs2.moca_aid, dbs2.coeff_index
        """
    return f"""
        SELECT {columns}
        FROM data_banyan_sigma_models dbs2
        JOIN (
{selected_aids_query}
        ) selected_aids
            ON selected_aids.moca_aid = dbs2.moca_aid
        LEFT JOIN (
{_xyzuvw_association_age_query()}
        ) daa
            ON daa.moca_aid = dbs2.moca_aid
        WHERE dbs2.moca_bsmdid = :bsmdid
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
                "age_myr": next(
                    (
                        _pythonize(model.get("age_myr"))
                        for model in aid_models
                        if _safe_float(model.get("age_myr")) is not None
                    ),
                    None,
                ),
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
    requested_aids_query = _xyzuvw_requested_aids_query(selection)
    member_aids_query = _xyzuvw_member_aids_query(selection, requested_aids_query, aid_clause)
    if selection["bsmdid"] != "latest":
        params["bsmdid"] = int(selection["bsmdid"])

    include_covariances = "errors" in selection["checkboxes"]
    covariance_columns = ""
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

    private_db = _is_private_db(args)
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
        xyz_public_filter = "AND xyz.is_public = 0" if private_db else ""
        uvw_public_filter = "AND uvw.is_public = 0" if private_db else ""
        cbs_public_filter = "AND cbs.is_public = 0" if private_db else ""
        cbs_probability_filter = "AND cbs.ya_prob >= 90" if selection["likely"] else ""
        require_banyan_filter = "AND best_cbs.cbs_id IS NOT NULL" if selection["likely"] else ""
        members_df = _read_sql(conn, f"""
            SELECT
                mo.designation,
                folded_members.moca_aid,
                folded_members.source_moca_aids,
                cbs.moca_aid AS bsigma_moca_aid,
                folded_members.moca_mtid,
                daa.age_myr,
                cspt.spectral_type AS spt,
                dr3.ruwe AS dr3_ruwe,
                folded_members.moca_oid,
                xyz.x_pc AS x,
                xyz.y_pc AS y,
                xyz.z_pc AS z,
                {covariance_columns}
                {XYZUVW_C_VALUE} * uvw.u_kms AS u,
                {XYZUVW_C_VALUE} * uvw.v_kms AS v,
                {XYZUVW_C_VALUE} * uvw.w_kms AS w,
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
            FROM (
                SELECT
                    selected_aids.moca_aid,
                    mmp.moca_oid,
                    mmp.moca_mtid,
                    GROUP_CONCAT(DISTINCT mmp.moca_aid ORDER BY mmp.moca_aid SEPARATOR ',') AS source_moca_aids
                FROM mechanics_memberships_propagated mmp
                JOIN (
{member_aids_query}
                ) selected_aids
                    ON selected_aids.member_moca_aid = mmp.moca_aid
                WHERE mmp.moca_mtid IN ({mtid_clause})
                GROUP BY selected_aids.moca_aid, mmp.moca_oid, mmp.moca_mtid
            ) folded_members
            JOIN moca_objects mo
                ON mo.moca_oid = folded_members.moca_oid
            LEFT JOIN data_spectral_types cspt
                ON cspt.moca_oid = folded_members.moca_oid
                AND cspt.adopted = 1
            LEFT JOIN cat_gaiadr3 dr3
                ON dr3.moca_oid = folded_members.moca_oid
            LEFT JOIN calc_xyz xyz
                ON xyz.moca_oid = folded_members.moca_oid
                AND xyz.ignored = 0
                {xyz_public_filter}
            LEFT JOIN calc_uvw uvw
                ON uvw.moca_oid = folded_members.moca_oid
                AND uvw.moca_aid = folded_members.moca_aid
                AND uvw.ignored = 0
                {uvw_public_filter}
            LEFT JOIN (
                SELECT
                    selected_aids.moca_aid,
                    mmp.moca_oid,
                    mmp.moca_mtid,
                    CAST(SUBSTRING_INDEX(
                        GROUP_CONCAT(
                            cbs.id
                            ORDER BY
                                cbs.ya_prob DESC,
                                IF(selected_aids.member_moca_aid = selected_aids.moca_aid, 1, 0) DESC,
                                cbs.id DESC
                            SEPARATOR ','
                        ),
                        ',',
                        1
                    ) AS UNSIGNED) AS cbs_id
                FROM mechanics_memberships_propagated mmp
                JOIN (
{member_aids_query}
                ) selected_aids
                    ON selected_aids.member_moca_aid = mmp.moca_aid
                JOIN calc_banyan_sigma cbs
                    ON cbs.moca_oid = mmp.moca_oid
                    AND cbs.moca_aid = selected_aids.member_moca_aid
                    AND cbs.moca_bsmdid = :active_bsmdid
                    AND cbs.max_observables = 1
                    {cbs_public_filter}
                WHERE mmp.moca_mtid IN ({mtid_clause})
                    {cbs_probability_filter}
                GROUP BY selected_aids.moca_aid, mmp.moca_oid, mmp.moca_mtid
            ) best_cbs
                ON best_cbs.moca_aid = folded_members.moca_aid
                AND best_cbs.moca_oid = folded_members.moca_oid
                AND best_cbs.moca_mtid = folded_members.moca_mtid
            LEFT JOIN calc_banyan_sigma cbs
                ON cbs.id = best_cbs.cbs_id
            LEFT JOIN calc_banyan_sigma_details cbsd
                ON cbs.id = cbsd.cbs_id
                AND cbsd.moca_aid = cbs.moca_aid
            LEFT JOIN (
{_xyzuvw_association_age_query()}
            ) daa
                ON daa.moca_aid = folded_members.moca_aid
            WHERE 1 = 1
                {require_banyan_filter}
            ORDER BY folded_members.moca_aid, folded_members.moca_mtid, folded_members.moca_oid
            LIMIT {XYZUVW_MAX_OBJECTS}
        """, params)
        models_df = _read_sql(conn, _xyzuvw_model_query(selection, requested_aids_query), params)

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


def _moca_explorer_parse_max_objects(raw: Any) -> int:
    if raw is None or str(raw).strip() == "":
        return max(1, min(MOCA_EXPLORER_DEFAULT_MAX_OBJECTS, MOCA_EXPLORER_HARD_MAX_OBJECTS))
    if str(raw).strip().lower() in {"0", "none", "uncapped", "all"}:
        return MOCA_EXPLORER_HARD_MAX_OBJECTS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = MOCA_EXPLORER_DEFAULT_MAX_OBJECTS
    return max(1, min(value, MOCA_EXPLORER_HARD_MAX_OBJECTS))


def _moca_explorer_selection(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "aids": _parse_xyzuvw_csv_ids(
            args.get("asso") or args.get("association") or args.get("moca_aid") or args.get("aid"),
            MOCA_EXPLORER_DEFAULT_AIDS,
        )[:80],
        "mtids": _parse_xyzuvw_csv_ids(args.get("mtid") or args.get("moca_mtid"), MOCA_EXPLORER_DEFAULT_MTIDS)[:80],
        "oids": _parse_xyzuvw_oids(args.get("oid") or args.get("oids") or args.get("moca_oid") or args.get("moca_oids")),
        "max_objects": _moca_explorer_parse_max_objects(args.get("max_objects") or args.get("limit")),
    }


def _moca_explorer_cache_key(args: dict[str, Any], selection: dict[str, Any]) -> str:
    cfg = _db_config(args)
    return "|".join([
        cfg["host"],
        cfg["username"],
        cfg["dbname"],
        "moca-explorer-v3-ew-base-tables",
        ",".join(selection["aids"]),
        ",".join(selection["mtids"]),
        ",".join(str(oid) for oid in selection["oids"]),
        str(selection["max_objects"]),
    ])


def _moca_explorer_add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    for column in [
        "moca_oid", "gmag", "bmag", "rmag", "plx", "dmod", "dr3_ruwe",
        "x", "y", "z", "u", "v", "w", "x_opt", "y_opt", "z_opt", "u_opt",
        "v_opt", "w_opt", "prot_days", "gaia_act", "ewli", "ewha",
    ]:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    if {"gmag", "rmag"}.issubset(out.columns):
        out["gr"] = out["gmag"] - out["rmag"]
    if {"bmag", "rmag"}.issubset(out.columns):
        out["br"] = out["bmag"] - out["rmag"]
    if {"gmag", "plx"}.issubset(out.columns):
        plx = out["plx"].where(out["plx"] > 0)
        out["m_g"] = out["gmag"] - 5.0 * (np.log10(1000.0 / plx) - 1.0)
    if {"rmag", "plx"}.issubset(out.columns):
        plx = out["plx"].where(out["plx"] > 0)
        out["m_r"] = out["rmag"] - 5.0 * (np.log10(1000.0 / plx) - 1.0)
    if "moca_oid" in out.columns:
        out["report_url"] = out["moca_oid"].apply(
            lambda oid: (
                f"https://mocadb.ca/search/results?search-query=oid%28{int(oid)}%29&search-type=star"
                if pd.notna(oid)
                else None
            )
        )
    for column, digits in {
        "gmag": 5, "bmag": 5, "rmag": 5, "plx": 5, "dmod": 5, "dr3_ruwe": 4,
        "x": 5, "y": 5, "z": 5, "u": 5, "v": 5, "w": 5,
        "x_opt": 5, "y_opt": 5, "z_opt": 5, "u_opt": 5, "v_opt": 5, "w_opt": 5,
        "prot_days": 5, "gaia_act": 6, "ewli": 5, "ewha": 5,
        "gr": 5, "br": 5, "m_g": 5, "m_r": 5,
    }.items():
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").round(digits)
    return out


def _moca_explorer_sequence_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        seqid = str(row.get("moca_seqid") or "")
        if not seqid:
            continue
        item = grouped.setdefault(seqid, {
            "moca_seqid": seqid,
            "moca_aid": row.get("moca_aid"),
            "tag": row.get("tag") or seqid,
            "color": row.get("color") or "#444444",
            "width": _pythonize(row.get("width")) or 2,
            "style": row.get("style") or "solid",
            "x": [],
            "y": [],
        })
        item["x"].append(_pythonize(row.get("xdata")))
        item["y"].append(_pythonize(row.get("ydata")))
    return list(grouped.values())


def _moca_explorer_dataviz_sequences(conn, tool: str) -> list[dict[str, Any]]:
    rows = _records(_read_sql(conn, """
        SELECT
            das.xdata,
            das.ydata,
            mds.moca_aid,
            mds.tag,
            mds.moca_seqid,
            mds.color,
            mds.width,
            mds.style
        FROM moca_dataviz_sequences mds
        LEFT JOIN data_astro_sequences das
            ON das.moca_seqid = mds.moca_seqid
        WHERE mds.display = 1
            AND mds.dataviz_tool = :tool
            AND das.xdata IS NOT NULL
            AND das.ydata IS NOT NULL
        ORDER BY mds.moca_seqid, das.xdata
    """, {"tool": tool}))
    return _moca_explorer_sequence_records(rows)


def _moca_explorer_spt_axis(conn) -> list[dict[str, Any]]:
    return _records(_read_sql(conn, """
        SELECT
            das.xdata,
            das.ydata,
            ms.moca_seqid,
            ms.xname,
            ms.yname,
            ms.valid_xrange_min,
            ms.valid_xrange_max,
            ms.valid_yrange_min,
            ms.valid_yrange_max,
            ms.name_bdcolapp
        FROM moca_sequences ms
        LEFT JOIN data_astro_sequences das
            ON das.moca_seqid = ms.moca_seqid
        WHERE ms.moca_seqid IN ('sptn_bprp_gaiaedr3_field', 'sptn_grp_gaiaedr3_field')
            AND COALESCE(ms.ignored, 0) = 0
            AND COALESCE(das.ignored, 0) = 0
            AND das.xdata IS NOT NULL
            AND das.ydata IS NOT NULL
        ORDER BY ms.moca_seqid, das.xdata
    """))


def _moca_explorer_association_labels(conn) -> list[dict[str, Any]]:
    try:
        return _records(_read_sql(conn, "CALL list_association_labels()"))
    except Exception:
        return _records(_read_sql(conn, """
            SELECT
                dbs.moca_aid,
                AVG(dbs.x_cen) AS x,
                AVG(dbs.y_cen) AS y,
                AVG(dbs.z_cen) AS z,
                AVG(dbs.u_cen) AS u,
                AVG(dbs.v_cen) AS v,
                AVG(dbs.w_cen) AS w
            FROM data_banyan_sigma_models dbs
            JOIN moca_banyan_sigma_models mbsm
                ON mbsm.moca_bsmdid = dbs.moca_bsmdid
            WHERE mbsm.adopted = 1
                AND dbs.moca_aid <> 'FIELD'
            GROUP BY dbs.moca_aid
        """))


def _load_moca_explorer_options_from_db(args: dict[str, Any]) -> dict[str, Any]:
    selection = _moca_explorer_selection(args)
    cache_key = f"{_spt_db_cache_key(args)}|moca-explorer-options-v2|{','.join(selection['aids'])}"
    now = time.time()
    cached = _MOCA_EXPLORER_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        associations = _records(_read_sql(conn, """
            SELECT ma.moca_aid, ma.name
            FROM moca_associations ma
            ORDER BY ma.moca_aid
        """))
        mtids = _records(_read_sql(conn, """
            SELECT mt.moca_mtid, mt.name, mt.description
            FROM moca_membership_types mt
            WHERE EXISTS (
                SELECT 1
                FROM mechanics_memberships_propagated mmp
                WHERE mmp.moca_mtid = mt.moca_mtid
                LIMIT 1
            )
            ORDER BY mt.level DESC, mt.moca_mtid
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
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "default": {
                "aids": list(MOCA_EXPLORER_DEFAULT_AIDS),
                "mtids": list(MOCA_EXPLORER_DEFAULT_MTIDS),
            },
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _MOCA_EXPLORER_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _load_moca_explorer_from_db(args: dict[str, Any]) -> dict[str, Any]:
    selection = _moca_explorer_selection(args)
    cache_key = _moca_explorer_cache_key(args, selection)
    now = time.time()
    cached = _MOCA_EXPLORER_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    aid_clause, aid_params = _sql_in_clause("mex_aid", selection["aids"])
    mtid_clause, mtid_params = _sql_in_clause("mex_mtid", selection["mtids"])
    params: dict[str, Any] = {**aid_params, **mtid_params}
    private_db = _is_private_db(args)
    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        started = time.time()
        active_model_rows = _records(_read_sql(conn, """
            SELECT mbsm.moca_bsmdid
            FROM moca_banyan_sigma_models mbsm
            WHERE mbsm.adopted = 1
            ORDER BY mbsm.moca_bsmdid DESC
            LIMIT 1
        """))
        params["active_bsmdid"] = active_model_rows[0].get("moca_bsmdid") if active_model_rows else None
        xyz_public_filter = "AND xyz.is_public = 0" if private_db else ""
        uvw_public_filter = "AND uvw.is_public = 0" if private_db else ""
        raw_uvw_public_filter = "AND uvw.is_public = 0" if private_db else ""
        cbs_public_filter = "AND cbs.is_public = 0" if private_db else ""
        li_public_filter = ""
        ha_public_filter = ""
        if selection["aids"] and selection["mtids"]:
            members_df = _read_sql(conn, f"""
                SELECT
                    mo.designation,
                    mmp.moca_aid,
                    mmp.moca_mtid,
                    cspt.spectral_type AS spt,
                    mmp.moca_oid,
                    COALESCE(pg.magnitude, dr3.phot_g_mean_mag) AS gmag,
                    COALESCE(pb.magnitude, dr3.phot_bp_mean_mag) AS bmag,
                    COALESCE(pr.magnitude, dr3.phot_rp_mean_mag) AS rmag,
                    COALESCE(dplx.parallax_mas, dr3.parallax) AS plx,
                    COALESCE(dd.dmod, dplx.dmod) AS dmod,
                    COALESCE(dr3.ruwe, dplx.ruwe, dd.plx_ruwe) AS dr3_ruwe,
                    xyz.x_pc AS x,
                    xyz.y_pc AS y,
                    xyz.z_pc AS z,
                    uvw.u_kms AS u,
                    uvw.v_kms AS v,
                    uvw.w_kms AS w,
                    drp.prot_days,
                    gap.activityindex_espcs AS gaia_act,
                    1000 * li.ew_angstrom AS ewli,
                    ha.ew_angstrom AS ewha,
                    cbsd.x_opt,
                    cbsd.y_opt,
                    cbsd.z_opt,
                    cbsd.u_opt,
                    cbsd.v_opt,
                    cbsd.w_opt
                FROM mechanics_memberships_propagated mmp
                JOIN moca_objects mo
                    ON mo.moca_oid = mmp.moca_oid
                LEFT JOIN data_spectral_types cspt
                    ON cspt.moca_oid = mmp.moca_oid
                    AND cspt.adopted = 1
                    AND COALESCE(cspt.ignored, 0) = 0
                LEFT JOIN cat_gaiadr3 dr3
                    ON dr3.moca_oid = mmp.moca_oid
                LEFT JOIN cat_gaiadr3_astrophysical_parameters gap
                    ON gap.moca_oid = mmp.moca_oid
                LEFT JOIN data_photometry pg
                    ON pg.moca_oid = mmp.moca_oid
                    AND pg.moca_psid = 'gaiadr3_gmag'
                    AND pg.adopted = 1
                    AND COALESCE(pg.ignored, 0) = 0
                LEFT JOIN data_photometry pb
                    ON pb.moca_oid = mmp.moca_oid
                    AND pb.moca_psid = 'gaiadr3_bpmag'
                    AND pb.adopted = 1
                    AND COALESCE(pb.ignored, 0) = 0
                LEFT JOIN data_photometry pr
                    ON pr.moca_oid = mmp.moca_oid
                    AND pr.moca_psid = 'gaiadr3_rpmag'
                    AND pr.adopted = 1
                    AND COALESCE(pr.ignored, 0) = 0
                LEFT JOIN data_parallaxes dplx
                    ON dplx.moca_oid = mmp.moca_oid
                    AND dplx.adopted = 1
                    AND COALESCE(dplx.ignored, 0) = 0
                LEFT JOIN data_distances dd
                    ON dd.moca_oid = mmp.moca_oid
                    AND dd.adopted = 1
                    AND dd.photometric_estimate = 0
                    AND COALESCE(dd.ignored, 0) = 0
                LEFT JOIN calc_xyz xyz
                    ON xyz.moca_oid = mmp.moca_oid
                    AND COALESCE(xyz.ignored, 0) = 0
                    {xyz_public_filter}
                LEFT JOIN calc_uvw uvw
                    ON uvw.moca_oid = mmp.moca_oid
                    AND uvw.moca_aid = mmp.moca_aid
                    AND COALESCE(uvw.ignored, 0) = 0
                    {uvw_public_filter}
                LEFT JOIN data_rotation_periods drp
                    ON drp.moca_oid = mmp.moca_oid
                    AND drp.adopted = 1
                    AND COALESCE(drp.ignored, 0) = 0
                LEFT JOIN (
                    SELECT cew.moca_oid, MAX(cew.ew_angstrom) AS ew_angstrom
                    FROM calc_equivalent_widths_combined cew
                    WHERE cew.moca_spid IN ('li', 'li_lowres')
                        AND COALESCE(cew.ignored, 0) = 0
                        {li_public_filter}
                    GROUP BY cew.moca_oid
                ) li
                    ON li.moca_oid = mmp.moca_oid
                LEFT JOIN (
                    SELECT cew.moca_oid, MIN(cew.ew_angstrom) AS ew_angstrom
                    FROM calc_equivalent_widths_combined cew
                    WHERE cew.moca_spid IN ('halpha', 'h_alpha', 'ha')
                        AND COALESCE(cew.ignored, 0) = 0
                        {ha_public_filter}
                    GROUP BY cew.moca_oid
                ) ha
                    ON ha.moca_oid = mmp.moca_oid
                LEFT JOIN calc_banyan_sigma cbs
                    ON cbs.moca_oid = mmp.moca_oid
                    AND cbs.moca_bsmdid = :active_bsmdid
                    AND cbs.max_observables = 1
                    {cbs_public_filter}
                LEFT JOIN calc_banyan_sigma_details cbsd
                    ON cbsd.cbs_id = cbs.id
                    AND cbsd.moca_aid = mmp.moca_aid
                WHERE mmp.moca_aid IN ({aid_clause})
                    AND mmp.moca_mtid IN ({mtid_clause})
                ORDER BY mmp.moca_aid, mmp.moca_mtid, cspt.spectral_type_number, mmp.moca_oid
                LIMIT {selection["max_objects"]}
            """, params)
        else:
            members_df = pd.DataFrame()

        if selection["oids"]:
            oid_clause = ",".join(str(int(oid)) for oid in selection["oids"])
            objects_df = _read_sql(conn, f"""
                SELECT
                    mo.designation,
                    COALESCE(cbs.best_ya, cbs.moca_aid, 'N/A') AS moca_aid,
                    'N/A' AS moca_mtid,
                    cspt.spectral_type AS spt,
                    mo.moca_oid,
                    COALESCE(pg.magnitude, dr3.phot_g_mean_mag) AS gmag,
                    COALESCE(pb.magnitude, dr3.phot_bp_mean_mag) AS bmag,
                    COALESCE(pr.magnitude, dr3.phot_rp_mean_mag) AS rmag,
                    COALESCE(dplx.parallax_mas, dr3.parallax) AS plx,
                    COALESCE(dd.dmod, dplx.dmod) AS dmod,
                    COALESCE(dr3.ruwe, dplx.ruwe, dd.plx_ruwe) AS dr3_ruwe,
                    xyz.x_pc AS x,
                    xyz.y_pc AS y,
                    xyz.z_pc AS z,
                    uvw.u_kms AS u,
                    uvw.v_kms AS v,
                    uvw.w_kms AS w,
                    drp.prot_days,
                    gap.activityindex_espcs AS gaia_act,
                    1000 * li.ew_angstrom AS ewli,
                    ha.ew_angstrom AS ewha
                FROM moca_objects mo
                LEFT JOIN data_spectral_types cspt
                    ON cspt.moca_oid = mo.moca_oid
                    AND cspt.adopted = 1
                    AND COALESCE(cspt.ignored, 0) = 0
                LEFT JOIN cat_gaiadr3 dr3
                    ON dr3.moca_oid = mo.moca_oid
                LEFT JOIN cat_gaiadr3_astrophysical_parameters gap
                    ON gap.moca_oid = mo.moca_oid
                LEFT JOIN data_photometry pg
                    ON pg.moca_oid = mo.moca_oid
                    AND pg.moca_psid = 'gaiadr3_gmag'
                    AND pg.adopted = 1
                    AND COALESCE(pg.ignored, 0) = 0
                LEFT JOIN data_photometry pb
                    ON pb.moca_oid = mo.moca_oid
                    AND pb.moca_psid = 'gaiadr3_bpmag'
                    AND pb.adopted = 1
                    AND COALESCE(pb.ignored, 0) = 0
                LEFT JOIN data_photometry pr
                    ON pr.moca_oid = mo.moca_oid
                    AND pr.moca_psid = 'gaiadr3_rpmag'
                    AND pr.adopted = 1
                    AND COALESCE(pr.ignored, 0) = 0
                LEFT JOIN data_parallaxes dplx
                    ON dplx.moca_oid = mo.moca_oid
                    AND dplx.adopted = 1
                    AND COALESCE(dplx.ignored, 0) = 0
                LEFT JOIN data_distances dd
                    ON dd.moca_oid = mo.moca_oid
                    AND dd.adopted = 1
                    AND dd.photometric_estimate = 0
                    AND COALESCE(dd.ignored, 0) = 0
                LEFT JOIN calc_xyz xyz
                    ON xyz.moca_oid = mo.moca_oid
                    AND COALESCE(xyz.ignored, 0) = 0
                    {xyz_public_filter}
                LEFT JOIN calc_uvw_raw uvw
                    ON uvw.moca_oid = mo.moca_oid
                    AND COALESCE(uvw.ignored, 0) = 0
                    {raw_uvw_public_filter}
                LEFT JOIN data_rotation_periods drp
                    ON drp.moca_oid = mo.moca_oid
                    AND drp.adopted = 1
                    AND COALESCE(drp.ignored, 0) = 0
                LEFT JOIN (
                    SELECT cew.moca_oid, MAX(cew.ew_angstrom) AS ew_angstrom
                    FROM calc_equivalent_widths_combined cew
                    WHERE cew.moca_spid IN ('li', 'li_lowres')
                        AND COALESCE(cew.ignored, 0) = 0
                        {li_public_filter}
                    GROUP BY cew.moca_oid
                ) li
                    ON li.moca_oid = mo.moca_oid
                LEFT JOIN (
                    SELECT cew.moca_oid, MIN(cew.ew_angstrom) AS ew_angstrom
                    FROM calc_equivalent_widths_combined cew
                    WHERE cew.moca_spid IN ('halpha', 'h_alpha', 'ha')
                        AND COALESCE(cew.ignored, 0) = 0
                        {ha_public_filter}
                    GROUP BY cew.moca_oid
                ) ha
                    ON ha.moca_oid = mo.moca_oid
                LEFT JOIN calc_banyan_sigma cbs
                    ON cbs.moca_oid = mo.moca_oid
                    AND cbs.moca_bsmdid = :active_bsmdid
                    AND cbs.max_observables = 1
                    {cbs_public_filter}
                WHERE mo.moca_oid IN ({oid_clause})
                ORDER BY FIELD(mo.moca_oid, {oid_clause})
            """, params)
        else:
            objects_df = pd.DataFrame()

        aid_model_clause, aid_model_params = _sql_in_clause("model_aid", selection["aids"])
        models_df = _read_sql(conn, f"""
            SELECT dbs2.*
            FROM data_banyan_sigma_models dbs2
            JOIN (
                SELECT MAX(dbs.moca_bsmdid) AS moca_bsmdid, dbs.moca_aid
                FROM data_banyan_sigma_models dbs
                JOIN moca_banyan_sigma_models mbsm
                    ON mbsm.moca_bsmdid = dbs.moca_bsmdid
                WHERE mbsm.adopted = 1
                    AND dbs.moca_aid IN ({aid_model_clause})
                GROUP BY dbs.moca_aid
            ) adopted_models
                ON adopted_models.moca_aid = dbs2.moca_aid
                AND adopted_models.moca_bsmdid = dbs2.moca_bsmdid
            ORDER BY dbs2.moca_aid, dbs2.coeff_index
        """, aid_model_params) if selection["aids"] else pd.DataFrame()

        sequences = {
            "cmd": _moca_explorer_dataviz_sequences(conn, "moca_explorer_gaiadr3_mg_gr"),
            "cmdField": _moca_explorer_dataviz_sequences(conn, "moca_explorer_gaiadr3_mg_gr_fieldscatter"),
            "prot": _moca_explorer_dataviz_sequences(conn, "moca_explorer_prot_br"),
            "gaiaAct": _moca_explorer_dataviz_sequences(conn, "moca_explorer_gaiadr3_act_br"),
            "ewha": _moca_explorer_dataviz_sequences(conn, "moca_explorer_ewha_br"),
            "ewli": _moca_explorer_dataviz_sequences(conn, "moca_explorer_ewli_br"),
        }
        labels = _moca_explorer_association_labels(conn)
        spt_axis = _moca_explorer_spt_axis(conn)
        query_seconds = round(time.time() - started, 3)

    members_df = _moca_explorer_add_derived_columns(members_df)
    objects_df = _moca_explorer_add_derived_columns(objects_df)
    payload = {
        "selection": selection,
        "members": _records(members_df),
        "objects": _records(objects_df),
        "models": _records(models_df),
        "sequences": sequences,
        "labels": labels,
        "sptAxis": spt_axis,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "member_count": int(len(members_df)),
            "object_count": int(len(objects_df)),
            "model_count": int(len(models_df)),
            "sequence_count": sum(len(value) for value in sequences.values()),
            "label_count": len(labels),
            "spt_axis_count": len(spt_axis),
            "truncated": int(len(members_df)) >= selection["max_objects"],
            "max_objects": selection["max_objects"],
            "query_seconds": query_seconds,
            "legacy_source": "deprecated/moca_explorer.py",
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _MOCA_EXPLORER_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _mock_moca_explorer_options() -> dict[str, Any]:
    aids = ["ABDMG", "BPMG", "TWA", "THA", "HYA", "CBER"]
    return {
        "associations": [{"value": aid, "label": f"{aid} - Mock association"} for aid in aids],
        "mtids": [{"value": mtid, "label": f"{mtid} - Mock membership", "description": "Mock membership type"} for mtid in ["BF", "HM", "CM", "LM"]],
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "default": {
                "aids": list(MOCA_EXPLORER_DEFAULT_AIDS),
                "mtids": list(MOCA_EXPLORER_DEFAULT_MTIDS),
            },
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _mock_moca_explorer_payload(args: dict[str, Any]) -> dict[str, Any]:
    selection = _moca_explorer_selection(args)
    rng = np.random.default_rng(20260604)
    members: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for aid_index, aid in enumerate(selection["aids"]):
        center = np.asarray([
            -45 + 35 * aid_index,
            25 - 18 * aid_index,
            -15 + 9 * aid_index,
            -12 + 3.5 * aid_index,
            -20 + 2.2 * aid_index,
            -8 + 1.4 * aid_index,
        ])
        scatter = np.asarray([18, 14, 11, 4.5, 3.2, 2.8])
        labels.append({"moca_aid": aid, "x": center[0], "y": center[1], "z": center[2], "u": center[3], "v": center[4], "w": center[5]})
        models.append({
            "moca_aid": aid,
            "moca_bsmdid": 999,
            "coeff_index": 0,
            "x_cen": center[0],
            "y_cen": center[1],
            "z_cen": center[2],
            "u_cen": center[3],
            "v_cen": center[4],
            "w_cen": center[5],
            "xx_covar": scatter[0] ** 2,
            "yy_covar": scatter[1] ** 2,
            "zz_covar": scatter[2] ** 2,
            "uu_covar": scatter[3] ** 2,
            "vv_covar": scatter[4] ** 2,
            "ww_covar": scatter[5] ** 2,
            "xy_covar": 0,
            "xz_covar": 0,
            "yz_covar": 0,
            "uv_covar": 0,
            "uw_covar": 0,
            "vw_covar": 0,
        })
        for index in range(48):
            coords = center + rng.normal(0, scatter)
            bp_rp = float(np.clip(rng.normal(1.7 + 0.12 * aid_index, 0.55), 0.1, 4.2))
            g_rp = float(np.clip(0.18 + 0.42 * bp_rp + rng.normal(0, 0.05), -0.05, 2.2))
            abs_g = 4.0 + 3.25 * bp_rp + 0.42 * bp_rp * bp_rp + rng.normal(0, 0.28)
            plx = float(rng.uniform(7, 80))
            distance = 1000.0 / plx
            gmag = abs_g + 5 * math.log10(distance) - 5
            oid = 880000 + aid_index * 1000 + index
            mtid = selection["mtids"][index % max(1, len(selection["mtids"]))]
            members.append({
                "designation": f"Mock {aid} member {index:02d}",
                "moca_aid": aid,
                "moca_mtid": mtid,
                "spt": ["K7", "M2", "M5", "L0"][index % 4],
                "moca_oid": oid,
                "gmag": round(float(gmag), 5),
                "bmag": round(float(gmag + bp_rp - g_rp), 5),
                "rmag": round(float(gmag - g_rp), 5),
                "plx": round(plx, 5),
                "dmod": round(5 * math.log10(distance) - 5, 5),
                "dr3_ruwe": round(float(rng.uniform(0.8, 1.8)), 4),
                "x": round(coords[0], 5),
                "y": round(coords[1], 5),
                "z": round(coords[2], 5),
                "u": round(coords[3], 5),
                "v": round(coords[4], 5),
                "w": round(coords[5], 5),
                "x_opt": round(0.65 * coords[0] + 0.35 * center[0], 5),
                "y_opt": round(0.65 * coords[1] + 0.35 * center[1], 5),
                "z_opt": round(0.65 * coords[2] + 0.35 * center[2], 5),
                "u_opt": round(0.65 * coords[3] + 0.35 * center[3], 5),
                "v_opt": round(0.65 * coords[4] + 0.35 * center[4], 5),
                "w_opt": round(0.65 * coords[5] + 0.35 * center[5], 5),
                "prot_days": round(float(0.45 + 12.0 / (1 + bp_rp) + rng.normal(0, 0.45)), 5),
                "gaia_act": round(float(0.004 + 0.08 * np.exp(-bp_rp / 2.0) + rng.normal(0, 0.008)), 6),
                "ewli": round(float(np.clip(650 - 170 * bp_rp + rng.normal(0, 45), 0, 760)), 5),
                "ewha": round(float(-(0.6 + 4.5 * np.exp(-bp_rp / 1.6) + rng.normal(0, 0.55))), 5),
            })
    members_df = _moca_explorer_add_derived_columns(pd.DataFrame(members))
    objects_df = pd.DataFrame()
    if selection["oids"]:
        objects = []
        for oid in selection["oids"]:
            objects.append({
                "designation": f"Highlighted mock oid{oid}",
                "moca_aid": "N/A",
                "moca_mtid": "N/A",
                "spt": "L/T",
                "moca_oid": int(oid),
                "gmag": 15.0,
                "bmag": 17.2,
                "rmag": 14.6,
                "plx": 60.0,
                "dmod": 1.109,
                "dr3_ruwe": 1.05,
                "x": 8.0,
                "y": -11.0,
                "z": 19.0,
                "u": -7.0,
                "v": -18.0,
                "w": -6.5,
                "prot_days": 3.8,
                "gaia_act": 0.026,
                "ewli": 190,
                "ewha": -4.2,
            })
        objects_df = _moca_explorer_add_derived_columns(pd.DataFrame(objects))

    x_gr = np.linspace(-0.1, 2.4, 100)
    x_br = np.linspace(0.1, 4.2, 100)
    seq = lambda seqid, tag, x, y, color, dash="solid": {
        "moca_seqid": seqid,
        "tag": tag,
        "color": color,
        "width": 2,
        "style": dash,
        "x": np.round(x, 5).tolist(),
        "y": np.round(y, 5).tolist(),
    }
    sequences = {
        "cmd": [
            seq("mock_cmd_field", "Field", x_gr, 4.5 + 6.0 * x_gr, "#555555"),
            seq("mock_cmd_young", "Young sequence", x_gr, 3.7 + 5.7 * x_gr, "#0072b2", "dash"),
        ],
        "cmdField": [
            seq("mock_cmd_fieldscatter", "Field stars", x_gr, 4.5 + 6.0 * x_gr + 0.45 * np.sin(4 * x_gr), "#7d8791"),
        ],
        "prot": [seq("mock_prot", "Mock rotation", x_br, 12 / (1 + x_br), "#009e73")],
        "gaiaAct": [seq("mock_act", "Mock activity", x_br, 0.09 * np.exp(-x_br / 2), "#d55e00")],
        "ewha": [seq("mock_ewha", "Mock H-alpha", x_br, -(0.8 + 4.5 * np.exp(-x_br / 1.5)), "#cc79a7")],
        "ewli": [seq("mock_ewli", "Mock lithium", x_br, np.clip(650 - 170 * x_br, 0, None), "#e69f00")],
    }
    sptn = np.linspace(-35, 5, 100)
    spt_axis = [
        {"moca_seqid": "sptn_grp_gaiaedr3_field", "xdata": float(value), "ydata": float(0.2 + (value + 35) * 0.045)}
        for value in sptn
    ] + [
        {"moca_seqid": "sptn_bprp_gaiaedr3_field", "xdata": float(value), "ydata": float(0.45 + (value + 35) * 0.09)}
        for value in sptn
    ]
    return {
        "selection": selection,
        "members": _records(members_df),
        "objects": _records(objects_df),
        "models": _records(pd.DataFrame(models)),
        "sequences": sequences,
        "labels": labels,
        "sptAxis": spt_axis,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "member_count": len(members_df),
            "object_count": len(objects_df),
            "model_count": len(models),
            "sequence_count": sum(len(value) for value in sequences.values()),
            "label_count": len(labels),
            "spt_axis_count": len(spt_axis),
            "truncated": False,
            "max_objects": selection["max_objects"],
            "query_seconds": 0,
            "legacy_source": "deprecated/moca_explorer.py",
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


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
        age_myr = round(float(10 ** (0.7 + 0.28 * aid_index)), 1)
        center = np.asarray([
            -30 + 45 * aid_index,
            20 - 25 * aid_index,
            -10 + 12 * aid_index,
            XYZUVW_C_VALUE * (-10 + 3 * aid_index),
            XYZUVW_C_VALUE * (-18 + 2 * aid_index),
            XYZUVW_C_VALUE * (-6 + aid_index),
        ], dtype=float)
        spread = np.asarray([18, 12, 10, 4 * XYZUVW_C_VALUE, 3 * XYZUVW_C_VALUE, 2.5 * XYZUVW_C_VALUE], dtype=float)
        label = {"moca_aid": aid, "age_myr": age_myr, "x": center[0], "y": center[1], "z": center[2], "u": center[3], "v": center[4], "w": center[5]}
        labels.append(label)
        models.append({
            "moca_aid": aid,
            "age_myr": age_myr,
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
                "age_myr": age_myr,
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
                    WHERE moca_oid = :target
                        AND designation IS NOT NULL
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
                    SELECT aid_rows.moca_aid, ma.name
                    FROM (
                        SELECT DISTINCT daa.moca_aid
                        FROM data_association_ages daa
                        WHERE daa.moca_aid IS NOT NULL
                    ) aid_rows
                    LEFT JOIN moca_associations ma
                        ON ma.moca_aid = aid_rows.moca_aid
                    ORDER BY aid_rows.moca_aid
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


def _legacy_rv_dataset_value(target_name: Any, template_name: Any, pipeline_version: Any) -> str:
    return "|".join(str(value or "") for value in (target_name, template_name, pipeline_version))


def _legacy_rv_dataset_selection(args: dict[str, Any]) -> tuple[str, str, str] | None:
    target_name = args.get("target_name") or args.get("target")
    template_name = args.get("template_name") or args.get("template")
    pipeline_version = args.get("pipeline_version") or args.get("version")
    if target_name and template_name and pipeline_version:
        return str(target_name), str(template_name), str(pipeline_version)

    raw_dataset = args.get("dataset") or args.get("rv_dataset")
    if not raw_dataset:
        return None
    parts = str(raw_dataset).split("|", 2)
    if len(parts) != 3 or not all(parts):
        return None
    return parts[0], parts[1], parts[2]


def _legacy_rv_cache_key(args: dict[str, Any], *parts: Any) -> str:
    return "|".join([_spt_db_cache_key(args), "legacy-radial-velocities", *[str(part) for part in parts]])


def _legacy_rv_option_from_row(row: dict[str, Any]) -> dict[str, Any]:
    value = _legacy_rv_dataset_value(row.get("target_name"), row.get("template_name"), row.get("pipeline_version"))
    count = row.get("row_count")
    suffix = f" ({count} segments)" if count is not None else ""
    return {
        "value": value,
        "label": f"{value}{suffix}",
        "target_name": row.get("target_name"),
        "template_name": row.get("template_name"),
        "pipeline_version": row.get("pipeline_version"),
        "row_count": count,
        "moca_oid": row.get("moca_oid"),
        "moca_specid": row.get("moca_specid"),
        "moca_instid": row.get("moca_instid"),
    }


def _mock_legacy_rv_options() -> dict[str, Any]:
    rows = [
        {
            "target_name": "target_13510",
            "template_name": "sonora_mock_template_a.fits",
            "pipeline_version": "legacy_mock_v1",
            "row_count": 42,
            "moca_oid": 602,
            "moca_specid": 13510,
            "moca_instid": "spex_irtf",
        },
        {
            "target_name": "target_450",
            "template_name": "sonora_mock_template_b.fits",
            "pipeline_version": "legacy_mock_v2",
            "row_count": 36,
            "moca_oid": 10995,
            "moca_specid": 450,
            "moca_instid": "nires_keck",
        },
    ]
    options = [_legacy_rv_option_from_row(row) for row in rows]
    return {
        "options": options,
        "value": options[0]["value"],
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "dataset_count": len(options),
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _mock_legacy_rv_payload(args: dict[str, Any]) -> dict[str, Any]:
    selection = _legacy_rv_dataset_selection(args) or ("target_13510", "sonora_mock_template_a.fits", "legacy_mock_v1")
    target_name, template_name, pipeline_version = selection
    seed = int(hashlib.sha1(_legacy_rv_dataset_value(*selection).encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    instid = "spex_irtf" if "13510" in target_name else "nires_keck"
    specid = 13510 if "13510" in target_name else 450
    oid = 602 if specid == 13510 else 10995
    n_rows = 42 if specid == 13510 else 36
    base_rv = -18.4 if specid == 13510 else 12.7
    rows: list[dict[str, Any]] = []
    for index in range(n_rows):
        wave_min = 0.86 + 0.034 * index
        wave_max = wave_min + 0.045
        rv_unc = float(rng.uniform(0.55, 2.2))
        data_contrast = float(rng.uniform(0.018, 0.09))
        model_contrast = float(rng.uniform(0.14, 0.42))
        lsf = float(rng.normal(1.12, 0.08))
        if index in {6, 24}:
            data_contrast = 0.004
        if index in {14}:
            model_contrast = 0.045
        if index in {31}:
            lsf = 1.72
        if index in {38} and n_rows > 40:
            rv_unc = 0.0
        rows.append({
            "id": 900000 + index,
            "moca_oid": oid,
            "moca_instid": instid,
            "moca_specid": specid,
            "moca_fsid": 9100 + index,
            "pipeline_version": pipeline_version,
            "target_name": target_name,
            "template_name": template_name,
            "berv_kms": 18.233,
            "berv_kms_unc": 0.013,
            "order_number": 1 + index // 7,
            "window_number": 1 + (index // 2) % 4,
            "segment_number": index + 1,
            "wave_min": round(wave_min, 5),
            "wave_max": round(wave_max, 5),
            "segment_wavelength": round((wave_min + wave_max) / 2, 5),
            "nwindows": 7,
            "nsegments": n_rows,
            "npoints": int(rng.integers(45, 140)),
            "radial_velocity_kms": round(base_rv + 1.3 * math.sin(index / 4.7) + float(rng.normal(0, rv_unc * 0.55)), 4),
            "radial_velocity_kms_unc": round(rv_unc, 4),
            "origin": "mock_mcmc_rv_pipeline",
            "blaze0": round(float(rng.normal(-0.03, 0.08)), 4),
            "blaze0_unc": round(float(rng.uniform(0.01, 0.05)), 4),
            "blaze1": round(float(rng.normal(0.02, 0.08)), 4),
            "blaze1_unc": round(float(rng.uniform(0.01, 0.05)), 4),
            "vsini_kms": round(float(rng.uniform(4, 32)), 4),
            "vsini_kms_unc": round(float(rng.uniform(0.4, 3.4)), 4),
            "lsf": round(lsf, 4),
            "lsf_unc": round(float(rng.uniform(0.01, 0.07)), 4),
            "best_chi2": round(float(rng.uniform(0.8, 2.4)), 4),
            "lnp_avg": round(float(rng.normal(-1240, 40)), 4),
            "lnp_mad": round(float(rng.uniform(4, 18)), 4),
            "lnp_std": round(float(rng.uniform(8, 28)), 4),
            "lnp_median": round(float(rng.normal(-1235, 40)), 4),
            "lnp_max": round(float(rng.normal(-1210, 35)), 4),
            "mean_acceptance_rate": round(float(rng.uniform(0.14, 0.42)), 5),
            "mean_finite_fraction": round(float(rng.uniform(0.91, 1.0)), 5),
            "mean_outofbounds_fraction": round(float(rng.uniform(0.0, 0.07)), 5),
            "parscale_rv": 25.0,
            "rv_min_bound": -150.0,
            "rv_max_bound": 150.0,
            "niter_mcmc": 8000,
            "nburnin_mcmc": 2000,
            "nchains_mcmc": 24,
            "model_contrast": round(model_contrast, 5),
            "nmodel_10p_contrast": int(rng.integers(18, 95)),
            "data_contrast": round(data_contrast, 5),
            "model_fit_url": "",
            "ignored": 0,
            "comments": "Synthetic legacy RV row for local smoke testing",
        })
    dataset_info = _legacy_rv_dataset_info(rows[0] if rows else {})
    return {
        "selection": {
            "dataset": _legacy_rv_dataset_value(*selection),
            "target_name": target_name,
            "template_name": template_name,
            "pipeline_version": pipeline_version,
        },
        "datasetInfo": dataset_info,
        "rows": rows,
        "images": {"chi2_url": "", "best_model_fit_url": ""},
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "row_count": len(rows),
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _load_legacy_rv_options_from_db(args: dict[str, Any]) -> dict[str, Any]:
    cache_key = _legacy_rv_cache_key(args, "options")
    now = time.time()
    cached = _LEGACY_RV_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        rows = _records(_read_sql(conn, """
            SELECT
                target_name,
                template_name,
                pipeline_version,
                COUNT(*) AS row_count,
                MIN(moca_oid) AS moca_oid,
                MIN(moca_specid) AS moca_specid,
                MIN(moca_instid) AS moca_instid
            FROM pcat_mcmc_rv_pipeline
            WHERE target_name IS NOT NULL
                AND template_name IS NOT NULL
                AND pipeline_version IS NOT NULL
                AND LOWER(CONCAT_WS('|', target_name, template_name, pipeline_version)) NOT LIKE '%spirou%'
            GROUP BY target_name, template_name, pipeline_version
            ORDER BY target_name, template_name, pipeline_version
        """))
    options = [_legacy_rv_option_from_row(row) for row in rows]
    payload = {
        "options": options,
        "value": options[0]["value"] if options else None,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "dataset_count": len(options),
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _LEGACY_RV_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _legacy_rv_dataset_info(first_row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "pipeline_version",
        "target_name",
        "template_name",
        "moca_oid",
        "moca_specid",
        "moca_instid",
        "berv_kms",
        "berv_kms_unc",
        "nwindows",
        "nsegments",
        "npoints",
        "origin",
        "parscale_rv",
        "rv_min_bound",
        "rv_max_bound",
        "niter_mcmc",
        "nburnin_mcmc",
        "nchains_mcmc",
    ]
    return {key: first_row.get(key) for key in keys if first_row.get(key) is not None}


def _legacy_rv_specid_from_selection(target_name: str, rows: list[dict[str, Any]]) -> int | None:
    for row in rows:
        try:
            if row.get("moca_specid") is not None:
                return int(row["moca_specid"])
        except (TypeError, ValueError):
            pass
    parts = str(target_name or "").split("_")
    for part in parts:
        if part.isdigit():
            return int(part)
    return None


def _legacy_rv_model_grid_images(conn, specid: int | None, template_name: str) -> dict[str, str]:
    if specid is None or not template_name:
        return {"chi2_url": "", "best_model_fit_url": ""}
    rows = _records(_read_sql(conn, """
        SELECT
            mfs.description,
            MIN(mf.url) AS url
        FROM calc_model_grid_fits cmgf
        JOIN data_model_grid_files dmgf
            ON dmgf.moca_mgridfileid = cmgf.moca_mgridfileid
        JOIN mechanics_file_sets mfs
            ON mfs.moca_fsid = cmgf.moca_fsid
        JOIN mechanics_files mf
            ON mf.moca_fid = mfs.moca_fid
        WHERE cmgf.moca_specid = :specid
            AND CONCAT(cmgf.moca_mgridid, '_', dmgf.file_name) = :template_name
            AND (mfs.description = 'All model fit chi2' OR mfs.description = 'Best model fit')
        GROUP BY mfs.description
    """, {"specid": int(specid), "template_name": template_name}))
    by_description = {str(row.get("description") or ""): str(row.get("url") or "") for row in rows}
    return {
        "chi2_url": by_description.get("All model fit chi2", ""),
        "best_model_fit_url": by_description.get("Best model fit", ""),
    }


def _load_legacy_rv_dataset_from_db(args: dict[str, Any]) -> dict[str, Any]:
    selection = _legacy_rv_dataset_selection(args)
    if selection is None:
        options_payload = _load_legacy_rv_options_from_db(args)
        default_value = options_payload.get("value")
        if default_value:
            selection = _legacy_rv_dataset_selection({"dataset": default_value})
    if selection is None:
        return {
            "selection": {},
            "datasetInfo": {},
            "rows": [],
            "images": {"chi2_url": "", "best_model_fit_url": ""},
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "row_count": 0,
                "private_db": _is_private_db(args),
            },
            "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
        }

    target_name, template_name, pipeline_version = selection
    dataset_value = _legacy_rv_dataset_value(target_name, template_name, pipeline_version)
    cache_key = _legacy_rv_cache_key(args, "data", hashlib.sha1(dataset_value.encode("utf-8")).hexdigest())
    now = time.time()
    cached = _LEGACY_RV_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        rows = _records(_read_sql(conn, """
            SELECT
                rv.id,
                rv.moca_oid,
                rv.moca_instid,
                rv.moca_specid,
                rv.moca_fsid,
                rv.pipeline_version,
                rv.target_name,
                rv.template_name,
                rv.berv_kms,
                rv.berv_kms_unc,
                rv.order_number,
                rv.window_number,
                rv.segment_number,
                rv.wave_min,
                rv.wave_max,
                ((rv.wave_min + rv.wave_max) / 2.0) AS segment_wavelength,
                rv.nwindows,
                rv.nsegments,
                rv.npoints,
                rv.radial_velocity_kms,
                rv.radial_velocity_kms_unc,
                rv.origin,
                rv.blaze0,
                rv.blaze0_unc,
                rv.blaze1,
                rv.blaze1_unc,
                rv.vsini_kms,
                rv.vsini_kms_unc,
                rv.lsf,
                rv.lsf_unc,
                rv.best_chi2,
                rv.lnp_avg,
                rv.lnp_mad,
                rv.lnp_std,
                rv.lnp_median,
                rv.lnp_max,
                rv.mean_acceptance_rate,
                rv.mean_finite_fraction,
                rv.mean_outofbounds_fraction,
                rv.parscale_rv,
                rv.rv_min_bound,
                rv.rv_max_bound,
                rv.niter_mcmc,
                rv.nburnin_mcmc,
                rv.nchains_mcmc,
                rv.model_contrast,
                rv.nmodel_10p_contrast,
                rv.data_contrast,
                rv.ignored,
                rv.comments,
                fit.model_fit_url
            FROM pcat_mcmc_rv_pipeline rv
            LEFT JOIN (
                SELECT
                    mfs.moca_fsid,
                    MIN(mf.url) AS model_fit_url
                FROM mechanics_file_sets mfs
                JOIN mechanics_files mf
                    ON mf.moca_fid = mfs.moca_fid
                WHERE mfs.description = 'MCMC RV model fit'
                GROUP BY mfs.moca_fsid
            ) fit
                ON fit.moca_fsid = rv.moca_fsid
            WHERE rv.target_name = :target_name
                AND rv.template_name = :template_name
                AND rv.pipeline_version = :pipeline_version
            ORDER BY rv.order_number, rv.window_number, rv.segment_number, rv.id
        """, {
            "target_name": target_name,
            "template_name": template_name,
            "pipeline_version": pipeline_version,
        }))
        specid = _legacy_rv_specid_from_selection(target_name, rows)
        images = _legacy_rv_model_grid_images(conn, specid, template_name)

    dataset_info = _legacy_rv_dataset_info(rows[0] if rows else {
        "target_name": target_name,
        "template_name": template_name,
        "pipeline_version": pipeline_version,
    })
    payload = {
        "selection": {
            "dataset": dataset_value,
            "target_name": target_name,
            "template_name": template_name,
            "pipeline_version": pipeline_version,
        },
        "datasetInfo": dataset_info,
        "rows": rows,
        "images": images,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "row_count": len(rows),
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _LEGACY_RV_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


RVBAM_DEFAULT_MAX_SAMPLES = int(os.environ.get("RVBAM_EXPLORER_MAX_SAMPLES", "1800"))
RVBAM_HARD_MAX_SAMPLES = int(os.environ.get("RVBAM_EXPLORER_HARD_MAX_SAMPLES", "8000"))
RVBAM_ARRAY_CACHE_SECONDS = int(os.environ.get("RVBAM_EXPLORER_ARRAY_CACHE_SECONDS", "900"))
RVBAM_ARRAY_CACHE_MAX_ITEMS = int(os.environ.get("RVBAM_EXPLORER_ARRAY_CACHE_ITEMS", "8"))
RVBAM_VENDOR_PACKAGE_DIR = BASE_DIR / "vendor"
RVBAM_SOURCE_PACKAGE_DIR = Path("/Users/jonathan/Documents/Python/Python_Packages/rvbam")
RVBAM_DEFAULT_PACKAGE_DIR = RVBAM_VENDOR_PACKAGE_DIR if (RVBAM_VENDOR_PACKAGE_DIR / "rvbam").is_dir() else RVBAM_SOURCE_PACKAGE_DIR
RVBAM_PACKAGE_DIR = Path(os.environ.get("RVBAM_PACKAGE_DIR") or str(RVBAM_DEFAULT_PACKAGE_DIR))
RVBAM_DEFAULT_LOCAL_MODEL_DIRS = (
    Path(os.environ.get("RVBAM_MODEL_GRID_HDF5_DIR", "/Volumes/T3_ext/model_grids_hdf5")),
    Path("/Volumes/T3_EXT/model_grids_hdf5"),
    Path("/Users/jonathan/Documents/Planetarium_Projects/Science/model_grids_hdf5"),
)
RVBAM_REBUILT_FIT_AUTO_SCALE_VERSION = "rvbam-diagnostic-v1"
RVBAM_REBUILT_FIT_LOG_OVERSAMPLE = 10.0
RVBAM_REBUILT_FIT_CONV_GRID = "data"
RVBAM_REQUIRED_TABLES = (
    "pcat_rv_sampling_runs",
    "pcat_rv_sampling_segments",
    "pcat_sampling_runs",
    "pcat_sampling_parameters",
    "pcat_sampling_payloads",
)
RVBAM_RV_CONTENT_MODEL_POINTS = int(os.environ.get("RVBAM_RV_CONTENT_MODEL_POINTS", "2048"))
RVBAM_RV_CONTENT_OUTLIER_FRACTION = 5.0 / 113.0
RVBAM_BERV_METADATA_KEYS = {
    "berv_source",
    "berv_kms",
    "berv_epoch_mjd",
    "moca_berv_corrected",
    "spacecraft_rv_corrected",
    "berv_coord_source",
    "berv_location",
    "berv_sign",
}
RVBAM_BERV_METADATA_ALIASES = {
    "moca_berv_corected": "moca_berv_corrected",
    "berv_corected": "moca_berv_corrected",
    "berv_corrected": "moca_berv_corrected",
}


def _rvbam_model_grid_dirs_from_env() -> list[Path]:
    raw = os.environ.get("RVBAM_MODEL_GRID_HDF5_DIRS", "")
    return [Path(item).expanduser() for item in raw.split(os.pathsep) if item.strip()]


def _rvbam_unique_paths(paths: list[Path] | tuple[Path, ...]) -> tuple[Path, ...]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        expanded = Path(path).expanduser()
        key = os.path.normcase(str(expanded))
        if key in seen:
            continue
        seen.add(key)
        out.append(expanded)
    return tuple(out)


RVBAM_LOCAL_MODEL_DIRS = _rvbam_unique_paths([
    *_rvbam_model_grid_dirs_from_env(),
    *RVBAM_DEFAULT_LOCAL_MODEL_DIRS,
])
RVBAM_LOCAL_MODEL_DIR = RVBAM_LOCAL_MODEL_DIRS[0]


def _prepare_rvbam_imports() -> None:
    import sys

    candidates = [RVBAM_PACKAGE_DIR, RVBAM_VENDOR_PACKAGE_DIR, RVBAM_SOURCE_PACKAGE_DIR]
    seen: set[Path] = set()
    existing_candidates: list[Path] = []
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen or not (resolved / "rvbam").is_dir():
            continue
        seen.add(resolved)
        existing_candidates.append(resolved)

    for package_dir in reversed(existing_candidates):
        rvbam_path = str(package_dir)
        if rvbam_path not in sys.path:
            sys.path.insert(0, rvbam_path)

    active_package_dir = existing_candidates[0] if existing_candidates else RVBAM_PACKAGE_DIR

    if sys.version_info >= (3, 10):
        return

    def ensure_package(package_name: str, directory: Path) -> types.ModuleType:
        existing = sys.modules.get(package_name)
        if existing is not None:
            return existing
        parent_name, _, attr_name = package_name.rpartition(".")
        parent_module = ensure_package(parent_name, directory.parent) if parent_name else None
        module = types.ModuleType(package_name)
        init_path = directory / "__init__.py"
        module.__file__ = str(init_path) if init_path.is_file() else None
        module.__package__ = package_name
        module.__path__ = [str(directory)]
        sys.modules[package_name] = module
        if parent_module is not None:
            setattr(parent_module, attr_name, module)
        return module

    ensure_package("rvbam", active_package_dir / "rvbam")
    ensure_package("rvbam.grid", active_package_dir / "rvbam" / "grid")
    ensure_package("rvbam.db", active_package_dir / "rvbam" / "db")
    ensure_package("rvbam.model", active_package_dir / "rvbam" / "model")
    ensure_package("rvbam.plots", active_package_dir / "rvbam" / "plots")

    for module_name, relative_path in (
        ("rvbam.grid.axes", "rvbam/grid/axes.py"),
        ("rvbam.db.atmosphere_repo", "rvbam/db/atmosphere_repo.py"),
    ):
        if module_name in sys.modules:
            continue
        path = active_package_dir / relative_path
        if not path.is_file():
            continue
        parent_name, _, attr_name = module_name.rpartition(".")
        parent_module = sys.modules.get(parent_name)
        source = path.read_text(encoding="utf-8")
        first_lines = source.splitlines()[:5]
        if "from __future__ import annotations" not in first_lines:
            source = "from __future__ import annotations\n" + source
        module = types.ModuleType(module_name)
        module.__file__ = str(path)
        module.__package__ = parent_name
        sys.modules[module_name] = module
        if parent_module is not None:
            setattr(parent_module, attr_name, module)
        exec(compile(source, str(path), "exec"), module.__dict__)


def _rvbam_cache_key(args: dict[str, Any], *parts: Any) -> str:
    return "|".join([_spt_db_cache_key(args), "rvbam-explorer", *[str(part) for part in parts]])


def _rvbam_int_arg(args: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = args.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _rvbam_segment_count_filter_arg(args: dict[str, Any], mode: str, *keys: str) -> int | None:
    for key in keys:
        value = args.get(key)
        if value in (None, ""):
            continue
        number = _safe_float(value)
        if number is None or number < 0:
            return None
        if mode == "max":
            return int(math.floor(number))
        return int(math.ceil(number))
    return None


def _rvbam_limit_arg(args: dict[str, Any], key: str, default: int, hard_max: int) -> int:
    value = _rvbam_int_arg(args, key)
    if value is None:
        return default
    return max(1, min(int(value), hard_max))


def _rvbam_parse_wavelength_coverage(raw_value: Any) -> list[tuple[float, float]]:
    """Parse wavelength coverage filters in microns.

    Accepted examples: ``1.0-1.35``, ``1.0:1.35``, ``1.0 1.35``,
    ``1.0, 1.35``, or a list of those ranges. A single value is treated as a
    zero-width coverage point.
    """
    raw = str(raw_value or "").strip()
    if not raw:
        return []
    ranges: list[tuple[float, float]] = []
    number_pattern = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
    pair_pattern = re.compile(
        rf"({number_pattern})\s*(?:-|:|,|\s+)\s*({number_pattern})"
    )
    for match in pair_pattern.finditer(raw):
        try:
            left = float(match.group(1))
            right = float(match.group(2))
        except ValueError:
            continue
        if not (math.isfinite(left) and math.isfinite(right)):
            continue
        lo, hi = sorted((left, right))
        ranges.append((lo, hi))
    if ranges:
        return ranges

    for value in re.findall(number_pattern, raw):
        try:
            number = float(value)
        except ValueError:
            continue
        if math.isfinite(number):
            ranges.append((number, number))
    return ranges


def _rvbam_wavelength_coverage_ranges(args: Any) -> list[tuple[float, float]]:
    raw_value = (
        args.get("wavelength_coverage")
        or args.get("wv_coverage")
        or args.get("coverage")
        or args.get("wavelength")
        or ""
    )
    return _rvbam_parse_wavelength_coverage(raw_value)


def _rvbam_segment_wavelength_filter_ranges(args: Any) -> list[tuple[float, float]]:
    raw_value = (
        args.get("segment_wavelength")
        or args.get("segment_wavelength_range")
        or args.get("segment_wv")
        or args.get("segment_wv_range")
        or ""
    )
    ranges: list[tuple[float, float]] = []
    for left, right in _rvbam_parse_wavelength_coverage(raw_value):
        lo = _rvbam_wavelength_micron(left)
        hi = _rvbam_wavelength_micron(right)
        if lo is None or hi is None:
            continue
        lo, hi = sorted((lo, hi))
        ranges.append((lo, hi))
    return ranges


def _rvbam_has_literature_rv_filter(args: Any) -> bool:
    return _as_bool(
        args.get("has_literature_rv")
        or args.get("literature_rv")
        or args.get("lit_rv")
    )


def _rvbam_wavelength_micron(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number / 10000.0 if abs(number) > 1000 else number


def _rvbam_comment_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return _pythonize(value)
    text = str(value).strip()
    if not text:
        return ""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    lowered = text.lower()
    if lowered in {"none", "null", "nan"}:
        return None
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    try:
        if re.fullmatch(r"[-+]?\d+", text):
            return int(text)
        if re.fullmatch(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", text):
            return _pythonize(float(text))
    except ValueError:
        pass
    return text


def _rvbam_parse_comment_metadata(comments: Any) -> dict[str, Any]:
    if not comments:
        return {}
    if isinstance(comments, Mapping):
        return {
            str(key).strip(): _rvbam_comment_value(value)
            for key, value in comments.items()
            if str(key).strip()
        }
    raw = str(comments).strip()
    if not raw:
        return {}

    metadata: dict[str, Any] = {}
    if raw.startswith("{") and raw.endswith("}"):
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError):
            decoded = None
        if isinstance(decoded, Mapping):
            metadata.update(_rvbam_parse_comment_metadata(decoded))

    pattern = re.compile(
        r"(?<![A-Za-z0-9_.-])([A-Za-z][A-Za-z0-9_]*)\s*=\s*"
        r"(?:\"([^\"]*)\"|'([^']*)'|([^;,\n\r]+))"
    )
    for match in pattern.finditer(raw):
        key = match.group(1).strip()
        value = next(
            group
            for group in (match.group(2), match.group(3), match.group(4))
            if group is not None
        )
        metadata[key] = _rvbam_comment_value(value)
    return metadata


def _rvbam_berv_metadata_from_comments(*comments: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for comment in comments:
        parsed = _rvbam_parse_comment_metadata(comment)
        for raw_key, value in parsed.items():
            key = RVBAM_BERV_METADATA_ALIASES.get(str(raw_key).strip(), str(raw_key).strip())
            if key not in RVBAM_BERV_METADATA_KEYS:
                continue
            if value is None or value == "":
                continue
            metadata.setdefault(key, value)
    return metadata


def _rvbam_segments_cover_wavelength_ranges(
    segments: Sequence[Mapping[str, Any]], ranges: Sequence[tuple[float, float]]
) -> bool:
    for segment in segments:
        seg_min = _rvbam_wavelength_micron(segment.get("wv_min"))
        seg_max = _rvbam_wavelength_micron(segment.get("wv_max"))
        if seg_min is None or seg_max is None:
            continue
        seg_min, seg_max = sorted((seg_min, seg_max))
        for lo, hi in ranges:
            if seg_min <= hi and seg_max >= lo:
                return True
    return False


def _rvbam_segment_timestamp_summary(
    segments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    created_values = [
        segment.get("created_timestamp")
        for segment in segments
        if segment.get("created_timestamp")
    ]
    modified_values = [
        segment.get("modified_timestamp")
        for segment in segments
        if segment.get("modified_timestamp")
    ]
    summary: dict[str, Any] = {
        "oldest_segment_created_timestamp": min(created_values)
        if created_values
        else None,
        "latest_segment_created_timestamp": max(created_values)
        if created_values
        else None,
        "latest_segment_modified_timestamp": max(modified_values)
        if modified_values
        else None,
    }
    return summary


def _rvbam_literature_exists_sql(conn: Any, private: bool) -> str:
    if not _db_table_exists(conn, "calc_radial_velocities_combined"):
        return "0 = 1"

    crv_public_clause = "" if private else "AND crv.is_public = 1"
    object_exists = f"""
        EXISTS (
            SELECT 1
            FROM calc_radial_velocities_combined AS crv
            WHERE crv.moca_oid = r.moca_oid
              AND crv.radial_velocity_kms IS NOT NULL
              AND COALESCE(crv.ignored, 0) = 0
              {crv_public_clause}
        )
    """
    if not _db_table_exists(conn, "moca_companions"):
        return object_exists

    companion_public_clause = "" if private else "AND COALESCE(mc.is_public, 0) = 1"
    host_exists = f"""
        EXISTS (
            SELECT 1
            FROM moca_companions AS mc
            JOIN calc_radial_velocities_combined AS crv
              ON crv.moca_oid = mc.moca_oid_parent
            WHERE mc.moca_oid_child = r.moca_oid
              AND crv.radial_velocity_kms IS NOT NULL
              AND COALESCE(mc.ignored, 0) = 0
              AND COALESCE(crv.ignored, 0) = 0
              {companion_public_clause}
              {crv_public_clause}
        )
    """
    return f"({object_exists} OR {host_exists})"


def _rvbam_required_tables_available(conn) -> tuple[bool, list[str]]:
    missing: list[str] = []
    unknown: list[str] = []
    for table in RVBAM_REQUIRED_TABLES:
        cache_key = _db_metadata_cache_key(conn, table)
        cached = _DB_TABLE_EXISTS_CACHE.get(cache_key)
        if cached is None:
            unknown.append(table)
        elif not cached:
            missing.append(table)

    if unknown:
        placeholders: list[str] = []
        params: dict[str, Any] = {}
        for index, table in enumerate(unknown):
            key = f"rvbam_required_table_{index}"
            placeholders.append(f":{key}")
            params[key] = table
        rows = conn.execute(text(f"""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
                AND table_name IN ({", ".join(placeholders)})
        """), params).fetchall()
        found = {str(row[0]) for row in rows}
        for table in unknown:
            exists = table in found
            _DB_TABLE_EXISTS_CACHE[_db_metadata_cache_key(conn, table)] = exists
            if not exists:
                missing.append(table)

    return not missing, missing


def _rvbam_available_columns(conn, table_name: str) -> set[str]:
    cache_key = _db_metadata_cache_key(conn, table_name)
    cached = _DB_COLUMNS_CACHE.get(cache_key)
    if cached is not None:
        return set(cached)
    rows = conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
            AND table_name = :table_name
    """), {"table_name": table_name}).fetchall()
    columns = {str(row[0]) for row in rows}
    _DB_COLUMNS_CACHE[cache_key] = set(columns)
    return columns


def _rvbam_wavelength_angstrom(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number if abs(number) > 1000 else number * 10000.0


def _rvbam_intrinsic_flux_contrast(flux: np.ndarray, flux_unc: np.ndarray) -> float | None:
    values = np.asarray(flux, dtype=float)
    errors = np.asarray(flux_unc, dtype=float)
    finite = np.isfinite(values) & np.isfinite(errors) & (errors > 0)
    if int(np.sum(finite)) < 3:
        return None
    values = values[finite]
    errors = errors[finite]
    median_flux = float(np.nanmedian(values))
    if not np.isfinite(median_flux) or median_flux == 0:
        return None
    deviations = values - median_flux
    observed_var = float(np.nanvar(deviations, ddof=1))
    noise_var = float(np.nanmean(errors ** 2))
    intrinsic_sigma = math.sqrt(max(0.0, observed_var - noise_var))
    contrast = intrinsic_sigma / abs(median_flux)
    return float(contrast) if np.isfinite(contrast) else None


def _rvbam_model_flux_content(model_flux: np.ndarray) -> tuple[float | None, int | None]:
    values = np.asarray(model_flux, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 3:
        return None, None
    high = float(np.nanpercentile(values, 99))
    low = float(np.nanpercentile(values, 1))
    if not np.isfinite(high) or high == 0:
        return None, None
    contrast = (high - low) / abs(high)
    deep_count = int(np.sum(values <= high * 0.9))
    return (float(contrast) if np.isfinite(contrast) else None, deep_count)


def _rvbam_residual_intrinsic_sigma(residual: np.ndarray, flux_unc: np.ndarray) -> float:
    values = np.asarray(residual, dtype=float)
    errors = np.asarray(flux_unc, dtype=float)
    finite = np.isfinite(values) & np.isfinite(errors) & (errors > 0)
    if int(np.sum(finite)) < 3:
        return 0.0
    values = values[finite]
    errors = errors[finite]
    observed_var = float(np.nanvar(values, ddof=1))
    noise_var = float(np.nanmean(errors ** 2))
    return math.sqrt(max(0.0, observed_var - noise_var))


def _rvbam_masked_outlier_indices(
    flux: np.ndarray,
    flux_unc: np.ndarray,
    model_flux: np.ndarray,
) -> np.ndarray:
    values = np.asarray(flux, dtype=float)
    errors = np.asarray(flux_unc, dtype=float)
    model_values = np.asarray(model_flux, dtype=float)
    finite = np.isfinite(values) & np.isfinite(errors) & (errors > 0) & np.isfinite(model_values)
    if int(np.sum(finite)) < 3:
        return np.array([], dtype=int)
    original_indices = np.nonzero(finite)[0]
    residual = values[finite] - model_values[finite]
    errors = errors[finite]
    sys_error = _rvbam_residual_intrinsic_sigma(residual, errors)
    total_sigma = np.sqrt(sys_error ** 2 + errors ** 2)
    valid = np.isfinite(total_sigma) & (total_sigma > 0)
    if not np.any(valid):
        return np.array([], dtype=int)
    nsigma = np.full(residual.shape, np.nan, dtype=float)
    nsigma[valid] = residual[valid] / total_sigma[valid]
    bad = np.nonzero(np.isfinite(nsigma) & (nsigma > 3.0))[0]
    max_outliers = int(math.ceil(RVBAM_RV_CONTENT_OUTLIER_FRACTION * int(np.sum(finite))))
    if max_outliers <= 0 or bad.size == 0:
        return np.array([], dtype=int)
    if bad.size > max_outliers:
        order = np.argsort(nsigma[bad])[::-1][:max_outliers]
        bad = bad[order]
    return original_indices[bad].astype(int)


def _rvbam_segment_ranges_angstrom(
    segments: Sequence[dict[str, Any]],
) -> list[tuple[float, float, dict[str, Any]]]:
    ranges: list[tuple[float, float, dict[str, Any]]] = []
    for segment in segments:
        wv_min = _rvbam_wavelength_angstrom(segment.get("wv_min"))
        wv_max = _rvbam_wavelength_angstrom(segment.get("wv_max"))
        if wv_min is None or wv_max is None:
            continue
        lo, hi = sorted((wv_min, wv_max))
        ranges.append((lo, hi, segment))
    return ranges


def _rvbam_enrich_segments_observed_content(
    conn: Any,
    moca_specid: Any,
    segments: Sequence[dict[str, Any]],
) -> dict[int, dict[str, np.ndarray]]:
    arrays_by_segment: dict[int, dict[str, np.ndarray]] = {}
    if not segments or moca_specid is None or not _db_table_exists(conn, "data_spectra"):
        return arrays_by_segment
    ranges = _rvbam_segment_ranges_angstrom(segments)
    if not ranges:
        return arrays_by_segment
    query_min = min(item[0] for item in ranges)
    query_max = max(item[1] for item in ranges)
    try:
        specid = int(moca_specid)
    except (TypeError, ValueError):
        return arrays_by_segment
    try:
        rows = _records(_read_sql(conn, """
            SELECT
                wavelength_angstrom,
                flux_flambda,
                flux_flambda_unc
            FROM data_spectra
            WHERE moca_specid = :moca_specid
                AND wavelength_angstrom BETWEEN :wv_min AND :wv_max
                AND flux_flambda IS NOT NULL
                AND flux_flambda_unc IS NOT NULL
                AND flux_flambda_unc > 0
            ORDER BY wavelength_angstrom
        """, {
            "moca_specid": specid,
            "wv_min": query_min,
            "wv_max": query_max,
        }))
    except Exception:
        return arrays_by_segment
    if not rows:
        return arrays_by_segment

    wavelength = np.array([float(row["wavelength_angstrom"]) for row in rows], dtype=float)
    flux = np.array([float(row["flux_flambda"]) for row in rows], dtype=float)
    flux_unc = np.array([float(row["flux_flambda_unc"]) for row in rows], dtype=float)
    snr = flux / flux_unc
    finite = np.isfinite(wavelength) & np.isfinite(snr)
    if not np.any(finite):
        return arrays_by_segment
    wavelength = wavelength[finite]
    flux = flux[finite]
    flux_unc = flux_unc[finite]
    snr = snr[finite]
    for lo, hi, segment in ranges:
        mask = (wavelength >= lo) & (wavelength <= hi)
        if not np.any(mask):
            continue
        segment_wavelength = wavelength[mask]
        segment_flux = flux[mask]
        segment_flux_unc = flux_unc[mask]
        segment_snr = snr[mask]
        segment["segment_snr_median"] = _pythonize(float(np.nanmedian(segment_snr)))
        segment["segment_snr_p10"] = _pythonize(float(np.nanpercentile(segment_snr, 10)))
        segment["segment_snr_p90"] = _pythonize(float(np.nanpercentile(segment_snr, 90)))
        segment["segment_snr_npoints"] = _pythonize(int(np.sum(np.isfinite(segment_snr))))
        data_contrast = _rvbam_intrinsic_flux_contrast(segment_flux, segment_flux_unc)
        if data_contrast is not None:
            segment["data_contrast"] = _pythonize(data_contrast)
        arrays_by_segment[id(segment)] = {
            "wavelength": segment_wavelength,
            "flux": segment_flux,
            "flux_unc": segment_flux_unc,
        }
    return arrays_by_segment


def _rvbam_parameters_by_sample_run(
    conn: Any,
    sample_run_ids: Sequence[Any],
) -> dict[int, list[dict[str, Any]]]:
    ids: list[int] = []
    for value in sample_run_ids:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed not in ids:
            ids.append(parsed)
    if not ids:
        return {}
    params = {f"sample_run_id_{index}": value for index, value in enumerate(ids)}
    placeholders = ", ".join(f":{key}" for key in params)
    rows = _records(_read_sql(conn, f"""
        SELECT
            moca_sample_run_id,
            param_name,
            param_index,
            units,
            mean_value,
            median_value,
            std_value,
            p16_value,
            p84_value,
            is_fixed,
            fixed_value,
            lower_bound,
            upper_bound
        FROM pcat_sampling_parameters
        WHERE moca_sample_run_id IN ({placeholders})
            AND COALESCE(ignored, 0) = 0
        ORDER BY moca_sample_run_id, param_index, param_name
    """, params))
    grouped: dict[int, list[dict[str, Any]]] = {value: [] for value in ids}
    for row in rows:
        sample_run_id = _safe_float(row.get("moca_sample_run_id"))
        if sample_run_id is None:
            continue
        grouped.setdefault(int(sample_run_id), []).append(row)
    return grouped


def _rvbam_scale_model_to_data(data_flux: np.ndarray, model_flux: np.ndarray) -> float:
    finite = np.isfinite(data_flux) & np.isfinite(model_flux)
    if not np.any(finite):
        return 1.0
    med_data = float(np.nanmedian(data_flux[finite]))
    med_model = float(np.nanmedian(model_flux[finite]))
    if not (np.isfinite(med_data) and np.isfinite(med_model)) or med_model == 0:
        return 1.0
    return float(med_data / med_model)


def _rvbam_enrich_segments_model_content(
    conn: Any,
    run: Mapping[str, Any],
    segments: Sequence[dict[str, Any]],
    arrays_by_segment: Mapping[int, dict[str, np.ndarray]],
) -> dict[str, Any]:
    status = _rvbam_local_model_status(run.get("moca_mgridid"), run.get("template_name"))
    meta: dict[str, Any] = {
        "model_available": bool(status.get("available")),
        "model_file": status.get("model_file"),
        "model_message": status.get("message") or "",
        "model_method": "rvbam.reconstructed_model_content.v1",
        "computed_model_segments": 0,
        "failed_model_segments": 0,
    }
    if not segments or not status.get("available"):
        return meta

    try:
        _prepare_rvbam_imports()
        from rvbam.grid.cache import SpectrumCache
        from rvbam.grid.interpolated_model import GridIndex, InterpolatedModelFetcher
        from rvbam.grid.local_models import LocalHdf5ModelStore, LocalModelConfig
        from rvbam.model.forward import ForwardModelConfig, edges_from_centers
        from rvbam.model.segment_loglike import SegmentData, SegmentLogLikelihood
    except Exception as exc:
        meta["model_available"] = False
        meta["model_message"] = f"Could not import RVBAM model helpers: {exc}"
        return meta

    sample_run_ids = [segment.get("moca_sample_run_id") for segment in segments]
    parameters_by_run = _rvbam_parameters_by_sample_run(conn, sample_run_ids)

    try:
        store = LocalHdf5ModelStore(
            conn,
            str(run.get("moca_mgridid") or ""),
            config=LocalModelConfig(base_dir=_rvbam_model_base_dir_for_status(status)),
            use_db_file_index=False,
        )
        par_list, axes, tuple_to_fileid = store.load_grid_index()
        expected = int(np.prod([len(axes.axes[p]) for p in par_list])) if par_list else 0
        require_full = not (expected and len(tuple_to_fileid) < expected)
        cache = SpectrumCache(fetch_fn=store.fetch_model_spectrum)
        fetcher = InterpolatedModelFetcher(
            None,
            str(run.get("moca_mgridid") or ""),
            GridIndex(par_list=par_list, axes=axes, tuple_to_fileid=tuple_to_fileid),
            cache=cache,
            require_full_corners=require_full,
        )
        try:
            grid_bounds = store.parameter_bounds()
        except Exception:
            grid_bounds = {}
    except Exception as exc:
        meta["model_available"] = False
        meta["model_message"] = f"Could not open local RVBAM model grid: {exc}"
        return meta

    forward_config = ForwardModelConfig(
        log_grid_oversample=RVBAM_REBUILT_FIT_LOG_OVERSAMPLE,
        conv_grid=RVBAM_REBUILT_FIT_CONV_GRID,
    )
    default_lsf_sigma_kms = _rvbam_default_rebuilt_fit_lsf_sigma_kms(dict(run))
    midpoint_theta = _rvbam_grid_midpoint_theta(par_list, axes, grid_bounds, default_lsf_sigma_kms)

    for segment in segments:
        arrays = arrays_by_segment.get(id(segment))
        if not arrays:
            continue
        wavelength = arrays["wavelength"]
        flux = arrays["flux"]
        flux_unc = arrays["flux_unc"]
        if wavelength.size < 3:
            continue
        w0 = _rvbam_wavelength_angstrom(segment.get("wv_min"))
        w1 = _rvbam_wavelength_angstrom(segment.get("wv_max"))
        if w0 is None or w1 is None:
            continue
        if w1 < w0:
            w0, w1 = w1, w0
        specid_value = _safe_float(run.get("moca_specid"))
        if specid_value is None:
            continue
        try:
            fetcher.set_segment_range(float(w0), float(w1))
            sample_run_id = int(segment["moca_sample_run_id"])
            theta = _rvbam_theta_from_parameters(parameters_by_run.get(sample_run_id, []), segment, dict(run))
            for key, value in midpoint_theta.items():
                theta.setdefault(key, value)
            data = SegmentData(
                wavelength=wavelength,
                flux=flux,
                flux_err=flux_unc,
                berv_kms=_safe_float(run.get("berv_kms")),
                berv_corrected=run.get("berv_corrected"),
                edges=edges_from_centers(wavelength),
                segment_bounds=(float(w0), float(w1)),
                specid=int(specid_value),
                window_number=segment.get("window_number"),
                segment_number=segment.get("segment_number"),
            )
            loglike = SegmentLogLikelihood(
                data,
                fetcher,
                forward_config=forward_config,
                model_flux_scale=1.0,
            )
            model_on_data = np.asarray(loglike.model_on_data(theta), dtype=float)
            model_scale = _rvbam_scale_model_to_data(flux, model_on_data)
            model_on_data_scaled = model_on_data * model_scale
            model_wavelength = np.linspace(
                float(w0),
                float(w1),
                max(16, int(RVBAM_RV_CONTENT_MODEL_POINTS)),
                dtype=float,
            )
            model_flux = np.asarray(loglike.model_on_grid(theta, model_wavelength), dtype=float) * model_scale
            model_contrast, deep_count = _rvbam_model_flux_content(model_flux)
            if model_contrast is not None:
                segment["model_contrast"] = _pythonize(model_contrast)
            if deep_count is not None:
                segment["nmodel_10p_contrast"] = _pythonize(deep_count)
            outlier_indices = _rvbam_masked_outlier_indices(flux, flux_unc, model_on_data_scaled)
            segment["noutliers_masked"] = _pythonize(int(outlier_indices.size))
            if outlier_indices.size:
                keep = np.ones(flux.shape, dtype=bool)
                keep[outlier_indices] = False
                data_contrast = _rvbam_intrinsic_flux_contrast(flux[keep], flux_unc[keep])
                if data_contrast is not None:
                    segment["data_contrast"] = _pythonize(data_contrast)
            meta["computed_model_segments"] = int(meta["computed_model_segments"]) + 1
        except Exception:
            meta["failed_model_segments"] = int(meta["failed_model_segments"]) + 1
            continue

    return meta


def _rvbam_enrich_segments_rv_content(
    conn: Any,
    run: Mapping[str, Any],
    segments: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    arrays_by_segment = _rvbam_enrich_segments_observed_content(conn, run.get("moca_specid"), segments)
    meta: dict[str, Any] = {
        "data_method": "rvbam.observed_intrinsic_flux_contrast.v1",
        "computed_data_segments": len(arrays_by_segment),
    }
    meta.update(_rvbam_enrich_segments_model_content(conn, run, segments, arrays_by_segment))
    return meta


def _rvbam_local_model_candidates(moca_mgridid: Any, template_name: Any = None) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    roots = RVBAM_LOCAL_MODEL_DIRS

    def add(path: Path | str | None) -> None:
        if path is None:
            return
        candidate = Path(path).expanduser()
        paths = [candidate] if candidate.is_absolute() else [root / candidate for root in roots]
        for item in paths:
            key = os.path.normcase(str(item))
            if key not in seen:
                seen.add(key)
                candidates.append(item)

    for raw in (moca_mgridid, template_name):
        text_value = str(raw or "").strip()
        if not text_value:
            continue
        basename = Path(text_value).name
        add(text_value)
        add(basename)
        if basename.endswith(".h5"):
            stem = basename[:-3]
            add(f"{stem}.h5")
            if stem.startswith("models_"):
                add(f"{stem}.h5")
            else:
                add(f"models_{stem}.h5")
        else:
            add(f"{basename}.h5")
            add(f"models_{basename}.h5")
    return candidates


def _rvbam_model_base_dir_for_status(status: dict[str, Any]) -> Path:
    for key in ("model_base_dir", "base_dir"):
        value = str(status.get(key) or "").strip()
        if value:
            return Path(value).expanduser()
    return RVBAM_LOCAL_MODEL_DIR


def _rvbam_local_model_status(moca_mgridid: Any, template_name: Any = None) -> dict[str, Any]:
    import importlib.util

    mgridid = str(moca_mgridid or "").strip()
    existing_base_dirs = [path for path in RVBAM_LOCAL_MODEL_DIRS if path.is_dir()]
    configured_base_exists = bool(existing_base_dirs)
    candidates = _rvbam_local_model_candidates(moca_mgridid, template_name)
    model_path = next((path for path in candidates if path.is_file()), candidates[0] if candidates else None)
    model_exists = bool(model_path and model_path.is_file())
    model_base_dir = model_path.parent if model_exists and model_path is not None else (existing_base_dirs[0] if existing_base_dirs else RVBAM_LOCAL_MODEL_DIR)
    base_exists = configured_base_exists or model_exists
    h5py_available = importlib.util.find_spec("h5py") is not None
    available = bool(base_exists and model_exists and h5py_available)
    if not configured_base_exists and not model_exists:
        message = "No configured local RVBAM HDF5 model directories are available on this server."
    elif not model_exists:
        message = "Local RVBAM HDF5 model file is not available on this server."
    elif not h5py_available:
        message = "h5py is not installed in the Python environment running this server."
    else:
        message = ""
    return {
        "available": available,
        "base_dir": str(model_base_dir),
        "base_dirs": [str(path) for path in RVBAM_LOCAL_MODEL_DIRS],
        "existing_base_dirs": [str(path) for path in existing_base_dirs],
        "base_exists": base_exists,
        "model_base_dir": str(model_base_dir),
        "model_file": str(model_path) if model_path else "",
        "model_exists": model_exists,
        "h5py_available": h5py_available,
        "moca_mgridid": mgridid,
        "template_name": str(template_name or "").strip(),
        "candidate_files": [str(path) for path in candidates[:8]],
        "message": message,
    }


def _rvbam_refresh_local_model_status(payload: dict[str, Any]) -> dict[str, Any]:
    run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
    previous = payload.get("localModelFit") if isinstance(payload.get("localModelFit"), dict) else {}
    payload["localModelFit"] = _rvbam_local_model_status(
        run.get("moca_mgridid") or previous.get("moca_mgridid"),
        run.get("template_name") or previous.get("template_name"),
    )
    return payload


def _mock_rvbam_berv_comment(run_id: int) -> str:
    if int(run_id) == 910001:
        return (
            'berv_source="astropy"; berv_kms=18.23; berv_epoch_mjd=61041.0; '
            'moca_berv_corrected=0; spacecraft_rv_corrected=0; '
            'berv_coord_source="moca_objects"; berv_location="greenwich"; '
            'berv_sign="add_to_sampler_rv"'
        )
    return "mode=\"standard\"; spectrum_berv_status=\"already_corrected\""


def _mock_rvbam_runs(args: dict[str, Any]) -> dict[str, Any]:
    runs = [
        {
            "moca_rv_sample_run_id": 910001,
            "moca_oid": 602,
            "designation": "2MASS J00361617+1821104",
            "moca_instid": "spex_irtf",
            "moca_specid": 13510,
            "spectrum_name": "mock_spex_prism_13510",
            "moca_mgridid": "sonora_bobcat",
            "pipeline_version": "rvbam-dev",
            "target_name": "2MASS J00361617+1821104",
            "template_name": "sonora_mock_t1800_logg5.0.fits",
            "nwindows": 5,
            "nsegments": 34,
            "median_snr_per_pix": 14.5,
            "median_snr_per_res_element": 26.0,
            "available_segment_count": 34,
            "segment_count": 34,
            "sample_segment_count": 34,
            "payload_segment_count": 34,
            "wv_min": 0.88,
            "wv_max": 2.38,
            "rv_mean_kms": -18.2,
            "rv_median_kms": -18.4,
            "rv_unc_median_kms": 1.1,
            "berv_kms": 18.23,
            "epoch_mjd": 61041.0,
            "data_collection_date": "2026-01-01",
            "comments": _mock_rvbam_berv_comment(910001),
            "origin": "mock_rvbam",
            "ignored": 0,
            "created_timestamp": "2026-01-10T12:00:00",
            "modified_timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        },
        {
            "moca_rv_sample_run_id": 910002,
            "moca_oid": 10995,
            "designation": "WISE J104915.57-531906.1",
            "moca_instid": "nires_keck",
            "moca_specid": 450,
            "spectrum_name": "mock_nires_450",
            "moca_mgridid": "sonora_cholla",
            "pipeline_version": "rvbam-dev",
            "target_name": "WISE J104915.57-531906.1",
            "template_name": "sonora_mock_t1300_logg5.0.fits",
            "nwindows": 4,
            "nsegments": 28,
            "median_snr_per_pix": 1.8,
            "median_snr_per_res_element": 3.2,
            "available_segment_count": 28,
            "segment_count": 28,
            "sample_segment_count": 28,
            "payload_segment_count": 28,
            "wv_min": 0.94,
            "wv_max": 2.31,
            "rv_mean_kms": 21.3,
            "rv_median_kms": 21.0,
            "rv_unc_median_kms": 0.8,
            "berv_kms": 0.0,
            "epoch_mjd": 61110.0,
            "data_collection_date": "2026-03-11",
            "comments": _mock_rvbam_berv_comment(910002),
            "origin": "mock_rvbam",
            "ignored": 0,
            "created_timestamp": "2026-01-22T12:00:00",
            "modified_timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        },
    ]
    for run in runs:
        run_id = int(run["moca_rv_sample_run_id"])
        segments = _mock_rvbam_segments(run_id)
        raw_available_count = sum(
            1
            for segment in segments
            if not _as_bool(segment.get("ignored")) and _safe_float(segment.get("rv_kms")) is not None
        )
        filtered_available_count = len(_rvbam_filtered_comparison_segments(segments, args))
        run["unfiltered_available_segment_count"] = raw_available_count
        run["available_segment_count"] = (
            filtered_available_count
            if _rvbam_comparison_segment_filters_active(args)
            else raw_available_count
        )
        if _rvbam_comparison_segment_filters_active(args):
            run["segment_filter_available_count"] = filtered_available_count
        run.update(_rvbam_segment_timestamp_summary(segments))
        literature_rv = _mock_rvbam_literature_rv(run)
        run["has_literature_rv"] = 1 if literature_rv else 0
        run["berv_metadata"] = _rvbam_berv_metadata_from_comments(run.get("comments"))
        run["literature_modified_timestamp"] = (
            run.get("latest_segment_modified_timestamp") if literature_rv else None
        )

    if _rvbam_has_literature_rv_filter(args):
        runs = [row for row in runs if _as_bool(row.get("has_literature_rv"))]

    min_segments = _rvbam_segment_count_filter_arg(args, "min", "min_segments", "min_segment_count", "min_available_segments")
    if min_segments is not None:
        runs = [row for row in runs if int(row.get("available_segment_count") or 0) >= min_segments]
    max_segments = _rvbam_segment_count_filter_arg(args, "max", "max_segments", "max_segment_count", "max_available_segments")
    if max_segments is not None:
        runs = [row for row in runs if int(row.get("available_segment_count") or 0) <= max_segments]
    min_run_snr = _safe_float(
        args.get("min_run_snr")
        or args.get("min_run_median_snr")
        or args.get("min_median_snr")
        or args.get("min_median_snr_per_pix")
    )
    if min_run_snr is not None:
        runs = [
            row
            for row in runs
            if (_safe_float(row.get("median_snr_per_pix")) is not None)
            and float(_safe_float(row.get("median_snr_per_pix")) or 0.0) >= min_run_snr
        ]

    wavelength_ranges = _rvbam_wavelength_coverage_ranges(args)
    if wavelength_ranges:
        runs = [
            row
            for row in runs
            if _rvbam_segments_cover_wavelength_ranges(
                _mock_rvbam_segments(int(row["moca_rv_sample_run_id"])),
                wavelength_ranges,
            )
        ]

    selected = _rvbam_int_arg(args, "run_id", "moca_rv_sample_run_id")
    if selected and not any(int(row["moca_rv_sample_run_id"]) == selected for row in runs):
        selected = None
    value = selected or (runs[0]["moca_rv_sample_run_id"] if runs else None)
    return {
        "runs": runs,
        "value": value,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "run_count": len(runs),
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _mock_rvbam_segments(run_id: int) -> list[dict[str, Any]]:
    seed = int(hashlib.sha1(str(run_id).encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    n_rows = 34 if run_id == 910001 else 28
    base_rv = -18.4 if run_id == 910001 else 21.0
    base_timestamp = datetime(2026, 1, 10 if run_id == 910001 else 22, 12, 0, 0)
    segments: list[dict[str, Any]] = []
    for index in range(n_rows):
        wv_min = 0.88 + 0.045 * index
        wv_max = wv_min + float(rng.uniform(0.03, 0.07))
        rv_unc = float(rng.uniform(0.35, 2.1))
        created_timestamp = base_timestamp + timedelta(minutes=23 * index)
        modified_timestamp = created_timestamp + timedelta(hours=1, minutes=index % 17)
        data_contrast = float(rng.uniform(0.018, 0.085))
        model_contrast = float(rng.uniform(0.10, 0.42))
        if index % 13 == 0:
            data_contrast *= 0.35
        if index % 11 == 0:
            model_contrast *= 0.45
        segment_snr_median = float(rng.uniform(8.0, 85.0))
        segments.append({
            "moca_rv_sampling_segment_id": run_id * 100 + index + 1,
            "moca_rv_sample_run_id": run_id,
            "moca_sample_run_id": run_id * 1000 + index + 1,
            "order_number": 1 + index // 7,
            "window_number": 1 + (index // 3) % 5,
            "segment_number": index + 1,
            "wv_min": round(wv_min, 6),
            "wv_max": round(wv_max, 6),
            "wv_center": round((wv_min + wv_max) / 2.0, 6),
            "rv_kms": round(base_rv + 1.2 * math.sin(index / 4.0) + float(rng.normal(0.0, rv_unc * 0.45)), 5),
            "rv_kms_unc": round(rv_unc, 5),
            "lsf": round(float(rng.uniform(9.0, 24.0)), 5),
            "lsf_unc": round(float(rng.uniform(0.4, 2.3)), 5),
            "vsini_kms": round(float(rng.uniform(6.0, 42.0)), 5),
            "vsini_kms_unc": round(float(rng.uniform(0.7, 5.0)), 5),
            "moca_fsid": 400000 + index,
            "sampler_type": "nested",
            "sampler_name": "ultranest",
            "sampler_variant": "reactive",
            "n_parameters": 5,
            "n_walkers": None,
            "n_iterations": int(rng.integers(3500, 9000)),
            "mean_acceptance_rate": round(float(rng.uniform(0.22, 0.58)), 5),
            "best_chi2": round(float(rng.uniform(0.7, 1.9)), 5),
            "lnp_median": round(float(rng.normal(-820.0, 40.0)), 5),
            "lnp_max": round(float(rng.normal(-790.0, 35.0)), 5),
            "mean_finite_fraction": round(float(rng.uniform(0.96, 1.0)), 5),
            "mean_outofbounds_fraction": round(float(rng.uniform(0.0, 0.04)), 5),
            "data_contrast": round(data_contrast, 5),
            "model_contrast": round(model_contrast, 5),
            "nmodel_10p_contrast": int(rng.integers(24, 180)),
            "noutliers_masked": int(rng.integers(0, 4)) if index % 7 == 0 else 0,
            "segment_snr_median": round(segment_snr_median, 3),
            "segment_snr_p10": round(segment_snr_median * float(rng.uniform(0.55, 0.82)), 3),
            "segment_snr_p90": round(segment_snr_median * float(rng.uniform(1.12, 1.65)), 3),
            "segment_snr_npoints": int(rng.integers(18, 95)),
            "param_count": 5,
            "payload_count": 2,
            "chain_payloads": 1,
            "lnp_payloads": 1,
            "total_stored_samples": int(rng.integers(6000, 18000)),
            "model_fit_url": "",
            "corner_url": "",
            "ignored": 0,
            "created_timestamp": created_timestamp.isoformat(timespec="seconds"),
            "modified_timestamp": modified_timestamp.isoformat(timespec="seconds"),
            "comments": _mock_rvbam_berv_comment(run_id),
        })
        segments[-1]["berv_metadata"] = _rvbam_berv_metadata_from_comments(segments[-1]["comments"])
    return segments


def _mock_rvbam_literature_rv(run: dict[str, Any]) -> dict[str, Any] | None:
    run_id = int(run.get("moca_rv_sample_run_id") or 0)
    if run_id == 910002:
        return {
            "source": "host",
            "label": "Literature host RV",
            "moca_oid": 10994,
            "target_moca_oid": run.get("moca_oid"),
            "host_moca_oid": 10994,
            "designation": "WISE J104915.57-531906.1 A",
            "radial_velocity_kms": 20.8,
            "radial_velocity_kms_unc": 0.9,
            "n_measurements": 4,
            "n_epochs": 3,
            "is_public": 1,
        }
    if run_id == 910001:
        return {
            "source": "object",
            "label": "Literature RV",
            "moca_oid": run.get("moca_oid"),
            "target_moca_oid": run.get("moca_oid"),
            "host_moca_oid": None,
            "designation": run.get("designation") or run.get("target_name"),
            "radial_velocity_kms": -18.0,
            "radial_velocity_kms_unc": 1.2,
            "n_measurements": 5,
            "n_epochs": 4,
            "is_public": 1,
        }
    return None


def _mock_rvbam_spectrum(run: dict[str, Any]) -> dict[str, Any]:
    specid = run.get("moca_specid")
    run_id = int(run.get("moca_rv_sample_run_id") or 0)
    berv_corrected = 0 if run_id == 910001 else 1
    spacecraft_rv_corrected = 1 if run_id == 910002 else 0
    return {
        "moca_specid": specid,
        "moca_pid": "mock",
        "moca_specpackid": None,
        "moca_oid": run.get("moca_oid"),
        "moca_instid": run.get("moca_instid"),
        "spectrum_name": run.get("spectrum_name"),
        "flux_units": "mock flux",
        "min_wavelength_angstrom": (run.get("wv_min") or 0) * 10000,
        "max_wavelength_angstrom": (run.get("wv_max") or 0) * 10000,
        "median_spectral_resolving_power": 1200,
        "median_snr_per_pix": run.get("median_snr_per_pix"),
        "median_snr_per_res_element": run.get("median_snr_per_res_element"),
        "data_collection_date": run.get("data_collection_date") or "2026-01-01",
        "epoch_mjd": run.get("epoch_mjd") or 61041.0,
        "instrument_mode_name": "mock",
        "berv_corrected": berv_corrected,
        "spacecraft_rv_corrected": spacecraft_rv_corrected,
        "origin": "mock_rvbam",
        "is_public": 1,
        "ignored": 0,
        "comments": "Synthetic moca_spectra metadata for local RVBAM smoke testing",
    }


def _mock_rvbam_run_payload(args: dict[str, Any], run_id: int | None = None) -> dict[str, Any]:
    run_args = dict(args)
    for key in (
        "has_literature_rv", "literature_rv", "lit_rv",
        "wavelength_coverage", "wv_coverage", "coverage", "wavelength",
        "min_segments", "min_segment_count", "min_available_segments",
        "max_segments", "max_segment_count", "max_available_segments",
        "min_run_snr", "min_run_median_snr", "min_median_snr", "min_median_snr_per_pix",
    ):
        run_args.pop(key, None)
    run_payload = _mock_rvbam_runs(run_args)
    selected_id = int(run_id or _rvbam_int_arg(args, "run_id", "moca_rv_sample_run_id") or run_payload["value"])
    run = next((row for row in run_payload["runs"] if int(row["moca_rv_sample_run_id"]) == selected_id), run_payload["runs"][0])
    selected_id = int(run["moca_rv_sample_run_id"])
    segments = _mock_rvbam_segments(selected_id)
    timestamp_summary = _rvbam_segment_timestamp_summary(segments)
    run.update(timestamp_summary)
    return {
        "run": run,
        "segments": segments,
        "literatureRv": _mock_rvbam_literature_rv(run),
        "spectrum": _mock_rvbam_spectrum(run),
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "segment_count": len(segments),
            "private_db": _is_private_db(args),
            **timestamp_summary,
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _rvbam_comparison_segment_filters(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "max_lsf": _safe_float(args.get("max_lsf")),
        "max_best_chi2": _safe_float(args.get("max_best_chi2")),
        "max_rv_unc": _safe_float(args.get("max_rv_unc")),
        "min_data_contrast": _safe_float(args.get("min_data_contrast")),
        "min_model_contrast": _safe_float(args.get("min_model_contrast")),
        "min_model_10p": _safe_float(args.get("min_model_10p")),
        "min_snr": _safe_float(args.get("min_snr")),
        "segment_wavelength_ranges": _rvbam_segment_wavelength_filter_ranges(args),
        "max_masked_outliers": _safe_float(args.get("max_masked_outliers") or args.get("max_noutliers_masked")),
    }


def _rvbam_comparison_segment_filters_active(args: dict[str, Any]) -> bool:
    for value in _rvbam_comparison_segment_filters(args).values():
        if isinstance(value, list) and value:
            return True
        if not isinstance(value, list) and value is not None:
            return True
    return False


def _rvbam_passes_max_filter(value: Any, maximum: float | None) -> bool:
    if maximum is None:
        return True
    number = _safe_float(value)
    return number is not None and number <= maximum


def _rvbam_passes_min_filter(value: Any, minimum: float | None) -> bool:
    if minimum is None:
        return True
    number = _safe_float(value)
    return number is not None and number >= minimum


def _rvbam_segment_passes_comparison_filters(segment: dict[str, Any], filters: dict[str, float | None]) -> bool:
    return (
        _rvbam_passes_max_filter(segment.get("lsf"), filters["max_lsf"])
        and _rvbam_passes_max_filter(segment.get("best_chi2"), filters["max_best_chi2"])
        and _rvbam_passes_max_filter(segment.get("rv_kms_unc"), filters["max_rv_unc"])
        and _rvbam_passes_min_filter(segment.get("data_contrast"), filters["min_data_contrast"])
        and _rvbam_passes_min_filter(segment.get("model_contrast"), filters["min_model_contrast"])
        and _rvbam_passes_min_filter(segment.get("nmodel_10p_contrast"), filters["min_model_10p"])
        and _rvbam_passes_min_filter(segment.get("segment_snr_median"), filters["min_snr"])
        and (
            not filters["segment_wavelength_ranges"]
            or _rvbam_segments_cover_wavelength_ranges([segment], filters["segment_wavelength_ranges"])
        )
        and _rvbam_passes_max_filter(segment.get("noutliers_masked"), filters["max_masked_outliers"])
    )


def _rvbam_filtered_comparison_segments(
    segments: Sequence[dict[str, Any]],
    args: dict[str, Any],
) -> list[dict[str, Any]]:
    include_ignored = _as_bool(args.get("include_ignored") or args.get("show_ignored"))
    filters = _rvbam_comparison_segment_filters(args)
    rows = [
        segment
        for segment in segments
        if (include_ignored or not _as_bool(segment.get("ignored")))
        and _safe_float(segment.get("rv_kms")) is not None
    ]
    return [
        segment
        for segment in rows
        if _rvbam_segment_passes_comparison_filters(segment, filters)
    ]


def _rvbam_weighted_rv_stats(segments: Sequence[dict[str, Any]]) -> dict[str, Any]:
    values: list[float] = []
    sw = 0.0
    swx = 0.0
    weighted_n = 0
    for segment in segments:
        value = _safe_float(segment.get("rv_kms"))
        if value is None:
            continue
        values.append(float(value))
        uncertainty = _safe_float(segment.get("rv_kms_unc"))
        if uncertainty is None or uncertainty <= 0:
            continue
        weight = 1.0 / (float(uncertainty) * float(uncertainty))
        sw += weight
        swx += weight * float(value)
        weighted_n += 1

    if not values:
        return {"n": 0, "mean": None, "unc": None, "weighted": False}
    if weighted_n and sw > 0:
        return {
            "n": weighted_n,
            "mean": swx / sw,
            "unc": math.sqrt(1.0 / sw),
            "weighted": True,
        }

    mean = float(sum(values) / len(values))
    unc = None
    if len(values) > 1:
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        unc = math.sqrt(variance / len(values))
    return {"n": len(values), "mean": mean, "unc": unc, "weighted": False}


def _rvbam_datetime_from_value(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text_value = str(value).strip()
    if not text_value:
        return None
    if text_value.endswith("Z"):
        text_value = f"{text_value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text_value)
    except ValueError:
        for fmt in ("%Y/%m/%d", "%Y %m %d", "%Y"):
            try:
                parsed = datetime.strptime(text_value, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _rvbam_decimal_year_from_datetime(value: datetime) -> float:
    start = datetime(value.year, 1, 1)
    end = datetime(value.year + 1, 1, 1)
    return float(value.year + (value - start).total_seconds() / (end - start).total_seconds())


def _rvbam_decimal_year_from_mjd(value: Any) -> float | None:
    mjd = _safe_float(value)
    if mjd is None:
        return None
    timestamp = datetime(1858, 11, 17) + timedelta(days=float(mjd))
    return _rvbam_decimal_year_from_datetime(timestamp)


def _rvbam_run_epoch_decimal_year(run: dict[str, Any], segment: dict[str, Any] | None = None) -> tuple[float | None, str | None]:
    for source, value in (
        ("epoch_mjd", run.get("epoch_mjd")),
        ("mjd", run.get("mjd")),
    ):
        decimal_year = _rvbam_decimal_year_from_mjd(value)
        if decimal_year is not None:
            return decimal_year, source

    for source, value in (
        ("data_collection_date", run.get("data_collection_date")),
        ("spectrum_created_timestamp", run.get("spectrum_created_timestamp")),
        ("run_created_timestamp", run.get("created_timestamp")),
        ("segment_created_timestamp", segment.get("created_timestamp") if segment else None),
    ):
        timestamp = _rvbam_datetime_from_value(value)
        if timestamp is not None:
            return _rvbam_decimal_year_from_datetime(timestamp), source

    return None, None


def _rvbam_literature_comparison_point(
    run: dict[str, Any],
    segments: Sequence[dict[str, Any]],
    literature_rv: dict[str, Any] | None,
    args: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    if not literature_rv:
        return None, "no_literature_rv"
    lit_value = _safe_float(literature_rv.get("radial_velocity_kms"))
    if lit_value is None:
        return None, "no_literature_rv"

    kept_segments = _rvbam_filtered_comparison_segments(segments, args)
    if not kept_segments:
        return None, "no_kept_segments"
    stats = _rvbam_weighted_rv_stats(kept_segments)
    rv_value = _safe_float(stats.get("mean"))
    if rv_value is None:
        return None, "no_segment_rv"

    run_id = run.get("moca_rv_sample_run_id")
    lit_unc = _safe_float(literature_rv.get("radial_velocity_kms_unc"))
    rv_unc = _safe_float(stats.get("unc"))
    decimal_year, epoch_source = _rvbam_run_epoch_decimal_year(run)
    return {
        "moca_rv_sample_run_id": run_id,
        "moca_oid": run.get("moca_oid"),
        "moca_specid": run.get("moca_specid"),
        "designation": run.get("designation") or run.get("target_name"),
        "target_name": run.get("target_name"),
        "moca_instid": run.get("moca_instid"),
        "pipeline_version": run.get("pipeline_version") or run.get("rv_pipeline_version"),
        "template_name": run.get("template_name"),
        "moca_mgridid": run.get("moca_mgridid"),
        "spectrum_name": run.get("spectrum_name"),
        "epoch_mjd": run.get("epoch_mjd"),
        "data_collection_date": run.get("data_collection_date"),
        "decimal_year": _pythonize(decimal_year),
        "decimal_year_source": epoch_source,
        "rvbam_rv_kms": _pythonize(rv_value),
        "rvbam_rv_kms_unc": _pythonize(rv_unc),
        "rvbam_rv_weighted": bool(stats.get("weighted")),
        "rvbam_rv_segment_count": int(stats.get("n") or 0),
        "kept_segment_count": len(kept_segments),
        "available_segment_count": len(segments),
        "literature_rv_kms": _pythonize(float(lit_value)),
        "literature_rv_kms_unc": _pythonize(lit_unc),
        "literature_label": literature_rv.get("label"),
        "literature_source": literature_rv.get("source"),
        "literature_moca_oid": literature_rv.get("moca_oid"),
        "literature_designation": literature_rv.get("designation"),
        "literature_n_measurements": literature_rv.get("n_measurements"),
        "literature_n_epochs": literature_rv.get("n_epochs"),
    }, None


def _rvbam_literature_bias_segment_points(
    run: dict[str, Any],
    segments: Sequence[dict[str, Any]],
    literature_rv: dict[str, Any] | None,
    args: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    skipped = {
        "no_literature_rv": 0,
        "no_kept_segments": 0,
        "no_segment_rv": 0,
        "no_epoch": 0,
    }
    if not literature_rv:
        skipped["no_literature_rv"] += 1
        return [], skipped
    lit_value = _safe_float(literature_rv.get("radial_velocity_kms"))
    if lit_value is None:
        skipped["no_literature_rv"] += 1
        return [], skipped

    kept_segments = _rvbam_filtered_comparison_segments(segments, args)
    if not kept_segments:
        skipped["no_kept_segments"] += 1
        return [], skipped

    run_id = run.get("moca_rv_sample_run_id")
    lit_unc = _safe_float(literature_rv.get("radial_velocity_kms_unc"))
    points: list[dict[str, Any]] = []
    for segment in kept_segments:
        rv_value = _safe_float(segment.get("rv_kms"))
        if rv_value is None:
            skipped["no_segment_rv"] += 1
            continue
        decimal_year, epoch_source = _rvbam_run_epoch_decimal_year(run, segment)
        if decimal_year is None:
            skipped["no_epoch"] += 1
            continue
        rv_unc = _safe_float(segment.get("rv_kms_unc"))
        uncertainties = [
            value
            for value in (rv_unc, lit_unc)
            if value is not None and value > 0
        ]
        bias_unc = math.sqrt(sum(float(value) ** 2 for value in uncertainties)) if uncertainties else None
        points.append({
            "moca_rv_sample_run_id": run_id,
            "moca_rv_sampling_segment_id": segment.get("moca_rv_sampling_segment_id"),
            "moca_oid": run.get("moca_oid"),
            "designation": run.get("designation") or run.get("target_name"),
            "target_name": run.get("target_name"),
            "template_name": run.get("template_name"),
            "segment_number": segment.get("segment_number"),
            "wv_center": segment.get("wv_center"),
            "decimal_year": _pythonize(decimal_year),
            "decimal_year_source": epoch_source,
            "measured_rv_kms": _pythonize(float(rv_value)),
            "measured_rv_kms_unc": _pythonize(rv_unc),
            "literature_rv_kms": _pythonize(float(lit_value)),
            "literature_rv_kms_unc": _pythonize(lit_unc),
            "rv_bias_kms": _pythonize(float(rv_value) - float(lit_value)),
            "rv_bias_kms_unc": _pythonize(bias_unc),
            "literature_label": literature_rv.get("label"),
        })
    return points, skipped


def _mock_rvbam_literature_comparison(args: dict[str, Any]) -> dict[str, Any]:
    run_payload = _mock_rvbam_runs(args)
    points: list[dict[str, Any]] = []
    bias_points: list[dict[str, Any]] = []
    skipped = {"no_literature_rv": 0, "no_kept_segments": 0, "no_segment_rv": 0, "errors": 0}
    bias_skipped = {"no_literature_rv": 0, "no_kept_segments": 0, "no_segment_rv": 0, "no_epoch": 0}
    for run in run_payload["runs"]:
        segments = _mock_rvbam_segments(int(run["moca_rv_sample_run_id"]))
        literature_rv = _mock_rvbam_literature_rv(run)
        point, reason = _rvbam_literature_comparison_point(
            run,
            segments,
            literature_rv,
            args,
        )
        run_bias_points, run_bias_skipped = _rvbam_literature_bias_segment_points(run, segments, literature_rv, args)
        bias_points.extend(run_bias_points)
        for key, count in run_bias_skipped.items():
            bias_skipped[key] = bias_skipped.get(key, 0) + int(count)
        if point:
            points.append(point)
        elif reason:
            skipped[reason] = skipped.get(reason, 0) + 1

    return {
        "points": points,
        "biasPoints": bias_points,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "candidate_run_count": len(run_payload["runs"]),
            "point_count": len(points),
            "bias_point_count": len(bias_points),
            "skipped": skipped,
            "bias_skipped": bias_skipped,
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _mock_rvbam_parameters(sample_run_id: int) -> list[dict[str, Any]]:
    rng = np.random.default_rng(sample_run_id % (2**32 - 1))
    rv = float(rng.normal(-18.0 if sample_run_id // 1000 == 910001 else 21.0, 0.7))
    return [
        {"moca_sampling_parameter_id": sample_run_id * 10 + 1, "moca_sample_run_id": sample_run_id, "param_name": "rv_kms", "param_index": 0, "units": "km/s", "median_value": rv, "p16_value": rv - 0.8, "p84_value": rv + 0.8, "std_value": 0.75, "is_fixed": 0, "prior_type": "uniform", "lower_bound": -150.0, "upper_bound": 150.0},
        {"moca_sampling_parameter_id": sample_run_id * 10 + 2, "moca_sample_run_id": sample_run_id, "param_name": "lsf_sigma_kms", "param_index": 1, "units": "km/s", "median_value": 15.0, "p16_value": 12.0, "p84_value": 19.5, "std_value": 3.2, "is_fixed": 0, "prior_type": "lognormal"},
        {"moca_sampling_parameter_id": sample_run_id * 10 + 3, "moca_sample_run_id": sample_run_id, "param_name": "vsini_kms", "param_index": 2, "units": "km/s", "median_value": 22.0, "p16_value": 16.0, "p84_value": 31.0, "std_value": 5.5, "is_fixed": 0, "prior_type": "uniform"},
        {"moca_sampling_parameter_id": sample_run_id * 10 + 4, "moca_sample_run_id": sample_run_id, "param_name": "blaze_left", "param_index": 3, "units": None, "median_value": -0.03, "p16_value": -0.08, "p84_value": 0.02, "std_value": 0.04, "is_fixed": 0, "prior_type": "uniform"},
        {"moca_sampling_parameter_id": sample_run_id * 10 + 5, "moca_sample_run_id": sample_run_id, "param_name": "blaze_right", "param_index": 4, "units": None, "median_value": 0.04, "p16_value": -0.01, "p84_value": 0.09, "std_value": 0.05, "is_fixed": 0, "prior_type": "uniform"},
    ]


def _rvbam_run_filter_sql(
    args: dict[str, Any],
    *,
    use_segment_summary: bool = True,
    literature_exists_sql: str | None = None,
) -> tuple[str, dict[str, Any]]:
    include_ignored = _as_bool(args.get("include_ignored") or args.get("show_ignored"))
    segment_exists_ignored_clause = "" if include_ignored else "AND COALESCE(s_exists.ignored, 0) = 0"
    segment_count_ignored_clause = "" if include_ignored else "AND COALESCE(sc.ignored, 0) = 0"
    if use_segment_summary:
        clauses: list[str] = ["COALESCE(seg.segment_count, 0) > 0"]
    else:
        clauses = [f"""
            EXISTS (
                SELECT 1
                FROM pcat_rv_sampling_segments AS s_exists
                WHERE s_exists.moca_rv_sample_run_id = r.moca_rv_sample_run_id
                  {segment_exists_ignored_clause}
            )
        """]
    params: dict[str, Any] = {}
    if not include_ignored:
        clauses.append("COALESCE(r.ignored, 0) = 0")

    if _rvbam_has_literature_rv_filter(args):
        clauses.append(literature_exists_sql or "COALESCE(lit.has_literature_rv, 0) = 1")

    moca_oid = _rvbam_int_arg(args, "moca_oid", "oid")
    if moca_oid is not None:
        clauses.append("r.moca_oid = :moca_oid")
        params["moca_oid"] = moca_oid

    moca_specid = _rvbam_int_arg(args, "moca_specid", "specid")
    if moca_specid is not None:
        clauses.append("r.moca_specid = :moca_specid")
        params["moca_specid"] = moca_specid

    pipeline = str(args.get("pipeline_version") or args.get("pipeline") or "").strip()
    if pipeline:
        clauses.append("r.pipeline_version = :pipeline_version")
        params["pipeline_version"] = pipeline

    mgridid = str(args.get("moca_mgridid") or args.get("mgridid") or "").strip()
    if mgridid:
        clauses.append("r.moca_mgridid = :moca_mgridid")
        params["moca_mgridid"] = mgridid

    instid = str(args.get("moca_instid") or args.get("instid") or "").strip()
    if instid:
        clauses.append("r.moca_instid = :moca_instid")
        params["moca_instid"] = instid

    query = str(args.get("q") or args.get("search") or "").strip()
    if query:
        like = f"%{query}%"
        clauses.append("""
            (
                r.target_name LIKE :query_like
                OR r.template_name LIKE :query_like
                OR r.pipeline_version LIKE :query_like
                OR r.moca_mgridid LIKE :query_like
                OR r.moca_instid LIKE :query_like
                OR mo.designation LIKE :query_like
                OR ms.spectrum_name LIKE :query_like
                OR CAST(r.moca_oid AS CHAR) = :query_exact
                OR CAST(r.moca_specid AS CHAR) = :query_exact
            )
        """)
        params["query_like"] = like
        params["query_exact"] = query

    min_segments = _rvbam_segment_count_filter_arg(args, "min", "min_segments", "min_segment_count", "min_available_segments")
    max_segments = _rvbam_segment_count_filter_arg(args, "max", "max_segments", "max_segment_count", "max_available_segments")
    segment_filters_active = _rvbam_comparison_segment_filters_active(args)
    sql_max_segments = None if segment_filters_active else max_segments
    if min_segments is not None or sql_max_segments is not None:
        if use_segment_summary:
            segment_count_sql = "COALESCE(seg.available_segment_count, 0)"
        else:
            segment_count_sql = f"""
                (
                    SELECT COUNT(*)
                    FROM pcat_rv_sampling_segments AS sc
                    WHERE sc.moca_rv_sample_run_id = r.moca_rv_sample_run_id
                      {segment_count_ignored_clause}
                      AND sc.rv_kms IS NOT NULL
                )
            """
        if min_segments is not None:
            clauses.append(f"{segment_count_sql} >= :min_segments")
            params["min_segments"] = int(min_segments)
        if sql_max_segments is not None:
            clauses.append(f"{segment_count_sql} <= :max_segments")
            params["max_segments"] = int(sql_max_segments)

    min_run_snr = _safe_float(
        args.get("min_run_snr")
        or args.get("min_run_median_snr")
        or args.get("min_median_snr")
        or args.get("min_median_snr_per_pix")
    )
    if min_run_snr is not None:
        clauses.append("ms.median_snr_per_pix IS NOT NULL AND ms.median_snr_per_pix >= :min_run_snr")
        params["min_run_snr"] = float(min_run_snr)

    segment_ignored_clause = "" if include_ignored else "AND COALESCE(swv.ignored, 0) = 0"
    wavelength_ranges = _rvbam_wavelength_coverage_ranges(args)
    if wavelength_ranges:
        overlap_clauses: list[str] = []
        for index, (wv_lo, wv_hi) in enumerate(wavelength_ranges):
            lo_key = f"wv_lo_{index}"
            hi_key = f"wv_hi_{index}"
            lo_angstrom_key = f"wv_lo_angstrom_{index}"
            hi_angstrom_key = f"wv_hi_angstrom_{index}"
            overlap_clauses.append(f"""
                (
                    (swv.wv_min <= :{hi_key} AND swv.wv_max >= :{lo_key})
                    OR (swv.wv_min <= :{hi_angstrom_key} AND swv.wv_max >= :{lo_angstrom_key})
                )
            """)
            params[lo_key] = wv_lo
            params[hi_key] = wv_hi
            params[lo_angstrom_key] = wv_lo * 10000.0
            params[hi_angstrom_key] = wv_hi * 10000.0
        overlap_sql = " OR ".join(overlap_clauses)
        clauses.append(f"""
            EXISTS (
                SELECT 1
                FROM pcat_rv_sampling_segments AS swv
                WHERE swv.moca_rv_sample_run_id = r.moca_rv_sample_run_id
                  {segment_ignored_clause}
                  AND ({overlap_sql})
            )
        """)

    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _rvbam_empty_segment_summary() -> dict[str, Any]:
    return {
        "segment_count": 0,
        "available_segment_count": 0,
        "sample_segment_count": 0,
        "payload_segment_count": 0,
        "wv_min": None,
        "wv_max": None,
        "rv_mean_kms": None,
        "rv_unc_mean_kms": None,
        "oldest_segment_created_timestamp": None,
        "latest_segment_created_timestamp": None,
        "latest_segment_modified_timestamp": None,
    }


def _rvbam_segment_summaries_from_db(
    conn: Any, run_ids: Sequence[Any], *, include_ignored: bool = False
) -> dict[int, dict[str, Any]]:
    unique_run_ids: list[int] = []
    seen: set[int] = set()
    for run_id in run_ids:
        try:
            value = int(run_id)
        except (TypeError, ValueError):
            continue
        if value in seen:
            continue
        seen.add(value)
        unique_run_ids.append(value)
    if not unique_run_ids:
        return {}

    placeholders: list[str] = []
    params: dict[str, Any] = {}
    for index, run_id in enumerate(unique_run_ids):
        key = f"rv_run_id_{index}"
        placeholders.append(f":{key}")
        params[key] = run_id

    ignored_clause = "" if include_ignored else "AND COALESCE(s.ignored, 0) = 0"
    rows = _records(_read_sql(conn, f"""
        SELECT
            s.moca_rv_sample_run_id,
            COUNT(*) AS segment_count,
            COUNT(CASE WHEN s.rv_kms IS NOT NULL THEN 1 ELSE NULL END) AS available_segment_count,
            SUM(CASE WHEN s.moca_sample_run_id IS NOT NULL THEN 1 ELSE 0 END) AS sample_segment_count,
            COUNT(DISTINCT CASE WHEN pl.moca_payload_id IS NOT NULL THEN s.moca_rv_sampling_segment_id ELSE NULL END) AS payload_segment_count,
            MIN(s.wv_min) AS wv_min,
            MAX(s.wv_max) AS wv_max,
            AVG(s.rv_kms) AS rv_mean_kms,
            AVG(s.rv_kms_unc) AS rv_unc_mean_kms,
            MIN(s.created_timestamp) AS oldest_segment_created_timestamp,
            MAX(s.created_timestamp) AS latest_segment_created_timestamp,
            MAX(s.modified_timestamp) AS latest_segment_modified_timestamp
        FROM pcat_rv_sampling_segments s
        LEFT JOIN pcat_sampling_payloads pl
            ON pl.moca_sample_run_id = s.moca_sample_run_id
            AND pl.payload_kind = 'chains'
        WHERE s.moca_rv_sample_run_id IN ({", ".join(placeholders)})
            {ignored_clause}
        GROUP BY s.moca_rv_sample_run_id
    """, params))
    summaries: dict[int, dict[str, Any]] = {}
    for row in rows:
        try:
            key = int(row.get("moca_rv_sample_run_id"))
        except (TypeError, ValueError):
            continue
        summaries[key] = row
    return summaries


def _rvbam_filtered_segment_counts_from_db(
    conn: Any,
    run_ids: Sequence[Any],
    args: dict[str, Any],
    *,
    include_ignored: bool = False,
) -> tuple[dict[int, int], list[str]]:
    unique_run_ids: list[int] = []
    seen: set[int] = set()
    for run_id in run_ids:
        try:
            value = int(run_id)
        except (TypeError, ValueError):
            continue
        if value in seen:
            continue
        seen.add(value)
        unique_run_ids.append(value)
    if not unique_run_ids:
        return {}, []

    placeholders: list[str] = []
    params: dict[str, Any] = {}
    for index, run_id in enumerate(unique_run_ids):
        key = f"rv_count_run_id_{index}"
        placeholders.append(f":{key}")
        params[key] = run_id

    filters = _rvbam_comparison_segment_filters(args)
    clauses = [
        f"s.moca_rv_sample_run_id IN ({', '.join(placeholders)})",
        "s.rv_kms IS NOT NULL",
    ]
    if not include_ignored:
        clauses.append("COALESCE(s.ignored, 0) = 0")
    if filters["max_lsf"] is not None:
        clauses.append("s.lsf IS NOT NULL AND s.lsf <= :count_max_lsf")
        params["count_max_lsf"] = float(filters["max_lsf"])
    if filters["max_rv_unc"] is not None:
        clauses.append("s.rv_kms_unc IS NOT NULL AND s.rv_kms_unc <= :count_max_rv_unc")
        params["count_max_rv_unc"] = float(filters["max_rv_unc"])
    if filters["max_best_chi2"] is not None:
        clauses.append("sr.best_chi2 IS NOT NULL AND sr.best_chi2 <= :count_max_best_chi2")
        params["count_max_best_chi2"] = float(filters["max_best_chi2"])
    if filters["segment_wavelength_ranges"]:
        overlap_clauses: list[str] = []
        for index, (wv_lo, wv_hi) in enumerate(filters["segment_wavelength_ranges"]):
            lo_key = f"count_wv_lo_{index}"
            hi_key = f"count_wv_hi_{index}"
            lo_angstrom_key = f"count_wv_lo_angstrom_{index}"
            hi_angstrom_key = f"count_wv_hi_angstrom_{index}"
            overlap_clauses.append(f"""
                (
                    (s.wv_min <= :{hi_key} AND s.wv_max >= :{lo_key})
                    OR (s.wv_min <= :{hi_angstrom_key} AND s.wv_max >= :{lo_angstrom_key})
                )
            """)
            params[lo_key] = float(wv_lo)
            params[hi_key] = float(wv_hi)
            params[lo_angstrom_key] = float(wv_lo) * 10000.0
            params[hi_angstrom_key] = float(wv_hi) * 10000.0
        clauses.append(f"({' OR '.join(overlap_clauses)})")

    segment_columns = _db_table_columns(conn, "pcat_rv_sampling_segments")
    optional_column_filters = [
        ("min_data_contrast", "data_contrast", ">=", filters["min_data_contrast"]),
        ("min_model_contrast", "model_contrast", ">=", filters["min_model_contrast"]),
        ("min_model_10p", "nmodel_10p_contrast", ">=", filters["min_model_10p"]),
        ("min_snr", "segment_snr_median", ">=", filters["min_snr"]),
        ("max_masked_outliers", "noutliers_masked", "<=", filters["max_masked_outliers"]),
    ]
    skipped_filters: list[str] = []
    for filter_name, column_name, operator, value in optional_column_filters:
        if value is None:
            continue
        if column_name not in segment_columns:
            skipped_filters.append(filter_name)
            continue
        param_key = f"count_{filter_name}"
        clauses.append(f"s.{column_name} IS NOT NULL AND s.{column_name} {operator} :{param_key}")
        params[param_key] = float(value)

    rows = _records(_read_sql(conn, f"""
        SELECT
            s.moca_rv_sample_run_id,
            COUNT(*) AS available_segment_count
        FROM pcat_rv_sampling_segments s
        LEFT JOIN pcat_sampling_runs sr
            ON sr.moca_sample_run_id = s.moca_sample_run_id
        WHERE {' AND '.join(clauses)}
        GROUP BY s.moca_rv_sample_run_id
    """, params))
    counts: dict[int, int] = {}
    for row in rows:
        try:
            key = int(row.get("moca_rv_sample_run_id"))
        except (TypeError, ValueError):
            continue
        counts[key] = int(row.get("available_segment_count") or 0)
    return counts, skipped_filters


def _load_rvbam_runs_from_db(args: dict[str, Any]) -> dict[str, Any]:
    limit = _rvbam_limit_arg(args, "limit", 250, 2000)
    cache_key = _rvbam_cache_key(
        args,
        "runs",
        args.get("q") or args.get("search") or "",
        args.get("moca_oid") or args.get("oid") or "",
        args.get("moca_specid") or args.get("specid") or "",
        args.get("pipeline_version") or args.get("pipeline") or "",
        args.get("moca_mgridid") or args.get("mgridid") or "",
        args.get("moca_instid") or args.get("instid") or "",
        args.get("include_ignored") or args.get("show_ignored") or "",
        args.get("has_literature_rv") or args.get("literature_rv") or args.get("lit_rv") or "",
        args.get("wavelength_coverage") or args.get("wv_coverage") or args.get("coverage") or args.get("wavelength") or "",
        args.get("min_segments") or args.get("min_segment_count") or args.get("min_available_segments") or "",
        args.get("max_segments") or args.get("max_segment_count") or args.get("max_available_segments") or "",
        args.get("min_run_snr") or args.get("min_run_median_snr") or args.get("min_median_snr") or args.get("min_median_snr_per_pix") or "",
        args.get("max_lsf") or "",
        args.get("max_best_chi2") or "",
        args.get("max_rv_unc") or "",
        args.get("min_data_contrast") or "",
        args.get("min_model_contrast") or "",
        args.get("min_model_10p") or "",
        args.get("min_snr") or "",
        args.get("segment_wavelength") or args.get("segment_wavelength_range") or args.get("segment_wv") or args.get("segment_wv_range") or "",
        args.get("max_masked_outliers") or args.get("max_noutliers_masked") or "",
        limit,
    )
    now = time.time()
    cached = _RVBAM_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        ok, missing = _rvbam_required_tables_available(conn)
        if not ok:
            return {
                "runs": [],
                "value": None,
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "run_count": 0,
                    "private_db": _is_private_db(args),
                    "missing_tables": missing,
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
        private_db = _is_private_db(args)
        has_literature_filter = _rvbam_has_literature_rv_filter(args)
        if has_literature_filter:
            literature_exists_sql = _rvbam_literature_exists_sql(conn, private_db)
            literature_select_sql = """
                1 AS has_literature_rv,
                NULL AS literature_modified_timestamp,
            """
            literature_join_clause = ""
        else:
            literature_exists_sql = None
            literature_select_sql = """
                0 AS has_literature_rv,
                NULL AS literature_modified_timestamp,
            """
            literature_join_clause = ""
        where_sql, params = _rvbam_run_filter_sql(
            args,
            use_segment_summary=False,
            literature_exists_sql=literature_exists_sql,
        )
        rows = _records(_read_sql(conn, f"""
            SELECT
                r.moca_rv_sample_run_id,
                r.moca_oid,
                mo.designation,
                r.moca_instid,
                r.moca_specid,
                ms.spectrum_name,
                ms.data_collection_date,
                ms.epoch_mjd,
                ms.median_snr_per_pix,
                ms.median_snr_per_res_element,
                r.moca_mgridid,
                r.moca_fsid,
                r.datadir,
                r.pipeline_version,
                r.target_name,
                r.template_name,
                r.nwindows,
                r.nsegments,
                r.npoints,
                r.berv_kms,
                r.berv_kms_unc,
                r.window_ranges,
                r.origin,
                r.rls,
                r.is_public,
                r.ignored,
                r.created_timestamp,
                r.modified_timestamp,
                {literature_select_sql}
                NULL AS rvbam_segment_summary_placeholder
            FROM pcat_rv_sampling_runs r
            LEFT JOIN moca_objects mo
                ON mo.moca_oid = r.moca_oid
            LEFT JOIN moca_spectra ms
                ON ms.moca_specid = r.moca_specid
            {literature_join_clause}
            {where_sql}
            ORDER BY r.modified_timestamp DESC, r.moca_rv_sample_run_id DESC
            LIMIT {limit}
        """, params))
        segment_summaries = _rvbam_segment_summaries_from_db(
            conn,
            [row.get("moca_rv_sample_run_id") for row in rows],
            include_ignored=_as_bool(args.get("include_ignored") or args.get("show_ignored")),
        )
        for row in rows:
            row.pop("rvbam_segment_summary_placeholder", None)
            try:
                row_id = int(row.get("moca_rv_sample_run_id"))
            except (TypeError, ValueError):
                row_id = -1
            row.update(segment_summaries.get(row_id) or _rvbam_empty_segment_summary())
        skipped_count_filters: list[str] = []
        if _rvbam_comparison_segment_filters_active(args):
            filtered_counts, skipped_count_filters = _rvbam_filtered_segment_counts_from_db(
                conn,
                [row.get("moca_rv_sample_run_id") for row in rows],
                args,
                include_ignored=_as_bool(args.get("include_ignored") or args.get("show_ignored")),
            )
            for row in rows:
                row["unfiltered_available_segment_count"] = row.get("available_segment_count")
                try:
                    row_id = int(row.get("moca_rv_sample_run_id"))
                except (TypeError, ValueError):
                    row_id = -1
                filtered_count = int(filtered_counts.get(row_id, 0))
                row["available_segment_count"] = filtered_count
                row["segment_filter_available_count"] = filtered_count
        min_segments = _rvbam_segment_count_filter_arg(args, "min", "min_segments", "min_segment_count", "min_available_segments")
        if min_segments is not None:
            rows = [row for row in rows if int(row.get("available_segment_count") or 0) >= int(min_segments)]
        max_segments = _rvbam_segment_count_filter_arg(args, "max", "max_segments", "max_segment_count", "max_available_segments")
        if max_segments is not None:
            rows = [row for row in rows if int(row.get("available_segment_count") or 0) <= int(max_segments)]
        min_run_snr = _safe_float(
            args.get("min_run_snr")
            or args.get("min_run_median_snr")
            or args.get("min_median_snr")
            or args.get("min_median_snr_per_pix")
        )
        if min_run_snr is not None:
            rows = [
                row
                for row in rows
                if (_safe_float(row.get("median_snr_per_pix")) is not None)
                and float(_safe_float(row.get("median_snr_per_pix")) or 0.0) >= min_run_snr
            ]

    selected = _rvbam_int_arg(args, "run_id", "moca_rv_sample_run_id")
    if selected is not None and not any(row.get("moca_rv_sample_run_id") == selected for row in rows):
        selected = None
    payload = {
        "runs": rows,
        "value": selected or (rows[0]["moca_rv_sample_run_id"] if rows else None),
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "run_count": len(rows),
            "private_db": _is_private_db(args),
            "segment_count_filters_skipped": skipped_count_filters,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _RVBAM_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _rvbam_literature_rv_payload(row: dict[str, Any], source: str, target_moca_oid: int) -> dict[str, Any]:
    value = row.get("radial_velocity_kms")
    uncertainty = row.get("radial_velocity_kms_unc")
    literature_moca_oid = row.get("literature_moca_oid")
    host_moca_oid = row.get("host_moca_oid") if source == "host" else None
    return {
        "source": source,
        "label": "Literature host RV" if source == "host" else "Literature RV",
        "moca_oid": literature_moca_oid,
        "target_moca_oid": target_moca_oid,
        "host_moca_oid": host_moca_oid,
        "designation": row.get("literature_designation"),
        "radial_velocity_kms": value,
        "radial_velocity_kms_unc": uncertainty,
        "n_measurements": row.get("n_measurements"),
        "n_epochs": row.get("n_epochs"),
        "is_public": row.get("is_public"),
    }


def _rvbam_literature_rv_from_db(conn, args: dict[str, Any], moca_oid: Any) -> dict[str, Any] | None:
    try:
        target_moca_oid = int(moca_oid)
    except (TypeError, ValueError):
        return None
    if not _db_table_exists(conn, "calc_radial_velocities_combined"):
        return None

    private_db = _is_private_db(args)
    preferred_is_public = 0 if private_db else 1
    crv_public_clause = "" if private_db else "AND crv.is_public = 1"
    params = {
        "moca_oid": target_moca_oid,
        "preferred_is_public": preferred_is_public,
    }
    object_rows = _records(_read_sql(conn, f"""
        SELECT
            crv.moca_oid AS literature_moca_oid,
            mo.designation AS literature_designation,
            crv.radial_velocity_kms,
            crv.radial_velocity_kms_unc,
            crv.n_measurements,
            crv.n_epochs,
            crv.is_public
        FROM calc_radial_velocities_combined crv
        LEFT JOIN moca_objects mo
            ON mo.moca_oid = crv.moca_oid
        WHERE crv.moca_oid = :moca_oid
            AND crv.radial_velocity_kms IS NOT NULL
            AND COALESCE(crv.ignored, 0) = 0
            {crv_public_clause}
        ORDER BY
            CASE WHEN crv.is_public = :preferred_is_public THEN 0 ELSE 1 END,
            crv.id DESC
        LIMIT 1
    """, params))
    if object_rows:
        return _rvbam_literature_rv_payload(object_rows[0], "object", target_moca_oid)

    if not _db_table_exists(conn, "moca_companions"):
        return None
    companion_public_clause = "" if private_db else "AND mc.is_public = 1"
    host_rows = _records(_read_sql(conn, f"""
        SELECT
            crv.moca_oid AS literature_moca_oid,
            mo.designation AS literature_designation,
            mc.moca_oid_parent AS host_moca_oid,
            crv.radial_velocity_kms,
            crv.radial_velocity_kms_unc,
            crv.n_measurements,
            crv.n_epochs,
            crv.is_public
        FROM moca_companions mc
        JOIN calc_radial_velocities_combined crv
            ON crv.moca_oid = mc.moca_oid_parent
        LEFT JOIN moca_objects mo
            ON mo.moca_oid = mc.moca_oid_parent
        WHERE mc.moca_oid_child = :moca_oid
            AND COALESCE(mc.ignored, 0) = 0
            AND crv.radial_velocity_kms IS NOT NULL
            AND COALESCE(crv.ignored, 0) = 0
            {companion_public_clause}
            {crv_public_clause}
        ORDER BY
            CASE WHEN crv.is_public = :preferred_is_public THEN 0 ELSE 1 END,
            mc.moca_cid,
            crv.id DESC
        LIMIT 1
    """, params))
    if host_rows:
        return _rvbam_literature_rv_payload(host_rows[0], "host", target_moca_oid)
    return None


def _rvbam_unique_int_values(values: Sequence[Any]) -> list[int]:
    output: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        output.append(parsed)
    return output


def _rvbam_placeholders(prefix: str, values: Sequence[int]) -> tuple[str, dict[str, int]]:
    params = {f"{prefix}_{index}": int(value) for index, value in enumerate(values)}
    return ", ".join(f":{key}" for key in params), params


def _rvbam_unavailable_comparison_filters(conn: Any, args: dict[str, Any]) -> list[str]:
    filters = _rvbam_comparison_segment_filters(args)
    segment_columns = _db_table_columns(conn, "pcat_rv_sampling_segments")
    checks = [
        ("min_data_contrast", "data_contrast", filters["min_data_contrast"]),
        ("min_model_contrast", "model_contrast", filters["min_model_contrast"]),
        ("min_model_10p", "nmodel_10p_contrast", filters["min_model_10p"]),
        ("min_snr", "segment_snr_median", filters["min_snr"]),
        ("max_masked_outliers", "noutliers_masked", filters["max_masked_outliers"]),
    ]
    return [
        filter_name
        for filter_name, column_name, value in checks
        if value is not None and column_name not in segment_columns
    ]


def _rvbam_args_without_comparison_filters(args: dict[str, Any], filter_names: Sequence[str]) -> dict[str, Any]:
    if not filter_names:
        return args
    aliases = {
        "min_data_contrast": ("min_data_contrast",),
        "min_model_contrast": ("min_model_contrast",),
        "min_model_10p": ("min_model_10p",),
        "min_snr": ("min_snr",),
        "max_masked_outliers": ("max_masked_outliers", "max_noutliers_masked"),
    }
    output = dict(args)
    for filter_name in filter_names:
        for alias in aliases.get(filter_name, (filter_name,)):
            output.pop(alias, None)
    return output


def _rvbam_literature_rvs_from_db(
    conn: Any,
    args: dict[str, Any],
    moca_oids: Sequence[Any],
) -> dict[int, dict[str, Any]]:
    target_oids = _rvbam_unique_int_values(moca_oids)
    if not target_oids or not _db_table_exists(conn, "calc_radial_velocities_combined"):
        return {}

    private_db = _is_private_db(args)
    preferred_is_public = 0 if private_db else 1
    crv_public_clause = "" if private_db else "AND crv.is_public = 1"
    placeholders, params = _rvbam_placeholders("lit_oid", target_oids)
    params["preferred_is_public"] = preferred_is_public
    object_rows = _records(_read_sql(conn, f"""
        SELECT
            crv.moca_oid AS target_moca_oid,
            crv.moca_oid AS literature_moca_oid,
            mo.designation AS literature_designation,
            crv.radial_velocity_kms,
            crv.radial_velocity_kms_unc,
            crv.n_measurements,
            crv.n_epochs,
            crv.is_public,
            crv.id AS radial_velocity_id
        FROM calc_radial_velocities_combined crv
        LEFT JOIN moca_objects mo
            ON mo.moca_oid = crv.moca_oid
        WHERE crv.moca_oid IN ({placeholders})
            AND crv.radial_velocity_kms IS NOT NULL
            AND COALESCE(crv.ignored, 0) = 0
            {crv_public_clause}
        ORDER BY
            crv.moca_oid,
            CASE WHEN crv.is_public = :preferred_is_public THEN 0 ELSE 1 END,
            crv.id DESC
    """, params))

    literature_by_oid: dict[int, dict[str, Any]] = {}
    for row in object_rows:
        target_oid = _safe_float(row.get("target_moca_oid"))
        if target_oid is None:
            continue
        key = int(target_oid)
        if key not in literature_by_oid:
            literature_by_oid[key] = _rvbam_literature_rv_payload(row, "object", key)

    missing_oids = [oid for oid in target_oids if oid not in literature_by_oid]
    if not missing_oids or not _db_table_exists(conn, "moca_companions"):
        return literature_by_oid

    companion_public_clause = "" if private_db else "AND COALESCE(mc.is_public, 0) = 1"
    host_placeholders, host_params = _rvbam_placeholders("lit_host_oid", missing_oids)
    host_params["preferred_is_public"] = preferred_is_public
    host_rows = _records(_read_sql(conn, f"""
        SELECT
            mc.moca_oid_child AS target_moca_oid,
            crv.moca_oid AS literature_moca_oid,
            mo.designation AS literature_designation,
            mc.moca_oid_parent AS host_moca_oid,
            crv.radial_velocity_kms,
            crv.radial_velocity_kms_unc,
            crv.n_measurements,
            crv.n_epochs,
            crv.is_public,
            mc.moca_cid,
            crv.id AS radial_velocity_id
        FROM moca_companions mc
        JOIN calc_radial_velocities_combined crv
            ON crv.moca_oid = mc.moca_oid_parent
        LEFT JOIN moca_objects mo
            ON mo.moca_oid = mc.moca_oid_parent
        WHERE mc.moca_oid_child IN ({host_placeholders})
            AND COALESCE(mc.ignored, 0) = 0
            AND crv.radial_velocity_kms IS NOT NULL
            AND COALESCE(crv.ignored, 0) = 0
            {companion_public_clause}
            {crv_public_clause}
        ORDER BY
            mc.moca_oid_child,
            CASE WHEN crv.is_public = :preferred_is_public THEN 0 ELSE 1 END,
            mc.moca_cid,
            crv.id DESC
    """, host_params))
    for row in host_rows:
        target_oid = _safe_float(row.get("target_moca_oid"))
        if target_oid is None:
            continue
        key = int(target_oid)
        if key not in literature_by_oid:
            literature_by_oid[key] = _rvbam_literature_rv_payload(row, "host", key)
    return literature_by_oid


def _rvbam_comparison_segments_from_db(
    conn: Any,
    run_ids: Sequence[Any],
    args: dict[str, Any],
    *,
    include_ignored: bool = False,
) -> tuple[dict[int, list[dict[str, Any]]], list[str]]:
    unique_run_ids = _rvbam_unique_int_values(run_ids)
    if not unique_run_ids:
        return {}, []

    placeholders, params = _rvbam_placeholders("lit_seg_run", unique_run_ids)
    segment_columns = _db_table_columns(conn, "pcat_rv_sampling_segments")
    optional_columns = [
        "data_contrast",
        "model_contrast",
        "nmodel_10p_contrast",
        "segment_snr_median",
        "noutliers_masked",
    ]
    optional_select = [
        f"s.{column}" if column in segment_columns else f"NULL AS {column}"
        for column in optional_columns
    ]
    ignored_clause = "" if include_ignored else "AND COALESCE(s.ignored, 0) = 0"
    rows = _records(_read_sql(conn, f"""
        SELECT
            s.moca_rv_sampling_segment_id,
            s.moca_rv_sample_run_id,
            s.moca_sample_run_id,
            s.order_number,
            s.window_number,
            s.segment_number,
            s.wv_min,
            s.wv_max,
            s.wv_center,
            s.rv_kms,
            s.rv_kms_unc,
            s.lsf,
            s.lsf_unc,
            s.vsini_kms,
            s.vsini_kms_unc,
            s.ignored,
            s.created_timestamp,
            s.modified_timestamp,
            sr.best_chi2,
            {", ".join(optional_select)}
        FROM pcat_rv_sampling_segments s
        LEFT JOIN pcat_sampling_runs sr
            ON sr.moca_sample_run_id = s.moca_sample_run_id
        WHERE s.moca_rv_sample_run_id IN ({placeholders})
            {ignored_clause}
        ORDER BY s.moca_rv_sample_run_id, s.order_number, s.window_number, s.segment_number, s.wv_min, s.moca_rv_sampling_segment_id
    """, params))
    segments_by_run: dict[int, list[dict[str, Any]]] = {run_id: [] for run_id in unique_run_ids}
    for row in rows:
        run_id = _safe_float(row.get("moca_rv_sample_run_id"))
        if run_id is None:
            continue
        segments_by_run.setdefault(int(run_id), []).append(row)
    return segments_by_run, _rvbam_unavailable_comparison_filters(conn, args)


def _rvbam_spectrum_from_db(conn, moca_specid: Any) -> dict[str, Any]:
    try:
        specid = int(moca_specid)
    except (TypeError, ValueError):
        return {}
    if not _db_table_exists(conn, "moca_spectra"):
        return {}
    rows = _records(_read_sql(conn, """
        SELECT *
        FROM moca_spectra
        WHERE moca_specid = :specid
        LIMIT 1
    """, {"specid": specid}))
    return rows[0] if rows else {}


def _load_rvbam_run_from_db(args: dict[str, Any], run_id: int) -> dict[str, Any]:
    cache_key = _rvbam_cache_key(args, "run", run_id, args.get("include_ignored") or args.get("show_ignored") or "")
    now = time.time()
    cached = _RVBAM_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        ok, missing = _rvbam_required_tables_available(conn)
        if not ok:
            return {
                "run": {},
                "segments": [],
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "segment_count": 0,
                    "private_db": _is_private_db(args),
                    "missing_tables": missing,
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
        run_rows = _records(_read_sql(conn, """
            SELECT
                r.*,
                mo.designation,
                ms.spectrum_name,
                ms.data_collection_date,
                ms.epoch_mjd,
                ms.min_wavelength_angstrom,
                ms.max_wavelength_angstrom,
                ms.median_spectral_resolving_power,
                ms.berv_corrected,
                ms.spacecraft_rv_corrected
            FROM pcat_rv_sampling_runs r
            LEFT JOIN moca_objects mo
                ON mo.moca_oid = r.moca_oid
            LEFT JOIN moca_spectra ms
                ON ms.moca_specid = r.moca_specid
            WHERE r.moca_rv_sample_run_id = :run_id
        """, {"run_id": int(run_id)}))
        run = run_rows[0] if run_rows else {}
        if not run:
            return {
                "run": {},
                "segments": [],
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "segment_count": 0,
                    "private_db": _is_private_db(args),
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
        ignored_clause = "" if _as_bool(args.get("include_ignored") or args.get("show_ignored")) else "AND COALESCE(s.ignored, 0) = 0"
        segments = _records(_read_sql(conn, f"""
            SELECT
                s.moca_rv_sampling_segment_id,
                s.moca_rv_sample_run_id,
                s.moca_sample_run_id,
                s.order_number,
                s.window_number,
                s.segment_number,
                s.wv_min,
                s.wv_max,
                s.wv_center,
                s.rv_kms,
                s.rv_kms_unc,
                s.lsf,
                s.lsf_unc,
                s.vsini_kms,
                s.vsini_kms_unc,
                s.moca_fsid,
                s.moca_rvsysid,
                s.origin,
                s.rls,
                s.is_public,
                s.ignored,
                s.created_timestamp,
                s.modified_timestamp,
                s.comments,
                sr.sampler_type,
                sr.sampler_name,
                sr.sampler_variant,
                sr.sampler_version,
                sr.pipeline_version AS sampling_pipeline_version,
                sr.n_parameters,
                sr.n_walkers,
                sr.n_iterations,
                sr.burnin_iterations,
                sr.thinning_interval,
                sr.convergence_criterion,
                sr.rhat_max,
                sr.ess_min,
                sr.autocorr_time_max,
                sr.mean_acceptance_rate,
                sr.best_chi2,
                sr.lnp_avg,
                sr.lnp_median,
                sr.lnp_std,
                sr.lnp_max,
                sr.mean_finite_fraction,
                sr.mean_outofbounds_fraction,
                sr.random_seed,
                fig.model_fit_url,
                fig.corner_url,
                COALESCE(params.param_count, 0) AS param_count,
                COALESCE(params.free_param_count, 0) AS free_param_count,
                COALESCE(payloads.payload_count, 0) AS payload_count,
                COALESCE(payloads.chain_payloads, 0) AS chain_payloads,
                COALESCE(payloads.lnp_payloads, 0) AS lnp_payloads,
                payloads.total_stored_samples
            FROM pcat_rv_sampling_segments s
            LEFT JOIN pcat_sampling_runs sr
                ON sr.moca_sample_run_id = s.moca_sample_run_id
            LEFT JOIN (
                SELECT
                    mfs.moca_fsid,
                    MAX(CASE WHEN mfs.description = 'RVBAM model fit' THEN mf.url ELSE NULL END) AS model_fit_url,
                    MAX(CASE WHEN mfs.description = 'RVBAM corner plot' THEN mf.url ELSE NULL END) AS corner_url
                FROM mechanics_file_sets mfs
                JOIN mechanics_files mf
                    ON mf.moca_fid = mfs.moca_fid
                WHERE mfs.description IN ('RVBAM model fit', 'RVBAM corner plot')
                GROUP BY mfs.moca_fsid
            ) fig
                ON fig.moca_fsid = s.moca_fsid
            LEFT JOIN (
                SELECT
                    moca_sample_run_id,
                    COUNT(*) AS param_count,
                    SUM(CASE WHEN COALESCE(is_fixed, 0) = 0 THEN 1 ELSE 0 END) AS free_param_count
                FROM pcat_sampling_parameters
                GROUP BY moca_sample_run_id
            ) params
                ON params.moca_sample_run_id = s.moca_sample_run_id
            LEFT JOIN (
                SELECT
                    moca_sample_run_id,
                    COUNT(*) AS payload_count,
                    SUM(CASE WHEN payload_kind = 'chains' THEN 1 ELSE 0 END) AS chain_payloads,
                    SUM(CASE WHEN payload_kind = 'lnp' THEN 1 ELSE 0 END) AS lnp_payloads,
                    SUM(COALESCE(n_stored_samples, 0)) AS total_stored_samples
                FROM pcat_sampling_payloads
                GROUP BY moca_sample_run_id
            ) payloads
                ON payloads.moca_sample_run_id = s.moca_sample_run_id
            WHERE s.moca_rv_sample_run_id = :run_id
                {ignored_clause}
            ORDER BY s.order_number, s.window_number, s.segment_number, s.wv_min, s.moca_rv_sampling_segment_id
        """, {"run_id": int(run_id)}))
        rv_content_meta = _rvbam_enrich_segments_rv_content(conn, run, segments)
        literature_rv = _rvbam_literature_rv_from_db(conn, args, run.get("moca_oid"))
        spectrum = _rvbam_spectrum_from_db(conn, run.get("moca_specid"))

    timestamp_summary = _rvbam_segment_timestamp_summary(segments)
    run.update(timestamp_summary)
    run["has_literature_rv"] = 1 if literature_rv else 0
    run["berv_metadata"] = _rvbam_berv_metadata_from_comments(run.get("comments"))
    for segment in segments:
        segment["berv_metadata"] = _rvbam_berv_metadata_from_comments(segment.get("comments"))
    payload = {
        "run": run,
        "segments": segments,
        "literatureRv": literature_rv,
        "spectrum": spectrum,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "segment_count": len(segments),
            "private_db": _is_private_db(args),
            "rv_content_diagnostics": rv_content_meta,
            **timestamp_summary,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _RVBAM_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _load_rvbam_literature_comparison_from_db(args: dict[str, Any]) -> dict[str, Any]:
    limit = _rvbam_limit_arg(args, "limit", 250, 1000)
    cache_key = _rvbam_cache_key(
        args,
        "literature-comparison-v2",
        args.get("q") or args.get("search") or "",
        args.get("moca_oid") or args.get("oid") or "",
        args.get("moca_specid") or args.get("specid") or "",
        args.get("pipeline_version") or args.get("pipeline") or "",
        args.get("moca_mgridid") or args.get("mgridid") or "",
        args.get("moca_instid") or args.get("instid") or "",
        args.get("include_ignored") or args.get("show_ignored") or "",
        args.get("has_literature_rv") or args.get("literature_rv") or args.get("lit_rv") or "",
        args.get("wavelength_coverage") or args.get("wv_coverage") or args.get("coverage") or args.get("wavelength") or "",
        args.get("min_segments") or args.get("min_segment_count") or args.get("min_available_segments") or "",
        args.get("max_segments") or args.get("max_segment_count") or args.get("max_available_segments") or "",
        args.get("min_run_snr") or args.get("min_run_median_snr") or args.get("min_median_snr") or args.get("min_median_snr_per_pix") or "",
        args.get("max_lsf") or "",
        args.get("max_best_chi2") or "",
        args.get("max_rv_unc") or "",
        args.get("min_data_contrast") or "",
        args.get("min_model_contrast") or "",
        args.get("min_model_10p") or "",
        args.get("min_snr") or "",
        args.get("segment_wavelength") or args.get("segment_wavelength_range") or args.get("segment_wv") or args.get("segment_wv_range") or "",
        args.get("max_masked_outliers") or args.get("max_noutliers_masked") or "",
        limit,
    )
    now = time.time()
    cached = _RVBAM_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    run_args = dict(args)
    run_args["limit"] = str(limit)
    run_payload = _load_rvbam_runs_from_db(run_args)
    points: list[dict[str, Any]] = []
    bias_points: list[dict[str, Any]] = []
    skipped: dict[str, int] = {
        "no_literature_rv": 0,
        "no_kept_segments": 0,
        "no_segment_rv": 0,
        "errors": 0,
    }
    bias_skipped: dict[str, int] = {
        "no_literature_rv": 0,
        "no_kept_segments": 0,
        "no_segment_rv": 0,
        "no_epoch": 0,
    }
    errors: list[dict[str, Any]] = []
    runs = run_payload.get("runs") or []
    skipped_segment_filters: list[str] = []
    segments_by_run: dict[int, list[dict[str, Any]]] = {}
    literature_by_oid: dict[int, dict[str, Any]] = {}
    if runs:
        engine = _engine(_connection_string(args))
        with engine.connect() as conn:
            segments_by_run, skipped_segment_filters = _rvbam_comparison_segments_from_db(
                conn,
                [run.get("moca_rv_sample_run_id") for run in runs],
                args,
                include_ignored=_as_bool(args.get("include_ignored") or args.get("show_ignored")),
            )
            literature_by_oid = _rvbam_literature_rvs_from_db(
                conn,
                args,
                [run.get("moca_oid") for run in runs],
            )
    comparison_args = _rvbam_args_without_comparison_filters(args, skipped_segment_filters)

    for run in runs:
        run_id = _rvbam_int_arg({"run_id": run.get("moca_rv_sample_run_id")}, "run_id")
        if run_id is None:
            skipped["errors"] += 1
            continue
        try:
            run_payload_row = run
            segment_payload = segments_by_run.get(int(run_id), [])
            moca_oid = _safe_float(run.get("moca_oid"))
            literature_rv = literature_by_oid.get(int(moca_oid)) if moca_oid is not None else None
            point, reason = _rvbam_literature_comparison_point(
                run_payload_row,
                segment_payload,
                literature_rv,
                comparison_args,
            )
            run_bias_points, run_bias_skipped = _rvbam_literature_bias_segment_points(
                run_payload_row,
                segment_payload,
                literature_rv,
                comparison_args,
            )
            bias_points.extend(run_bias_points)
            for key, count in run_bias_skipped.items():
                bias_skipped[key] = bias_skipped.get(key, 0) + int(count)
        except Exception as exc:
            skipped["errors"] += 1
            if len(errors) < 12:
                errors.append({
                    "moca_rv_sample_run_id": run_id,
                    "error": f"{type(exc).__name__}: {exc}",
                })
            continue
        if point:
            points.append(point)
        elif reason:
            skipped[reason] = skipped.get(reason, 0) + 1

    payload = {
        "points": points,
        "biasPoints": bias_points,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "candidate_run_count": len(run_payload.get("runs") or []),
            "point_count": len(points),
            "bias_point_count": len(bias_points),
            "run_limit": limit,
            "skipped": skipped,
            "bias_skipped": bias_skipped,
            "errors": errors,
            "private_db": _is_private_db(args),
            "runs_cache": run_payload.get("cache") or {},
            "comparison_mode": "batched_light_segments",
            "segment_filter_columns_skipped": skipped_segment_filters,
            "missing_tables": (run_payload.get("meta") or {}).get("missing_tables"),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _RVBAM_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _rvbam_segment_images(conn, moca_fsid: int | None) -> dict[str, str]:
    if moca_fsid is None:
        return {"model_fit_url": "", "corner_url": ""}
    rows = _records(_read_sql(conn, """
        SELECT
            mfs.description,
            MIN(mf.url) AS url
        FROM mechanics_file_sets mfs
        JOIN mechanics_files mf
            ON mf.moca_fid = mfs.moca_fid
        WHERE mfs.moca_fsid = :moca_fsid
            AND mfs.description IN ('RVBAM model fit', 'RVBAM corner plot')
        GROUP BY mfs.description
    """, {"moca_fsid": int(moca_fsid)}))
    by_description = {str(row.get("description") or ""): str(row.get("url") or "") for row in rows}
    return {
        "model_fit_url": by_description.get("RVBAM model fit", ""),
        "corner_url": by_description.get("RVBAM corner plot", ""),
    }


def _load_rvbam_segment_from_db(args: dict[str, Any], segment_id: int) -> dict[str, Any]:
    cache_key = _rvbam_cache_key(args, "segment", segment_id)
    now = time.time()
    cached = _RVBAM_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        _rvbam_refresh_local_model_status(payload)
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        ok, missing = _rvbam_required_tables_available(conn)
        if not ok:
            return {
                "segment": {},
                "run": {},
                "samplingRun": {},
                "parameters": [],
                "payloads": [],
                "images": {"model_fit_url": "", "corner_url": ""},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "private_db": _is_private_db(args),
                    "missing_tables": missing,
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
        rows = _records(_read_sql(conn, """
            SELECT
                s.*,
                r.moca_oid,
                mo.designation,
                r.moca_instid,
                r.moca_specid,
                ms.spectrum_name,
                r.moca_mgridid,
                r.pipeline_version AS rv_pipeline_version,
                r.target_name,
                r.template_name,
                r.berv_kms,
                r.berv_kms_unc,
                r.comments AS run_comments,
                r.nwindows,
                r.nsegments,
                r.npoints AS run_npoints,
                r.window_ranges,
                r.datadir,
                r.origin AS run_origin,
                r.ignored AS run_ignored,
                ms.berv_corrected,
                ms.spacecraft_rv_corrected,
                sr.sampler_type,
                sr.sampler_name,
                sr.sampler_variant,
                sr.sampler_version,
                sr.pipeline_version AS sampling_pipeline_version,
                sr.n_parameters,
                sr.n_walkers,
                sr.n_iterations,
                sr.burnin_iterations,
                sr.thinning_interval,
                sr.convergence_criterion,
                sr.rhat_max,
                sr.ess_min,
                sr.autocorr_time_max,
                sr.mean_acceptance_rate,
                sr.best_chi2,
                sr.lnp_avg,
                sr.lnp_median,
                sr.lnp_std,
                sr.lnp_max,
                sr.mean_finite_fraction,
                sr.mean_outofbounds_fraction,
                sr.random_seed,
                sr.origin AS sampling_origin,
                sr.ignored AS sampling_ignored,
                sr.comments AS sampling_comments
            FROM pcat_rv_sampling_segments s
            JOIN pcat_rv_sampling_runs r
                ON r.moca_rv_sample_run_id = s.moca_rv_sample_run_id
            LEFT JOIN moca_objects mo
                ON mo.moca_oid = r.moca_oid
            LEFT JOIN moca_spectra ms
                ON ms.moca_specid = r.moca_specid
            LEFT JOIN pcat_sampling_runs sr
                ON sr.moca_sample_run_id = s.moca_sample_run_id
            WHERE s.moca_rv_sampling_segment_id = :segment_id
        """, {"segment_id": int(segment_id)}))
        row = rows[0] if rows else {}
        if not row:
            return {
                "segment": {},
                "run": {},
                "samplingRun": {},
                "parameters": [],
                "payloads": [],
                "images": {"model_fit_url": "", "corner_url": ""},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "private_db": _is_private_db(args),
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
        sample_run_id = row.get("moca_sample_run_id")
        parameters = _records(_read_sql(conn, """
            SELECT
                moca_sampling_parameter_id,
                moca_sample_run_id,
                param_name,
                param_index,
                units,
                mean_value,
                median_value,
                std_value,
                p16_value,
                p84_value,
                is_fixed,
                fixed_value,
                lower_bound,
                upper_bound,
                prior_type,
                prior_details,
                init_guess,
                proposal_scale,
                origin,
                rls,
                is_public,
                ignored,
                comments
            FROM pcat_sampling_parameters
            WHERE moca_sample_run_id = :sample_run_id
            ORDER BY param_index, param_name
        """, {"sample_run_id": int(sample_run_id)})) if sample_run_id is not None else []
        payloads = _records(_read_sql(conn, """
            SELECT
                moca_payload_id,
                moca_sample_run_id,
                moca_sampling_parameter_id,
                payload_kind,
                payload_subkind,
                dtype,
                compression,
                order_comment,
                n_dim,
                dim1,
                dim2,
                dim3,
                dim4,
                burnin_iterations,
                thinning_interval,
                n_stored_samples,
                series_count,
                origin,
                rls,
                is_public,
                ignored,
                comments
            FROM pcat_sampling_payloads
            WHERE moca_sample_run_id = :sample_run_id
            ORDER BY payload_kind, payload_subkind, moca_payload_id
        """, {"sample_run_id": int(sample_run_id)})) if sample_run_id is not None else []
        images = _rvbam_segment_images(conn, row.get("moca_fsid"))
        rv_content_meta = _rvbam_enrich_segments_rv_content(conn, row, [row])

    segment_keys = [
        "moca_rv_sampling_segment_id", "moca_rv_sample_run_id", "moca_sample_run_id",
        "order_number", "window_number", "segment_number", "wv_min", "wv_max", "wv_center",
        "rv_kms", "rv_kms_unc", "lsf", "lsf_unc", "vsini_kms", "vsini_kms_unc",
        "moca_fsid", "moca_rvsysid", "origin", "rls", "is_public", "ignored",
        "created_timestamp", "modified_timestamp",
        "data_contrast", "model_contrast", "nmodel_10p_contrast", "noutliers_masked",
        "segment_snr_median", "segment_snr_p10", "segment_snr_p90", "segment_snr_npoints",
        "comments",
    ]
    run_keys = [
        "moca_rv_sample_run_id", "moca_oid", "designation", "moca_instid", "moca_specid",
        "spectrum_name", "moca_mgridid", "rv_pipeline_version", "target_name", "template_name",
        "berv_kms", "berv_kms_unc", "run_comments", "berv_corrected", "spacecraft_rv_corrected",
        "nwindows", "nsegments", "run_npoints", "window_ranges", "datadir", "run_origin", "run_ignored",
    ]
    sampling_keys = [
        "moca_sample_run_id", "sampler_type", "sampler_name", "sampler_variant", "sampler_version",
        "sampling_pipeline_version", "n_parameters", "n_walkers", "n_iterations", "burnin_iterations",
        "thinning_interval", "convergence_criterion", "rhat_max", "ess_min", "autocorr_time_max",
        "mean_acceptance_rate", "best_chi2", "lnp_avg", "lnp_median", "lnp_std", "lnp_max",
        "mean_finite_fraction", "mean_outofbounds_fraction", "random_seed", "sampling_origin",
        "sampling_ignored", "sampling_comments",
    ]
    segment_payload = {key: row.get(key) for key in segment_keys if row.get(key) is not None}
    run_payload = {key: row.get(key) for key in run_keys if row.get(key) is not None}
    sampling_payload = {key: row.get(key) for key in sampling_keys if row.get(key) is not None}
    segment_payload["berv_metadata"] = _rvbam_berv_metadata_from_comments(segment_payload.get("comments"))
    run_payload["berv_metadata"] = _rvbam_berv_metadata_from_comments(run_payload.get("run_comments"))
    sampling_payload["berv_metadata"] = _rvbam_berv_metadata_from_comments(sampling_payload.get("sampling_comments"))
    for parameter in parameters:
        parameter["berv_metadata"] = _rvbam_berv_metadata_from_comments(parameter.get("comments"))
    for payload_row in payloads:
        payload_row["berv_metadata"] = _rvbam_berv_metadata_from_comments(payload_row.get("comments"))

    payload = {
        "segment": segment_payload,
        "run": run_payload,
        "samplingRun": sampling_payload,
        "parameters": parameters,
        "payloads": payloads,
        "images": images,
        "localModelFit": _rvbam_local_model_status(row.get("moca_mgridid"), row.get("template_name")),
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "parameter_count": len(parameters),
            "payload_count": len(payloads),
            "private_db": _is_private_db(args),
            "rv_content_diagnostics": rv_content_meta,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _RVBAM_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _rvbam_payload_dtype(dtype_name: Any) -> np.dtype:
    mapping = {
        "f4": np.dtype("float32"),
        "f8": np.dtype("float64"),
        "i4": np.dtype("int32"),
        "i8": np.dtype("int64"),
        "u4": np.dtype("uint32"),
        "u8": np.dtype("uint64"),
    }
    dtype = mapping.get(str(dtype_name or "f4").lower())
    if dtype is None:
        raise ValueError(f"Unsupported RVBAM payload dtype: {dtype_name}")
    return dtype


def _rvbam_payload_shape(row: dict[str, Any]) -> tuple[int, ...]:
    dims: list[int] = []
    n_dim = _safe_float(row.get("n_dim"))
    for key in ("dim1", "dim2", "dim3", "dim4"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            dim = int(value)
        except (TypeError, ValueError):
            continue
        if dim > 0:
            dims.append(dim)
    if n_dim is not None and int(n_dim) > 0:
        dims = dims[:int(n_dim)]
    return tuple(dims)


def _rvbam_array_cache_key(row: dict[str, Any]) -> str:
    return "|".join([
        "payload",
        str(row.get("moca_payload_id")),
        str(row.get("modified_timestamp") or ""),
        str(row.get("dtype") or ""),
        str(row.get("compression") or ""),
        str(row.get("dim1") or ""),
        str(row.get("dim2") or ""),
        str(row.get("dim3") or ""),
        str(row.get("dim4") or ""),
    ])


def _rvbam_prune_array_cache() -> None:
    now = time.time()
    expired = [key for key, (stamp, _array) in _RVBAM_ARRAY_CACHE.items() if now - stamp > RVBAM_ARRAY_CACHE_SECONDS]
    for key in expired:
        _RVBAM_ARRAY_CACHE.pop(key, None)
    while len(_RVBAM_ARRAY_CACHE) > RVBAM_ARRAY_CACHE_MAX_ITEMS:
        oldest = min(_RVBAM_ARRAY_CACHE, key=lambda item: _RVBAM_ARRAY_CACHE[item][0])
        _RVBAM_ARRAY_CACHE.pop(oldest, None)


def _decode_rvbam_payload_array(row: dict[str, Any]) -> np.ndarray:
    cache_key = _rvbam_array_cache_key(row)
    now = time.time()
    cached = _RVBAM_ARRAY_CACHE.get(cache_key)
    if cached and now - cached[0] < RVBAM_ARRAY_CACHE_SECONDS:
        return cached[1]

    raw = row.get("payload")
    if raw is None:
        raise ValueError("RVBAM payload row did not include the payload blob.")
    if isinstance(raw, memoryview):
        raw_bytes = raw.tobytes()
    else:
        raw_bytes = bytes(raw)

    compression = str(row.get("compression") or "none").lower()
    if compression == "gzip":
        raw_bytes = gzip.decompress(raw_bytes)
    elif compression == "zstd":
        try:
            import zstandard as zstd  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("zstd-compressed RVBAM payloads require the zstandard package.") from exc
        raw_bytes = zstd.ZstdDecompressor().decompress(raw_bytes)
    elif compression != "none":
        raise ValueError(f"Unsupported RVBAM payload compression: {compression}")

    dtype = _rvbam_payload_dtype(row.get("dtype"))
    array = np.frombuffer(raw_bytes, dtype=dtype).copy()
    shape = _rvbam_payload_shape(row)
    if shape:
        expected = int(np.prod(shape))
        if expected == array.size:
            array = array.reshape(shape)
    _RVBAM_ARRAY_CACHE[cache_key] = (now, array)
    _rvbam_prune_array_cache()
    return array


def _rvbam_fetch_chain_payload(conn, sample_run_id: int) -> dict[str, Any] | None:
    row = conn.execute(text("""
        SELECT
            moca_payload_id,
            moca_sample_run_id,
            moca_sampling_parameter_id,
            payload_kind,
            payload_subkind,
            dtype,
            compression,
            order_comment,
            n_dim,
            dim1,
            dim2,
            dim3,
            dim4,
            burnin_iterations,
            thinning_interval,
            n_stored_samples,
            series_count,
            modified_timestamp,
            payload
        FROM pcat_sampling_payloads
        WHERE moca_sample_run_id = :sample_run_id
            AND payload_kind = 'chains'
            AND COALESCE(ignored, 0) = 0
        ORDER BY
            CASE WHEN payload_subkind = 'posterior' THEN 0 ELSE 1 END,
            moca_payload_id
        LIMIT 1
    """), {"sample_run_id": int(sample_run_id)}).mappings().first()
    return dict(row) if row is not None else None


def _rvbam_fetch_vector_payload(conn, sample_run_id: int, payload_terms: tuple[str, ...]) -> dict[str, Any] | None:
    terms = tuple(str(term).lower() for term in payload_terms)
    row = conn.execute(text("""
        SELECT
            moca_payload_id,
            moca_sample_run_id,
            moca_sampling_parameter_id,
            payload_kind,
            payload_subkind,
            dtype,
            compression,
            order_comment,
            n_dim,
            dim1,
            dim2,
            dim3,
            dim4,
            burnin_iterations,
            thinning_interval,
            n_stored_samples,
            series_count,
            modified_timestamp,
            payload
        FROM pcat_sampling_payloads
        WHERE moca_sample_run_id = :sample_run_id
            AND COALESCE(ignored, 0) = 0
            AND (
                LOWER(COALESCE(payload_kind, '')) IN :terms
                OR LOWER(COALESCE(payload_subkind, '')) IN :terms
                OR LOWER(COALESCE(order_comment, '')) IN :terms
            )
        ORDER BY
            CASE
                WHEN LOWER(COALESCE(payload_subkind, '')) IN :terms THEN 0
                WHEN LOWER(COALESCE(payload_kind, '')) IN :terms THEN 1
                ELSE 2
            END,
            moca_payload_id
        LIMIT 1
    """).bindparams(bindparam("terms", expanding=True)), {
        "sample_run_id": int(sample_run_id),
        "terms": terms,
    }).mappings().first()
    return dict(row) if row is not None else None


def _rvbam_corner_weights(
    conn,
    sample_run_id: int,
    sample_count: int,
    live_points: Any = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    meta: dict[str, Any] = {"weights_source": "uniform fallback"}
    if sample_count <= 0:
        return np.array([], dtype=float), meta

    weights_payload = _rvbam_fetch_vector_payload(conn, sample_run_id, (
        "weights",
        "weight",
        "posterior_weights",
        "sample_weights",
    ))
    if weights_payload is not None:
        try:
            weights = np.asarray(_decode_rvbam_payload_array(weights_payload), dtype=float).reshape(-1)
            if weights.size == sample_count and np.isfinite(weights).any() and np.nansum(weights) > 0:
                meta = {
                    "weights_source": "stored weights payload",
                    "weights_payload_id": weights_payload.get("moca_payload_id"),
                    "weights_payload_kind": weights_payload.get("payload_kind"),
                    "weights_payload_subkind": weights_payload.get("payload_subkind"),
                }
                return weights, meta
        except Exception as exc:
            meta["weights_payload_error"] = f"{type(exc).__name__}: {exc}"

    logl_payload = _rvbam_fetch_vector_payload(conn, sample_run_id, (
        "logl",
        "lnp",
        "log_likelihood",
    ))
    if logl_payload is not None:
        try:
            logl = np.asarray(_decode_rvbam_payload_array(logl_payload), dtype=float).reshape(-1)
            if logl.size == sample_count and np.isfinite(logl).any():
                live = _safe_float(live_points)
                order = np.argsort(logl)
                if live is not None and live > 0 and logl.size > 1:
                    indices = np.arange(logl.size, dtype=float)
                    logx_prev = -indices / float(live)
                    logx_next = -(indices + 1.0) / float(live)
                    log_width = logx_prev + np.log1p(-np.exp(logx_next - logx_prev))
                    log_weight_sorted = log_width + logl[order]
                    weights = np.zeros(sample_count, dtype=float)
                    finite_sorted = np.isfinite(log_weight_sorted)
                    shifted = np.clip(log_weight_sorted[finite_sorted] - float(np.nanmax(log_weight_sorted[finite_sorted])), -745.0, 50.0)
                    weights[order[finite_sorted]] = np.exp(shifted)
                    source = f"nested logl fallback (live_points={int(live)})"
                else:
                    weights = np.zeros(sample_count, dtype=float)
                    finite = np.isfinite(logl)
                    shifted = np.clip(logl[finite] - float(np.nanmax(logl[finite])), -745.0, 50.0)
                    weights[finite] = np.exp(shifted)
                    source = "exp(logl - max(logl)) fallback"
                if np.sum(weights) > 0:
                    meta = {
                        "weights_source": source,
                        "weights_payload_id": logl_payload.get("moca_payload_id"),
                        "weights_payload_kind": logl_payload.get("payload_kind"),
                        "weights_payload_subkind": logl_payload.get("payload_subkind"),
                    }
                    return weights, meta
        except Exception as exc:
            meta["logl_payload_error"] = f"{type(exc).__name__}: {exc}"

    return np.ones(sample_count, dtype=float), meta


def _rvbam_apply_corner_keep_weight(
    samples: np.ndarray,
    weights: np.ndarray,
    keep_weight: float,
) -> tuple[np.ndarray, np.ndarray]:
    if not (0.0 < keep_weight < 1.0):
        return samples, weights
    finite = np.isfinite(weights) & (weights > 0)
    if not np.any(finite):
        return samples, weights
    samples = samples[finite]
    weights = weights[finite]
    order = np.argsort(weights)[::-1]
    sorted_weights = weights[order]
    cumulative = np.cumsum(sorted_weights)
    if cumulative[-1] <= 0:
        return samples, weights
    cutoff = keep_weight * cumulative[-1]
    keep_n = int(np.searchsorted(cumulative, cutoff, side="left") + 1)
    keep_idx = order[:keep_n]
    return samples[keep_idx], weights[keep_idx]


def _rvbam_chain_matrix(array: np.ndarray, parameters: list[dict[str, Any]]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    if array.size == 0:
        return np.empty((0, 0), dtype=float), []
    param_count = max(1, len(parameters))
    arr = np.asarray(array, dtype=float)
    if arr.ndim == 1:
        if param_count > 1 and arr.size % param_count == 0:
            matrix = arr.reshape((-1, param_count))
        else:
            matrix = arr.reshape((-1, 1))
    elif arr.ndim == 2:
        if arr.shape[1] == param_count:
            matrix = arr
        elif arr.shape[0] == param_count:
            matrix = arr.T
        else:
            matrix = arr.reshape((arr.shape[0], -1))
    else:
        if arr.shape[-1] == param_count:
            matrix = arr.reshape((-1, param_count))
        elif arr.shape[0] == param_count:
            matrix = np.moveaxis(arr, 0, -1).reshape((-1, param_count))
        else:
            matrix = arr.reshape((-1, arr.shape[-1]))

    ncols = matrix.shape[1]
    if len(parameters) >= ncols:
        used_params = parameters[:ncols]
    else:
        used_params = list(parameters)
        for index in range(len(used_params), ncols):
            used_params.append({
                "param_name": f"param_{index}",
                "param_index": index,
                "units": None,
                "is_fixed": 0,
            })
    finite_rows = np.all(np.isfinite(matrix), axis=1)
    return matrix[finite_rows], used_params


def _rvbam_parameter_order(parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(parameters, key=lambda row: (
        int(row.get("param_index") or 0),
        str(row.get("param_name") or ""),
    ))


def _rvbam_requested_param_names(args: dict[str, Any], parameters: list[dict[str, Any]]) -> list[str]:
    available = [str(row.get("param_name") or "") for row in parameters if row.get("param_name")]
    max_params = _rvbam_limit_arg(args, "max_params", 8, 12)
    requested: list[str] = []
    raw = str(args.get("params") or "").strip()
    if raw:
        if raw.lower() in {"all", "*"}:
            requested = available
        else:
            requested = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        for key in ("x", "x_param", "param_x"):
            if args.get(key):
                requested.append(str(args[key]))
                break
        for key in ("y", "y_param", "param_y"):
            if args.get(key):
                requested.append(str(args[key]))
                break
    if _as_bool(args.get("corner") or args.get("corner_plot")) and not requested:
        requested = available
    requested = [name for name in requested if name in available]
    if requested:
        return requested[:max_params]
    preferred = [name for name in ("rv_kms", "lsf_sigma_kms", "vsini_kms") if name in available]
    for name in available:
        if name not in preferred:
            preferred.append(name)
    return preferred[: min(3, len(preferred))]


def _rvbam_sample_rows(matrix: np.ndarray, parameters: list[dict[str, Any]], names: list[str], max_points: int) -> list[dict[str, Any]]:
    if matrix.size == 0 or not names:
        return []
    name_to_index = {str(param.get("param_name")): index for index, param in enumerate(parameters)}
    columns = [(name, name_to_index[name]) for name in names if name in name_to_index and name_to_index[name] < matrix.shape[1]]
    if not columns:
        return []
    nrows = matrix.shape[0]
    if nrows <= max_points:
        indices = np.arange(nrows, dtype=int)
    else:
        indices = np.unique(np.linspace(0, nrows - 1, max_points).astype(int))
    out: list[dict[str, Any]] = []
    for sample_index in indices:
        row: dict[str, Any] = {"sample_index": int(sample_index)}
        for name, col_index in columns:
            value = float(matrix[sample_index, col_index])
            row[name] = value if math.isfinite(value) else None
        out.append(row)
    return out


def _rvbam_histogram(values: np.ndarray, bins: int = 40) -> dict[str, Any]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"edges": [], "counts": []}
    counts, edges = np.histogram(finite, bins=max(5, min(int(bins), 120)))
    return {
        "edges": [float(value) for value in edges],
        "counts": [int(value) for value in counts],
    }


def _rvbam_posterior_summaries(matrix: np.ndarray, parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for index, param in enumerate(parameters[: matrix.shape[1]]):
        values = matrix[:, index]
        finite = values[np.isfinite(values)]
        row = dict(param)
        if finite.size:
            p16, median, p84 = np.percentile(finite, [16, 50, 84])
            row.update({
                "sample_mean": float(np.mean(finite)),
                "sample_std": float(np.std(finite)),
                "sample_p16": float(p16),
                "sample_median": float(median),
                "sample_p84": float(p84),
                "sample_count": int(finite.size),
            })
        summaries.append({key: _pythonize(value) for key, value in row.items()})
    return summaries


def _rvbam_correlation_payload(matrix: np.ndarray, parameters: list[dict[str, Any]], max_params: int = 12) -> dict[str, Any]:
    if matrix.shape[0] < 2 or matrix.shape[1] < 2:
        return {"labels": [], "matrix": []}
    ncols = min(matrix.shape[1], max_params, len(parameters))
    labels = [str(param.get("param_name") or f"param_{index}") for index, param in enumerate(parameters[:ncols])]
    corr = np.corrcoef(matrix[:, :ncols], rowvar=False)
    corr = np.where(np.isfinite(corr), corr, np.nan)
    return {
        "labels": labels,
        "matrix": [[_pythonize(value) for value in row] for row in corr.tolist()],
    }


def _mock_rvbam_segment_payload(args: dict[str, Any], segment_id: int) -> dict[str, Any]:
    run_id = int(segment_id) // 100
    run_payload = _mock_rvbam_run_payload(args, run_id if run_id in {910001, 910002} else 910001)
    segment = next(
        (row for row in run_payload["segments"] if int(row["moca_rv_sampling_segment_id"]) == int(segment_id)),
        run_payload["segments"][0],
    )
    sample_run_id = int(segment["moca_sample_run_id"])
    params = _mock_rvbam_parameters(sample_run_id)
    payloads = [
        {
            "moca_payload_id": sample_run_id * 10 + 1,
            "moca_sample_run_id": sample_run_id,
            "payload_kind": "chains",
            "payload_subkind": "posterior",
            "dtype": "f8",
            "compression": "gzip",
            "order_comment": "chains: [samples, params] (param_index asc)",
            "n_dim": 2,
            "dim1": 12000,
            "dim2": len(params),
            "n_stored_samples": 12000,
            "series_count": 1,
        },
        {
            "moca_payload_id": sample_run_id * 10 + 2,
            "moca_sample_run_id": sample_run_id,
            "payload_kind": "lnp",
            "payload_subkind": "logl",
            "dtype": "f8",
            "compression": "gzip",
            "order_comment": "log likelihood, one value per stored sample",
            "n_dim": 1,
            "dim1": 12000,
            "n_stored_samples": 12000,
            "series_count": 1,
        },
    ]
    return {
        "segment": segment,
        "run": run_payload["run"],
        "samplingRun": {key: segment.get(key) for key in (
            "moca_sample_run_id", "sampler_type", "sampler_name", "sampler_variant",
            "n_parameters", "n_walkers", "n_iterations", "mean_acceptance_rate",
            "best_chi2", "lnp_median", "lnp_max", "mean_finite_fraction",
            "mean_outofbounds_fraction",
        ) if segment.get(key) is not None},
        "parameters": params,
        "payloads": payloads,
        "images": {"model_fit_url": "", "corner_url": ""},
        "localModelFit": _rvbam_local_model_status(
            run_payload["run"].get("moca_mgridid"),
            run_payload["run"].get("template_name"),
        ),
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "parameter_count": len(params),
            "payload_count": len(payloads),
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _mock_rvbam_posterior_payload(args: dict[str, Any], segment_id: int) -> dict[str, Any]:
    segment_payload = _mock_rvbam_segment_payload(args, segment_id)
    segment = segment_payload["segment"]
    params = _rvbam_parameter_order(segment_payload["parameters"])
    sample_count = 12000
    max_points = _rvbam_limit_arg(args, "max_points", RVBAM_DEFAULT_MAX_SAMPLES, RVBAM_HARD_MAX_SAMPLES)
    rng = np.random.default_rng(int(segment["moca_sample_run_id"]) % (2**32 - 1))
    means = np.array([
        float(segment.get("rv_kms") or 0.0),
        float(segment.get("lsf") or 15.0),
        float(segment.get("vsini_kms") or 22.0),
        -0.03,
        0.04,
    ])
    scales = np.array([
        max(float(segment.get("rv_kms_unc") or 0.8), 0.15),
        max(float(segment.get("lsf_unc") or 2.0), 0.2),
        max(float(segment.get("vsini_kms_unc") or 4.0), 0.2),
        0.035,
        0.04,
    ])
    cov = np.diag(scales**2)
    cov[0, 1] = cov[1, 0] = 0.25 * scales[0] * scales[1]
    cov[1, 2] = cov[2, 1] = -0.18 * scales[1] * scales[2]
    matrix = rng.multivariate_normal(means, cov, size=sample_count)
    names = _rvbam_requested_param_names(args, params)
    histograms = {}
    name_to_index = {str(param.get("param_name")): index for index, param in enumerate(params)}
    for name in names:
        if name in name_to_index:
            histograms[name] = _rvbam_histogram(matrix[:, name_to_index[name]])
    samples = _rvbam_sample_rows(matrix, params, names, max_points)
    return {
        "segment": segment,
        "selectedParams": names,
        "parameterOptions": [
            {
                "name": param.get("param_name"),
                "label": param.get("param_name"),
                "units": param.get("units"),
                "index": param.get("param_index"),
            }
            for param in params
        ],
        "summaries": _rvbam_posterior_summaries(matrix, params),
        "histograms": histograms,
        "correlation": _rvbam_correlation_payload(matrix, params),
        "samples": samples,
        "payload": {
            "payload_kind": "chains",
            "payload_subkind": "posterior",
            "dtype": "f8",
            "compression": "gzip",
            "shape": [sample_count, len(params)],
        },
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "sample_count": int(matrix.shape[0]),
            "returned_sample_count": len(samples),
            "max_points": max_points,
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _load_rvbam_posterior_from_db(args: dict[str, Any], segment_id: int) -> dict[str, Any]:
    max_points = _rvbam_limit_arg(args, "max_points", RVBAM_DEFAULT_MAX_SAMPLES, RVBAM_HARD_MAX_SAMPLES)
    bins = _rvbam_limit_arg(args, "bins", 42, 120)
    cache_key = _rvbam_cache_key(
        args,
        "posterior",
        segment_id,
        args.get("params") or "",
        args.get("x") or args.get("x_param") or args.get("param_x") or "",
        args.get("y") or args.get("y_param") or args.get("param_y") or "",
        max_points,
        bins,
    )
    now = time.time()
    cached = _RVBAM_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        ok, missing = _rvbam_required_tables_available(conn)
        if not ok:
            return {
                "segment": {},
                "selectedParams": [],
                "parameterOptions": [],
                "summaries": [],
                "histograms": {},
                "correlation": {"labels": [], "matrix": []},
                "samples": [],
                "payload": {},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "sample_count": 0,
                    "returned_sample_count": 0,
                    "private_db": _is_private_db(args),
                    "missing_tables": missing,
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
        segment_rows = _records(_read_sql(conn, """
            SELECT
                moca_rv_sampling_segment_id,
                moca_rv_sample_run_id,
                moca_sample_run_id,
                order_number,
                window_number,
                segment_number,
                wv_min,
                wv_max,
                wv_center,
                rv_kms,
                rv_kms_unc,
                lsf,
                lsf_unc,
                vsini_kms,
                vsini_kms_unc,
                ignored
            FROM pcat_rv_sampling_segments
            WHERE moca_rv_sampling_segment_id = :segment_id
        """, {"segment_id": int(segment_id)}))
        if not segment_rows or segment_rows[0].get("moca_sample_run_id") is None:
            return {
                "segment": segment_rows[0] if segment_rows else {},
                "selectedParams": [],
                "parameterOptions": [],
                "summaries": [],
                "histograms": {},
                "correlation": {"labels": [], "matrix": []},
                "samples": [],
                "payload": {},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "sample_count": 0,
                    "returned_sample_count": 0,
                    "private_db": _is_private_db(args),
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
        segment = segment_rows[0]
        sample_run_id = int(segment["moca_sample_run_id"])
        parameters = _rvbam_parameter_order(_records(_read_sql(conn, """
            SELECT
                moca_sampling_parameter_id,
                moca_sample_run_id,
                param_name,
                param_index,
                units,
                mean_value,
                median_value,
                std_value,
                p16_value,
                p84_value,
                is_fixed,
                fixed_value,
                lower_bound,
                upper_bound,
                prior_type,
                prior_details,
                init_guess,
                proposal_scale,
                ignored
            FROM pcat_sampling_parameters
            WHERE moca_sample_run_id = :sample_run_id
                AND COALESCE(ignored, 0) = 0
            ORDER BY param_index, param_name
        """, {"sample_run_id": sample_run_id})))
        chain_payload = _rvbam_fetch_chain_payload(conn, sample_run_id)
        if chain_payload is None:
            return {
                "segment": segment,
                "selectedParams": [],
                "parameterOptions": [
                    {
                        "name": param.get("param_name"),
                        "label": param.get("param_name"),
                        "units": param.get("units"),
                        "index": param.get("param_index"),
                    }
                    for param in parameters
                ],
                "summaries": parameters,
                "histograms": {},
                "correlation": {"labels": [], "matrix": []},
                "samples": [],
                "payload": {},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "sample_count": 0,
                    "returned_sample_count": 0,
                    "max_points": max_points,
                    "private_db": _is_private_db(args),
                    "message": "No posterior chains payload found for this segment.",
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }

    chain_array = _decode_rvbam_payload_array(chain_payload)
    matrix, used_parameters = _rvbam_chain_matrix(chain_array, parameters)
    selected_names = _rvbam_requested_param_names(args, used_parameters)
    name_to_index = {str(param.get("param_name")): index for index, param in enumerate(used_parameters)}
    histograms = {}
    for name in selected_names:
        index = name_to_index.get(name)
        if index is not None and index < matrix.shape[1]:
            histograms[name] = _rvbam_histogram(matrix[:, index], bins=bins)
    samples = _rvbam_sample_rows(matrix, used_parameters, selected_names, max_points)
    payload_meta = {key: _pythonize(value) for key, value in chain_payload.items() if key != "payload"}
    payload_meta["shape"] = list(chain_array.shape)
    payload = {
        "segment": segment,
        "selectedParams": selected_names,
        "parameterOptions": [
            {
                "name": param.get("param_name"),
                "label": param.get("param_name"),
                "units": param.get("units"),
                "index": param.get("param_index"),
            }
            for param in used_parameters
        ],
        "summaries": _rvbam_posterior_summaries(matrix, used_parameters),
        "histograms": histograms,
        "correlation": _rvbam_correlation_payload(matrix, used_parameters),
        "samples": samples,
        "payload": payload_meta,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "sample_count": int(matrix.shape[0]),
            "returned_sample_count": len(samples),
            "max_points": max_points,
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _RVBAM_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _load_rvbam_rebuilt_corner_from_db(args: dict[str, Any], segment_id: int) -> dict[str, Any]:
    keep_weight = _safe_float(args.get("corner_keep_weight") or args.get("keep_weight"))
    if keep_weight is None:
        keep_weight = 0.99
    keep_weight = min(max(float(keep_weight), 0.0), 1.0)
    q_low = _safe_float(args.get("q_low"))
    q_high = _safe_float(args.get("q_high"))
    q_low = 0.005 if q_low is None else min(max(float(q_low), 0.0), 0.49)
    q_high = 0.995 if q_high is None else min(max(float(q_high), 0.51), 1.0)
    cache_key = _rvbam_cache_key(
        args,
        "rebuilt-corner-image",
        segment_id,
        args.get("params") or "",
        args.get("max_params") or "",
        keep_weight,
        q_low,
        q_high,
    )
    now = time.time()
    cached = _RVBAM_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        ok, missing = _rvbam_required_tables_available(conn)
        if not ok:
            return {
                "available": False,
                "selectedParams": [],
                "image": {},
                "payload": {},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "sample_count": 0,
                    "returned_sample_count": 0,
                    "private_db": _is_private_db(args),
                    "missing_tables": missing,
                    "message": "RVBAM payload tables are not available.",
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
        segment_rows = _records(_read_sql(conn, """
            SELECT
                moca_rv_sampling_segment_id,
                moca_rv_sample_run_id,
                moca_sample_run_id,
                order_number,
                window_number,
                segment_number,
                rv_kms,
                rv_kms_unc,
                lsf,
                lsf_unc,
                vsini_kms,
                vsini_kms_unc,
                ignored
            FROM pcat_rv_sampling_segments
            WHERE moca_rv_sampling_segment_id = :segment_id
        """, {"segment_id": int(segment_id)}))
        if not segment_rows or segment_rows[0].get("moca_sample_run_id") is None:
            return {
                "available": False,
                "segment": segment_rows[0] if segment_rows else {},
                "selectedParams": [],
                "image": {},
                "payload": {},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "sample_count": 0,
                    "returned_sample_count": 0,
                    "private_db": _is_private_db(args),
                    "message": "No sampling run is attached to this segment.",
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
        segment = segment_rows[0]
        sample_run_id = int(segment["moca_sample_run_id"])
        parameters = _rvbam_parameter_order(_records(_read_sql(conn, """
            SELECT
                moca_sampling_parameter_id,
                moca_sample_run_id,
                param_name,
                param_index,
                units,
                mean_value,
                median_value,
                std_value,
                p16_value,
                p84_value,
                is_fixed,
                fixed_value,
                lower_bound,
                upper_bound,
                prior_type,
                prior_details,
                init_guess,
                proposal_scale,
                ignored
            FROM pcat_sampling_parameters
            WHERE moca_sample_run_id = :sample_run_id
                AND COALESCE(ignored, 0) = 0
            ORDER BY param_index, param_name
        """, {"sample_run_id": sample_run_id})))
        chain_payload = _rvbam_fetch_chain_payload(conn, sample_run_id)
        sampling_rows = _records(_read_sql(conn, """
            SELECT n_walkers
            FROM pcat_sampling_runs
            WHERE moca_sample_run_id = :sample_run_id
        """, {"sample_run_id": sample_run_id}))
        if chain_payload is None:
            return {
                "available": False,
                "segment": segment,
                "selectedParams": [],
                "image": {},
                "payload": {},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "sample_count": 0,
                    "returned_sample_count": 0,
                    "private_db": _is_private_db(args),
                    "message": "No posterior chains payload found for this segment.",
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
        live_points = sampling_rows[0].get("n_walkers") if sampling_rows else None
        weights, weights_meta = _rvbam_corner_weights(
            conn,
            sample_run_id,
            int(chain_payload.get("n_stored_samples") or 0),
            live_points=live_points,
        )

    chain_array = _decode_rvbam_payload_array(chain_payload)
    matrix, used_parameters = _rvbam_chain_matrix(chain_array, parameters)
    if weights.size != matrix.shape[0]:
        weights, weights_meta = np.ones(matrix.shape[0], dtype=float), {
            "weights_source": "uniform fallback",
            "weights_note": f"Stored weight vector length did not match chain matrix rows ({weights.size} != {matrix.shape[0]}).",
        }

    selected_names = _rvbam_requested_param_names(args, used_parameters)
    name_to_index = {str(param.get("param_name")): index for index, param in enumerate(used_parameters)}
    columns = [(name, name_to_index[name]) for name in selected_names if name in name_to_index and name_to_index[name] < matrix.shape[1]]
    if not columns:
        return {
            "available": False,
            "segment": segment,
            "selectedParams": [],
            "image": {},
            "payload": {},
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "sample_count": int(matrix.shape[0]),
                "returned_sample_count": 0,
                "private_db": _is_private_db(args),
                "message": "No finite posterior columns are available for the requested parameters.",
            },
            "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
        }

    selected_names = [name for name, _index in columns]
    selected_matrix = np.asarray(matrix[:, [index for _name, index in columns]], dtype=float)
    finite_rows = np.all(np.isfinite(selected_matrix), axis=1) & np.isfinite(weights) & (weights > 0)
    selected_matrix = selected_matrix[finite_rows]
    selected_weights = weights[finite_rows]
    pre_keep_count = int(selected_matrix.shape[0])
    selected_matrix, selected_weights = _rvbam_apply_corner_keep_weight(selected_matrix, selected_weights, keep_weight)
    if selected_matrix.shape[0] <= selected_matrix.shape[1]:
        return {
            "available": False,
            "segment": segment,
            "selectedParams": selected_names,
            "image": {},
            "payload": {},
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "sample_count": int(matrix.shape[0]),
                "finite_sample_count": pre_keep_count,
                "returned_sample_count": int(selected_matrix.shape[0]),
                "private_db": _is_private_db(args),
                "message": "Too few weighted posterior samples to rebuild a corner plot.",
            },
            "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
        }

    _prepare_rvbam_imports()
    mpl_config_dir = Path(os.environ.get("MPLCONFIGDIR", "/tmp/matplotlib"))
    mpl_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(mpl_config_dir)
    os.environ["MPLBACKEND"] = "Agg"
    from rvbam.plots.diagnostics import save_corner_plot

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        save_corner_plot(
            Path(tmp.name),
            selected_matrix,
            selected_weights,
            selected_names,
            q_low=q_low,
            q_high=q_high,
        )
        tmp.seek(0)
        png_bytes = tmp.read()
    if not png_bytes:
        raise ValueError("RVBAM corner plot generation returned an empty image.")
    encoded = base64.b64encode(png_bytes).decode("ascii")
    payload_meta = {key: _pythonize(value) for key, value in chain_payload.items() if key != "payload"}
    payload_meta["shape"] = list(chain_array.shape)
    payload = {
        "available": True,
        "segment": segment,
        "selectedParams": selected_names,
        "image": {
            "mime_type": "image/png",
            "data_url": f"data:image/png;base64,{encoded}",
            "byte_count": len(png_bytes),
        },
        "payload": payload_meta,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "sample_count": int(matrix.shape[0]),
            "finite_sample_count": pre_keep_count,
            "returned_sample_count": int(selected_matrix.shape[0]),
            "keep_weight": keep_weight,
            "q_low": q_low,
            "q_high": q_high,
            "weights_source": weights_meta.get("weights_source"),
            "weights": weights_meta,
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _RVBAM_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _rvbam_wavelength_micron(value: Any) -> float | None:
    number = _safe_float(value)
    if number is None:
        return None
    return float(number / 10000.0 if abs(number) > 1000 else number)


def _rvbam_segment_wavelength_bounds_micron(segment: dict[str, Any]) -> tuple[float, float] | None:
    left = _rvbam_wavelength_micron(segment.get("wv_min"))
    right = _rvbam_wavelength_micron(segment.get("wv_max"))
    if left is None or right is None:
        center = _rvbam_wavelength_micron(segment.get("wv_center"))
        if center is None:
            return None
        return center, center
    if right < left:
        left, right = right, left
    return float(left), float(right)


def _rvbam_global_corner_names(
    args: dict[str, Any],
    segment_payloads: list[dict[str, Any]],
) -> list[str]:
    max_params = _rvbam_limit_arg(args, "max_params", 8, 11)
    if not segment_payloads:
        return []
    available_sets = [
        {str(param.get("param_name") or "") for param in item["used_parameters"] if param.get("param_name")}
        for item in segment_payloads
    ]
    common = set.intersection(*available_sets) if available_sets else set()
    raw = str(args.get("params") or "").strip()
    if raw and raw.lower() not in {"all", "*"}:
        requested = [item.strip() for item in raw.split(",") if item.strip()]
        return [name for name in requested if name in common][:max_params]

    first_params = segment_payloads[0]["used_parameters"]
    ordered_common = [
        str(param.get("param_name"))
        for param in first_params
        if param.get("param_name")
        and str(param.get("param_name")) in common
        and (raw.lower() in {"all", "*"} or not _as_bool(param.get("is_fixed")))
    ]
    preferred = [name for name in ("rv_kms", "lsf_sigma_kms", "vsini_kms") if name in ordered_common]
    for name in ordered_common:
        if name not in preferred:
            preferred.append(name)
    return preferred[:max_params]


def _load_rvbam_global_corner_from_db(args: dict[str, Any], run_id: int) -> dict[str, Any]:
    keep_weight = _safe_float(args.get("corner_keep_weight") or args.get("keep_weight"))
    if keep_weight is None:
        keep_weight = 0.99
    keep_weight = min(max(float(keep_weight), 0.0), 1.0)
    q_low = _safe_float(args.get("q_low"))
    q_high = _safe_float(args.get("q_high"))
    q_low = 0.005 if q_low is None else min(max(float(q_low), 0.0), 0.49)
    q_high = 0.995 if q_high is None else min(max(float(q_high), 0.51), 1.0)
    max_total_samples = _rvbam_limit_arg(args, "max_total_samples", 12000, 60000)
    max_segment_samples = _rvbam_limit_arg(args, "max_segment_samples", 1200, 8000)
    seed = _rvbam_int_arg(args, "seed")
    if seed is None:
        seed = int(hashlib.sha1(f"rvbam-global-corner:{run_id}".encode("utf-8")).hexdigest()[:8], 16)
    cache_key = _rvbam_cache_key(
        args,
        "global-corner",
        run_id,
        args.get("params") or "",
        args.get("max_params") or "",
        args.get("include_ignored") or args.get("show_ignored") or "",
        keep_weight,
        q_low,
        q_high,
        max_total_samples,
        max_segment_samples,
        seed,
    )
    now = time.time()
    cached = _RVBAM_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    rng = np.random.default_rng(int(seed) % (2**32 - 1))
    skipped_segments: list[dict[str, Any]] = []
    segment_payloads: list[dict[str, Any]] = []
    candidate_segment_count = 0
    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        ok, missing = _rvbam_required_tables_available(conn)
        if not ok:
            return {
                "available": False,
                "run": {"moca_rv_sample_run_id": int(run_id)},
                "selectedParams": [],
                "image": {},
                "segments": [],
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "sample_count": 0,
                    "returned_sample_count": 0,
                    "missing_tables": missing,
                    "private_db": _is_private_db(args),
                    "message": "RVBAM payload tables are not available.",
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }

        run_rows = _records(_read_sql(conn, """
            SELECT
                r.moca_rv_sample_run_id,
                r.moca_oid,
                mo.designation,
                r.moca_instid,
                r.moca_specid,
                ms.spectrum_name,
                r.moca_mgridid,
                r.pipeline_version,
                r.target_name,
                r.template_name,
                r.ignored
            FROM pcat_rv_sampling_runs r
            LEFT JOIN moca_objects mo
                ON mo.moca_oid = r.moca_oid
            LEFT JOIN moca_spectra ms
                ON ms.moca_specid = r.moca_specid
            WHERE r.moca_rv_sample_run_id = :run_id
        """, {"run_id": int(run_id)}))
        run = run_rows[0] if run_rows else {"moca_rv_sample_run_id": int(run_id)}
        ignored_clause = "" if _as_bool(args.get("include_ignored") or args.get("show_ignored")) else "AND COALESCE(s.ignored, 0) = 0"
        segments = _records(_read_sql(conn, f"""
            SELECT
                s.moca_rv_sampling_segment_id,
                s.moca_rv_sample_run_id,
                s.moca_sample_run_id,
                s.order_number,
                s.window_number,
                s.segment_number,
                s.wv_min,
                s.wv_max,
                s.wv_center,
                s.ignored,
                sr.n_walkers
            FROM pcat_rv_sampling_segments s
            LEFT JOIN pcat_sampling_runs sr
                ON sr.moca_sample_run_id = s.moca_sample_run_id
            WHERE s.moca_rv_sample_run_id = :run_id
                AND s.moca_sample_run_id IS NOT NULL
                {ignored_clause}
            ORDER BY s.order_number, s.window_number, s.segment_number, s.wv_min, s.moca_rv_sampling_segment_id
        """, {"run_id": int(run_id)}))
        candidate_segment_count = len(segments)

        for segment in segments:
            segment_id = segment.get("moca_rv_sampling_segment_id")
            sample_run_id = segment.get("moca_sample_run_id")
            bounds = _rvbam_segment_wavelength_bounds_micron(segment)
            if bounds is None:
                skipped_segments.append({"segment_id": segment_id, "reason": "missing wavelength bounds"})
                continue
            parameters = _rvbam_parameter_order(_records(_read_sql(conn, """
                SELECT
                    moca_sampling_parameter_id,
                    moca_sample_run_id,
                    param_name,
                    param_index,
                    units,
                    mean_value,
                    median_value,
                    std_value,
                    p16_value,
                    p84_value,
                    is_fixed,
                    fixed_value,
                    lower_bound,
                    upper_bound,
                    prior_type,
                    prior_details,
                    init_guess,
                    proposal_scale,
                    ignored
                FROM pcat_sampling_parameters
                WHERE moca_sample_run_id = :sample_run_id
                    AND COALESCE(ignored, 0) = 0
                ORDER BY param_index, param_name
            """, {"sample_run_id": int(sample_run_id)})))
            chain_payload = _rvbam_fetch_chain_payload(conn, int(sample_run_id))
            if chain_payload is None:
                skipped_segments.append({"segment_id": segment_id, "reason": "missing chains payload"})
                continue
            try:
                chain_array = _decode_rvbam_payload_array(chain_payload)
                matrix, used_parameters = _rvbam_chain_matrix(chain_array, parameters)
                if matrix.size == 0:
                    skipped_segments.append({"segment_id": segment_id, "reason": "empty chains payload"})
                    continue
                weights, weights_meta = _rvbam_corner_weights(
                    conn,
                    int(sample_run_id),
                    int(chain_payload.get("n_stored_samples") or 0),
                    live_points=segment.get("n_walkers"),
                )
                if weights.size != matrix.shape[0]:
                    weights, weights_meta = np.ones(matrix.shape[0], dtype=float), {
                        "weights_source": "uniform fallback",
                        "weights_note": f"Stored weight vector length did not match chain matrix rows ({weights.size} != {matrix.shape[0]}).",
                    }
            except Exception as exc:
                skipped_segments.append({"segment_id": segment_id, "reason": f"{type(exc).__name__}: {exc}"})
                continue
            segment_payloads.append({
                "segment": segment,
                "bounds": bounds,
                "matrix": matrix,
                "weights": weights,
                "used_parameters": used_parameters,
                "chain_payload": chain_payload,
                "weights_meta": weights_meta,
            })

    selected_names = _rvbam_global_corner_names(args, segment_payloads)
    if not selected_names:
        return {
            "available": False,
            "run": run,
            "selectedParams": [],
            "image": {},
            "segments": [],
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "segment_count": candidate_segment_count,
                "used_segment_count": len(segment_payloads),
                "skipped_segments": skipped_segments[:20],
                "private_db": _is_private_db(args),
                "message": "No common posterior parameters were found across segment chains.",
            },
            "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
        }

    per_segment_limit = max(1, min(max_segment_samples, math.ceil(max_total_samples / max(len(segment_payloads), 1))))
    combined_arrays: list[np.ndarray] = []
    combined_weights: list[np.ndarray] = []
    segment_summaries: list[dict[str, Any]] = []
    for item in segment_payloads:
        name_to_index = {str(param.get("param_name")): index for index, param in enumerate(item["used_parameters"])}
        columns = [name_to_index[name] for name in selected_names if name in name_to_index and name_to_index[name] < item["matrix"].shape[1]]
        if len(columns) != len(selected_names):
            skipped_segments.append({
                "segment_id": item["segment"].get("moca_rv_sampling_segment_id"),
                "reason": "missing selected parameter columns",
            })
            continue
        selected_matrix = np.asarray(item["matrix"][:, columns], dtype=float)
        weights = np.asarray(item["weights"], dtype=float)
        finite_rows = np.all(np.isfinite(selected_matrix), axis=1) & np.isfinite(weights) & (weights > 0)
        selected_matrix = selected_matrix[finite_rows]
        weights = weights[finite_rows]
        finite_count = int(selected_matrix.shape[0])
        selected_matrix, weights = _rvbam_apply_corner_keep_weight(selected_matrix, weights, keep_weight)
        if selected_matrix.shape[0] <= selected_matrix.shape[1]:
            skipped_segments.append({
                "segment_id": item["segment"].get("moca_rv_sampling_segment_id"),
                "reason": "too few weighted posterior samples",
            })
            continue
        if selected_matrix.shape[0] > per_segment_limit:
            p = weights / np.sum(weights) if np.sum(weights) > 0 else None
            keep = rng.choice(selected_matrix.shape[0], size=per_segment_limit, replace=False, p=p)
            selected_matrix = selected_matrix[keep]
            weights = weights[keep]
        w0, w1 = item["bounds"]
        if w1 > w0:
            wavelength = rng.uniform(w0, w1, size=selected_matrix.shape[0])
        else:
            wavelength = np.full(selected_matrix.shape[0], w0, dtype=float)
        combined_arrays.append(np.column_stack([selected_matrix, wavelength]))
        weight_sum = float(np.sum(weights))
        combined_weights.append(weights / weight_sum if weight_sum > 0 else np.full(weights.shape[0], 1.0 / weights.shape[0]))
        segment_summaries.append({
            "moca_rv_sampling_segment_id": item["segment"].get("moca_rv_sampling_segment_id"),
            "moca_sample_run_id": item["segment"].get("moca_sample_run_id"),
            "segment_number": item["segment"].get("segment_number"),
            "wavelength_min_um": _pythonize(w0),
            "wavelength_max_um": _pythonize(w1),
            "finite_sample_count": finite_count,
            "returned_sample_count": int(selected_matrix.shape[0]),
            "weights_source": item["weights_meta"].get("weights_source"),
        })

    if not combined_arrays:
        return {
            "available": False,
            "run": run,
            "selectedParams": [*selected_names, "wavelength_um"],
            "image": {},
            "segments": segment_summaries,
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "segment_count": candidate_segment_count,
                "used_segment_count": 0,
                "skipped_segments": skipped_segments[:20],
                "private_db": _is_private_db(args),
                "message": "No segment had enough finite weighted posterior samples for a global corner plot.",
            },
            "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
        }

    combined_matrix = np.vstack(combined_arrays)
    combined_weight = np.concatenate(combined_weights)
    if combined_matrix.shape[0] <= combined_matrix.shape[1]:
        return {
            "available": False,
            "run": run,
            "selectedParams": [*selected_names, "wavelength_um"],
            "image": {},
            "segments": segment_summaries,
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "sample_count": int(combined_matrix.shape[0]),
                "returned_sample_count": int(combined_matrix.shape[0]),
                "private_db": _is_private_db(args),
                "message": "Too few combined posterior samples to build a global corner plot.",
            },
            "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
        }

    _prepare_rvbam_imports()
    mpl_config_dir = Path(os.environ.get("MPLCONFIGDIR", "/tmp/matplotlib"))
    mpl_config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(mpl_config_dir)
    os.environ["MPLBACKEND"] = "Agg"
    from rvbam.plots.diagnostics import save_corner_plot

    labels = [*selected_names, "wavelength_um"]
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        save_corner_plot(
            Path(tmp.name),
            combined_matrix,
            combined_weight,
            labels,
            q_low=q_low,
            q_high=q_high,
        )
        tmp.seek(0)
        png_bytes = tmp.read()
    if not png_bytes:
        raise ValueError("RVBAM global corner plot generation returned an empty image.")
    encoded = base64.b64encode(png_bytes).decode("ascii")
    payload = {
        "available": True,
        "run": run,
        "selectedParams": labels,
        "image": {
            "mime_type": "image/png",
            "data_url": f"data:image/png;base64,{encoded}",
            "byte_count": len(png_bytes),
        },
        "segments": segment_summaries,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "segment_count": candidate_segment_count,
            "used_segment_count": len(segment_summaries),
            "skipped_segments": skipped_segments[:20],
            "sample_count": int(sum(item.get("finite_sample_count", 0) for item in segment_summaries)),
            "returned_sample_count": int(combined_matrix.shape[0]),
            "per_segment_sample_limit": int(per_segment_limit),
            "max_total_samples": int(max_total_samples),
            "keep_weight": keep_weight,
            "q_low": q_low,
            "q_high": q_high,
            "seed": int(seed),
            "weights_source": "segment-normalized posterior weights",
            "wavelength_source": "uniform random draw within each segment wavelength range",
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _RVBAM_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _rvbam_segment_bounds_angstrom(wv_min: Any, wv_max: Any) -> tuple[float, float]:
    left = _safe_float(wv_min)
    right = _safe_float(wv_max)
    if left is None or right is None:
        raise ValueError("Selected RVBAM segment has no wavelength bounds.")
    if right < left:
        left, right = right, left
    # Some older payloads store microns, while current RVBAM rows use Angstrom.
    if max(abs(left), abs(right)) < 1000:
        left *= 10000.0
        right *= 10000.0
    return float(left), float(right)


def _rvbam_theta_from_parameters(
    parameters: list[dict[str, Any]],
    segment: dict[str, Any],
    run: dict[str, Any],
) -> dict[str, float]:
    theta: dict[str, float] = {}
    for param in parameters:
        name = str(param.get("param_name") or "").strip()
        if not name:
            continue
        value = None
        if _as_bool(param.get("is_fixed")):
            value = param.get("fixed_value")
        if value is None:
            value = param.get("median_value")
        if value is None:
            value = param.get("mean_value")
        parsed = _safe_float(value)
        if parsed is not None:
            theta[name] = float(parsed)

    if "rv_kms" not in theta:
        rv_value = _safe_float(segment.get("rv_kms"))
        berv = _safe_float(run.get("berv_kms"))
        if rv_value is not None:
            theta["rv_kms"] = rv_value - berv if berv is not None else rv_value
    if "lsf_sigma_kms" not in theta and _safe_float(segment.get("lsf")) is not None:
        theta["lsf_sigma_kms"] = float(_safe_float(segment.get("lsf")) or 0.0)
    if "vsini_kms" not in theta and _safe_float(segment.get("vsini_kms")) is not None:
        theta["vsini_kms"] = float(_safe_float(segment.get("vsini_kms")) or 0.0)
    theta.setdefault("blaze_left", 1.0)
    theta.setdefault("blaze_right", 1.0)
    theta.setdefault("E_floor", 0.0)
    return theta


def _rvbam_downsample_indices(length: int, max_points: int) -> np.ndarray:
    if length <= 0:
        return np.array([], dtype=int)
    if length <= max_points:
        return np.arange(length, dtype=int)
    return np.unique(np.linspace(0, length - 1, max_points).astype(int))


def _rvbam_fit_series_records(
    wavelength: np.ndarray,
    *arrays: np.ndarray,
    max_points: int,
    names: tuple[str, ...],
) -> list[dict[str, Any]]:
    indices = _rvbam_downsample_indices(int(wavelength.size), int(max_points))
    records: list[dict[str, Any]] = []
    for index in indices:
        row = {"wavelength_angstrom": _pythonize(float(wavelength[index]))}
        for name, array in zip(names, arrays):
            value = array[index] if index < array.size else np.nan
            row[name] = _pythonize(float(value)) if np.isfinite(value) else None
        records.append(row)
    return records


def _rvbam_default_rebuilt_fit_lsf_sigma_kms(run: dict[str, Any]) -> float:
    pipeline = str(run.get("pipeline_version") or "").lower()
    instrument = str(run.get("moca_instid") or "").lower()
    if "g395h" in pipeline or "nirspec" in instrument:
        return float(299792.458 / 2700.0 / 2.355)
    return 20.0


def _rvbam_grid_midpoint_theta(
    par_list: list[str],
    axes: Any,
    grid_bounds: dict[str, tuple[float, float]] | None,
    lsf_sigma_kms: float,
) -> dict[str, float]:
    theta: dict[str, float] = {}
    for parameter in par_list:
        bounds = (grid_bounds or {}).get(parameter)
        if bounds is not None:
            lo = _safe_float(bounds[0])
            hi = _safe_float(bounds[1])
            if lo is not None and hi is not None and np.isfinite(lo) and np.isfinite(hi):
                theta[parameter] = float(0.5 * (lo + hi))
                continue
        values = np.asarray(axes.axes[parameter], dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size:
            theta[parameter] = float(0.5 * (np.nanmin(finite) + np.nanmax(finite)))
    theta.update({
        "rv_kms": 0.0,
        "lsf_sigma_kms": float(lsf_sigma_kms),
        "blaze_left": 1.0,
        "blaze_right": 1.0,
        "E_floor": 0.0,
    })
    return theta


def _rvbam_auto_model_flux_scale(
    data: Any,
    fetcher: Any,
    par_list: list[str],
    axes: Any,
    forward_config: Any,
    grid_bounds: dict[str, tuple[float, float]] | None,
    lsf_sigma_kms: float,
) -> tuple[float, str]:
    _prepare_rvbam_imports()
    from rvbam.model.segment_loglike import SegmentLogLikelihood as RvbamSegmentLogLikelihood

    test_theta = _rvbam_grid_midpoint_theta(par_list, axes, grid_bounds, lsf_sigma_kms)
    try:
        tmp = RvbamSegmentLogLikelihood(
            data,
            fetcher,
            forward_config=forward_config,
            model_flux_scale=1.0,
        )
    except Exception:
        return 1.0, "fallback"

    try:
        model_on_data = tmp.model_on_data(test_theta)
        finite = np.isfinite(data.flux) & np.isfinite(model_on_data)
        if np.any(finite):
            med_data = float(np.nanmedian(data.flux[finite]))
            med_model = float(np.nanmedian(model_on_data[finite]))
            if np.isfinite(med_data) and np.isfinite(med_model) and med_model != 0:
                return float(med_data / med_model), "rvbam-diagnostic-grid-midpoint"
    except Exception:
        pass
    return 1.0, "fallback"


def _load_rvbam_rebuilt_fit_from_db(args: dict[str, Any], segment_id: int) -> dict[str, Any]:
    max_data_points = _rvbam_limit_arg(args, "max_data_points", 3000, 12000)
    max_model_points = _rvbam_limit_arg(args, "max_model_points", 3000, 12000)
    requested_model_flux_scale = _safe_float(args.get("model_flux_scale"))
    cache_key = _rvbam_cache_key(
        args,
        "rebuilt-fit",
        segment_id,
        max_data_points,
        max_model_points,
        requested_model_flux_scale if requested_model_flux_scale is not None else f"auto-{RVBAM_REBUILT_FIT_AUTO_SCALE_VERSION}",
    )
    now = time.time()
    cached = _RVBAM_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        _rvbam_refresh_local_model_status(payload)
        if not (payload.get("available") is False and payload.get("localModelFit", {}).get("available")):
            payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
            return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        rows = _records(_read_sql(conn, """
            SELECT
                s.moca_rv_sampling_segment_id,
                s.moca_rv_sample_run_id,
                s.moca_sample_run_id,
                s.order_number,
                s.window_number,
                s.segment_number,
                s.wv_min,
                s.wv_max,
                s.wv_center,
                s.rv_kms,
                s.rv_kms_unc,
                s.lsf,
                s.lsf_unc,
                s.vsini_kms,
                s.vsini_kms_unc,
                r.moca_oid,
                mo.designation,
                r.moca_instid,
                r.moca_specid,
                ms.spectrum_name,
                ms.berv_corrected,
                r.moca_mgridid,
                r.pipeline_version,
                r.target_name,
                r.template_name,
                r.berv_kms,
                r.berv_kms_unc
            FROM pcat_rv_sampling_segments s
            JOIN pcat_rv_sampling_runs r
                ON r.moca_rv_sample_run_id = s.moca_rv_sample_run_id
            LEFT JOIN moca_objects mo
                ON mo.moca_oid = r.moca_oid
            LEFT JOIN moca_spectra ms
                ON ms.moca_specid = r.moca_specid
            WHERE s.moca_rv_sampling_segment_id = :segment_id
        """, {"segment_id": int(segment_id)}))
        if not rows:
            raise ValueError(f"RVBAM segment not found: {segment_id}")
        row = rows[0]
        status = _rvbam_local_model_status(row.get("moca_mgridid"), row.get("template_name"))
        if not status.get("available"):
            return {
                "available": False,
                "localModelFit": status,
                "segment": row,
                "run": {},
                "data": [],
                "model": [],
                "theta": {},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "message": status.get("message") or "Local RVBAM HDF5 model file is not available on this server.",
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }

        sample_run_id = row.get("moca_sample_run_id")
        parameters = _records(_read_sql(conn, """
            SELECT
                param_name,
                param_index,
                units,
                mean_value,
                median_value,
                std_value,
                p16_value,
                p84_value,
                is_fixed,
                fixed_value,
                lower_bound,
                upper_bound
            FROM pcat_sampling_parameters
            WHERE moca_sample_run_id = :sample_run_id
                AND COALESCE(ignored, 0) = 0
            ORDER BY param_index, param_name
        """, {"sample_run_id": int(sample_run_id)})) if sample_run_id is not None else []

        w0, w1 = _rvbam_segment_bounds_angstrom(row.get("wv_min"), row.get("wv_max"))
        spectrum_rows = _records(_read_sql(conn, """
            SELECT
                wavelength_angstrom,
                flux_flambda,
                flux_flambda_unc
            FROM data_spectra
            WHERE moca_specid = :specid
                AND COALESCE(ignored, 0) = 0
                AND wavelength_angstrom BETWEEN :w0 AND :w1
            ORDER BY wavelength_angstrom
        """, {
            "specid": int(row["moca_specid"]),
            "w0": float(w0),
            "w1": float(w1),
        }))

    if not spectrum_rows:
        raise ValueError("No data_spectra rows found for the selected segment wavelength range.")

    _prepare_rvbam_imports()

    from rvbam.grid.cache import SpectrumCache
    from rvbam.grid.interpolated_model import GridIndex, InterpolatedModelFetcher
    from rvbam.grid.local_models import LocalHdf5ModelStore, LocalModelConfig
    from rvbam.model.forward import ForwardModelConfig, edges_from_centers
    from rvbam.model.segment_loglike import SegmentData, SegmentLogLikelihood

    wavelength = np.array([float(item["wavelength_angstrom"]) for item in spectrum_rows], dtype=float)
    flux = np.array([float(item["flux_flambda"]) if item.get("flux_flambda") is not None else np.nan for item in spectrum_rows], dtype=float)
    flux_err = np.array([float(item["flux_flambda_unc"]) if item.get("flux_flambda_unc") is not None else np.nan for item in spectrum_rows], dtype=float)
    finite = np.isfinite(wavelength) & np.isfinite(flux) & np.isfinite(flux_err)
    wavelength = wavelength[finite]
    flux = flux[finite]
    flux_err = flux_err[finite]
    if wavelength.size < 2:
        raise ValueError("Too few finite spectrum rows to rebuild the model fit.")

    theta = _rvbam_theta_from_parameters(parameters, row, row)
    with engine.connect() as conn:
        store = LocalHdf5ModelStore(
            conn,
            str(row["moca_mgridid"]),
            config=LocalModelConfig(base_dir=_rvbam_model_base_dir_for_status(status)),
            use_db_file_index=False,
        )
        par_list, axes, tuple_to_fileid = store.load_grid_index()
        expected = int(np.prod([len(axes.axes[p]) for p in par_list])) if par_list else 0
        require_full = not (expected and len(tuple_to_fileid) < expected)
        cache = SpectrumCache(fetch_fn=store.fetch_model_spectrum)
        fetcher = InterpolatedModelFetcher(
            None,
            str(row["moca_mgridid"]),
            GridIndex(par_list=par_list, axes=axes, tuple_to_fileid=tuple_to_fileid),
            cache=cache,
            require_full_corners=require_full,
        )
        fetcher.set_segment_range(w0, w1)
        try:
            grid_bounds = store.parameter_bounds()
        except Exception:
            grid_bounds = {}
        data = SegmentData(
            wavelength=wavelength,
            flux=flux,
            flux_err=flux_err,
            berv_kms=_safe_float(row.get("berv_kms")),
            berv_corrected=row.get("berv_corrected"),
            edges=edges_from_centers(wavelength),
            segment_bounds=(float(w0), float(w1)),
            specid=int(row["moca_specid"]),
            window_number=row.get("window_number"),
            segment_number=row.get("segment_number"),
        )
        forward_config = ForwardModelConfig(
            log_grid_oversample=RVBAM_REBUILT_FIT_LOG_OVERSAMPLE,
            conv_grid=RVBAM_REBUILT_FIT_CONV_GRID,
        )
        auto_scale_lsf_sigma_kms = _rvbam_default_rebuilt_fit_lsf_sigma_kms(row)
        model_flux_scale = requested_model_flux_scale
        model_flux_scale_source = "request"
        if model_flux_scale is None:
            model_flux_scale, model_flux_scale_source = _rvbam_auto_model_flux_scale(
                data,
                fetcher,
                par_list,
                axes,
                forward_config,
                grid_bounds,
                auto_scale_lsf_sigma_kms,
            )
        loglike = SegmentLogLikelihood(
            data,
            fetcher,
            forward_config=forward_config,
            model_flux_scale=float(model_flux_scale),
        )
        model_on_data = loglike.model_on_data(theta)
        sigma_eff = loglike.sigma_eff(theta)
        model_wv_hi = np.linspace(float(w0), float(w1), min(max_model_points, 10000), dtype=float)
        model_flux_hi = loglike.model_on_grid(theta, model_wv_hi)

    data_records = _rvbam_fit_series_records(
        wavelength,
        flux,
        flux_err,
        sigma_eff,
        model_on_data,
        max_points=max_data_points,
        names=("flux", "flux_err", "sigma_eff", "model_flux"),
    )
    model_records = _rvbam_fit_series_records(
        model_wv_hi,
        model_flux_hi,
        max_points=max_model_points,
        names=("model_flux",),
    )
    theta_payload = {key: _pythonize(value) for key, value in theta.items()}
    payload = {
        "available": True,
        "localModelFit": status,
        "segment": {
            key: row.get(key)
            for key in (
                "moca_rv_sampling_segment_id", "moca_rv_sample_run_id", "moca_sample_run_id",
                "order_number", "window_number", "segment_number", "wv_min", "wv_max",
                "rv_kms", "rv_kms_unc", "lsf", "lsf_unc", "vsini_kms", "vsini_kms_unc",
            )
            if row.get(key) is not None
        },
        "run": {
            key: row.get(key)
            for key in (
                "moca_oid", "designation", "moca_instid", "moca_specid", "spectrum_name",
                "moca_mgridid", "pipeline_version", "target_name", "template_name",
                "berv_kms", "berv_kms_unc",
            )
            if row.get(key) is not None
        },
        "parameters": parameters,
        "theta": theta_payload,
        "gridParameters": par_list,
        "data": data_records,
        "model": model_records,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "data_point_count": int(wavelength.size),
            "returned_data_point_count": len(data_records),
            "model_point_count": int(model_wv_hi.size),
            "returned_model_point_count": len(model_records),
            "model_file": status.get("model_file"),
            "model_grid_mode": getattr(store, "mode", None),
            "model_flux_scale": _pythonize(float(model_flux_scale)),
            "model_flux_scale_source": model_flux_scale_source,
            "model_flux_scale_lsf_sigma_kms": _pythonize(float(auto_scale_lsf_sigma_kms)),
            "forward_model_conv_grid": RVBAM_REBUILT_FIT_CONV_GRID,
            "forward_model_log_grid_oversample": _pythonize(float(RVBAM_REBUILT_FIT_LOG_OVERSAMPLE)),
            "private_db": _is_private_db(args),
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _RVBAM_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


MORANTA26_DEFAULT_CLUSTERS = ("THA", "IC2602", "PERI", "GRX")
MORANTA26_DEFAULT_LAMBDAS = (1, 2, 4, 8, 16)
MORANTA26_PID = "Mora26"
MORANTA26_PROBABILITY_THRESHOLD = 0.70
MORANTA26_LITERATURE_TOLERANCE = 0.15
MORANTA26_MIN_PERIOD_DAYS = 0.05
MORANTA26_MAX_PERIOD_DAYS = 30.0
MORANTA26_KV_RE = re.compile(r"(?:^|;\s*)([A-Za-z0-9_]+)=([^;]*)")


def _moranta26_cache_key(args: dict[str, Any], *parts: Any) -> str:
    return "|".join([_spt_db_cache_key(args), "moranta26-rotation", *[str(part) for part in parts]])


def _moranta26_parse_kv(text_value: Any) -> dict[str, str | None]:
    if text_value is None:
        return {}
    if isinstance(text_value, float) and not math.isfinite(text_value):
        return {}
    parsed: dict[str, str | None] = {}
    for key, value in MORANTA26_KV_RE.findall(str(text_value)):
        clean_value = value.strip()
        parsed[key] = None if clean_value in {"", "None", "NULL", "null"} else clean_value
    return parsed


def _moranta26_float(value: Any) -> float | None:
    return _safe_float(value)


def _moranta26_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _moranta26_source_id(value: Any) -> str:
    if value is None:
        return ""
    text_value = str(value).replace("Gaia DR3", "").replace("GaiaDR3", "").strip()
    digits = "".join(ch for ch in text_value if ch.isdigit())
    return digits or ""


def _moranta26_boolish_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return 0 if value.strip().lower() in {"", "0", "false", "n", "no", "none", "null"} else 1
    return 1 if bool(value) else 0


def _moranta26_revised_period(value: Any) -> float | None:
    revised = _moranta26_float(value)
    return revised if revised is not None and revised > 0 else None


def _moranta26_prob_all(row: dict[str, Any]) -> float | None:
    values = [
        _moranta26_float(row.get(key))
        for key in ("prob_rot", "prob_snr", "prob_asym", "prob_rms", "prob_ls")
    ]
    finite = [value for value in values if value is not None]
    if finite:
        return float(sum(finite) / len(finite))
    return _moranta26_float(row.get("final_prob"))


def _moranta26_normalize_catalog_df(df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _records(df):
        flags = _moranta26_parse_kv(raw.get("prot_flags"))
        comments = _moranta26_parse_kv(raw.get("comments"))
        get_identity = lambda key, fallback=None: flags.get(key, comments.get(key, fallback))
        moca_oid = _moranta26_int(raw.get("moca_oid"))
        source_id = _moranta26_source_id(raw.get("source_id"))
        prot_id = _moranta26_int(raw.get("prot_id"))
        source_moca_tplcid = _moranta26_int(get_identity("source_moca_tplcid"))
        revised_days = _moranta26_revised_period(comments.get("revised_days"))
        row = {
            "prot_id": prot_id,
            "moca_oid": moca_oid,
            "star_key": f"oid:{moca_oid}" if moca_oid is not None else (f"gaia:{source_id}" if source_id else f"prot:{prot_id}"),
            "source_id": source_id,
            "cluster": get_identity("project_id", "") or "",
            "m": _moranta26_int(get_identity("m", raw.get("m"))),
            "pipeline": get_identity("pipeline", "") or "",
            "sector": _moranta26_int(get_identity("sector")),
            "source_rotation_id": _moranta26_int(get_identity("source_rotation_id")),
            "source_moca_tplcid": source_moca_tplcid,
            "prot": _moranta26_float(raw.get("prot")),
            "prot_days_unc": _moranta26_float(raw.get("prot_days_unc")),
            "erru_prot": _moranta26_float(comments.get("erru_prot_days")),
            "errd_prot": _moranta26_float(comments.get("errd_prot_days")),
            "gp_rot": _moranta26_float(comments.get("gp_rot_days")),
            "lit_prot": _moranta26_float(comments.get("lit_prot_days")),
            "lit_source": comments.get("lit_source"),
            "ls_power": _moranta26_float(raw.get("ls_power") if raw.get("ls_power") is not None else comments.get("ls_power")),
            "snr": _moranta26_float(comments.get("snr")),
            "rms": _moranta26_float(comments.get("rms")),
            "category": get_identity("category", "") or "",
            "selected": _moranta26_boolish_int(get_identity("selected")),
            "revised": revised_days,
            "has_revised": revised_days is not None,
            "period_value_source": comments.get("period_value_source"),
            "quality": raw.get("quality"),
            "multiple_periods": _moranta26_boolish_int(raw.get("multiple_periods")),
            "ignored": _moranta26_boolish_int(raw.get("ignored")),
            "is_public": _moranta26_boolish_int(raw.get("is_public")),
            "rls": raw.get("rls"),
            "publication_comments": raw.get("publication_comments"),
            "comments": raw.get("comments"),
            "prot_flags": raw.get("prot_flags"),
            "prob_rot": _moranta26_float(comments.get("prob_rot")),
            "prob_snr": _moranta26_float(comments.get("prob_snr")),
            "prob_asym": _moranta26_float(comments.get("prob_asym")),
            "prob_rms": _moranta26_float(comments.get("prob_rms")),
            "prob_ls": _moranta26_float(comments.get("prob_ls")),
            "final_prob": _moranta26_float(comments.get("final_prob")),
            "phot_g_mean_mag": _moranta26_float(raw.get("phot_g_mean_mag")),
            "bp_rp": _moranta26_float(raw.get("bp_rp")),
            "grp": _moranta26_float(raw.get("grp")),
            "report_url": f"https://mocadb.ca/search/results?search-query=oid%28{moca_oid}%29&search-type=star" if moca_oid is not None else "",
        }
        row["prob_all"] = _moranta26_prob_all(row)
        row["has_literature_period"] = row["lit_prot"] is not None and row["lit_prot"] > 0
        row["has_light_curve"] = source_moca_tplcid is not None
        rows.append({key: _pythonize(value) for key, value in row.items()})
    rows.sort(key=lambda row: (
        str(row.get("cluster") or ""),
        row.get("moca_oid") if row.get("moca_oid") is not None else 10**18,
        row.get("source_id") or "",
        row.get("m") if row.get("m") is not None else 10**9,
        row.get("pipeline") or "",
        row.get("sector") if row.get("sector") is not None else 10**9,
        row.get("prot_id") if row.get("prot_id") is not None else 10**18,
    ))
    return rows


def _load_moranta26_catalog_from_db(args: dict[str, Any]) -> dict[str, Any]:
    cache_key = _moranta26_cache_key(args, "catalog", "include-ignored-v1")
    now = time.time()
    cached = _MORANTA26_ROTATION_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    schema = _db_schema_identifier(args)
    private_db = _is_private_db(args)
    visibility_columns = "rp.is_public,\n                rp.rls," if private_db else "1 AS is_public,\n                'public' AS rls,"
    visibility_filter = "\n                AND rp.is_public = 1\n                AND rp.rls = 'public'" if private_db else ""
    with engine.connect() as conn:
        started = time.time()
        df = _read_sql(conn, f"""
            SELECT
                rp.id AS prot_id,
                rp.moca_oid,
                rp.prot_days AS prot,
                rp.prot_days_unc,
                rp.prot_flags,
                rp.quality,
                rp.multiple_periods,
                rp.prot_index AS m,
                rp.ls_power,
                rp.ignored,
                {visibility_columns}
                rp.publication_comments,
                rp.comments,
                g.source_id,
                g.phot_g_mean_mag,
                (g.phot_bp_mean_mag - g.phot_rp_mean_mag) AS bp_rp,
                (g.phot_g_mean_mag - g.phot_rp_mean_mag) AS grp
            FROM {schema}.data_rotation_periods AS rp
            LEFT JOIN {schema}.cat_gaiadr3 AS g
                ON g.moca_oid = rp.moca_oid
            WHERE rp.moca_pid = :moca_pid
                {visibility_filter}
            ORDER BY rp.moca_oid, rp.prot_index, rp.id
        """, {"moca_pid": MORANTA26_PID})
        rows = _moranta26_normalize_catalog_df(df)
        light_curve_tables_available = (
            _db_table_exists(conn, "moca_photometric_time_series")
            and _db_table_exists(conn, "data_photometric_time_series")
        )
        if not light_curve_tables_available:
            for row in rows:
                row["source_moca_tplcid"] = None
                row["has_light_curve"] = False
        query_seconds = round(time.time() - started, 3)

    clusters = sorted({str(row.get("cluster") or "") for row in rows if row.get("cluster")}) or list(MORANTA26_DEFAULT_CLUSTERS)
    lambdas = sorted({int(row["m"]) for row in rows if row.get("m") is not None})
    pipelines = sorted({str(row.get("pipeline") or "") for row in rows if row.get("pipeline")})
    sectors = sorted({int(row["sector"]) for row in rows if row.get("sector") is not None})
    categories = sorted({str(row.get("category") or "") for row in rows if row.get("category")})
    qualities = sorted({str(row.get("quality") or "") for row in rows if row.get("quality")})
    payload = {
        "rows": rows,
        "options": {
            "clusters": clusters,
            "lambdas": lambdas,
            "pipelines": pipelines,
            "sectors": sectors,
            "categories": categories,
            "qualities": qualities,
        },
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "moca_pid": MORANTA26_PID,
            "row_count": len(rows),
            "ignored_row_count": sum(1 for row in rows if row.get("ignored")),
            "null_moca_oid_count": sum(1 for row in rows if row.get("moca_oid") is None),
            "light_curve_link_count": sum(1 for row in rows if row.get("source_moca_tplcid") is not None),
            "light_curve_tables_available": light_curve_tables_available,
            "literature_period_count": sum(1 for row in rows if row.get("has_literature_period")),
            "query_seconds": query_seconds,
            "include_ignored": True,
            "ignored_filter_note": "Mora26 dataviz intentionally includes data_rotation_periods rows with ignored=1 so all source m values can be explored.",
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _MORANTA26_ROTATION_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _moranta26_periodogram_records(rows: list[dict[str, Any]], *, max_points: int = 1200) -> list[dict[str, Any]]:
    if len(rows) < 5:
        return []
    time_values = np.array([row.get("btjd") for row in rows], dtype=float)
    flux_values = np.array([row.get("flux") for row in rows], dtype=float)
    valid = np.isfinite(time_values) & np.isfinite(flux_values)
    time_values = time_values[valid]
    flux_values = flux_values[valid]
    if time_values.size < 5:
        return []
    flux_values = flux_values - np.nanmedian(flux_values)
    try:
        from astropy.timeseries import LombScargle

        frequency, power = LombScargle(time_values, flux_values).autopower(
            minimum_frequency=1.0 / MORANTA26_MAX_PERIOD_DAYS,
            maximum_frequency=1.0 / MORANTA26_MIN_PERIOD_DAYS,
            samples_per_peak=12,
        )
        periods = 1.0 / frequency
    except Exception:
        periods = np.linspace(MORANTA26_MIN_PERIOD_DAYS, MORANTA26_MAX_PERIOD_DAYS, max_points)
        y_norm = np.sum(flux_values * flux_values)
        if not np.isfinite(y_norm) or y_norm <= 0:
            return []
        powers = []
        for period in periods:
            phase = 2.0 * np.pi * time_values / period
            cos_phase = np.cos(phase)
            sin_phase = np.sin(phase)
            cos_norm = np.sum(cos_phase * cos_phase)
            sin_norm = np.sum(sin_phase * sin_phase)
            power = 0.0
            if cos_norm > 0:
                power += (np.sum(flux_values * cos_phase) ** 2) / cos_norm
            if sin_norm > 0:
                power += (np.sum(flux_values * sin_phase) ** 2) / sin_norm
            powers.append(power / y_norm)
        power = np.array(powers, dtype=float)
    valid_period = np.isfinite(periods) & np.isfinite(power)
    periods = periods[valid_period]
    power = power[valid_period]
    order = np.argsort(periods)
    periods = periods[order]
    power = power[order]
    if periods.size > max_points:
        take = np.linspace(0, periods.size - 1, max_points).round().astype(int)
        periods = periods[take]
        power = power[take]
    return [
        {"period": _pythonize(float(period)), "power": _pythonize(float(power_value))}
        for period, power_value in zip(periods, power)
    ]


def _load_moranta26_lightcurve_from_db(args: dict[str, Any], photseqid: int) -> dict[str, Any]:
    cache_key = _moranta26_cache_key(args, "lightcurve", photseqid)
    now = time.time()
    cached = _MORANTA26_ROTATION_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    schema = _db_schema_identifier(args)
    private_db = _is_private_db(args)
    visibility_filter = "\n                AND h.is_public = 1\n                AND h.rls = 'public'" if private_db else ""
    with engine.connect() as conn:
        started = time.time()
        tables_available = (
            _db_table_exists(conn, "moca_photometric_time_series")
            and _db_table_exists(conn, "data_photometric_time_series")
        )
        if not tables_available:
            query_seconds = round(time.time() - started, 3)
            payload = {
                "photseqid": photseqid,
                "header": None,
                "rows": [],
                "periodogram": [],
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "private_db": private_db,
                    "moca_pid": MORANTA26_PID,
                    "row_count": 0,
                    "header_found": False,
                    "has_points": False,
                    "tables_available": False,
                    "query_seconds": query_seconds,
                },
                "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
            }
            _MORANTA26_ROTATION_CACHE[cache_key] = (now, copy.deepcopy(payload))
            return payload
        header_rows = _records(_read_sql(conn, f"""
            SELECT
                h.moca_photseqid,
                h.moca_oid,
                h.pipeline,
                h.flux_units,
                h.original_filename,
                h.comments AS header_comments
            FROM {schema}.moca_photometric_time_series AS h
            WHERE h.moca_pid = :moca_pid
                {visibility_filter}
                AND h.moca_photseqid = :photseqid
        """, {"moca_pid": MORANTA26_PID, "photseqid": photseqid}))
        point_df = _read_sql(conn, f"""
            SELECT
                p.epoch_year,
                ((p.epoch_year - 2000.0) * 365.25 - 5455.0) AS btjd,
                p.flux,
                p.sector
            FROM {schema}.data_photometric_time_series AS p
            WHERE p.moca_photseqid = :photseqid
                AND p.epoch_year IS NOT NULL
                AND p.flux IS NOT NULL
            ORDER BY p.epoch_year
        """, {"photseqid": photseqid}) if header_rows else pd.DataFrame()
        query_seconds = round(time.time() - started, 3)

    rows = _records(point_df)
    payload = {
        "photseqid": photseqid,
        "header": header_rows[0] if header_rows else None,
        "rows": rows,
        "periodogram": _moranta26_periodogram_records(rows),
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "moca_pid": MORANTA26_PID,
            "row_count": len(rows),
            "header_found": bool(header_rows),
            "has_points": bool(rows),
            "tables_available": True,
            "query_seconds": query_seconds,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _MORANTA26_ROTATION_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _mock_moranta26_catalog() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(2606)
    clusters = list(MORANTA26_DEFAULT_CLUSTERS)
    lambdas = list(MORANTA26_DEFAULT_LAMBDAS)
    pipelines = ["SAP", "PDCSAP"]
    prot_id = 1
    for cluster_index, cluster in enumerate(clusters):
        for star_index in range(8):
            oid = 900000 + cluster_index * 100 + star_index
            source_id = str(6300000000000000000 + cluster_index * 1000 + star_index)
            lit_period = 0.4 + 0.22 * star_index + 0.08 * cluster_index
            for lambda_value in lambdas:
                for pipeline_index, pipeline in enumerate(pipelines):
                    sector = 4 + cluster_index * 3 + pipeline_index
                    prob_all = float(np.clip(0.58 + 0.055 * math.log2(lambda_value) + rng.normal(0, 0.08), 0.05, 0.99))
                    prot = float(lit_period * (1.0 + rng.normal(0, 0.09 + 0.015 * pipeline_index)))
                    ignored = 1 if lambda_value != 4 and star_index % 5 == 0 else 0
                    rows.append({
                        "prot_id": prot_id,
                        "moca_oid": oid,
                        "star_key": f"oid:{oid}",
                        "source_id": source_id,
                        "cluster": cluster,
                        "m": lambda_value,
                        "pipeline": pipeline,
                        "sector": sector,
                        "source_rotation_id": 100000 + prot_id,
                        "source_moca_tplcid": 5000 + cluster_index * 100 + star_index * 2 + pipeline_index,
                        "prot": prot,
                        "prot_days_unc": 0.02 * prot,
                        "erru_prot": 0.025 * prot,
                        "errd_prot": 0.018 * prot,
                        "gp_rot": prot,
                        "lit_prot": lit_period if star_index % 7 != 0 else None,
                        "lit_source": "mock literature",
                        "ls_power": float(rng.uniform(0.1, 0.95)),
                        "snr": float(rng.uniform(5, 30)),
                        "rms": float(rng.uniform(0.001, 0.02)),
                        "category": "rotation" if prob_all > 0.68 else "weak",
                        "selected": 1 if prob_all > 0.72 else 0,
                        "revised": prot * 1.03 if star_index == 2 and lambda_value == 4 else None,
                        "has_revised": star_index == 2 and lambda_value == 4,
                        "period_value_source": "gp_rot",
                        "quality": "B" if prob_all > 0.72 else "D",
                        "multiple_periods": 1,
                        "ignored": ignored,
                        "is_public": 1,
                        "rls": "public",
                        "publication_comments": "Mock Mora26 row",
                        "comments": "Mock row",
                        "prot_flags": "Mock row",
                        "prob_rot": prob_all,
                        "prob_snr": prob_all,
                        "prob_asym": prob_all,
                        "prob_rms": prob_all,
                        "prob_ls": prob_all,
                        "final_prob": prob_all,
                        "prob_all": prob_all,
                        "phot_g_mean_mag": 11.0 + star_index,
                        "bp_rp": 1.1 + 0.2 * star_index,
                        "grp": 0.4 + 0.1 * star_index,
                        "report_url": f"https://mocadb.ca/search/results?search-query=oid%28{oid}%29&search-type=star",
                        "has_literature_period": star_index % 7 != 0,
                        "has_light_curve": True,
                    })
                    prot_id += 1
    return {
        "rows": rows,
        "options": {
            "clusters": clusters,
            "lambdas": lambdas,
            "pipelines": pipelines,
            "sectors": sorted({row["sector"] for row in rows}),
            "categories": sorted({row["category"] for row in rows}),
            "qualities": sorted({row["quality"] for row in rows}),
        },
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "moca_pid": MORANTA26_PID,
            "row_count": len(rows),
            "ignored_row_count": sum(1 for row in rows if row.get("ignored")),
            "null_moca_oid_count": 0,
            "light_curve_link_count": len(rows),
            "literature_period_count": sum(1 for row in rows if row.get("has_literature_period")),
            "include_ignored": True,
            "mock": True,
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _mock_moranta26_lightcurve(photseqid: int) -> dict[str, Any]:
    rng = np.random.default_rng(int(photseqid) % 100000)
    time_values = np.linspace(1410.93, 1436.2, 900)
    period = 0.72 + (int(photseqid) % 13) * 0.06
    flux = 1.0 + 0.018 * np.sin(2.0 * np.pi * time_values / period) + rng.normal(0, 0.004, size=time_values.size)
    rows = [
        {
            "epoch_year": float(2000.0 + (time_value + 5455.0) / 365.25),
            "btjd": float(time_value),
            "flux": float(flux_value),
            "sector": int(photseqid) % 30,
        }
        for time_value, flux_value in zip(time_values, flux)
    ]
    return {
        "photseqid": int(photseqid),
        "header": {
            "moca_photseqid": int(photseqid),
            "moca_oid": 900000 + (int(photseqid) % 1000),
            "pipeline": "SAP",
            "flux_units": "relative flux",
            "original_filename": f"mock.moca_tplcid={photseqid}",
            "header_comments": "Mock Mora26 light curve",
        },
        "rows": rows,
        "periodogram": _moranta26_periodogram_records(rows),
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "moca_pid": MORANTA26_PID,
            "row_count": len(rows),
            "header_found": True,
            "has_points": True,
            "mock": True,
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


GROUP_HIERARCHY_DEFAULT_TITLE = "Click on a graph node to explore children and other data visualization tools."


def _group_hierarchy_cache_key(args: dict[str, Any]) -> str:
    return "|".join([_spt_db_cache_key(args), "group-hierarchy", "catalog-v1"])


def _group_hierarchy_string(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text_value = str(value).strip()
    if not text_value or text_value.lower() in {"none", "nan", "null"}:
        return fallback
    return text_value


def _group_hierarchy_row(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    original_aid = _group_hierarchy_string(raw.get("original_aid") or raw.get("moca_aid"))
    if not original_aid:
        return None
    display_aid = _group_hierarchy_string(raw.get("moca_aid"), original_aid)
    parent_aid = _group_hierarchy_string(raw.get("parent_aid"))
    comments = _group_hierarchy_string(raw.get("comments"))
    if original_aid == "OTHERS":
        comments = "Groups with two or less direct children defined in a useful way"
    row = {
        "id": display_aid,
        "aid": original_aid,
        "label": display_aid,
        "moca_aid": display_aid,
        "original_aid": original_aid,
        "parent_id": parent_aid,
        "child_aid": _group_hierarchy_string(raw.get("child_aid")),
        "nobj": _pythonize(raw.get("nobj")),
        "suboptimal_grouping": _pythonize(raw.get("suboptimal_grouping")) or 0,
        "branch": _group_hierarchy_string(raw.get("branch")),
        "branch_depth": _pythonize(raw.get("branch_depth")),
        "optimal_branch_depth": _pythonize(raw.get("optimal_branch_depth")),
        "n_direct_branch_children": _pythonize(raw.get("n_direct_branch_children")),
        "name": _group_hierarchy_string(raw.get("name")),
        "alternate_names": _group_hierarchy_string(raw.get("alternate_names")),
        "physical_nature": _group_hierarchy_string(raw.get("physical_nature")),
        "comments": comments,
        "age_myr": _group_hierarchy_string(raw.get("age_myr")),
        "age_ref": _group_hierarchy_string(raw.get("age_ref")),
        "avg_dist": _pythonize(raw.get("avg_dist")),
        "partial_subgroup_overlap": _pythonize(raw.get("partial_subgroup_overlap")) or 0,
        "complete_parent_overlap": _pythonize(raw.get("complete_parent_overlap")) or 0,
        "relationship_comments": _group_hierarchy_string(raw.get("relationship_comments")),
        "synthetic": False,
    }
    row["search_label"] = " - ".join(
        part for part in (row["original_aid"], row["name"], row["alternate_names"]) if part
    )
    return row


def _group_hierarchy_synthetic_row(aid: str, parent_id: str = "") -> dict[str, Any]:
    aid = _group_hierarchy_string(aid)
    return {
        "id": aid,
        "aid": aid,
        "label": aid,
        "moca_aid": aid,
        "original_aid": aid,
        "parent_id": _group_hierarchy_string(parent_id),
        "child_aid": "",
        "nobj": None,
        "suboptimal_grouping": 0,
        "branch": "",
        "branch_depth": None,
        "optimal_branch_depth": None,
        "n_direct_branch_children": None,
        "name": aid,
        "alternate_names": "",
        "physical_nature": "",
        "comments": "",
        "age_myr": "",
        "age_ref": "",
        "avg_dist": None,
        "partial_subgroup_overlap": 0,
        "complete_parent_overlap": 0,
        "relationship_comments": "",
        "synthetic": True,
        "search_label": aid,
    }


def _group_hierarchy_relationships(conn) -> list[dict[str, Any]]:
    try:
        return _records(_read_sql(conn, """
            SELECT
                moca_aid,
                parent,
                hierarchical_level,
                only_complete_parent_overlap,
                any_partial_subgroup_overlap
            FROM mechanics_all_association_relationships
            ORDER BY parent, hierarchical_level, moca_aid
        """))
    except Exception:
        return []


def _load_group_hierarchy_from_db(args: dict[str, Any]) -> dict[str, Any]:
    cache_key = _group_hierarchy_cache_key(args)
    now = time.time()
    cached = _GROUP_HIERARCHY_CACHE.get(cache_key)
    if cached and now - cached[0] < CACHE_SECONDS:
        payload = copy.deepcopy(cached[1])
        payload["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
        return payload

    engine = _engine(_connection_string(args))
    with engine.connect() as conn:
        started = time.time()
        rows_df = _read_sql(conn, "CALL select_aid_hierarchy()")
        relationship_rows = _group_hierarchy_relationships(conn)
        query_seconds = round(time.time() - started, 3)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in _records(rows_df):
        row = _group_hierarchy_row(raw)
        if not row:
            continue
        base_id = row["id"]
        node_id = base_id
        suffix = 2
        while node_id in seen:
            node_id = f"{base_id}::{suffix}"
            suffix += 1
        row["id"] = node_id
        rows.append(row)
        seen.add(node_id)

    root_nobj = sum(
        float(row.get("nobj") or 0.0)
        for row in rows
        if row.get("parent_id") == "ALL" and isinstance(row.get("nobj"), (int, float))
    )
    if "ALL" not in seen:
        root = _group_hierarchy_synthetic_row("ALL")
        root["name"] = "All MOCAdb associations"
        root["nobj"] = _pythonize(root_nobj if root_nobj > 0 else None)
        rows.append(root)
        seen.add("ALL")

    missing_parents = sorted(
        {
            str(row.get("parent_id") or "")
            for row in rows
            if row.get("parent_id") and row.get("parent_id") not in seen
        }
    )
    for parent_id in missing_parents:
        rows.append(_group_hierarchy_synthetic_row(parent_id))
        seen.add(parent_id)

    row_ids = {row["id"] for row in rows}
    row_aids = {row["original_aid"] for row in rows}
    direct_children: dict[str, list[str]] = {}
    for row in rows:
        parent_id = str(row.get("parent_id") or "")
        if parent_id:
            direct_children.setdefault(parent_id, []).append(row["id"])
    for child_list in direct_children.values():
        child_list.sort()

    descendants: dict[str, list[str]] = {}
    for rel in relationship_rows:
        parent_id = _group_hierarchy_string(rel.get("parent"))
        child_id = _group_hierarchy_string(rel.get("moca_aid"))
        if not parent_id or not child_id or child_id not in row_aids or child_id == parent_id:
            continue
        descendants.setdefault(parent_id, []).append(child_id)
    for parent_id, child_list in descendants.items():
        descendants[parent_id] = sorted(dict.fromkeys(child_list))

    option_by_aid: dict[str, dict[str, Any]] = {}
    for row in rows:
        aid = row.get("original_aid")
        if not aid or aid == "ALL" or aid in option_by_aid:
            continue
        option_by_aid[aid] = {
            "value": aid,
            "node_id": row["id"],
            "label": f"{aid} - {row['name']}" if row.get("name") and row.get("name") != aid else aid,
            "name": row.get("name") or "",
        }
    options = sorted(
        [
            option
            for option in option_by_aid.values()
        ],
        key=lambda option: str(option["value"]),
    )

    payload = {
        "rows": rows,
        "direct_children": direct_children,
        "descendants": descendants,
        "options": options,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": _is_private_db(args),
            "row_count": len(rows),
            "relationship_count": len(relationship_rows),
            "query_seconds": query_seconds,
            "default_title": GROUP_HIERARCHY_DEFAULT_TITLE,
        },
        "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS},
    }
    _GROUP_HIERARCHY_CACHE[cache_key] = (now, copy.deepcopy(payload))
    return payload


def _mock_group_hierarchy_payload() -> dict[str, Any]:
    rows = [
        {**_group_hierarchy_synthetic_row("ALL"), "name": "All MOCAdb associations"},
        {**_group_hierarchy_synthetic_row("YOUNG", "ALL"), "name": "Young nearby groups", "physical_nature": "collection"},
        {**_group_hierarchy_synthetic_row("THA", "YOUNG"), "name": "Tucana-Horologium association", "physical_nature": "association", "age_myr": "40", "avg_dist": 47.0, "synthetic": False},
        {**_group_hierarchy_synthetic_row("BPMG", "YOUNG"), "name": "Beta Pictoris moving group", "physical_nature": "moving group", "age_myr": "26", "avg_dist": 36.0, "synthetic": False},
        {**_group_hierarchy_synthetic_row("ABDMG", "ALL"), "name": "AB Doradus moving group", "physical_nature": "moving group", "age_myr": "133", "avg_dist": 37.0, "synthetic": False},
        {**_group_hierarchy_synthetic_row("ABDMGC", "ABDMG"), "label": "(ABDMGC)", "name": "AB Doradus moving group core", "physical_nature": "moving group", "age_myr": "149", "avg_dist": 21.0, "synthetic": False},
    ]
    return {
        "rows": rows,
        "direct_children": {"ALL": ["ABDMG", "YOUNG"], "YOUNG": ["BPMG", "THA"], "ABDMG": ["ABDMGC"]},
        "descendants": {"ALL": ["ABDMG", "ABDMGC", "BPMG", "THA", "YOUNG"], "YOUNG": ["BPMG", "THA"], "ABDMG": ["ABDMGC"]},
        "options": [{"value": row["id"], "label": f"{row['id']} - {row['name']}", "name": row["name"]} for row in rows if row["id"] != "ALL"],
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "row_count": len(rows),
            "relationship_count": 5,
            "query_seconds": 0.0,
            "default_title": GROUP_HIERARCHY_DEFAULT_TITLE,
            "mock": True,
        },
        "cache": {"hit": False, "ttl_seconds": 0},
    }


def _banyan_sigma_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _banyan_sigma_truthy_option(options: Mapping[str, Any], key: str, default: bool = False) -> bool:
    if key not in options or options.get(key) is None:
        return default
    return _banyan_sigma_truthy(options.get(key))


def _banyan_sigma_top_n(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = BANYAN_SIGMA_DEFAULT_TOP_N
    return max(1, min(value, BANYAN_SIGMA_MAX_TOP_N))


def _banyan_sigma_finite(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if np.ma.is_masked(value):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _banyan_sigma_required_float(payload: Mapping[str, Any], key: str) -> float:
    value = _banyan_sigma_finite(payload.get(key))
    if value is None:
        raise ValueError(f"{key} must be finite")
    return value


def _banyan_sigma_first_finite(payload: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in payload:
            value = _banyan_sigma_finite(payload.get(key))
            if value is not None:
                return value
    return None


def _banyan_sigma_round_pair_to_error(
    value: Any,
    error: Any,
    sig_digits: int = 2,
) -> tuple[Any, Any]:
    value_float = _banyan_sigma_finite(value)
    error_float = _banyan_sigma_finite(error)
    if value_float is None or error_float is None or error_float <= 0:
        return value, error
    decimals = int(sig_digits - 1 - math.floor(math.log10(abs(error_float))))
    decimals = max(-12, min(decimals, 15))
    return round(value_float, decimals), round(error_float, decimals)


def _banyan_sigma_round_imported_observables(observables: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(observables)
    for value_key, error_key in (
        ("pmra", "epmra"),
        ("pmdec", "epmdec"),
        ("rv", "erv"),
        ("plx", "eplx"),
        ("dist", "edist"),
        ("psira", "epsira"),
        ("psidec", "epsidec"),
    ):
        out[value_key], out[error_key] = _banyan_sigma_round_pair_to_error(
            out.get(value_key),
            out.get(error_key),
            sig_digits=2,
        )
    return out


def _banyan_sigma_observables_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    observables = payload.get("observables") if isinstance(payload.get("observables"), Mapping) else payload
    out = {
        "name": str(observables.get("name") or observables.get("designation") or "").strip() or None,
        "ra": _banyan_sigma_required_float(observables, "ra"),
        "dec": _banyan_sigma_required_float(observables, "dec"),
        "pmra": _banyan_sigma_required_float(observables, "pmra"),
        "pmdec": _banyan_sigma_required_float(observables, "pmdec"),
        "epmra": _banyan_sigma_required_float(observables, "epmra"),
        "epmdec": _banyan_sigma_required_float(observables, "epmdec"),
        "rv": _banyan_sigma_finite(observables.get("rv")),
        "erv": _banyan_sigma_finite(observables.get("erv")),
        "plx": _banyan_sigma_finite(observables.get("plx")),
        "eplx": _banyan_sigma_finite(observables.get("eplx")),
        "dist": _banyan_sigma_finite(observables.get("dist")),
        "edist": _banyan_sigma_finite(observables.get("edist")),
        "psira": _banyan_sigma_finite(observables.get("psira")),
        "psidec": _banyan_sigma_finite(observables.get("psidec")),
        "epsira": _banyan_sigma_finite(observables.get("epsira")),
        "epsidec": _banyan_sigma_finite(observables.get("epsidec")),
    }
    if not 0 <= out["ra"] < 360:
        raise ValueError("ra must be in [0, 360)")
    if not -90 <= out["dec"] <= 90:
        raise ValueError("dec must be in [-90, 90]")
    if out["epmra"] < 0 or out["epmdec"] < 0:
        raise ValueError("proper-motion uncertainties must be non-negative")
    for key in ("erv", "eplx", "edist", "epsira", "epsidec"):
        if out.get(key) is not None and out[key] <= 0:
            raise ValueError(f"{key} must be positive when used")
    return out


def _banyan_sigma_call_kwargs(
    observables: Mapping[str, Any],
    options: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    kwargs = {
        "ra": observables["ra"],
        "dec": observables["dec"],
        "pmra": observables["pmra"],
        "pmdec": observables["pmdec"],
        "epmra": observables["epmra"],
        "epmdec": observables["epmdec"],
    }
    used = ["RA", "DEC", "PMRA", "PMDEC"]

    use_rv = _banyan_sigma_truthy(options.get("use_rv"))
    if use_rv:
        if observables.get("rv") is None or observables.get("erv") is None:
            raise ValueError("RV and ERV are both required when radial velocity is enabled")
        kwargs.update({"rv": observables["rv"], "erv": observables["erv"], "use_rv": True})
        used.append("RV")

    distance_mode = str(options.get("distance_mode") or "").strip().lower()
    if not distance_mode:
        if _banyan_sigma_truthy(options.get("use_plx")):
            distance_mode = "plx"
        elif _banyan_sigma_truthy(options.get("use_dist")):
            distance_mode = "dist"
    if distance_mode == "plx":
        if observables.get("plx") is None or observables.get("eplx") is None:
            raise ValueError("PLX and EPLX are both required when parallax is enabled")
        if observables["plx"] <= 0:
            raise ValueError("plx must be positive when parallax is enabled")
        kwargs.update({"plx": observables["plx"], "eplx": observables["eplx"], "use_plx": True})
        used.append("PLX")
    elif distance_mode == "dist":
        if observables.get("dist") is None or observables.get("edist") is None:
            raise ValueError("DIST and EDIST are both required when distance is enabled")
        if observables["dist"] <= 0:
            raise ValueError("dist must be positive when distance is enabled")
        kwargs.update({"dist": observables["dist"], "edist": observables["edist"], "use_dist": True})
        used.append("DIST")
    elif distance_mode not in {"", "none", "off"}:
        raise ValueError("distance_mode must be one of none, plx, or dist")

    if _banyan_sigma_truthy(options.get("use_psi")):
        required = ("psira", "psidec", "epsira", "epsidec")
        if any(observables.get(key) is None for key in required):
            raise ValueError("PSIRA, PSIDEC, EPSIRA, and EPSIDEC are required when PSI is enabled")
        kwargs.update({
            "psira": observables["psira"],
            "psidec": observables["psidec"],
            "epsira": observables["epsira"],
            "epsidec": observables["epsidec"],
            "use_psi": True,
        })
        used.append("PSI")

    if _banyan_sigma_truthy(options.get("unit_priors")):
        kwargs["unit_priors"] = True
    if _banyan_sigma_truthy(options.get("no_xyz")):
        kwargs["no_xyz"] = True

    restrained_distance_range, distance_filter = _banyan_sigma_distance_filter(
        observables,
        options,
        distance_mode,
    )
    if restrained_distance_range is not None:
        kwargs["restrained_distance_range"] = restrained_distance_range
    return kwargs, used, distance_filter


def _banyan_sigma_distance_filter(
    observables: Mapping[str, Any],
    options: Mapping[str, Any],
    distance_mode: str,
) -> tuple[list[float] | None, dict[str, Any]]:
    parallax_enabled = _banyan_sigma_truthy_option(options, "limit_parallax_5sigma", True)
    manual_enabled = _banyan_sigma_truthy_option(options, "use_manual_distance_range", False)
    meta: dict[str, Any] = {
        "limit_parallax_5sigma": parallax_enabled,
        "use_manual_distance_range": manual_enabled,
        "applied": False,
        "source": None,
        "min_pc": None,
        "max_pc": None,
        "upper_unbounded": False,
        "notes": [],
    }
    ranges: list[dict[str, Any]] = []

    if parallax_enabled and distance_mode == "plx":
        plx = observables.get("plx")
        eplx = observables.get("eplx")
        if plx is not None and eplx is not None and plx > 0 and eplx > 0:
            high_plx = plx + 5.0 * eplx
            low_plx = plx - 5.0 * eplx
            if high_plx > 0:
                raw_min_pc = 1000.0 / high_plx
                if low_plx > 0:
                    raw_max_pc = 1000.0 / low_plx
                    upper_unbounded = False
                else:
                    raw_max_pc = BANYAN_SIGMA_DISTANCE_RANGE_UNBOUNDED_MAX_PC
                    upper_unbounded = True
                    meta["notes"].append("The 5-sigma lower parallax bound is non-positive, so only the near-distance bound is applied.")
                min_pc = max(
                    raw_min_pc * (1.0 - BANYAN_SIGMA_PARALLAX_RANGE_INFLATE_PERCENT / 100.0)
                    - BANYAN_SIGMA_PARALLAX_RANGE_INFLATE_PC,
                    0.0,
                )
                if upper_unbounded:
                    max_pc = raw_max_pc
                else:
                    max_pc = max(
                        raw_max_pc * (1.0 + BANYAN_SIGMA_PARALLAX_RANGE_INFLATE_PERCENT / 100.0)
                        + BANYAN_SIGMA_PARALLAX_RANGE_INFLATE_PC,
                        BANYAN_SIGMA_PARALLAX_RANGE_MIN_UPPER_PC,
                    )
                ranges.append({
                    "source": "parallax_5sigma",
                    "min_pc": float(min_pc),
                    "max_pc": float(max_pc),
                    "upper_unbounded": upper_unbounded,
                    "raw_min_pc": float(raw_min_pc),
                    "raw_max_pc": float(raw_max_pc),
                    "inflate_percent": BANYAN_SIGMA_PARALLAX_RANGE_INFLATE_PERCENT,
                    "inflate_pc": BANYAN_SIGMA_PARALLAX_RANGE_INFLATE_PC,
                    "minimum_upper_pc": BANYAN_SIGMA_PARALLAX_RANGE_MIN_UPPER_PC,
                })
        else:
            meta["notes"].append("The parallax 5-sigma filter requires positive PLX and EPLX values.")

    if manual_enabled:
        min_pc = _banyan_sigma_first_finite(
            options,
            "distance_range_min_pc",
            "manual_distance_min_pc",
            "distance_min_pc",
            "range_min_pc",
        )
        max_pc = _banyan_sigma_first_finite(
            options,
            "distance_range_max_pc",
            "manual_distance_max_pc",
            "distance_max_pc",
            "range_max_pc",
        )
        if min_pc is None or max_pc is None:
            raise ValueError("manual distance range requires finite minimum and maximum distances")
        if min_pc < 0 or max_pc < 0:
            raise ValueError("manual distance range values must be non-negative")
        if min_pc > max_pc:
            raise ValueError("manual distance range minimum must not exceed maximum")
        ranges.append({
            "source": "manual",
            "min_pc": float(min_pc),
            "max_pc": float(max_pc),
            "upper_unbounded": False,
        })

    if not ranges:
        return None, meta

    min_pc = max(float(row["min_pc"]) for row in ranges)
    max_pc = min(float(row["max_pc"]) for row in ranges)
    if min_pc > max_pc:
        sources = ", ".join(str(row["source"]) for row in ranges)
        raise ValueError(f"distance range filters have an empty intersection ({sources})")

    upper_unbounded = any(row.get("upper_unbounded") for row in ranges) and math.isclose(
        max_pc,
        BANYAN_SIGMA_DISTANCE_RANGE_UNBOUNDED_MAX_PC,
        rel_tol=0,
        abs_tol=1,
    )
    meta.update({
        "applied": True,
        "source": "+".join(str(row["source"]) for row in ranges),
        "min_pc": min_pc,
        "max_pc": max_pc,
        "upper_unbounded": upper_unbounded,
        "range_components": ranges,
    })
    return [min_pc, max_pc], meta


def _banyan_sigma_hypothesis_info() -> dict[str, Any]:
    global _BANYAN_HYPOTHESES_CACHE
    if _BANYAN_HYPOTHESES_CACHE is not None:
        return _BANYAN_HYPOTHESES_CACHE

    import banyan_sigma.core as banyan_core
    from astropy.table import Table

    model_path = Path(banyan_core.__file__).resolve().parent / "data" / "banyan_sigma_parameters.fits"
    table = Table.read(model_path, format="fits")
    names: list[str] = []
    seen: set[str] = set()
    distance_components: dict[str, list[tuple[float, float]]] = {}
    for row in table:
        raw_name = row["NAME"]
        name = str(raw_name.decode("utf-8") if hasattr(raw_name, "decode") else raw_name).strip().upper()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
        if name and "DISTANCE_MIN" in table.colnames and "DISTANCE_MAX" in table.colnames:
            dmin = _banyan_sigma_finite(row["DISTANCE_MIN"])
            dmax = _banyan_sigma_finite(row["DISTANCE_MAX"])
            if dmin is not None and dmax is not None:
                distance_components.setdefault(name, []).append((dmin, dmax))
    _BANYAN_HYPOTHESES_CACHE = {
        "hypotheses": names,
        "hypothesis_count": len(names),
        "component_count": int(len(table)),
        "distance_components": distance_components,
        "model_path": str(model_path),
        "model_mtime": datetime.fromtimestamp(model_path.stat().st_mtime).isoformat(timespec="seconds"),
    }
    return _BANYAN_HYPOTHESES_CACHE


def _banyan_sigma_hypothesis_filter_meta(
    model_info: Mapping[str, Any],
    distance_filter: Mapping[str, Any],
) -> dict[str, Any]:
    total_count = int(model_info.get("hypothesis_count") or 0)
    meta = {
        "applied": False,
        "tested_count": total_count,
        "total_count": total_count,
        "excluded_count": 0,
    }
    if not distance_filter.get("applied"):
        return meta
    min_pc = _banyan_sigma_finite(distance_filter.get("min_pc"))
    max_pc = _banyan_sigma_finite(distance_filter.get("max_pc"))
    if min_pc is None or max_pc is None:
        return meta

    distance_components = model_info.get("distance_components") or {}
    tested_count = 0
    for name in model_info.get("hypotheses") or []:
        name = str(name)
        components = distance_components.get(name) or []
        if "FIELD" in name or not components:
            tested_count += 1
            continue
        if any(component_min <= max_pc and component_max >= min_pc for component_min, component_max in components):
            tested_count += 1

    meta.update({
        "applied": True,
        "tested_count": int(tested_count),
        "total_count": total_count,
        "excluded_count": max(0, total_count - int(tested_count)),
        "range_min_pc": min_pc,
        "range_max_pc": max_pc,
    })
    return meta


def _banyan_sigma_lnp_only(call_kwargs: dict[str, Any]) -> np.ndarray:
    from banyan_sigma import membership_probability
    import banyan_sigma.core as banyan_core

    original_concat = banyan_core.pd.concat

    def safe_concat(objs, *args, **kwargs):
        try:
            if hasattr(objs, "__len__") and len(objs) == 0:
                return pd.DataFrame()
        except TypeError:
            pass
        return original_concat(objs, *args, **kwargs)

    with _BANYAN_LNP_LOCK:
        banyan_core.pd.concat = safe_concat
        try:
            return np.asarray(membership_probability(**call_kwargs, lnp_only=True), dtype=float)
        finally:
            banyan_core.pd.concat = original_concat


def _banyan_sigma_detail_output(call_kwargs: dict[str, Any], hypotheses: list[str]):
    from banyan_sigma import membership_probability

    encoded = np.array(hypotheses, dtype="S64")
    return membership_probability(**call_kwargs, hypotheses=encoded)


def _banyan_sigma_output_detail_map(output, hypotheses: list[str]) -> dict[str, dict[str, Any]]:
    detail_map: dict[str, dict[str, Any]] = {}
    keys = {
        "LN_P": "ln_p",
        "D_OPT": "d_opt",
        "ED_OPT": "ed_opt",
        "RV_OPT": "rv_opt",
        "ERV_OPT": "erv_opt",
        "X": "x",
        "Y": "y",
        "Z": "z",
        "U": "u",
        "V": "v",
        "W": "w",
        "EX": "ex",
        "EY": "ey",
        "EZ": "ez",
        "EU": "eu",
        "EV": "ev",
        "EW": "ew",
        "XYZ_SEP": "xyz_sep",
        "UVW_SEP": "uvw_sep",
        "XYZ_SIG": "xyz_sig",
        "UVW_SIG": "uvw_sig",
        "MAHALANOBIS": "mahalanobis",
    }
    for hyp in hypotheses:
        try:
            series = output.xs(hyp, axis=1, level=0).iloc[0]
        except Exception:
            continue
        row: dict[str, Any] = {}
        for source_key, target_key in keys.items():
            if source_key in series:
                row[target_key] = _pythonize(series[source_key])
        detail_map[hyp] = row
    return detail_map


def _run_banyan_sigma(payload: Mapping[str, Any]) -> dict[str, Any]:
    observables = _banyan_sigma_observables_from_payload(payload)
    options = payload.get("options") if isinstance(payload.get("options"), Mapping) else payload
    top_n = _banyan_sigma_top_n(options.get("top_n"))
    call_kwargs, used_observables, distance_filter = _banyan_sigma_call_kwargs(observables, options)
    model_info = _banyan_sigma_hypothesis_info()
    hypotheses = model_info["hypotheses"]
    hypothesis_filter = _banyan_sigma_hypothesis_filter_meta(model_info, distance_filter)

    started = time.time()
    lnp = _banyan_sigma_lnp_only(call_kwargs)
    lnp_seconds = round(time.time() - started, 3)
    if lnp.ndim != 2 or lnp.shape[0] < 1 or lnp.shape[1] != len(hypotheses):
        raise RuntimeError("BANYAN Sigma returned an unexpected log-probability shape")

    probabilities = np.exp(lnp[0])
    probabilities = np.where(np.isfinite(probabilities), probabilities, 0.0)
    order = np.argsort(probabilities)[::-1]
    nonfield = np.array(["FIELD" not in name for name in hypotheses], dtype=bool)
    field_probability = float(np.sum(probabilities[~nonfield]))
    ya_probability = float(np.sum(probabilities[nonfield]))
    best_index = int(order[0]) if order.size else -1
    best_hyp = hypotheses[best_index] if best_index >= 0 else None
    nonfield_order = [int(index) for index in order if nonfield[int(index)]]
    best_ya = hypotheses[nonfield_order[0]] if nonfield_order else None

    top_indices = [int(index) for index in order[:top_n]]
    detail_hypotheses = [hypotheses[index] for index in top_indices]
    for name in (best_hyp, best_ya, "FIELD"):
        if name and name in hypotheses and name not in detail_hypotheses:
            detail_hypotheses.append(name)

    detail_started = time.time()
    detail_output = _banyan_sigma_detail_output(call_kwargs, detail_hypotheses)
    detail_seconds = round(time.time() - detail_started, 3)
    detail_map = _banyan_sigma_output_detail_map(detail_output, detail_hypotheses)

    top_rows: list[dict[str, Any]] = []
    for rank, index in enumerate(top_indices, start=1):
        hyp = hypotheses[index]
        row = {
            "rank": rank,
            "hypothesis": hyp,
            "probability": float(probabilities[index]),
            "probability_pct": float(probabilities[index] * 100.0),
            "is_field": "FIELD" in hyp,
        }
        row.update(detail_map.get(hyp, {}))
        top_rows.append({key: _pythonize(value) for key, value in row.items()})

    list_prob_yas = [
        {
            "hypothesis": hypotheses[int(index)],
            "probability_pct": float(probabilities[int(index)] * 100.0),
        }
        for index in order
        if nonfield[int(index)] and probabilities[int(index)] >= 0.05
    ]

    return {
        "observables": {key: _pythonize(value) for key, value in observables.items()},
        "used_observables": used_observables,
        "summary": {
            "ya_probability": ya_probability,
            "ya_probability_pct": ya_probability * 100.0,
            "field_probability": field_probability,
            "field_probability_pct": field_probability * 100.0,
            "best_hyp": best_hyp,
            "best_ya": best_ya,
            "list_prob_yas": list_prob_yas,
        },
        "top_rows": top_rows,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "top_n": top_n,
            "lnp_seconds": lnp_seconds,
            "detail_seconds": detail_seconds,
            "query_seconds": round(lnp_seconds + detail_seconds, 3),
            "hypothesis_count": model_info["hypothesis_count"],
            "component_count": model_info["component_count"],
            "model_path": model_info["model_path"],
            "model_mtime": model_info["model_mtime"],
            "distance_filter": distance_filter,
            "hypothesis_filter": hypothesis_filter,
            "cache_schema": BANYAN_SIGMA_CACHE_SCHEMA,
        },
    }


def _banyan_sigma_run_cache_key(args: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    cfg = _db_config(dict(args))
    cache_payload = {
        "schema": BANYAN_SIGMA_CACHE_SCHEMA,
        "host": cfg.get("host"),
        "username": cfg.get("username"),
        "dbname": cfg.get("dbname"),
        "payload": payload,
    }
    raw = json.dumps(cache_payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_banyan_sigma_stored_from_db(conn, args: Mapping[str, Any], moca_oid: int) -> dict[str, Any]:
    is_public = 0 if _is_private_db(dict(args)) else 1
    summary_df = _read_sql(conn, """
        SELECT
            cbs.id AS cbs_id,
            cbs.moca_oid,
            cbs.moca_aid,
            cbs.moca_bsmdid,
            mbsm.model_name,
            mbsm.date AS model_date,
            mbsm.adopted AS model_adopted,
            cbs.max_observables,
            cbs.mode,
            cbs.observables,
            cbs.ya_prob,
            cbs.list_prob_yas,
            cbs.list_prob_yas AS all_prob_yas,
            cbs.best_hyp,
            cbs.best_ya,
            cbs.d_opt,
            cbs.ed_opt,
            cbs.rv_opt,
            cbs.erv_opt,
            cbs.xyz_sep,
            cbs.xyz_sig,
            cbs.uvw_sep,
            cbs.uvw_sig,
            cbs.x_opt,
            cbs.y_opt,
            cbs.z_opt,
            cbs.u_opt,
            cbs.v_opt,
            cbs.w_opt,
            cbs.mahalanobis,
            cbs.nobs,
            cbs.origin,
            cbs.is_public,
            cbs.modified_timestamp
        FROM calc_banyan_sigma cbs
        LEFT JOIN moca_banyan_sigma_models mbsm
            ON mbsm.moca_bsmdid = cbs.moca_bsmdid
        WHERE cbs.moca_oid = :moca_oid
            AND cbs.max_observables = 1
            AND cbs.is_public = :is_public
            AND (mbsm.adopted = 1 OR mbsm.public_adopted = 1 OR mbsm.moca_bsmdid IS NULL)
        ORDER BY
            COALESCE(mbsm.adopted, 0) DESC,
            COALESCE(mbsm.public_adopted, 0) DESC,
            cbs.nobs DESC,
            cbs.ya_prob DESC,
            cbs.id DESC
        LIMIT 8
    """, {"moca_oid": moca_oid, "is_public": is_public})
    summaries = _records(summary_df)
    cbs_ids = [int(row["cbs_id"]) for row in summaries if row.get("cbs_id") is not None]
    details: list[dict[str, Any]] = []
    if cbs_ids:
        cbs_clause, cbs_params = _sql_in_clause("bsig_cbs", cbs_ids)
        details_df = _read_sql(conn, f"""
            SELECT
                cbsd.cbs_id,
                cbsd.moca_aid,
                cbsd.prob,
                cbsd.d_opt,
                cbsd.ed_opt,
                cbsd.rv_opt,
                cbsd.erv_opt,
                cbsd.xyz_sep,
                cbsd.xyz_sig,
                cbsd.uvw_sep,
                cbsd.uvw_sig,
                cbsd.x_opt,
                cbsd.y_opt,
                cbsd.z_opt,
                cbsd.u_opt,
                cbsd.v_opt,
                cbsd.w_opt,
                cbsd.mahalanobis
            FROM calc_banyan_sigma_details cbsd
            WHERE cbsd.cbs_id IN ({cbs_clause})
            ORDER BY cbsd.cbs_id, cbsd.prob DESC
            LIMIT 200
        """, cbs_params)
        details = _records(details_df)
    return {
        "summaries": summaries,
        "details": details,
        "meta": {
            "summary_count": len(summaries),
            "detail_count": len(details),
            "is_public_filter": is_public,
        },
    }


def _load_banyan_sigma_object_from_db(args: Mapping[str, Any], moca_oid: int) -> dict[str, Any]:
    private_db = _is_private_db(dict(args))
    coord_adopt = "eq.adopt_as_reference = 1" if private_db else "eq.public_adopt_as_reference = 1"
    pm_adopt = "pm.adopted = 1" if private_db else "pm.public_adopted = 1"
    plx_adopt = "plx.adopted = 1" if private_db else "plx.public_adopted = 1"
    dist_adopt = "dist.adopted = 1" if private_db else "dist.public_adopted = 1"
    rv_public_order = "rv.is_public ASC" if private_db else "rv.is_public DESC"
    engine = _engine(_connection_string(dict(args)))
    with engine.connect() as conn:
        rows = _records(_read_sql(conn, f"""
            SELECT
                mo.moca_oid,
                mo.designation,
                mo.moca_designation,
                mo.ra AS object_ra,
                mo.`dec` AS object_dec,
                COALESCE(eq.ra, mo.ra) AS ra,
                COALESCE(eq.`dec`, mo.`dec`) AS `dec`,
                eq.id AS coordinates_id,
                eq.moca_pid AS coordinates_moca_pid,
                eq.mission_name AS coordinates_mission_name,
                eq.data_release AS coordinates_data_release,
                pm.id AS proper_motion_id,
                pm.pmra_masyr AS pmra,
                pm.pmdec_masyr AS pmdec,
                pm.pmra_masyr_unc AS epmra,
                pm.pmdec_masyr_unc AS epmdec,
                pm.moca_pid AS proper_motion_moca_pid,
                pm.mission_name AS proper_motion_mission_name,
                pm.data_release AS proper_motion_data_release,
                plx.id AS parallax_id,
                plx.parallax_mas AS plx,
                plx.parallax_mas_unc AS eplx,
                plx.ruwe AS plx_ruwe,
                plx.moca_pid AS parallax_moca_pid,
                plx.mission_name AS parallax_mission_name,
                plx.data_release AS parallax_data_release,
                dist.id AS distance_id,
                dist.distance_pc AS dist,
                dist.distance_pc_unc AS edist,
                dist.photometric_estimate AS distance_photometric_estimate,
                dist.moca_pid AS distance_moca_pid,
                rv.id AS combined_rv_id,
                rv.radial_velocity_kms AS rv,
                rv.radial_velocity_kms_unc AS erv,
                rv.n_measurements AS rv_n_measurements,
                rv.n_epochs AS rv_n_epochs,
                rv.is_public AS rv_is_public
            FROM moca_objects mo
            LEFT JOIN data_equatorial_coordinates eq
                ON eq.moca_oid = mo.moca_oid
                AND eq.ignored = 0
                AND {coord_adopt}
            LEFT JOIN data_proper_motions pm
                ON pm.moca_oid = mo.moca_oid
                AND pm.ignored = 0
                AND {pm_adopt}
            LEFT JOIN data_parallaxes plx
                ON plx.moca_oid = mo.moca_oid
                AND plx.ignored = 0
                AND {plx_adopt}
            LEFT JOIN data_distances dist
                ON dist.moca_oid = mo.moca_oid
                AND dist.ignored = 0
                AND dist.photometric_estimate = 0
                AND {dist_adopt}
            LEFT JOIN calc_radial_velocities_combined rv
                ON rv.moca_oid = mo.moca_oid
                AND rv.ignored = 0
            WHERE mo.moca_oid = :moca_oid
            ORDER BY {rv_public_order}, rv.id DESC
            LIMIT 1
        """, {"moca_oid": moca_oid}))
        if not rows:
            raise ValueError(f"No MOCAdb object found for moca_oid={moca_oid}")
        row = rows[0]
        stored = _load_banyan_sigma_stored_from_db(conn, args, moca_oid)

    observables = {
        "name": row.get("designation") or f"oid{moca_oid}",
        "ra": row.get("ra"),
        "dec": row.get("dec"),
        "pmra": row.get("pmra"),
        "pmdec": row.get("pmdec"),
        "epmra": row.get("epmra"),
        "epmdec": row.get("epmdec"),
        "rv": row.get("rv"),
        "erv": row.get("erv"),
        "plx": row.get("plx"),
        "eplx": row.get("eplx"),
        "dist": row.get("dist"),
        "edist": row.get("edist"),
        "psira": None,
        "psidec": None,
        "epsira": None,
        "epsidec": None,
    }
    observables = _banyan_sigma_round_imported_observables(observables)
    return {
        "object": row,
        "observables": observables,
        "stored": stored,
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": private_db,
            "observables_rounded_to_error_sig_digits": 2,
            "has_required_observables": all(
                observables.get(key) is not None
                for key in ("ra", "dec", "pmra", "pmdec", "epmra", "epmdec")
            ),
        },
    }


def _mock_banyan_sigma_object(moca_oid: int = 999001) -> dict[str, Any]:
    observables = {
        "name": "AU Mic",
        "ra": 311.2911826481039,
        "dec": -31.3425000799281,
        "pmra": 281.319,
        "pmdec": -360.148,
        "epmra": 0.022,
        "epmdec": 0.019,
        "rv": -5.2,
        "erv": 0.7,
        "plx": 102.943,
        "eplx": 0.023,
        "dist": None,
        "edist": None,
        "psira": None,
        "psidec": None,
        "epsira": None,
        "epsidec": None,
    }
    return {
        "object": {
            "moca_oid": moca_oid,
            "designation": "AU Mic",
            "ra": observables["ra"],
            "dec": observables["dec"],
        },
        "observables": observables,
        "stored": {
            "summaries": [{
                "moca_oid": moca_oid,
                "moca_aid": "BPMG",
                "moca_bsmdid": 23,
                "model_name": "Mock adopted model",
                "max_observables": 1,
                "observables": "RA,DEC,PMRA,PMDEC,PLX,RV",
                "ya_prob": 99.8,
                "all_prob_yas": "BPMG(100)",
                "best_hyp": "BPMG",
                "best_ya": "BPMG",
                "d_opt": 9.71,
                "rv_opt": -5.2,
                "nobs": 6,
            }],
            "details": [{
                "cbs_id": 1,
                "moca_aid": "BPMG",
                "prob": 99.8,
                "d_opt": 9.71,
                "rv_opt": -5.2,
                "xyz_sep": 13.4,
                "uvw_sep": 0.89,
            }],
            "meta": {"summary_count": 1, "detail_count": 1, "is_public_filter": 0},
        },
        "meta": {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "private_db": False,
            "has_required_observables": True,
            "mock": True,
        },
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


@app.get("/group-hierarchy")
@app.get("/group_hierarchy")
@app.get("/js/group-hierarchy")
@app.get("/js/group_hierarchy")
def group_hierarchy_fast_page():
    return send_from_directory(STATIC_DIR, "group_hierarchy.html")


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


@app.get("/moca-explorer")
@app.get("/moca_explorer")
@app.get("/js/moca-explorer")
@app.get("/js/moca_explorer")
def moca_explorer_fast_page():
    return send_from_directory(STATIC_DIR, "moca_explorer.html")


@app.get("/banyan-sigma")
@app.get("/banyan_sigma")
@app.get("/banyansigma")
@app.get("/js/banyan-sigma")
@app.get("/js/banyan_sigma")
@app.get("/js/banyansigma")
def banyan_sigma_page():
    return send_from_directory(STATIC_DIR, "banyan_sigma.html")


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


@app.get("/xyz")
@app.get("/js/xyz")
def xyzuvw_three_page():
    return send_from_directory(STATIC_DIR, "xyzuvw_three.html")


@app.get("/xyz-dual")
@app.get("/xyz_dual")
@app.get("/js/xyz-dual")
@app.get("/js/xyz_dual")
def xyz2_three_page():
    return send_from_directory(STATIC_DIR, "xyz2_three.html")


@app.get("/xyz-plotly")
@app.get("/xyz_plotly")
@app.get("/js/xyz-plotly")
@app.get("/js/xyz_plotly")
def xyzuvw_plotly_page():
    return send_from_directory(STATIC_DIR, "xyzuvw.html")


@app.get("/xyz-dual-plotly")
@app.get("/xyz_dual_plotly")
@app.get("/js/xyz-dual-plotly")
@app.get("/js/xyz_dual_plotly")
def xyz2_plotly_page():
    return send_from_directory(STATIC_DIR, "xyz2.html")


@app.get("/xyzuvw")
@app.get("/xyzuvw-fast")
@app.get("/xyzuvw_fast")
@app.get("/xyzuvw-three")
@app.get("/xyzuvw_three")
@app.get("/spatial-kinematics")
@app.get("/spatial-kinematics-fast")
@app.get("/js/xyzuvw")
@app.get("/js/xyzuvw-fast")
@app.get("/js/xyzuvw_fast")
@app.get("/js/xyzuvw-three")
@app.get("/js/xyzuvw_three")
@app.get("/js/spatial-kinematics")
@app.get("/js/spatial-kinematics-fast")
def xyzuvw_legacy_redirect():
    path = "/js/xyz" if request.path.startswith("/js/") else "/xyz"
    return _redirect_with_query(path)


@app.get("/xyz2")
@app.get("/js/xyz2")
@app.get("/xyz2-three")
@app.get("/xyz2_three")
@app.get("/js/xyz2-three")
@app.get("/js/xyz2_three")
def xyz2_legacy_redirect():
    path = "/js/xyz-dual" if request.path.startswith("/js/") else "/xyz-dual"
    return _redirect_with_query(path)


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


@app.get("/legacy-radial-velocities")
@app.get("/legacy_radial_velocities")
@app.get("/legacy-rvs")
@app.get("/legacy_rvs")
@app.get("/js/legacy-radial-velocities")
@app.get("/js/legacy_radial_velocities")
@app.get("/js/legacy-rvs")
@app.get("/js/legacy_rvs")
def legacy_radial_velocities_page():
    return send_from_directory(STATIC_DIR, "legacy_radial_velocities.html")


@app.get("/moranta26-rotation")
@app.get("/moranta26_rotation")
@app.get("/js/moranta26-rotation")
@app.get("/js/moranta26_rotation")
def moranta26_rotation_page():
    return send_from_directory(STATIC_DIR, "moranta26_rotation.html")


@app.get("/rvbam-explorer")
@app.get("/rvbam_explorer")
@app.get("/js/rvbam-explorer")
@app.get("/js/rvbam_explorer")
def rvbam_explorer_page():
    return send_from_directory(STATIC_DIR, "rvbam_explorer.html")


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
            for key in ("distances", "photometry", "spectra", "designations", "spectralIndices", "equivalentWidths", "ages"):
                catalog[key] = [row for row in catalog[key] if int(row["moca_oid"]) in keep_oids]
        payload["meta"] = {
            **payload["meta"],
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "object_count": len(catalog["objects"]),
            "photometry_count": len(catalog["photometry"]),
            "spectra_count": len(catalog.get("spectra", [])),
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
            "spt_axis": None,
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


@app.get("/api/group-hierarchy/catalog")
@app.get("/api/group_hierarchy/catalog")
@app.get("/js/api/group-hierarchy/catalog")
@app.get("/js/api/group_hierarchy/catalog")
def group_hierarchy_catalog():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_group_hierarchy_payload()})
        payload = _load_group_hierarchy_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "rows": [],
            "direct_children": {},
            "descendants": {},
            "options": [],
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "row_count": 0,
                "default_title": GROUP_HIERARCHY_DEFAULT_TITLE,
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/group-hierarchy/cache/clear")
@app.post("/api/group_hierarchy/cache/clear")
@app.post("/js/api/group-hierarchy/cache/clear")
@app.post("/js/api/group_hierarchy/cache/clear")
def group_hierarchy_clear_cache():
    group_count = len(_GROUP_HIERARCHY_CACHE)
    _GROUP_HIERARCHY_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {"groupHierarchy": group_count},
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.get("/api/moca-explorer/options")
@app.get("/api/moca_explorer/options")
@app.get("/js/api/moca-explorer/options")
@app.get("/js/api/moca_explorer/options")
def moca_explorer_options():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_moca_explorer_options()})
        payload = _load_moca_explorer_options_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "associations": [],
            "mtids": [],
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/moca-explorer/search")
@app.get("/api/moca_explorer/search")
@app.get("/js/api/moca-explorer/search")
@app.get("/js/api/moca_explorer/search")
def moca_explorer_object_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            q = str(query or "").lower()
            options = [
                {"value": 602, "moca_oid": 602, "designation": "SIMP J013656.5+093347.3", "label": "oid602: SIMP J013656.5+093347.3"},
                {"value": 10995, "moca_oid": 10995, "designation": "2MASS J05591914-1404488", "label": "oid10995: 2MASS J05591914-1404488"},
                {"value": 506921, "moca_oid": 506921, "designation": "V* V2502 Oph", "label": "oid506921: V* V2502 Oph"},
            ]
            if q:
                options = [row for row in options if q in str(row.get("label") or "").lower()]
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


@app.get("/api/moca-explorer/associations/search")
@app.get("/api/moca_explorer/associations/search")
@app.get("/js/api/moca-explorer/associations/search")
@app.get("/js/api/moca_explorer/associations/search")
def moca_explorer_association_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            q = str(query or "").lower()
            options = _mock_moca_explorer_options()["associations"]
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


@app.get("/api/moca-explorer/data")
@app.get("/api/moca_explorer/data")
@app.get("/js/api/moca-explorer/data")
@app.get("/js/api/moca_explorer/data")
def moca_explorer_data():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_moca_explorer_payload(args)})
        payload = _load_moca_explorer_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "selection": _moca_explorer_selection(args),
            "members": [],
            "objects": [],
            "models": [],
            "sequences": {},
            "labels": [],
            "sptAxis": [],
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "member_count": 0,
                "object_count": 0,
                "model_count": 0,
                "sequence_count": 0,
                "label_count": 0,
                "spt_axis_count": 0,
                "truncated": False,
                "max_objects": _moca_explorer_parse_max_objects(args.get("max_objects") or args.get("limit")),
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/moca-explorer/cache/clear")
@app.post("/api/moca_explorer/cache/clear")
@app.post("/js/api/moca-explorer/cache/clear")
@app.post("/js/api/moca_explorer/cache/clear")
def moca_explorer_clear_cache():
    moca_explorer_count = len(_MOCA_EXPLORER_CACHE)
    _MOCA_EXPLORER_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {"mocaExplorer": moca_explorer_count},
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.get("/api/banyan-sigma/model")
@app.get("/api/banyan_sigma/model")
@app.get("/js/api/banyan-sigma/model")
@app.get("/js/api/banyan_sigma/model")
def banyan_sigma_model():
    try:
        info = _banyan_sigma_hypothesis_info()
        private_keys = {"hypotheses", "distance_components"}
        public_info = {key: value for key, value in info.items() if key not in private_keys}
        return jsonify({"ok": True, "source": "banyan_sigma", "model": public_info})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "model": {},
        }), 500


@app.get("/api/banyan-sigma/search")
@app.get("/api/banyan_sigma/search")
@app.get("/js/api/banyan-sigma/search")
@app.get("/js/api/banyan_sigma/search")
def banyan_sigma_search():
    args = dict(request.args)
    query = args.get("q") or args.get("search") or ""
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            options = [{
                "value": 999001,
                "moca_oid": 999001,
                "designation": "AU Mic",
                "canonical_designation": "AU Mic",
                "label": "AU Mic",
            }]
            q = str(query or "").strip().lower()
            if q:
                options = [row for row in options if q in str(row.get("label") or "").lower() or q in str(row.get("moca_oid") or "")]
            return jsonify({"ok": True, "source": "mock", "options": options, "meta": {"row_count": len(options)}})
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


@app.get("/api/banyan-sigma/object/<int:moca_oid>")
@app.get("/api/banyan_sigma/object/<int:moca_oid>")
@app.get("/js/api/banyan-sigma/object/<int:moca_oid>")
@app.get("/js/api/banyan_sigma/object/<int:moca_oid>")
def banyan_sigma_object(moca_oid: int):
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_banyan_sigma_object(moca_oid)})
        payload = _load_banyan_sigma_object_from_db(args, moca_oid)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "object": {},
            "observables": {},
            "stored": {"summaries": [], "details": [], "meta": {"summary_count": 0, "detail_count": 0}},
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
        }), 500


@app.post("/api/banyan-sigma/run")
@app.post("/api/banyan_sigma/run")
@app.post("/js/api/banyan-sigma/run")
@app.post("/js/api/banyan_sigma/run")
def banyan_sigma_run():
    args = dict(request.args)
    payload = request.get_json(silent=True) or {}
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            result = {
                "observables": _mock_banyan_sigma_object()["observables"],
                "used_observables": ["RA", "DEC", "PMRA", "PMDEC", "PLX", "RV"],
                "summary": {
                    "ya_probability": 0.998,
                    "ya_probability_pct": 99.8,
                    "field_probability": 0.002,
                    "field_probability_pct": 0.2,
                    "best_hyp": "BPMG",
                    "best_ya": "BPMG",
                    "list_prob_yas": [{"hypothesis": "BPMG", "probability_pct": 99.8}],
                },
                "top_rows": [
                    {"rank": 1, "hypothesis": "BPMG", "probability": 0.998, "probability_pct": 99.8, "d_opt": 9.71, "rv_opt": -5.2, "xyz_sep": 13.4, "uvw_sep": 0.89, "mahalanobis": 1.75},
                    {"rank": 2, "hypothesis": "FIELD", "probability": 0.002, "probability_pct": 0.2, "is_field": True},
                ],
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "top_n": 4,
                    "lnp_seconds": 0.0,
                    "detail_seconds": 0.0,
                    "query_seconds": 0.0,
                    "hypothesis_count": 7697,
                    "component_count": 11412,
                    "distance_filter": {
                        "applied": True,
                        "source": "parallax_5sigma",
                        "min_pc": 0.0,
                        "max_pc": 75.0,
                    },
                    "hypothesis_filter": {
                        "applied": True,
                        "tested_count": 91,
                        "total_count": 7697,
                        "excluded_count": 7606,
                    },
                    "mock": True,
                },
            }
            return jsonify({"ok": True, "source": "mock", "cache": {"hit": False, "ttl_seconds": 0}, "result": result})

        cache_key = _banyan_sigma_run_cache_key(args, payload)
        now = time.time()
        cached = _BANYAN_SIGMA_CACHE.get(cache_key)
        if cached and now - cached[0] < CACHE_SECONDS:
            result = copy.deepcopy(cached[1])
            result["cache"] = {"hit": True, "ttl_seconds": CACHE_SECONDS}
            return jsonify({"ok": True, "source": "banyan_sigma", **result})

        result_payload = {"result": _run_banyan_sigma(payload), "cache": {"hit": False, "ttl_seconds": CACHE_SECONDS}}
        moca_oid = _banyan_sigma_finite(payload.get("moca_oid"))
        if moca_oid is not None and int(moca_oid) > 0:
            try:
                engine = _engine(_connection_string(args))
                with engine.connect() as conn:
                    result_payload["stored"] = _load_banyan_sigma_stored_from_db(conn, args, int(moca_oid))
            except Exception as stored_exc:
                result_payload["stored"] = {
                    "summaries": [],
                    "details": [],
                    "meta": {"summary_count": 0, "detail_count": 0},
                    "error": f"{type(stored_exc).__name__}: {stored_exc}",
                }
        _BANYAN_SIGMA_CACHE[cache_key] = (now, copy.deepcopy(result_payload))
        return jsonify({"ok": True, "source": "banyan_sigma", **result_payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "result": {},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/banyan-sigma/cache/clear")
@app.post("/api/banyan_sigma/cache/clear")
@app.post("/js/api/banyan-sigma/cache/clear")
@app.post("/js/api/banyan_sigma/cache/clear")
def banyan_sigma_clear_cache():
    count = len(_BANYAN_SIGMA_CACHE)
    _BANYAN_SIGMA_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {"banyanSigma": count},
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


@app.get("/api/legacy-radial-velocities/options")
@app.get("/api/legacy_radial_velocities/options")
@app.get("/js/api/legacy-radial-velocities/options")
@app.get("/js/api/legacy_radial_velocities/options")
def legacy_radial_velocities_options():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_legacy_rv_options()})
        payload = _load_legacy_rv_options_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "options": [],
            "value": None,
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "dataset_count": 0},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/legacy-radial-velocities/data")
@app.get("/api/legacy_radial_velocities/data")
@app.get("/js/api/legacy-radial-velocities/data")
@app.get("/js/api/legacy_radial_velocities/data")
def legacy_radial_velocities_data():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_legacy_rv_payload(args)})
        payload = _load_legacy_rv_dataset_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "selection": {},
            "datasetInfo": {},
            "rows": [],
            "images": {"chi2_url": "", "best_model_fit_url": ""},
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "row_count": 0},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/legacy-radial-velocities/cache/clear")
@app.post("/api/legacy_radial_velocities/cache/clear")
@app.post("/js/api/legacy-radial-velocities/cache/clear")
@app.post("/js/api/legacy_radial_velocities/cache/clear")
def legacy_radial_velocities_clear_cache():
    rv_count = len(_LEGACY_RV_CACHE)
    _LEGACY_RV_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {"legacyRadialVelocities": rv_count},
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.get("/api/moranta26-rotation/catalog")
@app.get("/api/moranta26_rotation/catalog")
@app.get("/js/api/moranta26-rotation/catalog")
@app.get("/js/api/moranta26_rotation/catalog")
def moranta26_rotation_catalog():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_moranta26_catalog()})
        payload = _load_moranta26_catalog_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "rows": [],
            "options": {
                "clusters": list(MORANTA26_DEFAULT_CLUSTERS),
                "lambdas": list(MORANTA26_DEFAULT_LAMBDAS),
                "pipelines": [],
                "sectors": [],
                "categories": [],
                "qualities": [],
            },
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "moca_pid": MORANTA26_PID,
                "row_count": 0,
                "include_ignored": True,
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/moranta26-rotation/lightcurve/<int:photseqid>")
@app.get("/api/moranta26_rotation/lightcurve/<int:photseqid>")
@app.get("/js/api/moranta26-rotation/lightcurve/<int:photseqid>")
@app.get("/js/api/moranta26_rotation/lightcurve/<int:photseqid>")
def moranta26_rotation_lightcurve(photseqid: int):
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_moranta26_lightcurve(photseqid)})
        payload = _load_moranta26_lightcurve_from_db(args, int(photseqid))
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "photseqid": int(photseqid),
            "header": None,
            "rows": [],
            "periodogram": [],
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "moca_pid": MORANTA26_PID,
                "row_count": 0,
                "header_found": False,
                "has_points": False,
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/moranta26-rotation/cache/clear")
@app.post("/api/moranta26_rotation/cache/clear")
@app.post("/js/api/moranta26-rotation/cache/clear")
@app.post("/js/api/moranta26_rotation/cache/clear")
def moranta26_rotation_clear_cache():
    moranta_count = len(_MORANTA26_ROTATION_CACHE)
    _MORANTA26_ROTATION_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {"moranta26Rotation": moranta_count},
        "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    })


@app.get("/api/rvbam-explorer/search")
@app.get("/api/rvbam-explorer/runs")
@app.get("/api/rvbam_explorer/search")
@app.get("/api/rvbam_explorer/runs")
@app.get("/js/api/rvbam-explorer/search")
@app.get("/js/api/rvbam-explorer/runs")
@app.get("/js/api/rvbam_explorer/search")
@app.get("/js/api/rvbam_explorer/runs")
def rvbam_explorer_runs():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_rvbam_runs(args)})
        payload = _load_rvbam_runs_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "runs": [],
            "value": None,
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "run_count": 0},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/rvbam-explorer/literature-comparison")
@app.get("/api/rvbam-explorer/rv-literature-comparison")
@app.get("/api/rvbam_explorer/literature-comparison")
@app.get("/api/rvbam_explorer/rv-literature-comparison")
@app.get("/js/api/rvbam-explorer/literature-comparison")
@app.get("/js/api/rvbam-explorer/rv-literature-comparison")
@app.get("/js/api/rvbam_explorer/literature-comparison")
@app.get("/js/api/rvbam_explorer/rv-literature-comparison")
def rvbam_explorer_literature_comparison():
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_rvbam_literature_comparison(args)})
        payload = _load_rvbam_literature_comparison_from_db(args)
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        app.logger.exception("RVBAM literature comparison failed")
        meta = {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "candidate_run_count": 0,
            "point_count": 0,
        }
        if _is_local_app_request():
            meta["traceback"] = traceback.format_exc()
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "points": [],
            "meta": meta,
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/rvbam-explorer/run/<int:run_id>")
@app.get("/api/rvbam_explorer/run/<int:run_id>")
@app.get("/js/api/rvbam-explorer/run/<int:run_id>")
@app.get("/js/api/rvbam_explorer/run/<int:run_id>")
def rvbam_explorer_run(run_id: int):
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_rvbam_run_payload(args, run_id)})
        payload = _load_rvbam_run_from_db(args, int(run_id))
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "run": {},
            "segments": [],
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "segment_count": 0},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/rvbam-explorer/segment/<int:segment_id>")
@app.get("/api/rvbam_explorer/segment/<int:segment_id>")
@app.get("/js/api/rvbam-explorer/segment/<int:segment_id>")
@app.get("/js/api/rvbam_explorer/segment/<int:segment_id>")
def rvbam_explorer_segment(segment_id: int):
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_rvbam_segment_payload(args, segment_id)})
        payload = _load_rvbam_segment_from_db(args, int(segment_id))
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "segment": {},
            "run": {},
            "samplingRun": {},
            "parameters": [],
            "payloads": [],
            "images": {"model_fit_url": "", "corner_url": ""},
            "meta": {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"},
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/rvbam-explorer/segment/<int:segment_id>/posterior-summary")
@app.get("/api/rvbam-explorer/segment/<int:segment_id>/samples")
@app.get("/api/rvbam_explorer/segment/<int:segment_id>/posterior-summary")
@app.get("/api/rvbam_explorer/segment/<int:segment_id>/samples")
@app.get("/js/api/rvbam-explorer/segment/<int:segment_id>/posterior-summary")
@app.get("/js/api/rvbam-explorer/segment/<int:segment_id>/samples")
@app.get("/js/api/rvbam_explorer/segment/<int:segment_id>/posterior-summary")
@app.get("/js/api/rvbam_explorer/segment/<int:segment_id>/samples")
def rvbam_explorer_segment_posterior(segment_id: int):
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({"ok": True, "source": "mock", **_mock_rvbam_posterior_payload(args, segment_id)})
        payload = _load_rvbam_posterior_from_db(args, int(segment_id))
        return jsonify({"ok": True, "source": "MOCAdb", **payload})
    except Exception as exc:
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "segment": {},
            "selectedParams": [],
            "parameterOptions": [],
            "summaries": [],
            "histograms": {},
            "correlation": {"labels": [], "matrix": []},
            "samples": [],
            "payload": {},
            "meta": {
                "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "sample_count": 0,
                "returned_sample_count": 0,
            },
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/rvbam-explorer/segment/<int:segment_id>/rebuilt-corner")
@app.get("/api/rvbam-explorer/segment/<int:segment_id>/corner-plot")
@app.get("/api/rvbam_explorer/segment/<int:segment_id>/rebuilt-corner")
@app.get("/api/rvbam_explorer/segment/<int:segment_id>/corner-plot")
@app.get("/js/api/rvbam-explorer/segment/<int:segment_id>/rebuilt-corner")
@app.get("/js/api/rvbam-explorer/segment/<int:segment_id>/corner-plot")
@app.get("/js/api/rvbam_explorer/segment/<int:segment_id>/rebuilt-corner")
@app.get("/js/api/rvbam_explorer/segment/<int:segment_id>/corner-plot")
def rvbam_explorer_segment_rebuilt_corner(segment_id: int):
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({
                "ok": True,
                "source": "mock",
                "available": False,
                "selectedParams": [],
                "image": {},
                "payload": {},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "message": "Mock RVBAM runs do not have persisted weighted corner payloads.",
                },
                "cache": {"hit": False, "ttl_seconds": 0},
            })
        payload = _load_rvbam_rebuilt_corner_from_db(args, int(segment_id))
        return jsonify({"ok": True, "source": "MOCAdb+RVBAM-corner", **payload})
    except Exception as exc:
        app.logger.exception("RVBAM rebuilt corner failed for segment_id=%s", segment_id)
        meta = {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "sample_count": 0,
            "returned_sample_count": 0,
        }
        if _is_local_app_request():
            meta["traceback"] = traceback.format_exc()
        return jsonify({
            "ok": False,
            "source": "none",
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "selectedParams": [],
            "image": {},
            "payload": {},
            "meta": meta,
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/rvbam-explorer/run/<int:run_id>/global-corner")
@app.get("/api/rvbam-explorer/run/<int:run_id>/global-corner-plot")
@app.get("/api/rvbam_explorer/run/<int:run_id>/global-corner")
@app.get("/api/rvbam_explorer/run/<int:run_id>/global-corner-plot")
@app.get("/js/api/rvbam-explorer/run/<int:run_id>/global-corner")
@app.get("/js/api/rvbam-explorer/run/<int:run_id>/global-corner-plot")
@app.get("/js/api/rvbam_explorer/run/<int:run_id>/global-corner")
@app.get("/js/api/rvbam_explorer/run/<int:run_id>/global-corner-plot")
def rvbam_explorer_run_global_corner(run_id: int):
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({
                "ok": True,
                "source": "mock",
                "available": False,
                "run": {"moca_rv_sample_run_id": int(run_id)},
                "selectedParams": [],
                "image": {},
                "segments": [],
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "message": "Mock RVBAM runs do not have persisted weighted corner payloads.",
                },
                "cache": {"hit": False, "ttl_seconds": 0},
            })
        payload = _load_rvbam_global_corner_from_db(args, int(run_id))
        return jsonify({"ok": True, "source": "MOCAdb+RVBAM-global-corner", **payload})
    except Exception as exc:
        app.logger.exception("RVBAM global corner failed for run_id=%s", run_id)
        meta = {
            "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "sample_count": 0,
            "returned_sample_count": 0,
        }
        if _is_local_app_request():
            meta["traceback"] = traceback.format_exc()
        return jsonify({
            "ok": False,
            "source": "none",
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "run": {"moca_rv_sample_run_id": int(run_id)},
            "selectedParams": [],
            "image": {},
            "segments": [],
            "meta": meta,
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.get("/api/rvbam-explorer/segment/<int:segment_id>/rebuilt-fit")
@app.get("/api/rvbam-explorer/segment/<int:segment_id>/reconstructed-fit")
@app.get("/api/rvbam_explorer/segment/<int:segment_id>/rebuilt-fit")
@app.get("/api/rvbam_explorer/segment/<int:segment_id>/reconstructed-fit")
@app.get("/js/api/rvbam-explorer/segment/<int:segment_id>/rebuilt-fit")
@app.get("/js/api/rvbam-explorer/segment/<int:segment_id>/reconstructed-fit")
@app.get("/js/api/rvbam_explorer/segment/<int:segment_id>/rebuilt-fit")
@app.get("/js/api/rvbam_explorer/segment/<int:segment_id>/reconstructed-fit")
def rvbam_explorer_segment_rebuilt_fit(segment_id: int):
    args = dict(request.args)
    try:
        if args.get("mock") in {"1", "true", "yes"}:
            return jsonify({
                "ok": True,
                "source": "mock",
                "available": False,
                "localModelFit": _rvbam_local_model_status("mock_grid"),
                "segment": {},
                "run": {},
                "data": [],
                "model": [],
                "theta": {},
                "meta": {
                    "loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "message": "Mock RVBAM runs do not have local HDF5 model grids.",
                },
                "cache": {"hit": False, "ttl_seconds": 0},
            })
        payload = _load_rvbam_rebuilt_fit_from_db(args, int(segment_id))
        return jsonify({"ok": True, "source": "MOCAdb+local-HDF5", **payload})
    except Exception as exc:
        app.logger.exception("RVBAM rebuilt fit failed for segment_id=%s", segment_id)
        meta = {"loaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"}
        if _is_local_app_request():
            import sys
            meta.update({
                "traceback": traceback.format_exc(),
                "python_version": sys.version,
                "rvbam_package_dir": str(RVBAM_PACKAGE_DIR),
                "rvbam_model_grid_hdf5_dir": str(RVBAM_LOCAL_MODEL_DIR),
                "rvbam_model_grid_hdf5_dirs": [str(path) for path in RVBAM_LOCAL_MODEL_DIRS],
            })
        return jsonify({
            "ok": False,
            "source": "none",
            "error": f"{type(exc).__name__}: {exc}",
            "available": False,
            "localModelFit": {},
            "segment": {},
            "run": {},
            "data": [],
            "model": [],
            "theta": {},
            "meta": meta,
            "cache": {"hit": False, "ttl_seconds": 0},
        }), 500


@app.post("/api/rvbam-explorer/cache/clear")
@app.post("/api/rvbam_explorer/cache/clear")
@app.post("/js/api/rvbam-explorer/cache/clear")
@app.post("/js/api/rvbam_explorer/cache/clear")
def rvbam_explorer_clear_cache():
    rvbam_count = len(_RVBAM_CACHE)
    array_count = len(_RVBAM_ARRAY_CACHE)
    table_metadata_count = len(_DB_TABLE_EXISTS_CACHE)
    column_metadata_count = len(_DB_COLUMNS_CACHE)
    _RVBAM_CACHE.clear()
    _RVBAM_ARRAY_CACHE.clear()
    _DB_TABLE_EXISTS_CACHE.clear()
    _DB_COLUMNS_CACHE.clear()
    return jsonify({
        "ok": True,
        "cleared": {
            "rvbamExplorer": rvbam_count,
            "rvbamPayloadArrays": array_count,
            "dbTableMetadata": table_metadata_count,
            "dbColumnMetadata": column_metadata_count,
        },
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
    moca_explorer_count = len(_MOCA_EXPLORER_CACHE)
    group_hierarchy_count = len(_GROUP_HIERARCHY_CACHE)
    legacy_rv_count = len(_LEGACY_RV_CACHE)
    moranta26_rotation_count = len(_MORANTA26_ROTATION_CACHE)
    rvbam_count = len(_RVBAM_CACHE)
    rvbam_array_count = len(_RVBAM_ARRAY_CACHE)
    table_metadata_count = len(_DB_TABLE_EXISTS_CACHE)
    column_metadata_count = len(_DB_COLUMNS_CACHE)
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
    _MOCA_EXPLORER_CACHE.clear()
    _GROUP_HIERARCHY_CACHE.clear()
    _LEGACY_RV_CACHE.clear()
    _MORANTA26_ROTATION_CACHE.clear()
    _RVBAM_CACHE.clear()
    _RVBAM_ARRAY_CACHE.clear()
    _DB_TABLE_EXISTS_CACHE.clear()
    _DB_COLUMNS_CACHE.clear()
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
            "mocaExplorer": moca_explorer_count,
            "groupHierarchy": group_hierarchy_count,
            "legacyRadialVelocities": legacy_rv_count,
            "moranta26Rotation": moranta26_rotation_count,
            "rvbamExplorer": rvbam_count,
            "rvbamPayloadArrays": rvbam_array_count,
            "dbTableMetadata": table_metadata_count,
            "dbColumnMetadata": column_metadata_count,
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
