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

# Load data
moca_vanilla = MocaEngine()
moca = MocaEngine()


query_e = """
    SELECT ds.moca_specid, ms.spectrum_name, COALESCE(ms.flux_units,"NO_UNITS") AS flux_units, ds.wavelength_angstrom*1e-4 AS lam, flux_flambda AS sp, flux_flambda_unc AS esp
    FROM moca_spectra ms
    JOIN data_spectra ds ON(ds.moca_specid=ms.moca_specid AND ds.adopted=1)
"""

unselected_opacity = 0.1
selected_opacity = 1

df_all_spectra = moca.query("SELECT moca_specid, CONCAT(ms.moca_specid,': ',COALESCE(CONCAT(mo.designation, ' (',spt.spectral_type, ') with ', ms.moca_instid,COALESCE(CONCAT(' in ', ms.instrument_mode_name,' mode'),''),COALESCE(CONCAT(' (', ms.data_collection_date,')'),'')),ms.spectrum_name)) AS spectrum_name FROM moca_spectra ms LEFT JOIN moca_objects mo USING(moca_oid) LEFT JOIN (SELECT moca_oid, spectral_type FROM cdata_spectral_types WHERE adopted=1) spt USING(moca_oid)")

dfe = moca_vanilla.query("SELECT ds.moca_specid, ms.spectrum_name, ms.flux_units, ds.wavelength_angstrom*1e-4 AS lam, flux_flambda AS sp, flux_flambda_unc AS esp FROM moca_spectra ms JOIN data_spectra ds ON(ds.moca_specid=ms.moca_specid AND ds.adopted=1) LIMIT 0")

#To make hex colors more transparent
def hex_to_rgba(hex_color, alpha=0.5):
    hex_color = hex_color.lstrip('#')
    return f'rgba({int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}, {alpha})'

def weighted_median(values, weights):
    i = np.argsort(values)
    c = np.cumsum(weights[i])
    return values[i[np.searchsorted(c, 0.5 * c[-1])]]

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
        id="banner",
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
def generate_spectrum(df_spectra, df_aids, selected_data, style, self_figure):

    # Read layer properties
    hover = "closest"

    if "hover" not in style:
        hover = False
    
    xtitle  = "Wavelength (μm)"
    ytitle  = "Relative spectral flux density <i>F<sub>λ</sub></i>"
    
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
    data = []
    alpha = 0.2

    for i in range(nspectra):
        labeli = df_aids.loc[df_aids['moca_specid'] == unique_specids[i], 'spectrum_name'].values[0]
        colori = colormap[unique_specids[i]]

        #import pdb; pdb.set_trace()
        dfi = df_spectra[df_spectra['moca_specid'] == unique_specids[i]].dropna(subset=['sp', 'lam']).copy()

        #Normalize the spectrum with a weighted median, weight = SNR^2 if ESP is defined, SP^2 otherwise
        #if not dfi['esp'].replace(0, pd.NA).isna().all():
        #    signal_values = dfi['sp'].fillna(0).values / dfi['esp'].replace(0, pd.NA).fillna(dfi['esp'].median()).fillna(1).values
        #else:
        #    signal_values = dfi['sp'].fillna(0).values
        
        #Using a simpler way to normalize because errors often misbehave

        smoothed_signal = dfi['sp'].rolling(window=50).median().values
        
        weights = np.nan_to_num(smoothed_signal ** 2)
        smoothed_signal = np.nan_to_num(smoothed_signal, nan=np.nanmedian(smoothed_signal))
        
        norm = weighted_median(smoothed_signal, weights/np.sum(weights))

        dfi.loc[:, 'esp'] = dfi['esp'] / norm
        dfi.loc[:, 'sp'] = dfi['sp'] / norm

        x_array = dfi['lam'].values
        y_array = dfi['sp'].values

        # Insert NaNs in the gaps larger than 10x the median spacing
        x_with_nans, y_with_nans, ey_with_nans = insert_nans_in_gaps(dfi['lam'].values, dfi['sp'].values, ey_array=dfi['esp'].values, threshold_factor=10)

        new_trace = go.Scattergl(x=x_with_nans,y=y_with_nans,opacity=0.8,mode='lines',name=labeli,line=dict(color=colori, width=2, shape='hv'),connectgaps=False)

        if not dfi['esp'].isna().all():
            
            #dfi_filtered = dfi[['lam', 'sp', 'esp']].dropna()

            # Upper bound trace
            # Upper bound trace
            # Find the indices where NaNs occur in x_with_nans
            # Find the indices where NaNs occur in x_with_nans
            nan_indices = np.where(np.isnan(y_with_nans))[0]

            # Initialize start_idx at 0
            start_idx = 0

            # Loop over the nan_indices to handle each segment
            for nan_idx in nan_indices:
                #if start_idx !=0:
                #    continue
                # Only plot valid segments (ignore consecutive NaNs)
                if nan_idx > start_idx:
                    # Upper bound trace for the current segment
                    upper_bound_trace = go.Scatter(
                        x=x_with_nans[start_idx:nan_idx],  # Plot until nan_idx-1
                        y=y_with_nans[start_idx:nan_idx] + ey_with_nans[start_idx:nan_idx],
                        mode='lines',
                        line=dict(width=0),  # No line for the upper bound
                        hoverinfo='none',
                        fill=None,
                        showlegend=False
                    )

                    # Lower bound trace with fill='tonexty' for the current segment
                    lower_bound_trace = go.Scatter(
                        x=x_with_nans[start_idx:nan_idx],  # Plot until nan_idx-1
                        y=y_with_nans[start_idx:nan_idx] - ey_with_nans[start_idx:nan_idx],
                        mode='lines',
                        line=dict(width=0),  # No line for the lower bound
                        fill='tonexty',  # Fill between lower and upper bound
                        fillcolor=hex_to_rgba(colori, alpha),  # Set the fill color
                        hoverinfo='none',
                        showlegend=False
                    )

                    # Append traces to data
                    data.append(upper_bound_trace)
                    data.append(lower_bound_trace)

                # Move the start index to the point after the current NaN
                start_idx = nan_idx + 1

            # Handle the last segment after the last NaN
            if start_idx < len(x_with_nans):
                upper_bound_trace = go.Scatter(
                    x=x_with_nans[start_idx:],  # Plot remaining segment
                    y=y_with_nans[start_idx:] + ey_with_nans[start_idx:],
                    mode='lines',
                    line=dict(width=0),
                    hoverinfo='none',
                    fill=None,
                    showlegend=False
                )

                lower_bound_trace = go.Scatter(
                    x=x_with_nans[start_idx:],  # Plot remaining segment
                    y=y_with_nans[start_idx:] - ey_with_nans[start_idx:],
                    mode='lines',
                    line=dict(width=0),
                    fill='tonexty',
                    fillcolor=hex_to_rgba(colori, alpha),
                    hoverinfo='none',
                    showlegend=False
                )

                # Append final segment traces to data
                data.append(upper_bound_trace)
                data.append(lower_bound_trace)


            #data.append(upper_bound_trace)
            #data.append(lower_bound_trace)
        
        data.append(new_trace)

        min_lam = np.nanmin(dfi['lam'])
        max_lam = np.nanmax(dfi['lam'])
        xrange[0] = min(xrange[0], min_lam)
        xrange[1] = max(xrange[1], max_lam)

        # Calculate the IQR of 'sp' + 'esp' values
        Q1 = np.nanpercentile(dfi['sp'] + dfi['esp'].fillna(0), 5)
        Q3 = np.nanpercentile(dfi['sp'] + dfi['esp'].fillna(0), 98)
        IQR = Q3 - Q1

        # Determine the range for normalization using IQR
        min_y = Q1 - 0.1 * IQR
        max_y = Q3 + 0.1 * IQR

        yrange[0] = min(yrange[0], min_y)
        yrange[1] = max(yrange[1], max_y)

    xrange += np.array([-1, 1]) * (xrange[1] - xrange[0]) * 0.02
    yrange += np.array([-1,1])*(yrange[1]-yrange[0])*0.1
    layout.xaxis.range = xrange
    layout.yaxis.range = yrange

    fig = go.Figure(data=data,layout=layout)
                     
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
                    className="two columns",
                    children=[
                        dcc.Checklist(
                            id="spectram-view-selector-spectrapage",
                            options=[
                                {
                                    "label": "Enable Hover Properties",
                                    "value": "hover",
                                },
                            ],
                            value=[],
                        ),
                    ],
                ),
                html.Div(
                    className="ten columns",
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
            if 'moca_specid' in parsed_url_data.keys():
                specid_select = [int(x) for x in parsed_url_data['moca_specid'][0].split(',')]
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
    df_aids = moca.query("SELECT moca_specid, CONCAT(ms.moca_specid,': ',COALESCE(CONCAT(mo.designation, ' (',spt.spectral_type, ') with ', ms.moca_instid,COALESCE(CONCAT(' in ', ms.instrument_mode_name,' mode'),''),COALESCE(CONCAT(' (', ms.data_collection_date,')'),'')),ms.spectrum_name)) AS spectrum_name FROM moca_spectra ms LEFT JOIN moca_objects mo USING(moca_oid) LEFT JOIN (SELECT moca_oid, spectral_type FROM cdata_spectral_types WHERE adopted=1) spt USING(moca_oid)")
    aid_options = [{"label": row["spectrum_name"], "value": row["moca_specid"]} for index, row in df_aids.iterrows()]

    #Prevent app from crashing if no spectra are selected
    #import pdb; pdb.set_trace()
    if len(specid_select) == 0:
        df = dfe
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
    ),
    state=dict(specid_select=State("specid-select-spectrapage", "value"), self_figure=State("spectra-map-spectrapage", "figure")),
)
def update_spectrum_spectrapage(
    selections, 
    jsonified_db_data, spectra_view
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

    return generate_spectrum(df, df_aids, processed_data, spectra_view, self_figure)

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