# rvbam/noise.py
from __future__ import annotations
import numpy as np


def inflate_uncertainties(flux_unc: np.ndarray, e_floor_abs: float) -> np.ndarray:
    """
    sigma_eff = sqrt(sigma^2 + E^2)
    """
    e = float(e_floor_abs)
    if e <= 0:
        return flux_unc
    return np.sqrt(flux_unc * flux_unc + e * e)


def e_floor_prior_from_unit(
    u: float,
    flux_err: np.ndarray,
    log10_min_relative_to_cap: float = -12.0,
    log10_max_relative_to_cap: float = 2.0,
) -> float:
    """
    Relative log-uniform prior for E_floor fraction:

      E_frac_min = 10^(log10_min_relative_to_cap)
      E_frac_max = 10^(log10_max_relative_to_cap)

    E_floor_abs = E_frac * median(flux_err)
    """
    u = float(u)
    med = float(np.nanmedian(np.abs(flux_err)))
    if not np.isfinite(med) or med <= 0:
        med = 1.0  # neutral fallback; user can override by config later

    e_min = med * (10.0 ** float(log10_min_relative_to_cap))
    e_max = med * (10.0 ** float(log10_max_relative_to_cap))

    # Avoid exactly zero
    e_min = max(e_min, np.finfo(float).tiny)

    loge = np.log(e_min) + u * (np.log(e_max) - np.log(e_min))
    return float(np.exp(loge))
