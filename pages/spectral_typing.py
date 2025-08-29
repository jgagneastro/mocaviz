import dash
from datetime import datetime
from dash import dcc, html, Input, Output, State, callback_context
import pandas as pd
import numpy as np
import plotly.graph_objs as go
from sqlalchemy import create_engine, MetaData, Table, select, Float
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

# =============================================================================
# Constants for spectral processing
# =============================================================================
wv_min, wv_max = 0.85, 2.4
masked_regions = [(1.367, 1.424), (1.86, 2.0)]
# Use three normalization regions as in tom_redl_sequence.py
norm_regions = [
    (wv_min, np.mean(masked_regions[0])),
    (np.mean(masked_regions[0]), np.mean(masked_regions[1])),
    (np.mean(masked_regions[1]), wv_max)
]
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
                   html.Button("← Previous Standard", id='sp-typing-prev-button', disabled=True, n_clicks=0, style={'fontSize': '16px', 'border': '3px solid black', 'marginRight': '15px', 'verticalAlign': 'middle'}),
                   html.Button("Next Standard →", id='sp-typing-next-button', disabled=True, n_clicks=0, style={'fontSize': '16px', 'border': '3px solid black', 'verticalAlign': 'middle'})
              ], id='sp-typing-nav-div', style={'margin-bottom': '15px'})
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
         className="row",
         id="url-help-section-xupage",
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
        specid = qs.get("specid", [None])[0]
    else:
        specid = None
    
    connection_string = get_connection_string_sptype(url_search=search)
    engine = create_engine(connection_string)
    query = """
        SELECT ms.moca_specid, CONCAT(
            ms.moca_specid, ': ',
            COALESCE(
                CONCAT(
                    mo.designation, ' (', spt.spectral_type, ') with ', ms.moca_instid,
                    COALESCE(CONCAT(' in ', ms.instrument_mode_name, ' mode'), ''),
                    COALESCE(CONCAT(' (', ms.data_collection_date, ')'), '')
                ),
                ms.spectrum_name
            )
        ) AS spectrum_name, mo.designation
        FROM moca_spectra ms
        LEFT JOIN moca_objects mo USING(moca_oid)
        LEFT JOIN (SELECT moca_oid, spectral_type FROM cdata_spectral_types WHERE adopted=1) spt USING(moca_oid)
        WHERE (ms.moca_specpackid != 1 OR ms.moca_specpackid IS NULL)
    """
    df = pd.read_sql(query, engine)
    options = [{'label': row["spectrum_name"], 'value': row["moca_specid"]} for index, row in df.iterrows()]
    designation_map = {row["moca_specid"]: row["spectrum_name"].split(': ')[1].split(' with ')[0] for index, row in df.iterrows()}
    
    valid_specids = [str(opt['value']) for opt in options]
    default_value = specid if specid in valid_specids else None
    
    return options, int(default_value) if default_value is not None else None, designation_map, df.to_json(date_format='iso', orient='split')

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
            SELECT dstg.moca_sptgridid AS grid, dstg.moca_specid, dstg.spectral_type, dstg.spectral_type_number, dstg.short_object_designation AS designation, CONCAT(dstg.spectral_type,' (',dstg.short_object_designation,')') AS label
            FROM data_spectral_typing_grids dstg
            JOIN moca_spectral_typing_grids mstg USING(moca_sptgridid)
            WHERE dstg.adopted=1 AND mstg.adopted=1 AND dstg.moca_specid IS NOT NULL
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
            WHERE dstg.adopted=1 AND mstg.adopted=1 AND dstg.moca_specid IS NOT NULL AND ds.adopted=1 AND ds.flux_flambda IS NOT NULL AND ds.wavelength_angstrom IS NOT NULL
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
    #Output('sp-typing-grid-dropdown', 'options'),
    Output('sp-typing-grid-dropdown', 'value'),
    #Output('sp-typing-grid-data', 'data'),
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
    Input('sp-typing-grid-dropdown', 'options'), # This is now an input on Friday morning to trigger the first occurrence
    Input('sp-typing-grid-data', 'data'), # This is now an input on Friday morning to trigger the first occurrence
    #Input('sp-typing-grid-raw-spectra', 'data'), # This is now an input on Friday morning to trigger the first occurrence
    State('sp-typing-url', 'search'), #Changed to State on Friday
    #State('sp-typing-grid-dropdown', 'options'),
    # Putting this back on on Friday
    prevent_initial_call=True
)
def grid_controls_callback(prev_click, next_click, slider_input, current_value, chi2_clickData, options, grid_data, url_search):
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
        # Read necessary data
        #df_options = pd.read_json(grid_data, orient='split')
        #df_std_spectra = pd.read_json(grid_spectra, orient='split')
        #options = [{'label': label, 'value': grid} for grid, label in df[['grid', 'grid']].drop_duplicates().values]

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
            default_value = grid if grid in valid_grids else ('field')
            current_value = default_value
        
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

        # Set button disabled states based on the current index.
        #prev_disabled = (current_index == 0)
        #next_disabled = (current_index == num_options - 1)
        
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
            #elif 'sp-typing-grid-dropdown' in trigger_prop:
            #    new_index = current_index
            elif 'sp-typing-chi2-graph' in trigger_prop:
                if chi2_clickData:
                    point = chi2_clickData.get('points', [{}])[0]
                    cd = point.get('customdata', None)
                    if cd and isinstance(cd, list) and len(cd) >= 2:
                        # Update grid selection
                        try:
                            new_index = next(i for i, opt in enumerate(options) if opt['value'] == cd[0])
                        except StopIteration:
                            new_index = current_index
                    #else:
                    #    new_index = current_index
                #else:
                #    new_index = current_index
        #else:
        #    new_index = current_index

            # # If the grid has changed, try to find the best matching index in the new grid based on spectral_type_number
            # if 'sp-typing-chi2-graph' not in trigger_prop
            #     if new_index != current_index:
            #         try:
            #             df_grid = pd.read_json(grid_data, orient='split')
            #             current_grid = options[current_index]['value']
            #             new_grid = options[new_index]['value']
            #             current_grid_spts = df_grid[df_grid['grid'] == current_grid].reset_index(drop=True)
            #             new_grid_spts = df_grid[df_grid['grid'] == new_grid].reset_index(drop=True)
            #             if not current_grid_spts.empty and not new_grid_spts.empty:
            #                 #These mix up the horizontal and vertical indexes
            #                 #current_spt_num = current_grid_spts.iloc[current_index]['spectral_type_number']
            #                 #best_index = (new_grid_spts['spectral_type_number'] - current_spt_num).abs().idxmin()
            #                 #new_index = num_options - 1 - new_grid_spts.index.get_loc(best_index)
            #         except Exception:
            #             pass
                        
        new_value = options[new_index]['value']
        slider_value = num_options - 1 - new_index

        # Update button disabling
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
        JOIN data_spectra ds ON (ds.moca_specid = ms.moca_specid AND ds.adopted = 1)
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
                    (~np.isnan(comp_seg['spn'].values)) &
                    (~np.isnan(std_seg['spn'].values))
                )
                if np.sum(valid) > 0:
                    ratio = np.nanmedian(comp_seg['spn'].values[valid] / std_seg['spn'].values[valid])
                    # Normalize the original standard spectrum
                    std_df.loc[(std_df['wv'] >= region_min) & (std_df['wv'] <= region_max), 'spn'] *= ratio
                    std_df.loc[(std_df['wv'] >= region_min) & (std_df['wv'] <= region_max), 'esp'] *= ratio
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
                            (~np.isnan(comp_seg['spn'].values)) &
                            (~np.isnan(std_seg_dered['spn'].values))
                        )
                        if np.sum(valid) > 0:
                            ratio = np.nanmedian(comp_seg['spn'].values[valid] / std_seg_dered['spn'].values[valid])
                            # Normalize the original standard spectrum
                            std_df_dered.loc[(std_df_dered['wv'] >= region_min) & (std_df_dered['wv'] <= region_max), 'spn'] *= ratio
                            std_df_dered.loc[(std_df_dered['wv'] >= region_min) & (std_df_dered['wv'] <= region_max), 'esp'] *= ratio
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
    Output('sp-typing-current-sptnum', 'data'),
    Output('sp-typing-current-index', 'data'),
    Output('sp-typing-index-slider', 'value'),
    Output('sp-typing-index-slider', 'max'),
    Output('sp-typing-index-slider', 'marks'),
    Output('sp-typing-graph', 'figure'),
    Output('sp-typing-graph', 'config'),
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
    State('sp-typing-current-sptnum', 'data'),
    State('sp-typing-current-index', 'data'),
    State('sp-typing-precomputed-store', 'data'),
    State('sp-typing-deredden-checklist', 'value'),
    State('sp-typing-db-data', 'data'),
    State('sp-typing-url', 'search')
)
def update_graph(prev_clicks, next_clicks, slider_value, comparison_data, selected_grid, comparison_designation, chi2_clickData, norm_regions_store, previous_sptnum, current_index, precomputed, deredden_value, df_data, url_search):
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
        return dash.no_update, current_index, slider_value, 0, {0: ''}, empty_fig, figure_export_config, prev_disabled, next_disabled

    filtered_precomputed = [entry for entry in precomputed if entry['grid'] == selected_grid]
    local_norm_regions = [(float(a), float(b)) for (a, b) in (norm_regions_store or norm_regions)]
    
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
        # grid point with the smallest reduced χ² within the currently selected grid.
        parsed = urlparse(url_search) if url_search else None
        grid_index_param = None
        if parsed:
            qs = parse_qs(parsed.query)
            grid_index_param = qs.get("grid_index", [None])[0]

        if grid_index_param is not None:
            try:
                new_index = int(grid_index_param)
            except ValueError:
                # Fallback to best-chi2 if the param is malformed
                chi2_values = np.array(
                    [entry.get('reduced_chi2', np.nan) for entry in filtered_precomputed],
                    dtype=float
                )
                if np.all(np.isnan(chi2_values)):
                    new_index = len(filtered_precomputed) // 2
                else:
                    new_index = int(np.nanargmin(chi2_values))
        else:
            # Choose the index with the smallest reduced χ² (ignoring NaNs)
            chi2_values = np.array(
                [entry.get('reduced_chi2', np.nan) for entry in filtered_precomputed],
                dtype=float
            )
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
    #custom_colors = ['#E41A1C', '#377EB8', '#984EA3', '#A65628', '#FF5733', '#4682B4', '#8A2BE2', '#D62728', '#FF6347', '#5F9EA0', '#800080', '#DC143C', '#4169E1', '#C71585']
    custom_colors = ['#E41A1C', '#377EB8', '#4DAF4A', '#984EA3', '#FF7F00', '#FFFF33', '#A65628', '#F781BF']
    standard_color = custom_colors[new_index % len(custom_colors)]

    # For each normalization region, add a step trace for the Standard Spectrum (not dereddened) first
    standard_label = std_entry['spectral_type']+' ('+std_entry['designation']+')'
    standard_short_label = std_entry['spectral_type']
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
    
    # For each normalization region, add a step trace for the Comparison Spectrum on top
    comp_id = comparison_df['moca_specid'].iloc[0]
    df_data_parsed = pd.read_json(df_data, orient='split')
    comp_designation_row = df_data_parsed[df_data_parsed["moca_specid"] == comp_id]
    comp_designation = comp_designation_row["designation"].iloc[0] if not comp_designation_row.empty else "Unknown"
    comp_specid_tag = f" (specid={int(comp_id)})" if not comp_designation_row.empty else ""
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
    title_text = f"{comp_designation} {comp_specid_tag} vs {standard_label}, {selected_grid} grid"

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

    fig.update_layout(
        title=title_text,
        xaxis_title="Wavelength (µm)",
        yaxis_title="Normalized Flux",
        margin=dict(t=40),
        xaxis=dict(range=[x_min - x_margin, x_max + x_margin]),
        yaxis=dict(range=[y_min - y_margin, y_max + y_margin])
    )

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

    return current_sptnum, new_index, new_index, slider_max, slider_marks, fig, updated_config, prev_disabled, next_disabled

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

    # Replace zero reduced_chi2 values with 0.8 × minimum non-zero value
    non_zero_min = df_merged.loc[df_merged['reduced_chi2'] > 0, 'reduced_chi2'].min()
    df_merged.loc[df_merged['reduced_chi2'] == 0, 'reduced_chi2'] = non_zero_min * 0.8 if pd.notnull(non_zero_min) else min_chi2_val
    
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

    # Set y-axis upper limit based on the second smallest nonzero reduced_chi2 value
    vals = np.sort(df_merged['reduced_chi2'][df_merged['reduced_chi2'] > 0].dropna().values)
    if len(vals) >= 2:
        limit = 1.6 * vals[1]
        fig.update_yaxes(range=[None, limit])

    # Add a highlighted marker around the currently selected standard for the active grid
    df_sel = df_merged[df_merged['grid'] == selected_grid].sort_values('spectral_type_number')
    if not df_sel.empty and current_index is not None and current_index < len(df_sel):
         highlight = df_sel.iloc[current_index]
         fig.add_trace(go.Scatter(
             x=[highlight['spectral_type_number']],
             y=[highlight['reduced_chi2']],
             mode='markers',
             marker=dict(symbol='circle-open', size=20, color='black', line=dict(width=3)),
             name='displayed'
         ))

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