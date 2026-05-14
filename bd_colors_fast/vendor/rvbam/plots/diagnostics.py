from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import json
import numpy as np

import matplotlib
import os
if "MPLBACKEND" not in os.environ:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
try:
    import corner
except ImportError:  # pragma: no cover - optional dependency in deployed app
    corner = None

from rvbam.model.segment_loglike import SegmentLogLikelihood


@dataclass(frozen=True)
class PosteriorSummary:
    median: Dict[str, float]
    p16: Dict[str, float]
    p84: Dict[str, float]


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    if values.size == 0:
        return float("nan")
    order = np.argsort(values)
    v = values[order]
    w = weights[order]
    cw = np.cumsum(w)
    if cw[-1] <= 0:
        return float("nan")
    cw = cw / cw[-1]
    return float(np.interp(q, cw, v))


def summarize_posterior(samples: np.ndarray, weights: np.ndarray, names: Sequence[str]) -> PosteriorSummary:
    med = {}
    p16 = {}
    p84 = {}
    for i, name in enumerate(names):
        med[name] = weighted_quantile(samples[:, i], weights, 0.5)
        p16[name] = weighted_quantile(samples[:, i], weights, 0.16)
        p84[name] = weighted_quantile(samples[:, i], weights, 0.84)
    return PosteriorSummary(median=med, p16=p16, p84=p84)


def save_corner_plot(
    path: Path,
    samples: np.ndarray,
    weights: np.ndarray,
    names: Sequence[str],
    q_low: float = 0.005,
    q_high: float = 0.995,
) -> None:
    if samples.size == 0 or samples.ndim != 2 or samples.shape[0] == 0 or samples.shape[1] == 0:
        print("Warning: empty samples; skipping corner plot.")
        return
    if weights is None or weights.size == 0 or weights.shape[0] != samples.shape[0]:
        print("Warning: invalid weights; skipping corner plot.")
        return
    if not np.isfinite(weights).any() or np.sum(weights) <= 0:
        print("Warning: non-finite/zero weights; skipping corner plot.")
        return
    ranges = []
    for i in range(samples.shape[1]):
        vals = samples[:, i]
        finite = np.isfinite(vals)
        if not np.any(finite):
            print("Warning: no finite samples for a parameter; skipping corner plot.")
            return
        lo = weighted_quantile(vals[finite], weights[finite], q_low)
        hi = weighted_quantile(vals[finite], weights[finite], q_high)
        if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
            lo = float(np.nanmin(vals[finite]))
            hi = float(np.nanmax(vals[finite]))
        if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
            print("Warning: invalid parameter range; skipping corner plot.")
            return
        ranges.append((lo, hi))

    if corner is not None:
        try:
            fig = corner.corner(
                samples,
                weights=weights,
                labels=list(names),
                show_titles=True,
                title_fmt=".3g",
                range=ranges,
            )
        except ValueError as exc:
            print(f"Warning: corner plot failed ({exc}); using matplotlib fallback.")
        else:
            fig.savefig(path, dpi=150)
            plt.close(fig)
            return

    fig = _fallback_corner_plot(samples, weights, names, ranges)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _fallback_corner_plot(
    samples: np.ndarray,
    weights: np.ndarray,
    names: Sequence[str],
    ranges: Sequence[Tuple[float, float]],
):
    n_params = int(samples.shape[1])
    size = max(4.0, min(2.1 * n_params, 18.0))
    fig, axes = plt.subplots(n_params, n_params, figsize=(size, size), squeeze=False)
    weight_sum = float(np.sum(weights))
    plot_weights = weights / weight_sum if weight_sum > 0 else np.ones_like(weights) / max(weights.size, 1)
    summary = summarize_posterior(samples, plot_weights, names)

    for row in range(n_params):
        for col in range(n_params):
            ax = axes[row, col]
            if row < col:
                ax.axis("off")
                continue
            if row == col:
                values = samples[:, col]
                finite = np.isfinite(values)
                ax.hist(
                    values[finite],
                    bins=40,
                    range=ranges[col],
                    weights=plot_weights[finite],
                    color="#4f6d7a",
                    alpha=0.78,
                    histtype="stepfilled",
                )
                median = summary.median.get(names[col])
                p16 = summary.p16.get(names[col])
                p84 = summary.p84.get(names[col])
                if median is not None and np.isfinite(median):
                    ax.axvline(median, color="#202124", lw=1.0)
                    ax.set_title(f"{names[col]} = {median:.3g}", fontsize=8)
                for value in (p16, p84):
                    if value is not None and np.isfinite(value):
                        ax.axvline(value, color="#6b7280", lw=0.8, ls="--")
            else:
                x = samples[:, col]
                y = samples[:, row]
                finite = np.isfinite(x) & np.isfinite(y)
                ax.hist2d(
                    x[finite],
                    y[finite],
                    bins=36,
                    range=[ranges[col], ranges[row]],
                    weights=plot_weights[finite],
                    cmap="Blues",
                )

            if row == n_params - 1:
                ax.set_xlabel(names[col], fontsize=8)
            else:
                ax.set_xticklabels([])
            if col == 0 and row > 0:
                ax.set_ylabel(names[row], fontsize=8)
            elif col > 0:
                ax.set_yticklabels([])
            ax.tick_params(axis="both", labelsize=7)

    fig.tight_layout()
    return fig


def save_fit_plot(
    path: Path,
    data_wv: np.ndarray,
    data_flux: np.ndarray,
    data_err: np.ndarray,
    model_flux: np.ndarray,
    model_wv_hi: np.ndarray | None = None,
    model_flux_hi: np.ndarray | None = None,
    model_flux_samples_hi: Sequence[np.ndarray] | None = None,
    raw_model_wv: np.ndarray | None = None,
    raw_model_flux: np.ndarray | None = None,
    xlim: Tuple[float, float] | None = None,
    data_err_inflated: np.ndarray | None = None,
    param_lines: Sequence[str] | None = None,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    if data_err_inflated is not None:
        ax.errorbar(
            data_wv,
            data_flux,
            yerr=data_err_inflated,
            fmt=".",
            color="black",
            alpha=0.25,
            label="inflated err",
        )
    ax.errorbar(data_wv, data_flux, yerr=data_err, fmt=".", color="black", alpha=0.7, label="data")
    if raw_model_wv is not None and raw_model_flux is not None:
        ax.plot(raw_model_wv, raw_model_flux, color="tab:blue", lw=0.8, alpha=0.8, label="model (raw)")
    if model_wv_hi is not None and model_flux_samples_hi:
        for flux_hi in model_flux_samples_hi:
            ax.plot(model_wv_hi, flux_hi, color="tab:red", lw=0.6, alpha=0.12, label=None)
    if model_wv_hi is not None and model_flux_hi is not None:
        ax.plot(model_wv_hi, model_flux_hi, color="tab:red", lw=1.0, alpha=0.95, label="model")
    ax.plot(data_wv, model_flux, color="tab:red", lw=0.8, alpha=0.5, label=None)
    ax.set_xlabel("Wavelength")
    ax.set_ylabel("Flux")
    if xlim is not None:
        ax.set_xlim(xlim)
    if param_lines:
        ax.text(
            1.02,
            0.98,
            "\n".join(param_lines),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=7,
            family="monospace",
        )
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_run_diagnostics(
    outdir: Path,
    names: Sequence[str],
    samples: np.ndarray,
    weights: np.ndarray,
    loglike: SegmentLogLikelihood,
    keep_weight: float = 0.99,
    comments: str | None = None,
) -> PosteriorSummary:
    outdir.mkdir(parents=True, exist_ok=True)

    # Drop lowest-weight tail for cleaner diagnostics if requested
    if 0.0 < keep_weight < 1.0:
        order = np.argsort(weights)[::-1]
        w_sorted = weights[order]
        cum = np.cumsum(w_sorted)
        cutoff = keep_weight * cum[-1]
        keep_n = int(np.searchsorted(cum, cutoff, side="left") + 1)
        keep_idx = order[:keep_n]
        samples = samples[keep_idx]
        weights = weights[keep_idx]

    summary = summarize_posterior(samples, weights, names)

    summary_path = outdir / "posterior_summary.json"
    payload = {"median": summary.median, "p16": summary.p16, "p84": summary.p84}
    data = loglike.data
    if data is not None:
        seg = {
            "specid": data.specid,
            "window_number": data.window_number,
            "segment_number": data.segment_number,
        }
        if data.segment_bounds is not None:
            seg["wv_min"] = float(data.segment_bounds[0])
            seg["wv_max"] = float(data.segment_bounds[1])
        payload["segment"] = seg
    if comments:
        payload["comments"] = comments
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    corner_path = outdir / "corner.png"
    if samples.shape[0] <= samples.shape[1]:
        print("Warning: too few samples for corner plot; skipping.")
    else:
        save_corner_plot(corner_path, samples, weights, names)

    theta_med = summary.median
    model_flux = loglike.model_on_data(theta_med)
    sigma_eff = loglike.sigma_eff(theta_med)
    data = loglike.data
    if data.segment_bounds is not None:
        w0, w1 = data.segment_bounds
        model_wv_hi = np.linspace(w0, w1, 10000, dtype=float)
        model_flux_hi = loglike.model_on_grid(theta_med, model_wv_hi)
    else:
        model_wv_hi, model_flux_hi = loglike.model_on_log_grid(theta_med)
    model_flux_samples_hi = None
    if samples.shape[0] > 0 and model_wv_hi is not None:
        rng = np.random.default_rng(0)
        wsum = np.sum(weights)
        if wsum > 0:
            p = weights / wsum
        else:
            p = None
        draw_n = min(100, samples.shape[0])
        idx = rng.choice(samples.shape[0], size=draw_n, replace=samples.shape[0] < draw_n, p=p)
        model_flux_samples_hi = []
        for i in idx:
            theta = {name: float(samples[i, j]) for j, name in enumerate(names)}
            model_flux_samples_hi.append(loglike.model_on_grid(theta, model_wv_hi))
    fit_path = outdir / "model_fit.png"
    param_lines = []
    for name in names:
        med = summary.median.get(name)
        p16 = summary.p16.get(name)
        p84 = summary.p84.get(name)
        if med is None:
            continue
        if p16 is None or p84 is None:
            param_lines.append(f"{name}: {med:.3g}")
        else:
            err = 0.5 * (p84 - p16)
            param_lines.append(f"{name}: {med:.3g} +/- {err:.2g}")
    save_fit_plot(
        fit_path,
        data.wavelength,
        data.flux,
        data.flux_err,
        model_flux,
        model_wv_hi=model_wv_hi,
        model_flux_hi=model_flux_hi,
        data_err_inflated=sigma_eff,
        model_flux_samples_hi=model_flux_samples_hi,
        param_lines=param_lines,
    )

    return summary
