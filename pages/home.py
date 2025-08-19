import dash
from dash import html, dcc
from dash.dependencies import Input, Output, State

dash.register_page(__name__, path='/')

default_text = \
" Welcome to the MOCAdb data visualizations center." + \
" This web page contains several tools that will allow you to interactively explore the contents of the MOCA database." + \
" You can also access the Python codes used to run these visualizations" + \
" [on my GitHub](https://github.com/jgagneastro/mocaviz) and run them locally.\n\n" + \
" Please choose one of the following tools:\n" + \
" * Explore general MOCAdb data with the [MOCA explorer](/moca-explorer?#args#).\n" + \
" * Explore the 3D XYZUVW spatial positions of MOCAdb data with the [MOCA spatial-kinematic explorer](/xyzuvw?#args#).\n" + \
" * Explore hierarchical association structures with a [Sunburst graph](/group-hierarchy?#args#).\n" + \
" * Visualize spectra stored in MOCAdb with the [Spectral Explorer](/spectra?#args#).\n" + \
" * Visually determine spectral types with empirical grid comparisons using the [Spectral Typing tool](/spectral-typing?#args#).\n" + \
" * Visualize radial velocities calculated in MOCAdb with the [RV Explorer](/mcmc-rvs?#args#).\n" + \
" * Visualize astrometry in MOCAdb with the [Astrometric Explorer](/astrometry?#args#).\n" + \
" * Visualize color-color or color-magnitude plots in MOCAdb with the [Substellar Photometry Explorer](/bd-colors?#args#&xaxis_type=color&yaxis_type=absolute_magnitude&yaxis_value_1=mko_jmag&xaxis_value_1=mko_jmag&xaxis_value_2=mko_kmag).\n" + \
" * Visualize the age probability density functions of an association with the [MOCA Association Age Explorer](/age-pdfs?#args#).\n" + \
" * Visualize the age probability density functions of an object with the [MOCA Object Age Explorer](/oage-pdfs?#args#).\n" + \
" * Return to the [MOCAdb website](https://mocadb.ca).\n"

layout = html.Div(
    className="banner",
    children=[
        dcc.Location(id='home-url', refresh=False),
        #html.Img(src=get_asset_url("dash-logo.png")),
        html.H6(children='MOCAdb data visualizations',style={'color':"#000000","backgroundColor":"#DEDDE1", "marginLeft": 0, "width":"100%"}),
        dcc.Markdown(
                id='home-instructions',
                className='row',
                children=[
                    default_text
                ]
                , style={"width": "100%", "whiteSpace": "pre-wrap", "marginLeft": 30, "marginRight": 30, "marginTop": 30,},#, "backgroundColor":"#1F2C56"
            ),
        ],
    style={"width": "100%", "height": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"#F5F8FA"},#, "backgroundColor":"#192444"
    )

@dash.callback(output=Output('home-instructions', 'children'),
    inputs=dict(
        search=Input('home-url', 'search')
    ),
)
def display_page(search):
    
    resulting_url = default_text.replace("#args#",search.replace('?','&'))

    if resulting_url:
        resulting_url = resulting_url.replace('?&', '?')

    return resulting_url