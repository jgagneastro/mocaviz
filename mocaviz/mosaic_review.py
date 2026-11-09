"""Loopback-only MOSAIC proper-motion reviewer. Launched by Web Tools."""
from collections import OrderedDict, defaultdict
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

from .mosaic_review_fit import (
    FIT_VERSION, band_key, calibration_key, calibration_metadata, canonical_mission, fit_target, input_choices,
    parallax_motion,
)

STATIC = Path(__file__).resolve().parent / "static"
app = Flask(__name__, static_folder=str(STATIC))
app.config["MAX_CONTENT_LENGTH"] = 131072
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
_TARGETS = OrderedDict()
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
    selection = "ra IS NOT NULL AND `dec` IS NOT NULL AND measurement_epoch_yr IS NOT NULL" if detail else COORD_WHERE
    rows = query(cursor, f"""SELECT id,moca_oid,ignored,ra,`dec`,ra_unc_mas,dec_unc_mas,
        ra - COALESCE(calibration_delta_ra_mas / NULLIF(3600000 * COS(RADIANS(`dec`)),0),0) raw_ra,
        `dec` - COALESCE(calibration_delta_dec_mas / 3600000,0) raw_dec,
        measurement_epoch_yr,COALESCE(measurement_epoch_yr_unc,0) measurement_epoch_yr_unc,
        mission_name,data_release,moca_pid,moca_psid,calibration_method,origin,origin_table,airmass,
        single_epoch,pm_corrected,plx_corrected,point_of_view,adopt_as_reference,
        COALESCE(NULLIF(TRIM(CONCAT_WS(' ',NULLIF(TRIM(mission_name),''),NULLIF(TRIM(data_release),''))),''),moca_pid,'No mission') mission
        FROM data_equatorial_coordinates
        WHERE moca_oid IN ({placeholders}) AND (({selection}) OR (adopt_as_reference=1 AND ignored=0))
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


@app.get("/api/search")
def search():
    sample = request.args.get("sample", "public_l0")
    value = request.args.get("q", "").strip()[:100]
    if len(value) < 2:
        return jsonify(targets=[])
    with database() as cursor:
        allowed = set(sample_oids(cursor, sample))
        if value.isascii() and value.isdecimal() and int(value) < 2**64:
            results = query(cursor, "SELECT moca_oid,designation FROM moca_objects WHERE moca_oid=%s", (int(value),))
        else:
            prefix = value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            results = query(cursor, """SELECT moca_oid,designation FROM mechanics_all_designations
                WHERE designation LIKE %s ESCAPE '!' ORDER BY designation LIMIT 150""", (prefix,))
    matches = {row["moca_oid"]: row for row in results if row["moca_oid"] in allowed}
    return jsonify(targets=list(matches.values())[:12])


def preview_selection(body):
    if not isinstance(body, dict):
        raise ReviewError("Invalid fit controls.")
    selection = {}
    for key, limit in (("missions", 256), ("methods", 256), ("bands", 1024), ("excluded", 10000)):
        value = body.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or len(value) > limit:
            raise ReviewError("Too many items in the fit selection.")
        if key in {"missions", "methods"}:
            valid = all(isinstance(item, str) and len(item) <= 255 for item in value)
        elif key == "bands":
            valid = all(isinstance(item, list) and len(item) == 2 and isinstance(item[0], str)
                        and (item[1] is None or isinstance(item[1], str)) for item in value)
        else:
            valid = all(type(item) is int and 0 < item < 2**64 for item in value)
        if not valid:
            raise ReviewError("Invalid measurement selection.")
        selection[key] = value
    return selection


def display_measurements(payload, choices, selection, include_merged, use_raw):
    missions = selection.get("missions", [item["label"] for item in choices["missions"] if item["default"]])
    bands = {tuple(pair) for pair in selection.get("bands", [])}
    methods = selection.get("methods")
    result = []
    for row in payload["rows"]:
        if not row["ignored"] and not (include_merged and row["single_epoch"] == 0):
            continue
        mission = canonical_mission(row)
        if mission not in missions or (mission, band_key(row)) in bands:
            continue
        if methods is not None and calibration_key(row) not in methods:
            continue
        result.append(display_measurement(row, use_raw, "Ignored in MOCAdb" if row["ignored"] else "Merged astrometry"))
    return result


def display_measurement(row, use_raw, kind):
    return {"id": row.get("id"), "year": row.get("measurement_epoch_yr"), "kind": kind,
            "mission": canonical_mission(row) if row else None, "moca_psid": row.get("moca_psid"),
            "calibration_method": row.get("calibration_method"), "ignored": bool(row.get("ignored")),
            "sigmaRa": row.get("ra_unc_mas"), "sigmaDec": row.get("dec_unc_mas"),
            "raDeg": row.get("raw_ra" if use_raw else "ra"), "decDeg": row.get("raw_dec" if use_raw else "dec")}


@app.route("/api/target/<int:oid>", methods=("GET", "POST"))
def target(oid):
    options = fit_options()
    body = request.get_json() if request.method == "POST" else {}
    selection = preview_selection(body)
    source_token = body.get("sourceToken")
    snapshot = cached_fit(_TARGETS, source_token) if isinstance(source_token, str) else None
    if not snapshot or snapshot[0] != oid:
        with database() as cursor:
            payload = measurement_data(cursor, (oid,), detail=True)[oid]
            prior = current_review(cursor, oid, REVIEW_FIELDS + ",comparison_json") if review_table_ready(cursor) else None
        source_token = uuid4().hex
        remember(_TARGETS, source_token, (oid, payload, prior), 12)
    else:
        _, payload, prior = snapshot
    extra = {
        "only_recalibrated": body.get("onlyRecalibrated") is not False,
        "ignore_duplicates": body.get("ignoreDuplicates") is not False,
        "adjust_reference": body.get("adjustReference") is not False,
        "robust_fit": body.get("robustFit") is not False,
        "extra_floor": body.get("extraFloor") is True,
        "use_raw": body.get("raw") is True,
    }
    include_merged = body.get("merged") is True
    choices = input_choices(payload["rows"], only_recalibrated=extra["only_recalibrated"], include_merged=include_merged)
    adopted = payload["pm"]
    if adopted.get("origin") == ORIGIN:
        adopted = json.loads(prior["comparison_json"]) if prior else {}
    reference = payload["reference"] or next(iter(payload["rows"]), {})
    common = {"target": payload["target"], "literature": payload["literature"], "review": review_point(prior),
              "coordinates": {"ra": reference.get("ra"), "dec": reference.get("dec")},
              "inputChoices": choices, "sourceToken": source_token,
              "referenceMeasurement": display_measurement(payload["reference"], extra["use_raw"], "Adopted reference"),
              "displayMeasurements": display_measurements(payload, choices, selection, include_merged, extra["use_raw"])}
    try:
        result = fit_target(payload, **options, **extra, selection=selection)
    except ValueError as error:
        return jsonify(**common, unavailable=str(error))
    fit_reference = result["reference"]
    for row in [common["referenceMeasurement"], *common["displayMeasurements"]]:
        if row["year"] is not None:
            row["parallaxFactors"] = parallax_motion(fit_reference["ra"], fit_reference["dec"], row["year"])
    token = uuid4().hex
    remember(_FITS, token, {"oid": oid, "result": result, "adopted": adopted}, 32)
    fit = result["fits"][result["preferred"]]
    dx, dy = comparison(fit, adopted)
    if not prior and request.method == "GET":
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


def apply_pm(cursor, oid, pid, review_id, fit, bundle_json, version=FIT_VERSION):
    if fit is None:
        if pid:
            cursor.execute("UPDATE data_proper_motions SET ignored=1 WHERE id=%s AND ignored=0", (pid,))
        return pid
    params = (fit["pmra"], fit["pmdec"], fit["pmraUnc"], fit["pmdecUnc"], fit["t0"], version.removeprefix("mosaic-"),
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


@app.post("/api/target/<int:oid>/ignore")
def ignore_measurements(oid):
    body = request.get_json()
    ids = preview_selection({"excluded": body.get("ids") if isinstance(body, dict) else None}).get("excluded")
    if not ids:
        raise ReviewError("Select at least one astrometric measurement.")
    ids = sorted(set(ids))
    comments = body.get("comments", "")
    if not isinstance(comments, str) or len(comments) > 4096:
        raise ReviewError("Appended comments must be at most 4096 characters.")
    comments = comments.strip()
    revision = body.get("revision")
    apply = body.get("apply") is True
    placeholders = ",".join(["%s"] * len(ids))
    with database(write=apply) as cursor:
        if apply:
            lock_target(cursor, oid)
        rows = query(cursor, f"""SELECT id,ignored,comments,modified_timestamp,is_public,rls
            FROM data_equatorial_coordinates WHERE moca_oid=%s AND id IN ({placeholders}) ORDER BY id"""
            + (" FOR UPDATE" if apply else ""), (oid, *ids))
        if [row["id"] for row in rows] != ids:
            raise ReviewError("Selected measurements changed or do not belong to this target.", 409)
        current = hashlib.sha256(json.dumps([oid, comments, rows], default=str, sort_keys=True).encode()).hexdigest()
        changes = [row for row in rows if not row["ignored"]]
        if not apply:
            return jsonify(ids=ids, count=len(changes), alreadyIgnored=len(rows)-len(changes), revision=current)
        if current != revision:
            raise ReviewError("The measurements or comments changed. Review the selection again.", 409)
        groups = defaultdict(list)
        for row in changes:
            previous = row["comments"] or ""
            appended = previous + ("\n" if previous and not previous.endswith("\n") else "") + comments
            if comments and len(appended.encode("utf-8")) > 65535:
                raise ReviewError(f"Comments exceed the database capacity for row {row['id']}.")
            clause = "ignored=1,comments=%s" if comments else "ignored=1"
            params = (appended, oid, row["id"]) if comments else (oid, row["id"])
            cursor.execute(f"UPDATE data_equatorial_coordinates SET {clause} WHERE moca_oid=%s AND id=%s", params)
            if cursor.rowcount != 1:
                raise ReviewError("A measurement could not be updated. The changes were rolled back.", 409)
            groups[(row["is_public"], row["rls"])].append(row["id"])
        if changes:
            verified = query(cursor, f"""SELECT id,ignored FROM data_equatorial_coordinates
                WHERE moca_oid=%s AND id IN ({placeholders})""", (oid, *ids))
            if len(verified) != len(ids) or any(not row["ignored"] for row in verified):
                raise ReviewError("The saved flags could not be verified. The changes were rolled back.", 409)
        for (visibility, rls), group in groups.items():
            for start in range(0, len(group), 100):
                batch = group[start:start+100]
                cursor.execute("""INSERT INTO moca_changelog
                    (`user`,machine_name,modified_tables,nrows_modified,user_description,is_public,rls)
                    VALUES ('management',%s,'data_equatorial_coordinates',%s,%s,%s,%s)""",
                    (os.uname().nodename[:50], len(batch),
                     f"MOSAIC reviewer set ignored=1 for oid={oid}; IDs={batch}.", visibility, rls))
    if changes:
        with _CACHE_LOCK:
            for key in [key for key, (_, snapshot) in _TARGETS.items() if snapshot[0] == oid]:
                del _TARGETS[key]
            for key in [key for key, (_, preview) in _FITS.items() if preview["oid"] == oid]:
                del _FITS[key]
            for key in [key for key in _SUMMARY if key[0] == oid]:
                del _SUMMARY[key]
    return jsonify(ids=ids, updated=len(changes))


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
        fit = {key: val for key, val in result["fits"][mode].items() if key not in {"curve", "model", "parallaxMotion"}}
        used_ids = tuple(sorted({row["id"] for row in result["measurements"]}))
        placeholders = ",".join(["%s"] * len(used_ids))
        active = query(cursor, f"""SELECT id FROM data_equatorial_coordinates
            WHERE moca_oid=%s AND ignored=0 AND id IN ({placeholders}) FOR UPDATE""", (oid, *used_ids))
        if len(active) != len(used_ids):
            raise ReviewError("The measurements used by this fit changed. Reload the target before deciding.", 409)
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
        restored = current_review(cursor, oid, REVIEW_FIELDS + ",measurement_bundle,webtool_version")
        pid = owned_pm(cursor, oid)
        if restored and restored["decision"] == "adopt":
            bundle = restored["measurement_bundle"]
            restored_pid = apply_pm(cursor, oid, pid, restored["id"], json.loads(bundle)["fit"], bundle, restored["webtool_version"])
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
