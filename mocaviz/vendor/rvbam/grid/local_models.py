from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
from sqlalchemy import text


@dataclass(frozen=True)
class LocalModelConfig:
    base_dir: Path


class LocalHdf5ModelStore:
    def __init__(
        self,
        conn,
        moca_mgridid: str,
        config: LocalModelConfig | None = None,
        use_db_file_index: bool = True,
    ) -> None:
        try:
            import h5py  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency optional
            raise ImportError("h5py is required for --local-models.") from exc

        self._moca_mgridid = str(moca_mgridid)
        self._config = config or LocalModelConfig(base_dir=Path("model_files"))
        self._path = self._config.base_dir / f"models_{self._moca_mgridid}.h5"
        if not self._path.exists():
            raise FileNotFoundError(f"Local model file not found: {self._path}")

        db_fileid_to_gridpoint: Dict[int, int] = {}
        if use_db_file_index:
            q = text(
                "SELECT moca_mgridfileid, model_gridpoint_id "
                "FROM data_model_grid_files "
                "WHERE moca_mgridid=:gid"
            )
            rows = conn.execute(q, {"gid": self._moca_mgridid}).fetchall()
            db_fileid_to_gridpoint = {
                int(r[0]): int(r[1]) for r in rows if r[0] is not None
            }

        with h5py.File(self._path, "r") as h5:
            ids = np.array(h5["gridpoints/model_gridpoint_id"][:], dtype=int)
            self._gridpoint_row: Dict[int, int] = {int(val): int(i) for i, val in enumerate(ids)}
            local_fileid_to_gridpoint: Dict[int, int] = {}
            if "gridpoints/moca_mgridfileid" in h5:
                fileids = np.array(h5["gridpoints/moca_mgridfileid"][:], dtype=int)
                local_fileid_to_gridpoint = {
                    int(fid): int(gpid)
                    for fid, gpid in zip(fileids, ids)
                    if np.isfinite(fid)
                }
            mode = h5["spectra"].attrs.get("mode", "")
            if isinstance(mode, bytes):
                mode = mode.decode("utf-8")
            mode = str(mode)
            if mode not in ("common_grid", "ragged_concat"):
                raise ValueError(f"Unsupported local model spectra mode: {mode}")
            self._mode = mode
            self._wavelength_common = None
            if self._mode == "common_grid":
                self._wavelength_common = np.array(h5["spectra/wavelength"][:], dtype=float)
        self._fileid_to_gridpoint = local_fileid_to_gridpoint or db_fileid_to_gridpoint

    def fetch_model_spectrum(
        self,
        conn,
        moca_mgridid: str,
        moca_mgridfileid: int,
        wv_min_A: float,
        wv_max_A: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        try:
            import h5py  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency optional
            raise ImportError("h5py is required for --local-models.") from exc

        gpid = self._fileid_to_gridpoint.get(int(moca_mgridfileid))
        if gpid is None:
            return np.array([], dtype=float), np.array([], dtype=float)
        row = self._gridpoint_row.get(int(gpid))
        if row is None:
            return np.array([], dtype=float), np.array([], dtype=float)

        w0 = float(wv_min_A)
        w1 = float(wv_max_A)
        if w1 < w0:
            w0, w1 = w1, w0

        with h5py.File(self._path, "r") as h5:
            if self._mode == "common_grid":
                if self._wavelength_common is None:
                    wavelength = np.array(h5["spectra/wavelength"][:], dtype=float)
                else:
                    wavelength = self._wavelength_common
                i0, i1 = np.searchsorted(wavelength, [w0, w1], side="left")
                flux = np.array(h5["spectra/flux"][row, i0:i1], dtype=float)
                return wavelength[i0:i1], flux

            offsets = h5["spectra/offsets"]
            lengths = h5["spectra/lengths"]
            wcat = h5["spectra/wavelength_concat"]
            fcat = h5["spectra/flux_concat"]

            off = int(offsets[row])
            n = int(lengths[row])
            if n <= 0:
                return np.array([], dtype=float), np.array([], dtype=float)
            w_i = np.array(wcat[off : off + n], dtype=float)
            f_i = np.array(fcat[off : off + n], dtype=float)
            if w_i.size == 0:
                return np.array([], dtype=float), np.array([], dtype=float)
            j0, j1 = np.searchsorted(w_i, [w0, w1], side="left")
            return w_i[j0:j1], f_i[j0:j1]

    @staticmethod
    def _decode_name(value) -> str:
        if isinstance(value, (bytes, np.bytes_)):
            return value.decode("utf-8")
        return str(value)

    def load_grid_index(self):
        try:
            import h5py  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency optional
            raise ImportError("h5py is required for --local-models.") from exc

        with h5py.File(self._path, "r") as h5:
            names = [self._decode_name(n) for n in h5["parameters/names"][:]]
            values = np.array(h5["gridpoints/param_values"][:], dtype=float)
            fileids = np.array(h5["gridpoints/moca_mgridfileid"][:], dtype=int)

        axes = {name: np.unique(values[:, i]) for i, name in enumerate(names)}
        tuple_to_fileid: Dict[Tuple[float, ...], int] = {}
        for row_idx in range(values.shape[0]):
            key = tuple(float(v) for v in values[row_idx, :])
            tuple_to_fileid[key] = int(fileids[row_idx])

        from rvbam.grid.axes import GridAxes

        return names, GridAxes(axes), tuple_to_fileid

    def parameter_bounds(self) -> Dict[str, Tuple[float, float]]:
        try:
            import h5py  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency optional
            raise ImportError("h5py is required for --local-models.") from exc

        with h5py.File(self._path, "r") as h5:
            names = [self._decode_name(n) for n in h5["parameters/names"][:]]
            lows = np.array(h5["parameters/lower_bound"][:], dtype=float)
            highs = np.array(h5["parameters/upper_bound"][:], dtype=float)

        out: Dict[str, Tuple[float, float]] = {}
        for name, lo, hi in zip(names, lows, highs):
            if np.isfinite(lo) and np.isfinite(hi):
                out[name] = (float(lo), float(hi))
        return out

    def parameter_names(self) -> list[str]:
        try:
            import h5py  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency optional
            raise ImportError("h5py is required for --local-models.") from exc

        with h5py.File(self._path, "r") as h5:
            return [self._decode_name(n) for n in h5["parameters/names"][:]]

    @property
    def path(self) -> Path:
        return self._path

    @property
    def mode(self) -> str:
        return self._mode
