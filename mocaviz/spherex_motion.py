"""Optional human motion decisions, independent of spectral classification.

Preview/context are read-only. Signed writes and undo affect only the WiseView
vetting row and changelog, never spectral labels, types or ignored flags.
"""
from pathlib import Path
import re
from urllib.parse import urlencode

from . import spherex_review as sr
from .wiseview_review.review_helpers import CLASSIFICATION_SPECS

VERSION = 1
TABLE = "pcat_wiseview_visual_vetting"
FIELDS = (
    "moca_oid",
    "classification",
    "classification_integer",
    "comments",
    "reviewer",
    "ra_deg",
    "dec_deg",
    "wiseview_url",
    "source_table",
    "origin",
)
CHOICES = {item.key: item for item in CLASSIFICATION_SPECS}


def snapshot(cur, oid, lock=False):
    rows = sr.rows(
        cur,
        "SELECT id,"
        + ",".join("`%s`" % f for f in FIELDS)
        + ",modified_timestamp FROM "
        + TABLE
        + " WHERE moca_oid=%s"
        + (" FOR UPDATE" if lock else ""),
        (oid,),
    )
    if len(rows) > 1:
        raise sr.ReviewError(
            "Multiple motion reviews exist for this object; inspect them before editing.",
            409,
        )
    return sr.clean(rows[0]) if rows else None


def target(cur, body, *, lock=False):
    if body.get("lane") == "moshpit":
        from .spherex_moshpit_queue import TABLE as candidate_table, READY
        cid = sr.integer(body.get("candidate_id"), "MOSHPIT candidate ID")
        records = sr.rows(cur, f"""SELECT c.id AS candidate_id,c.moca_oid,c.ra_deg AS ra,c.dec_deg AS `dec`,
            c.source_key AS designation FROM {candidate_table} c WHERE c.id=%s AND {READY}"""
            + (" FOR UPDATE" if lock else ""), (cid,))
        if not records:
            raise sr.ReviewError("MOSHPIT candidate unavailable.", 404)
        obj = records[0]
        if obj["moca_oid"] != body.get("moca_oid"):
            raise sr.ReviewError("The candidate's OID changed. Reload the spectrum.", 409)
        return {**obj, "lane":"moshpit", "moca_specid":None}
    lane_key, lane = sr.lane_for(body)
    oid = sr.integer(body.get("moca_oid"), "moca_oid")
    specid = sr.integer(body.get("moca_specid"), "moca_specid")
    meta = sr.spectrum_metadata(cur, specid, oid, lane)
    ra, dec = meta.get("ra"), meta.get("dec")
    if ra is None or dec is None:
        raise sr.ReviewError("This object has no coordinates for motion review.")
    ra = sr.bounded_float(ra, "RA", 0, 360)
    dec = sr.bounded_float(dec, "Dec", -90, 90)
    return {
        "lane": lane_key,
        "moca_oid": oid,
        "moca_specid": specid,
        "ra": ra,
        "dec": dec,
        "designation": meta.get("designation"),
    }


def revision(obj, state):
    return sr.fingerprint({"target": obj, "review": state})


def choices():
    return [
        {
            "key": item.key,
            "label": item.classification,
            "score": float(item.classification_integer),
        }
        for item in CLASSIFICATION_SPECS
    ]


def context(cur, body):
    obj = target(cur, body)
    state = snapshot(cur, obj["moca_oid"]) if obj["moca_oid"] is not None else None
    return {
        "object": obj,
        "review": state,
        "revision": revision(obj, state),
        "choices": choices(),
        "motion_policy_version": VERSION,
    }


def text_field(body, name, limit):
    value = body.get(name, "")
    if not isinstance(value, str) or len(value) > limit:
        raise sr.ReviewError("Invalid motion " + name + ".")
    return value.strip()


def prepare(cur, auth, body):
    sr.require_management(auth)
    item = context(cur, body)
    if item["object"]["moca_oid"] is None:
        raise sr.ReviewError("This candidate awaits an OID for its object-level motion review.", 409)
    if body.get("revision") != item["revision"]:
        raise sr.ReviewError(
            "The position or motion review changed. Reload motion before saving.", 409
        )
    if item["review"] is not None and not sr.boolean(body.get("allow_replace")):
        raise sr.ReviewError(
            "Enable replacement to change the existing motion review.", 409
        )
    choice = (
        CHOICES.get(body.get("classification"))
        if isinstance(body.get("classification"), str)
        else None
    )
    if choice is None:
        raise sr.ReviewError("Choose a motion classification.")
    obj = item["object"]
    row = {
        "moca_oid": obj["moca_oid"],
        "classification": choice.classification,
        "classification_integer": float(choice.classification_integer),
        "comments": text_field(body, "comments", 4000),
        "reviewer": text_field(body, "reviewer", 100) or "Jonathan Gagné",
        "ra_deg": obj["ra"],
        "dec_deg": obj["dec"],
        "wiseview_url": wiseview_url(obj["ra"], obj["dec"]),
        "source_table": "pcat_moshpit_candidates" if obj["lane"] == "moshpit" else "moca_spectra",
        "origin": "mocaviz/spherex_motion.py: human review; lane=%s; moca_specid=%s"
        % (obj["lane"], obj["moca_specid"]),
    }
    if obj["lane"] == "moshpit":
        row["origin"] = f"mocaviz/spherex_motion.py: human review; MOSHPIT candidate={obj['candidate_id']}"
    plan = {"version": VERSION, "object": obj, "revision": item["revision"], "row": row}
    return {
        "dry_run": True,
        "row_counts": {TABLE: 1},
        "plan": plan,
        "receipt": sr.seal(auth, "motion-plan", plan),
    }


def write_row(cur, row, existing):
    if existing is None:
        # A competing insertion must raise rather than overwrite another review.
        sr.upsert(cur, TABLE, row, ())
    else:
        fields = [f for f in FIELDS if f != "moca_oid"]
        cur.execute(
            "UPDATE "
            + TABLE
            + " SET "
            + ",".join("`%s`=%%s" % f for f in fields)
            + " WHERE id=%s AND moca_oid=%s",
            tuple(row[f] for f in fields) + (existing["id"], row["moca_oid"]),
        )


def log(cur, auth, oid, row, undo=False):
    sr.changelog(
        cur, auth, oid, [{"table": TABLE, "rows": [row]}], 0, "gagne", undo=undo
    )


def submit(conn, cur, auth, body):
    sr.require_management(auth)
    plan = sr.unseal(auth, body.get("receipt"), "motion-plan")
    if plan.get("version") != VERSION:
        raise sr.ReviewError("Motion policy changed; reload motion before saving.", 409)
    obj = plan["object"]
    sr.lock_object(cur, obj["moca_oid"])
    current = target(cur, obj, lock=True)
    before = snapshot(cur, obj["moca_oid"], lock=True)
    if revision(current, before) != plan["revision"]:
        raise sr.ReviewError(
            "The position or motion review changed. Reload motion before saving.", 409
        )
    write_row(cur, plan["row"], before)
    after = snapshot(cur, obj["moca_oid"])
    log(cur, auth, obj["moca_oid"], plan["row"])
    token = sr.seal(
        auth,
        "motion-undo",
        {"version": VERSION, "object": obj, "before": before, "after": after},
        lifetime=86400,
    )
    conn.commit()
    return {"saved": True, "object": obj, "review": after, "undo_receipt": token}


def undo(conn, cur, auth, body):
    sr.require_management(auth)
    state = sr.unseal(auth, body.get("receipt"), "motion-undo")
    if state.get("version") != VERSION:
        raise sr.ReviewError("Motion policy changed; undo is unavailable.", 409)
    obj = state["object"]
    sr.lock_object(cur, obj["moca_oid"])
    now = snapshot(cur, obj["moca_oid"], lock=True)
    if sr.fingerprint(now) != sr.fingerprint(state["after"]):
        raise sr.ReviewError(
            "Motion review changed after your save. Undo would overwrite it.", 409
        )
    before = state["before"]
    if before is None:
        cur.execute(
            "DELETE FROM " + TABLE + " WHERE id=%s AND moca_oid=%s",
            (now["id"], obj["moca_oid"]),
        )
    else:
        write_row(cur, {f: before[f] for f in FIELDS}, now)
    log(cur, auth, obj["moca_oid"], before or {"moca_oid": obj["moca_oid"]}, undo=True)
    conn.commit()
    return {"undone": True, "object": obj, "review": before}


def wiseview_url(ra, dec):
    return "http://byw.tools/wiseview-v2#" + urlencode(
        {
            "ra": ra,
            "dec": dec,
            "size": 30,
            "band": 3,
            "speed": 500,
            "minbright": -50,
            "maxbright": 500,
            "window": 5,
            "diff_window": 1,
            "linear": 1,
            "color": "",
            "zoom": 40,
            "border": 0,
            "gaia": 1,
            "invert": 1,
            "maxdyr": 1,
            "scandir": 0,
            "neowise": 0,
            "diff": 0,
            "outer_epochs": 1,
            "unique_window": 1,
            "smooth_scan": 0,
            "shift": 0,
            "pmra": 0,
            "pmdec": 0,
        }
    )


def frame_html(prefix):
    from .sublime_findings_inspector import wiseview_html

    html = wiseview_html()
    base = prefix + "/sublime-findings/"
    html = html.replace('<base href="./">', '<base href="' + base + '">')
    for path in ("pawnstars", "xref"):
        for quote in ('"', "'"):
            html = html.replace(quote + "/" + path + quote, quote + base + path + quote)
    crosshair = (
        Path(__file__).parent / "wiseview_review" / "target_crosshair.js"
    ).read_text()
    crosshair = re.sub(r"</script", lambda _: r"<\/script", crosshair, flags=re.I)
    boot = """const p=new URLSearchParams(location.hash.slice(1));
        TargetCrosshair.install({ra_deg:Number(p.get('ra')),dec_deg:Number(p.get('dec'))});"""
    lifecycle = (Path(__file__).parent / "static" / "spherex_motion_frame.js").read_text()
    lifecycle = re.sub(r"</script", lambda _: r"<\/script", lifecycle, flags=re.I)
    # Install before the vendor's DOM-ready startup builds its swapper.
    return html.replace(
        "</head>",
        "<script>" + crosshair + "\n" + boot + "\n" + lifecycle + "</script></head>",
        1,
    )
