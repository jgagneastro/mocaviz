import dash
from dash import html, dcc, dash_table, get_asset_url
from urllib.parse import urlparse, parse_qs
from sqlalchemy import create_engine
from urllib.parse import quote_plus as urlquote

from utils.plot_banyan_model_helpers import build_ellipsoid_3d, build_solar_neighborhood_3d, build_graph_title, build_gmm_density_3d

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

rv_range = np.linspace(-50, 50, 50)  # Define 50 radial velocity values from -50 to +50 km/s

# Load data
moca_vanilla = MocaEngine()

c_value = 8.0

query_e = f"""
    SELECT mo.designation, mv.moca_aid, mv.moca_mtid, cspt.spectral_type AS spt, dr3.RUWE AS dr3_ruwe, mv.moca_oid, xyz.x_pc AS x, xyz.y_pc AS y, xyz.z_pc AS z, 
    xyz.xx_covar, xyz.yy_covar, xyz.zz_covar, 
    xyz.xy_covar, xyz.xz_covar, xyz.yz_covar,
    uvw.uu_covar, uvw.vv_covar, uvw.ww_covar,
    uvw.uv_covar, uvw.uw_covar, uvw.vw_covar,
    uvw.xu_covar, uvw.xv_covar, uvw.xw_covar,
    uvw.yu_covar, uvw.yv_covar, uvw.yw_covar,
    uvw.zu_covar, uvw.zv_covar, uvw.zw_covar,
    {c_value} * COALESCE(uvw.u_kms,uvwany.u_kms) AS u, {c_value} * COALESCE(uvw.v_kms,uvwany.v_kms) AS v, {c_value} * COALESCE(uvw.w_kms,uvwany.w_kms) AS w, 
    cbsd.x_opt, cbsd.y_opt, cbsd.z_opt, 
    {c_value} * cbsd.u_opt u_opt, {c_value} * cbsd.v_opt v_opt, {c_value} * cbsd.w_opt w_opt
    FROM mechanics_memberships_vetted mv
    LEFT JOIN calc_uvw uvw USING(moca_oid,moca_aid)
    LEFT JOIN calc_xyz xyz USING(moca_oid)
    LEFT JOIN moca_objects mo USING(moca_oid)
    LEFT JOIN cat_gaiadr3 dr3 USING(moca_oid)
    LEFT JOIN data_spectral_types cspt ON(cspt.moca_oid=mv.moca_oid AND cspt.adopted=1)
    LEFT JOIN calc_uvw uvwany ON(uvwany.moca_oid=mv.moca_oid AND uvwany.moca_aid IS NULL)
    LEFT JOIN (SELECT cbs.id, cbs.moca_oid, cbs.max_observables, cbs.moca_bsmdid FROM calc_banyan_sigma cbs JOIN moca_banyan_sigma_models mbsm USING(moca_bsmdid) WHERE mbsm.adopted = 1) cbs ON cbs.moca_oid = mv.moca_oid AND cbs.max_observables = 1
    LEFT JOIN calc_banyan_sigma_details cbsd ON(cbs.id=cbsd.cbs_id AND cbsd.moca_aid=mv.moca_aid)
"""

#This is just the same query as above but with a constraint YA_PROB >= 90
query_e_most_likely_mode = f"""
    SELECT mo.designation, mv.moca_aid, mv.moca_mtid, cspt.spectral_type AS spt, dr3.RUWE AS dr3_ruwe, mv.moca_oid, xyz.x_pc AS x, xyz.y_pc AS y, xyz.z_pc AS z, 
    xyz.xx_covar, xyz.yy_covar, xyz.zz_covar, 
    xyz.xy_covar, xyz.xz_covar, xyz.yz_covar,
    uvw.uu_covar, uvw.vv_covar, uvw.ww_covar,
    uvw.uv_covar, uvw.uw_covar, uvw.vw_covar,
    uvw.xu_covar, uvw.xv_covar, uvw.xw_covar,
    uvw.yu_covar, uvw.yv_covar, uvw.yw_covar,
    uvw.zu_covar, uvw.zv_covar, uvw.zw_covar,
    {c_value} * COALESCE(uvw.u_kms,uvwany.u_kms) AS u, {c_value} * COALESCE(uvw.v_kms,uvwany.v_kms) AS v, {c_value} * COALESCE(uvw.w_kms,uvwany.w_kms) AS w, 
    cbsd.x_opt, cbsd.y_opt, cbsd.z_opt, 
    {c_value} * cbsd.u_opt u_opt, {c_value} * cbsd.v_opt v_opt, {c_value} * cbsd.w_opt w_opt
    FROM mechanics_memberships_vetted mv
    LEFT JOIN calc_uvw uvw USING(moca_oid,moca_aid)
    LEFT JOIN calc_xyz xyz USING(moca_oid)
    LEFT JOIN moca_objects mo USING(moca_oid)
    LEFT JOIN cat_gaiadr3 dr3 USING(moca_oid)
    LEFT JOIN data_spectral_types cspt ON(cspt.moca_oid=mv.moca_oid AND cspt.adopted=1)
    LEFT JOIN calc_uvw uvwany ON(uvwany.moca_oid=mv.moca_oid AND uvwany.moca_aid IS NULL)
    LEFT JOIN calc_banyan_sigma cbs ON(cbs.moca_oid=mv.moca_oid AND cbs.max_observables=1 AND cbs.ya_prob >= 90 AND cbs.moca_bsmdid=(SELECT mbsm.moca_bsmdid FROM moca_banyan_sigma_models mbsm WHERE mbsm.adopted=1))
    LEFT JOIN calc_banyan_sigma_details cbsd ON(cbs.id=cbsd.cbs_id AND cbsd.moca_aid=mv.moca_aid)
"""
# This is a query that models what happens when the user selects a specific moca_oid to be displayed. By default
#  it is set to LIMIT 0 but when a user selects a moca_oid the limit is removed and a filter on the moca_oid is set.
query_oe = f"""
    SELECT mo.designation, COALESCE(mv.moca_aid,'N/A') AS moca_aid, 'N/A' AS moca_mtid, cspt.spectral_type AS spt, dr3.RUWE AS dr3_ruwe, mo.moca_oid, xyz.x_pc AS x, xyz.y_pc AS y, xyz.z_pc AS z,
    {c_value} * uvw.u_kms AS u, {c_value} * uvw.v_kms AS v, {c_value} * uvw.w_kms AS w,
    mo.ra, mo.`dec`,dpm.pmra_masyr,dpm.pmdec_masyr,cdist.distance_pc,crvc.radial_velocity_kms
    FROM moca_objects mo
    LEFT JOIN calc_banyan_sigma_best mv USING(moca_oid)
    LEFT JOIN calc_xyz xyz USING(moca_oid)
    LEFT JOIN calc_uvw_raw uvw USING(moca_oid)
    LEFT JOIN calc_radial_velocities_corrected crvc USING(moca_oid,moca_aid)
    LEFT JOIN cat_gaiadr3 dr3 USING(moca_oid)
    LEFT JOIN data_spectral_types cspt ON(cspt.moca_oid=mv.moca_oid AND cspt.adopted=1)
    LEFT JOIN data_distances cdist ON(cdist.moca_oid=mo.moca_oid AND cdist.adopted=1)
    LEFT JOIN data_proper_motions dpm ON(dpm.moca_oid=mo.moca_oid AND dpm.adopted=1)
"""

dfe = moca_vanilla.query(query_e+" LIMIT 0")
dfoe = moca_vanilla.query(query_oe+" LIMIT 0")
dfme = moca_vanilla.query("SELECT dbs.* FROM moca_banyan_sigma_models mbs LEFT JOIN data_banyan_sigma_models dbs USING(moca_bsmdid) WHERE mbs.adopted=1 LIMIT 0")

unselected_opacity = 0.1
selected_opacity = 1

# Load a list of all associations for the Dropdown menu
#TMP FIX BELOW
df_mtids = moca_vanilla.query("SELECT moca_mtid, name, description FROM (SELECT * FROM (SELECT mt.* FROM moca_membership_types mt JOIN (SELECT DISTINCT moca_mtid FROM mocadb.summary_all_members) dm ON(dm.moca_mtid=mt.moca_mtid)) oq) oq2 ORDER BY level DESC")

text_mtids = ("* **"+df_mtids["moca_mtid"]+"**: "+df_mtids["description"]).values.astype("U").tolist()

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
        children=[
            html.H2("MOCA SPATIAL-KINEMATIC EXPLORER"),
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

# Define the correct order of axes
axis_order = ["x", "y", "z", "u", "v", "w"]

# Function to get the correct covariance name based on custom order
def get_covar_name(axis1, axis2):
    """Returns the covariance column name with axes sorted according to xyzuvw order."""
    sorted_axes = sorted([axis1, axis2], key=lambda axis: axis_order.index(axis))
    return f"{sorted_axes[0]}{sorted_axes[1]}_covar"

# Function to apply scaling only if the variable is u, v, or w
def scale_offset(axis, value):
    return value * c_value if axis in ["u", "v", "w"] else value

# Function to determine scaling factor for covariance matrix elements
def scale_covar(axis1, axis2, value):
    spatial_axes = ["x", "y", "z"]
    kinematic_axes = ["u", "v", "w"]

    if axis1 in kinematic_axes and axis2 in kinematic_axes:
        return value * (c_value ** 2)  # Both are kinematic → multiply by c_value²
    elif (axis1 in spatial_axes and axis2 in kinematic_axes) or (axis1 in kinematic_axes and axis2 in spatial_axes):
        return value * c_value  # One spatial, one kinematic → multiply by c_value
    else:
        return value  # Both are spatial → no change
    
# Eventually move this to a subroutine
def generate_xyzuvw_map(dff, dfm, dfo, df_asso_centers, associations, xvar, yvar, zvar, xtitle, ytitle, ztitle, title, selected_data, style, self_figure, plot_errors=False):

    # Read layer properties
    models_visible = assume_membership = show_asso_centers = True
    hover = "closest"
    if "models" not in style:
        models_visible = False
    if "assmem" not in style:
        assume_membership = False
    if "asscen" not in style:
        show_asso_centers = False
    if "hover" not in style:
        hover = False
    
    max_pc_range = 2e3

    # Compute median position of all stars
    median_x = np.nan_to_num(np.nanmedian(dff[xvar].values), nan=0.0)
    median_y = np.nan_to_num(np.nanmedian(dff[yvar].values), nan=0.0)
    median_z = np.nan_to_num(np.nanmedian(dff[zvar].values), nan=0.0)

    # Check if the range exceeds max_pc_range
    if (
        median_x > max_pc_range/3 or
        median_y > max_pc_range/3 or
        median_z > max_pc_range/3
    ):
        # Recenter the plot on the median position
        center_x, center_y, center_z = median_x, median_y, median_z
        title = f"Centered on ({center_x:.1f}, {center_y:.1f}, {center_z:.1f})"
    else:
        # Keep the Sun at the center
        center_x, center_y, center_z = 0, 0, 0
        title = "Centered on the Sun"

    # Compute max range across all axes to enforce 1:1:1 aspect ratio
    max_extent = max(
        abs(dff[xvar] - center_x).max(),
        abs(dff[yvar] - center_y).max(),
        abs(dff[zvar] - center_z).max()
    )

    # Ensure max_extent does not exceed max_pc_range
    max_extent = min(max_extent, max_pc_range)

    # Mask stars outside the determined plotting range
    dff.loc[(dff[xvar] < center_x - max_extent) | (dff[xvar] > center_x + max_extent), xvar] = np.nan
    dff.loc[(dff[yvar] < center_y - max_extent) | (dff[yvar] > center_y + max_extent), yvar] = np.nan
    dff.loc[(dff[zvar] < center_z - max_extent) | (dff[zvar] > center_z + max_extent), zvar] = np.nan

    xvar_orig = xvar
    yvar_orig = yvar
    zvar_orig = zvar
    if assume_membership:
        xvar += "_opt"
        yvar += "_opt"
        zvar += "_opt"

    layout = go.Layout(
        height=850,
        uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        hovermode=hover,
        paper_bgcolor=bcg_color,#
        plot_bgcolor=bcg_color,
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
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

        # Lists to store valid points and errors
        error_x, error_y, error_z = [], [], []

        # Compute error bars
        if dff_select is not None and plot_errors is True:
            for _, row in dff_select.iterrows():
                x, y, z = row[xvar], row[yvar], row[zvar]

                # Skip if x, y, or z is NaN
                if np.isnan(x) or np.isnan(y) or np.isnan(z):
                    continue

                covar_matrix = np.array([
                    [row.get(f"{xvar}{xvar}_covar", 0), row.get(get_covar_name(xvar, yvar), 0), row.get(get_covar_name(xvar, zvar), 0)],
                    [row.get(get_covar_name(yvar, xvar), 0), row.get(f"{yvar}{yvar}_covar", 0), row.get(get_covar_name(yvar, zvar), 0)],
                    [row.get(get_covar_name(zvar, xvar), 0), row.get(get_covar_name(zvar, yvar), 0), row.get(f"{zvar}{zvar}_covar", 0)]
                ])

                # Skip iteration if any element in covar_matrix is NaN
                if np.isnan(covar_matrix).any():
                    continue

                # Compute Eigenvalues & Eigenvectors (More Stable Than SVD)
                try:
                    eigvals, eigvecs = np.linalg.eigh(covar_matrix)  # eigvecs = rotation matrix, eigvals = variances
                except np.linalg.LinAlgError:
                    continue  # Skip this star if decomposition fails

                # Generate Scaled Principal Axes
                principal_axes = eigvecs @ (np.sqrt(np.abs(eigvals)) * np.eye(3))

                # Store error bars (each axis separately, using NaN as a separator)
                for i in range(3):
                    error_x.extend([x - principal_axes[0, i], x + principal_axes[0, i], np.nan])
                    error_y.extend([y - principal_axes[1, i], y + principal_axes[1, i], np.nan])
                    error_z.extend([z - principal_axes[2, i], z + principal_axes[2, i], np.nan])
            
            # Single trace for all error bars
            error_trace = go.Scatter3d(
                x=error_x,
                y=error_y,
                z=error_z,
                mode="lines",
                line=dict(color=colormap[association], width=4),  # Slightly thicker lines
                opacity=0.2,  # Keep error bars semi-transparent
                showlegend=False,
            )
            data.append(error_trace)

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
            
            # Initialize the components list
            components = []
            
            for index, dfm_row in dfm_aid.iterrows():

                # Apply scaling selectively
                offset = np.array([
                    scale_offset(xvar_orig, dfm_row[xvar_orig + "_cen"]),
                    scale_offset(yvar_orig, dfm_row[yvar_orig + "_cen"]),
                    scale_offset(zvar_orig, dfm_row[zvar_orig + "_cen"])
                ])
                # Build the covariance matrix with scaling applied
                covar_matrix = np.array([
                    [
                        scale_covar(xvar_orig, xvar_orig, dfm_row[get_covar_name(xvar_orig, xvar_orig)]),
                        scale_covar(xvar_orig, yvar_orig, dfm_row[get_covar_name(xvar_orig, yvar_orig)]),
                        scale_covar(xvar_orig, zvar_orig, dfm_row[get_covar_name(xvar_orig, zvar_orig)])
                    ],
                    [
                        scale_covar(yvar_orig, xvar_orig, dfm_row[get_covar_name(yvar_orig, xvar_orig)]),
                        scale_covar(yvar_orig, yvar_orig, dfm_row[get_covar_name(yvar_orig, yvar_orig)]),
                        scale_covar(yvar_orig, zvar_orig, dfm_row[get_covar_name(yvar_orig, zvar_orig)])
                    ],
                    [
                        scale_covar(zvar_orig, xvar_orig, dfm_row[get_covar_name(zvar_orig, xvar_orig)]),
                        scale_covar(zvar_orig, yvar_orig, dfm_row[get_covar_name(zvar_orig, yvar_orig)]),
                        scale_covar(zvar_orig, zvar_orig, dfm_row[get_covar_name(zvar_orig, zvar_orig)])
                    ]
                ])

                # Extract amplitude (weight), defaulting to 1.0 if None
                weight = dfm_row["coeff_amplitude"]
                if pd.isna(weight):  # Handle None or NaN values
                    weight = 1.0
                
                # Append to components list
                components.append({
                    "weight": weight,
                    "mean": offset,
                    "cov": covar_matrix
                })

            # Plot the GMM model
            if len(components) != 0:
                modelname = association+" model"
                model = build_gmm_density_3d(components, colormap[association], contour_level=0.99, opacity=0.07, mesh=False, showlegend=True, legendgroup=modelname, legendname=modelname+' (99%)')
                data.extend(model)
                model = build_gmm_density_3d(components, colormap[association], contour_level=0.95, opacity=0.15, mesh=False, showlegend=True, legendgroup=modelname, legendname=modelname+' (95%)')
                data.extend(model)
                model = build_gmm_density_3d(components, colormap[association], contour_level=0.68, opacity=0.3, mesh=False, showlegend=True, legendgroup=modelname, legendname=modelname+' (68%)')
                data.extend(model)
    
    if len(dfo) != 0:
        text_list = build_hover_dfo(dfo)
        obj_color = "black"
        for index, row in dfo.iterrows():
            # Check if any coordinate is missing
            if pd.isna(row[xvar_orig]) or pd.isna(row[yvar_orig]) or pd.isna(row[zvar_orig]):
                
                # Extract necessary values from the row
                ra = row["ra"]
                dec = row["dec"]
                pmra = row["pmra_masyr"]
                pmdec = row["pmdec_masyr"]
                distance = row["distance_pc"]

                # Compute U, V, W for the given radial velocity range
                U_line, V_line, W_line = equatorial_UVW(ra, dec, pmra, pmdec, rv_range, distance)
                
                # Map UVW to the correct axes based on the user's selection
                # Generalized mapping function for each axis
                def map_axis(var_orig, static_value):
                    if var_orig == "u":
                        return U_line*c_value
                    elif var_orig == "v":
                        return V_line*c_value
                    elif var_orig == "w":
                        return W_line*c_value
                    else:
                        return np.full_like(rv_range, static_value)  # Repeat known static value

                # Map the selected axes correctly
                x_line = map_axis(xvar_orig, row[xvar_orig])
                y_line = map_axis(yvar_orig, row[yvar_orig])
                z_line = map_axis(zvar_orig, row[zvar_orig])

                # Append the line trace
                data.append(
                    go.Scatter3d(
                        x=x_line,
                        y=y_line,
                        z=z_line,
                        mode="lines",
                        line=dict(color=obj_color, width=5),
                        name=row['designation']+" (Unknown RV)"
                    )
                )
            else:
                # Normal point display for objects with complete data
                data.append(
                    go.Scatter3d(
                        x=[row[xvar_orig]],
                        y=[row[yvar_orig]],
                        z=[row[zvar_orig]],
                        mode="markers",
                        marker={"color": obj_color, "size": 8, "symbol": "diamond"},
                        text=text_list[index],
                        name=row['designation']
                    )
                )

    # Plot the Solar neighborhood reference
    sn = build_solar_neighborhood_3d(center=(center_x, center_y, center_z))
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

    fig = go.Figure(data=data,layout=layout)

    # Apply the same range to all axes for a 1:1:1 aspect ratio
    fig.update_scenes(
        xaxis={"range": [center_x - max_extent, center_x + max_extent], "title": xtitle},
        yaxis={"range": [center_y - max_extent, center_y + max_extent], "title": ytitle},
        zaxis={"range": [center_z - max_extent, center_z + max_extent], "title": ztitle},
    )

    # Try to force aspect ratio (does not always work)
    fig.update_scenes(aspectmode='data')

    # Define new center for camera rotation
    camera_center = dict(x=center_x, y=center_y, z=center_z)

    # Adjust the camera eye position relative to the new center
    eye_pos_xyz = [center_x + 500, center_y + 500, center_z + 500]  # Adjust as needed

    # Calculate relative eye position for consistent aspect ratio
    eye_pos_xrel = (eye_pos_xyz[0] - center_x) / max_extent * 2
    eye_pos_yrel = (eye_pos_xyz[1] - center_y) / max_extent * 2
    eye_pos_zrel = (eye_pos_xyz[2] - center_z) / max_extent * 2

    # Update camera dictionary
    camera = dict(
        up=dict(x=0, y=0, z=1),
        center=dict(x=0, y=0, z=0),  # Keep relative to the figure
        eye=dict(x=eye_pos_xrel, y=eye_pos_yrel, z=eye_pos_zrel),
    )

    # Apply new camera settings
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
    
    fig.add_annotation(
        x=1,
        y=1,
        xref="x domain",
        yref="y domain",
        text=title,
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
        dcc.Location(id='url', refresh=False),
        html.Div(
            id="top-row-xupage",
            children=[
                html.Div(
                    className="row",
                    id="top-row-header-xupage",
                    children=[
                        html.Div(
                            id="header-container-xupage",
                            children=[
                                build_banner(),
                            ],
                        ),
                        dcc.Store(id='db-data-xupage'),
                    ],
                ),
            ],
        ),
        html.Div(
            className="row",
            id="first-data-row-xupage",
            children=[
                html.Div(className="two columns",
                    children=[
                        html.Br(),
                        html.Br(),
                        html.Br(),
                        dcc.Markdown(children=["Select axes"]),
                        html.Div(
                            className="row",
                            id="axis-selection-container-xupage",
                            children=[
                                html.Div(
                                    className="row",
                                    children=[
                                        dcc.Dropdown(
                                            id="axis-1-dropdown-xupage",
                                            options=[{"label": i, "value": i} for i in ["X", "Y", "Z", "U", "V", "W"]],
                                            clearable=False,
                                            style={"width": "100%"}
                                        )
                                    ],
                                ),
                                html.Div(
                                    className="row",
                                    children=[
                                        dcc.Dropdown(
                                            id="axis-2-dropdown-xupage",
                                            options=[{"label": i, "value": i} for i in ["X", "Y", "Z", "U", "V", "W"]],
                                            clearable=False,
                                            style={"width": "100%"}
                                        )
                                    ],
                                ),
                                html.Div(
                                    className="row",
                                    children=[
                                        dcc.Dropdown(
                                            id="axis-3-dropdown-xupage",
                                            options=[{"label": i, "value": i} for i in ["X", "Y", "Z", "U", "V", "W"]],
                                            clearable=False,
                                            style={"width": "100%"}
                                        )
                                    ],
                                ),
                            ],
                            style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"white"},
                        ),
                        html.Br(),
                        dcc.Markdown(children=["Select stellar associations"]),
                        dcc.Dropdown(
                            id="aid-select-xupage",
                            multi=True,
                            value=None,
                            style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"white"},
                            ),
                        html.Br(),
                        dcc.Markdown(children=["Select membership types"]),
                        dcc.Dropdown(
                            id="mtid-select-xupage",
                            options=[
                                {"label": " "+i, "value": i}
                                for i in df_mtids["moca_mtid"].unique().tolist()
                            ],
                            multi=True,
                            value=None,
                            style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"white"},
                        ),
                        html.Br(),
                        dcc.Markdown(children=["Select individual stars"]),
                        dcc.Input(id="oid-select-xupage", type="text", placeholder="Insert MOCA object IDs separated by commas.", debounce=True, style={"width": "100%", "whiteSpace": "pre-wrap"}),
                        html.Br(),
                        html.Br(),
                        dcc.Markdown(children=["Select BANYAN model version"]),
                        dcc.Dropdown(
                            id="banyan-model-version-xupage",
                            options=[{"label": "Latest available", "value": "latest"}],  # Will be dynamically updated
                            value="latest",
                            style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor": "white"},
                            ),
                        html.Br(),
                        ],
                    ),
                # XYZ
                html.Div(
                    id="xyz-container-xupage",
                    className="eight columns",
                    children=[
                        dcc.Graph(id="xyz-map-xupage",config=figure_export_config),
                    ],
                ),
                html.Div(className="two columns",
                    children=[
                        html.Br(),
                        html.Br(),
                        html.Br(),
                        dcc.Checklist(
                                    id="xymap-view-selector-xupage",
                                    options=[
                                        {
                                            "label": "BANYAN Models",
                                            "value": "models",
                                        },
                                        {
                                            "label": "Show Object Errors",
                                            "value": "errors",
                                        },
                                        {
                                            "label": "Assume Membership",
                                            "value": "assmem",
                                        },
                                        {
                                            "label": "Enable Hover Properties",
                                            "value": "hover",
                                        },
                                        {
                                            "label": "Only Display Likely Members",
                                            "value": "likely",
                                        },
                                        {
                                            "label": "All Labels (slow load)",
                                            "value": "asscen",
                                        },
                                    ],
                                    value=[]
                                ),
                    ],
                ),
            ],
        ),
    html.Div(
        className="row",
        id="url-help-section-xupage",
        children=[
            html.Hr(),
            dcc.Markdown(
                """
                ## Using URL Parameters

                You can customize the visualization by adding parameters to the URL.  
                Use `?param=value` format and separate multiple parameters with `&`.

                ### Available URL Parameters  
                - `axes=xuw` → Sets the displayed axes to **X, U, W**.
                - `asso=THA,COL` → Selects the **THA** and **COL** associations.
                - `mtid=BF,HM,CM` → Filters by membership types **BF, HM, CM**.
                - `oid=12345,67890` → Highlights individual objects by MOCA OID.
                - `bsmdid=16` → Selects a specific **BANYAN Σ model version** by `moca_bsmdid`. Use `bsmdid=latest` to keep the default **latest available version**.
                - `checkbox=models,errors,hover,assmem,likely,asscen` → Enables various display options.  

                ### Checkbox Options (`checkbox=` parameter)
                - `models` → Displays **BANYAN models**.  
                - `errors` → Shows **error bars for objects**.  
                - `hover` → Enables **hover properties** (additional tooltips).  
                - `assmem` → Uses **assumed membership positions** for objects.  
                - `likely` → Filters to show **only likely members**.  
                - `asscen` → Displays **all association labels** (may slow down loading). 

                ### Example URLs  
                - `https://dataviz.mocadb.ca/xyzuvw?axes=xuw&asso=THA,COL`
                - `https://dataviz.mocadb.ca/xyzuvw?mtid=BF,HM&oid=12345,67890`
                - `https://dataviz.mocadb.ca/xyzuvw?bsmdid=16` → Uses **BANYAN Σ model version 16**.  
                - `https://dataviz.mocadb.ca/xyzuvw?asso=THA,COL&bsmdid=latest` → Uses **latest model version** for selected associations.
                
                Note that you can also click on an individual star to open its MOCAdb report in a separate tab of you allow for popups in your browser.
                """
            ),
        ],
        style={"padding": "20px", "backgroundColor": "#f9f9f9"}
    ),
    dcc.Store(id='clicked-moca-oid-xupage'),  # Stores clicked MOCA OID
    html.Div(id='dummy-output-xupage'),  # Needed for the client-side callback
    ]
)

selections = {
        }

@dash.callback(
    output=[
        Output("axis-1-dropdown-xupage", "value"),
        Output("axis-2-dropdown-xupage", "value"),
        Output("axis-3-dropdown-xupage", "value"),
    ],
    inputs=[Input("url", "search")]
)
def update_axes_from_url_xupage(url_search):
    """Extract axis selections from the URL and update dropdown values."""
    if url_search:
        parsed_url = urlparse(url_search)
        parsed_url_data = parse_qs(parsed_url.query)

        if 'axes' in parsed_url_data:
            axes = list(parsed_url_data['axes'][0])  # Convert "xuw" into ["x", "u", "w"]
            if len(axes) == 3:
                return axes[0].upper(), axes[1].upper(), axes[2].upper()

    # Default values if no valid URL parameter
    return "X", "Y", "Z"

# Update checkboxes from URL
@dash.callback(
    Output("xymap-view-selector-xupage", "value"),
    Input("url", "search")
)
def update_checklist_from_url(url_search):
    """Extract checkbox states from the URL and update the checklist component."""
    default_checkboxes = ["models", "errors"]  # Default values

    if url_search:
        parsed_url = urlparse(url_search)
        parsed_url_data = parse_qs(parsed_url.query)

        if "checkbox" in parsed_url_data:
            return parsed_url_data["checkbox"][0].split(",")  # Use URL values

    return default_checkboxes  # Use defaults if no parameter is found

# Update BSMDID dropdown from URL and read credentials
@dash.callback(
    [Output("banyan-model-version-xupage", "options"),
     Output("banyan-model-version-xupage", "value")],
    Input("url", "search"),
)
def update_banyan_version_dropdown(url_search):
    # Initialize MOCA engine
    moca = MocaEngine()

    # Extract credentials from URL
    user, pwd, dbase = None, None, None
    if url_search:
        parsed_url = urlparse(url_search)
        parsed_url_data = parse_qs(parsed_url.query)
        user = parsed_url_data.get("user", [None])[0]
        pwd = parsed_url_data.get("pwd", [None])[0]
        dbase = parsed_url_data.get("dbase", [None])[0]

    # If credentials are provided, override connection
    if user and pwd and dbase:
        engine = create_engine('mysql+pymysql://'+user+':'+urlquote(pwd)+'@104.248.106.21/'+dbase)
        moca.connection = engine.connect()

    # Query available model versions
    df_model_versions = moca.query("SELECT DISTINCT moca_bsmdid FROM data_banyan_sigma_models")

    # Generate dropdown options
    model_options = [{"label": "Latest available", "value": "latest"}] + [
        {"label": str(i), "value": str(i)} for i in sorted(df_model_versions["moca_bsmdid"].tolist(), reverse=True)
    ]

    # Determine selected version from URL
    selected_version = "latest"  # Default value
    if url_search and "bsmdid" in parsed_url_data:
        url_bsmdid = parsed_url_data["bsmdid"][0]
        available_versions = [opt["value"] for opt in model_options]
        if url_bsmdid in available_versions:
            selected_version = url_bsmdid

    return model_options, selected_version

# Update AID- and MTID-select
@dash.callback(
    output=[
        Output("db-data-xupage","data"),
        Output("aid-select-xupage","options"),
        Output("aid-select-xupage","value"),
        Output("mtid-select-xupage","value"),
        Output("oid-select-xupage","value"),
        ],
    inputs=[
        Input("aid-select-xupage", "value"),
        Input("mtid-select-xupage", "value"),
        Input("oid-select-xupage", "value"),
        Input("xymap-view-selector-xupage", "value"),
        Input("banyan-model-version-xupage", "value"),
    ],
    state=[State("url","search")]
)
def update_aid_select_xupage(
    aid_select, mtid_select, oid_select, xymap_view, banyan_version, url_search
):
    
    # Determine if the "Only Display Likely Members" checkbox is checked
    if "likely" in xymap_view:
        query_e_modified = query_e_most_likely_mode
    else:
        query_e_modified = query_e  # Use the default query

    # Read default associations from URL if none are selected
    # Example query type '?asso=THA,COL&mtid=BF,HM,CM'
    if aid_select is None:
        #Default values without URL variables
        if url_search == "":
            aid_select = initial_aids
            mtid_select = initial_mtids
        else:
            parsed_url = urlparse(url_search)
            parsed_url_data = parse_qs(parsed_url.query)
            if 'asso' in parsed_url_data.keys():
                aid_select = parsed_url_data['asso'][0].split(',')
            else:
                if aid_select is None:
                    aid_select = initial_aids
            aid_select = list(set(aid_select))  # Remove duplicates
            if 'mtid' in parsed_url_data.keys():
                mtid_select = parsed_url_data['mtid'][0].split(',')
            else:
                if mtid_select is None:
                    mtid_select = initial_mtids
            #OID is always a string in the input box so do not already split it into an array
            if 'oid' in parsed_url_data.keys():
                oid_select = parsed_url_data['oid'][0]

    # Read credentials
    user = None
    pwd = None
    dbase = None
    if url_search:
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
        engine = create_engine('mysql+pymysql://'+user+':'+urlquote(pwd)+'@104.248.106.21/'+dbase)

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
    if len(aid_select) == 0 or not mtid_select:
        df = dfe
        dfm = dfme
    else: 
        # Query the moca database to obtain a Pandas DataFrame for the specific group needed
        aid_query = " OR ".join(["mv.moca_aid='"+stri+"'" for stri in aid_select])
        mtid_query = " OR ".join(["mv.moca_mtid = '"+stri+"'" for stri in mtid_select])
        df = moca.query(query_e_modified+" WHERE ("+mtid_query+") AND ("+aid_query+")")

        # Query the moca database to obtain a Pandas DataFrame of the appropriate BANYAN Sigma models
        aid_query = " OR ".join(["moca_aid='"+stri+"'" for stri in aid_select])
        
        
        # BANYAN model query
        if banyan_version == "latest":
            # This version is flexible AND preserves multi-ellipse models when we need the latest version
            dfm = moca.query(
                "SELECT dbs2.* FROM data_banyan_sigma_models dbs2 "
                "JOIN (SELECT MAX(dbs.moca_bsmdid) AS moca_bsmdid, moca_aid "
                "FROM data_banyan_sigma_models dbs WHERE (" + aid_query + ") "
                "GROUP BY dbs.moca_aid) inq USING(moca_aid, moca_bsmdid)"
            )
        else:
            dfm = moca.query(
                "SELECT dbs2.* FROM data_banyan_sigma_models dbs2 "
                "WHERE (" + aid_query + ") AND moca_bsmdid=" + str(banyan_version)
            )

        # This version is flexible AND preserves multi-ellipse models
        #dfm = moca.query("SELECT dbs2.* FROM  data_banyan_sigma_models dbs2 JOIN (SELECT MAX(dbs.moca_bsmdid) AS moca_bsmdid, moca_aid FROM data_banyan_sigma_models dbs WHERE ("+aid_query+") GROUP BY dbs.moca_aid) inq USING(moca_aid, moca_bsmdid)")
        #dfm = moca.query("SELECT dbs2.* FROM  data_banyan_sigma_models dbs2 WHERE ("+aid_query+") AND moca_bsmdid="+str([insert the user-selected bsmdid here]))

    #Object-based selections
    oid_set = False
    if oid_select is not None:
        if len(oid_select) != 0:
            oid_set = True
    
    if not oid_set:
        dfo = dfoe
    else:
        # Query the moca database to obtain a Pandas DataFrame for the specific group needed
        oid_query = " OR ".join(["mo.moca_oid='"+stri+"'" for stri in oid_select.split(',')])
        dfo = moca.query(query_oe+" WHERE ("+oid_query+")")

    df_asso_centers = moca.query("CALL list_association_labels();")
    return (
        df.to_json(date_format='iso', orient='split'),
        dfm.to_json(date_format='iso', orient='split'),
        dfo.to_json(date_format='iso', orient='split'),
        df_asso_centers.to_json(date_format='iso', orient='split'),
        ), aid_options, aid_select, mtid_select, oid_select

def get_axis_unit(axis):
    return "km/s" if axis in ["U", "V", "W"] else "pc"

# Update XYZUVW Map
@dash.callback(
    output=Output("xyz-map-xupage", "figure"),
    inputs=dict(
        jsonified_db_data=Input("db-data-xupage", "data"),
        xymap_view=Input("xymap-view-selector-xupage", "value"),
        axis_1=Input("axis-1-dropdown-xupage", "value"),
        axis_2=Input("axis-2-dropdown-xupage", "value"),
        axis_3=Input("axis-3-dropdown-xupage", "value"),
    ),
    state=dict(aid_select=State("aid-select-xupage", "value"), self_figure=State("xyz-map-xupage", "figure")),
)
def update_map_xupage(
    #selections, 
    jsonified_db_data, xymap_view,
    axis_1, axis_2, axis_3,
    #, recenter
    aid_select, self_figure
):
    
    # Check if axes are distinct
    if len(set([axis_1, axis_2, axis_3])) < 3:
        return go.Figure(
            layout=go.Layout(
                height=400,
                annotations=[
                    dict(
                        text="Please select distinct axes",
                        x=0.5, y=0.5,
                        xref="paper", yref="paper",
                        showarrow=False,
                        font=dict(size=20, color="red")
                    )
                ]
            )
        )
    
    processed_data, prop_id = selection_helper(selections)
    if prop_id is None:
       return self_figure
    if prop_id == "xyz-map-xupage":
        return self_figure
    if prop_id == "xyz-recenter-in-xupage":
        print("DO RECENTER HERE")
    
    df = pd.read_json(jsonified_db_data[0], orient='split')
    dfm = pd.read_json(jsonified_db_data[1], orient='split')
    dfo = pd.read_json(jsonified_db_data[2], orient='split')
    df_asso_centers = pd.read_json(jsonified_db_data[3], orient='split')

    # Validate associations
    valid_aids = list(set(df["moca_aid"].unique()) | set(dfm["moca_aid"].unique()))
    filtered_aid_select = [aid for aid in aid_select if aid in valid_aids]
    invalid_aids = [aid for aid in aid_select if aid not in valid_aids]

    # If all requested associations are invalid, return an error message
    if not filtered_aid_select:
        return go.Figure(
            layout=go.Layout(
                height=400,
                annotations=[
                    dict(
                        text=f"No data to be displayed.",
                        x=0.5, y=0.5,
                        xref="paper", yref="paper",
                        showarrow=False,
                        font=dict(size=20, color="red")
                    )
                ]
            )
        )
    
    plot_errors = "errors" in xymap_view

    if df.empty and dfm.empty:
        return go.Figure(
            layout=go.Layout(
                height=400,
                annotations=[
                    dict(
                        text="No valid stars or models found for the selected criteria.",
                        x=0.5, y=0.5,
                        xref="paper", yref="paper",
                        showarrow=False,
                        font=dict(size=20, color="red")
                    )
                ]
            )
        )

    return generate_xyzuvw_map(df, dfm, dfo, df_asso_centers, filtered_aid_select, axis_1.lower(), axis_2.lower(), axis_3.lower(), axis_1.upper(), axis_2.upper(), axis_3.upper(), f'{axis_1}{axis_2}{axis_3} Galactic coordinates', processed_data, xymap_view, self_figure, plot_errors=plot_errors)

#Initiate some global constants
#1 AU/yr to km/s divided by 1000
kappa = 0.004743717361
#Not using "from astropy import units as u; kappa=u.au.to(u.km)/u.year.to(u.s)" because astropy defines one year as exactly 365.25 days instead of 365 days

#J2000.0 Equatorial position of the Galactic North (b=90 degrees) from Carrol and Ostlie
ra_pol = 192.8595
dec_pol = 27.12825

#J2000.0 Galactic latitude gb of the Celestial North pole (dec=90 degrees) from Carrol and Ostlie
l_north = 122.932

#Galactic Coordinates matrix
TGAL = (np.array([[-0.0548755604, -0.8734370902, -0.4838350155],
	[0.4941094279, -0.4448296300, 0.7469822445],
	[-0.8676661490,  -0.1980763734, 0.4559837762]]))

def equatorial_UVW(ra,dec,pmra,pmdec,rv,dist,pmra_error=None,pmdec_error=None,rv_error=None,dist_error=None):
	"""
	Transforms equatorial coordinates (ra,dec), proper motion (pmra,pmdec), radial velocity and distance to space velocities UVW. All inputs must be numpy arrays of the same dimension.
	
	param ra: Right ascension (degrees)
	param dec: Declination (degrees)
	param pmra: Proper motion in right ascension (milliarcsecond per year). 	Must include the cos(delta) term
	param pmdec: Proper motion in declination (milliarcsecond per year)
	param rv: Radial velocity (kilometers per second)
	param dist: Distance (parsec)
	param ra_error: Error on right ascension (degrees)
	param dec_error: Error on declination (degrees)
	param pmra_error: Error on proper motion in right ascension (milliarcsecond per year)
	param pmdec_error: Error on proper motion in declination (milliarcsecond per year)
	param rv_error: Error on radial velocity (kilometers per second)
	param dist_error: Error on distance (parsec)
	
	output (U,V,W): Tuple containing Space velocities UVW (kilometers per second)
	output (U,V,W,EU,EV,EW): Tuple containing Space velocities UVW and their measurement errors, used if any measurement errors are given as inputs (kilometers per second)
	"""
	
	#Verify keywords
	num_stars = np.size(ra)
	if np.size(dec) != num_stars or np.size(pmra) != num_stars or np.size(pmdec) != num_stars or np.size(dist) != num_stars:
		raise ValueError('ra, dec, pmra, pmdec, rv and distance must all be numpy arrays of the same size !')
	if pmra_error is not None and np.size(pmra_error) != num_stars:
		raise ValueError('pmra_error must be a numpy array of the same size as ra !')
	if pmdec_error is not None and np.size(pmdec_error) != num_stars:
		raise ValueError('pmdec_error must be a numpy array of the same size as ra !')
	if rv_error is not None and np.size(rv_error) != num_stars:
		raise ValueError('rv_error must be a numpy array of the same size as ra !')
	if dist_error is not None and np.size(dist_error) != num_stars:
		raise ValueError('dist_error must be a numpy array of the same size as ra !')
	
	#Compute elements of the T matrix
	cos_ra = np.cos(np.radians(ra))
	cos_dec = np.cos(np.radians(dec))
	sin_ra = np.sin(np.radians(ra))
	sin_dec = np.sin(np.radians(dec))
	T1 = TGAL[0,0]*cos_ra*cos_dec + TGAL[0,1]*sin_ra*cos_dec + TGAL[0,2]*sin_dec
	T2 = -TGAL[0,0]*sin_ra + TGAL[0,1]*cos_ra
	T3 = -TGAL[0,0]*cos_ra*sin_dec - TGAL[0,1]*sin_ra*sin_dec + TGAL[0,2]*cos_dec
	T4 = TGAL[1,0]*cos_ra*cos_dec + TGAL[1,1]*sin_ra*cos_dec + TGAL[1,2]*sin_dec
	T5 = -TGAL[1,0]*sin_ra + TGAL[1,1]*cos_ra
	T6 = -TGAL[1,0]*cos_ra*sin_dec - TGAL[1,1]*sin_ra*sin_dec + TGAL[1,2]*cos_dec
	T7 = TGAL[2,0]*cos_ra*cos_dec + TGAL[2,1]*sin_ra*cos_dec + TGAL[2,2]*sin_dec
	T8 = -TGAL[2,0]*sin_ra + TGAL[2,1]*cos_ra
	T9 = -TGAL[2,0]*cos_ra*sin_dec - TGAL[2,1]*sin_ra*sin_dec + TGAL[2,2]*cos_dec
	
	#Calculate UVW
	reduced_dist = kappa*dist
	U = T1*rv + T2*pmra*reduced_dist + T3*pmdec*reduced_dist
	V = T4*rv + T5*pmra*reduced_dist + T6*pmdec*reduced_dist
	W = T7*rv + T8*pmra*reduced_dist + T9*pmdec*reduced_dist
	
	#Return only (U, V, W) tuple if no errors are set
	if pmra_error is None and pmdec_error is None and rv_error is None and dist_error is None:
		return (U, V, W)
		
	#Propagate errors if they are specified
	if pmra_error is None:
		pmra_error = np.zeros(num_stars)
	if pmdec_error is None:
		pmdec_error = np.zeros(num_stars)
	if rv_error is None:
		rv_error = np.zeros(num_stars)
	if dist_error is None:
		dist_error = np.zeros(num_stars)
	reduced_dist_error = kappa*dist_error
	
	#Calculate derivatives
	T23_pm = np.sqrt((T2*pmra)**2+(T3*pmdec)**2)
	T23_pm_error = np.sqrt((T2*pmra_error)**2+(T3*pmdec_error)**2)
	EU_rv = T1 * rv_error
	EU_pm = T23_pm_error * reduced_dist
	EU_dist = T23_pm * reduced_dist_error
	EU_dist_pm = T23_pm_error * reduced_dist_error
	
	T56_pm = np.sqrt((T5*pmra)**2+(T6*pmdec)**2)
	T56_pm_error = np.sqrt((T5*pmra_error)**2+(T6*pmdec_error)**2)
	EV_rv = T4 * rv_error
	EV_pm = T56_pm_error * reduced_dist
	EV_dist = T56_pm * reduced_dist_error
	EV_dist_pm = T56_pm_error * reduced_dist_error

	T89_pm = np.sqrt((T8*pmra)**2+(T9*pmdec)**2)
	T89_pm_error = np.sqrt((T8*pmra_error)**2+(T9*pmdec_error)**2)
	EW_rv = T7 * rv_error
	EW_pm = T89_pm_error * reduced_dist
	EW_dist = T89_pm * reduced_dist_error
	EW_dist_pm = T89_pm_error * reduced_dist_error
	
	#Calculate error bars
	EU = np.sqrt(EU_rv**2 + EU_pm**2 + EU_dist**2 + EU_dist_pm**2)
	EV = np.sqrt(EV_rv**2 + EV_pm**2 + EV_dist**2 + EV_dist_pm**2)
	EW = np.sqrt(EW_rv**2 + EW_pm**2 + EW_dist**2 + EW_dist_pm**2)
	
	#Return measurements and error bars
	return (U, V, W, EU, EV, EW)

@dash.callback(
    Output('clicked-moca-oid-xupage', 'data'),
    Input('xyz-map-xupage', 'clickData')
)
def store_clicked_moca_oid_xupage(clickData):
    if clickData and 'points' in clickData:
        point = clickData['points'][0]  # First clicked point
        if 'customdata' in point:
            return point['customdata']  # Extract `moca_oid`
    return dash.no_update  # Do nothing if no valid data is found

dash.clientside_callback(
    """
    function(moca_oid) {
        if (moca_oid) {
            window.open('https://mocadb.ca/search/results?search-query=oid%28' + moca_oid + '%29&search-type=star', '_blank');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('dummy-output-xupage', 'children'),  # Dummy output (not used)
    Input('clicked-moca-oid-xupage', 'data')
)