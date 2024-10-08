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
        html.P("This page shows the measured radial velocities by the Markov Chain Monte Carlo method in specific wavelength segments of the observed spectrum. "
               "You can click on one data point in the scatter plot to see the detailed data corresponding to this segment and the model fit figure. "
               "You can also select specific data points with the plotly box selection tool to refine the average radial velocity that is displayed in the title "
               "and as a red line, which corresponds to an average weighted by measurement errors.\n"
               "The data points which LSF value is too large, or for which data_contrast or model_contrast are too low, are automatically flagged as bad data "
               " and those are not used in the average radial velocity calculation."),
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
    
    # Container for the dataset-level text outputs
    html.Div(id="mcmcrv-dataset-info-output", style={'margin-top': '20px'}),

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
     Input("mcmcrv-scatter-plot", "selectedData")],
     prevent_initial_call=True,
)
def update_scatter_plot(selected_dataset, selectedData):
    ctx = dash.callback_context
    
    if not selected_dataset:
        return dash.no_update
    
    triggered_by_selection = 'selectedData' in ctx.triggered[0]['prop_id']

    if triggered_by_selection and (selectedData is None or not selectedData.get('points')):
        return dash.no_update
    
    try:
        target_name, template_name, pipeline_version = selected_dataset.split('|')
    except ValueError:
        return dash.no_update

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
    connection.close()

    # Define LSF thresholds based on moca_instid
    lsf_thresholds = {
        'spex_irtf': 1.33,
        'fire_magellan': 1.384,
        'nires_keck': 1.378
    }

    df['lsf_threshold'] = df['moca_instid'].map(lsf_thresholds).fillna(1.5)
    df['segment_wavelength'] = (df['wave_min'] + df['wave_max']) / 2

    # Identify outliers based on criteria
    outliers = df[(df['radial_velocity_kms_unc'] <= 0) |
                  (df['data_contrast'] < 0.01) |
                  (df['model_contrast'] < 0.1) |
                  (df['lsf'] > df['lsf_threshold'])]

    # If all data points are flagged as outliers, treat none as outliers
    if len(outliers) == len(df):
        outliers = pd.DataFrame()  # Empty outliers DataFrame

    # Initialize selected_indices to include all points by default
    selected_indices = list(df.index)

    # Apply manual selection first
    if selectedData and len(selectedData['points']) > 1:
        selected_indices = [point['pointIndex'] for point in selectedData['points']]
        df_selected = df.iloc[selected_indices]
    else:
        df_selected = df.copy()

    # Filter out outliers from the selected data
    df_filtered = df_selected[~df_selected.index.isin(outliers.index)]

    # Calculate weighted average RV excluding outliers
    if not df_filtered.empty:
        weights = 1 / df_filtered['radial_velocity_kms_unc']**2
        weighted_avg_rv = np.average(df_filtered['radial_velocity_kms'], weights=weights)
        variance = np.average((df_filtered['radial_velocity_kms'] - weighted_avg_rv)**2, weights=weights)
        #This equation does not allow the error to decrease by a factor 1/SQRT(N)
        weighted_stddev_rv = np.sqrt(variance * (1 / (1 - (np.sum(weights**2) / np.sum(weights)**2))))
        #This one does
        #weighted_stddev_rv = np.sqrt(1 / np.sum(weights))*np.sqrt(1.5)#Factor 1.5 for window overlap
    else:
        weighted_avg_rv = np.nan
        weighted_stddev_rv = np.nan

    # Create scatter plot with normal data points
    fig = go.Figure()

    # Add red 'x' markers for outliers
    fig.add_trace(go.Scatter(
        x=outliers['segment_wavelength'],
        y=outliers['radial_velocity_kms'],
        mode='markers',
        marker=dict(size=15, symbol='x-thin', line=dict(color='red', width=3)),
        name='Bad data'
    ))

    fig.add_trace(go.Scatter(
        x=df['segment_wavelength'],
        y=df['radial_velocity_kms'],
        mode='markers',
        name='All data',
        marker=dict(
            color='white',        
            size=6,               
            symbol='circle',      
            line=dict(
                width=2,          
                color='black'     
            )
        ),
        selectedpoints=selected_indices,  
        error_y=dict(
            type='data',
            array=df['radial_velocity_kms_unc'],
            visible=True,
            color='rgba(0, 0, 0, 0.2)',  
            thickness=1.5,               
            width=2                      
        ),
        customdata=df['id'],
        text=df.apply(lambda row: f"RV: {row['radial_velocity_kms']:.2f} ± {row['radial_velocity_kms_unc']:.2f} km/s<br>Wavelength: {row['segment_wavelength']:.2f} μm", axis=1),
        hoverinfo='text'
    ))

    # Add horizontal lines for weighted average and standard deviation
    if not np.isnan(weighted_avg_rv):
        fig.add_hline(
            y=weighted_avg_rv,
            line=dict(color='rgba(139, 0, 0, 0.5)', width=3),  
            layer='below'
        )
        fig.add_hline(
            y=weighted_avg_rv + weighted_stddev_rv,
            line=dict(color='rgba(139, 0, 0, 0.3)', dash='longdash', width=1),  
            layer='below'
        )
        fig.add_hline(
            y=weighted_avg_rv - weighted_stddev_rv,
            line=dict(color='rgba(139, 0, 0, 0.3)', dash='longdash', width=1),  
            layer='below'
        )

    # Update layout and add legend
    fig.update_layout(
        plot_bgcolor='white',
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
        legend=dict(x=0.02, y=0.98, bgcolor='rgba(255, 255, 255, 0.5)'),  # Adjust legend position and background color
        title=f"{df['target_name'].iloc[0]}: Average RV = {weighted_avg_rv:.2f} ± {weighted_stddev_rv:.2f} km/s" if not np.isnan(weighted_avg_rv) else f"{df['target_name'].iloc[0]}: Average RV could not be calculated",
        title_x=0.5,
        title_y=0.98,
        title_xanchor='center',
        title_yanchor='top'
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
        return dash.no_update

    # If clickData is provided, check for customdata to ensure it’s not a red cross
    if clickData is not None and 'customdata' not in clickData['points'][0]:
        return dash.no_update
        
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
        connection.close()
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

# Callback to update the model fit images and dataset-level text outputs
@dash.callback(
    [Output("mcmcrv-chi2-image", "src"),
     Output("mcmcrv-bestmodelfit-image", "src"),
     Output("mcmcrv-dataset-info-output", "children")],
    Input("mcmcrv-dataset-dropdown", "value")
)
def update_model_fit_images(selected_dataset):
    if not selected_dataset:
        return dash.no_update

    target_name, template_name, pipeline_version = selected_dataset.split('|')
    
    specid = target_name.split('_')[1]

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
    
    # Extract the relevant data for the dataset-level text output
    first_row = df.iloc[0] if not df.empty else None
    dataset_info = []
    if first_row is not None:
        info_columns = [
            'pipeline_version', 'target_name', 'berv_kms', 'berv_kms_unc',
            'nwindows', 'nsegments', 'npoints', 'origin', 'parscale_rv',
            'rv_min_bound', 'rv_max_bound', 'niter_mcmc', 'nburnin_mcmc', 'nchains_mcmc'
        ]
        column_mappings = {
            'pipeline_version': 'Pipeline Version',
            'target_name': 'Target Name',
            'berv_kms': 'BERV',
            'berv_kms_unc': 'E_BERV',
            'nwindows': 'N_Windows',
            'nsegments': 'N_Segments',
            'npoints': 'N_Data_Points',
            'origin': 'Origin',
            'parscale_rv': 'RV Scale',
            'rv_min_bound': 'RV Min Bound',
            'rv_max_bound': 'RV Max Bound',
            'niter_mcmc': 'MCMC Iterations',
            'nburnin_mcmc': 'MCMC Burn-in',
            'nchains_mcmc': 'MCMC Chains'
        }
        for col in info_columns:
            value = first_row[col]
            display_key = column_mappings.get(col, col)
            if value is None:
                continue
            
            unit = ""
            if display_key in ['BERV', 'E_BERV']:
                unit = " km/s"

            if display_key in ['RV Min Bound', 'RV Max Bound', 'RV Scale']:
                unit = " km/s"
                value = int(value)

            dataset_info.append(
                html.Div([
                    dcc.Markdown((f"**{display_key} :** {value:.2f}" if isinstance(value, (float, decimal.Decimal)) else f"**{display_key} :** {value}")+unit, dangerously_allow_html=True)
                ], style={'margin': '5px', 'width': '23%'})
            )

    dataset_info_output = html.Div(dataset_info, style={
        'display': 'flex',
        'flex-wrap': 'wrap',
        'justify-content': 'space-between',
        'max-width': '100%'
    })

    # Query the chi2 and bestmodelfit URLs
    calc_model_grid_fits = Table('calc_model_grid_fits', metadata, autoload_with=engine)
    data_model_grid_files = Table('data_model_grid_files', metadata, autoload_with=engine)

    query_template_name = select(calc_model_grid_fits.c.moca_fsid).select_from(
        calc_model_grid_fits.join(
            data_model_grid_files,
            calc_model_grid_fits.c.moca_mgridfileid == data_model_grid_files.c.moca_mgridfileid
        )
    ).where(
        (calc_model_grid_fits.c.moca_mgridid + '_' + data_model_grid_files.c.file_name) == template_name,
        calc_model_grid_fits.c.moca_specid == int(specid)
    ).limit(1)

    template_name_fsid = connection.execute(query_template_name).scalar()
    
    if not template_name_fsid:
        connection.close()
        return "", "", dataset_info_output

    mechanics_file_sets = Table('mechanics_file_sets', metadata, autoload_with=engine)
    mechanics_files = Table('mechanics_files', metadata, autoload_with=engine)

    query_chi2 = select(mechanics_files.c.url).select_from(
        mechanics_files.join(mechanics_file_sets)
    ).where(
        mechanics_file_sets.c.moca_fsid == template_name_fsid
    ).where(
        mechanics_file_sets.c.description.like('All model fit chi2')
    ).limit(1)

    query_bestmodelfit = select(mechanics_files.c.url).select_from(
        mechanics_files.join(mechanics_file_sets)
    ).where(
        mechanics_file_sets.c.moca_fsid == template_name_fsid
    ).where(
        mechanics_file_sets.c.description.like('Best model fit')
    ).limit(1)

    chi2_url = connection.execute(query_chi2).scalar()
    bestmodelfit_url = connection.execute(query_bestmodelfit).scalar()
    connection.close()

    return (chi2_url + '/download' if chi2_url else "", 
            bestmodelfit_url + '/download' if bestmodelfit_url else "", 
            dataset_info_output)