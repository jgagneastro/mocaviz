from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from rvbam.grid.axes import GridAxes
from rvbam.grid.cache import SpectrumCache
from rvbam.grid.corner_interpolator import corners_and_weights, interpolate_spectrum_corners


@dataclass(frozen=True)
class GridIndex:
    par_list: List[str]
    axes: GridAxes
    tuple_to_fileid: Dict[Tuple[float, ...], int]


class InterpolatedModelFetcher:
    def __init__(
        self,
        conn,
        moca_mgridid: str,
        grid_index: GridIndex,
        cache: SpectrumCache | None = None,
        require_full_corners: bool = True,
        nearest_only: bool = False,
    ) -> None:
        self._conn = conn
        self._moca_mgridid = moca_mgridid
        self._grid_index = grid_index
        self._cache = cache or SpectrumCache()
        self._segment_range: Tuple[float, float] | None = None
        self._require_full_corners = bool(require_full_corners)
        self._nearest_only = bool(nearest_only)
        self._warned_missing = False

    def _nearest_key(self, theta_grid: Dict[str, float]) -> Tuple[float, ...] | None:
        keys = list(self._grid_index.tuple_to_fileid.keys())
        if not keys:
            return None
        target = np.array([theta_grid[p] for p in self._grid_index.par_list], dtype=float)
        spans = np.array(
            [
                max(self._grid_index.axes.axes[p].max() - self._grid_index.axes.axes[p].min(), 1e-12)
                for p in self._grid_index.par_list
            ],
            dtype=float,
        )
        best_key = None
        best_d = np.inf
        for key in keys:
            v = np.array(key, dtype=float)
            d = np.sum(((v - target) / spans) ** 2)
            if d < best_d:
                best_d = d
                best_key = key
        return best_key

    def set_segment_range(self, wv_min_A: float, wv_max_A: float, pad_factor: float = 1.0) -> None:
        w0 = float(wv_min_A)
        w1 = float(wv_max_A)
        if w1 < w0:
            raise ValueError("Segment range must be increasing.")
        pad = float(pad_factor) * (w1 - w0)
        self._segment_range = (w0 - pad, w1 + pad)

    def fetch(self, theta_grid: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray] | None:
        if self._segment_range is None:
            raise RuntimeError("Segment range not set. Call set_segment_range first.")

        wv_min_A, wv_max_A = self._segment_range

        def model_fetcher(fid: int):
            wv, flx = self._cache.get(self._conn, self._moca_mgridid, fid, wv_min_A, wv_max_A)
            if wv.size == 0 or flx.size == 0:
                if not self._warned_missing:
                    print("Warning: missing model spectra in grid; skipping empty spectra.")
                    self._warned_missing = True
                return None
            return wv, flx

        if self._nearest_only:
            best_key = self._nearest_key(theta_grid)
            if best_key is None:
                return None
            fid = self._grid_index.tuple_to_fileid[best_key]
            return model_fetcher(fid)

        corner_list = corners_and_weights(self._grid_index.axes.axes, theta_grid, self._grid_index.par_list)

        if self._require_full_corners:
            missing = [vals for vals, _ in corner_list if vals not in self._grid_index.tuple_to_fileid]
            if missing:
                return None

        try:
            model = interpolate_spectrum_corners(corner_list, self._grid_index.tuple_to_fileid, model_fetcher)
            if model is not None:
                return model
        except ValueError:
            if not self._warned_missing:
                print("Warning: model spectra grids do not match; falling back to nearest grid point.")
                self._warned_missing = True
            model = None

        # partial-corner fallback: nearest available grid point
        if not self._require_full_corners:
            best_key = self._nearest_key(theta_grid)
            if best_key is None:
                return None
            fid = self._grid_index.tuple_to_fileid[best_key]
            return model_fetcher(fid)

        return None
