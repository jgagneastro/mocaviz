"""Pure in-memory SPHEREx fitting, ported from spherex_pipeline/spherex_autotype.py.

Only numeric functions are vendored: no DB configuration, plotting, model loading,
or file output. Keep parity with the pipeline algorithm when updating this port.
"""
from __future__ import annotations

import math
import re
from typing import Optional

import numpy as np
import pandas as pd

MAX_TEMPLATE_DIST_ANGSTROM = 100.0


MIN_MATCH_POINTS = 3


PEC_A = -0.25380665466370705


PEC_B = 0.019559107265402373


MIN_SIGMA_FLOOR_MEDIAN_FLUX_FRAC = 0.02


ROBUST_CHI2_TRIM_FRACTION = 0.05


ROBUST_CHI2_MIN_POINTS_FOR_TRIM = 20


MAX_WEIGHT_MEDIAN_RATIO = 25.0


def _clean_comparison(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["wavelength_angstrom", "flux_flambda", "flux_flambda_unc"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if "ignored" in out.columns:
        out["ignored"] = pd.to_numeric(out["ignored"], errors="coerce").fillna(0).astype(int)
    out = out.dropna(subset=["wavelength_angstrom", "flux_flambda", "flux_flambda_unc"])
    out = out[np.isfinite(out["wavelength_angstrom"])]
    out = out[np.isfinite(out["flux_flambda"]) & np.isfinite(out["flux_flambda_unc"])]
    out = out[(out["flux_flambda"] > 0) & (out["flux_flambda_unc"] > 0)]
    out = out.sort_values("wavelength_angstrom")
    return out.reset_index(drop=True)


def _nearest_model_flux(
    model_w: np.ndarray, model_f: np.ndarray, data_w: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    idx = np.searchsorted(model_w, data_w)
    idx = np.clip(idx, 1, len(model_w) - 1)

    left = idx - 1
    right = idx
    dist_left = np.abs(model_w[left] - data_w)
    dist_right = np.abs(model_w[right] - data_w)

    use_right = dist_right < dist_left
    best_idx = np.where(use_right, right, left)
    best_dist = np.where(use_right, dist_right, dist_left)
    best_flux = model_f[best_idx]
    return best_flux, best_dist


def _rolling_median_centered(values: np.ndarray, window: int) -> np.ndarray:
    w = int(window)
    if w < 1:
        w = 1
    if w % 2 == 0:
        w += 1
    return (
        pd.Series(values)
        .rolling(window=w, center=True, min_periods=1)
        .median()
        .to_numpy(dtype=float)
    )


def _flag_high_uncertainty_points(
    comp_df: pd.DataFrame,
    *,
    window_points: int = 9,
    err_factor: float = 5.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Method 1: flag points with unusually high uncertainty vs local median."""
    data_e = comp_df["flux_flambda_unc"].to_numpy(dtype=float)
    expected = _rolling_median_centered(data_e, window_points)
    floor = np.nanmedian(expected[np.isfinite(expected) & (expected > 0)])
    if not np.isfinite(floor) or floor <= 0:
        floor = 1e-30
    expected = np.where(np.isfinite(expected) & (expected > 0), expected, floor)
    flags = data_e > (float(err_factor) * expected)
    return flags.astype(bool), expected


def _flag_residual_outliers_bestfit(
    comp_df: pd.DataFrame,
    best_row: pd.Series,
    template: dict[str, object],
    *,
    min_sigma_cut: float = 5.0,
    robust_z_cut: float = 5.0,
) -> tuple[np.ndarray, float]:
    """Method 2: flag outliers in |residual|/error distribution for best-fit template."""
    data_w = comp_df["wavelength_angstrom"].to_numpy(dtype=float)
    data_f = comp_df["flux_flambda"].to_numpy(dtype=float)
    data_e = comp_df["flux_flambda_unc"].to_numpy(dtype=float)
    model_w = template["wavelength_angstrom"].astype(float)
    model_f = template["flux_flambda"].astype(float)

    mflux, dist = _nearest_model_flux(model_w, model_f, data_w)
    ok = dist <= MAX_TEMPLATE_DIST_ANGSTROM
    flags = np.zeros(len(data_w), dtype=bool)
    if not np.any(ok):
        return flags, float(min_sigma_cut)

    scale_s = best_row.get("scale_s", None)
    if scale_s is None or not np.isfinite(scale_s):
        d = data_f[ok]
        e = data_e[ok]
        m = mflux[ok]
        den = np.sum(m * m / (e * e))
        if not np.isfinite(den) or den <= 0:
            return flags, float(min_sigma_cut)
        num = np.sum(d * m / (e * e))
        scale_s = num / den

    abs_norm_resid = np.abs((data_f[ok] - float(scale_s) * mflux[ok]) / data_e[ok])
    med = float(np.nanmedian(abs_norm_resid))
    mad = float(np.nanmedian(np.abs(abs_norm_resid - med)))
    robust_sigma = 1.4826 * mad
    if not np.isfinite(robust_sigma) or robust_sigma <= 0:
        sigma_cut = float(min_sigma_cut)
    else:
        sigma_cut = max(float(min_sigma_cut), med + float(robust_z_cut) * robust_sigma)
    flags_ok = abs_norm_resid > sigma_cut
    flags[np.where(ok)[0][flags_ok]] = True
    return flags, float(sigma_cut)


def _robust_chi2_mean(contrib: np.ndarray) -> tuple[Optional[float], int, int]:
    vals = np.asarray(contrib, dtype=float)
    vals = vals[np.isfinite(vals)]
    n = int(len(vals))
    if n <= 0:
        return None, 0, 0
    trim_n = 0
    if n >= ROBUST_CHI2_MIN_POINTS_FOR_TRIM:
        trim_n = int(math.floor(n * ROBUST_CHI2_TRIM_FRACTION))
        trim_n = min(trim_n, max(0, n - MIN_MATCH_POINTS))
    if trim_n > 0:
        vals = np.sort(vals)[: n - trim_n]
    return float(np.mean(vals)), int(len(vals)), int(trim_n)


def _compute_chi2(
    data_w: np.ndarray,
    data_f: np.ndarray,
    data_e: np.ndarray,
    model_w: np.ndarray,
    model_f: np.ndarray,
    drop_worst_n: int,
    chi2_sigma_cap: float,
) -> dict[str, Optional[float]]:
    if len(model_w) < 2:
        return {
            "n_used": 0,
            "scale_s": None,
            "reduced_chi2": None,
            "chi2_raw": None,
            "chi2_raw_10pct": None,
            "reduced_chi2_10pct": None,
            "red_chi2_raw_10pct": None,
            "red_chi2_10pct": None,
            "n_red_used": None,
            "chi2_raw_10pct_cap": None,
            "reduced_chi2_10pct_cap": None,
        }

    mflux, dist = _nearest_model_flux(model_w, model_f, data_w)
    ok = dist <= MAX_TEMPLATE_DIST_ANGSTROM
    if not np.any(ok):
        return {
            "n_used": 0,
            "scale_s": None,
            "reduced_chi2": None,
            "chi2_raw": None,
            "chi2_raw_10pct": None,
            "reduced_chi2_10pct": None,
            "red_chi2_raw_10pct": None,
            "red_chi2_10pct": None,
            "n_red_used": None,
            "chi2_raw_10pct_cap": None,
            "reduced_chi2_10pct_cap": None,
        }

    w = data_w[ok]
    d = data_f[ok]
    e = data_e[ok]
    m = mflux[ok]
    med_flux = float(np.nanmedian(d))
    if not np.isfinite(med_flux) or med_flux <= 0:
        med_flux = float(np.nanmedian(data_f[np.isfinite(data_f) & (data_f > 0)]))
    if not np.isfinite(med_flux) or med_flux <= 0:
        med_flux = 0.0
    # Prevent near-zero flux points from getting unrealistically tiny sigma floors.
    d_for_floor = np.maximum(d, MIN_SIGMA_FLOOR_MEDIAN_FLUX_FRAC * med_flux)

    # Use the same 10%-of-flux uncertainty floor for scale fitting as for scoring.
    sigma_eff = np.maximum(e, 0.1 * d_for_floor)
    weights = 1.0 / (sigma_eff * sigma_eff)
    med_w = float(np.nanmedian(weights[np.isfinite(weights) & (weights > 0)]))
    if np.isfinite(med_w) and med_w > 0:
        weights = np.minimum(weights, MAX_WEIGHT_MEDIAN_RATIO * med_w)
    num = np.sum(d * m * weights)
    den = np.sum(m * m * weights)
    n_used = len(d)

    if n_used < MIN_MATCH_POINTS or not np.isfinite(den) or den <= 0:
        return {
            "n_used": n_used,
            "scale_s": None,
            "reduced_chi2": None,
            "chi2_raw": None,
            "chi2_raw_10pct": None,
            "reduced_chi2_10pct": None,
            "red_chi2_raw_10pct": None,
            "red_chi2_10pct": None,
            "n_red_used": None,
            "chi2_raw_10pct_cap": None,
            "reduced_chi2_10pct_cap": None,
        }

    s = num / den
    resid = (d - s * m)
    contrib = (resid * resid) * weights
    if drop_worst_n > 0:
        if n_used <= drop_worst_n:
            return {
                "n_used": n_used,
                "scale_s": float(s),
                "reduced_chi2": None,
                "chi2_raw": None,
                "chi2_raw_10pct": None,
                "reduced_chi2_10pct": None,
                "red_chi2_raw_10pct": None,
                "red_chi2_10pct": None,
                "n_red_used": None,
                "chi2_raw_10pct_cap": None,
                "reduced_chi2_10pct_cap": None,
            }
        keep_idx = np.argsort(contrib)[: n_used - drop_worst_n]
        w = w[keep_idx]
        d = d[keep_idx]
        e = e[keep_idx]
        m = m[keep_idx]
        n_used = len(d)
        med_flux = float(np.nanmedian(d))
        if not np.isfinite(med_flux) or med_flux <= 0:
            med_flux = float(np.nanmedian(data_f[np.isfinite(data_f) & (data_f > 0)]))
        if not np.isfinite(med_flux) or med_flux <= 0:
            med_flux = 0.0
        d_for_floor = np.maximum(d, MIN_SIGMA_FLOOR_MEDIAN_FLUX_FRAC * med_flux)
        sigma_eff = np.maximum(e, 0.1 * d_for_floor)
        weights = 1.0 / (sigma_eff * sigma_eff)
        med_w = float(np.nanmedian(weights[np.isfinite(weights) & (weights > 0)]))
        if np.isfinite(med_w) and med_w > 0:
            weights = np.minimum(weights, MAX_WEIGHT_MEDIAN_RATIO * med_w)
        num = np.sum(d * m * weights)
        den = np.sum(m * m * weights)
        if not np.isfinite(den) or den <= 0 or n_used < MIN_MATCH_POINTS:
            return {
                "n_used": n_used,
                "scale_s": None,
                "reduced_chi2": None,
                "chi2_raw": None,
                "chi2_raw_10pct": None,
                "reduced_chi2_10pct": None,
                "red_chi2_raw_10pct": None,
                "red_chi2_10pct": None,
                "n_red_used": None,
                "chi2_raw_10pct_cap": None,
                "reduced_chi2_10pct_cap": None,
            }
        s = num / den
        resid = (d - s * m)
        contrib = (resid * resid) * weights

    chi2_raw = float(np.sum(contrib))
    reduced = chi2_raw / n_used
    sigma_eff = np.maximum(e, 0.1 * d_for_floor)
    weights = 1.0 / (sigma_eff * sigma_eff)
    med_w = float(np.nanmedian(weights[np.isfinite(weights) & (weights > 0)]))
    if np.isfinite(med_w) and med_w > 0:
        weights = np.minimum(weights, MAX_WEIGHT_MEDIAN_RATIO * med_w)
    contrib_10pct = (resid * resid) * weights
    chi2_raw_10pct = float(np.sum(contrib_10pct))
    reduced_10pct = chi2_raw_10pct / n_used
    cap2 = float(chi2_sigma_cap) * float(chi2_sigma_cap)
    contrib_10pct_cap = np.minimum(contrib_10pct, cap2)
    chi2_raw_10pct_cap = float(np.sum(contrib_10pct_cap))
    reduced_10pct_cap = chi2_raw_10pct_cap / n_used
    robust_reduced_10pct_cap, robust_n_used, robust_trimmed_n = _robust_chi2_mean(
        contrib_10pct_cap
    )
    robust_chi2_raw_10pct_cap = (
        float(robust_reduced_10pct_cap) * n_used
        if robust_reduced_10pct_cap is not None
        else None
    )
    red_mask = w >= 14000.0
    n_red_used = int(np.sum(red_mask))
    if n_red_used > 0:
        red_contrib_10pct = contrib_10pct[red_mask]
        red_contrib_10pct_cap = contrib_10pct_cap[red_mask]
        red_chi2_raw_10pct_uncapped = float(np.sum(red_contrib_10pct))
        red_chi2_10pct_uncapped = red_chi2_raw_10pct_uncapped / n_red_used
        red_chi2_raw_10pct_cap = float(np.sum(red_contrib_10pct_cap))
        red_chi2_10pct_cap = red_chi2_raw_10pct_cap / n_red_used
        red_robust_chi2_10pct_cap, red_robust_n_used, red_robust_trimmed_n = _robust_chi2_mean(
            red_contrib_10pct_cap
        )
        red_chi2_raw_10pct = (
            float(red_robust_chi2_10pct_cap) * n_red_used
            if red_robust_chi2_10pct_cap is not None
            else None
        )
        red_chi2_10pct = red_robust_chi2_10pct_cap
    else:
        red_chi2_raw_10pct_uncapped = None
        red_chi2_10pct_uncapped = None
        red_chi2_raw_10pct_cap = None
        red_chi2_10pct_cap = None
        red_robust_n_used = 0
        red_robust_trimmed_n = 0
        red_chi2_raw_10pct = None
        red_chi2_10pct = None
    return {
        "n_used": n_used,
        "scale_s": float(s),
        "reduced_chi2": float(reduced),
        "chi2_raw": float(chi2_raw),
        "chi2_raw_10pct": float(chi2_raw_10pct),
        "reduced_chi2_10pct": float(reduced_10pct),
        "red_chi2_raw_10pct": red_chi2_raw_10pct,
        "red_chi2_10pct": red_chi2_10pct,
        "n_red_used": n_red_used,
        "red_chi2_raw_10pct_uncapped": red_chi2_raw_10pct_uncapped,
        "red_chi2_10pct_uncapped": red_chi2_10pct_uncapped,
        "red_chi2_raw_10pct_cap": red_chi2_raw_10pct_cap,
        "red_chi2_10pct_cap": red_chi2_10pct_cap,
        "red_robust_n_used": red_robust_n_used,
        "red_robust_trimmed_n": red_robust_trimmed_n,
        "chi2_raw_10pct_cap": float(chi2_raw_10pct_cap),
        "reduced_chi2_10pct_cap": float(reduced_10pct_cap),
        "robust_chi2_raw_10pct_cap": robust_chi2_raw_10pct_cap,
        "robust_reduced_chi2_10pct_cap": robust_reduced_10pct_cap,
        "robust_n_used": robust_n_used,
        "robust_trimmed_n": robust_trimmed_n,
    }


def _autotype(
    comp_df: pd.DataFrame,
    templates: dict[int, dict[str, object]],
    drop_worst_n: int,
    chi2_sigma_cap: float,
    nonfield_odds_k: float,
    nonfield_extreme_odds_k: float,
) -> pd.DataFrame:
    data_w = comp_df["wavelength_angstrom"].to_numpy(dtype=float)
    data_f = comp_df["flux_flambda"].to_numpy(dtype=float)
    data_e = comp_df["flux_flambda_unc"].to_numpy(dtype=float)

    rows = []
    penalty_nonfield = 2.0 * math.log(float(nonfield_odds_k))
    penalty_nonfield_extreme = 2.0 * math.log(float(nonfield_extreme_odds_k))
    for tid, t in templates.items():
        model_w = t["wavelength_angstrom"]
        model_f = t["flux_flambda"]
        result = _compute_chi2(
            data_w, data_f, data_e, model_w, model_f, drop_worst_n, chi2_sigma_cap
        )
        grid_type = str(t.get("grid_type") or "")
        grid_norm = grid_type.strip().lower()
        if grid_norm == "field":
            penalty = 0.0
        elif grid_norm in {"extreme subdwarfs", "extremely low gravity"}:
            penalty = penalty_nonfield_extreme
        else:
            penalty = penalty_nonfield
        score = None
        robust_score_chi2 = result.get("robust_chi2_raw_10pct_cap")
        if robust_score_chi2 is None:
            robust_score_chi2 = result.get("chi2_raw_10pct_cap")
        if robust_score_chi2 is not None:
            score = float(robust_score_chi2) + float(penalty)
        rows.append(
            {
                "moca_spherex_template_id": tid,
                "spectral_type": t["spectral_type"],
                "spectral_type_number": t["spectral_type_number"],
                "grid_type": t.get("grid_type"),
                "selection_penalty": float(penalty),
                "selection_score": score,
                **result,
            }
        )

    df = pd.DataFrame(rows)
    df = df.sort_values(
        ["selection_score", "spectral_type_number"],
        ascending=[True, True],
        na_position="last",
    )
    return df.reset_index(drop=True)


def _build_autotype_spectral_type_db_values(
    *,
    moca_oid: int,
    moca_specid: Optional[int],
    best_row: pd.Series,
    code_name: str,
    calculation_method: str,
    ignored_value: int,
    provenance_note: Optional[str] = None,
) -> tuple[object, ...]:
    """Build the canonical private autotype SPT row used by all upsert paths."""
    def _fmt2(x: Optional[float]) -> str:
        if x is None or (not np.isfinite(x)):
            return "NULL"
        return f"{float(x):.2f}"

    spectral_type = _format_spt_with_pec_suffix(
        best_row.get("spectral_type"),
        best_row.get("spectral_type_number"),
        best_row.get("red_chi2_10pct"),
    )
    spectral_type_number = pd.to_numeric(best_row.get("spectral_type_number"), errors="coerce")
    spectral_type_number = float(spectral_type_number) if np.isfinite(spectral_type_number) else None
    reduced_chi2 = pd.to_numeric(best_row.get("reduced_chi2"), errors="coerce")
    reduced_chi2 = float(reduced_chi2) if np.isfinite(reduced_chi2) else None
    selection_score = pd.to_numeric(best_row.get("selection_score"), errors="coerce")
    selection_score = float(selection_score) if np.isfinite(selection_score) else None
    reduced_chi2_10pct_cap = pd.to_numeric(best_row.get("reduced_chi2_10pct_cap"), errors="coerce")
    reduced_chi2_10pct_cap = float(reduced_chi2_10pct_cap) if np.isfinite(reduced_chi2_10pct_cap) else None
    robust_reduced_chi2_10pct_cap = pd.to_numeric(best_row.get("robust_reduced_chi2_10pct_cap"), errors="coerce")
    robust_reduced_chi2_10pct_cap = (
        float(robust_reduced_chi2_10pct_cap)
        if np.isfinite(robust_reduced_chi2_10pct_cap)
        else None
    )
    chi2_raw_10pct = pd.to_numeric(best_row.get("chi2_raw_10pct"), errors="coerce")
    chi2_raw_10pct = float(chi2_raw_10pct) if np.isfinite(chi2_raw_10pct) else None
    red_chi2_10pct_uncapped = pd.to_numeric(best_row.get("red_chi2_10pct_uncapped"), errors="coerce")
    red_chi2_10pct_uncapped = float(red_chi2_10pct_uncapped) if np.isfinite(red_chi2_10pct_uncapped) else None
    red_chi2_10pct = pd.to_numeric(best_row.get("red_chi2_10pct"), errors="coerce")
    red_chi2_10pct = float(red_chi2_10pct) if np.isfinite(red_chi2_10pct) else None
    red_chi2_raw_10pct = pd.to_numeric(best_row.get("red_chi2_raw_10pct"), errors="coerce")
    red_chi2_raw_10pct = float(red_chi2_raw_10pct) if np.isfinite(red_chi2_raw_10pct) else None
    pec_ratio = _compute_pec_ratio(spectral_type_number, red_chi2_10pct)
    grid_type = str(best_row.get("grid_type") or "")
    suffix_base, gravity_class = _grid_suffix_and_gravity(grid_type)
    has_pec = spectral_type.lower().endswith(" pec")
    suffix = suffix_base
    if has_pec:
        suffix = f"{suffix};pec" if suffix else "pec"
    simple_spectral_type = _derive_simple_spectral_type(spectral_type)
    spectral_class = simple_spectral_type[0] if simple_spectral_type else None
    template_id = pd.to_numeric(best_row.get("moca_spherex_template_id"), errors="coerce")
    template_id = int(template_id) if np.isfinite(template_id) else None
    comments = (
        f"Auto-upserted by {code_name}; "
        f"template_id={template_id}; "
        f"grid_type={grid_type or 'NULL'}; "
        f"reduced_chi2={_fmt2(reduced_chi2)}; "
        f"selection_score={_fmt2(selection_score)}; "
        f"reduced_chi2_10pct_cap={_fmt2(reduced_chi2_10pct_cap)}; "
        f"robust_reduced_chi2_10pct_cap={_fmt2(robust_reduced_chi2_10pct_cap)}; "
        f"chi2_raw_10pct={_fmt2(chi2_raw_10pct)}; "
        f"red_chi2_10pct_uncapped={_fmt2(red_chi2_10pct_uncapped)}; "
        f"red_chi2_10pct={_fmt2(red_chi2_10pct)}; "
        f"red_chi2_raw_10pct={_fmt2(red_chi2_raw_10pct)}; "
        f"pec_metric={_fmt2(pec_ratio)}"
    )
    if provenance_note:
        comments = f"{comments}; {str(provenance_note).strip()}"

    return (
        int(moca_oid),
        int(moca_specid) if moca_specid is not None else None,
        "spherex",
        spectral_type,
        spectral_type,
        spectral_type_number,
        0.5,
        spectral_class,
        "E",
        0,
        simple_spectral_type,
        "near_infrared",
        "spherex",
        code_name,
        calculation_method,
        suffix,
        gravity_class,
        int(ignored_value),
        0,
        "gagne",
        comments,
    )


def _format_spt_with_pec_suffix(
    spectral_type: object,
    spectral_type_number: object,
    red_chi2_10pct: object,
) -> str:
    spt_display = str(spectral_type)
    try:
        pec_ratio = _compute_pec_ratio(spectral_type_number, red_chi2_10pct)
        if pec_ratio is not None:
            spt_lower = spt_display.lower()
            has_explicit_suffix_or_gravity = (
                ("pec" in spt_lower)
                or ("gamma" in spt_lower)
                or ("beta" in spt_lower)
                or ("alpha" in spt_lower)
            )
            if pec_ratio >= 2.0 and (not has_explicit_suffix_or_gravity):
                spt_display = f"{spt_display} pec"
    except Exception:
        pass
    return spt_display


def _compute_pec_ratio(
    spectral_type_number: object,
    red_chi2_10pct: object,
) -> Optional[float]:
    sptn = pd.to_numeric(spectral_type_number, errors="coerce")
    red_val = pd.to_numeric(red_chi2_10pct, errors="coerce")
    if not (np.isfinite(sptn) and np.isfinite(red_val)):
        return None
    denom = 10.0 ** (PEC_A + PEC_B * float(sptn))
    if not (np.isfinite(denom) and denom > 0):
        return None
    return float(red_val) / float(denom)


def _grid_suffix_and_gravity(grid_type: object) -> tuple[Optional[str], Optional[str]]:
    g = str(grid_type or "").strip().lower()
    if g == "extremely low gravity":
        return None, "δ"
    if g == "very low gravity":
        return None, "γ"
    if g == "intermediate gravity":
        return None, "β"
    if g == "subdwarfs":
        return "sd", None
    if g == "slight subdwarfs":
        return "d/sd", None
    if g == "extreme subdwarfs":
        return "esd", None
    return None, None


def _derive_simple_spectral_type(spectral_type: object) -> Optional[str]:
    s = str(spectral_type or "").strip()
    if s == "":
        return None
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"^(esd|d/sd|sd)", "", s, flags=re.IGNORECASE)
    s = s.replace("γ", "").replace("β", "").replace("α", "").replace("δ", "")
    s = re.sub(r"(gamma|beta|alpha|delta|pec)", "", s, flags=re.IGNORECASE)
    m = re.search(r"([OBAFGKMLTY][0-9](?:\.[0-9])?)", s, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).upper()




DEFAULT_OPTIONS = {
    "drop_worst_n": 5, "chi2_sigma_cap": 5.0,
    "nonfield_odds_k": 500.0, "nonfield_extreme_odds_k": 500000.0,
}


def fit_spectrum(rows, template_rows, options=None):
    """Run the pipeline's two-pass fit and return only JSON-compatible data."""
    if not rows:
        raise ValueError("No spectral data points are available.")
    options = {**DEFAULT_OPTIONS, **(options or {})}
    comp = _clean_comparison(pd.DataFrame(rows))
    if len(comp) < MIN_MATCH_POINTS:
        raise ValueError("Not enough positive, finite spectral points with uncertainties.")
    templates = {}
    for row in template_rows:
        tid = int(row["moca_spherex_template_id"])
        t = templates.setdefault(tid, {
            key: row.get(key) for key in ("spectral_type", "spectral_type_number", "grid_type")
        })
        t.setdefault("wavelength_angstrom", []).append(float(row["wavelength_angstrom"]))
        t.setdefault("flux_flambda", []).append(float(row["flux_flambda"]))
    if not templates:
        raise ValueError("No active SPHEREx templates are available.")
    for template in templates.values():
        for key in ("wavelength_angstrom", "flux_flambda"):
            template[key] = np.asarray(template[key], dtype=float)
    ignored = comp["ignored"].to_numpy(dtype=int) == 1
    fit_indices = np.flatnonzero(~ignored)
    # Do not resurrect DB-ignored pixels when there are too few to fit.
    if len(fit_indices) < MIN_MATCH_POINTS:
        raise ValueError("Not enough non-ignored spectral points for fitting.")
    fit = comp.iloc[fit_indices].reset_index(drop=True)
    def calculate(data):
        return _autotype(data, templates, **options)
    first = calculate(fit)
    finite = first[first.selection_score.notna()]
    if finite.empty:
        raise ValueError("No template has enough matching wavelength points; reduce dropped points.")
    bad_error, _ = _flag_high_uncertainty_points(fit)
    bad_residual = np.zeros(len(fit), dtype=bool)
    best = finite.iloc[0]
    label = _format_spt_with_pec_suffix(
        best.spectral_type, best.spectral_type_number, best.red_chi2_10pct)
    if "pec" not in label.lower():
        bad_residual, _ = _flag_residual_outliers_bestfit(
            fit, best, templates[int(best.moca_spherex_template_id)])
    bad = bad_error | bad_residual
    final = calculate(fit[~bad].reset_index(drop=True)) if (~bad).sum() >= MIN_MATCH_POINTS else first
    finite = final[final.selection_score.notna()]
    if finite.empty:
        finite = first[first.selection_score.notna()]
    flagged = ignored.copy()
    flagged[fit_indices] |= bad
    records = []
    overlays = []
    for rank, (_, row) in enumerate(finite.iterrows()):
        record = row.to_dict()
        record["display_type"] = _format_spt_with_pec_suffix(
            row.spectral_type, row.spectral_type_number, row.red_chi2_10pct)
        record["pec_metric"] = _compute_pec_ratio(row.spectral_type_number, row.red_chi2_10pct)
        records.append(record)
        if rank < 3:
            template = templates[int(row.moca_spherex_template_id)]
            overlays.append({
                "label": record["display_type"], "grid": row.grid_type,
                "wavelength_um": (template["wavelength_angstrom"] / 1e4).tolist(),
                "flux": (template["flux_flambda"] * float(row.scale_s)).tolist(),
            })
    return {
        "best": records[0], "matches": records, "overlays": overlays,
        "spectrum": {
            "wavelength_um": (comp.wavelength_angstrom.to_numpy() / 1e4).tolist(),
            "flux": comp.flux_flambda.tolist(), "error": comp.flux_flambda_unc.tolist(),
            "flagged": flagged.tolist(),
        },
        "bad_pixel_ids": [int(v) for v in comp.loc[flagged & ~ignored, "data_spectra_id"]],
        "options": options,
    }
