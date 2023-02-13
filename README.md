# mocaviz
This repository contains plotly dash tools to visualize data from the MOCA database.

For now we have only one file, load_mocadash.py which allows to visualize basic data from the Database by calling it in this way:

python /path/load_mocadash.py

And then open a web browser and type in the address:

127.0.0.1:8050

The features that have been implemented as of Feb 13, 2023 are:

- Visualizing the CMD, XYZ, UVW and projections in XYZUVW.
- Cross-filtering across diagrams (except 3D diagrams).
- Selecting among associations using a Dropdown menu.
- Dynamic update based on the (private) mocadb server upon selection of new associations only.

The features I still want to implement are:

- Better visuals especially marker style and transparency style.
- Applying the selected datapoints to the 3D scatter plots.
- Adding the following figures:
  -- Individual RV, PM, PLX epochs + spectrum when selecting one data point.
  -- Galex colors
  -- ROSAT X-ray flux and hardness ratio
  -- Gaia activity index vs G-R
  -- Lithium EW vs G-R
  -- Prot vs G-R
  -- Teff vs Age
  -- Distance vs Age
  -- Mass vs Age
  -- Mass vs Distance
  -- Initial mass functions
  -- Log R'HK index vs G-R
  -- Spectral types of components in binary systems
  -- H-alpha vs G-R
  -- Table view of selected points
  -- Exoplanet Prot/radius and AU/mass
  -- SpT vs color
  
I also want to eventually implement other data control centers (in distinct .py files):

- Brown dwarf dataviz:
  -- Near-infrared CMD
  -- Table view
  -- Individual RV, PLX, PM, spectrum
  -- SpT vs EW for several gravity-sensitive features
  -- SpT vs various colors
  -- Various color-color plots

- Rotation dataviz (maybe Leslie will do it):
  -- Gaia CMD
  -- vsini vs G-R
  -- inclinations from DB
  -- prot vs G-R
  -- binary flags
  -- Table view
  -- Available TESS panels
  -- Individual lightcurves (pulled from the database)

- Photometry viztool:
  -- Gaia CMD
  -- Table view
  -- Various color plots
  -- Various CMDs
  -- Various SpT vs color
  -- All photometry for various filters when a single star is selected
  
- Astrometry viztool:
  -- Gaia CMD
  -- Table view
  -- All epochs of ra,dec,plx,pm,rv when selected
  -- Sky maps of ra,dec and gl,gb
  -- pmra vs pmdec
  -- XYZ
  -- UVW

The more long-term features:

- Selecting data points in 3D scatter plots (not yet allowed by plotly).
- Showing BANYAN Sigma ellipsoid models.
- Preventing the field stars from being selected in the CMD (not yet allowed by plotly but it is already a feature request).
