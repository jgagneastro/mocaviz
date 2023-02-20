from plotly.offline import iplot
import plotly.graph_objs as go
import plotly.express as px 

from astropy.io import fits

import numpy as np
import pandas as pd
from mocapy import *

moca = MocaEngine()

df = moca.query("CALL select_aid_hierarchy();")

#Append "ALL"
#df = df.append({'moca_aid':'ALL'},ignore_index=True)
df.loc[df['nobj'].isnull(),'nobj'] = 10
df.loc[len(df), ['moca_aid','nobj','parent_aid']] = 'ALL', df[df.parent_aid=='ALL'].nobj.sum(), ''
#df.loc[-1,"nobj"] = df[df.parent_aid=='ALL'].nobj.sum()
#df = df.drop(columns='child_aid')

#df = df[df.moca_aid != 'PIPE']
#df = df[df.moca_aid != 'THEIA17']

#df = df[~df.child_aid.isnull()]

#import pdb; pdb.set_trace()

#df = df[~((df['moca_aid'].str.contains('S')) & (df['parent_aid']=='ALL'))]
#df = df[~((df['parent_aid'].str.contains('S')))]

#df = df[~(~(df['moca_aid'].str.contains('S')) & (df['parent_aid']=='ALL'))]
#df = df[((df['parent_aid'].str.contains('S')))]


# df2 = df[(
#     (df['moca_aid']== 'ALL') | (df['parent_aid']== 'ALL')
#     | (df['parent_aid']== 'POB3')
#     | (df['parent_aid']== 'GRSCO')
#     | (df['parent_aid']== 'SCOCEN')
#     | (df['parent_aid']== 'SUMA')
#     | (df['parent_aid']== 'STHOR')
#     | (df['parent_aid']== 'SPLE')
#     | (df['parent_aid']== 'SPL9')
#     | (df['parent_aid']== 'SPL8')
#     | (df['parent_aid']== 'SPL5')
#     | (df['parent_aid']== 'SPL3')
#     | (df['parent_aid']== 'SOH59')
#     | (df['parent_aid']== 'SOH51')
#     | (df['parent_aid']== 'SOH23')
#     | (df['parent_aid']== 'SNGC2451A')
#     | (df['parent_aid']== 'SIC2602')
#     | (df['parent_aid']== 'SIC2391')
#     | (df['parent_aid']== 'SHYA')
#     | (df['parent_aid']== 'SCBER')
#     | (df['parent_aid']== 'SBL1')
#     | (df['parent_aid']== 'SASCC123')
#     | (df['parent_aid']== 'PERS')
#     | (df['parent_aid']== 'MSW')
#     | (df['parent_aid']== 'CMUSC')
#     | (df['parent_aid']== 'OCT')
#     | (df['parent_aid']== 'CPL9')
#     | (df['parent_aid']== 'ABDMG')
#     | (df['parent_aid']== 'CUMA')
#     | (df['parent_aid']== 'SAPER')
#     | (df['parent_aid']== 'CAPER')
#     | (df['parent_aid']== 'GRORI')
#     | (df['parent_aid']== 'ORIC')
#     | (df['parent_aid']== 'GRORIS1')
#     )
#     ]

# dfnot = df[~(
#     (df['moca_aid']== 'ALL') | (df['parent_aid']== 'ALL')
#     | (df['parent_aid']== 'POB3')
#     | (df['parent_aid']== 'GRSCO')
#     | (df['parent_aid']== 'SCOCEN')
#     | (df['parent_aid']== 'SUMA')
#     | (df['parent_aid']== 'STHOR')
#     | (df['parent_aid']== 'SPLE')
#     | (df['parent_aid']== 'SPL9')
#     | (df['parent_aid']== 'SPL8')
#     | (df['parent_aid']== 'SPL5')
#     | (df['parent_aid']== 'SPL3')
#     | (df['parent_aid']== 'SOH59')
#     | (df['parent_aid']== 'SOH51')
#     | (df['parent_aid']== 'SOH23')
#     | (df['parent_aid']== 'SNGC2451A')
#     | (df['parent_aid']== 'SIC2602')
#     | (df['parent_aid']== 'SIC2391')
#     | (df['parent_aid']== 'SHYA')
#     | (df['parent_aid']== 'SCBER')
#     | (df['parent_aid']== 'SBL1')
#     | (df['parent_aid']== 'SASCC123')
#     | (df['parent_aid']== 'PERS')
#     | (df['parent_aid']== 'MSW')
#     | (df['parent_aid']== 'CMUSC')
#     | (df['parent_aid']== 'OCT')
#     | (df['parent_aid']== 'CPL9')
#     | (df['parent_aid']== 'ABDMG')
#     | (df['parent_aid']== 'CUMA')
#     | (df['parent_aid']== 'SAPER')
#     | (df['parent_aid']== 'CAPER')
#     | (df['parent_aid']== 'GRORI')
#     | (df['parent_aid']== 'ORIC')
#     | (df['parent_aid']== 'GRORIS1')
#     )
#     ]

# df = df2

# import pdb; pdb.set_trace()

#df = df[(df['moca_aid']== 'SPLE') | (df['moca_aid']== 'ABDMG') | (df['parent_aid'] == 'ABDMG') | (df['moca_aid']== 'USCO') | (df['parent_aid'] == 'USCO') | (df['moca_aid'] == 'ALL') | (df['moca_aid']== 'SCOCEN') | (df['parent_aid'] == 'SCOCEN')  | (df['moca_aid'] == 'GRSCO') ]
#df = df[(df['moca_aid']== 'USCO') | (df['parent_aid'] == 'USCO') | (df['moca_aid'] == 'ALL') | (df['moca_aid']== 'SCOCEN') | (df['parent_aid'] == 'SCOCEN') | (df['parent_aid'] == 'GRSCO') | (df['moca_aid'] == 'GRSCO') ]
#df = df[(df['moca_aid']== 'SPLE') | (df['moca_aid']== 'ABDMG') | (df['parent_aid'] == 'ABDMG') | (df['moca_aid'] == 'ALL')]

df.to_csv('test_hierarchy.csv')

#df = pd.read_csv('test_hierarchy.csv')
#df.loc[df.moca_aid=='ALL','parent_aid'] = ''

#df = pd.read_csv('/Users/jonathan/Downloads/dp-export-120637.csv')
#df.loc[df['Item and Group']=='All items','Parent'] = ''
#fig2 = px.sunburst(df, path=['Parent', 'Item and Group'], values='Weight', color='Parent')

# df2 = df.iloc[0].copy()
# df2["moca_aid"] = "ALL"
# df2["nobj"] = df[df.parent_aid=='ALL'].nobj.sum()
# df2["child_aid"] = ",".join(df[df.parent_aid=='ALL'].moca_aid.values)
# df2["parent_aid"] = ""
#df = pd.concat([df,df2])

fig = go.Figure(go.Sunburst(
    labels=df['moca_aid'].values,
    parents=df['parent_aid'].values,
    #values=df['nobj'].values,
    )
)
#import pdb; pdb.set_trace()
#fig = go.Figure(go.Sunburst(labels=df['Item and Group'].values,parents=df['Parent'].values))

# fig =go.Figure(go.Sunburst(
#     labels=["Eve", "Cain", "Seth", "Enos", "Noam", "Abel", "Awan", "Enoch", "Azura"],
#     parents=["", "Eve", "Enoch", "Seth", "Seth", "Eve", "Eve", "Awan", "Eve" ],
#     #values=[10, 14, 12, 10, 2, 6, 6, 4, 4],
# ))
fig.show()


#fig2 = px.sunburst(df, path=['parent_aid', 'moca_aid'], values='nobj', color='parent_aid')
#fig2.update_layout(title_text="Sunburst Diagram", font_size=10)
#fig2.show()
