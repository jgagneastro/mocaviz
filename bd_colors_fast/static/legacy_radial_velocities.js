const lrvLsfThresholds = {
  spex_irtf: 1.33,
  fire_magellan: 1.384,
  nires_keck: 1.378,
  nirspec_jwst: 2.5,
};

const lrvState = {
  options: [],
  payload: null,
  qualityRows: [],
  selectedIds: null,
  selectedRowId: null,
  requestedDataset: "",
  loadToken: 0,
  eventsBound: false,
};

const lrvEl = {};

document.addEventListener("DOMContentLoaded", initLegacyRadialVelocities);

const lrvAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function lrvAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), lrvAppBaseUrl).toString();
}

async function initLegacyRadialVelocities() {
  collectLegacyRvElements();
  readLegacyRvUrlState();
  bindLegacyRvControls();
  await loadLegacyRvOptions();
  await loadLegacyRvData();
}

function collectLegacyRvElements() {
  [
    "lrv-status",
    "lrv-dataset-filter",
    "lrv-dataset",
    "lrv-load",
    "lrv-use-selection",
    "lrv-show-bad",
    "lrv-show-errors",
    "lrv-clear-selection",
    "lrv-data-contrast",
    "lrv-model-contrast",
    "lrv-lsf-default",
    "lrv-plot",
    "lrv-plot-loader",
    "lrv-summary",
    "lrv-hint",
    "lrv-export-csv",
    "lrv-export-tsv",
    "lrv-export-fits",
    "lrv-export-votable",
    "lrv-info",
    "lrv-detail",
    "lrv-model-link",
    "lrv-model-image",
    "lrv-model-empty",
    "lrv-chi2-link",
    "lrv-chi2-image",
    "lrv-chi2-empty",
    "lrv-best-link",
    "lrv-best-image",
    "lrv-best-empty",
    "lrv-clear-cache-bottom",
    "lrv-clear-cache-status",
  ].forEach((id) => {
    lrvEl[id] = document.getElementById(id);
  });
}

function readLegacyRvUrlState() {
  const params = new URLSearchParams(window.location.search);
  lrvState.requestedDataset = params.get("dataset") || params.get("rv_dataset") || datasetFromParts(params);
  setNumericInputFromParam("lrv-data-contrast", params.get("data_contrast"));
  setNumericInputFromParam("lrv-model-contrast", params.get("model_contrast"));
  setNumericInputFromParam("lrv-lsf-default", params.get("lsf_max"));
  if (params.has("show_bad")) lrvEl["lrv-show-bad"].checked = asBool(params.get("show_bad"));
  if (params.has("errors")) lrvEl["lrv-show-errors"].checked = asBool(params.get("errors"));
  if (params.has("use_selection")) lrvEl["lrv-use-selection"].checked = asBool(params.get("use_selection"));
}

function bindLegacyRvControls() {
  lrvEl["lrv-dataset-filter"].addEventListener("input", renderLegacyRvDatasetOptions);
  lrvEl["lrv-dataset"].addEventListener("change", loadLegacyRvData);
  lrvEl["lrv-load"].addEventListener("click", loadLegacyRvData);
  lrvEl["lrv-use-selection"].addEventListener("change", () => {
    renderLegacyRvPlot();
    updateLegacyRvUrl();
  });
  for (const id of ["lrv-show-bad", "lrv-show-errors", "lrv-data-contrast", "lrv-model-contrast", "lrv-lsf-default"]) {
    lrvEl[id].addEventListener("change", () => {
      renderLegacyRvAll();
      updateLegacyRvUrl();
    });
  }
  lrvEl["lrv-clear-selection"].addEventListener("click", () => {
    lrvState.selectedIds = null;
    renderLegacyRvPlot();
  });
  lrvEl["lrv-export-csv"].addEventListener("click", () => exportLegacyRvRows("csv"));
  lrvEl["lrv-export-tsv"].addEventListener("click", () => exportLegacyRvRows("tsv"));
  lrvEl["lrv-export-fits"].addEventListener("click", () => exportLegacyRvRows("fits"));
  lrvEl["lrv-export-votable"].addEventListener("click", () => exportLegacyRvRows("votable"));
  lrvEl["lrv-clear-cache-bottom"].addEventListener("click", clearLegacyRvCache);
  window.addEventListener("resize", debounce(() => {
    if (lrvState.payload) Plotly.Plots.resize(lrvEl["lrv-plot"]);
  }, 150));
}

async function loadLegacyRvOptions() {
  setLegacyRvStatus("Loading datasets", "loading");
  try {
    const payload = await fetchJsonUrl(lrvAppUrl(`api/legacy-radial-velocities/options?${connectionParams().toString()}`));
    lrvState.options = payload.options || [];
    renderLegacyRvDatasetOptions();
    const requested = lrvState.requestedDataset;
    if (requested) {
      ensureDatasetOption(requested);
      lrvEl["lrv-dataset"].value = requested;
    } else if (payload.value) {
      lrvEl["lrv-dataset"].value = payload.value;
    }
  } catch (error) {
    lrvState.options = [];
    ensureDatasetOption(lrvState.requestedDataset);
    renderLegacyRvDatasetOptions();
    setLegacyRvStatus(error.message || "Could not load datasets", "error");
  }
}

function renderLegacyRvDatasetOptions() {
  const filter = String(lrvEl["lrv-dataset-filter"].value || "").trim().toLowerCase();
  const current = lrvEl["lrv-dataset"].value || lrvState.requestedDataset;
  let rows = lrvState.options;
  if (filter) {
    rows = rows.filter((row) => String(row.label || row.value || "").toLowerCase().includes(filter));
  }
  rows = rows.slice(0, 1000);
  if (current && !rows.some((row) => row.value === current)) {
    rows = [{ value: current, label: current }, ...rows];
  }
  if (!rows.length) {
    rows = [{ value: "", label: "No datasets found" }];
  }
  lrvEl["lrv-dataset"].innerHTML = rows.map((row) => {
    const value = row.value || "";
    const label = row.label || row.value || "";
    return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
  }).join("");
  if (current && rows.some((row) => row.value === current)) {
    lrvEl["lrv-dataset"].value = current;
  }
}

function ensureDatasetOption(dataset) {
  if (!dataset) return;
  if (!lrvState.options.some((row) => row.value === dataset)) {
    lrvState.options.unshift({ value: dataset, label: dataset });
  }
}

async function loadLegacyRvData() {
  updateLegacyRvUrl();
  const dataset = lrvEl["lrv-dataset"].value || lrvState.requestedDataset;
  if (!dataset) {
    renderEmptyLegacyRv("No dataset selected");
    return;
  }
  const token = ++lrvState.loadToken;
  setLegacyRvLoading(true);
  setLegacyRvStatus("Loading radial velocities", "loading");
  const params = connectionParams();
  params.set("dataset", dataset);
  try {
    const payload = await fetchJsonUrl(lrvAppUrl(`api/legacy-radial-velocities/data?${params.toString()}`));
    if (token !== lrvState.loadToken) return;
    if (!payload.ok) {
      setLegacyRvStatus(payload.error || "Could not load radial velocities", "error");
      renderEmptyLegacyRv(payload.error || "Could not load radial velocities");
      return;
    }
    lrvState.payload = payload;
    lrvState.selectedIds = null;
    lrvState.selectedRowId = null;
    if (payload.selection?.dataset) {
      ensureDatasetOption(payload.selection.dataset);
      renderLegacyRvDatasetOptions();
      lrvEl["lrv-dataset"].value = payload.selection.dataset;
    }
    renderLegacyRvAll();
    updateLegacyRvUrl();
  } catch (error) {
    if (token !== lrvState.loadToken) return;
    setLegacyRvStatus(error.message || "Could not load radial velocities", "error");
    renderEmptyLegacyRv(error.message || "Could not load radial velocities");
  }
}

function renderLegacyRvAll() {
  const rows = lrvState.payload?.rows || [];
  lrvState.qualityRows = annotateLegacyRvQuality(rows);
  renderLegacyRvInfo();
  renderLegacyRvDetail(selectedLegacyRvRow());
  renderLegacyRvDatasetImages();
  renderLegacyRvPlot();
  updateLegacyRvExportButtons();
}

function annotateLegacyRvQuality(rows) {
  const dataContrastMin = numberInputValue("lrv-data-contrast", 0.01);
  const modelContrastMin = numberInputValue("lrv-model-contrast", 0.1);
  const defaultLsfMax = numberInputValue("lrv-lsf-default", 1.5);
  const annotated = rows.map((row, index) => {
    const instid = String(row.moca_instid || "").toLowerCase();
    const lsfThreshold = lrvLsfThresholds[instid] ?? defaultLsfMax;
    const rvUnc = asNumber(row.radial_velocity_kms_unc);
    const dataContrast = asNumber(row.data_contrast);
    const modelContrast = asNumber(row.model_contrast);
    const lsf = asNumber(row.lsf);
    const isBad = (
      rvUnc === null || rvUnc <= 0
      || (dataContrast !== null && dataContrast < dataContrastMin)
      || (modelContrast !== null && modelContrast < modelContrastMin)
      || (lsf !== null && lsf > lsfThreshold)
    );
    return {
      ...row,
      _rowIndex: index,
      _rowId: String(row.id ?? index),
      _lsfThreshold: lsfThreshold,
      _isBad: isBad,
    };
  });
  if (annotated.length && annotated.every((row) => row._isBad)) {
    annotated.forEach((row) => {
      row._isBad = false;
    });
  }
  return annotated;
}

function renderLegacyRvPlot() {
  const rows = lrvState.qualityRows || [];
  if (!rows.length) {
    renderEmptyLegacyRv("No radial-velocity segments found");
    return;
  }
  setLegacyRvLoading(false);
  const stats = weightedLegacyRvStats(rows);
  const target = lrvState.payload?.selection?.target_name || rows[0]?.target_name || "Dataset";
  const goodRows = rows.filter((row) => !row._isBad);
  const badRows = rows.filter((row) => row._isBad);
  const traces = [legacyRvTrace(goodRows, "Accepted segments", "circle", false)];
  if (lrvEl["lrv-show-bad"].checked && badRows.length) {
    traces.unshift(legacyRvTrace(badRows, "Bad segments", "x-thin", true));
  }
  const shapes = [];
  if (stats.ok) {
    shapes.push(
      averageLine(stats.average, "rgba(139, 0, 0, 0.55)", 3, "solid"),
      averageLine(stats.average + stats.stddev, "rgba(139, 0, 0, 0.3)", 1, "dash"),
      averageLine(stats.average - stats.stddev, "rgba(139, 0, 0, 0.3)", 1, "dash"),
    );
  }
  const title = stats.ok
    ? `${target}: Average RV = ${formatFixed(stats.average, 2)} +/- ${formatFixed(stats.stddev, 2)} km/s`
    : `${target}: Average RV could not be calculated`;
  const layout = {
    title: { text: title, x: 0.5, y: 0.98, xanchor: "center", yanchor: "top", font: { size: 16 } },
    plot_bgcolor: "#ffffff",
    paper_bgcolor: "#ffffff",
    margin: { l: 62, r: 24, t: 52, b: 58 },
    dragmode: "select",
    hovermode: "closest",
    showlegend: true,
    legend: { x: 0.02, y: 0.98, bgcolor: "rgba(255,255,255,0.72)" },
    xaxis: {
      title: "Central wavelength (um)",
      gridcolor: "rgba(211,211,211,0.65)",
      zerolinecolor: "lightgray",
      showline: true,
      linewidth: 2,
      linecolor: "black",
      mirror: true,
      ticks: "outside",
      tickwidth: 2,
    },
    yaxis: {
      title: "Radial velocity (km/s)",
      gridcolor: "rgba(211,211,211,0.65)",
      zerolinecolor: "lightgray",
      showline: true,
      linewidth: 2,
      linecolor: "black",
      mirror: true,
      ticks: "outside",
      tickwidth: 2,
    },
    shapes,
    uirevision: lrvState.payload?.selection?.dataset || "legacy-rv",
  };
  Plotly.react(lrvEl["lrv-plot"], traces.filter(Boolean), layout, plotConfig("legacy_radial_velocities"))
    .then(bindLegacyRvPlotEvents);
  renderLegacyRvSummary(stats, rows);
  setLegacyRvStatus(statusTextForStats(stats, rows), stats.ok ? "" : "error");
}

function legacyRvTrace(rows, name, symbol, bad) {
  const showErrors = lrvEl["lrv-show-errors"].checked;
  return {
    type: "scatter",
    mode: "markers",
    name,
    x: rows.map((row) => asNumber(row.segment_wavelength)),
    y: rows.map((row) => asNumber(row.radial_velocity_kms)),
    ids: rows.map((row) => row._rowId),
    customdata: rows.map((row) => row._rowId),
    text: rows.map(legacyRvHoverText),
    hoverinfo: "text",
    marker: bad
      ? { color: "#9c2f2f", size: 13, symbol, line: { color: "#9c2f2f", width: 2.5 } }
      : { color: "#ffffff", size: 7, symbol, line: { color: "#000000", width: 1.8 } },
    error_y: {
      type: "data",
      array: rows.map((row) => Math.max(0, asNumber(row.radial_velocity_kms_unc) ?? 0)),
      visible: showErrors,
      color: "rgba(0,0,0,0.24)",
      thickness: 1.5,
      width: 2,
    },
    selectedpoints: selectedPointIndices(rows),
    selected: { marker: { opacity: 1 } },
    unselected: { marker: { opacity: lrvState.selectedIds ? 0.28 : 1 } },
  };
}

function selectedPointIndices(rows) {
  if (!lrvState.selectedIds) return undefined;
  const indices = [];
  rows.forEach((row, index) => {
    if (lrvState.selectedIds.has(row._rowId)) indices.push(index);
  });
  return indices;
}

function bindLegacyRvPlotEvents() {
  if (lrvState.eventsBound || !lrvEl["lrv-plot"]?.on) return;
  lrvState.eventsBound = true;
  lrvEl["lrv-plot"].on("plotly_selected", (event) => {
    const points = event?.points || [];
    if (!points.length) return;
    lrvState.selectedIds = new Set(points.map((point) => String(point.customdata)).filter(Boolean));
    renderLegacyRvPlot();
  });
  lrvEl["lrv-plot"].on("plotly_deselect", () => {
    lrvState.selectedIds = null;
    renderLegacyRvPlot();
  });
  lrvEl["lrv-plot"].on("plotly_click", (event) => {
    const point = event?.points?.[0];
    const rowId = point?.customdata;
    if (rowId === undefined || rowId === null) return;
    lrvState.selectedRowId = String(rowId);
    renderLegacyRvDetail(selectedLegacyRvRow());
    renderLegacyRvSelectedImage(selectedLegacyRvRow());
  });
}

function weightedLegacyRvStats(rows) {
  const useSelection = lrvEl["lrv-use-selection"].checked && lrvState.selectedIds && lrvState.selectedIds.size;
  const selectedRows = useSelection ? rows.filter((row) => lrvState.selectedIds.has(row._rowId)) : rows;
  const filtered = selectedRows.filter((row) => !row._isBad);
  const values = filtered
    .map((row) => ({
      rv: asNumber(row.radial_velocity_kms),
      unc: asNumber(row.radial_velocity_kms_unc),
    }))
    .filter((row) => row.rv !== null && row.unc !== null && row.unc > 0);
  if (!values.length) {
    return { ok: false, average: NaN, stddev: NaN, n: 0, selectedN: selectedRows.length, badN: rows.filter((row) => row._isBad).length };
  }
  const weights = values.map((row) => 1 / (row.unc * row.unc));
  const weightSum = weights.reduce((sum, value) => sum + value, 0);
  const average = values.reduce((sum, row, index) => sum + row.rv * weights[index], 0) / weightSum;
  const variance = values.reduce((sum, row, index) => sum + weights[index] * (row.rv - average) ** 2, 0) / weightSum;
  const weightSquareSum = weights.reduce((sum, value) => sum + value * value, 0);
  const correction = 1 - (weightSquareSum / (weightSum * weightSum));
  const stddev = values.length > 1 && correction > 0
    ? Math.sqrt(Math.max(0, variance / correction))
    : values[0].unc;
  return {
    ok: Number.isFinite(average) && Number.isFinite(stddev),
    average,
    stddev,
    n: values.length,
    selectedN: selectedRows.length,
    badN: rows.filter((row) => row._isBad).length,
  };
}

function renderLegacyRvSummary(stats, rows) {
  const selectedText = lrvState.selectedIds ? `${lrvState.selectedIds.size} selected` : "all segments";
  const parts = [
    `${rows.length} segments`,
    `${stats.badN} flagged bad`,
    selectedText,
  ];
  if (stats.ok) {
    parts.push(`weighted RV ${formatFixed(stats.average, 2)} +/- ${formatFixed(stats.stddev, 2)} km/s from ${stats.n} accepted segments`);
  }
  lrvEl["lrv-summary"].textContent = parts.join(" | ");
}

function statusTextForStats(stats, rows) {
  if (!rows.length) return "No radial velocities";
  if (!stats.ok) return "Average unavailable";
  return `RV ${formatFixed(stats.average, 2)} +/- ${formatFixed(stats.stddev, 2)} km/s`;
}

function renderLegacyRvInfo() {
  const info = lrvState.payload?.datasetInfo || {};
  const entries = Object.entries(info).filter(([, value]) => value !== null && value !== undefined && value !== "");
  lrvEl["lrv-info"].innerHTML = entries.map(([key, value]) => `
    <div class="lrv-info-item">
      <span>${escapeHtml(fieldLabel(key))}</span>
      <strong>${formatLegacyRvValue(key, value)}</strong>
    </div>
  `).join("");
}

function renderLegacyRvDetail(row) {
  if (!row) {
    lrvEl["lrv-detail"].innerHTML = '<div class="lrv-empty-detail">No segment selected</div>';
    renderLegacyRvSelectedImage(null);
    return;
  }
  const fields = [
    "id",
    "order_number",
    "window_number",
    "segment_number",
    "segment_wavelength",
    "radial_velocity_kms",
    "radial_velocity_kms_unc",
    "data_contrast",
    "model_contrast",
    "nmodel_10p_contrast",
    "vsini_kms",
    "vsini_kms_unc",
    "lsf",
    "lsf_unc",
    "best_chi2",
    "lnp_avg",
    "lnp_mad",
    "lnp_std",
    "lnp_median",
    "lnp_max",
    "mean_acceptance_rate",
    "mean_finite_fraction",
    "mean_outofbounds_fraction",
    "blaze0",
    "blaze0_unc",
    "blaze1",
    "blaze1_unc",
    "moca_fsid",
    "ignored",
    "comments",
  ];
  const tableRows = fields
    .filter((field) => row[field] !== null && row[field] !== undefined && row[field] !== "")
    .map((field) => `
      <tr>
        <th>${escapeHtml(fieldLabel(field))}</th>
        <td>${formatLegacyRvValue(field, row[field])}</td>
      </tr>
    `).join("");
  lrvEl["lrv-detail"].innerHTML = `
    <table class="lrv-detail-table">
      <tbody>${tableRows}</tbody>
    </table>
  `;
  renderLegacyRvSelectedImage(row);
}

function selectedLegacyRvRow() {
  const rows = lrvState.qualityRows || [];
  if (lrvState.selectedRowId) {
    return rows.find((row) => row._rowId === lrvState.selectedRowId) || null;
  }
  return null;
}

function renderLegacyRvDatasetImages() {
  const images = lrvState.payload?.images || {};
  setLegacyRvImage("lrv-chi2", images.chi2_url, "No chi2 image URL");
  setLegacyRvImage("lrv-best", images.best_model_fit_url, "No best-fit image URL");
}

function renderLegacyRvSelectedImage(row) {
  setLegacyRvImage("lrv-model", row?.model_fit_url, row ? "No segment model image URL" : "No segment selected");
}

function setLegacyRvImage(prefix, url, emptyText) {
  const link = lrvEl[`${prefix}-link`];
  const image = lrvEl[`${prefix}-image`];
  const empty = lrvEl[`${prefix}-empty`];
  const href = downloadUrl(url);
  if (!href) {
    link.hidden = true;
    image.removeAttribute("src");
    empty.hidden = false;
    empty.textContent = emptyText;
    return;
  }
  link.href = href;
  image.src = href;
  link.hidden = false;
  empty.hidden = true;
}

function renderEmptyLegacyRv(message) {
  setLegacyRvLoading(false);
  const layout = {
    plot_bgcolor: "#ffffff",
    paper_bgcolor: "#ffffff",
    margin: { l: 40, r: 20, t: 32, b: 40 },
    xaxis: { visible: false },
    yaxis: { visible: false },
    annotations: [{ text: escapeHtml(message), x: 0.5, y: 0.5, xref: "paper", yref: "paper", showarrow: false }],
  };
  Plotly.react(lrvEl["lrv-plot"], [], layout, plotConfig("legacy_radial_velocities_empty")).then(bindLegacyRvPlotEvents);
  lrvEl["lrv-summary"].textContent = message;
  lrvEl["lrv-info"].innerHTML = "";
  lrvEl["lrv-detail"].innerHTML = `<div class="lrv-empty-detail">${escapeHtml(message)}</div>`;
  renderLegacyRvSelectedImage(null);
  setLegacyRvImage("lrv-chi2", "", "No chi2 image URL");
  setLegacyRvImage("lrv-best", "", "No best-fit image URL");
  updateLegacyRvExportButtons();
}

function updateLegacyRvExportButtons() {
  const enabled = Boolean((lrvState.qualityRows || []).length);
  for (const id of ["lrv-export-csv", "lrv-export-tsv", "lrv-export-fits", "lrv-export-votable"]) {
    lrvEl[id].disabled = !enabled;
  }
}

function exportLegacyRvRows(format) {
  const rows = exportLegacyRvSourceRows();
  if (!rows.length || !window.MocaExport) return;
  const columns = [
    "id",
    "target_name",
    "template_name",
    "pipeline_version",
    "moca_oid",
    "moca_specid",
    "moca_instid",
    "order_number",
    "window_number",
    "segment_number",
    "segment_wavelength",
    "radial_velocity_kms",
    "radial_velocity_kms_unc",
    "is_bad",
    "lsf_threshold",
    "data_contrast",
    "model_contrast",
    "lsf",
    "best_chi2",
    "model_fit_url",
  ];
  const exportRows = rows.map((row) => ({
    ...row,
    is_bad: row._isBad ? 1 : 0,
    lsf_threshold: row._lsfThreshold,
  }));
  const numericColumns = new Set(columns.filter((column) => !["target_name", "template_name", "pipeline_version", "moca_instid", "model_fit_url"].includes(column)));
  const suffix = lrvState.selectedIds && lrvEl["lrv-use-selection"].checked ? "selected" : "all";
  MocaExport.saveTable(format, {
    rows: exportRows,
    columns,
    numericColumns,
    filenameBase: `legacy_radial_velocities_${slugify(lrvEl["lrv-dataset"].value || "dataset")}_${suffix}`,
    tableName: "legacy_radial_velocities",
  });
}

function exportLegacyRvSourceRows() {
  const rows = lrvState.qualityRows || [];
  if (lrvState.selectedIds && lrvEl["lrv-use-selection"].checked) {
    return rows.filter((row) => lrvState.selectedIds.has(row._rowId));
  }
  return rows;
}

async function clearLegacyRvCache() {
  lrvEl["lrv-clear-cache-status"].textContent = "Clearing...";
  lrvEl["lrv-clear-cache-status"].classList.remove("error");
  try {
    const payload = await postJson(lrvAppUrl("api/legacy-radial-velocities/cache/clear"), {});
    const count = payload.cleared?.legacyRadialVelocities ?? 0;
    lrvEl["lrv-clear-cache-status"].textContent = `Cleared ${count} cached payloads.`;
  } catch (error) {
    lrvEl["lrv-clear-cache-status"].textContent = error.message || "Could not clear cache";
    lrvEl["lrv-clear-cache-status"].classList.add("error");
  }
}

function updateLegacyRvUrl() {
  const params = new URLSearchParams(window.location.search);
  const dataset = lrvEl["lrv-dataset"].value;
  if (dataset) params.set("dataset", dataset);
  params.delete("target_name");
  params.delete("template_name");
  params.delete("pipeline_version");
  params.set("show_bad", lrvEl["lrv-show-bad"].checked ? "1" : "0");
  params.set("errors", lrvEl["lrv-show-errors"].checked ? "1" : "0");
  params.set("use_selection", lrvEl["lrv-use-selection"].checked ? "1" : "0");
  params.set("data_contrast", String(numberInputValue("lrv-data-contrast", 0.01)));
  params.set("model_contrast", String(numberInputValue("lrv-model-contrast", 0.1)));
  params.set("lsf_max", String(numberInputValue("lrv-lsf-default", 1.5)));
  const query = params.toString();
  window.history.replaceState({}, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}

function connectionParams() {
  const params = new URLSearchParams(window.location.search);
  for (const key of [
    "dataset",
    "rv_dataset",
    "target_name",
    "target",
    "template_name",
    "template",
    "pipeline_version",
    "version",
    "show_bad",
    "errors",
    "use_selection",
    "data_contrast",
    "model_contrast",
    "lsf_max",
  ]) {
    params.delete(key);
  }
  return params;
}

function datasetFromParts(params) {
  const target = params.get("target_name") || params.get("target");
  const template = params.get("template_name") || params.get("template");
  const version = params.get("pipeline_version") || params.get("version");
  return target && template && version ? `${target}|${template}|${version}` : "";
}

function legacyRvHoverText(row) {
  const parts = [
    `<b>ID ${escapeHtml(row.id)}</b>`,
    `RV: ${formatFixed(row.radial_velocity_kms, 2)} +/- ${formatFixed(row.radial_velocity_kms_unc, 2)} km/s`,
    `Wavelength: ${formatFixed(row.segment_wavelength, 4)} um`,
    `Order/window/segment: ${escapeHtml(row.order_number ?? "")}/${escapeHtml(row.window_number ?? "")}/${escapeHtml(row.segment_number ?? "")}`,
  ];
  if (row._isBad) parts.push("Flagged bad");
  return parts.join("<br>");
}

function averageLine(y, color, width, dash) {
  return {
    type: "line",
    xref: "paper",
    x0: 0,
    x1: 1,
    y0: y,
    y1: y,
    line: { color, width, dash },
    layer: "below",
  };
}

function fieldLabel(key) {
  const labels = {
    id: "ID",
    moca_oid: "MOCA OID",
    moca_specid: "MOCA SpecID",
    moca_instid: "Instrument",
    moca_fsid: "MOCA FSID",
    pipeline_version: "Pipeline Version",
    target_name: "Target Name",
    template_name: "Template Name",
    berv_kms: "BERV",
    berv_kms_unc: "E_BERV",
    order_number: "Order",
    window_number: "Window",
    segment_number: "Segment",
    segment_wavelength: "Central Wavelength",
    radial_velocity_kms: "RV",
    radial_velocity_kms_unc: "E_RV",
    data_contrast: "Data Contrast",
    model_contrast: "Model Contrast",
    nmodel_10p_contrast: "Model Points > 10% Contrast",
    vsini_kms: "v sin i",
    vsini_kms_unc: "E_v sin i",
    lsf: "log10(LSF)",
    lsf_unc: "E_log10(LSF)",
    best_chi2: "Chi2",
    lnp_avg: "avg(ln P)",
    lnp_mad: "mad(ln P)",
    lnp_std: "std(ln P)",
    lnp_median: "median(ln P)",
    lnp_max: "max(ln P)",
    mean_acceptance_rate: "Acceptance Rate",
    mean_finite_fraction: "Finite Steps",
    mean_outofbounds_fraction: "Out-of-bounds Steps",
    blaze0: "log10(Blaze left)",
    blaze0_unc: "E_log10(Blaze left)",
    blaze1: "log10(Blaze right)",
    blaze1_unc: "E_log10(Blaze right)",
    nwindows: "N Windows",
    nsegments: "N Segments",
    npoints: "N Data Points",
    origin: "Origin",
    parscale_rv: "RV Scale",
    rv_min_bound: "RV Min Bound",
    rv_max_bound: "RV Max Bound",
    niter_mcmc: "MCMC Iterations",
    nburnin_mcmc: "MCMC Burn-in",
    nchains_mcmc: "MCMC Chains",
    ignored: "Ignored",
    comments: "Comments",
  };
  return labels[key] || key;
}

function formatLegacyRvValue(key, value) {
  if (value === null || value === undefined || value === "") return "";
  const number = asNumber(value);
  if (["radial_velocity_kms", "radial_velocity_kms_unc", "vsini_kms", "vsini_kms_unc", "berv_kms", "berv_kms_unc", "parscale_rv", "rv_min_bound", "rv_max_bound"].includes(key) && number !== null) {
    return `${formatFixed(number, 2)} km/s`;
  }
  if (key === "segment_wavelength" && number !== null) return `${formatFixed(number, 4)} um`;
  if (["mean_acceptance_rate", "mean_finite_fraction", "mean_outofbounds_fraction", "model_contrast", "data_contrast"].includes(key) && number !== null) {
    return `${formatFixed(number * 100, 2)} %`;
  }
  if (number !== null && Math.abs(number) < 100000) return escapeHtml(formatSmartNumber(number));
  return escapeHtml(value);
}

function downloadUrl(url) {
  const text = String(url || "").trim();
  if (!text) return "";
  if (text.startsWith("data:") || /\/download(?:[?#].*)?$/.test(text)) return text;
  return `${text.replace(/\/+$/, "")}/download`;
}

function setLegacyRvLoading(isLoading) {
  lrvEl["lrv-plot-loader"].classList.toggle("is-visible", Boolean(isLoading));
}

function setLegacyRvStatus(message, kind = "") {
  lrvEl["lrv-status"].textContent = message || "";
  lrvEl["lrv-status"].classList.toggle("loading", kind === "loading");
  lrvEl["lrv-status"].classList.toggle("error", kind === "error");
}

async function fetchJsonUrl(url) {
  const response = await fetch(url);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `${response.status} ${response.statusText}`);
  }
  return payload;
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function plotConfig(filename) {
  return {
    responsive: true,
    displaylogo: false,
    scrollZoom: true,
    toImageButtonOptions: {
      format: "png",
      filename,
      height: 900,
      width: 1300,
      scale: 2,
    },
  };
}

function numberInputValue(id, fallback) {
  const value = Number(lrvEl[id].value);
  return Number.isFinite(value) ? value : fallback;
}

function setNumericInputFromParam(id, value) {
  if (value === null || value === undefined || value === "") return;
  const number = Number(value);
  if (Number.isFinite(number)) lrvEl[id].value = String(number);
}

function asNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function formatFixed(value, digits) {
  const number = asNumber(value);
  return number === null ? "N/A" : number.toFixed(digits);
}

function formatSmartNumber(value) {
  const number = asNumber(value);
  if (number === null) return "";
  if (Number.isInteger(number)) return String(number);
  const absValue = Math.abs(number);
  if (absValue >= 1000) return number.toFixed(1);
  if (absValue >= 10) return number.toFixed(2);
  if (absValue >= 1) return number.toFixed(3);
  return number.toPrecision(3);
}

function slugify(value) {
  return String(value || "dataset")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80) || "dataset";
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
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
