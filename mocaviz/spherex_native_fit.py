"""Shared, signed-flux fitting on the actual native DR1 wavelength grid.

No DB, plotting, Torch or package-local imports. This file is copied verbatim
to MOCAviz; parity is tested by hash. Template interpolation never extrapolates.
"""

import numpy as np

VERSION = "native_signed_student4_v1"
# Selection has its own version: a new rejection rule does not change the fitter.
SELECTION_VERSION = "native_student4_nirguard_v1"
NIR_GUARD_PARAMETERS = {
    "selection_version": SELECTION_VERSION,
    "nir_guard_full_delta_max": 10.0,
    "nir_guard_short_delta_max": -2.0,
    "nir_guard_wave_um": [1.0, 2.5],
}


def nir_evidence_guard(grid, wave, flux, error, full_fit, ignored=None):
    """Reject weak full-spectrum L evidence contradicted by the 1–2.5 um fit.

    These are penalized Student-t deviance differences, not sigma/probability.
    Missing evidence is unassessed, never an automated bad classification.
    Strong full-spectrum evidence bypasses the short-range contradiction test.
    """
    full_delta = full_fit.get("delta_early_minus_late")
    result = dict(selection_version=SELECTION_VERSION, nir_guard_assessed=False,
                  nir_guard_reject=False, fit_nir_delta=None, fit_nir_n_used=0,
                  nir_guard_error=None)
    if full_delta is None or not np.isfinite(full_delta):
        result["nir_guard_error"] = "nonfinite_full_delta"
        return result
    if full_delta >= NIR_GUARD_PARAMETERS["nir_guard_full_delta_max"]:
        result["nir_guard_assessed"] = True
        return result
    wave = np.asarray(wave, dtype=float)
    mask = (wave < 10000.) | (wave >= 25000.)
    if ignored is not None:
        mask |= np.asarray(ignored, dtype=bool)
    try:
        partial = grid.fit(wave, flux, error, ignored=mask)
        delta = partial["delta_early_minus_late"]
        if delta is None or not np.isfinite(delta):
            raise ValueError("nonfinite_short_delta")
        result.update(nir_guard_assessed=True, fit_nir_delta=float(delta),
                      fit_nir_n_used=int(partial["best"]["n_used"]),
                      nir_guard_reject=bool(delta < NIR_GUARD_PARAMETERS["nir_guard_short_delta_max"]))
    except ValueError as exc:
        result["nir_guard_error"] = str(exc)
    return result


NU = 4.0


class NativeTemplateGrid:
    def __init__(self, rows):
        groups = {}
        for row in rows:
            groups.setdefault(int(row["moca_spherex_template_id"]), []).append(row)
        self.templates = []
        for key, group in sorted(groups.items()):
            group = sorted(group, key=lambda r: float(r["wavelength_angstrom"]))
            wave = np.asarray([r["wavelength_angstrom"] for r in group], float)
            flux = np.asarray([r["flux_flambda"] for r in group], float)
            valid = np.isfinite(wave) & np.isfinite(flux) & (wave > 0) & (flux > 0)
            wave, flux = wave[valid], flux[valid]
            if len(wave) < 2 or np.any(np.diff(wave) <= 0):
                raise ValueError(
                    "Templates require distinct ordered finite wavelengths"
                )
            self.templates.append({**group[0], "id": key, "wave": wave, "flux": flux})
        if not self.templates:
            raise ValueError("No templates")
        self.minimum = max(t["wave"][0] for t in self.templates)
        self.maximum = min(t["wave"][-1] for t in self.templates)
        if self.minimum >= self.maximum:
            raise ValueError("Templates have no common wavelength coverage")
        self._type_numbers = np.asarray([t["spectral_type_number"] for t in self.templates], float)
        grids = [str(t.get("grid_type") or "").strip().lower() for t in self.templates]
        self._prior_groups = np.array([
            0 if grid == "field" else 2 if grid in {"extreme subdwarfs", "extremely low gravity"} else 1
            for grid in grids
        ])
        self._cache = {}

    def project(self, wave):
        key = wave.tobytes()
        if key not in self._cache:
            if len(self._cache) >= 4:
                self._cache.clear()
            # Interpolate F_nu-proportional density, then convert back to F_lambda.
            self._cache[key] = np.asarray(
                [
                    np.interp(wave, t["wave"], t["flux"] * t["wave"] ** 2) / wave**2
                    for t in self.templates
                ]
            )
        return self._cache[key]

    def fit(self, wave, flux, error, ignored=None, options=None, *, ranking_only=False):
        options = options or {}
        wave, flux, error = [np.asarray(a, dtype=float) for a in (wave, flux, error)]
        if wave.ndim != 1 or wave.shape != flux.shape or wave.shape != error.shape:
            raise ValueError("Spectrum arrays must have equal one-dimensional shapes")
        ignored = (
            np.zeros(wave.shape, bool) if ignored is None else np.asarray(ignored, bool)
        )
        valid = (
            np.isfinite(wave)
            & np.isfinite(flux)
            & np.isfinite(error)
            & (error > 0)
            & ~ignored
        )
        common = (wave >= self.minimum) & (wave <= self.maximum)
        use = valid & common
        if use.sum() < 8:
            raise ValueError(
                "Fewer than eight valid points within common template coverage"
            )
        w, d, e = wave[use], flux[use], error[use]
        models = self.project(w)
        # Work in F_nu-proportional units for numerical conditioning. Pointwise
        # errors/floors transform identically: no wavelength-dependent weight cap.
        norm = float(np.median(np.abs(d * w**2)))
        if not np.isfinite(norm) or norm <= 0:
            norm = float(np.median(e * w**2))
        y, sigma = d * w**2 / norm, e * w**2 / norm
        sigma = np.maximum(sigma, 0.1 * np.abs(y))
        m = models * w[None, :] ** 2
        model_norm = np.median(m, axis=1)
        m = m / model_norm[:, None]
        invvar = 1 / sigma**2
        least_squares = np.maximum(
            0, (m * y * invvar).sum(axis=1) / (m * m * invvar).sum(axis=1)
        )
        median = np.maximum(0, np.median(y[None, :] / m, axis=1))
        solutions = []
        for initial in (least_squares, median):
            a = initial
            for _ in range(40):
                residual = (y[None, :] - a[:, None] * m) / sigma
                weight = invvar[None, :] * (NU + 1) / (NU + residual**2)
                updated = np.maximum(
                    0, (m * y * weight).sum(axis=1) / (m * m * weight).sum(axis=1)
                )
                if np.all(np.abs(updated - a) <= 1e-7 * (1 + np.abs(a))):
                    a = updated
                    break
                a = updated
            residual = (y[None, :] - a[:, None] * m) / sigma
            loss = ((NU + 1) * np.log1p(residual**2 / NU)).sum(axis=1)
            solutions.append((a, residual, loss))
        choose = solutions[1][2] < solutions[0][2]
        a = np.where(choose, solutions[1][0], solutions[0][0])
        residual = np.where(choose[:, None], solutions[1][1], solutions[0][1])
        loss = np.minimum(solutions[0][2], solutions[1][2])
        odds = [1.0, options.get("nonfield_odds_k", 500.0), options.get("nonfield_extreme_odds_k", 500000.0)]
        penalties = (2 * np.log(np.asarray(odds, float)))[self._prior_groups]
        scores = loss + penalties
        positive = np.flatnonzero(a > 0)
        if not len(positive):
            raise ValueError("No positive-amplitude template fit")
        ranked = positive[np.lexsort((self._type_numbers[positive], scores[positive]))]
        late = ranked[self._type_numbers[ranked] >= 10]
        early = ranked[self._type_numbers[ranked] < 10]
        gap = float(scores[early[0]] - scores[late[0]]) if len(early) and len(late) else None
        if ranking_only:
            return {
                "best": {"spectral_type_number": float(self._type_numbers[ranked[0]])},
                "delta_early_minus_late": gap,
            }
        records = []
        cap = float(options.get("chi2_sigma_cap", 5.0)) ** 2
        for i in ranked:
            t = self.templates[i]
            terms = residual[i] ** 2
            red = w >= 14000
            record = {
                "moca_spherex_template_id": t["id"],
                "spectral_type": t["spectral_type"],
                "display_type": t["spectral_type"],
                "spectral_type_number": float(t["spectral_type_number"]),
                "grid_type": t.get("grid_type"),
                "n_used": int(use.sum()),
                "scale_s": float(a[i] * norm / model_norm[i]),
                "selection_score": float(scores[i]),
                "selection_penalty": float(penalties[i]),
                "chi2_raw": float(terms.sum()),
                "reduced_chi2": float(terms.mean()),
                "chi2_raw_10pct": float(terms.sum()),
                "reduced_chi2_10pct": float(terms.mean()),
                "chi2_raw_10pct_cap": float(np.minimum(terms, cap).sum()),
                "reduced_chi2_10pct_cap": float(np.minimum(terms, cap).mean()),
                "robust_reduced_chi2_10pct_cap": float(np.minimum(terms, cap).mean()),
                "red_chi2_10pct": float(np.minimum(terms[red], cap).mean())
                if red.any()
                else None,
                "red_chi2_raw_10pct": float(np.minimum(terms[red], cap).sum())
                if red.any()
                else None,
                "n_red_used": int(red.sum()),
                "fit_version": VERSION,
                "objective": "Student-t deviance, nu=4, plus template prior penalty",
            }
            records.append(record)
        return {
            "best": records[0],
            "matches": records,
            "used": use,
            "n_available_in_template_range": int(common.sum()),
            "delta_early_minus_late": gap,
            "fit_version": VERSION,
        }


def fit_rows_on_grid(rows, grid, options=None, *, ranking_only=False):
    """Fit the same measured rows for queue selection and the plotted spectrum."""
    if not rows:
        raise ValueError("No spectral data points are available")
    rows = sorted(rows, key=lambda r: float(r["wavelength_angstrom"] or 0))
    wave, flux, error = [
        np.asarray([r.get(key) for r in rows], float)
        for key in ("wavelength_angstrom", "flux_flambda", "flux_flambda_unc")
    ]
    ignored = np.asarray([bool(r.get("ignored")) for r in rows])
    fit = grid.fit(wave, flux, error, ignored, options, ranking_only=ranking_only)
    return fit, wave, flux, error, ignored


def fit_spectrum_rows(rows, template_rows, options=None):
    """Build reviewer overlays for the signed native-grid fit."""
    if not rows:
        raise ValueError("No spectral data points are available")
    grid = (
        template_rows
        if isinstance(template_rows, NativeTemplateGrid)
        else NativeTemplateGrid(template_rows)
    )
    fit, wave, flux, error, ignored = fit_rows_on_grid(rows, grid, options)
    overlays = []
    for match in fit["matches"][:10]:
        template = next(
            t for t in grid.templates if t["id"] == match["moca_spherex_template_id"]
        )
        # Draw exactly the interpolant used for fitting, not a different spline.
        dense = np.linspace(grid.minimum, grid.maximum, 1000)
        curve = (
            np.interp(dense, template["wave"], template["flux"] * template["wave"] ** 2)
            / dense**2
        )
        inside = (template["wave"] >= grid.minimum) & (template["wave"] <= grid.maximum)
        overlays.append(
            {
                "label": match["display_type"],
                "grid": match["grid_type"],
                "display_reduced_chi2": match["reduced_chi2_10pct_cap"],
                "wavelength_um": (template["wave"][inside] / 1e4).tolist(),
                "flux": (template["flux"][inside] * match["scale_s"]).tolist(),
                "curve_wavelength_um": (dense / 1e4).tolist(),
                "curve_flux": (curve * match["scale_s"]).tolist(),
            }
        )
    valid = np.isfinite(wave) & np.isfinite(flux) & np.isfinite(error) & (error > 0)
    return {
        "best": fit["best"],
        "matches": fit["matches"],
        "overlays": overlays,
        "spectrum": {
            "wavelength_um": (wave[valid] / 1e4).tolist(),
            "flux": flux[valid].tolist(),
            "error": error[valid].tolist(),
            "flagged": ignored[valid].tolist(),
        },
        "bad_pixel_ids": [],
        "fit_version": VERSION,
        "delta_early_minus_late": fit["delta_early_minus_late"],
        "n_available_in_template_range": fit["n_available_in_template_range"],
        "options": {**(options or {}), "drop_worst_n": 0},
    }
