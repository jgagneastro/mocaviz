const mflowsDefaultOid = 11266;
const mflowsDefaultAid = "ABDMG";
const mflowsTeamUsers = new Set(["collaborators", "management"]);
const mflowsDefaultModelVersion = "v1.0";
const mflowsFullForwardResultKeys = new Set(["full_forward_model", "association_full_forward_model"]);
const mflowsDynamicAgeMinMyr = 1;
const mflowsDynamicAgeMaxMyr = 1.35e4;

const mflowsState = {
  associations: [],
  associationFilter: "",
  minStackedStars: 0,
  payload: null,
  requestedModelVersion: "",
  searchTimer: null,
  loadToken: 0,
  auth: { role: "", hasCredentials: false, private_db: false },
};

const mflowsEl = {};

document.addEventListener("DOMContentLoaded", initMocaFlows);

const mflowsAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function mflowsAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), mflowsAppBaseUrl).toString();
}

async function initMocaFlows() {
  collectMocaFlowsElements();
  readMocaFlowsUrlState();
  bindMocaFlowsControls();
  updateMocaFlowsScopeControls();
  attachMocaFlowsAuth();
  const optionsPromise = loadMocaFlowsOptions();
  await loadMocaFlowsData();
  await optionsPromise;
}

function collectMocaFlowsElements() {
  [
    "mflows-status",
    "mflows-scope-object",
    "mflows-scope-association",
    "mflows-object-controls",
    "mflows-association-controls",
    "mflows-object-search",
    "mflows-object-results",
    "mflows-oid-input",
    "mflows-aid-filter",
    "mflows-min-stacked-stars",
    "mflows-aid-select",
    "mflows-load",
    "mflows-stack-section",
    "mflows-stack-mode",
    "mflows-mh-treatment",
    "mflows-curve-role",
    "mflows-model-version",
    "mflows-log-x",
    "mflows-log-y",
    "mflows-fixed-xrange",
    "mflows-compact",
    "mflows-summary",
    "mflows-hint",
    "mflows-open-report",
    "mflows-export-csv",
    "mflows-clear-cache",
    "mflows-panel-grid",
    "mflows-empty",
    "mflows-run-metadata",
  ].forEach((id) => {
    mflowsEl[id] = document.getElementById(id);
  });
}

function readMocaFlowsUrlState() {
  const params = new URLSearchParams(window.location.search);
  const scopeRaw = String(params.get("target") || params.get("scope") || params.get("mode") || "").toLowerCase();
  let scope = "association";
  if (scopeRaw === "object" || params.get("moca_oid") || params.get("oid")) scope = "object";
  if (scopeRaw === "association" || params.get("moca_aid") || params.get("aid")) scope = "association";
  mflowsEl["mflows-scope-object"].checked = scope === "object";
  mflowsEl["mflows-scope-association"].checked = scope === "association";
  mflowsEl["mflows-oid-input"].value = parseInteger(params.get("moca_oid") || params.get("oid")) ?? mflowsDefaultOid;

  const aid = String(params.get("moca_aid") || params.get("aid") || mflowsDefaultAid).trim().toUpperCase();
  mflowsEl["mflows-aid-select"].innerHTML = `<option value="${escapeHtml(aid)}">${escapeHtml(aid)}</option>`;
  mflowsEl["mflows-aid-select"].value = aid;

  const minStackedStars = Math.max(
    0,
    parseInteger(params.get("min_stacked") || params.get("min_stacked_stars") || params.get("min_stars")) ?? 0,
  );
  mflowsState.minStackedStars = minStackedStars;
  mflowsEl["mflows-min-stacked-stars"].value = minStackedStars > 0 ? String(minStackedStars) : "";

  const stackMode = String(params.get("stack_mode") || params.get("stack") || "hbm").toLowerCase();
  mflowsEl["mflows-stack-mode"].value = stackMode === "normal" || stackMode === "simple" ? "normal" : "hbm";

  const mh = String(params.get("mh_treatment") || params.get("metallicity") || "db").toLowerCase();
  mflowsEl["mflows-mh-treatment"].value = ["db", "marginalized", "copula2d"].includes(mh) ? mh : "db";

  const checkbox = new Set(parseCsv(params.get("checkbox"), []));
  for (const key of ["posteriors", "log_x", "log_y", "compact", "full_xrange", "fixed_xrange"]) {
    if (asBool(params.get(key))) checkbox.add(key);
  }
  const rawCurveRole = params.get("curve_role") || params.get("role") || params.get("pdf_role") || "";
  mflowsEl["mflows-curve-role"].value = rawCurveRole
    ? normalizeMocaFlowsCurveRole(rawCurveRole)
    : "posterior";
  mflowsState.requestedModelVersion = String(
    params.get("model_version")
      || params.get("mocaflows_model_version")
      || params.get("mflows_model_version")
      || "",
  ).trim();
  mflowsState.requestedModelVersion = normalizeMocaFlowsModelVersionSelection(mflowsState.requestedModelVersion);
  mflowsEl["mflows-log-x"].checked = checkbox.has("log_x") || !params.has("checkbox");
  mflowsEl["mflows-log-y"].checked = checkbox.has("log_y");
  const rawFullXRange = params.get("full_xrange") ?? params.get("fixed_xrange");
  mflowsEl["mflows-fixed-xrange"].checked = rawFullXRange === null
    ? !checkbox.has("trim_xrange")
    : asBool(rawFullXRange) || checkbox.has("full_xrange") || checkbox.has("fixed_xrange");
  mflowsEl["mflows-compact"].checked = checkbox.has("compact");
}

function bindMocaFlowsControls() {
  mflowsEl["mflows-scope-object"].addEventListener("change", () => {
    updateMocaFlowsScopeControls();
    loadMocaFlowsData();
  });
  mflowsEl["mflows-scope-association"].addEventListener("change", () => {
    updateMocaFlowsScopeControls();
    loadMocaFlowsData();
  });
  mflowsEl["mflows-oid-input"].addEventListener("change", loadMocaFlowsData);
  mflowsEl["mflows-aid-select"].addEventListener("change", loadMocaFlowsData);
  mflowsEl["mflows-load"].addEventListener("click", loadMocaFlowsData);
  mflowsEl["mflows-stack-mode"].addEventListener("change", () => {
    renderMocaFlowsAssociationOptions();
    loadMocaFlowsData();
  });
  for (const id of ["mflows-mh-treatment", "mflows-curve-role"]) {
    mflowsEl[id].addEventListener("change", loadMocaFlowsData);
  }
  mflowsEl["mflows-model-version"].addEventListener("change", () => {
    renderMocaFlowsPanels();
    updateMocaFlowsUrl();
  });
  for (const id of ["mflows-log-x", "mflows-log-y", "mflows-fixed-xrange", "mflows-compact"]) {
    mflowsEl[id].addEventListener("change", () => {
      renderMocaFlowsPanels();
      updateMocaFlowsUrl();
    });
  }
  mflowsEl["mflows-aid-filter"].addEventListener("input", () => {
    mflowsState.associationFilter = mflowsEl["mflows-aid-filter"].value.trim().toLowerCase();
    renderMocaFlowsAssociationOptions();
  });
  mflowsEl["mflows-min-stacked-stars"].addEventListener("input", () => {
    const parsed = parseInteger(mflowsEl["mflows-min-stacked-stars"].value);
    mflowsState.minStackedStars = Math.max(0, parsed ?? 0);
    renderMocaFlowsAssociationOptions();
  });
  mflowsEl["mflows-object-search"].addEventListener("input", () => {
    const value = mflowsEl["mflows-object-search"].value.trim();
    clearTimeout(mflowsState.searchTimer);
    mflowsState.searchTimer = setTimeout(() => searchMocaFlowsObjects(value), 250);
  });
  mflowsEl["mflows-object-search"].addEventListener("focus", () => {
    const value = mflowsEl["mflows-object-search"].value.trim();
    if (value) searchMocaFlowsObjects(value);
  });
  document.addEventListener("click", (event) => {
    if (!mflowsEl["mflows-object-results"].contains(event.target) && event.target !== mflowsEl["mflows-object-search"]) {
      mflowsEl["mflows-object-results"].hidden = true;
    }
  });
  mflowsEl["mflows-open-report"].addEventListener("click", openMocaFlowsReport);
  mflowsEl["mflows-export-csv"].addEventListener("click", exportMocaFlowsCsv);
  mflowsEl["mflows-clear-cache"].addEventListener("click", clearMocaFlowsCache);
  window.addEventListener("resize", debounce(() => resizeMocaFlowsPlots(), 150));
}

function attachMocaFlowsAuth() {
  const applyAuth = (auth) => {
    mflowsState.auth = auth || mflowsState.auth;
    updateMocaFlowsAuthHint();
  };
  if (window.MocaAuthContext?.ready) {
    window.MocaAuthContext.ready.then(applyAuth).catch(() => updateMocaFlowsAuthHint());
  }
  window.addEventListener("mocaviz-auth-context", (event) => applyAuth(event.detail || {}));
  updateMocaFlowsAuthHint();
}

function updateMocaFlowsAuthHint() {
  const auth = mflowsState.auth || {};
  const params = new URLSearchParams(window.location.search);
  const user = String(params.get("user") || params.get("username") || "").trim().toLowerCase();
  const dbName = String(params.get("dbase") || params.get("db") || params.get("database") || "").replace(/`/g, "").trim().toLowerCase();
  const urlLooksPrivate = mflowsTeamUsers.has(user) && dbName === "mocadb_private_tables";
  const loggedInPrivate = Boolean(auth.private_db && auth.role && auth.hasCredentials) || urlLooksPrivate || asBool(params.get("mock"));
  document.body.classList.toggle("mflows-private-ready", loggedInPrivate);
  if (!loggedInPrivate) {
    mflowsEl["mflows-hint"].textContent = "This tool is intended for authenticated mocadb_private_tables sessions.";
  }
}

function updateMocaFlowsScopeControls() {
  const scope = currentMocaFlowsScope();
  mflowsEl["mflows-object-controls"].hidden = scope !== "object";
  mflowsEl["mflows-association-controls"].hidden = scope !== "association";
  mflowsEl["mflows-stack-section"].hidden = scope !== "association";
  mflowsEl["mflows-open-report"].disabled = !mocaFlowsReportUrl();
}

async function loadMocaFlowsOptions() {
  const params = mocaFlowsApiParams();
  try {
    const payload = await fetchJsonUrl(mflowsAppUrl(`api/moca-flows/options?${params.toString()}`));
    mflowsState.associations = payload.associations || [];
  } catch (_error) {
    mflowsState.associations = [];
  }
  renderMocaFlowsAssociationOptions();
}

function renderMocaFlowsAssociationOptions() {
  const current = String(mflowsEl["mflows-aid-select"].value || mflowsDefaultAid).toUpperCase();
  const currentRow = mflowsState.associations.find((row) => mocaFlowsAssociationValue(row) === current) || {
    value: current,
    label: current,
    stacked_member_count: 0,
  };
  const hasQuickSearch = Boolean(mflowsState.associationFilter);
  const minStackedStars = Math.max(0, mflowsState.minStackedStars || 0);
  const hasCountFilter = minStackedStars > 0;
  const filterActive = hasQuickSearch || hasCountFilter;
  let rows = mflowsState.associations;
  if (mflowsState.associationFilter) {
    rows = rows.filter((row) => mocaFlowsAssociationSearchText(row).includes(mflowsState.associationFilter));
  }
  if (hasCountFilter) {
    rows = rows.filter((row) => mocaFlowsAssociationStackCount(row) >= minStackedStars);
  }
  rows = rows.slice(0, 800);
  if (!filterActive && current && !rows.some((row) => mocaFlowsAssociationValue(row) === current)) {
    rows = [currentRow, ...rows];
  }
  const currentVisible = rows.some((row) => mocaFlowsAssociationValue(row) === current);
  const options = [];
  if (filterActive && current && !currentVisible) {
    options.push(`<option value="${escapeHtml(current)}" selected hidden>${escapeHtml(mocaFlowsAssociationLabel(currentRow))}</option>`);
  }
  if (!rows.length) {
    options.push('<option value="" disabled>No matching associations</option>');
    mflowsEl["mflows-aid-select"].innerHTML = options.join("");
    if (current) mflowsEl["mflows-aid-select"].value = current;
    return;
  }
  options.push(...rows.map((row) => {
    const value = mocaFlowsAssociationValue(row);
    const label = mocaFlowsAssociationLabel(row);
    return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
  }));
  mflowsEl["mflows-aid-select"].innerHTML = options.join("");
  if (currentVisible || current) {
    mflowsEl["mflows-aid-select"].value = current;
  }
}

function mocaFlowsAssociationValue(row) {
  return String(row.value || row.moca_aid || "").trim().toUpperCase();
}

function mocaFlowsAssociationSearchText(row) {
  return [
    row.value,
    row.moca_aid,
    row.name,
    row.label,
    mocaFlowsAssociationStackCount(row),
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
}

function mocaFlowsAssociationLabel(row) {
  const value = String(row.value || row.moca_aid || "").trim();
  const name = String(row.name || "").trim();
  const base = String(row.label || (name && value ? `${value} - ${name}` : value || name)).trim();
  return `${base || value || "Association"} (${mocaFlowsAssociationStackCount(row)})`;
}

function mocaFlowsAssociationStackCount(row) {
  const stackMode = String(mflowsEl["mflows-stack-mode"]?.value || "hbm").toLowerCase();
  const hbmCount = parseInteger(row.hbm_stacked_member_count);
  const normalCount = parseInteger(row.normal_stacked_member_count);
  const genericCount = parseInteger(row.stacked_member_count ?? row.member_count ?? row.count);
  if (stackMode === "hbm" && hbmCount !== null) return Math.max(0, hbmCount);
  if (stackMode !== "hbm" && normalCount !== null) return Math.max(0, normalCount);
  if (genericCount !== null) return Math.max(0, genericCount);
  if (hbmCount !== null) return Math.max(0, hbmCount);
  if (normalCount !== null) return Math.max(0, normalCount);
  return 0;
}

async function searchMocaFlowsObjects(query) {
  if (!query) {
    mflowsEl["mflows-object-results"].hidden = true;
    return;
  }
  const params = mocaFlowsApiParams();
  params.set("q", query);
  try {
    const payload = await fetchJsonUrl(mflowsAppUrl(`api/moca-flows/search?${params.toString()}`));
    const options = payload.options || [];
    if (!options.length) {
      mflowsEl["mflows-object-results"].innerHTML = '<div class="designation-result-note">No matches</div>';
      mflowsEl["mflows-object-results"].hidden = false;
      return;
    }
    mflowsEl["mflows-object-results"].innerHTML = options.map((option) => `
      <button type="button" class="designation-result" data-oid="${escapeHtml(option.value)}">
        <span>${escapeHtml(option.label || option.designation || option.value)}</span>
      </button>
    `).join("");
    mflowsEl["mflows-object-results"].querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        mflowsEl["mflows-oid-input"].value = button.dataset.oid;
        mflowsEl["mflows-object-search"].value = "";
        mflowsEl["mflows-object-results"].hidden = true;
        if (!mflowsEl["mflows-scope-object"].checked) {
          mflowsEl["mflows-scope-object"].checked = true;
          updateMocaFlowsScopeControls();
        }
        loadMocaFlowsData();
      });
    });
    mflowsEl["mflows-object-results"].hidden = false;
  } catch (error) {
    mflowsEl["mflows-object-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(error.message)}</div>`;
    mflowsEl["mflows-object-results"].hidden = false;
  }
}

async function loadMocaFlowsData() {
  const token = ++mflowsState.loadToken;
  setMocaFlowsLoading(true);
  setMocaFlowsStatus("Loading MOCAFlows panels", "loading");
  updateMocaFlowsScopeControls();
  updateMocaFlowsUrl();
  const params = buildMocaFlowsParams();
  try {
    const payload = await fetchJsonUrl(mflowsAppUrl(`api/moca-flows/data?${params.toString()}`));
    if (token !== mflowsState.loadToken) return;
    if (!payload.ok) {
      mflowsState.payload = payload;
      renderMocaFlowsEmpty(payload.error || "Could not load MOCAFlows panels");
      return;
    }
    mflowsState.payload = payload;
    syncMocaFlowsModelVersionOptions(payload);
    renderMocaFlowsPanels();
    updateMocaFlowsUrl();
  } catch (error) {
    if (token !== mflowsState.loadToken) return;
    renderMocaFlowsEmpty(error.message || "Could not load MOCAFlows panels");
  }
}

function renderMocaFlowsPanels() {
  const payload = mflowsState.payload;
  const allPanels = payload?.panels || [];
  const panels = mocaFlowsVisiblePanels(payload);
  const renderPayload = payload ? { ...payload, panels } : payload;
  mflowsEl["mflows-panel-grid"].classList.toggle("is-compact", Boolean(mflowsEl["mflows-compact"].checked));
  mflowsEl["mflows-panel-grid"].innerHTML = "";
  if (!allPanels.length) {
    renderMocaFlowsRunMetadata(null);
    renderMocaFlowsEmpty(payload?.error || "No MOCAFlows panels available for this target.");
    return;
  }
  if (!panels.length) {
    renderMocaFlowsRunMetadata(null);
    mflowsEl["mflows-empty"].textContent = "No panels match the selected MOCAFlows model version.";
    mflowsEl["mflows-empty"].hidden = false;
    updateMocaFlowsSummary();
    setMocaFlowsExportDisabled(true);
    setMocaFlowsLoading(false);
    setMocaFlowsStatus(`0 of ${allPanels.length} MOCAFlows panels`, "");
    return;
  }
  mflowsEl["mflows-empty"].hidden = true;
  panels.forEach((panel, index) => {
    const article = document.createElement("article");
    article.className = "mflows-panel";
    const plotId = `mflows-panel-plot-${index}`;
    article.innerHTML = `
      <div class="mflows-panel-heading">
        <h3>${mocaFlowsPanelTitleHtml(panel)}</h3>
        <div class="mflows-panel-role">${escapeHtml(panel.curve_role || panel.curve?.metadata?.curve_role || "")}</div>
      </div>
      <div id="${plotId}" class="mflows-panel-plot"></div>
      <div class="mflows-panel-info">${mocaFlowsPanelInfoHtml(panel, renderPayload)}</div>
    `;
    mflowsEl["mflows-panel-grid"].appendChild(article);
    const plot = article.querySelector(`#${plotId}`);
    if (shouldRenderMocaFlowsMap(panel)) {
      renderMocaFlowsMap(plot, panel, renderPayload);
    } else {
      renderMocaFlowsAgePanel(plot, panel, renderPayload);
    }
  });
  renderMocaFlowsRunMetadata(renderPayload);
  updateMocaFlowsSummary();
  setMocaFlowsExportDisabled(false);
  setMocaFlowsLoading(false);
  setMocaFlowsStatus(
    panels.length === allPanels.length ? `${panels.length} MOCAFlows panels` : `${panels.length} of ${allPanels.length} MOCAFlows panels`,
    "",
  );
  scheduleMocaFlowsPlotResize();
}

function mocaFlowsPanelTitleHtml(panel) {
  const resultKey = mocaFlowsPanelResultKey(panel);
  if (resultKey === "toomre_t" || resultKey === "vtan") {
    return mocaFlowsKinematicPanelTitleHtml(panel, resultKey);
  }
  const formattedTitles = {
    ali_combined: "Lithium abundance <i>A</i>(Li)",
    gaia_act: "Gaia DR3 ESP-CS Activity Index",
    varg: "Var<sub>G</sub><sup>′</sup>",
    varbp: "Var<sub>BP</sub><sup>′</sup>",
    varrp: "Var<sub>RP</sub><sup>′</sup>",
    log_lx: "X-ray flux log <i>L</i><sub>X</sub>",
    radio_lnu: "Radio flux log <i>L</i><sub>ν</sub>",
    vsini: "<i>v</i> sin <i>i</i>",
  };
  if (formattedTitles[resultKey]) {
    return formattedTitles[resultKey];
  }
  if (isMocaFlowsRPrimeHkPanel(panel)) {
    return `log <i>R</i><sup>′</sup><sub>HK</sub>`;
  }
  if (isMocaFlowsLowResolutionLithiumPanel(panel)) {
    return `Lithium (low-resolution <i>R</i> &lt; 10,000)`;
  }
  return escapeHtml(panel?.title || panel?.result_key || "MOCAFlows");
}

function mocaFlowsKinematicPanelTitleHtml(panel, resultKey) {
  if (resultKey === "vtan") return "<i>V</i><sub>tan</sub>";
  const meta = panel?.metadata || {};
  const curveMeta = panel?.curve?.metadata || {};
  const text = [
    panel?.title,
    panel?.curve?.label,
    panel?.curve?.summary?.calculation_method,
    panel?.curve?.summary?.comments,
    meta.calculation_method,
    meta.comments,
    curveMeta.calculation_method,
    curveMeta.comments,
  ].filter((value) => value !== null && value !== undefined && value !== "")
    .join(" ")
    .toLowerCase();
  const hasToomre = text.includes("toomre");
  const hasVtan = text.includes("vtan") || text.includes("v tan") || text.includes("tangential");
  if (hasToomre && hasVtan) return "Toomre <i>T</i> / <i>V</i><sub>tan</sub>";
  if (hasVtan && !hasToomre) return "<i>V</i><sub>tan</sub>";
  return "Toomre <i>T</i>";
}

function mocaFlowsPanelResultKey(panel) {
  const meta = panel?.metadata || panel?.curve?.metadata || {};
  return String(panel?.result_key || meta.result_key || "").trim().toLowerCase();
}

function isMocaFlowsLowResolutionLithiumPanel(panel) {
  const meta = panel?.metadata || panel?.curve?.metadata || {};
  const values = [
    panel?.result_key,
    panel?.title,
    panel?.curve?.label,
    meta.result_key,
    meta.calculation_method,
  ];
  const normalized = values
    .filter((value) => value !== null && value !== undefined)
    .map((value) => String(value).toLowerCase().replace(/[^a-z0-9]+/g, ""))
    .join(" ");
  return normalized.includes("lilowres")
    || normalized.includes("lithiumlowres")
    || normalized.includes("lithiumlowresolution");
}

function isMocaFlowsRPrimeHkPanel(panel) {
  const meta = panel?.metadata || panel?.curve?.metadata || {};
  const values = [
    panel?.result_key,
    panel?.title,
    panel?.curve?.label,
    meta.result_key,
    meta.calculation_method,
  ];
  const normalized = values
    .filter((value) => value !== null && value !== undefined)
    .map((value) => String(value).toLowerCase().replace(/[^a-z0-9]+/g, ""))
    .join(" ");
  return normalized.includes("rprimehk")
    || normalized.includes("rprimeh")
    || normalized.includes("logrhk");
}

function mocaFlowsVisiblePanels(payload = mflowsState.payload) {
  const panels = payload?.panels || [];
  const selected = mflowsEl["mflows-model-version"]?.value || "";
  if (!selected) return panels;
  return panels.filter((panel) => mocaFlowsPanelModelVersion(panel).value === selected);
}

function syncMocaFlowsModelVersionOptions(payload) {
  const select = mflowsEl["mflows-model-version"];
  if (!select) return;
  const options = mocaFlowsModelVersionOptions(payload);
  const requested = mflowsState.requestedModelVersion || select.value || "";
  const totalPanels = payload?.panels?.length || 0;
  select.innerHTML = "";
  if (!totalPanels) {
    select.disabled = true;
    select.innerHTML = '<option value="">No model versions</option>';
    return;
  }
  select.disabled = false;
  const allNode = document.createElement("option");
  allNode.value = "";
  allNode.textContent = `All versions (${totalPanels})`;
  select.appendChild(allNode);
  for (const option of options) {
    const node = document.createElement("option");
    node.value = option.value;
    node.textContent = `${option.label} (${option.count})`;
    select.appendChild(node);
  }
  const normalizedRequested = normalizeMocaFlowsModelVersionSelection(requested);
  const selected = normalizedRequested && options.some((option) => option.value === normalizedRequested)
    ? normalizedRequested
    : "";
  select.value = selected;
  mflowsState.requestedModelVersion = "";
}

function mocaFlowsModelVersionOptions(payload) {
  const counts = new Map();
  for (const panel of payload?.panels || []) {
    const version = mocaFlowsPanelModelVersion(panel);
    const existing = counts.get(version.value);
    if (existing) {
      existing.count += 1;
    } else {
      counts.set(version.value, { ...version, count: 1 });
    }
  }
  return Array.from(counts.values()).sort((a, b) => {
    return String(b.label).localeCompare(String(a.label), undefined, { numeric: true, sensitivity: "base" });
  });
}

function mocaFlowsPanelModelVersion(panel) {
  const metadataVersion = cleanMocaFlowsModelVersion(
    mocaFlowsModelVersionFromMetadata(panel?.metadata)
      || mocaFlowsModelVersionFromMetadata(panel?.curve?.metadata)
      || mocaFlowsModelVersionFromMetadata(panel?.curve?.metadata?.metadata_json),
  );
  const commentVersion = cleanMocaFlowsModelVersion(
    mocaFlowsModelVersionFromText(mocaFlowsPanelCommentsText(panel)),
  );
  const value = metadataVersion || commentVersion;
  if (value) return { value, label: value };
  return { value: mflowsDefaultModelVersion, label: mflowsDefaultModelVersion };
}

function mocaFlowsPanelCommentsText(panel) {
  const parts = [];
  pushMocaFlowsText(parts, panel?.comments);
  pushMocaFlowsText(parts, panel?.metadata?.comments);
  pushMocaFlowsText(parts, panel?.curve?.comments);
  pushMocaFlowsText(parts, panel?.curve?.summary?.comments);
  pushMocaFlowsText(parts, panel?.curve?.metadata?.comments);
  pushMocaFlowsText(parts, panel?.curve?.metadata?.metadata_json);
  return parts.join("\n");
}

function pushMocaFlowsText(parts, value) {
  if (value === null || value === undefined || value === "") return;
  if (typeof value === "string") {
    const text = value.trim();
    if (text) parts.push(text);
    return;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    parts.push(String(value));
    return;
  }
  try {
    const text = JSON.stringify(value);
    if (text && text !== "{}" && text !== "[]") parts.push(text);
  } catch (_error) {
    const text = String(value || "").trim();
    if (text) parts.push(text);
  }
}

function mocaFlowsModelVersionFromMetadata(value) {
  if (!value || typeof value !== "object") return "";
  const stack = [{ value, path: "" }];
  const seen = new Set();
  while (stack.length) {
    const item = stack.pop();
    const objectValue = item.value;
    if (!objectValue || typeof objectValue !== "object" || seen.has(objectValue)) continue;
    seen.add(objectValue);
    for (const [key, child] of Object.entries(objectValue)) {
      const path = item.path ? `${item.path}.${key}` : key;
      if (isMocaFlowsModelVersionKey(path)) {
        const version = cleanMocaFlowsModelVersion(child);
        if (version) return version;
      }
      if (child && typeof child === "object") stack.push({ value: child, path });
    }
  }
  return "";
}

function isMocaFlowsModelVersionKey(path) {
  const normalized = String(path || "").toLowerCase().replace(/[^a-z0-9]+/g, "_");
  if (/(^|_)moca_?flows?_.*(model_)?version$/.test(normalized)) return true;
  if (/(^|_)true_?age_.*(model_)?version$/.test(normalized)) return true;
  if (/(^|_)(model|product|pipeline|report|code|run)_(version|tag|commit|sha|hash|id)$/.test(normalized)) return true;
  return /(^|_)(model|product|pipeline|report|code|run).*_(version|tag|commit|sha|hash|id)$/.test(normalized);
}

function mocaFlowsModelVersionFromText(text) {
  const source = String(text || "");
  if (!source.trim()) return "";
  const patterns = [
    /\b(?:mocaflows?|moca_?flows?|trueage|true_?age|model|product|pipeline|report|code|run)[\s_-]*(?:model|product|pipeline|report|code)?[\s_-]*(?:version|ver\.?|v|tag|commit|sha|hash|id)\s*[:=]\s*["']?([A-Za-z0-9][A-Za-z0-9._+:/-]{0,100})/i,
    /\b(?:mocaflows?|moca\s*flows|trueage|true\s*age)(?:\s+(?:model|product|pipeline|report|code))?\s*(?:version|ver\.?|v)\s*[:=]\s*["']?([A-Za-z0-9][A-Za-z0-9._+:/-]{0,100})/i,
    /\b(?:flagged|classified|tagged|marked|labeled|labelled|using|uses|use|from|as)\s+(v\s*\d+(?:[._-]\s*\d+){1,2})\b/i,
    /\b(v\s*\d+(?:[._-]\s*\d+){1,2})\b/i,
    /\b(?:git|commit|sha|hash)\s*[:=]\s*["']?([A-Fa-f0-9]{7,40})/i,
    /\b(?:version|ver\.?)\s*[:=]\s*["']?([A-Za-z0-9][A-Za-z0-9._+:/-]{0,100})/i,
  ];
  for (const pattern of patterns) {
    const match = source.match(pattern);
    const version = cleanMocaFlowsModelVersion(match?.[1]);
    if (version) return version;
  }
  return "";
}

function normalizeMocaFlowsModelVersionSelection(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  if (raw.toLowerCase() === "unspecified") return mflowsDefaultModelVersion;
  return cleanMocaFlowsModelVersion(raw);
}

function cleanMocaFlowsModelVersion(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return "";
  let text = String(value).trim();
  text = text.replace(/^["'`]+|["'`]+$/g, "");
  text = text.replace(/[.;,)\]}]+$/g, "");
  if (!text || text.length > 120) return "";
  const lower = text.toLowerCase();
  if (["none", "null", "nan", "na", "n/a", "unknown", "unspecified"].includes(lower)) return "";
  const numericVersion = text.replace(/\s+/g, "").match(/^v?(\d+)(?:[._-](\d+))(?:[._-](\d+))?$/i);
  if (numericVersion) {
    const parts = [numericVersion[1], numericVersion[2], numericVersion[3]].filter(Boolean);
    return `v${parts.join(".")}`;
  }
  return text;
}

function shouldRenderMocaFlowsMap(panel) {
  return mflowsEl["mflows-mh-treatment"].value === "copula2d" && panel.map;
}

function renderMocaFlowsAgePanel(plot, panel, payload) {
  const curve = panel.curve || {};
  const age = (curve.age_myr || []).map(Number);
  const pdf = (curve.pdf_age || []).map(Number);
  const logX = mflowsEl["mflows-log-x"].checked;
  const x = [];
  const y = [];
  for (let i = 0; i < age.length; i += 1) {
    if (Number.isFinite(age[i]) && age[i] > 0 && Number.isFinite(pdf[i])) {
      x.push(age[i]);
      y.push(mocaFlowsDisplayedPdfValue(age[i], pdf[i], logX));
    }
  }
  const logY = mflowsEl["mflows-log-y"].checked;
  const yRange = mocaFlowsPdfYRange(y, logY);
  const densityLabel = logX ? "Relative density per log age" : "Relative density";
  const trace = {
    x,
    y,
    type: "scatter",
    mode: "lines",
    name: panel.title || curve.label || "MOCAFlows",
    line: { color: "#111111", width: 2.4 },
    hovertemplate: `Age: %{x:.4g} Myr<br>${densityLabel}: %{y:.4g}<extra></extra>`,
  };
  const shapes = [
    ...mocaFlowsMeasurementShapes(payload, "below"),
    ...mocaFlowsCurveMarkerShapes(panel, "above", { perLogAge: logX }),
    ...mocaFlowsFullForwardAgeShapes(payload, panel, "above", { perLogAge: logX }),
    ...mocaFlowsAdoptedAgeShapes(payload, "above"),
  ];
  const annotations = mocaFlowsAgeAnnotations(payload);
  const range = mocaFlowsAgeRange(x, y, payload, panel);
  const compact = mflowsEl["mflows-compact"].checked;
  const tickOptions = logX ? mocaFlowsLogTickOptions(range, x, compact) : {};
  const layout = {
    title: { text: "", x: 0.5 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    margin: { l: 54, r: 14, t: 8, b: 46 },
    showlegend: false,
    shapes,
    annotations,
    xaxis: {
      title: { text: "Age (Myr)", font: { size: 12 } },
      type: logX ? "log" : "linear",
      showline: true,
      linewidth: 1.3,
      linecolor: "#444444",
      mirror: true,
      ticks: "outside",
      tickfont: { size: compact ? 10 : 11 },
      automargin: true,
      showgrid: true,
      gridcolor: "rgba(0,0,0,0.10)",
      zeroline: false,
      range: range,
      ...tickOptions,
    },
    yaxis: {
      title: { text: logX ? "Relative probability density per log age" : "Relative probability density", font: { size: 12 } },
      type: logY ? "log" : "linear",
      showline: true,
      linewidth: 1.3,
      linecolor: "#444444",
      mirror: true,
      ticks: "",
      showticklabels: false,
      showgrid: false,
      zeroline: false,
      rangemode: logY ? "normal" : "tozero",
      range: yRange,
    },
  };
  Plotly.react(plot, [trace], layout, mocaFlowsPlotConfig(panel.result_key || "mocaflows"));
}

function mocaFlowsDisplayedPdfValue(ageMyr, pdfAge, perLogAge = false) {
  const age = Number(ageMyr);
  const pdf = Number(pdfAge);
  if (!Number.isFinite(age) || age <= 0 || !Number.isFinite(pdf)) return NaN;
  return perLogAge ? pdf * age * Math.LN10 : pdf;
}

function mocaFlowsPeakContainingInterval(paired, cdf, total, peakIndex, perLogAge = false, mass = 0.68) {
  if (!Number.isFinite(total) || total <= 0 || !paired?.length || peakIndex < 0) return null;
  const target = Math.min(Math.max(mass, 0), 1) * total;
  if (!Number.isFinite(target) || target <= 0) return null;
  const peakArea = cdf[peakIndex];
  const peakCoord = paired[peakIndex]?.coord;
  if (!Number.isFinite(peakArea) || !Number.isFinite(peakCoord)) return null;

  const coordAtArea = (area) => {
    const clamped = Math.min(Math.max(area, 0), total);
    for (let index = 1; index < cdf.length; index += 1) {
      if (cdf[index] < clamped) continue;
      const denom = cdf[index] - cdf[index - 1];
      const frac = denom > 0 ? (clamped - cdf[index - 1]) / denom : 0;
      return paired[index - 1].coord + frac * (paired[index].coord - paired[index - 1].coord);
    }
    return paired[paired.length - 1].coord;
  };

  const lowerStart = Math.max(0, peakArea - target);
  const upperStart = Math.min(peakArea, total - target);
  const candidates = new Set([lowerStart, upperStart, 0, Math.max(0, total - target)]);
  for (const area of cdf) {
    candidates.add(area);
    candidates.add(area - target);
  }

  let best = null;
  for (const rawStart of candidates) {
    const start = Math.min(Math.max(rawStart, lowerStart), upperStart);
    const end = start + target;
    if (start - 1e-12 > peakArea || end + 1e-12 < peakArea) continue;
    const loCoord = coordAtArea(start);
    const hiCoord = coordAtArea(end);
    if (!Number.isFinite(loCoord) || !Number.isFinite(hiCoord) || hiCoord <= loCoord) continue;
    const width = hiCoord - loCoord;
    if (!best || width < best.width) best = { loCoord, hiCoord, width };
  }
  if (!best) return null;
  const lo = perLogAge ? 10 ** best.loCoord : best.loCoord;
  const hi = perLogAge ? 10 ** best.hiCoord : best.hiCoord;
  return Number.isFinite(lo) && Number.isFinite(hi) && hi > lo ? { lo, hi } : null;
}

function mocaFlowsCurveDisplayStats(panel, options = {}) {
  const perLogAge = Boolean(options.perLogAge);
  const age = panel?.curve?.age_myr || [];
  const pdf = panel?.curve?.pdf_age || [];
  const paired = [];
  for (let index = 0; index < age.length; index += 1) {
    const ageValue = asNumber(age[index]);
    const yValue = mocaFlowsDisplayedPdfValue(ageValue, pdf[index], perLogAge);
    if (!Number.isFinite(ageValue) || ageValue <= 0 || !Number.isFinite(yValue) || yValue < 0) continue;
    paired.push({
      age: ageValue,
      coord: perLogAge ? Math.log10(ageValue) : ageValue,
      density: yValue,
    });
  }
  if (paired.length < 2) return null;
  paired.sort((a, b) => a.coord - b.coord);
  let peak = null;
  let peakDensity = -Infinity;
  let peakIndex = -1;
  for (let index = 0; index < paired.length; index += 1) {
    const row = paired[index];
    if (row.density > peakDensity) {
      peakDensity = row.density;
      peak = row.age;
      peakIndex = index;
    }
  }
  const cdf = [0];
  for (let index = 1; index < paired.length; index += 1) {
    const dx = paired[index].coord - paired[index - 1].coord;
    const area = dx > 0 ? 0.5 * (paired[index].density + paired[index - 1].density) * dx : 0;
    cdf.push(cdf[cdf.length - 1] + area);
  }
  const total = cdf[cdf.length - 1];
  let meanNumerator = 0;
  for (let index = 1; index < paired.length; index += 1) {
    const dx = paired[index].coord - paired[index - 1].coord;
    if (dx <= 0) continue;
    meanNumerator += 0.5 * (
      paired[index].age * paired[index].density
      + paired[index - 1].age * paired[index - 1].density
    ) * dx;
  }
  const quantile = (probability) => {
    if (!Number.isFinite(total) || total <= 0) return null;
    const target = probability * total;
    for (let index = 1; index < cdf.length; index += 1) {
      if (cdf[index] < target) continue;
      const denom = cdf[index] - cdf[index - 1];
      const frac = denom > 0 ? (target - cdf[index - 1]) / denom : 0;
      const coord = paired[index - 1].coord + frac * (paired[index].coord - paired[index - 1].coord);
      return perLogAge ? 10 ** coord : coord;
    }
    return paired[paired.length - 1].age;
  };
  const lo = quantile(0.16);
  const median = quantile(0.5);
  const hi = quantile(0.84);
  const peakInterval = mocaFlowsPeakContainingInterval(paired, cdf, total, peakIndex, perLogAge, 0.68);
  return {
    peak: Number.isFinite(peak) && peak > 0 && peakDensity > 0 ? peak : null,
    lo: Number.isFinite(lo) && lo > 0 ? lo : null,
    median: Number.isFinite(median) && median > 0 ? median : null,
    mean: Number.isFinite(meanNumerator) && Number.isFinite(total) && total > 0 ? meanNumerator / total : null,
    hi: Number.isFinite(hi) && hi > 0 ? hi : null,
    bandLo: Number.isFinite(peakInterval?.lo) && peakInterval.lo > 0 ? peakInterval.lo : null,
    bandHi: Number.isFinite(peakInterval?.hi) && peakInterval.hi > 0 ? peakInterval.hi : null,
  };
}

function mocaFlowsMetaDisplayStats(panel) {
  const meta = panel?.metadata || panel?.curve?.metadata || {};
  const peak = asNumber(meta.peak_age_myr);
  const lo = asNumber(meta.age_lo_myr);
  const hi = asNumber(meta.age_hi_myr);
  return {
    peak: Number.isFinite(peak) && peak > 0 ? peak : null,
    lo: Number.isFinite(lo) && lo > 0 ? lo : null,
    median: Number.isFinite(peak) && peak > 0 ? peak : null,
    mean: null,
    hi: Number.isFinite(hi) && hi > 0 ? hi : null,
    bandLo: Number.isFinite(lo) && lo > 0 ? lo : null,
    bandHi: Number.isFinite(hi) && hi > 0 ? hi : null,
  };
}

function mocaFlowsPanelDisplayStats(panel, options = {}) {
  return mocaFlowsCurveDisplayStats(panel, options) || mocaFlowsMetaDisplayStats(panel);
}

function renderMocaFlowsMap(plot, panel, payload) {
  const map = panel.map || {};
  const ageRange = mflowsEl["mflows-fixed-xrange"].checked
    ? mocaFlowsFixedAgeRange(payload, map.age_myr || [], { log: true })
    : mocaFlowsDynamicAgeRangeFromValues(map.age_myr || [], { log: true });
  const tickOptions = ageRange
    ? mocaFlowsLogTickOptions(ageRange, map.age_myr || [], mflowsEl["mflows-compact"].checked)
    : {};
  const trace = {
    x: map.age_myr || [],
    y: map.feh || [],
    z: map.density || [],
    type: "heatmap",
    colorscale: [
      [0, "#f7fbff"],
      [0.25, "#deebf7"],
      [0.5, "#9ecae1"],
      [0.75, "#3182bd"],
      [1, "#08306b"],
    ],
    colorbar: { title: map.z_label || "Density", thickness: 10 },
    hovertemplate: "Age: %{x:.4g} Myr<br>[Fe/H]: %{y:.3f}<br>Density: %{z:.4g}<extra></extra>",
  };
  const metallicity = payload?.metallicity?.dbMeasurement || null;
  const shapes = [
    ...mocaFlowsFullForwardAgeShapes(payload, panel, "above", { perLogAge: true }),
    ...mocaFlowsAdoptedAgeShapes(payload, "above"),
    ...mocaFlowsFehShapes(metallicity, "above"),
  ];
  const layout = {
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    margin: { l: 54, r: 14, t: 8, b: 46 },
    showlegend: false,
    shapes,
    xaxis: {
      title: { text: "Age (Myr)", font: { size: 12 } },
      type: "log",
      showline: true,
      linewidth: 1.3,
      linecolor: "#444444",
      mirror: true,
      ticks: "outside",
      showgrid: true,
      gridcolor: "rgba(0,0,0,0.10)",
      zeroline: false,
      range: ageRange,
      ...tickOptions,
    },
    yaxis: {
      title: { text: "[Fe/H]", font: { size: 12 } },
      showline: true,
      linewidth: 1.3,
      linecolor: "#444444",
      mirror: true,
      ticks: "outside",
      showgrid: true,
      gridcolor: "rgba(0,0,0,0.10)",
      zeroline: false,
    },
  };
  Plotly.react(plot, [trace], layout, mocaFlowsPlotConfig(`${panel.result_key || "mocaflows"}_age_feh`));
}

function mocaFlowsCurveMarkerShapes(panel, layer = "below", options = {}) {
  const stats = mocaFlowsPanelDisplayStats(panel, options);
  const average = stats?.mean;
  const lo = stats?.lo;
  const hi = stats?.hi;
  const shapes = [];
  if (Number.isFinite(lo) && Number.isFinite(hi) && hi > lo) {
    shapes.push({
      type: "rect",
      xref: "x",
      yref: "paper",
      x0: lo,
      x1: hi,
      y0: 0,
      y1: 1,
      fillcolor: "rgba(229, 92, 86, 0.20)",
      line: { width: 0 },
      layer: "below",
    });
  }
  if (Number.isFinite(average) && average > 0) {
    shapes.push({
      type: "line",
      xref: "x",
      yref: "paper",
      x0: average,
      x1: average,
      y0: 0,
      y1: 1,
      line: { color: "#d33f49", width: 2.4 },
      layer,
    });
  }
  return shapes;
}

function mocaFlowsPanelPeakAge(panel, options = {}) {
  const stats = mocaFlowsPanelDisplayStats(panel, options);
  return Number.isFinite(stats?.peak) && stats.peak > 0 ? stats.peak : null;
}

function mocaFlowsPanelAverageAge(panel, options = {}) {
  const stats = mocaFlowsPanelDisplayStats(panel, options);
  return Number.isFinite(stats?.mean) && stats.mean > 0 ? stats.mean : null;
}

function isMocaFlowsFullForwardPanel(panel) {
  return mflowsFullForwardResultKeys.has(String(panel?.result_key || panel?.metadata?.result_key || ""));
}

function mocaFlowsFullForwardPanel(payload = mflowsState.payload) {
  const candidates = mocaFlowsVisiblePanels(payload).filter(isMocaFlowsFullForwardPanel);
  return candidates.find((panel) => String(panel?.result_key || "") === "full_forward_model") || candidates[0] || null;
}

function mocaFlowsFullForwardAge(payload = mflowsState.payload, options = {}) {
  const panel = mocaFlowsFullForwardPanel(payload);
  if (!panel) return null;
  const age = mocaFlowsPanelAverageAge(panel, options) ?? mocaFlowsPanelPeakAge(panel, options);
  return Number.isFinite(age) && age > 0 ? age : null;
}

function mocaFlowsFullForwardAgeShapes(payload, panel, layer = "above", options = {}) {
  const age = mocaFlowsFullForwardAge(payload, options);
  if (!Number.isFinite(age) || age <= 0) return [];
  return [{
    type: "line",
    xref: "x",
    yref: "paper",
    x0: age,
    x1: age,
    y0: 0,
    y1: 1,
    line: { color: "#7b3fb4", width: 2, dash: "dash" },
    layer,
  }];
}

function mocaFlowsAdoptedAgeShapes(payload, layer = "below") {
  const marker = normalizeAgeMarker(payload?.membershipAge || payload?.adoptedAge);
  if (!marker) return [];
  const shapes = [];
  if (Number.isFinite(marker.lower_myr) && Number.isFinite(marker.upper_myr) && marker.upper_myr > marker.lower_myr) {
    shapes.push({
      type: "rect",
      xref: "x",
      yref: "paper",
      x0: marker.lower_myr,
      x1: marker.upper_myr,
      y0: 0,
      y1: 1,
      fillcolor: "rgba(79, 168, 207, 0.11)",
      line: { width: 0 },
      layer: "below",
    });
  }
  shapes.push({
    type: "line",
    xref: "x",
    yref: "paper",
    x0: marker.value_myr,
    x1: marker.value_myr,
    y0: 0,
    y1: 1,
    line: { color: "#4fa8cf", width: 1.8 },
    layer,
  });
  return shapes;
}

function mocaFlowsMeasurementShapes(_payload, _layer = "below") {
  return [];
}

function mocaFlowsVisibleAgeMeasurements(payload) {
  const adopted = normalizeAgeMarker(payload?.membershipAge || payload?.adoptedAge);
  const adoptedAge = adopted?.value_myr;
  const markers = (payload?.ageMeasurements || [])
    .map(normalizeAgeMarker)
    .filter(Boolean)
    .filter((marker) => !marker.is_adopted)
    .filter((marker) => !isMocaFlowsModelAgeMarker(marker))
    .filter((marker) => !Number.isFinite(adoptedAge) || Math.abs(Math.log10(marker.value_myr / adoptedAge)) > 0.012)
    .sort((a, b) => a.value_myr - b.value_myr);
  const deduped = [];
  for (const marker of markers) {
    const previous = deduped[deduped.length - 1];
    if (previous && Math.abs(Math.log10(marker.value_myr / previous.value_myr)) < 0.018) continue;
    deduped.push(marker);
  }
  return deduped;
}

function isMocaFlowsModelAgeMarker(marker) {
  const text = [
    marker.method,
    marker.method_short,
    marker.origin,
    marker.reference_name,
    marker.reference_query,
    marker.comments,
    marker.quality_flag,
  ].filter(Boolean).join(" ").toLowerCase();
  return text.includes("moca_normalizing_flows")
    || text.includes("mocaflows")
    || text.includes("trueage scalar summary")
    || text.includes("calc_association_age_pdf_blobs")
    || text.includes("calc_object_age_pdf_blobs")
    || text.includes("quality_flag: model")
    || String(marker.quality_flag || "").toLowerCase() === "model";
}

function mocaFlowsFehShapes(metallicity, layer = "above") {
  const value = asNumber(metallicity?.value);
  if (!Number.isFinite(value)) return [];
  const lo = asNumber(metallicity.uncertainty_minus);
  const hi = asNumber(metallicity.uncertainty_plus);
  const shapes = [];
  if (Number.isFinite(lo) && Number.isFinite(hi) && lo > 0 && hi > 0) {
    shapes.push({
      type: "rect",
      xref: "paper",
      yref: "y",
      x0: 0,
      x1: 1,
      y0: value - lo,
      y1: value + hi,
      fillcolor: "rgba(86, 153, 87, 0.13)",
      line: { width: 0 },
      layer: "below",
    });
  }
  shapes.push({
    type: "line",
    xref: "paper",
    yref: "y",
    x0: 0,
    x1: 1,
    y0: value,
    y1: value,
    line: { color: "#3f8f4e", width: 1.8 },
    layer,
  });
  return shapes;
}

function mocaFlowsPdfYRange(values, logY = false) {
  const finite = values.filter((value) => Number.isFinite(value) && value >= 0);
  if (!finite.length) return [0, 1];
  finite.sort((a, b) => a - b);
  const maxY = finite[finite.length - 1];
  if (!(maxY > 0)) return [0, 1];
  const p99 = finite[Math.floor((finite.length - 1) * 0.99)];
  const robustMax = Math.max(p99, maxY * 0.72);
  const upper = Math.max(robustMax * 1.12, maxY * 1.02, 1e-12);
  if (!logY) return [0, upper];
  const positive = finite.filter((value) => value > 0);
  if (!positive.length) return undefined;
  const minPositive = positive[0];
  const p05 = positive[Math.floor((positive.length - 1) * 0.05)];
  const lower = Math.max(Math.min(p05, maxY * 1e-4, minPositive * 2), 1e-300);
  if (!(upper > lower)) return undefined;
  return [Math.log10(lower), Math.log10(upper)];
}

function mocaFlowsAgeAnnotations(_payload) {
  return [];
}

function mocaFlowsLogTickOptions(range, values, compact) {
  const valueRange = mocaFlowsLogRangeToValues(range, values);
  if (!valueRange) return {};
  const [xmin, xmax] = valueRange;
  if (!(xmax > xmin)) return {};
  const span = Math.log10(xmax) - Math.log10(xmin);
  let multipliers = span <= 1.1 ? [1, 1.5, 2, 3, 5, 7] : [1, 2, 3, 5];
  if (compact && span > 1.6) multipliers = [1, 3];
  const minDecade = Math.floor(Math.log10(xmin)) - 1;
  const maxDecade = Math.ceil(Math.log10(xmax)) + 1;
  const ticks = [];
  for (let decade = minDecade; decade <= maxDecade; decade += 1) {
    const base = 10 ** decade;
    for (const multiplier of multipliers) {
      const value = multiplier * base;
      if (value >= xmin * 0.999 && value <= xmax * 1.001) ticks.push(value);
    }
  }
  const maxTicks = compact ? 6 : 9;
  let selected = dedupeNumericTicks(ticks);
  if (selected.length > maxTicks) {
    selected = dedupeNumericTicks(ticks.filter((value) => {
      const decadeValue = Math.log10(value);
      return Math.abs(decadeValue - Math.round(decadeValue)) < 1e-8;
    }));
  }
  if (selected.length < 2) return {};
  return {
    tickmode: "array",
    tickvals: selected,
    ticktext: selected.map(formatAgeAxisTick),
  };
}

function mocaFlowsLogRangeToValues(range, values) {
  if (Array.isArray(range) && range.length >= 2 && range.every((value) => Number.isFinite(Number(value)))) {
    return [10 ** Number(range[0]), 10 ** Number(range[1])];
  }
  const finite = (values || []).map(Number).filter((value) => Number.isFinite(value) && value > 0);
  if (finite.length < 2) return null;
  return [Math.min(...finite), Math.max(...finite)];
}

function dedupeNumericTicks(values) {
  const sorted = values.filter((value) => Number.isFinite(value) && value > 0).sort((a, b) => a - b);
  const deduped = [];
  for (const value of sorted) {
    const previous = deduped[deduped.length - 1];
    if (previous && Math.abs(Math.log10(value / previous)) < 1e-5) continue;
    deduped.push(value);
  }
  return deduped;
}

function formatAgeAxisTick(value) {
  if (value >= 10000) return `${formatSig(value / 1000)}k`;
  if (value >= 1000) return `${Number(value / 1000).toPrecision(2).replace(/\.0+$/, "")}k`;
  if (value >= 100) return String(Math.round(value));
  if (value >= 10) return Number(value).toPrecision(2).replace(/\.0+$/, "");
  if (value >= 1) return Number(value).toPrecision(2).replace(/\.0+$/, "");
  return Number(value).toPrecision(1);
}

function mocaFlowsAgeRange(values, pdfValues, payload, panel) {
  if (mflowsEl["mflows-fixed-xrange"].checked) {
    const fixedRange = mocaFlowsFixedAgeRange(payload, values);
    if (fixedRange) return fixedRange;
  }
  const paired = [];
  for (let i = 0; i < values.length; i += 1) {
    const age = Number(values[i]);
    const pdf = Number(pdfValues[i]);
    if (Number.isFinite(age) && age > 0 && Number.isFinite(pdf) && pdf >= 0) {
      paired.push({ age, pdf });
    }
  }
  const fullAges = paired.map((row) => row.age);
  const fullMin = fullAges.length ? Math.min(...fullAges) : NaN;
  const fullMax = fullAges.length ? Math.max(...fullAges) : NaN;
  let ages = [...fullAges];
  const maxPdf = paired.length ? Math.max(...paired.map((row) => row.pdf)) : NaN;
  if (Number.isFinite(maxPdf) && maxPdf > 0 && Number.isFinite(fullMin) && Number.isFinite(fullMax) && fullMax > fullMin) {
    const support = paired.filter((row) => row.pdf >= maxPdf * 1e-5).map((row) => row.age);
    if (support.length >= 3) {
      const supportMin = Math.min(...support);
      const supportMax = Math.max(...support);
      const fullSpan = Math.log10(fullMax) - Math.log10(fullMin);
      const supportSpan = Math.log10(supportMax) - Math.log10(supportMin);
      if (supportSpan > 0 && supportSpan < fullSpan * 0.7) {
        ages = [...support];
        const marker = normalizeAgeMarker(payload?.membershipAge || payload?.adoptedAge);
        if (marker) {
          for (const value of [marker.value_myr, marker.lower_myr, marker.upper_myr]) {
            if (Number.isFinite(value) && value > 0) ages.push(value);
          }
        }
      }
    }
  }
  const meta = panel.metadata || panel.curve?.metadata || {};
  for (const value of [mocaFlowsPanelAverageAge(panel), mocaFlowsPanelPeakAge(panel), meta.age_lo_myr, meta.age_hi_myr]) {
    const number = asNumber(value);
    if (Number.isFinite(number) && number > 0) ages.push(number);
  }
  if (!isMocaFlowsFullForwardPanel(panel)) {
    const fullForwardAge = mocaFlowsFullForwardAge(payload, { perLogAge: mflowsEl["mflows-log-x"].checked });
    if (Number.isFinite(fullForwardAge) && fullForwardAge > 0) ages.push(fullForwardAge);
  }
  if (ages.length < 2) return undefined;
  const xmin = Math.min(...ages);
  const xmax = Math.max(...ages);
  if (!(xmax > xmin)) return undefined;
  if (mflowsEl["mflows-log-x"].checked) {
    const span = Math.max(0.12, Math.log10(xmax) - Math.log10(xmin));
    const pad = Math.max(0.06, 0.14 * span);
    const bounded = mocaFlowsBoundedDynamicAgeRange(10 ** (Math.log10(xmin) - pad), 10 ** (Math.log10(xmax) + pad));
    return bounded ? [Math.log10(bounded[0]), Math.log10(bounded[1])] : undefined;
  }
  const pad = 0.05 * (xmax - xmin);
  return mocaFlowsBoundedDynamicAgeRange(xmin - pad, xmax + pad);
}

function mocaFlowsDynamicAgeRangeFromValues(values = [], options = {}) {
  const finite = (values || []).map(Number).filter((value) => Number.isFinite(value) && value > 0);
  if (finite.length < 2) return undefined;
  const bounded = mocaFlowsBoundedDynamicAgeRange(Math.min(...finite), Math.max(...finite));
  if (!bounded) return undefined;
  const useLog = options.log ?? mflowsEl["mflows-log-x"]?.checked;
  return useLog ? [Math.log10(bounded[0]), Math.log10(bounded[1])] : bounded;
}

function mocaFlowsBoundedDynamicAgeRange(xminValue, xmaxValue) {
  const xmin = asNumber(xminValue);
  const xmax = asNumber(xmaxValue);
  if (!Number.isFinite(xmin) || !Number.isFinite(xmax)) return undefined;
  const boundedMin = Math.max(mflowsDynamicAgeMinMyr, xmin);
  const boundedMax = Math.min(mflowsDynamicAgeMaxMyr, xmax);
  return boundedMax > boundedMin ? [boundedMin, boundedMax] : undefined;
}

function mocaFlowsFixedAgeRange(payload, fallbackValues = [], options = {}) {
  const ages = [];
  const addAge = (value) => {
    const number = asNumber(value);
    if (Number.isFinite(number) && number > 0) ages.push(number);
  };
  const addAgeArray = (values) => {
    for (const value of values || []) addAge(value);
  };
  addAgeArray(fallbackValues);
  for (const panel of payload?.panels || []) {
    addAgeArray(panel?.curve?.age_myr);
    addAgeArray(panel?.map?.age_myr);
    const meta = panel?.metadata || panel?.curve?.metadata || {};
    for (const value of [mocaFlowsPanelAverageAge(panel), mocaFlowsPanelPeakAge(panel), meta.age_lo_myr, meta.age_hi_myr]) addAge(value);
  }
  const adopted = normalizeAgeMarker(payload?.membershipAge || payload?.adoptedAge);
  if (adopted) {
    for (const value of [adopted.value_myr, adopted.lower_myr, adopted.upper_myr]) addAge(value);
  }
  for (const marker of payload?.ageMeasurements || []) {
    const normalized = normalizeAgeMarker(marker);
    if (!normalized) continue;
    for (const value of [normalized.value_myr, normalized.lower_myr, normalized.upper_myr]) addAge(value);
  }
  if (ages.length < 2) return undefined;
  const xmin = Math.min(...ages);
  const xmax = Math.max(...ages);
  if (!(xmax > xmin)) return undefined;
  const useLog = options.log ?? mflowsEl["mflows-log-x"].checked;
  if (useLog) return [Math.log10(xmin), Math.log10(xmax)];
  return [xmin, xmax];
}

function mocaFlowsPanelInfoHtml(panel, payload) {
  const meta = panel.metadata || {};
  const perLogAge = Boolean(mflowsEl["mflows-log-x"].checked);
  const stats = mocaFlowsPanelDisplayStats(panel, { perLogAge });
  const lines = [];
  pushInfo(lines, "contributors", meta.n_contributors);
  pushInfo(lines, "PDF average age", pdfAverageAgeText(stats));
  const ageText = ageSummaryText(stats) || ageSummaryText(meta);
  pushInfo(lines, "PDF median age", ageText);
  const metadataJson = panel.curve?.metadata?.metadata_json;
  const hbmStack = isMocaFlowsHbmStack(payload);
  if (metadataJson && typeof metadataJson === "object") {
    if (hbmStack) {
      pushInfo(lines, "HBM outliers", mocaFlowsHbmOutlierText(panel, metadataJson));
      pushInfo(lines, "HBM diagnostics", mocaFlowsHbmDiagnosticsText(metadataJson));
    } else {
      pushInfo(lines, "min p_inlier", metadataJson.min_p_inlier);
      pushInfo(lines, "N(p<0.50)", metadataJson.n_p_lt_0p50);
      pushInfo(lines, "N(p<0.90)", metadataJson.n_p_lt_0p90);
    }
  } else if (hbmStack) {
    pushInfo(lines, "HBM outliers", "not stored");
  }
  pushInfo(lines, "method", meta.calculation_method);
  return lines.length ? lines.join("") : "<div>No panel metadata</div>";
}

function renderMocaFlowsRunMetadata(payload) {
  const box = mflowsEl["mflows-run-metadata"];
  if (!box) return;
  const panels = payload?.panels || [];
  if (!panels.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  const rows = mocaFlowsRunMetadataRows(panels);
  if (!rows.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  box.hidden = false;
  box.innerHTML = [
    `<h2>MOCAFlows run metadata</h2>`,
    `<div class="mflows-run-metadata-grid">`,
    rows.map((row) => [
      `<article class="mflows-run-metadata-item">`,
      `<h3>${row.titleHtml}</h3>`,
      `<div class="mflows-run-metadata-fields">`,
      mocaFlowsRunMetadataFieldHtml("result key", row.resultKey),
      mocaFlowsRunMetadataFieldHtml("method", row.method),
      mocaFlowsRunMetadataFieldHtml("age row", row.ageRowId),
      mocaFlowsRunMetadataFieldHtml("model version", row.modelVersion),
      mocaFlowsRunMetadataFieldHtml("created", row.created),
      mocaFlowsRunMetadataFieldHtml("modified", row.modified),
      `</div>`,
      `<div class="mflows-run-metadata-comments"><strong>comments</strong><span>${escapeHtml(row.comments || "No comments stored")}</span></div>`,
      `</article>`,
    ].join("")).join(""),
    `</div>`,
  ].join("");
}

function mocaFlowsRunMetadataRows(panels) {
  const rows = [];
  const seen = new Set();
  for (const panel of panels || []) {
    const meta = panel?.metadata || {};
    const curveMeta = panel?.curve?.metadata || {};
    const summary = panel?.curve?.summary || {};
    const comments = mocaFlowsPanelRunComments(panel);
    const row = {
      titleHtml: mocaFlowsPanelTitleHtml(panel),
      resultKey: panel?.result_key || meta.result_key || curveMeta.result_key || "",
      method: meta.calculation_method || curveMeta.calculation_method || summary.calculation_method || "",
      ageRowId: meta.age_row_id || curveMeta.age_row_id || curveMeta.age_id || "",
      modelVersion: mocaFlowsPanelModelVersion(panel).label,
      created: formatMocaFlowsTimestamp(meta.created_timestamp || curveMeta.created_timestamp),
      modified: formatMocaFlowsTimestamp(meta.modified_timestamp || curveMeta.modified_timestamp),
      comments,
    };
    const key = [
      row.resultKey,
      row.method,
      row.ageRowId,
      row.created,
      row.modified,
      row.comments,
    ].join("\u0001");
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push(row);
  }
  return rows;
}

function mocaFlowsPanelRunComments(panel) {
  const meta = panel?.metadata || {};
  const curveMeta = panel?.curve?.metadata || {};
  const summary = panel?.curve?.summary || {};
  for (const value of [meta.comments, curveMeta.comments, summary.comments]) {
    const text = String(value || "").trim();
    if (text) return text;
  }
  return "";
}

function mocaFlowsRunMetadataFieldHtml(label, value) {
  if (value === null || value === undefined || value === "") return "";
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function formatMocaFlowsTimestamp(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.replace("T", " ").replace(/\.\d+$/, "");
}

function isMocaFlowsHbmStack(payload) {
  const stackMode = payload?.selection?.stack_mode || mflowsEl["mflows-stack-mode"]?.value || "";
  return String(stackMode).toLowerCase() === "hbm";
}

function mocaFlowsHbmDiagnosticsText(metadataJson) {
  const parts = [];
  const minP = asNumber(metadataJson?.min_p_inlier);
  if (Number.isFinite(minP)) parts.push(`min p_inlier ${formatSig(minP)}`);
  for (const [label, key] of [
    ["N(p<0.50)", "n_p_lt_0p50"],
    ["N(p<0.90)", "n_p_lt_0p90"],
  ]) {
    const value = asNumber(metadataJson?.[key]);
    if (Number.isFinite(value)) parts.push(`${label} ${Math.round(value)}`);
  }
  return parts.join(" · ");
}

function mocaFlowsHbmOutlierText(panel, metadataJson) {
  const candidates = [
    ["n_hbm_outliers", "p_inlier < 0.50"],
    ["hbm_outliers", "p_inlier < 0.50"],
    ["n_outliers", "p_inlier < 0.50"],
    ["noutliers", "p_inlier < 0.50"],
    ["n_p_lt_0p50", "p_inlier < 0.50"],
    ["n_p_lt_0p5", "p_inlier < 0.50"],
    ["n_p_less_0p50", "p_inlier < 0.50"],
    ["n_p_inlier_lt_0p50", "p_inlier < 0.50"],
    ["n_p_lt_0p90", "p_inlier < 0.90"],
  ];
  for (const [key, label] of candidates) {
    const value = asNumber(metadataJson?.[key]);
    if (!Number.isFinite(value) || value < 0) continue;
    const count = Math.round(value);
    const contributors = asNumber(panel?.metadata?.n_contributors);
    const total = Number.isFinite(contributors) && contributors >= count ? ` / ${Math.round(contributors)}` : "";
    return `${count}${total} (${label})`;
  }
  return "not stored";
}

function pushInfo(lines, label, value) {
  if (value === null || value === undefined || value === "") return;
  pushInfoHtml(lines, label, escapeHtml(formatCell(value)));
}

function pushInfoHtml(lines, label, htmlValue) {
  if (htmlValue === null || htmlValue === undefined || htmlValue === "") return;
  lines.push([
    `<div class="mflows-info-row">`,
    `<span class="mflows-info-label">${escapeHtml(label)}</span>`,
    `<span class="mflows-info-value">${htmlValue}</span>`,
    `</div>`,
  ].join(""));
}

function pushMocaFlowsMetallicityInfo(lines, metallicity) {
  if (!metallicity) {
    pushInfo(lines, "M/H", "No M/H metadata");
    return;
  }
  const modeLabel = metallicity.label || metallicity.mode || "";
  const db = metallicity.dbMeasurement;
  if (metallicity.mode === "db" && !db) {
    pushInfoHtml(lines, "M/H", "No MOCAdb [M/H] measurement available");
    return;
  }
  if (metallicity.mode !== "db") {
    pushInfoHtml(lines, "M/H", escapeHtml(modeLabel));
    return;
  }
  pushInfoHtml(lines, "M/H", `${escapeHtml(modeLabel)}; ${mocaFlowsFehValueHtml(db)}`);
  const ref = mocaFlowsReferenceHtml(db);
  if (ref) pushInfoHtml(lines, "M/H ref", ref);
}

function mocaFlowsAgeMarkerHtml(marker) {
  const ref = mocaFlowsReferenceHtml(marker);
  const text = escapeHtml(ageMarkerText(marker));
  return ref ? `${text}; ${ref}` : text;
}

function mocaFlowsReferenceHtml(row) {
  const label = row?.reference_name || row?.reference_bibcode || row?.moca_pid || "";
  if (!label) return "";
  const url = row?.ads_url || "";
  if (!url) return escapeHtml(label);
  return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`;
}

function mocaFlowsFehValueHtml(feh) {
  return escapeHtml(mocaFlowsFehText(feh, false));
}

function mocaFlowsFehText(feh, html = false) {
  const value = asNumber(feh?.value);
  if (!Number.isFinite(value)) return "No DB measurement";
  const minus = asNumber(feh.uncertainty_minus);
  const plus = asNumber(feh.uncertainty_plus);
  const unc = Number.isFinite(minus) && Number.isFinite(plus)
    ? ` (+${formatSig(plus)}/-${formatSig(minus)})`
    : "";
  const text = `[M/H] = ${value >= 0 ? "+" : ""}${formatSig(value)}${unc} dex`;
  if (!html) return text;
  const ref = mocaFlowsReferenceHtml(feh);
  return ref ? `${escapeHtml(text)}; ${ref}` : escapeHtml(text);
}

function logAgeSummaryText(meta) {
  const center = asNumber(meta?.median ?? meta?.peak_age_myr);
  const lo = asNumber(meta?.lo ?? meta?.age_lo_myr);
  const hi = asNumber(meta?.hi ?? meta?.age_hi_myr);
  if (![center, lo, hi].every(Number.isFinite) || center <= 0 || lo <= 0 || hi <= 0) return "";
  const logPeak = Math.log10(center) + 6;
  const logHi = Math.log10(hi) + 6 - logPeak;
  const logLo = logPeak - (Math.log10(lo) + 6);
  return `${formatSig(logPeak)} +${formatSig(logHi)}/-${formatSig(logLo)}`;
}

function ageSummaryText(meta, options = {}) {
  const center = asNumber(meta?.median ?? meta?.peak_age_myr);
  const lo = asNumber(meta?.lo ?? meta?.age_lo_myr);
  const hi = asNumber(meta?.hi ?? meta?.age_hi_myr);
  return ageIntervalText(center, lo, hi, options);
}

function pdfAverageAgeText(stats) {
  const mean = asNumber(stats?.mean);
  if (!Number.isFinite(mean) || mean <= 0) return "";
  return ageIntervalText(mean, stats?.lo, stats?.hi);
}

function ageIntervalText(centerValue, lowerValue, upperValue, options = {}) {
  const center = asNumber(centerValue);
  if (!Number.isFinite(center) || center <= 0) return "";
  const lo = asNumber(lowerValue);
  const hi = asNumber(upperValue);
  const scale = ageUnitScale(center);
  const hasInterval = [lo, hi].every(Number.isFinite) && lo > 0 && hi > 0 && hi >= center && center >= lo;
  if (!hasInterval) return formatAgeScalar(center);
  const scaledCenter = center / scale.factor;
  const minus = (center - lo) / scale.factor;
  const plus = (hi - center) / scale.factor;
  const decimals = ageErrorDecimals(minus, plus);
  const valueText = `${formatAgeFixed(scaledCenter, decimals)} +${formatAgeFixed(plus, decimals)}/-${formatAgeFixed(minus, decimals)}`;
  if (options.parentheses) {
    return `${formatAgeFixed(scaledCenter, decimals)} (+${formatAgeFixed(plus, decimals)}/-${formatAgeFixed(minus, decimals)}) ${scale.unit}`;
  }
  return `${valueText} ${scale.unit}`;
}

function ageUnitScale(centerValue) {
  const center = Math.abs(asNumber(centerValue));
  return Number.isFinite(center) && center >= 1000
    ? { factor: 1000, unit: "Gyr" }
    : { factor: 1, unit: "Myr" };
}

function ageErrorDecimals(minus, plus) {
  const errors = [minus, plus].map((value) => Math.abs(asNumber(value))).filter(Number.isFinite);
  if (!errors.length) return 0;
  if (errors.every((value) => value >= 10)) return 0;
  return errors.some((value) => Math.abs(Math.round(value * 10) / 10 - Math.round(value)) > 1e-9) ? 1 : 0;
}

function formatAgeFixed(value, decimals) {
  const number = asNumber(value);
  if (!Number.isFinite(number)) return "";
  return number.toFixed(Math.max(0, Math.min(1, Number(decimals) || 0)));
}

function formatAgeScalar(value) {
  const number = asNumber(value);
  if (!Number.isFinite(number)) return "";
  const scale = ageUnitScale(number);
  const scaled = number / scale.factor;
  const rounded = Math.round(scaled * 10) / 10;
  const decimals = Math.abs(rounded - Math.round(rounded)) > 1e-9 ? 1 : 0;
  return `${formatAgeFixed(scaled, decimals)} ${scale.unit}`;
}

function updateMocaFlowsSummary() {
  const payload = mflowsState.payload;
  if (!payload) return;
  const target = mocaFlowsTargetLabel(payload);
  const allPanels = payload.panels || [];
  const panels = mocaFlowsVisiblePanels(payload);
  const maps = panels.filter((panel) => panel.map).length;
  const role = mocaFlowsCurveRoleLabel(payload.selection?.curve_role || mflowsEl["mflows-curve-role"].value);
  const panelCount = panels.length === allPanels.length ? `${panels.length} panels` : `${panels.length} of ${allPanels.length} panels`;
  mflowsEl["mflows-summary"].innerHTML = [
    `<strong>${escapeHtml(target)}</strong>`,
    panelCount,
    role,
    maps ? `${maps} age-[M/H] maps available` : "age-PDF panels",
  ].filter(Boolean).map(escapeMaybeHtml).join(" · ");
  mflowsEl["mflows-hint"].innerHTML = mocaFlowsTopInfoHtml(payload);
}

function mocaFlowsTopInfoHtml(payload) {
  const items = [];
  const metallicity = mocaFlowsTopMetallicityHtml(payload?.metallicity);
  if (metallicity) items.push(metallicity);
  const ageMarker = normalizeAgeMarker(payload?.membershipAge || payload?.adoptedAge);
  if (ageMarker) items.push(`<strong>adopted age:</strong> ${mocaFlowsAgeMarkerHtml(ageMarker)}`);
  if (isMocaFlowsHbmStack(payload)) {
    items.push("HBM stacking uses a Hierarchical Bayesian Model to combine member PDFs with an inlier/outlier mixture, down-weighting contributors that are inconsistent with the shared association age.");
  }
  const legend = mocaFlowsMarkerLegendHtml(payload);
  if (legend) items.push(legend);
  return items.join(" · ");
}

function mocaFlowsMarkerLegendHtml(payload) {
  const panels = mocaFlowsVisiblePanels(payload);
  const showAverage = panels.some((panel) => {
    const average = mocaFlowsPanelAverageAge(panel, { perLogAge: mflowsEl["mflows-log-x"]?.checked });
    return Number.isFinite(average) && average > 0;
  });
  const showAdopted = Boolean(normalizeAgeMarker(payload?.membershipAge || payload?.adoptedAge));
  const fullForwardAge = mocaFlowsFullForwardAge(payload, { perLogAge: mflowsEl["mflows-log-x"]?.checked });
  const showFullForward = panels.some((panel) => !isMocaFlowsFullForwardPanel(panel))
    && Number.isFinite(fullForwardAge)
    && fullForwardAge > 0;
  const items = [];
  if (showAverage) {
    items.push([
      `<span class="mflows-line-legend-item">`,
      `<span class="mflows-line-legend-swatch is-peak"></span>`,
      `<span>PDF average age</span>`,
      `</span>`,
    ].join(""));
  }
  if (showAdopted) {
    items.push([
      `<span class="mflows-line-legend-item">`,
      `<span class="mflows-line-legend-swatch is-adopted"></span>`,
      `<span>Adopted or membership age</span>`,
      `</span>`,
    ].join(""));
  }
  if (showFullForward) {
    items.push([
      `<span class="mflows-line-legend-item">`,
      `<span class="mflows-line-legend-swatch is-full-forward"></span>`,
      `<span>Full forward model age</span>`,
      `</span>`,
    ].join(""));
  }
  if (!items.length) return "";
  return `<span class="mflows-line-legend" aria-label="Line legend">${items.join(" ")}</span>`;
}

function mocaFlowsTopMetallicityHtml(metallicity) {
  if (!metallicity) return "";
  const modeLabel = metallicity.label || metallicity.mode || "";
  const db = metallicity.dbMeasurement;
  if (metallicity.mode === "db" && !db) {
    return `<strong>M/H:</strong> No MOCAdb [M/H] measurement available`;
  }
  if (metallicity.mode !== "db") {
    return modeLabel ? `<strong>M/H:</strong> ${escapeHtml(modeLabel)}` : "";
  }
  const ref = mocaFlowsReferenceHtml(db);
  return [
    `<strong>M/H:</strong> ${escapeHtml(modeLabel)}`,
    mocaFlowsFehValueHtml(db),
    ref,
  ].filter(Boolean).join("; ");
}

function renderMocaFlowsEmpty(message) {
  mflowsEl["mflows-panel-grid"].innerHTML = "";
  mflowsEl["mflows-empty"].textContent = message || "No MOCAFlows panels available for this target.";
  mflowsEl["mflows-empty"].hidden = false;
  mflowsEl["mflows-summary"].textContent = message || "No panels loaded";
  setMocaFlowsExportDisabled(true);
  setMocaFlowsLoading(false);
  setMocaFlowsStatus(message || "No MOCAFlows panels", "error");
}

function buildMocaFlowsParams() {
  const params = mocaFlowsApiParams();
  const scope = currentMocaFlowsScope();
  params.set("target", scope);
  if (scope === "association") {
    params.set("moca_aid", String(mflowsEl["mflows-aid-select"].value || mflowsDefaultAid).toUpperCase());
    params.set("stack_mode", mflowsEl["mflows-stack-mode"].value || "hbm");
  } else {
    params.set("moca_oid", parseInteger(mflowsEl["mflows-oid-input"].value) ?? mflowsDefaultOid);
  }
  params.set("mh_treatment", mflowsEl["mflows-mh-treatment"].value || "db");
  params.set("curve_role", normalizeMocaFlowsCurveRole(mflowsEl["mflows-curve-role"].value));
  return params;
}

function mocaFlowsApiParams() {
  const urlParams = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["mock", "host", "user", "username", "pwd", "password", "dbase", "db", "database", "port"]) {
    if (urlParams.has(key)) params.set(key, urlParams.get(key));
  }
  return params;
}

function updateMocaFlowsUrl() {
  const params = new URLSearchParams(window.location.search);
  const scope = currentMocaFlowsScope();
  params.set("target", scope);
  if (scope === "association") {
    params.delete("moca_oid");
    params.delete("oid");
    params.set("moca_aid", String(mflowsEl["mflows-aid-select"].value || mflowsDefaultAid).toUpperCase());
    params.set("stack_mode", mflowsEl["mflows-stack-mode"].value || "hbm");
  } else {
    params.delete("moca_aid");
    params.delete("aid");
    params.delete("stack_mode");
    params.set("moca_oid", parseInteger(mflowsEl["mflows-oid-input"].value) ?? mflowsDefaultOid);
  }
  params.set("mh_treatment", mflowsEl["mflows-mh-treatment"].value || "db");
  params.delete("posteriors");
  params.delete("posterior");
  params.delete("role");
  params.delete("pdf_role");
  params.delete("mocaflows_model_version");
  params.delete("mflows_model_version");
  params.set("curve_role", normalizeMocaFlowsCurveRole(mflowsEl["mflows-curve-role"].value));
  const modelVersionValue = mflowsEl["mflows-model-version"]?.value || mflowsState.requestedModelVersion || "";
  if (modelVersionValue) {
    params.set("model_version", modelVersionValue);
  } else {
    params.delete("model_version");
  }
  const checkbox = [];
  if (mflowsEl["mflows-log-x"].checked) checkbox.push("log_x");
  if (mflowsEl["mflows-log-y"].checked) checkbox.push("log_y");
  if (mflowsEl["mflows-compact"].checked) checkbox.push("compact");
  params.set("checkbox", checkbox.join(","));
  params.delete("measurements");
  params.delete("show_measurements");
  params.set("full_xrange", mflowsEl["mflows-fixed-xrange"].checked ? "1" : "0");
  const minStackedStars = Math.max(0, parseInteger(mflowsEl["mflows-min-stacked-stars"]?.value) ?? 0);
  if (minStackedStars > 0) {
    params.set("min_stacked", String(minStackedStars));
  } else {
    params.delete("min_stacked");
    params.delete("min_stacked_stars");
    params.delete("min_stars");
  }
  window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
}

function currentMocaFlowsScope() {
  return mflowsEl["mflows-scope-association"].checked ? "association" : "object";
}

function mocaFlowsTargetLabel(payload) {
  const selection = payload?.selection || {};
  const target = payload?.target || {};
  if ((selection.scope || currentMocaFlowsScope()) === "association") {
    const aid = target.moca_aid || selection.moca_aid || selection.target || mflowsEl["mflows-aid-select"].value || "association";
    return target.name ? `${aid}; ${target.name}` : String(aid);
  }
  const oid = selectedMocaFlowsObjectOid(payload);
  const designation = String(target.designation || "").trim();
  return designation ? `${designation} (moca_oid=${oid})` : `moca_oid=${oid || ""}`;
}

function selectedMocaFlowsObjectOid(payload = mflowsState.payload) {
  const selection = payload?.selection || {};
  const target = payload?.target || {};
  if ((selection.scope || currentMocaFlowsScope()) !== "object") return "";
  return normalizedMocaOid(target.moca_oid || selection.moca_oid || selection.target || mflowsEl["mflows-oid-input"].value);
}

function selectedMocaFlowsAssociationAid(payload = mflowsState.payload) {
  const selection = payload?.selection || {};
  const target = payload?.target || {};
  const aid = String(
    mflowsEl["mflows-aid-select"]?.value
      || target.moca_aid
      || selection.moca_aid
      || selection.target
      || "",
  ).trim().toUpperCase();
  return aid && aid !== "ASSOCIATION" ? aid : "";
}

function mocaFlowsReportUrl(payload = mflowsState.payload) {
  if (currentMocaFlowsScope() === "association") {
    const aid = selectedMocaFlowsAssociationAid(payload);
    return aid ? `https://mocadb.ca/search/results?search-query=${encodeURIComponent(aid)}&search-type=association` : "";
  }
  const oid = normalizedMocaOid(mflowsEl["mflows-oid-input"]?.value) || selectedMocaFlowsObjectOid(payload);
  return oid ? `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(oid)}%29&search-type=star` : "";
}

function openMocaFlowsReport() {
  const url = mocaFlowsReportUrl();
  if (!url) return;
  window.open(url, "_blank", "noopener");
}

function exportMocaFlowsCsv() {
  const rows = mocaFlowsVisiblePanels().map((panel) => {
    const meta = panel.metadata || {};
    const modelVersion = mocaFlowsPanelModelVersion(panel);
    return {
      result_key: panel.result_key,
      title: panel.title,
      curve_role: panel.curve_role || "",
      model_version: modelVersion.label,
      n_contributors: meta.n_contributors ?? "",
      peak_age_myr: meta.peak_age_myr ?? "",
      age_lo_myr: meta.age_lo_myr ?? "",
      age_hi_myr: meta.age_hi_myr ?? "",
      eps_mean: meta.eps_mean ?? "",
      calculation_method: meta.calculation_method ?? "",
      uses_db_feh: panel.uses_db_feh ? 1 : 0,
      has_map: panel.map ? 1 : 0,
      comments: mocaFlowsPanelCommentsText(panel),
    };
  });
  if (!rows.length) return;
  const columns = Object.keys(rows[0]);
  const csv = [columns.join(","), ...rows.map((row) => columns.map((column) => csvEscape(row[column])).join(","))].join("\n");
  downloadBlob(csv, "moca_flows_panels.csv", "text/csv;charset=utf-8");
}

async function clearMocaFlowsCache() {
  setMocaFlowsStatus("Clearing cache", "loading");
  try {
    await postJson("api/moca-flows/cache/clear", {});
    setMocaFlowsStatus("Cache cleared", "");
    await loadMocaFlowsData();
  } catch (error) {
    setMocaFlowsStatus(error.message || "Could not clear cache", "error");
  }
}

function resizeMocaFlowsPlots() {
  mflowsEl["mflows-panel-grid"].querySelectorAll(".mflows-panel-plot").forEach((plot) => {
    if (plot.data) Plotly.Plots.resize(plot);
  });
}

function scheduleMocaFlowsPlotResize() {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => resizeMocaFlowsPlots());
  });
}

function setMocaFlowsStatus(message, state) {
  mflowsEl["mflows-status"].textContent = message || "";
  mflowsEl["mflows-status"].classList.toggle("loading", state === "loading");
  mflowsEl["mflows-status"].classList.toggle("error", state === "error");
}

function setMocaFlowsLoading(isLoading) {
  mflowsEl["mflows-load"].disabled = Boolean(isLoading);
  mflowsEl["mflows-panel-grid"].classList.toggle("is-loading", Boolean(isLoading));
  mflowsEl["mflows-panel-grid"].querySelectorAll(".mflows-panel").forEach((panel) => {
    panel.setAttribute("aria-busy", isLoading ? "true" : "false");
  });
}

function setMocaFlowsExportDisabled(disabled) {
  mflowsEl["mflows-export-csv"].disabled = Boolean(disabled);
  mflowsEl["mflows-open-report"].disabled = !mocaFlowsReportUrl();
}

async function fetchJsonUrl(url) {
  const response = await fetch(url);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function postJson(path, body) {
  const response = await fetch(mflowsAppUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function mocaFlowsPlotConfig(filename) {
  return {
    displaylogo: false,
    displayModeBar: false,
    responsive: true,
    toImageButtonOptions: {
      format: "png",
      filename: `moca_flows_${filename}`,
      height: 620,
      width: 880,
      scale: 2,
    },
  };
}

function normalizeAgeMarker(raw) {
  if (!raw) return null;
  const value = asNumber(raw.value_myr);
  if (!Number.isFinite(value) || value <= 0) return null;
  const minus = asNumber(raw.uncertainty_minus_myr);
  const plus = asNumber(raw.uncertainty_plus_myr);
  return {
    ...raw,
    value_myr: value,
    lower_myr: asNumber(raw.lower_myr) ?? (Number.isFinite(minus) ? Math.max(1e-6, value - minus) : value),
    upper_myr: asNumber(raw.upper_myr) ?? (Number.isFinite(plus) ? value + plus : value),
    uncertainty_minus_myr: minus,
    uncertainty_plus_myr: plus,
  };
}

function ageMarkerText(marker) {
  const value = asNumber(marker.value_myr);
  const minus = asNumber(marker.uncertainty_minus_myr);
  const plus = asNumber(marker.uncertainty_plus_myr);
  if (Number.isFinite(value) && Number.isFinite(minus) && Number.isFinite(plus)) {
    return ageIntervalText(value, value - minus, value + plus, { parentheses: true });
  }
  return formatAgeScalar(value);
}

function parseCsv(value, fallback = []) {
  if (!value) return [...fallback];
  return String(value).split(",").map((item) => item.trim()).filter(Boolean);
}

function normalizeMocaFlowsCurveRole(value) {
  const role = String(value || "").trim().toLowerCase();
  if (role === "posterior" || role === "posteriors") return "posterior";
  if (role === "prior" || role === "priors") return "prior";
  return "likelihood";
}

function mocaFlowsCurveRoleLabel(value) {
  const role = normalizeMocaFlowsCurveRole(value);
  return {
    likelihood: "Likelihood",
    prior: "Prior",
    posterior: "Posterior",
  }[role];
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function asNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function parseInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizedMocaOid(oid) {
  const number = Number(oid);
  return Number.isFinite(number) && number > 0 ? number.toFixed(0) : "";
}

function formatCell(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toPrecision(6);
  return String(value);
}

function formatSig(value) {
  if (!Number.isFinite(value)) return "";
  return Number(value).toPrecision(3).replace(/\.0+$/, "");
}

function csvEscape(value) {
  const text = formatCell(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
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

function escapeMaybeHtml(value) {
  return String(value || "");
}

function stripHtml(value) {
  const div = document.createElement("div");
  div.innerHTML = value;
  return div.textContent || div.innerText || "";
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function debounce(fn, delay) {
  let timeout = null;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}
