const sptDefaultNormText = "0.860-1.350, 1.445-1.800, 2.010-2.400";
const sptDefaultNormPreset = "nir-ground";
const sptNormPresets = [
  { value: "red-visible", label: "Red-optical", norm: "0.520-0.900", bins: 800 },
  { value: sptDefaultNormPreset, label: "NIR ground-based", norm: sptDefaultNormText },
  { value: "nir-space", label: "NIR space-based (JWST NIRSpec Prism, SPHEREx)", norm: "0.800-5.000" },
  { value: "extended-bd-sed", label: "Extended L/T/Y SED (0.4–50 μm)", norm: "0.400-50.000", bins: 50 },
];
const sptNormPresetByValue = new Map(sptNormPresets.map((preset) => [preset.value, preset]));
const sptDefaultBins = 200;
const sptDefaultMinLogWavelengthOverlapPercent = 80;
const sptDefaultSpecid = 450;
const sptDefaultFixedRv = "3.1";
const sptDefaultCloudAlpha = "1.7";
const sptStandardsSourceMoca = "moca";
const sptStandardsSourcePickles = "pickles";
const sptPicklesDefaultGrid = "V solar M/H";
const sptPicklesLuminosityOrder = new Map([["V", 0], ["IV", 1], ["III", 2], ["II", 3], ["I", 4]]);
const sptPicklesMetallicityOrder = new Map([["strong", 0], ["solar", 1], ["weak", 2]]);
const sptGridColors = ["#8DD3C7", "#FFFFB3", "#BEBADA", "#FB8072", "#80B1D3", "#FDB462", "#B3DE69", "#FCCDE5"];
const sptStandardRed = "#E41A1C";
const sptStandardPalette = ["#E41A1C", "#377EB8", "#4DAF4A", "#984EA3", "#FF7F00", "#FFFF33", "#A65628", "#F781BF"];
const sptCompositeColors = ["#377EB8", "#E41A1C", "#4DAF4A", "#984EA3", "#FF7F00", "#A65628", "#F781BF", "#666666"];

const sptFeatureBands = globalThis.mocaBrownDwarfSpectralFeatureBands || [];
const sptSpectralLineOverlays = globalThis.mocaSpectralLineOverlays || {};

const sptState = {
  gridOptions: [],
  gridData: [],
  selectedSpecid: null,
  selectedSpectrumLabel: "",
  selectedSpectra: [],
  combineMode: false,
  selectionDirty: false,
  selectedGrid: "",
  currentIndex: 0,
  comparePayload: null,
  searchTimer: null,
  suppressSearchFocus: false,
  computeToken: 0,
  quickComputeToken: 0,
  initialGridParam: "",
  initialGridIndexParam: null,
  hasAppliedInitialIndex: false,
  fixedRvValue: sptDefaultFixedRv,
  cloudAlphaValue: sptDefaultCloudAlpha,
  authContext: { role: "", hasCredentials: false, privateDb: false },
  managementBusy: false,
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
  const normalized = String(path || "").replace(/^\/+/, "");
  return new URL(normalized, sptAppBaseUrl).toString();
}

function picklesGridSortParts(grid) {
  const text = String(grid || "").trim();
  const [luminosity = "", ...labelParts] = text.split(/\s+/);
  const label = labelParts.join(" ").toLowerCase();
  let metallicity = "solar";
  if (label.startsWith("strong")) metallicity = "strong";
  if (label.startsWith("weak")) metallicity = "weak";
  return {
    luminosityOrder: sptPicklesLuminosityOrder.get(luminosity.toUpperCase()) ?? 99,
    metallicityOrder: sptPicklesMetallicityOrder.get(metallicity) ?? 99,
    text: text.toLowerCase(),
  };
}

function comparePicklesGridNames(a, b) {
  const aa = picklesGridSortParts(a);
  const bb = picklesGridSortParts(b);
  return aa.luminosityOrder - bb.luminosityOrder
    || aa.metallicityOrder - bb.metallicityOrder
    || aa.text.localeCompare(bb.text);
}

function orderedGridOptions(options = []) {
  const out = [...(options || [])];
  if (selectedStandardsSource() !== sptStandardsSourcePickles) return out;
  return out.sort((a, b) => comparePicklesGridNames(a?.value, b?.value));
}

function orderedGridValues(values = []) {
  const out = [...new Set((values || []).map((value) => String(value)).filter(Boolean))];
  if (selectedStandardsSource() !== sptStandardsSourcePickles) return out;
  return out.sort(comparePicklesGridNames);
}

function defaultGridForCurrentStandardsSource(values = []) {
  if (selectedStandardsSource() === sptStandardsSourcePickles && values.includes(sptPicklesDefaultGrid)) {
    return sptPicklesDefaultGrid;
  }
  return values[0] || "";
}

function normRegionsMatch(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
  return a.every((region, index) => (
    Array.isArray(region)
    && Array.isArray(b[index])
    && Math.abs(Number(region[0]) - Number(b[index][0])) < 1e-6
    && Math.abs(Number(region[1]) - Number(b[index][1])) < 1e-6
  ));
}

function normPresetValueForText(text) {
  const regions = parseNormText(text || sptDefaultNormText);
  const match = sptNormPresets.find((preset) => normRegionsMatch(regions, parseNormText(preset.norm)));
  return match?.value || "custom";
}

function syncNormPresetFromText() {
  const select = sptEl["spt-norm-preset"];
  if (!select) return;
  select.value = normPresetValueForText(sptEl["spt-norm"]?.value || sptDefaultNormText);
}

function setNormText(value) {
  sptEl["spt-norm"].value = value || sptDefaultNormText;
  syncNormPresetFromText();
}

function defaultBinsForCurrentNormPreset() {
  const preset = sptNormPresetByValue.get(sptEl["spt-norm-preset"]?.value);
  return preset?.bins || sptDefaultBins;
}

function minimumLogWavelengthOverlapPercent() {
  const value = Number(sptEl["spt-min-overlap"]?.value);
  if (!Number.isFinite(value)) return sptDefaultMinLogWavelengthOverlapPercent;
  return Math.min(100, Math.max(0, value));
}

function syncMinimumOverlapOutput() {
  const output = sptEl["spt-min-overlap-output"];
  if (output) output.value = `${minimumLogWavelengthOverlapPercent().toFixed(0)}%`;
}

async function initSpectralTyping() {
  collectSpectralElements();
  readSpectralUrlState();
  const authPromise = loadSpectralAuthContext();
  bindSpectralControls();
  const gridPromise = loadSpectralGrid();
  await Promise.all([authPromise, gridPromise]);
  updateSpectralManagementVisibility();
  if (selectedComparisonSpecids().length) {
    await Promise.all([
      loadSelectedSpectrumLabels(),
      computeSpectralComparison(),
    ]);
  } else {
    renderEmptySpectralPlots("Select a comparison spectrum");
  }
}

function collectSpectralElements() {
  [
    "spt-status",
    "spt-comparison-search",
    "spt-comparison-search-label",
    "spt-comparison-results",
    "spt-selected-spectrum",
    "spt-selected-spectrum-text",
    "spt-clear-spectrum",
    "spt-start-composite",
    "spt-selected-spectra",
    "spt-composite-actions",
    "spt-compute-composite",
    "spt-cancel-composite",
    "spt-composite-hint",
    "spt-stitch-details",
    "spt-stitch-summary",
    "spt-stitch-content",
    "spt-standards-source",
    "spt-only-field",
    "spt-grid-select",
    "spt-prev-grid",
    "spt-next-grid",
    "spt-standard-slider",
    "spt-standard-marks",
    "spt-prev-standard",
    "spt-next-standard",
    "spt-next-best-chi2",
    "spt-next-worse-chi2",
    "spt-bins",
    "spt-norm-preset",
    "spt-norm",
    "spt-reset-norm",
    "spt-min-overlap",
    "spt-min-overlap-output",
    "spt-deredden",
    "spt-cloud",
    "spt-fixed-param-wrap",
    "spt-fixed-param-label",
    "spt-fixed-param",
    "spt-allred",
    "spt-showfeatures",
    "spt-showoh",
    "spt-showhydrogen",
    "spt-disable-lowres",
    "spt-management-tools",
    "spt-management-proposal",
    "spt-management-rls",
    "spt-management-author",
    "spt-push-spectral-type",
    "spt-management-status",
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
    "spt-export-chi2-csv",
    "spt-clear-cache",
    "spt-clear-cache-status",
  ].forEach((id) => {
    sptEl[id] = document.getElementById(id);
  });
}

function readSpectralUrlState() {
  const params = new URLSearchParams(window.location.search);
  const rawSpecids = params.get("specids") || "";
  const parsedSpecids = uniqueSpectralIntegers(
    rawSpecids.split(",").map((value) => parseInteger(value.trim())).filter((value) => value !== null),
  );
  const rawSpecid = params.get("specid") || params.get("moca_specid") || String(sptDefaultSpecid);
  const fallbackSpecid = parseInteger(rawSpecid);
  const initialSpecids = parsedSpecids.length ? parsedSpecids : (fallbackSpecid !== null ? [fallbackSpecid] : []);
  sptState.selectedSpectra = initialSpecids.map((specid) => ({ specid, label: `specid${specid}`, metadata: { moca_specid: specid } }));
  sptState.selectedSpecid = initialSpecids[0] ?? null;
  sptState.selectedSpectrumLabel = sptState.selectedSpecid !== null ? `specid${sptState.selectedSpecid}` : "";
  sptState.combineMode = parsedSpecids.length > 1 || asSpectralBool(params.get("combine"));
  sptState.initialGridParam = params.get("grid") || "";
  sptState.initialGridIndexParam = parseInteger(params.get("grid_index"));
  setNormText(params.get("norm") || sptDefaultNormText);
  sptEl["spt-bins"].value = params.get("bins") || String(defaultBinsForCurrentNormPreset());
  const minOverlap = params.has("min_overlap")
    ? Number(params.get("min_overlap"))
    : Number.NaN;
  sptEl["spt-min-overlap"].value = String(
    Number.isFinite(minOverlap)
      ? Math.min(100, Math.max(0, minOverlap))
      : sptDefaultMinLogWavelengthOverlapPercent,
  );
  syncMinimumOverlapOutput();
  sptEl["spt-deredden"].checked = asSpectralBool(params.get("deredden"));
  sptEl["spt-cloud"].checked = asSpectralBool(params.get("cloud")) || asSpectralBool(params.get("cloud_correction"));
  sptEl["spt-allred"].checked = !asFalse(params.get("allred"));
  sptEl["spt-showfeatures"].checked = !asFalse(params.get("showfeatures"));
  sptEl["spt-showoh"].checked = asSpectralBool(params.get("showoh") || params.get("oh_lines"));
  sptEl["spt-showhydrogen"].checked = asSpectralBool(params.get("showhydrogen") || params.get("hydrogen_lines"));
  sptEl["spt-disable-lowres"].checked = asSpectralBool(params.get("disable_lowres"));
  sptEl["spt-standards-source"].value = spectralStandardsSourceUrlValue(params);
  sptEl["spt-only-field"].checked = asSpectralBool(params.get("only_field"))
    || asSpectralBool(params.get("only_field_objects"));
  if (sptEl["spt-cloud"].checked) sptEl["spt-deredden"].checked = false;
  sptState.fixedRvValue = spectralFixedRvUrlValue(params);
  sptState.cloudAlphaValue = spectralCloudAlphaUrlValue(params);
  if (sptState.selectedSpecid !== null && !sptState.combineMode) {
    sptEl["spt-comparison-search"].value = `specid${sptState.selectedSpecid}`;
  }
  updateSelectedSpectrumDisplay();
}

function bindSpectralControls() {
  sptEl["spt-comparison-search"].addEventListener("input", () => {
    const value = sptEl["spt-comparison-search"].value.trim();
    clearTimeout(sptState.searchTimer);
    sptState.searchTimer = setTimeout(() => searchSpectra(value), 250);
  });
  sptEl["spt-clear-spectrum"].addEventListener("click", clearComparisonSpectrum);
  sptEl["spt-start-composite"].addEventListener("click", startCompositeSelection);
  sptEl["spt-compute-composite"].addEventListener("click", () => computeSpectralComparison({ force: true }));
  sptEl["spt-cancel-composite"].addEventListener("click", cancelCompositeSelection);
  sptEl["spt-comparison-search"].addEventListener("focus", () => {
    if (sptState.suppressSearchFocus) return;
    const value = sptEl["spt-comparison-search"].value.trim();
    if (value || sptState.combineMode) searchSpectra(value);
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
  sptEl["spt-next-best-chi2"].addEventListener("click", () => moveChi2Rank(-1));
  sptEl["spt-next-worse-chi2"].addEventListener("click", () => moveChi2Rank(1));
  bindSpectralKeyboardNavigation();
  sptEl["spt-standards-source"].addEventListener("change", reloadSpectralStandards);
  sptEl["spt-only-field"].addEventListener("change", reloadSpectralStandards);
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
  sptEl["spt-norm-preset"].addEventListener("change", () => {
    const preset = sptNormPresetByValue.get(sptEl["spt-norm-preset"].value);
    if (!preset) return;
    setNormText(preset.norm);
    if (preset.bins) sptEl["spt-bins"].value = String(preset.bins);
    computeSpectralComparison();
  });
  sptEl["spt-norm"].addEventListener("input", syncNormPresetFromText);
  sptEl["spt-norm"].addEventListener("change", () => {
    syncNormPresetFromText();
    computeSpectralComparison();
  });
  sptEl["spt-min-overlap"].addEventListener("input", syncMinimumOverlapOutput);
  sptEl["spt-min-overlap"].addEventListener("change", () => computeSpectralComparison());
  for (const id of ["spt-bins", "spt-fixed-param"]) {
    sptEl[id].addEventListener("change", () => computeSpectralComparison());
  }
  for (const id of ["spt-allred", "spt-showfeatures", "spt-showoh", "spt-showhydrogen", "spt-disable-lowres"]) {
    sptEl[id].addEventListener("change", () => {
      updateSpectralUrl();
      renderSpectralTyping();
    });
  }
  sptEl["spt-reset-norm"].addEventListener("click", () => {
    setNormText(sptDefaultNormText);
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
  sptEl["spt-export-chi2-csv"].addEventListener("click", exportSpectralChi2Csv);
  sptEl["spt-clear-cache"].addEventListener("click", () => clearSpectralCache());
  sptEl["spt-push-spectral-type"]?.addEventListener("click", () => pushCurrentSpectralType());
  for (const id of ["spt-management-rls", "spt-management-author"]) {
    sptEl[id]?.addEventListener("input", () => updateSpectralManagementControls());
  }
  window.addEventListener("mocaviz-auth-context", (event) => {
    const detail = event.detail || {};
    const role = String(detail.role || "").trim().toLowerCase();
    sptState.authContext = {
      role,
      hasCredentials: Boolean(detail.hasCredentials ?? detail.has_credentials),
      privateDb: Boolean(detail.privateDb ?? detail.private_db ?? role),
      source: detail.source || "",
    };
    updateSpectralManagementVisibility();
  });
  window.addEventListener("resize", debounce(() => {
    if (!sptEl["spt-comparison-results"].hidden) positionSearchResultsPopup();
    if (sptState.comparePayload) renderSpectralTyping();
  }, 150));
  updateProcessingModeControls();
}

async function reloadSpectralStandards() {
  sptState.comparePayload = null;
  sptState.selectedGrid = "";
  sptState.currentIndex = 0;
  sptState.initialGridParam = "";
  sptState.initialGridIndexParam = null;
  sptState.hasAppliedInitialIndex = false;
  updateSpectralUrl();
  await loadSpectralGrid();
  if (selectedComparisonSpecids().length) {
    await computeSpectralComparison();
  } else {
    renderEmptySpectralPlots("Select a comparison spectrum");
  }
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
  const params = new URLSearchParams();
  params.set("standards_source", selectedStandardsSource());
  if (onlyFieldObjectsEnabled()) params.set("only_field", "1");
  const suffix = params.toString();
  const payload = await fetchSpectralJson(`api/spectral-typing/grid${suffix ? `?${suffix}` : ""}`);
  if (!payload.ok) {
    setSpectralStatus(payload.error || "Could not load standards grid", "error");
    setSpectralLoading(false);
    return;
  }
  sptState.gridOptions = orderedGridOptions(payload.options || []);
  sptState.gridData = payload.gridData || [];
  fillGridSelect();
  setSpectralStatus(`${payload.meta?.standard_count || 0} standards loaded`, "");
  setSpectralLoading(false);
}

function fillGridSelect(options = sptState.gridOptions) {
  const orderedOptions = orderedGridOptions(options);
  sptState.gridOptions = orderedOptions;
  sptEl["spt-grid-select"].innerHTML = orderedOptions
    .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label || option.value)}</option>`)
    .join("");
  const values = orderedOptions.map((option) => String(option.value));
  if (!sptState.hasAppliedInitialIndex && sptState.initialGridParam && values.includes(sptState.initialGridParam)) {
    sptState.selectedGrid = sptState.initialGridParam;
  } else if (!sptState.selectedGrid || !values.includes(sptState.selectedGrid)) {
    sptState.selectedGrid = defaultGridForCurrentStandardsSource(values);
  }
  if (sptState.selectedGrid) sptEl["spt-grid-select"].value = sptState.selectedGrid;
  updateGridButtons();
}

async function searchSpectra(query, options = {}) {
  const selectedSpecid = options.selectedSpecid ?? null;
  const quiet = Boolean(options.quiet);
  if (!query && selectedSpecid === null && !sptState.combineMode) {
    sptEl["spt-comparison-results"].hidden = true;
    return;
  }
  if (!quiet && query && query.length < 2 && !/^\d+$/.test(query)) {
    sptEl["spt-comparison-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    showSearchResultsPopup();
    return;
  }
  const params = apiParams();
  if (query) params.set("q", query);
  if (selectedSpecid !== null) params.set("specid", selectedSpecid);
  const selectedSpecids = new Set(selectedComparisonSpecids());
  const requiredOid = sptState.combineMode ? compositeSelectionOid() : null;
  if (sptState.combineMode) {
    if (requiredOid === null) {
      setSpectralStatus("The selected spectrum is not linked to a moca_oid", "error");
      sptEl["spt-comparison-results"].hidden = true;
      return;
    }
    params.set("moca_oid", requiredOid);
    if (selectedSpecids.size) params.set("exclude_specids", [...selectedSpecids].join(","));
  }
  const payload = await fetchJsonUrl(sptAppUrl(`api/spectral-typing/search?${params.toString()}`));
  if (!payload.ok) {
    if (!quiet) {
      sptEl["spt-comparison-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
      showSearchResultsPopup();
    }
    return;
  }
  const results = (payload.options || []).filter((row) => {
    if (!sptState.combineMode) return true;
    const rowSpecid = parseInteger(row.value ?? row.moca_specid);
    const rowOid = parseInteger(row.moca_oid);
    return rowSpecid !== null && !selectedSpecids.has(rowSpecid) && rowOid === requiredOid;
  });
  if (selectedSpecid !== null && results.length) {
    selectSpectrum(results[0], { deferCompute: true });
    return;
  }
  renderSearchResults(results);
}

async function loadSelectedSpectrumLabels() {
  const items = [...sptState.selectedSpectra];
  if (!items.length) return;
  const resolved = [];
  for (const item of items) {
    const params = apiParams();
    params.set("specid", item.specid);
    const payload = await fetchJsonUrl(sptAppUrl(`api/spectral-typing/search?${params.toString()}`));
    const option = payload.ok ? (payload.options || []).find((row) => Number(row.value) === Number(item.specid)) : null;
    resolved.push(option ? spectralSelectionItem(option) : item);
  }
  sptState.selectedSpectra = resolved;
  syncPrimarySpectrumState();
  updateSelectedSpectrumDisplay();
}

function renderSearchResults(results) {
  if (!results.length) {
    const oid = sptState.combineMode ? compositeSelectionOid() : null;
    const message = oid === null ? "No spectra found" : `No other spectra found for oid${oid}`;
    sptEl["spt-comparison-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(message)}</div>`;
    showSearchResultsPopup();
    return;
  }
  sptEl["spt-comparison-results"].innerHTML = results.map((result, index) => (
    `<button class="designation-result spt-spectrum-result" type="button" data-index="${index}"><span>${escapeHtml(result.label || `specid${result.value}`)}</span></button>`
  )).join("");
  sptEl["spt-comparison-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const result = results[Number(button.dataset.index)];
      if (sptState.combineMode) {
        addSpectrumToComposite(result);
      } else {
        selectSpectrum(result);
      }
      sptEl["spt-comparison-results"].hidden = true;
      if (!sptState.combineMode) computeSpectralComparison();
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
  const item = spectralSelectionItem(option);
  sptState.selectedSpectra = [item];
  sptState.combineMode = false;
  sptState.selectionDirty = false;
  syncPrimarySpectrumState();
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
  sptState.selectedSpectra = [];
  sptState.combineMode = false;
  sptState.selectionDirty = false;
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
  updateSpectralManagementControls();
  sptEl["spt-comparison-search"].focus();
}

function updateSelectedSpectrumDisplay() {
  const hasSpectrum = selectedComparisonSpecids().length > 0;
  const compositeMode = Boolean(sptState.combineMode);
  sptEl["spt-selected-spectrum"].hidden = compositeMode;
  sptEl["spt-selected-spectrum-text"].textContent = hasSpectrum
    ? sptState.selectedSpectrumLabel || `specid${sptState.selectedSpecid}`
    : "No spectrum selected";
  sptEl["spt-clear-spectrum"].hidden = !hasSpectrum;
  sptEl["spt-start-composite"].hidden = !hasSpectrum || compositeMode;
  sptEl["spt-start-composite"].disabled = !hasSpectrum || compositeSelectionOid() === null;
  sptEl["spt-selected-spectra"].hidden = !compositeMode;
  sptEl["spt-composite-actions"].hidden = !compositeMode;
  sptEl["spt-composite-hint"].hidden = !compositeMode;
  sptEl["spt-comparison-search-label"].textContent = compositeMode ? "Add comparison spectrum" : "Comparison spectrum";
  sptEl["spt-comparison-search"].placeholder = compositeMode
    ? "Add a specid from the same object"
    : "Type a specid, oid, designation, or instrument";
  if (compositeMode) renderCompositeSpectrumTokens();
  const count = selectedComparisonSpecids().length;
  sptEl["spt-compute-composite"].disabled = count < 2;
  sptEl["spt-composite-hint"].textContent = count < 2
    ? "Add at least one more spectrum from the search box."
    : (sptState.selectionDirty ? "Selection changed. Type the combined spectrum when ready." : `${count} spectra selected.`);
  if (!compositeMode) renderStitchDetails(null);
}

function uniqueSpectralIntegers(values) {
  return [...new Set((values || []).map((value) => parseInteger(value)).filter((value) => value !== null))];
}

function selectedComparisonSpecids() {
  return uniqueSpectralIntegers(sptState.selectedSpectra.map((item) => item.specid));
}

function compositeSelectionOid() {
  for (const item of sptState.selectedSpectra) {
    const oid = parseInteger(item?.metadata?.moca_oid);
    if (oid !== null) return oid;
  }
  return parseInteger(sptState.comparePayload?.comparisonMetadata?.moca_oid);
}

function spectralSelectionItem(option) {
  const specid = parseInteger(option?.value ?? option?.moca_specid);
  const metadata = { ...(option || {}), moca_specid: specid, value: specid };
  return {
    specid,
    label: option?.label || `specid${specid}`,
    metadata,
  };
}

function syncPrimarySpectrumState() {
  const first = sptState.selectedSpectra[0] || null;
  sptState.selectedSpecid = first ? Number(first.specid) : null;
  sptState.selectedSpectrumLabel = first?.label || (first ? `specid${first.specid}` : "");
}

function startCompositeSelection() {
  if (!selectedComparisonSpecids().length) return;
  const oid = compositeSelectionOid();
  if (oid === null) {
    setSpectralStatus("The selected spectrum is not linked to a moca_oid and cannot be combined", "error");
    return;
  }
  sptState.combineMode = true;
  sptState.selectionDirty = false;
  sptEl["spt-comparison-search"].value = "";
  updateSelectedSpectrumDisplay();
  updateSpectralUrl();
  setSpectralStatus(`Showing unselected spectra for oid${oid}`, "");
  sptState.suppressSearchFocus = true;
  sptEl["spt-comparison-search"].focus();
  sptState.suppressSearchFocus = false;
  searchSpectra("");
}

async function cancelCompositeSelection() {
  const first = sptState.selectedSpectra[0] || null;
  sptState.selectedSpectra = first ? [first] : [];
  sptState.combineMode = false;
  sptState.selectionDirty = false;
  sptState.comparePayload = null;
  syncPrimarySpectrumState();
  sptEl["spt-comparison-search"].value = sptState.selectedSpectrumLabel;
  resetSpectralSelectionNavigation();
  updateSelectedSpectrumDisplay();
  updateSpectralUrl();
  if (first) await computeSpectralComparison({ force: true });
  else clearComparisonSpectrum();
}

function addSpectrumToComposite(option) {
  const item = spectralSelectionItem(option);
  if (item.specid === null) return;
  if (selectedComparisonSpecids().includes(item.specid)) {
    setSpectralStatus(`specid${item.specid} is already selected`, "error");
    return;
  }
  if (sptState.selectedSpectra.length >= 8) {
    setSpectralStatus("At most 8 spectra can be combined", "error");
    return;
  }
  const firstOid = parseInteger(sptState.selectedSpectra[0]?.metadata?.moca_oid ?? sptState.comparePayload?.comparisonMetadata?.moca_oid);
  const nextOid = parseInteger(item.metadata?.moca_oid);
  if (firstOid !== null && nextOid !== null && firstOid !== nextOid) {
    setSpectralStatus(`specid${item.specid} belongs to oid${nextOid}; selected spectra belong to oid${firstOid}`, "error");
    return;
  }
  sptState.selectedSpectra.push(item);
  markCompositeSelectionDirty();
  sptEl["spt-comparison-search"].value = "";
  updateSelectedSpectrumDisplay();
  updateSpectralUrl();
  sptEl["spt-comparison-search"].focus();
}

function removeSpectrumFromComposite(specid) {
  sptState.selectedSpectra = sptState.selectedSpectra.filter((item) => Number(item.specid) !== Number(specid));
  syncPrimarySpectrumState();
  markCompositeSelectionDirty();
  updateSelectedSpectrumDisplay();
  updateSpectralUrl();
  searchSpectra(sptEl["spt-comparison-search"].value.trim());
}

function markCompositeSelectionDirty() {
  sptState.selectionDirty = true;
  sptState.comparePayload = null;
  resetSpectralSelectionNavigation();
  renderStitchDetails(null);
  renderEmptySpectralPlots("Type combined spectrum when the selection is ready");
  setSpectralStatus("Composite selection changed", "");
}

function resetSpectralSelectionNavigation() {
  sptState.selectedGrid = "";
  sptState.currentIndex = 0;
  sptState.initialGridParam = "";
  sptState.initialGridIndexParam = null;
  sptState.hasAppliedInitialIndex = false;
}

function renderCompositeSpectrumTokens() {
  const target = sptEl["spt-selected-spectra"];
  if (!target) return;
  if (!sptState.selectedSpectra.length) {
    target.innerHTML = `<div class="plot-hint">No spectra selected</div>`;
    return;
  }
  target.innerHTML = sptState.selectedSpectra.map((item, index) => {
    const metadata = item.metadata || {};
    const oid = parseInteger(metadata.moca_oid);
    const detail = [
      oid !== null ? `oid ${oid}` : "",
      metadata.spectral_type ? `SpT ${metadata.spectral_type}` : "",
      metadata.moca_instid || "",
      metadata.instrument_mode_name || "",
    ].filter(Boolean).join(" · ");
    const title = metadata.designation || metadata.spectrum_name || item.label || `specid${item.specid}`;
    return `
      <div class="spectra-token" data-specid="${item.specid}" title="${escapeHtml(item.label || title)}">
        <span class="spectra-token-swatch" style="--swatch-color: ${sptCompositeColors[index % sptCompositeColors.length]}"></span>
        <span class="spectra-token-body">
          <span class="spectra-token-title">${escapeHtml(title)}</span>
          <span class="spectra-token-meta">specid ${escapeHtml(item.specid)}</span>
          ${detail ? `<span class="spectra-token-meta">${escapeHtml(detail)}</span>` : ""}
        </span>
        <button type="button" aria-label="Remove specid ${item.specid}" data-specid="${item.specid}">x</button>
      </div>
    `;
  }).join("");
  target.querySelectorAll("button[data-specid]").forEach((button) => {
    button.addEventListener("click", () => removeSpectrumFromComposite(Number(button.dataset.specid)));
  });
}

function applyComparisonSourcesToSelection(payload) {
  const bySpecid = new Map((payload?.comparisonSources || []).map((source) => [Number(source.moca_specid), source]));
  sptState.selectedSpectra = sptState.selectedSpectra.map((item) => {
    const source = bySpecid.get(Number(item.specid));
    return source
      ? { ...item, label: source.label || item.label, metadata: { ...(item.metadata || {}), ...source } }
      : item;
  });
  syncPrimarySpectrumState();
  updateSelectedSpectrumDisplay();
}

function renderStitchDetails(payload = sptState.comparePayload) {
  const details = sptEl["spt-stitch-details"];
  const summary = sptEl["spt-stitch-summary"];
  const content = sptEl["spt-stitch-content"];
  if (!details || !summary || !content) return;
  const stitching = payload?.stitching;
  if (!sptState.combineMode || !stitching?.composite) {
    details.hidden = true;
    details.open = false;
    content.innerHTML = "";
    return;
  }
  const components = stitching.components || [];
  const overlaps = stitching.overlaps || [];
  const warnings = stitching.warnings || [];
  details.hidden = false;
  summary.textContent = `${stitching.specids?.length || selectedComparisonSpecids().length} spectra · ${components.length} overlap component${components.length === 1 ? "" : "s"}`;
  const scaleText = (stitching.scales || []).map((row) => `specid${row.moca_specid}: ×${formatNumber(row.scale, 4)}`).join("; ");
  const overlapText = overlaps.map((row) => `${row.specids.join("↔")} (${formatNumber(row.overlap_min_um, 3)}–${formatNumber(row.overlap_max_um, 3)} μm; ${row.matched_points} bins)`).join("; ");
  content.innerHTML = [
    scaleText ? `<div><strong>Scales:</strong> ${escapeHtml(scaleText)}</div>` : "",
    overlapText ? `<div><strong>Overlaps:</strong> ${escapeHtml(overlapText)}</div>` : "",
    ...warnings.map((warning) => `<div class="spt-stitch-warning">${escapeHtml(warning)}</div>`),
  ].filter(Boolean).join("");
}

async function computeSpectralComparison(options = {}) {
  const specids = selectedComparisonSpecids();
  if (!specids.length) {
    renderEmptySpectralPlots("Select a comparison spectrum");
    return;
  }
  if (sptState.combineMode && sptState.selectionDirty && !options.force) {
    renderEmptySpectralPlots("Type combined spectrum when the selection is ready");
    return;
  }
  if (sptState.combineMode && specids.length < 2) {
    renderEmptySpectralPlots("Add at least one more spectrum");
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
  setSpectralTypingExportDisabled(true);
  setSpectralStatus("Computing spectral comparison", "loading");
  updateSpectralUrl();
  const body = {
    ...(specids.length > 1 ? { specids } : { specid: specids[0] }),
    bins: parseInteger(sptEl["spt-bins"].value) || sptDefaultBins,
    norm: sptEl["spt-norm"].value || sptDefaultNormText,
    min_overlap: minimumLogWavelengthOverlapPercent(),
    deredden: deredden ? "1" : "0",
    cloud_correction: cloud ? "1" : "0",
    cloud_alpha_fixed: cloud && fixedValue ? "1" : "0",
    cloud_alpha: cloud ? (fixedValue || sptDefaultCloudAlpha) : sptDefaultCloudAlpha,
    fix_rv: deredden ? (fixedValue || null) : null,
    priority_standard_specid: priorityStandardSpecid || null,
    standards_source: selectedStandardsSource(),
    only_field: onlyFieldObjectsEnabled(),
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
    renderStitchDetails(null);
    return;
  }
  sptState.selectionDirty = false;
  sptState.comparePayload = payload;
  applyComparisonSourcesToSelection(payload);
  sptState.gridOptions = orderedGridOptions(payload.options || sptState.gridOptions);
  chooseGridAndIndexAfterCompute();
  fillGridSelect(sptState.gridOptions);
  updateSpectralUrl();
  renderSpectralTyping();
  renderStitchDetails(payload);
  setSpectralTypingExportDisabled(false);
  const timing = payload.meta?.timings?.compare_total;
  const timingText = finiteNumber(timing) ? Number(timing).toFixed(1) : "";
  const cacheText = payload.cache?.hit ? " from cache" : "";
  const standardCount = Number(payload.meta?.standard_count || 0);
  const eligibleCount = Number(payload.meta?.chi2_standard_count ?? standardCount);
  setSpectralStatus(`Computed ${eligibleCount} χ²-eligible of ${standardCount} standards${cacheText}${timingText ? ` in ${timingText}s` : ""}`, "");
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
      comparisonSources: payload.comparisonSources || sptState.comparePayload.comparisonSources,
      stitching: payload.stitching || sptState.comparePayload.stitching,
      options: payload.options || sptState.comparePayload.options,
      meta: { ...(sptState.comparePayload.meta || {}), ...(payload.meta || {}), progressive: true },
      entries: mergedEntries,
    };
  }
  sptState.comparePayload = mergedPayload;
  sptState.gridOptions = orderedGridOptions(payload.options || sptState.gridOptions);
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
  renderStitchDetails(mergedPayload);
  updateSpectralManagementControls();
  updateGridButtons();
}

function chooseGridAndIndexAfterCompute() {
  const entries = sptState.comparePayload?.entries || [];
  if (!entries.length) {
    sptState.selectedGrid = "";
    sptState.currentIndex = 0;
    return;
  }
  const gridValues = orderedGridValues(entries.map((entry) => entry.grid));
  let selectedGlobalBest = false;
  if (sptState.initialGridParam && gridValues.includes(sptState.initialGridParam)) {
    sptState.selectedGrid = sptState.initialGridParam;
  } else if (
    selectedStandardsSource() === sptStandardsSourcePickles
    && !sptState.hasAppliedInitialIndex
    && !sptState.initialGridParam
    && gridValues.includes(sptPicklesDefaultGrid)
  ) {
    sptState.selectedGrid = sptPicklesDefaultGrid;
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
    sptState.selectedGrid = defaultGridForCurrentStandardsSource(gridValues);
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

function globalChi2Ranking() {
  const entries = sptState.comparePayload?.entries || [];
  const gridOrder = new Map(currentGridValues().map((grid, index) => [String(grid), index]));
  const nextLocalIndex = new Map();
  return entries
    .map((entry, sourceIndex) => {
      const grid = String(entry.grid || "");
      const localIndex = nextLocalIndex.get(grid) || 0;
      nextLocalIndex.set(grid, localIndex + 1);
      return {
        entry,
        sourceIndex,
        grid,
        localIndex,
        reducedChi2: Number(entry.reduced_chi2),
      };
    })
    .filter((candidate) => finiteNumber(candidate.entry.reduced_chi2))
    .sort((a, b) => (
      a.reducedChi2 - b.reducedChi2
      || (gridOrder.get(a.grid) ?? Number.MAX_SAFE_INTEGER) - (gridOrder.get(b.grid) ?? Number.MAX_SAFE_INTEGER)
      || Number(a.entry.spectral_type_number ?? Number.MAX_SAFE_INTEGER) - Number(b.entry.spectral_type_number ?? Number.MAX_SAFE_INTEGER)
      || a.sourceIndex - b.sourceIndex
    ));
}

function currentGlobalChi2Rank(ranking = globalChi2Ranking()) {
  const currentEntry = currentSpectralEntry();
  if (!currentEntry) return -1;
  return ranking.findIndex((candidate) => candidate.entry === currentEntry);
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

function currentSpectralEntry() {
  const entries = filteredEntries();
  if (!entries.length) return null;
  const index = Math.min(Math.max(0, sptState.currentIndex || 0), entries.length - 1);
  return entries[index] || null;
}

async function loadSpectralAuthContext() {
  sptState.authContext = spectralUrlAuthContext();
  try {
    const payload = window.MocaAuthContext?.ready
      ? await window.MocaAuthContext.ready
      : await fetchJsonUrl(sptAppUrl(`api/auth/context${window.location.search || ""}`));
    const role = String(payload?.role || "").trim().toLowerCase();
    sptState.authContext = {
      role,
      hasCredentials: Boolean(payload?.hasCredentials ?? payload?.has_credentials),
      privateDb: Boolean(payload?.privateDb ?? payload?.private_db ?? role),
      source: payload?.source || "",
    };
  } catch (error) {
    sptState.authContext = spectralUrlAuthContext();
  }
}

function spectralUrlAuthContext() {
  const params = new URLSearchParams(window.location.search);
  const user = String(params.get("user") || params.get("username") || "").trim().toLowerCase();
  const password = params.get("pwd") ?? params.get("password");
  const dbName = String(params.get("dbase") || params.get("db") || params.get("database") || "").trim().toLowerCase();
  const privateDb = dbName === "mocadb_private_tables";
  const hasCredentials = user === "management" && password !== null && String(password).length > 0;
  return {
    role: hasCredentials && privateDb ? "management" : "",
    hasCredentials,
    privateDb,
    source: "url",
  };
}

function updateSpectralManagementVisibility() {
  if (!sptEl["spt-management-tools"]) return;
  sptEl["spt-management-tools"].hidden = !hasSpectralManagementCredentials();
  updateSpectralManagementControls();
}

function hasSpectralManagementCredentials() {
  const context = sptState.authContext || spectralUrlAuthContext();
  return context.role === "management" && Boolean(context.hasCredentials) && context.privateDb !== false;
}

function spectralManagementToolsVisible() {
  return Boolean(sptEl["spt-management-tools"] && !sptEl["spt-management-tools"].hidden);
}

function isSpectralMockMode() {
  return asSpectralBool(new URLSearchParams(window.location.search).get("mock"));
}

function currentSpectralTypeProposal() {
  const payload = sptState.comparePayload;
  const entry = currentSpectralEntry();
  if (!payload || !entry) return null;
  const comparisonRows = payload.comparison || [];
  const wavelengths = comparisonRows.map((row) => Number(row.wv)).filter(Number.isFinite);
  const maxWavelength = wavelengths.length ? Math.max(...wavelengths) : null;
  const meta = payload.comparisonMetadata || {};
  const comparisonSpecids = uniqueSpectralIntegers(payload.meta?.specids || selectedComparisonSpecids());
  const composite = comparisonSpecids.length > 1;
  const comparisonSpecid = composite ? null : parseInteger(payload.meta?.specid ?? comparisonSpecids[0] ?? sptState.selectedSpecid);
  const standardSpecid = parseInteger(entry.moca_specid);
  const gridHistoryId = parseInteger(entry.moca_sptgridhid);
  const comparisonOid = parseInteger(meta.moca_oid);
  const spectralTypeNumber = finiteNumber(entry.spectral_type_number) ? Number(entry.spectral_type_number) : null;
  const deredden = Boolean(sptEl["spt-deredden"]?.checked);
  const cloud = Boolean(sptEl["spt-cloud"]?.checked);
  return {
    moca_oid: comparisonOid,
    moca_specid: comparisonSpecid,
    moca_specids: comparisonSpecids,
    moca_instid: composite ? null : (meta.moca_instid || null),
    object_designation: meta.designation || meta.spectrum_name || null,
    comparison_label: comparisonShortName(payload),
    spectral_type: entry.spectral_type || "",
    spectral_type_number: spectralTypeNumber,
    spectral_type_unc: 0.5,
    quality_flag: "B",
    moca_sptgridhid: gridHistoryId,
    spectral_standard_moca_specid: standardSpecid,
    standard_designation: entry.object_designation || entry.designation || null,
    standard_label: entry.label || entry.object_designation || entry.designation || `specid${standardSpecid || ""}`,
    grid: entry.grid || "",
    gravity_class: entry.gravity_class || "",
    reduced_chi2: finiteNumber(entry.reduced_chi2) ? Number(entry.reduced_chi2) : null,
    wavelength_regime: maxWavelength !== null && maxWavelength < 0.8 ? "visible" : "near_infrared",
    comparison_wavelength_max_um: maxWavelength,
    norm_regions: payload.meta?.norm_regions || parseNormText(sptEl["spt-norm"]?.value || sptDefaultNormText),
    norm_regions_text: payload.meta?.norm_regions_text || (sptEl["spt-norm"]?.value || sptDefaultNormText),
    bins_per_micron: parseInteger(sptEl["spt-bins"]?.value) || sptDefaultBins,
    correction: deredden ? "dereddened" : (cloud ? "bd_slope" : "none"),
    deredden,
    cloud_correction: cloud,
    best_parameters: spectralTypingBestParameters(entry),
    stitching_summary: composite ? spectralStitchingComment(payload.stitching) : "",
    rls: managementInputValue("spt-management-rls", "gagne"),
    author: managementInputValue("spt-management-author", "gagne"),
  };
}

function managementInputValue(id, fallback) {
  const value = String(sptEl[id]?.value || "").trim();
  return value || fallback;
}

function spectralManagementUnavailableReason(proposal = currentSpectralTypeProposal()) {
  if (!hasSpectralManagementCredentials()) return "Management credentials are required.";
  if (isSpectralMockMode()) return "Mock comparisons cannot be written to MOCAdb.";
  if (!proposal) return "No comparison displayed.";
  if (!proposal.moca_specid && !(proposal.moca_specids || []).length) return "Comparison moca_specid is missing.";
  if (!proposal.moca_oid) return "Comparison moca_oid is missing.";
  if (!proposal.spectral_standard_moca_specid) return "Standard moca_specid is missing.";
  if (!proposal.moca_sptgridhid) return "Grid history id is missing.";
  if (!proposal.spectral_type) return "Spectral type is missing.";
  if (!finiteNumber(proposal.spectral_type_number)) return "Spectral type number is missing.";
  if (!proposal.rls) return "RLS is required.";
  return "";
}

function updateSpectralManagementControls() {
  if (!spectralManagementToolsVisible()) return;
  const proposal = currentSpectralTypeProposal();
  const reason = spectralManagementUnavailableReason(proposal);
  if (sptEl["spt-management-proposal"]) {
    sptEl["spt-management-proposal"].innerHTML = proposal ? spectralManagementProposalHtml(proposal) : "No comparison displayed";
  }
  if (sptEl["spt-push-spectral-type"]) {
    sptEl["spt-push-spectral-type"].disabled = sptState.managementBusy || Boolean(reason);
    sptEl["spt-push-spectral-type"].title = reason || "";
  }
  if (reason && !sptState.managementBusy && sptEl["spt-management-status"]) {
    setSpectralManagementStatus(reason, "error");
  } else if (!reason && sptEl["spt-management-status"]?.classList.contains("error")) {
    setSpectralManagementStatus("");
  }
}

function spectralManagementProposalHtml(proposal) {
  const chi = finiteNumber(proposal.reduced_chi2) ? formatNumber(proposal.reduced_chi2, 2) : "N/A";
  const standard = proposal.standard_label || proposal.standard_designation || `specid${proposal.spectral_standard_moca_specid}`;
  return [
    `<div><strong>${escapeHtml(proposal.spectral_type)}</strong> for ${escapeHtml(proposal.comparison_label || `specid${proposal.moca_specid}`)}</div>`,
    proposal.moca_specids?.length > 1 ? `<div>Composite inputs: ${escapeHtml(proposal.moca_specids.map((specid) => `specid${specid}`).join(", "))}; stored moca_specid: NULL</div>` : "",
    `<div>Standard: ${escapeHtml(standard)} (${escapeHtml(proposal.spectral_standard_moca_specid)})</div>`,
    `<div>Grid: ${escapeHtml(proposal.grid || "N/A")}; χ²: ${escapeHtml(chi)}</div>`,
  ].filter(Boolean).join("");
}

async function pushCurrentSpectralType() {
  const proposal = currentSpectralTypeProposal();
  const reason = spectralManagementUnavailableReason(proposal);
  if (reason) {
    setSpectralManagementStatus(reason, "error");
    updateSpectralManagementControls();
    return;
  }
  const label = proposal.comparison_label || (proposal.moca_specids?.length > 1
    ? `composite ${proposal.moca_specids.join(",")}`
    : `specid${proposal.moca_specid}`);
  if (!window.confirm(`Push spectral type ${proposal.spectral_type} for ${label} into data_spectral_types?`)) return;

  sptState.managementBusy = true;
  setSpectralManagementStatus("Pushing spectral type...");
  updateSpectralManagementControls();
  try {
    const payload = await postSpectralJson("api/spectral-typing/push-spectral-type", proposal);
    if (!payload.ok) throw new Error(payload.error || "Could not push spectral type");
    const insertedId = payload.inserted_id ? ` id ${payload.inserted_id}` : "";
    setSpectralManagementStatus(`Inserted data_spectral_types${insertedId}.`);
  } catch (error) {
    setSpectralManagementStatus(error.message || String(error), "error");
  } finally {
    sptState.managementBusy = false;
    updateSpectralManagementControls();
  }
}

function setSpectralManagementStatus(text, mode = "") {
  if (!sptEl["spt-management-status"]) return;
  sptEl["spt-management-status"].textContent = text || "";
  sptEl["spt-management-status"].classList.toggle("error", mode === "error");
}

function hasExplicitUrlStandardSelection() {
  return Boolean(sptState.initialGridParam) && sptState.initialGridIndexParam !== null;
}

function canUseQuickStandardPreview() {
  return !sptState.selectionDirty && (hasExplicitUrlStandardSelection()
    || sptState.hasAppliedInitialIndex
    || Boolean(sptState.comparePayload?.entries?.length));
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
  renderStitchDetails(payload);
  updateSpectralManagementControls();
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
  const lowres = finiteNumber(payload.meta?.average_resolving_power)
    && payload.meta.average_resolving_power < 100
    && !sptEl["spt-disable-lowres"].checked;
  const standardLineColor = lowres ? mixHexColorWithWhite(standardColor, 0.4) : standardColor;
  const standardCurveRows = lowres && Array.isArray(entry.spectrum_display) && entry.spectrum_display.length
    ? entry.spectrum_display
    : standardRows;

  for (const [index, region] of normRegions.entries()) {
    const segment = segmentRows(standardCurveRows, region);
    if (!segment.length) continue;
    addSegmentedLineTraces(traces, segment, {
      type: "scatter",
      mode: "lines",
      line: { shape: "hv", width: 4, color: standardLineColor },
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
        line: { shape: "hv", width: 4, color: standardLineColor },
        opacity: 1,
        name: `${standardName}, ${correctionLabel}`,
        legendgroup: "standard-corrected",
        showlegend: index === 0,
        hovertemplate: `${correctionLabel} standard<br>wv=%{x:.4f}<br>flux=%{y:.4f}<extra></extra>`,
      });
    }
  }

  if (lowres) {
    addLowResolutionStandardMarkerTraces(traces, correctedRows || standardRows, normRegions, {
      standardColor,
      standardName,
      correctionLabel: correctedRows ? correctionLabel : "",
    });
    traces.push({
      x: comparisonRows.map((row) => row.wv),
      y: comparisonRows.map((row) => row.spn),
      error_y: {
        type: "data",
        array: comparisonRows.map((row) => finiteNumber(row.espn) ? row.espn : 0),
        color: "rgba(90,90,90,0.38)",
        thickness: 2,
        width: 0,
      },
      type: "scatter",
      mode: "markers",
      marker: { size: 10, color: "white", line: { color: "rgba(72,72,72,0.96)", width: 3.25 } },
      name: "Comparison",
      legendgroup: "comparison",
      customdata: comparisonRows.map((row) => row.source_specids || comparisonIdentifier(payload)),
      hovertemplate: "Comparison<br>wv=%{x:.4f}<br>flux=%{y:.4f}<br>source=%{customdata}<extra></extra>",
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
        includeSourceSpecids: true,
        hovertemplate: "Comparison<br>wv=%{x:.4f}<br>flux=%{y:.4f}<br>source=%{customdata}<extra></extra>",
      });
    }
  }

  const title = spectrumTitle(payload, entry);
  const values = [...comparisonRows, ...standardRows, ...standardCurveRows, ...(correctedRows || [])].filter((row) => finiteNumber(row.wv) && finiteNumber(row.spn));
  const xVals = values.map((row) => row.wv);
  const yVals = values.map((row) => row.spn);
  const xRange = paddedRange(xVals, 0.015, [0.85, 2.4]);
  const yRange = paddedRange(yVals, 0.05, [0, 1.5]);
  const lineOverlayOptions = {
    showOh: sptEl["spt-showoh"].checked,
    showHydrogen: sptEl["spt-showhydrogen"].checked,
  };
  const lineOverlayShapes = typeof sptSpectralLineOverlays.plotlySpectralLineShapes === "function"
    ? sptSpectralLineOverlays.plotlySpectralLineShapes(xRange, lineOverlayOptions)
    : [];
  const lineOverlayAnnotations = typeof sptSpectralLineOverlays.plotlySpectralLineAnnotations === "function"
    ? sptSpectralLineOverlays.plotlySpectralLineAnnotations(xRange, lineOverlayOptions)
    : [];
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
    shapes: [
      ...(sptEl["spt-showfeatures"].checked ? featureShapes(xRange) : []),
      ...lineOverlayShapes,
    ],
    annotations: [
      ...(sptEl["spt-showfeatures"].checked ? featureAnnotations(xRange) : []),
      ...lineOverlayAnnotations,
      metricAnnotation(entry, payload),
    ].filter(Boolean),
  };
  Plotly.react(sptEl["spt-plot"], traces, layout, plotConfig(`sptype_${comparisonIdentifier(payload)}_${entry.spectral_type || "std"}`));
}

function renderChi2Plot(payload, selectedEntry) {
  const entries = payload.entries || [];
  const adjustedEntries = adjustedChiEntries(entries);
  const chi2Entries = adjustedEntries.filter((entry) => (
    finiteNumber(entry.spectral_type_number)
    && finiteNumber(entry.reduced_chi2)
    && Number(entry.reduced_chi2) > 0
  ));
  const grids = orderedGridValues(chi2Entries.map((entry) => entry.grid));
  const traces = [];
  const minOverlap = Number(
    payload.meta?.min_log_wavelength_overlap_percent
      ?? minimumLogWavelengthOverlapPercent(),
  );
  const selectedAdjusted = adjustedEntries.find((entry) => Number(entry.moca_specid) === Number(selectedEntry.moca_specid) && String(entry.grid) === String(selectedEntry.grid));
  const selectedTrace = selectedAdjusted && finiteNumber(selectedAdjusted.reduced_chi2) ? {
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
    const rows = chi2Entries
      .filter((entry) => String(entry.grid) === grid)
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
      legendrank: gridIndex,
      line: { color, width: 3 },
      hoverinfo: "skip",
    });
    traces.push({
      x: rows.map((row) => row.spectral_type_number),
      y: rows.map((row) => row.reduced_chi2),
      text: rows.map((row) => row.label || row.spectral_type || ""),
      type: "scatter",
      mode: "markers",
      name: grid,
      legendgroup: grid,
      showlegend: false,
      marker: { size: 9, color },
      customdata: rows.map((row) => [
        row.grid,
        localIndexForEntry(row),
        row.log_wavelength_overlap_percent,
      ]),
      hovertemplate: "<b>%{text}</b><br>χ<sup>2</sup>: %{y:.2f}<br>mean log(λ) overlap: %{customdata[2]:.1f}%<extra></extra>",
    });
  });
  if (selectedTrace) traces.push(selectedTrace);
  const finiteChi = chi2Entries.map((entry) => entry.reduced_chi2).sort((a, b) => a - b);
  const yTopCount = Math.max(1, Math.floor(finiteChi.length * 0.75));
  const topChi = finiteChi.slice(0, yTopCount);
  const yRange = topChi.length ? [Math.log10(Math.max(1e-12, topChi[0] * 0.85)), Math.log10(topChi[topChi.length - 1] * 1.6)] : undefined;
  const visibleChiEntries = chiEntriesInsideRange(chi2Entries, yRange);
  const finiteX = visibleChiEntries.map((entry) => entry.spectral_type_number).filter(finiteNumber);
  const fallbackX = chi2Entries.map((entry) => entry.spectral_type_number).filter(finiteNumber);
  const xValues = finiteX.length ? finiteX : fallbackX;
  const xMin = xValues.length ? Math.floor(Math.min(...xValues)) : 0;
  const xMax = xValues.length ? Math.ceil(Math.max(...xValues)) : 30;
  const tickStep = Math.max(1, Math.ceil((xMax - xMin) / 20));
  const tickvals = [];
  for (let value = xMin; value <= xMax; value += tickStep) tickvals.push(value);
  const yTickSpec = logTickSpecForRange(yRange);
  const layout = {
    title: `Global goodness of fit for ${comparisonShortName(payload)} (≥${formatNumber(minOverlap, 0)}% mean log(λ) overlap)`,
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
    annotations: finiteChi.length ? [] : [{
      x: 0.5,
      y: 0.5,
      xref: "paper",
      yref: "paper",
      text: `No templates meet the ${formatNumber(minOverlap, 0)}% minimum mean log-wavelength overlap`,
      showarrow: false,
      font: { size: 16 },
    }],
  };
  Plotly.react(sptEl["spt-chi2-plot"], traces, layout, plotConfig(`global_chi2_${comparisonIdentifier(payload)}`));
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
  updateChi2RankButtons();
}

function updateChi2RankButtons() {
  const ranking = globalChi2Ranking();
  const currentRank = currentGlobalChi2Rank(ranking);
  sptEl["spt-next-best-chi2"].disabled = !ranking.length || currentRank === 0;
  sptEl["spt-next-worse-chi2"].disabled = !ranking.length || currentRank === ranking.length - 1;
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
  const comparisonSpecids = uniqueSpectralIntegers(payload.meta?.specids || []);
  if (comparisonSpecids.length > 1) {
    parts.push(`<strong>Composite comparison:</strong> ${escapeHtml(comparisonSpecids.map((specid) => `specid${specid}`).join(", "))}`);
    (payload.stitching?.warnings || []).forEach((warning) => {
      parts.push(`<span class="spt-stitch-warning">${escapeHtml(warning)}</span>`);
    });
  }
  parts.push(`<strong>${escapeHtml(entry.spectral_type || "Standard")} standard</strong>`);
  parts.push(`Standard: ${escapeHtml(entry.object_designation || entry.designation || "None")}`);
  parts.push(`Standard moca_specid: ${escapeHtml(entry.moca_specid ?? "None")}`);
  if (finiteNumber(entry.log_wavelength_overlap_percent)) {
    const overlap = formatNumber(entry.log_wavelength_overlap_percent, 1);
    const minimum = formatNumber(
      payload.meta?.min_log_wavelength_overlap_percent
        ?? minimumLogWavelengthOverlapPercent(),
      0,
    );
    const eligibility = entry.chi2_eligible === false
      ? `; excluded from the χ² map because it is below the ${minimum}% minimum`
      : "; included in the χ² map";
    parts.push(`<strong>Log-wavelength overlap:</strong> ${escapeHtml(overlap)}% of the comparison coverage${escapeHtml(eligibility)}.`);
  }
  const resolutionMatch = entry?.resolution_match;
  if (resolutionMatch?.applied) {
    const standardR = finiteNumber(resolutionMatch.standard_resolving_power)
      ? formatNumber(resolutionMatch.standard_resolving_power, 0)
      : "unknown";
    const comparisonR = finiteNumber(resolutionMatch.comparison_resolving_power)
      ? formatNumber(resolutionMatch.comparison_resolving_power, 0)
      : "wavelength-dependent";
    const mode = resolutionMatch.mode === "gaia_xp_wavelength_dependent_lsf"
      ? "Gaia XP wavelength-dependent LSF"
      : "constant resolving power";
    const kernel = finiteNumber(resolutionMatch.kernel_fwhm_max_nm)
      ? `; maximum smoothing-kernel FWHM ${formatNumber(resolutionMatch.kernel_fwhm_max_nm, 2)} nm`
      : "";
    parts.push(`<strong>Resolution match:</strong> standard <i>R</i> &asymp; ${escapeHtml(standardR)} degraded to comparison <i>R</i> &asymp; ${escapeHtml(comparisonR)} (${escapeHtml(mode)}${escapeHtml(kernel)}).`);
  } else if (resolutionMatch?.reason) {
    parts.push(`<strong>Resolution match:</strong> ${escapeHtml(String(resolutionMatch.reason).replaceAll("_", " "))}.`);
  }
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
      standards are adjusted with the optical and near-infrared branches of the
      Cardelli, Clayton &amp; Mathis (1989) extinction law,
      <span class="spectral-correction-formula">A(λ) / A(V) = a(x) + b(x) / R<sub>V</sub>, x = 1 / λ</span>.
      The fit solves for A(V) in each normalization region and, when the fixed-value field is blank, also fits R<sub>V</sub>.
      The corresponding color excess is reported as E(B-V) = A(V) / R<sub>V</sub>.
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
  updateChi2RankButtons();
  setSpectralTypingExportDisabled(true);
  updateLowResControl(null);
  updateSpectralManagementControls();
}

const spectralTypingExportColumns = ["row_type", "comparison_specid", "comparison_specids", "comparison_oid", "source_specids", "source_count", "standard_specid", "standard_oid", "grid", "spectral_type", "spectral_type_number", "wavelength_um", "normalized_flux", "normalized_flux_unc", "log_wavelength_overlap_percent", "chi2_eligible", "reduced_chi2", "correction", "best_parameters", "designation", "bibcode"];
const spectralTypingNumericExportColumns = new Set(["comparison_specid", "comparison_oid", "source_count", "standard_specid", "standard_oid", "spectral_type_number", "wavelength_um", "normalized_flux", "normalized_flux_unc", "log_wavelength_overlap_percent", "reduced_chi2"]);
const spectralChi2ExportColumns = ["comparison_specid", "comparison_specids", "comparison_oid", "standard_specid", "standard_oid", "grid", "spectral_type", "spectral_type_number", "log_wavelength_overlap_percent", "chi2_eligible", "reduced_chi2", "best_parameters", "designation", "bibcode"];
const spectralChi2NumericExportColumns = new Set(["comparison_specid", "comparison_oid", "standard_specid", "standard_oid", "spectral_type_number", "log_wavelength_overlap_percent", "reduced_chi2"]);

function exportSpectralTyping(format) {
  const rows = spectralTypingExportRows();
  if (!rows.length) return;
  MocaExport.saveTable(format, {
    rows,
    columns: spectralTypingExportColumns,
    numericColumns: spectralTypingNumericExportColumns,
    filenameBase: `mocadb_spectral_typing_${comparisonIdentifier()}`,
    tableName: "mocadb_spectral_typing",
    resourceName: "MOCAdb Spectral Typing",
    extName: "SPTYPING",
  });
}

function exportSpectralChi2Csv() {
  const rows = spectralTypingExportRows().filter((row) => row.row_type === "chi2_grid");
  if (!rows.length) return;
  MocaExport.saveTable("csv", {
    rows,
    columns: spectralChi2ExportColumns,
    numericColumns: spectralChi2NumericExportColumns,
    filenameBase: `mocadb_spectral_typing_chi2_${comparisonIdentifier()}`,
    tableName: "mocadb_spectral_typing_chi2",
    resourceName: "MOCAdb Spectral Typing Chi-Squared Values",
  });
}

function spectralTypingExportRows() {
  const payload = sptState.comparePayload;
  if (!payload) return [];
  const comparisonSpecids = uniqueSpectralIntegers(payload.meta?.specids || selectedComparisonSpecids());
  const comparisonSpecid = comparisonSpecids.length === 1 ? comparisonSpecids[0] : "";
  const comparisonSpecidsText = comparisonSpecids.join(",");
  const comparisonOid = payload.comparisonMetadata?.moca_oid || "";
  const entry = filteredEntries()[sptState.currentIndex] || null;
  const rows = [];
  (payload.comparison || []).forEach((row) => {
    rows.push({
      row_type: "comparison_spectrum",
      comparison_specid: comparisonSpecid,
      comparison_specids: comparisonSpecidsText,
      comparison_oid: comparisonOid,
      source_specids: row.source_specids || comparisonSpecidsText,
      source_count: row.source_count ?? comparisonSpecids.length,
      wavelength_um: row.wv,
      normalized_flux: row.spn,
      normalized_flux_unc: row.espn ?? "",
      designation: payload.comparisonMetadata?.designation || "",
    });
  });
  if (entry) {
    const base = {
      comparison_specid: comparisonSpecid,
      comparison_specids: comparisonSpecidsText,
      comparison_oid: comparisonOid,
      standard_specid: entry.moca_specid ?? "",
      standard_oid: entry.moca_oid ?? "",
      grid: entry.grid || "",
      spectral_type: entry.spectral_type || "",
      spectral_type_number: entry.spectral_type_number ?? "",
      log_wavelength_overlap_percent: entry.log_wavelength_overlap_percent ?? "",
      chi2_eligible: entry.chi2_eligible ?? "",
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
      comparison_specids: comparisonSpecidsText,
      comparison_oid: comparisonOid,
      standard_specid: candidate.moca_specid ?? "",
      standard_oid: candidate.moca_oid ?? "",
      grid: candidate.grid || "",
      spectral_type: candidate.spectral_type || "",
      spectral_type_number: candidate.spectral_type_number ?? "",
      log_wavelength_overlap_percent: candidate.log_wavelength_overlap_percent ?? "",
      chi2_eligible: candidate.chi2_eligible ?? "",
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
    return entry.A_V.map((av, index) => {
      const regionRv = rv[index];
      const colorExcess = spectralColorExcess(av, regionRv);
      return [
        `A(V)_${index + 1}=${formatNumber(av, 4)}`,
        colorExcess === null ? "" : `E(B-V)_${index + 1}=${formatNumber(colorExcess, 4)}`,
        regionRv === undefined ? "" : `R(V)_${index + 1}=${formatNumber(regionRv, 4)}`,
      ].filter(Boolean).join("; ");
    }).join("; ");
  }
  if (sptEl["spt-cloud"]?.checked && Array.isArray(entry.cloud_tau0)) {
    const alpha = Array.isArray(entry.cloud_alpha_values) ? entry.cloud_alpha_values : [];
    return entry.cloud_tau0.map((tau0, index) => `tau_${index + 1}=${formatNumber(tau0, 5)}${alpha[index] !== undefined ? `; alpha_${index + 1}=${formatNumber(alpha[index], 5)}` : ""}`).join("; ");
  }
  return "";
}

function spectralColorExcess(av, rv) {
  if (!finiteNumber(av) || !finiteNumber(rv) || Number(rv) <= 0) return null;
  return Number(av) / Number(rv);
}

function spectralStitchingComment(stitching) {
  if (!stitching?.composite) return "";
  const scales = (stitching.scales || [])
    .map((row) => `${row.moca_specid}:${finiteNumber(row.scale) ? Number(row.scale).toPrecision(6) : "NA"}`)
    .join(",");
  const components = (stitching.components || [])
    .map((row) => `[${(row.specids || []).join(",")}:${row.method || "unknown"}]`)
    .join("|");
  const warnings = (stitching.warnings || []).join(" | ");
  return [
    stitching.merge_method || "overlap_graph",
    scales ? `scales=${scales}` : "",
    components ? `components=${components}` : "",
    warnings ? `warnings=${warnings}` : "",
  ].filter(Boolean).join(", ");
}

function setSpectralTypingExportDisabled(disabled) {
  for (const id of ["spt-export-csv", "spt-export-tsv", "spt-export-fits", "spt-export-votable", "spt-export-chi2-csv"]) {
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

function moveChi2Rank(delta) {
  const ranking = globalChi2Ranking();
  if (!ranking.length) return false;
  const currentRank = currentGlobalChi2Rank(ranking);
  const nextRank = currentRank < 0
    ? (delta < 0 ? 0 : ranking.length - 1)
    : currentRank + delta;
  if (nextRank < 0 || nextRank >= ranking.length || nextRank === currentRank) return false;
  const next = ranking[nextRank];
  sptState.selectedGrid = next.grid;
  sptState.currentIndex = next.localIndex;
  sptState.hasAppliedInitialIndex = true;
  sptEl["spt-grid-select"].value = next.grid;
  updateSpectralUrl();
  renderSpectralTyping();
  return true;
}

function currentGridValues() {
  if (sptState.comparePayload?.entries?.length) {
    return orderedGridValues(sptState.comparePayload.entries.map((entry) => entry.grid));
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
    const { includeSourceSpecids, ...traceOptions } = baseTrace;
    traces.push({
      ...traceOptions,
      x: chunk.map((row) => row.wv),
      y: chunk.map((row) => row.spn),
      ...(includeSourceSpecids ? { customdata: chunk.map((row) => row.source_specids || "") } : {}),
      showlegend: Boolean(baseTrace.showlegend) && index === 0,
    });
  });
}

function addLowResolutionStandardMarkerTraces(traces, rows, normRegions, options) {
  const { standardColor, standardName, correctionLabel } = options;
  for (const region of normRegions) {
    const segment = segmentRows(rows, region);
    if (!segment.length) continue;
    const chunks = splitRowsByWavelengthGap(segment);
    chunks.forEach((chunk) => {
      traces.push({
        x: chunk.map((row) => row.wv),
        y: chunk.map((row) => row.spn),
        type: "scatter",
        mode: "markers",
        marker: { symbol: "diamond-open", size: 9, color: standardColor, line: { color: standardColor, width: 2.25 } },
        opacity: 0.95,
        name: correctionLabel ? `${standardName}, ${correctionLabel} sampled` : `${standardName}, sampled`,
        legendgroup: "standard-lowres-markers",
        showlegend: false,
        hovertemplate: "Sampled standard<br>wv=%{x:.4f}<br>flux=%{y:.4f}<extra></extra>",
      });
    });
  }
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

function visibleSpectralTypingFeatureBands(xRange) {
  if (typeof globalThis.mocaBrownDwarfSpectralFeatureBandsInRange === "function") {
    return globalThis.mocaBrownDwarfSpectralFeatureBandsInRange(xRange);
  }
  const xmin = Math.min(...xRange);
  const xmax = Math.max(...xRange);
  return sptFeatureBands.filter((band) => band.range[1] >= xmin && band.range[0] <= xmax);
}

function visibleSpectralTypingFeatureRange(band, xRange) {
  if (typeof globalThis.mocaClippedSpectralFeatureBandRange === "function") {
    return globalThis.mocaClippedSpectralFeatureBandRange(band, xRange);
  }
  const xmin = Math.min(...xRange);
  const xmax = Math.max(...xRange);
  return [Math.max(band.range[0], xmin), Math.min(band.range[1], xmax)];
}

function featureShapes(xRange) {
  return visibleSpectralTypingFeatureBands(xRange).map((band) => {
    const visibleRange = visibleSpectralTypingFeatureRange(band, xRange);
    return {
      type: "rect",
      x0: visibleRange[0],
      x1: visibleRange[1],
      xref: "x",
      y0: 0,
      y1: 0.94,
      yref: "paper",
      fillcolor: band.fill,
      line: { width: 0 },
      layer: "below",
    };
  });
}

function featureAnnotations(xRange) {
  return visibleSpectralTypingFeatureBands(xRange).map((band) => {
    const visibleRange = visibleSpectralTypingFeatureRange(band, xRange);
    return {
      x: 0.5 * (visibleRange[0] + visibleRange[1]),
      xref: "x",
      y: 0.98 - 0.035 * (Number(band.labelTier) || 0),
      yref: "paper",
      text: band.name,
      showarrow: false,
      font: { size: 10, color: band.text },
      textangle: -90,
      yanchor: "top",
    };
  });
}

function metricAnnotation(entry, payload = null) {
  const deredden = Boolean(sptEl["spt-deredden"]?.checked);
  const cloud = Boolean(sptEl["spt-cloud"]?.checked);
  const correctionReady = deredden
    ? Array.isArray(entry.spectrum_dered) && entry.spectrum_dered.length > 0
    : (!cloud || (Array.isArray(entry.spectrum_cloud) && entry.spectrum_cloud.length > 0));
  const correctionComputing = Boolean(payload?.meta?.progressive && (deredden || cloud) && !correctionReady);
  const chi2Text = entry.chi2_eligible === false
    ? "excluded (insufficient overlap)"
    : (correctionComputing ? "(computing)" : formatNumber(entry.reduced_chi2, 2));
  const lines = [`χ<sup>2</sup>: ${chi2Text}`];
  if (finiteNumber(entry.log_wavelength_overlap_percent)) {
    lines.push(`mean log(λ) overlap: ${formatNumber(entry.log_wavelength_overlap_percent, 1)}%`);
  }
  if (correctionComputing) {
    lines.push("best_parameters = (computing)");
  } else if (deredden && Array.isArray(entry.A_V)) {
    const showRv = !spectralRvIsFixed();
    entry.A_V.forEach((av, index) => {
      const rv = Array.isArray(entry.R_V) ? entry.R_V[index] : null;
      const colorExcess = spectralColorExcess(av, rv);
      lines.push(`${fitLabel("A(V)", index)}: ${formatNumber(av, 2)}`);
      if (colorExcess !== null) lines.push(`${fitLabel("E(B-V)", index)}: ${formatNumber(colorExcess, 2)}`);
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
  const specids = uniqueSpectralIntegers(payload.meta?.specids || []);
  if (specids.length > 1) ids.push(`specids=${specids.join(",")}`);
  else if (payload.meta?.specid) ids.push(`specid=${payload.meta.specid}`);
  if (payload.comparisonMetadata?.moca_oid) ids.push(`oid=${payload.comparisonMetadata.moca_oid}`);
  const idText = ids.length ? ` (${ids.join("; ")})` : "";
  const standard = `${entry.spectral_type || ""} (${entry.designation || entry.object_designation || ""})`.trim();
  return `${comparison}${idText} vs ${standard}, ${entry.grid} grid`;
}

function comparisonShortName(payload) {
  const meta = payload.comparisonMetadata || {};
  return meta.designation || meta.spectrum_name || `specid${payload.meta?.specid || ""}`;
}

function comparisonIdentifier(payload = sptState.comparePayload) {
  const specids = uniqueSpectralIntegers(payload?.meta?.specids || selectedComparisonSpecids());
  if (specids.length > 1) return `specids_${specids.join("_")}`;
  const specid = parseInteger(payload?.meta?.specid ?? specids[0] ?? sptState.selectedSpecid);
  return specid !== null ? `specid_${specid}` : "comparison_unknown";
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
  const comparisonSpecids = selectedComparisonSpecids();
  const hasResolvedSelection = sptState.hasAppliedInitialIndex || Boolean(sptState.comparePayload?.entries?.length);
  const shouldPersistGrid = hasResolvedSelection || Boolean(sptState.initialGridParam);
  const shouldPersistIndex = hasResolvedSelection || hasExplicitUrlStandardSelection();
  if (sptState.combineMode) {
    if (comparisonSpecids.length) params.set("specids", comparisonSpecids.join(","));
    else params.delete("specids");
    params.delete("specid");
    params.delete("moca_specid");
    if (comparisonSpecids.length < 2) params.set("combine", "1");
    else params.delete("combine");
  } else if (sptState.selectedSpecid !== null) {
    params.set("specid", sptState.selectedSpecid);
    params.delete("specids");
    params.delete("combine");
  } else {
    params.delete("specid");
    params.delete("moca_specid");
    params.delete("specids");
    params.delete("combine");
    params.delete("grid_index");
  }
  if (sptState.selectedGrid && shouldPersistGrid) params.set("grid", sptState.selectedGrid);
  else params.delete("grid");
  if (comparisonSpecids.length && sptState.selectedGrid && shouldPersistIndex) params.set("grid_index", String(sptState.currentIndex || 0));
  else params.delete("grid_index");
  params.set("bins", sptEl["spt-bins"].value || String(sptDefaultBins));
  params.set("norm", sptEl["spt-norm"].value || sptDefaultNormText);
  params.set("min_overlap", String(minimumLogWavelengthOverlapPercent()));
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
  if (sptEl["spt-showoh"].checked) params.set("showoh", "1");
  else params.delete("showoh");
  if (sptEl["spt-showhydrogen"].checked) params.set("showhydrogen", "1");
  else params.delete("showhydrogen");
  params.delete("oh_lines");
  params.delete("hydrogen_lines");
  if (sptEl["spt-disable-lowres"].checked) params.set("disable_lowres", "1");
  else params.delete("disable_lowres");
  if (selectedStandardsSource() === sptStandardsSourcePickles) params.set("standards_source", sptStandardsSourcePickles);
  else params.delete("standards_source");
  if (onlyFieldObjectsEnabled()) params.set("only_field", "1");
  else params.delete("only_field");
  params.delete("only_field_objects");
  params.delete("extend_pickles");
  params.delete("pickles");
  params.delete("pickles_standards");
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
  for (const key of ["host", "port", "user", "username", "pwd", "password", "dbase", "db", "database", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  return params;
}

function selectedStandardsSource() {
  return sptEl["spt-standards-source"]?.value === sptStandardsSourcePickles
    ? sptStandardsSourcePickles
    : sptStandardsSourceMoca;
}

function onlyFieldObjectsEnabled() {
  return Boolean(sptEl["spt-only-field"]?.checked);
}

function spectralStandardsSourceUrlValue(params) {
  const rawValue = String(
    params.get("standards_source")
    || params.get("standard_source")
    || params.get("template_source")
    || params.get("templates")
    || ""
  ).trim().toLowerCase();
  if (["pickles", "pickles_spectral_library", "pickles-library", "pickles library"].includes(rawValue)) {
    return sptStandardsSourcePickles;
  }
  if (
    asSpectralBool(params.get("extend_pickles"))
    || asSpectralBool(params.get("pickles"))
    || asSpectralBool(params.get("pickles_standards"))
  ) {
    return sptStandardsSourcePickles;
  }
  return sptStandardsSourceMoca;
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

function mixHexColorWithWhite(color, whiteFraction) {
  const match = String(color || "").trim().match(/^#?([0-9a-f]{6})$/i);
  if (!match) return color;
  const fraction = Math.max(0, Math.min(1, Number(whiteFraction) || 0));
  const hex = match[1];
  const channels = [0, 2, 4].map((start) => Number.parseInt(hex.slice(start, start + 2), 16));
  const mixed = channels.map((channel) => Math.round(channel * (1 - fraction) + 255 * fraction));
  return `rgb(${mixed[0]}, ${mixed[1]}, ${mixed[2]})`;
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
