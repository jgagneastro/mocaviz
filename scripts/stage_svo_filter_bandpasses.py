#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import math
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from astropy.io.votable import parse_single_table


SVO_FPS_URL = "https://svo2.cab.inta-csic.es/theory/fps/fps.php"


@dataclass(frozen=True)
class FilterRequest:
    moca_psid: str
    svo_filter_id: str


@dataclass
class FilterProfile:
    request: FilterRequest
    wavelength_angstrom: np.ndarray
    response: np.ndarray
    average_wavelength: float | None
    min_wavelength: float | None
    max_wavelength: float | None
    zeropoint_jy: float | None
    params: dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch SVO Filter Profile Service bandpasses and write reviewable "
            "MOCAdb SQL. The script does not connect to or modify the database."
        )
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        metavar="MOCA_PSID=SVO_FILTER_ID",
        help="Filter mapping. May be repeated, e.g. --filter tmass_jmag=2MASS/2MASS.J",
    )
    parser.add_argument(
        "--mapping-csv",
        help="CSV file with moca_psid and svo_filter_id columns.",
    )
    parser.add_argument(
        "--output",
        help="Write SQL to this path. Defaults to stdout.",
    )
    parser.add_argument(
        "--nrows",
        type=int,
        default=3,
        help="Number of profile sample rows to report in SQL comments per filter.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="SVO request timeout in seconds.",
    )
    parser.add_argument(
        "--skip-zeropoint",
        action="append",
        default=[],
        metavar="MOCA_PSID",
        help=(
            "Do not stage zeropoint_jansky for this moca_psid. Use this for AB "
            "systems when SVO reports Vega zero points, or when zeropoints need "
            "separate manual validation."
        ),
    )
    return parser.parse_args()


def load_requests(args: argparse.Namespace) -> list[FilterRequest]:
    requests: list[FilterRequest] = []
    for raw in args.filter:
        if "=" not in raw:
            raise SystemExit(f"--filter must look like MOCA_PSID=SVO_FILTER_ID: {raw!r}")
        psid, svo_id = raw.split("=", 1)
        requests.append(FilterRequest(psid.strip(), svo_id.strip()))
    if args.mapping_csv:
        with Path(args.mapping_csv).open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            required = {"moca_psid", "svo_filter_id"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise SystemExit(f"Mapping CSV is missing columns: {', '.join(sorted(missing))}")
            for row in reader:
                psid = (row.get("moca_psid") or "").strip()
                svo_id = (row.get("svo_filter_id") or "").strip()
                if psid and svo_id:
                    requests.append(FilterRequest(psid, svo_id))
    unique: dict[str, FilterRequest] = {}
    for request in requests:
        if not request.moca_psid or not request.svo_filter_id:
            raise SystemExit("Empty moca_psid or SVO filter ID in request list.")
        unique[request.moca_psid] = request
    return list(unique.values())


def fetch_svo_profile(request: FilterRequest, timeout: float) -> FilterProfile:
    query = urllib.parse.urlencode({"ID": request.svo_filter_id})
    url = f"{SVO_FPS_URL}?{query}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = response.read()
    votable = parse_single_table(io.BytesIO(payload))
    table = votable.to_table()
    params = votable_params(votable)
    wave_col = find_column(table.colnames, ("wavelength", "lambda"))
    response_col = find_column(table.colnames, ("transmission", "response", "throughput"))
    if wave_col is None or response_col is None:
        raise RuntimeError(f"Could not identify wavelength/response columns for {request.svo_filter_id}")

    wavelength = np.asarray(table[wave_col], dtype=float)
    response_values = np.asarray(table[response_col], dtype=float)
    wavelength = convert_wavelength_to_angstrom(wavelength, str(getattr(table[wave_col], "unit", "") or ""))
    clean = np.isfinite(wavelength) & np.isfinite(response_values)
    wavelength = wavelength[clean]
    response_values = np.clip(response_values[clean], 0.0, None)
    order = np.argsort(wavelength)
    wavelength = wavelength[order]
    response_values = response_values[order]
    if wavelength.size < 2:
        raise RuntimeError(f"SVO returned fewer than two profile points for {request.svo_filter_id}")
    integral = float(np.trapz(response_values, wavelength))
    if math.isfinite(integral) and integral > 0:
        response_values = response_values / integral
    average, lo, hi = profile_stats(wavelength, response_values)
    average = extract_wavelength_param_angstrom(params, "WavelengthMean") or average
    return FilterProfile(
        request=request,
        wavelength_angstrom=wavelength,
        response=response_values,
        average_wavelength=average,
        min_wavelength=lo,
        max_wavelength=hi,
        zeropoint_jy=extract_zeropoint_jy(params),
        params=params,
    )


def votable_params(votable) -> dict[str, str]:
    out: dict[str, str] = {}
    for param in getattr(votable, "params", []) or []:
        key = str(getattr(param, "name", None) or getattr(param, "ID", None) or "").strip()
        value = str(getattr(param, "value", "") or "").strip()
        unit = str(getattr(param, "unit", "") or "").strip()
        if key:
            out[key] = value
            if unit:
                out[f"{key}__unit"] = unit
    return out


def find_column(names: Iterable[str], needles: tuple[str, ...]) -> str | None:
    lower = [(name, name.lower()) for name in names]
    for needle in needles:
        for original, normalized in lower:
            if needle in normalized:
                return original
    return None


def convert_wavelength_to_angstrom(values: np.ndarray, unit: str) -> np.ndarray:
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {"", "angstrom", "aa", "a"}:
        return values.astype(float)
    if normalized in {"nm", "nanometer", "nanometers"}:
        return values.astype(float) * 10.0
    if normalized in {"um", "micron", "microns", "micrometer", "micrometers"}:
        return values.astype(float) * 10000.0
    if normalized in {"m", "meter", "meters"}:
        return values.astype(float) * 1e10
    return values.astype(float)


def profile_stats(wavelength: np.ndarray, response: np.ndarray) -> tuple[float | None, float | None, float | None]:
    area_segments = 0.5 * (response[1:] + response[:-1]) * np.diff(wavelength)
    area_segments = np.where(np.isfinite(area_segments) & (area_segments > 0), area_segments, 0.0)
    cumulative = np.concatenate([[0.0], np.cumsum(area_segments)])
    total = float(cumulative[-1])
    if not math.isfinite(total) or total <= 0:
        return None, float(np.nanmin(wavelength)), float(np.nanmax(wavelength))
    average = float(np.trapz(wavelength * response, wavelength) / total)
    lo = float(np.interp(0.05 * total, cumulative, wavelength))
    hi = float(np.interp(0.95 * total, cumulative, wavelength))
    return average, lo, hi


def extract_zeropoint_jy(params: dict[str, str]) -> float | None:
    for key, value in params.items():
        low_key = key.lower()
        if "__unit" in low_key:
            continue
        if "zero" not in low_key and "zp" not in low_key:
            continue
        unit = params.get(f"{key}__unit", "")
        if "jy" not in unit.lower() and "jansky" not in unit.lower():
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed) and parsed > 0:
            return parsed
    return None


def extract_wavelength_param_angstrom(params: dict[str, str], key: str) -> float | None:
    try:
        value = float(params.get(key, ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    unit = params.get(f"{key}__unit", "")
    converted = convert_wavelength_to_angstrom(np.asarray([value], dtype=float), unit)
    parsed = float(converted[0])
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def sql_float(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "NULL"
    return f"{float(value):.12g}"


def sql_values_chunk(profile: FilterProfile, start: int, stop: int) -> list[str]:
    psid_sql = sql_string(profile.request.moca_psid)
    rows: list[str] = []
    for wavelength, response in zip(
        profile.wavelength_angstrom[start:stop],
        profile.response[start:stop],
        strict=False,
    ):
        rows.append(
            f"  ({psid_sql}, {sql_float(float(wavelength))}, {sql_float(float(response))})"
        )
    return rows


def write_sql(profiles: list[FilterProfile], nrows: int, skip_zeropoints: set[str] | None = None) -> str:
    skip_zeropoints = skip_zeropoints or set()
    lines: list[str] = []
    lines.append("-- Review before applying to mocadb_private_tables.")
    lines.append("-- Generated by scripts/stage_svo_filter_bandpasses.py.")
    lines.append("-- Existing bandpass rows are not deleted or replaced.")
    lines.append("-- Zeropoint updates fill NULL values only; non-NULL differences are surfaced by audit SELECTs.")
    lines.append("")
    for profile in profiles:
        request = profile.request
        staged_zeropoint = None if request.moca_psid in skip_zeropoints else profile.zeropoint_jy
        lines.append(f"-- {request.moca_psid} from SVO {request.svo_filter_id}")
        lines.append(f"-- n_profile_rows={profile.wavelength_angstrom.size}")
        lines.append(
            "-- stats: "
            f"average={sql_float(profile.average_wavelength)} A, "
            f"cdf05={sql_float(profile.min_wavelength)} A, "
            f"cdf95={sql_float(profile.max_wavelength)} A, "
            f"zeropoint_jy={sql_float(staged_zeropoint)}"
        )
        if request.moca_psid in skip_zeropoints:
            lines.append("-- zeropoint_jy staging skipped for this filter.")
        for index in range(min(max(0, nrows), profile.wavelength_angstrom.size)):
            lines.append(
                "-- sample "
                f"{index + 1}: wavelength_angstrom={profile.wavelength_angstrom[index]:.8g}, "
                f"relative_spectral_response={profile.response[index]:.8g}"
            )
        psid_sql = sql_string(request.moca_psid)
        lines.append("")
        lines.append("SELECT")
        lines.append(f"  {psid_sql} AS `moca_psid`,")
        lines.append("  ps.`average_wavelength` AS `current_average_wavelength`,")
        lines.append(f"  {sql_float(profile.average_wavelength)} AS `proposed_average_wavelength`,")
        lines.append("  ps.`min_wavelength` AS `current_min_wavelength`,")
        lines.append(f"  {sql_float(profile.min_wavelength)} AS `proposed_min_wavelength`,")
        lines.append("  ps.`max_wavelength` AS `current_max_wavelength`,")
        lines.append(f"  {sql_float(profile.max_wavelength)} AS `proposed_max_wavelength`")
        lines.append("FROM `moca_photometry_systems` ps")
        lines.append(f"WHERE ps.`moca_psid` = {psid_sql}")
        lines.append("  AND (")
        lines.append(f"    (ps.`average_wavelength` IS NOT NULL AND {sql_float(profile.average_wavelength)} IS NOT NULL AND ABS(ps.`average_wavelength` - {sql_float(profile.average_wavelength)}) > 1e-6)")
        lines.append(f"    OR (ps.`min_wavelength` IS NOT NULL AND {sql_float(profile.min_wavelength)} IS NOT NULL AND ABS(ps.`min_wavelength` - {sql_float(profile.min_wavelength)}) > 1e-6)")
        lines.append(f"    OR (ps.`max_wavelength` IS NOT NULL AND {sql_float(profile.max_wavelength)} IS NOT NULL AND ABS(ps.`max_wavelength` - {sql_float(profile.max_wavelength)}) > 1e-6)")
        lines.append("  );")
        lines.append("")
        lines.append("SELECT")
        lines.append(f"  {psid_sql} AS `moca_psid`,")
        lines.append("  ps.`zeropoint_jansky` AS `current_zeropoint_jansky`,")
        lines.append(f"  {sql_float(staged_zeropoint)} AS `proposed_zeropoint_jansky`")
        lines.append("FROM `moca_photometry_systems` ps")
        lines.append(f"WHERE ps.`moca_psid` = {psid_sql}")
        lines.append("  AND ps.`zeropoint_jansky` IS NOT NULL")
        lines.append(f"  AND {sql_float(staged_zeropoint)} IS NOT NULL")
        lines.append(f"  AND ABS(ps.`zeropoint_jansky` - {sql_float(staged_zeropoint)}) > 1e-9;")
        lines.append("")
        lines.append("UPDATE `moca_photometry_systems`")
        lines.append("SET")
        lines.append(f"  `average_wavelength` = COALESCE(`average_wavelength`, {sql_float(profile.average_wavelength)}),")
        lines.append(f"  `min_wavelength` = COALESCE(`min_wavelength`, {sql_float(profile.min_wavelength)}),")
        lines.append(f"  `max_wavelength` = COALESCE(`max_wavelength`, {sql_float(profile.max_wavelength)}),")
        lines.append(f"  `zeropoint_jansky` = COALESCE(`zeropoint_jansky`, {sql_float(staged_zeropoint)}),")
        lines.append(
            "  `bandpass_file` = COALESCE("
            "`bandpass_file`, "
            f"{sql_string('SVO FPS ' + request.svo_filter_id)}"
            ")"
        )
        lines.append(f"WHERE `moca_psid` = {psid_sql};")
        lines.append("")
        lines.append("CREATE TEMPORARY TABLE IF NOT EXISTS `_mocaviz_svo_bandpass_stage` (")
        lines.append("  `moca_psid` varchar(128) NOT NULL,")
        lines.append("  `wavelength_angstrom` double NOT NULL,")
        lines.append("  `relative_spectral_response` double NOT NULL")
        lines.append(") ENGINE=Memory;")
        lines.append("DELETE FROM `_mocaviz_svo_bandpass_stage`;")
        chunk_size = 500
        for start in range(0, profile.wavelength_angstrom.size, chunk_size):
            stop = min(profile.wavelength_angstrom.size, start + chunk_size)
            value_rows = sql_values_chunk(profile, start, stop)
            if not value_rows:
                continue
            lines.append("INSERT INTO `_mocaviz_svo_bandpass_stage`")
            lines.append("  (`moca_psid`, `wavelength_angstrom`, `relative_spectral_response`)")
            lines.append("VALUES")
            lines.append(",\n".join(value_rows) + ";")
        lines.append("INSERT INTO `data_photometric_bandpasses`")
        lines.append("  (`moca_psid`, `wavelength_angstrom`, `relative_spectral_response`)")
        lines.append("SELECT")
        lines.append("  stage.`moca_psid`,")
        lines.append("  stage.`wavelength_angstrom`,")
        lines.append("  stage.`relative_spectral_response`")
        lines.append("FROM `_mocaviz_svo_bandpass_stage` stage")
        lines.append("WHERE NOT EXISTS (")
        lines.append("  SELECT 1")
        lines.append("  FROM `data_photometric_bandpasses` existing")
        lines.append(f"  WHERE existing.`moca_psid` = {psid_sql}")
        lines.append("  LIMIT 1")
        lines.append(")")
        lines.append("ORDER BY stage.`wavelength_angstrom`;")
        lines.append("DELETE FROM `_mocaviz_svo_bandpass_stage`;")
        lines.append("")
    lines.append("DROP TEMPORARY TABLE IF EXISTS `_mocaviz_svo_bandpass_stage`;")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    requests = load_requests(args)
    if not requests:
        raise SystemExit("No filters requested. Use --filter or --mapping-csv.")
    profiles = [fetch_svo_profile(request, args.timeout) for request in requests]
    sql = write_sql(profiles, args.nrows, set(args.skip_zeropoint or []))
    if args.output:
        Path(args.output).write_text(sql + "\n", encoding="utf-8")
    else:
        print(sql)


if __name__ == "__main__":
    main()
