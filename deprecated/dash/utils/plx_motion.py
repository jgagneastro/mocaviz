import numpy as np
from PyAstronomy.pyasl import sunpos
from astropy.time import Time

def parallax_motion(ra, dec, epochs):
    """
    Computes parallax motion in RA*cos(DEC) and DEC.

    Parameters:
        ra (float): Right Ascension in degrees.
        dec (float): Declination in degrees.
        epochs (array): Epochs in decimal years.

    Returns:
        dict: Parallax motion in RA*cos(DEC) and DEC as 1D arrays.
    """
    # Ensure epochs is an array
    epochs = np.atleast_1d(epochs)

    # Convert decimal years to Julian Dates
    jd_epochs = Time(epochs, format='decimalyear').jd

    # Compute the Sun's position using JD
    _, _, _, sun_elong, sun_obl = sunpos(jd_epochs, full_output=True)

    # Convert inputs to radians
    ra_rad = np.radians(ra)  # Scalar input
    dec_rad = np.radians(dec)
    sun_elong_rad = np.radians(sun_elong)
    sun_obl_rad = np.radians(sun_obl)

    # Precompute trigonometric values
    cos_ra = np.cos(ra_rad)
    sin_ra = np.sin(ra_rad)
    cos_dec = np.cos(dec_rad)
    sin_dec = np.sin(dec_rad)
    cos_sun_obl = np.cos(sun_obl_rad)
    sin_sun_obl = np.sin(sun_obl_rad)
    cos_sun_elong = np.cos(sun_elong_rad)
    sin_sun_elong = np.sin(sun_elong_rad)

    # Compute parallax displacements
    plx_motion_racosdec = (cos_ra * cos_sun_obl * sin_sun_elong - sin_ra * cos_sun_elong) * cos_dec
    plx_motion_dec = (
        cos_dec * sin_sun_obl * sin_sun_elong
        - cos_ra * sin_dec * cos_sun_elong
        - sin_ra * sin_dec * cos_sun_obl * sin_sun_elong
    )

    return {
        "plx_motion_racosdec": np.squeeze(plx_motion_racosdec),
        "plx_motion_dec": np.squeeze(plx_motion_dec),
    }

""" # Example usage
ra = 10.0  # Right Ascension in degrees
dec = -5.0  # Declination in degrees
epochs = np.array([2024.0, 2024.5, 2025.0])  # Epochs in decimal years

result = parallax_motion(ra, dec, epochs)
print("Parallax Motion in RA*cos(DEC):", result["plx_motion_racosdec"])
print("Parallax Motion in DEC:", result["plx_motion_dec"]) """