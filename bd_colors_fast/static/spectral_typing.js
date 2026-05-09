const sptDefaultNormText = "0.860-1.350, 1.445-1.800, 2.010-2.400";
const sptDefaultBins = 200;
const sptGridColors = ["#8DD3C7", "#FFFFB3", "#BEBADA", "#FB8072", "#80B1D3", "#FDB462", "#B3DE69", "#FCCDE5"];
const sptStandardRed = "#E41A1C";
const sptStandardPalette = ["#E41A1C", "#377EB8", "#4DAF4A", "#984EA3", "#FF7F00", "#FFFF33", "#A65628", "#F781BF"];

const sptFeatureBands = [
  { name: "H2O", range: [0.92, 0.96], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "FeH", range: [0.985, 1.005], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "VO", range: [1.045, 1.08], fill: "rgba(0,139,0,0.10)", text: "rgba(0,139,0,0.65)" },
  { name: "H2O", range: [1.13, 1.17], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "VO", range: [1.17, 1.2], fill: "rgba(0,139,0,0.10)", text: "rgba(0,139,0,0.65)" },
  { name: "FeH", range: [1.19, 1.24], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "Na", range: [1.137, 1.142], fill: "rgba(139,100,0,0.10)", text: "rgba(139,100,0,0.65)", labelY: 0.875 },
  { name: "K", range: [1.169, 1.181], fill: "rgba(139,100,0,0.10)", text: "rgba(139,100,0,0.65)", labelY: 0.835 },
  { name: "K", range: [1.243, 1.253], fill: "rgba(139,100,0,0.10)", text: "rgba(139,100,0,0.65)" },
  { name: "H2O", range: [1.32, 1.35], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "H2O", range: [1.5, 1.62], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "FeH", range: [1.583, 1.62], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "CH4", range: [1.6, 1.68], fill: "rgba(139,69,139,0.10)", text: "rgba(139,69,139,0.65)" },
  { name: "CH4", range: [1.72, 1.78], fill: "rgba(139,69,139,0.10)", text: "rgba(139,69,139,0.65)" },
  { name: "H2O", range: [1.95, 2.11], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "Na", range: [2.195, 2.205], fill: "rgba(139,100,0,0.10)", text: "rgba(139,100,0,0.65)" },
  { name: "CH4", range: [2.2, 2.27], fill: "rgba(139,69,139,0.10)", text: "rgba(139,69,139,0.65)" },
  { name: "CO", range: [2.293, 2.4], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
];

const sptState = {
  gridOptions: [],
  selectedSpecid: null,
  selectedSpectrumLabel: "",
  selectedGrid: "",
  currentIndex: 0,
  comparePayload: null,
  searchTimer: null,
  computeToken: 0,
  initialGridParam: "",
  initialGridIndexParam: null,
  hasAppliedInitialIndex: false,
};

const sptEl = {};

document.addEventListener("DOMContentLoaded", initSpectralTyping);

const sptAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function sptAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), sptAppBaseUrl).toString();
}

async function initSpectralTyping() {
  collectSpectralElements();
  readSpectralUrlState();
  bindSpectralControls();
  await loadSpectralGrid();
  if (sptState.selectedSpecid !== null) {
    await searchSpectra("", { selectedSpecid: sptState.selectedSpecid, quiet: true });
    await computeSpectralComparison();
  } else {
    renderEmptySpectralPlots("Select a comparison spectrum");
  }
}

function collectSpectralElements() {
  [
    "spt-status",
    "spt-comparison-search",
    "spt-comparison-results",
    "spt-selected-spectrum",
    "spt-selected-spectrum-text",
    "spt-clear-spectrum",
    "spt-grid-select",
    "spt-prev-grid",
    "spt-next-grid",
    "spt-standard-slider",
    "spt-standard-marks",
    "spt-prev-standard",
    "spt-next-standard",
    "spt-bins",
    "spt-norm",
    "spt-reset-norm",
    "spt-deredden",
    "spt-fix-rv",
    "spt-allred",
    "spt-showfeatures",
    "spt-disable-lowres",
    "spt-plot",
    "spt-chi2-plot",
    "spt-plot-loader",
    "spt-count-summary",
    "spt-standard-meta",
    "spt-open-report",
    "spt-open-standard-report",
    "spt-clear-cache",
    "spt-clear-cache-status",
  ].forEach((id) => {
    sptEl[id] = document.getElementById(id);
  });
}

function readSpectralUrlState() {
  const params = new URLSearchParams(window.location.search);
  const rawSpecid = params.get("specid") || params.get("moca_specid");
  sptState.selectedSpecid = parseInteger(rawSpecid);
  sptState.initialGridParam = params.get("grid") || "";
  sptState.initialGridIndexParam = parseInteger(params.get("grid_index"));
  sptEl["spt-bins"].value = params.get("bins") || String(sptDefaultBins);
  sptEl["spt-norm"].value = params.get("norm") || sptDefaultNormText;
  sptEl["spt-deredden"].checked = asSpectralBool(params.get("deredden"));
  sptEl["spt-fix-rv"].value = params.get("fix_rv") || "";
  if (sptState.selectedSpecid !== null) {
    sptEl["spt-comparison-search"].value = `specid${sptState.selectedSpecid}`;
  }
}

function bindSpectralControls() {
  sptEl["spt-comparison-search"].addEventListener("input", () => {
    const value = sptEl["spt-comparison-search"].value.trim();
    clearTimeout(sptState.searchTimer);
    sptState.searchTimer = setTimeout(() => searchSpectra(value), 250);
  });
  sptEl["spt-clear-spectrum"].addEventListener("click", clearComparisonSpectrum);
  sptEl["spt-comparison-search"].addEventListener("focus", () => {
    const value = sptEl["spt-comparison-search"].value.trim();
    if (value) searchSpectra(value);
  });
  document.addEventListener("click", (event) => {
    if (!sptEl["spt-comparison-results"].contains(event.target) && event.target !== sptEl["spt-comparison-search"]) {
      sptEl["spt-comparison-results"].hidden = true;
    }
  });

  sptEl["spt-grid-select"].addEventListener("change", () => {
    sptState.selectedGrid = sptEl["spt-grid-select"].value;
    sptState.currentIndex = bestIndexForGrid(sptState.selectedGrid);
    sptState.hasAppliedInitialIndex = true;
    updateSpectralUrl();
    renderSpectralTyping();
  });
  sptEl["spt-prev-grid"].addEventListener("click", () => moveGrid(-1));
  sptEl["spt-next-grid"].addEventListener("click", () => moveGrid(1));
  sptEl["spt-standard-slider"].addEventListener("input", () => {
    sptState.currentIndex = parseInteger(sptEl["spt-standard-slider"].value) || 0;
    sptState.hasAppliedInitialIndex = true;
    updateSpectralUrl();
    renderSpectralTyping();
  });
  sptEl["spt-prev-standard"].addEventListener("click", () => moveStandard(-1));
  sptEl["spt-next-standard"].addEventListener("click", () => moveStandard(1));
  for (const id of ["spt-bins", "spt-norm", "spt-deredden", "spt-fix-rv"]) {
    sptEl[id].addEventListener("change", () => computeSpectralComparison());
  }
  for (const id of ["spt-allred", "spt-showfeatures", "spt-disable-lowres"]) {
    sptEl[id].addEventListener("change", () => renderSpectralTyping());
  }
  sptEl["spt-reset-norm"].addEventListener("click", () => {
    sptEl["spt-norm"].value = sptDefaultNormText;
    computeSpectralComparison();
  });
  sptEl["spt-open-report"].addEventListener("click", () => {
    const oid = sptState.comparePayload?.comparisonMetadata?.moca_oid;
    if (oid !== null && oid !== undefined) window.open(mocaReportUrl(oid), "_blank", "noopener");
  });
  sptEl["spt-open-standard-report"].addEventListener("click", () => {
    const entry = filteredEntries()[sptState.currentIndex];
    const oid = entry?.moca_oid;
    if (oid !== null && oid !== undefined) window.open(mocaReportUrl(oid), "_blank", "noopener");
  });
  sptEl["spt-clear-cache"].addEventListener("click", () => clearSpectralCache());
  window.addEventListener("resize", debounce(() => {
    if (!sptEl["spt-comparison-results"].hidden) positionSearchResultsPopup();
    if (sptState.comparePayload) renderSpectralTyping();
  }, 150));
}

async function loadSpectralGrid() {
  setSpectralLoading(true);
  setSpectralStatus("Loading standards grid", "loading");
  const payload = await fetchSpectralJson("api/spectral-typing/grid");
  if (!payload.ok) {
    setSpectralStatus(payload.error || "Could not load standards grid", "error");
    setSpectralLoading(false);
    return;
  }
  sptState.gridOptions = payload.options || [];
  fillGridSelect();
  setSpectralStatus(`${payload.meta?.standard_count || 0} standards loaded`, "");
  setSpectralLoading(false);
}

function fillGridSelect(options = sptState.gridOptions) {
  sptEl["spt-grid-select"].innerHTML = options
    .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label || option.value)}</option>`)
    .join("");
  const values = options.map((option) => String(option.value));
  if (sptState.initialGridParam && values.includes(sptState.initialGridParam)) {
    sptState.selectedGrid = sptState.initialGridParam;
  } else if (!sptState.selectedGrid || !values.includes(sptState.selectedGrid)) {
    sptState.selectedGrid = values[0] || "";
  }
  if (sptState.selectedGrid) sptEl["spt-grid-select"].value = sptState.selectedGrid;
  updateGridButtons();
}

async function searchSpectra(query, options = {}) {
  const selectedSpecid = options.selectedSpecid ?? null;
  const quiet = Boolean(options.quiet);
  if (!query && selectedSpecid === null) {
    sptEl["spt-comparison-results"].hidden = true;
    return;
  }
  if (!quiet && query.length < 2 && !/^\d+$/.test(query)) {
    sptEl["spt-comparison-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    showSearchResultsPopup();
    return;
  }
  const params = apiParams();
  if (query) params.set("q", query);
  if (selectedSpecid !== null) params.set("specid", selectedSpecid);
  const payload = await fetchJsonUrl(sptAppUrl(`api/spectral-typing/search?${params.toString()}`));
  if (!payload.ok) {
    if (!quiet) {
      sptEl["spt-comparison-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
      showSearchResultsPopup();
    }
    return;
  }
  const results = payload.options || [];
  if (selectedSpecid !== null && results.length) {
    selectSpectrum(results[0], { deferCompute: true });
    return;
  }
  renderSearchResults(results);
}

function renderSearchResults(results) {
  if (!results.length) {
    sptEl["spt-comparison-results"].innerHTML = `<div class="designation-result-note">No spectra found</div>`;
    showSearchResultsPopup();
    return;
  }
  sptEl["spt-comparison-results"].innerHTML = results.map((result, index) => (
    `<button class="designation-result spt-spectrum-result" type="button" data-index="${index}"><span>${escapeHtml(result.label || `specid${result.value}`)}</span></button>`
  )).join("");
  sptEl["spt-comparison-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const result = results[Number(button.dataset.index)];
      selectSpectrum(result);
      sptEl["spt-comparison-results"].hidden = true;
      computeSpectralComparison();
    });
  });
  showSearchResultsPopup();
}

function showSearchResultsPopup() {
  positionSearchResultsPopup();
  sptEl["spt-comparison-results"].hidden = false;
}

function positionSearchResultsPopup() {
  const input = sptEl["spt-comparison-search"];
  const popup = sptEl["spt-comparison-results"];
  if (!input || !popup) return;
  const rect = input.getBoundingClientRect();
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - 320));
  const available = Math.max(280, window.innerWidth - left - 16);
  const width = Math.min(760, available);
  popup.style.left = `${left}px`;
  popup.style.top = `${rect.bottom + 4}px`;
  popup.style.width = `${Math.max(rect.width, width)}px`;
}

function selectSpectrum(option, options = {}) {
  const specid = parseInteger(option.value ?? option.moca_specid);
  if (specid === null) return;
  const changedSpectrum = sptState.selectedSpecid !== specid;
  sptState.selectedSpecid = specid;
  sptState.selectedSpectrumLabel = option.label || `specid${specid}`;
  if (changedSpectrum && !options.deferCompute) {
    sptState.selectedGrid = "";
    sptState.currentIndex = 0;
    sptState.initialGridParam = "";
    sptState.initialGridIndexParam = null;
    sptState.hasAppliedInitialIndex = false;
  }
  sptEl["spt-comparison-search"].value = sptState.selectedSpectrumLabel;
  updateSelectedSpectrumDisplay();
  if (!options.deferCompute) updateSpectralUrl();
}

function clearComparisonSpectrum() {
  sptState.selectedSpecid = null;
  sptState.selectedSpectrumLabel = "";
  sptState.comparePayload = null;
  sptState.selectedGrid = "";
  sptState.currentIndex = 0;
  sptState.initialGridParam = "";
  sptState.initialGridIndexParam = null;
  sptState.hasAppliedInitialIndex = false;
  sptEl["spt-comparison-search"].value = "";
  sptEl["spt-comparison-results"].hidden = true;
  updateSelectedSpectrumDisplay();
  updateSpectralUrl();
  setSpectralStatus("Select a comparison spectrum", "");
  renderEmptySpectralPlots("Select a comparison spectrum");
  sptEl["spt-comparison-search"].focus();
}

function updateSelectedSpectrumDisplay() {
  const hasSpectrum = sptState.selectedSpecid !== null;
  sptEl["spt-selected-spectrum-text"].textContent = hasSpectrum
    ? sptState.selectedSpectrumLabel || `specid${sptState.selectedSpecid}`
    : "No spectrum selected";
  sptEl["spt-clear-spectrum"].hidden = !hasSpectrum;
}

async function computeSpectralComparison() {
  if (sptState.selectedSpecid === null) {
    renderEmptySpectralPlots("Select a comparison spectrum");
    return;
  }
  const token = ++sptState.computeToken;
  setSpectralLoading(true);
  setSpectralStatus("Computing spectral comparison", "loading");
  updateSpectralUrl();
  const body = {
    specid: sptState.selectedSpecid,
    bins: parseInteger(sptEl["spt-bins"].value) || sptDefaultBins,
    norm: sptEl["spt-norm"].value || sptDefaultNormText,
    deredden: sptEl["spt-deredden"].checked ? "1" : "0",
    fix_rv: sptEl["spt-fix-rv"].value || null,
  };
  const payload = await postSpectralJson("api/spectral-typing/compare", body);
  if (token !== sptState.computeToken) return;
  setSpectralLoading(false);
  if (!payload.ok) {
    sptState.comparePayload = null;
    setSpectralStatus(payload.error || "Comparison failed", "error");
    renderEmptySpectralPlots(payload.error || "Comparison failed");
    return;
  }
  sptState.comparePayload = payload;
  sptState.gridOptions = payload.options || sptState.gridOptions;
  chooseGridAndIndexAfterCompute();
  fillGridSelect(sptState.gridOptions);
  updateSpectralUrl();
  renderSpectralTyping();
  const timing = payload.meta?.timings?.compare_total;
  const timingText = finiteNumber(timing) ? Number(timing).toFixed(1) : "";
  const cacheText = payload.cache?.hit ? " from cache" : "";
  setSpectralStatus(`Computed ${payload.meta?.standard_count || 0} standards${cacheText}${timingText ? ` in ${timingText}s` : ""}`, "");
}

function chooseGridAndIndexAfterCompute() {
  const entries = sptState.comparePayload?.entries || [];
  if (!entries.length) {
    sptState.selectedGrid = "";
    sptState.currentIndex = 0;
    return;
  }
  const gridValues = [...new Set(entries.map((entry) => String(entry.grid)).filter(Boolean))];
  let selectedGlobalBest = false;
  if (sptState.initialGridParam && gridValues.includes(sptState.initialGridParam)) {
    sptState.selectedGrid = sptState.initialGridParam;
  } else if (!sptState.hasAppliedInitialIndex || !sptState.selectedGrid || !gridValues.includes(sptState.selectedGrid)) {
    selectedGlobalBest = selectBestGlobalStandard(gridValues);
  }
  if (!selectedGlobalBest && !sptState.hasAppliedInitialIndex && sptState.initialGridIndexParam !== null) {
    const maxIndex = Math.max(0, filteredEntries().length - 1);
    sptState.currentIndex = Math.min(Math.max(0, sptState.initialGridIndexParam), maxIndex);
  } else if (!selectedGlobalBest) {
    sptState.currentIndex = bestIndexForGrid(sptState.selectedGrid);
  }
  sptState.hasAppliedInitialIndex = true;
}

function selectBestGlobalStandard(gridValues) {
  const best = bestGlobalStandardEntry();
  if (!best) {
    sptState.selectedGrid = gridValues[0] || "";
    sptState.currentIndex = bestIndexForGrid(sptState.selectedGrid);
    return false;
  }
  sptState.selectedGrid = String(best.grid || "");
  const index = localIndexForEntry(best);
  sptState.currentIndex = index >= 0 ? index : bestIndexForGrid(sptState.selectedGrid);
  return true;
}

function bestGlobalStandardEntry() {
  const entries = sptState.comparePayload?.entries || [];
  let best = null;
  let bestValue = Infinity;
  entries.forEach((entry) => {
    const value = Number(entry.reduced_chi2);
    if (Number.isFinite(value) && value < bestValue) {
      best = entry;
      bestValue = value;
    }
  });
  return best;
}

function filteredEntries() {
  const payload = sptState.comparePayload;
  if (!payload) return [];
  return (payload.entries || []).filter((entry) => String(entry.grid) === String(sptState.selectedGrid));
}

function bestIndexForGrid(grid) {
  const entries = (sptState.comparePayload?.entries || []).filter((entry) => String(entry.grid) === String(grid));
  if (!entries.length) return 0;
  let bestIndex = 0;
  let bestValue = Infinity;
  entries.forEach((entry, index) => {
    if (finiteNumber(entry.reduced_chi2) && entry.reduced_chi2 < bestValue) {
      bestValue = entry.reduced_chi2;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function renderSpectralTyping() {
  const payload = sptState.comparePayload;
  const entries = filteredEntries();
  if (!payload || !entries.length) {
    renderEmptySpectralPlots("No standards available for this grid");
    return;
  }
  if (sptState.currentIndex >= entries.length) sptState.currentIndex = entries.length - 1;
  if (sptState.currentIndex < 0) sptState.currentIndex = 0;
  const entry = entries[sptState.currentIndex];
  renderSpectrumPlot(payload, entry);
  renderChi2Plot(payload, entry);
  updateNavigation(entries, entry);
  updateLowResControl(payload);
  updateMetadata(payload, entry);
}

function renderSpectrumPlot(payload, entry) {
  const comparisonRows = payload.comparison || [];
  const standardRows = entry.spectrum || [];
  const dereddenedRows = sptEl["spt-deredden"].checked && entry.spectrum_dered ? entry.spectrum_dered : null;
  const normRegions = payload.meta?.norm_regions || parseNormText(sptEl["spt-norm"].value);
  const traces = [];
  const allred = sptEl["spt-allred"].checked;
  const standardColor = allred ? sptStandardRed : sptStandardPalette[Math.abs(sptState.currentIndex) % sptStandardPalette.length];
  const standardName = `Std. ${entry.spectral_type || ""}`.trim();

  for (const [index, region] of normRegions.entries()) {
    const segment = segmentRows(standardRows, region);
    if (!segment.length) continue;
    addSegmentedLineTraces(traces, segment, {
      type: "scatter",
      mode: "lines",
      line: { shape: "hv", width: 4, color: standardColor },
      opacity: dereddenedRows ? 0.3 : 1,
      name: dereddenedRows ? `${standardName}, original` : standardName,
      legendgroup: "standard-original",
      showlegend: index === 0,
      hovertemplate: "Standard<br>wv=%{x:.4f}<br>flux=%{y:.4f}<extra></extra>",
    });
  }

  if (dereddenedRows) {
    for (const [index, region] of normRegions.entries()) {
      const segment = segmentRows(dereddenedRows, region);
      if (!segment.length) continue;
      addSegmentedLineTraces(traces, segment, {
        type: "scatter",
        mode: "lines",
        line: { shape: "hv", width: 4, color: standardColor },
        opacity: 1,
        name: `${standardName}, dereddened`,
        legendgroup: "standard-dereddened",
        showlegend: index === 0,
        hovertemplate: "Dereddened standard<br>wv=%{x:.4f}<br>flux=%{y:.4f}<extra></extra>",
      });
    }
  }

  const lowres = finiteNumber(payload.meta?.average_resolving_power)
    && payload.meta.average_resolving_power < 100
    && !sptEl["spt-disable-lowres"].checked;
  if (lowres) {
    traces.push({
      x: comparisonRows.map((row) => row.wv),
      y: comparisonRows.map((row) => row.spn),
      error_y: {
        type: "data",
        array: comparisonRows.map((row) => finiteNumber(row.espn) ? row.espn : 0),
        color: "rgba(90,90,90,0.85)",
        thickness: 2,
        width: 0,
      },
      type: "scatter",
      mode: "markers",
      marker: { size: 9, color: "white", line: { color: "black", width: 2 } },
      name: "Comparison",
      legendgroup: "comparison",
      hovertemplate: "Comparison<br>wv=%{x:.4f}<br>flux=%{y:.4f}<extra></extra>",
    });
  } else {
    for (const [index, region] of normRegions.entries()) {
      const segment = segmentRows(comparisonRows, region);
      if (!segment.length) continue;
      addSegmentedLineTraces(traces, segment, {
        type: "scatter",
        mode: "lines",
        line: { shape: "hv", width: 4, color: "black" },
        opacity: 0.86,
        name: "Comparison",
        legendgroup: "comparison",
        showlegend: index === 0,
        hovertemplate: "Comparison<br>wv=%{x:.4f}<br>flux=%{y:.4f}<extra></extra>",
      });
    }
  }

  const title = spectrumTitle(payload, entry);
  const values = [...comparisonRows, ...standardRows, ...(dereddenedRows || [])].filter((row) => finiteNumber(row.wv) && finiteNumber(row.spn));
  const xVals = values.map((row) => row.wv);
  const yVals = values.map((row) => row.spn);
  const xRange = paddedRange(xVals, 0.015, [0.85, 2.4]);
  const yRange = paddedRange(yVals, 0.05, [0, 1.5]);
  const layout = {
    title,
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { t: 44, r: 120, b: 66, l: 72 },
    xaxis: {
      title: { text: "Wavelength (μm)", font: { size: 22 } },
      tickfont: { size: 16 },
      range: xRange,
      zeroline: false,
    },
    yaxis: {
      title: { text: "Normalized flux (<i>F</i><sub>λ</sub>)", font: { size: 22 } },
      tickfont: { size: 16 },
      range: yRange,
      zeroline: false,
    },
    legend: { orientation: "v", x: 1.02, xanchor: "left", y: 1, bgcolor: "rgba(255,255,255,0.75)" },
    shapes: sptEl["spt-showfeatures"].checked ? featureShapes() : [],
    annotations: [
      ...(sptEl["spt-showfeatures"].checked ? featureAnnotations() : []),
      metricAnnotation(entry),
    ].filter(Boolean),
  };
  Plotly.react(sptEl["spt-plot"], traces, layout, plotConfig(`sptype_specid_${payload.meta?.specid || "unknown"}_${entry.spectral_type || "std"}`));
}

function renderChi2Plot(payload, selectedEntry) {
  const entries = payload.entries || [];
  const adjustedEntries = adjustedChiEntries(entries);
  const grids = [...new Set(adjustedEntries.map((entry) => String(entry.grid)).filter(Boolean))];
  const traces = [];
  const selectedAdjusted = adjustedEntries.find((entry) => Number(entry.moca_specid) === Number(selectedEntry.moca_specid) && String(entry.grid) === String(selectedEntry.grid));
  const selectedTrace = selectedAdjusted ? {
      x: [selectedAdjusted.spectral_type_number],
      y: [selectedAdjusted.reduced_chi2],
      type: "scatter",
      mode: "markers",
      marker: { symbol: "circle-open", size: 16, line: { width: 2, color: "black" } },
      showlegend: false,
      hoverinfo: "skip",
      customdata: [[selectedEntry.grid, sptState.currentIndex]],
    } : null;
  grids.forEach((grid, gridIndex) => {
    const rows = adjustedEntries
      .filter((entry) => String(entry.grid) === grid && finiteNumber(entry.spectral_type_number) && finiteNumber(entry.reduced_chi2) && entry.reduced_chi2 > 0)
      .sort((a, b) => a.spectral_type_number - b.spectral_type_number);
    traces.push({
      x: rows.map((row) => row.spectral_type_number),
      y: rows.map((row) => row.reduced_chi2),
      text: rows.map((row) => row.label || row.spectral_type || ""),
      customdata: rows.map((row) => [row.grid, localIndexForEntry(row)]),
      type: "scatter",
      mode: "lines+markers",
      name: grid,
      line: { color: sptGridColors[gridIndex % sptGridColors.length], width: 3 },
      marker: { size: 9 },
      hovertemplate: "<b>%{text}</b><br>χ<sup>2</sup>: %{y:.2f}<extra></extra>",
    });
  });
  if (selectedTrace) traces.push(selectedTrace);
  const finiteX = adjustedEntries.map((entry) => entry.spectral_type_number).filter(finiteNumber);
  const finiteChi = adjustedEntries.map((entry) => entry.reduced_chi2).filter((value) => finiteNumber(value) && value > 0).sort((a, b) => a - b);
  const xMin = Math.floor(Math.min(...finiteX));
  const xMax = Math.ceil(Math.max(...finiteX));
  const tickStep = Math.max(1, Math.ceil((xMax - xMin) / 20));
  const tickvals = [];
  for (let value = xMin; value <= xMax; value += tickStep) tickvals.push(value);
  const yTopCount = Math.max(1, Math.floor(finiteChi.length * 0.75));
  const topChi = finiteChi.slice(0, yTopCount);
  const yRange = topChi.length ? [Math.log10(Math.max(1e-12, topChi[0] * 0.85)), Math.log10(topChi[topChi.length - 1] * 1.6)] : undefined;
  const yTickSpec = logTickSpecForRange(yRange);
  const layout = {
    title: `Global goodness of fit for ${comparisonShortName(payload)}`,
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { t: 44, r: 210, b: 66, l: 72 },
    xaxis: {
      title: { text: "Spectral Type", font: { size: 22 } },
      title_standoff: 8,
      tickfont: { size: 16 },
      tickmode: "array",
      tickvals,
      ticktext: tickvals.map(sptLabelFromNumber),
      zeroline: false,
    },
    yaxis: {
      title: { text: "χ²", font: { size: 22 }, standoff: 8 },
      tickfont: { size: 16 },
      type: "log",
      range: yRange,
      ...(yTickSpec.tickvals.length ? {
        tickmode: "array",
        tickvals: yTickSpec.tickvals,
        ticktext: yTickSpec.ticktext,
      } : {}),
      zeroline: false,
    },
    legend: {
      orientation: "v",
      x: 1.02,
      xanchor: "left",
      y: 1,
      yanchor: "top",
      font: { size: 11 },
      bgcolor: "rgba(255,255,255,0.86)",
    },
  };
  Plotly.react(sptEl["spt-chi2-plot"], traces, layout, plotConfig(`global_chi2_specid_${payload.meta?.specid || "unknown"}`));
  sptEl["spt-chi2-plot"].on("plotly_click", (event) => {
    const point = event.points?.[0];
    const custom = point?.customdata;
    if (!custom || custom.length < 2) return;
    sptState.selectedGrid = String(custom[0]);
    sptState.currentIndex = Number(custom[1]) || 0;
    sptState.hasAppliedInitialIndex = true;
    sptEl["spt-grid-select"].value = sptState.selectedGrid;
    updateSpectralUrl();
    renderSpectralTyping();
  });
}

function updateNavigation(entries, entry) {
  sptEl["spt-standard-slider"].disabled = entries.length <= 1;
  sptEl["spt-standard-slider"].min = "0";
  sptEl["spt-standard-slider"].max = String(Math.max(0, entries.length - 1));
  sptEl["spt-standard-slider"].value = String(sptState.currentIndex);
  renderStandardMarks(entries);
  sptEl["spt-prev-standard"].disabled = sptState.currentIndex <= 0;
  sptEl["spt-next-standard"].disabled = sptState.currentIndex >= entries.length - 1;
  sptEl["spt-count-summary"].textContent = `${entries.length} standards in ${sptState.selectedGrid}; showing ${entry.spectral_type || "standard"} (${sptState.currentIndex + 1} of ${entries.length})`;
  updateGridButtons();
}

function updateLowResControl(payload = sptState.comparePayload) {
  const checkbox = sptEl["spt-disable-lowres"];
  if (!checkbox) return;
  const averageResolvingPower = Number(payload?.meta?.average_resolving_power);
  const canUseLowResMode = Number.isFinite(averageResolvingPower) && averageResolvingPower < 100;
  checkbox.disabled = !canUseLowResMode;
  checkbox.closest(".checkline")?.classList.toggle("is-disabled", !canUseLowResMode);
  checkbox.closest(".checkline")?.setAttribute(
    "title",
    canUseLowResMode
      ? `Low-resolution display mode is active for this spectrum (average R ${averageResolvingPower.toFixed(0)}).`
      : "This spectrum is not low-resolution enough for low-resolution display mode."
  );
  if (!canUseLowResMode) checkbox.checked = false;
}

function renderStandardMarks(entries) {
  const target = sptEl["spt-standard-marks"];
  if (!target) return;
  if (!entries.length) {
    target.innerHTML = "";
    return;
  }
  const indexes = new Set([0, entries.length - 1]);
  const desiredMarks = entries.length <= 8 ? entries.length : 7;
  const denominator = Math.max(1, desiredMarks - 1);
  for (let i = 0; i < desiredMarks; i += 1) {
    indexes.add(Math.round((i * (entries.length - 1)) / denominator));
  }
  const maxIndex = Math.max(1, entries.length - 1);
  const marks = [...indexes].sort((a, b) => a - b).map((index) => {
    const entry = entries[index];
    const label = entry?.spectral_type || sptLabelFromNumber(entry?.spectral_type_number ?? index);
    const position = (100 * index) / maxIndex;
    return `<span class="standard-mark" style="--pos:${position}%"><span>${escapeHtml(label)}</span></span>`;
  });
  const currentEntry = entries[sptState.currentIndex];
  const currentPosition = (100 * sptState.currentIndex) / maxIndex;
  const currentLabel = currentEntry?.spectral_type || sptLabelFromNumber(currentEntry?.spectral_type_number ?? sptState.currentIndex);
  marks.push(`<span class="standard-mark-current" style="--pos:${currentPosition}%"><span>${escapeHtml(currentLabel)}</span></span>`);
  target.innerHTML = marks.join("");
}

function updateGridButtons() {
  const values = currentGridValues();
  const index = values.indexOf(String(sptState.selectedGrid));
  sptEl["spt-prev-grid"].disabled = index <= 0;
  sptEl["spt-next-grid"].disabled = index < 0 || index >= values.length - 1;
}

function updateMetadata(payload, entry) {
  const parts = [];
  parts.push(`<strong>${escapeHtml(entry.spectral_type || "Standard")} standard</strong>`);
  parts.push(`Standard: ${escapeHtml(entry.object_designation || entry.designation || "None")}`);
  parts.push(`Comments: ${escapeHtml(entry.comments || "None")}`);
  parts.push(`χ<sup>2</sup>: ${formatNumber(entry.reduced_chi2, 2)}`);
  if (sptEl["spt-deredden"].checked && Array.isArray(entry.A_V)) {
    entry.A_V.forEach((av, index) => {
      const rv = Array.isArray(entry.R_V) ? entry.R_V[index] : null;
      parts.push(`A(V)${index + 1}: ${formatNumber(av, 2)}; R(V)${index + 1}: ${formatNumber(rv, 2)}`);
    });
  }
  if (entry.bibcode) {
    const url = `https://ui.adsabs.harvard.edu/abs/${encodeURIComponent(entry.bibcode)}/abstract`;
    parts.push(`Bibcode: <a href="${url}" target="_blank" rel="noopener">${escapeHtml(entry.bibcode)}</a>`);
  } else {
    parts.push("Bibcode: None");
  }
  sptEl["spt-standard-meta"].innerHTML = parts.map((part) => `<div>${part}</div>`).join("");
  const oid = payload.comparisonMetadata?.moca_oid;
  sptEl["spt-open-report"].disabled = oid === null || oid === undefined;
  const standardOid = entry?.moca_oid;
  sptEl["spt-open-standard-report"].disabled = standardOid === null || standardOid === undefined;
}

function renderEmptySpectralPlots(message) {
  const layout = {
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    xaxis: { visible: false },
    yaxis: { visible: false },
    annotations: [{
      text: message,
      xref: "paper",
      yref: "paper",
      x: 0.5,
      y: 0.5,
      showarrow: false,
      font: { size: 18 },
    }],
  };
  Plotly.react(sptEl["spt-plot"], [], layout, plotConfig("spectral_typing_empty"));
  Plotly.react(sptEl["spt-chi2-plot"], [], { ...layout, annotations: [{ ...layout.annotations[0], text: "No chi2 data" }] }, plotConfig("spectral_typing_chi2_empty"));
  sptEl["spt-count-summary"].textContent = "No comparison loaded";
  sptEl["spt-standard-meta"].textContent = message;
  sptEl["spt-open-report"].disabled = true;
  sptEl["spt-open-standard-report"].disabled = true;
  updateLowResControl(null);
}

function moveGrid(delta) {
  const values = currentGridValues();
  const current = values.indexOf(String(sptState.selectedGrid));
  const next = current + delta;
  if (next < 0 || next >= values.length) return;
  sptState.selectedGrid = values[next];
  sptState.currentIndex = bestIndexForGrid(sptState.selectedGrid);
  sptState.hasAppliedInitialIndex = true;
  sptEl["spt-grid-select"].value = sptState.selectedGrid;
  updateSpectralUrl();
  renderSpectralTyping();
}

function moveStandard(delta) {
  const entries = filteredEntries();
  sptState.currentIndex = Math.min(Math.max(0, sptState.currentIndex + delta), Math.max(0, entries.length - 1));
  sptState.hasAppliedInitialIndex = true;
  updateSpectralUrl();
  renderSpectralTyping();
}

function currentGridValues() {
  if (sptState.comparePayload?.entries?.length) {
    return [...new Set(sptState.comparePayload.entries.map((entry) => String(entry.grid)).filter(Boolean))];
  }
  return sptState.gridOptions.map((option) => String(option.value));
}

function segmentRows(rows, region) {
  const start = Number(region[0]);
  const end = Number(region[1]);
  return (rows || [])
    .filter((row) => finiteNumber(row.wv) && finiteNumber(row.spn) && row.wv >= start && row.wv <= end)
    .sort((a, b) => Number(a.wv) - Number(b.wv));
}

function addSegmentedLineTraces(traces, rows, baseTrace) {
  const chunks = splitRowsByWavelengthGap(rows);
  chunks.forEach((chunk, index) => {
    traces.push({
      ...baseTrace,
      x: chunk.map((row) => row.wv),
      y: chunk.map((row) => row.spn),
      showlegend: Boolean(baseTrace.showlegend) && index === 0,
    });
  });
}

function splitRowsByWavelengthGap(rows) {
  if (!rows.length) return [];
  if (rows.length < 3) return [rows];
  const diffs = [];
  for (let index = 1; index < rows.length; index += 1) {
    const diff = Number(rows[index].wv) - Number(rows[index - 1].wv);
    if (Number.isFinite(diff) && diff > 0) diffs.push(diff);
  }
  if (!diffs.length) return [rows];
  const step = medianNumber(diffs);
  const gapLimit = Math.max(0.015, step * 4.5);
  const chunks = [];
  let current = [rows[0]];
  for (let index = 1; index < rows.length; index += 1) {
    const diff = Number(rows[index].wv) - Number(rows[index - 1].wv);
    if (Number.isFinite(diff) && diff > gapLimit) {
      if (current.length) chunks.push(current);
      current = [];
    }
    current.push(rows[index]);
  }
  if (current.length) chunks.push(current);
  return chunks.filter((chunk) => chunk.length >= 2);
}

function featureShapes() {
  return sptFeatureBands.map((band) => ({
    type: "rect",
    x0: band.range[0],
    x1: band.range[1],
    xref: "x",
    y0: 0,
    y1: 0.94,
    yref: "paper",
    fillcolor: band.fill,
    line: { width: 0 },
    layer: "below",
  }));
}

function featureAnnotations() {
  return sptFeatureBands.map((band, index) => ({
    x: 0.5 * (band.range[0] + band.range[1]),
    xref: "x",
    y: band.labelY ?? 0.98 - 0.035 * (index % 3),
    yref: "paper",
    text: band.name,
    showarrow: false,
    font: { size: 12, color: band.text },
  }));
}

function metricAnnotation(entry) {
  const lines = [`χ<sup>2</sup>: ${formatNumber(entry.reduced_chi2, 2)}`];
  if (sptEl["spt-deredden"].checked && Array.isArray(entry.A_V)) {
    entry.A_V.forEach((av, index) => {
      const rv = Array.isArray(entry.R_V) ? entry.R_V[index] : null;
      lines.push(`A(V)${index + 1}: ${formatNumber(av, 2)}`);
      lines.push(`R(V)${index + 1}: ${formatNumber(rv, 2)}`);
    });
  }
  return {
    x: 1.02,
    y: sptEl["spt-deredden"].checked ? 0.72 : 0.82,
    xref: "paper",
    yref: "paper",
    text: lines.join("<br>"),
    showarrow: false,
    align: "left",
    bgcolor: "white",
    xanchor: "left",
    yanchor: "top",
    font: { size: 13 },
  };
}

function adjustedChiEntries(entries) {
  const out = entries.map((entry) => ({ ...entry }));
  const finite = out.map((entry) => Number(entry.reduced_chi2)).filter((value) => Number.isFinite(value) && value >= 0).sort((a, b) => a - b);
  if (finite.length >= 2) {
    const smallest = finite[0];
    const second = finite[1];
    out.forEach((entry) => {
      const value = Number(entry.reduced_chi2);
      if (Number.isFinite(value) && (value === 0 || value < second / 10)) {
        entry.reduced_chi2 = second / 10;
      }
    });
  }
  return out;
}

function localIndexForEntry(entry) {
  const entries = (sptState.comparePayload?.entries || []).filter((candidate) => String(candidate.grid) === String(entry.grid));
  return entries.findIndex((candidate) => Number(candidate.moca_specid) === Number(entry.moca_specid));
}

function spectrumTitle(payload, entry) {
  const comparison = comparisonShortName(payload);
  const ids = [];
  if (payload.meta?.specid) ids.push(`specid=${payload.meta.specid}`);
  if (payload.comparisonMetadata?.moca_oid) ids.push(`oid=${payload.comparisonMetadata.moca_oid}`);
  const idText = ids.length ? ` (${ids.join("; ")})` : "";
  const standard = `${entry.spectral_type || ""} (${entry.designation || entry.object_designation || ""})`.trim();
  return `${comparison}${idText} vs ${standard}, ${entry.grid} grid`;
}

function comparisonShortName(payload) {
  const meta = payload.comparisonMetadata || {};
  return meta.designation || meta.spectrum_name || `specid${payload.meta?.specid || ""}`;
}

function parseNormText(text) {
  const regions = [];
  String(text || "")
    .replace(/[\[\](){}]/g, " ")
    .split(/[;,]+|\s{2,}/)
    .forEach((chunk) => {
      const parts = chunk.trim().split(/\s*[-:]\s*|\s+/).filter(Boolean);
      if (parts.length < 2) return;
      const start = Number(parts[0]);
      const end = Number(parts[1]);
      if (Number.isFinite(start) && Number.isFinite(end)) regions.push(start <= end ? [start, end] : [end, start]);
    });
  return regions.length ? regions : [[0.86, 1.35], [1.445, 1.8], [2.01, 2.4]];
}

function sptLabelFromNumber(value) {
  const classes = ["O", "B", "A", "F", "G", "K", "M", "L", "T", "Y"];
  const adjusted = Number(value) + 60;
  const classIndex = Math.floor(adjusted / 10);
  const subtype = adjusted % 10;
  if (classIndex >= 0 && classIndex < classes.length) {
    return `${classes[classIndex]}${Number.isInteger(subtype) ? subtype.toFixed(0) : subtype.toFixed(1)}`;
  }
  return String(value);
}

function logTickSpecForRange(logRange) {
  if (!Array.isArray(logRange) || logRange.length < 2) return { tickvals: [], ticktext: [] };
  const minLog = Math.min(Number(logRange[0]), Number(logRange[1]));
  const maxLog = Math.max(Number(logRange[0]), Number(logRange[1]));
  if (!Number.isFinite(minLog) || !Number.isFinite(maxLog)) return { tickvals: [], ticktext: [] };
  const span = maxLog - minLog;
  const mantissas = span <= 1.4 ? [1, 2, 3, 4, 5, 6, 7, 8, 9] : span <= 2.4 ? [1, 2, 3, 5] : [1, 3];
  const minValue = 10 ** minLog;
  const maxValue = 10 ** maxLog;
  const tickvals = [];
  for (let exponent = Math.floor(minLog) - 1; exponent <= Math.ceil(maxLog) + 1; exponent += 1) {
    mantissas.forEach((mantissa) => {
      const value = Number((mantissa * (10 ** exponent)).toPrecision(12));
      if (value >= minValue * 0.999 && value <= maxValue * 1.001) tickvals.push(value);
    });
  }
  const uniqueTicks = [...new Set(tickvals)].sort((a, b) => a - b);
  return {
    tickvals: uniqueTicks,
    ticktext: uniqueTicks.map(formatLogTickValue),
  };
}

function formatLogTickValue(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "";
  if (numeric >= 100 || Number.isInteger(numeric)) return String(Math.round(numeric));
  if (numeric >= 10) return numeric.toFixed(1).replace(/\.0$/, "");
  if (numeric >= 1) return numeric.toFixed(2).replace(/\.?0+$/, "");
  if (numeric >= 0.01) return numeric.toFixed(3).replace(/\.?0+$/, "");
  return numeric.toExponential(1).replace("e", "×10^");
}

function paddedRange(values, fraction, fallback) {
  const finite = values.filter(finiteNumber);
  if (!finite.length) return fallback;
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  if (min === max) return [min - 1, max + 1];
  const pad = fraction * (max - min);
  return [min - pad, max + pad];
}

function plotConfig(filename) {
  return {
    responsive: true,
    displaylogo: false,
    toImageButtonOptions: {
      format: "png",
      height: 700,
      width: 1900,
      scale: 2,
      filename,
    },
  };
}

function updateSpectralUrl() {
  const params = new URLSearchParams(window.location.search);
  if (sptState.selectedSpecid !== null) params.set("specid", sptState.selectedSpecid);
  else {
    params.delete("specid");
    params.delete("moca_specid");
    params.delete("grid_index");
  }
  if (sptState.selectedGrid) params.set("grid", sptState.selectedGrid);
  else params.delete("grid");
  if (sptState.selectedSpecid !== null && sptState.selectedGrid) params.set("grid_index", String(sptState.currentIndex || 0));
  else params.delete("grid_index");
  params.set("bins", sptEl["spt-bins"].value || String(sptDefaultBins));
  params.set("norm", sptEl["spt-norm"].value || sptDefaultNormText);
  if (sptEl["spt-deredden"].checked) params.set("deredden", "1");
  else params.delete("deredden");
  if (sptEl["spt-fix-rv"].value) params.set("fix_rv", sptEl["spt-fix-rv"].value);
  else params.delete("fix_rv");
  const nextUrl = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", nextUrl);
}

async function clearSpectralCache() {
  sptEl["spt-clear-cache"].disabled = true;
  sptEl["spt-clear-cache-status"].textContent = "Clearing...";
  try {
    const payload = await postSpectralJson("api/spectral-typing/cache/clear", {});
    if (!payload.ok) throw new Error(payload.error || "cache clear failed");
    const cleared = payload.cleared || {};
    sptEl["spt-clear-cache-status"].textContent = `Cleared ${Object.values(cleared).reduce((sum, value) => sum + Number(value || 0), 0)} cached items.`;
  } catch (error) {
    sptEl["spt-clear-cache-status"].textContent = error.message;
  } finally {
    sptEl["spt-clear-cache"].disabled = false;
  }
}

function apiParams() {
  const source = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "user", "pwd", "dbase", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  return params;
}

async function fetchSpectralJson(path) {
  const params = apiParams();
  const separator = path.includes("?") ? "&" : "?";
  return fetchJsonUrl(sptAppUrl(`${path}${params.toString() ? `${separator}${params.toString()}` : ""}`));
}

async function postSpectralJson(path, body) {
  const params = apiParams();
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(sptAppUrl(`${path}${params.toString() ? `${separator}${params.toString()}` : ""}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return response.json();
}

async function fetchJsonUrl(url) {
  const response = await fetch(url);
  return response.json();
}

function setSpectralStatus(text, kind) {
  sptEl["spt-status"].textContent = text;
  sptEl["spt-status"].classList.toggle("loading", kind === "loading");
  sptEl["spt-status"].classList.toggle("error", kind === "error");
}

function setSpectralLoading(isLoading) {
  sptEl["spt-plot-loader"].classList.toggle("is-visible", isLoading);
}

function parseInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function asSpectralBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

function finiteNumber(value) {
  return Number.isFinite(Number(value));
}

function formatNumber(value, digits) {
  return finiteNumber(value) ? Number(value).toFixed(digits) : "N/A";
}

function medianNumber(values) {
  const sorted = values.filter(finiteNumber).map(Number).sort((a, b) => a - b);
  if (!sorted.length) return 0;
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : 0.5 * (sorted[mid - 1] + sorted[mid]);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function mocaReportUrl(oid) {
  return `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(oid)}%29&search-type=star`;
}
