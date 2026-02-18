
import dash
from dash import dcc, html, Input, Output, State, callback_context
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus as urlquote, urlparse, parse_qs
import os
from datetime import datetime

# =============================================================================
# Database connection parameters (match spectral_typing.py)
# =============================================================================
default_host = '104.248.106.21'
default_username = 'public'
default_password = 'z@nUg_2h7_%?31y88'
default_dbname = 'mocadb'

env_host = os.environ.get('MOCA_HOST', default_host)
env_username = os.environ.get('MOCA_USERNAME', default_username)
env_password = os.environ.get('MOCA_PASSWORD', default_password)
env_dbname = os.environ.get('MOCA_DBNAME', default_dbname)

def get_connection_string_agepdfs(url_search=None):
    """Build a SQLAlchemy connection string using the same schema as spectral_typing.py.
    URL params (optional): user, pwd, dbase, host. Falls back to env vars above.
    """
    username = env_username
    password = env_password
    dbname = env_dbname
    host = env_host

    if url_search:
        parsed_url = urlparse(url_search)
        qs = parse_qs(parsed_url.query)
        username = qs.get("user", [username])[0]
        password = qs.get("pwd", [password])[0]
        dbname   = qs.get("dbase", [dbname])[0]
        host     = qs.get("host", [host])[0]

    return f"mysql+pymysql://{username}:{urlquote(password)}@{host}/{dbname}"

# -----------------------------------------------------------------------------
# Page registration
# -----------------------------------------------------------------------------
dash.register_page(
    __name__,
    path="/age-pdfs",
    name="MOCA Association Age Explorer",
    order=20,
)

# -----------------------------------------------------------------------------
# Figure export config (mirrors spectral_typing.py style)
# -----------------------------------------------------------------------------
figure_export_config = {
    "toImageButtonOptions": {
        "format": "png",  # png, svg, jpeg, webp
        "height": 700,
        "width": 1600,
        "scale": 2,
        "filename": "age_pdfs",
    },
    "modeBarButtonsToAdd": ["toImage"],
}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def get_engine_from_params(search: str):
    conn_str = get_connection_string_agepdfs(search)
    return create_engine(conn_str, pool_recycle=3600, pool_pre_ping=True)

def parse_bool_flag(qs_value, default=False):
    if qs_value is None:
        return default
    if isinstance(qs_value, str):
        val = qs_value.strip().lower()
        return val in ("1", "true", "yes", "y", "on")
    return bool(qs_value)

def parse_url_flags(search: str):
    """Return dict with UI defaults based on URL query params."""
    out = {
        "moca_aid": None,
        "log_x": True,      # default log x-axis for ages
        "log_y": False,     # default linear y for probability
        "cdf": False,
        "combine": False,
    }
    if not search:
        return out
    qs = parse_qs(urlparse(search).query)
    out["moca_aid"] = qs.get("moca_aid", qs.get("aid", [None]))[0]
    out["log_x"] = parse_bool_flag(qs.get("logx", [out["log_x"]])[0], out["log_x"])
    out["log_y"] = parse_bool_flag(qs.get("logy", [out["log_y"]])[0], out["log_y"])
    out["cdf"] = parse_bool_flag(qs.get("cdf", [out["cdf"]])[0], out["cdf"])
    out["combine"] = parse_bool_flag(qs.get("combine", [out["combine"]])[0], out["combine"])
    return out

def _normalize_pdf(age, pdf):
    """Normalize a PDF on a linear age axis using trapezoidal integration."""
    pdf = np.clip(pdf, 0.0, np.inf)
    area = np.trapz(pdf, age)
    if area <= 0 or not np.isfinite(area):
        return np.zeros_like(pdf)
    return pdf / area

def _cdf_from_pdf(age, pdf):
    cdf = np.cumsum((pdf[:-1] + pdf[1:]) * np.diff(age) / 2.0)
    cdf = np.concatenate([[0.0], cdf])
    if cdf[-1] <= 0:
        return np.zeros_like(cdf)
    return cdf / cdf[-1]

def _percentiles_from_cdf(age, cdf, ps=(0.16, 0.5, 0.84)):
    res = []
    for p in ps:
        res.append(np.interp(p, cdf, age))
    return tuple(res)

# -----------------------------------------------------------------------------
# Layout
# -----------------------------------------------------------------------------
layout = html.Div([
    dcc.Location(id="agepdfs-url"),
    html.H1("MOCA Association Age PDFs"),
    html.P([
        "Explore age probability distributions for a selected young association. ",
        "Choose an association (", html.Code("moca_aid"), 
        ") and filter by calculation methods. Display PDFs or CDFs, log/linear axes, ",
        "and optionally multiply selected PDFs to obtain a combined constraint."
    ], style={"fontStyle": "italic"}),
    html.Div([
        html.Label("Association (moca_aid)"),
        dcc.Dropdown(id="agepdfs-aid-dropdown", options=[], value=None, searchable=True, clearable=True, placeholder="Type to search moca_aid..."),
    ], style={"maxWidth": "600px", "marginBottom": "10px"}),
    html.Div([
        html.Label("Calculation methods", style={"fontWeight": "bold"}),
        dcc.Checklist(id="agepdfs-methods-checklist", options=[], value=[], inline=False)
    ], style={"maxWidth": "900px", "marginBottom": "10px"}),
    html.Div([
        html.Label("Display options", style={"fontWeight": "bold"}),
        dcc.Checklist(
            id="agepdfs-display-options",
            options=[
                {"label": "Log X (age)", "value": "log_x"},
                {"label": "Log Y (probability)", "value": "log_y"},
                {"label": "Show CDFs instead of PDFs", "value": "cdf"},
                {"label": "Combine selected PDFs", "value": "combine"},
            ],
            value=["log_x", "combine"],  # defaults: log_x + combined PDF
            inline=True
        )
    ], style={"marginBottom": "10px"}),
html.Div(id="agepdfs-combined-stats", style={"fontWeight": "bold", "marginBottom": "0px", "marginTop": "-9px"}),
    dcc.Graph(id="agepdfs-graph", figure=go.Figure(), config=figure_export_config),
    dcc.Store(id="agepdfs-db-cache"),
    html.Div([
        html.H2("Using URL Parameters"),
        html.P([
            "You can configure this page by appending parameters to the URL query string. ",
            "Supported parameters are:"
        ]),
        html.Ul([
            html.Li([html.Code("moca_aid"), " : pre-select the association."]),
            html.Li([html.Code("logx=true|false"), " : use logarithmic x-axis for age (default: true)."]),
            html.Li([html.Code("logy=true|false"), " : use logarithmic y-axis for probability (default: false; ignored for CDF)."]),
            html.Li([html.Code("cdf=true|false"), " : show CDF instead of PDF (default: false)."]),
            html.Li([html.Code("combine=true|false"), " : multiply selected PDFs and display combined curve (default: false)."]),
            html.Li([
                "Database connection (optional, falls back to environment variables): ",
                html.Code("user"), ", ", html.Code("password"), ", ",
                html.Code("host"), ", ", html.Code("port"), ", ", html.Code("db"), "."
            ]),
        ]),
        html.P([
            "Example: ",
            html.Code("/age-pdfs?moca_aid=ABDMG&logx=true&logy=false&cdf=false&combine=true"),
        ]),
    ], style={"padding": "20px", "backgroundColor": "#f9f9f9", "border": "1px solid #ddd", "borderRadius": "8px"}),
    html.Div(style={"height": "16px"}),
], className="container scalable")

# -----------------------------------------------------------------------------
# Callbacks
# -----------------------------------------------------------------------------
@dash.callback(
    Output("agepdfs-aid-dropdown", "options"),
    Output("agepdfs-aid-dropdown", "value"),
    Input("agepdfs-url", "search"),
)
def populate_aid_dropdown(search):
    """Populate moca_aid options; default selection can be set via URL param moca_aid."""
    flags = parse_url_flags(search)
    engine = get_engine_from_params(search)
    q = text("""
        SELECT DISTINCT daa.moca_aid
        FROM data_association_ages AS daa
        WHERE daa.moca_aid IS NOT NULL AND EXISTS (SELECT 1 FROM calc_association_age_pdfs AS cap WHERE cap.age_id = daa.id)
        ORDER BY daa.moca_aid
    """)
    df = pd.read_sql(q, engine)
    df = df.dropna(subset=["moca_aid"])  # remove NULLs to avoid invalid Dropdown options
    aids = sorted({str(aid) for aid in df["moca_aid"].tolist() if pd.notna(aid)})
    options = [{"label": aid, "value": aid} for aid in aids]
    default_value = flags["moca_aid"] if flags["moca_aid"] in aids else None
    return options, default_value

@dash.callback(
    Output("agepdfs-methods-checklist", "options"),
    Output("agepdfs-methods-checklist", "value"),
    Input("agepdfs-aid-dropdown", "value"),
    Input("agepdfs-url", "search"),
)
def populate_methods_for_aid(moca_aid, search):
    """List available calculation_method values for the selected association."""
    if not moca_aid:
        return [], []
    engine = get_engine_from_params(search)
    q = text("""
        SELECT DISTINCT daa.calculation_method, daa.comments
        FROM data_association_ages AS daa
        JOIN calc_association_age_pdfs AS cap
          ON cap.age_id = daa.id
        WHERE daa.moca_aid = :aid
          AND daa.calculation_method IS NOT NULL
        ORDER BY daa.calculation_method
    """)
    df = pd.read_sql(q, engine, params={"aid": moca_aid})
    if df.empty:
        return [], []

    # For each method, pick the first non-null, non-empty comment (if any)
    df["comments"] = df["comments"].apply(lambda x: x.strip() if isinstance(x, str) else None)
    comment_map = (
        df.dropna(subset=["calculation_method"]).groupby("calculation_method")["comments"]
          .apply(lambda s: next((c for c in s if isinstance(c, str) and len(c) > 0), None))
          .to_dict()
    )

    methods = sorted({str(m) for m in df["calculation_method"].dropna().astype(str)})

    # Build labels with method and an inline gray comment if present
    from dash import html as _html
    opts = []
    for m in methods:
        c = comment_map.get(m)
        if c:
            label = _html.Span([
                _html.Span(m),
                _html.Span(" — "+c, style={"color": "#555", "fontStyle": "italic", "marginLeft": "6px"})
            ])
        else:
            label = _html.Span(m)
        opts.append({"label": label, "value": m})

    # default: select all
    return opts, methods

@dash.callback(
    Output("agepdfs-graph", "figure"),
    Output("agepdfs-graph", "config"),
    Output("agepdfs-combined-stats", "children"),
    Input("agepdfs-aid-dropdown", "value"),
    Input("agepdfs-methods-checklist", "value"),
    Input("agepdfs-display-options", "value"),
    Input("agepdfs-url", "search"),
)
def update_graph(moca_aid, methods, display_opts, search):
    config = figure_export_config.copy()
    config["toImageButtonOptions"] = config.get("toImageButtonOptions", {}).copy()
    config["toImageButtonOptions"]["filename"] = f"age_pdfs_{moca_aid or 'none'}_{datetime.now().strftime('%y%m%d')}"
    if not (moca_aid and methods):
        fig = go.Figure()
        fig.update_layout(margin=dict(l=60, r=30, t=25, b=60), legend_title_text="Calculation method")
        return fig, config, ""

    engine = get_engine_from_params(search)
    # Fetch PDFs (log probability density) for selected methods
    q = text("""
        SELECT daa.id AS age_id,
               daa.calculation_method,
               cap.age_myr,
               cap.log_probability_density
        FROM data_association_ages AS daa
        JOIN calc_association_age_pdfs AS cap
          ON cap.age_id = daa.id
        WHERE daa.moca_aid = :aid
          AND daa.calculation_method IN :methods
        ORDER BY daa.calculation_method, cap.age_myr
    """)
    # SQLAlchemy Core supports expanding IN with tuple
    df = pd.read_sql(q, engine, params={"aid": moca_aid, "methods": tuple(methods)})

    if df.empty:
        fig = go.Figure()
        fig.update_layout(title="No PDFs found for the selected inputs.", margin=dict(l=60, r=30, t=25, b=60))
        return fig, config, ""

    # Build individual method curves
    show_cdf = "cdf" in (display_opts or [])
    use_logx = "log_x" in (display_opts or [])
    use_logy = "log_y" in (display_opts or [])
    do_combine = "combine" in (display_opts or [])

    fig = go.Figure()
    combined_stats_text = ""

    # For combining, we prepare a common log-age grid covering all methods
    # First collect per-method arrays
    method_traces = []
    grids = []
    for method in sorted(df["calculation_method"].unique()):
        sub = df[df["calculation_method"] == method].dropna(subset=["age_myr", "log_probability_density"]).copy()
        sub = sub[sub["age_myr"] > 0]
        if sub.empty:
            continue
        # Sort by age
        sub.sort_values("age_myr", inplace=True)
        age = sub["age_myr"].to_numpy(dtype=float)
        logpdf = sub["log_probability_density"].to_numpy(dtype=float)
        # Convert to linear PDF for plotting if pdf view; for CDF we need normalized PDF
        pdf = np.exp(logpdf - np.nanmax(logpdf))  # stability shift per method
        pdf = _normalize_pdf(age, pdf)

        if show_cdf:
            yvals = _cdf_from_pdf(age, pdf)
            yname = "CDF"
        else:
            yvals = pdf
            yname = "PDF"

        method_traces.append((method, age, yvals, pdf))  # keep pdf for combine
        grids.append(age)

        fig.add_trace(go.Scatter(
            x=age, y=yvals, mode="lines",
            name=f"{method}",
            line=dict(width=2.2),
            opacity=0.65,
            hovertemplate="Age: %{x:.3g} Myr<br>"+yname+": %{y:.3g}<extra>"+method+"</extra>"
        ))

    # Combined PDF
    if do_combine and method_traces:
        # Build common log10(age) grid
        all_age = np.concatenate([a for _, a, _, _ in method_traces])
        amin = np.nanmin(all_age[all_age > 0])
        amax = np.nanmax(all_age)
        # make a reasonable grid resolution in log age
        loga_min = np.log10(amin)
        loga_max = np.log10(amax)
        loga_grid = np.linspace(loga_min, loga_max, 1200)
        age_grid = 10**loga_grid

        # Interpolate log-PDFs on the log-age grid and sum in log space
        logpdf_sum = None
        for method, age, _, pdf in method_traces:
            # Recompute log-pdf from normalized pdf to maintain consistency
            # Avoid log(0)
            pdf_safe = np.clip(pdf, 1e-300, None)
            logpdf_method = np.log(pdf_safe)
            # Interpolate vs log10(age)
            loga = np.log10(age)
            # Ensure strictly increasing for interp
            order = np.argsort(loga)
            loga_sorted = loga[order]
            logpdf_sorted = logpdf_method[order]
            interp_vals = np.interp(loga_grid, loga_sorted, logpdf_sorted, left=-1e9, right=-1e9)
            if logpdf_sum is None:
                logpdf_sum = interp_vals
            else:
                logpdf_sum = np.where((interp_vals < -1e8) | (logpdf_sum < -1e8), -1e9, logpdf_sum + interp_vals)

        # Convert back to linear PDF, normalize on linear-age axis
        combined_pdf = np.exp(logpdf_sum - np.nanmax(logpdf_sum))
        combined_pdf = np.where(np.isfinite(combined_pdf), combined_pdf, 0.0)
        combined_pdf = _normalize_pdf(age_grid, combined_pdf)

        if show_cdf:
            combined_y = _cdf_from_pdf(age_grid, combined_pdf)
            yname = "CDF"
        else:
            combined_y = combined_pdf
            yname = "PDF"

        # Compute 16/50/84 percentiles on combined distribution
        combined_cdf = _cdf_from_pdf(age_grid, combined_pdf)
        a16, a50, a84 = _percentiles_from_cdf(age_grid, combined_cdf, ps=(0.16, 0.5, 0.84))
        # Add percentile lines
        fig.add_vline(x=a50, line_width=3, line_dash="dash", line_color="darkred")
        fig.add_vline(x=a16, line_width=2, line_dash="dot", line_color="darkred", opacity=0.6)
        fig.add_vline(x=a84, line_width=2, line_dash="dot", line_color="darkred", opacity=0.6)

        # Add combined trace
        fig.add_trace(go.Scatter(
            x=age_grid, y=combined_y, mode="lines",
            name=f"Combined {yname}",
            line=dict(width=4, color="black"),
            opacity=0.8,
            hovertemplate="Age: %{x:.3g} Myr<br>"+yname+": %{y:.3g}<extra>Combined</extra>"
        ))

        # Title text for combined estimate
        errm = a50 - a16
        errp = a84 - a50
        combined_stats_text = f"Combined PDF age: {a50:.1f} (+{errp:.1f}/-{errm:.1f}) Myr"

    # Determine dynamic x-range based on PDFs (not CDF)
    x_range = None
    if not show_cdf and method_traces:
        thr = 0.0 if use_logy else 0.005
        mins = []
        maxs = []
        for _m, a, _yvals, pdf in method_traces:
            msk = np.isfinite(pdf) & (pdf > thr) & np.isfinite(a) & (a > 0)
            if np.any(msk):
                mins.append(np.min(a[msk]))
                maxs.append(np.max(a[msk]))
        if do_combine and 'combined_pdf' in locals():
            mskc = np.isfinite(combined_pdf) & (combined_pdf > thr) & np.isfinite(age_grid) & (age_grid > 0)
            if np.any(mskc):
                mins.append(np.min(age_grid[mskc]))
                maxs.append(np.max(age_grid[mskc]))
        if mins and maxs:
            xmin = float(np.min(mins))
            xmax = float(np.max(maxs))
            if np.isfinite(xmin) and np.isfinite(xmax) and xmin < xmax:
                x_range = [xmin, xmax]
    elif show_cdf and method_traces:
        # In CDF mode, focus on the central region where CDF is between 0.005 and 0.995
        thr = 0.005
        mins = []
        maxs = []
        for _m, a, yvals, _pdf in method_traces:
            msk = (
                np.isfinite(a) & (a > 0) &
                np.isfinite(yvals) & (yvals > thr) & (yvals < (1.0 - thr))
            )
            if np.any(msk):
                mins.append(np.min(a[msk]))
                maxs.append(np.max(a[msk]))
        if do_combine and 'combined_y' in locals():
            mskc = (
                np.isfinite(age_grid) & (age_grid > 0) &
                np.isfinite(combined_y) & (combined_y > thr) & (combined_y < (1.0 - thr))
            )
            if np.any(mskc):
                mins.append(np.min(age_grid[mskc]))
                maxs.append(np.max(age_grid[mskc]))
        if mins and maxs:
            xmin = float(np.min(mins))
            xmax = float(np.max(maxs))
            if np.isfinite(xmin) and np.isfinite(xmax) and xmin < xmax:
                x_range = [xmin, xmax]
    
    # Add 10% padding in all cases; enforce minimum coverage only for log-x
    if x_range is not None:
        xmin, xmax = x_range
        if np.isfinite(xmin) and np.isfinite(xmax) and xmax > xmin and xmin > 0:
            width = xmax - xmin
            # 10% padding on both sides
            pad = 0.1 * width
            if xmin - pad > 0:
                xmin = xmin - pad
            else:
                # If padding would push below zero, shrink by 10% multiplicatively instead
                xmin = max(xmin * 0.9, np.finfo(float).tiny)
            xmax = xmax + pad
            # Enforce >= 2 orders of magnitude only when x-axis is log
            if use_logx:
                min_factor = 100.0  # 2 decades
                factor = xmax / max(xmin, 1e-12)
                if factor < min_factor:
                    # Expand symmetrically in log space around geometric mean
                    center = np.sqrt(xmin * xmax)
                    half = np.sqrt(min_factor)
                    xmin = center / half
                    xmax = center * half
            x_range = [xmin, xmax]

    # Axes and layout
    fig.update_layout(
        margin=dict(l=60, r=30, t=25, b=60),
        legend_title_text="Calculation method",
        xaxis_title="Age (Myr)",
        yaxis_title="Probability density",
        plot_bgcolor="white",
    )

    # Style axes with thick box, thicker/longer tick marks, and larger tick label text
    fig.update_xaxes(
        showline=True,
        linewidth=3,
        linecolor="black",
        mirror=True,
        ticks="outside",
        tickwidth=2.5,
        ticklen=8,
        tickfont=dict(size=16),
    )
    fig.update_yaxes(
        showline=True,
        linewidth=3,
        linecolor="black",
        mirror=True,
        ticks="outside",
        tickwidth=2.5,
        ticklen=8,
        tickfont=dict(size=16),
    )

    # Apply axis types and tick behavior
    if use_logx:
        fig.update_xaxes(
            type="log",
            dtick=1,                 # major ticks at powers of 10
            tick0=0,                 # start at 10^0 decade (auto shifts with range)
            minor=dict(
                ticks="outside",
                gridcolor="rgba(0,0,0,0.05)",
                showgrid=True,
                ticklen=4
            ),
            exponentformat="power",
            showexponent="all",
            showgrid=True,
            gridwidth=1,
            gridcolor="rgba(0,0,0,0.1)",
        )
    else:
        fig.update_xaxes(
            type="linear",
            showgrid=True,
            gridwidth=1,
            gridcolor="rgba(0,0,0,0.1)",
            minor=dict(showgrid=True,gridcolor="rgba(0,0,0,0.05)")
        )

    if show_cdf:
        fig.update_yaxes(
            type="linear",
            range=[0, 1],
            showgrid=True,
            gridwidth=1,
            gridcolor="rgba(0,0,0,0.1)",
        )
    else:
        fig.update_yaxes(
            type=("log" if use_logy else "linear"),
            showgrid=True,
            gridwidth=1,
            gridcolor="rgba(0,0,0,0.1)",
            rangemode="tozero"  # force lower bound to 0 in linear mode
        )

    # Apply dynamic x-range if computed (log axis expects log10 values)
    if x_range is not None:
        if use_logx:
            fig.update_xaxes(range=[float(np.log10(x_range[0])), float(np.log10(x_range[1]))])
        else:
            fig.update_xaxes(range=x_range)

    return fig, config, combined_stats_text
