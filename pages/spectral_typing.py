import dash
from datetime import datetime
from dash import dcc, html, Input, Output, State, callback_context
import pandas as pd
import numpy as np
import plotly.graph_objs as go
from sqlalchemy import create_engine, MetaData, Table, select, Float, text
from scipy.optimize import minimize
from math import floor, ceil, log10
import os
import re
from urllib.parse import quote_plus as urlquote, urlparse, parse_qs

debug_printing = True

figure_export_config = {
  'toImageButtonOptions': {
    'format': 'png', # one of png, svg, jpeg, webp
    'height': 700,
    'width': 1900,
    'scale': 2 # Multiply title/legend/axis/canvas sizes by this factor
  }
}

min_chi2_val = 0.8

# =============================================================================
# Database connection parameters
# =============================================================================
default_host = '104.248.106.21'
default_username = 'public'
default_password = 'z@nUg_2h7_%?31y88'
default_dbname = 'mocadb'

env_host = os.environ.get('MOCA_HOST', default_host)
env_username = os.environ.get('MOCA_USERNAME', default_username)
env_password = os.environ.get('MOCA_PASSWORD', default_password)
env_dbname = os.environ.get('MOCA_DBNAME', default_dbname)

def get_connection_string_sptype(url_search=None):
    # Use defaults as fallback
    username = env_username
    password = env_password
    dbname = env_dbname
    host = env_host

    # If URL parameters are provided, try to extract them.
    if url_search:
        parsed_url = urlparse(url_search)
        qs = parse_qs(parsed_url.query)
        username = qs.get("user", [username])[0]
        password = qs.get("pwd", [password])[0]
        dbname   = qs.get("dbase", [dbname])[0]
        host     = qs.get("host", [host])[0]

    return f'mysql+pymysql://{username}:{urlquote(password)}@{host}/{dbname}'

def generate_spectral_type_label(value):
    """
    Generate the spectral type label for a given numeric value based on the OBAFGKMLTY scheme.
    The zero point (0) corresponds to M0, and the mapping extends symmetrically for negative values.
    """
    # Define the spectral classes
    classes = ['O', 'B', 'A', 'F', 'G', 'K', 'M', 'L', 'T', 'Y']

    # Offset the zero point to M0
    adjusted_value = value + 60  # 60 ensures 0 -> M0

    # Determine the spectral class and subclass
    class_index = int(adjusted_value // 10)  # Integer division for the class
    subclass = adjusted_value % 10          # Remainder for the subclass

    # Ensure the class index is within bounds
    if 0 <= class_index < len(classes):
        return f"{classes[class_index]}{subclass:.1f}".rstrip('0').rstrip('.')
    
    # Fallback for out-of-range values
    return f"{value}"

def average_resolving_power(wv_array):
    wv = np.asarray(wv_array, dtype=float)
    wv = wv[np.isfinite(wv)]
    if wv.size < 2:
        return np.nan
    wv = np.unique(np.sort(wv))
    if wv.size < 2:
        return np.nan
    dwv = np.diff(wv)
    wv_mid = 0.5 * (wv[1:] + wv[:-1])
    valid = np.isfinite(dwv) & (dwv > 0) & np.isfinite(wv_mid) & (wv_mid > 0)
    if not np.any(valid):
        return np.nan
    return float(np.nanmean(wv_mid[valid] / dwv[valid]))

# =============================================================================
# Constants for spectral processing
# =============================================================================
wv_min, wv_max = 0.85, 2.4

masked_regions = [(1.367, 1.424), (1.86, 2.0)]

# Subtle background chemical/atomic features (µm). Ranges are approximate and easy to tweak.
FEATURE_BANDS = [
    # Y/J band (~0.9–1.35 µm)
    {"name": "H₂O", "rng": (0.92, 0.96)},     # H2O feature near 0.95 µm
    {"name": "FeH", "rng": (0.985, 1.005)},     # Wing–Ford band
    {"name": "VO",  "rng": (1.045, 1.080)},     # VO band
    {"name": "H₂O", "rng": (1.130, 1.170)},     # H2O feature near 1.15 µm
    {"name": "VO",  "rng": (1.170, 1.200)},     # VO feature near 1.18–1.20 µm
    {"name": "FeH", "rng": (1.190, 1.240)},     # FeH feature around 1.2 µm
    {"name": "Na",  "rng": (1.137, 1.142), "ion": True},  # Na I doublet
    {"name": "K",   "rng": (1.169, 1.181), "ion": True},  # K I doublet (~1.177 µm)
    {"name": "K",   "rng": (1.243, 1.253), "ion": True},  # K I doublet
    {"name": "H₂O", "rng": (1.320, 1.350)},     # water edge into 1.4 µm band
    # H band (~1.45–1.80 µm)
    {"name": "H₂O", "rng": (1.500, 1.620)},
    {"name": "FeH", "rng": (1.583, 1.620)},
    # CH4 (from comparison figure): H-band and K-band features
    {"name": "CH₄", "rng": (1.60, 1.68)},     # H-band methane
    {"name": "CH₄", "rng": (1.72, 1.78)},     # H-band methane
    {"name": "CH₄", "rng": (2.20, 2.27)},     # K-band methane onset
    # K band (~2.00–2.40 µm)
    {"name": "H₂O", "rng": (1.950, 2.11)},
    # Single lines/features
    {"name": "Na", "rng": (2.200-0.005, 2.200+0.005), "ion": True},       # Na I near 2.20 µm
    {"name": "CO",  "rng": (2.293, 2.400)},     # CO (2-0) bandheads and beyond
    # Mid-IR bands (µm)
    {"name": "H₂O", "rng": (2.50, 3.10)},
    {"name": "CH₄", "rng": (3.15, 3.45)},
    {"name": "NH₃", "rng": (3.90, 4.50)},
    {"name": "PH₃", "rng": (4.20, 4.35)},
    {"name": "CO", "rng": (4.55, 4.95)},
    {"name": "H₂O", "rng": (5.00, 7.00)},
    {"name": "CH₄", "rng": (7.00, 9.20)},
    {"name": "Silicates", "rng": (9.00, 13.00)},
    {"name": "NH₃", "rng": (10.00, 11.00)},
    {"name": "CO₂", "rng": (14.70, 15.30)},
    {"name": "H₂O", "rng": (15.00, 20.00)},
]

def _add_feature_bands(fig, ypad_frac=0.04):
    """
    Add subtle shaded bands and labels for common features in the background.
    ypad_frac controls top/bottom padding in 'paper' coords to keep labels inside.
    """
    # Define ion and neutral colors
    ion_fill = "rgba(139,100,0,0.10)"      # gold, subtle
    ion_text = "rgba(139,100,0,0.65)"
    vo_fill = "rgba(0,139,0,0.10)" #dark green, subtle
    vo_text = "rgba(0,139,0,0.65)"
    ch4_fill = "rgba(139,69,139,0.10)" #pink, subtle
    ch4_text = "rgba(139,69,139,0.65)"
    h2o_fill = "rgba(0,0,139,0.10)"      # dark blue, subtle
    h2o_text = "rgba(0,0,139,0.65)"
    neutral_fill = "rgba(100,100,100,0.06)"
    neutral_text = "rgba(60,60,60,0.65)"
    
    for fb in FEATURE_BANDS:
        is_ion = fb.get("ion", False) or fb["name"] in ("Na", "K", "Ca")
        is_h2o = fb["name"] in ("H₂O", "H2O")
        is_ch4 = fb["name"] in ("CH₄", "CH4")
        is_vo = fb["name"] in ("VO")

        fillcolor = ch4_fill if is_ch4 else (h2o_fill if is_h2o else (ion_fill if is_ion else (vo_fill if is_vo else neutral_fill)))
        textcolor = ch4_text if is_ch4 else (h2o_text if is_h2o else (ion_text if is_ion else (vo_text if is_vo else neutral_text)))

        base_y = 1.0 - ypad_frac*0.3
        base_offset_unit = 0.04
        ion_offset = base_offset_unit if is_ion else 0.0
        h2o_offset = -base_offset_unit if is_h2o else 0.0
        ch4_offset = -base_offset_unit if is_ch4 else 0.0
        vo_offset = -base_offset_unit/2 if is_vo else 0.0
        max_ploty = 1.0 - ypad_frac*0.04
        y_pos = min(max_ploty, base_y + ion_offset + h2o_offset + ch4_offset + vo_offset)

        # Support either a band (rng) or a single vertical line (x)
        if "rng" in fb:
            x0, x1 = fb["rng"]
            fig.add_shape(
                type="rect",
                x0=x0, x1=x1, xref="x",
                y0=0.0, y1=y_pos-base_offset_unit, yref="paper",
                fillcolor=fillcolor,
                line=dict(width=0),
                layer="below"
            )
            x_annot = (x0 + x1) / 2.0
        elif "x" in fb:
            x_annot = fb["x"]
            fig.add_shape(
                type="line",
                x0=x_annot, x1=x_annot, xref="x",
                y0=0.0 + ypad_frac, y1=1.0 - ypad_frac, yref="paper",
                line=dict(width=1.5, color=textcolor)
            )
        else:
            continue

        fig.add_annotation(
            x=x_annot, xref="x",
            y=y_pos, yref="paper",
            text=fb["name"],
            showarrow=False,
            font=dict(size=13, color=textcolor),
            align="center"
        )

# Use three normalization regions as in tom_redl_sequence.py
# norm_regions = [
#     (wv_min, np.mean(masked_regions[0])),
#     (np.mean(masked_regions[0]), np.mean(masked_regions[1])),
#     (np.mean(masked_regions[1]), wv_max)
# ]

#More restrained norm regions
norm_regions = [(0.86, 1.35), (1.445, 1.800), (2.01, 2.400)]

pre_smoothing_min_bins_per_micron = 200
default_bins_per_micron = 200

# =============================================================================
# Helper functions for spectral processing
# =============================================================================
# --- UI-configurable normalization regions ---
def _format_norm_regions_text(regions):
    # e.g. [(0.85,1.395),(1.395,1.93),(1.93,2.4)] -> "0.850-1.395, 1.395-1.930, 1.930-2.400"
    return ", ".join([f"{r[0]:.3f}-{r[1]:.3f}" for r in regions])

DEFAULT_NORM_REGIONS_TEXT = _format_norm_regions_text(norm_regions)

# Robust parser for user-entered normalization regions
# Accepts: "0.85-1.395, 1.395-1.93, 1.93-2.4" or "[0.85:1.395]; (1.395,1.93) 1.93 2.4" etc.
REGION_WINDOW_SPLIT_RE = re.compile(r"[;,]+|\s{2,}")
REGION_BOUNDS_SPLIT_RE = re.compile(r"\s*[-:,]\s*|\s+")

def parse_norm_regions(text, low=wv_min, high=wv_max):
    if not text:
        return list(norm_regions)
    s = re.sub(r"[\[\](){}]", " ", text.strip())
    chunks = [c for c in REGION_WINDOW_SPLIT_RE.split(s) if c.strip()]
    out = []
    for ch in chunks:
        parts = [p for p in REGION_BOUNDS_SPLIT_RE.split(ch) if p.strip()]
        if len(parts) < 2:
            continue
        try:
            a = float(parts[0]); b = float(parts[1])
            lo, hi = (a, b) if a <= b else (b, a)
            lo = max(lo, low); hi = min(hi, high)
            if hi > lo:
                out.append((round(lo, 6), round(hi, 6)))
        except ValueError:
            continue
    return out if out else list(norm_regions)

def median_smooth(df, bins_per_micron):
    if bins_per_micron <= 0:
        return df  # no smoothing if disabled
    df = df.copy()
    #wavelength_range = df['wv'].max() - df['wv'].min()
    bin_size = 1.0 / bins_per_micron
    bins = np.arange(df['wv'].min(), df['wv'].max(), bin_size)
    df['wv_bin'] = pd.cut(df['wv'], bins, labels=bins[:-1])
    df = df.groupby('wv_bin', as_index=False, observed=True).median()
    df.drop(columns=['wv_bin'], inplace=True)
    return df

def apply_wavelength_mask(df, masked_regions):
    df = df.copy()
    for min_wv, max_wv in masked_regions:
        df.loc[df['wv'].between(min_wv, max_wv), 'sp'] = np.nan
    return df

def weighted_median(values, weights):
    i = np.argsort(values)
    c = np.cumsum(weights[i])
    return values[i[np.searchsorted(c, 0.5 * c[-1])]]

def _mad_shifted_flux(flux_vals):
    flux = np.asarray(flux_vals, dtype=float)
    flux = flux[np.isfinite(flux)]
    if flux.size < 2:
        return np.nan
    dif = flux[1:] - flux[:-1]
    if dif.size == 0:
        return np.nan
    med_dif = np.nanmedian(dif)
    mad = np.nanmedian(np.abs(dif - med_dif))
    return float(mad) if np.isfinite(mad) and mad > 0 else np.nan

def _prepare_errors_for_metrics(flux_vals, err_vals):
    flux = np.asarray(flux_vals, dtype=float)
    if err_vals is None:
        err = np.full_like(flux, np.nan, dtype=float)
    else:
        err = np.asarray(err_vals, dtype=float)
        if err.shape != flux.shape:
            err = np.full_like(flux, np.nan, dtype=float)
    err = np.where(np.isfinite(err), np.abs(err), np.nan)

    finite_err = np.isfinite(err) & (err > 0)
    # If a spectrum has no finite errors at all, estimate from MAD(flux - shift(flux,1)).
    if not np.any(finite_err):
        mad_est = _mad_shifted_flux(flux)
        if np.isfinite(mad_est) and mad_est > 0:
            err = np.where(np.isfinite(flux), mad_est, np.nan)
            finite_err = np.isfinite(err) & (err > 0)

    # Floor 1: 0.01% of |flux| at each wavelength.
    floor_flux = 1e-4 * np.abs(flux)
    err = np.where(finite_err, np.fmax(err, floor_flux), err)

    # Floor 2: 0.8 * median(error) within each spectrum.
    finite_pos = err[np.isfinite(err) & (err > 0)]
    if finite_pos.size > 0:
        floor_med = 0.8 * float(np.nanmedian(finite_pos))
        if np.isfinite(floor_med) and floor_med > 0:
            err = np.where(np.isfinite(err), np.fmax(err, floor_med), err)
    return err

def _weighted_scale_chi2_minimization(x_ref, y_ref, e_ref, x_tgt, y_tgt, e_tgt):
    y_ref_i = np.interp(x_tgt, x_ref, y_ref, left=np.nan, right=np.nan)
    e_ref_i = np.interp(x_tgt, x_ref, e_ref, left=np.nan, right=np.nan)
    denom = np.sqrt(e_ref_i**2 + e_tgt**2)
    valid = (
        np.isfinite(y_ref_i) &
        np.isfinite(y_tgt) &
        np.isfinite(denom) & (denom > 0)
    )
    if np.sum(valid) == 0:
        return np.nan
    num = np.nansum((y_ref_i[valid] * y_tgt[valid]) / denom[valid])
    den = np.nansum((y_tgt[valid] * y_tgt[valid]) / denom[valid])
    if not np.isfinite(den) or den == 0:
        return np.nan
    return float(num / den)

def cardelli_extinction_law(wavelength, R_V):
    """
    Computes the extinction curve A(λ)/A(V) using the Cardelli, Clayton, & Mathis (1989) law.
    
    Parameters:
        wavelength (array): Wavelengths in microns.
        R_V (float): Ratio of total to selective extinction.
    
    Returns:
        A_lambda_Av (array): Extinction at each wavelength normalized to A(V).
    """
    x = 1.0 / wavelength  # Convert to inverse microns

    # Initialize extinction coefficients
    a, b = np.zeros_like(x), np.zeros_like(x)

    # Optical/NIR range (0.3 ≤ x < 3.3 → 0.3-3.3 μm)
    mask_opt_nir = (x >= 0.3) & (x < 3.3)
    if np.any(mask_opt_nir):
        y = x[mask_opt_nir]
        a[mask_opt_nir] = 0.574 * y**1.61
        b[mask_opt_nir] = -0.527 * y**1.61

    # Mid-IR range (x < 0.3 → λ > 3.3 μm)
    mask_mid_ir = (x < 0.3)
    if np.any(mask_mid_ir):
        a[mask_mid_ir] = 0.574 * (0.3)**1.61  # Extrapolated
        b[mask_mid_ir] = -0.527 * (0.3)**1.61  # Extrapolated

    return a + b / R_V

def deredden_spectrum(observed_spectrum, A_V, R_V):
    """
    Applies de-reddening to the observed spectrum using the Cardelli extinction law.
    
    Parameters:
        observed_spectrum (DataFrame): Observed spectrum with 'wv' (wavelength in microns) and 'sp' (flux).
        A_V (float): Extinction value in magnitudes.
        R_V (float): Ratio of total to selective extinction.
    
    Returns:
        DataFrame: De-reddened spectrum.
    """
    wv = observed_spectrum["wv"].values
    flux = observed_spectrum["spn"].values

    A_lambda_Av = cardelli_extinction_law(wv, R_V)
    extinction_factor = 10**(0.4 * A_V * A_lambda_Av)

    #dereddened_flux = flux * extinction_factor
    dereddened_flux = (flux * extinction_factor) / np.nanmedian(extinction_factor)
    return observed_spectrum.assign(spn=dereddened_flux)  # Preserve DataFrame structure

def optimize_A_V_R_V(observed_spectrum, reference_spectrum):
    """
    Optimizes A(V) and R(V) to best match the observed spectrum (after de-reddening) to the reference spectrum.
    
    Parameters:
        observed_spectrum (DataFrame): Observed spectrum with 'wv' (wavelength in microns) and 'sp' (flux).
        reference_spectrum (DataFrame): Reference spectrum with 'wv' and 'sp'.
    
    Returns:
        tuple: Best-fit (A_V, R_V).
    """
    def loss(params):
        A_V, R_V = params
        dereddened_spectrum = deredden_spectrum(observed_spectrum, A_V, R_V)
    
        # Extract flux values
        ref_sp = reference_spectrum["spn"].values
        dereddened_sp = dereddened_spectrum["spn"].values
        
        # Create a mask for valid data (both spectra have non-NaN values)
        valid = (~np.isnan(ref_sp)) & (~np.isnan(dereddened_sp)) & (~np.isinf(ref_sp)) & (~np.isinf(dereddened_sp))
        if np.sum(valid) == 0:
            return np.inf  # Penalize if no valid data
        
        # Use only valid data points
        ref_sp_valid = ref_sp[valid]
        dereddened_sp_valid = dereddened_sp[valid]
        
        # Compute the ratio of reference to dereddened flux
        ratio = ref_sp_valid / dereddened_sp_valid
        # Only keep ratios that are finite
        valid_ratio = ratio[np.isfinite(ratio)]
        if valid_ratio.size == 0:
            return np.inf

        # Compute the median ratio
        median_ratio = np.nanmedian(valid_ratio)

        # Normalize the dereddened spectrum using the median ratio
        dereddened_sp_valid_norm = dereddened_sp_valid * median_ratio

        # Compute and return the loss (sum of squared differences)
        return np.sum((dereddened_sp_valid_norm - ref_sp_valid) ** 2)
    
    def grad_loss(params):
        A_V, R_V = params
        c = 0.4 * np.log(10)  # Constant: 0.4*ln(10)
        
        dereddened_spectrum = deredden_spectrum(observed_spectrum, A_V, R_V)
        ref_sp = reference_spectrum["spn"].values
        dereddened_sp = dereddened_spectrum["spn"].values
        
        valid = (~np.isnan(ref_sp)) & (~np.isnan(dereddened_sp)) & (~np.isinf(ref_sp)) & (~np.isinf(dereddened_sp))
        if np.sum(valid) == 0:
            return np.array([np.nan, np.nan])
        
        ref_sp_valid = ref_sp[valid]
        dereddened_sp_valid = dereddened_sp[valid]
        # Compute median ratio m (treated as constant in the derivative)
        m = np.nanmedian(ref_sp_valid / dereddened_sp_valid)
        
        # Residual vector: difference between normalized de-reddened flux and reference flux.
        residual = m * dereddened_sp_valid - ref_sp_valid
        
        # Get the wavelengths corresponding to valid data.
        wv_valid = observed_spectrum["wv"].values[valid]
        # Compute extinction coefficients a and b.
        a, b = cardelli_extinction_coeffs(wv_valid, R_V)
        # Compute A_lambda using the Cardelli law: A_lambda = a + b/R_V.
        A_lambda = a + b / R_V
        # Let D = de-reddened flux (before normalization) for valid points.
        D = dereddened_sp_valid
        
        # Compute gradients.
        # Gradient with respect to A_V:
        grad_A_V = 2 * m * c * np.sum(residual * A_lambda * D)
        # Gradient with respect to R_V:
        grad_R_V = -2 * m * c * A_V * np.sum(residual * (b / (R_V**2)) * D)
        
        return np.array([grad_A_V, grad_R_V])

    # Initial guesses: A_V = 1.0, R_V = 3.1
    initial_guess = [1.0, 3.1]

    # Bounds: A_V in [0, 10], R_V in [2.0, 5.5] (physical range for R_V)
    #bounds = [(-10, 10), (2.0, 5.5)]
    bounds = [(-50, 50), (0.01, 50.5)]

    result = minimize(loss, initial_guess, bounds=bounds, method='L-BFGS-B')
    #result = minimize(loss, initial_guess, bounds=bounds, method='L-BFGS-B', jac=grad_loss)
    #result = minimize(loss, initial_guess, bounds=bounds, method='BFGS')
    #result = minimize(loss, initial_guess, bounds=bounds, method='Powell') #Too agressive sometimes
    return result.x  # Returns (A_V, R_V)

#def load_and_process_spectrum(moca_specid, bins_per_micron=None, common_wv=None, debug=False, url_search=None):
def process_spectrum(df, bins_per_micron=None, common_wv=None, debug=False, norm_regions_param=None):
    # Ensure that at least one of bins_per_micron or common_wv is provided.
    if bins_per_micron is None and common_wv is None:
        raise ValueError("Either bins_per_micron or common_wv must be specified.")

    if df.empty:
        return df
    
    if 'wv' not in df.columns:
        #import pdb; pdb.set_trace()
        return pd.DataFrame()

    # Apply wavelength mask.
    df = apply_wavelength_mask(df, masked_regions)
    
    local_norm_regions = norm_regions_param if norm_regions_param else norm_regions
    
    # Process normalization over defined wavelength regions.
    df_processed = pd.DataFrame()
    for norm_min, norm_max in local_norm_regions:
        region_df = df[(df['wv'] >= norm_min) & (df['wv'] <= norm_max)].copy()
        if region_df.empty:
            continue
        # Determine the number of bins for pre-smoothing.
        pre_smooth_bins = max(bins_per_micron, pre_smoothing_min_bins_per_micron) if bins_per_micron is not None else pre_smoothing_min_bins_per_micron
        region_smoothed = median_smooth(region_df, pre_smooth_bins)
        weights = np.nan_to_num(region_smoothed['sp'].values ** 2)
        norm_val = weighted_median(region_smoothed['sp'].values, weights)
        region_df['spn'] = region_df['sp'] / norm_val
        if 'esp' in region_df.columns:
            region_df['espn'] = region_df['esp'] / norm_val
        df_processed = pd.concat([df_processed, region_df])
    
    if 'wv' not in df_processed.columns:
        #import pdb; pdb.set_trace()
        return pd.DataFrame()

    df_processed = df_processed.dropna(subset=['wv', 'spn'])
    if debug:
        original_df = df_processed.copy() # For debugging

    # Compute the median resolution of the processed spectrum.
    current_res = np.median(np.diff(df_processed['wv'].values))
    
    # Case 1: No common_wv provided.
    if common_wv is None:
        required_bin_size = 1.0 / bins_per_micron
        if current_res >= required_bin_size:
            # The spectrum is too coarse: keep original grid (split by local_norm_regions)
            df_binned_list = []
            for norm_min, norm_max in local_norm_regions:
                region_df = df_processed[(df_processed['wv'] >= norm_min) & (df_processed['wv'] <= norm_max)]
                if not region_df.empty:
                    df_binned_list.append(region_df)
            if df_binned_list:
                df_processed = pd.concat(df_binned_list).sort_values('wv')
            # Else, df_processed remains unchanged.
        else:
            # Otherwise, perform median binning as usual.
            df_binned_list = []
            # Create bins using bins_per_micron over each norm region.
            for norm_min, norm_max in local_norm_regions:
                region_df = df_processed[(df_processed['wv'] >= norm_min) & (df_processed['wv'] <= norm_max)].copy()
                if region_df.empty:
                    continue
                # Compute bin edges for this region.
                bin_size = 1.0 / bins_per_micron
                region_common_wv = np.arange(region_df['wv'].min(), region_df['wv'].max() + bin_size, bin_size)
                if len(region_common_wv) >= 2:
                    half_steps = (region_common_wv[1:] - region_common_wv[:-1]) / 2.0
                    first_edge = region_common_wv[0] - half_steps[0]
                    last_edge = region_common_wv[-1] + half_steps[-1]
                    edges = np.concatenate([[first_edge], region_common_wv[:-1] + half_steps, [last_edge]])
                else:
                    edges = np.array([region_common_wv[0] - 0.001, region_common_wv[0] + 0.001])
                region_df['wv_bin'] = pd.cut(region_df['wv'], bins=edges, labels=region_common_wv, include_lowest=True)
                df_region_binned = region_df.groupby('wv_bin', as_index=False).agg({
                    'spn': 'median',
                    'esp': lambda x: np.nan if len(x) == 0 else np.sqrt(np.sum(x**2)) / np.sqrt(len(x)),
                    'moca_specid': 'first'
                })
                df_region_binned.rename(columns={'wv_bin': 'wv'}, inplace=True)
                df_region_binned['wv'] = df_region_binned['wv'].astype(float)
                df_binned_list.append(df_region_binned)
            if df_binned_list:
                df_processed = pd.concat(df_binned_list).sort_values('wv')
            else:
                df_processed = pd.DataFrame()
    
    # Case 2: common_wv is provided.
    else:
        common_wv = np.sort(np.array(common_wv))
        common_res = np.median(np.diff(common_wv))
        if current_res >= common_res:
            # The spectrum's resolution is lower than the common grid:
            # Interpolate the spectrum onto the common_wv grid.
            interp_spn = np.interp(common_wv, df_processed['wv'], df_processed['spn'], left=np.nan, right=np.nan)
            if 'esp' in df_processed.columns:
                interp_esp = np.interp(common_wv, df_processed['wv'], df_processed['esp'], left=np.nan, right=np.nan)
            else:
                interp_esp = np.full_like(common_wv, np.nan)
            # Also retain moca_specid from the original first row (assuming it's constant)
            moca_specid_val = df_processed['moca_specid'].iloc[0] if 'moca_specid' in df_processed.columns else None
            df_processed = pd.DataFrame({'wv': common_wv, 'spn': interp_spn, 'esp': interp_esp})
            if moca_specid_val is not None:
                df_processed['moca_specid'] = moca_specid_val
        else:
            # Otherwise, if the original spectrum is high-resolution compared to common_wv,
            # perform median binning onto the common_wv grid for each norm_region.
            df_binned_list = []
            for norm_min, norm_max in local_norm_regions:
                region_df = df_processed[(df_processed['wv'] >= norm_min) & (df_processed['wv'] <= norm_max)].copy()
                if region_df.empty:
                    continue
                region_common_wv = common_wv[(common_wv >= norm_min) & (common_wv <= norm_max)]
                if len(region_common_wv) == 0:
                    continue
                if len(region_common_wv) >= 2:
                    half_steps = (region_common_wv[1:] - region_common_wv[:-1]) / 2.0
                    first_edge = region_common_wv[0] - half_steps[0]
                    last_edge = region_common_wv[-1] + half_steps[-1]
                    edges = np.concatenate([[first_edge], region_common_wv[:-1] + half_steps, [last_edge]])
                else:
                    edges = np.array([region_common_wv[0] - 0.001, region_common_wv[0] + 0.001])
                region_df = region_df.dropna(subset=['wv', 'spn'])
                region_df['wv_bin'] = pd.cut(region_df['wv'], bins=edges, labels=region_common_wv, include_lowest=True)
                df_region_binned = region_df.groupby('wv_bin', as_index=False).agg({
                    'spn': 'median',
                    'esp': lambda x: np.nan if len(x) == 0 else np.sqrt(np.sum(x**2)) / np.sqrt(len(x)),
                    'moca_specid': 'first'
                })
                df_region_binned.rename(columns={'wv_bin': 'wv'}, inplace=True)
                df_region_binned['wv'] = df_region_binned['wv'].astype(float)
                df_binned_list.append(df_region_binned)
            if df_binned_list:
                df_processed = pd.concat(df_binned_list).sort_values('wv')
            else:
                df_processed = pd.DataFrame()
    
    if debug:
        # --- Debugging Block using Plotly ---
        import plotly.graph_objects as go
        import plotly.io as pio
        #import pdb
        # Set the default renderer to open in a browser window for debugging
        pio.renderers.default = "browser"

        fig_debug = go.Figure()
        # Plot original (unbinned) spectrum with error bars and 50% transparency
        fig_debug.add_trace(go.Scatter(
            x=original_df['wv'],
            y=original_df['spn'],
            error_y=dict(
                type='data',
                array=original_df['esp'],
                visible=True
            ),
            mode='markers',
            name='Original Spectrum',
            opacity=0.5  # 50% transparency
        ))
        # Plot rebinned spectrum with error bars and larger symbols
        fig_debug.add_trace(go.Scatter(
            x=df_processed['wv'],
            y=df_processed['spn'],
            error_y=dict(
                type='data',
                array=df_processed['esp'],
                visible=True
            ),
            mode='markers',
            name='Binned Spectrum',
            marker=dict(size=12)  # Larger marker symbols
        ))
        fig_debug.update_layout(
            title="Debug: Original vs. Binned Spectrum",
            xaxis_title="Wavelength (µm)",
            yaxis_title="Normalized Flux"
        )
        fig_debug.show()

        #pdb.set_trace()
        # --- End Debugging Block ---

    return df_processed


def darken_color(color, factor=0.7):
    # simple darkening helper for annotations if needed
    import matplotlib.colors as mc
    rgb = mc.to_rgb(color)
    return f'rgb({int(rgb[0]*255*factor)},{int(rgb[1]*255*factor)},{int(rgb[2]*255*factor)})'

# =============================================================================
# Dash app layout (each DIV includes "sp‑typing" in its id)
# =============================================================================
dash.register_page(__name__, path='/spectral-typing')

layout = html.Div([
    dcc.Location(id='sp-typing-url'),
    html.Div([
         html.Div([
              html.H1("MOCA Spectral Typing", id='sp-typing-header'),
              html.P([
                  "This dash app is used to assign spectral types visually.",
                  html.Br(),
                  "Please be patient as the initial download of the spectral standards grid can take a minute or two."
              ], style={"fontStyle": "italic", "marginBottom": "20px"}),
              html.Div([
                   html.Label("Select Comparison Spectrum:", style={"fontWeight": "bold"}),
                   dcc.Dropdown(
                       id='sp-typing-comparison-dropdown',
                       options=[],  # Populated via callback
                   )
              ], id='sp-typing-comparison-div', style={'margin-bottom': '15px'}),
              html.Div([
                   html.Div([
                        html.Div([
                             html.Label("Select Spectral Grid:", style={"fontWeight": "bold"}),
                             dcc.Dropdown(id='sp-typing-grid-dropdown', options=[]),
                        ], id='sp-typing-grid-div', style={'margin-bottom': '15px'}),
                        html.Div([
                             html.Label("Bins per Micron:", style={"fontWeight": "bold"}),
                             dcc.Input(id='sp-typing-bins-input', type='number', value=default_bins_per_micron),
                        ], id='sp-typing-bins-div', style={'margin-bottom': '15px'}),
                        html.Div([
                            html.Label("Normalization regions (µm):", style={"fontWeight": "bold"}),
                            dcc.Textarea(
                                id='sp-typing-norm-regions-input',
                                value=DEFAULT_NORM_REGIONS_TEXT,
                                style={'width': '100%', 'height': '30px', 'fontFamily': 'monospace'},
                                placeholder='e.g. 0.850-1.395, 1.395-1.930, 1.930-2.400'
                            ),
                            html.Div([
                                html.Button("Reset to default", id='sp-typing-norm-reset', n_clicks=0, style={'marginTop': '6px'})
                            ])
                        ], id='sp-typing-norm-div', style={'margin-bottom': '15px'})
                   ], style={'flex': '1'}),
                   html.Div([
                        html.Button("↑ Previous Grid", id='sp-typing-prev-grid-button', disabled=True, n_clicks=0, style={'fontSize': '16px', 'border': '3px solid black', 'margin-bottom': '10px', 'textAlign': 'left'}),
                        html.Button("↓ Next Grid", id='sp-typing-next-grid-button', disabled=True, n_clicks=0, style={'fontSize': '16px', 'border': '3px solid black', 'textAlign': 'left'})
                   ], style={'display': 'flex', 'flexDirection': 'column', 'justifyContent': 'center', 'margin-left': '15px'})
              ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '15px'}),
              html.Div([
                   dcc.Checklist(
                       options=[{'label': 'Apply Dereddening (slow)', 'value': 'deredden'}],
                       id='sp-typing-deredden-checklist',
                   )
              ], id='sp-typing-deredden-div', style={'margin-bottom': '15px'}),
              html.Div([
                   dcc.Checklist(
                       options=[{'label': 'All standards shown in red', 'value': 'allred'}],
                       value=['allred'],  # default ON
                       id='sp-typing-allred-checklist',
                   )
              ], id='sp-typing-allred-div', style={'margin-bottom': '15px'}),
              html.Div([
                   dcc.Checklist(
                       options=[{'label': 'Show chemical features', 'value': 'showfeatures'}],
                       value=['showfeatures'],  # default ON
                       id='sp-typing-showfeatures-checklist',
                   )
              ], id='sp-typing-showfeatures-div', style={'margin-bottom': '15px'}),
              html.Div([
                   dcc.Checklist(
                       options=[{'label': 'Deactivate low-resolution display mode', 'value': 'disable_lowres'}],
                       value=[],
                       id='sp-typing-lowres-checklist',
                   )
              ], id='sp-typing-lowres-div', style={'margin-bottom': '15px'}),
              html.Div([
                   html.Div([
                        html.Button(
                            "Generate SQL type",
                            id='sp-typing-sqlout-button',
                            n_clicks=0,
                            style={'fontSize': '12px',
                                   'border': '3px solid black',
                                   'verticalAlign': 'middle',
                                   'marginRight': '12px',
                                   'display': 'none'}
                        ),
                        html.Button(
                            "Adopt type in MOCAdb",
                            id='sp-typing-sqlout-adopt-button',
                            n_clicks=0,
                            style={'fontSize': '12px',
                                   'border': '3px solid black',
                                   'verticalAlign': 'middle',
                                   'display': 'none'}
                        )
                   ], style={'display': 'flex', 'flexDirection': 'row'}),
                   html.Div([
                        html.Button("← Previous Standard", id='sp-typing-prev-button', disabled=True, n_clicks=0,
                                    style={'fontSize': '16px', 'border': '3px solid black', 'marginRight': '15px', 'verticalAlign': 'middle'}),
                        html.Button("Next Standard →", id='sp-typing-next-button', disabled=True, n_clicks=0,
                                    style={'fontSize': '16px', 'border': '3px solid black', 'verticalAlign': 'middle'}),
                   ], style={'display': 'flex', 'flexDirection': 'row', 'marginBottom': '10px'})
              ], id='sp-typing-nav-div', style={'margin-bottom': '15px'}),
            html.Div(
                id='sp-typing-sqlout-output',
                children=[
                    dcc.Textarea(
                        id='sp-typing-sqlout-text',
                        value='',
                        readOnly=True,
                        style={'width': '100%', 'height': '140px', 'fontFamily': 'monospace'}
                    )
                ],
                style={'display': 'none', 'marginTop': '10px'}
            )
         ], style={'flex': '1'}),
         html.Div([
            html.Div([
                 dcc.Slider(
                     id='sp-typing-vertical-slider',
                     min=0,
                     max=10,
                     step=1,
                     value=0,
                     disabled=True,
                     marks={0: ''},
                     updatemode='drag'
                 )
            ], style={'width': '300px'})
        ], style={
            'alignItems': 'flex-start',
            'width': '150px',
            'transform': 'rotate(-90deg) translateX(-400px) translateY(-10px)',
            'transform-origin': 'top left',
            'margin-left': '20px',
            'textAlign': 'left',
            'padding': '20px 0'
        })
    ], style={'display': 'flex', 'margin-bottom': '15px'}),
    html.Div([
         dcc.Slider(
              id='sp-typing-index-slider',
              min=0,
              max=0,
              step=1,
              value=0,
              marks={0: ''}
         )
    ], style={'width': '100%', 'margin-bottom': '15px'}),
    dcc.Graph(id='sp-typing-graph', style={'height': '700px'}),#sp-typing-chi2-graph
    dcc.Graph(id='sp-typing-chi2-graph'),
    html.Div(
        id='sp-typing-standard-meta',
        style={
            'marginTop': '10px',
            'marginBottom': '20px',
            'padding': '10px 12px',
            'border': '1px solid #ddd',
            'backgroundColor': '#fcfcfc',
            'borderRadius': '4px',
            'lineHeight': 1.5
        }
    ),
    html.Div(
         className="row",
         id="url-help-section-sptyping",
         children=[
              dcc.Markdown(
                  """
                ## Using URL Parameters
                
                You can customize the app by appending parameters to the URL query string. The following parameters are supported:
                
                - **specid**: Pre-select a comparison spectrum (e.g., `specid=1`).
                - **grid**: Select the spectral grid (e.g., `grid=field`).
                - **bins**: Set the number of bins per micron (e.g., `bins=20`).
                - **deredden**: Apply dereddening if set to True (e.g., `deredden=True`).
                - **grid_index**: Set the starting display index for the grid (e.g., `grid_index=2`).
                - **norm**: Custom normalization regions in microns. Accepts flexible separators like commas or semicolons and `-`, `:`, or whitespace between bounds. Example: `norm=0.850-1.395,1.395-1.930,1.930-2.400`.
                
                ### Example URL:  
                - `https://dataviz.mocadb.ca/spectral-typing?specid=1&grid=field&bins=20&deredden=True&grid_index=2&norm=0.850-1.395,1.395-1.930,1.930-2.400`
                
                *Tip:* If you include spaces, your browser will URL-encode them automatically. The app also accepts semicolons and colons as separators.
                  """
              ),
         ],
         style={"padding": "20px", "backgroundColor": "#f9f9f9"}
    ),
    dcc.Store(id='sp-typing-precomputed-store'),
    dcc.Store(id='sp-typing-current-index', data=0),
    dcc.Store(id='sp-typing-comparison-spectrum'),
    dcc.Store(id='sp-typing-comparison-designation'),
    dcc.Store(id='sp-typing-db-data'),
    dcc.Store(id='sp-typing-grid-data'),
    dcc.Store(id='sp-typing-grid-raw-spectra'),
    dcc.Store(id='sp-typing-comparison-raw-spectrum'),
    dcc.Store(id='sp-typing-current-sptnum'),
    dcc.Store(id='sp-typing-norm-regions-store'),
    dcc.Store(id='sp-typing-sqlout-flag'),
    dcc.Store(id='sp-typing-sqlout-adopt-flag'),
], style={'width': '70%', 'margin': 'auto', 'padding': '20px'})

# =============================================================================
# Callback: Populate standard dropdown with available MOCA SpecIDs (with default specid from URL)
# =============================================================================
@dash.callback(
    Output('sp-typing-comparison-dropdown', 'options'),
    Output('sp-typing-comparison-dropdown', 'value'),
    Output('sp-typing-comparison-designation', 'data'),
    Output('sp-typing-db-data', 'data'),
    Input('sp-typing-url', 'search')
)
def update_comparison_options(search):
    if search:
        parsed = urlparse(search)
        qs = parse_qs(parsed.query)
        specid = qs.get("moca_specid", qs.get("specid", [None]))[0]
    else:
        specid = None
    
    connection_string = get_connection_string_sptype(url_search=search)
    engine = create_engine(connection_string)
    query = """
        SELECT ms.moca_specid,
               ms.moca_oid,
               ms.moca_instid,
               CONCAT(
                'specid', ms.moca_specid,
                COALESCE(CONCAT(',oid', ms.moca_oid),''), ': ',
                COALESCE(
                    CONCAT(
                        mo.designation, ' (', spt.spectral_type, ') with ', ms.moca_instid,
                        COALESCE(CONCAT(' in ', ms.instrument_mode_name, ' mode'), ''),
                        COALESCE(CONCAT(' (', ms.data_collection_date, ')'), '')
                    ),
                    ms.spectrum_name
                )
               ) AS spectrum_name,
               mo.designation
        FROM moca_spectra ms
        LEFT JOIN moca_objects mo USING(moca_oid)
        LEFT JOIN (SELECT moca_oid, spectral_type FROM data_spectral_types WHERE adopted=1) spt USING(moca_oid)
        WHERE (ms.moca_specpackid != 1 OR ms.moca_specpackid IS NULL) AND ms.ignored=0
    """
    df = pd.read_sql(query, engine)
    options = [{'label': row["spectrum_name"], 'value': row["moca_specid"]} for index, row in df.iterrows()]
    designation_map = {row["moca_specid"]: row["spectrum_name"].split(': ')[1].split(' with ')[0] for index, row in df.iterrows()}
    
    valid_specids = [str(opt['value']) for opt in options]
    default_value = specid if specid in valid_specids else None
    
    return options, int(default_value) if default_value is not None else None, designation_map, df.to_json(date_format='iso', orient='split')

# =============================================================================
# SQL Output Button Helper Functions and Callbacks
# =============================================================================

def _parse_spectral_class_and_suffix(spt: str):
    if not spt or not isinstance(spt, str):
        return None, None
    s = spt.strip()
    for pref in ('esd', 'd/sd', 'sd'):
        if s.lower().startswith(pref):
            rest = s[len(pref):].lstrip()
            m = re.search(r'[OBAFGKMLTY]', rest, re.IGNORECASE)
            spectral_class = m.group(0).upper() if m else None
            return spectral_class, ('d/sd' if pref == 'd/sd' else pref)
    m = re.search(r'[OBAFGKMLTY]', s, re.IGNORECASE)
    spectral_class = m.group(0).upper() if m else None
    return spectral_class, None

def _infer_gravity_class(grid_row):
    gc = None
    try:
        gc = (grid_row.get('gravity_class') or '').strip().lower()
    except Exception:
        gc = None
    if gc in ('beta', 'β'):
        return 'β'
    if gc in ('gamma','γ'):
        return 'γ'
    if gc in ('delta','δ'):
        return 'δ'
    name = ''
    try:
        name = (grid_row.get('moca_sptgridid') or '').lower()
    except Exception:
        name = ''
    if any(tag in name for tag in ['beta', 'vl-g', 'vlg']):
        return 'beta'
    if any(tag in name for tag in ['gamma', 'int-g', 'intg']):
        return 'gamma'
    if 'delta' in name:
        return 'delta'
    return None

# Callback to read sqlout=true from URL and toggle the button
@dash.callback(
    Output('sp-typing-sqlout-flag', 'data'),
    Output('sp-typing-sqlout-adopt-flag', 'data'),
    Output('sp-typing-sqlout-button', 'style'),
    Output('sp-typing-sqlout-adopt-button', 'style'),
    Input('sp-typing-url', 'href')
)
def set_sqlout_flag(href):
    show = False
    show_adopt = False
    
    # If the username is management or collaborators, show SQLout button
    try:
        parsed = urlparse(url_search) if url_search else None
        qs = parse_qs(parsed.query) if parsed else {}
        username_param = (qs.get('user', [env_username])[0] or '').strip().lower()
    except Exception:
        username_param = env_username

    if href:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        val = (qs.get('sqlout', [None])[0] or '').lower()
        show = val in ('true', '1', 'yes')

    if username_param == 'management' or username_param == 'collaborators':
        show = True
    if username_param == 'management':
        show_adopt = True
        
    btn_style = {'fontSize': '12px', 'border': '3px solid black', 'verticalAlign': 'middle', 'marginLeft': '12px'}
    if not show:
        btn_style['display'] = 'none'

    btn_style_adopt = {'fontSize': '12px', 'border': '3px solid black', 'verticalAlign': 'middle', 'marginLeft': '12px'}
    if not show:
        btn_style_adopt['display'] = 'none'

    return bool(show), bool(show_adopt), btn_style, btn_style_adopt

# Callback to generate SQL text on button press
@dash.callback(
    Output('sp-typing-sqlout-text', 'value'),
    Output('sp-typing-sqlout-output', 'style'),
    Input('sp-typing-sqlout-button', 'n_clicks'),
    Input('sp-typing-sqlout-adopt-button', 'n_clicks'),
    State('sp-typing-sqlout-flag', 'data'),
    State('sp-typing-current-index', 'data'),
    State('sp-typing-grid-dropdown', 'value'),
    State('sp-typing-precomputed-store', 'data'),
    State('sp-typing-comparison-spectrum', 'data'),
    State('sp-typing-db-data', 'data'),
    State('sp-typing-grid-data', 'data'),
    State('sp-typing-deredden-checklist', 'value'),
    State('sp-typing-norm-regions-store', 'data'),
    State('sp-typing-url', 'search')
)
def generate_sql(n_clicks, n_clicks_adopt, sqlout_enabled, current_index, selected_grid, precomputed, comparison_data, df_data_json, grid_data_json, deredden_value, norm_regions_store, url_search):
    if not (sqlout_enabled and (n_clicks or n_clicks_adopt) and precomputed and comparison_data and df_data_json and grid_data_json):
        raise dash.exceptions.PreventUpdate
    # pick current entry
    filtered = [e for e in precomputed if e.get('grid') == selected_grid]
    if not filtered:
        raise dash.exceptions.PreventUpdate
    idx = max(0, min(int(current_index or 0), len(filtered)-1))
    entry = filtered[idx]
    std_specid = int(entry.get('moca_specid'))
    spt = str(entry.get('spectral_type'))
    sptn = float(entry.get('spectral_type_number')) if entry.get('spectral_type_number') is not None else None
    redchi2 = entry.get('reduced_chi2')
    comp_df = pd.DataFrame(comparison_data)
    comp_specid = int(comp_df['moca_specid'].iloc[0])
    df_data = pd.read_json(df_data_json, orient='split')
    row_obj = df_data[df_data['moca_specid'] == comp_specid].iloc[0]
    # NaN-safe extraction for moca_oid, moca_instid, and designation
    _moca_oid_val = row_obj.get('moca_oid', None)
    moca_oid = int(_moca_oid_val) if (_moca_oid_val is not None and not pd.isna(_moca_oid_val)) else None
    _instid_val = row_obj.get('moca_instid', None)
    moca_instid = None if (_instid_val is None or pd.isna(_instid_val)) else _instid_val
    _obj_desig_val = row_obj.get('designation', None)
    object_designation = None if (_obj_desig_val is None or pd.isna(_obj_desig_val)) else _obj_desig_val
    grid_df = pd.read_json(grid_data_json, orient='split')
    grid_row = grid_df[grid_df['grid'] == selected_grid].iloc[0].to_dict()
    moca_sptgridhid = int(grid_row.get('moca_sptgridhid')) if grid_row.get('moca_sptgridhid') is not None else None
    gravity_class = _infer_gravity_class(grid_row)
    spectral_class, inferred_suffix = _parse_spectral_class_and_suffix(spt)
    suffix = inferred_suffix if inferred_suffix in ('d/sd', 'sd', 'esd') else None
    if gravity_class not in ('β', 'γ', 'δ'):
        gravity_class = None
    max_wv = float(pd.to_numeric(comp_df['wv'], errors='coerce').max())
    wavelength_regime = 'visible' if (np.isfinite(max_wv) and max_wv < 0.8) else 'near_infrared'
    is_bd = False
    if sptn is not None:
        if sptn >= 10:
            is_bd = True
        elif sptn >= 6 and gravity_class in ('β', 'γ', 'δ'):
            is_bd = True
    object_type = 'brown dwarf' if is_bd else None
    der = ('deredden' in (deredden_value or []))
    std_descr = f"{entry.get('designation','Unknown')}"

    # Determine active normalization regions and formatted text
    local_norm_regions = [(float(a), float(b)) for (a, b) in (norm_regions_store or norm_regions)]
    norm_text = _format_norm_regions_text(local_norm_regions)

    # Format reddening values if available and dereddening is applied
    av_list = entry.get('A_V') or []
    rv_list = entry.get('R_V') or []

    def _fmt_list(vals):
        try:
            return ",".join([f"{v:.3f}" if (v is not None and np.isfinite(float(v))) else "nan" for v in vals])
        except Exception:
            return ""

    def _nanmedian(vals):
        try:
            arr = np.array([float(v) if v is not None else np.nan for v in vals], dtype=float)
            finite = arr[np.isfinite(arr)]
            return float(np.nanmedian(arr)) if finite.size > 0 else float('nan')
        except Exception:
            return float('nan')

    if der and (av_list or rv_list):
        av_med = _nanmedian(av_list)
        rv_med = _nanmedian(rv_list)
        av_str = _fmt_list(av_list)
        rv_str = _fmt_list(rv_list)
        comments = (
            f"Standard: {std_descr}; χ²={redchi2:.3f} ; dereddened=yes; "
            f"A(V)_med={av_med:.3f}; R(V)_med={rv_med:.3f}; "
            f"A(V)_bands=[{av_str}]; R(V)_bands=[{rv_str}]; "
            f"norm_regions={norm_text}"
        )
    else:
        comments = (
            f"Standard: {std_descr}; χ²={redchi2:.3f} ; dereddened={'yes' if der else 'no'}; "
            f"norm_regions={norm_text}"
        )

    origin = 'spectral_typing.py'
    adopted = 0
    adopt_asis = 0
    if n_clicks_adopt:
        adopted = 1
    if n_clicks_adopt:
        adopt_asis = 1

    # If the URL contains user=management, execute the SQL and show a concise result message
    try:
        parsed = urlparse(url_search) if url_search else None
        qs = parse_qs(parsed.query) if parsed else {}
        username_param = (qs.get('user', [env_username])[0] or '').strip().lower()
    except Exception:
        username_param = env_username

    if username_param == 'management':
        author = 'gagne'
    else:
        author = None

    def fv(val):
        if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
            return 'NULL'
        if isinstance(val, (int, float)):
            return str(val)
        s = str(val).replace('"', '\\"')
        return f'"{s}"'
    cols = [
        ('moca_oid', moca_oid),
        ('moca_specid', comp_specid),
        ('moca_instid', moca_instid),
        ('spectral_type', spt),
        ('moca_sptgridhid', moca_sptgridhid),
        ('spectral_standard_moca_specid', std_specid),
        ('spectral_type_number', sptn),
        ('spectral_type_unc', 0.5),
        ('quality_flag', 'B'),
        ('photometric_estimate', 0),
        ('spectral_class', spectral_class),
        ('gravity_class', gravity_class),
        ('suffix', suffix),
        ('simple_spectral_type', spt),
        ('complete_spectral_type', spt),
        ('wavelength_regime', wavelength_regime),
        ('adopted', adopted),
        ('ignored', 0),
        ('adopt_asis', adopt_asis),
        ('origin', origin),
        ('author', author),
        ('object_designation', object_designation),
        ('object_type', object_type),
        ('comments', comments)
    ]
    col_names = ", ".join([c for c, _ in cols])
    select_parts = ", ".join([f"{fv(v)} AS {c}" for c, v in cols])
    sql = f"INSERT INTO data_spectral_types ({col_names}) SELECT {select_parts};"

    if username_param == 'management':
        try:
            connection_string = get_connection_string_sptype(url_search=url_search)
            engine = create_engine(connection_string)
            with engine.begin() as conn:
                
                msg_suffix = ''
                if n_clicks_adopt and moca_oid is not None:
                    # First reset all adopted types for this object
                    update_stmt = text("UPDATE data_spectral_types SET adopted=0 WHERE adopted=1 AND moca_oid=:moca_oid")
                    conn.execute(update_stmt, {"moca_oid": moca_oid})
                    update_stmt2 = text("UPDATE data_spectral_types SET adopt_asis=0 WHERE adopt_asis=1 AND moca_oid=:moca_oid")
                    conn.execute(update_stmt2, {"moca_oid": moca_oid})
                    msg_suffix = ' and de-adopted other spectral types for this moca_oid'

                result = conn.execute(text(sql))
                affected = result.rowcount
            
            # Normalize message; some drivers return -1 when rowcount is unknown
            if affected is None or affected < 0:
                msg = 'Statement executed'
            else:
                plural = '' if affected == 1 else 's'
                msg = f'{affected} row{plural} added to data_spectral_types{msg_suffix}'
            return msg, {'display': 'block', 'marginTop': '10px'}
        except Exception as e:
            # Surface the error to the UI box
            return f'ERROR: {e}', {'display': 'block', 'marginTop': '10px'}

    return sql, {'display': 'block', 'marginTop': '10px'}

# =============================================================================
# Callback: Define spectral grid options and download grid spectra
# =============================================================================
@dash.callback(
    Output('sp-typing-grid-dropdown', 'options'),
    Output('sp-typing-grid-data', 'data'),
    Output('sp-typing-grid-raw-spectra', 'data'),
    Input('sp-typing-url', 'search'),
    State('sp-typing-grid-dropdown', 'options'),
    State('sp-typing-grid-data', 'data'),
    State('sp-typing-grid-raw-spectra', 'data'),
)
def grid_data_download(url_search, current_options, current_grid_data, current_grid_spectra):
    if debug_printing:
        print("Triggered grid data download callback")
    # If the dropdown options are empty (initial call) then run the update_spectral_grids logic.
    if not current_options or current_options == [] or not current_grid_data or not current_grid_spectra:
        if debug_printing:
            print("Downloading grid data")
        connection_string = get_connection_string_sptype(url_search=url_search)
        engine = create_engine(connection_string)
        # SQL Query to populate the dropdown options
        query_options = """
            SELECT
              dstg.moca_sptgridid AS grid,
              dstg.moca_sptgridhid,
              dstg.moca_specid,
              dstg.moca_oid,
              dstg.object_designation,
              dstg.comments,
              dstg.bibcode,
              dstg.spectral_type,
              dstg.spectral_type_number,
              dstg.short_object_designation AS designation,
              CONCAT(dstg.spectral_type,' (',dstg.short_object_designation,')') AS label,
              CASE WHEN mstg.moca_sptgridid='extremely low gravity' THEN 'δ'
                   WHEN mstg.moca_sptgridid='very low gravity' THEN 'γ'
                   WHEN mstg.moca_sptgridid='intermediate gravity' THEN 'β'
                   WHEN mstg.moca_sptgridid='field' THEN 'α'
                   ELSE NULL
              END AS gravity_class
            FROM data_spectral_typing_grids dstg
            JOIN moca_spectral_typing_grids mstg USING(moca_sptgridid)
            WHERE dstg.ignored=0
              AND mstg.ignored=0
              AND dstg.moca_specid IS NOT NULL
              AND COALESCE(dstg.is_public, 1) IN (0, 1)
              AND NOT EXISTS (
                    SELECT 1
                    FROM data_spectral_typing_grids dstg2
                    WHERE dstg2.ignored=0
                      AND dstg2.moca_specid IS NOT NULL
                      AND dstg2.moca_sptgridid = dstg.moca_sptgridid
                      AND dstg2.grid_index = dstg.grid_index
                      AND COALESCE(dstg2.is_public, 1) IN (0, 1)
                      AND COALESCE(dstg2.is_public, 1) < COALESCE(dstg.is_public, 1)
              )
            ORDER BY mstg.display_order, dstg.grid_index
        """
        df_options = pd.read_sql(query_options, engine)

        if df_options.empty:
            if debug_printing:
                print("Encountered empty standard grid header")
            return dash.no_update, dash.no_update, dash.no_update
        
        # SQL Query to download the standard grid of spectra
        query_std_data = """
            SELECT ds.moca_specid, ds.wavelength_angstrom * 1e-4 AS wv, ds.flux_flambda sp, ds.flux_flambda_unc esp
            FROM data_spectral_typing_grids dstg
            JOIN moca_spectral_typing_grids mstg USING(moca_sptgridid)
            JOIN data_spectra ds USING(moca_specid)
            WHERE dstg.ignored=0
              AND mstg.ignored=0
              AND dstg.moca_specid IS NOT NULL
              AND ds.ignored=0
              AND ds.flux_flambda IS NOT NULL
              AND ds.wavelength_angstrom IS NOT NULL
              AND COALESCE(dstg.is_public, 1) IN (0, 1)
              AND NOT EXISTS (
                    SELECT 1
                    FROM data_spectral_typing_grids dstg2
                    WHERE dstg2.ignored=0
                      AND dstg2.moca_specid IS NOT NULL
                      AND dstg2.moca_sptgridid = dstg.moca_sptgridid
                      AND dstg2.grid_index = dstg.grid_index
                      AND COALESCE(dstg2.is_public, 1) IN (0, 1)
                      AND COALESCE(dstg2.is_public, 1) < COALESCE(dstg.is_public, 1)
              )
        """
        df_std_data = pd.read_sql(query_std_data, engine)
        if df_std_data.empty:
            if debug_printing:
                print("Encountered empty standard grid spectra")
            return dash.no_update, dash.no_update, dash.no_update
        
        # Normalize esp and sp by the median of sp, grouped by moca_specid
        # This steps seems required to store the data properly
        if not df_std_data.empty and 'moca_specid' in df_std_data.columns and 'sp' in df_std_data.columns:
            df_std_data['sp_median'] = df_std_data.groupby('moca_specid')['sp'].transform('median')
            df_std_data['esp'] = df_std_data['esp'] / df_std_data['sp_median']
            df_std_data['sp'] = df_std_data['sp'] / df_std_data['sp_median']
            df_std_data.drop(columns='sp_median', inplace=True)
        
        if debug_printing:
            print ("Download of grid data completed")

        options = [{'label': label, 'value': grid} for grid, label in df_options[['grid', 'grid']].drop_duplicates().values]

        # Encode stored data
        grid_data = df_options.to_json(date_format='iso', orient='split')
        grid_spectra = df_std_data.to_json(date_format='iso', orient='split')
    else:
        if debug_printing:
            print("Grid data already in store")
        # Preserve grid_data as no change (or use dash.no_update)
        grid_data = dash.no_update
        grid_spectra = dash.no_update
        options = current_options
    
    return options, grid_data, grid_spectra

# =============================================================================
# Callback: Update spt grids controls
# =============================================================================
@dash.callback(
    Output('sp-typing-grid-dropdown', 'value'),
    Output('sp-typing-vertical-slider', 'min'),
    Output('sp-typing-vertical-slider', 'max'),
    Output('sp-typing-vertical-slider', 'marks'),
    Output('sp-typing-vertical-slider', 'value'),
    Output('sp-typing-prev-grid-button', 'disabled'),
    Output('sp-typing-next-grid-button', 'disabled'),
    Input('sp-typing-prev-grid-button', 'n_clicks'),
    Input('sp-typing-next-grid-button', 'n_clicks'),
    Input('sp-typing-vertical-slider', 'value'),
    Input('sp-typing-grid-dropdown', 'value'),
    Input('sp-typing-chi2-graph', 'clickData'),
    Input('sp-typing-grid-dropdown', 'options'),
    Input('sp-typing-grid-data', 'data'),
    Input('sp-typing-precomputed-store', 'data'),
    State('sp-typing-url', 'search'),
    prevent_initial_call=True
)
def grid_controls_callback(prev_click, next_click, slider_input, current_value, chi2_clickData, options, grid_data, precomputed, url_search):
    if debug_printing:
        print("grid_controls_callback triggered")
    # If the dropdown options are empty (initial call) then exit and wait for them to be populated
    if not options or options == [] or not grid_data:
        if debug_printing:
            print("grid_controls_callback: Skipping because data not ready")
        
        # Exit without changes
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        #return current_value, min_val, max_val, marks, slider_value, prev_disabled, next_disabled

    else:
        if debug_printing:
            print("grid_controls_callback: Updating the selected grid")
        # Set the default grid if none are set yet
        if not current_value:
            # Parse URL parameters for grid
            if url_search:
                parsed = urlparse(url_search)
                qs = parse_qs(parsed.query)
                grid = qs.get("grid", [None])[0]
            else:
                grid = None

            valid_grids = [str(opt['value']) for opt in options]
            current_value = grid if grid in valid_grids else ('field')

            # If no explicit grid in URL and we have precomputed data, pick the grid of the global min χ²
            if not grid and precomputed:
                try:
                    pre = pd.DataFrame(precomputed)
                    if 'reduced_chi2' in pre.columns and pre['reduced_chi2'].notna().any():
                        best_idx = int(pre['reduced_chi2'].astype(float).idxmin())
                        best_grid = str(pre.loc[best_idx, 'grid'])
                        if best_grid in [str(opt['value']) for opt in options]:
                            current_value = best_grid
                except Exception as _e:
                    if debug_printing:
                        print(f"grid_controls_callback: could not set grid from global min χ²: {_e}")
            if debug_printing:
                print(f"grid_controls_callback: initial grid set to '{current_value}'")

        # Initialize slider outputs based on the options.
        num_options = len(options)
        min_val = 0
        max_val = num_options - 1
        marks = {i: options[num_options - 1 - i]['label'] for i in range(num_options)}
        try:
            current_index = next(i for i, opt in enumerate(options) if opt['value'] == current_value)
        except StopIteration:
            current_index = 0
        slider_value = num_options - 1 - current_index

        ctx = dash.callback_context
        new_index = current_index
        if debug_printing:
            print('Max index value on this grid', max_val)
        if ctx.triggered:
            trigger_prop = ctx.triggered[0]['prop_id']
            if 'sp-typing-prev-grid-button' in trigger_prop:
                new_index = max(current_index - 1, 0)
                if debug_printing:
                    print('New index will be', new_index)
            elif 'sp-typing-next-grid-button' in trigger_prop:
                new_index = min(current_index + 1, max_val)
                if debug_printing:
                    print('New index will be', new_index)
            elif 'sp-typing-vertical-slider' in trigger_prop:
                new_index = num_options - 1 - slider_input
            elif 'sp-typing-chi2-graph' in trigger_prop:
                if chi2_clickData:
                    point = chi2_clickData.get('points', [{}])[0]
                    cd = point.get('customdata', None)
                    if cd and isinstance(cd, list) and len(cd) >= 2:
                        try:
                            new_index = next(i for i, opt in enumerate(options) if opt['value'] == cd[0])
                        except StopIteration:
                            new_index = current_index
        new_value = options[new_index]['value']
        slider_value = num_options - 1 - new_index

        prev_disabled = (new_index == 0)
        next_disabled = (new_index == num_options - 1)
        return new_value, min_val, max_val, marks, slider_value, prev_disabled, next_disabled


# =============================================================================
# Callback: Download the raw comparison spectrum
# =============================================================================
@dash.callback(
    Output('sp-typing-comparison-raw-spectrum', 'data'),
    Input('sp-typing-comparison-dropdown', 'value'), # If the user selects a new comparison spectrum we re-download it
    State('sp-typing-url', 'search'),
    prevent_initial_call = True
)
def download_comparison_spectrum(comparison_specid, url_search):
    if debug_printing:
        print('download_comparison_spectrum callback being triggered')
    if not comparison_specid:
        return dash.no_update
    if debug_printing:
        print('download_comparison_spectrum callback being executed')
    
    # Download the comparison spectrum
    connection_string = get_connection_string_sptype(url_search=url_search)
    engine = create_engine(connection_string)
    
    # Fetch spectrum from MOCAdb
    comparison_query = f"""
        SELECT ds.moca_specid,
            ds.wavelength_angstrom * 1e-4 AS wv,
            ds.flux_flambda AS sp,
            ds.flux_flambda_unc AS esp
        FROM moca_spectra ms
        JOIN data_spectra ds ON (ds.moca_specid = ms.moca_specid AND ds.ignored = 0)
        WHERE ds.moca_specid = {comparison_specid}
    """

    comparison_df = pd.read_sql(comparison_query, engine)
    if comparison_df.empty:
        return dash.no_update

    # Normalize esp and sp by the median of sp
    # This steps seems required to store the data properly
    if not comparison_df.empty and 'sp' in comparison_df.columns:
        comparison_df['esp'] = comparison_df['esp'] / np.nanmedian(comparison_df['sp'])
        comparison_df['sp'] = comparison_df['sp'] / np.nanmedian(comparison_df['sp'])

    comparison_data = comparison_df.to_json(date_format='iso', orient='split')
    if debug_printing:
        print('download_comparison_spectrum completed')
    return comparison_data
    
# =============================================================================
# Callback: Precompute comparisons (all standards in grid)
# =============================================================================
# Friday: This now needs to be triggered only when a new comparison spectrum is selected, or the raw grid spectra are read
@dash.callback(
    Output('sp-typing-precomputed-store', 'data'),
    Output('sp-typing-comparison-spectrum', 'data'),
    #State('sp-typing-grid-dropdown', 'value'),
    Input('sp-typing-comparison-raw-spectrum', 'data'), # If a new comparison spectrum gets downloaded we re-bin all spectra
    Input('sp-typing-bins-input', 'value'), # If the user selects a different binning we re-bin all spectra
    Input('sp-typing-deredden-checklist', 'value'), # If the deredden option changes we re-bin all spectra
    Input('sp-typing-grid-raw-spectra', 'data'), # If the grid raw spectra gets updated we also re-bin all spectra
    Input('sp-typing-norm-regions-store', 'data'),
    State('sp-typing-grid-data', 'data'), # This encodes the list of standard spectra and their header properties
    #State('sp-typing-url', 'search'),
    prevent_initial_call = True
)
def precompute_comparisons(comparison_raw_spectrum, bins_per_micron, deredden_value, grid_raw_spectra, norm_regions_store, grid_data):
    if debug_printing:
        print('precompute_comparisons callback being triggered')
    if not comparison_raw_spectrum or not grid_raw_spectra:
        return dash.no_update, dash.no_update
    if debug_printing:
        print('precompute_comparisons callback being executed')
    
    bins = bins_per_micron if bins_per_micron is not None else default_bins_per_micron
    deredden = 'deredden' in (deredden_value or [])
    local_norm_regions = [(float(a), float(b)) for (a, b) in (norm_regions_store or norm_regions)]

    # Read the comparison spectrum and the grid spectra
    comparison_df_raw = pd.read_json(comparison_raw_spectrum, orient='split')
    grid_df_raw = pd.read_json(grid_raw_spectra, orient='split')
    if 'wv' not in comparison_df_raw.columns or 'wv' not in grid_df_raw.columns or 'sp' not in comparison_df_raw.columns or 'sp' not in grid_df_raw.columns:
        if debug_printing:
            print("precompute_comparisons: Exiting because encountered empty spectra")
        return dash.no_update, dash.no_update

    # Bin comparison spectrum
    comparison_df = process_spectrum(comparison_df_raw, bins_per_micron=bins, norm_regions_param=local_norm_regions)
    comparison_df['esp_calc'] = _prepare_errors_for_metrics(
        comparison_df['spn'].values,
        comparison_df['esp'].values if 'esp' in comparison_df.columns else None
    )
    
    # Define a wavelength grid on which to bin the standard spectral grid
    common_wv = np.sort(comparison_df['wv'].unique())

    # Encore the processed comparison spectrum for DCC Store
    comparison_json = comparison_df.to_dict('records')

    # grid_df is essentially the header of the standard spectra
    grid_df = pd.read_json(grid_data, orient='split')

    # Bin and normalize the standard spectra
    
    results = []
    grid_entries = grid_df
    for _, row in grid_entries.iterrows():
        std_specid = row['moca_specid']
        std_label = row['label']
        std_spt = row['spectral_type']
        std_spt_number = row['spectral_type_number']
        std_designation = row['designation']
        std_object_designation = row.get('object_designation', None)
        std_comments = row.get('comments', None)
        std_bibcode = row.get('bibcode', None)
        if debug_printing:
            print(std_specid)
        
        # Select the current standard spectrum on the grid
        std_df_raw = grid_df_raw[grid_df_raw['moca_specid'] == std_specid]

        if std_df_raw['sp'].sum() == 0:
            print("Encountered an all-zero spectrum")
            continue

        # Rebin the standard spectrum on the common wavelength grid
        if debug_printing:
            print('Rebinning standard spectrum...')
        std_df = process_spectrum(std_df_raw, common_wv=common_wv, norm_regions_param=local_norm_regions)
        std_df['esp_calc'] = _prepare_errors_for_metrics(
            std_df['spn'].values,
            std_df['esp'].values if 'esp' in std_df.columns else None
        )
        if debug_printing:
            print('Rebinning complete')
        std_data_dered = None
        std_data = None

        if 'wv' not in std_df.columns:
            continue
            #import pdb; pdb.set_trace()

        # Normalize the standard spectrum using the median ratio (comparison / standard), per region.
        if debug_printing:
            print('Normalizing standard spectrum...')
        for (region_min, region_max) in local_norm_regions:
            std_seg = std_df[(std_df['wv'] >= region_min) & (std_df['wv'] <= region_max)]
            comp_seg = comparison_df[(comparison_df['wv'] >= region_min) & (comparison_df['wv'] <= region_max)]
            if not std_seg.empty and not comp_seg.empty:
                valid = (
                    np.isfinite(comp_seg['spn'].values) &
                    np.isfinite(std_seg['spn'].values) &
                    np.isfinite(comp_seg['esp_calc'].values) & (comp_seg['esp_calc'].values > 0) &
                    np.isfinite(std_seg['esp_calc'].values) & (std_seg['esp_calc'].values > 0)
                )
                if np.sum(valid) > 0:
                    ratio = _weighted_scale_chi2_minimization(
                        comp_seg['wv'].values[valid],
                        comp_seg['spn'].values[valid],
                        comp_seg['esp_calc'].values[valid],
                        std_seg['wv'].values[valid],
                        std_seg['spn'].values[valid],
                        std_seg['esp_calc'].values[valid],
                    )
                    if np.isfinite(ratio):
                        # Normalize the original standard spectrum
                        mask_region = (std_df['wv'] >= region_min) & (std_df['wv'] <= region_max)
                        std_df.loc[mask_region, 'spn'] *= ratio
                        std_df.loc[mask_region, 'esp'] *= ratio
                        std_df.loc[mask_region, 'esp_calc'] *= ratio
        if debug_printing:
            print('Normalizing complete')

        if deredden and (not comparison_df.empty) and (not std_df.empty):
            try:
                if debug_printing:
                    print("Optimizing dereddening values for " + std_label+" ...")
                av_list = []
                rv_list = []
                std_df_dered = std_df.copy()
                # Optimize A(V) and R(V) for each normalization region individually
                for band_index, (region_min, region_max) in enumerate(local_norm_regions, start=1):
                    std_seg = std_df[(std_df['wv'] >= region_min) & (std_df['wv'] <= region_max)]
                    comp_seg = comparison_df[(comparison_df['wv'] >= region_min) & (comparison_df['wv'] <= region_max)]
                    if not std_seg.empty and not comp_seg.empty:
                        # Interpolate std_seg onto the wavelengths of comp_seg
                        common_wv_seg = comp_seg['wv'].values
                        interp_spn = np.interp(common_wv_seg, std_seg['wv'].values, std_seg['spn'].values, left=np.nan, right=np.nan)
                        std_seg_interp = pd.DataFrame({'wv': common_wv_seg, 'spn': interp_spn})
                        # Create a mask to include only finite (non-NaN, non-infinite) values in both spectra
                        mask = np.isfinite(std_seg_interp['spn'].values) & np.isfinite(comp_seg['spn'].values)
                        if np.sum(mask) == 0:
                            A_V_i, R_V_i = (np.nan, np.nan)
                        else:
                            std_seg_valid = std_seg_interp[mask]
                            comp_seg_valid = comp_seg[mask]
                            A_V_i, R_V_i = optimize_A_V_R_V(std_seg_valid[['wv', 'spn']], comp_seg_valid[['wv', 'spn']])
                        av_list.append(A_V_i)
                        rv_list.append(R_V_i)
                        # Apply de-reddening for this region and update the corresponding part in std_df_dered
                        dereddened_seg = deredden_spectrum(std_seg[['wv', 'spn']], A_V_i, R_V_i)
                        std_df_dered.loc[(std_df_dered['wv'] >= region_min) & (std_df_dered['wv'] <= region_max), 'spn'] = dereddened_seg['spn']
                    else:
                        av_list.append(np.nan)
                        rv_list.append(np.nan)
                if debug_printing:
                    print('Optimizing complete')
                
                std_df_dered['esp_calc'] = _prepare_errors_for_metrics(
                    std_df_dered['spn'].values,
                    std_df_dered['esp'].values if 'esp' in std_df_dered.columns else None
                )

                # Normalize the dereddened standard spectrum using the median ratio (comparison / standard), per region.
                if debug_printing:
                    print('Normalizing dereddened standard spectrum...')
                for (region_min, region_max) in local_norm_regions:
                    std_seg_dered = std_df_dered[(std_df_dered['wv'] >= region_min) & (std_df_dered['wv'] <= region_max)]
                    comp_seg = comparison_df[(comparison_df['wv'] >= region_min) & (comparison_df['wv'] <= region_max)]
                    if not std_seg_dered.empty and not comp_seg.empty:
                        valid = (
                            np.isfinite(comp_seg['spn'].values) &
                            np.isfinite(std_seg_dered['spn'].values) &
                            np.isfinite(comp_seg['esp_calc'].values) & (comp_seg['esp_calc'].values > 0) &
                            np.isfinite(std_seg_dered['esp_calc'].values) & (std_seg_dered['esp_calc'].values > 0)
                        )
                        if np.sum(valid) > 0:
                            ratio = _weighted_scale_chi2_minimization(
                                comp_seg['wv'].values[valid],
                                comp_seg['spn'].values[valid],
                                comp_seg['esp_calc'].values[valid],
                                std_seg_dered['wv'].values[valid],
                                std_seg_dered['spn'].values[valid],
                                std_seg_dered['esp_calc'].values[valid],
                            )
                            if np.isfinite(ratio):
                                # Normalize the original standard spectrum
                                mask_region = (std_df_dered['wv'] >= region_min) & (std_df_dered['wv'] <= region_max)
                                std_df_dered.loc[mask_region, 'spn'] *= ratio
                                std_df_dered.loc[mask_region, 'esp'] *= ratio
                                std_df_dered.loc[mask_region, 'esp_calc'] *= ratio
                if debug_printing:
                    print('Normalizing complete...')

                # # --- Debugging Block: Plot original vs. dereddened segment ---
                # import plotly.graph_objects as go
                # import plotly.io as pio
                # pio.renderers.default = "browser"
                
                # fig_debug = go.Figure()
                # fig_debug.add_trace(go.Scatter(
                #     x=std_df['wv'],
                #     y=std_df['spn'],
                #     mode='lines+markers',
                #     name='Original Spectrum',
                #     line=dict(color='blue')
                # ))
                # fig_debug.add_trace(go.Scatter(
                #     x=std_df_dered['wv'],
                #     y=std_df_dered['spn'],
                #     mode='lines+markers',
                #     name='Dereddened Spectrum',
                #     line=dict(color='red')
                # ))
                # fig_debug.update_layout(title="Debug: Original vs. Dereddened")
                # fig_debug.show()
                
                # import pdb; pdb.set_trace()
                # # --- End Debugging Block ---
                if debug_printing:
                    print("Encoding standard spectrum to dictionary")
                std_data = std_df.to_dict('records')  # original spectrum data stored for reference
                std_data_dered = std_df_dered.to_dict('records')  # de-reddened spectrum stored for use
                std_df = std_df_dered  # use the de-reddened dataframe for chi2 calculations
            except Exception as e:
                if debug_printing:
                    print("An exception has occurred while optimizing dereddening")
                av_list = [np.nan] * len(local_norm_regions)
                rv_list = [np.nan] * len(local_norm_regions)
                std_data = std_df.to_dict('records')
        else:
            av_list = [np.nan] * len(local_norm_regions)
            rv_list = [np.nan] * len(local_norm_regions)
            std_data = std_df.to_dict('records')
        
        if (not comparison_df.empty) and (not std_df.empty):
            residual_list = []
            for (region_min, region_max) in local_norm_regions:
                comp_seg = comparison_df[(comparison_df['wv'] >= region_min) & (comparison_df['wv'] <= region_max)]
                std_seg = std_df[(std_df['wv'] >= region_min) & (std_df['wv'] <= region_max)]
                if not comp_seg.empty and not std_seg.empty:
                    interp_std = np.interp(comp_seg['wv'], std_seg['wv'], std_seg['spn'], left=np.nan, right=np.nan)
                    diff = comp_seg['spn'] - interp_std
                    valid = diff[~np.isnan(diff)]
                    if not valid.empty:
                        residual_list.append(valid)
            if residual_list:
                n_bands = len(local_norm_regions)
                all_residuals = np.concatenate([r.to_numpy() for r in residual_list])
                N = len(all_residuals)
                p = 3*n_bands if deredden else n_bands
                dof = N - p if N > p else N
                reduced_chi2 = 1e3 * np.sum(all_residuals**2) / dof if dof > 0 else np.nan
                mad = 1e3 * np.median(np.abs(all_residuals))
            else:
                reduced_chi2 = np.nan
                mad = np.nan
        else:
            reduced_chi2 = np.nan
            mad = np.nan

        # # --- Debugging Block: Plot original vs. dereddened segment ---
        # import plotly.graph_objects as go
        # import plotly.io as pio
        # pio.renderers.default = "browser"
        
        # fig_debug = go.Figure()
        # fig_debug.add_trace(go.Scatter(
        #     x=[row['wv'] for row in std_data],
        #     y=[row['spn'] for row in std_data],
        #     mode='lines+markers',
        #     name='Original Spectrum',
        #     line=dict(color='blue')
        # ))
        # fig_debug.add_trace(go.Scatter(
        #     x=[row['wv'] for row in std_data_dered],
        #     y=[row['spn'] for row in std_data_dered],
        #     mode='lines+markers',
        #     name='Dereddened Spectrum',
        #     line=dict(color='red')
        # ))
        # fig_debug.update_layout(title="Debug: Original vs. Dereddened")
        # fig_debug.show()
        
        # import pdb; pdb.set_trace()
        # # --- End Debugging Block ---
        if debug_printing:
            print("Storing standard spectrum")
        results.append({
            'grid': row["grid"],
            'moca_specid': std_specid,
            'label': std_label,
            'spectral_type': std_spt,
            'spectral_type_number': std_spt_number,
            'designation': std_designation,
            'object_designation': std_object_designation,
            'comments': std_comments,
            'bibcode': std_bibcode,
            'spectrum': std_data,
            'spectrum_dered': std_data_dered,
            'A_V': av_list,
            'R_V': rv_list,
            'reduced_chi2': reduced_chi2,
            'mad': mad
        })
    return results, comparison_json

# =============================================================================
# Callback: Navigation and graph update (using Prev/Next buttons)
# =============================================================================
@dash.callback(
    Output('sp-typing-lowres-checklist', 'options'),
    Output('sp-typing-lowres-checklist', 'value'),
    Output('sp-typing-lowres-checklist', 'style'),
    Input('sp-typing-comparison-raw-spectrum', 'data'),
    State('sp-typing-lowres-checklist', 'value'),
)
def update_lowres_mode_checkbox(comparison_raw_spectrum, current_values):
    has_lowres = False
    if comparison_raw_spectrum:
        try:
            comparison_df_raw = pd.read_json(comparison_raw_spectrum, orient='split')
            avg_r = average_resolving_power(comparison_df_raw.get('wv', pd.Series(dtype=float)).values)
            has_lowres = np.isfinite(avg_r) and avg_r < 100.0
        except Exception:
            has_lowres = False

    options = [{
        'label': 'Deactivate low-resolution display mode',
        'value': 'disable_lowres',
        'disabled': not has_lowres
    }]

    if has_lowres:
        return options, (current_values or []), {}
    return options, [], {'color': '#9aa0a6'}

# =============================================================================
# Callback: Navigation and graph update (using Prev/Next buttons)
# =============================================================================
@dash.callback(
    Output('sp-typing-current-sptnum', 'data'),
    Output('sp-typing-current-index', 'data'),
    Output('sp-typing-index-slider', 'value'),
    Output('sp-typing-index-slider', 'max'),
    Output('sp-typing-index-slider', 'marks'),
    Output('sp-typing-graph', 'figure'),
    Output('sp-typing-graph', 'config'),
    Output('sp-typing-standard-meta', 'children'),
    Output('sp-typing-prev-button', 'disabled'),
    Output('sp-typing-next-button', 'disabled'),
    Input('sp-typing-prev-button', 'n_clicks'),
    Input('sp-typing-next-button', 'n_clicks'),
    Input('sp-typing-index-slider', 'value'),
    Input('sp-typing-comparison-spectrum', 'data'),
    Input('sp-typing-grid-dropdown', 'value'),
    Input('sp-typing-comparison-designation', 'data'),
    Input('sp-typing-chi2-graph', 'clickData'),
    Input('sp-typing-norm-regions-store', 'data'),
    Input('sp-typing-showfeatures-checklist', 'value'),
    Input('sp-typing-lowres-checklist', 'value'),
    State('sp-typing-current-sptnum', 'data'),
    State('sp-typing-current-index', 'data'),
    State('sp-typing-precomputed-store', 'data'),
    State('sp-typing-deredden-checklist', 'value'),
    State('sp-typing-allred-checklist', 'value'),
    State('sp-typing-db-data', 'data'),
    State('sp-typing-comparison-raw-spectrum', 'data'),
    State('sp-typing-url', 'search')
)
def update_graph(prev_clicks, next_clicks, slider_value, comparison_data, selected_grid, comparison_designation, chi2_clickData, norm_regions_store, showfeatures_value, lowres_value, previous_sptnum, current_index, precomputed, deredden_value, allred_value, df_data, comparison_raw_spectrum, url_search):
    if debug_printing:
        print("Update graph was triggered with sptnum state value:", previous_sptnum)
    ctx = callback_context
    if not precomputed or comparison_data is None:
        if debug_printing:
            print("Update graph encountered empty data frames")
        empty_fig = go.Figure()
        empty_fig.update_layout(
            xaxis={'visible': False},
            yaxis={'visible': False},
            annotations=[
                {
                    'text': 'Select a comparison spectrum',
                    'xref': 'paper',
                    'yref': 'paper',
                    'x': 0.5,
                    'y': 0.5,
                    'showarrow': False,
                    'font': {'size': 20}
                }
            ]
        )
        prev_disabled = True
        next_disabled = True
        return dash.no_update, current_index, slider_value, 0, {0: ''}, empty_fig, figure_export_config, [], prev_disabled, next_disabled

    filtered_precomputed = [entry for entry in precomputed if entry['grid'] == selected_grid]

    allred = 'allred' in (allred_value or [])
    # Print selected grid, best (effective) χ², and the spectral type at the raw smallest χ² on that grid
    try:
        chi_vals = np.array([entry.get('reduced_chi2', np.nan) for entry in filtered_precomputed], dtype=float)
        finite = chi_vals[np.isfinite(chi_vals)]
        finite = finite[np.argsort(finite)]  # sorted copy
        if finite.size >= 2:
            effective_min = float(finite[1]) / 5.0
        elif finite.size == 1:
            effective_min = float(finite[0])
        else:
            effective_min = float('nan')
        # Identify the raw minimum on this grid to report its spectral type
        if np.any(np.isfinite(chi_vals)):
            raw_min_idx = int(np.nanargmin(chi_vals))
            raw_min_entry = filtered_precomputed[raw_min_idx]
            raw_min_val = float(chi_vals[raw_min_idx])
            raw_min_spt = raw_min_entry.get('spectral_type', 'N/A')
            raw_min_des = raw_min_entry.get('designation', 'N/A')
            raw_min_specid = raw_min_entry.get('moca_specid', 'N/A')
            print(
                f"[Spectral Typing] Selected grid: {selected_grid} | Smallest χ² (effective): {effective_min:.6g} | "
                f"Best entry: {raw_min_spt} ({raw_min_des}, specid={raw_min_specid}) with raw χ²={raw_min_val:.6g}"
            )
        else:
            print(f"[Spectral Typing] Selected grid: {selected_grid} | Smallest χ² (effective): {effective_min:.6g} | Best entry: none (no finite χ²)")
    except Exception as _e:
        print(f"[Spectral Typing] Could not compute effective χ² for grid {selected_grid}: {_e}")
    local_norm_regions = [(float(a), float(b)) for (a, b) in (norm_regions_store or norm_regions)]
    showfeatures = 'showfeatures' in (showfeatures_value or [])
    lowres_auto = False
    if comparison_raw_spectrum:
        try:
            comparison_df_raw = pd.read_json(comparison_raw_spectrum, orient='split')
            avg_r = average_resolving_power(comparison_df_raw.get('wv', pd.Series(dtype=float)).values)
            lowres_auto = np.isfinite(avg_r) and avg_r < 100.0
        except Exception:
            lowres_auto = False
    force_disable_lowres = 'disable_lowres' in (lowres_value or [])
    lowres = lowres_auto and (not force_disable_lowres)
    
    triggered_ids = [t['prop_id'].split('.')[0] for t in ctx.triggered]
    if 'sp-typing-chi2-graph' in triggered_ids and chi2_clickData:
        # Expect the clicked point's customdata to be [grid, index]
        point = chi2_clickData.get('points', [{}])[0]
        cd = point.get('customdata', None)
        if cd and isinstance(cd, list) and len(cd) >= 2:
            clicked_grid, clicked_index = cd[0], cd[1]
            selected_grid = clicked_grid
            new_index = clicked_index
        else:
            new_index = current_index
    elif 'sp-typing-index-slider' in triggered_ids and slider_value is not None:
        new_index = slider_value
    elif 'sp-typing-prev-button' in triggered_ids:
        new_index = max(current_index - 1, 0)
    elif 'sp-typing-next-button' in triggered_ids:
        new_index = min(current_index + 1, len(filtered_precomputed) - 1)
    elif 'sp-typing-grid-dropdown' in triggered_ids and previous_sptnum is not None:
        # Try to find the closest spectral_type_number in the new grid
        #import pdb; pdb.set_trace()
        if debug_printing:
            print("Attempting to match grid index for spectral type number:", previous_sptnum)
        try:
            new_index = min(
                range(len(filtered_precomputed)),
                key=lambda i: abs(filtered_precomputed[i].get('spectral_type_number', 0) - previous_sptnum)
            )
        except Exception:
            new_index = current_index
    elif 'sp-typing-comparison-spectrum' in triggered_ids:
        # On first plotting after a comparison spectrum is selected:
        # If the URL provides ?grid_index=..., honor it. Otherwise, start at the
        # grid point with the smallest reduced χ² within the current grid.
        parsed = urlparse(url_search) if url_search else None
        grid_index_param = None
        if parsed:
            qs = parse_qs(parsed.query)
            grid_index_param = qs.get("grid_index", [None])[0]

        if grid_index_param is not None:
            try:
                # Honor explicit within-grid index if user provided it
                new_index = int(grid_index_param)
            except ValueError:
                # Fallback: choose the smallest χ² WITHIN THE CURRENT GRID
                chi2_values = np.array([e.get('reduced_chi2', np.nan) for e in filtered_precomputed], dtype=float)
                if np.all(np.isnan(chi2_values)):
                    new_index = len(filtered_precomputed) // 2
                else:
                    new_index = int(np.nanargmin(chi2_values))
        else:
            # Default when first plotting: if no index param, choose the smallest χ² within the current grid
            chi2_values = np.array([e.get('reduced_chi2', np.nan) for e in filtered_precomputed], dtype=float)
            if np.all(np.isnan(chi2_values)):
                new_index = len(filtered_precomputed) // 2
            else:
                new_index = int(np.nanargmin(chi2_values))
    else:
        new_index = current_index
    
    # Make sure we are not falling out of range
    if new_index >= len(filtered_precomputed):
        new_index = len(filtered_precomputed) - 1
    if new_index < 0:
        new_index = 0

    # Convert stored spectra back to DataFrames
    std_entry = filtered_precomputed[new_index]
    std_df = pd.DataFrame(std_entry['spectrum'])
    comparison_df = pd.DataFrame(comparison_data)
    fig = go.Figure()
    
    # Compute custom colors for the standard spectra
    custom_colors = ['#E41A1C', '#377EB8', '#4DAF4A', '#984EA3', '#FF7F00', '#FFFF33', '#A65628', '#F781BF']
    standard_color = '#E41A1C' if allred else custom_colors[new_index % len(custom_colors)]

    # Prepare comparison metadata early (used for low-res overlay and title)
    comp_id = comparison_df['moca_specid'].iloc[0]
    df_data_parsed = pd.read_json(df_data, orient='split')
    comp_designation_row = df_data_parsed[df_data_parsed["moca_specid"] == comp_id]
    comp_designation = comp_designation_row["designation"].iloc[0] if not comp_designation_row.empty else "Unknown"
    comp_specid_tag = f" (specid={int(comp_id)})" if not comp_designation_row.empty else ""
    moca_oid_val = comp_designation_row['moca_oid'].iloc[0] if not comp_designation_row.empty else None
    if moca_oid_val is not None and not pd.isna(moca_oid_val):
        comp_oid_tag = f" (oid={int(moca_oid_val)})"
    else:
        comp_oid_tag = ""

    # For each normalization region, add a step trace for the Standard Spectrum (not dereddened) first
    standard_label = std_entry['spectral_type']+' ('+std_entry['designation']+')'
    standard_short_label = std_entry['spectral_type']
    std_object_designation = std_entry.get('object_designation', None)
    std_comments = std_entry.get('comments', None)
    std_bibcode = std_entry.get('bibcode', None)
    if 'deredden' in (deredden_value or []):
        name = "Std. " + standard_short_label + ", original"
        opacity = 0.3
    else:
        name = "Std. " + standard_short_label
        opacity = 1.0
    for i, (region_min, region_max) in enumerate(local_norm_regions):
        std_seg = std_df[(std_df['wv'] >= region_min) & (std_df['wv'] <= region_max)]
        if not std_seg.empty:
            fig.add_trace(go.Scatter(
                x=std_seg['wv'],
                y=std_seg['spn'],
                mode='lines',
                line=dict(shape='hv', width=4, color=standard_color),
                opacity=opacity,
                name=name if i == 0 else "",
                showlegend=(i == 0),
                legendgroup="standard-original"
            ))
    
    # For each normalization region, add a step trace for the dereddened Standard Spectrum next (if the option is selected)
    if 'deredden' in (deredden_value or []):
        std_df_dered = pd.DataFrame(std_entry['spectrum_dered'])

        # # --- Debugging Block: Plot original vs. dereddened segment ---
        # import plotly.graph_objects as godebug
        # import plotly.io as pio
        # pio.renderers.default = "browser"
        
        # fig_debug = godebug.Figure()
        # fig_debug.add_trace(godebug.Scatter(
        #     x=std_df['wv'],
        #     y=std_df['spn'],
        #     mode='lines+markers',
        #     name='Original Spectrum',
        #     line=dict(color='blue')
        # ))
        # fig_debug.add_trace(godebug.Scatter(
        #     x=std_df_dered['wv'],
        #     y=std_df_dered['spn'],
        #     mode='lines+markers',
        #     name='Dereddened Spectrum',
        #     line=dict(color='red')
        # ))
        # fig_debug.update_layout(title="Debug: Original vs. Dereddened")
        # fig_debug.show()
        
        # import pdb; pdb.set_trace()

        for i, (region_min, region_max) in enumerate(local_norm_regions):
            std_seg_dered = std_df_dered[(std_df_dered['wv'] >= region_min) & (std_df_dered['wv'] <= region_max)]
            if not std_seg_dered.empty:
                fig.add_trace(go.Scatter(
                    x=std_seg_dered['wv'],
                    y=std_seg_dered['spn'],
                    mode='lines',
                    line=dict(shape='hv', width=4, color=standard_color),
                    opacity=1.0,
                    name="Std. " + standard_short_label + ", dereddened" if i == 0 else "",
                    showlegend=(i == 0),
                    legendgroup="standard-dereddened"
                ))
    # Low-resolution comparison view: markers + error bars on top of the standards
    if lowres and not comparison_df.empty:
        esp_col = "espn" if "espn" in comparison_df.columns else ("esp" if "esp" in comparison_df.columns else None)
        fig.add_trace(go.Scatter(
            x=comparison_df['wv'],
            y=comparison_df['spn'],
            mode='markers',
            marker=dict(
                size=9.1,
                color='white',
                line=dict(color='black', width=2)
            ),
            error_y=dict(
                type='data',
                array=comparison_df[esp_col] if esp_col else None,
                color='rgba(120,120,120,0.9)',
                thickness=2,
                width=0
            ) if esp_col else None,
            name="Comparison (low-res)",
            showlegend=True,
            legendgroup="comparison",
            opacity=1.0
        ))
    
    # For each normalization region, add a step trace for the Comparison Spectrum on top (histogram mode)
    if not lowres:
        for i, (region_min, region_max) in enumerate(local_norm_regions):
            comp_seg = comparison_df[(comparison_df['wv'] >= region_min) & (comparison_df['wv'] <= region_max)]
            if not comp_seg.empty:
                fig.add_trace(go.Scatter(
                    x=comp_seg['wv'],
                    y=comp_seg['spn'],
                    mode='lines',
                    line=dict(shape='hv', width=4, color='black'),
                    name=("Comparison") if i == 0 else "",
                    showlegend=(i == 0),
                    opacity=0.8,
                    legendgroup="comparison"
                ))
    title_text = f"{comp_designation} {comp_specid_tag} {comp_oid_tag} vs {standard_label}, {selected_grid} grid"

    y_min_values = []
    y_max_values = []
    quantile_low = 0.2
    quantile_high = 0.7
    if precomputed:
        for entry in precomputed:
            df_entry = pd.DataFrame(entry['spectrum'])
            if not df_entry.empty:
                spn = df_entry['spn'].values.tolist()
                y_min_values.append(np.nanquantile(spn,quantile_low))
                y_max_values.append(np.nanquantile(spn,quantile_high))
    y_min_values = [np.nanquantile(y_min_values, quantile_low)]
    y_max_values = [np.nanquantile(y_max_values, quantile_high)]
    
    # Add currently displayed data
    if not std_df.empty:
        spn = std_df['spn'].values.tolist()
        y_min_values.append(np.nanmin(spn))
        y_max_values.append(np.nanmax(spn))
    if not comparison_df.empty:
        spn = comparison_df['spn'].values.tolist()
        y_min_values.append(np.nanmin(spn))
        y_max_values.append(np.nanmax(spn))
    if 'deredden' in (deredden_value or []):
        std_df_dered = pd.DataFrame(std_entry['spectrum_dered'])
        if not std_df_dered.empty:
            spn = std_df_dered['spn'].values.tolist()
            y_min_values.append(np.nanmin(spn))
            y_max_values.append(np.nanmax(spn))

    if y_min_values:
        y_min = np.nanmin(y_min_values)
    else:
        y_min = 0
    
    if y_max_values:
        y_max = np.nanmax(y_max_values)
    else:
        y_max = 1

    global_wv = []
    for entry in precomputed:
        df_entry = pd.DataFrame(entry['spectrum'])
        if not df_entry.empty:
            global_wv.extend(df_entry['wv'].values.tolist())
    if not comparison_df.empty:
        global_wv.extend(comparison_df['wv'].values.tolist())
    x_min = np.nanmin(global_wv)
    x_max = np.nanmax(global_wv)
    
    y_margin = 0.05 * (y_max - y_min)
    x_margin = 0.015 * (x_max - x_min)

    # Subtle background features (VO, FeH, H₂O, Na, K, CO)
    if showfeatures:
        _add_feature_bands(fig, ypad_frac=0.05)

    fig.update_layout(
        title=title_text,
        xaxis_title="Wavelength (µm)",
        yaxis_title="Normalized Flux",
        margin=dict(t=40),
        xaxis=dict(range=[x_min - x_margin, x_max + x_margin]),
        yaxis=dict(range=[y_min - y_margin, y_max + y_margin])
    )

    # Build standard metadata for separate div (below plots)
    meta_lines = []
    meta_lines.append(f"{std_entry.get('spectral_type', 'Standard')} standard:")
    meta_lines.append(f"Standard: {std_object_designation if std_object_designation else 'None'}")
    meta_lines.append(f"Comments: {std_comments if std_comments else 'None'}")
    # Bibcode handled as link below (if present)

    reduced_chi2 = std_entry.get("reduced_chi2", np.nan)
    #mad = std_entry.get("mad", np.nan)
    metrics_text = f"χ²: {reduced_chi2:.2f}"
    #metrics_text = f"χ²: {reduced_chi2:.2f}<br>MAD: {mad:.2f}"
    if 'deredden' in (deredden_value or []):
        if std_entry['A_V'] is not None and std_entry['R_V'] is not None:
            sub_map = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉"}
            for idx, (av, rv) in enumerate(zip(std_entry['A_V'], std_entry['R_V']), start=1):
                sub_idx = ''.join(sub_map[d] for d in str(idx))
                av_str = f"{av:.2f}" if av is not None and not np.isnan(av) else "N/A"
                rv_str = f"{rv:.2f}" if rv is not None and not np.isnan(rv) else "N/A"
                metrics_text += f"<br><br>A(V){sub_idx}: {av_str}<br>R(V){sub_idx}: {rv_str}"

    if 'deredden' in (deredden_value or []):
        annotation_y = 0.7
    else:
        annotation_y = 0.8

    fig.add_annotation(
        x=1.02, y=annotation_y, xref="paper", yref="paper",
        text=metrics_text,
        showarrow=False,
        align="left",
        bgcolor="white",
        xanchor="left",
        yanchor="top",
        font=dict(size=14)
    )
    slider_max = len(filtered_precomputed) - 1
    slider_marks = {
        i: {
            'label': filtered_precomputed[i]['spectral_type'].replace(' ','\u00A0')
        }
        for i in range(len(filtered_precomputed))
    }
    
    prev_disabled = (new_index == 0)
    next_disabled = (new_index == len(filtered_precomputed) - 1)
    current_sptnum = std_entry.get('spectral_type_number')
    if debug_printing:
        print("Storing sptnum", current_sptnum)
    
    #Update export file name
    der_tag = ""
    if 'deredden' in (deredden_value or []):
        der_tag = "_der"
    date_str = datetime.now().strftime("%y%m%d")
    updated_config = figure_export_config.copy()
    updated_config['toImageButtonOptions'] = updated_config['toImageButtonOptions'].copy()
    updated_config['toImageButtonOptions']['filename'] = f"sptype_specid_{int(comp_id)}_{std_entry['spectral_type']}_{selected_grid}{der_tag}_{date_str}"

    std_meta_children = []
    if meta_lines:
        std_meta_children = [html.Div(meta_lines[0], style={"fontWeight": "bold"})]
        for line in meta_lines[1:]:
            std_meta_children.append(html.Div(line))
    if std_bibcode:
        bib_url = f"https://ui.adsabs.harvard.edu/abs/{std_bibcode}/abstract"
        std_meta_children.append(
            html.Div([
                html.Span("Bibcode: "),
                html.A(std_bibcode, href=bib_url, target="_blank")
            ])
        )
    else:
        std_meta_children.append(html.Div("Bibcode: None"))

    return current_sptnum, new_index, new_index, slider_max, slider_marks, fig, updated_config, std_meta_children, prev_disabled, next_disabled

@dash.callback(
    Output("sp-typing-bins-input", "value"),
    Output("sp-typing-deredden-checklist", "value"),
    Input("sp-typing-url", "href"),
    #prevent_initial_call='initial_duplicate'
)
def spt_set_defaults_from_url(href):
    if not href:
        raise dash.exceptions.PreventUpdate
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    bins_val = qs.get("bins", [None])[0]
    try:
        bins_val = int(bins_val) if bins_val is not None else default_bins_per_micron
    except ValueError:
        bins_val = default_bins_per_micron
    dereddening = qs.get("deredden", [None])[0]
    deredden_list = ["deredden"] if dereddening and dereddening.lower() == "true" else []
    return bins_val, deredden_list


# --- Updated normalization regions callback to support ?norm=... in the URL ---
@dash.callback(
    Output('sp-typing-norm-regions-store', 'data'),
    Output('sp-typing-norm-regions-input', 'value'),
    Input('sp-typing-norm-regions-input', 'value'),
    Input('sp-typing-norm-reset', 'n_clicks'),
    Input('sp-typing-url', 'href')
)
def update_norm_regions_store(text_value, reset_clicks, href):
    ctx = callback_context

    # Helper to produce store+pretty text from a raw string
    def _parse_and_format(raw: str):
        parsed = parse_norm_regions(raw)
        pretty = _format_norm_regions_text(parsed) if parsed else DEFAULT_NORM_REGIONS_TEXT
        return parsed, pretty

    # On initial page load, prefer URL ?norm=... if provided; else defaults
    if not ctx.triggered:
        if href:
            parsed_url = urlparse(href)
            qs = parse_qs(parsed_url.query)
            norm_param = qs.get('norm', [None])[0]
            if norm_param:
                return _parse_and_format(norm_param)
        # Fallback to defaults
        parsed = parse_norm_regions(DEFAULT_NORM_REGIONS_TEXT)
        return parsed, DEFAULT_NORM_REGIONS_TEXT

    trigger = ctx.triggered[0]['prop_id']

    # Reset button: restore defaults
    if 'sp-typing-norm-reset' in trigger:
        parsed = parse_norm_regions(DEFAULT_NORM_REGIONS_TEXT)
        return parsed, DEFAULT_NORM_REGIONS_TEXT

    # URL changed: try to read ?norm=...; if absent, keep current text_value parsed
    if 'sp-typing-url' in trigger:
        if href:
            parsed_url = urlparse(href)
            qs = parse_qs(parsed_url.query)
            norm_param = qs.get('norm', [None])[0]
            if norm_param:
                return _parse_and_format(norm_param)
        # If no norm in URL, fall back to current text box content
        return _parse_and_format(text_value or DEFAULT_NORM_REGIONS_TEXT)

    # Default path: user typed in the textarea → parse it
    return _parse_and_format(text_value)

@dash.callback(
    Output('sp-typing-chi2-graph', 'figure'),
    Output('sp-typing-chi2-graph', 'config'),
    Input('sp-typing-precomputed-store', 'data'),
    Input('sp-typing-grid-data', 'data'),
    Input('sp-typing-grid-dropdown', 'value'),
    Input('sp-typing-current-index', 'data'),
    State('sp-typing-db-data', 'data'),
    State('sp-typing-comparison-dropdown', 'value')
)
def update_chi2_graph(precomputed_data, grid_data, selected_grid, current_index, df_data, specid):
    
    if precomputed_data is None or grid_data is None:
        return go.Figure(), figure_export_config
    df_pre = pd.DataFrame(precomputed_data)
    df_grid = pd.read_json(grid_data, orient='split')
    
    # Merge on moca_specid to get the spectral_type_number for each grid point
    #df_merged = pd.merge(df_pre, df_grid[['moca_specid', 'spectral_type_number']], on='moca_specid', how='left')
    df_pre_no_dup = df_pre.drop(columns=['spectral_type_number'], errors='ignore')
    df_merged = pd.merge(df_pre_no_dup, df_grid[['moca_specid', 'spectral_type_number']], on='moca_specid', how='left')

    fig = go.Figure()
    grids = df_merged['grid'].unique()
    #colors = ['#E41A1C', '#377EB8', '#4DAF4A', '#984EA3', '#FF7F00', '#FFFF33', '#A65628', '#F781BF']
    #colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
    #colors = ['#E41A1C', '#FF7F00', '#FFFF33', '#4DAF4A', '#984EA3', '#F781BF', '#A65628', '#999999']
    #colors = ['#E41A1C', '#FF7F00', '#FFFF33', '#FFD700', '#984EA3', '#F781BF', '#A65628', '#999999']
    #colors = ['#D9D9D9', '#BFBFBF', '#A6A6A6', '#8C8C8C', '#737373', '#595959', '#404040', '#262626']
    colors = ['#8DD3C7', '#FFFFB3', '#BEBADA', '#FB8072', '#80B1D3', '#FDB462', '#B3DE69', '#FCCDE5']

    # Enforce: that zero χ² values becomes (second-smallest)/5, applied per grid
    # (Zeros or extremely tiny values will be lifted accordingly.)
    chi = df_merged['reduced_chi2'].astype(float)

    #If any chi2 is exactly zero, replace it with second smallest value / 10
    if (chi == 0).any():
        # Get the second smallest value among the finite ones
        second_smallest = chi.nsmallest(2).iloc[-1]
        df_merged.loc[chi == 0, 'reduced_chi2'] = second_smallest / 10.0
    
    #Adjust extreme but non zero Chi2 values
    chi_sorted = np.sort(chi)
    if chi_sorted[0] < chi_sorted[1] / 10.0:
        df_merged.loc[chi == chi_sorted[0], 'reduced_chi2'] = chi_sorted[1] / 10.0

    # adjusted_frames = []
    # for g in df_merged['grid'].unique():
    #     df_g_tmp = df_merged
    #     # Work with finite χ² only to find order statistics
        
    #     chi_finite = chi[finite_mask]
    #     if chi_finite.size >= 2:
    #         # Get order statistics
    #         sorted_vals = np.sort(chi_finite.values)
    #         second_smallest = sorted_vals[1]
    #         smallest = sorted_vals[0]
    #         # Identify rows that have the smallest value (there can be ties)
    #         idx_min = df_g_tmp.index[finite_mask][chi_finite.values == smallest]
    #         # Replace those minima with second_smallest / 5.0
    #         import pdb; pdb.set_trace()
    #         #df_g_tmp.loc[idx_min, 'reduced_chi2'] = float(second_smallest) / 5.0
    #     # If <2 finite values, leave as-is
    #     adjusted_frames.append(df_g_tmp)
    # df_merged = pd.concat(adjusted_frames, ignore_index=True)

    # Overlay an open-circle marker on the currently selected point (by specid), after adjustments
    try:
        df_pre_selected_grid = df_pre[df_pre['grid'] == selected_grid].reset_index(drop=True)
        if (len(df_pre_selected_grid) > 0) and (current_index is not None) and (0 <= int(current_index) < len(df_pre_selected_grid)):
            selected_specid = int(df_pre_selected_grid.iloc[int(current_index)]['moca_specid'])
            row_sel = df_merged[(df_merged['grid'] == selected_grid) & (df_merged['moca_specid'] == selected_specid)].iloc[0]
            intra_grid_specids = df_pre_selected_grid['moca_specid'].tolist()
            local_index = int(intra_grid_specids.index(selected_specid)) if selected_specid in intra_grid_specids else None
            fig.add_trace(go.Scatter(
                x=[row_sel['spectral_type_number']],
                y=[row_sel['reduced_chi2']],
                mode='markers',
                marker=dict(symbol='circle-open', size=16, line=dict(width=2, color='black')),
                showlegend=False,
                hoverinfo='skip',
                customdata=[[selected_grid, local_index]],
                name=''  # no legend entry
            ))
    except Exception as _e:
        if debug_printing:
            print(f"[Spectral Typing] Could not add selected-point overlay (post-adjustment): {_e}")
    
    for i, g in enumerate(grids):
        df_g = df_merged[df_merged['grid'] == g].sort_values('spectral_type_number').reset_index(drop=True)

        # Create a customdata list where each element is [grid, grid_point_index]
        customdata = df_g.apply(lambda row: [row['grid'], row.name], axis=1).tolist()
        
        fig.add_trace(go.Scatter(
            x=df_g['spectral_type_number'],
            y=df_g['reduced_chi2'].values,
            mode='lines+markers',
            name=str(g),
            text=df_g['label'],  # This assumes your merged dataframe has a 'label' column
            hovertemplate='<b>%{text}</b><br>χ²: %{y:.2f}<extra></extra>',
            line=dict(color=colors[i % len(colors)],width=3),
            marker=dict(symbol='circle', size=10),
            customdata=customdata
        ))
    fig.update_yaxes(type="log")

    #tickvals = fig.layout.xaxis.tickvals if fig.layout.xaxis.tickvals else [-10, 0, 14, 20, 25, 32]
    x_min_val = np.floor(df_merged['spectral_type_number'].min())
    x_max_val = np.ceil(df_merged['spectral_type_number'].max())
    n_ticks = int(x_max_val - x_min_val) + 1
    if n_ticks <= 20:
         tickvals = np.arange(x_min_val, x_max_val + 1)
    else:
         step = int(np.ceil((x_max_val - x_min_val) / 20))
         tickvals = np.arange(x_min_val, x_max_val + 1, step)

    df_data_parsed = pd.read_json(df_data, orient='split')
    comp_designation_row = df_data_parsed[df_data_parsed["moca_specid"] == specid]
    comp_designation = comp_designation_row["designation"].iloc[0] if not comp_designation_row.empty else "Unknown"
    comp_specid_tag = f" (specid={int(specid)})" if not specid is None else ""
    title_text_chi2 = f"Global goodness of fit for {comp_designation} {comp_specid_tag}"

    fig.update_layout(
        title=title_text_chi2,
        margin=dict(t=40),
        xaxis=dict(
            title='Spectral Type',
            tickmode='array',
            tickvals=tickvals,
            ticktext=[generate_spectral_type_label(x) for x in tickvals]
        ),
        yaxis_title='χ²',
        #ticktext=[generate_spectral_type_label(x) for x in tickvals]
    )

    # Set y-axis range to include the 30 best χ² values ±5% on both ends.
    chi2_vals = df_merged['reduced_chi2'].dropna().values
    chi2_vals = chi2_vals[chi2_vals > 0]
    if chi2_vals.size > 0:
        frac_pop = 0.75
        ntop = int(len(chi2_vals)*frac_pop)
        top = np.sort(chi2_vals)[:min(ntop, chi2_vals.size)]
        ymin = top.min()
        ymax = top.max()
        # Ensure strictly positive lower bound for log axis and add ±5% padding
        ymin_padded = max(1e-12, 0.85 * ymin)
        ymax_padded = 1.6 * ymax
        # Plotly expects log10 values for the range when y-axis type is 'log'
        fig.update_yaxes(range=[np.log10(ymin_padded), np.log10(ymax_padded)])

    #Update export file name
    date_str = datetime.now().strftime("%y%m%d")
    updated_config = figure_export_config.copy()
    updated_config['toImageButtonOptions'] = updated_config['toImageButtonOptions'].copy()
    updated_config['toImageButtonOptions']['filename'] = f"global_chi2_specid_{int(specid)}_{date_str}"

    #fig.update_yaxes(minor=dict(showgrid=False, tickcolor='rgba(0,0,0,0)', ticklen=0))
    #Didnt work
    #fig.update_layout(
    #    yaxis=dict(
    #        minor=dict(ticks="", ticklen=0)
    #    )
    #)
    return fig, updated_config
