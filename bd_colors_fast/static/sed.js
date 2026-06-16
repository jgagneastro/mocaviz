const sedDefaultOid = 10995;
const sedSpeedOfLight = 299792458.0;
const sedParsecMeters = 3.0856775814913673e16;
const sedLsunWatts = 3.828e26;
const sedEmpiricalWeightCapFactor = 5;
const sedGroundTelluricRanges = [
  [1.35, 1.46],
  [1.79, 1.98],
  [2.4, Infinity],
];
const sedColors = ["#377EB8", "#E41A1C", "#4DAF4A", "#984EA3", "#FF7F00", "#A65628", "#F781BF", "#666666", "#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3"];

const sedState = {
  oid: sedDefaultOid,
  payload: null,
  template: null,
  visible: {},
  selectedRows: [],
  filterResponseDisplay: null,
  empirical: null,
  selectedSpectrumKeys: new Set(),
  selectedSpectrumRows: {},
  selectedPhotometryKeys: new Set(),
  selectionDisabledSpectra: new Set(),
  carvedSpectrumRows: {},
  plotResetRanges: null,
  resettingAxes: false,
  searchTimer: null,
  templateSearchTimer: null,
  loadToken: 0,
};

const sedEl = {};

document.addEventListener("DOMContentLoaded", initSedExplorer);

const sedAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function sedAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), sedAppBaseUrl).toString();
}

async function initSedExplorer() {
  collectSedElements();
  readSedUrlState();
  bindSedControls();
  renderSedTargetToken();
  const templateId = parseInteger(new URLSearchParams(window.location.search).get("template_id"));
  await loadSedObject();
  if (templateId !== null) await loadSedTemplate(templateId);
}

function collectSedElements() {
  [
    "sed-status",
    "sed-search",
    "sed-results",
    "sed-target-token",
    "sed-load",
    "sed-clear-cache",
    "sed-xunit",
    "sed-yunit",
    "sed-xlog",
    "sed-ylog",
    "sed-hover",
    "sed-hide-ignored",
    "sed-show-filter-responses",
    "sed-anchor-spectra",
    "sed-anchor-ground-only",
    "sed-exclude-ground-telluric",
    "sed-spectrum-ranges",
    "sed-template-search",
    "sed-template-results",
    "sed-template-token",
    "sed-show-template",
    "sed-template-scale-mode",
    "sed-clear-template",
    "sed-extend-short",
    "sed-extend-long",
    "sed-construct",
    "sed-clear-empirical",
    "sed-remove-selection",
    "sed-carve-selection",
    "sed-remove-photometry-selection",
    "sed-clear-spectrum-removals",
    "sed-clear-spectrum-carves",
    "sed-spectrum-selection-note",
    "sed-bolometric-summary",
    "sed-layer-tokens",
    "sed-plot",
    "sed-plot-loader",
    "sed-summary",
    "sed-hint",
    "sed-flux-note",
    "sed-table-title",
    "sed-table-subtitle",
    "sed-table",
  ].forEach((id) => {
    sedEl[id] = document.getElementById(id);
  });
}

function readSedUrlState() {
  const params = new URLSearchParams(window.location.search);
  const oid = parseInteger(params.get("moca_oid") || params.get("oid") || params.get("target_oid"));
  sedState.oid = oid || sedDefaultOid;
  sedEl["sed-xunit"].value = params.get("xunit") || "um";
  sedEl["sed-yunit"].value = params.get("yunit") || "lambda_flambda";
  sedEl["sed-xlog"].checked = !asFalse(params.get("xlog"));
  sedEl["sed-ylog"].checked = !asFalse(params.get("ylog"));
  sedEl["sed-hover"].checked = params.has("hover") ? !asFalse(params.get("hover")) : true;
  sedEl["sed-hide-ignored"].checked = !asFalse(params.get("hide_ignored"));
  sedEl["sed-show-filter-responses"].checked = params.has("filter_responses") ? !asFalse(params.get("filter_responses")) : false;
  sedEl["sed-anchor-spectra"].checked = params.has("anchor_spectra") ? !asFalse(params.get("anchor_spectra")) : true;
  sedEl["sed-anchor-ground-only"].checked = params.has("anchor_ground_only") ? !asFalse(params.get("anchor_ground_only")) : true;
  sedEl["sed-exclude-ground-telluric"].checked = params.has("exclude_ground_telluric") ? !asFalse(params.get("exclude_ground_telluric")) : true;
  sedEl["sed-spectrum-ranges"].value = params.get("spectrum_ranges") || params.get("spectrum_wavelength") || params.get("spectral_ranges") || "";
  sedEl["sed-show-template"].checked = params.has("show_template") ? !asFalse(params.get("show_template")) : true;
  sedEl["sed-template-scale-mode"].value = params.get("template_scale") || "photometry";
  sedEl["sed-extend-short"].checked = params.has("extend_short") ? !asFalse(params.get("extend_short")) : true;
  sedEl["sed-extend-long"].checked = params.has("extend_long") ? !asFalse(params.get("extend_long")) : true;
}

function bindSedControls() {
  sedEl["sed-search"].addEventListener("input", () => {
    const value = sedEl["sed-search"].value.trim();
    clearTimeout(sedState.searchTimer);
    sedState.searchTimer = setTimeout(() => searchSedObjects(value), 250);
  });
  sedEl["sed-search"].addEventListener("focus", () => {
    const value = sedEl["sed-search"].value.trim();
    if (value) searchSedObjects(value);
  });
  sedEl["sed-template-search"].addEventListener("input", () => {
    const value = sedEl["sed-template-search"].value.trim();
    clearTimeout(sedState.templateSearchTimer);
    sedState.templateSearchTimer = setTimeout(() => searchSedTemplates(value), 250);
  });
  sedEl["sed-template-search"].addEventListener("focus", () => {
    const value = sedEl["sed-template-search"].value.trim();
    if (value) searchSedTemplates(value);
  });
  document.addEventListener("click", (event) => {
    if (!sedEl["sed-results"].contains(event.target) && event.target !== sedEl["sed-search"]) {
      sedEl["sed-results"].hidden = true;
    }
    if (!sedEl["sed-template-results"].contains(event.target) && event.target !== sedEl["sed-template-search"]) {
      sedEl["sed-template-results"].hidden = true;
    }
  });
  sedEl["sed-load"].addEventListener("click", loadSedObject);
  sedEl["sed-clear-cache"].addEventListener("click", clearSedCache);
  sedEl["sed-clear-template"].addEventListener("click", () => {
    sedState.template = null;
    delete sedState.visible.template;
    renderSed();
    updateSedUrl();
  });
  sedEl["sed-construct"].addEventListener("click", constructEmpiricalSed);
  sedEl["sed-clear-empirical"].addEventListener("click", clearEmpiricalSed);
  sedEl["sed-remove-selection"].addEventListener("click", disableSelectedSpectra);
  sedEl["sed-carve-selection"].addEventListener("click", carveSelectedSpectrumRows);
  sedEl["sed-remove-photometry-selection"].addEventListener("click", disableSelectedPhotometry);
  sedEl["sed-clear-spectrum-removals"].addEventListener("click", restoreSelectionDisabledSpectra);
  sedEl["sed-clear-spectrum-carves"].addEventListener("click", restoreCarvedSpectrumRows);
  sedEl["sed-spectrum-ranges"].addEventListener("input", debounce(() => {
    renderSed();
    updateSedUrl();
  }, 350));
  sedEl["sed-spectrum-ranges"].addEventListener("change", () => {
    renderSed();
    updateSedUrl();
  });
  for (const id of [
    "sed-xunit",
    "sed-yunit",
    "sed-xlog",
    "sed-ylog",
    "sed-hover",
    "sed-show-filter-responses",
    "sed-anchor-spectra",
    "sed-anchor-ground-only",
    "sed-exclude-ground-telluric",
    "sed-show-template",
    "sed-template-scale-mode",
    "sed-extend-short",
    "sed-extend-long",
  ]) {
    sedEl[id].addEventListener("change", () => {
      renderSed();
      updateSedUrl();
    });
  }
  sedEl["sed-hide-ignored"].addEventListener("change", loadSedObject);
  window.addEventListener("resize", debounce(() => {
    if (!sedEl["sed-results"].hidden) positionPopup(sedEl["sed-search"], sedEl["sed-results"]);
    if (!sedEl["sed-template-results"].hidden) positionPopup(sedEl["sed-template-search"], sedEl["sed-template-results"]);
    if (sedState.payload) renderSed();
  }, 150));
}

async function searchSedObjects(query) {
  if (!query) {
    sedEl["sed-results"].hidden = true;
    return;
  }
  if (query.length < 2 && !/^\d+$/.test(query)) {
    sedEl["sed-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    showPopup(sedEl["sed-search"], sedEl["sed-results"]);
    return;
  }
  const params = apiParams();
  params.set("q", query);
  const payload = await fetchJsonUrl(sedAppUrl(`api/sed/search?${params.toString()}`));
  if (!payload.ok) {
    sedEl["sed-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
    showPopup(sedEl["sed-search"], sedEl["sed-results"]);
    return;
  }
  renderSearchResults(payload.options || [], sedEl["sed-results"], async (result) => {
    sedState.oid = Number(result.value);
    sedEl["sed-search"].value = "";
    sedEl["sed-results"].hidden = true;
    await loadSedObject();
  });
}

async function searchSedTemplates(query) {
  if (!query) {
    sedEl["sed-template-results"].hidden = true;
    return;
  }
  if (query.length < 2 && !/^\d+$/.test(query)) {
    sedEl["sed-template-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    showPopup(sedEl["sed-template-search"], sedEl["sed-template-results"]);
    return;
  }
  const params = apiParams();
  params.set("q", query);
  const payload = await fetchJsonUrl(sedAppUrl(`api/sed/templates/search?${params.toString()}`));
  if (!payload.ok) {
    sedEl["sed-template-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
    showPopup(sedEl["sed-template-search"], sedEl["sed-template-results"]);
    return;
  }
  renderSearchResults(payload.options || [], sedEl["sed-template-results"], async (result) => {
    sedEl["sed-template-search"].value = "";
    sedEl["sed-template-results"].hidden = true;
    await loadSedTemplate(Number(result.value));
  });
}

function renderSearchResults(results, container, onSelect) {
  if (!results.length) {
    container.innerHTML = `<div class="designation-result-note">No matches found</div>`;
    showPopupForContainer(container);
    return;
  }
  container.innerHTML = results.map((result, index) => (
    `<button class="designation-result" type="button" data-index="${index}"><span>${escapeHtml(result.label || result.value)}</span></button>`
  )).join("");
  container.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => onSelect(results[Number(button.dataset.index)]));
  });
  showPopupForContainer(container);
}

function showPopupForContainer(container) {
  if (container === sedEl["sed-results"]) showPopup(sedEl["sed-search"], container);
  else showPopup(sedEl["sed-template-search"], container);
}

function showPopup(input, popup) {
  positionPopup(input, popup);
  popup.hidden = false;
}

function positionPopup(input, popup) {
  if (!input || !popup) return;
  const rect = input.getBoundingClientRect();
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - 360));
  const available = Math.max(320, window.innerWidth - left - 16);
  const width = Math.min(860, available);
  popup.style.position = "fixed";
  popup.style.left = `${left}px`;
  popup.style.top = `${rect.bottom + 6}px`;
  popup.style.width = `${width}px`;
  popup.style.zIndex = 1000;
}

async function loadSedObject() {
  const token = ++sedState.loadToken;
  setSedLoading(true);
  setSedStatus("Loading SED", "loading");
  updateSedUrl();
  const params = apiParams();
  params.set("hide_ignored", sedEl["sed-hide-ignored"].checked ? "1" : "0");
  const requestedBins = new URLSearchParams(window.location.search).get("bins") || "";
  if (requestedBins) params.set("bins", requestedBins);
  const payload = await fetchJsonUrl(sedAppUrl(`api/sed/object/${Number(sedState.oid)}?${params.toString()}`));
  if (token !== sedState.loadToken) return;
  if (!payload.ok) {
    setSedStatus(payload.error || "Could not load SED", "error");
    sedEl["sed-summary"].textContent = payload.error || "Could not load SED";
    setSedLoading(false);
    return;
  }
  sedState.payload = payload;
  sedState.oid = Number(payload.target?.moca_oid || sedState.oid);
  sedState.selectedRows = [];
  sedState.empirical = null;
  clearPlotlySelectionState();
  sedState.selectionDisabledSpectra = new Set();
  sedState.carvedSpectrumRows = {};
  resetVisibleForLoadedObject();
  ensureLayerDefaults();
  renderSedTargetToken();
  renderSed();
  updateSedUrl();
}

async function loadSedTemplate(templateId) {
  if (!Number.isFinite(Number(templateId))) return;
  setSedStatus("Loading template", "loading");
  const params = apiParams();
  const payload = await fetchJsonUrl(sedAppUrl(`api/sed/template/${Number(templateId)}?${params.toString()}`));
  if (!payload.ok) {
    setSedStatus(payload.error || "Could not load template", "error");
    return;
  }
  sedState.template = payload.template;
  sedState.visible.template = true;
  renderSedTemplateToken();
  renderSed();
  updateSedUrl();
}

function ensureLayerDefaults() {
  const payload = sedState.payload || {};
  (payload.photometry || []).forEach((row, index) => {
    const key = photKey(row, index);
    if (sedState.visible[key] === undefined) {
      sedState.visible[key] = row.conversion_status === "ok";
    }
  });
  (payload.spectra || []).forEach((spectrum) => {
    const key = specKey(spectrum);
    if (sedState.visible[key] === undefined) sedState.visible[key] = true;
  });
  if (sedState.template && sedState.visible.template === undefined) sedState.visible.template = true;
  if (sedState.empirical && sedState.visible.empirical === undefined) sedState.visible.empirical = true;
}

function resetVisibleForLoadedObject() {
  const templateVisible = sedState.visible.template;
  sedState.visible = {};
  if (templateVisible !== undefined) sedState.visible.template = templateVisible;
}

function renderSed() {
  if (!sedState.payload) return;
  setSedLoading(true);
  clearPlotlySelectionState();
  ensureLayerDefaults();
  renderSedTemplateToken();
  const processed = buildSedProcessedData();
  renderLayerTokens(processed);
  renderBolometricSummary();
  const baseTraces = sedTraces(processed);
  const layout = sedLayout(processed, baseTraces);
  const filterResponses = filterResponseOverlays(processed, layout);
  const traces = [...baseTraces, ...filterResponses.traces];
  sedState.filterResponseDisplay = filterResponses.info;
  sedState.plotResetRanges = sedAxisResetRangesFromLayout(layout);
  Plotly.react(sedEl["sed-plot"], traces, layout, plotConfig("mocadb_sed_explorer")).then(() => {
    updateSedPlotInitialRanges(sedEl["sed-plot"], sedState.plotResetRanges);
  });
  bindSedPlotEvents();
  renderSedSummary(processed);
  renderSedTable();
  updateSpectrumSelectionControls();
  setSedLoading(false);
}

function buildSedProcessedData() {
  const distance = sedDistance();
  const spectrumRanges = parseSedWavelengthRanges(sedEl["sed-spectrum-ranges"]?.value);
  const photometry = (sedState.payload.photometry || []).map((row, index) => {
    const color = sedColors[index % sedColors.length];
    const x = wavelengthToDisplay(Number(row.average_wavelength_angstrom) * 1e-4);
    const y = displayPhotometryY(row, distance);
    const yerr = displayPhotometryYerr(row, distance);
    return {
      kind: "photometry",
      key: photKey(row, index),
      row,
      index,
      color,
      x,
      lam: Number(row.average_wavelength_angstrom) * 1e-4,
      minLam: finite(row.min_wavelength_angstrom) ? Number(row.min_wavelength_angstrom) * 1e-4 : null,
      maxLam: finite(row.max_wavelength_angstrom) ? Number(row.max_wavelength_angstrom) * 1e-4 : null,
      y,
      yerr,
      visible: Boolean(sedState.visible[photKey(row, index)]),
      plotable: finite(x) && finite(y) && (!sedEl["sed-ylog"].checked || y > 0),
    };
  });
  const spectra = (sedState.payload.spectra || []).map((spectrum, index) => processSpectrumForSed(spectrum, index, photometry, distance, spectrumRanges));
  const template = processTemplateForSed(photometry, spectra, distance);
  return { distance, photometry, spectra, template, empirical: sedState.empirical, spectrumRanges };
}

function processSpectrumForSed(spectrum, index, photometry, distance, spectrumRanges) {
  const key = specKey(spectrum);
  const color = sedColors[(photometry.length + index) % sedColors.length];
  const spaceBased = isSpaceBasedSpectrum(spectrum);
  const anchored = shouldAnchorSpectrumToPhotometry(spectrum, spaceBased);
  const rawRows = (spectrum.rows || []).map((row, rowIndex) => {
    const lam = Number(row.lam);
    const flambda = Number(row.sp) * 10000.0;
    const flambdaErr = finite(row.esp) ? Number(row.esp) * 10000.0 : null;
    return { rowIndex, lam, flambda, flambdaErr, ignored: ignoredFlag(row.ignored) };
  }).filter((row) => finite(row.lam) && finite(row.flambda) && row.lam > 0);
  const telluricRows = filterGroundTelluricRows(rawRows, spaceBased);
  const uncarvedRows = filterCarvedSpectrumRows(telluricRows, key);
  const filteredRows = filterSpectrumRowsByRanges(uncarvedRows, spectrumRanges);
  const anchorFit = anchored ? anchoredSpectrumScaleDetails(filteredRows, photometry) : { scale: 1, matchedCount: 0 };
  const scale = anchorFit.scale;
  const safeScale = finite(scale) && scale > 0 ? scale : 1;
  const points = filteredRows.map((row) => {
    const flambda = row.flambda * safeScale;
    const flambdaErr = finite(row.flambdaErr) ? Math.abs(row.flambdaErr * safeScale) : null;
    const y = displayFromFlambda(row.lam, flambda, distance);
    const yerr = displayErrFromFlambda(row.lam, flambdaErr, distance);
    return {
      ...row,
      x: wavelengthToDisplay(row.lam),
      y,
      yerr,
      flambda,
      flambdaErr,
      lambdaFlux: row.lam * flambda,
    };
  }).filter((point) => finite(point.x) && finite(point.y) && (!sedEl["sed-ylog"].checked || point.y > 0));
  return {
    kind: "spectrum",
    key,
    spectrum,
    index,
    color,
    anchored,
    spaceBased,
    anchorMatchedCount: anchorFit.matchedCount,
    scale: safeScale,
    rawRows,
    telluricRows,
    uncarvedRows,
    filteredRows,
    telluricRowsRemoved: rawRows.length - telluricRows.length,
    carvedRows: telluricRows.length - uncarvedRows.length,
    spectrumRanges,
    points,
    visible: Boolean(sedState.visible[key]),
  };
}

function anchoredSpectrumScale(rawRows, photometry) {
  return anchoredSpectrumScaleDetails(rawRows, photometry).scale;
}

function anchoredSpectrumScaleDetails(rawRows, photometry) {
  const candidates = photometry.filter((point) => point.visible && point.plotable && finite(point.row.lambda_flambda_w_m2));
  const ratios = [];
  for (const point of candidates) {
    const raw = anchorRawLambdaFluxAtPhotometry(rawRows, point);
    if (finite(raw) && raw > 0) ratios.push(Number(point.row.lambda_flambda_w_m2) / raw);
  }
  const scale = robustMedian(ratios.filter((value) => finite(value) && value > 0));
  return { scale: finite(scale) && scale > 0 ? scale : 1, matchedCount: ratios.length };
}

function anchorRawLambdaFluxAtPhotometry(rawRows, point) {
  const positiveRows = rawRows
    .filter((row) => finite(row.lam) && row.lam > 0 && finite(row.flambda) && row.flambda > 0)
    .sort((a, b) => a.lam - b.lam);
  if (!positiveRows.length) return NaN;
  if (finite(point.minLam) && finite(point.maxLam) && point.maxLam > point.minLam) {
    const bandRows = positiveRows.filter((row) => row.lam >= point.minLam && row.lam <= point.maxLam);
    const bandFlux = robustMedian(bandRows.map((row) => row.lam * row.flambda).filter((value) => finite(value) && value > 0));
    if (finite(bandFlux) && bandFlux > 0) return bandFlux;
  }
  const lam = Number(point.lam);
  if (!finite(lam)) return NaN;
  return interpolateLogLog(positiveRows.map((row) => row.lam), positiveRows.map((row) => row.lam * row.flambda), lam);
}

function shouldAnchorSpectrumToPhotometry(spectrum, spaceBased = isSpaceBasedSpectrum(spectrum)) {
  if (sedEl["sed-anchor-ground-only"].checked) return !spaceBased;
  return sedEl["sed-anchor-spectra"].checked;
}

function isSpaceBasedSpectrum(spectrum) {
  const meta = spectrum?.metadata || spectrum?.spectrum?.metadata || {};
  const instText = normalizeSedMetadataText(meta.moca_instid);
  const allText = normalizeSedMetadataText([
    meta.moca_instid,
    meta.instrument_mode_name,
    meta.spectrum_name,
    meta.label,
  ].filter(Boolean).join(" "));
  const instTokens = sedMetadataTokens(instText);
  const allTokens = sedMetadataTokens(allText);
  const observatoryTokens = new Set(["jwst", "hst", "spherex", "spitzer", "wise", "akari", "iras", "iso", "herschel"]);
  const instrumentTokens = new Set(["miri", "nircam", "niriss", "wfc3", "stis", "acs", "cos", "nicmos", "wfpc", "wfpc2", "irac", "mips", "pacs", "spire"]);
  if ([...allTokens].some((token) => observatoryTokens.has(token))) return true;
  if ([...instTokens].some((token) => instrumentTokens.has(token))) return true;
  return false;
}

function normalizeSedMetadataText(value) {
  return String(value || "").trim().toLowerCase();
}

function sedMetadataTokens(text) {
  return new Set(String(text || "").split(/[^a-z0-9]+/i).map((token) => token.trim().toLowerCase()).filter(Boolean));
}

function processTemplateForSed(photometry, spectra, distance) {
  if (!sedState.template || !sedEl["sed-show-template"].checked || !sedState.visible.template) return null;
  const rows = (sedState.template.rows || []).map((row) => ({
    lam: Number(row.lam),
    flambda: Number(row.sp),
    flambdaErr: finite(row.esp) ? Number(row.esp) : null,
  })).filter((row) => finite(row.lam) && row.lam > 0 && finite(row.flambda) && row.flambda > 0);
  const scale = templateScale(rows, photometry, spectra);
  const points = rows.map((row) => {
    const flambda = row.flambda * scale;
    const y = displayFromFlambda(row.lam, flambda, distance);
    return { ...row, flambda, x: wavelengthToDisplay(row.lam), y, lambdaFlux: row.lam * flambda };
  }).filter((point) => finite(point.x) && finite(point.y) && (!sedEl["sed-ylog"].checked || point.y > 0));
  return { key: "template", rows, points, scale };
}

function templateScale(rows, photometry, spectra) {
  const mode = sedEl["sed-template-scale-mode"].value || "photometry";
  const obs = [];
  if (mode === "photometry" || mode === "all") {
    for (const point of photometry) {
      if (point.visible && finite(point.row.lambda_flambda_w_m2)) {
        obs.push({ lam: point.lam, lambdaFlux: Number(point.row.lambda_flambda_w_m2), source: "photometry" });
      }
    }
  }
  if (mode === "spectra" || mode === "all") {
    for (const spectrum of spectra) {
      if (!spectrum.visible) continue;
      const stride = Math.max(1, Math.ceil(spectrum.points.length / 150));
      spectrum.points.forEach((point, index) => {
        if (index % stride === 0 && finite(point.lambdaFlux)) obs.push({ lam: point.lam, lambdaFlux: point.lambdaFlux, source: "spectrum" });
      });
    }
  }
  const templateLambdaFlux = rows.map((row) => row.lam * row.flambda);
  const ratios = [];
  for (const point of obs) {
    const model = interpolateLogLog(rows.map((row) => row.lam), templateLambdaFlux, point.lam);
    if (finite(model) && model > 0 && finite(point.lambdaFlux) && point.lambdaFlux > 0) {
      ratios.push(point.lambdaFlux / model);
    }
  }
  const scale = robustMedian(ratios);
  return finite(scale) && scale > 0 ? scale : 1;
}

function sedTraces(processed) {
  const spectrumTraces = [];
  const templateTraces = [];
  const empiricalSedTraces = [];
  const photometrySpanTraces = [];
  const photometryMarkerTraces = [];
  for (const spectrum of processed.spectra) {
    if (!spectrum.visible || !spectrum.points.length) continue;
    const lineData = lineWithGaps(spectrum.points);
    spectrumTraces.push({
      type: "scattergl",
      mode: "lines+markers",
      x: lineData.x,
      y: lineData.y,
      customdata: lineData.custom.map((item) => item ? spectrumCustomData(spectrum, item) : null),
      line: { color: spectrum.color, width: 1.6 },
      marker: { color: spectrum.color, size: 4, opacity: 0.01 },
      name: spectrum.spectrum.metadata?.label || `specid${spectrum.spectrum.moca_specid}`,
      showlegend: false,
      hovertemplate: sedHoverTemplate("spectrum"),
      hoverinfo: sedEl["sed-hover"].checked ? undefined : "skip",
    });
  }
  if (processed.template && processed.template.points.length) {
    const color = "#222222";
    templateTraces.push({
      type: "scattergl",
      mode: "lines",
      x: processed.template.points.map((point) => point.x),
      y: processed.template.points.map((point) => point.y),
      customdata: processed.template.points.map((point) => templateCustomData(processed.template, point)),
      line: { color, width: 2.2, dash: "dash" },
      opacity: 0.82,
      name: "Scaled template",
      showlegend: false,
      hovertemplate: sedHoverTemplate("template"),
      hoverinfo: sedEl["sed-hover"].checked ? undefined : "skip",
    });
  }
  if (processed.empirical && sedState.visible.empirical) {
    empiricalSedTraces.push(...empiricalTraces(processed.empirical, processed.distance));
  }
  const visiblePhotometry = processed.photometry.filter((point) => point.visible && point.plotable);
  for (const point of visiblePhotometry) {
    if (finite(point.minLam) && finite(point.maxLam)) {
      photometrySpanTraces.push({
        type: "scattergl",
        mode: "lines",
        x: [wavelengthToDisplay(point.minLam), wavelengthToDisplay(point.maxLam)],
        y: [point.y, point.y],
        line: { color: colorWithAlpha(point.color, 0.46), width: 8 },
        hoverinfo: "skip",
        showlegend: false,
      });
    }
  }
  for (const point of visiblePhotometry) {
    const custom = photCustomData(point);
    photometryMarkerTraces.push({
      type: "scattergl",
      mode: "markers",
      x: [point.x],
      y: [point.y],
      customdata: [custom],
      marker: { symbol: "circle", color: point.color, size: 14, line: { color: "#ffffff", width: 2 } },
      error_y: { type: "data", array: [point.yerr || 0], visible: finite(point.yerr), color: point.color, thickness: 1.4, width: 4 },
      name: point.row.moca_psid,
      showlegend: false,
      hovertemplate: sedHoverTemplate("photometry"),
      hoverinfo: sedEl["sed-hover"].checked ? undefined : "skip",
    });
  }
  return [
    ...spectrumTraces,
    ...templateTraces,
    ...empiricalSedTraces,
    ...photometrySpanTraces,
    ...photometryMarkerTraces,
  ];
}

function filterResponseOverlays(processed, layout) {
  if (!sedEl["sed-show-filter-responses"]?.checked) return { traces: [], info: null };
  const yMapper = bandpassYMapper(layout);
  if (!yMapper) return { traces: [], info: null };
  const bandpassRows = new Map();
  (sedState.payload.bandpasses || []).forEach((row) => {
    const key = row.moca_psid;
    if (!key) return;
    if (!bandpassRows.has(key)) bandpassRows.set(key, []);
    bandpassRows.get(key).push(row);
  });
  const traces = [];
  const visiblePhotometry = processed.photometry.filter((point) => point.visible && point.plotable);
  for (const point of visiblePhotometry) {
    traces.push(...filterResponseTracesForPoint(point, bandpassRows.get(point.row.moca_psid) || [], yMapper));
  }
  const count = traces.filter((trace) => trace.meta?.sedFilterResponseLine).length;
  return {
    traces,
    info: count ? { count } : null,
  };
}

function filterResponseTracesForPoint(point, rows, yMapper) {
  if (!rows.length) return [];
  const xlog = sedEl["sed-xlog"].checked;
  const samples = rows.map((row) => ({
    x: wavelengthToDisplay(Number(row.wavelength_angstrom) * 1e-4),
    response: Math.max(0, Number(row.relative_spectral_response) || 0),
  })).filter((sample) => (
    finite(sample.x)
    && finite(sample.response)
    && (!xlog || sample.x > 0)
  )).sort((left, right) => left.x - right.x);
  if (samples.length < 2) return [];
  const minResponse = Math.min(...samples.map((sample) => sample.response));
  const maxResponse = Math.max(...samples.map((sample) => sample.response));
  const responseSpan = maxResponse - minResponse;
  if (!finite(maxResponse) || maxResponse <= 0 || !finite(responseSpan) || responseSpan <= 0) {
    return [];
  }

  const x = [];
  const y = [];
  samples.forEach((sample) => {
    const normalized = (sample.response - minResponse) / responseSpan;
    x.push(sample.x);
    y.push(yMapper.at(normalized));
  });
  const baseline = yMapper.at(0);
  const fillX = [...x, ...x.slice().reverse()];
  const fillY = [...y, ...x.map(() => baseline).reverse()];
  const label = point.row.moca_psid || "selected filter";
  const meta = { sedAutorange: false, sedFilterResponse: true, mocaPsid: label };
  return [
    {
      type: "scatter",
      mode: "lines",
      x: fillX,
      y: fillY,
      fill: "toself",
      fillcolor: colorWithAlpha(point.color, 0.08),
      line: { color: "rgba(0, 0, 0, 0)", width: 0 },
      name: `${label} filter response area`,
      showlegend: false,
      hoverinfo: "skip",
      meta,
    },
    {
      type: "scatter",
      mode: "lines",
      x,
      y,
      line: { color: colorWithAlpha(point.color, 0.82), width: 2 },
      name: `${label} filter response`,
      showlegend: false,
      hoverinfo: "skip",
      meta: { ...meta, sedFilterResponseLine: true },
    },
  ];
}

function bandpassYMapper(layout) {
  const range = normalizeSedAxisRange(layout?.yaxis?.range);
  if (!range) return null;
  const lo = Math.min(range[0], range[1]);
  const hi = Math.max(range[0], range[1]);
  const span = hi - lo;
  if (!finite(span) || span <= 0) return null;
  const innerLo = lo + span * 0.025;
  const innerHi = hi - span * 0.025;
  if (sedEl["sed-ylog"].checked) {
    return {
      at: (fraction) => 10 ** (innerLo + (innerHi - innerLo) * Math.max(0, Math.min(1, Number(fraction)))),
    };
  }
  return {
    at: (fraction) => innerLo + (innerHi - innerLo) * Math.max(0, Math.min(1, Number(fraction))),
  };
}

function empiricalTraces(empirical, distance) {
  const traces = [];
  const toDisplay = (point) => ({
    x: wavelengthToDisplay(point.lam),
    y: displayFromLambdaFlux(point.lam, point.lambdaFlux, distance),
    yerr: displayErrFromLambdaFlux(point.lam, point.sigma, distance),
    point,
  });
  const main = empirical.main.map(toDisplay).filter((point) => finite(point.x) && finite(point.y) && (!sedEl["sed-ylog"].checked || point.y > 0));
  traces.push(...empiricalErrorBandTraces(main));
  traces.push({
    type: "scattergl",
    mode: "lines",
    x: main.map((point) => point.x),
    y: main.map((point) => point.y),
    line: { color: "#101010", width: 3.2 },
    name: "Empirical SED",
    showlegend: false,
    hovertemplate: sedHoverTemplate("empirical"),
    customdata: main.map((display) => empiricalCustomData(display.point, display)),
    hoverinfo: sedEl["sed-hover"].checked ? undefined : "skip",
  });
  for (const [name, points] of [["Short extension", empirical.short || []], ["Long extension", empirical.long || []]]) {
    const display = points.map(toDisplay).filter((point) => finite(point.x) && finite(point.y) && (!sedEl["sed-ylog"].checked || point.y > 0));
    if (!display.length) continue;
    traces.push({
      type: "scattergl",
      mode: "lines",
      x: display.map((point) => point.x),
      y: display.map((point) => point.y),
      line: { color: "#101010", width: 2, dash: "dot" },
      opacity: 0.72,
      name,
      meta: { sedAutorange: false },
      showlegend: false,
      hoverinfo: "skip",
    });
  }
  return traces;
}

function empiricalErrorBandTraces(points) {
  const segments = contiguousDisplaySegments(points.filter((point) => (
    finite(point.yerr) && point.yerr > 0 && finite(point.point?.lam)
  )));
  return segments.map((segment) => {
    const band = segment.map((point) => ({
      x: point.x,
      upper: point.y + point.yerr,
      lower: point.y - point.yerr,
    })).filter((point) => (
      finite(point.x)
      && finite(point.upper)
      && finite(point.lower)
      && (!sedEl["sed-ylog"].checked || point.lower > 0)
    ));
    if (band.length < 2) return null;
    return {
      type: "scatter",
      mode: "lines",
      x: [...band.map((point) => point.x), ...band.map((point) => point.x).reverse()],
      y: [...band.map((point) => point.upper), ...band.map((point) => point.lower).reverse()],
      fill: "toself",
      fillcolor: "rgba(16, 16, 16, 0.20)",
      line: { color: "rgba(16, 16, 16, 0)", width: 0 },
      hoverinfo: "skip",
      showlegend: false,
      name: "Empirical SED uncertainty",
    };
  }).filter(Boolean);
}

function contiguousDisplaySegments(points) {
  if (points.length < 2) return points.length ? [points] : [];
  const gaps = [];
  for (let index = 1; index < points.length; index += 1) {
    const gap = Math.log(points[index].point.lam) - Math.log(points[index - 1].point.lam);
    if (finite(gap) && gap > 0) gaps.push(gap);
  }
  const medianGap = robustMedian(gaps);
  const gapLimit = finite(medianGap) && medianGap > 0 ? 12 * medianGap : Infinity;
  const segments = [];
  let current = [];
  for (const point of points) {
    const previous = current[current.length - 1];
    const gap = previous ? Math.log(point.point.lam) - Math.log(previous.point.lam) : 0;
    if (previous && finite(gap) && gap > gapLimit) {
      if (current.length >= 2) segments.push(current);
      current = [];
    }
    current.push(point);
  }
  if (current.length >= 2) segments.push(current);
  return segments;
}

function sedLayout(processed, traces) {
  const xlog = sedEl["sed-xlog"].checked;
  const ylog = sedEl["sed-ylog"].checked;
  const allX = [];
  const allY = [];
  traces.forEach((trace) => {
    if (trace.meta?.sedAutorange === false) return;
    (trace.x || []).forEach((value) => { if (finite(value) && (!xlog || value > 0)) allX.push(value); });
    (trace.y || []).forEach((value) => { if (finite(value) && (!ylog || value > 0)) allY.push(value); });
  });
  const xaxis = {
    title: { text: xAxisTitle(), font: { size: 22 }, standoff: 18 },
    type: xlog ? "log" : "linear",
    showgrid: true,
    gridcolor: "#e2e2e2",
    zeroline: false,
    automargin: true,
    ...boxAxisStyle(),
  };
  const yaxis = {
    title: { text: yAxisTitle(), font: { size: 22 } },
    type: ylog ? "log" : "linear",
    showgrid: true,
    gridcolor: "#e8e8e8",
    zeroline: false,
    automargin: true,
    ...boxAxisStyle(),
  };
  const xr = numericAxisRange(allX, { log: xlog, fallback: xlog ? [0.4, 30] : [0.4, 5.5], padFraction: 0.06 });
  const yr = numericAxisRange(allY, { log: ylog, fallback: null, padFraction: 0.10 });
  if (xr) xaxis.range = xlog ? xr.map(Math.log10) : xr;
  if (yr) yaxis.range = ylog ? yr.map(Math.log10) : yr;
  return {
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { l: 92, r: 32, t: 18, b: 86 },
    xaxis,
    yaxis,
    hovermode: sedEl["sed-hover"].checked ? "closest" : false,
    dragmode: "pan",
  };
}

function sedAxisResetRangesFromLayout(layout) {
  return {
    x: normalizeSedAxisRange(layout?.xaxis?.range),
    y: normalizeSedAxisRange(layout?.yaxis?.range),
  };
}

function normalizeSedAxisRange(range) {
  if (!Array.isArray(range) || range.length < 2) return null;
  const lo = Number(range[0]);
  const hi = Number(range[1]);
  return finite(lo) && finite(hi) && lo !== hi ? [lo, hi] : null;
}

function sedAxisRangeRelayoutUpdate(ranges) {
  const update = {};
  if (ranges?.x) {
    update["xaxis.autorange"] = false;
    update["xaxis.range[0]"] = ranges.x[0];
    update["xaxis.range[1]"] = ranges.x[1];
  }
  if (ranges?.y) {
    update["yaxis.autorange"] = false;
    update["yaxis.range[0]"] = ranges.y[0];
    update["yaxis.range[1]"] = ranges.y[1];
  }
  return update;
}

function updateSedPlotInitialRanges(plotEl, ranges) {
  setPlotlyAxisInitialRange(plotEl?._fullLayout?.xaxis, ranges?.x);
  setPlotlyAxisInitialRange(plotEl?._fullLayout?.yaxis, ranges?.y);
}

function setPlotlyAxisInitialRange(axis, range) {
  if (!axis || !range) return;
  axis._rangeInitial = range.slice();
  axis._rangeInitial0 = range[0];
  axis._rangeInitial1 = range[1];
  axis._autorangeInitial = false;
}

function bindSedPlotEvents() {
  if (sedEl["sed-plot"].dataset.bound === "1" || typeof sedEl["sed-plot"].on !== "function") return;
  sedEl["sed-plot"].dataset.bound = "1";
  sedEl["sed-plot"].on("plotly_click", (event) => {
    const rows = (event?.points || []).map((point) => point?.customdata).filter(Boolean);
    sedState.selectedRows = rows;
    renderSedTable();
  });
  sedEl["sed-plot"].on("plotly_selected", (event) => {
    const selection = plotSelectionFromEvent(event);
    sedState.selectedSpectrumKeys = selection.spectrumKeys;
    sedState.selectedSpectrumRows = selection.spectrumRows;
    sedState.selectedPhotometryKeys = selection.photometryKeys;
    updateSpectrumSelectionControls();
  });
  sedEl["sed-plot"].on("plotly_deselect", () => {
    clearPlotlySelectionState();
    updateSpectrumSelectionControls();
  });
  sedEl["sed-plot"].on("plotly_relayout", (event) => {
    handleSedPlotRelayout(event);
  });
}

function handleSedPlotRelayout(event) {
  if (sedState.resettingAxes || !event) return;
  const wantsAutorange = event["xaxis.autorange"] === true
    || event["yaxis.autorange"] === true
    || event.autorange === true;
  if (!wantsAutorange) return;
  const schedule = window.requestAnimationFrame || ((fn) => setTimeout(fn, 0));
  schedule(resetSedPlotAxesToStoredRange);
}

function resetSedPlotAxesToStoredRange() {
  const ranges = sedState.plotResetRanges;
  const update = sedAxisRangeRelayoutUpdate(ranges);
  if (!Object.keys(update).length || typeof Plotly === "undefined" || typeof Plotly.relayout !== "function") return;
  sedState.resettingAxes = true;
  Promise.resolve(Plotly.relayout(sedEl["sed-plot"], update)).finally(() => {
    sedState.resettingAxes = false;
    updateSedPlotInitialRanges(sedEl["sed-plot"], ranges);
  });
}

function constructEmpiricalSed() {
  if (!sedState.payload) return;
  const processed = buildSedProcessedData();
  const main = buildEmpiricalSedMain(processed, 2200);
  if (main.length < 2) {
    sedEl["sed-bolometric-summary"].textContent = "Need at least two non-overlapping SED points.";
    return;
  }
  const short = sedEl["sed-extend-short"].checked ? shortExtension(main) : [];
  const long = sedEl["sed-extend-long"].checked ? longExtension(main) : [];
  const dataFbol = integrateLambdaFlux(main);
  const mainUnc = integrationUncertainty(main);
  const shortFlux = integrateLambdaFlux(short);
  const longFlux = integrateLambdaFlux(long);
  const extensionFbol = shortFlux + longFlux;
  const extensionFbolUnc = Math.sqrt((0.20 * shortFlux) ** 2 + (0.20 * longFlux) ** 2);
  const fbol = dataFbol + extensionFbol;
  const fbolUnc = Math.sqrt(mainUnc * mainUnc + extensionFbolUnc * extensionFbolUnc);
  const tailFraction = finite(fbol) && fbol > 0 ? extensionFbol / fbol : null;
  const distance = sedDistance();
  let lbol = null;
  let lbolUnc = null;
  if (distance?.distance_pc && finite(fbol)) {
    const dMeters = Number(distance.distance_pc) * sedParsecMeters;
    lbol = 4 * Math.PI * dMeters * dMeters * fbol;
    const relFlux = finite(fbolUnc) && fbol > 0 ? fbolUnc / fbol : 0;
    const relDist = finite(distance.distance_pc_unc) && Number(distance.distance_pc) > 0 ? Number(distance.distance_pc_unc) / Number(distance.distance_pc) : 0;
    lbolUnc = Math.abs(lbol) * Math.sqrt(relFlux * relFlux + (2 * relDist) ** 2);
  }
  sedState.empirical = { main, short, long, fbol, fbolUnc, dataFbol, dataFbolUnc: mainUnc, extensionFbol, extensionFbolUnc, tailFraction, lbol, lbolUnc };
  sedState.visible.empirical = true;
  renderSed();
}

function clearEmpiricalSed() {
  sedState.empirical = null;
  delete sedState.visible.empirical;
  sedState.selectedRows = sedState.selectedRows.filter((row) => row?.kind !== "empirical");
  if (sedState.payload) renderSed();
  else renderBolometricSummary();
}

function disableSelectedSpectra() {
  const selection = sedState.selectedSpectrumKeys || new Set();
  let disabledCount = 0;
  for (const key of selection) {
    if (!key) continue;
    if (sedState.visible[key] !== false) disabledCount += 1;
    sedState.visible[key] = false;
    sedState.selectionDisabledSpectra.add(key);
  }
  sedState.selectedSpectrumKeys = new Set();
  if (!disabledCount) {
    updateSpectrumSelectionControls();
    return;
  }
  sedState.selectedRows = sedState.selectedRows.filter((row) => row?.kind !== "spectrum" || !selection.has(row.spectrumKey));
  clearPlotlySelectionState();
  renderSed();
}

function carveSelectedSpectrumRows() {
  const selection = sedState.selectedSpectrumRows || {};
  let carvedCount = 0;
  for (const [key, selectedRows] of Object.entries(selection)) {
    if (!selectedRows?.size) continue;
    if (!sedState.carvedSpectrumRows[key]) sedState.carvedSpectrumRows[key] = new Set();
    const carvedRows = sedState.carvedSpectrumRows[key];
    for (const rowIndex of selectedRows) {
      if (carvedRows.has(rowIndex)) continue;
      carvedRows.add(rowIndex);
      carvedCount += 1;
    }
  }
  if (!carvedCount) {
    updateSpectrumSelectionControls();
    return;
  }
  sedState.selectedRows = sedState.selectedRows.filter((row) => !isCarvedSpectrumRow(row));
  clearPlotlySelectionState();
  renderSed();
}

function disableSelectedPhotometry() {
  const selection = sedState.selectedPhotometryKeys || new Set();
  let disabledCount = 0;
  for (const key of selection) {
    if (!key) continue;
    if (sedState.visible[key] !== false) disabledCount += 1;
    sedState.visible[key] = false;
  }
  if (!disabledCount) {
    updateSpectrumSelectionControls();
    return;
  }
  sedState.selectedRows = sedState.selectedRows.filter((row) => row?.kind !== "photometry" || !selection.has(row.key));
  clearPlotlySelectionState();
  renderSed();
}

function restoreSelectionDisabledSpectra() {
  for (const key of sedState.selectionDisabledSpectra || []) {
    sedState.visible[key] = true;
  }
  sedState.selectionDisabledSpectra = new Set();
  clearPlotlySelectionState();
  if (sedState.payload) renderSed();
  else updateSpectrumSelectionControls();
}

function restoreCarvedSpectrumRows() {
  sedState.carvedSpectrumRows = {};
  clearPlotlySelectionState();
  if (sedState.payload) renderSed();
  else updateSpectrumSelectionControls();
}

function plotSelectionFromEvent(event) {
  const spectrumKeys = new Set();
  const spectrumRows = {};
  const photometryKeys = new Set();
  for (const point of event?.points || []) {
    const row = point?.customdata;
    if (row?.kind === "spectrum" && row.spectrumKey) {
      spectrumKeys.add(row.spectrumKey);
      if (Number.isInteger(Number(row.rowIndex))) {
        if (!spectrumRows[row.spectrumKey]) spectrumRows[row.spectrumKey] = new Set();
        spectrumRows[row.spectrumKey].add(Number(row.rowIndex));
      }
    } else if (row?.kind === "photometry" && row.key) {
      photometryKeys.add(row.key);
    }
  }
  return { spectrumKeys, spectrumRows, photometryKeys };
}

function clearPlotlySelectionState() {
  sedState.selectedSpectrumKeys = new Set();
  sedState.selectedSpectrumRows = {};
  sedState.selectedPhotometryKeys = new Set();
}

function selectedSpectrumCount() {
  return sedState.selectedSpectrumKeys?.size || 0;
}

function selectedSpectrumRowCount() {
  return Object.values(sedState.selectedSpectrumRows || {}).reduce((sum, rows) => sum + (rows?.size || 0), 0);
}

function selectedPhotometryCount() {
  return sedState.selectedPhotometryKeys?.size || 0;
}

function selectionDisabledSpectrumCount() {
  return sedState.selectionDisabledSpectra?.size || 0;
}

function carvedSpectrumRowCount() {
  return Object.values(sedState.carvedSpectrumRows || {}).reduce((sum, rows) => sum + (rows?.size || 0), 0);
}

function updateSpectrumSelectionControls() {
  if (!sedEl["sed-remove-selection"] || !sedEl["sed-clear-spectrum-removals"]) return;
  const selectedCount = selectedSpectrumCount();
  const selectedRows = selectedSpectrumRowCount();
  const selectedPhotometry = selectedPhotometryCount();
  const disabledCount = selectionDisabledSpectrumCount();
  const carvedCount = carvedSpectrumRowCount();
  sedEl["sed-remove-selection"].disabled = selectedCount === 0;
  if (sedEl["sed-carve-selection"]) sedEl["sed-carve-selection"].disabled = selectedRows === 0;
  if (sedEl["sed-remove-photometry-selection"]) sedEl["sed-remove-photometry-selection"].disabled = selectedPhotometry === 0;
  sedEl["sed-clear-spectrum-removals"].disabled = disabledCount === 0;
  if (sedEl["sed-clear-spectrum-carves"]) sedEl["sed-clear-spectrum-carves"].disabled = carvedCount === 0;
  sedEl["sed-spectrum-selection-note"].textContent = selectedCount || selectedRows || selectedPhotometry
    ? selectionSummaryText(selectedCount, selectedRows, selectedPhotometry)
    : selectionStateSummaryText(disabledCount, carvedCount);
}

function selectionSummaryText(spectrumCount, spectrumRowCount, photometryCount) {
  return [
    spectrumCount ? `${spectrumCount} ${spectrumCount === 1 ? "spectrum" : "spectra"}` : "",
    spectrumRowCount ? `${spectrumRowCount} spectrum sample${spectrumRowCount === 1 ? "" : "s"}` : "",
    photometryCount ? `${photometryCount} photometric point${photometryCount === 1 ? "" : "s"}` : "",
  ].filter(Boolean).join(", ") + " in current selection.";
}

function selectionStateSummaryText(disabledCount, carvedCount) {
  const pieces = [
    disabledCount ? `${disabledCount} ${disabledCount === 1 ? "spectrum" : "spectra"} disabled by selection` : "",
    carvedCount ? `${carvedCount} spectrum sample${carvedCount === 1 ? "" : "s"} carved out` : "",
  ].filter(Boolean);
  return pieces.length ? `${pieces.join(", ")}.` : "Use Plotly lasso or box select to select spectra or photometry.";
}

function observedSedPoints(processed) {
  const points = [];
  for (const point of processed.photometry) {
    if (!point.visible || !finite(point.row.lambda_flambda_w_m2) || !finite(point.lam)) continue;
    points.push({
      lam: point.lam,
      lambdaFlux: Number(point.row.lambda_flambda_w_m2),
      sigma: finite(point.row.lambda_flambda_w_m2_unc) ? Number(point.row.lambda_flambda_w_m2_unc) : Math.abs(Number(point.row.lambda_flambda_w_m2)) * 0.05,
      source: "photometry",
      sourceKey: point.key,
      sourceLabel: point.row.moca_psid,
    });
  }
  for (const spectrum of processed.spectra) {
    if (!spectrum.visible) continue;
    const meta = spectrum.spectrum.metadata || {};
    const stride = Math.max(1, Math.ceil(spectrum.points.length / 1200));
    spectrum.points.forEach((point, index) => {
      if (index % stride !== 0 || !finite(point.lambdaFlux) || point.lambdaFlux <= 0) return;
      points.push({
        lam: point.lam,
        lambdaFlux: point.lambdaFlux,
        sigma: finite(point.flambdaErr) ? Math.abs(point.lam * point.flambdaErr) : Math.abs(point.lambdaFlux) * 0.05,
        source: "spectrum",
        sourceKey: spectrum.key,
        sourceLabel: meta.label || `specid ${spectrum.spectrum.moca_specid}`,
      });
    });
  }
  return points.filter((point) => finite(point.lam) && point.lam > 0 && finite(point.lambdaFlux) && point.lambdaFlux > 0).sort((a, b) => a.lam - b.lam);
}

function buildEmpiricalSedMain(processed, maxPoints) {
  const visiblePhotometry = processed.photometry
    .filter((point) => point.visible && finite(point.row.lambda_flambda_w_m2) && finite(point.lam) && point.lam > 0)
    .map((point) => ({
      lam: point.lam,
      lambdaFlux: Number(point.row.lambda_flambda_w_m2),
      sigma: finite(point.row.lambda_flambda_w_m2_unc) ? Number(point.row.lambda_flambda_w_m2_unc) : Math.abs(Number(point.row.lambda_flambda_w_m2)) * 0.05,
      source: "photometry",
      sourceKey: point.key,
      sourceLabel: point.row.moca_psid,
    }))
    .filter((point) => finite(point.lambdaFlux) && point.lambdaFlux > 0);
  const visibleSpectra = processed.spectra.filter((spectrum) => spectrum.visible && spectrum.points.length >= 2);
  const bounds = [
    ...visiblePhotometry.map((point) => point.lam),
    ...visibleSpectra.flatMap((spectrum) => spectrumWavelengthBounds(spectrum.points)),
  ].filter((value) => finite(value) && value > 0);
  if (bounds.length < 2) return mergeSedPoints(visiblePhotometry, maxPoints);
  const minLam = Math.min(...bounds);
  const maxLam = Math.max(...bounds);
  if (!finite(minLam) || !finite(maxLam) || maxLam <= minLam) return mergeSedPoints(visiblePhotometry, maxPoints);

  const logMin = Math.log(minLam);
  const logMax = Math.log(maxLam);
  const logSpan = logMax - logMin;
  const gridCount = Math.max(2, Math.min(maxPoints, Math.ceil(logSpan * 700)));
  const grid = linspace(logMin, logMax, gridCount).map((value) => Math.exp(value));
  const bins = grid.map(() => []);

  for (const spectrum of visibleSpectra) {
    addSpectrumGridContributions(bins, grid, spectrum);
  }
  for (const point of visiblePhotometry) {
    const index = nearestLogGridIndex(grid, point.lam);
    if (index !== null) bins[index].push(point);
  }

  return bins
    .map((items, index) => items.length ? combineSedBin(items.map((item) => ({ ...item, lam: grid[index] }))) : null)
    .filter((point) => point && finite(point.lam) && finite(point.lambdaFlux) && point.lambdaFlux > 0)
    .sort((a, b) => a.lam - b.lam);
}

function spectrumWavelengthBounds(points) {
  const values = points.map((point) => point.lam).filter((value) => finite(value) && value > 0);
  if (!values.length) return [];
  return [Math.min(...values), Math.max(...values)];
}

function addSpectrumGridContributions(bins, grid, spectrum) {
  const points = spectrum.points
    .filter((point) => finite(point.lam) && point.lam > 0 && finite(point.lambdaFlux) && point.lambdaFlux > 0)
    .sort((a, b) => a.lam - b.lam);
  if (points.length < 2) return;
  const meta = spectrum.spectrum.metadata || {};
  const gapLimit = spectrumLogGapLimit(points);
  let rightIndex = 1;
  for (let gridIndex = 0; gridIndex < grid.length; gridIndex += 1) {
    const lam = grid[gridIndex];
    if (lam < points[0].lam || lam > points[points.length - 1].lam) continue;
    while (rightIndex < points.length - 1 && points[rightIndex].lam < lam) rightIndex += 1;
    const left = points[rightIndex - 1];
    const right = points[rightIndex];
    const contribution = interpolateSpectrumGridContribution(left, right, lam, gapLimit);
    if (!contribution) continue;
    bins[gridIndex].push({
      ...contribution,
      source: "spectrum",
      sourceKey: spectrum.key,
      sourceLabel: meta.label || `specid ${spectrum.spectrum.moca_specid}`,
    });
  }
}

function interpolateSpectrumGridContribution(left, right, lam, gapLimit) {
  if (!left || !right || !finite(left.lam) || !finite(right.lam) || !(right.lam > left.lam)) return null;
  const logGap = Math.log(right.lam) - Math.log(left.lam);
  if (!finite(logGap) || logGap <= 0 || logGap > gapLimit) return null;
  if (!finite(left.lambdaFlux) || !finite(right.lambdaFlux) || left.lambdaFlux <= 0 || right.lambdaFlux <= 0) return null;
  const t = (Math.log(lam) - Math.log(left.lam)) / logGap;
  if (!finite(t) || t < -1e-9 || t > 1 + 1e-9) return null;
  const lambdaFlux = Math.exp(Math.log(left.lambdaFlux) + t * (Math.log(right.lambdaFlux) - Math.log(left.lambdaFlux)));
  const leftSigma = finite(left.flambdaErr) && left.flambdaErr > 0 ? Math.abs(left.lam * left.flambdaErr) : Math.abs(left.lambdaFlux) * 0.05;
  const rightSigma = finite(right.flambdaErr) && right.flambdaErr > 0 ? Math.abs(right.lam * right.flambdaErr) : Math.abs(right.lambdaFlux) * 0.05;
  const sigma = leftSigma > 0 && rightSigma > 0
    ? Math.exp(Math.log(leftSigma) + t * (Math.log(rightSigma) - Math.log(leftSigma)))
    : Math.abs(lambdaFlux) * 0.05;
  return { lam, lambdaFlux, sigma };
}

function spectrumLogGapLimit(points) {
  const gaps = [];
  for (let index = 1; index < points.length; index += 1) {
    const gap = Math.log(points[index].lam) - Math.log(points[index - 1].lam);
    if (finite(gap) && gap > 0) gaps.push(gap);
  }
  const medianGap = robustMedian(gaps);
  return finite(medianGap) && medianGap > 0 ? 12 * medianGap : Infinity;
}

function nearestLogGridIndex(grid, lam) {
  if (!grid.length || !finite(lam) || lam <= 0) return null;
  if (lam <= grid[0]) return 0;
  if (lam >= grid[grid.length - 1]) return grid.length - 1;
  let lo = 0;
  let hi = grid.length - 1;
  const logLam = Math.log(lam);
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (Math.log(grid[mid]) < logLam) lo = mid;
    else hi = mid;
  }
  return Math.abs(Math.log(grid[lo]) - logLam) <= Math.abs(Math.log(grid[hi]) - logLam) ? lo : hi;
}

function mergeSedPoints(points, maxPoints) {
  const sorted = points.slice().sort((a, b) => a.lam - b.lam);
  if (!sorted.length) return [];
  const minLog = Math.log(sorted[0].lam);
  const maxLog = Math.log(sorted[sorted.length - 1].lam);
  if (!finite(minLog) || !finite(maxLog) || maxLog <= minLog) return [combineSedBin(sorted)].filter(Boolean);
  const logSpan = maxLog - minLog;
  const binCount = Math.max(2, Math.min(maxPoints, Math.ceil(logSpan * 280)));
  const width = logSpan / binCount;
  const bins = new Map();
  sorted.forEach((point) => {
    const key = Math.max(0, Math.min(binCount - 1, Math.floor((Math.log(point.lam) - minLog) / width)));
    if (!bins.has(key)) bins.set(key, []);
    bins.get(key).push(point);
  });
  return [...bins.values()]
    .map((items) => combineSedBin(items))
    .filter((point) => point && finite(point.lam) && finite(point.lambdaFlux))
    .sort((a, b) => a.lam - b.lam);
}

function combineSedBin(items) {
  const sourceGroups = new Map();
  for (const item of items) {
    const key = item.sourceKey || item.source || "unknown";
    if (!sourceGroups.has(key)) sourceGroups.set(key, []);
    sourceGroups.get(key).push(item);
  }
  const sources = [...sourceGroups.entries()].map(([key, sourceItems]) => combineSedSourceItems(key, sourceItems)).filter(Boolean);
  if (!sources.length) return null;
  const cappedSources = cappedWeightItems(sources, sedEmpiricalWeightCapFactor);
  const weightSum = cappedSources.reduce((sum, item) => sum + item.weight, 0);
  if (!finite(weightSum) || weightSum <= 0) return null;
  const lam = Math.exp(cappedSources.reduce((sum, item) => sum + item.weight * Math.log(item.lam), 0) / weightSum);
  const lambdaFlux = cappedSources.reduce((sum, item) => sum + item.weight * item.lambdaFlux, 0) / weightSum;
  const measurementSigma = Math.sqrt(1 / weightSum);
  const scatterSigma = sources.length > 1
    ? Math.sqrt(cappedSources.reduce((sum, item) => sum + item.weight * (item.lambdaFlux - lambdaFlux) ** 2, 0) / weightSum)
    : 0;
  const sigma = Math.sqrt(measurementSigma * measurementSigma + scatterSigma * scatterSigma);
  return {
    lam,
    lambdaFlux,
    sigma,
    measurementSigma,
    scatterSigma,
    source: "merged",
    sourceCount: sources.length,
    pointCount: items.length,
  };
}

function combineSedSourceItems(key, items) {
  const weightedItems = cappedWeightItems(items.map((item) => ({
    ...item,
    weight: sedPointWeight(item),
  })).filter((item) => finite(item.weight) && item.weight > 0), sedEmpiricalWeightCapFactor);
  const weightSum = weightedItems.reduce((sum, item) => sum + item.weight, 0);
  if (!finite(weightSum) || weightSum <= 0) return null;
  const lam = Math.exp(weightedItems.reduce((sum, item) => sum + item.weight * Math.log(item.lam), 0) / weightSum);
  const lambdaFlux = weightedItems.reduce((sum, item) => sum + item.weight * item.lambdaFlux, 0) / weightSum;
  return {
    key,
    lam,
    lambdaFlux,
    sigma: Math.sqrt(1 / weightSum),
    weight: weightSum,
    sourceLabel: weightedItems[0]?.sourceLabel || key,
  };
}

function cappedWeightItems(items, capFactor) {
  const weights = items.map((item) => Number(item.weight)).filter((value) => finite(value) && value > 0);
  const medianWeight = robustMedian(weights);
  const cap = finite(medianWeight) && medianWeight > 0 ? medianWeight * capFactor : Infinity;
  return items.map((item) => ({
    ...item,
    weight: Math.min(Number(item.weight), cap),
  })).filter((item) => finite(item.weight) && item.weight > 0);
}

function sedPointWeight(point) {
  const fallbackSigma = Math.abs(Number(point.lambdaFlux)) * 0.05;
  const sigma = finite(point.sigma) && Number(point.sigma) > 0 ? Math.abs(Number(point.sigma)) : fallbackSigma;
  if (!finite(sigma) || sigma <= 0) return 0;
  return 1 / (sigma * sigma);
}

function shortExtension(main) {
  const first = main[0];
  const minLam = Math.max(0.01, first.lam / 35);
  const logs = linspace(Math.log(minLam), Math.log(first.lam), 80).slice(0, -1);
  return logs.map((value) => {
    const lam = Math.exp(value);
    const lambdaFlux = first.lambdaFlux * Math.exp(-3.0 * (first.lam / lam - 1.0));
    return { lam, lambdaFlux, sigma: Math.abs(lambdaFlux) * 0.2, source: "short-extension" };
  });
}

function longExtension(main) {
  const last = main[main.length - 1];
  const maxLam = Math.min(1000, last.lam * 80);
  const logs = linspace(Math.log(last.lam), Math.log(maxLam), 120).slice(1);
  return logs.map((value) => {
    const lam = Math.exp(value);
    const lambdaFlux = last.lambdaFlux * (lam / last.lam) ** -3;
    return { lam, lambdaFlux, sigma: Math.abs(lambdaFlux) * 0.2, source: "long-extension" };
  });
}

function integrateLambdaFlux(points) {
  const sorted = points.filter((point) => finite(point.lam) && point.lam > 0 && finite(point.lambdaFlux)).sort((a, b) => a.lam - b.lam);
  let sum = 0;
  for (let i = 1; i < sorted.length; i += 1) {
    const dx = Math.log(sorted[i].lam) - Math.log(sorted[i - 1].lam);
    if (finite(dx) && dx > 0) sum += 0.5 * (sorted[i].lambdaFlux + sorted[i - 1].lambdaFlux) * dx;
  }
  return sum;
}

function integrationUncertainty(points) {
  const sorted = points.filter((point) => finite(point.lam) && point.lam > 0 && finite(point.sigma)).sort((a, b) => a.lam - b.lam);
  if (sorted.length < 2) return 0;
  let variance = 0;
  for (let i = 0; i < sorted.length; i += 1) {
    const left = i > 0 ? Math.log(sorted[i].lam) - Math.log(sorted[i - 1].lam) : 0;
    const right = i < sorted.length - 1 ? Math.log(sorted[i + 1].lam) - Math.log(sorted[i].lam) : 0;
    const weight = 0.5 * Math.max(0, left + right);
    variance += (weight * sorted[i].sigma) ** 2;
  }
  return Math.sqrt(variance);
}

function renderSedSummary(processed) {
  const payload = sedState.payload;
  const cacheText = payload.cache?.hit ? " from cache" : "";
  const photText = `${payload.meta?.plotted_photometry_count || 0}/${payload.meta?.photometry_count || 0} photometric points convertible`;
  const specText = `${payload.meta?.spectra_count || 0} spectra`;
  const rangeText = processed.spectrumRanges?.length ? `, spectrum ranges ${formatSedWavelengthRanges(processed.spectrumRanges)}` : "";
  const distText = processed.distance?.distance_pc ? `distance ${formatNumber(processed.distance.distance_pc, 4)} pc` : "no non-photometric distance";
  setSedStatus(`SED loaded${cacheText}`, "");
  sedEl["sed-summary"].textContent = `${targetName()} · ${photText}, ${specText}${rangeText}, ${distText}`;
  sedEl["sed-hint"].textContent = sedState.filterResponseDisplay
    ? `Filter responses displayed for ${sedState.filterResponseDisplay.count} photometric filter${sedState.filterResponseDisplay.count === 1 ? "" : "s"}.`
    : "Photometric filter responses hidden.";
  const missing = (payload.photometry || []).filter((row) => row.conversion_status !== "ok").length;
  sedEl["sed-flux-note"].textContent = missing
    ? `${missing} photometric rows lack wavelength or zeropoint metadata for physical-flux plotting.`
    : "All returned photometric rows are physically convertible.";
}

function renderLayerTokens(processed) {
  const tokens = [];
  for (const point of processed.photometry) {
    const unavailable = point.row.conversion_status !== "ok";
    tokens.push(layerTokenHtml({
      key: point.key,
      color: point.color,
      title: `${point.row.moca_psid} ${formatMaybeMag(point.row.magnitude)}`,
      meta: unavailable ? point.row.conversion_status : `${formatNumber(point.lam, 4)} um · photometry`,
      type: "photometry",
      active: point.visible,
      unavailable,
    }));
  }
  for (const spectrum of processed.spectra) {
    const baseRowCount = spectrum.telluricRows?.length ?? spectrum.rawRows.length;
    const rowText = processed.spectrumRanges?.length ? `${spectrum.points.length}/${baseRowCount} rows in range` : `${spectrum.points.length} rows`;
    const telluricText = spectrum.telluricRowsRemoved ? ` · ${spectrum.telluricRowsRemoved} telluric cut` : "";
    const carvedText = spectrum.carvedRows ? ` · ${spectrum.carvedRows} carved` : "";
    const anchorText = spectrum.anchored
      ? (spectrum.anchorMatchedCount ? `anchored ${spectrum.anchorMatchedCount} phot` : "anchor failed")
      : spectrum.spaceBased && sedEl["sed-anchor-ground-only"].checked
        ? "space/native"
        : "native";
    tokens.push(layerTokenHtml({
      key: spectrum.key,
      color: spectrum.color,
      title: spectrum.spectrum.metadata?.label || `specid ${spectrum.spectrum.moca_specid}`,
      meta: `scale ${formatScientific(spectrum.scale)} · ${anchorText} · ${rowText}${telluricText}${carvedText}`,
      type: "spectrum",
      active: spectrum.visible,
      unavailable: spectrum.rawRows.length === 0,
    }));
  }
  if (sedState.template) {
    tokens.push(layerTokenHtml({
      key: "template",
      color: "#222222",
      title: sedState.template.metadata?.label || "Template",
      meta: processed.template ? `scale ${formatScientific(processed.template.scale)}` : "hidden",
      type: "template",
      active: Boolean(sedState.visible.template && sedEl["sed-show-template"].checked),
      unavailable: false,
    }));
  }
  if (sedState.empirical) {
    tokens.push(layerTokenHtml({
      key: "empirical",
      color: "#101010",
      title: "Empirical SED",
      meta: `Fbol ${formatScientific(sedState.empirical.fbol)} W/m2`,
      type: "empirical",
      active: Boolean(sedState.visible.empirical),
      unavailable: false,
    }));
  }
  sedEl["sed-layer-tokens"].innerHTML = tokens.join("") || `<div class="plot-hint">No layers loaded</div>`;
  sedEl["sed-layer-tokens"].querySelectorAll("button[data-layer-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.layerKey;
      if (!key || button.disabled) return;
      const nextVisible = !sedState.visible[key];
      sedState.visible[key] = nextVisible;
      if (nextVisible) sedState.selectionDisabledSpectra.delete(key);
      renderSed();
    });
  });
}

function layerTokenHtml({ key, color, title, meta, type, active, unavailable }) {
  const classes = ["sed-layer-token", active ? "is-active" : "is-muted", unavailable ? "is-unavailable" : "", `is-${type}`].filter(Boolean).join(" ");
  return `
    <button type="button" class="${classes}" data-layer-key="${escapeHtml(key)}" ${unavailable ? "disabled" : ""}>
      <span class="sed-layer-symbol" style="--swatch-color: ${escapeHtml(color)}"></span>
      <span class="sed-layer-body">
        <span class="sed-layer-title">${escapeHtml(title)}</span>
        <span class="sed-layer-meta">${escapeHtml(meta || "")}</span>
      </span>
    </button>
  `;
}

function renderSedTargetToken() {
  const target = sedState.payload?.target || { moca_oid: sedState.oid, designation: `oid${sedState.oid}` };
  sedEl["sed-target-token"].innerHTML = `
    <div class="spectra-token sed-target-chip">
      <span class="spectra-token-swatch" style="--swatch-color: #377EB8"></span>
      <span class="spectra-token-body">
        <span class="spectra-token-title">${escapeHtml(target.designation || `oid${sedState.oid}`)}</span>
        <span class="spectra-token-meta">oid ${escapeHtml(target.moca_oid || sedState.oid)}${target.spectral_type ? ` · SpT ${escapeHtml(target.spectral_type)}` : ""}</span>
      </span>
    </div>
  `;
}

function renderSedTemplateToken() {
  if (!sedState.template) {
    sedEl["sed-template-token"].innerHTML = `<div class="plot-hint">No template loaded</div>`;
    return;
  }
  const meta = sedState.template.metadata || {};
  sedEl["sed-template-token"].innerHTML = `
    <div class="spectra-token sed-template-chip">
      <span class="spectra-token-swatch" style="--swatch-color: #222222"></span>
      <span class="spectra-token-body">
        <span class="spectra-token-title">${escapeHtml(meta.label || "Template")}</span>
        <span class="spectra-token-meta">${escapeHtml([meta.grid_type, `${sedState.template.rows?.length || 0} rows`].filter(Boolean).join(" · "))}</span>
      </span>
    </div>
  `;
}

function renderBolometricSummary() {
  const empirical = sedState.empirical;
  if (!empirical) {
    sedEl["sed-bolometric-summary"].textContent = "No empirical SED constructed";
    return;
  }
  const rows = [];
  if (finite(empirical.lbol)) {
    rows.push(bolometricSummaryRow("log10(Lbol/Lsun)", logLuminositySummary(empirical.lbol, empirical.lbolUnc)));
  }
  rows.push(bolometricSummaryRow("Fbol(total)", formatScaledMeasurement(empirical.fbol, empirical.fbolUnc, "W/m2")));
  if (finite(empirical.dataFbol)) {
    rows.push(bolometricSummaryRow("Fbol(data)", formatScaledMeasurement(empirical.dataFbol, empirical.dataFbolUnc, "W/m2")));
  }
  if (finite(empirical.extensionFbol)) {
    rows.push(bolometricSummaryRow("Fbol(tails)", formatScaledMeasurement(empirical.extensionFbol, empirical.extensionFbolUnc, "W/m2")));
    rows.push(bolometricSummaryRow("Tail Lbol fraction", formatFractionPercent(empirical.tailFraction)));
  }
  if (finite(empirical.lbol)) {
    rows.push(bolometricSummaryRow("Lbol(total)", formatScaledMeasurement(empirical.lbol, empirical.lbolUnc, "W")));
  }
  sedEl["sed-bolometric-summary"].innerHTML = rows.join("");
}

function bolometricSummaryRow(label, value) {
  return `
    <div class="sed-bolometric-row">
      <span class="sed-bolometric-label">${escapeHtml(label)}</span>
      <span class="sed-bolometric-value">${value}</span>
    </div>
  `;
}

function logLuminositySummary(lbol, lbolUnc) {
  if (!finite(lbol) || lbol <= 0) return "log10(Lbol/Lsun) unavailable";
  const ratio = lbol / sedLsunWatts;
  const logRatio = Math.log10(ratio);
  const logUnc = finite(lbolUnc) && lbolUnc > 0 ? lbolUnc / (Math.abs(lbol) * Math.log(10)) : null;
  return formatMeasurementPair(logRatio, logUnc);
}

function formatFractionPercent(fraction) {
  if (!finite(fraction)) return "unavailable";
  return `${formatNumber(100 * Number(fraction), 3)}% of total Lbol`;
}

function renderSedTable() {
  if (!sedState.selectedRows.length) {
    const missing = (sedState.payload?.photometry || []).filter((row) => row.conversion_status !== "ok");
    if (missing.length) {
      sedEl["sed-table-title"].textContent = "Photometry metadata gaps";
      sedEl["sed-table-subtitle"].textContent = "Rows listed here were returned but cannot be plotted on physical-flux axes.";
      const rows = missing.slice(0, 80).map((row) => ({
        psid: row.moca_psid,
        mag: formatMaybeMag(row.magnitude),
        status: row.conversion_status,
        system: row.system_type || "",
        average_wavelength: row.average_wavelength_angstrom || "",
        ref: row.photometry_ref || "",
      }));
      sedEl["sed-table"].innerHTML = renderTable(rows, ["psid", "mag", "status", "system", "average_wavelength", "ref"]);
      return;
    }
    sedEl["sed-table-title"].textContent = "Selected data";
    sedEl["sed-table-subtitle"].textContent = sedState.filterResponseDisplay
      ? "Filter responses displayed."
      : "Hover or click plot elements for metadata.";
    sedEl["sed-table"].textContent = "No data selected.";
    return;
  }
  sedEl["sed-table-title"].textContent = `${sedState.selectedRows.length} selected item${sedState.selectedRows.length === 1 ? "" : "s"}`;
  sedEl["sed-table-subtitle"].textContent = sedState.filterResponseDisplay
    ? "Filter responses displayed. Values reflect current display units."
    : "Values reflect current display units.";
  const rows = sedState.selectedRows.map((row) => ({
    kind: row.kind,
    label: row.label,
    wavelength: formatNumber(row.lam, 6),
    value: formatScientific(row.y),
    error: finite(row.yerr) ? formatScientific(row.yerr) : "",
    unit: row.unit,
    ref: row.ref || "",
    status: row.status || "",
  }));
  sedEl["sed-table"].innerHTML = renderTable(rows, ["kind", "label", "wavelength", "value", "error", "unit", "ref", "status"]);
}

function photCustomData(point) {
  const magUnc = photometryMagnitudeUncertainty(point.row);
  return {
    kind: "photometry",
    key: point.key,
    label: point.row.moca_psid,
    lam: point.lam,
    x: point.x,
    y: point.y,
    yerr: point.yerr,
    unit: yUnitText(),
    magnitude: point.row.magnitude,
    magnitude_unc: magUnc,
    magnitudeLine: formatPhotometryMagnitudeLine(point.row),
    psid: point.row.moca_psid,
    ref: point.row.photometry_ref,
    status: point.row.conversion_status,
    bandpass: point.row.bandpass_count,
  };
}

function spectrumCustomData(spectrum, point) {
  const meta = spectrum.spectrum.metadata || {};
  return {
    kind: "spectrum",
    spectrumKey: spectrum.key,
    rowIndex: point.rowIndex,
    label: meta.label || `specid ${spectrum.spectrum.moca_specid}`,
    lam: point.lam,
    y: point.y,
    unit: yUnitText(),
    specid: spectrum.spectrum.moca_specid,
    scale: spectrum.scale,
    ref: meta.spectrum_ref,
    status: meta.flux_units || "",
  };
}

function templateCustomData(template, point) {
  const meta = sedState.template?.metadata || {};
  return {
    kind: "template",
    label: meta.label || "Template",
    lam: point.lam,
    y: point.y,
    unit: yUnitText(),
    scale: template.scale,
    ref: meta.origin || "",
    status: "scaled template",
  };
}

function empiricalCustomData(point, display) {
  return {
    kind: "empirical",
    label: "Empirical SED",
    lam: point.lam,
    y: display.y,
    yerr: display.yerr,
    lambdaFlux: point.lambdaFlux,
    sigma: point.sigma,
    measurementSigma: point.measurementSigma,
    scatterSigma: point.scatterSigma,
    sourceCount: point.sourceCount,
    pointCount: point.pointCount,
    unit: yUnitText(),
  };
}

function sedHoverTemplate(kind) {
  if (!sedEl["sed-hover"].checked) return undefined;
  if (kind === "photometry") {
    return [
      "<b>%{customdata.label}</b>",
      "λ = %{customdata.lam:.6g} μm",
      "value = %{customdata.y:.4e} %{customdata.unit}",
      "%{customdata.magnitudeLine}",
      "bandpass rows = %{customdata.bandpass}",
      "ref = %{customdata.ref}",
      "<extra></extra>",
    ].join("<br>");
  }
  if (kind === "spectrum") {
    return [
      "<b>%{customdata.label}</b>",
      "λ = %{customdata.lam:.6g} μm",
      "value = %{customdata.y:.4e} %{customdata.unit}",
      "scale = %{customdata.scale:.4e}",
      "ref = %{customdata.ref}",
      "<extra></extra>",
    ].join("<br>");
  }
  if (kind === "template") {
    return [
      "<b>%{customdata.label}</b>",
      "λ = %{customdata.lam:.6g} μm",
      "value = %{customdata.y:.4e} %{customdata.unit}",
      "scale = %{customdata.scale:.4e}",
      "<extra></extra>",
    ].join("<br>");
  }
  return [
    "<b>%{customdata.label}</b>",
    "λ = %{customdata.lam:.6g} μm",
    "value = %{y:.4e} %{customdata.unit}",
    "error = %{customdata.yerr:.3e} %{customdata.unit}",
    "sources = %{customdata.sourceCount}",
    "<extra></extra>",
  ].join("<br>");
}

function displayPhotometryY(row, distance) {
  const lam = Number(row.average_wavelength_angstrom) * 1e-4;
  if (sedEl["sed-yunit"].value === "lambda_flambda") return Number(row.lambda_flambda_w_m2);
  if (sedEl["sed-yunit"].value === "flambda") return Number(row.flambda_w_m2_um);
  if (sedEl["sed-yunit"].value === "fnu") return Number(row.fnu_jy);
  const factor = luminosityFactor(distance);
  if (!finite(factor)) return NaN;
  if (sedEl["sed-yunit"].value === "lambda_llambda") return Number(row.lambda_flambda_w_m2) * factor;
  if (sedEl["sed-yunit"].value === "lambda_llambda_lsun") return Number(row.lambda_flambda_w_m2) * factor / sedLsunWatts;
  return displayFromLambdaFlux(lam, Number(row.lambda_flambda_w_m2), distance);
}

function displayPhotometryYerr(row, distance) {
  if (!finite(row.lambda_flambda_w_m2_unc) && !finite(row.flambda_w_m2_um_unc) && !finite(row.fnu_jy_unc)) return null;
  if (sedEl["sed-yunit"].value === "lambda_flambda") return Number(row.lambda_flambda_w_m2_unc);
  if (sedEl["sed-yunit"].value === "flambda") return Number(row.flambda_w_m2_um_unc);
  if (sedEl["sed-yunit"].value === "fnu") return Number(row.fnu_jy_unc);
  const factor = luminosityFactor(distance);
  if (!finite(factor)) return null;
  if (sedEl["sed-yunit"].value === "lambda_llambda") return Number(row.lambda_flambda_w_m2_unc) * factor;
  if (sedEl["sed-yunit"].value === "lambda_llambda_lsun") return Number(row.lambda_flambda_w_m2_unc) * factor / sedLsunWatts;
  return null;
}

function displayFromFlambda(lamUm, flambdaWm2Um, distance) {
  const lambdaFlux = lamUm * flambdaWm2Um;
  return displayFromLambdaFlux(lamUm, lambdaFlux, distance);
}

function displayErrFromFlambda(lamUm, flambdaErr, distance) {
  if (!finite(flambdaErr)) return null;
  return Math.abs(displayFromLambdaFlux(lamUm, lamUm * flambdaErr, distance));
}

function displayErrFromLambdaFlux(lamUm, lambdaFluxErr, distance) {
  if (!finite(lambdaFluxErr)) return null;
  return Math.abs(displayFromLambdaFlux(lamUm, Math.abs(Number(lambdaFluxErr)), distance));
}

function displayFromLambdaFlux(lamUm, lambdaFlux, distance) {
  if (!finite(lamUm) || !finite(lambdaFlux)) return NaN;
  const yunit = sedEl["sed-yunit"].value;
  if (yunit === "lambda_flambda") return lambdaFlux;
  if (yunit === "flambda") return lambdaFlux / lamUm;
  if (yunit === "fnu") return (lambdaFlux / lamUm) * lamUm * lamUm * 1e20 / sedSpeedOfLight;
  const factor = luminosityFactor(distance);
  if (!finite(factor)) return NaN;
  if (yunit === "lambda_llambda") return lambdaFlux * factor;
  if (yunit === "lambda_llambda_lsun") return lambdaFlux * factor / sedLsunWatts;
  return lambdaFlux;
}

function luminosityFactor(distance) {
  if (!distance?.distance_pc || !finite(distance.distance_pc)) return NaN;
  const d = Number(distance.distance_pc) * sedParsecMeters;
  return 4 * Math.PI * d * d;
}

function sedDistance() {
  return (sedState.payload?.distances || [])[0] || null;
}

function photKey(row, index) {
  return `phot:${row.photometry_id ?? `${row.moca_psid}:${index}`}`;
}

function specKey(spectrum) {
  return `spec:${spectrum.moca_specid}`;
}

function targetName() {
  const target = sedState.payload?.target || {};
  return target.designation || `oid${target.moca_oid || sedState.oid}`;
}

function xAxisTitle() {
  const unit = sedEl["sed-xunit"].value;
  if (unit === "nm") return "Wavelength (nm)";
  if (unit === "angstrom") return "Wavelength (Angstrom)";
  return "Wavelength (μm)";
}

function yAxisTitle() {
  const unit = sedEl["sed-yunit"].value;
  if (unit === "flambda") return "Fλ (W/m²/μm)";
  if (unit === "fnu") return "Fν (Jy)";
  if (unit === "lambda_llambda") return "λLλ (W)";
  if (unit === "lambda_llambda_lsun") return "λLλ (Lsun)";
  return "λFλ (W/m²)";
}

function yUnitText() {
  const unit = sedEl["sed-yunit"].value;
  if (unit === "flambda") return "W/m2/um";
  if (unit === "fnu") return "Jy";
  if (unit === "lambda_llambda") return "W";
  if (unit === "lambda_llambda_lsun") return "Lsun";
  return "W/m2";
}

function wavelengthToDisplay(lamUm) {
  if (!finite(lamUm)) return NaN;
  const unit = sedEl["sed-xunit"].value;
  if (unit === "nm") return lamUm * 1000;
  if (unit === "angstrom") return lamUm * 10000;
  return lamUm;
}

function parseSedWavelengthRanges(raw) {
  const text = String(raw || "").trim();
  if (!text) return [];
  const ranges = [];
  const numberPattern = /[-+]?\d*\.?\d+(?:e[-+]?\d+)?/ig;
  const pairPattern = /([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(?:-|:|,|\s+)\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)/ig;
  let match;
  while ((match = pairPattern.exec(text)) !== null) {
    const left = parseSedWavelengthMicron(match[1]);
    const right = parseSedWavelengthMicron(match[2]);
    if (!finite(left) || !finite(right)) continue;
    ranges.push(left <= right ? [left, right] : [right, left]);
  }
  if (ranges.length) return ranges;
  while ((match = numberPattern.exec(text)) !== null) {
    const value = parseSedWavelengthMicron(match[0]);
    if (finite(value)) ranges.push([value, value]);
  }
  return ranges;
}

function parseSedWavelengthMicron(value) {
  const number = Number(value);
  if (!finite(number) || number <= 0) return NaN;
  return Math.abs(number) > 1000 ? number / 10000 : number;
}

function filterSpectrumRowsByRanges(rows, ranges) {
  if (!ranges?.length) return rows;
  return rows.filter((row) => wavelengthInSedRanges(row.lam, ranges));
}

function filterGroundTelluricRows(rows, spaceBased) {
  if (!sedEl["sed-exclude-ground-telluric"]?.checked || spaceBased) return rows;
  return rows.filter((row) => !wavelengthInSedRanges(row.lam, sedGroundTelluricRanges));
}

function filterCarvedSpectrumRows(rows, spectrumKey) {
  const carvedRows = sedState.carvedSpectrumRows?.[spectrumKey];
  if (!carvedRows?.size) return rows;
  return rows.filter((row) => !carvedRows.has(row.rowIndex));
}

function isCarvedSpectrumRow(row) {
  if (row?.kind !== "spectrum" || !row.spectrumKey || !Number.isInteger(Number(row.rowIndex))) return false;
  return Boolean(sedState.carvedSpectrumRows?.[row.spectrumKey]?.has(Number(row.rowIndex)));
}

function wavelengthInSedRanges(lam, ranges) {
  return finite(lam) && ranges.some(([lo, hi]) => Number(lam) >= lo && Number(lam) <= hi);
}

function formatSedWavelengthRanges(ranges) {
  return ranges.map(([lo, hi]) => (
    lo === hi ? `${formatNumber(lo, 5)} um` : `${formatNumber(lo, 5)}-${formatNumber(hi, 5)} um`
  )).join(", ");
}

function lineWithGaps(points) {
  if (points.length < 2) {
    return { x: points.map((point) => point.x), y: points.map((point) => point.y), custom: points };
  }
  const diffs = [];
  for (let index = 1; index < points.length; index += 1) {
    const diff = points[index].lam - points[index - 1].lam;
    if (diff > 0 && finite(diff)) diffs.push(diff);
  }
  const medianDiff = robustMedian(diffs);
  const gapLimit = finite(medianDiff) && medianDiff > 0 ? 12 * medianDiff : Infinity;
  const x = [];
  const y = [];
  const custom = [];
  points.forEach((point, index) => {
    if (index > 0 && point.lam - points[index - 1].lam > gapLimit) {
      x.push(null);
      y.push(null);
      custom.push(null);
    }
    x.push(point.x);
    y.push(point.y);
    custom.push(point);
  });
  return { x, y, custom };
}

function interpolateLogLog(x, y, target) {
  const pairs = x.map((value, index) => ({ x: Number(value), y: Number(y[index]) }))
    .filter((point) => finite(point.x) && point.x > 0 && finite(point.y) && point.y > 0)
    .sort((a, b) => a.x - b.x);
  if (pairs.length < 2 || target < pairs[0].x || target > pairs[pairs.length - 1].x) return NaN;
  for (let index = 1; index < pairs.length; index += 1) {
    const left = pairs[index - 1];
    const right = pairs[index];
    if (target < left.x || target > right.x) continue;
    const t = (Math.log(target) - Math.log(left.x)) / (Math.log(right.x) - Math.log(left.x));
    return Math.exp(Math.log(left.y) + t * (Math.log(right.y) - Math.log(left.y)));
  }
  return NaN;
}

function numericAxisRange(values, options = {}) {
  const log = Boolean(options.log);
  const finiteValues = values.filter((value) => finite(value) && (!log || value > 0));
  if (!finiteValues.length) return options.fallback || null;
  let lo = Math.min(...finiteValues);
  let hi = Math.max(...finiteValues);
  if (!finite(lo) || !finite(hi)) return options.fallback || null;
  if (lo === hi) {
    lo *= log ? 0.8 : 0.95;
    hi *= log ? 1.25 : 1.05;
  }
  const pad = options.padFraction ?? 0.08;
  if (log && lo > 0 && hi > 0) {
    const logLo = Math.log10(lo);
    const logHi = Math.log10(hi);
    const span = Math.max(0.1, logHi - logLo);
    return [10 ** (logLo - span * pad), 10 ** (logHi + span * pad)];
  }
  const span = hi - lo || Math.abs(hi) || 1;
  return [lo - span * pad, hi + span * pad];
}

function boxAxisStyle() {
  return {
    showline: true,
    mirror: true,
    linewidth: 1,
    linecolor: "#6c6870",
    ticks: "outside",
    ticklen: 5,
    tickcolor: "#6c6870",
  };
}

async function clearSedCache() {
  setSedStatus("Clearing cache", "loading");
  const payload = await postJson("api/sed/cache/clear", {});
  if (!payload.ok) {
    setSedStatus(payload.error || "Cache clear failed", "error");
    return;
  }
  await loadSedObject();
}

function updateSedUrl() {
  const params = new URLSearchParams(window.location.search);
  params.set("moca_oid", String(sedState.oid));
  params.set("xunit", sedEl["sed-xunit"].value);
  params.set("yunit", sedEl["sed-yunit"].value);
  setBoolParam(params, "xlog", sedEl["sed-xlog"].checked, true);
  setBoolParam(params, "ylog", sedEl["sed-ylog"].checked, true);
  setBoolParam(params, "hover", sedEl["sed-hover"].checked, true);
  setBoolParam(params, "hide_ignored", sedEl["sed-hide-ignored"].checked, true);
  setBoolParam(params, "filter_responses", sedEl["sed-show-filter-responses"].checked, false);
  setBoolParam(params, "anchor_spectra", sedEl["sed-anchor-spectra"].checked, true);
  setBoolParam(params, "anchor_ground_only", sedEl["sed-anchor-ground-only"].checked, true);
  setBoolParam(params, "exclude_ground_telluric", sedEl["sed-exclude-ground-telluric"].checked, true);
  copySedInputToParam(params, "spectrum_ranges", "sed-spectrum-ranges");
  params.delete("spectrum_wavelength");
  params.delete("spectral_ranges");
  setBoolParam(params, "show_template", sedEl["sed-show-template"].checked, true);
  params.set("template_scale", sedEl["sed-template-scale-mode"].value);
  setBoolParam(params, "extend_short", sedEl["sed-extend-short"].checked, true);
  setBoolParam(params, "extend_long", sedEl["sed-extend-long"].checked, true);
  if (sedState.template?.moca_spherex_template_id) params.set("template_id", String(sedState.template.moca_spherex_template_id));
  else params.delete("template_id");
  const query = params.toString();
  window.history.replaceState({}, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}

function copySedInputToParam(params, key, id) {
  const value = String(sedEl[id]?.value || "").trim();
  if (value) params.set(key, value);
  else params.delete(key);
}

function apiParams() {
  const current = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "port", "user", "username", "pwd", "password", "dbase", "db", "database", "mock"]) {
    const value = current.get(key);
    if (value) params.set(key, value);
  }
  return params;
}

function setSedStatus(text, mode = "") {
  sedEl["sed-status"].textContent = text;
  sedEl["sed-status"].className = `status${mode ? ` ${mode}` : ""}`;
}

function setSedLoading(loading) {
  sedEl["sed-plot-loader"].classList.toggle("is-visible", Boolean(loading));
}

async function fetchJsonUrl(url) {
  const response = await fetch(url, { credentials: "same-origin" });
  return response.json();
}

async function postJson(path, body) {
  const response = await fetch(sedAppUrl(path), {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return response.json();
}

function plotConfig(filename) {
  return {
    responsive: true,
    displaylogo: false,
    toImageButtonOptions: {
      format: "png",
      filename,
      height: 900,
      width: 1400,
      scale: 2,
    },
  };
}

function renderTable(rows, columns) {
  if (!rows.length) return "No rows.";
  return `
    <table>
      <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column] ?? "")}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
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
  return `rgba(55, 126, 184, ${clampedAlpha})`;
}

function finite(value) {
  return Number.isFinite(Number(value));
}

function ignoredFlag(value) {
  return Number(value || 0) !== 0;
}

function robustMedian(values) {
  const clean = values.map(Number).filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (!clean.length) return NaN;
  const mid = Math.floor(clean.length / 2);
  return clean.length % 2 ? clean[mid] : 0.5 * (clean[mid - 1] + clean[mid]);
}

function linspace(start, stop, n) {
  if (n <= 1) return [start];
  const out = [];
  const step = (stop - start) / (n - 1);
  for (let index = 0; index < n; index += 1) out.push(start + step * index);
  return out;
}

function parseInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const text = String(value).trim();
  if (!/^-?\d+$/.test(text)) return null;
  const out = Number.parseInt(text, 10);
  return Number.isFinite(out) ? out : null;
}

function asBool(value) {
  return String(value || "").trim().toLowerCase() in {"1": 1, "true": 1, "yes": 1, "on": 1};
}

function asFalse(value) {
  if (value === null || value === undefined || value === "") return false;
  return String(value).trim().toLowerCase() in {"0": 1, "false": 1, "no": 1, "off": 1};
}

function setBoolParam(params, key, value, defaultValue = false) {
  if (Boolean(value) === Boolean(defaultValue)) params.delete(key);
  else params.set(key, value ? "1" : "0");
}

function formatNumber(value, digits = 4) {
  if (!finite(value)) return "";
  return Number(value).toLocaleString(undefined, { maximumSignificantDigits: digits });
}

function formatScientific(value) {
  if (!finite(value)) return "";
  return Number(value).toExponential(3);
}

function formatScaledMeasurement(value, uncertainty, unit = "") {
  if (!finite(value)) return "";
  const numberValue = Number(value);
  const numberUnc = finite(uncertainty) ? Math.abs(Number(uncertainty)) : null;
  const basis = Math.abs(numberValue) > 0 ? Math.abs(numberValue) : numberUnc;
  const exponent = finite(basis) && basis > 0 ? Math.floor(Math.log10(basis)) : 0;
  const factor = 10 ** exponent;
  const hasUncertainty = finite(numberUnc) && numberUnc > 0;
  const pair = formatMeasurementPair(numberValue / factor, hasUncertainty ? numberUnc / factor : null);
  const core = hasUncertainty ? `(${pair})` : pair;
  const scale = exponent === 0 ? "" : ` &times; 10<sup>${exponent}</sup>`;
  const suffix = unit ? ` ${escapeHtml(unit)}` : "";
  return `${core}${scale}${suffix}`;
}

function formatMeasurementPair(value, uncertainty, sigDigits = 2) {
  if (!finite(value)) return "";
  if (!finite(uncertainty) || uncertainty <= 0) return formatNumber(value, 4);
  const absUnc = Math.abs(Number(uncertainty));
  const order = Math.floor(Math.log10(absUnc));
  const decimals = Math.min(12, Math.max(0, sigDigits - 1 - order));
  return `${formatFixed(value, decimals)} ± ${formatFixed(absUnc, decimals)}`;
}

function formatFixed(value, decimals) {
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatMaybeMag(value) {
  return finite(value) ? `${formatNumber(value, 5)} mag` : "";
}

function formatPhotometryMagnitudeLine(row) {
  if (!finite(row?.magnitude)) return "mag =";
  const magnitude = formatNumber(row.magnitude, 6);
  if (finite(row.magnitude_unc) && Math.abs(Number(row.magnitude_unc)) > 0) {
    return `mag = ${magnitude} ± ${formatNumber(Math.abs(Number(row.magnitude_unc)), 3)}`;
  }
  const pos = finite(row.magnitude_unc_pos) ? Math.abs(Number(row.magnitude_unc_pos)) : null;
  const neg = finite(row.magnitude_unc_neg) ? Math.abs(Number(row.magnitude_unc_neg)) : null;
  if (finite(pos) && finite(neg) && pos > 0 && neg > 0) {
    if (Math.abs(pos - neg) <= 1e-12) return `mag = ${magnitude} ± ${formatNumber(pos, 3)}`;
    return `mag = ${magnitude} +${formatNumber(pos, 3)}/-${formatNumber(neg, 3)}`;
  }
  if (finite(pos) && pos > 0) return `mag = ${magnitude} +${formatNumber(pos, 3)}`;
  if (finite(neg) && neg > 0) return `mag = ${magnitude} -${formatNumber(neg, 3)}`;
  return `mag = ${magnitude}`;
}

function photometryMagnitudeUncertainty(row) {
  if (finite(row?.magnitude_unc) && Math.abs(Number(row.magnitude_unc)) > 0) return Math.abs(Number(row.magnitude_unc));
  const values = [row?.magnitude_unc_pos, row?.magnitude_unc_neg]
    .filter((value) => finite(value) && Math.abs(Number(value)) > 0)
    .map((value) => Math.abs(Number(value)));
  return values.length ? Math.max(...values) : null;
}

function escapeHtml(value) {
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
