const speDefaultSpecids = [13510];
const speDefaultNorm = "0.95-1.35";
const speDefaultBinsPerMicron = 200;
const speSpeedOfLight = 299792458.0;
const speColors = ["#377EB8", "#E41A1C", "#4DAF4A", "#984EA3", "#FF7F00", "#A65628", "#F781BF", "#999999", "#66C2A5", "#FC8D62", "#8DA0CB", "#E78AC3"];

const speFeatureBands = [
  { name: "H2O", range: [0.92, 0.96], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "FeH", range: [0.985, 1.005], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "VO", range: [1.045, 1.08], fill: "rgba(0,139,0,0.10)", text: "rgba(0,139,0,0.65)" },
  { name: "H2O", range: [1.13, 1.17], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "VO", range: [1.17, 1.2], fill: "rgba(0,139,0,0.10)", text: "rgba(0,139,0,0.65)" },
  { name: "FeH", range: [1.19, 1.24], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "Na", range: [1.137, 1.142], fill: "rgba(139,100,0,0.10)", text: "rgba(139,100,0,0.65)", labelY: 0.98 },
  { name: "K", range: [1.169, 1.181], fill: "rgba(139,100,0,0.10)", text: "rgba(139,100,0,0.65)", labelY: 0.955 },
  { name: "K", range: [1.243, 1.253], fill: "rgba(139,100,0,0.10)", text: "rgba(139,100,0,0.65)" },
  { name: "H2O", range: [1.32, 1.35], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "H2O", range: [1.5, 1.62], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "FeH", range: [1.583, 1.62], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "CH4", range: [1.6, 1.68], fill: "rgba(139,69,139,0.10)", text: "rgba(139,69,139,0.65)" },
  { name: "CH4", range: [1.72, 1.78], fill: "rgba(139,69,139,0.10)", text: "rgba(139,69,139,0.65)" },
  { name: "H2O", range: [1.95, 2.11], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "Na", range: [2.195, 2.205], fill: "rgba(139,100,0,0.10)", text: "rgba(139,100,0,0.65)" },
  { name: "CH4", range: [2.2, 2.27], fill: "rgba(139,69,139,0.10)", text: "rgba(139,69,139,0.65)" },
  { name: "CO", range: [2.293, 2.4], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "H2O", range: [2.5, 3.1], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "CH4", range: [3.15, 3.45], fill: "rgba(139,69,139,0.10)", text: "rgba(139,69,139,0.65)" },
  { name: "NH3", range: [3.9, 4.5], fill: "rgba(20,120,120,0.10)", text: "rgba(20,110,110,0.65)" },
  { name: "PH3", range: [4.2, 4.35], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)", labelY: 0.955 },
  { name: "CO", range: [4.55, 4.95], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "H2O", range: [5.0, 7.0], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)" },
  { name: "CH4", range: [7.0, 9.2], fill: "rgba(139,69,139,0.10)", text: "rgba(139,69,139,0.65)" },
  { name: "Silicates", range: [9.0, 13.0], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "NH3", range: [10.0, 11.0], fill: "rgba(20,120,120,0.10)", text: "rgba(20,110,110,0.65)", labelY: 0.955 },
  { name: "CO2", range: [14.7, 15.3], fill: "rgba(90,90,90,0.08)", text: "rgba(60,60,60,0.65)" },
  { name: "H2O", range: [15.0, 20.0], fill: "rgba(0,0,139,0.10)", text: "rgba(0,0,139,0.65)", labelY: 0.955 },
];

const speState = {
  selected: [],
  payload: null,
  processed: [],
  selectedPoints: [],
  searchTimer: null,
  loadToken: 0,
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
  return new URL(String(path || "").replace(/^\/+/, ""), speAppBaseUrl).toString();
}

async function initSpectraExplorer() {
  collectSpectraElements();
  readSpectraUrlState();
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
    "spe-xlog",
    "spe-ylog",
    "spe-fnu",
    "spe-showfeatures",
    "spe-disable-lowres-wrap",
    "spe-disable-lowres",
    "spe-normalize",
    "spe-normrange",
    "spe-reset-norm",
    "spe-plot",
    "spe-plot-loader",
    "spe-summary",
    "spe-hint",
    "spe-export-csv",
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
  speEl["spe-xlog"].checked = !asFalse(params.get("xlog"));
  speEl["spe-ylog"].checked = !asFalse(params.get("ylog"));
  speEl["spe-fnu"].checked = asBool(params.get("fnu_jy") || params.get("fnu"));
  speEl["spe-showfeatures"].checked = !asFalse(params.get("showfeatures"));
  speEl["spe-disable-lowres"].checked = asBool(params.get("disable_lowres"));
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
    updateSpectraUrl();
    speEl["spe-search"].focus();
  });
  for (const id of ["spe-hover", "spe-xlog", "spe-ylog", "spe-fnu", "spe-showfeatures", "spe-disable-lowres", "spe-normalize"]) {
    speEl[id].addEventListener("change", () => {
      renderSpectra();
      updateSpectraUrl();
    });
  }
  speEl["spe-normrange"].addEventListener("change", () => {
    renderSpectra();
    updateSpectraUrl();
  });
  speEl["spe-reset-norm"].addEventListener("click", () => {
    speEl["spe-normrange"].value = speDefaultNorm;
    renderSpectra();
    updateSpectraUrl();
  });
  speEl["spe-export-csv"].addEventListener("click", exportPlottedSpectraCsv);
  speEl["spe-clear-cache"].addEventListener("click", clearSpectraCache);
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
  const labels = new Map((payload.options || []).map((item) => [Number(item.value), item.label || `specid${item.value}`]));
  speState.selected = speState.selected.map((item) => ({ ...item, label: labels.get(item.specid) || item.label }));
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
      addSelectedSpectrum(Number(result.value), result.label || `specid${result.value}`);
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

function addSelectedSpectrum(specid, label) {
  if (!Number.isFinite(specid)) return;
  if (speState.selected.some((item) => item.specid === specid)) return;
  speState.selected.push({ specid, label });
  renderSelectedSpectra();
  updateSpectraUrl();
}

function renderSelectedSpectra() {
  if (!speState.selected.length) {
    speEl["spe-selected-list"].innerHTML = `<div class="plot-hint">No spectra selected</div>`;
    return;
  }
  speEl["spe-selected-list"].innerHTML = speState.selected.map((item) => `
    <div class="designation-chip spectra-chip" title="${escapeHtml(item.label)}">
      <span>${escapeHtml(item.label)}</span>
      <button type="button" aria-label="Remove specid ${item.specid}" data-specid="${item.specid}">x</button>
    </div>
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

async function loadSpectra() {
  if (!speState.selected.length) {
    renderEmptySpectra("Select one or more spectra");
    return;
  }
  const token = ++speState.loadToken;
  setSpectraLoading(true);
  setSpectraStatus("Loading spectra", "loading");
  const params = apiParams();
  params.set("specids", speState.selected.map((item) => item.specid).join(","));
  params.set("bins", new URLSearchParams(window.location.search).get("bins") || String(speDefaultBinsPerMicron));
  const payload = await fetchJsonUrl(speAppUrl(`api/spectra/load?${params.toString()}`));
  if (token !== speState.loadToken) return;
  if (!payload.ok) {
    setSpectraStatus(payload.error || "Could not load spectra", "error");
    renderEmptySpectra(payload.error || "Could not load spectra");
    return;
  }
  speState.payload = payload;
  speState.selectedPoints = [];
  const labels = new Map((payload.spectra || []).map((item) => [Number(item.moca_specid), item.metadata?.label || `specid${item.moca_specid}`]));
  speState.selected = speState.selected.map((item) => ({ ...item, label: labels.get(item.specid) || item.label }));
  renderSelectedSpectra();
  renderDownloadLinks();
  updateLowresToggleState();
  renderSpectra();
  updateSpectraUrl();
}

function renderSpectra() {
  if (!speState.payload || !(speState.payload.spectra || []).length) {
    renderEmptySpectra("No spectra loaded");
    return;
  }
  setSpectraLoading(true);
  const processed = processSpectraPayload();
  speState.processed = processed;
  const traces = [];
  processed.forEach((spectrum, index) => {
    const color = speColors[index % speColors.length];
    if (!spectrum.points.length) return;
    if (spectrum.lowRes && !speEl["spe-disable-lowres"].checked) {
      traces.push({
        type: "scattergl",
        mode: "lines",
        x: spectrum.points.map((point) => point.lam),
        y: spectrum.points.map((point) => point.y),
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
          symbol: "circle-open",
          color,
          size: 8,
          line: { color, width: 2 },
        },
        error_y: {
          type: "data",
          array: spectrum.points.map((point) => point.yerr || 0),
          visible: spectrum.points.some((point) => finite(point.yerr)),
          color,
          thickness: 1,
          width: 2,
        },
        name: spectrum.name,
        legendgroup: String(spectrum.specid),
        hovertemplate: hoverTemplate(),
        hoverinfo: speEl["spe-hover"].checked ? undefined : "skip",
      });
    } else {
      const lineData = lineWithGaps(spectrum.points);
      traces.push({
        type: "scattergl",
        mode: "lines",
        x: lineData.x,
        y: lineData.y,
        customdata: lineData.custom,
        line: { color, width: 1.5 },
        name: spectrum.name,
        legendgroup: String(spectrum.specid),
        hovertemplate: hoverTemplate(),
        hoverinfo: speEl["spe-hover"].checked ? undefined : "skip",
      });
    }
  });

  const layout = spectraLayout(processed);
  Plotly.react(speEl["spe-plot"], traces, layout, plotConfig("mocadb_spectral_explorer"));
  bindSpectraPlotEvents();
  speEl["spe-export-csv"].disabled = processed.every((spectrum) => !spectrum.points.length);
  const rowCount = processed.reduce((sum, spectrum) => sum + spectrum.rawRows.length, 0);
  const cacheText = speState.payload.cache?.hit ? " from cache" : "";
  setSpectraStatus(`${processed.length} spectra loaded${cacheText}`, "");
  speEl["spe-summary"].textContent = `${processed.length} spectra loaded, ${rowCount.toLocaleString()} spectral rows`;
  speEl["spe-hint"].textContent = speEl["spe-normalize"].checked ? "Displayed fluxes are normalized by the selected wavelength range." : "Displayed fluxes use the stored spectral flux calibration.";
  renderSpectraTable();
  setSpectraLoading(false);
}

function bindSpectraPlotEvents() {
  if (speEl["spe-plot"].dataset.bound === "1" || typeof speEl["spe-plot"].on !== "function") return;
  speEl["spe-plot"].dataset.bound = "1";
  speEl["spe-plot"].on("plotly_click", (event) => {
    const points = event?.points || [];
    speState.selectedPoints = points.map(pointFromPlotly).filter(Boolean);
    renderSpectraTable();
  });
  speEl["spe-plot"].on("plotly_selected", (event) => {
    const points = event?.points || [];
    speState.selectedPoints = points.map(pointFromPlotly).filter(Boolean);
    renderSpectraTable();
  });
}

function processSpectraPayload() {
  const range = parseNormRange(speEl["spe-normrange"].value);
  const useFnu = speEl["spe-fnu"].checked;
  const normalize = speEl["spe-normalize"].checked;
  const ylog = speEl["spe-ylog"].checked;
  return (speState.payload.spectra || []).map((spectrum, index) => {
    const metadata = spectrum.metadata || {};
    const rawRows = (spectrum.rows || []).map((row, rowIndex) => {
      const lam = wavelengthMicron(row.lam);
      const rawFlambdaUm = Number(row.sp) * 10000.0;
      const rawErrFlambdaUm = finite(row.esp) ? Number(row.esp) * 10000.0 : null;
      const converted = useFnu && finite(lam)
        ? rawFlambdaUm * lam * lam * 1e20 / speSpeedOfLight
        : rawFlambdaUm;
      const convertedErr = useFnu && finite(lam) && finite(rawErrFlambdaUm)
        ? rawErrFlambdaUm * lam * lam * 1e20 / speSpeedOfLight
        : rawErrFlambdaUm;
      return {
        rowIndex,
        specid: Number(spectrum.moca_specid),
        lam,
        rawFlambdaUm,
        rawErrFlambdaUm,
        yOriginal: converted,
        yerrOriginal: convertedErr,
      };
    }).filter((row) => finite(row.lam) && finite(row.yOriginal));
    const normCandidates = rawRows.filter((row) => row.lam >= range[0] && row.lam <= range[1] && finite(row.yOriginal) && row.yOriginal !== 0);
    const scale = normalize ? robustMedian(normCandidates.map((row) => row.yOriginal)) : 1;
    const safeScale = finite(scale) && scale !== 0 ? scale : 1;
    const points = rawRows.map((row) => {
      const y = row.yOriginal / safeScale;
      const yerr = finite(row.yerrOriginal) ? Math.abs(row.yerrOriginal / safeScale) : null;
      return {
        ...row,
        y,
        yerr,
        custom: {
          specid: Number(spectrum.moca_specid),
          oid: metadata.moca_oid,
          label: spectrumName(metadata, Number(spectrum.moca_specid)),
          lam: row.lam,
          y,
          yerr,
          rawFlambdaUm: row.rawFlambdaUm,
          rawErrFlambdaUm: row.rawErrFlambdaUm,
          normalized: normalize,
          unit: yAxisUnit(),
          rowIndex: row.rowIndex,
        },
      };
    }).filter((row) => finite(row.lam) && finite(row.y) && (!ylog || row.y > 0));
    return {
      specid: Number(spectrum.moca_specid),
      metadata,
      name: spectrumName(metadata, Number(spectrum.moca_specid)),
      rawRows,
      points,
      lowRes: finite(spectrum.meta?.average_resolving_power) && Number(spectrum.meta.average_resolving_power) < 100,
      averageResolvingPower: spectrum.meta?.average_resolving_power,
      color: speColors[index % speColors.length],
    };
  });
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

function spectraLayout(processed) {
  const xlog = speEl["spe-xlog"].checked;
  const ylog = speEl["spe-ylog"].checked;
  const shapes = [];
  const annotations = [];
  const allX = processed.flatMap((spectrum) => spectrum.points.map((point) => point.lam));
  const allY = processed.flatMap((spectrum) => spectrum.points.map((point) => point.y));
  const xRange = numericAxisRange(allX, { log: xlog, fallback: xlog ? [0.7, 30] : [0.7, 2.6] });
  const yRange = numericAxisRange(allY, { log: ylog, fallback: null, padFraction: 0.08 });
  const xmin = xRange ? xRange[0] : NaN;
  const xmax = xRange ? xRange[1] : NaN;
  if (speEl["spe-showfeatures"].checked && finite(xmin) && finite(xmax)) {
    for (const band of speFeatureBands) {
      if (band.range[1] < xmin || band.range[0] > xmax) continue;
      shapes.push({
        type: "rect",
        xref: "x",
        yref: "paper",
        x0: band.range[0],
        x1: band.range[1],
        y0: 0,
        y1: 1,
        line: { width: 0 },
        fillcolor: band.fill,
        layer: "below",
      });
      annotations.push({
        x: featureAnnotationX(band, xlog),
        y: band.labelY || 0.992,
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
  return {
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
      font: { size: 12 },
    },
    xaxis,
    yaxis,
    dragmode: "select",
    hovermode: speEl["spe-hover"].checked ? "closest" : false,
    shapes,
    annotations,
  };
}

function featureAnnotationX(band, xlog) {
  const x0 = Number(band.range?.[0]);
  const x1 = Number(band.range?.[1]);
  if (xlog && x0 > 0 && x1 > 0) return Math.log10(Math.sqrt(x0 * x1));
  return 0.5 * (x0 + x1);
}

function hoverTemplate() {
  if (!speEl["spe-hover"].checked) return undefined;
  return [
    "<b>%{customdata.label}</b>",
    "specid %{customdata.specid}",
    "λ = %{x:.6g} μm",
    `${speEl["spe-normalize"].checked ? "Normalized flux" : "Flux"} = %{y:.6g} %{customdata.unit}`,
    "error = %{customdata.yerr:.3g} %{customdata.unit}",
    "stored Fλ = %{customdata.rawFlambdaUm:.4e} W/m²/μm",
    "<extra></extra>",
  ].join("<br>");
}

function updateLowresToggleState() {
  const hasLowRes = (speState.payload?.spectra || []).some((spectrum) => finite(spectrum.meta?.average_resolving_power) && Number(spectrum.meta.average_resolving_power) < 100);
  speEl["spe-disable-lowres"].disabled = !hasLowRes;
  speEl["spe-disable-lowres-wrap"].classList.toggle("is-disabled", !hasLowRes);
  if (!hasLowRes) speEl["spe-disable-lowres"].checked = false;
}

function renderDownloadLinks() {
  const spectra = speState.payload?.spectra || [];
  if (!spectra.length) {
    speEl["spe-download-links"].innerHTML = "";
    return;
  }
  speEl["spe-download-links"].innerHTML = spectra.map((spectrum) => (
    `<button type="button" data-specid="${spectrum.moca_specid}">CSV specid${spectrum.moca_specid}</button>`
  )).join("");
  speEl["spe-download-links"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => downloadRawSpectrumCsv(Number(button.dataset.specid)));
  });
}

function renderSpectraTable() {
  if (speState.selectedPoints.length) {
    speEl["spe-table-title"].textContent = `${speState.selectedPoints.length} selected spectral rows`;
    speEl["spe-table-subtitle"].textContent = "Rows reflect the displayed flux unit and normalization state.";
    const columns = ["specid", "oid", "wavelength_um", "display_flux", "display_error", "raw_flambda_w_m2_um"];
    const rows = speState.selectedPoints.map((point) => ({
      specid: point.specid,
      oid: point.oid,
      wavelength_um: formatNumber(point.lam, 6),
      display_flux: formatScientific(point.y),
      display_error: finite(point.yerr) ? formatScientific(point.yerr) : "",
      raw_flambda_w_m2_um: formatScientific(point.rawFlambdaUm),
    }));
    speEl["spe-table"].innerHTML = tableHtml(columns, rows);
    return;
  }
  const rows = (speState.processed || []).map((spectrum) => ({
    specid: spectrum.specid,
    oid: spectrum.metadata?.moca_oid ?? "",
    object: spectrum.metadata?.designation || "",
    spectral_type: spectrum.metadata?.spectral_type || "",
    instrument: instrumentLabel(spectrum.metadata),
    rows: spectrum.rawRows.length.toLocaleString(),
    resolving_power: finite(spectrum.averageResolvingPower) ? Math.round(Number(spectrum.averageResolvingPower)).toLocaleString() : "",
    report: spectrum.metadata?.moca_oid ? `<a class="report-link" href="${mocaReportUrl(spectrum.metadata.moca_oid)}" target="_blank" rel="noopener">Report</a>` : "",
  }));
  speEl["spe-table-title"].textContent = "Selected spectra";
  speEl["spe-table-subtitle"].textContent = "Click or box-select plotted points to inspect spectral rows.";
  speEl["spe-table"].innerHTML = tableHtml(["specid", "oid", "object", "spectral_type", "instrument", "rows", "resolving_power", "report"], rows, { htmlColumns: new Set(["report"]) });
}

function pointFromPlotly(point) {
  const custom = point?.customdata;
  if (!custom || typeof custom !== "object") return null;
  return custom;
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
  Plotly.react(speEl["spe-plot"], [], layout, plotConfig("mocadb_spectral_explorer_empty"));
  speEl["spe-summary"].textContent = message;
  speEl["spe-table"].innerHTML = "";
  speEl["spe-export-csv"].disabled = true;
  setSpectraLoading(false);
  setSpectraStatus(message, message.includes("Could not") ? "error" : "");
}

function downloadRawSpectrumCsv(specid) {
  const spectrum = (speState.payload?.spectra || []).find((item) => Number(item.moca_specid) === Number(specid));
  if (!spectrum) return;
  const metadata = spectrum.metadata || {};
  const columns = ["moca_specid", "moca_oid", "wavelength_um", "flux_flambda_w_m2_angstrom", "flux_flambda_unc_w_m2_angstrom"];
  const lines = [
    `# ${metadata.label || `specid${specid}`}`,
    columns.join(","),
    ...(spectrum.rows || []).map((row) => [
      spectrum.moca_specid,
      metadata.moca_oid || "",
      row.lam,
      row.sp,
      row.esp ?? "",
    ].map(csvCell).join(",")),
  ];
  downloadBlob(lines.join("\n"), `mocadb_spectrum_specid${specid}.csv`, "text/csv;charset=utf-8");
}

function exportPlottedSpectraCsv() {
  const columns = ["moca_specid", "moca_oid", "wavelength_um", "display_flux", "display_error", "raw_flambda_w_m2_um", "raw_flambda_unc_w_m2_um", "display_unit", "normalized"];
  const rows = [];
  (speState.processed || []).forEach((spectrum) => {
    spectrum.points.forEach((point) => {
      rows.push([
        spectrum.specid,
        spectrum.metadata?.moca_oid || "",
        point.lam,
        point.y,
        point.yerr ?? "",
        point.rawFlambdaUm,
        point.rawErrFlambdaUm ?? "",
        yAxisUnit(),
        speEl["spe-normalize"].checked ? 1 : 0,
      ]);
    });
  });
  if (!rows.length) return;
  const csv = [columns.join(","), ...rows.map((row) => row.map(csvCell).join(","))].join("\n");
  downloadBlob(csv, "mocadb_spectral_explorer_plotted.csv", "text/csv;charset=utf-8");
}

async function clearSpectraCache() {
  speEl["spe-clear-cache"].disabled = true;
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
    speEl["spe-clear-cache"].disabled = false;
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
  if (!speEl["spe-xlog"].checked) params.set("xlog", "0");
  else params.delete("xlog");
  if (!speEl["spe-ylog"].checked) params.set("ylog", "0");
  else params.delete("ylog");
  setBoolParam(params, "fnu_jy", speEl["spe-fnu"].checked);
  if (!speEl["spe-showfeatures"].checked) params.set("showfeatures", "0");
  else params.delete("showfeatures");
  setBoolParam(params, "disable_lowres", speEl["spe-disable-lowres"].checked);
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
  if (speEl["spe-normalize"].checked) {
    return speEl["spe-fnu"].checked
      ? "Relative spectral flux density <i>F</i><sub>ν</sub>"
      : "Relative spectral flux density <i>F</i><sub>λ</sub>";
  }
  return speEl["spe-fnu"].checked
    ? "Flux density <i>F</i><sub>ν</sub> (Jy)"
    : "Spectral flux density <i>F</i><sub>λ</sub> (W/m²/μm)";
}

function yAxisUnit() {
  if (speEl["spe-normalize"].checked) return "relative";
  return speEl["spe-fnu"].checked ? "Jy" : "W/m²/μm";
}

function spectrumName(metadata, specid) {
  const designation = metadata?.designation || metadata?.spectrum_name || `specid${specid}`;
  const spt = metadata?.spectral_type ? ` (${metadata.spectral_type})` : "";
  return `${designation}${spt}`;
}

function instrumentLabel(metadata) {
  return [metadata?.moca_instid, metadata?.instrument_mode_name ? `${metadata.instrument_mode_name} mode` : ""].filter(Boolean).join(", ");
}

function wavelengthMicron(value) {
  const lam = Number(value);
  if (!finite(lam) || lam <= 0) return NaN;
  // The API normally returns microns, but older/mock payloads may still expose Angstrom values.
  return lam > 100 ? lam * 1e-4 : lam;
}

function parseNormRange(raw) {
  const match = String(raw || "").match(/(-?\d+(?:\.\d+)?)\s*[-:]\s*(-?\d+(?:\.\d+)?)/);
  if (!match) return [0.95, 1.35];
  const a = Number(match[1]);
  const b = Number(match[2]);
  if (!finite(a) || !finite(b) || a === b) return [0.95, 1.35];
  return [Math.min(a, b), Math.max(a, b)];
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
  return {
    values: ticks.map((tick) => tick.value),
    text: ticks.map((tick) => options.majorLabelsOnly && !tick.major ? "" : formatPlainLogTick(tick.value)),
  };
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
  for (const key of ["host", "user", "pwd", "dbase", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
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
  return {
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
}

function setBoolParam(params, key, checked) {
  if (checked) params.set(key, "1");
  else params.delete(key);
}

function mocaReportUrl(oid) {
  return `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(oid)}%29&search-type=star`;
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
  return Number.isFinite(Number(value));
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

function asFalse(value) {
  return ["0", "false", "no", "off"].includes(String(value || "").toLowerCase());
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
