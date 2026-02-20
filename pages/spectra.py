import dash
from dash import html, dcc, dash_table, get_asset_url
from urllib.parse import urlparse, parse_qs, quote
from sqlalchemy import create_engine

dash.register_page(__name__)

import pathlib, os
import colorsys
import numpy.core.defchararray as np_f

import pandas as pd
import numpy as np
from scipy.interpolate import PchipInterpolator

import plotly.graph_objs as go
from dash.dependencies import Input, Output, State

from mocapy import *

bcg_color = 'rgb(255,255,255)'

initial_specids = [683,2105,1954]

figure_export_config = {
  'toImageButtonOptions': {
    'format': 'png', # one of png, svg, jpeg, webp
    'height': 500*2,
    'width': 700*2,
    'scale': 6*2 # Multiply title/legend/axis/canvas sizes by this factor
  }
}



query_e = """
    SELECT ds.moca_specid, ms.spectrum_name, COALESCE(ms.flux_units,"NO_UNITS") AS flux_units, ds.wavelength_angstrom*1e-4 AS lam, flux_flambda AS sp, flux_flambda_unc AS esp
    FROM moca_spectra ms
    JOIN data_spectra ds ON(ds.moca_specid=ms.moca_specid AND ds.ignored=0)
"""

unselected_opacity = 0.1
selected_opacity = 1

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

        x0, x1 = fb["rng"]
        fig.add_shape(
            type="rect",
            x0=x0, x1=x1,
            y0=0 + ypad_frac, y1=1 - ypad_frac,
            xref="x", yref="paper",
            fillcolor=fillcolor,
            line=dict(width=0),
            layer="below",
        )
        fig.add_annotation(
            x=(x0 + x1) / 2,
            y=1 - ypad_frac*0.5,
            xref="x", yref="paper",
            text=fb["name"],
            showarrow=False,
            font=dict(size=11, color=textcolor),
            yanchor="top"
        )
# Empty dataframe used when no spectra are selected (avoid DB calls at import-time)
EMPTY_SPECTRA_DF = pd.DataFrame(
    columns=[
        "moca_specid",
        "spectrum_name",
        "flux_units",
        "lam",
        "sp",
        "esp",
    ]
)

#To make hex colors more transparent
def hex_to_rgba(hex_color, alpha=0.5):
    hex_color = hex_color.lstrip('#')
    return f'rgba({int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}, {alpha})'

def weighted_median(values, weights):
    i = np.argsort(values)
    c = np.cumsum(weights[i])
    return values[i[np.searchsorted(c, 0.5 * c[-1])]]

# Normalize range parser: accepts "0.95-1.35" or "0.95,1.35"
def parse_norm_range(text_val):
    if not text_val:
        return None
    s = str(text_val).strip()
    if not s:
        return None
    s = s.replace(",", "-")
    parts = [p for p in s.split("-") if p.strip()]
    if len(parts) != 2:
        return None
    try:
        a = float(parts[0])
        b = float(parts[1])
    except Exception:
        return None
    if not np.isfinite(a) or not np.isfinite(b):
        return None
    lo, hi = (a, b) if a <= b else (b, a)
    return (lo, hi)

def average_resolving_power(lam_array):
    lam = np.asarray(lam_array, dtype=float)
    lam = lam[np.isfinite(lam)]
    if lam.size < 2:
        return np.nan
    lam = np.unique(np.sort(lam))
    if lam.size < 2:
        return np.nan
    dlam = np.diff(lam)
    lam_mid = 0.5 * (lam[1:] + lam[:-1])
    valid = np.isfinite(dlam) & (dlam > 0) & np.isfinite(lam_mid) & (lam_mid > 0)
    if not np.any(valid):
        return np.nan
    return float(np.nanmean(lam_mid[valid] / dlam[valid]))

# Assign color to legend
# Eventually move this to a subroutine
def colormap_picker_spectra(aid_list):
    # Color palettes generated at http://vrl.cs.brown.edu/color
    la = len(aid_list)
    if la==1:
        colors = ['#e52638']# red
    elif la== 2:
        colors = ["#e52638", "#69ef7b"]# red,green
    elif la==3:
        colors = ["#e52638", "#3db447", "#793883"]# red,green,blue
    elif la==4:
        colors = ["#e52638", "#7bde3f", "#84317b", "#1d8a20"]# red,geen,purple,green
    elif la==5:
        colors = ["#e52638", "#4cf185", "#801967", "#3b8738", "#dd3dca"]# red,geen,purple,green,pink
    elif la==6:
        colors = ["#e52638", "#61f22d", "#d45fea", "#84bc04", "#672396", "#a4c28a"]
    elif la==7:
        colors = ["#e52638", "#2ce462", "#bf11af", "#94d86f", "#7943b1", "#518413", "#fe79ec"]
    elif la==8:
        colors = ["#e52638", "#80de1a", "#fe62cc", "#0b6d33", "#7d1a6e", "#c2df7d", "#4749dc", "#f39450"]
    elif la==9:
        colors = ["#e52638", "#1ed46b", "#9c3190", "#85aa32", "#531ce8", "#eac328", "#1642cd", "#fd8f20", "#1b511d"]
    elif la==10:
        colors = ["#e52638", "#37d275", "#c65ab9", "#76f014", "#740ece", "#6a9012", "#4233a6", "#c9dd87", "#1c4585", "#ffa270"]
    elif la==11:
        colors = ["#e52638", "#2dd460", "#f968c3", "#a7d64e", "#791c76", "#36edd3", "#753131", "#82d1f4", "#2c4e2f", "#e3a3e7", "#609111"]
    elif la==12:
        colors = ["#e52638", "#2ab53c", "#ef6ade", "#95b833", "#6242d3", "#fcce6a", "#135ac2", "#f47d0d", "#074d65", "#e9c9fa", "#683c00", "#62d7e1"]
    elif la==13:
        colors = ["#e52638", "#89eb7b", "#a50fa9", "#09f54c", "#e76cef", "#6c9f30", "#7212ff", "#c7dd91", "#5f4ac2", "#fcd107", "#83366b", "#1ceaf9", "#ef8ead"]
    elif la==14:
        colors = ["#e52638", "#0df38f", "#a54984", "#65f112", "#8323dc", "#428621", "#fe7dda", "#add465", "#4233a6", "#fea53b", "#085782", "#fab5b5", "#1abdc5", "#673d17"]
    elif la==15:
        colors = ["#e52638", "#99ea40", "#711f86", "#2cf52b", "#eb54c7", "#3ba545", "#d995d0", "#1b511d", "#e5836a", "#35c8ef", "#613b4f", "#aae3a4", "#2a2bf0", "#869764", "#0166d8"]
    elif la==16:
        colors = ["#e52638", "#20b465", "#ee53be", "#51f310", "#74168e", "#b7d165", "#6524ff", "#687f39", "#a18ff8", "#fece5f", "#523d6e", "#a2e1ca", "#783019", "#3ba7e5", "#c46d35", "#2c647e"]
    elif la==17:
        colors = ["#e52638", "#36c272", "#fb5de7", "#a9e81a", "#9a23b1", "#2cf52b", "#86487f", "#c6dbae", "#7212ff", "#708e30", "#b69cfd", "#dac925", "#1b48bc", "#f2a966", "#145a6a", "#e2bdc7", "#0b5313"]
    elif la==18:
        colors = ["#e52638", "#8adc30", "#2b19d9", "#dcda5e", "#941483", "#09f54c", "#f75ef0", "#3e9539", "#bd7ab4", "#0b5313", "#f7c5f1", "#683c00", "#43dcc5", "#724363", "#b0ceb3", "#1c4bb4", "#d6a075", "#104b6d"]
    elif la==19:
        colors = ["#e52638", "#61d056", "#fd3fbe", "#2a6b2a", "#760796", "#a4c46d", "#2a2bf0", "#f0c046", "#5b468b", "#f5cdaf", "#1c4c5e", "#fbacf6", "#76480d", "#85d2e1", "#8c0250", "#1eefc9", "#e07142", "#308ac9", "#ab8a77"]
    #20 or more
    else:
        colors = ["#e52638", "#1ed46b", "#bc337d", "#9ee5a4", "#db2bee", "#167b2b", "#f2b0f6", "#bce333", "#710c9e", "#d9c771", "#5e3966", "#65e6f9", "#9e4302", "#389eaa", "#f19189", "#214a65", "#ded1d4", "#1b48bc", "#fd8f2f", "#4c93e9"]
    
    #Flip colors to get red on top
    colors.reverse()
    
    colormap = {}
    for ind, moca_aid in enumerate(aid_list):
        colormap[moca_aid] = colors[ind%len(colors)]
    return colormap

# Eventually move this to a subroutine
def selection_helper_spectra(selections):

    # Find which one has been triggered
    ctx = dash.callback_context

    prop_id = ""
    prop_type = ""
    if ctx.triggered:
        splitted = ctx.triggered[0]["prop_id"].split(".")
        prop_id = splitted[0]
        prop_type = splitted[1]
    else:
        return None, None

    processed_data = None
    selected_data = None

    #print(" Triggered by "+prop_id)
    if prop_id in selections.keys():
        selected_data = selections[prop_id]
        # Deal with circular callbacks that tend to reset selection
        if selected_data is not None:
            if len(selected_data['points']) == 0:
                return None, None
        if selected_data is None:
            processed_data = None
        else:
            processed_data = [seldatapoint['customdata'] for seldatapoint in selected_data['points']]

    return processed_data, prop_id

# Eventually move this to a subroutine
# Visual website banner
def build_banner_spectra():
    return html.Div(
        id="spectra-banner",
        #className="banner",
        children=[
            #html.Img(src=get_asset_url("dash-logo.png")),
            html.H2("MOCA SPECTRAL EXPLORER"),
        ],
        style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"white"},
    )

# Hover display
def build_hover_spectra(dff):
    return list(
        map(
            lambda x1, x2, x3, x4, x5: "MOCA OID : "+str(int(x1))+"<br>Designation : "+str(x2)+"<br>Spectrum ID : "+str(x3)+"<br>SPT : "+str(x4),
            dff["moca_oid"],
            dff["designation"],
            dff["moca_specid"],
            dff["spt"],
        )
    )

def insert_nans_in_gaps(x_array, y_array, threshold_factor=10, ey_array=None):
    """
    Insert NaNs in y_array and ey_array where gaps in x_array are larger than the threshold.
    
    Parameters:
    - x_array: array of x values (e.g., wavelengths)
    - y_array: array of y values (e.g., spectral flux)
    - threshold_factor: multiplier of the median x spacing to determine the gap threshold
    - ey_array: optional array of errors for y values (will insert NaNs in the same locations as y_array if provided)
    
    Returns:
    - x_with_nans: x array with NaNs inserted at large gaps
    - y_with_nans: y array with NaNs inserted at large gaps
    - ey_with_nans: ey array with NaNs inserted at large gaps (if provided)
    """
    # Step 1: Calculate the differences between consecutive x values
    gaps = np.diff(x_array)
    
    # Step 2: Calculate the median gap
    median_gap = np.median(gaps)

    # Step 3: Set the threshold (10x the median gap by default)
    gap_threshold = threshold_factor * median_gap

    # Step 4: Find the indices where the gap exceeds the threshold
    gap_indices = np.where(gaps > gap_threshold)[0]
    
    # Step 5: Create new arrays with NaNs inserted at the gaps
    x_with_nans = []
    y_with_nans = []
    ey_with_nans = [] if ey_array is not None else None
    
    start_idx = 0
    for gap_idx in gap_indices:
        # Add the data up to the gap
        x_with_nans.extend(x_array[start_idx:gap_idx+1])
        y_with_nans.extend(y_array[start_idx:gap_idx+1])
        if ey_with_nans is not None:
            ey_with_nans.extend(ey_array[start_idx:gap_idx+1])
        
        # Insert a NaN in the middle of the gap
        x_gap_middle = (x_array[gap_idx] + x_array[gap_idx+1]) / 2
        x_with_nans.append(x_gap_middle)
        y_with_nans.append(np.nan)
        if ey_with_nans is not None:
            ey_with_nans.append(np.nan)
        
        # Move the start index to after the gap
        start_idx = gap_idx + 1
    
    # Add the remaining data after the last gap
    x_with_nans.extend(x_array[start_idx:])
    y_with_nans.extend(y_array[start_idx:])
    if ey_with_nans is not None:
        ey_with_nans.extend(ey_array[start_idx:])
    
    # Return all arrays (including ey_with_nans if provided)
    if ey_with_nans is not None:
        return np.array(x_with_nans), np.array(y_with_nans), np.array(ey_with_nans)
    else:
        return np.array(x_with_nans), np.array(y_with_nans)

# Eventually move this to a subroutine
def generate_spectrum(df_spectra, df_aids, selected_data, style, showfeatures, norm_range, self_figure):

    # Read layer properties
    style = style or []
    hover = "closest"
    xlog = "xlog" in style
    ylog = "ylog" in style
    use_fnu_jy = "fnu_jy" in style
    normalize = "normalize" in style
    disable_lowres_display = "disable_lowres_display" in style
    c_light_m_s = 299792458.0

    if "hover" not in style:
        hover = False
    
    xtitle  = "Wavelength (μm)"
    ytitle  = "Relative spectral flux density <i>F<sub>λ</sub></i>"
    if use_fnu_jy:
        ytitle = "Relative spectral flux density <i>F<sub>ν</sub></i>"
    
    layout = go.Layout(
        height=850,
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        xaxis={'title':xtitle,'uirevision':'fixed','linewidth':3,'showline':True,'linecolor':'black','mirror':True},
        yaxis={'title':ytitle,'uirevision':'fixed','linewidth':3,'showline':True,'linecolor':'black','mirror':True},
        hovermode=hover,
        paper_bgcolor=bcg_color,#
        plot_bgcolor=bcg_color,
        margin=dict(l=3, r=3, t=3, b=0),
        legend=dict(
            orientation = 'h', xanchor = "right", x = 1, y = 0, yanchor="bottom",
        ),
        meta={}
    )

    #layout['xaxis']['titlefont'] = dict(size=18)  # Adjust the size as needed
    #layout['yaxis']['titlefont'] = dict(size=18)  # Adjust the size as needed
    #tickfont=dict(size=20)
    layout.update(font=dict(size=16),xaxis=dict(showgrid=True, gridcolor='rgba(241, 241, 241, 1)', gridwidth=2, zeroline=False), yaxis=dict(showgrid=True, gridcolor='rgba(211, 211, 211, 0.5)', gridwidth=2, zeroline=False), plot_bgcolor='white');

    unique_specids = np.unique(df_spectra.moca_specid.values)
    nspectra = unique_specids.shape[0]

    colormap = colormap_picker_spectra(unique_specids)

    xrange = np.array([float('inf'), float('-inf')])
    yrange = np.array([float('inf'), float('-inf')])
    xlog_range = np.array([float('inf'), float('-inf')])
    ylog_range = np.array([float('inf'), float('-inf')])
    data = []
    alpha = 0.2

    # Build per-spectrum dataframes and convert to W/m^2/um
    spec_map = {}
    for specid in unique_specids:
        dfi = df_spectra[df_spectra['moca_specid'] == specid].dropna(subset=['sp', 'lam']).copy()
        if dfi.empty:
            continue
        dfi['sp'] = dfi['sp'] * 10000.0
        dfi['esp'] = dfi['esp'] * 10000.0
        if use_fnu_jy:
            lam_um = dfi['lam'].values
            conversion = (lam_um ** 2) * (1e20 / c_light_m_s)
            dfi['sp'] = dfi['sp'].values * conversion
            dfi['esp'] = dfi['esp'].values * conversion
        spec_map[specid] = dfi

    # Update y-axis title for absolute flux mode
    if not normalize:
        if use_fnu_jy:
            ytitle = "Flux density <i>F<sub>ν</sub></i> (Jy)"
        else:
            ytitle = "Absolute spectral flux density <i>F<sub>λ</sub></i> (W/m<sup>2</sup>/μm)"

    # Normalization helpers
    def _get_overlap_mask(df_ref, df_tgt, rng):
        x = df_tgt['lam'].values
        lo = df_ref['lam'].min()
        hi = df_ref['lam'].max()
        mask = (x >= lo) & (x <= hi)
        if rng is not None:
            mask &= (x >= rng[0]) & (x <= rng[1])
        return mask

    def _calc_snr(df, rng):
        if rng is not None:
            dfr = df[(df['lam'] >= rng[0]) & (df['lam'] <= rng[1])]
        else:
            dfr = df
        if dfr.empty:
            return -np.inf
        sp = dfr['sp'].values
        esp = dfr['esp'].replace(0, np.nan).values
        snr = np.nanmedian(sp / esp) if np.isfinite(np.nanmedian(sp / esp)) else -np.inf
        return snr

    def _median_norm(df, rng):
        if rng is not None:
            dfr = df[(df['lam'] >= rng[0]) & (df['lam'] <= rng[1])]
        else:
            dfr = df
        if dfr.empty:
            return 1.0
        return float(np.nanmedian(dfr['sp'].values))

    def _scale_to_ref(df_ref, df_tgt, rng):
        mask = _get_overlap_mask(df_ref, df_tgt, rng)
        if not np.any(mask):
            return None
        x_t = df_tgt['lam'].values[mask]
        y_t = df_tgt['sp'].values[mask]
        e_t = df_tgt['esp'].replace(0, np.nan).values[mask]
        y_r = np.interp(x_t, df_ref['lam'].values, df_ref['sp'].values)
        e_r = np.interp(x_t, df_ref['lam'].values, df_ref['esp'].replace(0, np.nan).values)
        denom = np.sqrt(e_r**2 + e_t**2)
        denom = np.where(np.isfinite(denom) & (denom > 0), denom, np.nan)
        num = np.nansum((y_r * y_t) / denom)
        den = np.nansum((y_t * y_t) / denom)
        if not np.isfinite(den) or den == 0:
            return None
        return num / den

    # Apply normalization if enabled
    if normalize and spec_map:
        # pick highest SNR spectrum as seed
        seed_specid = max(spec_map.keys(), key=lambda sid: _calc_snr(spec_map[sid], norm_range))
        seed_df = spec_map[seed_specid]
        seed_norm = _median_norm(seed_df, norm_range)
        if seed_norm != 0 and np.isfinite(seed_norm):
            seed_df['sp'] /= seed_norm
            seed_df['esp'] /= seed_norm
        normalized = {seed_specid}

        # Orphan normalization for spectra with no overlap with any normalized spectrum
        changed = True
        while changed:
            changed = False
            for sid, df in spec_map.items():
                if sid in normalized:
                    continue
                # If it doesn't overlap norm range at all, normalize to median=1 and mark normalized
                if norm_range is not None:
                    if df[(df['lam'] >= norm_range[0]) & (df['lam'] <= norm_range[1])].empty:
                        n = _median_norm(df, None)
                        if n != 0 and np.isfinite(n):
                            df['sp'] /= n
                            df['esp'] /= n
                        normalized.add(sid)
                        changed = True
                        continue
                # Try to scale to any normalized spectrum
                best_ref = None
                best_n = 0
                for rid in normalized:
                    ref_df = spec_map[rid]
                    mask = _get_overlap_mask(ref_df, df, norm_range)
                    npts = int(np.sum(mask))
                    if npts > best_n:
                        best_n = npts
                        best_ref = rid
                if best_ref is not None and best_n > 0:
                    s = _scale_to_ref(spec_map[best_ref], df, norm_range)
                    if s is None or not np.isfinite(s):
                        continue
                    df['sp'] *= s
                    df['esp'] *= s
                    normalized.add(sid)
                    changed = True
                else:
                    # Orphan: normalize to median=1 and add to normalized set
                    n = _median_norm(df, norm_range if norm_range is not None else None)
                    if n != 0 and np.isfinite(n):
                        df['sp'] /= n
                        df['esp'] /= n
                    normalized.add(sid)
                    changed = True

        # Normalize any remaining orphan spectra to median=1
        for sid, df in spec_map.items():
            if sid in normalized:
                continue
            n = _median_norm(df, None)
            if n != 0 and np.isfinite(n):
                df['sp'] /= n
                df['esp'] /= n
            normalized.add(sid)

    for i in range(nspectra):
        if unique_specids[i] not in spec_map:
            continue
        labeli = df_aids.loc[df_aids['moca_specid'] == unique_specids[i], 'spectrum_name'].values[0]
        colori = colormap[unique_specids[i]]

        dfi = spec_map[unique_specids[i]].copy()
        avg_resolving_power = average_resolving_power(dfi['lam'].values)
        use_lowres_display = (not disable_lowres_display) and np.isfinite(avg_resolving_power) and (avg_resolving_power < 100.0)

        if use_lowres_display:
            valid_lowres = np.isfinite(dfi['lam'].values) & np.isfinite(dfi['sp'].values)
            x_lowres = dfi['lam'].values[valid_lowres]
            y_lowres = dfi['sp'].values[valid_lowres]
            ey_lowres = dfi['esp'].values[valid_lowres]

            if x_lowres.size > 0:
                x_sort_idx = np.argsort(x_lowres)
                x_lowres = x_lowres[x_sort_idx]
                y_lowres = y_lowres[x_sort_idx]
                ey_lowres = ey_lowres[x_sort_idx]

                unique_x, unique_idx = np.unique(x_lowres, return_index=True)
                unique_y = y_lowres[unique_idx]

                if unique_x.size >= 3:
                    dense_x = np.linspace(unique_x[0], unique_x[-1], max(300, 8 * unique_x.size))
                    spline = PchipInterpolator(unique_x, unique_y, extrapolate=False)
                    dense_y = spline(dense_x)
                    spline_trace = go.Scatter(
                        x=dense_x,
                        y=dense_y,
                        mode='lines',
                        line=dict(color=hex_to_rgba(colori, 0.5), width=2.8),
                        hoverinfo='none',
                        showlegend=False
                    )
                    data.append(spline_trace)
                elif unique_x.size >= 2:
                    spline_trace = go.Scatter(
                        x=unique_x,
                        y=unique_y,
                        mode='lines',
                        line=dict(color=hex_to_rgba(colori, 0.5), width=2.8),
                        hoverinfo='none',
                        showlegend=False
                    )
                    data.append(spline_trace)

                if np.any(np.isfinite(ey_lowres)):
                    error_trace = go.Scatter(
                        x=x_lowres,
                        y=y_lowres,
                        mode='markers',
                        marker=dict(size=1, color='rgba(0,0,0,0)'),
                        error_y=dict(
                            type='data',
                            array=np.where(np.isfinite(ey_lowres), ey_lowres, 0.0),
                            visible=True,
                            color=hex_to_rgba(colori, 0.45),
                            thickness=2.5,
                            width=0,
                        ),
                        hoverinfo='none',
                        showlegend=False
                    )
                    data.append(error_trace)

                marker_trace = go.Scattergl(
                    x=x_lowres,
                    y=y_lowres,
                    opacity=1.0,
                    mode='markers',
                    name=labeli,
                    marker=dict(
                        symbol='circle',
                        size=8,
                        color='white',
                        line=dict(color=colori, width=3),
                    ),
                    connectgaps=False,
                )
                data.append(marker_trace)
        else:
            # Insert NaNs in the gaps larger than 10x the median spacing
            x_with_nans, y_with_nans, ey_with_nans = insert_nans_in_gaps(dfi['lam'].values, dfi['sp'].values, ey_array=dfi['esp'].values, threshold_factor=10)

            new_trace = go.Scattergl(x=x_with_nans,y=y_with_nans,opacity=0.8,mode='lines',name=labeli,line=dict(color=colori, width=2, shape='hv'),connectgaps=False)

            if not dfi['esp'].isna().all():
                valid = np.isfinite(x_with_nans) & np.isfinite(y_with_nans) & np.isfinite(ey_with_nans)
                valid_idx = np.where(valid)[0]

                if valid_idx.size > 0:
                    split_points = np.where(np.diff(valid_idx) > 1)[0] + 1
                    valid_segments = np.split(valid_idx, split_points)

                    for seg_idx in valid_segments:
                        if seg_idx.size < 2:
                            continue

                        upper_bound_trace = go.Scatter(
                            x=x_with_nans[seg_idx],
                            y=y_with_nans[seg_idx] + ey_with_nans[seg_idx],
                            mode='lines',
                            line=dict(width=0, shape='hv'),
                            hoverinfo='none',
                            connectgaps=False,
                            fill=None,
                            showlegend=False
                        )

                        lower_bound_trace = go.Scatter(
                            x=x_with_nans[seg_idx],
                            y=y_with_nans[seg_idx] - ey_with_nans[seg_idx],
                            mode='lines',
                            line=dict(width=0, shape='hv'),
                            fill='tonexty',
                            fillcolor=hex_to_rgba(colori, alpha),
                            hoverinfo='none',
                            connectgaps=False,
                            showlegend=False
                        )

                        data.append(upper_bound_trace)
                        data.append(lower_bound_trace)
            
            data.append(new_trace)

        min_lam = np.nanmin(dfi['lam'])
        max_lam = np.nanmax(dfi['lam'])
        xrange[0] = min(xrange[0], min_lam)
        xrange[1] = max(xrange[1], max_lam)
        positive_x = dfi['lam'].values[np.isfinite(dfi['lam'].values) & (dfi['lam'].values > 0)]
        if positive_x.size > 0:
            xlog_range[0] = min(xlog_range[0], float(np.nanmin(positive_x)))
            xlog_range[1] = max(xlog_range[1], float(np.nanmax(positive_x)))

        # Calculate the IQR of 'sp' + 'esp' values
        Q1 = np.nanpercentile(dfi['sp'] + dfi['esp'].fillna(0), 5)
        Q3 = np.nanpercentile(dfi['sp'] + dfi['esp'].fillna(0), 98)
        IQR = Q3 - Q1

        # Determine the range for normalization using IQR
        min_y = Q1 - 0.1 * IQR
        max_y = Q3 + 0.1 * IQR

        yrange[0] = min(yrange[0], min_y)
        yrange[1] = max(yrange[1], max_y)
        positive_y = dfi['sp'].values[np.isfinite(dfi['sp'].values) & (dfi['sp'].values > 0)]
        if positive_y.size > 0:
            ylog_range[0] = min(ylog_range[0], float(np.nanmin(positive_y)))
            ylog_range[1] = max(ylog_range[1], float(np.nanmax(positive_y)))

    if np.isfinite(xrange).all() and xrange[1] > xrange[0]:
        xrange += np.array([-1, 1]) * (xrange[1] - xrange[0]) * 0.02
        layout.xaxis.range = xrange
    if np.isfinite(yrange).all() and yrange[1] > yrange[0]:
        yrange += np.array([-1,1])*(yrange[1]-yrange[0])*0.1
        layout.yaxis.range = yrange

    if xlog:
        layout.xaxis.type = 'log'
        if np.isfinite(xlog_range).all() and xlog_range[1] > xlog_range[0]:
            xlo, xhi = xlog_range
            layout.xaxis.range = [np.log10(xlo / 1.05), np.log10(xhi * 1.05)]
    else:
        layout.xaxis.type = 'linear'

    if ylog:
        layout.yaxis.type = 'log'
        if np.isfinite(ylog_range).all() and ylog_range[1] > ylog_range[0]:
            ylo, yhi = ylog_range
            layout.yaxis.range = [np.log10(ylo / 1.2), np.log10(yhi * 1.2)]
    else:
        layout.yaxis.type = 'linear'

    fig = go.Figure(data=data,layout=layout)
    if showfeatures:
        _add_feature_bands(fig, ypad_frac=0.05)
                     
    fig.update_layout(yaxis={'title': ytitle})
    return fig

layout = html.Div(
    children=[
        dcc.Location(id='url', refresh=False),
        html.Div(
            id="top-row-spectrapage",
            children=[
                html.Div(
                    className="row",
                    id="top-row-header-spectrapage",
                    children=[
                        html.Div(
                            id="header-container-spectrapage",
                            children=[
                                build_banner_spectra(),
                                # dcc.Markdown(children=["MOCA Spatial-Kinematic Explorer"]),
                            ],
                        ),
                        dcc.Store(id='db-data-spectrapage'),
                    ],
                ),
                # Select a spectrum dropdown at the top
                html.Div(
                    className="row",
                    id="dropdown-row-spectrapage",
                    children=[
                        html.Div(
                            className="twelve columns",
                            children=[
                                html.Br(),
                                html.Br(),
                                html.Br(),
                                dcc.Markdown(children=["  Select a set of spectra to be displayed: "], style={'fontSize': 22, 'fontWeight': 'bold'}),
                                dcc.Dropdown(
                                    className='custom-dropdown',
                                    id="specid-select-spectrapage",
                                    multi=True,
                                    value=None,
                                    #style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"white","fontSize": 16},
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        html.Div(
            className="row",
            id="first-data-row-spectrapage",
            children=[
                # Spectrum at the bottom
                html.Div(
                    id="spectra-container-spectrapage",
                    className="twelve columns",
                    children=[
                        html.Br(),
                        dcc.Graph(id="spectra-map-spectrapage", config=figure_export_config),
                    ],
                ),
            ],
        ),
        html.Div(
            className="row",
            id="second-data-row-spectrapage",
            children=[
                # Options in the middle
                html.Div(
                    className="six columns",
                    children=[
                        dcc.Checklist(
                            id="spectram-view-selector-spectrapage",
                            options=[
                                {
                                    "label": "Enable Hover Properties",
                                    "value": "hover",
                                },
                                {
                                    "label": "Log X axis",
                                    "value": "xlog",
                                },
                                {
                                    "label": "Log Y axis",
                                    "value": "ylog",
                                },
                                {
                                    "label": "F_nu instead (Jy) of F_lambda (W/m/$\\mu$m)",
                                    "value": "fnu_jy",
                                },
                            ],
                            value=[],
                        ),
                        dcc.Checklist(
                            id="spectram-showfeatures-spectrapage",
                            options=[
                                {
                                    "label": "Show chemical features",
                                    "value": "showfeatures",
                                },
                            ],
                            value=['showfeatures'],
                        ),
                        dcc.Checklist(
                            id="spectram-lowres-toggle-spectrapage",
                            options=[
                                {
                                    "label": "Deactivate low-resolution display mode",
                                    "value": "disable_lowres_display",
                                    "disabled": True,
                                },
                            ],
                            value=[],
                        ),
                    ],
                ),
                html.Div(
                    className="six columns",
                    children=[
                        dcc.Checklist(
                            id="spectram-normalize-spectrapage",
                            options=[
                                {
                                    "label": "Normalize spectra",
                                    "value": "normalize",
                                },
                            ],
                            value=['normalize'],
                        ),
                        dcc.Input(
                            id="spectram-normrange-spectrapage",
                            type="text",
                            placeholder="Norm range (e.g. 0.95-1.35)",
                            value="0.95-1.35",
                            style={"width": "100%", "marginTop": "6px"}
                        ),
                    ],
                ),
            ],
        ),
        html.Div(
            className="row",
            id="download-row-spectrapage",
            children=[
                html.Div(
                    className="twelve columns",
                    children=[
                        html.H4("Download Links"),
                        html.Div(id="download-links-container")
                    ]
                )
            ]
        ),
        html.Div(
            className="row",
            id="url-help-section-spectrapage",
            children=[
                dcc.Markdown(
                    """
                    ## Using URL Parameters

                    You can customize the Spectral Explorer by appending parameters to the URL query string. The following parameter is supported:

                    - **moca_specid**: Pre-select a set of spectra to be displayed (e.g., `moca_specid=203,212`). Provide one or more values separated by commas. If not provided, a default set of spectra will be loaded.

                    ### Example URL:
                    - `https://dataviz.mocadb.ca/spectra?moca_specid=203,212`

                    """
                )
            ],
            style={"padding": "20px", "backgroundColor": "#f9f9f9"}
        ),
    ]
)

selections = {
        }

# Eventually move this to a subroutine if possible
@dash.callback(
    output=[
        Output("db-data-spectrapage","data"),
        Output("specid-select-spectrapage","options"),
        Output("specid-select-spectrapage","value"),
        ],
    inputs=[
        Input("specid-select-spectrapage", "value"),
    ],
    state=[State("url","search")]
)
def update_specid_select_spectrapage(
    specid_select, url_search
):
    
    #print("DBQUERY callback-spectrapage")
    
    # Read default spectra from URL if none are selected
    # Example query type '?moca_specid=203,212'
    if specid_select is None:
        #Default values without URL variables
        if url_search == "":
            specid_select = initial_specids
        else:
            parsed_url = urlparse(url_search)
            parsed_url_data = parse_qs(parsed_url.query)
            if 'moca_specid' in parsed_url_data.keys() or 'specid' in parsed_url_data.keys():
                raw_specids = parsed_url_data.get('moca_specid', parsed_url_data.get('specid', ['']))[0]
                specid_select = [int(x) for x in raw_specids.split(',') if x.strip()]
            else:
                if specid_select is None:
                    specid_select = initial_specids

    # Read credentials
    user = None
    pwd = None
    dbase = None
    if url_search != "":
        parsed_url = urlparse(url_search)
        parsed_url_data = parse_qs(parsed_url.query)
        if 'user' in parsed_url_data.keys():
            user = parsed_url_data['user'][0]
        if 'pwd' in parsed_url_data.keys():
            pwd = parsed_url_data['pwd'][0]
        if 'dbase' in parsed_url_data.keys():
            dbase = parsed_url_data['dbase'][0]

    # Load MOCA engine for this user
    moca = MocaEngine()

    #Substitute MOCA engine's connection if credentials are provided
    if user is not None and pwd is not None and dbase is not None:
        engine = create_engine('mysql+pymysql://'+user+':'+pwd.replace('%','%25').replace('@','%40').replace(">","%3E").replace("#","%23").replace("_","%5F")+'@104.248.106.21/'+dbase)

        # This is only required for CALL statements
        raw_con = engine.raw_connection()
        moca.raw_connection = raw_con

        # This is required for all queries
        con = engine.connect()
        moca.connection = con

    # Query for AID list here
    df_aids = moca.query("SELECT moca_specid, CONCAT(ms.moca_specid,': ',COALESCE(CONCAT(mo.designation, ' (',spt.spectral_type, ') with ', ms.moca_instid,COALESCE(CONCAT(' in ', ms.instrument_mode_name,' mode'),''),COALESCE(CONCAT(' (', ms.data_collection_date,')'),'')),ms.spectrum_name)) AS spectrum_name FROM moca_spectra ms LEFT JOIN moca_objects mo USING(moca_oid) LEFT JOIN (SELECT moca_oid, spectral_type FROM data_spectral_types WHERE adopted=1) spt USING(moca_oid)")
    aid_options = [{"label": row["spectrum_name"], "value": row["moca_specid"]} for index, row in df_aids.iterrows()]

    #Prevent app from crashing if no spectra are selected
    #import pdb; pdb.set_trace()
    if len(specid_select) == 0:
        df = EMPTY_SPECTRA_DF.copy()
    else:
        # Query the moca database to obtain a Pandas DataFrame for the specific group needed
        aid_query = " OR ".join(["ms.moca_specid='"+str(stri)+"'" for stri in specid_select])
        df = moca.query(query_e+" WHERE ("+aid_query+")")
        
        #Normalize spectra before jsonifying to avoid memory problems
        norm = df['moca_specid'].map(df.groupby('moca_specid')['sp'].median())
        df['esp'] /= norm
        df['sp'] /= norm

    #Object-based selections
    oid_set = False

    return (
        df.to_json(date_format='iso', orient='split'),
        df_aids.to_json(date_format='iso', orient='split'),
        ), aid_options, specid_select

# Update spectrum figure
@dash.callback(
    output=Output("spectra-map-spectrapage", "figure"),
    inputs=dict(
        selections=selections,
        jsonified_db_data=Input("db-data-spectrapage", "data"),
        spectra_view=Input("spectram-view-selector-spectrapage", "value"),
        spectra_features=Input("spectram-showfeatures-spectrapage", "value"),
        spectra_lowres_toggle=Input("spectram-lowres-toggle-spectrapage", "value"),
        spectra_norm=Input("spectram-normalize-spectrapage", "value"),
        spectra_normrange=Input("spectram-normrange-spectrapage", "value"),
    ),
    state=dict(specid_select=State("specid-select-spectrapage", "value"), self_figure=State("spectra-map-spectrapage", "figure")),
)
def update_spectrum_spectrapage(
    selections, 
    jsonified_db_data, spectra_view, spectra_features, spectra_lowres_toggle, spectra_norm, spectra_normrange
    , specid_select, self_figure
):
    
    #print("SPECTRA callback-spectrapage")
    processed_data, prop_id = selection_helper_spectra(selections)
    if prop_id is None:
       return self_figure
    if prop_id == "spectra-map-spectrapage":
        return self_figure

    df = pd.read_json(jsonified_db_data[0], orient='split')
    df_aids = pd.read_json(jsonified_db_data[1], orient='split')

    showfeatures = 'showfeatures' in (spectra_features or [])
    fig = self_figure if self_figure is not None else go.Figure()
    style = spectra_view or []
    if 'disable_lowres_display' in (spectra_lowres_toggle or []):
        style = list(set(style + ['disable_lowres_display']))
    if 'normalize' in (spectra_norm or []):
        style = list(set(style + ['normalize']))
    norm_range = parse_norm_range(spectra_normrange)
    return generate_spectrum(df, df_aids, processed_data, style, showfeatures, norm_range, fig)

@dash.callback(
    Output("spectram-lowres-toggle-spectrapage", "options"),
    Output("spectram-lowres-toggle-spectrapage", "value"),
    Input("db-data-spectrapage", "data"),
    State("spectram-lowres-toggle-spectrapage", "value"),
)
def update_lowres_toggle_state(jsonified_db_data, current_values):
    has_lowres = False
    if jsonified_db_data is not None and len(jsonified_db_data) > 0:
        df = pd.read_json(jsonified_db_data[0], orient='split')
        if not df.empty:
            for _, dfi in df.groupby('moca_specid'):
                avg_r = average_resolving_power(dfi['lam'].values)
                if np.isfinite(avg_r) and avg_r < 100.0:
                    has_lowres = True
                    break

    options = [
        {
            "label": "Deactivate low-resolution display mode",
            "value": "disable_lowres_display",
            "disabled": not has_lowres,
        },
    ]
    if has_lowres:
        return options, (current_values or [])
    return options, []

@dash.callback(
    Output("spectram-normrange-spectrapage", "disabled"),
    Input("spectram-normalize-spectrapage", "value"),
)
def toggle_normrange_disabled(norm_values):
    return 'normalize' not in (norm_values or [])

@dash.callback(
    Output("download-links-container", "children"),
    Input("db-data-spectrapage", "data")
)
def update_download_links(json_data):
    if json_data is None or len(json_data) == 0:
        return []
    # The first element in json_data is the main dataframe
    df = pd.read_json(json_data[0], orient='split')
    download_links = []
    # Group the dataframe by moca_specid
    for specid, group in df.groupby('moca_specid'):
        # Select only the relevant columns and rename them
        csv_df = group[['lam', 'sp', 'esp']].rename(
            columns={'lam': 'wavelength_microns', 'sp': 'flux_flambda', 'esp': 'flux_error_flambda'}
        )
        csv_str = csv_df.to_csv(index=False)
        # Encode CSV content for a data URI
        href = "data:text/csv;charset=utf-8," + quote(csv_str)
        # Create a download link (styled as a button if desired)
        link = html.A(
            f"Download moca_specid_{specid}.csv",
            href=href,
            download=f"moca_specid_{specid}.csv",
            target="_blank",
            style={'marginRight': '10px', 'padding': '5px 10px', 'border': '1px solid #ccc', 'borderRadius': '3px', 'textDecoration': 'none', 'color': 'black'}
        )
        download_links.append(link)
    return download_links
