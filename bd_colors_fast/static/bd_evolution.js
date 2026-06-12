const bdeTerrainStops = [
  [0.0, [51, 51, 153]],
  [0.15, [0, 153, 255]],
  [0.25, [0, 204, 102]],
  [0.5, [255, 255, 153]],
  [0.75, [128, 92, 84]],
  [1.0, [255, 255, 255]],
];
const BDE_MASS_BOUNDARY_TARGETS_MJUP = [13, 80];
const BDE_MASS_TRACK_LABEL_COUNT = 12;
const BDE_MASS_TARGET_LABEL_TOLERANCE_MJUP = 1.0;
const BDE_MASS_LABEL_SUPPRESSED_MJUP = new Set([14]);
const BDE_DEFAULT_SPT_RANGE = "L2+";
const BDE_DEFAULT_AGE_JITTER_DEX = 0.016;
const BDE_AGE_JITTER_CLIP_SIGMA = 2.5;
const BDE_MAX_AGE_JITTER_DEX = 0.08;
const BDE_DEFAULT_YA_PROB_MIN = 80;
const BDE_DEFAULT_IGNORED_MEMBERSHIP_AIDS = "OCTN,CUMA";
const BDE_DEFAULT_TRACK_MODEL = "sonora_diamondback_mocadb";
const BDE_MSUN_TO_MJUP = 1047.5654817267318;
const BDE_RJUP_TO_RSUN = 0.10045;
const BDE_MJUP_UNIT_HTML = "<i>M</i><sub>Jup</sub>";
const BDE_RJUP_UNIT_HTML = "<i>R</i><sub>Jup</sub>";
const BDE_SECURITY_CLASS_COUNT = 6;
const BDE_SECURITY_CLASS_COLORS = [
  "#74b3ff",
  "#2f7dff",
  "#0057ff",
  "#ff7a8a",
  "#ff3e55",
  "#d6001c",
];
const BDE_MARKER_MIN_SIZE = 10;
const BDE_MARKER_MAX_SIZE = 12;
const BDE_MARKER_SELECTED_MIN_SIZE = 15;
const BDE_MARKER_SELECTED_MAX_SIZE = 18;
const BDE_SYMBOL_SIZE_MULTIPLIERS = {
  square: 0.8,
  star: 1.2,
  "triangle-up": 0.95,
  "triangle-down": 0.95,
};
const BDE_SECURITY_SIZE_MIN_MULTIPLIER = 0.8;
const BDE_SECURITY_SIZE_MAX_MULTIPLIER = 1.2;
const BDE_MARKER_EDGE_COLOR = "rgba(255,255,255,0.88)";
const BDE_COMPANION_EDGE_COLOR = "#111111";
const BDE_HIGHLIGHT_EDGE_COLOR = "#111111";
const BDE_HIGHLIGHT_HALO_COLOR = "rgba(255,210,63,0.42)";
const BDE_ISOTHERM_MIN_POINTS = 3;
const BDE_ISOTHERM_LABEL_COUNT = 10;
const BDE_ISOTHERM_TARGET_TEFF_K = [
  300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400, 2600,
];
const BDE_MASS_RADIUS_SMOOTH_PASSES = 2;
const BDE_MASS_RADIUS_SMOOTH_MIN_CORRECTION_RJUP = 0.018;
const BDE_MASS_RADIUS_SMOOTH_MAX_CORRECTION_RJUP = 0.11;
const bdeTrackModelOptions = [
  { key: "sonora_diamondback_mocadb", label: "Sonora Diamondback + MOCAdb empirical extension" },
];
const bdeObservableSymbols = [
  { key: "pm", label: "μ", symbol: "circle", securityRank: 0 },
  { key: "pm_rv", label: "μ,RV", symbol: "diamond", securityRank: 1 },
  { key: "pm_photdist", label: "μ,D_phot", symbol: "triangle-up", securityRank: 2 },
  { key: "pm_plx", label: "μ,D_trig", symbol: "square", securityRank: 3 },
  { key: "pm_rv_photdist", label: "μ,RV,D_phot", symbol: "hexagon", securityRank: 4 },
  { key: "pm_rv_plx", label: "μ,RV,D_trig", symbol: "star", securityRank: 5 },
  { key: "other", label: "Other BANYAN Sigma", symbol: "pentagon" },
  { key: "none", label: "No BANYAN Sigma", symbol: "triangle-down" },
];

const bdeFallbackAxes = {
  age_myr: { key: "age_myr", label: "Age", title: "Age (Myr)", defaultLog: true, defaultRange: [2, 1000], positive: true, spectralTypeAxis: false },
  teff_k: { key: "teff_k", label: "Teff", title: "<i>T</i><sub>eff</sub> (K)", defaultLog: false, defaultRange: [200, 2000], positive: true, spectralTypeAxis: true },
  mass_mjup: { key: "mass_mjup", label: "Mass", title: `Mass (${BDE_MJUP_UNIT_HTML})`, defaultLog: false, defaultRange: [0.5, 85], positive: true, spectralTypeAxis: false },
  logg: { key: "logg", label: "log g", title: "log g (dex cgs)", defaultLog: false, defaultRange: [3.0, 5.7], positive: true, spectralTypeAxis: false },
  radius_rjup: { key: "radius_rjup", label: "Radius", title: `Radius (${BDE_RJUP_UNIT_HTML})`, defaultLog: false, defaultRange: [0.8, 2.0], positive: true, spectralTypeAxis: false },
};

const bdeDefaultSptAxis = [
  { label: "M0", teff_k: 3850 },
  { label: "M5", teff_k: 3050 },
  { label: "M8", teff_k: 2600 },
  { label: "L0", teff_k: 2300 },
  { label: "L2", teff_k: 2000 },
  { label: "L5", teff_k: 1700 },
  { label: "T0", teff_k: 1300 },
  { label: "T5", teff_k: 1000 },
  { label: "T9", teff_k: 600 },
  { label: "Y0", teff_k: 450 },
];

const bdeExportColumns = [
  "designation", "moca_oid", "spt", "sptn", "age_myr", "age_myr_unc",
  "age_source", "age_source_detail", "membership", "ya_prob", "observables",
  "banyan_observables", "banyan_distance_id", "banyan_distance_photometric", "is_companion",
  "teff_k", "teff_k_unc", "mass_mjup", "mass_mjup_unc", "mass_msun", "logg",
  "logg_unc", "radius_rjup", "radius_rjup_unc", "radius_rsun", "radius_rsun_unc", "report_url",
];
const bdeNumericExportColumns = new Set([
  "moca_oid", "sptn", "age_myr", "age_myr_unc", "ya_prob", "teff_k",
  "teff_k_unc", "mass_mjup", "mass_mjup_unc", "mass_msun", "logg",
  "logg_unc", "radius_rjup", "radius_rjup_unc", "radius_rsun", "radius_rsun_unc", "banyan_distance_id",
  "banyan_distance_photometric", "is_companion",
]);

const bdeEl = {};
const bdeState = {
  axes: { ...bdeFallbackAxes },
  sptAxis: [...bdeDefaultSptAxis],
  payload: null,
  rows: [],
  tracks: [],
  selectedOids: new Set(),
  selectedHighlightObjects: [],
  loadToken: 0,
  sptReloadTimer: null,
  objectSearchTimer: null,
  objectSearchToken: 0,
  tracksDefaultInitialized: false,
  companionsHiddenByLegend: false,
  legendVisibility: new Map(),
};

document.addEventListener("DOMContentLoaded", initBdEvolution);

const bdeAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function bdeAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), bdeAppBaseUrl).toString();
}

async function initBdEvolution() {
  collectBdEvolutionElements();
  populateBdEvolutionAxisSelects();
  populateBdEvolutionTrackSelect();
  bindBdEvolutionControls();
  readBdEvolutionUrlState();
  await loadBdEvolutionData();
}

function collectBdEvolutionElements() {
  [
    "bde-status", "bde-x-axis", "bde-y-axis", "bde-x-log", "bde-y-log",
    "bde-track-model", "bde-spt-range", "bde-ya-prob-min", "bde-ya-prob-min-value", "bde-ignore-aids",
    "bde-object-search", "bde-object-results", "bde-selected-objects", "bde-highlight-oids", "bde-remove-companions",
    "bde-tracks", "bde-data-hover", "bde-track-hover", "bde-track-hover-line",
    "bde-age-jitter", "bde-max-objects", "bde-load",
    "bde-plot", "bde-plot-loader", "bde-summary", "bde-subtitle",
    "bde-clear-selection", "bde-export-csv", "bde-export-tsv",
    "bde-table-title", "bde-table-subtitle", "bde-table",
    "bde-clear-cache-bottom", "bde-clear-cache-status",
  ].forEach((id) => {
    bdeEl[id] = document.getElementById(id);
  });
}

function bindBdEvolutionControls() {
  bdeEl["bde-load"].addEventListener("click", () => loadBdEvolutionData());
  for (const id of ["bde-x-axis", "bde-y-axis"]) {
    bdeEl[id].addEventListener("change", () => {
      applyBdEvolutionTrackDefaultForAxes(true);
      updateBdEvolutionUrl();
      renderBdEvolutionPlot();
    });
  }
  for (const id of ["bde-x-log", "bde-y-log", "bde-data-hover", "bde-track-hover"]) {
    bdeEl[id].addEventListener("change", () => {
      updateBdEvolutionUrl();
      renderBdEvolutionPlot();
    });
  }
  bdeEl["bde-tracks"].addEventListener("change", () => {
    updateBdEvolutionTrackHoverControl();
    updateBdEvolutionUrl();
    renderBdEvolutionPlot();
  });
  bdeEl["bde-track-model"].addEventListener("change", () => {
    updateBdEvolutionUrl();
    loadBdEvolutionData();
  });
  bdeEl["bde-age-jitter"].addEventListener("input", () => {
    updateBdEvolutionUrl();
    renderBdEvolutionPlot();
  });
  bdeEl["bde-spt-range"].addEventListener("input", () => {
    updateBdEvolutionUrl();
    scheduleBdEvolutionReload();
  });
  bdeEl["bde-spt-range"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadBdEvolutionData();
  });
  bdeEl["bde-spt-range"].addEventListener("change", () => loadBdEvolutionData());
  bdeEl["bde-ya-prob-min"].addEventListener("input", () => {
    updateBdEvolutionYaProbReadout();
    updateBdEvolutionUrl();
    scheduleBdEvolutionReload();
  });
  bdeEl["bde-ya-prob-min"].addEventListener("change", () => loadBdEvolutionData());
  bdeEl["bde-ignore-aids"].addEventListener("input", () => {
    updateBdEvolutionUrl();
    applyBdEvolutionClientFilters();
  });
  bdeEl["bde-ignore-aids"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      bdeEl["bde-ignore-aids"].value = bdEvolutionIgnoredMembershipAidsText();
      updateBdEvolutionUrl();
      applyBdEvolutionClientFilters();
    }
  });
  bdeEl["bde-ignore-aids"].addEventListener("change", () => {
    bdeEl["bde-ignore-aids"].value = bdEvolutionIgnoredMembershipAidsText();
    updateBdEvolutionUrl();
    applyBdEvolutionClientFilters();
  });
  bdeEl["bde-object-search"].addEventListener("input", () => {
    const value = bdeEl["bde-object-search"].value.trim();
    clearTimeout(bdeState.objectSearchTimer);
    bdeState.objectSearchTimer = setTimeout(() => searchBdEvolutionObjects(value), 220);
  });
  bdeEl["bde-object-search"].addEventListener("focus", () => {
    const value = bdeEl["bde-object-search"].value.trim();
    if (value) searchBdEvolutionObjects(value);
  });
  bdeEl["bde-highlight-oids"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadBdEvolutionData();
  });
  bdeEl["bde-highlight-oids"].addEventListener("change", () => loadBdEvolutionData());
  bdeEl["bde-remove-companions"].addEventListener("change", () => {
    updateBdEvolutionUrl();
    applyBdEvolutionClientFilters();
  });
  bdeEl["bde-max-objects"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadBdEvolutionData();
  });
  bdeEl["bde-max-objects"].addEventListener("change", () => loadBdEvolutionData());
  bdeEl["bde-clear-selection"].addEventListener("click", () => clearBdEvolutionSelection());
  bdeEl["bde-export-csv"].addEventListener("click", () => exportBdEvolution("csv"));
  bdeEl["bde-export-tsv"].addEventListener("click", () => exportBdEvolution("tsv"));
  bdeEl["bde-clear-cache-bottom"].addEventListener("click", () => clearBdEvolutionCache());
  document.addEventListener("click", (event) => {
    if (!bdeEl["bde-object-results"].contains(event.target) && event.target !== bdeEl["bde-object-search"]) {
      bdeEl["bde-object-results"].hidden = true;
    }
  });
  window.addEventListener("resize", debounce(() => {
    if (bdeEl["bde-plot"] && bdeState.payload) Plotly.Plots.resize(bdeEl["bde-plot"]);
  }, 150));
}

function populateBdEvolutionAxisSelects() {
  const axes = axisList();
  const axisKeys = new Set(axes.map((axis) => axis.key));
  for (const id of ["bde-x-axis", "bde-y-axis"]) {
    const current = normalizeBdEvolutionAxisKey(bdeEl[id]?.value || (id === "bde-x-axis" ? "age_myr" : "teff_k"));
    bdeEl[id].innerHTML = axes.map((axis) => (
      `<option value="${htmlEscape(axis.key)}">${htmlEscape(axis.label || axis.key)}</option>`
    )).join("");
    bdeEl[id].value = axisKeys.has(current) ? current : bdEvolutionDefaultAxisKey(id, axisKeys);
  }
}

function bdEvolutionDefaultAxisKey(selectId, axisKeys) {
  const preferred = selectId === "bde-x-axis"
    ? ["age_myr", "teff_k", "mass_mjup", "radius_rjup"]
    : ["teff_k", "mass_mjup", "age_myr", "radius_rjup"];
  return preferred.find((key) => axisKeys.has(key)) || axisKeys.values().next().value || "";
}

function populateBdEvolutionTrackSelect() {
  const current = bdeEl["bde-track-model"]?.value || BDE_DEFAULT_TRACK_MODEL;
  const optionKeys = new Set(bdeTrackModelOptions.map((option) => option.key));
  bdeEl["bde-track-model"].innerHTML = bdeTrackModelOptions.map((option) => (
    `<option value="${htmlEscape(option.key)}">${htmlEscape(option.label)}</option>`
  )).join("");
  bdeEl["bde-track-model"].value = optionKeys.has(current) ? current : BDE_DEFAULT_TRACK_MODEL;
}

function readBdEvolutionUrlState() {
  const params = new URLSearchParams(window.location.search);
  const first = (...keys) => {
    for (const key of keys) {
      if (params.has(key)) return params.get(key) || "";
    }
    return "";
  };
  const xAxis = first("x", "xaxis");
  const yAxis = first("y", "yaxis");
  const normalizedXAxis = normalizeBdEvolutionAxisKey(xAxis);
  const normalizedYAxis = normalizeBdEvolutionAxisKey(yAxis);
  const selectableAxes = new Set(axisList().map((axis) => axis.key));
  if (selectableAxes.has(normalizedXAxis)) bdeEl["bde-x-axis"].value = normalizedXAxis;
  if (selectableAxes.has(normalizedYAxis)) bdeEl["bde-y-axis"].value = normalizedYAxis;
  const xlog = first("xlog", "x_log");
  const ylog = first("ylog", "y_log");
  if (xlog) bdeEl["bde-x-log"].checked = truthyParam(xlog);
  if (ylog) bdeEl["bde-y-log"].checked = truthyParam(ylog);
  const trackModel = first("track_model", "model_track", "track_set");
  if (bdeTrackModelOptions.some((option) => option.key === trackModel)) {
    bdeEl["bde-track-model"].value = trackModel;
  }
  const maxObjects = first("max_objects", "limit");
  if (maxObjects) bdeEl["bde-max-objects"].value = maxObjects;
  bdeEl["bde-spt-range"].value = first("spt_range", "spt") || BDE_DEFAULT_SPT_RANGE;
  const yaProbMin = first("ya_prob_min", "min_ya_prob", "membership_prob_min", "min_membership_probability");
  bdeEl["bde-ya-prob-min"].value = yaProbMin || String(BDE_DEFAULT_YA_PROB_MIN);
  updateBdEvolutionYaProbReadout();
  const ignoredAidKeys = ["ignore_aids", "ignored_aids", "exclude_aids", "excluded_aids", "ignore_groups", "ignored_groups", "exclude_groups", "excluded_groups", "ignore_memberships", "ignored_memberships", "exclude_memberships", "excluded_memberships"];
  const ignoredAidParamPresent = ignoredAidKeys.some((key) => params.has(key));
  const ignoredAids = first(...ignoredAidKeys);
  bdeEl["bde-ignore-aids"].value = ignoredAidParamPresent ? normalizeBdEvolutionAidListText(ignoredAids) : BDE_DEFAULT_IGNORED_MEMBERSHIP_AIDS;
  const targetOidParam = first("oid", "oids", "moca_oid", "moca_oids");
  bdeState.selectedHighlightObjects = parseBdEvolutionOids(targetOidParam).map((oid) => ({
    value: oid,
    moca_oid: oid,
    label: `oid${oid}`,
  }));
  bdeEl["bde-highlight-oids"].value = "";
  renderBdEvolutionHighlightList();
  const removeCompanions = first("remove_companions", "exclude_companions", "no_companions");
  if (removeCompanions) bdeEl["bde-remove-companions"].checked = truthyParam(removeCompanions);
  const ageJitter = first("age_jitter", "jitter");
  bdeEl["bde-age-jitter"].value = ageJitter || String(BDE_DEFAULT_AGE_JITTER_DEX);
  const hover = first("hover");
  const dataHover = first("data_hover", "datahover");
  const trackHover = first("track_hover", "trackhover", "model_hover", "modelhover");
  if (hover) bdeEl["bde-data-hover"].checked = truthyParam(hover);
  if (dataHover) bdeEl["bde-data-hover"].checked = truthyParam(dataHover);
  if (trackHover) bdeEl["bde-track-hover"].checked = truthyParam(trackHover);
  applyBdEvolutionTrackDefaultForAxes(false);
  updateBdEvolutionTrackHoverControl();
}

async function loadBdEvolutionData() {
  updateBdEvolutionUrl();
  const token = ++bdeState.loadToken;
  if (bdeState.sptReloadTimer) {
    clearTimeout(bdeState.sptReloadTimer);
    bdeState.sptReloadTimer = null;
  }
  setBdEvolutionLoading(true);
  setBdEvolutionStatus("Loading Brown Dwarf Evolution Explorer", "loading");
  try {
    const payload = await fetchJsonUrl(bdeAppUrl(`api/bd-evolution/data?${dataParams().toString()}`));
    if (token !== bdeState.loadToken) return;
    if (!payload.ok) throw new Error(payload.error || "MOCAdb query failed");
    bdeState.payload = payload;
    bdeState.axes = payload.axes || { ...bdeFallbackAxes };
    bdeState.sptAxis = payload.sptAxis?.length ? payload.sptAxis : [...bdeDefaultSptAxis];
    bdeState.rows = (payload.rows || []).map(enrichBdEvolutionRow);
    bdeState.tracks = (payload.tracks || []).map(enrichBdEvolutionTrackRow);
    populateBdEvolutionAxisSelects();
    populateBdEvolutionTrackSelect();
    readBdEvolutionUrlState();
    if (payload.meta?.spt_range) bdeEl["bde-spt-range"].value = payload.meta.spt_range;
    if (payload.meta?.ya_prob_min !== undefined) {
      bdeEl["bde-ya-prob-min"].value = String(Math.round(Number(payload.meta.ya_prob_min)));
      updateBdEvolutionYaProbReadout();
    }
    pruneBdEvolutionSelection();
    renderBdEvolutionPlot();
    renderBdEvolutionTable();
    setBdEvolutionExportDisabled(bdEvolutionDisplayRows().length === 0);
    updateBdEvolutionSummary();
    updateBdEvolutionUrl();
    updateBdEvolutionLoadedStatus();
  } catch (error) {
    if (token !== bdeState.loadToken) return;
    bdeState.payload = null;
    bdeState.rows = [];
    bdeState.tracks = [];
    setBdEvolutionExportDisabled(true);
    renderBdEvolutionEmptyPlot(error.message);
    renderBdEvolutionTable();
    updateBdEvolutionSummary();
    setBdEvolutionStatus(error.message, "error");
  } finally {
    if (token === bdeState.loadToken) setBdEvolutionLoading(false);
  }
}

function dataParams() {
  const params = connectionParams();
  const maxObjects = Number(bdeEl["bde-max-objects"].value);
  if (Number.isFinite(maxObjects) && maxObjects > 0) params.set("max_objects", String(Math.floor(maxObjects)));
  const sptRange = (bdeEl["bde-spt-range"].value || BDE_DEFAULT_SPT_RANGE).trim();
  params.set("spt_range", sptRange || BDE_DEFAULT_SPT_RANGE);
  params.set("track_model", bdeEl["bde-track-model"].value || BDE_DEFAULT_TRACK_MODEL);
  params.set("ya_prob_min", String(bdEvolutionYaProbMin()));
  const highlightOids = bdEvolutionHighlightedOids();
  if (highlightOids.length) params.set("moca_oid", highlightOids.join(","));
  params.set("ignore_aids", "");
  return params;
}

function connectionParams() {
  const current = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "port", "user", "pwd", "dbase", "db", "database", "mock"]) {
    if (current.has(key)) params.set(key, current.get(key) || "");
  }
  return params;
}

function updateBdEvolutionUrl() {
  const params = new URLSearchParams(window.location.search);
  for (const key of ["x", "xaxis", "y", "yaxis", "xlog", "x_log", "ylog", "y_log", "track_model", "model_track", "track_set", "spt_range", "spt", "ya_prob_min", "min_ya_prob", "membership_prob_min", "min_membership_probability", "ignore_aids", "ignored_aids", "exclude_aids", "excluded_aids", "ignore_groups", "ignored_groups", "exclude_groups", "excluded_groups", "ignore_memberships", "ignored_memberships", "exclude_memberships", "excluded_memberships", "oid", "oids", "moca_oid", "moca_oids", "remove_companions", "exclude_companions", "no_companions", "age_jitter", "jitter", "hover", "data_hover", "datahover", "track_hover", "trackhover", "model_hover", "modelhover", "max_objects", "limit"]) {
    params.delete(key);
  }
  params.set("x", bdeEl["bde-x-axis"].value || "age_myr");
  params.set("y", bdeEl["bde-y-axis"].value || "teff_k");
  params.set("xlog", bdeEl["bde-x-log"].checked ? "1" : "0");
  params.set("ylog", bdeEl["bde-y-log"].checked ? "1" : "0");
  params.set("track_model", bdeEl["bde-track-model"].value || BDE_DEFAULT_TRACK_MODEL);
  params.set("spt_range", (bdeEl["bde-spt-range"].value || BDE_DEFAULT_SPT_RANGE).trim() || BDE_DEFAULT_SPT_RANGE);
  params.set("ya_prob_min", String(bdEvolutionYaProbMin()));
  params.set("ignore_aids", bdEvolutionIgnoredMembershipAidsText());
  const highlightOids = bdEvolutionHighlightedOids();
  if (highlightOids.length) params.set("moca_oid", highlightOids.join(","));
  params.set("age_jitter", String(bdEvolutionAgeJitterDex()));
  params.set("data_hover", bdeEl["bde-data-hover"].checked ? "1" : "0");
  params.set("track_hover", bdeEl["bde-track-hover"].checked ? "1" : "0");
  if (bdeEl["bde-remove-companions"].checked) params.set("remove_companions", "1");
  const maxObjects = Number(bdeEl["bde-max-objects"].value);
  if (Number.isFinite(maxObjects) && maxObjects > 0) params.set("max_objects", String(Math.floor(maxObjects)));
  const next = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ""}${window.location.hash}`;
  window.history.replaceState({}, "", next);
}

function applyBdEvolutionTrackDefaultForAxes(force = false) {
  if (!force && bdeState.tracksDefaultInitialized) return;
  const groupingMode = bdEvolutionTrackGroupingMode(
    bdeEl["bde-x-axis"].value || "age_myr",
    bdeEl["bde-y-axis"].value || "teff_k",
  );
  bdeEl["bde-tracks"].checked = groupingMode === "iso_age" || groupingMode === "isotherm" || !bdEvolutionAxesIncludeMass();
  bdeState.tracksDefaultInitialized = true;
}

function bdEvolutionAxesIncludeMass() {
  return bdeEl["bde-x-axis"].value === "mass_mjup" || bdeEl["bde-y-axis"].value === "mass_mjup";
}

function updateBdEvolutionTrackHoverControl() {
  const disabled = !bdeEl["bde-tracks"].checked || !bdeState.tracks.length;
  bdeEl["bde-track-hover"].disabled = disabled;
  bdeEl["bde-track-hover-line"]?.classList.toggle("is-disabled", disabled);
}

function bdEvolutionObservableCategory(row) {
  const raw = String(row.banyan_observables || row.observables || "").trim().toLowerCase();
  if (!raw) return bdEvolutionObservableSpec("none");
  const tokens = new Set(raw.split(/[^a-z0-9]+/).filter(Boolean));
  const hasRv = tokens.has("rv") || tokens.has("radial") || tokens.has("radialvelocity");
  const hasPlx = tokens.has("plx") || tokens.has("parallax") || tokens.has("dist") || tokens.has("distance");
  const isPhotometricDistance = hasPlx && Number(row.banyan_distance_photometric || 0) === 1;
  if (hasRv && isPhotometricDistance) return bdEvolutionObservableSpec("pm_rv_photdist");
  if (hasRv && hasPlx) return bdEvolutionObservableSpec("pm_rv_plx");
  if (isPhotometricDistance) return bdEvolutionObservableSpec("pm_photdist");
  if (hasPlx) return bdEvolutionObservableSpec("pm_plx");
  if (hasRv) return bdEvolutionObservableSpec("pm_rv");
  if (tokens.has("pm") || tokens.has("proper") || tokens.has("propermotion")) return bdEvolutionObservableSpec("pm");
  return bdEvolutionObservableSpec("other");
}

function bdEvolutionObservableSpec(key) {
  return bdeObservableSymbols.find((item) => item.key === key) || bdeObservableSymbols[bdeObservableSymbols.length - 1];
}

function enrichBdEvolutionRow(row) {
  const oid = coerceMocaOid(row.moca_oid);
  const highlighted = oid !== null && bdEvolutionHighlightedOidSet().has(oid);
  const age = finiteNumber(row.age_myr);
  const jitterSeed = `${oid ?? row.designation ?? ""}|${row.spt ?? ""}|${age ?? ""}`;
  const radiusRsun = finiteNumber(row.radius_rsun);
  const radiusRsunUnc = finiteNumber(row.radius_rsun_unc);
  const radiusRjup = finiteNumber(row.radius_rjup) ?? (radiusRsun === null ? null : radiusRsun / BDE_RJUP_TO_RSUN);
  const radiusRjupUnc = finiteNumber(row.radius_rjup_unc) ?? (radiusRsunUnc === null ? null : radiusRsunUnc / BDE_RJUP_TO_RSUN);
  return {
    ...row,
    moca_oid: oid,
    radius_rjup: radiusRjup,
    radius_rjup_unc: radiusRjupUnc,
    _oid: oid,
    _highlighted: highlighted,
    _age_jitter_normal: deterministicNormal(jitterSeed),
    _reportUrl: row.report_url || (oid !== null ? `https://mocadb.ca/search/results?search-query=oid%28${oid}%29&search-type=star` : null),
  };
}

function enrichBdEvolutionTrackRow(row) {
  const radiusRsun = finiteNumber(row.radius_rsun);
  const radiusRjup = finiteNumber(row.radius_rjup) ?? (radiusRsun === null ? null : radiusRsun / BDE_RJUP_TO_RSUN);
  return {
    ...row,
    radius_rjup: radiusRjup,
  };
}

function normalizeBdEvolutionAxisKey(key) {
  if (key === "radius_rsun") return "radius_rjup";
  return key;
}

function renderBdEvolutionPlot() {
  if (!bdeState.payload) {
    renderBdEvolutionEmptyPlot("No data loaded");
    return;
  }
  rememberBdEvolutionLegendVisibility(bdeEl["bde-plot"]?.data || []);
  const xKey = bdeEl["bde-x-axis"].value || "age_myr";
  const yKey = bdeEl["bde-y-axis"].value || "teff_k";
  const xLog = bdeEl["bde-x-log"].checked;
  const yLog = bdeEl["bde-y-log"].checked;
  const dataHover = bdeEl["bde-data-hover"].checked;
  const trackHover = bdeEl["bde-track-hover"].checked && bdeEl["bde-tracks"].checked;
  const plotRows = bdEvolutionDisplayRows().filter((row) => rowIsPlottable(row, xKey, yKey, xLog, yLog, true));
  const traces = [];
  if (bdeEl["bde-tracks"].checked) {
    traces.push(...buildBdEvolutionTrackTraces(xKey, yKey, xLog, yLog, trackHover));
  }
  traces.push(...buildBdEvolutionObjectTraces(plotRows, xKey, yKey, dataHover));
  const highlightedRows = plotRows.filter((row) => row._highlighted);
  if (highlightedRows.length) traces.push(buildBdEvolutionHighlightedTrace(highlightedRows, xKey, yKey, dataHover));
  if (plotRows.some(bdEvolutionIsCompanion)) traces.push(buildBdEvolutionCompanionLegendTrace());
  applyBdEvolutionStoredLegendVisibility(traces);
  const layout = bdEvolutionLayout(xKey, yKey, xLog, yLog, plotRows.length);
  if (bdeEl["bde-tracks"].checked) {
    layout.annotations.push(...buildBdEvolutionTrackMassAnnotations(xKey, yKey, xLog, yLog, layout));
    layout.annotations.push(...buildBdEvolutionIsothermAnnotations(xKey, yKey, xLog, yLog, layout));
  }
  updateBdEvolutionTrackHoverControl();
  clearBdEvolutionPlotEvents();
  Plotly.react(bdeEl["bde-plot"], traces, layout, plotConfig("brown_dwarf_evolution"));
  bindBdEvolutionPlotEvents();
  updateBdEvolutionSummary();
}

function buildBdEvolutionObjectTraces(rows, xKey, yKey, hover) {
  const grouped = new Map();
  for (const row of rows) {
    const category = bdEvolutionObservableCategory(row);
    if (!grouped.has(category.key)) grouped.set(category.key, { ...category, rows: [] });
    grouped.get(category.key).rows.push(row);
  }
  return bdeObservableSymbols
    .map((spec) => grouped.get(spec.key))
    .filter(Boolean)
    .flatMap((group) => buildBdEvolutionObjectTraceSet(group, xKey, yKey, hover));
}

function bdEvolutionSecurityRank(group) {
  const rank = finiteNumber(group?.securityRank);
  if (rank === null) return null;
  return Math.max(0, Math.min(BDE_SECURITY_CLASS_COUNT - 1, Math.round(rank)));
}

function bdEvolutionSecurityFraction(group) {
  const rank = bdEvolutionSecurityRank(group);
  if (rank === null) return null;
  return rank / Math.max(1, BDE_SECURITY_CLASS_COUNT - 1);
}

function bdEvolutionClassColor(group) {
  const rank = bdEvolutionSecurityRank(group);
  if (rank === null) return "#6f6a73";
  return BDE_SECURITY_CLASS_COLORS[rank] || BDE_SECURITY_CLASS_COLORS[BDE_SECURITY_CLASS_COLORS.length - 1];
}

function bdEvolutionClassMarkerSize(group, selected = false) {
  const fraction = bdEvolutionSecurityFraction(group);
  const minSize = selected ? BDE_MARKER_SELECTED_MIN_SIZE : BDE_MARKER_MIN_SIZE;
  const maxSize = selected ? BDE_MARKER_SELECTED_MAX_SIZE : BDE_MARKER_MAX_SIZE;
  const baseSize = fraction === null ? minSize : minSize + (maxSize - minSize) * fraction;
  const securityMultiplier = fraction === null
    ? 1
    : BDE_SECURITY_SIZE_MIN_MULTIPLIER
      + (BDE_SECURITY_SIZE_MAX_MULTIPLIER - BDE_SECURITY_SIZE_MIN_MULTIPLIER) * fraction;
  return baseSize * securityMultiplier * (BDE_SYMBOL_SIZE_MULTIPLIERS[group?.symbol] || 1);
}

function buildBdEvolutionObjectTraceSet(group, xKey, yKey, hover) {
  const companionRows = group.rows.filter(bdEvolutionIsCompanion);
  const objectRows = group.rows.filter((row) => !bdEvolutionIsCompanion(row));
  const traces = [];
  if (objectRows.length) {
    traces.push(buildBdEvolutionObjectTrace({ ...group, rows: objectRows }, xKey, yKey, hover, {
      edgeColor: BDE_MARKER_EDGE_COLOR,
      showlegend: true,
      traceKind: "object",
    }));
  } else if (companionRows.length) {
    traces.push(buildBdEvolutionObjectTrace({ ...group, rows: [] }, xKey, yKey, false, {
      edgeColor: BDE_MARKER_EDGE_COLOR,
      legendOnly: true,
      showlegend: true,
      traceKind: "object-legend",
    }));
  }
  if (companionRows.length) {
    traces.push(buildBdEvolutionObjectTrace({ ...group, rows: companionRows }, xKey, yKey, hover, {
      edgeColor: BDE_COMPANION_EDGE_COLOR,
      showlegend: false,
      traceKind: "companion",
      visible: bdeState.companionsHiddenByLegend ? "legendonly" : undefined,
    }));
  }
  return traces;
}

function buildBdEvolutionObjectTrace(group, xKey, yKey, hover, options = {}) {
  const rows = group.rows;
  const legendOnly = Boolean(options.legendOnly);
  const markerColor = bdEvolutionClassColor(group);
  const markerSize = bdEvolutionClassMarkerSize(group, false);
  const selectedMarkerSize = bdEvolutionClassMarkerSize(group, true);
  return {
    type: rows.length > 25000 ? "scattergl" : "scatter",
    mode: "markers",
    name: group.label,
    x: legendOnly ? [null] : rows.map((row) => plotValue(row, xKey, true)),
    y: legendOnly ? [null] : rows.map((row) => plotValue(row, yKey, true)),
    customdata: legendOnly ? [null] : rows.map((row) => row._oid),
    text: legendOnly ? [""] : rows.map(hoverText),
    selectedpoints: legendOnly ? null : selectedPointIndices(rows),
    marker: {
      color: markerColor,
      symbol: group.symbol,
      size: legendOnly ? markerSize : rows.map((row) => bdeState.selectedOids.has(row._oid) ? selectedMarkerSize : markerSize),
      opacity: 0.88,
      line: { color: options.edgeColor || BDE_MARKER_EDGE_COLOR, width: 1.4 },
    },
    selected: { marker: { opacity: 1, size: selectedMarkerSize } },
    unselected: { marker: { opacity: bdeState.selectedOids.size ? 0.24 : 0.88 } },
    legendgroup: `object-${group.key}`,
    showlegend: options.showlegend !== false,
    meta: { bdeRole: "object", bdeCategory: group.key, bdeTraceKind: options.traceKind || "object" },
    visible: options.visible,
    hovertemplate: hover && !legendOnly ? "%{text}<extra></extra>" : undefined,
    hoverinfo: hover && !legendOnly ? undefined : "none",
  };
}

function buildBdEvolutionHighlightedTrace(rows, xKey, yKey, hover) {
  return {
    type: rows.length > 25000 ? "scattergl" : "scatter",
    mode: "markers",
    name: "Target OID",
    x: rows.map((row) => plotValue(row, xKey, true)),
    y: rows.map((row) => plotValue(row, yKey, true)),
    customdata: rows.map((row) => row._oid),
    text: rows.map(hoverText),
    selectedpoints: selectedPointIndices(rows),
    marker: {
      symbol: "circle-open",
      size: rows.map((row) => bdeState.selectedOids.has(row._oid) ? 28 : 24),
      color: BDE_HIGHLIGHT_HALO_COLOR,
      line: { color: BDE_HIGHLIGHT_EDGE_COLOR, width: 2.8 },
    },
    selected: { marker: { opacity: 1, size: 30 } },
    unselected: { marker: { opacity: bdeState.selectedOids.size ? 0.55 : 1 } },
    legendgroup: "target-oids",
    showlegend: true,
    meta: { bdeRole: "target-oid" },
    hovertemplate: hover ? "%{text}<extra></extra>" : undefined,
    hoverinfo: hover ? undefined : "none",
  };
}

function bdEvolutionIsCompanion(row) {
  return finiteNumber(row?.is_companion) > 0;
}

function bdEvolutionDisplayRows() {
  const ignoredAids = bdEvolutionIgnoredMembershipAids();
  return bdeState.rows.filter((row) => {
    if (row._highlighted) return true;
    if (ignoredAids.includes(String(row.membership || "").toUpperCase())) return false;
    if (bdeEl["bde-remove-companions"]?.checked && bdEvolutionIsCompanion(row)) return false;
    return true;
  });
}

function bdEvolutionRowsAfterIgnoredGroups() {
  const ignoredAids = bdEvolutionIgnoredMembershipAids();
  if (!ignoredAids.length) return bdeState.rows;
  return bdeState.rows.filter((row) => row._highlighted || !ignoredAids.includes(String(row.membership || "").toUpperCase()));
}

function buildBdEvolutionCompanionLegendTrace() {
  return {
    type: "scatter",
    mode: "markers",
    name: "Companion",
    x: [null],
    y: [null],
    marker: {
      symbol: "circle",
      size: 12,
      color: "rgba(255,255,255,0)",
      line: { color: BDE_COMPANION_EDGE_COLOR, width: 2 },
    },
    showlegend: true,
    visible: bdeState.companionsHiddenByLegend ? "legendonly" : undefined,
    hoverinfo: "none",
    meta: { bdeRole: "companion-legend" },
  };
}

function buildBdEvolutionTrackTraces(xKey, yKey, xLog, yLog, hover) {
  const { groupingMode, groups } = bdEvolutionTrackGroups(xKey, yKey, xLog, yLog);
  const colorbarTrace = buildBdEvolutionTrackColorbarTrace(groups, groupingMode, xKey, yKey);
  const withColorbar = (traces) => colorbarTrace ? [...traces, colorbarTrace] : traces;
  if (groupingMode === "isotherm") {
    return withColorbar(buildBdEvolutionIsothermTraces(groups, xKey, yKey, hover));
  }
  const massBoundaryKeys = groupingMode === "iso_mass" ? bdEvolutionBoundaryMassKeys(groups) : new Set();
  const traces = groups.map((group) => {
    const style = bdEvolutionTrackStyle(group, groups, massBoundaryKeys);
    const label = group.label;
    return {
      type: "scatter",
      mode: "lines",
      name: label,
      legendgroup: "tracks",
      showlegend: false,
      meta: { bdeRole: "model-track", bdeTrackMode: groupingMode },
      x: group.rows.map((row) => Number(row[xKey])),
      y: group.rows.map((row) => Number(row[yKey])),
      text: group.rows.map((row) => trackHoverText(row, label)),
      line: bdEvolutionTrackLineStyle(style, groupingMode, xKey, yKey),
      opacity: style.opacity,
      hovertemplate: hover ? "%{text}<extra></extra>" : undefined,
      hoverinfo: hover ? undefined : "none",
    };
  });
  return withColorbar(traces);
}

function buildBdEvolutionIsothermTraces(groups, xKey, yKey, hover) {
  return groups.map((group) => {
    const style = bdEvolutionIsothermStyle(group, groups);
    const label = group.label;
    return {
      type: "scatter",
      mode: "lines",
      name: label,
      legendgroup: "tracks",
      showlegend: false,
      meta: { bdeRole: "model-track", bdeTrackMode: "isotherm" },
      x: group.rows.map((row) => Number(row[xKey])),
      y: group.rows.map((row) => Number(row[yKey])),
      text: group.rows.map((row) => trackHoverText(row, label)),
      line: { color: style.color, width: style.width },
      opacity: style.opacity,
      hovertemplate: hover ? "%{text}<extra></extra>" : undefined,
      hoverinfo: hover ? undefined : "none",
    };
  });
}

function bdEvolutionTrackLineStyle(style, groupingMode, xKey, yKey) {
  const line = { color: style.color, width: style.width };
  if (groupingMode === "iso_age" && bdEvolutionUsesMassRadiusAxes(xKey, yKey)) {
    line.shape = "spline";
    line.smoothing = 0.55;
  }
  return line;
}

function buildBdEvolutionTrackColorbarTrace(groups, groupingMode, xKey, yKey) {
  const values = groups
    .map((group) => finiteNumber(group.sortValue))
    .filter((value) => value !== null);
  if (!values.length) return null;
  const anchor = bdEvolutionTrackColorbarAnchor(groups, xKey, yKey);
  if (!anchor) return null;
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const span = maxValue - minValue;
  const cmin = span > 0 ? minValue : minValue - 1;
  const cmax = span > 0 ? maxValue : maxValue + 1;
  return {
    type: "scatter",
    mode: "markers",
    name: "Model tracks",
    x: [anchor.x, anchor.x],
    y: [anchor.y, anchor.y],
    marker: {
      color: [cmin, cmax],
      cmin,
      cmax,
      colorscale: bdEvolutionTrackColorScale(groupingMode),
      showscale: true,
      size: 0.1,
      opacity: 0,
      colorbar: {
        title: {
          text: bdEvolutionTrackColorbarTitle(groupingMode),
          side: "top",
          font: { size: 11 },
        },
        x: 1.035,
        xanchor: "left",
        y: 0.31,
        yanchor: "middle",
        len: 0.52,
        thickness: 12,
        tickfont: { size: 10 },
        outlinewidth: 0,
      },
    },
    showlegend: false,
    hoverinfo: "none",
    meta: { bdeRole: "model-track", bdeTraceKind: "model-colorbar", bdeTrackMode: groupingMode },
  };
}

function bdEvolutionTrackColorbarAnchor(groups, xKey, yKey) {
  for (const group of groups || []) {
    for (const row of group.rows || []) {
      const x = finiteNumber(row[xKey]);
      const y = finiteNumber(row[yKey]);
      if (x !== null && y !== null) return { x, y };
    }
  }
  return null;
}

function bdEvolutionTrackColorbarTitle(groupingMode) {
  if (groupingMode === "isotherm") return "Model tracks<br><i>T</i><sub>eff</sub> (K)";
  if (groupingMode === "iso_age") return "Model tracks<br>Age (Myr)";
  return `Model tracks<br>Mass (${BDE_MJUP_UNIT_HTML})`;
}

function bdEvolutionTrackColorScale(groupingMode) {
  if (groupingMode === "isotherm") {
    return [0, 0.25, 0.5, 0.75, 1].map((value) => [value, bdEvolutionIsothermColor(value)]);
  }
  return bdeTerrainStops.map(([value, color]) => [value, terrainRgbFromChannels(color)]);
}

function bdEvolutionTrackGroups(xKey, yKey, xLog, yLog) {
  const groupingMode = bdEvolutionTrackGroupingMode(xKey, yKey);
  if (groupingMode === "isotherm") {
    return { groupingMode, groups: buildBdEvolutionIsothermGroups(xKey, yKey, xLog, yLog) };
  }
  const grouped = new Map();
  for (const row of bdeState.tracks || []) {
    if (!rowIsPlottable(row, xKey, yKey, xLog, yLog)) continue;
    const group = bdEvolutionTrackGroup(row, groupingMode);
    if (!grouped.has(group.key)) grouped.set(group.key, { ...group, rows: [] });
    grouped.get(group.key).rows.push(row);
  }
  const groups = Array.from(grouped.values())
    .map((group) => ({
      ...group,
      rows: bdEvolutionCleanModelTrackRows(
        group.rows.sort((a, b) => bdEvolutionTrackRowSort(a, b, xKey, yKey, groupingMode)),
        groupingMode,
        xKey,
        yKey,
      ),
    }))
    .sort((a, b) => a.sortValue - b.sortValue);
  return { groupingMode, groups };
}

function bdEvolutionCleanModelTrackRows(rows, groupingMode, xKey, yKey) {
  if (groupingMode === "iso_age" && bdEvolutionUsesMassRadiusAxes(xKey, yKey)) {
    return bdEvolutionSmoothMassRadiusIsoAgeRows(rows);
  }
  return rows;
}

function bdEvolutionSmoothMassRadiusIsoAgeRows(rows) {
  if (rows.length < 5) return rows;
  const sortedRows = rows
    .slice()
    .sort((a, b) => {
      const massA = finiteNumber(a.mass_mjup);
      const massB = finiteNumber(b.mass_mjup);
      if (massA === null || massB === null) return 0;
      return massA - massB;
    });
  const radii = sortedRows.map((row) => finiteNumber(row.radius_rjup));
  if (radii.some((value) => value === null)) return sortedRows;
  const smoothedRadii = bdEvolutionSmoothRadiusSeries(radii);
  return sortedRows.map((row, index) => ({
    ...row,
    radius_rjup: smoothedRadii[index],
    radius_rsun: smoothedRadii[index] * BDE_RJUP_TO_RSUN,
  }));
}

function bdEvolutionSmoothRadiusSeries(values) {
  let out = values.slice();
  for (let pass = 0; pass < BDE_MASS_RADIUS_SMOOTH_PASSES; pass += 1) {
    const next = out.slice();
    for (let index = 1; index < out.length - 1; index += 1) {
      const candidate = 0.25 * out[index - 1] + 0.5 * out[index] + 0.25 * out[index + 1];
      const correction = candidate - out[index];
      if (Math.abs(correction) < BDE_MASS_RADIUS_SMOOTH_MIN_CORRECTION_RJUP) continue;
      next[index] = out[index] + clampNumber(
        correction,
        -BDE_MASS_RADIUS_SMOOTH_MAX_CORRECTION_RJUP,
        BDE_MASS_RADIUS_SMOOTH_MAX_CORRECTION_RJUP,
      );
    }
    out = next;
  }
  return out;
}

function buildBdEvolutionIsothermGroups(xKey, yKey, xLog, yLog) {
  const massTracks = bdEvolutionMassTrackRows(xKey, yKey, xLog, yLog);
  const sourceRows = massTracks.flatMap((group) => group.rows);
  return bdEvolutionIsothermTargets(sourceRows)
    .map((teff) => {
      const crossingRows = massTracks
        .map((massTrack) => bdEvolutionIsothermPointForMassTrack(massTrack.rows, teff))
        .filter(Boolean);
      const rows = bdEvolutionCleanAgeMassIsothermRows(crossingRows, xKey, yKey)
        .sort((a, b) => bdEvolutionTrackRowSort(a, b, xKey, yKey, "isotherm"));
      return {
        key: `teff:${teff}`,
        label: `Teff = ${formatCell(teff)} K`,
        sortValue: teff,
        rows,
      };
    })
    .filter((group) => group.rows.length >= BDE_ISOTHERM_MIN_POINTS);
}

function bdEvolutionMassTrackRows(xKey, yKey, xLog, yLog) {
  const grouped = new Map();
  for (const row of bdeState.tracks || []) {
    if (!rowIsPlottable(row, xKey, yKey, xLog, yLog)) continue;
    const age = finiteNumber(row.age_myr);
    const mass = finiteNumber(row.track_mass_mjup) ?? finiteNumber(row.mass_mjup);
    const teff = finiteNumber(row.teff_k);
    if (age === null || mass === null || teff === null || age <= 0 || mass <= 0) continue;
    const key = bdEvolutionMassKey(mass);
    if (!grouped.has(key)) grouped.set(key, { mass, rows: [] });
    grouped.get(key).rows.push(row);
  }
  return Array.from(grouped.values())
    .map((group) => ({ ...group, rows: group.rows.sort((a, b) => Number(a.age_myr) - Number(b.age_myr)) }))
    .filter((group) => group.rows.length >= 2)
    .sort((a, b) => a.mass - b.mass);
}

function bdEvolutionIsothermTargets(rows) {
  const values = rows
    .map((row) => finiteNumber(row.teff_k))
    .filter((value) => value !== null && value > 0);
  if (!values.length) return [];
  const minTeff = Math.min(...values);
  const maxTeff = Math.max(...values);
  return BDE_ISOTHERM_TARGET_TEFF_K.filter((teff) => teff >= minTeff && teff <= maxTeff);
}

function bdEvolutionIsothermPointForMassTrack(rows, teff) {
  const crossings = [];
  for (let index = 1; index < rows.length; index += 1) {
    const before = rows[index - 1];
    const after = rows[index];
    const beforeTeff = finiteNumber(before.teff_k);
    const afterTeff = finiteNumber(after.teff_k);
    if (beforeTeff === null || afterTeff === null) continue;
    const deltaTeff = afterTeff - beforeTeff;
    const lo = Math.min(beforeTeff, afterTeff);
    const hi = Math.max(beforeTeff, afterTeff);
    if (teff < lo || teff > hi) continue;
    if (Math.abs(deltaTeff) < 1e-9) continue;
    const fraction = (teff - beforeTeff) / deltaTeff;
    const age = bdEvolutionInterpolateAge(before.age_myr, after.age_myr, fraction);
    const mass = bdEvolutionInterpolateLinear(
      finiteNumber(before.track_mass_mjup) ?? finiteNumber(before.mass_mjup),
      finiteNumber(after.track_mass_mjup) ?? finiteNumber(after.mass_mjup),
      fraction,
    );
    if (age === null || mass === null) continue;
    crossings.push({
      row: {
        ...before,
        age_myr: age,
        mass_mjup: mass,
        mass_msun: mass / BDE_MSUN_TO_MJUP,
        track_mass_mjup: mass,
        teff_k: teff,
        track_id: `${formatCell(teff)} K`,
      },
      age,
      coolingBranch: beforeTeff >= afterTeff,
    });
  }
  if (!crossings.length) return null;
  const candidates = crossings.filter((crossing) => crossing.coolingBranch);
  return (candidates.length ? candidates : crossings)
    .reduce((best, crossing) => {
      if (!best) return crossing;
      return crossing.age > best.age ? crossing : best;
    }, null).row;
}

function bdEvolutionCleanAgeMassIsothermRows(rows, xKey, yKey) {
  if (!bdEvolutionUsesAgeMassAxes(xKey, yKey) || rows.length < 4) return rows;
  // Stitched tracks can contain small Teff loops; keep the longest ordered cooling-branch path.
  const sortedRows = rows
    .slice()
    .sort((a, b) => {
      const massA = finiteNumber(a.track_mass_mjup) ?? finiteNumber(a.mass_mjup);
      const massB = finiteNumber(b.track_mass_mjup) ?? finiteNumber(b.mass_mjup);
      if (massA === null || massB === null) return 0;
      return massA - massB;
    });
  const logAges = sortedRows.map((row) => {
    const age = finiteNumber(row.age_myr);
    return age !== null && age > 0 ? Math.log(age) : null;
  });
  if (logAges.some((value) => value === null)) return rows;
  const keepIndexes = bdEvolutionLongestNondecreasingIndexes(logAges);
  if (keepIndexes.length < BDE_ISOTHERM_MIN_POINTS) return sortedRows;
  return keepIndexes.map((index) => sortedRows[index]);
}

function bdEvolutionUsesAgeMassAxes(xKey, yKey) {
  const axes = new Set([xKey, yKey]);
  return axes.has("age_myr") && axes.has("mass_mjup");
}

function bdEvolutionUsesMassRadiusAxes(xKey, yKey) {
  const axes = new Set([xKey, yKey]);
  return axes.has("mass_mjup") && axes.has("radius_rjup");
}

function bdEvolutionLongestNondecreasingIndexes(values) {
  const lengths = values.map(() => 1);
  const previous = values.map(() => -1);
  let bestIndex = 0;
  for (let index = 1; index < values.length; index += 1) {
    for (let before = 0; before < index; before += 1) {
      if (values[index] < values[before]) continue;
      const candidateLength = lengths[before] + 1;
      if (candidateLength > lengths[index]) {
        lengths[index] = candidateLength;
        previous[index] = before;
      }
    }
    if (lengths[index] >= lengths[bestIndex]) bestIndex = index;
  }
  const out = [];
  for (let index = bestIndex; index >= 0; index = previous[index]) {
    out.push(index);
    if (previous[index] < 0) break;
  }
  return out.reverse();
}

function bdEvolutionInterpolateAge(before, after, fraction) {
  const beforeAge = finiteNumber(before);
  const afterAge = finiteNumber(after);
  if (beforeAge === null || afterAge === null || beforeAge <= 0 || afterAge <= 0) return null;
  const logAge = Math.log(beforeAge) + fraction * (Math.log(afterAge) - Math.log(beforeAge));
  const age = Math.exp(logAge);
  return Number.isFinite(age) ? age : null;
}

function bdEvolutionInterpolateLinear(before, after, fraction) {
  if (before === null || after === null) return null;
  const value = before + fraction * (after - before);
  return Number.isFinite(value) ? value : null;
}

function bdEvolutionTrackGroupingMode(xKey, yKey) {
  const axes = new Set([xKey, yKey]);
  if (axes.has("age_myr") && axes.has("mass_mjup")) return "isotherm";
  if (axes.has("teff_k") && axes.has("mass_mjup")) return "iso_age";
  if (axes.has("mass_mjup") && axes.has("radius_rjup")) return "iso_age";
  return "iso_mass";
}

function bdEvolutionTrackGroup(row, groupingMode) {
  if (groupingMode === "iso_age") {
    const age = finiteNumber(row.age_myr);
    return {
      key: age === null ? "age:unknown" : `age:${age.toFixed(7)}`,
      label: age === null ? "Age unknown" : `Age = ${formatTrackAge(age)}`,
      sortValue: age === null ? Number.POSITIVE_INFINITY : age,
    };
  }
  const mass = finiteNumber(row.track_mass_mjup) ?? finiteNumber(row.mass_mjup);
  return {
    key: row.track_id || (mass === null ? "track" : `mass:${mass.toFixed(6)}`),
    label: mass === null ? String(row.track_id || "Model track") : bdEvolutionMassHtml(mass),
    sortValue: mass === null ? Number.POSITIVE_INFINITY : mass,
  };
}

function bdEvolutionTrackStyle(group, groups, massBoundaryKeys) {
  if (massBoundaryKeys.has(group.key)) {
    return { color: "#000000", width: 3, opacity: 0.92 };
  }
  return {
    color: bdEvolutionTerrainColor(group.sortValue, groups.map((item) => item.sortValue)),
    width: 1.25,
    opacity: 0.66,
  };
}

function bdEvolutionIsothermStyle(group, groups) {
  const values = groups
    .map((item) => finiteNumber(item.sortValue))
    .filter((value) => value !== null);
  const minValue = values.length ? Math.min(...values) : group.sortValue;
  const maxValue = values.length ? Math.max(...values) : group.sortValue;
  const span = maxValue - minValue;
  const fraction = span > 0 ? (group.sortValue - minValue) / span : 0.5;
  return {
    color: bdEvolutionIsothermColor(fraction),
    width: 1.65,
    opacity: 0.82,
  };
}

function bdEvolutionBoundaryMassKeys(groups) {
  const finiteGroups = groups.filter((group) => Number.isFinite(group.sortValue));
  const out = new Set();
  for (const target of BDE_MASS_BOUNDARY_TARGETS_MJUP) {
    const nearest = finiteGroups.reduce((best, group) => {
      if (!best) return group;
      return Math.abs(group.sortValue - target) < Math.abs(best.sortValue - target) ? group : best;
    }, null);
    if (nearest) out.add(nearest.key);
  }
  return out;
}

function buildBdEvolutionTrackMassAnnotations(xKey, yKey, xLog, yLog, layout) {
  const { groupingMode, groups } = bdEvolutionTrackGroups(xKey, yKey, xLog, yLog);
  if (groupingMode !== "iso_mass" || !groups.length) return [];

  const massBoundaryKeys = bdEvolutionBoundaryMassKeys(groups);
  const visibleGroups = groups
    .map((group) => {
      const mass = finiteNumber(group.sortValue);
      if (mass === null) return null;
      const rows = group.rows.filter((row) => bdEvolutionPointInAxisRanges(
        Number(row[xKey]),
        Number(row[yKey]),
        layout.xaxis,
        layout.yaxis,
      ));
      if (!rows.length) return null;
      return {
        group,
        mass,
        rows,
        style: bdEvolutionTrackStyle(group, groups, massBoundaryKeys),
        point: bdEvolutionMassLabelPoint(rows, xKey, yKey, layout.xaxis),
      };
    })
    .filter((item) => item && item.point)
    .sort((a, b) => a.mass - b.mass);

  return selectBdEvolutionMassLabelGroups(visibleGroups)
    .map((item) => ({
      x: bdEvolutionAnnotationCoordinate(item.point.x, layout.xaxis),
      y: bdEvolutionAnnotationCoordinate(item.point.y, layout.yaxis),
      xref: "x",
      yref: "y",
      text: bdEvolutionMassHtml(item.labelMass),
      showarrow: false,
      xanchor: "left",
      yanchor: "middle",
      xshift: 5,
      bgcolor: "rgba(255,255,255,0.68)",
      bordercolor: "rgba(255,255,255,0)",
      borderpad: 1,
      font: {
        size: 10,
        color: item.style.color,
        family: "Arial, sans-serif",
      },
    }));
}

function buildBdEvolutionIsothermAnnotations(xKey, yKey, xLog, yLog, layout) {
  const { groupingMode, groups } = bdEvolutionTrackGroups(xKey, yKey, xLog, yLog);
  if (groupingMode !== "isotherm" || !groups.length) return [];
  const visibleGroups = groups
    .map((group) => {
      const rows = group.rows.filter((row) => bdEvolutionPointInAxisRanges(
        Number(row[xKey]),
        Number(row[yKey]),
        layout.xaxis,
        layout.yaxis,
      ));
      if (!rows.length) return null;
      return {
        group,
        rows,
        style: bdEvolutionIsothermStyle(group, groups),
        point: bdEvolutionMassLabelPoint(rows, xKey, yKey, layout.xaxis),
      };
    })
    .filter((item) => item && item.point)
    .sort((a, b) => a.group.sortValue - b.group.sortValue);

  return evenlySpacedItems(visibleGroups, BDE_ISOTHERM_LABEL_COUNT)
    .map((item) => ({
      x: bdEvolutionAnnotationCoordinate(item.point.x, layout.xaxis),
      y: bdEvolutionAnnotationCoordinate(item.point.y, layout.yaxis),
      xref: "x",
      yref: "y",
      text: htmlEscape(`${formatCell(item.group.sortValue)} K`),
      showarrow: false,
      xanchor: "left",
      yanchor: "middle",
      xshift: 5,
      bgcolor: "rgba(255,255,255,0.68)",
      bordercolor: "rgba(255,255,255,0)",
      borderpad: 1,
      font: {
        size: 10,
        color: item.style.color,
        family: "Arial, sans-serif",
      },
    }));
}

function selectBdEvolutionMassLabelGroups(visibleGroups) {
  const selected = [];
  const usedKeys = new Set();
  const usedLabels = new Set();
  const add = (item, labelMass) => {
    if (!item || usedKeys.has(item.group.key)) return false;
    const roundedLabel = Number.isFinite(labelMass) ? Math.round(labelMass) : Math.round(item.mass);
    if (!bdEvolutionValidMassLabel(roundedLabel) || usedLabels.has(roundedLabel)) return false;
    selected.push({ ...item, labelMass: roundedLabel });
    usedKeys.add(item.group.key);
    usedLabels.add(roundedLabel);
    return true;
  };

  for (const target of BDE_MASS_BOUNDARY_TARGETS_MJUP) {
    const nearest = visibleGroups.reduce((best, item) => {
      const delta = Math.abs(item.mass - target);
      if (delta > BDE_MASS_TARGET_LABEL_TOLERANCE_MJUP) return best;
      if (!best || delta < Math.abs(best.mass - target)) return item;
      return best;
    }, null);
    add(nearest, target);
  }

  const candidateByLabel = new Map();
  visibleGroups
    .filter((item) => !usedKeys.has(item.group.key))
    .forEach((item) => {
      const label = bdEvolutionRoundedMassLabel(item.mass);
      if (!bdEvolutionValidMassLabel(label) || usedLabels.has(label)) return;
      const current = candidateByLabel.get(label);
      if (!current || Math.abs(item.mass - label) < Math.abs(current.mass - label)) {
        candidateByLabel.set(label, item);
      }
    });
  const candidates = Array.from(candidateByLabel.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([label, item]) => ({ ...item, labelCandidate: label }));
  const slots = Math.max(0, BDE_MASS_TRACK_LABEL_COUNT - selected.length);
  for (const item of evenlySpacedItems(candidates, slots)) {
    add(item, item.labelCandidate);
  }

  return selected.sort((a, b) => a.mass - b.mass);
}

function bdEvolutionRoundedMassLabel(mass) {
  if (!Number.isFinite(mass) || mass < 1) return null;
  return Math.round(mass);
}

function bdEvolutionValidMassLabel(label) {
  return Number.isFinite(label) && label > 0 && !BDE_MASS_LABEL_SUPPRESSED_MJUP.has(label);
}

function bdEvolutionMassLabelPoint(rows, xKey, yKey, xaxis) {
  const positioned = rows
    .map((row) => ({
      x: Number(row[xKey]),
      y: Number(row[yKey]),
      position: bdEvolutionAxisPosition(Number(row[xKey]), xaxis),
    }))
    .filter((row) => Number.isFinite(row.x) && Number.isFinite(row.y) && Number.isFinite(row.position))
    .sort((a, b) => a.position - b.position);
  if (!positioned.length) return null;
  const index = Math.min(positioned.length - 1, Math.max(0, Math.floor(positioned.length * 0.06)));
  return positioned[index];
}

function bdEvolutionPointInAxisRanges(x, y, xaxis, yaxis) {
  return bdEvolutionValueInAxisRange(x, xaxis) && bdEvolutionValueInAxisRange(y, yaxis);
}

function bdEvolutionValueInAxisRange(value, axis) {
  if (!Number.isFinite(value)) return false;
  if (!Array.isArray(axis?.range) || axis.range.length !== 2) return true;
  const scaled = bdEvolutionAxisScaledValue(value, axis);
  if (!Number.isFinite(scaled)) return false;
  const lo = Math.min(Number(axis.range[0]), Number(axis.range[1]));
  const hi = Math.max(Number(axis.range[0]), Number(axis.range[1]));
  return scaled >= lo && scaled <= hi;
}

function bdEvolutionAxisPosition(value, axis) {
  if (!Number.isFinite(value)) return Number.NaN;
  if (!Array.isArray(axis?.range) || axis.range.length !== 2) return 0;
  const scaled = bdEvolutionAxisScaledValue(value, axis);
  const left = Number(axis.range[0]);
  const right = Number(axis.range[1]);
  const span = right - left;
  if (!Number.isFinite(scaled) || !Number.isFinite(span) || Math.abs(span) < 1e-12) return Number.NaN;
  return (scaled - left) / span;
}

function bdEvolutionAxisScaledValue(value, axis) {
  if (axis?.type === "log") {
    return value > 0 ? Math.log10(value) : Number.NaN;
  }
  return value;
}

function bdEvolutionAnnotationCoordinate(value, axis) {
  const scaled = bdEvolutionAxisScaledValue(value, axis);
  return Number.isFinite(scaled) ? scaled : value;
}

function evenlySpacedItems(items, count) {
  if (!items.length || count <= 0) return [];
  if (items.length <= count) return items.slice();
  if (count === 1) return [items[Math.floor((items.length - 1) / 2)]];
  const out = [];
  const used = new Set();
  for (let index = 0; index < count; index += 1) {
    const itemIndex = Math.round(index * (items.length - 1) / (count - 1));
    if (!used.has(itemIndex)) {
      used.add(itemIndex);
      out.push(items[itemIndex]);
    }
  }
  return out;
}

function bdEvolutionMassKey(mass) {
  return mass === null ? "" : Number(mass).toFixed(6);
}

function bdEvolutionTerrainColor(value, values) {
  const finiteValues = (values || []).filter(Number.isFinite);
  if (!Number.isFinite(value) || !finiteValues.length) return terrainRgb(0.5);
  const minValue = Math.min(...finiteValues);
  const maxValue = Math.max(...finiteValues);
  const t = maxValue > minValue ? (value - minValue) / (maxValue - minValue) : 0.5;
  return terrainRgb(Math.max(0, Math.min(1, t)));
}

function terrainRgb(t) {
  for (let index = 1; index < bdeTerrainStops.length; index += 1) {
    const [rightT, rightColor] = bdeTerrainStops[index];
    const [leftT, leftColor] = bdeTerrainStops[index - 1];
    if (t <= rightT) {
      const local = rightT > leftT ? (t - leftT) / (rightT - leftT) : 0;
      const rgb = leftColor.map((left, channel) => Math.round(left + local * (rightColor[channel] - left)));
      return terrainRgbFromChannels(rgb);
    }
  }
  const last = bdeTerrainStops[bdeTerrainStops.length - 1][1];
  return terrainRgbFromChannels(last);
}

function terrainRgbFromChannels(rgb) {
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

function bdEvolutionIsothermColor(fraction) {
  const bounded = Math.max(0, Math.min(1, Number.isFinite(fraction) ? fraction : 0.5));
  const hue = 220 * (1 - bounded);
  return `hsl(${hue.toFixed(1)}, 88%, 40%)`;
}

function bdEvolutionTrackRowSort(a, b, xKey, yKey, groupingMode) {
  if (groupingMode === "iso_age") {
    const massA = finiteNumber(a.mass_mjup);
    const massB = finiteNumber(b.mass_mjup);
    if (massA !== null && massB !== null && massA !== massB) return massA - massB;
  }
  const xA = finiteNumber(a[xKey]);
  const xB = finiteNumber(b[xKey]);
  if (xA !== null && xB !== null && xA !== xB) return xA - xB;
  const yA = finiteNumber(a[yKey]);
  const yB = finiteNumber(b[yKey]);
  if (yA !== null && yB !== null && yA !== yB) return yA - yB;
  return 0;
}

function formatTrackAge(ageMyr) {
  if (!Number.isFinite(ageMyr)) return "";
  if (ageMyr >= 1000) return `${formatCell(ageMyr / 1000)} Gyr`;
  return `${formatCell(ageMyr)} Myr`;
}

function bdEvolutionMassHtml(value) {
  return `${htmlEscape(formatCell(value))} ${BDE_MJUP_UNIT_HTML}`;
}

function bdEvolutionTrackHoverMassHtml(value) {
  const mass = finiteNumber(value);
  return `${htmlEscape(mass === null ? "" : mass.toFixed(1))} ${BDE_MJUP_UNIT_HTML}`;
}

function bdEvolutionRadiusHtml(value) {
  return `${htmlEscape(formatCell(value))} ${BDE_RJUP_UNIT_HTML}`;
}

function bdEvolutionHtmlLines(parts) {
  return parts.filter((part) => part !== null && part !== undefined && String(part) !== "").map(htmlEscape).join("<br>")
    .replace(/ M_Jup/g, ` ${BDE_MJUP_UNIT_HTML}`)
    .replace(/ R_Jup/g, ` ${BDE_RJUP_UNIT_HTML}`);
}

function bdEvolutionLabelHtml(label) {
  const text = String(label ?? "");
  if (text.includes(BDE_MJUP_UNIT_HTML) || text.includes(BDE_RJUP_UNIT_HTML)) return text;
  return bdEvolutionHtmlLines([text]);
}

function bdEvolutionLayout(xKey, yKey, xLog, yLog, nPlotted) {
  const layout = {
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    margin: {
      l: 88,
      r: yKey === "teff_k" ? 218 : 156,
      t: xKey === "teff_k" ? 76 : 28,
      b: 82,
    },
    hovermode: "closest",
    dragmode: "lasso",
    showlegend: true,
    legend: {
      orientation: "v",
      groupclick: "togglegroup",
      x: 1.01,
      xanchor: "left",
      y: 1,
      yanchor: "top",
      bgcolor: "rgba(255,255,255,0.78)",
      bordercolor: "rgba(0,0,0,0)",
      font: { size: 10 },
    },
    xaxis: plotAxis(xKey, xLog),
    yaxis: plotAxis(yKey, yLog),
    annotations: [],
  };
  if (!nPlotted) {
    layout.annotations.push({
      text: "No objects have finite values for these axes.",
      x: 0.5,
      y: 0.5,
      xref: "paper",
      yref: "paper",
      showarrow: false,
      font: { size: 16, color: "#5f5864" },
    });
  }
  if (xKey === "teff_k") layout.xaxis2 = spectralTypeAxis("x", layout.xaxis);
  if (yKey === "teff_k") layout.yaxis2 = spectralTypeAxis("y", layout.yaxis);
  return layout;
}

function plotAxis(key, logScale) {
  const spec = axisSpec(key);
  const axis = {
    ...bdEvolutionBoxAxisStyle(),
    title: { text: spec.title || spec.label || key, font: { size: 22 }, standoff: 12 },
    zeroline: false,
    showgrid: true,
    gridcolor: "#e2e2e2",
    automargin: true,
    tickfont: { size: 15 },
    type: logScale ? "log" : "linear",
  };
  if (Array.isArray(spec.defaultRange) && spec.defaultRange.length === 2) {
    axis.range = logScale
      ? spec.defaultRange.map((value) => Math.log10(Math.max(Number(value), Number.MIN_VALUE)))
      : spec.defaultRange.slice();
  }
  return axis;
}

function bdEvolutionBoxAxisStyle() {
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

function spectralTypeAxis(orientation, mainAxis) {
  const ticks = (bdeState.sptAxis || bdeDefaultSptAxis)
    .map((row) => ({ label: row.label, teff: finiteNumber(row.teff_k) }))
    .filter((row) => row.label && row.teff !== null && row.teff > 0);
  const axis = {
    ...bdEvolutionBoxAxisStyle(),
    overlaying: orientation,
    side: orientation === "x" ? "top" : "right",
    title: { text: "Spectral Type", font: { size: 22 }, standoff: 10 },
    tickmode: "array",
    tickvals: ticks.map((row) => row.teff),
    ticktext: ticks.map((row) => row.label),
    showgrid: false,
    zeroline: false,
    tickfont: { size: 15 },
    type: mainAxis.type,
  };
  if (mainAxis.range) axis.range = mainAxis.range.slice();
  return axis;
}

function clearBdEvolutionPlotEvents() {
  const plot = bdeEl["bde-plot"];
  plot.removeAllListeners?.("plotly_selected");
  plot.removeAllListeners?.("plotly_deselect");
  plot.removeAllListeners?.("plotly_click");
  plot.removeAllListeners?.("plotly_legendclick");
  plot.removeAllListeners?.("plotly_legenddoubleclick");
}

function bindBdEvolutionPlotEvents() {
  const plot = bdeEl["bde-plot"];
  clearBdEvolutionPlotEvents();
  plot.on?.("plotly_click", (event) => {
    const oids = selectedOidsFromEventPoints(event?.points || []);
    if (!oids.length) return;
    applyBdEvolutionSelection(oids.slice(0, 1), event?.event || null, "click");
  });
  plot.on?.("plotly_selected", (event) => {
    const oids = selectedOidsFromEventPoints(event?.points || []);
    applyBdEvolutionSelection(oids, event?.event || null, "range");
  });
  plot.on?.("plotly_deselect", () => {
    clearBdEvolutionSelection();
  });
  plot.on?.("plotly_legendclick", (event) => handleBdEvolutionLegendClick(event));
  plot.on?.("plotly_legenddoubleclick", (event) => handleBdEvolutionLegendDoubleClick(event));
}

function handleBdEvolutionLegendClick(event) {
  const plot = bdeEl["bde-plot"];
  const traces = plot?.data || [];
  const curveNumber = Number(event?.curveNumber);
  const clickedTrace = traces[curveNumber];
  if (!clickedTrace || bdEvolutionTraceRole(clickedTrace) !== "companion-legend") {
    scheduleBdEvolutionLegendVisibilityCapture();
    if (bdeState.companionsHiddenByLegend) scheduleBdEvolutionCompanionLegendVisibilitySync();
    return true;
  }
  const companionsVisible = bdEvolutionCompanionTracesVisible(traces);
  const nextCompanionVisible = companionsVisible ? "legendonly" : true;
  bdeState.companionsHiddenByLegend = companionsVisible;
  const visible = traces.map((trace) => {
    if (bdEvolutionTraceRole(trace) === "companion-legend") {
      return nextCompanionVisible;
    }
    if (bdEvolutionTraceKind(trace) === "companion") {
      return nextCompanionVisible === "legendonly" ? "legendonly" : bdEvolutionStoredClassVisibilityForTrace(trace);
    }
    return trace.visible === undefined ? true : trace.visible;
  });
  Plotly.restyle(plot, { visible });
  return false;
}

function scheduleBdEvolutionCompanionLegendVisibilitySync() {
  window.setTimeout(() => {
    const plot = bdeEl["bde-plot"];
    const traces = plot?.data || [];
    if (!traces.length || !bdeState.companionsHiddenByLegend) return;
    const visible = traces.map((trace) => {
      if (bdEvolutionTraceRole(trace) === "companion-legend" || bdEvolutionTraceKind(trace) === "companion") {
        return "legendonly";
      }
      return trace.visible === undefined ? true : trace.visible;
    });
    Plotly.restyle(plot, { visible });
  }, 0);
}

function handleBdEvolutionLegendDoubleClick(event) {
  const plot = bdeEl["bde-plot"];
  const traces = plot?.data || [];
  const curveNumber = Number(event?.curveNumber);
  const clickedTrace = traces[curveNumber];
  if (!clickedTrace || bdEvolutionTraceRole(clickedTrace) !== "object") return false;
  const clickedCategory = clickedTrace?.meta?.bdeCategory;
  const companionsVisible = bdEvolutionCompanionTracesVisible(traces);

  const objectTraceIndices = [];
  const visible = traces.map((trace, index) => {
    const role = bdEvolutionTraceRole(trace);
    if (role === "model-track") return true;
    if (role === "object") {
      objectTraceIndices.push(index);
      if (bdEvolutionTraceKind(trace) === "companion" && !companionsVisible) return "legendonly";
      return trace?.meta?.bdeCategory === clickedCategory ? true : "legendonly";
    }
    return trace.visible === undefined ? true : trace.visible;
  });
  const clickedOnly = objectTraceIndices.length > 1
    && objectTraceIndices.every((index) => traces[index]?.meta?.bdeCategory === clickedCategory
      ? traces[index].visible !== "legendonly"
      : traces[index].visible === "legendonly");
  if (clickedOnly) {
    for (const index of objectTraceIndices) visible[index] = true;
  }
  Plotly.restyle(plot, { visible });
  rememberBdEvolutionLegendVisibility(traces, visible);
  return false;
}

function scheduleBdEvolutionLegendVisibilityCapture() {
  window.setTimeout(() => {
    rememberBdEvolutionLegendVisibility(bdeEl["bde-plot"]?.data || []);
  }, 40);
}

function bdEvolutionTraceRole(trace) {
  return trace?.meta?.bdeRole || (trace?.legendgroup === "tracks" ? "model-track" : (trace?.showlegend ? "object" : "other"));
}

function bdEvolutionTraceKind(trace) {
  return trace?.meta?.bdeTraceKind || "";
}

function bdEvolutionCompanionTracesVisible(traces) {
  return (traces || []).some((trace) => (
    bdEvolutionTraceKind(trace) === "companion" && trace.visible !== "legendonly"
  ));
}

function applyBdEvolutionStoredLegendVisibility(traces) {
  for (const trace of traces) {
    trace.visible = bdEvolutionStoredVisibilityForTrace(trace);
    if ((bdEvolutionTraceRole(trace) === "companion-legend" || bdEvolutionTraceKind(trace) === "companion")
      && bdeState.companionsHiddenByLegend) {
      trace.visible = "legendonly";
    }
  }
}

function bdEvolutionStoredVisibilityForTrace(trace) {
  const key = bdEvolutionTraceVisibilityKey(trace);
  if (key && bdeState.legendVisibility.has(key)) {
    return bdeState.legendVisibility.get(key);
  }
  return trace.visible === "legendonly" ? "legendonly" : true;
}

function bdEvolutionStoredClassVisibilityForTrace(trace) {
  const key = bdEvolutionTraceVisibilityKey(trace);
  if (key && bdeState.legendVisibility.has(key)) {
    return bdeState.legendVisibility.get(key);
  }
  return true;
}

function rememberBdEvolutionLegendVisibility(traces, visibleValues = null) {
  for (const [index, trace] of (traces || []).entries()) {
    const key = bdEvolutionTraceVisibilityCaptureKey(trace);
    if (!key) continue;
    const visible = visibleValues ? visibleValues[index] : trace.visible;
    bdeState.legendVisibility.set(key, visible === "legendonly" ? "legendonly" : true);
  }
}

function bdEvolutionTraceVisibilityKey(trace) {
  const role = bdEvolutionTraceRole(trace);
  if (role === "object" && trace?.meta?.bdeCategory) return `object:${trace.meta.bdeCategory}`;
  if (role === "target-oid") return "target-oid";
  return null;
}

function bdEvolutionTraceVisibilityCaptureKey(trace) {
  if (bdEvolutionTraceKind(trace) === "companion") return null;
  return bdEvolutionTraceVisibilityKey(trace);
}

function selectedOidsFromEventPoints(points) {
  const oids = [];
  for (const point of points || []) {
    const oid = coerceMocaOid(point.customdata);
    if (oid !== null) oids.push(oid);
  }
  return uniqueNumbers(oids);
}

function applyBdEvolutionSelection(oids, nativeEvent = null, mode = "range") {
  const clean = uniqueNumbers((oids || []).map(coerceMocaOid).filter((oid) => oid !== null));
  if (!clean.length) {
    if (mode === "range") clearBdEvolutionSelection();
    return;
  }
  const additive = Boolean(nativeEvent?.shiftKey || nativeEvent?.ctrlKey || nativeEvent?.metaKey);
  if (mode === "click" && additive) {
    const next = new Set(bdeState.selectedOids);
    for (const oid of clean) {
      if (next.has(oid)) next.delete(oid);
      else next.add(oid);
    }
    bdeState.selectedOids = next;
  } else if (additive) {
    bdeState.selectedOids = new Set([...bdeState.selectedOids, ...clean]);
  } else {
    bdeState.selectedOids = new Set(clean);
  }
  renderBdEvolutionPlot();
  renderBdEvolutionTable();
  updateBdEvolutionSummary();
}

function clearBdEvolutionSelection() {
  bdeState.selectedOids = new Set();
  renderBdEvolutionPlot();
  renderBdEvolutionTable();
  updateBdEvolutionSummary();
}

function selectedPointIndices(rows) {
  if (!bdeState.selectedOids.size) return null;
  const indices = [];
  rows.forEach((row, index) => {
    if (bdeState.selectedOids.has(row._oid)) indices.push(index);
  });
  return indices;
}

function pruneBdEvolutionSelection() {
  if (!bdeState.selectedOids.size) return;
  const loaded = new Set(bdEvolutionDisplayRows().map((row) => row._oid).filter((oid) => oid !== null));
  bdeState.selectedOids = new Set([...bdeState.selectedOids].filter((oid) => loaded.has(oid)));
}

function renderBdEvolutionTable() {
  const rows = selectedTableRows();
  const maxRows = 900;
  const shown = rows.slice(0, maxRows);
  bdeEl["bde-table-title"].textContent = bdeState.selectedOids.size
    ? `${bdeState.selectedOids.size.toLocaleString()} selected objects`
    : "Selected objects";
  bdeEl["bde-table-subtitle"].textContent = shown.length
    ? (rows.length > maxRows ? `Showing ${maxRows.toLocaleString()} of ${rows.length.toLocaleString()} selected rows.` : `${rows.length.toLocaleString()} selected rows.`)
    : "Click or lasso points in the plot.";
  if (!shown.length) {
    bdeEl["bde-table"].innerHTML = `<div class="selection-table">No selected objects.</div>`;
    return;
  }
  const columns = ["designation", "moca_oid", "spt", "age_myr", "age_source", "membership", "ya_prob", "observables", "banyan_distance_photometric", "teff_k", "mass_mjup", "logg", "radius_rjup"];
  const header = columns.map((column) => `<th>${htmlEscape(column)}</th>`).join("");
  const body = shown.map((row) => {
    const cells = columns.map((column) => {
      if (column === "designation" && row._reportUrl) {
        return `<td><a class="report-link" href="${htmlEscape(row._reportUrl)}" target="_blank" rel="noopener">${htmlEscape(row.designation || row._oid || "")}</a></td>`;
      }
      return `<td>${htmlEscape(formatBdEvolutionTableCell(row, column))}</td>`;
    }).join("");
    return `<tr class="is-selected">${cells}</tr>`;
  }).join("");
  bdeEl["bde-table"].innerHTML = `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
}

function formatBdEvolutionTableCell(row, column) {
  if (column === "moca_oid") return row._oid === null ? "" : String(row._oid);
  return formatCell(row[column]);
}

function selectedTableRows() {
  return bdEvolutionDisplayRows()
    .filter((row) => bdeState.selectedOids.has(row._oid))
    .sort((a, b) => Number(a.age_myr || 0) - Number(b.age_myr || 0) || Number(a.moca_oid || 0) - Number(b.moca_oid || 0));
}

function renderBdEvolutionHighlightList() {
  const target = bdeEl["bde-selected-objects"];
  if (!target) return;
  const selected = bdeState.selectedHighlightObjects;
  if (!selected.length) {
    target.innerHTML = `<div class="designation-result-note">No target objects selected</div>`;
    return;
  }
  target.innerHTML = selected.map((object) => {
    const oid = coerceMocaOid(object.moca_oid ?? object.value);
    const label = object.label || (object.designation ? `oid${oid}: ${object.designation}` : `oid${oid}`);
    return `
      <span class="designation-chip">
        <span title="${htmlEscape(label)}">${htmlEscape(label)}</span>
        <button type="button" data-remove-oid="${htmlEscape(oid)}" aria-label="Remove ${htmlEscape(label)}">x</button>
      </span>
    `;
  }).join("");
  target.querySelectorAll("button[data-remove-oid]").forEach((button) => {
    button.addEventListener("click", () => {
      const oid = coerceMocaOid(button.dataset.removeOid);
      bdeState.selectedHighlightObjects = bdeState.selectedHighlightObjects.filter((object) => coerceMocaOid(object.moca_oid ?? object.value) !== oid);
      renderBdEvolutionHighlightList();
      loadBdEvolutionData();
    });
  });
}

async function searchBdEvolutionObjects(query) {
  query = String(query || "").trim();
  const token = ++bdeState.objectSearchToken;
  if (!query) {
    bdeEl["bde-object-results"].hidden = true;
    return;
  }
  if (query.replace(/\s+/g, "").length < 2 && !/^\d+$/.test(query)) {
    bdeEl["bde-object-results"].innerHTML = `<div class="designation-result-note">Type at least 2 characters.</div>`;
    bdeEl["bde-object-results"].hidden = false;
    return;
  }
  const params = connectionParams();
  params.set("q", query);
  try {
    const payload = await fetchJsonUrl(bdeAppUrl(`api/bd-evolution/search?${params.toString()}`));
    if (token !== bdeState.objectSearchToken) return;
    const results = (payload.options || []).filter((result) => coerceMocaOid(result.moca_oid ?? result.value) !== null);
    if (!results.length) {
      bdeEl["bde-object-results"].innerHTML = `<div class="designation-result-note">No objects found</div>`;
      bdeEl["bde-object-results"].hidden = false;
      return;
    }
    bdeEl["bde-object-results"].innerHTML = results.map((result, index) => {
      const oid = coerceMocaOid(result.moca_oid ?? result.value);
      const selected = bdeState.selectedHighlightObjects.some((object) => coerceMocaOid(object.moca_oid ?? object.value) === oid);
      const label = result.label || (result.designation ? `oid${oid}: ${result.designation}` : `oid${oid}`);
      return `
        <button type="button" class="designation-result" data-index="${index}" ${selected ? "disabled" : ""}>
          ${selected ? "Selected: " : ""}${htmlEscape(label)}
        </button>
      `;
    }).join("");
    bdeEl["bde-object-results"].querySelectorAll("button[data-index]").forEach((button) => {
      button.addEventListener("click", () => {
        const result = results[Number(button.dataset.index)];
        selectBdEvolutionHighlightObject(result);
        bdeEl["bde-object-search"].value = "";
        bdeEl["bde-object-results"].hidden = true;
      });
    });
    bdeEl["bde-object-results"].hidden = false;
  } catch (error) {
    if (token !== bdeState.objectSearchToken) return;
    bdeEl["bde-object-results"].innerHTML = `<div class="designation-result-note">${htmlEscape(error.message || "Search failed")}</div>`;
    bdeEl["bde-object-results"].hidden = false;
  }
}

function selectBdEvolutionHighlightObject(result) {
  const oid = coerceMocaOid(result?.moca_oid ?? result?.value);
  if (oid === null) return;
  if (!bdeState.selectedHighlightObjects.some((object) => coerceMocaOid(object.moca_oid ?? object.value) === oid)) {
    bdeState.selectedHighlightObjects.push({
      value: oid,
      moca_oid: oid,
      designation: result.designation || "",
      label: result.label || (result.designation ? `oid${oid}: ${result.designation}` : `oid${oid}`),
    });
  }
  renderBdEvolutionHighlightList();
  loadBdEvolutionData();
}

function applyBdEvolutionClientFilters() {
  pruneBdEvolutionSelection();
  renderBdEvolutionPlot();
  renderBdEvolutionTable();
  setBdEvolutionExportDisabled(bdEvolutionDisplayRows().length === 0);
  updateBdEvolutionSummary();
  updateBdEvolutionLoadedStatus();
}

function updateBdEvolutionSummary() {
  const payload = bdeState.payload;
  if (!payload) {
    bdeEl["bde-summary"].textContent = "No data loaded";
    bdeEl["bde-subtitle"].textContent = "Selection: none";
    bdeEl["bde-clear-selection"].disabled = true;
    return;
  }
  const meta = payload.meta || {};
  const displayRows = bdEvolutionDisplayRows();
  const rowsAfterIgnoredGroups = bdEvolutionRowsAfterIgnoredGroups();
  const cache = payload.cache?.hit ? "cache hit" : "fresh query";
  const truncated = meta.truncated ? ", truncated" : "";
  const hiddenIgnoredCount = bdeState.rows.length - rowsAfterIgnoredGroups.length;
  const hiddenCompanionCount = rowsAfterIgnoredGroups.length - displayRows.length;
  const forcedTargetCount = displayRows.filter((row) => row._highlighted).length;
  const forcedTargets = forcedTargetCount
    ? `, ${forcedTargetCount.toLocaleString()} target OID${forcedTargetCount === 1 ? "" : "s"} forced`
    : "";
  const companions = bdeEl["bde-remove-companions"].checked ? `, ${hiddenCompanionCount.toLocaleString()} companions hidden` : "";
  const ignoredAids = bdEvolutionIgnoredMembershipAids();
  const ignoredGroups = ignoredAids.length ? `, ${hiddenIgnoredCount.toLocaleString()} ${ignoredAids.join(",")} rows hidden` : "";
  const yaProbMin = Number.isFinite(Number(meta.ya_prob_min)) ? Number(meta.ya_prob_min) : bdEvolutionYaProbMin();
  const yaProbCut = `YA >= ${formatCell(yaProbMin)}%`;
  const tracks = Number(meta.track_count || bdeState.tracks.length || 0).toLocaleString();
  const sptRange = meta.spt_range || bdeEl["bde-spt-range"].value || BDE_DEFAULT_SPT_RANGE;
  const objectAgeCount = displayRows.filter((row) => row.age_source === "object age").length;
  const membershipAgeCount = displayRows.filter((row) => row.age_source === "BANYAN Sigma membership age").length;
  bdeEl["bde-summary"].textContent = `${sptRange} sample: ${displayRows.length.toLocaleString()} objects, ${tracks} model rows, ${objectAgeCount.toLocaleString()} object ages, ${membershipAgeCount.toLocaleString()} membership ages, ${yaProbCut} (${cache}${truncated}${forcedTargets}${companions}${ignoredGroups})`;
  bdeEl["bde-subtitle"].textContent = bdeState.selectedOids.size
    ? `Selection: ${bdeState.selectedOids.size.toLocaleString()} object(s)`
    : "Selection: none";
  bdeEl["bde-clear-selection"].disabled = bdeState.selectedOids.size === 0;
}

function updateBdEvolutionLoadedStatus() {
  if (!bdeState.payload) return;
  setBdEvolutionStatus(`${bdeState.payload.source || "MOCAdb"}: ${bdEvolutionDisplayRows().length.toLocaleString()} objects`, "");
}

function renderBdEvolutionEmptyPlot(message) {
  const layout = bdEvolutionLayout("age_myr", "teff_k", true, false, 0);
  layout.annotations = [{
    text: htmlEscape(message || "No data loaded"),
    x: 0.5,
    y: 0.5,
    xref: "paper",
    yref: "paper",
    showarrow: false,
    font: { size: 16, color: "#5f5864" },
  }];
  clearBdEvolutionPlotEvents();
  Plotly.react(bdeEl["bde-plot"], [], layout, plotConfig("brown_dwarf_evolution_empty"));
}

function exportBdEvolution(format) {
  if (!window.MocaExport || !bdeState.rows.length) return;
  const selected = selectedTableRows();
  const displayRows = bdEvolutionDisplayRows();
  MocaExport.saveTable(format, {
    rows: selected.length ? selected : displayRows,
    columns: bdeExportColumns,
    numericColumns: bdeNumericExportColumns,
    filenameBase: selected.length ? "brown_dwarf_evolution_selected" : "brown_dwarf_evolution_rows",
    tableName: "brown_dwarf_evolution",
    resourceName: "Brown Dwarf Evolution Explorer rows",
    extName: "BD_EVOLUTION",
  });
}

function setBdEvolutionExportDisabled(disabled) {
  for (const id of ["bde-export-csv", "bde-export-tsv"]) {
    if (bdeEl[id]) bdeEl[id].disabled = disabled;
  }
}

async function clearBdEvolutionCache() {
  bdeEl["bde-clear-cache-bottom"].disabled = true;
  bdeEl["bde-clear-cache-status"].classList.remove("error");
  bdeEl["bde-clear-cache-status"].textContent = "Clearing cache";
  try {
    const payload = await fetchJsonUrl(bdeAppUrl("api/bd-evolution/cache/clear"), { method: "POST" });
    bdeEl["bde-clear-cache-status"].textContent = `Cleared ${payload.cleared?.bdEvolution ?? 0} entries.`;
  } catch (error) {
    bdeEl["bde-clear-cache-status"].classList.add("error");
    bdeEl["bde-clear-cache-status"].textContent = error.message;
  } finally {
    bdeEl["bde-clear-cache-bottom"].disabled = false;
  }
}

function axisList() {
  const axes = bdeState.axes || bdeFallbackAxes;
  const orderedAxes = Object.values(axes).sort((a, b) => {
    const order = ["age_myr", "teff_k", "mass_mjup", "logg", "radius_rjup"];
    const orderA = order.includes(a.key) ? order.indexOf(a.key) : Number.POSITIVE_INFINITY;
    const orderB = order.includes(b.key) ? order.indexOf(b.key) : Number.POSITIVE_INFINITY;
    return orderA - orderB;
  });
  if (!bdeState.payload) return orderedAxes;
  const availableKeys = bdEvolutionAvailableAxisKeys(orderedAxes);
  return orderedAxes.filter((axis) => availableKeys.has(axis.key));
}

function bdEvolutionAvailableAxisKeys(axes) {
  const rows = bdeState.rows?.length ? bdeState.rows : (bdeState.tracks || []);
  if (!rows.length) return new Set(axes.map((axis) => axis.key));
  const keys = new Set();
  for (const axis of axes) {
    if (rows.some((row) => bdEvolutionAxisValueAvailable(row, axis))) keys.add(axis.key);
  }
  return keys.size ? keys : new Set(axes.map((axis) => axis.key));
}

function bdEvolutionAxisValueAvailable(row, axis) {
  const value = finiteNumber(row?.[axis.key]);
  if (value === null) return false;
  if (axis.positive && value <= 0) return false;
  return true;
}

function axisSpec(key) {
  return bdeState.axes?.[key] || bdeFallbackAxes[key] || { key, label: key, title: key, positive: false };
}

function rowIsPlottable(row, xKey, yKey, xLog, yLog, useAgeJitter = false) {
  const x = plotValue(row, xKey, useAgeJitter);
  const y = plotValue(row, yKey, useAgeJitter);
  if (x === null || y === null) return false;
  if (xLog && x <= 0) return false;
  if (yLog && y <= 0) return false;
  return true;
}

function plotValue(row, key, useAgeJitter = false) {
  if (useAgeJitter && key === "age_myr") {
    return jitteredAgeMyr(finiteNumber(row.age_myr), finiteNumber(row._age_jitter_normal));
  }
  return finiteNumber(row[key]);
}

function jitteredAgeMyr(age, normalDeviate) {
  if (age === null || age <= 0) return age;
  const sigma = bdEvolutionAgeJitterDex();
  if (!sigma || normalDeviate === null) return age;
  const maxAbs = sigma * BDE_AGE_JITTER_CLIP_SIGMA;
  const jitterDex = Math.max(-maxAbs, Math.min(maxAbs, normalDeviate * sigma));
  return age * Math.pow(10, jitterDex);
}

function bdEvolutionAgeJitterDex() {
  const value = finiteNumber(bdeEl["bde-age-jitter"]?.value);
  if (value === null) return BDE_DEFAULT_AGE_JITTER_DEX;
  return Math.max(0, Math.min(BDE_MAX_AGE_JITTER_DEX, value));
}

function bdEvolutionYaProbMin() {
  const value = finiteNumber(bdeEl["bde-ya-prob-min"]?.value);
  if (value === null) return BDE_DEFAULT_YA_PROB_MIN;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function normalizeBdEvolutionAidListText(value) {
  const seen = new Set();
  const output = [];
  for (const item of String(value || "").split(/[,\s;]+/)) {
    const aid = item.trim().toUpperCase();
    if (!aid || seen.has(aid)) continue;
    seen.add(aid);
    output.push(aid);
  }
  return output.join(",");
}

function bdEvolutionIgnoredMembershipAidsText() {
  return normalizeBdEvolutionAidListText(bdeEl["bde-ignore-aids"]?.value);
}

function bdEvolutionIgnoredMembershipAids() {
  return bdEvolutionIgnoredMembershipAidsText().split(",").filter(Boolean);
}

function parseBdEvolutionOids(value) {
  return uniqueNumbers(String(value || "")
    .split(/[,\s;]+/)
    .map(coerceMocaOid)
    .filter((oid) => oid !== null));
}

function bdEvolutionHighlightedOids() {
  const oids = [];
  for (const object of bdeState.selectedHighlightObjects) {
    const oid = coerceMocaOid(object.moca_oid ?? object.value);
    if (oid !== null) oids.push(oid);
  }
  if (bdeEl["bde-highlight-oids"]) {
    oids.push(...parseBdEvolutionOids(bdeEl["bde-highlight-oids"].value));
  }
  return uniqueNumbers(oids);
}

function bdEvolutionHighlightedOidSet() {
  return new Set(bdEvolutionHighlightedOids());
}

function updateBdEvolutionYaProbReadout() {
  if (!bdeEl["bde-ya-prob-min-value"]) return;
  bdeEl["bde-ya-prob-min-value"].textContent = `${bdEvolutionYaProbMin()}%`;
}

function deterministicNormal(seed) {
  const u1 = Math.max(deterministicUnit(`${seed}:u1`), 1e-12);
  const u2 = deterministicUnit(`${seed}:u2`);
  return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
}

function deterministicUnit(seed) {
  let hash = 2166136261;
  const text = String(seed ?? "");
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return (hash + 0.5) / 4294967296;
}

function scheduleBdEvolutionReload() {
  clearTimeout(bdeState.sptReloadTimer);
  bdeState.sptReloadTimer = setTimeout(() => loadBdEvolutionData(), 550);
}

function sourceColor(row) {
  if (row.age_source === "BANYAN Sigma membership age") return "#c5533d";
  if (row.age_source === "object age") return "#225ea8";
  return "#4f4a53";
}

function hoverText(row) {
  const oidText = row._oid === null ? "" : String(row._oid);
  const name = row.designation || (oidText ? `oid${oidText}` : "MOCAdb object");
  const parts = [
    `${name}`,
    `MOCA OID: ${oidText}`,
    `Spectral type: ${row.spt || row.simple_spt || ""}`,
    `Age: ${formatCell(row.age_myr)} Myr`,
    `Age source: ${row.age_source || ""}`,
    `Membership: ${row.membership || ""}`,
    bdEvolutionIsCompanion(row) ? "Companion: yes" : "",
    `BANYAN observables: ${bdEvolutionObservableCategory(row).label}`,
  ];
  return bdEvolutionHtmlLines(parts);
}

function trackHoverText(row, label) {
  return [
    htmlEscape(row.grid_name || "Evolutionary track"),
    bdEvolutionLabelHtml(label),
    htmlEscape(`Age: ${formatCell(row.age_myr)} Myr`),
    `Mass: ${bdEvolutionTrackHoverMassHtml(row.mass_mjup)}`,
    htmlEscape(`Teff: ${formatCell(row.teff_k)} K`),
    htmlEscape(`log g: ${formatCell(row.logg)}`),
    `Radius: ${bdEvolutionRadiusHtml(row.radius_rjup)}`,
  ].join("<br>");
}

function plotConfig(name) {
  return {
    responsive: true,
    displaylogo: false,
    scrollZoom: true,
    modeBarButtonsToAdd: ["select2d", "lasso2d"],
    toImageButtonOptions: { format: "png", filename: name || "brown_dwarf_evolution", scale: 3 },
  };
}

async function fetchJsonUrl(url, options = {}) {
  const response = await fetch(url, options);
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function setBdEvolutionLoading(loading) {
  bdeEl["bde-plot-loader"].classList.toggle("is-visible", loading);
  bdeEl["bde-load"].disabled = loading;
}

function setBdEvolutionStatus(text, type) {
  bdeEl["bde-status"].textContent = text;
  bdeEl["bde-status"].classList.toggle("loading", type === "loading");
  bdeEl["bde-status"].classList.toggle("error", type === "error");
}

function truthyParam(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function coerceMocaOid(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const number = Number(text);
  if (!Number.isInteger(number) || number <= 0) return null;
  return number;
}

function uniqueNumbers(values) {
  const seen = new Set();
  const out = [];
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number) && !seen.has(number)) {
      seen.add(number);
      out.push(number);
    }
  }
  return out;
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function clampNumber(value, minValue, maxValue) {
  return Math.max(minValue, Math.min(maxValue, value));
}

function formatCell(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "";
    if (Math.abs(value) >= 1000) return value.toFixed(1);
    if (Math.abs(value) >= 100) return Number(value.toFixed(2)).toString();
    if (Math.abs(value) >= 10) return Number(value.toFixed(3)).toString();
    return Number(value.toFixed(5)).toString();
  }
  const number = Number(value);
  if (Number.isFinite(number) && String(value).trim() !== "") return formatCell(number);
  return String(value);
}

function htmlEscape(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
