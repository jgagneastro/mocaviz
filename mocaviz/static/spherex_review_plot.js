/* Browser-only counterpart of spherex_pipeline's _plot_comparison.
 * Keep its row offsets, clipping, bounds and styling aligned with the PNGs.
 * No DOM, storage, network, credentials or database state belongs in this module.
 */
(function (root) {
  "use strict";
  const finite = Number.isFinite;
  const escapeText = (value) => String(value ?? "").replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;").replaceAll(">", "&gt;");

  function extent(values) {
    let low = Infinity, high = -Infinity;
    for (const value of values) if (finite(value)) {
      low = Math.min(low, value); high = Math.max(high, value);
    }
    return finite(low) ? [low, high] : [0, 0];
  }

  function figure(data, revision, width = 800) {
    // The reference figure is 10 inches wide; convert its point sizes to this viewport.
    const pt = (size, minimum = 0) => Math.max(minimum, size * Math.min(width, 1000) / 720);
    const raw = data.raw_spectrum || [], fit = data.fit;
    const spectrum = fit?.spectrum || {
      wavelength_um: raw.map((r) => finite(r.wavelength_angstrom) ? r.wavelength_angstrom / 1e4 : null),
      flux: raw.map((r) => r.flux_flambda), error: raw.map((r) => r.flux_flambda_unc),
      flagged: raw.map((r) => Boolean(r.ignored)),
    };
    const overlays = fit?.overlays || [];
    const goodFlux = spectrum.flux.filter((f, i) => finite(f) && !spectrum.flagged[i]);
    const dataBounds = extent(goodFlux.length ? goodFlux : spectrum.flux);
    const dataSpan = dataBounds[1] - dataBounds[0] || Math.abs(dataBounds[1]) || 1;
    // The default PNG uses the scaled template span, never a data outlier, for spacing.
    const templateBounds = overlays.map((o) => extent(o.flux));
    const baseSpan = Math.max(0, ...templateBounds.map(([a, b]) => b - a)) || dataSpan;
    const offset = 1.15 * baseSpan, freeSpace = offset - baseSpan;
    const shifts = overlays.map((_, i) => (overlays.length - 1 - i) * offset);
    let yBounds = overlays.length ? extent(templateBounds.flatMap(([a, b], i) =>
      [a + shifts[i], b + shifts[i]])) : extent(spectrum.flux.flatMap((f, i) =>
      finite(f) ? [f - (spectrum.error[i] || 0), f + (spectrum.error[i] || 0)] : []));
    const yPad = 0.05 * (yBounds[1] - yBounds[0] || Math.abs(yBounds[1]) || 1);
    yBounds = [yBounds[0] - yPad, yBounds[1] + yPad];
    // Matplotlib's separate scientific multiplier; this is NOT median normalization.
    const exponent = Math.floor(Math.log10(Math.max(...yBounds.map(Math.abs)) || 1));
    const power = exponent <= -5 || exponent >= 6 ? exponent : 0;
    const unit = 10 ** power;
    const xBounds = extent(spectrum.wavelength_um);
    const xPad = 0.03 * (xBounds[1] - xBounds[0] || Math.abs(xBounds[1]) || 1);
    const traces = [], annotations = [], shapes = [];

    function points(flagged, shift, lower, upper, rank) {
      const x = [], y = [], plus = [], minus = [], original = [];
      for (let i = 0; i < spectrum.flux.length; i++) {
        const w = spectrum.wavelength_um[i], f = spectrum.flux[i], value = f + shift;
        if (Boolean(spectrum.flagged[i]) !== flagged || !finite(w) || !finite(f) ||
            value < lower || value >= upper) continue;
        const error = finite(spectrum.error[i]) ? Math.max(0, spectrum.error[i]) : 0;
        x.push(w); y.push(value / unit); original.push(f);
        minus.push(Math.min(error, Math.max(0, value - lower)) / unit);
        plus.push(Math.min(error, Math.max(0, upper - value)) / unit);
      }
      if (!x.length) return;
      traces.push({
        x, y, customdata: original, type: "scatter", mode: "markers",
        name: flagged ? "Flagged bad data points" : "Comparison spectrum",
        meta: {role: flagged ? "flagged" : "data", rank}, legendgroup: flagged ? "flagged" : "data",
        showlegend: flagged && rank === 0, opacity: flagged ? 0.2 : 1,
        marker: flagged ? {symbol: "x-thin", size: pt(5, 4), color: "#ff7f0e", line: {color: "#ff7f0e", width: pt(1.5, 1)}} :
          {symbol: "circle", size: pt(4.2, 4), color: "white", line: {color: "#666666", width: pt(2, 1.2)}},
        error_y: {type: "data", symmetric: false, array: plus, arrayminus: minus,
          visible: true, thickness: pt(flagged ? 1.2 : 2, 1), width: 0, color: flagged ? "#ff7f0e" : "#999999"},
        hovertemplate: "Wavelength: %{x:.4f} µm<br>Fλ: %{customdata:.4g}<extra>%{fullData.name}</extra>",
      });
    }

    for (let i = 0; i < Math.max(1, overlays.length); i++) {
      const overlay = overlays[i], shift = shifts[i] || 0;
      const lower = overlay ? shift : -Infinity, upper = overlay && i > 0 ? shift + offset : Infinity;
      // Draw flagged points behind the unflagged measurements, as in the PNG.
      points(true, shift, lower, upper, i);
      points(false, shift, lower, upper, i);
      shapes.push({type: "line", xref: "paper", x0: 0, x1: 1, y0: shift / unit, y1: shift / unit,
        layer: "below", line: {color: "rgba(185,217,247,0.9)", width: pt(0.9, 0.7)}});
      if (!overlay) continue;
      const templateName = escapeText(overlay.label) + " (" + escapeText(overlay.grid) + ")";
      traces.push({
        x: overlay.curve_wavelength_um || overlay.wavelength_um,
        y: (overlay.curve_flux || overlay.flux).map((f) => finite(f) ? (f + shift) / unit : null),
        type: "scatter", mode: "lines", name: templateName, showlegend: false,
        meta: {role: "template-curve", rank: i}, line: {color: "red", width: pt(1.5, 1)},
        hoverinfo: "skip", connectgaps: false,
      }, {
        x: overlay.wavelength_um, y: overlay.flux.map((f) => finite(f) ? (f + shift) / unit : null),
        customdata: overlay.flux, type: "scatter", mode: "markers", name: templateName,
        showlegend: false, meta: {role: "template-points", rank: i},
        marker: {size: pt(3.8, 3), color: "red", opacity: 0.7, line: {color: "red", width: pt(0.5, 0.3)}},
        hovertemplate: "Wavelength: %{x:.4f} µm<br>Fλ: %{customdata:.4g}<extra>%{fullData.name}</extra>",
      });
      const row = fit.matches?.[i] || {};
      const chi2 = [overlay.display_reduced_chi2, row.robust_reduced_chi2_10pct_cap,
        row.reduced_chi2_10pct_cap, row.reduced_chi2].find(finite);
      annotations.push({
        x: xBounds[1] - 0.005 * (xBounds[1] - xBounds[0]),
        y: (templateBounds[i][0] + shift - 0.5 * freeSpace) / unit,
        xref: "x", yref: "y", text: "<b>" + escapeText(overlay.label) + "  χ²<sub>r</sub>=" +
          (finite(chi2) ? chi2.toFixed(1) : "—") + "</b>",
        showarrow: false, xanchor: "right", yanchor: "middle", font: {color: "red", size: pt(14, 11)},
      });
    }
    if (power) annotations.push({xref: "paper", yref: "paper", x: 0, y: 1, yshift: 3,
      xanchor: "left", yanchor: "bottom", showarrow: false, font: {size: pt(10, 10), color: "black"},
      text: "1e" + String(power).replace("-", "−")});
    const object = data.object || {};
    const laneNames = {spiff: "SPIFF", spiffstacker: "SPIFFStacker", sublimeaperture: "SUBLIMEaperture"};
    const compact = width < 520;
    const title = "SPHEREx Autotype:" + (compact ? "<br>" : " ") + "Comparison Spectrum vs Templates";
    const subtitle = [object.designation || "unknown", "moca_oid=" + object.moca_oid,
      "moca_specid=" + object.moca_specid, laneNames[data.lane] || data.lane].filter(Boolean)
      .map(escapeText).join(compact ? "<br>" : " | ");
    const axis = {showgrid: true, gridcolor: "rgba(176,176,176,0.2)", gridwidth: 1,
      showline: true, mirror: true, linecolor: "black", linewidth: pt(1.5, 1.2),
      ticks: "outside", tickcolor: "black", ticklen: pt(3.5, 3), tickwidth: 1,
      tickfont: {size: pt(13, 10)}, zeroline: false, automargin: true};
    return {traces, layout: {
      margin: {l: compact ? 62 : Math.max(66, width * 0.083), r: 16,
        t: compact ? 130 : Math.max(52, width * 0.058), b: Math.max(56, width * 0.072)},
      font: {family: '"DejaVu Sans", Arial, sans-serif', color: "black", size: 13},
      title: {text: title + "<br>" + subtitle,
        x: 0.5, xanchor: "center", y: compact ? 0.955 : 0.97, yanchor: "top",
        font: {size: compact ? 11 : pt(12, 11)}},
      xaxis: {...axis, title: {text: "Wavelength (µm)", font: {size: pt(15, 12)}, standoff: pt(4, 4)},
        range: [xBounds[0] - xPad, xBounds[1] + xPad]},
      yaxis: {...axis, title: {text: "Relative Spectral Flux Density + offset (F<sub>λ</sub>)",
        font: {size: pt(15, 12)}, standoff: pt(4, 4)}, range: yBounds.map((v) => v / unit), exponentformat: "none"},
      annotations, shapes, showlegend: traces.some((t) => t.showlegend),
      legend: {x: 0.99, y: 0.99, xanchor: "right", yanchor: "top", font: {size: pt(10, 10)},
        bgcolor: "rgba(255,255,255,0.9)", itemclick: false, itemdoubleclick: false},
      paper_bgcolor: "white", plot_bgcolor: "white", uirevision: revision,
    }};
  }

  const api = {figure};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SpherexReviewPlot = api;
})(typeof window === "undefined" ? globalThis : window);
