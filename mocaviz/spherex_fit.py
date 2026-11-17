"""Select the SPHEREx fitter using the spectrum's reduction provenance."""

from .spherex_autotype_core import fit_spectrum
from .spherex_native_fit import fit_spectrum_rows as native_fit_spectrum_rows


def is_native_cube(meta):
    return (meta.get("moca_specpackid") == 76 and
            meta.get("data_reduction_pipeline") == "SUBLIME3C native DR1 cube aperture extraction")


def spectrum_fit(meta, spectrum, templates, options=None):
    if is_native_cube(meta):
        return native_fit_spectrum_rows(spectrum, templates, options)
    return fit_spectrum(spectrum, templates, options)
