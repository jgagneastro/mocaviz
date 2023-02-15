#import plotly.plotly as py
from plotly.offline import iplot
import plotly.graph_objs as go

from astropy.io import fits

import numpy as np

# # Creating the data
# x = np.linspace(-5, 5, 50)
# y = np.linspace(-5, 5, 50)
# xGrid, yGrid = np.meshgrid(y, x)
# R = np.sqrt(xGrid ** 2 + yGrid ** 2)
# z = np.sin(R)

hdul = fits.open('/Users/jonathan/Documents/IDL/IDL_library/GitHub/banyan_sigma_idl/data/banyan_sigma_parameters.fits')
covar_matrix = hdul[1].data[0]['COVARIANCE_MATRIX'][3:,3:]
offset = hdul[1].data[0]['CENTER_VEC'][3:]

u, s, vh = np.linalg.svd(covar_matrix)
rotmat = np.linalg.inv(u)
#rotmat /= np.linalg.det(u)
a, b, c = np.sqrt(s)*1.557

phi = np.linspace(0, 2*np.pi,num=20)
theta = np.linspace(-np.pi/2, np.pi/2,num=20)
phi, theta=np.meshgrid(phi, theta)

x = np.cos(theta) * np.sin(phi) * a
y = np.cos(theta) * np.cos(phi) * b
#xGrid, yGrid = np.meshgrid(y, x)
z = np.sin(theta) * c

#import pdb; pdb.set_trace()

xf = x
yf = z*b/c
zf = y*c/b

# Creating the plot
lines = []
line_marker = dict(color='#0066FF', width=2)
#for i, j, k in zip(xGrid, yGrid, z):
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






# import numpy as np
# import plotly.graph_objs as go
# import pyvista as pv  #pip install pyvista


# def pcloud(points3d, marker_size=1.5,  marker_color='#454F8C'):
#     #define the trace representing the point cloud
#     points3d=np.asarray(points3d)
#     if points3d.ndim != 2  or points3d.shape[1] != 3:
#         raise ValueError('your data is not a 3D point cloud')
#     return go.Scatter3d(
#                 name='',
#                 mode='markers',
#                 x=points3d[:,0],
#                 y=points3d[:,1], 
#                 z=points3d[:,2],
#                 marker_size=marker_size,
#                 marker_color=marker_color
#                )

# def get_mesh(points3d, faces,   color='lightblue',  opacity=1):
#     # define the Mesh3d representing the alpha-shape
#     points3d=np.asarray(points3d)
#     if points3d.ndim != 2  or points3d.shape[1] != 3:
#         raise ValueError('your data is not a 3D point cloud')  
#     faces = np.asarray(faces)
#     i, j, k = np.asarray(faces).T
#     return  go.Mesh3d(
#                 color=color,
#                 opacity=opacity,
#                 i=i, j=j, k=k,
#                 x =points3d[:,0],
#                 y= points3d[:,1], 
#                 z= points3d[:,2],
#                 flatshading=True
#                         )               


# def alphashape3d(points3d, alpha=1):
#     #extract  0, 1, 2, 3-simplices of the  alpha shape constructed from points3d
#     # Here alpha =1/alphahull, where alphahull is a property of a Plotly alpha shape
#     cloud = pv.PolyData(points3d) 
#     mesh = cloud.delaunay_3d(alpha=alpha)
#     unconnected_points3d = []  #isolated 0-simplices
#     edges = [] # isolated edges, 1-simplices
#     faces = []  # triangles that are not faces of some tetrahedra
#     tetrahedra = []  # 3-simplices
#     for k  in mesh.offset:
#         length = mesh.cells[k] 
#         if length == 2:
#             edges.append(list(mesh.cells[k+1: k+length+1]))
#         elif length ==3:
#             faces.append(list(mesh.cells[k+1: k+length+1]))
#         elif length == 4:
#             tetrahedra.append(list(mesh.cells[k+1: k+length+1]))
#         elif length == 1:
#             unconnected_points3d.append(mesh.cells[k+1])
#         else:  
#             raise ValueError('For a 3d point cloud only unconneted points3d, edges,\
#                              triangles and tetrahedra are set up') 
      
#     return unconnected_points3d, edges, faces, tetrahedra

# def get_tetrahedra_faces(tetrahedra, faces):
#     # extract tetrahedra faces and append them to the existing faces
#     for t in tetrahedra:
#         faces.extend([[t[0], t[1], t[2]],
#                       [t[0], t[2], t[3]],
#                       [t[0], t[3], t[1]],
#                       [t[1], t[2], t[3]]])
#     return faces  


# def edge_trace(points, edges):
#     # define the trace for isolated edges of an alpha shape
#     Xe = []
#     Ye = []
#     Ze = []
#     for e in edge:
#         Xe.extend([points[e[0], 0], points[e[1], 0], None])
#         Ye.extend([points[e[0], 1], points[e[1], 1], None])
#         Ze.extend([points[e[0], 2], points[e[1], 2], None])
#     return go.Scatter3d(x=Xe, y=Ye, z=Ze, 
#                           mode='lines', 
#                           line_width=1, 
#                           line_color='rgb(50,50,50)')   

# ######################################################################################
# pts = np.loadtxt(np.DataSource().open('https://raw.githubusercontent.com/empet/Plotly-plots/master/Data/data-file.txt'))
# alpha= 0.5

# title = f'Alpha Shape of a 3D Point Cloud<br>alpha={alpha}'

# scatt =  pcloud(pts,  marker_color='#454F8C', marker_size=3)

# #Extract the simplicial structure of the alpha shape defined via pyvista
# unconnected_points, edges,  faces, tetrahedra = alphashape3d(pts, alpha=alpha)
# faces = get_tetrahedra_faces(tetrahedra, faces)
# alphashape = get_mesh(pts, faces, opacity=1)
# fig1 = go.Figure(data =[scatt, alphashape])
# fig1.update_layout(title_text=title, title_x=0.5, width=800, height=800)
# fig1.show()






# # # from plotly.offline import iplot, init_notebook_mode
# # # from plotly.graph_objs import Mesh3d
# # # import numpy as np

# # # # some math: generate points on the surface of the ellipsoid

# # # phi = np.linspace(0, 2*np.pi,num=10)
# # # theta = np.linspace(-np.pi/2, np.pi/2,num=10)
# # # phi, theta=np.meshgrid(phi, theta)

# # # x = np.cos(theta) * np.sin(phi) * 3
# # # y = np.cos(theta) * np.cos(phi) * 2
# # # z = np.sin(theta)

# # # # to use with Jupyter notebook

# # # #init_notebook_mode()

# # # iplot([Mesh3d({
# # #                 'x': x.flatten(), 
# # #                 'y': y.flatten(), 
# # #                 'z': z.flatten(), 
# # #                 'alphahull': 0,
# # #                 'opacity': 0.5,
# # # })])


# # import plotly.graph_objects as go
# # import numpy as np
# # from plotly.offline import iplot

# # i = [7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2]
# # j = [3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3]
# # k = [0, 7, 2, 3, 6, 7, 1, 1, 5, 5, 7, 6]

# # triangles = np.vstack((i,j,k)).T

# # # x = [0, 0, 1, 1, 0, 0, 1, 1]
# # # y = [0, 1, 1, 0, 0, 1, 1, 0]
# # # z = [0, 0, 0, 0, 1, 1, 1, 1]

# # phi = np.linspace(0, 2*np.pi,num=10)
# # theta = np.linspace(-np.pi/2, np.pi/2,num=10)
# # phi, theta=np.meshgrid(phi, theta)

# # x = np.cos(theta) * np.sin(phi) * 3
# # y = np.cos(theta) * np.cos(phi) * 2
# # z = np.sin(theta)

# # vertices = np.vstack((x,y,z)).T
# # tri_points = vertices[triangles]

# # #extract the lists of x, y, z coordinates of the triangle vertices and connect them by a line
# # Xe = []
# # Ye = []
# # Ze = []
# # for T in tri_points:
# #     Xe.extend([T[k%3][0] for k in range(4)]+[ None])
# #     Ye.extend([T[k%3][1] for k in range(4)]+[ None])
# #     Ze.extend([T[k%3][2] for k in range(4)]+[ None])
       
# # #define the trace for triangle sides
# # iplot([go.Scatter3d(
# #                    x=Xe,
# #                    y=Ye,
# #                    z=Ze,
# #                    mode='lines',
# #                    name='',
# #                    line=dict(color= 'rgb(70,70,70)', width=3))])