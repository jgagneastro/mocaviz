"""Prepare MOSAIC measurements and produce quick, reviewable SciPy fits."""
from collections import Counter
import math

import numpy as np
from scipy.linalg import lstsq

from mosaic import astrometric_calibrations as calibrations
from mosaic.astrometric_systematics import astrometric_systematics_metadata
from mosaic.parallax_branch import ParallaxBranchPolicy
from mosaic.prepare import (
    ASTROMETRY_INPUT_POLICY_VERSION, astrometry_input_policy_metadata,
    astrometry_row_is_fit_eligible, parallax_motion, prepare_payload,
)

from .astrometry_survey_offsets import add_offset_columns, fitted_survey_offsets, survey_offset_basis

FIT_VERSION = "mosaic-review-20261109-v3"
PARALLAX_POLICY = ParallaxBranchPolicy()
EXCLUDED_PSIDS = {"smss_umag", "smss_vmag", "smss_gmag", "panstarrs1_gmag", "panstarrs1_rmag"}


def canonical_mission(row):
    if str(row.get("mission_name") or "").strip().lower() in {"smss", "skymapper"}:
        return " ".join(filter(None, ("SkyMapper", row.get("data_release"))))
    return row["mission"]


def calibration_key(row):
    return (row.get("calibration_method") or "").strip()


def band_key(row):
    return (row.get("moca_psid") or "").strip() or None


def candidate_rows(rows, *, only_recalibrated=True):
    """Apply the scientific exclusions before choosing display or fit subsets."""
    for row in rows:
        if row["ignored"] or not astrometry_row_is_fit_eligible(
            row, require_recalibration_provenance=only_recalibrated
        ):
            continue
        mission = row["mission"].upper()
        psid = str(row.get("moca_psid") or "").lower()
        if (mission.startswith(("VIDEO", "VMC")) or psid in EXCLUDED_PSIDS
                or (mission == "WISE UNTIMELY" and not psid)):
            continue
        if not all(row.get(key) is not None and math.isfinite(row[key]) for key in (
            "ra", "dec", "measurement_epoch_yr", "ra_unc_mas", "dec_unc_mas"
        )):
            continue
        if row["ra_unc_mas"] <= 0 or row["dec_unc_mas"] <= 0:
            continue
        yield row


def preferred_missions(rows):
    latest = {}
    for row in rows:
        name, release = row.get("mission_name"), str(row.get("data_release") or "").upper()
        if name and release.startswith("DR") and release[2:].strip().isdigit():
            latest[name] = max(int(release[2:]), latest.get(name, 0))
    has_motion = any(row["mission"].lower().startswith("wise unwisemotion") for row in rows)
    for row in rows:
        name, release = row.get("mission_name"), str(row.get("data_release") or "").upper()
        if name in latest and release.startswith("DR") and release[2:].strip().isdigit() and int(release[2:]) < latest[name]:
            continue
        if has_motion and row["mission"].lower() == "wise untimely":
            continue
        yield canonical_mission(row)


def selected_rows(rows, *, only_recalibrated=True, missions=None, bands=(), methods=None,
                  excluded=(), ignore_duplicates=True, use_raw=False):
    candidates = list(candidate_rows(rows, only_recalibrated=only_recalibrated))
    if only_recalibrated and not candidates:
        candidates = list(candidate_rows(rows, only_recalibrated=False))
    chosen = set(preferred_missions(candidates) if missions is None else missions)
    excluded, bands = set(excluded), {tuple(pair) for pair in bands}
    methods = None if methods is None else set(methods)
    seen = set()
    for row in sorted(candidates, key=lambda item: item["id"]):
        mission = canonical_mission(row)
        if (mission not in chosen or (mission, band_key(row)) in bands or row["id"] in excluded
                or (methods is not None and calibration_key(row) not in methods)):
            continue
        ra = row["raw_ra"] if use_raw and row.get("raw_ra") is not None else row["ra"]
        dec = row["raw_dec"] if use_raw and row.get("raw_dec") is not None else row["dec"]
        key = (ra, dec, row.get("measurement_epoch_yr"), row.get("ra_unc_mas"),
               row.get("dec_unc_mas"), row.get("measurement_epoch_yr_unc"))
        if not ignore_duplicates or key not in seen:
            yield row
            seen.add(key)


def input_choices(rows, *, only_recalibrated, include_merged=False):
    candidates = list(candidate_rows(rows, only_recalibrated=only_recalibrated))
    fallback = only_recalibrated and not candidates
    if fallback:
        candidates = list(candidate_rows(rows, only_recalibrated=False))
    defaults = set(preferred_missions(candidates))
    if include_merged:
        merged = [row for row in rows if not row["ignored"] and row["single_epoch"] == 0]
        candidates.extend(merged)
        defaults.update(canonical_mission(row) for row in merged)
    missions = {}
    methods = Counter()
    for row in candidates:
        mission = canonical_mission(row)
        missions.setdefault(mission, Counter())[band_key(row)] += 1
        methods[calibration_key(row)] += 1
    return {
        "missions": [{"label": name, "count": sum(bands.values()), "default": name in defaults,
                      "bands": [{"label": band, "count": n} for band, n in sorted(bands.items(), key=lambda pair: pair[0] or "")]}
                     for name, bands in sorted(missions.items(), key=lambda pair: pair[0].casefold())],
        "methods": [{"label": label, "count": count} for label, count in sorted(methods.items())],
        "recalibratedFallback": fallback,
    }


def calibration_metadata(enabled):
    return {
        "inputPolicy": astrometry_input_policy_metadata(),
        "floors": astrometric_systematics_metadata(enabled=enabled),
        "models": [
            calibrations.ukidss_las_ra_calibration_metadata(enabled=enabled),
            calibrations.two_mass_declination_calibration_metadata(),
            calibrations.nsc_declination_calibration_metadata(enabled=False),
            calibrations.ps1_r_declination_calibration_metadata(enabled=False),
        ],
        "excludedPsids": sorted(EXCLUDED_PSIDS | {"ctio_decam_umag", "ctio_decam_gmag"}),
        "selection": [
            "All NSC, VIDEO, VMC and UKIDSS GPS astrometry, legacy SkyMapper rows, and WISE unTimely rows without a band are excluded.",
            "Canonical SMSS is displayed as SkyMapper. Prefer unWISEMotion to unTimely and newer numbered releases among remaining rows.",
            "The input selection stays in force when coordinate offsets and catalog error floors are turned off.",
        ],
        "airmass": "MOSAIC audited airmass dependencies. No airmass term passed the production calibration policy for retained rows.",
    }


def _design(dt, factors, free_parallax, indicators):
    n = len(dt)
    design = np.zeros((2 * n, 5 if free_parallax else 4))
    design[:n, 0] = design[n:, 2] = 1
    design[:n, 1] = design[n:, 3] = dt
    if free_parallax:
        design[:, 4] = factors.T.ravel()
    return add_offset_columns(design, indicators)


def _parallax_leverage(design, sigma, weights, times):
    policy = PARALLAX_POLICY
    if np.ptp(times) < policy.minimum_span_yr or len(np.unique(np.floor(times * 365.25 + 0.5))) < policy.minimum_nights:
        return "Needs ≥8 nights spanning ≥2 years."
    whitened = design * (np.sqrt(weights) / sigma)[:, None]
    _, singular, vh = np.linalg.svd(whitened, full_matrices=False)
    if len(singular) < design.shape[1] or singular[-1] <= singular[0] * 1e-10:
        return "Seasonal coverage does not constrain parallax independently."
    covariance = (vh.T / singular**2) @ vh
    unc = np.sqrt(covariance.diagonal())
    corr = np.abs(covariance[4, [1, 3]]) / (unc[4] * unc[[1, 3]])
    if unc[4] > policy.maximum_predicted_uncertainty_mas or corr.max() > policy.maximum_pm_correlation:
        return f"Insufficient parallax leverage ({unc[4]:.1f} mas predicted; PM correlation {corr.max():.2f})."
    nuisance = np.delete(whitened, 4, axis=1)
    factor = whitened[:, 4]
    residual = factor - nuisance @ lstsq(nuisance, factor)[0]
    energy = np.square(residual.reshape(2, -1)).sum(axis=0)
    _, night_index = np.unique(np.floor(times * 365.25 + 0.5), return_inverse=True)
    if np.bincount(night_index, weights=energy).max() > policy.maximum_night_information_fraction * energy.sum():
        return "One night contributes more than half of the parallax information."
    return ""


def _fit(design, y, sigma, weights, epoch_unc, factors, factor_derivatives,
         fixed_plx, fixed_unc, free_parallax, robust_fit, extra_floor):
    """Weighted least squares with epoch errors and bounded Huber influence."""
    robust = np.ones(len(y) // 2)
    params = np.zeros(design.shape[1])
    floors = np.zeros((2, 1))
    for iteration in range(6):
        rates = np.array([[params[1]], [params[3]]])
        plx = params[4] if free_parallax else fixed_plx
        nominal = np.hypot(sigma, (epoch_unc * (rates + plx * factor_derivatives.T)).ravel())
        effective = np.hypot(nominal.reshape(2, -1), floors).ravel()
        weight = np.sqrt(weights * np.tile(robust, 2)) / effective
        whitened = design * weight[:, None]
        updated, _, rank, _ = lstsq(whitened, y * weight, cond=1e-10)
        if rank < design.shape[1]:
            raise ValueError("These epochs do not constrain the selected astrometric model.")
        residuals = (y - design @ updated).reshape(2, -1)
        distance = np.linalg.norm(residuals / effective.reshape(2, -1), axis=0)
        updated_weights = np.minimum(1, 3.5 / np.maximum(distance, 1e-6)) if robust_fit and len(robust) >= 6 else robust
        updated_floors = floors
        if extra_floor and len(robust) >= 6:
            mad = 1.4826 * np.median(np.abs(residuals - np.median(residuals, axis=1, keepdims=True)), axis=1)
            nominal_variance = np.median(nominal.reshape(2, -1)**2, axis=1)
            updated_floors = np.sqrt(np.maximum(mad**2 - nominal_variance, 0))[:, None]
        converged = (np.allclose(updated, params, atol=1e-6) and np.allclose(updated_weights, robust, atol=1e-4)
                     and np.allclose(updated_floors, floors, atol=1e-4))
        params = updated
        if converged:
            break
        if iteration < 5:
            robust = updated_weights
            floors = updated_floors
    model = design @ params
    chi2 = float(np.sum(((y - model) * weight) ** 2))
    dof = max(float(2 * np.dot(weights[:len(robust)], robust) - len(params)), 1.0)
    _, singular, vh = np.linalg.svd(whitened, full_matrices=False)
    cov = ((vh.T / singular**2) @ vh) * max(1.0, chi2 / dof)
    response = None
    if not free_parallax and fixed_unc > 0:
        response = lstsq(whitened, factors.T.ravel() * weight, cond=1e-10)[0]
    return params, cov, response, chi2 / dof, model, robust, effective, floors.ravel().tolist()


def adopted_trajectory(payload, fit_reference, years):
    """Propagate the adopted reference and reported errors in the fit frame."""
    reference = payload.get("reference") or {}
    pm = payload.get("pm") or {}
    plx = payload.get("parallax") or {}
    required = [reference.get(key) for key in ("ra","dec","measurement_epoch_yr")]
    required += [pm.get(key) for key in ("pmra_masyr","pmdec_masyr")]
    if any(value is None or not math.isfinite(value) for value in required):
        return None
    ra, dec, epoch, pmra, pmdec = required
    parallax = plx.get("parallax_mas") or 0.0
    fit_ra, fit_dec = fit_reference["ra"], fit_reference["dec"]
    factors = np.array([parallax_motion(fit_ra,fit_dec,year) for year in years]).T
    epoch_factor = np.zeros(2)
    epoch_derivative = np.zeros(2)
    pov = str(reference.get("point_of_view") or "").strip().casefold()
    if not reference.get("plx_corrected") and pov in {"earth","geocentric",""}:
        epoch_factor = np.array(parallax_motion(fit_ra,fit_dec,epoch))
        epoch_derivative = (np.array(parallax_motion(fit_ra,fit_dec,epoch+1e-4))
                            - np.array(parallax_motion(fit_ra,fit_dec,epoch-1e-4)))/2e-4
    delta = np.asarray(years)-epoch
    factor_delta = factors-epoch_factor[:,None]
    offset = np.array([((ra-fit_ra+180)%360-180)*math.cos(math.radians(fit_dec)),dec-fit_dec])*3600000
    motion = np.array([pmra,pmdec])
    positions = offset[:,None] + motion[:,None]*delta + parallax*factor_delta

    def uncertainty(value):
        return value if value is not None and math.isfinite(value) and value > 0 else 0.0

    coordinate_unc = np.array([uncertainty(reference.get(key)) for key in ("ra_unc_mas","dec_unc_mas")])
    motion_unc = np.array([uncertainty(pm.get(key)) for key in ("pmra_masyr_unc","pmdec_masyr_unc")])
    epoch_unc = uncertainty(reference.get("measurement_epoch_yr_unc"))
    parallax_unc = uncertainty(plx.get("parallax_mas_unc"))
    variance = (coordinate_unc[:,None]**2 + (motion_unc[:,None]*delta)**2
                + (parallax_unc*factor_delta)**2 + ((motion+parallax*epoch_derivative)[:,None]*epoch_unc)**2)
    sigma = np.sqrt(variance)
    return {"year":years,"ra":positions[0].tolist(),"dec":positions[1].tolist(),
            "sigmaRa":sigma[0].tolist() if np.any(sigma[0]) else None,
            "sigmaDec":sigma[1].tolist() if np.any(sigma[1]) else None}


def fit_target(payload, *, offsets, calibrated, detail=True, selection=None, only_recalibrated=True,
               use_raw=False, ignore_duplicates=True, adjust_reference=True, robust_fit=True, extra_floor=False):
    selection = selection or {}
    original_rows = list(selected_rows(payload["rows"], only_recalibrated=only_recalibrated,
        use_raw=use_raw, ignore_duplicates=ignore_duplicates, **selection))
    if len(original_rows) < 2:
        raise ValueError("Fewer than two usable MOSAIC measurements.")
    prepared = prepare_payload(
        {**payload, "rows": original_rows}, apply_systematic_errors=calibrated,
        apply_ukidss_las_ra_calibration=calibrated,
        apply_nsc_declination_calibration=False, apply_ps1_r_declination_calibration=False,
        use_raw=use_raw, adjust_reference=adjust_reference, require_recalibration_provenance=False,
    )
    rows = prepared.rows
    by_id = {row["id"]: row for row in original_rows}
    if len(rows) < 2:
        raise ValueError("Fewer than two usable MOSAIC measurements.")
    times = np.array([row["plot_epoch_abs"] for row in rows])
    group = [row["independent_group"] for row in rows]
    counts = Counter(group)
    if len(counts) < 2 or np.ptp(times) <= 1 / 365.25:
        raise ValueError("The fit requires independent observations separated by more than one day.")
    weights = np.tile([1 / counts[key] for key in group], 2)
    mission = [canonical_mission(row) for row in rows]
    anchor, labels, indicators = survey_offset_basis(mission, group) if offsets else (None, [], np.zeros((len(rows), 0)))
    ref_ra, ref_dec, t0 = prepared.reference_ra, prepared.reference_dec, prepared.reference_epoch
    # MOSAIC's local tangent-plane ordinate needs a wrap at the R.A. seam.
    y_ra = [((row["plot_ra"] - ref_ra + 180) % 360 - 180) * math.cos(math.radians(ref_dec)) * 3600000 for row in rows]
    y = np.array(y_ra + [row["base_rel_dec"] for row in rows])
    dt = times - t0
    sigma = np.array([row["ra_unc_mas"] for row in rows] + [row["dec_unc_mas"] for row in rows])
    epoch_unc = np.array([row["measurement_epoch_yr_unc"] for row in rows])
    factors = np.array([parallax_motion(ref_ra, ref_dec, time) for time in times])
    derivatives = np.array([np.subtract(parallax_motion(ref_ra, ref_dec, time + 1e-4),
        parallax_motion(ref_ra, ref_dec, time - 1e-4)) / 2e-4 for time in times])
    fixed_plx = prepared.measured_parallax or 0.0
    fixed_unc = prepared.measured_parallax_unc or 0.0 if prepared.measured_parallax is not None else 0.0

    def branch(free, design):
        fixed = 0 if free else fixed_plx
        trajectory, covariance, response, chi, model, robust, effective, floors = _fit(
            design, y - fixed * factors.T.ravel(), sigma, weights, epoch_unc, factors, derivatives,
            fixed, fixed_unc, free, robust_fit, extra_floor)
        model += fixed * factors.T.ravel()
        variance = covariance.diagonal().copy()
        if response is not None:
            variance += (response * fixed_unc)**2
        uncertainty = np.sqrt(np.maximum(0,variance))
        fit = {
            "mode": "pm_plx" if free else "pm", "fitter": "scipy", "t0": t0,
            "baselineYears": float(np.ptp(times)),
            "pmra": float(trajectory[1]), "pmdec": float(trajectory[3]),
            "pmraUnc": float(uncertainty[1]), "pmdecUnc": float(uncertainty[3]),
            "plx": float(trajectory[4]) if free else None,
            "plxUnc": float(uncertainty[4]) if free else None, "fixedPlx": None if free else fixed_plx,
            "fixedPlxUnc": None if free else fixed_unc, "fittedErrorFloors": floors,
            "reducedChi2": chi, "surveyOffsets": fitted_survey_offsets(anchor, labels, trajectory[5 if free else 4:]),
        }
        if detail:
            phase_t = np.linspace(times.min(), times.max(), min(2400, max(150, int(np.ptp(times) * 32))))
            phase = np.array([parallax_motion(ref_ra, ref_dec, time) for time in phase_t])
            plx = trajectory[4] if free else fixed_plx
            base = 5 if free else 4
            prediction = _design(phase_t-t0, phase, free, np.zeros((len(phase_t),0)))
            variance = np.einsum("ij,jk,ik->i", prediction, covariance[:base,:base], prediction)
            if response is not None:
                variance += ((phase.T.ravel()-prediction @ response[:base]) * fixed_unc)**2
            curve_error = np.sqrt(np.maximum(0,variance)).reshape(2,-1)
            fit["curve"] = {
                "year": phase_t.tolist(),
                "parallaxRa": (plx * phase[:, 0]).tolist(), "parallaxDec": (plx * phase[:, 1]).tolist(),
                "sigmaRa": curve_error[0].tolist(), "sigmaDec": curve_error[1].tolist(),
                "ra": (trajectory[0] + trajectory[1] * (phase_t - t0) + plx * phase[:, 0]).tolist(),
                "dec": (trajectory[2] + trajectory[3] * (phase_t - t0) + plx * phase[:, 1]).tolist(),
            }
            fit["model"] = model.reshape(2, -1).tolist()
            fit["parallaxMotion"] = (plx * factors).T.tolist()
            fit["effectiveUncertainties"] = effective.reshape(2, -1).tolist()
            fit["weights"] = robust.tolist()
        return fit

    pm = branch(False, _design(dt, factors, False, indicators))
    plx_design = _design(dt, factors, True, indicators)
    reason = ("Needs ≥10 independent astrometric groups." if len(counts) < PARALLAX_POLICY.minimum_rows
              else _parallax_leverage(plx_design, sigma, weights, times))
    modes = {"pm": pm}
    preferred = "pm"
    if not reason:
        plx = branch(True, plx_design)
        if plx["plxUnc"] <= 0 or plx["plx"] < 3 * plx["plxUnc"]:
            reason = "Free parallax is below 3σ. Showing the PM fit."
        else:
            modes["pm_plx"] = plx
            preferred = "pm_plx"
    result = {"fits": modes, "preferred": preferred, "parallaxReason": reason, "nRows": len(rows), "nGroups": len(counts)}
    if detail:
        result["reference"] = {"ra": ref_ra, "dec": ref_dec, "year": t0}
        result["adoptedTrajectory"] = adopted_trajectory(payload, result["reference"], modes[preferred]["curve"]["year"])
        result["settings"] = {"version": FIT_VERSION, "inputPolicyVersion": ASTROMETRY_INPUT_POLICY_VERSION,
                              "calibrated": calibrated, "fitSurveyOffsets": offsets,
                              "onlyRecalibrated": only_recalibrated, "raw": use_raw,
                              "ignoreDuplicates": ignore_duplicates, "adjustReference": adjust_reference,
                              "robustFit": robust_fit, "fitExtraFloor": extra_floor, "selection": selection}
        result["measurements"] = [
            {**{key: row.get(key) for key in (
                "id", "mission_name", "data_release", "moca_psid", "moca_pid", "airmass", "origin",
                "origin_table", "measurement_epoch_yr_unc", "calibration_method", "point_of_view",
            )}, "year": float(times[i]), "mission": mission[i], "ra": float(y[i]), "dec": float(y[i + len(rows)]),
             "catalogRaDeg": by_id[row["id"]]["ra"], "catalogDecDeg": by_id[row["id"]]["dec"],
             "raDeg": row["plot_ra"], "decDeg": row["plot_dec"],
             "catalogSigmaRa": by_id[row["id"]]["ra_unc_mas"],
             "catalogSigmaDec": by_id[row["id"]]["dec_unc_mas"],
             "sigmaRa": float(sigma[i]), "sigmaDec": float(sigma[i + len(rows)]),
             "group": group[i], "groupWeight": float(weights[i]),
             "calibration": {key: value for key, value in row.items() if key.startswith((
                 "astrometric_systematic", "ukidss_las_ra_calibration"
             ))}}
            for i, row in enumerate(rows)
        ]
    return result
