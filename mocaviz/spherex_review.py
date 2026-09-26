"""Stateless, file-free SPHEREx autotype and visual review endpoints.

Credentials are supplied per request only. Never use mocaviz's cached engines,
dotenv defaults, disk caches, local pipeline imports, or server-side plotting.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# Also covers lazy imports triggered by the first request in a fresh worker.
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
import pymysql
from flask import Blueprint, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .spherex_autotype_core import (
    DEFAULT_OPTIONS, _build_autotype_spectral_type_db_values, fit_spectrum,
)

review = Blueprint("spherex_review", __name__)
STATIC = Path(__file__).resolve().parent / "static"
PRIVATE_DB = "mocadb_private_tables"
LANES = {
    "spiff": {
        "label": "SPIFF", "pack": 55, "table": "pcat_spherex_visual_vetting",
        "method": "spherex_autotype", "methods": ("spherex_autotype",),
    },
    "spiffstacker": {
        "label": "SPIFFStacker", "pack": 62, "table": "pcat_spherex_spiffstacker_visual_vetting",
        "method": "spiff_stacker_autotype", "methods": ("spiff_stacker_autotype",),
    },
    "sublimeaperture": {
        "label": "SUBLIMEaperture", "pack": 76, "table": "pcat_spherex_sublimeaperture_visual_vetting",
        "method": "sublimeaperture_autotype",
        "methods": ("sublimeaperture_autotype", "spherex_sublimeap_autotype"),
    },
}
CLASSIFICATIONS = [
    ("bad", "0"), ("good", "1"), ("good_candidate", "2"), ("peculiar_ucd", "3"),
    ("contaminated_ucd", "4"), ("incomplete_but_promising", "5"), ("unclear", "6"),
    ("good_plus_star", "7"), ("good_reddened", "8"), ("weird", "9"),
    ("galaxy", "g"), ("halo", "h"), ("reddened", "r"), ("snr", "s"),
    ("scatter", "c"), ("star", "t"), ("giant", "i"), ("early", "e"),
    ("late_M", "m"),
]
USABLE = {
    "good", "good_candidate", "late_M", "incomplete_but_promising",
    "good_plus_star", "contaminated_ucd", "good_reddened", "weird",
    "risky_andromeda", "giant", "peculiar_ucd",
}
SPT_FIELDS = (
    "moca_oid", "moca_specid", "moca_instid", "spectral_type", "complete_spectral_type",
    "spectral_type_number", "spectral_type_unc", "spectral_class", "quality_flag",
    "photometric_estimate", "simple_spectral_type", "wavelength_regime", "mission_name",
    "origin", "calculation_method", "suffix", "gravity_class", "ignored", "is_public",
    "rls", "comments",
)
MAX_BODY = 256 * 1024


class ReviewError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, np.floating)):
        value = float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def canonical(value):
    return json.dumps(clean(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value, name, low=1, high=2**53 - 1):
    if isinstance(value, bool):
        raise ReviewError(f"{name} must be an integer.")
    try:
        number = float(value)
        if not math.isfinite(number) or not number.is_integer() or not low <= number <= high:
            raise ValueError()
        return int(number)
    except (TypeError, ValueError, OverflowError):
        raise ReviewError(f"{name} must be an integer between {low} and {high}.") from None


def boolean(value, default=False):
    if value is None:
        return default
    if value in (True, 1, "1", "true"):
        return True
    if value in (False, 0, "0", "false"):
        return False
    raise ReviewError("Boolean options must be true or false.")


def bounded_float(value, name, low, high):
    try:
        number = float(value)
        if not math.isfinite(number) or not low <= number <= high:
            raise ValueError()
        return number
    except (TypeError, ValueError):
        raise ReviewError(f"{name} must be between {low} and {high}.") from None


def fit_options(body):
    raw = body.get("options") or {}
    if not isinstance(raw, dict) or set(raw) - set(DEFAULT_OPTIONS):
        raise ReviewError("Unsupported fit options.")
    return {
        "drop_worst_n": integer(raw.get("drop_worst_n", 5), "Dropped points", 0, 100),
        "chi2_sigma_cap": bounded_float(raw.get("chi2_sigma_cap", 5), "Sigma cap", 0.1, 100),
        "nonfield_odds_k": bounded_float(raw.get("nonfield_odds_k", 500), "Non-field odds", 1, 1e9),
        "nonfield_extreme_odds_k": bounded_float(raw.get("nonfield_extreme_odds_k", 500000), "Extreme odds", 1, 1e12),
    }


def credentials():
    """URL aliases, or headers populated from the page URL; never environment."""
    def supplied(keys, header):
        values = [request.args[k] for k in keys if k in request.args]
        if request.headers.get(header) is not None:
            values.append(request.headers[header])
        if len(set(values)) > 1:
            raise ReviewError("Conflicting URL credentials.", 403)
        return values[0] if values else ""
    user = supplied(("user", "username"), "X-MOCA-User")
    password = supplied(("pwd", "password"), "X-MOCA-Password")
    database = supplied(("dbase", "db", "database"), "X-MOCA-Database")
    if user not in {"collaborators", "management"} or not password:
        raise ReviewError("Open this page with collaborator or management credentials in its URL.", 403)
    if database != PRIVATE_DB:
        raise ReviewError("These tools require dbase=mocadb_private_tables in the URL.", 403)
    if request.args.get("host", "mocadb.ca") != "mocadb.ca" or request.args.get("port", "3306") != "3306":
        raise ReviewError("These tools connect only to mocadb.ca:3306.", 403)
    return {"user": user, "password": password, "database": database}


@contextmanager
def connection(auth):
    conn = pymysql.connect(
        host="mocadb.ca", port=3306, user=auth["user"], password=auth["password"],
        database=PRIVATE_DB, ssl={"verify_mode": False, "check_hostname": False},
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
        autocommit=False, connect_timeout=15, read_timeout=60, write_timeout=60,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_USER() AS authenticated_user FROM DUAL")
            row = cur.fetchone() or {}
            if str(row.get("authenticated_user", "")).split("@", 1)[0] != auth["user"]:
                raise ReviewError("Database authentication did not match the requested account.", 403)
            yield conn, cur
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def require_management(auth):
    if auth["user"] != "management":
        raise ReviewError("Database changes require management credentials supplied in the URL.", 403)


def seal(auth, kind, data, lifetime=900):
    payload = {"kind": kind, "expires": int(time.time()) + lifetime, "data": clean(data)}
    raw = base64.urlsafe_b64encode(canonical(payload).encode()).decode()
    # Receipts live only in the browser. Derivation avoids stored credentials,
    # shared server sessions and per-worker keys; receipts work across workers.
    key = hmac.new(auth["password"].encode(), b"mocaviz:spherex-review:v1", hashlib.sha256).digest()
    signature = hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()
    token = f"{raw}.{signature}"
    if len(token) > MAX_BODY - 256:
        raise ReviewError("This operation's undo/preview state exceeds the interactive request limit.")
    return token


def unseal(auth, token, kind):
    if not isinstance(token, str) or len(token) > MAX_BODY:
        raise ReviewError("Invalid or expired review receipt.", 409)
    try:
        raw, signature = token.rsplit(".", 1)
        key = hmac.new(auth["password"].encode(), b"mocaviz:spherex-review:v1", hashlib.sha256).digest()
        expected = hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(raw))
        if payload["kind"] != kind or payload["expires"] < time.time():
            raise ValueError()
        return payload["data"]
    except (ValueError, KeyError, TypeError):
        raise ReviewError("Invalid or expired review receipt. Reload the object.", 409) from None


def lane_for(body):
    key = body.get("lane", "spiffstacker")
    if not isinstance(key, str) or key not in LANES:
        raise ReviewError("Choose spiff, spiffstacker, or sublimeaperture.")
    return key, LANES[key]


def rows(cur, sql, params=()):
    cur.execute(sql, params)
    return list(cur.fetchall())


def snapshot(cur, lane, oid, *, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    vet = rows(cur, f"SELECT id, classification, sources, modified_timestamp FROM {lane['table']} WHERE moca_oid=%s" + suffix, (oid,))
    fields = ", ".join(f"\x60{key}\x60" for key in SPT_FIELDS)
    placeholders = ",".join(["%s"] * len(lane["methods"]))
    spt = rows(cur, f"SELECT id, {fields}, modified_timestamp FROM data_spectral_types WHERE moca_oid=%s AND calculation_method IN ({placeholders}) ORDER BY id" + suffix, (oid, *lane["methods"]))
    spectra = rows(cur, "SELECT moca_specid, ignored, modified_timestamp FROM moca_spectra WHERE moca_oid=%s AND moca_specpackid=%s ORDER BY moca_specid" + suffix, (oid, lane["pack"]))
    return clean({"vet": vet, "spt": spt, "spectra": spectra})


def dataset(cur, lane, oid, specid):
    meta = rows(cur, """
        SELECT s.moca_specid, s.moca_oid, s.ignored, s.median_snr_per_pix,
               mo.designation, mo.ra, mo.\x60dec\x60
        FROM moca_spectra s JOIN moca_objects mo ON mo.moca_oid=s.moca_oid
        WHERE s.moca_specid=%s AND s.moca_oid=%s AND s.moca_specpackid=%s AND mo.ignored=0
    """, (specid, oid, lane["pack"]))
    if not meta:
        raise ReviewError("This spectrum no longer exists in the selected lane. Reload the queue.", 404)
    spectrum = rows(cur, """
        SELECT id AS data_spectra_id, wavelength_angstrom, flux_flambda, flux_flambda_unc, ignored
        FROM data_spectra WHERE moca_specid=%s ORDER BY wavelength_angstrom, id LIMIT 10001
    """, (specid,))
    templates = rows(cur, """
        SELECT t.moca_spherex_template_id, t.spectral_type, t.spectral_type_number, t.grid_type,
               dt.wavelength_angstrom, dt.flux_flambda
        FROM moca_spherex_templates t JOIN data_spherex_templates dt
          ON dt.moca_spherex_template_id=t.moca_spherex_template_id
        WHERE t.ignored=0 AND dt.ignored=0 AND dt.flux_flambda>0
          AND dt.wavelength_angstrom IS NOT NULL
          AND t.spectral_type IS NOT NULL AND t.spectral_type_number IS NOT NULL
        ORDER BY t.moca_spherex_template_id, dt.wavelength_angstrom LIMIT 200001
    """)
    if len(spectrum) > 10000 or len(templates) > 200000:
        raise ReviewError("The spectrum/template grid exceeds this interactive tool's size limit.")
    return meta[0], spectrum, templates


def analyze(cur, body):
    key, lane = lane_for(body)
    oid = integer(body.get("moca_oid"), "moca_oid")
    specid = integer(body.get("moca_specid"), "moca_specid")
    meta, spectrum, templates = dataset(cur, lane, oid, specid)
    state = snapshot(cur, lane, oid)
    options = fit_options(body)
    fit, warning = None, None
    try:
        fit = fit_spectrum(spectrum, templates, options)
    except ValueError as exc:
        warning = str(exc)
    return clean({
        "lane": key, "object": meta, "state": state, "revision": fingerprint(state),
        "data_revision": fingerprint([spectrum, templates]), "fit": fit,
        "raw_spectrum": spectrum, "warning": warning,
    })


def queue(cur, body):
    _, lane = lane_for(body)
    limit = integer(body.get("limit", 100), "Queue batch size", 1, 500)
    after = integer(body.get("after", 0), "Queue cursor", 0)
    pending = boolean(body.get("pending_only"), True)
    conditions = ["mo.ignored=0", "s.moca_oid>%s"]
    params = [lane["pack"], after]
    if pending:
        conditions.extend(["s.ignored=0", "v.moca_oid IS NULL"])
    if body.get("moca_oids"):
        raw = body["moca_oids"]
        if not isinstance(raw, list) or len(raw) > 500:
            raise ReviewError("Provide at most 500 object IDs.")
        ids = [integer(v, "moca_oid") for v in raw]
        conditions.append("s.moca_oid IN (" + ",".join(["%s"] * len(ids)) + ")")
        params.extend(ids)
    if body.get("min_snr") not in (None, ""):
        conditions.append("s.median_snr_per_pix >= %s")
        params.append(bounded_float(body["min_snr"], "Minimum S/N", 0, 1e9))
    if body.get("min_sptn") not in (None, ""):
        conditions.append("EXISTS (SELECT 1 FROM data_spectral_types d WHERE d.moca_oid=s.moca_oid AND d.calculation_method IN (" + ",".join(["%s"] * len(lane["methods"])) + ") AND d.spectral_type_number>=%s)")
        params.extend(lane["methods"])
        params.append(bounded_float(body["min_sptn"], "Minimum spectral-type number", -60, 40))
    if boolean(body.get("no_known")):
        conditions.append("""NOT EXISTS (
            SELECT 1 FROM data_spectral_types known WHERE known.moca_oid=s.moca_oid
            AND known.ignored=0 AND known.photometric_estimate=0 AND known.spectral_type_number>=0
            AND (known.calculation_method IS NULL OR known.calculation_method NOT IN
                ('spherex_autotype','spiff_stacker_autotype','sublimeaperture_autotype','spherex_sublimeap_autotype'))
        )""")
    conditions.append("NOT EXISTS (SELECT 1 FROM moca_spectra newer WHERE newer.moca_oid=s.moca_oid AND newer.moca_specpackid=s.moca_specpackid AND newer.moca_specid>s.moca_specid" + (" AND newer.ignored=0)" if pending else ")"))
    records = rows(cur, f"""
        SELECT s.moca_oid, s.moca_specid, mo.designation, s.median_snr_per_pix,
               v.classification
        FROM moca_spectra s JOIN moca_objects mo ON mo.moca_oid=s.moca_oid
        LEFT JOIN {lane['table']} v ON v.moca_oid=s.moca_oid
        WHERE s.moca_specpackid=%s AND {' AND '.join(conditions)}
        ORDER BY s.moca_oid LIMIT %s
    """, (*params, limit + 1))
    return {"items": records[:limit], "has_more": len(records) > limit,
            "next_after": records[limit - 1]["moca_oid"] if len(records) >= limit else None}


def visibility(body):
    if "is_public" not in body:
        raise ReviewError("Select the visibility of new spectral-type measurements.")
    public = integer(body["is_public"], "is_public", 0, 1)
    rls = "public" if public else str(body.get("rls") or "").strip()
    if not rls or len(rls) > 20 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:+-" for c in rls):
        raise ReviewError("Private writes require an RLS name of at most 20 characters.")
    return public, rls


def make_spt(item, lane, ignored, public, rls):
    if not item["fit"]:
        raise ReviewError("A valid autotype fit is required to write a spectral type.")
    existing_methods = {row["calculation_method"] for row in item["state"]["spt"]}
    method = next((value for value in lane["methods"] if value in existing_methods), lane["method"])
    values = _build_autotype_spectral_type_db_values(
        moca_oid=item["object"]["moca_oid"], moca_specid=item["object"]["moca_specid"],
        best_row=pd.Series(item["fit"]["best"]), code_name="mocaviz/spherex_review.py",
        calculation_method=method, ignored_value=ignored,
    )
    row = dict(zip(SPT_FIELDS, values))
    row.update(is_public=public, rls=rls)
    return clean(row)


def prepare(cur, body, auth):
    item = analyze(cur, body)
    if item["revision"] != body.get("revision") or item["data_revision"] != body.get("data_revision"):
        raise ReviewError("The spectrum or classification changed. Reload it before submitting.", 409)
    action = body.get("action")
    if action not in {"classify", "upsert_spt", "bad_pixels"}:
        raise ReviewError("Unknown review action.")
    key, lane = lane_for(body)
    public, rls = visibility(body)
    classification = body.get("classification")
    if action == "classify" and classification not in dict(CLASSIFICATIONS):
        raise ReviewError("Unknown quality classification.")
    replace = boolean(body.get("allow_replace"))
    if (action == "classify" and item["state"]["vet"] or action == "upsert_spt" and item["state"]["spt"]) and not replace:
        raise ReviewError("A stored result already exists. Enable replacement to review it again.", 409)
    operations = []
    if action == "classify":
        sources = str(body.get("sources") or "mocaviz").strip()
        if len(sources) > 255:
            raise ReviewError("Sources must be at most 255 characters.")
        operations.append({"table": lane["table"], "operation": "upsert", "rows": [
            {"moca_oid": item["object"]["moca_oid"], "classification": classification, "sources": sources},
        ]})
        ignored = int(classification not in USABLE)
        if item["state"]["spt"]:
            operations.append({"table": "data_spectral_types", "operation": "update", "rows": [
                {"id": row["id"], "ignored": ignored} for row in item["state"]["spt"]
            ]})
        elif item["fit"]:
            operations.append({"table": "data_spectral_types", "operation": "insert", "rows": [
                make_spt(item, lane, ignored, public, rls),
            ]})
        if ignored:
            operations.append({"table": "moca_spectra", "operation": "update", "rows": [
                {"moca_specid": row["moca_specid"], "ignored": 1}
                for row in item["state"]["spectra"] if row["ignored"] != 1
            ]})
    elif action == "upsert_spt":
        classification = item["state"]["vet"][0]["classification"] if item["state"]["vet"] else None
        operations.append({"table": "data_spectral_types", "operation": "upsert", "rows": [
            make_spt(item, lane, int(classification not in USABLE), public, rls),
        ]})
    else:
        if not item["fit"] or not item["fit"]["bad_pixel_ids"]:
            raise ReviewError("No newly flagged pixels to write.")
        operations.append({"table": "data_spectra", "operation": "update", "rows": [
            {"id": row_id, "ignored": 1} for row_id in item["fit"]["bad_pixel_ids"]
        ]})
    plan = {
        "lane": key, "moca_oid": item["object"]["moca_oid"],
        "moca_specid": item["object"]["moca_specid"], "revision": item["revision"],
        "data_revision": item["data_revision"], "operations": operations,
        "action": action, "is_public": public, "rls": rls,
    }
    return {"plan": plan, "receipt": seal(auth, "plan", plan),
            "dry_run": True, "warning": item["warning"],
            "row_counts": {op["table"]: len(op["rows"]) for op in operations}}


def upsert(cur, table, values, update_fields):
    columns = list(values)
    sql = f"INSERT INTO \x60{table}\x60 (" + ",".join(f"\x60{k}\x60" for k in columns) + ") VALUES (" + ",".join(["%s"] * len(columns)) + ")"
    if update_fields:
        sql += " ON DUPLICATE KEY UPDATE " + ",".join(f"\x60{k}\x60=VALUES(\x60{k}\x60)" for k in update_fields)
    cur.execute(sql, tuple(values[k] for k in columns))


def changelog(cur, auth, oid, operations, public, rls, undo=False):
    count = sum(len(op["rows"]) for op in operations)
    cur.execute("""
        INSERT INTO moca_changelog
        (\x60user\x60, modified_tables, nrows_modified, user_description, is_public, rls)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (auth["user"], ", ".join(op["table"] for op in operations), count,
          f"mocaviz/spherex_review.py: {'undo' if undo else 'review'} for moca_oid={oid}",
          public, rls))


def lock_object(cur, oid):
    records = rows(cur, "SELECT moca_oid FROM moca_objects WHERE moca_oid=%s AND ignored=0 FOR UPDATE", (oid,))
    if not records:
        raise ReviewError("The object is no longer active.", 404)


def lock_source_pixels(cur, specid):
    # Only the selected spectrum, never the shared template grid.
    selected = rows(cur, "SELECT id FROM data_spectra WHERE moca_specid=%s ORDER BY id LIMIT 10001 FOR UPDATE", (specid,))
    if len(selected) > 10000:
        raise ReviewError("The selected spectrum exceeds the interactive size limit.")


def submit(conn, cur, auth, body):
    plan = unseal(auth, body.get("receipt"), "plan")
    _, lane = lane_for(plan)
    oid, specid = plan["moca_oid"], plan["moca_specid"]
    lock_object(cur, oid)
    before = snapshot(cur, lane, oid, lock=True)
    lock_source_pixels(cur, specid)
    _, spectrum, templates = dataset(cur, lane, oid, specid)
    if fingerprint(before) != plan["revision"] or fingerprint([spectrum, templates]) != plan["data_revision"]:
        raise ReviewError("Another review or spectrum update changed this object. Reload it.", 409)
    pixel_before = []
    for op in plan["operations"]:
        table = op["table"]
        for row in op["rows"]:
            if table == lane["table"]:
                upsert(cur, table, row, ("classification", "sources"))
            elif table == "data_spectral_types":
                if op["operation"] == "update":
                    cur.execute("UPDATE data_spectral_types SET ignored=%s WHERE id=%s AND moca_oid=%s",
                                (row["ignored"], row["id"], oid))
                else:
                    upsert(cur, table, row, [k for k in row if k not in {"moca_oid", "calculation_method"}])
            elif table == "moca_spectra":
                cur.execute("UPDATE moca_spectra SET ignored=1 WHERE moca_specid=%s AND moca_oid=%s AND moca_specpackid=%s",
                            (row["moca_specid"], oid, lane["pack"]))
            elif table == "data_spectra":
                existing = next((v for v in spectrum if v["data_spectra_id"] == row["id"]), None)
                if existing is None:
                    raise ReviewError("A flagged pixel disappeared.", 409)
                pixel_before.append({"id": row["id"], "ignored": existing["ignored"]})
                cur.execute("UPDATE data_spectra SET ignored=1 WHERE id=%s AND moca_specid=%s", (row["id"], specid))
            else:
                raise ReviewError("Invalid write plan.")
    changelog(cur, auth, oid, plan["operations"], plan["is_public"], plan["rls"])
    after = snapshot(cur, lane, oid)
    _, after_spectrum, _ = dataset(cur, lane, oid, specid)
    undo = {
        "lane": plan["lane"], "moca_oid": oid, "moca_specid": specid,
        "before": before, "after": after, "pixels": pixel_before,
        "after_data": fingerprint(after_spectrum),
        "operations": plan["operations"], "is_public": plan["is_public"], "rls": plan["rls"],
    }
    receipt = seal(auth, "undo", undo, lifetime=24 * 3600)
    conn.commit()
    return {"submitted": True, "undo_receipt": receipt}


def undo(conn, cur, auth, body):
    saved = unseal(auth, body.get("receipt"), "undo")
    _, lane = lane_for(saved)
    oid, specid = saved["moca_oid"], saved["moca_specid"]
    lock_object(cur, oid)
    current = snapshot(cur, lane, oid, lock=True)
    lock_source_pixels(cur, specid)
    _, spectrum, _ = dataset(cur, lane, oid, specid)
    if fingerprint(current) != fingerprint(saved["after"]) or fingerprint(spectrum) != saved["after_data"]:
        raise ReviewError("The database changed after this review. Undo would overwrite newer work.", 409)
    before = saved["before"]
    changed_tables = {op["table"] for op in saved["operations"]}
    if lane["table"] in changed_tables:
        if before["vet"]:
            row = before["vet"][0]
            cur.execute(f"UPDATE {lane['table']} SET classification=%s, sources=%s WHERE moca_oid=%s",
                        (row["classification"], row["sources"], oid))
        else:
            cur.execute(f"DELETE FROM {lane['table']} WHERE moca_oid=%s", (oid,))
    if "data_spectral_types" in changed_tables:
        previous = {r["id"]: r for r in before["spt"]}
        for row in current["spt"]:
            if row["id"] not in previous:
                cur.execute("DELETE FROM data_spectral_types WHERE id=%s AND moca_oid=%s", (row["id"], oid))
        for row in previous.values():
            # Deliberately omit DB-worker-managed adoption flags and timestamps.
            fields = list(SPT_FIELDS)
            cur.execute("UPDATE data_spectral_types SET " + ",".join(f"\x60{k}\x60=%s" for k in fields) + " WHERE id=%s AND moca_oid=%s",
                        (*[row[k] for k in fields], row["id"], oid))
    if "moca_spectra" in changed_tables:
        for row in before["spectra"]:
            cur.execute("UPDATE moca_spectra SET ignored=%s WHERE moca_specid=%s AND moca_oid=%s",
                        (row["ignored"], row["moca_specid"], oid))
    for row in saved["pixels"]:
        cur.execute("UPDATE data_spectra SET ignored=%s WHERE id=%s AND moca_specid=%s",
                    (row["ignored"], row["id"], specid))
    changelog(cur, auth, oid, saved["operations"], saved["is_public"], saved["rls"], undo=True)
    conn.commit()
    return {"undone": True}


def demo_item(body):
    oid = integer(body.get("moca_oid", 1001), "moca_oid")
    lane, _ = lane_for(body)
    wavelengths = np.linspace(8000, 50000, 90)
    flux = 1e-17 * (1.3 + np.sin(wavelengths / 3500) * 0.3)
    spectrum = [
        {"data_spectra_id": i + 1, "wavelength_angstrom": w, "flux_flambda": f,
         "flux_flambda_unc": f * 0.08, "ignored": 0}
        for i, (w, f) in enumerate(zip(wavelengths, flux))
    ]
    templates = [
        {"moca_spherex_template_id": t + 1, "spectral_type": f"L{t + 3}",
         "spectral_type_number": t + 13, "grid_type": "field",
         "wavelength_angstrom": w, "flux_flambda": f * (1 + t * 0.15 * np.cos(w / 5000))}
        for t in range(3) for w, f in zip(wavelengths, flux)
    ]
    return clean({
        "lane": lane, "object": {"moca_oid": oid, "moca_specid": oid + 10000,
            "designation": f"Demonstration {oid}", "ra": 93.4382457, "dec": -64.9139227,
            "median_snr_per_pix": 12.5, "ignored": 0},
        "state": {"vet": [], "spt": [], "spectra": []}, "revision": "demo", "data_revision": "demo",
        "fit": fit_spectrum(spectrum, templates, fit_options(body)),
        "raw_spectrum": spectrum, "warning": "Synthetic demo data. Database writes are disabled.",
    })


@review.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
    return response


@review.get("/spherex-autotype")
@review.get("/spherex-review")
def page():
    return send_from_directory(STATIC, "spherex_review.html")


@review.post("/api/spherex-review/<operation>")
def api(operation):
    try:
        if not request.is_json:
            raise ReviewError("Provide an application/json request.", 415)
        raw_body = request.stream.read(MAX_BODY + 1)
        if len(raw_body) > MAX_BODY:
            raise ReviewError("Review request is too large.", 413)
        try:
            body = json.loads(raw_body)
        except (ValueError, UnicodeError):
            raise ReviewError("Invalid JSON request.") from None
        if not isinstance(body, dict):
            raise ReviewError("Provide a JSON object.")
        mock = boolean(body.get("mock"))
        if operation not in {"context", "queue", "analyze", "preview", "submit", "undo"}:
            raise ReviewError("Unknown review operation.", 404)
        if mock:
            if operation in {"preview", "submit", "undo"}:
                raise ReviewError("Demo results cannot be written to MOCAdb.", 403)
            if operation == "context":
                result = {"role": "demo", "can_write": False, "lanes": LANES, "classifications": CLASSIFICATIONS}
            elif operation == "queue":
                result = {"items": [{"moca_oid": n, "moca_specid": n + 10000, "designation": f"Demonstration {n}"} for n in range(1001, 1007)], "has_more": False, "next_after": None}
            else:
                result = demo_item(body)
        else:
            auth = credentials()
            if operation in {"preview", "submit", "undo"}:
                require_management(auth)
            with connection(auth) as (conn, cur):
                if operation == "context":
                    result = {"role": auth["user"], "can_write": auth["user"] == "management",
                              "lanes": LANES, "classifications": CLASSIFICATIONS}
                elif operation == "queue":
                    result = queue(cur, body)
                elif operation == "analyze":
                    result = analyze(cur, body)
                elif operation == "preview":
                    result = prepare(cur, body, auth)
                elif operation == "submit":
                    result = submit(conn, cur, auth, body)
                else:
                    result = undo(conn, cur, auth, body)
        return jsonify({"ok": True, **clean(result)})
    except ReviewError as exc:
        return jsonify(ok=False, error=str(exc)), exc.status
    except HTTPException as exc:
        return jsonify(ok=False, error=exc.name), exc.code
    except pymysql.MySQLError as exc:
        code = exc.args[0] if exc.args else None
        if code in {1044, 1045, 1142}:
            message, status = "Credentials were rejected or lack permission for this operation.", 403
        elif code in {1205, 1213}:
            message, status = "The database is busy. Reload this object and try again.", 409
        else:
            message, status = "Database request failed. Reload to check its state before retrying; no submission is assumed successful.", 503
        # Do not log/return raw DB exceptions (may contain SQL, user or password).
        return jsonify(ok=False, error=message), status
    except Exception:
        # No traceback or request logging; these routes must not persist credentials.
        return jsonify(ok=False, error="Review request failed. Reload the object and try again."), 500
