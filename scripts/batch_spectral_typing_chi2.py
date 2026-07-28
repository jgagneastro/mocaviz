#!/usr/bin/env python3
"""Batch MOCAdb spectral typing and download compact chi-squared CSV tables."""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


DEFAULT_BASE_URL = "https://dataviz.mocadb.ca"
DEFAULT_NORM = "0.860-1.350,1.445-1.800,2.010-2.400"
DEFAULT_DBNAME = "mocadb_private_tables"
MAX_WORKERS = 4

CHI2_COLUMNS = [
    "requested_moca_oid",
    "spectrum_policy",
    "comparison_specid",
    "comparison_specids",
    "comparison_oid",
    "standard_specid",
    "standard_oid",
    "grid",
    "spectral_type",
    "spectral_type_number",
    "reduced_chi2",
    "best_parameters",
    "designation",
    "bibcode",
]

MANIFEST_COLUMNS = [
    "timestamp_utc",
    "moca_oid",
    "spectrum_policy",
    "specids",
    "target_key",
    "output_csv",
    "status",
    "chi2_row_count",
    "duration_seconds",
    "error_code",
    "error",
]


class ApiError(RuntimeError):
    def __init__(self, message: str, *, error_code: str = "", status: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status = status


@dataclass(frozen=True)
class BatchTask:
    moca_oid: int
    specids: tuple[int, ...]
    spectrum_policy: str

    @property
    def target_key(self) -> str:
        if len(self.specids) == 1:
            selection = f"specid_{self.specids[0]}"
        else:
            selection = "specids_" + "-".join(str(specid) for specid in self.specids)
        return f"oid_{self.moca_oid}_{selection}"


class SpectralTypingApi:
    def __init__(
        self,
        base_url: str,
        *,
        user: str = "",
        password: str = "",
        dbase: str = "",
        mock: bool = False,
        timeout: float = 600.0,
        retries: int = 2,
    ) -> None:
        parsed_base_url = urllib.parse.urlparse(base_url)
        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
            raise ValueError("--base-url must be an http:// or https:// URL.")
        self.base_url = base_url.rstrip("/")
        self.timeout = max(1.0, float(timeout))
        self.retries = max(0, int(retries))
        self.mock = bool(mock)
        self.requested_dbase = str(dbase or "").strip().strip("`").casefold()
        self.auth_headers = {
            key: value
            for key, value in {
                "X-MOCA-User": user,
                "X-MOCA-Password": password,
                "X-MOCA-Database": dbase,
            }.items()
            if value
        }
        self.common_params = {"mock": "1"} if mock else {}

    def search_spectra(self, moca_oid: int) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "api/spectral-typing/search",
            params={"moca_oid": int(moca_oid)},
        )
        self._validate_database_access(payload, "spectral-typing search")
        return list(payload.get("options") or [])

    def search_spectrum(self, moca_specid: int) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "api/spectral-typing/search",
            params={"specid": int(moca_specid)},
        )
        self._validate_database_access(payload, "spectral-typing search")
        return list(payload.get("options") or [])

    def compare(self, specids: Sequence[int], settings: Mapping[str, Any]) -> dict[str, Any]:
        selected = sorted({int(specid) for specid in specids})
        body: dict[str, Any] = {
            "summary_only": True,
            "bins": int(settings["bins"]),
            "norm": str(settings["norm"]),
            "deredden": bool(settings["deredden"]),
            "cloud_correction": bool(settings["cloud"]),
            "cloud_alpha": float(settings["cloud_alpha"]),
            "cloud_alpha_fixed": not bool(settings["fit_cloud_alpha"]),
            "standards_source": str(settings["standards_source"]),
            "only_field": bool(settings["only_field"]),
        }
        if settings.get("fix_rv") is not None:
            body["fix_rv"] = float(settings["fix_rv"])
        if len(selected) == 1:
            body["specid"] = selected[0]
        else:
            body["specids"] = selected
        payload = self._request("POST", "api/spectral-typing/compare", body=body)
        self._validate_database_access(payload, "spectral-typing comparison")
        return payload

    def _validate_database_access(
        self,
        payload: Mapping[str, Any],
        operation: str,
    ) -> None:
        if self.mock or self.requested_dbase != DEFAULT_DBNAME.casefold():
            return
        meta = payload.get("meta")
        private_db = meta.get("private_db") if isinstance(meta, Mapping) else None
        if private_db is True:
            return
        if private_db is False:
            detail = "the server reported a public-database response"
        else:
            detail = "the server did not confirm private-database access"
        raise ApiError(
            f"Private database access was requested, but {detail} during "
            f"{operation}. Refusing to write incomplete public-grid results. "
            "Verify the credentials and deploy a MOCAviz version that supports "
            "X-MOCA authentication headers.",
            error_code="private_database_not_confirmed",
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        query_values = {**self.common_params}
        query_values.update({
            key: value
            for key, value in (params or {}).items()
            if value is not None and value != ""
        })
        query = urllib.parse.urlencode(query_values, doseq=True)
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        encoded_body = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "MOCAviz-batch-spectral-typing/1.0",
            **self.auth_headers,
        }
        if body is not None:
            encoded_body = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        last_error: ApiError | None = None
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(
                url,
                data=encoded_body,
                headers=headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = _decode_json(response.read(), endpoint)
                if not payload.get("ok", True):
                    raise ApiError(
                        str(payload.get("error") or f"{endpoint} failed"),
                        error_code=str(payload.get("error_code") or ""),
                    )
                return payload
            except urllib.error.HTTPError as error:
                payload = _decode_json(error.read(), endpoint, allow_empty=True)
                last_error = ApiError(
                    str(payload.get("error") or f"{endpoint} returned HTTP {error.code}"),
                    error_code=str(payload.get("error_code") or ""),
                    status=int(error.code),
                )
                retryable = error.code == 429 or error.code >= 500
                if not retryable or attempt >= self.retries:
                    raise last_error from None
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = ApiError(f"{endpoint} request failed: {error.reason if hasattr(error, 'reason') else error}")
                if attempt >= self.retries:
                    raise last_error from None
            except ApiError:
                raise
            time.sleep(min(8.0, 0.75 * (2 ** attempt)))
        raise last_error or ApiError(f"{endpoint} request failed")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve moca_oid values or select explicit moca_specid values, run "
            "the MOCAviz spectral-typing API, and write resumable chi-squared "
            "CSV exports."
        ),
    )
    parser.add_argument(
        "input_csv",
        nargs="?",
        type=Path,
        help="CSV, TSV, or one-value-per-line file containing moca_oid values.",
    )
    parser.add_argument(
        "--oid",
        type=int,
        action="append",
        default=[],
        help="Process one moca_oid directly. May be repeated.",
    )
    parser.add_argument(
        "--specid",
        "--spec-id",
        dest="specid",
        type=int,
        action="append",
        default=[],
        metavar="MOCA_SPECID",
        help=(
            "Type exactly this moca_specid without selecting the object's other "
            "spectra. May be repeated."
        ),
    )
    parser.add_argument(
        "--specid-csv",
        "--spec-id-csv",
        dest="specid_csv",
        type=Path,
        metavar="PATH",
        help=(
            "CSV, TSV, or one-value-per-line file containing explicit "
            "moca_specid values."
        ),
    )
    parser.add_argument(
        "--specid-column",
        "--spec-id-column",
        dest="specid_column",
        default="",
        help=(
            "Column in --specid-csv containing spectrum IDs. Auto-detects "
            "moca_specid, specid, or spec_id by default."
        ),
    )
    parser.add_argument(
        "--oid-column",
        default="",
        help="Input column containing object IDs. Auto-detects moca_oid or oid by default.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("spectral_typing_chi2"),
        help="Output directory (default: spectral_typing_chi2).",
    )
    parser.add_argument(
        "--combined-only",
        "--no-individual-csvs",
        dest="combined_only",
        action="store_true",
        help=(
            "Write result rows only to combined_chi2.csv without creating "
            "per-comparison chi2/*.csv files. The manifest and run "
            "configuration are still retained."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MOCAVIZ_BASE_URL", DEFAULT_BASE_URL),
        help=f"MOCAviz server URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("MOCAVIZ_USER", ""),
        help="MOCAdb user. Defaults to MOCAVIZ_USER.",
    )
    parser.add_argument(
        "--dbase",
        default=os.environ.get("MOCAVIZ_DBASE", DEFAULT_DBNAME),
        help=f"Database schema (default: {DEFAULT_DBNAME}).",
    )
    parser.add_argument(
        "--no-password-prompt",
        action="store_true",
        help="Do not prompt if a user was supplied without MOCAVIZ_PASSWORD.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use the server's network-free mock spectral-typing data.",
    )
    parser.add_argument(
        "--spectrum-policy",
        choices=("all", "composite", "first"),
        default="all",
        help=(
            "How to handle multiple spectra per object: all writes one CSV per "
            "spectrum (default); composite combines them (the server normally "
            "allows up to eight); first uses the lowest specid. This does not "
            "affect explicit --specid selections."
        ),
    )
    parser.add_argument("--bins", type=int, default=200, help="Bins per micron (default: 200).")
    parser.add_argument("--norm", default=DEFAULT_NORM, help="Normalization wavelength regions.")
    parser.add_argument(
        "--standards-source",
        choices=("moca", "pickles"),
        default="moca",
        help="Standards library (default: moca).",
    )
    parser.add_argument("--only-field", action="store_true", help="Use only field/solar-metallicity standards.")
    parser.add_argument("--deredden", action="store_true", help="Fit extinction while computing chi-squared values.")
    parser.add_argument("--fix-rv", type=float, default=None, help="Fixed R(V) for --deredden.")
    parser.add_argument("--cloud", action="store_true", help="Apply the brown-dwarf slope correction.")
    parser.add_argument("--cloud-alpha", type=float, default=1.7, help="Cloud alpha value (default: 1.7).")
    parser.add_argument("--fit-cloud-alpha", action="store_true", help="Fit cloud alpha instead of fixing it.")
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=f"Concurrent comparison requests, 1-{MAX_WORKERS} (default: 1).",
    )
    parser.add_argument("--pause", type=float, default=0.25, help="Pause after each comparison request in seconds.")
    parser.add_argument("--timeout", type=float, default=600.0, help="Per-request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries for transient request failures.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N unique object IDs and explicit spectrum IDs.",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Skip successful existing outputs (default: true). Combined-only "
            "runs inspect combined_chi2.csv directly."
        ),
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Resolve spectra and print the planned comparisons without computing them.",
    )
    args = parser.parse_args(argv)
    if (
        args.input_csv is None
        and not args.oid
        and not args.specid
        and args.specid_csv is None
    ):
        parser.error(
            "provide input_csv, --specid-csv, at least one --oid, "
            "or at least one --specid"
        )
    if any(specid <= 0 for specid in args.specid):
        parser.error("--specid values must be positive")
    if args.deredden and args.cloud:
        parser.error("--deredden and --cloud cannot be used together")
    if args.fit_cloud_alpha and not args.cloud:
        parser.error("--fit-cloud-alpha requires --cloud")
    if args.fix_rv is not None and not args.deredden:
        parser.error("--fix-rv requires --deredden")
    if not 1 <= args.workers <= MAX_WORKERS:
        parser.error(f"--workers must be between 1 and {MAX_WORKERS}")
    if args.bins < 1 or args.bins > 2000:
        parser.error("--bins must be between 1 and 2000")
    if args.pause < 0:
        parser.error("--pause cannot be negative")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.retries < 0:
        parser.error("--retries cannot be negative")
    if args.fix_rv is not None and args.fix_rv <= 0:
        parser.error("--fix-rv must be positive")
    if args.cloud_alpha <= 0:
        parser.error("--cloud-alpha must be positive")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    return args


def _load_identifier_values(
    path: Path | None,
    direct_values: Sequence[int],
    requested_column: str,
    auto_columns: Sequence[str],
    identifier_name: str,
    parse_value: Callable[[str, int | None], int],
) -> list[int]:
    values: list[int] = [int(value) for value in direct_values]
    if path is not None:
        if not path.is_file():
            raise SystemExit(f"Input file not found: {path}")
        text = path.read_text(encoding="utf-8-sig")
        if text.strip():
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
            except csv.Error:
                dialect = csv.excel
            rows = list(csv.reader(text.splitlines(), dialect))
            rows = [row for row in rows if row and any(cell.strip() for cell in row)]
            if rows:
                header = [cell.strip() for cell in rows[0]]
                normalized = [cell.lower() for cell in header]
                requested = requested_column.strip().lower()
                has_header = False
                if requested:
                    if requested not in normalized:
                        raise SystemExit(
                            f"Input file has no {requested_column!r} column."
                        )
                    column_index = normalized.index(requested)
                    has_header = True
                else:
                    matching_columns = [
                        column
                        for column in auto_columns
                        if column in normalized
                    ]
                    if matching_columns:
                        column_index = normalized.index(matching_columns[0])
                        has_header = True
                    else:
                        column_index = 0
                data_rows = rows[1:] if has_header else rows
                for line_number, row in enumerate(
                    data_rows,
                    start=2 if has_header else 1,
                ):
                    if column_index >= len(row):
                        raise SystemExit(
                            f"Missing {identifier_name} at input line {line_number}."
                        )
                    raw = row[column_index].strip()
                    if not raw or raw.startswith("#"):
                        continue
                    values.append(parse_value(raw, line_number))

    unique: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value <= 0:
            raise SystemExit(f"{identifier_name} values must be positive: {value}")
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def load_moca_oids(
    path: Path | None,
    direct_oids: Sequence[int],
    oid_column: str = "",
) -> list[int]:
    return _load_identifier_values(
        path,
        direct_oids,
        oid_column,
        ("moca_oid", "oid"),
        "moca_oid",
        parse_moca_oid,
    )


def load_moca_specids(
    path: Path | None,
    direct_specids: Sequence[int],
    specid_column: str = "",
) -> list[int]:
    return _load_identifier_values(
        path,
        direct_specids,
        specid_column,
        ("moca_specid", "specid", "spec_id"),
        "moca_specid",
        parse_moca_specid,
    )


def parse_moca_oid(raw: str, line_number: int | None = None) -> int:
    text = str(raw).strip()
    match = re.fullmatch(r"(?:(?:moca_)?oid\s*[:#_(]?\s*)?([0-9]+)\)?", text, flags=re.IGNORECASE)
    if not match or int(match.group(1)) <= 0:
        location = f" at input line {line_number}" if line_number is not None else ""
        raise SystemExit(f"Invalid moca_oid{location}: {raw!r}")
    return int(match.group(1))


def parse_moca_specid(raw: str, line_number: int | None = None) -> int:
    text = str(raw).strip()
    match = re.fullmatch(
        r"(?:(?:moca_)?spec_?id\s*[:#_(]?\s*)?([0-9]+)\)?",
        text,
        flags=re.IGNORECASE,
    )
    if not match or int(match.group(1)) <= 0:
        location = (
            f" at input line {line_number}"
            if line_number is not None
            else ""
        )
        raise SystemExit(f"Invalid moca_specid{location}: {raw!r}")
    return int(match.group(1))


def comparison_tasks(moca_oid: int, options: Sequence[Mapping[str, Any]], policy: str) -> list[BatchTask]:
    specids = sorted({
        int(option["moca_specid"])
        for option in options
        if option.get("moca_specid") is not None
        and int(option.get("moca_oid") or moca_oid) == int(moca_oid)
    })
    if not specids:
        return []
    if policy == "all":
        return [BatchTask(int(moca_oid), (specid,), policy) for specid in specids]
    if policy == "first":
        return [BatchTask(int(moca_oid), (specids[0],), policy)]
    return [BatchTask(int(moca_oid), tuple(specids), policy)]


def specific_comparison_task(
    moca_specid: int,
    options: Sequence[Mapping[str, Any]],
) -> BatchTask | None:
    for option in options:
        try:
            option_specid = int(option.get("moca_specid"))
            option_oid = int(option.get("moca_oid"))
        except (TypeError, ValueError):
            continue
        if option_specid == int(moca_specid) and option_oid > 0:
            return BatchTask(option_oid, (option_specid,), "specific")
    return None


def chi2_rows(
    payload: Mapping[str, Any],
    task: BatchTask,
    settings: Mapping[str, Any],
) -> list[dict[str, Any]]:
    meta = payload.get("meta") or {}
    metadata = payload.get("comparisonMetadata") or {}
    specids = sorted({
        int(value)
        for value in (meta.get("specids") or task.specids)
        if value is not None
    })
    comparison_specid: int | str = specids[0] if len(specids) == 1 else ""
    comparison_oid = metadata.get("moca_oid") or task.moca_oid
    rows = []
    for entry in payload.get("entries") or []:
        rows.append({
            "requested_moca_oid": task.moca_oid,
            "spectrum_policy": task.spectrum_policy,
            "comparison_specid": comparison_specid,
            "comparison_specids": ",".join(str(specid) for specid in specids),
            "comparison_oid": comparison_oid,
            "standard_specid": entry.get("moca_specid") or "",
            "standard_oid": entry.get("moca_oid") or "",
            "grid": entry.get("grid") or "",
            "spectral_type": entry.get("spectral_type") or "",
            "spectral_type_number": _finite_or_blank(entry.get("spectral_type_number")),
            "reduced_chi2": _finite_or_blank(entry.get("reduced_chi2")),
            "best_parameters": best_parameters(entry, settings),
            "designation": entry.get("designation") or entry.get("object_designation") or "",
            "bibcode": entry.get("bibcode") or "",
        })
    return rows


def best_parameters(entry: Mapping[str, Any], settings: Mapping[str, Any]) -> str:
    if settings.get("deredden") and isinstance(entry.get("A_V"), list):
        rv_values = entry.get("R_V") if isinstance(entry.get("R_V"), list) else []
        parts = []
        for index, av in enumerate(entry["A_V"]):
            if _as_float(av) is None:
                continue
            region_rv = rv_values[index] if index < len(rv_values) else None
            values = [f"A(V)_{index + 1}={_format_number(av, 4)}"]
            if _as_float(region_rv) not in (None, 0.0):
                values.append(f"E(B-V)_{index + 1}={_format_number(float(av) / float(region_rv), 4)}")
                values.append(f"R(V)_{index + 1}={_format_number(region_rv, 4)}")
            parts.extend(values)
        return "; ".join(parts)
    if settings.get("cloud") and isinstance(entry.get("cloud_tau0"), list):
        alpha_values = entry.get("cloud_alpha_values") if isinstance(entry.get("cloud_alpha_values"), list) else []
        parts = []
        for index, tau0 in enumerate(entry["cloud_tau0"]):
            if _as_float(tau0) is None:
                continue
            value = f"tau_{index + 1}={_format_number(tau0, 5)}"
            if index < len(alpha_values) and _as_float(alpha_values[index]) is not None:
                value += f"; alpha_{index + 1}={_format_number(alpha_values[index], 5)}"
            parts.append(value)
        return "; ".join(parts)
    return ""


def run_batch(args: argparse.Namespace, api: SpectralTypingApi | None = None) -> int:
    oids = load_moca_oids(args.input_csv, args.oid, args.oid_column)
    specids = load_moca_specids(
        args.specid_csv,
        args.specid,
        args.specid_column,
    )
    if args.limit is not None:
        oids = oids[:args.limit]
        specids = specids[:args.limit]
    if not oids and not specids:
        raise SystemExit("No moca_oid or moca_specid values were found.")

    password = os.environ.get("MOCAVIZ_PASSWORD", "")
    if args.user and not password and not args.no_password_prompt and not args.mock:
        if not sys.stdin.isatty():
            raise SystemExit("Set MOCAVIZ_PASSWORD or run from an interactive terminal for the password prompt.")
        password = getpass.getpass(f"Password for MOCAdb user {args.user}: ")

    settings = settings_from_args(args)
    client = api or SpectralTypingApi(
        args.base_url,
        user=args.user,
        password=password,
        dbase=args.dbase,
        mock=args.mock,
        timeout=args.timeout,
        retries=args.retries,
    )
    output_dir = args.output_dir.resolve()
    chi2_dir = output_dir / "chi2"
    combined_path = output_dir / "combined_chi2.csv"
    manifest_path = output_dir / "manifest.csv"
    config_path = output_dir / "run_config.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    if not args.combined_only:
        chi2_dir.mkdir(parents=True, exist_ok=True)
    ensure_run_config(config_path, run_configuration(args, settings))

    if args.resume:
        completed = (
            combined_target_keys(combined_path)
            if args.combined_only
            else completed_target_keys(manifest_path, output_dir)
        )
    else:
        completed = set()
    tasks: list[BatchTask] = []
    failures = 0
    no_spectra = 0
    print(
        f"Resolving spectra for {len(oids)} object(s) and "
        f"{len(specids)} explicit spectrum ID(s)..."
    )
    for index, oid in enumerate(oids, start=1):
        try:
            options = client.search_spectra(oid)
            resolved = comparison_tasks(oid, options, args.spectrum_policy)
            if not resolved:
                no_spectra += 1
                append_manifest(manifest_path, manifest_row(
                    oid,
                    args.spectrum_policy,
                    status="no_spectra",
                    error="No non-ignored spectra were found for this object.",
                ))
            else:
                tasks.extend(resolved)
        except ApiError as error:
            failures += 1
            append_manifest(manifest_path, manifest_row(
                oid,
                args.spectrum_policy,
                status="search_error",
                error_code=error.error_code,
                error=str(error),
            ))
            if error.error_code == "private_database_not_confirmed":
                raise SystemExit(str(error)) from None
        except Exception as error:
            failures += 1
            append_manifest(manifest_path, manifest_row(
                oid,
                args.spectrum_policy,
                status="search_error",
                error=error.__class__.__name__ + ": " + str(error),
            ))
        if index % 50 == 0 or index == len(oids):
            print(f"  resolved {index}/{len(oids)} objects")

    for index, specid in enumerate(specids, start=1):
        try:
            options = client.search_spectrum(specid)
            task = specific_comparison_task(specid, options)
            if task is None:
                no_spectra += 1
                append_manifest(manifest_path, manifest_row(
                    None,
                    "specific",
                    specids=(specid,),
                    target_key=f"specid_{specid}",
                    status="no_spectra",
                    error=f"No non-ignored spectrum was found for moca_specid={specid}.",
                ))
            else:
                tasks.append(task)
        except ApiError as error:
            failures += 1
            append_manifest(manifest_path, manifest_row(
                None,
                "specific",
                specids=(specid,),
                target_key=f"specid_{specid}",
                status="search_error",
                error_code=error.error_code,
                error=str(error),
            ))
            if error.error_code == "private_database_not_confirmed":
                raise SystemExit(str(error)) from None
        except Exception as error:
            failures += 1
            append_manifest(manifest_path, manifest_row(
                None,
                "specific",
                specids=(specid,),
                target_key=f"specid_{specid}",
                status="search_error",
                error=error.__class__.__name__ + ": " + str(error),
            ))
        if index % 50 == 0 or index == len(specids):
            print(f"  resolved {index}/{len(specids)} explicit spectrum IDs")

    tasks_by_key: dict[str, BatchTask] = {}
    for task in tasks:
        tasks_by_key[task.target_key] = task
    tasks = list(tasks_by_key.values())

    pending = [task for task in tasks if task.target_key not in completed]
    skipped = len(tasks) - len(pending)
    if args.plan_only:
        for task in pending:
            print(f"{task.target_key}: {','.join(str(specid) for specid in task.specids)}")
        print(f"Planned {len(pending)} comparison(s); {skipped} already complete.")
        return 1 if failures else 0

    print(
        f"Running {len(pending)} comparison(s) with {args.workers} worker(s)"
        f"{f'; skipping {skipped} completed' if skipped else ''}..."
    )
    successes = 0
    combined_rows: list[dict[str, Any]] = []
    if args.combined_only:
        pending_keys = {task.target_key for task in pending}
        combined_rows = [
            row
            for row in read_csv_rows(combined_path)
            if chi2_row_target_key(row) not in pending_keys
        ]
    if pending:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_tasks: dict[
                Future[tuple[dict[str, str], list[dict[str, Any]]]],
                BatchTask,
            ] = {
                executor.submit(
                    process_task,
                    client,
                    task,
                    settings,
                    output_dir,
                    args.pause,
                    not args.combined_only,
                ): task
                for task in pending
            }
            for completed_count, future in enumerate(as_completed(future_tasks), start=1):
                row, result_rows = future.result()
                append_manifest(manifest_path, row)
                if row["status"] == "success":
                    successes += 1
                    combined_rows.extend(result_rows)
                else:
                    failures += 1
                print(
                    f"  [{completed_count}/{len(pending)}] {row['target_key']}: "
                    f"{row['status']}"
                )

    if args.combined_only:
        combined_rows.sort(key=chi2_row_target_key)
        write_csv_atomic(combined_path, CHI2_COLUMNS, combined_rows)
        combined_count = len(combined_rows)
    else:
        combined_path, combined_count = rebuild_combined_csv(chi2_dir, combined_path)
    print(
        f"Finished: {successes} new success(es), {skipped} resumed, "
        f"{no_spectra} selection(s) without spectra, {failures} error(s)."
    )
    print(f"Combined {combined_count} chi-squared rows in {combined_path}")
    print(f"Manifest: {manifest_path}")
    return 1 if failures else 0


def process_task(
    api: SpectralTypingApi,
    task: BatchTask,
    settings: Mapping[str, Any],
    output_dir: Path,
    pause: float,
    write_individual_csv: bool = True,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    started = time.monotonic()
    relative_path = Path("chi2") / f"{task.target_key}_chi2.csv"
    output_path = output_dir / relative_path
    output_csv = str(relative_path) if write_individual_csv else "combined_chi2.csv"
    if write_individual_csv and output_path.is_file():
        output_path.unlink()
    try:
        payload = api.compare(task.specids, settings)
        rows = chi2_rows(payload, task, settings)
        if not rows:
            raise ApiError("The spectral-typing response contained no chi-squared rows.")
        if write_individual_csv:
            write_csv_atomic(output_path, CHI2_COLUMNS, rows)
        return (
            manifest_row(
                task.moca_oid,
                task.spectrum_policy,
                specids=task.specids,
                target_key=task.target_key,
                output_csv=output_csv,
                status="success",
                chi2_row_count=len(rows),
                duration_seconds=time.monotonic() - started,
            ),
            rows,
        )
    except ApiError as error:
        return (
            manifest_row(
                task.moca_oid,
                task.spectrum_policy,
                specids=task.specids,
                target_key=task.target_key,
                output_csv=output_csv if write_individual_csv else "",
                status="error",
                duration_seconds=time.monotonic() - started,
                error_code=error.error_code,
                error=str(error),
            ),
            [],
        )
    except Exception as error:
        return (
            manifest_row(
                task.moca_oid,
                task.spectrum_policy,
                specids=task.specids,
                target_key=task.target_key,
                output_csv=output_csv if write_individual_csv else "",
                status="error",
                duration_seconds=time.monotonic() - started,
                error=error.__class__.__name__ + ": " + str(error),
            ),
            [],
        )
    finally:
        if pause > 0:
            time.sleep(float(pause))


def settings_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "bins": int(args.bins),
        "norm": str(args.norm),
        "standards_source": str(args.standards_source),
        "only_field": bool(args.only_field),
        "deredden": bool(args.deredden),
        "fix_rv": args.fix_rv,
        "cloud": bool(args.cloud),
        "cloud_alpha": float(args.cloud_alpha),
        "fit_cloud_alpha": bool(args.fit_cloud_alpha),
    }


def run_configuration(args: argparse.Namespace, settings: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "base_url": str(args.base_url).rstrip("/"),
        "user": str(args.user),
        "dbase": str(args.dbase),
        "mock": bool(args.mock),
        "spectrum_policy": str(args.spectrum_policy),
        **settings,
    }


def ensure_run_config(path: Path, configuration: Mapping[str, Any]) -> None:
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous != dict(configuration):
            raise SystemExit(
                f"Output settings differ from {path}. Choose a new --output-dir "
                "to avoid mixing incompatible chi-squared tables."
            )
        return
    write_text_atomic(path, json.dumps(configuration, indent=2, sort_keys=True) + "\n")


def completed_target_keys(manifest_path: Path, output_dir: Path) -> set[str]:
    if not manifest_path.is_file():
        return set()
    completed: set[str] = set()
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            output_csv = row.get("output_csv") or ""
            if (
                row.get("status") == "success"
                and output_csv
                and output_csv != "combined_chi2.csv"
                and (output_dir / output_csv).is_file()
            ):
                completed.add(row.get("target_key") or "")
    return completed


def combined_target_keys(path: Path) -> set[str]:
    return {
        target_key
        for row in read_csv_rows(path)
        if (target_key := chi2_row_target_key(row))
    }


def chi2_row_target_key(row: Mapping[str, Any]) -> str:
    try:
        moca_oid = int(row.get("requested_moca_oid") or 0)
        raw_specids = str(
            row.get("comparison_specids")
            or row.get("comparison_specid")
            or ""
        )
        specids = tuple(sorted({
            int(value.strip())
            for value in raw_specids.split(",")
            if value.strip()
        }))
    except (TypeError, ValueError):
        return ""
    if moca_oid <= 0 or not specids:
        return ""
    return BatchTask(
        moca_oid,
        specids,
        str(row.get("spectrum_policy") or ""),
    ).target_key


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def manifest_row(
    moca_oid: int | None,
    spectrum_policy: str,
    *,
    specids: Sequence[int] = (),
    target_key: str = "",
    output_csv: str = "",
    status: str,
    chi2_row_count: int | str = "",
    duration_seconds: float | str = "",
    error_code: str = "",
    error: str = "",
) -> dict[str, str]:
    oid_text = "" if moca_oid is None else str(int(moca_oid))
    default_target_key = (
        f"oid_{int(moca_oid)}"
        if moca_oid is not None
        else (
            f"specid_{int(specids[0])}"
            if len(specids) == 1
            else ""
        )
    )
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "moca_oid": oid_text,
        "spectrum_policy": spectrum_policy,
        "specids": ",".join(str(specid) for specid in specids),
        "target_key": target_key or default_target_key,
        "output_csv": output_csv,
        "status": status,
        "chi2_row_count": str(chi2_row_count),
        "duration_seconds": (
            f"{float(duration_seconds):.3f}"
            if duration_seconds != ""
            else ""
        ),
        "error_code": error_code,
        "error": " ".join(str(error).splitlines()),
    }


def append_manifest(path: Path, row: Mapping[str, Any]) -> None:
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())


def rebuild_combined_csv(chi2_dir: Path, output_path: Path) -> tuple[Path, int]:
    rows: list[dict[str, Any]] = []
    for path in sorted(chi2_dir.glob("*_chi2.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    write_csv_atomic(output_path, CHI2_COLUMNS, rows)
    return output_path, len(rows)


def write_csv_atomic(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _decode_json(payload: bytes, endpoint: str, *, allow_empty: bool = False) -> dict[str, Any]:
    if not payload and allow_empty:
        return {}
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ApiError(f"{endpoint} returned invalid JSON: {error}") from None
    if not isinstance(decoded, dict):
        raise ApiError(f"{endpoint} returned a non-object JSON response.")
    return decoded


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _finite_or_blank(value: Any) -> float | str:
    number = _as_float(value)
    return number if number is not None else ""


def _format_number(value: Any, digits: int) -> str:
    number = _as_float(value)
    return "" if number is None else f"{number:.{digits}f}"


def main(argv: Sequence[str] | None = None) -> int:
    return run_batch(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
