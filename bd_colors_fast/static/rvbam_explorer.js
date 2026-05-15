const rvbState = {
  runs: [],
  payload: null,
  segmentDetail: null,
  posterior: null,
  rebuiltCorner: null,
  globalCorner: null,
  rebuiltFit: null,
  selectedSegmentId: null,
  selectedIds: null,
  requestedRunId: null,
  requestedSegmentId: null,
  requestedTab: null,
  requestedXParam: "",
  requestedYParam: "",
  autoRebuiltFitSegmentId: null,
  autoRebuiltCornerSegmentId: null,
  loadToken: 0,
  segmentToken: 0,
  posteriorToken: 0,
  globalCornerToken: 0,
  ignorePlotlyDeselectUntil: 0,
  activeTab: "fit",
};

const rvbEl = {};

const RVB_SHOW_GLOBAL_CORNER_TAB = false;

const rvbScatterYAxisOptions = {
  rv_kms: { key: "rv_kms", label: "RV", axisTitle: "RV (km/s)", errorKey: "rv_kms_unc", unit: "km/s", digits: 3 },
  rv_kms_unc: { key: "rv_kms_unc", label: "RV uncertainty", axisTitle: "RV uncertainty (km/s)", unit: "km/s", digits: 3 },
  lsf: { key: "lsf", label: "LSF sigma", axisTitle: "LSF sigma (km/s)", errorKey: "lsf_unc", unit: "km/s", digits: 3 },
  vsini_kms: { key: "vsini_kms", label: "v sin i", axisTitle: "v sin i (km/s)", errorKey: "vsini_kms_unc", unit: "km/s", digits: 3 },
  best_chi2: { key: "best_chi2", label: "Best chi2", axisTitle: "Best chi2", digits: 3 },
  lnp_median: { key: "lnp_median", label: "Median log likelihood", axisTitle: "Median log likelihood", digits: 3 },
  lnp_max: { key: "lnp_max", label: "Max log likelihood", axisTitle: "Max log likelihood", digits: 3 },
  mean_finite_fraction: { key: "mean_finite_fraction", label: "Finite fraction", axisTitle: "Finite fraction", digits: 4 },
  mean_outofbounds_fraction: { key: "mean_outofbounds_fraction", label: "Out-of-bounds fraction", axisTitle: "Out-of-bounds fraction", digits: 4 },
  n_iterations: { key: "n_iterations", label: "Sampler iterations", axisTitle: "Sampler iterations", digits: 1 },
};

document.addEventListener("DOMContentLoaded", initRvbamExplorer);

const rvbAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function rvbAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), rvbAppBaseUrl).toString();
}

async function initRvbamExplorer() {
  collectRvbamElements();
  readRvbamUrlState();
  bindRvbamControls();
  activateRvbamTab(rvbState.activeTab);
  renderEmptyRvbam("Loading RVBAM runs");
  await loadRvbamRuns();
  await loadSelectedRvbamRun();
}

function collectRvbamElements() {
  [
    "rvb-status",
    "rvb-search",
    "rvb-oid",
    "rvb-specid",
    "rvb-pipeline",
    "rvb-run",
    "rvb-load-runs",
    "rvb-load-run",
    "rvb-scatter-y",
    "rvb-use-selection",
    "rvb-show-errors",
    "rvb-use-online-figures",
    "rvb-use-online-figures-row",
    "rvb-include-ignored",
    "rvb-clear-selection",
    "rvb-max-lsf",
    "rvb-max-best-chi2",
    "rvb-max-rv-unc",
    "rvb-param-x",
    "rvb-param-y",
    "rvb-max-points",
    "rvb-load-posterior",
    "rvb-load-rebuilt-corner",
    "rvb-load-global-corner",
    "rvb-load-rebuilt-fit",
    "rvb-segment-plot",
    "rvb-plot-loader",
    "rvb-summary",
    "rvb-hint",
    "rvb-open-report",
    "rvb-open-spectrum",
    "rvb-export-csv",
    "rvb-export-tsv",
    "rvb-export-fits",
    "rvb-export-votable",
    "rvb-info",
    "rvb-segments-table",
    "rvb-spectrum-table",
    "rvb-model-link",
    "rvb-model-image",
    "rvb-model-empty",
    "rvb-corner-link",
    "rvb-corner-image",
    "rvb-corner-empty",
    "rvb-posterior-plot",
    "rvb-correlation-plot",
    "rvb-rebuilt-corner-plot",
    "rvb-rebuilt-corner-meta",
    "rvb-global-corner-plot",
    "rvb-global-corner-meta",
    "rvb-rebuilt-fit-plot",
    "rvb-rebuilt-fit-meta",
    "rvb-params-table",
    "rvb-payload-table",
    "rvb-clear-cache-bottom",
    "rvb-clear-cache-status",
  ].forEach((id) => {
    rvbEl[id] = document.getElementById(id);
  });
}

function readRvbamUrlState() {
  const params = new URLSearchParams(window.location.search);
  rvbState.requestedRunId = numberOrNull(params.get("run_id") || params.get("moca_rv_sample_run_id"));
  rvbState.requestedSegmentId = numberOrNull(params.get("segment_id") || params.get("moca_rv_sampling_segment_id"));
  rvbState.requestedXParam = params.get("x") || params.get("x_param") || "";
  rvbState.requestedYParam = params.get("y") || params.get("y_param") || "";
  const requestedTab = params.get("tab") || params.get("rvb_tab");
  if (isRvbamTabName(requestedTab)) {
    rvbState.requestedTab = requestedTab;
    rvbState.activeTab = requestedTab;
  }
  if (params.has("q")) rvbEl["rvb-search"].value = params.get("q") || "";
  if (params.has("moca_oid") || params.has("oid")) rvbEl["rvb-oid"].value = params.get("moca_oid") || params.get("oid") || "";
  if (params.has("moca_specid") || params.has("specid")) rvbEl["rvb-specid"].value = params.get("moca_specid") || params.get("specid") || "";
  if (params.has("pipeline") || params.has("pipeline_version")) rvbEl["rvb-pipeline"].value = params.get("pipeline") || params.get("pipeline_version") || "";
  if (params.has("include_ignored")) rvbEl["rvb-include-ignored"].checked = asBool(params.get("include_ignored"));
  if (params.has("errors")) rvbEl["rvb-show-errors"].checked = asBool(params.get("errors"));
  if (params.has("use_selection")) rvbEl["rvb-use-selection"].checked = asBool(params.get("use_selection"));
  if (params.has("online_figures") || params.has("use_online_figures")) {
    rvbEl["rvb-use-online-figures"].checked = asBool(params.get("online_figures") || params.get("use_online_figures"));
  }
  const scatterY = params.get("scatter_y") || params.get("y_axis");
  if (scatterY && rvbScatterYAxisOptions[scatterY]) rvbEl["rvb-scatter-y"].value = scatterY;
  if (params.has("max_lsf")) rvbEl["rvb-max-lsf"].value = params.get("max_lsf") || "";
  if (params.has("max_best_chi2")) rvbEl["rvb-max-best-chi2"].value = params.get("max_best_chi2") || "";
  if (params.has("max_rv_unc")) rvbEl["rvb-max-rv-unc"].value = params.get("max_rv_unc") || "";
  if (params.has("max_points")) rvbEl["rvb-max-points"].value = params.get("max_points") || rvbEl["rvb-max-points"].value;
}

function bindRvbamControls() {
  rvbEl["rvb-load-runs"].addEventListener("click", async () => {
    await loadRvbamRuns();
    await loadSelectedRvbamRun();
  });
  rvbEl["rvb-load-run"].addEventListener("click", loadSelectedRvbamRun);
  rvbEl["rvb-run"].addEventListener("change", () => {
    rvbState.requestedRunId = numberOrNull(rvbEl["rvb-run"].value);
    rvbState.requestedSegmentId = null;
    rvbState.selectedSegmentId = null;
    updateRvbamUrl();
    loadSelectedRvbamRun();
  });
  rvbEl["rvb-include-ignored"].addEventListener("change", async () => {
    updateRvbamUrl();
    await loadRvbamRuns();
    await loadSelectedRvbamRun();
  });
  rvbEl["rvb-show-errors"].addEventListener("change", () => {
    renderRvbamRun();
    updateRvbamUrl();
  });
  rvbEl["rvb-use-online-figures"].addEventListener("change", () => {
    updateRvbamFigureTabs(rvbState.segmentDetail || {});
    updateRvbamUrl();
  });
  rvbEl["rvb-scatter-y"].addEventListener("change", () => {
    renderRvbamSegmentPlot();
    updateRvbamUrl();
  });
  rvbEl["rvb-use-selection"].addEventListener("change", () => {
    renderRvbamSegmentPlot();
    renderRvbamSummary();
    updateRvbamUrl();
  });
  rvbEl["rvb-clear-selection"].addEventListener("click", () => {
    rvbState.selectedIds = null;
    renderRvbamSegmentPlot();
    renderRvbamSummary();
  });
  const averageFilterChanged = () => {
    renderRvbamSegmentPlot();
    renderRvbamSummary();
    updateRvbamUrl();
  };
  for (const id of ["rvb-max-lsf", "rvb-max-best-chi2", "rvb-max-rv-unc"]) {
    rvbEl[id].addEventListener("input", debounce(averageFilterChanged, 120));
    rvbEl[id].addEventListener("change", averageFilterChanged);
  }
  rvbEl["rvb-load-posterior"].addEventListener("click", loadRvbamPosterior);
  rvbEl["rvb-load-rebuilt-corner"].addEventListener("click", loadRvbamRebuiltCorner);
  rvbEl["rvb-load-global-corner"].addEventListener("click", loadRvbamGlobalCorner);
  rvbEl["rvb-load-rebuilt-fit"].addEventListener("click", loadRvbamRebuiltFit);
  rvbEl["rvb-param-x"].addEventListener("change", () => {
    rvbState.requestedXParam = rvbEl["rvb-param-x"].value;
    updateRvbamUrl();
  });
  rvbEl["rvb-param-y"].addEventListener("change", () => {
    rvbState.requestedYParam = rvbEl["rvb-param-y"].value;
    updateRvbamUrl();
  });
  rvbEl["rvb-clear-cache-bottom"].addEventListener("click", clearRvbamCache);
  rvbEl["rvb-open-report"].addEventListener("click", openRvbamReport);
  rvbEl["rvb-open-spectrum"].addEventListener("click", openRvbamSpectrum);
  rvbEl["rvb-export-csv"].addEventListener("click", () => exportRvbamSegments("csv"));
  rvbEl["rvb-export-tsv"].addEventListener("click", () => exportRvbamSegments("tsv"));
  rvbEl["rvb-export-fits"].addEventListener("click", () => exportRvbamSegments("fits"));
  rvbEl["rvb-export-votable"].addEventListener("click", () => exportRvbamSegments("votable"));
  document.querySelectorAll("[data-rvb-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      rvbState.requestedTab = null;
      activateRvbamTab(button.dataset.rvbTab || "fit");
      updateRvbamUrl();
    });
  });
  window.addEventListener("resize", debounce(() => {
    for (const id of ["rvb-segment-plot", "rvb-posterior-plot", "rvb-correlation-plot", "rvb-rebuilt-corner-plot", "rvb-global-corner-plot", "rvb-rebuilt-fit-plot"]) {
      if (rvbEl[id]) Plotly.Plots.resize(rvbEl[id]);
    }
  }, 150));
}

async function loadRvbamRuns() {
  setRvbamStatus("Loading runs", "loading");
  const params = rvbamRunQueryParams();
  if (rvbState.requestedRunId) params.set("run_id", String(rvbState.requestedRunId));
  try {
    const payload = await fetchJsonUrl(rvbAppUrl(`api/rvbam-explorer/runs?${params.toString()}`));
    if (!payload.ok) throw new Error(payload.error || "Could not load RVBAM runs");
    rvbState.runs = payload.runs || [];
    renderRvbamRunOptions(payload.value);
    setRvbamStatus(`${rvbState.runs.length} runs`, "");
  } catch (error) {
    rvbState.runs = [];
    renderRvbamRunOptions(null);
    setRvbamStatus(error.message || "Could not load RVBAM runs", "error");
  }
}

function rvbamRunQueryParams() {
  const params = connectionParams();
  const query = String(rvbEl["rvb-search"].value || "").trim();
  const oid = String(rvbEl["rvb-oid"].value || "").trim();
  const specid = String(rvbEl["rvb-specid"].value || "").trim();
  const pipeline = String(rvbEl["rvb-pipeline"].value || "").trim();
  if (query) params.set("q", query);
  if (oid) params.set("moca_oid", oid);
  if (specid) params.set("moca_specid", specid);
  if (pipeline) params.set("pipeline", pipeline);
  if (rvbEl["rvb-include-ignored"].checked) params.set("include_ignored", "1");
  params.set("limit", "500");
  return params;
}

function renderRvbamRunOptions(value) {
  const current = String(rvbEl["rvb-run"].value || value || rvbState.requestedRunId || "");
  let rows = rvbState.runs.slice(0, 1000);
  if (!rows.length) rows = [{ moca_rv_sample_run_id: "", label: "No runs found" }];
  rvbEl["rvb-run"].innerHTML = rows.map((row) => {
    const id = row.moca_rv_sample_run_id || "";
    const label = row.label || runOptionLabel(row);
    return `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`;
  }).join("");
  if (current && rows.some((row) => String(row.moca_rv_sample_run_id || "") === current)) {
    rvbEl["rvb-run"].value = current;
  } else if (value) {
    rvbEl["rvb-run"].value = String(value);
  }
}

function runOptionLabel(row) {
  if (row.label) return row.label;
  const name = row.designation || row.target_name || `OID ${row.moca_oid ?? "?"}`;
  const spec = row.moca_specid ? `spec ${row.moca_specid}` : "no specid";
  const template = row.template_name ? basename(row.template_name) : "no template";
  const version = row.pipeline_version || "no version";
  const count = Number(row.segment_count || 0);
  const headerCount = Number(row.nsegments || 0);
  const countText = count
    ? `${count} segments`
    : (headerCount ? `0 linked segments, header says ${headerCount}` : "no segments");
  return `${name} | ${spec} | ${template} | ${version} | ${countText}`;
}

function renderScatterYAxisOptions(rows) {
  if (!rvbEl["rvb-scatter-y"]) return;
  const previous = rvbEl["rvb-scatter-y"].value || "rv_kms";
  const available = availableScatterYAxisSpecs(rows);
  rvbEl["rvb-scatter-y"].innerHTML = available.map((spec) => {
    const label = spec.unit ? `${spec.label} (${spec.unit})` : spec.label;
    return `<option value="${escapeHtml(spec.key)}">${escapeHtml(label)}</option>`;
  }).join("");
  if (available.some((spec) => spec.key === previous)) {
    rvbEl["rvb-scatter-y"].value = previous;
  } else if (available.some((spec) => spec.key === "rv_kms")) {
    rvbEl["rvb-scatter-y"].value = "rv_kms";
  } else if (available.length) {
    rvbEl["rvb-scatter-y"].value = available[0].key;
  }
}

function availableScatterYAxisSpecs(rows) {
  const specs = Object.values(rvbScatterYAxisOptions);
  if (!rows?.length) return specs;
  const available = specs.filter((spec) => rows.some((row) => asNumber(row[spec.key]) !== null));
  return available.length ? available : [rvbScatterYAxisOptions.rv_kms];
}

async function loadSelectedRvbamRun() {
  const runId = numberOrNull(rvbEl["rvb-run"].value) || rvbState.requestedRunId;
  if (!runId) {
    renderEmptyRvbam("No RVBAM run selected");
    return;
  }
  const token = ++rvbState.loadToken;
  setRvbamLoading(true);
  setRvbamStatus("Loading run", "loading");
  const params = connectionParams();
  if (rvbEl["rvb-include-ignored"].checked) params.set("include_ignored", "1");
  try {
    const payload = await fetchJsonUrl(rvbAppUrl(`api/rvbam-explorer/run/${runId}?${params.toString()}`));
    if (token !== rvbState.loadToken) return;
    if (!payload.ok) throw new Error(payload.error || "Could not load RVBAM run");
    rvbState.payload = payload;
    rvbState.posterior = null;
    rvbState.rebuiltCorner = null;
    rvbState.globalCorner = null;
    rvbState.rebuiltFit = null;
    rvbState.autoRebuiltFitSegmentId = null;
    rvbState.autoRebuiltCornerSegmentId = null;
    rvbState.segmentDetail = null;
    rvbState.selectedIds = null;
    const segments = payload.segments || [];
    renderScatterYAxisOptions(segments);
    const requested = rvbState.requestedSegmentId;
    const selected = requested && segments.some((row) => Number(row.moca_rv_sampling_segment_id) === Number(requested))
      ? requested
      : (segments[0]?.moca_rv_sampling_segment_id || null);
    rvbState.selectedSegmentId = selected;
    renderRvbamRun();
    updateRvbamUrl();
    if (selected) await loadRvbamSegment(selected);
    setRvbamStatus(`${segments.length} segments`, "");
  } catch (error) {
    if (token !== rvbState.loadToken) return;
    setRvbamStatus(error.message || "Could not load RVBAM run", "error");
    renderEmptyRvbam(error.message || "Could not load RVBAM run");
  } finally {
    if (token === rvbState.loadToken) setRvbamLoading(false);
  }
}

function renderRvbamRun() {
  const payload = rvbState.payload;
  if (!payload || !payload.run) {
    renderEmptyRvbam("No run loaded");
    return;
  }
  renderScatterYAxisOptions(payload.segments || []);
  renderRvbamInfo();
  renderRvbamSpectrumTable();
  renderRvbamSegmentsTable();
  renderRvbamSegmentPlot();
  renderRvbamSummary();
  updateRvbamGlobalCornerControls();
  if (!rvbState.globalCorner) renderEmptyGlobalCorner("Global corner not loaded");
  updateRvbamExportButtons();
}

function renderRvbamInfo() {
  const run = rvbState.payload?.run || {};
  const segments = rvbState.payload?.segments || [];
  const spectrum = rvbState.payload?.spectrum || {};
  const entries = [
    ["Target", run.designation || run.target_name],
    ["OID", run.moca_oid],
    ["SpecID", run.moca_specid],
    ["Instrument", run.moca_instid],
    ["Pipeline", run.pipeline_version || run.rv_pipeline_version],
    ["Template", basename(run.template_name)],
    ["Model Grid", run.moca_mgridid],
    ["Segments", segments.length],
    ["BERV", formatWithUnit(run.berv_kms, "km/s", 3)],
    ["BERV corrected", formatFlag(spectrum.berv_corrected ?? run.berv_corrected)],
    ["Spacecraft RV corrected", formatFlag(spectrum.spacecraft_rv_corrected ?? run.spacecraft_rv_corrected)],
    ["Wavelength", wavelengthRangeLabel(segments)],
  ];
  rvbEl["rvb-info"].innerHTML = entries.map(([key, value]) => `
    <div class="rvb-info-item">
      <span>${escapeHtml(key)}</span>
      <strong>${escapeHtml(displayValue(value))}</strong>
    </div>
  `).join("");
}

function renderRvbamSpectrumTable() {
  const spectrum = rvbState.payload?.spectrum || {};
  const rows = orderedRvbamSpectrumRows(spectrum);
  rvbEl["rvb-spectrum-table"].innerHTML = rows.length
    ? simpleTable(rows, [["column", "moca_spectra column"], ["value", "Value"]], "rvb-detail-table rvb-spectrum-metadata-table")
    : '<div class="rvb-empty-detail">No moca_spectra metadata for this moca_specid</div>';
}

function orderedRvbamSpectrumRows(spectrum) {
  const entries = Object.entries(spectrum || {});
  const deferredColumns = new Set(["comments", "fits_header"]);
  const rows = entries
    .filter(([column]) => !deferredColumns.has(column))
    .map(([column, value]) => ({ column, value }));
  for (const column of ["comments", "fits_header"]) {
    if (Object.prototype.hasOwnProperty.call(spectrum, column)) {
      rows.push({ column, value: spectrum[column] });
    }
  }
  return rows;
}

function renderRvbamSegmentsTable() {
  const rows = rvbState.payload?.segments || [];
  if (!rows.length) {
    rvbEl["rvb-segments-table"].innerHTML = '<div class="rvb-empty-detail">No segments found</div>';
    return;
  }
  const columns = [
    ["segment_number", "Seg"],
    ["order_number", "Order"],
    ["window_number", "Window"],
    ["wv_center", "Wave (um)"],
    ["rv_kms", "RV"],
    ["rv_kms_unc", "E_RV"],
    ["lsf", "LSF"],
    ["vsini_kms", "vsini"],
    ["sampler_name", "Sampler"],
    ["payload_count", "Payloads"],
  ];
  rvbEl["rvb-segments-table"].innerHTML = `
    <table class="rvb-segment-table">
      <thead>
        <tr>${columns.map(([, label]) => `<th>${escapeHtml(label)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows.map((row) => {
          const id = Number(row.moca_rv_sampling_segment_id);
          const selected = id === Number(rvbState.selectedSegmentId) ? " is-selected" : "";
          const ignored = Number(row.ignored || 0) ? " is-ignored" : "";
          return `
            <tr class="rvb-segment-row${selected}${ignored}" data-segment-id="${escapeHtml(id)}">
              ${columns.map(([key]) => `<td>${escapeHtml(formatSegmentCell(row, key))}</td>`).join("")}
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
  rvbEl["rvb-segments-table"].querySelectorAll("[data-segment-id]").forEach((row) => {
    row.addEventListener("click", () => {
      const id = numberOrNull(row.dataset.segmentId);
      if (id) selectRvbamSegment(id);
    });
  });
}

function renderRvbamSegmentPlot() {
  const rows = rvbState.payload?.segments || [];
  if (!rows.length) {
    renderEmptyPlot("No RVBAM segments");
    return;
  }
  const ySpec = scatterYAxisSpec();
  const showErrors = rvbEl["rvb-show-errors"].checked && Boolean(ySpec.errorKey);
  const selectedRows = selectedRvbamRows();
  const averageRows = filteredAverageRvbamRows(selectedRows);
  const filteredOutRows = averageFilteredOutRvbamRows(selectedRows);
  const filteredOutIds = new Set(filteredOutRows.map((row) => Number(row.moca_rv_sampling_segment_id)).filter(Boolean));
  const stats = averageSegmentStats(averageRows, ySpec);
  const activeRows = rows.filter((row) => !Number(row.ignored || 0));
  const ignoredRows = rows.filter((row) => Number(row.ignored || 0));
  const rangeRows = rows.length ? rows : averageRows;
  const traces = [];
  traces.push(segmentTrace(activeRows, "Segments", "circle", false, showErrors, 8, false, ySpec, filteredOutIds));
  if (ignoredRows.length) traces.push(segmentTrace(ignoredRows, "Ignored", "x-thin", true, showErrors, 13, false, ySpec));
  if (filteredOutRows.length) traces.push(filteredAverageLegendTrace());
  const selected = rows.filter((row) => Number(row.moca_rv_sampling_segment_id) === Number(rvbState.selectedSegmentId));
  if (selected.length) traces.push(segmentTrace(selected, "Selected", "star", false, showErrors, 18, true, ySpec));
  const literatureRv = rvbamLiteratureRvForYAxis(ySpec);
  if (literatureRv) traces.push(rvbamLiteratureRvLegendTrace(literatureRv));
  const shapes = [];
  if (literatureRv) {
    const band = rvbamLiteratureRvErrorBand(literatureRv);
    if (band) shapes.push(band);
    shapes.push(rvbamAverageLine(literatureRv.value, "rgba(24, 128, 61, 0.95)", 3, "solid"));
  }
  if (stats.n) {
    shapes.push(rvbamAverageLine(stats.mean, "rgba(168, 18, 18, 0.82)", 4, "solid"));
    if (stats.unc !== null && stats.unc > 0) {
      shapes.push(
        rvbamAverageLine(stats.mean + stats.unc, "rgba(168, 18, 18, 0.62)", 1.5, "dash"),
        rvbamAverageLine(stats.mean - stats.unc, "rgba(168, 18, 18, 0.62)", 1.5, "dash"),
      );
    }
  }
  const run = rvbState.payload?.run || {};
  const designation = run.designation || run.target_name || `OID ${run.moca_oid ?? "unknown"}`;
  const modelName = run.template_name ? basename(run.template_name) : (run.moca_mgridid || "no model");
  const titlePrefix = `${designation} | ${modelName}`;
  const filterNote = averageFilterNote(selectedRows.length, averageRows.length);
  const title = stats.n
    ? `${titlePrefix}<br>${averageStatsLabel(stats, ySpec, { compactRvUncertainty: true })}${filterNote}`
    : `${titlePrefix}<br>${ySpec.label} average unavailable${filterNote}`;
  const xRange = scatterAxisRange(rangeRows, (row) => segmentWavelengthMicron(row));
  const yRange = scatterAxisRange(
    rangeRows,
    (row) => asNumber(row[ySpec.key]),
    rvbamLiteratureRvRangeValues(literatureRv),
  );

  const layout = {
    title: { text: title, x: 0.5, y: 0.965, xanchor: "center", yanchor: "top", font: { size: 12.8 } },
    margin: { l: 64, r: 24, t: 52, b: 58 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    hovermode: "closest",
    clickmode: "event",
    dragmode: "lasso",
    xaxis: {
      title: "Wavelength center (μm)",
      range: xRange || undefined,
      zerolinecolor: "lightgray",
      gridcolor: "rgba(211,211,211,0.65)",
      showline: true,
      linewidth: 2,
      linecolor: "black",
      mirror: true,
      ticks: "outside",
      tickwidth: 2,
    },
    yaxis: {
      title: ySpec.axisTitle,
      range: yRange || undefined,
      zeroline: true,
      zerolinecolor: "lightgray",
      gridcolor: "rgba(211,211,211,0.65)",
      showline: true,
      linewidth: 2,
      linecolor: "black",
      mirror: true,
      ticks: "outside",
      tickwidth: 2,
    },
    showlegend: true,
    legend: { x: 0.02, y: 0.98, bgcolor: "rgba(255,255,255,0.72)" },
    shapes,
    uirevision: `${rvbState.payload?.run?.moca_rv_sample_run_id || "rvbam-explorer"}:${ySpec.key}`,
    selectionrevision: selectedIdsKey(),
  };
  Plotly.react(rvbEl["rvb-segment-plot"], traces.filter(Boolean), layout, plotConfig("rvbam_segments"))
    .then(bindRvbamPlotEvents);
}

function scatterYAxisSpec() {
  const key = rvbEl["rvb-scatter-y"]?.value || "rv_kms";
  return rvbScatterYAxisOptions[key] || rvbScatterYAxisOptions.rv_kms;
}

function segmentTrace(rows, name, symbol, ignored, showErrors, size, selectedTrace, ySpec, filteredOutIds = null) {
  if (!rows.length) return null;
  const selectedpoints = selectedPointIndices(rows);
  const isFilteredOut = (row) => !ignored && !selectedTrace && filteredOutIds?.has(Number(row.moca_rv_sampling_segment_id));
  return {
    type: "scatter",
    mode: "markers",
    name,
    x: rows.map(segmentWavelengthMicron),
    y: rows.map((row) => asNumber(row[ySpec.key])),
    error_y: showErrors ? {
      type: "data",
      array: rows.map((row) => Math.max(0, asNumber(row[ySpec.errorKey]) ?? 0)),
      visible: true,
      color: "rgba(0,0,0,0.24)",
      thickness: 2.1,
      width: 3,
    } : undefined,
    marker: ignored
      ? { color: "#9c2f2f", size, symbol, line: { color: "#9c2f2f", width: 2.5 } }
      : selectedTrace
        ? { color: "#ffffff", size, symbol, opacity: 1, line: { color: "#d6a100", width: 4.2 } }
      : {
        color: rows.map((row) => isFilteredOut(row) ? "rgba(168,18,18,0.96)" : "#ffffff"),
        size: rows.map((row) => isFilteredOut(row) ? 16 : size),
        symbol: rows.map((row) => isFilteredOut(row) ? "x-thin" : symbol),
        opacity: selectedTrace ? 1 : 0.98,
        line: {
          color: rows.map((row) => isFilteredOut(row) ? "rgba(168,18,18,0.96)" : "#000000"),
          width: rows.map((row) => isFilteredOut(row) ? 2 : 2.2),
        },
      },
    customdata: rows.map((row) => Number(row.moca_rv_sampling_segment_id)),
    text: rows.map((row) => isFilteredOut(row) ? `${segmentHover(row, ySpec)}<br><b>Filtered from average</b>` : segmentHover(row, ySpec)),
    hoverinfo: "text",
    selectedpoints,
    selected: { marker: { opacity: 1 } },
    unselected: { marker: { opacity: rvbState.selectedIds ? 0.28 : 1 } },
  };
}

function filteredAverageLegendTrace() {
  return {
    type: "scatter",
    mode: "markers",
    name: "Filtered from average",
    x: [null],
    y: [null],
    marker: {
      symbol: "x-thin",
      color: "rgba(168,18,18,0.96)",
      size: 16,
      line: { color: "rgba(168,18,18,0.96)", width: 2 },
    },
    hoverinfo: "skip",
    showlegend: true,
  };
}

function rvbamLiteratureRvForYAxis(ySpec) {
  if (ySpec.key !== "rv_kms") return null;
  return normalizedRvbamLiteratureRv();
}

function normalizedRvbamLiteratureRv() {
  const literatureRv = rvbState.payload?.literatureRv;
  if (!literatureRv || typeof literatureRv !== "object") return null;
  const value = asNumber(literatureRv.radial_velocity_kms);
  if (value === null) return null;
  const uncertainty = asNumber(literatureRv.radial_velocity_kms_unc);
  return {
    ...literatureRv,
    value,
    uncertainty,
    label: literatureRv.label || (literatureRv.source === "host" ? "Literature host RV" : "Literature RV"),
  };
}

function rvbamLiteratureRvLegendTrace(literatureRv) {
  return {
    type: "scatter",
    mode: "lines",
    name: literatureRv.label,
    x: [null, null],
    y: [null, null],
    line: { color: "rgba(24, 128, 61, 0.95)", width: 3 },
    hoverinfo: "skip",
    showlegend: true,
  };
}

function rvbamLiteratureRvRangeValues(literatureRv) {
  if (!literatureRv) return [];
  const values = [literatureRv.value];
  if (literatureRv.uncertainty !== null && literatureRv.uncertainty > 0) {
    values.push(literatureRv.value - literatureRv.uncertainty, literatureRv.value + literatureRv.uncertainty);
  }
  return values;
}

function rvbamLiteratureRvErrorBand(literatureRv) {
  if (literatureRv.uncertainty === null || literatureRv.uncertainty <= 0) return null;
  return rvbamHorizontalBand(
    literatureRv.value - literatureRv.uncertainty,
    literatureRv.value + literatureRv.uncertainty,
    "rgba(112, 190, 118, 0.18)",
  );
}

function scatterAxisRange(rows, accessor, extraValues = []) {
  const values = rows
    .map(accessor)
    .concat(extraValues)
    .filter((value) => value !== null && Number.isFinite(value));
  if (!values.length) return null;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    const pad = Math.abs(min || 1) * 0.05;
    return [min - pad, max + pad];
  }
  const pad = (max - min) * 0.06;
  return [min - pad, max + pad];
}

function selectedPointIndices(rows) {
  if (!rvbState.selectedIds) return undefined;
  const indices = [];
  rows.forEach((row, index) => {
    if (rvbState.selectedIds.has(Number(row.moca_rv_sampling_segment_id))) indices.push(index);
  });
  return indices;
}

function selectedIdsKey() {
  if (!rvbState.selectedIds?.size) return "none";
  return Array.from(rvbState.selectedIds).sort((a, b) => a - b).join(",");
}

function rvbamAverageLine(y, color, width, dash) {
  return {
    type: "line",
    xref: "paper",
    x0: 0,
    x1: 1,
    yref: "y",
    y0: y,
    y1: y,
    line: { color, width, dash },
    layer: "below",
  };
}

function rvbamHorizontalBand(y0, y1, fillcolor) {
  return {
    type: "rect",
    xref: "paper",
    x0: 0,
    x1: 1,
    yref: "y",
    y0: Math.min(y0, y1),
    y1: Math.max(y0, y1),
    fillcolor,
    line: { width: 0 },
    layer: "below",
  };
}

function bindRvbamPlotEvents() {
  const plot = rvbEl["rvb-segment-plot"];
  if (!plot?.on) return;
  rebindPlotlyEvent(plot, "plotly_selected", handleRvbamPlotSelected);
  rebindPlotlyEvent(plot, "plotly_deselect", handleRvbamPlotDeselect);
  rebindPlotlyEvent(plot, "plotly_click", handleRvbamPlotClick);
}

function rebindPlotlyEvent(plot, eventName, handler) {
  if (plot.removeListener) plot.removeListener(eventName, handler);
  plot.on(eventName, handler);
}

function handleRvbamPlotSelected(event) {
  const ids = rvbamSegmentIdsFromPlotEvent(event);
  if (!ids.size) return;
  rvbState.selectedIds = ids.size ? ids : null;
  rvbState.ignorePlotlyDeselectUntil = Date.now() + 800;
  const singleId = ids.size === 1 ? Array.from(ids)[0] : null;
  if (singleId) {
    selectRvbamSegment(singleId);
    renderRvbamSummary();
    return;
  }
  renderRvbamSegmentPlot();
  renderRvbamSummary();
}

function handleRvbamPlotDeselect() {
  if (Date.now() < rvbState.ignorePlotlyDeselectUntil) return;
  rvbState.selectedIds = null;
  renderRvbamSegmentPlot();
  renderRvbamSummary();
}

function handleRvbamPlotClick(event) {
  const id = rvbamSegmentIdFromPlotPoint(event?.points?.[0]);
  if (!id) return;
  rvbState.ignorePlotlyDeselectUntil = Date.now() + 800;
  selectRvbamSegment(id);
}

function rvbamSegmentIdsFromPlotEvent(event) {
  const ids = new Set();
  for (const point of event?.points || []) {
    const id = rvbamSegmentIdFromPlotPoint(point);
    if (id) ids.add(id);
  }
  return ids;
}

function rvbamSegmentIdFromPlotPoint(point) {
  const candidates = [
    point?.customdata,
    Array.isArray(point?.data?.customdata) && Number.isInteger(point?.pointNumber)
      ? point.data.customdata[point.pointNumber]
      : null,
  ];
  for (const value of candidates) {
    const id = numberOrNull(Array.isArray(value) ? value[0] : value);
    if (id) return id;
  }
  return null;
}

function selectRvbamSegment(id) {
  rvbState.selectedSegmentId = Number(id);
  rvbState.posterior = null;
  rvbState.rebuiltCorner = null;
  rvbState.rebuiltFit = null;
  rvbState.autoRebuiltFitSegmentId = null;
  rvbState.autoRebuiltCornerSegmentId = null;
  renderRvbamSegmentsTable();
  renderRvbamSegmentPlot();
  updateRvbamUrl();
  loadRvbamSegment(id);
}

async function loadRvbamSegment(segmentId) {
  const id = Number(segmentId || rvbState.selectedSegmentId);
  if (!id) return;
  const token = ++rvbState.segmentToken;
  setRvbamStatus("Loading segment", "loading");
  const params = connectionParams();
  try {
    const payload = await fetchJsonUrl(rvbAppUrl(`api/rvbam-explorer/segment/${id}?${params.toString()}`));
    if (token !== rvbState.segmentToken) return;
    if (!payload.ok) throw new Error(payload.error || "Could not load RVBAM segment");
    rvbState.segmentDetail = payload;
    rvbState.posterior = null;
    rvbState.rebuiltCorner = null;
    rvbState.rebuiltFit = null;
    rvbState.autoRebuiltFitSegmentId = null;
    rvbState.autoRebuiltCornerSegmentId = null;
    renderRvbamSegmentDetail();
    setRvbamStatus("Segment loaded", "");
  } catch (error) {
    if (token !== rvbState.segmentToken) return;
    setRvbamStatus(error.message || "Could not load RVBAM segment", "error");
    renderRvbamSegmentError(error.message || "Could not load RVBAM segment");
  }
}

function renderRvbamSegmentDetail() {
  const detail = rvbState.segmentDetail || {};
  const segment = detail.segment || {};
  const noFsidText = segment.moca_fsid
    ? `No RVBAM figure URL found for file set ${segment.moca_fsid}`
    : "No RVBAM figure file set is attached to this segment";
  setRvbamImage("rvb-model", detail.images?.model_fit_url, noFsidText);
  setRvbamImage("rvb-corner", detail.images?.corner_url, noFsidText);
  updateRvbamLocalModelControls(detail.localModelFit || {});
  updateRvbamRebuiltCornerControls(detail.payloads || []);
  updateRvbamFigureTabs(detail);
  renderRvbamParameterOptions(detail.parameters || []);
  renderRvbamParametersTable(detail.parameters || []);
  renderRvbamPayloadTable(detail.payloads || [], detail.samplingRun || {});
  renderEmptyPosterior("Posterior not loaded");
  renderEmptyRebuiltCorner("Rebuilt corner not loaded");
  const fitStatus = detail.localModelFit || {};
  const fitMessage = fitStatus.message && (fitStatus.model_exists || fitStatus.base_exists)
    ? fitStatus.message
    : "Rebuilt fit not loaded";
  renderEmptyRebuiltFit(fitMessage);
  activateRequestedRvbamTabIfReady();
  maybeAutoLoadRvbamActiveTab();
}

function updateRvbamLocalModelControls(localModelFit) {
  const available = Boolean(localModelFit?.available);
  const fileAvailable = Boolean(localModelFit?.base_exists && localModelFit?.model_exists);
  const button = rvbEl["rvb-load-rebuilt-fit"];
  const tab = document.querySelector('[data-rvb-tab="rebuilt"]');
  if (button) {
    button.hidden = true;
    button.disabled = !available || !rvbState.selectedSegmentId;
  }
  if (tab) tab.hidden = !fileAvailable;
  if (!fileAvailable && rvbState.activeTab === "rebuilt") activateRvbamTab("fit");
}

function updateRvbamRebuiltCornerControls(payloads) {
  const available = (payloads || []).some((row) => String(row.payload_kind || "") === "chains" && !Number(row.ignored || 0));
  const button = rvbEl["rvb-load-rebuilt-corner"];
  const tab = document.querySelector('[data-rvb-tab="rebuilt-corner"]');
  if (button) {
    button.hidden = true;
    button.disabled = !available || !rvbState.selectedSegmentId;
  }
  if (tab) tab.hidden = !available;
  if (!available && rvbState.activeTab === "rebuilt-corner") activateRvbamTab("corner");
}

function updateRvbamGlobalCornerControls() {
  const button = rvbEl["rvb-load-global-corner"];
  if (!button) return;
  const tab = document.querySelector('[data-rvb-tab="global-corner"]');
  if (tab) tab.hidden = !RVB_SHOW_GLOBAL_CORNER_TAB;
  if (!RVB_SHOW_GLOBAL_CORNER_TAB) {
    button.disabled = true;
    if (rvbState.activeTab === "global-corner") ensureRvbamActiveTabVisible();
    return;
  }
  const runId = currentRvbamRunId();
  const segments = rvbState.payload?.segments || [];
  const includeIgnored = Boolean(rvbEl["rvb-include-ignored"]?.checked);
  const available = segments.some((row) => row.moca_sample_run_id && Number(row.chain_payloads || 0) > 0 && (includeIgnored || !Number(row.ignored || 0)));
  button.disabled = !runId || !available;
}

function currentRvbamRunId() {
  return numberOrNull(rvbState.payload?.run?.moca_rv_sample_run_id)
    || numberOrNull(rvbEl["rvb-run"]?.value)
    || rvbState.requestedRunId;
}

function isRvbamTabName(name) {
  return ["fit", "rebuilt", "corner", "rebuilt-corner", "global-corner", "posterior", "params", "payload", "spectrum"].includes(String(name || ""));
}

function activateRequestedRvbamTabIfReady() {
  const requested = rvbState.requestedTab;
  if (!isRvbamTabName(requested)) return;
  const button = document.querySelector(`[data-rvb-tab="${requested}"]`);
  if (!button || button.hidden) return;
  rvbState.requestedTab = null;
  if (rvbState.activeTab !== requested) activateRvbamTab(requested);
}

function maybeAutoLoadRvbamActiveTab() {
  const segmentId = Number(rvbState.selectedSegmentId);
  if (!segmentId || !rvbState.segmentDetail?.segment) return;
  const activeButton = document.querySelector(`[data-rvb-tab="${rvbState.activeTab}"]`);
  if (activeButton?.hidden) return;

  if (rvbState.activeTab === "rebuilt") {
    const available = Boolean(rvbState.segmentDetail?.localModelFit?.available);
    if (!available || rvbState.rebuiltFit || rvbState.autoRebuiltFitSegmentId === segmentId) return;
    rvbState.autoRebuiltFitSegmentId = segmentId;
    loadRvbamRebuiltFit();
  } else if (rvbState.activeTab === "rebuilt-corner") {
    if (!hasRvbamChainPayload() || rvbState.rebuiltCorner || rvbState.autoRebuiltCornerSegmentId === segmentId) return;
    rvbState.autoRebuiltCornerSegmentId = segmentId;
    loadRvbamRebuiltCorner();
  }
}

function updateRvbamFigureTabs(detail) {
  const hasOnline = hasRvbamOnlineFigureSet(detail);
  const checkbox = rvbEl["rvb-use-online-figures"];
  const row = rvbEl["rvb-use-online-figures-row"];
  if (checkbox) {
    checkbox.disabled = !hasOnline;
    if (!hasOnline) checkbox.checked = false;
  }
  if (row) row.classList.toggle("is-disabled", !hasOnline);

  const useOnline = Boolean(hasOnline && checkbox?.checked);
  setRvbamTabHidden("fit", !useOnline);
  setRvbamTabHidden("corner", !useOnline);
  setRvbamTabLabel("rebuilt", useOnline ? "Rebuild Model Fit" : "Model Fit");
  setRvbamTabLabel("rebuilt-corner", useOnline ? "Rebuild Corner Plot" : "Corner Plot");
  ensureRvbamActiveTabVisible();
}

function hasRvbamOnlineFigureSet(detail) {
  const segment = detail?.segment || {};
  const images = detail?.images || {};
  return Boolean(segment.moca_fsid || images.model_fit_url || images.corner_url);
}

function setRvbamTabHidden(name, hidden) {
  const button = document.querySelector(`[data-rvb-tab="${name}"]`);
  if (button) button.hidden = Boolean(hidden);
}

function setRvbamTabLabel(name, label) {
  const button = document.querySelector(`[data-rvb-tab="${name}"]`);
  if (button) button.textContent = label;
}

function ensureRvbamActiveTabVisible() {
  const activeButton = document.querySelector(`[data-rvb-tab="${rvbState.activeTab}"]`);
  if (activeButton && !activeButton.hidden) return;
  const fallback = firstVisibleRvbamTab();
  if (fallback) activateRvbamTab(fallback);
}

function firstVisibleRvbamTab() {
  const order = [
    "rebuilt",
    "fit",
    "rebuilt-corner",
    ...(RVB_SHOW_GLOBAL_CORNER_TAB ? ["global-corner"] : []),
    "corner",
    "posterior",
    "params",
    "payload",
    "spectrum",
  ];
  for (const name of order) {
    const button = document.querySelector(`[data-rvb-tab="${name}"]`);
    if (button && !button.hidden) return name;
  }
  return null;
}

function renderRvbamParameterOptions(parameters) {
  const names = parameters.map((row) => String(row.param_name || "")).filter(Boolean);
  const fallback = ["rv_kms", "lsf_sigma_kms", "vsini_kms"].filter((name) => !names.length || names.includes(name));
  const options = names.length ? names : fallback;
  const optionHtml = options.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
  rvbEl["rvb-param-x"].innerHTML = optionHtml || '<option value="">No parameters</option>';
  rvbEl["rvb-param-y"].innerHTML = optionHtml || '<option value="">No parameters</option>';
  const x = rvbState.requestedXParam || (options.includes("rv_kms") ? "rv_kms" : options[0]);
  const y = rvbState.requestedYParam || (options.includes("vsini_kms") ? "vsini_kms" : options[1] || options[0]);
  if (x && options.includes(x)) rvbEl["rvb-param-x"].value = x;
  if (y && options.includes(y)) rvbEl["rvb-param-y"].value = y;
  rvbEl["rvb-load-posterior"].disabled = !options.length || !rvbState.selectedSegmentId;
}

function renderRvbamParametersTable(parameters) {
  if (!parameters.length) {
    rvbEl["rvb-params-table"].innerHTML = '<div class="rvb-empty-detail">No parameters</div>';
    return;
  }
  const columns = [
    ["param_index", "Index"],
    ["param_name", "Name"],
    ["median_value", "Median"],
    ["p16_value", "P16"],
    ["p84_value", "P84"],
    ["std_value", "Std"],
    ["units", "Units"],
    ["prior_type", "Prior"],
    ["lower_bound", "Lower"],
    ["upper_bound", "Upper"],
    ["is_fixed", "Fixed"],
  ];
  rvbEl["rvb-params-table"].innerHTML = simpleTable(parameters, columns, "rvb-detail-table");
}

function renderRvbamPayloadTable(payloads, samplingRun) {
  const runRows = Object.entries(samplingRun || {})
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => ({ key, value }));
  const payloadColumns = [
    ["payload_kind", "Kind"],
    ["payload_subkind", "Subkind"],
    ["dtype", "DType"],
    ["compression", "Compression"],
    ["n_dim", "Dims"],
    ["dim1", "Dim1"],
    ["dim2", "Dim2"],
    ["dim3", "Dim3"],
    ["n_stored_samples", "Samples"],
  ];
  const samplingHtml = runRows.length ? simpleTable(runRows, [["key", "Sampling Run"], ["value", "Value"]], "rvb-detail-table") : '<div class="rvb-empty-detail">No sampling-run metadata</div>';
  const payloadHtml = payloads.length ? simpleTable(payloads, payloadColumns, "rvb-detail-table") : '<div class="rvb-empty-detail">No payload metadata</div>';
  rvbEl["rvb-payload-table"].innerHTML = `${samplingHtml}${payloadHtml}`;
}

async function loadRvbamPosterior() {
  const segmentId = Number(rvbState.selectedSegmentId);
  if (!segmentId) return;
  const token = ++rvbState.posteriorToken;
  setRvbamStatus("Loading posterior", "loading");
  rvbEl["rvb-load-posterior"].disabled = true;
  const params = connectionParams();
  const x = rvbEl["rvb-param-x"].value;
  const y = rvbEl["rvb-param-y"].value;
  if (x) params.set("x", x);
  if (y) params.set("y", y);
  params.set("max_points", String(numberInputValue("rvb-max-points", 1800)));
  try {
    const payload = await fetchJsonUrl(rvbAppUrl(`api/rvbam-explorer/segment/${segmentId}/posterior-summary?${params.toString()}`));
    if (token !== rvbState.posteriorToken) return;
    if (!payload.ok) throw new Error(payload.error || "Could not load posterior");
    rvbState.posterior = payload;
    renderRvbamPosterior();
    renderRvbamParametersTable(payload.summaries || rvbState.segmentDetail?.parameters || []);
    activateRvbamTab("posterior");
    setRvbamStatus(`${payload.meta?.returned_sample_count || 0} posterior samples shown`, "");
  } catch (error) {
    if (token !== rvbState.posteriorToken) return;
    setRvbamStatus(error.message || "Could not load posterior", "error");
    renderEmptyPosterior(error.message || "Could not load posterior");
  } finally {
    rvbEl["rvb-load-posterior"].disabled = !rvbState.selectedSegmentId;
  }
}

function renderRvbamPosterior() {
  const payload = rvbState.posterior || {};
  const samples = payload.samples || [];
  const selected = payload.selectedParams || [];
  if (!samples.length || !selected.length) {
    renderEmptyPosterior(payload.meta?.message || "No posterior samples");
    return;
  }
  const xName = selected[0];
  const yName = selected[1] || selected[0];
  const x = samples.map((row) => asNumber(row[xName])).filter((value) => value !== null);
  const y = samples.map((row) => asNumber(row[yName])).filter((value) => value !== null);
  const traces = [];
  if (xName && yName && xName !== yName && x.length && y.length) {
    traces.push({
      type: "histogram2dcontour",
      x: samples.map((row) => row[xName]),
      y: samples.map((row) => row[yName]),
      colorscale: "Greys",
      contours: { coloring: "heatmap", showlines: false },
      showscale: false,
      hoverinfo: "skip",
    });
    traces.push({
      type: "scattergl",
      mode: "markers",
      name: "Samples",
      x: samples.map((row) => row[xName]),
      y: samples.map((row) => row[yName]),
      marker: { size: 4, color: "rgba(73, 97, 107, .46)" },
      hovertemplate: `${escapeHtml(xName)}: %{x:.5g}<br>${escapeHtml(yName)}: %{y:.5g}<extra></extra>`,
    });
  } else {
    traces.push({
      type: "histogram",
      x,
      marker: { color: "#6b7379" },
      nbinsx: 44,
      hovertemplate: `${escapeHtml(xName)}: %{x:.5g}<br>N: %{y}<extra></extra>`,
    });
  }
  const layout = {
    margin: { l: 58, r: 14, t: 22, b: 50 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    xaxis: { title: xName, gridcolor: "#e3e1e6", zeroline: false },
    yaxis: { title: xName === yName ? "Count" : yName, gridcolor: "#e3e1e6", zeroline: false },
    showlegend: false,
  };
  Plotly.react(rvbEl["rvb-posterior-plot"], traces, layout, plotConfig("rvbam_posterior"));
  renderRvbamCorrelation(payload.correlation || {});
}

function renderRvbamCorrelation(correlation) {
  const labels = correlation.labels || [];
  const matrix = correlation.matrix || [];
  if (!labels.length || !matrix.length) {
    Plotly.react(rvbEl["rvb-correlation-plot"], [], emptyLayout("No correlation matrix"), plotConfig("rvbam_corr_empty"));
    return;
  }
  const trace = {
    type: "heatmap",
    x: labels,
    y: labels,
    z: matrix,
    zmin: -1,
    zmax: 1,
    colorscale: [
      [0, "#2f5f7f"],
      [0.5, "#f7f7f6"],
      [1, "#9b4b3f"],
    ],
    colorbar: { title: "r", len: 0.8 },
    hovertemplate: "%{y} vs %{x}: %{z:.3f}<extra></extra>",
  };
  const layout = {
    margin: { l: 88, r: 18, t: 20, b: 82 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    xaxis: { tickangle: -35 },
    yaxis: { automargin: true },
  };
  Plotly.react(rvbEl["rvb-correlation-plot"], [trace], layout, plotConfig("rvbam_correlation"));
}

async function loadRvbamRebuiltCorner() {
  const segmentId = Number(rvbState.selectedSegmentId);
  if (!segmentId) return;
  setRvbamStatus("Rebuilding corner plot", "loading");
  rvbEl["rvb-load-rebuilt-corner"].disabled = true;
  const params = connectionParams();
  const names = rebuiltCornerParameterNames();
  if (names.length) params.set("params", names.join(","));
  else params.set("corner", "1");
  params.set("max_params", "12");
  params.set("corner_keep_weight", "0.99");
  try {
    const payload = await fetchJsonUrl(rvbAppUrl(`api/rvbam-explorer/segment/${segmentId}/rebuilt-corner?${params.toString()}`));
    if (!payload.ok) throw new Error(payload.error || "Could not rebuild corner plot");
    rvbState.rebuiltCorner = payload;
    activateRvbamTab("rebuilt-corner");
    renderRvbamRebuiltCorner();
    setRvbamStatus(`Rebuilt corner from ${payload.meta?.returned_sample_count || 0} weighted samples`, "");
  } catch (error) {
    setRvbamStatus(error.message || "Could not rebuild corner plot", "error");
    renderEmptyRebuiltCorner(error.message || "Could not rebuild corner plot");
    activateRvbamTab("rebuilt-corner");
  } finally {
    rvbEl["rvb-load-rebuilt-corner"].disabled = !hasRvbamChainPayload();
  }
}

async function loadRvbamGlobalCorner() {
  const runId = currentRvbamRunId();
  if (!runId) return;
  const token = ++rvbState.globalCornerToken;
  setRvbamStatus("Building global corner plot", "loading");
  rvbEl["rvb-load-global-corner"].disabled = true;
  const params = connectionParams();
  if (rvbEl["rvb-include-ignored"].checked) params.set("include_ignored", "1");
  const names = rebuiltCornerParameterNames();
  if (names.length) params.set("params", names.join(","));
  params.set("max_params", "10");
  params.set("max_total_samples", "12000");
  params.set("max_segment_samples", "1200");
  params.set("corner_keep_weight", "0.99");
  try {
    const payload = await fetchJsonUrl(rvbAppUrl(`api/rvbam-explorer/run/${runId}/global-corner?${params.toString()}`));
    if (token !== rvbState.globalCornerToken) return;
    if (!payload.ok) throw new Error(payload.error || "Could not build global corner plot");
    rvbState.globalCorner = payload;
    activateRvbamTab("global-corner");
    renderRvbamGlobalCorner();
    if (payload.available) {
      setRvbamStatus(`Global corner from ${payload.meta?.returned_sample_count || 0} samples across ${payload.meta?.used_segment_count || 0} segments`, "");
    } else {
      setRvbamStatus(payload.meta?.message || "No global corner image", "error");
    }
  } catch (error) {
    if (token !== rvbState.globalCornerToken) return;
    setRvbamStatus(error.message || "Could not build global corner plot", "error");
    renderEmptyGlobalCorner(error.message || "Could not build global corner plot");
    activateRvbamTab("global-corner");
  } finally {
    updateRvbamGlobalCornerControls();
  }
}

function rebuiltCornerParameterNames() {
  const parameters = rvbState.segmentDetail?.parameters || [];
  return parameters
    .filter((row) => row.param_name && !Number(row.is_fixed || 0))
    .sort((a, b) => Number(a.param_index || 0) - Number(b.param_index || 0))
    .map((row) => String(row.param_name))
    .slice(0, 10);
}

function hasRvbamChainPayload() {
  return (rvbState.segmentDetail?.payloads || []).some((row) => String(row.payload_kind || "") === "chains" && !Number(row.ignored || 0));
}

function renderRvbamRebuiltCorner() {
  const payload = rvbState.rebuiltCorner || {};
  const image = payload.image || {};
  const params = payload.selectedParams || [];
  if (!payload.available || !image.data_url) {
    renderEmptyRebuiltCorner(payload.meta?.message || "No rebuilt corner image");
    return;
  }
  rvbEl["rvb-rebuilt-corner-plot"].style.width = "100%";
  rvbEl["rvb-rebuilt-corner-plot"].style.height = "100%";
  const layout = {
    autosize: true,
    margin: { l: 0, r: 0, t: 0, b: 0 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    showlegend: false,
    hovermode: false,
    dragmode: "zoom",
    xaxis: { visible: false, range: [0, 1], fixedrange: false, constrain: "domain" },
    yaxis: { visible: false, range: [0, 1], fixedrange: false, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
    images: [{
      source: image.data_url,
      xref: "x",
      yref: "y",
      x: 0,
      y: 1,
      sizex: 1,
      sizey: 1,
      xanchor: "left",
      yanchor: "top",
      sizing: "contain",
      layer: "above",
    }],
  };
  const traces = [{
    type: "scatter",
    mode: "markers",
    x: [0, 1],
    y: [0, 1],
    marker: { size: 1, opacity: 0 },
    hoverinfo: "skip",
    showlegend: false,
  }];
  Plotly.react(rvbEl["rvb-rebuilt-corner-plot"], traces, layout, plotConfig("rvbam_rebuilt_corner", { saveImage: true, imageScale: 4 }));
  renderRvbamRebuiltCornerMeta(payload, params);
  setTimeout(() => Plotly.Plots.resize(rvbEl["rvb-rebuilt-corner-plot"]), 0);
}

function renderRvbamGlobalCorner() {
  const payload = rvbState.globalCorner || {};
  const image = payload.image || {};
  if (!payload.available || !image.data_url) {
    renderEmptyGlobalCorner(payload.meta?.message || "No global corner image");
    return;
  }
  rvbEl["rvb-global-corner-plot"].style.width = "100%";
  rvbEl["rvb-global-corner-plot"].style.height = "100%";
  const layout = {
    autosize: true,
    margin: { l: 0, r: 0, t: 0, b: 0 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    showlegend: false,
    hovermode: false,
    dragmode: "zoom",
    xaxis: { visible: false, range: [0, 1], fixedrange: false, constrain: "domain" },
    yaxis: { visible: false, range: [0, 1], fixedrange: false, scaleanchor: "x", scaleratio: 1, constrain: "domain" },
    images: [{
      source: image.data_url,
      xref: "x",
      yref: "y",
      x: 0,
      y: 1,
      sizex: 1,
      sizey: 1,
      xanchor: "left",
      yanchor: "top",
      sizing: "contain",
      layer: "above",
    }],
  };
  const traces = [{
    type: "scatter",
    mode: "markers",
    x: [0, 1],
    y: [0, 1],
    marker: { size: 1, opacity: 0 },
    hoverinfo: "skip",
    showlegend: false,
  }];
  Plotly.react(rvbEl["rvb-global-corner-plot"], traces, layout, plotConfig("rvbam_global_corner", { saveImage: true, imageScale: 4 }));
  renderRvbamGlobalCornerMeta(payload);
  setTimeout(() => Plotly.Plots.resize(rvbEl["rvb-global-corner-plot"]), 0);
}

function rebuiltCornerSummaryMap(payload) {
  const rows = payload.summaries?.length ? payload.summaries : (rvbState.segmentDetail?.parameters || []);
  const out = new Map();
  for (const row of rows) {
    const name = String(row.param_name || row.name || "");
    if (name) out.set(name, row);
  }
  return out;
}

function cornerParamValues(samples, name) {
  return samples
    .map((sample) => asNumber(sample[name]))
    .filter((value) => value !== null && Number.isFinite(value));
}

function cornerPairValues(samples, xName, yName, xRange, yRange) {
  const x = [];
  const y = [];
  for (const sample of samples) {
    const xValue = asNumber(sample[xName]);
    const yValue = asNumber(sample[yName]);
    if (xValue === null || yValue === null) continue;
    if (!cornerInRange(xValue, xRange) || !cornerInRange(yValue, yRange)) continue;
    x.push(xValue);
    y.push(yValue);
  }
  return { x, y };
}

function cornerRobustRange(values, summary) {
  const sorted = (values || []).filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return undefined;
  let lo = quantileSorted(sorted, 0.005);
  let hi = quantileSorted(sorted, 0.995);
  const median = asNumber(summary?.sample_median ?? summary?.median_value);
  const p16 = asNumber(summary?.sample_p16 ?? summary?.p16_value);
  const p84 = asNumber(summary?.sample_p84 ?? summary?.p84_value);
  if (median !== null && p16 !== null && p84 !== null && p84 > p16) {
    const halfWidth = Math.max(p84 - p16, 1e-12);
    lo = Math.max(lo, median - 4.5 * halfWidth);
    hi = Math.min(hi, median + 4.5 * halfWidth);
  }
  if (!(hi > lo)) {
    lo = sorted[0];
    hi = sorted[sorted.length - 1];
  }
  if (!(hi > lo)) {
    const center = Number.isFinite(lo) ? lo : 0;
    return [center - 0.5, center + 0.5];
  }
  const pad = (hi - lo) * 0.055;
  return [lo - pad, hi + pad];
}

function quantileSorted(sorted, q) {
  if (!sorted.length) return null;
  const position = (sorted.length - 1) * q;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  const weight = position - lower;
  return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

function cornerInRange(value, range) {
  return Number.isFinite(value) && (!range || (value >= range[0] && value <= range[1]));
}

function cornerBinSpec(range, bins) {
  if (!range || !(range[1] > range[0])) return undefined;
  return { start: range[0], end: range[1], size: (range[1] - range[0]) / bins };
}

function cornerSummaryLabel(name, summary) {
  const median = asNumber(summary?.sample_median ?? summary?.median_value);
  const p16 = asNumber(summary?.sample_p16 ?? summary?.p16_value);
  const p84 = asNumber(summary?.sample_p84 ?? summary?.p84_value);
  if (median === null || p16 === null || p84 === null) return escapeHtml(shortParamName(name));
  const plus = Math.max(0, p84 - median);
  const minus = Math.max(0, median - p16);
  return `${escapeHtml(shortParamName(name))} = ${formatCornerNumber(median)}<br>+${formatCornerNumber(plus)} / -${formatCornerNumber(minus)}`;
}

function formatCornerNumber(value) {
  const number = asNumber(value);
  if (number === null) return "None";
  const abs = Math.abs(number);
  if (abs >= 1000 || (abs > 0 && abs < 0.001)) return number.toExponential(2);
  if (abs >= 100) return number.toFixed(1);
  if (abs >= 10) return number.toFixed(2);
  if (abs >= 1) return number.toFixed(2);
  return number.toFixed(3);
}

function renderRvbamRebuiltCornerMeta(payload, params) {
  rvbEl["rvb-rebuilt-corner-meta"].innerHTML = "";
}

function renderRvbamGlobalCornerMeta(payload) {
  rvbEl["rvb-global-corner-meta"].innerHTML = "";
}

function renderEmptyRebuiltCorner(message) {
  if (!rvbEl["rvb-rebuilt-corner-plot"]) return;
  const text = message === "Rebuilt corner not loaded"
    ? "Corner plot is being generated"
    : (message || "Rebuilt corner not loaded");
  rvbEl["rvb-rebuilt-corner-plot"].style.width = "";
  rvbEl["rvb-rebuilt-corner-plot"].style.height = "";
  Plotly.react(rvbEl["rvb-rebuilt-corner-plot"], [], emptyLayout(text), plotConfig("rvbam_rebuilt_corner_empty"));
  if (rvbEl["rvb-rebuilt-corner-meta"]) rvbEl["rvb-rebuilt-corner-meta"].innerHTML = "";
}

function renderEmptyGlobalCorner(message) {
  if (!rvbEl["rvb-global-corner-plot"]) return;
  const text = message === "Global corner not loaded"
    ? 'Global corner not loaded<br><span style="font-size:12px;">Use the Build Global Corner Plot button in this tab</span>'
    : (message || "Global corner not loaded");
  rvbEl["rvb-global-corner-plot"].style.width = "";
  rvbEl["rvb-global-corner-plot"].style.height = "";
  Plotly.react(rvbEl["rvb-global-corner-plot"], [], emptyLayout(text), plotConfig("rvbam_global_corner_empty"));
  if (rvbEl["rvb-global-corner-meta"]) rvbEl["rvb-global-corner-meta"].innerHTML = "";
}

function shortParamName(name) {
  const text = String(name || "");
  return text.length > 16 ? `${text.slice(0, 15)}...` : text;
}

async function loadRvbamRebuiltFit() {
  const segmentId = Number(rvbState.selectedSegmentId);
  if (!segmentId) return;
  setRvbamStatus("Rebuilding model fit", "loading");
  rvbEl["rvb-load-rebuilt-fit"].disabled = true;
  const params = connectionParams();
  params.set("max_data_points", "4000");
  params.set("max_model_points", "4000");
  try {
    const payload = await fetchJsonUrl(rvbAppUrl(`api/rvbam-explorer/segment/${segmentId}/rebuilt-fit?${params.toString()}`));
    if (!payload.ok) throw new Error(payload.error || "Could not rebuild model fit");
    rvbState.rebuiltFit = payload;
    renderRvbamRebuiltFit();
    activateRvbamTab("rebuilt");
    const count = payload.meta?.returned_model_point_count || 0;
    setRvbamStatus(`Rebuilt model fit loaded (${count} model points)`, "");
  } catch (error) {
    console.error("RVBAM rebuilt fit failed", error, error.payload || null);
    setRvbamStatus(error.message || "Could not rebuild model fit", "error");
    renderEmptyRebuiltFit(error.message || "Could not rebuild model fit");
    activateRvbamTab("rebuilt");
  } finally {
    rvbEl["rvb-load-rebuilt-fit"].disabled = !rvbState.segmentDetail?.localModelFit?.available;
  }
}

function renderRvbamRebuiltFit() {
  const payload = rvbState.rebuiltFit || {};
  const data = payload.data || [];
  const model = payload.model || [];
  if (!payload.available || !data.length || !model.length) {
    renderEmptyRebuiltFit(payload.meta?.message || "No rebuilt model fit");
    return;
  }
  const dataX = data.map((row) => wavelengthMicron(row.wavelength_angstrom));
  const modelX = model.map((row) => wavelengthMicron(row.wavelength_angstrom));
  const dataFlux = data.map((row) => asNumber(row.flux));
  const dataErr = data.map((row) => asNumber(row.flux_err));
  const inflatedErr = data.map((row) => asNumber(row.sigma_eff));
  const hasInflatedErr = inflatedErr.some((value) => value !== null && value > 0);
  const traces = [];
  if (hasInflatedErr) {
    traces.push({
      type: "scatter",
      mode: "markers",
      name: "Inflated err",
      x: dataX,
      y: dataFlux,
      error_y: {
        type: "data",
        array: inflatedErr.map((value) => Math.max(0, value ?? 0)),
        visible: true,
        color: "rgba(145,145,145,0.48)",
        thickness: 2.4,
        width: 3,
      },
      marker: {
        symbol: "circle-open",
        color: "rgba(0,0,0,0)",
        size: 7.2,
        line: { color: "rgba(0,0,0,0)", width: 0 },
      },
      hovertemplate: "Inflated err<br>wavelength: %{x:.6g} μm<br>flux: %{y:.5g}<extra></extra>",
    });
  }
  traces.push(
    {
      type: "scatter",
      mode: "markers",
      name: "Data",
      x: dataX,
      y: dataFlux,
      error_y: {
        type: "data",
        array: dataErr.map((value) => Math.max(0, value ?? 0)),
        visible: true,
        color: "rgba(178,178,178,0.86)",
        thickness: 2.2,
        width: 4,
      },
      marker: {
        symbol: "circle-open",
        color: "#111111",
        size: 7.2,
        line: { color: "#111111", width: 2.3 },
      },
      opacity: 1,
      hovertemplate: "Data<br>wavelength: %{x:.6g} μm<br>flux: %{y:.5g}<extra></extra>",
    },
    {
      type: "scatter",
      mode: "lines",
      name: "HDF5 rebuilt model",
      x: modelX,
      y: model.map((row) => asNumber(row.model_flux)),
      line: { color: "rgba(168,18,18,.95)", width: 2.2 },
      hovertemplate: "HDF5 rebuilt model<br>wavelength: %{x:.6g} μm<br>flux: %{y:.5g}<extra></extra>",
    },
  );
  const run = payload.run || {};
  const segment = payload.segment || {};
  const title = [
    run.designation || run.target_name || "RVBAM model fit",
    run.template_name ? basename(run.template_name) : run.moca_mgridid,
    `segment ${segment.segment_number ?? ""}`.trim(),
  ].filter(Boolean).join(" | ");
  const rebuiltFitLegend = rebuiltFitLegendPosition(dataX, dataFlux, modelX, model.map((row) => asNumber(row.model_flux)));
  const layout = {
    title: { text: title, x: 0.5, y: 0.98, xanchor: "center", yanchor: "top", font: { size: 15 } },
    margin: { l: 72, r: rebuiltFitLegend.outside ? 132 : 24, t: 54, b: 58 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    hovermode: "closest",
    xaxis: {
      title: "Wavelength (μm)",
      gridcolor: "rgba(211,211,211,0.65)",
      showline: true,
      linewidth: 2,
      linecolor: "black",
      mirror: true,
      ticks: "outside",
      tickwidth: 2,
    },
    yaxis: {
      title: "Relative flux F<sub>λ</sub>",
      gridcolor: "rgba(211,211,211,0.65)",
      zeroline: false,
      showline: true,
      linewidth: 2,
      linecolor: "black",
      mirror: true,
      ticks: "outside",
      tickwidth: 2,
      exponentformat: "power",
      showexponent: "last",
    },
    legend: rebuiltFitLegend.legend,
  };
  Plotly.react(rvbEl["rvb-rebuilt-fit-plot"], traces, layout, plotConfig("rvbam_rebuilt_fit", { saveImage: true }));
  renderRvbamRebuiltFitMeta(payload);
}

function rebuiltFitLegendPosition(dataX, dataY, modelX, modelY) {
  const dataPoints = pairFinite(dataX, dataY);
  const modelPoints = pairFinite(modelX, modelY).filter((_, index) => index % 8 === 0);
  const points = [...dataPoints.map((point) => ({ ...point, weight: 5 })), ...modelPoints.map((point) => ({ ...point, weight: 1 }))];
  if (!points.length) {
    return { outside: false, legend: plotLegend("top-left") };
  }
  const xRange = rangeFromValues(points.map((point) => point.x));
  const yRange = rangeFromValues(points.map((point) => point.y));
  if (!xRange || !yRange) {
    return { outside: false, legend: plotLegend("top-left") };
  }
  const candidates = ["top-left", "top-right", "bottom-left", "bottom-right"];
  let best = { name: candidates[0], score: Infinity };
  for (const name of candidates) {
    const score = legendOverlapScore(name, points, xRange, yRange);
    if (score < best.score) best = { name, score };
  }
  if (best.score > 28) {
    return { outside: true, legend: plotLegend("outside-right") };
  }
  return { outside: false, legend: plotLegend(best.name) };
}

function plotLegend(name) {
  const base = {
    bgcolor: "rgba(255,255,255,0.78)",
    bordercolor: "rgba(0,0,0,0)",
    borderwidth: 0,
    font: { size: 12 },
  };
  if (name === "top-right") return { ...base, x: 0.98, y: 0.98, xanchor: "right", yanchor: "top" };
  if (name === "bottom-left") return { ...base, x: 0.02, y: 0.02, xanchor: "left", yanchor: "bottom" };
  if (name === "bottom-right") return { ...base, x: 0.98, y: 0.02, xanchor: "right", yanchor: "bottom" };
  if (name === "outside-right") return { ...base, x: 1.02, y: 0.98, xanchor: "left", yanchor: "top" };
  return { ...base, x: 0.02, y: 0.98, xanchor: "left", yanchor: "top" };
}

function legendOverlapScore(name, points, xRange, yRange) {
  const xSpan = xRange[1] - xRange[0] || 1;
  const ySpan = yRange[1] - yRange[0] || 1;
  const xPad = 0.02 * xSpan;
  const yPad = 0.04 * ySpan;
  const xWidth = 0.34 * xSpan;
  const yHeight = 0.26 * ySpan;
  const isRight = name.endsWith("right");
  const isTop = name.startsWith("top");
  const x0 = isRight ? xRange[1] - xWidth - xPad : xRange[0] + xPad;
  const x1 = isRight ? xRange[1] - xPad : xRange[0] + xWidth + xPad;
  const y0 = isTop ? yRange[1] - yHeight - yPad : yRange[0] + yPad;
  const y1 = isTop ? yRange[1] - yPad : yRange[0] + yHeight + yPad;
  return points.reduce((score, point) => {
    if (point.x < x0 || point.x > x1 || point.y < y0 || point.y > y1) return score;
    return score + point.weight;
  }, 0);
}

function pairFinite(xs, ys) {
  const pairs = [];
  const count = Math.min(xs?.length || 0, ys?.length || 0);
  for (let index = 0; index < count; index += 1) {
    const x = asNumber(xs[index]);
    const y = asNumber(ys[index]);
    if (x !== null && y !== null) pairs.push({ x, y });
  }
  return pairs;
}

function rangeFromValues(values) {
  const finite = values.map(asNumber).filter((value) => value !== null);
  if (!finite.length) return null;
  let min = Math.min(...finite);
  let max = Math.max(...finite);
  if (min === max) {
    const pad = Math.abs(min || 1) * 0.05;
    min -= pad;
    max += pad;
  }
  return [min, max];
}

function renderRvbamRebuiltFitMeta(payload) {
  const theta = payload.theta || {};
  const thetaRows = Object.entries(theta).map(([key, value]) => ({ key, value }));
  const meta = payload.meta || {};
  const modelInfo = payload.localModelFit || {};
  const infoRows = [
    { key: "model_file", value: modelInfo.model_file || meta.model_file },
    { key: "grid_parameters", value: (payload.gridParameters || []).join(", ") },
    { key: "model_flux_scale", value: meta.model_flux_scale },
    { key: "model_flux_scale_source", value: meta.model_flux_scale_source },
    { key: "data_points", value: `${meta.returned_data_point_count || 0}/${meta.data_point_count || 0}` },
    { key: "model_points", value: `${meta.returned_model_point_count || 0}/${meta.model_point_count || 0}` },
  ];
  rvbEl["rvb-rebuilt-fit-meta"].innerHTML = `
    ${simpleTable(infoRows, [["key", "Rebuild"], ["value", "Value"]], "rvb-detail-table")}
    ${simpleTable(thetaRows, [["key", "Theta"], ["value", "Value"]], "rvb-detail-table")}
  `;
}

function renderEmptyRebuiltFit(message) {
  if (!rvbEl["rvb-rebuilt-fit-plot"]) return;
  const text = message === "Rebuilt fit not loaded"
    ? "Model fit is being generated"
    : (message || "Rebuilt fit not loaded");
  Plotly.react(rvbEl["rvb-rebuilt-fit-plot"], [], emptyLayout(text), plotConfig("rvbam_rebuilt_empty"));
  if (rvbEl["rvb-rebuilt-fit-meta"]) rvbEl["rvb-rebuilt-fit-meta"].innerHTML = "";
}

function renderRvbamSummary() {
  const selectedRows = selectedRvbamRows();
  const rows = filteredAverageRvbamRows(selectedRows);
  const ySpec = scatterYAxisSpec();
  const average = averageSegmentStats(rows, ySpec);
  const run = rvbState.payload?.run || {};
  const parts = [
    run.designation || run.target_name || "RVBAM run",
    averageFilterSummary(selectedRows.length, rows.length),
  ];
  if (average.n) {
    parts.push(averageStatsLabel(average, ySpec, { compactRvUncertainty: true }));
  }
  parts.push(...rvbamCorrectionSummaryParts());
  const literatureText = rvbamLiteratureRvSummaryText();
  if (literatureText) parts.push(literatureText);
  rvbEl["rvb-summary"].textContent = parts.join(" | ");
  updateRvbamReportButton();
}

function rvbamCorrectionSummaryParts() {
  const run = rvbState.payload?.run || {};
  const spectrum = rvbState.payload?.spectrum || {};
  return [
    `RVBAM BERV correction: ${rvbamPipelineBervSummary(run)}`,
    `moca_spectra.berv_corrected=${formatFlag(spectrum.berv_corrected ?? run.berv_corrected)}`,
    `moca_spectra.spacecraft_rv_corrected=${formatFlag(spectrum.spacecraft_rv_corrected ?? run.spacecraft_rv_corrected)}`,
  ];
}

function rvbamPipelineBervSummary(run) {
  const berv = asNumber(run?.berv_kms);
  if (berv === null) return "not recorded";
  if (Math.abs(berv) < 1e-9) return "recorded, no net shift (0.000 km/s)";
  return `active ${berv >= 0 ? "+" : ""}${formatFixed(berv, 3)} km/s`;
}

function rvbamLiteratureRvSummaryText() {
  const literatureRv = normalizedRvbamLiteratureRv();
  if (!literatureRv) return "";
  const unit = "km/s";
  const rounded = oneSignificantUncertaintyLabel(literatureRv.value, literatureRv.uncertainty);
  if (rounded) return `${literatureRv.label} = ${rounded.value} ${unit} +/- ${rounded.unc} ${unit}`;
  return `${literatureRv.label} = ${formatFixed(literatureRv.value, 1)} ${unit}`;
}

function updateRvbamReportButton() {
  const button = rvbEl["rvb-open-report"];
  const spectrumButton = rvbEl["rvb-open-spectrum"];
  const oid = numberOrNull(rvbState.payload?.run?.moca_oid);
  const specid = numberOrNull(rvbState.payload?.run?.moca_specid);
  if (button) button.disabled = !oid;
  if (spectrumButton) spectrumButton.disabled = !specid;
}

function openRvbamReport() {
  const oid = numberOrNull(rvbState.payload?.run?.moca_oid);
  if (!oid) return;
  const url = `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(String(oid))}%29&search-type=star`;
  window.open(url, "_blank", "noopener");
}

function openRvbamSpectrum() {
  const specid = numberOrNull(rvbState.payload?.run?.moca_specid);
  if (!specid) return;
  const currentParams = new URLSearchParams(window.location.search);
  const params = new URLSearchParams({ moca_specid: String(specid) });
  for (const key of ["mock", "host", "user", "pwd", "dbase"]) {
    if (currentParams.has(key)) params.set(key, currentParams.get(key) || "");
  }
  window.open(rvbAppUrl(`spectra?${params.toString()}`), "_blank", "noopener");
}

function selectedRvbamRows() {
  const rows = rvbState.payload?.segments || [];
  if (rvbEl["rvb-use-selection"].checked && rvbState.selectedIds?.size) {
    return rows.filter((row) => rvbState.selectedIds.has(Number(row.moca_rv_sampling_segment_id)));
  }
  return rows.filter((row) => !Number(row.ignored || 0));
}

function filteredAverageRvbamRows(rows) {
  const filters = averageFilters();
  if (!filters.active) return rows;
  return rows.filter((row) => passesAverageFilters(row, filters));
}

function averageFilteredOutRvbamRows(rows) {
  const filters = averageFilters();
  if (!filters.active) return [];
  return rows.filter((row) => !passesAverageFilters(row, filters));
}

function averageFilters() {
  const maxLsf = numberOrNull(rvbEl["rvb-max-lsf"]?.value);
  const maxBestChi2 = numberOrNull(rvbEl["rvb-max-best-chi2"]?.value);
  const maxRvUnc = numberOrNull(rvbEl["rvb-max-rv-unc"]?.value);
  return {
    maxLsf,
    maxBestChi2,
    maxRvUnc,
    active: maxLsf !== null || maxBestChi2 !== null || maxRvUnc !== null,
  };
}

function passesAverageFilters(row, filters) {
  return (
    passesMaxFilter(row.lsf, filters.maxLsf)
    && passesMaxFilter(row.best_chi2, filters.maxBestChi2)
    && passesMaxFilter(row.rv_kms_unc, filters.maxRvUnc)
  );
}

function passesMaxFilter(value, maximum) {
  if (maximum === null) return true;
  const number = asNumber(value);
  return number !== null && number <= maximum;
}

function averageFilterSummary(selectedCount, keptCount) {
  const segmentLabel = `${keptCount} segment${keptCount === 1 ? "" : "s"}`;
  if (!averageFilters().active) return segmentLabel;
  return `${segmentLabel} kept for average out of ${selectedCount}`;
}

function averageFilterNote(selectedCount, keptCount) {
  if (!averageFilters().active) return "";
  return ` (${keptCount}/${selectedCount} kept by filters)`;
}

function averageSegmentStats(rows, ySpec) {
  const values = [];
  let sw = 0;
  let swx = 0;
  let weightedN = 0;
  for (const row of rows) {
    const value = asNumber(row[ySpec.key]);
    if (value === null) continue;
    values.push(value);
    const unc = ySpec.errorKey ? asNumber(row[ySpec.errorKey]) : null;
    if (unc === null || unc <= 0) continue;
    const weight = 1 / (unc * unc);
    sw += weight;
    swx += weight * value;
    weightedN += 1;
  }
  if (!values.length) return { n: 0, mean: null, unc: null, weighted: false };
  if (weightedN && sw > 0) {
    return { n: weightedN, mean: swx / sw, unc: Math.sqrt(1 / sw), weighted: true };
  }
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  let unc = null;
  if (values.length > 1) {
    const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
    unc = Math.sqrt(variance / values.length);
  }
  return { n: values.length, mean, unc, weighted: false };
}

function averageStatsLabel(stats, ySpec, options = {}) {
  const prefix = stats.weighted ? `weighted ${ySpec.label}` : `mean ${ySpec.label}`;
  const unit = ySpec.unit ? ` ${ySpec.unit}` : "";
  const digits = Number.isFinite(ySpec.digits) ? ySpec.digits : 3;
  if (stats.unc !== null && stats.unc > 0) {
    if (options.compactRvUncertainty && ySpec.key === "rv_kms") {
      const rounded = oneSignificantUncertaintyLabel(stats.mean, stats.unc);
      if (rounded) return `${prefix} = ${rounded.value}${unit} +/- ${rounded.unc}${unit}`;
    }
    const meanText = `${formatFixed(stats.mean, digits)}${unit}`;
    return `${prefix} = ${meanText} +/- ${formatFixed(stats.unc, digits)}${unit}`;
  }
  const meanText = `${formatFixed(stats.mean, digits)}${unit}`;
  return `${prefix} = ${meanText}`;
}

function oneSignificantUncertaintyLabel(value, uncertainty) {
  const valueNumber = asNumber(value);
  const uncertaintyNumber = asNumber(uncertainty);
  if (valueNumber === null || uncertaintyNumber === null || uncertaintyNumber <= 0) return null;
  let place = 10 ** Math.floor(Math.log10(Math.abs(uncertaintyNumber)));
  let roundedUncertainty = roundToPlace(Math.abs(uncertaintyNumber), place);
  if (roundedUncertainty >= 10 * place) {
    place *= 10;
    roundedUncertainty = roundToPlace(Math.abs(uncertaintyNumber), place);
  }
  const decimals = place < 1 ? Math.max(0, -Math.floor(Math.log10(place))) : 0;
  return {
    value: roundToPlace(valueNumber, place).toFixed(decimals),
    unc: roundedUncertainty.toFixed(decimals),
  };
}

function roundToPlace(value, place) {
  return Math.round(value / place) * place;
}

function renderRvbamSegmentError(message) {
  setRvbamImage("rvb-model", "", "No model-fit image URL");
  setRvbamImage("rvb-corner", "", "No corner-plot image URL");
  updateRvbamLocalModelControls({});
  updateRvbamRebuiltCornerControls([]);
  updateRvbamFigureTabs({});
  rvbEl["rvb-params-table"].innerHTML = `<div class="rvb-empty-detail">${escapeHtml(message)}</div>`;
  rvbEl["rvb-payload-table"].innerHTML = "";
  renderEmptyPosterior(message);
  renderEmptyRebuiltCorner(message);
  renderEmptyRebuiltFit(message);
}

function renderEmptyPosterior(message) {
  const text = message === "Posterior not loaded"
    ? 'Posterior not loaded<br><span style="font-size:12px;">Use "Load Posterior" button in left panel menu</span>'
    : (message || "No posterior");
  Plotly.react(rvbEl["rvb-posterior-plot"], [], emptyLayout(text), plotConfig("rvbam_posterior_empty"));
  Plotly.react(rvbEl["rvb-correlation-plot"], [], emptyLayout("No correlation matrix"), plotConfig("rvbam_corr_empty"));
}

function renderEmptyRvbam(message) {
  rvbState.payload = null;
  rvbState.segmentDetail = null;
  rvbState.posterior = null;
  rvbState.rebuiltCorner = null;
  rvbState.globalCorner = null;
  rvbState.selectedSegmentId = null;
  renderEmptyPlot(message);
  rvbEl["rvb-summary"].textContent = message;
  updateRvbamReportButton();
  rvbEl["rvb-info"].innerHTML = "";
  rvbEl["rvb-spectrum-table"].innerHTML = "";
  rvbEl["rvb-segments-table"].innerHTML = `<div class="rvb-empty-detail">${escapeHtml(message)}</div>`;
  renderRvbamSegmentError(message);
  renderEmptyGlobalCorner(message);
  updateRvbamGlobalCornerControls();
  updateRvbamExportButtons();
}

function renderEmptyPlot(message) {
  Plotly.react(rvbEl["rvb-segment-plot"], [], emptyLayout(message), plotConfig("rvbam_segments_empty"))
    .then(bindRvbamPlotEvents);
}

function emptyLayout(message) {
  return {
    margin: { l: 42, r: 18, t: 20, b: 38 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    annotations: [{
      text: message || "No data",
      x: 0.5,
      y: 0.5,
      xref: "paper",
      yref: "paper",
      showarrow: false,
      font: { color: "#5f5864", size: 14 },
    }],
    xaxis: { visible: false },
    yaxis: { visible: false },
  };
}

function setRvbamImage(prefix, url, emptyText) {
  const link = rvbEl[`${prefix}-link`];
  const image = rvbEl[`${prefix}-image`];
  const empty = rvbEl[`${prefix}-empty`];
  const href = downloadUrl(url);
  image.onerror = null;
  image.onload = null;
  link.hidden = true;
  empty.hidden = false;
  empty.innerHTML = "";
  if (href) {
    link.href = href;
    image.dataset.rvbSrc = href;
    empty.textContent = "Loading figure...";
    image.onload = () => {
      if (image.dataset.rvbSrc !== href) return;
      link.hidden = false;
      empty.hidden = true;
      empty.innerHTML = "";
    };
    image.onerror = () => {
      if (image.dataset.rvbSrc !== href) return;
      link.hidden = true;
      image.removeAttribute("src");
      empty.hidden = false;
      empty.innerHTML = "";
      empty.textContent = emptyText || "No RVBAM figure is available";
    };
    image.src = href;
  } else {
    delete image.dataset.rvbSrc;
    image.removeAttribute("src");
    empty.textContent = emptyText;
  }
}

function activateRvbamTab(name) {
  rvbState.activeTab = name;
  document.querySelectorAll("[data-rvb-tab]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.rvbTab === name);
  });
  document.querySelectorAll(".rvb-tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `rvb-tab-${name}`);
  });
  setTimeout(() => {
    for (const id of ["rvb-posterior-plot", "rvb-correlation-plot", "rvb-rebuilt-corner-plot", "rvb-global-corner-plot", "rvb-rebuilt-fit-plot"]) {
      if (rvbEl[id]) Plotly.Plots.resize(rvbEl[id]);
    }
  }, 0);
  maybeAutoLoadRvbamActiveTab();
}

function updateRvbamExportButtons() {
  const enabled = Boolean(rvbState.payload?.segments?.length);
  for (const id of ["rvb-export-csv", "rvb-export-tsv", "rvb-export-fits", "rvb-export-votable"]) {
    rvbEl[id].disabled = !enabled;
  }
}

function exportRvbamSegments(format) {
  const rows = selectedRvbamRows();
  if (!rows.length || !window.MocaExport) return;
  const columns = [
    "moca_rv_sampling_segment_id",
    "moca_rv_sample_run_id",
    "moca_sample_run_id",
    "order_number",
    "window_number",
    "segment_number",
    "wv_min",
    "wv_max",
    "wv_center",
    "rv_kms",
    "rv_kms_unc",
    "lsf",
    "lsf_unc",
    "vsini_kms",
    "vsini_kms_unc",
    "sampler_type",
    "sampler_name",
    "sampler_variant",
    "n_iterations",
    "best_chi2",
    "lnp_median",
    "lnp_max",
    "mean_finite_fraction",
    "mean_outofbounds_fraction",
    "payload_count",
    "model_fit_url",
    "corner_url",
    "ignored",
  ];
  const numericColumns = new Set(columns.filter((column) => !["sampler_type", "sampler_name", "sampler_variant", "model_fit_url", "corner_url"].includes(column)));
  const runId = rvbState.payload?.run?.moca_rv_sample_run_id || "run";
  const suffix = rvbState.selectedIds && rvbEl["rvb-use-selection"].checked ? "selected" : "all";
  window.MocaExport.saveTable(format, {
    rows,
    columns,
    numericColumns,
    filenameBase: `rvbam_explorer_${slugify(runId)}_${suffix}`,
    tableName: "rvbam_explorer_segments",
    resourceName: "RVBAM Explorer segments",
  });
}

async function clearRvbamCache() {
  rvbEl["rvb-clear-cache-status"].textContent = "Clearing...";
  rvbEl["rvb-clear-cache-status"].classList.remove("error");
  try {
    const payload = await postJson(rvbAppUrl("api/rvbam-explorer/cache/clear"), {});
    const count = Object.values(payload.cleared || {}).reduce((sum, value) => sum + Number(value || 0), 0);
    rvbEl["rvb-clear-cache-status"].textContent = `Cleared ${count} cached payloads.`;
  } catch (error) {
    rvbEl["rvb-clear-cache-status"].textContent = error.message || "Could not clear cache";
    rvbEl["rvb-clear-cache-status"].classList.add("error");
  }
}

function updateRvbamUrl() {
  const params = new URLSearchParams(window.location.search);
  const runId = rvbEl["rvb-run"].value || rvbState.payload?.run?.moca_rv_sample_run_id;
  if (runId) params.set("run_id", String(runId)); else params.delete("run_id");
  if (rvbState.selectedSegmentId) params.set("segment_id", String(rvbState.selectedSegmentId)); else params.delete("segment_id");
  copyInputToParam(params, "q", "rvb-search");
  copyInputToParam(params, "moca_oid", "rvb-oid");
  copyInputToParam(params, "moca_specid", "rvb-specid");
  copyInputToParam(params, "pipeline", "rvb-pipeline");
  params.set("include_ignored", rvbEl["rvb-include-ignored"].checked ? "1" : "0");
  params.set("errors", rvbEl["rvb-show-errors"].checked ? "1" : "0");
  params.set("use_selection", rvbEl["rvb-use-selection"].checked ? "1" : "0");
  params.set("online_figures", rvbEl["rvb-use-online-figures"].checked && !rvbEl["rvb-use-online-figures"].disabled ? "1" : "0");
  params.set("scatter_y", scatterYAxisSpec().key);
  copyInputToParam(params, "max_lsf", "rvb-max-lsf");
  copyInputToParam(params, "max_best_chi2", "rvb-max-best-chi2");
  copyInputToParam(params, "max_rv_unc", "rvb-max-rv-unc");
  if (rvbEl["rvb-param-x"].value) params.set("x", rvbEl["rvb-param-x"].value);
  if (rvbEl["rvb-param-y"].value) params.set("y", rvbEl["rvb-param-y"].value);
  params.set("max_points", String(numberInputValue("rvb-max-points", 1800)));
  if (rvbState.activeTab && rvbState.activeTab !== "fit") params.set("tab", rvbState.activeTab);
  else params.delete("tab");
  const next = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", next);
}

function copyInputToParam(params, paramName, elementId) {
  const value = String(rvbEl[elementId].value || "").trim();
  if (value) params.set(paramName, value);
  else params.delete(paramName);
}

function connectionParams() {
  const input = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "user", "pwd", "dbase", "mock"]) {
    if (input.has(key)) params.set(key, input.get(key));
  }
  return params;
}

function simpleTable(rows, columns, className) {
  if (!rows.length) return '<div class="rvb-empty-detail">No rows</div>';
  return `
    <table class="${className || "rvb-detail-table"}">
      <thead>
        <tr>${columns.map(([, label]) => `<th>${escapeHtml(label)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>${columns.map(([key]) => `<td>${escapeHtml(formatGenericCell(row[key]))}</td>`).join("")}</tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function formatSegmentCell(row, key) {
  const value = row[key];
  if (["wv_center", "wv_min", "wv_max"].includes(key)) return formatFixed(wavelengthMicron(value), 5);
  if (["rv_kms", "rv_kms_unc", "lsf", "lsf_unc", "vsini_kms", "vsini_kms_unc", "best_chi2", "lnp_median", "lnp_max"].includes(key)) return formatFixed(value, 3);
  return displayValue(value);
}

function formatGenericCell(value) {
  const number = asNumber(value);
  if (number !== null) {
    if (Math.abs(number) >= 1000 || (Math.abs(number) > 0 && Math.abs(number) < 0.001)) return number.toExponential(4);
    return Number.isInteger(number) ? String(number) : formatFixed(number, 5);
  }
  return displayValue(value);
}

function formatFlag(value) {
  const number = asNumber(value);
  if (number === 1) return "1 (yes)";
  if (number === 0) return "0 (no)";
  if (number !== null) return String(number);
  return "unknown";
}

function segmentHover(row, ySpec) {
  const yValue = ySpec && ySpec.key !== "rv_kms"
    ? `${ySpec.label}: ${formatGenericCell(row[ySpec.key])}`
    : "";
  return [
    `Segment ${displayValue(row.segment_number)}`,
    `Order ${displayValue(row.order_number)} window ${displayValue(row.window_number)}`,
    `Wavelength ${formatFixed(segmentWavelengthMicron(row), 5)} micron`,
    yValue,
    `RV ${formatFixed(row.rv_kms, 3)} +/- ${formatFixed(row.rv_kms_unc, 3)} km/s`,
    `LSF ${formatFixed(row.lsf, 3)} km/s`,
    `vsini ${formatFixed(row.vsini_kms, 3)} km/s`,
  ].filter(Boolean).join("<br>");
}

function wavelengthRangeLabel(rows) {
  const mins = rows.map((row) => wavelengthMicron(row.wv_min)).filter((value) => value !== null);
  const maxs = rows.map((row) => wavelengthMicron(row.wv_max)).filter((value) => value !== null);
  if (!mins.length || !maxs.length) return "";
  return `${formatFixed(Math.min(...mins), 3)}-${formatFixed(Math.max(...maxs), 3)} micron`;
}

function segmentWavelengthMicron(row) {
  const center = wavelengthMicron(row?.wv_center);
  if (center !== null) return center;
  const left = wavelengthMicron(row?.wv_min);
  const right = wavelengthMicron(row?.wv_max);
  if (left === null || right === null) return null;
  return (left + right) / 2;
}

function midpoint(a, b) {
  const left = asNumber(a);
  const right = asNumber(b);
  if (left === null || right === null) return null;
  return (left + right) / 2;
}

function wavelengthMicron(value) {
  const number = asNumber(value);
  if (number === null) return null;
  return Math.abs(number) > 1000 ? number / 10000 : number;
}

function formatWithUnit(value, unit, digits) {
  const number = asNumber(value);
  if (number === null) return "";
  return `${formatFixed(number, digits ?? 3)} ${unit}`;
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") return "None";
  return String(value);
}

function basename(value) {
  const text = String(value || "");
  if (!text) return "";
  return text.split(/[\\/]/).filter(Boolean).pop() || text;
}

function numberInputValue(id, fallback) {
  const value = Number(rvbEl[id]?.value);
  return Number.isFinite(value) ? value : fallback;
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function asNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatFixed(value, digits) {
  const number = asNumber(value);
  if (number === null) return "None";
  return number.toFixed(digits);
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

function downloadUrl(url) {
  const text = String(url || "").trim();
  if (!text) return "";
  if (text.startsWith("data:") || /\/download(?:[?#].*)?$/.test(text)) return text;
  return `${text.replace(/\/+$/, "")}/download`;
}

function slugify(value) {
  return String(value || "rvbam")
    .toLowerCase()
    .replace(/[^a-z0-9_.+-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80) || "rvbam";
}

function plotConfig(name, options = {}) {
  const removeButtons = options.saveImage ? [] : ["toImage"];
  return {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: removeButtons,
    toImageButtonOptions: { format: "png", filename: name || "rvbam_explorer", scale: options.imageScale || 2 },
  };
}

function setRvbamLoading(isLoading) {
  rvbEl["rvb-plot-loader"].classList.toggle("is-visible", Boolean(isLoading));
}

function setRvbamStatus(message, kind) {
  rvbEl["rvb-status"].textContent = message || "";
  rvbEl["rvb-status"].classList.toggle("loading", kind === "loading");
  rvbEl["rvb-status"].classList.toggle("error", kind === "error");
}

async function fetchJsonUrl(url) {
  const response = await fetch(url);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    const error = new Error(payload.error || `${response.status} ${response.statusText}`);
    error.payload = payload;
    error.status = response.status;
    throw error;
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
    const error = new Error(payload.error || `${response.status} ${response.statusText}`);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function debounce(fn, wait) {
  let handle = null;
  return (...args) => {
    window.clearTimeout(handle);
    handle = window.setTimeout(() => fn(...args), wait);
  };
}
