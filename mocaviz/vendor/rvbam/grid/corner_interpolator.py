from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

import numpy as np
from sqlalchemy import bindparam, text


def load_gridpoint_index(conn, moca_mgridid: str, par_list: List[str]) -> Dict[Tuple[float, ...], int]:
    """
    Build mapping: tuple(param values in par_list order) -> moca_mgridfileid.
    """
    q = text(
        """
      SELECT p.model_gridpoint_id, p.moca_mgridpar, p.parameter_value, f.moca_mgridfileid
      FROM data_model_grid_points p
      JOIN data_model_grid_files f
        ON f.moca_mgridid=p.moca_mgridid AND f.model_gridpoint_id=p.model_gridpoint_id
      WHERE p.moca_mgridid=:gid AND p.moca_mgridpar IN :pars
    """
    ).bindparams(bindparam("pars", expanding=True))
    rows = conn.execute(q, {"gid": moca_mgridid, "pars": list(par_list)}).fetchall()

    by_gp: Dict[int, Dict[str, float]] = {}
    fileid_by_gp: Dict[int, int] = {}
    for gridpoint_id, par, val, fileid in rows:
        gpid = int(gridpoint_id)
        by_gp.setdefault(gpid, {})[str(par)] = float(val)
        fileid_by_gp[gpid] = int(fileid)

    tuple_to_fileid: Dict[Tuple[float, ...], int] = {}
    for gridpoint_id, d in by_gp.items():
        try:
            key = tuple(d[p] for p in par_list)
        except KeyError:
            continue
        tuple_to_fileid[key] = fileid_by_gp[gridpoint_id]

    return tuple_to_fileid


def bracket(axis: np.ndarray, x: float) -> Tuple[float, float, float]:
    """
    Returns (x0, x1, t) where x = x0*(1-t) + x1*t.
    """
    if x <= axis[0]:
        return float(axis[0]), float(axis[0]), 0.0
    if x >= axis[-1]:
        return float(axis[-1]), float(axis[-1]), 0.0
    j = int(np.searchsorted(axis, x))
    x0, x1 = axis[j - 1], axis[j]
    t = (x - x0) / (x1 - x0)
    return float(x0), float(x1), float(t)


def corners_and_weights(
    axes: Dict[str, np.ndarray],
    theta: Dict[str, float],
    par_list: List[str],
) -> List[Tuple[Tuple[float, ...], float]]:
    """
    Returns list of (corner_values_tuple, weight).
    """
    br = [bracket(axes[p], theta[p]) for p in par_list]
    lows = [b[0] for b in br]
    highs = [b[1] for b in br]
    ts = [b[2] for b in br]

    corners: List[Tuple[Tuple[float, ...], float]] = []
    for mask in range(1 << len(par_list)):
        w = 1.0
        vals = []
        for i in range(len(par_list)):
            use_high = (mask >> i) & 1
            if use_high:
                vals.append(highs[i])
                w *= ts[i]
            else:
                vals.append(lows[i])
                w *= (1.0 - ts[i])
        corners.append((tuple(vals), float(w)))
    return corners


def interpolate_spectrum_corners(
    corner_list: Iterable[Tuple[Tuple[float, ...], float]],
    tuple_to_fileid: Dict[Tuple[float, ...], int],
    model_fetcher,
) -> Tuple[np.ndarray, np.ndarray] | None:
    """
    Combine corner spectra with multilinear weights.
    model_fetcher(fileid) -> (wavelength, flux)
    Returns (wavelength, flux) or None if nothing could be fetched.
    """
    model_sum = None
    wsum = 0.0
    wv_ref = None

    for corner_vals, w in corner_list:
        if w == 0.0:
            continue
        fid = tuple_to_fileid.get(corner_vals)
        if fid is None:
            continue
        fetched = model_fetcher(fid)
        if fetched is None:
            continue
        wv, flx = fetched
        if wv_ref is None:
            wv_ref = wv
            model_sum = w * flx
        else:
            if wv.shape != wv_ref.shape or not np.allclose(wv, wv_ref, rtol=0, atol=0):
                raise ValueError("Model spectra grids do not match; cannot interpolate.")
            model_sum += w * flx
        wsum += w

    if model_sum is None or wsum == 0.0:
        return None

    return wv_ref, model_sum / wsum
