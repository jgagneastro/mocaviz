"""Private GNIRS planner: request credentials, one shared cache, browser plots."""
from contextlib import contextmanager
import csv
import gzip
import io
import json
import math
from pathlib import Path
import sys
import threading
from html import escape
from urllib.parse import urlsplit

sys.dont_write_bytecode = True

import numpy as np
import pymysql
from flask import Blueprint, Response, jsonify, request

from . import cache
from .builder import rebuild
from .catalog import Catalog
from .visibility import target_windows

planner = Blueprint("gnirs_planner", __name__)
STATIC = Path(__file__).resolve().parents[1] / "static" / "gnirs_planner"
PRIVATE_DB = "mocadb_private_tables"
MAX_BODY = 64 * 1024
_catalog = None
_catalog_lock = threading.Lock()


class AccessError(Exception):
    def __init__(self, message="Collaborator credentials are required.", status=403):
        super().__init__(message)
        self.status = status


def credentials():
    """Only explicit request values; never env, .env, files or cached engines."""
    def value(aliases, header):
        values = [v for key in aliases for v in request.args.getlist(key)]
        if header in request.headers:
            values.append(request.headers[header])
        if len(set(values)) > 1:
            raise AccessError("Conflicting credentials in the request.")
        return values[0] if values else ""
    user = value(("user", "username"), "X-MOCA-User")
    password = value(("pwd", "password"), "X-MOCA-Password")
    database = value(("dbase", "db", "database"), "X-MOCA-Database") or PRIVATE_DB
    if user not in {"collaborators", "management"} or not password or len(password) > 4096:
        raise AccessError()
    if database != PRIVATE_DB:
        raise AccessError("The GNIRS planner requires private collaborator access.")
    if any(v != "mocadb.ca" for v in request.args.getlist("host")) or any(v != "3306" for v in request.args.getlist("port")):
        raise AccessError("The GNIRS planner connects only to mocadb.ca.")
    return {"user": user, "password": password}


@contextmanager
def connection(auth):
    conn = None
    try:
        conn = pymysql.connect(
            host="mocadb.ca", port=3306, user=auth["user"], password=auth["password"],
            database=PRIVATE_DB, ssl={"verify_mode": False, "check_hostname": False},
            charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
            autocommit=False, connect_timeout=10, read_timeout=120, write_timeout=30,
        )
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_USER() AS authenticated_user FROM DUAL")
            row = cur.fetchone() or {}
            if str(row.get("authenticated_user", "")).split("@", 1)[0] != auth["user"]:
                raise AccessError("Database authentication did not match the requested account.")
            conn.rollback()
            yield cur
    finally:
        if conn is not None:
            try:
                conn.rollback()
            finally:
                conn.close()


def get_catalog(path):
    global _catalog
    revision = cache.revision(path)
    with _catalog_lock:
        if _catalog is None or _catalog.db_path != path or _catalog.revision != revision:
            _catalog = Catalog(path, cache.metadata(path))
        return _catalog


@planner.after_request
def private_response(response):
    # The calibrated grids are several MB. Compress transport in RAM without
    # caching authenticated HTTP responses or creating gzip files on disk.
    if response.mimetype == "application/json":
        response.vary.add("Accept-Encoding")
        if request.accept_encodings["gzip"] > 0 and "Content-Encoding" not in response.headers:
            body = response.get_data()
            if len(body) > 2048:
                compressed = gzip.compress(body, compresslevel=4, mtime=0)
                if len(compressed) < len(body):
                    response.set_data(compressed)
                    response.headers["Content-Encoding"] = "gzip"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'; object-src 'none'"
    )
    return response


@planner.get("/gnirs-planner")
@planner.get("/gnirs-planner/")
def page():
    try:
        auth = credentials()
        with connection(auth):
            pass
        return html_page("index.html")
    except AccessError:
        return html_page("login.html"), 403
    except pymysql.MySQLError:
        return html_page("login.html"), 403
    except Exception:
        # Do not let an unexpected driver error expose a credential-bearing URL
        # or connection details through Flask's exception logger/debugger.
        return Response("The private GNIRS planner is temporarily unavailable.", status=503)
    finally:
        if "auth" in locals():
            auth.clear()


def html_page(name):
    base = request.script_root + "/static/gnirs_planner"
    return Response((Path(__file__).with_name("templates") / name).read_text().replace("__ASSET_BASE__", escape(base, quote=True)), content_type="text/html; charset=utf-8")


def export_csv(catalog, job):
    out = io.StringIO()
    writer = csv.writer(out)
    columns = ["moca_oid", "designation", "spectral_type", "association", "individual_probability_percent", "summed_young_probability_percent", "age_myr", "distance_pc", "measured_rv", "rv_kms", "rv_unc_kms", "rv_provenance", "science_h", "program_h", "telescope_h", "visits", "best_airmass", "best_utc", "observing_mode", "condition_scenario", "slit_arcsec", "grating_lmm", "snr_goal", "snr_unit", "coverage_fraction", "timing_interval_um", "observing_band", "photometry_band", "magnitude", "template", "frames", "frame_seconds", "read_mode", "calibration_minutes_per_visit", "grid_version"]
    writer.writerow(columns)
    with cache.reader(catalog.db_path) as db:
        for s in job["stats"]:
            row = catalog.target(int(s["oid"]), job, db=db)
            rv = row["rv"] or {}
            v, t, f = row["visibility"], row["_timing"], job["filters"]
            values = [row["moca_oid"], row["designation"], row["spt"], row["moca_aid"], row["individual_prob"], row["summed_young_prob"], row["age_myr"], row["distance_pc"], row["has_rv"], rv.get("radial_velocity_kms"), rv.get("radial_velocity_kms_unc"), ";".join(filter(None, rv.get("references", []))), *[float(s[k]) / 3600 if math.isfinite(s[k]) else "" for k in ("science", "program", "telescope")], int(s["visits"]), v["best_airmass"], v["best_utc"]]
            values += [f["observingMode"], f["mode"], t["slit"], 32 if f["observingMode"] == "sxd" else 111, f["snr"], f["snrUnit"], f["coverageFraction"], json.dumps(t.get("timing_interval_um", t["wavelength_range_um"])), "jhk" if f["observingMode"] == "sxd" else t["band"], t.get("photometry_band", t["band"]), t["mag"], t["template_spt"], t.get("frames"), t.get("frame_seconds"), t.get("read_mode", "VERY_FAINT"), f["calibrationMinutes"], catalog.meta["sxd_grid" if f["observingMode"] == "sxd" else "grid"]["version"]]
            writer.writerow(["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value for value in values])
    return Response(out.getvalue(), content_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=gnirs_selection.csv"})


@planner.post("/api/gnirs/<operation>")
def api(operation):
    auth = None
    try:
        auth = credentials()
        if request.headers.get("Origin") and urlsplit(request.headers["Origin"]).netloc != request.host:
            raise AccessError("Use the planner from its own site.")
        if not request.is_json:
            raise AccessError("Provide a JSON request.", 415)
        raw = request.stream.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise AccessError("Planner request is too large.", 413)
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError()
        if operation not in {"meta", "data", "selection", "list", "target", "navigate", "export", "windows", "regenerate", "regenerate-itc"}:
            raise AccessError("Unknown planner operation.", 404)
        # Authenticate even when every byte of the response is already cached.
        with connection(auth):
            pass
        path = cache.cache_path()
        if operation == "regenerate":
            if body.get("action") == "start":
                cache.metadata(path)  # Require the initial imported calibration bundle.
                fd = cache.acquire_rebuild(path)
                if fd is not None:
                    try:
                        cache.progress(path, "queued", "Starting the shared catalog refresh.", lease=fd)
                        thread = threading.Thread(target=rebuild, args=(path, dict(auth), fd, connection), daemon=True)
                        thread.start()
                    except BaseException:
                        cache.release_rebuild(fd)
                        raise
                return jsonify(cache.status(path)), 202
            return jsonify(cache.status(path))
        if operation == "regenerate-itc":
            if body.get("action") == "start":
                raise AccessError("Timing grids are updated through the deployment cache import.", 409)
            return jsonify(phase="idle", message="Timing grids are included in the shared deployment cache.")
        catalog = get_catalog(path)
        if operation in {"meta", "data"}:
            # Timing stays on the server: do not download multi-configuration curves
            # into every browser or build per-user response files.
            browser_meta={**catalog.meta}
            for name in ('grid','sxd_grid'):
                if browser_meta.get(name):browser_meta[name]={**{k:v for k,v in browser_meta[name].items() if k not in ('rows','models')},'rows':[]}
            return jsonify(browser_meta)
        if operation == "windows":
            row = catalog.target(int(body["oid"]))
            return jsonify(target_windows(row, catalog.meta["semester"]) if row else {})
        filters = body.get("filters", {})
        if not isinstance(filters, dict):
            raise ValueError()
        with catalog.lock:
            key = catalog.start(filters)
            job = catalog.jobs[key]
        if body.get("id") and body["id"] != key:
            raise AccessError("The catalog changed. Use Reload cache to refresh the selection.", 409)
        if job["status"] != "complete":
            raise AccessError("The cached selection could not be calculated.", 503)
        if operation == "selection":
            result = {"id": key, "status": "complete", "scanned": job["scanned"], "result": job["result"]}
        elif operation == "list":
            query = str(body.get("q", "")).strip()
            if len(query) > 256:
                raise ValueError()
            result = catalog.listed(job, query, body.get("sort", "time"), max(0, int(body.get("offset", 0))), body.get("gnirs_only") == "1")
        elif operation == "target":
            result = catalog.target(int(body["oid"]), job)
        elif operation == "navigate":
            ids = job["stats"]["oid"][job["age_order"]]
            found = np.flatnonzero(ids == int(body.get("oid", 0)))
            index = max(0, min(len(ids) - 1, (int(found[0]) if len(found) else -1) + int(body.get("step", 1))))
            result = {"row": catalog.target(int(ids[index]), job) if len(ids) else None, "index": index, "count": len(ids)}
        else:
            result = export_csv(catalog, job)
        if cache.revision(path) != catalog.revision:
            raise AccessError("The catalog changed. Use Reload cache to refresh the selection.", 409)
        return result if isinstance(result, Response) else jsonify(result)
    except AccessError as exc:
        return jsonify(error=str(exc)), exc.status
    except pymysql.MySQLError:
        return jsonify(error="Could not authenticate with MOCAdb. Check the supplied credentials and try again."), 403
    except cache.CacheUnavailable as exc:
        return jsonify(error=str(exc)), 503
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
        return jsonify(error="Invalid planner request."), 400
    except Exception:
        # Never echo raw driver/SQL exceptions or request URLs into responses/logs.
        return jsonify(error="The planner could not complete this request."), 503
    finally:
        if auth is not None:
            auth.clear()
