# rvbam/grid/axes.py
from dataclasses import dataclass
import numpy as np
from sqlalchemy import text

@dataclass(frozen=True)
class GridAxes:
    # e.g. {'teff': np.array([...]), 'logg': np.array([...])}
    axes: dict[str, np.ndarray]

def load_grid_axes(conn, moca_mgridid: str) -> GridAxes:
    q = text("""
        SELECT moca_mgridpar, parameter_value
        FROM data_model_grid_points
        WHERE moca_mgridid=:gid
        GROUP BY moca_mgridpar, parameter_value
        ORDER BY moca_mgridpar, parameter_value
    """)
    rows = conn.execute(q, {"gid": moca_mgridid}).fetchall()
    axes: dict[str, list[float]] = {}
    for par, val in rows:
        axes.setdefault(par, []).append(float(val))
    return GridAxes({k: np.array(v, dtype=float) for k, v in axes.items()})