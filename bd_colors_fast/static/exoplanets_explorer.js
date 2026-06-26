const exoDefaultAxes = [
  { key: "orbital_period_days", label: "Orbital Period (days)", title: "Orbital Period (days)", defaultLog: true, positive: true, unc: "orbital_period_days_unc", uncPos: "orbital_period_days_unc_pos", uncNeg: "orbital_period_days_unc_neg" },
  { key: "sep_au", label: "Semi-major Axis / Projected Separation (AU)", title: "Semi-major Axis / Projected Separation (AU)", defaultLog: true, positive: true, unc: "sep_au_unc", uncPos: "sep_au_unc_pos", uncNeg: "sep_au_unc_neg" },
  { key: "sep_mas", label: "Angular Separation (mas)", title: "Angular Separation (mas)", defaultLog: true, positive: true, unc: "sep_mas_unc", uncPos: "sep_mas_unc_pos", uncNeg: "sep_mas_unc_neg" },
  { key: "planet_radius_rearth", label: "Planet Radius (R_earth)", title: "Planet Radius (<i>R</i><sub>Earth</sub>)", defaultLog: true, positive: true, unc: "planet_radius_rearth_unc", uncPos: "planet_radius_rearth_unc_pos", uncNeg: "planet_radius_rearth_unc_neg" },
  { key: "planet_radius_rjup", label: "Planet Radius (R_jup)", title: "Planet Radius (<i>R</i><sub>Jup</sub>)", defaultLog: true, positive: true, unc: "planet_radius_rjup_unc", uncPos: "planet_radius_rjup_unc_pos", uncNeg: "planet_radius_rjup_unc_neg" },
  { key: "planet_mass_mearth", label: "Planet Mass (M_earth)", title: "Planet Mass (<i>M</i><sub>Earth</sub>)", defaultLog: true, positive: true, unc: "planet_mass_mearth_unc", uncPos: "planet_mass_mearth_unc_pos", uncNeg: "planet_mass_mearth_unc_neg", confirmedOnly: true },
  { key: "planet_mass_mjup", label: "Planet Mass (M_jup)", title: "Planet Mass (<i>M</i><sub>Jup</sub>)", defaultLog: true, positive: true, unc: "planet_mass_mjup_unc", uncPos: "planet_mass_mjup_unc_pos", uncNeg: "planet_mass_mjup_unc_neg", confirmedOnly: true },
  { key: "planet_density_gcm3", label: "Planet Density (g/cm^3)", title: "Planet Density (g cm<sup>-3</sup>)", defaultLog: true, positive: true, confirmedOnly: true },
  { key: "planet_eq_temp_k", label: "Equilibrium Temperature (K)", title: "Equilibrium Temperature (K)", positive: true },
  { key: "planet_insolation_earth", label: "Insolation (Earth flux)", title: "Insolation (<i>S</i><sub>Earth</sub>)", defaultLog: true, positive: true },
  { key: "planet_eccentricity", label: "Eccentricity", title: "Eccentricity", confirmedOnly: true },
  { key: "planet_inclination_deg", label: "Orbital Inclination (deg)", title: "Orbital Inclination (deg)", positive: true, confirmedOnly: true },
  { key: "transit_depth", label: "Transit Depth", title: "Transit Depth", defaultLog: true, positive: true, unc: "transit_depth_unc", uncPos: "transit_depth_unc_pos", uncNeg: "transit_depth_unc_neg" },
  { key: "transit_duration_hours", label: "Transit Duration (hours)", title: "Transit Duration (hours)", defaultLog: true, positive: true, unc: "transit_duration_hours_unc", uncPos: "transit_duration_hours_unc_pos", uncNeg: "transit_duration_hours_unc_neg" },
  { key: "planet_star_radius_ratio", label: "Planet/Star Radius Ratio", title: "Planet/Star Radius Ratio", defaultLog: true, positive: true, confirmedOnly: true },
  { key: "rv_semiamplitude_ms", label: "RV Semi-amplitude (m/s)", title: "RV Semi-amplitude (m s<sup>-1</sup>)", defaultLog: true, positive: true, confirmedOnly: true },
  { key: "host_distance_pc", label: "Host Distance (pc)", title: "Host Distance (pc)", positive: true, unc: "host_distance_pc_unc", uncPos: "host_distance_pc_unc_pos", uncNeg: "host_distance_pc_unc_neg" },
  { key: "host_age_myr", label: "Host Age (Myr)", title: "Host Age (Myr)", defaultLog: true, positive: true, unc: "host_age_myr_unc", uncPos: "host_age_myr_unc_pos", uncNeg: "host_age_myr_unc_neg" },
  { key: "host_sptn", label: "Host Spectral Type", title: "Host Spectral Type", spectralTypeAxis: true },
  { key: "host_teff_k", label: "Host Effective Temperature (K)", title: "Host Effective Temperature (K)", positive: true, unc: "host_teff_k_unc", uncPos: "host_teff_k_unc_pos", uncNeg: "host_teff_k_unc_neg" },
  { key: "host_radius_rsun", label: "Host Radius (R_sun)", title: "Host Radius (<i>R</i><sub>Sun</sub>)", positive: true, unc: "host_radius_rsun_unc", uncPos: "host_radius_rsun_unc_pos", uncNeg: "host_radius_rsun_unc_neg" },
  { key: "host_mass_msun", label: "Host Mass (M_sun)", title: "Host Mass (<i>M</i><sub>Sun</sub>)", positive: true, unc: "host_mass_msun_unc", uncPos: "host_mass_msun_unc_pos", uncNeg: "host_mass_msun_unc_neg" },
  { key: "host_logg", label: "Host log g", title: "Host log g" },
  { key: "host_metallicity_dex", label: "Host Metallicity (dex)", title: "Host Metallicity (dex)", confirmedOnly: true },
  { key: "host_tmag", label: "TESS Magnitude", title: "TESS Magnitude" },
  { key: "ra_deg", label: "RA (deg)", title: "RA (deg)" },
  { key: "dec_deg", label: "Dec (deg)", title: "Dec (deg)" },
  { key: "pmra_masyr", label: "Proper Motion RA (mas/yr)", title: "Proper Motion RA (mas yr<sup>-1</sup>)" },
  { key: "pmdec_masyr", label: "Proper Motion Dec (mas/yr)", title: "Proper Motion Dec (mas yr<sup>-1</sup>)" },
  { key: "mass_ratio_q", label: "Mass Ratio q", title: "Mass Ratio q", defaultLog: true, positive: true, confirmedOnly: true, unc: "mass_ratio_q_unc", uncPos: "mass_ratio_q_unc_pos", uncNeg: "mass_ratio_q_unc_neg" },
  { key: "total_system_mass_msun", label: "Total System Mass (M_sun)", title: "Total System Mass (<i>M</i><sub>Sun</sub>)", positive: true, confirmedOnly: true, unc: "total_system_mass_msun_unc", uncPos: "total_system_mass_msun_unc_pos", uncNeg: "total_system_mass_msun_unc_neg" },
  { key: "binding_energy_erg", label: "Binding Energy (erg)", title: "Binding Energy (erg)", defaultLog: true, positive: true, confirmedOnly: true, unc: "binding_energy_erg_unc", uncPos: "binding_energy_erg_unc_pos", uncNeg: "binding_energy_erg_unc_neg" },
  { key: "discovery_year", label: "Discovery Year", title: "Discovery Year", positive: true, confirmedOnly: true },
];

const exoTessAxisKeys = new Set([
  "orbital_period_days", "sep_au", "sep_mas", "planet_radius_rearth", "planet_radius_rjup",
  "planet_eq_temp_k", "planet_insolation_earth", "transit_depth", "transit_duration_hours",
  "host_distance_pc", "host_age_myr", "host_sptn", "host_teff_k", "host_radius_rsun",
  "host_mass_msun", "host_logg", "host_tmag", "ra_deg", "dec_deg", "pmra_masyr", "pmdec_masyr",
]);

const exoRangeFilters = [
  { key: "orbital_period_days", minId: "exo-filter-period-min", maxId: "exo-filter-period-max", minParam: "period_min", maxParam: "period_max", nullId: "exo-filter-orbital-period-days-null" },
  { key: "planet_mass_mjup", minId: "exo-filter-mass-mjup-min", maxId: "exo-filter-mass-mjup-max", minParam: "mass_mjup_min", maxParam: "mass_mjup_max", nullId: "exo-filter-planet-mass-mjup-null" },
  { key: "host_age_myr", minId: "exo-filter-age-min", maxId: "exo-filter-age-max", minParam: "age_myr_min", maxParam: "age_myr_max", nullId: "exo-filter-host-age-myr-null" },
  { key: "planet_radius_rjup", minId: "exo-filter-radius-rjup-min", maxId: "exo-filter-radius-rjup-max", minParam: "radius_rjup_min", maxParam: "radius_rjup_max", nullId: "exo-filter-planet-radius-rjup-null" },
  { key: "host_distance_pc", minId: "exo-filter-distance-min", maxId: "exo-filter-distance-max", minParam: "distance_pc_min", maxParam: "distance_pc_max", nullId: "exo-filter-host-distance-pc-null" },
  { key: "sep_au", minId: "exo-filter-sep-au-min", maxId: "exo-filter-sep-au-max", minParam: "sep_au_min", maxParam: "sep_au_max", nullId: "exo-filter-sep-au-null" },
  { key: "host_teff_k", minId: "exo-filter-host-teff-min", maxId: "exo-filter-host-teff-max", minParam: "host_teff_min", maxParam: "host_teff_max", nullId: "exo-filter-host-teff-k-null" },
  { key: "host_mass_msun", minId: "exo-filter-host-mass-min", maxId: "exo-filter-host-mass-max", minParam: "host_mass_min", maxParam: "host_mass_max", nullId: "exo-filter-host-mass-msun-null" },
];

const exoAgeColorTicks = [1, 10, 50, 100, 300, 1000, 3000];
const exoAgeColorScale = [
  [0.00, "#3f5bff"],
  [0.20, "#1e9df0"],
  [0.38, "#31d8cf"],
  [0.55, "#76ed91"],
  [0.72, "#ffd16b"],
  [0.87, "#ff7043"],
  [1.00, "#e70012"],
];
const exoMethodPalette = ["#2563EB", "#0F766E", "#C026D3", "#EA580C", "#65A30D", "#DC2626", "#7C3AED", "#0891B2", "#4B5563", "#CA8A04"];
const exoMethodColorOverrides = new Map([
  ["Transit", exoMethodPalette[0]],
  ["Radial Velocity", exoMethodPalette[1]],
  ["Imaging", exoMethodPalette[2]],
  ["Direct Imaging", exoMethodPalette[2]],
  ["Microlensing", exoMethodPalette[3]],
  ["Transit Timing Variations", exoMethodPalette[4]],
  ["Eclipse Timing Variations", exoMethodPalette[5]],
  ["Astrometry", exoMethodPalette[6]],
  ["Orbital Brightness Modulation", exoMethodPalette[7]],
  ["Pulsar Timing", exoMethodPalette[8]],
  ["Pulsation Timing Variations", exoMethodPalette[8]],
  ["Disk Kinematics", exoMethodPalette[9]],
]);
const exoMethodSymbols = new Map([
  ["Transit", "circle"],
  ["Radial Velocity", "diamond"],
  ["Imaging", "star"],
  ["Direct Imaging", "star"],
  ["Microlensing", "square"],
  ["Transit Timing Variations", "triangle-up"],
  ["Eclipse Timing Variations", "triangle-down"],
  ["Astrometry", "cross"],
  ["Orbital Brightness Modulation", "hexagon"],
  ["Pulsar Timing", "x"],
  ["Pulsation Timing Variations", "x"],
  ["Disk Kinematics", "star-diamond"],
]);
const exoSpectralTypeTicks = [
  [-60, "O0"], [-50, "B0"], [-40, "A0"], [-30, "F0"], [-20, "G0"], [-10, "K0"],
  [0, "M0"], [5, "M5"], [10, "L0"], [15, "L5"], [20, "T0"], [25, "T5"], [30, "Y0"],
];
const exoErrorBarStyle = { thickness: 0.8, width: 0 };
const exoExportColumns = [
  "row_kind", "planet_id", "planet_name", "host_name", "moca_oid_parent", "discoverymethod", "tfopwg_disp",
  "orbital_period_days", "planet_radius_rjup", "planet_radius_rearth", "planet_mass_mjup", "planet_mass_mearth",
  "sep_au", "sep_mas", "mass_ratio_q", "binding_energy_erg", "host_age_myr", "host_age_source",
  "host_distance_pc", "host_distance_source", "host_spt", "host_sptn", "host_teff_k", "host_radius_rsun",
  "host_mass_msun", "host_logg", "host_metallicity_dex", "host_tmag", "planet_eq_temp_k",
  "planet_insolation_earth", "planet_density_gcm3", "planet_eccentricity", "transit_depth",
  "transit_duration_hours", "ra_deg", "dec_deg", "toi", "tid", "nasa_id",
];
const exoNumericExportColumns = new Set(exoExportColumns.filter((column) => ![
  "row_kind", "planet_id", "planet_name", "host_name", "discoverymethod", "tfopwg_disp",
  "host_age_source", "host_distance_source", "host_spt",
].includes(column)));

const exoState = {
  axes: new Map(exoDefaultAxes.map((axis) => [axis.key, axis])),
  rows: [],
  payload: null,
  highlightOids: new Set(),
  highlightRowIds: new Set(),
  selectedIds: new Set(),
  designationIndex: null,
  designationIndexKey: "",
  designationIndexPromise: null,
  designationCacheBust: "",
  searchTimer: null,
  filterLoadTimer: null,
  loadToken: 0,
};
const exoEl = {};

document.addEventListener("DOMContentLoaded", initExoplanetsExplorer);

const exoAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function exoAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), exoAppBaseUrl).toString();
}

async function initExoplanetsExplorer() {
  collectExoplanetElements();
  populateExoplanetAxisSelects();
  readExoplanetUrlState();
  bindExoplanetControls();
  await loadExoplanetData();
}

function collectExoplanetElements() {
  [
    "exo-status", "exo-x-axis", "exo-y-axis", "exo-x-log", "exo-y-log",
    "exo-object-search", "exo-object-results", "exo-selected-objects", "exo-highlight-oids",
    "exo-color-age", "exo-show-confirmed", "exo-show-tess", "exo-error-bars",
    "exo-hover-text",
    "exo-filter-method", "exo-spt-range",
    "exo-use-photometric-distances",
    ...exoRangeFilters.flatMap((filter) => [filter.minId, filter.maxId, filter.nullId]),
    "exo-max-confirmed", "exo-max-tess", "exo-load", "exo-clear-cache", "exo-clear-cache-status",
    "exo-plot", "exo-plot-loader", "exo-summary", "exo-subtitle",
    "exo-clear-selection", "exo-export-csv", "exo-export-tsv",
    "exo-table-title", "exo-table-subtitle", "exo-table",
  ].forEach((id) => { exoEl[id] = document.getElementById(id); });
}

function bindExoplanetControls() {
  exoEl["exo-load"].addEventListener("click", () => loadExoplanetData());
  exoEl["exo-clear-cache"].addEventListener("click", () => clearExoplanetCache());
  for (const id of ["exo-x-axis", "exo-y-axis"]) {
    exoEl[id].addEventListener("change", () => {
      applyAxisLogDefaults();
      updateTessAvailability();
      updateExoplanetUrl();
      loadExoplanetData();
    });
  }
  for (const id of ["exo-x-log", "exo-y-log", "exo-show-confirmed", "exo-show-tess"]) {
    exoEl[id].addEventListener("change", () => {
      updateExoplanetUrl();
      loadExoplanetData();
    });
  }
  for (const id of ["exo-color-age", "exo-error-bars", "exo-hover-text", "exo-filter-method"]) {
    exoEl[id].addEventListener("input", () => {
      updateExoplanetUrl();
      renderExoplanetsExplorer();
    });
    exoEl[id].addEventListener("change", () => {
      updateExoplanetUrl();
      renderExoplanetsExplorer();
    });
  }
  exoEl["exo-highlight-oids"].addEventListener("change", () => {
    setExoplanetHighlightOids(parseIntegerList(exoEl["exo-highlight-oids"].value));
  });
  exoEl["exo-highlight-oids"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") setExoplanetHighlightOids(parseIntegerList(exoEl["exo-highlight-oids"].value));
  });
  exoEl["exo-object-search"].addEventListener("input", () => {
    clearTimeout(exoState.searchTimer);
    const value = exoEl["exo-object-search"].value.trim();
    exoState.searchTimer = setTimeout(() => searchExoplanetTargets(value), 220);
  });
  exoEl["exo-object-search"].addEventListener("focus", () => {
    const value = exoEl["exo-object-search"].value.trim();
    if (value) searchExoplanetTargets(value);
  });
  document.addEventListener("click", (event) => {
    if (!exoEl["exo-object-results"].contains(event.target) && event.target !== exoEl["exo-object-search"]) {
      exoEl["exo-object-results"].hidden = true;
    }
  });
  exoEl["exo-spt-range"].addEventListener("input", () => {
    updateExoplanetUrl();
    scheduleExoplanetDataLoad();
  });
  exoEl["exo-use-photometric-distances"].addEventListener("change", () => {
    updateExoplanetUrl();
    loadExoplanetData();
  });
  for (const filter of exoRangeFilters) {
    for (const id of [filter.minId, filter.maxId]) {
      exoEl[id].addEventListener("input", () => {
        updateExoplanetUrl();
        scheduleExoplanetDataLoad();
        renderExoplanetsExplorer();
      });
    }
    exoEl[filter.nullId].addEventListener("change", () => {
      updateExoplanetUrl();
      scheduleExoplanetDataLoad();
      renderExoplanetsExplorer();
    });
  }
  for (const id of ["exo-max-confirmed", "exo-max-tess"]) {
    exoEl[id].addEventListener("change", () => loadExoplanetData());
  }
  exoEl["exo-clear-selection"].addEventListener("click", () => {
    exoState.selectedIds.clear();
    renderExoplanetTable();
    renderExoplanetsExplorer();
  });
  exoEl["exo-export-csv"].addEventListener("click", () => exportExoplanetRows("csv"));
  exoEl["exo-export-tsv"].addEventListener("click", () => exportExoplanetRows("tsv"));
  window.addEventListener("resize", debounce(() => {
    if (exoEl["exo-plot"] && exoState.payload) Plotly.Plots.resize(exoEl["exo-plot"]);
  }, 150));
}

function populateExoplanetAxisSelects() {
  const axes = [...exoState.axes.values()];
  for (const id of ["exo-x-axis", "exo-y-axis"]) {
    const current = exoEl[id]?.value || (id === "exo-x-axis" ? "sep_au" : "planet_mass_mjup");
    exoEl[id].innerHTML = axes.map((axis) => `<option value="${escapeHtml(axis.key)}">${escapeHtml(axis.label || axis.key)}</option>`).join("");
    exoEl[id].value = exoState.axes.has(current) ? current : (id === "exo-x-axis" ? "sep_au" : "planet_mass_mjup");
  }
}

function readExoplanetUrlState() {
  const params = new URLSearchParams(window.location.search);
  exoEl["exo-x-axis"].value = params.get("x") || params.get("xaxis") || "sep_au";
  exoEl["exo-y-axis"].value = params.get("y") || params.get("yaxis") || "planet_mass_mjup";
  exoEl["exo-x-log"].checked = truthyParam(params.get("xlog") ?? params.get("x_log"), axisSpec(exoEl["exo-x-axis"].value).defaultLog);
  exoEl["exo-y-log"].checked = truthyParam(params.get("ylog") ?? params.get("y_log"), axisSpec(exoEl["exo-y-axis"].value).defaultLog);
  exoEl["exo-color-age"].checked = truthyParam(params.get("color_age") ?? params.get("color_by_age"), false);
  exoEl["exo-show-confirmed"].checked = truthyParam(params.get("show_confirmed") ?? params.get("confirmed"), true);
  exoEl["exo-show-tess"].checked = truthyParam(params.get("show_tess_candidates") ?? params.get("tess_candidates") ?? params.get("tess"), true);
  exoEl["exo-error-bars"].checked = truthyParam(params.get("errors") ?? params.get("error_bars"), false);
  exoEl["exo-hover-text"].checked = truthyParam(params.get("hover_text") ?? params.get("hover"), true);
  exoEl["exo-filter-method"].value = params.get("method") || params.get("discoverymethod") || "";
  exoEl["exo-spt-range"].value = params.get("spt_range") || params.get("spt") || "";
  exoEl["exo-use-photometric-distances"].checked = truthyParam(
    params.get("use_photometric_distances") ?? params.get("photometric_distances") ?? params.get("phot_dist"),
    false,
  );
  for (const filter of exoRangeFilters) {
    exoEl[filter.minId].value = validNumberText(params.get(filter.minParam));
    exoEl[filter.maxId].value = validNumberText(params.get(filter.maxParam));
    exoEl[filter.nullId].checked = truthyParam(params.get(`ignore_null_${filter.key}`) ?? params.get(`ignore_missing_${filter.key}`), false);
  }
  exoEl["exo-max-confirmed"].value = params.get("max_confirmed") || params.get("max_exoplanets") || "50000";
  exoEl["exo-max-tess"].value = params.get("max_tess_candidates") || params.get("max_tess") || "50000";
  setExoplanetHighlightOids(parseIntegerList(
    params.get("highlight_oids") || params.get("highlight_oid") || params.get("moca_oids") || params.get("moca_oid") || params.get("oids") || params.get("oid") || "",
  ), { quiet: true });
  setExoplanetHighlightRowIds(parseTokenList(
    params.get("highlight_exoplanets") || params.get("highlight_planets") || params.get("exoplanet_ids") || params.get("planet_ids") || "",
  ), { quiet: true });
  updateTessAvailability();
}

function applyAxisLogDefaults() {
  exoEl["exo-x-log"].checked = Boolean(axisSpec(exoEl["exo-x-axis"].value).defaultLog);
  exoEl["exo-y-log"].checked = Boolean(axisSpec(exoEl["exo-y-axis"].value).defaultLog);
}

async function loadExoplanetData(options = {}) {
  clearTimeout(exoState.filterLoadTimer);
  const token = ++exoState.loadToken;
  setExoplanetLoading(true);
  setExoplanetStatus("Loading exoplanets", "loading");
  const params = exoplanetApiParams();
  applyExoplanetDataParams(params);
  if (options.cacheBust) params.set("_cache_bust", String(Date.now()));
  try {
    const payload = await fetchExoplanetJson(`api/exoplanets-explorer/data?${params.toString()}`);
    if (token !== exoState.loadToken) return;
    exoState.payload = payload;
    exoState.rows = payload.rows || [];
    if (Array.isArray(payload.axes) && payload.axes.length) {
      exoState.axes = new Map(payload.axes.map((axis) => [axis.key, axis]));
      populateExoplanetAxisSelects();
    }
    renderHighlightedExoplanetList();
    if (!payload.ok) {
      setExoplanetStatus(payload.error || "Could not load exoplanets", "error");
    } else {
      const meta = payload.meta || {};
      setExoplanetStatus(`${Number(meta.confirmed_count || 0).toLocaleString()} confirmed planets, ${Number(meta.tess_candidate_count || 0).toLocaleString()} TESS candidates loaded`, "");
    }
  } catch (error) {
    if (token !== exoState.loadToken) return;
    exoState.payload = { ok: false, error: error.message };
    exoState.rows = [];
    setExoplanetStatus(error.message || "Could not load exoplanets", "error");
  } finally {
    if (token === exoState.loadToken) {
      setExoplanetLoading(false);
      updateExoplanetUrl();
      renderExoplanetsExplorer();
    }
  }
}

function scheduleExoplanetDataLoad(delay = 350) {
  clearTimeout(exoState.filterLoadTimer);
  exoState.filterLoadTimer = setTimeout(() => loadExoplanetData(), delay);
}

function renderExoplanetsExplorer() {
  const xKey = exoEl["exo-x-axis"].value;
  const yKey = exoEl["exo-y-axis"].value;
  const xLog = exoEl["exo-x-log"].checked;
  const yLog = exoEl["exo-y-log"].checked;
  updateTessAvailability();
  const rows = displayRows();
  const plottable = rows.filter((row) => rowIsPlottable(row, xKey, yKey, xLog, yLog));
  const selected = plottable.filter((row) => exoState.selectedIds.has(rowId(row)));
  const highlighted = plottable.filter((row) => !exoState.selectedIds.has(rowId(row)) && rowIsHighlighted(row));
  const base = plottable.filter((row) => !exoState.selectedIds.has(rowId(row)) && !rowIsHighlighted(row));
  const confirmedBase = base.filter(isConfirmedRow);
  const tessBase = base.filter(isTessRow);
  const confirmedAgeColorbar = exoEl["exo-color-age"].checked && confirmedBase.some(rowHasUsableAge);
  const tessAgeColorbar = exoEl["exo-color-age"].checked && !confirmedAgeColorbar && tessBase.some(rowHasUsableAge);
  const hasAgeColorbar = confirmedAgeColorbar || tessAgeColorbar;
  const traces = [
    ...tessCandidateTraces(tessBase, xKey, yKey, { showAgeColorbar: tessAgeColorbar }),
    ...confirmedPlanetTraces(confirmedBase, xKey, yKey, { showAgeColorbar: confirmedAgeColorbar }),
    highlightTrace(highlighted, xKey, yKey),
    selectedTrace(selected, xKey, yKey),
  ].filter(Boolean);
  const layout = exoplanetLayout(xKey, yKey, xLog, yLog, plottable, { hasAgeColorbar });
  Plotly.react(exoEl["exo-plot"], traces, layout, plotConfigSafe(`exoplanets_explorer_${xKey}_${yKey}`));
  bindExoplanetPlotEvents();
  renderExoplanetSummary(rows, plottable);
  renderExoplanetTable();
  setExoplanetExportDisabled(!rows.length);
}

function confirmedPlanetTraces(rows, xKey, yKey, options = {}) {
  if (!exoEl["exo-show-confirmed"].checked || !rows.length) return [];
  const methods = methodsByDecreasingClassSize(rows);
  if (!exoEl["exo-color-age"].checked) {
    return methods.map((method, index) => {
      const methodRows = rows.filter((row) => (row.discoverymethod || "Unknown") === method);
      return scatterTrace(methodRows, xKey, yKey, {
        name: countLabel(method, methodRows),
        marker: {
          color: methodColor(method, index),
          size: 8,
          opacity: 0.58,
          symbol: exoMethodSymbols.get(method) || "circle",
          line: { color: "rgba(255,255,255,0.86)", width: 0.65 },
        },
      });
    });
  }
  let colorbarAvailable = Boolean(options.showAgeColorbar);
  const traces = [];
  for (const method of methods) {
    const methodRows = rows.filter((row) => (row.discoverymethod || "Unknown") === method);
    const withAge = methodRows.filter(rowHasUsableAge);
    const withoutAge = methodRows.filter((row) => !rowHasUsableAge(row));
    traces.push(scatterTrace(withoutAge, xKey, yKey, {
      name: countLabel(`${method}: age unknown`, withoutAge),
      marker: unknownAgeMarker({ symbol: exoMethodSymbols.get(method) || "circle", size: 8, opacity: 0.24 }),
    }));
    const showColorbar = colorbarAvailable && withAge.length > 0;
    traces.push(scatterTrace(withAge, xKey, yKey, {
      name: countLabel(`${method}: host ages`, withAge),
      marker: ageColorMarker(withAge, { symbol: exoMethodSymbols.get(method) || "circle", size: 8, showColorbar, opacity: 0.64 }),
    }));
    if (showColorbar) colorbarAvailable = false;
  }
  return traces;
}

function tessCandidateTraces(rows, xKey, yKey, options = {}) {
  if (!tessEnabled() || !rows.length) return [];
  const transitSymbol = exoMethodSymbols.get("Transit") || "circle";
  if (exoEl["exo-color-age"].checked) {
    const withAge = rows.filter(rowHasUsableAge);
    const withoutAge = rows.filter((row) => !rowHasUsableAge(row));
    return [
      scatterTrace(withoutAge, xKey, yKey, {
        name: countLabel("TESS candidates: age unknown", withoutAge),
        marker: tessUnknownAgeMarker(transitSymbol),
      }),
      scatterTrace(withAge, xKey, yKey, {
        name: countLabel("TESS candidates: host ages", withAge),
        marker: tessAgeColorMarker(withAge, {
          symbol: transitSymbol,
          showColorbar: options.showAgeColorbar,
        }),
      }),
    ].filter(Boolean);
  }
  return [scatterTrace(rows, xKey, yKey, {
    name: countLabel("TESS candidates", rows),
    marker: {
      color: transitColor(),
      size: 8,
      opacity: 0.45,
      symbol: openMarkerSymbol(transitSymbol),
      line: { color: transitColor(), width: 1.25 },
    },
  })];
}

function selectedTrace(rows, xKey, yKey) {
  if (!rows.length) return null;
  return scatterTrace(rows, xKey, yKey, {
    name: countLabel("Selected", rows),
    marker: { color: "#FACC15", size: 15, opacity: 0.98, symbol: "star", line: { color: "#111111", width: 1.8 } },
  });
}

function highlightTrace(rows, xKey, yKey) {
  if (!rows.length) return null;
  return scatterTrace(rows, xKey, yKey, {
    name: countLabel("Highlighted", rows),
    marker: { color: "#FFD43B", size: 15, opacity: 0.98, symbol: "star", line: { color: "#111111", width: 1.8 } },
  });
}

function scatterTrace(rows, xKey, yKey, options = {}) {
  if (!rows.length) return null;
  const trace = {
    x: rows.map((row) => finiteNumber(row[xKey])),
    y: rows.map((row) => finiteNumber(row[yKey])),
    customdata: rows.map((row) => rowId(row)),
    type: "scattergl",
    mode: "markers",
    name: options.name,
    marker: options.marker,
    showlegend: true,
  };
  if (exoEl["exo-hover-text"].checked) {
    trace.text = rows.map((row) => hoverText(row, xKey, yKey));
    trace.hovertemplate = "%{text}<extra></extra>";
  } else {
    trace.hoverinfo = "skip";
    trace.hovertemplate = null;
  }
  if (exoEl["exo-error-bars"].checked) {
    const color = errorBarColor(options.marker);
    const xError = errorSpec(rows, axisSpec(xKey), color);
    const yError = errorSpec(rows, axisSpec(yKey), color);
    if (xError) trace.error_x = xError;
    if (yError) trace.error_y = yError;
  }
  return trace;
}

function exoplanetLayout(xKey, yKey, xLog, yLog, rows, options = {}) {
  const layout = {
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    margin: { l: 92, r: options.hasAgeColorbar ? 118 : 36, t: 28, b: 84 },
    hovermode: "closest",
    dragmode: "lasso",
    showlegend: true,
    legend: {
      orientation: "v",
      x: 0.985,
      xanchor: "right",
      y: 0.015,
      yanchor: "bottom",
      bgcolor: "rgba(255,255,255,0.84)",
      bordercolor: "rgba(17,17,17,0.72)",
      borderwidth: 1,
      font: { size: 10, color: "#252329" },
    },
    xaxis: plotAxis(xKey, xLog),
    yaxis: plotAxis(yKey, yLog),
    annotations: [],
  };
  if (axisSpec(xKey).spectralTypeAxis) {
    layout.xaxis.tickmode = "array";
    layout.xaxis.tickvals = exoSpectralTypeTicks.map((tick) => tick[0]);
    layout.xaxis.ticktext = exoSpectralTypeTicks.map((tick) => tick[1]);
  }
  if (axisSpec(yKey).spectralTypeAxis) {
    layout.yaxis.tickmode = "array";
    layout.yaxis.tickvals = exoSpectralTypeTicks.map((tick) => tick[0]);
    layout.yaxis.ticktext = exoSpectralTypeTicks.map((tick) => tick[1]);
    layout.yaxis.autorange = "reversed";
  }
  if (!rows.length) {
    layout.annotations.push({
      text: "No exoplanets have finite values for these axes and filters.",
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

function plotAxis(key, logScale) {
  const spec = axisSpec(key);
  const useLog = Boolean(logScale && !spec.spectralTypeAxis);
  const axis = {
    title: { text: spec.title || spec.label || key, font: { size: 21 }, standoff: 12 },
    type: useLog ? "log" : "linear",
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
  if (useLog) {
    axis.exponentformat = "power";
    axis.showexponent = "all";
  }
  return axis;
}

function displayRows() {
  const method = normalizeSearchText(exoEl["exo-filter-method"].value);
  const activeRanges = activeRangeFilters();
  return (exoState.rows || []).filter((row) => {
    if (isConfirmedRow(row) && !exoEl["exo-show-confirmed"].checked) return false;
    if (isTessRow(row) && !tessEnabled()) return false;
    if (method && !normalizeSearchText(row.discoverymethod).includes(method)) return false;
    return rowMatchesRangeFilters(row, activeRanges);
  });
}

function activeRangeFilters() {
  return exoRangeFilters
    .map((filter) => ({
      ...filter,
      min: finiteNumber(exoEl[filter.minId]?.value),
      max: finiteNumber(exoEl[filter.maxId]?.value),
      ignoreNull: Boolean(exoEl[filter.nullId]?.checked),
    }))
    .filter((filter) => filter.min !== null || filter.max !== null || filter.ignoreNull);
}

function rowMatchesRangeFilters(row, filters) {
  for (const filter of filters) {
    const value = finiteNumber(row[filter.key]);
    if (value === null) {
      if (filter.ignoreNull) return false;
      continue;
    }
    if (filter.min !== null && value < filter.min) return false;
    if (filter.max !== null && value > filter.max) return false;
  }
  return true;
}

function rowIsPlottable(row, xKey, yKey, xLog, yLog) {
  const x = finiteNumber(row[xKey]);
  const y = finiteNumber(row[yKey]);
  if (x === null || y === null) return false;
  if (xLog && !axisSpec(xKey).spectralTypeAxis && x <= 0) return false;
  if (yLog && !axisSpec(yKey).spectralTypeAxis && y <= 0) return false;
  return true;
}

function bindExoplanetPlotEvents() {
  const plot = exoEl["exo-plot"];
  plot.removeAllListeners?.("plotly_click");
  plot.removeAllListeners?.("plotly_selected");
  plot.removeAllListeners?.("plotly_deselect");
  plot.on?.("plotly_click", (event) => {
    const ids = idsFromEventPoints(event?.points || []);
    if (!ids.length) return;
    if (!event?.event?.shiftKey && !event?.event?.metaKey && !event?.event?.ctrlKey) exoState.selectedIds.clear();
    ids.slice(0, 1).forEach((id) => exoState.selectedIds.add(id));
    refreshSelectionUi();
  });
  plot.on?.("plotly_selected", (event) => {
    const ids = idsFromEventPoints(event?.points || []);
    if (!ids.length) return;
    if (!event?.event?.shiftKey && !event?.event?.metaKey && !event?.event?.ctrlKey) exoState.selectedIds.clear();
    ids.forEach((id) => exoState.selectedIds.add(id));
    refreshSelectionUi();
  });
  plot.on?.("plotly_deselect", () => {
    exoState.selectedIds.clear();
    refreshSelectionUi();
  });
}

function refreshSelectionUi() {
  const xKey = exoEl["exo-x-axis"].value;
  const yKey = exoEl["exo-y-axis"].value;
  const rows = displayRows();
  const plottable = rows.filter((row) => rowIsPlottable(row, xKey, yKey, exoEl["exo-x-log"].checked, exoEl["exo-y-log"].checked));
  renderExoplanetSummary(rows, plottable);
  renderExoplanetTable();
  setExoplanetExportDisabled(!rows.length);
}

function renderExoplanetSummary(rows, plottable) {
  const total = exoState.rows.length;
  const confirmed = rows.filter(isConfirmedRow).length;
  const tess = rows.filter(isTessRow).length;
  const selected = (exoState.rows || []).filter((row) => exoState.selectedIds.has(rowId(row))).length;
  const highlighted = highlightedRows().length;
  const cache = exoState.payload?.cache?.hit ? "cached" : exoState.payload?.source || "";
  exoEl["exo-summary"].textContent = `${plottable.length.toLocaleString()} plotted; ${rows.length.toLocaleString()} of ${total.toLocaleString()} rows filtered; ${confirmed.toLocaleString()} confirmed, ${tess.toLocaleString()} TESS${selected ? `; ${selected} selected` : ""}${highlighted ? `; ${highlighted} highlighted` : ""}`;
  exoEl["exo-subtitle"].textContent = `${axisSpec(exoEl["exo-x-axis"].value).label} vs ${axisSpec(exoEl["exo-y-axis"].value).label}${cache ? ` (${cache})` : ""}`;
}

function renderExoplanetTable() {
  const rows = selectedRows();
  const hasSelection = Boolean(exoState.selectedIds.size);
  exoEl["exo-clear-selection"].disabled = !hasSelection;
  exoEl["exo-table-title"].textContent = hasSelection ? "Selected exoplanets" : "Highlighted exoplanets";
  exoEl["exo-table-subtitle"].textContent = rows.length ? `${rows.length.toLocaleString()} rows` : "Click, lasso, or highlight objects in the plot.";
  if (!rows.length) {
    exoEl["exo-table"].innerHTML = `<div class="designation-result-note">No exoplanets selected.</div>`;
    return;
  }
  const columns = selectionColumns();
  exoEl["exo-table"].innerHTML = `<table><thead><tr>${columns.map((column) => `<th>${escapeHtml(tableHeader(column))}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => (
    `<tr>${columns.map((column) => `<td>${tableCellHtml(row, column)}</td>`).join("")}</tr>`
  )).join("")}</tbody></table>`;
}

function selectedRows() {
  const selected = (exoState.rows || []).filter((row) => exoState.selectedIds.has(rowId(row)));
  return selected.length ? selected : highlightedRows();
}

function highlightedRows() {
  return (exoState.rows || []).filter(rowIsHighlighted);
}

function selectionColumns() {
  return [
    "dataset", "planet_name", "host_name", "host_report_url", "discoverymethod", "tfopwg_disp",
    "host_age_myr", "host_age_source", "orbital_period_days", "planet_radius_rjup",
    "planet_mass_mjup", "sep_au", "sep_mas", "host_distance_pc", "host_spt",
    "host_teff_k", "host_mass_msun", "toi", "tid", "nasa_id",
  ];
}

function tableCellHtml(row, column) {
  if (column === "host_report_url") return reportButtonHtml(row.host_report_url, "Host Report");
  if (column === "host_age_myr") return escapeHtml(formatAgeMyrCell(row[column]));
  if (column === "dataset") return escapeHtml(row.dataset || row.row_kind || "");
  return escapeHtml(formatCell(row[column]));
}

function reportButtonHtml(url, label) {
  if (!url) return `<span class="button-link is-disabled">${escapeHtml(label)}</span>`;
  return `<a class="button-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
}

async function searchExoplanetTargets(query) {
  if (!query || query.length < 2) {
    exoEl["exo-object-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    exoEl["exo-object-results"].hidden = false;
    return;
  }
  exoEl["exo-object-results"].innerHTML = `<div class="designation-result-note">Searching designations...</div>`;
  exoEl["exo-object-results"].hidden = false;
  try {
    const index = await ensureExoplanetDesignationIndex();
    if (normalizeSearchText(exoEl["exo-object-search"].value) !== normalizeSearchText(query)) return;
    const indexResults = localExoplanetSearchResults(query, index);
    if (indexResults.length) {
      renderExoplanetSearchResults(indexResults);
      return;
    }
  } catch (error) {
    console.warn("Exoplanet designation index unavailable", error);
  }
  const localResults = localExoplanetSearchResults(query, exoState.rows || []);
  if (localResults.length) {
    renderExoplanetSearchResults(localResults);
    return;
  }
  const params = exoplanetDesignationParams();
  params.set("q", query);
  const payload = await fetchExoplanetJson(`api/exoplanets-explorer/search?${params.toString()}`);
  renderExoplanetSearchResults(payload.options || []);
}

async function ensureExoplanetDesignationIndex() {
  const key = `${exoEl["exo-show-confirmed"].checked ? "confirmed" : "no-confirmed"}:${tessEnabled() ? "tess" : "no-tess"}`;
  if (exoState.designationIndex && exoState.designationIndexKey === key) return exoState.designationIndex;
  if (exoState.designationIndexPromise && exoState.designationIndexKey === key) return exoState.designationIndexPromise;
  exoState.designationIndexKey = key;
  const params = exoplanetDesignationParams();
  if (exoState.designationCacheBust) params.set("_cache_bust", exoState.designationCacheBust);
  exoState.designationIndexPromise = fetchExoplanetJson(`api/exoplanets-explorer/designations?${params.toString()}`)
    .then((payload) => {
      if (!payload.ok) throw new Error(payload.error || "Could not load designation index");
      exoState.designationIndex = payload.options || [];
      return exoState.designationIndex;
    })
    .finally(() => {
      exoState.designationIndexPromise = null;
    });
  return exoState.designationIndexPromise;
}

function exoplanetDesignationParams() {
  const params = exoplanetApiParams();
  params.set("include_confirmed", exoEl["exo-show-confirmed"].checked ? "1" : "0");
  params.set("include_tess_candidates", tessEnabled() ? "1" : "0");
  params.set("max_confirmed", exoEl["exo-max-confirmed"].value || "50000");
  params.set("max_tess_candidates", exoEl["exo-max-tess"].value || "50000");
  return params;
}

function localExoplanetSearchResults(query, rows = []) {
  const needle = normalizeSearchText(query);
  if (!needle) return [];
  const sourceRows = rows || [];
  const hostCounts = new Map();
  for (const row of sourceRows) {
    const oid = exoplanetHostOid(row);
    if (oid !== null && exoplanetResultKind(row) !== "host") hostCounts.set(oid, (hostCounts.get(oid) || 0) + 1);
  }
  const hostResults = [];
  const seenHosts = new Set();
  const planetResults = [];
  for (const row of sourceRows) {
    const kind = exoplanetResultKind(row);
    const oid = exoplanetHostOid(row);
    if (kind === "host" || oid !== null) {
      const hostKey = oid !== null ? String(oid) : normalizeSearchText(exoplanetHostName(row));
      if (hostKey && !seenHosts.has(hostKey)) {
        seenHosts.add(hostKey);
        const hostFields = [
          exoplanetHostName(row),
          row.parent_designations,
          oid,
        ].map(normalizeSearchText);
        if (hostFields.some((value) => value.includes(needle))) {
          hostResults.push({
            ...row,
            result_kind: "host",
            value: oid,
            moca_oid: oid,
            label: exoplanetSearchResultMainLabel({ ...row, result_kind: "host", value: oid }),
            main_label: exoplanetSearchResultMainLabel({ ...row, result_kind: "host", value: oid }),
            detail_label: exoplanetSearchResultDetailLabel({ ...row, result_kind: "host", value: oid }, needle, hostCounts.get(oid) || 0),
          });
        }
      }
    }
    if (kind === "host") continue;
    const rowIdentifier = exoplanetOptionRowId(row);
    const textFields = [
      exoplanetPlanetName(row),
      exoplanetHostName(row),
      row.parent_designations,
      row.child_designations,
      rowIdentifier,
      row.nasa_id,
      row.tess_candidate_id,
      row.toi,
      row.tid,
      oid,
    ].map(normalizeSearchText);
    if (!textFields.some((value) => value.includes(needle))) continue;
    planetResults.push({
      ...row,
      result_kind: kind,
      value: rowIdentifier,
      label: exoplanetSearchResultLabel(row, needle),
      main_label: exoplanetSearchResultMainLabel(row),
      detail_label: exoplanetSearchResultDetailLabel(row, needle),
    });
    if (planetResults.length >= 80) break;
  }
  const hostLimit = Math.min(hostResults.length, 30);
  return [
    ...hostResults.slice(0, hostLimit),
    ...planetResults.slice(0, 80 - hostLimit),
  ].slice(0, 80);
}

function renderExoplanetSearchResults(results) {
  if (!results.length) {
    exoEl["exo-object-results"].innerHTML = `<div class="designation-result-note">No matching objects found</div>`;
    exoEl["exo-object-results"].hidden = false;
    return;
  }
  exoEl["exo-object-results"].innerHTML = results.map((result, index) => searchResultButtonHtml(result, index)).join("");
  exoEl["exo-object-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const result = results[Number(button.dataset.index)];
      if (exoplanetResultKind(result) === "host") {
        addExoplanetHighlightOid(result.moca_oid ?? result.moca_oid_parent ?? result.value);
      } else {
        addExoplanetHighlightRowId(result.value || exoplanetOptionRowId(result));
      }
      exoEl["exo-object-search"].value = result.label || exoplanetSearchResultMainLabel(result);
      exoEl["exo-object-results"].hidden = true;
    });
  });
  exoEl["exo-object-results"].hidden = false;
}

function searchResultButtonHtml(result, index) {
  const main = result.main_label || result.label || exoplanetSearchResultMainLabel(result);
  const detail = result.detail_label || "";
  return [
    `<button class="designation-result" type="button" data-index="${index}">`,
    `<span class="designation-result-main">${escapeHtml(main)}</span>`,
    detail ? `<span class="designation-result-meta">${escapeHtml(detail)}</span>` : "",
    "</button>",
  ].join("");
}

function exoplanetSearchResultLabel(row, needle) {
  const base = exoplanetSearchResultMainLabel(row);
  const aliases = matchingExoplanetAliasLabels(row, needle);
  return aliases.length ? `${base} [${aliases.slice(0, 3).join("; ")}]` : base;
}

function exoplanetSearchResultMainLabel(row) {
  const kind = exoplanetResultKind(row);
  if (kind === "host") {
    const oid = exoplanetHostOid(row);
    return `${oid !== null ? `oid${oid}: ` : ""}${exoplanetHostName(row) || "host"}`;
  }
  const prefix = kind === "tess_candidate" ? "TESS" : "planet";
  return `${prefix}: ${exoplanetHostName(row) || "host"} -> ${exoplanetPlanetName(row) || "planet"}`;
}

function exoplanetSearchResultDetailLabel(row, needle, hostCount = 0) {
  if (exoplanetResultKind(row) === "host") {
    const aliases = matchingExoplanetAliasLabels(row, needle);
    const countText = hostCount ? `${hostCount.toLocaleString()} row${hostCount === 1 ? "" : "s"}` : "";
    return [countText, ...aliases.slice(0, 2)].filter(Boolean).join("; ");
  }
  const aliases = matchingExoplanetAliasLabels(row, needle);
  if (aliases.length) return aliases.slice(0, 3).join("; ");
  const details = [];
  if (row.discoverymethod) details.push(row.discoverymethod);
  if (row.tfopwg_disp) details.push(row.tfopwg_disp);
  if (row.toi) details.push(`TOI ${row.toi}`);
  if (row.tid) details.push(`TIC ${row.tid}`);
  const oid = exoplanetHostOid(row);
  if (oid !== null) details.push(`oid${oid}`);
  return details.slice(0, 3).join("; ");
}

function matchingExoplanetAliasLabels(row, needle) {
  const labels = [];
  for (const [field, prefix] of [["parent_designations", "host"], ["child_designations", "planet"]]) {
    for (const alias of splitDesignationAliases(row[field])) {
      if (normalizeSearchText(alias).includes(needle) && alias !== exoplanetHostName(row) && alias !== exoplanetPlanetName(row)) {
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

function addExoplanetHighlightOid(oid) {
  const value = finiteInteger(oid);
  if (value === null) return;
  exoState.highlightOids.add(value);
  syncHighlightOidInput();
  renderHighlightedExoplanetList();
  updateExoplanetUrl();
  if (!(exoState.rows || []).some((row) => exoplanetHostOid(row) === value)) loadExoplanetData();
  else renderExoplanetsExplorer();
}

function setExoplanetHighlightOids(oids, options = {}) {
  exoState.highlightOids = new Set((oids || []).map(finiteInteger).filter((value) => value !== null));
  syncHighlightOidInput();
  renderHighlightedExoplanetList();
  if (!options.quiet) {
    updateExoplanetUrl();
    loadExoplanetData();
  }
}

function addExoplanetHighlightRowId(id) {
  const value = String(id || "").trim();
  if (!value) return;
  exoState.highlightRowIds.add(value);
  renderHighlightedExoplanetList();
  updateExoplanetUrl();
  if (!(exoState.rows || []).some((row) => rowId(row) === value)) loadExoplanetData();
  else renderExoplanetsExplorer();
}

function setExoplanetHighlightRowIds(ids, options = {}) {
  exoState.highlightRowIds = new Set((ids || []).map((id) => String(id || "").trim()).filter(Boolean));
  renderHighlightedExoplanetList();
  if (!options.quiet) {
    updateExoplanetUrl();
    loadExoplanetData();
  }
}

function syncHighlightOidInput() {
  if (exoEl["exo-highlight-oids"]) {
    exoEl["exo-highlight-oids"].value = [...exoState.highlightOids].sort((a, b) => a - b).join(", ");
  }
}

function renderHighlightedExoplanetList() {
  if (!exoEl["exo-selected-objects"]) return;
  const oids = [...exoState.highlightOids].sort((a, b) => a - b);
  const rowIds = [...exoState.highlightRowIds].sort((a, b) => a.localeCompare(b));
  const entries = [
    ...oids.map((oid) => {
      const rows = (exoState.rows || []).filter((row) => exoplanetHostOid(row) === oid);
      const label = rows.length
        ? `oid${oid}: ${exoplanetHostName(rows[0]) || "host"} (${rows.length.toLocaleString()})`
        : `oid${oid}`;
      return { kind: "oid", value: String(oid), label, title: "Remove highlighted host" };
    }),
    ...rowIds.map((id) => {
      const row = (exoState.rows || []).find((candidate) => rowId(candidate) === id);
      const label = row ? exoplanetSearchResultMainLabel(row) : `exoplanet: ${id}`;
      return { kind: "row", value: id, label, title: "Remove highlighted planet" };
    }),
  ];
  if (!entries.length) {
    exoEl["exo-selected-objects"].textContent = "No objects highlighted";
    return;
  }
  exoEl["exo-selected-objects"].innerHTML = entries.map((entry) => (
    `<button type="button" data-kind="${entry.kind}" data-value="${escapeHtml(entry.value)}" title="${escapeHtml(entry.title)}">${escapeHtml(entry.label)} x</button>`
  )).join("");
  exoEl["exo-selected-objects"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.kind === "oid") exoState.highlightOids.delete(Number(button.dataset.value));
      else exoState.highlightRowIds.delete(button.dataset.value || "");
      syncHighlightOidInput();
      renderHighlightedExoplanetList();
      updateExoplanetUrl();
      renderExoplanetsExplorer();
    });
  });
}

function updateExoplanetUrl() {
  const params = new URLSearchParams(window.location.search);
  params.set("x", exoEl["exo-x-axis"].value);
  params.set("y", exoEl["exo-y-axis"].value);
  params.set("xlog", exoEl["exo-x-log"].checked ? "1" : "0");
  params.set("ylog", exoEl["exo-y-log"].checked ? "1" : "0");
  setParamIf(params, "color_age", exoEl["exo-color-age"].checked ? "1" : "");
  setParamIf(params, "show_confirmed", exoEl["exo-show-confirmed"].checked ? "" : "0");
  setParamIf(params, "show_tess_candidates", exoEl["exo-show-tess"].checked ? "1" : "0");
  setParamIf(params, "errors", exoEl["exo-error-bars"].checked ? "1" : "");
  setParamIf(params, "hover_text", exoEl["exo-hover-text"].checked ? "" : "0");
  params.delete("filter");
  params.delete("q");
  setParamIf(params, "method", exoEl["exo-filter-method"].value.trim());
  params.delete("tess_disposition");
  params.delete("tfopwg_disp");
  setParamIf(params, "spt_range", exoEl["exo-spt-range"].value.trim());
  setParamIf(params, "use_photometric_distances", exoEl["exo-use-photometric-distances"].checked ? "1" : "");
  for (const filter of exoRangeFilters) {
    setParamIf(params, filter.minParam, validNumberText(exoEl[filter.minId]?.value));
    setParamIf(params, filter.maxParam, validNumberText(exoEl[filter.maxId]?.value));
    setParamIf(params, `ignore_null_${filter.key}`, exoEl[filter.nullId]?.checked ? "1" : "");
  }
  if (exoState.highlightOids.size) params.set("highlight_oids", [...exoState.highlightOids].sort((a, b) => a - b).join(","));
  else params.delete("highlight_oids");
  params.delete("highlight_oid");
  params.delete("moca_oids");
  params.delete("moca_oid");
  params.delete("oids");
  params.delete("oid");
  if (exoState.highlightRowIds.size) params.set("highlight_exoplanets", [...exoState.highlightRowIds].sort((a, b) => a.localeCompare(b)).join(","));
  else params.delete("highlight_exoplanets");
  params.delete("highlight_planets");
  params.delete("exoplanet_ids");
  params.delete("planet_ids");
  params.set("max_confirmed", exoEl["exo-max-confirmed"].value || "50000");
  params.set("max_tess_candidates", exoEl["exo-max-tess"].value || "50000");
  window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}

function exoplanetApiParams() {
  const source = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "port", "user", "username", "pwd", "password", "dbase", "db", "database", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  return params;
}

function applyExoplanetDataParams(params) {
  params.set("x", exoEl["exo-x-axis"].value);
  params.set("y", exoEl["exo-y-axis"].value);
  params.set("xlog", exoEl["exo-x-log"].checked ? "1" : "0");
  params.set("ylog", exoEl["exo-y-log"].checked ? "1" : "0");
  params.set("include_confirmed", exoEl["exo-show-confirmed"].checked ? "1" : "0");
  params.set("include_tess_candidates", tessEnabled() ? "1" : "0");
  params.set("max_confirmed", exoEl["exo-max-confirmed"].value || "50000");
  params.set("max_tess_candidates", exoEl["exo-max-tess"].value || "50000");
  if (exoEl["exo-spt-range"].value.trim()) params.set("spt_range", exoEl["exo-spt-range"].value.trim());
  if (exoEl["exo-use-photometric-distances"].checked) params.set("use_photometric_distances", "1");
  for (const filter of exoRangeFilters) {
    const minValue = validNumberText(exoEl[filter.minId]?.value);
    const maxValue = validNumberText(exoEl[filter.maxId]?.value);
    if (minValue) params.set(filter.minParam, minValue);
    if (maxValue) params.set(filter.maxParam, maxValue);
    if (exoEl[filter.nullId]?.checked) params.set(`ignore_null_${filter.key}`, "1");
  }
  if (exoState.highlightOids.size) params.set("highlight_oids", [...exoState.highlightOids].sort((a, b) => a - b).join(","));
  if (exoState.highlightRowIds.size) params.set("highlight_exoplanets", [...exoState.highlightRowIds].sort((a, b) => a.localeCompare(b)).join(","));
  return params;
}

async function clearExoplanetCache() {
  exoEl["exo-clear-cache"].disabled = true;
  exoEl["exo-clear-cache-status"].classList.remove("error");
  exoEl["exo-clear-cache-status"].textContent = "Clearing cache";
  try {
    const payload = await postExoplanetJson("api/exoplanets-explorer/cache/clear");
    exoState.designationIndex = null;
    exoState.designationIndexKey = "";
    exoState.designationIndexPromise = null;
    exoState.designationCacheBust = String(Date.now());
    const cleared = payload.cleared || {};
    const count = Object.values(cleared).reduce((sum, value) => sum + Number(value || 0), 0);
    exoEl["exo-clear-cache-status"].textContent = `Cleared ${count} cached entr${count === 1 ? "y" : "ies"}. Reloading.`;
    await loadExoplanetData({ cacheBust: true });
    exoEl["exo-clear-cache-status"].textContent = `Cleared ${count} cached entr${count === 1 ? "y" : "ies"}.`;
  } catch (error) {
    exoEl["exo-clear-cache-status"].classList.add("error");
    exoEl["exo-clear-cache-status"].textContent = error.message || "Could not clear cache";
  } finally {
    exoEl["exo-clear-cache"].disabled = false;
  }
}

function exportExoplanetRows(format) {
  if (!window.MocaExport) return;
  const selected = selectedRows();
  const rows = selected.length ? selected : displayRows();
  MocaExport.saveTable(format, {
    rows,
    columns: exoExportColumns,
    numericColumns: exoNumericExportColumns,
    filenameBase: selected.length ? "exoplanets_explorer_selected" : "exoplanets_explorer_rows",
    tableName: "exoplanets_explorer",
    resourceName: "Exoplanets Explorer rows",
    extName: "EXOPLANETS",
  });
}

function updateTessAvailability() {
  const unavailable = !exoTessAxisKeys.has(exoEl["exo-x-axis"].value) || !exoTessAxisKeys.has(exoEl["exo-y-axis"].value);
  exoEl["exo-show-tess"].disabled = unavailable;
  const label = exoEl["exo-show-tess"].closest("label");
  if (label) {
    label.classList.toggle("is-disabled", unavailable);
    label.title = unavailable ? "TESS candidates do not have this selected axis pair." : "";
  }
}

function tessEnabled() {
  return Boolean(exoEl["exo-show-tess"]?.checked && !exoEl["exo-show-tess"]?.disabled);
}

function axisSpec(key) {
  return exoState.axes.get(key) || exoDefaultAxes.find((axis) => axis.key === key) || { key, label: key, title: key };
}

function ageColorMarker(rows, options = {}) {
  return {
    color: rows.map(ageColorValue),
    colorscale: exoAgeColorScale,
    cmin: Math.log10(exoAgeColorTicks[0]),
    cmax: Math.log10(exoAgeColorTicks[exoAgeColorTicks.length - 1]),
    showscale: Boolean(options.showColorbar),
    ...(options.showColorbar ? { colorbar: ageColorbarSpec() } : {}),
    size: options.size || 8,
    opacity: options.opacity ?? 0.88,
    symbol: options.symbol || "circle",
    line: { color: "rgba(255,255,255,0.82)", width: 0.65 },
  };
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

function tessAgeColorMarker(rows, options = {}) {
  return {
    color: rows.map(ageColorValue),
    colorscale: exoAgeColorScale,
    cmin: Math.log10(exoAgeColorTicks[0]),
    cmax: Math.log10(exoAgeColorTicks[exoAgeColorTicks.length - 1]),
    showscale: Boolean(options.showColorbar),
    ...(options.showColorbar ? { colorbar: ageColorbarSpec() } : {}),
    size: options.size || 8,
    opacity: options.opacity ?? 0.76,
    symbol: openMarkerSymbol(options.symbol || exoMethodSymbols.get("Transit") || "circle"),
    line: { width: options.lineWidth || 1.35 },
  };
}

function tessUnknownAgeMarker(symbol) {
  return {
    color: "#9CA3AF",
    size: 8,
    opacity: 0.34,
    symbol: openMarkerSymbol(symbol || exoMethodSymbols.get("Transit") || "circle"),
    line: { color: "#9CA3AF", width: 1.25 },
  };
}

function ageColorValue(row) {
  const age = usableAgeMyr(row.host_age_myr);
  return Math.log10(clampNumber(age || exoAgeColorTicks[0], exoAgeColorTicks[0], exoAgeColorTicks[exoAgeColorTicks.length - 1]));
}

function ageColorbarSpec() {
  return {
    title: { text: "Age (Myr)", side: "right" },
    tickmode: "array",
    tickvals: exoAgeColorTicks.map((value) => Math.log10(value)),
    ticktext: exoAgeColorTicks.map((value) => value >= 1000 ? `${Math.round(value / 1000)}k` : String(value)),
    thickness: 18,
    len: 0.86,
    x: 1.025,
    y: 0.5,
    outlinewidth: 1.5,
    outlinecolor: "#111111",
    tickfont: { size: 13, color: "#111111" },
  };
}

function errorSpec(rows, spec, color) {
  const posKey = spec.uncPos;
  const negKey = spec.uncNeg;
  const symKey = spec.unc;
  const style = color ? { ...exoErrorBarStyle, color } : exoErrorBarStyle;
  const hasAsymmetric = posKey && negKey && rows.some((row) => finiteNumber(row[posKey]) !== null || finiteNumber(row[negKey]) !== null);
  if (hasAsymmetric) {
    return {
      type: "data",
      array: rows.map((row) => finiteNumber(row[posKey]) ?? finiteNumber(row[symKey]) ?? 0),
      arrayminus: rows.map((row) => finiteNumber(row[negKey]) ?? finiteNumber(row[symKey]) ?? 0),
      symmetric: false,
      visible: true,
      ...style,
    };
  }
  if (symKey && rows.some((row) => finiteNumber(row[symKey]) !== null)) {
    return { type: "data", array: rows.map((row) => finiteNumber(row[symKey]) || 0), visible: true, ...style };
  }
  return null;
}

function errorBarColor(marker = {}) {
  if (typeof marker.color === "string") return colorWithAlpha(marker.color, 0.35);
  if (typeof marker.line?.color === "string") return colorWithAlpha(marker.line.color, 0.35);
  return "rgba(80, 80, 80, 0.32)";
}

function hoverText(row, xKey, yKey) {
  return [
    `<b>${escapeHtml(row.planet_name || row.designation_child || "exoplanet")}</b>`,
    `${escapeHtml(axisSpec(xKey).label || xKey)}: ${escapeHtml(formatAxisValue(row, xKey))}`,
    `${escapeHtml(axisSpec(yKey).label || yKey)}: ${escapeHtml(formatAxisValue(row, yKey))}`,
    `Host: ${escapeHtml(row.host_name || row.designation_parent || "")}`,
    isTessRow(row) ? `Disposition: ${escapeHtml(row.tfopwg_disp || "")}` : `Discovery: ${escapeHtml(row.discoverymethod || "Unknown")}`,
    `Host SpT: ${escapeHtml(row.host_spt || "")}`,
    `Distance: ${escapeHtml(formatCell(row.host_distance_pc))} pc`,
    `Age: ${escapeHtml(formatAgeMyrText(row.host_age_myr))}`,
  ].join("<br>");
}

function formatAxisValue(row, key) {
  if (key === "host_sptn") return row.host_spt || formatCell(row[key]);
  if (key === "host_age_myr") return formatAgeMyrCell(row[key]);
  return formatCell(row[key]);
}

function tableHeader(column) {
  const headers = {
    dataset: "Dataset",
    planet_name: "Planet",
    host_name: "Host",
    host_report_url: "Host Report",
    discoverymethod: "Discovery",
    tfopwg_disp: "TESS Disp.",
    host_age_myr: "Age (Myr)",
    host_age_source: "Age Source",
    orbital_period_days: "Period (d)",
    planet_radius_rjup: "Radius (R_Jup)",
    planet_mass_mjup: "Mass (M_Jup)",
    sep_au: "Sep. (AU)",
    sep_mas: "Sep. (mas)",
    host_distance_pc: "Distance (pc)",
    host_spt: "Host SpT",
    host_teff_k: "Host Teff",
    host_mass_msun: "Host Mass",
    toi: "TOI",
    tid: "TIC",
    nasa_id: "NASA id",
  };
  return headers[column] || axisSpec(column).label || column;
}

function rowId(row) {
  return String(row.planet_id || row.exoplanet_id || `${row.row_kind}:${row.nasa_id || row.tess_candidate_id || row.rowid || ""}`);
}

function rowIsHighlighted(row) {
  const oid = exoplanetHostOid(row);
  return exoState.highlightRowIds.has(rowId(row)) || (oid !== null && exoState.highlightOids.has(oid));
}

function exoplanetHostOid(row) {
  return finiteInteger(row?.moca_oid ?? row?.moca_oid_parent);
}

function exoplanetOptionRowId(row) {
  const value = row?.value || row?.planet_id || row?.exoplanet_id || rowId(row);
  return String(value || "").trim();
}

function exoplanetResultKind(row) {
  const kind = String(row?.result_kind || row?.row_kind || "").trim();
  if (kind === "host") return "host";
  if (kind === "tess_candidate") return "tess_candidate";
  return "confirmed_planet";
}

function exoplanetHostName(row) {
  return row?.host_name || row?.designation_parent || row?.hostname || row?.object_designation || "";
}

function exoplanetPlanetName(row) {
  return row?.planet_name || row?.designation_child || row?.pl_name || row?.label || "";
}

function idsFromEventPoints(points) {
  return [...new Set((points || []).map(pointRowId).filter(Boolean))];
}

function pointRowId(point) {
  const direct = normalizePointRowId(point?.customdata);
  if (direct) return direct;
  const indices = [
    point?.pointIndex,
    point?.pointNumber,
    Array.isArray(point?.pointNumbers) ? point.pointNumbers[0] : null,
  ].map((value) => Number(value)).filter(Number.isInteger);
  const customdataSources = [
    point?.data?.customdata,
    point?.fullData?.customdata,
    exoEl["exo-plot"]?.data?.[Number(point?.curveNumber)]?.customdata,
  ].filter(Array.isArray);
  for (const index of indices) {
    for (const source of customdataSources) {
      const value = normalizePointRowId(source[index]);
      if (value) return value;
    }
  }
  return null;
}

function normalizePointRowId(value) {
  const raw = Array.isArray(value) ? value[0] : value;
  const text = String(raw ?? "").trim();
  return text || null;
}

function isConfirmedRow(row) {
  return String(row.row_kind || "") === "confirmed_planet";
}

function isTessRow(row) {
  return String(row.row_kind || "") === "tess_candidate";
}

function rowHasUsableAge(row) {
  return usableAgeMyr(row.host_age_myr) !== null;
}

function usableAgeMyr(value) {
  const age = finiteNumber(value);
  return age !== null && age > 0 ? age : null;
}

function rowText(row) {
  return [
    row.planet_id, row.planet_name, row.host_name, row.moca_oid_parent, row.nasa_id,
    row.tess_candidate_id, row.toi, row.tid, row.discoverymethod, row.tfopwg_disp,
  ].map(normalizeSearchText).join(" ");
}

function countLabel(label, rows) {
  return `${label} (${rows.length.toLocaleString()})`;
}

function uniqueSorted(values) {
  return [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function methodsByDecreasingClassSize(rows) {
  const counts = new Map();
  for (const row of rows || []) {
    const method = row.discoverymethod || "Unknown";
    counts.set(method, (counts.get(method) || 0) + 1);
  }
  return [...counts.keys()].sort((a, b) => {
    const countDiff = (counts.get(b) || 0) - (counts.get(a) || 0);
    return countDiff || a.localeCompare(b);
  });
}

function transitColor() {
  return methodColor("Transit", 0);
}

function methodColor(method, fallbackIndex = 0) {
  return exoMethodColorOverrides.get(method) || exoMethodPalette[fallbackIndex % exoMethodPalette.length];
}

function openMarkerSymbol(symbol) {
  const text = String(symbol || "circle");
  return text.includes("open") ? text : `${text}-open`;
}

function setExoplanetLoading(isLoading) {
  exoEl["exo-plot-loader"].classList.toggle("is-visible", Boolean(isLoading));
}

function setExoplanetStatus(text, kind) {
  exoEl["exo-status"].textContent = text || "";
  exoEl["exo-status"].className = `status ${kind || ""}`.trim();
}

function setExoplanetExportDisabled(disabled) {
  for (const id of ["exo-export-csv", "exo-export-tsv"]) exoEl[id].disabled = disabled;
}

async function fetchExoplanetJson(path) {
  const response = await fetch(exoAppUrl(path), { headers: { Accept: "application/json" } });
  return response.json();
}

async function postExoplanetJson(path, body = {}) {
  const response = await fetch(exoAppUrl(path), {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function plotConfigSafe(filename) {
  if (typeof plotConfig === "function") return plotConfig(filename);
  return { responsive: true, displaylogo: false };
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function validNumberText(value) {
  const number = finiteNumber(value);
  return number === null ? "" : String(number);
}

function finiteInteger(value) {
  const number = finiteNumber(value);
  return number === null ? null : Math.trunc(number);
}

function parseIntegerList(raw) {
  return String(raw || "")
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => /^[0-9]+$/.test(item))
    .map((item) => Number(item))
    .filter(Number.isFinite);
}

function parseTokenList(raw) {
  return String(raw || "")
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function truthyParam(value, fallback = false) {
  if (value === null || value === undefined || value === "") return Boolean(fallback);
  const text = String(value).trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(text)) return true;
  if (["0", "false", "no", "off"].includes(text)) return false;
  return Boolean(fallback);
}

function setParamIf(params, key, value) {
  const text = String(value || "").trim();
  if (text) params.set(key, text);
  else params.delete(key);
}

function clampNumber(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeSearchText(value) {
  return String(value || "").trim().toLowerCase();
}

function formatCell(value) {
  const number = finiteNumber(value);
  if (number === null) return value === null || value === undefined ? "" : String(value);
  const abs = Math.abs(number);
  if (abs > 0 && (abs < 0.001 || abs >= 100000)) return number.toExponential(3);
  if (abs >= 1000) return number.toLocaleString(undefined, { maximumFractionDigits: 1 });
  if (abs >= 10) return number.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (abs >= 1) return number.toLocaleString(undefined, { maximumFractionDigits: 3 });
  return number.toLocaleString(undefined, { maximumSignificantDigits: 4 });
}

function formatAgeMyrCell(value) {
  const age = usableAgeMyr(value);
  if (age === null) return "";
  if (age >= 1000) return `${formatCell(age / 1000)} Gyr`;
  return `${formatCell(age)} Myr`;
}

function formatAgeMyrText(value) {
  return formatAgeMyrCell(value) || "unknown";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function colorWithAlpha(color, alpha) {
  const rgb = colorToRgb(color);
  return rgb ? `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})` : color;
}

function colorToRgb(color) {
  const text = String(color || "").trim();
  const hexMatch = text.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (!hexMatch) return null;
  const hex = hexMatch[1].length === 3
    ? hexMatch[1].split("").map((char) => `${char}${char}`).join("")
    : hexMatch[1];
  return {
    r: parseInt(hex.slice(0, 2), 16),
    g: parseInt(hex.slice(2, 4), 16),
    b: parseInt(hex.slice(4, 6), 16),
  };
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
