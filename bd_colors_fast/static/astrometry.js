const atmDefaultOid = 602;
const atmMissionColors = ["#377EB8", "#E41A1C", "#4DAF4A", "#984EA3", "#FF7F00", "#A65628", "#F781BF", "#999999", "#66C2A5", "#FC8D62"];
const atmBinSizeDays = 50;
const atmPhaseBinSizeDays = 20;

const atmState = {
  selectedOid: null,
  selectedTargetLabel: "",
  payload: null,
  selectedMissions: new Set(),
  selectedIds: new Set(),
  manualRejectedIds: new Set(),
  processedRows: [],
  searchTimer: null,
  hasUserMissionChoice: false,
  initialMissions: [],
  fitResult: null,
  fitBusy: false,
  pushBusy: false,
  fitCapabilities: null,
  authContext: null,
  lastPrepared: null,
  pushFitSignature: "",
};

const atmEl = {};

document.addEventListener("DOMContentLoaded", initAstrometry);

const atmAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function atmAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), atmAppBaseUrl).toString();
}

async function initAstrometry() {
  collectAstrometryElements();
  readAstrometryUrlState();
  bindAstrometryControls();
  await initializeAstrometryFitContext();
  updateAstrometryManagementVisibility();
  if (atmState.selectedOid === null) atmState.selectedOid = atmDefaultOid;
  atmEl["atm-target-search"].value = `oid${atmState.selectedOid}`;
  await searchAstrometryTargets("", { selectedOid: atmState.selectedOid, quiet: true });
  await loadAstrometryObject();
}

function collectAstrometryElements() {
  [
    "atm-status",
    "atm-target-search",
    "atm-target-results",
    "atm-selected-target-text",
    "atm-clear-target",
    "atm-open-report",
    "atm-missions-all",
    "atm-missions-none",
    "atm-mission-list",
    "atm-subtract-pm",
    "atm-subtract-plx",
    "atm-phase-yearly",
    "atm-bin",
    "atm-display-absolute",
    "atm-display-merged",
    "atm-display-reference",
    "atm-adjust-reference",
    "atm-only-recalibrated",
    "atm-revert-raw",
    "atm-fit-method",
    "atm-fit-outlier-mixture",
    "atm-fit-method-note",
    "atm-reject-selected-fit",
    "atm-reset-manual-rejections",
    "atm-manual-rejection-note",
    "atm-fit-pm",
    "atm-fit-plx",
    "atm-clear-fit",
    "atm-fit-summary",
    "atm-management-tools",
    "atm-push-coordinate",
    "atm-push-pm",
    "atm-push-parallax",
    "atm-push-moca-pid",
    "atm-push-origin",
    "atm-push-comments",
    "atm-push-is-public",
    "atm-push-rls",
    "atm-push-allow-duplicate",
    "atm-push-preview",
    "atm-push-apply",
    "atm-push-status",
    "atm-ra-plot",
    "atm-dec-plot",
    "atm-plot-loader",
    "atm-summary",
    "atm-export-csv",
    "atm-export-tsv",
    "atm-export-fits",
    "atm-export-votable",
    "atm-clear-cache-bottom",
    "atm-clear-cache-status",
    "atm-table-title",
    "atm-table-subtitle",
    "atm-table",
  ].forEach((id) => {
    atmEl[id] = document.getElementById(id);
  });
}

function readAstrometryUrlState() {
  const params = new URLSearchParams(window.location.search);
  atmState.selectedOid = parseInteger(params.get("moca_oid") || params.get("oid"));
  atmState.initialMissions = (params.get("missions") || "").split(",").map((item) => item.trim()).filter(Boolean);
  atmEl["atm-subtract-pm"].checked = asBool(params.get("subtract_pm"));
  atmEl["atm-subtract-plx"].checked = asBool(params.get("subtract_plx"));
  atmEl["atm-phase-yearly"].checked = asBool(params.get("phase"));
  atmEl["atm-bin"].checked = asBool(params.get("bin"));
  atmEl["atm-display-absolute"].checked = asBool(params.get("display_absolute"));
  atmEl["atm-display-merged"].checked = asBool(params.get("display_merged"));
  atmEl["atm-display-reference"].checked = !asFalse(params.get("display_reference"));
  atmEl["atm-adjust-reference"].checked = !asFalse(params.get("adjust_ref"));
  atmEl["atm-only-recalibrated"].checked = !asFalse(params.get("only_recalibrated"));
  atmEl["atm-revert-raw"].checked = asBool(params.get("revert_raw"));
  if (atmEl["atm-fit-method"]) {
    const method = String(params.get("fit_method") || params.get("fitter") || "scipy").toLowerCase();
    atmEl["atm-fit-method"].value = method === "ultranest" ? "ultranest" : "scipy";
  }
  if (atmEl["atm-fit-outlier-mixture"]) {
    const outlierParam = params.has("fit_outlier_mixture")
      ? params.get("fit_outlier_mixture")
      : params.get("outlier_mixture");
    atmEl["atm-fit-outlier-mixture"].checked = !asFalse(outlierParam);
  }
}

function bindAstrometryControls() {
  atmEl["atm-target-search"].addEventListener("input", () => {
    const value = atmEl["atm-target-search"].value.trim();
    clearTimeout(atmState.searchTimer);
    atmState.searchTimer = setTimeout(() => searchAstrometryTargets(value), 250);
  });
  atmEl["atm-target-search"].addEventListener("focus", () => {
    const value = atmEl["atm-target-search"].value.trim();
    if (value) searchAstrometryTargets(value);
  });
  document.addEventListener("click", (event) => {
    if (!atmEl["atm-target-results"].contains(event.target) && event.target !== atmEl["atm-target-search"]) {
      atmEl["atm-target-results"].hidden = true;
    }
  });
  atmEl["atm-clear-target"].addEventListener("click", () => {
    atmState.selectedOid = null;
    atmState.selectedTargetLabel = "";
    atmState.payload = null;
    atmState.selectedIds.clear();
    clearAstrometryFit({ render: false });
    atmEl["atm-target-search"].value = "";
    updateSelectedTargetDisplay();
    updateAstrometryUrl();
    renderEmptyAstrometry("Select a target");
    atmEl["atm-target-search"].focus();
  });
  atmEl["atm-open-report"].addEventListener("click", () => {
    openMocaReport(currentAstrometryReportOid());
  });
  atmEl["atm-missions-all"].addEventListener("click", () => {
    atmState.selectedMissions = new Set((atmState.payload?.missions || []).map((row) => row.value));
    atmState.hasUserMissionChoice = true;
    clearAstrometryFit({ render: false });
    renderMissionList();
    renderAstrometry();
    updateAstrometryUrl();
  });
  atmEl["atm-missions-none"].addEventListener("click", () => {
    atmState.selectedMissions.clear();
    atmState.hasUserMissionChoice = true;
    clearAstrometryFit({ render: false });
    renderMissionList();
    renderAstrometry();
    updateAstrometryUrl();
  });
  for (const id of ["atm-subtract-pm", "atm-subtract-plx", "atm-phase-yearly", "atm-bin", "atm-display-absolute", "atm-display-reference"]) {
    atmEl[id].addEventListener("change", () => {
      renderAstrometry();
      updateAstrometryUrl();
    });
  }
  for (const id of ["atm-adjust-reference", "atm-only-recalibrated", "atm-revert-raw"]) {
    atmEl[id].addEventListener("change", () => {
      clearAstrometryFit({ render: false });
      renderAstrometry();
      updateAstrometryUrl();
    });
  }
  atmEl["atm-display-merged"].addEventListener("change", async () => {
    const availableMissions = (atmState.payload?.missions || []).map((row) => row.value);
    const hadAllMissionsSelected = availableMissions.length > 0 && availableMissions.every((mission) => atmState.selectedMissions.has(mission));
    if (hadAllMissionsSelected) atmState.hasUserMissionChoice = false;
    atmState.selectedIds.clear();
    clearAstrometryFit({ render: false });
    updateAstrometryUrl();
    await loadAstrometryObject();
  });
  for (const id of ["atm-fit-method", "atm-fit-outlier-mixture"]) {
    if (!atmEl[id]) continue;
    atmEl[id].addEventListener("change", () => {
      clearAstrometryFit({ render: false });
      updateAstrometryFitControlState();
      renderAstrometry();
      updateAstrometryUrl();
    });
  }
  atmEl["atm-fit-pm"].addEventListener("click", () => runAstrometryFit("pm"));
  atmEl["atm-fit-plx"].addEventListener("click", () => runAstrometryFit("pm_plx"));
  if (atmEl["atm-reject-selected-fit"]) atmEl["atm-reject-selected-fit"].addEventListener("click", addSelectedAstrometryFitRejections);
  if (atmEl["atm-reset-manual-rejections"]) atmEl["atm-reset-manual-rejections"].addEventListener("click", clearManualAstrometryFitRejections);
  atmEl["atm-clear-fit"].addEventListener("click", () => {
    clearAstrometryFit({ render: false });
    renderAstrometry();
  });
  for (const id of ["atm-push-coordinate", "atm-push-pm", "atm-push-parallax", "atm-push-moca-pid", "atm-push-origin", "atm-push-comments", "atm-push-rls", "atm-push-allow-duplicate"]) {
    if (!atmEl[id]) continue;
    atmEl[id].addEventListener("input", updateAstrometryPushControls);
    atmEl[id].addEventListener("change", updateAstrometryPushControls);
  }
  if (atmEl["atm-push-is-public"]) {
    atmEl["atm-push-is-public"].addEventListener("change", () => {
      syncAstrometryPushRls();
      updateAstrometryPushControls();
    });
  }
  if (atmEl["atm-push-preview"]) atmEl["atm-push-preview"].addEventListener("click", () => runAstrometryPush(true));
  if (atmEl["atm-push-apply"]) atmEl["atm-push-apply"].addEventListener("click", () => runAstrometryPush(false));
  atmEl["atm-export-csv"].addEventListener("click", () => exportAstrometry("csv"));
  atmEl["atm-export-tsv"].addEventListener("click", () => exportAstrometry("tsv"));
  atmEl["atm-export-fits"].addEventListener("click", () => exportAstrometry("fits"));
  atmEl["atm-export-votable"].addEventListener("click", () => exportAstrometry("votable"));
  atmEl["atm-clear-cache-bottom"].addEventListener("click", clearAstrometryCache);
  window.addEventListener("resize", debounce(() => {
    if (!atmEl["atm-target-results"].hidden) positionAstrometrySearchPopup();
    if (atmState.payload) renderAstrometry();
  }, 150));
}

async function initializeAstrometryFitContext() {
  if (window.MocaAuthContext?.ready) {
    try {
      atmState.authContext = await window.MocaAuthContext.ready;
    } catch (error) {
      atmState.authContext = window.MocaAuthContext.current || null;
    }
  }
  try {
    const payload = await fetchAstrometryJson("api/astrometry/fit/capabilities");
    if (payload?.ok) {
      atmState.fitCapabilities = payload;
      atmState.authContext = payload.auth || atmState.authContext;
    }
  } catch (error) {
    atmState.fitCapabilities = null;
  }
  updateAstrometryFitControlState();
  updateAstrometryManagementVisibility();
}

function updateAstrometryFitControlState() {
  const select = atmEl["atm-fit-method"];
  if (!select) return;
  const fitters = atmState.fitCapabilities?.fitters || {};
  const ultranest = fitters.ultranest || {};
  const ultraOption = select.querySelector('option[value="ultranest"]');
  if (ultraOption) {
    const enabled = ultranest.enabled !== false && ultranest.available !== false;
    ultraOption.disabled = !enabled;
    ultraOption.textContent = enabled ? "UltraNest" : "UltraNest (unavailable)";
    ultraOption.title = ultranest.message || "";
    if (select.value === "ultranest" && !enabled) select.value = "scipy";
  }
  select.disabled = Boolean(atmState.fitBusy);
  if (atmEl["atm-fit-outlier-mixture"]) atmEl["atm-fit-outlier-mixture"].disabled = Boolean(atmState.fitBusy);
  if (atmEl["atm-fit-method-note"]) {
    const note = select.value === "ultranest"
      ? ultranest.message || "UltraNest fits run on the server and can be slow."
      : "";
    atmEl["atm-fit-method-note"].textContent = note;
  }
  updateManualAstrometryRejectionControls();
  updateAstrometryPushControls();
}

function astrometryManagementAllowed() {
  const params = new URLSearchParams(window.location.search);
  if (asBool(params.get("mock"))) return false;
  const auth = atmState.authContext || {};
  const role = String(auth.role || "").trim().toLowerCase();
  const privateDb = Boolean(auth.private_db ?? auth.privateDb);
  return role === "management" && privateDb;
}

function updateAstrometryManagementVisibility() {
  if (!atmEl["atm-management-tools"]) return;
  const visible = astrometryManagementAllowed();
  atmEl["atm-management-tools"].hidden = !visible;
  if (visible) {
    syncAstrometryPushDefaults();
    syncAstrometryPushRls();
    updateAstrometryPushControls();
  }
}

function astrometryPushFitSignature() {
  const fit = atmState.fitResult;
  if (!fit) return "";
  return [
    fit.mode || "",
    fit.fitter || "",
    fit.outlierMixture ? "outliers" : "plain",
    finite(fit.t0) ? Number(fit.t0).toFixed(8) : "",
    finite(fit.pmra) ? Number(fit.pmra).toFixed(8) : "",
    finite(fit.pmdec) ? Number(fit.pmdec).toFixed(8) : "",
    finite(fit.plx) ? Number(fit.plx).toFixed(8) : "",
  ].join("|");
}

function astrometryDefaultPushOrigin(fit = atmState.fitResult) {
  const mode = fit?.mode === "pm_plx" ? "pm_plx" : "pm";
  const suffix = String(fit?.fitter || "").toLowerCase() === "ultranest" ? "_ultranest" : "";
  return `mocaviz_astrometry_${mode}_fit${suffix}`;
}

function syncAstrometryPushDefaults() {
  if (!atmEl["atm-management-tools"] || atmEl["atm-management-tools"].hidden) return;
  const signature = astrometryPushFitSignature();
  if (signature === atmState.pushFitSignature) return;
  atmState.pushFitSignature = signature;
  const fit = atmState.fitResult;
  if (atmEl["atm-push-coordinate"]) atmEl["atm-push-coordinate"].checked = Boolean(fit);
  if (atmEl["atm-push-pm"]) atmEl["atm-push-pm"].checked = Boolean(fit);
  if (atmEl["atm-push-parallax"]) atmEl["atm-push-parallax"].checked = Boolean(fit && fit.mode === "pm_plx");
  const origin = fit ? astrometryDefaultPushOrigin(fit) : "";
  if (atmEl["atm-push-origin"]) atmEl["atm-push-origin"].value = origin;
  if (atmEl["atm-push-comments"]) {
    atmEl["atm-push-comments"].value = origin ? `${origin} (management push from JS astrometric explorer)` : "";
  }
  setAstrometryPushStatus(fit ? "" : "Run a fit before pushing values.");
}

function syncAstrometryPushRls() {
  if (!atmEl["atm-push-is-public"] || !atmEl["atm-push-rls"]) return;
  if (atmEl["atm-push-is-public"].checked) {
    atmEl["atm-push-rls"].value = "public";
    atmEl["atm-push-rls"].disabled = true;
  } else {
    atmEl["atm-push-rls"].disabled = false;
    if (!atmEl["atm-push-rls"].value || atmEl["atm-push-rls"].value === "public") {
      atmEl["atm-push-rls"].value = "gagne";
    }
  }
}

function astrometryPushUnavailableReason() {
  if (!astrometryManagementAllowed()) return "Management/private MOCAdb credentials are required.";
  if (!atmState.fitResult) return "Run a fit before pushing values.";
  const pushCoordinate = Boolean(atmEl["atm-push-coordinate"]?.checked);
  const pushPm = Boolean(atmEl["atm-push-pm"]?.checked);
  const pushParallax = Boolean(atmEl["atm-push-parallax"]?.checked);
  if (!pushCoordinate && !pushPm && !pushParallax) return "Select at least one fitted quantity.";
  if (pushParallax && atmState.fitResult.mode !== "pm_plx") return "Run a PM+PLX fit before pushing parallax.";
  if (!String(atmEl["atm-push-origin"]?.value || "").trim()) return "Origin is required.";
  if (!atmEl["atm-push-is-public"]?.checked && !String(atmEl["atm-push-rls"]?.value || "").trim()) return "RLS is required.";
  if (pushCoordinate) {
    const prepared = atmState.lastPrepared || prepareAstrometryRows();
    const fittedCoordinate = astrometryFittedCoordinate(atmState.fitResult, prepared);
    if (!fittedCoordinate || !finite(fittedCoordinate.ra) || !finite(fittedCoordinate.dec)) return "Fitted coordinate is unavailable.";
  }
  return "";
}

function updateAstrometryPushControls() {
  if (!atmEl["atm-management-tools"] || atmEl["atm-management-tools"].hidden) return;
  const fit = atmState.fitResult;
  const busy = Boolean(atmState.pushBusy || atmState.fitBusy);
  const hasFit = Boolean(fit);
  const isPlxFit = fit?.mode === "pm_plx";
  for (const id of ["atm-push-coordinate", "atm-push-pm"]) {
    if (atmEl[id]) atmEl[id].disabled = busy || !hasFit;
  }
  if (atmEl["atm-push-parallax"]) {
    atmEl["atm-push-parallax"].disabled = busy || !isPlxFit;
    if (!isPlxFit) atmEl["atm-push-parallax"].checked = false;
  }
  for (const id of ["atm-push-moca-pid", "atm-push-origin", "atm-push-comments", "atm-push-is-public", "atm-push-allow-duplicate"]) {
    if (atmEl[id]) atmEl[id].disabled = busy || !hasFit;
  }
  syncAstrometryPushRls();
  if (atmEl["atm-push-rls"]) atmEl["atm-push-rls"].disabled = busy || !hasFit || Boolean(atmEl["atm-push-is-public"]?.checked);
  const reason = astrometryPushUnavailableReason();
  if (atmEl["atm-push-preview"]) atmEl["atm-push-preview"].disabled = busy || Boolean(reason);
  if (atmEl["atm-push-apply"]) atmEl["atm-push-apply"].disabled = busy || Boolean(reason);
}

function updateManualAstrometryRejectionControls() {
  const busy = Boolean(atmState.fitBusy);
  const selectedCount = manualAstrometryRejectableSelectionCount();
  const manualCount = manualAstrometryRejectedVisibleCount();
  if (atmEl["atm-reject-selected-fit"]) {
    atmEl["atm-reject-selected-fit"].disabled = busy || selectedCount < 1;
  }
  if (atmEl["atm-reset-manual-rejections"]) {
    atmEl["atm-reset-manual-rejections"].disabled = busy || atmState.manualRejectedIds.size < 1;
  }
  if (atmEl["atm-manual-rejection-note"]) {
    const hiddenCount = Math.max(atmState.manualRejectedIds.size - manualCount, 0);
    const selectionText = selectedCount ? `${selectedCount} selected` : "no selected points";
    const manualText = manualCount === 1 ? "1 manually rejected point" : `${manualCount} manually rejected points`;
    atmEl["atm-manual-rejection-note"].textContent = hiddenCount
      ? `${manualText} visible, ${hiddenCount} hidden by current filters; ${selectionText}`
      : `${manualText}; ${selectionText}`;
  }
}

function manualAstrometryRejectableSelectionCount() {
  if (!atmState.selectedIds.size || !atmState.processedRows.length) return 0;
  const selected = new Set([...atmState.selectedIds].map(String));
  return atmState.processedRows.filter((row) => {
    const id = astrometryRowIdKey(row);
    return selected.has(id) && !atmState.manualRejectedIds.has(id);
  }).length;
}

function manualAstrometryRejectedVisibleCount() {
  if (!atmState.manualRejectedIds.size || !atmState.processedRows.length) return 0;
  return atmState.processedRows.filter((row) => isManuallyRejectedAstrometryRow(row)).length;
}

function pruneManualAstrometryRejections() {
  if (!atmState.payload?.rows || !atmState.manualRejectedIds.size) return;
  const validIds = new Set((atmState.payload.rows || []).map((row) => astrometryRowIdKey(row)));
  atmState.manualRejectedIds = new Set([...atmState.manualRejectedIds].filter((id) => validIds.has(String(id))));
}

function addSelectedAstrometryFitRejections() {
  if (!atmState.selectedIds.size || !atmState.processedRows.length) return;
  const selected = new Set([...atmState.selectedIds].map(String));
  let added = 0;
  atmState.processedRows.forEach((row) => {
    const id = astrometryRowIdKey(row);
    if (!selected.has(id) || atmState.manualRejectedIds.has(id)) return;
    atmState.manualRejectedIds.add(id);
    added += 1;
  });
  if (!added) {
    updateManualAstrometryRejectionControls();
    return;
  }
  atmState.selectedIds.clear();
  clearAstrometryFit({ render: false });
  renderAstrometry();
  setAstrometryStatus(`${added} point${added === 1 ? "" : "s"} manually rejected from future fits`, "");
}

function clearManualAstrometryFitRejections() {
  if (!atmState.manualRejectedIds.size) return;
  const cleared = atmState.manualRejectedIds.size;
  atmState.manualRejectedIds.clear();
  atmState.selectedIds.clear();
  clearAstrometryFit({ render: false });
  renderAstrometry();
  setAstrometryStatus(`Cleared ${cleared} manual fit rejection${cleared === 1 ? "" : "s"}`, "");
}

function astrometryRowIdKey(rowOrId) {
  if (rowOrId && typeof rowOrId === "object") return String(rowOrId.id);
  return String(rowOrId);
}

function isManuallyRejectedAstrometryRow(row) {
  return atmState.manualRejectedIds.has(astrometryRowIdKey(row));
}

async function searchAstrometryTargets(query, options = {}) {
  const selectedOid = options.selectedOid ?? null;
  const quiet = Boolean(options.quiet);
  if (!query && selectedOid === null) {
    atmEl["atm-target-results"].hidden = true;
    return;
  }
  if (!quiet && query.length < 2 && !/^\d+$/.test(query)) {
    atmEl["atm-target-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    showAstrometrySearchPopup();
    return;
  }
  const params = apiParams();
  if (query) params.set("q", query);
  if (selectedOid !== null) params.set("moca_oid", selectedOid);
  const payload = await fetchJsonUrl(atmAppUrl(`api/astrometry/search?${params.toString()}`));
  if (!payload.ok) {
    if (!quiet) {
      atmEl["atm-target-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
      showAstrometrySearchPopup();
    }
    return;
  }
  const results = payload.options || [];
  if (selectedOid !== null && results.length) {
    selectAstrometryTarget(results[0], { deferLoad: true });
    return;
  }
  renderAstrometrySearchResults(results);
}

function renderAstrometrySearchResults(results) {
  if (!results.length) {
    atmEl["atm-target-results"].innerHTML = `<div class="designation-result-note">No targets found</div>`;
    showAstrometrySearchPopup();
    return;
  }
  atmEl["atm-target-results"].innerHTML = results.map((result, index) => (
    `<button class="designation-result" type="button" data-index="${index}"><span>${escapeHtml(result.label || `oid${result.value}`)}</span></button>`
  )).join("");
  atmEl["atm-target-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      const result = results[Number(button.dataset.index)];
      selectAstrometryTarget(result);
      atmEl["atm-target-results"].hidden = true;
      await loadAstrometryObject();
    });
  });
  showAstrometrySearchPopup();
}

function showAstrometrySearchPopup() {
  positionAstrometrySearchPopup();
  atmEl["atm-target-results"].hidden = false;
}

function positionAstrometrySearchPopup() {
  const input = atmEl["atm-target-search"];
  const popup = atmEl["atm-target-results"];
  if (!input || !popup) return;
  const rect = input.getBoundingClientRect();
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - 320));
  const available = Math.max(280, window.innerWidth - left - 16);
  const width = Math.min(760, available);
  popup.style.left = `${left}px`;
  popup.style.top = `${rect.bottom + 4}px`;
  popup.style.width = `${Math.max(rect.width, width)}px`;
}

function selectAstrometryTarget(option, options = {}) {
  const oid = parseInteger(option.value ?? option.moca_oid);
  if (oid === null) return;
  const changed = atmState.selectedOid !== oid;
  atmState.selectedOid = oid;
  atmState.selectedTargetLabel = option.label || `oid${oid}`;
  if (changed) {
    atmState.payload = null;
    atmState.selectedIds.clear();
    atmState.manualRejectedIds.clear();
    atmState.selectedMissions.clear();
    atmState.initialMissions = [];
    atmState.hasUserMissionChoice = false;
    clearAstrometryFit({ render: false });
  }
  atmEl["atm-target-search"].value = atmState.selectedTargetLabel;
  updateSelectedTargetDisplay();
  if (!options.deferLoad) updateAstrometryUrl();
}

async function loadAstrometryObject() {
  updateAstrometryUrl();
  if (atmState.selectedOid === null) {
    renderEmptyAstrometry("Select a target");
    return;
  }
  setAstrometryLoading(true);
  setAstrometryStatus("Loading astrometry", "loading");
  const objectPath = atmEl["atm-display-merged"].checked
    ? `api/astrometry/object/${atmState.selectedOid}?display_merged=1`
    : `api/astrometry/object/${atmState.selectedOid}`;
  const payload = await fetchAstrometryJson(objectPath);
  setAstrometryLoading(false);
  if (!payload.ok) {
    atmState.payload = null;
    atmState.selectedIds.clear();
    atmState.manualRejectedIds.clear();
    clearAstrometryFit({ render: false });
    setAstrometryStatus(payload.error || "Could not load astrometry", "error");
    renderEmptyAstrometry(payload.error || "Could not load astrometry");
    return;
  }
  atmState.payload = payload;
  atmState.selectedIds.clear();
  pruneManualAstrometryRejections();
  atmState.selectedTargetLabel = targetLabel(payload.target);
  atmEl["atm-target-search"].value = atmState.selectedTargetLabel;
  updateSelectedTargetDisplay();
  initializeMissionSelection();
  renderMissionList();
  renderAstrometry();
  setAstrometryStatus(`${payload.meta?.row_count || 0} astrometric measurements loaded${payload.cache?.hit ? " from cache" : ""}`, "");
}

function initializeMissionSelection() {
  const available = new Set((atmState.payload?.missions || []).map((row) => row.value));
  if (atmState.hasUserMissionChoice) {
    atmState.selectedMissions = new Set([...atmState.selectedMissions].filter((mission) => available.has(mission)));
    return;
  }
  if (atmState.initialMissions.length) {
    atmState.selectedMissions = new Set(atmState.initialMissions.filter((mission) => available.has(mission)));
  } else {
    atmState.selectedMissions = new Set(available);
  }
}

function renderMissionList() {
  const missions = atmState.payload?.missions || [];
  if (!missions.length) {
    atmEl["atm-mission-list"].innerHTML = `<div class="plot-hint">No missions loaded</div>`;
    return;
  }
  atmEl["atm-mission-list"].innerHTML = missions.map((mission) => (
    `<label class="checkline mission-check">
      <input type="checkbox" value="${escapeHtml(mission.value)}" ${atmState.selectedMissions.has(mission.value) ? "checked" : ""}>
      <span>${escapeHtml(mission.label || mission.value)}</span>
    </label>`
  )).join("");
  atmEl["atm-mission-list"].querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) atmState.selectedMissions.add(input.value);
      else atmState.selectedMissions.delete(input.value);
      atmState.hasUserMissionChoice = true;
      clearAstrometryFit({ render: false });
      renderAstrometry();
      updateAstrometryUrl();
    });
  });
}

function updateSelectedTargetDisplay() {
  const hasTarget = atmState.selectedOid !== null;
  atmEl["atm-selected-target-text"].textContent = hasTarget ? atmState.selectedTargetLabel || `oid${atmState.selectedOid}` : "No target selected";
  atmEl["atm-clear-target"].hidden = !hasTarget;
  atmEl["atm-open-report"].disabled = !normalizedMocaOid(currentAstrometryReportOid());
}

function renderAstrometry() {
  if (!atmState.payload) {
    renderEmptyAstrometry("No target loaded");
    return;
  }
  const prepared = prepareAstrometryRows();
  atmState.processedRows = prepared.rows;
  atmState.lastPrepared = prepared;
  renderAstrometryPlot("ra", prepared);
  renderAstrometryPlot("dec", prepared);
  renderAstrometrySummary(prepared);
  renderAstrometryTable();
  updateAstrometryUrl();
  setAstrometryExportDisabled(!atmState.processedRows.length);
  setAstrometryFitDisabled(!atmState.processedRows.length);
  updateManualAstrometryRejectionControls();
  updateAstrometryFitSummary();
  updateAstrometryManagementVisibility();
}

function prepareAstrometryRows() {
  const payload = atmState.payload;
  const allRows = (payload.rows || []).map((row) => ({ ...row }));
  const displayMerged = atmEl["atm-display-merged"].checked;
  const recalFiltered = atmEl["atm-only-recalibrated"].checked
    ? allRows.filter((row) => row.calibration_method || Number(row.include_in_recalibrated_display) === 1 || (displayMerged && Number(row.single_epoch) === 0))
    : allRows;
  const baseRows = recalFiltered.length ? recalFiltered : allRows;
  const missionRows = baseRows.filter((row) => atmState.selectedMissions.has(String(row.mission || "No mission")));
  const rows = missionRows.filter((row) => finite(row.measurement_epoch_yr));
  const useRaw = atmEl["atm-revert-raw"].checked;
  const reference = normalizedReference(payload.reference, rows, useRaw);
  const pm = payload.pm || {};
  const plx = payload.parallax || {};
  const pmra = finite(pm.pmra_masyr) ? Number(pm.pmra_masyr) : 0;
  const pmdec = finite(pm.pmdec_masyr) ? Number(pm.pmdec_masyr) : 0;
  const pmraUnc = finite(pm.pmra_masyr_unc) ? Number(pm.pmra_masyr_unc) : 0;
  const pmdecUnc = finite(pm.pmdec_masyr_unc) ? Number(pm.pmdec_masyr_unc) : 0;
  const plxValue = finite(plx.parallax_mas) ? Number(plx.parallax_mas) : 0;
  const plxUnc = finite(plx.parallax_mas_unc) ? Number(plx.parallax_mas_unc) : 0;
  const refRaUnc = finite(payload.reference?.ra_unc_mas) ? Number(payload.reference.ra_unc_mas) : null;
  const refDecUnc = finite(payload.reference?.dec_unc_mas) ? Number(payload.reference.dec_unc_mas) : null;
  const displayReference = atmEl["atm-display-reference"].checked;
  let refRa = reference.ra;
  let refDec = reference.dec;
  let refEpoch = reference.epoch;
  if (atmEl["atm-adjust-reference"].checked && rows.length) {
    const epochs = rows.map((row) => Number(row.measurement_epoch_yr)).filter(finite);
    const targetEpoch = mean(epochs);
    if (finite(targetEpoch)) {
      const finitePositions = rows.map((row) => astrometryPosition(row, useRaw)).filter((pos) => finite(pos.ra) && finite(pos.dec));
      const meanRa = mean(finitePositions.map((pos) => pos.ra));
      const meanDec = mean(finitePositions.map((pos) => pos.dec));
      const raCandidates = [];
      const decCandidates = [];
      rows.forEach((row) => {
        const pos = astrometryPosition(row, useRaw);
        const epoch = Number(row.measurement_epoch_yr);
        if (!finite(pos.ra) || !finite(pos.dec) || !finite(epoch)) return;
        const cosDec = Math.cos(rad(pos.dec));
        if (!finite(cosDec) || Math.abs(cosDec) < 1e-9) return;
        const pf = finite(meanRa) && finite(meanDec) ? parallaxMotion(meanRa, meanDec, epoch) : { ra: 0, dec: 0 };
        let raObserved = pos.ra * cosDec * 3600 * 1000;
        let decObserved = pos.dec * 3600 * 1000;
        raObserved -= pmra * (epoch - targetEpoch);
        decObserved -= pmdec * (epoch - targetEpoch);
        raObserved -= plxValue * pf.ra;
        decObserved -= plxValue * pf.dec;
        raCandidates.push(raObserved / (cosDec * 3600 * 1000));
        decCandidates.push(decObserved / (3600 * 1000));
      });
      const candidateRa = median(raCandidates);
      const candidateDec = median(decCandidates);
      if (finite(candidateRa) && finite(candidateDec)) {
        refRa = candidateRa;
        refDec = candidateDec;
      }
      refEpoch = targetEpoch;
    }
  }
  const processed = rows.map((row) => {
    const pos = astrometryPosition(row, useRaw);
    const ra = pos.ra;
    const dec = pos.dec;
    const epoch = Number(row.measurement_epoch_yr);
    const pf = parallaxMotion(refRa, refDec, epoch);
    const baseRelRa = (ra - refRa) * Math.cos(rad(refDec)) * 3600 * 1000;
    const baseRelDec = (dec - refDec) * 3600 * 1000;
    let relRa = baseRelRa;
    let relDec = baseRelDec;
    if (atmEl["atm-subtract-pm"].checked) {
      relRa -= pmra * (epoch - refEpoch);
      relDec -= pmdec * (epoch - refEpoch);
    }
    if (atmEl["atm-subtract-plx"].checked) {
      relRa -= plxValue * pf.ra;
      relDec -= plxValue * pf.dec;
    }
    const x = atmEl["atm-phase-yearly"].checked ? yearlyPhase(epoch) : epoch;
    return {
      ...row,
      plot_x: x,
      plot_epoch_abs: epoch,
      base_rel_ra: baseRelRa,
      base_rel_dec: baseRelDec,
      rel_ra: relRa,
      rel_dec: relDec,
      plot_ra: ra,
      plot_dec: dec,
    };
  }).filter((row) => finite(row.rel_ra) && finite(row.rel_dec));
  const referenceAstrometry = adoptedReferenceAstrometry(payload.reference, {
    useRaw,
    refRa,
    refDec,
    refEpoch,
    pmra,
    pmdec,
    plxValue,
  });
  const xValues = [
    ...processed.map((row) => row.plot_x),
    ...(displayReference && referenceAstrometry ? [referenceAstrometry.plot_x] : []),
  ].filter(finite);
  const xRange = paddedRange(xValues, atmEl["atm-phase-yearly"].checked ? [0, 1] : null);
  const model = buildAstrometryModel({
    xRange,
    rows: processed,
    refRa,
    refDec,
    refEpoch,
    pmra,
    pmdec,
    pmraUnc,
    pmdecUnc,
    plxValue,
    plxUnc,
  });
  const binned = atmEl["atm-bin"].checked ? binAstrometryRows(processed) : [];
  return {
    rows: processed,
    binned,
    model,
    reference: {
      ra: refRa,
      dec: refDec,
      raUncMas: refRaUnc,
      decUncMas: refDecUnc,
      epoch: refEpoch,
      source: astrometryPublicationInfo(payload.reference, "Reference coordinates"),
    },
    referenceAstrometry,
    pm: { pmra, pmdec, pmraUnc, pmdecUnc, reference: pm.reference, source: astrometryPublicationInfo(pm, pm.reference || "Proper motion") },
    parallax: { value: plxValue, uncertainty: plxUnc, reference: plx.reference, source: astrometryPublicationInfo(plx, plx.reference || "Parallax") },
    usedFallbackRecalibration: atmEl["atm-only-recalibrated"].checked && !recalFiltered.length && allRows.length > 0,
  };
}

function adoptedReferenceAstrometry(reference, { useRaw, refRa, refDec, refEpoch, pmra, pmdec, plxValue }) {
  if (!reference || reference.fallback) return null;
  if (reference.adopt_as_reference !== undefined && Number(reference.adopt_as_reference) !== 1) return null;
  const pos = astrometryPosition(reference, useRaw);
  const ra = pos.ra;
  const dec = pos.dec;
  const epoch = Number(reference.measurement_epoch_yr);
  if (!finite(ra) || !finite(dec) || !finite(epoch) || !finite(refRa) || !finite(refDec) || !finite(refEpoch)) return null;
  const pf = parallaxMotion(refRa, refDec, epoch);
  let relRa = (ra - refRa) * Math.cos(rad(refDec)) * 3600 * 1000;
  let relDec = (dec - refDec) * 3600 * 1000;
  if (atmEl["atm-subtract-pm"].checked) {
    relRa -= pmra * (epoch - refEpoch);
    relDec -= pmdec * (epoch - refEpoch);
  }
  if (atmEl["atm-subtract-plx"].checked) {
    relRa -= plxValue * pf.ra;
    relDec -= plxValue * pf.dec;
  }
  return {
    ...reference,
    id: reference.id ?? "adopted-reference",
    plot_x: atmEl["atm-phase-yearly"].checked ? yearlyPhase(epoch) : epoch,
    plot_epoch_abs: epoch,
    rel_ra: relRa,
    rel_dec: relDec,
    plot_ra: ra,
    plot_dec: dec,
  };
}

function astrometryPosition(row, useRaw) {
  const rawRa = useRaw ? row.raw_ra : row.ra;
  const rawDec = useRaw ? row.raw_dec : row.dec;
  const ra = finite(rawRa) ? Number(rawRa) : Number(row.ra);
  const dec = finite(rawDec) ? Number(rawDec) : Number(row.dec);
  return { ra, dec };
}

function normalizedReference(reference, rows, useRaw) {
  let ra = finite(useRaw ? reference?.raw_ra : reference?.ra) ? Number(useRaw ? reference.raw_ra : reference.ra) : NaN;
  let dec = finite(useRaw ? reference?.raw_dec : reference?.dec) ? Number(useRaw ? reference.raw_dec : reference.dec) : NaN;
  let epoch = finite(reference?.measurement_epoch_yr) ? Number(reference.measurement_epoch_yr) : NaN;
  if (!finite(ra) || !finite(dec) || !finite(epoch)) {
    const usable = rows.filter((row) => {
      const pos = astrometryPosition(row, useRaw);
      return finite(pos.ra) && finite(pos.dec) && finite(row.measurement_epoch_yr);
    });
    if (usable.length) {
      const sorted = [...usable].sort((a, b) => Number(a.measurement_epoch_yr) - Number(b.measurement_epoch_yr));
      const mid = sorted[Math.floor(sorted.length / 2)];
      const pos = astrometryPosition(mid, useRaw);
      ra = Number(pos.ra);
      dec = Number(pos.dec);
      epoch = Number(mid.measurement_epoch_yr);
    }
  }
  return { ra, dec, epoch };
}

function buildAstrometryModel({ xRange, rows, refRa, refDec, refEpoch, pmra, pmdec, pmraUnc, pmdecUnc, plxValue, plxUnc }) {
  if (!rows.length || !finite(xRange[0]) || !finite(xRange[1]) || xRange[0] === xRange[1]) {
    return { x: [], ra: [], dec: [], raUpper: [], raLower: [], decUpper: [], decLower: [] };
  }
  const n = 500;
  const centerEpoch = mean(rows.map((row) => Number(row.plot_epoch_abs)).filter(finite));
  const roundedCenter = Math.round(centerEpoch || refEpoch || 0);
  const x = [];
  const ra = [];
  const dec = [];
  const raUpper = [];
  const raLower = [];
  const decUpper = [];
  const decLower = [];
  for (let index = 0; index < n; index += 1) {
    const frac = n <= 1 ? 0 : index / (n - 1);
    const xv = xRange[0] + frac * (xRange[1] - xRange[0]);
    const epoch = atmEl["atm-phase-yearly"].checked ? xv + roundedCenter : xv;
    const dt = epoch - refEpoch;
    const pf = parallaxMotion(refRa, refDec, epoch);
    let modelRa = atmEl["atm-subtract-pm"].checked ? 0 : pmra * dt;
    let modelDec = atmEl["atm-subtract-pm"].checked ? 0 : pmdec * dt;
    if (!atmEl["atm-subtract-plx"].checked) {
      modelRa += plxValue * pf.ra;
      modelDec += plxValue * pf.dec;
    }
    const pmRaSigma = atmEl["atm-subtract-pm"].checked ? 0 : Math.abs(dt * pmraUnc);
    const pmDecSigma = atmEl["atm-subtract-pm"].checked ? 0 : Math.abs(dt * pmdecUnc);
    const plxRaSigma = atmEl["atm-subtract-plx"].checked ? 0 : Math.abs(pf.ra * plxUnc);
    const plxDecSigma = atmEl["atm-subtract-plx"].checked ? 0 : Math.abs(pf.dec * plxUnc);
    const sigRa = Math.sqrt(pmRaSigma ** 2 + plxRaSigma ** 2);
    const sigDec = Math.sqrt(pmDecSigma ** 2 + plxDecSigma ** 2);
    x.push(xv);
    ra.push(modelRa);
    dec.push(modelDec);
    raLower.push(modelRa - sigRa);
    raUpper.push(modelRa + sigRa);
    decLower.push(modelDec - sigDec);
    decUpper.push(modelDec + sigDec);
  }
  return { x, ra, dec, raUpper, raLower, decUpper, decLower };
}

function binAstrometryRows(rows) {
  const phase = atmEl["atm-phase-yearly"].checked;
  const binWidth = (phase ? atmPhaseBinSizeDays : atmBinSizeDays) / 365.25;
  const groups = new Map();
  rows.forEach((row) => {
    const key = Math.floor(Number(row.plot_x) / binWidth) * binWidth;
    const label = Number(key.toFixed(6));
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(row);
  });
  return [...groups.entries()].map(([x, group]) => {
    const ra = weightedAverage(group, "rel_ra", "ra_unc_mas");
    const dec = weightedAverage(group, "rel_dec", "dec_unc_mas");
    return {
      id: `bin-${x}`,
      plot_x: x,
      rel_ra: ra.value,
      rel_dec: dec.value,
      ra_unc_mas: ra.uncertainty,
      dec_unc_mas: dec.uncertainty,
      ndata: group.length,
      mission: "Binned data",
    };
  }).filter((row) => finite(row.rel_ra) && finite(row.rel_dec));
}

function weightedAverage(rows, valueKey, errorKey) {
  const values = rows
    .map((row) => ({ value: Number(row[valueKey]), error: Math.max(Number(row[errorKey]) || 1, 1e-6) }))
    .filter((item) => finite(item.value) && finite(item.error));
  if (!values.length) return { value: NaN, uncertainty: NaN };
  if (values.length === 1) return { value: values[0].value, uncertainty: values[0].error };
  const weights = values.map((item) => 1 / item.error ** 2);
  const weightSum = weights.reduce((sum, value) => sum + value, 0);
  const meanValue = values.reduce((sum, item, index) => sum + item.value * weights[index], 0) / weightSum;
  const variance = values.reduce((sum, item, index) => sum + weights[index] * (item.value - meanValue) ** 2, 0) / weightSum;
  return { value: meanValue, uncertainty: Math.sqrt(Math.max(variance, 0)) };
}

function astrometryMissionStyles(rows) {
  const styles = new Map();
  rows.forEach((row) => {
    const mission = String(row.mission || "No mission");
    if (!styles.has(mission)) {
      styles.set(mission, { color: atmMissionColors[styles.size % atmMissionColors.length] });
    }
  });
  return styles;
}

function astrometryMarkerStyle(mission, missionStyles) {
  const style = missionStyles.get(String(mission || "No mission")) || { color: atmMissionColors[0] };
  return {
    color: style.color,
    size: atmEl["atm-bin"].checked ? 7 : 8,
    opacity: atmEl["atm-bin"].checked ? 0.36 : 0.9,
  };
}

function displayAbsoluteAstrometry() {
  return Boolean(atmEl["atm-display-absolute"]?.checked);
}

function astrometryYValue(prepared, axis, row) {
  const offset = axis === "ra" ? row.rel_ra : row.rel_dec;
  if (!displayAbsoluteAstrometry()) return offset;
  const absoluteKey = axis === "ra" ? "plot_ra" : "plot_dec";
  if (finite(row[absoluteKey])) return Number(row[absoluteKey]);
  return astrometryOffsetToDegrees(prepared, axis, offset);
}

function astrometryYSeries(prepared, axis, offsets) {
  return displayAbsoluteAstrometry()
    ? offsets.map((value) => astrometryOffsetToDegrees(prepared, axis, value))
    : offsets;
}

function astrometryYError(prepared, axis, sigmaMas) {
  if (!displayAbsoluteAstrometry()) return sigmaMas;
  if (!finite(sigmaMas)) return 0;
  const divisor = axis === "ra" ? astrometryRaDegreeDivisor(prepared) : 3600 * 1000;
  return finite(divisor) && Math.abs(divisor) > 1e-12 ? Math.abs(Number(sigmaMas) / divisor) : 0;
}

function astrometryOffsetToDegrees(prepared, axis, offsetMas) {
  if (!finite(offsetMas)) return NaN;
  if (axis === "ra") {
    const divisor = astrometryRaDegreeDivisor(prepared);
    return finite(prepared.reference.ra) && finite(divisor) && Math.abs(divisor) > 1e-12
      ? Number(prepared.reference.ra) + Number(offsetMas) / divisor
      : NaN;
  }
  return finite(prepared.reference.dec)
    ? Number(prepared.reference.dec) + Number(offsetMas) / (3600 * 1000)
    : NaN;
}

function astrometryRaDegreeDivisor(prepared) {
  const cosDec = Math.cos(rad(prepared.reference.dec));
  return finite(cosDec) ? cosDec * 3600 * 1000 : NaN;
}

function renderAstrometryPlot(axis, prepared) {
  const isRa = axis === "ra";
  const plotEl = isRa ? atmEl["atm-ra-plot"] : atmEl["atm-dec-plot"];
  const displayAbsolute = displayAbsoluteAstrometry();
  const traces = [];
  const modelOffsets = isRa ? prepared.model.ra : prepared.model.dec;
  const lowerOffsets = isRa ? prepared.model.raLower : prepared.model.decLower;
  const upperOffsets = isRa ? prepared.model.raUpper : prepared.model.decUpper;
  const modelY = astrometryYSeries(prepared, axis, modelOffsets);
  const lower = astrometryYSeries(prepared, axis, lowerOffsets);
  const upper = astrometryYSeries(prepared, axis, upperOffsets);
  const yTitle = displayAbsolute ? `${isRa ? "R.A." : "Decl."} (${isRa ? "hh:mm:ss" : "dd:mm:ss"})` : `${isRa ? "R.A." : "Decl."} offset (mas)`;
  const yHoverLabel = displayAbsolute ? `${isRa ? "R.A." : "Decl."}` : `${isRa ? "R.A." : "Decl."} offset`;
  const yHoverUnit = displayAbsolute ? "deg" : "mas";
  const yHoverFormat = displayAbsolute ? ".8f" : ".2f";
  traces.push({
    x: prepared.model.x,
    y: modelY,
    type: "scatter",
    mode: "lines",
    line: { color: "rgba(55,126,184,0.72)", width: 4 },
    name: "MOCAdb solution",
    hoverinfo: "skip",
  });
  traces.push({
    x: prepared.model.x,
    y: lower,
    type: "scatter",
    mode: "lines",
    line: { width: 0 },
    showlegend: false,
    hoverinfo: "skip",
  });
  traces.push({
    x: prepared.model.x,
    y: upper,
    type: "scatter",
    mode: "lines",
    line: { width: 0 },
    fill: "tonexty",
    fillcolor: "rgba(55,126,184,0.16)",
    name: "Model +/-1 sigma",
    showlegend: isRa,
    hoverinfo: "skip",
  });
  const missionStyles = astrometryMissionStyles(prepared.rows);
  const missions = [...missionStyles.keys()];
  missions.forEach((mission) => {
    const rows = prepared.rows.filter((row) => String(row.mission || "No mission") === mission);
    const markerStyle = astrometryMarkerStyle(mission, missionStyles);
    traces.push({
      x: rows.map((row) => row.plot_x),
      y: rows.map((row) => astrometryYValue(prepared, axis, row)),
      customdata: rows.map((row) => row.id),
      text: rows.map((row) => hoverText(row)),
      type: "scatter",
      mode: "markers",
      marker: {
        size: markerStyle.size,
        color: markerStyle.color,
        opacity: markerStyle.opacity,
        line: { width: 1.4, color: "rgba(255,255,255,0.82)" },
      },
      error_y: {
        type: "data",
        array: rows.map((row) => astrometryYError(prepared, axis, Number(isRa ? row.ra_unc_mas : row.dec_unc_mas) || 0)),
        visible: true,
        color: "rgba(0,0,0,0.25)",
        thickness: 1.2,
        width: 2,
      },
      name: mission,
      legendgroup: mission,
      hovertemplate: "%{text}<extra></extra>",
    });
  });
  if (prepared.binned.length) {
    traces.push({
      x: prepared.binned.map((row) => row.plot_x),
      y: prepared.binned.map((row) => astrometryYValue(prepared, axis, row)),
      text: prepared.binned.map((row) => `Binned data<br>N=${row.ndata}<br>${yHoverLabel}: ${formatAstrometryYForDisplay(axis, astrometryYValue(prepared, axis, row), displayAbsolute)}${displayAbsolute ? "" : ` ${yHoverUnit}`}`),
      type: "scatter",
      mode: "markers",
      marker: { size: 11, color: "white", line: { width: 2.5, color: "black" } },
      error_y: {
        type: "data",
        array: prepared.binned.map((row) => astrometryYError(prepared, axis, Number(isRa ? row.ra_unc_mas : row.dec_unc_mas) || 0)),
        visible: true,
        color: "rgba(0,0,0,0.35)",
        thickness: 1.5,
        width: 2,
      },
      name: "Binned data",
      hovertemplate: "%{text}<extra></extra>",
    });
  }
  const referenceMarker = atmEl["atm-display-reference"].checked ? prepared.referenceAstrometry : null;
  if (referenceMarker) {
    traces.push({
      x: [referenceMarker.plot_x],
      y: [astrometryYValue(prepared, axis, referenceMarker)],
      text: [referenceAstrometryHoverText(referenceMarker, isRa)],
      type: "scatter",
      mode: "markers",
      marker: {
        symbol: "star",
        size: 17,
        color: "#FFD166",
        opacity: 1,
        line: { width: 2, color: "#252329" },
      },
      name: "Reference astrometry",
      hovertemplate: "%{text}<extra></extra>",
    });
  }
  const fittedReferenceMarker = astrometryFittedReferenceMarker(prepared);
  if (fittedReferenceMarker) {
    traces.push({
      x: [fittedReferenceMarker.plot_x],
      y: [astrometryYValue(prepared, axis, fittedReferenceMarker)],
      text: [fittedReferenceHoverText(fittedReferenceMarker, isRa)],
      type: "scatter",
      mode: "markers",
      marker: {
        symbol: "star",
        size: 17,
        color: "#d73027",
        opacity: 1,
        line: { width: 2, color: "#252329" },
      },
      name: "Fitted reference position",
      legendgroup: "astrometry-fit-reference",
      showlegend: isRa,
      hovertemplate: "%{text}<extra></extra>",
    });
  }
  const fitCurve = atmState.fitResult ? buildAstrometryFitCurve(atmState.fitResult, prepared) : null;
  const fitOffsets = fitCurve ? (isRa ? fitCurve.ra : fitCurve.dec) : [];
  const fitY = astrometryYSeries(prepared, axis, fitOffsets);
  if (fitCurve && fitCurve.x.length) {
    traces.push({
      x: fitCurve.x,
      y: fitY,
      text: fitY.map((value) => formatAstrometryYForDisplay(axis, value, displayAbsolute)),
      type: "scatter",
      mode: "lines",
      line: { color: "#d73027", width: 3.5, dash: "longdash" },
      name: fitCurve.label,
      legendgroup: "astrometry-fit",
      showlegend: isRa,
      hovertemplate: displayAbsolute
        ? `${fitCurve.label}<br>%{x:.5g}<br>${yHoverLabel}: %{text}<extra></extra>`
        : `${fitCurve.label}<br>%{x:.5g}<br>${yHoverLabel}: %{y:${yHoverFormat}} ${yHoverUnit}<extra></extra>`,
    });
  }
  const fitOutlierRows = astrometryFitOutlierRows(prepared);
  if (fitOutlierRows.length) {
    traces.push({
      x: fitOutlierRows.map((row) => row.plot_x),
      y: fitOutlierRows.map((row) => astrometryYValue(prepared, axis, row)),
      customdata: fitOutlierRows.map((row) => row.id),
      text: fitOutlierRows.map((row) => astrometryFitOutlierHoverText(row)),
      type: "scatter",
      mode: "markers",
      marker: {
        symbol: "x-thin",
        size: 17,
        color: "#d73027",
        line: { width: 1, color: "#d73027" },
      },
      name: "PM-fit outliers",
      legendgroup: "astrometry-fit-outliers",
      showlegend: isRa,
      hovertemplate: "%{text}<extra></extra>",
    });
  }
  const manualRejectedRows = astrometryManualRejectedRows(prepared);
  if (manualRejectedRows.length) {
    traces.push({
      x: manualRejectedRows.map((row) => row.plot_x),
      y: manualRejectedRows.map((row) => astrometryYValue(prepared, axis, row)),
      customdata: manualRejectedRows.map((row) => row.id),
      text: manualRejectedRows.map((row) => astrometryManualRejectedHoverText(row)),
      type: "scatter",
      mode: "markers",
      marker: {
        symbol: "x-thin",
        size: 18,
        color: "#1f78b4",
        line: { width: 1.2, color: "#1f78b4" },
      },
      name: "Manually rejected from fit",
      legendgroup: "astrometry-manual-rejections",
      showlegend: isRa,
      hovertemplate: "%{text}<extra></extra>",
    });
  }
  const yValues = [
    ...prepared.rows.map((row) => astrometryYValue(prepared, axis, row)),
    ...modelY,
    ...fitY,
    ...(referenceMarker ? [astrometryYValue(prepared, axis, referenceMarker)] : []),
    ...(fittedReferenceMarker ? [astrometryYValue(prepared, axis, fittedReferenceMarker)] : []),
  ].filter(finite);
  const yRange = paddedRange(yValues, null);
  const sexagesimalTicks = displayAbsolute ? astrometrySexagesimalTickSpec(yRange, axis) : null;
  const layout = {
    title: {
      text: `${isRa ? "R.A." : "Decl."} ${displayAbsolute ? "coordinates" : "offsets"} for ${escapeHtml(targetShortName(atmState.payload.target))}`,
      x: 0.5,
      xanchor: "center",
      y: 0.98,
      yanchor: "top",
    },
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { t: 58, r: 220, b: 76, l: displayAbsolute ? 132 : 72 },
    xaxis: {
      title: { text: atmEl["atm-phase-yearly"].checked ? "Yearly phase" : "Epoch (year)", font: { size: 20 }, standoff: 18 },
      tickfont: { size: 15 },
      tickformat: atmEl["atm-phase-yearly"].checked ? ".2f" : ".1f",
      separatethousands: false,
      automargin: true,
      range: paddedRange([
        ...prepared.rows.map((row) => row.plot_x),
        ...(referenceMarker ? [referenceMarker.plot_x] : []),
        ...(fittedReferenceMarker ? [fittedReferenceMarker.plot_x] : []),
      ].filter(finite), atmEl["atm-phase-yearly"].checked ? [0, 1] : null),
      showline: true,
      mirror: true,
      linecolor: "#000000",
      linewidth: 3,
      ticks: "outside",
      ticklen: 8,
      tickwidth: 2,
      tickcolor: "#000000",
      zeroline: false,
    },
    yaxis: {
      title: { text: yTitle, font: { size: 20 }, standoff: displayAbsolute ? 12 : 8 },
      tickfont: { size: displayAbsolute ? 13 : 15 },
      ...(sexagesimalTicks ? {
        tickmode: "array",
        tickvals: sexagesimalTicks.tickvals,
        ticktext: sexagesimalTicks.ticktext,
      } : {}),
      range: yRange,
      automargin: true,
      showline: true,
      mirror: true,
      linecolor: "#000000",
      linewidth: 3,
      ticks: "outside",
      ticklen: 8,
      tickwidth: 2,
      tickcolor: "#000000",
      zeroline: !displayAbsolute,
      zerolinecolor: "#c8c5cc",
    },
    legend: {
      orientation: "v",
      x: 1.02,
      xanchor: "left",
      y: 1,
      yanchor: "top",
      font: { size: 9 },
      bgcolor: "rgba(255,255,255,0.86)",
      groupclick: "togglegroup",
    },
    annotations: isRa ? [summaryAnnotation(prepared)] : [],
  };
  Plotly.react(plotEl, traces, layout, plotConfig(`astrometry_${axis}_oid_${atmState.selectedOid || "unknown"}`));
  if (typeof plotEl.removeAllListeners === "function") {
    plotEl.removeAllListeners("plotly_selected");
    plotEl.removeAllListeners("plotly_click");
    plotEl.removeAllListeners("plotly_deselect");
  }
  plotEl.on("plotly_selected", (event) => handleAstrometrySelection(event));
  plotEl.on("plotly_click", (event) => handleAstrometryClick(event));
  plotEl.on("plotly_deselect", () => handleAstrometryDeselect());
}

async function runAstrometryFit(mode) {
  if (!atmState.payload) return;
  const prepared = prepareAstrometryRows();
  const fitter = selectedAstrometryFitMethod();
  try {
    setAstrometryFitBusy(true, `Running ${fitter === "ultranest" ? "UltraNest" : "SciPy"} fit`);
    const payload = await postAstrometryJson("api/astrometry/fit", buildAstrometryFitRequest(mode, prepared));
    if (!payload?.ok || !payload.fit) {
      throw new Error(payload?.error || "Fit failed");
    }
    atmState.fitCapabilities = payload.capabilities || atmState.fitCapabilities;
    atmState.fitResult = payload.fit;
    updateAstrometryFitControlState();
    updateAstrometryManagementVisibility();
    renderAstrometry();
    setAstrometryStatus(`${atmState.fitResult.fitterLabel || "Astrometry"} fit complete`, "");
  } catch (error) {
    atmState.fitResult = null;
    updateAstrometryFitSummary(error.message || "Fit failed");
    updateAstrometryManagementVisibility();
    setAstrometryFitDisabled(!prepared.rows.length);
    setAstrometryStatus(error.message || "Fit failed", "error");
  } finally {
    setAstrometryFitBusy(false);
  }
}

function selectedAstrometryFitMethod() {
  const method = String(atmEl["atm-fit-method"]?.value || "scipy").toLowerCase();
  return method === "ultranest" ? "ultranest" : "scipy";
}

function buildAstrometryFitRequest(mode, prepared) {
  const rows = prepared.rows.filter((row) => (
    finite(row.plot_epoch_abs)
    && finite(row.base_rel_ra)
    && finite(row.base_rel_dec)
    && !isManuallyRejectedAstrometryRow(row)
  )).map((row) => ({
    id: row.id,
    mission: row.mission,
    plot_epoch_abs: row.plot_epoch_abs,
    measurement_epoch_yr: row.measurement_epoch_yr,
    base_rel_ra: row.base_rel_ra,
    base_rel_dec: row.base_rel_dec,
    ra_unc_mas: row.ra_unc_mas,
    dec_unc_mas: row.dec_unc_mas,
  }));
  return {
    mode,
    fitter: selectedAstrometryFitMethod(),
    outlierMixture: atmEl["atm-fit-outlier-mixture"] ? atmEl["atm-fit-outlier-mixture"].checked : true,
    reference: {
      ra: prepared.reference.ra,
      dec: prepared.reference.dec,
      epoch: prepared.reference.epoch,
    },
    parallax: {
      value: prepared.parallax.value,
      uncertainty: prepared.parallax.uncertainty,
    },
    rows,
  };
}

function setAstrometryFitBusy(busy, message = "") {
  atmState.fitBusy = Boolean(busy);
  if (message) updateAstrometryFitSummary(message);
  setAstrometryLoading(Boolean(busy));
  setAstrometryFitDisabled(!manualAstrometryFitRows(atmState.processedRows).length);
  updateAstrometryFitControlState();
  updateAstrometryPushControls();
}

function clearAstrometryFit(options = {}) {
  atmState.fitResult = null;
  updateAstrometryFitSummary();
  updateAstrometryManagementVisibility();
  if (options.render) renderAstrometry();
}

function computeAstrometryFit(mode, prepared) {
  const rows = prepared.rows.filter((row) => (
    finite(row.plot_epoch_abs)
    && finite(row.base_rel_ra)
    && finite(row.base_rel_dec)
  ));
  const isParallaxFit = mode === "pm_plx";
  const minRows = isParallaxFit ? 3 : 2;
  if (rows.length < minRows) {
    throw new Error(`Need at least ${minRows} usable measurements for this fit.`);
  }
  if (!finite(prepared.reference.ra) || !finite(prepared.reference.dec)) {
    throw new Error("Need a finite reference position for the parallax basis.");
  }
  const nParams = isParallaxFit ? 5 : 4;
  const normal = zeroMatrix(nParams);
  const rhs = new Array(nParams).fill(0);
  const equations = [];
  const t0 = finite(prepared.reference.epoch)
    ? Number(prepared.reference.epoch)
    : median(rows.map((row) => row.plot_epoch_abs));
  const fixedPlx = !isParallaxFit && finite(prepared.parallax.value) ? Number(prepared.parallax.value) : 0;

  rows.forEach((row) => {
    const epoch = Number(row.plot_epoch_abs);
    const dt = epoch - t0;
    const pf = parallaxMotion(prepared.reference.ra, prepared.reference.dec, epoch);
    let raValue = Number(row.base_rel_ra);
    let decValue = Number(row.base_rel_dec);
    if (!isParallaxFit && fixedPlx) {
      raValue -= fixedPlx * pf.ra;
      decValue -= fixedPlx * pf.dec;
    }
    const raBasis = isParallaxFit ? [1, dt, 0, 0, pf.ra] : [1, dt, 0, 0];
    const decBasis = isParallaxFit ? [0, 0, 1, dt, pf.dec] : [0, 0, 1, dt];
    addWeightedEquation(normal, rhs, equations, raBasis, raValue, astrometryFitSigma(row.ra_unc_mas));
    addWeightedEquation(normal, rhs, equations, decBasis, decValue, astrometryFitSigma(row.dec_unc_mas));
  });

  const solved = solveNormalEquations(normal, rhs);
  if (!solved) throw new Error("The selected measurements do not constrain this fit.");
  const solution = solved.solution;
  const residuals = equations.map((eq) => eq.value - dot(eq.basis, solution));
  const chi2 = residuals.reduce((sum, residual, index) => sum + (residual / equations[index].sigma) ** 2, 0);
  const dof = Math.max(equations.length - nParams, 1);
  const varianceScale = Math.max(chi2 / dof, 1);
  const scaledUnc = (index) => Math.sqrt(Math.max((solved.covariance[index]?.[index] || 0) * varianceScale, 0));
  return {
    mode: isParallaxFit ? "pm_plx" : "pm",
    label: isParallaxFit ? "Fitted PM + parallax" : "Fitted PM",
    nRows: rows.length,
    t0,
    posRa: solution[0],
    pmra: solution[1],
    posDec: solution[2],
    pmdec: solution[3],
    plx: isParallaxFit ? solution[4] : null,
    fixedPlx,
    posRaUnc: scaledUnc(0),
    pmraUnc: scaledUnc(1),
    posDecUnc: scaledUnc(2),
    pmdecUnc: scaledUnc(3),
    plxUnc: isParallaxFit ? scaledUnc(4) : null,
    chi2,
    dof,
    reducedChi2: chi2 / dof,
  };
}

function buildAstrometryFitCurve(fit, prepared) {
  const xValues = prepared.rows.map((row) => row.plot_x).filter(finite);
  const xRange = paddedRange(xValues, atmEl["atm-phase-yearly"].checked ? [0, 1] : null);
  if (!xRange || !finite(xRange[0]) || !finite(xRange[1]) || xRange[0] === xRange[1]) {
    return null;
  }
  const n = 500;
  const centerEpoch = mean(prepared.rows.map((row) => row.plot_epoch_abs).filter(finite));
  const roundedCenter = Math.round(centerEpoch || fit.t0 || 0);
  const x = [];
  const ra = [];
  const dec = [];
  for (let index = 0; index < n; index += 1) {
    const frac = n <= 1 ? 0 : index / (n - 1);
    const xv = xRange[0] + frac * (xRange[1] - xRange[0]);
    const epoch = atmEl["atm-phase-yearly"].checked ? xv + roundedCenter : xv;
    const predicted = predictAstrometryFit(fit, prepared, epoch);
    x.push(xv);
    ra.push(predicted.ra);
    dec.push(predicted.dec);
  }
  return { x, ra, dec, label: fit.label };
}

function predictAstrometryFit(fit, prepared, epoch) {
  const dt = epoch - fit.t0;
  const pf = parallaxMotion(prepared.reference.ra, prepared.reference.dec, epoch);
  let ra = fit.posRa + fit.pmra * dt;
  let dec = fit.posDec + fit.pmdec * dt;
  const fitPlx = fit.mode === "pm_plx" ? fit.plx : fit.fixedPlx;
  if (finite(fitPlx)) {
    ra += Number(fitPlx) * pf.ra;
    dec += Number(fitPlx) * pf.dec;
  }
  if (atmEl["atm-subtract-pm"].checked) {
    ra -= prepared.pm.pmra * (epoch - prepared.reference.epoch);
    dec -= prepared.pm.pmdec * (epoch - prepared.reference.epoch);
  }
  if (atmEl["atm-subtract-plx"].checked) {
    const adoptedPlx = finite(prepared.parallax.value) ? Number(prepared.parallax.value) : 0;
    ra -= adoptedPlx * pf.ra;
    dec -= adoptedPlx * pf.dec;
  }
  return { ra, dec };
}

function astrometryFittedReferenceMarker(prepared) {
  const fit = atmState.fitResult;
  if (!fit || !finite(fit.posRa) || !finite(fit.posDec) || !finite(fit.t0)) return null;
  const epoch = Number(fit.t0);
  const coordinates = astrometryFittedCoordinate(fit, prepared);
  if (!coordinates || !finite(coordinates.ra) || !finite(coordinates.dec)) return null;
  const pf = parallaxMotion(prepared.reference.ra, prepared.reference.dec, epoch);
  let relRa = Number(fit.posRa);
  let relDec = Number(fit.posDec);
  if (atmEl["atm-subtract-pm"].checked) {
    relRa -= prepared.pm.pmra * (epoch - prepared.reference.epoch);
    relDec -= prepared.pm.pmdec * (epoch - prepared.reference.epoch);
  }
  if (atmEl["atm-subtract-plx"].checked) {
    const adoptedPlx = finite(prepared.parallax.value) ? Number(prepared.parallax.value) : 0;
    relRa -= adoptedPlx * pf.ra;
    relDec -= adoptedPlx * pf.dec;
  }
  return {
    id: "fitted-reference-position",
    plot_x: atmEl["atm-phase-yearly"].checked ? yearlyPhase(epoch) : epoch,
    plot_epoch_abs: epoch,
    rel_ra: relRa,
    rel_dec: relDec,
    plot_ra: coordinates.ra,
    plot_dec: coordinates.dec,
    fitLabel: fit.label,
    fitMeta: astrometryFitMeta(fit),
    posRaUnc: coordinates.raUncMas,
    posDecUnc: coordinates.decUncMas,
  };
}

function setAstrometryFitDisabled(disabled) {
  const rowCount = manualAstrometryFitRows(atmState.processedRows).length;
  const busy = Boolean(atmState.fitBusy);
  if (atmEl["atm-fit-pm"]) atmEl["atm-fit-pm"].disabled = busy || Boolean(disabled) || rowCount < 2;
  if (atmEl["atm-fit-plx"]) atmEl["atm-fit-plx"].disabled = busy || Boolean(disabled) || rowCount < 3;
  if (atmEl["atm-clear-fit"]) atmEl["atm-clear-fit"].disabled = busy || !atmState.fitResult;
  updateAstrometryFitControlState();
}

function manualAstrometryFitRows(rows) {
  return (rows || []).filter((row) => !isManuallyRejectedAstrometryRow(row));
}

function updateAstrometryFitSummary(message = "") {
  if (!atmEl["atm-fit-summary"]) return;
  if (message) {
    atmEl["atm-fit-summary"].textContent = message;
    return;
  }
  const fit = atmState.fitResult;
  if (!fit) {
    atmEl["atm-fit-summary"].textContent = "No fit computed";
    if (atmEl["atm-clear-fit"]) atmEl["atm-clear-fit"].disabled = true;
    return;
  }
  atmEl["atm-fit-summary"].innerHTML = astrometryFitInlineSummary(fit);
  if (atmEl["atm-clear-fit"]) atmEl["atm-clear-fit"].disabled = false;
}

function astrometryFitInlineSummary(fit) {
  const parts = [
    `<strong>${escapeHtml(fit.label)}</strong>`,
    `PMRA ${formatValueError(fit.pmra, fit.pmraUnc, "mas/yr")}`,
    `PMDEC ${formatValueError(fit.pmdec, fit.pmdecUnc, "mas/yr")}`,
  ];
  if (fit.mode === "pm_plx") {
    parts.push(`parallax ${formatValueError(fit.plx, fit.plxUnc, "mas")}`);
  } else if (finite(fit.fixedPlx) && Number(fit.fixedPlx) !== 0) {
    parts.push(`adopted parallax fixed at ${formatNumber(fit.fixedPlx, 2)} mas`);
  }
  if (fit.outlierMixture && finite(fit.nInliers) && finite(fit.nRows)) {
    parts.push(`inliers ${fit.nInliers}/${fit.nRows}`);
  } else {
    parts.push(`N=${fit.nRows}`);
  }
  if (atmState.manualRejectedIds.size) {
    parts.push(`manual rejects ${atmState.manualRejectedIds.size}`);
  }
  parts.push(`reduced chi2=${formatNumber(fit.reducedChi2, 2)}`);
  return parts.join(" | ");
}

function astrometrySelectedMissionLabels() {
  const missions = atmState.selectedMissions?.size
    ? [...atmState.selectedMissions]
    : (atmState.processedRows || []).map((row) => row.mission || "No mission");
  return [...new Set(missions.map((mission) => String(mission || "No mission")))];
}

function astrometryFitMissionCounts(prepared) {
  const counts = new Map();
  (prepared?.rows || []).forEach((row) => {
    if (
      !finite(row.plot_epoch_abs)
      || !finite(row.base_rel_ra)
      || !finite(row.base_rel_dec)
      || isManuallyRejectedAstrometryRow(row)
    ) {
      return;
    }
    const mission = String(row.mission || "No mission");
    counts.set(mission, (counts.get(mission) || 0) + 1);
  });
  return [...counts.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([mission, nData]) => ({ mission, nData }));
}

function buildAstrometryPushRequest(dryRun) {
  const fit = atmState.fitResult;
  const prepared = atmState.lastPrepared || prepareAstrometryRows();
  const fittedCoordinate = astrometryFittedCoordinate(fit, prepared);
  const target = atmState.payload?.target || {};
  return {
    dryRun: Boolean(dryRun),
    allowDuplicate: Boolean(atmEl["atm-push-allow-duplicate"]?.checked),
    target: {
      moca_oid: normalizedMocaOid(target.moca_oid) || normalizedMocaOid(atmState.selectedOid),
      designation: targetShortName(target),
    },
    push: {
      coordinate: Boolean(atmEl["atm-push-coordinate"]?.checked),
      pm: Boolean(atmEl["atm-push-pm"]?.checked),
      parallax: Boolean(atmEl["atm-push-parallax"]?.checked),
    },
    visibility: {
      isPublic: Boolean(atmEl["atm-push-is-public"]?.checked),
      rls: String(atmEl["atm-push-rls"]?.value || "").trim(),
    },
    metadata: {
      mocaPid: String(atmEl["atm-push-moca-pid"]?.value || "").trim(),
      origin: String(atmEl["atm-push-origin"]?.value || astrometryDefaultPushOrigin(fit)).trim(),
      comments: String(atmEl["atm-push-comments"]?.value || "").trim(),
      selectedMissions: astrometrySelectedMissionLabels(),
      manualRejectedIds: [...atmState.manualRejectedIds],
      manualRejectedCount: atmState.manualRejectedIds.size,
      automaticRejectedCount: finite(fit?.nOutliers) ? Number(fit.nOutliers) : (Array.isArray(fit?.outlierIds) ? fit.outlierIds.length : 0),
      missionCounts: astrometryFitMissionCounts(prepared),
    },
    fit,
    fittedCoordinate,
  };
}

async function runAstrometryPush(dryRun) {
  const reason = astrometryPushUnavailableReason();
  if (reason) {
    setAstrometryPushStatus(reason, "error");
    updateAstrometryPushControls();
    return;
  }
  const requestBody = buildAstrometryPushRequest(dryRun);
  const selectedLabels = astrometryPushSelectedLabels(requestBody.push);
  if (!dryRun && !window.confirm(`Push ${selectedLabels.join(", ")} to MOCAdb?`)) return;

  atmState.pushBusy = true;
  setAstrometryPushStatus(dryRun ? "Preparing push preview..." : "Pushing fitted values...");
  updateAstrometryPushControls();
  try {
    const payload = await postAstrometryJson("api/astrometry/fit/push", requestBody);
    setAstrometryPushStatus(astrometryPushResultMarkup(payload), payload?.ok ? "" : "error", true);
    if (!payload?.ok) return;
    if (!dryRun && payload.cleared?.astrometryObjects !== undefined) {
      setAstrometryStatus(`Pushed ${payload.insertedCount || 0} astrometry row${Number(payload.insertedCount) === 1 ? "" : "s"} to MOCAdb`, "");
    }
  } catch (error) {
    setAstrometryPushStatus(error.message || String(error), "error");
  } finally {
    atmState.pushBusy = false;
    updateAstrometryPushControls();
  }
}

function astrometryPushSelectedLabels(push) {
  const labels = [];
  if (push?.coordinate) labels.push("fitted coordinate");
  if (push?.pm) labels.push("fitted PM");
  if (push?.parallax) labels.push("fitted parallax");
  return labels.length ? labels : ["selected values"];
}

function astrometryPushResultMarkup(payload) {
  if (!payload) return "No response from MOCAdb push endpoint.";
  if (!payload.ok && payload.error && !payload.preparedRows) return escapeHtml(payload.error);
  const rows = payload.preparedRows || [];
  const duplicates = payload.duplicates || [];
  const title = payload.dryRun
    ? "Push preview"
    : `Inserted ${Number(payload.insertedCount || 0)} row${Number(payload.insertedCount) === 1 ? "" : "s"}`;
  const rowText = rows.length
    ? rows.map((row) => {
      const values = row.values || {};
      return `<li>${escapeHtml(row.label || row.kind)} -> ${escapeHtml(row.table)}${astrometryPushValueSnippet(row.kind, values)}</li>`;
    }).join("")
    : "<li>No rows prepared.</li>";
  const duplicateText = duplicates.length
    ? `<div class="astrometry-push-warning">${escapeHtml(payload.error || "Existing active rows match this push.")}</div><ul>${duplicates.map((row) => (
      `<li>${escapeHtml(row.label || row.kind)}: ${Number(row.count || 0)} match${Number(row.count) === 1 ? "" : "es"} by ${escapeHtml(row.basis || "origin")}</li>`
    )).join("")}</ul>`
    : "";
  const insertedText = payload.inserted?.length
    ? `<ul>${payload.inserted.map((row) => (
      `<li>${escapeHtml(row.label || row.kind)} inserted in ${escapeHtml(row.table)}${row.id ? ` id=${escapeHtml(row.id)}` : ""}</li>`
    )).join("")}</ul>`
    : "";
  const changelogText = payload.changelogId ? `<div>moca_changelog id=${escapeHtml(payload.changelogId)}</div>` : "";
  const provenance = payload.fitProvenance ? `<div>${escapeHtml(payload.fitProvenance)}</div>` : "";
  const meta = [
    payload.origin ? `origin=${payload.origin}` : "",
    payload.moca_pid ? `moca_pid=${payload.moca_pid}` : "",
    `rls=${payload.rls || "N/A"}`,
    `is_public=${Number(payload.is_public || 0)}`,
  ].filter(Boolean).join("; ");
  return `
    <div><strong>${escapeHtml(title)}</strong></div>
    <div>${escapeHtml(meta)}</div>
    ${provenance}
    <ul>${rowText}</ul>
    ${duplicateText}
    ${insertedText}
    ${changelogText}
  `;
}

function astrometryPushValueSnippet(kind, values) {
  if (!values) return "";
  if (kind === "pm") {
    return ` (${formatValueErrorSymbol(values.pmra_masyr, values.pmra_masyr_unc, "mas/yr")}, ${formatValueErrorSymbol(values.pmdec_masyr, values.pmdec_masyr_unc, "mas/yr")})`;
  }
  if (kind === "parallax") {
    return ` (${formatValueErrorSymbol(values.parallax_mas, values.parallax_mas_unc, "mas")})`;
  }
  if (kind === "coordinate") {
    return ` (${escapeHtml(formatRaSexagesimal(values.ra))}, ${escapeHtml(formatDecSexagesimal(values.dec))}, epoch ${formatNumber(values.measurement_epoch_yr, 4)})`;
  }
  return "";
}

function setAstrometryPushStatus(content, mode = "", html = false) {
  if (!atmEl["atm-push-status"]) return;
  if (html) atmEl["atm-push-status"].innerHTML = content || "";
  else atmEl["atm-push-status"].textContent = content || "";
  atmEl["atm-push-status"].classList.toggle("error", mode === "error");
}

function astrometryFitOutlierRows(prepared) {
  const fit = atmState.fitResult;
  if (!fit?.outlierMixture) return [];
  const ids = new Set((Array.isArray(fit.outlierIds) ? fit.outlierIds : []).map((id) => String(id)));
  if (!ids.size && Array.isArray(fit.responsibilities)) {
    fit.responsibilities.forEach((row) => {
      if (row?.inlier === false && row.id !== undefined && row.id !== null) ids.add(String(row.id));
    });
  }
  if (!ids.size) return [];
  return prepared.rows.filter((row) => ids.has(String(row.id)));
}

function astrometryManualRejectedRows(prepared) {
  if (!atmState.manualRejectedIds.size) return [];
  return prepared.rows.filter((row) => isManuallyRejectedAstrometryRow(row));
}

function astrometryFitInlierProbability(rowId) {
  const fit = atmState.fitResult;
  if (!Array.isArray(fit?.responsibilities)) return NaN;
  const match = fit.responsibilities.find((row) => String(row.id) === String(rowId));
  return finite(match?.inlierProbability) ? Number(match.inlierProbability) : NaN;
}

function astrometryFitOutlierHoverText(row) {
  const inlierProbability = astrometryFitInlierProbability(row.id);
  const probabilityLine = finite(inlierProbability)
    ? `<br><b>Fit inlier probability:</b> ${formatNumber(inlierProbability, 3)}`
    : "";
  return `${hoverText(row)}<br><b>PM-fit status:</b> rejected as outlier${probabilityLine}`;
}

function astrometryManualRejectedHoverText(row) {
  return `${hoverText(row)}<br><b>Manual fit status:</b> rejected from fit`;
}

function astrometryFitSigma(value) {
  const sigma = Number(value);
  return finite(sigma) && sigma > 0 ? Math.max(sigma, 1e-3) : 1;
}

function zeroMatrix(size) {
  return Array.from({ length: size }, () => new Array(size).fill(0));
}

function addWeightedEquation(normal, rhs, equations, basis, value, sigma) {
  if (!basis.every(finite) || !finite(value) || !finite(sigma) || sigma <= 0) return;
  const weight = 1 / sigma ** 2;
  for (let row = 0; row < basis.length; row += 1) {
    rhs[row] += weight * basis[row] * value;
    for (let col = 0; col < basis.length; col += 1) {
      normal[row][col] += weight * basis[row] * basis[col];
    }
  }
  equations.push({ basis, value, sigma });
}

function solveNormalEquations(normal, rhs) {
  const covariance = invertMatrix(normal);
  if (!covariance) return null;
  const solution = covariance.map((row) => row.reduce((sum, value, index) => sum + value * rhs[index], 0));
  return { solution, covariance };
}

function invertMatrix(matrix) {
  const n = matrix.length;
  const augmented = matrix.map((row, rowIndex) => [
    ...row.map(Number),
    ...Array.from({ length: n }, (_, colIndex) => rowIndex === colIndex ? 1 : 0),
  ]);
  for (let col = 0; col < n; col += 1) {
    let pivotRow = col;
    let pivotAbs = Math.abs(augmented[col][col]);
    for (let row = col + 1; row < n; row += 1) {
      const absValue = Math.abs(augmented[row][col]);
      if (absValue > pivotAbs) {
        pivotAbs = absValue;
        pivotRow = row;
      }
    }
    if (!finite(pivotAbs) || pivotAbs < 1e-12) return null;
    if (pivotRow !== col) {
      const tmp = augmented[col];
      augmented[col] = augmented[pivotRow];
      augmented[pivotRow] = tmp;
    }
    const pivot = augmented[col][col];
    for (let item = 0; item < 2 * n; item += 1) augmented[col][item] /= pivot;
    for (let row = 0; row < n; row += 1) {
      if (row === col) continue;
      const factor = augmented[row][col];
      for (let item = 0; item < 2 * n; item += 1) {
        augmented[row][item] -= factor * augmented[col][item];
      }
    }
  }
  return augmented.map((row) => row.slice(n));
}

function dot(values, params) {
  return values.reduce((sum, value, index) => sum + value * params[index], 0);
}

function astrometryPublicationInfo(row, fallback = "") {
  const raw = row || {};
  const explicitName = raw.publication_name || raw.reference || "";
  const sourceId = raw.moca_pid || raw.origin || "";
  const name = explicitName || sourceId || fallback || "";
  const rawBibcode = raw.publication_bibcode || raw.bibcode || "";
  const bibcode = rawBibcode || (looksLikeAdsBibcode(raw.moca_pid) ? raw.moca_pid : "");
  const hasSource = Boolean(explicitName || sourceId || rawBibcode || raw.bibcode);
  return {
    name,
    bibcode,
    query: hasSource ? (explicitName || sourceId || bibcode) : "",
  };
}

function astrometryPublicationMarkup(rowOrInfo, fallback = "") {
  const info = rowOrInfo && (rowOrInfo.name !== undefined || rowOrInfo.query !== undefined || rowOrInfo.bibcode !== undefined)
    ? rowOrInfo
    : astrometryPublicationInfo(rowOrInfo, fallback);
  const label = info.name || info.bibcode || fallback || "N/A";
  const url = astrometryAdsUrl(info);
  if (!url) return escapeHtml(label);
  return `<a href="${url}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`;
}

function astrometryAdsUrl(info) {
  const bibcode = String(info?.bibcode || "").trim();
  if (bibcode) {
    return `https://ui.adsabs.harvard.edu/abs/${encodeURIComponent(bibcode)}/abstract`;
  }
  const query = String(info?.query || "").trim();
  return query ? `https://ui.adsabs.harvard.edu/search/q=${encodeURIComponent(query)}` : "";
}

function looksLikeAdsBibcode(value) {
  return /^\d{4}.{14}[A-Za-z0-9.]$/.test(String(value || ""));
}

function summaryAnnotation(prepared) {
  const pm = prepared.pm;
  const plx = prepared.parallax;
  const coordRef = prepared.reference?.source;
  return {
    xref: "paper",
    yref: "paper",
    x: 0.01,
    y: 0.99,
    xanchor: "left",
    yanchor: "top",
    text: [
      `<b>PMRA:</b> ${formatValueError(pm.pmra, pm.pmraUnc, "mas/yr")}`,
      `<b>PMDEC:</b> ${formatValueError(pm.pmdec, pm.pmdecUnc, "mas/yr")}`,
      `<b>Parallax:</b> ${formatValueError(plx.value, plx.uncertainty, "mas")}`,
      `<br><b>PM ref:</b> ${astrometryPublicationMarkup(pm.source, pm.reference || "N/A")}`,
      `<b>Parallax ref:</b> ${astrometryPublicationMarkup(plx.source, plx.reference || "N/A")}`,
      `<b>Coord ref:</b> ${astrometryPublicationMarkup(coordRef, "N/A")}`,
    ].join(" | "),
    showarrow: false,
    font: { size: 13, color: "#252329" },
    bgcolor: "rgba(255,255,255,0.72)",
  };
}

function handleAstrometrySelection(event) {
  const ids = (event?.points || []).map((point) => point.customdata).filter((id) => id !== undefined && id !== null);
  atmState.selectedIds = new Set(ids);
  renderAstrometryTable();
  updateManualAstrometryRejectionControls();
}

function handleAstrometryClick(event) {
  const point = event?.points?.[0];
  if (!point || point.customdata === undefined || point.customdata === null) return;
  atmState.selectedIds = new Set([point.customdata]);
  renderAstrometryTable();
  updateManualAstrometryRejectionControls();
}

function handleAstrometryDeselect() {
  atmState.selectedIds.clear();
  renderAstrometryTable();
  updateManualAstrometryRejectionControls();
}

function astrometrySummarySection(title, sourceMarkup, lines, options = {}) {
  const source = sourceMarkup ? ` <span class="astrometry-summary-source">${sourceMarkup}</span>` : "";
  const meta = options.meta ? ` <span class="astrometry-summary-source">${escapeHtml(options.meta)}</span>` : "";
  return `
    <div class="astrometry-summary-section">
      <div class="astrometry-summary-title"><strong>${escapeHtml(title)}</strong>${source}${meta}</div>
      ${lines.map((line) => `<div class="astrometry-summary-line">${line}</div>`).join("")}
    </div>`;
}

function astrometrySummaryValueLine(labelHtml, value, error, unit) {
  return `<span class="astrometry-summary-symbol">${labelHtml}</span><span class="astrometry-summary-value">= ${formatValueErrorSymbol(value, error, unit)}</span>`;
}

function astrometrySummaryDifferenceLine(labelHtml, literatureValue, fittedValue, literatureError, fittedError, unit) {
  const delta = finite(literatureValue) && finite(fittedValue) ? Number(literatureValue) - Number(fittedValue) : NaN;
  const error = astrometryQuadratureError(literatureError, fittedError);
  const sigma = finite(delta) && finite(error) && Number(error) > 0 ? Math.abs(Number(delta)) / Number(error) : NaN;
  const sigmaText = finite(sigma) ? ` (${formatNumber(sigma, 2)} &sigma;)` : "";
  return `<span class="astrometry-summary-symbol">${labelHtml}</span><span class="astrometry-summary-value">= ${formatValueErrorSymbol(delta, error, unit)}${sigmaText}</span>`;
}

function astrometrySummarySubhead(text) {
  return `<span class="astrometry-summary-subhead">${escapeHtml(text)}</span>`;
}

function astrometrySummaryTextLine(label, value) {
  return `<span class="astrometry-summary-symbol">${escapeHtml(label)}</span><span class="astrometry-summary-value">= ${escapeHtml(value)}</span>`;
}

function astrometryCoordinateLines(coordinates) {
  return [
    astrometryCoordinateLine("&alpha;", coordinates.ra, coordinates.raUncMas, formatRaSexagesimal),
    astrometryCoordinateLine("&delta;", coordinates.dec, coordinates.decUncMas, formatDecSexagesimal),
    astrometrySummaryTextLine("epoch", `${formatNumber(coordinates.epoch, 4)} yr`),
  ];
}

function astrometryCoordinateLine(labelHtml, value, uncertainty, formatter) {
  const coordinate = finite(value) ? `${formatter(value)} (${formatNumber(value, 8)} deg)` : "N/A";
  const errorText = finite(uncertainty) && Number(uncertainty) > 0
    ? ` &plusmn; ${formatNumber(uncertainty, 2)} mas`
    : "";
  return `<span class="astrometry-summary-symbol">${labelHtml}</span><span class="astrometry-summary-value">= ${coordinate}${errorText}</span>`;
}

function astrometryCoordinateDifferenceLines(prepared, fit) {
  if (!fit || !finite(fit.posRa) || !finite(fit.posDec)) return [];
  return [
    astrometrySummarySubhead("literature - fitted"),
    astrometrySummaryDifferenceLine("&Delta;&alpha;", 0, fit.posRa, prepared.reference.raUncMas, fit.posRaUnc, "mas"),
    astrometrySummaryDifferenceLine("&Delta;&delta;", 0, fit.posDec, prepared.reference.decUncMas, fit.posDecUnc, "mas"),
  ];
}

function astrometryProperMotionDifferenceLines(prepared, fit) {
  if (!fit) return [];
  return [
    astrometrySummarySubhead("literature - fitted"),
    astrometrySummaryDifferenceLine("&Delta;&mu;<sub>&alpha;</sub>", prepared.pm.pmra, fit.pmra, prepared.pm.pmraUnc, fit.pmraUnc, "mas/yr"),
    astrometrySummaryDifferenceLine("&Delta;&mu;<sub>&delta;</sub>", prepared.pm.pmdec, fit.pmdec, prepared.pm.pmdecUnc, fit.pmdecUnc, "mas/yr"),
  ];
}

function astrometryParallaxDifferenceLines(prepared, fit) {
  if (!fit || fit.mode !== "pm_plx") return [];
  return [
    astrometrySummarySubhead("literature - fitted"),
    astrometrySummaryDifferenceLine("&Delta;&varpi;", prepared.parallax.value, fit.plx, prepared.parallax.uncertainty, fit.plxUnc, "mas"),
  ];
}

function astrometryFittedCoordinate(fit, prepared) {
  if (!fit || !finite(fit.posRa) || !finite(fit.posDec)) return null;
  const raDivisor = astrometryRaDegreeDivisor(prepared);
  const ra = finite(raDivisor) && Math.abs(raDivisor) > 1e-12
    ? Number(prepared.reference.ra) + Number(fit.posRa) / raDivisor
    : NaN;
  const dec = finite(prepared.reference.dec)
    ? Number(prepared.reference.dec) + Number(fit.posDec) / (3600 * 1000)
    : NaN;
  return {
    ra,
    dec,
    raUncMas: finite(fit.posRaUnc) ? Number(fit.posRaUnc) : null,
    decUncMas: finite(fit.posDecUnc) ? Number(fit.posDecUnc) : null,
    epoch: fit.t0,
  };
}

function astrometryFitMeta(fit) {
  const parts = [fit.label || "fit"];
  if (fit.outlierMixture && finite(fit.nInliers) && finite(fit.nRows)) {
    parts.push(`inliers ${fit.nInliers}/${fit.nRows}`);
  } else if (finite(fit.nRows)) {
    parts.push(`N=${fit.nRows}`);
  }
  if (finite(fit.reducedChi2)) parts.push(`reduced chi2=${formatNumber(fit.reducedChi2, 2)}`);
  return parts.join("; ");
}

function renderAstrometrySummary(prepared) {
  const target = atmState.payload.target || {};
  const rows = prepared.rows;
  const missionCount = new Set(rows.map((row) => row.mission)).size;
  const manualRejectedCount = astrometryManualRejectedRows(prepared).length;
  const recalcNote = prepared.usedFallbackRecalibration ? " Recalibrated-only filter had no rows, so all rows are shown." : "";
  const fit = atmState.fitResult;
  const fittedCoordinate = astrometryFittedCoordinate(fit, prepared);
  const sections = [
    astrometrySummarySection(
      "Reference coordinate",
      astrometryPublicationMarkup(prepared.reference.source, "N/A"),
      astrometryCoordinateLines(prepared.reference),
    ),
  ];
  if (fittedCoordinate) {
    sections.push(astrometrySummarySection(
      "Fitted coordinate",
      "",
      [
        ...astrometryCoordinateLines(fittedCoordinate),
        ...astrometryCoordinateDifferenceLines(prepared, fit),
      ],
      { meta: astrometryFitMeta(fit) },
    ));
  }
  sections.push(astrometrySummarySection(
    "Reference proper motion",
    astrometryPublicationMarkup(prepared.pm.source, prepared.pm.reference || "N/A"),
    [
      astrometrySummaryValueLine("&mu;<sub>&alpha;</sub>", prepared.pm.pmra, prepared.pm.pmraUnc, "mas/yr"),
      astrometrySummaryValueLine("&mu;<sub>&delta;</sub>", prepared.pm.pmdec, prepared.pm.pmdecUnc, "mas/yr"),
    ],
  ));
  if (fit) {
    sections.push(astrometrySummarySection(
      "Fitted proper motion",
      "",
      [
        astrometrySummaryValueLine("&mu;<sub>&alpha;</sub>", fit.pmra, fit.pmraUnc, "mas/yr"),
        astrometrySummaryValueLine("&mu;<sub>&delta;</sub>", fit.pmdec, fit.pmdecUnc, "mas/yr"),
        ...astrometryProperMotionDifferenceLines(prepared, fit),
      ],
    ));
  }
  sections.push(astrometrySummarySection(
    "Reference parallax",
    astrometryPublicationMarkup(prepared.parallax.source, prepared.parallax.reference || "N/A"),
    [astrometrySummaryValueLine("&varpi;", prepared.parallax.value, prepared.parallax.uncertainty, "mas")],
  ));
  if (fit?.mode === "pm_plx") {
    sections.push(astrometrySummarySection(
      "Fitted parallax",
      "",
      [
        astrometrySummaryValueLine("&varpi;", fit.plx, fit.plxUnc, "mas"),
        ...astrometryParallaxDifferenceLines(prepared, fit),
      ],
    ));
  }
  atmEl["atm-summary"].innerHTML = `
    <div class="astrometry-summary-meta">
      <strong>${escapeHtml(targetShortName(target))}</strong>
      <span>oid${escapeHtml(target.moca_oid)}</span>
      <span>${rows.length} measurements</span>
      <span>${missionCount} missions</span>
      ${manualRejectedCount ? `<span>${manualRejectedCount} manually rejected from fit</span>` : ""}
    </div>
    <div class="astrometry-summary-grid">${sections.join("")}</div>
    ${recalcNote ? `<div class="astrometry-summary-note">${escapeHtml(recalcNote.trim())}</div>` : ""}
  `;
}

function renderAstrometryTable() {
  const selected = atmState.selectedIds.size
    ? atmState.processedRows.filter((row) => atmState.selectedIds.has(row.id))
    : atmState.processedRows;
  const rows = selected.slice(0, 350);
  const missionStyles = astrometryMissionStyles(atmState.processedRows);
  atmEl["atm-table-title"].textContent = atmState.selectedIds.size ? "Selected measurements" : "Measurements";
  atmEl["atm-table-subtitle"].textContent = `${selected.length} row${selected.length === 1 ? "" : "s"}${selected.length > rows.length ? `, showing first ${rows.length}` : ""}`;
  if (!rows.length) {
    atmEl["atm-table"].innerHTML = `<div class="empty-table">No measurements to show.</div>`;
    return;
  }
  atmEl["atm-table"].innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>ID</th>
          <th>Mission</th>
          <th>Epoch</th>
          <th>R.A. offset</th>
          <th>Decl. offset</th>
          <th>R.A.</th>
          <th>Decl.</th>
          <th>Origin</th>
          <th>Calibration</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td class="astrometry-symbol-cell">${astrometrySymbolMarkup(row, missionStyles)}</td>
            <td>${escapeHtml(row.id)}</td>
            <td>${escapeHtml(row.mission || "")}</td>
            <td>${formatNumber(row.measurement_epoch_yr, 5)}</td>
            <td>${formatNumber(row.rel_ra, 2)} +/- ${formatNumber(row.ra_unc_mas, 2)} mas</td>
            <td>${formatNumber(row.rel_dec, 2)} +/- ${formatNumber(row.dec_unc_mas, 2)} mas</td>
            <td title="${formatNumber(row.plot_ra, 8)} deg">${formatRaSexagesimal(row.plot_ra)}</td>
            <td title="${formatNumber(row.plot_dec, 8)} deg">${formatDecSexagesimal(row.plot_dec)}</td>
            <td>${escapeHtml(row.origin || row.moca_pid || "")}</td>
            <td>${escapeHtml(row.calibration_method || "")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>`;
}

function astrometrySymbolMarkup(row, missionStyles) {
  const mission = String(row.mission || "No mission");
  const markerStyle = astrometryMarkerStyle(mission, missionStyles);
  const title = `${mission}: marker size ${markerStyle.size}, color ${markerStyle.color}`;
  return `<span class="astrometry-table-symbol" title="${escapeHtml(title)}" style="--atm-symbol-color: ${markerStyle.color}; --atm-symbol-size: ${markerStyle.size}px; --atm-symbol-opacity: ${markerStyle.opacity};"></span>`;
}

function astrometrySexagesimalTickSpec(range, axis) {
  if (!range || !finite(range[0]) || !finite(range[1]) || Number(range[0]) === Number(range[1])) return null;
  const count = 6;
  const lo = Number(range[0]);
  const hi = Number(range[1]);
  const step = (hi - lo) / (count - 1);
  const tickvals = Array.from({ length: count }, (_, index) => lo + step * index);
  return {
    tickvals,
    ticktext: tickvals.map((value) => formatAstrometryYForDisplay(axis, value, true)),
  };
}

function formatAstrometryYForDisplay(axis, value, displayAbsolute) {
  if (!displayAbsolute) return formatNumber(value, 2);
  return axis === "ra" ? formatRaSexagesimal(value) : formatDecSexagesimal(value);
}

function formatRaSexagesimal(degrees, precision = 2) {
  if (!finite(degrees)) return "N/A";
  let totalSeconds = normalizeDegrees(Number(degrees)) / 15 * 3600;
  totalSeconds = roundToPrecision(totalSeconds, precision);
  const daySeconds = 24 * 3600;
  if (totalSeconds >= daySeconds) totalSeconds -= daySeconds;
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds - hours * 3600) / 60);
  const seconds = totalSeconds - hours * 3600 - minutes * 60;
  return `${padInt(hours, 2)}:${padInt(minutes, 2)}:${formatPaddedSeconds(seconds, precision)}`;
}

function formatDecSexagesimal(degrees, precision = 2) {
  if (!finite(degrees)) return "N/A";
  const sign = Number(degrees) < 0 ? "-" : "+";
  let totalSeconds = roundToPrecision(Math.abs(Number(degrees)) * 3600, precision);
  const maxSeconds = 90 * 3600;
  if (totalSeconds > maxSeconds) totalSeconds = maxSeconds;
  const deg = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds - deg * 3600) / 60);
  const seconds = totalSeconds - deg * 3600 - minutes * 60;
  return `${sign}${padInt(deg, 2)}:${padInt(minutes, 2)}:${formatPaddedSeconds(seconds, precision)}`;
}

function roundToPrecision(value, precision) {
  const scale = 10 ** precision;
  return Math.round(Number(value) * scale) / scale;
}

function padInt(value, width) {
  return String(Math.trunc(Math.abs(value))).padStart(width, "0");
}

function formatPaddedSeconds(value, precision) {
  const text = Number(value).toFixed(precision);
  return text.padStart(precision > 0 ? 3 + precision : 2, "0");
}

function hoverText(row) {
  return [
    `<b>ID:</b> ${escapeHtml(row.id)}`,
    `<b>Mission:</b> ${escapeHtml(row.mission || "N/A")}`,
    `<b>Epoch:</b> ${formatNumber(row.measurement_epoch_yr, 5)} yr`,
    `<b>R.A. offset:</b> ${formatNumber(row.rel_ra, 2)} +/- ${formatNumber(row.ra_unc_mas, 2)} mas`,
    `<b>Decl. offset:</b> ${formatNumber(row.rel_dec, 2)} +/- ${formatNumber(row.dec_unc_mas, 2)} mas`,
    `<b>R.A.:</b> ${formatRaSexagesimal(row.plot_ra)} (${formatNumber(row.plot_ra, 8)} deg)`,
    `<b>Decl.:</b> ${formatDecSexagesimal(row.plot_dec)} (${formatNumber(row.plot_dec, 8)} deg)`,
    `<b>Reference:</b> ${escapeHtml(row.moca_pid || "N/A")}`,
    `<b>Origin:</b> ${escapeHtml(row.origin || "N/A")}`,
    `<b>Bandpass:</b> ${escapeHtml(row.moca_psid || "N/A")}`,
    `<b>Calibration:</b> ${escapeHtml(row.calibration_method || "N/A")}`,
    `<b>Comments:</b> ${escapeHtml(row.comments || "")}`,
  ].join("<br>");
}

function referenceAstrometryHoverText(row, isRa) {
  return [
    "<b>Reference astrometry</b>",
    `<b>ID:</b> ${escapeHtml(row.id)}`,
    `<b>Epoch:</b> ${formatNumber(row.plot_epoch_abs, 5)} yr`,
    `<b>${isRa ? "R.A." : "Decl."} offset:</b> ${formatNumber(isRa ? row.rel_ra : row.rel_dec, 2)} mas`,
    `<b>R.A.:</b> ${formatRaSexagesimal(row.plot_ra)} (${formatNumber(row.plot_ra, 8)} deg)`,
    `<b>Decl.:</b> ${formatDecSexagesimal(row.plot_dec)} (${formatNumber(row.plot_dec, 8)} deg)`,
    `<b>Publication:</b> ${astrometryPublicationMarkup(row, row.moca_pid || "N/A")}`,
    `<b>Bibcode:</b> ${row.publication_bibcode || row.bibcode ? astrometryPublicationMarkup({ name: row.publication_bibcode || row.bibcode, bibcode: row.publication_bibcode || row.bibcode }) : "N/A"}`,
    `<b>Mission:</b> ${escapeHtml(row.mission_name || "N/A")}`,
    `<b>Data release:</b> ${escapeHtml(row.data_release || "N/A")}`,
    `<b>Origin:</b> ${escapeHtml(row.origin || row.moca_pid || "N/A")}`,
    `<b>Comments:</b> ${escapeHtml(row.comments || "")}`,
  ].join("<br>");
}

function fittedReferenceHoverText(row, isRa) {
  return [
    "<b>Fitted reference position</b>",
    `<b>Fit:</b> ${escapeHtml(row.fitMeta || row.fitLabel || "fit")}`,
    `<b>Epoch:</b> ${formatNumber(row.plot_epoch_abs, 5)} yr`,
    `<b>${isRa ? "R.A." : "Decl."} offset:</b> ${formatNumber(isRa ? row.rel_ra : row.rel_dec, 2)} mas`,
    `<b>Fitted R.A.:</b> ${formatRaSexagesimal(row.plot_ra)} (${formatNumber(row.plot_ra, 8)} deg) +/- ${formatNumber(row.posRaUnc, 2)} mas`,
    `<b>Fitted Decl.:</b> ${formatDecSexagesimal(row.plot_dec)} (${formatNumber(row.plot_dec, 8)} deg) +/- ${formatNumber(row.posDecUnc, 2)} mas`,
  ].join("<br>");
}

function renderEmptyAstrometry(message) {
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
  Plotly.react(atmEl["atm-ra-plot"], [], layout, plotConfig("astrometry_ra_empty"));
  Plotly.react(atmEl["atm-dec-plot"], [], layout, plotConfig("astrometry_dec_empty"));
  atmEl["atm-summary"].textContent = message;
  atmEl["atm-table"].innerHTML = "";
  atmState.processedRows = [];
  atmState.lastPrepared = null;
  atmState.fitResult = null;
  setAstrometryExportDisabled(true);
  setAstrometryFitDisabled(true);
  updateAstrometryFitSummary();
  setAstrometryLoading(false);
}

const astrometryExportColumns = ["id", "mission", "measurement_epoch_yr", "rel_ra", "rel_dec", "ra_unc_mas", "dec_unc_mas", "plot_ra", "plot_dec", "origin", "moca_pid", "calibration_method", "comments"];
const astrometryNumericExportColumns = new Set(["id", "measurement_epoch_yr", "rel_ra", "rel_dec", "ra_unc_mas", "dec_unc_mas", "plot_ra", "plot_dec", "moca_pid"]);

function exportAstrometry(format) {
  const rows = atmState.selectedIds.size
    ? atmState.processedRows.filter((row) => atmState.selectedIds.has(row.id))
    : atmState.processedRows;
  if (!rows.length) return;
  MocaExport.saveTable(format, {
    rows,
    columns: astrometryExportColumns,
    numericColumns: astrometryNumericExportColumns,
    filenameBase: `moca_astrometry_oid_${atmState.selectedOid || "unknown"}`,
    tableName: "moca_astrometry",
    resourceName: "MOCAdb Astrometric Explorer",
    extName: "ASTROM",
  });
}

function setAstrometryExportDisabled(disabled) {
  for (const id of ["atm-export-csv", "atm-export-tsv", "atm-export-fits", "atm-export-votable"]) {
    if (atmEl[id]) atmEl[id].disabled = disabled;
  }
}

async function clearAstrometryCache() {
  atmEl["atm-clear-cache-bottom"].disabled = true;
  atmEl["atm-clear-cache-status"].textContent = "Clearing...";
  atmEl["atm-clear-cache-status"].classList.remove("error");
  try {
    const payload = await postAstrometryJson("api/astrometry/cache/clear", {});
    if (!payload.ok) throw new Error(payload.error || "Cache clear failed");
    const cleared = payload.cleared?.astrometryObjects || 0;
    atmEl["atm-clear-cache-status"].textContent = `Cleared ${cleared} cached payload${cleared === 1 ? "" : "s"}.`;
    if (atmState.selectedOid !== null) await loadAstrometryObject();
  } catch (error) {
    atmEl["atm-clear-cache-status"].textContent = error.message;
    atmEl["atm-clear-cache-status"].classList.add("error");
  } finally {
    atmEl["atm-clear-cache-bottom"].disabled = false;
  }
}

function parallaxMotion(raDeg, decDeg, epoch) {
  const epochs = Array.isArray(epoch) ? epoch : [epoch];
  const ra = rad(raDeg);
  const dec = rad(decDeg);
  const cosRa = Math.cos(ra);
  const sinRa = Math.sin(ra);
  const cosDec = Math.cos(dec);
  const sinDec = Math.sin(dec);
  const out = epochs.map((value) => {
    const n = (Number(value) - 2000.0) * 365.25;
    const meanLong = rad(normalizeDegrees(280.460 + 0.9856474 * n));
    const anomaly = rad(normalizeDegrees(357.528 + 0.9856003 * n));
    const sunLong = meanLong + rad(1.915) * Math.sin(anomaly) + rad(0.020) * Math.sin(2 * anomaly);
    const obliquity = rad(23.439 - 0.0000004 * n);
    const cosObl = Math.cos(obliquity);
    const sinObl = Math.sin(obliquity);
    const cosSun = Math.cos(sunLong);
    const sinSun = Math.sin(sunLong);
    return {
      ra: (cosRa * cosObl * sinSun - sinRa * cosSun) * cosDec,
      dec: cosDec * sinObl * sinSun - cosRa * sinDec * cosSun - sinRa * sinDec * cosObl * sinSun,
    };
  });
  return Array.isArray(epoch) ? out : out[0];
}

function normalizeDegrees(value) {
  return ((value % 360) + 360) % 360;
}

function yearlyPhase(epoch) {
  return ((Number(epoch) % 1) + 1) % 1;
}

function paddedRange(values, fixed) {
  if (fixed) return fixed;
  const finiteValues = values.filter(finite);
  if (!finiteValues.length) return undefined;
  const min = Math.min(...finiteValues);
  const max = Math.max(...finiteValues);
  if (min === max) return [min - 1, max + 1];
  const pad = 0.06 * (max - min);
  return [min - pad, max + pad];
}

function targetLabel(target) {
  return `oid${target?.moca_oid || atmState.selectedOid}: ${targetShortName(target)}`;
}

function targetShortName(target) {
  return target?.designation || target?.designations?.[0] || `oid${target?.moca_oid || atmState.selectedOid || ""}`;
}

function setAstrometryStatus(text, mode = "") {
  atmEl["atm-status"].textContent = text;
  atmEl["atm-status"].className = `status${mode ? ` ${mode}` : ""}`;
}

function setAstrometryLoading(loading) {
  atmEl["atm-plot-loader"].classList.toggle("is-visible", Boolean(loading));
}

function updateAstrometryUrl() {
  const params = new URLSearchParams(window.location.search);
  if (atmState.selectedOid !== null) {
    params.set("moca_oid", atmState.selectedOid);
    params.delete("oid");
  } else {
    params.delete("moca_oid");
    params.delete("oid");
  }
  if (atmState.hasUserMissionChoice && atmState.selectedMissions.size) params.set("missions", [...atmState.selectedMissions].join(","));
  else params.delete("missions");
  setBoolParam(params, "subtract_pm", atmEl["atm-subtract-pm"].checked);
  setBoolParam(params, "subtract_plx", atmEl["atm-subtract-plx"].checked);
  setBoolParam(params, "phase", atmEl["atm-phase-yearly"].checked);
  setBoolParam(params, "bin", atmEl["atm-bin"].checked);
  setBoolParam(params, "display_absolute", atmEl["atm-display-absolute"].checked);
  setBoolParam(params, "display_merged", atmEl["atm-display-merged"].checked);
  setBoolParam(params, "revert_raw", atmEl["atm-revert-raw"].checked);
  if (selectedAstrometryFitMethod() === "ultranest") params.set("fit_method", "ultranest");
  else params.delete("fit_method");
  if (atmEl["atm-fit-outlier-mixture"] && !atmEl["atm-fit-outlier-mixture"].checked) params.set("fit_outlier_mixture", "0");
  else params.delete("fit_outlier_mixture");
  if (!atmEl["atm-display-reference"].checked) params.set("display_reference", "0");
  else params.delete("display_reference");
  if (!atmEl["atm-adjust-reference"].checked) params.set("adjust_ref", "0");
  else params.delete("adjust_ref");
  if (!atmEl["atm-only-recalibrated"].checked) params.set("only_recalibrated", "0");
  else params.delete("only_recalibrated");
  const nextUrl = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", nextUrl);
}

function setBoolParam(params, key, checked) {
  if (checked) params.set(key, "1");
  else params.delete(key);
}

function apiParams() {
  const source = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "user", "username", "pwd", "password", "dbase", "db", "database", "port", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  return params;
}

async function fetchAstrometryJson(path) {
  const params = apiParams();
  const separator = path.includes("?") ? "&" : "?";
  return fetchJsonUrl(atmAppUrl(`${path}${params.toString() ? `${separator}${params.toString()}` : ""}`));
}

async function postAstrometryJson(path, body) {
  const params = apiParams();
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(atmAppUrl(`${path}${params.toString() ? `${separator}${params.toString()}` : ""}`), {
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

function openMocaReport(oid) {
  const url = mocaReportUrl(oid);
  if (url) window.open(url, "_blank", "noopener");
}

function currentAstrometryReportOid() {
  return (
    normalizedMocaOid(atmState.selectedOid)
    || normalizedMocaOid(atmState.payload?.target?.moca_oid)
    || normalizedMocaOid(new URLSearchParams(window.location.search).get("moca_oid") || new URLSearchParams(window.location.search).get("oid"))
  );
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

function formatValueError(value, error, unit) {
  if (!finite(value)) return "N/A";
  if (!finite(error) || Number(error) <= 0) return `${formatNumber(value, 2)} ${unit}`;
  return `${formatNumber(value, 2)} +/- ${formatNumber(error, 2)} ${unit}`;
}

function formatValueErrorSymbol(value, error, unit) {
  if (!finite(value)) return "N/A";
  const safeUnit = escapeHtml(unit);
  if (!finite(error) || Number(error) <= 0) return `${formatNumber(value, 2)} ${safeUnit}`;
  return `${formatNumber(value, 2)} &plusmn; ${formatNumber(error, 2)} ${safeUnit}`;
}

function astrometryQuadratureError(...values) {
  const finiteValues = values.filter((value) => finite(value) && Number(value) > 0).map(Number);
  if (!finiteValues.length) return NaN;
  return Math.sqrt(finiteValues.reduce((sum, value) => sum + value ** 2, 0));
}

function formatNumber(value, digits) {
  return finite(value) ? Number(value).toFixed(digits) : "N/A";
}

function mean(values) {
  const finiteValues = values.filter(finite).map(Number);
  if (!finiteValues.length) return NaN;
  return finiteValues.reduce((sum, value) => sum + value, 0) / finiteValues.length;
}

function median(values) {
  const finiteValues = values.filter(finite).map(Number).sort((a, b) => a - b);
  if (!finiteValues.length) return NaN;
  const mid = Math.floor(finiteValues.length / 2);
  return finiteValues.length % 2 ? finiteValues[mid] : 0.5 * (finiteValues[mid - 1] + finiteValues[mid]);
}

function finite(value) {
  return Number.isFinite(Number(value));
}

function parseInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

function asFalse(value) {
  return ["0", "false", "no", "off"].includes(String(value || "").toLowerCase());
}

function rad(value) {
  return Number(value) * Math.PI / 180;
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

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
