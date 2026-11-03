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

  function figure(data, revision, width = 800, count = 3, templateColor = "red") {
    // The reference figure is 10 inches wide; convert its point sizes to this viewport.
    const pt = (size, minimum = 0) => Math.max(minimum, size * Math.min(width, 1000) / 720);
    const raw = data.raw_spectrum || [], fit = data.fit;
    const spectrum = fit?.spectrum || {
      wavelength_um: raw.map((r) => finite(r.wavelength_angstrom) ? r.wavelength_angstrom / 1e4 : null),
      flux: raw.map((r) => r.flux_flambda), error: raw.map((r) => r.flux_flambda_unc),
      flagged: raw.map((r) => Boolean(r.ignored)),
    };
    const overlays = (fit?.overlays || []).slice(0, Math.max(1, Math.min(10, count)));
    const spectra = overlays.length ? overlays.map(o => o.spectrum || spectrum) : [spectrum];
    const goodFlux = spectra.flatMap(v => v.flux.filter((f, i) => finite(f) && !v.flagged[i]));
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
    const rowBounds = [];
    let laneGap = 0;
    if (data.stackLanes && overlays.length) {
      // Each reduction can have its own flux baseline and range. Give each
      // measured spectrum room rather than clipping it to a template's span.
      const bounds = spectra.map((v, i) => extent([
        ...overlays[i].flux, ...(overlays[i].curve_flux || []),
        ...v.flux.filter((f, j) => !v.flagged[j]),
      ]));
      laneGap = 0.18 * (Math.max(...bounds.map(([lo, hi]) => hi - lo)) || dataSpan);
      let bottom = bounds[bounds.length - 1][0] - laneGap / 2;
      for (let i = bounds.length - 1; i >= 0; i--) {
        const [lo, hi] = bounds[i];
        shifts[i] = bottom + laneGap / 2 - lo;
        rowBounds[i] = [bottom, bottom + (hi - lo) + laneGap];
        bottom = rowBounds[i][1];
      }
      yBounds = [rowBounds[rowBounds.length - 1][0], rowBounds[0][1]];
    }
    const yPad = 0.05 * (yBounds[1] - yBounds[0] || Math.abs(yBounds[1]) || 1);
    yBounds = [yBounds[0] - yPad, yBounds[1] + yPad];
    // Matplotlib's separate scientific multiplier; this is NOT median normalization.
    const exponent = Math.floor(Math.log10(Math.max(...yBounds.map(Math.abs)) || 1));
    const power = exponent <= -5 || exponent >= 6 ? exponent : 0;
    const unit = 10 ** power;
    const xBounds = extent(spectra.flatMap(v => v.wavelength_um));
    const xPad = 0.03 * (xBounds[1] - xBounds[0] || Math.abs(xBounds[1]) || 1);
    const traces = [], annotations = [], shapes = [];

    function points(flagged, shift, lower, upper, rank) {
      const spectrum = overlays[rank]?.spectrum || spectra[0];
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
      const [lower, upper] = rowBounds[i] || [overlay ? shift : -Infinity, overlay && i > 0 ? shift + offset : Infinity];
      // Draw flagged points behind the unflagged measurements, as in the PNG.
      points(true, shift, lower, upper, i);
      points(false, shift, lower, upper, i);
      const baseline = (rowBounds[i]?.[0] ?? shift) / unit;
      shapes.push({type: "line", xref: "paper", x0: 0, x1: 1, y0: baseline, y1: baseline,
        layer: "below", line: {color: "rgba(185,217,247,0.9)", width: pt(0.9, 0.7)}});
      if (!overlay) continue;
      const color = overlay.color || templateColor;
      const templateName = escapeText(overlay.label) + " (" + escapeText(overlay.grid) + ")";
      if (!overlay.no_template) traces.push({
        x: overlay.curve_wavelength_um || overlay.wavelength_um,
        y: (overlay.curve_flux || overlay.flux).map((f) => finite(f) ? (f + shift) / unit : null),
        type: "scatter", mode: "lines", name: templateName, showlegend: false,
        meta: {role: "template-curve", rank: i}, line: {color, width: pt(1.5, 1)},
        hoverinfo: "skip", connectgaps: false,
      }, {
        x: overlay.wavelength_um, y: overlay.flux.map((f) => finite(f) ? (f + shift) / unit : null),
        customdata: overlay.flux, type: "scatter", mode: "markers", name: templateName,
        showlegend: false, meta: {role: "template-points", rank: i},
        marker: {size: pt(3.8, 3), color, opacity: 0.7, line: {color, width: pt(0.5, 0.3)}},
        hovertemplate: "Wavelength: %{x:.4f} µm<br>Fλ: %{customdata:.4g}<extra>%{fullData.name}</extra>",
      });
      const row = fit.matches?.[i] || {};
      const chi2 = [overlay.display_reduced_chi2, row.robust_reduced_chi2_10pct_cap,
        row.reduced_chi2_10pct_cap, row.reduced_chi2].find(finite);
      annotations.push({
        x: xBounds[1] - 0.005 * (xBounds[1] - xBounds[0]),
        y: (rowBounds[i] ? rowBounds[i][0] + laneGap * 0.24 : templateBounds[i][0] + shift - 0.5 * freeSpace) / unit,
        xref: "x", yref: "y", text: "<b>" + escapeText(overlay.label) + "  χ²<sub>r</sub>=" +
          (finite(chi2) ? chi2.toFixed(1) : "—") + "</b>",
        showarrow: false, xanchor: "right", yanchor: "middle", font: {color, size: pt(14, 11)},
      });
    }
    if (power) annotations.push({xref: "paper", yref: "paper", x: 0, y: 1, yshift: 3,
      xanchor: "left", yanchor: "bottom", showarrow: false, font: {size: pt(10, 10), color: "black"},
      text: "1e" + String(power).replace("-", "−")});
    const compact = width < 520;
    const axis = {showgrid: true, gridcolor: "rgba(176,176,176,0.2)", gridwidth: 1,
      showline: true, mirror: true, linecolor: "black", linewidth: pt(1.5, 1.2),
      ticks: "outside", tickcolor: "black", ticklen: pt(3.5, 3), tickwidth: 1,
      tickfont: {size: pt(13, 10)}, zeroline: false, automargin: true};
    return {traces, layout: {
      margin: {l: compact ? 62 : Math.max(66, width * 0.083), r: 16,
        t: 26, b: Math.max(56, width * 0.072)},
      font: {family: '"DejaVu Sans", Arial, sans-serif', color: "black", size: 13},
      // Object identity and tool title already appear in the review UI.
      title: {text: ""},
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

  const lanes = [
    {key: "spiffstacker", label: "SPIFFStacker", color: "#2563eb"},
    {key: "spiff", label: "SPIFF", color: "#159570"},
    {key: "sublimeaperture", label: "SUBLIMEaperture", color: "#c75b12"},
  ];
  function comparisonFigure(data, revision, width = 800, count = 3, markReviewLane = true) {
    if (data.read_only) return figure(data, revision, width, count);
    const available = {...data.comparison, [data.lane]: data};
    const traces = [], annotations = [], shapes = [], layout = {};
    let sharedRange = [Infinity, -Infinity], legendShown = false;
    lanes.forEach((lane, i) => {
      const item = available[lane.key], suffix = i ? String(i + 1) : "";
      const x = "x" + suffix, y = "y" + suffix, low = (2 - i) / 3;
      const row = figure(item || {raw_spectrum: []}, revision, width, count, lane.color);
      const domain = [low + 0.025, low + 0.285];
      if (item) sharedRange = [Math.min(sharedRange[0], row.layout.xaxis.range[0]), Math.max(sharedRange[1], row.layout.xaxis.range[1])];
      if (!i) Object.assign(layout, row.layout);
      layout["xaxis" + suffix] = {...row.layout.xaxis, anchor: y, matches: i ? "x" : undefined,
        title: i === 2 ? row.layout.xaxis.title : {text: ""}};
      layout["yaxis" + suffix] = {...row.layout.yaxis, anchor: x, domain,
        title: {...row.layout.yaxis.title, text: "F<sub>λ</sub> + offset"}};
      for (const trace of item ? row.traces : []) {
        if (trace.showlegend) {trace.showlegend = !legendShown; legendShown = true;}
        traces.push({...trace, xaxis: x, yaxis: y, meta: {...trace.meta, lane: lane.key}});
      }
      for (const shape of item ? row.layout.shapes : []) shapes.push({...shape, yref: y});
      for (const a of item ? row.layout.annotations : []) annotations.push({...a,
        xref: a.xref === "paper" ? x + " domain" : x,
        yref: a.yref === "paper" ? y + " domain" : y,
        y: a.yref === "paper" ? a.y : Math.max(a.y, row.layout.yaxis.range[0] +
          0.075 * (row.layout.yaxis.range[1] - row.layout.yaxis.range[0]))});
      annotations.push({xref: "paper", yref: "paper", x: 0.5, y: domain[1] + 0.014,
        text: "<b>" + lane.label + (markReviewLane && lane.key === data.lane ? " · review lane" : "") + "</b>",
        showarrow: false, xanchor: "center", yanchor: "bottom", font: {color: lane.color, size: 15}});
      if (!item) {
        layout["yaxis" + suffix].visible = false;
        annotations.push({xref: "paper", yref: "paper", x: 0.5, y: (domain[0] + domain[1]) / 2,
          text: escapeText(data.comparison_errors?.[lane.key] || (Object.hasOwn(data, "comparison") ? "No active " + lane.label + " spectrum" : "Restart the review service to load companion spectra")),
          showarrow: false, font: {color: "#637787", size: 13}});
      }
    });
    for (let i = 0; i < 3; i++) if (sharedRange.every(Number.isFinite)) layout["xaxis" + (i ? i + 1 : "")].range = sharedRange;
    Object.assign(layout, {annotations, shapes, height: Math.max(840, count * 180 + 300),
      margin: {l: 75, r: 18, t: 45, b: 55}, uirevision: revision, showlegend: legendShown});
    return {traces, layout};
  }
  function laneStackFigure(available, revision, width = 800) {
    const rows = lanes.filter(lane => available[lane.key] && !available[lane.key].missing && !available[lane.key].error);
    const values = item => item.fit?.spectrum || {
      wavelength_um: (item.raw_spectrum || []).map(r => r.wavelength_angstrom / 1e4),
      flux: (item.raw_spectrum || []).map(r => r.flux_flambda),
      error: (item.raw_spectrum || []).map(r => r.flux_flambda_unc),
      flagged: (item.raw_spectrum || []).map(r => Boolean(r.ignored)),
    };
    const overlays = rows.map(lane => {
      const item = available[lane.key], spectrum = values(item), best = item.fit?.overlays?.[0];
      return {...best, color: lane.color, spectrum,
        label: lane.label + " · " + (best?.label || "no valid fit"),
        grid: best?.grid || "", no_template: !best,
        wavelength_um: best?.wavelength_um || spectrum.wavelength_um,
        flux: best?.flux || spectrum.flux};
    });
    const data = {stackLanes: true, fit: {overlays, spectrum: rows.length ? values(available[rows[0].key]) :
      {wavelength_um: [], flux: [], error: [], flagged: []},
      matches: rows.map(lane => available[lane.key].fit?.matches?.[0] || {})}};
    const result = figure(data, revision, width, 3);
    for (const trace of result.traces) trace.meta.lane = rows[trace.meta.rank]?.key;
    result.layout.height = Math.max(400, Math.min(700, width));
    return result;
  }
  const api = {figure, comparisonFigure, laneStackFigure, lanes};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SpherexReviewPlot = api;
})(typeof window === "undefined" ? globalThis : window);
