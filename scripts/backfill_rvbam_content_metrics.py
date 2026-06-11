#!/usr/bin/env python3
"""Backfill persisted RVBAM RV-content metrics in MOCAdb.

This script reuses the RV-content diagnostic code from bd_colors_fast.app so
the stored values match the current RVBAM explorer definitions.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from bd_colors_fast import app as mocaviz_app  # noqa: E402


METHOD = "rvbam.segment_rv_content"
VERSION = "v1-mocaviz-20260611"
REQUIRED_COLUMNS = (
    *mocaviz_app.RVBAM_RV_CONTENT_METRIC_COLUMNS,
    *mocaviz_app.RVBAM_RV_CONTENT_PROVENANCE_COLUMNS,
)
UPDATE_COLUMNS = (
    "data_contrast",
    "model_contrast",
    "nmodel_10p_contrast",
    "noutliers_masked",
    "segment_snr_median",
    "segment_snr_p10",
    "segment_snr_p90",
    "segment_snr_npoints",
    "rv_content_method",
    "rv_content_version",
    "rv_content_status",
    "rv_content_error",
)


@dataclass
class DbConfig:
    host: str
    user: str
    password: str
    database: str
    port: int
    ssl_insecure: bool


def env_value(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or str(value).strip() == "":
        return default
    return value


def load_db_config(args: argparse.Namespace) -> DbConfig:
    host = args.host or env_value("MOCA_HOST", mocaviz_app.DEFAULT_HOST) or mocaviz_app.DEFAULT_HOST
    user = args.user or env_value("MOCA_USERNAME", mocaviz_app.DEFAULT_USERNAME) or mocaviz_app.DEFAULT_USERNAME
    password = args.pwd or env_value("MOCA_PASSWORD", mocaviz_app.DEFAULT_PASSWORD) or mocaviz_app.DEFAULT_PASSWORD
    database = args.dbase or env_value("MOCA_DBNAME", "mocadb_private_tables") or "mocadb_private_tables"
    port = int(args.port or env_value("MOCA_PORT", "3306") or "3306")
    ssl_insecure = bool(args.ssl_insecure or env_value("MOCA_SSL_INSECURE", "") in {"1", "true", "yes"})
    if host == "173.209.56.106":
        ssl_insecure = True
    return DbConfig(host=host, user=user, password=password, database=database, port=port, ssl_insecure=ssl_insecure)


def make_engine(cfg: DbConfig):
    if cfg.user.strip().lower() == "public":
        raise SystemExit("Refusing to write with the public MOCAdb user.")
    if cfg.database.strip("`").lower() != "mocadb_private_tables":
        raise SystemExit(f"Refusing to write to non-private database {cfg.database!r}.")
    password = quote_plus(cfg.password)
    url = f"mysql+pymysql://{cfg.user}:{password}@{cfg.host}:{cfg.port}/{cfg.database}"
    connect_args: dict[str, Any] = {}
    if cfg.ssl_insecure:
        connect_args["ssl"] = {"verify_mode": False, "check_hostname": False}
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, connect_args=connect_args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--pwd", default=None)
    parser.add_argument("--dbase", default=None)
    parser.add_argument("--port", default=None)
    parser.add_argument("--ssl-insecure", action="store_true")
    parser.add_argument("--commit", action="store_true", help="Write updates. Default is dry run.")
    parser.add_argument("--force", action="store_true", help="Recompute rows even when all metrics are already present.")
    parser.add_argument("--exclude-ignored", action="store_true", help="Skip ignored RVBAM segments.")
    parser.add_argument("--run-id", type=int, action="append", default=[], help="Limit to one moca_rv_sample_run_id; repeatable.")
    parser.add_argument("--specid", type=int, default=None, help="Limit to one moca_specid.")
    parser.add_argument("--oid", type=int, default=None, help="Limit to one moca_oid.")
    parser.add_argument("--pipeline-version", default=None, help="Limit to one RVBAM pipeline_version.")
    parser.add_argument("--mgridid", default=None, help="Limit to one moca_mgridid.")
    parser.add_argument("--limit-runs", type=int, default=None, help="Maximum number of RVBAM runs to process.")
    parser.add_argument("--limit-segments", type=int, default=None, help="Maximum number of segments to update.")
    parser.add_argument("--batch-size", type=int, default=100, help="Rows per UPDATE transaction.")
    parser.add_argument("--nrows", type=int, default=3, help="Number of example rows to print.")
    parser.add_argument("--progress-every", type=int, default=10, help="Print progress every N runs.")
    parser.add_argument("--count-only", action="store_true", help="Only count candidate runs; do not compute metrics.")
    parser.add_argument("--list-runs", action="store_true", help="Print candidate run IDs before processing.")
    parser.add_argument("--summary", action="store_true", help="Print stored metric summary counts for this method/version.")
    return parser.parse_args()


def existing_columns(conn) -> set[str]:
    rows = conn.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'pcat_rv_sampling_segments'
    """)).fetchall()
    return {str(row[0]) for row in rows}


def validate_schema(conn) -> None:
    columns = existing_columns(conn)
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise SystemExit("Missing required pcat_rv_sampling_segments columns: " + ", ".join(missing))


def candidate_run_rows(conn, args: argparse.Namespace) -> list[dict[str, Any]]:
    clauses = ["1 = 1"]
    params: dict[str, Any] = {}
    if not args.force:
        params["rv_content_method"] = METHOD
        params["rv_content_version"] = VERSION
        clauses.append("""
            EXISTS (
                SELECT 1
                FROM pcat_rv_sampling_segments s
                WHERE s.moca_rv_sample_run_id = r.moca_rv_sample_run_id
                  AND (
                    s.rv_content_status IS NULL
                    OR s.rv_content_method IS NULL
                    OR s.rv_content_method <> :rv_content_method
                    OR s.rv_content_version IS NULL
                    OR s.rv_content_version <> :rv_content_version
                    OR s.rv_content_computed_timestamp IS NULL
                  )
            )
        """)
    if args.exclude_ignored:
        clauses.append("COALESCE(r.ignored, 0) = 0")
    if args.run_id:
        placeholders = []
        for index, run_id in enumerate(args.run_id):
            key = f"run_id_{index}"
            placeholders.append(f":{key}")
            params[key] = int(run_id)
        clauses.append(f"r.moca_rv_sample_run_id IN ({', '.join(placeholders)})")
    if args.specid is not None:
        clauses.append("r.moca_specid = :specid")
        params["specid"] = int(args.specid)
    if args.oid is not None:
        clauses.append("r.moca_oid = :oid")
        params["oid"] = int(args.oid)
    if args.pipeline_version:
        clauses.append("r.pipeline_version = :pipeline_version")
        params["pipeline_version"] = str(args.pipeline_version)
    if args.mgridid:
        clauses.append("r.moca_mgridid = :mgridid")
        params["mgridid"] = str(args.mgridid)
    limit_sql = f"LIMIT {max(1, int(args.limit_runs))}" if args.limit_runs else ""
    sql = f"""
        SELECT
          r.*,
          ms.berv_corrected,
          ms.spacecraft_rv_corrected,
          ms.spectrum_name
        FROM pcat_rv_sampling_runs r
        LEFT JOIN moca_spectra ms
          ON ms.moca_specid = r.moca_specid
        WHERE {' AND '.join(clauses)}
        ORDER BY r.moca_rv_sample_run_id
        {limit_sql}
    """
    return mocaviz_app._records(mocaviz_app._read_sql(conn, sql, params))


def segment_rows_for_run(conn, run_id: int, args: argparse.Namespace) -> list[dict[str, Any]]:
    clauses = ["s.moca_rv_sample_run_id = :run_id"]
    params: dict[str, Any] = {"run_id": int(run_id)}
    if args.exclude_ignored:
        clauses.append("COALESCE(s.ignored, 0) = 0")
    if not args.force:
        params["rv_content_method"] = METHOD
        params["rv_content_version"] = VERSION
        clauses.append("""
            (
              s.rv_content_status IS NULL
              OR s.rv_content_method IS NULL
              OR s.rv_content_method <> :rv_content_method
              OR s.rv_content_version IS NULL
              OR s.rv_content_version <> :rv_content_version
              OR s.rv_content_computed_timestamp IS NULL
            )
        """)
    if args.limit_segments is not None:
        params["limit_segments"] = max(1, int(args.limit_segments))
        limit_sql = "LIMIT :limit_segments"
    else:
        limit_sql = ""
    return mocaviz_app._records(mocaviz_app._read_sql(conn, f"""
        SELECT
          s.*,
          sr.best_chi2,
          sr.pipeline_version AS sampling_pipeline_version
        FROM pcat_rv_sampling_segments s
        LEFT JOIN pcat_sampling_runs sr
          ON sr.moca_sample_run_id = s.moca_sample_run_id
        WHERE {' AND '.join(clauses)}
        ORDER BY s.order_number, s.window_number, s.segment_number, s.wv_min, s.moca_rv_sampling_segment_id
        {limit_sql}
    """, params))


def finite_or_none(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def status_for_segment(segment: dict[str, Any], meta: dict[str, Any]) -> tuple[str, str | None]:
    has_data = segment.get("segment_snr_median") is not None or segment.get("data_contrast") is not None
    has_model = segment.get("model_contrast") is not None or segment.get("nmodel_10p_contrast") is not None
    has_outliers = segment.get("noutliers_masked") is not None
    model_message = str(meta.get("model_message") or "").strip() or None
    if has_data and has_model and has_outliers:
        return "ok", None
    if has_data and not has_model:
        return "model_unavailable", model_message
    if has_data:
        return "observed_only", model_message
    return "data_unavailable", "No finite data_spectra points were found for this segment wavelength range."


def update_payload(segment: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    status, error = status_for_segment(segment, meta)
    payload: dict[str, Any] = {
        "moca_rv_sampling_segment_id": int(segment["moca_rv_sampling_segment_id"]),
        "rv_content_method": METHOD,
        "rv_content_version": VERSION,
        "rv_content_status": status,
        "rv_content_error": error[:2048] if error else None,
    }
    for column in mocaviz_app.RVBAM_RV_CONTENT_METRIC_COLUMNS:
        value = finite_or_none(segment.get(column))
        if column in {"nmodel_10p_contrast", "noutliers_masked", "segment_snr_npoints"} and value is not None:
            value = int(value)
        payload[column] = value
    return payload


def write_updates(engine, updates: list[dict[str, Any]], batch_size: int) -> int:
    if not updates:
        return 0
    stmt = text("""
        UPDATE pcat_rv_sampling_segments
        SET
          data_contrast = :data_contrast,
          model_contrast = :model_contrast,
          nmodel_10p_contrast = :nmodel_10p_contrast,
          noutliers_masked = :noutliers_masked,
          segment_snr_median = :segment_snr_median,
          segment_snr_p10 = :segment_snr_p10,
          segment_snr_p90 = :segment_snr_p90,
          segment_snr_npoints = :segment_snr_npoints,
          rv_content_method = :rv_content_method,
          rv_content_version = :rv_content_version,
          rv_content_computed_timestamp = UTC_TIMESTAMP(),
          rv_content_status = :rv_content_status,
          rv_content_error = :rv_content_error
        WHERE moca_rv_sampling_segment_id = :moca_rv_sampling_segment_id
    """)
    updated = 0
    batch_size = max(1, int(batch_size))
    for start in range(0, len(updates), batch_size):
        batch = updates[start:start + batch_size]
        with engine.begin() as conn:
            result = conn.execute(stmt, batch)
        updated += int(result.rowcount or 0)
    return updated


def print_examples(updates: list[dict[str, Any]], nrows: int) -> None:
    for row in updates[:max(0, int(nrows))]:
        print(
            "example "
            f"segment_id={row['moca_rv_sampling_segment_id']} "
            f"status={row['rv_content_status']} "
            f"data={row['data_contrast']} "
            f"model={row['model_contrast']} "
            f"n10p={row['nmodel_10p_contrast']} "
            f"snr={row['segment_snr_median']} "
            f"nout={row['noutliers_masked']}"
        )


def print_stored_summary(conn) -> None:
    rows = mocaviz_app._records(mocaviz_app._read_sql(conn, """
        SELECT
          rv_content_status,
          COUNT(*) AS n_segments,
          SUM(data_contrast IS NOT NULL) AS n_data_contrast,
          SUM(model_contrast IS NOT NULL) AS n_model_contrast,
          SUM(segment_snr_median IS NOT NULL) AS n_segment_snr,
          MIN(rv_content_computed_timestamp) AS first_computed,
          MAX(rv_content_computed_timestamp) AS latest_computed
        FROM pcat_rv_sampling_segments
        WHERE rv_content_method = :method
          AND rv_content_version = :version
        GROUP BY rv_content_status
        ORDER BY rv_content_status
    """, {"method": METHOD, "version": VERSION}))
    total = 0
    for row in rows:
        total += int(row.get("n_segments") or 0)
        print(
            "summary "
            f"status={row.get('rv_content_status')} "
            f"segments={row.get('n_segments')} "
            f"data={row.get('n_data_contrast')} "
            f"model={row.get('n_model_contrast')} "
            f"snr={row.get('n_segment_snr')} "
            f"first={row.get('first_computed')} "
            f"latest={row.get('latest_computed')}"
        )
    print(f"summary total_segments={total}")


def main() -> int:
    args = parse_args()
    cfg = load_db_config(args)
    mode = "COMMIT" if args.commit else "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"Target: {cfg.user}@{cfg.host}:{cfg.port}/{cfg.database}")
    engine = make_engine(cfg)
    started = time.time()
    all_updates: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    run_count = 0
    segment_count = 0
    updated_total = 0
    examples_printed = False
    errors: list[str] = []

    with engine.connect() as conn:
        validate_schema(conn)
        if args.summary:
            print_stored_summary(conn)
            if args.count_only:
                return 0
        runs = candidate_run_rows(conn, args)
        print(f"Candidate RVBAM runs: {len(runs)}")
        if args.list_runs:
            for run in runs:
                print(
                    "candidate "
                    f"run_id={run.get('moca_rv_sample_run_id')} "
                    f"oid={run.get('moca_oid')} "
                    f"specid={run.get('moca_specid')} "
                    f"pipeline={run.get('pipeline_version')} "
                    f"mgridid={run.get('moca_mgridid')} "
                    f"template={Path(str(run.get('template_name') or '')).name}"
                )
        if args.count_only:
            return 0
        if not runs:
            return 0
        for run_index, run in enumerate(runs, start=1):
            run_id = int(run["moca_rv_sample_run_id"])
            if args.limit_segments is not None and len(all_updates) >= int(args.limit_segments):
                break
            try:
                segments = segment_rows_for_run(conn, run_id, args)
                if args.limit_segments is not None:
                    remaining = max(0, int(args.limit_segments) - len(all_updates))
                    segments = segments[:remaining]
                if not segments:
                    continue
                run_count += 1
                segment_count += len(segments)
                meta = mocaviz_app._rvbam_enrich_segments_rv_content(conn, run, segments)
                updates = [update_payload(segment, meta) for segment in segments]
                for row in updates:
                    status = row["rv_content_status"]
                    status_counts[status] = status_counts.get(status, 0) + 1
                if not examples_printed:
                    print_examples(updates, args.nrows)
                    examples_printed = True
                if args.commit:
                    updated_total += write_updates(engine, updates, args.batch_size)
                else:
                    all_updates.extend(updates)
            except Exception as exc:
                message = f"run_id={run_id}: {type(exc).__name__}: {exc}"
                errors.append(message)
                print(f"ERROR {message}", flush=True)
            if args.progress_every and run_index % max(1, int(args.progress_every)) == 0:
                elapsed = time.time() - started
                prepared_or_updated = updated_total if args.commit else len(all_updates)
                action_name = "updated" if args.commit else "pending_updates"
                print(
                    f"progress runs_seen={run_index}/{len(runs)} "
                    f"runs_with_segments={run_count} {action_name}={prepared_or_updated} "
                    f"elapsed_s={elapsed:.1f}",
                    flush=True,
                )

    prepared_or_updated = updated_total if args.commit else len(all_updates)
    final_label = "Rows updated" if args.commit else "Prepared updates"
    print(f"{final_label}: {prepared_or_updated} segments across {run_count} runs")
    print(f"Input segments examined: {segment_count}")
    print(f"Status counts: {status_counts}")
    if errors:
        print(f"Run errors: {len(errors)}")
        for message in errors[:10]:
            print(f"  {message}")

    if not args.commit:
        print("Dry run only; no rows updated. Re-run with --commit to write.")

    print(f"Elapsed seconds: {time.time() - started:.1f}")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
