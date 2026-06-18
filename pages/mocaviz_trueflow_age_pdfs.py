"""Dash page for MOCA object and association age PDFs.

Copy this file into ``mocaviz/pages/``.  It is intentionally self-contained so
that it can read both the legacy per-row PDF tables and the newer compact blob
tables without depending on this repository at runtime.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import math
import os
from typing import Any
from urllib.parse import parse_qs, quote_plus
import zlib

import dash
from dash import Input, Output, State, dash_table, dcc, html
from dash.exceptions import PreventUpdate
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import bindparam, create_engine, text


def _np_trapezoid(y: Any, x: Any) -> Any:
    trapezoid = getattr(np, "trapezoid", None)
    if trapezoid is not None:
        return trapezoid(y, x)
    return np.trapz(y, x)


PAGE_PREFIX = "trueflow-agepdfs-v2"
AGE_AXIS_MIN_MYR = 1.0
AGE_AXIS_MAX_MYR = 14000.0

ONLINE_DB_DEFAULTS = {
    "host": "104.248.106.21",
    "username": "public",
    "password": "z@nUg_2h7_%?31y88",
    "database": "mocadb",
    "port": "3306",
}

LOCAL_DB_DEFAULTS = {
    "host": "",
    "username": "",
    "password": "",
    "database": "mocadb_private_tables",
    "port": "3306",
}

FIGURE_EXPORT_CONFIG = {
    "toImageButtonOptions": {
        "format": "png",
        "filename": "trueflow_age_pdfs",
        "height": 900,
        "width": 1300,
        "scale": 2,
    },
    "displaylogo": False,
}

CHECKLIST_LABEL_STYLE = {
    "display": "inline-block",
    "marginRight": "22px",
    "marginBottom": "6px",
    "whiteSpace": "nowrap",
}


class AgeCurve:
    """Small immutable-ish container.

    Dash imports page modules in a way that can trip a Python 3.8 dataclasses
    bug when ``from __future__ import annotations`` is active, because the page
    module may not be present in ``sys.modules`` while the dataclass decorator
    evaluates string annotations.  A plain class avoids that import-time crash.
    """

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


dash.register_page(
    __name__,
    path="/trueflow-age-pdfs",
    name="MOCA TrueFlow Age PDFs",
    order=21,
)


def _id(name: str) -> str:
    return f"{PAGE_PREFIX}-{name}"


def _url_params(search: str | None) -> dict[str, str]:
    if not search:
        return {}
    parsed = parse_qs(search[1:] if search.startswith("?") else search)
    return {key: values[-1] for key, values in parsed.items() if values}


def _env_first(names: tuple[str, ...], default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value not in (None, ""):
            return value
    return default


def _db_config_for_scope(scope: str, search: str | None) -> dict[str, str]:
    """Return DB connection settings.

    Object PDFs default to the local ATM connection and ``mocadb_private_tables``.
    Association PDFs default to the online/public MOCA connection.
    URL params can override either mode with ``host``, ``user``/``username``,
    ``pwd``/``password``, ``db``/``dbase``/``database``, and ``port``.
    """

    params = _url_params(search)
    if scope == "object":
        cfg = {
            "host": _env_first(("ATM_HOST",), LOCAL_DB_DEFAULTS["host"]),
            "username": _env_first(("ATM_USERNAME", "ATM_USER"), LOCAL_DB_DEFAULTS["username"]),
            "password": _env_first(("ATM_PASSWORD",), LOCAL_DB_DEFAULTS["password"]),
            "database": LOCAL_DB_DEFAULTS["database"],
            "port": _env_first(("ATM_PORT",), LOCAL_DB_DEFAULTS["port"]),
        }
    else:
        cfg = {
            "host": _env_first(("MOCA_HOST",), ONLINE_DB_DEFAULTS["host"]),
            "username": _env_first(("MOCA_USERNAME", "MOCA_USER"), ONLINE_DB_DEFAULTS["username"]),
            "password": _env_first(("MOCA_PASSWORD",), ONLINE_DB_DEFAULTS["password"]),
            # Association mode reads the online MOCA server.  Honor MOCA_DBNAME
            # because the newer blob tables may live in mocadb_private_tables on
            # the online server, while older public deployments may still point
            # to mocadb.
            "database": _env_first(("MOCA_DBNAME",), ONLINE_DB_DEFAULTS["database"]),
            "port": _env_first(("MOCA_PORT",), ONLINE_DB_DEFAULTS["port"]),
        }
    if params.get("host"):
        cfg["host"] = params["host"]
    if params.get("user") or params.get("username"):
        cfg["username"] = params.get("user") or params.get("username") or cfg["username"]
    if params.get("pwd") or params.get("password"):
        cfg["password"] = params.get("pwd") or params.get("password") or cfg["password"]
    if params.get("db") or params.get("dbase") or params.get("database"):
        cfg["database"] = params.get("db") or params.get("dbase") or params.get("database") or cfg["database"]
    if params.get("port"):
        cfg["port"] = params["port"]
    return cfg


def _engine_for_scope(scope: str, search: str | None):
    cfg = _db_config_for_scope(scope, search)
    if not cfg["host"] or not cfg["username"]:
        raise RuntimeError(
            "Missing DB credentials. Object mode needs ATM_HOST/ATM_USERNAME/ATM_PASSWORD; "
            "association mode needs MOCA_* or the public defaults."
        )
    url = (
        f"mysql+pymysql://{quote_plus(cfg['username'])}:{quote_plus(cfg['password'])}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    )
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _normalize_pdf(age_myr: np.ndarray, pdf: np.ndarray) -> np.ndarray:
    age_myr = np.asarray(age_myr, dtype=float)
    pdf = np.asarray(pdf, dtype=float)
    ok = np.isfinite(age_myr) & np.isfinite(pdf) & (age_myr > 0)
    out = np.zeros_like(pdf, dtype=float)
    if np.count_nonzero(ok) < 2:
        return out
    clipped = np.clip(pdf[ok], 0.0, None)
    norm = float(_np_trapezoid(clipped, age_myr[ok]))
    if not math.isfinite(norm) or norm <= 0:
        return out
    out[ok] = clipped / norm
    return out


def _cdf_from_pdf(age_myr: np.ndarray, pdf: np.ndarray) -> np.ndarray:
    age_myr = np.asarray(age_myr, dtype=float)
    pdf = _normalize_pdf(age_myr, pdf)
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


def _percentiles(age_myr: np.ndarray, pdf: np.ndarray) -> tuple[float, float, float] | None:
    age_myr = np.asarray(age_myr, dtype=float)
    pdf = _normalize_pdf(age_myr, pdf)
    ok = np.isfinite(age_myr) & np.isfinite(pdf) & (age_myr > 0)
    if np.count_nonzero(ok) < 2:
        return None
    age = age_myr[ok]
    cdf = _cdf_from_pdf(age, pdf[ok])
    if not np.any(np.diff(cdf) > 0):
        return None
    return tuple(float(np.interp(p, cdf, age)) for p in (0.16, 0.5, 0.84))


def _plain_log_age_ticks(xmin: float, xmax: float) -> tuple[list[float], list[str]]:
    """Readable tick labels for a log-scaled age axis."""

    if not (math.isfinite(xmin) and math.isfinite(xmax)) or xmin <= 0 or xmax <= xmin:
        return [], []
    tick_values: list[float] = []
    lo_decade = int(math.floor(math.log10(xmin))) - 1
    hi_decade = int(math.ceil(math.log10(xmax))) + 1
    for decade in range(lo_decade, hi_decade + 1):
        base = 10.0**decade
        for multiplier in range(1, 10):
            value = multiplier * base
            if xmin <= value <= xmax:
                tick_values.append(float(value))
    tick_values = sorted(set(tick_values))

    def fmt(value: float) -> str:
        if value >= 100:
            return f"{value:.0f}"
        if value >= 10:
            return f"{value:.0f}" if abs(value - round(value)) < 1e-8 else f"{value:.1f}".rstrip("0").rstrip(".")
        if value >= 1:
            return f"{value:.0f}" if abs(value - round(value)) < 1e-8 else f"{value:.2g}"
        return f"{value:.2g}"

    return tick_values, [fmt(value) for value in tick_values]


def _clamped_age_axis_range(xmin: Any, xmax: Any) -> list[float]:
    try:
        lower = float(xmin)
        upper = float(xmax)
    except (TypeError, ValueError):
        return [AGE_AXIS_MIN_MYR, AGE_AXIS_MAX_MYR]
    if not (math.isfinite(lower) and math.isfinite(upper)):
        return [AGE_AXIS_MIN_MYR, AGE_AXIS_MAX_MYR]
    lower = max(AGE_AXIS_MIN_MYR, lower)
    upper = min(AGE_AXIS_MAX_MYR, upper)
    if upper <= lower:
        return [AGE_AXIS_MIN_MYR, AGE_AXIS_MAX_MYR]
    return [lower, upper]


def _table_exists(engine, table_name: str) -> bool:
    query = text(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
        """
    )
    with engine.connect() as connection:
        return int(connection.execute(query, {"table_name": table_name}).scalar() or 0) > 0


def _columns(engine, table_name: str) -> set[str]:
    query = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = :table_name
        """
    )
    with engine.connect() as connection:
        return {str(row[0]) for row in connection.execute(query, {"table_name": table_name})}


def _qid(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return f"`{name}`"


def _fetch_age_rows(engine, scope: str, target: str | int) -> pd.DataFrame:
    age_table = "data_object_ages" if scope == "object" else "data_association_ages"
    target_col = "moca_oid" if scope == "object" else "moca_aid"
    if not _table_exists(engine, age_table):
        return pd.DataFrame()
    cols = _columns(engine, age_table)
    order_terms = []
    for col in ("adopted", "public_adopted", "adopt_asis", "public_adopt_asis"):
        if col in cols:
            order_terms.append(f"{_qid(col)} DESC")
    for col in ("modified_timestamp", "created_timestamp", "id"):
        if col in cols:
            order_terms.append(f"{_qid(col)} DESC")
    order_sql = ", ".join(order_terms) if order_terms else "1"
    query = text(
        f"""
        SELECT *
        FROM {_qid(age_table)}
        WHERE {_qid(target_col)} = :target
        ORDER BY {order_sql}
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"target": target}).mappings().all()
    return pd.DataFrame(rows)


def _fetch_association_options(search: str | None) -> list[dict[str, str]]:
    engine = _engine_for_scope("association", search)
    if not _table_exists(engine, "data_association_ages"):
        return []
    query = text(
        """
        SELECT DISTINCT moca_aid
        FROM data_association_ages
        WHERE moca_aid IS NOT NULL
        ORDER BY moca_aid
        """
    )
    with engine.connect() as connection:
        aids = [str(row[0]) for row in connection.execute(query)]
    return [{"label": aid, "value": aid} for aid in aids]


def _dtype(dtype: str | None, byte_order: str | None) -> np.dtype:
    dtype = dtype or "float32"
    byte_order = byte_order or "little"
    if dtype not in {"float32", "float64"}:
        dtype = "float32"
    prefix = "<" if byte_order != "big" else ">"
    return np.dtype(prefix + ("f4" if dtype == "float32" else "f8"))


def _decode_array(
    blob: bytes | memoryview,
    *,
    n_values: int,
    dtype: str | None,
    byte_order: str | None,
    compression: str | None,
    expected_sha256: str | None = None,
) -> np.ndarray:
    raw_blob = bytes(blob)
    if compression == "none":
        raw = raw_blob
    else:
        raw = zlib.decompress(raw_blob)
    if expected_sha256:
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected_sha256:
            raise ValueError("Blob SHA256 check failed")
    values = np.frombuffer(raw, dtype=_dtype(dtype, byte_order), count=int(n_values))
    return values.astype(float, copy=True)


def _log10_age_log_pdf_to_age_pdf(log10_age_grid: np.ndarray, log_pdf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
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
    log_norm = float(_np_trapezoid(log_age_pdf, log10_age_grid))
    if not math.isfinite(log_norm) or log_norm <= 0:
        return np.array([], dtype=float), np.array([], dtype=float)
    log_age_pdf /= log_norm
    age_myr = np.power(10.0, log10_age_grid)
    age_pdf = log_age_pdf / (age_myr * np.log(10.0))
    return age_myr, _normalize_pdf(age_myr, age_pdf)


def _blob_curve_sort_key(curve: AgeCurve) -> tuple[Any, ...]:
    meta = curve.metadata or {}
    return (
        meta.get("age_id"),
        meta.get("result_key"),
        meta.get("pdf_space"),
        meta.get("used_colors"),
    )


def _deduplicate_blob_curves(curves: list[AgeCurve], *, prefer_posteriors: bool) -> list[AgeCurve]:
    """Deduplicate likelihood/posterior alternatives for the same stored age product."""

    by_key: dict[tuple[Any, ...], AgeCurve] = {}
    for curve in curves:
        key = _blob_curve_sort_key(curve)
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


def _age_curve_from_log_pdf_row(
    data: dict[str, Any],
    age_meta: dict[Any, dict[str, Any]],
    *,
    log_pdf_blob_key: str = "log_pdf_blob",
    log_pdf_sha_key: str = "log_pdf_sha256",
    label_prefix: str | None = None,
) -> AgeCurve | None:
    try:
        grid = _decode_array(
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
        log_pdf = _decode_array(
            data[log_pdf_blob_key],
            n_values=int(data["grid_n_grid"]),
            dtype=data.get("dtype"),
            byte_order=data.get("byte_order"),
            compression=data.get("compression"),
            expected_sha256=data.get(log_pdf_sha_key),
        )
        age, pdf = _log10_age_log_pdf_to_age_pdf(log10_age, log_pdf)
    except Exception as exc:
        return AgeCurve(
            key=f"blob-decode-error-{data.get('id') or data.get('prior_id')}",
            label=f"Blob decode error id={data.get('id') or data.get('prior_id')}",
            source="MOCAFlows error",
            age_myr=np.array([], dtype=float),
            pdf_age=np.array([], dtype=float),
            metadata={"error": str(exc), **data},
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
    if data.get("prior_key"):
        extras.append(str(data["prior_key"]))
    label = f"{result_key} {role} (age_id={data['age_id']})"
    if label_prefix:
        label = f"{label_prefix} {label}"
    if row_method and row_method != result_key:
        label = f"{label}; {row_method}"
    if extras:
        label = f"{label}; {', '.join(extras)}"
    return AgeCurve(
        key=f"blob-{data.get('id') or 'prior'}-{data.get('age_id')}-{data.get('result_key')}",
        label=label,
        source="MOCAFlows",
        age_myr=age,
        pdf_age=pdf,
        metadata={**data, "scalar_row": meta},
    )


def _fetch_referenced_prior_curves(engine, blob_table: str, age_ids: list[int], age_meta: dict[Any, dict[str, Any]]) -> list[AgeCurve]:
    if not (_table_exists(engine, "calc_age_pdf_priors") and _table_exists(engine, "calc_age_pdf_grids")):
        return []
    blob_cols = _columns(engine, blob_table)
    prior_cols = _columns(engine, "calc_age_pdf_priors")
    if "prior_id" not in blob_cols:
        return []
    required_prior_cols = {"id", "prior_key", "grid_id", "pdf_space", "log_pdf_blob"}
    if not required_prior_cols.issubset(prior_cols):
        return []
    wanted_blob_cols = [
        "id",
        "age_id",
        "result_key",
        "used_colors",
        "n_contributors",
        "curve_role",
    ]
    wanted_prior_cols = [
        "id",
        "prior_key",
        "pdf_space",
        "dtype",
        "byte_order",
        "compression",
        "compression_level",
        "log_pdf_sha256",
        "log_pdf_blob",
        "source",
        "metadata_json",
    ]
    select_blob = ",\n               ".join(
        f"b.{_qid(col)} AS {_qid('parent_' + col if col == 'id' else col)}"
        for col in wanted_blob_cols
        if col in blob_cols
    )
    select_prior = ",\n               ".join(
        f"p.{_qid(col)} AS {_qid('prior_id' if col == 'id' else col)}"
        for col in wanted_prior_cols
        if col in prior_cols
    )
    query = text(
        f"""
        SELECT {select_blob},
               {select_prior},
               g.id AS grid_row_id,
               g.coordinate AS grid_coordinate,
               g.n_grid AS grid_n_grid,
               g.dtype AS grid_dtype,
               g.byte_order AS grid_byte_order,
               g.compression AS grid_compression,
               g.grid_sha256 AS grid_sha256,
               g.grid_blob AS grid_blob
        FROM {_qid(blob_table)} AS b
        JOIN calc_age_pdf_priors AS p
          ON p.id = b.prior_id
        JOIN calc_age_pdf_grids AS g
          ON g.id = p.grid_id
        WHERE b.age_id IN :age_ids
          AND b.prior_id IS NOT NULL
        ORDER BY b.age_id, b.result_key, p.id
        """
    ).bindparams(bindparam("age_ids", expanding=True))
    with engine.connect() as connection:
        rows = connection.execute(query, {"age_ids": age_ids}).mappings().all()
    curves: list[AgeCurve] = []
    for row in rows:
        data = dict(row)
        data["id"] = f"prior-{data.get('prior_id')}-parent-{data.get('parent_id')}"
        data["curve_role"] = "prior"
        curve = _age_curve_from_log_pdf_row(data, age_meta, label_prefix="Referenced")
        if curve is not None:
            curves.append(curve)
    return curves


def _fetch_blob_curves(engine, scope: str, age_rows: pd.DataFrame, *, load_posteriors: bool = False) -> list[AgeCurve]:
    if age_rows.empty or "id" not in age_rows:
        return []
    blob_table = "calc_object_age_pdf_blobs" if scope == "object" else "calc_association_age_pdf_blobs"
    if not (_table_exists(engine, blob_table) and _table_exists(engine, "calc_age_pdf_grids")):
        return []

    age_ids = [int(v) for v in age_rows["id"].dropna().astype(int).unique()]
    if not age_ids:
        return []

    blob_cols = _columns(engine, blob_table)
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
        f"b.{_qid(col)} AS {_qid(col)}" for col in wanted_blob_cols if col in blob_cols
    )
    role_values = ("posterior", "likelihood") if load_posteriors else ("likelihood",)
    query = text(
        f"""
        SELECT {select_blob},
               g.id AS grid_row_id,
               g.coordinate AS grid_coordinate,
               g.n_grid AS grid_n_grid,
               g.dtype AS grid_dtype,
               g.byte_order AS grid_byte_order,
               g.compression AS grid_compression,
               g.grid_sha256 AS grid_sha256,
               g.grid_blob AS grid_blob
        FROM {_qid(blob_table)} AS b
        JOIN calc_age_pdf_grids AS g
          ON g.id = b.grid_id
        WHERE b.age_id IN :age_ids
          AND b.curve_role IN :role_values
        ORDER BY b.age_id, b.result_key, b.curve_role, b.id
        """
    ).bindparams(bindparam("age_ids", expanding=True), bindparam("role_values", expanding=True))
    with engine.connect() as connection:
        rows = connection.execute(query, {"age_ids": age_ids, "role_values": role_values}).mappings().all()

    age_meta = age_rows.set_index("id", drop=False).to_dict(orient="index")
    curves: list[AgeCurve] = []
    for row in rows:
        data = dict(row)
        curve = _age_curve_from_log_pdf_row(data, age_meta)
        if curve is not None:
            curves.append(curve)
    return _deduplicate_blob_curves(curves, prefer_posteriors=load_posteriors)


def _fetch_legacy_pdf_curves(engine, scope: str, age_rows: pd.DataFrame) -> list[AgeCurve]:
    if age_rows.empty or "id" not in age_rows:
        return []
    pdf_table = "calc_object_age_pdfs" if scope == "object" else "calc_association_age_pdfs"
    if not _table_exists(engine, pdf_table):
        return []
    cols = _columns(engine, pdf_table)
    if not {"age_id", "age_myr", "log_probability_density"}.issubset(cols):
        return []
    age_ids = [int(v) for v in age_rows["id"].dropna().astype(int).unique()]
    if not age_ids:
        return []
    query = text(
        f"""
        SELECT age_id, age_myr, log_probability_density
        FROM {_qid(pdf_table)}
        WHERE age_id IN :age_ids
        ORDER BY age_id, age_myr
        """
    ).bindparams(bindparam("age_ids", expanding=True))
    with engine.connect() as connection:
        rows = connection.execute(query, {"age_ids": age_ids}).mappings().all()
    pdf_rows = pd.DataFrame(rows)
    if pdf_rows.empty:
        return []
    age_meta = age_rows.set_index("id", drop=False).to_dict(orient="index")
    curves: list[AgeCurve] = []
    for age_id, sub in pdf_rows.groupby("age_id", sort=False):
        sub = sub.dropna(subset=["age_myr", "log_probability_density"]).copy()
        sub = sub[sub["age_myr"] > 0]
        if sub.shape[0] < 2:
            continue
        sub.sort_values("age_myr", inplace=True)
        age = sub["age_myr"].to_numpy(dtype=float)
        log_pdf = sub["log_probability_density"].to_numpy(dtype=float)
        pdf = np.exp(log_pdf - float(np.nanmax(log_pdf)))
        pdf = _normalize_pdf(age, pdf)
        if not np.any(pdf > 0):
            continue
        meta = age_meta.get(age_id, {})
        method = meta.get("calculation_method") or meta.get("method") or meta.get("method_detailed") or "legacy age PDF"
        curves.append(
            AgeCurve(
                key=f"legacy-{age_id}",
                label=f"{method} legacy PDF (age_id={age_id})",
                source="Legacy",
                age_myr=age,
                pdf_age=pdf,
                metadata={"age_id": age_id, "scalar_row": meta},
            )
        )
    return curves


def _first_number(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        if name in row:
            value = _safe_float(row.get(name))
            if value is not None:
                return value
    return None


def _scalar_age_summary(row: dict[str, Any]) -> tuple[float, float, float, str] | None:
    center = _first_number(row, ("age_myr", "age", "age_value_myr", "best_age_myr"))
    note = "stored uncertainty"
    if center is None:
        log_age_yr = _first_number(row, ("log_age_yr", "log10_age_yr"))
        if log_age_yr is not None:
            center = 10.0**log_age_yr / 1e6
    if center is None or center <= 0:
        return None

    lo_unc = _first_number(
        row,
        (
            "age_myr_unc_neg",
            "age_myr_err_neg",
            "age_myr_minus",
            "age_unc_neg",
            "age_err_neg",
        ),
    )
    hi_unc = _first_number(
        row,
        (
            "age_myr_unc_pos",
            "age_myr_err_pos",
            "age_myr_plus",
            "age_unc_pos",
            "age_err_pos",
        ),
    )
    sym_unc = _first_number(row, ("age_myr_unc", "age_unc", "age_err", "uncertainty_myr"))
    if lo_unc is None and hi_unc is None and sym_unc is not None:
        lo_unc = sym_unc
        hi_unc = sym_unc

    log_center = math.log10(center * 1e6)
    log_lo = _first_number(row, ("log_age_unc_neg", "log_age_yr_unc_neg", "log10_age_yr_unc_neg"))
    log_hi = _first_number(row, ("log_age_unc_pos", "log_age_yr_unc_pos", "log10_age_yr_unc_pos"))
    log_sym = _first_number(row, ("log_age_unc", "log_age_yr_unc", "log10_age_yr_unc"))
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


def _gaussian_grid(age_rows: pd.DataFrame, stored_curves: list[AgeCurve]) -> np.ndarray:
    candidates: list[float] = []
    for curve in stored_curves:
        if curve.age_myr.size:
            good = curve.age_myr[np.isfinite(curve.age_myr) & (curve.age_myr > 0)]
            if good.size:
                candidates.extend([float(np.nanmin(good)), float(np.nanmax(good))])
    for row in age_rows.to_dict(orient="records"):
        summary = _scalar_age_summary(row)
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


def _stored_pdf_age_ids(stored_curves: list[AgeCurve]) -> set[int]:
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


def _is_hbm_mocaflows_curve(curve: AgeCurve) -> bool:
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


def _filter_mocaflows_hbm(curves: list[AgeCurve], *, scope: str, use_hbm: bool) -> list[AgeCurve]:
    if scope != "association":
        return curves
    out: list[AgeCurve] = []
    for curve in curves:
        if curve.source != "MOCAFlows":
            out.append(curve)
            continue
        if _is_hbm_mocaflows_curve(curve) == use_hbm:
            out.append(curve)
    return out


def _all_stored_pdf_age_ids(engine, scope: str, age_rows: pd.DataFrame) -> set[int]:
    """Age rows that have any stored PDF, independent of selected curve role."""

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
        if not _table_exists(engine, table_name):
            continue
        cols = _columns(engine, table_name)
        if "age_id" not in cols:
            continue
        query = text(
            f"""
            SELECT DISTINCT age_id
            FROM {_qid(table_name)}
            WHERE age_id IN :age_ids
            """
        ).bindparams(bindparam("age_ids", expanding=True))
        with engine.connect() as connection:
            out.update(int(row[0]) for row in connection.execute(query, {"age_ids": age_ids}))
    return out


def _scalar_gaussian_curves(
    age_rows: pd.DataFrame,
    stored_curves: list[AgeCurve],
    skip_age_ids: set[int] | None = None,
) -> list[AgeCurve]:
    if age_rows.empty:
        return []
    skip_age_ids = skip_age_ids or set()
    grid = _gaussian_grid(age_rows, stored_curves)
    curves: list[AgeCurve] = []
    for row in age_rows.to_dict(orient="records"):
        age_id_raw = row.get("id")
        try:
            age_id_int = int(age_id_raw) if age_id_raw is not None else None
        except (TypeError, ValueError):
            age_id_int = None
        if age_id_int is not None and age_id_int in skip_age_ids:
            continue
        summary = _scalar_age_summary(row)
        if not summary:
            continue
        center, lo_unc, hi_unc, note = summary
        sigma = np.where(grid < center, lo_unc, hi_unc)
        pdf = np.exp(-0.5 * ((grid - center) / sigma) ** 2)
        pdf = _normalize_pdf(grid, pdf)
        if not np.any(pdf > 0):
            continue
        method = row.get("calculation_method") or row.get("method") or row.get("method_detailed") or "scalar age"
        age_id = row.get("id", "unknown")
        curves.append(
            AgeCurve(
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
            )
        )
    return curves


def _load_curves(
    scope: str,
    target: str | int,
    search: str | None,
    *,
    load_blob_posteriors: bool = False,
) -> tuple[pd.DataFrame, list[AgeCurve]]:
    engine = _engine_for_scope(scope, search)
    age_rows = _fetch_age_rows(engine, scope, target)
    blob_curves = _fetch_blob_curves(engine, scope, age_rows, load_posteriors=load_blob_posteriors)
    legacy_curves = _fetch_legacy_pdf_curves(engine, scope, age_rows)
    stored_curves = blob_curves + legacy_curves
    skip_age_ids = _all_stored_pdf_age_ids(engine, scope, age_rows)
    skip_age_ids.update(_stored_pdf_age_ids(stored_curves))
    scalar_curves = _scalar_gaussian_curves(
        age_rows,
        stored_curves,
        skip_age_ids=skip_age_ids,
    )
    return age_rows, blob_curves + legacy_curves + scalar_curves


def _curve_summary_row(curve: AgeCurve) -> dict[str, Any]:
    pct = _percentiles(curve.age_myr, curve.pdf_age)
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


def _combine_curves(curves: list[AgeCurve]) -> AgeCurve | None:
    valid = [curve for curve in curves if curve.age_myr.size > 1 and np.any(curve.pdf_age > 0)]
    if not valid:
        return None
    all_age = np.concatenate([curve.age_myr for curve in valid])
    all_age = all_age[np.isfinite(all_age) & (all_age > 0)]
    if all_age.size < 2:
        return None
    log_grid = np.linspace(np.log10(float(np.nanmin(all_age))), np.log10(float(np.nanmax(all_age))), 1600)
    log_sum = np.zeros_like(log_grid)
    covered = np.ones_like(log_grid, dtype=bool)
    for curve in valid:
        age = curve.age_myr
        pdf = _normalize_pdf(age, curve.pdf_age)
        ok = np.isfinite(age) & np.isfinite(pdf) & (age > 0) & (pdf > 0)
        if np.count_nonzero(ok) < 2:
            continue
        log_age = np.log10(age[ok])
        log_pdf = np.log(np.clip(pdf[ok], 1e-300, None))
        order = np.argsort(log_age)
        interp = np.interp(log_grid, log_age[order], log_pdf[order], left=np.nan, right=np.nan)
        covered &= np.isfinite(interp)
        log_sum += np.nan_to_num(interp, nan=-1e9)
    if not np.any(covered):
        return None
    age_grid = np.power(10.0, log_grid)
    pdf = np.zeros_like(age_grid)
    pdf[covered] = np.exp(log_sum[covered] - float(np.nanmax(log_sum[covered])))
    pdf = _normalize_pdf(age_grid, pdf)
    if not np.any(pdf > 0):
        return None
    return AgeCurve(
        key="combined-visible",
        label="Product of visible curves",
        source="combined",
        age_myr=age_grid,
        pdf_age=pdf,
        metadata={"n_curves": len(valid)},
    )


layout = html.Div(
    [
        dcc.Location(id=_id("url")),
        html.H2("MOCA TrueFlow Age PDFs"),
        html.Div(
            [
                html.Div(
                    [
                        html.Label("Target type"),
                        dcc.RadioItems(
                            id=_id("target-type"),
                            options=[
                                {"label": "Object age PDFs (local MOCAdb)", "value": "object"},
                                {"label": "Association age PDFs (online MOCAdb)", "value": "association"},
                            ],
                            value="object",
                            inline=False,
                        ),
                    ],
                    style={"minWidth": "260px", "paddingRight": "18px"},
                ),
                html.Div(
                    [
                        html.Label("MOCA OID"),
                        dcc.Input(
                            id=_id("moca-oid-input"),
                            type="number",
                            debounce=True,
                            placeholder="e.g. 11266",
                            style={"width": "180px"},
                        ),
                    ],
                    style={"paddingRight": "18px"},
                ),
                html.Div(
                    [
                        html.Label("MOCA AID"),
                        dcc.Dropdown(
                            id=_id("moca-aid-dropdown"),
                            options=[],
                            placeholder="Select association",
                            style={"width": "260px"},
                        ),
                    ],
                    style={"paddingRight": "18px"},
                ),
                html.Button("Load PDFs", id=_id("load-button"), n_clicks=0),
            ],
            style={"display": "flex", "gap": "8px", "alignItems": "end", "flexWrap": "wrap"},
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Label("Data products"),
                        dcc.Checklist(
                            id=_id("source-checklist"),
                            options=[
                                {"label": "MOCAFlows products", "value": "MOCAFlows"},
                                {"label": "other age tools", "value": "Legacy"},
                                {"label": "Scalar rows as asymmetric Gaussians", "value": "Scalar Gaussian"},
                            ],
                            value=["MOCAFlows", "Legacy", "Scalar Gaussian"],
                            inline=True,
                            labelStyle=CHECKLIST_LABEL_STYLE,
                        ),
                    ],
                    style={"paddingTop": "12px"},
                ),
                html.Div(
                    [
                        html.Label("MOCAFlows options"),
                        dcc.Checklist(
                            id=_id("blob-role-checklist"),
                            options=[
                                {"label": "use posteriors when possible", "value": "posteriors"},
                                {
                                    "label": "Use Hierarchical Bayesian Models with outlier rejection",
                                    "value": "hbm",
                                },
                            ],
                            value=["hbm"],
                            inline=True,
                            labelStyle=CHECKLIST_LABEL_STYLE,
                        ),
                    ],
                    style={"paddingTop": "10px"},
                ),
                html.Div(
                    [
                        html.Label("Display"),
                        dcc.Checklist(
                            id=_id("display-options"),
                            options=[
                                {"label": "log x-axis", "value": "log_x"},
                                {"label": "log y-axis", "value": "log_y"},
                                {"label": "CDF", "value": "cdf"},
                                {"label": "show product of visible curves", "value": "combine"},
                            ],
                            value=["log_x"],
                            inline=True,
                            labelStyle=CHECKLIST_LABEL_STYLE,
                        ),
                    ],
                    style={"paddingTop": "10px"},
                ),
            ]
        ),
        html.Div(id=_id("status"), style={"padding": "10px 0", "fontWeight": "600"}),
        dcc.Graph(id=_id("graph"), config=FIGURE_EXPORT_CONFIG, style={"height": "760px"}),
        dash_table.DataTable(
            id=_id("curve-table"),
            columns=[
                {"name": "curve", "id": "curve"},
                {"name": "source", "id": "source"},
                {"name": "age", "id": "age"},
                {"name": "calculation_method", "id": "calculation_method"},
                {"name": "moca_pid", "id": "moca_pid"},
                {"name": "adopted", "id": "adopted"},
                {"name": "public_adopted", "id": "public_adopted"},
                {"name": "comments", "id": "comments"},
            ],
            data=[],
            page_size=12,
            style_table={"overflowX": "auto"},
            style_cell={
                "fontFamily": "monospace",
                "fontSize": 12,
                "textAlign": "left",
                "maxWidth": "360px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
            },
            style_header={"fontWeight": "700"},
        ),
    ],
    style={"padding": "18px 28px"},
)


@dash.callback(
    Output(_id("moca-oid-input"), "value"),
    Output(_id("moca-aid-dropdown"), "value"),
    Input(_id("url"), "search"),
)
def _apply_url_defaults(search: str | None):
    params = _url_params(search)
    oid_value = params.get("moca_oid") or params.get("oid")
    aid_value = params.get("moca_aid") or params.get("aid")
    try:
        oid_value = int(oid_value) if oid_value not in (None, "") else None
    except ValueError:
        oid_value = None
    return oid_value, aid_value


@dash.callback(
    Output(_id("target-type"), "value"),
    Input(_id("url"), "search"),
    Input(_id("moca-aid-dropdown"), "value"),
    Input(_id("moca-oid-input"), "n_submit"),
    State(_id("moca-oid-input"), "value"),
    State(_id("target-type"), "value"),
)
def _auto_select_target_type(
    search: str | None,
    moca_aid: str | None,
    _oid_submit_count: int | None,
    moca_oid: int | None,
    current_scope: str | None,
):
    ctx = dash.callback_context
    triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""
    if triggered == f"{_id('moca-aid-dropdown')}.value" and moca_aid:
        return "association"
    if triggered == f"{_id('moca-oid-input')}.n_submit" and moca_oid not in (None, ""):
        return "object"

    params = _url_params(search)
    scope = params.get("target") or params.get("scope") or params.get("mode")
    if scope in {"object", "association"}:
        return scope
    if params.get("moca_aid") or params.get("aid"):
        return "association"
    if params.get("moca_oid") or params.get("oid"):
        return "object"
    return current_scope or "object"


@dash.callback(
    Output(_id("moca-aid-dropdown"), "options"),
    Input(_id("url"), "search"),
)
def _populate_associations(search: str | None):
    try:
        return _fetch_association_options(search)
    except Exception:
        return []


@dash.callback(
    Output(_id("graph"), "figure"),
    Output(_id("graph"), "config"),
    Output(_id("status"), "children"),
    Output(_id("curve-table"), "data"),
    Input(_id("load-button"), "n_clicks"),
    Input(_id("target-type"), "value"),
    Input(_id("source-checklist"), "value"),
    Input(_id("blob-role-checklist"), "value"),
    Input(_id("display-options"), "value"),
    State(_id("moca-oid-input"), "value"),
    State(_id("moca-aid-dropdown"), "value"),
    State(_id("url"), "search"),
)
def _plot_age_pdfs(
    _n_clicks: int,
    scope: str,
    selected_sources: list[str] | None,
    blob_role_options: list[str] | None,
    display_options: list[str] | None,
    moca_oid: int | None,
    moca_aid: str | None,
    search: str | None,
):
    if scope not in {"object", "association"}:
        scope = "object"
    target = moca_oid if scope == "object" else moca_aid
    config = FIGURE_EXPORT_CONFIG.copy()
    config["toImageButtonOptions"] = config.get("toImageButtonOptions", {}).copy()
    config["toImageButtonOptions"]["filename"] = (
        f"trueflow_age_pdfs_{scope}_{target or 'none'}_{datetime.now().strftime('%Y%m%d')}"
    )

    if target in (None, ""):
        fig = go.Figure()
        fig.update_layout(
            title="Choose a MOCA OID or MOCA AID, then click Load PDFs.",
            margin=dict(l=70, r=30, t=55, b=65),
            xaxis_title="Age (Myr)",
            yaxis_title="Probability density",
        )
        fig.update_xaxes(range=[AGE_AXIS_MIN_MYR, AGE_AXIS_MAX_MYR])
        return fig, config, "", []

    selected_sources = selected_sources or []
    blob_role_options = blob_role_options or []
    display_options = display_options or []
    try:
        age_rows, curves = _load_curves(
            scope,
            target,
            search,
            load_blob_posteriors=("posteriors" in blob_role_options),
        )
    except Exception as exc:
        fig = go.Figure()
        fig.update_layout(
            title=f"Failed to load {scope} age PDFs for {target}: {exc}",
            margin=dict(l=70, r=30, t=70, b=65),
        )
        fig.update_xaxes(range=[AGE_AXIS_MIN_MYR, AGE_AXIS_MAX_MYR])
        return fig, config, f"Load failed: {exc}", []

    curves = [curve for curve in curves if curve.source in selected_sources]
    curves = _filter_mocaflows_hbm(curves, scope=scope, use_hbm=("hbm" in blob_role_options))
    curves = [curve for curve in curves if curve.age_myr.size > 1 and np.any(curve.pdf_age > 0)]

    show_cdf = "cdf" in display_options
    use_logx = "log_x" in display_options
    use_logy = "log_y" in display_options and not show_cdf
    show_combine = "combine" in display_options

    fig = go.Figure()
    source_counts: dict[str, int] = {}
    for curve in curves:
        source_counts[curve.source] = source_counts.get(curve.source, 0) + 1
    table_rows = [_curve_summary_row(curve) for curve in curves]
    if show_combine:
        combined = _combine_curves(curves)
        if combined is not None:
            curves = curves + [combined]
            table_rows.insert(0, _curve_summary_row(combined))

    for curve in curves:
        if curve.source == "combined":
            line = dict(width=4.0, color="black", dash="solid")
            opacity = 0.9
        elif curve.source == "Scalar Gaussian":
            line = dict(width=1.7, dash="dash")
            opacity = 0.55
        elif curve.source == "MOCAFlows":
            line = dict(width=2.4)
            opacity = 0.78
        else:
            line = dict(width=2.1, dash="dot")
            opacity = 0.70
        y_values = _cdf_from_pdf(curve.age_myr, curve.pdf_age) if show_cdf else curve.pdf_age
        fig.add_trace(
            go.Scatter(
                x=curve.age_myr,
                y=y_values,
                mode="lines",
                name=curve.label,
                line=line,
                opacity=opacity,
                hovertemplate=(
                    "Age: %{x:.4g} Myr<br>"
                    + ("CDF" if show_cdf else "PDF")
                    + ": %{y:.4g}<extra>"
                    + curve.label
                    + "</extra>"
                ),
            )
        )

    title = f"{scope.capitalize()} {target}: age PDFs"
    db_cfg = _db_config_for_scope(scope, search)
    source_text = ", ".join(f"{key}: {value}" for key, value in sorted(source_counts.items()))
    if not source_text:
        source_text = "none"
    status = (
        f"Loaded {len(age_rows)} scalar age rows and {len(curves)} displayed curves "
        f"from {db_cfg['host']}/{db_cfg['database']} ({source_text})."
    )
    if not curves:
        title = f"No displayable age PDFs for {scope} {target}"

    fig.update_layout(
        title=title,
        margin=dict(l=72, r=30, t=65, b=70),
        xaxis_title="Age (Myr)",
        yaxis_title="CDF" if show_cdf else "Probability density",
        legend_title_text="Age product",
        plot_bgcolor="white",
    )
    fig.update_xaxes(
        type="log" if use_logx else "linear",
        showline=True,
        linewidth=2,
        linecolor="black",
        mirror=True,
        ticks="outside",
        showgrid=True,
        gridcolor="rgba(0,0,0,0.12)",
    )
    fig.update_yaxes(
        type="linear" if show_cdf else ("log" if use_logy else "linear"),
        showline=True,
        linewidth=2,
        linecolor="black",
        mirror=True,
        ticks="outside",
        showgrid=True,
        gridcolor="rgba(0,0,0,0.12)",
    )
    if show_cdf:
        fig.update_yaxes(range=[0, 1])
    elif not use_logy:
        fig.update_yaxes(rangemode="tozero")

    default_xrange = [AGE_AXIS_MIN_MYR, AGE_AXIS_MAX_MYR]
    if use_logx:
        tick_values, tick_text = _plain_log_age_ticks(default_xrange[0], default_xrange[1])
        fig.update_xaxes(
            range=[math.log10(default_xrange[0]), math.log10(default_xrange[1])],
            tickmode="array",
            tickvals=tick_values,
            ticktext=tick_text,
        )
    else:
        fig.update_xaxes(range=default_xrange)

    if curves:
        all_age = np.concatenate([curve.age_myr for curve in curves if curve.age_myr.size])
        all_pdf = np.concatenate([curve.pdf_age for curve in curves if curve.pdf_age.size])
        ok = np.isfinite(all_age) & np.isfinite(all_pdf) & (all_age > 0) & (all_pdf > 0)
        if np.any(ok):
            xmin = float(np.nanmin(all_age[ok]))
            xmax = float(np.nanmax(all_age[ok]))
            if xmax > xmin:
                if use_logx:
                    pad = 0.06 * (math.log10(xmax) - math.log10(xmin))
                    plot_xmin = 10.0 ** (math.log10(xmin) - pad)
                    plot_xmax = 10.0 ** (math.log10(xmax) + pad)
                    plot_xmin, plot_xmax = _clamped_age_axis_range(plot_xmin, plot_xmax)
                    tick_values, tick_text = _plain_log_age_ticks(plot_xmin, plot_xmax)
                    fig.update_xaxes(
                        range=[math.log10(plot_xmin), math.log10(plot_xmax)],
                        tickmode="array",
                        tickvals=tick_values,
                        ticktext=tick_text,
                    )
                else:
                    pad = 0.06 * (xmax - xmin)
                    fig.update_xaxes(range=_clamped_age_axis_range(xmin - pad, xmax + pad))

    return fig, config, status, table_rows
