import dash
from dash import html, dcc

dash.register_page(__name__, path='/')

layout = html.Div(
    className="banner",
    children=[
        #html.Img(src=get_asset_url("dash-logo.png")),
        html.H6(children='MOCAdb data visualizations',style={'color':"#000000","backgroundColor":"#DEDDE1", "marginLeft": 0, "width":"100%"}),
        dcc.Markdown(
                id="home-instructions",
                className="row",
                children=[
                    " Welcome to the MOCAdb data visualizations center. This web page contains several tools that will allow you to interactively explore the contents of the MOCA database. You can also access the Python codes used to run these visualizations [on my GitHub](https://github.com/jgagneastro/mocaviz) and run them locally.\n\n"
                    " Please choose one of the following tools:\n"
                    " * Explore general MOCAdb data with the [MOCA explorer](/moca-explorer).",
                    " * Explore the 3D XYZ spatial positions of MOCAdb data with the [MOCA spatial explorer](/xyz).",
                    " * Explore hierarchical association structures with a [Sunburst graph](/group-hierarchy).",
                    " * Return to the [MOCAdb website](https://mocadb.ca).",
                ]
                , style={"width": "100%", "whiteSpace": "pre-wrap", "marginLeft": 30, "marginRight": 30, "marginTop": 30,},#, "backgroundColor":"#1F2C56"
            ),
        ],
    style={"width": "100%", "height": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"#F5F8FA"},#, "backgroundColor":"#192444"
    )