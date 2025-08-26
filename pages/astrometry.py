import dash
from math import floor, log10
import numpy as np
import decimal
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objs as go
from urllib.parse import quote_plus as urlquote, urlparse, parse_qs
from sqlalchemy import create_engine, select, MetaData, Table, func, and_, or_, cast, String, case
import pandas as pd
import os
from utils.plx_motion import parallax_motion
from scipy.optimize import curve_fit
from astropy.time import Time
from PyAstronomy.pyasl import sunpos

# Register the page in the Dash app
dash.register_page(__name__)

# Placeholder for the database connection string
connection_string = None

bin_size_days = 50
bin_size_days_phased = 20

figure_export_config = {
  'toImageButtonOptions': {
    'format': 'png', # one of png, svg, jpeg, webp
    'height': 500*2,
    'width': 700*2,
    'scale': 6*2 # Multiply title/legend/axis/canvas sizes by this factor
  }
}

def robust_error_weighted_plxfit_with_rejection(
    measurement_epoch_yr, rel_ra, rel_dec, ra_unc_mas, dec_unc_mas, ref_ra, ref_dec,
    sigma_threshold=10, max_iterations=5, inflate_errors=False, mission_labels=None, per_mission_inflate=False
):
    """
    Perform a robust error-weighted fit for parallax, proper motion, and positions with iterative outlier rejection.

    Parameters:
    - measurement_epoch_yr (array-like): The time values (years).
    - rel_ra (array-like): The relative RA offsets (mas).
    - rel_dec (array-like): The relative Dec offsets (mas).
    - ra_unc_mas (array-like): The uncertainties in relative RA (mas).
    - dec_unc_mas (array-like): The uncertainties in relative Dec (mas).
    - ref_ra (float): Reference RA in degrees.
    - ref_dec (float): Reference Dec in degrees.
    - sigma_threshold (float): Number of standard deviations for outlier rejection.
    - max_iterations (int): Maximum number of iterations for outlier rejection.

    Returns:
    - plx (float): Best-fit parallax (mas).
    - pmra (float): Best-fit proper motion in RA (mas/yr).
    - pmdec (float): Best-fit proper motion in Dec (mas/yr).
    - eplx (float): Uncertainty in the parallax.
    - epmra (float): Uncertainty in the proper motion in RA.
    - epmdec (float): Uncertainty in the proper motion in Dec.
    - inlier_mask (array): Boolean mask indicating inliers used in the final fit.
    """
    # Convert inputs to numpy arrays and ensure consistent dimensions
    epoch_yr = np.array(measurement_epoch_yr)
    rel_ra = np.array(rel_ra)
    rel_dec = np.array(rel_dec)
    ra_unc = np.array(ra_unc_mas)
    dec_unc = np.array(dec_unc_mas)
    # Track per-axis additive error inflation (mas)
    s_ra = 0.0
    s_dec = 0.0

    if not (len(epoch_yr) == len(rel_ra) == len(rel_dec) == len(ra_unc) == len(dec_unc)):
        raise ValueError(
            "All input arrays must have the same length. "
            f"Lengths: measurement_epoch_yr={len(epoch_yr)}, rel_ra={len(rel_ra)}, "
            f"rel_dec={len(rel_dec)}, ra_unc_mas={len(ra_unc)}, dec_unc_mas={len(dec_unc)}"
        )

    # Convert year epochs to MJD using Astropy
    time_obj = Time(epoch_yr, format='jyear', scale='utc')
    mjd_vec = time_obj.mjd

    # Convert reference RA/Dec to radians
    ref_ra_rad = np.radians(ref_ra)
    ref_dec_rad = np.radians(ref_dec)

    # Compute parallax motion terms using reference RA/Dec
    (void1, void2, void3, sun_elong, sun_obl) = sunpos(mjd_vec + 2400000.5, full_output=True)
    sun_elong = sun_elong[0]
    sun_obl = sun_obl[0]

    sin_sun_elong = np.sin(np.radians(sun_elong))
    cos_sun_elong = np.cos(np.radians(sun_elong))
    sin_sun_obl = np.sin(np.radians(sun_obl))
    cos_sun_obl = np.cos(np.radians(sun_obl))

    cos_ref_ra = np.cos(ref_ra_rad)
    sin_ref_ra = np.sin(ref_ra_rad)
    cos_ref_dec = np.cos(ref_dec_rad)
    sin_ref_dec = np.sin(ref_dec_rad)

    plx_motion_ra = cos_ref_ra * cos_sun_obl * sin_sun_elong - sin_ref_ra * cos_sun_elong
    plx_motion_dec = (
        cos_ref_dec * sin_sun_obl * sin_sun_elong
        - cos_ref_ra * sin_ref_dec * cos_sun_elong
        - sin_ref_ra * sin_ref_dec * cos_sun_obl * sin_sun_elong
    )

    # Initial mask (all points are considered inliers)
    inlier_mask = ~np.isnan(epoch_yr) & ~np.isnan(rel_ra) & ~np.isnan(rel_dec) & \
                  ~np.isnan(ra_unc) & ~np.isnan(dec_unc)

    if len(inlier_mask) != len(epoch_yr):
        raise ValueError(
            f"Inlier mask dimension mismatch: inlier_mask={len(inlier_mask)}, epoch_yr={len(epoch_yr)}"
        )

    # Define the model for fitting: y = pm * t + plx * plx_motion + pos
    def plx_pm_model(xdata, pmra, pmdec, plx, pos_ra, pos_dec):
        ra_model = pmra * xdata[0] + plx * xdata[1] + pos_ra
        dec_model = pmdec * xdata[0] + plx * xdata[2] + pos_dec
        return np.concatenate([ra_model, dec_model])  # Combine RA and Dec models into a single 1D array

    for iteration in range(max_iterations):
        # Perform the fit using inliers
        xdata = np.vstack([
            epoch_yr[inlier_mask],
            plx_motion_ra[inlier_mask],
            plx_motion_dec[inlier_mask]
        ])

        ydata = np.concatenate([rel_ra[inlier_mask], rel_dec[inlier_mask]])  # Combine observed RA and Dec offsets
        sigma = np.concatenate([ra_unc[inlier_mask], dec_unc[inlier_mask]])  # Combine uncertainties for RA and Dec

        # Perform the fit using combined RA and Dec model
        popt, pcov = curve_fit(
            plx_pm_model,  # The model function
            xdata,         # Independent variable: epoch_yr repeated for RA and Dec
            ydata,         # Dependent variable: observed RA and Dec offsets
            sigma=sigma,   # Combined uncertainties
            absolute_sigma=True
        )

        # Extract residuals for RA and Dec from the concatenated model output
        xdata = np.vstack([
            epoch_yr,
            plx_motion_ra,
            plx_motion_dec
        ])
        model_output = plx_pm_model(xdata, *popt)  # Model output is concatenated for RA and Dec
        ra_model = model_output[:len(rel_ra)]  # Extract RA model part
        dec_model = model_output[len(rel_ra):]  # Extract Dec model part

        # Calculate residuals for RA and Dec
        ra_residuals = rel_ra - ra_model
        dec_residuals = rel_dec - dec_model

        # Calculate standardized residuals for RA and Dec
        ra_standardized_residuals = np.abs(ra_residuals / ra_unc)
        dec_standardized_residuals = np.abs(dec_residuals / dec_unc)

        # Update inlier mask by combining RA and Dec criteria
        new_inlier_mask = (ra_standardized_residuals < sigma_threshold) & (dec_standardized_residuals < sigma_threshold)

        # Stop if no changes in the mask
        if np.array_equal(inlier_mask, new_inlier_mask):
            break

        inlier_mask = new_inlier_mask

        # ========== Optional two-pass inflation of uncertainties ==========
    if inflate_errors:
        # Model for all rows
        xdata_all = np.vstack([epoch_yr, plx_motion_ra, plx_motion_dec])
        model_all = plx_pm_model(xdata_all, *popt)
        ra_model_all = model_all[:len(rel_ra)]
        dec_model_all = model_all[len(rel_ra):]

        # Residuals for inliers
        ra_resid_in = (rel_ra - ra_model_all)[inlier_mask]
        dec_resid_in = (rel_dec - dec_model_all)[inlier_mask]
        ra_sig_in = ra_unc[inlier_mask]
        dec_sig_in = dec_unc[inlier_mask]

        # DOF per coordinate equation (pm + plx + intercept)
        dof_ra = max(1, ra_resid_in.size - 3)
        dof_dec = max(1, dec_resid_in.size - 3)

        s_ra = _solve_sigma_add(ra_resid_in, ra_sig_in, dof_ra)
        s_dec = _solve_sigma_add(dec_resid_in, dec_sig_in, dof_dec)

        # Refit with inflated uncertainties on inliers
        popt, pcov = curve_fit(
            plx_pm_model,
            np.vstack([epoch_yr[inlier_mask], plx_motion_ra[inlier_mask], plx_motion_dec[inlier_mask]]),
            np.concatenate([rel_ra[inlier_mask], rel_dec[inlier_mask]]),
            sigma=np.sqrt(np.concatenate([ra_unc[inlier_mask]**2 + s_ra**2, dec_unc[inlier_mask]**2 + s_dec**2])),
            absolute_sigma=True
        )

        # Per-mission inflation (optional): compute s_add per mission and refit with per-point sigmas
        s_ra_by_mission = {}
        s_dec_by_mission = {}
        if inflate_errors and per_mission_inflate and mission_labels is not None:
            missions_arr = np.asarray(mission_labels)
            # Build model over ALL rows
            xdata_all = np.vstack([epoch_yr, plx_motion_ra, plx_motion_dec])
            model_all = plx_pm_model(xdata_all, *popt)
            ra_model_all = model_all[:len(rel_ra)]
            dec_model_all = model_all[len(rel_ra):]
            # Initialize inflated sigma arrays with base
            ra_sig2 = ra_unc**2
            dec_sig2 = dec_unc**2
            # Compute per-mission s_add on inliers only
            for m in np.unique(missions_arr[inlier_mask]):
                mask_m = (missions_arr == m) & inlier_mask
                if mask_m.sum() >= 3:  # need DOF
                    ra_resid_m = (rel_ra - ra_model_all)[mask_m]
                    dec_resid_m = (rel_dec - dec_model_all)[mask_m]
                    ra_sig_m = ra_unc[mask_m]
                    dec_sig_m = dec_unc[mask_m]
                    dof_ra_m = max(1, mask_m.sum() - 3)
                    dof_dec_m = max(1, mask_m.sum() - 3)
                    s_ra_m = _solve_sigma_add(ra_resid_m, ra_sig_m, dof_ra_m)
                    s_dec_m = _solve_sigma_add(dec_resid_m, dec_sig_m, dof_dec_m)
                    s_ra_by_mission[m] = float(s_ra_m)
                    s_dec_by_mission[m] = float(s_dec_m)
                    # Apply to ALL points of this mission (including outliers) during refit
                    ra_sig2[missions_arr == m] = ra_unc[missions_arr == m]**2 + s_ra_m**2
                    dec_sig2[missions_arr == m] = dec_unc[missions_arr == m]**2 + s_dec_m**2
                else:
                    s_ra_by_mission[m] = 0.0
                    s_dec_by_mission[m] = 0.0
            # Refit using per-point inflated sigmas on inliers
            sigma_vec = np.sqrt(np.concatenate([ra_sig2[inlier_mask], dec_sig2[inlier_mask]]))
            
            popt, pcov = curve_fit(
                plx_pm_model,
                np.vstack([epoch_yr[inlier_mask], plx_motion_ra[inlier_mask], plx_motion_dec[inlier_mask]]),
                np.concatenate([rel_ra[inlier_mask], rel_dec[inlier_mask]]),
                sigma=sigma_vec,
                absolute_sigma=True
            )
    
    # Extract results
    pmra, pmdec, plx, pos_ra, pos_dec = popt
    e_pmra, e_pmdec, e_plx, e_pos_ra, e_pos_dec = np.sqrt(np.diag(pcov))

    return plx, pmra, pmdec, e_plx, e_pmra, e_pmdec, inlier_mask, s_ra, s_dec, s_ra_by_mission if ('s_ra_by_mission' in locals()) else {}, s_dec_by_mission if ('s_dec_by_mission' in locals()) else {}

def _solve_sigma_add(residuals, sigma, dof):
    """
    Find non-negative s such that sum(resid^2/(sigma^2 + s^2)) == dof.
    Monotonic bisection. Returns 0 if already not under-dispersed.
    """
    resid2 = np.asarray(residuals, float)**2
    sig2 = np.asarray(sigma, float)**2
    # Guard against zeros and NaNs
    if not np.any(sig2 > 0):
        sig2 = np.ones_like(resid2)
    else:
        safe = np.nanmedian(sig2[sig2 > 0])
        sig2 = np.where(sig2 <= 0, safe if np.isfinite(safe) and safe > 0 else 1.0, sig2)

    def f(s):
        return np.nansum(resid2 / (sig2 + s*s)) - dof

    if f(0.0) <= 0:
        return 0.0

    # Find upper bound
    s_lo, s_hi = 0.0, np.sqrt(np.nanmedian(resid2)) if np.isfinite(np.nanmedian(resid2)) else 1.0
    for _ in range(60):
        if f(s_hi) < 0:
            break
        s_hi *= 2.0

    # Bisection
    for _ in range(60):
        s_mid = 0.5*(s_lo + s_hi)
        if f(s_mid) > 0:
            s_lo = s_mid
        else:
            s_hi = s_mid
    return s_hi

#Robust error-weighted fit
def robust_error_weighted_pmfit_with_rejection(measurement_epoch_yr, rel_ra, ra_unc_mas, sigma_threshold=10, max_iterations=5, inflate_errors=False, mission_labels=None, per_mission_inflate=False):
    """
    Perform a robust error-weighted fit with iterative outlier rejection.
    
    Parameters:
    - measurement_epoch_yr (array-like): The time values (years).
    - rel_ra (array-like): The relative RA offsets (mas).
    - ra_unc_mas (array-like): The uncertainties in relative RA (mas).
    - sigma_threshold (float): Number of standard deviations for outlier rejection.
    - max_iterations (int): Maximum number of iterations for outlier rejection.
    
    Returns:
    - slope (float): Best-fit slope (proper motion in mas/yr).
    - slope_error (float): Uncertainty in the slope.
    - inlier_mask (array): Boolean mask indicating inliers used in the final fit.
    """
    # Define a linear model: y = m * x + b
    def linear_model(x, m, b):
        return m * x + b

    # Convert inputs to numpy arrays
    x = np.array(measurement_epoch_yr)
    y = np.array(rel_ra)
    sigma = np.array(ra_unc_mas)
    # Track additive error inflation (mas)
    s_add = 0.0

    # Initial mask (all points are considered inliers)
    inlier_mask = ~np.isnan(x) & ~np.isnan(y) & ~np.isnan(sigma)

    for iteration in range(max_iterations):
        # Perform the fit using inliers
        popt, pcov = curve_fit(
            linear_model,
            x[inlier_mask],
            y[inlier_mask],
            sigma=sigma[inlier_mask],
            absolute_sigma=True
        )
        
        # Calculate residuals
        residuals = y - linear_model(x, *popt)

        # Calculate standardized residuals (z-scores)
        standardized_residuals = np.abs(residuals / sigma)

        # Update inlier mask
        new_inlier_mask = standardized_residuals < sigma_threshold

        # Stop if no changes in the mask
        if np.array_equal(inlier_mask, new_inlier_mask):
            break

        inlier_mask = new_inlier_mask
    
    
    if inflate_errors and not per_mission_inflate:
        residuals = y - linear_model(x, *popt)
        in_inliers = inlier_mask
        dof = max(1, in_inliers.sum() - 2)  # slope + intercept
        s_add = _solve_sigma_add(residuals[in_inliers], sigma[in_inliers], dof)
        popt, pcov = curve_fit(
            linear_model,
            x[in_inliers],
            y[in_inliers],
            sigma=np.sqrt(sigma[in_inliers]**2 + s_add**2),
            absolute_sigma=True
        )
    elif inflate_errors and per_mission_inflate and mission_labels is not None:
        missions_arr = np.asarray(mission_labels)
        # Compute residuals on all points with current fit
        residuals_all = y - linear_model(x, *popt)
        # Start with base sigmas
        sig2 = sigma**2
        s_add_by_mission = {}
        for m in np.unique(missions_arr[inlier_mask]):
            mask_m = (missions_arr == m) & inlier_mask
            if mask_m.sum() >= 3:
                dof_m = max(1, mask_m.sum() - 2)
                s_m = _solve_sigma_add(residuals_all[mask_m], sigma[mask_m], dof_m)
                s_add_by_mission[m] = float(s_m)
                sig2[missions_arr == m] = sigma[missions_arr == m]**2 + s_m**2
            else:
                s_add_by_mission[m] = 0.0
        # Refit with per-point inflated sigmas on inliers only
        popt, pcov = curve_fit(
            linear_model,
            x[inlier_mask],
            y[inlier_mask],
            sigma=np.sqrt(sig2[inlier_mask]),
            absolute_sigma=True
        )
    
    # Final slope and error
    slope = popt[0]
    slope_error = np.sqrt(pcov[0, 0])

    return slope, slope_error, inlier_mask, s_add, s_add_by_mission if ('s_add_by_mission' in locals()) else {}

# Group by binned time and calculate weighted averages
def weighted_combination(group):
    # Extract RA and Dec values and their uncertainties
    x_ra = group["rel_ra"].values
    ex_ra = group["ra_unc_mas"].values
    x_dec = group["rel_dec"].values
    ex_dec = group["dec_unc_mas"].values

    # Filter out NaN values for RA
    valid_ra_mask = ~np.isnan(x_ra) & ~np.isnan(ex_ra)
    x_ra = x_ra[valid_ra_mask]
    ex_ra = ex_ra[valid_ra_mask]

    # Filter out NaN values for Dec
    valid_dec_mask = ~np.isnan(x_dec) & ~np.isnan(ex_dec)
    x_dec = x_dec[valid_dec_mask]
    ex_dec = ex_dec[valid_dec_mask]

    # Handle cases with no valid data
    if len(x_ra) == 0:
        combined_ra = np.nan
        combined_ra_unc = np.nan
    elif len(x_ra) == 1:
        combined_ra = x_ra[0]
        combined_ra_unc = ex_ra[0]
    else:
        weights_ra = 1 / np.maximum(ex_ra, 0.7 * np.median(ex_ra))**2
        weights_ra /= weights_ra.sum()  # Normalize weights
        combined_ra = np.sum(x_ra * weights_ra)
        bias_ra = 1 - np.sum(weights_ra**2)
        wstd_ra = np.sqrt(np.sum(weights_ra * (x_ra - combined_ra)**2) / bias_ra) if bias_ra > 0 else 0
        combined_ra_unc = np.sqrt(wstd_ra**2)

    if len(x_dec) == 0:
        combined_dec = np.nan
        combined_dec_unc = np.nan
    elif len(x_dec) == 1:
        combined_dec = x_dec[0]
        combined_dec_unc = ex_dec[0]
    else:
        weights_dec = 1 / np.maximum(ex_dec, 0.7 * np.median(ex_dec))**2
        weights_dec /= weights_dec.sum()  # Normalize weights
        combined_dec = np.sum(x_dec * weights_dec)
        bias_dec = 1 - np.sum(weights_dec**2)
        wstd_dec = np.sqrt(np.sum(weights_dec * (x_dec - combined_dec)**2) / bias_dec) if bias_dec > 0 else 0
        combined_dec_unc = np.sqrt(wstd_dec**2)

    # Return combined results as a Series
    return pd.Series({
        "rel_ra": combined_ra,
        "ra_unc_mas": combined_ra_unc,
        "rel_dec": combined_dec,
        "dec_unc_mas": combined_dec_unc,
        "ndata":len(x_ra)
    })

# def format_value_with_error(value, error, unit=""):
#     """
#     Formats a value with its error, ensuring clean rounding and no floating-point artifacts.
#     If the value or error is None, it returns "N/A".
#     """
#     if pd.isna(value) or pd.isna(error) or value == "N/A" or error == "N/A":
#         return "N/A"
    
#     # Calculate the significant digit for the error
#     error_magnitude = 10 ** floor(log10(abs(error)))
#     rounded_error = round(error / error_magnitude) * error_magnitude

#     # Ensure the value is rounded to the same number of significant digits as the error
#     significant_digits = -int(floor(log10(abs(rounded_error))))
#     significant_digits = max(0, -int(floor(log10(abs(rounded_error)))))
#     rounded_value = round(value, max(0, significant_digits))

#     # Format the result to remove floating-point artifacts
#     rounded_value_str = f"{rounded_value:.{significant_digits}f}".rstrip('0').rstrip('.')
#     rounded_error_str = f"{rounded_error:.{significant_digits}f}".rstrip('0').rstrip('.')

#     # Return formatted string with ± symbol and unit
#     return f"{rounded_value_str} ± {rounded_error_str}" + (f" {unit}" if unit else "")

def format_value_with_error(value, error, unit=""):
    """
    Formats a value with its error, ensuring clean rounding and no floating-point artifacts.
    If the value or error is None, it returns "N/A".
    """
    if pd.isna(value) or pd.isna(error) or value == "N/A" or error == "N/A":
        return "N/A"

    # Round the error to 1 significant digit
    error_exp = floor(log10(abs(error)))
    rounded_error = round(error, -error_exp)
    
    # Round the value to the same decimal place
    rounded_value = round(value, -error_exp)

    # Format
    rounded_value_str = str(int(rounded_value)) if error_exp >= 0 else f"{rounded_value:.{-error_exp}f}"
    rounded_error_str = str(int(rounded_error)) if error_exp >= 0 else f"{rounded_error:.{-error_exp}f}"

    return f"{rounded_value_str} ± {rounded_error_str}" + (f" {unit}" if unit else "")

def wrap_text(text, width=50):
    """Wraps text with line breaks every 'width' characters."""
    if not text:  # Handles None or empty string
        return ""
    return '<br>'.join([text[i:i+width] for i in range(0, len(text), width)])

# Define the initial layout of the page
# Layout
layout = html.Div([
    dcc.Location(id="url", refresh=False),
    html.Div([
        html.H1("Astrometric Explorer"),
        html.P("This page allows to compare the individual-epoch astrometry of MOCAdb entries "
               " with their best-available proper motion and parallax solutions."
               ),
    ], style={'width': '100%', 'display': 'inline-block'}),
    
    dcc.Input(
        id="astrometry-dropdown-search",
        placeholder="Filter dropdown menu by object name or MOCA OID then press Enter",
        type="text",
        debounce=True,
        style={
            "width": "100%",  # Full width
            "padding": "0.5rem",  # Optional padding for better alignment
            "fontSize": "16px"  # Match the dropdown font size
        }
    ),
    dcc.Dropdown(
        id="astrometry-filtered-dropdown",
        options=[],  # Will be populated dynamically
        placeholder="Specify an object name or moca_oid above",
        searchable=True,
        style={
        "width": "100%",  # Full width
        "fontSize": "16px"  # Ensure font size matches input
        }
    ),

    dcc.Dropdown(
        id="mission-toggle-dropdown",
        options=[],  # Will be dynamically populated
        multi=True,
        placeholder="Select missions to display",
        style={
            "width": "100%",
            "fontSize": "16px",
            "marginTop": "10px"
        }
    ),

    html.Div([
        # Column 1
        html.Div([
            dcc.Checklist(
                id="subtract-pm-checkbox",
                options=[{'label': 'Subtract proper motion', 'value': 'subtract_pm'}],
                value=[],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="subtract-plx-checkbox",
                options=[{'label': 'Subtract parallax motion', 'value': 'subtract_plx'}],
                value=[],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="phase-yr-checkbox",
                options=[{'label': 'Phase yearly', 'value': 'phase'}],
                value=[],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="astrometry-bin-checkbox",
                options=[{'label': 'Bin data by '+str(bin_size_days)+'-day intervals ('+str(bin_size_days_phased)+' days if phased yearly) just for display', 'value': 'bin_checked'}],
                value=[],  # Default is unchecked
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
        ], style={'display': 'inline-block', 'vertical-align': 'top', 'width': '50%', 'padding-right': '10px'}),
        
        # Column 2
        html.Div([
            dcc.Checklist(
                id="adjust-reference-epoch-checkbox",
                options=[{'label': 'Adjust reference epoch', 'value': 'adjust_ref'}],
                value=['adjust_ref'],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="fit-proper-motion-checkbox",
                options=[{'label': 'Fit proper motion', 'value': 'fit_pm'}],
                value=['adjust_ref'],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="fit-parallax-checkbox",
                options=[{'label': 'Fit parallax', 'value': 'fit_plx'}],
                value=[],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="inflate-errors-checkbox",
                options=[{'label': 'Back propagate residuals into measurement errors during fit', 'value': 'inflate'}],
                value=['inflate'],  # default ON
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="only-use-recalibrated-checkbox",
                options=[{'label': 'Only use recalibrated astrometry when possible', 'value': 'only_recalibrated'}],
                value=['only_recalibrated'], # default ON
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            ),
            dcc.Checklist(
                id="revert-raw-checkbox",
                options=[{'label': 'Revert all astrometry to pre-calibration', 'value': 'revert_raw'}],
                value=[],
                inline=True,
                style={'margin-bottom': '10px', 'font-size': '16px'}
            )
            ], style={'display': 'inline-block', 'vertical-align': 'top', 'width': '50%', 'padding-left': '10px'})
        ], style={'display': 'flex', 'width': '100%', 'margin-bottom': '20px'}),

    html.Div([
        dcc.Graph(id="astrometry-plot-ra",config=figure_export_config),
    ], style={'width': '100%', 'display': 'inline-block', 'margin-bottom': '20px'}),
    
    html.Div([
        dcc.Graph(id="astrometry-plot-dec",config=figure_export_config),
    ], style={'width': '100%', 'display': 'inline-block'}),

    html.Div([
        html.Div("URL parameter: moca_oid", style={"fontWeight": "bold", "marginBottom": "6px"}),
        html.P(
            "You can deep‑link this page to a specific object by passing a moca_oid in the URL query string. "
            "This selects the object in the dropdown on load and renders its astrometry. "
            "No credentials parameters are required for this feature."),
        html.Div("Examples:", style={"fontStyle": "italic", "marginTop": "4px"}),
        html.Pre(
            "?moca_oid=602\n"
            "?moca_oid=156",
            style={"backgroundColor": "#f7f7f7", "padding": "8px", "border": "1px solid #ddd", "overflowX": "auto", "marginTop": "4px"}
        ),
        html.Ul([
            html.Li("If omitted, the page defaults to moca_oid=602."),
            html.Li("If the id doesn’t exist or isn’t accessible, the dropdown will stay on the default."),
        ], style={"marginTop": "4px"}),
    ], style={
        "border": "1px solid #ddd",
        "backgroundColor": "#fcfcfc",
        "padding": "10px 12px",
        "borderRadius": "4px",
        "marginTop": "14px",
        "marginBottom": "6px",
        "lineHeight": 1.5
    }),

], style={'width': '65%', 'display': 'inline-block','padding-left': '15px'})

@dash.callback(
    output=[
        Output("astrometry-filtered-dropdown", "options"),
        Output("astrometry-filtered-dropdown", "value"),
    ],
    inputs=[
        Input("url", "href"),
        Input("astrometry-dropdown-search", "value"),  # Search input from the dropdown search box
    ],
    state=[State("url", "search")]
)
def update_dropdown(href, search_value, url_search):

    # Parse URL parameters
    parsed_url = urlparse(url_search)
    parsed_url_data = parse_qs(parsed_url.query)
    
    # Check for moca_oid in the URL query parameters
    moca_oid_param = parsed_url_data.get('moca_oid', [None])[0]

    env_username = parsed_url_data.get('user', [None])[0]
    env_password = parsed_url_data.get('pwd', [None])[0]
    env_dbname = parsed_url_data.get('dbase', [None])[0]

    default_host = '104.248.106.21'
    default_username = 'public'
    default_password = 'z@nUg_2h7_%?31y88'
    default_dbname = 'mocadb'
    default_moca_oid = 602  # Default MOCA OID when no input is provided
    
    if env_username is None:
        env_username = os.environ.get('MOCA_USERNAME', default_username)
    if env_password is None:
        env_password = os.environ.get('MOCA_PASSWORD', default_password)
    if env_dbname is None:
        env_dbname = os.environ.get('MOCA_DBNAME', default_dbname)
    env_host = os.environ.get('MOCA_HOST', default_host)

    if env_username is None:
        return dash.no_update
    if env_password is None:
        return dash.no_update
    if env_dbname is None:
        return dash.no_update

    global connection_string
    connection_string = f'mysql+pymysql://{env_username}:{urlquote(env_password)}@{env_host}/{env_dbname}'

    # Establish connection to the database
    engine = create_engine(connection_string)
    connection = engine.connect()
    metadata = MetaData()

    # Reflect the moca_objects table
    moca_objects = Table('moca_objects', metadata, autoload_with=engine)
    mechanics_all_designations = Table('mechanics_all_designations', metadata, autoload_with=engine)

    # Determine the query logic based on inputs
    if search_value:  # If a search term is provided
        search_query = f"%{search_value}%"
        query = (
            select([mechanics_all_designations.c.moca_oid, mechanics_all_designations.c.designation])
            .where(
                or_(
                    mechanics_all_designations.c.designation.ilike(search_query),
                    cast(mechanics_all_designations.c.moca_oid, String).ilike(search_query)
                )
            )
            .limit(25)  # Limit to a reasonable number of results
        )
    elif moca_oid_param:  # If a specific moca_oid is provided in the URL
        query = (
            select([moca_objects.c.moca_oid, moca_objects.c.designation])
            .where(moca_objects.c.moca_oid == int(moca_oid_param))
        )
    else:  # Default to the row with moca_oid=602
        query = (
            select([moca_objects.c.moca_oid, moca_objects.c.designation])
            .where(moca_objects.c.moca_oid == default_moca_oid)
        )
    
    result_df = pd.read_sql(query, connection)

    # Format dropdown options by concatenating in Python
    dataset_options = [
        {"label": f"{row['moca_oid']}|{row['designation']}", "value": str(row['moca_oid'])}
        for _, row in result_df.iterrows()
    ]

    # Determine the default value
    if moca_oid_param and moca_oid_param in result_df['moca_oid'].astype(str).tolist():
        default_value = str(moca_oid_param)
    else:
        default_value = str(default_moca_oid)

    connection.close()
    return dataset_options, default_value

@dash.callback(
    Output("mission-toggle-dropdown", "options"),
    Output("mission-toggle-dropdown", "value"),
    Input("astrometry-filtered-dropdown", "value"),
    prevent_initial_call=True
)
def update_mission_dropdown(selected_dataset):
    if not selected_dataset:
        return [], []
    
    moca_oid = selected_dataset
    engine = create_engine(connection_string)
    connection = engine.connect()
    metadata = MetaData()

    # Reflect the relevant table and fetch unique missions
    data_equatorial_coordinates = Table('data_equatorial_coordinates', metadata, autoload_with=engine)
    query = select(
            func.coalesce(
                case(
                    # Check if the concatenated mission name is empty after trimming spaces
                    [
                        (func.trim(func.concat(data_equatorial_coordinates.c.mission_name, ' ', data_equatorial_coordinates.c.data_release)) == "", "No mission"),
                    ],
                    else_=func.coalesce(
                        func.concat(data_equatorial_coordinates.c.mission_name, ' ', data_equatorial_coordinates.c.data_release),
                        data_equatorial_coordinates.c.moca_pid
                    )
                ),
                'No mission'  # Fallback if all other options are NULL
            ).label('mission')
        ).distinct().where(
        and_(
            data_equatorial_coordinates.c.moca_oid == moca_oid,
            data_equatorial_coordinates.c.adopted == 1,
            data_equatorial_coordinates.c.single_epoch == 1
            )
    )

    missions_df = pd.read_sql(query, connection)
    connection.close()

    # Generate options for the dropdown
    mission_options = [{"label": mission, "value": mission} for mission in missions_df['mission']]
    return mission_options, [option["value"] for option in mission_options]  # Select all by default


# Define the callback to update the scatter plot based on input
@dash.callback(
    [Output("astrometry-plot-ra", "figure"),
     Output("astrometry-plot-dec", "figure")],
    [Input("astrometry-filtered-dropdown", "value"),
     Input("mission-toggle-dropdown", "value"),  # New input for selected missions
     Input("subtract-pm-checkbox", "value"),
     Input("subtract-plx-checkbox", "value"),
     Input("phase-yr-checkbox", "value"),
     Input("adjust-reference-epoch-checkbox", "value"),
     Input("only-use-recalibrated-checkbox", "value"),
     Input("revert-raw-checkbox", "value"),
     Input("astrometry-bin-checkbox", "value"),
     Input("fit-proper-motion-checkbox", "value"),
     Input("fit-parallax-checkbox", "value"),
     Input("inflate-errors-checkbox", "value"),
     Input("astrometry-plot-ra", "selectedData"),
     Input("astrometry-plot-dec", "selectedData")],
     prevent_initial_call=True,
)
def update_scatter_plot(selected_dataset, selected_missions, pm_checkbox_values, plx_checkbox_values, phase_checkbox_values, adjust_ref_checkbox_values, only_recalibrated_checkbox_values, revert_raw_checkbox_values, bin_checkbox_values, fit_pm_values, fit_plx_values, inflate_err_values, selectedData_ra, selectedData_dec):
    ctx = dash.callback_context
    
    if not selected_dataset:
        return dash.no_update, dash.no_update
    
    subtract_pm = 'subtract_pm' in pm_checkbox_values  # Check if the checkbox is selected
    subtract_plx = 'subtract_plx' in plx_checkbox_values  # Check if the checkbox is selected
    phase_yearly = 'phase' in phase_checkbox_values  # Check if the checkbox is selected
    adjust_reference_epoch = 'adjust_ref' in adjust_ref_checkbox_values  # Check if the checkbox is selected
    only_recalibrated = 'only_recalibrated' in only_recalibrated_checkbox_values  # Check if the checkbox is selected
    revert_raw = 'revert_raw' in revert_raw_checkbox_values  # Check if the checkbox is selected
    bin_activated = 'bin_checked' in bin_checkbox_values
    fit_pm = 'fit_pm' in fit_pm_values
    fit_plx = 'fit_plx' in fit_plx_values
    inflate_errors = 'inflate' in inflate_err_values

    triggered_prop = ctx.triggered[0]["prop_id"]

    triggered_by_selection = ('selectedData_ra' in ctx.triggered[0]['prop_id']) or ('selectedData_dec' in ctx.triggered[0]['prop_id'])

    if triggered_by_selection and ((selectedData_ra is None and selectedData_dec is None) or (not selectedData_ra.get('points') and not selectedData_dec.get('points'))):
        return dash.no_update, dash.no_update
    
    try:
        moca_oid = selected_dataset
        #moca_oid, designation = selected_dataset.split('|')
    except ValueError:
        return dash.no_update, dash.no_update

    engine = create_engine(connection_string)
    connection = engine.connect()
    metadata = MetaData()

    #Query combined coordinates
    calc_equatorial_coordinates_combined = Table('calc_equatorial_coordinates_combined', metadata, autoload_with=engine)

    query = select(calc_equatorial_coordinates_combined.c.ra,
                   calc_equatorial_coordinates_combined.c.dec,
                   calc_equatorial_coordinates_combined.c.position_epoch_yr
                   ).where(
        (calc_equatorial_coordinates_combined.c.moca_oid == moca_oid)
    )
    ref_df = pd.read_sql(query, connection)
    ra_ref, dec_ref, epoch_ref = ref_df.iloc[0]["ra"], ref_df.iloc[0]["dec"], ref_df.iloc[0]["position_epoch_yr"]

    #Query PM
    data_proper_motions = Table('data_proper_motions', metadata, autoload_with=engine)
    moca_publications = Table('moca_publications', metadata, autoload_with=engine)
    pm_publications = moca_publications.alias('pm_publications')

    query = (select([data_proper_motions.c.pmra_masyr,
                   data_proper_motions.c.pmdec_masyr,
                   data_proper_motions.c.pmra_masyr_unc,
                   data_proper_motions.c.pmdec_masyr_unc,
                   func.concat(func.coalesce(func.coalesce(pm_publications.c.name, pm_publications.c.moca_pid), data_proper_motions.c.origin),func.coalesce(func.concat(', ',data_proper_motions.c.mission_name,func.coalesce(func.concat(' ',data_proper_motions.c.data_release),'')),'')).label('pm_ref')
                ])
                .select_from(data_proper_motions
                            .outerjoin(
                                pm_publications,
                                (pm_publications.c.moca_pid == data_proper_motions.c.moca_pid)
                            )
                    )
                .where(
                    (data_proper_motions.c.moca_oid == moca_oid)
                ).limit(1))
    
    pm_df = pd.read_sql(query, connection)
    
    #Query PLX
    data_parallaxes = Table('data_parallaxes', metadata, autoload_with=engine)
    plx_publications = moca_publications.alias('plx_publications')

    query = (select([data_parallaxes.c.parallax_mas,
                   data_parallaxes.c.parallax_mas_unc,
                   func.concat(func.coalesce(func.coalesce(plx_publications.c.name, plx_publications.c.moca_pid), data_parallaxes.c.origin),func.coalesce(func.concat(', ',data_parallaxes.c.mission_name,func.coalesce(func.concat(' ',data_parallaxes.c.data_release),'')),'')).label('plx_ref')
                ])
                .select_from(data_parallaxes
                            .outerjoin(
                                plx_publications,
                                (plx_publications.c.moca_pid == data_parallaxes.c.moca_pid)
                            )
                    )
                .where(
                    (data_parallaxes.c.moca_oid == moca_oid)
                ).limit(1))

    plx_df = pd.read_sql(query, connection)

    #Query all coordinates
    data_equatorial_coordinates = Table('data_equatorial_coordinates', metadata, autoload_with=engine)
    # Reflect missions table for recalibrated filter logic
    moca_missions = Table('moca_missions', metadata, autoload_with=engine)

    # Conditionally construct the "ra" and "dec" columns
    if revert_raw:
        ra_column = (data_equatorial_coordinates.c.ra -
                    func.ifnull(
                        data_equatorial_coordinates.c.calibration_delta_ra_mas /
                        (3600 * 1000 * func.cos(data_equatorial_coordinates.c.dec * func.pi() / 180)), 0)
                    ).label('ra')
        dec_column = (data_equatorial_coordinates.c.dec -
                    func.ifnull(
                        data_equatorial_coordinates.c.calibration_delta_dec_mas /
                        (3600 * 1000), 0)
                    ).label('dec')
    else:
        ra_column = data_equatorial_coordinates.c.ra.label('ra')
        dec_column = data_equatorial_coordinates.c.dec.label('dec')

    # Left join to missions to know whether a detections table exists for a mission
    dec_base = data_equatorial_coordinates.outerjoin(
        moca_missions,
        and_(
            moca_missions.c.mission_name == data_equatorial_coordinates.c.mission_name,
            moca_missions.c.data_release == data_equatorial_coordinates.c.data_release,
        )
    )

    # Build the recalibration condition: require calibrated OR mission explicitly allowed
    # Note: with the outer join, rows without a matching mission will NOT pass this flag check
    recalib_condition = or_(
        data_equatorial_coordinates.c.calibration_method.isnot(None),
        moca_missions.c.include_in_recalibrated_display == 1
    )

    query = select(
        data_equatorial_coordinates.c.id,
        ra_column,
        dec_column,
        data_equatorial_coordinates.c.measurement_epoch_yr,
        data_equatorial_coordinates.c.ra_unc_mas,
        data_equatorial_coordinates.c.dec_unc_mas,
        func.coalesce(data_equatorial_coordinates.c.measurement_epoch_yr_unc, 0).label('measurement_epoch_yr_unc'),
        func.coalesce(
            case(
                [
                    (func.trim(func.concat(data_equatorial_coordinates.c.mission_name, ' ', data_equatorial_coordinates.c.data_release)) == "", "No mission"),
                ],
                else_=func.coalesce(
                    func.concat(data_equatorial_coordinates.c.mission_name, ' ', data_equatorial_coordinates.c.data_release),
                    data_equatorial_coordinates.c.moca_pid
                )
            ), 'No mission'
        ).label('mission'),
        data_equatorial_coordinates.c.moca_pid,
        data_equatorial_coordinates.c.mission_name,
        data_equatorial_coordinates.c.data_release,
        data_equatorial_coordinates.c.origin,
        data_equatorial_coordinates.c.comments,
        data_equatorial_coordinates.c.airmass,
        data_equatorial_coordinates.c.moca_psid,
        data_equatorial_coordinates.c.calibration_delta_ra_mas,
        data_equatorial_coordinates.c.calibration_delta_dec_mas,
        data_equatorial_coordinates.c.nstars_calibration,
        data_equatorial_coordinates.c.calibration_method,
    ).select_from(dec_base).where(
        and_(
            data_equatorial_coordinates.c.moca_oid == moca_oid,
            data_equatorial_coordinates.c.adopted == 1,
            data_equatorial_coordinates.c.single_epoch == 1,
            recalib_condition if only_recalibrated else True,
        )
    )
    data_df = pd.read_sql(query, connection)
    connection.close()

    # Check if data_df is empty
    if data_df.empty:
        #return dash.no_update, dash.no_update
        # Return empty figures with a message
        empty_figure = go.Figure()
        empty_figure.update_layout(
            title="No data available",
            xaxis_title="Epoch (Year)",
            yaxis_title="Offset (mas)",
            xaxis=dict(showgrid=False, zeroline=False),
            yaxis=dict(showgrid=False, zeroline=False),
            annotations=[
                dict(
                    x=0.5, y=0.5, xref="paper", yref="paper",
                    text="No data available for the selected dataset",
                    showarrow=False,
                    font=dict(size=16)
                )
            ]
        )
        return empty_figure, empty_figure

    if selected_missions:
        data_df = data_df[data_df["mission"].isin(selected_missions)]

    # Calculate relative offsets
    data_df["rel_ra"] = (data_df["ra"] - ra_ref) * np.cos(np.radians(dec_ref)) * 3600 * 1000
    data_df["rel_dec"] = (data_df["dec"] - dec_ref) * 3600 * 1000

    if fit_plx:
        plx, pmra, pmdec, eplx, epmra, epmdec, plx_inlier_mask, s_add_ra, s_add_dec, s_add_ra_by_mission, s_add_dec_by_mission = robust_error_weighted_plxfit_with_rejection(
            data_df['measurement_epoch_yr'], data_df['rel_ra'], data_df['rel_dec'],
            data_df['ra_unc_mas'], data_df['dec_unc_mas'], ra_ref, dec_ref,
            inflate_errors=inflate_errors,
            mission_labels=data_df['mission'],
            per_mission_inflate=inflate_errors
        )
        # Rebuild plx_df and pm_df
        plx_df = pd.DataFrame({
            "parallax_mas": [plx],
            "parallax_mas_unc": [eplx],
            "plx_ref": ["fitted in Astrometric Explorer"]
        })
        # Rebuild pm_df
        pm_df = pd.DataFrame({
            "pmra_masyr": [pmra],
            "pmdec_masyr": [pmdec],
            "pmra_masyr_unc": [epmra],
            "pmdec_masyr_unc": [epmdec],
            "pm_ref": ["fitted in Astrometric Explorer"]
        })

    if fit_pm and not fit_plx:
        pmra, epmra, pmra_inlier_mask, s_add_ra, s_add_ra_by_mission = robust_error_weighted_pmfit_with_rejection(
            data_df['measurement_epoch_yr'], data_df['rel_ra'], data_df['ra_unc_mas'],
            inflate_errors=inflate_errors,
            mission_labels=data_df['mission'],
            per_mission_inflate=inflate_errors
        )
        pmdec, epmdec, pmdec_inlier_mask, s_add_dec, s_add_dec_by_mission = robust_error_weighted_pmfit_with_rejection(
            data_df['measurement_epoch_yr'], data_df['rel_dec'], data_df['dec_unc_mas'],
            inflate_errors=inflate_errors,
            mission_labels=data_df['mission'],
            per_mission_inflate=inflate_errors
        )

        # Rebuild pm_df
        pm_df = pd.DataFrame({
            "pmra_masyr": [pmra],
            "pmdec_masyr": [pmdec],
            "pmra_masyr_unc": [epmra],
            "pmdec_masyr_unc": [epmdec],
            "pm_ref": ["fitted in Astrometric Explorer"]
        })
    # Default additive error inflations (mas) if not set by fitting blocks
    if 's_add_ra' not in locals():
        s_add_ra = 0.0
    if 's_add_dec' not in locals():
        s_add_dec = 0.0
    if 's_add_ra_by_mission' not in locals():
        s_add_ra_by_mission = {}
    if 's_add_dec_by_mission' not in locals():
        s_add_dec_by_mission = {}

    # ---- Build inlier/outlier masks for display ----
    n_points = len(data_df)
    # Default masks: all inliers if not fitted
    if 'plx_inlier_mask' in locals():
        inliers_ra = np.array(plx_inlier_mask, dtype=bool)
        inliers_dec = np.array(plx_inlier_mask, dtype=bool)
    else:
        # PM-only may have separate masks
        if 'pmra_inlier_mask' in locals():
            inliers_ra = np.array(pmra_inlier_mask, dtype=bool)
        else:
            inliers_ra = np.ones(n_points, dtype=bool)
        if 'pmdec_inlier_mask' in locals():
            inliers_dec = np.array(pmdec_inlier_mask, dtype=bool)
        else:
            inliers_dec = np.ones(n_points, dtype=bool)

    # Attach flags to dataframe
    data_df['is_outlier_ra'] = ~inliers_ra
    data_df['is_outlier_dec'] = ~inliers_dec

    # Extract proper motion and parallax values
    # Extract proper motion and parallax values with errors
    if len(pm_df) != 0:
        pmra_display = format_value_with_error(pm_df.iloc[0]["pmra_masyr"], pm_df.iloc[0]["pmra_masyr_unc"], "mas/yr")
        pmdec_display = format_value_with_error(pm_df.iloc[0]["pmdec_masyr"], pm_df.iloc[0]["pmdec_masyr_unc"], "mas/yr")+" ("+pm_df["pm_ref"].fillna('No reference').str.replace(r'[()]', '', regex=True).iloc[0]+")"
    else:
        pmra_display, pmdec_display = "N/A", "N/A"

    if len(plx_df) != 0:
        parallax_display = format_value_with_error(plx_df.iloc[0]["parallax_mas"], plx_df.iloc[0]["parallax_mas_unc"], "mas")+" ("+plx_df["plx_ref"].fillna('No reference').str.replace(r'[()]', '', regex=True).iloc[0]+")"
    else:
        parallax_display = "N/A"
    
    if adjust_reference_epoch:
        epochs = data_df["measurement_epoch_yr"].values
        epoch_ref = np.nanmean(epochs)
        rel_ra_observed = (data_df["ra"]) * np.cos(np.radians(data_df["dec"])) * 3600 * 1000
        rel_dec_observed = (data_df["dec"]) * 3600 * 1000

        if len(pm_df) != 0:
            rel_ra_observed -= (epochs - epoch_ref) * pm_df.iloc[0]["pmra_masyr"]
            rel_dec_observed -= (epochs - epoch_ref) * pm_df.iloc[0]["pmdec_masyr"]

        if len(plx_df) != 0:
            plxm = parallax_motion(np.nanmean(data_df["ra"]), np.nanmean(data_df["dec"]), epochs)
            rel_ra_observed -= plxm["plx_motion_racosdec"]*plx_df.iloc[0]["parallax_mas"]
            rel_dec_observed -= plxm["plx_motion_dec"]*plx_df.iloc[0]["parallax_mas"]
        
        ra_ref = np.nanmedian(rel_ra_observed/(np.cos(np.radians(data_df["dec"])) * 3600 * 1000))
        dec_ref = np.nanmedian(rel_dec_observed/(3600 * 1000))

        # Recalculate relative offsets
        data_df["rel_ra"] = (data_df["ra"] - ra_ref) * np.cos(np.radians(dec_ref)) * 3600 * 1000
        data_df["rel_dec"] = (data_df["dec"] - dec_ref) * 3600 * 1000

    # Subtract proper motion if checkbox is checked
    if subtract_pm and len(pm_df) != 0:
        pmra = pm_df.iloc[0]["pmra_masyr"]
        pmdec = pm_df.iloc[0]["pmdec_masyr"]
        epochs = data_df["measurement_epoch_yr"].values

        data_df["rel_ra"] -= (epochs - epoch_ref) * pmra
        data_df["rel_dec"] -= (epochs - epoch_ref) * pmdec
    
    if subtract_plx and len(plx_df) != 0:
        epochs = data_df["measurement_epoch_yr"].values
        plxm = parallax_motion(ra_ref, dec_ref, epochs)
        data_df["rel_ra"] -= plxm["plx_motion_racosdec"]*plx_df.iloc[0]["parallax_mas"]
        data_df["rel_dec"] -= plxm["plx_motion_dec"]*plx_df.iloc[0]["parallax_mas"]

    # If binning is enabled
    if bin_activated:
        
        if phase_yearly:
            # Handle phasing
            data_df["binned_time"] = (data_df["measurement_epoch_yr"] % 1 // (bin_size_days_phased/365.25)) * (bin_size_days_phased/365.25)
        else:
            # Regular binning
            data_df["binned_time"] = (data_df["measurement_epoch_yr"] * 365.25 // bin_size_days) * bin_size_days / 365.25
        
        binned_df = data_df.groupby("binned_time").apply(weighted_combination).dropna().reset_index()

    # Assign a unique color to each mission
    unique_missions = data_df['mission'].unique()
    mission_color_map = {mission: i for i, mission in enumerate(unique_missions)}
    data_df["mission_color"] = data_df["mission"].map(mission_color_map)

    # Handle selection propagation
    if triggered_prop == "astrometry-plot-ra.selectedData" and selectedData_ra:
        selected_indices = [point["pointIndex"] for point in selectedData_ra["points"]]
    elif triggered_prop == "astrometry-plot-dec.selectedData" and selectedData_dec:
        selected_indices = [point["pointIndex"] for point in selectedData_dec["points"]]
    else:
        selected_indices = list(data_df.index)

    fig_ra = go.Figure()
    fig_dec = go.Figure()

    if phase_yearly:
        data_df["x_values"] = np.mod(data_df["measurement_epoch_yr"], 1)  # Phase yearly
        xaxis_title = "Yearly Phase (0 = Jan 1st, 1 = Dec 31st)"
    else:
        data_df["x_values"] = data_df["measurement_epoch_yr"]  # Original epochs
        xaxis_title = "Epoch (Year)"  # Default x-axis title

    #Plot the proper motion
    # Extract the full x-axis range from the figure (start and end)
    #xaxis_range = [data_df["measurement_epoch_yr"].min(), data_df["measurement_epoch_yr"].max()]
    data_min = data_df["x_values"].min()
    data_max = data_df["x_values"].max()

    # Add 5% padding
    padding = (data_max - data_min) * 0.05
    xaxis_range = [data_min - padding, data_max + padding]

    # Generate 5000 evenly spaced points across the x-axis range
    ntimep = 5000
    time_values = np.linspace(xaxis_range[0], xaxis_range[1], ntimep)

    if subtract_pm or len(pm_df) == 0:
        expected_rel_ra = np.zeros_like(time_values)
        expected_rel_dec = np.zeros_like(time_values)
    else:
        if phase_yearly:
            expected_rel_ra = (time_values+np.round(np.mean(data_df["measurement_epoch_yr"])) - epoch_ref) * pm_df.iloc[0]["pmra_masyr"]
            expected_rel_dec = (time_values+np.round(np.mean(data_df["measurement_epoch_yr"])) - epoch_ref) * pm_df.iloc[0]["pmdec_masyr"]
        else:
            expected_rel_ra = (time_values - epoch_ref) * pm_df.iloc[0]["pmra_masyr"]
            expected_rel_dec = (time_values - epoch_ref) * pm_df.iloc[0]["pmdec_masyr"]
    
    if not subtract_plx and len(plx_df) != 0:
        if phase_yearly:
            plxm = parallax_motion(ra_ref, dec_ref, time_values+np.round(np.mean(data_df["measurement_epoch_yr"])))
        else:    
            plxm = parallax_motion(ra_ref, dec_ref, time_values)
        expected_rel_ra += plxm["plx_motion_racosdec"]*plx_df.iloc[0]["parallax_mas"]
        expected_rel_dec += plxm["plx_motion_dec"]*plx_df.iloc[0]["parallax_mas"]

    # === Compute 1-sigma model envelopes from parameter uncertainties ===
    # Pull uncertainties (0 if missing)
    pmra_unc = float(pm_df.iloc[0]["pmra_masyr_unc"]) if len(pm_df) != 0 and pd.notna(pm_df.iloc[0]["pmra_masyr_unc"]) else 0.0
    pmdec_unc = float(pm_df.iloc[0]["pmdec_masyr_unc"]) if len(pm_df) != 0 and pd.notna(pm_df.iloc[0]["pmdec_masyr_unc"]) else 0.0
    plx_unc  = float(plx_df.iloc[0]["parallax_mas_unc"]) if len(plx_df) != 0 and pd.notna(plx_df.iloc[0]["parallax_mas_unc"]) else 0.0

    # Time factor for PM contribution
    if phase_yearly:
        dt_vals = (time_values + np.round(np.mean(data_df["measurement_epoch_yr"])) - epoch_ref)
    else:
        dt_vals = (time_values - epoch_ref)

    # Parallax motion terms for the envelope (zeroed if subtract_plx or no parallax)
    if (not subtract_plx) and (len(plx_df) != 0):
        if phase_yearly:
            plxm_env = parallax_motion(ra_ref, dec_ref, time_values + np.round(np.mean(data_df["measurement_epoch_yr"])))
        else:
            plxm_env = parallax_motion(ra_ref, dec_ref, time_values)
        plx_ra_term = plxm_env["plx_motion_racosdec"]
        plx_dec_term = plxm_env["plx_motion_dec"]
    else:
        plx_ra_term = np.zeros_like(time_values)
        plx_dec_term = np.zeros_like(time_values)

    # 1-sigma envelopes (independent errors, no covariance)
    sigma_model_ra = np.sqrt((dt_vals * pmra_unc)**2 + (plx_ra_term * plx_unc)**2)
    sigma_model_dec = np.sqrt((dt_vals * pmdec_unc)**2 + (plx_dec_term * plx_unc)**2)

    ra_envelope_upper = expected_rel_ra + sigma_model_ra
    ra_envelope_lower = expected_rel_ra - sigma_model_ra
    dec_envelope_upper = expected_rel_dec + sigma_model_dec
    dec_envelope_lower = expected_rel_dec - sigma_model_dec

    # Add line to RA figure
    fig_ra.add_trace(go.Scatter(
        x=time_values,
        y=expected_rel_ra,
        mode="lines",
        line=dict(color='rgba(100, 150, 250, 0.6)', width=4),  # Semi-transparent gray line
        name="MOCAdb solution",
        hoverinfo='skip'
    ))
    # Shaded 1-sigma band around RA model
    fig_ra.add_trace(go.Scatter(
        x=time_values,
        y=ra_envelope_lower,
        mode="lines",
        line=dict(width=0),
        hoverinfo='skip',
        showlegend=False,
        name="Model −1σ"
    ))
    fig_ra.add_trace(go.Scatter(
        x=time_values,
        y=ra_envelope_upper,
        mode="lines",
        line=dict(width=0),
        fill='tonexty',
        fillcolor='rgba(100, 150, 250, 0.15)',
        hoverinfo='skip',
        showlegend=True,
        name="Model ±1σ"
    ))

    # Add line to DEC figure
    fig_dec.add_trace(go.Scatter(
        x=time_values,
        y=expected_rel_dec,
        mode="lines",
        line=dict(color='rgba(100, 150, 250, 0.6)', width=4),  # Semi-transparent gray line
        name="MOCAdb solution",
        hoverinfo='skip'
    ))
    # Shaded 1-sigma band around DEC model
    fig_dec.add_trace(go.Scatter(
        x=time_values,
        y=dec_envelope_lower,
        mode="lines",
        line=dict(width=0),
        hoverinfo='skip',
        showlegend=False,
        name="Model −1σ"
    ))
    fig_dec.add_trace(go.Scatter(
        x=time_values,
        y=dec_envelope_upper,
        mode="lines",
        line=dict(width=0),
        fill='tonexty',
        fillcolor='rgba(100, 150, 250, 0.15)',
        hoverinfo='skip',
        showlegend=False,
        name="Model ±1σ"
    ))

    data_df['rel_ra_str'] = data_df['rel_ra'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['rel_dec_str'] = data_df['rel_dec'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['ra_unc_mas_str'] = data_df['ra_unc_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['dec_unc_mas_str'] = data_df['dec_unc_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['ra_str'] = data_df['ra'].apply(lambda x: f"{x:.6f}" if pd.notna(x) else "N/A")
    data_df['dec_str'] = data_df['dec'].apply(lambda x: f"{x:.6f}" if pd.notna(x) else "N/A")
    data_df['measurement_epoch_yr_str'] = data_df['measurement_epoch_yr'].apply(lambda x: f"{x:.4f}" if pd.notna(x) else "N/A")
    data_df['id_str'] = data_df['id'].apply(lambda x: f"{int(x):d}" if pd.notna(x) else "N/A")
    data_df['airmass_str'] = data_df['airmass'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['delta_ra_str'] = data_df['calibration_delta_ra_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['delta_dec_str'] = data_df['calibration_delta_dec_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    data_df['nstars_str'] = data_df['nstars_calibration'].apply(lambda x: f"{int(x):d}" if pd.notna(x) else "N/A")

    if bin_activated:
        binned_df['rel_ra_str'] = binned_df['rel_ra'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        binned_df['rel_dec_str'] = binned_df['rel_dec'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        binned_df['ra_unc_mas_str'] = binned_df['ra_unc_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        binned_df['dec_unc_mas_str'] = binned_df['dec_unc_mas'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")

    for mission in unique_missions:
        
        mission_data = data_df[data_df["mission"] == mission]
        opacity = 0.3 if bin_activated else 1.0  # Semi-transparent if binning is active

        fig_ra.add_trace(go.Scatter(
            x=mission_data["x_values"],
            y=mission_data["rel_ra"],
            mode='markers',
            error_y=dict(
                type='data',
                array=mission_data['ra_unc_mas'],
                visible=True,
                color='rgba(0, 0, 0, 0.2)',
                thickness=1.5,
                width=2
            ),
            marker=dict(
                color=mission_color_map[mission],  # Use the assigned color for this mission
                size=8,
                symbol='circle',
                opacity=opacity,
                line=dict(width=2, color='black')
            ),
            name=(mission + (f"  (σ_add={s_add_ra_by_mission.get(mission, 0.0):.2f} mas)" if inflate_errors and s_add_ra_by_mission.get(mission, 0.0) > 0 else "")),
            customdata=mission_data['id'],
            text=[
                (
                    f"<b>ID:</b> {row['id_str']}<br>"
                    f"<b>Mission:</b> {row['mission'] or 'N/A'}<br>"
                    f"<b>Reference:</b> {row['moca_pid'] or 'N/A'}<br>"
                    f"<b>Epoch:</b> {row['measurement_epoch_yr_str']} yr<br>"
                    f"<b>Relative R.A.:</b> {row['rel_ra_str']} ± {row['ra_unc_mas_str']} mas<br>"
                    f"<b>Relative Decl.:</b> {row['rel_dec_str']} ± {row['dec_unc_mas_str']} mas<br>"
                    f"<b>RA:</b> {row['ra_str']} deg<br>"
                    f"<b>DEC:</b> {row['dec_str']} deg<br>"
                    f"<b>Origin:</b> {row['origin'] or 'N/A'}<br>"
                    f"<b>Airmass:</b> {row['airmass_str']}<br>"
                    f"<b>Bandpass:</b> {row['moca_psid'] or 'N/A'}<br>"
                    f"<b>Calibration offset R.A.:</b> {row['delta_ra_str']} mas<br>"
                    f"<b>Calibration offset Decl.:</b> {row['delta_dec_str']} mas<br>"
                    f"<b>Calibration Nstars:</b> {row['nstars_str']}<br>"
                    f"<b>Calibration method:</b> {row['calibration_method'] or 'N/A'}<br>"
                    + ("<b>Flagged:</b> Outlier<br>" if row['is_outlier_ra'] else "")
                    + f"<b>Comments:</b> {wrap_text(row['comments'] or '', width=50)}"
                )
                for _, row in mission_data.iterrows()
            ],
            hoverinfo='text'
        ))

        # Overlay red X markers for RA outliers (non-inliers)
        out_ra = mission_data[mission_data['is_outlier_ra']]
        if not out_ra.empty:
            fig_ra.add_trace(go.Scatter(
                x=out_ra["x_values"],
                y=out_ra["rel_ra"],
                mode='markers',
                marker=dict(symbol='x-thin', size=14, color='red', line=dict(width=1, color='red')),
                showlegend=False,
                hoverinfo='skip'
            ))

    # Plot binned data points (black)
    if bin_activated:
        fig_ra.add_trace(go.Scatter(
            x=binned_df["binned_time"],
            y=binned_df["rel_ra"],
            error_y=dict(
                type='data',
                array=binned_df['ra_unc_mas'],
                visible=True,
                color='rgba(0, 0, 0, 0.2)',  
                thickness=1.5,               
                width=2                  
            ),
            mode="markers",
            marker=dict(
                size=10,
                color="white",
                symbol="circle",
                line=dict(width=3, color='black')
            ),
            name="Binned Data",
            hoverinfo="text",
            text=binned_df.apply(
                lambda row: 
                    f"<b>Epoch:</b> {row['binned_time']} yr<br>" \
                    f"<b>Relative R.A.:</b> {row['rel_ra_str']} ± {row['ra_unc_mas_str']} mas<br>" \
                    f"<b>Relative Decl.:</b> {row['rel_dec_str']} ± {row['dec_unc_mas_str']} mas<br>" \
                    f"<b>N Data:</b> {int(row['ndata'])}<br>" \
                    ,
                axis=1
            ),
        ))

    # Update layout for better legend positioning
    fig_ra.update_layout(
        plot_bgcolor='white',
        xaxis_title=xaxis_title, yaxis_title="RA Offset (mas)",
        xaxis=dict(
            range=xaxis_range,  # Use the manually defined range
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        yaxis=dict(
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        margin=dict(l=40, r=40, t=60, b=40),
        paper_bgcolor='white',
        showlegend=True,
        legend=dict(
             title=dict(
                text="<b> Missions</b>",  # Make the title bold
                font=dict(size=14)  # Optional: adjust font size
            ),
            #x=0.02, y=0.98,  # Adjust legend position as needed
            bgcolor='rgba(255, 255, 255, 0.5)',  # Optional: semi-transparent background
            bordercolor='black',
            borderwidth=2
        ),
        annotations=[
            dict(
                xref="paper", yref="paper",
                x=0.5, y=1.12,  # Position above the graph
                text=(f"<b>PMRA:</b> {pmra_display} | <b>PMDEC:</b> {pmdec_display} | <b>Parallax:</b> {parallax_display}"),
                showarrow=False,
                font=dict(size=14, color="black"),
                align="center"
            )
        ]
    )

    for mission in unique_missions:
        
        mission_data = data_df[data_df["mission"] == mission]
        opacity = 0.3 if bin_activated else 1.0  # Semi-transparent if binning is active

        fig_dec.add_trace(go.Scatter(
            x=mission_data["x_values"],
            y=mission_data["rel_dec"],
            mode='markers',
            error_y=dict(
                type='data',
                array=mission_data['dec_unc_mas'],
                visible=True,
                color='rgba(0, 0, 0, 0.2)',
                thickness=1.5,
                width=2
            ),
            marker=dict(
                color=mission_color_map[mission],  # Use the assigned color for this mission
                size=8,
                symbol='circle',
                opacity=opacity,
                line=dict(width=2, color='black')
            ),
            name=(mission + (f"  (σ_add={s_add_dec_by_mission.get(mission, 0.0):.2f} mas)" if inflate_errors and s_add_dec_by_mission.get(mission, 0.0) > 0 else "")),
            customdata=mission_data['id'],
            text=[
                (
                    f"<b>ID:</b> {row['id_str']}<br>"
                    f"<b>Mission:</b> {row['mission'] or 'N/A'}<br>"
                    f"<b>Relative R.A.:</b> {row['rel_ra_str']} ± {row['ra_unc_mas_str']} mas<br>"
                    f"<b>Relative Decl.:</b> {row['rel_dec_str']} ± {row['dec_unc_mas_str']} mas<br>"
                    f"<b>RA:</b> {row['ra_str']} deg<br>"
                    f"<b>DEC:</b> {row['dec_str']} deg<br>"
                    f"<b>Epoch:</b> {row['measurement_epoch_yr_str']} yr<br>"
                    f"<b>Reference:</b> {row['moca_pid'] or 'N/A'}<br>"
                    f"<b>Origin:</b> {row['origin'] or 'N/A'}<br>"
                    f"<b>Airmass:</b> {row['airmass_str']}<br>"
                    f"<b>Bandpass:</b> {row['moca_psid'] or 'N/A'}<br>"
                    + ("<b>Flagged:</b> Outlier<br>" if row['is_outlier_dec'] else "")
                    + f"<b>Comments:</b> {wrap_text(row['comments'] or '', width=50)}"
                )
                for _, row in mission_data.iterrows()
            ],
            hoverinfo='text'
        ))

        # Overlay red X markers for DEC outliers (non-inliers)
        out_dec = mission_data[mission_data['is_outlier_dec']]
        if not out_dec.empty:
            fig_dec.add_trace(go.Scatter(
                x=out_dec["x_values"],
                y=out_dec["rel_dec"],
                mode='markers',
                marker=dict(symbol='x-thin', size=14, color='red', line=dict(width=1, color='red')),
                showlegend=False,
                hoverinfo='skip'
            ))

    if bin_activated:
        fig_dec.add_trace(go.Scatter(
            x=binned_df["binned_time"],
            y=binned_df["rel_dec"],
            error_y=dict(
                type='data',
                array=binned_df['ra_unc_mas'],
                visible=True,
                color='rgba(0, 0, 0, 0.2)',  
                thickness=1.5,               
                width=2                  
            ),
            mode="markers",
            marker=dict(
                size=10,
                color="white",
                symbol="circle",
                line=dict(width=3, color='black')
            ),
            name="Binned Data",
            hoverinfo="text",
            text=binned_df.apply(
                lambda row: 
                    f"<b>Epoch:</b> {row['binned_time']} yr<br>" \
                    f"<b>Relative R.A.:</b> {row['rel_ra_str']} ± {row['ra_unc_mas_str']} mas<br>" \
                    f"<b>Relative Decl.:</b> {row['rel_dec_str']} ± {row['dec_unc_mas_str']} mas<br>" \
                    f"<b>N Data:</b> {int(row['ndata'])}<br>" \
                    ,
                axis=1
            ),
        ))
    
    # Update layout for better legend positioning
    fig_dec.update_layout(
        plot_bgcolor='white',
        xaxis_title=xaxis_title, yaxis_title="DEC Offset (mas)",
        xaxis=dict(
            range=xaxis_range,  # Use the manually defined range
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        yaxis=dict(
            gridcolor='rgba(211, 211, 211, 0.6)',
            zerolinecolor='lightgray',
            showline=True,
            linewidth=2,
            linecolor='black',
            mirror=True,
            ticks='outside',
            tickwidth=2,
        ),
        margin=dict(l=40, r=40, t=60, b=40),
        paper_bgcolor='white',
        showlegend=True,
        legend=dict(
             title=dict(
                text="<b> Missions</b>",  # Make the title bold
                font=dict(size=14)  # Optional: adjust font size
            ),
            #x=0.02, y=0.98,  # Adjust legend position as needed
            bgcolor='rgba(255, 255, 255, 0.5)',  # Optional: semi-transparent background
            bordercolor='black',
            borderwidth=1
        )
    )

    return fig_ra, fig_dec
