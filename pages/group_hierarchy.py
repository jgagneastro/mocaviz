import dash
from dash import html, dcc, callback, Input, Output

#from plotly.offline import iplot
import plotly.graph_objs as go

import numpy as np
import pandas as pd
from mocapy import *

#Register web page in the Dash app
dash.register_page(__name__)

#Set up and query MOCAdb for current group hierarchy
moca = MocaEngine()
df = moca.query("CALL select_aid_hierarchy();")

df.loc[df["original_aid"]=="OTHERS","comments"] = "Groups with two or less direct children defined in a useful way"

#Append "ALL" to the data
df.loc[df['nobj'].isnull(),'nobj'] = 10
df.loc[len(df), ['moca_aid','nobj','parent_aid']] = 'ALL', df[df.parent_aid=='ALL'].nobj.sum(), ''

#Show the group hierarchy sunburst figure
def generate_gh_sunburst():
    
    #layout = go.Layout(
        #clickmode="event+select",
        #uirevision=1, #Prevent the resetting of user-defined zoom level etc.
        #dragmode="lasso",
        #xaxis={'title':xtitle},
        #yaxis={'title':ytitle},
        #showlegend=True,
        #autosize=True,
        #hovermode=hover,
        #hovermode="closest",
        #margin=dict(l=110, r=50, t=50, b=50),
    #    paper_bgcolor='rgba(0,0,0,0)',
    #    plot_bgcolor='rgba(0,0,0,0)',
    #    margin=dict(l=0, r=0, t=0, b=0),
    #)

    fig = go.Figure()

    text_list = list(
        map(
            lambda x1, x2, x3, x4, x5, x6, x7, x8, x9: "Other names : "+str(x1)+"<br>Type : "+str(x2)+"<br>Age : "+str(x3)+" Myr, "+str(x4)+"<br>Distance : "+str(x5)+" pc"+("<br>Only a subset of this group overlaps with parent" if x6==1 else "")+("<br>Complete Overlap with Parent" if x7 == 1 else "")+"<br>Relationship Comments : "+str(x8).replace(".",".<br>").replace("al.<br> ","al. ")+"<br>Comments : "+str(x9).replace(".",".<br>").replace("al.<br> ","al. "),
            df["alternate_names"],
            df["physical_nature"],
            df["age_myr"],
            df["age_ref"],
            df["avg_dist"],
            df["partial_subgroup_overlap"],
            df["complete_parent_overlap"],
            df["relationship_comments"],
            df["comments"],
        ))

    data = go.Sunburst(
        labels=df['moca_aid'],
        parents=df['parent_aid'],
        #data_frame=df,
        #labels='moca_aid',
        #parents='parent_aid',
        #customdata=df,
        #hovertemplate="Price: %{y:$.2f}",
        #hover_name=df['moca_aid'],
        #hover_data=
        hovertext=text_list,
        #values=df['nobj'].values,
        )
    
    fig.add_trace(data)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),plot_bgcolor='rgba(0,0,0,0)')#,paper_bgcolor='rgba(0,0,0,0)'
    #import pdb; pdb.set_trace()

    #fig = go.Figure(data=data, layout=layout)
    return fig

#fig.show()

figure_export_config = {
  'toImageButtonOptions': {
    'format': 'png', # one of png, svg, jpeg, webp
    'height': 500*2,
    'width': 700*2,
    'scale': 6*2 # Multiply title/legend/axis/canvas sizes by this factor
  }
}

def gh_build_banner():
    return html.Div(
        id="gh-banner",
        className="banner",
        children=[
            #html.Img(src=app.get_asset_url("dash-logo.png")),
            html.H6("Hierarchical breakdown of MOCA associations ",style={'color':"#000000","backgroundColor":"#DEDDE1", "marginLeft": 0, "width":"100%"}),
        ],
    )

#Page layout
layout = html.Div(
    className="twelve columns",
    #id="top-row",
    children=[
        #gh_build_banner(),
        #html.H1(children='MOCAdb associations hierarchical breakdown'),
    	# dcc.Markdown(
     #        #html.P(
     #            id="gh-instructions",
     #            children=[
     #                "This page shows the hierarchical structures of subgroups in MOCAdb, ignoring duplicates, deprecated assocations, and associations without parents or children. Click on a young association to center the sunburst diagram on the association in question. More information on the short association names can be found [here](https://mocadb.ca/associations).",
     #            ]
     #            , style={"width": "100%", "whiteSpace": "pre-wrap", "backgroundColor":"#F5F8FA"},#, "color":"white"
     #        ),
    	# html.Br(),
        dcc.Graph(id="gh-sunburst",config=figure_export_config, figure=generate_gh_sunburst(), style={"height" : "100vh"}),#"width": "100%"
])


# @dash.callback(
#     Output(component_id='analytics-output', component_property='children'),
#     Input(component_id='analytics-input', component_property='value')
# )
# def update_city_selected(input_value):
#     return f'You selected: {input_value}'


