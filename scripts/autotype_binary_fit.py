#!/usr/bin/env python3
"""Fit unresolved-binary spectra using two-template linear mixtures.

This CLI searches over pairs of template spectra and fits:

    target_flux ~= a * template_1 + b * template_2

For each pair, scale factors are solved with weighted linear least squares on
the common wavelength grid (target wavelengths with interpolated templates).
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from itertools import combinations
from typing import List, Optional, Sequence, Tuple

import click
import numpy as np
import pandas as pd
from scipy.optimize import nnls


@dataclass
class Spectrum:
    name: str
    wave: np.ndarray
    flux: np.ndarray
    err: Optional[np.ndarray] = None


@dataclass
class FitResult:
    template_1: str
    template_2: str
    a: float
    b: float
    chi2: float
    red_chi2: float
    n_points: int


def _read_spectrum_csv(
    path: str,
    wave_col: str,
    flux_col: str,
    err_col: Optional[str],
    comment_char: str = "#",
) -> Spectrum:
    df = pd.read_csv(path, comment=comment_char)
    if wave_col not in df.columns or flux_col not in df.columns:
        raise click.ClickException(
            f"{path}: missing required columns '{wave_col}' and/or '{flux_col}'."
        )

    wave = pd.to_numeric(df[wave_col], errors="coerce").to_numpy(dtype=float)
    flux = pd.to_numeric(df[flux_col], errors="coerce").to_numpy(dtype=float)
    err = None
    if err_col and err_col in df.columns:
        err = pd.to_numeric(df[err_col], errors="coerce").to_numpy(dtype=float)

    finite = np.isfinite(wave) & np.isfinite(flux)
    if err is not None:
        finite &= np.isfinite(err) & (err > 0)
    wave = wave[finite]
    flux = flux[finite]
    err = err[finite] if err is not None else None

    if wave.size < 3:
        raise click.ClickException(f"{path}: not enough finite points after filtering.")

    order = np.argsort(wave)
    wave = wave[order]
    flux = flux[order]
    if err is not None:
        err = err[order]

    return Spectrum(name=os.path.basename(path), wave=wave, flux=flux, err=err)


def _normalize_flux(flux: np.ndarray, mode: str) -> np.ndarray:
    if mode == "none":
        return flux
    if mode == "median":
        norm = np.nanmedian(flux)
    elif mode == "mean":
        norm = np.nanmean(flux)
    else:
        raise ValueError(f"Unknown normalize mode: {mode}")
    if not np.isfinite(norm) or norm == 0:
        return flux
    return flux / norm


def _interp_template_to_target(
    tpl_wave: np.ndarray,
    tpl_flux: np.ndarray,
    target_wave: np.ndarray,
) -> np.ndarray:
    return np.interp(target_wave, tpl_wave, tpl_flux, left=np.nan, right=np.nan)


def _fit_two_component_linear(
    y: np.ndarray,
    t1: np.ndarray,
    t2: np.ndarray,
    sigma: Optional[np.ndarray],
    non_negative: bool,
) -> Tuple[float, float, float, int]:
    valid = np.isfinite(y) & np.isfinite(t1) & np.isfinite(t2)
    if sigma is not None:
        valid &= np.isfinite(sigma) & (sigma > 0)

    yv = y[valid]
    m = np.column_stack([t1[valid], t2[valid]])
    if yv.size < 3:
        return np.nan, np.nan, np.inf, 0

    if sigma is None:
        yw = yv
        mw = m
        sigma_eff = np.ones_like(yv)
    else:
        sigma_eff = sigma[valid]
        w = 1.0 / sigma_eff
        yw = yv * w
        mw = m * w[:, None]

    if non_negative:
        coeffs, _ = nnls(mw, yw)
        a, b = float(coeffs[0]), float(coeffs[1])
    else:
        coeffs, _, _, _ = np.linalg.lstsq(mw, yw, rcond=None)
        a, b = float(coeffs[0]), float(coeffs[1])

    model = a * t1[valid] + b * t2[valid]
    resid = (yv - model) / sigma_eff
    chi2 = float(np.sum(resid**2))
    return a, b, chi2, int(yv.size)


def _resolve_template_paths(template_globs: Sequence[str]) -> List[str]:
    paths: List[str] = []
    for pattern in template_globs:
        matched = glob.glob(pattern)
        if matched:
            paths.extend(matched)
        elif os.path.isfile(pattern):
            paths.append(pattern)
    deduped = sorted(set(paths))
    if len(deduped) < 2:
        raise click.ClickException(
            "Need at least two template files (after glob expansion)."
        )
    return deduped


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--target", "target_path", required=True, type=click.Path(exists=True))
@click.option(
    "--templates",
    "template_patterns",
    required=True,
    multiple=True,
    help="Template file(s) or glob(s). Repeat flag for multiple groups.",
)
@click.option("--wave-col", default="wavelength_microns", show_default=True)
@click.option("--flux-col", default="flux_flambda", show_default=True)
@click.option("--err-col", default="flux_error_flambda", show_default=True)
@click.option(
    "--normalize",
    type=click.Choice(["none", "median", "mean"], case_sensitive=False),
    default="median",
    show_default=True,
    help="Per-spectrum flux normalization applied before fitting.",
)
@click.option(
    "--allow-negative/--non-negative",
    default=False,
    show_default=True,
    help="Allow negative scale factors. Default enforces non-negative scales.",
)
@click.option("--top", "top_n", default=10, show_default=True, type=int)
@click.option(
    "--out",
    "out_path",
    default=None,
    type=click.Path(dir_okay=False),
    help="Optional output CSV path for ranked results.",
)
def main(
    target_path: str,
    template_patterns: Sequence[str],
    wave_col: str,
    flux_col: str,
    err_col: str,
    normalize: str,
    allow_negative: bool,
    top_n: int,
    out_path: Optional[str],
) -> None:
    """Fit all two-template combinations to a target spectrum."""
    target = _read_spectrum_csv(target_path, wave_col, flux_col, err_col)
    template_paths = _resolve_template_paths(template_patterns)
    templates = [
        _read_spectrum_csv(path, wave_col, flux_col, None) for path in template_paths
    ]

    target_flux = _normalize_flux(target.flux, normalize.lower())
    target_err = target.err.copy() if target.err is not None else None

    results: List[FitResult] = []
    for t1, t2 in combinations(templates, 2):
        tpl1_flux = _normalize_flux(t1.flux, normalize.lower())
        tpl2_flux = _normalize_flux(t2.flux, normalize.lower())
        t1i = _interp_template_to_target(t1.wave, tpl1_flux, target.wave)
        t2i = _interp_template_to_target(t2.wave, tpl2_flux, target.wave)

        a, b, chi2, n_points = _fit_two_component_linear(
            y=target_flux,
            t1=t1i,
            t2=t2i,
            sigma=target_err,
            non_negative=not allow_negative,
        )
        if not np.isfinite(chi2) or n_points < 3:
            continue
        dof = max(n_points - 2, 1)
        results.append(
            FitResult(
                template_1=t1.name,
                template_2=t2.name,
                a=a,
                b=b,
                chi2=chi2,
                red_chi2=chi2 / dof,
                n_points=n_points,
            )
        )

    if not results:
        raise click.ClickException("No valid template-pair fits were produced.")

    df = pd.DataFrame([r.__dict__ for r in results]).sort_values("red_chi2")
    click.echo(
        f"Evaluated {len(results)} template pairs. Showing best {min(top_n, len(df))}:"
    )
    click.echo(df.head(top_n).to_string(index=False, float_format=lambda x: f"{x:.6g}"))

    if out_path:
        df.to_csv(out_path, index=False)
        click.echo(f"\nWrote ranked results to: {out_path}")


if __name__ == "__main__":
    main()
