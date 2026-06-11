const sieDefaultSpecid = 758;
const siePublicDefaultSpecid = 758;
const sieDefaultDefinitionUid = "legacy:spectra_index.pro:allers_2013:ki_2";
const sieSpectrumColor = "#293241";
const sieContinuumColor = "#B23A48";

const sieRoleStyles = {
  numerator: { label: "Numerator", stroke: "#2F6FA8", fill: "rgba(47, 111, 168, 0.16)" },
  denominator: { label: "Denominator", stroke: "#2E7D59", fill: "rgba(46, 125, 89, 0.16)" },
  feature: { label: "Feature", stroke: "#B23A48", fill: "rgba(178, 58, 72, 0.17)" },
  blue_continuum: { label: "Blue continuum", stroke: "#B0832F", fill: "rgba(176, 131, 47, 0.15)" },
  red_continuum: { label: "Red continuum", stroke: "#7B5EA7", fill: "rgba(123, 94, 167, 0.14)" },
  continuum: { label: "Continuum", stroke: "#A56A43", fill: "rgba(165, 106, 67, 0.14)" },
};

const sieState = {
  specid: sieDefaultSpecid,
  spectrumMetadata: null,
  definitionUid: sieDefaultDefinitionUid,
  definitionMetadata: null,
  definitionOptions: [],
  definitionFilter: "",
  payload: null,
  processed: null,
  calculation: null,
  spectrumSearchTimer: null,
  loadToken: 0,
};

const sieEl = {};

document.addEventListener("DOMContentLoaded", initSpectralIndexExplorer);

const sieAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function sieAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), sieAppBaseUrl).toString();
}

async function initSpectralIndexExplorer() {
  collectSpectralIndexElements();
  readSpectralIndexUrlState();
  bindSpectralIndexControls();
  renderSpectrumToken();
  renderDefinitionToken();
  await loadSpectralIndexLabels();
  await loadSpectralIndexExplorer();
}

function collectSpectralIndexElements() {
  [
    "sie-status",
    "sie-spectrum-search",
    "sie-spectrum-results",
    "sie-spectrum-selected",
    "sie-load",
    "sie-open-spectrum",
    "sie-definition-filter",
    "sie-definition-select",
    "sie-definition-selected",
    "sie-normalize",
    "sie-show-continuum",
    "sie-show-labels",
    "sie-show-points",
    "sie-hide-ignored",
    "sie-plot",
    "sie-plot-loader",
    "sie-summary",
    "sie-hint",
    "sie-clear-cache",
    "sie-calculation-table",
    "sie-band-table",
  ].forEach((id) => {
    sieEl[id] = document.getElementById(id);
  });
}

function readSpectralIndexUrlState() {
  const params = new URLSearchParams(window.location.search);
  sieState.specid = parseInteger(params.get("moca_specid") || params.get("specid")) || defaultSpectralIndexSpecid();
  sieState.definitionUid = params.get("definition_uid") || params.get("observable_uid") || params.get("uid") || sieDefaultDefinitionUid;
  sieEl["sie-normalize"].checked = !asFalse(params.get("normalize"));
  sieEl["sie-show-continuum"].checked = !asFalse(params.get("continuum"));
  sieEl["sie-show-labels"].checked = !asFalse(params.get("labels"));
  sieEl["sie-show-points"].checked = !asFalse(params.get("points"));
  sieEl["sie-hide-ignored"].checked = params.has("include_ignored") || params.has("show_ignored")
    ? false
    : !asFalse(params.get("hide_ignored"));
}

function defaultSpectralIndexSpecid() {
  const params = new URLSearchParams(window.location.search);
  const dbName = (params.get("dbase") || params.get("db") || params.get("database") || "").replace(/`/g, "").trim().toLowerCase();
  const username = (params.get("user") || params.get("username") || "").trim().toLowerCase();
  return dbName === "mocadb" || username === "public" ? siePublicDefaultSpecid : sieDefaultSpecid;
}

function bindSpectralIndexControls() {
  sieEl["sie-spectrum-search"].addEventListener("input", () => {
    const value = sieEl["sie-spectrum-search"].value.trim();
    clearTimeout(sieState.spectrumSearchTimer);
    sieState.spectrumSearchTimer = setTimeout(() => searchSpectra(value), 250);
  });
  sieEl["sie-spectrum-search"].addEventListener("focus", () => {
    const value = sieEl["sie-spectrum-search"].value.trim();
    if (value) searchSpectra(value);
  });
  sieEl["sie-definition-select"].addEventListener("change", async () => {
    const selected = sieEl["sie-definition-select"].value;
    if (!selected) return;
    sieState.definitionUid = selected;
    sieState.definitionMetadata = definitionMetadataFromOption(sieState.definitionOptions.find((option) => option.value === selected) || { value: selected });
    renderDefinitionToken();
    await loadSpectralIndexExplorer();
  });
  sieEl["sie-definition-filter"].addEventListener("input", () => {
    sieState.definitionFilter = sieEl["sie-definition-filter"].value.trim();
    renderDefinitionSelect({ preserveCurrent: true });
  });
  sieEl["sie-definition-filter"].addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") return;
    const firstOption = firstFilteredDefinitionOption();
    if (!firstOption) return;
    event.preventDefault();
    sieState.definitionUid = firstOption.value;
    sieState.definitionMetadata = definitionMetadataFromOption(firstOption);
    renderDefinitionSelect();
    renderDefinitionToken();
    await loadSpectralIndexExplorer();
  });
  document.addEventListener("click", (event) => {
    if (!sieEl["sie-spectrum-results"].contains(event.target) && event.target !== sieEl["sie-spectrum-search"]) {
      sieEl["sie-spectrum-results"].hidden = true;
    }
  });
  sieEl["sie-load"].addEventListener("click", loadSpectralIndexExplorer);
  sieEl["sie-open-spectrum"].addEventListener("click", openCurrentSpectrumExplorer);
  sieEl["sie-hide-ignored"].addEventListener("change", loadSpectralIndexExplorer);
  for (const id of ["sie-normalize", "sie-show-continuum", "sie-show-labels", "sie-show-points"]) {
    sieEl[id].addEventListener("change", () => {
      renderSpectralIndexExplorer();
      updateSpectralIndexUrl();
    });
  }
  sieEl["sie-clear-cache"].addEventListener("click", clearSpectralIndexCache);
  window.addEventListener("resize", debounce(() => {
    if (!sieEl["sie-spectrum-results"].hidden) positionSearchPopup(sieEl["sie-spectrum-search"], sieEl["sie-spectrum-results"]);
    if (sieState.payload) renderSpectralIndexExplorer();
  }, 150));
}

async function loadSpectralIndexLabels() {
  await Promise.all([loadSelectedSpectrumLabel(), loadDefinitionOptions()]);
}

async function loadSelectedSpectrumLabel() {
  const params = apiParams();
  params.set("specids", String(sieState.specid));
  const payload = await fetchJsonUrl(sieAppUrl(`api/spectra/search?${params.toString()}`));
  if (!payload.ok) return;
  const option = (payload.options || []).find((item) => Number(item.value) === Number(sieState.specid));
  if (option) {
    sieState.spectrumMetadata = spectrumMetadataFromOption(option);
    renderSpectrumToken();
  }
}

async function loadDefinitionOptions() {
  const params = apiParams();
  const payload = await fetchJsonUrl(sieAppUrl(`api/spectral-index-explorer/definitions/search?${params.toString()}`));
  if (!payload.ok) {
    sieEl["sie-definition-select"].innerHTML = `<option value="">${escapeHtml(payload.error || "Could not load definitions")}</option>`;
    return;
  }
  let options = payload.options || [];
  let option = options.find((item) => item.value === sieState.definitionUid);
  if (!option && sieState.definitionUid) {
    const selectedParams = apiParams();
    selectedParams.set("definition_uid", sieState.definitionUid);
    const selectedPayload = await fetchJsonUrl(sieAppUrl(`api/spectral-index-explorer/definitions/search?${selectedParams.toString()}`));
    if (selectedPayload.ok && (selectedPayload.options || []).length) {
      option = selectedPayload.options[0];
      options = [option, ...options.filter((item) => item.value !== option.value)];
    }
  }
  sieState.definitionOptions = options.map(definitionMetadataFromOption);
  if (option) {
    sieState.definitionMetadata = definitionMetadataFromOption(option);
  }
  renderDefinitionSelect();
  renderDefinitionToken();
}

function renderDefinitionSelect({ preserveCurrent = false } = {}) {
  const allOptions = sieState.definitionOptions || [];
  const options = filteredDefinitionOptions();
  if (!options.length) {
    const message = allOptions.length ? "No matching definitions" : "No definitions available";
    sieEl["sie-definition-select"].innerHTML = `<option value="">${message}</option>`;
    return;
  }
  sieEl["sie-definition-select"].innerHTML = options.map((option) => (
    `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label || option.definition_uid || option.value)}</option>`
  )).join("");
  const hasSelected = options.some((option) => option.value === sieState.definitionUid);
  if (preserveCurrent && !hasSelected) {
    const text = `${options.length.toLocaleString()} matching ${options.length === 1 ? "definition" : "definitions"}`;
    sieEl["sie-definition-select"].insertAdjacentHTML("afterbegin", `<option value="">${escapeHtml(text)}</option>`);
    sieEl["sie-definition-select"].value = "";
    return;
  }
  const fallbackOption = options.find((option) => option.value === sieDefaultDefinitionUid) || allOptions.find((option) => option.value === sieDefaultDefinitionUid) || options[0];
  sieEl["sie-definition-select"].value = hasSelected ? sieState.definitionUid : fallbackOption.value;
  if (!hasSelected) {
    sieState.definitionUid = fallbackOption.value;
    sieState.definitionMetadata = definitionMetadataFromOption(fallbackOption);
  }
}

function filteredDefinitionOptions() {
  const options = sieState.definitionOptions || [];
  const rawFilter = sieEl["sie-definition-filter"]?.value || sieState.definitionFilter || "";
  const tokens = String(rawFilter)
    .toLowerCase()
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean);
  if (!tokens.length) return options;
  return options.filter((option) => {
    const haystack = definitionFilterText(option);
    return tokens.every((token) => haystack.includes(token));
  });
}

function firstFilteredDefinitionOption() {
  return filteredDefinitionOptions()[0] || null;
}

function definitionFilterText(option) {
  return [
    option.label,
    option.value,
    option.definition_uid,
    option.display_name,
    option.legacy_observable_name,
    option.moca_siid,
    option.moca_spid,
    option.moca_pid,
    option.source_label,
    option.source_key,
    option.observable_type,
    option.calculation_family,
    option.base_description,
  ].filter(Boolean).join(" ").toLowerCase();
}

async function searchSpectra(query) {
  if (!query) {
    sieEl["sie-spectrum-results"].hidden = true;
    return;
  }
  if (query.length < 2 && !/^\d+$/.test(query)) {
    sieEl["sie-spectrum-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    showSearchPopup(sieEl["sie-spectrum-search"], sieEl["sie-spectrum-results"]);
    return;
  }
  const params = apiParams();
  params.set("q", query);
  const payload = await fetchJsonUrl(sieAppUrl(`api/spectra/search?${params.toString()}`));
  if (!payload.ok) {
    sieEl["sie-spectrum-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
    showSearchPopup(sieEl["sie-spectrum-search"], sieEl["sie-spectrum-results"]);
    return;
  }
  renderSpectrumSearchResults(payload.options || []);
}

function renderSpectrumSearchResults(results) {
  if (!results.length) {
    sieEl["sie-spectrum-results"].innerHTML = `<div class="designation-result-note">No spectra found</div>`;
    showSearchPopup(sieEl["sie-spectrum-search"], sieEl["sie-spectrum-results"]);
    return;
  }
  sieEl["sie-spectrum-results"].innerHTML = results.map((result, index) => (
    `<button class="designation-result spt-spectrum-result" type="button" data-index="${index}"><span>${escapeHtml(result.label || `specid${result.value}`)}</span></button>`
  )).join("");
  sieEl["sie-spectrum-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      const result = results[Number(button.dataset.index)];
      sieState.specid = Number(result.value);
      sieState.spectrumMetadata = spectrumMetadataFromOption(result);
      sieEl["sie-spectrum-search"].value = "";
      sieEl["sie-spectrum-results"].hidden = true;
      renderSpectrumToken();
      await loadSpectralIndexExplorer();
    });
  });
  showSearchPopup(sieEl["sie-spectrum-search"], sieEl["sie-spectrum-results"]);
}

function showSearchPopup(input, popup) {
  positionSearchPopup(input, popup);
  popup.hidden = false;
}

function positionSearchPopup(input, popup) {
  if (!input || !popup) return;
  const rect = input.getBoundingClientRect();
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - 380));
  const available = Math.max(320, window.innerWidth - left - 16);
  const width = Math.min(900, available);
  popup.style.position = "fixed";
  popup.style.left = `${left}px`;
  popup.style.top = `${rect.bottom + 4}px`;
  popup.style.width = `${Math.max(rect.width, width)}px`;
}

function renderSpectrumToken() {
  const metadata = currentSpectrumMetadata();
  const specid = Number(sieState.specid);
  const title = spectrumName(metadata, specid);
  const detail = [
    normalizedMocaOid(metadata.moca_oid) ? `oid ${normalizedMocaOid(metadata.moca_oid)}` : "",
    metadata.spectral_type ? `SpT ${metadata.spectral_type}` : "",
    instrumentLabel(metadata),
    metadata.data_collection_date || "",
  ].filter(Boolean).join(" - ");
  sieEl["sie-spectrum-selected"].innerHTML = `
    <div class="spectra-token" title="${escapeHtml(metadata.label || title)}">
      <span class="spectra-token-swatch" style="--swatch-color: ${sieSpectrumColor}"></span>
      <span class="spectra-token-body">
        <span class="spectra-token-title">${escapeHtml(title)}</span>
        <span class="spectra-token-meta">specid ${escapeHtml(specid)}</span>
        ${detail ? `<span class="spectra-token-meta">${escapeHtml(detail)}</span>` : ""}
      </span>
    </div>
  `;
}

function renderDefinitionToken() {
  const definition = currentDefinitionMetadata();
  const uid = definition.definition_uid || sieState.definitionUid;
  const baseId = definition.moca_siid || definition.moca_spid || "";
  const title = definition.display_name || definition.legacy_observable_name || baseId || uid;
  const detail = [
    definition.source_label || definition.source_key || "",
    definition.observable_type ? String(definition.observable_type).replace(/_/g, " ") : "",
    baseId,
    wavelengthRangeText(definition.min_wavelength, definition.max_wavelength),
  ].filter(Boolean).join(" - ");
  sieEl["sie-definition-selected"].innerHTML = `
    <div class="spectra-token" title="${escapeHtml(uid)}">
      <span class="spectra-token-swatch" style="--swatch-color: ${roleStyleForName(definition.observable_type).stroke}"></span>
      <span class="spectra-token-body">
        <span class="spectra-token-title">${escapeHtml(title)}</span>
        ${detail ? `<span class="spectra-token-meta">${escapeHtml(detail)}</span>` : ""}
        <span class="spectra-token-meta spectra-token-spectrum-name">${escapeHtml(uid)}</span>
      </span>
    </div>
  `;
}

async function loadSpectralIndexExplorer() {
  updateSpectralIndexUrl();
  const token = ++sieState.loadToken;
  setSpectralIndexLoading(true);
  setSpectralIndexStatus("Loading definition", "loading");
  const params = apiParams();
  params.set("moca_specid", String(sieState.specid));
  params.set("definition_uid", sieState.definitionUid);
  params.set("hide_ignored", sieEl["sie-hide-ignored"].checked ? "1" : "0");
  const requestedBins = new URLSearchParams(window.location.search).get("bins")
    ?? new URLSearchParams(window.location.search).get("bins_per_micron")
    ?? new URLSearchParams(window.location.search).get("sie_bins");
  if (requestedBins !== null && requestedBins !== "") params.set("bins", requestedBins);
  const payload = await fetchJsonUrl(sieAppUrl(`api/spectral-index-explorer/load?${params.toString()}`));
  if (token !== sieState.loadToken) return;
  if (!payload.ok) {
    sieState.payload = null;
    sieState.processed = null;
    sieState.calculation = null;
    setSpectralIndexStatus(payload.error || "Could not load definition", "error");
    renderEmptySpectralIndex(payload.error || "Could not load definition");
    setSpectralIndexLoading(false);
    return;
  }
  sieState.payload = payload;
  if (payload.spectrum?.metadata) sieState.spectrumMetadata = spectrumMetadataFromOption(payload.spectrum.metadata);
  if (payload.definition) sieState.definitionMetadata = definitionMetadataFromOption(payload.definition);
  sieState.definitionUid = payload.definition?.definition_uid || sieState.definitionUid;
  renderSpectrumToken();
  renderDefinitionToken();
  renderSpectralIndexExplorer();
  updateSpectralIndexUrl();
}

function renderSpectralIndexExplorer() {
  if (!sieState.payload?.definition || !sieState.payload?.spectrum) {
    renderEmptySpectralIndex("No definition loaded");
    return;
  }
  setSpectralIndexLoading(true);
  const processed = processSpectralIndexPayload(sieState.payload);
  const calculation = calculateObservable(processed.points, processed.definition);
  sieState.processed = processed;
  sieState.calculation = calculation;
  const traces = spectralIndexTraces(processed, calculation);
  const layout = spectralIndexLayout(processed, calculation);
  Plotly.react(sieEl["sie-plot"], traces, layout, plotConfig("mocadb_spectral_index_explorer"));
  renderCalculationTable(calculation, processed);
  renderBandTable(processed.definition.bands || [], calculation);
  const valueText = calculation.valueText || "not calculable";
  const rowsText = pluralize(processed.points.length, "spectral row", "spectral rows");
  const cacheText = sieState.payload.cache?.hit ? " from cache" : "";
  setSpectralIndexStatus(`${valueText}${cacheText}`, calculation.value === null ? "error" : "");
  sieEl["sie-summary"].textContent = `${definitionDisplayName(processed.definition)} on specid ${processed.specid}: ${valueText}`;
  sieEl["sie-hint"].textContent = `${rowsText} in the plotted wavelength window`;
  setSpectralIndexLoading(false);
}

function processSpectralIndexPayload(payload) {
  const spectrum = payload.spectrum || {};
  const definition = normalizeDefinition(payload.definition || {});
  const rows = (spectrum.rows || []).map((row, rowIndex) => {
    const lam = finite(row.lam) ? Number(row.lam) : (finite(row.wavelength_angstrom) ? Number(row.wavelength_angstrom) * 1e-4 : NaN);
    const wavelengthAngstrom = finite(row.wavelength_angstrom) ? Number(row.wavelength_angstrom) : lam * 10000.0;
    const flux = Number(row.sp);
    const err = finite(row.esp) ? Number(row.esp) : null;
    return {
      rowIndex,
      lam,
      wavelengthAngstrom,
      flux,
      err,
      ignored: ignoredFlag(row.ignored),
    };
  }).filter((row) => finite(row.lam) && finite(row.wavelengthAngstrom) && finite(row.flux));
  const visibleRows = sieEl["sie-hide-ignored"].checked ? rows.filter((row) => !row.ignored) : rows;
  const inBandRows = visibleRows.filter((row) => rowInDefinitionWindow(row, definition));
  const scaleSource = inBandRows.length ? inBandRows : visibleRows;
  const scale = sieEl["sie-normalize"].checked ? robustMedian(scaleSource.map((row) => row.flux).filter((value) => finite(value) && value !== 0)) : 1;
  const safeScale = finite(scale) && scale !== 0 ? scale : 1;
  const points = visibleRows.map((row) => ({
    ...row,
    y: row.flux / safeScale,
    yerr: finite(row.err) ? Math.abs(row.err / safeScale) : null,
  })).filter((row) => finite(row.y));
  return {
    specid: Number(spectrum.moca_specid || sieState.specid),
    metadata: spectrum.metadata || {},
    definition,
    rawRows: rows,
    points,
    scale: safeScale,
  };
}

function normalizeDefinition(definition) {
  const bands = (definition.bands || []).map((band) => ({
    ...band,
    band_order: Number(band.band_order),
    band_role: String(band.band_role || "").toLowerCase(),
    wavelength_start: Number(band.wavelength_start),
    wavelength_end: Number(band.wavelength_end),
  })).filter((band) => finite(band.wavelength_start) && finite(band.wavelength_end))
    .map((band) => band.wavelength_start <= band.wavelength_end
      ? band
      : { ...band, wavelength_start: band.wavelength_end, wavelength_end: band.wavelength_start })
    .sort((a, b) => Number(a.band_order || 0) - Number(b.band_order || 0));
  return { ...definition, bands };
}

function rowInDefinitionWindow(row, definition) {
  const minW = finite(definition.min_wavelength) ? Number(definition.min_wavelength) : Math.min(...(definition.bands || []).map((band) => band.wavelength_start));
  const maxW = finite(definition.max_wavelength) ? Number(definition.max_wavelength) : Math.max(...(definition.bands || []).map((band) => band.wavelength_end));
  return row.wavelengthAngstrom >= minW && row.wavelengthAngstrom <= maxW;
}

function calculateObservable(points, definition) {
  const bands = definition.bands || [];
  const bandStats = bands.map((band) => bandStatistic(points, band));
  const observableType = String(definition.observable_type || "").toLowerCase();
  const family = String(definition.calculation_family || "").toLowerCase();
  const isEquivalentWidth = observableType === "equivalent_width" || family.includes("equivalent_width");
  if (isEquivalentWidth) return equivalentWidthCalculation(points, definition, bandStats);
  return spectralIndexCalculation(points, definition, bandStats);
}

function bandStatistic(points, band) {
  const start = Number(band.wavelength_start);
  const end = Number(band.wavelength_end);
  const center = 0.5 * (start + end);
  const samples = points.filter((point) => point.wavelengthAngstrom >= start && point.wavelengthAngstrom <= end);
  const statistic = String(band.band_statistic || "").toLowerCase();
  let flux = null;
  if (samples.length) {
    const values = samples.map((point) => point.flux).filter(finite);
    flux = statistic.includes("median") ? robustMedian(values) : mean(values);
  } else {
    flux = interpolateFlux(points, center);
  }
  return {
    band,
    start,
    end,
    center,
    samples,
    flux: finite(flux) ? flux : null,
    displayFlux: finite(flux) && sieState.processed?.scale ? flux / sieState.processed.scale : null,
    interpolated: !samples.length && finite(flux),
  };
}

function spectralIndexCalculation(points, definition, bandStats) {
  const numerator = firstRoleStat(bandStats, "numerator");
  const denominator = firstRoleStat(bandStats, "denominator");
  if (numerator && denominator && finite(numerator.flux) && finite(denominator.flux) && denominator.flux !== 0) {
    const value = numerator.flux / denominator.flux;
    return calculationResult(definition, bandStats, value, null, [
      ["numerator", numerator],
      ["denominator", denominator],
    ], "mean(numerator) / mean(denominator)");
  }

  const feature = firstRoleStat(bandStats, "feature");
  const continuum = continuumModel(points, definition, bandStats);
  if (feature && continuum && finite(feature.flux) && feature.flux !== 0) {
    const continuumAtFeature = continuum.evaluate(feature.center);
    if (finite(continuumAtFeature) && continuumAtFeature !== 0) {
      const method = String(definition.combination_method || "").toLowerCase();
      const featureOverContinuum = method.includes("feature_divided") || method.includes("feature_over");
      const value = featureOverContinuum ? feature.flux / continuumAtFeature : continuumAtFeature / feature.flux;
      const formula = featureOverContinuum
        ? "mean(feature) / continuum(feature)"
        : "continuum(feature) / mean(feature)";
      return calculationResult(definition, bandStats, value, continuum, [
        ["feature", feature],
        ["continuum_at_feature", { flux: continuumAtFeature, center: feature.center, samples: [] }],
      ], formula);
    }
  }

  return calculationResult(definition, bandStats, null, continuum, [], "not calculable");
}

function equivalentWidthCalculation(points, definition, bandStats) {
  const feature = firstRoleStat(bandStats, "feature");
  const continuum = continuumModel(points, definition, bandStats);
  if (!feature || !continuum) {
    return calculationResult(definition, bandStats, null, continuum, [], "not calculable");
  }
  const grid = featureIntegrationGrid(points, feature);
  if (grid.length < 2) {
    return calculationResult(definition, bandStats, null, continuum, [], "not calculable");
  }
  const rows = grid.map((x) => {
    const flux = interpolateFlux(points, x);
    const cont = continuum.evaluate(x);
    const integrand = finite(flux) && finite(cont) && cont !== 0 ? 1 - flux / cont : null;
    return { wavelengthAngstrom: x, lam: x * 1e-4, flux, continuum: cont, integrand };
  }).filter((row) => finite(row.integrand));
  if (rows.length < 2) {
    return calculationResult(definition, bandStats, null, continuum, [], "not calculable");
  }
  let ew = 0;
  for (let index = 1; index < rows.length; index += 1) {
    const left = rows[index - 1];
    const right = rows[index];
    ew += 0.5 * (left.integrand + right.integrand) * (right.wavelengthAngstrom - left.wavelengthAngstrom);
  }
  const result = calculationResult(definition, bandStats, ew, continuum, [
    ["feature", feature],
    ["continuum_model", { flux: continuum.evaluate(feature.center), center: feature.center, samples: continuum.anchors || [] }],
  ], "integral(1 - flux / continuum) d_lambda");
  result.integrationRows = rows;
  return result;
}

function calculationResult(definition, bandStats, value, continuum, components, formula) {
  const isEquivalentWidth = String(definition.observable_type || "").toLowerCase() === "equivalent_width"
    || String(definition.calculation_family || "").toLowerCase().includes("equivalent_width");
  const unit = isEquivalentWidth ? "Angstrom" : "";
  return {
    value: finite(value) ? value : null,
    valueText: finite(value) ? `${formatNumber(value, isEquivalentWidth ? 4 : 5)}${unit ? ` ${unit}` : ""}` : "not calculable",
    unit,
    formula,
    definition,
    bandStats,
    continuum,
    components,
  };
}

function firstRoleStat(bandStats, role) {
  return bandStats.find((stat) => String(stat.band.band_role || "").toLowerCase() === role) || null;
}

function roleStats(bandStats, roles) {
  const wanted = new Set(roles);
  return bandStats.filter((stat) => wanted.has(String(stat.band.band_role || "").toLowerCase()));
}

function continuumModel(points, definition, bandStats) {
  const continuumStats = roleStats(bandStats, ["blue_continuum", "red_continuum", "continuum"]);
  const anchors = continuumStats
    .filter((stat) => finite(stat.flux))
    .map((stat) => ({ x: stat.center, y: stat.flux, stat }));
  if (!anchors.length) return null;
  if (anchors.length === 1) {
    const y = anchors[0].y;
    return { anchors, evaluate: () => y, coefficients: [y], degree: 0 };
  }
  const requestedDegree = parseInteger(definition.continuum_polynomial_degree);
  const degree = Math.max(1, Math.min(requestedDegree || 1, anchors.length - 1, 3));
  const coefficients = fitPolynomial(anchors.map((item) => item.x), anchors.map((item) => item.y), degree);
  if (!coefficients) {
    const sorted = anchors.slice().sort((a, b) => a.x - b.x);
    return {
      anchors,
      degree: 1,
      coefficients: null,
      evaluate: (x) => linearFromAnchors(sorted, x),
    };
  }
  return {
    anchors,
    degree,
    coefficients,
    evaluate: (x) => evaluatePolynomial(coefficients, x),
  };
}

function featureIntegrationGrid(points, featureStat) {
  const start = featureStat.start;
  const end = featureStat.end;
  const interior = points
    .filter((point) => point.wavelengthAngstrom >= start && point.wavelengthAngstrom <= end)
    .map((point) => point.wavelengthAngstrom);
  const grid = uniqueSorted([start, ...interior, end]);
  if (grid.length >= 2) return grid;
  return uniqueSorted([start, featureStat.center, end]);
}

function interpolateFlux(points, wavelengthAngstrom) {
  const sorted = points
    .filter((point) => finite(point.wavelengthAngstrom) && finite(point.flux))
    .sort((a, b) => a.wavelengthAngstrom - b.wavelengthAngstrom);
  if (!sorted.length) return null;
  if (wavelengthAngstrom <= sorted[0].wavelengthAngstrom) return sorted[0].flux;
  const last = sorted[sorted.length - 1];
  if (wavelengthAngstrom >= last.wavelengthAngstrom) return last.flux;
  for (let index = 1; index < sorted.length; index += 1) {
    const left = sorted[index - 1];
    const right = sorted[index];
    if (wavelengthAngstrom <= right.wavelengthAngstrom) {
      const dx = right.wavelengthAngstrom - left.wavelengthAngstrom;
      if (!finite(dx) || dx === 0) return left.flux;
      const t = (wavelengthAngstrom - left.wavelengthAngstrom) / dx;
      return left.flux + t * (right.flux - left.flux);
    }
  }
  return null;
}

function spectralIndexTraces(processed, calculation) {
  const points = processed.points;
  const line = lineWithGaps(points);
  const traces = [{
    type: "scattergl",
    mode: "lines",
    x: line.x,
    y: line.y,
    customdata: line.custom,
    line: { color: sieSpectrumColor, width: 1.7 },
    name: spectrumName(processed.metadata, processed.specid),
    hovertemplate: [
      "<b>%{customdata.label}</b>",
      "lambda = %{x:.7g} um",
      "display flux = %{y:.6g}",
      "stored flux = %{customdata.flux:.4e}",
      "<extra></extra>",
    ].join("<br>"),
  }];

  if (calculation.integrationRows?.length && calculation.continuum && sieEl["sie-show-continuum"].checked) {
    const scale = processed.scale || 1;
    const rows = calculation.integrationRows;
    traces.push({
      type: "scatter",
      mode: "lines",
      x: rows.map((row) => row.lam).concat(rows.map((row) => row.lam).reverse()),
      y: rows.map((row) => row.continuum / scale).concat(rows.map((row) => row.flux / scale).reverse()),
      fill: "toself",
      fillcolor: "rgba(178, 58, 72, 0.16)",
      line: { color: "rgba(178, 58, 72, 0)", width: 0 },
      name: "EW area",
      hoverinfo: "skip",
      showlegend: true,
    });
  }

  if (calculation.continuum && sieEl["sie-show-continuum"].checked) {
    const continuumTrace = continuumLineTrace(processed, calculation.continuum);
    if (continuumTrace) traces.push(continuumTrace);
  }

  if (sieEl["sie-show-points"].checked) {
    traces.push(...bandSampleTraces(processed, calculation.bandStats || []));
  }
  return traces;
}

function lineWithGaps(points) {
  if (points.length < 2) {
    return {
      x: points.map((point) => point.lam),
      y: points.map((point) => point.y),
      custom: points.map(pointCustomData),
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
    custom.push(pointCustomData(point));
  });
  return { x, y, custom };
}

function pointCustomData(point) {
  return {
    label: spectrumName(sieState.processed?.metadata || {}, sieState.processed?.specid || sieState.specid),
    flux: point.flux,
    ignored: point.ignored,
  };
}

function continuumLineTrace(processed, continuum) {
  const bands = processed.definition.bands || [];
  if (!bands.length) return null;
  const minW = Math.min(...bands.map((band) => band.wavelength_start));
  const maxW = Math.max(...bands.map((band) => band.wavelength_end));
  const x = [];
  const y = [];
  const count = 180;
  for (let index = 0; index < count; index += 1) {
    const wave = minW + (maxW - minW) * index / Math.max(1, count - 1);
    const value = continuum.evaluate(wave);
    if (finite(value)) {
      x.push(wave * 1e-4);
      y.push(value / processed.scale);
    }
  }
  if (x.length < 2) return null;
  return {
    type: "scatter",
    mode: "lines",
    x,
    y,
    line: { color: sieContinuumColor, width: 2.4, dash: "dash" },
    name: "Continuum model",
    hovertemplate: "continuum<br>lambda = %{x:.7g} um<br>flux = %{y:.6g}<extra></extra>",
  };
}

function bandSampleTraces(processed, bandStats) {
  const traces = [];
  for (const stat of bandStats) {
    const samples = stat.samples || [];
    const style = roleStyleForName(stat.band.band_role);
    if (samples.length) {
      traces.push({
        type: "scattergl",
        mode: "markers",
        x: samples.map((point) => point.lam),
        y: samples.map((point) => point.y),
        marker: {
          color: style.stroke,
          size: 7,
          symbol: "circle",
          line: { color: "#ffffff", width: 0.8 },
        },
        name: `${bandDisplayLabel(stat.band)} samples`,
        showlegend: false,
        hovertemplate: `${escapeHtml(bandDisplayLabel(stat.band))}<br>lambda = %{x:.7g} um<br>flux = %{y:.6g}<extra></extra>`,
      });
    }
    if (finite(stat.flux)) {
      traces.push({
        type: "scatter",
        mode: "markers",
        x: [stat.center * 1e-4],
        y: [stat.flux / processed.scale],
        marker: {
          color: "#ffffff",
          size: 11,
          symbol: "diamond",
          line: { color: style.stroke, width: 2.2 },
        },
        name: `${bandDisplayLabel(stat.band)} statistic`,
        showlegend: false,
        hovertemplate: `${escapeHtml(bandDisplayLabel(stat.band))}<br>statistic = %{y:.6g}<extra></extra>`,
      });
    }
  }
  return traces;
}

function spectralIndexLayout(processed, calculation) {
  const bands = processed.definition.bands || [];
  const shapes = [];
  const annotations = [];
  for (const band of bands) {
    const style = roleStyleForName(band.band_role);
    shapes.push({
      type: "rect",
      xref: "x",
      yref: "paper",
      x0: band.wavelength_start * 1e-4,
      x1: band.wavelength_end * 1e-4,
      y0: 0,
      y1: 1,
      line: { color: style.stroke, width: 1 },
      fillcolor: style.fill,
      layer: "below",
    });
    if (sieEl["sie-show-labels"].checked) {
      annotations.push({
        x: 0.5 * (band.wavelength_start + band.wavelength_end) * 1e-4,
        y: 0.985,
        xref: "x",
        yref: "paper",
        text: bandDisplayLabel(band),
        showarrow: false,
        font: { color: style.stroke, size: 11 },
        textangle: -90,
        yanchor: "top",
      });
    }
  }
  const xValues = processed.points.map((point) => point.lam);
  for (const band of bands) {
    xValues.push(band.wavelength_start * 1e-4, band.wavelength_end * 1e-4);
  }
  const yValues = processed.points.map((point) => point.y);
  if (calculation.continuum) {
    for (const band of bands) {
      const y0 = calculation.continuum.evaluate(band.wavelength_start);
      const y1 = calculation.continuum.evaluate(band.wavelength_end);
      if (finite(y0)) yValues.push(y0 / processed.scale);
      if (finite(y1)) yValues.push(y1 / processed.scale);
    }
  }
  const xRange = numericRange(xValues, 0.04);
  const yRange = numericRange(yValues, 0.1);
  return {
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { l: 82, r: 28, t: 18, b: 78 },
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 1.01,
      xanchor: "left",
      x: 0,
      bgcolor: "rgba(238,238,239,0.88)",
      font: { size: 12 },
    },
    xaxis: {
      title: { text: "Wavelength (um)", font: { size: 22 }, standoff: 18 },
      showgrid: true,
      gridcolor: "#e2e2e2",
      zeroline: false,
      tickfont: { size: 14 },
      automargin: true,
      range: xRange,
      ...boxAxisStyle(),
    },
    yaxis: {
      title: { text: sieEl["sie-normalize"].checked ? "Normalized spectral flux" : "Spectral flux", font: { size: 22 } },
      showgrid: true,
      gridcolor: "#e8e8e8",
      zeroline: false,
      tickfont: { size: 14 },
      automargin: true,
      range: yRange,
      ...boxAxisStyle(),
    },
    hovermode: "closest",
    shapes,
    annotations,
  };
}

function renderCalculationTable(calculation, processed) {
  const rows = [
    { field: "value", value: calculation.valueText || "not calculable" },
    { field: "formula", value: calculation.formula || "" },
    { field: "definition UID", value: processed.definition.definition_uid || "" },
    { field: "family", value: processed.definition.calculation_family || "" },
    { field: "continuum method", value: processed.definition.continuum_method || "" },
    { field: "polynomial degree", value: processed.definition.continuum_polynomial_degree ?? "" },
  ];
  for (const [name, stat] of calculation.components || []) {
    rows.push({
      field: name.replace(/_/g, " "),
      value: stat && finite(stat.flux)
        ? `${formatScientific(stat.flux)} at ${formatNumber((stat.center || 0) * 1e-4, 6)} um`
        : "",
    });
  }
  sieEl["sie-calculation-table"].innerHTML = tableHtml(["field", "value"], rows);
}

function renderBandTable(bands, calculation) {
  const statsByOrder = new Map((calculation.bandStats || []).map((stat) => [Number(stat.band.band_order), stat]));
  const rows = bands.map((band) => {
    const stat = statsByOrder.get(Number(band.band_order));
    return {
      order: band.band_order,
      role: band.band_role,
      label: band.band_label || "",
      start_um: formatNumber(Number(band.wavelength_start) * 1e-4, 7),
      end_um: formatNumber(Number(band.wavelength_end) * 1e-4, 7),
      rows: stat ? stat.samples.length : 0,
      statistic: stat && finite(stat.flux) ? formatScientific(stat.flux) : "",
    };
  });
  sieEl["sie-band-table"].innerHTML = tableHtml(["order", "role", "label", "start_um", "end_um", "rows", "statistic"], rows);
}

function renderEmptySpectralIndex(message) {
  Plotly.react(sieEl["sie-plot"], [], emptyLayout(message || "No definition loaded"), plotConfig("mocadb_spectral_index_empty"));
  sieEl["sie-summary"].textContent = message || "No definition loaded";
  sieEl["sie-hint"].textContent = "";
  sieEl["sie-calculation-table"].innerHTML = "";
  sieEl["sie-band-table"].innerHTML = "";
}

async function clearSpectralIndexCache() {
  const payload = await fetchJsonUrl(sieAppUrl("api/spectral-index-explorer/cache/clear"), { method: "POST" });
  if (payload.ok) {
    setSpectralIndexStatus("Cache cleared", "");
    await loadSpectralIndexExplorer();
  } else {
    setSpectralIndexStatus(payload.error || "Could not clear cache", "error");
  }
}

function openCurrentSpectrumExplorer() {
  const params = apiParams();
  params.set("moca_specid", String(sieState.specid));
  window.open(sieAppUrl(`spectra?${params.toString()}`), "_blank", "noopener");
}

function updateSpectralIndexUrl() {
  const params = new URLSearchParams(window.location.search);
  params.set("moca_specid", String(sieState.specid));
  params.set("definition_uid", sieState.definitionUid);
  params.set("normalize", sieEl["sie-normalize"].checked ? "1" : "0");
  params.set("continuum", sieEl["sie-show-continuum"].checked ? "1" : "0");
  params.set("labels", sieEl["sie-show-labels"].checked ? "1" : "0");
  params.set("points", sieEl["sie-show-points"].checked ? "1" : "0");
  params.set("hide_ignored", sieEl["sie-hide-ignored"].checked ? "1" : "0");
  const next = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", next);
}

function setSpectralIndexStatus(text, className) {
  sieEl["sie-status"].textContent = text;
  sieEl["sie-status"].className = `status ${className || ""}`.trim();
}

function setSpectralIndexLoading(loading) {
  sieEl["sie-plot-loader"].classList.toggle("is-visible", Boolean(loading));
}

function apiParams() {
  const current = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "port", "user", "username", "pwd", "password", "dbase", "db", "database", "mock"]) {
    if (current.has(key)) params.set(key, current.get(key));
  }
  if (params.has("db") && !params.has("dbase")) params.set("dbase", params.get("db"));
  if (params.has("database") && !params.has("dbase")) params.set("dbase", params.get("database"));
  if (params.has("username") && !params.has("user")) params.set("user", params.get("username"));
  if (params.has("password") && !params.has("pwd")) params.set("pwd", params.get("password"));
  return params;
}

async function fetchJsonUrl(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({ ok: false, error: `HTTP ${response.status}` }));
  return payload;
}

function plotConfig(filename) {
  return {
    responsive: true,
    displaylogo: false,
    toImageButtonOptions: { format: "png", filename, scale: 2 },
    modeBarButtonsToRemove: ["lasso2d"],
  };
}

function emptyLayout(message) {
  return {
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { l: 40, r: 20, t: 20, b: 40 },
    xaxis: { visible: false },
    yaxis: { visible: false },
    annotations: [{
      text: message,
      x: 0.5,
      y: 0.5,
      xref: "paper",
      yref: "paper",
      showarrow: false,
      font: { size: 18, color: "#5f5864" },
    }],
  };
}

function fitPolynomial(xs, ys, degree) {
  const n = degree + 1;
  const matrix = Array.from({ length: n }, () => Array(n).fill(0));
  const vector = Array(n).fill(0);
  const x0 = mean(xs);
  const scale = Math.max(1, Math.max(...xs.map((x) => Math.abs(x - x0))));
  for (let row = 0; row < xs.length; row += 1) {
    const x = (xs[row] - x0) / scale;
    const powers = Array(n).fill(1);
    for (let power = 1; power < n; power += 1) powers[power] = powers[power - 1] * x;
    for (let i = 0; i < n; i += 1) {
      vector[i] += ys[row] * powers[i];
      for (let j = 0; j < n; j += 1) matrix[i][j] += powers[i] * powers[j];
    }
  }
  const coeffs = solveLinearSystem(matrix, vector);
  if (!coeffs) return null;
  return { coeffs, x0, scale };
}

function evaluatePolynomial(model, xRaw) {
  const x = (xRaw - model.x0) / model.scale;
  let out = 0;
  let power = 1;
  for (const coeff of model.coeffs) {
    out += coeff * power;
    power *= x;
  }
  return out;
}

function solveLinearSystem(matrix, vector) {
  const n = vector.length;
  const a = matrix.map((row, index) => row.concat(vector[index]));
  for (let col = 0; col < n; col += 1) {
    let pivot = col;
    for (let row = col + 1; row < n; row += 1) {
      if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row;
    }
    if (Math.abs(a[pivot][col]) < 1e-30) return null;
    if (pivot !== col) [a[pivot], a[col]] = [a[col], a[pivot]];
    const divisor = a[col][col];
    for (let item = col; item <= n; item += 1) a[col][item] /= divisor;
    for (let row = 0; row < n; row += 1) {
      if (row === col) continue;
      const factor = a[row][col];
      for (let item = col; item <= n; item += 1) a[row][item] -= factor * a[col][item];
    }
  }
  return a.map((row) => row[n]);
}

function linearFromAnchors(anchors, x) {
  if (!anchors.length) return null;
  if (anchors.length === 1) return anchors[0].y;
  if (x <= anchors[0].x) return interpolateAnchor(anchors[0], anchors[1], x);
  for (let index = 1; index < anchors.length; index += 1) {
    if (x <= anchors[index].x) return interpolateAnchor(anchors[index - 1], anchors[index], x);
  }
  return interpolateAnchor(anchors[anchors.length - 2], anchors[anchors.length - 1], x);
}

function interpolateAnchor(left, right, x) {
  const dx = right.x - left.x;
  if (!finite(dx) || dx === 0) return left.y;
  return left.y + (x - left.x) * (right.y - left.y) / dx;
}

function roleStyleForName(role) {
  const key = String(role || "").toLowerCase();
  if (key.includes("denominator")) return sieRoleStyles.denominator;
  if (key.includes("numerator")) return sieRoleStyles.numerator;
  if (key.includes("feature")) return sieRoleStyles.feature;
  if (key.includes("blue")) return sieRoleStyles.blue_continuum;
  if (key.includes("red")) return sieRoleStyles.red_continuum;
  if (key.includes("continuum")) return sieRoleStyles.continuum;
  if (key.includes("equivalent")) return sieRoleStyles.feature;
  return { label: role || "Band", stroke: "#6C6471", fill: "rgba(108, 100, 113, 0.14)" };
}

function bandDisplayLabel(band) {
  const label = band.band_label || roleStyleForName(band.band_role).label || band.band_role || "Band";
  return `${label}`;
}

function definitionDisplayName(definition) {
  return definition.display_name || definition.legacy_observable_name || definition.moca_siid || definition.moca_spid || definition.definition_uid || "definition";
}

function currentSpectrumMetadata() {
  return {
    ...(sieState.spectrumMetadata || {}),
    ...(sieState.payload?.spectrum?.metadata || {}),
    moca_specid: sieState.specid,
  };
}

function currentDefinitionMetadata() {
  return {
    ...(sieState.definitionMetadata || {}),
    ...(sieState.payload?.definition || {}),
    definition_uid: sieState.definitionUid,
  };
}

function spectrumMetadataFromOption(option) {
  const specid = Number(option?.moca_specid ?? option?.value ?? sieState.specid);
  return {
    ...(option || {}),
    moca_specid: Number.isFinite(specid) ? specid : option?.moca_specid,
    value: Number.isFinite(specid) ? specid : option?.value,
    label: option?.label || (Number.isFinite(specid) ? `specid${specid}` : ""),
  };
}

function definitionMetadataFromOption(option) {
  return {
    ...(option || {}),
    definition_uid: option?.definition_uid || option?.value || sieState.definitionUid,
    value: option?.value || option?.definition_uid || sieState.definitionUid,
    label: option?.label || option?.definition_uid || option?.value || "",
  };
}

function spectrumName(metadata, specid) {
  return metadata?.designation || metadata?.spectrum_name || `specid${specid}`;
}

function instrumentLabel(metadata) {
  return [metadata?.moca_instid, metadata?.instrument_mode_name].filter(Boolean).join(" ");
}

function normalizedMocaOid(oid) {
  const value = Number(oid);
  return Number.isInteger(value) && value > 0 ? value : null;
}

function wavelengthRangeText(start, end) {
  if (!finite(start) || !finite(end)) return "";
  return `${formatNumber(Number(start) * 1e-4, 5)}-${formatNumber(Number(end) * 1e-4, 5)} um`;
}

function tableHtml(columns, rows) {
  if (!rows.length) return `<div class="plot-hint">No rows</div>`;
  return `
    <table>
      <thead><tr>${columns.map((column) => `<th>${escapeHtml(column.replace(/_/g, " "))}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column] ?? "")}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

function boxAxisStyle() {
  return {
    showline: true,
    linecolor: "#252329",
    linewidth: 1.2,
    mirror: true,
    ticks: "outside",
    tickcolor: "#252329",
  };
}

function numericRange(values, padFraction) {
  const finiteValues = values.filter(finite);
  if (!finiteValues.length) return null;
  let minValue = Math.min(...finiteValues);
  let maxValue = Math.max(...finiteValues);
  if (minValue === maxValue) {
    const pad = Math.max(Math.abs(minValue) * 0.05, 1);
    return [minValue - pad, maxValue + pad];
  }
  const pad = (maxValue - minValue) * padFraction;
  return [minValue - pad, maxValue + pad];
}

function uniqueSorted(values) {
  const out = [];
  for (const value of values.filter(finite).sort((a, b) => a - b)) {
    if (!out.length || Math.abs(value - out[out.length - 1]) > 1e-8) out.push(value);
  }
  return out;
}

function mean(values) {
  const clean = values.filter(finite);
  return clean.length ? clean.reduce((sum, value) => sum + value, 0) / clean.length : null;
}

function robustMedian(values) {
  const clean = values.filter(finite).slice().sort((a, b) => a - b);
  if (!clean.length) return null;
  const mid = Math.floor(clean.length / 2);
  return clean.length % 2 ? clean[mid] : 0.5 * (clean[mid - 1] + clean[mid]);
}

function formatNumber(value, digits = 4) {
  if (!finite(value)) return "";
  const absValue = Math.abs(Number(value));
  if (absValue !== 0 && (absValue < 1e-4 || absValue >= 1e5)) return Number(value).toExponential(Math.max(1, digits - 1));
  return Number(value).toLocaleString(undefined, { maximumSignificantDigits: digits });
}

function formatScientific(value) {
  if (!finite(value)) return "";
  return Number(value).toExponential(4);
}

function pluralize(count, singular, plural) {
  const value = Number(count) || 0;
  return `${value.toLocaleString()} ${value === 1 ? singular : plural}`;
}

function finite(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" && value.trim() === "") return false;
  return Number.isFinite(Number(value));
}

function parseInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function ignoredFlag(value) {
  return String(value || "").trim() === "1" || value === true;
}

function asFalse(value) {
  if (value === false) return true;
  if (value === true) return false;
  return ["0", "false", "no", "off"].includes(String(value || "").trim().toLowerCase());
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
