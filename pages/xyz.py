import dash
from dash import html, dcc, dash_table, get_asset_url
from urllib.parse import urlparse, parse_qs
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

#bcg_color = 'rgb(0,0,0)'
#bcg_color = 'rgb(220,220,220)'
bcg_color = 'rgb(255,255,255)'

#initial_aids = ["ABDMG","BPMG","TWA","THA"]
initial_aids = ["HYA","CBER","TWA","THA"]
initial_mtids = ["BF","HM","CM"]

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
df_columns = ['designation','moca_aid','moca_mtid','spt','moca_oid','gmag','bmag', 'rmag','plx','dmod','dr3_ruwe','x','y','z','u','v','w','prot_days','gaia_act','ewli','ewha']
df_columns_memonly = ['x_opt','y_opt','z_opt','u_opt','v_opt','w_opt']
dfe = moca.query("SELECT "+", ".join(df_columns+df_columns_memonly)+" FROM summary_all_members LIMIT 0")
dfoe = moca.query("SELECT "+", ".join(df_columns)+" FROM summary_all_objects LIMIT 0")
#dfoe = dfe.copy(deep=True)
dfme = moca.query("SELECT dbs.* FROM moca_banyan_sigma_models mbs LEFT JOIN data_banyan_sigma_models dbs USING(moca_bsmdid) WHERE mbs.adopted=1 LIMIT 0")

unselected_opacity = 0.1
selected_opacity = 1
#selected_opacity = 0.3
#selected_opacity = 1

# Load a list of all associations for the Dropdown menu
#df_aids = moca.query("SELECT moca_aid FROM moca_associations")
#df_oids = moca.query("SELECT designation FROM mechanics_all_designations") #This is way too large
df_mtids = moca.query("SELECT moca_mtid, name, description FROM (SELECT * FROM (SELECT mt.* FROM moca_membership_types mt JOIN (SELECT DISTINCT moca_mtid FROM summary_all_members) dm ON(dm.moca_mtid=mt.moca_mtid)) oq) oq2 ORDER BY level DESC")

text_mtids = ("* **"+df_mtids["moca_mtid"]+"**: "+df_mtids["description"]).values.astype("U").tolist()

#print("Downloaded "+str(len(df_aids))+" rows of data for associations information")

#df_asso_centers = moca.query("SELECT dbsm.moca_aid, AVG(dbsm.x_cen) x, AVG(dbsm.y_cen) y, AVG(dbsm.z_cen) z, AVG(dbsm.u_cen) u, AVG(dbsm.v_cen) v, AVG(dbsm.w_cen) w FROM data_banyan_sigma_models dbsm JOIN moca_banyan_sigma_models mbsm USING(moca_bsmdid) WHERE mbsm.adopted=1 AND dbsm.moca_aid != 'FIELD' GROUP BY dbsm.moca_aid")
#df_asso_centers = moca.query("CALL list_association_labels();")

# Assign color to legend
# Eventually move this to a subroutine
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
    
    #Flip colors to get red on top
    colors.reverse()
    
    colormap = {}
    for ind, moca_aid in enumerate(aid_list):
        colormap[moca_aid] = colors[ind%len(colors)]
    return colormap

# Eventually move this to a subroutine
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

# Eventually move this to a subroutine
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

# Eventually move this to a subroutine
# Visual website banner
def build_banner():
    return html.Div(
        id="banner",
        #className="banner",
        children=[
            #html.Img(src=get_asset_url("dash-logo.png")),
            html.H2("MOCA SPATIAL EXPLORER"),
        ],
        style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"white"},
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

def build_hover_dfo(dff):
    return list(
        map(
            lambda x1, x2, x3, x4, x5, x6: "MOCA OID : "+str(int(x1))+"<br>Designation : "+str(x2)+"<br>Membership : "+str(x4)+" in "+str(x3)+"<br>SPT : "+str(x5)+"<br>RUWE : "+str('%.1f' %x6),
            dff["moca_oid"],
            dff["designation"],
            dff["moca_aid"],
            dff["moca_mtid"],
            dff["spt"],
            dff["dr3_ruwe"],
        )
    )

# Eventually move this to a subroutine
def build_graph_title(title):
    return html.P(className="graph-title", children=title)

# Eventually move this to a subroutine
# Build 3D ellipsoids to show BANYAN models
def build_ellipsoid_3d(offset, covar_matrix, trace_color, opacity=0.5):
    
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

def build_solar_neighborhood_3d(radius=50, nlines=10, trace_color='black', opacity=0.2, npoints=500):
    
    #Build 3D grid
    phi = np.linspace(0, 2*np.pi,num=npoints)
    radii = (np.linspace(0,radius,num=nlines+1))[1:]
    phim, radiim = np.meshgrid(phi, radii)

    x = np.cos(phim) * radiim
    y = np.sin(phim) * radiim
    z = phim * 0

    # Create the plot
    thick = 3
    lines = []
    line_marker = dict(color=trace_color, width=thick)

    # First layer of grid lines
    for i, j, k in zip(x, y, z):
        lines.append(go.Scatter3d(x=i, y=j, z=k, mode='lines', line=line_marker, hoverinfo='skip', opacity=opacity, showlegend=False))

    #Add 500 pc blue line

    opacity=0.5
    maxrad = 500
    thick = 5
    linvec = np.linspace(0,maxrad,num=npoints)
    zeros = np.zeros(npoints)

    lines.append(go.Scatter3d(x=zeros, y=zeros, z=linvec, mode='lines', line=dict(color='blue', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))
    lines.append(go.Scatter3d(x=linvec, y=zeros, z=zeros, mode='lines', line=dict(color='red', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))
    lines.append(go.Scatter3d(x=zeros, y=linvec, z=zeros, mode='lines', line=dict(color='green', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))
    lines.append(go.Scatter3d(x=zeros, y=zeros, z=-linvec, mode='lines', line=dict(color='black', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))
    lines.append(go.Scatter3d(x=-linvec, y=zeros, z=zeros, mode='lines', line=dict(color='black', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))
    lines.append(go.Scatter3d(x=zeros, y=-linvec, z=zeros, mode='lines', line=dict(color='black', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))

    return lines

# Eventually move this to a subroutine
def generate_xyz_map_xyzpage(dff, dfm, dfo, df_asso_centers, associations, xvar, yvar, zvar, xtitle, ytitle, ztitle, title, selected_data, style, self_figure):

    # Read hover property
    # hover = False
    # try:
    #     if hover_select[0] == 'Enable Hover Properties':
    #         hover = "closest"
    # except:
    #     void = 1

    # Read layer properties
    models_visible = assume_membership = show_asso_centers = True
    hover = "closest"
    if "BANYAN Models" not in style:
        models_visible = False
    if "assmem" not in style:
        assume_membership = False
    if "asscen" not in style:
        show_asso_centers = False
    if "hover" not in style:
        hover = False
    
    #max_pc_range = 1e5
    max_pc_range = 1e3
    #max_pc_range = 100
    
    dff.loc[dff[xvar].abs()>=max_pc_range, xvar] = np.nan
    dff.loc[dff[yvar].abs()>=max_pc_range, yvar] = np.nan
    dff.loc[dff[zvar].abs()>=max_pc_range, zvar] = np.nan
    #import pdb; pdb.set_trace()

    xvar_orig = xvar
    yvar_orig = yvar
    zvar_orig = zvar
    if assume_membership:
        xvar += "_opt"
        yvar += "_opt"
        zvar += "_opt"

    layout = go.Layout(
        height=850,
        #width=1200,
        #uirevision="constant",
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        #dragmode="lasso",
        xaxis={'title':xtitle,'uirevision':'fixed'},
        yaxis={'title':ytitle,'uirevision':'fixed'},
        #showlegend=True,
        hovermode=hover,
        paper_bgcolor=bcg_color,#
        plot_bgcolor=bcg_color,
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            #orientation="h",
            #orientation="",
            #orientation="h",
            #x=0,
            #y=0.,
            #yanchor="bottom",
            orientation = 'h', xanchor = "right", x = 1, y = 0, yanchor="bottom",
        ),
    )
    
    colormap = colormap_picker(associations)

    #Default axis range
    default_pc_range = 500
    pc_range = max([dff[xvar].abs().max(),dff[yvar].abs().max(),dff[zvar].abs().max(),default_pc_range])
    pc_range = min([pc_range,max_pc_range])

    data = []

    if show_asso_centers:
        df_asso_display = df_asso_centers.loc[(df_asso_centers[xvar_orig].abs()<=pc_range)&(df_asso_centers[yvar_orig].abs()<=pc_range)&(df_asso_centers[zvar_orig].abs()<=pc_range)]
        new_trace = go.Scatter3d(
            x=df_asso_display[xvar_orig],
            y=df_asso_display[yvar_orig],
            z=df_asso_display[zvar_orig],
            opacity=0.2,
            mode="text",
            text=df_asso_display["moca_aid"],
            name="Association labels",
        )
        data.append(new_trace)

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

        # # Plot the *DE*selected data points
        # if dff_deselect is not None:
        #     dff_plot = dff_deselect
        #     new_trace = go.Scatter3d(
        #         x=dff_plot[xvar],#This is the x in the MOCA column
        #         y=dff_plot[yvar],#This is the y in the MOCA column
        #         z=dff_plot[zvar],#This is the y in the MOCA column
        #         opacity=unselected_opacity,
        #         mode="markers",
        #         showlegend=False,
        #         marker={"color": colormap[association], "size": 3},
        #         text=dff_plot["text_list"],
        #         name=association,
        #         customdata=dff_plot["moca_oid"],
        #     )
        #     data.append(new_trace)

        # Plot the selected data points
        if dff_select is not None:
            dff_plot = dff_select
            new_trace = go.Scatter3d(
                x=dff_plot[xvar],#This is the x in the MOCA column
                y=dff_plot[yvar],#This is the y in the MOCA column
                z=dff_plot[zvar],#This is the y in the MOCA column
                #opacity=selected_opacity,
                mode="markers",
                marker={"color": colormap[association], "size": 3, "opacity":selected_opacity},
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
                offset = np.array([dfm_row[xvar_orig+'_cen'],dfm_row[yvar_orig+'_cen'],dfm_row[zvar_orig+'_cen']])
                covar_matrix = np.array([
                    [dfm_row[xvar_orig+xvar_orig+'_covar'],dfm_row[xvar_orig+yvar_orig+'_covar'],dfm_row[xvar_orig+zvar_orig+'_covar']],
                    [dfm_row[xvar_orig+yvar_orig+'_covar'],dfm_row[yvar_orig+yvar_orig+'_covar'],dfm_row[yvar_orig+zvar_orig+'_covar']],
                    [dfm_row[xvar_orig+zvar_orig+'_covar'],dfm_row[yvar_orig+zvar_orig+'_covar'],dfm_row[zvar_orig+zvar_orig+'_covar']]
                    ])

                ellipses = build_ellipsoid_3d(offset, covar_matrix, colormap[association])

                for elli in ellipses:
                    data.append(elli)
    
    if len(dfo) != 0:
        
        text_list = build_hover_dfo(dfo)
        obj_color = "black"
        #Use xvar_orig, yvar_orig, zvar_orig because moca_oid displays cannot assume membership
        new_trace = go.Scatter3d(
            x=dfo[xvar_orig],#This is the x in the MOCA column
            y=dfo[yvar_orig],#This is the y in the MOCA column
            z=dfo[zvar_orig],#This is the z in the MOCA column
            #opacity=1,
            mode="markers",
            marker={"color": obj_color, "size": 8, "symbol":"diamond"},
            text=text_list,
            name="Individual Objects",
        )
        data.append(new_trace)

    # new_trace = go.Scatter3d(
    #         x=[0],
    #         y=[0],
    #         z=[0],
    #         opacity=1,
    #         mode="markers",
    #         marker_symbol="cross",
    #         marker={"color": "#000000", "size": 5},#, "symbol":"circle-dot"
    #         text="Sun",
    #         name="Sun",
    #     )
    # data.append(new_trace)

    # Plot the Solar neighborhood reference
    sn = build_solar_neighborhood_3d()
    for sni in sn:
        data.append(sni)

    # Add invisible points because plotly is too much of an idiot to correctly enforce even aspect ratio
    new_trace = go.Scatter3d(
            x=[pc_range,-pc_range],
            y=[pc_range,-pc_range],
            z=[pc_range,-pc_range],
            mode="markers",
            marker={"color": "rgba(255,255,255,0)", "size": 1},
            showlegend=False,
        )
    data.append(new_trace)

    #if self_figure is not None:
    #    fig = go.Figure(data=data,layout=self_figure['layout'])
    #else:
    fig = go.Figure(data=data,layout=layout)

    if (xvar_orig=='x' or xvar_orig=='y' or xvar_orig=='z'):
        #fig.update_scenes(xaxis={'range':[-1e4,3e4]})
        fig.update_scenes(xaxis={'range':[-pc_range,pc_range]})
    if (yvar_orig=='x' or yvar_orig=='y' or yvar_orig=='z'):
        #fig.update_scenes(yaxis={'range':[-3e4,3e4]})
        fig.update_scenes(yaxis={'range':[-pc_range,pc_range]})
    if (zvar_orig=='x' or zvar_orig=='y' or zvar_orig=='z'):
        #fig.update_scenes(zaxis={'range':[-1e4,1e4]})
        fig.update_scenes(zaxis={'range':[-pc_range,pc_range]})
    if (xvar_orig=='u' or xvar_orig=='v' or xvar_orig=='w'):
        fig.update_scenes(xaxis={'range':[-pc_range,pc_range]})
    if (yvar_orig=='u' or yvar_orig=='v' or yvar_orig=='w'):
        fig.update_scenes(yaxis={'range':[-pc_range,pc_range]})
    if (zvar_orig=='u' or zvar_orig=='v' or zvar_orig=='w'):
        fig.update_scenes(zaxis={'range':[-pc_range,pc_range]})

    # Try to force aspect ratio (does not always work)
    fig.update_scenes(aspectmode='data')

    #import pdb; pdb.set_trace()
    # dx = (fig['layout']['scene']['xaxis']['range'][1] - fig['layout']['scene']['xaxis']['range'][0])
    # dy = (fig['layout']['scene']['yaxis']['range'][1] - fig['layout']['scene']['yaxis']['range'][0])
    # dz = (fig['layout']['scene']['zaxis']['range'][1] - fig['layout']['scene']['zaxis']['range'][0])
    # xc = (fig['layout']['scene']['xaxis']['range'][1] + fig['layout']['scene']['xaxis']['range'][0])/2
    # yc = (fig['layout']['scene']['yaxis']['range'][1] + fig['layout']['scene']['yaxis']['range'][0])/2
    # zc = (fig['layout']['scene']['zaxis']['range'][1] + fig['layout']['scene']['zaxis']['range'][0])/2
    
    # dx_zoom = dx*2**zoom_out_level
    # dy_zoom = dy*2**zoom_out_level
    # dz_zoom = dz*2**zoom_out_level

    # #Update zoom level
    # fig.update_scenes(xaxis={'range':[xc-dx_zoom/2,xc+dx_zoom/2]})
    # fig.update_scenes(yaxis={'range':[yc-dy_zoom/2,yc+dy_zoom/2]})
    # fig.update_scenes(zaxis={'range':[zc-dz_zoom/2,zc+dz_zoom/2]})

    #Adjust camera position
    dx = (fig['layout']['scene']['xaxis']['range'][1] - fig['layout']['scene']['xaxis']['range'][0])
    dy = (fig['layout']['scene']['yaxis']['range'][1] - fig['layout']['scene']['yaxis']['range'][0])
    dz = (fig['layout']['scene']['zaxis']['range'][1] - fig['layout']['scene']['zaxis']['range'][0])
    xc = (fig['layout']['scene']['xaxis']['range'][1] + fig['layout']['scene']['xaxis']['range'][0])/2
    yc = (fig['layout']['scene']['yaxis']['range'][1] + fig['layout']['scene']['yaxis']['range'][0])/2
    zc = (fig['layout']['scene']['zaxis']['range'][1] + fig['layout']['scene']['zaxis']['range'][0])/2

    #eye_pos_xyz = [100.,100.,100.]
    eye_pos_xyz = [-500.,-500.,500.]
    eye_pos_xrel = (eye_pos_xyz[0] - xc)/dx*2
    eye_pos_yrel = (eye_pos_xyz[1] - yc)/dy*2
    eye_pos_zrel = (eye_pos_xyz[2] - zc)/dz*2

    cen_pos_xyz = [0.,0.,0.]
    cen_pos_xrel = (cen_pos_xyz[0] - xc)/dx*2
    cen_pos_yrel = (cen_pos_xyz[1] - yc)/dy*2
    cen_pos_zrel = (cen_pos_xyz[2] - zc)/dz*2

    camera = dict(
        up=dict(x=0, y=0, z=1),
        center=dict(x=cen_pos_xrel, y=cen_pos_yrel, z=cen_pos_zrel),
        eye=dict(x=eye_pos_xrel, y=eye_pos_yrel, z=eye_pos_zrel),
        #projection=dict(type='orthographic'),
    )

    fig.update_layout(scene_camera=camera)

    #Remove axes
    fig.update_layout(
        scene=dict(
            xaxis_showspikes=False,
            yaxis_showspikes=False,
            zaxis_showspikes=False,
            xaxis=dict(showticklabels=False),#,showgrid=False,showbackground=False,gridcolor=bcg_color,zerolinecolor=bcg_color
            yaxis=dict(showticklabels=False),
            zaxis=dict(showticklabels=False),
        )
    )
    
    #Fix axis names and MOCAdb watermark
    fig.update_scenes(xaxis={'title':''},yaxis={'title':''},zaxis={'title':''})
    
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

    #from PIL import Image
    #eight_bit_img = Image.open("/Users/jonathan/Documents/Postdoc/Digital_Universe/nyadb_xyz/data/Models/eso9845d-processed.pbm")
    #im_x, im_y = eight_bit_img.size
    # orig_img = Image.open("/Users/jonathan/Documents/Postdoc/Digital_Universe/nyadb_xyz/data/Models/eso9845d-processed.pbm")
    # im_x, im_y = orig_img.size
    # im = np.asarray(orig_img)
    # eight_bit_img = Image.fromarray(im).convert('P', palette='WEB', dither=None)
    # dum_img = Image.fromarray(np.ones((3,3,3), dtype='uint8')).convert('P', palette='WEB')
    # idx_to_color = np.array(dum_img.getpalette()).reshape((-1, 3))
    # colorscale=[[i/255.0, "rgb({}, {}, {})".format(*rgb)] for i, rgb in enumerate(idx_to_color)]
    # x = np.linspace(0,im_x, im_x)
    # y = np.linspace(0, im_y, im_y)
    # z = np.zeros((im_x,im_y))

    # contours = dict(x = dict(highlight=False),
    #             y = dict(highlight=False),
    #             z = dict(highlight=False))

    # fig.add_trace(go.Surface(x=x, y=y, z=z,
    #     surfacecolor=eight_bit_img, 
    #     contours=contours,
    #     cmin=0, 
    #     cmax=255,
    #     colorscale=colorscale,
    #     showscale=False,
    #     lighting_diffuse=1,
    #     lighting_ambient=1,
    #     lighting_fresnel=1,
    #     lighting_roughness=1,
    #     lighting_specular=0.5,
    #     opacity=1,
    # ))

    #zoom_out_level
    #import pdb; pdb.set_trace()

    #fig.update_layout(uirevision='constant')

    return fig

layout = html.Div(
    children=[
        dcc.Location(id='url', refresh=False),
        html.Div(
            id="top-row-xyzpage",
            children=[
                html.Div(
                    className="row",
                    id="top-row-header-xyzpage",
                    children=[
                        html.Div(
                            id="header-container-xyzpage",
                            children=[
                                build_banner(),
                                #dcc.Markdown(children=["MOCA Spatial-Kinematic Explorer"]),
                            ],
                        ),
                        dcc.Store(id='db-data-xyzpage'),
                    ],
                ),
            ],
        ),
        html.Div(
            #className="flex-grow-1",
            className="row",
            #style={"height": "1200pix"},#, "backgroundColor":"blue"
            id="first-data-row-xyzpage",
            children=[
                html.Div(className="two columns",
                    children=[
                        html.Br(),
                        html.Br(),
                        html.Br(),
                        dcc.Markdown(children=["Select stellar associations"]),
                        dcc.Dropdown(
                            id="aid-select-xyzpage",
                            multi=True,
                            value=None,
                            style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"white"},
                            ),
                        html.Br(),
                        html.Br(),
                        dcc.Markdown(children=["Select membership types"]),
                        dcc.Dropdown(
                            id="mtid-select-xyzpage",
                            options=[
                                {"label": " "+i, "value": i}
                                for i in df_mtids["moca_mtid"].unique().tolist()
                            ],
                            multi=True,
                            value=None,
                            style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"white"},
                        ),
                        html.Br(),
                        html.Br(),
                        dcc.Markdown(children=["Select individual stars"]),
                        dcc.Input(id="oid-select-xyzpage", type="text", placeholder="Insert MOCA object IDs separated by commas.", debounce=True, style={"width": "100%", "whiteSpace": "pre-wrap"}),
                        ],
                    ),
                # XYZ
                html.Div(
                    id="xyz-container-xyzpage",
                    className="eight columns",
                    children=[
                        #html.Br(),
                        #build_graph_title("Galactic X, Y, Z coordinates"),
                        # dcc.Checklist(
                        #             id="hover-select-xyzpage",
                        #             options=[
                        #                 {
                        #                     "label": " Enable Hover Properties",
                        #                     "value": "Enable Hover Properties",
                        #                 },
                        #             ],
                        #             value=[],
                        #             #labelStyle={'color': 'white'}
                        #         ),
                        
                        #html.Button('Zoom In', id='xyz-zoom-in-xyzpage', n_clicks=0),
                        #html.Button('Zoom Out', id='xyz-zoom-out-xyzpage', n_clicks=0),
                        dcc.Graph(id="xyz-map-xyzpage",config=figure_export_config),
                    ],
                ),
                html.Div(className="two columns",
                    children=[
                        html.Br(),
                        html.Br(),
                        html.Br(),
                        dcc.Checklist(
                                    id="xymap-view-selector-xyzpage",
                                    options=[
                                        {
                                            "label": "All Labels (slow load)",
                                            "value": "asscen",
                                        },
                                        {
                                            "label": "BANYAN Models",
                                            "value": "BANYAN Models",
                                        },
                                        {
                                            "label": "Assume Membership",
                                            "value": "assmem",
                                        },
                                        {
                                            "label": "Enable Hover Properties",
                                            "value": "hover",
                                        },
                                    ],
                                    value=["BANYAN Models"],
                                ),
                        #html.Br(),
                        #html.Button('Recenter', id='xyz-recenter-in-xyzpage', n_clicks=0),
                    ],
                ),
                # html.Div(className="one column"),
                # # UVW
                # html.Div(
                #     id="uvw-container-xyzpage",
                #     className="twelve columns",
                #     children=[
                #         html.Br(),
                #         build_graph_title("Galactic U, V, W space velocities"),
                #         html.Br(),html.Br(),#html.Br(),
                #         #html.Button('Zoom In', id='uvw-zoom-in-xyzpage', n_clicks=0),
                #         #html.Button('Zoom Out', id='uvw-zoom-out-xyzpage', n_clicks=0),
                #         dcc.Graph(id="uvw-map-xyzpage",config=figure_export_config),
                #     ],
                # ),
                # html.Div(className="one column"),
            ],
        ),
        # html.Div(
        #     className="row",
        #     id="table-row",
        #     children=[
        #         #Table
        #         html.Div(
        #             id="table-container",
        #             className="twelve columns",
        #             children=[
        #                 html.Br(),
        #                 build_graph_title("MOCA summary table"),
        #                 html.P("Rows are shown in order of selection, association and membership type. Selected rows are highlighted in green."),
        #                 dash_table.DataTable(
        #                     id="df-table",
        #                     columns=[{'id': x, 'name': x, 'presentation': 'markdown'} for x in dfe.columns],
        #                     export_format='csv',
        #                     style_header={
        #                         'fontSize': 15,
        #                         'fontWeight': 'bold',
        #                         'textAlign': 'center',
        #                     },
        #                     selected_rows=[],
        #                     style_data_conditional=get_style_data_conditional(),
        #                 ),
        #             ],
        #         ),
        #     ],
        # ),
    ]
)

selections = {
        }

# # Update table
# @dash.callback(
#     output=[
#         Output("df-table","data"),
#         Output("df-table","selected_rows"),
#         Output("df-table","style_data_conditional"),
#     ],
#     inputs=dict(
#         selections=selections,
#         jsonified_db_data=Input("db-data", "data"),
#         xymap_view=Input("xymap-view-selector", "value"),
#     ),
#     state=dict(
#         aid_select=State("aid-select", "value"),
#         self_data=State("df-table", "data"),
#         self_selrows=State("df-table", "selected_rows"),
#         self_style=State("df-table", "style_data_conditional")),
# )
# def update_table(
#     selections, jsonified_db_data, xymap_view, aid_select, self_data, self_selrows, self_style
# ):
    
#     print("TABLE callback")
#     processed_data, prop_id = selection_helper(selections)
    
#     if prop_id is None:
#         #selected_index = []
#         return self_data, self_selrows, self_style

#     # Read data from session memory
#     df = pd.read_json(jsonified_db_data[0], orient='split')
    
#     #If no group is loaded then return empty dataframe
#     if len(df) == 0:
#         selected_index = []
#         return dfe.to_dict('records'), selected_index, get_style_data_conditional(selected_index)

#     #Add clickable links
#     df['designation'] = '['+df['designation'].values+'](https://mocadb.ca/search/results?search-query='+np_f.replace(np_f.replace(df['designation'].values.astype("U")," ","%20"),"+","%2B")+'&search-type=star)'
#     df['moca_aid'] = '['+df['moca_aid'].values+'](https://mocadb.ca/search/results?search-query='+np_f.replace(df['moca_aid'].values.astype("U")," ","%20")+'&search-type=association)'

#     df_sorted = df
#     df_sorted['num_moca_mtid'] = df_sorted['moca_mtid']
    
#     #This could probably be done better with the moca_membership_types table
#     df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"BF","1.BF")
#     df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"HM","2.HM")
#     df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"CM","3.CM")
#     df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"LM","4.LM")
#     df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"AM","5.AM")
#     df_sorted['num_moca_mtid'] = np_f.replace(df_sorted['num_moca_mtid'].values.astype("U"),"R","6.R")
#     df_sorted = df_sorted.sort_values(by=['moca_aid', 'num_moca_mtid', 'spt'])

#     if processed_data is None:
#         selected_index = []
#         df_out = df_sorted
#     else:
#         df_selected_indices = df_sorted['moca_oid'].isin(processed_data)
#         selected_index = np.where(df_selected_indices)[0]
#         df_out = pd.concat([df_sorted[df_selected_indices],df_sorted[~df_selected_indices]])
#         #If we sort the table the selected indices are the first ones
#         selected_index = list(range(len(selected_index)))

#     table_data_style_conditional = get_style_data_conditional(selected_index)

#     return df_out.to_dict('records'), selected_index, table_data_style_conditional


# Eventually move this to a subroutine if possible
# Update AID- and MTID-select
@dash.callback(
    output=[
        Output("db-data-xyzpage","data"),
        Output("aid-select-xyzpage","options"),
        Output("aid-select-xyzpage","value"),
        Output("mtid-select-xyzpage","value"),
        Output("oid-select-xyzpage","value"),
        ],
    inputs=[
        Input("aid-select-xyzpage", "value"),
        Input("mtid-select-xyzpage", "value"),
        Input("oid-select-xyzpage", "value"),
    ],
    state=[State("url","search")]
)
def update_aid_select_xyzpage(
    aid_select, mtid_select, oid_select, url_search
):
    
    print("DBQUERY callback-xyzpage")
    
    # Read default associations from URL if none are selected
    # Example query type '?asso=THA,COL&mtid=BF,HM,CM'
    user = None
    pwd = None
    dbase = None
    if aid_select is None:
        #Default values without URL variables
        if url_search == "":
            aid_select = initial_aids
            mtid_select = initial_mtids
        else:
            parsed_url = urlparse(url_search)
            parsed_url_data = parse_qs(parsed_url.query)
            if 'user' in parsed_url_data.keys():
                user = parsed_url_data['user'][0]
            if 'pwd' in parsed_url_data.keys():
                pwd = parsed_url_data['pwd'][0]
            if 'dbase' in parsed_url_data.keys():
                dbase = parsed_url_data['dbase'][0]
            if 'asso' in parsed_url_data.keys():
                aid_select = parsed_url_data['asso'][0].split(',')
            else:
                if aid_select is None:
                    aid_select = initial_aids
            if 'mtid' in parsed_url_data.keys():
                mtid_select = parsed_url_data['mtid'][0].split(',')
            else:
                if mtid_select is None:
                    mtid_select = initial_mtids
            #OID is always a string in the input box so do not already split it into an array
            if 'oid' in parsed_url_data.keys():
                oid_select = parsed_url_data['oid'][0]

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
    df_aids = moca.query("SELECT moca_aid FROM moca_associations")
    aid_options=[
        {"label": dcc.Link(children=i ,href="https://mocadb.ca/search/results?search-query="+i+"&search-type=association"), "value": i}
        #{"label": i, "value": i}
        for i in df_aids["moca_aid"].unique().tolist()
    ]

    #Prevent app from crashing if no associations are selected
    if len(aid_select) == 0:
        df = dfe
        dfm = dfme
    else: 
        # Query the moca database to obtain a Pandas DataFrame for the specific group needed
        aid_query = " OR ".join(["moca_aid='"+stri+"'" for stri in aid_select])
        mtid_query = " OR ".join(["moca_mtid = '"+stri+"'" for stri in mtid_select])
        df = moca.query("SELECT "+", ".join(df_columns+df_columns_memonly)+" FROM summary_all_members WHERE ("+mtid_query+") AND ("+aid_query+")")
        df['gr'] = df['gmag']-df['rmag']
        df['br'] = df['bmag']-df['rmag']
        df['m_g'] = df['gmag']-5.0*(np.log10(1000.0/df['plx'].values.astype('float64'))-1)
        df['m_r'] = df['rmag']-5.0*(np.log10(1000.0/df['plx'].values.astype('float64'))-1)

        # Query the moca database to obtain a Pandas DataFrame of the appropriate BANYAN Sigma models
        dfm = moca.query("SELECT dbs.* FROM moca_banyan_sigma_models mbs LEFT JOIN data_banyan_sigma_models dbs USING(moca_bsmdid) WHERE mbs.adopted=1 AND ("+aid_query+")")

    #Object-based selections
    oid_set = False
    if oid_select is not None:
        if len(oid_select) != 0:
            oid_set = True
    
    if not oid_set:
        dfo = dfoe
    else:
        # Query the moca database to obtain a Pandas DataFrame for the specific group needed
        oid_query = " OR ".join(["moca_oid='"+stri+"'" for stri in oid_select.split(',')])
        dfo = moca.query("SELECT "+", ".join(df_columns)+" FROM summary_all_objects WHERE ("+oid_query+")")
        dfo['gr'] = dfo['gmag']-dfo['rmag']
        dfo['br'] = dfo['bmag']-dfo['rmag']
        dfo['m_g'] = dfo['gmag']-5.0*(np.log10(1000.0/dfo['plx'].values.astype('float64'))-1)
        dfo['m_r'] = dfo['rmag']-5.0*(np.log10(1000.0/dfo['plx'].values.astype('float64'))-1)

    df_asso_centers = moca.query("CALL list_association_labels();")
    print("Downloaded "+str(len(df))+" rows of general data from DB")
    print("Downloaded "+str(len(dfo))+" rows of general object-based data from DB")

    return (
        df.to_json(date_format='iso', orient='split'),
        dfm.to_json(date_format='iso', orient='split'),
        dfo.to_json(date_format='iso', orient='split'),
        df_asso_centers.to_json(date_format='iso', orient='split'),
        ), aid_options, aid_select, mtid_select, oid_select

# Update XYZ Map
@dash.callback(
    output=Output("xyz-map-xyzpage", "figure"),
    inputs=dict(
        #selections=selections,
        jsonified_db_data=Input("db-data-xyzpage", "data"),
        xymap_view=Input("xymap-view-selector-xyzpage", "value"),
        #hover_select=Input("hover-select-xyzpage", "value"),
        #recenter=Input("xyz-recenter-in-xyzpage", "n_clicks"),
        #zoom_out=Input("xyz-zoom-out-xyzpage", "n_clicks"),
        #zoom_in=Input("xyz-zoom-in-xyzpage", "n_clicks"),
    ),
    state=dict(aid_select=State("aid-select-xyzpage", "value"), self_figure=State("xyz-map-xyzpage", "figure")),
)
def update_xyz_map_xyzpage(
    #selections, 
    jsonified_db_data, xymap_view
    #, recenter
    , aid_select, self_figure
):
    
    print("XYZ callback-xyzpage")
    #zoom_out_level = zoom_out - zoom_in

    processed_data, prop_id = selection_helper(selections)
    if prop_id is None:
       return self_figure
    if prop_id == "xyz-map-xyzpage":
        return self_figure
    if prop_id == "xyz-recenter-in-xyzpage":
        print("DO RECENTER HERE")

    df = pd.read_json(jsonified_db_data[0], orient='split')
    dfm = pd.read_json(jsonified_db_data[1], orient='split')
    dfo = pd.read_json(jsonified_db_data[2], orient='split')
    df_asso_centers = pd.read_json(jsonified_db_data[3], orient='split')
    #import pdb; pdb.set_trace()

    return generate_xyz_map_xyzpage(df, dfm, dfo, df_asso_centers, aid_select, 'x', 'y', 'z', 'X (pc)', 'Y (pc)', 'Z (pc)', 'XYZ Galactic coordinates', processed_data, xymap_view, self_figure)

# # Update UVW Map
# @dash.callback(
#     output=Output("uvw-map-xyzpage", "figure"),
#     inputs=dict(
#         #selections=selections,
#         jsonified_db_data=Input("db-data-xyzpage", "data"),
#         xymap_view=Input("xymap-view-selector-xyzpage", "value"),
#         #hover_select=Input("hover-select-xyzpage", "value"),
#         #zoom_out=Input("uvw-zoom-out-xyzpage", "n_clicks"),
#         #zoom_in=Input("uvw-zoom-in-xyzpage", "n_clicks"),
#     ),
#     state=dict(aid_select=State("aid-select-xyzpage", "value"), self_figure=State("uvw-map-xyzpage", "figure")),
# )
# def update_uvw_map_xyzpage(
#     #selections, 
#     jsonified_db_data, xymap_view, aid_select, self_figure
# ):
#     return None
    # print("UVW callback-xyzpage")
    # zoom_out_level = zoom_out - zoom_in

    # processed_data, prop_id = selection_helper(selections)
    # if prop_id is None:
    #    return self_figure
    # if prop_id == "uvw-map-xyzpage":
    #     return self_figure
    # df = pd.read_json(jsonified_db_data[0], orient='split')
    # dfm = pd.read_json(jsonified_db_data[1], orient='split')
    # dfo = pd.read_json(jsonified_db_data[2], orient='split')
    # return generate_xyz_map_xyzpage(df, dfm, dfo, aid_select, 'u', 'v', 'w', 'U (km/s)', 'V (km/s)', 'W (km/s)', 'UVW Galactic space velocities', processed_data, xymap_view, self_figure)

