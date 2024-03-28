import plotly.graph_objs as go

fig = go.Figure(data=go.Scatter3d(
    x=[100, 200, 300, 400, 500],
    y=[100, 200, 300, 400, 500],
    z=[100, 200, 300, 400, 500],
    mode='markers',
    marker=dict(
        size=10,
        color='blue'
    )
))

fig.update_layout(scene=dict(
        xaxis=dict(range=[-10000, 10000]),
        yaxis=dict(range=[-10000, 10000]),
        zaxis=dict(range=[-10000, 10000]),
        aspectratio=dict(x=1, y=1, z=1),
        camera=dict(
            eye=dict(x=1.2, y=1.2, z=1.2),
            projection=dict(type='orthographic')
        )
    ))

fig.show()
