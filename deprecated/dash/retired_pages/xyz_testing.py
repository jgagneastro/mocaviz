import numpy as np

import plotly.graph_objs as go

npoints = 500
radius=50
nlines=10
trace_color='black'
opacity=0.2

#Build 3D grid
phi = np.linspace(0, 2*np.pi,num=npoints)
radii = (np.linspace(0,radius,num=nlines+1))[1:]
phim, radiim = np.meshgrid(phi, radii)

x = np.cos(phim) * radiim
y = np.sin(phim) * radiim
z = phim * 0

# Create the plot
thick = 3
lines = []
line_marker = dict(color=trace_color, width=thick)

# First layer of grid lines
for i, j, k in zip(x, y, z):
    lines.append(go.Scatter3d(x=i, y=j, z=k, mode='lines', line=line_marker, hoverinfo='skip', opacity=opacity, showlegend=False))

#Add 500 pc blue line

opacity=0.5
maxrad = 500
thick = 5
linvec = np.linspace(0,maxrad,num=npoints)
zeros = np.zeros(npoints)

lines.append(go.Scatter3d(x=zeros, y=zeros, z=linvec, mode='lines', line=dict(color='blue', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))
lines.append(go.Scatter3d(x=linvec, y=zeros, z=zeros, mode='lines', line=dict(color='red', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))
lines.append(go.Scatter3d(x=zeros, y=linvec, z=zeros, mode='lines', line=dict(color='green', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))
lines.append(go.Scatter3d(x=zeros, y=zeros, z=-linvec, mode='lines', line=dict(color='black', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))
lines.append(go.Scatter3d(x=-linvec, y=zeros, z=zeros, mode='lines', line=dict(color='black', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))
lines.append(go.Scatter3d(x=zeros, y=-linvec, z=zeros, mode='lines', line=dict(color='black', width=thick), hoverinfo='skip', opacity=opacity, showlegend=False))

go.Figure(data=lines).show()