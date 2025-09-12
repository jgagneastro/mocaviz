#TESTING CMD: http://127.0.0.1:8050/bd-colors?xaxis_type=color&yaxis_type=absolute_magnitude&yaxis_value_1=mko_jmag&xaxis_value_1=mko_jmag&xaxis_value_2=mko_kmag&moca_oid=602&binaries=true
#TESTING SPT VS MK: http://127.0.0.1:8050/bd-colors?xaxis_type=spectral_type&yaxis_type=absolute_magnitude&yaxis_value_1=mko_jmag&moca_oid=602
#TESTING SPECTRAL INDEX: 127.0.0.1:8050/bd-colors?xaxis_type=spectral_type&moca_oid=602&yaxis_type=spectral_index&yaxis_value_1=h2o_j

import dash
from dash import dcc, html, Input, Output, State
from dash.dependencies import ALL
from sqlalchemy import create_engine, MetaData, Table, select, case
from sqlalchemy.sql import func
import pandas as pd
from math import log10, floor, ceil
from urllib.parse import quote_plus as urlquote, urlparse, parse_qs, unquote
import os
import numpy as np
import plotly.graph_objs as go
import fnmatch

# Register the page
dash.register_page(__name__, path='/bd-colors')

# Default connection parameters
default_host = '104.248.106.21'
default_username = 'public'
default_password = 'z@nUg_2h7_%?31y88'
default_dbname = 'mocadb'
default_spt_range = 'M6-Y2'
default_spt_range_val = [6,32]

all_valid_axis_types = ['spectral_type', 'color', 'absolute_magnitude', 'spectral_index', 'equivalent_width']
one_value_axis_types = ['absolute_magnitude', 'spectral_index', 'equivalent_width']
two_values_axis_types = ['color']

figure_export_config = {
  'toImageButtonOptions': {
    'format': 'png', # one of png, svg, jpeg, webp
    'height': 500,
    'width': 700,
    'scale': 6 # Multiply title/legend/axis/canvas sizes by this factor
  }
}

# --- Reference sequences overplot rules & helpers ---
# Rules are dynamically generated from `moca_sequences` (DB-driven).
REF_SEQUENCE_RULES = None  # populated on-demand from DB

def _build_axis_from_row(axis_prefix, row):
    """Build an axis spec dict for a given row using *_bdcolapp columns.
    axis_prefix: 'x' or 'y'
    Returns a dict like {'type': 'color', 'color': {...}} or None if insufficient data.
    Assumptions per user request:
      - swap_ok = True (handled at rule level)
      - unordered = False for all color axes
      - Ignore rows with NULL in required fields for the axis type
    """
    tkey = f"{axis_prefix}axis_type_bdcolapp"
    v1k  = f"{axis_prefix}axis_value_1_bdcolapp"
    v2k  = f"{axis_prefix}axis_value_2_bdcolapp"

    atype = row.get(tkey)
    v1 = row.get(v1k)
    v2 = row.get(v2k)

    if atype is None:
        return None

    atype = atype.strip()

    if atype == 'color':
        # Need two distinct bands
        if not v1 or not v2 or v1 == 'NULL' or v2 == 'NULL' or v1 == v2:
            return None
        return {
            'type': 'color',
            'color': {'psid1': v1, 'psid2': v2, 'unordered': False}
        }
    elif atype == 'absolute_magnitude':
        if not v1 or v1 == 'NULL':
            return None
        return {'type': 'absolute_magnitude', 'absmag': {'psid': v1}}
    elif atype == 'spectral_index':
        if not v1 or v1 == 'NULL':
            return None
        return {'type': 'spectral_index', 'sindex': {'flag': v1}}
    elif atype == 'equivalent_width':
        if not v1 or v1 == 'NULL':
            return None
        return {'type': 'equivalent_width', 'eqw': {'flag': v1}}
    elif atype == 'spectral_type':
        return {'type': 'spectral_type'}
    else:
        # Unknown/unsupported type
        return None


def _load_ref_sequence_rules(engine):
    """Generate REF_SEQUENCE_RULES from table `moca_sequences` using the *_bdcolapp columns.
    Criteria:
      - display_in_bdcolapp == 1 (intended for the app)
      - xaxis_type_bdcolapp and yaxis_type_bdcolapp not NULL
      - Required value columns for each axis type not NULL (and distinct for colors)
      - swap_ok=True for all rules; unordered=False for color axes
    """
    global REF_SEQUENCE_RULES
    try:
        meta = MetaData()
        t = Table('moca_sequences', meta, autoload_with=engine)
        with engine.connect() as conn:
            sel = select([
                t.c.moca_seqid,
                t.c.name_bdcolapp,
                t.c.display_in_bdcolapp,
                t.c.xaxis_type_bdcolapp,
                t.c.yaxis_type_bdcolapp,
                t.c.xaxis_value_1_bdcolapp,
                t.c.xaxis_value_2_bdcolapp,
                t.c.yaxis_value_1_bdcolapp,
                t.c.yaxis_value_2_bdcolapp,
            ]).where(t.c.display_in_bdcolapp == 1)
            df = pd.read_sql(sel, conn)
    except Exception:
        # Fallback: no rules if table not accessible
        REF_SEQUENCE_RULES = []
        return REF_SEQUENCE_RULES

    rules = []
    for _, row in df.iterrows():
        rowd = row.to_dict()
        axx = _build_axis_from_row('x', rowd)
        axy = _build_axis_from_row('y', rowd)
        if axx is None or axy is None:
            continue  # ignore rows with NULLs or invalid combos
        rules.append({
            'seqid': rowd.get('moca_seqid'),
            'legend': rowd.get('name_bdcolapp') or rowd.get('moca_seqid') or 'reference sequence',
            'axes': {'x': axx, 'y': axy},
            'swap_ok': True
        })

    REF_SEQUENCE_RULES = rules
    return REF_SEQUENCE_RULES

# ---- Generalized, flag-based axis matching (no DB resolution) ----

def _axis_signature(axis_type, band_values):
    """Build a canonical signature dict for an axis selection using raw flags.
    Examples (using the provided flags as-is):
      {'type':'color', 'color': {'psid1':'mko_jmag','psid2':'mko_hmag'}}
      {'type':'absolute_magnitude','absmag': {'psid':'mko_jmag'}}
      {'type':'spectral_type'}
      {'type':'spectral_index','sindex': {'flag':'h2o_j'}}
      {'type':'equivalent_width','eqw': {'flag':'na_i_8190'}}
    """
    sig = {'type': axis_type}
    bv = band_values or []
    t = axis_type or ''
    if t == 'color':
        f1 = bv[0] if len(bv) >= 1 else None
        f2 = bv[1] if len(bv) >= 2 else None
        sig['color'] = {'psid1': f1, 'psid2': f2}
    elif t == 'absolute_magnitude':
        f1 = bv[0] if len(bv) >= 1 else None
        sig['absmag'] = {'psid': f1}
    elif t == 'spectral_index':
        f1 = bv[0] if len(bv) >= 1 else None
        sig['sindex'] = {'flag': f1}
    elif t == 'equivalent_width':
        f1 = bv[0] if len(bv) >= 1 else None
        sig['eqw'] = {'flag': f1}
    # spectral_type carries no flags
    return sig



# Helper for wildcard/flag matching
def _match_flag(want, have):
    """Return True if `have` matches `want` allowing shell-style wildcards.
    - If want is None or want == '*', accept any non-None `have`.
    - If want includes '*' or '?', use fnmatch.
    - Else, require exact equality.
    """
    if want is None:
        return True
    if have is None:
        return False
    if isinstance(want, str):
        w = want.strip()
        if w == '*':
            return True
        if ('*' in w) or ('?' in w):
            return fnmatch.fnmatch(str(have), w)
        return str(have) == w
    return want == have

def _match_axis(sig, rule_axis):
    """Return True if a user axis signature matches the rule axis spec.
    Uses raw flags with optional wildcards ('*', '?') in rule values.
    The rule may omit specifics to wildcard that sub-structure.
    """
    if rule_axis is None:
        return True
    if sig.get('type') != rule_axis.get('type'):
        return False

    t = sig.get('type')

    if t == 'color':
        r = (rule_axis.get('color') or {})
        if not r:
            return True
        unordered = r.get('unordered', True)
        want1, want2 = r.get('psid1'), r.get('psid2')
        have1 = sig.get('color', {}).get('psid1')
        have2 = sig.get('color', {}).get('psid2')
        if unordered:
            # Accept either mapping (want1->have1 & want2->have2) OR swapped
            direct = _match_flag(want1, have1) and _match_flag(want2, have2)
            swapped = _match_flag(want1, have2) and _match_flag(want2, have1)
            return direct or swapped
        else:
            return _match_flag(want1, have1) and _match_flag(want2, have2)

    if t == 'absolute_magnitude':
        r = (rule_axis.get('absmag') or {})
        want = r.get('psid')
        have = sig.get('absmag', {}).get('psid')
        return _match_flag(want, have)

    if t == 'spectral_index':
        r = (rule_axis.get('sindex') or {})
        want = r.get('flag')
        have = sig.get('sindex', {}).get('flag')
        return _match_flag(want, have)

    if t == 'equivalent_width':
        r = (rule_axis.get('eqw') or {})
        want = r.get('flag')
        have = sig.get('eqw', {}).get('flag')
        return _match_flag(want, have)

    if t == 'spectral_type':
        return True

    return False


def _match_rule(sig_x, sig_y, rule):
    """Try to match a rule in direct orientation or swapped (if swap_ok).
    Returns (matched: bool, swapped: bool).
    """
    axes = rule.get('axes', {})
    rx, ry = axes.get('x'), axes.get('y')
    swap_ok = rule.get('swap_ok', True)

    if _match_axis(sig_x, rx) and _match_axis(sig_y, ry):
        return True, False
    if swap_ok and _match_axis(sig_x, ry) and _match_axis(sig_y, rx):
        return True, True
    return False, False

def _maybe_add_reference_sequence(fig, engine, x_axis_type, y_axis_type, x_band_values, y_band_values):
    """
    If the (x,y) selections match any rule in REF_SEQUENCE_RULES, fetch the sequence
    from data_astro_sequences and overplot. Works for any axis-type combo. Orientation
    is adapted if the rule matched in swapped mode.
    """
    try:
        sig_x = _axis_signature(x_axis_type, x_band_values)
        sig_y = _axis_signature(y_axis_type, y_band_values)

        # Ensure rules are loaded from the DB (once per callback execution)
        global REF_SEQUENCE_RULES
        if REF_SEQUENCE_RULES is None:
            _load_ref_sequence_rules(engine)
        rules_src = REF_SEQUENCE_RULES or []

        # 1) Collect all matches
        matches = []  # list of (rule, swapped_bool)
        for rule in rules_src:
            ok, is_swapped = _match_rule(sig_x, sig_y, rule)
            if ok:
                matches.append((rule, is_swapped))
        if not matches:
            return

        # 2) Pick a color per rule (rule.get('color', ...) if you ever add explicit colors)
        palette = ["#000000", "#611414", "#195d19", "#63457e", "#613106","#12466b",
           "#0c616a", "#603152", '#7f7f7f', '#bcbd22']

        # Fetch the sequence
        meta = MetaData()
        seq = Table('data_astro_sequences', meta, autoload_with=engine)
        
        for idx, (rule, swapped) in enumerate(matches):
            color = rule.get('color', palette[idx % len(palette)])
            legend_name = rule.get('legend', rule.get('seqid', 'reference sequence'))

            with engine.connect() as conn:
                q = select([seq.c.xdata, seq.c.ydata, seq.c.yerror]).where(seq.c.moca_seqid == rule['seqid'])
                df = pd.read_sql(q, conn)
            if df.empty:
                continue

            x_vals = pd.to_numeric(df['xdata'], errors='coerce').values
            y_vals = pd.to_numeric(df['ydata'], errors='coerce').values
            yerr   = pd.to_numeric(df['yerror'], errors='coerce').values if 'yerror' in df.columns else None

            # Orient according to match
            if swapped:
                plot_x, plot_y = y_vals, x_vals
                err_y = None  # DB yerror maps to unswapped Y; skip in swapped orientation
            else:
                plot_x, plot_y = x_vals, y_vals
                err_y = yerr

            # Sort by X for stable filled polygon
            order = np.argsort(plot_x)
            xs = plot_x[order]
            ys = plot_y[order]

            # Shaded ±1σ band (only when not swapped)
            if err_y is not None:
                err_sorted = err_y[order]
                y_upper = ys + err_sorted
                y_lower = ys - err_sorted
                band_x = np.concatenate([xs, xs[::-1]])
                band_y = np.concatenate([y_upper, y_lower[::-1]])

                fig.add_trace(go.Scatter(
                    x=band_x, y=band_y, mode='lines',
                    line=dict(width=0),
                    fill='toself',
                    fillcolor=_modulate_rgba_alpha(color, alpha_factor=0.15, default='rgba(0,0,0,0.12)'),
                    hoverinfo='skip',
                    name=f"{legend_name} ±1σ",
                    showlegend=False,
                    legendgroup=legend_name
                ))

                # Central thick line with per-sequence color
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode='lines',
                    line=dict(width=3, color=color),
                    name=legend_name,
                    legendgroup=legend_name,
                    hoverinfo='x+y+name'
                ))
    except Exception:
        return

def parse_spt_label(label):
        """Reverse `generate_spectral_type_label` to map a spectral type to a number."""
        classes = ['O', 'B', 'A', 'F', 'G', 'K', 'M', 'L', 'T', 'Y']
        class_map = {cls: idx for idx, cls in enumerate(classes)}

        if not label or len(label) < 2:
            return None

        spt_class = label[0]
        subclass = label[1:]

        if spt_class in class_map:
            try:
                subclass_num = float(subclass)
                return class_map[spt_class] * 10 + subclass_num - 60
            except ValueError:
                return None
        return None

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

def compute_ticks(data_range, axis_length_pixels=400, min_tick_spacing=50):
    """
    Compute aesthetically pleasing ticks similar to Plotly.

    Parameters:
    - data_range (tuple): The (min, max) range of data values for the axis.
    - axis_length_pixels (int): The estimated axis length in pixels (default 400 pixels).
    - min_tick_spacing (int): The minimum spacing between ticks in pixels (default 50 pixels).

    Returns:
    - numpy.ndarray: The computed tick positions.
    """
    # Calculate ideal number of ticks based on axis length and minimum spacing
    num_ticks = axis_length_pixels // min_tick_spacing

    # Unpack the range
    data_min, data_max = data_range
    raw_range = data_max - data_min
    if raw_range <= 0:
        raise ValueError("Invalid data range for tick computation.")

    # Calculate rough step size
    rough_step = raw_range / num_ticks

    # "Nice" step size adjustment to nearest 1, 2, 5 multiple
    magnitude = 10 ** floor(log10(rough_step))  # Base scale
    fractions = [1, 2, 5, 10]
    nice_step = min(fractions, key=lambda f: abs(f * magnitude - rough_step)) * magnitude

    # Align ticks to the "nice" step
    tick_start = ceil(data_min / nice_step) * nice_step
    tick_end = floor(data_max / nice_step) * nice_step

    # Generate ticks
    ticks = np.arange(tick_start, tick_end + nice_step, nice_step)

    return ticks
    
# --- Best18 median colors overlay helpers ---
from plotly import graph_objs as pgo
from sqlalchemy import Table

def _fetch_median_colors_df(engine, psid1, psid2, moca_pid_preference='Best18'):
    """
    Return DataFrame with columns: spectral_type_number, color_mag, n_obj
    for a given (psid1, psid2). Prefers rows with moca_pid==moca_pid_preference; 
    falls back to any moca_pid if needed.
    """
    t = Table('data_median_colors', MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        # Preferred moca_pid (e.g. Best18)
        q_pref = (
            select([t.c.spectral_type_number.label('spectral_type_number'),
                    t.c.color_mag.label('color_mag'),
                    t.c.n_obj.label('n_obj')])
            .where((t.c.moca_psid1 == psid1) & (t.c.moca_psid2 == psid2) & (t.c.moca_pid == moca_pid_preference))
        )
        try:
            df = pd.read_sql(q_pref, conn)
            if not df.empty:
                return df
        except Exception:
            pass
        # Fallback: any moca_pid
        q_any = (
            select([t.c.spectral_type_number.label('spectral_type_number'),
                    t.c.color_mag.label('color_mag'),
                    t.c.n_obj.label('n_obj')])
            .where((t.c.moca_psid1 == psid1) & (t.c.moca_psid2 == psid2))
        )
        try:
            df_any = pd.read_sql(q_any, conn)
            return df_any
        except Exception:
            return pd.DataFrame(columns=['spectral_type_number', 'color_mag', 'n_obj'])

def _spt_color_to_markers(df, axis_for_color='y', spt_min=None, spt_max=None, name='Median colors (Best18)'):
    """
    Build two Plotly traces for median colors:
      • Large unfilled black circles at each SPT/color point
      • Centered text labels (e.g., M6) colored by spectral class

    axis_for_color: 'y' => (SPT on X, color on Y); 'x' => (color on X, SPT on Y)
    Returns a list of two traces (circle, text) or None if no data.
    """
    if df is None or df.empty:
        return None
    df = df.dropna(subset=['spectral_type_number', 'color_mag']).copy()
    if df.empty:
        return None

    if spt_min is not None:
        df = df[df['spectral_type_number'] >= spt_min]
    if spt_max is not None:
        df = df[df['spectral_type_number'] <= spt_max]
    if df.empty:
        return None

    sptn = df['spectral_type_number'].astype(float).values
    col  = df['color_mag'].astype(float).values

    # Positions for the overlay according to the axes
    if axis_for_color == 'y':
        xvals, yvals = sptn, col
    else:
        xvals, yvals = col, sptn

    # Helper to get spectral class letter and label (no decimals)
    def _class_and_label(s):
        lbl = generate_spectral_type_label(s)
        # Keep just the class letter and integer subclass (e.g., M6)
        try:
            cls = lbl[0]
            # Find first digit run
            # parse_spt_label expects like 'M6' or 'L3.5', but we want integer subclass for the tag
            # We format using nearest integer for cleanliness on the marker text.
            sub = int(round(float(lbl[1:]))) if lbl[1:] else 0
            return cls, f"{cls}{sub}"
        except Exception:
            return 'M', lbl

    # Try to use an existing class colormap from the module if present
    # e.g., CLASS_COLOR_MAP = {'M': '#e53935', 'L': '#fdd835', 'T': '#1e88e5', 'Y': '#8e24aa', 'K': '#6d4c41'}
    _globals = globals()
    class_map = None
    for key in ('CLASS_COLOR_MAP', 'SPT_CLASS_COLORS', 'SPECTRAL_CLASS_COLORS'):
        if key in _globals and isinstance(_globals[key], dict):
            class_map = _globals[key]
            break
    if class_map is None:
        class_map = {
            'M': '#e53935',   # red
            'L': '#fdd835',   # yellow
            'T': '#1e88e5',   # blue
            'Y': '#8e24aa',   # purple
            'K': '#6d4c41',   # brown
            'G': '#fb8c00',   # orange (fallbacks below M if ever shown)
            'F': '#43a047',   # green
            'A': '#8d6e63',
            'B': '#546e7a',
            'O': '#424242',
        }

    classes, labels, colors = [], [], []
    for s in sptn:
        cls, lbl = _class_and_label(s)
        classes.append(cls)
        labels.append(lbl)
        colors.append(class_map.get(cls, '#000000'))

    hover = [f"SPT={generate_spectral_type_label(s)} | color={c:.3f}" for s, c in zip(sptn, col)]

    circle_trace = pgo.Scatter(
        x=xvals,
        y=yvals,
        mode='markers',
        name=name,
        marker=dict(
            size=18,
            color='rgba(0,0,0,0)',   # unfilled
            line=dict(color='black', width=2),
            symbol='circle'
        ),
        hoverinfo='text',
        hovertext=hover,
        showlegend=True
    )

    text_trace = pgo.Scatter(
        x=xvals,
        y=yvals,
        mode='text',
        name=f"{name} labels",
        text=labels,
        textposition='middle center',
        textfont=dict(size=10, color='black'),   # always black text
        hoverinfo='skip',
        showlegend=False
    )

    return [circle_trace, text_trace]

def _add_best18_overlay(fig, engine, x_axis_type, y_axis_type, x_band_values, y_band_values, spt_range):
    """
    Decide which overlay(s) to add based on the axis types and add to fig in place.
    Works for SPT–color, color–SPT, and color–color.
    """
    try:
        spt_min = spt_range.get('min') if isinstance(spt_range, dict) else None
        spt_max = spt_range.get('max') if isinstance(spt_range, dict) else None

        # SPT (x) vs Color (y)
        if x_axis_type == 'spectral_type' and y_axis_type == 'color' and y_band_values and len(y_band_values) >= 2:
            ps1, ps2 = y_band_values[0], y_band_values[1]
            df = _fetch_median_colors_df(engine, ps1, ps2)
            tr = _spt_color_to_markers(df, axis_for_color='y', spt_min=spt_min, spt_max=spt_max)
            if tr is not None:
                if isinstance(tr, list):
                    for _t in tr:
                        fig.add_trace(_t)
                else:
                    fig.add_trace(tr)

        # Color (x) vs SPT (y)
        if x_axis_type == 'color' and y_axis_type == 'spectral_type' and x_band_values and len(x_band_values) >= 2:
            ps1, ps2 = x_band_values[0], x_band_values[1]
            df = _fetch_median_colors_df(engine, ps1, ps2)
            tr = _spt_color_to_markers(df, axis_for_color='x', spt_min=spt_min, spt_max=spt_max)
            if tr is not None:
                if isinstance(tr, list):
                    for _t in tr:
                        fig.add_trace(_t)
                else:
                    fig.add_trace(tr)

        # Color (x) vs Color (y)
        if (x_axis_type == 'color' and y_axis_type == 'color' and
            x_band_values and y_band_values and len(x_band_values) >= 2 and len(y_band_values) >= 2):
            x1, x2 = x_band_values[0], x_band_values[1]
            y1, y2 = y_band_values[0], y_band_values[1]
            dfx = _fetch_median_colors_df(engine, x1, x2)
            dfy = _fetch_median_colors_df(engine, y1, y2)
            if dfx is not None and not dfx.empty and dfy is not None and not dfy.empty:
                m = pd.merge(
                    dfx[['spectral_type_number', 'color_mag']],
                    dfy[['spectral_type_number', 'color_mag']],
                    on='spectral_type_number',
                    suffixes=('_x', '_y')
                ).dropna()
                if not m.empty:
                    sptn = m['spectral_type_number'].astype(float).values
                    xcol = m['color_mag_x'].astype(float).values
                    ycol = m['color_mag_y'].astype(float).values
                    if spt_min is not None:
                        mask = sptn >= spt_min
                        sptn, xcol, ycol = sptn[mask], xcol[mask], ycol[mask]
                    if spt_max is not None:
                        mask = sptn <= spt_max
                        sptn, xcol, ycol = sptn[mask], xcol[mask], ycol[mask]
                    if len(sptn) > 0:
                        # Build labels and class colors
                        def _class_and_label(s):
                            lbl = generate_spectral_type_label(s)
                            try:
                                cls = lbl[0]
                                sub = int(round(float(lbl[1:]))) if lbl[1:] else 0
                                return cls, f"{cls}{sub}"
                            except Exception:
                                return 'M', lbl
                        _globals = globals()
                        class_map = None
                        for key in ('CLASS_COLOR_MAP', 'SPT_CLASS_COLORS', 'SPECTRAL_CLASS_COLORS'):
                            if key in _globals and isinstance(_globals[key], dict):
                                class_map = _globals[key]
                                break
                        if class_map is None:
                            class_map = {'M':'#e53935','L':'#fdd835','T':'#1e88e5','Y':'#8e24aa','K':'#6d4c41','G':'#fb8c00','F':'#43a047','A':'#8d6e63','B':'#546e7a','O':'#424242'}
                        labels = []
                        text_colors = []
                        for s in sptn:
                            cls, lbl = _class_and_label(s)
                            labels.append(lbl)
                            text_colors.append(class_map.get(cls, '#000000'))
                        hover = [f"SPT={generate_spectral_type_label(s)} | x={x:.3f} | y={y:.3f}" for s, x, y in zip(sptn, xcol, ycol)]
                        # Unfilled circle markers
                        fig.add_trace(pgo.Scatter(
                            x=xcol, y=ycol, mode='markers', name='Median colors (Best18)',
                            marker=dict(size=18, color='rgba(0,0,0,0)', line=dict(color='black', width=2), symbol='circle'),
                            hoverinfo='text', hovertext=hover
                        ))
                        # Centered black labels
                        fig.add_trace(pgo.Scatter(
                            x=xcol, y=ycol, mode='text', name='Median colors labels', text=labels,
                            textposition='middle center', textfont=dict(size=10, color='black'), hoverinfo='skip', showlegend=False
                        ))
        # Finally, add any matching reference sequence overlays
        _maybe_add_reference_sequence(fig, engine, x_axis_type, y_axis_type, x_band_values, y_band_values)
    except Exception:
        # Never break the app if overlay has issues
        pass

# Add Gaussian noise for the spt axis
def add_gaussian_noise(data, stddev=0.25, max_amplitude=0.5):
    """
    Add Gaussian noise to the data with the given standard deviation and limit.
    If noise falls outside the range [-max_amplitude, max_amplitude], it is re-generated
    to ensure that all values respect the Gaussian distribution.
    """
    noise = np.random.normal(loc=0, scale=stddev, size=len(data))
    while np.any((noise < -max_amplitude) | (noise > max_amplitude)):
        # Regenerate noise for the out-of-bounds values
        out_of_bounds = (noise < -max_amplitude) | (noise > max_amplitude)
        noise[out_of_bounds] = np.random.normal(loc=0, scale=stddev, size=np.sum(out_of_bounds))
    return data + noise

# Define hovertext lines for each row
def construct_hovertext(row):
    hovertext = [
        f"",
        f"MOCA OID: {row['moca_oid']}",
        f"Main designation: {row['designation']}",
        f"Spectral type: {row['complete_spectral_type']} ({row['spt_ref']})",
        f"Distance: {row['distance_display']} ({row['distance_ref']})",
        f"Age: {row['age']} (Myr)" if 'age' in row and not pd.isna(row['age']) else "",
        f""
    ]
    
    # Add optional keys dynamically
    optional_keys = {
        'x_ref': "",
        'y_ref': "",
        'x_ref_1': "",
        'x_ref_2': "",
        'y_ref_1': "",
        'y_ref_2': "",
    }
    for key, label in optional_keys.items():
        if key in row and not pd.isna(row[key]):
            hovertext.append(f"{label}{row[key]}")

    # Add X and Y axis values
    hovertext.append(f"")
    hovertext.append(f"X-axis value: {row['x_data_display']}")
    hovertext.append(f"Y-axis value: {row['y_data_display']}")

    # Remove duplicate lines while maintaining order, but allow duplicated empty strings
    seen = set()
    unique_hovertext = []
    for line in hovertext:
        if line == "" or line not in seen:  # Allow empty strings but deduplicate others
            unique_hovertext.append(line)
            if line != "":  # Only track non-empty strings
                seen.add(line)
    
    return "<br>".join(unique_hovertext)

def color_format_value_with_error(value, error, unit=""):
    """
    Formats a value with its error, aligning the value's decimal precision with the error.
    If the error is None, zero, or negative, only the value is formatted.
    If the value or error is invalid (e.g., None or 'N/A'), it returns "N/A".
    """
    # Handle invalid value or error
    if pd.isna(value) or value == "N/A":
        return "N/A"
    
    # If the error is invalid (None, zero, or negative), return only the value
    if pd.isna(error) or error <= 0 or error == "N/A":
        return f"{value:.2f}" + (f" {unit}" if unit else "")

    # Calculate the significant digit for the error
    error_magnitude = 10 ** floor(log10(abs(error)))  # Scale of the error
    rounded_error = round(error / error_magnitude) * error_magnitude  # Round error to 1 significant digit

    # Determine the number of decimal places for the error
    significant_digits_error = max(0, -int(floor(log10(abs(rounded_error)))))

    # Round the value to match the decimal places of the error
    rounded_value = round(value, significant_digits_error)

    # Format the result to remove floating-point artifacts
    rounded_value_str = f"{rounded_value:.{significant_digits_error}f}".rstrip('0').rstrip('.')
    rounded_error_str = f"{rounded_error:.{significant_digits_error}f}".rstrip('0').rstrip('.')

    # Return formatted string with ± symbol and unit
    return f"{rounded_value_str} ± {rounded_error_str}" + (f" {unit}" if unit else "")

def format_dataframe_with_error(df, value_col, error_col, unit="", output_col="formatted"):
    """
    Formats a DataFrame column with values and their corresponding errors.

    Parameters:
    - df: pandas DataFrame
    - value_col: Name of the column containing values.
    - error_col: Name of the column containing errors.
    - unit: (Optional) A single string to represent the unit for all rows. Default is an empty string (no units).
    - output_col: Name of the column to store the formatted output.

    Returns:
    - DataFrame with a new column containing the formatted values.
    """
    def apply_format(row):
        return color_format_value_with_error(row[value_col], row[error_col], unit)
    
    df[output_col] = df.apply(apply_format, axis=1)
    return df.copy()

def _modulate_rgba_alpha(color_str, alpha_factor=1.0, default='rgba(0,0,0,1.0)'):
    """
    Return same color with alpha multiplied by alpha_factor.
    Accepts 'rgba(r,g,b,a)', 'rgb(r,g,b)', or '#RRGGBB'.
    """
    if not isinstance(color_str, str) or not color_str:
        color_str = default
    color_str = color_str.strip()
    # rgba
    if color_str.lower().startswith('rgba'):
        try:
            parts = color_str[color_str.find('(')+1:color_str.rfind(')')].split(',')
            r, g, b, a = [p.strip() for p in parts]
            a_val = float(a)
            a_new = max(0.0, min(1.0, a_val * float(alpha_factor)))
            return f'rgba({r},{g},{b},{a_new})'
        except Exception:
            return default
    # rgb
    if color_str.lower().startswith('rgb'):
        try:
            parts = color_str[color_str.find('(')+1:color_str.rfind(')')].split(',')
            r, g, b = [p.strip() for p in parts[:3]]
            a_new = max(0.0, min(1.0, float(alpha_factor)))
            return f'rgba({r},{g},{b},{a_new})'
        except Exception:
            return default
    # hex #RRGGBB
    if color_str.startswith('#') and len(color_str) == 7:
        try:
            r = int(color_str[1:3], 16)
            g = int(color_str[3:5], 16)
            b = int(color_str[5:7], 16)
            a_new = max(0.0, min(1.0, float(alpha_factor)))
            return f'rgba({r},{g},{b},{a_new})'
        except Exception:
            return default
    # Fallback (named colors etc.)
    return default

def _derive_error_color_from_trace(trace, default='#1f77b4'):
    """
    Compute an RGBA for error bars matching the trace's marker (or line) color & opacity.
    If the marker has a per-point color array, we use the first valid entry.
    Fallback order: marker.color -> marker.line.color -> line.color -> default.
    """
    def _first_valid_color(c):
        # Accept string color; if list/tuple, pick first string entry
        if isinstance(c, str) and c:
            return c
        if isinstance(c, (list, tuple)):
            for v in c:
                if isinstance(v, str) and v:
                    return v
        return None

    mcol = None
    try:
        mcol = _first_valid_color(getattr(trace.marker, 'color', None))
    except Exception:
        mcol = None
    if not mcol:
        try:
            mcol = _first_valid_color(getattr(trace.marker, 'line', None).color)
        except Exception:
            mcol = None
    if not mcol:
        try:
            mcol = _first_valid_color(getattr(trace, 'line', None).color)
        except Exception:
            mcol = None
    if not mcol:
        mcol = default

    try:
        op = trace.opacity if trace.opacity is not None else 1.0
    except Exception:
        op = 1.0

    return _modulate_rgba_alpha(mcol, alpha_factor=op, default=default)

# Layout for the page
layout = (
    html.Div([
        dcc.Location(id='url'),  # To track URL and query parameters

        # Title and Description
        html.H1("Substellar Photometry Explorer"),
        html.P(["This page allows you to display the spectral types, absolute magnitudes, colors, spectral indices or equivalent widths of substellar objects in the MOCA database.",html.Br(),
                "While this page is intended for use with brown dwarfs, it can be extended to earlier spectral types too.",html.Br(),
                "You can use the plotly selection tool to obtain a table with the selected objects below the scatter plot, which is downloadable as a CSV file.",html.Br(),
                "You can also list unique MOCA identifiers to highlight them in the figure.",html.Br()]),

        # SPT range
        html.Div([
            html.Label("Spectral type range"),
            dcc.Input(
                id='bdphot-spt-range-input',
                type='text',
                value=None,
                placeholder="Enter range (e.g., '"+default_spt_range+"')",
                debounce=True,  # Trigger only when Enter is pressed
                style={'width': '50%'}
            ),
            html.Div(
                id='bdphot-spt-range-error',  # To display validation errors
                style={'color': 'red', 'marginTop': '0.5rem'}
            )
        ], style={'marginBottom': '1rem'}),

        dcc.Store(id='bdphot-spt-range-store', data={'min': default_spt_range_val[0], 'max': default_spt_range_val[1]}),

        # Grid for dropdowns
        html.Div([
            # Row 1
            html.Div([
                html.Label("X-axis type:"),
                dcc.Dropdown(
                    id='bdphot-x-axis-type-dropdown',
                    options=[
                        {'label': 'Spectral Type', 'value': 'spectral_type'},
                        {'label': 'Color', 'value': 'color'},
                        {'label': 'Absolute Magnitude', 'value': 'absolute_magnitude'},
                        {'label': 'Spectral Index', 'value': 'spectral_index'},
                        {'label': 'Equivalent Width', 'value': 'equivalent_width'}
                    ],
                    placeholder='Select x-axis type',
                )
            ], id='bdphot-cell-1', style={"gridArea": "1 / 1"}),

            html.Div([
                html.Label("Y-axis type:"),
                dcc.Dropdown(
                    id='bdphot-y-axis-type-dropdown',
                    options=[
                        {'label': 'Spectral Type', 'value': 'spectral_type'},
                        {'label': 'Color', 'value': 'color'},
                        {'label': 'Absolute Magnitude', 'value': 'absolute_magnitude'},
                        {'label': 'Spectral Index', 'value': 'spectral_index'},
                        {'label': 'Equivalent Width', 'value': 'equivalent_width'}
                    ],
                    placeholder='Select y-axis type',
                )
            ], id='bdphot-cell-2', style={"gridArea": "1 / 2"}),

            # Row 2
            html.Div(id='bdphot-x-axis-first-band', style={"gridArea": "2 / 1"}),  # Cell 3
            html.Div(id='bdphot-y-axis-first-band', style={"gridArea": "2 / 2"}),  # Cell 4

            # Row 3
            html.Div(id='bdphot-x-axis-second-band', style={"gridArea": "3 / 1"}),  # Cell 5
            html.Div(id='bdphot-y-axis-second-band', style={"gridArea": "3 / 2"}),  # Cell 6
        ], style={
            "display": "grid",
            "gridTemplateColumns": "1fr 1fr",
            "gridTemplateRows": "auto auto auto",
            "gap": "1rem",
            "width": "100%",
        }),

        # MOCA OID Input
        html.Div([
            html.Label("Highlight Specific Objects (MOCA IDs):"),
            dcc.Input(
                id='bdphot-moca-ids-input',
                type='text',
                placeholder="Insert MOCA object IDs separated by commas",
                value=None,  # Dynamically set this value via a callback
                style={'width': '100%'}
            )
        ], style={'marginTop': '1rem'}),

        # Checkboxes in a 2x3 Grid
        html.Div([
            #html.Div([
            #    dcc.Checklist(
            #        options=[{'label': 'Display best photometry only', 'value': 'best_photometry'}],
            #        id='bdphot-checkbox-best-photometry',
            #    )
            #], style={'gridArea': '1 / 1'}),

            html.Div([
                dcc.Checklist(
                    options=[{'label': 'Display measurement errors', 'value': 'display_errors'}],
                    id='bdphot-checkbox-display-errors',
                )
            ], style={'gridArea': '1 / 1'}),

            html.Div([
                dcc.Checklist(
                    options=[{'label': 'Include photometric distance estimates', 'value': 'photometric_distances'}],
                    id='bdphot-checkbox-photometric-distances',
                )
            ], style={'gridArea': '1 / 2'}),

            html.Div([
                dcc.Checklist(
                    options=[{'label': 'Display binary systems', 'value': 'binaries'}],
                    id='bdphot-checkbox-binaries',
                )
            ], style={'gridArea': '2 / 1'}),
            html.Div([
                dcc.Checklist(
                    options=[{'label': 'Include photometric spectral type estimates', 'value': 'spectral_type_estimates'}],
                    id='bdphot-checkbox-spectral-type-estimates',
                )
            ], style={'gridArea': '2 / 2'}),
            html.Div([
                dcc.Checklist(
                    options=[{'label': 'Color-code by age', 'value': 'color_by_age'}],
                    id='bdphot-checkbox-color-by-age',
                )
            ], style={'gridArea': '3 / 1'}),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "1fr 1fr",
            "gridTemplateRows": "auto auto auto",
            "gap": "1rem",
            "marginTop": "1rem",
        }),

        # Photometry error filters
        html.Div([
            html.Label("Fade and shrink large errors:"),
            html.Div([
                html.Div([
                    html.Label("Max X-axis measurement error (mag):"),
                    dcc.Input(
                        id='bdphot-x-err-threshold',
                        type='number',
                        placeholder="e.g. 0.1",
                        min=0,
                        step=0.001,
                        debounce=True,
                        style={'width': '100%'}
                    ),
                    html.Small(
                        "Points with σ_x above this will be drawn transparent and ignored for X limits.",
                        style={'display': 'block', 'color': '#666'}
                    )
                ], style={'gridArea': '1 / 1'}),
                html.Div([
                    html.Label("Max Y-axis measurement error (mag):"),
                    dcc.Input(
                        id='bdphot-y-err-threshold',
                        type='number',
                        placeholder="e.g. 0.1",
                        min=0,
                        step=0.001,
                        debounce=True,
                        style={'width': '100%'}
                    ),
                    html.Small(
                        "Points with σ_y above this will be drawn transparent and ignored for Y limits.",
                        style={'display': 'block', 'color': '#666'}
                    )
                ], style={'gridArea': '1 / 2'}),
            ], style={
                "display": "grid",
                "gridTemplateColumns": "1fr 1fr",
                "gridTemplateRows": "auto",
                "gap": "1rem",
            }),
        ], style={'marginTop': '1rem'}),

        # Scatter Plot
        dcc.Graph(id='bdphot-scatter-plot', config=figure_export_config, clickData=None),
        
        # Clicked moca_oid store
        dcc.Store(id='bdphot-clicked-moca-oid'),

        # Dummy output used by the click-window open architecture
        html.Div(id="bdphot-dummy-output", style={"display": "none"}),

        # Missing MOCA IDs display
        html.Div(id='bdphot-missing-moca-ids', style={'color': 'red', 'marginTop': '1rem'}),

        # Component that stores merged_data
        dcc.Store(id='bdphot-merged-data-store'),  # Add a Store component
    
    ], style={'width': '65%', 'display': 'inline-block','padding-left': '15px'}), 

    # Export button and download component
    html.Div([
        html.Button("Export Table to CSV", id="bdphot-export-button", n_clicks=0),
        dcc.Download(id="bdphot-export-dataframe-csv"),  # Component for download
    ], style={'marginTop': '1rem', 'textAlign': 'left', 'padding-left': '15px'}),

    # Add the table as a separate full-width section    
    html.Div(
        id='bdphot-selected-data-table',
        style={
            'marginTop': '1rem',
            'width': '100%',  # Ensure full window width
            'padding': '0',  # Remove padding for proper alignment
            'padding-left': '15px',
            'marginBottom': '2rem',
            'boxSizing': 'border-box',  # Include padding/border in the width calculation
        }
    ),
    html.Div(
        className="row",
        id="url-help-section-bdcolors",
        children=[
            html.Hr(),
            dcc.Markdown(
                """
                ## Using URL Parameters

                You can customize the visualization by adding parameters to the URL using the `?param=value` format and separating multiple parameters with `&`.

                ### Available URL Parameters
                - **xaxis_type** → Sets the observable for the X-axis. Valid values: **spectral_type**, **color**, **absolute_magnitude**, **spectral_index**, **equivalent_width**.
                - **yaxis_type** → Sets the observable for the Y-axis. Valid values: **spectral_type**, **color**, **absolute_magnitude**, **spectral_index**, **equivalent_width**.
                - **xaxis_value_1** → Specifies the first band or index for the X-axis (e.g., `mko_jmag`).
                - **xaxis_value_2** → Specifies the second band for the X-axis when using some axis types that require it.
                - **yaxis_value_1** → Specifies the first band or index for the Y-axis.
                - **yaxis_value_2** → Specifies the second band for the Y-axis when using some axis types that require it.
                - **moca_oid** → Highlights specific objects by their MOCA OID. You can list multiple OIDs separated by commas.
                - **spt_range** → Sets the spectral type range. Use the format like `M6-Y2`.
                - **errors** → Display measurement errors. Set to `true` to activate or `false` to deactivate. Default is `false`.
                - **photdist** → Includes photometric distance estimates. Set to `true` to activate or `false` to deactivate. Default is `false`.
                - **binaries** → Displays binary systems. Set to `true` to activate or `false` to deactivate. Default is `false`.
                - **agecolor** → Enables color-coding by association age. Set to `true` to activate or `false` to deactivate. Default is `false`.
                - **photspt** → Includes photometric spectral type estimates. Set to `true` to activate or `false` to deactivate. Default is `false`.
                - **xerr_max** → Maximum allowed *measurement* uncertainty (σ, in mag) for the X-axis. Points above this are faded/shrunk and excluded from X-axis limits.
                - **yerr_max** → Maximum allowed *measurement* uncertainty (σ, in mag) for the Y-axis. Points above this are faded/shrunk and excluded from Y-axis limits.

                ### Example URLs  
                - `https://dataviz.mocadb.ca/bd-colors?xaxis_type=color&yaxis_type=absolute_magnitude&yaxis_value_1=mko_jmag&xaxis_value_1=mko_jmag&xaxis_value_2=mko_kmag&moca_oid=602&binaries=true`
                - `https://dataviz.mocadb.ca/bd-colors?xaxis_type=spectral_type&yaxis_type=absolute_magnitude&yaxis_value_1=mko_jmag&moca_oid=602`
                - `https://dataviz.mocadb.ca/bd-colors?xaxis_type=spectral_type&yaxis_type=spectral_index&yaxis_value_1=h2o_j&moca_oid=602`

                Clicking on a data point in the plot will open its detailed MOCA report in a new tab.
                """
            ),#- **bestphot** → Enables best photometry only. Set to `true` to activate or `false` to deactivate. Default is `true`.
        ],
        style={"padding": "20px", "backgroundColor": "#f9f9f9"}
    ),
)

@dash.callback(
    Output('bdphot-x-err-threshold', 'value'),
    Output('bdphot-y-err-threshold', 'value'),
    Input('url', 'href')
)
def update_error_thresholds_from_url(url):
    params = parse_url_params(url)
    x_raw = params.get('xerr_max', [None])[0]
    y_raw = params.get('yerr_max', [None])[0]
    def _to_float(v):
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None
    return _to_float(x_raw), _to_float(y_raw)

def parse_url_params(url):
    """Parse URL parameters into a dictionary."""
    parsed_url = urlparse(url)
    return parse_qs(parsed_url.query)

def get_connection_string(url):
    """Build connection string from environment variables or defaults."""
    
    # Parse URL parameters
    parsed_url = urlparse(url)
    parsed_url_data = parse_qs(parsed_url.query)
    
    # Check for moca_oid in the URL query parameters
    moca_oid_param = parsed_url_data.get('moca_oid', [None])[0]

    env_username = parsed_url_data.get('user', [None])[0]
    env_password = parsed_url_data.get('pwd', [None])[0]
    env_dbname = parsed_url_data.get('dbase', [None])[0]

    default_host = '104.248.106.21'
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

    connection_string = f'mysql+pymysql://{env_username}:{urlquote(env_password)}@{env_host}/{env_dbname}'
    
    return connection_string

def fetch_moca_photometry_systems(url):
    """Fetch moca_psid and related data from moca_photometry_systems."""
    connection_string = get_connection_string(url)
    engine = create_engine(connection_string)
    with engine.connect() as connection:
        metadata = MetaData()
        moca_photometry_systems = Table('moca_photometry_systems', metadata, autoload_with=engine)
        photometry_query = select([moca_photometry_systems])
        return pd.read_sql(photometry_query, connection)

def fetch_moca_spectral_indices(url):
    """Fetch moca_psid and related data from moca_photometry_systems."""
    connection_string = get_connection_string(url)
    engine = create_engine(connection_string)
    with engine.connect() as connection:
        metadata = MetaData()
        moca_spectral_indices = Table('moca_spectral_indices', metadata, autoload_with=engine)
        spi_query = select([moca_spectral_indices])
        return pd.read_sql(spi_query, connection)
    
def fetch_moca_equivalent_widths(url):
    """Fetch moca_psid and related data from moca_photometry_systems."""
    connection_string = get_connection_string(url)
    engine = create_engine(connection_string)
    with engine.connect() as connection:
        metadata = MetaData()
        moca_chemical_species = Table('moca_chemical_species', metadata, autoload_with=engine)
        csi_query = select([moca_chemical_species])
        return pd.read_sql(csi_query, connection)

@dash.callback(
    Output('bdphot-x-axis-first-band', 'children'),
    [Input('bdphot-x-axis-type-dropdown', 'value')],
    State('url', 'href')
)
def update_x_axis_first_band(axis_type, url):
    
    if axis_type not in one_value_axis_types and axis_type not in two_values_axis_types:
        return None  # Clear the dropdown if the type doesn't match
    
    if (axis_type in one_value_axis_types) or (axis_type in two_values_axis_types):
        # Parse URL parameters
        url_params = parse_url_params(url)
        url_default_value = url_params.get('xaxis_value_1', [None])[0]

        if axis_type in ['color', 'absolute_magnitude']:
            
            # Fetch photometry systems for dropdown options
            photometry_systems = fetch_moca_photometry_systems(url)
            if photometry_systems.empty:
                return html.Div([
                    html.Label("Select first band for the x-axis:"),
                    dcc.Dropdown(
                        id={'type': 'bdphot-dynamic-dropdown', 'axis': 'x', 'band': 'first'},
                        options=[],  # No options available
                        placeholder="No photometry systems available",
                    )
                ])

            options = [
                {'label': f"{row['name']} ({row['moca_psid']})", 'value': row['moca_psid']}
                for _, row in photometry_systems.iterrows()
            ]

            # Ensure the default value is valid for this axis type
            default_value = url_default_value if url_default_value in photometry_systems['moca_psid'].tolist() else None

            return html.Div([
                html.Label("Select first band for the x-axis:"),
                dcc.Dropdown(
                    id={'type': 'bdphot-dynamic-dropdown', 'axis': 'x', 'band': 'first'},
                    options=options,
                    value=default_value,  # Set default value from URL
                    placeholder="Select first band",
                )
            ])
        
        if axis_type in ['spectral_index']:

            # Fetch valid spectral indices for dropdown options
            spectral_indices = fetch_moca_spectral_indices(url)
            if spectral_indices.empty:
                return html.Div([
                    html.Label("Select spectral index for the x-axis:"),
                    dcc.Dropdown(
                        id={'type': 'bdphot-dynamic-dropdown', 'axis': 'x', 'band': 'first'},
                        options=[],  # No options available
                        placeholder="No spectral index available",
                    )
                ])
        
            options = [
                {'label': f"{row['description']} ({row['moca_siid']})", 'value': row['moca_siid']}
                for _, row in spectral_indices.iterrows()
            ]

            # Ensure the default value is valid for this axis type
            default_value = url_default_value if url_default_value in spectral_indices['moca_siid'].tolist() else None
            
            return html.Div([
                html.Label("Select spectral index for the x-axis:"),
                dcc.Dropdown(
                    id={'type': 'bdphot-dynamic-dropdown', 'axis': 'x', 'band': 'first'},
                    options=options,
                    value=default_value,  # Set default value from URL
                    placeholder="Select spectral index",
                )
            ])
        
        if axis_type in ['equivalent_width']:

            # Fetch valid spectral indices for dropdown options
            equivalent_widths = fetch_moca_equivalent_widths(url)
            if equivalent_widths.empty:
                return html.Div([
                    html.Label("Select chemical species for the x-axis equivalent width:"),
                    dcc.Dropdown(
                        id={'type': 'bdphot-dynamic-dropdown', 'axis': 'x', 'band': 'first'},
                        options=[],  # No options available
                        placeholder="No chemical species for equivalent width calculations are available",
                    )
                ])
        
            options = [
                {'label': f"{row['description']} ({row['moca_spid']})", 'value': row['moca_spid']}
                for _, row in equivalent_widths.iterrows()
            ]

            # Ensure the default value is valid for this axis type
            default_value = url_default_value if url_default_value in equivalent_widths['moca_spid'].tolist() else None
            
            return html.Div([
                html.Label("Select chemical species for the x-axis equivalent width:"),
                dcc.Dropdown(
                    id={'type': 'bdphot-dynamic-dropdown', 'axis': 'x', 'band': 'first'},
                    options=options,
                    value=default_value,  # Set default value from URL
                    placeholder="Select chemical species",
                )
            ])

    return html.Div()

@dash.callback(
    Output('bdphot-x-axis-second-band', 'children'),
    [Input('bdphot-x-axis-type-dropdown', 'value')],
    State('url', 'href')
)
def update_x_axis_second_band(axis_type, url):
    
    if axis_type in two_values_axis_types:
        # Parse URL parameters
        url_params = parse_url_params(url)
        url_default_value = url_params.get('xaxis_value_2', [None])[0]

        # Fetch photometry systems for dropdown options
        photometry_systems = fetch_moca_photometry_systems(url)
        if photometry_systems.empty:
            return html.Div([
                html.Label("Select second band for the x-axis:"),
                dcc.Dropdown(
                    id={'type': 'bdphot-dynamic-dropdown', 'axis': 'x', 'band': 'second'},
                    options=[],  # No options available
                    placeholder="No photometry systems available",
                )
            ])
        
        options = [
            {'label': f"{row['name']} ({row['moca_psid']})", 'value': row['moca_psid']}
            for _, row in photometry_systems.iterrows()
        ]

        # Ensure the default value is valid for this axis type
        default_value = url_default_value if url_default_value in photometry_systems['moca_psid'].tolist() else None
            
        return html.Div([
            html.Label("Select second band for the x-axis:"),
            dcc.Dropdown(
                id={'type': 'bdphot-dynamic-dropdown', 'axis': 'x', 'band': 'second'},
                options=options,
                value=default_value,  # Set default value from URL
                placeholder="Select second band",
            )
        ])
    return html.Div()

@dash.callback(
    Output('bdphot-y-axis-first-band', 'children'),
    [Input('bdphot-y-axis-type-dropdown', 'value')],
    State('url', 'href')
)
def update_y_axis_first_band(axis_type, url):
    
    # Reset logic
    if axis_type not in one_value_axis_types and axis_type not in two_values_axis_types:
        return None  # Clear the dropdown if the type doesn't match
    
    if (axis_type in one_value_axis_types) or (axis_type in two_values_axis_types):
        # Parse URL parameters
        url_params = parse_url_params(url)
        url_default_value = url_params.get('yaxis_value_1', [None])[0]

        if axis_type in ['color', 'absolute_magnitude']:
            
            # Fetch photometry systems for dropdown options
            photometry_systems = fetch_moca_photometry_systems(url)
            if photometry_systems.empty:
                return html.Div([
                    html.Label("Select second band for the x-axis:"),
                    dcc.Dropdown(
                        id={'type': 'bdphot-dynamic-dropdown', 'axis': 'y', 'band': 'first'},
                        options=[],  # No options available
                        placeholder="No photometry systems available",
                    )
                ])
        
            options = [
                {'label': f"{row['name']} ({row['moca_psid']})", 'value': row['moca_psid']}
                for _, row in photometry_systems.iterrows()
            ]

            # Ensure the default value is valid for this axis type
            default_value = url_default_value if url_default_value in photometry_systems['moca_psid'].tolist() else None

            return html.Div([
                html.Label("Select first band for the y-axis:"),
                dcc.Dropdown(
                    id={'type': 'bdphot-dynamic-dropdown', 'axis': 'y', 'band': 'first'},
                    options=options,
                    value=default_value,  # Set default value from URL
                    placeholder="Select first band",
                )
            ])

        if axis_type in ['spectral_index']:

            # Fetch valid spectral indices for dropdown options
            spectral_indices = fetch_moca_spectral_indices(url)
            if spectral_indices.empty:
                return html.Div([
                    html.Label("Select spectral index for the y-axis:"),
                    dcc.Dropdown(
                        id={'type': 'bdphot-dynamic-dropdown', 'axis': 'y', 'band': 'first'},
                        options=[],  # No options available
                        placeholder="No spectral index available",
                    )
                ])
            
            options = [
                {'label': f"{row['description']} ({row['moca_siid']})", 'value': row['moca_siid']}
                for _, row in spectral_indices.iterrows()
            ]

            # Ensure the default value is valid for this axis type
            default_value = url_default_value if url_default_value in spectral_indices['moca_siid'].tolist() else None

            return html.Div([
                html.Label("Select spectral index for the y-axis:"),
                dcc.Dropdown(
                    id={'type': 'bdphot-dynamic-dropdown', 'axis': 'y', 'band': 'first'},
                    options=options,
                    value=default_value,  # Set default value from URL
                    placeholder="Select spectral index",
                )
            ])
        
        if axis_type in ['equivalent_width']:

            # Fetch valid spectral indices for dropdown options
            equivalent_widths = fetch_moca_equivalent_widths(url)
            if equivalent_widths.empty:
                return html.Div([
                    html.Label("Select chemical species for the y-axis equivalent width:"),
                    dcc.Dropdown(
                        id={'type': 'bdphot-dynamic-dropdown', 'axis': 'y', 'band': 'first'},
                        options=[],  # No options available
                        placeholder="No chemical species for equivalent width calculations are available",
                    )
                ])
        
            options = [
                {'label': f"{row['description']} ({row['moca_spid']})", 'value': row['moca_spid']}
                for _, row in equivalent_widths.iterrows()
            ]

            # Ensure the default value is valid for this axis type
            default_value = url_default_value if url_default_value in equivalent_widths['moca_spid'].tolist() else None
            
            return html.Div([
                html.Label("Select chemical species for the y-axis equivalent width:"),
                dcc.Dropdown(
                    id={'type': 'bdphot-dynamic-dropdown', 'axis': 'y', 'band': 'first'},
                    options=options,
                    value=default_value,  # Set default value from URL
                    placeholder="Select chemical species",
                )
            ])
    
    return html.Div()

@dash.callback(
    Output('bdphot-y-axis-second-band', 'children'),
    [Input('bdphot-y-axis-type-dropdown', 'value')],
    State('url', 'href')
)
def update_y_axis_second_band(axis_type, url):
    
    if axis_type in two_values_axis_types:
        # Parse URL parameters
        url_params = parse_url_params(url)
        url_default_value = url_params.get('yaxis_value_2', [None])[0]

        # Fetch photometry systems for dropdown options
        photometry_systems = fetch_moca_photometry_systems(url)
        if photometry_systems.empty:
            return html.Div([
                html.Label("Select second band for the y-axis:"),
                dcc.Dropdown(
                    id={'type': 'bdphot-dynamic-dropdown', 'axis': 'y', 'band': 'second'},
                    options=[],  # No options available
                    placeholder="No photometry systems available",
                )
            ])
        
        options = [
            {'label': f"{row['name']} ({row['moca_psid']})", 'value': row['moca_psid']}
            for _, row in photometry_systems.iterrows()
        ]
        default_value = url_default_value if url_default_value in photometry_systems['moca_psid'].tolist() else None

        return html.Div([
            html.Label("Select second band for the y-axis:"),
            dcc.Dropdown(
                id={'type': 'bdphot-dynamic-dropdown', 'axis': 'y', 'band': 'second'},
                options=options,
                value=default_value,  # Set default value from URL
                placeholder="Select second band",
            )
        ])
    return html.Div()

@dash.callback(
    [
        Output('bdphot-x-axis-type-dropdown', 'value'),
        Output('bdphot-y-axis-type-dropdown', 'value'),
    ],
    Input('url', 'href')
)
def update_dropdowns_from_url(url):
    # Parse the URL parameters
    url_params = parse_url_params(url)

    # Extract x-axis and y-axis types from parameters
    xaxis_type = url_params.get('xaxis_type', [None])[0]
    yaxis_type = url_params.get('yaxis_type', [None])[0]

    # Validate x-axis type
    if xaxis_type not in ['spectral_type', 'absolute_magnitude', 'color', 'spectral_index', 'equivalent_width']:
        xaxis_type = None  # Default value

    # Validate y-axis type
    if yaxis_type not in ['spectral_type', 'absolute_magnitude', 'color', 'spectral_index', 'equivalent_width']:
        yaxis_type = None  # Default value

    # Return the validated or default values
    return xaxis_type, yaxis_type

@dash.callback(
    [
        Output('bdphot-scatter-plot', 'figure'),
        Output('bdphot-missing-moca-ids', 'children'),  # For missing MOCA IDs
        Output('bdphot-merged-data-store', 'data')  # Save `merged_data` to the Store
    ],
    [
        Input('bdphot-x-axis-type-dropdown', 'value'),
        Input('bdphot-y-axis-type-dropdown', 'value'),
        Input('bdphot-x-axis-type-dropdown', 'options'),  # Access options of x-axis dropdown
        Input('bdphot-y-axis-type-dropdown', 'options'),  # Access options of y-axis dropdown
        Input({'type': 'bdphot-dynamic-dropdown', 'axis': 'x', 'band': ALL}, 'value'),
        Input({'type': 'bdphot-dynamic-dropdown', 'axis': 'y', 'band': ALL}, 'value'),
        Input('bdphot-moca-ids-input', 'value'),
        Input('bdphot-moca-ids-input', 'n_submit'),  # Trigger on Enter
        #Input('bdphot-checkbox-best-photometry', 'value'),
        Input('bdphot-checkbox-display-errors', 'value'),
        Input('bdphot-checkbox-photometric-distances', 'value'),
        Input('bdphot-checkbox-binaries', 'value'),
        Input('bdphot-checkbox-spectral-type-estimates', 'value'),
        Input('bdphot-checkbox-color-by-age', 'value'),
        Input('bdphot-spt-range-store', 'data'), 
        Input('bdphot-x-err-threshold', 'value'),
        Input('bdphot-y-err-threshold', 'value'),
    ],
    State('url', 'href')
)
#, best_photometry_value
def update_plot(x_axis_type, y_axis_type, x_axis_options, y_axis_options, x_band_values, y_band_values, moca_ids, n_submit, display_errors_value, photometric_distances_value, binaries_value, spectral_type_estimates_value, color_by_age_value, spt_range, x_err_threshold, y_err_threshold, url):
    
    # Placeholders for MOCA-style axis ranges (also used by "Home")
    custom_xrange = None
    custom_yrange = None
    
    # Interpret the highlighted moca_oids
    # Process moca_ids only when Enter is pressed
    moca_ids_array = []
    if n_submit and moca_ids:
        try:
            moca_ids_array = [int(moca_id.strip()) for moca_id in moca_ids.split(',') if moca_id.strip()]
        except ValueError:
            moca_ids_array = []

    # Read URL fallbacks for error thresholds if inputs are None
    url_params_local = parse_url_params(url)
    if x_err_threshold is None:
        try:
            x_err_threshold = float(url_params_local.get('xerr_max', [None])[0])
        except Exception:
            pass
    if y_err_threshold is None:
        try:
            y_err_threshold = float(url_params_local.get('yerr_max', [None])[0])
        except Exception:
            pass

    # Extract labels for the selected axis types
    x_axis_type_label = next((opt['label'] for opt in x_axis_options if opt['value'] == x_axis_type), None)
    y_axis_type_label = next((opt['label'] for opt in y_axis_options if opt['value'] == y_axis_type), None)

    if x_band_values:
        # Get the input IDs and associated values from callback context
        input_ids_and_values = [
            (item['id'], value) 
            for item, value in zip(dash.callback_context.inputs_list[4], x_band_values)
        ]

        # Sort based on the 'band' key in the ID
        sorted_band_values = sorted(
            input_ids_and_values, 
            key=lambda item: item[0]['band']
        )

        # Extract the values in the correct order
        x_band_values = [value for _, value in sorted_band_values]
    
    if y_band_values:
        # Get the input IDs and associated values from callback context
        input_ids_and_values = [
            (item['id'], value) 
            for item, value in zip(dash.callback_context.inputs_list[5], y_band_values)
        ]

        # Sort based on the 'band' key in the ID
        sorted_band_values = sorted(
            input_ids_and_values, 
            key=lambda item: item[0]['band']
        )

        # Extract the values in the correct order
        y_band_values = [value for _, value in sorted_band_values]
    
    # Define empty figure in case no data is returned
    empty_figure = go.Figure()
    empty_figure.update_layout(
        title="No data available",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        annotations=[
            dict(
                x=0.5, y=0.5, xref="paper", yref="paper",
                text="Select X and Y axes to be displayed",
                showarrow=False,
                font=dict(size=16)
                )
            ]
        )

    empty_figure_noresults = go.Figure()
    empty_figure_noresults.update_layout(
        title="No data available",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False),
        annotations=[
            dict(
                x=0.5, y=0.5, xref="paper", yref="paper",
                text="No valid data points were returned for this combination of observables",
                showarrow=False,
                font=dict(size=16)
                )
            ]
        )
    
    def _message_figure(msg):
        fig = go.Figure()
        fig.update_layout(
            title="No data available",
            xaxis=dict(showgrid=False, zeroline=False),
            yaxis=dict(showgrid=False, zeroline=False),
            annotations=[dict(
                x=0.5, y=0.5, xref="paper", yref="paper",
                text=msg, showarrow=False, font=dict(size=16)
            )]
        )
        return fig

    # Check if all dropdowns are correctly filled
    if x_axis_type == 'absolute_magnitude':
        if len(x_band_values) < 1 or any(v is None for v in x_band_values):
            return empty_figure, None, None
    if y_axis_type == 'absolute_magnitude':
        if len(y_band_values) < 1 or any(v is None for v in y_band_values):
            return empty_figure, None, None
    if x_axis_type == 'color':
        if len(x_band_values) < 2 or any(v is None for v in x_band_values):
            return empty_figure, None, None
        if (len(x_band_values) >= 2) and (x_band_values[0] == x_band_values[1]):
            return _message_figure("Please select two distinct photometric bands for the desired colors"), None, None
    if y_axis_type == 'color':
        if len(y_band_values) < 2 or any(v is None for v in y_band_values):
            return empty_figure, None, None
        if (len(y_band_values) >= 2) and (y_band_values[0] == y_band_values[1]):
            return _message_figure("Please select two distinct photometric bands for the desired colors"), None, None
    if x_axis_type == 'spectral_index':
        if len(x_band_values) < 1 or any(v is None for v in x_band_values):
            return empty_figure, None, None
    if y_axis_type == 'spectral_index':
        if len(y_band_values) < 1 or any(v is None for v in y_band_values):
            return empty_figure, None, None
    if x_axis_type == 'equivalent_width':
        if len(x_band_values) < 1 or any(v is None for v in x_band_values):
            return empty_figure, None, None
    if y_axis_type == 'equivalent_width':
        if len(y_band_values) < 1 or any(v is None for v in y_band_values):
            return empty_figure, None, None

    want_age_color = isinstance(color_by_age_value, (list, tuple)) and ('color_by_age' in color_by_age_value)

    connection_string = get_connection_string(url)

    # Establish connection
    engine = create_engine(connection_string)
    metadata = MetaData()

    # Query data
    with engine.connect() as connection:
        
        x_data = pd.DataFrame()
        y_data = pd.DataFrame()

        # --- Age-coloring tables & helpers ---
        moca_banyan_sigma_models = Table('moca_banyan_sigma_models', metadata, autoload_with=engine)
        calc_banyan_sigma         = Table('calc_banyan_sigma',         metadata, autoload_with=engine)
        data_association_ages     = Table('data_association_ages',     metadata, autoload_with=engine)
        # Adopted BANYAN Sigma model id (scalar subquery)
        adopted_bsmdid_sq = select([moca_banyan_sigma_models.c.moca_bsmdid])\
            .where(moca_banyan_sigma_models.c.adopted == 1)\
            .limit(1)\
            .as_scalar()
        
        def with_age_left_joins(sel_from):
            """If age coloring requested, LEFT JOIN cbs and daa with the required constraints."""
            if not want_age_color:
                return sel_from
            return (
                sel_from
                .outerjoin(
                    calc_banyan_sigma,
                    (calc_banyan_sigma.c.moca_oid == moca_objects.c.moca_oid) &
                    (calc_banyan_sigma.c.max_observables == 1) &
                    (calc_banyan_sigma.c.moca_aid.isnot(None)) &
                    (calc_banyan_sigma.c.ya_prob >= 80) &
                    (calc_banyan_sigma.c.moca_bsmdid == adopted_bsmdid_sq)
                )
                .outerjoin(
                    data_association_ages,
                    (data_association_ages.c.moca_aid == calc_banyan_sigma.c.moca_aid) &
                    (data_association_ages.c.age_myr.isnot(None)) &
                    (data_association_ages.c.adopted == 1)
                )
            )

        def add_age_column(columns):
            """If age coloring requested, include daa.age_myr as age."""
            if not want_age_color:
                return columns
            return columns + [func.min(data_association_ages.c.age_myr).label('age')]

        # --- General Tables ---
        cdata_spectral_types = Table('cdata_spectral_types', metadata, autoload_with=engine)
        moca_objects = Table('moca_objects', metadata, autoload_with=engine)
        cdata_distances = Table('cdata_distances', metadata, autoload_with=engine)
        moca_publications = Table('moca_publications', metadata, autoload_with=engine)
        data_parallaxes = Table('data_parallaxes', metadata, autoload_with=engine)
        mechanics_object_properties_combined = Table('mechanics_object_properties_combined', metadata, autoload_with=engine)
        spt_publications = moca_publications.alias('spt_publications')
        distance_publications = moca_publications.alias('distance_publications')
        parallax_publications = moca_publications.alias('parallax_publications')
        
        # Define the distance join condition based on checkbox
        
        if 'photometric_distances' not in photometric_distances_value:
            distance_join_condition = (
                (cdata_distances.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                (cdata_distances.c.adopted == 1) &
                ((cdata_distances.c.photometric_estimate == 0) | (cdata_distances.c.photometric_estimate.is_(None)))
            )
        else:
            distance_join_condition = (
                (cdata_distances.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                (cdata_distances.c.adopted == 1)
            )

        # Add a filter for binary systems if the checkbox is off
        binary_filter = None
        if 'binaries' not in binaries_value:
            binary_filter = (~(
                mechanics_object_properties_combined.c.all_prop_confidences.like('%multiple_system:C%') |
                mechanics_object_properties_combined.c.all_prop_confidences.like('%multiple_system:Y%')
            ) | (mechanics_object_properties_combined.c.all_prop_confidences.is_(None))) | (cdata_spectral_types.c.moca_oid.in_(moca_ids_array))

        # Add filter for photometric spectral type estimates
        if 'spectral_type_estimates' not in spectral_type_estimates_value:
            spectral_type_filter = (cdata_spectral_types.c.photometric_estimate == 0) | (cdata_spectral_types.c.moca_oid.in_(moca_ids_array))
        else:
            spectral_type_filter = True  # No filter applied

        if x_axis_type == 'spectral_index' or y_axis_type == 'spectral_index':
            moca_spectral_indices = Table('moca_spectral_indices', metadata, autoload_with=engine)
            cdata_spectral_indices = Table('cdata_spectral_indices', metadata, autoload_with=engine)
            spectral_index_publications = moca_publications.alias('spectral_index_publications')

        if x_axis_type == 'equivalent_width' or y_axis_type == 'equivalent_width':
            moca_equivalent_widths = Table('moca_chemical_species', metadata, autoload_with=engine)
            cdata_equivalent_widths = Table('cdata_equivalent_widths', metadata, autoload_with=engine)
            equivalent_widths_publications = moca_publications.alias('equivalent_widths_publications')

        if x_axis_type == 'absolute_magnitude' or y_axis_type == 'absolute_magnitude' or x_axis_type == 'color' or y_axis_type == 'color':
            # Determine which photometry table to use
            #if 'best_photometry' in best_photometry_value:
            #    photometry = Table('mechanics_best_photometry_by_band', metadata, autoload_with=engine)
            #else:
            photometry = Table('cdata_photometry', metadata, autoload_with=engine)
            photsys = Table('moca_photometry_systems', metadata, autoload_with=engine)
            photometry_publications = moca_publications.alias('photometry_publications')

        #Alias the photometry table if needed
        if x_axis_type == 'color' or y_axis_type == 'color':
            phot1 = photometry.alias('phot1')
            phot2 = photometry.alias('phot2')
            photsys1 = photsys.alias('photsys1')
            photsys2 = photsys.alias('photsys2')
            photometry_publications1 = moca_publications.alias('photometry_publications1')
            photometry_publications2 = moca_publications.alias('photometry_publications2')
        
        if x_axis_type == 'spectral_type' or y_axis_type == 'spectral_type':
            spt_query = (
                select(add_age_column([
                    cdata_spectral_types.c.moca_oid,
                    func.min(moca_objects.c.designation).label('designation'),  # Take the first designation
                    func.min(cdata_spectral_types.c.spectral_type_number).label('spectral_type_number'),
                    func.min(cdata_spectral_types.c.spectral_type_unc).label('spectral_type_unc'),
                    func.min(cdata_spectral_types.c.spectral_class).label('spectral_class'),
                    func.min(cdata_spectral_types.c.suffix).label('suffix'),
                    func.min(cdata_spectral_types.c.gravity_class).label('gravity_class'),
                    func.min(cdata_spectral_types.c.complete_spectral_type).label('complete_spectral_type'),
                    func.min(cdata_distances.c.distance_pc).label('distance_pc'),
                    func.min(cdata_distances.c.distance_pc_unc).label('distance_pc_unc'),
                    func.min(
                        func.coalesce(func.coalesce(spt_publications.c.name, spt_publications.c.moca_pid), cdata_spectral_types.c.origin)
                    ).label('spt_ref'),
                    func.min(
                        func.coalesce(func.coalesce(func.coalesce(func.coalesce(func.coalesce(func.coalesce(distance_publications.c.name, distance_publications.c.moca_pid),parallax_publications.c.name),parallax_publications.c.moca_pid),data_parallaxes.c.origin),cdata_distances.c.calculation_method),cdata_distances.c.origin)
                    ).label('distance_ref'),
                    case(
                        [
                            # Young brown dwarfs condition
                            (
                                (cdata_spectral_types.c.gravity_class.in_(['γ', 'β', 'β-γ', 'δ', 'β/γ', 'low gravity', 'low-gravity'])) |
                                (cdata_spectral_types.c.gravity_class.like('VL-G%')) |
                                (cdata_spectral_types.c.gravity_class.like('INT-G%')) |
                                (cdata_spectral_types.c.suffix.like('%red%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%red%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%VL-G%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%INT-G%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%γ%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%β%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%δ%')),
                                'young'
                            ),
                            # Subdwarfs condition
                            (
                                (cdata_spectral_types.c.suffix.like('sd%')) |
                                (cdata_spectral_types.c.suffix.like('esd%')) |
                                (cdata_spectral_types.c.suffix.like('d/sd%')) |
                                (cdata_spectral_types.c.suffix.like('%blue%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('sd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('esd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('d/sd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%blue%')),
                                'old'
                            ),
                        ],
                        else_='field'  # Default to 'field'
                    ).label('age_sample')
                ]))
                .select_from(with_age_left_joins(
                    cdata_spectral_types
                    .join(moca_objects, moca_objects.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    .outerjoin(cdata_distances, distance_join_condition)
                    .outerjoin(
                        spt_publications,
                        (spt_publications.c.moca_pid == cdata_spectral_types.c.moca_pid)
                    )
                    .outerjoin(
                        distance_publications,
                        (distance_publications.c.moca_pid == cdata_distances.c.moca_pid)
                    )
                    .outerjoin(
                        data_parallaxes,
                        (data_parallaxes.c.id == cdata_distances.c.parallax_id)
                    )
                    .outerjoin(
                        parallax_publications,
                        (parallax_publications.c.moca_pid == data_parallaxes.c.moca_pid)
                    )
                    .outerjoin(
                        mechanics_object_properties_combined,
                        (mechanics_object_properties_combined.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    )
                ))
                .where(
                    ((cdata_spectral_types.c.adopted == 1) &
                    (((cdata_spectral_types.c.spectral_type_number >= spt_range['min']) & (cdata_spectral_types.c.spectral_type_number <= spt_range['max'])) |
                    (cdata_spectral_types.c.moca_oid.in_(moca_ids_array))))
                )
                .group_by(cdata_spectral_types.c.moca_oid)
            )
            
            # Add the binary filter to the query dynamically
            if binary_filter is not None:
                spt_query = spt_query.where(binary_filter)
            
            # Add the photspt filter to the query dynamically
            spt_query = spt_query.where(spectral_type_filter)

        if x_axis_type == 'absolute_magnitude' or y_axis_type == 'absolute_magnitude':
            absmag_query = (
                select(add_age_column([
                    cdata_spectral_types.c.moca_oid,
                    func.min(moca_objects.c.designation).label('designation'),
                    func.min(cdata_spectral_types.c.spectral_type_number).label('spectral_type_number'),
                    func.min(cdata_spectral_types.c.spectral_type_unc).label('spectral_type_unc'),
                    func.min(cdata_spectral_types.c.spectral_class).label('spectral_class'),
                    func.min(cdata_spectral_types.c.suffix).label('suffix'),
                    func.min(cdata_spectral_types.c.gravity_class).label('gravity_class'),
                    func.min(cdata_spectral_types.c.complete_spectral_type).label('complete_spectral_type'),
                    func.min(cdata_distances.c.distance_pc).label('distance_pc'),
                    func.min(cdata_distances.c.distance_pc_unc).label('distance_pc_unc'),
                    func.min(cdata_distances.c.dmod).label('dmod'),
                    func.min(cdata_distances.c.dmod_unc).label('dmod_unc'),
                    func.min(photometry.c.magnitude).label('magnitude'),
                    func.min(photometry.c.magnitude_unc).label('magnitude_unc'),
                    func.min(photsys.c.name).label('magnitude_name'),
                    func.min(
                            func.coalesce(func.coalesce(spt_publications.c.name, spt_publications.c.moca_pid), cdata_spectral_types.c.origin)
                        ).label('spt_ref'),
                    func.min(
                            func.coalesce(func.coalesce(func.coalesce(func.coalesce(func.coalesce(func.coalesce(distance_publications.c.name, distance_publications.c.moca_pid),parallax_publications.c.name),parallax_publications.c.moca_pid),data_parallaxes.c.origin),cdata_distances.c.calculation_method),cdata_distances.c.origin)
                        ).label('distance_ref'),
                    func.min(
                            func.concat(func.coalesce(func.coalesce(func.coalesce(photometry_publications.c.name, photometry_publications.c.moca_pid),photometry.c.origin),photometry.c.calculation_method),func.coalesce(func.concat(', ',func.concat(photometry.c.mission_name,func.coalesce(func.concat(' ',photometry.c.data_release),''))),''))
                        ).label('photometry_ref'),
                    case(
                        [
                            # Young brown dwarfs condition
                            (
                                (cdata_spectral_types.c.gravity_class.in_(['γ', 'β', 'β-γ', 'δ', 'β/γ', 'low gravity', 'low-gravity'])) |
                                (cdata_spectral_types.c.gravity_class.like('VL-G%')) |
                                (cdata_spectral_types.c.gravity_class.like('INT-G%')) |
                                (cdata_spectral_types.c.suffix.like('%red%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%red%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%VL-G%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%INT-G%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%γ%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%β%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%δ%')),
                                'young'
                            ),
                            # Subdwarfs condition
                            (
                                (cdata_spectral_types.c.suffix.like('sd%')) |
                                (cdata_spectral_types.c.suffix.like('esd%')) |
                                (cdata_spectral_types.c.suffix.like('d/sd%')) |
                                (cdata_spectral_types.c.suffix.like('%blue%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('sd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('esd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('d/sd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%blue%')),
                                'old'
                            ),
                        ],
                        else_='field'  # Default to 'field'
                    ).label('age_sample')
                ]))
                .select_from(with_age_left_joins(
                    cdata_spectral_types
                    .join(moca_objects, moca_objects.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    .join(cdata_distances, distance_join_condition)
                    .join(
                        photometry,
                        (photometry.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (photometry.c.adopted == 1) & (photometry.c.magnitude_unc.isnot(None))
                    )
                    .join(
                        photsys,
                        (photsys.c.moca_psid == photometry.c.moca_psid)
                    )
                    .outerjoin(
                        spt_publications,
                        (spt_publications.c.moca_pid == cdata_spectral_types.c.moca_pid)
                    )
                    .outerjoin(
                        distance_publications,
                        (distance_publications.c.moca_pid == cdata_distances.c.moca_pid)
                    )
                    .outerjoin(
                        data_parallaxes,
                        (data_parallaxes.c.id == cdata_distances.c.parallax_id)
                    )
                    .outerjoin(
                        parallax_publications,
                        (parallax_publications.c.moca_pid == data_parallaxes.c.moca_pid)
                    )
                    .outerjoin(
                        photometry_publications,
                        (photometry_publications.c.moca_pid == photometry.c.moca_pid)
                    )
                    .outerjoin(
                        mechanics_object_properties_combined,
                        (mechanics_object_properties_combined.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    )
                ))
                .where(
                    (cdata_spectral_types.c.adopted == 1) &
                    (((cdata_spectral_types.c.spectral_type_number >= spt_range['min']) & (cdata_spectral_types.c.spectral_type_number <= spt_range['max'])) |
                    (cdata_spectral_types.c.moca_oid.in_(moca_ids_array)))
                )
                .group_by(cdata_spectral_types.c.moca_oid)
            )
        
            # Add the binary filter to the query dynamically
            if binary_filter is not None:
                absmag_query = absmag_query.where(binary_filter)

            # Add the photspt filter to the query dynamically
            absmag_query = absmag_query.where(spectral_type_filter)

        if x_axis_type == 'spectral_index' or y_axis_type == 'spectral_index':
            spti_query = (
                select(add_age_column([
                    cdata_spectral_types.c.moca_oid,
                    func.min(moca_objects.c.designation).label('designation'),
                    func.min(cdata_spectral_types.c.spectral_type_number).label('spectral_type_number'),
                    func.min(cdata_spectral_types.c.spectral_type_unc).label('spectral_type_unc'),
                    func.min(cdata_spectral_types.c.spectral_class).label('spectral_class'),
                    func.min(cdata_spectral_types.c.suffix).label('suffix'),
                    func.min(cdata_spectral_types.c.gravity_class).label('gravity_class'),
                    func.min(cdata_spectral_types.c.complete_spectral_type).label('complete_spectral_type'),
                    func.min(cdata_distances.c.distance_pc).label('distance_pc'),
                    func.min(cdata_distances.c.distance_pc_unc).label('distance_pc_unc'),
                    func.min(cdata_distances.c.dmod).label('dmod'),
                    func.min(cdata_distances.c.dmod_unc).label('dmod_unc'),
                    func.min(cdata_spectral_indices.c.index_value).label('index_value'),
                    func.min(cdata_spectral_indices.c.index_value_unc).label('index_value_unc'),
                    func.min(moca_spectral_indices.c.description).label('spectral_index_description'),
                    func.min(
                            func.coalesce(func.coalesce(spt_publications.c.name, spt_publications.c.moca_pid), cdata_spectral_types.c.origin)
                        ).label('spt_ref'),
                    func.min(
                            func.coalesce(func.coalesce(func.coalesce(func.coalesce(func.coalesce(func.coalesce(distance_publications.c.name, distance_publications.c.moca_pid),parallax_publications.c.name),parallax_publications.c.moca_pid),data_parallaxes.c.origin),cdata_distances.c.calculation_method),cdata_distances.c.origin)
                        ).label('distance_ref'),
                    func.min(
                            func.concat(func.coalesce(func.coalesce(func.coalesce(spectral_index_publications.c.name, spectral_index_publications.c.moca_pid),cdata_spectral_indices.c.origin),cdata_spectral_indices.c.calculation_method),func.coalesce(func.concat(', ',func.concat(cdata_spectral_indices.c.mission_name,func.coalesce(func.concat(' ',cdata_spectral_indices.c.data_release),''))),''))
                        ).label('spectral_index_ref'),
                    case(
                        [
                            # Young brown dwarfs condition
                            (
                                (cdata_spectral_types.c.gravity_class.in_(['γ', 'β', 'β-γ', 'δ', 'β/γ', 'low gravity', 'low-gravity'])) |
                                (cdata_spectral_types.c.gravity_class.like('VL-G%')) |
                                (cdata_spectral_types.c.gravity_class.like('INT-G%')) |
                                (cdata_spectral_types.c.suffix.like('%red%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%red%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%VL-G%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%INT-G%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%γ%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%β%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%δ%')),
                                'young'
                            ),
                            # Subdwarfs condition
                            (
                                (cdata_spectral_types.c.suffix.like('sd%')) |
                                (cdata_spectral_types.c.suffix.like('esd%')) |
                                (cdata_spectral_types.c.suffix.like('d/sd%')) |
                                (cdata_spectral_types.c.suffix.like('%blue%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('sd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('esd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('d/sd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%blue%')),
                                'old'
                            ),
                        ],
                        else_='field'  # Default to 'field'
                    ).label('age_sample')
                ]))
                .select_from(with_age_left_joins(
                    cdata_spectral_types
                    .join(moca_objects, moca_objects.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    .join(
                        cdata_spectral_indices,
                        (cdata_spectral_indices.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (cdata_spectral_indices.c.adopted == 1)
                    )
                    .join(
                        moca_spectral_indices,
                        (cdata_spectral_indices.c.moca_siid == moca_spectral_indices.c.moca_siid)
                    )
                    .outerjoin(cdata_distances, distance_join_condition)
                    .outerjoin(
                        spt_publications,
                        (spt_publications.c.moca_pid == cdata_spectral_types.c.moca_pid)
                    )
                    .outerjoin(
                        distance_publications,
                        (distance_publications.c.moca_pid == cdata_distances.c.moca_pid)
                    )
                    .outerjoin(
                        data_parallaxes,
                        (data_parallaxes.c.id == cdata_distances.c.parallax_id)
                    )
                    .outerjoin(
                        parallax_publications,
                        (parallax_publications.c.moca_pid == data_parallaxes.c.moca_pid)
                    )
                    .outerjoin(
                        spectral_index_publications,
                        (spectral_index_publications.c.moca_pid == cdata_spectral_indices.c.moca_pid)
                    )
                    .outerjoin(
                        mechanics_object_properties_combined,
                        (mechanics_object_properties_combined.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    )
                ))
                .where(
                    (cdata_spectral_types.c.adopted == 1) &
                    (((cdata_spectral_types.c.spectral_type_number >= spt_range['min']) & (cdata_spectral_types.c.spectral_type_number <= spt_range['max'])) |
                    (cdata_spectral_types.c.moca_oid.in_(moca_ids_array)))
                )
                .group_by(cdata_spectral_types.c.moca_oid)
            )
        
            # Add the binary filter to the query dynamically
            if binary_filter is not None:
                spti_query = spti_query.where(binary_filter)

            # Add the photspt filter to the query dynamically
            spti_query = spti_query.where(spectral_type_filter)

        if x_axis_type == 'equivalent_width' or y_axis_type == 'equivalent_width':
            ew_query = (
                select(add_age_column([
                    cdata_spectral_types.c.moca_oid,
                    func.min(moca_objects.c.designation).label('designation'),
                    func.min(cdata_spectral_types.c.spectral_type_number).label('spectral_type_number'),
                    func.min(cdata_spectral_types.c.spectral_type_unc).label('spectral_type_unc'),
                    func.min(cdata_spectral_types.c.spectral_class).label('spectral_class'),
                    func.min(cdata_spectral_types.c.suffix).label('suffix'),
                    func.min(cdata_spectral_types.c.gravity_class).label('gravity_class'),
                    func.min(cdata_spectral_types.c.complete_spectral_type).label('complete_spectral_type'),
                    func.min(cdata_distances.c.distance_pc).label('distance_pc'),
                    func.min(cdata_distances.c.distance_pc_unc).label('distance_pc_unc'),
                    func.min(cdata_distances.c.dmod).label('dmod'),
                    func.min(cdata_distances.c.dmod_unc).label('dmod_unc'),
                    func.min(cdata_equivalent_widths.c.ew_angstrom).label('ew_angstrom'),
                    func.min(cdata_equivalent_widths.c.ew_angstrom_unc).label('ew_angstrom_unc'),
                    func.min(moca_equivalent_widths.c.description).label('equivalent_width_description'),
                    func.min(
                            func.coalesce(func.coalesce(spt_publications.c.name, spt_publications.c.moca_pid), cdata_spectral_types.c.origin)
                        ).label('spt_ref'),
                    func.min(
                            func.coalesce(func.coalesce(func.coalesce(func.coalesce(func.coalesce(func.coalesce(distance_publications.c.name, distance_publications.c.moca_pid),parallax_publications.c.name),parallax_publications.c.moca_pid),data_parallaxes.c.origin),cdata_distances.c.calculation_method),cdata_distances.c.origin)
                        ).label('distance_ref'),
                    func.min(
                            func.concat(func.coalesce(func.coalesce(func.coalesce(equivalent_widths_publications.c.name, equivalent_widths_publications.c.moca_pid),cdata_equivalent_widths.c.origin),cdata_equivalent_widths.c.calculation_method),func.coalesce(func.concat(', ',func.concat(cdata_equivalent_widths.c.mission_name,func.coalesce(func.concat(' ',cdata_equivalent_widths.c.data_release),''))),''))
                        ).label('equivalent_width_ref'),
                    case(
                        [
                            # Young brown dwarfs condition
                            (
                                (cdata_spectral_types.c.gravity_class.in_(['γ', 'β', 'β-γ', 'δ', 'β/γ', 'low gravity', 'low-gravity'])) |
                                (cdata_spectral_types.c.gravity_class.like('VL-G%')) |
                                (cdata_spectral_types.c.gravity_class.like('INT-G%')) |
                                (cdata_spectral_types.c.suffix.like('%red%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%red%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%VL-G%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%INT-G%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%γ%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%β%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%δ%')),
                                'young'
                            ),
                            # Subdwarfs condition
                            (
                                (cdata_spectral_types.c.suffix.like('sd%')) |
                                (cdata_spectral_types.c.suffix.like('esd%')) |
                                (cdata_spectral_types.c.suffix.like('d/sd%')) |
                                (cdata_spectral_types.c.suffix.like('%blue%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('sd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('esd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('d/sd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%blue%')),
                                'old'
                            ),
                        ],
                        else_='field'  # Default to 'field'
                    ).label('age_sample')
                ]))
                .select_from(with_age_left_joins(
                    cdata_spectral_types
                    .join(moca_objects, moca_objects.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    .join(
                        cdata_equivalent_widths,
                        (cdata_equivalent_widths.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (cdata_equivalent_widths.c.adopted == 1)
                    )
                    .join(
                        moca_equivalent_widths,
                        (cdata_equivalent_widths.c.moca_spid == moca_equivalent_widths.c.moca_spid)
                    )
                    .outerjoin(cdata_distances, distance_join_condition)
                    .outerjoin(
                        spt_publications,
                        (spt_publications.c.moca_pid == cdata_spectral_types.c.moca_pid)
                    )
                    .outerjoin(
                        distance_publications,
                        (distance_publications.c.moca_pid == cdata_distances.c.moca_pid)
                    )
                    .outerjoin(
                        data_parallaxes,
                        (data_parallaxes.c.id == cdata_distances.c.parallax_id)
                    )
                    .outerjoin(
                        parallax_publications,
                        (parallax_publications.c.moca_pid == data_parallaxes.c.moca_pid)
                    )
                    .outerjoin(
                        equivalent_widths_publications,
                        (equivalent_widths_publications.c.moca_pid == cdata_equivalent_widths.c.moca_pid)
                    )
                    .outerjoin(
                        mechanics_object_properties_combined,
                        (mechanics_object_properties_combined.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    )
                ))
                .where(
                    (cdata_spectral_types.c.adopted == 1) &
                    (((cdata_spectral_types.c.spectral_type_number >= spt_range['min']) & (cdata_spectral_types.c.spectral_type_number <= spt_range['max'])) |
                    (cdata_spectral_types.c.moca_oid.in_(moca_ids_array)))
                )
                .group_by(cdata_spectral_types.c.moca_oid)
            )
        
            # Add the binary filter to the query dynamically
            if binary_filter is not None:
                ew_query = ew_query.where(binary_filter)

            # Add the photspt filter to the query dynamically
            ew_query = ew_query.where(spectral_type_filter)

        if x_axis_type == 'color' or y_axis_type == 'color':
            color_query = (
                select(add_age_column([
                    cdata_spectral_types.c.moca_oid,
                    func.min(moca_objects.c.designation).label('designation'),
                    func.min(cdata_spectral_types.c.spectral_type_number).label('spectral_type_number'),
                    func.min(cdata_spectral_types.c.spectral_type_unc).label('spectral_type_unc'),
                    func.min(cdata_spectral_types.c.spectral_class).label('spectral_class'),
                    func.min(cdata_spectral_types.c.suffix).label('suffix'),
                    func.min(cdata_spectral_types.c.gravity_class).label('gravity_class'),
                    func.min(cdata_spectral_types.c.complete_spectral_type).label('complete_spectral_type'),
                    func.min(cdata_distances.c.distance_pc).label('distance_pc'),
                    func.min(cdata_distances.c.distance_pc_unc).label('distance_pc_unc'),
                    func.min(phot1.c.magnitude).label('magnitude_1'),
                    func.min(phot1.c.magnitude_unc).label('magnitude_unc_1'),
                    func.min(phot2.c.magnitude).label('magnitude_2'),
                    func.min(phot2.c.magnitude_unc).label('magnitude_unc_2'),
                    func.min(photsys1.c.name).label('magnitude_name_1'),
                    func.min(photsys2.c.name).label('magnitude_name_2'),
                    func.min(
                            func.coalesce(func.coalesce(spt_publications.c.name, spt_publications.c.moca_pid), cdata_spectral_types.c.origin)
                        ).label('spt_ref'),
                    func.min(
                            func.coalesce(func.coalesce(func.coalesce(func.coalesce(func.coalesce(func.coalesce(distance_publications.c.name, distance_publications.c.moca_pid),parallax_publications.c.name),parallax_publications.c.moca_pid),data_parallaxes.c.origin),cdata_distances.c.calculation_method),cdata_distances.c.origin)
                        ).label('distance_ref'),
                    func.min(
                            func.concat(func.coalesce(func.coalesce(func.coalesce(photometry_publications1.c.name, photometry_publications1.c.moca_pid),phot1.c.origin),phot1.c.calculation_method),func.coalesce(func.concat(', ',func.concat(phot1.c.mission_name,func.coalesce(func.concat(' ',phot1.c.data_release),''))),''))
                        ).label('photometry_ref_1'),
                    func.min(
                            func.concat(func.coalesce(func.coalesce(func.coalesce(photometry_publications2.c.name, photometry_publications2.c.moca_pid),phot2.c.origin),phot2.c.calculation_method),func.coalesce(func.concat(', ',func.concat(phot2.c.mission_name,func.coalesce(func.concat(' ',phot2.c.data_release),''))),''))
                        ).label('photometry_ref_2'),
                    case(
                        [
                            # Young brown dwarfs condition
                            (
                                (cdata_spectral_types.c.gravity_class.in_(['γ', 'β', 'β-γ', 'δ', 'β/γ', 'low gravity', 'low-gravity'])) |
                                (cdata_spectral_types.c.gravity_class.like('VL-G%')) |
                                (cdata_spectral_types.c.gravity_class.like('INT-G%')) |
                                (cdata_spectral_types.c.suffix.like('%red%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%red%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%VL-G%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%INT-G%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%γ%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%β%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%δ%')),
                                'young'
                            ),
                            # Subdwarfs condition
                            (
                                (cdata_spectral_types.c.suffix.like('sd%')) |
                                (cdata_spectral_types.c.suffix.like('esd%')) |
                                (cdata_spectral_types.c.suffix.like('d/sd%')) |
                                (cdata_spectral_types.c.suffix.like('%blue%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('sd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('esd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('d/sd%')) |
                                (cdata_spectral_types.c.complete_spectral_type.like('%blue%')),
                                'old'
                            ),
                        ],
                        else_='field'  # Default to 'field'
                    ).label('age_sample')
                ]))
                .select_from(with_age_left_joins(
                    cdata_spectral_types
                    .join(moca_objects, moca_objects.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    .join(
                        phot1,
                        (phot1.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (phot1.c.adopted == 1) & (phot1.c.magnitude_unc.isnot(None))
                    )
                    .join(
                        phot2,
                        (phot2.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (phot2.c.adopted == 1) & (phot2.c.magnitude_unc.isnot(None))
                    )
                    .join(
                        photsys1,
                        (photsys1.c.moca_psid == phot1.c.moca_psid)
                    )
                    .join(
                        photsys2,
                        (photsys2.c.moca_psid == phot2.c.moca_psid)
                    )
                    .outerjoin(cdata_distances, distance_join_condition)
                    .outerjoin(
                        spt_publications,
                        (spt_publications.c.moca_pid == cdata_spectral_types.c.moca_pid)
                    )
                    .outerjoin(
                        distance_publications,
                        (distance_publications.c.moca_pid == cdata_distances.c.moca_pid)
                    )
                    .outerjoin(
                        data_parallaxes,
                        (data_parallaxes.c.id == cdata_distances.c.parallax_id)
                    )
                    .outerjoin(
                        parallax_publications,
                        (parallax_publications.c.moca_pid == data_parallaxes.c.moca_pid)
                    )
                    .outerjoin(
                        photometry_publications1,
                        (photometry_publications1.c.moca_pid == phot1.c.moca_pid)
                    )
                    .outerjoin(
                        photometry_publications2,
                        (photometry_publications2.c.moca_pid == phot2.c.moca_pid)
                    )
                    .outerjoin(
                        mechanics_object_properties_combined,
                        (mechanics_object_properties_combined.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    )
                ))
                .where(
                    (cdata_spectral_types.c.adopted == 1) &
                    (((cdata_spectral_types.c.spectral_type_number >= spt_range['min']) & (cdata_spectral_types.c.spectral_type_number <= spt_range['max'])) |
                    (cdata_spectral_types.c.moca_oid.in_(moca_ids_array)))
                )
                .group_by(cdata_spectral_types.c.moca_oid)
            )
        
            # Add the binary filter to the query dynamically
            if binary_filter is not None:
                color_query = color_query.where(binary_filter)

            # Add the photspt filter to the query dynamically
            color_query = color_query.where(spectral_type_filter)

        if x_axis_type == 'spectral_type':
            
            
            x_data = pd.read_sql(spt_query, connection)
            

            # Check if some data was returned
            if x_data.empty:
                return empty_figure_noresults, None, None

            x_data['x_data'] = add_gaussian_noise(x_data['spectral_type_number'])
            x_data['ex_data'] = x_data['spectral_type_unc']
            x_axis_label = 'Spectral Type'
        
        if x_axis_type == 'spectral_index' and x_band_values and any(v for v in x_band_values if v is not None):
            x_spectral_index = x_band_values[0]
            
            x_query = spti_query.where(cdata_spectral_indices.c.moca_siid == x_spectral_index)

            x_data = pd.read_sql(x_query, connection)
            
            # Check if some data was returned
            if x_data.empty:
                return empty_figure_noresults, None, None
            
            # Add index-related info
            x_data_reformatted = format_dataframe_with_error(x_data, "index_value", "index_value_unc", unit="", output_col="index_display").loc[:, ["index_display"]]
            x_data['x_ref'] = x_data['spectral_index_description']+" : "+x_data_reformatted['index_display']+" ("+x_data['spectral_index_ref'].fillna('No reference').str.replace(r'[()]', '', regex=True)+")"

            # Calculate absolute magnitude and uncertainty using dmod
            x_data['x_data'] = x_data['index_value']
            x_data['ex_data'] = x_data['index_value_unc']
            
            x_axis_label = x_data['spectral_index_description'].iloc[0]

        if x_axis_type == 'equivalent_width' and x_band_values and any(v for v in x_band_values if v is not None):
            x_equivalent_width = x_band_values[0]
            
            x_query = ew_query.where(cdata_equivalent_widths.c.moca_spid == x_equivalent_width)

            x_data = pd.read_sql(x_query, connection)
            
            # Check if some data was returned
            if x_data.empty:
                return empty_figure_noresults, None, None
            
            # Add index-related info
            x_data_reformatted = format_dataframe_with_error(x_data, "ew_angstrom", "ew_angstrom_unc", unit="", output_col="ew_display").loc[:, ["ew_display"]]
            x_data['x_ref'] = x_data['equivalent_width_description']+" : "+x_data_reformatted['ew_display']+" ("+x_data['equivalent_width_ref'].fillna('No reference').str.replace(r'[()]', '', regex=True)+")"

            # Calculate absolute magnitude and uncertainty using dmod
            x_data['x_data'] = x_data['ew_angstrom']
            x_data['ex_data'] = x_data['ew_angstrom_unc']
            
            x_axis_label = x_data['equivalent_width_description'].iloc[0]

        if x_axis_type == 'absolute_magnitude' and x_band_values and any(v for v in x_band_values if v is not None):
            x_photometry_band = x_band_values[0]  # Extract the selected bandpass (e.g., 'mko_jmag')
            
            x_query = absmag_query.where(photometry.c.moca_psid == x_photometry_band)

            x_data = pd.read_sql(x_query, connection)
            
            # Check if some data was returned
            if x_data.empty:
                return empty_figure_noresults, None, None
            
            # Add mag-related info
            x_data_reformatted = format_dataframe_with_error(x_data, "magnitude", "magnitude_unc", unit="mag", output_col="magnitude_display").loc[:, ["magnitude_display"]]
            x_data['x_ref'] = x_data['magnitude_name']+" ("+x_photometry_band+") : "+x_data_reformatted['magnitude_display']+" ("+x_data['photometry_ref'].fillna('No reference').str.replace(r'[()]', '', regex=True)+")"

            # Calculate absolute magnitude and uncertainty using dmod
            x_data['x_data'] = x_data['magnitude'] - x_data['dmod']
            x_data['ex_data'] = np.sqrt(
                (x_data['magnitude_unc'])**2 + (x_data['dmod_unc'])**2
            )
            
            x_axis_label = 'Absolute '+x_data['magnitude_name'].iloc[0]+' ('+x_photometry_band+')-band magnitude'

        if x_axis_type == 'color' and x_band_values and sum(v is not None for v in x_band_values) == 2:
            x_photometry_band_1, x_photometry_band_2 = [v for v in x_band_values if v is not None]  # Extract non-None values
            
            x_query = color_query.where((phot1.c.moca_psid == x_photometry_band_1) & (phot2.c.moca_psid == x_photometry_band_2))

            x_data = pd.read_sql(x_query, connection)
            
            # Check if some data was returned
            if x_data.empty:
                return empty_figure_noresults, None, None
            
            # Add mag-related info
            x_data_reformatted_1 = format_dataframe_with_error(x_data, "magnitude_1", "magnitude_unc_1", unit="mag", output_col="magnitude_display").loc[:, ["magnitude_display"]]
            x_data_reformatted_2 = format_dataframe_with_error(x_data, "magnitude_2", "magnitude_unc_2", unit="mag", output_col="magnitude_display").loc[:, ["magnitude_display"]]
            x_data['x_ref_1'] = x_data['magnitude_name_1']+" ("+x_photometry_band_1+") : "+x_data_reformatted_1['magnitude_display']+" ("+x_data['photometry_ref_1'].fillna('No reference').str.replace(r'[()]', '', regex=True)+")"
            x_data['x_ref_2'] = x_data['magnitude_name_2']+" ("+x_photometry_band_2+") : "+x_data_reformatted_2['magnitude_display']+" ("+x_data['photometry_ref_2'].fillna('No reference').str.replace(r'[()]', '', regex=True)+")"

            # Calculate absolute magnitude and uncertainty using dmod
            x_data['x_data'] = x_data['magnitude_1'] - x_data['magnitude_2']
            x_data['ex_data'] = np.sqrt(
                (x_data['magnitude_unc_1'])**2 + (x_data['magnitude_unc_2'])**2
            )

            x_axis_label = x_data['magnitude_name_1'].iloc[0]+' ('+x_photometry_band_1+') - '+x_data['magnitude_name_2'].iloc[0]+' ('+x_photometry_band_2+') color'

        if y_axis_type == 'spectral_type':
            
            y_data = pd.read_sql(spt_query, connection)

            # Check if some data was returned
            if y_data.empty:
                return empty_figure_noresults, None, None
            
            y_data['y_data'] = y_data['spectral_type_number']
            y_data['ey_data'] = y_data['spectral_type_unc']
            y_axis_label = 'Spectral Type'

        if y_axis_type == 'spectral_index' and y_band_values and any(v for v in y_band_values if v is not None):
            y_spectral_index = y_band_values[0]
            
            y_query = spti_query.where(cdata_spectral_indices.c.moca_siid == y_spectral_index)

            y_data = pd.read_sql(y_query, connection)
            
            # Check if some data was returned
            if y_data.empty:
                return empty_figure_noresults, None, None
            
            # Add index-related info
            y_data_reformatted = format_dataframe_with_error(y_data, "index_value", "index_value_unc", unit="", output_col="index_display").loc[:, ["index_display"]]
            y_data['y_ref'] = y_data['spectral_index_description']+" : "+y_data_reformatted['index_display']+" ("+y_data['spectral_index_ref'].fillna('No reference').str.replace(r'[()]', '', regex=True)+")"

            # Calculate absolute magnitude and uncertainty using dmod
            y_data['y_data'] = y_data['index_value']
            y_data['ey_data'] = y_data['index_value_unc']
            
            y_axis_label = y_data['spectral_index_description'].iloc[0]

        if y_axis_type == 'equivalent_width' and y_band_values and any(v for v in y_band_values if v is not None):
            y_equivalent_width = y_band_values[0]
            
            y_query = ew_query.where(cdata_equivalent_widths.c.moca_spid == y_equivalent_width)

            y_data = pd.read_sql(y_query, connection)
            
            # Check if some data was returned
            if y_data.empty:
                return empty_figure_noresults, None, None
            
            # Add index-related info
            y_data_reformatted = format_dataframe_with_error(y_data, "ew_angstrom", "ew_angstrom_unc", unit="", output_col="ew_display").loc[:, ["ew_display"]]
            y_data['y_ref'] = y_data['equivalent_width_description']+" : "+y_data_reformatted['ew_display']+" ("+y_data['equivalent_width_ref'].fillna('No reference').str.replace(r'[()]', '', regex=True)+")"

            # Calculate absolute magnitude and uncertainty using dmod
            y_data['y_data'] = y_data['ew_angstrom']
            y_data['ey_data'] = y_data['ew_angstrom_unc']
            
            y_axis_label = y_data['equivalent_width_description'].iloc[0]
        
        if y_axis_type == 'absolute_magnitude' and y_band_values and any(v for v in y_band_values if v is not None):
            y_photometry_band = y_band_values[0]  # Extract the selected bandpass (e.g., 'mko_jmag')
            
            y_query = absmag_query.where(photometry.c.moca_psid == y_photometry_band)

            y_data = pd.read_sql(y_query, connection)            
            
            # Check if some data was returned
            if y_data.empty:
                return empty_figure_noresults, None, None
            
            # Add mag-related info
            y_data_reformatted = format_dataframe_with_error(y_data, "magnitude", "magnitude_unc", unit="mag", output_col="magnitude_display").loc[:, ["magnitude_display"]]
            y_data['y_ref'] = y_data['magnitude_name']+" ("+y_photometry_band+") : "+y_data_reformatted['magnitude_display']+" ("+y_data['photometry_ref'].fillna('No reference').str.replace(r'[()]', '', regex=True)+")"

            # Calculate absolute magnitude and uncertainty using dmod
            y_data['y_data'] = y_data['magnitude'] - y_data['dmod']
            y_data['ey_data'] = np.sqrt(
                (y_data['magnitude_unc'])**2 + (y_data['dmod_unc'])**2
            )
            
            y_axis_label = 'Absolute '+y_data['magnitude_name'].iloc[0]+' ('+y_photometry_band+')-band magnitude'

        if y_axis_type == 'color' and y_band_values and sum(v is not None for v in y_band_values) == 2:
            y_photometry_band_1, y_photometry_band_2 = [v for v in y_band_values if v is not None]  # Extract non-None values

            y_query = color_query.where((phot1.c.moca_psid == y_photometry_band_1) & (phot2.c.moca_psid == y_photometry_band_2))

            y_data = pd.read_sql(y_query, connection)
            
            # Check if some data was returned
            if y_data.empty:
                return empty_figure_noresults, None, None
            
            # Add mag-related info
            y_data_reformatted_1 = format_dataframe_with_error(y_data, "magnitude_1", "magnitude_unc_1", unit="mag", output_col="magnitude_display").loc[:, ["magnitude_display"]]
            y_data_reformatted_2 = format_dataframe_with_error(y_data, "magnitude_2", "magnitude_unc_2", unit="mag", output_col="magnitude_display").loc[:, ["magnitude_display"]]
            y_data['y_ref_1'] = y_data['magnitude_name_1']+" ("+y_photometry_band_1+") : "+y_data_reformatted_1['magnitude_display']+" ("+y_data['photometry_ref_1'].fillna('No reference').str.replace(r'[()]', '', regex=True)+")"
            y_data['y_ref_2'] = y_data['magnitude_name_2']+" ("+y_photometry_band_2+") : "+y_data_reformatted_2['magnitude_display']+" ("+y_data['photometry_ref_2'].fillna('No reference').str.replace(r'[()]', '', regex=True)+")"

            # Calculate absolute magnitude and uncertainty using dmod
            y_data['y_data'] = y_data['magnitude_1'] - y_data['magnitude_2']
            y_data['ey_data'] = np.sqrt(
                (y_data['magnitude_unc_1'])**2 + (y_data['magnitude_unc_2'])**2
            )

            y_axis_label = y_data['magnitude_name_1'].iloc[0]+' ('+y_photometry_band_1+') - '+y_data['magnitude_name_2'].iloc[0]+' ('+y_photometry_band_2+') color'

    # Check if both axes are selected
    if x_data.empty or y_data.empty:
        return empty_figure_noresults, None, None
    
    # Identify overlapping columns except for the merge key
    overlapping_columns = set(x_data.columns).intersection(set(y_data.columns)) - {'moca_oid'}

    # Drop overlapping columns from y_data before merging
    y_data = y_data.drop(columns=overlapping_columns)

    # Merge the x and y data on moca_oid
    merged_data = pd.merge(x_data, y_data, on='moca_oid', how='inner')

    # Remove rows with missing or invalid data in x_data or y_data
    merged_data = merged_data.dropna(subset=['x_data', 'y_data'])

    # Remove rows with non-finite (infinite or NaN) values in x_data or y_data
    merged_data = merged_data[(merged_data['x_data'].apply(np.isfinite)) & (merged_data['y_data'].apply(np.isfinite))]

    if merged_data.empty:
        return empty_figure_noresults, None, None

    # Handle missing distance and uncertainty
    merged_data['distance'] = merged_data['distance_pc'].fillna('N/A')
    merged_data['distance_unc'] = merged_data['distance_pc_unc'].fillna('N/A')

    # Format references
    if 'spt_ref' in merged_data.columns:
        merged_data['spt_ref'] = merged_data['spt_ref'].fillna('N/A').str.replace(r'[()]', '', regex=True)
    if 'distance_ref' in merged_data.columns:
        merged_data['distance_ref'] = merged_data['distance_ref'].fillna('N/A').str.replace(r'[()]', '', regex=True)
    
    # Format numbers with significant digits
    merged_data = format_dataframe_with_error(merged_data, "distance", "distance_unc", unit="pc", output_col="distance_display")
    merged_data = format_dataframe_with_error(merged_data, "x_data", "ex_data", unit="", output_col="x_data_display")
    merged_data = format_dataframe_with_error(merged_data, "y_data", "ey_data", unit="", output_col="y_data_display")

    # Apply hovertext construction row-wise
    merged_data['hovertext'] = merged_data.apply(construct_hovertext, axis=1)

    # Separate merged_data by highlighted or regular data sets
    highlighted_data = merged_data[merged_data['moca_oid'].isin(moca_ids_array)].copy()
    regular_data = merged_data[~merged_data['moca_oid'].isin(moca_ids_array)].copy()

    # Define color mapping for spectral classes
    spectral_class_colors = {
        'O': 'purple',
        'B': 'darkblue',
        'A': 'blue',
        'F': 'lightblue',
        'G': 'greenyellow',
        'K': 'darkgreen',
        'M': 'red',
        'L': 'orange',
        'T': 'blue',
        'Y': 'purple',
    }

    # Define symbols for age_sample categories
    age_sample_symbols = {
        'field': 'circle',  # Default symbol
        'young': 'triangle-up',  # Low-gravity or red
        'old': 'square',  # Subdwarf or blue
    }

    # Define legend names for age_sample categories
    age_sample_legend_names = {
        'field': 'No spectral flags',
        'young': 'Low-gravity or red',
        'old': 'Subdwarf or blue',
    }

    # Map symbols to age_sample in the merged_data DataFrame
    regular_data['symbol'] = regular_data['age_sample'].map(age_sample_symbols).fillna('circle')  # Default to circle for unknown age_sample
    
    # Determine missing MOCA IDs
    missing_ids_message = None
    missing_ids = set(moca_ids_array) - set(highlighted_data['moca_oid'].unique())
    if missing_ids:
        missing_ids_message = f"MOCA IDs not found: {', '.join(map(str, missing_ids))}"

    color_by_age = want_age_color and ('age' in merged_data.columns)

    # Add a default color for unknown or unrecognized spectral classes
    if not color_by_age:
    
        default_color = 'aqua'

        # Map colors to spectral classes in the merged_data DataFrame
        regular_data['color'] = regular_data['spectral_class'].map(spectral_class_colors).fillna(default_color)

        fig = go.Figure()

        # Scatter plot logic
        fig.add_trace(go.Scatter(
            x=regular_data['x_data'],  # Replace with appropriate x column
            y=regular_data['y_data'],  # Replace with appropriate y column
            mode='markers',
            text=regular_data['hovertext'],  # Replace with desired hover text
            customdata=regular_data['moca_oid'],  # Include moca_oid for identification
            marker=dict(
                size=10,
                color=regular_data['color'],  # Assign colors based on spectral_class
                symbol=regular_data['symbol'],  # Assign symbols based on age_sample
                opacity=0.4
            ),
            showlegend=False      # Exclude from legend
        ))

        # Add invisible traces to create the spectral class legend
        for spectral_class, color in spectral_class_colors.items():
            if spectral_class in regular_data['spectral_class'].unique():
                fig.add_trace(go.Scatter(
                    x=[None],  # No data for the trace
                    y=[None],  # No data for the trace
                    mode='markers',
                    marker=dict(size=10, color=color),
                    name=f"{spectral_class} class"  # Legend entry
                ))

        # Add an invisible trace for unknown classes if needed
        if (regular_data['spectral_class'].isnull().any() or not regular_data['spectral_class'].isin(spectral_class_colors.keys()).all()):
            fig.add_trace(go.Scatter(
                x=[None],  # No data for the trace
                y=[None],  # No data for the trace
                mode='markers',
                marker=dict(size=10, color=default_color),
                name="Other classes"
            ))

    if color_by_age:
        has_age = (regular_data['age'].notna()) # & (regular_data['age'] < 2e3)

        merged_with_age = regular_data[has_age].copy()
        merged_no_age   = regular_data[~has_age].copy()

        traces = []

        if color_by_age and not merged_no_age.empty:
            traces.append(
                go.Scattergl(
                    x=merged_no_age['x_data'],
                    y=merged_no_age['y_data'],
                    mode='markers',
                    marker=dict(
                        size=merged_no_age.get('marker_size', 5),
                        symbol=merged_no_age.get('symbol', 'circle'),
                        color='rgba(120,120,120,0.3)',
                        line=dict(width=merged_no_age.get('marker_line_width', 0)),
                    ),
                    hovertemplate=merged_no_age.get('hovertemplate', None),
                    name='No age',
                    text=merged_no_age['hovertext'],
                    customdata=merged_no_age['moca_oid'],  # Include moca_oid for identification
                    showlegend=False,
                )
            )
        
        if color_by_age and not merged_with_age.empty:

            logages = np.log10(merged_with_age['age'])
            # --- Build logarithmic colorbar ticks (in Age, not log(Age)) ---
            try:
                age_min = float(np.nanmin(merged_with_age['age']))
                age_max = float(np.nanmax(merged_with_age['age']))
                if np.isfinite(age_min) and np.isfinite(age_max) and age_min > 0 and age_max > 0:
                    kmin = int(np.floor(np.log10(age_min)))
                    kmax = int(np.ceil(np.log10(age_max)))
                    _tick_ages = [10**k for k in range(kmin, kmax + 1)]
                    _tickvals = [np.log10(a) for a in _tick_ages]
                    _ticktext = [str(int(a)) if a >= 1 else f"{a:g}" for a in _tick_ages]
                else:
                    _tickvals = None
                    _ticktext = None
            except Exception:
                _tickvals = None
                _ticktext = None

            # Common colorbar styling: closer to figure and thick black outline
            _colorbar_kwargs = dict(
                title='<b>Age (Myr)</b>',
                ticks='outside',
                ticklen=5,
                tickwidth=2,
                x=1.02,         # pull closer to the plotting area
                xpad=0,        # remove extra padding
                outlinecolor='black',
                outlinewidth=3,
            )
            if _tickvals is not None and _ticktext is not None:
                _colorbar_kwargs.update(tickmode='array', tickvals=_tickvals, ticktext=_ticktext)

            traces.append(
                go.Scattergl(
                    x=merged_with_age['x_data'],
                    y=merged_with_age['y_data'],
                    mode='markers',
                    marker=dict(
                        size=merged_with_age.get('marker_size', 6),
                        symbol=merged_with_age.get('symbol', 'circle'),
                        color=logages,
                        #color=np.log10(merged_with_age['age']),
                        colorscale='Rainbow',   # purple (young) → red (old)
                        reversescale=False,
                        colorbar=_colorbar_kwargs,
                        showscale=True,
                        line=dict(width=merged_with_age.get('marker_line_width', 0)),
                        opacity=merged_with_age.get('marker_opacity', 0.6),
                    ),
                    hovertemplate=merged_with_age.get('hovertemplate', None),
                    name='Objects (age-coded)',
                    text=merged_with_age['hovertext'],
                    customdata=merged_with_age['moca_oid'],  # Include moca_oid for identification
                    showlegend=False,  # colorbar replaces color legend
                )
            )

        fig = go.Figure(data=traces)

    # Add invisible traces for the age_sample legend
    for age_sample, symbol in age_sample_symbols.items():
        legend_name = age_sample_legend_names.get(age_sample, age_sample.capitalize())  # Fallback to capitalize if missing
        fig.add_trace(go.Scatter(
            x=[None],  # No data for the trace
            y=[None],  # No data for the trace
            mode='markers',
            marker=dict(size=10, color='gray', symbol=symbol),  # Gray color for age_sample legend
            name=legend_name  # Translated legend entry
        ))
    
    # Add the highlighted objects
    if not highlighted_data.empty:
        fig.add_trace(go.Scatter(
            x=highlighted_data['x_data'],  # Highlighted x column
            y=highlighted_data['y_data'],  # Highlighted y column
            mode='markers',
            text=highlighted_data['hovertext'],  # Hover text for highlighted objects
            customdata=highlighted_data['moca_oid'],  # Include moca_oid for identification
            marker=dict(
                symbol='star',
                size=22,
                line=dict(
                    width=3,
                    color='black'
                ),
                color='rgba(0,0,0,0)',  # Make the fill completely transparent
            ),
            name="Highlighted objects"  # Legend entry
        ))

    # Determine y-axis range for absolute magnitude
    if y_axis_type == 'absolute_magnitude' and not y_data.empty:
        y_min = y_data['y_data'].min()
        y_max = y_data['y_data'].max()
        y_range = [y_max, y_min]  # Flip the range for absolute magnitudes
    else:
        y_range = None  # Default range

    fig.update_layout(
        xaxis_title=x_axis_label,
        yaxis_title=y_axis_label,
        xaxis=dict(
            gridcolor='rgba(211, 211, 211, 0.6)',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        yaxis=dict(
            gridcolor='rgba(211, 211, 211, 0.6)',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
            range=y_range,
        ),
        template="plotly_white",
        #legend_title="Spectral Class",
        margin=dict(l=40, r=40, t=70, b=40),
        legend=dict(
             title=dict(
                text="<b> Legend</b>",  # Make the title bold
                font=dict(size=14)  # Optional: adjust font size
            ),
            bgcolor='rgba(255, 255, 255, 0.5)',  # Optional: semi-transparent background
            bordercolor='black',
            borderwidth=2
        ),
        title=None,
        annotations=[
            dict(
                xref="paper", yref="paper",
                x=0.5, y=1.075,  # Position above the graph
                text=f"<b> {y_axis_type_label} versus {x_axis_type_label} for spectral types {generate_spectral_type_label(spt_range['min'])}-{generate_spectral_type_label(spt_range['max'])} </b><br>Click any data point to open its MOCA report",
                showarrow=False,
                font=dict(size=14, color="black"),
                align="center"
            )
        ],
        height=800,  # Increase the height (default is usually ~450-500)
    )
    
    if want_age_color:
        fig.update_layout(legend=dict(x=1.15))

    # Update x-axis tick labels if spectral type is selected
    if x_axis_type == 'spectral_type':
        
        # Filter merged_data to include only rows where y_data is finite
        filtered_data = merged_data[np.isfinite(merged_data['y_data'])]

        # Calculate x_min and x_max based on the filtered data
        x_min = filtered_data['x_data'].min()
        x_max = filtered_data['x_data'].max()

        # Add a small padding to the range for visual spacing
        x_padding = 0.05 * (x_max - x_min)
        x_range = [x_min - x_padding, x_max + x_padding]

        x_tickvals = compute_ticks(x_range)

        if x_tickvals.any():
            fig.layout.xaxis.tickvals = x_tickvals
            fig.layout.xaxis.ticktext = [generate_spectral_type_label(val) for val in x_tickvals]

    # Update y-axis tick labels if spectral type is selected
    if y_axis_type == 'spectral_type':
        
        # Determine y-axis range mimicking Plotly's auto behavior
        y_min = merged_data['y_data'].min()
        y_max = merged_data['y_data'].max()

        # Add a small padding to the range for visual spacing
        y_padding = 0.05 * (y_max - y_min)
        y_range = [y_min - y_padding, y_max + y_padding]

        y_tickvals = compute_ticks(y_range)

        if y_tickvals.any():
            fig.layout.yaxis.tickvals = y_tickvals
            fig.layout.yaxis.ticktext = [generate_spectral_type_label(val) for val in y_tickvals]

    # --- Optional measurement error bars ---
    display_errors_flag = isinstance(display_errors_value, (list, tuple)) and ('display_errors' in display_errors_value)

    if merged_data is not None and len(merged_data) and len(fig.data) >= 1 and isinstance(fig.data[0], (go.Scatter, go.Scattergl)):
        md = merged_data.copy()
        md['err_x'] = md['ex_data']
        md['err_y'] = md['ey_data']

        main = fig.data[0]
        oids = list(main.customdata) if getattr(main, "customdata", None) is not None else None
        if oids is not None and 'moca_oid' in md.columns:
            ex_map = md.set_index('moca_oid')['err_x'].to_dict()
            ey_map = md.set_index('moca_oid')['err_y'].to_dict()
            errx_all = [ex_map.get(int(oid), None) for oid in oids]
            erry_all = [ey_map.get(int(oid), None) for oid in oids]
        else:
            # fallback: assume same order
            errx_all = md['err_x'].tolist() if 'err_x' in md.columns else None
            erry_all = md['err_y'].tolist() if 'err_y' in md.columns else None

        error_thick = 0.7
        err_color_main = 'rgba(128,128,128,0.2)'  # transparent gray
        if display_errors_flag:
            if errx_all is not None:
                main.update(error_x=dict(
                    array=errx_all, type='data', visible=True,
                    thickness=error_thick,  # thinner lines
                    width=0,      # no end caps
                    color=err_color_main  # match marker color + opacity
                ))
            if erry_all is not None:
                main.update(error_y=dict(
                    array=erry_all, type='data', visible=True,
                    thickness=error_thick,
                    width=0,
                    color=err_color_main
                ))
        else:
            main.update(error_x=dict(visible=False, thickness=error_thick, width=0), error_y=dict(visible=False, thickness=error_thick, width=0))

    # --- Measurements error filtering & styling (per-axis) ---

    # Allow thresholds from URL if UI empty
    url_params_local = parse_url_params(url)
    url_xerr = url_params_local.get('xerr_max', [None])[0]
    url_yerr = url_params_local.get('yerr_max', [None])[0]

    def _as_float(v):
        try:
            return float(v)
        except Exception:
            return None

    xerr_max = (_as_float(x_err_threshold) if x_err_threshold is not None else _as_float(url_xerr))
    yerr_max = (_as_float(y_err_threshold) if y_err_threshold is not None else _as_float(url_yerr))

    # Skip if no data
    if merged_data is not None and len(merged_data):
        md = merged_data.copy()

        # Per-point photometric sigmas for each axis
        md['sigma_x'] = md['ex_data'] #md.apply(lambda r: _compute_photometric_sigma(x_axis_type, r), axis=1)
        md['sigma_y'] = md['ey_data'] #md.apply(lambda r: _compute_photometric_sigma(y_axis_type, r), axis=1)

        # Masks
        md['too_noisy_x'] = md['sigma_x'] > xerr_max if xerr_max is not None else False
        md['too_noisy_y'] = md['sigma_y'] > yerr_max if yerr_max is not None else False
        md['transparent_mask'] = md['too_noisy_x'] | md['too_noisy_y']

        # Fading: keep original color & symbol; split into two traces with different opacities
        try:
            # The main regular-data scatter was added first (index 0)
            if len(fig.data) >= 1 and isinstance(fig.data[0], (go.Scatter, go.Scattergl)):
                main = fig.data[0]

                # We rely on customdata holding moca_oid to align with md
                oids = list(main.customdata) if getattr(main, "customdata", None) is not None else None
                if oids is not None:
                    # Map each OID to its transparent flag
                    mask_by_oid = md.set_index('moca_oid')['transparent_mask']
                    noisy_flags = [bool(mask_by_oid.get(int(oid), False)) for oid in oids]

                    good_idx = [i for i, f in enumerate(noisy_flags) if not f]
                    noisy_idx = [i for i, f in enumerate(noisy_flags) if f]

                    def _subset(arr, idxs):
                        if arr is None:
                            return None
                        a = list(arr)
                        return [a[i] for i in idxs]

                    # Snapshot existing arrays so we can slice them consistently
                    x_all = list(main.x)
                    y_all = list(main.y)
                    text_all = list(main.text) if getattr(main, "text", None) is not None else None
                    cdata_all = list(main.customdata) if getattr(main, "customdata", None) is not None else None
                    color_all = list(main.marker.color) if getattr(main.marker, "color", None) is not None else None
                    symbol_all = list(main.marker.symbol) if getattr(main.marker, "symbol", None) is not None else None
                    size_all = list(main.marker.size) if isinstance(main.marker.size, (list, tuple)) else main.marker.size

                    # Update main trace to only GOOD points (preserve existing color/symbol arrays and opacity)
                    main.x = _subset(x_all, good_idx)
                    main.y = _subset(y_all, good_idx)
                    main.text = _subset(text_all, good_idx) if text_all is not None else None
                    main.customdata = _subset(cdata_all, good_idx) if cdata_all is not None else None
                    if color_all is not None:
                        main.marker.update(color=_subset(color_all, good_idx))
                    if symbol_all is not None:
                        main.marker.update(symbol=_subset(symbol_all, good_idx))

                    # Slice error arrays on the main (GOOD) trace as well
                    try:
                        if getattr(main, "error_x", None) and getattr(main.error_x, "array", None) is not None:
                            main.update(error_x=dict(
                                array=_subset(list(main.error_x.array), good_idx),
                                type='data',
                                visible=display_errors_flag,
                                thickness=error_thick,
                                width=0,
                                color=err_color_main
                            ))
                        if getattr(main, "error_y", None) and getattr(main.error_y, "array", None) is not None:
                            main.update(error_y=dict(
                                array=_subset(list(main.error_y.array), good_idx),
                                type='data',
                                visible=display_errors_flag,
                                thickness=error_thick,
                                width=0,
                                color=err_color_main
                            ))
                    except Exception:
                        pass

                    # Add a second trace for NOISY points with low opacity (colors/symbols preserved)
                    if noisy_idx:
                        hidden_opacity = 0.08
                        errx_all = list(main.error_x.array) if getattr(main, "error_x", None) and getattr(main.error_x, "array", None) is not None else None
                        erry_all = list(main.error_y.array) if getattr(main, "error_y", None) and getattr(main.error_y, "array", None) is not None else None
                        noisy_err_color = _modulate_rgba_alpha(_derive_error_color_from_trace(main), alpha_factor=hidden_opacity)
                        fig.add_trace(go.Scatter(
                            x=_subset(x_all, noisy_idx),
                            y=_subset(y_all, noisy_idx),
                            mode='markers',
                            text=_subset(text_all, noisy_idx) if text_all is not None else None,
                            customdata=_subset(cdata_all, noisy_idx) if cdata_all is not None else None,
                            marker=dict(
                                size=(size_all * 0.5 if not isinstance(size_all, list)
                                    else [s * 0.5 for s in _subset(size_all, noisy_idx)]),
                                color=_subset(color_all, noisy_idx) if color_all is not None else None,
                                symbol=_subset(symbol_all, noisy_idx) if symbol_all is not None else None,
                            ),
                            # error_x=(dict(array=_subset(errx_all, noisy_idx), type='data', visible=True,
                            #             thickness=1, width=0, color=noisy_err_color)
                            #         if errx_all is not None and display_errors_flag else None),
                            # error_y=(dict(array=_subset(erry_all, noisy_idx), type='data', visible=True,
                            #             thickness=1, width=0, color=noisy_err_color)
                            #         if erry_all is not None and display_errors_flag else None),
                            opacity=hidden_opacity,
                            showlegend=False
                        ))
        except Exception:
            pass

        # Axis ranges: exclude noisy points per-axis, keep them drawn
        # Identify columns used for plotting
        xcol = None
        for cand in ['x', 'x_value', 'x_data', 'x_data_value', 'x_plot']:
            if cand in md.columns:
                xcol = cand
                break
        ycol = None
        for cand in ['y', 'y_value', 'y_data', 'y_data_value', 'y_plot']:
            if cand in md.columns:
                ycol = cand
                break

        try:
            if xcol:
                good_for_x = (~md['too_noisy_x']) if xerr_max is not None else md[xcol].notna()
                if good_for_x.any():
                    xmin = float(np.nanmin(md.loc[good_for_x, xcol]))
                    xmax = float(np.nanmax(md.loc[good_for_x, xcol]))
                    if np.isfinite(xmin) and np.isfinite(xmax) and xmin != xmax:
                        custom_xrange = [xmin, xmax]
                        # Add 5% padding
                        x_padding = 0.05 * np.abs(xmax - xmin)
                        custom_xrange = [custom_xrange[0] - x_padding, custom_xrange[1] + x_padding]
                        fig.update_xaxes(range=custom_xrange, autorange=False)
            if ycol:
                good_for_y = (~md['too_noisy_y']) if yerr_max is not None else md[ycol].notna()
                if good_for_y.any():
                    ymin = float(np.nanmin(md.loc[good_for_y, ycol]))
                    ymax = float(np.nanmax(md.loc[good_for_y, ycol]))
                    if np.isfinite(ymin) and np.isfinite(ymax) and ymin != ymax:
                        if y_axis_type == 'absolute_magnitude':
                            custom_yrange = [ymax, ymin]
                        else:
                            custom_yrange = [ymin, ymax]
                        # Add 5% padding
                        y_padding = 0.05 * np.abs(ymax - ymin)
                        custom_yrange = [custom_yrange[0] - y_padding, custom_yrange[1] + y_padding]
                        fig.update_yaxes(range=custom_yrange, autorange=False)
        except Exception:
            pass

        # Store augmented data (so selection/export include flags if useful)
        merged_data = md

    if display_errors_value and 'display_errors' in display_errors_value:
        # Hide the grid when errors are shown
        fig.update_layout(
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=False)
        )
    else:
        # Restore the grid when errors are hidden
        fig.update_layout(
            xaxis=dict(showgrid=True),
            yaxis=dict(showgrid=True)
        )
    
    # --- Overlay Best18 median colors as large circles, color-coded by spectral type ---
    try:
        # Determine the active figure variable name (fig vs figure)
        _target_fig = locals().get('fig') or locals().get('figure')
        if _target_fig is not None:
            _add_best18_overlay(_target_fig, engine, x_axis_type, y_axis_type, x_band_values, y_band_values, spt_range)
    except Exception:
        pass

    # Ensure "Home" resets to MOCA-style limits (initial ranges)
    if custom_xrange is not None:
        fig.update_xaxes(autorange=False, range=custom_xrange)
    if custom_yrange is not None:
        fig.update_yaxes(autorange=False, range=custom_yrange)

    # Optional: keep zoom/pan state stable across re-renders
    fig.update_layout(uirevision="moca_home_v1")

    return fig, dcc.Markdown(missing_ids_message) if missing_ids_message else None, merged_data.to_dict('records')  # Save `merged_data` as a JSON serializable dictionary

@dash.callback(
    Output('bdphot-selected-data-table', 'children'),
    [
        Input('bdphot-scatter-plot', 'selectedData'),
        Input('bdphot-merged-data-store', 'data')  # Access `merged_data` from the Store
    ]
)
def update_table(selectedData, merged_data_records):
    
    no_data_element = html.Div("No points selected.")

    if merged_data_records == None:
        return no_data_element

    # Convert the stored `merged_data` back to a DataFrame
    merged_data = pd.DataFrame(merged_data_records)

    if merged_data.empty:
        return no_data_element
    
    # Extract selected points
    selected_data = []
    if selectedData and 'points' in selectedData:
        selected_data = [point['customdata'] for point in selectedData['points'] if 'customdata' in point]

    if len(selected_data) == 0:
        return no_data_element
    
    
    selected_rows = merged_data[merged_data['moca_oid'].isin(selected_data)]

    if selected_rows.empty:
        return no_data_element
    
    # Drop the hovertext column from the table
    if 'hovertext' in selected_rows.columns:
        selected_rows = selected_rows.drop(columns=['hovertext'])
    
    # Generate table    
    return dash.dash_table.DataTable(
        columns=[{"name": col, "id": col} for col in selected_rows.columns],
        data=selected_rows.to_dict('records'),
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '5px'},
        style_header={'fontWeight': 'bold'}
    )
    

@dash.callback(
    Output("bdphot-export-dataframe-csv", "data"),
    Input("bdphot-export-button", "n_clicks"),
    [
        State("bdphot-merged-data-store", "data"),  # Use the stored `merged_data`
        State("bdphot-scatter-plot", "selectedData")  # Use the selection data from the plot
    ],
    prevent_initial_call=True
)
def export_table_to_csv(n_clicks, merged_data_store, selectedData):
    """
    Exports the table data to a CSV file when the export button is clicked.
    If no points are selected, export the full dataset.
    """
    if not merged_data_store:
        return dash.no_update

    # Convert the stored JSON data back to a DataFrame
    merged_data = pd.DataFrame(merged_data_store)

    # Check if any points are selected
    if selectedData and 'points' in selectedData:
        selected_data = [point['customdata'] for point in selectedData['points'] if 'customdata' in point]
        selected_rows = merged_data[merged_data['moca_oid'].isin(selected_data)]
    else:
        # No selection, export the full dataset
        selected_rows = merged_data

    # If no data is available, do nothing
    if selected_rows.empty:
        return dash.no_update

    # Export to CSV
    return dcc.send_data_frame(selected_rows.to_csv, "moca_colors_dataset.csv", index=False)

@dash.callback(
    [
        Output('bdphot-moca-ids-input', 'value'),
        Output('bdphot-moca-ids-input', 'n_submit')
    ],
    Input('url', 'href')
)
def update_moca_ids_input(url):
    """
    Parse `moca_oid` from the URL and set it as the value of the input field.
    Trigger a submit if `moca_oid` exists in the URL.
    """
    url_params = parse_url_params(url)
    moca_oid = url_params.get('moca_oid', [None])[0]
    
    if moca_oid:
        # Split and validate IDs
        moca_ids = [oid.strip() for oid in moca_oid.split(',') if oid.strip().isdigit()]
        if moca_ids:
            return ','.join(moca_ids), 1  # Set value and trigger a submit once
    
    return None, dash.no_update  # No default value or submission

@dash.callback(
    [
        #Output('bdphot-checkbox-best-photometry', 'value'),
        Output('bdphot-checkbox-display-errors', 'value'),
        Output('bdphot-checkbox-photometric-distances', 'value'),
        Output('bdphot-checkbox-binaries', 'value'),
        Output('bdphot-checkbox-spectral-type-estimates', 'value'),
        Output('bdphot-checkbox-color-by-age', 'value'),
    ],
    Input('url', 'href')
)
def update_checkboxes_from_url(url):
    """
    Update checkbox states based on URL parameters.
    """
    url_params = parse_url_params(url)

    # Parse each checkbox's corresponding URL parameter
    #bestphot = url_params.get('bestphot', ['true'])[0].lower() == 'true'
    photdist = url_params.get('photdist', ['false'])[0].lower() == 'true'
    binaries = url_params.get('binaries', ['false'])[0].lower() == 'true'
    photspt = url_params.get('photspt', ['false'])[0].lower() == 'true'
    errors = url_params.get('errors', ['false'])[0].lower() == 'true'
    agecolor = url_params.get('agecolor', ['false'])[0].lower() == 'true'

    # Return values for each checkbox
    return (
        #['best_photometry'] if bestphot else [],
        ['display_errors'] if errors else [],
        ['photometric_distances'] if photdist else [],
        ['binaries'] if binaries else [],
        ['spectral_type_estimates'] if photspt else [],
        ['color_by_age'] if agecolor else [],
    )

@dash.callback(
    [
        Output('bdphot-spt-range-error', 'children'),
        Output('bdphot-spt-range-input', 'value'),
        Output('bdphot-spt-range-store', 'data'),
    ],
    Input('bdphot-spt-range-input', 'value'),
    State('url', 'href')
)
def validate_spt_range(spt_range, url):

    default_range = default_spt_range
    default_store = {'min': default_spt_range_val[0], 'max': default_spt_range_val[1]}
    error_message = None

    # Parse the URL state only if spt_range is not provided
    if not spt_range:
        url_params = parse_url_params(url)
        spt_range_param = url_params.get('spt_range', [None])[0]

        if spt_range_param:
            try:
                spt_range = unquote(spt_range_param)
                spt_range = spt_range.replace('_','-')
                if '-' in spt_range:
                    start, end = spt_range.split('-')
                    start_value = parse_spt_label(start.strip())
                    end_value = parse_spt_label(end.strip())

                    if start_value is not None and end_value is not None:
                        return error_message, f"{start}-{end}", {'min': start_value, 'max': end_value}
            except Exception:
                pass  # Fall through to default handling if URL value is invalid

        # Default to valid range if invalid
        return error_message, default_range, default_store

    # Validate the manually entered range
    if not spt_range or '-' not in spt_range:
        return "Invalid format. Use '"+default_spt_range+"'.", default_range, default_store

    try:
        spt_min_label, spt_max_label = spt_range.split('-')
        spt_min = parse_spt_label(spt_min_label)
        spt_max = parse_spt_label(spt_max_label)

        if spt_min is None or spt_max is None or spt_min > spt_max:
            raise ValueError("Invalid range.")
    except Exception:
        return "Invalid range or spectral types.", default_range, default_store

    # Valid input
    return error_message, spt_range, {'min': spt_min, 'max': spt_max}

@dash.callback(
    Output('bdphot-clicked-moca-oid', 'data'),
    Input('bdphot-scatter-plot', 'clickData')
)
def store_clicked_moca_oid(clickData):
    if clickData and 'points' in clickData:
        return clickData['points'][0]['customdata']  # Extract `moca_oid`
    return dash.no_update

dash.clientside_callback(
    """
    function(moca_oid) {
        if (moca_oid) {
            window.open('https://mocadb.ca/search/results?search-query=oid%28' + moca_oid + '%29&search-type=star', '_blank');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('bdphot-dummy-output', 'children'),  # Use a dummy output to avoid conflicts
    Input('bdphot-clicked-moca-oid', 'data')
)