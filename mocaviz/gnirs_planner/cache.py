"""One private SQLite file, shared by users and WSGI workers.

Only explicit seeding/regeneration opens a writer. Journals, temporary SQL
tables and sorts stay in RAM. The rebuild lease lives inside the same SQLite file.
There are no per-user files, lock files, sidecars, history files or disk jobs.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid
from dataclasses import dataclass

from .visibility import pack, unpack

FORMAT_VERSION = 1


class CacheUnavailable(Exception):
    pass


def cache_path():
    raw = os.environ.get("MOCAVIZ_GNIRS_CACHE_FILE", "").strip()
    if not raw:
        raise CacheUnavailable("The server has no shared cache location configured (MOCAVIZ_GNIRS_CACHE_FILE). Regenerate catalog needs that location and the initial timing-calibration bundle; it cannot configure the server.")
    path = Path(raw).expanduser().absolute()
    # The cache contains private rows. Never make it a Flask static asset.
    static = Path(__file__).resolve().parents[1] / "static"
    try:
        path.resolve().relative_to(static.resolve())
    except ValueError:
        pass
    else:
        raise CacheUnavailable("The GNIRS cache must be outside the public static directory.")
    return path


@contextmanager
def reader(path):
    if not path.is_file():
        raise CacheUnavailable("The shared GNIRS cache needs its initial deployment import, including the RV/SXD timing grids. Regenerate catalog refreshes an initialized cache.")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def writer(path, initialize_file=False, lease=None, timeout=30):
    conn = sqlite3.connect(path, timeout=timeout)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=MEMORY")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-16384")
        conn.execute("PRAGMA synchronous=FULL")
        if initialize_file:
            conn.execute("PRAGMA auto_vacuum=FULL")
        # Python's sqlite3 does not begin a transaction for DDL. Explicit BEGIN is
        # essential so DROP/RENAME/index creation and metadata publish atomically.
        conn.execute("BEGIN IMMEDIATE")
        if lease is not None:
            held = get(conn, 'lease', {})
            if held.get('owner') != lease.owner or not lease_active(held):
                raise CacheUnavailable('The shared rebuild lease expired; restart regeneration.')
            put(conn, 'lease', {'owner': lease.owner, 'pid': os.getpid(), 'expires': time.time() + 300})
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


@dataclass(frozen=True)
class RebuildLease:
    path: Path
    owner: str


def lease_active(lease):
    if not lease or lease.get('expires', 0) <= time.time():
        return False
    try:
        os.kill(int(lease['pid']), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def acquire_rebuild(path, create=False):
    # CREATE EXCL is only for the administrator's first offline import.
    flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise CacheUnavailable("The configured cache is not a regular file.")
    finally:
        os.close(fd)
    if create:
        initialize(path)
    lease = RebuildLease(path, uuid.uuid4().hex)
    try:
        with writer(path, timeout=0) as db:
            if lease_active(get(db, 'lease')):
                return None
            put(db, 'lease', {'owner': lease.owner, 'pid': os.getpid(), 'expires': time.time() + 300})
    except sqlite3.OperationalError as exc:
        if 'locked' in str(exc):
            return None
        raise
    return lease


def release_rebuild(lease):
    with writer(lease.path) as db:
        if get(db, 'lease', {}).get('owner') == lease.owner:
            db.execute("DELETE FROM metadata WHERE key='lease'")


def initialize(path):
    with writer(path, initialize_file=True) as db:
        db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value BLOB NOT NULL)")


def put(db, key, value):
    db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, pack(value)))


def get(db, key, default=None):
    row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
    return unpack(row[0]) if row else default


def metadata(path):
    with reader(path) as db:
        result = get(db, "catalog")
    if not result or result.get("cache_format") != FORMAT_VERSION:
        raise CacheUnavailable("The shared GNIRS cache needs its initial deployment import, including the RV/SXD timing grids. Regenerate catalog refreshes an initialized cache.")
    return result


def revision(path):
    with reader(path) as db:
        return get(db, "revision")


def status(path):
    if not path.exists():
        return {"phase": "idle", "message": "Initial cache import is required."}
    with reader(path) as db:
        state = get(db, "rebuild", {"phase": "idle", "message": "No regeneration is running."})
    if state["phase"] in {"queued", "collecting", "building", "publishing"}:
        with reader(path) as db:
            active = lease_active(get(db, "lease"))
        if not active:
            return {"phase": "interrupted", "message": "The previous regeneration stopped; the published catalog is retained."}
    return state


def progress(path, phase, message, lease=None, **extra):
    with writer(path, lease=lease) as db:
        put(db, "rebuild", {"phase": phase, "message": message, "updated_at": time.time(), **extra})


def validate_ready(path):
    """Check startup prerequisites read-only, without scanning the full catalog."""
    try:
        meta = metadata(path)
        if not all((meta.get(key) or {}).get("rows") for key in ("grid", "sxd_grid")) or not meta.get("semester"):
            raise CacheUnavailable("The shared cache is missing its timing-calibration bundle. Import the initial deployment cache before starting the planner.")
        with reader(path) as db:
            db.execute("SELECT oid, payload, visibility FROM targets LIMIT 0")
            if not get(db, "revision"):
                raise CacheUnavailable("The shared cache has no published catalog. Import the initial deployment cache before starting the planner.")
    except sqlite3.DatabaseError:
        raise CacheUnavailable("The shared cache is not a readable initialized GNIRS database. Check the configured file or re-import the deployment cache.") from None
    return meta
