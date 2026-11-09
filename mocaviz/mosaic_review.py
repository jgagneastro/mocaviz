"""Loopback-only MOSAIC proper-motion reviewer. Launched by Web Tools."""
from collections import OrderedDict
import argparse
from contextlib import contextmanager
from functools import lru_cache
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time
from uuid import UUID, uuid4

from flask import Flask, Response, abort, jsonify, request, send_from_directory
import pymysql
from pymysql.cursors import DictCursor

from .mosaic_review_fit import FIT_VERSION, calibration_metadata, fit_target

STATIC = Path(__file__).resolve().parent / "static"
app = Flask(__name__, static_folder=str(STATIC))
app.config["MAX_CONTENT_LENGTH"] = 16384
LOG = logging.getLogger(__name__)
TABLE = "pcat_mosaic_pm_vetting"
ORIGIN = "mocaviz_mosaic_pm_review"
SAMPLES = {
    "public_l0": None,
    "sublime2": "pcat_sublime_candidates_v2",
    "sublime1": "pcat_sublime_candidates",
    "catwise": "pcat_catwise2020_red_movers",
}
LANES = {
    55: "pcat_spherex_visual_vetting",
    62: "pcat_spherex_spiffstacker_visual_vetting",
    76: "pcat_spherex_sublimeaperture_visual_vetting",
}
PM_COLUMNS = """id,moca_oid,pmra_masyr,pmdec_masyr,pmra_masyr_unc,pmdec_masyr_unc,
                moca_pid,origin,mission_name,data_release,adopted,public_adopted"""
PLX_COLUMNS = """id,moca_oid,parallax_mas,parallax_mas_unc,
                 moca_pid,origin,mission_name,data_release,adopted,public_adopted"""
# Let the moca_oid index bound the per-target coordinate scan.
COORD_WHERE = """ignored=0 AND single_epoch=1 AND pm_corrected=0 AND plx_corrected=0
    AND point_of_view='earth' AND ra IS NOT NULL AND `dec` IS NOT NULL
    AND measurement_epoch_yr IS NOT NULL AND ra_unc_mas>0 AND dec_unc_mas>0
    AND ((calibration_method IS NOT NULL AND TRIM(calibration_method) NOT IN ('','none','null','nan'))
         OR (mission_name='2MASS' AND data_release='PSC'))"""
SAMPLE_TTL = 900
FIT_TTL = 3600
_SAMPLE_CACHE = {}
_CACHE_LOCK = threading.Lock()
_FITS = OrderedDict()
_SUMMARY = OrderedDict()


class ReviewError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@app.before_request
def local_only():
    if (request.remote_addr not in {"127.0.0.1", "::1"}
            or request.host.partition(":")[0] not in {"127.0.0.1", "localhost"}
            or any(name in request.headers for name in ("Forwarded", "X-Forwarded-For", "X-Forwarded-Host"))):
        abort(404)
    if request.method == "POST" and (not request.is_json or request.headers.get("Origin") != request.host_url.rstrip("/")):
        abort(403)


@app.after_request
def private_response(response):
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(ReviewError)
def review_error(error):
    return jsonify(error=str(error)), error.status


@app.errorhandler(pymysql.MySQLError)
def database_error(error):
    code = error.args[0] if error.args else None
    LOG.warning("MOSAIC review database error %s", code)
    return jsonify(error=f"MOCAdb request failed (code {code}). Reload to verify the review state."), 503


@contextmanager
def database(*, write=False):
    user = os.environ.get("MOCA_USERNAME")
    password = os.environ.get("MOCA_PASSWORD")
    if user != "management" or not password:
        raise ReviewError("Start MOSAIC from Web Tools with the management connection configured.", 403)
    connection = pymysql.connect(host="mocadb.ca", user=user, password=password,
        database="mocadb_private_tables", charset="utf8mb4", autocommit=False,
        ssl={"verify_mode": False, "check_hostname": False},
        connect_timeout=6, read_timeout=35, write_timeout=10, cursorclass=DictCursor)
    try:
        with connection.cursor() as cursor:
            cursor.execute("START TRANSACTION" if write else "START TRANSACTION READ ONLY")
            yield cursor
        if write:
            connection.commit()
    finally:
        connection.close()


def query(cursor, sql, params=()):
    cursor.execute(sql, params)
    return cursor.fetchall()


def one(cursor, sql, params=()):
    cursor.execute(sql, params)
    return cursor.fetchone()


def review_table_ready(cursor):
    return bool(one(cursor, """SELECT 1 FROM information_schema.TABLES
        WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s""", (TABLE,)))


def sample_sql(sample):
    if sample not in SAMPLES:
        raise ReviewError("Choose a listed review sample.")
    if sample == "public_l0":
        vetted_lanes = " OR ".join(
            f"(spectrum.moca_specpackid={pack} AND EXISTS (SELECT 1 FROM {table} v"
            " WHERE v.moca_oid=s.moca_oid AND v.classification='good'))"
            for pack, table in LANES.items())
        source = f"""SELECT s.moca_oid FROM data_spectral_types s
            JOIN moca_objects o ON o.moca_oid=s.moca_oid AND o.ignored=0
            LEFT JOIN moca_spectra spectrum ON spectrum.moca_specid=s.moca_specid AND spectrum.moca_oid=s.moca_oid
            WHERE s.public_adopted=1 AND s.is_public=1 AND s.ignored=0 AND s.spectral_type_number>=10
              AND (
                (COALESCE(s.moca_instid,'')<>'SPHEREx' AND COALESCE(s.mission_name,'')<>'SPHEREx'
                 AND COALESCE(spectrum.moca_instid,'')<>'SPHEREx'
                 AND COALESCE(spectrum.moca_specpackid,0) NOT IN (55,62,76)
                 AND LOWER(COALESCE(s.origin,'')) NOT REGEXP 'spherex|spiff|sublimeaperture'
                 AND LOWER(COALESCE(s.calculation_method,'')) NOT REGEXP 'spherex|spiff|sublimeaperture')
                OR (spectrum.ignored=0 AND ({vetted_lanes})
                    AND NOT EXISTS (SELECT 1 FROM moca_spectra newer WHERE newer.moca_oid=s.moca_oid
                     AND newer.moca_specpackid=spectrum.moca_specpackid AND newer.ignored=0
                     AND newer.moca_specid>spectrum.moca_specid))
              )"""
    else:
        source = f"""SELECT DISTINCT p.moca_oid FROM {SAMPLES[sample]} p
            JOIN moca_objects o ON o.moca_oid=p.moca_oid AND o.ignored=0"""
    # Defer the epoch lookup to the current object or a small comparison batch.
    # An unbounded cross-catalog eligibility scan can hold the entire sample open.
    return f"SELECT source.moca_oid FROM ({source}) source ORDER BY source.moca_oid"


def sample_oids(cursor, sample):
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _SAMPLE_CACHE.get(sample)
    if cached and now - cached[0] < SAMPLE_TTL:
        return cached[1]
    oids = [row["moca_oid"] for row in query(cursor, sample_sql(sample))]
    with _CACHE_LOCK:
        _SAMPLE_CACHE[sample] = now, oids
    return oids


def review_point(review):
    if not review:
        return None
    return {"oid": review["moca_oid"], "id": review["id"], "state": review["decision"],
            "dx": review["delta_pmra"], "dy": review["delta_pmdec"], "mode": review["fit_mode"],
            "properMotionId": review["proper_motion_id"]}


REVIEW_FIELDS = "id,moca_oid,decision,delta_pmra,delta_pmdec,fit_mode,proper_motion_id"


def current_review(cursor, oid, fields=REVIEW_FIELDS):
    return one(cursor, f"""SELECT {fields} FROM {TABLE}
        WHERE moca_oid=%s AND undone_at IS NULL ORDER BY id DESC LIMIT 1""", (oid,))


def latest_reviews(cursor):
    return query(cursor, f"""SELECT {', '.join('v.' + part for part in REVIEW_FIELDS.split(','))}
        FROM {TABLE} v JOIN (SELECT moca_oid, MAX(id) id FROM {TABLE} WHERE undone_at IS NULL
                            GROUP BY moca_oid) recent ON recent.id=v.id""")


def measurement_data(cursor, oids, *, detail=False):
    placeholders = ",".join(["%s"] * len(oids))
    chosen = "" if detail else "AND adopted=1"
    catalogs = {
        "pm": query(cursor, f"""SELECT {PM_COLUMNS} FROM data_proper_motions
            WHERE moca_oid IN ({placeholders}) AND ignored=0 {chosen}
            ORDER BY adopted DESC,public_adopted DESC,id DESC""", oids),
        "parallax": query(cursor, f"""SELECT {PLX_COLUMNS} FROM data_parallaxes
            WHERE moca_oid IN ({placeholders}) AND ignored=0 {chosen}
            ORDER BY adopted DESC,public_adopted DESC,id DESC""", oids),
    }
    payloads = {oid: {"target": {"moca_oid": oid}, "reference": {}, "rows": [], "pm": {}, "parallax": {},
                      "literature": {"pm": [], "parallax": []}} for oid in oids}
    for kind, catalog in catalogs.items():
        for row in catalog:
            payload = payloads[row["moca_oid"]]
            if row["adopted"]:
                payload[kind] = row
            payload["literature"][kind].append(row)
    if not detail:
        # An unreviewed point with no adopted PM cannot be shown in the difference plot.
        oids = tuple(oid for oid in oids if payloads[oid]["pm"])
        if not oids:
            return payloads
        placeholders = ",".join(["%s"] * len(oids))
    if detail:
        target = one(cursor, """SELECT moca_oid,COALESCE(designation,moca_designation) designation
                              FROM moca_objects WHERE moca_oid=%s AND ignored=0""", (oids[0],))
        if not target:
            raise ReviewError("This MOCAdb target is unavailable.", 404)
        payloads[oids[0]]["target"] = target
    # Only one catalog trip for the full coordinate block and the adopted references.
    rows = query(cursor, f"""SELECT id,moca_oid,ignored,ra,`dec`,ra_unc_mas,dec_unc_mas,
        measurement_epoch_yr,COALESCE(measurement_epoch_yr_unc,0) measurement_epoch_yr_unc,
        mission_name,data_release,moca_pid,moca_psid,calibration_method,origin,origin_table,airmass,
        single_epoch,pm_corrected,plx_corrected,point_of_view,adopt_as_reference,
        COALESCE(NULLIF(TRIM(CONCAT_WS(' ',NULLIF(TRIM(mission_name),''),NULLIF(TRIM(data_release),''))),''),moca_pid,'No mission') mission
        FROM data_equatorial_coordinates
        WHERE moca_oid IN ({placeholders}) AND (({COORD_WHERE}) OR (adopt_as_reference=1 AND ignored=0))
        ORDER BY moca_oid,measurement_epoch_yr,id""", oids)
    for row in rows:
        payload = payloads[row["moca_oid"]]
        if row["adopt_as_reference"]:
            payload["reference"] = row
        payload["rows"].append(row)
    return payloads


def comparison(fit, adopted):
    ra, dec = adopted.get("pmra_masyr"), adopted.get("pmdec_masyr")
    return (fit["pmra"] - ra, fit["pmdec"] - dec) if ra is not None and dec is not None else (None, None)


def fit_options():
    return {"offsets": request.args.get("offsets") != "0", "calibrated": request.args.get("calibrated") != "0"}


def remember(cache, key, data, limit):
    with _CACHE_LOCK:
        cache[key] = time.monotonic(), data
        cache.move_to_end(key)
        if len(cache) > limit:
            cache.popitem(last=False)


def cached_fit(cache, key):
    with _CACHE_LOCK:
        item = cache.get(key)
        if item and time.monotonic() - item[0] < FIT_TTL:
            cache.move_to_end(key)
            return item[1]
    return None


@app.get("/")
def index():
    return send_from_directory(STATIC, "mosaic_review.html")


@app.get("/plotly.min.js")
def plotly():
    return Response(plotly_source(), mimetype="application/javascript")


@lru_cache(maxsize=1)
def plotly_source():
    from plotly.offline import get_plotlyjs
    return get_plotlyjs()


@app.get("/api/queue")
def queue():
    sample = request.args.get("sample", "public_l0")
    with database() as cursor:
        oids = sample_oids(cursor, sample)
        ready = review_table_ready(cursor)
        reviews = latest_reviews(cursor) if ready else []
    selected = set(oids)
    return jsonify(oids=oids, reviews=[review_point(row) for row in reviews if row["moca_oid"] in selected],
                   writesReady=ready, version=FIT_VERSION)


@app.get("/api/calibrations")
def calibration_policy():
    return jsonify(calibration_metadata(fit_options()["calibrated"]))


@app.get("/api/target/<int:oid>")
def target(oid):
    options = fit_options()
    with database() as cursor:
        payload = measurement_data(cursor, (oid,), detail=True)[oid]
        prior = current_review(cursor, oid, REVIEW_FIELDS + ",comparison_json") if review_table_ready(cursor) else None
    adopted = payload["pm"]
    if adopted.get("origin") == ORIGIN:
        adopted = json.loads(prior["comparison_json"]) if prior else {}
    reference = payload["reference"] or next(iter(payload["rows"]), {})
    common = {"target": payload["target"], "literature": payload["literature"], "review": review_point(prior),
              "coordinates": {"ra": reference.get("ra"), "dec": reference.get("dec")}}
    try:
        result = fit_target(payload, **options)
    except ValueError as error:
        return jsonify(**common, unavailable=str(error))
    token = uuid4().hex
    remember(_FITS, token, {"oid": oid, "result": result, "adopted": adopted}, 32)
    fit = result["fits"][result["preferred"]]
    dx, dy = comparison(fit, adopted)
    if not prior:
        remember(_SUMMARY, (oid, *options.values()), {"oid": oid, "dx": dx, "dy": dy}, 4096)
    return jsonify(**common, **result, token=token, comparison=adopted)


@app.get("/api/comparison")
def comparison_batch():
    try:
        oids = tuple(dict.fromkeys(int(value) for value in request.args.get("oids", "").split(",")))
    except ValueError:
        raise ReviewError("Supply numeric comparison targets.") from None
    if not 1 <= len(oids) <= 12 or min(oids) <= 0:
        raise ReviewError("Supply one to twelve comparison targets.")
    options = fit_options()
    points, missing = [], []
    for oid in oids:
        previous = cached_fit(_SUMMARY, (oid, *options.values()))
        if previous is None:
            missing.append(oid)
        else:
            points.append(previous)
    if missing:
        with database() as cursor:
            payloads = measurement_data(cursor, tuple(missing))
        for oid, payload in payloads.items():
            fit_point = {"oid": oid, "dx": None, "dy": None}
            if payload["pm"] and payload["rows"]:
                try:
                    result = fit_target(payload, detail=False, **options)
                    fit_point["dx"], fit_point["dy"] = comparison(result["fits"][result["preferred"]], payload["pm"])
                except ValueError:
                    pass
            remember(_SUMMARY, (oid, *options.values()), fit_point, 4096)
            points.append(fit_point)
    return jsonify(points=[point for point in points if point["dx"] is not None])


def serialize(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)


def operation_id(value):
    try:
        return UUID(value).hex
    except (ValueError, TypeError, AttributeError):
        raise ReviewError("Missing decision request ID.") from None


def lock_target(cursor, oid):
    if not one(cursor, "SELECT moca_oid FROM moca_objects WHERE moca_oid=%s AND ignored=0 FOR UPDATE", (oid,)):
        raise ReviewError("This MOCAdb target is unavailable.", 404)


def owned_pm(cursor, oid):
    row = one(cursor, f"""SELECT proper_motion_id FROM {TABLE}
        WHERE moca_oid=%s AND proper_motion_id IS NOT NULL ORDER BY id DESC LIMIT 1""", (oid,))
    if not row:
        return None
    pid = row["proper_motion_id"]
    if not one(cursor, """SELECT id FROM data_proper_motions
        WHERE id=%s AND moca_oid=%s AND origin=%s AND mission_name='MOSAIC' AND rls='gagne' AND is_public=0 FOR UPDATE""",
        (pid, oid, ORIGIN)):
        raise ReviewError("The linked PM row was modified outside this reviewer.", 409)
    return pid


def apply_pm(cursor, oid, pid, review_id, fit, bundle_json):
    if fit is None:
        if pid:
            cursor.execute("UPDATE data_proper_motions SET ignored=1 WHERE id=%s AND ignored=0", (pid,))
        return pid
    params = (fit["pmra"], fit["pmdec"], fit["pmraUnc"], fit["pmdecUnc"], fit["t0"], "review-20261109-v1",
              fit["fitter"], hashlib.md5(bundle_json.encode("utf-8"), usedforsecurity=False).hexdigest(),
              f"{ORIGIN}; {TABLE}.id={review_id}; fit={fit['mode']}")
    if pid is None:
        cursor.execute("""INSERT INTO data_proper_motions
            (pmra_masyr,pmdec_masyr,pmra_masyr_unc,pmdec_masyr_unc,epoch,data_release,calculation_method,md5_uid,comments,
             moca_oid,origin,mission_name,is_public,rls,ignored)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'MOSAIC',0,'gagne',0)""", (*params, oid, ORIGIN))
        return cursor.lastrowid
    cursor.execute("""UPDATE data_proper_motions SET pmra_masyr=%s,pmdec_masyr=%s,pmra_masyr_unc=%s,pmdec_masyr_unc=%s,
        epoch=%s,data_release=%s,calculation_method=%s,md5_uid=%s,comments=%s,ignored=0 WHERE id=%s""", (*params, pid))
    return pid


def audit_write(cursor, oid, review_id, action, pm_modified):
    cursor.execute("""INSERT INTO moca_changelog
        (`user`,machine_name,modified_tables,nrows_modified,user_description,rls,is_public)
        VALUES ('management',%s,%s,%s,%s,'gagne',0)""",
        (os.uname().nodename[:50], TABLE + (", data_proper_motions" if pm_modified else ""),
         2 if pm_modified else 1, f"MOSAIC reviewer {action}, oid={oid}, vetting id={review_id}"))


def require_review_table(cursor):
    if not review_table_ready(cursor):
        raise ReviewError("Apply the proposed MOSAIC vetting table to enable writes.", 409)


@app.post("/api/target/<int:oid>/decision")
def decision(oid):
    body = request.get_json()
    if not isinstance(body, dict) or body.get("decision") not in ("adopt", "reject"):
        raise ReviewError("Choose Adopt or Reject.")
    action = body["decision"]
    uid = operation_id(body.get("requestId"))
    token = body.get("token")
    preview = cached_fit(_FITS, token) if isinstance(token, str) else None
    with database(write=True) as cursor:
        require_review_table(cursor)
        lock_target(cursor, oid)
        old = current_review(cursor, oid)
        duplicate = one(cursor, f"SELECT id,moca_oid,undone_at FROM {TABLE} WHERE request_id=%s", (uid,))
        if duplicate:
            if not old or old["id"] != duplicate["id"] or duplicate["moca_oid"] != oid or duplicate["undone_at"]:
                raise ReviewError("This decision has already changed. Reload to continue.", 409)
            return jsonify(review=review_point(old))
        if body.get("expected") != (old["id"] if old else None):
            raise ReviewError("A review for this target changed. Reload the target before deciding.", 409)
        if not preview or preview["oid"] != oid:
            raise ReviewError("The fit preview expired. Reload the target before deciding.", 409)
        result = preview["result"]
        mode = body.get("mode")
        if not isinstance(mode, str) or mode not in result["fits"]:
            raise ReviewError("Select a fitted solution.")
        fit = {key: val for key, val in result["fits"][mode].items() if key not in {"curve", "model"}}
        bundle = serialize({"settings": result["settings"], "reference": result["reference"],
                            "measurements": result["measurements"], "fit": fit})
        dx, dy = comparison(fit, preview["adopted"])
        pid = owned_pm(cursor, oid)
        cursor.execute(f"""INSERT INTO {TABLE}
            (request_id,moca_oid,decision,webtool_version,method,fit_mode,measurement_bundle,comparison_json,
             delta_pmra,delta_pmdec,is_public,rls)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,'gagne')""",
            (uid, oid, action, FIT_VERSION, fit["fitter"], mode, bundle, serialize(preview["adopted"]), dx, dy))
        review_id = cursor.lastrowid
        if action == "adopt":
            pid = apply_pm(cursor, oid, pid, review_id, fit, bundle)
            cursor.execute(f"UPDATE {TABLE} SET proper_motion_id=%s WHERE id=%s", (pid, review_id))
        elif pid:
            apply_pm(cursor, oid, pid, review_id, None, None)
        audit_write(cursor, oid, review_id, action, action == "adopt" or bool(pid))
        return jsonify(review=review_point(current_review(cursor, oid)))


@app.post("/api/target/<int:oid>/undo")
def undo(oid):
    body = request.get_json()
    expected = body.get("id") if isinstance(body, dict) else None
    if type(expected) is not int or expected < 1:
        raise ReviewError("Select a saved decision to undo.")
    with database(write=True) as cursor:
        require_review_table(cursor)
        lock_target(cursor, oid)
        previous = current_review(cursor, oid)
        target_decision = one(cursor, f"SELECT undone_at FROM {TABLE} WHERE id=%s AND moca_oid=%s", (expected, oid))
        if target_decision and target_decision["undone_at"]:
            return jsonify(review=review_point(previous))
        if not previous or previous["id"] != expected:
            raise ReviewError("This is no longer the current decision. Reload to continue.", 409)
        cursor.execute(f"UPDATE {TABLE} SET undone_at=CURRENT_TIMESTAMP(6) WHERE id=%s", (expected,))
        restored = current_review(cursor, oid, REVIEW_FIELDS + ",measurement_bundle")
        pid = owned_pm(cursor, oid)
        if restored and restored["decision"] == "adopt":
            bundle = restored["measurement_bundle"]
            restored_pid = apply_pm(cursor, oid, pid, restored["id"], json.loads(bundle)["fit"], bundle)
            if restored_pid != pid:
                cursor.execute(f"UPDATE {TABLE} SET proper_motion_id=%s WHERE id=%s", (restored_pid, restored["id"]))
                restored["proper_motion_id"] = restored_pid
        elif pid:
            apply_pm(cursor, oid, pid, expected, None, None)
        audit_write(cursor, oid, expected, "undo", bool(pid))
        return jsonify(review=review_point(restored))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8911)
    args = parser.parse_args()
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
