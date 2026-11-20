"""MOSHPIT candidate spectra for the standard SPHEREx reviewer."""

import json
import math
from datetime import datetime, timezone
from uuid import uuid4

from . import spherex_review as review
from .spherex_native_fit import fit_spectrum_rows

TABLE = "pcat_moshpit_candidates"
READY = "c.origin='moshpit/native_dr1' AND c.spectrum_json IS NOT NULL"


def requested(body):
    return body.get("lane") == "moshpit" or body.get("review_sample") == "moshpit"


def queue(cur, body, count_only):
    conditions, params = [READY], []
    if body.get("moca_specid") is not None:
        raise review.ReviewError("Use the MOSHPIT candidate ID for a native spectrum.")
    cid = body.get("candidate_id")
    if cid not in (None, ""):
        conditions.append("c.id=%s")
        params.append(review.integer(cid, "MOSHPIT candidate ID"))
    else:
        if review.boolean(body.get("pending_only"), True):
            conditions.append("c.spectral_review IS NULL")
        oid_status = body.get("oid_status", "all")
        if oid_status not in ("all", "assigned", "unassigned"):
            raise review.ReviewError("Choose a supported MOSHPIT OID filter.")
        if oid_status != "all":
            conditions.append("c.moca_oid IS " + ("NOT NULL" if oid_status == "assigned" else "NULL"))
    where = " AND ".join(conditions)
    if count_only:
        cur.execute(f"SELECT COUNT(*) AS total FROM {TABLE} c WHERE {where}", params)
        return cur.fetchone()
    after = review.integer(body.get("after") or 0, "Candidate cursor", 0)
    limit = review.integer(body.get("limit", 100), "Queue batch size", 1, 500)
    records = review.rows(cur, f"""
        SELECT c.id AS candidate_id, c.moca_oid, c.source_key AS designation
        FROM {TABLE} c WHERE {where} AND c.id>%s ORDER BY c.id LIMIT %s
    """, (*params, after, limit + 1))
    more = len(records) > limit
    return {"lane": "moshpit", "items": records[:limit], "has_more": more,
            "next_after": records[limit - 1]["candidate_id"] if more else None}


def spectral_rows(product):
    try:
        wave, flux, error = (product[k] for k in ("wavelength_um", "flux_ujy", "error_ujy"))
        if not all(isinstance(v, list) for v in (wave, flux, error)) or not (len(wave) == len(flux) == len(error)):
            raise ValueError()
        spectrum = []
        for w, f, e in zip(wave, flux, error):
            if w is None or f is None or not math.isfinite(w) or w <= 0 or not math.isfinite(f):
                continue
            angstrom = w * 1e4
            # A microjansky converted to W m^-2 Angstrom^-1.
            conversion = 2.99792458e-14 / angstrom**2
            valid_error = e is not None and math.isfinite(e) and e > 0
            spectrum.append({"wavelength_angstrom": angstrom,
                             "flux_flambda": f * conversion, "flux_flambda_unc": e * conversion if valid_error else None,
                             "ignored": int(not valid_error)})
        return spectrum
    except (TypeError, KeyError, ValueError, OverflowError):
        raise review.ReviewError("The MOSHPIT spectrum contains invalid channel arrays.", 422) from None


def review_state(row):
    history = json.loads(row["review_history"] or "[]")
    latest = next((event["id"] for event in reversed(history) if event.get("lane") == "spectral"), None)
    return history, review.fingerprint([row["spectral_review"], latest])


def candidate(cur, cid, *, spectrum=False, lock=False):
    # Keep the write lock on the candidate alone. An OID assignment can arrive during a review.
    fields = ",c.spectrum_json,c.moca_oid,c.ra_deg,c.dec_deg,c.median_snr,c.selection_route,c.spectral_type,c.p_accept" if spectrum else ""
    found = review.rows(cur, f"""
        SELECT c.id,c.source_key,c.spectral_review,c.review_history,SHA2(c.spectrum_json,256) AS data_revision{fields}
        FROM {TABLE} c WHERE c.id=%s AND {READY}""" + (" FOR UPDATE" if lock else ""), (cid,))
    if not found:
        raise review.ReviewError("MOSHPIT candidate spectrum unavailable.", 404)
    return found[0]


def analyze(cur, body):
    row = candidate(cur, review.integer(body.get("candidate_id"), "MOSHPIT candidate ID"), spectrum=True)
    try:
        spectrum = spectral_rows(json.loads(row["spectrum_json"]))
    except json.JSONDecodeError:
        raise review.ReviewError("The MOSHPIT spectrum contains invalid JSON.", 422) from None
    _, revision = review_state(row)
    name = row["source_key"]
    if row["moca_oid"] is not None:
        objects = review.rows(cur, "SELECT designation FROM moca_objects WHERE moca_oid=%s AND ignored=0", (row["moca_oid"],))
        if objects and objects[0]["designation"]:
            name = objects[0]["designation"]
    meta = {"candidate_id": row["id"], "moca_oid": row["moca_oid"], "moca_specid": None,
            "designation": name, "ra": row["ra_deg"], "dec": row["dec_deg"], "object_origin": "MOSHPIT native DR1",
            "source_key": row["source_key"], "selection_route": row["selection_route"], "selection_type": row["spectral_type"],
            "median_snr_per_pix": row["median_snr"], "spectral_cnn_probability": row["p_accept"]}
    options = review.fit_options(body)
    templates = review.template_rows(cur)
    try:
        fit, warning = fit_spectrum_rows(spectrum, templates, options), None
    except ValueError as exc:
        fit, warning = None, str(exc)
    return {"lane": "moshpit", "read_only": False, "object": meta, "fit": fit, "raw_spectrum": spectrum,
            "state": {"spectral_review": row["spectral_review"]}, "warning": warning,
            "revision": revision, "data_revision": row["data_revision"]}


def check_revision(row, expected):
    history, revision = review_state(row)
    if row["data_revision"] != expected.get("data_revision") or revision != expected.get("revision"):
        raise review.ReviewError("The MOSHPIT spectrum or its review changed. Reload the candidate.", 409)
    return history


def prepare(cur, auth, body):
    cid = review.integer(body.get("candidate_id"), "MOSHPIT candidate ID")
    label = body.get("classification")
    if body.get("action") != "classify" or label not in dict(review.CLASSIFICATIONS):
        raise review.ReviewError("Choose a MOSHPIT spectral quality classification.")
    row = candidate(cur, cid)
    check_revision(row, body)
    if row["spectral_review"] is not None and not review.boolean(body.get("allow_replace")):
        raise review.ReviewError("Enable replacement to change an existing MOSHPIT classification.", 409)
    sources = str(body.get("sources") or "mocaviz").strip()
    if len(sources) > 255:
        raise review.ReviewError("Sources must be at most 255 characters.")
    plan = {"lane": "moshpit", "candidate_id": cid, "classification": label, "sources": sources,
            "revision": body["revision"], "data_revision": row["data_revision"],
            "write_policy_version": review.WRITE_POLICY_VERSION,
            "operations": [{"table": TABLE, "operation": "update", "rows": [{"id": cid, "spectral_review": label}]}]}
    return {"plan": plan, "receipt": review.seal(auth, "plan", plan), "dry_run": True, "row_counts": {TABLE: 1}}


def apply_review(conn, cur, auth, plan, *, undo=False):
    cid = plan["candidate_id"]
    row = candidate(cur, cid, lock=True)
    history = check_revision(row, plan)
    action = "undo" if undo else "classify"
    label = plan["classification"]
    event = {"id": uuid4().hex, "at": datetime.now(timezone.utc).isoformat(), "reviewer": auth["user"],
             "origin": "MOSHPIT human vetting", "lane": "spectral", "action": action, "label": label,
             "previous": row["spectral_review"], "sources": plan["sources"]}
    history.append(event)
    cur.execute(f"UPDATE {TABLE} SET spectral_review=%s,review_history=%s WHERE id=%s",
                (label, review.canonical(history), cid))
    cur.execute("INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls) "
                "VALUES (%s,%s,1,%s,0,'gagne')", (auth["user"], TABLE, f"MOSHPIT human spectral {action}, candidate {cid}."))
    if undo:
        result = {"undone": True}
    else:
        saved = {"lane": "moshpit", "candidate_id": cid, "classification": row["spectral_review"], "sources": plan["sources"],
                 "revision": review.fingerprint([label, event["id"]]), "data_revision": row["data_revision"]}
        result = {"submitted": True, "undo_receipt": review.seal(auth, "undo", saved, lifetime=24 * 3600)}
    conn.commit()
    return result
