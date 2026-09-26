#!/usr/bin/env python3
"""Private, stateless reduction comparison for MoCaViz.

Comparison logic ported from moca-shared-tools spectrum_compare (215df27).
Requests use caller credentials, one read-only transaction, and no disk writes.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import re
import statistics
import ssl
import sys
from contextlib import contextmanager
from decimal import Decimal

# Prevent lazy dependency imports from writing bytecode during requests.
sys.dont_write_bytecode = True
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import pymysql
from pymysql.cursors import DictCursor
from flask import Blueprint, Response, g, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

review = Blueprint("spectrum_compare", __name__)
PRIVATE_DB = "mocadb_private_tables"


class AccessError(Exception):
    """Safe client-facing error, without supplied values or driver messages."""


def credentials() -> dict[str, str]:
    """Headers populated from the page URL; no saved credentials or fallback."""
    if any(key in request.args for key in (
        "user", "username", "pwd", "password", "dbase", "db", "database", "host", "port"
    )):
        raise AccessError("Use the page to supply credentials; API URLs must not contain them.")
    user = request.headers.get("X-MOCA-User", "")
    password = request.headers.get("X-MOCA-Password", "")
    database = request.headers.get("X-MOCA-Database", "")
    if user not in {"collaborators", "management"} or not password:
        raise AccessError("Collaborator or management username and password are required.")
    if database != PRIVATE_DB:
        raise AccessError("This reviewer requires the private MOCAdb database.")
    return {"user": user, "password": password}


@contextmanager
def authenticated_reader(auth: dict[str, str]):
    # On the MOCAdb host, an explicitly configured Unix socket avoids sending
    # credentials over the network at all. It is deployment configuration,
    # never a request parameter. TCP always requires verified TLS.
    socket_path = os.environ.get("MOCAVIZ_COMPARE_UNIX_SOCKET", "")
    if socket_path and not Path(socket_path).is_absolute():
        raise RuntimeError("The configured database socket must be an absolute path")
    connection = pymysql.connect(
        host="mocadb.ca", port=3306, database=PRIVATE_DB,
        user=auth["user"], password=auth["password"],
        charset="utf8mb4", cursorclass=DictCursor, autocommit=False,
        unix_socket=socket_path or None,
        ssl=None if socket_path else ssl.create_default_context(),
        connect_timeout=15, read_timeout=75, write_timeout=15,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute("SELECT CURRENT_USER() AS authenticated_user FROM DUAL")
            row = cursor.fetchone() or {}
            if str(row.get("authenticated_user", "")).split("@", 1)[0] != auth["user"]:
                raise AccessError("Database authentication did not match the supplied account.")
            g.spectrum_compare_cursor = cursor
            try:
                yield
            finally:
                g.pop("spectrum_compare_cursor", None)
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


@review.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "worker-src 'self' blob:; img-src 'self' data:; "
        "frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
    )
    return response


@review.get("/spectrum-compare")
def page():
    # This empty shell contains no private data. Every API call authenticates.
    return send_from_directory(Path(__file__).parent / "templates", "spectrum_compare.html")


@review.get("/api/spectrum-compare/<operation>")
def api(operation):
    try:
        auth = credentials()
        if operation not in {"packages", "spectra", "spectrum"}:
            return jsonify(error="Unknown comparison operation."), 404
        package_id = None
        specid = None
        max_points = DEFAULT_MAX_POINTS
        if operation == "spectra":
            package_id = package_selection(request.args.get("package_id", "all"))
            if package_id is not None and package_id not in MANAGED_PACKAGES:
                raise ValueError()
        if operation == "spectrum":
            specid = int(request.args.get("moca_specid", ""))
            if not 0 < specid <= 2**53 - 1:
                raise ValueError()
            max_points = min(30_000, max(1_000, int(request.args.get("max_points", DEFAULT_MAX_POINTS))))
        with authenticated_reader(auth):
            if operation == "packages":
                result = package_rows()
            elif operation == "spectra":
                result = spectrum_index(package_id)
            else:
                result = spectrum_payload(specid, max_points=max_points)
        body, encoding = encoded_json(result, request.headers.get("Accept-Encoding", ""))
        response = Response(body, mimetype="application/json")
        response.vary.add("Accept-Encoding")
        if encoding:
            response.headers["Content-Encoding"] = encoding
        return response
    except AccessError as error:
        return jsonify(error=str(error)), 403
    except (ValueError, KeyError, OverflowError):
        return jsonify(error="Invalid selection, or the active managed spectrum is unavailable."), 400
    except HTTPException as error:
        return jsonify(error=error.name), error.code
    except pymysql.MySQLError as error:
        if error.args and error.args[0] in {1044, 1045, 1142}:
            return jsonify(error="Credentials were rejected or lack private-data access."), 403
        return jsonify(error="The database is unavailable or busy. Please try again."), 503
    except Exception:
        # Never log/return raw DB exceptions, SQL, credentials or tracebacks.
        return jsonify(error="The comparison could not be loaded. Please try again."), 500


# Packages shown as current managed reductions.  The public archive IGRINS-2
# PLP 3.2 products in package 110 and ESO-downloaded X-shooter 1D products in
# package 115 are intentionally absent so they remain eligible as legacy
# comparators for managed packages 113 and 114, respectively.
MANAGED_PACKAGES = (106, 107, 108, 109, 113, 114)
IGRINS_ARCHIVE_LEGACY_PACKAGE = 110
ESO_ARCHIVE_LEGACY_PACKAGE = 115
EXCLUDED_LEGACY_PACKAGES = MANAGED_PACKAGES
DEFAULT_MAX_POINTS = 12_000
MAX_LEGACY_OVERLAYS = 3
GZIP_MIN_BYTES = 1_024
MAX_NORMALIZATION_WINDOWS = 256
NORMALIZATION_SAMPLES_PER_WINDOW = 2
QualitySamples = tuple[
    list[tuple[float, float]],
    list[tuple[float, float]],
    list[tuple[float, float]],
]


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError("Unsupported database value")


def encoded_json(payload: Any, accept_encoding: str = "") -> tuple[bytes, str | None]:
    """Serialize an API response and gzip larger payloads when supported."""

    body = json.dumps(
        payload,
        allow_nan=False,
        default=_json_default,
        separators=(",", ":"),
    ).encode("utf-8")
    if "gzip" in accept_encoding.lower() and len(body) >= GZIP_MIN_BYTES:
        return gzip.compress(body, compresslevel=5), "gzip"
    return body, None


def readonly_rows(sql: str, parameters: Iterable[Any] = ()) -> list[dict[str, Any]]:
    """Only the authenticated request transaction may execute comparison SQL."""
    cursor = g.spectrum_compare_cursor
    cursor.execute(sql, tuple(parameters))
    return list(cursor.fetchall())


def observing_night(alias: str) -> str:
    return (
        f"COALESCE(NULLIF({alias}.data_collection_date,''),"
        f"DATE_FORMAT(DATE_ADD('1858-11-17', INTERVAL FLOOR({alias}.epoch_mjd) DAY),"
        "'%%Y-%%m-%%d'))"
    )


def object_name_sql(spectrum_alias: str, object_alias: str) -> str:
    """Return a non-empty, reviewer-friendly object label expression."""

    return (
        f"COALESCE(NULLIF({object_alias}.designation,''),"
        f"NULLIF({spectrum_alias}.object_designation,''),"
        f"NULLIF({spectrum_alias}.telescope_object_name,''),"
        f"NULLIF({spectrum_alias}.spectrum_name,''),"
        f"CONCAT('spectrum ',{spectrum_alias}.moca_specid))"
    )


def mode_compatible_sql(current: str, legacy: str) -> str:
    """Match exact labels or a compatible slit/wavelength signature."""

    exact_label = (
        f"({current}.instrument_mode_name IS NOT NULL AND "
        f"LOWER(TRIM({legacy}.instrument_mode_name))="
        f"LOWER(TRIM({current}.instrument_mode_name)))"
    )
    physical_signature = (
        f"({current}.slit_width_as IS NOT NULL AND {legacy}.slit_width_as IS NOT NULL "
        f"AND ABS({legacy}.slit_width_as-{current}.slit_width_as) <= "
        f"GREATEST(0.03,0.05*GREATEST({legacy}.slit_width_as,{current}.slit_width_as)) "
        f"AND {current}.min_wavelength_angstrom IS NOT NULL "
        f"AND {current}.max_wavelength_angstrom IS NOT NULL "
        f"AND {legacy}.min_wavelength_angstrom IS NOT NULL "
        f"AND {legacy}.max_wavelength_angstrom IS NOT NULL "
        f"AND GREATEST(0,LEAST({legacy}.max_wavelength_angstrom,"
        f"{current}.max_wavelength_angstrom)-"
        f"GREATEST({legacy}.min_wavelength_angstrom,"
        f"{current}.min_wavelength_angstrom)) >= "
        f"0.5*LEAST({legacy}.max_wavelength_angstrom-"
        f"{legacy}.min_wavelength_angstrom,"
        f"{current}.max_wavelength_angstrom-"
        f"{current}.min_wavelength_angstrom))"
    )
    return f"({exact_label} OR {physical_signature})"


def _normalized_mode_label(value: Any) -> str | None:
    label = str(value or "").strip().casefold()
    return label or None


def rows_mode_compatible(current: dict[str, Any], legacy: dict[str, Any]) -> bool:
    current_label = _normalized_mode_label(current.get("instrument_mode_name"))
    legacy_label = _normalized_mode_label(legacy.get("instrument_mode_name"))
    if current_label is not None and legacy_label == current_label:
        return True
    keys = ("slit_width_as", "min_wavelength_angstrom", "max_wavelength_angstrom")
    if any(current.get(key) is None or legacy.get(key) is None for key in keys):
        return False
    current_slit = float(current["slit_width_as"])
    legacy_slit = float(legacy["slit_width_as"])
    slit_tolerance = max(0.03, 0.05 * max(current_slit, legacy_slit))
    if abs(current_slit - legacy_slit) > slit_tolerance:
        return False
    current_min = float(current["min_wavelength_angstrom"])
    current_max = float(current["max_wavelength_angstrom"])
    legacy_min = float(legacy["min_wavelength_angstrom"])
    legacy_max = float(legacy["max_wavelength_angstrom"])
    overlap = max(0.0, min(current_max, legacy_max) - max(current_min, legacy_min))
    shorter_span = min(current_max - current_min, legacy_max - legacy_min)
    return shorter_span > 0 and overlap >= 0.5 * shorter_span


def package_rows() -> list[dict[str, Any]]:
    placeholders = ",".join(["%s"] * len(MANAGED_PACKAGES))
    rows = readonly_rows(
        f"""
        SELECT p.moca_specpackid,p.moca_instid,p.instrument_name,p.package_name,
               COUNT(s.moca_specid) AS active_spectra
        FROM moca_spectra_packages AS p
        LEFT JOIN moca_spectra AS s
          ON s.moca_specpackid=p.moca_specpackid AND s.ignored=0
        WHERE p.moca_specpackid IN ({placeholders})
        GROUP BY p.moca_specpackid,p.moca_instid,p.instrument_name,p.package_name
        ORDER BY p.moca_specpackid
        """,
        MANAGED_PACKAGES,
    )
    for row in rows:
        instrument = row.get("instrument_name") or row.get("moca_instid") or "unknown"
        row["description"] = (
            f"{instrument} — package {row['moca_specpackid']} — "
            f"{int(row['active_spectra'] or 0):,} spectra"
        )
    total = sum(int(row.get("active_spectra") or 0) for row in rows)
    return [
        {
            "moca_specpackid": "all",
            "moca_instid": None,
            "instrument_name": "All Cameras",
            "package_name": None,
            "active_spectra": total,
            "description": f"All Cameras — {total:,} spectra",
        },
        *rows,
    ]


def spectrum_index(package_id: int | None) -> list[dict[str, Any]]:
    if package_id is not None and package_id not in MANAGED_PACKAGES:
        raise ValueError(f"package {package_id} is not managed by this viewer")
    if package_id is None:
        package_clause = "s.moca_specpackid IN (" + ",".join(
            ["%s"] * len(MANAGED_PACKAGES)
        ) + ")"
        package_parameters: tuple[Any, ...] = MANAGED_PACKAGES
    else:
        package_clause = "s.moca_specpackid=%s"
        package_parameters = (package_id,)
    night_current = observing_night("s")
    night_legacy = observing_night("legacy")
    excluded = ",".join(["%s"] * len(EXCLUDED_LEGACY_PACKAGES))
    rows = readonly_rows(
        f"""
        SELECT s.moca_specid,s.moca_specpackid,s.moca_oid,s.moca_instid,
               s.spectrum_name,
               {object_name_sql('s', 'object_row')} AS object_name,
               object_row.ra AS object_ra,object_row.`dec` AS object_dec,
               s.instrument_mode_name,{night_current} AS observing_night,
               s.epoch_mjd,s.nwavelengths,s.min_wavelength_angstrom,
               s.max_wavelength_angstrom,s.slit_width_as,s.seeing,
               s.data_reduction_pipeline_version,
               s.modified_timestamp AS modification_date,
               (
                 SELECT COUNT(*)
                 FROM moca_spectra AS legacy
                 WHERE legacy.ignored=0
                   AND (legacy.moca_specpackid IS NULL OR
                        legacy.moca_specpackid NOT IN ({excluded}))
                   AND s.moca_oid IS NOT NULL
                   AND legacy.moca_oid=s.moca_oid
                   AND legacy.moca_instid <=> s.moca_instid
                   AND {mode_compatible_sql('s', 'legacy')}
                   AND {night_legacy} <=> {night_current}
               ) AS legacy_count
        FROM moca_spectra AS s
        LEFT JOIN moca_objects AS object_row ON object_row.moca_oid=s.moca_oid
        WHERE {package_clause} AND s.ignored=0
        ORDER BY observing_night,s.moca_oid,s.moca_specid
        """,
        (*EXCLUDED_LEGACY_PACKAGES, *package_parameters),
    )
    return rows


def package_selection(value: str) -> int | None:
    """Translate the package dropdown value; ``None`` means every camera."""

    normalized = value.strip().lower()
    if normalized == "all":
        return None
    return int(normalized)


_EMPTY_WARNING_VALUES = {"", "-", "0", "FALSE", "N/A", "NONE", "NULL", "PASS"}
_WARNING_FIELD_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:_WARNING_CODES|_WARNING_FLAGS|_WARNING|WARN))\s*=\s*([^;\r\n]*)",
    re.IGNORECASE,
)
_QA_STATE_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:_QA|QA))\s*=\s*([^;\s,\r\n]+)",
    re.IGNORECASE,
)
_WARNING_STATE_RE = re.compile(
    r"WARN|FAIL|REVIEW|REJECT|DEGRADED|PARTIAL|UNMEASURABLE",
    re.IGNORECASE,
)
_FITS_WARNING_CODES_RE = re.compile(
    r"(?m)^\s*QAWARN\s*=\s*'([^']*)'",
    re.IGNORECASE,
)
_FITS_QA_STATE_RE = re.compile(
    r"(?m)^\s*([A-Z][A-Z0-9_]{1,15}QA)\s*=\s*(?:'([^']*)'|([^/\r\n]*))",
    re.IGNORECASE,
)
_COMPACT_QA_KEY_ALIASES = {
    "SEEQA": "SEEINGQA",
}


def spectrum_qa_warnings(comments: Any, fits_header: Any) -> list[str]:
    """Extract concise warning labels from persisted spectrum QA metadata."""

    warnings: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = re.sub(r"\s+", " ", str(value or "")).strip(" ,;\t\r\n'\"")
        if not text or text.upper() in _EMPTY_WARNING_VALUES:
            return
        if "=" in text:
            key, field_value = text.split("=", 1)
            compact_key = key.upper().replace("_", "")
            compact_key = _COMPACT_QA_KEY_ALIASES.get(compact_key, compact_key)
            identity = f"{compact_key}={field_value.strip().upper()}"
        else:
            identity = text.casefold()
        if identity not in seen:
            seen.add(identity)
            warnings.append(text)

    comment_text = str(comments or "")
    for match in _WARNING_FIELD_RE.finditer(comment_text):
        key = match.group(1).upper()
        value = match.group(2).strip()
        if key.endswith(("_WARNING_CODES", "_WARNING_FLAGS")):
            for item in value.split(","):
                add(item)
        elif value.upper() not in _EMPTY_WARNING_VALUES:
            add(f"{key}={value}")

    for match in _QA_STATE_RE.finditer(comment_text):
        key = match.group(1).upper()
        value = match.group(2).strip(" '\"")
        if _WARNING_STATE_RE.search(value):
            add(f"{key}={value}")

    for segment in re.split(r"[;\r\n]+", comment_text):
        text = segment.strip()
        human_warning = re.match(
            r"^(?:QA\s+WARNING\s+|QA\s+|WARNING:\s*)(.+)$", text, re.IGNORECASE
        )
        if human_warning:
            add(human_warning.group(1))

    header_text = str(fits_header or "")
    for match in _FITS_WARNING_CODES_RE.finditer(header_text):
        for item in match.group(1).split(","):
            add(item)
    for match in _FITS_QA_STATE_RE.finditer(header_text):
        key = match.group(1).upper()
        value = (match.group(2) or match.group(3) or "").strip(" '\"")
        if _WARNING_STATE_RE.search(value):
            add(f"{key}={value}")

    return warnings


def _spectrum_metadata(specid: int) -> dict[str, Any]:
    placeholders = ",".join(["%s"] * len(MANAGED_PACKAGES))
    rows = readonly_rows(
        f"""
        SELECT s.moca_specid,s.moca_specpackid,s.moca_oid,s.moca_instid,
               s.spectrum_name,
               {object_name_sql('s', 'object_row')} AS object_name,
               object_row.ra AS object_ra,object_row.`dec` AS object_dec,
               s.instrument_mode_name,
               {observing_night('s')} AS observing_night,s.epoch_mjd,
               s.flux_units,s.slit_width_as,s.min_wavelength_angstrom,
               s.max_wavelength_angstrom,s.median_spectral_resolving_power,
               s.pix_per_res_element,s.seeing,
               s.wavelength_solution_reference,
               s.wavelength_solution_error_kms,s.slit_filling_rv_correction,
               s.slit_filling_rv_error_kms,
               s.data_reduction_pipeline_version,
               s.modified_timestamp AS modification_date,
               s.comments,s.fits_header
        FROM moca_spectra AS s
        LEFT JOIN moca_objects AS object_row ON object_row.moca_oid=s.moca_oid
        WHERE s.moca_specid=%s AND s.ignored=0
          AND s.moca_specpackid IN ({placeholders})
        """,
        (specid, *MANAGED_PACKAGES),
    )
    if len(rows) != 1:
        raise ValueError(f"active managed spectrum {specid} does not exist")
    metadata = dict(rows[0])
    metadata["qa_warnings"] = spectrum_qa_warnings(
        metadata.pop("comments", None), metadata.pop("fits_header", None)
    )
    return metadata


def _legacy_metadata(current: dict[str, Any]) -> list[dict[str, Any]]:
    if current.get("moca_oid") is None:
        return []
    excluded = ",".join(["%s"] * len(EXCLUDED_LEGACY_PACKAGES))
    rows = readonly_rows(
        f"""
        SELECT legacy.moca_specid,legacy.moca_specpackid,legacy.moca_oid,
               legacy.moca_instid,legacy.spectrum_name,
               {object_name_sql('legacy', 'object_row')} AS object_name,
               legacy.instrument_mode_name,
               {observing_night('legacy')} AS observing_night,legacy.epoch_mjd,
               legacy.flux_units,legacy.slit_width_as,
               legacy.min_wavelength_angstrom,legacy.max_wavelength_angstrom,
               legacy.median_spectral_resolving_power,
               legacy.pix_per_res_element,legacy.seeing,
               legacy.wavelength_solution_reference,
               legacy.wavelength_solution_error_kms,
               legacy.slit_filling_rv_correction,
               legacy.slit_filling_rv_error_kms,
               legacy.data_reduction_pipeline_version,
               legacy.modified_timestamp AS modification_date
        FROM moca_spectra AS legacy
        LEFT JOIN moca_objects AS object_row
          ON object_row.moca_oid=legacy.moca_oid
        WHERE legacy.ignored=0
          AND (legacy.moca_specpackid IS NULL OR
               legacy.moca_specpackid NOT IN ({excluded}))
          AND legacy.moca_oid=%s
          AND legacy.moca_instid <=> %s
          AND {observing_night('legacy')} <=> %s
        ORDER BY legacy.moca_specpackid,legacy.moca_specid
        """,
        (
            *EXCLUDED_LEGACY_PACKAGES,
            current["moca_oid"],
            current.get("moca_instid"),
            current.get("observing_night"),
        ),
    )
    return [row for row in rows if rows_mode_compatible(current, row)]


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _coverage_metrics(
    current: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, float | bool]:
    current_min = _finite_positive(current.get("min_wavelength_angstrom"))
    current_max = _finite_positive(current.get("max_wavelength_angstrom"))
    candidate_min = _finite_positive(candidate.get("min_wavelength_angstrom"))
    candidate_max = _finite_positive(candidate.get("max_wavelength_angstrom"))
    if (
        current_min is None
        or current_max is None
        or candidate_min is None
        or candidate_max is None
        or current_max <= current_min
        or candidate_max <= candidate_min
    ):
        return {
            "has_overlap": False,
            "overlap_angstrom": 0.0,
            "overlap_fraction": 0.0,
            "coverage_similarity": 0.0,
        }
    overlap = max(
        0.0, min(current_max, candidate_max) - max(current_min, candidate_min)
    )
    union = max(current_max, candidate_max) - min(current_min, candidate_min)
    shorter_span = min(current_max - current_min, candidate_max - candidate_min)
    return {
        "has_overlap": overlap > 0,
        "overlap_angstrom": overlap,
        "overlap_fraction": overlap / shorter_span if shorter_span > 0 else 0.0,
        "coverage_similarity": overlap / union if union > 0 else 0.0,
    }


def _resolution_metrics(
    current: dict[str, Any], candidate: dict[str, Any]
) -> tuple[int, float, float | None]:
    current_r = _finite_positive(current.get("median_spectral_resolving_power"))
    candidate_r = _finite_positive(candidate.get("median_spectral_resolving_power"))
    if current_r is None:
        return 0, 0.0, None
    if candidate_r is None:
        return 1, 0.0, None
    ratio = candidate_r / current_r
    return 0, abs(math.log(ratio)), ratio


def _date_distance(current: dict[str, Any], candidate: dict[str, Any]) -> float:
    current_mjd = _finite_positive(current.get("epoch_mjd"))
    candidate_mjd = _finite_positive(candidate.get("epoch_mjd"))
    if current_mjd is None or candidate_mjd is None:
        return math.inf
    return abs(current_mjd - candidate_mjd)


def select_approximate_legacy(
    current: dict[str, Any], candidates: Iterable[dict[str, Any]]
) -> dict[str, Any] | None:
    """Choose one clearly approximate same-object legacy comparator.

    A known different-night spectrum from the same instrument always has first
    priority.  A same-instrument spectrum whose observing night is unavailable
    is the next-best tier: missing legacy date metadata must not force a
    cross-instrument comparison.  If neither exists, a different-instrument
    spectrum must overlap the current wavelength range.  Within a tier, prefer
    measured resolving power, wavelength overlap/coverage similarity, and
    temporal proximity, with ``moca_specid`` as a deterministic final tie-breaker.
    """

    current_oid = current.get("moca_oid")
    if current_oid is None:
        return None
    current_instrument = str(current.get("moca_instid") or "").strip()
    current_night = str(current.get("observing_night") or "").strip()
    same_instrument_different_night: list[
        tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]
    ] = []
    same_instrument_unknown_night: list[
        tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]
    ] = []
    other_instrument: list[tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]] = []
    for original in candidates:
        candidate = dict(original)
        if candidate.get("moca_oid") != current_oid:
            continue
        candidate_instrument = str(candidate.get("moca_instid") or "").strip()
        candidate_night = str(candidate.get("observing_night") or "").strip()
        coverage = _coverage_metrics(current, candidate)
        resolution_missing, resolution_distance, resolution_ratio = (
            _resolution_metrics(current, candidate)
        )
        coverage_distance = 1.0 - float(coverage["coverage_similarity"])
        combined_distance = resolution_distance + coverage_distance
        specid = int(candidate.get("moca_specid") or 0)
        score = (
            not bool(coverage["has_overlap"]),
            resolution_missing,
            combined_distance,
            _date_distance(current, candidate),
            specid,
        )
        details = {
            "approximate_match_score": combined_distance,
            "wavelength_overlap_angstrom": coverage["overlap_angstrom"],
            "wavelength_overlap_fraction": coverage["overlap_fraction"],
            "wavelength_coverage_similarity": coverage["coverage_similarity"],
            "resolving_power_ratio": resolution_ratio,
        }
        if current_instrument and candidate_instrument == current_instrument:
            if current_night and candidate_night:
                if candidate_night != current_night:
                    same_instrument_different_night.append(
                        (score, candidate, details)
                    )
            else:
                same_instrument_unknown_night.append((score, candidate, details))
        elif (
            current_instrument
            and candidate_instrument
            and candidate_instrument != current_instrument
            and bool(coverage["has_overlap"])
        ):
            other_instrument.append((score, candidate, details))

    if same_instrument_different_night:
        pool = same_instrument_different_night
        match_basis = "same instrument, different observing night"
        match_tier = "same_instrument_different_night"
    elif same_instrument_unknown_night:
        pool = same_instrument_unknown_night
        match_basis = "same instrument; observing night unavailable"
        match_tier = "same_instrument_unknown_night"
    elif other_instrument:
        pool = other_instrument
        match_basis = (
            "different instrument; closest resolving power and wavelength coverage"
        )
        match_tier = "different_instrument"
    else:
        return None
    _, selected, details = min(pool, key=lambda item: item[0])
    selected.update(details)
    selected["approximate_match_basis"] = match_basis
    selected["approximate_match_tier"] = match_tier
    return selected


def _approximate_legacy_metadata(current: dict[str, Any]) -> dict[str, Any] | None:
    if current.get("moca_oid") is None:
        return None
    excluded = ",".join(["%s"] * len(EXCLUDED_LEGACY_PACKAGES))
    rows = readonly_rows(
        f"""
        SELECT legacy.moca_specid,legacy.moca_specpackid,legacy.moca_oid,
               legacy.moca_instid,legacy.spectrum_name,
               {object_name_sql('legacy', 'object_row')} AS object_name,
               legacy.instrument_mode_name,
               {observing_night('legacy')} AS observing_night,legacy.epoch_mjd,
               legacy.flux_units,legacy.slit_width_as,
               legacy.min_wavelength_angstrom,legacy.max_wavelength_angstrom,
               legacy.median_spectral_resolving_power,
               legacy.pix_per_res_element,legacy.seeing,
               legacy.wavelength_solution_reference,
               legacy.wavelength_solution_error_kms,
               legacy.slit_filling_rv_correction,
               legacy.slit_filling_rv_error_kms,
               legacy.data_reduction_pipeline_version,
               legacy.modified_timestamp AS modification_date
        FROM moca_spectra AS legacy
        LEFT JOIN moca_objects AS object_row
          ON object_row.moca_oid=legacy.moca_oid
        WHERE legacy.ignored=0
          AND (legacy.moca_specpackid IS NULL OR
               legacy.moca_specpackid NOT IN ({excluded}))
          AND legacy.moca_oid=%s
        ORDER BY legacy.moca_specid
        """,
        (*EXCLUDED_LEGACY_PACKAGES, current["moca_oid"]),
    )
    return select_approximate_legacy(current, rows)


def _spectral_samples_for_specids_by_quality(
    specids: Iterable[int],
    xmin: float | None,
    xmax: float | None,
) -> dict[int, QualitySamples]:
    """Fetch valid, ignored, and S/N samples for all displayed traces at once."""

    ordered_specids = list(dict.fromkeys(int(specid) for specid in specids))
    if not ordered_specids:
        return {}
    placeholders = ",".join(["%s"] * len(ordered_specids))
    clauses = [
        f"moca_specid IN ({placeholders})",
        "wavelength_angstrom IS NOT NULL",
        "flux_flambda IS NOT NULL",
    ]
    parameters: list[Any] = list(ordered_specids)
    if xmin is not None:
        clauses.append("wavelength_angstrom >= %s")
        parameters.append(xmin)
    if xmax is not None:
        clauses.append("wavelength_angstrom <= %s")
        parameters.append(xmax)
    rows = readonly_rows(
        "SELECT moca_specid,wavelength_angstrom,flux_flambda,flux_flambda_unc,ignored "
        "FROM data_spectra WHERE "
        + " AND ".join(clauses)
        + " ORDER BY moca_specid,wavelength_angstrom",
        parameters,
    )
    result: dict[int, QualitySamples] = {
        specid: ([], [], []) for specid in ordered_specids
    }
    for row in rows:
        row_specid = int(row.get("moca_specid", ordered_specids[0]))
        if row_specid not in result:
            continue
        valid_samples, ignored_samples, snr_samples = result[row_specid]
        wavelength = float(row["wavelength_angstrom"])
        flux = float(row["flux_flambda"])
        if math.isfinite(wavelength) and math.isfinite(flux):
            is_ignored = int(row.get("ignored") or 0) != 0
            samples = ignored_samples if is_ignored else valid_samples
            samples.append((wavelength, flux))
            uncertainty_value = row.get("flux_flambda_unc")
            if not is_ignored and uncertainty_value is not None:
                uncertainty = float(uncertainty_value)
                snr = flux / uncertainty if uncertainty > 0 else math.nan
                if math.isfinite(uncertainty) and math.isfinite(snr):
                    snr_samples.append((wavelength, snr))
    return result


def _spectral_samples_by_quality(
    specid: int,
    xmin: float | None,
    xmax: float | None,
) -> tuple[
    list[tuple[float, float]],
    list[tuple[float, float]],
    list[tuple[float, float]],
]:
    """Compatibility wrapper for one spectrum's quality-separated samples."""

    return _spectral_samples_for_specids_by_quality([specid], xmin, xmax)[int(specid)]


def minmax_downsample(samples: list[tuple[float, float]], max_points: int) -> list[tuple[float, float]]:
    """Preserve local extrema while bounding the payload size."""
    if len(samples) <= max_points:
        return samples
    interior = samples[1:-1]
    bucket_count = max(1, (max_points - 2) // 2)
    result = [samples[0]]
    for bucket in range(bucket_count):
        start = bucket * len(interior) // bucket_count
        stop = (bucket + 1) * len(interior) // bucket_count
        part = interior[start:stop]
        if not part:
            continue
        minimum = min(range(len(part)), key=lambda index: part[index][1])
        maximum = max(range(len(part)), key=lambda index: part[index][1])
        for index in sorted({minimum, maximum}):
            result.append(part[index])
    result.append(samples[-1])
    return result[:max_points]


def shared_normalization_details(
    series: list[list[tuple[float, float]]],
) -> tuple[list[float] | None, list[float], list[list[float]]]:
    """Return scales measured in identical, equally weighted wavelength boxes.

    The browser receives extrema-preserving downsampled traces, whose medians are
    not representative of the underlying spectra.  Measure normalization from
    full-resolution samples here instead.  A common outer min/max interval is
    insufficient when traces have different sampling densities or gaps: their
    pixel-weighted medians then represent different wavelength distributions.
    Divide the overlap into equal-width boxes, retain only boxes populated by
    every trace, take one median per trace and box, then give each common box
    equal weight.  If there is no jointly populated box, fall back to each
    trace's own positive-flux median.
    """

    supports = [
        (min(point[0] for point in samples), max(point[0] for point in samples))
        for samples in series
        if samples
    ]
    common_range: list[float] | None = None
    if len(supports) == len(series) and supports:
        lower = max(support[0] for support in supports)
        upper = min(support[1] for support in supports)
        if upper > lower:
            common_range = [lower, upper]

    if common_range is not None:
        lower, upper = common_range
        positive_counts = [
            sum(
                1
                for wavelength, flux in samples
                if lower <= wavelength <= upper
                and math.isfinite(flux)
                and flux > 0
            )
            for samples in series
        ]
        minimum_count = min(positive_counts, default=0)
        window_count = max(
            1,
            min(
                MAX_NORMALIZATION_WINDOWS,
                minimum_count // NORMALIZATION_SAMPLES_PER_WINDOW,
            ),
        )
        span = upper - lower
        buckets: list[list[list[float]]] = [
            [[] for _ in range(window_count)] for _ in series
        ]
        for trace_index, samples in enumerate(series):
            for wavelength, flux in samples:
                if not (
                    lower <= wavelength <= upper
                    and math.isfinite(flux)
                    and flux > 0
                ):
                    continue
                window_index = min(
                    window_count - 1,
                    int((wavelength - lower) / span * window_count),
                )
                buckets[trace_index][window_index].append(flux)

        window_levels: list[list[float]] = [[] for _ in series]
        common_windows: list[list[float]] = []
        for window_index in range(window_count):
            if not all(buckets[index][window_index] for index in range(len(series))):
                continue
            common_windows.append(
                [
                    lower + span * window_index / window_count,
                    lower + span * (window_index + 1) / window_count,
                ]
            )
            for trace_index in range(len(series)):
                window_levels[trace_index].append(
                    float(statistics.median(buckets[trace_index][window_index]))
                )

        if common_windows:
            reference_levels = window_levels[0]
            reference_scale = float(statistics.median(reference_levels))
            scales = [reference_scale]
            for levels in window_levels[1:]:
                relative_scale = float(
                    statistics.median(
                        level / reference
                        for level, reference in zip(
                            levels, reference_levels, strict=True
                        )
                    )
                )
                scales.append(reference_scale * relative_scale)
            return common_range, [
                scale if math.isfinite(scale) and scale > 0 else 1.0
                for scale in scales
            ], common_windows

    scales: list[float] = []
    for samples in series:
        values = [
            flux for _, flux in samples if math.isfinite(flux) and flux > 0
        ]
        scale = float(statistics.median(values)) if values else 1.0
        scales.append(scale if math.isfinite(scale) and scale > 0 else 1.0)
    return common_range, scales, []


def shared_normalization(
    series: list[list[tuple[float, float]]],
) -> tuple[list[float] | None, list[float]]:
    """Compatibility wrapper returning the common range and trace scales."""

    common_range, scales, _ = shared_normalization_details(series)
    return common_range, scales


def reference_normalization_details(
    series: list[list[tuple[float, float]]],
) -> tuple[list[float], list[dict[str, Any]]]:
    """Normalize every comparison to the first trace over its own overlap.

    A multi-arm legacy product can contain traces whose wavelength ranges only
    touch in a narrow detector/arm seam.  Requiring one interval populated by
    *all* traces would then derive every scale from that seam.  Instead, choose
    one stable scale for the new reduction and measure each comparison/new
    ratio independently in equal-width windows spanning that pair's complete
    valid overlap.
    """

    if not series:
        return [], []

    reference = series[0]
    _, reference_scales, reference_windows = shared_normalization_details(
        [reference]
    )
    reference_scale = reference_scales[0]
    scales = [reference_scale]
    details: list[dict[str, Any]] = [
        {
            "trace_index": 0,
            "reference_trace_index": 0,
            "range_angstrom": (
                [reference[0][0], reference[-1][0]] if reference else None
            ),
            "windows_angstrom": reference_windows,
            "method": "reference_positive_windows",
            "relative_scale": 1.0,
        }
    ]

    for trace_index, comparison in enumerate(series[1:], start=1):
        pair_range, pair_scales, pair_windows = shared_normalization_details(
            [reference, comparison]
        )
        pair_reference_scale, pair_comparison_scale = pair_scales
        relative_scale = (
            pair_comparison_scale / pair_reference_scale
            if math.isfinite(pair_reference_scale) and pair_reference_scale > 0
            else 1.0
        )
        if not math.isfinite(relative_scale) or relative_scale <= 0:
            relative_scale = 1.0
        scales.append(reference_scale * relative_scale)
        details.append(
            {
                "trace_index": trace_index,
                "reference_trace_index": 0,
                "range_angstrom": pair_range,
                "windows_angstrom": pair_windows,
                "method": (
                    "paired_overlap_windows"
                    if pair_windows
                    else "independent_positive_medians"
                ),
                "relative_scale": relative_scale,
            }
        )
    return scales, details


def spectrum_payload(
    specid: int,
    *,
    xmin: float | None = None,
    xmax: float | None = None,
    max_points: int = DEFAULT_MAX_POINTS,
) -> dict[str, Any]:
    current = _spectrum_metadata(specid)
    available_legacy = _legacy_metadata(current)
    legacy = available_legacy[:MAX_LEGACY_OVERLAYS]
    approximate_legacy = (
        None if available_legacy else _approximate_legacy_metadata(current)
    )
    comparison_rows = [("legacy", row) for row in legacy]
    if approximate_legacy is not None:
        comparison_rows.append(("approximate_legacy", approximate_legacy))
    displayed_rows = (("new", current), *comparison_rows)
    samples_by_specid = _spectral_samples_for_specids_by_quality(
        [int(metadata["moca_specid"]) for _, metadata in displayed_rows], xmin, xmax
    )
    raw_traces = []
    for kind, metadata in displayed_rows:
        valid, ignored, snr = samples_by_specid[int(metadata["moca_specid"])]
        raw_traces.append((kind, metadata, valid, ignored, snr))

    normalization_scales, normalization_details = reference_normalization_details(
        [valid for _, _, valid, _, _ in raw_traces]
    )
    traces = []
    for (kind, metadata, valid, ignored, snr), normalization_scale, normalization in zip(
        raw_traces, normalization_scales, normalization_details, strict=True
    ):
        traces.append(
            {
                "kind": kind,
                "metadata": metadata,
                "original_points": len(valid),
                "original_ignored_points": len(ignored),
                "original_snr_points": len(snr),
                "normalization_scale": normalization_scale,
                "normalization_range_angstrom": normalization["range_angstrom"],
                "normalization_windows_angstrom": normalization[
                    "windows_angstrom"
                ],
                "normalization_method": normalization["method"],
                "normalization_relative_scale": normalization[
                    "relative_scale"
                ],
                # The browser's refined smoother operates on these native
                # valid samples, then downsamples the completed curve.  Keep
                # ignored points out of both smoothing stages.
                "smoothing_points": valid,
                "points": minmax_downsample(valid, max_points),
                "ignored_points": minmax_downsample(ignored, max_points),
                "snr_points": minmax_downsample(snr, max_points),
            }
        )
    return {
        "current": current,
        "legacy_count": len(legacy),
        "total_legacy_count": len(available_legacy),
        "approximate_legacy_count": int(approximate_legacy is not None),
        "approximate_legacy": approximate_legacy,
        "max_points": max_points,
        # Retain the singular fields for one-comparator clients.  With multiple
        # comparison arms there is intentionally no single common interval.
        "normalization_range_angstrom": (
            normalization_details[1]["range_angstrom"]
            if len(normalization_details) == 2
            else None
        ),
        "normalization_windows_angstrom": (
            normalization_details[1]["windows_angstrom"]
            if len(normalization_details) == 2
            else []
        ),
        "normalization_details": normalization_details,
        "traces": traces,
    }
