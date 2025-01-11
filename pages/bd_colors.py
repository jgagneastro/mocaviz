#TODO: Add the reading of moca_oids from URL
#TODO: in hovertext, change the x-axis color ref to the actual color measurement + ref. Same for absmag.
#TODO: Add a checkbox to hide binaries (enabled by default)
#TODO: Add a checkbox that selects only the best photometry (checked by default). This controls whether the table used is cdata_photometry or mechanics_best
#TODO: Add a checkbox for photometric distance estimates (by default is turned off)
#TODO: Add a checkbox for candidate BDs (by default is turned off)
#TODO: Add spectral indices
#TODO: Add noise to SPT
#TODO: Rename all DIV elements for a page-specific name

import dash
from dash import dcc, html, Input, Output, State
from dash.dependencies import ALL
from sqlalchemy import create_engine, MetaData, Table, select, case
from sqlalchemy.sql import func
import pandas as pd
from math import log10, floor
from urllib.parse import quote_plus as urlquote, urlparse, parse_qs
import os
import numpy as np
import plotly.graph_objs as go


# Register the page
dash.register_page(__name__, path='/bd-colors')

# Default connection parameters
default_host = '104.248.106.21'
default_username = 'public'
default_password = 'z@nUg_2h7_%?31y88'
default_dbname = 'mocadb'

# Define hovertext lines for each row
def construct_hovertext(row):
    hovertext = [
        f"MOCA OID: {row['moca_oid']}",
        f"Main designation: {row['designation']}",
        f"Spectral type: {row['complete_spectral_type']} ({row['spt_ref']})",
        f"Distance: {row['distance_display']} ({row['distance_ref']})"
    ]
    
    # Add optional keys dynamically
    optional_keys = {
        'x_ref': "X-axis absolute mag reference: ",
        'y_ref': "Y-axis absolute mag reference: ",
        'x_ref_1': "X-axis color reference 1: ",
        'x_ref_2': "X-axis color reference 2: ",
        'y_ref_1': "Y-axis color reference 1: ",
        'y_ref_2': "Y-axis color reference 2: ",
    }
    for key, label in optional_keys.items():
        if key in row and not pd.isna(row[key]):
            hovertext.append(f"{label}{row[key]}")

    # Add X and Y axis values
    hovertext.append(f"X-axis value: {row['x_data_display']}")
    hovertext.append(f"Y-axis value: {row['y_data_display']}")
    
    return "<br>".join(hovertext)

def color_format_value_with_error(value, error, unit=""):
    """
    Formats a value with its error, aligning the value's decimal precision with the error.
    If the value or error is None, it returns "N/A".
    """
    if pd.isna(value) or pd.isna(error) or value == "N/A" or error == "N/A":
        return "N/A"
    
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
    return df

# Layout for the page
layout = (
    html.Div([
        dcc.Location(id='url'),  # To track URL and query parameters

        # Title and Description
        html.H1("Substellar Photometry Explorer"),
        html.P("This page allows you to display the spectral type, absolute magnitudes, or colors of substellar objects in the MOCA database."),

        # Grid for dropdowns
        html.Div([
            # Row 1
            html.Div([
                html.Label("X-axis type:"),
                dcc.Dropdown(
                    id='bdcolors-x-axis-type-dropdown',
                    options=[
                        {'label': 'Spectral Type', 'value': 'spectral_type'},
                        {'label': 'Color', 'value': 'color'},
                        {'label': 'Absolute Magnitude', 'value': 'absolute_magnitude'}
                    ],
                    placeholder='Select x-axis type',
                )
            ], id='cell-1', style={"gridArea": "1 / 1"}),

            html.Div([
                html.Label("Y-axis type:"),
                dcc.Dropdown(
                    id='bdcolors-y-axis-type-dropdown',
                    options=[
                        {'label': 'Spectral Type', 'value': 'spectral_type'},
                        {'label': 'Color', 'value': 'color'},
                        {'label': 'Absolute Magnitude', 'value': 'absolute_magnitude'}
                    ],
                    placeholder='Select y-axis type',
                )
            ], id='cell-2', style={"gridArea": "1 / 2"}),

            # Row 2
            html.Div(id='bdcolors-x-axis-first-band', style={"gridArea": "2 / 1"}),  # Cell 3
            html.Div(id='bdcolors-y-axis-first-band', style={"gridArea": "2 / 2"}),  # Cell 4

            # Row 3
            html.Div(id='bdcolors-x-axis-second-band', style={"gridArea": "3 / 1"}),  # Cell 5
            html.Div(id='bdcolors-y-axis-second-band', style={"gridArea": "3 / 2"}),  # Cell 6
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
                id='moca-ids-input',
                type='text',
                placeholder="Insert MOCA object IDs separated by commas",
                style={'width': '100%'}
            )
        ], style={'marginTop': '1rem'}),

        # Scatter Plot
        dcc.Graph(id='scatter-plot'),
        
        # Missing MOCA IDs display
        html.Div(id='missing-moca-ids', style={'color': 'red', 'marginTop': '1rem'}),

        # Component that stores merged_data
        dcc.Store(id='merged-data-store'),  # Add a Store component
        

    ], style={'width': '65%', 'display': 'inline-block','padding-left': '15px'}), 

    # Export button and download component
    html.Div([
        html.Button("Export Table to CSV", id="export-button", n_clicks=0),
        dcc.Download(id="export-dataframe-csv"),  # Component for download
    ], style={'marginTop': '1rem', 'textAlign': 'left', 'padding-left': '15px'}),

    # Add the table as a separate full-width section    
    html.Div(
        id='selected-data-table',
        style={
            'marginTop': '1rem',
            'width': '100%',  # Ensure full window width
            'padding': '0',  # Remove padding for proper alignment
            'padding-left': '15px',
            'marginBottom': '2rem',
            'boxSizing': 'border-box',  # Include padding/border in the width calculation
        }
    )
)

def parse_url_params(url):
    """Parse URL parameters into a dictionary."""
    parsed_url = urlparse(url)
    return parse_qs(parsed_url.query)

def get_connection_string():
    """Build connection string from environment variables or defaults."""
    env_username = os.environ.get('MOCA_USERNAME', default_username)
    env_password = os.environ.get('MOCA_PASSWORD', default_password)
    env_dbname = os.environ.get('MOCA_DBNAME', default_dbname)
    env_host = os.environ.get('MOCA_HOST', default_host)
    return f'mysql+pymysql://{urlquote(env_username)}:{urlquote(env_password)}@{env_host}/{env_dbname}'

def fetch_moca_photometry_systems():
    """Fetch moca_psid and related data from moca_photometry_systems."""
    connection_string = get_connection_string()
    engine = create_engine(connection_string)
    with engine.connect() as connection:
        metadata = MetaData()
        moca_photometry_systems = Table('moca_photometry_systems', metadata, autoload_with=engine)
        photometry_query = select([moca_photometry_systems])
        return pd.read_sql(photometry_query, connection)

@dash.callback(
    Output('bdcolors-x-axis-first-band', 'children'),
    [Input('bdcolors-x-axis-type-dropdown', 'value')],
    State('url', 'href')
)
def update_x_axis_first_band(axis_type, url):
    if axis_type in ['color', 'absolute_magnitude']:
        # Parse URL parameters
        url_params = parse_url_params(url)
        default_value = url_params.get('xaxis_value_1', [None])[0]

        # Fetch photometry systems for dropdown options
        photometry_systems = fetch_moca_photometry_systems()
        options = [
            {'label': f"{row['name']} ({row['moca_psid']})", 'value': row['moca_psid']}
            for _, row in photometry_systems.iterrows()
        ]

        return html.Div([
            html.Label("Select first band for x-axis:"),
            dcc.Dropdown(
                id={'type': 'dynamic-dropdown', 'axis': 'x', 'band': 'first'},
                options=options,
                value=default_value,  # Set default value from URL
                placeholder="Select first band",
            )
        ])
    return None

@dash.callback(
    Output('bdcolors-x-axis-second-band', 'children'),
    [Input('bdcolors-x-axis-type-dropdown', 'value')],
    State('url', 'href')
)
def update_x_axis_second_band(axis_type, url):
    if axis_type == 'color':
        # Parse URL parameters
        url_params = parse_url_params(url)
        default_value = url_params.get('xaxis_value_2', [None])[0]

        # Fetch photometry systems for dropdown options
        photometry_systems = fetch_moca_photometry_systems()
        options = [
            {'label': f"{row['name']} ({row['moca_psid']})", 'value': row['moca_psid']}
            for _, row in photometry_systems.iterrows()
        ]

        return html.Div([
            html.Label("Select second band for x-axis:"),
            dcc.Dropdown(
                id={'type': 'dynamic-dropdown', 'axis': 'x', 'band': 'second'},
                options=options,
                value=default_value,  # Set default value from URL
                placeholder="Select second band",
            )
        ])
    return None

@dash.callback(
    Output('bdcolors-y-axis-first-band', 'children'),
    [Input('bdcolors-y-axis-type-dropdown', 'value')],
    State('url', 'href')
)
def update_y_axis_first_band(axis_type, url):
    if axis_type in ['color', 'absolute_magnitude']:
        # Parse URL parameters
        url_params = parse_url_params(url)
        default_value = url_params.get('yaxis_value_1', [None])[0]

        # Fetch photometry systems for dropdown options
        photometry_systems = fetch_moca_photometry_systems()
        options = [
            {'label': f"{row['name']} ({row['moca_psid']})", 'value': row['moca_psid']}
            for _, row in photometry_systems.iterrows()
        ]

        return html.Div([
            html.Label("Select first band for y-axis:"),
            dcc.Dropdown(
                id={'type': 'dynamic-dropdown', 'axis': 'y', 'band': 'first'},
                options=options,
                value=default_value,  # Set default value from URL
                placeholder="Select first band",
            )
        ])
    return None

@dash.callback(
    Output('bdcolors-y-axis-second-band', 'children'),
    [Input('bdcolors-y-axis-type-dropdown', 'value')],
    State('url', 'href')
)
def update_y_axis_second_band(axis_type, url):
    if axis_type == 'color':
        # Parse URL parameters
        url_params = parse_url_params(url)
        default_value = url_params.get('yaxis_value_2', [None])[0]

        # Fetch photometry systems for dropdown options
        photometry_systems = fetch_moca_photometry_systems()
        options = [
            {'label': f"{row['name']} ({row['moca_psid']})", 'value': row['moca_psid']}
            for _, row in photometry_systems.iterrows()
        ]

        return html.Div([
            html.Label("Select second band for y-axis:"),
            dcc.Dropdown(
                id={'type': 'dynamic-dropdown', 'axis': 'y', 'band': 'second'},
                options=options,
                value=default_value,  # Set default value from URL
                placeholder="Select second band",
            )
        ])
    return None

@dash.callback(
    [
        Output('bdcolors-x-axis-type-dropdown', 'value'),
        Output('bdcolors-y-axis-type-dropdown', 'value'),
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
    if xaxis_type not in ['spectral_type', 'absolute_magnitude', 'color']:
        xaxis_type = None  # Default value

    # Validate y-axis type
    if yaxis_type not in ['spectral_type', 'absolute_magnitude', 'color']:
        yaxis_type = None  # Default value

    # Return the validated or default values
    return xaxis_type, yaxis_type

@dash.callback(
    [
        Output('scatter-plot', 'figure'),
        Output('missing-moca-ids', 'children'),  # For missing MOCA IDs
        Output('merged-data-store', 'data')  # Save `merged_data` to the Store
    ],
    [
        Input('bdcolors-x-axis-type-dropdown', 'value'),
        Input('bdcolors-y-axis-type-dropdown', 'value'),
        Input({'type': 'dynamic-dropdown', 'axis': 'x', 'band': ALL}, 'value'),
        Input({'type': 'dynamic-dropdown', 'axis': 'y', 'band': ALL}, 'value'),
        Input('moca-ids-input', 'value'),
        Input('moca-ids-input', 'n_submit'),  # Trigger on Enter
    ],
    State('url', 'href')
)
def update_plot(x_axis_type, y_axis_type, x_band_values, y_band_values, moca_ids, n_submit, url):
    
    # Interpret the highlighted moca_oids
    # Process moca_ids only when Enter is pressed
    moca_ids_array = []
    if n_submit and moca_ids:
        try:
            moca_ids_array = [int(moca_id.strip()) for moca_id in moca_ids.split(',') if moca_id.strip()]
        except ValueError:
            moca_ids_array = []

    if x_band_values:
        # Get the input IDs and associated values from callback context
        input_ids_and_values = [
            (item['id'], value) 
            for item, value in zip(dash.callback_context.inputs_list[2], x_band_values)
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
            for item, value in zip(dash.callback_context.inputs_list[3], y_band_values)
        ]

        # Sort based on the 'band' key in the ID
        sorted_band_values = sorted(
            input_ids_and_values, 
            key=lambda item: item[0]['band']
        )

        # Extract the values in the correct order
        y_band_values = [value for _, value in sorted_band_values]
    
    connection_string = get_connection_string()

    # Establish connection
    engine = create_engine(connection_string)
    metadata = MetaData()

    # Query data
    with engine.connect() as connection:
        
        x_data = pd.DataFrame()
        y_data = pd.DataFrame()

        cdata_spectral_types = Table('cdata_spectral_types', metadata, autoload_with=engine)
        moca_objects = Table('moca_objects', metadata, autoload_with=engine)
        cdata_distances = Table('cdata_distances', metadata, autoload_with=engine)
        moca_publications = Table('moca_publications', metadata, autoload_with=engine)
        data_parallaxes = Table('data_parallaxes', metadata, autoload_with=engine)
        spt_publications = moca_publications.alias('spt_publications')
        distance_publications = moca_publications.alias('distance_publications')
        parallax_publications = moca_publications.alias('parallax_publications')

        if x_axis_type == 'absolute_magnitude' or y_axis_type == 'absolute_magnitude' or x_axis_type == 'color' or y_axis_type == 'color':
            photometry = Table('cdata_photometry', metadata, autoload_with=engine)
            #photometry = Table('mechanics_best_photometry_by_band', metadata, autoload_with=engine)
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
                select([
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
                ])
                .select_from(
                    cdata_spectral_types
                    .join(moca_objects, moca_objects.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    .outerjoin(
                        cdata_distances,
                        (cdata_distances.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (cdata_distances.c.adopted == 1)
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
                )
                .where(
                    ((cdata_spectral_types.c.adopted == 1) &
                    (cdata_spectral_types.c.spectral_type_number >= 6) &
                    (cdata_spectral_types.c.photometric_estimate == 0)) |
                    (cdata_spectral_types.c.moca_oid.in_(moca_ids_array))
                )
                .group_by(cdata_spectral_types.c.moca_oid)
            )

        if x_axis_type == 'absolute_magnitude' or y_axis_type == 'absolute_magnitude':
            absmag_query = (
                select([
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
                ])
                .select_from(
                    cdata_spectral_types
                    .join(moca_objects, moca_objects.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    .join(
                        cdata_distances,
                        (cdata_distances.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (cdata_distances.c.adopted == 1)
                    )
                    .join(
                        photometry,
                        (photometry.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (photometry.c.adopted == 1)
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
                )
                .where(
                    (cdata_spectral_types.c.adopted == 1) &
                    (cdata_spectral_types.c.spectral_type_number >= 6) &
                    (cdata_spectral_types.c.photometric_estimate == 0)
                )
                .group_by(cdata_spectral_types.c.moca_oid)
            )
        
        if x_axis_type == 'color' or y_axis_type == 'color':
            color_query = (
                select([
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
                ])
                .select_from(
                    cdata_spectral_types
                    .join(moca_objects, moca_objects.c.moca_oid == cdata_spectral_types.c.moca_oid)
                    .join(
                        cdata_distances,
                        (cdata_distances.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (cdata_distances.c.adopted == 1)
                    )
                    .join(
                        phot1,
                        (phot1.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (phot1.c.adopted == 1)
                    )
                    .join(
                        phot2,
                        (phot2.c.moca_oid == cdata_spectral_types.c.moca_oid) &
                        (phot2.c.adopted == 1)
                    )
                    .join(
                        photsys1,
                        (photsys1.c.moca_psid == phot1.c.moca_psid)
                    )
                    .join(
                        photsys2,
                        (photsys2.c.moca_psid == phot2.c.moca_psid)
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
                        photometry_publications1,
                        (photometry_publications1.c.moca_pid == phot1.c.moca_pid)
                    )
                    .outerjoin(
                        photometry_publications2,
                        (photometry_publications2.c.moca_pid == phot2.c.moca_pid)
                    )
                )
                .where(
                    (cdata_spectral_types.c.adopted == 1) &
                    (cdata_spectral_types.c.spectral_type_number >= 6) &
                    (cdata_spectral_types.c.photometric_estimate == 0)
                )
                .group_by(cdata_spectral_types.c.moca_oid)
            )

        if x_axis_type == 'spectral_type':

            x_data = pd.read_sql(spt_query, connection)

            x_data['x_data'] = x_data['spectral_type_number']
            x_data['ex_data'] = x_data['spectral_type_unc']
            x_axis_label = 'Spectral Type'
        
        if x_axis_type == 'absolute_magnitude' and x_band_values and any(v for v in x_band_values if v is not None):
            x_photometry_band = x_band_values[0]  # Extract the selected bandpass (e.g., 'mko_jmag')
            
            x_query = absmag_query.where(photometry.c.moca_psid == x_photometry_band)

            x_data = pd.read_sql(x_query, connection)
            
            # Calculate absolute magnitude and uncertainty using dmod
            x_data['x_data'] = x_data['magnitude'] - x_data['dmod']
            x_data['x_ref'] = x_data['photometry_ref']
            x_data['ex_data'] = np.sqrt(
                (x_data['magnitude_unc'])**2 + (x_data['dmod_unc'])**2
            )
            
            x_axis_label = 'Absolute '+x_data['magnitude_name'].iloc[0]+' ('+x_photometry_band+')-band magnitude'

        if x_axis_type == 'color' and x_band_values and sum(v is not None for v in x_band_values) == 2:
            x_photometry_band_1, x_photometry_band_2 = [v for v in x_band_values if v is not None]  # Extract non-None values
            
            x_query = color_query.where((phot1.c.moca_psid == x_photometry_band_1) & (phot2.c.moca_psid == x_photometry_band_2))

            x_data = pd.read_sql(x_query, connection)
            
            # Calculate absolute magnitude and uncertainty using dmod
            x_data['x_data'] = x_data['magnitude_1'] - x_data['magnitude_2']
            x_data['x_ref_1'] = x_data['photometry_ref_1']
            x_data['x_ref_2'] = x_data['photometry_ref_2']
            x_data['ex_data'] = np.sqrt(
                (x_data['magnitude_unc_1'])**2 + (x_data['magnitude_unc_2'])**2
            )

            x_axis_label = x_data['magnitude_name_1'].iloc[0]+' ('+x_photometry_band_1+') - '+x_data['magnitude_name_2'].iloc[0]+' ('+x_photometry_band_2+') color'

        if y_axis_type == 'spectral_type':
            
            y_data = pd.read_sql(spt_query, connection)

            y_data['y_data'] = y_data['spectral_type_number']
            y_data['ey_data'] = y_data['spectral_type_unc']
            y_axis_label = 'Spectral Type'

        if y_axis_type == 'absolute_magnitude' and y_band_values and any(v for v in y_band_values if v is not None):
            y_photometry_band = y_band_values[0]  # Extract the selected bandpass (e.g., 'mko_jmag')
            
            y_query = absmag_query.where(photometry.c.moca_psid == y_photometry_band)

            y_data = pd.read_sql(y_query, connection)
            
            # Calculate absolute magnitude and uncertainty using dmod
            y_data['y_data'] = y_data['magnitude'] - y_data['dmod']
            y_data['y_ref'] = y_data['photometry_ref']
            y_data['ey_data'] = np.sqrt(
                (y_data['magnitude_unc'])**2 + (y_data['dmod_unc'])**2
            )
            
            y_axis_label = 'Absolute '+y_data['magnitude_name'].iloc[0]+' ('+y_photometry_band+')-band magnitude'

        if y_axis_type == 'color' and y_band_values and sum(v is not None for v in y_band_values) == 2:
            y_photometry_band_1, y_photometry_band_2 = [v for v in y_band_values if v is not None]  # Extract non-None values

            y_query = color_query.where((phot1.c.moca_psid == y_photometry_band_1) & (phot2.c.moca_psid == y_photometry_band_2))

            y_data = pd.read_sql(y_query, connection)
            
            # Calculate absolute magnitude and uncertainty using dmod
            y_data['y_data'] = y_data['magnitude_1'] - y_data['magnitude_2']
            y_data['y_ref_1'] = y_data['photometry_ref_1']
            y_data['y_ref_2'] = y_data['photometry_ref_2']
            y_data['ey_data'] = np.sqrt(
                (y_data['magnitude_unc_1'])**2 + (y_data['magnitude_unc_2'])**2
            )

            y_axis_label = y_data['magnitude_name_1'].iloc[0]+' ('+y_photometry_band_1+') - '+y_data['magnitude_name_2'].iloc[0]+' ('+y_photometry_band_2+') color'

    # Check if both axes are selected
    if x_data.empty or y_data.empty:
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
        return empty_figure, None, None
    
    # Identify overlapping columns except for the merge key
    overlapping_columns = set(x_data.columns).intersection(set(y_data.columns)) - {'moca_oid'}

    # Drop overlapping columns from y_data before merging
    y_data = y_data.drop(columns=overlapping_columns)

    # Merge the x and y data on moca_oid
    merged_data = pd.merge(x_data, y_data, on='moca_oid', how='inner')

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
    highlighted_data = merged_data[merged_data['moca_oid'].isin(moca_ids_array)]
    regular_data = merged_data[~merged_data['moca_oid'].isin(moca_ids_array)]

    # Define color mapping for spectral classes
    spectral_class_colors = {
        'M': 'red',
        'L': 'orange',
        'T': 'blue',
        'Y': 'purple',
    }

    # Define symbols for age_sample categories
    age_sample_symbols = {
        'field': 'circle',  # Default symbol
        'young': 'triangle-up',  # Young or red
        'old': 'square',  # Subdwarf or blue
    }

    # Define legend names for age_sample categories
    age_sample_legend_names = {
        'field': 'Field',
        'young': 'Young or red',
        'old': 'Subdwarf or blue',
    }

    # Add a default color for unknown or unrecognized spectral classes
    default_color = 'aqua'

    # Map colors to spectral classes in the merged_data DataFrame
    regular_data['color'] = regular_data['spectral_class'].map(spectral_class_colors).fillna(default_color)

    # Map symbols to age_sample in the merged_data DataFrame
    regular_data['symbol'] = regular_data['age_sample'].map(age_sample_symbols).fillna('circle')  # Default to circle for unknown age_sample

    # Determine missing MOCA IDs
    missing_ids_message = None
    missing_ids = set(moca_ids_array) - set(highlighted_data['moca_oid'].unique())
    if missing_ids:
        missing_ids_message = f"MOCA IDs not found: {', '.join(map(str, missing_ids))}"

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
        fig.add_trace(go.Scatter(
            x=[None],  # No data for the trace
            y=[None],  # No data for the trace
            mode='markers',
            marker=dict(size=10, color=color),
            name=f"{spectral_class} class"  # Legend entry
        ))

    # Add an invisible trace for unknown classes if needed
    fig.add_trace(go.Scatter(
        x=[None],  # No data for the trace
        y=[None],  # No data for the trace
        mode='markers',
        marker=dict(size=10, color=default_color),
        name="Other classes"
    ))

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
        template="plotly_white",
        legend_title="Spectral Class",
        height=800,  # Increase the height (default is usually ~450-500)
        yaxis=dict(range=y_range)  # Apply the flipped range for absolute magnitudes
    )

    return fig, dcc.Markdown(missing_ids_message) if missing_ids_message else None, merged_data.to_dict('records')  # Save `merged_data` as a JSON serializable dictionary

@dash.callback(
    Output('selected-data-table', 'children'),
    [
        Input('scatter-plot', 'selectedData'),
        Input('merged-data-store', 'data')  # Access `merged_data` from the Store
    ]
)
def update_table(selectedData, merged_data_records):
    # Convert the stored `merged_data` back to a DataFrame
    merged_data = pd.DataFrame(merged_data_records)

    # Extract selected points
    selected_data = []
    if selectedData and 'points' in selectedData:
        selected_data = [point['customdata'] for point in selectedData['points'] if 'customdata' in point]

    selected_rows = merged_data[merged_data['moca_oid'].isin(selected_data)]
    
    # Drop the hovertext column from the table
    if 'hovertext' in selected_rows.columns:
        selected_rows = selected_rows.drop(columns=['hovertext'])

    # Generate table
    if not selected_rows.empty:
        return dash.dash_table.DataTable(
            columns=[{"name": col, "id": col} for col in selected_rows.columns],
            data=selected_rows.to_dict('records'),
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'left', 'padding': '5px'},
            style_header={'fontWeight': 'bold'}
        )
    return html.Div("No points selected.")

@dash.callback(
    Output("export-dataframe-csv", "data"),
    Input("export-button", "n_clicks"),
    [
        State("merged-data-store", "data"),  # Use the stored `merged_data`
        State("scatter-plot", "selectedData")  # Use the selection data from the plot
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