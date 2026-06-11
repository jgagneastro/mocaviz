#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import math
import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text


DEFAULT_HOST = "104.248.106.21"
DEFAULT_USERNAME = "public"
DEFAULT_PASSWORD = "z@nUg_2h7_%?31y88"
DEFAULT_DBNAME = "mocadb"
DEFAULT_CSV = Path(
    "/Users/jonathan/Documents/Python/Python_Packages/diamondback_substellar_masses/moca_stitched.csv"
)
TRACK_NAME = "Sonora Diamondback extended with MOCAdb empirical tracks"
ORIGIN = "mocaviz/scripts/import_bd_evolution_tracks.py"
MSUN_TO_MJUP = 1047.5654817267318
RJUP_TO_RSUN = 0.10045
MODEL_MIN_AGE_MYR = 2.0
DATAVIZ_TOOL = "bd_evolution"

SEQUENCES = {
    "bde_sdb_moca_teff": {
        "axis": "teff_k",
        "csv_column": "Teff(K)",
        "yname": "Teff (K)",
        "tag": "Teff",
        "color": "#0072b2",
    },
    "bde_sdb_moca_mass": {
        "axis": "mass_mjup",
        "csv_column": "mass_mjup",
        "yname": "Mass (M_Jup)",
        "tag": "Mass",
        "color": "#d55e00",
    },
    "bde_sdb_moca_logg": {
        "axis": "logg",
        "csv_column": "log g",
        "yname": "log g (dex cgs)",
        "tag": "log g",
        "color": "#009e73",
    },
    "bde_sdb_moca_radius": {
        "axis": "radius_rsun",
        "csv_column": "radius_rsun",
        "yname": "Radius (R_sun)",
        "tag": "Radius",
        "color": "#cc79a7",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or upload the Brown Dwarf Evolution Explorer stitched tracks to MOCAdb."
    )
    parser.add_argument("--csv", type=Path, default=Path(os.environ.get("BD_EVOLUTION_TRACK_CSV", DEFAULT_CSV)))
    parser.add_argument("--apply", action="store_true", help="Write to MOCAdb. Without this flag, only a dry run is printed.")
    parser.add_argument("--nrows", type=int, default=3, help="Example rows per table to show in dry-run output.")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--is-public", type=int, choices=[0, 1], default=None)
    parser.add_argument("--rls", default=None)
    parser.add_argument("--host", default=os.environ.get("MOCA_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MOCA_PORT", "3306")))
    parser.add_argument("--user", default=os.environ.get("MOCA_USERNAME", DEFAULT_USERNAME))
    parser.add_argument("--password", default=os.environ.get("MOCA_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument("--database", default=os.environ.get("MOCA_DBNAME", DEFAULT_DBNAME))
    parser.add_argument("--skip-db-check", action="store_true", help="Do not query the target DB during dry run.")
    args = parser.parse_args()
    if args.apply and args.is_public is None:
        parser.error("--is-public is required with --apply so the RLS intent is explicit.")
    if args.apply and args.is_public == 0 and not args.rls:
        parser.error("--rls is required with --apply when --is-public 0.")
    if args.is_public is None:
        args.is_public = 1
    if not args.rls:
        args.rls = "public" if args.is_public == 1 else None
    if args.rls is None:
        parser.error("--rls is required when --is-public 0.")
    if args.is_public == 1 and args.rls != "public":
        parser.error("--rls must be public when --is-public 1.")
    return args


def connection_string(args: argparse.Namespace) -> str:
    password = quote_plus(str(args.password or ""))
    return f"mysql+pymysql://{args.user}:{password}@{args.host}:{args.port}/{args.database}"


def finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_stitched_tracks(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))
    df = pd.read_csv(csv_path)
    required = {"M/MSun", "age(Gyr)", "Teff(K)", "log g", "R/Rsun"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {csv_path}: {', '.join(sorted(missing))}")
    df = df.copy()
    df["age_myr"] = pd.to_numeric(df["age(Gyr)"], errors="coerce") * 1000.0
    df["mass_msun"] = pd.to_numeric(df["M/MSun"], errors="coerce")
    df["mass_mjup"] = df["mass_msun"] * MSUN_TO_MJUP
    df["Teff(K)"] = pd.to_numeric(df["Teff(K)"], errors="coerce")
    df["log g"] = pd.to_numeric(df["log g"], errors="coerce")
    df["R/Rsun"] = pd.to_numeric(df["R/Rsun"], errors="coerce")
    df["radius_rsun"] = df["R/Rsun"] * RJUP_TO_RSUN
    if "source" not in df.columns:
        df["source"] = "stitched"
    df = df.replace([float("inf"), float("-inf")], pd.NA)
    df = df.dropna(subset=["age_myr", "mass_mjup"])
    df = df[(df["age_myr"] >= MODEL_MIN_AGE_MYR) & (df["mass_mjup"] > 0)]
    return df.sort_values(["mass_mjup", "age_myr"]).reset_index(drop=True)


def max_grid_step(values: pd.Series) -> float | None:
    clean = sorted({float(value) for value in values.dropna().tolist() if finite(value) is not None})
    if len(clean) < 2:
        return None
    return max(b - a for a, b in zip(clean[:-1], clean[1:]))


def build_rows(df: pd.DataFrame, is_public: int, rls: str, csv_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    now = datetime.utcnow()
    date_text = now.date().isoformat()
    time_text = now.strftime("%H:%M:%S")
    source_comment = (
        f"{TRACK_NAME}; source CSV: {csv_path}; ages restricted to >= {MODEL_MIN_AGE_MYR:g} Myr; "
        "radii converted from R_Jup-scale CSV values to R_sun"
    )
    mass_min = float(df["mass_mjup"].min())
    mass_max = float(df["mass_mjup"].max())
    age_min = float(df["age_myr"].min())
    age_max = float(df["age_myr"].max())
    max_xbinsize = df.groupby("mass_mjup")["age_myr"].apply(max_grid_step).dropna().max()
    max_zbinsize = max_grid_step(df["mass_mjup"])

    sequence_rows: list[dict[str, Any]] = []
    data_rows: list[dict[str, Any]] = []
    dataviz_rows: list[dict[str, Any]] = []
    for seqid, config in SEQUENCES.items():
        y = pd.to_numeric(df[config["csv_column"]], errors="coerce")
        valid = df.loc[y.notna()].copy()
        y_valid = y.loc[y.notna()].astype(float)
        sequence_rows.append({
            "moca_seqid": seqid,
            "moca_pid": None,
            "xname": "Age (Myr)",
            "yname": config["yname"],
            "zname": "Mass (M_Jup)",
            "max_xbinsize": float(max_xbinsize) if finite(max_xbinsize) is not None else None,
            "max_zbinsize": float(max_zbinsize) if finite(max_zbinsize) is not None else None,
            "valid_xrange_min": age_min,
            "valid_xrange_max": age_max,
            "valid_yrange_min": float(y_valid.min()) if not y_valid.empty else None,
            "valid_yrange_max": float(y_valid.max()) if not y_valid.empty else None,
            "valid_zrange_min": mass_min,
            "valid_zrange_max": mass_max,
            "origin": ORIGIN,
            "date": date_text,
            "time": time_text,
            "comments": source_comment,
            "rls": rls,
            "display_in_bdcolapp": 0,
            "name_bdcolapp": TRACK_NAME,
            "is_public": is_public,
        })
        for row_index, (_, row) in enumerate(valid.iterrows()):
            ydata = row["mass_mjup"] if config["axis"] == "mass_mjup" else row[config["csv_column"]]
            data_rows.append({
                "moca_seqid": seqid,
                "xdata": float(row["age_myr"]),
                "xerror": None,
                "ydata": float(ydata),
                "yerror": None,
                "zdata": float(row["mass_mjup"]),
                "zerror": None,
                "origin": ORIGIN,
                "comments": str(row.get("source") or "stitched")[:255],
                "rls": rls,
                "is_public": is_public,
            })
        dataviz_rows.append({
            "dataviz_tool": DATAVIZ_TOOL,
            "moca_seqid": seqid,
            "moca_aid": None,
            "tag": f"{TRACK_NAME}: {config['tag']}",
            "display": 1,
            "color": config["color"],
            "width": 1.25,
            "style": "solid",
            "rls": rls,
            "is_public": is_public,
        })
    return sequence_rows, data_rows, dataviz_rows


def compact_example(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value is not None}


def print_examples(name: str, rows: list[dict[str, Any]], nrows: int) -> None:
    print(f"\n{name}: {len(rows):,} prepared row(s)")
    for index, row in enumerate(rows[: max(0, nrows)], start=1):
        print(f"  example {index}:")
        for key, value in compact_example(row).items():
            print(f"    {key}: {value}")


def in_clause(prefix: str, values: list[str]) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    parts: list[str] = []
    for index, value in enumerate(values):
        key = f"{prefix}_{index}"
        params[key] = value
        parts.append(f":{key}")
    return ", ".join(parts), params


def check_existing(engine, seqids: list[str]) -> None:
    clause, params = in_clause("seqid", seqids)
    with engine.connect() as conn:
        seq_rows = conn.execute(text(f"""
            SELECT moca_seqid, COUNT(*) AS n
            FROM moca_sequences
            WHERE moca_seqid IN ({clause})
            GROUP BY moca_seqid
            ORDER BY moca_seqid
        """), params).mappings().all()
        data_rows = conn.execute(text(f"""
            SELECT moca_seqid, COUNT(*) AS n
            FROM data_astro_sequences
            WHERE moca_seqid IN ({clause})
            GROUP BY moca_seqid
            ORDER BY moca_seqid
        """), params).mappings().all()
        dataviz_rows = conn.execute(text(f"""
            SELECT moca_seqid, COUNT(*) AS n
            FROM moca_dataviz_sequences
            WHERE dataviz_tool = :tool
                AND moca_seqid IN ({clause})
            GROUP BY moca_seqid
            ORDER BY moca_seqid
        """), {**params, "tool": DATAVIZ_TOOL}).mappings().all()
    print("\nExisting target rows:")
    print(f"  moca_sequences: {dict((row['moca_seqid'], row['n']) for row in seq_rows) or 'none'}")
    print(f"  data_astro_sequences: {dict((row['moca_seqid'], row['n']) for row in data_rows) or 'none'}")
    print(f"  moca_dataviz_sequences: {dict((row['moca_seqid'], row['n']) for row in dataviz_rows) or 'none'}")


def execute_apply(engine, sequence_rows: list[dict[str, Any]], data_rows: list[dict[str, Any]], dataviz_rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    seqids = [row["moca_seqid"] for row in sequence_rows]
    clause, params = in_clause("seqid", seqids)
    sequence_sql = text("""
        INSERT INTO moca_sequences (
            moca_seqid, moca_pid, xname, yname, zname, max_xbinsize, max_zbinsize,
            valid_xrange_min, valid_xrange_max, valid_yrange_min, valid_yrange_max,
            valid_zrange_min, valid_zrange_max, origin, `date`, `time`, comments,
            rls, display_in_bdcolapp, name_bdcolapp, is_public
        )
        VALUES (
            :moca_seqid, :moca_pid, :xname, :yname, :zname, :max_xbinsize, :max_zbinsize,
            :valid_xrange_min, :valid_xrange_max, :valid_yrange_min, :valid_yrange_max,
            :valid_zrange_min, :valid_zrange_max, :origin, :date, :time, :comments,
            :rls, :display_in_bdcolapp, :name_bdcolapp, :is_public
        )
        ON DUPLICATE KEY UPDATE
            moca_pid = VALUES(moca_pid),
            xname = VALUES(xname),
            yname = VALUES(yname),
            zname = VALUES(zname),
            max_xbinsize = VALUES(max_xbinsize),
            max_zbinsize = VALUES(max_zbinsize),
            valid_xrange_min = VALUES(valid_xrange_min),
            valid_xrange_max = VALUES(valid_xrange_max),
            valid_yrange_min = VALUES(valid_yrange_min),
            valid_yrange_max = VALUES(valid_yrange_max),
            valid_zrange_min = VALUES(valid_zrange_min),
            valid_zrange_max = VALUES(valid_zrange_max),
            origin = VALUES(origin),
            `date` = VALUES(`date`),
            `time` = VALUES(`time`),
            comments = VALUES(comments),
            rls = VALUES(rls),
            display_in_bdcolapp = VALUES(display_in_bdcolapp),
            name_bdcolapp = VALUES(name_bdcolapp),
            is_public = VALUES(is_public)
    """)
    data_sql = text("""
        INSERT INTO data_astro_sequences (
            moca_seqid, xdata, xerror, ydata, yerror, zdata, zerror,
            origin, comments, rls, is_public
        )
        VALUES (
            :moca_seqid, :xdata, :xerror, :ydata, :yerror, :zdata, :zerror,
            :origin, :comments, :rls, :is_public
        )
    """)
    dataviz_sql = text("""
        INSERT INTO moca_dataviz_sequences (
            dataviz_tool, moca_seqid, moca_aid, tag, display, color, width,
            style, rls, is_public
        )
        VALUES (
            :dataviz_tool, :moca_seqid, :moca_aid, :tag, :display, :color, :width,
            :style, :rls, :is_public
        )
    """)
    changelog_sql = text("""
        INSERT INTO moca_changelog (
            `user`, machine_name, modified_tables, nrows_modified,
            user_description, rls, is_public
        )
        VALUES (
            :user, :machine_name, :modified_tables, :nrows_modified,
            :user_description, :rls, :is_public
        )
    """)
    with engine.begin() as conn:
        conn.execute(sequence_sql, sequence_rows)
        conn.execute(text(f"DELETE FROM data_astro_sequences WHERE moca_seqid IN ({clause})"), params)
        for start in range(0, len(data_rows), args.batch_size):
            conn.execute(data_sql, data_rows[start:start + args.batch_size])
        conn.execute(text(f"""
            DELETE FROM moca_dataviz_sequences
            WHERE dataviz_tool = :tool
                AND moca_seqid IN ({clause})
        """), {**params, "tool": DATAVIZ_TOOL})
        conn.execute(dataviz_sql, dataviz_rows)
        conn.execute(changelog_sql, {
            "user": getpass.getuser(),
            "machine_name": socket.gethostname(),
            "modified_tables": "moca_sequences,data_astro_sequences,moca_dataviz_sequences",
            "nrows_modified": len(sequence_rows) + len(data_rows) + len(dataviz_rows),
            "user_description": f"Refreshed {TRACK_NAME} for the Brown Dwarf Evolution Explorer.",
            "rls": args.rls,
            "is_public": args.is_public,
        })


def main() -> None:
    args = parse_args()
    df = load_stitched_tracks(args.csv)
    sequence_rows, data_rows, dataviz_rows = build_rows(df, args.is_public, args.rls, args.csv)
    print(f"Input CSV: {args.csv}")
    print(f"Input stitched rows: {len(df):,}")
    print(f"Track name: {TRACK_NAME}")
    print(f"is_public: {args.is_public}; rls: {args.rls}")
    print("Refresh behavior: existing data_astro_sequences and bd_evolution dataviz rows for these sequence IDs will be replaced on --apply.")
    print_examples("moca_sequences", sequence_rows, args.nrows)
    print_examples("data_astro_sequences", data_rows, args.nrows)
    print_examples("moca_dataviz_sequences", dataviz_rows, args.nrows)

    engine = None
    if args.apply or not args.skip_db_check:
        try:
            engine = create_engine(connection_string(args), pool_pre_ping=True, pool_recycle=1800)
            check_existing(engine, [row["moca_seqid"] for row in sequence_rows])
        except Exception as exc:
            if args.apply:
                raise
            print(f"\nExisting target rows: unavailable ({type(exc).__name__}: {exc})")

    if not args.apply:
        print("\nDry run only. Re-run with --apply --is-public 1 to write public rows, or --apply --is-public 0 --rls <value> for private rows.")
        return
    if engine is None:
        engine = create_engine(connection_string(args), pool_pre_ping=True, pool_recycle=1800)
    execute_apply(engine, sequence_rows, data_rows, dataviz_rows, args)
    print(f"\nApplied {len(sequence_rows):,} sequence headers, {len(data_rows):,} sequence data rows, and {len(dataviz_rows):,} dataviz rows.")


if __name__ == "__main__":
    main()
