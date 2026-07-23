const speDefaultSpecids = [13510];
const speDefaultNorm = "0.95-1.35";
const speDefaultBinsPerMicron = 0;
const speDefaultDisplayBinsPerMicron = 200;
const speDefaultShowFeatures = true;
const speDefaultPixPerResolutionElement = 2.2;
const speLowResolutionResolvingPowerPerPixelThreshold = 45;
const speSpeedOfLight = 299792458.0;
const speColors = ["#377EB8", "#E41A1C", "#4DAF4A", "#984EA3", "#FF7F00", "#A65628", "#F781BF", "#999999", "#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3"];

const speFeatureBands = globalThis.mocaBrownDwarfSpectralFeatureBands || [];

const speState = {
  selected: [],
  payload: null,
  processed: [],
  selectedPoints: [],
  searchTimer: null,
  loadToken: 0,
  ignoreBusy: false,
  authContext: { role: "", hasCredentials: false },
  ignoreSpecids: new Set(),
  ignoreSelectionInitialized: false,
  dragSpecid: null,
  logTickRefreshTimer: null,
  refreshingLogTicks: false,
  renderToken: 0,
};

const speEl = {};

document.addEventListener("DOMContentLoaded", initSpectraExplorer);

const speAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function speAppUrl(path) {
  const normalized = String(path || "").replace(/^\/+/, "");
  return new URL(normalized, speAppBaseUrl).toString();
}

async function initSpectraExplorer() {
  collectSpectraElements();
  readSpectraUrlState();
  updateSpectraDisplayResolutionControls();
  await loadSpectraAuthContext();
  updateSpectraManagementVisibility();
  bindSpectraControls();
  renderSelectedSpectra();
  await loadSelectedSpectrumLabels();
  await loadSpectra();
}

function collectSpectraElements() {
  [
    "spe-status",
    "spe-search",
    "spe-results",
    "spe-selected-list",
    "spe-load",
    "spe-clear-selected",
    "spe-hover",
    "spe-error-shade",
    "spe-snr",
    "spe-hide-ignored",
    "spe-xlog",
    "spe-ylog",
    "spe-fnu",
    "spe-showfeatures",
    "spe-disable-lowres-wrap",
    "spe-disable-lowres",
    "spe-decrease-resolution",
    "spe-display-bins-wrap",
    "spe-display-bins",
    "spe-xrange-min",
    "spe-xrange-max",
    "spe-reset-xrange",
    "spe-normalize",
    "spe-normrange",
    "spe-reset-norm",
    "spe-management-tools",
    "spe-ignore-spectrum-list",
    "spe-ignore-all-spectra",
    "spe-ignore-no-spectra",
    "spe-ignore-summary",
    "spe-ignore-selected",
    "spe-ignore-status",
    "spe-plot",
    "spe-plot-loader",
    "spe-summary",
    "spe-hint",
    "spe-export-csv",
    "spe-export-tsv",
    "spe-export-fits",
    "spe-export-votable",
    "spe-clear-cache",
    "spe-clear-cache-bottom",
    "spe-clear-cache-status",
    "spe-table-title",
    "spe-table-subtitle",
    "spe-download-links",
    "spe-table",
  ].forEach((id) => {
    speEl[id] = document.getElementById(id);
  });
}

function readSpectraUrlState() {
  const params = new URLSearchParams(window.location.search);
  const rawSpecids = params.get("specids") || params.get("moca_specid") || params.get("specid") || speDefaultSpecids.join(",");
  const specids = rawSpecids.split(",").map((item) => parseInteger(item.trim())).filter((value) => value !== null);
  speState.selected = uniqueIntegers(specids.length ? specids : speDefaultSpecids).map((specid) => ({ specid, label: `specid${specid}` }));
  speEl["spe-hover"].checked = asBool(params.get("hover"));
  speEl["spe-error-shade"].checked = asBool(params.get("error_shade") || params.get("errorshade"));
  speEl["spe-snr"].checked = asBool(params.get("snr") || params.get("sn_per_pixel"));
  speEl["spe-hide-ignored"].checked = asBool(params.get("include_ignored") || params.get("show_ignored"))
    ? false
    : !asFalse(params.get("hide_ignored") || params.get("hide_ignored_points"));
  speEl["spe-xlog"].checked = asBool(params.get("xlog"));
  speEl["spe-ylog"].checked = asBool(params.get("ylog"));
  speEl["spe-fnu"].checked = asBool(params.get("fnu_jy") || params.get("fnu"));
  speEl["spe-showfeatures"].checked = params.has("showfeatures")
    ? !asFalse(params.get("showfeatures"))
    : speDefaultShowFeatures;
  speEl["spe-disable-lowres"].checked = asBool(params.get("disable_lowres"));
  speEl["spe-decrease-resolution"].checked = asBool(
    params.get("decrease_resolution") || params.get("decrease_resolving_power") || params.get("display_lowres")
  );
  speEl["spe-display-bins"].value = (
    params.get("display_bins")
    || params.get("display_bins_per_micron")
    || params.get("decrease_resolution_bins")
    || String(speDefaultDisplayBinsPerMicron)
  );
  const displayXRange = parseSpectraDisplayXRangeUrl(params);
  speEl["spe-xrange-min"].value = displayXRange.min ?? "";
  speEl["spe-xrange-max"].value = displayXRange.max ?? "";
  speEl["spe-normalize"].checked = !asFalse(params.get("normalize"));
  speEl["spe-normrange"].value = params.get("norm") || speDefaultNorm;
}

function bindSpectraControls() {
  speEl["spe-search"].addEventListener("input", () => {
    const value = speEl["spe-search"].value.trim();
    clearTimeout(speState.searchTimer);
    speState.searchTimer = setTimeout(() => searchSpectraExplorer(value), 250);
  });
  speEl["spe-search"].addEventListener("focus", () => {
    const value = speEl["spe-search"].value.trim();
    if (value) searchSpectraExplorer(value);
  });
  document.addEventListener("click", (event) => {
    if (!speEl["spe-results"].contains(event.target) && event.target !== speEl["spe-search"]) {
      speEl["spe-results"].hidden = true;
    }
  });
  speEl["spe-load"].addEventListener("click", loadSpectra);
  speEl["spe-clear-selected"].addEventListener("click", () => {
    speState.selected = [];
    speState.payload = null;
    speState.processed = [];
    renderSelectedSpectra();
    renderEmptySpectra("Select one or more spectra");
    updateSpectraIgnoreControls();
    updateSpectraUrl();
    speEl["spe-search"].focus();
  });
  for (const id of ["spe-hover", "spe-error-shade", "spe-snr", "spe-xlog", "spe-ylog", "spe-fnu", "spe-showfeatures", "spe-disable-lowres", "spe-decrease-resolution", "spe-normalize"]) {
    speEl[id].addEventListener("change", () => {
      if (id === "spe-decrease-resolution") updateSpectraDisplayResolutionControls();
      renderSpectra({
        preserveViewport: true,
        preserveYAxis: !["spe-snr", "spe-fnu", "spe-normalize"].includes(id),
      });
      updateSpectraUrl();
    });
  }
  const renderDisplayBinning = debounce(() => {
    if (!spectraDisplayResolutionDecreased()) {
      updateSpectraUrl();
      return;
    }
    renderSpectra({ preserveViewport: true });
    updateSpectraUrl();
  }, 180);
  speEl["spe-display-bins"].addEventListener("input", renderDisplayBinning);
  speEl["spe-display-bins"].addEventListener("change", () => {
    updateSpectraDisplayResolutionControls();
    renderSpectra({ preserveViewport: true });
    updateSpectraUrl();
  });
  const renderDisplayXRange = debounce(() => {
    renderSpectra();
    updateSpectraUrl();
  }, 180);
  for (const id of ["spe-xrange-min", "spe-xrange-max"]) {
    speEl[id].addEventListener("input", renderDisplayXRange);
    speEl[id].addEventListener("change", () => {
      renderSpectra();
      updateSpectraUrl();
    });
  }
  speEl["spe-reset-xrange"].addEventListener("click", () => {
    speEl["spe-xrange-min"].value = "";
    speEl["spe-xrange-max"].value = "";
    renderSpectra();
    updateSpectraUrl();
  });
  speEl["spe-hide-ignored"].addEventListener("change", () => loadSpectra({ preserveViewport: true }));
  speEl["spe-normrange"].addEventListener("change", () => {
    renderSpectra({ preserveViewport: true, preserveYAxis: false });
    updateSpectraUrl();
  });
  speEl["spe-reset-norm"].addEventListener("click", () => {
    speEl["spe-normrange"].value = speDefaultNorm;
    renderSpectra({ preserveViewport: true, preserveYAxis: false });
    updateSpectraUrl();
  });
  if (speEl["spe-ignore-selected"]) {
    speEl["spe-ignore-selected"].addEventListener("click", ignoreSelectedSpectralRows);
  }
  if (speEl["spe-ignore-all-spectra"]) {
    speEl["spe-ignore-all-spectra"].addEventListener("click", () => {
      speState.ignoreSpecids = new Set((speState.processed || []).map((spectrum) => Number(spectrum.specid)));
      speState.ignoreSelectionInitialized = true;
      renderSpectraIgnoreTraceChoices();
      updateSpectraIgnoreControls();
    });
  }
  if (speEl["spe-ignore-no-spectra"]) {
    speEl["spe-ignore-no-spectra"].addEventListener("click", () => {
      speState.ignoreSpecids = new Set();
      speState.ignoreSelectionInitialized = true;
      renderSpectraIgnoreTraceChoices();
      updateSpectraIgnoreControls();
    });
  }
  speEl["spe-export-csv"].addEventListener("click", () => exportPlottedSpectra("csv"));
  speEl["spe-export-tsv"].addEventListener("click", () => exportPlottedSpectra("tsv"));
  speEl["spe-export-fits"].addEventListener("click", () => exportPlottedSpectra("fits"));
  speEl["spe-export-votable"].addEventListener("click", () => exportPlottedSpectra("votable"));
  if (speEl["spe-clear-cache"]) speEl["spe-clear-cache"].addEventListener("click", clearSpectraCache);
  speEl["spe-clear-cache-bottom"].addEventListener("click", clearSpectraCache);
  window.addEventListener("resize", debounce(() => {
    if (!speEl["spe-results"].hidden) positionSpectraSearchPopup();
    if (speState.payload) renderSpectra();
  }, 150));
}

async function loadSelectedSpectrumLabels() {
  if (!speState.selected.length) return;
  const params = apiParams();
  params.set("specids", speState.selected.map((item) => item.specid).join(","));
  const payload = await fetchJsonUrl(speAppUrl(`api/spectra/search?${params.toString()}`));
  if (!payload.ok) return;
  const metadata = new Map((payload.options || []).map((item) => [Number(item.value), spectraMetadataFromOption(item)]));
  speState.selected = speState.selected.map((item) => {
    const nextMetadata = metadata.get(item.specid);
    return nextMetadata
      ? { ...item, label: nextMetadata.label || item.label, metadata: { ...(item.metadata || {}), ...nextMetadata } }
      : item;
  });
  renderSelectedSpectra();
}

async function searchSpectraExplorer(query) {
  if (!query) {
    speEl["spe-results"].hidden = true;
    return;
  }
  if (query.length < 2 && !/^\d+$/.test(query)) {
    speEl["spe-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    showSpectraSearchPopup();
    return;
  }
  const params = apiParams();
  params.set("q", query);
  const payload = await fetchJsonUrl(speAppUrl(`api/spectra/search?${params.toString()}`));
  if (!payload.ok) {
    speEl["spe-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
    showSpectraSearchPopup();
    return;
  }
  renderSpectraSearchResults(payload.options || []);
}

function renderSpectraSearchResults(results) {
  if (!results.length) {
    speEl["spe-results"].innerHTML = `<div class="designation-result-note">No spectra found</div>`;
    showSpectraSearchPopup();
    return;
  }
  speEl["spe-results"].innerHTML = results.map((result, index) => (
    `<button class="designation-result spt-spectrum-result" type="button" data-index="${index}"><span>${escapeHtml(result.label || `specid${result.value}`)}</span></button>`
  )).join("");
  speEl["spe-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      const result = results[Number(button.dataset.index)];
      addSelectedSpectrum(Number(result.value), result);
      speEl["spe-search"].value = "";
      speEl["spe-results"].hidden = true;
      await loadSpectra();
    });
  });
  showSpectraSearchPopup();
}

function showSpectraSearchPopup() {
  positionSpectraSearchPopup();
  speEl["spe-results"].hidden = false;
}

function positionSpectraSearchPopup() {
  const input = speEl["spe-search"];
  const popup = speEl["spe-results"];
  if (!input || !popup) return;
  const rect = input.getBoundingClientRect();
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - 360));
  const available = Math.max(320, window.innerWidth - left - 16);
  const width = Math.min(860, available);
  popup.style.position = "fixed";
  popup.style.left = `${left}px`;
  popup.style.top = `${rect.bottom + 4}px`;
  popup.style.width = `${Math.max(rect.width, width)}px`;
}

function addSelectedSpectrum(specid, labelOrMetadata) {
  if (!Number.isFinite(specid)) return;
  if (speState.selected.some((item) => item.specid === specid)) return;
  const metadata = typeof labelOrMetadata === "object"
    ? spectraMetadataFromOption(labelOrMetadata)
    : { moca_specid: specid, label: labelOrMetadata || `specid${specid}` };
  speState.selected.push({ specid, label: metadata.label || `specid${specid}`, metadata });
  renderSelectedSpectra();
  updateSpectraUrl();
}

function renderSelectedSpectra() {
  bindSelectedSpectrumDragHandlers();
  if (!speState.selected.length) {
    speEl["spe-selected-list"].innerHTML = `<div class="plot-hint">No spectra selected</div>`;
    return;
  }
  speEl["spe-selected-list"].innerHTML = speState.selected.map((item) => `
    ${selectedSpectrumTokenHtml(item)}
  `).join("");
  speEl["spe-selected-list"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      const specid = Number(button.dataset.specid);
      speState.selected = speState.selected.filter((item) => item.specid !== specid);
      renderSelectedSpectra();
      updateSpectraUrl();
      if (speState.selected.length) await loadSpectra();
      else renderEmptySpectra("Select one or more spectra");
    });
  });
}

function selectedSpectrumTokenHtml(item) {
  const metadata = selectedSpectrumMetadata(item);
  const specid = Number(item.specid);
  const oid = normalizedMocaOid(metadata.moca_oid);
  const color = spectraColorForSpecid(specid);
  const titleParts = [
    spectrumName(metadata, specid),
    oid ? `OID ${oid}` : "",
    `SpecID ${specid}`,
    metadata.spectral_type ? `SpT ${metadata.spectral_type}` : "",
    instrumentLabel(metadata),
    metadata.data_collection_date || "",
    metadata.spectrum_name || "",
  ].filter(Boolean);
  const idParts = [`specid ${specid}`, oid ? `oid ${oid}` : ""].filter(Boolean).join(" · ");
  const detailParts = [
    metadata.spectral_type ? `SpT ${metadata.spectral_type}` : "",
    instrumentLabel(metadata),
    metadata.data_collection_date || "",
  ].filter(Boolean).join(" · ");
  const spectrumNameText = metadata.spectrum_name && metadata.spectrum_name !== metadata.designation
    ? metadata.spectrum_name
    : "";
  return `
    <div class="spectra-token" data-specid="${specid}" title="${escapeHtml(titleParts.join("\n"))}">
      <span class="spectra-token-swatch spectra-token-drag-handle" draggable="true" data-specid="${specid}" title="Drag to reorder" aria-label="Drag specid ${specid} to reorder" style="--swatch-color: ${escapeHtml(color)}"></span>
      <span class="spectra-token-body">
        <span class="spectra-token-title">${escapeHtml(spectrumName(metadata, specid))}</span>
        <span class="spectra-token-meta">${escapeHtml(idParts)}</span>
        ${detailParts ? `<span class="spectra-token-meta">${escapeHtml(detailParts)}</span>` : ""}
        ${spectrumNameText ? `<span class="spectra-token-meta spectra-token-spectrum-name">${escapeHtml(spectrumNameText)}</span>` : ""}
      </span>
      <button type="button" aria-label="Remove specid ${item.specid}" data-specid="${item.specid}">x</button>
    </div>
  `;
}

function bindSelectedSpectrumDragHandlers() {
  const list = speEl["spe-selected-list"];
  if (!list || list.dataset.dragBound === "1") return;
  list.dataset.dragBound = "1";
  list.addEventListener("dragstart", onSelectedSpectrumDragStart);
  list.addEventListener("dragover", onSelectedSpectrumDragOver);
  list.addEventListener("drop", onSelectedSpectrumDrop);
  list.addEventListener("dragend", clearSelectedSpectrumDragState);
  list.addEventListener("dragleave", (event) => {
    if (event.relatedTarget && list.contains(event.relatedTarget)) return;
    clearSelectedSpectrumDropMarkers();
  });
}

function onSelectedSpectrumDragStart(event) {
  const handle = event.target.closest?.(".spectra-token-drag-handle");
  if (!handle) return;
  const token = handle.closest(".spectra-token");
  const specid = Number(token?.dataset?.specid);
  if (!Number.isFinite(specid)) return;
  speState.dragSpecid = specid;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(specid));
  }
  requestAnimationFrame(() => {
    token.classList.add("is-dragging");
    speEl["spe-selected-list"]?.classList.add("is-reordering");
  });
}

function onSelectedSpectrumDragOver(event) {
  if (!Number.isFinite(speState.dragSpecid)) return;
  event.preventDefault();
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  markSelectedSpectrumDropTarget(selectedSpectrumDropPlacement(event.clientY));
}

function onSelectedSpectrumDrop(event) {
  if (!Number.isFinite(speState.dragSpecid)) return;
  event.preventDefault();
  const placement = selectedSpectrumDropPlacement(event.clientY);
  const moved = moveSelectedSpectrum(speState.dragSpecid, placement.targetSpecid, placement.position);
  clearSelectedSpectrumDragState();
  if (!moved) return;
  updateSpectraUrl();
  if (speState.payload?.spectra?.length) renderSpectra();
  else renderSelectedSpectra();
}

function selectedSpectrumDropPlacement(clientY) {
  const list = speEl["spe-selected-list"];
  const tokens = Array.from(list?.querySelectorAll(".spectra-token") || [])
    .filter((token) => Number(token.dataset.specid) !== Number(speState.dragSpecid));
  if (!tokens.length) return { targetSpecid: null, position: "after", token: null };
  for (const token of tokens) {
    const rect = token.getBoundingClientRect();
    if (clientY < rect.top + rect.height / 2) {
      return { targetSpecid: Number(token.dataset.specid), position: "before", token };
    }
  }
  const token = tokens[tokens.length - 1];
  return { targetSpecid: Number(token.dataset.specid), position: "after", token };
}

function markSelectedSpectrumDropTarget(placement) {
  clearSelectedSpectrumDropMarkers();
  if (!placement?.token) return;
  placement.token.classList.add(placement.position === "before" ? "is-drop-before" : "is-drop-after");
}

function clearSelectedSpectrumDropMarkers() {
  speEl["spe-selected-list"]?.querySelectorAll(".spectra-token").forEach((token) => {
    token.classList.remove("is-drop-before", "is-drop-after");
  });
}

function clearSelectedSpectrumDragState() {
  speState.dragSpecid = null;
  clearSelectedSpectrumDropMarkers();
  speEl["spe-selected-list"]?.classList.remove("is-reordering");
  speEl["spe-selected-list"]?.querySelectorAll(".spectra-token").forEach((token) => {
    token.classList.remove("is-dragging");
  });
}

function moveSelectedSpectrum(specid, targetSpecid, position) {
  const fromIndex = speState.selected.findIndex((item) => Number(item.specid) === Number(specid));
  if (fromIndex < 0) return false;
  const moving = speState.selected[fromIndex];
  const next = speState.selected.filter((item) => Number(item.specid) !== Number(specid));
  let insertIndex = next.length;
  if (targetSpecid !== null && targetSpecid !== undefined) {
    const targetIndex = next.findIndex((item) => Number(item.specid) === Number(targetSpecid));
    if (targetIndex >= 0) insertIndex = position === "after" ? targetIndex + 1 : targetIndex;
  }
  next.splice(insertIndex, 0, moving);
  const changed = next.some((item, index) => Number(item.specid) !== Number(speState.selected[index]?.specid));
  if (!changed) return false;
  speState.selected = next;
  return true;
}

function spectraMetadataFromOption(option) {
  const specid = Number(option?.moca_specid ?? option?.value);
  return {
    ...(option || {}),
    moca_specid: Number.isFinite(specid) ? specid : option?.moca_specid,
    value: Number.isFinite(specid) ? specid : option?.value,
    label: option?.label || (Number.isFinite(specid) ? `specid${specid}` : ""),
  };
}

function selectedSpectrumMetadata(item) {
  const specid = Number(item?.specid);
  const loaded = (speState.payload?.spectra || []).find((spectrum) => Number(spectrum.moca_specid) === specid);
  return {
    ...(item?.metadata || {}),
    ...(loaded?.metadata || {}),
    moca_specid: specid,
    value: specid,
    label: loaded?.metadata?.label || item?.metadata?.label || item?.label || `specid${specid}`,
  };
}

async function loadSpectra(options = {}) {
  const preservedViewport = options?.preserveViewport ? spectraCurrentViewport() : null;
  updateSpectraUrl();
  if (!speState.selected.length) {
    renderEmptySpectra("Select one or more spectra");
    return;
  }
  const token = ++speState.loadToken;
  setSpectraLoading(true);
  setSpectraStatus("Loading spectra", "loading");
  const params = apiParams();
  params.set("specids", speState.selected.map((item) => item.specid).join(","));
  params.set("hide_ignored", speEl["spe-hide-ignored"].checked ? "1" : "0");
  const urlParams = new URLSearchParams(window.location.search);
  const requestedBins = urlParams.get("bins") ?? urlParams.get("bins_per_micron") ?? urlParams.get("spe_bins");
  if (requestedBins !== null && requestedBins !== "") {
    params.set("bins", requestedBins);
  } else {
    params.set("bins", String(speDefaultBinsPerMicron));
  }
  const payload = await fetchJsonUrl(speAppUrl(`api/spectra/load?${params.toString()}`));
  if (token !== speState.loadToken) return;
  if (!payload.ok) {
    setSpectraStatus(payload.error || "Could not load spectra", "error");
    renderEmptySpectra(payload.error || "Could not load spectra");
    return;
  }
  speState.payload = payload;
  speState.selectedPoints = [];
  speState.ignoreSpecids = new Set();
  speState.ignoreSelectionInitialized = false;
  const metadata = new Map((payload.spectra || []).map((item) => {
    const specid = Number(item.moca_specid);
    return [specid, spectraMetadataFromOption({ ...(item.metadata || {}), value: specid })];
  }));
  speState.selected = speState.selected.map((item) => {
    const nextMetadata = metadata.get(item.specid);
    return nextMetadata
      ? { ...item, label: nextMetadata.label || item.label, metadata: { ...(item.metadata || {}), ...nextMetadata } }
      : item;
  });
  renderSelectedSpectra();
  renderDownloadLinks();
  updateLowresToggleState();
  renderSpectra({ viewport: preservedViewport });
  updateSpectraUrl();
}

function renderSpectra(options = {}) {
  if (!speState.payload || !(speState.payload.spectra || []).length) {
    renderEmptySpectra("No spectra loaded");
    return;
  }
  const preservedViewport = options.viewport || (
    options.preserveViewport ? spectraCurrentViewport() : null
  );
  if (preservedViewport && options.preserveYAxis === false) preservedViewport.y = null;
  setSpectraLoading(true);
  const nonCanonicalFluxUnitCount = updateSpectraFluxUnitControls();
  const processed = processSpectraPayload();
  speState.processed = processed;
  updateLowresToggleState(processed);
  syncSpectraIgnoreTraceSelection();
  renderSpectraIgnoreTraceChoices();
  renderSelectedSpectra();
  const traces = [];
  const showSnr = speEl["spe-snr"].checked;
  const showErrorShade = speEl["spe-error-shade"].checked && !showSnr;
  const ylog = speEl["spe-ylog"].checked;
  const managementMode = spectraManagementToolsVisible();
  const displayResolutionDecreased = spectraDisplayResolutionDecreased();
  processed.forEach((spectrum, index) => {
    const color = spectrum.color || speColors[index % speColors.length];
    const hasRegularPoints = spectrum.points.length > 0;
    const hasIgnoredPoints = (spectrum.ignoredPoints || []).length > 0;
    if (!hasRegularPoints && !hasIgnoredPoints) return;
    if (showErrorShade && hasRegularPoints) traces.push(...errorShadeTraces(spectrum, color, ylog));
    if (spectrum.lowRes && !speEl["spe-disable-lowres"].checked) {
      if (hasRegularPoints) {
        const lineData = lineWithGaps(spectrum.points);
        traces.push({
          type: "scattergl",
          mode: "lines",
          x: lineData.x,
          y: lineData.y,
          line: { color, width: 1.4 },
          opacity: 0.65,
          name: spectrum.name,
          legendgroup: String(spectrum.specid),
          showlegend: false,
          hoverinfo: "skip",
        });
        traces.push({
          type: "scattergl",
          mode: "markers",
          x: spectrum.points.map((point) => point.lam),
          y: spectrum.points.map((point) => point.y),
          customdata: spectrum.points.map((point) => point.custom),
          marker: {
            symbol: "circle",
            color: "#ffffff",
            size: 8,
            line: { color, width: 2 },
          },
          error_y: {
            type: "data",
            array: spectrum.points.map((point) => point.yerr || 0),
            visible: spectrum.points.some((point) => finite(point.yerr)),
            color: colorWithAlpha(color, 0.45),
            thickness: 1,
            width: 0,
          },
          name: spectrum.name,
          legendgroup: String(spectrum.specid),
          hovertemplate: hoverTemplatesForCustomData(spectrum.points.map((point) => point.custom)),
          hoverinfo: speEl["spe-hover"].checked ? undefined : "skip",
        });
      }
    } else {
      if (hasRegularPoints) {
        const lineData = lineWithGaps(spectrum.points);
        const trace = {
          type: "scattergl",
          mode: "lines",
          x: lineData.x,
          y: lineData.y,
          customdata: lineData.custom,
          line: { color, width: 1.5 },
          name: spectrum.name,
          legendgroup: String(spectrum.specid),
          hovertemplate: hoverTemplatesForCustomData(lineData.custom),
          hoverinfo: speEl["spe-hover"].checked ? undefined : "skip",
        };
        traces.push(trace);
        if (managementMode && !displayResolutionDecreased) traces.push(selectableSpectrumPointsTrace(spectrum, color));
      }
    }
    if (hasIgnoredPoints) traces.push(ignoredPointsTrace(spectrum, color));
  });

  const layout = spectraLayout(processed, preservedViewport);
  const renderToken = ++speState.renderToken;
  const renderPromise = Plotly.react(speEl["spe-plot"], traces, layout, plotConfig("mocadb_spectral_explorer"));
  restoreSpectraViewportAfterRender(renderPromise, preservedViewport, renderToken);
  bindSpectraPlotEvents();
  setSpectraExportDisabled(processed.every((spectrum) => !displayedSpectrumPoints(spectrum).length));
  const rowCount = processed.reduce((sum, spectrum) => sum + spectrum.rawRows.length, 0);
  const cacheText = speState.payload.cache?.hit ? " from cache" : "";
  const spectraCountText = pluralize(processed.length, "spectrum", "spectra");
  const rowCountText = pluralize(rowCount, "spectral row", "spectral rows");
  setSpectraStatus(`${spectraCountText} loaded${cacheText}`, "");
  speEl["spe-summary"].textContent = `${spectraCountText} loaded, ${rowCountText}`;
  const displayBinsText = displayResolutionDecreased
    ? ` Display resolving power is decreased to ${spectraDisplayBinsPerMicron().toLocaleString()} bins/μm${speEl["spe-xlog"].checked || speEl["spe-ylog"].checked ? " with log-space averaging for log axes" : ""}.`
    : "";
  const fluxUnitNotice = nonCanonicalFluxUnitCount
    ? ` ${pluralize(nonCanonicalFluxUnitCount, "spectrum uses", "spectra use")} native or relative flux units; Jy conversion is disabled and unnormalized values retain the units recorded for each spectrum.`
    : "";
  speEl["spe-hint"].textContent = ((showSnr
    ? "Displayed values are flux divided by flux uncertainty per pixel."
    : (speEl["spe-normalize"].checked ? "Displayed fluxes are normalized by the selected wavelength range." : "Displayed fluxes use the stored spectral flux calibration.")) + fluxUnitNotice + displayBinsText).trim();
  renderSpectraTable();
  updateSpectraIgnoreControls();
  setSpectraLoading(false);
}

function bindSpectraPlotEvents() {
  if (speEl["spe-plot"].dataset.bound === "1" || typeof speEl["spe-plot"].on !== "function") return;
  speEl["spe-plot"].dataset.bound = "1";
  speEl["spe-plot"].on("plotly_click", (event) => {
    const points = event?.points || [];
    speState.selectedPoints = uniqueSpectralPlotPoints(points.map(pointFromPlotly).filter(Boolean));
    renderSpectraTable();
    updateSpectraIgnoreControls();
  });
  speEl["spe-plot"].on("plotly_selected", (event) => {
    if (window.MocaPlotlySelection?.isDegenerate(speEl["spe-plot"], event)) return;
    const points = event?.points || [];
    speState.selectedPoints = uniqueSpectralPlotPoints(points.map(pointFromPlotly).filter(Boolean));
    renderSpectraTable();
    updateSpectraIgnoreControls();
  });
  speEl["spe-plot"].on("plotly_relayout", scheduleSpectraLogTickRefresh);
}

function scheduleSpectraLogTickRefresh(event = {}) {
  if (speState.refreshingLogTicks) return;
  if (!speEl["spe-xlog"]?.checked && !speEl["spe-ylog"]?.checked) return;
  const keys = Object.keys(event || {});
  const rangeChanged = !keys.length || keys.some((key) => (
    /^xaxis\.(range|autorange|type)/.test(key)
    || /^xaxis\.range\[\d+\]/.test(key)
    || /^yaxis\.(range|autorange|type)/.test(key)
    || /^yaxis\.range\[\d+\]/.test(key)
  ));
  if (!rangeChanged) return;
  window.clearTimeout(speState.logTickRefreshTimer);
  speState.logTickRefreshTimer = window.setTimeout(refreshSpectraLogAxisTicks, 40);
}

function refreshSpectraLogAxisTicks() {
  const plot = speEl["spe-plot"];
  if (!plot || typeof Plotly === "undefined" || typeof Plotly.relayout !== "function" || speState.refreshingLogTicks) return;
  const update = {};
  if (speEl["spe-xlog"]?.checked) {
    const ticks = visibleSpectraLogAxisTicks(plot, "xaxis", { minTicks: 3, fallbackTickCount: 5 });
    if (ticks.values.length) {
      update["xaxis.tickmode"] = "array";
      update["xaxis.tickvals"] = ticks.values;
      update["xaxis.ticktext"] = ticks.text;
    }
  }
  if (speEl["spe-ylog"]?.checked) {
    const ticks = visibleSpectraLogAxisTicks(plot, "yaxis", { majorLabelsOnly: true, minTicks: 3, fallbackTickCount: 5 });
    if (ticks.values.length) {
      update["yaxis.tickmode"] = "array";
      update["yaxis.tickvals"] = ticks.values;
      update["yaxis.ticktext"] = ticks.text;
    }
  }
  if (!Object.keys(update).length) return;
  speState.refreshingLogTicks = true;
  Promise.resolve(Plotly.relayout(plot, update))
    .catch((error) => console.warn("Unable to refresh spectral log-axis ticks", error))
    .finally(() => {
      speState.refreshingLogTicks = false;
    });
}

function visibleSpectraLogAxisTicks(plot, axisName, options = {}) {
  const range = visibleSpectraLogAxisLinearRange(plot, axisName);
  return range ? plainLogTicks(range[0], range[1], options) : { values: [], text: [] };
}

function visibleSpectraLogAxisLinearRange(plot, axisName) {
  const layoutAxis = plot?.layout?.[axisName] || {};
  const fullAxis = plot?._fullLayout?.[axisName] || {};
  const axisType = fullAxis.type || layoutAxis.type;
  const range = Array.isArray(fullAxis.range) ? fullAxis.range : layoutAxis.range;
  if (axisType !== "log" || !Array.isArray(range) || range.length < 2) return null;
  const lowerLog = Number(range[0]);
  const upperLog = Number(range[1]);
  if (!finite(lowerLog) || !finite(upperLog) || lowerLog === upperLog) return null;
  const xmin = 10 ** Math.min(lowerLog, upperLog);
  const xmax = 10 ** Math.max(lowerLog, upperLog);
  return finite(xmin) && finite(xmax) && xmin > 0 && xmax > xmin ? [xmin, xmax] : null;
}

function processSpectraPayload() {
  const range = parseNormRange(speEl["spe-normrange"].value);
  const useFnu = speEl["spe-fnu"].checked;
  const normalize = speEl["spe-normalize"].checked;
  const showSnr = speEl["spe-snr"].checked;
  const hideIgnored = speEl["spe-hide-ignored"].checked;
  const ylog = speEl["spe-ylog"].checked;
  const selectedOrder = new Map((speState.selected || []).map((item, index) => [Number(item.specid), index]));
  return (speState.payload.spectra || []).slice().sort((a, b) => {
    const aSpecid = Number(a.moca_specid);
    const bSpecid = Number(b.moca_specid);
    const aOrder = selectedOrder.has(aSpecid) ? selectedOrder.get(aSpecid) : Number.MAX_SAFE_INTEGER;
    const bOrder = selectedOrder.has(bSpecid) ? selectedOrder.get(bSpecid) : Number.MAX_SAFE_INTEGER;
    return aOrder - bOrder;
  }).map((spectrum, index) => {
    const metadata = spectrum.metadata || {};
    const fluxUnitInfo = spectrumFluxUnitInfo(metadata);
    const color = spectraColorForSpecid(Number(spectrum.moca_specid));
    const rawRows = (spectrum.rows || []).map((row, rowIndex) => {
      const lam = wavelengthMicron(row.lam);
      const ignored = ignoredFlag(row.ignored);
      const storedFlux = Number(row.sp);
      const storedFluxUnc = finite(row.esp) ? Number(row.esp) : null;
      const rawFlambdaUm = fluxUnitInfo.canonical ? storedFlux * 10000.0 : storedFlux;
      const rawErrFlambdaUm = finite(storedFluxUnc) ? (fluxUnitInfo.canonical ? storedFluxUnc * 10000.0 : storedFluxUnc) : null;
      const converted = useFnu && fluxUnitInfo.canonical && finite(lam)
        ? rawFlambdaUm * lam * lam * 1e20 / speSpeedOfLight
        : rawFlambdaUm;
      const convertedErr = useFnu && fluxUnitInfo.canonical && finite(lam) && finite(rawErrFlambdaUm)
        ? rawErrFlambdaUm * lam * lam * 1e20 / speSpeedOfLight
        : rawErrFlambdaUm;
      return {
        rowIndex,
        specid: Number(spectrum.moca_specid),
        dataSpectraId: parseInteger(row.data_spectra_id ?? row.id),
        lam,
        rawFlambdaUm,
        rawErrFlambdaUm,
        ignored,
        yOriginal: converted,
        yerrOriginal: convertedErr,
      };
    }).filter((row) => finite(row.lam) && finite(row.yOriginal) && !(hideIgnored && row.ignored));
    const normCandidates = rawRows.filter((row) => !row.ignored && row.lam >= range[0] && row.lam <= range[1] && finite(row.yOriginal) && row.yOriginal !== 0);
    const scale = normalize ? robustMedian(normCandidates.map((row) => row.yOriginal)) : 1;
    const safeScale = finite(scale) && scale !== 0 ? scale : 1;
    const displayPoints = rawRows.map((row) => {
      const y = showSnr
        ? (finite(row.yerrOriginal) && row.yerrOriginal !== 0 ? row.yOriginal / Math.abs(row.yerrOriginal) : NaN)
        : row.yOriginal / safeScale;
      const yerr = showSnr ? null : (finite(row.yerrOriginal) ? Math.abs(row.yerrOriginal / safeScale) : null);
      return {
        ...row,
        y,
        yerr,
        custom: {
          specid: Number(spectrum.moca_specid),
          oid: metadata.moca_oid,
          label: spectrumName(metadata, Number(spectrum.moca_specid)),
          instrument: instrumentLabel(metadata) || "N/A",
          obsDate: observationDateLabel(metadata) || "N/A",
          mocaPid: metadata.moca_pid || "",
          spectrumRef: spectrumReferenceLabel(metadata),
          spectrumRefUrl: spectrumReferenceUrl(metadata),
          spectrumBibcode: spectrumBibcodeLabel(metadata),
          lam: row.lam,
          y,
          yerr,
          rawFlambdaUm: row.rawFlambdaUm,
          rawErrFlambdaUm: row.rawErrFlambdaUm,
          rawFluxUnit: fluxUnitInfo.displayUnit,
          ignored: row.ignored,
          normalized: normalize,
          unit: yAxisUnit(),
          rowIndex: row.rowIndex,
          dataSpectraId: row.dataSpectraId,
          color,
        },
      };
    }).filter((row) => finite(row.lam) && finite(row.y) && (!ylog || row.y > 0));
    const regularDisplayPoints = displayPoints.filter((row) => !row.ignored);
    const ignoredDisplayPoints = hideIgnored ? [] : displayPoints.filter((row) => row.ignored);
    const points = displayBinSpectralPoints(regularDisplayPoints);
    const ignoredPoints = hideIgnored ? [] : displayBinSpectralPoints(ignoredDisplayPoints);
    const storedAverageResolvingPower = finite(spectrum.meta?.average_resolving_power)
      ? Number(spectrum.meta.average_resolving_power)
      : null;
    const displayAverageResolvingPower = spectraDisplayResolutionDecreased()
      ? estimateDisplayResolvingPower(points.length ? points : ignoredPoints)
      : null;
    const effectiveAverageResolvingPower = finite(displayAverageResolvingPower)
      ? displayAverageResolvingPower
      : storedAverageResolvingPower;
    const lowresResolvingPowerPerPixel = spectrumLowresResolvingPowerPerPixel(spectrum);
    return {
      specid: Number(spectrum.moca_specid),
      metadata,
      fluxUnitInfo,
      name: spectrumLegendName(metadata, Number(spectrum.moca_specid), displayPoints),
      rawRows,
      points,
      ignoredPoints,
      displayResolutionDecreased: spectraDisplayResolutionDecreased(),
      lowRes: finite(lowresResolvingPowerPerPixel) && lowresResolvingPowerPerPixel < speLowResolutionResolvingPowerPerPixelThreshold,
      averageResolvingPower: effectiveAverageResolvingPower,
      storedAverageResolvingPower,
      lowresResolvingPowerPerPixel,
      color,
    };
  });
}

function displayBinSpectralPoints(points) {
  if (!spectraDisplayResolutionDecreased() || !points.length) return points;
  const binsPerMicron = spectraDisplayBinsPerMicron();
  if (!Number.isFinite(binsPerMicron) || binsPerMicron <= 0) return points;
  const xlog = speEl["spe-xlog"].checked;
  const ylog = speEl["spe-ylog"].checked;
  const clean = points
    .filter((point) => finite(point.lam) && finite(point.y) && (!xlog || point.lam > 0) && (!ylog || point.y > 0))
    .sort((a, b) => a.lam - b.lam);
  return contiguousPointGroups(clean).flatMap((group) => binSpectralPointGroup(group, binsPerMicron, { xlog, ylog }));
}

function binSpectralPointGroup(points, binsPerMicron, options = {}) {
  if (points.length < 2) return points;
  const wavelengths = points.map((point) => point.lam).filter(finite);
  const lamMin = Math.min(...wavelengths);
  const lamMax = Math.max(...wavelengths);
  if (!finite(lamMin) || !finite(lamMax) || lamMax <= lamMin) return points;

  const binCount = Math.max(1, Math.round((lamMax - lamMin) * binsPerMicron));
  if (binCount >= points.length) return points;

  const xMin = options.xlog ? Math.log10(lamMin) : lamMin;
  const xMax = options.xlog ? Math.log10(lamMax) : lamMax;
  if (!finite(xMin) || !finite(xMax) || xMax <= xMin) return points;
  const binWidth = (xMax - xMin) / binCount;
  if (!finite(binWidth) || binWidth <= 0) return points;

  const bins = new Map();
  points.forEach((point) => {
    const xValue = options.xlog ? Math.log10(point.lam) : point.lam;
    if (!finite(xValue)) return;
    let binIndex = Math.floor((xValue - xMin) / binWidth);
    if (binIndex < 0) return;
    if (binIndex >= binCount) binIndex = binCount - 1;
    if (!bins.has(binIndex)) bins.set(binIndex, []);
    bins.get(binIndex).push(point);
  });

  return [...bins.keys()]
    .sort((a, b) => a - b)
    .map((binIndex) => aggregateSpectralBin(bins.get(binIndex), options))
    .filter(Boolean);
}

function aggregateSpectralBin(points, options = {}) {
  if (!points?.length) return null;
  const first = points[0];
  const xValues = points.map((point) => options.xlog ? Math.log10(point.lam) : point.lam).filter(finite);
  const yValues = points.map((point) => options.ylog ? Math.log10(point.y) : point.y).filter(finite);
  if (!xValues.length || !yValues.length) return null;
  const xMean = averageFinite(xValues);
  const yMean = averageFinite(yValues);
  if (!finite(xMean) || !finite(yMean)) return null;
  const lam = options.xlog ? 10 ** xMean : xMean;
  const y = options.ylog ? 10 ** yMean : yMean;
  const yerr = aggregateSpectralBinError(points, y, options.ylog);
  const rawFlambdaUm = averageFinite(points.map((point) => point.rawFlambdaUm));
  const rawErrFlambdaUm = aggregateLinearError(points.map((point) => point.rawErrFlambdaUm));
  const custom = {
    ...(first.custom || {}),
    lam,
    y,
    yerr,
    rawFlambdaUm,
    rawErrFlambdaUm,
    rowIndex: null,
    dataSpectraId: null,
    binned: true,
    nData: points.length,
    ignored: first.ignored,
  };
  return {
    ...first,
    rowIndex: null,
    dataSpectraId: null,
    lam,
    y,
    yerr,
    rawFlambdaUm,
    rawErrFlambdaUm,
    binned: true,
    nData: points.length,
    custom,
  };
}

function aggregateSpectralBinError(points, y, ylog) {
  if (!ylog) return aggregateLinearError(points.map((point) => point.yerr));
  if (!finite(y) || y <= 0) return null;
  const logSigmas = [];
  points.forEach((point) => {
    const center = Number(point.y);
    const err = Math.abs(Number(point.yerr));
    if (!finite(center) || !finite(err) || center <= 0) return;
    const upper = center + err;
    if (upper <= 0) return;
    const upperSigma = Math.log10(upper) - Math.log10(center);
    const lower = center - err;
    const lowerSigma = lower > 0 ? Math.log10(center) - Math.log10(lower) : upperSigma;
    const sigma = 0.5 * (Math.abs(upperSigma) + Math.abs(lowerSigma));
    if (finite(sigma)) logSigmas.push(sigma);
  });
  if (!logSigmas.length) return null;
  const logSigma = Math.sqrt(logSigmas.reduce((sum, value) => sum + value * value, 0)) / logSigmas.length;
  const upper = 10 ** (Math.log10(y) + logSigma);
  return finite(upper) ? Math.max(0, upper - y) : null;
}

function aggregateLinearError(values) {
  const clean = values.map(Number).filter((value) => finite(value) && value >= 0);
  if (!clean.length) return null;
  return Math.sqrt(clean.reduce((sum, value) => sum + value * value, 0)) / clean.length;
}

function averageFinite(values) {
  const clean = values.map(Number).filter(finite);
  if (!clean.length) return NaN;
  return clean.reduce((sum, value) => sum + value, 0) / clean.length;
}

function estimateDisplayResolvingPower(points) {
  const estimates = [];
  for (const group of contiguousPointGroups((points || []).slice().sort((a, b) => a.lam - b.lam))) {
    if (group.length < 2) continue;
    group.forEach((point, index) => {
      const left = index > 0 ? point.lam - group[index - 1].lam : NaN;
      const right = index < group.length - 1 ? group[index + 1].lam - point.lam : NaN;
      const widths = [left, right].filter((value) => finite(value) && value > 0);
      if (!widths.length || !finite(point.lam) || point.lam <= 0) return;
      const deltaLambda = averageFinite(widths);
      if (finite(deltaLambda) && deltaLambda > 0) estimates.push(point.lam / deltaLambda);
    });
  }
  return robustMedian(estimates);
}

function lineWithGaps(points) {
  if (points.length < 2) {
    return {
      x: points.map((point) => point.lam),
      y: points.map((point) => point.y),
      custom: points.map((point) => point.custom),
    };
  }
  const diffs = [];
  for (let index = 1; index < points.length; index += 1) {
    const diff = points[index].lam - points[index - 1].lam;
    if (diff > 0 && finite(diff)) diffs.push(diff);
  }
  const medianDiff = robustMedian(diffs);
  const gapLimit = finite(medianDiff) && medianDiff > 0 ? 10 * medianDiff : Infinity;
  const x = [];
  const y = [];
  const custom = [];
  points.forEach((point, index) => {
    if (index > 0 && point.lam - points[index - 1].lam > gapLimit) {
      x.push(null);
      y.push(null);
      custom.push(null);
    }
    x.push(point.lam);
    y.push(point.y);
    custom.push(point.custom);
  });
  return { x, y, custom };
}

function displayedSpectrumPoints(spectrum) {
  return [...(spectrum.points || []), ...(spectrum.ignoredPoints || [])];
}

function selectableSpectrumPointsTrace(spectrum, color) {
  const points = spectrum.points || [];
  return {
    type: "scattergl",
    mode: "markers",
    x: points.map((point) => point.lam),
    y: points.map((point) => point.y),
    customdata: points.map((point) => point.custom),
    marker: {
      symbol: "circle",
      color,
      size: 8,
      opacity: 0,
      line: { width: 0 },
    },
    selected: { marker: { opacity: 0, size: 8 } },
    unselected: { marker: { opacity: 0, size: 8 } },
    name: `${spectrum.name} selectable points`,
    legendgroup: String(spectrum.specid),
    showlegend: false,
    hoverinfo: "skip",
  };
}

function ignoredPointsTrace(spectrum, color) {
  const points = spectrum.ignoredPoints || [];
  return {
    type: "scattergl",
    mode: "markers",
    x: points.map((point) => point.lam),
    y: points.map((point) => point.y),
    customdata: points.map((point) => point.custom),
    marker: {
      symbol: "x",
      color,
      size: 10,
      line: { color, width: 2 },
    },
    name: `${spectrum.name} ignored`,
    legendgroup: String(spectrum.specid),
    showlegend: false,
    hovertemplate: hoverTemplatesForCustomData(points.map((point) => point.custom)),
    hoverinfo: speEl["spe-hover"].checked ? undefined : "skip",
  };
}

function errorShadeTraces(spectrum, color, ylog) {
  return errorShadeSegments(spectrum.points, ylog).map((segment, index) => ({
    type: "scatter",
    mode: "lines",
    x: segment.x,
    y: segment.y,
    fill: "toself",
    fillcolor: colorWithAlpha(color, 0.16),
    line: { color: "rgba(0,0,0,0)", width: 0 },
    name: `${spectrum.name} 1-sigma`,
    legendgroup: String(spectrum.specid),
    showlegend: false,
    hoverinfo: "skip",
    connectgaps: false,
  }));
}

function errorShadeSegments(points, ylog) {
  const groups = contiguousPointGroups(points.filter((point) => finite(point.yerr) && point.yerr >= 0));
  return groups.map((group) => {
    const smoothed = smoothedErrorBand(group, ylog);
    if (smoothed.length < 2) return null;
    return {
      x: smoothed.map((point) => point.lam).concat(smoothed.map((point) => point.lam).reverse()),
      y: smoothed.map((point) => point.upper).concat(smoothed.map((point) => point.lower).reverse()),
    };
  }).filter(Boolean);
}

function contiguousPointGroups(points) {
  if (points.length < 2) return points.length ? [points] : [];
  const diffs = [];
  for (let index = 1; index < points.length; index += 1) {
    const diff = points[index].lam - points[index - 1].lam;
    if (diff > 0 && finite(diff)) diffs.push(diff);
  }
  const medianDiff = robustMedian(diffs);
  const gapLimit = finite(medianDiff) && medianDiff > 0 ? 10 * medianDiff : Infinity;
  const groups = [];
  let current = [];
  points.forEach((point, index) => {
    if (index > 0 && point.lam - points[index - 1].lam > gapLimit) {
      if (current.length) groups.push(current);
      current = [];
    }
    current.push(point);
  });
  if (current.length) groups.push(current);
  return groups;
}

function smoothedErrorBand(points, ylog) {
  const windowSize = smoothingWindowSize(points.length);
  const yValues = points.map((point) => point.y);
  const errValues = points.map((point) => Math.abs(point.yerr));
  const errSmooth = movingAverage(errValues, windowSize);
  return points.map((point, index) => {
    const center = point.y;
    const sigma = finite(errSmooth[index]) ? Math.abs(errSmooth[index]) : Math.abs(point.yerr || 0);
    const upper = center + sigma;
    let lower = center - sigma;
    if (ylog && lower <= 0) lower = positiveLowerEnvelope(center, sigma, yValues);
    return { lam: point.lam, lower, upper };
  }).filter((point) => finite(point.lam) && finite(point.lower) && finite(point.upper) && (!ylog || (point.lower > 0 && point.upper > 0)));
}

function smoothingWindowSize(length) {
  if (length < 7) return 1;
  const target = Math.floor(length / 90);
  const odd = target % 2 ? target : target + 1;
  return Math.max(5, Math.min(61, odd));
}

function movingAverage(values, windowSize) {
  if (windowSize <= 1 || values.length <= 2) return values.slice();
  const half = Math.floor(windowSize / 2);
  const output = [];
  for (let index = 0; index < values.length; index += 1) {
    let sum = 0;
    let count = 0;
    const left = Math.max(0, index - half);
    const right = Math.min(values.length - 1, index + half);
    for (let cursor = left; cursor <= right; cursor += 1) {
      const value = values[cursor];
      if (!finite(value)) continue;
      sum += value;
      count += 1;
    }
    output.push(count ? sum / count : values[index]);
  }
  return output;
}

function positiveLowerEnvelope(center, sigma, yValues) {
  const positives = yValues.filter((value) => finite(value) && value > 0);
  const floor = positives.length ? Math.min(...positives) * 0.1 : 1e-12;
  if (center > 0) return Math.max(floor, center / (1 + Math.max(1, sigma / center)));
  return floor;
}

function colorWithAlpha(color, alpha) {
  const text = String(color || "").trim();
  const clampedAlpha = Math.max(0, Math.min(1, Number(alpha)));
  const hex = text.match(/^#?([0-9a-f]{6})$/i);
  if (hex) {
    const value = hex[1];
    const red = parseInt(value.slice(0, 2), 16);
    const green = parseInt(value.slice(2, 4), 16);
    const blue = parseInt(value.slice(4, 6), 16);
    return `rgba(${red}, ${green}, ${blue}, ${clampedAlpha})`;
  }
  const rgba = text.match(/^rgba?\(([^)]+)\)$/i);
  if (rgba) {
    const parts = rgba[1].split(",").slice(0, 3).map((item) => item.trim());
    if (parts.length === 3) return `rgba(${parts.join(", ")}, ${clampedAlpha})`;
  }
  return `rgba(55, 126, 184, ${clampedAlpha})`;
}

function spectraLayout(processed, viewport = null) {
  const xlog = speEl["spe-xlog"].checked;
  const ylog = speEl["spe-ylog"].checked;
  const shapes = [];
  const annotations = [];
  const allX = processed.flatMap((spectrum) => displayedSpectrumPoints(spectrum).map((point) => point.lam));
  const autoXRange = numericAxisRange(allX, { log: xlog, fallback: xlog ? [0.7, 30] : [0.7, 2.6] });
  const xRange = spectraDisplayXRange(autoXRange) || autoXRange;
  const allY = spectraYAxisValues(processed, ylog, { xRange });
  const yRange = numericAxisRange(allY, { log: ylog, fallback: null, padFraction: 0.08 });
  const xmin = xRange ? xRange[0] : NaN;
  const xmax = xRange ? xRange[1] : NaN;
  if (speEl["spe-showfeatures"].checked && finite(xmin) && finite(xmax)) {
    const visibleBands = typeof globalThis.mocaBrownDwarfSpectralFeatureBandsInRange === "function"
      ? globalThis.mocaBrownDwarfSpectralFeatureBandsInRange([xmin, xmax])
      : speFeatureBands.filter((band) => band.range[1] >= xmin && band.range[0] <= xmax);
    for (const band of visibleBands) {
      const visibleRange = typeof globalThis.mocaClippedSpectralFeatureBandRange === "function"
        ? globalThis.mocaClippedSpectralFeatureBandRange(band, [xmin, xmax])
        : [Math.max(band.range[0], xmin), Math.min(band.range[1], xmax)];
      shapes.push({
        type: "rect",
        xref: "x",
        yref: "paper",
        x0: visibleRange[0],
        x1: visibleRange[1],
        y0: 0,
        y1: 1,
        line: { width: 0 },
        fillcolor: band.fill,
        layer: "below",
      });
      annotations.push({
        x: featureAnnotationX(visibleRange, xlog),
        y: 0.992 - 0.037 * (Number(band.labelTier) || 0),
        xref: "x",
        yref: "paper",
        text: band.name,
        showarrow: false,
        font: { color: band.text, size: 11 },
        textangle: -90,
        yanchor: "top",
      });
    }
  }
  const xaxis = {
    title: { text: "Wavelength (μm)", font: { size: 24 }, standoff: 22 },
    type: xlog ? "log" : "linear",
    showgrid: true,
    gridcolor: "#e2e2e2",
    zeroline: false,
    tickfont: { size: 15 },
    automargin: true,
    ...spectraBoxAxisStyle(),
  };
  if (xRange) {
    xaxis.range = xlog ? xRange.map((value) => Math.log10(value)) : xRange;
    if (xlog) {
      const ticks = plainLogTicks(xRange[0], xRange[1]);
      xaxis.tickmode = "array";
      xaxis.tickvals = ticks.values;
      xaxis.ticktext = ticks.text;
    }
  }
  const yaxis = {
    title: { text: yAxisTitle(), font: { size: 24 } },
    type: ylog ? "log" : "linear",
    showgrid: true,
    gridcolor: "#e8e8e8",
    zeroline: false,
    tickfont: { size: 15 },
    automargin: true,
    ...spectraBoxAxisStyle(),
  };
  if (yRange) {
    yaxis.range = ylog ? yRange.map((value) => Math.log10(value)) : yRange;
    if (ylog) {
      const ticks = plainLogTicks(yRange[0], yRange[1], { majorLabelsOnly: true });
      yaxis.tickmode = "array";
      yaxis.tickvals = ticks.values;
      yaxis.ticktext = ticks.text;
    }
  }
  applySpectraViewportToAxis(xaxis, viewport?.x);
  applySpectraViewportToAxis(yaxis, viewport?.y, { majorLabelsOnly: true });
  return {
    uirevision: spectraPlotUiRevision(),
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { l: 86, r: 34, t: 18, b: 90 },
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.01,
      xanchor: "left",
      x: 0,
      bgcolor: "rgba(238,238,239,0.88)",
      font: { size: 10 },
    },
    xaxis,
    yaxis,
    dragmode: "select",
    hovermode: speEl["spe-hover"].checked ? "closest" : false,
    shapes,
    annotations,
  };
}

function spectraCurrentViewport() {
  const fullLayout = speEl["spe-plot"]?._fullLayout;
  if (!fullLayout) return null;
  return {
    x: spectraAxisDataRange(fullLayout.xaxis),
    y: spectraAxisDataRange(fullLayout.yaxis),
  };
}

function spectraAxisDataRange(axis) {
  const range = Array.isArray(axis?.range) ? axis.range.map(Number) : null;
  if (!range || range.length < 2 || !range.every(finite) || range[0] === range[1]) return null;
  if (axis?.type !== "log") return range;
  const dataRange = range.map((value) => 10 ** value);
  return dataRange.every((value) => finite(value) && value > 0) ? dataRange : null;
}

function applySpectraViewportToAxis(axis, dataRange, tickOptions = {}) {
  if (!axis || !Array.isArray(dataRange) || dataRange.length < 2) return;
  const range = spectraAxisLayoutRange(dataRange, axis.type === "log");
  if (!range) return;
  if (axis.type === "log") {
    axis.range = range;
    const dataValues = dataRange.map(Number);
    const ticks = plainLogTicks(Math.min(...dataValues), Math.max(...dataValues), tickOptions);
    axis.tickmode = "array";
    axis.tickvals = ticks.values;
    axis.ticktext = ticks.text;
  } else {
    axis.range = range;
  }
  axis.autorange = false;
}

function restoreSpectraViewportAfterRender(renderPromise, viewport, renderToken) {
  if (!viewport || typeof Plotly === "undefined" || typeof Plotly.relayout !== "function") return;
  const update = spectraViewportRelayoutUpdate(viewport);
  if (!Object.keys(update).length) return;
  Promise.resolve(renderPromise)
    .then(() => {
      if (renderToken !== speState.renderToken) return null;
      return Plotly.relayout(speEl["spe-plot"], update);
    })
    .catch((error) => console.warn("Unable to restore spectral plot viewport", error));
}

function spectraViewportRelayoutUpdate(viewport) {
  const update = {};
  for (const [axisName, log] of [
    ["xaxis", Boolean(speEl["spe-xlog"]?.checked)],
    ["yaxis", Boolean(speEl["spe-ylog"]?.checked)],
  ]) {
    const dataRange = axisName === "xaxis" ? viewport?.x : viewport?.y;
    const range = spectraAxisLayoutRange(dataRange, log);
    if (!range) continue;
    update[`${axisName}.autorange`] = false;
    update[`${axisName}.range[0]`] = range[0];
    update[`${axisName}.range[1]`] = range[1];
  }
  return update;
}

function spectraAxisLayoutRange(dataRange, log) {
  if (!Array.isArray(dataRange) || dataRange.length < 2) return null;
  const range = dataRange.map(Number);
  if (!range.every(finite) || range[0] === range[1]) return null;
  if (!log) return range;
  if (!range.every((value) => value > 0)) return null;
  return range.map((value) => Math.log10(value));
}

function spectraPlotUiRevision() {
  const specids = (speState.selected || [])
    .map((item) => Number(item?.specid))
    .filter(Number.isFinite)
    .join(",");
  const explicitXRange = ["spe-xrange-min", "spe-xrange-max"]
    .map((id) => parsePositiveNumber(speEl[id]?.value))
    .map((value) => value === null ? "auto" : String(value))
    .join(":");
  return `spectra:${specids || "none"}:xrange:${explicitXRange}`;
}

function spectraYAxisValues(processed, ylog, options = {}) {
  const xRange = Array.isArray(options.xRange) ? options.xRange : null;
  const values = processed.flatMap((spectrum) => (
    displayedSpectrumPoints(spectrum)
      .filter((point) => spectralPointInXRange(point, xRange))
      .map((point) => point.y)
  ));
  if (!speEl["spe-error-shade"].checked || speEl["spe-snr"].checked) return values;
  for (const spectrum of processed) {
    const points = spectrum.points.filter((point) => spectralPointInXRange(point, xRange));
    for (const segment of errorShadeSegments(points, ylog)) {
      values.push(...segment.y);
    }
  }
  return values;
}

function spectralPointInXRange(point, xRange) {
  if (!xRange) return true;
  const lam = Number(point?.lam);
  if (!finite(lam)) return false;
  return lam >= xRange[0] && lam <= xRange[1];
}

function featureAnnotationX(range, xlog) {
  const x0 = Number(range?.[0]);
  const x1 = Number(range?.[1]);
  if (xlog && x0 > 0 && x1 > 0) return Math.log10(Math.sqrt(x0 * x1));
  return 0.5 * (x0 + x1);
}

function hoverTemplatesForCustomData(customDataItems) {
  if (!speEl["spe-hover"].checked) return undefined;
  return (customDataItems || []).map((customData) => (
    customData ? hoverTemplate(customData) : "<extra></extra>"
  ));
}

function hoverTemplate(customData) {
  const referenceLines = spectrumReferenceLabel(customData)
    ? ["spectrum reference = %{customdata.spectrumRef}"]
    : [];
  if (speEl["spe-snr"].checked) {
    return [
      "<b>%{customdata.label}</b>",
      "specid %{customdata.specid}",
      "instrument = %{customdata.instrument}",
      "obs date = %{customdata.obsDate}",
      ...referenceLines,
      "λ = %{x:.6g} μm",
      "S/N per pixel = %{y:.6g}",
      "stored Fλ = %{customdata.rawFlambdaUm:.4e} %{customdata.rawFluxUnit}",
      "stored error = %{customdata.rawErrFlambdaUm:.4e} %{customdata.rawFluxUnit}",
      "ignored = %{customdata.ignored}",
      "<extra></extra>",
    ].join("<br>");
  }
  return [
    "<b>%{customdata.label}</b>",
    "specid %{customdata.specid}",
    "instrument = %{customdata.instrument}",
    "obs date = %{customdata.obsDate}",
    ...referenceLines,
    "λ = %{x:.6g} μm",
    `${speEl["spe-normalize"].checked ? "Normalized flux" : "Flux"} = %{y:.6g} %{customdata.unit}`,
    "error = %{customdata.yerr:.3g} %{customdata.unit}",
    "stored Fλ = %{customdata.rawFlambdaUm:.4e} %{customdata.rawFluxUnit}",
    "ignored = %{customdata.ignored}",
    "<extra></extra>",
  ].join("<br>");
}

function updateLowresToggleState(processed = null) {
  const processedSpectra = Array.isArray(processed) ? processed : null;
  const hasLowRes = processedSpectra
    ? processedSpectra.some((spectrum) => spectrum.lowRes)
    : (speState.payload?.spectra || []).some((spectrum) => spectrumUsesLowresDisplay(spectrum));
  speEl["spe-disable-lowres"].disabled = !hasLowRes;
  speEl["spe-disable-lowres-wrap"].classList.toggle("is-disabled", !hasLowRes);
  if (!hasLowRes) speEl["spe-disable-lowres"].checked = false;
}

function updateSpectraDisplayResolutionControls() {
  const input = speEl["spe-display-bins"];
  if (!input) return;
  const parsed = parseInteger(input.value);
  if (parsed === null || parsed <= 0) input.value = String(speDefaultDisplayBinsPerMicron);
  else if (parsed > 2000) input.value = "2000";
  const checked = spectraDisplayResolutionDecreased();
  input.disabled = !checked;
  if (speEl["spe-display-bins-wrap"]) speEl["spe-display-bins-wrap"].classList.toggle("disabled-field", !checked);
}

function spectraDisplayResolutionDecreased() {
  return Boolean(speEl["spe-decrease-resolution"]?.checked);
}

function spectraDisplayBinsPerMicron() {
  const parsed = parseInteger(speEl["spe-display-bins"]?.value);
  if (parsed !== null && parsed > 0) return Math.max(1, Math.min(2000, parsed));
  return speDefaultDisplayBinsPerMicron;
}

function renderDownloadLinks() {
  const spectra = speState.payload?.spectra || [];
  if (!spectra.length) {
    speEl["spe-download-links"].innerHTML = "";
    return;
  }
  speEl["spe-download-links"].innerHTML = spectra.map((spectrum) => (
    `<button type="button" data-format="csv" data-specid="${spectrum.moca_specid}">CSV specid${spectrum.moca_specid}</button>`
    + `<button type="button" data-format="fits" data-specid="${spectrum.moca_specid}">FITS specid${spectrum.moca_specid}</button>`
    + originalSpectrumDownloadLinkHtml(spectrum)
  )).join("");
  speEl["spe-download-links"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => downloadRawSpectrum(Number(button.dataset.specid), button.dataset.format || "csv"));
  });
}

function originalSpectrumDownloadUrl(spectrum) {
  const rawUrl = String(spectrum?.metadata?.original_download_url || "").trim();
  if (!rawUrl) return "";
  try {
    const url = new URL(rawUrl, window.location.href);
    if (!["http:", "https:"].includes(url.protocol)) return "";
    return url.href;
  } catch (error) {
    return "";
  }
}

function originalSpectrumDownloadLinkHtml(spectrum) {
  const url = originalSpectrumDownloadUrl(spectrum);
  if (!url) return "";
  const specid = Number(spectrum?.moca_specid);
  const label = Number.isFinite(specid) ? `Original specid${specid}` : "Original file";
  return `<a class="button-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" download>${escapeHtml(label)}</a>`;
}

function renderSpectraTable() {
  if (speState.selectedPoints.length) {
    speEl["spe-table-title"].textContent = `${speState.selectedPoints.length} selected spectral rows`;
    speEl["spe-table-subtitle"].textContent = speEl["spe-snr"].checked
      ? "Rows reflect displayed S/N per pixel."
      : "Rows reflect the displayed flux unit and normalization state.";
    const columns = ["plot", "specid", "oid", "reference", "wavelength_um", "display_flux", "display_error", "raw_flambda", "raw_flux_units", "ignored"];
    if (spectraManagementToolsVisible()) columns.splice(3, 0, "row_id");
    const rows = speState.selectedPoints.map((point) => ({
      plot: swatchHtml(point.color || spectraColorForSpecid(point.specid)),
      specid: point.specid,
      oid: point.oid,
      row_id: point.dataSpectraId ?? "",
      reference: spectrumReferenceHtml(point),
      wavelength_um: formatNumber(point.lam, 6),
      display_flux: formatScientific(point.y),
      display_error: finite(point.yerr) ? formatScientific(point.yerr) : "",
      raw_flambda: formatScientific(point.rawFlambdaUm),
      raw_flux_units: point.rawFluxUnit || "",
      ignored: point.ignored,
    }));
    speEl["spe-table"].innerHTML = tableHtml(columns, rows, { htmlColumns: new Set(["plot", "reference"]) });
    return;
  }
  const rows = (speState.processed || []).map((spectrum) => {
    const reportUrl = mocaReportUrl(spectrum.metadata?.moca_oid);
    return {
      plot: swatchHtml(spectrum.color),
      specid: spectrum.specid,
      oid: normalizedMocaOid(spectrum.metadata?.moca_oid),
      object: spectrum.metadata?.designation || "",
      spectral_type: spectrum.metadata?.spectral_type || "",
      instrument: instrumentLabel(spectrum.metadata),
      flux_units: spectrum.metadata?.flux_units || "",
      reference: spectrumReferenceHtml(spectrum.metadata),
      rows: spectrum.rawRows.length.toLocaleString(),
      resolving_power: finite(spectrum.averageResolvingPower) ? Math.round(Number(spectrum.averageResolvingPower)).toLocaleString() : "",
      report: reportUrl ? `<a class="report-link" href="${reportUrl}" target="_blank" rel="noopener">Report</a>` : "",
    };
  });
  speEl["spe-table-title"].textContent = `Selected spectra (${pluralize(rows.length, "spectrum", "spectra")})`;
  speEl["spe-table-subtitle"].textContent = "Click or box-select plotted points to inspect spectral rows.";
  speEl["spe-table"].innerHTML = tableHtml(["plot", "specid", "oid", "object", "spectral_type", "instrument", "flux_units", "reference", "rows", "resolving_power", "report"], rows, { htmlColumns: new Set(["plot", "reference", "report"]) });
}

function spectraColorForSpecid(specid) {
  const id = Number(specid);
  const payloadSpectra = speState.payload?.spectra || [];
  const payloadIndex = payloadSpectra.findIndex((spectrum) => Number(spectrum.moca_specid) === id);
  if (payloadIndex >= 0) return spectrumTraceColor(payloadSpectra[payloadIndex], payloadIndex);

  const processedIndex = (speState.processed || []).findIndex((spectrum) => Number(spectrum.specid) === id);
  if (processedIndex >= 0) return spectrumTraceColor(speState.processed[processedIndex], processedIndex);

  const selectedIndex = (speState.selected || []).findIndex((item) => Number(item.specid) === id);
  if (selectedIndex >= 0) return spectrumTraceColor(null, selectedIndex);

  return "#555555";
}

function spectrumTraceColor(spectrum, index) {
  return spectrum?.color || speColors[index % speColors.length] || "#555555";
}

function swatchHtml(color) {
  return `<span class="curve-swatch table-color-line" style="--swatch-color: ${escapeHtml(color || "#555555")};"></span>`;
}

function pointFromPlotly(point) {
  const custom = point?.customdata;
  if (!custom || typeof custom !== "object") return null;
  return custom;
}

function uniqueSpectralPlotPoints(points) {
  const seen = new Set();
  const output = [];
  for (const point of points || []) {
    if (!point) continue;
    const key = [
      point.dataSpectraId ?? "",
      point.specid ?? "",
      finite(point.lam) ? Number(point.lam).toPrecision(12) : "",
    ].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    output.push(point);
  }
  return output;
}

async function loadSpectraAuthContext() {
  speState.authContext = spectraUrlAuthContext();
  try {
    const payload = window.MocaAuthContext?.ready
      ? await window.MocaAuthContext.ready
      : await fetchJsonUrl(speAppUrl(`api/auth/context${window.location.search || ""}`));
    const role = String(payload?.role || "").trim().toLowerCase();
    speState.authContext = {
      role,
      hasCredentials: Boolean(payload?.hasCredentials ?? payload?.has_credentials),
      source: payload?.source || "",
    };
  } catch (error) {
    speState.authContext = spectraUrlAuthContext();
  }
}

function spectraUrlAuthContext() {
  const params = new URLSearchParams(window.location.search);
  const user = String(params.get("user") || params.get("username") || "").trim().toLowerCase();
  const password = params.get("pwd") ?? params.get("password");
  const hasCredentials = user === "management" && password !== null && String(password).length > 0;
  return {
    role: hasCredentials ? "management" : "",
    hasCredentials,
    source: "url",
  };
}

function updateSpectraManagementVisibility() {
  if (!speEl["spe-management-tools"]) return;
  speEl["spe-management-tools"].hidden = !hasSpectraManagementCredentials();
  if (!speEl["spe-management-tools"].hidden) {
    syncSpectraIgnoreTraceSelection();
    renderSpectraIgnoreTraceChoices();
  }
  updateSpectraIgnoreControls();
}

function spectraManagementToolsVisible() {
  return Boolean(speEl["spe-management-tools"] && !speEl["spe-management-tools"].hidden);
}

function hasSpectraManagementCredentials() {
  const context = speState.authContext || spectraUrlAuthContext();
  return context.role === "management" && Boolean(context.hasCredentials);
}

function syncSpectraIgnoreTraceSelection() {
  if (!spectraManagementToolsVisible()) return;
  const validSpecids = (speState.processed || [])
    .map((spectrum) => Number(spectrum.specid))
    .filter(Number.isFinite);
  const validSet = new Set(validSpecids);
  if (!speState.ignoreSelectionInitialized) {
    speState.ignoreSpecids = new Set(validSpecids);
    speState.ignoreSelectionInitialized = true;
    return;
  }
  speState.ignoreSpecids = new Set([...speState.ignoreSpecids].filter((specid) => validSet.has(Number(specid))));
}

function renderSpectraIgnoreTraceChoices() {
  if (!speEl["spe-ignore-spectrum-list"] || !spectraManagementToolsVisible()) return;
  const spectra = speState.processed || [];
  if (!spectra.length) {
    speEl["spe-ignore-spectrum-list"].innerHTML = `<div class="plot-hint">No spectra loaded</div>`;
    return;
  }
  speEl["spe-ignore-spectrum-list"].innerHTML = spectra.map((spectrum) => {
    const specid = Number(spectrum.specid);
    const checked = speState.ignoreSpecids.has(specid) ? " checked" : "";
    return `
      <label class="checkline spectra-ignore-trace-choice">
        <input type="checkbox" value="${specid}"${checked}>
        <span class="spectra-token-swatch" style="--swatch-color: ${escapeHtml(spectrum.color || spectraColorForSpecid(specid))}"></span>
        <span>${escapeHtml(spectrum.name || spectrumLegendName(spectrum.metadata, specid))}</span>
      </label>
    `;
  }).join("");
  speEl["spe-ignore-spectrum-list"].querySelectorAll("input[type='checkbox']").forEach((input) => {
    input.addEventListener("change", () => {
      const specid = Number(input.value);
      if (input.checked) speState.ignoreSpecids.add(specid);
      else speState.ignoreSpecids.delete(specid);
      speState.ignoreSelectionInitialized = true;
      updateSpectraIgnoreControls();
    });
  });
}

function selectedEditableSpectralRows() {
  const seen = new Set();
  const rows = [];
  const allowedSpecids = speState.ignoreSpecids || new Set();
  for (const point of speState.selectedPoints || []) {
    const dataSpectraId = parseInteger(point?.dataSpectraId);
    const specid = parseInteger(point?.specid);
    if (dataSpectraId === null || specid === null || ignoredFlag(point?.ignored)) continue;
    if (!allowedSpecids.has(specid)) continue;
    const key = `${specid}:${dataSpectraId}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({
      data_spectra_id: dataSpectraId,
      moca_specid: specid,
      lam: Number(point.lam),
    });
  }
  return rows;
}

function spectraIgnoreUnavailableReason(editableRows) {
  if (!spectraManagementToolsVisible()) return "";
  const params = new URLSearchParams(window.location.search);
  if (asBool(params.get("mock"))) return "Mock spectra cannot be written to MOCAdb.";
  if (speState.payload?.meta?.bins_per_micron) return "Reload raw spectra to edit ignored flags.";
  if (spectraDisplayResolutionDecreased()) return "Disable display resolving-power reduction to edit ignored flags.";
  if (!speState.ignoreSpecids?.size) return "No spectra selected for updating.";
  if (!(speState.selectedPoints || []).length) return "No spectral rows selected.";
  if (!editableRows.length) return "No selected editable rows in the chosen spectra.";
  return "";
}

function updateSpectraIgnoreControls() {
  if (!speEl["spe-management-tools"] || speEl["spe-management-tools"].hidden) return;
  const editableRows = selectedEditableSpectralRows();
  const reason = spectraIgnoreUnavailableReason(editableRows);
  const summary = selectedSpectralRowsSummary(editableRows);
  if (speEl["spe-ignore-summary"]) speEl["spe-ignore-summary"].textContent = reason || summary;
  if (speEl["spe-ignore-selected"]) {
    speEl["spe-ignore-selected"].disabled = speState.ignoreBusy || Boolean(reason);
  }
}

function selectedSpectralRowsSummary(rows) {
  if (!rows.length) return "No editable rows selected.";
  const specids = [...new Set(rows.map((row) => row.moca_specid))].sort((a, b) => a - b);
  const wavelengths = rows.map((row) => row.lam).filter(finite);
  const range = wavelengths.length
    ? `, ${formatNumber(Math.min(...wavelengths), 6)}-${formatNumber(Math.max(...wavelengths), 6)} um`
    : "";
  return `${pluralize(rows.length, "editable row", "editable rows")} selected from ${pluralize(specids.length, "spectrum", "spectra")}${range}.`;
}

async function ignoreSelectedSpectralRows() {
  const editableRows = selectedEditableSpectralRows();
  const reason = spectraIgnoreUnavailableReason(editableRows);
  if (reason) {
    setSpectraIgnoreStatus(reason, "error");
    updateSpectraIgnoreControls();
    return;
  }
  const summary = selectedSpectralRowsSummary(editableRows);
  if (!window.confirm(`Set ignored=1 for ${summary}`)) return;

  speState.ignoreBusy = true;
  setSpectraIgnoreStatus("Updating selected rows...");
  updateSpectraIgnoreControls();
  try {
    const payload = await postSpectraJson("api/spectra/ignore", {
      data_spectra_ids: editableRows.map((row) => row.data_spectra_id),
      moca_specids: [...new Set(editableRows.map((row) => row.moca_specid))],
    });
    if (!payload.ok) throw new Error(payload.error || "Could not update ignored flags");
    speState.selectedPoints = [];
    await loadSpectra();
    const updated = Number(payload.updated_count || 0).toLocaleString();
    setSpectraIgnoreStatus(`Set ignored=1 for ${updated} spectral row${Number(payload.updated_count) === 1 ? "" : "s"}.`);
  } catch (error) {
    setSpectraIgnoreStatus(error.message || String(error), "error");
  } finally {
    speState.ignoreBusy = false;
    updateSpectraIgnoreControls();
  }
}

function setSpectraIgnoreStatus(text, mode = "") {
  if (!speEl["spe-ignore-status"]) return;
  speEl["spe-ignore-status"].textContent = text || "";
  speEl["spe-ignore-status"].classList.toggle("error", mode === "error");
}

function renderEmptySpectra(message) {
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
  ++speState.renderToken;
  Plotly.react(speEl["spe-plot"], [], layout, plotConfig("mocadb_spectral_explorer_empty"));
  speEl["spe-summary"].textContent = message;
  speEl["spe-table"].innerHTML = "";
  setSpectraExportDisabled(true);
  setSpectraLoading(false);
  setSpectraStatus(message, message.includes("Could not") ? "error" : "");
  updateSpectraIgnoreControls();
}

const rawSpectrumExportColumns = ["moca_specid", "moca_oid", "wavelength_um", "flux_flambda", "flux_flambda_unc", "flux_units", "ignored"];
const rawSpectrumNumericExportColumns = new Set(["moca_specid", "moca_oid", "wavelength_um", "flux_flambda", "flux_flambda_unc", "ignored"]);

function rawSpectrumExportRows(spectrum) {
  const metadata = spectrum.metadata || {};
  return (spectrum.rows || []).map((row) => ({
    moca_specid: spectrum.moca_specid,
    moca_oid: metadata.moca_oid || "",
    wavelength_um: row.lam,
    flux_flambda: row.sp,
    flux_flambda_unc: row.esp ?? "",
    flux_units: metadata.flux_units || "unknown",
    ignored: ignoredFlag(row.ignored),
  }));
}

function downloadRawSpectrum(specid, format = "csv") {
  const spectrum = (speState.payload?.spectra || []).find((item) => Number(item.moca_specid) === Number(specid));
  if (!spectrum) return;
  const metadata = spectrum.metadata || {};
  const rows = rawSpectrumExportRows(spectrum);
  if (format === "fits") {
    MocaExport.saveTable("fits", {
      rows,
      columns: rawSpectrumExportColumns,
      numericColumns: rawSpectrumNumericExportColumns,
      filenameBase: `mocadb_spectrum_specid${specid}`,
      tableName: `mocadb_spectrum_specid${specid}`,
      extName: "MOCA_SPECTRUM",
    });
    return;
  }
  const lines = [
    `# ${metadata.label || `specid${specid}`}`,
    rawSpectrumExportColumns.join(","),
    ...rows.map((row) => rawSpectrumExportColumns.map((column) => row[column]).map(csvCell).join(",")),
  ];
  downloadBlob(lines.join("\n"), `mocadb_spectrum_specid${specid}.csv`, "text/csv;charset=utf-8");
}

const plottedSpectraExportColumns = ["moca_specid", "moca_oid", "wavelength_um", "display_flux", "display_error", "raw_flambda", "raw_flambda_unc", "raw_flux_units", "display_unit", "normalized", "ignored"];
const plottedSpectraNumericExportColumns = new Set(["moca_specid", "moca_oid", "wavelength_um", "display_flux", "display_error", "raw_flambda", "raw_flambda_unc", "normalized", "ignored"]);

function exportPlottedSpectra(format) {
  const columns = plottedSpectraExportColumns;
  const rows = [];
  (speState.processed || []).forEach((spectrum) => {
    displayedSpectrumPoints(spectrum).forEach((point) => {
      rows.push({
        moca_specid: spectrum.specid,
        moca_oid: spectrum.metadata?.moca_oid || "",
        wavelength_um: point.lam,
        display_flux: point.y,
        display_error: point.yerr ?? "",
        raw_flambda: point.rawFlambdaUm,
        raw_flambda_unc: point.rawErrFlambdaUm ?? "",
        raw_flux_units: point.rawFluxUnit || spectrum.fluxUnitInfo?.displayUnit || "unknown",
        display_unit: yAxisUnit(),
        normalized: speEl["spe-snr"].checked ? 0 : (speEl["spe-normalize"].checked ? 1 : 0),
        ignored: point.ignored,
      });
    });
  });
  if (!rows.length) return;
  MocaExport.saveTable(format, {
    rows,
    columns,
    numericColumns: plottedSpectraNumericExportColumns,
    filenameBase: "mocadb_spectral_explorer_plotted",
    tableName: "mocadb_spectral_explorer_plotted",
    resourceName: "MOCAdb Spectral Explorer",
    extName: "SPECTRA",
  });
}

function setSpectraExportDisabled(disabled) {
  for (const id of ["spe-export-csv", "spe-export-tsv", "spe-export-fits", "spe-export-votable"]) {
    if (speEl[id]) speEl[id].disabled = disabled;
  }
}

async function clearSpectraCache() {
  if (speEl["spe-clear-cache"]) speEl["spe-clear-cache"].disabled = true;
  speEl["spe-clear-cache-bottom"].disabled = true;
  speEl["spe-clear-cache-status"].textContent = "Clearing...";
  speEl["spe-clear-cache-status"].classList.remove("error");
  try {
    const payload = await postSpectraJson("api/spectra/cache/clear", {});
    if (!payload.ok) throw new Error(payload.error || "Cache clear failed");
    const cleared = payload.cleared?.spectraExplorer || 0;
    speEl["spe-clear-cache-status"].textContent = `Cleared ${cleared} cached spectra payload${cleared === 1 ? "" : "s"}.`;
    if (speState.selected.length) await loadSpectra();
  } catch (error) {
    speEl["spe-clear-cache-status"].textContent = error.message;
    speEl["spe-clear-cache-status"].classList.add("error");
  } finally {
    if (speEl["spe-clear-cache"]) speEl["spe-clear-cache"].disabled = false;
    speEl["spe-clear-cache-bottom"].disabled = false;
  }
}

function updateSpectraUrl() {
  const params = new URLSearchParams(window.location.search);
  if (speState.selected.length) params.set("moca_specid", speState.selected.map((item) => item.specid).join(","));
  else params.delete("moca_specid");
  params.delete("specid");
  params.delete("specids");
  setBoolParam(params, "hover", speEl["spe-hover"].checked);
  setBoolParam(params, "error_shade", speEl["spe-error-shade"].checked);
  setBoolParam(params, "snr", speEl["spe-snr"].checked);
  if (!speEl["spe-hide-ignored"].checked) params.set("hide_ignored", "0");
  else params.delete("hide_ignored");
  params.delete("include_ignored");
  params.delete("show_ignored");
  setBoolParam(params, "xlog", speEl["spe-xlog"].checked);
  setBoolParam(params, "ylog", speEl["spe-ylog"].checked);
  params.delete("xrange");
  params.delete("x_range");
  params.delete("wavelength_range");
  params.delete("xmin");
  params.delete("x_min");
  params.delete("lambda_min");
  params.delete("xmax");
  params.delete("x_max");
  params.delete("lambda_max");
  const xRangeMin = parsePositiveNumber(speEl["spe-xrange-min"].value);
  const xRangeMax = parsePositiveNumber(speEl["spe-xrange-max"].value);
  if (xRangeMin !== null && xRangeMax !== null && xRangeMin !== xRangeMax) {
    const lower = Math.min(xRangeMin, xRangeMax);
    const upper = Math.max(xRangeMin, xRangeMax);
    params.set("xrange", `${formatXRangeUrlNumber(lower)}-${formatXRangeUrlNumber(upper)}`);
  } else {
    if (xRangeMin !== null) params.set("xmin", formatXRangeUrlNumber(xRangeMin));
    if (xRangeMax !== null) params.set("xmax", formatXRangeUrlNumber(xRangeMax));
  }
  setBoolParam(params, "fnu_jy", speEl["spe-fnu"].checked);
  if (!speEl["spe-showfeatures"].checked) params.set("showfeatures", "0");
  else params.delete("showfeatures");
  setBoolParam(params, "disable_lowres", speEl["spe-disable-lowres"].checked);
  setBoolParam(params, "decrease_resolution", spectraDisplayResolutionDecreased());
  params.delete("decrease_resolving_power");
  params.delete("display_lowres");
  params.delete("display_bins_per_micron");
  params.delete("decrease_resolution_bins");
  if (spectraDisplayResolutionDecreased()) params.set("display_bins", String(spectraDisplayBinsPerMicron()));
  else params.delete("display_bins");
  if (!speEl["spe-normalize"].checked) params.set("normalize", "0");
  else params.delete("normalize");
  if ((speEl["spe-normrange"].value || "").trim() !== speDefaultNorm) params.set("norm", speEl["spe-normrange"].value.trim());
  else params.delete("norm");
  window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}

function setSpectraStatus(text, mode = "") {
  speEl["spe-status"].textContent = text;
  speEl["spe-status"].className = `status${mode ? ` ${mode}` : ""}`;
}

function setSpectraLoading(loading) {
  speEl["spe-plot-loader"].classList.toggle("is-visible", Boolean(loading));
}

function yAxisTitle() {
  if (speEl["spe-snr"].checked) return "S/N per pixel";
  if (speEl["spe-normalize"].checked) {
    return speEl["spe-fnu"].checked
      ? "Relative spectral flux density <i>F</i><sub>ν</sub>"
      : "Relative spectral flux density <i>F</i><sub>λ</sub>";
  }
  return speEl["spe-fnu"].checked
    ? "Flux density <i>F</i><sub>ν</sub> (Jy)"
    : `Spectral flux density <i>F</i><sub>λ</sub> (${spectrumDisplayFluxUnit()})`;
}

function yAxisUnit() {
  if (speEl["spe-snr"].checked) return "S/N";
  if (speEl["spe-normalize"].checked) return "relative";
  return speEl["spe-fnu"].checked ? "Jy" : spectrumDisplayFluxUnit();
}

function spectrumFluxUnitInfo(metadata = {}) {
  const storedUnit = String(metadata?.flux_units || "").trim();
  const normalized = storedUnit.toLowerCase().replace(/[µμ]/g, "u").replace(/å/g, "angstrom");
  const explicitlyRelative = !storedUnit || normalized === "no_units" || normalized.startsWith("relative");
  const hasWatts = /(?:^|[^a-z])w(?:$|[^a-z])/.test(normalized);
  const perSquareMeter = /m\s*(?:\^\s*)?-\s*2/.test(normalized) || /\/\s*m\s*(?:\^\s*)?2/.test(normalized) || normalized.includes("m²");
  const perAngstrom = normalized.includes("angstrom") || /\/\s*\[?\s*a\s*\]?(?:$|[^a-z])/.test(normalized) || /(?:^|[^a-z])a\s*(?:\^\s*)?-\s*1(?:$|[^a-z])/.test(normalized);
  const canonical = !explicitlyRelative && hasWatts && perSquareMeter && perAngstrom;
  return {
    canonical,
    storedUnit: storedUnit || "unknown",
    displayUnit: canonical ? "W/m²/μm" : (storedUnit || "native units"),
  };
}

function spectrumDisplayFluxUnit() {
  const infos = (speState.payload?.spectra || []).map((spectrum) => spectrumFluxUnitInfo(spectrum.metadata || {}));
  if (!infos.length || infos.every((info) => info.canonical)) return "W/m²/μm";
  const units = [...new Set(infos.map((info) => info.displayUnit))];
  return units.length === 1 ? units[0] : "native units vary by spectrum";
}

function updateSpectraFluxUnitControls() {
  const infos = (speState.payload?.spectra || []).map((spectrum) => spectrumFluxUnitInfo(spectrum.metadata || {}));
  const nonCanonicalCount = infos.filter((info) => !info.canonical).length;
  const fnu = speEl["spe-fnu"];
  if (!fnu) return nonCanonicalCount;
  if (nonCanonicalCount && fnu.checked) fnu.checked = false;
  fnu.disabled = nonCanonicalCount > 0;
  fnu.title = nonCanonicalCount
    ? "Jy conversion requires every loaded spectrum to have absolute F_lambda units in W m^-2 Angstrom^-1."
    : "";
  return nonCanonicalCount;
}

function spectrumName(metadata, specid) {
  const designation = metadata?.designation || metadata?.spectrum_name || `specid${specid}`;
  const spt = metadata?.spectral_type ? ` (${metadata.spectral_type})` : "";
  return `${designation}${spt}`;
}

function spectrumLegendName(metadata, specid, points = []) {
  const oid = normalizedMocaOid(metadata?.moca_oid);
  const idText = [oid ? `oid${oid}` : "", `specid${specid}`].filter(Boolean).join(" / ");
  const instrument = instrumentLegendLabel(metadata);
  const wavelengthRange = wavelengthRangeLabel(points);
  return `${idText}: ${spectrumName(metadata, specid)}${instrument ? ` [${instrument}]` : ""}${wavelengthRange ? ` ${wavelengthRange}` : ""}`;
}

function instrumentLabel(metadata) {
  return metadata?.instrument_description || metadata?.moca_instrument_description || metadata?.moca_instid || "";
}

function instrumentLegendLabel(metadata) {
  const instrument = String(
    metadata?.moca_instid
    || metadata?.moca_instrument_id
    || metadata?.instrument_name
    || metadata?.instrument_description
    || metadata?.moca_instrument_description
    || ""
  ).trim();
  const mode = String(metadata?.instrument_mode_name || "").trim();
  if (!instrument) return mode;
  if (!mode || instrument.toLowerCase().includes(mode.toLowerCase())) return instrument;
  return `${instrument} ${mode}`;
}

function wavelengthRangeLabel(points) {
  const wavelengths = (points || []).map((point) => Number(point?.lam)).filter(finite);
  if (!wavelengths.length) return "";
  const minWavelength = Math.min(...wavelengths);
  const maxWavelength = Math.max(...wavelengths);
  if (!finite(minWavelength) || !finite(maxWavelength)) return "";
  return `(${minWavelength.toFixed(1)}-${maxWavelength.toFixed(1)} μm)`;
}

function observationDateLabel(metadata) {
  return metadata?.data_collection_date || metadata?.obs_date || metadata?.observation_date || "";
}

function spectrumReferenceLabel(metadata) {
  if (!metadata?.moca_pid && !metadata?.mocaPid) return "";
  return metadata?.spectrumRef
    || metadata?.spectrum_ref
    || metadata?.spectrum_reference
    || metadata?.publication_name
    || "";
}

function spectrumBibcodeLabel(metadata) {
  return metadata?.spectrumBibcode
    || metadata?.publication_bibcode
    || metadata?.reference_bibcode
    || metadata?.spectrum_bibcode
    || "";
}

function spectrumReferenceUrl(metadata) {
  const url = String(metadata?.spectrumRefUrl
    || metadata?.spectrum_ref_url
    || metadata?.publication_url
    || metadata?.reference_url
    || "").trim();
  if (!url) return "";
  try {
    const parsed = new URL(url, window.location.href);
    if (!["http:", "https:"].includes(parsed.protocol)) return "";
    return parsed.href;
  } catch (error) {
    return "";
  }
}

function spectrumReferenceHtml(metadata) {
  const label = spectrumReferenceLabel(metadata);
  if (!label) return "";
  const url = spectrumReferenceUrl(metadata);
  if (!url) return escapeHtml(label);
  return `<a class="report-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`;
}

function wavelengthMicron(value) {
  const lam = Number(value);
  if (!finite(lam) || lam <= 0) return NaN;
  // The API normally returns microns, but older/mock payloads may still expose Angstrom values.
  return lam > 100 ? lam * 1e-4 : lam;
}

function firstFiniteNumber(...values) {
  for (const value of values) {
    if (finite(value)) return Number(value);
  }
  return null;
}

function spectrumLowresResolvingPowerPerPixel(spectrum) {
  const storedMetric = firstFiniteNumber(
    spectrum?.meta?.lowres_resolving_power_per_pixel,
    spectrum?.meta?.resolving_power_per_pixel
  );
  if (finite(storedMetric)) return storedMetric;
  const medianResolvingPower = firstFiniteNumber(
    spectrum?.meta?.median_spectral_resolving_power,
    spectrum?.metadata?.median_spectral_resolving_power,
    spectrum?.meta?.stored_average_resolving_power
  );
  if (!finite(medianResolvingPower)) return null;
  const storedPixPerResElement = firstFiniteNumber(
    spectrum?.meta?.pix_per_res_element,
    spectrum?.metadata?.pix_per_res_element
  );
  const pixPerResElement = finite(storedPixPerResElement)
    ? storedPixPerResElement
    : speDefaultPixPerResolutionElement;
  if (!finite(pixPerResElement) || pixPerResElement <= 0) return null;
  return medianResolvingPower / pixPerResElement;
}

function spectrumUsesLowresDisplay(spectrum) {
  const resolvingPowerPerPixel = spectrumLowresResolvingPowerPerPixel(spectrum);
  return finite(resolvingPowerPerPixel)
    && resolvingPowerPerPixel < speLowResolutionResolvingPowerPerPixelThreshold;
}

function parseNormRange(raw) {
  const match = String(raw || "").match(/(-?\d+(?:\.\d+)?)\s*[-:]\s*(-?\d+(?:\.\d+)?)/);
  if (!match) return [0.95, 1.35];
  const a = Number(match[1]);
  const b = Number(match[2]);
  if (!finite(a) || !finite(b) || a === b) return [0.95, 1.35];
  return [Math.min(a, b), Math.max(a, b)];
}

function parseSpectraDisplayXRangeUrl(params) {
  const fromRange = parseSpectraRangeText(params.get("xrange") || params.get("x_range") || params.get("wavelength_range"));
  const min = parsePositiveNumber(params.get("xmin") || params.get("x_min") || params.get("lambda_min")) ?? fromRange.min;
  const max = parsePositiveNumber(params.get("xmax") || params.get("x_max") || params.get("lambda_max")) ?? fromRange.max;
  return { min: formatXRangeControlNumber(min), max: formatXRangeControlNumber(max) };
}

function parseSpectraRangeText(raw) {
  const values = String(raw || "")
    .match(/\d*\.?\d+(?:e[+-]?\d+)?/gi)
    ?.map(Number)
    .filter((value) => finite(value) && value > 0) || [];
  if (values.length < 2 || values[0] === values[1]) return { min: null, max: null };
  return { min: Math.min(values[0], values[1]), max: Math.max(values[0], values[1]) };
}

function spectraDisplayXRange(autoRange = null) {
  const min = parsePositiveNumber(speEl["spe-xrange-min"]?.value);
  const max = parsePositiveNumber(speEl["spe-xrange-max"]?.value);
  if (min === null && max === null) return null;
  let lower = min ?? (Array.isArray(autoRange) ? Number(autoRange[0]) : null);
  let upper = max ?? (Array.isArray(autoRange) ? Number(autoRange[1]) : null);
  if (!finite(lower) || !finite(upper) || lower <= 0 || upper <= 0 || lower === upper) return null;
  if (lower > upper && min !== null && max !== null) [lower, upper] = [upper, lower];
  return lower < upper ? [lower, upper] : null;
}

function parsePositiveNumber(value) {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const number = Number(value);
  return finite(number) && number > 0 ? number : null;
}

function formatXRangeControlNumber(value) {
  if (!finite(value) || Number(value) <= 0) return "";
  return Number(value).toPrecision(8).replace(/\.?0+$/, "");
}

function formatXRangeUrlNumber(value) {
  if (!finite(value) || Number(value) <= 0) return "";
  return Number(value).toPrecision(10).replace(/\.?0+$/, "");
}

function numericAxisRange(values, options = {}) {
  const log = Boolean(options.log);
  const padFraction = options.padFraction ?? 0.035;
  const fallback = options.fallback || null;
  const clean = values.map(Number).filter((value) => finite(value) && (!log || value > 0)).sort((a, b) => a - b);
  if (!clean.length) return fallback;
  const lo = clean.length >= 20 ? quantile(clean, 0.002) : clean[0];
  const hi = clean.length >= 20 ? quantile(clean, 0.998) : clean[clean.length - 1];
  if (!finite(lo) || !finite(hi) || hi <= lo) return fallback;
  if (log) {
    const logLo = Math.log10(lo);
    const logHi = Math.log10(hi);
    const pad = Math.max(0.015, (logHi - logLo) * padFraction);
    return [10 ** (logLo - pad), 10 ** (logHi + pad)];
  }
  const pad = Math.max((hi - lo) * padFraction, Math.abs(hi || lo || 1) * 1e-6);
  return [lo - pad, hi + pad];
}

function quantile(sortedValues, q) {
  if (!sortedValues.length) return NaN;
  const index = Math.min(Math.max(q, 0), 1) * (sortedValues.length - 1);
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sortedValues[lower];
  const frac = index - lower;
  return sortedValues[lower] * (1 - frac) + sortedValues[upper] * frac;
}

function plainLogTicks(xmin, xmax, options = {}) {
  const ticks = [];
  if (!finite(xmin) || !finite(xmax) || xmin <= 0 || xmax <= xmin) return { values: [], text: [] };
  const lo = Math.floor(Math.log10(xmin)) - 1;
  const hi = Math.ceil(Math.log10(xmax)) + 1;
  for (let decade = lo; decade <= hi; decade += 1) {
    const base = 10 ** decade;
    for (let multiplier = 1; multiplier < 10; multiplier += 1) {
      const value = multiplier * base;
      if (value >= xmin && value <= xmax) ticks.push({ value, major: multiplier === 1 });
    }
  }
  const minTicks = Number.isFinite(Number(options.minTicks)) ? Math.max(1, Number(options.minTicks)) : 3;
  const labeledCount = options.majorLabelsOnly ? ticks.filter((tick) => tick.major).length : ticks.length;
  if (ticks.length < minTicks || labeledCount < Math.min(2, minTicks)) {
    const linearTicks = niceLinearTickObjects(xmin, xmax, options.fallbackTickCount || 5);
    if (linearTicks.length) {
      return {
        values: linearTicks.map((tick) => tick.value),
        text: linearTicks.map((tick) => tick.text),
      };
    }
  }
  return {
    values: ticks.map((tick) => tick.value),
    text: ticks.map((tick) => options.majorLabelsOnly && !tick.major ? "" : formatPlainLogTick(tick.value)),
  };
}

function niceLinearTickObjects(xmin, xmax, targetCount = 5) {
  if (!finite(xmin) || !finite(xmax) || xmax <= xmin) return [];
  const count = Math.max(2, Math.min(8, Math.round(Number(targetCount) || 5)));
  const step = niceLinearTickStep((xmax - xmin) / Math.max(1, count - 1));
  if (!finite(step) || step <= 0) return [];
  const start = Math.ceil((xmin - step * 1e-9) / step) * step;
  const values = [];
  for (let value = start; value <= xmax + step * 1e-9 && values.length < 20; value += step) {
    const rounded = roundNiceLinearTick(value, step);
    if (rounded >= xmin - step * 1e-8 && rounded <= xmax + step * 1e-8) values.push(rounded);
  }
  if (values.length < 2) {
    values.push(roundNiceLinearTick(xmin, (xmax - xmin) / 2));
    values.push(roundNiceLinearTick((xmin + xmax) / 2, (xmax - xmin) / 2));
    values.push(roundNiceLinearTick(xmax, (xmax - xmin) / 2));
  }
  const unique = [...new Set(values)].sort((a, b) => a - b);
  return unique.map((value) => ({ value, text: formatNiceLinearTick(value, step) }));
}

function niceLinearTickStep(rawStep) {
  if (!finite(rawStep) || rawStep <= 0) return NaN;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10;
  return nice * magnitude;
}

function roundNiceLinearTick(value, step) {
  const decimals = niceLinearTickDecimals(step);
  return Number(Number(value).toFixed(decimals));
}

function formatNiceLinearTick(value, step) {
  if (Math.abs(value) >= 1000 && Math.abs(step) >= 1) {
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  const decimals = niceLinearTickDecimals(step);
  return Number(value).toFixed(decimals).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

function niceLinearTickDecimals(step) {
  const positiveStep = Math.abs(Number(step));
  if (!finite(positiveStep) || positiveStep <= 0 || positiveStep >= 1) return 0;
  return Math.min(8, Math.max(0, Math.ceil(-Math.log10(positiveStep)) + 1));
}

function formatPlainLogTick(value) {
  if (value >= 1000) return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (value >= 100) return String(Math.round(value));
  if (value >= 10) return Math.abs(value - Math.round(value)) < 1e-8 ? String(Math.round(value)) : value.toFixed(1).replace(/\.0$/, "");
  if (value >= 1) return Math.abs(value - Math.round(value)) < 1e-8 ? String(Math.round(value)) : value.toPrecision(2);
  if (value >= 0.01) return value.toPrecision(2);
  return value.toExponential(0).replace("e", "x10^");
}

function robustMedian(values) {
  const clean = values.map(Number).filter(finite).sort((a, b) => a - b);
  if (!clean.length) return NaN;
  const mid = Math.floor(clean.length / 2);
  return clean.length % 2 ? clean[mid] : 0.5 * (clean[mid - 1] + clean[mid]);
}

function tableHtml(columns, rows, options = {}) {
  const htmlColumns = options.htmlColumns || new Set();
  if (!rows.length) return `<div class="selection-table">No rows to display.</div>`;
  return `
    <div class="selection-table">
      <table>
        <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              ${columns.map((column) => `<td>${htmlColumns.has(column) ? (row[column] || "") : escapeHtml(row[column] ?? "")}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function apiParams() {
  const source = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "port", "user", "username", "pwd", "password", "dbase", "db", "database", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  if (!params.has("user") && params.has("username")) params.set("user", params.get("username"));
  if (!params.has("pwd") && params.has("password")) params.set("pwd", params.get("password"));
  if (!params.has("dbase")) {
    if (params.has("db")) params.set("dbase", params.get("db"));
    else if (params.has("database")) params.set("dbase", params.get("database"));
  }
  return params;
}

async function postSpectraJson(path, body) {
  const params = apiParams();
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(speAppUrl(`${path}${params.toString() ? `${separator}${params.toString()}` : ""}`), {
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
  const managementMode = spectraManagementToolsVisible();
  const config = {
    responsive: true,
    displaylogo: false,
    toImageButtonOptions: {
      format: "png",
      height: 900,
      width: 1700,
      scale: 2,
      filename,
    },
  };
  if (managementMode) {
    config.displayModeBar = true;
    config.modeBarButtonsToAdd = ["select2d", "lasso2d"];
  }
  return config;
}

function setBoolParam(params, key, checked) {
  if (checked) params.set(key, "1");
  else params.delete(key);
}

function pluralize(count, singular, plural) {
  const formatted = Number(count || 0).toLocaleString();
  return `${formatted} ${Number(count) === 1 ? singular : plural}`;
}

function spectraBoxAxisStyle() {
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

function uniqueIntegers(values) {
  const seen = new Set();
  const out = [];
  values.forEach((value) => {
    const integer = parseInteger(value);
    if (integer === null || seen.has(integer)) return;
    seen.add(integer);
    out.push(integer);
  });
  return out;
}

function parseInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function finite(value) {
  if (value === null || value === undefined || value === "") return false;
  return Number.isFinite(Number(value));
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

function asFalse(value) {
  return ["0", "false", "no", "off"].includes(String(value || "").toLowerCase());
}

function ignoredFlag(value) {
  if (value === true) return 1;
  if (value === false || value === null || value === undefined || value === "") return 0;
  const number = Number(value);
  if (Number.isFinite(number)) return number !== 0 ? 1 : 0;
  return asBool(value) ? 1 : 0;
}

function formatNumber(value, digits) {
  return finite(value) ? Number(value).toFixed(digits) : "";
}

function formatScientific(value) {
  return finite(value) ? Number(value).toExponential(6) : "";
}

function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
