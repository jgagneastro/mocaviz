import dash
import io
import contextlib
import logging
from collections import deque
import threading
from math import floor, log10
import numpy as np
import decimal
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objs as go
from urllib.parse import quote_plus as urlquote, urlparse, parse_qs
from sqlalchemy import create_engine, select, MetaData, Table, func, and_, or_, cast, String, case, Column, Integer, Float, Text, text
import pandas as pd
import os
from utils.plx_motion import parallax_motion
from scipy.optimize import curve_fit
from astropy.time import Time
from PyAstronomy.pyasl import sunpos

from datetime import datetime

# ---- Astrometry page version stamp ----
ASTROMETRY_PAGE_VERSION = "2026-02-17-debug-v1"

# Register the page after layout is defined (see below).

# ---- Server-side request logging (helps debug when you can't access browser DevTools) ----
try:
    _app = dash.get_app()
    _server = _app.server
    if not getattr(_server, "_mocaviz_request_logger", False):
        _server._mocaviz_request_logger = True

        @_server.before_request
        def _mocaviz_log_request():
            try:
                from flask import request
                path = request.path or ""
                # One-time: log whether astrometry plot callbacks are registered (runs after module import)
                if not getattr(_server, "_mocaviz_logged_astrometry_callbacks", False):
                    try:
                        import sys
                        cb_keys = list(getattr(_app, "callback_map", {}).keys())
                        ast_keys = [k for k in cb_keys if "astrometry-plot-ra" in k or "astrometry-plot-dec" in k]
                        sys.stderr.write(f"[mocaviz:init] astrometry plot callback keys (first request): {ast_keys}\n")
                        sys.stderr.flush()
                    except Exception:
                        pass
                    _server._mocaviz_logged_astrometry_callbacks = True
                # Focus on Dash update traffic + this page
                if path.startswith("/_dash") or "astrometry" in path:
                    import sys

                    # For Dash update requests, log which output(s) are being updated.
                    if path == "/_dash-update-component" and request.method == "POST":
                        try:
                            payload = request.get_json(silent=True) or {}
                            out = payload.get("output")
                            outs = payload.get("outputs")
                            sys.stderr.write(f"[mocaviz:dash] outputs={out or outs}\n")
                        except Exception:
                            pass

                    sys.stderr.write(
                        f"[mocaviz:req] {request.method} {path} len={request.content_length} remote={request.remote_addr}\n"
                    )
                    sys.stderr.flush()
            except Exception:
                pass

        @_server.after_request
        def _mocaviz_log_response(response):
            try:
                from flask import request
                path = request.path or ""
                if path.startswith("/_dash") or "astrometry" in path:
                    import sys
                    sys.stderr.write(
                        f"[mocaviz:resp] {request.method} {path} -> {response.status_code}\n"
                    )
                    sys.stderr.flush()
            except Exception:
                pass
            return response
except Exception:
    # If pages are imported before the Dash app exists, skip logging.
    pass

figure_export_config = {
  'toImageButtonOptions': {
    'format': 'png', # one of png, svg, jpeg, webp
    'height': 700,
    'width': 1900,
    'scale': 2 # Multiply title/legend/axis/canvas sizes by this factor
  }
}

# ---- DB connection helper (avoid globals; safe for multi-worker deployments) ----

def _parse_url_search(url_search: str):
    """Parse Dash dcc.Location.search (e.g. '?a=1&b=2') into a dict."""
    return parse_qs((url_search or "").lstrip("?"))


def get_engine_from_url(url_search: str):
    """Build a SQLAlchemy engine from URL query params or environment defaults."""
    parsed = _parse_url_search(url_search)

    default_host = 'mocadb.ca'
    default_username = 'public'
    default_password = 'z@nUg_2h7_%?31y88'
    default_dbname = 'mocadb'

    env_username = parsed.get('user', [None])[0] or os.environ.get('MOCA_USERNAME', default_username)
    env_password = parsed.get('pwd', [None])[0] or os.environ.get('MOCA_PASSWORD', default_password)
    env_dbname = parsed.get('dbase', [None])[0] or os.environ.get('MOCA_DBNAME', default_dbname)
    env_host = os.environ.get('MOCA_HOST', default_host)

    conn_str = f'mysql+pymysql://{env_username}:{urlquote(env_password)}@{env_host}/{env_dbname}'
    return create_engine(conn_str)

bin_size_days = 50
bin_size_days_phased = 20

figure_export_config = {
  'toImageButtonOptions': {
    'format': 'png', # one of png, svg, jpeg, webp
    'height': 700,
    'width': 1900,
    'scale': 2 # Multiply title/legend/axis/canvas sizes by this factor
  }
}

try:
    import importlib.util
    if importlib.util.find_spec("ultranest") is not None:
        import ultranest
        import ultranest.stepsampler
        _ULTRANEST_AVAILABLE = True
    else:
        _ULTRANEST_AVAILABLE = False
except Exception:
    _ULTRANEST_AVAILABLE = False

# ---- UltraNest log buffer (in-memory, polled by Interval) ----
_ULTRANEST_LOG_BUFFER = deque(maxlen=200)
_ULTRANEST_LOG_LOCK = threading.Lock()
_ULTRANEST_LOG_RUNNING = False
_ULTRANEST_LOG_TOKEN = 0

def _ultra_log_reset(header):
    global _ULTRANEST_LOG_RUNNING, _ULTRANEST_LOG_TOKEN
    with _ULTRANEST_LOG_LOCK:
        _ULTRANEST_LOG_TOKEN += 1
        _ULTRANEST_LOG_BUFFER.clear()
        if header:
            _ULTRANEST_LOG_BUFFER.append(header)
        _ULTRANEST_LOG_RUNNING = True
    return _ULTRANEST_LOG_TOKEN

def _ultra_log_append(text):
    if text is None:
        return
    lines = str(text).splitlines()
    if not lines:
        return
    with _ULTRANEST_LOG_LOCK:
        for line in lines:
            if line is not None and str(line).strip() != "":
                _ULTRANEST_LOG_BUFFER.append(str(line))

def _ultra_log_finish():
    global _ULTRANEST_LOG_RUNNING
    with _ULTRANEST_LOG_LOCK:
        _ULTRANEST_LOG_RUNNING = False

def _ultra_log_snapshot():
    with _ULTRANEST_LOG_LOCK:
        return _ULTRANEST_LOG_TOKEN, _ULTRANEST_LOG_RUNNING, list(_ULTRANEST_LOG_BUFFER)

class _UltraStream:
    def __init__(self):
        self._buffer = ""
    def write(self, s):
        if s is None:
            return 0
        self._buffer += str(s)
        if "\n" in self._buffer:
            parts = self._buffer.split("\n")
            for line in parts[:-1]:
                _ultra_log_append(line)
            self._buffer = parts[-1]
        return len(s)
    def flush(self):
        if self._buffer:
            _ultra_log_append(self._buffer)
            self._buffer = ""
    def isatty(self):
        return False

class _UltraLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        _ultra_log_append(msg)

# ===== UltraNest refinement AFTER EM (keeps EM mixture/inlier logic) =====

def _ultranest_refine_pm_only(t, y_ra, y_dec, s_ra, s_dec, inlier_mask,
                              pmra_em, pmdec_em, pos_ra_em, pos_dec_em,
                              s_add_ra=0.0, s_add_dec=0.0,
                              mission_labels=None, s_add_ra_by_mission=None, s_add_dec_by_mission=None,
                              t0_ref=None):
    """Refine PM-only parameters with UltraNest using EM inliers and inflated sigmas.
    Returns: pmra, pmdec, e_pmra, e_pmdec, pos_ra_m, pos_dec_m
    """
    if not _ULTRANEST_AVAILABLE:
        raise RuntimeError("UltraNest is not available. Please install 'ultranest'.")

    t = np.asarray(t, float)
    y_ra = np.asarray(y_ra, float)
    y_dec = np.asarray(y_dec, float)
    s_ra = np.asarray(s_ra, float)
    s_dec = np.asarray(s_dec, float)
    mask = np.asarray(inlier_mask, bool)

    # Center time using EM's reference epoch if provided; otherwise use inlier median
    if t0_ref is None or not np.isfinite(t0_ref):
        t0 = float(np.nanmedian(t[mask]))
    else:
        t0 = float(t0_ref)
    tc = t - t0

    # Build per-point inflated sigmas using global + per-mission s_add if provided
    sig_ra = s_ra.copy()
    sig_dec = s_dec.copy()
    if mission_labels is not None and s_add_ra_by_mission and s_add_dec_by_mission:
        missions_arr = np.asarray(mission_labels)
        for m, s_add_m in s_add_ra_by_mission.items():
            sig_ra[missions_arr == m] = np.sqrt(sig_ra[missions_arr == m]**2 + float(s_add_m)**2)
        for m, s_add_m in s_add_dec_by_mission.items():
            sig_dec[missions_arr == m] = np.sqrt(sig_dec[missions_arr == m]**2 + float(s_add_m)**2)
    # Global additions
    sig_ra = np.sqrt(sig_ra**2 + float(s_add_ra)**2)
    sig_dec = np.sqrt(sig_dec**2 + float(s_add_dec)**2)

    # Use only inliers
    tc = tc[mask]
    y_ra = y_ra[mask]
    y_dec = y_dec[mask]
    sig_ra = sig_ra[mask]
    sig_dec = sig_dec[mask]

    # --- Robust scales to set sensible bounds (avoid extreme exploration) ---
    ra_res_em  = y_ra  - (pmra_em * tc + pos_ra_em)
    dec_res_em = y_dec - (pmdec_em * tc + pos_dec_em)
    mad_ra  = np.nanmedian(np.abs(ra_res_em - np.nanmedian(ra_res_em)))
    mad_dec = np.nanmedian(np.abs(dec_res_em - np.nanmedian(dec_res_em)))
    rob_pos = float(max(1.4826 * mad_ra, 1.4826 * mad_dec, 1.0))  # mas
    baseline = float(max(np.ptp(tc), 1e-3))  # years
    # rough slope scale from position scatter over baseline
    rob_pm = float(max(rob_pos / baseline, 0.05))  # mas/yr

    def model(theta):
        pmra, pmdec, pos_ra, pos_dec = theta
        return pmra * tc + pos_ra, pmdec * tc + pos_dec

    def loglike(theta):
        ra_m, dec_m = model(theta)
        chi2 = np.sum(((y_ra - ra_m)/sig_ra)**2) + np.sum(((y_dec - dec_m)/sig_dec)**2)
        return -0.5 * chi2

    # --- Data-driven bounds centered on EM using robust scales ---
    pmra_span   = (float(pmra_em) - 8*rob_pm,  float(pmra_em) + 8*rob_pm)
    pmdec_span  = (float(pmdec_em) - 8*rob_pm,  float(pmdec_em) + 8*rob_pm)
    # Ensure at least a modest span
    if pmra_span[1] - pmra_span[0] < 0.2: pmra_span = (pmra_span[0]-0.1, pmra_span[1]+0.1)
    if pmdec_span[1] - pmdec_span[0] < 0.2: pmdec_span = (pmdec_span[0]-0.1, pmdec_span[1]+0.1)
    pos_ra_span = (float(pos_ra_em) - 8*rob_pos, float(pos_ra_em) + 8*rob_pos)
    pos_dec_span= (float(pos_dec_em) - 8*rob_pos, float(pos_dec_em) + 8*rob_pos)
    if pos_ra_span[1] - pos_ra_span[0] < 2.0: pos_ra_span = (pos_ra_span[0]-1.0, pos_ra_span[1]+1.0)
    if pos_dec_span[1] - pos_dec_span[0] < 2.0: pos_dec_span = (pos_dec_span[0]-1.0, pos_dec_span[1]+1.0)

    # ---- DEBUG: print anchor epoch, scales, and bounds ----
    try:
        print("[UltraNest PM-only] Anchor t0 = %.6f yr, N_inliers = %d" % (t0, tc.size))
        print("[UltraNest PM-only] tc range: [%.3f, %.3f] yr" % (np.nanmin(tc), np.nanmax(tc)))
        print("[UltraNest PM-only] EM seeds: pmRA=%.3f, pmDEC=%.3f, posRA@t0=%.3f, posDEC@t0=%.3f" % (pmra_em, pmdec_em, pos_ra_em, pos_dec_em))
        print("[UltraNest PM-only] robust scales: rob_pos=%.3f mas, rob_pm=%.3f mas/yr" % (rob_pos, rob_pm))
        print("[UltraNest PM-only] bounds pmRA=[%.3f, %.3f], pmDEC=[%.3f, %.3f]" % (pmra_span[0], pmra_span[1], pmdec_span[0], pmdec_span[1]))
        print("[UltraNest PM-only] bounds posRA=[%.3f, %.3f], posDEC=[%.3f, %.3f]" % (pos_ra_span[0], pos_ra_span[1], pos_dec_span[0], pos_dec_span[1]))
    except Exception as _e_dbg:
        print("[UltraNest PM-only] DEBUG print failed:", _e_dbg)

    bounds = [pmra_span, pmdec_span, pos_ra_span, pos_dec_span]

    def transform(u):
        return [b[0] + u[i]*(b[1]-b[0]) for i, b in enumerate(bounds)]

    sampler = ultranest.ReactiveNestedSampler(
        param_names=["pmra", "pmdec", "pos_ra", "pos_dec"],
        loglike=loglike,
        transform=transform,
        resume="overwrite",
    )
    sampler.stepsampler = ultranest.stepsampler.RegionSliceSampler(nsteps=32)
    result = sampler.run(min_num_live_points=300, dlogz=0.5)
    stats = sampler.results
    mean = stats['posterior']['mean']
    stdev = stats['posterior']['stdev']

    pmra, pmdec, pos_ra, pos_dec = [float(x) for x in mean]
    e_pmra, e_pmdec = float(stdev[0]), float(stdev[1])
    return pmra, pmdec, e_pmra, e_pmdec, pos_ra, pos_dec


def _ultranest_refine_pm_plx(t, y_ra, y_dec, s_ra, s_dec, inlier_mask,
                             ra_ref_deg, dec_ref_deg,
                             pmra_em, pmdec_em, plx_em, pos_ra_em, pos_dec_em,
                             s_add_ra=0.0, s_add_dec=0.0,
                             mission_labels=None, s_add_ra_by_mission=None, s_add_dec_by_mission=None,
                             t0_ref=None):
    """Refine PM+PLX parameters with UltraNest using EM inliers and inflated sigmas.
    Returns: plx, pmra, pmdec, e_plx, e_pmra, e_pmdec, pos_ra, pos_dec
    """
    if not _ULTRANEST_AVAILABLE:
        raise RuntimeError("UltraNest is not available. Please install 'ultranest'.")

    t = np.asarray(t, float)
    y_ra = np.asarray(y_ra, float)
    y_dec = np.asarray(y_dec, float)
    s_ra = np.asarray(s_ra, float)
    s_dec = np.asarray(s_dec, float)
    mask = np.asarray(inlier_mask, bool)

    # Center time and parallax basis using EM's reference epoch if provided; else median of inliers
    if t0_ref is None or not np.isfinite(t0_ref):
        t0 = float(np.nanmedian(t[mask]))
    else:
        t0 = float(t0_ref)
    tc = t - t0
    plxm_all = parallax_motion(ra_ref_deg, dec_ref_deg, t)
    pra_all = np.asarray(plxm_all["plx_motion_racosdec"], float)
    pdec_all = np.asarray(plxm_all["plx_motion_dec"], float)
    # Parallax basis relative to t0
    plxm0 = parallax_motion(ra_ref_deg, dec_ref_deg, t0)
    pra0 = float(plxm0["plx_motion_racosdec"])
    pdec0 = float(plxm0["plx_motion_dec"])
    pra_rel_all = pra_all - pra0
    pdec_rel_all = pdec_all - pdec0

    # --- Transform EM intercepts (defined at EM's reference epoch t0_em) to UltraNest epoch t0 ---
    # After recent changes, EM PLX+PM uses centered time around t0_em (= t0_ref passed in),
    # so pos_ra_em/pos_dec_em are intercepts at t0_em. Map them to t0 via linear + parallax shift:
    t0_em = float(t0_ref) if (t0_ref is not None and np.isfinite(t0_ref)) else float(t0)
    plxm_em0 = parallax_motion(ra_ref_deg, dec_ref_deg, t0_em)
    pra_em0 = float(plxm_em0["plx_motion_racosdec"])  # parallax factor at EM's epoch
    pdec_em0 = float(plxm_em0["plx_motion_dec"])      # parallax factor at EM's epoch
    pos_ra_em_t0  = float(pos_ra_em  + pmra_em * (t0 - t0_em) + plx_em * (pra0 - pra_em0))
    pos_dec_em_t0 = float(pos_dec_em + pmdec_em * (t0 - t0_em) + plx_em * (pdec0 - pdec_em0))

    # Build inflated sigmas (per-mission + global) then mask to inliers
    sig_ra = s_ra.copy()
    sig_dec = s_dec.copy()
    if mission_labels is not None and s_add_ra_by_mission and s_add_dec_by_mission:
        missions_arr = np.asarray(mission_labels)
        for m, s_add_m in s_add_ra_by_mission.items():
            sig_ra[missions_arr == m] = np.sqrt(sig_ra[missions_arr == m]**2 + float(s_add_m)**2)
        for m, s_add_m in s_add_dec_by_mission.items():
            sig_dec[missions_arr == m] = np.sqrt(sig_dec[missions_arr == m]**2 + float(s_add_m)**2)
    sig_ra = np.sqrt(sig_ra**2 + float(s_add_ra)**2)
    sig_dec = np.sqrt(sig_dec**2 + float(s_add_dec)**2)

    tc = tc[mask]
    y_ra = y_ra[mask]
    y_dec = y_dec[mask]
    pra = pra_rel_all[mask]
    pdec = pdec_rel_all[mask]
    sig_ra = sig_ra[mask]
    sig_dec = sig_dec[mask]

    # --- Robust scales for bounds (centered model at t0, parallax relative to t0) ---
    ra_res_em  = y_ra  - (pmra_em * tc + plx_em * pra + pos_ra_em_t0)
    dec_res_em = y_dec - (pmdec_em * tc + plx_em * pdec + pos_dec_em_t0)
    mad_ra  = np.nanmedian(np.abs(ra_res_em - np.nanmedian(ra_res_em)))
    mad_dec = np.nanmedian(np.abs(dec_res_em - np.nanmedian(dec_res_em)))
    rob_pos = float(max(1.4826 * mad_ra, 1.4826 * mad_dec, 1.0))  # mas
    baseline = float(max(np.ptp(tc), 1e-3))  # years
    rob_pm = float(max(rob_pos / baseline, 0.05))  # mas/yr
    # Parallax scale from projection amplitudes
    proj_amp = float(max(np.nanmax(np.abs(pra)), np.nanmax(np.abs(pdec)), 1e-2))
    rob_plx = float(max(rob_pos / proj_amp, 0.02))  # mas

    def model(theta):
        pmra, pmdec, plx, pos_ra, pos_dec = theta
        # Intercepts are defined at t0
        return pmra * tc + plx * pra + pos_ra, pmdec * tc + plx * pdec + pos_dec

    def loglike(theta):
        ra_m, dec_m = model(theta)
        chi2 = np.sum(((y_ra - ra_m)/sig_ra)**2) + np.sum(((y_dec - dec_m)/sig_dec)**2)
        return -0.5 * chi2

    # --- Data-driven bounds centered on EM using robust scales ---
    pmra_span   = (float(pmra_em) - 8*rob_pm,  float(pmra_em) + 8*rob_pm)
    pmdec_span  = (float(pmdec_em) - 8*rob_pm,  float(pmdec_em) + 8*rob_pm)
    plx_span    = (float(plx_em)  - 8*rob_plx, float(plx_em)  + 8*rob_plx)
    if pmra_span[1] - pmra_span[0] < 0.2: pmra_span = (pmra_span[0]-0.1, pmra_span[1]+0.1)
    if pmdec_span[1] - pmdec_span[0] < 0.2: pmdec_span = (pmdec_span[0]-0.1, pmdec_span[1]+0.1)
    if plx_span[1] - plx_span[0]   < 0.1: plx_span   = (plx_span[0]-0.05, plx_span[1]+0.05)
    pos_ra_span = (pos_ra_em_t0 - 8*rob_pos, pos_ra_em_t0 + 8*rob_pos)
    pos_dec_span= (pos_dec_em_t0 - 8*rob_pos, pos_dec_em_t0 + 8*rob_pos)
    if pos_ra_span[1] - pos_ra_span[0] < 2.0: pos_ra_span = (pos_ra_span[0]-1.0, pos_ra_span[1]+1.0)
    if pos_dec_span[1] - pos_dec_span[0] < 2.0: pos_dec_span = (pos_dec_span[0]-1.0, pos_dec_span[1]+1.0)

    # ---- DEBUG: print anchor epoch, scales, and bounds ----
    try:
        print("[UltraNest PM+PLX] Anchor t0 = %.6f yr, N_inliers = %d" % (t0, tc.size))
        print("[UltraNest PM+PLX] tc range: [%.3f, %.3f] yr" % (np.nanmin(tc), np.nanmax(tc)))
        print("[UltraNest PM+PLX] EM seeds: pmRA=%.3f, pmDEC=%.3f, plx=%.3f, posRA@t0_em=%.3f, posDEC@t0_em=%.3f" % (pmra_em, pmdec_em, plx_em, pos_ra_em, pos_dec_em))
        print("[UltraNest PM+PLX] transformed EM intercepts: posRA@t0=%.3f, posDEC@t0=%.3f" % (pos_ra_em_t0, pos_dec_em_t0))
        print("[UltraNest PM+PLX] robust scales: rob_pos=%.3f mas, rob_pm=%.3f mas/yr, rob_plx=%.3f mas" % (rob_pos, rob_pm, rob_plx))
        print("[UltraNest PM+PLX] bounds pmRA=[%.3f, %.3f], pmDEC=[%.3f, %.3f], plx=[%.3f, %.3f]" % (pmra_span[0], pmra_span[1], pmdec_span[0], pmdec_span[1], plx_span[0], plx_span[1]))
        print("[UltraNest PM+PLX] bounds posRA=[%.3f, %.3f], posDEC=[%.3f, %.3f]" % (pos_ra_span[0], pos_ra_span[1], pos_dec_span[0], pos_dec_span[1]))
    except Exception as _e_dbg:
        print("[UltraNest PM+PLX] DEBUG print failed:", _e_dbg)

    bounds = [pmra_span, pmdec_span, plx_span, pos_ra_span, pos_dec_span]

    def transform(u):
        return [b[0] + u[i]*(b[1]-b[0]) for i, b in enumerate(bounds)]

    sampler = ultranest.ReactiveNestedSampler(
        param_names=["pmra", "pmdec", "plx", "pos_ra", "pos_dec"],
        loglike=loglike,
        transform=transform,
        resume="overwrite",
    )
    sampler.stepsampler = ultranest.stepsampler.RegionSliceSampler(nsteps=32)
    result = sampler.run(min_num_live_points=400, dlogz=0.5)
    stats = sampler.results
    mean = stats['posterior']['mean']
    stdev = stats['posterior']['stdev']

    pmra, pmdec, plx, pos_ra, pos_dec = [float(x) for x in mean]
    e_pmra, e_pmdec, e_plx = float(stdev[0]), float(stdev[1]), float(stdev[2])
    return plx, pmra, pmdec, e_plx, e_pmra, e_pmdec, pos_ra, pos_dec, t0

def robust_error_weighted_plxfit_with_rejection(
    measurement_epoch_yr, rel_ra, rel_dec, ra_unc_mas, dec_unc_mas, ref_ra, ref_dec,
    sigma_threshold=10, max_iterations=5, inflate_errors=False, mission_labels=None, per_mission_inflate=False,
    seed_pmra=None, seed_pmdec=None, seed_plx=None, seed_pos_ra=None, seed_pos_dec=None
):
    """
    Perform a robust error-weighted fit for parallax, proper motion, and positions with iterative outlier rejection.

    Parameters:
    - measurement_epoch_yr (array-like): The time values (years).
    - rel_ra (array-like): The relative RA offsets (mas).
    - rel_dec (array-like): The relative Dec offsets (mas).
    - ra_unc_mas (array-like): The uncertainties in relative RA (mas).
    - dec_unc_mas (array-like): The uncertainties in relative Dec (mas).
    - ref_ra (float): Reference RA in degrees.
    - ref_dec (float): Reference Dec in degrees.
    - sigma_threshold (float): Number of standard deviations for outlier rejection.
    - max_iterations (int): Maximum number of iterations for outlier rejection.

    Returns:
    - plx (float): Best-fit parallax (mas).
    - pmra (float): Best-fit proper motion in RA (mas/yr).
    - pmdec (float): Best-fit proper motion in Dec (mas/yr).
    - eplx (float): Uncertainty in the parallax.
    - epmra (float): Uncertainty in the proper motion in RA.
    - epmdec (float): Uncertainty in the proper motion in Dec.
    - inlier_mask (array): Boolean mask indicating inliers used in the final fit.
    """
    # Convert inputs to numpy arrays and ensure consistent dimensions
    epoch_yr = np.array(measurement_epoch_yr)
    rel_ra = np.array(rel_ra)
    rel_dec = np.array(rel_dec)
    ra_unc = np.array(ra_unc_mas)
    dec_unc = np.array(dec_unc_mas)
    # Track per-axis additive error inflation (mas)
    s_ra = 0.0
    s_dec = 0.0

    if not (len(epoch_yr) == len(rel_ra) == len(rel_dec) == len(ra_unc) == len(dec_unc)):
        raise ValueError(
            "All input arrays must have the same length. "
            f"Lengths: measurement_epoch_yr={len(epoch_yr)}, rel_ra={len(rel_ra)}, "
            f"rel_dec={len(rel_dec)}, ra_unc_mas={len(ra_unc)}, dec_unc_mas={len(dec_unc)}"
        )

    # Convert year epochs to MJD using Astropy
    time_obj = Time(epoch_yr, format='jyear', scale='utc')
    mjd_vec = time_obj.mjd

    # Convert reference RA/Dec to radians
    ref_ra_rad = np.radians(ref_ra)
    ref_dec_rad = np.radians(ref_dec)

    # Compute parallax motion terms using reference RA/Dec
    (void1, void2, void3, sun_elong, sun_obl) = sunpos(mjd_vec + 2400000.5, full_output=True)
    sun_elong = sun_elong[0]
    sun_obl = sun_obl[0]

    sin_sun_elong = np.sin(np.radians(sun_elong))
    cos_sun_elong = np.cos(np.radians(sun_elong))
    sin_sun_obl = np.sin(np.radians(sun_obl))
    cos_sun_obl = np.cos(np.radians(sun_obl))

    cos_ref_ra = np.cos(ref_ra_rad)
    sin_ref_ra = np.sin(ref_ra_rad)
    cos_ref_dec = np.cos(ref_dec_rad)
    sin_ref_dec = np.sin(ref_dec_rad)

    plx_motion_ra = cos_ref_ra * cos_sun_obl * sin_sun_elong - sin_ref_ra * cos_sun_elong
    plx_motion_dec = (
        cos_ref_dec * sin_sun_obl * sin_sun_elong
        - cos_ref_ra * sin_ref_dec * cos_sun_elong
        - sin_ref_ra * sin_ref_dec * cos_sun_obl * sin_sun_elong
    )

    # ---- Center time and parallax basis at a reference epoch for numerical stability ----
    # Use median epoch across all rows as EM reference (kept fixed through the EM loop)
    t0_ref_plx = float(np.nanmedian(epoch_yr))
    # Parallax basis relative to t0_ref_plx
    mjd0 = float(Time(t0_ref_plx, format='jyear', scale='utc').mjd)
    (void1_0, void2_0, void3_0, sun_elong0, sun_obl0) = sunpos(mjd0 + 2400000.5, full_output=True)
    sun_elong0 = sun_elong0[0]
    sun_obl0 = sun_obl0[0]
    sin_sun_elong0 = np.sin(np.radians(sun_elong0))
    cos_sun_elong0 = np.cos(np.radians(sun_elong0))
    sin_sun_obl0 = np.sin(np.radians(sun_obl0))
    cos_sun_obl0 = np.cos(np.radians(sun_obl0))

    pra0 = cos_ref_ra * cos_sun_obl0 * sin_sun_elong0 - sin_ref_ra * cos_sun_elong0
    pdec0 = (
        cos_ref_dec * sin_sun_obl0 * sin_sun_elong0
        - cos_ref_ra * sin_ref_dec * cos_sun_elong0
        - sin_ref_ra * sin_ref_dec * cos_sun_obl0 * sin_sun_elong0
    )

    # Relative parallax factors
    pra_rel = plx_motion_ra - pra0
    pdec_rel = plx_motion_dec - pdec0

    # Initial mask (all points are considered inliers)
    inlier_mask = ~np.isnan(epoch_yr) & ~np.isnan(rel_ra) & ~np.isnan(rel_dec) & \
                  ~np.isnan(ra_unc) & ~np.isnan(dec_unc)

    if len(inlier_mask) != len(epoch_yr):
        raise ValueError(
            f"Inlier mask dimension mismatch: inlier_mask={len(inlier_mask)}, epoch_yr={len(epoch_yr)}"
        )

    # Define the model for fitting: y = pm * t_centered + plx * relative_parallax + pos
    def plx_pm_model(xdata, pmra, pmdec, plx, pos_ra, pos_dec):
        # xdata = [t_centered, pra_rel, pdec_rel]
        ra_model = pmra * xdata[0] + plx * xdata[1] + pos_ra
        dec_model = pmdec * xdata[0] + plx * xdata[2] + pos_dec
        return np.concatenate([ra_model, dec_model])  # Combine RA and Dec models into a single 1D array

    for iteration in range(max_iterations):
        # --- Build inlier subset arrays ---
        e = epoch_yr[inlier_mask]
        pra = pra_rel[inlier_mask]
        pdec = pdec_rel[inlier_mask]
        y_ra = rel_ra[inlier_mask]
        y_dec = rel_dec[inlier_mask]
        sig_ra = ra_unc[inlier_mask]
        sig_dec = dec_unc[inlier_mask]
        n = e.size

        # Prepare x/y for curve_fit (centered time, relative parallax factors)
        tc = e - t0_ref_plx
        xdata_in = np.vstack([tc, pra, pdec])
        ydata_in = np.concatenate([y_ra, y_dec])

        # ---- Initialize moving and stationary components ----
        # ---- Optional seeding from literature PM/PLX ----
        p0_seed = None
        if (seed_pmra is not None) or (seed_pmdec is not None) or (seed_plx is not None) or (seed_pos_ra is not None) or (seed_pos_dec is not None):
            # Fill missing seeds with zeros temporarily
            spmra = float(seed_pmra) if seed_pmra is not None and np.isfinite(seed_pmra) else 0.0
            spmdec = float(seed_pmdec) if seed_pmdec is not None and np.isfinite(seed_pmdec) else 0.0
            splx  = float(seed_plx)  if seed_plx  is not None and np.isfinite(seed_plx)  else 0.0
            # If intercepts are not given, estimate them as precision-weighted means of residuals
            if seed_pos_ra is None or not np.isfinite(seed_pos_ra):
                w_ra = 1.0 / np.maximum(sig_ra, 1e-6)**2
                seed_pos_ra = float(np.sum(w_ra * (y_ra - spmra * e - splx * pra)) / np.sum(w_ra)) if np.sum(w_ra) > 0 else float(np.nanmedian(y_ra - spmra * e - splx * pra))
            if seed_pos_dec is None or not np.isfinite(seed_pos_dec):
                w_dec = 1.0 / np.maximum(sig_dec, 1e-6)**2
                seed_pos_dec = float(np.sum(w_dec * (y_dec - spmdec * e - splx * pdec)) / np.sum(w_dec)) if np.sum(w_dec) > 0 else float(np.nanmedian(y_dec - spmdec * e - splx * pdec))
            p0_seed = np.array([spmra, spmdec, splx, float(seed_pos_ra), float(seed_pos_dec)], dtype=float)

        popt, pcov = curve_fit(
            plx_pm_model,
            xdata_in,
            ydata_in,
            sigma=np.concatenate([sig_ra, sig_dec]),
            absolute_sigma=True,
            p0=p0_seed
        )

        # Initial stationary (constant offsets) estimates
        w_ra0 = 1.0 / np.maximum(sig_ra, 1e-6) ** 2
        w_dec0 = 1.0 / np.maximum(sig_dec, 1e-6) ** 2
        s_ra_stat = float(np.sum(w_ra0 * y_ra) / np.sum(w_ra0)) if np.isfinite(np.sum(w_ra0)) and np.sum(w_ra0) > 0 else float(np.nanmean(y_ra))
        s_dec_stat = float(np.sum(w_dec0 * y_dec) / np.sum(w_dec0)) if np.isfinite(np.sum(w_dec0)) and np.sum(w_dec0) > 0 else float(np.nanmean(y_dec))

        # Mixture weight and responsibilities (for moving component)
        w_mix = 0.7
        r = np.full(n, 0.8, dtype=float)

        # ---- EM loops (moving + stationary) ----
        for _ in range(10):
            # E-step: responsibilities for the moving component
            model_concat = plx_pm_model(xdata_in, *popt)
            ra_m = model_concat[:n]
            dec_m = model_concat[n:]

            m2_mov = ((y_ra - ra_m) ** 2) / (sig_ra ** 2) + ((y_dec - dec_m) ** 2) / (sig_dec ** 2)
            m2_sta = ((y_ra - s_ra_stat) ** 2) / (sig_ra ** 2) + ((y_dec - s_dec_stat) ** 2) / (sig_dec ** 2)

            ratio = ((1.0 - w_mix) / max(w_mix, 1e-6)) * np.exp(0.5 * (m2_mov - m2_sta))
            r = 1.0 / (1.0 + ratio)

            # M-step: update moving params with responsibilities as weights
            scale = np.sqrt(np.clip(r, 1e-6, None))
            sigma_eff = np.concatenate([sig_ra / scale, sig_dec / scale])

            popt, pcov = curve_fit(
                plx_pm_model,
                xdata_in,
                ydata_in,
                sigma=sigma_eff,
                absolute_sigma=True
            )

            # Update stationary offsets (constant model)
            w_s_ra = (1.0 - r) / (sig_ra ** 2)
            w_s_dec = (1.0 - r) / (sig_dec ** 2)
            denom_ra = float(np.sum(w_s_ra))
            denom_dec = float(np.sum(w_s_dec))
            if denom_ra > 0:
                s_ra_stat = float(np.sum(w_s_ra * y_ra) / denom_ra)
            if denom_dec > 0:
                s_dec_stat = float(np.sum(w_s_dec * y_dec) / denom_dec)

            # Update mixture weight
            w_mix = float(np.clip(np.mean(r), 0.05, 0.95))

        # ---- After EM: compute residuals to MOVING component on ALL rows for rejection ----
        xdata_all = np.vstack([epoch_yr - t0_ref_plx, pra_rel, pdec_rel])
        model_output = plx_pm_model(xdata_all, *popt)
        ra_model = model_output[:len(rel_ra)]
        dec_model = model_output[len(rel_ra):]

        ra_residuals = rel_ra - ra_model
        dec_residuals = rel_dec - dec_model

        ra_standardized_residuals = np.abs(ra_residuals / ra_unc)
        dec_standardized_residuals = np.abs(dec_residuals / dec_unc)

        # Outlier rejection based ONLY on the moving component residuals
        new_inlier_mask = (ra_standardized_residuals < sigma_threshold) & (dec_standardized_residuals < sigma_threshold)

        # Stop if no changes in the mask
        if np.array_equal(inlier_mask, new_inlier_mask):
            break

        inlier_mask = new_inlier_mask
    # ========== Optional two-pass inflation of uncertainties ==========
    if inflate_errors:
        # Model for all rows
        xdata_all = np.vstack([epoch_yr - t0_ref_plx, pra_rel, pdec_rel])
        model_all = plx_pm_model(xdata_all, *popt)
        ra_model_all = model_all[:len(rel_ra)]
        dec_model_all = model_all[len(rel_ra):]

        # Residuals for inliers
        ra_resid_in = (rel_ra - ra_model_all)[inlier_mask]
        dec_resid_in = (rel_dec - dec_model_all)[inlier_mask]
        ra_sig_in = ra_unc[inlier_mask]
        dec_sig_in = dec_unc[inlier_mask]

        # DOF per coordinate equation (pm + plx + intercept)
        dof_ra = max(1, ra_resid_in.size - 3)
        dof_dec = max(1, dec_resid_in.size - 3)

        s_ra = _solve_sigma_add(ra_resid_in, ra_sig_in, dof_ra)
        s_dec = _solve_sigma_add(dec_resid_in, dec_sig_in, dof_dec)

        # Refit with inflated uncertainties on inliers
        popt, pcov = curve_fit(
            plx_pm_model,
            np.vstack([epoch_yr[inlier_mask] - t0_ref_plx, pra_rel[inlier_mask], pdec_rel[inlier_mask]]),
            np.concatenate([rel_ra[inlier_mask], rel_dec[inlier_mask]]),
            sigma=np.sqrt(np.concatenate([ra_unc[inlier_mask]**2 + s_ra**2, dec_unc[inlier_mask]**2 + s_dec**2])),
            absolute_sigma=True
        )

        # Per-mission inflation (optional): compute s_add per mission and refit with per-point sigmas
        s_ra_by_mission = {}
        s_dec_by_mission = {}
        if inflate_errors and per_mission_inflate and mission_labels is not None:
            missions_arr = np.asarray(mission_labels)
            # Build model over ALL rows
            xdata_all = np.vstack([epoch_yr - t0_ref_plx, pra_rel, pdec_rel])
            model_all = plx_pm_model(xdata_all, *popt)
            ra_model_all = model_all[:len(rel_ra)]
            dec_model_all = model_all[len(rel_ra):]
            # Initialize inflated sigma arrays with base
            ra_sig2 = ra_unc**2
            dec_sig2 = dec_unc**2
            # Compute per-mission s_add on inliers only
            for m in np.unique(missions_arr[inlier_mask]):
                mask_m = (missions_arr == m) & inlier_mask
                if mask_m.sum() >= 3:  # need DOF
                    ra_resid_m = (rel_ra - ra_model_all)[mask_m]
                    dec_resid_m = (rel_dec - dec_model_all)[mask_m]
                    ra_sig_m = ra_unc[mask_m]
                    dec_sig_m = dec_unc[mask_m]
                    dof_ra_m = max(1, mask_m.sum() - 3)
                    dof_dec_m = max(1, mask_m.sum() - 3)
                    s_ra_m = _solve_sigma_add(ra_resid_m, ra_sig_m, dof_ra_m)
                    s_dec_m = _solve_sigma_add(dec_resid_m, dec_sig_m, dof_dec_m)
                    s_ra_by_mission[m] = float(s_ra_m)
                    s_dec_by_mission[m] = float(s_dec_m)
                    # Apply to ALL points of this mission (including outliers) during refit
                    ra_sig2[missions_arr == m] = ra_unc[missions_arr == m]**2 + s_ra_m**2
                    dec_sig2[missions_arr == m] = dec_unc[missions_arr == m]**2 + s_dec_m**2
                else:
                    s_ra_by_mission[m] = 0.0
                    s_dec_by_mission[m] = 0.0
            # Refit using per-point inflated sigmas on inliers
            sigma_vec = np.sqrt(np.concatenate([ra_sig2[inlier_mask], dec_sig2[inlier_mask]]))
            
            popt, pcov = curve_fit(
                plx_pm_model,
                np.vstack([epoch_yr[inlier_mask] - t0_ref_plx, pra_rel[inlier_mask], pdec_rel[inlier_mask]]),
                np.concatenate([rel_ra[inlier_mask], rel_dec[inlier_mask]]),
                sigma=sigma_vec,
                absolute_sigma=True
            )
    
    # Extract results
    pmra, pmdec, plx, pos_ra, pos_dec = popt
    e_pmra, e_pmdec, e_plx, e_pos_ra, e_pos_dec = np.sqrt(np.diag(pcov))

    return (plx, pmra, pmdec, e_plx, e_pmra, e_pmdec,
        inlier_mask,
        s_ra, s_dec,
        s_ra_by_mission if ('s_ra_by_mission' in locals()) else {},
        s_dec_by_mission if ('s_dec_by_mission' in locals()) else {},
        pos_ra, pos_dec, t0_ref_plx)

def _solve_sigma_add(residuals, sigma, dof):
    """
    Find non-negative s such that sum(resid^2/(sigma^2 + s^2)) == dof.
    Monotonic bisection. Returns 0 if already not under-dispersed.
    """
    resid2 = np.asarray(residuals, float)**2
    sig2 = np.asarray(sigma, float)**2
    # Guard against zeros and NaNs
    if not np.any(sig2 > 0):
        sig2 = np.ones_like(resid2)
    else:
        safe = np.nanmedian(sig2[sig2 > 0])
        sig2 = np.where(sig2 <= 0, safe if np.isfinite(safe) and safe > 0 else 1.0, sig2)

    def f(s):
        return np.nansum(resid2 / (sig2 + s*s)) - dof

    if f(0.0) <= 0:
        return 0.0

    # Find upper bound
    s_lo, s_hi = 0.0, np.sqrt(np.nanmedian(resid2)) if np.isfinite(np.nanmedian(resid2)) else 1.0
    for _ in range(60):
        if f(s_hi) < 0:
            break
        s_hi *= 2.0

    # Bisection
    for _ in range(60):
        s_mid = 0.5*(s_lo + s_hi)
        if f(s_mid) > 0:
            s_lo = s_mid
        else:
            s_hi = s_mid
    return s_hi

#Robust error-weighted fit
def _fit_pm2d_from_two_points(t1, ra1, dec1, t2, ra2, dec2):
    """Minimal model from two epochs for PM-only in RA+DEC."""
    dt = float(t2 - t1)
    if not np.isfinite(dt) or abs(dt) < 1e-6:
        return None
    pmra = (ra2 - ra1) / dt
    pmdec = (dec2 - dec1) / dt
    pos_ra_m = ra1 - pmra * t1
    pos_dec_m = dec1 - pmdec * t1
    return np.array([pmra, pmdec, pos_ra_m, pos_dec_m], dtype=float)

def _theil_sen_pm2d_seed(t, y_ra, y_dec):
    """Robust slope (Theil–Sen) for RA and DEC separately; returns params."""
    t = np.asarray(t, float)
    y_ra = np.asarray(y_ra, float)
    y_dec = np.asarray(y_dec, float)
    n = t.size
    if n < 2:
        return None

    # Build pairwise slopes with a modest baseline guard
    slopes_ra = []
    slopes_dec = []
    for i in range(n - 1):
        dt = t[i+1:] - t[i]
        good = np.isfinite(dt) & (np.abs(dt) > 0.25)  # >= 3 months baseline
        if not np.any(good):
            continue
        slopes_ra.append((y_ra[i+1:][good] - y_ra[i]) / dt[good])
        slopes_dec.append((y_dec[i+1:][good] - y_dec[i]) / dt[good])
    if not slopes_ra:
        return None
    pmra = float(np.median(np.concatenate(slopes_ra)))
    pmdec = float(np.median(np.concatenate(slopes_dec)))

    # Intercepts via median at reference epoch (reduce correlation)
    t0 = float(np.nanmedian(t))
    pos_ra_m = float(np.nanmedian(y_ra - pmra * (t - t0))) + pmra * t0
    pos_dec_m = float(np.nanmedian(y_dec - pmdec * (t - t0))) + pmdec * t0
    return np.array([pmra, pmdec, pos_ra_m, pos_dec_m], dtype=float)

def _ransac_pm2d_seed(t, y_ra, y_dec, sra, sde, n_trials=400, z_thresh=3.5, min_inliers=4):
    """
    RANSAC seed for the moving track. Chooses two-epoch fits and keeps the model
    with the most 2D inliers (Mahalanobis threshold).
    """
    rng = np.random.default_rng(12345)
    t = np.asarray(t, float)
    y_ra = np.asarray(y_ra, float)
    y_dec = np.asarray(y_dec, float)
    sra = np.asarray(sra, float)
    sde = np.asarray(sde, float)
    n = t.size
    if n < 2:
        return None

    best_params = None
    best_count = 0

    for _ in range(n_trials):
        i, j = rng.integers(0, n, size=2)
        if i == j:
            continue
        if abs(t[j] - t[i]) < 0.5:  # ensure >= 6 months baseline
            continue
        params = _fit_pm2d_from_two_points(t[i], y_ra[i], y_dec[i], t[j], y_ra[j], y_dec[j])
        if params is None:
            continue

        pmra, pmdec, pos_ra_m, pos_dec_m = params
        ra_m = pmra * t + pos_ra_m
        dec_m = pmdec * t + pos_dec_m
        z2 = ((y_ra - ra_m) / np.maximum(sra, 1e-3))**2 + ((y_dec - dec_m) / np.maximum(sde, 1e-3))**2
        inliers = z2 < (z_thresh**2)
        count = int(np.sum(inliers))
        if count > best_count and count >= min_inliers:
            best_count = count
            best_params = params

    return best_params

def robust_error_weighted_pmfit_with_rejection(
    measurement_epoch_yr,
    rel_ra,
    rel_dec,
    ra_unc_mas,
    dec_unc_mas,
    sigma_threshold=10,
    max_iterations=5,
    inflate_errors=False,
    mission_labels=None,
    per_mission_inflate=False,
    seed_pmra=None,
    seed_pmdec=None
):
    """
    Joint RA+DEC robust PM-only fit with a moving+stationary mixture.
    Moving component: RA = pmra * t + pos_ra_m ; DEC = pmdec * t + pos_dec_m
    Stationary component: RA = s_ra_stat ; DEC = s_dec_stat
    Outlier rejection is based ONLY on residuals to the moving component.
    Returns:
        pmra, pmdec, e_pmra, e_pmdec,
        inlier_mask,
        s_add_ra, s_add_dec,
        s_add_ra_by_mission, s_add_dec_by_mission,
        pos_ra_m, pos_dec_m, s_ra_stat, s_dec_stat
    """
    # Model: use centered time for numerical stability
    def pm2d_model(xdata, pmra, pmdec, pos_ra_m, pos_dec_m):
        tcent = xdata[0]  # already centered before passing in
        ra_model = pmra * tcent + pos_ra_m
        dec_model = pmdec * tcent + pos_dec_m
        return np.concatenate([ra_model, dec_model])

    # Convert inputs to numpy arrays
    t_all = np.asarray(measurement_epoch_yr, float)
    y_ra_all = np.asarray(rel_ra, float)
    y_dec_all = np.asarray(rel_dec, float)
    sig_ra_all = np.asarray(ra_unc_mas, float)
    sig_dec_all = np.asarray(dec_unc_mas, float)

    # Center time to reduce intercept/pm correlation
    t0_ref = float(np.nanmedian(t_all))

    debug_pm_init = {"seeds": [], "chosen": None}

    # Track additive error inflations
    s_add_ra = 0.0
    s_add_dec = 0.0

    # Start: all valid points are inliers
    inlier_mask = (~np.isnan(t_all) & ~np.isnan(y_ra_all) & ~np.isnan(y_dec_all)
                   & ~np.isnan(sig_ra_all) & ~np.isnan(sig_dec_all))

    # EM + rejection loop
    for _ in range(max_iterations):
        # Inlier subset
        t = t_all[inlier_mask]
        y_ra = y_ra_all[inlier_mask]
        y_dec = y_dec_all[inlier_mask]
        sra = sig_ra_all[inlier_mask]
        sde = sig_dec_all[inlier_mask]
        n = t.size

        # Centered time
        tc = t - t0_ref

        # ----- Detect a stationary core near the median and avoid it for seeding -----
        mra0 = float(np.nanmedian(y_ra))
        mdec0 = float(np.nanmedian(y_dec))
        dr = np.sqrt((y_ra - mra0)**2 + (y_dec - mdec0)**2)
        sig_med = float(np.sqrt(np.nanmedian(sra**2) + np.nanmedian(sde**2)))
        # Core radius: max of 5σ or 30th percentile of radial distances
        r_core = max(5.0 * (sig_med if np.isfinite(sig_med) and sig_med > 0 else 20.0),
                     float(np.nanpercentile(dr, 30)) if np.isfinite(np.nanpercentile(dr, 30)) else 0.0)
        core_mask = dr < r_core
        # Use non-core (outer) points for robust seeding when available
        use_outer = np.sum(~core_mask) >= 4
        t_seed = tc[~core_mask] if use_outer else tc
        ra_seed = y_ra[~core_mask] if use_outer else y_ra
        dec_seed = y_dec[~core_mask] if use_outer else y_dec
        sra_seed = sra[~core_mask] if use_outer else sra
        sde_seed = sde[~core_mask] if use_outer else sde

        # Prepare x/y for curve_fit
        xdata_in = np.vstack([tc])
        ydata_in = np.concatenate([y_ra, y_dec])

        # ===== Multi-start initialisation for the moving model =====
        # Optional seed from literature PM
        seed_candidate = None
        if (seed_pmra is not None and np.isfinite(seed_pmra)) or (seed_pmdec is not None and np.isfinite(seed_pmdec)):
            spmra = float(seed_pmra) if seed_pmra is not None and np.isfinite(seed_pmra) else 0.0
            spmdec = float(seed_pmdec) if seed_pmdec is not None and np.isfinite(seed_pmdec) else 0.0
            # Intercepts consistent with centered time tc: pos = mean(y - pm*tcent)
            w_ra0 = 1.0 / np.maximum(sra, 1e-6) ** 2
            w_dec0 = 1.0 / np.maximum(sde, 1e-6) ** 2
            pos_ra_seed = float(np.sum(w_ra0 * (y_ra - spmra * tc)) / np.sum(w_ra0)) if np.sum(w_ra0) > 0 else float(np.nanmedian(y_ra - spmra * tc))
            pos_dec_seed = float(np.sum(w_dec0 * (y_dec - spmdec * tc)) / np.sum(w_dec0)) if np.sum(w_dec0) > 0 else float(np.nanmedian(y_dec - spmdec * tc))
            seed_candidate = np.array([spmra, spmdec, pos_ra_seed, pos_dec_seed], dtype=float)

        if '_debug_collected' not in locals():
            # Candidate A: plain WLS seed (use outer points if available)
            try:
                popt_a, _ = curve_fit(
                    pm2d_model,
                    np.vstack([t_seed]),
                    np.concatenate([ra_seed, dec_seed]),
                    sigma=np.concatenate([sra_seed, sde_seed]),
                    absolute_sigma=True,
                )
            except Exception:
                popt_a = None
            if popt_a is not None and np.all(np.isfinite(popt_a)):
                debug_pm_init["seeds"].append(
                    {"method": "WLS", "pmra": float(popt_a[0]), "pmdec": float(popt_a[1]),
                    "pos_ra": float(popt_a[2]), "pos_dec": float(popt_a[3])}
                )
            else:
                debug_pm_init["seeds"].append({"method": "WLS", "pmra": None, "pmdec": None, "pos_ra": None, "pos_dec": None})
            # Candidate B: RANSAC seed (tends to lock onto the moving track)
            popt_b = _ransac_pm2d_seed(t_seed, ra_seed, dec_seed, sra_seed, sde_seed, n_trials=2000, z_thresh=2.75, min_inliers=6)
            if popt_b is not None and np.all(np.isfinite(popt_b)):
                debug_pm_init["seeds"].append(
                    {"method": "RANSAC", "pmra": float(popt_b[0]), "pmdec": float(popt_b[1]),
                    "pos_ra": float(popt_b[2]), "pos_dec": float(popt_b[3])}
                )
            else:
                debug_pm_init["seeds"].append({"method": "RANSAC", "pmra": None, "pmdec": None, "pos_ra": None, "pos_dec": None})
            # Candidate C: Theil–Sen robust slope seed
            popt_c = _theil_sen_pm2d_seed(t_seed, ra_seed, dec_seed)
            if popt_c is not None and np.all(np.isfinite(popt_c)):
                debug_pm_init["seeds"].append(
                    {"method": "Theil-Sen", "pmra": float(popt_c[0]), "pmdec": float(popt_c[1]),
                    "pos_ra": float(popt_c[2]), "pos_dec": float(popt_c[3])}
                )
            else:
                debug_pm_init["seeds"].append({"method": "Theil-Sen", "pmra": None, "pmdec": None, "pos_ra": None, "pos_dec": None})
            _debug_collected = True
        else:
            try:
                popt_a, _ = curve_fit(
                    pm2d_model,
                    np.vstack([t_seed]),
                    np.concatenate([ra_seed, dec_seed]),
                    sigma=np.concatenate([sra_seed, sde_seed]),
                    absolute_sigma=True,
                )
            except Exception:
                popt_a = None
            popt_b = _ransac_pm2d_seed(t_seed, ra_seed, dec_seed, sra_seed, sde_seed, n_trials=2000, z_thresh=2.75, min_inliers=6)
            popt_c = _theil_sen_pm2d_seed(t_seed, ra_seed, dec_seed)

        # Keep only finite candidates (B, C, A order), but put seed_candidate first if present
        base_cands = [p for p in (popt_b, popt_c, popt_a) if p is not None and np.all(np.isfinite(p))]
        if seed_candidate is not None and np.all(np.isfinite(seed_candidate)):
            candidates = [seed_candidate] + base_cands
            debug_pm_init["seeds"].insert(0, {"method": "Literature seed", "pmra": float(seed_candidate[0]), "pmdec": float(seed_candidate[1]), "pos_ra": float(seed_candidate[2]), "pos_dec": float(seed_candidate[3])})
        else:
            candidates = base_cands

        # Simple motion scale heuristic from outer points
        if use_outer and t_seed.size > 1:
            rough_mu = np.median(np.abs(np.concatenate([
                (ra_seed - np.median(ra_seed)) / np.maximum(np.abs(t_seed), 1e-6),
                (dec_seed - np.median(dec_seed)) / np.maximum(np.abs(t_seed), 1e-6)
            ])))
        else:
            rough_mu = 0.0

        if not candidates:
            # Fallback to zeros to avoid crash; EM will adjust or rejection will drop all
            popt = np.array([0.0, 0.0, float(np.nanmedian(y_ra)), float(np.nanmedian(y_dec))], dtype=float)
            debug_pm_init["chosen"] = "none"
        else:
            # Score each seed by initial log-likelihood (equal mixture, crude stationary)
            best_ll = -np.inf
            popt = candidates[0]
            # Rough stationary centroids
            s_ra_stat = float(np.nanmedian(y_ra))
            s_dec_stat = float(np.nanmedian(y_dec))
            seed_map = {}
            if popt_b is not None: seed_map[tuple(np.round(popt_b, 12))] = "RANSAC"
            if popt_c is not None: seed_map[tuple(np.round(popt_c, 12))] = "Theil-Sen"
            if popt_a is not None: seed_map[tuple(np.round(popt_a, 12))] = "WLS"
            for cand in candidates:
                ra_m = cand[0] * tc + cand[2]
                dec_m = cand[1] * tc + cand[3]
                m2_mov = ((y_ra - ra_m) ** 2) / (sra ** 2) + ((y_dec - dec_m) ** 2) / (sde ** 2)
                m2_sta = ((y_ra - s_ra_stat) ** 2) / (sra ** 2) + ((y_dec - s_dec_stat) ** 2) / (sde ** 2)
                ll = np.sum(np.log(0.5 * np.exp(-0.5 * m2_mov) + 0.5 * np.exp(-0.5 * m2_sta) + 1e-300))
                mu_mag = np.hypot(cand[0], cand[1])
                penalty = 0.0
                if rough_mu > 10.0:
                    penalty = -0.1 * max(0.0, (10.0 * rough_mu / max(mu_mag, 1e-6)) - 1.0)
                score = ll + penalty
                if score > best_ll:
                    best_ll = score
                    popt = cand
                    key = tuple(np.round(popt, 12))
                    debug_pm_init["chosen"] = seed_map.get(key, "unknown")

        # --- Initialize stationary offsets from precision-weighted means ---
        w_ra0 = 1.0 / np.maximum(sra, 1e-6) ** 2
        w_dec0 = 1.0 / np.maximum(sde, 1e-6) ** 2
        s_ra_stat = float(np.sum(w_ra0 * y_ra) / np.sum(w_ra0)) if np.sum(w_ra0) > 0 else float(np.nanmedian(y_ra))
        s_dec_stat = float(np.sum(w_dec0 * y_dec) / np.sum(w_dec0)) if np.sum(w_dec0) > 0 else float(np.nanmedian(y_dec))

        # Start with neutral mixture weight (avoid bias to stationary if many near zero)
        w_mix = 0.5
        r = np.full(n, 0.5, dtype=float)

        # ===== EM inner loop =====
        for _em in range(12):
            model_concat = pm2d_model(xdata_in, *popt)
            ra_m = model_concat[:n]
            dec_m = model_concat[n:]

            m2_mov = ((y_ra - ra_m) ** 2) / (sra ** 2) + ((y_dec - dec_m) ** 2) / (sde ** 2)
            m2_sta = ((y_ra - s_ra_stat) ** 2) / (sra ** 2) + ((y_dec - s_dec_stat) ** 2) / (sde ** 2)

            # E-step with small temperature (anneal early responsibilities for stability)
            tau = 1.5 - 1.2 * (_em / 11.0)
            ratio = ((1.0 - w_mix) / max(w_mix, 1e-6)) * np.exp(0.5 / max(tau, 0.3) * (m2_mov - m2_sta))
            r = 1.0 / (1.0 + ratio)
            r = np.clip(r, 1e-4, 1.0 - 1e-4)

            # M-step: refit moving with r-weights
            scale = np.sqrt(r)
            sigma_eff = np.concatenate([sra / scale, sde / scale])
            popt, pcov = curve_fit(
                pm2d_model,
                xdata_in,
                ydata_in,
                sigma=sigma_eff,
                absolute_sigma=True,
                maxfev=20000
            )

            # Update stationary offsets
            w_s_ra = (1.0 - r) / (sra ** 2)
            w_s_dec = (1.0 - r) / (sde ** 2)
            if np.sum(w_s_ra) > 0:
                s_ra_stat = float(np.sum(w_s_ra * y_ra) / np.sum(w_s_ra))
            if np.sum(w_s_dec) > 0:
                s_dec_stat = float(np.sum(w_s_dec * y_dec) / np.sum(w_s_dec))

            # Update mixture weight; keep away from extremes
            w_mix = float(np.clip(np.mean(r), 0.1, 0.9))

        # --- Outlier rejection based on moving-component residuals over ALL rows ---
        x_all = np.vstack([t_all - t0_ref])
        model_all = pm2d_model(x_all, *popt)
        ra_model_all = model_all[:len(t_all)]
        dec_model_all = model_all[len(t_all):]

        ra_res = y_ra_all - ra_model_all
        dec_res = y_dec_all - dec_model_all

        z_ra = np.abs(ra_res / sig_ra_all)
        z_dec = np.abs(dec_res / sig_dec_all)

        new_inlier_mask = (z_ra < sigma_threshold) & (z_dec < sigma_threshold)

        if np.array_equal(inlier_mask, new_inlier_mask):
            break
        inlier_mask = new_inlier_mask

    # Optional error inflation (global and/or per mission)
    if inflate_errors:
        # Residuals for inliers with current fit
        x_all = np.vstack([t_all - t0_ref])
        model_all = pm2d_model(x_all, *popt)
        ra_model_all = model_all[:len(t_all)]
        dec_model_all = model_all[len(t_all):]

        ra_res_in = (y_ra_all - ra_model_all)[inlier_mask]
        dec_res_in = (y_dec_all - dec_model_all)[inlier_mask]
        ra_sig_in = sig_ra_all[inlier_mask]
        dec_sig_in = sig_dec_all[inlier_mask]

        dof_ra = max(1, ra_res_in.size - 2)  # pm + intercept
        dof_dec = max(1, dec_res_in.size - 2)

        s_add_ra = _solve_sigma_add(ra_res_in, ra_sig_in, dof_ra)
        s_add_dec = _solve_sigma_add(dec_res_in, dec_sig_in, dof_dec)

        # Refit with inflated uncertainties on inliers
        sigma_vec = np.sqrt(np.concatenate([
            (sig_ra_all[inlier_mask] ** 2 + s_add_ra ** 2),
            (sig_dec_all[inlier_mask] ** 2 + s_add_dec ** 2)
        ]))
        popt, pcov = curve_fit(
            pm2d_model,
            np.vstack([t_all[inlier_mask] - t0_ref]),
            np.concatenate([y_ra_all[inlier_mask], y_dec_all[inlier_mask]]),
            sigma=sigma_vec,
            absolute_sigma=True
        )

        # Per-mission inflation (optional)
        s_add_ra_by_mission = {}
        s_add_dec_by_mission = {}
        if per_mission_inflate and mission_labels is not None:
            missions_arr = np.asarray(mission_labels)
            model_all = pm2d_model(np.vstack([t_all - t0_ref]), *popt)
            ra_model_all = model_all[:len(t_all)]
            dec_model_all = model_all[len(t_all):]
            ra_sig2 = sig_ra_all ** 2
            dec_sig2 = sig_dec_all ** 2
            for m in np.unique(missions_arr[inlier_mask]):
                mask_m = (missions_arr == m) & inlier_mask
                if mask_m.sum() >= 3:
                    dof_ra_m = max(1, mask_m.sum() - 2)
                    dof_dec_m = max(1, mask_m.sum() - 2)
                    s_ra_m = _solve_sigma_add((y_ra_all - ra_model_all)[mask_m], sig_ra_all[mask_m], dof_ra_m)
                    s_dec_m = _solve_sigma_add((y_dec_all - dec_model_all)[mask_m], sig_dec_all[mask_m], dof_dec_m)
                    s_add_ra_by_mission[m] = float(s_ra_m)
                    s_add_dec_by_mission[m] = float(s_dec_m)
                    ra_sig2[missions_arr == m] = sig_ra_all[missions_arr == m] ** 2 + s_ra_m ** 2
                    dec_sig2[missions_arr == m] = sig_dec_all[missions_arr == m] ** 2 + s_dec_m ** 2
                else:
                    s_add_ra_by_mission[m] = 0.0
                    s_add_dec_by_mission[m] = 0.0
            sigma_vec = np.sqrt(np.concatenate([ra_sig2[inlier_mask], dec_sig2[inlier_mask]]))
            popt, pcov = curve_fit(
                pm2d_model,
                np.vstack([t_all[inlier_mask] - t0_ref]),
                np.concatenate([y_ra_all[inlier_mask], y_dec_all[inlier_mask]]),
                sigma=sigma_vec,
                absolute_sigma=True
            )
        else:
            s_add_ra_by_mission = {}
            s_add_dec_by_mission = {}
    else:
        s_add_ra_by_mission = {}
        s_add_dec_by_mission = {}

    # Extract results
    pmra, pmdec, pos_ra_m, pos_dec_m = popt
    e_pmra, e_pmdec = np.sqrt(np.diag(pcov))[0], np.sqrt(np.diag(pcov))[1]

    return (pmra, pmdec, e_pmra, e_pmdec,
        inlier_mask,
        s_add_ra, s_add_dec,
        s_add_ra_by_mission, s_add_dec_by_mission,
        pos_ra_m, pos_dec_m, s_ra_stat, s_dec_stat,
        debug_pm_init)

# Group by binned time and calculate weighted averages
def weighted_combination(group):
    # Extract RA and Dec values and their uncertainties
    x_ra = group["rel_ra"].values
    ex_ra = group["ra_unc_mas"].values
    x_dec = group["rel_dec"].values
    ex_dec = group["dec_unc_mas"].values

    # Filter out NaN values for RA
    valid_ra_mask = ~np.isnan(x_ra) & ~np.isnan(ex_ra)
    x_ra = x_ra[valid_ra_mask]
    ex_ra = ex_ra[valid_ra_mask]

    # Filter out NaN values for Dec
    valid_dec_mask = ~np.isnan(x_dec) & ~np.isnan(ex_dec)
    x_dec = x_dec[valid_dec_mask]
    ex_dec = ex_dec[valid_dec_mask]

    # Handle cases with no valid data
    if len(x_ra) == 0:
        combined_ra = np.nan
        combined_ra_unc = np.nan
    elif len(x_ra) == 1:
        combined_ra = x_ra[0]
        combined_ra_unc = ex_ra[0]
    else:
        weights_ra = 1 / np.maximum(ex_ra, 0.7 * np.median(ex_ra))**2
        weights_ra /= weights_ra.sum()  # Normalize weights
        combined_ra = np.sum(x_ra * weights_ra)
        bias_ra = 1 - np.sum(weights_ra**2)
        wstd_ra = np.sqrt(np.sum(weights_ra * (x_ra - combined_ra)**2) / bias_ra) if bias_ra > 0 else 0
        combined_ra_unc = np.sqrt(wstd_ra**2)

    if len(x_dec) == 0:
        combined_dec = np.nan
        combined_dec_unc = np.nan
    elif len(x_dec) == 1:
        combined_dec = x_dec[0]
        combined_dec_unc = ex_dec[0]
    else:
        weights_dec = 1 / np.maximum(ex_dec, 0.7 * np.median(ex_dec))**2
        weights_dec /= weights_dec.sum()  # Normalize weights
        combined_dec = np.sum(x_dec * weights_dec)
        bias_dec = 1 - np.sum(weights_dec**2)
        wstd_dec = np.sqrt(np.sum(weights_dec * (x_dec - combined_dec)**2) / bias_dec) if bias_dec > 0 else 0
        combined_dec_unc = np.sqrt(wstd_dec**2)

    # Return combined results as a Series
    return pd.Series({
        "rel_ra": combined_ra,
        "ra_unc_mas": combined_ra_unc,
        "rel_dec": combined_dec,
        "dec_unc_mas": combined_dec_unc,
        "ndata":len(x_ra)
    })

# def format_value_with_error(value, error, unit=""):
#     """
#     Formats a value with its error, ensuring clean rounding and no floating-point artifacts.
#     If the value or error is None, it returns "N/A".
#     """
#     if pd.isna(value) or pd.isna(error) or value == "N/A" or error == "N/A":
#         return "N/A"
    
#     # Calculate the significant digit for the error
#     error_magnitude = 10 ** floor(log10(abs(error)))
#     rounded_error = round(error / error_magnitude) * error_magnitude

#     # Ensure the value is rounded to the same number of significant digits as the error
#     significant_digits = -int(floor(log10(abs(rounded_error))))
#     significant_digits = max(0, -int(floor(log10(abs(rounded_error)))))
#     rounded_value = round(value, max(0, significant_digits))

#     # Format the result to remove floating-point artifacts
#     rounded_value_str = f"{rounded_value:.{significant_digits}f}".rstrip('0').rstrip('.')
#     rounded_error_str = f"{rounded_error:.{significant_digits}f}".rstrip('0').rstrip('.')

#     # Return formatted string with ± symbol and unit
#     return f"{rounded_value_str} ± {rounded_error_str}" + (f" {unit}" if unit else "")

def format_value_with_error(value, error, unit=""):
    """
    Formats a value with its error, ensuring clean rounding and no floating-point artifacts.
    If the value or error is None, it returns "N/A".
    """
    if pd.isna(value) or pd.isna(error) or value == "N/A" or error == "N/A":
        return "N/A"

    # Round the error to 1 significant digit
    error_exp = floor(log10(abs(error)))
    rounded_error = round(error, -error_exp)
    
    # Round the value to the same decimal place
    rounded_value = round(value, -error_exp)

    # Format
    rounded_value_str = str(int(rounded_value)) if error_exp >= 0 else f"{rounded_value:.{-error_exp}f}"
    rounded_error_str = str(int(rounded_error)) if error_exp >= 0 else f"{rounded_error:.{-error_exp}f}"

    return f"{rounded_value_str} ± {rounded_error_str}" + (f" {unit}" if unit else "")

def wrap_text(text, width=50):
    """Wraps text with line breaks every 'width' characters."""
    if not text:  # Handles None or empty string
        return ""
    return '<br>'.join([text[i:i+width] for i in range(0, len(text), width)])

# Define the initial layout of the page
# Layout
layout = html.Div([
    dcc.Location(id="url", refresh=False),
    html.Div([
        html.H1("Astrometric Explorer"),
        html.P("This page allows to compare the individual-epoch astrometry of MOCAdb entries "
               " with their best-available proper motion and parallax solutions."
               ),
    ], style={'width': '100%', 'display': 'inline-block'}),
    
    dcc.Input(
        id="astrometry-dropdown-search",
        placeholder="Filter dropdown menu by object name or MOCA OID then press Enter",
        type="text",
        debounce=True,
        style={
            "width": "100%",  # Full width
            "padding": "0.5rem",  # Optional padding for better alignment
            "fontSize": "16px"  # Match the dropdown font size
        }
    ),
    dcc.Dropdown(
        id="astrometry-filtered-dropdown",
        options=[],  # Will be populated dynamically
        placeholder="Specify an object name or moca_oid above",
        searchable=True,
        style={
        "width": "100%",  # Full width
        "fontSize": "16px"  # Ensure font size matches input
        }
    ),

    dcc.Dropdown(
        id="mission-toggle-dropdown",
        options=[],  # Will be dynamically populated
        multi=True,
        placeholder="Select missions to display",
        style={
            "width": "100%",
            "fontSize": "16px",
            "marginTop": "10px"
        }
    ),

    html.Div([
        # Column 1
        html.Div([
            # UltraNest now *only* refines EM results using EM inliers + inflated errors
            dcc.Checklist(
                id="subtract-pm-checkbox",
                options=[{'label': 'Subtract proper motion', 'value': 'subtract_pm'}],
                value=[],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="subtract-plx-checkbox",
                options=[{'label': 'Subtract parallax motion', 'value': 'subtract_plx'}],
                value=[],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="phase-yr-checkbox",
                options=[{'label': 'Phase yearly', 'value': 'phase'}],
                value=[],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="astrometry-bin-checkbox",
                options=[{'label': 'Bin data by '+str(bin_size_days)+'-day intervals ('+str(bin_size_days_phased)+' days if phased yearly) just for display', 'value': 'bin_checked'}],
                value=[],  # Default is unchecked
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
        ], style={'display': 'inline-block', 'vertical-align': 'top', 'width': '50%', 'padding-right': '10px'}),
        
        # Column 2
        html.Div([
            dcc.Checklist(
                id="adjust-reference-epoch-checkbox",
                options=[{'label': 'Adjust reference epoch', 'value': 'adjust_ref'}],
                value=['adjust_ref'],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="fit-proper-motion-checkbox",
                options=[{'label': 'Fit proper motion', 'value': 'fit_pm'}],
                value=['adjust_ref'],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="fit-parallax-checkbox",
                options=[{'label': 'Fit parallax', 'value': 'fit_plx'}],
                value=[],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="fit-ultranest-checkbox",
                options=[{
                    'label': (
                        'Fit using ultranest (slow)'
                        if _ULTRANEST_AVAILABLE
                        else 'Fit using ultranest (slow): requires local mocaviz install'
                    ),
                    'value': 'ultranest'
                }],
                value=[],
                inline=True,
                style={
                    'margin-bottom': '10px',
                    'font-size': '16px',
                    'opacity': (1.0 if _ULTRANEST_AVAILABLE else 0.5),
                    'pointerEvents': ('auto' if _ULTRANEST_AVAILABLE else 'none')
                }
            ),
            dcc.Checklist(
                id="inflate-errors-checkbox",
                options=[{'label': 'Back propagate residuals into measurement errors during fit', 'value': 'inflate'}],
                value=['inflate'],  # default ON
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="only-use-recalibrated-checkbox",
                options=[{'label': 'Only use recalibrated astrometry when possible', 'value': 'only_recalibrated'}],
                value=['only_recalibrated'], # default ON
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="revert-raw-checkbox",
                options=[{'label': 'Revert all astrometry to pre-calibration', 'value': 'revert_raw'}],
                value=[],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            )
            ], style={'display': 'inline-block', 'vertical-align': 'top', 'width': '50%', 'padding-left': '10px'})
        ], style={'display': 'flex', 'width': '100%', 'margin-bottom': '20px'}),

    html.Div([
        html.Button("Push PM fit", id="astrometry-push-pm", n_clicks=0, disabled=True, style={'fontSize': '12px', 'border': '3px solid black', 'verticalAlign': 'middle', 'marginRight': '12px', 'display': 'none'}),
        html.Button("Push PM+PLX fit", id="astrometry-push-pmplx", n_clicks=0, disabled=True, style={'fontSize': '12px', 'border': '3px solid black', 'verticalAlign': 'middle', 'display': 'none'}),
        html.Div(id="astrometry-push-output", style={'display': 'none', 'marginTop': '10px'}),
        html.Pre(id="astrometry-ultranest-output", style={'display': 'none', 'marginTop': '10px', 'fontSize': '11px', 'whiteSpace': 'pre-wrap'}),
        dcc.Interval(id="astrometry-ultranest-interval", interval=1500, n_intervals=0),
    ], style={'marginTop': '10px', 'marginBottom': '10px'}),

    html.Div([
        dcc.Graph(id="astrometry-plot-ra"),
    ], style={'width': '100%', 'display': 'inline-block', 'margin-bottom': '20px'}),
    
    html.Div([
        dcc.Graph(id="astrometry-plot-dec"),
    ], style={'width': '100%', 'display': 'inline-block'}),

    html.Div([
        html.Div("URL parameter: moca_oid", style={"fontWeight": "bold", "marginBottom": "6px"}),
        html.P(
            "You can deep‑link this page to a specific object by passing a moca_oid in the URL query string. "
            "This selects the object in the dropdown on load and renders its astrometry. "
            "No credentials parameters are required for this feature."),
        html.Div("Examples:", style={"fontStyle": "italic", "marginTop": "4px"}),
        html.Pre(
            "?moca_oid=602\n"
            "?moca_oid=156",
            style={"backgroundColor": "#f7f7f7", "padding": "8px", "border": "1px solid #ddd", "overflowX": "auto", "marginTop": "4px"}
        ),
        html.Ul([
            html.Li("If omitted, the page defaults to moca_oid=602."),
            html.Li("If the id doesn’t exist or isn’t accessible, the dropdown will stay on the default."),
        ], style={"marginTop": "4px"}),
    ], style={
        "border": "1px solid #ddd",
        "backgroundColor": "#fcfcfc",
        "padding": "10px 12px",
        "borderRadius": "4px",
        "marginTop": "14px",
        "marginBottom": "6px",
        "lineHeight": 1.5
    }),

    dcc.Store(id='astrometry-fit-store'),

], style={'width': '65%', 'display': 'inline-block','padding-left': '15px'})

# Register the page now that layout is defined (helps with eager imports).
dash.register_page(__name__, layout=layout)

@dash.callback(
    output=[
        Output("astrometry-filtered-dropdown", "options"),
        Output("astrometry-filtered-dropdown", "value"),
    ],
    inputs=[
        Input("url", "href"),
        Input("astrometry-dropdown-search", "value"),  # Search input from the dropdown search box
    ],
    state=[State("url", "search")]
)
def update_dropdown(href, search_value, url_search):

    # Parse URL parameters
    parsed_url_data = _parse_url_search(url_search)
    
    # Check for moca_oid (or oid) in the URL query parameters
    moca_oid_param = parsed_url_data.get('moca_oid', parsed_url_data.get('oid', [None]))[0]

    env_username = parsed_url_data.get('user', [None])[0]
    env_password = parsed_url_data.get('pwd', [None])[0]
    env_dbname = parsed_url_data.get('dbase', [None])[0]

    default_host = 'mocadb.ca'
    default_username = 'public'
    default_password = 'z@nUg_2h7_%?31y88'
    default_dbname = 'mocadb'
    default_moca_oid = 602  # Default MOCA OID when no input is provided
    
    if env_username is None:
        env_username = os.environ.get('MOCA_USERNAME', default_username)
    if env_password is None:
        env_password = os.environ.get('MOCA_PASSWORD', default_password)
    if env_dbname is None:
        env_dbname = os.environ.get('MOCA_DBNAME', default_dbname)
    env_host = os.environ.get('MOCA_HOST', default_host)

    if env_username is None:
        return dash.no_update
    if env_password is None:
        return dash.no_update
    if env_dbname is None:
        return dash.no_update

    # Establish connection to the database
    engine = get_engine_from_url(url_search)
    connection = engine.connect()
    metadata = MetaData()

    # Define only needed columns explicitly (avoid reflection warnings for MySQL/MariaDB POINT types)
    moca_objects = Table(
        'moca_objects', metadata,
        Column('moca_oid', Integer),
        Column('designation', String(255)),
    )
    mechanics_all_designations = Table(
        'mechanics_all_designations', metadata,
        Column('moca_oid', Integer),
        Column('designation', String(255)),
    )

    # Determine the query logic based on inputs
    if search_value:  # If a search term is provided
        search_query = f"%{search_value}%"
        query = (
            select([mechanics_all_designations.c.moca_oid, mechanics_all_designations.c.designation])
            .where(
                or_(
                    mechanics_all_designations.c.designation.ilike(search_query),
                    cast(mechanics_all_designations.c.moca_oid, String).ilike(search_query)
                )
            )
            .limit(25)  # Limit to a reasonable number of results
        )
    elif moca_oid_param:  # If a specific moca_oid is provided in the URL
        query = (
            select([moca_objects.c.moca_oid, moca_objects.c.designation])
            .where(moca_objects.c.moca_oid == int(moca_oid_param))
        )
    else:  # Default to the row with moca_oid=602
        query = (
            select([moca_objects.c.moca_oid, moca_objects.c.designation])
            .where(moca_objects.c.moca_oid == default_moca_oid)
        )
    
    result_df = pd.read_sql(query, connection)

    # Format dropdown options by concatenating in Python
    dataset_options = [
        {"label": f"{row['moca_oid']}|{row['designation']}", "value": str(row['moca_oid'])}
        for _, row in result_df.iterrows()
    ]

    # Determine the default value
    if moca_oid_param and moca_oid_param in result_df['moca_oid'].astype(str).tolist():
        default_value = str(moca_oid_param)
    else:
        default_value = str(default_moca_oid)

    connection.close()
    return dataset_options, default_value

@dash.callback(
    Output("mission-toggle-dropdown", "options"),
    Output("mission-toggle-dropdown", "value"),
    Input("astrometry-filtered-dropdown", "value"),
    State("url", "search"),
    prevent_initial_call=True
)
def update_mission_dropdown(selected_dataset, url_search):
    if not selected_dataset:
        return [], []
    
    moca_oid = selected_dataset
    engine = get_engine_from_url(url_search)
    connection = engine.connect()
    metadata = MetaData()

    # Reflect the relevant table and fetch unique missions
    data_equatorial_coordinates = Table(
        "data_equatorial_coordinates", metadata,
        Column("id", Integer),
        Column("moca_oid", Integer),
        Column("ra", Float),
        Column("dec", Float),
        Column("measurement_epoch_yr", Float),
        Column("ra_unc_mas", Float),
        Column("dec_unc_mas", Float),
        Column("measurement_epoch_yr_unc", Float),
        Column("ignored", Integer),
        Column("single_epoch", Integer),
        Column("adopt_as_reference", Integer),
        Column("mission_name", String(64)),
        Column("data_release", String(64)),
        Column("moca_pid", String(64)),
        Column("origin", String(255)),
        Column("comments", Text),
        Column("airmass", Float),
        Column("moca_psid", Integer),
        Column("calibration_delta_ra_mas", Float),
        Column("calibration_delta_dec_mas", Float),
        Column("nstars_calibration", Integer),
        Column("calibration_method", String(64)),
    )
    query = select(
            func.coalesce(
                case(
                    # Check if the concatenated mission name is empty after trimming spaces
                    [
                        (func.trim(func.concat(data_equatorial_coordinates.c.mission_name, ' ', data_equatorial_coordinates.c.data_release)) == "", "No mission"),
                    ],
                    else_=func.coalesce(
                        func.concat(data_equatorial_coordinates.c.mission_name, ' ', data_equatorial_coordinates.c.data_release),
                        data_equatorial_coordinates.c.moca_pid
                    )
                ),
                'No mission'  # Fallback if all other options are NULL
            ).label('mission')
        ).distinct().where(
        and_(
            data_equatorial_coordinates.c.moca_oid == moca_oid,
            data_equatorial_coordinates.c.ignored == 0,
            data_equatorial_coordinates.c.single_epoch == 1
            )
    )

    missions_df = pd.read_sql(query, connection)
    connection.close()

    # Generate options for the dropdown
    mission_options = [{"label": mission, "value": mission} for mission in missions_df['mission']]
    return mission_options, [option["value"] for option in mission_options]  # Select all by default


# Define the callback to update the scatter plot based on input
try:
    import sys
    try:
        import dash
        _app_at_decorator = dash.get_app()
        _app_id = id(_app_at_decorator) if _app_at_decorator is not None else None
    except Exception:
        _app_id = None
    sys.stderr.write(
        "[astrometry:init] reached callback decorator for update_astrometry_scatter_plot "
        f"(dash.get_app id={_app_id})\n"
    )
    sys.stderr.flush()
except Exception:
    pass
@dash.callback(
    [
        Output("astrometry-plot-ra", "figure"),
        Output("astrometry-plot-ra", "config"),
        Output("astrometry-plot-dec", "figure"),
        Output("astrometry-plot-dec", "config"),
        Output("astrometry-fit-store", "data"),
    ],
    [
        Input("astrometry-filtered-dropdown", "value"),
        Input("mission-toggle-dropdown", "value"),
        Input("subtract-pm-checkbox", "value"),
        Input("subtract-plx-checkbox", "value"),
        Input("phase-yr-checkbox", "value"),
        Input("adjust-reference-epoch-checkbox", "value"),
        Input("only-use-recalibrated-checkbox", "value"),
        Input("revert-raw-checkbox", "value"),
        Input("astrometry-bin-checkbox", "value"),
        Input("fit-proper-motion-checkbox", "value"),
        Input("fit-parallax-checkbox", "value"),
        Input("fit-ultranest-checkbox", "value"),
        Input("inflate-errors-checkbox", "value"),
        Input("astrometry-plot-ra", "selectedData"),
        Input("astrometry-plot-dec", "selectedData"),
    ],
    [State("url", "search")],
)
def update_astrometry_scatter_plot(selected_dataset, selected_missions, pm_checkbox_values, plx_checkbox_values, phase_checkbox_values, adjust_ref_checkbox_values, only_recalibrated_checkbox_values, revert_raw_checkbox_values, bin_checkbox_values, fit_pm_values, fit_plx_values, ultranest_values, inflate_err_values, selectedData_ra, selectedData_dec, url_search):
    ctx = dash.callback_context
    fit_payload = None
    fit_mode = None
    fit_ultranest = False
    fit_ra0_mov = None
    fit_dec0_mov = None
    fit_ra_unc_mas = None
    fit_dec_unc_mas = None
    fit_epoch_ref = None
    try:
        import sys
        sys.stderr.write(
            f"[astrometry.update_astrometry_scatter_plot] ENTER oid={selected_dataset} missions={'None' if selected_missions is None else (len(selected_missions) if isinstance(selected_missions, list) else 'nonlist')}\n"
        )
        sys.stderr.flush()
    except Exception:
        pass
    def _diag(reason: str):
        fig = go.Figure()
        fig.update_layout(
            title=(
                f"ASTROMETRY DIAG | {reason} | "
                f"oid={selected_dataset} | "
                f"missions={'None' if selected_missions is None else (len(selected_missions) if isinstance(selected_missions, list) else selected_missions)} | "
                f"triggered={(ctx.triggered[0]['prop_id'] if ctx and ctx.triggered else 'none')} | "
                f"{ASTROMETRY_PAGE_VERSION} | {datetime.utcnow().isoformat()}Z"
            ),
            xaxis_title="Epoch (Year)",
            yaxis_title="Offset (mas)",
        )
        return fig, figure_export_config, fig, figure_export_config, None
    
    if not selected_dataset:
        return _diag("EARLY EXIT: no selected_dataset")
    #if not selected_dataset:
    #    return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    # If URL contains ?debug_astrometry=1, return a tiny figure immediately.
    # This helps diagnose server timeouts / response-size issues.
    parsed_url = _parse_url_search(url_search)
    if str(parsed_url.get('debug_astrometry', [None])[0]).strip() == '1':
        dbg = go.Figure()
        dbg.update_layout(
            title=(
                f"DEBUG_ASTROMETRY=1 | callback reached | oid={selected_dataset} | "
                f"missions={'None' if selected_missions is None else (len(selected_missions) if isinstance(selected_missions, list) else selected_missions)} | "
                f"{ASTROMETRY_PAGE_VERSION} | {datetime.utcnow().isoformat()}Z"
            ),
            xaxis_title="Epoch (Year)",
            yaxis_title="Offset (mas)",
        )
        dbg.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode='lines', name='ping'))
        return dbg, figure_export_config, dbg, figure_export_config, None

    # Make selected_missions robust if None
    if selected_missions is None:
        selected_missions = []
    
    subtract_pm = 'subtract_pm' in pm_checkbox_values  # Check if the checkbox is selected
    subtract_plx = 'subtract_plx' in plx_checkbox_values  # Check if the checkbox is selected
    phase_yearly = 'phase' in phase_checkbox_values  # Check if the checkbox is selected
    adjust_reference_epoch = 'adjust_ref' in adjust_ref_checkbox_values  # Check if the checkbox is selected
    only_recalibrated = 'only_recalibrated' in only_recalibrated_checkbox_values  # Check if the checkbox is selected
    revert_raw = 'revert_raw' in revert_raw_checkbox_values  # Check if the checkbox is selected
    bin_activated = 'bin_checked' in bin_checkbox_values
    fit_pm = 'fit_pm' in fit_pm_values
    fit_plx = 'fit_plx' in fit_plx_values
    inflate_errors = 'inflate' in inflate_err_values
    use_ultranest = 'ultranest' in ultranest_values

    triggered_prop = ctx.triggered[0]["prop_id"] if ctx.triggered else ""
    triggered_by_selection = triggered_prop.endswith(".selectedData")

    if triggered_by_selection:
        pts_ra = (selectedData_ra or {}).get("points") or []
        pts_dec = (selectedData_dec or {}).get("points") or []
        if (len(pts_ra) == 0) and (len(pts_dec) == 0):
            return _diag("EARLY EXIT: triggered_by_selection but no points selected")
        # Otherwise, allow the callback to proceed and use the selection downstream.
    
    try:
        moca_oid = selected_dataset
        #moca_oid, designation = selected_dataset.split('|')
    except ValueError as e:
        return _diag(f"EARLY EXIT: ValueError: {e}")

    try:
        engine = get_engine_from_url(url_search)
        import sys
        sys.stderr.write(f"[astrometry.update_astrometry_scatter_plot] fired oid={moca_oid} missions={'ALL' if not selected_missions else len(selected_missions)}\n")
        sys.stderr.flush()
        connection = engine.connect()
        metadata = MetaData()

        #Query combined coordinates
        data_equatorial_coordinates = Table(
            "data_equatorial_coordinates", metadata,
            Column("id", Integer),
            Column("moca_oid", Integer),
            Column("ra", Float),
            Column("dec", Float),
            Column("measurement_epoch_yr", Float),
            Column("ra_unc_mas", Float),
            Column("dec_unc_mas", Float),
            Column("measurement_epoch_yr_unc", Float),
            Column("ignored", Integer),
            Column("single_epoch", Integer),
            Column("adopt_as_reference", Integer),
            Column("mission_name", String(64)),
            Column("data_release", String(64)),
            Column("moca_pid", String(64)),
            Column("origin", String(255)),
            Column("comments", Text),
            Column("airmass", Float),
            Column("moca_psid", Integer),
            Column("calibration_delta_ra_mas", Float),
            Column("calibration_delta_dec_mas", Float),
            Column("nstars_calibration", Integer),
            Column("calibration_method", String(64)),
        )

        query = select(data_equatorial_coordinates.c.ra,
                       data_equatorial_coordinates.c.dec,
                       data_equatorial_coordinates.c.measurement_epoch_yr
                       ).where(
            and_(data_equatorial_coordinates.c.moca_oid == moca_oid, data_equatorial_coordinates.c.adopt_as_reference == 1)
        )
        ref_df = pd.read_sql(query, connection)
        if ref_df.empty:
            empty_figure = go.Figure()
            empty_figure.update_layout(
                title="No reference epoch available (adopt_as_reference=1 not found)",
                xaxis_title="Epoch (Year)",
                yaxis_title="Offset (mas)",
            )
            return empty_figure, figure_export_config, empty_figure, figure_export_config, None
        ra_ref, dec_ref, epoch_ref = ref_df.iloc[0]["ra"], ref_df.iloc[0]["dec"], ref_df.iloc[0]["measurement_epoch_yr"]
        if not np.isfinite(epoch_ref):
            epoch_ref = np.nan
        fit_epoch_ref = epoch_ref

        def _pick_unc(primary_val, series_fallback):
            try:
                if primary_val is not None and np.isfinite(primary_val):
                    return float(primary_val)
            except Exception:
                pass
            try:
                arr = pd.to_numeric(series_fallback, errors='coerce')
                finite = arr[np.isfinite(arr)]
                if finite.size > 0:
                    return float(np.nanmedian(finite))
            except Exception:
                pass
            return None

        #Query PM
        data_proper_motions = Table(
            'data_proper_motions', metadata,
            Column('moca_oid', Integer),
            Column('pmra_masyr', Float),
            Column('pmdec_masyr', Float),
            Column('pmra_masyr_unc', Float),
            Column('pmdec_masyr_unc', Float),
            Column('moca_pid', String(64)),
            Column('origin', String(255)),
            Column('mission_name', String(64)),
            Column('data_release', String(64)),
            Column('adopted', Integer),
        )
        moca_publications = Table(
            'moca_publications', metadata,
            Column('moca_pid', String(64)),
            Column('name', String(255)),
        )
        pm_publications = moca_publications.alias('pm_publications')

        query = (select([data_proper_motions.c.pmra_masyr,
                       data_proper_motions.c.pmdec_masyr,
                       data_proper_motions.c.pmra_masyr_unc,
                       data_proper_motions.c.pmdec_masyr_unc,
                       func.concat(func.coalesce(func.coalesce(pm_publications.c.name, pm_publications.c.moca_pid), data_proper_motions.c.origin),func.coalesce(func.concat(', ',data_proper_motions.c.mission_name,func.coalesce(func.concat(' ',data_proper_motions.c.data_release),'')),'')).label('pm_ref')
                    ])
                    .select_from(data_proper_motions
                                .outerjoin(
                                    pm_publications,
                                    (pm_publications.c.moca_pid == data_proper_motions.c.moca_pid)
                                )
                        )
                    .where(
                        and_(data_proper_motions.c.moca_oid == moca_oid, data_proper_motions.c.adopted == 1)
                    ).limit(1))
    
        pm_df = pd.read_sql(query, connection)
        if pm_df.empty:
            pm_df = pd.DataFrame([{ 'pmra_masyr': np.nan, 'pmdec_masyr': np.nan, 'pmra_masyr_unc': np.nan, 'pmdec_masyr_unc': np.nan, 'pm_ref': 'No adopted PM' }])

        #Query PLX
        data_parallaxes = Table(
            'data_parallaxes', metadata,
            Column('moca_oid', Integer),
            Column('parallax_mas', Float),
            Column('parallax_mas_unc', Float),
            Column('moca_pid', String(64)),
            Column('origin', String(255)),
            Column('mission_name', String(64)),
            Column('data_release', String(64)),
            Column('adopted', Integer),
        )
        plx_publications = moca_publications.alias('plx_publications')

        query = (select([data_parallaxes.c.parallax_mas,
                       data_parallaxes.c.parallax_mas_unc,
                       func.concat(func.coalesce(func.coalesce(plx_publications.c.name, plx_publications.c.moca_pid), data_parallaxes.c.origin),func.coalesce(func.concat(', ',data_parallaxes.c.mission_name,func.coalesce(func.concat(' ',data_parallaxes.c.data_release),'')),'')).label('plx_ref')
                    ])
                    .select_from(data_parallaxes
                                .outerjoin(
                                    plx_publications,
                                    (plx_publications.c.moca_pid == data_parallaxes.c.moca_pid)
                                )
                        )
                    .where(
                        and_(data_parallaxes.c.moca_oid == moca_oid, data_parallaxes.c.adopted == 1)
                    ).limit(1))

        plx_df = pd.read_sql(query, connection)
        if plx_df.empty:
            plx_df = pd.DataFrame([{ 'parallax_mas': np.nan, 'parallax_mas_unc': np.nan, 'plx_ref': 'No adopted PLX' }])

        #Query all coordinates
        moca_missions = Table(
            'moca_missions', metadata,
            Column('mission_name', String(64)),
            Column('data_release', String(64)),
            Column('include_in_recalibrated_display', Integer),
        )

        # Conditionally construct the "ra" and "dec" columns
        if revert_raw:
            ra_column = (data_equatorial_coordinates.c.ra -
                        func.ifnull(
                            data_equatorial_coordinates.c.calibration_delta_ra_mas /
                            (3600 * 1000 * func.cos(data_equatorial_coordinates.c.dec * func.pi() / 180)), 0)
                        ).label('ra')
            dec_column = (data_equatorial_coordinates.c.dec -
                        func.ifnull(
                            data_equatorial_coordinates.c.calibration_delta_dec_mas /
                            (3600 * 1000), 0)
                        ).label('dec')
        else:
            ra_column = data_equatorial_coordinates.c.ra.label('ra')
            dec_column = data_equatorial_coordinates.c.dec.label('dec')

        # Left join to missions to know whether a detections table exists for a mission
        dec_base = data_equatorial_coordinates.outerjoin(
            moca_missions,
            and_(
                moca_missions.c.mission_name == data_equatorial_coordinates.c.mission_name,
                moca_missions.c.data_release == data_equatorial_coordinates.c.data_release,
            )
        )

        # Build the recalibration condition: require calibrated OR mission explicitly allowed
        recalib_condition = or_(
            data_equatorial_coordinates.c.calibration_method.isnot(None),
            moca_missions.c.include_in_recalibrated_display == 1
        )

        query = select(
            data_equatorial_coordinates.c.id,
            ra_column,
            dec_column,
            data_equatorial_coordinates.c.measurement_epoch_yr,
            data_equatorial_coordinates.c.ra_unc_mas,
            data_equatorial_coordinates.c.dec_unc_mas,
            func.coalesce(data_equatorial_coordinates.c.measurement_epoch_yr_unc, 0).label('measurement_epoch_yr_unc'),
            func.coalesce(
                case(
                    [
                        (func.trim(func.concat(data_equatorial_coordinates.c.mission_name, ' ', data_equatorial_coordinates.c.data_release)) == "", "No mission"),
                    ],
                    else_=func.coalesce(
                        func.concat(data_equatorial_coordinates.c.mission_name, ' ', data_equatorial_coordinates.c.data_release),
                        data_equatorial_coordinates.c.moca_pid
                    )
                ), 'No mission'
            ).label('mission'),
            data_equatorial_coordinates.c.moca_pid,
            data_equatorial_coordinates.c.mission_name,
            data_equatorial_coordinates.c.data_release,
            data_equatorial_coordinates.c.origin,
            data_equatorial_coordinates.c.comments,
            data_equatorial_coordinates.c.airmass,
            data_equatorial_coordinates.c.moca_psid,
            data_equatorial_coordinates.c.calibration_delta_ra_mas,
            data_equatorial_coordinates.c.calibration_delta_dec_mas,
            data_equatorial_coordinates.c.nstars_calibration,
            data_equatorial_coordinates.c.calibration_method,
        ).select_from(dec_base).where(
            and_(
                data_equatorial_coordinates.c.moca_oid == moca_oid,
                data_equatorial_coordinates.c.ignored == 0,
                data_equatorial_coordinates.c.single_epoch == 1,
                recalib_condition if only_recalibrated else True,
            )
        )
        data_df = pd.read_sql(query, connection)
        if data_df.empty:
            empty_fig = go.Figure()
            empty_fig.update_layout(
                title=(
                    f"EMPTY data_df for oid={moca_oid} | "
                    f"missions={'ALL' if not selected_missions else selected_missions[:5]} | "
                    f"only_recalibrated={only_recalibrated} | revert_raw={revert_raw}"
                )
            )
            return empty_fig, figure_export_config, empty_fig, figure_export_config, None
    
        # NOTE: connection is closed in the finally block below
    
    except Exception as e:
        # Surface server-side exceptions directly in the figure titles so failures are visible
        try:
            print('[astrometry.update_astrometry_scatter_plot] ERROR:', repr(e))
        except Exception:
            pass
        err_fig = go.Figure()
        err_fig.update_layout(
            title=f"Astrometry callback error: {type(e).__name__}: {e}",
            xaxis_title="Epoch (Year)",
            yaxis_title="Offset (mas)",
        )
        return err_fig, figure_export_config, err_fig, figure_export_config, None
    finally:
        try:
            connection.close()
        except Exception:
            pass

    # Check if data_df is empty
    if data_df.empty:
        #return dash.no_update, dash.no_update
        # Return empty figures with a message
        empty_figure = go.Figure()
        empty_figure.update_layout(
            title="No data available",
            xaxis_title="Epoch (Year)",
            yaxis_title="Offset (mas)",
            xaxis=dict(showgrid=False, zeroline=False),
            yaxis=dict(showgrid=False, zeroline=False),
            annotations=[
                dict(
                    x=0.5, y=0.5, xref="paper", yref="paper",
                    text="No data available for the selected dataset",
                    showarrow=False,
                    font=dict(size=16)
                )
            ]
        )
        return empty_figure, figure_export_config, empty_figure, figure_export_config, None

    if selected_missions:
        data_df = data_df[data_df["mission"].isin(selected_missions)]

    # If adopted reference epoch is missing, fall back to the median finite epoch from points.
    if not np.isfinite(epoch_ref):
        epoch_vals = pd.to_numeric(data_df["measurement_epoch_yr"], errors='coerce').values
        finite_epoch_vals = epoch_vals[np.isfinite(epoch_vals)]
        if finite_epoch_vals.size > 0:
            epoch_ref = float(np.nanmedian(finite_epoch_vals))
            fit_epoch_ref = epoch_ref

    # Calculate relative offsets
    data_df["rel_ra"] = (data_df["ra"] - ra_ref) * np.cos(np.radians(dec_ref)) * 3600 * 1000
    data_df["rel_dec"] = (data_df["dec"] - dec_ref) * 3600 * 1000
    # Cap number of points to keep Dash response sizes reasonable on the server
    MAX_PLOT_POINTS = 4000
    if len(data_df) > MAX_PLOT_POINTS:
        # Keep a deterministic subset (by epoch) to avoid randomness across updates
        data_df = data_df.sort_values('measurement_epoch_yr').iloc[::max(1, len(data_df)//MAX_PLOT_POINTS)].copy()

    if fit_plx:
        # Always run EM mixture fit first
        plx, pmra, pmdec, eplx, epmra, epmdec, plx_inlier_mask, s_add_ra, s_add_dec, s_add_ra_by_mission, s_add_dec_by_mission, pos_ra_fit, pos_dec_fit, t0_ref_plx = robust_error_weighted_plxfit_with_rejection(
            data_df['measurement_epoch_yr'], data_df['rel_ra'], data_df['rel_dec'],
            data_df['ra_unc_mas'], data_df['dec_unc_mas'], ra_ref, dec_ref,
            inflate_errors=inflate_errors,
            mission_labels=data_df['mission'],
            per_mission_inflate=inflate_errors,
            seed_pmra=(float(pm_df.iloc[0]["pmra_masyr"]) if len(pm_df)!=0 and pd.notna(pm_df.iloc[0]["pmra_masyr"]) else None),
            seed_pmdec=(float(pm_df.iloc[0]["pmdec_masyr"]) if len(pm_df)!=0 and pd.notna(pm_df.iloc[0]["pmdec_masyr"]) else None),
            seed_plx=(float(plx_df.iloc[0]["parallax_mas"]) if len(plx_df)!=0 and pd.notna(plx_df.iloc[0]["parallax_mas"]) else None)
        )
        # Optional UltraNest refinement using EM inliers and inflated sigmas
        ultranest_flag = ""
        if use_ultranest and _ULTRANEST_AVAILABLE:
            ultranest_flag = " with UltraNest"
            _ultra_log_reset("UltraNest PM+PLX: starting")
            ultra_stream = _UltraStream()
            logger_ultra = logging.getLogger("ultranest")
            logger_root = logging.getLogger()
            handler_ultra = _UltraLogHandler()
            handler_root = _UltraLogHandler()
            prev_ultra_level = logger_ultra.level
            prev_root_level = logger_root.level
            try:
                handler_ultra.setLevel(logging.INFO)
                handler_root.setLevel(logging.INFO)
                logger_ultra.addHandler(handler_ultra)
                logger_root.addHandler(handler_root)
                logger_ultra.setLevel(logging.INFO)
                logger_root.setLevel(logging.INFO)
                with contextlib.redirect_stdout(ultra_stream), contextlib.redirect_stderr(ultra_stream):
                    try:
                        print(f"[UltraNest PM+PLX] BEFORE: EM reference epoch t0_ref_plx = {t0_ref_plx:.6f} yr")
                        print(f"[UltraNest PM+PLX] Seed params from EM: pmRA={pmra:.3f}, pmDEC={pmdec:.3f}, plx={plx:.3f}, posRA={pos_ra_fit:.3f}, posDEC={pos_dec_fit:.3f}")
                        plx, pmra, pmdec, eplx, epmra, epmdec, pos_ra_fit, pos_dec_fit, t0_ultra = _ultranest_refine_pm_plx(
                            data_df['measurement_epoch_yr'], data_df['rel_ra'], data_df['rel_dec'],
                            data_df['ra_unc_mas'], data_df['dec_unc_mas'], plx_inlier_mask,
                            ra_ref, dec_ref,
                            pmra, pmdec, plx, pos_ra_fit, pos_dec_fit,
                            s_add_ra=s_add_ra, s_add_dec=s_add_dec,
                            mission_labels=data_df['mission'],
                            s_add_ra_by_mission=s_add_ra_by_mission,
                            s_add_dec_by_mission=s_add_dec_by_mission,
                            t0_ref=t0_ref_plx,
                        )
                        print(f"[UltraNest PM+PLX] AFTER: UltraNest reference epoch t0_ultra = {t0_ultra:.6f} yr")
                    except Exception as e:
                        print("[Astrometric Explorer] UltraNest refinement failed (PM+PLX). Using EM results.", e)
            finally:
                try:
                    logger_ultra.removeHandler(handler_ultra)
                except Exception:
                    pass
                try:
                    logger_root.removeHandler(handler_root)
                except Exception:
                    pass
                try:
                    logger_ultra.setLevel(prev_ultra_level)
                except Exception:
                    pass
                try:
                    logger_root.setLevel(prev_root_level)
                except Exception:
                    pass
                _ultra_log_finish()
        # Ensure t0_ultra is defined even if UltraNest wasn't used
        t0_ultra = locals().get('t0_ultra', None)
        # Rebuild plx_df and pm_df
        plx_df = pd.DataFrame({
            "parallax_mas": [plx],
            "parallax_mas_unc": [eplx],
            "plx_ref": ["MOCAdb fit"+ultranest_flag]
        })
        # Rebuild pm_df
        pm_df = pd.DataFrame({
            "pmra_masyr": [pmra],
            "pmdec_masyr": [pmdec],
            "pmra_masyr_unc": [epmra],
            "pmdec_masyr_unc": [epmdec],
            "pm_ref": ["MOCAdb fit"+ultranest_flag]
        })
        # --- Recenter observed data to moving-component reference at epoch_ref ---
        # Shift observed data so that zero is the moving-component position at epoch_ref
        plxm_ref = parallax_motion(ra_ref, dec_ref, epoch_ref)
        if t0_ultra is not None:
            plxm_t0 = parallax_motion(ra_ref, dec_ref, t0_ultra)
            ra0_mov = (
                pm_df.iloc[0]["pmra_masyr"] * (epoch_ref - t0_ultra)
                + plx * (plxm_ref["plx_motion_racosdec"] - plxm_t0["plx_motion_racosdec"])
                + pos_ra_fit
            )
            dec0_mov = (
                pm_df.iloc[0]["pmdec_masyr"] * (epoch_ref - t0_ultra)
                + plx * (plxm_ref["plx_motion_dec"] - plxm_t0["plx_motion_dec"])
                + pos_dec_fit
            )
        else:
            # EM (non-UltraNest) intercepts are defined at t0_ref_plx (fit reference epoch)
            plxm_t0 = parallax_motion(ra_ref, dec_ref, t0_ref_plx)
            ra0_mov = (
                pm_df.iloc[0]["pmra_masyr"] * (epoch_ref - t0_ref_plx)
                + plx * (plxm_ref["plx_motion_racosdec"] - plxm_t0["plx_motion_racosdec"])
                + pos_ra_fit
            )
            dec0_mov = (
                pm_df.iloc[0]["pmdec_masyr"] * (epoch_ref - t0_ref_plx)
                + plx * (plxm_ref["plx_motion_dec"] - plxm_t0["plx_motion_dec"])
                + pos_dec_fit
            )
        data_df["rel_ra"] = data_df["rel_ra"] - ra0_mov
        data_df["rel_dec"] = data_df["rel_dec"] - dec0_mov

        fit_mode = "pm_plx"
        fit_ultranest = bool(use_ultranest and _ULTRANEST_AVAILABLE)
        fit_ra0_mov = float(ra0_mov) if np.isfinite(ra0_mov) else None
        fit_dec0_mov = float(dec0_mov) if np.isfinite(dec0_mov) else None
        fit_ra_unc_mas = _pick_unc(s_add_ra, data_df.get("ra_unc_mas", pd.Series(dtype=float)))
        fit_dec_unc_mas = _pick_unc(s_add_dec, data_df.get("dec_unc_mas", pd.Series(dtype=float)))

    if fit_pm and not fit_plx:
        # Always run EM mixture fit first
        (pmra, pmdec, epmra, epmdec,
         pm_inlier_mask,
         s_add_ra, s_add_dec,
         s_add_ra_by_mission, s_add_dec_by_mission,
         pos_ra_m, pos_dec_m, s_ra_stat, s_dec_stat,
         debug_pm_init) = robust_error_weighted_pmfit_with_rejection(
            data_df['measurement_epoch_yr'], data_df['rel_ra'], data_df['rel_dec'],
            data_df['ra_unc_mas'], data_df['dec_unc_mas'],
            inflate_errors=inflate_errors,
            mission_labels=data_df['mission'],
            per_mission_inflate=inflate_errors,
            seed_pmra=(float(pm_df.iloc[0]["pmra_masyr"]) if len(pm_df)!=0 and pd.notna(pm_df.iloc[0]["pmra_masyr"]) else None),
            seed_pmdec=(float(pm_df.iloc[0]["pmdec_masyr"]) if len(pm_df)!=0 and pd.notna(pm_df.iloc[0]["pmdec_masyr"]) else None)
        )
        # Optional UltraNest refinement on EM inliers
        t0_ref_em = float(np.nanmedian(data_df["measurement_epoch_yr"]))
        ultranest_flag = ""
        if use_ultranest and _ULTRANEST_AVAILABLE:
            ultranest_flag = " with UltraNest"
            _ultra_log_reset("UltraNest PM-only: starting")
            ultra_stream = _UltraStream()
            logger_ultra = logging.getLogger("ultranest")
            logger_root = logging.getLogger()
            handler_ultra = _UltraLogHandler()
            handler_root = _UltraLogHandler()
            prev_ultra_level = logger_ultra.level
            prev_root_level = logger_root.level
            try:
                handler_ultra.setLevel(logging.INFO)
                handler_root.setLevel(logging.INFO)
                logger_ultra.addHandler(handler_ultra)
                logger_root.addHandler(handler_root)
                logger_ultra.setLevel(logging.INFO)
                logger_root.setLevel(logging.INFO)
                with contextlib.redirect_stdout(ultra_stream), contextlib.redirect_stderr(ultra_stream):
                    try:
                        print(f"[UltraNest PM-only] BEFORE: EM reference epoch t0_ref_em = {t0_ref_em:.6f} yr")
                        print(f"[UltraNest PM-only] Seed params from EM: pmRA={pmra:.3f}, pmDEC={pmdec:.3f}, posRA={pos_ra_m:.3f}, posDEC={pos_dec_m:.3f}")
                        pmra, pmdec, epmra, epmdec, pos_ra_m, pos_dec_m = _ultranest_refine_pm_only(
                            data_df['measurement_epoch_yr'], data_df['rel_ra'], data_df['rel_dec'],
                            data_df['ra_unc_mas'], data_df['dec_unc_mas'], pm_inlier_mask,
                            pmra, pmdec, pos_ra_m, pos_dec_m,
                            s_add_ra=s_add_ra, s_add_dec=s_add_dec,
                            mission_labels=data_df['mission'],
                            s_add_ra_by_mission=s_add_ra_by_mission,
                            s_add_dec_by_mission=s_add_dec_by_mission,
                            t0_ref=t0_ref_em,
                        )
                        print(f"[UltraNest PM-only] AFTER: UltraNest reference epoch t0_ref (passed) = {t0_ref_em:.6f} yr")
                    except Exception as e:
                        print("[Astrometric Explorer] UltraNest refinement failed (PM-only). Using EM results.", e)
            finally:
                try:
                    logger_ultra.removeHandler(handler_ultra)
                except Exception:
                    pass
                try:
                    logger_root.removeHandler(handler_root)
                except Exception:
                    pass
                try:
                    logger_ultra.setLevel(prev_ultra_level)
                except Exception:
                    pass
                try:
                    logger_root.setLevel(prev_root_level)
                except Exception:
                    pass
                _ultra_log_finish()

        # For downstream display logic expecting per-axis masks, reuse the joint mask:
        pmra_inlier_mask = pm_inlier_mask
        pmdec_inlier_mask = pm_inlier_mask

        # Rebuild pm_df from joint fit
        pm_df = pd.DataFrame({
            "pmra_masyr": [pmra],
            "pmdec_masyr": [pmdec],
            "pmra_masyr_unc": [epmra],
            "pmdec_masyr_unc": [epmdec],
            "pm_ref": ["MOCAdb fit"+ultranest_flag]
        })
        
        def _fmt(x):
            return "N/A" if (x is None or (isinstance(x, float) and not np.isfinite(x))) else f"{x:.2f}"
        
        seed_lines = []
        for s in debug_pm_init.get("seeds", []):
            seed_lines.append(f"{s['method']}: pmRA={_fmt(s['pmra'])} mas/yr, pmDEC={_fmt(s['pmdec'])} mas/yr")
        chosen = debug_pm_init.get("chosen", "unknown")
        pm_init_text = "<br>".join(["<b>PM init seeds</b>"] + seed_lines + [f"<b>Chosen:</b> {chosen}"])
        
        print("[Astrometric Explorer] PM-only initialisation:")
        for line in seed_lines:
            print("  ", line)
        print("  Chosen:", chosen)
        # --- Recenter observed data to moving-component reference at epoch_ref using PM-only solution ---
        # Center observed data to moving-component reference at epoch_ref using PM-only solution
        t0_fit = float(np.nanmedian(data_df["measurement_epoch_yr"]))
        ra0_mov = pm_df.iloc[0]["pmra_masyr"] * (epoch_ref - t0_fit) + pos_ra_m
        dec0_mov = pm_df.iloc[0]["pmdec_masyr"] * (epoch_ref - t0_fit) + pos_dec_m
        data_df["rel_ra"] = data_df["rel_ra"] - ra0_mov
        data_df["rel_dec"] = data_df["rel_dec"] - dec0_mov

        fit_mode = "pm"
        fit_ultranest = bool(use_ultranest and _ULTRANEST_AVAILABLE)
        fit_ra0_mov = float(ra0_mov) if np.isfinite(ra0_mov) else None
        fit_dec0_mov = float(dec0_mov) if np.isfinite(dec0_mov) else None
        fit_ra_unc_mas = _pick_unc(s_add_ra, data_df.get("ra_unc_mas", pd.Series(dtype=float)))
        fit_dec_unc_mas = _pick_unc(s_add_dec, data_df.get("dec_unc_mas", pd.Series(dtype=float)))

    # Default additive error inflations (mas) if not set by fitting blocks
    if 's_add_ra' not in locals():
        s_add_ra = 0.0
    if 's_add_dec' not in locals():
        s_add_dec = 0.0
    if 's_add_ra_by_mission' not in locals():
        s_add_ra_by_mission = {}
    if 's_add_dec_by_mission' not in locals():
        s_add_dec_by_mission = {}

    # ---- Build inlier/outlier masks for display ----
    n_points = len(data_df)
    # Default masks: all inliers if not fitted
    if 'plx_inlier_mask' in locals():
        inliers_ra = np.array(plx_inlier_mask, dtype=bool)
        inliers_dec = np.array(plx_inlier_mask, dtype=bool)
    else:
        # PM-only may have separate masks
        if 'pmra_inlier_mask' in locals():
            inliers_ra = np.array(pmra_inlier_mask, dtype=bool)
        else:
            inliers_ra = np.ones(n_points, dtype=bool)
        if 'pmdec_inlier_mask' in locals():
            inliers_dec = np.array(pmdec_inlier_mask, dtype=bool)
        else:
            inliers_dec = np.ones(n_points, dtype=bool)

    # Attach flags to dataframe
    data_df['is_outlier_ra'] = ~inliers_ra
    data_df['is_outlier_dec'] = ~inliers_dec


    # Extract proper motion and parallax values
    # Extract proper motion and parallax values with errors
    if len(pm_df) != 0:
        pmra_display = format_value_with_error(pm_df.iloc[0]["pmra_masyr"], pm_df.iloc[0]["pmra_masyr_unc"], "mas/yr")
        pmdec_display = format_value_with_error(pm_df.iloc[0]["pmdec_masyr"], pm_df.iloc[0]["pmdec_masyr_unc"], "mas/yr")+" ("+pm_df["pm_ref"].fillna('No reference').str.replace(r'[()]', '', regex=True).iloc[0]+")"
    else:
        pmra_display, pmdec_display = "N/A", "N/A"

    if len(plx_df) != 0:
        parallax_display = format_value_with_error(plx_df.iloc[0]["parallax_mas"], plx_df.iloc[0]["parallax_mas_unc"], "mas")+" ("+plx_df["plx_ref"].fillna('No reference').str.replace(r'[()]', '', regex=True).iloc[0]+")"
    else:
        parallax_display = "N/A"

    pmra_val = float(pm_df.iloc[0]["pmra_masyr"]) if (len(pm_df) != 0 and pd.notna(pm_df.iloc[0]["pmra_masyr"])) else np.nan
    pmdec_val = float(pm_df.iloc[0]["pmdec_masyr"]) if (len(pm_df) != 0 and pd.notna(pm_df.iloc[0]["pmdec_masyr"])) else np.nan
    plx_val = float(plx_df.iloc[0]["parallax_mas"]) if (len(plx_df) != 0 and pd.notna(plx_df.iloc[0]["parallax_mas"])) else np.nan
    pmra_unc_val = float(pm_df.iloc[0]["pmra_masyr_unc"]) if (len(pm_df) != 0 and pd.notna(pm_df.iloc[0]["pmra_masyr_unc"])) else 0.0
    pmdec_unc_val = float(pm_df.iloc[0]["pmdec_masyr_unc"]) if (len(pm_df) != 0 and pd.notna(pm_df.iloc[0]["pmdec_masyr_unc"])) else 0.0
    plx_unc_val = float(plx_df.iloc[0]["parallax_mas_unc"]) if (len(plx_df) != 0 and pd.notna(plx_df.iloc[0]["parallax_mas_unc"])) else 0.0
    has_pm_vals = np.isfinite(pmra_val) and np.isfinite(pmdec_val)
    has_plx_val = np.isfinite(plx_val)
    plx_for_model = plx_val if has_plx_val else 0.0
    
    if adjust_reference_epoch and (not fit_plx) and (not fit_pm):
        epochs = data_df["measurement_epoch_yr"].values
        finite_epochs = epochs[np.isfinite(epochs)]
        if finite_epochs.size > 0:
            epoch_ref_candidate = float(np.nanmean(finite_epochs))
            if np.isfinite(epoch_ref_candidate):
                epoch_ref = epoch_ref_candidate
                rel_ra_observed = (data_df["ra"]) * np.cos(np.radians(data_df["dec"])) * 3600 * 1000
                rel_dec_observed = (data_df["dec"]) * 3600 * 1000

                if has_pm_vals:
                    rel_ra_observed -= (epochs - epoch_ref) * pmra_val
                    rel_dec_observed -= (epochs - epoch_ref) * pmdec_val

                if has_plx_val:
                    ra_vals = pd.to_numeric(data_df["ra"], errors='coerce').values
                    dec_vals = pd.to_numeric(data_df["dec"], errors='coerce').values
                    ra_finite = ra_vals[np.isfinite(ra_vals)]
                    dec_finite = dec_vals[np.isfinite(dec_vals)]
                    if ra_finite.size > 0 and dec_finite.size > 0:
                        plxm = parallax_motion(float(np.nanmean(ra_finite)), float(np.nanmean(dec_finite)), epochs)
                        rel_ra_observed -= plxm["plx_motion_racosdec"] * plx_for_model
                        rel_dec_observed -= plxm["plx_motion_dec"] * plx_for_model
                
                ra_ref_candidate = np.nanmedian(rel_ra_observed / (np.cos(np.radians(data_df["dec"])) * 3600 * 1000))
                dec_ref_candidate = np.nanmedian(rel_dec_observed / (3600 * 1000))
                if np.isfinite(ra_ref_candidate) and np.isfinite(dec_ref_candidate):
                    ra_ref = float(ra_ref_candidate)
                    dec_ref = float(dec_ref_candidate)
                    # Recalculate relative offsets
                    data_df["rel_ra"] = (data_df["ra"] - ra_ref) * np.cos(np.radians(dec_ref)) * 3600 * 1000
                    data_df["rel_dec"] = (data_df["dec"] - dec_ref) * 3600 * 1000

    # Subtract proper motion if checkbox is checked
    if subtract_pm and has_pm_vals:
        epochs = data_df["measurement_epoch_yr"].values

        data_df["rel_ra"] -= (epochs - epoch_ref) * pmra_val
        data_df["rel_dec"] -= (epochs - epoch_ref) * pmdec_val
    
    if subtract_plx:
        epochs = data_df["measurement_epoch_yr"].values
        plxm = parallax_motion(ra_ref, dec_ref, epochs)
        data_df["rel_ra"] -= plxm["plx_motion_racosdec"] * plx_for_model
        data_df["rel_dec"] -= plxm["plx_motion_dec"] * plx_for_model

    # If binning is enabled, compute bin indices now (grouping happens after we know outliers)
    if bin_activated:
        if phase_yearly:
            data_df["binned_time"] = (data_df["measurement_epoch_yr"] % 1 // (bin_size_days_phased/365.25)) * (bin_size_days_phased/365.25)
        else:
            data_df["binned_time"] = (data_df["measurement_epoch_yr"] * 365.25 // bin_size_days) * bin_size_days / 365.25

    # Build binned_df from NON-outliers only, using transformed data
    if bin_activated:
        non_outlier_mask = ~(data_df['is_outlier_ra'] | data_df['is_outlier_dec'])
        if 'binned_time' not in data_df.columns:
            if phase_yearly:
                data_df["binned_time"] = (data_df["measurement_epoch_yr"] % 1 // (bin_size_days_phased/365.25)) * (bin_size_days_phased/365.25)
            else:
                data_df["binned_time"] = (data_df["measurement_epoch_yr"] * 365.25 // bin_size_days) * bin_size_days / 365.25
        binned_df = (
            data_df[non_outlier_mask]
            .groupby("binned_time")
            .apply(weighted_combination)
            .dropna()
            .reset_index()
        )

    # Assign a unique color to each mission
    unique_missions = data_df['mission'].unique()
    mission_color_map = {mission: i for i, mission in enumerate(unique_missions)}
    data_df["mission_color"] = data_df["mission"].map(mission_color_map)

    # Handle selection propagation
    if triggered_prop == "astrometry-plot-ra.selectedData" and selectedData_ra:
        selected_indices = [point["pointIndex"] for point in selectedData_ra["points"]]
    elif triggered_prop == "astrometry-plot-dec.selectedData" and selectedData_dec:
        selected_indices = [point["pointIndex"] for point in selectedData_dec["points"]]
    else:
        selected_indices = list(data_df.index)

    fig_ra = go.Figure()
    fig_dec = go.Figure()

    if phase_yearly:
        data_df["x_values"] = np.mod(data_df["measurement_epoch_yr"], 1)  # Phase yearly
        xaxis_title = "Yearly Phase (0 = Jan 1st, 1 = Dec 31st)"
    else:
        data_df["x_values"] = data_df["measurement_epoch_yr"]  # Original epochs
        xaxis_title = "Epoch (Year)"  # Default x-axis title

    #Plot the proper motion
    # Extract the full x-axis range from the figure (start and end)
    #xaxis_range = [data_df["measurement_epoch_yr"].min(), data_df["measurement_epoch_yr"].max()]
    data_min = data_df["x_values"].min()
    data_max = data_df["x_values"].max()

    # Add 5% padding
    padding = (data_max - data_min) * 0.05
    xaxis_range = [data_min - padding, data_max + padding]

    # Generate 5000 evenly spaced points across the x-axis range
    ntimep = 5000
    time_values = np.linspace(xaxis_range[0], xaxis_range[1], ntimep)

    # Build model using best-fitting moving-component reference when available
    # Absolute time values for modeling (phase uses wrapped x but absolute calendar year for PM/PLX terms)
    if phase_yearly:
        epochs_for_phase = pd.to_numeric(data_df["measurement_epoch_yr"], errors='coerce').values
        finite_epochs_phase = epochs_for_phase[np.isfinite(epochs_for_phase)]
        epoch_phase_center = float(np.nanmean(finite_epochs_phase)) if finite_epochs_phase.size > 0 else 0.0
        t_abs = time_values + np.round(epoch_phase_center)
    else:
        t_abs = time_values

    if fit_plx:
        # Anchor model to epoch_ref and then optionally subtract PM/PLX exactly like the data
        plxm_model = parallax_motion(ra_ref, dec_ref, t_abs)
        plxm_ref   = parallax_motion(ra_ref, dec_ref, epoch_ref)
        # Base anchored components
        pm_ra_term  = (pmra_val * (t_abs - epoch_ref)) if has_pm_vals else np.zeros_like(time_values)
        pm_dec_term = (pmdec_val * (t_abs - epoch_ref)) if has_pm_vals else np.zeros_like(time_values)
        # Parallax term (array); if not available, zero array with correct shape
        plx_ra_term = plx_for_model * (plxm_model["plx_motion_racosdec"] - plxm_ref["plx_motion_racosdec"])
        plx_dec_term = plx_for_model * (plxm_model["plx_motion_dec"] - plxm_ref["plx_motion_dec"])
        # Apply the same subtractions as done to the data (preserve array shapes)
        if subtract_pm:
            pm_ra_term = np.zeros_like(time_values)
            pm_dec_term = np.zeros_like(time_values)
        if subtract_plx:
            plx_ra_term = np.zeros_like(time_values)
            plx_dec_term = np.zeros_like(time_values)
        expected_rel_ra = pm_ra_term + plx_ra_term
        expected_rel_dec = pm_dec_term + plx_dec_term
    elif fit_pm:
        # PM-only anchored to epoch_ref; optionally add DB parallax as differential
        pm_ra_term  = (pmra_val * (t_abs - epoch_ref)) if has_pm_vals else np.zeros_like(time_values)
        pm_dec_term = (pmdec_val * (t_abs - epoch_ref)) if has_pm_vals else np.zeros_like(time_values)
        if subtract_pm:
            pm_ra_term = np.zeros_like(time_values)
            pm_dec_term = np.zeros_like(time_values)
        expected_rel_ra = pm_ra_term
        expected_rel_dec = pm_dec_term
        if not subtract_plx:
            plxm_model = parallax_motion(ra_ref, dec_ref, t_abs)
            plxm_ref   = parallax_motion(ra_ref, dec_ref, epoch_ref)
            expected_rel_ra += (plxm_model["plx_motion_racosdec"] - plxm_ref["plx_motion_racosdec"]) * plx_for_model
            expected_rel_dec += (plxm_model["plx_motion_dec"] - plxm_ref["plx_motion_dec"]) * plx_for_model
    else:
        # No fresh fit: fall back to MOCAdb solution relative to the chosen reference epoch
        if subtract_pm or (not has_pm_vals):
            expected_rel_ra = np.zeros_like(time_values)
            expected_rel_dec = np.zeros_like(time_values)
        else:
            expected_rel_ra = (t_abs - epoch_ref) * pmra_val
            expected_rel_dec = (t_abs - epoch_ref) * pmdec_val
        # Add parallax term if not subtracted (even when PM is subtracted)
        if not subtract_plx:
            plxm_model = parallax_motion(ra_ref, dec_ref, t_abs)
            expected_rel_ra += plxm_model["plx_motion_racosdec"] * plx_for_model
            expected_rel_dec += plxm_model["plx_motion_dec"] * plx_for_model

    # === Compute 1-sigma model envelopes from parameter uncertainties ===
    # Pull uncertainties (0 if missing); zero them if subtract_pm
    pmra_unc = 0.0 if subtract_pm else pmra_unc_val
    pmdec_unc = 0.0 if subtract_pm else pmdec_unc_val
    plx_unc  = plx_unc_val

    # Time factor for PM contribution; zero if subtract_pm
    if phase_yearly:
        dt_vals = (time_values + np.round(epoch_phase_center) - epoch_ref)
    else:
        dt_vals = (time_values - epoch_ref)
    if subtract_pm:
        dt_vals = np.zeros_like(dt_vals)

    # Parallax motion terms for the envelope (zeroed if subtract_plx or no parallax)
    if not subtract_plx:
        plxm_env = parallax_motion(ra_ref, dec_ref, t_abs)
        plx_ra_term = plxm_env["plx_motion_racosdec"]
        plx_dec_term = plxm_env["plx_motion_dec"]
    else:
        plx_ra_term = np.zeros_like(time_values)
        plx_dec_term = np.zeros_like(time_values)

    # 1-sigma envelopes (independent errors, no covariance)
    sigma_model_ra = np.sqrt((dt_vals * pmra_unc)**2 + (plx_ra_term * plx_unc)**2)
    sigma_model_dec = np.sqrt((dt_vals * pmdec_unc)**2 + (plx_dec_term * plx_unc)**2)

    ra_envelope_upper = expected_rel_ra + sigma_model_ra
    ra_envelope_lower = expected_rel_ra - sigma_model_ra
    dec_envelope_upper = expected_rel_dec + sigma_model_dec
    dec_envelope_lower = expected_rel_dec - sigma_model_dec

    # Add line to RA figure
    fig_ra.add_trace(go.Scatter(
        x=time_values,
        y=expected_rel_ra,
        mode="lines",
        line=dict(color='rgba(100, 150, 250, 0.6)', width=4),  # Semi-transparent gray line
        name="MOCAdb solution",
        hoverinfo='skip'
    ))
    # Shaded 1-sigma band around RA model
    fig_ra.add_trace(go.Scatter(
        x=time_values,
        y=ra_envelope_lower,
        mode="lines",
        line=dict(width=0),
        hoverinfo='skip',
        showlegend=False,
        name="Model −1σ"
    ))
    fig_ra.add_trace(go.Scatter(
        x=time_values,
        y=ra_envelope_upper,
        mode="lines",
        line=dict(width=0),
        fill='tonexty',
        fillcolor='rgba(100, 150, 250, 0.15)',
        hoverinfo='skip',
        showlegend=True,
        name="Model ±1σ"
    ))

    # Add line to DEC figure
    fig_dec.add_trace(go.Scatter(
        x=time_values,
        y=expected_rel_dec,
        mode="lines",
        line=dict(color='rgba(100, 150, 250, 0.6)', width=4),  # Semi-transparent gray line
        name="MOCAdb solution",
        hoverinfo='skip'
    ))
    # Shaded 1-sigma band around DEC model
    fig_dec.add_trace(go.Scatter(
        x=time_values,
        y=dec_envelope_lower,
        mode="lines",
        line=dict(width=0),
        hoverinfo='skip',
        showlegend=False,
        name="Model −1σ"
    ))
    fig_dec.add_trace(go.Scatter(
        x=time_values,
        y=dec_envelope_upper,
        mode="lines",
        line=dict(width=0),
        fill='tonexty',
        fillcolor='rgba(100, 150, 250, 0.15)',
        hoverinfo='skip',
        showlegend=False,
        name="Model ±1σ"
    ))

    data_df['rel_ra_str'] = data_df['rel_ra'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['rel_dec_str'] = data_df['rel_dec'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['ra_unc_mas_str'] = data_df['ra_unc_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['dec_unc_mas_str'] = data_df['dec_unc_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['ra_str'] = data_df['ra'].apply(lambda x: f"{x:.6f}" if pd.notna(x) else "N/A")
    data_df['dec_str'] = data_df['dec'].apply(lambda x: f"{x:.6f}" if pd.notna(x) else "N/A")
    data_df['measurement_epoch_yr_str'] = data_df['measurement_epoch_yr'].apply(lambda x: f"{x:.4f}" if pd.notna(x) else "N/A")
    data_df['id_str'] = data_df['id'].apply(lambda x: f"{int(x):d}" if pd.notna(x) else "N/A")
    data_df['airmass_str'] = data_df['airmass'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['delta_ra_str'] = data_df['calibration_delta_ra_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['delta_dec_str'] = data_df['calibration_delta_dec_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['nstars_str'] = data_df['nstars_calibration'].apply(lambda x: f"{int(x):d}" if pd.notna(x) else "N/A")

    if bin_activated:
        binned_df['rel_ra_str'] = binned_df['rel_ra'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        binned_df['rel_dec_str'] = binned_df['rel_dec'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        binned_df['ra_unc_mas_str'] = binned_df['ra_unc_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        binned_df['dec_unc_mas_str'] = binned_df['dec_unc_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")

    # Outlier legend flag for RA
    outlier_legend_added = False

    for mission in unique_missions:
        
        mission_data = data_df[data_df["mission"] == mission]
        opacity = 0.3 if bin_activated else 1.0  # Semi-transparent if binning is active

        fig_ra.add_trace(go.Scatter(
            x=mission_data["x_values"],
            y=mission_data["rel_ra"],
            mode='markers',
            error_y=dict(
                type='data',
                array=mission_data['ra_unc_mas'],
                visible=True,
                color='rgba(0, 0, 0, 0.2)',
                thickness=1.5,
                width=2
            ),
            marker=dict(
                color=mission_color_map[mission],  # Use the assigned color for this mission
                size=8,
                symbol='circle',
                opacity=opacity,
                line=dict(width=2, color='black')
            ),
            name=(mission + (f"  (σ_add={s_add_ra_by_mission.get(mission, 0.0):.2f} mas)" if inflate_errors and s_add_ra_by_mission.get(mission, 0.0) > 0 else "")),
            customdata=mission_data['id'],
            text=[
                (
                    f"<b>ID:</b> {row['id_str']}<br>"
                    f"<b>Mission:</b> {row['mission'] or 'N/A'}<br>"
                    f"<b>Reference:</b> {row['moca_pid'] or 'N/A'}<br>"
                    f"<b>Epoch:</b> {row['measurement_epoch_yr_str']} yr<br>"
                    f"<b>Relative R.A.:</b> {row['rel_ra_str']} ± {row['ra_unc_mas_str']} mas<br>"
                    f"<b>Relative Decl.:</b> {row['rel_dec_str']} ± {row['dec_unc_mas_str']} mas<br>"
                    f"<b>RA:</b> {row['ra_str']} deg<br>"
                    f"<b>DEC:</b> {row['dec_str']} deg<br>"
                    f"<b>Origin:</b> {row['origin'] or 'N/A'}<br>"
                    f"<b>Airmass:</b> {row['airmass_str']}<br>"
                    f"<b>Bandpass:</b> {row['moca_psid'] or 'N/A'}<br>"
                    f"<b>Calibration offset R.A.:</b> {row['delta_ra_str']} mas<br>"
                    f"<b>Calibration offset Decl.:</b> {row['delta_dec_str']} mas<br>"
                    f"<b>Calibration Nstars:</b> {row['nstars_str']}<br>"
                    f"<b>Calibration method:</b> {row['calibration_method'] or 'N/A'}<br>"
                    + ("<b>Flagged:</b> Outlier<br>" if row['is_outlier_ra'] else "")
                    + f"<b>Comments:</b> {wrap_text(row['comments'] or '', width=50)}"
                )
                for _, row in mission_data.iterrows()
            ],
            hoverinfo='text'
        ))

        # Overlay red X markers for RA outliers (non-inliers)
        out_ra = mission_data[mission_data['is_outlier_ra']]
        if not out_ra.empty:
            fig_ra.add_trace(go.Scatter(
                x=out_ra["x_values"],
                y=out_ra["rel_ra"],
                mode='markers',
                marker=dict(symbol='x-thin', size=14, color='red', line=dict(width=1, color='red')),
                showlegend=not outlier_legend_added,
                name='Flagged outliers',
                legendgroup='outliers',
                hoverinfo='skip'
            ))
            outlier_legend_added = True

    # Plot binned data points (black)
    if bin_activated:
        fig_ra.add_trace(go.Scatter(
            x=binned_df["binned_time"],
            y=binned_df["rel_ra"],
            error_y=dict(
                type='data',
                array=binned_df['ra_unc_mas'],
                visible=True,
                color='rgba(0, 0, 0, 0.2)',  
                thickness=1.5,               
                width=2                  
            ),
            mode="markers",
            marker=dict(
                size=10,
                color="white",
                symbol="circle",
                line=dict(width=3, color='black')
            ),
            name="Binned Data",
            hoverinfo="text",
            text=binned_df.apply(
                lambda row: 
                    f"<b>Epoch:</b> {row['binned_time']} yr<br>" \
                    f"<b>Relative R.A.:</b> {row['rel_ra_str']} ± {row['ra_unc_mas_str']} mas<br>" \
                    f"<b>Relative Decl.:</b> {row['rel_dec_str']} ± {row['dec_unc_mas_str']} mas<br>" \
                    f"<b>N Data:</b> {int(row['ndata'])}<br>" \
                    ,
                axis=1
            ),
        ))

    # Update layout for better legend positioning
    fig_ra.update_layout(
        plot_bgcolor='white',
        xaxis_title=xaxis_title, yaxis_title="RA Offset (mas)",
        xaxis=dict(
            range=xaxis_range,  # Use the manually defined range
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        yaxis=dict(
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        margin=dict(l=40, r=40, t=60, b=40),
        paper_bgcolor='white',
        showlegend=True,
        legend=dict(
             title=dict(
                text="<b> Missions</b>",  # Make the title bold
                font=dict(size=14)  # Optional: adjust font size
            ),
            #x=0.02, y=0.98,  # Adjust legend position as needed
            bgcolor='rgba(255, 255, 255, 0.5)',  # Optional: semi-transparent background
            bordercolor='black',
            borderwidth=2,
            groupclick='togglegroup',
        ),
        annotations=[
            dict(
                xref="paper", yref="paper",
                x=0.5, y=1.12,  # Position above the graph
                text=(f"<b>PMRA:</b> {pmra_display} | <b>PMDEC:</b> {pmdec_display} | <b>Parallax:</b> {parallax_display}"),
                showarrow=False,
                font=dict(size=14, color="black"),
                align="center"
            ),
            # dict(
            #     xref="paper", yref="paper",
            #     x=0.01, y=0.97,
            #     text=pm_init_text if ('pm_init_text' in locals()) else "",
            #     showarrow=False,
            #     align="left",
            #     font=dict(size=12, color="black"),
            #     bgcolor="rgba(255,255,255,0.7)",
            #     bordercolor="black",
            #     borderwidth=1
            # )
        ]
    )

    # Outlier legend flag for DEC
    outlier_legend_added = False

    for mission in unique_missions:
        
        mission_data = data_df[data_df["mission"] == mission]
        opacity = 0.3 if bin_activated else 1.0  # Semi-transparent if binning is active

        fig_dec.add_trace(go.Scatter(
            x=mission_data["x_values"],
            y=mission_data["rel_dec"],
            mode='markers',
            error_y=dict(
                type='data',
                array=mission_data['dec_unc_mas'],
                visible=True,
                color='rgba(0, 0, 0, 0.2)',
                thickness=1.5,
                width=2
            ),
            marker=dict(
                color=mission_color_map[mission],  # Use the assigned color for this mission
                size=8,
                symbol='circle',
                opacity=opacity,
                line=dict(width=2, color='black')
            ),
            name=(mission + (f"  (σ_add={s_add_dec_by_mission.get(mission, 0.0):.2f} mas)" if inflate_errors and s_add_dec_by_mission.get(mission, 0.0) > 0 else "")),
            customdata=mission_data['id'],
            text=[
                (
                    f"<b>ID:</b> {row['id_str']}<br>"
                    f"<b>Mission:</b> {row['mission'] or 'N/A'}<br>"
                    f"<b>Relative R.A.:</b> {row['rel_ra_str']} ± {row['ra_unc_mas_str']} mas<br>"
                    f"<b>Relative Decl.:</b> {row['rel_dec_str']} ± {row['dec_unc_mas_str']} mas<br>"
                    f"<b>RA:</b> {row['ra_str']} deg<br>"
                    f"<b>DEC:</b> {row['dec_str']} deg<br>"
                    f"<b>Epoch:</b> {row['measurement_epoch_yr_str']} yr<br>"
                    f"<b>Reference:</b> {row['moca_pid'] or 'N/A'}<br>"
                    f"<b>Origin:</b> {row['origin'] or 'N/A'}<br>"
                    f"<b>Airmass:</b> {row['airmass_str']}<br>"
                    f"<b>Bandpass:</b> {row['moca_psid'] or 'N/A'}<br>"
                    + ("<b>Flagged:</b> Outlier<br>" if row['is_outlier_dec'] else "")
                    + f"<b>Comments:</b> {wrap_text(row['comments'] or '', width=50)}"
                )
                for _, row in mission_data.iterrows()
            ],
            hoverinfo='text'
        ))

        # Overlay red X markers for DEC outliers (non-inliers)
        out_dec = mission_data[mission_data['is_outlier_dec']]
        if not out_dec.empty:
            fig_dec.add_trace(go.Scatter(
                x=out_dec["x_values"],
                y=out_dec["rel_dec"],
                mode='markers',
                marker=dict(symbol='x-thin', size=14, color='red', line=dict(width=1, color='red')),
                showlegend=not outlier_legend_added,
                name='Flagged outliers',
                legendgroup='outliers',
                hoverinfo='skip'
            ))
            outlier_legend_added = True

    if bin_activated:
        fig_dec.add_trace(go.Scatter(
            x=binned_df["binned_time"],
            y=binned_df["rel_dec"],
            error_y=dict(
                type='data',
                array=binned_df['ra_unc_mas'],
                visible=True,
                color='rgba(0, 0, 0, 0.2)',  
                thickness=1.5,               
                width=2                  
            ),
            mode="markers",
            marker=dict(
                size=10,
                color="white",
                symbol="circle",
                line=dict(width=3, color='black')
            ),
            name="Binned Data",
            hoverinfo="text",
            text=binned_df.apply(
                lambda row: 
                    f"<b>Epoch:</b> {row['binned_time']} yr<br>" \
                    f"<b>Relative R.A.:</b> {row['rel_ra_str']} ± {row['ra_unc_mas_str']} mas<br>" \
                    f"<b>Relative Decl.:</b> {row['rel_dec_str']} ± {row['dec_unc_mas_str']} mas<br>" \
                    f"<b>N Data:</b> {int(row['ndata'])}<br>" \
                    ,
                axis=1
            ),
        ))
    
    # Update layout for better legend positioning
    fig_dec.update_layout(
        plot_bgcolor='white',
        xaxis_title=xaxis_title, yaxis_title="DEC Offset (mas)",
        xaxis=dict(
            range=xaxis_range,  # Use the manually defined range
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        yaxis=dict(
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        margin=dict(l=40, r=40, t=60, b=40),
        paper_bgcolor='white',
        showlegend=True,
        legend=dict(
             title=dict(
                text="<b> Missions</b>",  # Make the title bold
                font=dict(size=14)  # Optional: adjust font size
            ),
            #x=0.02, y=0.98,  # Adjust legend position as needed
            bgcolor='rgba(255, 255, 255, 0.5)',  # Optional: semi-transparent background
            bordercolor='black',
            borderwidth=2,
            groupclick='togglegroup',
        )
    )
    
    date_str = datetime.now().strftime("%y%m%d")

    config_ra = {'toImageButtonOptions': figure_export_config['toImageButtonOptions'].copy()}
    config_ra['toImageButtonOptions']['filename'] = (
        f"astrometry_global_chi2_ra_mocaoid_{int(moca_oid)}_{date_str}"
    )

    config_dec = {'toImageButtonOptions': figure_export_config['toImageButtonOptions'].copy()}
    config_dec['toImageButtonOptions']['filename'] = (
        f"astrometry_global_chi2_dec_mocaoid_{int(moca_oid)}_{date_str}"
    )

    # Package fit payload for management push (if available)
    def _to_float_or_none(val):
        try:
            if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
                return None
            return float(val)
        except Exception:
            return None

    if fit_mode in ("pm", "pm_plx"):
        fit_payload = {
            "moca_oid": int(moca_oid),
            "fit_mode": fit_mode,
            "fit_ultranest": bool(fit_ultranest),
            "pmra_masyr": _to_float_or_none(pm_df.iloc[0]["pmra_masyr"]) if len(pm_df) else None,
            "pmdec_masyr": _to_float_or_none(pm_df.iloc[0]["pmdec_masyr"]) if len(pm_df) else None,
            "pmra_masyr_unc": _to_float_or_none(pm_df.iloc[0]["pmra_masyr_unc"]) if len(pm_df) else None,
            "pmdec_masyr_unc": _to_float_or_none(pm_df.iloc[0]["pmdec_masyr_unc"]) if len(pm_df) else None,
            "plx_mas": _to_float_or_none(plx_df.iloc[0]["parallax_mas"]) if (fit_mode == "pm_plx" and len(plx_df)) else None,
            "plx_mas_unc": _to_float_or_none(plx_df.iloc[0]["parallax_mas_unc"]) if (fit_mode == "pm_plx" and len(plx_df)) else None,
            "ra_ref_deg": _to_float_or_none(ra_ref),
            "dec_ref_deg": _to_float_or_none(dec_ref),
            "epoch_ref": _to_float_or_none(fit_epoch_ref),
            "ra0_mov_mas": _to_float_or_none(fit_ra0_mov),
            "dec0_mov_mas": _to_float_or_none(fit_dec0_mov),
            "ra_unc_mas": _to_float_or_none(fit_ra_unc_mas),
            "dec_unc_mas": _to_float_or_none(fit_dec_unc_mas),
            "selected_missions": selected_missions or [],
        }

    return fig_ra, config_ra, fig_dec, config_dec, fit_payload

# =============================================================================
# UltraNest log polling
# =============================================================================
@dash.callback(
    Output("astrometry-ultranest-output", "children"),
    Output("astrometry-ultranest-output", "style"),
    Input("astrometry-ultranest-interval", "n_intervals"),
    State("fit-ultranest-checkbox", "value"),
)
def _poll_ultranest_output(n_intervals, ultranest_values):
    style = {'display': 'none', 'marginTop': '10px', 'fontSize': '11px', 'whiteSpace': 'pre-wrap'}
    if not ultranest_values or 'ultranest' not in ultranest_values:
        return "", style

    style = {'display': 'block', 'marginTop': '10px', 'fontSize': '11px', 'whiteSpace': 'pre-wrap'}
    if not _ULTRANEST_AVAILABLE:
        return "UltraNest output: unavailable (package not installed)", style

    _token, running, lines = _ultra_log_snapshot()
    if lines:
        text = "\n".join(lines[-12:])
    else:
        text = "UltraNest output: (none yet)"
    if running:
        text = text + "\n[UltraNest running...]"
    return text, style

# =============================================================================
# Management-only push of PM / PM+PLX fits to the database
# =============================================================================
@dash.callback(
    Output("astrometry-push-pm", "style"),
    Output("astrometry-push-pmplx", "style"),
    Output("astrometry-push-output", "style"),
    Output("astrometry-push-pm", "disabled"),
    Output("astrometry-push-pmplx", "disabled"),
    Output("astrometry-push-pm", "children"),
    Output("astrometry-push-pmplx", "children"),
    Input("url", "search"),
    Input("astrometry-fit-store", "data"),
)
def _toggle_astrometry_push_controls(url_search, fit_data):
    base_btn = {'fontSize': '12px', 'border': '3px solid black', 'verticalAlign': 'middle', 'marginRight': '12px'}
    base_btn2 = {'fontSize': '12px', 'border': '3px solid black', 'verticalAlign': 'middle'}
    style_out = {'marginTop': '10px'}
    try:
        parsed = parse_qs((url_search or "").lstrip("?"))
        env_username = os.environ.get('MOCA_USERNAME', '')
        username_param = (parsed.get('user', [env_username])[0] or '').strip().lower()
    except Exception:
        username_param = (os.environ.get('MOCA_USERNAME', '') or '').strip().lower()

    if username_param != 'management':
        base_btn['display'] = 'none'
        base_btn2['display'] = 'none'
        style_out['display'] = 'none'
        return base_btn, base_btn2, style_out, True, True, "Push PM fit", "Push PM+PLX fit"

    fit_mode = (fit_data or {}).get("fit_mode")
    fit_ultranest = bool((fit_data or {}).get("fit_ultranest"))
    suffix = " (ultranest)" if fit_ultranest else " (no ultranest)"
    pm_label = f"Push PM fit{suffix}"
    pmplx_label = f"Push PM+PLX fit{suffix}"
    style_btn = dict(base_btn)
    style_btn2 = dict(base_btn2)
    pm_disabled = True
    pmplx_disabled = True
    if fit_mode != "pm":
        style_btn.update({'opacity': 0.5, 'pointerEvents': 'none'})
        pm_disabled = True
    else:
        pm_disabled = False
    if fit_mode != "pm_plx":
        style_btn2.update({'opacity': 0.5, 'pointerEvents': 'none'})
        pmplx_disabled = True
    else:
        pmplx_disabled = False
    return style_btn, style_btn2, style_out, pm_disabled, pmplx_disabled, pm_label, pmplx_label


@dash.callback(
    Output("astrometry-push-output", "children"),
    Input("astrometry-push-pm", "n_clicks"),
    Input("astrometry-push-pmplx", "n_clicks"),
    State("astrometry-fit-store", "data"),
    State("url", "search"),
    prevent_initial_call=True
)
def push_astrometry_fit(n_clicks_pm, n_clicks_pmplx, fit_data, url_search):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update

    try:
        parsed = parse_qs((url_search or "").lstrip("?"))
        env_username = os.environ.get('MOCA_USERNAME', '')
        username_param = (parsed.get('user', [env_username])[0] or '').strip().lower()
    except Exception:
        username_param = (os.environ.get('MOCA_USERNAME', '') or '').strip().lower()

    if username_param != 'management':
        return "Not authorized."

    if not fit_data:
        return "No fit results available. Run a PM or PM+PLX fit first."

    triggered = ctx.triggered[0]["prop_id"].split(".")[0]
    if triggered == "astrometry-push-pm" and fit_data.get("fit_mode") != "pm":
        return "Current fit is not PM-only."
    if triggered == "astrometry-push-pmplx" and fit_data.get("fit_mode") != "pm_plx":
        return "Current fit is not PM+PLX."

    def _num(val):
        try:
            if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
                return None
            return float(val)
        except Exception:
            return None

    def _parse_mission(label):
        if not label or label.strip().lower() == "no mission":
            return None, None
        parts = str(label).strip().split()
        if len(parts) >= 2:
            return " ".join(parts[:-1]), parts[-1]
        return parts[0], None

    selected_missions = fit_data.get("selected_missions") or []
    mission_name = None
    data_release = ""
    if len(selected_missions) == 1:
        mission_name, data_release = _parse_mission(selected_missions[0])
        if data_release is None:
            data_release = ""

    fit_mode = fit_data.get("fit_mode")
    fit_ultranest = bool(fit_data.get("fit_ultranest"))
    origin_base = "mocaviz_astrometry_pm_fit" if fit_mode == "pm" else "mocaviz_astrometry_pm_plx_fit"
    calc_method = "mocaviz_pm_fit" if fit_mode == "pm" else "mocaviz_pm_plx_fit"
    if fit_ultranest:
        origin_base = origin_base + "_ultranest"
        calc_method = calc_method + "_ultranest"
    comments = f"{origin_base} (management push)"

    moca_oid = int(fit_data.get("moca_oid"))
    pmra = _num(fit_data.get("pmra_masyr"))
    pmdec = _num(fit_data.get("pmdec_masyr"))
    pmra_unc = _num(fit_data.get("pmra_masyr_unc"))
    pmdec_unc = _num(fit_data.get("pmdec_masyr_unc"))
    plx = _num(fit_data.get("plx_mas"))
    plx_unc = _num(fit_data.get("plx_mas_unc"))
    ra_ref = _num(fit_data.get("ra_ref_deg"))
    dec_ref = _num(fit_data.get("dec_ref_deg"))
    epoch_ref = _num(fit_data.get("epoch_ref"))
    ra0_mov = _num(fit_data.get("ra0_mov_mas"))
    dec0_mov = _num(fit_data.get("dec0_mov_mas"))
    ra_unc_mas = _num(fit_data.get("ra_unc_mas"))
    dec_unc_mas = _num(fit_data.get("dec_unc_mas"))

    if any(v is None for v in [ra_ref, dec_ref, epoch_ref, ra0_mov, dec0_mov, pmra, pmdec]):
        return "Fit payload missing required values."

    cos_dec = np.cos(np.radians(dec_ref))
    ra_fit = ra_ref + (ra0_mov / (cos_dec * 3600.0 * 1000.0))
    dec_fit = dec_ref + (dec0_mov / (3600.0 * 1000.0))

    pm_corrected = 1
    plx_corrected = 1 if fit_mode == "pm_plx" else 0

    pm_params = {
        "moca_oid": moca_oid,
        "pmra": pmra,
        "pmdec": pmdec,
        "pmra_unc": pmra_unc,
        "pmdec_unc": pmdec_unc,
        "mission_name": mission_name,
        "data_release": data_release,
        "origin": origin_base,
        "comments": comments,
        "rls": "gagne",
        "calc_method": calc_method
    }
    plx_params = {
        "moca_oid": moca_oid,
        "plx": plx,
        "plx_unc": plx_unc,
        "mission_name": mission_name,
        "data_release": data_release,
        "origin": origin_base,
        "comments": comments,
        "rls": "gagne"
    }
    eq_params = {
        "moca_oid": moca_oid,
        "ra": ra_fit,
        "dec": dec_fit,
        "ra_unc": ra_unc_mas,
        "dec_unc": dec_unc_mas,
        "epoch": epoch_ref,
        "epoch_unc": 0.0,
        "frame_equinox": "J2000",
        "coord_frame": "ICRS",
        "mission_name": mission_name,
        "data_release": data_release,
        "origin": origin_base,
        "pm_corrected": pm_corrected,
        "plx_corrected": plx_corrected,
        "point_of_view": "earth",
        "comments": comments,
        "rls": "gagne"
    }

    dry_run_push = False
    if dry_run_push:
        import sys
        sys.stderr.write("[astrometry:push] DRY RUN enabled. SQL statements and params:\n")
        sys.stderr.write("PM SQL:\n")
        sys.stderr.write("""
            INSERT INTO data_proper_motions
            (moca_oid, moca_pid, pmra_masyr, pmdec_masyr, pmra_masyr_unc, pmdec_masyr_unc,
             mission_name, data_release, origin, ignored, adopt_asis, adopted, is_public,
             public_adopt_asis, public_adopted, comments, rls, calculation_method)
            VALUES
            (:moca_oid, NULL, :pmra, :pmdec, :pmra_unc, :pmdec_unc,
             :mission_name, :data_release, :origin, 0, 0, 0, 0,
             0, 0, :comments, :rls, :calc_method)
        """)
        sys.stderr.write(f"PM params: {pm_params}\n")
        if fit_mode == "pm_plx":
            sys.stderr.write("PLX SQL:\n")
            sys.stderr.write("""
                INSERT INTO data_parallaxes
                (moca_oid, moca_pid, parallax_mas, parallax_mas_unc,
                 mission_name, data_release, origin, ignored, adopt_asis, adopted, is_public,
                 public_adopt_asis, public_adopted, comments, rls)
                VALUES
                (:moca_oid, NULL, :plx, :plx_unc,
                 :mission_name, :data_release, :origin, 0, 0, 0, 0,
                 0, 0, :comments, :rls)
            """)
            sys.stderr.write(f"PLX params: {plx_params}\n")
        sys.stderr.write("EQ SQL:\n")
        sys.stderr.write("""
            INSERT INTO data_equatorial_coordinates
            (moca_oid, moca_pid, ra, `dec`, ra_unc_mas, dec_unc_mas,
             measurement_epoch_yr, measurement_epoch_yr_unc, frame_equinox, coord_frame,
             mission_name, data_release, origin, ignored, adopt_asis, is_public,
             public_adopt_asis, adopt_as_reference, public_adopt_as_reference, single_epoch,
             pm_corrected, plx_corrected, point_of_view, comments, rls)
            VALUES
            (:moca_oid, NULL, :ra, :dec, :ra_unc, :dec_unc,
             :epoch, :epoch_unc, :frame_equinox, :coord_frame,
             :mission_name, :data_release, :origin, 0, 0, 0,
             0, 0, 0, 0,
             :pm_corrected, :plx_corrected, :point_of_view, :comments, :rls)
        """)
        sys.stderr.write(f"EQ params: {eq_params}\n")
        sys.stderr.flush()
        return "DRY RUN: SQL printed to server log."

    engine = get_engine_from_url(url_search)
    conn = engine.connect()
    try:
        # Insert PM
        pm_sql = text("""
            INSERT INTO data_proper_motions
            (moca_oid, moca_pid, pmra_masyr, pmdec_masyr, pmra_masyr_unc, pmdec_masyr_unc,
             mission_name, data_release, origin, ignored, adopt_asis, adopted, is_public,
             public_adopt_asis, public_adopted, comments, rls, calculation_method)
            VALUES
            (:moca_oid, NULL, :pmra, :pmdec, :pmra_unc, :pmdec_unc,
             :mission_name, :data_release, :origin, 0, 0, 0, 0,
             0, 0, :comments, :rls, :calc_method)
        """)
        conn.execute(pm_sql, pm_params)

        # Insert PLX (if PM+PLX)
        if fit_mode == "pm_plx":
            plx_sql = text("""
                INSERT INTO data_parallaxes
                (moca_oid, moca_pid, parallax_mas, parallax_mas_unc,
                 mission_name, data_release, origin, ignored, adopt_asis, adopted, is_public,
                 public_adopt_asis, public_adopted, comments, rls)
                VALUES
                (:moca_oid, NULL, :plx, :plx_unc,
                 :mission_name, :data_release, :origin, 0, 0, 0, 0,
                 0, 0, :comments, :rls)
            """)
            conn.execute(plx_sql, plx_params)

        # Insert equatorial coordinates row
        eq_sql = text("""
            INSERT INTO data_equatorial_coordinates
            (moca_oid, moca_pid, ra, `dec`, ra_unc_mas, dec_unc_mas,
             measurement_epoch_yr, measurement_epoch_yr_unc, frame_equinox, coord_frame,
             mission_name, data_release, origin, ignored, adopt_asis, is_public,
             public_adopt_asis, adopt_as_reference, public_adopt_as_reference, single_epoch,
             pm_corrected, plx_corrected, point_of_view, comments, rls)
            VALUES
            (:moca_oid, NULL, :ra, :dec, :ra_unc, :dec_unc,
             :epoch, :epoch_unc, :frame_equinox, :coord_frame,
             :mission_name, :data_release, :origin, 0, 0, 0,
             0, 0, 0, 0,
             :pm_corrected, :plx_corrected, :point_of_view, :comments, :rls)
        """)
        conn.execute(eq_sql, eq_params)

        return f"Inserted PM{' + PLX' if fit_mode == 'pm_plx' else ''} and equatorial coordinates for moca_oid={moca_oid}."
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass

# --- Ensure astrometry callbacks are registered under Passenger/Gunicorn ---
try:
    import sys
    import dash

    _app_for_cb = dash.get_app()

    if not globals().get("_ASTROMETRY_CALLBACKS_REGISTERED", False):
        globals()["_ASTROMETRY_CALLBACKS_REGISTERED"] = True

        if "register_callbacks" in globals() and callable(globals()["register_callbacks"]):
            sys.stderr.write("[astrometry:init] calling register_callbacks()\n")
            sys.stderr.flush()
            globals()["register_callbacks"]()

    cb_keys = list(getattr(_app_for_cb, "callback_map", {}).keys())
    ast_keys = [k for k in cb_keys if "astrometry-plot-ra" in k or "astrometry-plot-dec" in k]
    sys.stderr.write(f"[astrometry:init] astrometry plot callback keys after register: {ast_keys}\n")
    sys.stderr.flush()
except Exception as e:
    try:
        import sys
        sys.stderr.write(f"[astrometry:init] callback registration block failed: {e}\n")
        sys.stderr.flush()
    except Exception:
        pass
