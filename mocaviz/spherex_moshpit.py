"""MOSHPIT candidate spectra for the standard SPHEREx reviewer."""

import json
from datetime import datetime, timezone
from uuid import uuid4

from . import spherex_review as review
from .spherex_native_fit import NativeTemplateGrid, fit_rows_on_grid, fit_spectrum_rows

from .spherex_moshpit_queue import DESIGNATION, MIN_MAIN_TYPE, READY, TABLE, custom_priors, queue, spectral_rows


def requested(body):
    return body.get("lane") == "moshpit" or body.get("review_sample") == "moshpit"


def review_state(row):
    history = json.loads(row["review_history"] or "[]")
    latest = next((event["id"] for event in reversed(history) if event.get("lane") == "spectral"), None)
    return history, review.fingerprint([row["spectral_review"], latest])


def candidate(cur, cid, *, spectrum=False, lock=False):
    # Keep the write lock on the candidate alone. An OID assignment can arrive during a review.
    fields = ",JSON_EXTRACT(c.evidence_json,'$.chosen_fit') AS selection_evidence,c.spectrum_json,c.moca_oid,c.ra_deg,c.dec_deg,c.median_snr,c.selection_route,c.spectral_type,c.p_accept" if spectrum else ""
    if spectrum:
        missing, _ = review.aperture_review_clause("c.moca_oid", candidate_column="c.spectral_review")
        fields += f",NOT {missing} AS aperture_reviewed"
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
    evidence = json.loads(row["selection_evidence"] or "null")
    if isinstance(evidence, dict):
        meta["selection_checks"] = {key: evidence.get(key) for key in (
            "primary", "empirical_pass", "eligible_sublime4", "sublime4_channel", "sublime4_type",
            "delta", "empirical_delta", "delta_first", "delta_last",
        )}
    options = review.fit_options(body)
    templates = review.template_rows(cur)
    try:
        grid = NativeTemplateGrid(templates)
        fit, warning = fit_spectrum_rows(spectrum, grid, options), None
        standard = (
            fit_rows_on_grid(spectrum, grid, ranking_only=True)[0] if custom_priors(options) else fit
        )
        meta["main_queue_type_eligible"] = standard["best"]["spectral_type_number"] >= MIN_MAIN_TYPE
    except ValueError as exc:
        fit, warning = None, str(exc)
        meta["main_queue_type_eligible"] = False
    return {"lane": "moshpit", "read_only": False, "object": meta, "fit": fit, "raw_spectrum": spectrum,
            "state": {"spectral_review": row["spectral_review"], "aperture_reviewed": bool(row["aperture_reviewed"])},
            "warning": warning,
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
