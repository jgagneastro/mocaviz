# rvbam/blaze.py
from __future__ import annotations
import numpy as np


def blaze_from_edges(
    wavelength: np.ndarray,
    wv_left: float,
    wv_right: float,
    blaze_left: float,
    blaze_right: float,
) -> np.ndarray:
    """
    Linear blaze across the segment defined by multiplicative edge values.
    """
    denom = (wv_right - wv_left)
    if denom == 0:
        return np.full_like(wavelength, blaze_left, dtype=float)

    x = (wavelength - wv_left) / denom
    x = np.clip(x, 0.0, 1.0)
    return (1.0 - x) * blaze_left + x * blaze_right


def loguniform_from_unit(u: float, log10_min: float, log10_max: float) -> float:
    """
    Map u in [0,1] to a log-uniform value in [10^log10_min, 10^log10_max].
    """
    u = float(u)
    log10v = log10_min + u * (log10_max - log10_min)
    return float(10.0 ** log10v)