from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple
import threading

import numpy as np

from rvbam.db.atmosphere_repo import fetch_model_spectrum


@dataclass
class SpectrumCacheKey:
    moca_mgridfileid: int
    wv_min_A: float
    wv_max_A: float


class SpectrumCache:
    def __init__(self, fetch_fn=None) -> None:
        self._cache: Dict[Tuple[int, float, float], Tuple[np.ndarray, np.ndarray]] = {}
        self._fetch_fn = fetch_fn or fetch_model_spectrum
        self._lock = threading.Lock()

    def __getstate__(self):
        return {"_cache": {}, "_fetch_fn": self._fetch_fn}

    def __setstate__(self, state):
        self._cache = state.get("_cache", {})
        self._fetch_fn = state.get("_fetch_fn", fetch_model_spectrum)
        self._lock = threading.Lock()

    def get(
        self,
        conn,
        moca_mgridid: str,
        moca_mgridfileid: int,
        wv_min_A: float,
        wv_max_A: float,
    ) -> Tuple[np.ndarray, np.ndarray]:
        key = (int(moca_mgridfileid), float(wv_min_A), float(wv_max_A))
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                return hit

        lam, flx = self._fetch_fn(conn, moca_mgridid, moca_mgridfileid, wv_min_A, wv_max_A)
        with self._lock:
            self._cache[key] = (lam, flx)
        return lam, flx
