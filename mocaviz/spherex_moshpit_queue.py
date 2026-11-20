"""Use the shared review queue controls with campaign-native candidate spectra."""

import json
import math
import zlib
from collections import OrderedDict
from statistics import median
from threading import Lock

from astropy.coordinates import SkyCoord

from .spherex_native_fit import NativeTemplateGrid, VERSION, fit_rows_on_grid
from . import spherex_queue_metrics as metrics
from . import spherex_review as review

TABLE = "pcat_moshpit_candidates"
# The historical name reservation is the first identity record. Later candidates use their ID.
NUMBER = "COALESCE(CAST(JSON_VALUE(c.review_history,'$[0].moshpit_number') AS UNSIGNED),c.id)"
DESIGNATION = f"CONCAT('MOSHPIT ',{NUMBER})"
READY = "c.origin='moshpit/native_dr1' AND c.spectrum_json IS NOT NULL"
MIN_MAIN_TYPE = 10.0  # L0 on the shared spectral-type scale.
# Cache only summary numbers. A changed native spectrum gets a new digest.
_summaries = OrderedDict()
_cache_lock = Lock()


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


def custom_priors(options):
    # The sigma cap is a displayed diagnostic. Only these odds change native template ranking.
    return any(options[k] != review.DEFAULT_OPTIONS[k] for k in ("nonfield_odds_k", "nonfield_extreme_odds_k"))


def spectrum_summary(raw, grid, options):
    try:
        product = json.loads(raw)
        rows = spectral_rows(product)
        standard = fit_rows_on_grid(rows, grid, ranking_only=True)[0]
        current = fit_rows_on_grid(rows, grid, options, ranking_only=True)[0] if custom_priors(options) else standard
    except (ValueError, review.ReviewError):
        # No valid shared fit means this spectrum cannot enter the main queue.
        return None
    bands = {key: [] for key in (*review.SNR_WAVELENGTH_RANGES, "1-2")}
    bounds = {**review.SNR_WAVELENGTH_RANGES, "1-2": (1, 2)}
    terms = []
    model = product.get("template_ujy") or []
    for i, (w, f, e) in enumerate(zip(product["wavelength_um"], product["flux_ujy"], product["error_ujy"])):
        if any(v is None or not math.isfinite(v) for v in (w, f, e)) or w <= 0 or e <= 0:
            continue
        for band, limits in bounds.items():
            if limits is None or limits[0] <= w <= limits[1]:
                bands[band].append(f / e)
        if i < len(model) and model[i] is not None and math.isfinite(model[i]):
            # Same capped diagnostic as the native reviewer, evaluated on the saved survey model.
            z = (f - model[i]) / max(e, 0.1 * abs(f))
            terms.append(min(abs(z), 5.0) ** 2)
    return (
        {band: median(snr) if snr else None for band, snr in bands.items()},
        sum(terms) / len(terms) if terms else None,
        standard["best"]["spectral_type_number"],
        current["best"]["spectral_type_number"],
        current["delta_early_minus_late"],
    )


def summaries(cur, candidates, options):
    if not candidates:
        return {}
    templates = review.template_rows(cur)
    policy = (VERSION, review.fingerprint(templates), options["nonfield_odds_k"], options["nonfield_extreme_odds_k"])
    result, missing = {}, []
    with _cache_lock:
        for row in candidates:
            key = (row["candidate_id"], row["digest"], policy)
            if key in _summaries:
                result[key[0]] = _summaries[key]
                _summaries.move_to_end(key)
            else:
                missing.append(key[0])
    grid = NativeTemplateGrid(templates) if missing else None
    for start in range(0, len(missing), 256):
        ids = missing[start : start + 256]
        # MariaDB prefixes COMPRESS() results with a four-byte length.
        # Transfer compressed products only on cache misses.
        query = (
            f"SELECT id,COMPRESS(spectrum_json) AS packed,SHA2(spectrum_json,256) AS digest FROM {TABLE} WHERE id IN ("
            + ",".join(["%s"] * len(ids))
            + ")"
        )
        for row in review.rows(cur, query, tuple(ids)):
            value = spectrum_summary(zlib.decompress(row["packed"][4:]), grid, options)
            with _cache_lock:
                key = (row["id"], row["digest"], policy)
                _summaries[key] = result[row["id"]] = value
                _summaries.move_to_end(key)
                if len(_summaries) > 65536:
                    _summaries.popitem(last=False)
    return result


def vetting_conditions(body, where, params):
    classification = body.get("vetting_classification")
    if classification:
        if not isinstance(classification, str) or classification not in dict(review.CLASSIFICATIONS):
            raise review.ReviewError("Choose a valid current spectral vetting classification.")
        where.append("c.spectral_review=%s")
        params.append(classification)
    missing = body.get(
        "missing_vetting", "lane" if review.boolean(body.get("pending_only"), not classification) else "all"
    )
    if not isinstance(missing, str) or missing not in review.MISSING_VETTING_MODES:
        raise review.ReviewError("Choose a valid missing spectral-vetting scope.")
    if missing in ("lane", "viable_elsewhere"):
        where.append("c.spectral_review IS NULL")
    legacy = ("spiff", "spiffstacker", "sublimeaperture")
    if missing == "viable_elsewhere":
        viable = ",".join(["%s"] * len(review.VIABLE_OTHER_LANE))
        where.append(
            "("
            + " OR ".join(
                f"EXISTS (SELECT 1 FROM {review.LANES[k]['table']} v WHERE v.moca_oid=c.moca_oid AND v.classification IN ({viable}))"
                for k in legacy
            )
            + ")"
        )
        params.extend(review.VIABLE_OTHER_LANE * len(legacy))
    elif missing in (*legacy[:2], "both", "either"):
        keys = (missing,) if missing in legacy[:2] else legacy if missing == "both" else legacy[:2]
        operator = " OR " if missing == "either" else " AND "
        where.append(
            "("
            + operator.join(
                f"NOT EXISTS (SELECT 1 FROM {review.LANES[k]['table']} v WHERE v.moca_oid=c.moca_oid)"
                for k in keys
            )
            + ")"
        )


def queue(cur, body, count_only):
    if body.get("moca_specid") not in (None, ""):
        raise review.ReviewError("Use the MOSHPIT candidate ID for a native spectrum.")
    base = f"c.id AS candidate_id,c.moca_oid,{DESIGNATION} AS designation,c.ra_deg AS ra,c.dec_deg AS `dec`"
    direct_id = body.get("candidate_id")
    number = body.get("moshpit_number")
    if direct_id not in (None, "") or number not in (None, ""):
        if number not in (None, "") and direct_id not in (None, ""):
            raise review.ReviewError("Choose one MOSHPIT name or candidate ID.")
        by_name = number not in (None, "")
        value = review.integer(number if by_name else direct_id, "MOSHPIT number" if by_name else "Candidate ID")
        column = NUMBER if by_name else "c.id"
        records = review.rows(cur, f"SELECT {base} FROM {TABLE} c WHERE {READY} AND {column}=%s", (value,))
        return (
            {"total": len(records)}
            if count_only
            else {"lane": "moshpit", "items": records, "has_more": False, "next_after": None}
        )

    source = body.get("adopted_spt_source", "private")
    column = review.adopted_spt_column("private" if source == "survey" else source)
    order = review.queue_order(body) if "queue_order" in body else "candidate_asc"
    priority = not count_only and order in metrics.PRIORITY_ORDERS
    cnn_source = body.get("cnn_priority_source", "combined")
    if cnn_source not in ("combined", "spectral", "sublime2"):
        raise review.ReviewError("Choose combined, spectral or SUBLIME2 CNN priority.")
    where, params, joins = [READY], [], []
    vetting_conditions(body, where, params)
    oid_status = body.get("oid_status", "all")
    if oid_status not in ("all", "assigned", "unassigned"):
        raise review.ReviewError("Choose a supported MOSHPIT OID filter.")
    if oid_status != "all":
        where.append("c.moca_oid IS " + ("NULL" if oid_status == "unassigned" else "NOT NULL"))
    ids = body.get("moca_oids")
    if ids:
        if not isinstance(ids, list) or len(ids) > 500:
            raise review.ReviewError("Provide at most 500 object IDs.")
        where.append("c.moca_oid IN (" + ",".join(["%s"] * len(ids)) + ")")
        params.extend(review.integer(v, "moca_oid") for v in ids)
    if review.boolean(body.get("exclude_duplicates")):
        where.append(
            "NOT EXISTS (SELECT 1 FROM pcat_duplicated_vetting d WHERE d.potential_duplicated_moca_oid=c.moca_oid AND d.classification='y')"
        )
    if review.boolean(body.get("no_known")):
        where.append(review.exclude_known_sql("c.moca_oid"))
    motion_min = body.get("min_wiseview_score")
    if review.boolean(body.get("no_wiseview_score")):
        if motion_min not in (None, ""):
            raise review.ReviewError("Clear the minimum WiseView score to select objects without scores.")
        where.append(
            "NOT EXISTS (SELECT 1 FROM pcat_wiseview_visual_vetting v WHERE v.moca_oid=c.moca_oid AND v.classification_integer IS NOT NULL)"
        )
    elif motion_min not in (None, ""):
        where.append(
            "EXISTS (SELECT 1 FROM pcat_wiseview_visual_vetting v WHERE v.moca_oid=c.moca_oid AND v.classification_integer>=%s)"
        )
        params.append(review.bounded_float(motion_min, "Minimum WiseView score", -1, 6))

    det_lo, det_hi = review.snr_bounds(body, "sublime2_snr", "SUBLIME2 detection S/N")
    det_cuts, det_params = [], []
    for value, clause in ((det_lo, "d.detection_snr>=%s"), (det_hi, "d.detection_snr<=%s")):
        if value is not None:
            det_cuts.append(clause)
            det_params.append(value)
    if body.get("min_cnn_probability") not in (None, ""):
        det_cuts.append("d.visual_nn_good_probability>=%s")
        det_params.append(
            review.bounded_float(body["min_cnn_probability"], "Minimum SUBLIME2 CNN probability", 0, 1)
        )
    if det_cuts:
        where.append(
            "c.moca_oid IN (SELECT d.moca_oid FROM pcat_sublime_candidates_v2 d WHERE "
            + " AND ".join(det_cuts)
            + ")"
        )
        params.extend(det_params)
    if body.get("min_spectral_cnn_probability") not in (None, ""):
        where.append("c.p_accept BETWEEN %s AND 1")
        params.append(
            review.bounded_float(
                body["min_spectral_cnn_probability"], "Minimum spectral CNN probability", 0, 1
            )
        )
    fields = [base, "c.p_accept"]
    if priority and order in metrics.CNN_ORDERS and cnn_source != "spectral":
        joins.append("""LEFT JOIN (SELECT moca_oid,MAX(visual_nn_good_probability) AS probability
            FROM pcat_sublime_candidates_v2 WHERE visual_nn_good_probability BETWEEN 0 AND 1 GROUP BY moca_oid) cat
            ON cat.moca_oid=c.moca_oid""")
        fields.append("cat.probability AS catalog_cnn")

    pids = body.get("adopted_spt_moca_pids", [])
    if (
        not isinstance(pids, list)
        or len(pids) > 500
        or any(not isinstance(p, str) or not p.strip() or len(p) > 255 for p in pids)
    ):
        raise review.ReviewError("Provide at most 500 adopted-type publication IDs.")
    if pids:
        where.append(
            f"EXISTS (SELECT 1 FROM data_spectral_types d WHERE d.moca_oid=c.moca_oid AND d.{column}=1 AND d.ignored=0 AND d.moca_pid IN ("
            + ",".join(["%s"] * len(pids))
            + "))"
        )
        params.extend(p.strip() for p in pids)
    type_cut = body.get("min_sptn")
    if type_cut not in (None, "") or priority or (not count_only and order.startswith("spt_")):
        if source == "survey":
            joins.append(
                "LEFT JOIN moca_spherex_templates t ON t.moca_spherex_template_id=CAST(JSON_VALUE(c.spectrum_json,'$.template_id') AS UNSIGNED)"
            )
            # Some survey products retain the fitted label without a template ID.
            type_number = """COALESCE(t.spectral_type_number, (SELECT MAX(named.spectral_type_number)
                FROM moca_spherex_templates named WHERE named.spectral_type=c.spectral_type))"""
        else:
            joins.append(f"""LEFT JOIN data_spectral_types t ON t.id=(SELECT MAX(a.id) FROM data_spectral_types a
                WHERE a.moca_oid=c.moca_oid AND a.{column}=1 AND a.ignored=0 AND a.spectral_type_number IS NOT NULL)""")
            type_number = "t.spectral_type_number"
        fields.append(type_number + " AS sort_spt")
        if type_cut not in (None, ""):
            where.append(type_number + ">=%s")
            params.append(review.bounded_float(type_cut, "Minimum spectral type", -60, 40))
    lat = body.get("min_abs_galactic_latitude")
    lat = (
        review.bounded_float(lat, "Minimum absolute Galactic latitude", 0, 90)
        if lat not in (None, "")
        else None
    )
    low, high = review.snr_bounds(body, "snr", "spectrum median S/N")
    band = review.queue_snr_band(body)
    chi = body.get("max_reduced_chi2")
    chi = (
        review.bounded_float(chi, "Maximum stored reduced chi squared", 0, 1e9)
        if chi not in (None, "")
        else None
    )
    minimum = body.get("min_current_fit_sptn")
    minimum = (
        max(MIN_MAIN_TYPE, review.bounded_float(minimum, "Current fitted type", -60, 40))
        if minimum not in (None, "") else MIN_MAIN_TYPE
    )
    gap_min = body.get("min_current_fit_gap")
    if gap_min not in (None, ""):
        gap_min = review.bounded_float(gap_min, "Current fit separation", -math.inf, math.inf)
    else:
        gap_min = None
    options = review.fit_options(body)
    fields.append("SHA2(c.spectrum_json,256) AS digest")
    selection = f" FROM {TABLE} c " + " ".join(joins) + " WHERE " + " AND ".join(where)
    records = review.rows(cur, "SELECT " + ",".join(fields) + selection, tuple(params))
    if records and (lat is not None or (priority and order in metrics.GALACTIC_ORDERS)):
        coords = SkyCoord([r["ra"] for r in records], [r["dec"] for r in records], unit="deg")
        for row, b in zip(records, abs(coords.galactic.b.deg)):
            row["abs_b"] = float(b)
            row["sort_galactic_bin"] = 0 if b > 15 else 1 if b > 10 else 2
        if lat is not None:
            records = [r for r in records if r["abs_b"] >= lat]
    stats = summaries(cur, records, options)
    eligible = []
    for row in records:
        value = stats.get(row["candidate_id"])
        if value is None:
            continue
        snrs, reduced, standard_type, current_type, gap = value
        snr = snrs[band]
        if (
            standard_type < MIN_MAIN_TYPE or current_type < minimum
            or (gap_min is not None and (gap is None or gap < gap_min))
            or (low is not None and (snr is None or snr < low))
            or (high is not None and (snr is None or snr > high))
            or (chi is not None and (reduced is None or reduced > chi))
        ):
            continue
        row["sort_snr_1_2"] = snrs["1-2"]
        eligible.append(row)
    records = eligible
    if count_only:
        return {"total": len(records)}
    for row in records:
        if priority:
            spt = row.get("sort_spt")
            row["sort_subtype"] = None if spt is None else math.copysign(math.floor(abs(spt) + 0.5), spt)
            a, b = row.get("p_accept"), row.get("catalog_cnn")
            probability = (
                review.combined_cnn_probability(a, b)
                if cnn_source == "combined"
                else a
                if cnn_source == "spectral"
                else b
            )
            row["sort_cnn_bin"] = 0 if probability is not None and probability >= 0.8 else 1
    return ordered_page(records, order, body)


def sort_key(row, order):
    cid = row["candidate_id"]
    if order in metrics.PRIORITY_ORDERS:
        return (*metrics.priority_rank(row, order), cid)
    if order.startswith("spt_"):
        value = row["sort_spt"]
    elif order.startswith("oid_"):
        value = row["moca_oid"]
    else:
        return (cid,)
    return (value is None, -(value or 0) if order.endswith("desc") else (value or 0), cid)


def ordered_page(records, order, body):
    limit = review.integer(body.get("limit", 100), "Queue batch size", 1, 500)
    after = body.get("after")
    ranked = sorted((sort_key(row, order), row) for row in records)
    if after not in (None, 0):
        if order == "candidate_asc":
            after_key = (review.integer(after, "Candidate cursor"),)
        else:
            key = after.get("key") if isinstance(after, dict) and after.get("order") == order else None
            if (
                not isinstance(key, list)
                or not 1 <= len(key) <= 12
                or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in key)
            ):
                raise review.ReviewError("Invalid MOSHPIT queue cursor. Reload the queue.")
            if ranked and len(key) != len(ranked[0][0]):
                raise review.ReviewError("MOSHPIT queue order changed. Reload the queue.")
            after_key = tuple(key)
        ranked = [(k, r) for k, r in ranked if k > after_key]
    page = ranked[:limit]
    more = len(ranked) > limit
    last = page[-1][0] if more else None
    cursor = (last[-1] if order == "candidate_asc" else {"order": order, "key": list(last)}) if more else None
    for _, row in page:
        row.pop("digest", None)
    return {"lane": "moshpit", "items": [row for _, row in page], "has_more": more, "next_after": cursor}
