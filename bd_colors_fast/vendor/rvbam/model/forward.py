from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from rvbam.blaze import blaze_from_edges

C_KMS = 299792.458


@dataclass(frozen=True)
class ForwardModelConfig:
    log_grid_oversample: float = 10.0
    vsini_epsilon: float = 0.6
    conv_grid: str = "model"  # "model" or "data"


def _ensure_sorted(wavelength: np.ndarray, flux: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if wavelength.ndim != 1:
        raise ValueError("wavelength must be 1D")
    if flux.ndim != 1 or flux.shape != wavelength.shape:
        raise ValueError("flux must be 1D and match wavelength shape")
    if np.all(np.diff(wavelength) > 0):
        return wavelength, flux
    idx = np.argsort(wavelength)
    return wavelength[idx], flux[idx]


def _log_grid_from_wavelength(wavelength: np.ndarray, oversample: float = 1.0) -> Tuple[np.ndarray, float]:
    loglam = np.log(wavelength)
    dlog = float(np.median(np.diff(loglam)))
    if not np.isfinite(dlog) or dlog <= 0:
        raise ValueError("Invalid log-lambda spacing")
    dlog = dlog / float(oversample)
    n = int(np.floor((loglam[-1] - loglam[0]) / dlog)) + 1
    log_grid = loglam[0] + dlog * np.arange(n, dtype=float)
    return log_grid, dlog


def _log_grid_from_data(data_wavelength: np.ndarray, oversample: float = 1.0) -> Tuple[np.ndarray, float]:
    if data_wavelength.ndim != 1:
        raise ValueError("data_wavelength must be 1D")
    wv = np.asarray(data_wavelength, dtype=float)
    if np.any(np.diff(wv) <= 0):
        wv = np.sort(wv)
    loglam = np.log(wv)
    dlog = float(np.median(np.diff(loglam)))
    if not np.isfinite(dlog) or dlog <= 0:
        raise ValueError("Invalid data log-lambda spacing")
    dlog = dlog / float(oversample)
    n = int(np.floor((loglam[-1] - loglam[0]) / dlog)) + 1
    log_grid = loglam[0] + dlog * np.arange(n, dtype=float)
    return log_grid, dlog


def _interp_to_log_grid(log_grid: np.ndarray, wavelength: np.ndarray, flux: np.ndarray) -> np.ndarray:
    loglam = np.log(wavelength)
    return np.interp(log_grid, loglam, flux, left=flux[0], right=flux[-1])


def _shift_log_grid(flux_log: np.ndarray, log_grid: np.ndarray, rv_kms: float) -> np.ndarray:
    if rv_kms == 0.0:
        return flux_log
    delta = np.log1p(rv_kms / C_KMS)
    return np.interp(log_grid, log_grid + delta, flux_log, left=flux_log[0], right=flux_log[-1])


def _gaussian_kernel_sigma_ln(lsf_sigma_kms: float) -> float:
    return float(lsf_sigma_kms) / C_KMS


def _convolve_kernel(flux: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    if kernel.size == 1:
        return flux
    return np.convolve(flux, kernel, mode="same")


def _gaussian_kernel(dlog: float, sigma_ln: float) -> np.ndarray:
    if sigma_ln <= 0:
        return np.array([1.0], dtype=float)
    half_width = int(np.ceil(4.0 * sigma_ln / dlog))
    size = 2 * half_width + 1
    x = (np.arange(size, dtype=float) - half_width) * dlog
    k = np.exp(-0.5 * (x / sigma_ln) ** 2)
    k /= np.sum(k)
    return k


def _rotational_kernel(dlog: float, vsini_kms: float, epsilon: float) -> np.ndarray:
    if vsini_kms <= 0:
        return np.array([1.0], dtype=float)
    vmax = float(vsini_kms)
    half_width = int(np.ceil(vmax / (C_KMS * dlog)))
    size = 2 * half_width + 1
    x = (np.arange(size, dtype=float) - half_width) * dlog
    v = x * C_KMS
    mu = np.zeros_like(v)
    inside = np.abs(v) <= vmax
    mu[inside] = np.sqrt(1.0 - (v[inside] / vmax) ** 2)
    k = np.zeros_like(v)
    if np.any(inside):
        k[inside] = (
            2.0 * (1.0 - epsilon) * mu[inside]
            + 0.5 * np.pi * epsilon * (1.0 - (v[inside] / vmax) ** 2)
        )
        k /= (np.pi * vmax * (1.0 - epsilon / 3.0))
        k /= np.sum(k)
    else:
        k[half_width] = 1.0
    return k


def edges_from_centers(wavelength: np.ndarray) -> np.ndarray:
    if wavelength.ndim != 1:
        raise ValueError("wavelength must be 1D")
    if wavelength.size < 2:
        raise ValueError("wavelength must have at least 2 points to build edges")
    edges = np.empty(wavelength.size + 1, dtype=float)
    edges[1:-1] = 0.5 * (wavelength[1:] + wavelength[:-1])
    edges[0] = wavelength[0] - (edges[1] - wavelength[0])
    edges[-1] = wavelength[-1] + (wavelength[-1] - edges[-2])
    return edges


def flux_conserving_bin(
    model_wavelength: np.ndarray,
    model_flux: np.ndarray,
    edges: np.ndarray,
) -> np.ndarray:
    model_wavelength, model_flux = _ensure_sorted(model_wavelength, model_flux)
    if edges.ndim != 1 or edges.size < 2:
        raise ValueError("edges must be 1D with at least 2 values")

    cumulative = np.zeros_like(model_wavelength)
    dw = np.diff(model_wavelength)
    trapezoid = 0.5 * (model_flux[1:] + model_flux[:-1]) * dw
    cumulative[1:] = np.cumsum(trapezoid)

    i_edges = np.interp(edges, model_wavelength, cumulative, left=np.nan, right=np.nan)
    bin_flux = (i_edges[1:] - i_edges[:-1]) / (edges[1:] - edges[:-1])

    outside = (edges[:-1] < model_wavelength[0]) | (edges[1:] > model_wavelength[-1])
    if np.any(outside):
        bin_flux[outside] = np.nan

    return bin_flux


def forward_model_flux(
    model_wavelength: np.ndarray,
    model_flux: np.ndarray,
    data_wavelength: np.ndarray,
    rv_kms: float,
    lsf_sigma_kms: float,
    vsini_kms: float = 0.0,
    blaze_left: Optional[float] = None,
    blaze_right: Optional[float] = None,
    segment_bounds: Optional[Tuple[float, float]] = None,
    data_edges: Optional[np.ndarray] = None,
    config: Optional[ForwardModelConfig] = None,
) -> np.ndarray:
    """
    Core forward model:
    - shift in log-lambda (RV)
    - rotational + LSF broadening in velocity space (log-lambda)
    - flux-conserving binning to observed pixel edges
    """
    if config is None:
        config = ForwardModelConfig()

    model_wavelength_broadened, flux_log = forward_model_log_grid(
        model_wavelength,
        model_flux,
        data_wavelength=data_wavelength,
        rv_kms=rv_kms,
        lsf_sigma_kms=lsf_sigma_kms,
        vsini_kms=vsini_kms,
        blaze_left=blaze_left,
        blaze_right=blaze_right,
        segment_bounds=segment_bounds,
        config=config,
    )

    if data_edges is None:
        data_edges = edges_from_centers(data_wavelength)

    binned = flux_conserving_bin(model_wavelength_broadened, flux_log, data_edges)
    return binned


def forward_model_log_grid(
    model_wavelength: np.ndarray,
    model_flux: np.ndarray,
    rv_kms: float,
    lsf_sigma_kms: float,
    vsini_kms: float = 0.0,
    blaze_left: Optional[float] = None,
    blaze_right: Optional[float] = None,
    segment_bounds: Optional[Tuple[float, float]] = None,
    data_wavelength: Optional[np.ndarray] = None,
    config: Optional[ForwardModelConfig] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns model on the internal oversampled log-lambda grid (wavelength, flux).
    """
    if config is None:
        config = ForwardModelConfig()

    model_wavelength, model_flux = _ensure_sorted(model_wavelength, model_flux)
    if config.conv_grid == "data":
        if data_wavelength is None:
            raise ValueError("data_wavelength is required when conv_grid='data'")
        log_grid, dlog = _log_grid_from_data(data_wavelength, config.log_grid_oversample)
    else:
        log_grid, dlog = _log_grid_from_wavelength(model_wavelength, config.log_grid_oversample)
    flux_log = _interp_to_log_grid(log_grid, model_wavelength, model_flux)

    flux_log = _shift_log_grid(flux_log, log_grid, rv_kms)

    if vsini_kms > 0:
        rot_kernel = _rotational_kernel(dlog, vsini_kms, config.vsini_epsilon)
        flux_log = _convolve_kernel(flux_log, rot_kernel)

    if lsf_sigma_kms > 0:
        sigma_ln = _gaussian_kernel_sigma_ln(lsf_sigma_kms)
        gauss_kernel = _gaussian_kernel(dlog, sigma_ln)
        flux_log = _convolve_kernel(flux_log, gauss_kernel)

    model_wavelength_broadened = np.exp(log_grid)

    if blaze_left is not None and blaze_right is not None and segment_bounds is not None:
        wv_left, wv_right = segment_bounds
        blaze = blaze_from_edges(model_wavelength_broadened, wv_left, wv_right, blaze_left, blaze_right)
        flux_log = flux_log * blaze

    return model_wavelength_broadened, flux_log
