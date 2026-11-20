"""MOSHPIT candidate spectra for the standard SPHEREx reviewer."""

import json
import math
from datetime import datetime, timezone
from uuid import uuid4

from . import spherex_review as review
from .spherex_native_fit import fit_spectrum_rows

from .spherex_moshpit_queue import TABLE, READY, DESIGNATION, queue


def requested(body):
    return body.get("lane") == "moshpit" or body.get("review_sample") == "moshpit"


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
        SELECT c.id,{DESIGNATION} AS designation,c.source_key,c.spectral_review,c.review_history,SHA2(c.spectrum_json,256) AS data_revision{fields}
        FROM {TABLE} c WHERE c.id=%s AND {READY}""" + (" FOR UPDATE" if lock else ""), (cid,))
    if not found:
        raise review.ReviewError("MOSHPIT candidate spectrum unavailable.", 404)
    return found[0]


def analyze(cur, body):
    row = candidate(cur, review.integer(body.get("candidate_id"), "MOSHPIT candidate ID"), spectrum=True)
    try:
        product = json.loads(row["spectrum_json"])
        spectrum = spectral_rows(product)
    except json.JSONDecodeError:
        raise review.ReviewError("The MOSHPIT spectrum contains invalid JSON.", 422) from None
    _, revision = review_state(row)
    source = body.get("adopted_spt_source", "private")
    objects = []
    if row["moca_oid"] is not None:
        column = review.adopted_spt_column("private" if source == "survey" else source)
        objects = review.rows(cur, f"""SELECT mo.designation AS object_designation,
            COALESCE(NULLIF(TRIM(t.spectral_type),''),NULLIF(TRIM(t.complete_spectral_type),'')) AS adopted_spectral_type,
            COALESCE(NULLIF(TRIM(t.moca_pid),''),NULLIF(TRIM(t.origin),'')) AS adopted_spectral_type_reference
            FROM moca_objects mo LEFT JOIN data_spectral_types t ON t.id=(SELECT MAX(a.id)
                FROM data_spectral_types a WHERE a.moca_oid=mo.moca_oid AND a.{column}=1 AND a.ignored=0)
            WHERE mo.moca_oid=%s AND mo.ignored=0""", (row["moca_oid"],))
    meta = {"candidate_id": row["id"], "moca_oid": row["moca_oid"], "moca_specid": None,
            "designation": row["designation"], "n_measured_channels": sum(not p["ignored"] for p in spectrum),
            "n_total_channels": len(product["wavelength_um"]), "ra": row["ra_deg"], "dec": row["dec_deg"], "object_origin": "MOSHPIT native DR1",
            "source_key": row["source_key"], "selection_route": row["selection_route"], "selection_type": row["spectral_type"],
            "median_snr_per_pix": row["median_snr"], "spectral_cnn_probability": row["p_accept"]}
    if objects:
        meta.update(objects[0], adopted_spt_source="private" if source == "survey" else source)
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
