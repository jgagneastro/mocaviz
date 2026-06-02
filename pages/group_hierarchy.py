import dash
from dash import html, dcc, callback, Input, Output, State
from urllib.parse import urlparse, parse_qs
from sqlalchemy import create_engine

#from plotly.offline import iplot
import plotly.graph_objs as go

import numpy as np
import pandas as pd
from utils.mocapy_compat import patch_pandas_sql_private_api

patch_pandas_sql_private_api()
from mocapy import *

#Register web page in the Dash app
dash.register_page(__name__)

default_title = 'Click on a graph node to explore children and other data visualization tools.'

#Show the group hierarchy sunburst figure
def generate_gh_sunburst(df, aid_select):

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

    if aid_select is None:
        aid_select = 'ALL'
    #print(aid_select)

    text_list = list(
        map(
            lambda x1, x2, x3, x4, x5, x6, x7, x8, x9, x10: str(x10)+"<br>Other names : "+str(x1)+"<br>Type : "+str(x2)+"<br>Age : "+str(x3)+" Myr, "+str(x4)+"<br>Distance : "+str(x5)+" pc"+("<br>Only a subset of this group overlaps with parent" if x6==1 else "")+("<br>Complete Overlap with Parent" if x7 == 1 else "")+"<br>Relationship Comments : "+str(x8).replace(". ",".<br>").replace("al.<br> ","al. ")+"<br>Comments : "+str(x9).replace(". ",".<br>").replace("al.<br> ","al. "),
            df["alternate_names"],
            df["physical_nature"],
            df["age_myr"],
            df["age_ref"],
            df["avg_dist"],
            df["partial_subgroup_overlap"],
            df["complete_parent_overlap"],
            df["relationship_comments"],
            df["comments"],
            df["name"],
        ))
    #import pdb; pdb.set_trace()
    #df["url"] = np.char.add("<a href=https://www.google.com>",np.char.add(df["original_aid"].to_numpy().astype("str"),"</a>"))
    data = go.Sunburst(
        labels=df['moca_aid'],
        parents=df['parent_aid'],
        level=aid_select,
        #text=df['url'],
        #data_frame=df,
        #labels='moca_aid',
        #parents='parent_aid',
        customdata=df['original_aid'],
        #customdata=np.stack((df['original_aid'], df['child_aid']), axis=-1),
        #hovertemplate="Price: %{y:$.2f}",
        #hover_name=df['moca_aid'],
        #hover_data=
        hovertext=text_list,
        #values=df['nobj'].values,
        )
    
    fig.add_trace(data)
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),plot_bgcolor='rgba(0,0,0,0)')#,paper_bgcolor='rgba(0,0,0,0)'

    #Useful for paper figures
    fig.update_layout(uniformtext=dict(minsize=8))
    
    #import pdb; pdb.set_trace()

    #fig = go.Figure(data=data, layout=layout)
    return fig

#fig.show()

figure_export_config = {
  'toImageButtonOptions': {
    'format': 'png', # one of png, svg, jpeg, webp
    'height': 500*2,
    'width': 700*2,
    'scale': 6 # Multiply title/legend/axis/canvas sizes by this factor
  }
}

# def gh_build_banner():
#     return html.Div(
#         id="gh-banner",
#         className="banner",
#         children=[
#             #html.Img(src=app.get_asset_url("dash-logo.png")),
#             html.H6("Hierarchical breakdown of MOCA associations ",style={'color':"#000000","backgroundColor":"#DEDDE1", "marginLeft": 0, "width":"100%"}),
#         ],
#     )

#Page layout
layout = html.Div(
    className="twelve columns",
    id="gh-div",
    #style={"width": "100%", "whiteSpace": "pre-wrap", "align":"center"},
    #n_clicks=0,
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
        dcc.Location(id="url", refresh=False),
        dcc.Markdown(id="gh-title",children=default_title),#,style={"width": "100%", "whiteSpace": "pre-wrap", "align":"center"}
        #dcc.Graph(id="gh-sunburst",config=figure_export_config, figure=generate_gh_sunburst(), style={"height" : "100vh"}),#"width": "100%"
        dcc.Graph(id="gh-sunburst",config=figure_export_config, style={"height" : "100vh"}),#"width": "100%"
        html.Div(id='dummy_div'),
])

@dash.callback(
    output=Output("gh-title", "children"),
    inputs=dict(
        #selections=selections,
        clickdata=Input("gh-sunburst", "clickData"),
    ),
    state=dict(url_search=State("url", "search"),self_figure=State("gh-sunburst", "figure")),
)
def gh_callback(clickdata, url_search, self_figure):
    
    if clickdata is not None:

        url_add = ""
        user = None
        pwd = None
        dbase = None
        if url_search != "":
            parsed_url = urlparse(url_search)
            parsed_url_data = parse_qs(parsed_url.query)
            if ('user' in parsed_url_data.keys()) & ('pwd' in parsed_url_data.keys()) & ('dbase' in parsed_url_data.keys()):
                user = parsed_url_data['user'][0]
                pwd = parsed_url_data['pwd'][0]
                dbase = parsed_url_data['dbase'][0]
                url_add = "&user="+user+"&pwd="+pwd+"&dbase="+dbase

        #Set up and query MOCAdb for clean lists of children
        moca = MocaEngine()

        #Substitute MOCA engine's connection if credentials are provided
        if user is not None and pwd is not None and dbase is not None:
            engine = create_engine('mysql+pymysql://'+user+':'+pwd.replace('%','%25').replace('@','%40').replace(">","%3E").replace("#","%23").replace("_","%5F")+'@104.248.106.21/'+dbase)

            # This is only required for CALL statements
            raw_con = engine.raw_connection()
            moca.raw_connection = raw_con

            # This is required for all queries
            con = engine.connect()
            moca.connection = con

        dfrel = moca.query("CALL list_association_children();")
        clean_children_list = dfrel.loc[dfrel['moca_aid']==clickdata['points'][0]['customdata'],'clean_children'].values

        child_aid = ""
        if len(clean_children_list) != 0:
            child_aid = ","+clean_children_list[0]

        label = clickdata['points'][0]['customdata']
        if label is not None:
            text = "You have clicked on the "+label+" branch.\n Click on the central node to go up a hiearchical level.\n\n Click [here](https://mocadb.ca/search/results?search-query="+label+"&search-type=association) to open a MOCA report for this association.\n\n Click [here](https://dataviz.mocadb.ca/xyzuvw?axes=xyz&asso="+label+child_aid+"&mtid=BF,HM,CM"+url_add+") to open a 3D XYZ map of this branch.\n\n Click [here](https://mocadb.ca/query?query=SELECT+sam.*+FROM+summary_all_members+sam+LEFT+JOIN+moca_membership_types+mmt+ON(mmt.moca_mtid=sam.moca_mtid)+WHERE+moca_aid='"+label+"'+ORDER+BY+mmt.level+DESC,sam.sptn+ASC) to obtain a full list of members for this association.\n\n Use Command + click to open links in a new tab."
            return text
        #np.char.add("<a href=https://www.google.com>",np.char.add(df["original_aid"].to_numpy().astype("str"),"</a>"))

    return default_title

# Update Hierarchy graph once - the dummy trigger is the solution I found to allow reading the URL
@dash.callback(
    output=Output("gh-sunburst", "figure"),
    inputs=dict(
        dummy=Input("dummy_div", "children"),
    ),
    state=dict(url_search=State("url", "search")),
)
def update_gh_figure(dummy, url_search):
    
    #print("GH callback")
    aid_select = 'ALL'
    user = None
    pwd = None
    dbase = None
    url_add = None
    if url_search != "":
        parsed_url = urlparse(url_search)
        parsed_url_data = parse_qs(parsed_url.query)
        if 'asso' in parsed_url_data.keys():
            aid_select = parsed_url_data['asso'][0]
        else:
            aid_select = 'ALL'
        if 'user' in parsed_url_data.keys():
            user = parsed_url_data['user'][0]
        if 'pwd' in parsed_url_data.keys():
            pwd = parsed_url_data['pwd'][0]
        if 'dbase' in parsed_url_data.keys():
            dbase = parsed_url_data['dbase'][0]

    #Set up and query MOCAdb for current group hierarchy
    moca = MocaEngine()

    #Substitute MOCA engine's connection if credentials are provided
    if user is not None and pwd is not None and dbase is not None:
        engine = create_engine('mysql+pymysql://'+user+':'+pwd.replace('%','%25').replace('@','%40').replace(">","%3E").replace("#","%23").replace("_","%5F")+'@104.248.106.21/'+dbase)

        # This is only required for CALL statements
        raw_con = engine.raw_connection()
        moca.raw_connection = raw_con

        # This is required for all queries
        con = engine.connect()
        moca.connection = con

    df = moca.query("CALL select_aid_hierarchy();")
    df.loc[df["original_aid"]=="OTHERS","comments"] = "Groups with two or less direct children defined in a useful way"

    #Append "ALL" to the data
    df.loc[df['nobj'].isnull(),'nobj'] = 10
    df.loc[len(df), ['moca_aid','nobj','parent_aid']] = 'ALL', df[df.parent_aid=='ALL'].nobj.sum(), ''

    # Missing parents (allow root parent as empty string only). Instead of erroring,
    # synthesize root nodes for any missing parents so the sunburst can render.
    ids = set(df["moca_aid"].tolist())
    missing_parents = sorted({p for p in df["parent_aid"] if p != "" and p not in ids})
    if missing_parents:
        # Build one empty-row per missing parent, with parent_aid set to root ""
        synth_rows = []
        for p in missing_parents:
            new_row = {col: None for col in df.columns}
            new_row["moca_aid"] = str(p)
            new_row["parent_aid"] = ""
            synth_rows.append(new_row)
        if synth_rows:
            df = pd.concat([df, pd.DataFrame(synth_rows)], ignore_index=True)

    return generate_gh_sunburst(df, aid_select)

# @dash.callback(
#     output=Output("gh-sunburst", "data"),
#     inputs=dict(
#         url_search=Input("url", "search"),
#     ),
#     #state=dict(self_figure=State("gh-sunburst", "figure")),
# )
# def url_callback(url_search):
#     if clickdata is not None:
#         #import pdb; pdb.set_trace()
#         label = clickdata['points'][0]['customdata']
#         text = "You are now viewing the "+label+" branch.\n Click on the central node to go up a hiearchical level.\n\n Click [here](https://mocadb.ca/search/results?search-query="+label+"&search-type=association) to open a MOCA report for this association.\n Click [here](https://dataviz.mocadb.ca/xyzuvw?axes=xyz&asso="+label+"&mtid=BF,HM,CM) to open a 3D XYZ map of this branch.\n\n Use Command + click to open links in a new tab."
#         return text
#         #np.char.add("<a href=https://www.google.com>",np.char.add(df["original_aid"].to_numpy().astype("str"),"</a>"))

#     return default_title

# url_search = State("url","search")
#     if url_search != "":
#         parsed_url = urlparse(url_search)
#         parsed_url_data = parse_qs(parsed_url.query)
#         if 'asso' in parsed_url_data.keys():
#             aid_select = parsed_url_data['asso'][0]
#         else:
#             aid_select = 'ALL'

#     import pdb; pdb.set_trace()
