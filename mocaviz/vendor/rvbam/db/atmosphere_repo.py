# rvbam/db/atmosphere_repo.py (partial)
import numpy as np
from sqlalchemy import text

def fetch_model_spectrum(conn, moca_mgridid: str, moca_mgridfileid: int,
                         wv_min_A: float, wv_max_A: float):
    q = text("""
      SELECT wavelength_angstrom, flux_flambda
      FROM data_model_grid_spectra
      WHERE moca_mgridid=:gid
        AND moca_mgridfileid=:fid
        AND ignored=0
        AND wavelength_angstrom BETWEEN :w0 AND :w1
      ORDER BY wavelength_angstrom
    """)
    rows = conn.execute(q, {"gid": moca_mgridid, "fid": moca_mgridfileid,
                           "w0": float(wv_min_A), "w1": float(wv_max_A)}).fetchall()
    lam = np.array([r[0] for r in rows], dtype=float)
    flx = np.array([r[1] for r in rows], dtype=float)
    return lam, flx


def fetch_grid_parameter_names(conn, moca_mgridid: str) -> list[str]:
    q = text(
        """
      SELECT moca_mgridpar
      FROM moca_model_grid_parameters
      WHERE moca_mgridid=:gid
      ORDER BY moca_mgridpar
    """
    )
    rows = conn.execute(q, {"gid": moca_mgridid}).fetchall()
    return [str(r[0]) for r in rows]


def dump_model_spectra_query(
    moca_mgridid: str,
    moca_mgridfileid: int,
    wv_min_A: float,
    wv_max_A: float,
) -> str:
    return (
        "SELECT wavelength_angstrom, flux_flambda "
        "FROM data_model_grid_spectra "
        f"WHERE moca_mgridid='{moca_mgridid}' "
        f"AND moca_mgridfileid={int(moca_mgridfileid)} "
        "AND ignored=0 "
        f"AND wavelength_angstrom BETWEEN {float(wv_min_A)} AND {float(wv_max_A)} "
        "ORDER BY wavelength_angstrom"
    )
def fetch_grid_parameter_bounds(conn, moca_mgridid: str):
    q = text(
        """
      SELECT moca_mgridpar, lower_bound, upper_bound
      FROM moca_model_grid_parameters
      WHERE moca_mgridid=:gid
    """
    )
    rows = conn.execute(q, {"gid": moca_mgridid}).fetchall()
    out = {}
    for par, low, high in rows:
        if low is None or high is None:
            continue
        out[str(par)] = (float(low), float(high))
    return out


def fetch_template_name(conn, moca_mgridid: str) -> str | None:
    q = text(
        """
      SELECT file_name
      FROM data_model_grid_files
      WHERE moca_mgridid=:gid
      ORDER BY moca_mgridfileid
      LIMIT 1
    """
    )
    row = conn.execute(q, {"gid": moca_mgridid}).fetchone()
    if row is None:
        return None
    return str(row[0]) if row[0] is not None else None
