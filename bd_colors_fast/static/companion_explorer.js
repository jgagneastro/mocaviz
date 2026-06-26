const cexDefaultAxes = [
  { key: "sep_au", label: "Projected Physical Separation (AU)", title: "Projected Physical Separation (AU)", defaultLog: true, positive: true, unc: "sep_au_unc", uncPos: "sep_au_unc_pos", uncNeg: "sep_au_unc_neg" },
  { key: "sep_mas", label: "Projected Angular Separation (mas)", title: "Projected Angular Separation (mas)", defaultLog: true, positive: true, unc: "sep_mas_unc", uncPos: "sep_mas_unc_pos", uncNeg: "sep_mas_unc_neg" },
  { key: "total_system_mass_msun", label: "Total System Mass (M_sun)", title: "Total System Mass (<i>M</i><sub>Sun</sub>)", positive: true, unc: "total_system_mass_msun_unc", uncPos: "total_system_mass_msun_unc_pos", uncNeg: "total_system_mass_msun_unc_neg" },
  { key: "mass_ratio_q", label: "Mass Ratio Q (M_child/M_parent)", title: "Mass Ratio Q (<i>M</i><sub>child</sub>/<i>M</i><sub>parent</sub>)", defaultLog: true, positive: true, unc: "mass_ratio_q_unc", uncPos: "mass_ratio_q_unc_pos", uncNeg: "mass_ratio_q_unc_neg" },
  { key: "binding_energy_erg", label: "Binding Energy (erg)", title: "Binding Energy (erg)", defaultLog: true, positive: true, unc: "binding_energy_erg_unc", uncPos: "binding_energy_erg_unc_pos", uncNeg: "binding_energy_erg_unc_neg" },
  { key: "pa_deg", label: "Position Angle (deg)", title: "Position Angle (deg)" },
  { key: "pmdiff_masyr", label: "Proper Motion Difference (mas/yr)", title: "Proper Motion Difference (mas yr<sup>-1</sup>)", positive: true, unc: "pmdiff_masyr_unc", exoplanetUnavailable: true },
  { key: "pmdiff_nsigma", label: "Proper Motion Difference (N_sigma)", title: "Proper Motion Difference (<i>N</i><sub>σ</sub>)", positive: true, exoplanetUnavailable: true },
  { key: "distance_diff_pc", label: "Distance Difference (pc)", title: "Distance Difference (pc)", unc: "distance_diff_pc_unc", exoplanetUnavailable: true },
  { key: "distance_diff_nsigma", label: "Distance Difference (N_sigma)", title: "Distance Difference (<i>N</i><sub>σ</sub>)", positive: true, exoplanetUnavailable: true },
  { key: "comover_xyz_separation_pc", label: "CoMover XYZ Separation (pc)", title: "CoMover XYZ Separation (pc)", defaultLog: true, positive: true, exoplanetUnavailable: true },
  { key: "comover_xyz_separation_nsigma", label: "CoMover XYZ Separation (N_sigma)", title: "CoMover XYZ Separation (<i>N</i><sub>σ</sub>)", defaultLog: true, positive: true, exoplanetUnavailable: true },
  { key: "comover_uvw_separation_kms", label: "CoMover UVW Separation (km/s)", title: "CoMover UVW Separation (km s<sup>-1</sup>)", positive: true, exoplanetUnavailable: true },
  { key: "comover_uvw_separation_nsigma", label: "CoMover UVW Separation (N_sigma)", title: "CoMover UVW Separation (<i>N</i><sub>σ</sub>)", positive: true, exoplanetUnavailable: true },
  { key: "comover_probability", label: "CoMover Probability (%)", title: "CoMover Probability (%)", positive: true, exoplanetUnavailable: true },
  { key: "system_distance_pc", label: "System Distance (pc)", title: "System Distance (pc)", positive: true, unc: "distance_pc_parent_unc", uncPos: "distance_pc_parent_unc_pos", uncNeg: "distance_pc_parent_unc_neg" },
  { key: "parent_sptn", label: "Parent Spectral Type", title: "Parent Spectral Type", spectralTypeAxis: true },
  { key: "child_sptn", label: "Companion Spectral Type", title: "Companion Spectral Type", spectralTypeAxis: true },
  { key: "mass_msun_parent", label: "Parent Mass (M_sun)", title: "Parent Mass (<i>M</i><sub>Sun</sub>)", positive: true, unc: "mass_msun_unc_parent", uncPos: "mass_msun_unc_pos_parent", uncNeg: "mass_msun_unc_neg_parent" },
  { key: "mass_msun_child", label: "Companion Mass (M_sun)", title: "Companion Mass (<i>M</i><sub>Sun</sub>)", positive: true, unc: "mass_msun_unc_child", uncPos: "mass_msun_unc_pos_child", uncNeg: "mass_msun_unc_neg_child" },
];

const cexQuantityFilters = [
  { id: "cex-filter-parent-age-myr", nullId: "cex-filter-parent-age-myr-null", param: "parent_age_myr_max", aliases: ["age_myr_max", "parent_age_max", "age_max"], nullParam: "ignore_null_parent_age_myr", nullAliases: ["ignore_null_age_myr", "ignore_missing_parent_age_myr", "ignore_missing_age_myr"], key: "parent_age_myr", age: true },
  { id: "cex-filter-pmdiff-masyr", nullId: "cex-filter-pmdiff-masyr-null", param: "pmdiff_masyr_max", aliases: ["pm_diff_masyr_max"], nullParam: "ignore_null_pmdiff_masyr", nullAliases: ["ignore_null_pm_diff_masyr", "ignore_missing_pmdiff_masyr", "ignore_missing_pm_diff_masyr"], key: "pmdiff_masyr" },
  { id: "cex-filter-distance-diff-pc", nullId: "cex-filter-distance-diff-pc-null", param: "distance_diff_pc_max", aliases: ["dist_diff_pc_max"], nullParam: "ignore_null_distance_diff_pc", nullAliases: ["ignore_null_dist_diff_pc", "ignore_missing_distance_diff_pc", "ignore_missing_dist_diff_pc"], key: "distance_diff_pc", absolute: true },
  { id: "cex-filter-comover-xyz-pc", nullId: "cex-filter-comover-xyz-pc-null", param: "comover_xyz_separation_pc_max", aliases: ["comover_xyz_sep_pc_max"], nullParam: "ignore_null_comover_xyz_separation_pc", nullAliases: ["ignore_null_comover_xyz_sep_pc", "ignore_missing_comover_xyz_separation_pc", "ignore_missing_comover_xyz_sep_pc"], key: "comover_xyz_separation_pc" },
  { id: "cex-filter-comover-uvw-kms", nullId: "cex-filter-comover-uvw-kms-null", param: "comover_uvw_separation_kms_max", aliases: ["comover_uvw_sep_kms_max"], nullParam: "ignore_null_comover_uvw_separation_kms", nullAliases: ["ignore_null_comover_uvw_sep_kms", "ignore_missing_comover_uvw_separation_kms", "ignore_missing_comover_uvw_sep_kms"], key: "comover_uvw_separation_kms" },
  { id: "cex-filter-comover-xyz-nsigma", nullId: "cex-filter-comover-xyz-nsigma-null", param: "comover_xyz_separation_nsigma_max", aliases: ["comover_xyz_sigma_max"], nullParam: "ignore_null_comover_xyz_separation_nsigma", nullAliases: ["ignore_null_comover_xyz_sigma", "ignore_missing_comover_xyz_separation_nsigma", "ignore_missing_comover_xyz_sigma"], key: "comover_xyz_separation_nsigma" },
  { id: "cex-filter-comover-uvw-nsigma", nullId: "cex-filter-comover-uvw-nsigma-null", param: "comover_uvw_separation_nsigma_max", aliases: ["comover_uvw_sigma_max"], nullParam: "ignore_null_comover_uvw_separation_nsigma", nullAliases: ["ignore_null_comover_uvw_sigma", "ignore_missing_comover_uvw_separation_nsigma", "ignore_missing_comover_uvw_sigma"], key: "comover_uvw_separation_nsigma" },
];

const cexAgeColorTicks = [1, 10, 50, 100, 300, 1000, 3000];
const cexAgeColorScale = [
  [0.00, "#3f5bff"],
  [0.20, "#1e9df0"],
  [0.38, "#31d8cf"],
  [0.55, "#76ed91"],
  [0.72, "#ffd16b"],
  [0.87, "#ff7043"],
  [1.00, "#e70012"],
];
const cexExoplanetMethodPalette = ["#0F766E", "#C026D3", "#EA580C", "#2563EB", "#65A30D", "#DC2626", "#7C3AED", "#0891B2", "#4B5563", "#CA8A04"];
const cexDefaultTransitColor = "#CA8A04";
const cexErrorBarAlpha = 0.35;
const cexErrorBarStyle = { thickness: 0.8, width: 0 };
const cexExoplanetMethodSymbols = new Map([
  ["Transit", "triangle-up"],
  ["Radial Velocity", "circle"],
  ["Imaging", "star"],
  ["Direct Imaging", "star"],
  ["Microlensing", "diamond"],
  ["Transit Timing Variations", "square"],
  ["Eclipse Timing Variations", "square-open"],
  ["Astrometry", "cross"],
  ["Orbital Brightness Modulation", "triangle-down"],
  ["Pulsar Timing", "x"],
  ["Pulsation Timing Variations", "x"],
  ["Disk Kinematics", "hexagon"],
]);
const cexTessCandidateAxisKeys = new Set(["sep_au", "sep_mas", "system_distance_pc", "parent_sptn", "mass_msun_parent"]);
const cexSpectralTypeTicks = [
  [-60, "O0"],
  [-50, "B0"],
  [-40, "A0"],
  [-30, "F0"],
  [-20, "G0"],
  [-10, "K0"],
  [0, "M0"],
  [5, "M5"],
  [10, "L0"],
  [15, "L5"],
  [20, "T0"],
  [25, "T5"],
  [30, "Y0"],
];

const cexExportColumns = [
  "row_kind", "moca_cid", "exoplanet_id", "nasa_id", "tess_candidate_id", "toi", "tid", "tfopwg_disp", "designation_parent", "designation_child", "moca_oid_parent", "moca_oid_child",
  "spectral_type_parent", "spectral_type_child", "sep_au", "sep_au_unc", "sep_mas", "sep_as",
  "pa_deg", "comover_probability", "mass_ratio_q", "mass_ratio_q_unc", "total_system_mass_msun",
  "total_system_mass_msun_unc", "mass_msun_parent", "mass_msun_unc_parent", "mass_msun_child",
  "mass_msun_unc_child", "binding_energy_erg", "binding_energy_erg_unc", "pmdiff_masyr",
  "pmdiff_masyr_unc", "pmdiff_nsigma", "distance_pc_parent", "distance_pc_parent_unc",
  "distance_pc_child", "distance_pc_child_unc", "distance_diff_pc", "distance_diff_pc_unc",
  "distance_diff_nsigma", "comover_xyz_separation_pc", "comover_xyz_separation_nsigma",
  "comover_uvw_separation_kms", "comover_uvw_separation_nsigma", "parent_age_myr",
  "parent_age_myr_unc", "parent_age_source", "parent_age_source_detail", "parent_age_membership",
  "parent_age_ya_prob", "distance_photometric_estimate", "discoverymethod", "pl_orbsmax",
  "pl_orbper", "pl_bmasse", "pl_bmassj", "mass_source_child", "sep_source",
];
const cexNumericExportColumns = new Set(cexExportColumns.filter((column) => (
  !column.startsWith("designation")
  && !column.startsWith("spectral")
  && !["row_kind", "exoplanet_id", "parent_age_source", "parent_age_source_detail", "parent_age_membership", "discoverymethod", "tfopwg_disp", "mass_source_child", "sep_source"].includes(column)
)));

const cexState = {
  axes: new Map(cexDefaultAxes.map((axis) => [axis.key, axis])),
  rows: [],
  exoplanets: [],
  tessCandidates: [],
  payload: null,
  highlightCids: new Set(),
  highlightExoplanetIds: new Set(),
  selectedCids: new Set(),
  selectedRowKeys: new Set(),
  designationIndex: null,
  designationIndexKey: "",
  designationIndexPromise: null,
  designationCacheBust: "",
  searchTimer: null,
  filterLoadTimer: null,
  loadToken: 0,
};
const cexEl = {};

document.addEventListener("DOMContentLoaded", initCompanionExplorer);

const cexAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function cexAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), cexAppBaseUrl).toString();
}

async function initCompanionExplorer() {
  collectCompanionElements();
  populateCompanionAxisSelects();
  readCompanionUrlState();
  bindCompanionControls();
  await loadCompanionData();
}

function collectCompanionElements() {
  [
    "cex-status", "cex-x-axis", "cex-y-axis", "cex-x-log", "cex-y-log",
    "cex-spt-range", "cex-prob-min", "cex-prob-min-value",
    ...cexQuantityFilters.map((filter) => filter.id),
    ...cexQuantityFilters.map((filter) => filter.nullId),
    "cex-companion-search", "cex-companion-results", "cex-selected-companions", "cex-highlight-cids",
    "cex-color-age", "cex-show-exoplanets", "cex-show-tess-candidates", "cex-error-bars", "cex-hover-text", "cex-ignore-null-comover", "cex-use-photometric-distances",
    "cex-max-rows", "cex-load", "cex-clear-cache", "cex-clear-cache-status",
    "cex-plot", "cex-plot-loader", "cex-summary", "cex-subtitle",
    "cex-clear-selection", "cex-export-csv", "cex-export-tsv",
    "cex-table-title", "cex-table-subtitle", "cex-table",
  ].forEach((id) => { cexEl[id] = document.getElementById(id); });
}

function bindCompanionControls() {
  cexEl["cex-load"].addEventListener("click", () => loadCompanionData());
  cexEl["cex-clear-cache"].addEventListener("click", () => clearCompanionCache());
  for (const id of ["cex-x-axis", "cex-y-axis"]) {
    cexEl[id].addEventListener("change", () => {
      applyCompanionAxisDefaults(false);
      updateExoplanetAvailability();
      updateCompanionUrl();
      loadCompanionData();
    });
  }
  for (const id of ["cex-x-log", "cex-y-log", "cex-show-exoplanets", "cex-show-tess-candidates", "cex-ignore-null-comover"]) {
    cexEl[id].addEventListener("change", () => {
      updateCompanionUrl();
      loadCompanionData();
    });
  }
  for (const id of ["cex-color-age", "cex-error-bars", "cex-hover-text"]) {
    cexEl[id].addEventListener("change", () => {
      updateCompanionUrl();
      renderCompanionExplorer();
    });
  }
  cexEl["cex-use-photometric-distances"].addEventListener("change", () => {
    updateCompanionUrl();
    loadCompanionData();
  });
  cexEl["cex-spt-range"].addEventListener("input", () => {
    updateCompanionUrl();
    scheduleCompanionDataLoad();
  });
  cexEl["cex-prob-min"].addEventListener("input", () => {
    updateCompanionProbabilityReadout();
    updateCompanionUrl();
    scheduleCompanionDataLoad();
  });
  for (const filter of cexQuantityFilters) {
    cexEl[filter.id].addEventListener("input", () => {
      updateCompanionUrl();
      scheduleCompanionDataLoad();
    });
    cexEl[filter.nullId].addEventListener("change", () => {
      updateCompanionUrl();
      scheduleCompanionDataLoad();
    });
  }
  cexEl["cex-max-rows"].addEventListener("change", () => loadCompanionData());
  cexEl["cex-highlight-cids"].addEventListener("change", () => {
    setCompanionHighlightCids(parseCidList(cexEl["cex-highlight-cids"].value));
  });
  cexEl["cex-highlight-cids"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") setCompanionHighlightCids(parseCidList(cexEl["cex-highlight-cids"].value));
  });
  cexEl["cex-companion-search"].addEventListener("input", () => {
    clearTimeout(cexState.searchTimer);
    const value = cexEl["cex-companion-search"].value.trim();
    cexState.searchTimer = setTimeout(() => searchCompanionTargets(value), 220);
  });
  cexEl["cex-companion-search"].addEventListener("focus", () => {
    const value = cexEl["cex-companion-search"].value.trim();
    if (value) searchCompanionTargets(value);
  });
  document.addEventListener("click", (event) => {
    if (!cexEl["cex-companion-results"].contains(event.target) && event.target !== cexEl["cex-companion-search"]) {
      cexEl["cex-companion-results"].hidden = true;
    }
  });
  cexEl["cex-clear-selection"].addEventListener("click", () => clearCompanionSelection());
  cexEl["cex-export-csv"].addEventListener("click", () => exportCompanionRows("csv"));
  cexEl["cex-export-tsv"].addEventListener("click", () => exportCompanionRows("tsv"));
  window.addEventListener("resize", debounce(() => {
    if (cexEl["cex-plot"] && cexState.payload) Plotly.Plots.resize(cexEl["cex-plot"]);
  }, 150));
}

function readCompanionUrlState() {
  const params = new URLSearchParams(window.location.search);
  const defaultPayload = { default: { x: "sep_au", y: "mass_ratio_q", xLog: true, yLog: true } };
  cexEl["cex-x-axis"].value = params.get("x") || params.get("xaxis") || defaultPayload.default.x;
  cexEl["cex-y-axis"].value = params.get("y") || params.get("yaxis") || defaultPayload.default.y;
  cexEl["cex-x-log"].checked = truthyParam(params.get("xlog") ?? params.get("x_log"), defaultPayload.default.xLog);
  cexEl["cex-y-log"].checked = truthyParam(params.get("ylog") ?? params.get("y_log"), defaultPayload.default.yLog);
  cexEl["cex-spt-range"].value = params.get("spt_range") || params.get("spt") || "";
  cexEl["cex-prob-min"].value = String(clampNumber(Number(params.get("comover_probability_min") || params.get("prob_min") || 50), 0, 100));
  for (const filter of cexQuantityFilters) {
    const value = firstCompanionParam(params, [filter.param, ...(filter.aliases || [])]);
    const limit = validFilterLimit(value);
    cexEl[filter.id].value = limit === null ? "" : String(limit);
    cexEl[filter.nullId].checked = truthyParam(firstCompanionParam(params, [filter.nullParam, ...(filter.nullAliases || [])]), false);
  }
  cexEl["cex-color-age"].checked = truthyParam(params.get("color_age") ?? params.get("color_by_age"), false);
  cexEl["cex-show-exoplanets"].checked = truthyParam(params.get("show_exoplanets") ?? params.get("exoplanets"), true);
  cexEl["cex-show-tess-candidates"].checked = truthyParam(params.get("show_tess_candidates") ?? params.get("tess_candidates"), false);
  cexEl["cex-error-bars"].checked = truthyParam(params.get("errors") ?? params.get("error_bars"), false);
  cexEl["cex-hover-text"].checked = truthyParam(params.get("hover_text") ?? params.get("hoverbox") ?? params.get("hover"), true);
  cexEl["cex-ignore-null-comover"].checked = truthyParam(
    params.get("ignore_null_comover") ?? params.get("ignore_missing_comover_probability") ?? params.get("ignore_missing_comover"),
    false,
  );
  cexEl["cex-use-photometric-distances"].checked = truthyParam(
    params.get("use_photometric_distances") ?? params.get("photometric_distances") ?? params.get("phot_dist"),
    false,
  );
  cexEl["cex-max-rows"].value = params.get("max_rows") || params.get("limit") || "80000";
  setCompanionHighlightCids(parseCidList(params.get("cids") || params.get("moca_cid") || params.get("cid") || ""), { quiet: true });
  setExoplanetHighlightIds(parseTokenList(params.get("highlight_exoplanets") || params.get("exoplanet_ids") || ""), { quiet: true });
  updateCompanionProbabilityReadout();
  updateExoplanetAvailability();
}

function populateCompanionAxisSelects() {
  const axes = [...cexState.axes.values()];
  for (const id of ["cex-x-axis", "cex-y-axis"]) {
    const current = cexEl[id]?.value || (id === "cex-x-axis" ? "sep_au" : "mass_ratio_q");
    cexEl[id].innerHTML = axes.map((axis) => `<option value="${escapeHtml(axis.key)}">${escapeHtml(axis.label || axis.key)}</option>`).join("");
    cexEl[id].value = cexState.axes.has(current) ? current : (id === "cex-x-axis" ? "sep_au" : "mass_ratio_q");
  }
}

async function loadCompanionData(options = {}) {
  clearTimeout(cexState.filterLoadTimer);
  const token = ++cexState.loadToken;
  setCompanionLoading(true);
  setCompanionStatus("Loading companions", "loading");
  const params = companionApiParams();
  applyCompanionDataParams(params);
  if (options.cacheBust) params.set("_cache_bust", String(Date.now()));
  const payload = await fetchCompanionJson(`api/companion-explorer/data?${params.toString()}`);
  if (token !== cexState.loadToken) return;
  if (!payload.ok) {
    cexState.rows = [];
    cexState.exoplanets = [];
    cexState.tessCandidates = [];
    cexState.payload = payload;
    setCompanionStatus(payload.error || "Could not load companions", "error");
    setCompanionLoading(false);
    renderCompanionExplorer();
    return;
  }
  cexState.payload = payload;
  cexState.rows = payload.rows || [];
  cexState.exoplanets = payload.exoplanets || [];
  cexState.tessCandidates = payload.tess_candidates || payload.tessCandidates || [];
  if (Array.isArray(payload.axes) && payload.axes.length) {
    cexState.axes = new Map(payload.axes.map((axis) => [axis.key, axis]));
    populateCompanionAxisSelects();
  }
  renderHighlightedCompanionList();
  applyCompanionAxisDefaults(true, payload.default || {});
  setCompanionStatus(`${cexState.rows.length.toLocaleString()} companions, ${cexState.exoplanets.length.toLocaleString()} exoplanets, ${cexState.tessCandidates.length.toLocaleString()} TESS candidates loaded`, "");
  setCompanionLoading(false);
  updateCompanionUrl();
  renderCompanionExplorer();
}

function applyCompanionAxisDefaults(initial = false, defaults = {}) {
  if (!initial) return;
  const params = new URLSearchParams(window.location.search);
  if (!params.has("x") && !params.has("xaxis")) cexEl["cex-x-axis"].value = defaults.x || "sep_au";
  if (!params.has("y") && !params.has("yaxis")) cexEl["cex-y-axis"].value = defaults.y || "mass_ratio_q";
  if (!params.has("xlog") && !params.has("x_log")) cexEl["cex-x-log"].checked = Boolean(defaults.xLog ?? axisSpec(cexEl["cex-x-axis"].value).defaultLog);
  if (!params.has("ylog") && !params.has("y_log")) cexEl["cex-y-log"].checked = Boolean(defaults.yLog ?? axisSpec(cexEl["cex-y-axis"].value).defaultLog);
}

function renderCompanionExplorer() {
  const xKey = cexEl["cex-x-axis"].value;
  const yKey = cexEl["cex-y-axis"].value;
  const xLog = cexEl["cex-x-log"].checked;
  const yLog = cexEl["cex-y-log"].checked;
  updateExoplanetAvailability();
  const rows = companionDisplayRows();
  const exoplanets = exoplanetDisplayRows();
  const tessCandidates = tessCandidateDisplayRows();
  const plottable = rows.filter((row) => companionRowIsPlottable(row, xKey, yKey, xLog, yLog));
  const plottableExoplanets = exoplanets.filter((row) => companionRowIsPlottable(row, xKey, yKey, xLog, yLog));
  const plottableTessCandidates = tessCandidates.filter((row) => companionRowIsPlottable(row, xKey, yKey, xLog, yLog));
  const highlighted = plottable.filter((row) => cexState.highlightCids.has(Number(row.moca_cid)));
  const base = plottable.filter((row) => !cexState.highlightCids.has(Number(row.moca_cid)));
  const highlightedExoplanets = plottableExoplanets.filter((row) => cexState.highlightExoplanetIds.has(exoplanetRowId(row)));
  const baseExoplanets = plottableExoplanets.filter((row) => !cexState.highlightExoplanetIds.has(exoplanetRowId(row)));
  const colorByAge = cexEl["cex-color-age"].checked;
  const companionAgeColorbar = colorByAge && base.some(rowHasUsableAge);
  const exoplanetAgeColorbar = colorByAge && !companionAgeColorbar && baseExoplanets.some(rowHasUsableAge);
  const hasAgeColorbar = companionAgeColorbar || exoplanetAgeColorbar;
  const allPlottableRows = [...plottable, ...plottableExoplanets, ...plottableTessCandidates];
  const exoplanetMethods = exoplanetDiscoveryMethods(baseExoplanets);
  const transitColor = exoplanetMethodColor("Transit", exoplanetMethods);
  const traces = [
    ...companionBaseTraces(base, xKey, yKey, { showAgeColorbar: companionAgeColorbar }),
    ...tessCandidateTraces(plottableTessCandidates, xKey, yKey, { transitColor }),
    ...exoplanetTraces(baseExoplanets, xKey, yKey, { showAgeColorbar: exoplanetAgeColorbar, methods: exoplanetMethods }),
    companionHighlightTrace(highlighted, xKey, yKey),
    exoplanetHighlightTrace(highlightedExoplanets, xKey, yKey),
  ].filter(Boolean);
  const layout = companionLayout(xKey, yKey, xLog, yLog, allPlottableRows, { hasAgeColorbar });
  Plotly.react(cexEl["cex-plot"], traces, layout, plotConfig(`companion_explorer_${xKey}_${yKey}`));
  bindCompanionPlotEvents();
  renderCompanionSummary(rows, plottable, exoplanets, plottableExoplanets, tessCandidates, plottableTessCandidates);
  renderCompanionTable();
  setCompanionExportDisabled(!(rows.length + exoplanets.length + tessCandidates.length));
}

function scheduleCompanionDataLoad(delay = 350) {
  clearTimeout(cexState.filterLoadTimer);
  cexState.filterLoadTimer = setTimeout(() => loadCompanionData(), delay);
}

function companionBaseTraces(rows, xKey, yKey, options = {}) {
  const colorByAge = cexEl["cex-color-age"].checked;
  if (!colorByAge) {
    return [companionScatterTrace(rows, xKey, yKey, {
      name: countTraceLabel("MOCAdb companions", rows),
      marker: { color: "#3B82F6", size: 8, opacity: 0.78, line: { color: "rgba(255,255,255,0.75)", width: 0.7 } },
      showlegend: true,
    })];
  }
  const withAge = rows.filter(rowHasUsableAge);
  const withoutAge = rows.filter((row) => !rowHasUsableAge(row));
  return [
    companionScatterTrace(withoutAge, xKey, yKey, {
      name: countTraceLabel("MOCAdb companions: age unknown", withoutAge),
      marker: unknownAgeMarker({ symbol: "circle", size: 8 }),
      showlegend: true,
    }),
    companionScatterTrace(withAge, xKey, yKey, {
      name: countTraceLabel("MOCAdb companions: parent ages", withAge),
      marker: ageColorMarker(withAge, { symbol: "circle", size: 8, showColorbar: options.showAgeColorbar }),
      showlegend: true,
    }),
  ];
}

function companionHighlightTrace(rows, xKey, yKey) {
  if (!rows.length) return null;
  return companionScatterTrace(rows, xKey, yKey, {
    name: countTraceLabel("Highlighted", rows),
    marker: { color: "#FFD43B", size: 15, opacity: 0.98, symbol: "star", line: { color: "#111111", width: 1.8 } },
    showlegend: true,
  });
}

function exoplanetHighlightTrace(rows, xKey, yKey) {
  if (!exoplanetsEnabled() || !rows.length) return null;
  return companionScatterTrace(rows, xKey, yKey, {
    name: countTraceLabel("Highlighted exoplanets", rows),
    marker: { color: "#FACC15", size: 15, opacity: 0.98, symbol: "star", line: { color: "#7C2D12", width: 1.8 } },
    showlegend: true,
  });
}

function exoplanetTraces(rows, xKey, yKey, options = {}) {
  if (!exoplanetsEnabled() || !rows.length) return [];
  const methods = options.methods || exoplanetDiscoveryMethods(rows);
  if (cexEl["cex-color-age"].checked) {
    let colorbarAvailable = Boolean(options.showAgeColorbar);
    const traces = [];
    for (const method of methods) {
      const methodRows = rows.filter((row) => exoplanetDiscoveryMethod(row) === method);
      const withAge = methodRows.filter(rowHasUsableAge);
      const withoutAge = methodRows.filter((row) => !rowHasUsableAge(row));
      traces.push(companionScatterTrace(withoutAge, xKey, yKey, {
        name: countTraceLabel(`Exoplanets: ${method} age unknown`, withoutAge),
        marker: unknownAgeMarker({ symbol: exoplanetMethodSymbol(method), size: 8, opacity: 0.34 }),
        showlegend: true,
      }));
      const showColorbar = colorbarAvailable && withAge.length > 0;
      traces.push(companionScatterTrace(withAge, xKey, yKey, {
        name: countTraceLabel(`Exoplanets: ${method} host ages`, withAge),
        marker: ageColorMarker(withAge, { symbol: exoplanetMethodSymbol(method), size: 8, showColorbar, opacity: 0.9 }),
        showlegend: true,
      }));
      if (showColorbar) colorbarAvailable = false;
    }
    return traces;
  }
  return methods.map((method, index) => {
    const methodRows = rows.filter((row) => exoplanetDiscoveryMethod(row) === method);
    return companionScatterTrace(methodRows, xKey, yKey, {
      name: countTraceLabel(`Exoplanets: ${method}`, methodRows),
      marker: {
        color: exoplanetMethodColor(method, methods, index),
        size: 7,
        opacity: 0.68,
        symbol: exoplanetMethodSymbol(method),
        line: { color: "rgba(255,255,255,0.85)", width: 0.5 },
      },
      showlegend: true,
    });
  });
}

function tessCandidateTraces(rows, xKey, yKey, options = {}) {
  if (!tessCandidatesEnabled() || !rows.length) return [];
  const transitColor = options.transitColor || exoplanetMethodColor("Transit");
  return [companionScatterTrace(rows, xKey, yKey, {
    name: countTraceLabel("TESS candidates", rows),
    marker: tessCandidateMarker(transitColor),
    showlegend: true,
  })];
}

function exoplanetDiscoveryMethods(rows) {
  return [...new Set(rows.map(exoplanetDiscoveryMethod))].sort((a, b) => a.localeCompare(b));
}

function exoplanetDiscoveryMethod(row) {
  return row.discoverymethod || "Unknown";
}

function exoplanetMethodSymbol(method) {
  return cexExoplanetMethodSymbols.get(method) || "diamond-open";
}

function exoplanetMethodColor(method, methods = [], explicitIndex = null) {
  if (Number.isInteger(explicitIndex)) return cexExoplanetMethodPalette[explicitIndex % cexExoplanetMethodPalette.length];
  let orderedMethods = Array.isArray(methods) ? methods.slice() : [];
  if (!orderedMethods.length && method === "Transit") return cexDefaultTransitColor;
  if (!orderedMethods.length) orderedMethods = [method];
  if (!orderedMethods.includes(method)) orderedMethods = [...orderedMethods, method].sort((a, b) => a.localeCompare(b));
  const index = orderedMethods.indexOf(method);
  return cexExoplanetMethodPalette[Math.max(index, 0) % cexExoplanetMethodPalette.length];
}

function tessCandidateMarker(transitColor) {
  return {
    color: transitColor,
    size: 9,
    opacity: 0.34,
    symbol: "triangle-up-open",
    line: { color: transitColor, width: 1.25 },
  };
}

function rowHasUsableAge(row) {
  return usableAgeMyr(row.parent_age_myr) !== null;
}

function countTraceLabel(label, rows) {
  return `${label} (${rows.length.toLocaleString()})`;
}

function unknownAgeMarker(options = {}) {
  return {
    color: "#A8ADB3",
    size: options.size || 8,
    opacity: options.opacity ?? 0.28,
    symbol: options.symbol || "circle",
    line: { color: "rgba(255,255,255,0.72)", width: 0.55 },
  };
}

function ageColorMarker(rows, options = {}) {
  return {
    color: rows.map(ageColorValue),
    colorscale: cexAgeColorScale,
    cmin: Math.log10(cexAgeColorTicks[0]),
    cmax: Math.log10(cexAgeColorTicks[cexAgeColorTicks.length - 1]),
    showscale: Boolean(options.showColorbar),
    ...(options.showColorbar ? { colorbar: ageColorbarSpec() } : {}),
    size: options.size || 8,
    opacity: options.opacity ?? 0.88,
    symbol: options.symbol || "circle",
    line: { color: "rgba(255,255,255,0.82)", width: 0.65 },
  };
}

function ageColorValue(row) {
  const age = usableAgeMyr(row.parent_age_myr);
  return Math.log10(clampNumber(age || cexAgeColorTicks[0], cexAgeColorTicks[0], cexAgeColorTicks[cexAgeColorTicks.length - 1]));
}

function ageColorbarSpec() {
  return {
    title: { text: "Age (Myr)", side: "right" },
    tickmode: "array",
    tickvals: cexAgeColorTicks.map((value) => Math.log10(value)),
    ticktext: cexAgeColorTicks.map((value) => value >= 1000 ? `${Math.round(value / 1000)}k` : String(value)),
    thickness: 18,
    len: 0.86,
    x: 1.025,
    y: 0.5,
    outlinewidth: 1.5,
    outlinecolor: "#111111",
    tickfont: { size: 13, color: "#111111" },
  };
}

function companionScatterTrace(rows, xKey, yKey, options) {
  if (!rows.length) return null;
  const hoverTextEnabled = cexEl["cex-hover-text"]?.checked !== false;
  const trace = {
    x: rows.map((row) => finiteNumber(row[xKey])),
    y: rows.map((row) => finiteNumber(row[yKey])),
    customdata: rows.map((row) => [rowSelectionKey(row), row.moca_cid ?? null]),
    type: "scattergl",
    mode: "markers",
    name: options.name,
    marker: options.marker,
    showlegend: options.showlegend,
  };
  if (hoverTextEnabled) {
    trace.text = rows.map((row) => companionHoverText(row, xKey, yKey));
    trace.hovertemplate = "%{text}<extra></extra>";
  } else {
    trace.hoverinfo = "skip";
  }
  if (cexEl["cex-error-bars"].checked) {
    const errorColor = companionErrorBarColor(options.marker);
    const xError = companionErrorSpec(rows, axisSpec(xKey), errorColor);
    const yError = companionErrorSpec(rows, axisSpec(yKey), errorColor);
    if (xError) trace.error_x = xError;
    if (yError) trace.error_y = yError;
  }
  return trace;
}

function companionErrorSpec(rows, spec, color) {
  const posKey = spec.uncPos;
  const negKey = spec.uncNeg;
  const symKey = spec.unc;
  const style = color ? { ...cexErrorBarStyle, color } : cexErrorBarStyle;
  const hasAsymmetric = posKey && negKey && rows.some((row) => finiteNumber(row[posKey]) !== null || finiteNumber(row[negKey]) !== null);
  if (hasAsymmetric) {
    const array = rows.map((row) => finiteNumber(row[posKey]) ?? finiteNumber(row[symKey]) ?? 0);
    const arrayminus = rows.map((row) => finiteNumber(row[negKey]) ?? finiteNumber(row[symKey]) ?? 0);
    return { type: "data", array, arrayminus, symmetric: false, visible: true, ...style };
  }
  if (symKey && rows.some((row) => finiteNumber(row[symKey]) !== null)) {
    return { type: "data", array: rows.map((row) => finiteNumber(row[symKey]) || 0), visible: true, ...style };
  }
  return null;
}

function companionErrorBarColor(marker = {}) {
  if (typeof marker.color === "string") return colorWithAlpha(marker.color, cexErrorBarAlpha);
  if (Array.isArray(marker.color) && marker.colorscale) {
    return colorScaleSample(marker.colorscale, marker.color, marker.cmin, marker.cmax, cexErrorBarAlpha);
  }
  if (typeof marker.line?.color === "string") return colorWithAlpha(marker.line.color, cexErrorBarAlpha);
  return null;
}

function colorScaleSample(colorscale, values, cmin, cmax, alpha) {
  const numericValues = values.map(finiteNumber).filter((value) => value !== null);
  if (!numericValues.length) return null;
  const sorted = numericValues.slice().sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const lo = finiteNumber(cmin) ?? Math.min(...numericValues);
  const hi = finiteNumber(cmax) ?? Math.max(...numericValues);
  const scaled = hi > lo ? clampNumber((median - lo) / (hi - lo), 0, 1) : 0.5;
  return interpolatedScaleColor(colorscale, scaled, alpha);
}

function interpolatedScaleColor(colorscale, value, alpha) {
  const stops = (colorscale || [])
    .map((stop) => [finiteNumber(stop?.[0]), colorToRgb(stop?.[1])])
    .filter(([position, color]) => position !== null && color)
    .sort((a, b) => a[0] - b[0]);
  if (!stops.length) return null;
  if (value <= stops[0][0]) return rgbaString(stops[0][1], alpha);
  for (let index = 1; index < stops.length; index += 1) {
    const [upperPosition, upperColor] = stops[index];
    const [lowerPosition, lowerColor] = stops[index - 1];
    if (value > upperPosition) continue;
    const span = upperPosition - lowerPosition;
    const fraction = span > 0 ? (value - lowerPosition) / span : 0;
    return rgbaString({
      r: Math.round(lowerColor.r + (upperColor.r - lowerColor.r) * fraction),
      g: Math.round(lowerColor.g + (upperColor.g - lowerColor.g) * fraction),
      b: Math.round(lowerColor.b + (upperColor.b - lowerColor.b) * fraction),
    }, alpha);
  }
  return rgbaString(stops[stops.length - 1][1], alpha);
}

function colorWithAlpha(color, alpha) {
  const rgb = colorToRgb(color);
  return rgb ? rgbaString(rgb, alpha) : color;
}

function colorToRgb(color) {
  const text = String(color || "").trim();
  const hexMatch = text.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hexMatch) {
    const hex = hexMatch[1].length === 3
      ? hexMatch[1].split("").map((char) => `${char}${char}`).join("")
      : hexMatch[1];
    return {
      r: parseInt(hex.slice(0, 2), 16),
      g: parseInt(hex.slice(2, 4), 16),
      b: parseInt(hex.slice(4, 6), 16),
    };
  }
  const rgbMatch = text.match(/^rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)/i);
  if (rgbMatch) {
    return {
      r: Math.round(Number(rgbMatch[1])),
      g: Math.round(Number(rgbMatch[2])),
      b: Math.round(Number(rgbMatch[3])),
    };
  }
  return null;
}

function rgbaString(color, alpha) {
  return `rgba(${color.r}, ${color.g}, ${color.b}, ${alpha})`;
}

function companionLayout(xKey, yKey, xLog, yLog, plottableRows = [], options = {}) {
  const pointCount = plottableRows.length;
  const layout = {
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    margin: { l: 92, r: options.hasAgeColorbar ? 118 : 36, t: 28, b: 84 },
    hovermode: "closest",
    dragmode: "lasso",
    showlegend: true,
    legend: companionLegendSpec(plottableRows, xKey, yKey, xLog, yLog),
    xaxis: companionAxis(xKey, xLog),
    yaxis: companionAxis(yKey, yLog),
    annotations: [],
  };
  if (axisSpec(xKey).spectralTypeAxis) {
    const ticks = spectralTicksForAxis(plottableRows, xKey);
    layout.xaxis.tickmode = "array";
    layout.xaxis.tickvals = ticks.map((tick) => tick.value);
    layout.xaxis.ticktext = ticks.map((tick) => tick.label);
    layout.xaxis.autorange = true;
  }
  if (axisSpec(yKey).spectralTypeAxis) {
    const ticks = spectralTicksForAxis(plottableRows, yKey);
    layout.yaxis.tickmode = "array";
    layout.yaxis.tickvals = ticks.map((tick) => tick.value);
    layout.yaxis.ticktext = ticks.map((tick) => tick.label);
    layout.yaxis.autorange = "reversed";
  }
  if (!pointCount) {
    layout.annotations.push({
      text: "No companions have finite values for these axes and filters.",
      x: 0.5,
      y: 0.5,
      xref: "paper",
      yref: "paper",
      showarrow: false,
      font: { size: 16, color: "#5f5864" },
    });
  }
  return layout;
}

function companionLegendSpec(rows, xKey, yKey, xLog, yLog) {
  const placement = companionLegendPlacement(rows, xKey, yKey, xLog, yLog);
  const anchors = {
    "top-left": { x: 0.015, xanchor: "left", y: 0.985, yanchor: "top" },
    "top-right": { x: 0.985, xanchor: "right", y: 0.985, yanchor: "top" },
    "bottom-left": { x: 0.015, xanchor: "left", y: 0.015, yanchor: "bottom" },
    "bottom-right": { x: 0.985, xanchor: "right", y: 0.015, yanchor: "bottom" },
  };
  return {
    orientation: "v",
    ...anchors[placement],
    bgcolor: "rgba(255,255,255,0.84)",
    bordercolor: "rgba(17,17,17,0.72)",
    borderwidth: 1,
    font: { size: 10, color: "#252329" },
  };
}

function companionLegendPlacement(rows, xKey, yKey, xLog, yLog) {
  const points = companionLegendPoints(rows, xKey, yKey, xLog, yLog);
  if (!points.length) return "top-right";
  const cornerCounts = new Map([
    ["top-right", 0],
    ["top-left", 0],
    ["bottom-right", 0],
    ["bottom-left", 0],
  ]);
  for (const point of points) {
    if (point.x >= 0.64 && point.y >= 0.64) cornerCounts.set("top-right", cornerCounts.get("top-right") + 1);
    if (point.x <= 0.36 && point.y >= 0.64) cornerCounts.set("top-left", cornerCounts.get("top-left") + 1);
    if (point.x >= 0.64 && point.y <= 0.36) cornerCounts.set("bottom-right", cornerCounts.get("bottom-right") + 1);
    if (point.x <= 0.36 && point.y <= 0.36) cornerCounts.set("bottom-left", cornerCounts.get("bottom-left") + 1);
  }
  return [...cornerCounts.entries()].sort((a, b) => a[1] - b[1])[0][0];
}

function companionLegendPoints(rows, xKey, yKey, xLog, yLog) {
  const rawPoints = (rows || [])
    .map((row) => ({
      x: companionLegendAxisValue(row, xKey, xLog),
      y: companionLegendAxisValue(row, yKey, yLog),
    }))
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (!rawPoints.length) return [];
  const xs = rawPoints.map((point) => point.x);
  const ys = rawPoints.map((point) => point.y);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const reverseY = axisSpec(yKey).spectralTypeAxis;
  return rawPoints.map((point) => ({
    x: normalizeLegendCoordinate(point.x, xMin, xMax),
    y: reverseY ? 1 - normalizeLegendCoordinate(point.y, yMin, yMax) : normalizeLegendCoordinate(point.y, yMin, yMax),
  }));
}

function companionLegendAxisValue(row, key, logScale) {
  const value = finiteNumber(row[key]);
  if (value === null) return null;
  if (logScale && !axisSpec(key).spectralTypeAxis) return value > 0 ? Math.log10(value) : null;
  return value;
}

function normalizeLegendCoordinate(value, min, max) {
  if (!Number.isFinite(value) || !Number.isFinite(min) || !Number.isFinite(max)) return null;
  if (max <= min) return 0.5;
  return (value - min) / (max - min);
}

function companionAxis(key, logScale) {
  const spec = axisSpec(key);
  const useLogScale = Boolean(logScale && !spec.spectralTypeAxis);
  const axis = {
    title: { text: spec.title || spec.label || key, font: { size: 21 }, standoff: 12 },
    type: useLogScale ? "log" : "linear",
    showline: true,
    mirror: true,
    linecolor: "#000000",
    linewidth: 3,
    ticks: "outside",
    ticklen: 8,
    tickwidth: 2,
    tickcolor: "#000000",
    showgrid: true,
    gridcolor: "#e2e2e2",
    zeroline: false,
    automargin: true,
    tickfont: { size: 14 },
  };
  if (useLogScale) {
    axis.exponentformat = "power";
    axis.showexponent = "all";
  }
  return axis;
}

function companionDisplayRows() {
  const sptWindow = parseSpectralRange(cexEl["cex-spt-range"].value);
  const probMin = Number(cexEl["cex-prob-min"].value) || 0;
  const ignoreNullComover = Boolean(cexEl["cex-ignore-null-comover"].checked);
  const quantityFilters = activeCompanionQuantityFilters();
  return (cexState.rows || []).filter((row) => {
    const cid = Number(row.moca_cid);
    if (cexState.highlightCids.has(cid)) return true;
    const prob = finiteNumber(row.comover_probability);
    if (prob !== null && prob < probMin) return false;
    if (prob === null && ignoreNullComover) return false;
    return rowMatchesSpectralRange(row, sptWindow)
      && rowMatchesQuantityFilters(row, quantityFilters)
      && rowMatchesAxisValueRanges(row);
  });
}

function exoplanetDisplayRows() {
  if (!exoplanetsEnabled()) return [];
  const sptWindow = parseSpectralRange(cexEl["cex-spt-range"].value);
  const quantityFilters = activeCompanionQuantityFilters();
  return (cexState.exoplanets || []).filter((row) => {
    if (cexState.highlightExoplanetIds.has(exoplanetRowId(row))) return true;
    return rowMatchesSpectralRange(row, sptWindow)
      && rowMatchesQuantityFilters(row, quantityFilters)
      && rowMatchesAxisValueRanges(row);
  });
}

function tessCandidateDisplayRows() {
  if (!tessCandidatesEnabled()) return [];
  const sptWindow = parseSpectralRange(cexEl["cex-spt-range"].value);
  const quantityFilters = activeCompanionQuantityFilters();
  return (cexState.tessCandidates || []).filter((row) => (
    rowMatchesSpectralRange(row, sptWindow)
    && rowMatchesQuantityFilters(row, quantityFilters)
    && rowMatchesAxisValueRanges(row)
  ));
}

function activeCompanionQuantityFilters() {
  return cexQuantityFilters
    .map((filter) => ({
      ...filter,
      limit: validFilterLimit(cexEl[filter.id]?.value),
      ignoreNull: Boolean(cexEl[filter.nullId]?.checked),
    }))
    .filter((filter) => filter.limit !== null || filter.ignoreNull);
}

function quantityFilterValue(row, filter) {
  const rawValue = filter.age ? usableAgeMyr(row[filter.key]) : finiteNumber(row[filter.key]);
  if (rawValue === null) return null;
  return filter.absolute ? Math.abs(rawValue) : rawValue;
}

function rowMatchesQuantityFilters(row, filters) {
  for (const filter of filters) {
    const value = quantityFilterValue(row, filter);
    if (value === null) {
      if (filter.ignoreNull) return false;
      continue;
    }
    if (filter.limit !== null && value > filter.limit) return false;
  }
  return true;
}

function rowMatchesAxisValueRanges(row) {
  for (const key of [cexEl["cex-x-axis"].value, cexEl["cex-y-axis"].value]) {
    if (key !== "mass_ratio_q") continue;
    const value = finiteNumber(row.mass_ratio_q);
    if (value === null || !validMassRatio(value)) return false;
  }
  return true;
}

function exoplanetsEnabled() {
  return Boolean(cexEl["cex-show-exoplanets"]?.checked && !cexEl["cex-show-exoplanets"]?.disabled);
}

function tessCandidatesEnabled() {
  return Boolean(cexEl["cex-show-tess-candidates"]?.checked && !cexEl["cex-show-tess-candidates"]?.disabled);
}

function exoplanetsUnavailableForAxes() {
  return Boolean(axisSpec(cexEl["cex-x-axis"].value).exoplanetUnavailable || axisSpec(cexEl["cex-y-axis"].value).exoplanetUnavailable);
}

function tessCandidatesUnavailableForAxes() {
  return !cexTessCandidateAxisKeys.has(cexEl["cex-x-axis"].value) || !cexTessCandidateAxisKeys.has(cexEl["cex-y-axis"].value);
}

function updateExoplanetAvailability() {
  if (!cexEl["cex-show-exoplanets"]) return;
  const unavailable = exoplanetsUnavailableForAxes();
  cexEl["cex-show-exoplanets"].disabled = unavailable;
  const label = cexEl["cex-show-exoplanets"].closest("label");
  if (label) {
    label.classList.toggle("is-disabled", unavailable);
    label.title = unavailable ? "NASA exoplanets do not have CoMover, distance-difference, or proper-motion-difference quantities." : "";
  }
  if (!cexEl["cex-show-tess-candidates"]) return;
  const tessUnavailable = tessCandidatesUnavailableForAxes();
  cexEl["cex-show-tess-candidates"].disabled = tessUnavailable;
  const tessLabel = cexEl["cex-show-tess-candidates"].closest("label");
  if (tessLabel) {
    tessLabel.classList.toggle("is-disabled", tessUnavailable);
    tessLabel.title = tessUnavailable ? "TESS candidates only have host mass, host spectral type, host distance, and period-derived separation quantities." : "";
  }
}

function companionRowIsPlottable(row, xKey, yKey, xLog, yLog) {
  const x = finiteNumber(row[xKey]);
  const y = finiteNumber(row[yKey]);
  if (x === null || y === null) return false;
  if (xKey === "mass_ratio_q" && !validMassRatio(x)) return false;
  if (yKey === "mass_ratio_q" && !validMassRatio(y)) return false;
  if (xLog && !axisSpec(xKey).spectralTypeAxis && x <= 0) return false;
  if (yLog && !axisSpec(yKey).spectralTypeAxis && y <= 0) return false;
  return true;
}

function validMassRatio(value) {
  return value >= 0 && value <= 1;
}

function renderCompanionSummary(rows, plottable, exoplanets = [], plottableExoplanets = [], tessCandidates = [], plottableTessCandidates = []) {
  const total = cexState.rows.length;
  const exoplanetTotal = cexState.exoplanets.length;
  const tessTotal = cexState.tessCandidates.length;
  const filtered = rows.length;
  const exoplanetFiltered = exoplanets.length;
  const tessFiltered = tessCandidates.length;
  const highlighted = rows.filter((row) => cexState.highlightCids.has(Number(row.moca_cid))).length;
  const highlightedExoplanets = exoplanets.filter((row) => cexState.highlightExoplanetIds.has(exoplanetRowId(row))).length;
  const highlightedTotal = highlighted + highlightedExoplanets;
  const cache = cexState.payload?.cache?.hit ? "cached" : cexState.payload?.source || "";
  const plottedText = `${plottable.length.toLocaleString()} companions`;
  const exoplanetText = exoplanetsEnabled()
    ? `, ${plottableExoplanets.length.toLocaleString()} exoplanets`
    : "";
  const tessText = tessCandidatesEnabled()
    ? `, ${plottableTessCandidates.length.toLocaleString()} TESS candidates`
    : "";
  cexEl["cex-summary"].textContent = `${plottedText}${exoplanetText}${tessText} plotted; ${filtered.toLocaleString()} of ${total.toLocaleString()} companions filtered${exoplanetsEnabled() ? `; ${exoplanetFiltered.toLocaleString()} of ${exoplanetTotal.toLocaleString()} exoplanets filtered` : ""}${tessCandidatesEnabled() ? `; ${tessFiltered.toLocaleString()} of ${tessTotal.toLocaleString()} TESS candidates filtered` : ""}${highlightedTotal ? `; ${highlightedTotal} highlighted` : ""}`;
  cexEl["cex-subtitle"].textContent = `${axisSpec(cexEl["cex-x-axis"].value).label} vs ${axisSpec(cexEl["cex-y-axis"].value).label}${cache ? ` (${cache})` : ""}`;
}

function bindCompanionPlotEvents() {
  const plot = cexEl["cex-plot"];
  plot.removeAllListeners?.("plotly_click");
  plot.removeAllListeners?.("plotly_selected");
  plot.removeAllListeners?.("plotly_deselect");
  plot.on?.("plotly_click", (event) => {
    const keys = selectionKeysFromEventPoints(event?.points || []);
    if (keys.length) applyCompanionSelection(keys.slice(0, 1), event?.event || null);
  });
  plot.on?.("plotly_selected", (event) => {
    applyCompanionSelection(selectionKeysFromEventPoints(event?.points || []), event?.event || null);
  });
  plot.on?.("plotly_deselect", () => clearCompanionSelection());
}

function applyCompanionSelection(selectionValues, event) {
  if (!event?.shiftKey && !event?.metaKey && !event?.ctrlKey) {
    cexState.selectedCids.clear();
    cexState.selectedRowKeys.clear();
  }
  selectionValues.forEach((value) => {
    const key = normalizeSelectionKey(value);
    if (!key) return;
    cexState.selectedRowKeys.add(key);
    const cid = companionCidFromSelectionKey(key);
    if (cid !== null) cexState.selectedCids.add(cid);
  });
  renderCompanionTable();
}

function clearCompanionSelection() {
  cexState.selectedCids.clear();
  cexState.selectedRowKeys.clear();
  renderCompanionTable();
}

function renderCompanionTable() {
  const rows = selectedTableRows();
  const hasSelection = cexState.selectedRowKeys.size || cexState.selectedCids.size;
  cexEl["cex-clear-selection"].disabled = !hasSelection;
  cexEl["cex-table-title"].textContent = hasSelection ? "Selected objects" : "Highlighted objects";
  cexEl["cex-table-subtitle"].textContent = rows.length ? `${rows.length.toLocaleString()} object${rows.length === 1 ? "" : "s"}` : "Click or lasso points in the plot.";
  if (!rows.length) {
    cexEl["cex-table"].innerHTML = `<div class="designation-result-note">No objects selected.</div>`;
    return;
  }
  const columns = companionSelectionTableColumns();
  cexEl["cex-table"].innerHTML = `<table><thead><tr>${columns.map((column) => `<th>${escapeHtml(tableHeader(column))}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => (
    `<tr>${columns.map((column) => `<td>${companionTableCellHtml(row, column)}</td>`).join("")}</tr>`
  )).join("")}</tbody></table>`;
}

function companionSelectionTableColumns() {
  const baseColumns = ["moca_cid", "designation_parent", "parent_report_url", "designation_child", "child_report_url", "parent_age_myr"];
  const axisColumns = [...cexState.axes.keys()].filter((key) => !baseColumns.includes(key));
  return [...baseColumns, ...axisColumns];
}

function companionTableCellHtml(row, column) {
  if (column === "parent_report_url") return reportButtonHtml(row.parent_report_url, "Parent Report");
  if (column === "child_report_url") return reportButtonHtml(row.child_report_url, "Child Report");
  if (column === "moca_cid") return escapeHtml(formatIntegerCell(row[column]));
  if (column === "parent_sptn") return escapeHtml(row.spectral_type_parent || formatCell(row[column]));
  if (column === "child_sptn") return escapeHtml(row.spectral_type_child || formatCell(row[column]));
  if (column === "parent_age_myr") return escapeHtml(formatAgeMyrCell(row[column]));
  return escapeHtml(formatCell(row[column]));
}

function reportButtonHtml(url, label) {
  if (!url) return `<span class="button-link is-disabled">${escapeHtml(label)}</span>`;
  return `<a class="button-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
}

function formatIntegerCell(value) {
  const number = finiteNumber(value);
  if (number === null) return value === null || value === undefined ? "" : String(value);
  return Number.isInteger(number) ? String(number) : String(Math.trunc(number));
}

function normalizeSearchText(value) {
  return String(value || "").trim().toLowerCase();
}

function selectedTableRows() {
  const selectedRows = combinedLoadedRows();
  const selected = selectedRows.filter((row) => {
    const key = rowSelectionKey(row);
    return (key && cexState.selectedRowKeys.has(key))
      || (row.row_kind === "companion" && cexState.selectedCids.has(Number(row.moca_cid)));
  });
  if (selected.length) return selected;
  return combinedLoadedRows().filter((row) => (
    (row.row_kind === "companion" && cexState.highlightCids.has(Number(row.moca_cid)))
    || (row.row_kind === "exoplanet" && cexState.highlightExoplanetIds.has(exoplanetRowId(row)))
  ));
}

async function searchCompanionTargets(query) {
  if (!query || query.length < 2) {
    cexEl["cex-companion-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    cexEl["cex-companion-results"].hidden = false;
    return;
  }
  cexEl["cex-companion-results"].innerHTML = `<div class="designation-result-note">Searching designations...</div>`;
  cexEl["cex-companion-results"].hidden = false;
  try {
    const index = await ensureCompanionDesignationIndex();
    if (normalizeSearchText(cexEl["cex-companion-search"].value) !== normalizeSearchText(query)) return;
    const indexResults = companionDesignationIndexResults(query, index);
    if (indexResults.length) {
      renderCompanionSearchResults(indexResults);
      return;
    }
  } catch (error) {
    console.warn("Companion designation index unavailable", error);
  }
  const localResults = localCompanionSearchResults(query);
  if (localResults.length) {
    renderCompanionSearchResults(localResults);
    return;
  }
  const params = companionApiParams();
  params.set("include_exoplanets", exoplanetsEnabled() ? "1" : "0");
  params.set("q", query);
  const payload = await fetchCompanionJson(`api/companion-explorer/search?${params.toString()}`);
  renderCompanionSearchResults(payload.options || []);
}

async function ensureCompanionDesignationIndex() {
  const key = exoplanetsEnabled() ? "exoplanets" : "companions";
  if (cexState.designationIndex && cexState.designationIndexKey === key) return cexState.designationIndex;
  if (cexState.designationIndexPromise && cexState.designationIndexKey === key) return cexState.designationIndexPromise;
  cexState.designationIndexKey = key;
  const params = companionApiParams();
  params.set("include_exoplanets", exoplanetsEnabled() ? "1" : "0");
  if (cexState.designationCacheBust) params.set("_cache_bust", cexState.designationCacheBust);
  cexState.designationIndexPromise = fetchCompanionJson(`api/companion-explorer/designations?${params.toString()}`)
    .then((payload) => {
      if (!payload.ok) throw new Error(payload.error || "Could not load designation index");
      cexState.designationIndex = payload.options || [];
      return cexState.designationIndex;
    })
    .finally(() => {
      cexState.designationIndexPromise = null;
    });
  return cexState.designationIndexPromise;
}

function companionDesignationIndexResults(query, rows) {
  const companionRows = (rows || []).filter((row) => (row.result_kind || "companion") !== "exoplanet");
  const exoplanetRows = (rows || []).filter((row) => (row.result_kind || "companion") === "exoplanet");
  return localCompanionSearchResults(query, companionRows, exoplanetRows);
}

function localCompanionSearchResults(query, companionRows = cexState.rows || [], exoplanetRows = exoplanetsEnabled() ? cexState.exoplanets || [] : []) {
  const needle = normalizeSearchText(query);
  if (!needle) return [];
  const companionResults = [];
  for (const row of companionRows || []) {
    const cid = row.moca_cid ?? row.value;
    const cidText = String(cid ?? "");
    const textFields = [
      row.designation_parent,
      row.designation_child,
      row.parent_designations,
      row.child_designations,
      cidText,
    ].map(normalizeSearchText);
    if (!textFields.some((value) => value.includes(needle))) continue;
    companionResults.push({
      ...row,
      result_kind: "companion",
      value: cid,
      label: companionSearchResultLabel(row, needle),
      main_label: companionSearchResultMainLabel(row),
      detail_label: companionSearchResultDetailLabel(row, needle),
    });
    if (companionResults.length >= 80) break;
  }
  const exoplanetResults = [];
  if (exoplanetsEnabled()) {
    for (const row of exoplanetRows || []) {
      const id = exoplanetRowId(row);
      const textFields = [
        row.designation_parent,
        row.designation_child,
        row.parent_designations,
        row.child_designations,
        row.nasa_id,
        id,
      ].map(normalizeSearchText);
      if (!textFields.some((value) => value.includes(needle))) continue;
      exoplanetResults.push({
        ...row,
        result_kind: "exoplanet",
        value: id,
        label: exoplanetSearchResultLabel(row, needle),
        main_label: exoplanetSearchResultMainLabel(row),
        detail_label: exoplanetSearchResultDetailLabel(row, needle),
      });
      if (exoplanetResults.length >= 80) break;
    }
  }
  if (!exoplanetResults.length) return companionResults.slice(0, 80);
  if (!companionResults.length) return exoplanetResults.slice(0, 80);
  const companionLimit = Math.min(companionResults.length, 50);
  const results = [
    ...companionResults.slice(0, companionLimit),
    ...exoplanetResults.slice(0, 80 - companionLimit),
  ];
  if (results.length < 80) results.push(...companionResults.slice(companionLimit, 80 - results.length + companionLimit));
  return results.slice(0, 80);
}

function companionSearchResultLabel(row, needle) {
  const base = companionSearchResultMainLabel(row);
  const aliases = matchingAliasLabels(row, needle);
  return aliases.length ? `${base} [${aliases.slice(0, 3).join("; ")}]` : base;
}

function companionSearchResultMainLabel(row) {
  return `cid${formatIntegerCell(row.moca_cid)}: ${row.designation_parent || "parent"} -> ${row.designation_child || "companion"}`;
}

function companionSearchResultDetailLabel(row, needle) {
  const aliases = matchingAliasLabels(row, needle);
  return aliases.length ? aliases.slice(0, 3).join("; ") : "";
}

function matchingAliasLabels(row, needle) {
  const labels = [];
  for (const [field, prefix] of [["parent_designations", "parent"], ["child_designations", "child"]]) {
    for (const alias of splitDesignationAliases(row[field])) {
      if (normalizeSearchText(alias).includes(needle) && alias !== row.designation_parent && alias !== row.designation_child) {
        labels.push(`${prefix}: ${alias}`);
      }
      if (labels.length >= 4) return labels;
    }
  }
  return labels;
}

function exoplanetSearchResultLabel(row, needle) {
  const base = exoplanetSearchResultMainLabel(row);
  const aliases = matchingExoplanetAliasLabels(row, needle);
  return aliases.length ? `${base} [${aliases.slice(0, 3).join("; ")}]` : base;
}

function exoplanetSearchResultMainLabel(row) {
  return `exoplanet: ${row.designation_parent || "host"} -> ${row.designation_child || "planet"}`;
}

function exoplanetSearchResultDetailLabel(row, needle) {
  const aliases = matchingExoplanetAliasLabels(row, needle);
  return aliases.length ? aliases.slice(0, 3).join("; ") : "";
}

function matchingExoplanetAliasLabels(row, needle) {
  const labels = [];
  for (const [field, prefix] of [["parent_designations", "host"], ["child_designations", "planet"], ["nasa_id", "NASA"], ["exoplanet_id", "id"]]) {
    for (const alias of splitDesignationAliases(row[field])) {
      if (normalizeSearchText(alias).includes(needle) && alias !== row.designation_parent && alias !== row.designation_child) {
        labels.push(`${prefix}: ${alias}`);
      }
      if (labels.length >= 4) return labels;
    }
  }
  return labels;
}

function splitDesignationAliases(value) {
  return String(value || "")
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderCompanionSearchResults(results) {
  if (!results.length) {
    cexEl["cex-companion-results"].innerHTML = `<div class="designation-result-note">No matching objects found</div>`;
    cexEl["cex-companion-results"].hidden = false;
    return;
  }
  cexEl["cex-companion-results"].innerHTML = results.map((result, index) => (
    searchResultButtonHtml(result, index)
  )).join("");
  cexEl["cex-companion-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const result = results[Number(button.dataset.index)];
      if ((result.result_kind || "companion") === "exoplanet") {
        addExoplanetHighlightId(result.value);
      } else {
        addCompanionHighlightCid(result.value);
      }
      cexEl["cex-companion-search"].value = result.label || companionResultFallbackLabel(result);
      cexEl["cex-companion-results"].hidden = true;
    });
  });
  cexEl["cex-companion-results"].hidden = false;
}

function searchResultButtonHtml(result, index) {
  const main = result.main_label || result.label || companionResultFallbackLabel(result);
  const detail = result.detail_label || "";
  return [
    `<button class="designation-result" type="button" data-index="${index}">`,
    `<span class="designation-result-main">${escapeHtml(main)}</span>`,
    detail ? `<span class="designation-result-meta">${escapeHtml(detail)}</span>` : "",
    "</button>",
  ].join("");
}

function companionResultFallbackLabel(result) {
  return (result.result_kind || "companion") === "exoplanet" ? `exoplanet: ${result.value}` : `cid${result.value}`;
}

function addCompanionHighlightCid(cid) {
  const value = Number(cid);
  if (!Number.isFinite(value)) return;
  cexState.highlightCids.add(value);
  syncHighlightCidInput();
  renderHighlightedCompanionList();
  updateCompanionUrl();
  if (!(cexState.rows || []).some((row) => Number(row.moca_cid) === value)) loadCompanionData();
  else renderCompanionExplorer();
}

function setCompanionHighlightCids(cids, options = {}) {
  cexState.highlightCids = new Set((cids || []).map(Number).filter(Number.isFinite));
  syncHighlightCidInput();
  renderHighlightedCompanionList();
  if (!options.quiet) {
    updateCompanionUrl();
    loadCompanionData();
  }
}

function addExoplanetHighlightId(id) {
  const value = String(id || "").trim();
  if (!value) return;
  cexState.highlightExoplanetIds.add(value);
  renderHighlightedCompanionList();
  updateCompanionUrl();
  if (exoplanetsEnabled() && !(cexState.exoplanets || []).some((row) => exoplanetRowId(row) === value)) loadCompanionData();
  else renderCompanionExplorer();
}

function setExoplanetHighlightIds(ids, options = {}) {
  cexState.highlightExoplanetIds = new Set((ids || []).map((id) => String(id || "").trim()).filter(Boolean));
  renderHighlightedCompanionList();
  if (!options.quiet) {
    updateCompanionUrl();
    loadCompanionData();
  }
}

function syncHighlightCidInput() {
  if (cexEl["cex-highlight-cids"]) {
    cexEl["cex-highlight-cids"].value = [...cexState.highlightCids].sort((a, b) => a - b).join(", ");
  }
}

function renderHighlightedCompanionList() {
  const cids = [...cexState.highlightCids].sort((a, b) => a - b);
  const exoplanetIds = [...cexState.highlightExoplanetIds].sort((a, b) => a.localeCompare(b));
  const entries = [
    ...cids.map((cid) => {
      const row = cexState.rows.find((candidate) => Number(candidate.moca_cid) === cid);
      const label = row ? `cid${cid}: ${row.designation_parent || "parent"} -> ${row.designation_child || "companion"}` : `cid${cid}`;
      return { kind: "companion", value: String(cid), label, title: "Remove highlighted companion" };
    }),
    ...exoplanetIds.map((id) => {
      const row = cexState.exoplanets.find((candidate) => exoplanetRowId(candidate) === id);
      const label = row ? `exoplanet: ${row.designation_parent || "host"} -> ${row.designation_child || "planet"}` : `exoplanet: ${id}`;
      return { kind: "exoplanet", value: id, label, title: "Remove highlighted exoplanet" };
    }),
  ];
  if (!entries.length) {
    cexEl["cex-selected-companions"].textContent = "No objects highlighted";
    return;
  }
  cexEl["cex-selected-companions"].innerHTML = entries.map((entry) => (
    `<button type="button" data-kind="${entry.kind}" data-value="${escapeHtml(entry.value)}" title="${escapeHtml(entry.title)}">${escapeHtml(entry.label)} x</button>`
  )).join("");
  cexEl["cex-selected-companions"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.kind === "exoplanet") cexState.highlightExoplanetIds.delete(button.dataset.value || "");
      else cexState.highlightCids.delete(Number(button.dataset.value));
      syncHighlightCidInput();
      renderHighlightedCompanionList();
      updateCompanionUrl();
      renderCompanionExplorer();
    });
  });
}

function updateCompanionUrl() {
  const params = new URLSearchParams(window.location.search);
  params.set("x", cexEl["cex-x-axis"].value);
  params.set("y", cexEl["cex-y-axis"].value);
  params.set("xlog", cexEl["cex-x-log"].checked ? "1" : "0");
  params.set("ylog", cexEl["cex-y-log"].checked ? "1" : "0");
  if (cexEl["cex-spt-range"].value.trim()) params.set("spt_range", cexEl["cex-spt-range"].value.trim());
  else params.delete("spt_range");
  params.set("comover_probability_min", cexEl["cex-prob-min"].value || "0");
  for (const filter of cexQuantityFilters) {
    const value = validFilterLimit(cexEl[filter.id]?.value);
    if (value === null) params.delete(filter.param);
    else params.set(filter.param, String(value));
    for (const alias of filter.aliases || []) params.delete(alias);
    if (cexEl[filter.nullId]?.checked) params.set(filter.nullParam, "1");
    else params.delete(filter.nullParam);
    for (const alias of filter.nullAliases || []) params.delete(alias);
  }
  if (cexEl["cex-ignore-null-comover"].checked) params.set("ignore_null_comover", "1");
  else {
    params.delete("ignore_null_comover");
    params.delete("ignore_missing_comover_probability");
    params.delete("ignore_missing_comover");
  }
  if (cexEl["cex-color-age"].checked) params.set("color_age", "1");
  else params.delete("color_age");
  if (cexEl["cex-show-exoplanets"].checked) params.delete("show_exoplanets");
  else params.set("show_exoplanets", "0");
  if (cexEl["cex-show-tess-candidates"].checked) params.set("show_tess_candidates", "1");
  else {
    params.delete("show_tess_candidates");
    params.delete("tess_candidates");
  }
  if (cexEl["cex-use-photometric-distances"].checked) params.set("use_photometric_distances", "1");
  else params.delete("use_photometric_distances");
  if (cexEl["cex-error-bars"].checked) params.set("errors", "1");
  else params.delete("errors");
  if (cexEl["cex-hover-text"].checked) {
    params.delete("hover_text");
    params.delete("hoverbox");
    params.delete("hover");
  } else {
    params.set("hover_text", "0");
    params.delete("hoverbox");
    params.delete("hover");
  }
  if (cexState.highlightCids.size) params.set("cids", [...cexState.highlightCids].sort((a, b) => a - b).join(","));
  else params.delete("cids");
  if (cexState.highlightExoplanetIds.size) params.set("highlight_exoplanets", [...cexState.highlightExoplanetIds].sort((a, b) => a.localeCompare(b)).join(","));
  else {
    params.delete("highlight_exoplanets");
    params.delete("exoplanet_ids");
  }
  params.set("max_rows", cexEl["cex-max-rows"].value || "80000");
  window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}

function exportCompanionRows(format) {
  if (!window.MocaExport) return;
  const selected = selectedTableRows();
  const rows = selected.length ? selected : combinedDisplayRows();
  MocaExport.saveTable(format, {
    rows,
    columns: cexExportColumns,
    numericColumns: cexNumericExportColumns,
    filenameBase: selected.length ? "companion_explorer_selected" : "companion_explorer_rows",
    tableName: "companion_explorer",
    resourceName: "Companion Explorer rows",
    extName: "COMPANIONS",
  });
}

function combinedDisplayRows() {
  return [...companionDisplayRows(), ...exoplanetDisplayRows(), ...tessCandidateDisplayRows()];
}

function combinedLoadedRows() {
  return [...(cexState.rows || []), ...(cexState.exoplanets || []), ...(cexState.tessCandidates || [])];
}

function setCompanionExportDisabled(disabled) {
  for (const id of ["cex-export-csv", "cex-export-tsv"]) cexEl[id].disabled = disabled;
}

async function clearCompanionCache() {
  cexEl["cex-clear-cache"].disabled = true;
  cexEl["cex-clear-cache-status"].classList.remove("error");
  cexEl["cex-clear-cache-status"].textContent = "Clearing cache";
  try {
    const payload = await postCompanionJson("api/companion-explorer/cache/clear");
    cexState.designationIndex = null;
    cexState.designationIndexKey = "";
    cexState.designationIndexPromise = null;
    cexState.designationCacheBust = String(Date.now());
    const cleared = payload.cleared || {};
    const count = Object.values(cleared).reduce((sum, value) => sum + Number(value || 0), 0);
    cexEl["cex-clear-cache-status"].textContent = `Cleared ${count} cached entr${count === 1 ? "y" : "ies"}. Reloading.`;
    await loadCompanionData({ cacheBust: true });
    cexEl["cex-clear-cache-status"].textContent = `Cleared ${count} cached entr${count === 1 ? "y" : "ies"}.`;
  } catch (error) {
    cexEl["cex-clear-cache-status"].classList.add("error");
    cexEl["cex-clear-cache-status"].textContent = error.message || "Could not clear cache";
  } finally {
    cexEl["cex-clear-cache"].disabled = false;
  }
}

function setCompanionLoading(isLoading) {
  cexEl["cex-plot-loader"].classList.toggle("is-visible", Boolean(isLoading));
}

function setCompanionStatus(text, kind) {
  cexEl["cex-status"].textContent = text || "";
  cexEl["cex-status"].className = `status ${kind || ""}`.trim();
}

function updateCompanionProbabilityReadout() {
  cexEl["cex-prob-min-value"].textContent = `${Number(cexEl["cex-prob-min"].value || 0).toFixed(0)}%`;
}

function axisSpec(key) {
  return cexState.axes.get(key) || cexDefaultAxes.find((axis) => axis.key === key) || { key, label: key, title: key };
}

function companionHoverText(row, xKey, yKey) {
  const coordinateLines = companionHoverCoordinateLines(row, xKey, yKey);
  if (row.row_kind === "exoplanet") {
    return [
      `<b>${escapeHtml(row.designation_child || "NASA exoplanet")}</b>`,
      ...coordinateLines,
      `Host: ${escapeHtml(row.designation_parent || "")}`,
      `Discovery: ${escapeHtml(row.discoverymethod || "Unknown")}`,
      `Host SpT: ${escapeHtml(row.spectral_type_parent || "")}`,
      `Mass: ${formatCell(row.mass_msun_child)} M_sun`,
      `Separation: ${formatCell(row.sep_au)} AU`,
      `Age: ${formatAgeMyrText(row.parent_age_myr)}`,
    ].join("<br>");
  }
  if (row.row_kind === "tess_candidate") {
    return [
      `<b>${escapeHtml(row.designation_child || "TESS candidate")}</b>`,
      ...coordinateLines,
      `Host: ${escapeHtml(row.designation_parent || "")}`,
      `Disposition: ${escapeHtml(row.tfopwg_disp || "")}`,
      `Host SpT: ${escapeHtml(row.spectral_type_parent || "")}`,
      `Host mass: ${formatCell(row.mass_msun_parent)} M_sun`,
      `Period: ${formatCell(row.pl_orbper)} days`,
      `Separation: ${formatCell(row.sep_au)} AU`,
      `Age: ${formatAgeMyrText(row.parent_age_myr)}`,
    ].join("<br>");
  }
  return [
    `<b>cid${escapeHtml(row.moca_cid)}</b>`,
    ...coordinateLines,
    `${escapeHtml(row.designation_parent || "parent")} -> ${escapeHtml(row.designation_child || "companion")}`,
    `Parent SpT: ${escapeHtml(row.spectral_type_parent || "")}`,
    `Companion SpT: ${escapeHtml(row.spectral_type_child || "")}`,
    `CoMover: ${formatCell(row.comover_probability)}%`,
    `Age: ${formatAgeMyrText(row.parent_age_myr)}`,
  ].join("<br>");
}

function companionHoverCoordinateLines(row, xKey, yKey) {
  return [
    `${escapeHtml(axisSpec(xKey).label || xKey)}: ${escapeHtml(formatAxisHoverValue(row, xKey))}`,
    `${escapeHtml(axisSpec(yKey).label || yKey)}: ${escapeHtml(formatAxisHoverValue(row, yKey))}`,
  ];
}

function formatAxisHoverValue(row, key) {
  if (key === "parent_sptn") return row.spectral_type_parent || formatCell(row[key]);
  if (key === "child_sptn") return row.spectral_type_child || formatCell(row[key]);
  if (key === "parent_age_myr") return formatAgeMyrCell(row[key]);
  return formatCell(row[key]);
}

function tableHeader(column) {
  const baseHeaders = {
    moca_cid: "cid",
    designation_parent: "Parent",
    parent_report_url: "Parent Report",
    designation_child: "Companion",
    child_report_url: "Child Report",
    spectral_type_parent: "Parent SpT",
    spectral_type_child: "Companion SpT",
    parent_age_myr: "Age (Myr)",
  };
  return baseHeaders[column] || axisSpec(column).label || column;
}

function rowSelectionKey(row) {
  if (!row) return "";
  if (row.row_kind === "exoplanet") {
    const id = exoplanetRowId(row);
    return id ? `exoplanet:${id}` : "";
  }
  if (row.row_kind === "tess_candidate") {
    const id = row.tess_candidate_id ?? row.exoplanet_id ?? row.toi ?? row.tid ?? row.designation_child;
    return id === null || id === undefined || id === "" ? "" : `tess:${id}`;
  }
  const cid = finiteNumber(row.moca_cid);
  return cid === null ? "" : `companion:${Math.trunc(cid)}`;
}

function normalizeSelectionKey(value) {
  if (Array.isArray(value)) return normalizeSelectionKey(value[0]);
  if (value === null || value === undefined || value === "") return "";
  const text = String(value).trim();
  if (!text) return "";
  if (/^(companion|exoplanet|tess):/i.test(text)) return text;
  const cid = finiteNumber(text);
  return cid === null ? "" : `companion:${Math.trunc(cid)}`;
}

function companionCidFromSelectionKey(key) {
  const match = String(key || "").match(/^companion:(\d+)$/i);
  if (!match) return null;
  const cid = Number(match[1]);
  return Number.isFinite(cid) ? cid : null;
}

function selectionKeyFromEventPoint(point) {
  let key = normalizeSelectionKey(point?.customdata);
  if (key) return key;
  const pointIndex = point?.pointIndex ?? point?.pointNumber ?? point?.pointNumbers?.[0];
  const customdata = point?.data?.customdata || point?.fullData?.customdata;
  if (pointIndex !== undefined && Array.isArray(customdata)) {
    key = normalizeSelectionKey(customdata[pointIndex]);
    if (key) return key;
  }
  return "";
}

function selectionKeysFromEventPoints(points) {
  return [...new Set((points || [])
    .map(selectionKeyFromEventPoint)
    .filter(Boolean))];
}

function cidsFromEventPoints(points) {
  return selectionKeysFromEventPoints(points)
    .map(companionCidFromSelectionKey)
    .filter((cid) => cid !== null);
}

function companionApiParams() {
  const source = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "port", "user", "username", "pwd", "password", "dbase", "db", "database", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  return params;
}

function applyCompanionDataParams(params) {
  params.set("max_rows", cexEl["cex-max-rows"].value || "80000");
  params.set("x", cexEl["cex-x-axis"].value);
  params.set("y", cexEl["cex-y-axis"].value);
  params.set("xlog", cexEl["cex-x-log"].checked ? "1" : "0");
  params.set("ylog", cexEl["cex-y-log"].checked ? "1" : "0");
  params.set("comover_probability_min", cexEl["cex-prob-min"].value || "0");
  params.set("include_exoplanets", exoplanetsEnabled() ? "1" : "0");
  params.set("include_tess_candidates", tessCandidatesEnabled() ? "1" : "0");
  if (cexEl["cex-spt-range"].value.trim()) params.set("spt_range", cexEl["cex-spt-range"].value.trim());
  if (cexEl["cex-ignore-null-comover"].checked) params.set("ignore_null_comover", "1");
  if (cexEl["cex-use-photometric-distances"].checked) params.set("use_photometric_distances", "1");
  for (const filter of cexQuantityFilters) {
    const value = validFilterLimit(cexEl[filter.id]?.value);
    if (value !== null) params.set(filter.param, String(value));
    if (cexEl[filter.nullId]?.checked) params.set(filter.nullParam, "1");
  }
  for (const cid of cexState.highlightCids) params.append("cids", String(cid));
  if (cexState.highlightExoplanetIds.size) {
    params.set("highlight_exoplanets", [...cexState.highlightExoplanetIds].sort((a, b) => a.localeCompare(b)).join(","));
  }
  return params;
}

async function fetchCompanionJson(path) {
  const response = await fetch(cexAppUrl(path), { headers: { Accept: "application/json" } });
  return response.json();
}

async function postCompanionJson(path, body = {}) {
  const response = await fetch(cexAppUrl(path), {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function firstCompanionParam(params, keys) {
  for (const key of keys) {
    if (params.has(key)) return params.get(key);
  }
  return null;
}

function parseCidList(raw) {
  return String(raw || "")
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => /^[0-9]+$/.test(item))
    .map((item) => Number(item.trim()))
    .filter(Number.isFinite);
}

function parseTokenList(raw) {
  return String(raw || "")
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function exoplanetRowId(row) {
  return String(row?.exoplanet_id || row?.nasa_id || row?.designation_child || "").trim();
}

function parseSpectralRange(raw) {
  const text = String(raw || "").trim();
  if (!text || /^all$/i.test(text)) return null;
  if (text.endsWith("+")) {
    const lo = parseSpectralTypeNumber(text.slice(0, -1));
    return lo === null ? null : { min: lo, max: Infinity };
  }
  const parts = text.split(/\s*[-–]\s*/).filter(Boolean);
  if (parts.length >= 2) {
    const a = parseSpectralTypeNumber(parts[0]);
    const b = parseSpectralTypeNumber(parts[1]);
    if (a === null || b === null) return null;
    return { min: Math.min(a, b), max: Math.max(a, b) };
  }
  const value = parseSpectralTypeNumber(text);
  return value === null ? null : { min: value - 0.5, max: value + 0.5 };
}

function rowMatchesSpectralRange(row, range) {
  if (!range) return true;
  return [finiteNumber(row.parent_sptn), finiteNumber(row.child_sptn)].some((value) => value !== null && value >= range.min && value <= range.max);
}

function parseSpectralTypeNumber(label) {
  const match = String(label || "").trim().match(/^([OBAFGKMLTY])\s*([0-9]+(?:\.[0-9]+)?)/i);
  if (!match) return null;
  const offsets = { O: -60, B: -50, A: -40, F: -30, G: -20, K: -10, M: 0, L: 10, T: 20, Y: 30 };
  return offsets[match[1].toUpperCase()] + Number(match[2]);
}

function spectralTicksForAxis(rows, key) {
  const values = (rows || [])
    .map((row) => finiteNumber(row[key]))
    .filter((value) => value !== null);
  if (!values.length) return cexSpectralTypeTicks.filter(([value]) => value >= -10).map(([value, label]) => ({ value, label }));
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const tickMin = Math.floor(minValue / 10) * 10;
  const tickMax = Math.ceil(maxValue / 5) * 5;
  const ticks = cexSpectralTypeTicks
    .filter(([value]) => value >= tickMin && value <= tickMax)
    .map(([value, label]) => ({ value, label }));
  return ticks.length ? ticks : [{ value: Math.round(minValue), label: formatSpectralTickLabel(minValue) }];
}

function formatSpectralTickLabel(value) {
  const rounded = Math.round(value);
  const candidate = cexSpectralTypeTicks.find(([tickValue]) => tickValue === rounded);
  if (candidate) return candidate[1];
  return formatCell(value);
}

function finiteNumber(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function validFilterLimit(value) {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function usableAgeMyr(value) {
  const age = finiteNumber(value);
  return age !== null && age > 0 ? age : null;
}

function formatAgeMyrCell(value) {
  const age = usableAgeMyr(value);
  return age === null ? "NULL" : formatCell(age);
}

function formatAgeMyrText(value) {
  const age = formatAgeMyrCell(value);
  return age === "NULL" ? age : `${age} Myr`;
}

function formatCell(value) {
  const number = finiteNumber(value);
  if (number === null) return value === null || value === undefined ? "" : String(value);
  if (Math.abs(number) >= 1e4 || (Math.abs(number) > 0 && Math.abs(number) < 1e-3)) return number.toExponential(3);
  if (Math.abs(number) >= 100) return number.toFixed(1);
  if (Math.abs(number) >= 10) return number.toFixed(2);
  return number.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function truthyParam(value, fallback = false) {
  if (value === null || value === undefined || value === "") return Boolean(fallback);
  return ["1", "true", "yes", "on"].includes(String(value).toLowerCase());
}

function clampNumber(value, min, max) {
  const number = Number(value);
  if (!Number.isFinite(number)) return min;
  return Math.min(Math.max(number, min), max);
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
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

function plotConfig(filename) {
  return {
    responsive: true,
    displaylogo: false,
    toImageButtonOptions: {
      filename,
      format: "png",
      scale: 2,
    },
  };
}
