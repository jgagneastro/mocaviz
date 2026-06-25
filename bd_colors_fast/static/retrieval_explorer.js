const rexState = {
  options: [],
  payload: null,
  selectedTab: "abundances",
  searchTimer: null,
  loadToken: 0,
  siblingProfileLoadToken: 0,
  siblingProfileCache: new Map(),
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
const condensationCurveColors = {
  FE_METAL_VISSCHER2010_SOLAR: "#ff6b00",
  FE_METAL: "#ff6b00",
  FE: "#ff6b00",
  FORSTERITE_MG2SIO4_VISSCHER2010_SOLAR: "#00a651",
  FORSTERITE_MG2SIO4: "#00a651",
  MG2SIO4: "#00a651",
  ENSTATITE_MGSIO3_VISSCHER2010_SOLAR: "#9b5de5",
  ENSTATITE_MGSIO3: "#9b5de5",
  MGSIO3: "#9b5de5",
  H2O_ICE_LIQUID_MURPHYKOOP2005_XH2O5E4: "#00a6d6",
  H2O_ICE_LIQUID: "#00a6d6",
  H2O: "#00a6d6",
  SIO4_GROUP: "#ffb000",
  SIO4: "#ffb000",
};
const condensationCurveFallbackColors = ["#00a6d6", "#ff6b00", "#00a651", "#9b5de5", "#ffb000", "#ff4db8"];
const condensationCurveLabelFractions = [0.50, 0.64, 0.36, 0.78, 0.22, 0.57, 0.43, 0.71, 0.29, 0.85, 0.15];
const selectedTpProfileColor = "#c62828";
const tpProfileComparisonColors = ["#1f77b4", "#2ca02c", "#ff7f0e", "#9467bd", "#17becf", "#8c564b", "#e377c2", "#bcbd22"];
const maxSiblingTpProfiles = 12;
const tpProfileLineWidthSelected = 4.2;
const tpProfileLineWidthComparison = 3.9;
const tpProfileMarkerSize = 3.25;
const tpProfileMarkerDensityBinK = 200;
const tpProfileMarkerReferenceWindowK = [400, 600];
const cloudPressureLineColor = "#6f6f6f";
const cloudPressureFillColor = "rgba(115,115,115,.14)";
const cloudPressureLabelColor = "#565656";
const abundanceComparisonYOffset = -0.15;
const abundanceComparisonMarkerEdge = "rgba(255,255,255,0.88)";
const retrievalUrlCheckboxControls = [
  { id: "rex-show-envelope", param: "show_tp_envelope", aliases: ["show_envelope", "tp_envelope"], defaultChecked: true },
  { id: "rex-log-temperature-axis", param: "log_temperature_axis", aliases: ["log_temperature", "log_temp"], defaultChecked: false },
  { id: "rex-log-pressure-axis", param: "log_pressure_axis", aliases: ["log_pressure", "log_p"], defaultChecked: true },
  { id: "rex-show-sibling-tp-profiles", param: "show_other_tp_profiles", aliases: ["show_sibling_tp_profiles", "other_tp_profiles"], defaultChecked: false },
  { id: "rex-display-condensation-curves", param: "display_condensation_curves", aliases: ["show_condensation_curves", "condensation_curves"], defaultChecked: true },
  { id: "rex-display-noncrossing-condensation-curves", param: "display_noncrossing_condensation_curves", aliases: ["show_all_condensation_curves", "noncrossing_condensation_curves"], defaultChecked: false },
  { id: "rex-show-clouds", param: "show_cloud_pressure_markers", aliases: ["show_clouds", "cloud_markers"], defaultChecked: true },
];
const retrievalUrlSelectControls = [
  { id: "rex-abundance-mode", param: "abundance_mode", aliases: ["abundances"], defaultValue: "object" },
  { id: "rex-corner-size", param: "corner_size", aliases: ["corner_parameters"], defaultValue: "4" },
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
  updateRetrievalTabAvailability();
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
    "rex-log-temperature-axis",
    "rex-log-pressure-axis",
    "rex-show-sibling-tp-profiles",
    "rex-display-condensation-curves",
    "rex-display-noncrossing-condensation-curves",
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
    "rex-tab-fundamentals",
    "rex-tab-parameters",
    "rex-tab-spectrum",
    "rex-tab-corner",
    "rex-abundance-plot",
    "rex-fundamental-cards",
    "rex-fundamental-table",
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
  const includeIgnored = firstUrlParam(params, ["include_ignored", "show_ignored"]);
  if (includeIgnored !== null) rexEl["rex-include-ignored"].checked = asBool(includeIgnored);
  for (const control of retrievalUrlCheckboxControls) {
    const value = firstUrlParam(params, [control.param, ...(control.aliases || [])]);
    if (value !== null && rexEl[control.id]) rexEl[control.id].checked = asBool(value);
  }
  for (const control of retrievalUrlSelectControls) {
    const value = firstUrlParam(params, [control.param, ...(control.aliases || [])]);
    if (value !== null) setSelectValueIfPresent(rexEl[control.id], value);
  }
}

function bindRetrievalControls() {
  rexEl["rex-find"].addEventListener("click", () => searchRetrievals({ loadFirst: true }));
  rexEl["rex-load"].addEventListener("click", () => loadSelectedRetrieval());
  rexEl["rex-atmosphere"].addEventListener("change", () => loadSelectedRetrieval());
  rexEl["rex-include-ignored"].addEventListener("change", () => {
    updateRetrievalUrl();
    searchRetrievals({ loadFirst: true });
  });
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
  for (const id of ["rex-show-envelope", "rex-log-temperature-axis", "rex-log-pressure-axis", "rex-display-condensation-curves", "rex-display-noncrossing-condensation-curves", "rex-show-clouds", "rex-abundance-mode", "rex-corner-size"]) {
    rexEl[id]?.addEventListener("change", () => {
      renderRetrievalPayload();
      updateRetrievalUrl();
    });
  }
  rexEl["rex-show-sibling-tp-profiles"]?.addEventListener("change", async () => {
    updateRetrievalUrl();
    if (rexEl["rex-show-sibling-tp-profiles"].checked) {
      setRetrievalLoader(true);
      try {
        await ensureSiblingTpProfilesLoaded();
      } finally {
        setRetrievalLoader(false);
      }
    }
    renderRetrievalPayload();
    updateRetrievalUrl();
  });
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
      if (options.loadFirst) {
        rexState.payload = null;
        renderRetrievalPayload();
        setRetrievalLoader(false);
      }
      setRetrievalStatus(`${rexState.options.length} retrievals`, "");
    }
  } catch (error) {
    setRetrievalStatus(error.message || "Could not load retrievals", "error");
    if (options.loadFirst) {
      rexState.payload = null;
      renderRetrievalPayload();
      setRetrievalLoader(false);
    }
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
  rexState.siblingProfileLoadToken += 1;
  setRetrievalStatus("Loading retrieval", "loading");
  setRetrievalLoader(true);
  const params = connectionParams();
  if (rexEl["rex-include-ignored"].checked) params.set("include_ignored", "1");
  try {
    const payload = await fetchJsonUrl(rexAppUrl(`api/retrieval-explorer/atmosphere/${atmosphereId}?${params.toString()}`));
    if (token !== rexState.loadToken) return;
    if (!payload.ok) throw new Error(payload.error || "Could not load retrieval");
    await enrichRetrievalPayloadWithObjectFundamentals(payload, token);
    if (token !== rexState.loadToken) return;
    payload.siblingTpProfiles = [];
    rexState.payload = payload;
    updateRetrievalUrl(atmosphereId);
    if (rexEl["rex-show-sibling-tp-profiles"]?.checked) {
      await ensureSiblingTpProfilesLoaded();
      if (token !== rexState.loadToken) return;
    }
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

async function enrichRetrievalPayloadWithObjectFundamentals(payload, token) {
  const atmosphere = payload?.atmosphere || {};
  const oid = parseInteger(atmosphere.moca_oid);
  const pid = String(atmosphere.moca_pid || "").trim();
  if (!payload || !oid || !pid) return payload;
  const params = connectionParams();
  if (rexEl["rex-include-ignored"].checked) params.set("include_ignored", "1");
  try {
    const url = rexAppUrl(`api/retrieval-explorer/object-fundamentals/${oid}/${encodeURIComponent(pid)}?${params.toString()}`);
    const fallback = await fetchJsonUrl(url);
    if (token !== rexState.loadToken) return payload;
    if (!fallback.ok) throw new Error(fallback.error || "Could not load object-level fundamentals");
    mergeObjectFundamentals(payload, fallback.fundamentalParameters || []);
    payload.objectFundamentalParameters = fallback.fundamentalParameters || [];
    payload.meta = payload.meta || {};
    payload.meta.object_fundamental_count = fallback.meta?.row_count ?? (fallback.fundamentalParameters || []).length;
  } catch (error) {
    payload.objectFundamentalParameters = [];
    payload.meta = payload.meta || {};
    payload.meta.object_fundamental_error = error.message || "Could not load object-level fundamentals";
  }
  return payload;
}

function mergeObjectFundamentals(payload, fallbackRows) {
  if (!Array.isArray(fallbackRows) || !fallbackRows.length) return;
  const scalarRows = Array.isArray(payload.scalarParameters) ? payload.scalarParameters : [];
  const existingKeys = new Set(scalarRows.map(fundamentalParameterMergeKey).filter(Boolean));
  const additions = [];
  fallbackRows.forEach((row) => {
    const key = fundamentalParameterMergeKey(row);
    if (!key || existingKeys.has(key)) return;
    additions.push({
      ...row,
      parameter_kind: row.parameter_kind || "derived_atmosphere",
      fallback_source: row.fallback_source || "object_level_same_oid_pid",
    });
    existingKeys.add(key);
  });
  if (!additions.length) return;
  payload.scalarParameters = [...scalarRows, ...additions];
  payload.meta = payload.meta || {};
  payload.meta.scalar_parameter_count = payload.scalarParameters.length;
  payload.meta.object_fundamental_merged_count = additions.length;
}

function fundamentalParameterMergeKey(row) {
  const text = `${row?.moca_atparid || ""} ${row?.parameter_name || ""}`.toUpperCase();
  if (text.includes("TEFF") || text.includes("EFFECTIVE")) return "TEFF_K";
  if (text.includes("MASS")) return "MASS_MJUP";
  if (text.includes("RADIUS")) return "RADIUS_RJUP";
  if (text.includes("LOGG") || text.includes("GRAVITY")) return "LOGG_CGS";
  return String(row?.moca_atparid || "").toUpperCase() || null;
}

function renderRetrievalPayload() {
  renderRetrievalSummary();
  updateEnvelopeControl();
  updateSiblingTpProfileControl();
  updateCondensationCurveControl();
  updateCloudMarkerControl();
  renderTpPlot();
  renderContributionPlot();
  renderAbundancePlot();
  renderFundamentalParameters();
  renderParameterTables();
  renderSpectrumPlot();
  renderCornerPlot();
  updateRetrievalTabAvailability();
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
  const profileItems = displayedTpProfileItems(payload);
  const displayedProfileSets = profileItems.map((item) => item.profiles);
  const displayedProfiles = displayedProfileSets.flat();
  const condensationCurveCount = condensationCurvePlotItems(
    payload?.condensationCurves || [],
    displayedProfiles,
    {
      includeNonCrossing: Boolean(rexEl["rex-display-noncrossing-condensation-curves"]?.checked),
      profileSets: displayedProfileSets,
    },
  ).length;
  rexEl["rex-hint"].textContent = `${payload.meta?.profile_count || 0} T/P points, ${payload.meta?.cloud_parameter_count || 0} cloud parameters, ${condensationCurveCount || 0} condensation curves, ${payload.meta?.abundance_count || 0} abundance rows.`;
  rexEl["rex-selection-card"].innerHTML = [
    ["Atmosphere ID", a.id],
    ["Object", objectCardHtml(a), true],
    ["Publication", publicationCardHtml(a), true],
    ["Code", retrievalCodeCardHtml(a), true],
    ["Model", a.retrieval_model],
    ["Chemistry", a.chemistry_assumption],
    ["Clouds", a.cloud_assumption],
    ["Input specid", a.moca_specid],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "").map(([label, value, isHtml]) => (
    `<div><span>${escapeHtml(label)}</span><strong>${isHtml ? value : escapeHtml(value)}</strong></div>`
  )).join("");
}

function objectCardHtml(atmosphere) {
  const label = atmosphere?.designation || atmosphere?.object_designation || atmosphere?.moca_oid || "";
  const oid = parseInteger(atmosphere?.moca_oid);
  if (!label) return "";
  if (!oid) return escapeHtml(label);
  const url = `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(oid)}%29&search-type=star`;
  return `<a class="retrieval-card-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
}

function publicationCardHtml(atmosphere) {
  const name = atmosphere?.publication_name || atmosphere?.publication_title;
  const bibcode = atmosphere?.publication_bibcode || atmosphere?.bibcode || "";
  const label = name || bibcode || atmosphere?.moca_pid || "";
  if (!label) return "";
  const adsUrl = bibcode ? `https://ui.adsabs.harvard.edu/abs/${encodeURIComponent(bibcode)}/abstract` : "";
  if (!adsUrl) return escapeHtml(label);
  const bibcodeHtml = bibcode && bibcode !== label
    ? `<small class="retrieval-publication-bibcode">${escapeHtml(bibcode)}</small>`
    : "";
  return `<a class="retrieval-card-link retrieval-publication-link" href="${escapeHtml(adsUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>${bibcodeHtml}`;
}

function retrievalCodeCardHtml(atmosphere) {
  const label = atmosphere?.retrieval_code || "";
  if (!label) return "";
  const bibcode = atmosphere?.publication_bibcode || atmosphere?.bibcode || "";
  if (!bibcode) return escapeHtml(label);
  const adsUrl = `https://ui.adsabs.harvard.edu/abs/${encodeURIComponent(bibcode)}/abstract`;
  return `<a class="retrieval-card-link" href="${escapeHtml(adsUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
}

function updateCloudMarkerControl() {
  const checkbox = rexEl["rex-show-clouds"];
  const label = checkbox?.closest(".checkline");
  if (!checkbox) return;
  const markerRows = cloudPressureRows(rexState.payload?.cloudParameters || []);
  updateCheckboxAvailability(checkbox, markerRows.length > 0, {
    unavailableTitle: "No cloud pressure markers are available for this retrieval.",
    availableTitle: `${markerRows.length} cloud pressure marker${markerRows.length === 1 ? "" : "s"} available.`,
  });
}

function updateEnvelopeControl() {
  const checkbox = rexEl["rex-show-envelope"];
  if (!checkbox) return;
  const profiles = retrievalTpProfiles(rexState.payload);
  const hasEnvelope = profiles.some((row) => envelopeLow(row) !== null) && profiles.some((row) => envelopeHigh(row) !== null);
  updateCheckboxAvailability(checkbox, hasEnvelope, {
    unavailableTitle: "No T/P uncertainty envelope is stored for this retrieval.",
    availableTitle: "A T/P uncertainty envelope is available for this retrieval.",
  });
}

function updateSiblingTpProfileControl() {
  const checkbox = rexEl["rex-show-sibling-tp-profiles"];
  if (!checkbox) return;
  const candidates = sameObjectSiblingCandidates(rexState.payload);
  const profileCount = rexState.payload?.siblingTpProfiles?.length || 0;
  updateCheckboxAvailability(checkbox, candidates.length > 0, {
    unavailableTitle: "No other same-object retrieval T/P profiles are available.",
    availableTitle: profileCount
      ? `${profileCount} comparison T/P profile${profileCount === 1 ? "" : "s"} loaded.`
      : `${candidates.length} other same-object retrieval row${candidates.length === 1 ? "" : "s"} available.`,
  });
}

function updateCondensationCurveControl() {
  const checkbox = rexEl["rex-display-condensation-curves"];
  if (!checkbox) return;
  const profileItems = displayedTpProfileItems(rexState.payload);
  const displayedProfileSets = profileItems.map((item) => item.profiles);
  const displayedProfiles = displayedProfileSets.flat();
  const totalCurveCount = condensationCurvePlotItems(rexState.payload?.condensationCurves || [], displayedProfiles, {
    includeNonCrossing: true,
    profileSets: displayedProfileSets,
  }).length;
  const crossingCurveCount = condensationCurvePlotItems(rexState.payload?.condensationCurves || [], displayedProfiles, {
    profileSets: displayedProfileSets,
  }).length;
  updateCheckboxAvailability(checkbox, totalCurveCount > 0, {
    unavailableTitle: "No condensation curves are drawable over this T/P pressure range.",
    availableTitle: `${crossingCurveCount} of ${totalCurveCount} condensation curve${totalCurveCount === 1 ? "" : "s"} cross the displayed T/P profile${profileItems.length === 1 ? "" : "s"}.`,
  });
  updateNonCrossingCondensationCurveControl(totalCurveCount, crossingCurveCount);
}

function updateNonCrossingCondensationCurveControl(totalCurveCount = null, crossingCurveCount = null) {
  const checkbox = rexEl["rex-display-noncrossing-condensation-curves"];
  const mainCheckbox = rexEl["rex-display-condensation-curves"];
  if (!checkbox || !mainCheckbox) return;
  const profileItems = displayedTpProfileItems(rexState.payload);
  const displayedProfileSets = profileItems.map((item) => item.profiles);
  const displayedProfiles = displayedProfileSets.flat();
  const total = totalCurveCount ?? condensationCurvePlotItems(rexState.payload?.condensationCurves || [], displayedProfiles, {
    includeNonCrossing: true,
    profileSets: displayedProfileSets,
  }).length;
  const crossing = crossingCurveCount ?? condensationCurvePlotItems(rexState.payload?.condensationCurves || [], displayedProfiles, {
    profileSets: displayedProfileSets,
  }).length;
  const nonCrossing = Math.max(0, total - crossing);
  updateCheckboxAvailability(checkbox, mainCheckbox.checked && total > 0, {
    unavailableTitle: mainCheckbox.checked
      ? "No condensation curves are drawable over this T/P pressure range."
      : "Enable Display condensation curves first.",
    availableTitle: `${nonCrossing} condensation curve${nonCrossing === 1 ? "" : "s"} do not cross the displayed T/P profile${profileItems.length === 1 ? "" : "s"}.`,
  });
}

function updateCheckboxAvailability(checkbox, available, options = {}) {
  const label = checkbox?.closest(".checkline");
  const disabled = !available;
  if (disabled) {
    if (!checkbox.disabled) checkbox.dataset.previousChecked = checkbox.checked ? "1" : "0";
    checkbox.checked = false;
    checkbox.disabled = true;
    label?.classList.add("is-disabled");
    if (label) label.title = options.unavailableTitle || "";
    return;
  }
  const wasDisabled = checkbox.disabled;
  checkbox.disabled = false;
  label?.classList.remove("is-disabled");
  if (label) label.title = options.availableTitle || "";
  if (wasDisabled && checkbox.dataset.previousChecked !== "0") checkbox.checked = true;
  delete checkbox.dataset.previousChecked;
}

function displayedTpProfileItems(payload = rexState.payload) {
  const siblingItems = rexEl["rex-show-sibling-tp-profiles"]?.checked
    ? (payload?.siblingTpProfiles || []).map((item, index) => {
      const atmosphere = item.atmosphere || item.candidate || {};
      const label = retrievalRunLabel(atmosphere, `Atmosphere ${item.id || index + 1}`);
      return {
        key: `sibling-${item.id || index}`,
        id: item.id,
        profiles: item.profiles || [],
        color: tpProfileComparisonColors[index % tpProfileComparisonColors.length],
        legendLabel: label,
        hoverLabel: label,
        legendRank: 20 + index,
        isSelected: false,
      };
    })
    : [];
  const selectedProfiles = retrievalTpProfiles(payload);
  const selectedAtmosphere = payload?.atmosphere || {};
  const selectedLabel = retrievalRunLabel(selectedAtmosphere, "selected retrieval");
  const selectedItem = selectedProfiles.length ? {
    key: `selected-${retrievalAtmosphereId(selectedAtmosphere) || "retrieval"}`,
    id: retrievalAtmosphereId(selectedAtmosphere),
    profiles: selectedProfiles,
    color: selectedTpProfileColor,
    legendLabel: `Selected: ${selectedLabel}`,
    hoverLabel: `Selected retrieval: ${selectedLabel}`,
    legendRank: 0,
    isSelected: true,
  } : null;
  return [...siblingItems, selectedItem].filter((item) => item?.profiles?.length);
}

function sameObjectSiblingCandidates(payload = rexState.payload) {
  const selectedId = retrievalAtmosphereId(payload?.atmosphere || payload?.selection || {});
  const selectedOid = parseInteger(payload?.atmosphere?.moca_oid);
  return (payload?.siblingAtmospheres || []).filter((row) => {
    const id = retrievalAtmosphereId(row);
    if (!id || id === selectedId) return false;
    const oid = parseInteger(row?.moca_oid);
    return !selectedOid || !oid || oid === selectedOid;
  });
}

async function ensureSiblingTpProfilesLoaded() {
  const payload = rexState.payload;
  if (!payload?.atmosphere?.id) return [];
  const candidates = sameObjectSiblingCandidates(payload).slice(0, maxSiblingTpProfiles);
  if (!candidates.length) {
    payload.siblingTpProfiles = [];
    updateSiblingTpProfileControl();
    return [];
  }
  const token = ++rexState.siblingProfileLoadToken;
  const loaded = await Promise.all(candidates.map((candidate) => loadSiblingTpProfile(candidate)));
  if (token !== rexState.siblingProfileLoadToken || payload !== rexState.payload) return [];
  payload.siblingTpProfiles = loaded.filter(Boolean);
  updateSiblingTpProfileControl();
  return payload.siblingTpProfiles;
}

async function loadSiblingTpProfile(candidate) {
  const id = retrievalAtmosphereId(candidate);
  if (!id) return null;
  const cacheKey = siblingTpProfileCacheKey(id);
  let payload = rexState.siblingProfileCache.get(cacheKey);
  if (!payload) {
    const params = connectionParams();
    if (rexEl["rex-include-ignored"]?.checked) params.set("include_ignored", "1");
    payload = await fetchJsonUrl(rexAppUrl(`api/retrieval-explorer/atmosphere/${id}?${params.toString()}`)).catch(() => null);
    if (!payload?.ok) return null;
    rexState.siblingProfileCache.set(cacheKey, payload);
  }
  const profiles = retrievalTpProfiles(payload);
  if (!profiles.length) return null;
  return {
    id,
    candidate,
    atmosphere: { ...candidate, ...(payload.atmosphere || {}) },
    profiles,
  };
}

function siblingTpProfileCacheKey(id) {
  const params = connectionParams();
  if (rexEl["rex-include-ignored"]?.checked) params.set("include_ignored", "1");
  return `${id}|${params.toString()}`;
}

function retrievalAtmosphereId(row) {
  return parseInteger(row?.atmosphere_structure_id ?? row?.id ?? row?.value);
}

function retrievalRunLabel(row, fallback = "retrieval") {
  const id = retrievalAtmosphereId(row);
  const publication = row?.publication_name
    || row?.publication_title
    || row?.moca_pid
    || row?.publication_bibcode
    || row?.bibcode;
  const model = compactJoin([row?.retrieval_code, row?.retrieval_model, row?.time_bin_label], " / ");
  return compactJoin([publication, model, id ? `id ${id}` : null], " | ") || fallback;
}

function renderTpPlot() {
  const profiles = retrievalTpProfiles(rexState.payload);
  if (!profiles.length) {
    Plotly.react(rexEl["rex-tp-plot"], [], emptyLayout("No T/P profile rows"), plotConfig("retrieval_tp_empty"));
    return;
  }
  const profileItems = displayedTpProfileItems(rexState.payload);
  const displayedProfileSets = profileItems.map((item) => item.profiles).filter((rows) => rows.length >= 2);
  const displayedProfiles = displayedProfileSets.flat();
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
  const showCondensationCurves = Boolean(rexEl["rex-display-condensation-curves"]?.checked);
  const includeNonCrossingCondensationCurves = Boolean(rexEl["rex-display-noncrossing-condensation-curves"]?.checked);
  const condensationItems = showCondensationCurves
    ? condensationCurvePlotItems(rexState.payload?.condensationCurves || [], displayedProfiles, {
      includeNonCrossing: includeNonCrossingCondensationCurves,
      profileSets: displayedProfileSets,
    })
    : [];
  const condensationTraces = condensationCurveTraces(condensationItems);
  traces.push(...condensationTraces);
  const showProfileLegend = profileItems.length > 1;
  traces.push(...profileItems.flatMap((item) => tpProfileTraces(item, showProfileLegend)));
  const shapes = rexEl["rex-show-clouds"].checked ? cloudPressureShapes(rexState.payload?.cloudParameters || [], profiles) : [];
  const useLogTemperatureAxis = Boolean(rexEl["rex-log-temperature-axis"]?.checked);
  const useLogPressureAxis = Boolean(rexEl["rex-log-pressure-axis"]?.checked);
  const annotations = [
    ...condensationCurveAnnotations(condensationItems, { useLogTemperatureAxis, useLogPressureAxis }),
    ...(rexEl["rex-show-clouds"].checked ? cloudPressureAnnotations(rexState.payload?.cloudParameters || [], { useLogPressureAxis }) : []),
  ];
  const xaxis = temperatureAxisLayout(traces, useLogTemperatureAxis);
  const yaxis = pressureAxisLayout(traces, useLogPressureAxis);
  const layout = {
    margin: { l: 74, r: 72, t: 22, b: showProfileLegend ? 82 : 54 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    xaxis,
    yaxis,
    showlegend: showProfileLegend,
    legend: { orientation: "h", x: 0, xanchor: "left", y: -0.18, font: { size: 10 }, itemsizing: "constant" },
    shapes,
    annotations,
  };
  Plotly.react(rexEl["rex-tp-plot"], traces, layout, plotConfig("retrieval_tp"));
}

function temperatureAxisLayout(traces, useLogTemperatureAxis) {
  const values = traces.flatMap((trace) => Array.isArray(trace.x) ? trace.x : [])
    .map(asNumber)
    .filter((value) => value !== null && Number.isFinite(value) && (!useLogTemperatureAxis || value > 0));
  const base = {
    title: "Temperature (K)",
    type: useLogTemperatureAxis ? "log" : "linear",
    gridcolor: "#e3e1e6",
    zeroline: false,
  };
  if (!values.length) return { ...base, autorange: true };
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return { ...base, autorange: true };
  if (useLogTemperatureAxis) {
    const logMin = Math.log10(min);
    const logMax = Math.log10(max);
    const pad = Math.max((logMax - logMin) * 0.06, 0.025);
    return { ...base, range: [logMin - pad, logMax + pad] };
  }
  const pad = Math.max((max - min) * 0.06, 10);
  return { ...base, range: [Math.max(0, min - pad), max + pad] };
}

function pressureAxisLayout(traces, useLogPressureAxis) {
  const base = {
    title: "Pressure (bar)",
    type: useLogPressureAxis ? "log" : "linear",
    autorange: "reversed",
    gridcolor: "#e3e1e6",
    zeroline: false,
  };
  if (useLogPressureAxis) return base;
  const values = traces.flatMap((trace) => Array.isArray(trace.y) ? trace.y : [])
    .map(asNumber)
    .filter((value) => value !== null && Number.isFinite(value) && value >= 0);
  if (!values.length) return base;
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return base;
  const pad = Math.max((max - min) * 0.06, max * 0.02, 0.01);
  return { ...base, range: [max + pad, Math.max(0, min - pad)] };
}

function tpProfileTraces(item, showLegend) {
  const label = item.hoverLabel || item.label || "Retrieval";
  const legendGroup = item.key || label;
  const x = item.profiles.map((row) => row.value);
  const y = item.profiles.map((row) => row.pressure);
  const markerProfiles = decimatedTpProfileMarkerRows(item.profiles);
  const lineTrace = {
    type: "scatter",
    mode: "lines",
    name: item.legendLabel || label,
    x,
    y,
    line: {
      color: item.color,
      width: item.isSelected ? tpProfileLineWidthSelected : tpProfileLineWidthComparison,
      shape: "spline",
      smoothing: 0.85,
    },
    hovertemplate: `${escapeHtml(label)}<br>T=%{x:.4g} K<br>P=%{y:.4g} bar<extra></extra>`,
    legendgroup: legendGroup,
    legendrank: item.legendRank ?? (item.isSelected ? 0 : 20),
    showlegend: showLegend,
  };
  const markerTrace = {
    type: "scatter",
    mode: "markers",
    name: `${item.legendLabel || label} anchor points`,
    x: markerProfiles.map((row) => row.value),
    y: markerProfiles.map((row) => row.pressure),
    marker: { size: tpProfileMarkerSize, color: "#000000" },
    hovertemplate: `${escapeHtml(label)}<br>T=%{x:.4g} K<br>P=%{y:.4g} bar<extra>anchor point</extra>`,
    legendgroup: legendGroup,
    showlegend: false,
  };
  return [lineTrace, markerTrace];
}

function decimatedTpProfileMarkerRows(profiles = []) {
  if (profiles.length <= 2) return profiles;
  const [referenceMin, referenceMax] = tpProfileMarkerReferenceWindowK;
  const referenceCount = profiles.filter((row) => row.value >= referenceMin && row.value <= referenceMax).length;
  const maxMarkersPerBin = referenceCount > 0 ? referenceCount : Math.min(12, profiles.length);
  if (maxMarkersPerBin <= 0) return profiles;
  const grouped = new Map();
  profiles.forEach((row, index) => {
    const value = asNumber(row.value);
    if (value === null) return;
    const key = Math.floor(value / tpProfileMarkerDensityBinK);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push({ row, index });
  });
  const keepIndexes = new Set();
  grouped.forEach((items) => {
    if (items.length <= maxMarkersPerBin) {
      items.forEach((item) => keepIndexes.add(item.index));
      return;
    }
    evenlySpacedItems(items, maxMarkersPerBin).forEach((item) => keepIndexes.add(item.index));
  });
  return profiles.filter((row, index) => keepIndexes.has(index));
}

function evenlySpacedItems(items, count) {
  if (count >= items.length) return items;
  if (count <= 1) return [items[Math.floor(items.length / 2)]];
  const out = [];
  const seen = new Set();
  for (let index = 0; index < count; index += 1) {
    const sourceIndex = Math.round((items.length - 1) * index / (count - 1));
    if (!seen.has(sourceIndex)) {
      out.push(items[sourceIndex]);
      seen.add(sourceIndex);
    }
  }
  return out;
}

function retrievalTpProfiles(payload) {
  return (payload?.profiles || [])
    .map((row) => ({ ...row, pressure: asNumber(row.pressure_bar), value: profileValue(row) }))
    .filter((row) => row.pressure !== null && row.pressure > 0 && row.value !== null)
    .sort((a, b) => a.pressure - b.pressure);
}

function condensationCurveRows(curves) {
  return (curves || []).map((curve) => {
    const points = (curve.points || [])
      .map((point) => {
        const pressure = asNumber(point.pressure_bar);
        const temperature = asNumber(point.temperature_k);
        if (pressure === null || pressure <= 0 || temperature === null) return null;
        const logPressure = asNumber(point.log10_pressure_bar) ?? Math.log10(pressure);
        return {
          ...point,
          pressure,
          temperature,
          logPressure,
          sourcePointIndex: parseInteger(point.source_point_index),
        };
      })
      .filter(Boolean)
      .sort((a, b) => {
        if (a.sourcePointIndex !== null && b.sourcePointIndex !== null) return a.sourcePointIndex - b.sourcePointIndex;
        return a.pressure - b.pressure;
      });
    return points.length >= 2 ? { ...curve, points } : null;
  }).filter(Boolean);
}

function condensationCurvePlotItems(curves, profiles = [], options = {}) {
  const profileSets = (Array.isArray(options.profileSets) && options.profileSets.length ? options.profileSets : [profiles])
    .map((profileSet) => tpProfileLogTemperaturePoints(profileSet))
    .filter((profileSet) => profileSet.length >= 2);
  const pressureProfiles = (Array.isArray(options.profileSets) && options.profileSets.length)
    ? options.profileSets.flat()
    : profiles;
  const pressureBounds = condensationCurvePressureBounds(pressureProfiles);
  if (!profileSets.length) return [];
  const includeNonCrossing = Boolean(options.includeNonCrossing);
  const items = condensationCurveRows(curves).map((curve, index) => {
    const points = pressureBounds
      ? curve.points.filter((point) => point.pressure >= pressureBounds.min && point.pressure <= pressureBounds.max)
      : curve.points;
    if (points.length < 2) return null;
    let crossing = null;
    for (const profilePoints of profileSets) {
      crossing = condensationCurveProfileCrossing(points, profilePoints, pressureBounds);
      if (crossing) break;
    }
    if (!crossing && !includeNonCrossing) return null;
    const label = condensationCurveLabel(curve);
    const color = condensationCurveColor(curve, index);
    const status = String(curve.curve_status || "").toLowerCase();
    const source = curve.source_bibcode || curve.set_name || "condensation";
    return { curve, points, label, color, status, source, crossing };
  }).filter(Boolean);
  return placeCondensationCurveLabels(items, pressureBounds);
}

function condensationCurveTraces(items) {
  return (items || []).map((item) => ({
    type: "scatter",
    mode: "lines",
    name: condensationCurveSpeciesLabel(item.curve),
    x: item.points.map((point) => point.temperature),
    y: item.points.map((point) => point.pressure),
    line: { color: item.color, width: 1.45, dash: item.status === "placeholder" ? "dot" : "solid" },
    hovertemplate: `${escapeHtml(item.label)}<br>T=%{x:.4g} K<br>P=%{y:.4g} bar<extra>${escapeHtml(item.source)}</extra>`,
    legendgroup: "condensation-curves",
    showlegend: false,
  }));
}

function condensationCurveAnnotations(items, options = {}) {
  return (items || []).map((item) => {
    const point = condensationCurveAnnotationPoint(item);
    if (!point) return null;
    const x = options.useLogTemperatureAxis ? Math.log10(point.temperature) : point.temperature;
    if (!Number.isFinite(x)) return null;
    return {
      x,
      y: options.useLogPressureAxis ? point.logPressure : point.pressure,
      xref: "x",
      yref: "y",
      text: condensationCurveSpeciesLabelHtml(item.curve),
      showarrow: false,
      xanchor: "center",
      yanchor: "middle",
      align: "center",
      font: { color: item.color, size: 11 },
      bgcolor: "rgba(255,255,255,0.74)",
      borderpad: 2,
    };
  }).filter(Boolean);
}

function condensationCurveAnnotationPoint(item) {
  const labelPoint = item?.labelPoint;
  const logPressure = asNumber(labelPoint?.logPressure)
    ?? (asNumber(labelPoint?.pressure) !== null ? Math.log10(asNumber(labelPoint.pressure)) : null);
  if (logPressure === null || !Number.isFinite(logPressure)) return null;
  const curve = logTemperaturePoints(item?.points || []);
  const temperature = interpolateLogTemperature(curve, logPressure) ?? asNumber(labelPoint?.temperature);
  if (temperature === null || !Number.isFinite(temperature) || temperature <= 0) return null;
  return { logPressure, pressure: 10 ** logPressure, temperature };
}

function placeCondensationCurveLabels(items, pressureBounds) {
  if (!items.length) return [];
  return items.map((item, index) => {
    const fraction = items.length === 1
      ? 0.5
      : condensationCurveLabelFractions[index % condensationCurveLabelFractions.length];
    const labelPoint = items.length === 1 && item.crossing
      ? item.crossing
      : condensationCurveLabelPoint(item.points, pressureBounds, fraction);
    return {
      ...item,
      labelPoint: labelPoint || item.crossing || condensationCurveLabelPoint(item.points, pressureBounds, 0.5),
    };
  });
}

function condensationCurveLabelPoint(points, pressureBounds, fraction = 0.5) {
  const curve = logTemperaturePoints(points);
  if (!curve.length) return null;
  const minLog = Math.max(curve[0].logPressure, pressureBounds ? Math.log10(pressureBounds.min) : curve[0].logPressure);
  const maxLog = Math.min(curve[curve.length - 1].logPressure, pressureBounds ? Math.log10(pressureBounds.max) : curve[curve.length - 1].logPressure);
  if (!Number.isFinite(minLog) || !Number.isFinite(maxLog) || minLog > maxLog) return null;
  const cleanFraction = Math.min(0.92, Math.max(0.08, asNumber(fraction) ?? 0.5));
  const targetLogPressure = minLog + (maxLog - minLog) * cleanFraction;
  const temperature = interpolateLogTemperature(curve, targetLogPressure);
  if (temperature !== null) return { logPressure: targetLogPressure, temperature };
  const nearest = curve.reduce((best, point) => (
    Math.abs(point.logPressure - targetLogPressure) < Math.abs(best.logPressure - targetLogPressure) ? point : best
  ), curve[0]);
  return { logPressure: nearest.logPressure, temperature: nearest.temperature };
}

function tpProfileLogTemperaturePoints(profiles = []) {
  return profiles
    .map((row) => {
      const pressure = asNumber(row.pressure);
      const temperature = profileValue(row);
      if (pressure === null || pressure <= 0 || temperature === null) return null;
      return { logPressure: Math.log10(pressure), temperature };
    })
    .filter(Boolean)
    .sort((a, b) => a.logPressure - b.logPressure);
}

function condensationCurveProfileCrossing(curvePoints, profilePoints, pressureBounds) {
  const curve = logTemperaturePoints(curvePoints);
  const profile = logTemperaturePoints(profilePoints);
  if (curve.length < 2 || profile.length < 2) return null;
  const curveMin = curve[0].logPressure;
  const curveMax = curve[curve.length - 1].logPressure;
  const profileMin = profile[0].logPressure;
  const profileMax = profile[profile.length - 1].logPressure;
  let minLog = Math.max(curveMin, profileMin);
  let maxLog = Math.min(curveMax, profileMax);
  if (pressureBounds) {
    minLog = Math.max(minLog, Math.log10(pressureBounds.min));
    maxLog = Math.min(maxLog, Math.log10(pressureBounds.max));
  }
  if (!Number.isFinite(minLog) || !Number.isFinite(maxLog) || minLog >= maxLog) return null;
  const logPressures = Array.from(new Set([
    minLog,
    maxLog,
    ...curve.map((point) => point.logPressure).filter((value) => value > minLog && value < maxLog),
    ...profile.map((point) => point.logPressure).filter((value) => value > minLog && value < maxLog),
  ])).sort((a, b) => a - b);
  let previous = null;
  for (const logPressure of logPressures) {
    const curveTemperature = interpolateLogTemperature(curve, logPressure);
    const profileTemperature = interpolateLogTemperature(profile, logPressure);
    if (curveTemperature === null || profileTemperature === null) continue;
    const difference = curveTemperature - profileTemperature;
    if (Math.abs(difference) <= 1e-6) {
      return { logPressure, temperature: curveTemperature };
    }
    if (previous && previous.difference * difference < 0) {
      const fraction = Math.abs(previous.difference) / (Math.abs(previous.difference) + Math.abs(difference));
      const crossingLogPressure = previous.logPressure + fraction * (logPressure - previous.logPressure);
      const crossingTemperature = interpolateLogTemperature(curve, crossingLogPressure);
      if (crossingTemperature !== null) return { logPressure: crossingLogPressure, temperature: crossingTemperature };
    }
    previous = { logPressure, difference };
  }
  return null;
}

function logTemperaturePoints(points = []) {
  return points
    .map((point) => {
      const logPressure = asNumber(point.logPressure ?? point.log10_pressure_bar);
      const temperature = asNumber(point.temperature ?? point.temperature_k ?? point.value);
      if (logPressure === null || temperature === null) return null;
      return { logPressure, temperature };
    })
    .filter(Boolean)
    .sort((a, b) => a.logPressure - b.logPressure);
}

function interpolateLogTemperature(points, logPressure) {
  if (!points.length || logPressure < points[0].logPressure || logPressure > points[points.length - 1].logPressure) return null;
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index];
    if (Math.abs(point.logPressure - logPressure) < 1e-10) return point.temperature;
    if (index === 0) continue;
    const previous = points[index - 1];
    if (previous.logPressure <= logPressure && logPressure <= point.logPressure) {
      const span = point.logPressure - previous.logPressure;
      if (Math.abs(span) < 1e-12) return point.temperature;
      const fraction = (logPressure - previous.logPressure) / span;
      return previous.temperature + fraction * (point.temperature - previous.temperature);
    }
  }
  return null;
}

function condensationCurveSpeciesLabel(curve) {
  return curve.condensate_formula
    || curve.condensate_name
    || curve.moca_condid
    || condensationCurveLabel(curve);
}

function condensationCurveSpeciesLabelHtml(curve) {
  return formatChemicalFormulaHtml(condensationCurveSpeciesLabel(curve));
}

function condensationCurvePressureBounds(profiles = []) {
  const pressures = profiles
    .map((row) => asNumber(row.pressure))
    .filter((pressure) => pressure !== null && pressure > 0);
  if (!pressures.length) return null;
  const minLog = Math.log10(Math.min(...pressures)) - 0.05;
  const maxLog = Math.log10(Math.max(...pressures)) + 0.05;
  return { min: 10 ** minLog, max: 10 ** maxLog };
}

function condensationCurveLabel(curve) {
  return curve.curve_label
    || curve.label
    || curve.condensate_name
    || curve.condensate_formula
    || curve.moca_condid
    || curve.moca_ccurveid
    || "Condensation curve";
}

function condensationCurveColor(curve, index) {
  const keys = [
    curve.moca_ccurveid,
    curve.moca_condid,
    curve.condensate_formula,
    curve.mineral_name,
  ].map((value) => String(value || "").trim().toUpperCase()).filter(Boolean);
  for (const key of keys) {
    if (condensationCurveColors[key]) return condensationCurveColors[key];
  }
  return condensationCurveFallbackColors[index % condensationCurveFallbackColors.length];
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
      cloudKey: row.component_label || row.species_formula || row.component_kind || "cloud",
    };
  }).filter(Boolean);
}

function cloudPressureShapes(rows, profiles = []) {
  const clouds = cloudPressureRows(rows);
  const shapes = [];
  const deepestPressure = deepestProfilePressure(profiles) || Math.max(...clouds.map((row) => row.pressure), 0);
  const byLayer = new Map();
  for (const [index, row] of clouds.entries()) {
    const key = row.cloudKey;
    if (!byLayer.has(key)) byLayer.set(key, { rows: [], colorIndex: index });
    const item = byLayer.get(key);
    item.rows.push(row);
    if (isCloudTopPressureRow(row)) {
      item.top = row.pressure;
      item.topRow = row;
    }
    if (isCloudBasePressureRow(row)) item.base = row.pressure;
  }
  byLayer.forEach((item) => {
    if (!item.top) return;
    const cloudBottom = item.base || deepestPressure;
    if (!cloudBottom || cloudBottom <= item.top) return;
    shapes.push({
      type: "rect",
      xref: "paper",
      x0: 0,
      x1: 1,
      yref: "y",
      y0: item.top,
      y1: cloudBottom,
      fillcolor: cloudPressureFillColor,
      line: { width: 0 },
      layer: "below",
    });
  });
  clouds.slice(0, 12).forEach((row, index) => {
    const isTop = isCloudTopPressureRow(row);
    shapes.push({
      type: "line",
      xref: "paper",
      x0: 0,
      x1: 1,
      yref: "y",
      y0: row.pressure,
      y1: row.pressure,
      line: {
        color: cloudPressureLineColor,
        width: isTop ? 4.4 : 2.4,
        dash: isTop ? "solid" : "dash",
      },
      layer: "below",
    });
  });
  return shapes;
}

function deepestProfilePressure(profiles = []) {
  const pressures = profiles
    .map((row) => asNumber(row.pressure))
    .filter((pressure) => pressure !== null && pressure > 0);
  return pressures.length ? Math.max(...pressures) : null;
}

function cloudPressureAnnotations(rows, options = {}) {
  const clouds = cloudPressureRows(rows);
  const topRows = clouds.filter(isCloudTopPressureRow);
  const labelRows = topRows.length ? topRows : clouds;
  return labelRows.slice(0, 6).map((row) => {
    return {
      xref: "paper",
      x: 0.985,
      xanchor: "right",
      yref: "y",
      y: options.useLogPressureAxis ? logAxisAnnotationPressure(row.pressure) : row.pressure,
      yanchor: "bottom",
      yshift: 4,
      text: escapeHtml(row.label),
      showarrow: false,
      align: "right",
      font: { size: 11, color: cloudPressureLabelColor },
      bgcolor: "rgba(255,255,255,.92)",
      bordercolor: cloudPressureLineColor,
      borderwidth: 1,
      borderpad: 2,
    };
  });
}

function isCloudTopPressureRow(row) {
  return cloudPressureRowId(row).includes("TOP");
}

function isCloudBasePressureRow(row) {
  const id = cloudPressureRowId(row);
  return id.includes("BASE") || id.includes("BOTTOM");
}

function cloudPressureRowId(row) {
  return String(row?.moca_atparid || row?.parameter_name || row?.label || "").toUpperCase();
}

function logAxisAnnotationPressure(pressure) {
  const value = asNumber(pressure);
  return value !== null && value > 0 ? Math.log10(value) : value;
}

function renderContributionPlot() {
  const rows = (rexState.payload?.contributionFunctions || [])
    .map((row) => ({ ...row, pressure: asNumber(row.pressure_bar), value: asNumber(row.value_p50 ?? row.value) }))
    .filter((row) => row.pressure !== null && row.pressure > 0 && row.value !== null);
  if (!rows.length) {
    Plotly.react(rexEl["rex-contribution-plot"], [], emptyLayout("No contribution functions", { textangle: 90 }), plotConfig("retrieval_contribution_empty"));
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
  if (!targetRows.length) {
    Plotly.react(rexEl["rex-abundance-plot"], [], emptyLayout("No abundance rows"), plotConfig("retrieval_abundance_empty"));
    return;
  }
  const mode = rexEl["rex-abundance-mode"].value;
  const numericTargetRows = targetRows.filter((row) => asNumber(row.feh_val) !== null);
  const selectedByPublication = numericTargetRows.filter(isSelectedRetrievalAbundance);
  const selected = selectedByPublication.length ? selectedByPublication : numericTargetRows;
  const selectedIds = new Set(selected.map((row) => Number(row.id)).filter(Number.isFinite));
  const selectedTypes = new Set(selected.map((row) => row.abundance_type).filter(Boolean));
  const targetIds = new Set(numericTargetRows.map((row) => Number(row.id)).filter(Number.isFinite));
  const otherRetrievalRows = numericTargetRows.filter((row) => (
    !selectedIds.has(Number(row.id))
    && selectedTypes.has(row.abundance_type)
  ));
  const context = mode === "population"
    ? comparisonRows.filter((row) => (
      asNumber(row.feh_val) !== null
      && Number(row.selected_object || 0) !== 1
      && !targetIds.has(Number(row.id))
      && selectedTypes.has(row.abundance_type)
    ))
    : [];
  const types = abundanceOrder(selected, context);
  const yPositions = abundanceYPositions(types);
  const traces = [];
  if (context.length) {
    Array.from(groupBy(context, (row) => row.abundance_type).entries()).forEach(([type, group], index) => {
      traces.push({
        type: "box",
        name: "Population context",
        x: group.map((row) => asNumber(row.feh_val)),
        y: group.map((row) => abundanceY(row, yPositions)),
        customdata: group.map((row) => [abundancePopulationHoverLabel(row), abundanceDisplayLabel(row.abundance_type)]),
        orientation: "h",
        boxpoints: "outliers",
        width: 0.46,
        marker: { color: "rgba(95,88,100,.38)", size: 4, line: { color: abundanceComparisonMarkerEdge, width: 1.1 } },
        line: { color: "rgba(95,88,100,.75)" },
        hovertemplate: "%{customdata[0]}<br>%{customdata[1]}: %{x:.4g}<extra>population context</extra>",
        legendgroup: "population-context",
        showlegend: index === 0,
      });
    });
  }
  Array.from(groupBy(otherRetrievalRows, abundanceRetrievalKey).entries()).forEach(([key, group], index) => {
    const color = rexColors[index % rexColors.length];
    traces.push({
      type: "scatter",
      mode: "markers",
      name: abundanceRetrievalLabel(group[0], key),
      x: group.map((row) => asNumber(row.feh_val)),
      y: group.map((row) => abundanceY(row, yPositions, abundanceComparisonYOffset)),
      customdata: group.map((row) => [abundanceHoverLabel(row), abundanceDisplayLabel(row.abundance_type)]),
      error_x: {
        type: "data",
        array: group.map((row) => asNumber(row.feh_unc_pos ?? row.feh_unc) || 0),
        arrayminus: group.map((row) => asNumber(row.feh_unc_neg ?? row.feh_unc) || 0),
        visible: true,
        color,
        thickness: 1,
      },
      marker: { size: 10, color, line: { color: abundanceComparisonMarkerEdge, width: 1.4 } },
      hovertemplate: "%{customdata[0]}<br>%{customdata[1]}: %{x:.4g}<extra></extra>",
    });
  });
  traces.push({
    type: "scatter",
    mode: "markers",
    name: `Selected: ${abundanceRetrievalLabel(selected[0])}`,
    x: selected.map((row) => asNumber(row.feh_val)),
    y: selected.map((row) => abundanceY(row, yPositions)),
    customdata: selected.map((row) => [abundanceHoverLabel(row), abundanceDisplayLabel(row.abundance_type)]),
    error_x: {
      type: "data",
      array: selected.map((row) => asNumber(row.feh_unc_pos ?? row.feh_unc) || 0),
      arrayminus: selected.map((row) => asNumber(row.feh_unc_neg ?? row.feh_unc) || 0),
      visible: true,
      color: "#7a5600",
      thickness: 1.5,
    },
    marker: { symbol: "star", size: 15, color: "#f2b705", line: { color: "#5a3d00", width: 2.2 } },
    hovertemplate: "%{customdata[0]}<br>%{customdata[1]}: %{x:.4g}<extra>selected retrieval</extra>",
  });
  const solarRows = (payload?.solarReferences || []).filter((row) => types.includes(row.abundance_type));
  if (solarRows.length) {
    traces.push({
      type: "scatter",
      mode: "markers",
      name: "Solar reference",
      x: solarRows.map((row) => row.value),
      y: solarRows.map((row) => abundanceY(row, yPositions)),
      customdata: solarRows.map((row) => [row.label || "solar reference", abundanceDisplayLabel(row.abundance_type)]),
      marker: { symbol: "line-ns-open", size: 24, color: "#c82424", line: { color: "#c82424", width: 4 } },
      hovertemplate: "%{customdata[0]}<br>%{customdata[1]}: %{x:.4g}<extra>solar reference</extra>",
    });
  }
  const layout = {
    margin: { l: 156, r: 20, t: 20, b: 50 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    xaxis: { title: "", gridcolor: "#e3e1e6", zeroline: true, zerolinecolor: "#c9c5cc" },
    yaxis: {
      tickmode: "array",
      tickvals: types.map((type) => yPositions.get(type)),
      ticktext: types.map(abundanceDisplayLabel),
      range: [-0.6, Math.max(types.length - 0.4, 0.6)],
      automargin: true,
      showgrid: true,
      gridcolor: "#d8d5dc",
      gridwidth: 1,
      zeroline: false,
    },
    legend: { orientation: "h", y: -0.18 },
    boxmode: "group",
  };
  Plotly.react(rexEl["rex-abundance-plot"], traces, layout, plotConfig("retrieval_abundance"));
}

function sameObject(row, atmosphere) {
  return atmosphere?.moca_oid !== undefined && Number(row.moca_oid) === Number(atmosphere.moca_oid);
}

function isSelectedRetrievalAbundance(row) {
  if (!Object.prototype.hasOwnProperty.call(row, "same_publication")) return true;
  return Number(row.same_publication || 0) === 1;
}

function abundanceRetrievalKey(row) {
  return String(row?.moca_pid || row?.source_bibcode || row?.bibcode || row?.calculation_method || row?.id || "retrieval");
}

function abundanceRetrievalLabel(row, fallback = "retrieval") {
  return String(row?.moca_pid || row?.source_bibcode || row?.bibcode || fallback || "retrieval");
}

function abundanceHoverLabel(row) {
  return compactJoin([
    abundanceRetrievalLabel(row),
    abundanceObjectLabel(row),
    row?.source_bibcode || row?.bibcode,
  ], " | ");
}

function abundancePopulationHoverLabel(row) {
  return compactJoin([
    abundanceObjectLabel(row),
    abundanceRetrievalLabel(row),
    row?.source_bibcode || row?.bibcode,
  ], " | ");
}

function abundanceDisplayLabel(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const logF = raw.match(/^log10\(f_(.+)\)$/i);
  if (logF) return `log<sub>10</sub> <i>f</i><sub>${formatChemicalFormulaHtml(logF[1])}</sub>`;
  const logQuantity = raw.match(/^log10\(([^)]+)\)(?:_(.+))?$/i);
  if (logQuantity) {
    return `log<sub>10</sub> ${formatRatioHtml(logQuantity[1])}${formatSuffixSubscript(logQuantity[2])}`;
  }
  const bracketSuffix = raw.match(/^(\[[^\]]+\])_(.+)$/);
  if (bracketSuffix) return `${escapeHtml(bracketSuffix[1])}${formatSuffixSubscript(bracketSuffix[2])}`;
  const ratioSuffix = raw.match(/^([A-Za-z0-9+]+(?:\/[A-Za-z0-9+]+)?)_(.+)$/);
  if (ratioSuffix) return `${formatRatioHtml(ratioSuffix[1])}${formatSuffixSubscript(ratioSuffix[2])}`;
  return formatChemicalFormulaHtml(raw);
}

function formatRatioHtml(value) {
  return String(value || "")
    .split("/")
    .map(formatChemicalFormulaHtml)
    .join("/");
}

function formatChemicalFormulaHtml(value) {
  return escapeHtml(value).replace(/([A-Za-z\)])(\d+)/g, "$1<sub>$2</sub>");
}

function formatSuffixSubscript(value) {
  return value ? `<sub>${escapeHtml(value)}</sub>` : "";
}

function abundanceObjectLabel(row) {
  const designation = row?.designation || row?.object_designation || (row?.moca_oid ? `oid ${row.moca_oid}` : "object");
  const spectralType = row?.spectral_type || spectralTypeNumberLabel(row?.spectral_type_number) || "SpT unavailable";
  return `${designation} | ${spectralType}`;
}

function spectralTypeNumberLabel(value) {
  const number = asNumber(value);
  return number === null ? "" : `SpTn ${formatNumber(number)}`;
}

function abundanceYPositions(types) {
  const positions = new Map();
  types.forEach((type, index) => {
    positions.set(type, types.length - 1 - index);
  });
  return positions;
}

function abundanceY(row, positions, offset = 0) {
  const position = positions.get(row?.abundance_type);
  return position === undefined ? null : position + offset;
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

function renderFundamentalParameters() {
  const rows = fundamentalParameterRows(rexState.payload);
  const cards = rexEl["rex-fundamental-cards"];
  if (cards) {
    if (!rows.length) {
      cards.innerHTML = '<div class="empty-note">No retrieval-derived fundamental parameters are stored for this retrieval.</div>';
    } else {
      cards.innerHTML = rows.slice(0, 12).map((row) => `
        <div class="retrieval-fundamental-card">
          <span>${escapeHtml(row.parameter_symbol || row.moca_atparid || row.parameter_name || "parameter")}</span>
          <strong>${escapeHtml(formatParameterValue(row))}</strong>
          <small>${escapeHtml(compactJoin([row.parameter_name || row.moca_atparid, row.value_unit || row.default_unit], " | "))}</small>
        </div>
      `).join("");
    }
  }
  renderTable(rexEl["rex-fundamental-table"], rows, [
    ["Parameter", (row) => row.parameter_name || row.moca_atparid],
    ["Symbol", (row) => row.parameter_symbol],
    ["Kind", (row) => row.parameter_kind],
    ["Value", formatParameterValue],
    ["Unit", (row) => row.value_unit || row.default_unit],
    ["Component", (row) => compactJoin([row.component_label, row.species_formula], " ")],
  ]);
}

function fundamentalParameterRows(payload) {
  return (payload?.scalarParameters || [])
    .filter(isFundamentalParameter)
    .sort((a, b) => fundamentalParameterRank(a) - fundamentalParameterRank(b));
}

function isFundamentalParameter(row) {
  const id = String(row?.moca_atparid || "").toUpperCase();
  const name = String(row?.parameter_name || "").toUpperCase();
  const kind = String(row?.parameter_kind || "").toLowerCase();
  if (kind === "cloud" || kind === "model_comparison" || kind === "evidence") return false;
  if (["derived_atmosphere", "fundamental", "physical", "nuisance", "thermal_parameterization"].includes(kind)) return true;
  return [
    "MASS",
    "RADIUS",
    "LOGG",
    "GRAVITY",
    "TEFF",
    "EFFECTIVE",
    "LUMINOS",
    "DISTANCE",
    "RCB",
    "ADIABATIC",
    "SCALE",
  ].some((needle) => id.includes(needle) || name.includes(needle));
}

function fundamentalParameterRank(row) {
  const text = `${row?.moca_atparid || ""} ${row?.parameter_name || ""}`.toUpperCase();
  const order = ["TEFF", "EFFECTIVE", "MASS", "RADIUS", "LOGG", "GRAVITY", "LUMINOS", "DISTANCE", "RCB", "ADIABATIC"];
  const index = order.findIndex((needle) => text.includes(needle));
  return index >= 0 ? index : 99;
}

function formatParameterValue(row) {
  const value = row.value_text || (row.value_p50 ?? row.value);
  const text = formatNumber(value);
  if (row.value_text) return text;
  const unc = asNumber(row.value_unc);
  if (unc !== null) return `${text} ± ${formatNumber(unc)}`;
  const uncFromPosNeg = meanFinite([
    asNumber(row.value_unc_neg),
    asNumber(row.value_unc_pos),
  ]);
  if (uncFromPosNeg !== null) return `${text} ± ${formatNumber(uncFromPosNeg)}`;
  const valueNumber = asNumber(value);
  const lo = asNumber(row.value_p16);
  const hi = asNumber(row.value_p84);
  if (lo !== null && hi !== null && valueNumber !== null) {
    const percentileUnc = (Math.abs(valueNumber - lo) + Math.abs(hi - valueNumber)) / 2;
    return `${text} ± ${formatNumber(percentileUnc)}`;
  }
  return text;
}

function renderSpectrumPlot() {
  const spectrum = rexState.payload?.retrievedSpectrum || {};
  if (!hasSpectrumData(spectrum)) {
    Plotly.react(rexEl["rex-spectrum-plot"], [], emptyLayout(spectrum.message || "No retrieved spectrum data to draw"), plotConfig("retrieval_spectrum_empty"));
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
  const selection = cornerPlotSelection(posterior);
  if (!selection.available) {
    Plotly.react(rexEl["rex-corner-plot"], [], emptyLayout(posterior.message || "No posterior samples linked to this atmosphere"), plotConfig("retrieval_corner_empty"));
    return;
  }
  const dimensions = selection.params.map((name) => ({
    label: name,
    values: selection.sampleRows.map((row) => asNumber(row[name])),
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

function updateRetrievalTabAvailability() {
  const fundamentalAvailable = fundamentalParameterRows(rexState.payload).length > 0;
  const parametersAvailable = hasParameterTableData(rexState.payload);
  const spectrumAvailable = hasSpectrumData(rexState.payload?.retrievedSpectrum || {});
  const cornerAvailable = cornerPlotSelection(rexState.payload?.posterior || {}).available;
  setRetrievalTabAvailable("fundamentals", fundamentalAvailable, "No retrieval-derived fundamental parameters are available for this retrieval.");
  setRetrievalTabAvailable("parameters", parametersAvailable, "No scalar or cloud parameters are available for this retrieval.");
  setRetrievalTabAvailable("spectrum", spectrumAvailable, "No retrieved spectrum data are available for this retrieval.");
  setRetrievalTabAvailable("corner", cornerAvailable, "No posterior samples are available for this retrieval.");
  updateSelectAvailability(rexEl["rex-corner-size"], cornerAvailable, {
    unavailableTitle: "No posterior samples are available for this retrieval.",
    availableTitle: "Choose how many posterior parameters to show in the corner plot.",
  });
}

function hasParameterTableData(payload) {
  return Boolean((payload?.scalarParameters || []).length || (payload?.cloudParameters || []).length);
}

function setRetrievalTabAvailable(tab, available, unavailableTitle) {
  const button = document.querySelector(`[data-rex-tab="${tab}"]`);
  if (!button) return;
  button.disabled = !available;
  button.classList.toggle("is-disabled", !available);
  button.setAttribute("aria-disabled", available ? "false" : "true");
  button.title = available ? "" : unavailableTitle;
}

function updateSelectAvailability(select, available, options = {}) {
  if (!select) return;
  const label = select.closest("label");
  const disabled = !available;
  select.disabled = disabled;
  select.title = disabled ? (options.unavailableTitle || "") : (options.availableTitle || "");
  label?.classList.toggle("is-disabled", disabled);
  if (label) label.title = select.title;
}

function hasSpectrumData(spectrum) {
  if (!spectrum?.available) return false;
  if (hasPlotSeries(spectrum.wavelength_um, spectrum.observed_brightness_temperature_k)) return true;
  if (hasPlotSeries(spectrum.wavelength_um, spectrum.best_fit_brightness_temperature_k)) return true;
  return (spectrum.components || []).some((component) => (
    hasPlotSeries(component?.wavelength_um, component?.brightness_temperature_k)
  ));
}

function hasPlotSeries(xValues, yValues) {
  if (!Array.isArray(xValues) || !Array.isArray(yValues)) return false;
  return xValues.some((value) => asNumber(value) !== null) && yValues.some((value) => asNumber(value) !== null);
}

function cornerPlotSelection(posterior) {
  if (!posterior?.available || !posterior.samples?.length || !posterior.parameters?.length) {
    return { available: false, params: [], sampleRows: [] };
  }
  const maxParams = Number(rexEl["rex-corner-size"]?.value || 4);
  const params = posterior.parameters.slice(0, maxParams).filter(Boolean);
  const sampleRows = posterior.samples.filter((row) => params.every((name) => asNumber(row[name]) !== null));
  return { available: params.length > 0 && sampleRows.length > 0, params, sampleRows };
}

function activateRetrievalTab(tab) {
  rexState.selectedTab = retrievalTabIsAvailable(tab || "abundances") ? (tab || "abundances") : firstAvailableRetrievalTab();
  document.querySelectorAll("[data-rex-tab]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.rexTab === rexState.selectedTab);
  });
  for (const key of ["abundances", "fundamentals", "parameters", "spectrum", "corner"]) {
    const panel = rexEl[`rex-tab-${key}`];
    if (panel) panel.hidden = key !== rexState.selectedTab;
  }
  setTimeout(() => resizeRetrievalPlots(), 0);
}

function retrievalTabIsAvailable(tab) {
  const button = document.querySelector(`[data-rex-tab="${tab}"]`);
  return !button || !button.disabled;
}

function firstAvailableRetrievalTab() {
  const fallback = ["abundances", "fundamentals", "parameters", "spectrum", "corner"]
    .find((tab) => retrievalTabIsAvailable(tab));
  return fallback || "abundances";
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

function updateRetrievalUrl(atmosphereId = null) {
  const url = new URL(window.location.href);
  const resolvedAtmosphereId = atmosphereId || selectedAtmosphereId() || parseInteger(url.searchParams.get("id"));
  if (resolvedAtmosphereId) url.searchParams.set("id", resolvedAtmosphereId);
  const oid = rexEl["rex-oid"].value.trim();
  if (oid) url.searchParams.set("moca_oid", oid);
  else url.searchParams.delete("moca_oid");
  if (rexEl["rex-include-ignored"].checked) url.searchParams.set("include_ignored", "1");
  else url.searchParams.delete("include_ignored");
  url.searchParams.delete("show_ignored");
  for (const control of retrievalUrlCheckboxControls) {
    const checkbox = rexEl[control.id];
    setDefaultBoolUrlParam(url.searchParams, control, Boolean(checkbox?.checked), Boolean(checkbox?.disabled));
  }
  for (const control of retrievalUrlSelectControls) {
    setDefaultSelectUrlParam(url.searchParams, control, rexEl[control.id]?.value);
  }
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function firstUrlParam(params, keys) {
  for (const key of keys) {
    if (params.has(key)) return params.get(key) ?? "";
  }
  return null;
}

function setSelectValueIfPresent(select, value) {
  if (!select || value === null || value === undefined) return;
  const text = String(value);
  if (Array.from(select.options || []).some((option) => option.value === text)) select.value = text;
}

function setDefaultBoolUrlParam(params, control, checked, disabled = false) {
  for (const alias of control.aliases || []) params.delete(alias);
  if (disabled || checked === control.defaultChecked) {
    params.delete(control.param);
    return;
  }
  params.set(control.param, checked ? "1" : "0");
}

function setDefaultSelectUrlParam(params, control, value) {
  for (const alias of control.aliases || []) params.delete(alias);
  const text = value === null || value === undefined ? "" : String(value);
  if (!text || text === control.defaultValue) {
    params.delete(control.param);
    return;
  }
  params.set(control.param, text);
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

function emptyLayout(message, options = {}) {
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
      textangle: options.textangle || 0,
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

function meanFinite(values) {
  const numbers = values.filter((value) => Number.isFinite(value));
  if (!numbers.length) return null;
  return numbers.reduce((sum, value) => sum + Math.abs(value), 0) / numbers.length;
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
