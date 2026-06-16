const rexState = {
  options: [],
  payload: null,
  selectedTab: "abundances",
  searchTimer: null,
  loadToken: 0,
};

const rexEl = {};
const rexColors = [
  "#2c7fb8",
  "#d95f0e",
  "#31a354",
  "#756bb1",
  "#c51b8a",
  "#636363",
  "#1b9e77",
  "#e6ab02",
  "#66a61e",
  "#a6761d",
];

document.addEventListener("DOMContentLoaded", initRetrievalExplorer);

const rexAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function rexAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), rexAppBaseUrl).toString();
}

async function initRetrievalExplorer() {
  collectRetrievalElements();
  readRetrievalUrlState();
  bindRetrievalControls();
  await searchRetrievals({ loadFirst: true });
}

function collectRetrievalElements() {
  [
    "rex-status",
    "rex-search",
    "rex-search-results",
    "rex-oid",
    "rex-atmosphere",
    "rex-find",
    "rex-load",
    "rex-include-ignored",
    "rex-show-envelope",
    "rex-show-clouds",
    "rex-abundance-mode",
    "rex-corner-size",
    "rex-clear-cache",
    "rex-selection-card",
    "rex-tp-plot",
    "rex-tp-loader",
    "rex-contribution-plot",
    "rex-summary",
    "rex-hint",
    "rex-tab-abundances",
    "rex-tab-parameters",
    "rex-tab-spectrum",
    "rex-tab-corner",
    "rex-abundance-plot",
    "rex-parameter-table",
    "rex-cloud-table",
    "rex-spectrum-plot",
    "rex-corner-plot",
  ].forEach((id) => {
    rexEl[id] = document.getElementById(id);
  });
}

function readRetrievalUrlState() {
  const params = new URLSearchParams(window.location.search);
  const oid = parseInteger(params.get("moca_oid") || params.get("oid"));
  if (oid) rexEl["rex-oid"].value = oid;
  rexEl["rex-include-ignored"].checked = asBool(params.get("include_ignored") || params.get("show_ignored"));
}

function bindRetrievalControls() {
  rexEl["rex-find"].addEventListener("click", () => searchRetrievals({ loadFirst: true }));
  rexEl["rex-load"].addEventListener("click", () => loadSelectedRetrieval());
  rexEl["rex-atmosphere"].addEventListener("change", () => loadSelectedRetrieval());
  rexEl["rex-include-ignored"].addEventListener("change", () => searchRetrievals({ loadFirst: true }));
  rexEl["rex-oid"].addEventListener("change", () => searchRetrievals({ loadFirst: true }));
  rexEl["rex-search"].addEventListener("input", () => {
    clearTimeout(rexState.searchTimer);
    rexState.searchTimer = setTimeout(() => searchRetrievals({ loadFirst: false, fromTextSearch: true }), 250);
  });
  rexEl["rex-search"].addEventListener("focus", () => {
    if (rexEl["rex-search"].value.trim()) searchRetrievals({ loadFirst: false, fromTextSearch: true });
  });
  document.addEventListener("click", (event) => {
    if (!rexEl["rex-search-results"].contains(event.target) && event.target !== rexEl["rex-search"]) {
      rexEl["rex-search-results"].hidden = true;
    }
  });
  for (const id of ["rex-show-envelope", "rex-show-clouds", "rex-abundance-mode", "rex-corner-size"]) {
    rexEl[id].addEventListener("change", renderRetrievalPayload);
  }
  rexEl["rex-clear-cache"].addEventListener("click", clearRetrievalCache);
  document.querySelectorAll("[data-rex-tab]").forEach((button) => {
    button.addEventListener("click", () => activateRetrievalTab(button.dataset.rexTab));
  });
}

function connectionParams() {
  const source = new URLSearchParams(window.location.search);
  const out = new URLSearchParams();
  for (const key of ["host", "port", "user", "username", "pwd", "password", "dbase", "db", "database", "mock"]) {
    if (source.has(key)) out.set(key, source.get(key) || "");
  }
  return out;
}

function retrievalQueryParams() {
  const params = connectionParams();
  const search = rexEl["rex-search"].value.trim();
  const oid = rexEl["rex-oid"].value.trim();
  if (search) params.set("q", search);
  if (oid) params.set("moca_oid", oid);
  if (rexEl["rex-include-ignored"].checked) params.set("include_ignored", "1");
  return params;
}

async function searchRetrievals(options = {}) {
  setRetrievalStatus("Loading retrievals", "loading");
  const params = retrievalQueryParams();
  try {
    const payload = await fetchJsonUrl(rexAppUrl(`api/retrieval-explorer/search?${params.toString()}`));
    if (!payload.ok) throw new Error(payload.error || "Could not load retrieval list");
    rexState.options = payload.options || [];
    renderRetrievalOptions();
    if (options.fromTextSearch) renderRetrievalSearchResults();
    if (options.loadFirst && rexState.options.length) {
      const current = selectedAtmosphereId();
      if (!current || !rexState.options.some((row) => Number(row.value) === current)) {
        rexEl["rex-atmosphere"].value = String(rexState.options[0].value);
      }
      await loadSelectedRetrieval();
    } else {
      setRetrievalStatus(`${rexState.options.length} retrievals`, "");
    }
  } catch (error) {
    setRetrievalStatus(error.message || "Could not load retrievals", "error");
    renderRetrievalOptions();
  }
}

function renderRetrievalOptions() {
  if (!rexState.options.length) {
    rexEl["rex-atmosphere"].innerHTML = '<option value="">No retrievals found</option>';
    return;
  }
  rexEl["rex-atmosphere"].innerHTML = rexState.options.map((row) => (
    `<option value="${escapeHtml(row.value)}">${escapeHtml(row.label || `retrieval ${row.value}`)}</option>`
  )).join("");
  const params = new URLSearchParams(window.location.search);
  const requested = parseInteger(params.get("id") || params.get("atmosphere_id") || params.get("retrieval_id"));
  if (requested && rexState.options.some((row) => Number(row.value) === requested)) {
    rexEl["rex-atmosphere"].value = String(requested);
  }
}

function renderRetrievalSearchResults() {
  const box = rexEl["rex-search-results"];
  const options = rexState.options.slice(0, 12);
  if (!options.length || !rexEl["rex-search"].value.trim()) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  box.innerHTML = options.map((row) => (
    `<button type="button" data-atmosphere-id="${escapeHtml(row.value)}">${escapeHtml(row.label || row.value)}</button>`
  )).join("");
  box.querySelectorAll("button[data-atmosphere-id]").forEach((button) => {
    button.addEventListener("click", () => {
      rexEl["rex-atmosphere"].value = button.dataset.atmosphereId;
      box.hidden = true;
      loadSelectedRetrieval();
    });
  });
  box.hidden = false;
}

function selectedAtmosphereId() {
  return parseInteger(rexEl["rex-atmosphere"].value);
}

async function loadSelectedRetrieval() {
  const atmosphereId = selectedAtmosphereId();
  if (!atmosphereId) return;
  const token = ++rexState.loadToken;
  setRetrievalStatus("Loading retrieval", "loading");
  setRetrievalLoader(true);
  const params = connectionParams();
  if (rexEl["rex-include-ignored"].checked) params.set("include_ignored", "1");
  try {
    const payload = await fetchJsonUrl(rexAppUrl(`api/retrieval-explorer/atmosphere/${atmosphereId}?${params.toString()}`));
    if (token !== rexState.loadToken) return;
    if (!payload.ok) throw new Error(payload.error || "Could not load retrieval");
    rexState.payload = payload;
    updateRetrievalUrl(atmosphereId);
    renderRetrievalPayload();
    setRetrievalStatus(retrievalStatusText(payload), "");
  } catch (error) {
    if (token !== rexState.loadToken) return;
    setRetrievalStatus(error.message || "Could not load retrieval", "error");
    rexState.payload = null;
    renderRetrievalPayload();
  } finally {
    if (token === rexState.loadToken) setRetrievalLoader(false);
  }
}

function renderRetrievalPayload() {
  renderRetrievalSummary();
  renderTpPlot();
  renderContributionPlot();
  renderAbundancePlot();
  renderParameterTables();
  renderSpectrumPlot();
  renderCornerPlot();
  activateRetrievalTab(rexState.selectedTab);
}

function retrievalStatusText(payload) {
  const atmosphere = payload?.atmosphere || {};
  const designation = atmosphere.designation || atmosphere.object_designation || `oid${atmosphere.moca_oid || ""}`;
  const source = atmosphere.bibcode || atmosphere.publication_bibcode || atmosphere.moca_pid || "retrieval";
  return `${designation} | ${source}`;
}

function renderRetrievalSummary() {
  const payload = rexState.payload;
  if (!payload?.atmosphere?.id) {
    rexEl["rex-summary"].textContent = "No retrieval loaded";
    rexEl["rex-selection-card"].textContent = "No retrieval loaded";
    return;
  }
  const a = payload.atmosphere;
  const bits = [
    a.designation || a.object_designation || `oid${a.moca_oid || "?"}`,
    a.bibcode || a.publication_bibcode || a.moca_pid,
    a.retrieval_code,
    a.retrieval_model,
    a.time_bin_label,
  ].filter(Boolean);
  rexEl["rex-summary"].textContent = bits.join(" | ");
  rexEl["rex-hint"].textContent = `${payload.meta?.profile_count || 0} T/P points, ${payload.meta?.cloud_parameter_count || 0} cloud parameters, ${payload.meta?.abundance_count || 0} abundance rows.`;
  rexEl["rex-selection-card"].innerHTML = [
    ["Atmosphere ID", a.id],
    ["Object", a.designation || a.object_designation || a.moca_oid],
    ["Publication", a.bibcode || a.publication_bibcode || a.moca_pid],
    ["Code", a.retrieval_code],
    ["Model", a.retrieval_model],
    ["Chemistry", a.chemistry_assumption],
    ["Clouds", a.cloud_assumption],
    ["Input specid", a.moca_specid],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "").map(([label, value]) => (
    `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`
  )).join("");
}

function renderTpPlot() {
  const profiles = (rexState.payload?.profiles || [])
    .map((row) => ({ ...row, pressure: asNumber(row.pressure_bar), value: profileValue(row) }))
    .filter((row) => row.pressure !== null && row.pressure > 0 && row.value !== null)
    .sort((a, b) => a.pressure - b.pressure);
  if (!profiles.length) {
    Plotly.react(rexEl["rex-tp-plot"], [], emptyLayout("No T/P profile rows"), plotConfig("retrieval_tp_empty"));
    return;
  }
  const traces = [];
  const showEnvelope = rexEl["rex-show-envelope"].checked;
  const p16 = profiles.map((row) => envelopeLow(row));
  const p84 = profiles.map((row) => envelopeHigh(row));
  const hasEnvelope = showEnvelope && p16.some(isFiniteNumber) && p84.some(isFiniteNumber);
  if (hasEnvelope) {
    traces.push({
      type: "scatter",
      mode: "lines",
      name: "p16",
      x: p16,
      y: profiles.map((row) => row.pressure),
      line: { width: 0, color: "rgba(44,127,184,0)" },
      hoverinfo: "skip",
      showlegend: false,
    });
    traces.push({
      type: "scatter",
      mode: "lines",
      name: "p84-p16",
      x: p84,
      y: profiles.map((row) => row.pressure),
      line: { width: 0, color: "rgba(44,127,184,0)" },
      fill: "tonextx",
      fillcolor: "rgba(44,127,184,.18)",
      hoverinfo: "skip",
      showlegend: false,
    });
  }
  traces.push({
    type: "scatter",
    mode: "lines+markers",
    name: "T/P",
    x: profiles.map((row) => row.value),
    y: profiles.map((row) => row.pressure),
    line: { color: "#1f4e79", width: 2.5 },
    marker: { size: 4, color: "#1f4e79" },
    hovertemplate: "T=%{x:.4g} K<br>P=%{y:.4g} bar<extra></extra>",
  });
  const shapes = rexEl["rex-show-clouds"].checked ? cloudPressureShapes(rexState.payload?.cloudParameters || []) : [];
  const annotations = rexEl["rex-show-clouds"].checked ? cloudPressureAnnotations(rexState.payload?.cloudParameters || []) : [];
  const layout = {
    margin: { l: 74, r: 20, t: 22, b: 54 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    xaxis: { title: "Temperature (K)", gridcolor: "#e3e1e6", zeroline: false },
    yaxis: { title: "Pressure (bar)", type: "log", autorange: "reversed", gridcolor: "#e3e1e6", zeroline: false },
    showlegend: false,
    shapes,
    annotations,
  };
  Plotly.react(rexEl["rex-tp-plot"], traces, layout, plotConfig("retrieval_tp"));
}

function profileValue(row) {
  return asNumber(row.value_p50 ?? row.value ?? row.temperature_k);
}

function envelopeLow(row) {
  const direct = asNumber(row.value_p16);
  if (direct !== null) return direct;
  const value = profileValue(row);
  const unc = asNumber(row.value_unc_neg ?? row.value_unc);
  return value !== null && unc !== null ? value - Math.abs(unc) : null;
}

function envelopeHigh(row) {
  const direct = asNumber(row.value_p84);
  if (direct !== null) return direct;
  const value = profileValue(row);
  const unc = asNumber(row.value_unc_pos ?? row.value_unc);
  return value !== null && unc !== null ? value + Math.abs(unc) : null;
}

function cloudPressureRows(rows) {
  return rows.map((row) => {
    let pressure = asNumber(row.pressure_bar);
    if (pressure === null && String(row.value_unit || row.default_unit || "").toLowerCase() === "bar") {
      pressure = asNumber(row.value_p50 ?? row.value);
    }
    if (pressure === null || pressure <= 0) return null;
    return {
      ...row,
      pressure,
      label: row.component_label || row.species_formula || row.parameter_name || row.moca_atparid || "cloud",
    };
  }).filter(Boolean);
}

function cloudPressureShapes(rows) {
  const clouds = cloudPressureRows(rows);
  const shapes = [];
  const byLabel = new Map();
  for (const row of clouds) {
    const key = row.label;
    if (!byLabel.has(key)) byLabel.set(key, {});
    const item = byLabel.get(key);
    const id = String(row.moca_atparid || "");
    if (id.includes("TOP")) item.top = row.pressure;
    if (id.includes("BASE") || id.includes("BOTTOM")) item.base = row.pressure;
  }
  let rectIndex = 0;
  byLabel.forEach((item) => {
    if (!item.top || !item.base || item.top === item.base) return;
    shapes.push({
      type: "rect",
      xref: "paper",
      x0: 0,
      x1: 1,
      yref: "y",
      y0: Math.min(item.top, item.base),
      y1: Math.max(item.top, item.base),
      fillcolor: rectIndex % 2 ? "rgba(166,97,26,.10)" : "rgba(49,115,92,.10)",
      line: { width: 0 },
      layer: "below",
    });
    rectIndex += 1;
  });
  clouds.slice(0, 12).forEach((row, index) => {
    shapes.push({
      type: "line",
      xref: "paper",
      x0: 0,
      x1: 1,
      yref: "y",
      y0: row.pressure,
      y1: row.pressure,
      line: { color: rexColors[index % rexColors.length], width: 1.2, dash: "dot" },
    });
  });
  return shapes;
}

function cloudPressureAnnotations(rows) {
  return cloudPressureRows(rows).slice(0, 6).map((row, index) => ({
    xref: "paper",
    x: 1,
    xanchor: "right",
    yref: "y",
    y: row.pressure,
    text: escapeHtml(row.label),
    showarrow: false,
    font: { size: 10, color: rexColors[index % rexColors.length] },
    bgcolor: "rgba(255,255,255,.72)",
    borderpad: 2,
  }));
}

function renderContributionPlot() {
  const rows = (rexState.payload?.contributionFunctions || [])
    .map((row) => ({ ...row, pressure: asNumber(row.pressure_bar), value: asNumber(row.value_p50 ?? row.value) }))
    .filter((row) => row.pressure !== null && row.pressure > 0 && row.value !== null);
  if (!rows.length) {
    Plotly.react(rexEl["rex-contribution-plot"], [], emptyLayout("No contribution functions"), plotConfig("retrieval_contribution_empty"));
    return;
  }
  const groups = groupBy(rows, (row) => row.component_label || row.species_formula || row.spectral_region_label || `axis ${row.profile_axis_index}`);
  const traces = Array.from(groups.entries()).slice(0, 10).map(([label, group], index) => {
    const sorted = group.slice().sort((a, b) => a.pressure - b.pressure);
    const maxValue = Math.max(...sorted.map((row) => Math.abs(row.value || 0)), 1e-12);
    return {
      type: "scatter",
      mode: "lines",
      name: label,
      x: sorted.map((row) => row.value / maxValue),
      y: sorted.map((row) => row.pressure),
      line: { color: rexColors[index % rexColors.length], width: 2 },
      hovertemplate: `${escapeHtml(label)}<br>CF=%{x:.3f}<br>P=%{y:.4g} bar<extra></extra>`,
    };
  });
  const layout = {
    margin: { l: 64, r: 8, t: 22, b: 54 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    xaxis: { title: "Contribution", range: [0, 1.05], gridcolor: "#e3e1e6", zeroline: false },
    yaxis: { title: "Pressure (bar)", type: "log", autorange: "reversed", gridcolor: "#e3e1e6", zeroline: false },
    legend: { orientation: "h", y: -0.22, font: { size: 10 } },
  };
  Plotly.react(rexEl["rex-contribution-plot"], traces, layout, plotConfig("retrieval_contribution"));
}

function renderAbundancePlot() {
  const payload = rexState.payload;
  const targetRows = payload?.abundances || [];
  const comparisonRows = payload?.comparisonAbundances || [];
  const rows = rexEl["rex-abundance-mode"].value === "population" ? comparisonRows : comparisonRows.filter((row) => Number(row.selected_object || 0) === 1 || sameObject(row, payload?.atmosphere));
  if (!targetRows.length) {
    Plotly.react(rexEl["rex-abundance-plot"], [], emptyLayout("No abundance rows"), plotConfig("retrieval_abundance_empty"));
    return;
  }
  const types = abundanceOrder(targetRows, rows);
  const selected = targetRows.filter((row) => asNumber(row.feh_val) !== null);
  const context = rows.filter((row) => asNumber(row.feh_val) !== null && !selected.some((sel) => Number(sel.id) === Number(row.id)));
  const traces = [];
  if (context.length) {
    traces.push({
      type: "box",
      name: "Comparison",
      x: context.map((row) => asNumber(row.feh_val)),
      y: context.map((row) => row.abundance_type),
      orientation: "h",
      boxpoints: "outliers",
      marker: { color: "rgba(95,88,100,.38)", size: 4 },
      line: { color: "rgba(95,88,100,.75)" },
      hovertemplate: "%{y}<br>%{x:.4g}<extra>comparison</extra>",
    });
  }
  traces.push({
    type: "scatter",
    mode: "markers",
    name: "Selected retrieval",
    x: selected.map((row) => asNumber(row.feh_val)),
    y: selected.map((row) => row.abundance_type),
    error_x: {
      type: "data",
      array: selected.map((row) => asNumber(row.feh_unc_pos ?? row.feh_unc) || 0),
      arrayminus: selected.map((row) => asNumber(row.feh_unc_neg ?? row.feh_unc) || 0),
      visible: true,
      color: "#1f1f1f",
      thickness: 1,
    },
    marker: { size: 10, color: "#9b4b3f", line: { color: "#2b2424", width: 1 } },
    hovertemplate: "%{y}<br>%{x:.4g}<extra>selected</extra>",
  });
  const solarRows = (payload?.solarReferences || []).filter((row) => types.includes(row.abundance_type));
  if (solarRows.length) {
    traces.push({
      type: "scatter",
      mode: "markers",
      name: "Reference",
      x: solarRows.map((row) => row.value),
      y: solarRows.map((row) => row.abundance_type),
      marker: { symbol: "line-ns-open", size: 18, color: "#222222", line: { width: 2 } },
      hovertemplate: "%{y}<br>%{x:.4g}<extra>reference</extra>",
    });
  }
  const layout = {
    margin: { l: 138, r: 20, t: 20, b: 50 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    xaxis: { title: "Reported value", gridcolor: "#e3e1e6", zeroline: true, zerolinecolor: "#c9c5cc" },
    yaxis: { categoryorder: "array", categoryarray: types.slice().reverse(), automargin: true },
    legend: { orientation: "h", y: -0.18 },
    boxmode: "group",
  };
  Plotly.react(rexEl["rex-abundance-plot"], traces, layout, plotConfig("retrieval_abundance"));
}

function sameObject(row, atmosphere) {
  return atmosphere?.moca_oid !== undefined && Number(row.moca_oid) === Number(atmosphere.moca_oid);
}

function abundanceOrder(targetRows, contextRows) {
  const kindRank = {
    molecular_vmr: 0,
    combined_gas_vmr: 1,
    bulk_metallicity: 2,
    elemental_ratio: 3,
    elemental_abundance: 4,
    stellar_metallicity: 5,
  };
  const rows = [...targetRows, ...contextRows];
  const meta = new Map();
  rows.forEach((row) => {
    if (!row.abundance_type || meta.has(row.abundance_type)) return;
    meta.set(row.abundance_type, row.quantity_kind || "");
  });
  return Array.from(meta.keys()).sort((a, b) => {
    const ka = kindRank[meta.get(a)] ?? 99;
    const kb = kindRank[meta.get(b)] ?? 99;
    return ka === kb ? a.localeCompare(b) : ka - kb;
  });
}

function renderParameterTables() {
  renderTable(rexEl["rex-parameter-table"], rexState.payload?.scalarParameters || [], [
    ["Kind", (row) => row.parameter_kind],
    ["Parameter", (row) => row.parameter_name || row.moca_atparid],
    ["Component", (row) => compactJoin([row.component_label, row.species_formula], " ")],
    ["Value", formatParameterValue],
    ["Unit", (row) => row.value_unit || row.default_unit],
  ]);
  renderTable(rexEl["rex-cloud-table"], rexState.payload?.cloudParameters || [], [
    ["Parameter", (row) => row.parameter_name || row.moca_atparid],
    ["Component", (row) => compactJoin([row.component_label, row.species_formula], " ")],
    ["Pressure", (row) => formatNumber(row.pressure_bar || (String(row.value_unit || row.default_unit).toLowerCase() === "bar" ? row.value : null))],
    ["Value", formatParameterValue],
    ["Unit", (row) => row.value_unit || row.default_unit],
  ]);
}

function formatParameterValue(row) {
  const value = row.value_text || (row.value_p50 ?? row.value);
  const text = formatNumber(value);
  const lo = asNumber(row.value_p16);
  const hi = asNumber(row.value_p84);
  if (lo !== null && hi !== null && asNumber(value) !== null) return `${text} [${formatNumber(lo)}, ${formatNumber(hi)}]`;
  const unc = asNumber(row.value_unc);
  return unc !== null ? `${text} +/- ${formatNumber(unc)}` : text;
}

function renderSpectrumPlot() {
  const spectrum = rexState.payload?.retrievedSpectrum || {};
  if (!spectrum.available) {
    Plotly.react(rexEl["rex-spectrum-plot"], [], emptyLayout(spectrum.message || "No retrieved spectrum product"), plotConfig("retrieval_spectrum_empty"));
    return;
  }
  const traces = [];
  if (spectrum.observed_brightness_temperature_k?.length) {
    traces.push({
      type: "scatter",
      mode: "markers",
      name: "observed",
      x: spectrum.wavelength_um,
      y: spectrum.observed_brightness_temperature_k,
      marker: { size: 5, color: "#ffffff", line: { color: "#000000", width: 1 } },
      hovertemplate: "lambda=%{x:.3f} um<br>Tb=%{y:.4g} K<extra>observed</extra>",
    });
  }
  if (spectrum.best_fit_brightness_temperature_k?.length) {
    traces.push({
      type: "scatter",
      mode: "lines",
      name: "best-fit",
      x: spectrum.wavelength_um,
      y: spectrum.best_fit_brightness_temperature_k,
      line: { color: "#5f5f5f", width: 2.5 },
      hovertemplate: "lambda=%{x:.3f} um<br>Tb=%{y:.4g} K<extra>best-fit</extra>",
    });
  }
  (spectrum.components || []).forEach((component, index) => {
    traces.push({
      type: "scatter",
      mode: "lines",
      name: component.label || `component ${index + 1}`,
      x: component.wavelength_um,
      y: component.brightness_temperature_k,
      line: { color: component.color || rexColors[index % rexColors.length], width: 1.8 },
      hovertemplate: "lambda=%{x:.3f} um<br>Tb=%{y:.4g} K<extra></extra>",
    });
  });
  const layout = {
    margin: { l: 70, r: 20, t: 22, b: 54 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    xaxis: { title: "Wavelength (um)", gridcolor: "#e3e1e6", zeroline: false },
    yaxis: { title: "Brightness temperature (K)", gridcolor: "#e3e1e6", zeroline: false },
    legend: { orientation: "h", y: 1.1 },
  };
  Plotly.react(rexEl["rex-spectrum-plot"], traces, layout, plotConfig("retrieval_spectrum"));
}

function renderCornerPlot() {
  const posterior = rexState.payload?.posterior || {};
  if (!posterior.available || !posterior.samples?.length || !posterior.parameters?.length) {
    Plotly.react(rexEl["rex-corner-plot"], [], emptyLayout(posterior.message || "No posterior samples linked to this atmosphere"), plotConfig("retrieval_corner_empty"));
    return;
  }
  const maxParams = Number(rexEl["rex-corner-size"].value || 4);
  const params = posterior.parameters.slice(0, maxParams);
  const sampleRows = posterior.samples.filter((row) => params.every((name) => asNumber(row[name]) !== null));
  const dimensions = params.map((name) => ({
    label: name,
    values: sampleRows.map((row) => asNumber(row[name])),
  }));
  const trace = {
    type: "splom",
    dimensions,
    diagonal: { visible: true },
    showupperhalf: false,
    marker: { size: 3, color: "rgba(73, 97, 107, .42)", line: { width: 0 } },
    hoverinfo: "skip",
  };
  const layout = {
    margin: { l: 44, r: 16, t: 20, b: 44 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    dragmode: "select",
  };
  Plotly.react(rexEl["rex-corner-plot"], [trace], layout, plotConfig("retrieval_corner", { saveImage: true, imageScale: 4 }));
}

function activateRetrievalTab(tab) {
  rexState.selectedTab = tab || "abundances";
  document.querySelectorAll("[data-rex-tab]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.rexTab === rexState.selectedTab);
  });
  for (const key of ["abundances", "parameters", "spectrum", "corner"]) {
    const panel = rexEl[`rex-tab-${key}`];
    if (panel) panel.hidden = key !== rexState.selectedTab;
  }
  setTimeout(() => resizeRetrievalPlots(), 0);
}

function resizeRetrievalPlots() {
  for (const id of ["rex-tp-plot", "rex-contribution-plot", "rex-abundance-plot", "rex-spectrum-plot", "rex-corner-plot"]) {
    const el = rexEl[id];
    if (el && window.Plotly) Plotly.Plots.resize(el);
  }
}

async function clearRetrievalCache() {
  setRetrievalStatus("Clearing cache", "loading");
  try {
    const payload = await fetchJsonUrl(rexAppUrl(`api/retrieval-explorer/cache/clear?${connectionParams().toString()}`), { method: "POST" });
    if (!payload.ok) throw new Error(payload.error || "Could not clear cache");
    await searchRetrievals({ loadFirst: true });
  } catch (error) {
    setRetrievalStatus(error.message || "Could not clear cache", "error");
  }
}

function updateRetrievalUrl(atmosphereId) {
  const url = new URL(window.location.href);
  url.searchParams.set("id", atmosphereId);
  const oid = rexEl["rex-oid"].value.trim();
  if (oid) url.searchParams.set("moca_oid", oid);
  else url.searchParams.delete("moca_oid");
  if (rexEl["rex-include-ignored"].checked) url.searchParams.set("include_ignored", "1");
  else url.searchParams.delete("include_ignored");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function renderTable(container, rows, columns) {
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = '<div class="empty-note">No rows</div>';
    return;
  }
  container.innerHTML = `
    <table>
      <thead><tr>${columns.map(([label]) => `<th>${escapeHtml(label)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((row) => `<tr>${columns.map(([, getter]) => `<td>${escapeHtml(getter(row) ?? "")}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

async function fetchJsonUrl(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok && !payload.error) payload.error = `${response.status} ${response.statusText}`;
  return payload;
}

function plotConfig(filename, extra = {}) {
  return {
    responsive: true,
    displaylogo: false,
    toImageButtonOptions: {
      filename,
      format: "png",
      scale: extra.imageScale || 2,
    },
    ...extra,
  };
}

function emptyLayout(message) {
  return {
    margin: { l: 20, r: 20, t: 20, b: 20 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    xaxis: { visible: false },
    yaxis: { visible: false },
    annotations: [{
      text: message,
      x: 0.5,
      y: 0.5,
      xref: "paper",
      yref: "paper",
      showarrow: false,
      font: { color: "#5f5864", size: 14 },
    }],
  };
}

function setRetrievalStatus(message, kind) {
  rexEl["rex-status"].textContent = message;
  rexEl["rex-status"].className = `status ${kind || ""}`.trim();
}

function setRetrievalLoader(visible) {
  rexEl["rex-tp-loader"].classList.toggle("is-visible", Boolean(visible));
}

function parseInteger(value) {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

function asNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function isFiniteNumber(value) {
  return Number.isFinite(Number(value));
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function formatNumber(value) {
  const number = asNumber(value);
  if (number === null) return value === null || value === undefined ? "" : String(value);
  if (Math.abs(number) >= 1000 || (Math.abs(number) > 0 && Math.abs(number) < 0.01)) return number.toExponential(3);
  return number.toLocaleString(undefined, { maximumSignificantDigits: 4 });
}

function compactJoin(values, separator) {
  return values.filter((value) => value !== null && value !== undefined && String(value).trim()).join(separator);
}

function groupBy(rows, keyFn) {
  const out = new Map();
  rows.forEach((row) => {
    const key = keyFn(row);
    if (!out.has(key)) out.set(key, []);
    out.get(key).push(row);
  });
  return out;
}
