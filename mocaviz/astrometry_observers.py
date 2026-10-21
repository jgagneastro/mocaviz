"""Saved, epoch-matched spacecraft states for mixed-observer astrometry fits.

No network requests, Earth substitution or assumed stellar parallax. Earth
rows retain the existing model; JWST rows use their recorded barycentric state.
"""

import json
import math

import numpy as np


def state_from_row(row):
    if str(row.get("point_of_view") or "").strip().lower() != "jwst":
        raise ValueError("A JWST row is required")
    state = row.get("observer")
    if state is None:
        comments = row.get("comments") or {}
        if isinstance(comments, str):
            try:
                comments = json.loads(comments)
            except (ValueError, TypeError) as exc:
                raise ValueError("Invalid JWST provenance JSON") from exc
        state = comments.get("observer") if isinstance(comments, dict) else None
    if state is None:
        raise ValueError("JWST row has no saved observer state")
    if not isinstance(state, dict):
        raise TypeError("JWST observer state must be a mapping")
    if any(
        state.get(k) != v
        for k, v in {"body": "jwst", "origin": "ssb", "frame": "icrf"}.items()
    ):
        raise ValueError("JWST observer state has wrong origin/frame")
    p = np.asarray(state.get("position_au"), float)
    v = np.asarray(state.get("velocity_au_per_day"), float)
    if p.shape != (3,) or v.shape != (3,) or not np.isfinite([p, v]).all():
        raise ValueError("JWST observer state needs finite AU / AU-day vectors")
    if not 0.5 < np.linalg.norm(p) < 2 or not 0.001 < np.linalg.norm(v) < 0.06:
        raise ValueError("Implausible JWST observer units")
    mjd = float(state["epoch_mjd_utc"])
    epoch = float(row.get("plot_epoch_abs", row.get("measurement_epoch_yr")))
    if (
        not math.isfinite(mjd)
        or not math.isfinite(epoch)
        or abs((51544.5 + (epoch - 2000) * 365.25) - mjd) * 86400 > 0.1
    ):
        raise ValueError("JWST observer state does not match measurement epoch")
    return state


def attach_observers(rows):
    for row in rows:
        if str(row.get("point_of_view") or "").strip().lower() != "jwst":
            continue
        try:
            row["observer"] = state_from_row(row)
            row["observer_status"] = "epoch-matched JWST barycentric state"
            comments = row.get("comments") or {}
            if isinstance(comments, str):
                comments = json.loads(comments)
            if comments.get("independent_group"):
                row["independent_group"] = comments["independent_group"]
        except (ValueError, TypeError, KeyError) as exc:
            row["observer"] = None
            row["observer_status"] = "excluded from fit: " + str(exc)
    return rows


def apply_observers(rows, ra_deg, dec_deg, pra, pdec, dpra, dpdec):
    """Replace only spacecraft rows, including epoch-uncertainty derivatives."""
    a, d = np.deg2rad([ra_deg, dec_deg])
    east = np.array([-np.sin(a), np.cos(a), 0.0])
    north = np.array([-np.sin(d) * np.cos(a), -np.sin(d) * np.sin(a), np.cos(d)])
    output = [np.array(x, copy=True) for x in [pra, pdec, dpra, dpdec]]
    for i, row in enumerate(rows):
        pov = str(row.get("point_of_view") or "").strip().lower()
        if pov == "earth":
            continue
        if pov != "jwst":
            raise ValueError("Unsupported observer; no implicit Earth fallback")
        state = state_from_row(row)
        position = np.asarray(state["position_au"])
        velocity = np.asarray(state["velocity_au_per_day"]) * 365.25
        output[0][i] = -position @ east
        output[1][i] = -position @ north
        output[2][i] = -velocity @ east
        output[3][i] = -velocity @ north
    return tuple(output)
