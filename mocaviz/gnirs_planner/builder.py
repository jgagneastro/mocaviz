"""Paged read-only MOCAdb refresh into the existing single cache file."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import time
import uuid

from .assemble import assemble
from .cache import (
    FORMAT_VERSION, get, metadata, progress, put, reader, release_rebuild, writer,
)
from .schema import SCHEMA, create_indexes, records
from .visibility import summaries, unpack

QUERIES = Path(__file__).with_name("queries")
POSITION_KEYS = ("ra", "dec", "measurement_epoch_yr", "pmra_masyr", "pmdec_masyr", "coord_frame")


def publish(db, meta):
    """One SQLite transaction publishes the candidate and releases old pages."""
    count = db.execute("SELECT count(*) FROM staging_targets").fetchone()[0]
    if count != meta["manifest"]["target_count"]:
        raise ValueError("Catalog count did not match the parent selection")
    # Readers hold read transactions; SQLite serializes this publication with them.
    db.execute("DROP TABLE IF EXISTS targets")
    db.execute("ALTER TABLE staging_targets RENAME TO targets")
    create_indexes(db)
    meta.update(
        cache_format=FORMAT_VERSION, catalog_count=count, catalog_complete=True,
        revision=uuid.uuid4().hex, built_at=datetime.now(timezone.utc).isoformat(),
        associations=[r[0] for r in db.execute("SELECT DISTINCT aid FROM targets ORDER BY aid")],
        observables=[r[0] for r in db.execute("SELECT DISTINCT obs FROM targets ORDER BY obs")],
    )
    put(db, "catalog", meta)
    put(db, "revision", meta["revision"])
    put(db, "rebuild", {"phase": "complete", "message": f"Updated catalog: {count:,} objects.", "updated_at": time.time()})


def rebuild(path, auth, lock_fd, connection):
    """Credentials live only for this operation; no subprocess or persisted job."""
    try:
        meta = metadata(path)
        config = meta["semester"]
        with writer(path, lease=lock_fd) as db:
            db.execute("DROP TABLE IF EXISTS staging_targets")
            db.execute(SCHEMA.replace("targets", "staging_targets", 1))
        with connection(auth) as cur:
            # Only SELECTs run on MOCAdb. Use one consistent read snapshot.
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY")
            cur.execute("SELECT DISTINCT o.moca_oid FROM moca_objects o JOIN data_spectral_types s "
                        "ON s.moca_oid=o.moca_oid AND s.adopted=1 AND s.ignored=0 "
                        "WHERE o.ignored=0 AND s.spectral_type_number>=5 ORDER BY o.moca_oid")
            ids = [int(r["moca_oid"]) for r in cur.fetchall()]
            if not ids:
                raise ValueError("Empty parent catalog")
            cur.execute((QUERIES / "association_distances.sql").read_text())
            association_distances = clean_rows(cur.fetchall())
            for start in range(0, len(ids), 1000):
                group = ids[start:start + 1000]
                progress(path, "collecting", f"Reading objects {start + 1:,}–{start + len(group):,} of {len(ids):,}.", lease=lock_fd)
                id_list = ",".join(map(str, group))
                raw = {"association_distances": association_distances}
                for name in ("targets", "radial_velocities", "combined_rvs", "photometry", "spectra", "companions", "spiff_vetting"):
                    sql = (QUERIES / (name + ".sql")).read_text().replace("__OIDS__", id_list)
                    cur.execute(sql)
                    raw[name] = clean_rows(cur.fetchall())
                with reader(path) as db:
                    previous = {}
                    for offset in range(0, len(group), 500):
                        chunk = group[offset:offset + 500]
                        for item in db.execute("SELECT oid,payload,visibility FROM targets WHERE oid IN (" + ",".join("?" for _ in chunk) + ")", chunk):
                            previous[item["oid"]] = {**unpack(item["payload"]), "visibility": unpack(item["visibility"])}
                rows = assemble(raw, meta, previous)
                missing = []
                for row in rows:
                    prior = previous.get(row["moca_oid"], {})
                    if prior and all(row.get(k) == prior.get(k) for k in POSITION_KEYS):
                        row["visibility"] = prior["visibility"]
                    else:
                        missing.append(row)
                progress(path, "building", f"Assembling objects {start + 1:,}–{start + len(group):,} of {len(ids):,}.", lease=lock_fd)
                for offset in range(0, len(missing), 128):
                    batch = missing[offset:offset + 128]
                    for row, (summary, _) in zip(batch, summaries(batch, config)):
                        row["visibility"] = summary
                packed = records(rows)
                if packed:
                    with writer(path, lease=lock_fd) as db:
                        db.executemany("INSERT INTO staging_targets VALUES (" + ",".join("?" for _ in packed[0]) + ")", packed)
            meta["manifest"] = {
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "target_count": len(ids), "all_photometric": True, "spt_min": 5,
                "parent_scope": "All active adopted spectroscopic and photometric M5+ MOCAdb objects.",
            }
            meta["source_hashes"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in QUERIES.glob("*.sql")}
        progress(path, "publishing", "Publishing the shared catalog.", lease=lock_fd)
        with writer(path, lease=lock_fd) as db:
            publish(db, meta)
    except BaseException:
        # Never record exception text: a DB driver may include connection secrets.
        try:
            with writer(path, lease=lock_fd) as db:
                db.execute("DROP TABLE IF EXISTS staging_targets")
                put(db, "rebuild", {"phase": "error", "message": "Regeneration failed; the previous complete catalog was retained.", "updated_at": time.time()})
        except BaseException:
            pass
    finally:
        auth.clear()
        release_rebuild(lock_fd)


def clean_rows(rows):
    from decimal import Decimal
    from datetime import date, datetime
    def clean(value):
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value
    return [{k: clean(v) for k, v in row.items()} for row in rows]
