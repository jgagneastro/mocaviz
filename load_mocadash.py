import pathlib, os
import colorsys
#import os

import pandas as pd
import numpy as np

import dash
from dash import dcc, html
#from dash import html
import plotly.graph_objs as go
from dash.dependencies import Input, Output, State
import plotly.express as px

from mocapy import *

# app initialize
app = dash.Dash(
    __name__,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1.0"}
    ],
)
server = app.server
#app.config["suppress_callback_exceptions"] = True

initial_aids = ["ABDMG","BPMG","TWA"]
aid_query = " OR ".join(["moca_aid='"+stri+"'" for stri in initial_aids])

# Load data
moca = MocaEngine()

unselected_opacity = 0.06

#Load a list of all associations for the Dropdown menu
df_aids = moca.query("SELECT moca_aid FROM moca_associations")

print("Downloaded "+str(len(df_aids))+" rows of data for associations information")

df_cmd_field = moca.query("SELECT phot_g_mean_mag, phot_rp_mean_mag, parallax FROM data_gaiadr3_cmd_field")
#df_cmd_field = moca.query("SELECT phot_g_mean_mag, phot_rp_mean_mag, parallax FROM data_gaiadr3_cmd_field LIMIT 100")
df_cmd_field['gr'] = df_cmd_field['phot_g_mean_mag']-df_cmd_field['phot_rp_mean_mag']
df_cmd_field['m_g'] = df_cmd_field['phot_g_mean_mag']-5.0*(np.log10(1000.0/df_cmd_field['parallax'])-1)
df_cmd_field['customdata'] = 'NaN'
field_opacity = 0.03
field_color_fraction = 1
field_markersize = 2
bcg_color = np.array([230,236,245])

print("Downloaded "+str(len(df_cmd_field))+" rows of data for field stars")

# Assign color to legend

def colormap_picker(aid_list):
    #Color palettes generated at http://vrl.cs.brown.edu/color
    la = len(aid_list)
    if la==1:
        colors = ['#e52638']#red
    elif la== 2:
        colors = ["#e52638", "#69ef7b"]#red,green
    elif la==3:
        colors = ["#e52638", "#3db447", "#793883"]#red,green,blue
    elif la==4:
        colors = ["#e52638", "#7bde3f", "#84317b", "#1d8a20"]#red,geen,purple,green
    elif la==5:
        colors = ["#e52638", "#4cf185", "#801967", "#3b8738", "#dd3dca"]#red,geen,purple,green,pink
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

def build_banner():
    return html.Div(
        id="banner",
        className="banner",
        children=[
            #html.Img(src=app.get_asset_url("dash-logo.png")),
            html.H6("MOCA explorer"),
        ],
    )

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

def generate_xy_map(dff, associations, xvar, yvar, xtitle, ytitle, selected_data, style):

    layout = go.Layout(
        clickmode="event+select",
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        dragmode="lasso",
        xaxis={'title':xtitle},
        yaxis={'title':ytitle},
        showlegend=True,
        #autosize=True,
        hovermode="closest",
        margin=dict(l=110, r=50, t=50, b=50),
        #margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            #bgcolor="#1f2c56",
            orientation="h",
            #font=dict(color="white"),
            x=0,
            y=-0.25,
            yanchor="bottom",
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
            marker={"color": colormap[association], "size": 4},
            text=dff_aid['text_list'],
            name=association,
            selectedpoints=selected_index,
            customdata=dff_aid["moca_oid"],
        )
        new_trace.update(unselected=dict(marker=dict(opacity=unselected_opacity)))
        #new_trace.update(selected=dict(marker=dict(color='red')),unselected=dict(marker=dict(color='blue',opacity=0.001)))
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

    return fig

def generate_xyz_map(dff, associations, xvar, yvar, zvar, xtitle, ytitle, ztitle, selected_data, style):

    layout = go.Layout(
        #clickmode="event+select",
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        dragmode="lasso",
        xaxis={'title':xtitle},
        yaxis={'title':ytitle},
        #zaxis={'title':ztitle},
        showlegend=True,
        #autosize=True,
        hovermode="closest",
        margin=dict(l=110, r=50, t=50, b=50),
        #margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            #bgcolor="#1f2c56",
            orientation="h",
            #font=dict(color="white"),
            yanchor="top",
        ),
    )

    colormap = colormap_picker(associations)

    data = []
    if selected_data is None:
        totsel = 0
    else:
        totsel = len(selected_data)
    # for association in associations:
    #     if selected_data[association] is not None:
    #         totsel += len(selected_data[association])

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

        #Plot the *DE*selected data points
        if dff_deselect is not None:
            dff_plot = dff_deselect
            new_trace = go.Scatter3d(
                x=dff_plot[xvar],#This is the x in the MOCA column
                y=dff_plot[yvar],#This is the y in the MOCA column
                z=dff_plot[zvar],#This is the y in the MOCA column
                opacity=unselected_opacity,
                mode="markers",
                marker={"color": colormap[association], "size": 3},
                text=dff_plot["text_list"],
                name=association,
                customdata=dff_plot["moca_oid"],
            )
            data.append(new_trace)

        #Plot the selected data points
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
    
    fig = go.Figure(data=data,layout=layout)
    fig.update_scenes(xaxis={'title':xtitle},yaxis={'title':ytitle},zaxis={'title':ztitle})
    
    #Dont set default axis range for now because I cannot zoom out of it in the dash app
    # #Default axis range
    # if (xvar=='x' or xvar=='y' or xvar=='z'):
    #     fig.update_scenes(xaxis={'range':[-150,150]})
    # if (yvar=='x' or yvar=='y' or yvar=='z'):
    #     fig.update_scenes(yaxis={'range':[-150,150]})
    # if (zvar=='x' or zvar=='y' or zvar=='z'):
    #     fig.update_scenes(zaxis={'range':[-150,150]})
    # if xvar=='u':
    #     fig.update_scenes(xaxis={'range':[-80,70]})
    # if yvar=='u':
    #     fig.update_scenes(yaxis={'range':[-80,70]})
    # if zvar=='u':
    #     fig.update_scenes(zaxis={'range':[-80,70]})
    # if xvar=='v':
    #     fig.update_scenes(xaxis={'range':[-70,20]})
    # if yvar=='v':
    #     fig.update_scenes(yaxis={'range':[-70,20]})
    # if zvar=='v':
    #     fig.update_scenes(zaxis={'range':[-70,20]})
    # if xvar=='w':
    #     fig.update_scenes(xaxis={'range':[-70,20]})
    # if yvar=='w':
    #     fig.update_scenes(yaxis={'range':[-70,20]})
    # if zvar=='w':
    #     fig.update_scenes(zaxis={'range':[-70,20]})

    return fig

def generate_gaiadr3_cmd(dff, associations, df_cmd_field, selected_data, field_visible, sequences_visible):

    layout = go.Layout(
        clickmode="event+select",
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        dragmode="lasso",
        xaxis={'title':'Gaia DR3 G - G_RP color (mag)'},
        yaxis={'title':'Gaia DR3 absolute G-band magnitude (mag)'},
        showlegend=True,
        #autosize=True,
        hovermode="closest",
        margin=dict(l=110, r=50, t=50, b=50),
        #margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            #bgcolor="#1f2c56",
            orientation="h",
            #font=dict(color="white"),
            x=0,
            y=-0.25,
            yanchor="bottom",
        ),
    )
    hovertemplate = "%{text}<br><br>G - G_RP : %{x:.2f}<br>M_G : %{y:.2f}<extra></extra>"

    colormap = colormap_picker(associations)

    data = []
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
            customdata=df_cmd_field['customdata'],
            visible=field_visible,
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

        new_trace = go.Scattergl(
            x=dff_aid["gr"],#This is the x in the MOCA column
            y=dff_aid["m_g"],#This is the y in the MOCA column
            opacity=0.8,
            mode="markers",
            hovertemplate=hovertemplate,
            marker={"color": colormap[association], "size": 5},
            text=dff_aid['text_list'],
            name=association,
            #selectedpoints=[],
            selectedpoints=selected_index,
            customdata=dff_aid["moca_oid"],
        )
        
        hexcolor = colormap[association]
        rgbcolor = np.array([int(hexcolor.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)])
        diff = bcg_color-rgbcolor
        rgbcolor_pale = (rgbcolor+diff*(1.0-unselected_opacity)).astype(int)
        #hsvcolor = list(colorsys.rgb_to_hsv(rgbcolor[0],rgbcolor[1],rgbcolor[2]))
        ##hsvcolor[1] = 255-(255-hsvcolor[1])/50.0
        #hsvcolor[1] = hsvcolor[1]/10.0
        #hsvcolor[2] = 1-(1-hsvcolor[2])/10.0
        ##hsvcolor[1] = hsvcolor[1]/10.0
        ##hsvcolor[1] = 1.0-(1.0-hsvcolor[1])/10.0
        #rgbcolor = list(colorsys.hsv_to_rgb(hsvcolor[0],hsvcolor[1],hsvcolor[2]))
        rgbcolor = [str(int(i)) for i in rgbcolor_pale]
        rgbcolorf = "rgb("+",".join(rgbcolor)+")"
        new_trace.update(unselected=dict(marker=dict(color=rgbcolorf)))
        #new_trace.update(unselected=dict(marker=dict(opacity=unselected_opacity)))
        data.append(new_trace)

    fig = go.Figure(data=data,layout=layout)
    
    #Default axis range
    fig.update_layout(yaxis_range=[20,-2])
    fig.update_layout(xaxis_range=[-0.5,2.5])

    return fig

# Helper for extracting select index from plots
def get_selection(data, moca_aid, associations, selection_data, starting_index):
    ind = []
    current_curve = associations.index(moca_aid)
    for point in selection_data["points"]:
        if point["curveNumber"] - starting_index == current_curve:
            ind.append(point["pointNumber"])
    return ind

app.layout = html.Div(
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
                                    #CODE CRASHES WHEN ZERO ASSO
                                    #EXPLAIN SHIFT CLICK ON ASSO NAMES
                                    #EXPLAIN 3D GRAPHS CANT YET SELECT
                                    #EXPLAIN up to 20 colors
                                    #EXPLAIN database is queried everytime asso are changed
                                    #EXPLAIN graph ordering is like the ordering list of asso
                                    #EXPLAIN CLICK TO SELECT 1 POIN
                                    #EXPLAIN LASSO
                                    #EXPLAIN BUG WHERE SELECTION IN A NEW PANEL REQUIRES RESELECTING
                                    #EXPLAIN two fingers up and down swipe to zoom in/out in 3D scatter
                                    #EXPLAIN two fingers click to drag 3D figure
                                    #EXPLAIN bug in Safari where imprint of the first plot state can remain, not present in Google Chrome
                                    #XPLAIN individual plots only appear when 1 star is selected
                                    #EXPLAIN clicking on legend items
                                    id="instructions",
                                    children="Select data points from any plot to "
                                    "visualize cross-filtering to other plots. Selection could be done by "
                                    "clicking on individual data points or using the lasso tool to capture "
                                    "multiple data points or bars. With the box tool from modebar, multiple "
                                    "regions can be selected by holding the SHIFT key while clicking and "
                                    "dragging.", style={"width": "100%"},
                                ),
                                build_graph_title("Select Stellar Associations"),
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
                            ],
                        ),
                        dcc.Store(id='db-data'),
                    ],
                ),
            ],
        ),
        html.Div(
            className="row",
            id="bottom-row",
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
                                            "label": "Field Stars",
                                            "value": "Field Stars",
                                        },
                                        {
                                            "label": "Sequences",
                                            "value": "Sequences",
                                        },
                                    ],
                                    value=["Field Stars", "Sequences"],
                                ),
                        html.Br(),
                        dcc.Graph(id="gaiadr3-cmd"),
                    ],
                ),
                # XYZ
                html.Div(
                    id="xyz-container",
                    className="four columns",
                    children=[
                        html.Br(),
                        build_graph_title("Galactic X, Y, Z coordinates"),
                        html.Br(),html.Br(),html.Br(),html.Br(),
                        dcc.Graph(id="xyz-map"),
                    ],
                ),
                # UVW
                html.Div(
                    id="uvw-container",
                    className="four columns",
                    children=[
                        html.Br(),
                        build_graph_title("Galactic U, V, W space velocities"),
                        html.Br(),html.Br(),html.Br(),html.Br(),
                        dcc.Graph(id="uvw-map"),
                    ],
                ),
                # XY
                html.Div(
                    id="xy-container",
                    className="three columns",
                    children=[
                        html.Br(),
                        build_graph_title("Galactic X, Y coordinates"),
                        dcc.Checklist(
                                    id="xymap-view-selector",
                                    options=[
                                        {
                                            "label": "Association Centers",
                                            "value": "Association Centers",
                                        },
                                        {
                                            "label": "BANYAN Models",
                                            "value": "BANYAN Models",
                                        },
                                    ],
                                    value=["Association Centers", "BANYAN Models"],
                                ),
                        html.Br(),
                        dcc.Graph(id="xy-map"),
                    ],
                ),
                # YZ
                html.Div(
                    id="yz-container",
                    className="three columns",
                    children=[
                        html.Br(),
                        build_graph_title("Galactic Y, Z coordinates"),
                        html.Br(),html.Br(),html.Br(),html.Br(),
                        dcc.Graph(id="yz-map"),
                    ],
                ),
                # UV
                html.Div(
                    id="uv-container",
                    className="three columns",
                    children=[
                        html.Br(),
                        build_graph_title("Galactic U, V space velocities"),
                        html.Br(),html.Br(),html.Br(),html.Br(),
                        dcc.Graph(id="uv-map"),
                    ],
                ),
                # UW
                html.Div(
                    id="uw-container",
                    className="three columns",
                    children=[
                        html.Br(),
                        build_graph_title("Galactic U, W space velocities"),
                        html.Br(),html.Br(),html.Br(),html.Br(),
                        dcc.Graph(id="uw-map"),
                    ],
                ),
            ],
        ),
    ]
)

# Update AID-select
@app.callback(
    output=Output("db-data","data"),
    inputs=[
        Input("aid-select", "value"),
    ],
)
def update_aid_select(
    aid_select,
):
    
    # Query the moca database to obtain a Pandas DataFrame for the specific group needed
    aid_query = " OR ".join(["moca_aid='"+stri+"'" for stri in aid_select])
    df = moca.query("SELECT spt, designation, dr3_ruwe, gmag, rmag, plx, dmod, moca_oid, moca_aid, moca_mtid, x, y, z, u, v, w FROM summary_all_members WHERE (moca_mtid != 'CM' AND moca_mtid != 'LM' AND moca_mtid != 'R') AND ("+aid_query+")")
    df['gr'] = df['gmag']-df['rmag']
    df['m_g'] = df['gmag']-5.0*(np.log10(1000.0/df['plx'])-1)
    df['m_r'] = df['rmag']-5.0*(np.log10(1000.0/df['plx'])-1)

    print("Downloaded "+str(len(df))+" rows of general data from DB")

    return df.to_json(date_format='iso', orient='split')

# Update XYZ Map
@app.callback(
    output=Output("xyz-map", "figure"),
    inputs=[
        Input("uv-map", "selectedData"),
        Input("uw-map", "selectedData"),
        Input("xy-map", "selectedData"),
        Input("yz-map", "selectedData"),
        Input("gaiadr3-cmd", "selectedData"),
        Input("db-data", "data"),
        Input("xymap-view-selector", "value"),
    ],
    state=[State("aid-select", "value")],
)
def update_xyz_map(
    uv_selected_data, uw_selected_data, xy_selected_data, yz_selected_data, cmd_selected_data, jsonified_db_data, xymap_view, aid_select
):
    
    # Read data from session memory
    df = pd.read_json(jsonified_db_data, orient='split')
    dff = df[df["moca_aid"].isin(aid_select)]
    
    # Preserve plotting order
    associations = aid_select

    # Find which one has been triggered
    ctx = dash.callback_context

    prop_id = ""
    prop_type = ""
    if ctx.triggered:
        splitted = ctx.triggered[0]["prop_id"].split(".")
        prop_id = splitted[0]
        prop_type = splitted[1]

    processed_data = None
    selected_data = None

    if (prop_id == "gaiadr3-cmd" or prop_id == "uv-map" or prop_id == "uw-map" or prop_id == "xy-map" or prop_id == "yz-map"):
        if prop_id == "uv-map":
            selected_data = uv_selected_data
        if prop_id == "uw-map":
            selected_data = uw_selected_data
        if prop_id == "xy-map":
            selected_data = xy_selected_data
        if prop_id == "yz-map":
            selected_data = yz_selected_data
        if prop_id == "gaiadr3-cmd":
            selected_data = cmd_selected_data
        if selected_data is None:
            processed_data = None
        else:
            processed_data = [seldatapoint['customdata'] for seldatapoint in selected_data['points']]

    return generate_xyz_map(dff, associations, 'x', 'y', 'z', 'X (pc)', 'Y (pc)', 'Z (pc)', processed_data, xymap_view)

# Update UVW Map
@app.callback(
    output=Output("uvw-map", "figure"),
    inputs=[
        Input("uv-map", "selectedData"),
        Input("uw-map", "selectedData"),
        Input("xy-map", "selectedData"),
        Input("yz-map", "selectedData"),
        Input("gaiadr3-cmd", "selectedData"),
        Input("db-data", "data"),
        Input("xymap-view-selector", "value"),
    ],
    state=[State("aid-select", "value")],
)
def update_uvw_map(
    uv_selected_data, uw_selected_data, xy_selected_data, yz_selected_data, cmd_selected_data, jsonified_db_data, xymap_view, aid_select
):
    
    df = pd.read_json(jsonified_db_data, orient='split')
    dff = df[df["moca_aid"].isin(aid_select)]
    
    # Preserve plotting order
    associations = aid_select

    # Find which one has been triggered
    ctx = dash.callback_context

    prop_id = ""
    prop_type = ""
    if ctx.triggered:
        splitted = ctx.triggered[0]["prop_id"].split(".")
        prop_id = splitted[0]
        prop_type = splitted[1]

    processed_data = None
    selected_data = None

    if (prop_id == "gaiadr3-cmd" or prop_id == "uv-map" or prop_id == "uw-map" or prop_id == "xy-map" or prop_id == "yz-map"):
        if prop_id == "uv-map":
            selected_data = uv_selected_data
        if prop_id == "uw-map":
            selected_data = uw_selected_data
        if prop_id == "xy-map":
            selected_data = xy_selected_data
        if prop_id == "yz-map":
            selected_data = yz_selected_data
        if prop_id == "gaiadr3-cmd":
            selected_data = cmd_selected_data
        if selected_data is None:
            processed_data = None
        else:
            processed_data = [seldatapoint['customdata'] for seldatapoint in selected_data['points']]

    return generate_xyz_map(dff, associations, 'u', 'v', 'w', 'U (km/s)', 'V (km/s)', 'W (km/s)', processed_data, xymap_view)

# Update UV Map
@app.callback(
    output=Output("uv-map", "figure"),
    inputs=[
        Input("uw-map", "selectedData"),
        Input("xy-map", "selectedData"),
        Input("yz-map", "selectedData"),
        Input("gaiadr3-cmd", "selectedData"),
        Input("db-data", "data"),
        Input("xymap-view-selector", "value"),
    ],
    state=[State("aid-select", "value")],
)
def update_uv_map(
    uw_selected_data, xy_selected_data, yz_selected_data, cmd_selected_data, jsonified_db_data, xymap_view, aid_select
):
    
    # Read data from session memory
    df = pd.read_json(jsonified_db_data, orient='split')
    dff = df[df["moca_aid"].isin(aid_select)]
    
    # Preserve plotting order
    associations = aid_select

    # Find which one has been triggered
    ctx = dash.callback_context

    prop_id = ""
    prop_type = ""
    if ctx.triggered:
        splitted = ctx.triggered[0]["prop_id"].split(".")
        prop_id = splitted[0]
        prop_type = splitted[1]

    processed_data = None
    selected_data = None

    if (prop_id == "gaiadr3-cmd" or prop_id == "yz-map" or prop_id == "xy-map" or prop_id == "uw-map"):
        if prop_id == "uw-map":
            selected_data = uw_selected_data
        if prop_id == "xy-map":
            selected_data = xy_selected_data
        if prop_id == "yz-map":
            selected_data = yz_selected_data
        if prop_id == "gaiadr3-cmd":
            selected_data = cmd_selected_data
        if selected_data is None:
            processed_data = None
        else:
            processed_data = [seldatapoint['customdata'] for seldatapoint in selected_data['points']]

    return generate_xy_map(dff, associations, 'u', 'v', 'U (km/s)', 'V (km/s)', processed_data, xymap_view)

# Update UW Map
@app.callback(
    output=Output("uw-map", "figure"),
    inputs=[
        Input("uv-map", "selectedData"),
        Input("xy-map", "selectedData"),
        Input("yz-map", "selectedData"),
        Input("gaiadr3-cmd", "selectedData"),
        Input("db-data", "data"),
        Input("xymap-view-selector", "value"),
    ],
    state=[State("aid-select", "value")],
)
def update_uw_map(
    uv_selected_data, xy_selected_data, yz_selected_data, cmd_selected_data, jsonified_db_data, xymap_view, aid_select
):
    
    df = pd.read_json(jsonified_db_data, orient='split')
    dff = df[df["moca_aid"].isin(aid_select)]
    
    # Preserve plotting order
    associations = aid_select

    # Find which one has been triggered
    ctx = dash.callback_context

    prop_id = ""
    prop_type = ""
    if ctx.triggered:
        splitted = ctx.triggered[0]["prop_id"].split(".")
        prop_id = splitted[0]
        prop_type = splitted[1]

    processed_data = None
    selected_data = None

    if (prop_id == "gaiadr3-cmd" or prop_id == "yz-map" or prop_id == "xy-map" or prop_id == "uv-map"):
        if prop_id == "uv-map":
            selected_data = uv_selected_data
        if prop_id == "xy-map":
            selected_data = xy_selected_data
        if prop_id == "yz-map":
            selected_data = yz_selected_data
        if prop_id == "gaiadr3-cmd":
            selected_data = cmd_selected_data
        if selected_data is None:
            processed_data = None
        else:
            processed_data = [seldatapoint['customdata'] for seldatapoint in selected_data['points']]

    return generate_xy_map(dff, associations, 'u', 'w', 'U (km/s)', 'W (km/s)', processed_data, xymap_view)

# Update XY Map
@app.callback(
    output=Output("xy-map", "figure"),
    inputs=[
        Input("uv-map", "selectedData"),
        Input("uw-map", "selectedData"),
        Input("yz-map", "selectedData"),
        Input("gaiadr3-cmd", "selectedData"),
        Input("db-data", "data"),
        Input("xymap-view-selector", "value"),
    ],
    state=[State("aid-select", "value")],
)
def update_xy_map(
    uv_selected_data, uw_selected_data, yz_selected_data, cmd_selected_data, jsonified_db_data, xymap_view, aid_select
):
    
    # Read data from session memory
    df = pd.read_json(jsonified_db_data, orient='split')
    dff = df[df["moca_aid"].isin(aid_select)]

    # Preserve plotting order
    associations = aid_select

    # Find which one has been triggered
    ctx = dash.callback_context

    prop_id = ""
    prop_type = ""
    if ctx.triggered:
        splitted = ctx.triggered[0]["prop_id"].split(".")
        prop_id = splitted[0]
        prop_type = splitted[1]

    processed_data = None
    selected_data = None

    if (prop_id == "gaiadr3-cmd" or prop_id == "yz-map" or prop_id == "uv-map" or prop_id == "uw-map"):
        if prop_id == "uv-map":
            selected_data = uv_selected_data
        if prop_id == "uw-map":
            selected_data = uw_selected_data
        if prop_id == "yz-map":
            selected_data = yz_selected_data
        if prop_id == "gaiadr3-cmd":
            selected_data = cmd_selected_data
        if selected_data is None:
            processed_data = None
        else:
            processed_data = [seldatapoint['customdata'] for seldatapoint in selected_data['points']]

    return generate_xy_map(dff, associations, 'x', 'y', 'X (pc)', 'Y (pc)', processed_data, xymap_view)

# Update YZ Map
@app.callback(
    output=Output("yz-map", "figure"),
    inputs=[
        Input("xy-map", "selectedData"),
        Input("uv-map", "selectedData"),
        Input("uw-map", "selectedData"),
        Input("gaiadr3-cmd", "selectedData"),
        Input("db-data", "data"),
        Input("xymap-view-selector", "value"),
    ],
    state=[State("aid-select", "value")],
)
def update_yz_map(
    xy_selected_data, uv_selected_data, uw_selected_data, cmd_selected_data, jsonified_db_data, xymap_view, aid_select
):
    
    # Read data from session memory
    df = pd.read_json(jsonified_db_data, orient='split')
    dff = df[df["moca_aid"].isin(aid_select)]
    
    # Preserve plotting order
    associations = aid_select

    # Find which one has been triggered
    ctx = dash.callback_context

    prop_id = ""
    prop_type = ""
    if ctx.triggered:
        splitted = ctx.triggered[0]["prop_id"].split(".")
        prop_id = splitted[0]
        prop_type = splitted[1]

    processed_data = None
    selected_data = None
    
    if (prop_id == "gaiadr3-cmd" or prop_id == "xy-map" or prop_id == "uv-map" or prop_id == "uw-map"):
        if prop_id == "xy-map":
            selected_data = xy_selected_data
        if prop_id == "uv-map":
            selected_data = uv_selected_data
        if prop_id == "uw-map":
            selected_data = uw_selected_data
        if prop_id == "gaiadr3-cmd":
            selected_data = cmd_selected_data
        if selected_data is None:
            processed_data = None
        else:
            processed_data = [seldatapoint['customdata'] for seldatapoint in selected_data['points']]

    return generate_xy_map(dff, associations, 'y', 'z', 'Y (pc)', 'Z (pc)', processed_data, xymap_view)

# Update Gaia DR3 CMD
@app.callback(
    output=Output("gaiadr3-cmd", "figure"),
    inputs=[
        Input("xy-map", "selectedData"),
        Input("yz-map", "selectedData"),
        Input("uv-map", "selectedData"),
        Input("uw-map", "selectedData"),
        Input("db-data", "data"),
        Input("cmd-layer-select", "value"),
    ],
    state=[State("gaiadr3-cmd", "figure"), State("aid-select", "value")],
)
def update_gaiadr3_cmd(
    xy_selected_data,
    yz_selected_data,
    uv_selected_data,
    uw_selected_data,
    jsonified_db_data,
    layer_select,
    curr_fig,
    aid_select,
):
    sequences_visible = field_visible = True

    df = pd.read_json(jsonified_db_data, orient='split')
    dff = df[df["moca_aid"].isin(aid_select)]
    
    #Preserve plotting order
    associations = aid_select

    # Find which one has been triggered
    ctx = dash.callback_context

    prop_id = ""
    prop_type = ""
    if ctx.triggered:
        splitted = ctx.triggered[0]["prop_id"].split(".")
        prop_id = splitted[0]
        prop_type = splitted[1]

    processed_data = None
    selected_data = None

    if prop_id != "cmd-layer-select":
        if (prop_id == "xy-map" or prop_id == "yz-map" or prop_id == "uv-map" or prop_id == "uw-map") and prop_type == "selectedData":
            if prop_id == "xy-map":
                selected_data = xy_selected_data
            if prop_id == "yz-map":
                selected_data = yz_selected_data
            if prop_id == "uv-map":
                selected_data = uv_selected_data
            if prop_id == "uw-map":
                selected_data = uw_selected_data
            
            #Fetch the moca_oid identifiers of the selected data points
            if selected_data is None:
                processed_data = None
            else:
                processed_data = [seldatapoint['customdata'] for seldatapoint in selected_data['points']]
        
        return generate_gaiadr3_cmd(
            dff, associations, df_cmd_field, processed_data, field_visible, sequences_visible
        )

    if prop_id == "cmd-layer-select":
        if curr_fig is not None:
            #This is not coded yet
            if "Field Stars" not in layer_select:
                field_visible = "legendonly"
            if "Sequences" not in layer_select:
                sequences_visible = "legendonly"

            curr_fig["data"][0]["visible"] = field_visible

            return curr_fig
        else:
            return curr_fig

# Running the server
#if __name__ == "__main__":
#    app.run_server(host='0.0.0.0',debug=True)
if __name__ == "__main__":
    app.run_server(debug=True)
