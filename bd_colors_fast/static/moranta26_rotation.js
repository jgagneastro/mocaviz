const m26DefaultLambdas = [1, 2, 4, 8, 16];
const m26LiteratureTolerance = 0.15;
const m26MinPeriodDays = 0.05;
const m26MaxPeriodDays = 30.0;
const m26RevisedColor = "#E76F51";
const m26LambdaColors = {
  1: "#0072B2",
  2: "#009E73",
  4: "#D55E00",
  8: "#CC79A7",
  16: "#6B5B95",
};

const m26State = {
  rows: [],
  options: {},
  filteredRows: [],
  selectedStarKey: "",
  selectedPhotseqid: null,
  customPeriod: null,
  lightcurvePayload: null,
  initial: {},
  loadToken: 0,
};

const m26El = {};

document.addEventListener("DOMContentLoaded", initMoranta26Rotation);

const m26AppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function m26AppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), m26AppBaseUrl).toString();
}

async function initMoranta26Rotation() {
  collectMoranta26Elements();
  readMoranta26UrlState();
  bindMoranta26Controls();
  renderMoranta26Empty();
  await loadMoranta26Catalog();
}

function collectMoranta26Elements() {
  [
    "m26-status",
    "m26-cluster",
    "m26-lambda",
    "m26-pipeline",
    "m26-sector",
    "m26-category",
    "m26-quality",
    "m26-selected-filter",
    "m26-prob-threshold",
    "m26-include-ignored",
    "m26-require-lit",
    "m26-search",
    "m26-search-button",
    "m26-clear-search",
    "m26-load",
    "m26-clear-cache",
    "m26-clear-cache-status",
    "m26-summary",
    "m26-plot",
    "m26-plot-loader",
    "m26-star-summary",
    "m26-dataset-select",
    "m26-phase-source",
    "m26-lightcurve-source",
    "m26-table",
    "m26-lightcurve-plot",
    "m26-lightcurve-loader",
    "m26-phase-plot",
    "m26-periodogram-plot",
  ].forEach((id) => {
    m26El[id] = document.getElementById(id);
  });
}

function readMoranta26UrlState() {
  const params = new URLSearchParams(window.location.search);
  m26State.initial.cluster = params.get("cluster") || "";
  m26State.initial.sourceId = normalizeMoranta26SourceId(params.get("gaia_dr3") || params.get("source_id") || "");
  m26State.initial.lambdas = parseIntegerList(params.get("m") || params.get("lambda") || params.get("lambdas"));
  m26El["m26-include-ignored"].checked = !asFalse(params.get("include_ignored"));
  m26El["m26-require-lit"].checked = asBool(params.get("require_lit") || params.get("lit_only"));
  const threshold = finiteNumber(params.get("prob_threshold")) ? Number(params.get("prob_threshold")) : 0.70;
  m26El["m26-prob-threshold"].value = String(Math.min(Math.max(threshold, 0), 1));
  if (m26State.initial.sourceId) m26El["m26-search"].value = m26State.initial.sourceId;
}

function bindMoranta26Controls() {
  for (const id of [
    "m26-cluster",
    "m26-lambda",
    "m26-pipeline",
    "m26-sector",
    "m26-category",
    "m26-quality",
    "m26-selected-filter",
    "m26-prob-threshold",
    "m26-include-ignored",
    "m26-require-lit",
  ]) {
    m26El[id].addEventListener("change", () => {
      updateMoranta26Url();
      renderMoranta26CatalogView();
    });
  }
  m26El["m26-search-button"].addEventListener("click", () => selectMoranta26SearchResult());
  m26El["m26-search"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") selectMoranta26SearchResult();
  });
  m26El["m26-clear-search"].addEventListener("click", () => {
    m26State.selectedStarKey = "";
    m26El["m26-search"].value = "";
    m26State.lightcurvePayload = null;
    renderMoranta26CatalogView();
  });
  m26El["m26-load"].addEventListener("click", () => loadMoranta26Catalog({ force: true }));
  m26El["m26-clear-cache"].addEventListener("click", clearMoranta26Cache);
  m26El["m26-dataset-select"].addEventListener("change", () => {
    const value = m26El["m26-dataset-select"].value;
    m26State.selectedPhotseqid = value ? Number(value) : null;
    m26State.lightcurvePayload = null;
    updateMoranta26PhaseOptions();
    loadMoranta26Lightcurve();
  });
  m26El["m26-phase-source"].addEventListener("change", () => renderMoranta26LightcurveView());
}

async function loadMoranta26Catalog() {
  const token = (m26State.loadToken += 1);
  setMoranta26Status("Loading Mora26 rotation rows", "loading");
  setMoranta26PlotLoading(true);
  try {
    const params = connectionParams();
    const payload = await fetchJsonUrl(m26AppUrl(`api/moranta26-rotation/catalog?${params.toString()}`));
    if (token !== m26State.loadToken) return;
    if (!payload.ok) throw new Error(payload.error || "Catalog load failed");
    m26State.rows = Array.isArray(payload.rows) ? payload.rows : [];
    m26State.options = payload.options || {};
    populateMoranta26Controls();
    setMoranta26Status(`Loaded ${m26State.rows.length.toLocaleString()} Mora26 rows`, "");
    if (m26State.initial.sourceId) {
      selectMoranta26SourceId(m26State.initial.sourceId, { quiet: true });
      m26State.initial.sourceId = "";
    }
    renderMoranta26CatalogView();
  } catch (error) {
    setMoranta26Status(error.message, "error");
    m26El["m26-summary"].textContent = error.message;
    renderMoranta26Empty(error.message);
  } finally {
    setMoranta26PlotLoading(false);
  }
}

function populateMoranta26Controls() {
  const clusters = m26State.options.clusters?.length ? m26State.options.clusters : ["THA", "IC2602", "PERI", "GRX"];
  setSelectOptions(m26El["m26-cluster"], clusters, m26State.initial.cluster && clusters.includes(m26State.initial.cluster) ? [m26State.initial.cluster] : [clusters[0]], String);
  const lambdas = (m26State.options.lambdas?.length ? m26State.options.lambdas : m26DefaultLambdas).map(Number);
  const selectedLambdas = m26State.initial.lambdas?.length
    ? m26State.initial.lambdas.filter((value) => lambdas.includes(value))
    : lambdas.filter((value) => m26DefaultLambdas.includes(value));
  setSelectOptions(m26El["m26-lambda"], lambdas, selectedLambdas.length ? selectedLambdas : lambdas, (value) => `m = ${value}`);
  setSelectOptions(m26El["m26-pipeline"], m26State.options.pipelines || [], m26State.options.pipelines || [], String);
  setSelectOptions(m26El["m26-sector"], m26State.options.sectors || [], m26State.options.sectors || [], (value) => `Sector ${value}`);
  setSelectOptions(m26El["m26-category"], m26State.options.categories || [], m26State.options.categories || [], String);
  setSelectOptions(m26El["m26-quality"], m26State.options.qualities || [], m26State.options.qualities || [], String);
  m26State.initial.lambdas = [];
}

function renderMoranta26CatalogView() {
  const rows = filteredMoranta26Rows();
  m26State.filteredRows = rows;
  if (m26State.selectedStarKey && !rows.some((row) => row.star_key === m26State.selectedStarKey)) {
    const starRows = m26State.rows.filter((row) => row.star_key === m26State.selectedStarKey);
    if (!starRows.length) m26State.selectedStarKey = "";
  }
  renderMoranta26Summary(rows);
  renderMoranta26PeriodComparison(rows);
  renderMoranta26StarPanel();
}

function filteredMoranta26Rows() {
  const cluster = m26El["m26-cluster"].value;
  const selectedLambdas = selectedNumericValues(m26El["m26-lambda"]);
  const selectedPipelines = selectedStringValues(m26El["m26-pipeline"]);
  const selectedSectors = selectedNumericValues(m26El["m26-sector"]);
  const selectedCategories = selectedStringValues(m26El["m26-category"]);
  const selectedQualities = selectedStringValues(m26El["m26-quality"]);
  const selectedState = m26El["m26-selected-filter"].value;
  const includeIgnored = m26El["m26-include-ignored"].checked;
  const requireLit = m26El["m26-require-lit"].checked;
  return m26State.rows.filter((row) => {
    if (cluster && String(row.cluster || "") !== cluster) return false;
    if (selectedLambdas.length && !selectedLambdas.includes(Number(row.m))) return false;
    if (selectedPipelines.length && !selectedPipelines.includes(String(row.pipeline || ""))) return false;
    if (selectedSectors.length && !selectedSectors.includes(Number(row.sector))) return false;
    if (selectedCategories.length && !selectedCategories.includes(String(row.category || ""))) return false;
    if (selectedQualities.length && !selectedQualities.includes(String(row.quality || ""))) return false;
    if (selectedState === "selected" && Number(row.selected || 0) !== 1) return false;
    if (selectedState === "unselected" && Number(row.selected || 0) === 1) return false;
    if (!includeIgnored && Number(row.ignored || 0) === 1) return false;
    if (requireLit && !hasLiteraturePeriod(row)) return false;
    return true;
  });
}

function renderMoranta26Summary(rows) {
  const plotRows = rows.filter((row) => hasLiteraturePeriod(row) && finiteNumber(row.prot));
  const ignoredRows = rows.filter((row) => Number(row.ignored || 0) === 1).length;
  const stars = new Set(rows.map((row) => row.star_key).filter(Boolean)).size;
  const lightCurves = new Set(rows.map((row) => row.source_moca_tplcid).filter((value) => value !== null && value !== undefined)).size;
  const threshold = moranta26Threshold();
  const passing = plotRows.filter((row) => finiteNumber(row.prob_all) && Number(row.prob_all) >= threshold).length;
  m26El["m26-summary"].innerHTML = [
    `<strong>${rows.length.toLocaleString()}</strong> displayed Mora26 period rows`,
    `<strong>${stars.toLocaleString()}</strong> objects`,
    `<strong>${plotRows.length.toLocaleString()}</strong> rows with literature periods`,
    `<strong>${passing.toLocaleString()}</strong> rows at prob_all >= ${formatNumber(threshold, 2)}`,
    `<strong>${ignoredRows.toLocaleString()}</strong> DB ignored rows included`,
    `<strong>${lightCurves.toLocaleString()}</strong> linked light curves`,
  ].join(" | ");
}

function renderMoranta26PeriodComparison(rows) {
  const plotRows = rows.filter((row) => hasLiteraturePeriod(row) && finiteNumber(row.prot));
  if (!plotRows.length) {
    Plotly.react(m26El["m26-plot"], [], emptyPlotLayout("No literature-period comparison rows match the current filters."), plotConfig("moranta26_rotation_empty"));
    return;
  }
  const threshold = moranta26Threshold();
  const lambdas = selectedNumericValues(m26El["m26-lambda"]).length
    ? selectedNumericValues(m26El["m26-lambda"])
    : uniqueSorted(plotRows.map((row) => row.m).filter((value) => value !== null && value !== undefined).map(Number));
  const lambdaValues = lambdas.filter((value) => plotRows.some((row) => Number(row.m) === Number(value)));
  const cols = lambdaValues.length <= 4 ? 2 : 3;
  const nCols = Math.max(1, Math.min(cols, lambdaValues.length));
  const nRows = Math.max(1, Math.ceil(lambdaValues.length / nCols));
  const plotHeight = Math.max(520, 420 * nRows);
  m26El["m26-plot"].style.height = `${plotHeight}px`;
  m26El["m26-plot"].parentElement.style.minHeight = `${plotHeight}px`;
  const domains = subplotDomains(nRows, nCols);
  const axisLimit = moranta26AxisLimit(plotRows);
  const traces = [];
  const layout = {
    template: "plotly_white",
    height: plotHeight,
    margin: { l: 48, r: 42, t: 76, b: 48 },
    paper_bgcolor: "#f5f6f8",
    plot_bgcolor: "#ffffff",
    title: { text: "Literature vs detected rotation periods", x: 0.01, xanchor: "left" },
    hovermode: "closest",
    clickmode: "event+select",
    annotations: [],
    showlegend: true,
    legend: { orientation: "h", y: 1.06, yanchor: "bottom", x: 1, xanchor: "right" },
  };
  lambdaValues.forEach((lambdaValue, index) => {
    const axisName = index === 0 ? "" : String(index + 1);
    const xaxisKey = `xaxis${axisName}`;
    const yaxisKey = `yaxis${axisName}`;
    const xref = index === 0 ? "x" : `x${index + 1}`;
    const yref = index === 0 ? "y" : `y${index + 1}`;
    const domain = domains[index];
    layout[xaxisKey] = {
      title: "Literature P (days)",
      range: [0, axisLimit],
      domain: domain.x,
      showline: true,
      mirror: true,
      ticks: "outside",
    };
    layout[yaxisKey] = {
      title: "Detected P (days)",
      range: [0, axisLimit],
      domain: domain.y,
      showline: true,
      mirror: true,
      ticks: "outside",
      scaleanchor: xref,
      scaleratio: 1,
    };
    layout.annotations.push({
      text: `m = ${lambdaValue}`,
      xref: "paper",
      yref: "paper",
      x: (domain.x[0] + domain.x[1]) / 2,
      y: domain.y[1] + 0.035,
      showarrow: false,
      font: { size: 13 },
    });
    const lineX = [0, axisLimit];
    traces.push(lineTrace(lineX, lineX, xref, yref, index === 0 ? "1:1" : undefined, "#1f2933", "solid"));
    traces.push(lineTrace(lineX, lineX.map((value) => value * (1 + m26LiteratureTolerance)), xref, yref, index === 0 ? "15% band" : undefined, "#9aa3ad", "dash"));
    traces.push(lineTrace(lineX, lineX.map((value) => value * (1 - m26LiteratureTolerance)), xref, yref, undefined, "#9aa3ad", "dash"));
    const lambdaRows = plotRows.filter((row) => Number(row.m) === Number(lambdaValue));
    const belowRows = lambdaRows.filter((row) => !finiteNumber(row.prob_all) || Number(row.prob_all) < threshold);
    const passingRows = lambdaRows.filter((row) => finiteNumber(row.prob_all) && Number(row.prob_all) >= threshold);
    if (belowRows.length) {
      traces.push(markerTrace(belowRows, xref, yref, `Below cut${index === 0 ? "" : ` m=${lambdaValue}`}`, {
        size: 6,
        color: "rgba(126,132,140,0.55)",
        symbol: belowRows.map((row) => Number(row.ignored || 0) ? "x" : "circle-open"),
        line: { color: "rgba(72,78,88,0.8)", width: 0.8 },
      }, index === 0));
    }
    if (passingRows.length) {
      traces.push(markerTrace(passingRows, xref, yref, `Mora26 rows${index === 0 ? "" : ` m=${lambdaValue}`}`, {
        size: 8,
        color: passingRows.map((row) => Number(row.prob_all)),
        colorscale: "Viridis",
        cmin: threshold,
        cmax: 1,
        showscale: index === 0,
        colorbar: index === 0 ? { title: "prob_all", len: 0.72, thickness: 14 } : undefined,
        symbol: passingRows.map((row) => Number(row.ignored || 0) ? "x" : "circle"),
        line: { color: "rgba(20,37,58,0.35)", width: 0.7 },
      }, index === 0));
    }
    const revisedRows = lambdaRows.filter((row) => finiteNumber(row.revised) && Number(row.revised) > 0);
    if (revisedRows.length) {
      traces.push({
        x: revisedRows.map((row) => row.lit_prot),
        y: revisedRows.map((row) => row.revised),
        mode: "markers",
        type: "scatter",
        xaxis: xref,
        yaxis: yref,
        customdata: revisedRows.map(moranta26CustomData),
        text: revisedRows.map(moranta26HoverText),
        hovertemplate: "%{text}<br>Revised P = %{y:.5f} d<extra></extra>",
        marker: { size: 10, color: m26RevisedColor, symbol: "diamond", line: { color: "#ffffff", width: 1 } },
        name: "Revised period",
        legendgroup: "revised",
        showlegend: index === 0,
      });
    }
    const selectedRows = m26State.selectedStarKey
      ? lambdaRows.filter((row) => row.star_key === m26State.selectedStarKey)
      : [];
    if (selectedRows.length) {
      traces.push({
        x: selectedRows.map((row) => row.lit_prot),
        y: selectedRows.map((row) => row.prot),
        mode: "markers",
        type: "scatter",
        xaxis: xref,
        yaxis: yref,
        customdata: selectedRows.map(moranta26CustomData),
        text: selectedRows.map(moranta26HoverText),
        hovertemplate: "%{text}<extra></extra>",
        marker: { size: 16, color: "#111827", symbol: "diamond-open", line: { color: "#111827", width: 2.8 } },
        name: "Selected object",
        legendgroup: "selected",
        showlegend: index === 0,
      });
    }
  });
  Plotly.react(m26El["m26-plot"], traces, layout, plotConfig("moranta26_rotation_comparison")).then(bindMoranta26ComparisonClick);
}

function renderMoranta26StarPanel() {
  const starRows = selectedMoranta26StarRows();
  if (!starRows.length) {
    m26El["m26-star-summary"].textContent = "Select a point or search for a Gaia DR3 source ID.";
    m26El["m26-dataset-select"].innerHTML = "";
    m26El["m26-phase-source"].innerHTML = "";
    m26El["m26-lightcurve-source"].textContent = "";
    m26El["m26-table"].innerHTML = "";
    renderMoranta26LightcurveEmpty("Select a star to inspect the linked TESS light curves.");
    return;
  }
  const first = starRows[0];
  const lit = starRows.find((row) => hasLiteraturePeriod(row))?.lit_prot;
  const ignoredCount = starRows.filter((row) => Number(row.ignored || 0) === 1).length;
  m26El["m26-star-summary"].innerHTML = `
    <strong>${escapeHtml(first.source_id ? `Gaia DR3 ${first.source_id}` : first.star_key)}</strong>
    <span>moca_oid ${escapeHtml(first.moca_oid ?? "N/A")}</span>
    <span>Literature P ${lit ? `${formatNumber(lit, 5)} d` : "N/A"}</span>
    <span>${starRows.length} Mora26 rows; ${ignoredCount} ignored</span>
    ${first.report_url ? `<a href="${first.report_url}" target="_blank" rel="noopener">Open MOCAdb report</a>` : ""}
  `;
  renderMoranta26StarTable(starRows);
  updateMoranta26DatasetOptions(starRows);
  updateMoranta26PhaseOptions();
  if (m26State.selectedPhotseqid) loadMoranta26Lightcurve();
}

function selectedMoranta26StarRows() {
  if (!m26State.selectedStarKey) return [];
  const cluster = m26El["m26-cluster"].value;
  return m26State.rows
    .filter((row) => row.star_key === m26State.selectedStarKey && (!cluster || row.cluster === cluster))
    .sort(moranta26RowSort);
}

function updateMoranta26DatasetOptions(starRows) {
  const byPhotseqid = new Map();
  starRows.forEach((row) => {
    if (row.source_moca_tplcid === null || row.source_moca_tplcid === undefined) return;
    const key = String(row.source_moca_tplcid);
    const item = byPhotseqid.get(key) || { photseqid: Number(row.source_moca_tplcid), rows: [] };
    item.rows.push(row);
    byPhotseqid.set(key, item);
  });
  const options = [...byPhotseqid.values()].sort((a, b) => {
    const aRow = bestMoranta26Row(a.rows);
    const bRow = bestMoranta26Row(b.rows);
    return (Number(aRow?.sector) || 0) - (Number(bRow?.sector) || 0)
      || String(aRow?.pipeline || "").localeCompare(String(bRow?.pipeline || ""))
      || Number(a.photseqid) - Number(b.photseqid);
  });
  if (!options.length) {
    m26State.selectedPhotseqid = null;
    m26El["m26-dataset-select"].innerHTML = "";
    renderMoranta26LightcurveEmpty("No source_moca_tplcid light-curve link is available for this selection.");
    return;
  }
  if (!m26State.selectedPhotseqid || !options.some((option) => Number(option.photseqid) === Number(m26State.selectedPhotseqid))) {
    m26State.selectedPhotseqid = Number(options[0].photseqid);
    m26State.lightcurvePayload = null;
  }
  m26El["m26-dataset-select"].innerHTML = options.map((option) => {
    const row = bestMoranta26Row(option.rows);
    const mValues = uniqueSorted(option.rows.map((item) => item.m).filter((value) => value !== null && value !== undefined).map(Number)).join(", ");
    const label = `Sector ${row?.sector ?? "N/A"} | ${row?.pipeline || "N/A"} | photseqid ${option.photseqid} | m ${mValues}`;
    return `<option value="${option.photseqid}" ${Number(option.photseqid) === Number(m26State.selectedPhotseqid) ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
}

function updateMoranta26PhaseOptions(preferredValue) {
  const rows = selectedMoranta26StarRows();
  const currentRows = rows.filter((row) => Number(row.source_moca_tplcid) === Number(m26State.selectedPhotseqid));
  const sourceRows = currentRows.length ? currentRows : rows;
  const options = [];
  const revised = sourceRows.find((row) => finiteNumber(row.revised) && Number(row.revised) > 0);
  if (revised) options.push({ value: "revised", label: `Revised period: ${formatNumber(revised.revised, 5)} d` });
  sourceRows
    .filter((row) => finiteNumber(row.prot))
    .sort((a, b) => Number(a.m || 0) - Number(b.m || 0) || Number(b.prob_all || -1) - Number(a.prob_all || -1))
    .forEach((row) => {
      const value = `prot:${row.prot_id}`;
      if (!options.some((option) => option.value === value)) {
        options.push({ value, label: `m=${row.m} detection: ${formatNumber(row.prot, 5)} d` });
      }
    });
  const lit = sourceRows.find((row) => hasLiteraturePeriod(row));
  if (lit) options.push({ value: "literature", label: `Literature period: ${formatNumber(lit.lit_prot, 5)} d` });
  if (finiteNumber(m26State.customPeriod) && Number(m26State.customPeriod) > 0) {
    options.push({ value: "custom", label: `Clicked LS period: ${formatNumber(m26State.customPeriod, 5)} d` });
  }
  const current = preferredValue || m26El["m26-phase-source"].value;
  const defaultValue = options.find((option) => option.value === current)?.value
    || options.find((option) => option.value.startsWith("prot:"))?.value
    || options[0]?.value
    || "";
  m26El["m26-phase-source"].innerHTML = options.map((option) => (
    `<option value="${escapeHtml(option.value)}" ${option.value === defaultValue ? "selected" : ""}>${escapeHtml(option.label)}</option>`
  )).join("");
}

async function loadMoranta26Lightcurve() {
  if (!m26State.selectedPhotseqid) return;
  const photseqid = Number(m26State.selectedPhotseqid);
  setMoranta26LightcurveLoading(true);
  try {
    const params = connectionParams();
    const payload = await fetchJsonUrl(m26AppUrl(`api/moranta26-rotation/lightcurve/${photseqid}?${params.toString()}`));
    if (!payload.ok) throw new Error(payload.error || "Light-curve load failed");
    if (Number(payload.photseqid) !== photseqid) return;
    m26State.lightcurvePayload = payload;
    renderMoranta26LightcurveView();
  } catch (error) {
    m26El["m26-lightcurve-source"].textContent = error.message;
    renderMoranta26LightcurveEmpty(error.message);
  } finally {
    setMoranta26LightcurveLoading(false);
  }
}

function renderMoranta26LightcurveView() {
  const payload = m26State.lightcurvePayload;
  if (!payload || Number(payload.photseqid) !== Number(m26State.selectedPhotseqid)) {
    renderMoranta26LightcurveEmpty("Select a sector and pipeline to load its linked light curve.");
    return;
  }
  const rows = Array.isArray(payload.rows) ? payload.rows : [];
  const currentRow = currentMoranta26PeriodRow();
  const phase = resolveMoranta26PhasePeriod();
  const header = payload.header || {};
  m26El["m26-lightcurve-source"].textContent = rows.length
    ? `Light curve ${payload.photseqid}: ${rows.length.toLocaleString()} points; ${header.flux_units || "relative flux"}; ${header.original_filename || ""}`
    : (payload.meta?.header_found ? "No non-null flux points available for this light-curve header." : "No light-curve header found.");
  if (!rows.length) {
    renderMoranta26LightcurveEmpty("No non-null flux points available.");
    return;
  }
  const lightTrace = {
    x: rows.map((row) => row.btjd),
    y: rows.map((row) => row.flux),
    type: "scattergl",
    mode: "markers",
    marker: { size: 4, color: "#1F6FEB", opacity: 0.8 },
    hovertemplate: "BTJD %{x:.5f}<br>Flux %{y:.6f}<extra></extra>",
  };
  Plotly.react(m26El["m26-lightcurve-plot"], [lightTrace], {
    template: "plotly_white",
    height: 360,
    margin: { l: 58, r: 24, t: 46, b: 52 },
    title: `Light curve: photseqid ${payload.photseqid}`,
    xaxis: { title: "TESS BTJD" },
    yaxis: { title: header.flux_units || "relative flux" },
  }, plotConfig("moranta26_lightcurve"));

  if (phase.period) {
    const phaseX = rows.map((row) => ((Number(row.btjd) / phase.period) % 1 + 1) % 1);
    const x = phaseX.concat(phaseX.map((value) => value + 1));
    const y = rows.map((row) => row.flux).concat(rows.map((row) => row.flux));
    Plotly.react(m26El["m26-phase-plot"], [{
      x,
      y,
      type: "scattergl",
      mode: "markers",
      marker: { size: 4, color: "#0B7285", opacity: 0.82 },
      hovertemplate: "Phase %{x:.4f}<br>Flux %{y:.6f}<extra></extra>",
    }], {
      template: "plotly_white",
      height: 330,
      margin: { l: 54, r: 22, t: 48, b: 48 },
      title: `Phase folded on ${phase.label}: ${formatNumber(phase.period, 5)} d`,
      xaxis: { title: "Phase", range: [0, 2] },
      yaxis: { title: header.flux_units || "relative flux" },
    }, plotConfig("moranta26_phase"));
  } else {
    Plotly.react(m26El["m26-phase-plot"], [], emptyPlotLayout("No valid phase period is available."), plotConfig("moranta26_phase_empty"));
  }

  const periodogram = Array.isArray(payload.periodogram) ? payload.periodogram : [];
  const shapes = [];
  const annotations = [];
  addPeriodMarker(shapes, annotations, currentRow?.lit_prot, "#2B8A3E", "Literature");
  addPeriodMarker(shapes, annotations, currentRow?.revised, m26RevisedColor, "Revised");
  addPeriodMarker(shapes, annotations, phase.period, "#C92A2A", phase.label || "Phase");
  Plotly.react(m26El["m26-periodogram-plot"], periodogram.length ? [{
    x: periodogram.map((row) => row.period),
    y: periodogram.map((row) => row.power),
    type: "scatter",
    mode: "lines",
    line: { color: "#444C99", width: 1.6 },
    hovertemplate: "Period %{x:.5f} d<br>Power %{y:.5f}<extra></extra>",
  }] : [], {
    template: "plotly_white",
    height: 330,
    margin: { l: 54, r: 22, t: 48, b: 48 },
    title: "Lomb-Scargle periodogram",
    xaxis: { title: "Period (days)", range: [m26MinPeriodDays, m26MaxPeriodDays] },
    yaxis: { title: "Power" },
    shapes,
    annotations,
  }, plotConfig("moranta26_periodogram")).then(bindMoranta26PeriodogramClick);
}

function renderMoranta26StarTable(rows) {
  const sorted = [...rows].sort(moranta26RowSort);
  const body = sorted.map((row) => `
    <tr class="${Number(row.ignored || 0) ? "is-muted-row" : ""}">
      <td>${escapeHtml(row.m ?? "")}</td>
      <td>${escapeHtml(row.pipeline || "")}</td>
      <td>${escapeHtml(row.sector ?? "")}</td>
      <td>${formatMaybe(row.prot, 5)}</td>
      <td>${formatMaybe(row.revised, 5)}</td>
      <td>${formatMaybe(row.lit_prot, 5)}</td>
      <td>${formatMaybe(row.prob_all, 3)}</td>
      <td>${escapeHtml(row.category || "")}</td>
      <td>${escapeHtml(row.quality || "")}</td>
      <td>${Number(row.selected || 0) ? "yes" : "no"}</td>
      <td>${Number(row.ignored || 0) ? "yes" : "no"}</td>
      <td>${escapeHtml(row.source_moca_tplcid ?? "")}</td>
    </tr>
  `).join("");
  m26El["m26-table"].innerHTML = `
    <table>
      <thead>
        <tr>
          <th>m</th><th>Pipeline</th><th>Sector</th><th>P detected</th><th>P revised</th><th>P literature</th>
          <th>prob_all</th><th>Category</th><th>Quality</th><th>Selected</th><th>Ignored</th><th>photseqid</th>
        </tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
  `;
}

function selectMoranta26SearchResult() {
  const normalized = normalizeMoranta26SourceId(m26El["m26-search"].value);
  if (!normalized) return;
  if (!selectMoranta26SourceId(normalized)) {
    setMoranta26Status(`Gaia DR3 ${normalized} was not found in the loaded Mora26 rows`, "error");
  }
}

function selectMoranta26SourceId(sourceId, options = {}) {
  const normalized = normalizeMoranta26SourceId(sourceId);
  if (!normalized) return false;
  let match = m26State.rows.find((row) => normalizeMoranta26SourceId(row.source_id) === normalized && row.cluster === m26El["m26-cluster"].value);
  if (!match) {
    match = m26State.rows.find((row) => normalizeMoranta26SourceId(row.source_id) === normalized);
    if (match?.cluster) m26El["m26-cluster"].value = match.cluster;
  }
  if (!match) return false;
  m26State.selectedStarKey = match.star_key;
  m26State.selectedPhotseqid = match.source_moca_tplcid || null;
  m26State.lightcurvePayload = null;
  m26El["m26-search"].value = normalized;
  if (!options.quiet) setMoranta26Status(`Selected Gaia DR3 ${normalized}`, "");
  renderMoranta26CatalogView();
  return true;
}

function currentMoranta26PeriodRow() {
  const rows = selectedMoranta26StarRows().filter((row) => Number(row.source_moca_tplcid) === Number(m26State.selectedPhotseqid));
  return bestMoranta26Row(rows) || bestMoranta26Row(selectedMoranta26StarRows());
}

function resolveMoranta26PhasePeriod() {
  const value = m26El["m26-phase-source"].value;
  const rows = selectedMoranta26StarRows();
  const currentRows = rows.filter((row) => Number(row.source_moca_tplcid) === Number(m26State.selectedPhotseqid));
  const sourceRows = currentRows.length ? currentRows : rows;
  if (value === "custom" && finiteNumber(m26State.customPeriod) && Number(m26State.customPeriod) > 0) {
    return { period: Number(m26State.customPeriod), label: "clicked LS period" };
  }
  if (value === "revised") {
    const row = sourceRows.find((item) => finiteNumber(item.revised) && Number(item.revised) > 0);
    if (row) return { period: Number(row.revised), label: "revised period" };
  }
  if (value === "literature") {
    const row = sourceRows.find(hasLiteraturePeriod);
    if (row) return { period: Number(row.lit_prot), label: "literature period" };
  }
  if (value?.startsWith("prot:")) {
    const protId = Number(value.slice(5));
    const row = sourceRows.find((item) => Number(item.prot_id) === protId);
    if (row && finiteNumber(row.prot)) return { period: Number(row.prot), label: `m=${row.m} detection` };
  }
  const fallback = bestMoranta26Row(sourceRows);
  return fallback && finiteNumber(fallback.prot)
    ? { period: Number(fallback.prot), label: `m=${fallback.m} detection` }
    : { period: null, label: "" };
}

function bestMoranta26Row(rows) {
  if (!rows?.length) return null;
  return [...rows].sort((a, b) => Number(b.prob_all ?? -1) - Number(a.prob_all ?? -1) || Number(a.m ?? 999) - Number(b.m ?? 999))[0];
}

function moranta26RowSort(a, b) {
  return Number(a.m ?? 999) - Number(b.m ?? 999)
    || Number(a.sector ?? 999) - Number(b.sector ?? 999)
    || String(a.pipeline || "").localeCompare(String(b.pipeline || ""))
    || Number(b.prob_all ?? -1) - Number(a.prob_all ?? -1);
}

function markerTrace(rows, xaxis, yaxis, name, marker, showlegend) {
  return {
    x: rows.map((row) => row.lit_prot),
    y: rows.map((row) => row.prot),
    type: "scatter",
    mode: "markers",
    xaxis,
    yaxis,
    customdata: rows.map(moranta26CustomData),
    text: rows.map(moranta26HoverText),
    hovertemplate: "%{text}<extra></extra>",
    marker,
    name,
    showlegend,
  };
}

function lineTrace(x, y, xaxis, yaxis, name, color, dash) {
  return {
    x,
    y,
    type: "scatter",
    mode: "lines",
    xaxis,
    yaxis,
    line: { color, width: 1.15, dash },
    hoverinfo: "skip",
    name,
    showlegend: Boolean(name),
  };
}

function moranta26CustomData(row) {
  return [row.star_key, row.prot_id, row.moca_oid, row.source_id, row.source_moca_tplcid, row.m, row.pipeline, row.sector];
}

function moranta26HoverText(row) {
  return [
    row.source_id ? `Gaia DR3 ${escapeHtml(row.source_id)}` : "Gaia DR3 N/A",
    `moca_oid ${escapeHtml(row.moca_oid ?? "N/A")}`,
    `m = ${escapeHtml(row.m ?? "N/A")} | ${escapeHtml(row.pipeline || "N/A")} S${escapeHtml(row.sector ?? "N/A")}`,
    `photseqid ${escapeHtml(row.source_moca_tplcid ?? "N/A")}`,
    `Lit P = ${formatMaybe(row.lit_prot, 5)} d`,
    `Detected P = ${formatMaybe(row.prot, 5)} d`,
    `prob_all = ${formatMaybe(row.prob_all, 4)}`,
    `category = ${escapeHtml(row.category || "N/A")}; quality = ${escapeHtml(row.quality || "N/A")}`,
    Number(row.ignored || 0) ? "DB ignored row" : "DB active row",
  ].join("<br>");
}

function subplotDomains(rows, cols) {
  const xGap = cols > 1 ? 0.07 : 0;
  const yGap = rows > 1 ? 0.12 : 0;
  const width = (1 - xGap * (cols - 1)) / cols;
  const height = (1 - yGap * (rows - 1)) / rows;
  const domains = [];
  for (let index = 0; index < rows * cols; index += 1) {
    const row = Math.floor(index / cols);
    const col = index % cols;
    const x0 = col * (width + xGap);
    const y1 = 1 - row * (height + yGap);
    domains.push({ x: [x0, x0 + width], y: [y1 - height, y1] });
  }
  return domains;
}

function moranta26AxisLimit(rows) {
  const values = [];
  rows.forEach((row) => {
    if (finiteNumber(row.lit_prot)) values.push(Number(row.lit_prot));
    if (finiteNumber(row.prot)) values.push(Number(row.prot));
    if (finiteNumber(row.revised)) values.push(Number(row.revised));
  });
  if (!values.length) return 5;
  return Math.min(m26MaxPeriodDays, Math.max(3, Math.max(...values) * 1.08));
}

function addPeriodMarker(shapes, annotations, value, color, label) {
  if (!finiteNumber(value) || Number(value) <= 0) return;
  const x = Number(value);
  shapes.push({
    type: "line",
    xref: "x",
    yref: "paper",
    x0: x,
    x1: x,
    y0: 0,
    y1: 1,
    line: { color, width: 1.2, dash: "dot" },
  });
  annotations.push({
    x,
    y: 1,
    xref: "x",
    yref: "paper",
    text: label,
    showarrow: false,
    yanchor: "bottom",
    font: { color, size: 10 },
  });
}

function bindMoranta26PeriodogramClick() {
  if (m26El["m26-periodogram-plot"]._m26ClickBound) return;
  m26El["m26-periodogram-plot"]._m26ClickBound = true;
  m26El["m26-periodogram-plot"].on("plotly_click", (event) => {
    const xValue = event?.points?.[0]?.x;
    if (!finiteNumber(xValue) || Number(xValue) <= 0) return;
    m26State.customPeriod = Number(xValue);
    updateMoranta26PhaseOptions("custom");
    renderMoranta26LightcurveView();
  });
}

function bindMoranta26ComparisonClick() {
  if (m26El["m26-plot"]._m26ClickBound) return;
  m26El["m26-plot"]._m26ClickBound = true;
  m26El["m26-plot"].on("plotly_click", (event) => {
    const custom = event?.points?.[0]?.customdata;
    if (!custom || !custom[0]) return;
    m26State.selectedStarKey = String(custom[0]);
    m26State.selectedPhotseqid = custom[4] ? Number(custom[4]) : null;
    m26State.lightcurvePayload = null;
    renderMoranta26CatalogView();
  });
}

function renderMoranta26Empty(message = "No Mora26 rotation rows are loaded.") {
  const layout = emptyPlotLayout(message);
  Plotly.react(m26El["m26-plot"], [], layout, plotConfig("moranta26_empty"));
  renderMoranta26LightcurveEmpty("Select a star to inspect the linked TESS light curves.");
}

function renderMoranta26LightcurveEmpty(message) {
  Plotly.react(m26El["m26-lightcurve-plot"], [], emptyPlotLayout(message), plotConfig("moranta26_lightcurve_empty"));
  Plotly.react(m26El["m26-phase-plot"], [], emptyPlotLayout(message), plotConfig("moranta26_phase_empty"));
  Plotly.react(m26El["m26-periodogram-plot"], [], emptyPlotLayout(message), plotConfig("moranta26_periodogram_empty"));
}

function emptyPlotLayout(message) {
  return {
    template: "plotly_white",
    height: 330,
    xaxis: { visible: false },
    yaxis: { visible: false },
    annotations: [{
      text: message,
      xref: "paper",
      yref: "paper",
      x: 0.5,
      y: 0.5,
      showarrow: false,
      font: { size: 15, color: "#5f5864" },
    }],
  };
}

async function clearMoranta26Cache() {
  m26El["m26-clear-cache"].disabled = true;
  m26El["m26-clear-cache-status"].textContent = "Clearing...";
  try {
    const response = await fetch(m26AppUrl("api/moranta26-rotation/cache/clear"), { method: "POST" });
    const payload = await response.json();
    if (!payload.ok) throw new Error(payload.error || "cache clear failed");
    m26El["m26-clear-cache-status"].textContent = `Cleared ${payload.cleared?.moranta26Rotation ?? 0} cached entries.`;
    await loadMoranta26Catalog();
  } catch (error) {
    m26El["m26-clear-cache-status"].textContent = error.message;
  } finally {
    m26El["m26-clear-cache"].disabled = false;
  }
}

function updateMoranta26Url() {
  const params = new URLSearchParams(window.location.search);
  params.set("cluster", m26El["m26-cluster"].value || "");
  const lambdas = selectedNumericValues(m26El["m26-lambda"]);
  if (lambdas.length) params.set("m", lambdas.join(","));
  else params.delete("m");
  if (!m26El["m26-include-ignored"].checked) params.set("include_ignored", "0");
  else params.delete("include_ignored");
  if (m26El["m26-require-lit"].checked) params.set("require_lit", "1");
  else params.delete("require_lit");
  if (m26El["m26-search"].value.trim()) params.set("source_id", normalizeMoranta26SourceId(m26El["m26-search"].value));
  else params.delete("source_id");
  const threshold = m26El["m26-prob-threshold"].value;
  if (threshold && threshold !== "0.70") params.set("prob_threshold", threshold);
  else params.delete("prob_threshold");
  window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}

function connectionParams() {
  const source = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "port", "user", "pwd", "dbase", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  return params;
}

function setSelectOptions(select, values, selectedValues, labelFn) {
  const selected = new Set((selectedValues || []).map((value) => String(value)));
  select.innerHTML = (values || []).map((value) => {
    const valueText = String(value);
    return `<option value="${escapeHtml(valueText)}" ${selected.has(valueText) ? "selected" : ""}>${escapeHtml(labelFn(value))}</option>`;
  }).join("");
}

function selectedStringValues(select) {
  return [...select.selectedOptions].map((option) => String(option.value));
}

function selectedNumericValues(select) {
  return [...select.selectedOptions].map((option) => Number(option.value)).filter((value) => Number.isFinite(value));
}

function uniqueSorted(values) {
  return [...new Set(values)].sort((a, b) => Number(a) - Number(b));
}

function normalizeMoranta26SourceId(value) {
  return String(value || "").replace(/Gaia\s*DR3/gi, "").replace(/\D/g, "");
}

function hasLiteraturePeriod(row) {
  return finiteNumber(row?.lit_prot) && Number(row.lit_prot) > 0;
}

function moranta26Threshold() {
  const value = Number(m26El["m26-prob-threshold"].value);
  return Number.isFinite(value) ? Math.min(Math.max(value, 0), 1) : 0.70;
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return false;
  return Number.isFinite(Number(value));
}

function formatNumber(value, digits) {
  return finiteNumber(value) ? Number(value).toFixed(digits) : "N/A";
}

function formatMaybe(value, digits) {
  return finiteNumber(value) ? Number(value).toFixed(digits) : "";
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

function asFalse(value) {
  return ["0", "false", "no", "off"].includes(String(value || "").toLowerCase());
}

function parseIntegerList(raw) {
  if (!raw) return [];
  return String(raw).split(/[,\s;]+/).map((value) => Number.parseInt(value, 10)).filter((value) => Number.isFinite(value));
}

function setMoranta26Status(text, kind) {
  m26El["m26-status"].textContent = text;
  m26El["m26-status"].classList.toggle("loading", kind === "loading");
  m26El["m26-status"].classList.toggle("error", kind === "error");
}

function setMoranta26PlotLoading(loading) {
  m26El["m26-plot-loader"]?.classList.toggle("is-visible", Boolean(loading));
}

function setMoranta26LightcurveLoading(loading) {
  m26El["m26-lightcurve-loader"]?.classList.toggle("is-visible", Boolean(loading));
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
      width: 1600,
      scale: 2,
      filename,
    },
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
