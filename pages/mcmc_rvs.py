import dash
import numpy as np
import decimal
from dash import dcc, html, Input, Output, State,  callback_context, dash_table
import plotly.graph_objs as go
from urllib.parse import quote_plus as urlquote
from sqlalchemy import create_engine, select, MetaData, Table, inspect
import pandas as pd
import os

# Read connection information for the database
default_host = '104.248.106.21'
default_username = 'public'
default_password = 'z@nUg_2h7_%?31y88'
default_dbname = 'mocadb'

env_username = os.environ.get('MOCA_USERNAME', default_username)
env_password = os.environ.get('MOCA_PASSWORD', default_password)
env_dbname = os.environ.get('MOCA_DBNAME', default_dbname)
env_host = os.environ.get('MOCA_HOST', default_host)

connection_string = f'mysql+pymysql://{env_username}:{urlquote(env_password)}@{env_host}/{env_dbname}'

# List of required tables
required_tables = ['pcat_mcmc_rv_pipeline', 'mechanics_file_sets', 'mechanics_files']

# Function to check if required tables exist
def check_tables_exist(engine, required_tables):
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    missing_tables = [table for table in required_tables if table not in existing_tables]
    return missing_tables

# Create an engine and check for missing tables
engine = create_engine(connection_string)
missing_tables = check_tables_exist(engine, required_tables)

# Exit if any required tables are missing
if not missing_tables:

    # Register the page in the Dash app
    dash.register_page(__name__)

    # Establish connection to the database
    connection = engine.connect()
    metadata = MetaData()

    # Reflect the pcat_mcmc_rv_pipeline table
    pcat_mcmc_rv_pipeline = Table('pcat_mcmc_rv_pipeline', metadata, autoload_with=engine)

    # Corrected query to get unique dataset identifiers
    query_unique_datasets = select(
        (pcat_mcmc_rv_pipeline.c.target_name + '|' + 
        pcat_mcmc_rv_pipeline.c.template_name + '|' + 
        pcat_mcmc_rv_pipeline.c.pipeline_version).label('dataset_identifier')
    ).distinct()

    # Execute the query
    unique_datasets = pd.read_sql(query_unique_datasets, connection)

    # Get the unique identifiers as a list
    dataset_options = unique_datasets['dataset_identifier'].tolist()

    # Temporary hack to hide spirou data
    # Filter out options containing the word "spirou"
    dataset_options = [dataset for dataset in dataset_options if "spirou" not in dataset.lower()]

    #print(dataset_options)

    # Close the connection after getting the options
    connection.close()

    #  Define the layout of the page
    layout = html.Div([
        html.Div([
            html.H1("MCMC Radial Velocity Diagnostics"),
        ], style={'width': '100%', 'display': 'inline-block'}),
        
        dcc.Dropdown(
            className='custom-dropdown',
            id="mcmcrv-dataset-dropdown",
            options=[{'label': dataset, 'value': dataset} for dataset in dataset_options],
            #style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"white","fontSize": 16},
            placeholder="Select a dataset",
            style={
                'color': 'white !important',          # Set text color to white
                'width': '100%',           # Full width
                'minWidth': '300px',       # Minimum width to accommodate long text
                'fontSize': '16px'         # Adjust font size if necessary
            },
            #value=None
            value="specid_2302_CWISE J014642.51+512817.4|sonora_diamondback_t1600g100f1_m0.0_co1.0.spec|moca_2024aug21_1pm"  # Set the default value
        ),

        #html.Div([
        #    dcc.Input(id="input-moca_specid", value=2302, placeholder="Enter moca_specid", type="text", style={'margin-right': '10px'}),
        #    html.Button("Submit", id="submit-button")
        #], style={'display': 'flex', 'align-items': 'center', 'margin-top': '20px'}),
        
        html.Div([
            dcc.Graph(id="mcmcrv-scatter-plot"),
        ], style={'width': '65%', 'display': 'inline-block'}),
        
        # Add dcc.Loading to show a loading spinner while the image is updating
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
                        "padding-left": "10px"  # Add padding to the left to prevent cutting off
                    }
                )
            ),
        ], style={'width': '30%', 'display': 'inline-block', 'margin-left': '5%'}),
        
        #Add some text output
        html.Div(id="mcmcrv-text-output"),
    ])

    # Add a table to display the selected row's data
    #   """ html.Div([
    #       dcc.Loading(
    #          id="mcmcrv-loading-table",
    #          type="default",
    #          children=dash_table.DataTable(id="data-table", columns=[], data=[],style_table={'overflowX': 'auto'},
    #  style_header={
    #      'textAlign': 'center',
    #  },
    #  style_cell={
    #      'textAlign': 'left',
    #      'whiteSpace': 'normal',
    #      'height': 'auto',
    ##  },
    # style_cell_conditional=[
    #     {'if': {'column_id': 'your_column_name'},
    #      'width': '20%'},
    # ],)
    #     ),
    # ], style={'width': '100%', 'margin-top': '20px'}) """

    # Define the callback to update the scatter plot based on input
    @dash.callback(
        Output("mcmcrv-scatter-plot", "figure"),
        [Input("mcmcrv-scatter-plot", "selectedData"), Input("mcmcrv-dataset-dropdown", "value"), Input("mcmcrv-scatter-plot", "relayoutData")],
        #Input("mcmcrv-dataset-dropdown", "value"),
        prevent_initial_call=False  # Allow initial call with default value
        #Input("submit-button", "n_clicks"),
        #State("input-moca_specid", "value")
    )
    def update_scatter_plot(selectedData, selected_dataset, relayoutData):
        ctx = dash.callback_context
        #triggered_by_selection = 'selectedData' in ctx.triggered[0]['prop_id']
        #triggered_by_relayout = 'relayoutData' in ctx.triggered[0]['prop_id']
        
        triggered_by_selection = 'selectedData' in ctx.triggered[0]['prop_id']

        # If the selection was triggered but selectedData is empty, do nothing
        if triggered_by_selection and (selectedData is None or not selectedData.get('points')):
            return dash.no_update

        #print(ctx.triggered[0]['prop_id'])
        # If the plot was relayed out (e.g., zoomed/panned), but not due to selection, skip the update
        #if triggered_by_relayout and not triggered_by_selection:
        #    return dash.no_update
        
        if not selected_dataset:
            return go.Figure()
        #print(1)
        # Split the selected dataset into its components
        try:
            target_name, template_name, pipeline_version = selected_dataset.split('|')
        except ValueError:
            return go.Figure()

        # Establish connection to the database
        engine = create_engine(connection_string)
        connection = engine.connect()
        metadata = MetaData()

        # Reflect the pcat_mcmc_rv_pipeline table
        pcat_mcmc_rv_pipeline = Table('pcat_mcmc_rv_pipeline', metadata, autoload_with=engine)

        # Query the data
        #query = select([pcat_mcmc_rv_pipeline]).where(pcat_mcmc_rv_pipeline.c.moca_specid == int(moca_specid))
        #query = select(pcat_mcmc_rv_pipeline).where(pcat_mcmc_rv_pipeline.c.moca_specid == int(moca_specid))
        query = select(pcat_mcmc_rv_pipeline).where(
            (pcat_mcmc_rv_pipeline.c.target_name == target_name) &
            (pcat_mcmc_rv_pipeline.c.template_name == template_name) &
            (pcat_mcmc_rv_pipeline.c.pipeline_version == pipeline_version)
        )
        df = pd.read_sql(query, connection)
        df_filtered = df[df['radial_velocity_kms_unc'] > 0]

        # Close the connection
        connection.close()

        # If multiple data points are selected, update the average RV and horizontal lines
        if selectedData and len(selectedData['points']) > 1:
            selected_indices = [point['pointIndex'] for point in selectedData['points']]
            df_filtered = df_filtered.iloc[selected_indices]
        
        # Calculate weights as 1/error^2
        weights = 1 / df_filtered['radial_velocity_kms_unc']**2

        # Calculate the weighted average RV
        weighted_avg_rv = np.average(df_filtered['radial_velocity_kms'], weights=weights)

        # Calculate the weighted standard deviation
        variance = np.average((df_filtered['radial_velocity_kms'] - weighted_avg_rv)**2, weights=weights)
        weighted_stddev_rv = np.sqrt(variance * (1 / (1 - (np.sum(weights**2) / np.sum(weights)**2))))

        # Calculate segment wavelength
        df['segment_wavelength'] = (df['wave_min'] + df['wave_max']) / 2

        # Initialize selected points
        selected_indices = list(range(len(df_filtered)))  # Select all points by default

        # Preserve selected data points if they exist
        if selectedData and 'points' in selectedData:
            selected_indices = [point['pointIndex'] for point in selectedData['points']]

        # If this was triggered by selectedData, and the selected points are the same, return no update
        #if triggered_by_selected_data:
        #    return dash.no_update  # Skip the update if we're re-triggered by selection

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
            selectedpoints=selected_indices,  # Preserve selected points
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

        # Update the layout for background, grid, and border
        fig.update_layout(
            plot_bgcolor='white',             # Completely white background
            xaxis=dict(
                gridcolor='rgba(211, 211, 211, 0.6)', # Slightly paler gray grid lines
                zerolinecolor='lightgray',            # Gray zero line
                showline=True,
                linewidth=2,                          # Thickness of the black box outline
                linecolor='black',                    # Black outline for the box
                mirror=True,                          # Mirror the axis line on all sides
                ticks='outside',                      # Use tick marks on the axes
                tickwidth=2,                          # Thicker tick marks
            ),
            yaxis=dict(
                gridcolor='rgba(211, 211, 211, 0.6)', # Slightly paler gray grid lines
                zerolinecolor='lightgray',            # Gray zero line
                showline=True,
                linewidth=2,                          # Thickness of the black box outline
                linecolor='black',                    # Black outline for the box
                mirror=True,                          # Mirror the axis line on all sides
                ticks='outside',                      # Use tick marks on the axes
                tickwidth=2,                          # Thicker tick marks
            ),
            margin=dict(l=40, r=40, t=40, b=40),      # Adjust margins if needed
            paper_bgcolor='white',                    # Completely white background outside the plot
            showlegend=False,                         # Hide legend if not needed
            title=None                                # Remove figure title
        )


        fig.update_layout(xaxis_title="Segment Wavelength (μm)",
                        yaxis_title="Radial Velocity (km/s)")
        
        fig.update_layout(
            title={
                'text': f"Average RV = {weighted_avg_rv:.2f} ± {weighted_stddev_rv:.2f} km/s",
                'y': 0.98,  # Vertical position (closer to the top)
                'x': 0.5,   # Center horizontally
                'xanchor': 'center',
                'yanchor': 'top',
            }
        )
        
        return fig

    # Single callback: Clear the image, load the new image, and update the table
    @dash.callback(
        [Output("mcmcrv-image-display", "src"),
        Output("mcmcrv-text-output", "children")],
        #Output("data-table", "columns"),
        #Output("data-table", "data")],
        Input("mcmcrv-scatter-plot", "clickData"),
        prevent_initial_call=True
    )
    def update_image_and_table(clickData):
        if not clickData:
            return "", []
        
        clicked_id = clickData['points'][0]['customdata']

        # Establish connection to the database
        engine = create_engine(connection_string)
        connection = engine.connect()
        metadata = MetaData()

        # Reflect the table
        pcat_mcmc_rv_pipeline = Table('pcat_mcmc_rv_pipeline', metadata, autoload_with=engine)

        # Define the columns to select (including moca_fsid for internal use)
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
            #pcat_mcmc_rv_pipeline.c.rv_chains_std,
            #pcat_mcmc_rv_pipeline.c.b0_chains_std,
            #pcat_mcmc_rv_pipeline.c.b1_chains_std,
            #pcat_mcmc_rv_pipeline.c.vsini_chains_std,
            #pcat_mcmc_rv_pipeline.c.lsf_chains_std,
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
            pcat_mcmc_rv_pipeline.c.moca_fsid  # Included for internal processing
        ]

        # Unpack the columns using *columns_to_select
        query_row = select(*columns_to_select).where(pcat_mcmc_rv_pipeline.c.id == clicked_id)
        row_data = connection.execute(query_row).fetchone()

        if row_data is None:
            return "", []
        
        row_dict = {}  # Initialize the dictionary
        for col, value in row_data._mapping.items():
            #print(f"Column: {col}, Value: {value}, Type: {type(value)}")
            row_dict[col] = round(float(value), 2) if isinstance(value, decimal.Decimal) else value

        # Convert the RowProxy object into a dictionary and round values
        #row_dict = {col: round(value, 2) if isinstance(value, (float)) else value
        #            for col, value in row_data._mapping.items()}

        # Mapping for column renaming and unit appending
        column_mappings = {
            'rv': 'rv (km/s)',
            'erv': 'E_rv (km/s)',
            'vsini_kms': '<i>v</i> sin <i>i</i> (km/s)',
            'vsini_kms_unc': 'E_<i>v</i> sin <i>i</i> (km/s)',
            'lsf': 'log<sub>10</sub>(lsf)',
            'lsf_unc': 'e_log<sub>10</sub>(lsf)',
        }


        # Extract moca_fsid for internal use, then remove it from the dictionary
        moca_fsid = row_dict.pop('moca_fsid', None)

        # Prepare the data for the table
        #columns = [{"name": col, "id": col} for col in row_dict.keys()]
        #data = [row_dict]

    # Prepare the text output in grid format with 4 columns, omitting None values
        text_output = []
        for key, value in row_dict.items():
            if value is not None:  # Check if the value is not None
                # Mapping for renaming columns and adding units
                column_mappings = {
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
                }

                display_key = column_mappings.get(key, key)

                # Append "km/s" after specific values
                if key in ['rv', 'erv', 'vsini_kms', 'vsini_kms_unc']:
                    value = f"{value} km/s"

                # Append "um" after specific values
                if key in ['segment_wavelength']:
                    value = f"{value} μm"
                
                # Append "%" after specific values
                elif key in ['mean_finite_fraction', 'mean_outofbounds_fraction', 'model_contrast', 'mean_acceptance_rate']:
                    value = f"{value} %"
                
                # Handle the Markdown formatting for keys with subscripts and italic
                if key in column_mappings:
                    text_output.append(
                        html.Div([
                            dcc.Markdown(f"**{display_key} :** {value}", dangerously_allow_html=True)
                        ], style={'margin': '5px', 'width': '23%'})  # Adjust width for 4 columns
                    )
                else:
                    text_output.append(
                        html.Div([
                            dcc.Markdown(f"**{display_key} :** {value}")
                        ], style={'margin': '5px', 'width': '23%'})  # Adjust width for 4 columns
                    )

        # Wrap the text output in a flexible grid container
        grid_output = html.Div(text_output, style={
            'display': 'flex', 
            'flex-wrap': 'wrap',
            'justify-content': 'space-between',
            'max-width': '100%'
        })




        if not moca_fsid:
            connection.close()
            return "", []
        
        # Query to get the moca_fid from mechanics_file_sets
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
        
        # Query to get the URL from mechanics_files
        query_file = select(mechanics_files.c.url).where(mechanics_files.c.moca_fid == moca_fid)
        result_file = connection.execute(query_file).fetchone()
        file_url = result_file[0] if result_file else ""

        print(f"Retrieved file URL: {file_url}")

        # Close the connection
        connection.close()

        return file_url + '/download' if file_url else "", grid_output
