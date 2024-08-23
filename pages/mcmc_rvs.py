import dash
import numpy as np
import decimal
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objs as go
from urllib.parse import quote_plus as urlquote, urlparse, parse_qs
from sqlalchemy import create_engine, select, MetaData, Table
import pandas as pd
import os

# Register the page in the Dash app
dash.register_page(__name__)

# Placeholder for the database connection string
connection_string = None

# Define the initial layout of the page
layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div([
        html.H1("MCMC Radial Velocity Diagnostics"),
    ], style={'width': '100%', 'display': 'inline-block'}),
    
    dcc.Dropdown(
        id="mcmcrv-dataset-dropdown",
        options=[],  # Initially empty, will be populated via callback
        placeholder="Select a dataset",
        style={
            'color': 'white !important',
            'width': '100%',
            'minWidth': '300px',
            'fontSize': '16px'
        },
    ),

    html.Div([
        dcc.Graph(id="mcmcrv-scatter-plot"),
    ], style={'width': '65%', 'display': 'inline-block'}),
    
    html.Div([
        dcc.Loading(
            id="mcmcrv-loading-image",
            type="default",
            children=html.Img(
                id="mcmcrv-image-display",
                style={
                    "max-width": "100%",
                    "height": "auto",
                    "display": "block",
                    "margin-left": "auto",
                    "margin-right": "auto",
                    "padding-left": "10px"
                }
            )
        ),
    ], style={'width': '30%', 'display': 'inline-block', 'margin-left': '5%'}),
    
    html.Div(id="mcmcrv-text-output"),

    # New row for the additional images
    html.Div([
        dcc.Loading(
            id="mcmcrv-loading-chi2",
            type="default",
            children=html.Img(
                id="mcmcrv-chi2-image",
                style={
                    "max-width": "100%",
                    "height": "auto",
                    "display": "block",
                    "margin-left": "auto",
                    "margin-right": "auto",
                }
            )
        ),
        dcc.Loading(
            id="mcmcrv-loading-bestmodelfit",
            type="default",
            children=html.Img(
                id="mcmcrv-bestmodelfit-image",
                style={
                    "max-width": "100%",
                    "height": "auto",
                    "display": "block",
                    "margin-left": "auto",
                    "margin-right": "auto",
                }
            )
        ),
    ], style={'display': 'flex', 'justify-content': 'space-between', 'margin-top': '20px'}),
])

# Callback to populate the dropdown and initialize connection based on URL parameters
@dash.callback(
    output=[
        Output("mcmcrv-dataset-dropdown", "options"),
        Output("mcmcrv-dataset-dropdown", "value"),
        Output("url", "search"),  # This triggers the callback once the options are set
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
    env_host = '104.248.106.21'

    global connection_string
    connection_string = f'mysql+pymysql://{env_username}:{urlquote(env_password)}@{env_host}/{env_dbname}'

    # Establish connection to the database
    engine = create_engine(connection_string)
    connection = engine.connect()
    metadata = MetaData()

    # Reflect the pcat_mcmc_rv_pipeline table
    pcat_mcmc_rv_pipeline = Table('pcat_mcmc_rv_pipeline', metadata, autoload_with=engine)

    # Query to get unique dataset identifiers
    query_unique_datasets = select(
        (pcat_mcmc_rv_pipeline.c.target_name + '|' + 
        pcat_mcmc_rv_pipeline.c.template_name + '|' + 
        pcat_mcmc_rv_pipeline.c.pipeline_version).label('dataset_identifier')
    ).distinct()

    # Execute the query
    unique_datasets = pd.read_sql(query_unique_datasets, connection)

    # Get the unique identifiers as a list
    dataset_options = unique_datasets['dataset_identifier'].tolist()

    # Filter out options containing the word "spirou"
    dataset_options = [dataset for dataset in dataset_options if "spirou" not in dataset.lower()]

    # Close the connection
    connection.close()

    # Set the first option as default if available
    default_value = dataset_options[0] if dataset_options else None

    return [{"label": dataset, "value": dataset} for dataset in dataset_options], default_value, url_search

# Define the callback to update the scatter plot based on input
@dash.callback(
    Output("mcmcrv-scatter-plot", "figure"),
    [Input("mcmcrv-dataset-dropdown", "value"),
     Input("mcmcrv-scatter-plot", "selectedData"),
     Input("mcmcrv-scatter-plot", "relayoutData")]
)
def update_scatter_plot(selected_dataset, selectedData, relayoutData):
    ctx = dash.callback_context
    triggered_by_selection = 'selectedData' in ctx.triggered[0]['prop_id']

    # If the selection was triggered but selectedData is empty, do nothing
    if triggered_by_selection and (selectedData is None or not selectedData.get('points')):
        return dash.no_update

    if not selected_dataset:
        return go.Figure()

    try:
        target_name, template_name, pipeline_version = selected_dataset.split('|')
    except ValueError:
        return go.Figure()

    engine = create_engine(connection_string)
    connection = engine.connect()
    metadata = MetaData()

    pcat_mcmc_rv_pipeline = Table('pcat_mcmc_rv_pipeline', metadata, autoload_with=engine)

    query = select(pcat_mcmc_rv_pipeline).where(
        (pcat_mcmc_rv_pipeline.c.target_name == target_name) &
        (pcat_mcmc_rv_pipeline.c.template_name == template_name) &
        (pcat_mcmc_rv_pipeline.c.pipeline_version == pipeline_version)
    )
    df = pd.read_sql(query, connection)
    df_filtered = df[df['radial_velocity_kms_unc'] > 0]

    connection.close()

    if selectedData and len(selectedData['points']) > 1:
        selected_indices = [point['pointIndex'] for point in selectedData['points']]
        df_filtered = df_filtered.iloc[selected_indices]

    weights = 1 / df_filtered['radial_velocity_kms_unc']**2
    weighted_avg_rv = np.average(df_filtered['radial_velocity_kms'], weights=weights)
    variance = np.average((df_filtered['radial_velocity_kms'] - weighted_avg_rv)**2, weights=weights)
    weighted_stddev_rv = np.sqrt(variance * (1 / (1 - (np.sum(weights**2) / np.sum(weights)**2))))

    df['segment_wavelength'] = (df['wave_min'] + df['wave_max']) / 2

    selected_indices = list(range(len(df_filtered)))

    if selectedData and 'points' in selectedData:
        selected_indices = [point['pointIndex'] for point in selectedData['points']]

    fig = go.Figure(data=go.Scatter(
        x=df['segment_wavelength'],
        y=df['radial_velocity_kms'],
        mode='markers',
        marker=dict(
            color='white',        # White center
            size=6,               # Slightly smaller symbol size
            symbol='circle',      # Filled circle
            line=dict(
                width=2,          # Thick black outline
                color='black'     # Outline color
            )
        ),
        error_y=dict(
            type='data',
            array=df['radial_velocity_kms_unc'],
            visible=True,
            color='rgba(0, 0, 0, 0.2)',  # Paler and lighter color for error bars
            thickness=1.5,               # Slightly thicker error bars
            width=2                      # Capsize width
        ),
        customdata=df['id'],
        text=df.apply(lambda row: f"RV: {row['radial_velocity_kms']:.2f} ± {row['radial_velocity_kms_unc']:.2f} km/s<br>Wavelength: {row['segment_wavelength']:.2f} μm", axis=1),
        hoverinfo='text'                # Use the formatted text for hover information
    ))

    # Add horizontal lines for weighted average and standard deviation
    fig.add_hline(
        y=weighted_avg_rv,
        line=dict(color='rgba(139, 0, 0, 0.5)', width=3),  # Thicker and darker red line
        layer='below'  # Display behind data points
    )
    fig.add_hline(
        y=weighted_avg_rv + weighted_stddev_rv,
        line=dict(color='rgba(139, 0, 0, 0.3)', dash='longdash', width=1),  # Thicker dashed line, same color, longer dashes
        layer='below'  # Display behind data points
    )
    fig.add_hline(
        y=weighted_avg_rv - weighted_stddev_rv,
        line=dict(color='rgba(139, 0, 0, 0.3)', dash='longdash', width=1),  # Thicker dashed line, same color, longer dashes
        layer='below'  # Display behind data points
    )

    return fig

# Callback to update the image and text output when a scatter plot point is clicked
@dash.callback(
    [Output("mcmcrv-image-display", "src"),
     Output("mcmcrv-text-output", "children")],
    Input("mcmcrv-scatter-plot", "clickData"),
    prevent_initial_call=True
)
def update_image_and_table(clickData):
    if not clickData:
        return "", []
    
    clicked_id = clickData['points'][0]['customdata']

    engine = create_engine(connection_string)
    connection = engine.connect()
    metadata = MetaData()

    pcat_mcmc_rv_pipeline = Table('pcat_mcmc_rv_pipeline', metadata, autoload_with=engine)

    columns_to_select = [
        pcat_mcmc_rv_pipeline.c.id,
        pcat_mcmc_rv_pipeline.c.order_number,
        pcat_mcmc_rv_pipeline.c.window_number,
        pcat_mcmc_rv_pipeline.c.segment_number,
        ((pcat_mcmc_rv_pipeline.c.wave_min + pcat_mcmc_rv_pipeline.c.wave_max) / 2).label('segment_wavelength'),
        pcat_mcmc_rv_pipeline.c.radial_velocity_kms.label('rv'),
        pcat_mcmc_rv_pipeline.c.radial_velocity_kms_unc.label('erv'),
        pcat_mcmc_rv_pipeline.c.blaze0,
        pcat_mcmc_rv_pipeline.c.blaze0_unc,
        pcat_mcmc_rv_pipeline.c.blaze1,
        pcat_mcmc_rv_pipeline.c.blaze1_unc,
        pcat_mcmc_rv_pipeline.c.vsini_kms,
        pcat_mcmc_rv_pipeline.c.vsini_kms_unc,
        pcat_mcmc_rv_pipeline.c.lsf,
        pcat_mcmc_rv_pipeline.c.lsf_unc,
        pcat_mcmc_rv_pipeline.c.best_chi2,
        pcat_mcmc_rv_pipeline.c.lnp_avg,
        pcat_mcmc_rv_pipeline.c.lnp_mad,
        pcat_mcmc_rv_pipeline.c.lnp_std,
        pcat_mcmc_rv_pipeline.c.lnp_median,
        pcat_mcmc_rv_pipeline.c.lnp_max,
        (pcat_mcmc_rv_pipeline.c.mean_acceptance_rate * 100).label('mean_acceptance_rate'),
        (pcat_mcmc_rv_pipeline.c.mean_finite_fraction * 100).label('mean_finite_fraction'),
        (pcat_mcmc_rv_pipeline.c.mean_outofbounds_fraction * 100).label('mean_outofbounds_fraction'),
        (pcat_mcmc_rv_pipeline.c.model_contrast * 100).label('model_contrast'),
        pcat_mcmc_rv_pipeline.c.nmodel_10p_contrast,
        pcat_mcmc_rv_pipeline.c.moca_fsid
    ]

    query_row = select(*columns_to_select).where(pcat_mcmc_rv_pipeline.c.id == clicked_id)
    row_data = connection.execute(query_row).fetchone()

    if row_data is None:
        return "", []
    
    row_dict = {col: round(float(value), 2) if isinstance(value, decimal.Decimal) else value for col, value in row_data._mapping.items()}

    column_mappings = {
        'rv': 'rv (km/s)',
        'erv': 'E_rv (km/s)',
        'vsini_kms': '<i>v</i> sin <i>i</i> (km/s)',
        'vsini_kms_unc': 'E_<i>v</i> sin <i>i</i> (km/s)',
        'lsf': 'log<sub>10</sub>(lsf)',
        'lsf_unc': 'e_log<sub>10</sub>(lsf)',
    }

    moca_fsid = row_dict.pop('moca_fsid', None)

    text_output = []
    for key, value in row_dict.items():
        if value is not None:
            column_mappings.update({
                'id': 'ID',
                'order_number': 'Order',
                'window_number': 'Window',
                'segment_wavelength': 'Central wavelength',
                'segment_number': 'Segment',
                'lnp_median': 'median(ln P)',
                'lnp_std': 'std(ln P)',
                'lnp_max': 'max(ln P)',
                'lnp_mad': 'mad(ln P)',
                'lnp_avg': 'avg(ln P)',
                'mean_finite_fraction': 'Finite steps',
                'mean_outofbounds_fraction': 'Out of bounds steps',
                'mean_acceptance_rate': 'Acceptance rate',
                'model_contrast': 'Model contrast',
                'nmodel_10p_contrast': 'Model points with > 10% contrast',
                'rv': 'RV',
                'erv': 'E_RV',
                'best_chi2': 'χ<sup>2</sup>',
                'vsini_kms': '<i>v</i> sin <i>i</i>',
                'vsini_kms_unc': 'E_<i>v</i> sin <i>i</i>',
                'lsf': 'log<sub>10</sub>(lsf)',
                'lsf_unc': 'E_log<sub>10</sub>(lsf)',
                'blaze0': 'log<sub>10</sub>(Blaze<sub>left</sub>)',
                'blaze0_unc': 'E_log<sub>10</sub>(Blaze<sub>left</sub>)',
                'blaze1': 'log<sub>10</sub>(Blaze<sub>right</sub>)',
                'blaze1_unc': 'E_log<sub>10</sub>(Blaze<sub>right</sub>)',
            })

            display_key = column_mappings.get(key, key)

            if key in ['rv', 'erv', 'vsini_kms', 'vsini_kms_unc']:
                value = f"{value} km/s"

            if key in ['segment_wavelength']:
                value = f"{value} μm"
            
            if key in ['mean_finite_fraction', 'mean_outofbounds_fraction', 'model_contrast', 'mean_acceptance_rate']:
                value = f"{value} %"
            
            if key in column_mappings:
                text_output.append(
                    html.Div([
                        dcc.Markdown(f"**{display_key} :** {value}", dangerously_allow_html=True)
                    ], style={'margin': '5px', 'width': '23%'})
                )
            else:
                text_output.append(
                    html.Div([
                        dcc.Markdown(f"**{display_key} :** {value}")
                    ], style={'margin': '5px', 'width': '23%'})
                )

    grid_output = html.Div(text_output, style={
        'display': 'flex', 
        'flex-wrap': 'wrap',
        'justify-content': 'space-between',
        'max-width': '100%'
    })

    if not moca_fsid:
        connection.close()
        return "", []
    
    mechanics_file_sets = Table('mechanics_file_sets', metadata, autoload_with=engine)
    mechanics_files = Table('mechanics_files', metadata, autoload_with=engine)

    query_fileset = select(mechanics_file_sets.c.moca_fid).where(
        mechanics_file_sets.c.moca_fsid == moca_fsid
    ).where(
        mechanics_file_sets.c.description.like('MCMC RV model fit')
    )
    result_fileset = connection.execute(query_fileset).fetchone()
    moca_fid = result_fileset[0] if result_fileset else None

    if not moca_fid:
        connection.close()
        return "", []
    
    query_file = select(mechanics_files.c.url).where(mechanics_files.c.moca_fid == moca_fid)
    result_file = connection.execute(query_file).fetchone()
    file_url = result_file[0] if result_file else ""

    connection.close()

    return file_url + '/download' if file_url else "", grid_output

# Callback to update the additional images (chi2 and bestmodelfit) when a dataset is selected
@dash.callback(
    [Output("mcmcrv-chi2-image", "src"),
     Output("mcmcrv-bestmodelfit-image", "src")],
    Input("mcmcrv-dataset-dropdown", "value")
)
def update_model_fit_images(selected_dataset):
    if not selected_dataset:
        return "", ""
    
    try:
        target_name, template_name, pipeline_version = selected_dataset.split('|')
    except ValueError:
        return "", ""

    engine = create_engine(connection_string)
    connection = engine.connect()
    metadata = MetaData()

    pcat_mcmc_rv_pipeline = Table('pcat_mcmc_rv_pipeline', metadata, autoload_with=engine)
    calc_model_grid_fits = Table('calc_model_grid_fits', metadata, autoload_with=engine)
    data_model_grid_files = Table('data_model_grid_files', metadata, autoload_with=engine)
    mechanics_file_sets = Table('mechanics_file_sets', metadata, autoload_with=engine)
    mechanics_files = Table('mechanics_files', metadata, autoload_with=engine)

    # Query to match template_name on CONCAT(calc_model_grid_fits.moca_mgridid, '_', data_model_grid_files.file_name)
    query_template_name = select(calc_model_grid_fits.c.moca_fsid).select_from(
        calc_model_grid_fits.join(
            data_model_grid_files,
            calc_model_grid_fits.c.moca_mgridfileid == data_model_grid_files.c.moca_mgridfileid
        )
    ).where(
        (calc_model_grid_fits.c.moca_mgridid + '_' + data_model_grid_files.c.file_name) == template_name
    ).limit(1)

    result_template_name = connection.execute(query_template_name).fetchone()
    if not result_template_name:
        connection.close()
        return "", ""

    moca_fsid = result_template_name[0]

    # Query to get the moca_fid for the "Best model fit"
    query_bestmodelfit_fid = select(mechanics_file_sets.c.moca_fid).where(
        mechanics_file_sets.c.moca_fsid == moca_fsid
    ).where(
        mechanics_file_sets.c.description.like('Best model fit')
    )
    result_bestmodelfit_fid = connection.execute(query_bestmodelfit_fid).fetchone()

    # Query to get the moca_fid for the "All model fit chi2"
    query_chi2_fid = select(mechanics_file_sets.c.moca_fid).where(
        mechanics_file_sets.c.moca_fsid == moca_fsid
    ).where(
        mechanics_file_sets.c.description.like('All model fit chi2')
    )
    result_chi2_fid = connection.execute(query_chi2_fid).fetchone()

    bestmodelfit_url = ""
    chi2_url = ""

    # If we found a moca_fid for bestmodelfit, fetch its URL
    if result_bestmodelfit_fid:
        bestmodelfit_fid = result_bestmodelfit_fid[0]
        query_bestmodelfit_url = select(mechanics_files.c.url).where(
            mechanics_files.c.moca_fid == bestmodelfit_fid
        )
        result_bestmodelfit_url = connection.execute(query_bestmodelfit_url).fetchone()
        bestmodelfit_url = result_bestmodelfit_url[0] if result_bestmodelfit_url else ""

    # If we found a moca_fid for chi2, fetch its URL
    if result_chi2_fid:
        chi2_fid = result_chi2_fid[0]
        query_chi2_url = select(mechanics_files.c.url).where(
            mechanics_files.c.moca_fid == chi2_fid
        )
        result_chi2_url = connection.execute(query_chi2_url).fetchone()
        chi2_url = result_chi2_url[0] if result_chi2_url else ""

    connection.close()

    return chi2_url + '/download' if chi2_url else "", bestmodelfit_url + '/download' if bestmodelfit_url else ""
