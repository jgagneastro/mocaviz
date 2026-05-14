from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np

from rvbam.model.forward import ForwardModelConfig, forward_model_flux, forward_model_log_grid
from rvbam.noise import inflate_uncertainties
from rvbam.grid.interpolated_model import InterpolatedModelFetcher


@dataclass
class SegmentData:
    wavelength: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    berv_kms: Optional[float] = None
    berv_corrected: Optional[int] = None
    edges: Optional[np.ndarray] = None
    segment_bounds: Optional[Tuple[float, float]] = None
    specid: Optional[int] = None
    window_number: Optional[int] = None
    segment_number: Optional[int] = None


class SegmentLogLikelihood:
    def __init__(
        self,
        data: SegmentData,
        model_fetcher: InterpolatedModelFetcher,
        forward_config: Optional[ForwardModelConfig] = None,
        model_flux_scale: float = 1.0,
    ) -> None:
        self._data = data
        self._model_fetcher = model_fetcher
        self._forward_config = forward_config or ForwardModelConfig()
        self._model_flux_scale = float(model_flux_scale)
        self._median_err = float(np.nanmedian(np.abs(self._data.flux_err)))
        if not np.isfinite(self._median_err) or self._median_err <= 0:
            self._median_err = 1.0

    def loglike(self, theta: Dict[str, float]) -> float:
        e_floor_frac = float(theta.get("E_floor", 0.0))
        model_on_data = self.model_on_data(theta)

        sigma_eff = inflate_uncertainties(self._data.flux_err, e_floor_frac * self._median_err)
        finite = np.isfinite(self._data.flux) & np.isfinite(model_on_data) & np.isfinite(sigma_eff)
        if not np.any(finite):
            return -np.inf

        r = (self._data.flux[finite] - model_on_data[finite]) / sigma_eff[finite]
        return float(-0.5 * np.sum(r * r + np.log(2.0 * np.pi * sigma_eff[finite] ** 2)))

    def model_on_data(self, theta: Dict[str, float]) -> np.ndarray:
        rv_kms = float(theta.get("rv_kms", 0.0))
        lsf_sigma_kms = float(theta.get("lsf_sigma_kms", 0.0))
        vsini_kms = float(theta.get("vsini_kms", 0.0))
        blaze_left = theta.get("blaze_left")
        blaze_right = theta.get("blaze_right")

        theta_grid = {
            k: v
            for k, v in theta.items()
            if k not in {"E_floor", "rv_kms", "lsf_sigma_kms", "vsini_kms", "blaze_left", "blaze_right"}
        }

        model = self._model_fetcher.fetch(theta_grid)
        if model is None:
            raise RuntimeError("Model fetch failed for provided theta.")
        model_wv, model_flux = model
        if self._model_flux_scale != 1.0:
            model_flux = model_flux * self._model_flux_scale

        return forward_model_flux(
            model_wv,
            model_flux,
            self._data.wavelength,
            rv_kms=rv_kms,
            lsf_sigma_kms=lsf_sigma_kms,
            vsini_kms=vsini_kms,
            blaze_left=blaze_left,
            blaze_right=blaze_right,
            segment_bounds=self._data.segment_bounds,
            data_edges=self._data.edges,
            config=self._forward_config,
        )

    def model_on_log_grid(self, theta: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray]:
        rv_kms = float(theta.get("rv_kms", 0.0))
        lsf_sigma_kms = float(theta.get("lsf_sigma_kms", 0.0))
        vsini_kms = float(theta.get("vsini_kms", 0.0))
        blaze_left = theta.get("blaze_left")
        blaze_right = theta.get("blaze_right")

        theta_grid = {
            k: v
            for k, v in theta.items()
            if k not in {"E_floor", "rv_kms", "lsf_sigma_kms", "vsini_kms", "blaze_left", "blaze_right"}
        }

        model = self._model_fetcher.fetch(theta_grid)
        if model is None:
            raise RuntimeError("Model fetch failed for provided theta.")
        model_wv, model_flux = model
        if self._model_flux_scale != 1.0:
            model_flux = model_flux * self._model_flux_scale

        return forward_model_log_grid(
            model_wv,
            model_flux,
            data_wavelength=self._data.wavelength,
            rv_kms=rv_kms,
            lsf_sigma_kms=lsf_sigma_kms,
            vsini_kms=vsini_kms,
            blaze_left=blaze_left,
            blaze_right=blaze_right,
            segment_bounds=self._data.segment_bounds,
            config=self._forward_config,
        )

    def model_on_grid(self, theta: Dict[str, float], wavelength_grid: np.ndarray) -> np.ndarray:
        rv_kms = float(theta.get("rv_kms", 0.0))
        lsf_sigma_kms = float(theta.get("lsf_sigma_kms", 0.0))
        vsini_kms = float(theta.get("vsini_kms", 0.0))
        blaze_left = theta.get("blaze_left")
        blaze_right = theta.get("blaze_right")

        theta_grid = {
            k: v
            for k, v in theta.items()
            if k not in {"E_floor", "rv_kms", "lsf_sigma_kms", "vsini_kms", "blaze_left", "blaze_right"}
        }

        model = self._model_fetcher.fetch(theta_grid)
        if model is None:
            raise RuntimeError("Model fetch failed for provided theta.")
        model_wv, model_flux = model
        if self._model_flux_scale != 1.0:
            model_flux = model_flux * self._model_flux_scale

        return forward_model_flux(
            model_wv,
            model_flux,
            wavelength_grid,
            rv_kms=rv_kms,
            lsf_sigma_kms=lsf_sigma_kms,
            vsini_kms=vsini_kms,
            blaze_left=blaze_left,
            blaze_right=blaze_right,
            segment_bounds=self._data.segment_bounds,
            data_edges=None,
            config=self._forward_config,
        )

    def sigma_eff(self, theta: Dict[str, float]) -> np.ndarray:
        e_floor_frac = float(theta.get("E_floor", 0.0))
        return inflate_uncertainties(self._data.flux_err, e_floor_frac * self._median_err)

    @property
    def data(self) -> SegmentData:
        return self._data
