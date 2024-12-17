import dash
from math import floor, log10
import numpy as np
import decimal
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objs as go
from urllib.parse import quote_plus as urlquote, urlparse, parse_qs
from sqlalchemy import create_engine, select, MetaData, Table, func, and_, cast, String
import pandas as pd
import os
from utils.plx_motion import parallax_motion

# Register the page in the Dash app
dash.register_page(__name__)

# Placeholder for the database connection string
connection_string = None

def format_value_with_error(value, error, unit):
    """
    Formats a value with its error, displaying only one significant digit for the error.
    If the value or error is None, it returns "N/A".
    """
    if pd.isna(value) or pd.isna(error) or value == "N/A" or error == "N/A":
        return "N/A"
    
    # Calculate the significant digit for the error
    error_magnitude = 10 ** floor(log10(abs(error)))
    rounded_error = round(error / error_magnitude) * error_magnitude
    rounded_value = round(value, -int(floor(log10(abs(rounded_error)))))

    # Format the result with ± symbol and unit
    return f"{rounded_value} ± {rounded_error}" + (f" {unit}" if rounded_value else "")

def wrap_text(text, width=50):
    """Wraps text with line breaks every 'width' characters."""
    if not text:  # Handles None or empty string
        return ""
    return '<br>'.join([text[i:i+width] for i in range(0, len(text), width)])

# Define the initial layout of the page
# Layout
layout = html.Div([
    dcc.Location(id="url", refresh=False),
    html.Div([
        html.H1("Astrometric explorer"),
        html.P("This page allows to compare the individual-epoch astrometry of MOCAdb entries "
               " with their best-available proper motion and parallax solutions."
               ),
    ], style={'width': '100%', 'display': 'inline-block'}),
    
    dcc.Dropdown(
        id="astrometry-dataset-dropdown",
        options=[],  # Initially empty, will be populated via callback
        placeholder="Select a MOCA Object",
        style={
            'color': 'white !important',
            'width': '100%',
            'minWidth': '300px',
            'fontSize': '16px'
        },
    ),

    html.Div([
        dcc.Checklist(
            id="subtract-pm-checkbox",
            options=[{'label': 'Subtract proper motion', 'value': 'subtract_pm'}],
            value=[],
            inline=True,
            style={'margin-bottom': '10px', 'font-size': '16px'}
        ),
        dcc.Checklist(
            id="subtract-plx-checkbox",
            options=[{'label': 'Subtract parallax motion', 'value': 'subtract_plx'}],
            value=[],
            inline=True,
            style={'margin-bottom': '10px', 'font-size': '16px'}
        ),
        dcc.Checklist(
            id="phase-yr-checkbox",
            options=[{'label': 'Phase yearly', 'value': 'phase'}],
            value=[],
            inline=True,
            style={'margin-bottom': '10px', 'font-size': '16px'}
        ),
        dcc.Checklist(
            id="adjust-reference-epoch-checkbox",
            options=[{'label': 'Adjust reference epoch', 'value': 'adjust_ref'}],
            value=[],
            inline=True,
            style={'margin-bottom': '10px', 'font-size': '16px'}
        ),
        html.Div([
            dcc.Graph(id="astrometry-plot-ra"),
        ], style={'width': '100%', 'display': 'inline-block', 'margin-bottom': '20px'}),
        html.Div([
            dcc.Graph(id="astrometry-plot-dec"),
        ], style={'width': '100%', 'display': 'inline-block'}),
    ], style={'width': '65%', 'display': 'inline-block'}),

], style={'padding-left': '15px'})

# Callback to populate the dropdown and initialize connection based on URL parameters
@dash.callback(
    output=[
        Output("astrometry-dataset-dropdown", "options"),
        Output("astrometry-dataset-dropdown", "value"),
        #Output("url", "search"),  # This triggers the callback once the options are set
    ],
    inputs=[Input("url", "href")],
    state=[State("url", "search")]
)
def update_dropdown(href, url_search):
    # Parse URL parameters
    parsed_url = urlparse(url_search)
    parsed_url_data = parse_qs(parsed_url.query)
    
    env_username = parsed_url_data.get('user', [None])[0]
    env_password = parsed_url_data.get('pwd', [None])[0]
    env_dbname = parsed_url_data.get('dbase', [None])[0]

    default_host = '104.248.106.21'
    default_username = 'public'
    default_password = 'z@nUg_2h7_%?31y88'
    default_dbname = 'mocadb'
    
    if env_username is None:
        env_username = os.environ.get('MOCA_USERNAME', default_username)
    if env_password is None:
        env_password = os.environ.get('MOCA_PASSWORD', default_password)
    if env_dbname is None:
        env_dbname = os.environ.get('MOCA_DBNAME', default_dbname)
    env_host = os.environ.get('MOCA_HOST', default_host)

    if env_username is None:
        return dash.no_update
    if env_password is None:
        return dash.no_update
    if env_dbname is None:
        return dash.no_update

    global connection_string
    connection_string = f'mysql+pymysql://{env_username}:{urlquote(env_password)}@{env_host}/{env_dbname}'

    # Establish connection to the database
    engine = create_engine(connection_string)
    connection = engine.connect()
    metadata = MetaData()

    # Reflect the moca_objects table
    moca_objects = Table('moca_objects', metadata, autoload_with=engine)

    # Reflect the cdata_spectral_types table
    cdata_spectral_types = Table('cdata_spectral_types', metadata, autoload_with=engine)

    # Query to get unique dataset identifiers with join and filters
    query_unique_datasets = (
        select(
            (cast(moca_objects.c.moca_oid, String) + '|' + moca_objects.c.designation).label('dataset_identifier')
        )
        .select_from(
            moca_objects.join(
                cdata_spectral_types,
                moca_objects.c.moca_oid == cdata_spectral_types.c.moca_oid
            )
        )
        .where(
            and_(
                cdata_spectral_types.c.adopted == 1,
                cdata_spectral_types.c.spectral_type_number >= 10,
                cdata_spectral_types.c.photometric_estimate == 0
            )
        )
    )

    # Execute the query
    unique_datasets = pd.read_sql(query_unique_datasets, connection)

    # Get the unique identifiers as a list
    dataset_options = unique_datasets['dataset_identifier'].tolist()
    
    # Close the connection
    connection.close()

    # Set the first option as default if available
        # Check for moca_oid in the URL query parameters
    moca_oid_param = parsed_url_data.get('moca_oid', [None])[0]

    # Set default value based on moca_oid if provided
    if moca_oid_param:
        default_value = next(
            (dataset for dataset in dataset_options if dataset.startswith(f'{moca_oid_param}|')),
            None
        )
    else:
        # Fallback: set the first available option as default
        default_value = next(
            (dataset for dataset in dataset_options if dataset.startswith('602|')),
            dataset_options[0] if dataset_options else None
        )

    return [{"label": dataset, "value": dataset} for dataset in dataset_options], default_value#, url_search

# Define the callback to update the scatter plot based on input
@dash.callback(
    [Output("astrometry-plot-ra", "figure"),
     Output("astrometry-plot-dec", "figure")],
    [Input("astrometry-dataset-dropdown", "value"),
     Input("subtract-pm-checkbox", "value"),
     Input("subtract-plx-checkbox", "value"),
     Input("phase-yr-checkbox", "value"),
     Input("adjust-reference-epoch-checkbox", "value"),
     Input("astrometry-plot-ra", "selectedData"),
     Input("astrometry-plot-dec", "selectedData")],
     prevent_initial_call=True,
)
def update_scatter_plot(selected_dataset, pm_checkbox_values, plx_checkbox_values, phase_checkbox_values, adjust_ref_checkbox_values, selectedData_ra, selectedData_dec):
    ctx = dash.callback_context
    
    if not selected_dataset:
        return dash.no_update, dash.no_update
    
    subtract_pm = 'subtract_pm' in pm_checkbox_values  # Check if the checkbox is selected
    subtract_plx = 'subtract_plx' in plx_checkbox_values  # Check if the checkbox is selected
    phase_yearly = 'phase' in phase_checkbox_values  # Check if the checkbox is selected
    adjust_reference_epoch = 'adjust_ref' in adjust_ref_checkbox_values  # Check if the checkbox is selected

    triggered_prop = ctx.triggered[0]["prop_id"]

    triggered_by_selection = ('selectedData_ra' in ctx.triggered[0]['prop_id']) or ('selectedData_dec' in ctx.triggered[0]['prop_id'])

    if triggered_by_selection and ((selectedData_ra is None and selectedData_dec is None) or (not selectedData_ra.get('points') and not selectedData_dec.get('points'))):
        return dash.no_update, dash.no_update
    
    try:
        moca_oid, designation = selected_dataset.split('|')
    except ValueError:
        return dash.no_update, dash.no_update

    engine = create_engine(connection_string)
    connection = engine.connect()
    metadata = MetaData()

    #Query combined coordinates
    calc_equatorial_coordinates_combined = Table('calc_equatorial_coordinates_combined', metadata, autoload_with=engine)

    query = select(calc_equatorial_coordinates_combined.c.ra,
                   calc_equatorial_coordinates_combined.c.dec,
                   calc_equatorial_coordinates_combined.c.position_epoch_yr
                   ).where(
        (calc_equatorial_coordinates_combined.c.moca_oid == moca_oid)
    )
    ref_df = pd.read_sql(query, connection)
    ra_ref, dec_ref, epoch_ref = ref_df.iloc[0]["ra"], ref_df.iloc[0]["dec"], ref_df.iloc[0]["position_epoch_yr"]

    #Query PM
    data_proper_motions = Table('data_proper_motions', metadata, autoload_with=engine)

    query = select(data_proper_motions.c.pmra_masyr,
                   data_proper_motions.c.pmdec_masyr,
                   data_proper_motions.c.pmra_masyr_unc,
                   data_proper_motions.c.pmdec_masyr_unc,
                   ).where(
        (data_proper_motions.c.moca_oid == moca_oid)
    ).limit(1)
    pm_df = pd.read_sql(query, connection)
    
    #Query PLX
    data_parallaxes = Table('data_parallaxes', metadata, autoload_with=engine)

    query = select(data_parallaxes.c.parallax_mas,
                   data_parallaxes.c.parallax_mas_unc,
                   ).where(
        (data_parallaxes.c.moca_oid == moca_oid)
    ).limit(1)
    plx_df = pd.read_sql(query, connection)

    # Extract proper motion and parallax values
    # Extract proper motion and parallax values with errors
    if len(pm_df) != 0:
        pmra_display = format_value_with_error(pm_df.iloc[0]["pmra_masyr"], pm_df.iloc[0]["pmra_masyr_unc"], "mas/yr")
        pmdec_display = format_value_with_error(pm_df.iloc[0]["pmdec_masyr"], pm_df.iloc[0]["pmdec_masyr_unc"], "mas/yr")
    else:
        pmra_display, pmdec_display = "N/A", "N/A"

    if len(plx_df) != 0:
        parallax_display = format_value_with_error(plx_df.iloc[0]["parallax_mas"], plx_df.iloc[0]["parallax_mas_unc"], "mas")
    else:
        parallax_display = "N/A"

    #Query all coordinates
    data_equatorial_coordinates = Table('data_equatorial_coordinates', metadata, autoload_with=engine)

    query = select(data_equatorial_coordinates.c.id,
                    data_equatorial_coordinates.c.ra,
                    data_equatorial_coordinates.c.dec,
                    data_equatorial_coordinates.c.measurement_epoch_yr,
                    data_equatorial_coordinates.c.ra_unc_mas,
                    data_equatorial_coordinates.c.dec_unc_mas,
                    func.coalesce(data_equatorial_coordinates.c.measurement_epoch_yr_unc, 0).label('measurement_epoch_yr_unc'),
                    func.coalesce(
                        func.coalesce(
                            func.concat(data_equatorial_coordinates.c.mission_name, ' ', data_equatorial_coordinates.c.data_release),
                            data_equatorial_coordinates.c.moca_pid
                        ),
                        'other'
                    ).label('mission'),
                   data_equatorial_coordinates.c.moca_pid,
                   data_equatorial_coordinates.c.mission_name,
                   data_equatorial_coordinates.c.data_release,
                   data_equatorial_coordinates.c.origin,
                   data_equatorial_coordinates.c.comments,
                   data_equatorial_coordinates.c.airmass,
                   data_equatorial_coordinates.c.moca_psid,
                   ).where(
        ((data_equatorial_coordinates.c.moca_oid == moca_oid) & 
         (data_equatorial_coordinates.c.adopted == 1) &
         (data_equatorial_coordinates.c.single_epoch == 1))
    )
    data_df = pd.read_sql(query, connection)
    connection.close()

    if adjust_reference_epoch:
        epochs = data_df["measurement_epoch_yr"].values
        epoch_ref = np.nanmean(epochs)
        rel_ra_observed = (data_df["ra"]) * np.cos(np.radians(data_df["dec"])) * 3600 * 1000
        rel_dec_observed = (data_df["dec"]) * 3600 * 1000

        if len(pm_df) != 0:
            rel_ra_observed -= (epochs - epoch_ref) * pm_df.iloc[0]["pmra_masyr"]
            rel_dec_observed -= (epochs - epoch_ref) * pm_df.iloc[0]["pmdec_masyr"]

        if len(plx_df) != 0:
            plxm = parallax_motion(np.nanmean(data_df["ra"]), np.nanmean(data_df["dec"]), epochs)
            rel_ra_observed -= plxm["plx_motion_racosdec"]*plx_df.iloc[0]["parallax_mas"]
            rel_dec_observed -= plxm["plx_motion_dec"]*plx_df.iloc[0]["parallax_mas"]
        
        ra_ref = np.nanmedian(rel_ra_observed/(np.cos(np.radians(data_df["dec"])) * 3600 * 1000))
        dec_ref = np.nanmedian(rel_dec_observed/(3600 * 1000))
    
    # Calculate relative offsets
    data_df["rel_ra"] = (data_df["ra"] - ra_ref) * np.cos(np.radians(dec_ref)) * 3600 * 1000
    data_df["rel_dec"] = (data_df["dec"] - dec_ref) * 3600 * 1000

    # Subtract proper motion if checkbox is checked
    if subtract_pm and len(pm_df) != 0:
        pmra = pm_df.iloc[0]["pmra_masyr"]
        pmdec = pm_df.iloc[0]["pmdec_masyr"]
        epochs = data_df["measurement_epoch_yr"].values

        data_df["rel_ra"] -= (epochs - epoch_ref) * pmra
        data_df["rel_dec"] -= (epochs - epoch_ref) * pmdec
    
    if subtract_plx and len(plx_df) != 0:
        epochs = data_df["measurement_epoch_yr"].values
        plxm = parallax_motion(ra_ref, dec_ref, epochs)
        data_df["rel_ra"] -= plxm["plx_motion_racosdec"]*plx_df.iloc[0]["parallax_mas"]
        data_df["rel_dec"] -= plxm["plx_motion_dec"]*plx_df.iloc[0]["parallax_mas"]

    # Assign a unique color to each mission
    unique_missions = data_df['mission'].unique()
    mission_color_map = {mission: i for i, mission in enumerate(unique_missions)}
    data_df["mission_color"] = data_df["mission"].map(mission_color_map)

    # Handle selection propagation
    if triggered_prop == "astrometry-plot-ra.selectedData" and selectedData_ra:
        selected_indices = [point["pointIndex"] for point in selectedData_ra["points"]]
    elif triggered_prop == "astrometry-plot-dec.selectedData" and selectedData_dec:
        selected_indices = [point["pointIndex"] for point in selectedData_dec["points"]]
    else:
        selected_indices = list(data_df.index)

    fig_ra = go.Figure()
    fig_dec = go.Figure()

    if phase_yearly:
        data_df["x_values"] = np.mod(data_df["measurement_epoch_yr"], 1)  # Phase yearly
        xaxis_title = "Yearly Phase (0 = Jan 1st, 1 = Dec 31st)"
    else:
        data_df["x_values"] = data_df["measurement_epoch_yr"]  # Original epochs
        xaxis_title = "Epoch (Year)"  # Default x-axis title

    #Plot the proper motion
    # Extract the full x-axis range from the figure (start and end)
    #xaxis_range = [data_df["measurement_epoch_yr"].min(), data_df["measurement_epoch_yr"].max()]
    data_min = data_df["x_values"].min()
    data_max = data_df["x_values"].max()

    # Add 5% padding
    padding = (data_max - data_min) * 0.05
    xaxis_range = [data_min - padding, data_max + padding]

    # Generate 5000 evenly spaced points across the x-axis range
    ntimep = 5000
    time_values = np.linspace(xaxis_range[0], xaxis_range[1], ntimep)

    if subtract_pm or len(pm_df) == 0:
        expected_rel_ra = np.zeros_like(time_values)
        expected_rel_dec = np.zeros_like(time_values)
    else:
        if phase_yearly:
            expected_rel_ra = (time_values+np.round(np.mean(data_df["measurement_epoch_yr"])) - epoch_ref) * pm_df.iloc[0]["pmra_masyr"]
            expected_rel_dec = (time_values+np.round(np.mean(data_df["measurement_epoch_yr"])) - epoch_ref) * pm_df.iloc[0]["pmdec_masyr"]
        else:
            expected_rel_ra = (time_values - epoch_ref) * pm_df.iloc[0]["pmra_masyr"]
            expected_rel_dec = (time_values - epoch_ref) * pm_df.iloc[0]["pmdec_masyr"]
    
    if not subtract_plx and len(plx_df) != 0:
        if phase_yearly:
            plxm = parallax_motion(ra_ref, dec_ref, time_values+np.round(np.mean(data_df["measurement_epoch_yr"])))
        else:    
            plxm = parallax_motion(ra_ref, dec_ref, time_values)
        expected_rel_ra += plxm["plx_motion_racosdec"]*plx_df.iloc[0]["parallax_mas"]
        expected_rel_dec += plxm["plx_motion_dec"]*plx_df.iloc[0]["parallax_mas"]

    # Add line to RA figure
    fig_ra.add_trace(go.Scatter(
        x=time_values,
        y=expected_rel_ra,
        mode="lines",
        line=dict(color='rgba(100, 150, 250, 0.6)', width=4),  # Semi-transparent gray line
        name="MOCAdb solution",
        hoverinfo='skip'
    ))

    # Add line to DEC figure
    fig_dec.add_trace(go.Scatter(
        x=time_values,
        y=expected_rel_dec,
        mode="lines",
        line=dict(color='rgba(100, 150, 250, 0.6)', width=4),  # Semi-transparent gray line
        name="MOCAdb solution",
        hoverinfo='skip'
    ))

    data_df['rel_ra_str'] = data_df['rel_ra'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['rel_dec_str'] = data_df['rel_dec'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['ra_unc_mas_str'] = data_df['ra_unc_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['dec_unc_mas_str'] = data_df['dec_unc_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['ra_str'] = data_df['ra'].apply(lambda x: f"{x:.6f}" if pd.notna(x) else "N/A")
    data_df['dec_str'] = data_df['dec'].apply(lambda x: f"{x:.6f}" if pd.notna(x) else "N/A")
    data_df['measurement_epoch_yr_str'] = data_df['measurement_epoch_yr'].apply(lambda x: f"{x:.4f}" if pd.notna(x) else "N/A")
    data_df['id_str'] = data_df['id'].apply(lambda x: f"{int(x):d}" if pd.notna(x) else "N/A")
    data_df['airmass_str'] = data_df['airmass'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    
    for mission in unique_missions:
        mission_data = data_df[data_df["mission"] == mission]
        fig_ra.add_trace(go.Scatter(
            x=mission_data["x_values"],
            y=mission_data["rel_ra"],
            mode='markers',
            error_y=dict(
                type='data',
                array=data_df['ra_unc_mas'],
                visible=True,
                color='rgba(0, 0, 0, 0.2)',  
                thickness=1.5,               
                width=2                  
            ),
            marker=dict(
                color=mission_color_map[mission],  # Use the assigned color for this mission
                size=8,
                symbol='circle',
                line=dict(width=2, color='black')
            ),
            name=mission,  # This will appear in the legend
            customdata=mission_data['id'],
            text=mission_data.apply(
                lambda row: 
                    f"<b>ID:</b> {row['id_str']}<br>" \
                    f"<b>Mission:</b> {row['mission'] or 'N/A'}<br>" \
                    f"<b>Relative R.A.:</b> {row['rel_ra_str']} ± {row['ra_unc_mas_str']} mas<br>" \
                    f"<b>Relative Decl.:</b> {row['rel_dec_str']} ± {row['dec_unc_mas_str']} mas<br>" \
                    f"<b>RA:</b> {row['ra_str']} deg<br>" \
                    f"<b>DEC:</b> {row['dec_str']} deg<br>" \
                    f"<b>Epoch:</b> {row['measurement_epoch_yr_str']} yr<br>" \
                    f"<b>Reference:</b> {row['moca_pid'] or 'N/A'}<br>" \
                    f"<b>Origin:</b> {row['origin'] or 'N/A'}<br>" \
                    f"<b>Airmass:</b> {row['airmass_str']}<br>" \
                    f"<b>Bandpass:</b> {row['moca_psid'] or 'N/A'}<br>" \
                    f"<b>Comments:</b> {wrap_text(row['comments'] or '', width=50)}",
                axis=1
            ),
            hoverinfo='text'
        ))

    # Update layout for better legend positioning
    fig_ra.update_layout(
        plot_bgcolor='white',
        xaxis_title=xaxis_title, yaxis_title="RA Offset (mas)",
        xaxis=dict(
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        yaxis=dict(
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        margin=dict(l=40, r=40, t=40, b=40),
        paper_bgcolor='white',
        showlegend=True,
        legend=dict(
             title=dict(
                text="<b> Missions</b>",  # Make the title bold
                font=dict(size=14)  # Optional: adjust font size
            ),
            #x=0.02, y=0.98,  # Adjust legend position as needed
            bgcolor='rgba(255, 255, 255, 0.5)',  # Optional: semi-transparent background
            bordercolor='black',
            borderwidth=1
        ),
        annotations=[
            dict(
                xref="paper", yref="paper",
                x=0.5, y=1.12,  # Position above the graph
                text=f"<b>PMRA:</b> {pmra_display} | <b>PMDEC:</b> {pmdec_display} | <b>Parallax:</b> {parallax_display}",
                showarrow=False,
                font=dict(size=14, color="black"),
                align="center"
            )
        ]
    )

    for mission in unique_missions:
        mission_data = data_df[data_df["mission"] == mission]
        fig_dec.add_trace(go.Scatter(
            x=mission_data["x_values"],
            y=mission_data["rel_dec"],
            mode='markers',
            error_y=dict(
                type='data',
                array=data_df['dec_unc_mas'],
                visible=True,
                color='rgba(0, 0, 0, 0.2)',  
                thickness=1.5,               
                width=2                  
            ),
            marker=dict(
                color=mission_color_map[mission],  # Use the assigned color for this mission
                size=8,
                symbol='circle',
                line=dict(width=2, color='black')
            ),
            name=mission,  # This will appear in the legend
            customdata=mission_data['id'],
            text=mission_data.apply(
                lambda row: 
                    f"<b>ID:</b> {row['id_str']}<br>" \
                    f"<b>Mission:</b> {row['mission'] or 'N/A'}<br>" \
                    f"<b>Relative R.A.:</b> {row['rel_ra_str']} ± {row['ra_unc_mas_str']} mas<br>" \
                    f"<b>Relative Decl.:</b> {row['rel_dec_str']} ± {row['dec_unc_mas_str']} mas<br>" \
                    f"<b>RA:</b> {row['ra_str']} deg<br>" \
                    f"<b>DEC:</b> {row['dec_str']} deg<br>" \
                    f"<b>Epoch:</b> {row['measurement_epoch_yr_str']} yr<br>" \
                    f"<b>Reference:</b> {row['moca_pid'] or 'N/A'}<br>" \
                    f"<b>Origin:</b> {row['origin'] or 'N/A'}<br>" \
                    f"<b>Airmass:</b> {row['airmass_str']}<br>" \
                    f"<b>Bandpass:</b> {row['moca_psid'] or 'N/A'}<br>" \
                    f"<b>Comments:</b> {wrap_text(row['comments'] or '', width=50)}",
                axis=1
            ),
            hoverinfo='text'
        ))

    # Update layout for better legend positioning
    fig_dec.update_layout(
        plot_bgcolor='white',
        xaxis_title=xaxis_title, yaxis_title="DEC Offset (mas)",
        xaxis=dict(
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        yaxis=dict(
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        margin=dict(l=40, r=40, t=40, b=40),
        paper_bgcolor='white',
        showlegend=True,
        legend=dict(
             title=dict(
                text="<b> Missions</b>",  # Make the title bold
                font=dict(size=14)  # Optional: adjust font size
            ),
            #x=0.02, y=0.98,  # Adjust legend position as needed
            bgcolor='rgba(255, 255, 255, 0.5)',  # Optional: semi-transparent background
            bordercolor='black',
            borderwidth=1
        )
    )

    return fig_ra, fig_dec
