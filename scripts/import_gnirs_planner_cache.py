#!/usr/bin/env python3
"""One-time offline packaging of the existing planner into ONE deployment file.

No credentials are read. No live network calls. Run on the development machine,
then install the output outside the web root with mode 0600 for the web worker.
"""
import argparse
from pathlib import Path
import json
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mocaviz.gnirs_planner.cache import acquire_rebuild, initialize, release_rebuild, writer
from mocaviz.gnirs_planner.builder import publish
from mocaviz.gnirs_planner.schema import SCHEMA
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Existing gnirs_target_selector directory")
    parser.add_argument("--output", type=Path, required=True, help="New private SQLite output; must not exist")
    args = parser.parse_args()
    source = args.source.resolve() / "cache"
    output = args.output.absolute()
    names = {"database": "catalog.sqlite", "metadata": "metadata.json"}
    if (source / "current.json").exists():
        names.update(json.loads((source / "current.json").read_text()))
    if any(Path(v).name != v for v in names.values()):
        raise ValueError("Invalid source cache pointer")
    meta = json.loads((source / names["metadata"]).read_text())
    meta["grid"] = json.loads((source / "rv_itc_20260924/grid.json").read_text())
    meta["sxd_grid"] = json.loads((source / "sxd_itc/grid.json").read_text())
    # Explicit allowlist: never ingest .auth.json, access.txt, env files, logs,
    # saved URLs, user filters, or arbitrary neighboring files.
    allowed = {"grid", "sxd_grid", "mass_tracks", "spectral_type_axis", "semester", "manifest", "built_at", "rv_definition", "visibility_method"}
    meta = {k: v for k, v in meta.items() if k in allowed}
    fd = acquire_rebuild(output, create=True)
    try:
        with writer(output, lease=fd) as dest:
            dest.execute(SCHEMA.replace("targets", "staging_targets", 1))
        src = sqlite3.connect((source / names["database"]).as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            count = src.execute("SELECT count(*) FROM targets").fetchone()[0]
            cursor = src.execute("SELECT * FROM targets ORDER BY oid")
            imported = 0
            while batch := cursor.fetchmany(2000):
                with writer(output, lease=fd) as dest:
                    dest.executemany("INSERT INTO staging_targets VALUES (" + ",".join("?" for _ in batch[0]) + ")", batch)
                imported += len(batch)
                if imported % 20000 == 0:
                    print(f"Imported {imported:,}/{count:,} objects into the shared cache", flush=True)
        finally:
            src.close()
        meta["manifest"]["target_count"] = count
        with writer(output, lease=fd) as dest:
            publish(dest, meta)
            if dest.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Cache integrity check failed")
        print(f"Ready: {output} ({output.stat().st_size / 1024**2:.1f} MiB; {count:,} objects)")
    finally:
        release_rebuild(fd)


if __name__ == "__main__":
    main()
