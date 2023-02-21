import dash
from dash import html, dcc, dash_table, get_asset_url

dash.register_page(__name__)

import pathlib, os
import colorsys
import numpy.core.defchararray as np_f

import pandas as pd
import numpy as np

import plotly.graph_objs as go
from dash.dependencies import Input, Output, State

from mocapy import *

initial_aids = ["ABDMG","BPMG","TWA","THA"]
initial_mtids = ["BF","HM"]

figure_export_config = {
  'toImageButtonOptions': {
    'format': 'png', # one of png, svg, jpeg, webp
    'height': 500*2,
    'width': 700*2,
    'scale': 6*2 # Multiply title/legend/axis/canvas sizes by this factor
  }
}

# Load data
moca = MocaEngine()

#Query an empty row to obtain the structure for the table
df_columns = ['designation','moca_aid','moca_mtid','spt','moca_oid','gmag','bmag', 'rmag','plx','dmod','dr3_ruwe','x','y','z','u','v','w','prot_days','gaia_act']
dfe = moca.query("SELECT "+", ".join(df_columns)+" FROM summary_all_members LIMIT 0")
dfme = moca.query("SELECT dbs.* FROM moca_banyan_sigma_models mbs LEFT JOIN data_banyan_sigma_models dbs USING(moca_bsmdid) WHERE mbs.adopted=1 LIMIT 0")

unselected_opacity = 0.1

# Load a list of all associations for the Dropdown menu
df_aids = moca.query("SELECT moca_aid FROM moca_associations")
df_mtids = moca.query("SELECT moca_mtid, name, description FROM (SELECT * FROM (SELECT mt.* FROM moca_membership_types mt JOIN (SELECT DISTINCT moca_mtid FROM summary_all_members) dm ON(dm.moca_mtid=mt.moca_mtid)) oq) oq2 ORDER BY level DESC")

text_mtids = ("* **"+df_mtids["moca_mtid"]+"**: "+df_mtids["description"]).values.astype("U").tolist()

print("Downloaded "+str(len(df_aids))+" rows of data for associations information")

df_cmd_field = moca.query("SELECT xdata gr, ydata m_g FROM data_astro_sequences WHERE moca_seqid='grp_mg_gaiadr3_field_scatter'")
df_cmd_field['customdata'] = 'NaN'
field_opacity = 0.2
field_color_fraction = 0.5
field_markersize = 3
bcg_color = np.array([230,236,245])

df_cmd_seq_25 = moca.query("SELECT xdata gr, ydata m_g FROM data_astro_sequences WHERE moca_seqid='grp_mg_gaiaedr3_15myr_30myr'")
df_cmd_seq_40 = moca.query("SELECT xdata gr, ydata m_g FROM data_astro_sequences WHERE moca_seqid='grp_mg_gaiaedr3_30myr_50myr'")
df_cmd_seq_100 = moca.query("SELECT xdata gr, ydata m_g FROM data_astro_sequences WHERE moca_seqid='grp_mg_gaiaedr3_50myr_250myr'")
df_cmd_seq_25['customdata'] = 'NaN'
df_cmd_seq_40['customdata'] = 'NaN'
df_cmd_seq_100['customdata'] = 'NaN'


df_prot_seq_prae = moca.query("SELECT xdata br, ydata prot FROM data_astro_sequences WHERE moca_seqid='bprp_prot_prae_prelim'")
df_prot_seq_ple = moca.query("SELECT xdata br, ydata prot FROM data_astro_sequences WHERE moca_seqid='bprp_prot_ple_prelim'")
df_prot_seq_ngc6811 = moca.query("SELECT xdata br, ydata prot FROM data_astro_sequences WHERE moca_seqid='bprp_prot_ngc6811_prelim'")
df_prot_seq_prae['customdata'] = 'NaN'
df_prot_seq_ple['customdata'] = 'NaN'
df_prot_seq_ngc6811['customdata'] = 'NaN'

print("Downloaded "+str(len(df_cmd_field))+" rows of data for field stars")

# Assign color to legend
def colormap_picker(aid_list):
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
    colormap = {}
    for ind, moca_aid in enumerate(aid_list):
        colormap[moca_aid] = colors[ind%len(colors)]
    return colormap

def selection_helper(selections):

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

    print(" Triggered by "+prop_id)
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

# Conditional styling for the DataTable
def get_style_data_conditional(selected_rows: list = []) -> list:
    non_selected_band_color = "rgb(229, 236, 246)"
    selected_band_color = '#98c21f'
    return [
        {
            'if': {'row_index': 'odd'},
            'backgroundColor': non_selected_band_color
        },
        {
            'if': {'row_index': 'even'},
            'backgroundColor': "white"
        },
        {
            'if': {'row_index': selected_rows},
            'backgroundColor': selected_band_color,
            'fontWeight': 'bold',
            'color': 'white',
        },
    ]

# Visual website banner
def build_banner():
    return html.Div(
        id="banner",
        className="banner",
        children=[
            html.Img(src=get_asset_url("dash-logo.png")),
            html.H6("MOCA explorer"),
        ],
    )

# Hover display
def build_hover(dff):
    return list(
        map(
            lambda x1, x2, x3, x4, x5: "MOCA OID : "+str(int(x1))+"<br>Designation : "+str(x2)+"<br>Membership : "+str(x3)+"<br>SPT : "+str(x4)+"<br>RUWE : "+str('%.1f' %x5),
            dff["moca_oid"],
            dff["designation"],
            dff["moca_mtid"],
            dff["spt"],
            dff["dr3_ruwe"],
        )
    )

def build_graph_title(title):
    return html.P(className="graph-title", children=title)

# Build 3D ellipsoids to show BANYAN models
def build_ellipsoid_3d(offset, covar_matrix, trace_color, opacity=0.15):
    
    #Build rotation matrix with singular value decomposition
    u, s, vh = np.linalg.svd(covar_matrix)
    rotmat = u
    
    #3D version of 68% volume inclusion requires a factor 1.557
    #inverf((erf(1d0/sqrt(2d0)))^(1d0/3))*sqrt(2d0)
    a, b, c = np.sqrt(s)*1.557

    #Build 3D grid
    phi = np.linspace(0, 2*np.pi,num=20)
    theta = np.linspace(-np.pi/2, np.pi/2,num=20)
    phi, theta=np.meshgrid(phi, theta)

    x = np.cos(theta) * np.sin(phi) * a
    y = np.cos(theta) * np.cos(phi) * b
    z = np.sin(theta) * c

    xf = x
    yf = z*b/c
    zf = y*c/b

    # Create the plot
    lines = []
    line_marker = dict(color=trace_color, width=2)
    
    # First layer of grid lines
    for i, j, k in zip(x, y, z):
        ir, jr, kr = rotmat@[i,j,k]
        lines.append(go.Scatter3d(x=ir+offset[0], y=jr+offset[1], z=kr+offset[2], mode='lines', line=line_marker, hoverinfo='skip', opacity=opacity, showlegend=False))
    
    # Second layer of grid lines rotated by 90 degrees
    for i, j, k in zip(xf, yf, zf):
        ir, jr, kr = rotmat@[i,j,k]
        lines.append(go.Scatter3d(x=ir+offset[0], y=jr+offset[1], z=kr+offset[2], mode='lines', line=line_marker, hoverinfo='skip', opacity=opacity, showlegend=False))

    return lines

def build_ellipsoid_2d(offset, covar_matrix, trace_color, opacity=0.3):
    
    # Build rotation matrix with singular value decomposition
    u, s, vh = np.linalg.svd(covar_matrix)
    rotmat = u
    
    # 2D version of 68% volume inclusion requires a factor 1.3605
    # inverf((erf(1d0/sqrt(2d0)))^(1d0/2))*sqrt(2d0)
    a, b = np.sqrt(s)*1.3605

    # Build 3D grid
    theta = np.linspace(-np.pi, np.pi, num=50)

    x = np.cos(theta) * a
    y = np.sin(theta) * b

    # Create the plot
    line_marker = dict(color=trace_color, width=2)
    xr, yr = rotmat@[x,y]
    data = go.Scattergl(x=xr+offset[0], y=yr+offset[1], mode='lines', line=line_marker, hoverinfo='skip', opacity=opacity, showlegend=False)
    
    return data

# RV Time series
def generate_rvts(dfrvts):

    layout = go.Layout(
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        xaxis={'title':"Epoch (years)"},
        yaxis={'title':"Radial velocity (km/s)"},
        hovermode="closest",
        margin=dict(l=110, r=50, t=50, b=50),
    )

    hovertemplate = "%{text}<br><br>Year : %{x:.1f}<br>RV (km/s) : %{y:.1f}<extra></extra>"
    data = []

    text_list = list(
        map(
            lambda x1, x2, x3, x4, x5, x6: "RV error (km/s) : "+str(x1)+"<br>N : "+str(x2)+"<br>Bibcode : "+str(x3)+"<br>Mission : "+str(x4)+str(x5)+"<br>Instrument : "+str(x6),
            dfrvts["erv"],
            dfrvts["n_measurements"],
            dfrvts["bibcode"],
            dfrvts["mission_name"],
            dfrvts["data_release"],
            dfrvts["moca_instid"],
        ))

    new_trace = go.Scattergl(
        x=dfrvts["yr"].values,
        y=dfrvts['rv'].values,
        opacity=0.8,
        mode="markers",
        #marker=dict(color="#000000", size=8),
        hovertemplate=hovertemplate,
        marker=dict(
            color='rgba(0,0,0,0)',
            size=10,
            line=dict(
                color='DarkSlateGrey',
                width=2,
            ),
        ),
        text=text_list,
        error_y=dict(
            type='data',
            array=dfrvts['erv'].values,
            visible=True),
        )
    
    data.append(new_trace)

    fig = go.Figure(data=data,layout=layout)

    print("RVTS FIGURE DRAWN")
    
    return fig

def generate_spectrum(dfspe):

    #Read hover property
    hoverinfo = "skip"

    layout = go.Layout(
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        xaxis={'title':"Wavelength (Angstroms)"},
        yaxis={'title':"Spectral flux density (Flambda)"},
        margin=dict(l=110, r=50, t=50, b=50),
    )

    data = []

    new_trace = go.Scattergl(x=dfspe["wv"].values,y=dfspe['ff'].values/dfspe['ff'].median(),opacity=0.8,mode="lines")
    data.append(new_trace)

    fig = go.Figure(data=data,layout=layout)

    fig.update_layout(yaxis_range=[0,3])
    fig.update_layout(xaxis_range=[dfspe["wv"].min(),dfspe["wv"].max()])
    print("SP FIGURE DRAWN")

    fig.add_annotation(
        x=1,
        y=1,
        xref="x domain",
        yref="y domain",
        text="MOCAdb",
        showarrow=False,
        align="right",
        valign="top",
        opacity=0.8,
        font=dict(
            family="Courier New, monospace",
            size=16,
            color="rgb(192,198,206)",
            ),
        )
    fig.show()

    return fig

def generate_xy_map(dff, dfm, associations, xvar, yvar, xtitle, ytitle, title, selected_data, style, hover_select):

    #Read hover property
    hoverinfo = "skip"
    try:
        if hover_select[0] == 'Enable Hover Properties':
            hoverinfo = None
    except:
        void = 1

    # Read layer properties
    models_visible = assume_membership = True
    if "BANYAN Models" not in style:
        models_visible = False
    if "assmem" not in style:
        assume_membership = False

    if assume_membership:
        xvar += "_assmem"
        yvar += "_assmem"

    layout = go.Layout(
        clickmode="event+select",
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        dragmode="lasso",
        xaxis={'title':xtitle},
        yaxis={'title':ytitle},
        showlegend=True,
        #autosize=True,
        #hovermode=hover,
        hovermode="closest",
        margin=dict(l=110, r=50, t=50, b=50),
        legend=dict(
            orientation="h",
            x=0,
            y=-0.2,
            yanchor="top",
        ),
    )

    colormap = colormap_picker(associations)

    data = []

    text_list = build_hover(dff)
    aid_list = dff["moca_aid"].tolist()
    text_list = [aid_list[i] + "<br>" + text_list[i] for i in range(len(text_list))]
    dff['text_list'] = text_list

    for association in associations:

        dff_aid = dff[dff["moca_aid"] == association]
        if selected_data is None:
            selected_index = None
        else:
            selected_index = np.where(dff_aid['moca_oid'].isin(selected_data))[0]

        new_trace = go.Scattergl(
            x=dff_aid[xvar],#This is the x in the MOCA column
            y=dff_aid[yvar],#This is the y in the MOCA column
            opacity=0.8,
            mode="markers",
            marker=dict(color=colormap[association], size=4),#, line=dict(width=2,color='DarkSlateGrey')
            hoverinfo=hoverinfo,
            text=dff_aid['text_list'],
            name=association,
            selectedpoints=selected_index,
            customdata=dff_aid["moca_oid"],
        )
        new_trace.update(unselected=dict(marker=dict(opacity=unselected_opacity)))#, line=dict(width=2,color='DarkSlateGrey')
        data.append(new_trace)

        if models_visible:
        
            dfm_aid = dfm[dfm["moca_aid"] == association]

            for index, dfm_row in dfm_aid.iterrows():

                #Rebuild covariance matrix and offset from the models dataframe
                offset = np.array([dfm_row[xvar+'_cen'],dfm_row[yvar+'_cen']])
                covar_matrix = np.array([
                    [dfm_row[xvar+xvar+'_covar'],dfm_row[xvar+yvar+'_covar']],
                    [dfm_row[xvar+yvar+'_covar'],dfm_row[yvar+yvar+'_covar']]
                    ])

                ellipse = build_ellipsoid_2d(offset, covar_matrix, colormap[association])
                
                data.append(ellipse)
    
    new_trace = go.Scattergl(
            x=[0],
            y=[0],
            opacity=0.8,
            mode="markers",
            marker_symbol="cross",
            marker={"color": "#000000", "size": 9},
            text="Sun",
            name="Sun",
        )
    data.append(new_trace)

    fig = go.Figure(data=data,layout=layout)

    #Default axis range
    if (xvar=='x' or xvar=='y' or xvar=='z'):
        fig.update_layout(xaxis_range=[-150,150])
    if (yvar=='x' or yvar=='y' or yvar=='z'):
        fig.update_layout(yaxis_range=[-150,150])
    if xvar=='u':
        fig.update_layout(xaxis_range=[-80,70])
    if yvar=='u':
        fig.update_layout(yaxis_range=[-80,70])
    if xvar=='v':
        fig.update_layout(xaxis_range=[-70,20])
    if yvar=='v':
        fig.update_layout(yaxis_range=[-70,20])
    if xvar=='w':
        fig.update_layout(xaxis_range=[-70,20])
    if yvar=='w':
        fig.update_layout(yaxis_range=[-70,20])

    fig.add_annotation(
        x=1,
        y=1,
        xref="x domain",
        yref="y domain",
        text="MOCAdb",
        showarrow=False,
        align="right",
        valign="top",
        opacity=0.8,
        font=dict(
            family="Courier New, monospace",
            size=16,
            color="rgb(192,198,206)",
            ),
        )

    return fig

def generate_xyz_map(dff, dfm, associations, xvar, yvar, zvar, xtitle, ytitle, ztitle, title, selected_data, style, hover_select):

    # Read hover property
    hover = False
    try:
        if hover_select[0] == 'Enable Hover Properties':
            hover = "closest"
    except:
        void = 1

    # Read layer properties
    models_visible = assume_membership = True
    if "BANYAN Models" not in style:
        models_visible = False
    if "assmem" not in style:
        assume_membership = False

    if assume_membership:
        xvar += "_assmem"
        yvar += "_assmem"
        zvar += "_assmem"

    layout = go.Layout(
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        dragmode="lasso",
        xaxis={'title':xtitle},
        yaxis={'title':ytitle},
        showlegend=True,
        hovermode=hover,
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            orientation="h",
            yanchor="top",
        ),
    )
    
    colormap = colormap_picker(associations)

    data = []
    if selected_data is None:
        totsel = 0
    else:
        totsel = len(selected_data)

    text_list = build_hover(dff)
    aid_list = dff["moca_aid"].tolist()
    text_list = [aid_list[i] + "<br>" + text_list[i] for i in range(len(text_list))]
    dff['text_list'] = text_list

    for association in associations:

        dff_aid = dff[dff["moca_aid"] == association]
        if selected_data is None:
            selected_index = None
        else:
            selected_index = np.where(dff_aid['moca_oid'].isin(selected_data))[0]
        
        if totsel==0:
            dff_deselect = None
            dff_select = dff_aid
        else:
            df_select_index = dff_aid.index.isin(dff_aid.iloc[selected_index].index)
            dff_deselect = dff_aid[~df_select_index]
            dff_select = dff_aid[df_select_index]

        # Plot the *DE*selected data points
        if dff_deselect is not None:
            dff_plot = dff_deselect
            new_trace = go.Scatter3d(
                x=dff_plot[xvar],#This is the x in the MOCA column
                y=dff_plot[yvar],#This is the y in the MOCA column
                z=dff_plot[zvar],#This is the y in the MOCA column
                opacity=unselected_opacity,
                mode="markers",
                showlegend=False,
                marker={"color": colormap[association], "size": 3},
                text=dff_plot["text_list"],
                name=association,
                customdata=dff_plot["moca_oid"],
            )
            data.append(new_trace)

        # Plot the selected data points
        if dff_select is not None:
            dff_plot = dff_select
            new_trace = go.Scatter3d(
                x=dff_plot[xvar],#This is the x in the MOCA column
                y=dff_plot[yvar],#This is the y in the MOCA column
                z=dff_plot[zvar],#This is the y in the MOCA column
                opacity=0.8,
                mode="markers",
                marker={"color": colormap[association], "size": 3},
                text=dff_plot["text_list"],
                name=association,
                customdata=dff_plot["moca_oid"],
            )
            data.append(new_trace)

        # Plot the appropriate BANYAN models
        if models_visible:
            dfm_aid = dfm[dfm["moca_aid"] == association]

            for index, dfm_row in dfm_aid.iterrows():

                # Rebuild covariance matrix and offset from the models dataframe
                offset = np.array([dfm_row[xvar+'_cen'],dfm_row[yvar+'_cen'],dfm_row[zvar+'_cen']])
                covar_matrix = np.array([
                    [dfm_row[xvar+xvar+'_covar'],dfm_row[xvar+yvar+'_covar'],dfm_row[xvar+zvar+'_covar']],
                    [dfm_row[xvar+yvar+'_covar'],dfm_row[yvar+yvar+'_covar'],dfm_row[yvar+zvar+'_covar']],
                    [dfm_row[xvar+zvar+'_covar'],dfm_row[yvar+zvar+'_covar'],dfm_row[zvar+zvar+'_covar']]
                    ])

                ellipses = build_ellipsoid_3d(offset, covar_matrix, colormap[association])

                for elli in ellipses:
                    data.append(elli)
            
    new_trace = go.Scatter3d(
            x=[0],
            y=[0],
            z=[0],
            opacity=0.8,
            mode="markers",
            marker_symbol="cross",
            marker={"color": "#000000", "size": 5},#, "symbol":"circle-dot"
            text="Sun",
            name="Sun",
        )
    data.append(new_trace)

    fig = go.Figure(data=data,layout=layout)
    fig.update_scenes(xaxis={'title':xtitle},yaxis={'title':ytitle},zaxis={'title':ztitle})
    
    fig.add_annotation(
        x=0,
        y=1,
        xref="x domain",
        yref="y domain",
        text="MOCAdb",
        showarrow=False,
        align="left",
        valign="top",
        opacity=0.8,
        font=dict(
            family="Courier New, monospace",
            size=16,
            color="rgb(192,198,206)",
            ),
        )

    #Default axis range
    if (xvar=='x' or xvar=='y' or xvar=='z'):
        fig.update_scenes(xaxis={'range':[-150,150]})
    if (yvar=='x' or yvar=='y' or yvar=='z'):
        fig.update_scenes(yaxis={'range':[-150,150]})
    if (zvar=='x' or zvar=='y' or zvar=='z'):
        fig.update_scenes(zaxis={'range':[-150,150]})
    if xvar=='u':
        fig.update_scenes(xaxis={'range':[-80,70]})
    if yvar=='u':
        fig.update_scenes(yaxis={'range':[-80,70]})
    if zvar=='u':
        fig.update_scenes(zaxis={'range':[-80,70]})
    if xvar=='v':
        fig.update_scenes(xaxis={'range':[-70,20]})
    if yvar=='v':
        fig.update_scenes(yaxis={'range':[-70,20]})
    if zvar=='v':
        fig.update_scenes(zaxis={'range':[-70,20]})
    if xvar=='w':
        fig.update_scenes(xaxis={'range':[-70,20]})
    if yvar=='w':
        fig.update_scenes(yaxis={'range':[-70,20]})
    if zvar=='w':
        fig.update_scenes(zaxis={'range':[-70,20]})

    return fig

def generate_prot_color(dff, associations, selected_data, prot_layer_select, hover_select):

    #Read hover property
    hover = False
    try:
        if hover_select[0] == 'Enable Hover Properties':
            hover = "closest"
    except:
        void = 1

    #Read layer properties
    sequences_visible = ylog = br = True
    if "ylog" not in prot_layer_select:
        ylog = False
    if "br" not in prot_layer_select:
        br = False
    if "Sequences" not in prot_layer_select:
        sequences_visible = False

    #Only show preliminary sequences in B-R
    if not br:
        sequences_visible = False

    if br:
        xaxis_title = 'Gaia DR3 G_BP - G_RP color (mag)'
    else:
        xaxis_title = 'Gaia DR3 G - G_RP color (mag)'

    layout = go.Layout(
        clickmode="event+select",
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        dragmode="lasso",
        xaxis={'title':xaxis_title},
        yaxis={'title':'Rotation period (days)'},
        showlegend=True,
        #autosize=True,
        hovermode=hover,
        margin=dict(l=110, r=50, t=50, b=50),
        legend=dict(
            orientation="h",
            x=0,
            y=-0.2,
            yanchor="top",
        ),
    )
    if br:
        hovertemplate = "%{text}<br><br>G_BP - G_RP : %{x:.2f}<br>M_G : %{y:.2f}<extra></extra>"
    else:    
        hovertemplate = "%{text}<br><br>G - G_RP : %{x:.2f}<br>M_G : %{y:.2f}<extra></extra>"
    
    data = []
    colormap = colormap_picker(associations)

    text_list = build_hover(dff)
    aid_list = dff["moca_aid"].tolist()
    text_list = [aid_list[i] + "<br>" + text_list[i] for i in range(len(text_list))]
    dff['text_list'] = text_list

    for association in associations:

        dff_aid = dff[dff["moca_aid"] == association]
        if selected_data is None:
            selected_index = None
        else:
            selected_index = np.where(dff_aid['moca_oid'].isin(selected_data))[0]

        if br:
            xdata = dff_aid["br"]
        else:
            xdata = dff_aid["gr"]

        new_trace = go.Scattergl(
            x=xdata,#This is the x in the MOCA column
            y=dff_aid["prot_days"],#This is the y in the MOCA column
            opacity=0.8,
            mode="markers",
            hovertemplate=hovertemplate,
            marker={"color": colormap[association], "size": 5},
            text=dff_aid['text_list'],
            name=association,
            selectedpoints=selected_index,
            customdata=dff_aid["moca_oid"],
        )
        
        new_trace.update(unselected=dict(marker=dict(opacity=unselected_opacity)))
        data.append(new_trace)

    #Show preliminary sequences
    seqwid = 1
    seqcol = '#0066FF'
    new_trace = go.Scattergl(
            x=df_prot_seq_ple["br"],
            y=df_prot_seq_ple["prot"],
            customdata=df_prot_seq_ple['customdata'],
            opacity=0.9,
            mode="lines",
            line=dict(color=seqcol, width=seqwid, dash='dot'),
            hoverinfo='skip',
            name='Pleiades (100 Myr)',
            visible=sequences_visible,
        )
    data.append(new_trace)

    new_trace = go.Scattergl(
            x=df_prot_seq_prae["br"],
            y=df_prot_seq_prae["prot"],
            customdata=df_prot_seq_prae['customdata'],
            opacity=0.9,
            mode="lines",
            line=dict(color=seqcol, width=seqwid, dash='dash'),
            hoverinfo='skip',
            name='Praesepe (600 Myr)',
            visible=sequences_visible,
        )
    data.append(new_trace)

    new_trace = go.Scattergl(
            x=df_prot_seq_ngc6811["br"],
            y=df_prot_seq_ngc6811["prot"],
            customdata=df_prot_seq_ngc6811['customdata'],
            opacity=0.9,
            mode="lines",
            line=dict(color=seqcol, width=seqwid),#, dash='dot'
            hoverinfo='skip',
            name='NGC 6811 (1 Gyr)',
            visible=sequences_visible,
        )
    data.append(new_trace)

    fig = go.Figure(data=data,layout=layout)

    #Default axis range
    if br:
        fig.update_layout(xaxis_range=[0.2,3.2])
    else:
        fig.update_layout(xaxis_range=[0.2,1.5])
    
    yrange = [0.1,25]
    if ylog:
        fig.update_layout(yaxis_range=[np.log10(yrange[0]),np.log10(yrange[1])])
        fig.update_layout(yaxis_type = "log")
    else:
        fig.update_layout(yaxis_range=[yrange[0],yrange[1]])

    fig.add_annotation(
        x=0,
        y=1,
        xref="x domain",
        yref="y domain",
        text="MOCAdb",
        showarrow=False,
        align="left",
        valign="top",
        opacity=0.8,
        font=dict(
            family="Courier New, monospace",
            size=16,
            color="rgb(192,198,206)",
            ),
        )

    return fig

def generate_gaia_act_color(dff, associations, selected_data, act_layer_select, hover_select):

    #Read hover property
    hover = False
    try:
        if hover_select[0] == 'Enable Hover Properties':
            hover = "closest"
    except:
        void = 1

    #Read layer properties
    sequences_visible = ylog = br = True
    if "ylog" not in act_layer_select:
        ylog = False
    if "br" not in act_layer_select:
        br = False
    if "Sequences" not in act_layer_select:
        sequences_visible = False

    if br:
        xaxis_title = 'Gaia DR3 G_BP - G_RP color (mag)'
    else:
        xaxis_title = 'Gaia DR3 G - G_RP color (mag)'

    layout = go.Layout(
        clickmode="event+select",
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        dragmode="lasso",
        xaxis={'title':xaxis_title},
        yaxis={'title':'Gaia DR3 activity index'},
        showlegend=True,
        #autosize=True,
        hovermode=hover,
        margin=dict(l=110, r=50, t=50, b=50),
        legend=dict(
            orientation="h",
            x=0,
            y=-0.2,
            yanchor="top",
        ),
    )
    if br:
        hovertemplate = "%{text}<br><br>G_BP - G_RP : %{x:.2f}<br>M_G : %{y:.2f}<extra></extra>"
    else:    
        hovertemplate = "%{text}<br><br>G - G_RP : %{x:.2f}<br>M_G : %{y:.2f}<extra></extra>"
    data = []
    colormap = colormap_picker(associations)

    text_list = build_hover(dff)
    aid_list = dff["moca_aid"].tolist()
    text_list = [aid_list[i] + "<br>" + text_list[i] for i in range(len(text_list))]
    dff['text_list'] = text_list

    for association in associations:

        dff_aid = dff[dff["moca_aid"] == association]
        if selected_data is None:
            selected_index = None
        else:
            selected_index = np.where(dff_aid['moca_oid'].isin(selected_data))[0]

        if br:
            xdata = dff_aid["br"]
        else:
            xdata = dff_aid["gr"]

        new_trace = go.Scattergl(
            x=xdata,#This is the x in the MOCA column
            y=dff_aid["gaia_act"],#This is the y in the MOCA column
            opacity=0.8,
            mode="markers",
            hovertemplate=hovertemplate,
            marker={"color": colormap[association], "size": 5},
            text=dff_aid['text_list'],
            name=association,
            selectedpoints=selected_index,
            customdata=dff_aid["moca_oid"],
        )
        
        new_trace.update(unselected=dict(marker=dict(opacity=unselected_opacity)))
        data.append(new_trace)

    fig = go.Figure(data=data,layout=layout)

    #Default axis range
    if br:
        fig.update_layout(xaxis_range=[0.2,3.2])
    else:
        fig.update_layout(xaxis_range=[0.2,1.5])
    
    yrange = [-0.05,0.2]
    if ylog:
        fig.update_layout(yaxis_range=[np.log10(0.001),np.log10(yrange[1])])
        fig.update_layout(yaxis_type = "log")
    else:
        fig.update_layout(yaxis_range=[yrange[0],yrange[1]])

    fig.add_annotation(
        xref="x domain",
        yref="y domain",
        x=0,
        y=1,
        text="MOCAdb",
        showarrow=False,
        align="left",
        valign="top",
        opacity=0.8,
        font=dict(
            family="Courier New, monospace",
            size=16,
            color="rgb(192,198,206)",
            ),
        )

    return fig

def generate_gaiadr3_cmd(dff, associations, df_cmd_field, selected_data, cmd_layer_select, hover_select):

    #Read layer properties
    sequences_visible = field_visible = br = True
    if "Field Stars" not in cmd_layer_select:
        field_visible = False
    if "Sequences" not in cmd_layer_select:
        sequences_visible = False
    if "br" not in cmd_layer_select:
        br = False

    #Not yet implemented
    if br:
        sequences_visible = False
        field_visible = False

    #Read hover property
    hover = False
    try:
        if hover_select[0] == 'Enable Hover Properties':
            hover = "closest"
    except:
        void = 1

    if br:
        xaxis_title = 'Gaia DR3 G_BP - G_RP color (mag)'
    else:
        xaxis_title = 'Gaia DR3 G - G_RP color (mag)'

    layout = go.Layout(
        clickmode="event+select",
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        dragmode="lasso",
        xaxis={'title':xaxis_title},
        yaxis={'title':'Gaia DR3 absolute G-band magnitude (mag)'},
        showlegend=True,
        hovermode=hover,
        margin=dict(l=110, r=50, t=50, b=50),
        legend=dict(
            orientation="h",
            x=0,
            y=-0.2,
            yanchor="top",
        ),
    )
    hovertemplate = "%{text}<br><br>G - G_RP : %{x:.2f}<br>M_G : %{y:.2f}<extra></extra>"
    data = []
    colormap = colormap_picker(associations)

    if not field_visible:
        field_visible_input = "legendonly"
    else:
        field_visible_input = True

    if not sequences_visible:
        sequences_visible_input = "legendonly"
    else:
        sequences_visible_input = True

    #if field_visible:
    hexcolor = "#000000"
    rgbcolor = np.array([int(hexcolor.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)])
    diff = bcg_color-rgbcolor
    rgbcolor_pale = (rgbcolor+diff*(1.0-field_color_fraction)).astype(int)
    rgbcolor = [str(int(i)) for i in rgbcolor_pale]
    rgbcolorf = "rgb("+",".join(rgbcolor)+")"
    new_trace = go.Scattergl(
            x=df_cmd_field["gr"],
            y=df_cmd_field["m_g"],
            #opacity=field_opacity,
            mode="markers",
            marker={"color": rgbcolorf, "size": field_markersize, "opacity": field_opacity},
            hoverinfo='skip',
            name='Field stars',
            showlegend=False,
            customdata=df_cmd_field['customdata'],
            visible=field_visible_input,
        )
    new_trace.update(unselected=dict(marker=dict(color=rgbcolorf,opacity=field_opacity)),selected=dict(marker=dict(color=rgbcolorf,opacity=field_opacity)))
    data.append(new_trace)

    text_list = build_hover(dff)
    aid_list = dff["moca_aid"].tolist()
    text_list = [aid_list[i] + "<br>" + text_list[i] for i in range(len(text_list))]
    dff['text_list'] = text_list

    for association in associations:

        dff_aid = dff[dff["moca_aid"] == association]
        if selected_data is None:
            selected_index = None
        else:
            selected_index = np.where(dff_aid['moca_oid'].isin(selected_data))[0]

        if br:
            xdata = dff_aid["br"]
        else:
            xdata = dff_aid["gr"]
        
        new_trace = go.Scattergl(
            x=xdata,#This is the x in the MOCA column
            y=dff_aid["m_g"],#This is the y in the MOCA column
            opacity=0.8,
            mode="markers",
            hovertemplate=hovertemplate,
            marker={"color": colormap[association], "size": 5},
            text=dff_aid['text_list'],
            name=association,
            selectedpoints=selected_index,
            customdata=dff_aid["moca_oid"],
        )
        
        new_trace.update(unselected=dict(marker=dict(opacity=unselected_opacity)))
        data.append(new_trace)

    #Add empirical isochrones
    seqwid = 1
    seqcol = '#0066FF'
    
    new_trace = go.Scattergl(
            x=df_cmd_seq_100["gr"],
            y=df_cmd_seq_100["m_g"],
            opacity=0.9,
            mode="lines",
            line=dict(color=seqcol, width=seqwid),
            hoverinfo='skip',
            name='100 Myr',
            #showlegend=False,
            customdata=df_cmd_seq_100['customdata'],
            visible=sequences_visible_input,
        )
    data.append(new_trace)

    new_trace = go.Scattergl(
            x=df_cmd_seq_40["gr"],
            y=df_cmd_seq_40["m_g"],
            opacity=0.9,
            mode="lines",
            line=dict(color=seqcol, width=seqwid, dash="dash"),
            hoverinfo='skip',
            name='40 Myr',
            #showlegend=False,
            customdata=df_cmd_seq_40['customdata'],
            visible=sequences_visible_input,
        )
    data.append(new_trace)

    new_trace = go.Scattergl(
            x=df_cmd_seq_25["gr"],
            y=df_cmd_seq_25["m_g"],
            opacity=0.9,
            mode="lines",
            line=dict(color=seqcol, width=seqwid, dash="dot"),
            hoverinfo='skip',
            name='22 Myr',
            #showlegend=False,
            customdata=df_cmd_seq_25['customdata'],
            visible=sequences_visible_input,
        )
    data.append(new_trace)

    fig = go.Figure(data=data,layout=layout)

    #Default axis range
    fig.update_layout(yaxis_range=[20,-2])
    if br:
        fig.update_layout(xaxis_range=[-0.5,3.5])
    else:
        fig.update_layout(xaxis_range=[-0.5,2.5])

    fig.add_annotation(
        x = 1,
        y = 1,
        xref="x domain",
        yref="y domain",
        text="MOCAdb",
        showarrow=False,
        align="right",
        valign="top",
        opacity=0.8,
        font=dict(
            family="Courier New, monospace",
            size=16,
            color="rgb(192,198,206)",
            ),
        )

    return fig

layout = html.Div(
    children=[
        html.Div(
            id="top-row",
            children=[
                html.Div(
                    className="row",
                    id="top-row-header",
                    children=[
                        html.Div(
                            id="header-container",
                            children=[
                                build_banner(),
                                html.P(
                                    #Also explain here individual plots only appear when 1 star is selected
                                    id="instructions",
                                    children=["Select data points from any plot to "
                                    "visualize cross-filtering to other plots. Selection can be done by "
                                    "clicking on individual data points or using the Plotly lasso or box tools to capture "
                                    "multiple data points. Hovering on top of a data point will display basic information on the star in question if the Hover option below is enabled.",
                                    html.Br(),html.Br(),
                                    " With the box tool from modebar, multiple "
                                    "regions can be selected by holding the SHIFT key while clicking and "
                                    "dragging."
                                    ,html.Br(),
                                    " The Plotly lasso tool can be used to select multiple data points in a custom shape."
                                    ,html.Br(),
                                    " Note that the MOCA database is queried every time the list of associations are changed. The color scheme is also slightly updated to maximize color distances, with up to 20 colors."
                                    ,html.Br(),
                                    " The plotting order follows the order in which the young associations are listed in the Dropdown panel."
                                    ,html.Br(),
                                    "Holding the SHIFT key while clicking on an association name "
                                    "will open the MOCA report for that association in a new tab. "
                                    ,html.Br(),
                                    "Clicking on a Plotly legend item will turn on or off the display of one association only in the specific panel where it was clicked. Double-clicking a legend item will only display the association in question."
                                    ,html.Br(),
                                    "The 3D scatter plots are more easily controlled in Turntable Rotation mode, by using two fingers swiped up or down for zooming, two-fingers clicking for drag, or simple clicking for rotations."
                                    ,html.Br(),html.Br(),
                                    "Known issues:",html.Br(),
                                    " - In Safari, 3D scatter plots often keep an imprint of the original view point.",html.Br(),
                                    " - Plotly does not yet allow to perform selections in 3D scatter plots.",html.Br(),
                                    " - Some panels will sometimes fail to refresh a cross-filtering, especially with rapid selections in new panels. When this happens, simply re-select the desired data points.",html.Br(),
                                    ]
                                    , style={"width": "100%"},
                                ),
                                build_graph_title("Select Stellar Associations"),
                                dcc.Markdown(
                                #html.P(
                                    id="aid-instructions",
                                    children=[
                                        "Select the associations to be included in the visualizations below. More information on the short association names can be found [here](https://mocadb.ca/associations).",
                                    ]
                                    , style={"width": "100%", "color":"white", "whiteSpace": "pre-wrap"},
                                ),
                                dcc.Dropdown(
                                    id="aid-select",
                                    options=[
                                        {"label": dcc.Link(children=i ,href="https://mocadb.ca/search/results?search-query="+i+"&search-type=association"), "value": i}
                                        #{"label": i, "value": i}
                                        for i in df_aids["moca_aid"].unique().tolist()
                                    ],
                                    multi=True,
                                    value=initial_aids
                                ),
                                html.Br(),
                                build_graph_title("Select Membership Types"),
                                dcc.Markdown(
                                    id="mtid-instructions",
                                    children=["Select the data included in the visualizations below, among the following types of membership:  \n"]+text_mtids
                                    , style={"width": "100%", "color":"white", "whiteSpace": "pre-wrap"},
                                ),
                                dcc.Dropdown(
                                    id="mtid-select",
                                    options=[
                                        {"label": " "+i, "value": i}
                                        for i in df_mtids["moca_mtid"].unique().tolist()
                                    ],
                                    multi=True,
                                    value=initial_mtids
                                ),
                                html.Br(),
                                build_graph_title("Select Options"),
                                dcc.Checklist(
                                    id="hover-select",
                                    options=[
                                        {
                                            "label": " Enable Hover Properties",
                                            "value": "Enable Hover Properties",
                                        },
                                    ],
                                    value=[],
                                    labelStyle={'color': 'white'}
                                ),
                            ],
                        ),
                        dcc.Store(id='db-data'),
                    ],
                ),
            ],
        ),
        html.Div(
            className="row",
            id="first-data-row",
            children=[
                #CMD
                html.Div(
                    id="cmd-container",
                    className="four columns",
                    children=[
                        html.Br(),
                        build_graph_title("Gaia DR3 Color-Magnitude Diagram"),
                        dcc.Checklist(
                                    id="cmd-layer-select",
                                    options=[
                                        {
                                            "label": " Field Stars",
                                            "value": "Field Stars",
                                        },
                                        {
                                            "label": " Empirical Sequences",
                                            "value": "Sequences",
                                        },
                                        {
                                            "label": " G_BP - G_RP X axis",
                                            "value": "br",
                                        },
                                    ],
                                    value=["Sequences", "Field Stars"],
                                    labelStyle={'presentation': 'markdown'},
                                ),
                        html.Br(),
                        dcc.Graph(id="gaiadr3-cmd",config=figure_export_config),
                    ],
                ),
                # XYZ
                html.Div(
                    id="xyz-container",
                    className="four columns",
                    children=[
                        html.Br(),
                        build_graph_title("Galactic X, Y, Z coordinates"),
                        dcc.Checklist(
                                    id="xymap-view-selector",
                                    options=[
                                        # {
                                        #     "label": "Association Centers",
                                        #     "value": "Association Centers",
                                        # },
                                        {
                                            "label": "BANYAN Models",
                                            "value": "BANYAN Models",
                                        },
                                        {
                                            "label": "Assume Membership",
                                            "value": "assmem",
                                        },
                                    ],
                                    value=["BANYAN Models"],
                                ),
                        html.Br(),
                        dcc.Graph(id="xyz-map",config=figure_export_config),
                    ],
                ),
                # UVW
                html.Div(
                    id="uvw-container",
                    className="four columns",
                    children=[
                        html.Br(),
                        build_graph_title("Galactic U, V, W space velocities"),
                        html.Br(),html.Br(),html.Br(),
                        dcc.Graph(id="uvw-map",config=figure_export_config),
                    ],
                ),
            ],
        ),
        html.Div(
            className="row",
            id="second-data-row",
            children=[
                # XY
                html.Div(
                    id="xy-container",
                    className="three columns",
                    children=[
                        build_graph_title("Galactic X, Y coordinates"),
                        dcc.Graph(id="xy-map",config=figure_export_config),
                    ],
                ),
                # YZ
                html.Div(
                    id="yz-container",
                    className="three columns",
                    children=[
                        build_graph_title("Galactic Y, Z coordinates"),
                        dcc.Graph(id="yz-map",config=figure_export_config),
                    ],
                ),
                # UV
                html.Div(
                    id="uv-container",
                    className="three columns",
                    children=[
                        build_graph_title("Galactic U, V space velocities"),
                        dcc.Graph(id="uv-map",config=figure_export_config),
                    ],
                ),
                # UW
                html.Div(
                    id="uw-container",
                    className="three columns",
                    children=[
                        build_graph_title("Galactic U, W space velocities"),
                        dcc.Graph(id="uw-map",config=figure_export_config),
                    ],
                ),
            ],
        ),
        html.Div(
            className="row",
            id="third-data-row",
            children=[
                # PROT
                html.Div(
                    id="prot-container",
                    className="four columns",
                    children=[
                        build_graph_title("Rotation periods"),
                        dcc.Checklist(
                                    id="prot-layer-select",
                                    options=[
                                        {
                                            "label": " Empirical Sequences",
                                            "value": "Sequences",
                                        },
                                        {
                                            "label": " Logarithmic Y axis",
                                            "value": "ylog",
                                        },
                                        {
                                            "label": " G_BP - G_RP X axis",
                                            "value": "br",
                                        },
                                    ],
                                    value=["Sequences","br"],
                                ),
                        html.Br(),
                        dcc.Graph(id="prot-color",config=figure_export_config),
                    ],
                ),
                # PROT
                html.Div(
                    id="gaia-act-container",
                    className="four columns",
                    children=[
                        #html.Br(),
                        build_graph_title("Gaia DR3 activity index"),
                        dcc.Checklist(
                                    id="gaia-act-layer-select",
                                    options=[
                                        # {
                                        #     "label": " Empirical Sequences",
                                        #     "value": "Empirical Sequences",
                                        # },
                                        {
                                            "label": " Logarithmic Y axis",
                                            "value": "ylog",
                                        },
                                        {
                                            "label": " G_BP - G_RP X axis",
                                            "value": "br",
                                        },
                                    ],
                                    value=[],
                                ),
                        html.Br(),
                        dcc.Graph(id="gaia-act-color",config=figure_export_config),
                    ],
                ),
            ],
        ),
        # html.Div(
        #     className="row",
        #     id="singleobj-data-row-1",
        #     children=[
        #         # RV time series
        #         html.Div(
        #             id="rvts-container",
        #             className="four columns",
        #             children=[
        #                 #html.Br(),
        #                 build_graph_title("Radial velocities"),
        #                 dcc.Graph(id="rvts-fig",config=figure_export_config),
        #             ],
        #         ),
        #     ],
        # ),
        # html.Div(
        #     className="row",
        #     id="singleobj-data-row-2",
        #     children=[
        #         # Spectrum
        #         html.Div(
        #             id="spectrum-container",
        #             className="four columns",
        #             children=[
        #                 #html.Br(),
        #                 build_graph_title("Spectrum"),
        #                 dcc.Graph(id="spectrum-fig",config=figure_export_config),
        #             ],
        #         ),
        #     ],
        # ),
        html.Div(
            className="row",
            id="table-row",
            children=[
                #Table
                html.Div(
                    id="table-container",
                    className="twelve columns",
                    children=[
                        html.Br(),
                        build_graph_title("MOCA summary table"),
                        html.P("Rows are shown in order of selection, association and membership type. Selected rows are highlighted in green."),
                        dash_table.DataTable(
                            id="df-table",
                            columns=[{'id': x, 'name': x, 'presentation': 'markdown'} for x in dfe.columns],
                            export_format='csv',
                            style_header={
                                'fontSize': 15,
                                'fontWeight': 'bold',
                                'textAlign': 'center',
                            },
                            selected_rows=[],
                            style_data_conditional=get_style_data_conditional(),
                        ),
                    ],
                ),
            ],
        ),
    ]
)

selections = {
            "uv-map":Input("uv-map", "selectedData"),
            "uw-map":Input("uw-map", "selectedData"),
            "xy-map":Input("xy-map", "selectedData"),
            "yz-map":Input("yz-map", "selectedData"),
            "gaiadr3-cmd":Input("gaiadr3-cmd", "selectedData"),
            "prot-color":Input("prot-color", "selectedData"),
            "gaia-act-color":Input("gaia-act-color", "selectedData"),
        }

# Update table
@dash.callback(
    output=[
        Output("df-table","data"),
        Output("df-table","selected_rows"),
        Output("df-table","style_data_conditional"),
    ],
    inputs=dict(
        selections=selections,
        jsonified_db_data=Input("db-data", "data"),
        xymap_view=Input("xymap-view-selector", "value"),
    ),
    state=dict(aid_select=State("aid-select", "value"), self_data=State("df-table", "data"), self_selrows=State("df-table", "selected_rows"), self_style=State("df-table", "style_data_conditional")),
)
def update_table(
    selections, jsonified_db_data, xymap_view, aid_select, self_data, self_selrows, self_style
):
    
    print("TABLE callback")
    processed_data, prop_id = selection_helper(selections)
    
    if prop_id is None:
        #selected_index = []
        return self_data, self_selrows, self_style

    # Read data from session memory
    df = pd.read_json(jsonified_db_data[0], orient='split')
    
    #If no group is loaded then return empty dataframe
    if len(df) == 0:
        selected_index = []
        return dfe.to_dict('records'), selected_index, get_style_data_conditional(selected_index)

    #Add clickable links
    df['designation'] = '['+df['designation'].values+'](https://mocadb.ca/search/results?search-query='+np_f.replace(np_f.replace(df['designation'].values.astype("U")," ","%20"),"+","%2B")+'&search-type=star)'
    df['moca_aid'] = '['+df['moca_aid'].values+'](https://mocadb.ca/search/results?search-query='+np_f.replace(df['moca_aid'].values.astype("U")," ","%20")+'&search-type=association)'

    df_sorted = df
    df_sorted['num_moca_mtid'] = df_sorted['moca_mtid']
    
    #This could probably be done better with the moca_membership_types table
    df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"BF","1.BF")
    df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"HM","2.HM")
    df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"CM","3.CM")
    df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"LM","4.LM")
    df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"AM","5.AM")
    df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"R","6.R")
    df_sorted = df_sorted.sort_values(by=['moca_aid', 'num_moca_mtid', 'spt'])

    if processed_data is None:
        selected_index = []
        df_out = df_sorted
    else:
        df_selected_indices = df_sorted['moca_oid'].isin(processed_data)
        selected_index = np.where(df_selected_indices)[0]
        df_out = pd.concat([df_sorted[df_selected_indices],df_sorted[~df_selected_indices]])
        #If we sort the table the selected indices are the first ones
        selected_index = list(range(len(selected_index)))

    table_data_style_conditional = get_style_data_conditional(selected_index)

    return df_out.to_dict('records'), selected_index, table_data_style_conditional

# Update AID- and MTID-select
@dash.callback(
    output=Output("db-data","data"),
    inputs=[
        Input("aid-select", "value"),
        Input("mtid-select", "value"),
    ],
)
def update_aid_select(
    aid_select, mtid_select
):
    
    print("DBQUERY callback")
    
    #Prevent app from crashing if no associations are selected
    if len(aid_select) == 0:
        df = dfe
        dfm = dfme
    else: 
        # Query the moca database to obtain a Pandas DataFrame for the specific group needed
        aid_query = " OR ".join(["moca_aid='"+stri+"'" for stri in aid_select])
        mtid_query = " OR ".join(["moca_mtid = '"+stri+"'" for stri in mtid_select])
        df = moca.query("SELECT "+", ".join(df_columns)+" FROM summary_all_members WHERE ("+mtid_query+") AND ("+aid_query+")")
        df['gr'] = df['gmag']-df['rmag']
        df['br'] = df['bmag']-df['rmag']
        df['m_g'] = df['gmag']-5.0*(np.log10(1000.0/df['plx'])-1)
        df['m_r'] = df['rmag']-5.0*(np.log10(1000.0/df['plx'])-1)

        # Query the moca database to obtain a Pandas DataFrame of the appropriate BANYAN Sigma models
        dfm = moca.query("SELECT dbs.* FROM moca_banyan_sigma_models mbs LEFT JOIN data_banyan_sigma_models dbs USING(moca_bsmdid) WHERE mbs.adopted=1 AND ("+aid_query+")")

    print("Downloaded "+str(len(df))+" rows of general data from DB")

    return df.to_json(date_format='iso', orient='split'), dfm.to_json(date_format='iso', orient='split')

# # Update RVTS figure
# @dash.callback(
#     output=Output("rvts-fig", "figure"),
#     inputs=dict(
#         selections=selections,
#     ),
#     state=dict(self_figure=State("rvts-fig", "figure")),
# )
# def update_spectrum_fig(
#     selections, self_figure
# ):
    
#     print("RVTS callback")
#     processed_data, prop_id = selection_helper(selections)
    

#     if prop_id == "rvts-fig":
#         print("RETURNS SELF1")
#         return self_figure
    
#     if prop_id is None:
#        print("RETURNS SELF2")
#        return self_figure

#     if processed_data is None:
#         print("RETURNS SELF3")
#         return self_figure
    
#     if len(processed_data) != 1:
#         print("RETURNS NONE1")
#         return None

#     #Query the database
#     dfrvts = moca.query("SELECT radial_velocity_kms rv, radial_velocity_kms_unc erv, epoch yr, moca_instid, n_measurements, mission_name, data_release, mp.bibcode FROM data_radial_velocities dd LEFT JOIN moca_publications mp USING(moca_pid) WHERE adopted=1 AND moca_oid="+str(selections[prop_id]['points'][0]['customdata']))

#     if dfrvts is None:
#         print("RETURNS NONE2")
#         return None
    
#     if len(dfrvts) == 0:
#         print("RETURNS NONE3")
#         return None

#     return generate_rvts(dfrvts)

# # Update spectrum figure
# @dash.callback(
#     output=Output("spectrum-fig", "figure"),
#     inputs=dict(
#         selections=selections,
#     ),
#     state=dict(self_figure=State("spectrum-fig", "figure")),
# )
# def update_spectrum_fig(
#     selections, self_figure
# ):
    
#     print("Spectrum callback")
#     processed_data, prop_id = selection_helper(selections)
    
#     if prop_id == "spectrum-fig":
#         return self_figure
#     if prop_id is None:
#        return self_figure

#     if processed_data is None:
#         return None
    
#     if len(processed_data) != 1:
#         return None

#     #Query the database
#     dfspe = moca.query("SELECT wavelength_angstrom wv, flux_flambda ff FROM moca_spectra ms LEFT JOIN data_spectra ds USING(moca_specid) WHERE ms.moca_oid="+str(selections[prop_id]['points'][0]['customdata']))

#     if dfspe is None:
#         return None
    
#     if len(dfspe) == 0:
#         return None

#     return generate_spectrum(dfspe)

# Update prot-color
@dash.callback(
    output=Output("prot-color", "figure"),
    inputs=dict(
        selections=selections,
        jsonified_db_data=Input("db-data", "data"),
        prot_layer_select=Input("prot-layer-select", "value"),
        hover_select=Input("hover-select", "value"),
    ),
    state=dict(aid_select=State("aid-select", "value"), self_figure=State("prot-color", "figure")),
)
def update_prot_color(
    selections, jsonified_db_data, prot_layer_select, hover_select, aid_select, self_figure
):
    
    print("PROT callback")
    processed_data, prop_id = selection_helper(selections)
    if prop_id == "prot-color":
        return self_figure
    if prop_id is None:
       return self_figure
    df = pd.read_json(jsonified_db_data[0], orient='split')
    return generate_prot_color(df, aid_select, processed_data, prot_layer_select, hover_select)

# Update gaia-act-color
@dash.callback(
    output=Output("gaia-act-color", "figure"),
    inputs=dict(
        selections=selections,
        jsonified_db_data=Input("db-data", "data"),
        gaia_act_layer_select=Input("gaia-act-layer-select", "value"),
        hover_select=Input("hover-select", "value"),
    ),
    state=dict(aid_select=State("aid-select", "value"), self_figure=State("gaia-act-color", "figure")),
)
def update_gaia_act_color(
    selections, jsonified_db_data, gaia_act_layer_select, hover_select, aid_select, self_figure
):
    
    print("PROT callback")
    processed_data, prop_id = selection_helper(selections)
    if prop_id is None:
       return self_figure
    if prop_id == "gaia-act-color":
        return self_figure
    df = pd.read_json(jsonified_db_data[0], orient='split')
    return generate_gaia_act_color(df, aid_select, processed_data, gaia_act_layer_select, hover_select)

# Update XYZ Map
@dash.callback(
    output=Output("xyz-map", "figure"),
    inputs=dict(
        selections=selections,
        jsonified_db_data=Input("db-data", "data"),
        xymap_view=Input("xymap-view-selector", "value"),
        hover_select=Input("hover-select", "value"),
    ),
    state=dict(aid_select=State("aid-select", "value"), self_figure=State("xyz-map", "figure")),
)
def update_xyz_map(
    selections, jsonified_db_data, xymap_view, hover_select, aid_select, self_figure
):
    
    print("XYZ callback")
    processed_data, prop_id = selection_helper(selections)
    if prop_id is None:
       return self_figure
    if prop_id == "xyz-map":
        return self_figure
    
    df = pd.read_json(jsonified_db_data[0], orient='split')
    dfm = pd.read_json(jsonified_db_data[1], orient='split')
    return generate_xyz_map(df, dfm, aid_select, 'x', 'y', 'z', 'X (pc)', 'Y (pc)', 'Z (pc)', 'XYZ Galactic coordinates', processed_data, xymap_view, hover_select)

# Update UVW Map
@dash.callback(
    output=Output("uvw-map", "figure"),
    inputs=dict(
        selections=selections,
        jsonified_db_data=Input("db-data", "data"),
        xymap_view=Input("xymap-view-selector", "value"),
        hover_select=Input("hover-select", "value"),
    ),
    state=dict(aid_select=State("aid-select", "value"), self_figure=State("uvw-map", "figure")),
)
def update_uvw_map(
    selections, jsonified_db_data, xymap_view, hover_select, aid_select, self_figure
):
    
    print("UVW callback")
    processed_data, prop_id = selection_helper(selections)
    if prop_id is None:
       return self_figure
    if prop_id == "uvw-map":
        return self_figure
    df = pd.read_json(jsonified_db_data[0], orient='split')
    dfm = pd.read_json(jsonified_db_data[1], orient='split')
    return generate_xyz_map(df, dfm, aid_select, 'u', 'v', 'w', 'U (km/s)', 'V (km/s)', 'W (km/s)', 'UVW Galactic space velocities', processed_data, xymap_view, hover_select)

# Update UV Map
@dash.callback(
    output=Output("uv-map", "figure"),
    inputs=dict(
        selections={
            #"uv-map":Input("uv-map", "selectedData"),
            "uw-map":Input("uw-map", "selectedData"),
            "xy-map":Input("xy-map", "selectedData"),
            "yz-map":Input("yz-map", "selectedData"),
            "gaiadr3-cmd":Input("gaiadr3-cmd", "selectedData"),
            "prot-color":Input("prot-color", "selectedData"),
            "gaia-act-color":Input("prot-color", "selectedData"),
        },
        jsonified_db_data=Input("db-data", "data"),
        xymap_view=Input("xymap-view-selector", "value"),
        hover_select=Input("hover-select", "value"),
    ),
    state=dict(aid_select=State("aid-select", "value"), self_figure=State("uv-map", "figure")),
)
def update_uv_map(
    selections, jsonified_db_data, xymap_view, hover_select, aid_select, self_figure
):
    
    print("UV callback")
    processed_data, prop_id = selection_helper(selections)
    if prop_id is None:
       return self_figure
    df = pd.read_json(jsonified_db_data[0], orient='split')
    dfm = pd.read_json(jsonified_db_data[1], orient='split')
    return generate_xy_map(df, dfm, aid_select, 'u', 'v', 'U (km/s)', 'V (km/s)', 'UV Galactic space velocities', processed_data, xymap_view, hover_select)

# Update UW Map
@dash.callback(
    output=Output("uw-map", "figure"),
    inputs=dict(
        selections=selections,
        jsonified_db_data=Input("db-data", "data"),
        xymap_view=Input("xymap-view-selector", "value"),
        hover_select=Input("hover-select", "value"),
    ),
    state=dict(aid_select=State("aid-select", "value"), self_figure=State("uw-map", "figure")),
)
def update_uw_map(
    selections, jsonified_db_data, xymap_view, hover_select, aid_select, self_figure
):
    
    print("UW callback")
    processed_data, prop_id = selection_helper(selections)
    if prop_id is None:
       return self_figure
    if prop_id == "uw-map":
        return self_figure
    df = pd.read_json(jsonified_db_data[0], orient='split')
    dfm = pd.read_json(jsonified_db_data[1], orient='split')
    return generate_xy_map(df, dfm, aid_select, 'u', 'w', 'U (km/s)', 'W (km/s)', 'UW Galactic space velocities', processed_data, xymap_view, hover_select)

# Update XY Map
@dash.callback(
    output=Output("xy-map", "figure"),
    inputs=dict(
        selections=selections,
        jsonified_db_data=Input("db-data", "data"),
        xymap_view=Input("xymap-view-selector", "value"),
        hover_select=Input("hover-select", "value"),
    ),
    state=dict(aid_select=State("aid-select", "value"), self_figure=State("xy-map", "figure")),
)
def update_xy_map(
    selections, jsonified_db_data, xymap_view, hover_select, aid_select, self_figure
):
    
    print("XY callback")
    processed_data, prop_id = selection_helper(selections)
    if prop_id is None:
       return self_figure
    if prop_id == "xy-map":
        return self_figure
    df = pd.read_json(jsonified_db_data[0], orient='split')
    dfm = pd.read_json(jsonified_db_data[1], orient='split')
    return generate_xy_map(df, dfm, aid_select, 'x', 'y', 'X (pc)', 'Y (pc)', 'XY Galactic coordinates', processed_data, xymap_view, hover_select)

# Update YZ Map
@dash.callback(
    output=Output("yz-map", "figure"),
    inputs=dict(
        selections=selections,
        jsonified_db_data=Input("db-data", "data"),
        xymap_view=Input("xymap-view-selector", "value"),
        hover_select=Input("hover-select", "value"),
    ),
    state=dict(aid_select=State("aid-select", "value"), self_figure=State("yz-map", "figure")),
)
def update_yz_map(
    selections, jsonified_db_data, xymap_view, hover_select, aid_select, self_figure
):
    
    print("YZ callback")
    processed_data, prop_id = selection_helper(selections)
    if prop_id is None:
       return self_figure
    if prop_id == "yz-map":
        return self_figure
    df = pd.read_json(jsonified_db_data[0], orient='split')
    dfm = pd.read_json(jsonified_db_data[1], orient='split')
    return generate_xy_map(df, dfm, aid_select, 'y', 'z', 'Y (pc)', 'Z (pc)', 'YZ Galactic coordinates', processed_data, xymap_view, hover_select)

# Update Gaia DR3 CMD
@dash.callback(
    output=Output("gaiadr3-cmd", "figure"),
    inputs=dict(
        selections=selections,
        jsonified_db_data=Input("db-data", "data"),
        cmd_layer_select=Input("cmd-layer-select", "value"),
        hover_select=Input("hover-select", "value"),
    ),
    state=dict(aid_select=State("aid-select", "value"), self_figure=State("gaiadr3-cmd", "figure")),
)
def update_gaiadr3_cmd(
    selections, jsonified_db_data, cmd_layer_select, hover_select, aid_select, self_figure
):

    print("CMD callback")
    processed_data, prop_id = selection_helper(selections)
    if prop_id is None:
       return self_figure
    if prop_id == "gaiadr3-cmd":
        return self_figure

    df = pd.read_json(jsonified_db_data[0], orient='split')
    return generate_gaiadr3_cmd(df, aid_select, df_cmd_field, processed_data, cmd_layer_select, hover_select)
