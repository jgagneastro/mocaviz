const axisTypes = [
  { value: "spectral_type", label: "Spectral Type" },
  { value: "color", label: "Color" },
  { value: "absolute_magnitude", label: "Absolute Magnitude" },
  { value: "spectral_index", label: "Spectral Index" },
  { value: "equivalent_width", label: "Equivalent Width" },
];

const classColors = {
  O: "purple",
  B: "darkblue",
  A: "blue",
  F: "#68a6d9",
  G: "#72b85f",
  K: "darkgreen",
  M: "#E69F00",
  L: "#009E73",
  T: "#0072B2",
  Y: "#CC79A7",
};

const spectralClassLegendOrder = ["M", "L", "T", "Y"];
const simplePhotometryPrefix = "simple:";
const simplePhotometryBands = ["g", "r", "i", "z", "y", "J", "H", "K", "W1", "W2", "W3", "W4"];
const broadSampleMaxObjects = 1000000;
const spectralTypeJitterAmplitude = 0.3;
const yDwarfRangePaddingFraction = 0.05;
const ageColorbarLength = 0.7371;
const ageColorbarBinaryLengthMultiplier = 0.95;
const ageColorbarPhotdistLengthMultiplier = 0.95;
const ageColorbarAllOptionalLengthMultiplier = 0.95;
const noAgeMarkerColor = "#8d8d8d";
const ageColorscale = [
  [0, "rgb(150,0,90)"],
  [0.125, "rgb(0,0,200)"],
  [0.25, "rgb(0,25,255)"],
  [0.375, "rgb(0,152,255)"],
  [0.5, "rgb(44,255,150)"],
  [0.625, "rgb(151,255,0)"],
  [0.75, "rgb(255,234,0)"],
  [0.875, "rgb(255,111,0)"],
  [1, "rgb(255,0,0)"],
];
const plotAspectRatio = 16 / 9;
const minPlotHeight = 420;

const sampleSymbols = {
  field: "circle",
  low_gravity: "triangle-up",
  subdwarf: "square",
};

const sampleLegendLabels = {
  field: "Field",
  low_gravity: "Low-gravity",
  subdwarf: "Subdwarf",
};
const binaryLegendColor = "#6f7472";
const photometricSptLegendColor = "#8a8f8d";
const photometricSptEdgeColor = "#111";
const photometricSptEdgeWidth = 2;

const state = {
  raw: null,
  maps: null,
  allRows: [],
  rows: [],
  selectedOids: [],
  selectedDesignations: [],
  hiddenLegendClasses: new Set(),
  hiddenLegendSamples: new Set(),
  hiddenLegendBinaries: false,
  hiddenLegendPhotdist: false,
  legendClickTimer: null,
  manualPhotdistChoice: false,
  plotBound: false,
  plotLoadReasons: new Set(),
  autoErrorDefaults: { x: false, y: false },
  manualErrorThresholds: { x: false, y: false },
  axisRangeRevision: 0,
  pendingInitialAxisRange: true,
  lastAppliedAxisRangeSignature: "",
  plotRenderToken: 0,
  plotCanvasKey: "",
  forceFreshPlot: false,
  loadToken: 0,
  reloadTimer: null,
  plotResizeFrame: null,
  plotResizeObserver: null,
  featuresLoaded: {
    designations: false,
    spectralIndices: false,
    equivalentWidths: false,
    ages: false,
  },
  featureLoads: {},
  photometryLoaded: new Set(),
  spectralIndicesLoaded: new Set(),
  photometricDistancesLoaded: false,
  sequencesKey: "",
  sequencesLoadedAll: false,
  bulkPreloadActive: false,
  cacheClearActive: false,
  preservedDesignationOids: new Set(),
};

const appBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function appUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), appBaseUrl).toString();
}

const el = {};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  collectElements();
  updateLocalOnlyControls();
  fillAxisTypeSelects();
  readInitialUrlState();
  bindControls();
  await loadBootstrap({ applyAxisDefaults: true, resetAxisRange: true });
}

function updateLocalOnlyControls() {
  const host = window.location.hostname.toLowerCase();
  const isLocalHost = host === "localhost" || host === "127.0.0.1" || host === "::1" || host.endsWith(".localhost");
  if (el["bulk-preload-local-only"]) el["bulk-preload-local-only"].hidden = !isLocalHost;
}

function collectElements() {
  [
    "status",
    "x-axis-type",
    "x-value-1",
    "x-value-2",
    "x-value-1-wrap",
    "x-value-2-wrap",
    "x-value-1-label",
    "x-value-2-label",
    "y-axis-type",
    "y-value-1",
    "y-value-2",
    "y-value-1-wrap",
    "y-value-2-wrap",
    "y-value-1-label",
    "y-value-2-label",
    "spt-range",
    "highlight-designation-search",
    "highlight-designation-results",
    "highlight-designation-selected",
    "highlight-oids",
    "xerr-max",
    "yerr-max",
    "show-errors",
    "include-photdist",
    "include-binaries",
    "include-photspt",
    "include-risky-photspt",
    "risky-photspt-line",
    "advanced-photometry",
    "color-by-age",
    "visual-area",
    "plot",
    "plot-loader",
    "count-summary",
    "plot-hint",
    "selection-table",
    "missing-oids",
    "export-csv",
    "export-tsv",
    "export-fits",
    "export-votable",
    "bulk-preload",
    "bulk-preload-status",
    "bulk-preload-local-only",
    "clear-cache",
    "clear-cache-status",
  ].forEach((id) => {
    el[id] = document.getElementById(id);
  });
}

function fillAxisTypeSelects() {
  for (const id of ["x-axis-type", "y-axis-type"]) {
    el[id].innerHTML = axisTypes.map((item) => optionHtml(item.value, item.label)).join("");
  }
}

function readInitialUrlState() {
  const params = new URLSearchParams(window.location.search);
  const explicitErrorThresholds = {
    x: params.has("xerr_max"),
    y: params.has("yerr_max"),
  };
  state.manualErrorThresholds = { ...explicitErrorThresholds };
  el["x-axis-type"].value = validAxisType(params.get("xaxis_type")) || "color";
  el["y-axis-type"].value = validAxisType(params.get("yaxis_type")) || "absolute_magnitude";
  el["spt-range"].value = params.get("spt_range") || "L2+";
  el["highlight-oids"].value = params.get("moca_oid") || params.get("oid") || "";
  state.selectedDesignations = parseDesignationParams(params);
  el["xerr-max"].value = params.get("xerr_max") || "";
  el["yerr-max"].value = params.get("yerr_max") || "";
  el["show-errors"].checked = asBool(params.get("errors"));
  el["include-photdist"].checked = asBool(params.get("photdist"));
  state.manualPhotdistChoice = el["include-photdist"].checked;
  el["include-binaries"].checked = asBool(params.get("binaries"));
  el["include-photspt"].checked = asBool(params.get("photspt"));
  el["include-risky-photspt"].checked = asBool(params.get("risky_photspt")) || asBool(params.get("include_risky_photspt"));
  el["advanced-photometry"].checked = asBool(params.get("advanced_photometry"));
  el["color-by-age"].checked = asBool(params.get("agecolor"));
  updatePhotdistControl();
  updateAdvancedPhotometryControl();
  if (applyAxisErrorDefaults(explicitErrorThresholds)) requestInitialAxisRange();
}

function validAxisType(value) {
  return axisTypes.some((item) => item.value === value) ? value : null;
}

function asBool(value) {
  return ["1", "true", "yes"].includes(String(value || "").toLowerCase());
}

function bindControls() {
  const axisControls = new Set([
    "x-axis-type",
    "x-value-1",
    "x-value-2",
    "y-axis-type",
    "y-value-1",
    "y-value-2",
  ]);
  for (const id of axisControls) {
    el[id].addEventListener("change", () => {
      if (id.endsWith("axis-type")) {
        refreshAxisValueControls(id[0], { preferDefaults: true });
        applyAxisErrorDefaults();
      }
      updatePhotdistControl();
      updateAdvancedPhotometryControl();
      requestInitialAxisRange();
      render();
    });
  }
  for (const id of ["xerr-max", "yerr-max"]) {
    el[id].addEventListener("input", () => {
      state.autoErrorDefaults[id[0]] = false;
      state.manualErrorThresholds[id[0]] = true;
      requestInitialAxisRange();
      render();
    });
    el[id].addEventListener("change", () => {
      state.autoErrorDefaults[id[0]] = false;
      state.manualErrorThresholds[id[0]] = true;
      requestInitialAxisRange();
      render();
    });
  }
  for (const id of ["show-errors", "include-binaries", "color-by-age"]) {
    el[id].addEventListener("input", render);
    el[id].addEventListener("change", render);
  }
  el["include-photdist"].addEventListener("change", () => {
    state.manualPhotdistChoice = el["include-photdist"].checked;
    requestInitialAxisRange();
    render();
  });
  el["spt-range"].addEventListener("input", () => {
    requestInitialAxisRange();
    render();
    scheduleBootstrapReload({ resetAxisRange: true });
  });
  el["highlight-oids"].addEventListener("input", () => {
    render();
    scheduleBootstrapReload({ resetAxisRange: false });
  });
  el["highlight-designation-search"].addEventListener("focus", () => {
    ensureDesignationsLoaded();
    renderDesignationPicker();
  });
  el["highlight-designation-search"].addEventListener("input", () => {
    ensureDesignationsLoaded();
    renderDesignationPicker();
  });
  el["highlight-designation-search"].addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const match = designationSearchMatches()[0];
    if (!match) return;
    event.preventDefault();
    selectDesignation(match.designation);
  });
  el["highlight-designation-results"].addEventListener("mousedown", (event) => {
    const button = event.target instanceof Element ? event.target.closest("button[data-designation]") : null;
    if (!button) return;
    event.preventDefault();
    selectDesignation(button.dataset.designation);
  });
  el["highlight-designation-selected"].addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("button[data-remove-designation]") : null;
    if (!button) return;
    removeDesignation(button.dataset.removeDesignation);
  });
  el["include-photspt"].addEventListener("change", () => {
    requestInitialAxisRange();
    render();
    if (!photometricSptCatalogReady()) {
      scheduleBootstrapReload({ resetAxisRange: true });
    }
  });
  el["include-risky-photspt"].addEventListener("change", () => {
    updatePhotometricSptControl();
    requestInitialAxisRange();
    render();
    if (el["include-photspt"].checked) {
      scheduleBootstrapReload({ resetAxisRange: true });
    }
  });
  el["advanced-photometry"].addEventListener("change", () => {
    refreshAxisValueControls("x", { preferDefaults: true });
    refreshAxisValueControls("y", { preferDefaults: true });
    requestInitialAxisRange();
    render();
  });
  el["bulk-preload"]?.addEventListener("click", bulkPreloadAll);
  el["clear-cache"]?.addEventListener("click", clearDownloadedCache);
  el["export-csv"].addEventListener("click", exportCsv);
  el["export-tsv"].addEventListener("click", exportTsv);
  el["export-fits"].addEventListener("click", exportFits);
  el["export-votable"].addEventListener("click", exportVotable);
  window.addEventListener("resize", schedulePlotResize);
  installPlotResizeObserver();
}

function requestInitialAxisRange() {
  state.pendingInitialAxisRange = true;
}

function scheduleBootstrapReload(options = {}) {
  window.clearTimeout(state.reloadTimer);
  state.reloadTimer = window.setTimeout(() => loadBootstrap(options), 500);
}

function hasAbsoluteMagnitudeAxis() {
  return el["x-axis-type"].value === "absolute_magnitude" || el["y-axis-type"].value === "absolute_magnitude";
}

function includePhotometricDistancesForAxes() {
  return hasAbsoluteMagnitudeAxis() && el["include-photdist"].checked;
}

function applyAxisErrorDefaults(explicitErrorThresholds = {}) {
  let changed = false;
  for (const axis of ["x", "y"]) {
    const input = el[`${axis}err-max`];
    const defaultValue = defaultErrorThresholdForAxisType(el[`${axis}-axis-type`].value);
    const hasManualThreshold = Boolean(explicitErrorThresholds[axis] || state.manualErrorThresholds[axis]);
    if (defaultValue) {
      if (!hasManualThreshold && (input.value === "" || state.autoErrorDefaults[axis])) {
        if (input.value !== defaultValue) {
          input.value = defaultValue;
          changed = true;
        }
        state.autoErrorDefaults[axis] = true;
      }
    } else if (state.autoErrorDefaults[axis]) {
      input.value = "";
      state.autoErrorDefaults[axis] = false;
      changed = true;
    }
  }
  return changed;
}

function defaultErrorThresholdForAxisType(type) {
  if (type === "spectral_type") return "3";
  if (type === "absolute_magnitude") return "0.5";
  if (type === "color") return "0.2";
  if (type === "equivalent_width") return "5";
  return "";
}

function updatePhotdistControl() {
  const checkbox = el["include-photdist"];
  const hasAbsoluteAxis = hasAbsoluteMagnitudeAxis();
  if (!hasAbsoluteAxis && !checkbox.disabled) {
    state.manualPhotdistChoice = checkbox.checked;
  }
  checkbox.disabled = !hasAbsoluteAxis;
  checkbox.checked = hasAbsoluteAxis ? state.manualPhotdistChoice : true;
  checkbox.closest(".checkline")?.classList.toggle("is-disabled", !hasAbsoluteAxis);
}

function hasPhotometryAxis() {
  return ["x", "y"].some((axis) => {
    const type = el[`${axis}-axis-type`].value;
    return type === "color" || type === "absolute_magnitude";
  });
}

function useAdvancedPhotometrySystems() {
  return hasPhotometryAxis() && el["advanced-photometry"].checked;
}

function updateAdvancedPhotometryControl() {
  const checkbox = el["advanced-photometry"];
  const enabled = hasPhotometryAxis();
  checkbox.disabled = !enabled;
  checkbox.closest(".checkline")?.classList.toggle("is-disabled", !enabled);
}

function updatePhotometricSptControl() {
  const checkbox = el["include-photspt"];
  const riskyCheckbox = el["include-risky-photspt"];
  const riskyLine = el["risky-photspt-line"];
  if (!checkbox || !riskyCheckbox || !riskyLine) return;
  checkbox.disabled = false;
  const privateData = Boolean(state.raw?.meta?.private_db);
  riskyLine.hidden = !privateData;
  riskyCheckbox.disabled = !privateData;
  if (!privateData) riskyCheckbox.checked = false;
  const line = checkbox.closest(".checkline");
  line?.classList.toggle("is-disabled", false);
  if (line) line.title = "";
  riskyLine.classList.toggle("is-disabled", !privateData);
  riskyLine.title = privateData
    ? "When enabled, this reloads all photometric spectral type estimates from the active private data source."
    : "";
}

function riskyPhotometricSptRequested() {
  return Boolean(el["include-risky-photspt"]?.checked);
}

function photometricSptCatalogReady() {
  if (!el["include-photspt"].checked) return true;
  if (!state.raw?.meta?.include_photometric_spt) return false;
  if (riskyPhotometricSptRequested() && !state.raw?.meta?.include_risky_photometric_spt) return false;
  if (!riskyPhotometricSptRequested() && state.raw?.meta?.include_risky_photometric_spt) return false;
  return true;
}

function buildBootstrapParams() {
  const params = new URLSearchParams(window.location.search);
  params.set("spt_range", el["spt-range"].value || "L2+");
  const oidValue = backendHighlightOidValue();
  if (oidValue) params.set("moca_oid", oidValue);
  else params.delete("moca_oid");
  params.delete("oid");
  params.delete("designation");
  params.delete("designations");
  if (state.selectedDesignations.length) {
    params.set("designation", state.selectedDesignations.join(","));
  }
  params.set("photspt", el["include-photspt"].checked ? "1" : "0");
  params.set("risky_photspt", riskyPhotometricSptRequested() ? "1" : "0");
  params.set("advanced_photometry", useAdvancedPhotometrySystems() ? "1" : "0");
  params.set("photdist", includePhotometricDistancesForAxes() ? "1" : "0");
  params.set("xaxis_type", el["x-axis-type"].value || "color");
  params.set("yaxis_type", el["y-axis-type"].value || "absolute_magnitude");
  normalizeBroadSampleCap(params);
  for (const axis of ["x", "y"]) {
    const value1Control = el[`${axis}-value-1`];
    const value2Control = el[`${axis}-value-2`];
    const controlsReady = state.raw || value1Control.options.length > 0 || value2Control.options.length > 0;
    if (!controlsReady) continue;
    params.delete(`${axis}axis_value_1`);
    params.delete(`${axis}axis_value_2`);
    const value1 = value1Control.value;
    const value2 = value2Control.value;
    if (value1) params.set(`${axis}axis_value_1`, value1);
    if (value2) params.set(`${axis}axis_value_2`, value2);
  }
  return params;
}

function updateUrlFromControls() {
  const params = buildBootstrapParams();
  params.set("errors", el["show-errors"].checked ? "1" : "0");
  params.set("binaries", el["include-binaries"].checked ? "1" : "0");
  params.set("agecolor", el["color-by-age"].checked ? "1" : "0");
  copyInputValueToParam(params, "xerr_max", "xerr-max");
  copyInputValueToParam(params, "yerr_max", "yerr-max");
  const query = params.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}

function copyInputValueToParam(params, paramName, elementId) {
  const value = String(el[elementId]?.value || "").trim();
  if (value) params.set(paramName, value);
  else params.delete(paramName);
}

function backendHighlightOidValue() {
  const oids = parseOidList(el["highlight-oids"].value);
  const seen = new Set(oids);
  for (const oid of state.preservedDesignationOids) {
    if (seen.has(oid)) continue;
    seen.add(oid);
    oids.push(oid);
  }
  for (const oid of selectedDesignationOids()) {
    if (seen.has(oid)) continue;
    seen.add(oid);
    oids.push(oid);
  }
  return oids.join(",");
}

function normalizeBroadSampleCap(params, forceBroad = usesBroadSample()) {
  if (!forceBroad) return;
  const current = String(params.get("max_objects") || "").trim().toLowerCase();
  if (["0", "none", "uncapped", "all"].includes(current)) return;
  const value = Number(current);
  if (!Number.isFinite(value) || value < broadSampleMaxObjects) {
    params.set("max_objects", String(broadSampleMaxObjects));
  }
}

function usesBroadSample() {
  const range = parseSptRange(el["spt-range"].value);
  return el["include-photspt"].checked || (range && range.min < 10);
}

function buildBulkPreloadParams() {
  const params = buildBootstrapParams();
  params.set("photspt", "1");
  params.set("include_photspt", "1");
  params.set("risky_photspt", "0");
  params.set("include_risky_photspt", "0");
  params.set("photdist", "1");
  params.set("include_photdist", "1");
  params.set("psids", "all");
  params.set("siids", "all");
  params.set("sequences", "all");
  params.set("bulk", "1");
  normalizeBroadSampleCap(params, true);
  return params;
}

async function loadBootstrap(options = {}) {
  const token = ++state.loadToken;
  state.plotLoadReasons.clear();
  setPlotLoading("catalog", true);
  setStatus("Loading catalog");
  try {
    const params = buildBootstrapParams();
    const response = await fetch(appUrl(`api/bootstrap?${params.toString()}`));
    const payload = await response.json();
    if (token !== state.loadToken) return;
    state.raw = payload;
    state.maps = buildMaps(payload.catalog);
    resetFeatureState(payload);
    updatePhotometricSptControl();
    if (options.resetAxisRange) requestInitialAxisRange();
    refreshAxisValueControls("x");
    refreshAxisValueControls("y");
    if (options.applyAxisDefaults) applyAxisDefaults(params);
    if (applyAxisErrorDefaults()) requestInitialAxisRange();
    state.sequencesKey = state.sequencesLoadedAll ? "all" : currentSequenceKey();

    const count = payload.meta && payload.meta.object_count ? payload.meta.object_count : 0;
    const capped = payload.meta && payload.meta.object_limit_applied ? `, capped at ${payload.meta.max_objects}` : "";
    const sptMode = payload.meta && payload.meta.include_photometric_spt ? ", including photometric spectral types" : ", spectroscopic spectral types only";
    if (payload.ok) {
      setStatus(`${count.toLocaleString()} objects loaded from ${displaySource(payload.source)}${sptMode}${capped}`);
    } else {
      setStatus(`Using sample data: ${payload.error}`, true);
    }
    render();
    loadPhotometryOptionCounts(token);
  } finally {
    if (token === state.loadToken) setPlotLoading("catalog", false);
  }
}

async function bulkPreloadAll() {
  if (state.bulkPreloadActive) return;
  const token = ++state.loadToken;
  window.clearTimeout(state.reloadTimer);
  state.bulkPreloadActive = true;
  state.plotLoadReasons.clear();
  setPlotLoading("bulk-preload", true);
  setBulkPreloadControls(true, "Bulk loading all app data. This can take a few minutes.");
  setStatus("Bulk loading all app data");
  try {
    const params = buildBulkPreloadParams();
    const response = await fetch(appUrl(`api/preload?${params.toString()}`));
    const payload = await response.json();
    if (token !== state.loadToken) return;
    if (!payload.ok) {
      const message = payload.error || "Unknown preload error";
      setBulkPreloadControls(false, `Bulk load failed: ${message}`, true);
      setStatus(`Bulk load failed: ${message}`, true);
      return;
    }
    state.raw = payload;
    state.maps = buildMaps(payload.catalog);
    resetFeatureState(payload);
    updatePhotometricSptControl();
    refreshAxisValueControls("x");
    refreshAxisValueControls("y");
    requestInitialAxisRange();
    state.forceFreshPlot = true;
    const counts = bulkPreloadCounts(payload);
    const elapsed = Number(payload.meta?.timings?.preload_total);
    const elapsedText = Number.isFinite(elapsed) ? ` in ${elapsed.toFixed(1)} s` : "";
    const omissionText = payload.meta?.preload_omitted_risky_photometric_spt
      ? " Risky photometric SPT estimates were omitted from the bulk preload."
      : "";
    setStatus(`Bulk preload complete${elapsedText}: ${counts}.${omissionText}`);
    setBulkPreloadControls(false, `Loaded ${counts}${elapsedText}.${omissionText}`);
    render();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (token === state.loadToken) {
      setBulkPreloadControls(false, `Bulk load failed: ${message}`, true);
      setStatus(`Bulk load failed: ${message}`, true);
    }
  } finally {
    if (token === state.loadToken) {
      state.bulkPreloadActive = false;
      setPlotLoading("bulk-preload", false);
    }
  }
}

async function clearDownloadedCache() {
  if (state.cacheClearActive || state.bulkPreloadActive) return;
  const designationOidsToPreserve = selectedDesignationOids();
  ++state.loadToken;
  window.clearTimeout(state.reloadTimer);
  state.cacheClearActive = true;
  state.bulkPreloadActive = false;
  clearClientData({ preservedDesignationOids: designationOidsToPreserve });
  state.plotLoadReasons.clear();
  setPlotLoading("clear-cache", true);
  setCacheControls(true, "Clearing cache and reloading.");
  setBulkPreloadControls(false, "Not loaded.");
  setStatus("Clearing cache");
  try {
    const response = await fetch(appUrl("api/cache/clear"), { method: "POST" });
    const payload = await response.json();
    if (!payload.ok) {
      throw new Error(payload.error || "Cache clear failed");
    }
    const bootstrap = Number(payload.cleared?.bootstrap || 0);
    const features = Number(payload.cleared?.features || 0);
    setCacheControls(true, `Cleared ${bootstrap.toLocaleString()} catalog and ${features.toLocaleString()} feature cache entries. Reloading.`);
    setStatus("Cache cleared; reloading catalog");
    await loadBootstrap({ applyAxisDefaults: false, resetAxisRange: true });
    setCacheControls(false, `Cache cleared and reloaded at ${new Date().toLocaleTimeString()}.`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    setCacheControls(false, `Cache clear failed: ${message}`, true);
    setStatus(`Cache clear failed: ${message}`, true);
  } finally {
    state.cacheClearActive = false;
    setPlotLoading("clear-cache", false);
  }
}

function clearClientData(options = {}) {
  state.preservedDesignationOids = new Set(options.preservedDesignationOids || []);
  state.raw = null;
  state.maps = null;
  state.allRows = [];
  state.rows = [];
  state.selectedOids = [];
  state.hiddenLegendClasses.clear();
  state.hiddenLegendSamples.clear();
  state.hiddenLegendBinaries = false;
  state.hiddenLegendPhotdist = false;
  state.featuresLoaded = {
    designations: false,
    spectralIndices: false,
    equivalentWidths: false,
    ages: false,
  };
  state.featureLoads = {};
  state.photometryLoaded = new Set();
  state.spectralIndicesLoaded = new Set();
  state.photometricDistancesLoaded = false;
  state.sequencesKey = "";
  state.sequencesLoadedAll = false;
  state.pendingInitialAxisRange = true;
  state.lastAppliedAxisRangeSignature = "";
  state.forceFreshPlot = true;
  updatePhotometricSptControl();
  if (el.plot && window.Plotly) Plotly.purge(el.plot);
  state.plotBound = false;
  if (el["selection-table"]) el["selection-table"].innerHTML = "";
  if (el["missing-oids"]) {
    el["missing-oids"].hidden = true;
    el["missing-oids"].textContent = "";
  }
  if (el["count-summary"]) el["count-summary"].textContent = "";
}

function bulkPreloadCounts(payload) {
  const catalog = payload.catalog || {};
  const parts = [
    `${Number(catalog.objects?.length || 0).toLocaleString()} objects`,
    `${Number(catalog.designations?.length || 0).toLocaleString()} designations`,
    `${Number(catalog.photometry?.length || 0).toLocaleString()} photometry rows`,
    `${Number(catalog.spectralIndices?.length || 0).toLocaleString()} spectral-index rows`,
    `${Number(catalog.equivalentWidths?.length || 0).toLocaleString()} EW rows`,
    `${Number(catalog.ages?.length || 0).toLocaleString()} ages`,
  ];
  return parts.join(", ");
}

function setBulkPreloadControls(disabled, text, isError = false) {
  if (el["bulk-preload"]) el["bulk-preload"].disabled = disabled;
  if (!el["bulk-preload-status"]) return;
  el["bulk-preload-status"].textContent = text;
  el["bulk-preload-status"].classList.toggle("error", Boolean(isError));
}

function setCacheControls(disabled, text, isError = false) {
  if (el["clear-cache"]) el["clear-cache"].disabled = disabled;
  if (!el["clear-cache-status"]) return;
  el["clear-cache-status"].textContent = text;
  el["clear-cache-status"].classList.toggle("error", Boolean(isError));
}

function resetFeatureState(payload) {
  const lazy = new Set(payload.meta?.lazy_features || []);
  state.featuresLoaded = {
    designations: !lazy.has("designations"),
    spectralIndices: !lazy.has("spectralIndices"),
    equivalentWidths: !lazy.has("equivalentWidths"),
    ages: !lazy.has("ages"),
  };
  state.photometryLoaded = new Set(payload.meta?.photometry_psids || (payload.catalog?.photometry || []).map((row) => row.moca_psid));
  for (const band of payload.meta?.photometry_simplebands || []) {
    state.photometryLoaded.add(simplePhotometryValue(band));
  }
  state.spectralIndicesLoaded = new Set(payload.meta?.spectral_index_siids || (payload.catalog?.spectralIndices || []).map((row) => row.moca_siid));
  state.photometricDistancesLoaded = Boolean(payload.meta?.include_photometric_dist);
  state.sequencesLoadedAll = Boolean(payload.meta?.all_sequences_loaded);
  state.featureLoads = {};
}

function ensureNeededFeatures() {
  if (!state.raw || !state.maps) return;
  if (state.selectedDesignations.length && !state.featuresLoaded.designations && !state.featureLoads.designations) {
    loadFeature("designations");
  }
  if (includePhotometricDistancesForAxes() && !state.photometricDistancesLoaded && !state.featureLoads.distances) {
    loadDistances();
  }
  const sequenceKey = currentSequenceKey();
  if (!state.sequencesLoadedAll && sequenceKey !== state.sequencesKey && !state.featureLoads.sequences) {
    loadSequences(sequenceKey);
  }

  const missingPhotometry = neededPhotometryPsids().filter((psid) => !state.photometryLoaded.has(psid));
  if (missingPhotometry.length && !state.featureLoads.photometry) {
    loadPhotometry(missingPhotometry);
  }

  const needed = new Set();
  const missingSpectralIndices = neededSpectralIndexIds().filter((siid) => !state.spectralIndicesLoaded.has(siid));
  if (missingSpectralIndices.length) needed.add("spectralIndices");
  for (const axis of ["x", "y"]) {
    const type = el[`${axis}-axis-type`].value;
    if (type === "equivalent_width") needed.add("equivalentWidths");
  }
  if (el["color-by-age"].checked) needed.add("ages");

  for (const feature of needed) {
    if ((feature === "spectralIndices" || !state.featuresLoaded[feature]) && !state.featureLoads[feature]) {
      loadFeature(feature);
    }
  }
}

function currentSequenceKey() {
  return ["x", "y"].map((axis) => {
    const spec = axisSpec(axis);
    return [spec.type, spec.value1 || "", spec.value2 || ""].join(",");
  }).join("|");
}

async function loadSequences(sequenceKey) {
  const token = state.loadToken;
  state.featureLoads.sequences = true;
  let shouldRender = false;
  if (!hasActiveDataLoads(["sequences"])) setStatus("Loading sequence overlays");
  try {
    const params = buildBootstrapParams();
    const response = await fetch(appUrl(`api/feature/sequences?${params.toString()}`));
    const payload = await response.json();
    if (token !== state.loadToken || sequenceKey !== currentSequenceKey()) return;
    if (!payload.ok) {
      setStatus(`Could not load sequences: ${payload.error}`, true);
      return;
    }
    state.raw.catalog.sequences = payload.rows || [];
    state.sequencesLoadedAll = Boolean(payload.meta?.all_sequences_loaded);
    state.sequencesKey = sequenceKey;
    state.maps = buildMaps(state.raw.catalog);
    const rowCount = payload.meta?.row_count || 0;
    if (rowCount > 0 && !hasActiveDataLoads(["sequences"])) {
      setStatus(`${rowCount.toLocaleString()} sequence rows loaded`);
    }
    shouldRender = true;
  } finally {
    delete state.featureLoads.sequences;
    if (shouldRender) scheduleFreshRenderAfterDataLoad(token);
  }
}

async function loadDistances() {
  const token = state.loadToken;
  state.featureLoads.distances = true;
  let shouldRender = false;
  setPlotLoading("distances", true);
  setStatus("Loading photometric distances");
  try {
    const params = buildBootstrapParams();
    params.set("photdist", "1");
    const response = await fetch(appUrl(`api/feature/distances?${params.toString()}`));
    const payload = await response.json();
    if (token !== state.loadToken) return;
    if (!payload.ok) {
      setStatus(`Could not load distances: ${payload.error}`, true);
      return;
    }
    state.raw.catalog.distances = mergeRowsByKey(
      state.raw.catalog.distances || [],
      payload.rows || [],
      (row) => row.id || `${row.moca_oid}|${row.photometric_estimate}|${row.distance_pc}`,
    );
    state.photometricDistancesLoaded = true;
    state.maps = buildMaps(state.raw.catalog);
    if (hasAbsoluteMagnitudeAxis()) requestInitialAxisRange();
    setStatus(`${(payload.meta?.row_count || 0).toLocaleString()} distance rows loaded`);
    shouldRender = true;
  } finally {
    delete state.featureLoads.distances;
    setPlotLoading("distances", false);
    if (shouldRender) scheduleFreshRenderAfterDataLoad(token);
  }
}

function neededPhotometryPsids() {
  const psids = [];
  for (const axis of ["x", "y"]) {
    const type = el[`${axis}-axis-type`].value;
    const value1 = el[`${axis}-value-1`].value;
    const value2 = el[`${axis}-value-2`].value;
    if ((type === "color" || type === "absolute_magnitude") && value1) psids.push(value1);
    if (type === "color" && value2) psids.push(value2);
  }
  return [...new Set(psids)];
}

function splitPhotometrySelectors(selectors) {
  const psids = [];
  const simplebands = [];
  for (const selector of selectors || []) {
    const band = simplePhotometryBand(selector);
    if (band) {
      if (!simplebands.includes(band)) simplebands.push(band);
    } else if (selector && !psids.includes(selector)) {
      psids.push(selector);
    }
  }
  return { psids, simplebands };
}

async function loadPhotometry(selectors) {
  const token = state.loadToken;
  state.featureLoads.photometry = true;
  let shouldRender = false;
  setPlotLoading("photometry", true);
  setStatus(`Loading ${selectors.join(", ")} photometry`);
  try {
    const params = buildBootstrapParams();
    const { psids, simplebands } = splitPhotometrySelectors(selectors);
    params.delete("psids");
    params.delete("simplebands");
    if (psids.length) params.set("psids", psids.join(","));
    if (simplebands.length) params.set("simplebands", simplebands.join(","));
    const response = await fetch(appUrl(`api/feature/photometry?${params.toString()}`));
    const payload = await response.json();
    if (token !== state.loadToken) return;
    if (!payload.ok) {
      setStatus(`Could not load photometry: ${payload.error}`, true);
      return;
    }
    state.raw.catalog.photometry = mergeRowsByKey(
      state.raw.catalog.photometry || [],
      payload.rows || [],
      (row) => `${row.moca_oid}|${row.moca_psid}`,
    );
    for (const selector of selectors) state.photometryLoaded.add(selector);
    state.maps = buildMaps(state.raw.catalog);
    if (selectors.some((selector) => neededPhotometryPsids().includes(selector))) requestInitialAxisRange();
    setStatus(`${(payload.meta?.row_count || 0).toLocaleString()} photometry rows loaded`);
    shouldRender = true;
  } finally {
    delete state.featureLoads.photometry;
    setPlotLoading("photometry", false);
    if (shouldRender) scheduleFreshRenderAfterDataLoad(token);
  }
}

async function loadPhotometryOptionCounts(token) {
  const params = buildBootstrapParams();
  const response = await fetch(appUrl(`api/feature/photometry-options?${params.toString()}`));
  const payload = await response.json();
  if (token !== state.loadToken || !payload.ok) return;
  state.raw.options.photometry = payload.rows || [];
  if (payload.meta?.simple_photometry_options) {
    state.raw.options.simplePhotometry = payload.meta.simple_photometry_options;
  }
  const changedX = refreshAxisValueControls("x");
  const changedY = refreshAxisValueControls("y");
  if (changedX || changedY) requestInitialAxisRange();
  render();
}

async function loadFeature(feature) {
  const routes = {
    designations: "designations",
    spectralIndices: "spectral-indices",
    equivalentWidths: "equivalent-widths",
    ages: "ages",
  };
  const labels = {
    designations: "designations",
    spectralIndices: "spectral indices",
    equivalentWidths: "equivalent widths",
    ages: "ages",
  };
  const loadingLabels = {
    designations: "designation catalog data",
    spectralIndices: "spectral-index catalog data",
    equivalentWidths: "equivalent-width catalog data",
    ages: "age catalog data",
  };
  const route = routes[feature];
  if (!route) return;

  const token = state.loadToken;
  state.featureLoads[feature] = true;
  let shouldRender = false;
  setPlotLoading(feature, true);
  setStatus(`Loading ${loadingLabels[feature]}`);
  try {
    const params = buildBootstrapParams();
    const response = await fetch(appUrl(`api/feature/${route}?${params.toString()}`));
    const payload = await response.json();
    if (token !== state.loadToken) return;
    if (!payload.ok) {
      setStatus(`Could not load ${labels[feature]}: ${payload.error}`, true);
      return;
    }
    if (feature === "spectralIndices") {
      state.raw.catalog[feature] = mergeRowsByKey(
        state.raw.catalog[feature] || [],
        payload.rows || [],
        (row) => `${row.moca_oid}|${row.moca_siid}`,
      );
      for (const siid of payload.meta?.spectral_index_siids || neededSpectralIndexIds()) {
        state.spectralIndicesLoaded.add(siid);
      }
      state.featuresLoaded[feature] = spectralIndicesReady();
    } else if (feature === "designations") {
      state.raw.catalog[feature] = mergeRowsByKey(
        state.raw.catalog[feature] || [],
        payload.rows || [],
        (row) => `${row.moca_oid}|${normalizeDesignation(row.designation)}`,
      );
      state.featuresLoaded[feature] = true;
    } else {
      state.raw.catalog[feature] = payload.rows || [];
      state.featuresLoaded[feature] = true;
    }
    state.maps = buildMaps(state.raw.catalog);
    const changedX = refreshAxisValueControls("x");
    const changedY = refreshAxisValueControls("y");
    if (changedX || changedY || currentAxesUseFeature(feature)) requestInitialAxisRange();
    setStatus(`${(payload.meta?.row_count || 0).toLocaleString()} ${labels[feature]} rows loaded`);
    shouldRender = true;
  } finally {
    delete state.featureLoads[feature];
    setPlotLoading(feature, false);
    if (shouldRender) scheduleFreshRenderAfterDataLoad(token);
  }
}

function scheduleFreshRenderAfterDataLoad(token) {
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      if (token !== state.loadToken) return;
      state.forceFreshPlot = true;
      render();
    });
  });
}

function mergeRowsByKey(existing, incoming, keyFn) {
  const rows = new Map();
  for (const row of existing) rows.set(keyFn(row), row);
  for (const row of incoming) rows.set(keyFn(row), row);
  return [...rows.values()];
}

function setStatus(text, isError = false) {
  el.status.textContent = text;
  el.status.classList.toggle("error", isError);
  el.status.classList.toggle("loading", !isError && text.startsWith("Loading"));
}

function setPlotLoading(reason, isLoading) {
  if (!reason) return;
  if (isLoading) {
    state.plotLoadReasons.add(reason);
  } else {
    state.plotLoadReasons.delete(reason);
  }
  el["plot-loader"]?.classList.toggle("is-visible", state.plotLoadReasons.size > 0);
}

function hasActiveDataLoads(except = []) {
  const ignored = new Set(except);
  return Object.keys(state.featureLoads).some((key) => !ignored.has(key));
}

function buildMaps(catalog) {
  const objectByOid = new Map();
  const distanceByOid = new Map();
  const photometryByOid = new Map();
  const simplePhotometryByOid = new Map();
  const designationsByOid = new Map();
  const oidsByDesignation = new Map();
  const designationRows = [];
  const spectrumSpecidsByOid = new Map();
  const spectralIndexByOid = new Map();
  const equivalentWidthByOid = new Map();
  const ageByOid = new Map();

  for (const object of catalog.objects || []) {
    objectByOid.set(Number(object.moca_oid), object);
  }
  for (const distance of catalog.distances || []) {
    const oid = Number(distance.moca_oid);
    if (!distanceByOid.has(oid)) distanceByOid.set(oid, []);
    distanceByOid.get(oid).push(distance);
  }
  for (const rows of distanceByOid.values()) {
    rows.sort((a, b) => Number(a.photometric_estimate || 0) - Number(b.photometric_estimate || 0));
  }
  addNestedRows(photometryByOid, catalog.photometry || [], "moca_psid");
  addSimplePhotometryRows(simplePhotometryByOid, catalog.photometry || []);
  addSpectrumRows(spectrumSpecidsByOid, catalog.spectra || []);
  addDesignationRows(designationsByOid, oidsByDesignation, designationRows, catalog.designations || []);
  addNestedRows(spectralIndexByOid, catalog.spectralIndices || [], "moca_siid");
  addNestedRows(equivalentWidthByOid, catalog.equivalentWidths || [], "moca_spid");
  for (const age of catalog.ages || []) {
    ageByOid.set(Number(age.moca_oid), Number(age.age_myr));
  }

  return {
    objectByOid,
    distanceByOid,
    photometryByOid,
    simplePhotometryByOid,
    designationsByOid,
    oidsByDesignation,
    designationRows,
    spectrumSpecidsByOid,
    spectralIndexByOid,
    equivalentWidthByOid,
    ageByOid,
  };
}

function addSpectrumRows(target, rows) {
  for (const row of rows) {
    const oid = Number(row.moca_oid);
    const specid = normalizedMocaSpecid(row.moca_specid);
    if (!Number.isFinite(oid) || !specid) continue;
    if (!target.has(oid)) target.set(oid, []);
    const specids = target.get(oid);
    if (!specids.includes(specid)) specids.push(specid);
  }
  for (const specids of target.values()) {
    specids.sort((a, b) => Number(a) - Number(b));
  }
}

function addSimplePhotometryRows(target, rows) {
  for (const row of rows) {
    if (Number(row.adopted_simpleband || 0) !== 1 || !row.system_band_simple) continue;
    const oid = Number(row.moca_oid);
    const band = normalizeSimplePhotometryBand(row.system_band_simple);
    if (!band) continue;
    if (!target.has(oid)) target.set(oid, new Map());
    if (!target.get(oid).has(band)) target.get(oid).set(band, row);
  }
}

function addDesignationRows(designationsByOid, oidsByDesignation, designationRows, rows) {
  const seenRows = new Set();
  for (const row of rows) {
    const oid = Number(row.moca_oid);
    const designation = String(row.designation || "").trim();
    const key = normalizeDesignation(designation);
    if (!Number.isFinite(oid) || !key) continue;
    if (!designationsByOid.has(oid)) designationsByOid.set(oid, []);
    if (!designationsByOid.get(oid).some((value) => normalizeDesignation(value) === key)) {
      designationsByOid.get(oid).push(designation);
    }
    if (!oidsByDesignation.has(key)) oidsByDesignation.set(key, new Set());
    oidsByDesignation.get(key).add(oid);
    const rowKey = `${key}|${oid}`;
    if (seenRows.has(rowKey)) continue;
    seenRows.add(rowKey);
    designationRows.push({
      moca_oid: oid,
      designation,
      normalized: key,
      searchable: searchableDesignation(designation),
    });
  }
  for (const values of designationsByOid.values()) {
    values.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  }
  designationRows.sort((a, b) => (
    a.designation.localeCompare(b.designation, undefined, { sensitivity: "base" }) ||
    a.moca_oid - b.moca_oid
  ));
}

function addNestedRows(target, rows, keyField) {
  for (const row of rows) {
    const oid = Number(row.moca_oid);
    if (!target.has(oid)) target.set(oid, new Map());
    target.get(oid).set(row[keyField], row);
  }
}

function dataCountBy(rows, keyField) {
  const counts = new Map();
  for (const row of rows || []) {
    const key = row[keyField];
    if (!key) continue;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return counts;
}

function ensureDesignationsLoaded() {
  if (!state.raw || state.featuresLoaded.designations || state.featureLoads.designations) return;
  loadFeature("designations");
}

function highlightedOidSet() {
  const oids = parseOidSet(el["highlight-oids"].value);
  for (const oid of selectedDesignationOids()) oids.add(oid);
  return oids;
}

function selectedDesignationOids() {
  const oids = new Set();
  if (!state.maps?.oidsByDesignation) return oids;
  for (const designation of state.selectedDesignations) {
    const matches = state.maps.oidsByDesignation.get(normalizeDesignation(designation));
    if (!matches) continue;
    for (const oid of matches) oids.add(oid);
  }
  return oids;
}

function designationSearchMatches() {
  const query = el["highlight-designation-search"]?.value || "";
  const normalizedQuery = normalizeDesignation(query);
  const searchableQuery = searchableDesignation(query);
  if (!normalizedQuery || !state.maps?.designationRows) return [];
  if (searchableQuery.length < 2) return [];
  const selected = new Set(state.selectedDesignations.map(normalizeDesignation));
  const prefix = [];
  const contains = [];
  const seen = new Set();
  for (const row of state.maps.designationRows) {
    if (selected.has(row.normalized) || seen.has(row.normalized)) continue;
    const startsWith = row.normalized.startsWith(normalizedQuery) || row.searchable.startsWith(searchableQuery);
    const containsQuery = row.normalized.includes(normalizedQuery) || row.searchable.includes(searchableQuery);
    if (!startsWith && !containsQuery) continue;
    seen.add(row.normalized);
    if (startsWith) prefix.push(row);
    else contains.push(row);
    if (prefix.length >= 40) break;
  }
  return prefix.concat(contains).slice(0, 40);
}

function renderDesignationPicker() {
  if (!el["highlight-designation-selected"] || !el["highlight-designation-results"]) return;
  el["highlight-designation-search"].placeholder = state.selectedDesignations.length
    ? "Add another"
    : "Start typing a designation";
  el["highlight-designation-selected"].innerHTML = state.selectedDesignations.map((designation) => {
    const label = selectedDesignationLabel(designation);
    return `
      <span class="designation-chip">
        <span>${escapeHtml(label)}</span>
        <button type="button" data-remove-designation="${escapeHtml(designation)}" aria-label="Remove ${escapeHtml(label)}">x</button>
      </span>
    `;
  }).join("");

  const query = el["highlight-designation-search"].value.trim();
  const active = document.activeElement === el["highlight-designation-search"] || Boolean(query);
  if (!active) {
    el["highlight-designation-results"].hidden = true;
    el["highlight-designation-results"].innerHTML = "";
    return;
  }
  if (!query) {
    el["highlight-designation-results"].hidden = true;
    el["highlight-designation-results"].innerHTML = "";
    return;
  }
  if (!state.featuresLoaded.designations) {
    el["highlight-designation-results"].hidden = false;
    el["highlight-designation-results"].innerHTML = `<div class="designation-result-note">Loading designations...</div>`;
    return;
  }
  if (searchableDesignation(query).length < 2) {
    el["highlight-designation-results"].hidden = false;
    el["highlight-designation-results"].innerHTML = `<div class="designation-result-note">Type at least 2 characters.</div>`;
    return;
  }
  const matches = designationSearchMatches();
  el["highlight-designation-results"].hidden = false;
  el["highlight-designation-results"].innerHTML = matches.length
    ? matches.map((row) => `
        <button type="button" class="designation-result" data-designation="${escapeHtml(row.designation)}">
          ${escapeHtml(row.designation)}
        </button>
      `).join("")
    : `<div class="designation-result-note">No loaded designations match.</div>`;
}

function selectedDesignationLabel(designation) {
  const key = normalizeDesignation(designation);
  const row = state.maps?.designationRows?.find((item) => item.normalized === key);
  return row?.designation || designation;
}

function selectDesignation(designation) {
  const cleaned = String(designation || "").trim();
  const key = normalizeDesignation(cleaned);
  if (!key) return;
  if (!state.selectedDesignations.some((item) => normalizeDesignation(item) === key)) {
    state.selectedDesignations.push(cleaned);
  }
  state.preservedDesignationOids = selectedDesignationOids();
  el["highlight-designation-search"].value = "";
  render();
}

function removeDesignation(designation) {
  const key = normalizeDesignation(designation);
  state.selectedDesignations = state.selectedDesignations.filter((item) => normalizeDesignation(item) !== key);
  state.preservedDesignationOids = selectedDesignationOids();
  render();
}

function refreshAxisValueControls(axis, optionsConfig = {}) {
  const type = el[`${axis}-axis-type`].value;
  const value1 = el[`${axis}-value-1`];
  const value2 = el[`${axis}-value-2`];
  const wrap1 = el[`${axis}-value-1-wrap`];
  const wrap2 = el[`${axis}-value-2-wrap`];
  const label1 = el[`${axis}-value-1-label`];
  const label2 = el[`${axis}-value-2-label`];

  let options = [];
  if (type === "color" || type === "absolute_magnitude") {
    options = photometryOptionsForCurrentMode();
  } else if (type === "spectral_index") {
    options = (state.raw?.options?.spectralIndices || [])
      .map((row) => ({
        value: row.moca_siid,
        label: `${row.description} (${row.moca_siid})`,
      }));
  } else if (type === "equivalent_width") {
    const counts = state.featuresLoaded.equivalentWidths ? dataCountBy(state.raw?.catalog?.equivalentWidths, "moca_spid") : null;
    options = (state.raw?.options?.equivalentWidths || [])
      .filter((row) => !counts || counts.has(row.moca_spid))
      .map((row) => ({
        value: row.moca_spid,
        label: `${row.description} (${row.moca_spid})`,
      }));
  }

  const old1 = value1.value;
  const old2 = value2.value;
  value1.innerHTML = options.map((item) => optionHtml(item.value, item.label)).join("");
  value2.innerHTML = options.map((item) => optionHtml(item.value, item.label)).join("");
  const default1 = preferredOptionValue(type, options, 0);
  const default2 = preferredOptionValue(type, options, 1);
  value1.value = optionsConfig.preferDefaults
    ? default1
    : (options.some((item) => item.value === old1) ? old1 : default1);
  value2.value = optionsConfig.preferDefaults
    ? default2
    : (options.some((item) => item.value === old2) ? old2 : default2);
  const changed = value1.value !== old1 || value2.value !== old2;

  const needsOne = ["color", "absolute_magnitude", "spectral_index", "equivalent_width"].includes(type);
  label1.textContent = type === "color" ? "Quantity 1" : "Quantity";
  label2.textContent = "Quantity 2";
  wrap1.style.display = needsOne && options.length ? "block" : "none";
  wrap2.style.display = type === "color" && options.length > 1 ? "block" : "none";
  return changed;
}

function preferredOptionValue(type, options, fallbackIndex = 0) {
  if (type === "color") {
    const preferred = fallbackIndex === 1 ? defaultPhotometryValue("K") : defaultPhotometryValue("J");
    const match = options.find((item) => item.value === preferred);
    if (match) return match.value;
  } else if (type === "absolute_magnitude") {
    const mkoJ = options.find((item) => item.value === defaultPhotometryValue("J"));
    if (mkoJ) return mkoJ.value;
  } else if (type === "spectral_index") {
    const hcont = options.find((item) => item.value === "hcont" || /h-?cont/i.test(item.label));
    if (hcont) return hcont.value;
  } else if (type === "equivalent_width") {
    const sodium1138 = options.find((item) => {
      const normalized = normalizeOptionText(`${item.label} ${item.value}`);
      return normalized.includes("na1138") || normalized.includes("nai1138");
    });
    if (sodium1138) return sodium1138.value;
  }
  return options[fallbackIndex]?.value || "";
}

function defaultPhotometryValue(simpleBand) {
  if (useAdvancedPhotometrySystems()) {
    if (simpleBand === "K") return "mko_kmag";
    if (simpleBand === "H") return "mko_hmag";
    return "mko_jmag";
  }
  return simplePhotometryValue(simpleBand);
}

function photometryOptionsForCurrentMode() {
  if (useAdvancedPhotometrySystems()) {
    return (state.raw?.options?.photometry || [])
      .filter((row) => row.n_data === undefined || Number(row.n_data) > 0)
      .map((row) => ({
        value: row.moca_psid,
        label: `${row.name} (${row.moca_psid})`,
      }));
  }
  const rows = state.raw?.options?.simplePhotometry || simplePhotometryBands.map((band) => ({
    value: simplePhotometryValue(band),
    system_band_simple: band,
    label: band,
  }));
  return rows
    .filter((row) => normalizeSimplePhotometryBand(row.system_band_simple) || simplePhotometryBand(row.value))
    .filter((row) => row.n_data === undefined || Number(row.n_data) > 0)
    .map((row) => {
      const band = normalizeSimplePhotometryBand(row.system_band_simple) || simplePhotometryBand(row.value);
      return {
        value: simplePhotometryValue(band),
        label: simplePhotometryLabel(band),
      };
    });
}

function simplePhotometryValue(band) {
  return `${simplePhotometryPrefix}${normalizeSimplePhotometryBand(band) || band}`;
}

function simplePhotometryBand(value) {
  const raw = String(value || "");
  if (!raw.startsWith(simplePhotometryPrefix)) return "";
  return normalizeSimplePhotometryBand(raw.slice(simplePhotometryPrefix.length)) || "";
}

function isSimplePhotometryValue(value) {
  return Boolean(simplePhotometryBand(value));
}

function simplePhotometryLabel(band) {
  return String(normalizeSimplePhotometryBand(band) || band || "");
}

function normalizeSimplePhotometryBand(value) {
  const aliases = new Map(simplePhotometryBands.map((band) => [band.toLowerCase(), band]));
  return aliases.get(String(value || "").trim().toLowerCase()) || "";
}

function normalizeOptionText(text) {
  return String(text || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function applyAxisDefaults(params) {
  const defaults = [
    ["x", "xaxis_value_1", defaultPhotometryValue("J")],
    ["x", "xaxis_value_2", defaultPhotometryValue("K")],
    ["y", "yaxis_value_1", defaultPhotometryValue("J")],
    ["y", "yaxis_value_2", defaultPhotometryValue("K")],
  ];
  for (const [axis, paramName, fallback] of defaults) {
    const field = paramName.endsWith("_2") ? `${axis}-value-2` : `${axis}-value-1`;
    const wanted = params.get(paramName) || fallback;
    if ([...el[field].options].some((option) => option.value === wanted)) {
      el[field].value = wanted;
    }
  }
}

function optionHtml(value, label) {
  return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
}

function render() {
  updateUrlFromControls();
  if (!state.raw || !state.maps) return;
  if (applyAxisErrorDefaults()) requestInitialAxisRange();
  if (deferRenderUntilPhotometricDistancesLoaded()) return;
  if (deferRenderUntilAgesLoaded()) return;
  const rows = buildRows();
  state.allRows = rows;
  const plottedRows = legendFilteredRows(rows);
  state.rows = plottedRows;
  state.selectedOids = state.selectedOids.filter((oid) => plottedRows.some((row) => row.moca_oid === oid));
  const rangeSignature = axisRangeSignature();
  if (!state.pendingInitialAxisRange && rangeSignature !== state.lastAppliedAxisRangeSignature) {
    requestInitialAxisRange();
  }
  const plotRanges = drawPlot(rows, plottedRows, {
    keepPendingInitialRange: hasPendingCriticalPlotData(),
    rangeSignature,
  });
  renderTable(state.selectedOids);
  renderDesignationPicker();
  renderMissingHighlightedOids(rows);
  renderCountSummary(plottedRows, plotRanges);
  renderPlotHint();
  schedulePlotResize();
  ensureNeededFeatures();
}

function deferRenderUntilPhotometricDistancesLoaded() {
  if (!includePhotometricDistancesForAxes() || state.photometricDistancesLoaded) return false;
  if (!state.featureLoads.distances) loadDistances();
  return true;
}

function deferRenderUntilAgesLoaded() {
  if (!el["color-by-age"].checked || state.featuresLoaded.ages) return false;
  if (!state.featureLoads.ages) loadFeature("ages");
  return true;
}

function displaySource(source) {
  return String(source || "").toLowerCase() === "mocadb" ? "MOCAdb" : String(source || "");
}

function renderCountSummary(rows, plotRanges = currentPlotRanges()) {
  const plotted = rows.length;
  const deEmphasized = rows.filter((row) => row.noisy).length;
  const outsideRange = countRowsOutsideRange(rows, plotRanges);
  const outsideText = outsideRange ? `, ${outsideRange.toLocaleString()} of which are outside the plotting range` : "";
  if (plotted > 0 && deEmphasized === plotted) {
    el["count-summary"].textContent = `${plotted.toLocaleString()} data points currently plotted and de-emphasized${outsideText}`;
  } else if (deEmphasized) {
    el["count-summary"].textContent = `${plotted.toLocaleString()} data points currently plotted, ${deEmphasized.toLocaleString()} of which are de-emphasized${outsideText}`;
  } else {
    el["count-summary"].textContent = `${plotted.toLocaleString()} data points currently plotted${outsideText}`;
  }
}

function renderPlotHint() {
  const jitterText = hasSpectralTypeAxis() ? " Spectral-type axes use ±0.3 subtype jitter." : "";
  el["plot-hint"].innerHTML = `Click a data point to open its MOCAdb report${jitterText}<br>Double-click an empty region of the plot to reset Plotly selection`;
}

function hasSpectralTypeAxis() {
  return el["x-axis-type"].value === "spectral_type" || el["y-axis-type"].value === "spectral_type";
}

function countRowsOutsideRange(rows, plotRanges) {
  const xRange = orderedRange(plotRanges?.x);
  const yRange = orderedRange(plotRanges?.y);
  if (!xRange || !yRange) return 0;
  return rows.filter((row) => (
    Number.isFinite(plotX(row)) &&
    Number.isFinite(plotY(row)) &&
    (plotX(row) < xRange[0] || plotX(row) > xRange[1] || plotY(row) < yRange[0] || plotY(row) > yRange[1])
  )).length;
}

function currentPlotRanges() {
  return {
    x: currentAxisRange("x"),
    y: currentAxisRange("y"),
  };
}

function legendFilteredRows(rows) {
  const hideClasses = !el["color-by-age"].checked;
  return rows.filter((row) => (
    (!hideClasses || !state.hiddenLegendClasses.has(row.spectral_class)) &&
    !state.hiddenLegendSamples.has(row.age_sample) &&
    (!state.hiddenLegendBinaries || !row.is_binary) &&
    (!state.hiddenLegendPhotdist || !row.is_photometric_distance)
  ));
}

function buildRows() {
  const range = parseSptRange(el["spt-range"].value);
  const highlighted = highlightedOidSet();
  const includePhotdist = includePhotometricDistancesForAxes();
  const includeBinaries = el["include-binaries"].checked;
  const includePhotspt = el["include-photspt"].checked;
  const xSpec = axisSpec("x");
  const ySpec = axisSpec("y");
  const rows = [];

  for (const object of state.raw.catalog.objects || []) {
    const oid = Number(object.moca_oid);
    const spt = Number(object.spectral_type_number);
    const isHighlighted = highlighted.has(oid);
    const binary = isBinary(object);
    const photometricSpt = Number(object.spectral_type_photometric_estimate || 0) === 1;
    if (!Number.isFinite(spt)) continue;
    if (range && (spt < range.min || spt > range.max) && !isHighlighted) continue;
    if (!includeBinaries && binary && !isHighlighted) continue;
    if (!includePhotspt && photometricSpt && !isHighlighted) continue;

    const x = axisValue(object, xSpec, includePhotdist);
    const y = axisValue(object, ySpec, includePhotdist);
    if (!x || !y || !Number.isFinite(x.value) || !Number.isFinite(y.value)) continue;

    const age = state.maps.ageByOid.get(oid);
    const ageSample = ageSampleFor(object);
    const distance = bestDistance(oid, includePhotdist);
    const row = {
      moca_oid: oid,
      designation: object.designation || "",
      spectral_type_number: spt,
      spectral_type: sptLabel(spt),
      spectral_class: normalizedSpectralClass(object.spectral_class || classFromSpt(spt)),
      complete_spectral_type: object.complete_spectral_type || sptLabel(spt),
      distance_pc: distance?.distance_pc ?? null,
      age_myr: Number.isFinite(age) ? age : null,
      age_sample: ageSample,
      is_binary: binary,
      is_photometric_spt: photometricSpt,
      is_photometric_distance: includePhotdist && Number(distance?.photometric_estimate || 0) === 1,
      x: x.value,
      y: y.value,
      plot_x: jitteredAxisValue(x.value, oid, "x", xSpec.type),
      plot_y: jitteredAxisValue(y.value, oid, "y", ySpec.type),
      ex: x.error,
      ey: y.error,
      x_label: x.label,
      y_label: y.label,
      x_ref: x.ref,
      y_ref: y.ref,
      input_data: mergeAxisInputs(x.inputs, y.inputs),
      highlighted: isHighlighted,
      noisy: isNoisy(x.error, numericValue(el["xerr-max"].value)) || isNoisy(y.error, numericValue(el["yerr-max"].value)),
    };
    row.hover = hoverText(row);
    rows.push(row);
  }
  return rows;
}

function axisSpec(axis) {
  return {
    type: el[`${axis}-axis-type`].value,
    value1: el[`${axis}-value-1`].value,
    value2: el[`${axis}-value-2`].value,
  };
}

function axisValue(object, spec, includePhotdist) {
  const oid = Number(object.moca_oid);
  if (spec.type === "spectral_type") {
    return {
      value: Number(object.spectral_type_number),
      error: numericValue(object.spectral_type_unc),
      label: "Spectral Type",
      ref: object.spt_ref || "",
      inputs: [{
        key: "spectral_type",
        label: "Spectral type number",
        value: Number(object.spectral_type_number),
        error: numericValue(object.spectral_type_unc),
      }],
    };
  }
  if (spec.type === "color") {
    const phot1 = photometryForAxisValue(oid, spec.value1);
    const phot2 = photometryForAxisValue(oid, spec.value2);
    if (!phot1 || !phot2 || spec.value1 === spec.value2) return null;
    return {
      value: Number(phot1.magnitude) - Number(phot2.magnitude),
      error: hypot(phot1.magnitude_unc, phot2.magnitude_unc),
      label: `${bandAxisLabel(phot1, spec.value1)} \u2212 ${bandAxisLabel(phot2, spec.value2)}`,
      ref: `${phot1.photometry_ref || ""}; ${phot2.photometry_ref || ""}`,
      inputs: [
        photometryInput(phot1, spec.value1),
        photometryInput(phot2, spec.value2),
      ],
    };
  }
  if (spec.type === "absolute_magnitude") {
    const phot = photometryForAxisValue(oid, spec.value1);
    const dist = bestDistance(oid, includePhotdist);
    if (!phot || !dist || dist.dmod === null || dist.dmod === undefined) return null;
    return {
      value: Number(phot.magnitude) - Number(dist.dmod),
      error: hypot(phot.magnitude_unc, dist.dmod_unc),
      label: `Absolute ${bandAxisLabel(phot, spec.value1)}-band magnitude (mag)`,
      ref: `${phot.photometry_ref || ""}; ${dist.distance_ref || ""}`,
      inputs: [
        photometryInput(phot, spec.value1),
        distanceInput(dist),
      ],
    };
  }
  if (spec.type === "spectral_index") {
    const row = state.maps.spectralIndexByOid.get(oid)?.get(spec.value1);
    if (!row) return null;
    return {
      value: Number(row.index_value),
      error: numericValue(row.index_value_unc),
      label: row.description || spec.value1,
      ref: row.spectral_index_ref || "",
      inputs: [{
        key: `spectral_index:${row.moca_siid}`,
        label: row.description || spec.value1,
        value: Number(row.index_value),
        error: numericValue(row.index_value_unc),
        moca_specid: normalizedMocaSpecid(row.moca_specid),
      }],
    };
  }
  if (spec.type === "equivalent_width") {
    const row = state.maps.equivalentWidthByOid.get(oid)?.get(spec.value1);
    if (!row) return null;
    const scale = spec.value1 === "li" ? 1000 : 1;
    const unit = spec.value1 === "li" ? "mÅ" : "Å";
    return {
      value: Number(row.ew_angstrom) * scale,
      error: numericValue(row.ew_angstrom_unc) * scale,
      label: `${row.description || spec.value1} (${unit})`,
      ref: row.equivalent_width_ref || "",
      inputs: [{
        key: `equivalent_width:${row.moca_spid}`,
        label: row.description || spec.value1,
        value: Number(row.ew_angstrom) * scale,
        error: numericValue(row.ew_angstrom_unc) * scale,
        unit,
        moca_specid: normalizedMocaSpecid(row.moca_specid),
      }],
    };
  }
  return null;
}

function photometryInput(row, fallbackId) {
  const simpleBand = simplePhotometryBand(fallbackId);
  const key = simpleBand
    ? `photometry:simple:${simpleBand}`
    : `photometry:${row.moca_psid || fallbackId}`;
  return {
    key,
    label: bandAxisLabel(row, fallbackId),
    value: Number(row.magnitude),
    error: numericValue(row.magnitude_unc),
    unit: "mag",
  };
}

function distanceInput(row) {
  return {
    key: "distance_pc",
    label: "Distance",
    value: Number(row.distance_pc),
    error: numericValue(row.distance_pc_unc),
    unit: "pc",
  };
}

function mergeAxisInputs(...inputLists) {
  const out = [];
  const seen = new Set();
  for (const input of inputLists.flat()) {
    if (!input?.key || seen.has(input.key)) continue;
    seen.add(input.key);
    out.push(input);
  }
  return out;
}

function photometryForAxisValue(oid, value) {
  const simpleBand = simplePhotometryBand(value);
  if (simpleBand) return state.maps.simplePhotometryByOid.get(oid)?.get(simpleBand);
  return state.maps.photometryByOid.get(oid)?.get(value);
}

function jitteredAxisValue(value, oid, axis, axisType) {
  if (axisType !== "spectral_type") return value;
  return value + deterministicJitter(oid, axis);
}

function deterministicJitter(oid, axis) {
  const seed = `${oid}:${axis}:spectral-type-jitter`;
  let hash = 2166136261;
  for (let index = 0; index < seed.length; index += 1) {
    hash ^= seed.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  const unit = (hash >>> 0) / 4294967295;
  return (unit * 2 - 1) * spectralTypeJitterAmplitude;
}

function plotX(row) {
  return Number.isFinite(row.plot_x) ? row.plot_x : row.x;
}

function plotY(row) {
  return Number.isFinite(row.plot_y) ? row.plot_y : row.y;
}

function bandAxisLabel(photometryRow, fallbackId) {
  const simpleBand = photometryRow?.system_band_simple || simplePhotometryBand(fallbackId);
  if (simpleBand) return italicBandAxisLabel(simplePhotometryLabel(simpleBand));
  const raw = String(photometryRow?.name || fallbackId || "");
  const lower = `${raw} ${fallbackId || ""}`.toLowerCase();
  if (/(^|[^a-z])ks([^a-z]|$)|ksmag|k_s/.test(lower)) return "<i>K</i><sub>S</sub>";
  if (/(^|[^a-z])j([^a-z]|$)|jmag/.test(lower)) return "<i>J</i>";
  if (/(^|[^a-z])h([^a-z]|$)|hmag/.test(lower)) return "<i>H</i>";
  if (/(^|[^a-z])k([^a-z]|$)|kmag/.test(lower)) return "<i>K</i>";
  if (/(^|[^a-z])g([^a-z]|$)|gmag/.test(lower)) return "<i>g</i>";
  if (/(^|[^a-z])r([^a-z]|$)|rmag/.test(lower)) return "<i>r</i>";
  if (/(^|[^a-z])i([^a-z]|$)|imag/.test(lower)) return "<i>i</i>";
  if (/(^|[^a-z])z([^a-z]|$)|zmag/.test(lower)) return "<i>z</i>";
  if (/(^|[^a-z])y([^a-z]|$)|ymag/.test(lower)) return "<i>y</i>";
  if (/(^|[^a-z])l([^a-z]|$)|lmag/.test(lower)) return "<i>L</i>";
  if (/(^|[^a-z])m([^a-z]|$)|mmag/.test(lower)) return "<i>M</i>";
  const wMatch = lower.match(/(?:^|[^a-z0-9])w([1-4])(?:[^a-z0-9]|$)|wise[_ -]?w([1-4])/);
  if (wMatch) return `<i>W</i>${wMatch[1] || wMatch[2]}`;
  return escapeHtml(raw);
}

function italicBandAxisLabel(label) {
  const text = String(label || "");
  const match = text.match(/^([A-Za-z])([0-9]*)$/);
  if (!match) return escapeHtml(text);
  const [, band, suffix] = match;
  const italicBands = new Set(["J", "H", "K", "L", "M", "g", "r", "i", "z", "y"]);
  return italicBands.has(band) ? `<i>${escapeHtml(band)}</i>${escapeHtml(suffix)}` : escapeHtml(text);
}

function bestDistance(oid, includePhotdist) {
  const rows = state.maps.distanceByOid.get(Number(oid)) || [];
  if (includePhotdist) return rows[0] || null;
  return rows.find((row) => Number(row.photometric_estimate || 0) !== 1) || null;
}

function isBinary(object) {
  const text = String(object.all_prop_confidences || "");
  return text.includes("multiple_system:C") || text.includes("multiple_system:Y");
}

function ageSampleFor(object) {
  const gravity = String(object.gravity_class || "").toLowerCase();
  const suffix = String(object.suffix || "").toLowerCase();
  const complete = String(object.complete_spectral_type || "").toLowerCase();
  const lowGravityTokens = ["vl-g", "int-g", "low", "red", "gamma", "beta", "delta", "\u03b3", "\u03b2", "\u03b4"];
  if (lowGravityTokens.some((token) => gravity.includes(token) || suffix.includes(token) || complete.includes(token))) {
    return "low_gravity";
  }
  if (
    suffix.startsWith("sd") ||
    suffix.startsWith("esd") ||
    suffix.startsWith("d/sd") ||
    suffix.includes("blue") ||
    complete.startsWith("sd") ||
    complete.startsWith("esd") ||
    complete.startsWith("d/sd") ||
    complete.includes("blue")
  ) {
    return "subdwarf";
  }
  return "field";
}

function drawPlot(rows, plottedRows = legendFilteredRows(rows), options = {}) {
  const renderToken = ++state.plotRenderToken;
  const rangeSignature = options.rangeSignature || axisRangeSignature();
  const xLabel = plottedRows[0]?.x_label || rows[0]?.x_label || axisTypes.find((item) => item.value === el["x-axis-type"].value)?.label || "X";
  const yLabel = plottedRows[0]?.y_label || rows[0]?.y_label || axisTypes.find((item) => item.value === el["y-axis-type"].value)?.label || "Y";
  const regularRows = plottedRows.filter((row) => !row.highlighted);
  const highlightedRows = plottedRows.filter((row) => row.highlighted);
  const legendRows = rows;
  const pointOpacity = opacityForCount(regularRows.filter((row) => !row.noisy).length);
  const wantsInitialRange = state.pendingInitialAxisRange;
  const rangeRows = automaticRangeRows(plottedRows);
  const candidateInitialRanges = wantsInitialRange ? {
    x: percentileRange(rangeRows, "x"),
    y: percentileRange(rangeRows, "y"),
  } : { x: null, y: null };
  const appliesInitialRange = Boolean(candidateInitialRanges.x && candidateInitialRanges.y);
  const currentRanges = appliesInitialRange ? { x: null, y: null } : currentPlotRanges();
  const layoutRanges = {
    x: appliesInitialRange ? candidateInitialRanges.x : currentRanges.x,
    y: appliesInitialRange ? candidateInitialRanges.y : currentRanges.y,
  };
  const densityRanges = densityPlotRanges(plottedRows, layoutRanges);
  const summaryRanges = {
    x: orderedRange(layoutRanges.x),
    y: orderedRange(layoutRanges.y),
  };
  const opacityByOid = localOpacityMap(regularRows, pointOpacity, densityRanges);
  const nextRangeRevision = appliesInitialRange ? state.axisRangeRevision + 1 : state.axisRangeRevision;
  if (appliesInitialRange) {
    state.axisRangeRevision = nextRangeRevision;
  }
  const traces = [];

  if (el["color-by-age"].checked) {
    traces.push(...ageColorTraces(regularRows, opacityByOid, pointOpacity));
  } else {
    const good = regularRows.filter((row) => !row.noisy);
    traces.push(errorBarTrace(good, 0.2, "default-good-errors"));
    traces.push(defaultTrace(good, "Objects", rowOpacities(good, opacityByOid, pointOpacity)));
    const noisy = regularRows.filter((row) => row.noisy);
    if (noisy.length) {
      traces.push(errorBarTrace(noisy, 0.11, "default-noisy-errors"));
      traces.push(defaultTrace(noisy, "Filtered by error", mutedRowOpacities(noisy, opacityByOid, pointOpacity), false));
    }
    traces.push(...legendTraces(legendRows));
  }
  traces.push(...sampleLegendTraces(legendRows));
  traces.push(...binaryLegendTraces(legendRows));
  traces.push(...photometricDistanceLegendTraces(legendRows));
  traces.push(...photometricSptLegendTraces(legendRows));

  traces.push(...medianColorTraces());
  traces.push(...sequenceTraces());
  traces.push(...binaryOverlayTraces(regularRows, opacityByOid, pointOpacity));

  if (highlightedRows.length) {
    traces.push(...highlightedPointTraces(highlightedRows));
  }

  const plotSize = syncPlotGeometry();
  const layout = {
    autosize: false,
    width: plotSize?.width,
    height: plotSize?.height,
    margin: plotMargins(),
    paper_bgcolor: "#f0f1f0",
    plot_bgcolor: "#ffffff",
    xaxis: axisLayout("x", xLabel, rows, layoutRanges.x),
    yaxis: axisLayout("y", yLabel, rows, layoutRanges.y),
    legend: {
      orientation: "v",
      bgcolor: "rgba(255,255,255,0.7)",
      bordercolor: "#d7ddda",
      borderwidth: 1,
      x: 1.02,
      y: 1,
    },
    dragmode: "select",
    hovermode: "closest",
    uirevision: `bd-colors-fast-${nextRangeRevision}`,
  };

  const plotCanvasKey = currentPlotCanvasKey();
  const forceFreshPlot = state.forceFreshPlot && el.plot?._fullLayout;
  const plotCanvasChanged = state.plotCanvasKey && state.plotCanvasKey !== plotCanvasKey && el.plot?._fullLayout;
  if (plotCanvasChanged || forceFreshPlot) {
    Plotly.purge(el.plot);
    state.plotBound = false;
  }
  state.forceFreshPlot = false;
  state.plotCanvasKey = plotCanvasKey;

  const plotConfig = {
    responsive: false,
    displaylogo: false,
    displayModeBar: true,
    toImageButtonOptions: { format: "png", width: 900, height: 700, scale: 3 },
  };
  const shouldCreateNewPlot = plotCanvasChanged || forceFreshPlot || !el.plot?._fullLayout;
  const plotPromise = shouldCreateNewPlot
    ? Plotly.newPlot(el.plot, traces.filter(Boolean), layout, plotConfig)
    : Plotly.react(el.plot, traces.filter(Boolean), layout, plotConfig);
  plotPromise.then(() => {
    bindPlotEvents();
    schedulePlotResize();
    if (renderToken === state.plotRenderToken && appliesInitialRange && !options.keepPendingInitialRange) {
      state.pendingInitialAxisRange = false;
      state.lastAppliedAxisRangeSignature = rangeSignature;
    }
  });
  return summaryRanges;
}

function currentPlotCanvasKey() {
  const axes = ["x", "y"].map((axis) => {
    const spec = axisSpec(axis);
    return [axis, spec.type, spec.value1 || "", spec.value2 || ""].join(":");
  }).join("|");
  return [
    el["color-by-age"].checked ? "age-color" : "class-color",
    includePhotometricDistancesForAxes() ? "photdist" : "spectrodist",
    el["include-binaries"].checked ? "binaries" : "singles",
    el["include-photspt"].checked ? "photspt" : "spectrospt",
    axes,
  ].join("|");
}

function plotMargins() {
  return {
    l: 78,
    r: 28,
    t: 34,
    b: 86,
  };
}

function syncPlotGeometry() {
  const frame = el.plot?.parentElement;
  const visualArea = el["visual-area"];
  if (!frame || !visualArea) return null;

  const visualRect = visualArea.getBoundingClientRect();
  const toolbar = document.querySelector(".table-toolbar");
  const toolbarHeight = toolbar?.getBoundingClientRect().height || 104;
  const style = getComputedStyle(visualArea);
  const rowGap = Number.parseFloat(style.rowGap) || 0;
  const minSelectionHeight = window.matchMedia("(max-width: 820px)").matches ? 120 : 92;
  const availableWidth = Math.max(320, visualArea.clientWidth);
  const availableHeight = Math.max(
    minPlotHeight,
    window.innerHeight - visualRect.top - toolbarHeight - minSelectionHeight - rowGap * 2,
  );
  const height = Math.round(Math.max(minPlotHeight, Math.min(availableWidth / plotAspectRatio, availableHeight)));
  const width = Math.round(Math.min(availableWidth, height * plotAspectRatio));

  frame.style.width = `${width}px`;
  frame.style.height = `${height}px`;
  return { width, height };
}

function schedulePlotResize() {
  if (!el.plot) return;
  if (state.plotResizeFrame) cancelAnimationFrame(state.plotResizeFrame);
  state.plotResizeFrame = requestAnimationFrame(() => {
    state.plotResizeFrame = null;
    resizePlotToGeometry();
  });
}

function resizePlotToGeometry() {
  const plotSize = syncPlotGeometry();
  if (!plotSize || !el.plot?._fullLayout) return;
  Plotly.relayout(el.plot, {
    autosize: false,
    width: plotSize.width,
    height: plotSize.height,
  });
}

function installPlotResizeObserver() {
  if (!("ResizeObserver" in window) || !el["visual-area"]) return;
  state.plotResizeObserver = new ResizeObserver(schedulePlotResize);
  state.plotResizeObserver.observe(el["visual-area"]);
  const toolbar = document.querySelector(".table-toolbar");
  if (toolbar) state.plotResizeObserver.observe(toolbar);
}

function hasPendingCriticalPlotData() {
  if (includePhotometricDistancesForAxes() && !state.photometricDistancesLoaded) return true;
  if (neededPhotometryPsids().some((psid) => !state.photometryLoaded.has(psid))) return true;
  for (const axis of ["x", "y"]) {
    const type = el[`${axis}-axis-type`].value;
    if (type === "spectral_index" && !state.spectralIndicesLoaded.has(el[`${axis}-value-1`].value)) return true;
    if (type === "equivalent_width" && !state.featuresLoaded.equivalentWidths) return true;
  }
  return false;
}

function neededSpectralIndexIds() {
  const ids = [];
  for (const axis of ["x", "y"]) {
    if (el[`${axis}-axis-type`].value === "spectral_index") ids.push(el[`${axis}-value-1`].value);
  }
  return [...new Set(ids.filter(Boolean))];
}

function spectralIndicesReady() {
  const needed = neededSpectralIndexIds();
  return needed.length > 0 && needed.every((siid) => state.spectralIndicesLoaded.has(siid));
}

function currentAxesUseFeature(feature) {
  const featureTypes = {
    spectralIndices: "spectral_index",
    equivalentWidths: "equivalent_width",
  };
  const axisType = featureTypes[feature];
  return Boolean(axisType && ["x", "y"].some((axis) => el[`${axis}-axis-type`].value === axisType));
}

function axisRangeSignature() {
  return ["x", "y"].map((axis) => {
    const spec = axisSpec(axis);
    return [
      axis,
      spec.type,
      spec.value1 || "",
      spec.value2 || "",
      el[`${axis}err-max`].value || "",
      axisDataReadySignature(spec),
    ].join(":");
  }).join("|");
}

function axisDataReadySignature(spec) {
  if (spec.type === "spectral_index") return state.spectralIndicesLoaded.has(spec.value1) ? `loaded:${spec.value1}` : `loading:${spec.value1}`;
  if (spec.type === "equivalent_width") return state.featuresLoaded.equivalentWidths ? "loaded" : "loading";
  if (spec.type === "absolute_magnitude") {
    const photometryReady = state.photometryLoaded.has(spec.value1) ? "phot-loaded" : "phot-loading";
    const distanceReady = includePhotometricDistancesForAxes() ? (state.photometricDistancesLoaded ? "dist-loaded" : "dist-loading") : "dist-spectro";
    return `${photometryReady}:${distanceReady}`;
  }
  if (spec.type === "color") {
    const oneReady = state.photometryLoaded.has(spec.value1) ? "p1-loaded" : "p1-loading";
    const twoReady = state.photometryLoaded.has(spec.value2) ? "p2-loaded" : "p2-loading";
    return `${oneReady}:${twoReady}`;
  }
  return "ready";
}

function automaticRangeRows(rows) {
  const good = rows.filter((row) => !row.noisy);
  return errorThresholdsActive() && good.length ? good : rows;
}

function errorThresholdsActive() {
  return numericValue(el["xerr-max"].value) !== null || numericValue(el["yerr-max"].value) !== null;
}

function percentileRange(rows, field) {
  const values = rows.map((row) => Number(plotValue(row, field))).filter(Number.isFinite).sort((a, b) => a - b);
  if (!values.length) return null;
  const p2 = quantile(values, 0.02);
  const p98 = quantile(values, 0.98);
  const hasValuesOutsideCentiles = values[0] < p2 || values[values.length - 1] > p98;
  let span = p98 - p2;
  if (!Number.isFinite(span) || span <= 0) {
    const min = values[0];
    const max = values[values.length - 1];
    span = max - min;
    if (!Number.isFinite(span) || span <= 0) span = Math.max(Math.abs(p2) * 0.1, 1);
  }
  const paddingFraction = el[`${field}-axis-type`]?.value === "spectral_type"
    ? 0.05
    : (hasValuesOutsideCentiles ? 0.2 : 0.05);
  const padding = span * paddingFraction;
  return rangeWithAbsoluteMagnitudeYDwarfs([p2 - padding, p98 + padding], rows, field);
}

function rangeWithAbsoluteMagnitudeYDwarfs(range, rows, field) {
  if (el[`${field}-axis-type`]?.value !== "absolute_magnitude") return range;
  const yDwarfValues = rows
    .filter((row) => isNonDeemphasizedYDwarf(row))
    .map((row) => Number(plotValue(row, field)))
    .filter(Number.isFinite);
  if (!yDwarfValues.length) return range;

  const yMin = Math.min(...yDwarfValues);
  const yMax = Math.max(...yDwarfValues);
  const span = Math.max(range[1] - range[0], yMax - yMin, 1);
  const padding = span * yDwarfRangePaddingFraction;
  return [
    Math.min(range[0], yMin - padding),
    Math.max(range[1], yMax + padding),
  ];
}

function isNonDeemphasizedYDwarf(row) {
  if (row.noisy) return false;
  const klass = String(row.spectral_class || "").trim().toUpperCase();
  if (klass.startsWith("Y")) return true;
  const spt = Number(row.spectral_type_number);
  return Number.isFinite(spt) && spt >= 30 && spt < 40;
}

function plotValue(row, field) {
  if (field === "x") return plotX(row);
  if (field === "y") return plotY(row);
  return row[field];
}

function quantile(values, q) {
  if (values.length === 1) return values[0];
  const index = (values.length - 1) * q;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return values[lower];
  const weight = index - lower;
  return values[lower] * (1 - weight) + values[upper] * weight;
}

function opacityForCount(count) {
  if (count <= 300) return 0.94;
  if (count <= 1000) return 0.93;
  if (count <= 3000) return 0.91;
  if (count <= 8000) return 0.88;
  if (count <= 20000) return 0.82;
  return 0.74;
}

function mutedOpacityFor(opacity) {
  return Math.max(0.06, opacity * 0.18);
}

function densityPlotRanges(rows, initialRanges) {
  return {
    x: orderedRange(initialRanges.x) || currentAxisRange("x") || dataRange(rows, "x"),
    y: orderedRange(initialRanges.y) || currentAxisRange("y") || dataRange(rows, "y"),
  };
}

function currentAxisRange(axis) {
  return orderedRange(el.plot?.layout?.[`${axis}axis`]?.range);
}

function dataRange(rows, field) {
  const values = rows.map((row) => Number(plotValue(row, field))).filter(Number.isFinite);
  if (!values.length) return null;
  return [Math.min(...values), Math.max(...values)];
}

function orderedRange(range) {
  if (!Array.isArray(range) || range.length < 2) return null;
  const a = Number(range[0]);
  const b = Number(range[1]);
  if (!Number.isFinite(a) || !Number.isFinite(b) || a === b) return null;
  return [Math.min(a, b), Math.max(a, b)];
}

function localOpacityMap(rows, baseOpacity, ranges) {
  const output = new Map();
  if (!rows.length) return output;
  const xRange = orderedRange(ranges.x);
  const yRange = orderedRange(ranges.y);
  if (!xRange || !yRange) {
    rows.forEach((row) => output.set(row.moca_oid, baseOpacity));
    return output;
  }
  const xSpan = xRange[1] - xRange[0];
  const ySpan = yRange[1] - yRange[0];
  const binCount = Math.max(18, Math.min(72, Math.round(Math.sqrt(rows.length) * 1.35)));
  const densityRadius = rows.length > 500 ? 2 : 1;
  const counts = new Map();
  const bins = rows.map((row) => {
    const x = Number(plotX(row));
    const y = Number(plotY(row));
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < xRange[0] || x > xRange[1] || y < yRange[0] || y > yRange[1]) return null;
    const bx = clamp(Math.floor(((x - xRange[0]) / xSpan) * binCount), 0, binCount - 1);
    const by = clamp(Math.floor(((y - yRange[0]) / ySpan) * binCount), 0, binCount - 1);
    const key = `${bx},${by}`;
    counts.set(key, (counts.get(key) || 0) + 1);
    return [bx, by];
  });
  const densityByBin = new Map();
  const densities = bins.map((bin) => {
    if (!bin) return 0;
    const key = `${bin[0]},${bin[1]}`;
    if (!densityByBin.has(key)) densityByBin.set(key, neighborDensity(bin, counts, densityRadius));
    return densityByBin.get(key);
  });
  const visibleDensities = densities.filter((density) => density > 0).sort((a, b) => a - b);
  if (!visibleDensities.length) {
    rows.forEach((row) => output.set(row.moca_oid, baseOpacity));
    return output;
  }
  const sparseDensity = quantile(visibleDensities, 0.35);
  const denseDensity = quantile(visibleDensities, 0.95);
  const denseOpacity = denseOpacityFloor(baseOpacity, visibleDensities.length);
  rows.forEach((row, index) => {
    output.set(row.moca_oid, opacityForDensity(densities[index], sparseDensity, denseDensity, baseOpacity, denseOpacity));
  });
  return output;
}

function neighborDensity(bin, counts, radius = 1) {
  let total = 0;
  for (let dx = -radius; dx <= radius; dx += 1) {
    for (let dy = -radius; dy <= radius; dy += 1) {
      total += counts.get(`${bin[0] + dx},${bin[1] + dy}`) || 0;
    }
  }
  return total;
}

function denseOpacityFloor(baseOpacity, count) {
  let floor = 0.22;
  if (count <= 300) floor = 0.72;
  else if (count <= 1000) floor = 0.56;
  else if (count <= 3000) floor = 0.42;
  else if (count <= 8000) floor = 0.3;
  else if (count <= 20000) floor = 0.24;
  return Math.min(baseOpacity, floor);
}

function opacityForDensity(density, sparseDensity, denseDensity, baseOpacity, denseOpacity) {
  if (density <= 0 || denseDensity <= sparseDensity) return baseOpacity;
  const raw = (Math.log1p(density) - Math.log1p(sparseDensity)) / (Math.log1p(denseDensity) - Math.log1p(sparseDensity));
  const t = Math.pow(clamp(raw, 0, 1), 0.62);
  return baseOpacity - t * (baseOpacity - denseOpacity);
}

function rowOpacities(rows, opacityByOid, fallback) {
  return rows.map((row) => opacityByOid.get(row.moca_oid) ?? fallback);
}

function mutedRowOpacities(rows, opacityByOid, fallback) {
  return rows.map((row) => mutedOpacityFor(opacityByOid.get(row.moca_oid) ?? fallback));
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function defaultTrace(rows, name, opacity, showlegend = name !== "Objects") {
  if (!rows.length) return null;
  const markerLine = markerLineForRows(rows);
  return {
    type: "scattergl",
    uid: `default-${name.toLowerCase().replace(/\W+/g, "-")}`,
    mode: "markers",
    x: rows.map(plotX),
    y: rows.map(plotY),
    text: rows.map((row) => row.hover),
    customdata: rows.map((row) => row.moca_oid),
    hoverinfo: "text",
    marker: {
      size: markerSizesForRows(rows, 9),
      color: rows.map((row) => classColors[row.spectral_class] || "#1da6b8"),
      symbol: rows.map(markerSymbolForRow),
      opacity,
      ...(markerLine ? { line: markerLine } : {}),
    },
    name,
    showlegend,
  };
}

function highlightedPointTraces(rows) {
  return [
    errorBarTrace(rows, 0.2, "highlighted-errors"),
    {
      type: "scattergl",
      uid: "highlighted-halo",
      mode: "markers",
      x: rows.map(plotX),
      y: rows.map(plotY),
      customdata: rows.map((row) => row.moca_oid),
      hoverinfo: "skip",
      marker: {
        symbol: "circle",
        size: 28,
        color: "#ffffff",
        opacity: 0.94,
        line: { color: "#111", width: 1.2 },
      },
      name: "Highlighted halo",
      showlegend: false,
    },
    {
      type: "scattergl",
      uid: "highlighted-points",
      mode: "markers",
      x: rows.map(plotX),
      y: rows.map(plotY),
      text: rows.map((row) => row.hover),
      customdata: rows.map((row) => row.moca_oid),
      hoverinfo: "text",
      marker: {
        symbol: "star",
        size: 20,
        color: "#ffe66d",
        opacity: 1,
        line: { color: "#111", width: 2.5 },
      },
      name: "Highlighted",
    },
  ].filter(Boolean);
}

function binaryOverlayTraces(rows, opacityByOid, pointOpacity) {
  const binaryRows = rows.filter((row) => row.is_binary);
  if (!binaryRows.length) return [];
  const colorDomain = ageColorDomain(rows);
  const edgeColors = el["color-by-age"].checked
    ? binaryRows.map((row) => ageColorForRow(row, colorDomain))
    : binaryRows.map((row) => classColors[row.spectral_class] || "#1da6b8");
  return [{
    type: "scattergl",
    uid: "binary-overlay",
    mode: "markers",
    x: binaryRows.map(plotX),
    y: binaryRows.map(plotY),
    text: binaryRows.map((row) => row.hover),
    customdata: binaryRows.map((row) => row.moca_oid),
    hoverinfo: "text",
    marker: {
      size: markerSizesForRows(binaryRows, 9),
      color: edgeColors,
      symbol: binaryRows.map(binaryOverlaySymbolForRow),
      opacity: displayRowOpacities(binaryRows, opacityByOid, pointOpacity),
      line: { color: edgeColors, width: 2 },
    },
    name: "Binaries",
    showlegend: false,
  }];
}

function binaryOverlaySymbolForRow(row) {
  return openMarkerSymbol(sampleSymbols[row.age_sample] || "circle");
}

function markerSizesForRows(rows, baseSize) {
  // Array sizes keep scattergl on the antialiased marker path even when sizes match.
  return rows.map((row) => row.is_photometric_distance ? baseSize * 0.8 : baseSize);
}

function ageColorTraces(rows, opacityByOid, pointOpacity) {
  const traces = [];
  const noAge = rows.filter((row) => !Number.isFinite(row.age_myr) || row.age_myr <= 0);
  const withAge = rows.filter((row) => Number.isFinite(row.age_myr) && row.age_myr > 0);
  const colorDomain = ageColorDomain(rows);
  if (noAge.length) {
    traces.push(errorBarTrace(noAge, 0.1, "age-no-age-errors"));
    for (const group of markerStyleGroups(noAge)) {
      const marker = {
        size: markerSizeForRow(group.rows[0], 7),
        color: noAgeMarkerColor,
        symbol: group.symbol,
        opacity: noAgeOpacityForGroup(group, pointOpacity),
      };
      if (group.photometricSpt) {
        marker.line = { color: photometricSptEdgeColor, width: photometricSptEdgeWidth };
      }
      traces.push({
        type: "scattergl",
        uid: `age-no-age-${group.key}`,
        mode: "markers",
        x: group.rows.map(plotX),
        y: group.rows.map(plotY),
        ids: group.rows.map((row) => `no-age-${row.moca_oid}`),
        text: group.rows.map((row) => row.hover),
        customdata: group.rows.map((row) => row.moca_oid),
        hoverinfo: "text",
        marker,
        name: "No age",
        showlegend: false,
      });
    }
  }
  if (withAge.length) {
    const markerLine = markerLineForRows(withAge);
    traces.push(errorBarTrace(withAge, 0.2, "age-with-age-errors"));
    traces.push({
      type: "scattergl",
      uid: "age-with-age",
      mode: "markers",
      x: withAge.map(plotX),
      y: withAge.map(plotY),
      ids: withAge.map((row) => `with-age-${row.moca_oid}`),
      text: withAge.map((row) => row.hover),
      customdata: withAge.map((row) => row.moca_oid),
      hoverinfo: "text",
      marker: {
        size: markerSizesForRows(withAge, 9),
        color: withAge.map((row) => Math.log10(row.age_myr)),
        colorscale: ageColorscale,
        reversescale: false,
        ...(colorDomain ? { cmin: colorDomain.min, cmax: colorDomain.max } : {}),
        showscale: true,
        colorbar: ageColorbar(withAge),
        symbol: withAge.map(markerSymbolForRow),
        opacity: displayRowOpacities(withAge, opacityByOid, pointOpacity),
        ...(markerLine ? { line: markerLine } : {}),
      },
      name: "Age",
      showlegend: false,
    });
  }
  return traces;
}

function markerSymbolForRow(row) {
  const symbol = sampleSymbols[row.age_sample] || "circle";
  return row.is_binary ? openMarkerSymbol(symbol) : symbol;
}

function openMarkerSymbol(symbol) {
  return String(symbol || "circle").endsWith("-open") ? symbol : `${symbol}-open`;
}

function markerLineForRows(rows) {
  if (!rows.some((row) => row.is_photometric_spt)) return null;
  return {
    color: rows.map((row) => row.is_photometric_spt ? photometricSptEdgeColor : "rgba(0,0,0,0)"),
    width: rows.map((row) => row.is_photometric_spt ? photometricSptEdgeWidth : 0),
  };
}

function markerStyleGroups(rows) {
  const groups = new Map();
  for (const row of rows) {
    const symbol = markerSymbolForRow(row);
    const photometricSpt = Boolean(row.is_photometric_spt);
    const photometricDistance = Boolean(row.is_photometric_distance);
    const noisy = Boolean(row.noisy);
    const key = [
      symbol,
      photometricSpt ? "photspt" : "spt",
      photometricDistance ? "photdist" : "distance",
      noisy ? "noisy" : "clean",
    ].join("-");
    if (!groups.has(key)) {
      groups.set(key, { key, symbol, photometricSpt, photometricDistance, noisy, rows: [] });
    }
    groups.get(key).rows.push(row);
  }
  return [...groups.values()];
}

function markerSizeForRow(row, baseSize) {
  return row.is_photometric_distance ? baseSize * 0.8 : baseSize;
}

function noAgeOpacityForGroup(group, fallback) {
  const opacity = Math.min(fallback, 0.72);
  if (group.noisy) return clamp(opacity * 0.55, 0.08, 0.14);
  return clamp(opacity * 0.55, 0.28, 0.46);
}

function ageColorDomain(rows) {
  const values = rows
    .map((row) => Number(row.age_myr))
    .filter((age) => Number.isFinite(age) && age > 0)
    .map((age) => Math.log10(age));
  if (!values.length) return null;
  values.push(0, 3);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 0.5;
    max += 0.5;
  }
  return { min, max };
}

function ageColorForRow(row, domain) {
  const age = Number(row.age_myr);
  if (!domain || !Number.isFinite(age) || age <= 0) return noAgeMarkerColor;
  const t = clamp((Math.log10(age) - domain.min) / (domain.max - domain.min), 0, 1);
  return interpolateColorscale(ageColorscale, t);
}

function interpolateColorscale(colorscale, t) {
  for (let index = 1; index < colorscale.length; index += 1) {
    const [rightStop, rightColor] = colorscale[index];
    const [leftStop, leftColor] = colorscale[index - 1];
    if (t <= rightStop) {
      const localT = rightStop === leftStop ? 0 : (t - leftStop) / (rightStop - leftStop);
      return interpolateRgb(parseRgb(leftColor), parseRgb(rightColor), localT);
    }
  }
  return colorscale[colorscale.length - 1][1];
}

function parseRgb(color) {
  const match = String(color).match(/^rgb\((\d+),(\d+),(\d+)\)$/);
  return match ? match.slice(1).map(Number) : [141, 141, 141];
}

function interpolateRgb(left, right, t) {
  const values = left.map((value, index) => Math.round(value + (right[index] - value) * t));
  return `rgb(${values[0]},${values[1]},${values[2]})`;
}

function displayRowOpacities(rows, opacityByOid, fallback) {
  return rows.map((row) => {
    const opacity = opacityByOid.get(row.moca_oid) ?? fallback;
    return row.noisy ? mutedOpacityFor(opacity) : opacity;
  });
}

function noAgeBackgroundOpacities(rows, opacityByOid, fallback) {
  return rows.map((row) => {
    const opacity = opacityByOid.get(row.moca_oid) ?? fallback;
    if (row.noisy) return clamp(opacity * 0.55, 0.08, 0.14);
    return clamp(opacity * 0.55, 0.24, 0.46);
  });
}

function ageColorbar(rows) {
  const ages = rows.map((row) => Number(row.age_myr)).filter((age) => Number.isFinite(age) && age > 0);
  let length = ageColorbarLength;
  if (el["include-binaries"].checked) length *= ageColorbarBinaryLengthMultiplier;
  if (includePhotometricDistancesForAxes()) length *= ageColorbarPhotdistLengthMultiplier;
  if (includePhotometricDistancesForAxes() && el["include-binaries"].checked && el["include-photspt"].checked) {
    length *= ageColorbarAllOptionalLengthMultiplier;
  }
  const out = {
    title: "<b>Age (Myr)</b>",
    ticks: "outside",
    ticklen: 5,
    tickwidth: 2,
    x: 1.02,
    y: 0.02,
    yanchor: "bottom",
    lenmode: "fraction",
    len: length,
    thickness: 15,
    xpad: 0,
    ypad: 0,
    outlinecolor: "black",
    outlinewidth: 3,
  };
  if (!ages.length) return out;
  const domain = ageColorDomain(rows);
  const kmin = Math.floor(domain?.min ?? 0);
  const kmax = Math.ceil(domain?.max ?? 3);
  const tickAges = [];
  for (let k = kmin; k <= kmax; k += 1) tickAges.push(10 ** k);
  if (tickAges.length) {
    out.tickmode = "array";
    out.tickvals = tickAges.map((age) => Math.log10(age));
    out.ticktext = tickAges.map((age) => age >= 1 ? String(Math.round(age)) : String(age));
  }
  return out;
}

function legendTraces(rows) {
  const classes = orderedSpectralClasses(rows.map((row) => row.spectral_class));
  return classes.map((klass) => ({
    type: "scatter",
    mode: "markers",
    x: [null],
    y: [null],
    marker: { size: 9, color: classColors[klass] || "#1da6b8" },
    name: `${klass} class`,
    legendgroup: `class:${klass}`,
    visible: state.hiddenLegendClasses.has(klass) ? "legendonly" : true,
  }));
}

function sampleLegendTraces(rows) {
  const samples = ["field", "low_gravity", "subdwarf"].filter((sample) => rows.some((row) => row.age_sample === sample));
  return samples.map((sample) => ({
    type: "scatter",
    mode: "markers",
    x: [null],
    y: [null],
    marker: {
      size: 10,
      color: "#5f5864",
      symbol: sampleSymbols[sample],
      line: { color: "#252329", width: 1 },
    },
    name: sampleLegendLabels[sample],
    legendgroup: `sample:${sample}`,
    visible: state.hiddenLegendSamples.has(sample) ? "legendonly" : true,
  }));
}

function binaryLegendTraces(rows) {
  if (!el["include-binaries"].checked || !rows.some((row) => row.is_binary)) return [];
  return [{
    type: "scatter",
    mode: "markers",
    x: [null],
    y: [null],
    marker: {
      size: 10,
      color: binaryLegendColor,
      symbol: "circle-open",
      line: { color: binaryLegendColor, width: 2 },
    },
    name: "Binaries",
    legendgroup: "binary:known",
    visible: state.hiddenLegendBinaries ? "legendonly" : true,
  }];
}

function photometricDistanceLegendTraces(rows) {
  if (!includePhotometricDistancesForAxes() || !rows.some((row) => row.is_photometric_distance)) return [];
  return [{
    type: "scatter",
    mode: "markers",
    x: [null],
    y: [null],
    marker: {
      size: 6,
      color: "#8a8f8d",
      symbol: "circle",
      line: { color: "#6f7472", width: 1 },
    },
    name: "Photo. dist.",
    legendgroup: "photdist:known",
    visible: state.hiddenLegendPhotdist ? "legendonly" : true,
  }];
}

function photometricSptLegendTraces(rows) {
  if (!el["include-photspt"].checked || !rows.some((row) => row.is_photometric_spt)) return [];
  return [{
    type: "scatter",
    mode: "markers",
    x: [null],
    y: [null],
    marker: {
      size: 10,
      color: photometricSptLegendColor,
      symbol: "circle",
      line: { color: photometricSptEdgeColor, width: photometricSptEdgeWidth },
    },
    name: "Photometric SPT",
    legendgroup: "photspt:known",
  }];
}

function medianColorTraces() {
  const x = axisSpec("x");
  const y = axisSpec("y");
  const out = [];
  const rows = state.raw.catalog.medianColors || [];
  let axisForColor = null;
  let psid1 = null;
  let psid2 = null;
  if (x.type === "spectral_type" && y.type === "color") {
    axisForColor = "y";
    psid1 = y.value1;
    psid2 = y.value2;
  } else if (x.type === "color" && y.type === "spectral_type") {
    axisForColor = "x";
    psid1 = x.value1;
    psid2 = x.value2;
  }
  if (!axisForColor) return out;
  const matching = rows.filter((row) => row.moca_psid1 === psid1 && row.moca_psid2 === psid2);
  if (!matching.length) return out;
  out.push({
    type: "scatter",
    mode: "markers+text",
    x: matching.map((row) => axisForColor === "y" ? row.spectral_type_number : row.color_mag),
    y: matching.map((row) => axisForColor === "y" ? row.color_mag : row.spectral_type_number),
    text: matching.map((row) => sptLabel(Number(row.spectral_type_number)).replace(".0", "")),
    textposition: "middle center",
    marker: { size: 24, color: "rgba(255,255,255,0)", line: { color: "#111", width: 1.8 } },
    textfont: { size: 10, color: "#111" },
    hoverinfo: "skip",
    name: "Best18 median",
  });
  return out;
}

function sequenceTraces() {
  const rows = state.raw.catalog.sequences || [];
  if (!rows.length) return [];
  const x = axisSpec("x");
  const y = axisSpec("y");
  const grouped = new Map();
  for (const row of rows) {
    if (!sequenceMatches(row, x, y)) continue;
    if (!grouped.has(row.moca_seqid)) grouped.set(row.moca_seqid, []);
    grouped.get(row.moca_seqid).push(row);
  }
  const colors = ["#111", "#7c5a20", "#0c7a75", "#8a3d55"];
  return [...grouped.entries()].map(([seqid, seqRows], index) => ({
    type: "scatter",
    mode: "lines",
    x: seqRows.map((row) => Number(row.xdata)),
    y: seqRows.map((row) => Number(row.ydata)),
    line: { width: 2.5, color: colors[index % colors.length] },
    hoverinfo: "x+y+name",
    name: seqRows[0].name_bdcolapp || seqid,
  }));
}

function sequenceMatches(row, x, y) {
  return (
    axisMatchesRule(x, row.xaxis_type_bdcolapp, row.xaxis_value_1_bdcolapp, row.xaxis_value_2_bdcolapp) &&
    axisMatchesRule(y, row.yaxis_type_bdcolapp, row.yaxis_value_1_bdcolapp, row.yaxis_value_2_bdcolapp)
  );
}

function axisMatchesRule(axis, type, value1, value2) {
  if (axis.type !== type) return false;
  if (type === "spectral_type") return true;
  if (type === "color") {
    return sequenceAxisValueMatches(axis.value1, value1) && sequenceAxisValueMatches(axis.value2, value2);
  }
  return sequenceAxisValueMatches(axis.value1, value1);
}

function sequenceAxisValueMatches(axisValue, sequenceValue) {
  if (axisValue === sequenceValue) return true;
  const simpleBand = simplePhotometryBand(axisValue);
  if (!simpleBand) return false;
  return photometrySimpleBandForValue(sequenceValue) === simpleBand;
}

function photometrySimpleBandForValue(value) {
  const option = (state.raw?.options?.photometry || []).find((row) => row.moca_psid === value);
  return normalizeSimplePhotometryBand(option?.system_band_simple);
}

function axisLayout(axis, label, rows, initialRange) {
  const layout = {
    title: {
      text: label,
      font: { size: 18 },
      standoff: axis === "x" ? 14 : 12,
    },
    automargin: false,
    tickfont: { size: 13 },
    gridcolor: "rgba(215,221,218,0.8)",
    zeroline: false,
    showline: true,
    linewidth: 2.2,
    linecolor: "#1f2524",
    mirror: true,
    ticks: "outside",
  };
  const type = el[`${axis}-axis-type`].value;
  if (type === "spectral_type") {
    const values = rows.map((row) => axis === "x" ? row.x : row.y).filter(Number.isFinite);
    if (values.length) {
      const min = Math.floor(Math.min(...values));
      const max = Math.ceil(Math.max(...values));
      const ticks = [];
      for (let value = Math.ceil(min / 2) * 2; value <= max; value += 2) ticks.push(value);
      layout.tickvals = ticks;
      layout.ticktext = ticks.map(sptLabel);
    }
  }
  const isAbsoluteMagnitudeY = axis === "y" && el["y-axis-type"].value === "absolute_magnitude";
  if (initialRange) {
    const reversed = isAbsoluteMagnitudeY;
    layout.range = reversed ? [initialRange[1], initialRange[0]] : initialRange;
    layout.autorange = false;
  } else if (isAbsoluteMagnitudeY) {
    layout.autorange = "reversed";
  }
  return layout;
}

function errorBarTrace(rows, opacity = 0.2, uid = "error-bars") {
  if (!el["show-errors"].checked || !rows.length || !rows.some(hasFiniteError)) return null;
  return {
    type: "scattergl",
    uid,
    mode: "markers",
    x: rows.map(plotX),
    y: rows.map(plotY),
    hoverinfo: "skip",
    showlegend: false,
    marker: {
      size: 1,
      color: "rgba(0,0,0,0)",
      opacity: 0,
    },
    error_x: errorSpec(rows, "ex", opacity),
    error_y: errorSpec(rows, "ey", opacity),
    name: "Error bars",
  };
}

function hasFiniteError(row) {
  return (Number.isFinite(row.ex) && row.ex > 0) || (Number.isFinite(row.ey) && row.ey > 0);
}

function errorSpec(rows, field, opacity = 0.2) {
  if (!el["show-errors"].checked) return { visible: false };
  return {
    type: "data",
    array: rows.map((row) => Number.isFinite(row[field]) ? row[field] : 0),
    visible: true,
    thickness: 0.75,
    width: 0,
    color: `rgba(55,55,55,${opacity})`,
  };
}

function bindPlotEvents() {
  if (state.plotBound && el.plot.removeAllListeners) {
    el.plot.removeAllListeners("plotly_selected");
    el.plot.removeAllListeners("plotly_deselect");
    el.plot.removeAllListeners("plotly_click");
    el.plot.removeAllListeners("plotly_legendclick");
    el.plot.removeAllListeners("plotly_legenddoubleclick");
    el.plot.removeAllListeners("plotly_relayout");
  }
  el.plot.on("plotly_selected", (event) => {
    state.selectedOids = event?.points?.map((point) => Number(point.customdata)).filter(Number.isFinite) || [];
    renderTable(state.selectedOids);
  });
  el.plot.on("plotly_deselect", () => {
    state.selectedOids = [];
    renderTable([]);
  });
  el.plot.on("plotly_click", (event) => {
    const oid = Number(event?.points?.[0]?.customdata);
    if (Number.isFinite(oid)) {
      const reportUrl = mocaReportUrl(oid);
      if (reportUrl) window.open(reportUrl, "_blank");
    }
  });
  el.plot.on("plotly_legendclick", (event) => {
    const trace = event?.fullData?.[event.curveNumber] || event?.data?.[event.curveNumber];
    return handleLegendClick(trace);
  });
  el.plot.on("plotly_legenddoubleclick", (event) => {
    const trace = event?.fullData?.[event.curveNumber] || event?.data?.[event.curveNumber];
    return handleLegendDoubleClick(trace);
  });
  el.plot.on("plotly_relayout", () => {
    renderCountSummary(state.rows);
  });
  state.plotBound = true;
}

function handleLegendClick(trace) {
  const group = customLegendGroup(trace);
  if (!group) return true;
  if (isStaticLegendGroup(group)) return false;
  window.clearTimeout(state.legendClickTimer);
  state.legendClickTimer = window.setTimeout(() => {
    toggleLegendGroup(group);
    render();
    state.legendClickTimer = null;
  }, 350);
  return false;
}

function handleLegendDoubleClick(trace) {
  const group = customLegendGroup(trace);
  if (!group) return true;
  if (isStaticLegendGroup(group)) return false;
  window.clearTimeout(state.legendClickTimer);
  state.legendClickTimer = null;
  isolateLegendGroup(group);
  render();
  return false;
}

function customLegendGroup(trace) {
  const group = String(trace?.legendgroup || "");
  return group.startsWith("class:") || group.startsWith("sample:") || group.startsWith("binary:") || group.startsWith("photdist:") || group.startsWith("photspt:") ? group : "";
}

function isStaticLegendGroup(group) {
  return group.startsWith("photspt:");
}

function toggleLegendGroup(group) {
  if (group.startsWith("class:")) {
    toggleLegendValue(state.hiddenLegendClasses, group.slice("class:".length));
  } else if (group.startsWith("sample:")) {
    toggleLegendValue(state.hiddenLegendSamples, group.slice("sample:".length));
  } else if (group.startsWith("binary:")) {
    state.hiddenLegendBinaries = !state.hiddenLegendBinaries;
  } else if (group.startsWith("photdist:")) {
    state.hiddenLegendPhotdist = !state.hiddenLegendPhotdist;
  }
}

function isolateLegendGroup(group) {
  if (group.startsWith("class:")) {
    const klass = group.slice("class:".length);
    const classes = legendClassValues();
    const alreadyIsolated = isLegendValueIsolated(state.hiddenLegendClasses, classes, klass) && state.hiddenLegendSamples.size === 0;
    state.hiddenLegendClasses.clear();
    state.hiddenLegendSamples.clear();
    if (!alreadyIsolated) {
      classes.filter((item) => item !== klass).forEach((item) => state.hiddenLegendClasses.add(item));
    }
  } else if (group.startsWith("sample:")) {
    const sample = group.slice("sample:".length);
    const samples = legendSampleValues();
    const alreadyIsolated = isLegendValueIsolated(state.hiddenLegendSamples, samples, sample) && state.hiddenLegendClasses.size === 0;
    state.hiddenLegendClasses.clear();
    state.hiddenLegendSamples.clear();
    if (!alreadyIsolated) {
      samples.filter((item) => item !== sample).forEach((item) => state.hiddenLegendSamples.add(item));
    }
  }
}

function isLegendValueIsolated(hiddenValues, availableValues, value) {
  const others = availableValues.filter((item) => item !== value);
  return availableValues.includes(value) && !hiddenValues.has(value) && others.length > 0 && others.every((item) => hiddenValues.has(item));
}

function legendClassValues() {
  return orderedSpectralClasses(state.allRows.map((row) => row.spectral_class));
}

function legendSampleValues() {
  return ["field", "low_gravity", "subdwarf"].filter((sample) => state.allRows.some((row) => row.age_sample === sample));
}

function orderedSpectralClasses(classes) {
  const unique = [...new Set(classes.filter(Boolean))];
  return unique.sort((a, b) => {
    const ai = spectralClassLegendOrder.indexOf(a);
    const bi = spectralClassLegendOrder.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return String(a).localeCompare(String(b));
  });
}

function toggleLegendValue(hiddenValues, value) {
  if (!value) return;
  if (hiddenValues.has(value)) {
    hiddenValues.delete(value);
  } else {
    hiddenValues.add(value);
  }
}

function renderTable(oids) {
  if (!oids.length) {
    el["selection-table"].textContent = "No points selected.";
    return;
  }
  const selected = state.rows.filter((row) => oids.includes(row.moca_oid));
  const showAllSpectraLinks = selected.some((row) => allSpectrumSpecidsForRow(row).length);
  const showSpectrumLinks = selected.some((row) => spectrumSpecidsForRow(row).length);
  const columns = [
    tableColumn("moca_oid"),
    tableColumn("designation"),
    tableColumn("spectral_type"),
    ...(showSpectrumLinks ? [spectrumSpecidTableColumn()] : []),
    tableColumn("x"),
    tableColumn("y"),
    ...inputTableColumns(selected),
  ];
  if (el["color-by-age"].checked) {
    columns.push(tableColumn("age_myr"), tableColumn("age_sample"));
  }
  const headerCells = [
    "plot",
    "report",
    ...(showAllSpectraLinks ? ["all spectra"] : []),
    ...(showSpectrumLinks ? ["spectrum"] : []),
    ...columns.map((col) => col.label),
  ]
    .map((col) => `<th>${escapeHtml(plainText(col))}</th>`)
    .join("");
  el["selection-table"].innerHTML = `
    <table>
      <thead><tr>${headerCells}</tr></thead>
      <tbody>
        ${selected.map((row) => {
          const reportUrl = mocaReportUrl(row.moca_oid);
          return `
            <tr>
              <td>${bdTableMarkerHtml(row)}</td>
              <td>${reportUrl ? `<a class="report-link" href="${escapeHtml(reportUrl)}" target="_blank" rel="noopener">Report</a>` : ""}</td>
              ${showAllSpectraLinks ? `<td>${allSpectraLinkHtml(row)}</td>` : ""}
              ${showSpectrumLinks ? `<td>${spectrumLinkHtml(row)}</td>` : ""}
              ${columns.map((col) => `<td>${escapeHtml(col.value(row))}</td>`).join("")}
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}

function bdTableMarkerHtml(row) {
  const symbol = row.highlighted ? "star" : String(markerSymbolForRow(row));
  const baseSymbol = symbol.replace(/-open$/, "");
  const open = !row.highlighted && symbol.endsWith("-open");
  const color = row.highlighted ? "#ffe66d" : bdTableColor(row);
  const edgeColor = row.highlighted
    ? "#111111"
    : (open ? color : (row.is_photometric_spt ? photometricSptEdgeColor : "rgba(255,255,255,0.82)"));
  const edgeWidth = row.highlighted
    ? 2.5
    : (open ? 2.4 : (row.is_photometric_spt ? photometricSptEdgeWidth : 1.4));
  const fill = open ? "none" : color;
  const opacity = row.noisy ? 0.45 : 1;
  const size = markerSizeForRow(row, 14.4);
  const sizeText = Number.isFinite(size) ? size.toFixed(1) : "18.0";
  const shape = ["circle", "square", "triangle-up", "star"].includes(baseSymbol) ? baseSymbol : "circle";
  return `<span class="plot-table-marker-wrap"><span class="plot-table-marker is-${escapeHtml(shape)}${open ? " is-open" : ""}" style="--marker-size: ${sizeText}px; --marker-color: ${escapeHtml(color)}; --marker-fill: ${escapeHtml(fill)}; --marker-edge: ${escapeHtml(edgeColor)}; --marker-border-width: ${escapeHtml(edgeWidth)}px; --marker-opacity: ${opacity};"></span></span>`;
}

function bdTableColor(row) {
  if (el["color-by-age"]?.checked) return ageColorForRow(row, ageColorDomain(state.rows));
  return classColors[row.spectral_class] || "#1da6b8";
}

function tableColumn(key) {
  return {
    label: key,
    value: (row) => key === "moca_oid" ? formatIntegerCell(row[key]) : formatCell(row[key]),
  };
}

function spectrumSpecidTableColumn() {
  return {
    label: "moca_specid",
    value: (row) => spectrumSpecidsForRow(row).join(", "),
  };
}

function spectrumSpecidsForRow(row) {
  const seen = new Set();
  const specids = [];
  for (const input of row.input_data || []) {
    if (!isSpectrumInput(input)) continue;
    const specid = normalizedMocaSpecid(input.moca_specid);
    if (!specid || seen.has(specid)) continue;
    seen.add(specid);
    specids.push(specid);
  }
  return specids;
}

function allSpectrumSpecidsForRow(row) {
  const oid = Number(row?.moca_oid);
  if (!Number.isFinite(oid)) return [];
  return state.maps?.spectrumSpecidsByOid?.get(oid) || [];
}

function isSpectrumInput(input) {
  const key = String(input?.key || "");
  return key.startsWith("spectral_index:") || key.startsWith("equivalent_width:");
}

function spectrumLinkHtml(row) {
  const url = spectraExplorerUrlForRow(row);
  if (!url) return "";
  return `<a class="report-link spectrum-link" role="button" href="${escapeHtml(url)}" target="_blank" rel="noopener">View spectrum</a>`;
}

function allSpectraLinkHtml(row) {
  const url = allSpectraExplorerUrlForRow(row);
  if (!url) return "";
  return `<a class="report-link all-spectra-link" role="button" href="${escapeHtml(url)}" target="_blank" rel="noopener">View all spectra</a>`;
}

function spectraExplorerUrlForRow(row) {
  const specids = spectrumSpecidsForRow(row);
  return spectraExplorerUrlForSpecids(specids);
}

function allSpectraExplorerUrlForRow(row) {
  const specids = allSpectrumSpecidsForRow(row);
  return spectraExplorerUrlForSpecids(specids);
}

function spectraExplorerUrlForSpecids(specids) {
  if (!specids.length) return "";
  const url = new URL("spectra", appBaseUrl);
  const params = spectraExplorerUrlParams();
  params.set("moca_specid", specids.join(","));
  url.search = params.toString();
  return url.toString();
}

function spectraExplorerUrlParams() {
  const source = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "user", "pwd", "dbase", "database", "db", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  if (!params.has("dbase")) {
    const databaseName = source.get("database") || source.get("db");
    if (databaseName) params.set("dbase", databaseName);
  }
  return params;
}

function formatIntegerCell(value) {
  const number = Number(value);
  return Number.isFinite(number) ? String(Math.trunc(number)) : "";
}

function inputTableColumns(rows) {
  const columns = [];
  const seen = new Set();
  for (const row of rows) {
    for (const input of row.input_data || []) {
      if (seen.has(input.key)) continue;
      seen.add(input.key);
      columns.push({
        key: input.key,
        label: plainText(input.label),
        value: (targetRow) => {
          const match = (targetRow.input_data || []).find((item) => item.key === input.key);
          return match ? measurementText(match) : "";
        },
      });
    }
  }
  return columns;
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

function normalizedMocaSpecid(specid) {
  if (specid === null || specid === undefined) return "";
  const text = String(specid).trim();
  if (!text) return "";
  const number = Number(text);
  if (!Number.isFinite(number) || number <= 0) return "";
  return number.toFixed(0);
}

function renderMissingHighlightedOids(rows) {
  const requested = parseOidList(el["highlight-oids"].value);
  const plotted = new Set(rows.map((row) => row.moca_oid));
  const missing = requested.filter((oid) => !plotted.has(oid));
  const messages = [];
  if (missing.length) {
    messages.push(`These OIDs were not found in the current dataset: ${missing.join(", ")}`);
  }
  if (state.selectedDesignations.length && state.featuresLoaded.designations) {
    const missingDesignations = state.selectedDesignations.filter((designation) => {
      const matches = state.maps?.oidsByDesignation?.get(normalizeDesignation(designation));
      return !matches || ![...matches].some((oid) => plotted.has(oid));
    });
    if (missingDesignations.length) {
      messages.push(`These designations were not found in the current plotted dataset: ${missingDesignations.map(selectedDesignationLabel).join(", ")}`);
    }
  }
  el["missing-oids"].hidden = messages.length === 0;
  el["missing-oids"].textContent = messages.join(" ");
}

const exportColumns = [
  "moca_oid",
  "designation",
  "spectral_type",
  "spectral_type_number",
  "x",
  "ex",
  "y",
  "ey",
  "x_label",
  "y_label",
  "distance_pc",
  "age_myr",
  "age_sample",
  "x_ref",
  "y_ref",
];

const numericExportColumns = new Set([
  "moca_oid",
  "spectral_type_number",
  "x",
  "ex",
  "y",
  "ey",
  "distance_pc",
  "age_myr",
]);

function exportRows() {
  return state.selectedOids.length
    ? state.rows.filter((row) => state.selectedOids.includes(row.moca_oid))
    : state.rows;
}

function exportCsv() {
  const selected = exportRows();
  if (!selected.length) return;
  const csv = [
    exportColumns.join(","),
    ...selected.map((row) => exportColumns.map((col) => csvCell(row[col], col)).join(",")),
  ].join("\n");
  downloadBlob(csv, "moca_colors_fast_dataset.csv", "text/csv;charset=utf-8");
}

function exportTsv() {
  const selected = exportRows();
  if (!selected.length) return;
  const tsv = [
    exportColumns.join("\t"),
    ...selected.map((row) => exportColumns.map((col) => tsvCell(row[col], col)).join("\t")),
  ].join("\n");
  downloadBlob(tsv, "moca_colors_fast_dataset.tsv", "text/tab-separated-values;charset=utf-8");
}

function exportVotable() {
  const selected = exportRows();
  if (!selected.length) return;
  const fields = exportColumns.map((column) => ({
    name: column,
    datatype: numericExportColumns.has(column) ? "double" : "char",
  }));
  const fieldXml = fields.map((field) => {
    const arraysize = field.datatype === "char" ? ' arraysize="*"' : "";
    return `      <FIELD name="${xmlEscape(field.name)}" datatype="${field.datatype}"${arraysize}/>`;
  }).join("\n");
  const rowsXml = selected.map((row) => {
    const cells = exportColumns
      .map((column) => `          <TD>${xmlEscape(votableCell(row[column], column))}</TD>`)
      .join("\n");
    return `        <TR>\n${cells}\n        </TR>`;
  }).join("\n");
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
  <RESOURCE name="MOCAdb Brown Dwarf Photometry Explorer">
    <TABLE name="moca_colors_fast_dataset">
${fieldXml}
      <DATA>
        <TABLEDATA>
${rowsXml}
        </TABLEDATA>
      </DATA>
    </TABLE>
  </RESOURCE>
</VOTABLE>
`;
  downloadBlob(xml, "moca_colors_fast_dataset.vot", "application/x-votable+xml;charset=utf-8");
}

function exportFits() {
  const selected = exportRows();
  if (!selected.length) return;
  const bytes = buildFitsTable(selected, exportColumns);
  downloadBlob(bytes, "moca_colors_fast_dataset.fits", "application/fits");
}

function downloadBlob(content, filename, type) {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function buildFitsTable(rows, columns) {
  const specs = columns.map((name) => {
    if (numericExportColumns.has(name)) return { name, form: "D", bytes: 8, numeric: true };
    const width = Math.max(1, ...rows.map((row) => fitsAscii(exportCellText(row[name], name)).length));
    return { name, form: `${Math.min(width, 1024)}A`, bytes: Math.min(width, 1024), numeric: false };
  });
  const rowLength = specs.reduce((total, spec) => total + spec.bytes, 0);
  const primary = fitsHeader([
    fitsCard("SIMPLE", true),
    fitsCard("BITPIX", 8),
    fitsCard("NAXIS", 0),
    fitsCard("EXTEND", true),
    fitsEndCard(),
  ]);
  const tableCards = [
    fitsCard("XTENSION", "BINTABLE"),
    fitsCard("BITPIX", 8),
    fitsCard("NAXIS", 2),
    fitsCard("NAXIS1", rowLength),
    fitsCard("NAXIS2", rows.length),
    fitsCard("PCOUNT", 0),
    fitsCard("GCOUNT", 1),
    fitsCard("TFIELDS", specs.length),
  ];
  specs.forEach((spec, index) => {
    tableCards.push(fitsCard(`TTYPE${index + 1}`, spec.name));
    tableCards.push(fitsCard(`TFORM${index + 1}`, spec.form));
  });
  tableCards.push(fitsCard("EXTNAME", "MOCA_COLORS"));
  tableCards.push(fitsEndCard());

  const data = new Uint8Array(paddedLength(rowLength * rows.length));
  const view = new DataView(data.buffer);
  rows.forEach((row, rowIndex) => {
    let offset = rowIndex * rowLength;
    specs.forEach((spec) => {
      if (spec.numeric) {
        const value = Number(row[spec.name]);
        view.setFloat64(offset, Number.isFinite(value) ? value : NaN, false);
      } else {
        data.fill(32, offset, offset + spec.bytes);
        const text = fitsAscii(exportCellText(row[spec.name], spec.name)).slice(0, spec.bytes);
        for (let i = 0; i < text.length; i += 1) data[offset + i] = text.charCodeAt(i);
      }
      offset += spec.bytes;
    });
  });

  return new Blob([primary, fitsHeader(tableCards), data], { type: "application/fits" });
}

function fitsHeader(cards) {
  return asciiBytes(cards.join("").padEnd(paddedLength(cards.length * 80), " "));
}

function fitsCard(keyword, value) {
  let textValue;
  if (typeof value === "boolean") {
    textValue = value ? "T" : "F";
  } else if (typeof value === "number") {
    textValue = String(value);
  } else {
    textValue = `'${fitsAscii(value).replace(/'/g, "''")}'`;
  }
  return `${keyword.padEnd(8)}= ${textValue.padStart(20)}`.padEnd(80, " ");
}

function fitsEndCard() {
  return "END".padEnd(80, " ");
}

function paddedLength(length) {
  return Math.ceil(length / 2880) * 2880;
}

function asciiBytes(text) {
  const output = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i += 1) output[i] = text.charCodeAt(i) & 0x7f;
  return output;
}

function fitsAscii(value) {
  return String(value ?? "").replace(/[^\x20-\x7e]/g, "?");
}

function hoverText(row) {
  const inputLines = (row.input_data || []).map((input) => (
    `${escapeHtml(plainText(input.label))}: ${escapeHtml(measurementText(input))}`
  ));
  const hasDistanceInput = (row.input_data || []).some((input) => input.key === "distance_pc");
  return [
    `<b>${escapeHtml(row.designation)}</b>`,
    `MOCA OID: ${row.moca_oid}`,
    `SpT: ${escapeHtml(row.complete_spectral_type || row.spectral_type)}`,
    `X (${escapeHtml(plainText(row.x_label))}): ${escapeHtml(measurementText({ value: row.x, error: row.ex }))}`,
    `Y (${escapeHtml(plainText(row.y_label))}): ${escapeHtml(measurementText({ value: row.y, error: row.ey }))}`,
    ...inputLines,
    row.distance_pc && !hasDistanceInput ? `Distance: ${formatCell(row.distance_pc)} pc` : null,
    row.age_myr ? `Age: ${formatCell(row.age_myr)} Myr` : null,
  ].filter(Boolean).join("<br>");
}

function measurementText(measurement) {
  if (!measurement) return "";
  const parts = [formatCell(measurement.value)];
  const error = numericValue(measurement.error);
  if (Number.isFinite(error)) parts.push("+/-", formatCell(error));
  const unit = String(measurement.unit || "").trim();
  if (unit) parts.push(unit);
  return parts.filter((part) => part !== "").join(" ");
}

function parseSptRange(text) {
  const raw = String(text || "").trim().toUpperCase().replace("_", "-").replace(/^>=\s*/, "");
  if (raw.endsWith("+")) {
    const min = parseSpt(raw.slice(0, -1).trim());
    return Number.isFinite(min) ? { min, max: Infinity } : { min: 10, max: Infinity };
  }
  const parts = raw.split("-");
  if (parts.length !== 2) {
    const min = parseSpt(raw);
    return Number.isFinite(min) ? { min, max: Infinity } : { min: 10, max: Infinity };
  }
  const min = parseSpt(parts[0].trim());
  const max = parseSpt(parts[1].trim());
  if (!Number.isFinite(min) || !Number.isFinite(max) || min > max) return { min: 10, max: Infinity };
  return { min, max };
}

function parseSpt(label) {
  const match = String(label || "").trim().toUpperCase().match(/^([OBAFGKMLTY])\s*([0-9]+(?:\.[0-9]+)?)$/);
  if (!match) return NaN;
  const classes = { O: 0, B: 10, A: 20, F: 30, G: 40, K: 50, M: 60, L: 70, T: 80, Y: 90 };
  return classes[match[1]] + Number(match[2]) - 60;
}

function sptLabel(value) {
  const adjusted = Number(value) + 60;
  const classes = ["O", "B", "A", "F", "G", "K", "M", "L", "T", "Y"];
  const index = Math.floor(adjusted / 10);
  const subclass = adjusted % 10;
  if (index < 0 || index >= classes.length) return formatCell(value);
  const rounded = Math.round(subclass * 10) / 10;
  return `${classes[index]}${String(rounded).replace(/\.0$/, "")}`;
}

function classFromSpt(value) {
  return sptLabel(value).charAt(0);
}

function normalizedSpectralClass(value) {
  const cleaned = String(value || "").split("+")[0].replace(/\?/g, "").trim();
  return cleaned || String(value || "");
}

function parseDesignationParams(params) {
  const rawValues = [
    ...params.getAll("designation"),
    ...params.getAll("designations"),
  ];
  const selected = [];
  const seen = new Set();
  for (const raw of rawValues) {
    for (const designation of String(raw || "").split(",")) {
      const cleaned = designation.trim();
      const key = normalizeDesignation(cleaned);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      selected.push(cleaned);
    }
  }
  return selected;
}

function normalizeDesignation(value) {
  return String(value || "").trim().replace(/\s+/g, " ").toLowerCase();
}

function searchableDesignation(value) {
  return normalizeDesignation(value).replace(/[^a-z0-9]+/g, "");
}

function parseOidSet(text) {
  return new Set(parseOidList(text));
}

function parseOidList(text) {
  const seen = new Set();
  return String(text || "")
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map(Number)
    .filter((oid) => Number.isFinite(oid) && !seen.has(oid) && seen.add(oid));
}

function numericValue(value) {
  const text = String(value ?? "").trim().toLowerCase();
  if (!text || text === "none" || text === "null" || text === "nan") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function hypot(a, b) {
  const aa = numericValue(a) || 0;
  const bb = numericValue(b) || 0;
  return Math.sqrt(aa * aa + bb * bb);
}

function isNoisy(error, threshold) {
  return threshold !== null && Number.isFinite(error) && error > threshold;
}

function formatCell(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "";
    if (Math.abs(value) >= 100) return value.toFixed(1);
    if (Math.abs(value) >= 10) return value.toFixed(2);
    return value.toFixed(3);
  }
  return String(value);
}

function csvCell(value, column = "") {
  const text = exportCellText(value, column);
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function tsvCell(value, column = "") {
  return exportCellText(value, column).replace(/[\t\r\n]+/g, " ");
}

function votableCell(value, column) {
  if (numericExportColumns.has(column)) return numericExportText(value);
  return exportCellText(value);
}

function exportCellText(value, column = "") {
  if (numericExportColumns.has(column)) return numericExportText(value);
  return plainText(formatCell(value));
}

function numericExportText(value) {
  const number = Number(value);
  return Number.isFinite(number) ? String(number) : "";
}

function plainText(value) {
  return String(value ?? "")
    .replace(/<sub>(.*?)<\/sub>/gi, "_$1")
    .replace(/<[^>]*>/g, "")
    .replace(/\u2212/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

function xmlEscape(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
