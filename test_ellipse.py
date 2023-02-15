from plotly.offline import iplot
import plotly.graph_objs as go

from astropy.io import fits

import numpy as np

hdul = fits.open('/Users/jonathan/Documents/IDL/IDL_library/GitHub/banyan_sigma_idl/data/banyan_sigma_parameters.fits')
covar_matrix = hdul[1].data[0]['COVARIANCE_MATRIX'][3:,3:]
offset = hdul[1].data[0]['CENTER_VEC'][3:]

u, s, vh = np.linalg.svd(covar_matrix)
rotmat = np.linalg.inv(u)
#rotmat /= np.linalg.det(u) #Introduces noise
a, b, c = np.sqrt(s)*1.557

phi = np.linspace(0, 2*np.pi,num=20)
theta = np.linspace(-np.pi/2, np.pi/2,num=20)
phi, theta=np.meshgrid(phi, theta)

x = np.cos(theta) * np.sin(phi) * a
y = np.cos(theta) * np.cos(phi) * b
z = np.sin(theta) * c

xf = x
yf = z*b/c
zf = y*c/b

# Creating the plot
lines = []
line_marker = dict(color='#0066FF', width=2)
for i, j, k in zip(x, y, z):
    ir, jr, kr = rotmat@[i,j,k]
    lines.append(go.Scatter3d(x=ir+offset[0], y=jr+offset[1], z=kr+offset[2], mode='lines', line=line_marker, hoverinfo='skip', opacity=0.3))
for i, j, k in zip(xf, yf, zf):
    ir, jr, kr = rotmat@[i,j,k]
    lines.append(go.Scatter3d(x=ir+offset[0], y=jr+offset[1], z=kr+offset[2], mode='lines', line=line_marker, hoverinfo='skip', opacity=0.3))

layout = go.Layout(
    hovermode=False,
    title='Wireframe Plot',
    scene=dict(
        xaxis=dict(
            gridcolor='rgb(255, 255, 255)',
            zerolinecolor='rgb(255, 255, 255)',
            showbackground=True,
            backgroundcolor='rgb(230, 230,230)',
            showspikes=False,
        ),
        yaxis=dict(
            gridcolor='rgb(255, 255, 255)',
            zerolinecolor='rgb(255, 255, 255)',
            showbackground=True,
            backgroundcolor='rgb(230, 230,230)',
            showspikes=False,
        ),
        zaxis=dict(
            gridcolor='rgb(255, 255, 255)',
            zerolinecolor='rgb(255, 255, 255)',
            showbackground=True,
            backgroundcolor='rgb(230, 230,230)',
            showspikes=False,
        )
    ),
    showlegend=False,
)
fig = go.Figure(data=lines, layout=layout)
iplot(fig, filename='wireframe_plot')