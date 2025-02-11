import numpy as np
import plotly.graph_objs as go
import numpy as np
import plotly.graph_objects as go
from scipy.stats import multivariate_normal
from skimage.measure import marching_cubes

# Build 3D ellipsoids to show BANYAN models
def build_ellipsoid_3d(offset, covar_matrix, trace_color, opacity=0.5):
    
    #Build rotation matrix with singular value decomposition
    u, s, vh = np.linalg.svd(covar_matrix)
    rotmat = u
    
    #3D version of 68% volume inclusion requires a factor 1.557
    #inverf((erf(1d0/sqrt(2d0)))^(1d0/3))*sqrt(2d0)
    a, b, c = np.sqrt(s)*1.557

    #Build 3D grid
    phi = np.linspace(0, 2*np.pi,num=20)
    theta = np.linspace(-np.pi/2, np.pi/2,num=20)
    phi, theta=np.meshgrid(phi, theta)

    x = np.cos(theta) * np.sin(phi) * a
    y = np.cos(theta) * np.cos(phi) * b
    z = np.sin(theta) * c

    xf = x
    yf = z*b/c
    zf = y*c/b

    # Create the plot
    lines = []
    line_marker = dict(color=trace_color, width=2)
    
    # First layer of grid lines
    for i, j, k in zip(x, y, z):
        ir, jr, kr = rotmat@[i,j,k]
        lines.append(go.Scatter3d(x=ir+offset[0], y=jr+offset[1], z=kr+offset[2], mode='lines', line=line_marker, hoverinfo='skip', opacity=opacity, showlegend=False))
    
    # Second layer of grid lines rotated by 90 degrees
    for i, j, k in zip(xf, yf, zf):
        ir, jr, kr = rotmat@[i,j,k]
        lines.append(go.Scatter3d(x=ir+offset[0], y=jr+offset[1], z=kr+offset[2], mode='lines', line=line_marker, hoverinfo='skip', opacity=opacity, showlegend=False))

    return lines

# Eventually move this to a subroutine
def build_graph_title(title):
    return html.P(className="graph-title", children=title)

def build_solar_neighborhood_3d(radius=50, nlines=10, trace_color='black', opacity=0.2, npoints=500):
    
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

    return lines

# Automatically determine the bounding box based on Gaussian parameters
def compute_grid_limits(components, sigma_scale=10):
    """
    Compute dynamic grid limits based on the GMM component parameters.
    
    Args:
    - components: List of Gaussian components (dicts with 'mean' and 'cov').
    - sigma_scale: How many standard deviations to include in limits.
    
    Returns:
    - x_min, x_max, y_min, y_max, z_min, z_max
    """
    all_means = np.array([comp["mean"] for comp in components])  # (N, 3)
    all_covs = np.array([comp["cov"] for comp in components])  # (N, 3, 3)
    
    # Compute standard deviations from covariance matrices
    all_sigmas = np.array([np.sqrt(np.diag(cov)) for cov in all_covs])  # (N, 3)

    # Compute limits
    min_bounds = np.min(all_means - sigma_scale * all_sigmas, axis=0)
    max_bounds = np.max(all_means + sigma_scale * all_sigmas, axis=0)

    return min_bounds[0], max_bounds[0], min_bounds[1], max_bounds[1], min_bounds[2], max_bounds[2]

def build_gmm_density_3d(components, trace_color, opacity=0.5, contour_level=0.9, mesh=True):
    
    # Define dynamic grid limits based on GMM parameters
    x_min, x_max, y_min, y_max, z_min, z_max = compute_grid_limits(components, sigma_scale=5)
    num_points = 50

    # Create a 3D grid
    x = np.linspace(x_min, x_max, num_points)
    y = np.linspace(y_min, y_max, num_points)
    z = np.linspace(z_min, z_max, num_points)
    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

    # Compute GMM density
    density = np.zeros(X.shape)
    for comp in components:
        weight = comp["weight"]
        mean = comp["mean"]
        cov = comp["cov"]
        rv = multivariate_normal(mean=mean, cov=cov)
        density += weight * rv.pdf(np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])).reshape(X.shape)

    # Find the 10% probability threshold
    #iso_level = np.percentile(density, 10)  # 10% density contour

    # Sort density values in descending order
    sorted_density = np.sort(density.ravel())[::-1]  

    # Compute cumulative sum and normalize
    cumulative_sum = np.cumsum(sorted_density)
    cumulative_sum /= cumulative_sum[-1]  # Normalize to total probability mass

    # Find the isosurface threshold where 68% of the density is enclosed
    iso_level_index = np.searchsorted(cumulative_sum, contour_level)
    iso_level = sorted_density[iso_level_index]  # Get the density value at this threshold

    # Compute the isosurface mesh using Marching Cubes
    verts, faces, _, _ = marching_cubes(density, level=iso_level)

    # Convert voxel coordinates to real space
    verts_real = np.column_stack([
        np.interp(verts[:, 0], (0, num_points - 1), (x_min, x_max)),
        np.interp(verts[:, 1], (0, num_points - 1), (y_min, y_max)),
        np.interp(verts[:, 2], (0, num_points - 1), (z_min, z_max))
    ])
    
    if mesh is False:
        lines = [go.Mesh3d(
            x=verts_real[:, 0], y=verts_real[:, 1], z=verts_real[:, 2],
            i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
            color=trace_color, opacity=opacity,
        )]
        return lines

    # Extract structured mesh lines for the grid
    edges_xy = set()  # XY-plane (constant Z)
    edges_xz = set()  # XZ-plane (constant Y)
    edges_yz = set()  # YZ-plane (constant X)

    for face in faces:
        for i in range(3):
            v1, v2 = sorted([face[i], face[(i + 1) % 3]])  # Ensure unique ordering
            if np.isclose(verts[v1, 2], verts[v2, 2]):  # Same Z => XY-plane grid
                edges_xy.add((v1, v2))
            if np.isclose(verts[v1, 1], verts[v2, 1]):  # Same Y => XZ-plane grid
                edges_xz.add((v1, v2))
            if np.isclose(verts[v1, 0], verts[v2, 0]):  # Same X => YZ-plane grid
                edges_yz.add((v1, v2))

    edges_xy = np.array(list(edges_xy))
    edges_xz = np.array(list(edges_xz))
    edges_yz = np.array(list(edges_yz))

    # Prepare line segments for structured grid
    edge_x_xy, edge_y_xy, edge_z_xy = [], [], []
    for edge in edges_xy:
        v1, v2 = edge
        edge_x_xy.extend([verts_real[v1, 0], verts_real[v2, 0], None])
        edge_y_xy.extend([verts_real[v1, 1], verts_real[v2, 1], None])
        edge_z_xy.extend([verts_real[v1, 2], verts_real[v2, 2], None])

    edge_x_xz, edge_y_xz, edge_z_xz = [], [], []
    for edge in edges_xz:
        v1, v2 = edge
        edge_x_xz.extend([verts_real[v1, 0], verts_real[v2, 0], None])
        edge_y_xz.extend([verts_real[v1, 1], verts_real[v2, 1], None])
        edge_z_xz.extend([verts_real[v1, 2], verts_real[v2, 2], None])

    edge_x_yz, edge_y_yz, edge_z_yz = [], [], []
    for edge in edges_yz:
        v1, v2 = edge
        edge_x_yz.extend([verts_real[v1, 0], verts_real[v2, 0], None])
        edge_y_yz.extend([verts_real[v1, 1], verts_real[v2, 1], None])
        edge_z_yz.extend([verts_real[v1, 2], verts_real[v2, 2], None])

    lines = []
    line_marker = dict(color=trace_color, width=2)
    
    # Add XY-plane aligned grid (horizontal mesh)
    lines.append(go.Scatter3d(
        x=edge_x_xy, y=edge_y_xy, z=edge_z_xy, 
        mode='lines', line=line_marker, hoverinfo='skip',
        opacity=opacity, showlegend=False))
    
    # Add XZ-plane aligned grid (vertical mesh)
    lines.append(go.Scatter3d(
        x=edge_x_xz, y=edge_y_xz, z=edge_z_xz,
        mode='lines', line=line_marker, hoverinfo='skip',
        opacity=opacity, showlegend=False))
    
    # Add YZ-plane aligned grid (side mesh)
    lines.append(go.Scatter3d(
        x=edge_x_yz, y=edge_y_yz, z=edge_z_yz,
        mode='lines', line=line_marker, hoverinfo='skip',
        opacity=opacity, showlegend=False))
    
    return lines