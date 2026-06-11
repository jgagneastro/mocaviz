const sptDefaultNormText = "0.860-1.350, 1.445-1.800, 2.010-2.400";
const sptDefaultBins = 200;
const sptDefaultSpecid = 450;
const sptDefaultFixedRv = "3.1";
const sptDefaultCloudAlpha = "1.7";
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
  { name: "CO2", range: [4.15, 4.35], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "CO", range: [4.4, 4.95], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
];

const sptState = {
  gridOptions: [],
  gridData: [],
  selectedSpecid: null,
  selectedSpectrumLabel: "",
  selectedGrid: "",
  currentIndex: 0,
  comparePayload: null,
  searchTimer: null,
  computeToken: 0,
  quickComputeToken: 0,
  initialGridParam: "",
  initialGridIndexParam: null,
  hasAppliedInitialIndex: false,
  fixedRvValue: sptDefaultFixedRv,
  cloudAlphaValue: sptDefaultCloudAlpha,
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
    "spt-cloud",
    "spt-fixed-param-wrap",
    "spt-fixed-param-label",
    "spt-fixed-param",
    "spt-allred",
    "spt-showfeatures",
    "spt-disable-lowres",
    "spt-plot",
    "spt-chi2-plot",
    "spt-plot-loader",
    "spt-chi2-loader",
    "spt-correction-info",
    "spt-count-summary",
    "spt-standard-meta",
    "spt-open-report",
    "spt-open-standard-report",
    "spt-export-csv",
    "spt-export-tsv",
    "spt-export-fits",
    "spt-export-votable",
    "spt-clear-cache",
    "spt-clear-cache-status",
  ].forEach((id) => {
    sptEl[id] = document.getElementById(id);
  });
}

function readSpectralUrlState() {
  const params = new URLSearchParams(window.location.search);
  const rawSpecid = params.get("specid") || params.get("moca_specid") || String(sptDefaultSpecid);
  sptState.selectedSpecid = parseInteger(rawSpecid);
  sptState.initialGridParam = params.get("grid") || "";
  sptState.initialGridIndexParam = parseInteger(params.get("grid_index"));
  sptEl["spt-bins"].value = params.get("bins") || String(sptDefaultBins);
  sptEl["spt-norm"].value = params.get("norm") || sptDefaultNormText;
  sptEl["spt-deredden"].checked = asSpectralBool(params.get("deredden"));
  sptEl["spt-cloud"].checked = asSpectralBool(params.get("cloud")) || asSpectralBool(params.get("cloud_correction"));
  sptEl["spt-allred"].checked = !asFalse(params.get("allred"));
  sptEl["spt-showfeatures"].checked = !asFalse(params.get("showfeatures"));
  sptEl["spt-disable-lowres"].checked = asSpectralBool(params.get("disable_lowres"));
  if (sptEl["spt-cloud"].checked) sptEl["spt-deredden"].checked = false;
  sptState.fixedRvValue = spectralFixedRvUrlValue(params);
  sptState.cloudAlphaValue = spectralCloudAlphaUrlValue(params);
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
  bindSpectralKeyboardNavigation();
  sptEl["spt-deredden"].addEventListener("change", () => {
    if (sptEl["spt-deredden"].checked) sptEl["spt-cloud"].checked = false;
    updateProcessingModeControls();
    computeSpectralComparison();
  });
  sptEl["spt-cloud"].addEventListener("change", () => {
    if (sptEl["spt-cloud"].checked) sptEl["spt-deredden"].checked = false;
    updateProcessingModeControls();
    computeSpectralComparison();
  });
  sptEl["spt-fixed-param"].addEventListener("input", syncFixedParameterValue);
  for (const id of ["spt-bins", "spt-norm", "spt-fixed-param"]) {
    sptEl[id].addEventListener("change", () => computeSpectralComparison());
  }
  for (const id of ["spt-allred", "spt-showfeatures", "spt-disable-lowres"]) {
    sptEl[id].addEventListener("change", () => {
      updateSpectralUrl();
      renderSpectralTyping();
    });
  }
  sptEl["spt-reset-norm"].addEventListener("click", () => {
    sptEl["spt-norm"].value = sptDefaultNormText;
    computeSpectralComparison();
  });
  sptEl["spt-open-report"].addEventListener("click", () => {
    const oid = sptState.comparePayload?.comparisonMetadata?.moca_oid;
    openMocaReport(oid);
  });
  sptEl["spt-open-standard-report"].addEventListener("click", () => {
    const entry = filteredEntries()[sptState.currentIndex];
    const oid = entry?.moca_oid;
    openMocaReport(oid);
  });
  sptEl["spt-export-csv"].addEventListener("click", () => exportSpectralTyping("csv"));
  sptEl["spt-export-tsv"].addEventListener("click", () => exportSpectralTyping("tsv"));
  sptEl["spt-export-fits"].addEventListener("click", () => exportSpectralTyping("fits"));
  sptEl["spt-export-votable"].addEventListener("click", () => exportSpectralTyping("votable"));
  sptEl["spt-clear-cache"].addEventListener("click", () => clearSpectralCache());
  window.addEventListener("resize", debounce(() => {
    if (!sptEl["spt-comparison-results"].hidden) positionSearchResultsPopup();
    if (sptState.comparePayload) renderSpectralTyping();
  }, 150));
  updateProcessingModeControls();
}

function bindSpectralKeyboardNavigation() {
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    if (isSpectralKeyboardEditableTarget(event.target)) return;
    let moved = false;
    if (event.key === "ArrowLeft") moved = moveStandard(-1);
    else if (event.key === "ArrowRight") moved = moveStandard(1);
    else if (event.key === "ArrowUp") moved = moveGrid(-1);
    else if (event.key === "ArrowDown") moved = moveGrid(1);
    if (moved) event.preventDefault();
  });
}

function isSpectralKeyboardEditableTarget(target) {
  if (!target) return false;
  if (target.isContentEditable) return true;
  const tagName = String(target.tagName || "").toLowerCase();
  return tagName === "input" || tagName === "textarea" || tagName === "select";
}

function updateProcessingModeControls() {
  const deredden = Boolean(sptEl["spt-deredden"]?.checked);
  const cloud = Boolean(sptEl["spt-cloud"]?.checked);
  const active = deredden || cloud;
  if (sptEl["spt-fixed-param-wrap"]) sptEl["spt-fixed-param-wrap"].hidden = !active;
  if (sptEl["spt-fixed-param"]) {
    sptEl["spt-fixed-param"].disabled = !active;
    sptEl["spt-fixed-param"].value = deredden ? sptState.fixedRvValue : (cloud ? sptState.cloudAlphaValue : "");
    sptEl["spt-fixed-param"].placeholder = deredden ? "free R_V" : (cloud ? "free alpha" : "free");
  }
  if (sptEl["spt-fixed-param-label"]) {
    sptEl["spt-fixed-param-label"].textContent = deredden || !cloud ? "Fix R_V value" : "Fix alpha value";
  }
  sptEl["spt-fixed-param-wrap"]?.classList.toggle("disabled-field", !active);
  renderCorrectionInfo();
}

function currentProcessingMode() {
  if (sptEl["spt-deredden"]?.checked) return "rv";
  if (sptEl["spt-cloud"]?.checked) return "alpha";
  return "";
}

function syncFixedParameterValue() {
  const input = sptEl["spt-fixed-param"];
  if (!input) return;
  const value = String(input.value || "").trim();
  const mode = currentProcessingMode();
  if (mode === "rv") sptState.fixedRvValue = value;
  if (mode === "alpha") sptState.cloudAlphaValue = value;
}

function fixedParameterValue() {
  syncFixedParameterValue();
  return String(sptEl["spt-fixed-param"]?.value || "").trim();
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
  sptState.gridData = payload.gridData || [];
  fillGridSelect();
  setSpectralStatus(`${payload.meta?.standard_count || 0} standards loaded`, "");
  setSpectralLoading(false);
}

function fillGridSelect(options = sptState.gridOptions) {
  sptEl["spt-grid-select"].innerHTML = options
    .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label || option.value)}</option>`)
    .join("");
  const values = options.map((option) => String(option.value));
  if (!sptState.hasAppliedInitialIndex && sptState.initialGridParam && values.includes(sptState.initialGridParam)) {
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
  const fixedValue = fixedParameterValue();
  const deredden = sptEl["spt-deredden"].checked;
  const cloud = sptEl["spt-cloud"].checked;
  const token = ++sptState.computeToken;
  const priorityStandardSpecid = canUseQuickStandardPreview() ? currentStandardSpecid() : null;
  const canShowQuickStandard = priorityStandardSpecid !== null;
  let fullCompleted = false;
  setTopLoading(!canShowQuickStandard);
  setChi2Loading(true);
  setSpectralStatus("Computing spectral comparison", "loading");
  updateSpectralUrl();
  const body = {
    specid: sptState.selectedSpecid,
    bins: parseInteger(sptEl["spt-bins"].value) || sptDefaultBins,
    norm: sptEl["spt-norm"].value || sptDefaultNormText,
    deredden: deredden ? "1" : "0",
    cloud_correction: cloud ? "1" : "0",
    cloud_alpha_fixed: cloud && fixedValue ? "1" : "0",
    cloud_alpha: cloud ? (fixedValue || sptDefaultCloudAlpha) : sptDefaultCloudAlpha,
    fix_rv: deredden ? (fixedValue || null) : null,
    priority_standard_specid: priorityStandardSpecid || null,
  };
  if (canShowQuickStandard) {
    const quickToken = ++sptState.quickComputeToken;
    setSpectralStatus("Computing selected standard", "loading");
    postSpectralJson("api/spectral-typing/standard", {
      ...body,
      standard_specid: priorityStandardSpecid,
    }).then((quickPayload) => {
      if (fullCompleted || token !== sptState.computeToken || quickToken !== sptState.quickComputeToken) return;
      if (!quickPayload?.ok || !(quickPayload.entries || []).length) return;
      applyQuickStandardPayload(quickPayload);
      setTopLoading(false);
      setChi2Loading(true);
      setSpectralStatus("Displayed selected standard; computing full χ² grid", "loading");
    }).catch(() => {
      if (token === sptState.computeToken) setTopLoading(true);
    });
  }
  const payload = await postSpectralJson("api/spectral-typing/compare", body);
  fullCompleted = true;
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
  setSpectralTypingExportDisabled(false);
  const timing = payload.meta?.timings?.compare_total;
  const timingText = finiteNumber(timing) ? Number(timing).toFixed(1) : "";
  const cacheText = payload.cache?.hit ? " from cache" : "";
  setSpectralStatus(`Computed ${payload.meta?.standard_count || 0} standards${cacheText}${timingText ? ` in ${timingText}s` : ""}`, "");
}

function applyQuickStandardPayload(payload) {
  const quickEntry = (payload.entries || [])[0];
  if (!quickEntry) return;
  let mergedPayload = payload;
  if (sptState.comparePayload?.entries?.length) {
    let replaced = false;
    const mergedEntries = sptState.comparePayload.entries.map((entry) => {
      if (Number(entry.moca_specid) === Number(quickEntry.moca_specid) && String(entry.grid) === String(quickEntry.grid)) {
        replaced = true;
        return { ...entry, ...quickEntry };
      }
      return entry;
    });
    if (!replaced) mergedEntries.push(quickEntry);
    mergedPayload = {
      ...sptState.comparePayload,
      comparison: payload.comparison || sptState.comparePayload.comparison,
      comparisonMetadata: payload.comparisonMetadata || sptState.comparePayload.comparisonMetadata,
      options: payload.options || sptState.comparePayload.options,
      meta: { ...(sptState.comparePayload.meta || {}), ...(payload.meta || {}), progressive: true },
      entries: mergedEntries,
    };
  }
  sptState.comparePayload = mergedPayload;
  sptState.gridOptions = payload.options || sptState.gridOptions;
  if (!sptState.selectedGrid) sptState.selectedGrid = String(quickEntry.grid || "");
  fillGridSelect(sptState.gridOptions);
  const localIndex = localIndexForEntry(quickEntry);
  if (localIndex >= 0) sptState.currentIndex = localIndex;
  const entries = filteredEntries();
  const entry = entries[sptState.currentIndex] || quickEntry;
  renderSpectrumPlot(mergedPayload, entry);
  updateNavigation(entries.length ? entries : [entry], entry);
  updateLowResControl(mergedPayload);
  updateMetadata(mergedPayload, entry);
  renderCorrectionInfo(mergedPayload);
  updateGridButtons();
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

function gridMetadataEntries(grid = sptState.selectedGrid) {
  return (sptState.gridData || []).filter((entry) => String(entry.grid) === String(grid));
}

function currentStandardSpecid() {
  const entries = filteredEntries();
  const selectedEntry = entries[sptState.currentIndex];
  if (selectedEntry?.moca_specid !== null && selectedEntry?.moca_specid !== undefined) {
    return Number(selectedEntry.moca_specid);
  }
  const rows = gridMetadataEntries();
  if (!rows.length) return null;
  let index = sptState.currentIndex || 0;
  if (!sptState.hasAppliedInitialIndex && sptState.initialGridIndexParam !== null) {
    index = sptState.initialGridIndexParam;
  }
  index = Math.min(Math.max(0, index), rows.length - 1);
  const specid = rows[index]?.moca_specid;
  return specid === null || specid === undefined ? null : Number(specid);
}

function hasExplicitUrlStandardSelection() {
  return Boolean(sptState.initialGridParam) && sptState.initialGridIndexParam !== null;
}

function canUseQuickStandardPreview() {
  return hasExplicitUrlStandardSelection()
    || sptState.hasAppliedInitialIndex
    || Boolean(sptState.comparePayload?.entries?.length);
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
  renderCorrectionInfo(payload);
}

function renderSpectrumPlot(payload, entry) {
  const comparisonRows = payload.comparison || [];
  const standardRows = entry.spectrum || [];
  const dereddenedRows = sptEl["spt-deredden"].checked && entry.spectrum_dered ? entry.spectrum_dered : null;
  const cloudRows = sptEl["spt-cloud"].checked && entry.spectrum_cloud ? entry.spectrum_cloud : null;
  const correctedRows = dereddenedRows || cloudRows;
  const correctionLabel = cloudRows ? "slope-corrected" : "dereddened";
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
      opacity: correctedRows ? 0.3 : 1,
      name: correctedRows ? `${standardName}, original` : standardName,
      legendgroup: "standard-original",
      showlegend: index === 0,
      hovertemplate: "Standard<br>wv=%{x:.4f}<br>flux=%{y:.4f}<extra></extra>",
    });
  }

  if (correctedRows) {
    for (const [index, region] of normRegions.entries()) {
      const segment = segmentRows(correctedRows, region);
      if (!segment.length) continue;
      addSegmentedLineTraces(traces, segment, {
        type: "scatter",
        mode: "lines",
        line: { shape: "hv", width: 4, color: standardColor },
        opacity: 1,
        name: `${standardName}, ${correctionLabel}`,
        legendgroup: "standard-corrected",
        showlegend: index === 0,
        hovertemplate: `${correctionLabel} standard<br>wv=%{x:.4f}<br>flux=%{y:.4f}<extra></extra>`,
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
  const values = [...comparisonRows, ...standardRows, ...(correctedRows || [])].filter((row) => finiteNumber(row.wv) && finiteNumber(row.spn));
  const xVals = values.map((row) => row.wv);
  const yVals = values.map((row) => row.spn);
  const xRange = paddedRange(xVals, 0.015, [0.85, 2.4]);
  const yRange = paddedRange(yVals, 0.05, [0, 1.5]);
  const layout = {
    title,
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { t: 44, r: 120, b: 86, l: 72 },
    xaxis: {
      title: { text: "Wavelength (μm)", font: { size: 22 } },
      title_standoff: 10,
      tickfont: { size: 16 },
      range: xRange,
      ...spectralBoxAxisStyle(),
      zeroline: false,
    },
    yaxis: {
      title: { text: "Normalized flux (<i>F</i><sub>λ</sub>)", font: { size: 22 } },
      tickfont: { size: 16 },
      range: yRange,
      ...spectralBoxAxisStyle(),
      zeroline: false,
    },
    legend: { orientation: "v", x: 1.02, xanchor: "left", y: 1, bgcolor: "rgba(255,255,255,0.75)" },
    shapes: sptEl["spt-showfeatures"].checked ? featureShapes() : [],
    annotations: [
      ...(sptEl["spt-showfeatures"].checked ? featureAnnotations() : []),
      metricAnnotation(entry, payload),
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
    const color = sptGridColors[gridIndex % sptGridColors.length];
    const spline = chi2InterpolatingSpline(rows);
    traces.push({
      x: spline.x,
      y: spline.y,
      type: "scatter",
      mode: "lines",
      name: grid,
      legendgroup: grid,
      line: { color, width: 3 },
      hoverinfo: "skip",
    });
    traces.push({
      x: rows.map((row) => row.spectral_type_number),
      y: rows.map((row) => row.reduced_chi2),
      text: rows.map((row) => row.label || row.spectral_type || ""),
      customdata: rows.map((row) => [row.grid, localIndexForEntry(row)]),
      type: "scatter",
      mode: "markers",
      name: grid,
      legendgroup: grid,
      showlegend: false,
      marker: { size: 9, color },
      hovertemplate: "<b>%{text}</b><br>χ<sup>2</sup>: %{y:.2f}<extra></extra>",
    });
  });
  if (selectedTrace) traces.push(selectedTrace);
  const finiteChi = adjustedEntries.map((entry) => entry.reduced_chi2).filter((value) => finiteNumber(value) && value > 0).sort((a, b) => a - b);
  const yTopCount = Math.max(1, Math.floor(finiteChi.length * 0.75));
  const topChi = finiteChi.slice(0, yTopCount);
  const yRange = topChi.length ? [Math.log10(Math.max(1e-12, topChi[0] * 0.85)), Math.log10(topChi[topChi.length - 1] * 1.6)] : undefined;
  const visibleChiEntries = chiEntriesInsideRange(adjustedEntries, yRange);
  const finiteX = visibleChiEntries.map((entry) => entry.spectral_type_number).filter(finiteNumber);
  const fallbackX = adjustedEntries.map((entry) => entry.spectral_type_number).filter(finiteNumber);
  const xValues = finiteX.length ? finiteX : fallbackX;
  const xMin = xValues.length ? Math.floor(Math.min(...xValues)) : 0;
  const xMax = xValues.length ? Math.ceil(Math.max(...xValues)) : 30;
  const tickStep = Math.max(1, Math.ceil((xMax - xMin) / 20));
  const tickvals = [];
  for (let value = xMin; value <= xMax; value += tickStep) tickvals.push(value);
  const yTickSpec = logTickSpecForRange(yRange);
  const layout = {
    title: `Global goodness of fit for ${comparisonShortName(payload)}`,
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { t: 44, r: 210, b: 86, l: 72 },
    xaxis: {
      title: { text: "Spectral Type", font: { size: 22 } },
      title_standoff: 10,
      tickfont: { size: 16 },
      tickmode: "array",
      tickvals,
      ticktext: tickvals.map(sptLabelFromNumber),
      range: [xMin - 0.5, xMax + 0.5],
      ...spectralBoxAxisStyle(),
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
      ...spectralBoxAxisStyle(),
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

function chi2InterpolatingSpline(rows) {
  const points = rows
    .map((row) => ({
      x: Number(row.spectral_type_number),
      yLog: Math.log10(Number(row.reduced_chi2)),
    }))
    .filter((point) => finiteNumber(point.x) && finiteNumber(point.yLog));
  const filtered = [];
  for (const point of points) {
    const previous = filtered[filtered.length - 1];
    if (previous && previous.x === point.x && previous.yLog === point.yLog) continue;
    filtered.push(point);
  }
  if (filtered.length < 3) {
    return {
      x: filtered.map((point) => point.x),
      y: filtered.map((point) => 10 ** point.yLog),
    };
  }
  const parameter = filtered.map((_, index) => index);
  const xValues = filtered.map((point) => point.x);
  const yLogValues = filtered.map((point) => point.yLog);
  const xSlopes = pchipSlopes(parameter, xValues);
  const yLogSlopes = pchipSlopes(parameter, yLogValues);
  const x = [];
  const y = [];
  for (let index = 0; index < filtered.length - 1; index += 1) {
    const distance = Math.hypot(
      filtered[index + 1].x - filtered[index].x,
      filtered[index + 1].yLog - filtered[index].yLog,
    );
    const samples = Math.max(8, Math.min(32, Math.ceil(distance * 10)));
    for (let sample = 0; sample <= samples; sample += 1) {
      if (index > 0 && sample === 0) continue;
      const t = sample / samples;
      const h = parameter[index + 1] - parameter[index];
      x.push(cubicHermiteValue(xValues[index], xValues[index + 1], xSlopes[index] * h, xSlopes[index + 1] * h, t));
      y.push(10 ** cubicHermiteValue(yLogValues[index], yLogValues[index + 1], yLogSlopes[index] * h, yLogSlopes[index + 1] * h, t));
    }
  }
  return { x, y };
}

function pchipSlopes(x, y) {
  const n = x.length;
  if (n < 2) return new Array(n).fill(0);
  const h = [];
  const delta = [];
  for (let index = 0; index < n - 1; index += 1) {
    h.push(x[index + 1] - x[index]);
    delta.push((y[index + 1] - y[index]) / h[index]);
  }
  if (n === 2) return [delta[0], delta[0]];
  const slopes = new Array(n).fill(0);
  for (let index = 1; index < n - 1; index += 1) {
    if (delta[index - 1] === 0 || delta[index] === 0 || Math.sign(delta[index - 1]) !== Math.sign(delta[index])) {
      slopes[index] = 0;
    } else {
      const w1 = 2 * h[index] + h[index - 1];
      const w2 = h[index] + 2 * h[index - 1];
      slopes[index] = (w1 + w2) / ((w1 / delta[index - 1]) + (w2 / delta[index]));
    }
  }
  slopes[0] = pchipEndpointSlope(h[0], h[1], delta[0], delta[1]);
  slopes[n - 1] = pchipEndpointSlope(h[n - 2], h[n - 3], delta[n - 2], delta[n - 3]);
  return slopes;
}

function pchipEndpointSlope(h0, h1, delta0, delta1) {
  let slope = ((2 * h0 + h1) * delta0 - h0 * delta1) / (h0 + h1);
  if (Math.sign(slope) !== Math.sign(delta0)) slope = 0;
  else if (Math.sign(delta0) !== Math.sign(delta1) && Math.abs(slope) > Math.abs(3 * delta0)) slope = 3 * delta0;
  return slope;
}

function cubicHermiteValue(y0, y1, m0, m1, t) {
  const t2 = t * t;
  const t3 = t2 * t;
  return (
    (2 * t3 - 3 * t2 + 1) * y0
    + (t3 - 2 * t2 + t) * m0
    + (-2 * t3 + 3 * t2) * y1
    + (t3 - t2) * m1
  );
}

function updateNavigation(entries, entry) {
  sptEl["spt-standard-slider"].disabled = entries.length <= 1;
  sptEl["spt-standard-slider"].min = "0";
  sptEl["spt-standard-slider"].max = String(Math.max(0, entries.length - 1));
  sptEl["spt-standard-slider"].value = String(sptState.currentIndex);
  renderStandardMarks(entries);
  sptEl["spt-prev-standard"].disabled = sptState.currentIndex <= 0;
  sptEl["spt-next-standard"].disabled = sptState.currentIndex >= entries.length - 1;
  if (sptEl["spt-count-summary"]) {
    sptEl["spt-count-summary"].textContent = "";
    sptEl["spt-count-summary"].hidden = true;
  }
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
  parts.push(`Standard moca_specid: ${escapeHtml(entry.moca_specid ?? "None")}`);
  if (entry.bibcode) {
    const url = `https://ui.adsabs.harvard.edu/abs/${encodeURIComponent(entry.bibcode)}/abstract`;
    parts.push(`Bibcode for standard: <a href="${url}" target="_blank" rel="noopener">${escapeHtml(entry.bibcode)}</a>`);
  } else {
    parts.push("Bibcode for standard: None");
  }
  sptEl["spt-standard-meta"].innerHTML = parts.map((part) => `<div>${part}</div>`).join("");
  const oid = payload.comparisonMetadata?.moca_oid;
  sptEl["spt-open-report"].disabled = !normalizedMocaOid(oid);
  const standardOid = entry?.moca_oid;
  sptEl["spt-open-standard-report"].disabled = !normalizedMocaOid(standardOid);
}

function renderCorrectionInfo(payload = sptState.comparePayload) {
  const target = sptEl["spt-correction-info"];
  if (!target) return;
  const deredden = Boolean(sptEl["spt-deredden"]?.checked);
  const cloud = Boolean(sptEl["spt-cloud"]?.checked);
  if (!deredden && !cloud) {
    target.hidden = true;
    target.innerHTML = "";
    return;
  }
  target.hidden = false;
  if (deredden) {
    target.innerHTML = `
      <strong>Extinction fit:</strong>
      standards are adjusted with the near-infrared Cardelli, Clayton &amp; Mathis (1989) extinction law,
      <span class="spectral-correction-formula">A(λ) / A(V) = a(x) + b(x) / R<sub>V</sub>, x = 1 / λ</span>.
      The fit solves for A(V) in each normalization region and, when the fixed-value field is blank, also fits R<sub>V</sub>.
      <a href="https://ui.adsabs.harvard.edu/abs/1989ApJ...345..245C/abstract" target="_blank" rel="noopener">Reference</a>.
    `;
    return;
  }
  const lambda0 = finiteNumber(payload?.meta?.cloud_lambda0) ? formatNumber(payload.meta.cloud_lambda0, 2) : "1.25";
  target.innerHTML = `
    <strong>Brown dwarf slope fit:</strong>
    this is an ad-hoc multiplicative slope correction. It often gives behavior similar to the extinction option,
    but τ<sub>0</sub> and α are easier to interpret as cloud-opacity strength and wavelength dependence in brown dwarf atmospheres.
    <span class="spectral-correction-formula">C(λ) = exp{-τ<sub>0</sub>[(λ / λ<sub>0</sub>)<sup>-α</sup> - 1]}, λ<sub>0</sub> = ${escapeHtml(lambda0)} μm</span>.
  `;
}

function fitLabel(name, index) {
  return `${name}<sub>${Number(index) + 1}</sub>`;
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
  if (sptEl["spt-count-summary"]) {
    sptEl["spt-count-summary"].textContent = "";
    sptEl["spt-count-summary"].hidden = true;
  }
  sptEl["spt-standard-meta"].textContent = message;
  renderCorrectionInfo();
  sptEl["spt-open-report"].disabled = true;
  sptEl["spt-open-standard-report"].disabled = true;
  setSpectralTypingExportDisabled(true);
  updateLowResControl(null);
}

const spectralTypingExportColumns = ["row_type", "comparison_specid", "comparison_oid", "standard_specid", "standard_oid", "grid", "spectral_type", "spectral_type_number", "wavelength_um", "normalized_flux", "normalized_flux_unc", "reduced_chi2", "correction", "best_parameters", "designation", "bibcode"];
const spectralTypingNumericExportColumns = new Set(["comparison_specid", "comparison_oid", "standard_specid", "standard_oid", "spectral_type_number", "wavelength_um", "normalized_flux", "normalized_flux_unc", "reduced_chi2"]);

function exportSpectralTyping(format) {
  const rows = spectralTypingExportRows();
  if (!rows.length) return;
  const specid = sptState.selectedSpecid || "unknown";
  MocaExport.saveTable(format, {
    rows,
    columns: spectralTypingExportColumns,
    numericColumns: spectralTypingNumericExportColumns,
    filenameBase: `mocadb_spectral_typing_specid_${specid}`,
    tableName: "mocadb_spectral_typing",
    resourceName: "MOCAdb Spectral Typing",
    extName: "SPTYPING",
  });
}

function spectralTypingExportRows() {
  const payload = sptState.comparePayload;
  if (!payload) return [];
  const comparisonSpecid = payload.meta?.specid || sptState.selectedSpecid || "";
  const comparisonOid = payload.comparisonMetadata?.moca_oid || "";
  const entry = filteredEntries()[sptState.currentIndex] || null;
  const rows = [];
  (payload.comparison || []).forEach((row) => {
    rows.push({
      row_type: "comparison_spectrum",
      comparison_specid: comparisonSpecid,
      comparison_oid: comparisonOid,
      wavelength_um: row.wv,
      normalized_flux: row.spn,
      normalized_flux_unc: row.espn ?? "",
      designation: payload.comparisonMetadata?.designation || "",
    });
  });
  if (entry) {
    const base = {
      comparison_specid: comparisonSpecid,
      comparison_oid: comparisonOid,
      standard_specid: entry.moca_specid ?? "",
      standard_oid: entry.moca_oid ?? "",
      grid: entry.grid || "",
      spectral_type: entry.spectral_type || "",
      spectral_type_number: entry.spectral_type_number ?? "",
      reduced_chi2: entry.reduced_chi2 ?? "",
      best_parameters: spectralTypingBestParameters(entry),
      designation: entry.designation || entry.object_designation || "",
      bibcode: entry.bibcode || "",
    };
    (entry.spectrum || []).forEach((row) => {
      rows.push({ ...base, row_type: "standard_spectrum", correction: "none", wavelength_um: row.wv, normalized_flux: row.spn, normalized_flux_unc: row.espn ?? "" });
    });
    const correctedRows = sptEl["spt-deredden"].checked ? entry.spectrum_dered : (sptEl["spt-cloud"].checked ? entry.spectrum_cloud : null);
    const correction = sptEl["spt-deredden"].checked ? "dereddened" : (sptEl["spt-cloud"].checked ? "bd_slope" : "");
    (correctedRows || []).forEach((row) => {
      rows.push({ ...base, row_type: "standard_spectrum", correction, wavelength_um: row.wv, normalized_flux: row.spn, normalized_flux_unc: row.espn ?? "" });
    });
  }
  (payload.entries || []).forEach((candidate) => {
    rows.push({
      row_type: "chi2_grid",
      comparison_specid: comparisonSpecid,
      comparison_oid: comparisonOid,
      standard_specid: candidate.moca_specid ?? "",
      standard_oid: candidate.moca_oid ?? "",
      grid: candidate.grid || "",
      spectral_type: candidate.spectral_type || "",
      spectral_type_number: candidate.spectral_type_number ?? "",
      reduced_chi2: candidate.reduced_chi2 ?? "",
      best_parameters: spectralTypingBestParameters(candidate),
      designation: candidate.designation || candidate.object_designation || "",
      bibcode: candidate.bibcode || "",
    });
  });
  return rows;
}

function spectralTypingBestParameters(entry) {
  if (sptEl["spt-deredden"]?.checked && Array.isArray(entry.A_V)) {
    const rv = Array.isArray(entry.R_V) ? entry.R_V : [];
    return entry.A_V.map((av, index) => `A(V)_${index + 1}=${formatNumber(av, 4)}${rv[index] !== undefined ? `; R(V)_${index + 1}=${formatNumber(rv[index], 4)}` : ""}`).join("; ");
  }
  if (sptEl["spt-cloud"]?.checked && Array.isArray(entry.cloud_tau0)) {
    const alpha = Array.isArray(entry.cloud_alpha_values) ? entry.cloud_alpha_values : [];
    return entry.cloud_tau0.map((tau0, index) => `tau_${index + 1}=${formatNumber(tau0, 5)}${alpha[index] !== undefined ? `; alpha_${index + 1}=${formatNumber(alpha[index], 5)}` : ""}`).join("; ");
  }
  return "";
}

function setSpectralTypingExportDisabled(disabled) {
  for (const id of ["spt-export-csv", "spt-export-tsv", "spt-export-fits", "spt-export-votable"]) {
    if (sptEl[id]) sptEl[id].disabled = disabled;
  }
}

function moveGrid(delta) {
  const values = currentGridValues();
  const current = values.indexOf(String(sptState.selectedGrid));
  if (current < 0) return false;
  const next = current + delta;
  if (next < 0 || next >= values.length) return false;
  sptState.selectedGrid = values[next];
  sptState.currentIndex = bestIndexForGrid(sptState.selectedGrid);
  sptState.hasAppliedInitialIndex = true;
  sptEl["spt-grid-select"].value = sptState.selectedGrid;
  updateSpectralUrl();
  renderSpectralTyping();
  return true;
}

function moveStandard(delta) {
  const entries = filteredEntries();
  if (!entries.length) return false;
  const next = Math.min(Math.max(0, sptState.currentIndex + delta), entries.length - 1);
  if (next === sptState.currentIndex) return false;
  sptState.currentIndex = next;
  sptState.hasAppliedInitialIndex = true;
  updateSpectralUrl();
  renderSpectralTyping();
  return true;
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

function metricAnnotation(entry, payload = null) {
  const deredden = Boolean(sptEl["spt-deredden"]?.checked);
  const cloud = Boolean(sptEl["spt-cloud"]?.checked);
  const correctionReady = deredden
    ? Array.isArray(entry.spectrum_dered) && entry.spectrum_dered.length > 0
    : (!cloud || (Array.isArray(entry.spectrum_cloud) && entry.spectrum_cloud.length > 0));
  const correctionComputing = Boolean(payload?.meta?.progressive && (deredden || cloud) && !correctionReady);
  const lines = [`χ<sup>2</sup>: ${correctionComputing ? "(computing)" : formatNumber(entry.reduced_chi2, 2)}`];
  if (correctionComputing) {
    lines.push("best_parameters = (computing)");
  } else if (deredden && Array.isArray(entry.A_V)) {
    const showRv = !spectralRvIsFixed();
    entry.A_V.forEach((av, index) => {
      const rv = Array.isArray(entry.R_V) ? entry.R_V[index] : null;
      lines.push(`${fitLabel("A(V)", index)}: ${formatNumber(av, 2)}`);
      if (showRv) lines.push(`${fitLabel("R(V)", index)}: ${formatNumber(rv, 2)}`);
    });
  } else if (cloud && Array.isArray(entry.cloud_tau0)) {
    const showAlpha = !spectralCloudAlphaIsFixed();
    const alphaValues = Array.isArray(entry.cloud_alpha_values) ? entry.cloud_alpha_values : [];
    entry.cloud_tau0.forEach((tau0, index) => {
      lines.push(`${fitLabel("τ", index)}: ${formatNumber(tau0, 3)}`);
      if (showAlpha) lines.push(`${fitLabel("α", index)}: ${formatNumber(alphaValues[index] ?? entry.cloud_alpha, 2)}`);
    });
  }
  return {
    x: 1.02,
    y: (sptEl["spt-deredden"].checked || sptEl["spt-cloud"].checked) ? 0.72 : 0.82,
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

function spectralRvIsFixed() {
  return Boolean(sptEl["spt-deredden"]?.checked && String(sptState.fixedRvValue || "").trim());
}

function spectralCloudAlphaIsFixed() {
  return Boolean(sptEl["spt-cloud"]?.checked && String(sptState.cloudAlphaValue || "").trim());
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

function chiEntriesInsideRange(entries, yRange) {
  const usable = entries.filter((entry) => (
    finiteNumber(entry.spectral_type_number)
    && finiteNumber(entry.reduced_chi2)
    && Number(entry.reduced_chi2) > 0
  ));
  if (!Array.isArray(yRange) || yRange.length !== 2) return usable;
  return usable.filter((entry) => {
    const logChi = Math.log10(Number(entry.reduced_chi2));
    return logChi >= yRange[0] && logChi <= yRange[1];
  });
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
  const fixedValue = fixedParameterValue();
  const params = new URLSearchParams(window.location.search);
  const hasResolvedSelection = sptState.hasAppliedInitialIndex || Boolean(sptState.comparePayload?.entries?.length);
  const shouldPersistGrid = hasResolvedSelection || Boolean(sptState.initialGridParam);
  const shouldPersistIndex = hasResolvedSelection || hasExplicitUrlStandardSelection();
  if (sptState.selectedSpecid !== null) params.set("specid", sptState.selectedSpecid);
  else {
    params.delete("specid");
    params.delete("moca_specid");
    params.delete("grid_index");
  }
  if (sptState.selectedGrid && shouldPersistGrid) params.set("grid", sptState.selectedGrid);
  else params.delete("grid");
  if (sptState.selectedSpecid !== null && sptState.selectedGrid && shouldPersistIndex) params.set("grid_index", String(sptState.currentIndex || 0));
  else params.delete("grid_index");
  params.set("bins", sptEl["spt-bins"].value || String(sptDefaultBins));
  params.set("norm", sptEl["spt-norm"].value || sptDefaultNormText);
  if (sptEl["spt-deredden"].checked) params.set("deredden", "1");
  else {
    params.delete("deredden");
    params.delete("fix_rv");
  }
  if (sptEl["spt-cloud"].checked) params.set("cloud", "1");
  else {
    params.delete("cloud");
    params.delete("cloud_correction");
    params.delete("cloud_alpha");
    params.delete("cloud_alpha_fixed");
    params.delete("cloud_fit_alpha");
  }
  if (sptEl["spt-cloud"].checked) {
    if (fixedValue) {
      params.set("cloud_alpha", fixedValue);
      params.set("cloud_alpha_fixed", "1");
      params.delete("cloud_fit_alpha");
    } else {
      params.set("cloud_alpha", "free");
      params.set("cloud_alpha_fixed", "0");
      params.set("cloud_fit_alpha", "1");
    }
  }
  if (sptEl["spt-deredden"].checked) {
    params.set("fix_rv", fixedValue || "free");
  }
  if (!sptEl["spt-allred"].checked) params.set("allred", "0");
  else params.delete("allred");
  if (!sptEl["spt-showfeatures"].checked) params.set("showfeatures", "0");
  else params.delete("showfeatures");
  if (sptEl["spt-disable-lowres"].checked) params.set("disable_lowres", "1");
  else params.delete("disable_lowres");
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
  setTopLoading(isLoading);
  setChi2Loading(isLoading);
}

function setTopLoading(isLoading) {
  sptEl["spt-plot-loader"]?.classList.toggle("is-visible", Boolean(isLoading));
}

function setChi2Loading(isLoading) {
  sptEl["spt-chi2-loader"]?.classList.toggle("is-visible", Boolean(isLoading));
}

function spectralBoxAxisStyle() {
  return {
    showline: true,
    mirror: true,
    linecolor: "#000000",
    linewidth: 3,
    ticks: "outside",
    ticklen: 8,
    tickwidth: 2,
    tickcolor: "#000000",
  };
}

function parseInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function asSpectralBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

function asFalse(value) {
  return ["0", "false", "no", "off"].includes(String(value || "").toLowerCase());
}

function spectralFixedRvUrlValue(params) {
  if (!params.has("fix_rv")) return sptDefaultFixedRv;
  const raw = String(params.get("fix_rv") || "").trim();
  if (!raw || ["free", "fit", "none", "null"].includes(raw.toLowerCase())) return "";
  return raw;
}

function spectralCloudAlphaUrlValue(params) {
  if (asSpectralBool(params.get("cloud_fit_alpha")) || asSpectralBool(params.get("fit_cloud_alpha"))) return "";
  const rawFixed = params.has("cloud_alpha_fixed") ? String(params.get("cloud_alpha_fixed") || "").trim().toLowerCase() : "";
  if (rawFixed && ["0", "false", "no", "off", "free", "fit"].includes(rawFixed)) return "";
  if (!params.has("cloud_alpha")) return sptDefaultCloudAlpha;
  const raw = String(params.get("cloud_alpha") || "").trim();
  if (!raw || ["free", "fit", "none", "null"].includes(raw.toLowerCase())) return "";
  return raw;
}

function finiteNumber(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" && value.trim() === "") return false;
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

function openMocaReport(oid) {
  const url = mocaReportUrl(oid);
  if (url) window.open(url, "_blank", "noopener");
}

function mocaReportUrl(oid) {
  const normalizedOid = normalizedMocaOid(oid);
  return normalizedOid ? `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(normalizedOid)}%29&search-type=star` : "";
}

function normalizedMocaOid(oid) {
  if (oid === null || oid === undefined) return "";
  const text = String(oid).trim();
  if (!text) return "";
  const number = Number(text);
  if (!Number.isFinite(number) || number <= 0) return "";
  return number.toFixed(0);
}
