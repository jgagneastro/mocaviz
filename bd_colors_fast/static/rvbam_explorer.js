const rvbState = {
  runs: [],
  payload: null,
  segmentDetail: null,
  posterior: null,
  rebuiltCorner: null,
  globalCorner: null,
  rebuiltFit: null,
  literatureComparison: null,
  literatureComparisonDirty: true,
  literatureComparisonLoadingKey: "",
  selectedSegmentId: null,
  selectedIds: null,
  requestedRunId: null,
  requestedSegmentId: null,
  requestedTab: null,
  requestedScatterY: "",
  requestedXParam: "",
  requestedYParam: "",
  requestedInstid: "",
  requestedMgridid: "",
  autoRebuiltFitSegmentId: null,
  autoRebuiltCornerSegmentId: null,
  loadToken: 0,
  segmentToken: 0,
  posteriorToken: 0,
  globalCornerToken: 0,
  literatureComparisonToken: 0,
  ignorePlotlyDeselectUntil: 0,
  averageFilterPreset: "",
  activeTab: "posterior",
};

const rvbEl = {};

const RVB_SHOW_GLOBAL_CORNER_TAB = false;
const rvbRvMethodLabels = {
  weighted_errors: "weighted errors",
  median_mad: "median and MAD",
  weighted_median_mad: "weighted median and weighted MAD",
};
const rvbAlwaysShowScatterYAxisKeys = new Set([
  "data_contrast",
  "model_contrast",
  "nmodel_10p_contrast",
  "noutliers_masked",
]);
const rvbRvContentMetricKeys = new Set([
  "data_contrast",
  "model_contrast",
  "nmodel_10p_contrast",
  "noutliers_masked",
  "segment_snr_median",
  "segment_snr_p10",
  "segment_snr_p90",
  "segment_snr_npoints",
]);
const rvbAverageFilterInputIds = [
  "rvb-max-lsf",
  "rvb-max-best-chi2",
  "rvb-max-rv-unc",
  "rvb-min-data-contrast",
  "rvb-min-model-contrast",
  "rvb-min-model-10p",
  "rvb-min-snr",
  "rvb-segment-wavelength",
  "rvb-max-masked-outliers",
];
const rvbFireAverageFilterDefaults = {
  "rvb-max-lsf": "30",
  "rvb-max-rv-unc": "45",
  "rvb-min-data-contrast": "0.1",
  "rvb-min-model-contrast": "0.1",
  "rvb-min-model-10p": "200",
  "rvb-min-snr": "2",
};

const rvbScatterYAxisOptions = {
  rv_kms: { key: "rv_kms", label: "RV", axisTitle: "RV (km/s)", errorKey: "rv_kms_unc", unit: "km/s", digits: 3 },
  rv_kms_unc: { key: "rv_kms_unc", label: "RV uncertainty", axisTitle: "RV uncertainty (km/s)", unit: "km/s", digits: 3 },
  lsf: { key: "lsf", label: "LSF sigma", axisTitle: "LSF sigma (km/s)", errorKey: "lsf_unc", unit: "km/s", digits: 3 },
  vsini_kms: { key: "vsini_kms", label: "v sin i", axisTitle: "v sin i (km/s)", errorKey: "vsini_kms_unc", unit: "km/s", digits: 3 },
  segment_snr_median: { key: "segment_snr_median", label: "Segment median S/N", axisTitle: "Segment median S/N per pixel", digits: 2 },
  data_contrast: { key: "data_contrast", label: "Data RV content", axisTitle: "Data RV content contrast", digits: 4 },
  model_contrast: { key: "model_contrast", label: "Model RV content", axisTitle: "Model RV content contrast", digits: 4 },
  nmodel_10p_contrast: { key: "nmodel_10p_contrast", label: "Model deep-line pixels", axisTitle: "Model pixels at least 10% below high flux", digits: 1 },
  noutliers_masked: { key: "noutliers_masked", label: "Masked line outliers", axisTitle: "Masked high-residual pixels", digits: 1 },
  best_chi2: { key: "best_chi2", label: "Best chi2", axisTitle: "Best chi2", digits: 3 },
  lnp_median: { key: "lnp_median", label: "Median log likelihood", axisTitle: "Median log likelihood", digits: 3 },
  lnp_max: { key: "lnp_max", label: "Max log likelihood", axisTitle: "Max log likelihood", digits: 3 },
  mean_finite_fraction: { key: "mean_finite_fraction", label: "Finite fraction", axisTitle: "Finite fraction", digits: 4 },
  mean_outofbounds_fraction: { key: "mean_outofbounds_fraction", label: "Out-of-bounds fraction", axisTitle: "Out-of-bounds fraction", digits: 4 },
  n_iterations: { key: "n_iterations", label: "Sampler iterations", axisTitle: "Sampler iterations", digits: 1 },
};
const rvbScatterThresholdSpecs = {
  rv_kms_unc: { filterKey: "maxRvUnc", direction: "max", label: "Max RV uncertainty" },
  lsf: { filterKey: "maxLsf", direction: "max", label: "Max LSF width" },
  segment_snr_median: { filterKey: "minSnr", direction: "min", label: "Min segment median S/N" },
  data_contrast: { filterKey: "minDataContrast", direction: "min", label: "Min data RV content" },
  model_contrast: { filterKey: "minModelContrast", direction: "min", label: "Min model RV content" },
  nmodel_10p_contrast: { filterKey: "minModel10p", direction: "min", label: "Min model deep-line pixels" },
  noutliers_masked: { filterKey: "maxMaskedOutliers", direction: "max", label: "Max masked line outliers" },
  best_chi2: { filterKey: "maxBestChi2", direction: "max", label: "Max best chi2" },
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
    "rvb-instid",
    "rvb-mgridid",
    "rvb-has-literature-rv",
    "rvb-max-literature-rv-unc",
    "rvb-wavelength-coverage",
    "rvb-min-segments",
    "rvb-max-segments",
    "rvb-min-run-snr",
    "rvb-max-resulting-rv-unc",
    "rvb-run",
    "rvb-load-runs",
    "rvb-load-run",
    "rvb-scatter-y",
    "rvb-rv-method",
    "rvb-use-selection",
    "rvb-show-errors",
    "rvb-show-hover",
    "rvb-use-online-figures",
    "rvb-use-online-figures-row",
    "rvb-include-ignored",
    "rvb-clear-selection",
    "rvb-clear-average-filters",
    "rvb-restore-average-filter-defaults",
    "rvb-max-lsf",
    "rvb-max-best-chi2",
    "rvb-max-rv-unc",
    "rvb-min-data-contrast",
    "rvb-min-model-contrast",
    "rvb-min-model-10p",
    "rvb-min-snr",
    "rvb-segment-wavelength",
    "rvb-max-masked-outliers",
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
    "rvb-info-open-report",
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
    "rvb-lit-rv-plot",
    "rvb-lit-rv-bias-plot",
    "rvb-lit-rv-bias-summary",
    "rvb-lit-rv-meta",
    "rvb-params-table",
    "rvb-payload-table",
    "rvb-clear-cache-bottom",
    "rvb-clear-cache-status",
  ].forEach((id) => {
    rvbEl[id] = document.getElementById(id);
  });
}

function rvbamShowPlotHoverText() {
  return rvbEl["rvb-show-hover"]?.checked === true;
}

function rvbamHoverInfo(enabledValue = "text") {
  return rvbamShowPlotHoverText() ? enabledValue : "none";
}

function rvbamHoverTemplate(template) {
  return rvbamShowPlotHoverText() ? template : null;
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
  if (params.has("moca_instid") || params.has("instid") || params.has("instrument")) {
    rvbState.requestedInstid = params.get("moca_instid") || params.get("instid") || params.get("instrument") || "";
    rvbEl["rvb-instid"].value = rvbState.requestedInstid;
  }
  if (params.has("moca_mgridid") || params.has("mgridid") || params.has("model_grid") || params.has("atmosphere_model") || params.has("model")) {
    rvbState.requestedMgridid = params.get("moca_mgridid") || params.get("mgridid") || params.get("model_grid") || params.get("atmosphere_model") || params.get("model") || "";
    rvbEl["rvb-mgridid"].value = rvbState.requestedMgridid;
  }
  if (params.has("has_literature_rv") || params.has("literature_rv") || params.has("lit_rv")) {
    rvbEl["rvb-has-literature-rv"].checked = asBool(params.get("has_literature_rv") || params.get("literature_rv") || params.get("lit_rv"));
  }
  if (params.has("max_literature_rv_unc") || params.has("max_literature_rv_error") || params.has("max_lit_rv_unc") || params.has("max_lit_rv_error") || params.has("max_mocadb_rv_unc")) {
    rvbEl["rvb-max-literature-rv-unc"].value = params.get("max_literature_rv_unc") || params.get("max_literature_rv_error") || params.get("max_lit_rv_unc") || params.get("max_lit_rv_error") || params.get("max_mocadb_rv_unc") || "";
  }
  if (params.has("wavelength_coverage") || params.has("wv_coverage") || params.has("coverage")) {
    rvbEl["rvb-wavelength-coverage"].value = params.get("wavelength_coverage") || params.get("wv_coverage") || params.get("coverage") || "";
  }
  if (params.has("min_segments") || params.has("min_segment_count") || params.has("min_available_segments")) {
    rvbEl["rvb-min-segments"].value = params.get("min_segments") || params.get("min_segment_count") || params.get("min_available_segments") || "";
  }
  if (params.has("max_segments") || params.has("max_segment_count") || params.has("max_available_segments")) {
    rvbEl["rvb-max-segments"].value = params.get("max_segments") || params.get("max_segment_count") || params.get("max_available_segments") || "";
  }
  if (params.has("min_run_snr") || params.has("min_run_median_snr") || params.has("min_median_snr") || params.has("min_median_snr_per_pix")) {
    rvbEl["rvb-min-run-snr"].value = params.get("min_run_snr") || params.get("min_run_median_snr") || params.get("min_median_snr") || params.get("min_median_snr_per_pix") || "";
  }
  if (params.has("max_resulting_rv_unc") || params.has("max_resulting_rv_error") || params.has("max_run_rv_unc") || params.has("max_run_rv_error") || params.has("max_rvbam_rv_unc")) {
    rvbEl["rvb-max-resulting-rv-unc"].value = params.get("max_resulting_rv_unc") || params.get("max_resulting_rv_error") || params.get("max_run_rv_unc") || params.get("max_run_rv_error") || params.get("max_rvbam_rv_unc") || "";
  }
  if (params.has("include_ignored")) rvbEl["rvb-include-ignored"].checked = asBool(params.get("include_ignored"));
  if (params.has("errors")) rvbEl["rvb-show-errors"].checked = asBool(params.get("errors"));
  if (params.has("hover_text") || params.has("show_hover") || params.has("hover")) {
    rvbEl["rvb-show-hover"].checked = asBool(params.get("hover_text") || params.get("show_hover") || params.get("hover"));
  }
  if (params.has("use_selection")) rvbEl["rvb-use-selection"].checked = asBool(params.get("use_selection"));
  if (params.has("online_figures") || params.has("use_online_figures")) {
    rvbEl["rvb-use-online-figures"].checked = asBool(params.get("online_figures") || params.get("use_online_figures"));
  }
  if ((params.get("average_filter_preset") || params.get("filter_preset")) === "none") {
    rvbState.averageFilterPreset = "none";
  }
  const scatterY = params.get("scatter_y") || params.get("y_axis");
  if (scatterY && rvbScatterYAxisOptions[scatterY]) {
    rvbState.requestedScatterY = scatterY;
    rvbEl["rvb-scatter-y"].value = scatterY;
  }
  const rvMethod = rvMethodValue(params.get("rv_method") || params.get("rv_calculation_method") || params.get("rv_stat_method"));
  if (rvbEl["rvb-rv-method"]) rvbEl["rvb-rv-method"].value = rvMethod;
  if (params.has("max_lsf")) rvbEl["rvb-max-lsf"].value = params.get("max_lsf") || "";
  if (params.has("max_best_chi2")) rvbEl["rvb-max-best-chi2"].value = params.get("max_best_chi2") || "";
  if (params.has("max_rv_unc")) rvbEl["rvb-max-rv-unc"].value = params.get("max_rv_unc") || "";
  if (params.has("min_data_contrast")) rvbEl["rvb-min-data-contrast"].value = params.get("min_data_contrast") || "";
  if (params.has("min_model_contrast")) rvbEl["rvb-min-model-contrast"].value = params.get("min_model_contrast") || "";
  if (params.has("min_model_10p")) rvbEl["rvb-min-model-10p"].value = params.get("min_model_10p") || "";
  if (params.has("min_snr")) rvbEl["rvb-min-snr"].value = params.get("min_snr") || "";
  if (params.has("segment_wavelength") || params.has("segment_wavelength_range") || params.has("segment_wv")) {
    rvbEl["rvb-segment-wavelength"].value = params.get("segment_wavelength") || params.get("segment_wavelength_range") || params.get("segment_wv") || "";
  }
  if (params.has("max_masked_outliers") || params.has("max_noutliers_masked")) rvbEl["rvb-max-masked-outliers"].value = params.get("max_masked_outliers") || params.get("max_noutliers_masked") || "";
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
    invalidateRvbamLiteratureComparison();
    await loadRvbamRuns();
    await loadSelectedRvbamRun();
  });
  const runFilterChanged = async () => {
    updateRvbamUrl();
    invalidateRvbamLiteratureComparison();
    await loadRvbamRuns();
    await loadSelectedRvbamRun();
  };
  rvbEl["rvb-instid"].addEventListener("change", async () => {
    rvbState.requestedInstid = String(rvbEl["rvb-instid"].value || "").trim();
    await runFilterChanged();
  });
  rvbEl["rvb-mgridid"].addEventListener("change", async () => {
    rvbState.requestedMgridid = String(rvbEl["rvb-mgridid"].value || "").trim();
    await runFilterChanged();
  });
  rvbEl["rvb-has-literature-rv"].addEventListener("change", runFilterChanged);
  rvbEl["rvb-wavelength-coverage"].addEventListener("input", debounce(runFilterChanged, 350));
  rvbEl["rvb-wavelength-coverage"].addEventListener("change", runFilterChanged);
  for (const id of ["rvb-max-literature-rv-unc", "rvb-min-segments", "rvb-max-segments", "rvb-min-run-snr", "rvb-max-resulting-rv-unc"]) {
    rvbEl[id].addEventListener("input", debounce(runFilterChanged, 250));
    rvbEl[id].addEventListener("change", runFilterChanged);
  }
  rvbEl["rvb-show-errors"].addEventListener("change", () => {
    renderRvbamRun();
    renderRvbamLiteratureComparison();
    updateRvbamUrl();
  });
  rvbEl["rvb-show-hover"].addEventListener("change", () => {
    renderRvbamSegmentPlot();
    renderRvbamLiteratureComparison();
    if (rvbState.posterior) renderRvbamPosterior();
    if (rvbState.rebuiltFit) renderRvbamRebuiltFit();
    updateRvbamUrl();
  });
  rvbEl["rvb-use-online-figures"].addEventListener("change", () => {
    updateRvbamFigureTabs(rvbState.segmentDetail || {});
    updateRvbamUrl();
  });
  rvbEl["rvb-scatter-y"].addEventListener("change", () => {
    rvbState.requestedScatterY = "";
    renderRvbamSegmentPlot();
    updateRvbamUrl();
  });
  rvbEl["rvb-use-selection"].addEventListener("change", () => {
    renderRvbamSegmentPlot();
    renderRvbamSummary();
    updateRvbamUrl();
  });
  rvbEl["rvb-rv-method"].addEventListener("change", () => {
    renderRvbamSegmentPlot();
    renderRvbamSummary();
    invalidateRvbamLiteratureComparison();
    updateRvbamUrl();
    if (rvbamAverageDependentRunFilterActive()) {
      loadRvbamRuns().then(loadSelectedRvbamRun);
    }
  });
  rvbEl["rvb-clear-selection"].addEventListener("click", () => {
    rvbState.selectedIds = null;
    renderRvbamSegmentPlot();
    renderRvbamSummary();
    updateRvbamUrl();
  });
  const refreshAverageFilters = () => {
    renderRvbamSegmentPlot();
    renderRvbamSummary();
    invalidateRvbamLiteratureComparison();
    updateRvbamUrl();
    if (rvbamAverageDependentRunFilterActive()) {
      loadRvbamRuns().then(loadSelectedRvbamRun);
    }
  };
  const averageFilterChanged = () => {
    rvbState.averageFilterPreset = hasAnyAverageFilterInputValue() ? "" : "none";
    refreshAverageFilters();
  };
  for (const id of rvbAverageFilterInputIds) {
    rvbEl[id].addEventListener("input", debounce(averageFilterChanged, 120));
    rvbEl[id].addEventListener("change", averageFilterChanged);
  }
  rvbEl["rvb-clear-average-filters"].addEventListener("click", () => {
    clearAverageFilterInputValues();
    rvbState.averageFilterPreset = "none";
    refreshAverageFilters();
  });
  rvbEl["rvb-restore-average-filter-defaults"].addEventListener("click", () => {
    applyRvbamRunDefaultAverageFilters(currentRvbamRunForDefaults(), { force: true });
    refreshAverageFilters();
  });
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
  rvbEl["rvb-info-open-report"].addEventListener("click", openRvbamReport);
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
    for (const id of ["rvb-segment-plot", "rvb-posterior-plot", "rvb-correlation-plot", "rvb-rebuilt-corner-plot", "rvb-global-corner-plot", "rvb-rebuilt-fit-plot", "rvb-lit-rv-plot", "rvb-lit-rv-bias-plot"]) {
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
    const runIds = new Set(rvbState.runs.map((row) => Number(row.moca_rv_sample_run_id)).filter(Number.isFinite));
    if (rvbState.requestedRunId && !runIds.has(Number(rvbState.requestedRunId))) {
      rvbState.requestedRunId = null;
      rvbState.requestedSegmentId = null;
      rvbState.selectedSegmentId = null;
      rvbState.selectedIds = null;
    }
    renderRvbamInstrumentOptions(payload.instrumentOptions || instrumentOptionsFromRuns(rvbState.runs));
    renderRvbamModelOptions(Array.isArray(payload.modelOptions) ? payload.modelOptions : modelOptionsFromRuns(rvbState.runs));
    renderRvbamRunOptions(payload.value);
    setRvbamStatus(`${rvbState.runs.length} runs${rvbamSkippedFilterSuffix(payload)}`, "");
  } catch (error) {
    rvbState.runs = [];
    renderRvbamInstrumentOptions([]);
    renderRvbamModelOptions([]);
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
  const instid = String(rvbEl["rvb-instid"].value || "").trim();
  const mgridid = String(rvbEl["rvb-mgridid"].value || "").trim();
  const minSegments = String(rvbEl["rvb-min-segments"].value || "").trim();
  const maxSegments = String(rvbEl["rvb-max-segments"].value || "").trim();
  const minRunSnr = String(rvbEl["rvb-min-run-snr"].value || "").trim();
  const maxLiteratureRvUnc = String(rvbEl["rvb-max-literature-rv-unc"].value || "").trim();
  const maxResultingRvUnc = String(rvbEl["rvb-max-resulting-rv-unc"].value || "").trim();
  if (query) params.set("q", query);
  if (oid) params.set("moca_oid", oid);
  if (specid) params.set("moca_specid", specid);
  if (pipeline) params.set("pipeline", pipeline);
  if (instid) params.set("moca_instid", instid);
  if (mgridid) params.set("moca_mgridid", mgridid);
  if (minSegments) params.set("min_segments", minSegments);
  if (maxSegments) params.set("max_segments", maxSegments);
  if (minRunSnr) params.set("min_run_snr", minRunSnr);
  if (maxLiteratureRvUnc) params.set("max_literature_rv_unc", maxLiteratureRvUnc);
  if (maxResultingRvUnc) params.set("max_resulting_rv_unc", maxResultingRvUnc);
  if (rvbEl["rvb-has-literature-rv"].checked) params.set("has_literature_rv", "1");
  const wavelengthCoverage = String(rvbEl["rvb-wavelength-coverage"].value || "").trim();
  if (wavelengthCoverage) params.set("wavelength_coverage", wavelengthCoverage);
  if (rvbEl["rvb-include-ignored"].checked) params.set("include_ignored", "1");
  appendRvbamAverageFilterParams(params);
  params.set("limit", "500");
  return params;
}

function appendRvbamAverageFilterParams(params) {
  params.set("rv_method", selectedRvMethod());
  const mappings = [
    ["max_lsf", "rvb-max-lsf"],
    ["max_best_chi2", "rvb-max-best-chi2"],
    ["max_rv_unc", "rvb-max-rv-unc"],
    ["min_data_contrast", "rvb-min-data-contrast"],
    ["min_model_contrast", "rvb-min-model-contrast"],
    ["min_model_10p", "rvb-min-model-10p"],
    ["min_snr", "rvb-min-snr"],
    ["segment_wavelength", "rvb-segment-wavelength"],
    ["max_masked_outliers", "rvb-max-masked-outliers"],
  ];
  for (const [paramName, elementId] of mappings) {
    const value = String(rvbEl[elementId]?.value || "").trim();
    if (value) params.set(paramName, value);
    else params.delete(paramName);
  }
}

function rvbamAverageDependentRunFilterActive() {
  return Boolean(
    String(rvbEl["rvb-min-segments"]?.value || "").trim()
    || String(rvbEl["rvb-max-segments"]?.value || "").trim()
    || String(rvbEl["rvb-max-resulting-rv-unc"]?.value || "").trim()
  );
}

function rvMethodValue(raw) {
  const value = String(raw || "").trim().toLowerCase();
  const aliases = {
    "": "weighted_errors",
    default: "weighted_errors",
    weighted: "weighted_errors",
    weighted_error: "weighted_errors",
    weighted_errors: "weighted_errors",
    weighted_mean: "weighted_errors",
    median: "median_mad",
    mad: "median_mad",
    median_mad: "median_mad",
    median_and_mad: "median_mad",
    weighted_median: "weighted_median_mad",
    weighted_mad: "weighted_median_mad",
    weighted_median_mad: "weighted_median_mad",
    weighted_median_and_mad: "weighted_median_mad",
  };
  return aliases[value] || "weighted_errors";
}

function selectedRvMethod() {
  return rvMethodValue(rvbEl["rvb-rv-method"]?.value);
}

function instrumentOptionsFromRuns(rows) {
  const counts = new Map();
  for (const row of rows || []) {
    const instid = String(row.moca_instid || "").trim();
    if (!instid) continue;
    counts.set(instid, (counts.get(instid) || 0) + 1);
  }
  return [...counts.entries()]
    .sort(([left], [right]) => left.localeCompare(right, undefined, { sensitivity: "base" }))
    .map(([value, count]) => ({ value, label: `${value} (${count})`, run_count: count }));
}

function modelOptionsFromRuns(rows) {
  const counts = new Map();
  for (const row of rows || []) {
    const mgridid = String(row.moca_mgridid || "").trim();
    if (!mgridid) continue;
    counts.set(mgridid, (counts.get(mgridid) || 0) + 1);
  }
  return [...counts.entries()]
    .sort(([left], [right]) => left.localeCompare(right, undefined, { sensitivity: "base" }))
    .map(([value, count]) => ({ value, label: `${value} (${count})`, run_count: count }));
}

function renderRvbamInstrumentOptions(options) {
  const current = String(rvbEl["rvb-instid"].value || rvbState.requestedInstid || "").trim();
  const rows = Array.isArray(options) ? options.slice() : [];
  const hasCurrent = rows.some((row) => String(row.value || "") === current);
  if (current && !hasCurrent) {
    rows.unshift({ value: current, label: `${current} (selected)` });
  }
  rvbEl["rvb-instid"].innerHTML = [
    '<option value="">All instruments</option>',
    ...rows.map((row) => {
      const value = String(row.value || "").trim();
      const label = row.label || value;
      return value ? `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>` : "";
    }),
  ].join("");
  rvbEl["rvb-instid"].value = current;
  rvbState.requestedInstid = current;
}

function renderRvbamModelOptions(options) {
  const current = String(rvbEl["rvb-mgridid"].value || rvbState.requestedMgridid || "").trim();
  const rows = Array.isArray(options) ? options.slice() : [];
  const hasCurrent = rows.some((row) => String(row.value || "") === current);
  if (current && !hasCurrent) {
    rows.unshift({ value: current, label: `${current} (0)`, run_count: 0 });
  }
  rvbEl["rvb-mgridid"].innerHTML = [
    '<option value="">All atmosphere models</option>',
    ...rows.map((row) => {
      const value = String(row.value || "").trim();
      const label = row.label || value;
      return value ? `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>` : "";
    }),
  ].join("");
  rvbEl["rvb-mgridid"].value = current;
  rvbState.requestedMgridid = current;
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
  const count = Number(firstPresent(row.available_segment_count, row.segment_count, 0) || 0);
  const linkedCount = Number(row.segment_count || 0);
  const headerCount = Number(row.nsegments || 0);
  const runSnr = asNumber(row.median_snr_per_pix);
  const resultingRvUnc = asNumber(firstPresent(row.resulting_rv_kms_unc, row.filtered_rv_kms_unc));
  let countText = count ? `${count} available segments` : "no available segments";
  if (count && linkedCount && linkedCount !== count) countText = `${count} available / ${linkedCount} linked segments`;
  if (!count && linkedCount) countText = `0 available / ${linkedCount} linked segments`;
  if (!linkedCount && headerCount) countText = `${count} available, header says ${headerCount}`;
  const snrText = runSnr !== null ? `S/N ${formatFixed(runSnr, 1)}` : "S/N unavailable";
  const rvErrorText = resultingRvUnc !== null ? `RV err ${formatFixed(resultingRvUnc, 2)} km/s` : "";
  const lastAdded = formatTimestampShort(row.latest_segment_created_timestamp);
  const timestampText = lastAdded ? `last RV ${lastAdded}` : "no RV timestamp";
  return [name, spec, template, version, countText, rvErrorText, snrText, timestampText].filter(Boolean).join(" | ");
}

function rvbamSkippedFilterSuffix(payload) {
  const skipped = payload?.meta?.segment_count_filters_skipped || payload?.meta?.segment_filter_columns_skipped || [];
  if (!skipped.length) return "";
  return `; metric filters unavailable: ${skipped.join(", ")}`;
}

function rvbamRvContentStatusSuffix(payload) {
  const summary = rvbamRvContentSummary(payload?.meta || {});
  return summary ? `; ${summary}` : "";
}

function rvbamRvContentSummary(meta) {
  const diagnostics = meta?.rv_content_diagnostics || {};
  if (!Object.keys(diagnostics).length) return "";
  const total = Number(diagnostics.segment_count || 0);
  const withAny = Number(diagnostics.segments_with_any_metric || 0);
  const missing = Array.isArray(diagnostics.missing_columns) ? diagnostics.missing_columns : [];
  const missingMetrics = missing.filter((column) => rvbRvContentMetricKeys.has(column));
  if (missingMetrics.length) {
    return `RV content metric DB columns missing: ${missingMetrics.join(", ")}`;
  }
  if (!total) return "";
  if (withAny === total) return `RV content metrics stored for ${withAny}/${total} segments`;
  if (withAny > 0) return `RV content metrics stored for ${withAny}/${total} segments`;
  return "RV content metrics unavailable in MOCAdb";
}

function renderScatterYAxisOptions(rows) {
  if (!rvbEl["rvb-scatter-y"]) return;
  const previous = rvbState.requestedScatterY || rvbEl["rvb-scatter-y"].value || "rv_kms";
  const available = availableScatterYAxisSpecs(rows);
  rvbEl["rvb-scatter-y"].innerHTML = available.map((spec) => {
    const baseLabel = spec.unit ? `${spec.label} (${spec.unit})` : spec.label;
    const label = scatterYAxisHasValues(rows, spec) || !rvbAlwaysShowScatterYAxisKeys.has(spec.key)
      ? baseLabel
      : `${baseLabel} (not stored)`;
    return `<option value="${escapeHtml(spec.key)}">${escapeHtml(label)}</option>`;
  }).join("");
  if (available.some((spec) => spec.key === previous)) {
    rvbEl["rvb-scatter-y"].value = previous;
    rvbState.requestedScatterY = "";
  } else if (available.some((spec) => spec.key === "rv_kms")) {
    rvbEl["rvb-scatter-y"].value = "rv_kms";
  } else if (available.length) {
    rvbEl["rvb-scatter-y"].value = available[0].key;
  }
}

function availableScatterYAxisSpecs(rows) {
  const specs = Object.values(rvbScatterYAxisOptions);
  if (!rows?.length) return specs;
  const available = specs.filter((spec) => (
    rvbAlwaysShowScatterYAxisKeys.has(spec.key)
    || scatterYAxisHasValues(rows, spec)
  ));
  return available.length ? available : [rvbScatterYAxisOptions.rv_kms];
}

function scatterYAxisHasValues(rows, spec) {
  if (!rows?.length) return true;
  return rows.some((row) => asNumber(row[spec.key]) !== null);
}

async function loadSelectedRvbamRun() {
  const runId = numberOrNull(rvbEl["rvb-run"].value) || rvbState.requestedRunId;
  if (!runId) {
    rvbState.payload = null;
    rvbState.segmentDetail = null;
    rvbState.posterior = null;
    rvbState.rebuiltCorner = null;
    rvbState.globalCorner = null;
    rvbState.rebuiltFit = null;
    rvbState.selectedIds = null;
    rvbState.selectedSegmentId = null;
    renderEmptyRvbam("No RVBAM run selected");
    updateRvbamUrl();
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
    const averageDefaultsChanged = applyRvbamRunDefaultAverageFilters(payload.run || {});
    if (averageDefaultsChanged) invalidateRvbamLiteratureComparison();
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
    setRvbamStatus(`${segments.length} segments${rvbamRvContentStatusSuffix(payload)}`, "");
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
  renderRvbamLiteratureComparison();
  renderRvbamSummary();
  updateRvbamGlobalCornerControls();
  if (!rvbState.globalCorner) renderEmptyGlobalCorner("Global corner not loaded");
  updateRvbamExportButtons();
}

function renderRvbamInfo() {
  const run = rvbState.payload?.run || {};
  const segments = rvbState.payload?.segments || [];
  const spectrum = rvbState.payload?.spectrum || {};
  const meta = rvbState.payload?.meta || {};
  const oldestRvTimestamp = firstPresent(meta.oldest_segment_created_timestamp, run.oldest_segment_created_timestamp);
  const latestRvTimestamp = firstPresent(meta.latest_segment_created_timestamp, run.latest_segment_created_timestamp);
  const latestModifiedTimestamp = firstPresent(meta.latest_segment_modified_timestamp, run.latest_segment_modified_timestamp);
  const bervStatus = rvbamBervStatus(run, spectrum);
  const bervMetadata = bervStatus.metadata || {};
  const literatureRv = rvbState.payload?.literatureRv || null;
  const bervEntries = [
    ["BERV status", bervStatus.shortLabel],
    ["RVBAM BERV", bervStatus.correctionLabel],
    ["BERV source", bervMetadata.berv_source],
    ["BERV epoch MJD", bervMetadata.berv_epoch_mjd],
    ["BERV coord source", bervMetadata.berv_coord_source],
    ["BERV location", bervMetadata.berv_location],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "");
  const entries = [
    ["Target", run.designation || run.target_name],
    ["OID", run.moca_oid],
    ["SpecID", run.moca_specid],
    ["Instrument", run.moca_instid],
    ["Pipeline", run.pipeline_version || run.rv_pipeline_version],
    ["Template", basename(run.template_name)],
    ["Model Grid", run.moca_mgridid],
    ["Segments", segments.length],
    ["MOCAdb RV", literatureRv ? rvbamLiteratureRvInfoText(literatureRv) : formatFlag(run.has_literature_rv)],
    ["MOCAdb RV source", rvbamLiteratureRvSourceLabel(literatureRv)],
    ["MOCAdb RV note", rvbamLiteratureRvFallbackNote(literatureRv)],
    ["Oldest RV added", formatTimestamp(oldestRvTimestamp)],
    ["Latest RV added", formatTimestamp(latestRvTimestamp)],
    ["Latest RV modified", formatTimestamp(latestModifiedTimestamp)],
    ["RV content metrics", rvbamRvContentSummary(meta)],
    ...bervEntries,
    ["moca_spectra BERV corrected", formatFlag(spectrum.berv_corrected ?? run.berv_corrected)],
    ["Spacecraft RV corrected", formatFlag(spectrum.spacecraft_rv_corrected ?? run.spacecraft_rv_corrected)],
    ["Wavelength", wavelengthRangeLabel(segments)],
  ];
  rvbEl["rvb-info"].innerHTML = entries.map(([key, value]) => `
    <div class="rvb-info-item">
      <span>${escapeHtml(key)}</span>
      <strong>${renderRvbamInfoValue(key, value)}</strong>
    </div>
  `).join("");
}

function renderRvbamInfoValue(key, value) {
  if (key === "OID") {
    const oid = numberOrNull(value);
    if (oid) {
      return `<a class="rvb-info-link" href="${escapeHtml(rvbamMocaReportUrl(oid))}" target="_blank" rel="noopener">${escapeHtml(displayValue(value))}</a>`;
    }
  }
  if (key === "SpecID") {
    const specid = numberOrNull(value);
    if (specid) {
      return `<a class="rvb-info-link" href="${escapeHtml(rvbamSpectrumExplorerUrl(specid))}" target="_blank" rel="noopener">${escapeHtml(displayValue(value))}</a>`;
    }
  }
  return escapeHtml(displayValue(value));
}

function rvbamLiteratureRvInfoText(literatureRv) {
  if (!literatureRv) return "";
  const value = uncertaintyText(literatureRv.radial_velocity_kms, literatureRv.radial_velocity_kms_unc, "km/s", 2);
  return literatureRv.label ? `${literatureRv.label}: ${value}` : value;
}

function rvbamLiteratureRvSourceLabel(literatureRv) {
  if (!literatureRv) return "";
  const method = literatureRv.rv_combination_method_label || (literatureRv.is_raw_fallback ? "Ad hoc weighted raw RV fallback" : "");
  const count = numberOrNull(literatureRv.raw_rv_row_count);
  if (literatureRv.is_raw_fallback) {
    const countText = count ? ` (${count} raw row${count === 1 ? "" : "s"})` : "";
    return `${method || "Ad hoc weighted raw RV fallback"}${countText}`;
  }
  if (literatureRv.source === "host") return method || "MOCAdb combined host RV";
  return method || "MOCAdb combined RV";
}

function rvbamLiteratureRvFallbackNote(literatureRv) {
  if (!literatureRv?.is_raw_fallback) return "";
  const count = numberOrNull(literatureRv.raw_rv_row_count);
  if (literatureRv.fallback_reason) return literatureRv.fallback_reason;
  const countText = count ? ` from ${count} non-ignored raw row${count === 1 ? "" : "s"}` : "";
  return `Fallback because no combined RV row was found; using an ad hoc weighted combination${countText} in data_radial_velocities.`;
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
    ["segment_snr_median", "S/N"],
    ["data_contrast", "Data RV C"],
    ["model_contrast", "Model RV C"],
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
  const filteredActiveRows = activeRows.filter((row) => filteredOutIds.has(Number(row.moca_rv_sampling_segment_id)));
  const validActiveRows = activeRows.filter((row) => !filteredOutIds.has(Number(row.moca_rv_sampling_segment_id)));
  const xRangeRows = rows.length ? rows : averageRows;
  const yRangeRows = averageRows.length ? averageRows : selectedRows;
  const traces = [];
  if (filteredActiveRows.length) {
    traces.push(segmentTrace(filteredActiveRows, "Filtered from average", "x-thin", false, showErrors, 14, false, ySpec, { filtered: true }));
  }
  traces.push(segmentTrace(validActiveRows, "Segments", "circle", false, showErrors, 8, false, ySpec));
  if (ignoredRows.length) traces.push(segmentTrace(ignoredRows, "Ignored", "x-thin", true, showErrors, 13, false, ySpec));
  const selected = rows.filter((row) => {
    const id = Number(row.moca_rv_sampling_segment_id);
    return id === Number(rvbState.selectedSegmentId) && !filteredOutIds.has(id);
  });
  if (selected.length) traces.push(segmentTrace(selected, "Selected", "star", false, showErrors, 18, true, ySpec));
  const literatureRv = rvbamLiteratureRvForYAxis(ySpec);
  if (literatureRv) traces.push(rvbamLiteratureRvLegendTrace(literatureRv));
  const yThreshold = rvbamScatterYAxisThreshold(ySpec);
  if (yThreshold) traces.push(rvbamScatterThresholdLegendTrace(yThreshold));
  const shapes = [];
  if (yThreshold) shapes.push(rvbamScatterThresholdLine(yThreshold));
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
  const xRange = scatterAxisRange(xRangeRows, (row) => segmentWavelengthMicron(row));
  const yExtraValues = ySpec.key === "rv_kms" ? rvbamLiteratureRvRangeValues(literatureRv) : [];
  if (yThreshold) yExtraValues.push(yThreshold.value);
  const yRange = scatterAxisRange(
    yRangeRows,
    (row) => asNumber(row[ySpec.key]),
    yExtraValues,
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

function invalidateRvbamLiteratureComparison() {
  rvbState.literatureComparison = null;
  rvbState.literatureComparisonDirty = true;
  if (rvbState.activeTab === "literature") {
    ensureRvbamLiteratureComparisonLoaded();
  }
}

function rvbamLiteratureComparisonParams() {
  const params = rvbamRunQueryParams();
  appendRvbamAverageFilterParams(params);
  return params;
}

function ensureRvbamLiteratureComparisonLoaded() {
  if (!rvbEl["rvb-lit-rv-plot"]) return;
  if (rvbState.literatureComparison && !rvbState.literatureComparisonDirty) {
    renderRvbamLiteratureComparison();
    return;
  }
  loadRvbamLiteratureComparison();
}

async function loadRvbamLiteratureComparison() {
  if (!rvbEl["rvb-lit-rv-plot"]) return;
  const params = rvbamLiteratureComparisonParams();
  const loadingKey = params.toString();
  if (rvbState.literatureComparisonLoadingKey === loadingKey) return;
  const token = ++rvbState.literatureComparisonToken;
  rvbState.literatureComparisonLoadingKey = loadingKey;
  rvbState.literatureComparisonDirty = false;
  renderEmptyLiteratureComparison("Loading literature comparison");
  if (rvbEl["rvb-lit-rv-meta"]) rvbEl["rvb-lit-rv-meta"].textContent = "Loading comparison...";
  setRvbamStatus("Loading literature comparison", "loading");
  try {
    const payload = await fetchJsonUrl(rvbAppUrl(`api/rvbam-explorer/literature-comparison?${params.toString()}`));
    if (token !== rvbState.literatureComparisonToken) return;
    if (!payload.ok) throw new Error(payload.error || "Could not load literature comparison");
    rvbState.literatureComparison = payload;
    renderRvbamLiteratureComparison();
    const count = (payload.points || []).length;
    setRvbamStatus(`${count} literature comparison points`, "");
  } catch (error) {
    if (token !== rvbState.literatureComparisonToken) return;
    rvbState.literatureComparison = null;
    rvbState.literatureComparisonDirty = true;
    renderEmptyLiteratureComparison(error.message || "Could not load literature comparison");
    setRvbamStatus(error.message || "Could not load literature comparison", "error");
  } finally {
    if (rvbState.literatureComparisonLoadingKey === loadingKey) rvbState.literatureComparisonLoadingKey = "";
  }
}

function renderRvbamLiteratureComparison() {
  if (!rvbEl["rvb-lit-rv-plot"]) return;
  const payload = rvbState.literatureComparison;
  if (!payload) {
    const message = rvbState.literatureComparisonLoadingKey
      ? "Loading literature comparison"
      : "Literature comparison not loaded";
    renderEmptyLiteratureComparison(message);
    return;
  }
  renderRvbamLiteratureComparisonPlot(payload);
  renderRvbamLiteratureBiasPlot(payload);
  const comparisonPoints = rvbamLiteraturePointsForActiveModelFilter(payload.points || []);
  const plottedCount = comparisonPoints.filter((point) => (
    asNumber(point.literature_rv_kms) !== null
    && asNumber(point.rvbam_rv_kms) !== null
  )).length;
  const biasCount = rvbamLiteratureRunBiasPoints(payload).length;
  updateRvbamLiteratureComparisonMeta(payload, plottedCount, biasCount);
}

function renderRvbamLiteratureComparisonPlot(payload) {
  const allPoints = rvbamLiteraturePointsForActiveModelFilter(payload.points || []);
  const points = allPoints.filter((point) => (
    asNumber(point.literature_rv_kms) !== null
    && asNumber(point.rvbam_rv_kms) !== null
  ));
  if (!points.length) {
    const meta = payload.meta || {};
    const candidateCount = Number(meta.candidate_run_count || 0);
    renderEmptyLiteratureRvPlot(candidateCount ? "No filtered runs have both RVBAM and literature RVs" : "No runs match the current filters");
    return;
  }

  const selectedRunId = currentRvbamRunId();
  const selectedPoints = points.filter((point) => Number(point.moca_rv_sample_run_id) === Number(selectedRunId));
  const regularPoints = points.filter((point) => Number(point.moca_rv_sample_run_id) !== Number(selectedRunId));
  const linearFit = rvbamRobustWeightedLiteratureComparisonFit(points);
  const axisRange = rvbamLiteratureComparisonAxisRange(points, linearFit);
  const traces = [];
  if (linearFit) traces.push(rvbamLiteratureComparisonFitTrace(linearFit));
  if (regularPoints.length) traces.push(rvbamLiteratureComparisonTrace(regularPoints, "Filtered runs", false));
  if (selectedPoints.length) traces.push(rvbamLiteratureComparisonTrace(selectedPoints, "Current run", true));
  const layout = {
    title: { text: "RVBAM RV vs Literature RV", x: 0.5, y: 0.965, xanchor: "center", yanchor: "top", font: { size: 13 } },
    margin: { l: 62, r: 24, t: 46, b: 58 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    hovermode: "closest",
    clickmode: "event",
    xaxis: {
      title: "Literature RV (km/s)",
      range: axisRange || undefined,
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
    yaxis: {
      title: "RVBAM RV (km/s)",
      range: axisRange || undefined,
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
    legend: { x: 0.02, y: 0.98, bgcolor: "rgba(255,255,255,0.74)" },
    shapes: axisRange ? [{
      type: "line",
      xref: "x",
      yref: "y",
      x0: axisRange[0],
      x1: axisRange[1],
      y0: axisRange[0],
      y1: axisRange[1],
      line: { color: "rgba(0,0,0,0.58)", width: 2, dash: "dash" },
      layer: "below",
    }] : [],
    uirevision: `rvbam-lit-comparison:${rvbamLiteratureComparisonSignature()}`,
  };
  Plotly.react(rvbEl["rvb-lit-rv-plot"], traces, layout, plotConfig("rvbam_literature_comparison"))
    .then(bindRvbamLiteratureComparisonEvents);
}

function renderRvbamLiteratureBiasPlot(payload) {
  const points = rvbamLiteratureRunBiasPoints(payload);
  if (!points.length) {
    renderEmptyLiteratureBiasPlot("No combined RV residuals with observation dates");
    return;
  }

  const selectedRunId = currentRvbamRunId();
  const selectedPoints = points.filter((point) => Number(point.moca_rv_sample_run_id) === Number(selectedRunId));
  const regularPoints = points.filter((point) => Number(point.moca_rv_sample_run_id) !== Number(selectedRunId));
  const linearFit = rvbamRobustWeightedLiteratureBiasFit(points);
  renderRvbamLiteratureBiasSummary(points, linearFit);
  const xRange = rvbamLiteratureBiasTimeRange(points);
  const yRange = rvbamLiteratureBiasRange(points, linearFit);
  const traces = [];
  if (linearFit) traces.push(rvbamLiteratureBiasFitTrace(linearFit));
  if (regularPoints.length) traces.push(rvbamLiteratureBiasTrace(regularPoints, "Filtered runs", false));
  if (selectedPoints.length) traces.push(rvbamLiteratureBiasTrace(selectedPoints, "Current run", true));
  const layout = {
    title: { text: "Combined RV - Literature RV vs Decimal Year", x: 0.5, y: 0.965, xanchor: "center", yanchor: "top", font: { size: 13 } },
    margin: { l: 62, r: 24, t: 46, b: 58 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    hovermode: "closest",
    clickmode: "event",
    xaxis: {
      title: "Year",
      range: xRange || undefined,
      tickformat: ".1f",
      hoverformat: ".4f",
      separatethousands: false,
      zeroline: false,
      gridcolor: "rgba(211,211,211,0.65)",
      showline: true,
      linewidth: 2,
      linecolor: "black",
      mirror: true,
      ticks: "outside",
      tickwidth: 2,
    },
    yaxis: {
      title: "RVBAM - Literature RV (km/s)",
      range: yRange || undefined,
      zeroline: false,
      gridcolor: "rgba(211,211,211,0.65)",
      showline: true,
      linewidth: 2,
      linecolor: "black",
      mirror: true,
      ticks: "outside",
      tickwidth: 2,
    },
    showlegend: false,
    shapes: [{
      type: "line",
      xref: "paper",
      x0: 0,
      x1: 1,
      yref: "y",
      y0: 0,
      y1: 0,
      line: { color: "rgba(0,0,0,0.58)", width: 2, dash: "dash" },
      layer: "below",
    }],
    uirevision: `rvbam-lit-bias:${rvbamLiteratureComparisonSignature()}`,
  };
  Plotly.react(rvbEl["rvb-lit-rv-bias-plot"], traces, layout, plotConfig("rvbam_literature_bias"))
    .then(bindRvbamLiteratureBiasEvents);
}

function activeRvbamModelGridFilter() {
  return String(rvbEl["rvb-mgridid"]?.value || rvbState.requestedMgridid || "").trim();
}

function rvbamLiteraturePointsForActiveModelFilter(points) {
  const mgridid = activeRvbamModelGridFilter();
  if (!mgridid) return points || [];
  return (points || []).filter((point) => String(point?.moca_mgridid || "").trim() === mgridid);
}

function rvbamLiteratureComparisonTrace(points, name, selectedTrace) {
  const showErrors = rvbEl["rvb-show-errors"]?.checked !== false;
  const showHover = rvbamShowPlotHoverText();
  return {
    type: "scatter",
    mode: "markers",
    name,
    x: points.map((point) => asNumber(point.literature_rv_kms)),
    y: points.map((point) => asNumber(point.rvbam_rv_kms)),
    error_x: showErrors ? {
      type: "data",
      array: points.map((point) => Math.max(0, asNumber(point.literature_rv_kms_unc) ?? 0)),
      visible: true,
      color: selectedTrace ? "rgba(214,161,0,0.42)" : "rgba(0,0,0,0.24)",
      thickness: selectedTrace ? 2.5 : 1.9,
      width: selectedTrace ? 4 : 3,
    } : undefined,
    error_y: showErrors ? {
      type: "data",
      array: points.map((point) => Math.max(0, asNumber(point.rvbam_rv_kms_unc) ?? 0)),
      visible: true,
      color: selectedTrace ? "rgba(21,101,192,0.56)" : "rgba(21,101,192,0.34)",
      thickness: selectedTrace ? 2.5 : 1.9,
      width: selectedTrace ? 4 : 3,
    } : undefined,
    marker: selectedTrace
      ? { color: "#ffffff", size: 16, symbol: "star", line: { color: "#d6a100", width: 4 } }
      : { color: "#ffffff", size: 9, symbol: "circle", line: { color: "#000000", width: 2.1 } },
    customdata: points.map((point) => Number(point.moca_rv_sample_run_id)),
    text: showHover ? points.map(rvbamLiteratureComparisonHover) : undefined,
    hoverinfo: rvbamHoverInfo("text"),
  };
}

function rvbamLiteratureComparisonAxisRange(points, linearFit = null) {
  const values = [];
  for (const point of points) {
    for (const [valueKey, uncKey] of [
      ["literature_rv_kms", "literature_rv_kms_unc"],
      ["rvbam_rv_kms", "rvbam_rv_kms_unc"],
    ]) {
      const value = asNumber(point[valueKey]);
      if (value === null) continue;
      values.push(value);
      const unc = asNumber(point[uncKey]);
      if (unc !== null && unc > 0) {
        values.push(value - unc, value + unc);
      }
    }
  }
  if (linearFit) values.push(linearFit.xMin, linearFit.xMax, linearFit.yMin, linearFit.yMax);
  if (!values.length) return null;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    const pad = Math.max(1, Math.abs(min || 1) * 0.08);
    return [min - pad, max + pad];
  }
  const pad = Math.max(0.5, (max - min) * 0.08);
  return [min - pad, max + pad];
}

function rvbamRobustWeightedLiteratureComparisonFit(points) {
  const rows = [];
  for (const point of points || []) {
    const x = asNumber(point.literature_rv_kms);
    const y = asNumber(point.rvbam_rv_kms);
    if (x === null || y === null) continue;
    const xUnc = asNumber(point.literature_rv_kms_unc);
    const yUnc = asNumber(point.rvbam_rv_kms_unc);
    rows.push({
      x,
      y,
      xUnc: xUnc !== null && xUnc > 0 ? xUnc : null,
      yUnc: yUnc !== null && yUnc > 0 ? yUnc : null,
    });
  }
  if (rows.length < 2) return null;
  const uniqueX = new Set(rows.map((row) => formatFixed(row.x, 10)));
  if (uniqueX.size < 2) return null;

  const finiteXUncertainties = rows.map((row) => row.xUnc).filter((value) => value !== null && value > 0);
  const finiteYUncertainties = rows.map((row) => row.yUnc).filter((value) => value !== null && value > 0);
  const fallbackXUnc = medianValue(finiteXUncertainties) || 0;
  const fallbackYUnc = medianValue(finiteYUncertainties) || fallbackXUnc || 1;
  for (const row of rows) {
    row.xSigma = row.xUnc && row.xUnc > 0 ? row.xUnc : fallbackXUnc;
    row.ySigma = row.yUnc && row.yUnc > 0 ? row.yUnc : fallbackYUnc;
    row.baseWeight = 1 / (row.ySigma * row.ySigma);
    row.robustWeight = 1;
  }

  const initialWeightSum = rows.reduce((sum, row) => sum + row.baseWeight, 0);
  const x0 = initialWeightSum > 0
    ? rows.reduce((sum, row) => sum + row.x * row.baseWeight, 0) / initialWeightSum
    : rows.reduce((sum, row) => sum + row.x, 0) / rows.length;
  let fit = null;
  for (let iteration = 0; iteration < 30; iteration += 1) {
    fit = rvbamWeightedLinearFit(rows, x0);
    if (!fit) return null;
    const standardizedResiduals = [];
    for (const row of rows) {
      const effectiveSigma = Math.sqrt(row.ySigma * row.ySigma + (fit.slope * row.xSigma) ** 2) || row.ySigma || 1;
      row.baseWeight = 1 / (effectiveSigma * effectiveSigma);
      standardizedResiduals.push((row.y - (fit.intercept + fit.slope * (row.x - x0))) / effectiveSigma);
    }
    const center = medianValue(standardizedResiduals) || 0;
    const scatter = medianValue(standardizedResiduals.map((value) => Math.abs(value - center))) || 0;
    const scale = Math.max(1, 1.4826 * scatter);
    const cutoff = 1.345 * scale;
    let maxChange = 0;
    for (let index = 0; index < rows.length; index += 1) {
      const distance = Math.abs(standardizedResiduals[index] - center);
      const nextWeight = distance <= cutoff || cutoff <= 0 ? 1 : cutoff / distance;
      maxChange = Math.max(maxChange, Math.abs(nextWeight - rows[index].robustWeight));
      rows[index].robustWeight = nextWeight;
    }
    if (maxChange < 0.001) break;
  }
  fit = rvbamWeightedLinearFit(rows, x0);
  if (!fit) return null;
  const xValues = rows.map((row) => row.x);
  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const yMin = fit.intercept + fit.slope * (xMin - x0);
  const yMax = fit.intercept + fit.slope * (xMax - x0);
  return { ...fit, x0, xMin, xMax, yMin, yMax, n: rows.length };
}

function rvbamLiteratureComparisonFitTrace(fit) {
  return {
    type: "scatter",
    mode: "lines",
    name: "Robust weighted linear fit",
    x: [fit.xMin, fit.xMax],
    y: [fit.yMin, fit.yMax],
    line: { color: "#d62728", width: 2.4, dash: "dash" },
    hoverinfo: rvbamHoverInfo("text"),
    hovertemplate: rvbamHoverTemplate([
      "Robust weighted linear fit",
      "Literature RV %{x:.3f} km/s",
      "RVBAM RV %{y:.3f} km/s",
      `Slope ${escapeHtml(signedUncertaintyText(fit.slope, fit.slopeUnc, "", 3))}`,
      `N ${escapeHtml(fit.n)}`,
      "<extra></extra>",
    ].join("<br>")),
  };
}

function rvbamLiteratureBiasTimeRange(points) {
  const values = points.map((point) => asNumber(point.decimal_year)).filter((value) => value !== null);
  if (!values.length) return null;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) return [min - 0.08, max + 0.08];
  const pad = Math.max(0.04, (max - min) * 0.08);
  return [min - pad, max + pad];
}

function rvbamLiteratureBiasRange(points, linearFit = null) {
  const values = [0];
  for (const point of points) {
    const value = asNumber(point.rv_bias_kms);
    if (value === null) continue;
    values.push(value);
    const unc = asNumber(point.rv_bias_kms_unc);
    if (unc !== null && unc > 0) values.push(value - unc, value + unc);
  }
  if (linearFit) values.push(linearFit.yMin, linearFit.yMax);
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    const pad = Math.max(1, Math.abs(min || 1) * 0.08);
    return [min - pad, max + pad];
  }
  const pad = Math.max(0.5, (max - min) * 0.08);
  return [min - pad, max + pad];
}

function rvbamRobustWeightedLiteratureBiasFit(points) {
  const rows = [];
  for (const point of points || []) {
    const x = asNumber(point.decimal_year);
    const y = asNumber(point.rv_bias_kms);
    if (x === null || y === null) continue;
    const unc = asNumber(point.rv_bias_kms_unc);
    rows.push({ x, y, unc: unc !== null && unc > 0 ? unc : null });
  }
  if (rows.length < 2) return null;
  const uniqueX = new Set(rows.map((row) => formatFixed(row.x, 10)));
  if (uniqueX.size < 2) return null;

  const finiteUncertainties = rows.map((row) => row.unc).filter((value) => value !== null && value > 0);
  const fallbackUnc = medianValue(finiteUncertainties) || 1;
  for (const row of rows) {
    row.sigma = row.unc && row.unc > 0 ? row.unc : fallbackUnc;
    row.baseWeight = 1 / (row.sigma * row.sigma);
    row.robustWeight = 1;
  }

  const baseWeightSum = rows.reduce((sum, row) => sum + row.baseWeight, 0);
  const x0 = baseWeightSum > 0
    ? rows.reduce((sum, row) => sum + row.x * row.baseWeight, 0) / baseWeightSum
    : rows.reduce((sum, row) => sum + row.x, 0) / rows.length;
  let fit = null;
  for (let iteration = 0; iteration < 30; iteration += 1) {
    fit = rvbamWeightedLinearFit(rows, x0);
    if (!fit) return null;
    const standardizedResiduals = rows.map((row) => (row.y - (fit.intercept + fit.slope * (row.x - x0))) / row.sigma);
    const center = medianValue(standardizedResiduals) || 0;
    const scatter = medianValue(standardizedResiduals.map((value) => Math.abs(value - center))) || 0;
    const scale = Math.max(1, 1.4826 * scatter);
    const cutoff = 1.345 * scale;
    let maxChange = 0;
    for (let index = 0; index < rows.length; index += 1) {
      const distance = Math.abs(standardizedResiduals[index] - center);
      const nextWeight = distance <= cutoff || cutoff <= 0 ? 1 : cutoff / distance;
      maxChange = Math.max(maxChange, Math.abs(nextWeight - rows[index].robustWeight));
      rows[index].robustWeight = nextWeight;
    }
    if (maxChange < 0.001) break;
  }
  fit = rvbamWeightedLinearFit(rows, x0);
  if (!fit) return null;
  const xValues = rows.map((row) => row.x);
  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const yMin = fit.intercept + fit.slope * (xMin - x0);
  const yMax = fit.intercept + fit.slope * (xMax - x0);
  return { ...fit, x0, xMin, xMax, yMin, yMax, n: rows.length };
}

function rvbamWeightedLinearFit(rows, x0) {
  let sw = 0;
  let sx = 0;
  let sy = 0;
  let sxx = 0;
  let sxy = 0;
  const fitRows = [];
  for (const row of rows) {
    const baseWeight = Number.isFinite(row.baseWeight) && row.baseWeight > 0 ? row.baseWeight : 1;
    const robustWeight = Number.isFinite(row.robustWeight) && row.robustWeight > 0 ? row.robustWeight : 1;
    const weight = baseWeight * robustWeight;
    if (!Number.isFinite(weight) || weight <= 0) continue;
    const dx = row.x - x0;
    sw += weight;
    sx += weight * dx;
    sy += weight * row.y;
    sxx += weight * dx * dx;
    sxy += weight * dx * row.y;
    fitRows.push({ row, weight, dx });
  }
  const denominator = sw * sxx - sx * sx;
  if (!Number.isFinite(denominator) || Math.abs(denominator) <= Number.EPSILON) return null;
  const slope = (sw * sxy - sx * sy) / denominator;
  const intercept = (sy - slope * sx) / sw;
  if (!Number.isFinite(slope) || !Number.isFinite(intercept)) return null;
  let chi2 = 0;
  for (const item of fitRows) {
    const residual = item.row.y - (intercept + slope * item.dx);
    chi2 += item.weight * residual * residual;
  }
  const dof = Math.max(1, fitRows.length - 2);
  const reducedChi2 = fitRows.length > 2 ? chi2 / dof : 1;
  const covarianceScale = Number.isFinite(reducedChi2) ? Math.max(1, reducedChi2) : 1;
  const slopeUnc = Math.sqrt(Math.max(0, covarianceScale * sw / denominator));
  const interceptUnc = Math.sqrt(Math.max(0, covarianceScale * sxx / denominator));
  return {
    slope,
    intercept,
    slopeUnc: Number.isFinite(slopeUnc) ? slopeUnc : null,
    interceptUnc: Number.isFinite(interceptUnc) ? interceptUnc : null,
    chi2,
    dof,
    reducedChi2,
  };
}

function rvbamLiteratureBiasFitTrace(fit) {
  return {
    type: "scatter",
    mode: "lines",
    name: "Robust weighted linear fit",
    x: [fit.xMin, fit.xMax],
    y: [fit.yMin, fit.yMax],
    line: { color: "#d62728", width: 2.4, dash: "dash" },
    hoverinfo: rvbamHoverInfo("text"),
    hovertemplate: rvbamHoverTemplate([
      "Robust weighted linear fit",
      "Year %{x:.4f}",
      "Residual %{y:.3f} km/s",
      `Slope ${escapeHtml(signedUncertaintyText(fit.slope, fit.slopeUnc, "km/s/yr", 3))}`,
      `N ${escapeHtml(fit.n)}`,
      "<extra></extra>",
    ].join("<br>")),
  };
}

function renderRvbamLiteratureBiasSummary(points, linearFit) {
  if (!rvbEl["rvb-lit-rv-bias-summary"]) return;
  const stats = rvbamLiteratureBiasMedianStats(points);
  if (!stats.n) {
    rvbEl["rvb-lit-rv-bias-summary"].innerHTML = '<span class="muted">No residuals available.</span>';
    return;
  }
  const medianText = signedUncertaintyText(stats.median, stats.uncertainty, "km/s", 2);
  const driftText = linearFit
    ? signedUncertaintyText(linearFit.slope, linearFit.slopeUnc, "km/s/yr", 3)
    : "unavailable";
  const details = [
    `${stats.n} residual${stats.n === 1 ? "" : "s"}`,
    stats.scatter !== null && stats.scatter > 0 ? `robust scatter ${formatFixed(stats.scatter, 2)} km/s` : "",
    linearFit?.n ? `${linearFit.n} trend point${linearFit.n === 1 ? "" : "s"}` : "",
  ].filter(Boolean).join("; ");
  rvbEl["rvb-lit-rv-bias-summary"].innerHTML = [
    `Median RVBAM - literature RV: <strong>${escapeHtml(medianText)}</strong>`,
    `Drift: <strong>${escapeHtml(driftText)}</strong>`,
    details ? `<span class="muted">${escapeHtml(details)}</span>` : "",
  ].filter(Boolean).join(" | ");
}

function rvbamLiteratureBiasMedianStats(points) {
  const rows = (points || [])
    .map((point) => ({
      value: asNumber(point.rv_bias_kms),
      uncertainty: asNumber(point.rv_bias_kms_unc),
    }))
    .filter((row) => row.value !== null);
  const n = rows.length;
  if (!n) return { n: 0, median: null, uncertainty: null, scatter: null };
  const values = rows.map((row) => row.value);
  const median = medianValue(values);
  const mad = median === null ? null : medianValue(values.map((value) => Math.abs(value - median)));
  const scatter = mad !== null && mad > 0 ? 1.4826 * mad : null;
  const finiteUncertainties = rows
    .map((row) => row.uncertainty)
    .filter((value) => value !== null && value > 0);
  const medianMeasurementUnc = medianValue(finiteUncertainties);
  const measurementTerm = medianMeasurementUnc !== null && medianMeasurementUnc > 0
    ? (n === 1 ? medianMeasurementUnc : 1.253 * medianMeasurementUnc / Math.sqrt(n))
    : null;
  const scatterTerm = scatter !== null && scatter > 0 && n > 1
    ? 1.253 * scatter / Math.sqrt(n)
    : null;
  const terms = [measurementTerm, scatterTerm].filter((value) => value !== null && Number.isFinite(value) && value > 0);
  const uncertainty = terms.length
    ? Math.sqrt(terms.reduce((sum, value) => sum + value * value, 0))
    : null;
  return { n, median, uncertainty, scatter };
}

function rvbamLiteratureBiasTrace(points, name, selectedTrace) {
  const showErrors = rvbEl["rvb-show-errors"]?.checked !== false;
  const showHover = rvbamShowPlotHoverText();
  return {
    type: "scatter",
    mode: "markers",
    name,
    x: points.map((point) => asNumber(point.decimal_year)),
    y: points.map((point) => asNumber(point.rv_bias_kms)),
    error_y: showErrors ? {
      type: "data",
      array: points.map((point) => Math.max(0, asNumber(point.rv_bias_kms_unc) ?? 0)),
      visible: true,
      color: selectedTrace ? "rgba(214,161,0,0.42)" : "rgba(0,0,0,0.24)",
      thickness: selectedTrace ? 2.5 : 1.9,
      width: selectedTrace ? 4 : 3,
    } : undefined,
    marker: selectedTrace
      ? { color: "#ffffff", size: 14, symbol: "star", line: { color: "#d6a100", width: 3.8 } }
      : { color: "#ffffff", size: 8, symbol: "circle", line: { color: "#000000", width: 1.9 } },
    customdata: points.map((point) => Number(point.moca_rv_sample_run_id)),
    text: showHover ? points.map(rvbamLiteratureBiasHover) : undefined,
    hoverinfo: rvbamHoverInfo("text"),
  };
}

function rvbamLiteratureRunBiasPoints(payload) {
  const output = [];
  for (const point of rvbamLiteraturePointsForActiveModelFilter(payload?.points || [])) {
    const decimalYear = asNumber(point.decimal_year);
    const rvbamRv = asNumber(point.rvbam_rv_kms);
    const literatureRv = asNumber(point.literature_rv_kms);
    if (decimalYear === null || rvbamRv === null || literatureRv === null) continue;
    const rvbamUnc = asNumber(point.rvbam_rv_kms_unc);
    const literatureUnc = asNumber(point.literature_rv_kms_unc);
    const uncertainties = [rvbamUnc, literatureUnc].filter((value) => value !== null && value > 0);
    const biasUnc = uncertainties.length
      ? Math.sqrt(uncertainties.reduce((sum, value) => sum + value * value, 0))
      : null;
    output.push({
      ...point,
      decimal_year: decimalYear,
      measured_rv_kms: rvbamRv,
      measured_rv_kms_unc: rvbamUnc,
      rv_bias_kms: rvbamRv - literatureRv,
      rv_bias_kms_unc: biasUnc,
    });
  }
  return output;
}

function rvbamLiteratureComparisonHover(point) {
  const target = point.designation || point.target_name || `OID ${point.moca_oid ?? "unknown"}`;
  const rvbam = uncertaintyText(point.rvbam_rv_kms, point.rvbam_rv_kms_unc, "km/s", 2);
  const literature = uncertaintyText(point.literature_rv_kms, point.literature_rv_kms_unc, "km/s", 2);
  const countText = `${displayValue(point.kept_segment_count)}/${displayValue(point.available_segment_count)} kept segments`;
  const methodText = point.rvbam_rv_method_label || rvbRvMethodLabels[rvMethodValue(point.rvbam_rv_method)] || (point.rvbam_rv_weighted ? "weighted by RV uncertainty" : "unweighted mean");
  const literatureSourceText = rvbamLiteraturePointSourceText(point);
  return [
    `<b>${escapeHtml(target)}</b>`,
    `Run ${escapeHtml(point.moca_rv_sample_run_id)}`,
    `RVBAM RV ${escapeHtml(rvbam)} (${escapeHtml(methodText)})`,
    `${escapeHtml(point.literature_label || "Literature RV")} ${escapeHtml(literature)}`,
    literatureSourceText ? `MOCAdb RV source ${escapeHtml(literatureSourceText)}` : "",
    point.literature_designation ? `Literature target ${escapeHtml(point.literature_designation)}` : "",
    countText,
    point.template_name ? `Template ${escapeHtml(basename(point.template_name))}` : "",
    point.spectrum_name ? `Spectrum ${escapeHtml(point.spectrum_name)}` : "",
  ].filter(Boolean).join("<br>");
}

function rvbamLiteratureBiasHover(point) {
  const target = point.designation || point.target_name || `OID ${point.moca_oid ?? "unknown"}`;
  const measured = uncertaintyText(point.measured_rv_kms, point.measured_rv_kms_unc, "km/s", 2);
  const literature = uncertaintyText(point.literature_rv_kms, point.literature_rv_kms_unc, "km/s", 2);
  const bias = uncertaintyText(point.rv_bias_kms, point.rv_bias_kms_unc, "km/s", 2);
  const methodText = point.rvbam_rv_method_label || rvbRvMethodLabels[rvMethodValue(point.rvbam_rv_method)] || (point.rvbam_rv_weighted ? "weighted by RV uncertainty" : "combined RV");
  const keptCount = firstPresent(point.kept_segment_count, point.rvbam_rv_segment_count);
  const countText = keptCount !== null && keptCount !== undefined ? `${displayValue(keptCount)} kept segments` : "";
  const literatureSourceText = rvbamLiteraturePointSourceText(point);
  return [
    `<b>${escapeHtml(target)}</b>`,
    `Year ${escapeHtml(formatFixed(point.decimal_year, 4))}`,
    `Run ${escapeHtml(point.moca_rv_sample_run_id)}`,
    `Combined RV ${escapeHtml(measured)} (${escapeHtml(methodText)})`,
    `${escapeHtml(point.literature_label || "Literature RV")} ${escapeHtml(literature)}`,
    literatureSourceText ? `MOCAdb RV source ${escapeHtml(literatureSourceText)}` : "",
    `Combined - literature ${escapeHtml(bias)}`,
    countText,
    point.decimal_year_source ? `Epoch source ${escapeHtml(point.decimal_year_source)}` : "",
    point.template_name ? `Template ${escapeHtml(basename(point.template_name))}` : "",
  ].filter(Boolean).join("<br>");
}

function rvbamLiteraturePointSourceText(point) {
  if (!point?.literature_is_raw_fallback) return "";
  const method = point.literature_rv_combination_method_label || "Ad hoc weighted raw RV fallback";
  const count = numberOrNull(point.literature_raw_rv_row_count);
  return count ? `${method} (${count} raw row${count === 1 ? "" : "s"})` : method;
}

function uncertaintyText(value, uncertainty, unit, digits) {
  const valueNumber = asNumber(value);
  if (valueNumber === null) return "unavailable";
  const uncertaintyNumber = asNumber(uncertainty);
  const rounded = oneSignificantUncertaintyLabel(valueNumber, uncertaintyNumber);
  if (rounded) return `${rounded.value} ${unit} +/- ${rounded.unc} ${unit}`;
  return `${formatFixed(valueNumber, digits ?? 2)} ${unit}`;
}

function signedUncertaintyText(value, uncertainty, unit, digits) {
  const valueNumber = asNumber(value);
  if (valueNumber === null) return "unavailable";
  const unitText = unit ? ` ${unit}` : "";
  const sign = valueNumber > 0 ? "+" : "";
  const uncertaintyNumber = asNumber(uncertainty);
  const rounded = oneSignificantUncertaintyLabel(valueNumber, uncertaintyNumber);
  if (rounded) {
    const roundedSign = Number(rounded.value) > 0 ? "+" : "";
    return `${roundedSign}${rounded.value}${unitText} +/- ${rounded.unc}${unitText}`;
  }
  return `${sign}${formatFixed(valueNumber, digits ?? 2)}${unitText}`;
}

function rvbamLiteratureComparisonSignature() {
  const params = rvbamLiteratureComparisonParams();
  return Array.from(params.entries()).map(([key, value]) => `${key}=${value}`).sort().join("&");
}

function updateRvbamLiteratureComparisonMeta(payload, plottedCount, biasCount) {
  if (!rvbEl["rvb-lit-rv-meta"]) return;
  const meta = payload?.meta || {};
  const skipped = meta.skipped || {};
  const skippedParts = [];
  if (Number(skipped.no_literature_rv || 0)) skippedParts.push(`${skipped.no_literature_rv} without literature RV`);
  if (Number(skipped.no_kept_segments || 0)) skippedParts.push(`${skipped.no_kept_segments} without kept segments`);
  if (Number(skipped.no_segment_rv || 0)) skippedParts.push(`${skipped.no_segment_rv} without segment RV`);
  if (Number(skipped.errors || 0)) skippedParts.push(`${skipped.errors} errors`);
  const candidateCount = Number(meta.candidate_run_count || 0);
  const cacheText = payload?.cache?.hit ? "cache hit" : "fresh";
  rvbEl["rvb-lit-rv-meta"].textContent = [
    `${plottedCount} run comparison points, ${biasCount || 0} run residuals from ${candidateCount} filtered runs`,
    skippedParts.length ? `skipped ${skippedParts.join(", ")}` : "",
    cacheText,
  ].filter(Boolean).join(" | ");
}

function renderEmptyLiteratureComparison(message) {
  renderEmptyLiteratureRvPlot(message);
  renderEmptyLiteratureBiasPlot(message);
  if (rvbEl["rvb-lit-rv-meta"] && !rvbState.literatureComparison) {
    rvbEl["rvb-lit-rv-meta"].textContent = "";
  }
}

function renderEmptyLiteratureRvPlot(message) {
  if (!rvbEl["rvb-lit-rv-plot"]) return;
  Plotly.react(rvbEl["rvb-lit-rv-plot"], [], emptyLayout(message || "No literature comparison"), plotConfig("rvbam_literature_comparison_empty"));
}

function renderEmptyLiteratureBiasPlot(message) {
  if (!rvbEl["rvb-lit-rv-bias-plot"]) return;
  Plotly.react(rvbEl["rvb-lit-rv-bias-plot"], [], emptyLayout(message || "No literature RV residuals"), plotConfig("rvbam_literature_bias_empty"));
  if (rvbEl["rvb-lit-rv-bias-summary"]) rvbEl["rvb-lit-rv-bias-summary"].innerHTML = "";
}

function bindRvbamLiteratureComparisonEvents() {
  const plot = rvbEl["rvb-lit-rv-plot"];
  if (!plot?.on) return;
  rebindPlotlyEvent(plot, "plotly_click", handleRvbamLiteratureComparisonClick);
}

function bindRvbamLiteratureBiasEvents() {
  const plot = rvbEl["rvb-lit-rv-bias-plot"];
  if (!plot?.on) return;
  rebindPlotlyEvent(plot, "plotly_click", handleRvbamLiteratureBiasClick);
}

function handleRvbamLiteratureComparisonClick(event) {
  const runId = numberOrNull(event?.points?.[0]?.customdata);
  if (!runId) return;
  rvbState.requestedRunId = runId;
  rvbState.requestedSegmentId = null;
  rvbState.selectedSegmentId = null;
  if (rvbEl["rvb-run"]) rvbEl["rvb-run"].value = String(runId);
  updateRvbamUrl();
  loadSelectedRvbamRun();
}

function handleRvbamLiteratureBiasClick(event) {
  const customdata = event?.points?.[0]?.customdata;
  const runId = numberOrNull(Array.isArray(customdata) ? customdata[0] : customdata);
  const segmentId = numberOrNull(Array.isArray(customdata) ? customdata[1] : null);
  if (!runId) return;
  rvbState.requestedRunId = runId;
  rvbState.requestedSegmentId = segmentId;
  rvbState.selectedSegmentId = segmentId;
  if (rvbEl["rvb-run"]) rvbEl["rvb-run"].value = String(runId);
  updateRvbamUrl();
  loadSelectedRvbamRun();
}

function scatterYAxisSpec() {
  const key = rvbEl["rvb-scatter-y"]?.value || "rv_kms";
  return rvbScatterYAxisOptions[key] || rvbScatterYAxisOptions.rv_kms;
}

function segmentTrace(rows, name, symbol, ignored, showErrors, size, selectedTrace, ySpec, options = {}) {
  if (!rows.length) return null;
  const selectedpoints = selectedPointIndices(rows);
  const filtered = Boolean(options.filtered);
  const showHover = rvbamShowPlotHoverText();
  const errorColor = filtered ? "rgba(168,18,18,0.22)" : "rgba(0,0,0,0.24)";
  return {
    type: "scatter",
    mode: "markers",
    name,
    opacity: filtered ? 0.28 : 1,
    x: rows.map(segmentWavelengthMicron),
    y: rows.map((row) => asNumber(row[ySpec.key])),
    error_y: showErrors ? {
      type: "data",
      array: rows.map((row) => Math.max(0, asNumber(row[ySpec.errorKey]) ?? 0)),
      visible: true,
      color: errorColor,
      thickness: filtered ? 1.4 : 2.1,
      width: filtered ? 2 : 3,
    } : undefined,
    marker: filtered
      ? {
        color: "rgba(168,18,18,0.24)",
        size,
        symbol,
        line: { color: "rgba(168,18,18,0.46)", width: 1.4 },
      }
      : ignored
      ? { color: "#9c2f2f", size, symbol, line: { color: "#9c2f2f", width: 2.5 } }
      : selectedTrace
        ? { color: "#ffffff", size, symbol, opacity: 1, line: { color: "#d6a100", width: 4.2 } }
      : {
        color: "#ffffff",
        size,
        symbol,
        opacity: selectedTrace ? 1 : 0.98,
        line: {
          color: "#000000",
          width: 2.2,
        },
      },
    customdata: rows.map((row) => Number(row.moca_rv_sampling_segment_id)),
    text: showHover ? rows.map((row) => filtered ? filteredSegmentHover(row, ySpec) : segmentHover(row, ySpec)) : undefined,
    hoverinfo: rvbamHoverInfo("text"),
    selectedpoints,
    selected: { marker: { opacity: 1 } },
    unselected: { marker: { opacity: rvbState.selectedIds && !filtered ? 0.28 : 1 } },
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
    label: literatureRv.label || (literatureRv.is_raw_fallback ? "Raw MOCAdb RV fallback" : (literatureRv.source === "host" ? "Literature host RV" : "Literature RV")),
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

function rvbamScatterYAxisThreshold(ySpec) {
  const thresholdSpec = rvbScatterThresholdSpecs[ySpec?.key];
  if (!thresholdSpec) return null;
  const value = asNumber(averageFilters()[thresholdSpec.filterKey]);
  if (value === null) return null;
  const digits = Number.isFinite(ySpec.digits) ? ySpec.digits : 3;
  return {
    ...thresholdSpec,
    value,
    text: `${thresholdSpec.label} = ${formatFixed(value, digits)}`,
    color: "rgba(43, 92, 171, 0.94)",
    width: 2.6,
    dash: thresholdSpec.direction === "min" ? "dash" : "dot",
  };
}

function rvbamScatterThresholdLine(threshold) {
  return rvbamAverageLine(threshold.value, threshold.color, threshold.width, threshold.dash);
}

function rvbamScatterThresholdLegendTrace(threshold) {
  return {
    type: "scatter",
    mode: "lines",
    name: threshold.text,
    x: [null, null],
    y: [null, null],
    line: { color: threshold.color, width: threshold.width, dash: threshold.dash },
    hoverinfo: "skip",
    showlegend: true,
  };
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
  renderRvbamPayloadTable(detail.payloads || [], detail.samplingRun || {}, segment);
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
  if (!fileAvailable && rvbState.activeTab === "rebuilt") activateRvbamTab("posterior");
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
  if (!available && rvbState.activeTab === "rebuilt-corner") activateRvbamTab("posterior");
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
  return ["fit", "rebuilt", "corner", "rebuilt-corner", "global-corner", "literature", "posterior", "params", "payload", "spectrum"].includes(String(name || ""));
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
  if (rvbState.activeTab === "literature") {
    ensureRvbamLiteratureComparisonLoaded();
    return;
  }
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
    "posterior",
    "rebuilt",
    "fit",
    "rebuilt-corner",
    ...(RVB_SHOW_GLOBAL_CORNER_TAB ? ["global-corner"] : []),
    "corner",
    "params",
    "payload",
    "literature",
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

function renderRvbamPayloadTable(payloads, samplingRun, segment) {
  const segmentRows = selectedSegmentMetadataRows(segment || {});
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
  const segmentHtml = segmentRows.length ? simpleTable(segmentRows, [["key", "Selected Window"], ["value", "Value"]], "rvb-detail-table") : '<div class="rvb-empty-detail">No selected-window metadata</div>';
  const samplingHtml = runRows.length ? simpleTable(runRows, [["key", "Sampling Run"], ["value", "Value"]], "rvb-detail-table") : '<div class="rvb-empty-detail">No sampling-run metadata</div>';
  const payloadHtml = payloads.length ? simpleTable(payloads, payloadColumns, "rvb-detail-table") : '<div class="rvb-empty-detail">No payload metadata</div>';
  rvbEl["rvb-payload-table"].innerHTML = `${segmentHtml}${samplingHtml}${payloadHtml}`;
}

function selectedSegmentMetadataRows(segment) {
  const detail = rvbState.segmentDetail || {};
  const bervMetadata = rvbamBervMetadataFromSources(
    segment,
    detail.samplingRun,
    detail.run,
    ...(detail.parameters || []),
    ...(detail.payloads || []),
    rvbState.payload?.run,
  );
  const bervStatus = rvbamBervStatus(
    detail.run || rvbState.payload?.run || {},
    rvbState.payload?.spectrum || {},
    bervMetadata,
  );
  const rows = [
    ["Segment ID", segment.moca_rv_sampling_segment_id],
    ["Sampling Run ID", segment.moca_sample_run_id],
    ["Order", segment.order_number],
    ["Window", segment.window_number],
    ["Segment", segment.segment_number],
    ["Wavelength min", formatWithUnit(wavelengthMicron(segment.wv_min), "micron", 5)],
    ["Wavelength max", formatWithUnit(wavelengthMicron(segment.wv_max), "micron", 5)],
    ["Wavelength center", formatWithUnit(wavelengthMicron(segment.wv_center), "micron", 5)],
    ["Data RV content contrast", segment.data_contrast],
    ["Model RV content contrast", segment.model_contrast],
    ["Model deep-line pixels", segment.nmodel_10p_contrast],
    ["Masked high-residual pixels", segment.noutliers_masked],
    ["Segment median S/N", segment.segment_snr_median],
    ["Segment S/N p10", segment.segment_snr_p10],
    ["Segment S/N p90", segment.segment_snr_p90],
    ["Segment S/N points", segment.segment_snr_npoints],
    ["RV content method", segment.rv_content_method],
    ["RV content version", segment.rv_content_version],
    ["RV content status", segment.rv_content_status],
    ["RV content computed", formatTimestamp(segment.rv_content_computed_timestamp)],
    ["RV content error", segment.rv_content_error],
    ["BERV status", bervStatus.shortLabel],
    ["RVBAM BERV", bervStatus.correctionLabel],
    ["BERV source", bervMetadata.berv_source],
    ["BERV epoch MJD", bervMetadata.berv_epoch_mjd],
    ["BERV sign", bervMetadata.berv_sign],
    ["BERV coord source", bervMetadata.berv_coord_source],
    ["BERV location", bervMetadata.berv_location],
    ["Created", formatTimestamp(segment.created_timestamp)],
    ["Modified", formatTimestamp(segment.modified_timestamp)],
  ];
  return rows
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => ({ key, value }));
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
      hoverinfo: rvbamHoverInfo("text"),
      hovertemplate: rvbamHoverTemplate(`${escapeHtml(xName)}: %{x:.5g}<br>${escapeHtml(yName)}: %{y:.5g}<extra></extra>`),
    });
  } else {
    traces.push({
      type: "histogram",
      x,
      marker: { color: "#6b7379" },
      nbinsx: 44,
      hoverinfo: rvbamHoverInfo("text"),
      hovertemplate: rvbamHoverTemplate(`${escapeHtml(xName)}: %{x:.5g}<br>N: %{y}<extra></extra>`),
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
    hoverinfo: rvbamHoverInfo("text"),
    hovertemplate: rvbamHoverTemplate("%{y} vs %{x}: %{z:.3f}<extra></extra>"),
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
      hoverinfo: rvbamHoverInfo("text"),
      hovertemplate: rvbamHoverTemplate("Inflated err<br>wavelength: %{x:.6g} μm<br>flux: %{y:.5g}<extra></extra>"),
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
      hoverinfo: rvbamHoverInfo("text"),
      hovertemplate: rvbamHoverTemplate("Data<br>wavelength: %{x:.6g} μm<br>flux: %{y:.5g}<extra></extra>"),
    },
    {
      type: "scatter",
      mode: "lines",
      name: "HDF5 rebuilt model",
      x: modelX,
      y: model.map((row) => asNumber(row.model_flux)),
      line: { color: "rgba(168,18,18,.95)", width: 2.2 },
      hoverinfo: rvbamHoverInfo("text"),
      hovertemplate: rvbamHoverTemplate("HDF5 rebuilt model<br>wavelength: %{x:.6g} μm<br>flux: %{y:.5g}<extra></extra>"),
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
  const status = rvbamBervStatus(run, spectrum);
  return [
    status.summary,
    `moca_spectra.berv_corrected=${formatFlag(spectrum.berv_corrected ?? run.berv_corrected)}`,
    `moca_spectra.spacecraft_rv_corrected=${formatFlag(spectrum.spacecraft_rv_corrected ?? run.spacecraft_rv_corrected)}`,
  ];
}

function rvbamBervStatus(run, spectrum, suppliedMetadata) {
  const metadata = suppliedMetadata || rvbamBervMetadataForRun(run, spectrum);
  const berv = firstNumber(metadata.berv_kms, run?.berv_kms);
  const spectrumBervCorrected = flagIsTrue(firstPresent(spectrum?.berv_corrected, run?.berv_corrected, metadata.moca_berv_corrected));
  const sign = String(metadata.berv_sign || "").trim().toLowerCase();
  const hasBervMetadata = Object.keys(metadata).some((key) => String(key).startsWith("berv_"));
  const nonzeroBerv = berv !== null && Math.abs(berv) >= 1e-9;
  const appliedByRvbam = sign === "add_to_sampler_rv" || (nonzeroBerv && !spectrumBervCorrected) || (hasBervMetadata && nonzeroBerv);
  const correctionLabel = berv === null ? "" : signedUnitLabel(berv, "km/s", 3);

  if (appliedByRvbam) {
    const source = metadata.berv_source ? ` from ${metadata.berv_source}` : "";
    const epoch = metadata.berv_epoch_mjd ? ` at MJD ${metadata.berv_epoch_mjd}` : "";
    return {
      state: "rvbam_applied",
      shortLabel: "RVBAM applied",
      correctionLabel,
      summary: `RVBAM applied BERV ${correctionLabel}${source}${epoch} to sampler RVs`,
      metadata,
    };
  }

  if (spectrumBervCorrected) {
    return {
      state: "spectrum_corrected",
      shortLabel: "already in spectrum",
      correctionLabel: correctionLabel || "no additional RVBAM shift",
      summary: "BERV already corrected in the moca_spectra wavelength solution; RVBAM did not apply an additional correction",
      metadata,
    };
  }

  if (berv !== null) {
    return {
      state: "recorded_zero",
      shortLabel: nonzeroBerv ? "recorded" : "no net shift",
      correctionLabel,
      summary: `RVBAM BERV correction recorded as ${correctionLabel}`,
      metadata,
    };
  }

  return {
    state: "not_recorded",
    shortLabel: "not recorded",
    correctionLabel: "",
    summary: "RVBAM BERV correction not recorded",
    metadata,
  };
}

function rvbamBervMetadataForRun(run, spectrum) {
  const metadata = rvbamBervMetadataFromSources(run);
  if (!Object.prototype.hasOwnProperty.call(metadata, "moca_berv_corrected") && spectrum?.berv_corrected !== undefined) {
    metadata.moca_berv_corrected = spectrum.berv_corrected;
  }
  if (!Object.prototype.hasOwnProperty.call(metadata, "spacecraft_rv_corrected") && spectrum?.spacecraft_rv_corrected !== undefined) {
    metadata.spacecraft_rv_corrected = spectrum.spacecraft_rv_corrected;
  }
  return metadata;
}

function rvbamBervMetadataFromSources(...sources) {
  const metadata = {};
  for (const source of sources.flat().filter(Boolean)) {
    if (source && typeof source.berv_metadata === "object" && !Array.isArray(source.berv_metadata)) {
      mergeRvbamBervMetadata(metadata, source.berv_metadata);
    }
    for (const key of ["comments", "run_comments", "sampling_comments"]) {
      if (source?.[key]) mergeRvbamBervMetadata(metadata, parseRvbamCommentMetadata(source[key]));
    }
  }
  return metadata;
}

function mergeRvbamBervMetadata(target, source) {
  for (const [rawKey, rawValue] of Object.entries(source || {})) {
    const key = normalizeRvbamBervMetadataKey(rawKey);
    if (!key || rawValue === null || rawValue === undefined || rawValue === "") continue;
    if (target[key] === undefined || target[key] === "") target[key] = rawValue;
  }
}

function normalizeRvbamBervMetadataKey(key) {
  const normalized = String(key || "").trim();
  const aliases = {
    moca_berv_corected: "moca_berv_corrected",
    berv_corected: "moca_berv_corrected",
    berv_corrected: "moca_berv_corrected",
  };
  const canonical = aliases[normalized] || normalized;
  return [
    "berv_source",
    "berv_kms",
    "berv_epoch_mjd",
    "moca_berv_corrected",
    "spacecraft_rv_corrected",
    "berv_coord_source",
    "berv_location",
    "berv_sign",
  ].includes(canonical) ? canonical : "";
}

function parseRvbamCommentMetadata(comment) {
  const text = String(comment || "").trim();
  if (!text) return {};
  if (text.startsWith("{") && text.endsWith("}")) {
    try {
      const decoded = JSON.parse(text);
      if (decoded && typeof decoded === "object" && !Array.isArray(decoded)) return decoded;
    } catch (_) {
      // Fall through to key=value parsing.
    }
  }
  const metadata = {};
  const pattern = /(?:^|[;,\s])([A-Za-z][A-Za-z0-9_]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^;,\n\r]+))/g;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    const value = [match[2], match[3], match[4]].find((item) => item !== undefined);
    metadata[match[1]] = coerceRvbamCommentValue(value);
  }
  return metadata;
}

function coerceRvbamCommentValue(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (["true", "yes", "on"].includes(text.toLowerCase())) return true;
  if (["false", "no", "off"].includes(text.toLowerCase())) return false;
  if (["none", "null", "nan"].includes(text.toLowerCase())) return null;
  const number = Number(text);
  if (Number.isFinite(number) && /^[-+]?(?:\d+|\d*\.\d+)(?:e[-+]?\d+)?$/i.test(text)) return number;
  return text;
}

function firstNumber(...values) {
  for (const value of values) {
    const number = asNumber(value);
    if (number !== null) return number;
  }
  return null;
}

function flagIsTrue(value) {
  if (value === true) return true;
  if (value === false) return false;
  const number = asNumber(value);
  if (number !== null) return number === 1;
  return ["true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function signedUnitLabel(value, unit, digits) {
  const number = asNumber(value);
  if (number === null) return "";
  const sign = number > 0 ? "+" : "";
  return `${sign}${formatFixed(number, digits ?? 3)} ${unit}`;
}

function rvbamLiteratureRvSummaryText() {
  const literatureRv = normalizedRvbamLiteratureRv();
  if (!literatureRv) return "";
  const unit = "km/s";
  const fallbackSuffix = rvbamLiteratureRvSummarySuffix(literatureRv);
  const rounded = oneSignificantUncertaintyLabel(literatureRv.value, literatureRv.uncertainty);
  if (rounded) return `${literatureRv.label} = ${rounded.value} ${unit} +/- ${rounded.unc} ${unit}${fallbackSuffix}`;
  return `${literatureRv.label} = ${formatFixed(literatureRv.value, 1)} ${unit}${fallbackSuffix}`;
}

function rvbamLiteratureRvSummarySuffix(literatureRv) {
  if (!literatureRv?.is_raw_fallback) return "";
  const count = numberOrNull(literatureRv.raw_rv_row_count);
  return count ? ` (ad hoc from ${count} raw row${count === 1 ? "" : "s"})` : " (ad hoc raw RV fallback)";
}

function updateRvbamReportButton() {
  const buttons = [rvbEl["rvb-open-report"], rvbEl["rvb-info-open-report"]].filter(Boolean);
  const spectrumButton = rvbEl["rvb-open-spectrum"];
  const oid = numberOrNull(rvbState.payload?.run?.moca_oid);
  const specid = numberOrNull(rvbState.payload?.run?.moca_specid);
  buttons.forEach((button) => { button.disabled = !oid; });
  if (spectrumButton) spectrumButton.disabled = !specid;
}

function openRvbamReport() {
  const oid = numberOrNull(rvbState.payload?.run?.moca_oid);
  if (!oid) return;
  window.open(rvbamMocaReportUrl(oid), "_blank", "noopener");
}

function openRvbamSpectrum() {
  const specid = numberOrNull(rvbState.payload?.run?.moca_specid);
  if (!specid) return;
  window.open(rvbamSpectrumExplorerUrl(specid), "_blank", "noopener");
}

function rvbamSpectrumExplorerUrl(specid) {
  const currentParams = new URLSearchParams(window.location.search);
  const params = new URLSearchParams({ moca_specid: String(specid) });
  for (const key of ["mock", "host", "user", "pwd", "dbase"]) {
    if (currentParams.has(key)) params.set(key, currentParams.get(key) || "");
  }
  return rvbAppUrl(`spectra?${params.toString()}`);
}

function rvbamMocaReportUrl(oid) {
  return `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(String(oid))}%29&search-type=star`;
}

function currentRvbamRunForDefaults() {
  const currentRunId = numberOrNull(rvbEl["rvb-run"]?.value) || numberOrNull(rvbState.payload?.run?.moca_rv_sample_run_id);
  if (rvbState.payload?.run && Number(rvbState.payload.run.moca_rv_sample_run_id) === Number(currentRunId)) {
    return rvbState.payload.run;
  }
  return rvbState.runs.find((row) => Number(row.moca_rv_sample_run_id) === Number(currentRunId)) || rvbState.payload?.run || {};
}

function applyRvbamRunDefaultAverageFilters(run, options = {}) {
  const force = Boolean(options.force);
  if (isRvbamFireRun(run)) {
    if (force || rvbState.averageFilterPreset === "fire" || (!hasAnyAverageFilterInputValue() && rvbState.averageFilterPreset !== "none")) {
      setAverageFilterInputValues(rvbFireAverageFilterDefaults, { clearMissing: true });
      rvbState.averageFilterPreset = "fire";
      return true;
    }
    return false;
  }
  if (force) {
    clearAverageFilterInputValues();
    rvbState.averageFilterPreset = "";
    return true;
  }
  if (rvbState.averageFilterPreset === "fire" && averageFilterInputsMatch(rvbFireAverageFilterDefaults)) {
    clearAverageFilterInputValues();
    rvbState.averageFilterPreset = "";
    return true;
  }
  if (rvbState.averageFilterPreset !== "none") {
    rvbState.averageFilterPreset = "";
  }
  return false;
}

function isRvbamFireRun(run) {
  return String(run?.moca_instid || "").toLowerCase().includes("fire");
}

function hasAnyAverageFilterInputValue() {
  return rvbAverageFilterInputIds.some((id) => String(rvbEl[id]?.value || "").trim() !== "");
}

function setAverageFilterInputValues(values, options = {}) {
  const clearMissing = Boolean(options.clearMissing);
  for (const id of rvbAverageFilterInputIds) {
    if (Object.prototype.hasOwnProperty.call(values, id)) {
      rvbEl[id].value = values[id];
    } else if (clearMissing || rvbState.averageFilterPreset === "fire") {
      rvbEl[id].value = "";
    }
  }
}

function clearAverageFilterInputValues() {
  for (const id of rvbAverageFilterInputIds) {
    rvbEl[id].value = "";
  }
}

function averageFilterInputsMatch(values) {
  return rvbAverageFilterInputIds.every((id) => {
    const current = String(rvbEl[id]?.value || "").trim();
    const expected = Object.prototype.hasOwnProperty.call(values, id) ? String(values[id]) : "";
    return current === expected;
  });
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
  const minDataContrast = numberOrNull(rvbEl["rvb-min-data-contrast"]?.value);
  const minModelContrast = numberOrNull(rvbEl["rvb-min-model-contrast"]?.value);
  const minModel10p = numberOrNull(rvbEl["rvb-min-model-10p"]?.value);
  const minSnr = numberOrNull(rvbEl["rvb-min-snr"]?.value);
  const segmentWavelengthRanges = parseRvbamWavelengthRanges(rvbEl["rvb-segment-wavelength"]?.value);
  const maxMaskedOutliers = numberOrNull(rvbEl["rvb-max-masked-outliers"]?.value);
  return {
    maxLsf,
    maxBestChi2,
    maxRvUnc,
    minDataContrast,
    minModelContrast,
    minModel10p,
    minSnr,
    segmentWavelengthRanges,
    maxMaskedOutliers,
    active: maxLsf !== null || maxBestChi2 !== null || maxRvUnc !== null
      || minDataContrast !== null || minModelContrast !== null || minModel10p !== null
      || minSnr !== null || segmentWavelengthRanges.length > 0 || maxMaskedOutliers !== null,
  };
}

function passesAverageFilters(row, filters) {
  return (
    passesMaxFilter(row.lsf, filters.maxLsf)
    && passesMaxFilter(row.best_chi2, filters.maxBestChi2)
    && passesMaxFilter(row.rv_kms_unc, filters.maxRvUnc)
    && passesMinFilter(row.data_contrast, filters.minDataContrast)
    && passesMinFilter(row.model_contrast, filters.minModelContrast)
    && passesMinFilter(row.nmodel_10p_contrast, filters.minModel10p)
    && passesMinFilter(row.segment_snr_median, filters.minSnr)
    && passesSegmentWavelengthFilter(row, filters.segmentWavelengthRanges)
    && passesMaxFilter(row.noutliers_masked, filters.maxMaskedOutliers)
  );
}

function failedAverageFilterKeys(row, filters = averageFilters()) {
  if (!filters.active) return new Set();
  const failed = new Set();
  if (!passesMaxFilter(row.lsf, filters.maxLsf)) failed.add("lsf");
  if (!passesMaxFilter(row.best_chi2, filters.maxBestChi2)) failed.add("best_chi2");
  if (!passesMaxFilter(row.rv_kms_unc, filters.maxRvUnc)) failed.add("rv_kms_unc");
  if (!passesMinFilter(row.data_contrast, filters.minDataContrast)) failed.add("data_contrast");
  if (!passesMinFilter(row.model_contrast, filters.minModelContrast)) failed.add("model_contrast");
  if (!passesMinFilter(row.nmodel_10p_contrast, filters.minModel10p)) failed.add("nmodel_10p_contrast");
  if (!passesMinFilter(row.segment_snr_median, filters.minSnr)) failed.add("segment_snr_median");
  if (!passesSegmentWavelengthFilter(row, filters.segmentWavelengthRanges)) failed.add("wavelength");
  if (!passesMaxFilter(row.noutliers_masked, filters.maxMaskedOutliers)) failed.add("noutliers_masked");
  return failed;
}

function passesSegmentWavelengthFilter(row, ranges) {
  if (!ranges?.length) return true;
  const bounds = segmentWavelengthBoundsMicron(row);
  if (!bounds) return false;
  return ranges.some(([lo, hi]) => bounds[0] <= hi && bounds[1] >= lo);
}

function passesMaxFilter(value, maximum) {
  if (maximum === null) return true;
  const number = asNumber(value);
  return number !== null && number <= maximum;
}

function passesMinFilter(value, minimum) {
  if (minimum === null) return true;
  const number = asNumber(value);
  return number !== null && number >= minimum;
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

function medianValue(values) {
  const finite = values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (!finite.length) return null;
  const mid = Math.floor(finite.length / 2);
  return finite.length % 2 ? finite[mid] : 0.5 * (finite[mid - 1] + finite[mid]);
}

function weightedMedianValue(values, weights) {
  const pairs = values
    .map((value, index) => ({ value, weight: weights[index] }))
    .filter((row) => Number.isFinite(row.value) && Number.isFinite(row.weight) && row.weight > 0)
    .sort((a, b) => a.value - b.value);
  if (!pairs.length) return medianValue(values);
  const total = pairs.reduce((sum, row) => sum + row.weight, 0);
  const cutoff = 0.5 * total;
  let cumulative = 0;
  for (let index = 0; index < pairs.length; index += 1) {
    const row = pairs[index];
    cumulative += row.weight;
    if (cumulative >= cutoff) {
      const tolerance = Math.max(1, Math.abs(cutoff)) * Number.EPSILON * 16;
      if (Math.abs(cumulative - cutoff) <= tolerance && index + 1 < pairs.length) {
        return 0.5 * (row.value + pairs[index + 1].value);
      }
      return row.value;
    }
  }
  return pairs[pairs.length - 1].value;
}

function averageSegmentStats(rows, ySpec, method = selectedRvMethod()) {
  const isRv = ySpec.key === "rv_kms";
  const rvMethod = isRv ? rvMethodValue(method) : "weighted_errors";
  const values = [];
  const weightedRows = [];
  for (const row of rows) {
    const value = asNumber(row[ySpec.key]);
    if (value === null) continue;
    values.push(value);
    const unc = ySpec.errorKey ? asNumber(row[ySpec.errorKey]) : null;
    if (unc === null || unc <= 0) continue;
    weightedRows.push({ value, unc, nominalWeight: 1 / (unc * unc) });
  }
  if (!values.length) return { n: 0, mean: null, unc: null, weighted: false };

  if (isRv && (rvMethod === "median_mad" || !weightedRows.length)) {
    const center = medianValue(values);
    const mad = center === null ? null : medianValue(values.map((value) => Math.abs(value - center)));
    return {
      n: values.length,
      mean: center,
      unc: mad !== null && mad > 0 ? mad : null,
      weighted: false,
      method: "median_mad",
      methodLabel: rvbRvMethodLabels.median_mad,
      mad,
    };
  }

  if (weightedRows.length) {
    const nominalWeights = weightedRows.map((row) => row.nominalWeight).filter((weight) => Number.isFinite(weight) && weight > 0);
    if (nominalWeights.length) {
      if (!isRv) {
        const sw = nominalWeights.reduce((sum, weight) => sum + weight, 0);
        const mean = weightedRows.reduce((sum, row) => sum + row.value * row.nominalWeight, 0) / sw;
        return { n: weightedRows.length, mean, unc: Math.sqrt(1 / sw), weighted: true };
      }
      const sortedWeights = [...nominalWeights].sort((a, b) => a - b);
      const mid = Math.floor(sortedWeights.length / 2);
      const medianWeight = sortedWeights.length % 2
        ? sortedWeights[mid]
        : 0.5 * (sortedWeights[mid - 1] + sortedWeights[mid]);
      const weightCeiling = Number.isFinite(medianWeight) && medianWeight > 0 ? 5 * medianWeight : 0;
      const usableRows = weightedRows.filter((row) => Number.isFinite(row.value) && Number.isFinite(row.unc) && row.unc > 0 && Number.isFinite(row.nominalWeight) && row.nominalWeight > 0);
      const weights = usableRows.map((row) => (weightCeiling > 0 ? Math.min(row.nominalWeight, weightCeiling) : row.nominalWeight));
      const sw = weights.reduce((sum, weight) => sum + weight, 0);
      if (sw > 0 && Number.isFinite(sw)) {
        if (rvMethod === "weighted_median_mad") {
          const usableValues = usableRows.map((row) => row.value);
          const center = weightedMedianValue(usableValues, weights);
          const mad = weightedMedianValue(usableValues.map((value) => Math.abs(value - center)), weights);
          return {
            n: usableRows.length,
            mean: center,
            unc: mad !== null && mad > 0 ? mad : null,
            weighted: true,
            method: "weighted_median_mad",
            methodLabel: rvbRvMethodLabels.weighted_median_mad,
            mad,
            medianWeight,
            weightCeiling,
            weightCeilingFactor: 5,
          };
        }
        const mean = usableRows.reduce((sum, row, index) => sum + row.value * weights[index], 0) / sw;
        const propagatedUnc = Math.sqrt(usableRows.reduce((sum, row, index) => {
          const normalizedWeight = weights[index] / sw;
          return sum + (normalizedWeight * row.unc) ** 2;
        }, 0));
        const variance = usableRows.reduce((sum, row, index) => sum + weights[index] * (row.value - mean) ** 2, 0) / sw;
        const weightSquareSum = weights.reduce((sum, weight) => sum + weight * weight, 0);
        const correction = 1 - (weightSquareSum / (sw * sw));
        const scatterUnc = usableRows.length > 1 && correction > 0
          ? Math.sqrt(Math.max(0, variance / correction))
          : 0;
        const uncTerms = [propagatedUnc, scatterUnc].filter((value) => Number.isFinite(value) && value > 0);
        const unc = uncTerms.length ? Math.sqrt(uncTerms.reduce((sum, value) => sum + value * value, 0)) : null;
        return {
          n: usableRows.length,
          mean,
          unc,
          weighted: true,
          method: "weighted_errors",
          methodLabel: rvbRvMethodLabels.weighted_errors,
          propagatedUnc,
          scatterUnc,
          medianWeight,
          weightCeiling,
          weightCeilingFactor: 5,
        };
      }
    }
  }
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  let unc = null;
  if (values.length > 1) {
    const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
    unc = Math.sqrt(variance / (isRv ? 1 : values.length));
  }
  return {
    n: values.length,
    mean,
    unc,
    weighted: false,
    method: isRv ? "weighted_errors" : undefined,
    methodLabel: isRv ? "mean" : undefined,
  };
}

function averageStatsLabel(stats, ySpec, options = {}) {
  const methodLabel = ySpec.key === "rv_kms" && stats.methodLabel ? stats.methodLabel : null;
  const prefix = methodLabel ? `${methodLabel} ${ySpec.label}` : (stats.weighted ? `weighted ${ySpec.label}` : `mean ${ySpec.label}`);
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
    for (const id of ["rvb-posterior-plot", "rvb-correlation-plot", "rvb-rebuilt-corner-plot", "rvb-global-corner-plot", "rvb-rebuilt-fit-plot", "rvb-lit-rv-plot", "rvb-lit-rv-bias-plot"]) {
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
    "data_contrast",
    "model_contrast",
    "nmodel_10p_contrast",
    "noutliers_masked",
    "segment_snr_median",
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
  copyInputToParam(params, "moca_instid", "rvb-instid");
  copyInputToParam(params, "moca_mgridid", "rvb-mgridid");
  copyInputToParam(params, "min_segments", "rvb-min-segments");
  copyInputToParam(params, "max_segments", "rvb-max-segments");
  copyInputToParam(params, "min_run_snr", "rvb-min-run-snr");
  copyInputToParam(params, "max_literature_rv_unc", "rvb-max-literature-rv-unc");
  copyInputToParam(params, "max_resulting_rv_unc", "rvb-max-resulting-rv-unc");
  for (const alias of ["instid", "instrument"]) params.delete(alias);
  for (const alias of ["mgridid", "model_grid", "atmosphere_model", "model"]) params.delete(alias);
  for (const alias of ["min_segment_count", "min_available_segments", "max_segment_count", "max_available_segments"]) params.delete(alias);
  for (const alias of ["min_run_median_snr", "min_median_snr", "min_median_snr_per_pix"]) params.delete(alias);
  for (const alias of ["max_literature_rv_error", "max_lit_rv_unc", "max_lit_rv_error", "max_mocadb_rv_unc"]) params.delete(alias);
  for (const alias of ["max_resulting_rv_error", "max_run_rv_unc", "max_run_rv_error", "max_rvbam_rv_unc"]) params.delete(alias);
  if (rvbEl["rvb-has-literature-rv"].checked) params.set("has_literature_rv", "1");
  else params.delete("has_literature_rv");
  copyInputToParam(params, "wavelength_coverage", "rvb-wavelength-coverage");
  params.set("include_ignored", rvbEl["rvb-include-ignored"].checked ? "1" : "0");
  params.set("errors", rvbEl["rvb-show-errors"].checked ? "1" : "0");
  params.set("hover_text", rvbEl["rvb-show-hover"].checked ? "1" : "0");
  for (const alias of ["show_hover", "hover"]) params.delete(alias);
  params.set("use_selection", rvbEl["rvb-use-selection"].checked ? "1" : "0");
  params.set("online_figures", rvbEl["rvb-use-online-figures"].checked && !rvbEl["rvb-use-online-figures"].disabled ? "1" : "0");
  params.set("scatter_y", scatterYAxisSpec().key);
  params.set("rv_method", selectedRvMethod());
  for (const alias of ["rv_calculation_method", "rv_stat_method"]) params.delete(alias);
  copyInputToParam(params, "max_lsf", "rvb-max-lsf");
  copyInputToParam(params, "max_best_chi2", "rvb-max-best-chi2");
  copyInputToParam(params, "max_rv_unc", "rvb-max-rv-unc");
  copyInputToParam(params, "min_data_contrast", "rvb-min-data-contrast");
  copyInputToParam(params, "min_model_contrast", "rvb-min-model-contrast");
  copyInputToParam(params, "min_model_10p", "rvb-min-model-10p");
  copyInputToParam(params, "min_snr", "rvb-min-snr");
  copyInputToParam(params, "segment_wavelength", "rvb-segment-wavelength");
  copyInputToParam(params, "max_masked_outliers", "rvb-max-masked-outliers");
  for (const alias of ["min_snr_p10", "min_segment_snr_p10", "min_snr_pixels", "min_snr_npoints", "max_noutliers_masked", "segment_wavelength_range", "segment_wv"]) params.delete(alias);
  if (rvbState.averageFilterPreset === "none" && !hasAnyAverageFilterInputValue()) {
    params.set("average_filter_preset", "none");
  } else {
    params.delete("average_filter_preset");
  }
  params.delete("filter_preset");
  if (rvbEl["rvb-param-x"].value) params.set("x", rvbEl["rvb-param-x"].value);
  if (rvbEl["rvb-param-y"].value) params.set("y", rvbEl["rvb-param-y"].value);
  params.set("max_points", String(numberInputValue("rvb-max-points", 1800)));
  if (rvbState.activeTab && rvbState.activeTab !== "posterior") params.set("tab", rvbState.activeTab);
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
  if (["data_contrast", "model_contrast"].includes(key)) return formatFixed(value, 4);
  if (key === "segment_snr_median") return formatFixed(value, 2);
  if (["rv_kms", "rv_kms_unc", "lsf", "lsf_unc", "vsini_kms", "vsini_kms_unc", "best_chi2", "lnp_median", "lnp_max"].includes(key)) return formatFixed(value, 3);
  return displayValue(value);
}

function formatGenericCell(value) {
  const number = asNumber(value);
  if (number !== null) {
    if (Number.isInteger(number)) return String(number);
    if (Math.abs(number) >= 1000 || (Math.abs(number) > 0 && Math.abs(number) < 0.001)) return number.toExponential(4);
    return formatFixed(number, 5);
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

function filteredSegmentHover(row, ySpec) {
  const failedKeys = failedAverageFilterKeys(row);
  return `${segmentHover(row, ySpec, { failedKeys })}<br><b>Filtered from average</b>`;
}

function segmentHover(row, ySpec, options = {}) {
  const failedKeys = options.failedKeys || new Set();
  const yValue = ySpec && ySpec.key !== "rv_kms"
    ? rvbamSegmentHoverMetricLine(ySpec.label, formatGenericCell(row[ySpec.key]), ySpec.key, failedKeys)
    : "";
  return [
    `Segment ${displayValue(row.segment_number)}`,
    `Order ${displayValue(row.order_number)} window ${displayValue(row.window_number)}`,
    rvbamSegmentHoverMetricLine("Wavelength", `${formatFixed(segmentWavelengthMicron(row), 5)} micron`, "wavelength", failedKeys),
    yValue,
    `RV ${formatFixed(row.rv_kms, 3)} km/s`,
    rvbamSegmentHoverMetricLine("RV uncertainty", `${formatFixed(row.rv_kms_unc, 3)} km/s`, "rv_kms_unc", failedKeys),
    rvbamSegmentHoverMetricLine("LSF", `${formatFixed(row.lsf, 3)} km/s`, "lsf", failedKeys),
    `vsini ${formatFixed(row.vsini_kms, 3)} km/s`,
    asNumber(row.best_chi2) !== null ? rvbamSegmentHoverMetricLine("Best chi2", formatFixed(row.best_chi2, 3), "best_chi2", failedKeys) : "",
    asNumber(row.segment_snr_median) !== null ? rvbamSegmentHoverMetricLine("Segment median S/N", `${formatFixed(row.segment_snr_median, 2)} (spectrum quality)`, "segment_snr_median", failedKeys) : "",
    asNumber(row.data_contrast) !== null ? rvbamSegmentHoverMetricLine("Data RV content", `${formatFixed(row.data_contrast, 4)}: intrinsic fractional data structure after flux errors`, "data_contrast", failedKeys) : "",
    asNumber(row.model_contrast) !== null ? rvbamSegmentHoverMetricLine("Model RV content", `${formatFixed(row.model_contrast, 4)}: template 99-to-1 percentile fractional contrast`, "model_contrast", failedKeys) : "",
    asNumber(row.nmodel_10p_contrast) !== null ? rvbamSegmentHoverMetricLine("Model deep-line pixels", `${formatGenericCell(row.nmodel_10p_contrast)}: pixels at least 10% below high flux`, "nmodel_10p_contrast", failedKeys) : "",
    asNumber(row.noutliers_masked) !== null ? rvbamSegmentHoverMetricLine("Masked high-residual pixels", `${formatGenericCell(row.noutliers_masked)}: fit points removed before final RV`, "noutliers_masked", failedKeys) : "",
  ].filter(Boolean).join("<br>");
}

function rvbamSegmentHoverMetricLine(label, valueText, key, failedKeys) {
  const line = `${label} ${valueText}`;
  return failedKeys?.has(key) ? rvbamFailedHoverLine(line) : line;
}

function rvbamFailedHoverLine(text) {
  return `<b><span style="color:#b00020">${text}</span></b>`;
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

function segmentWavelengthBoundsMicron(row) {
  let left = wavelengthMicron(row?.wv_min);
  let right = wavelengthMicron(row?.wv_max);
  if (left === null || right === null) {
    const center = segmentWavelengthMicron(row);
    if (center === null) return null;
    left = center;
    right = center;
  }
  return left <= right ? [left, right] : [right, left];
}

function parseRvbamWavelengthRanges(raw) {
  const text = String(raw || "").trim();
  if (!text) return [];
  const ranges = [];
  const numberPattern = /[-+]?\d*\.?\d+(?:e[-+]?\d+)?/ig;
  const pairPattern = /([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(?:-|:|,|\s+)\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)/ig;
  let match;
  while ((match = pairPattern.exec(text)) !== null) {
    const left = wavelengthMicron(match[1]);
    const right = wavelengthMicron(match[2]);
    if (left === null || right === null) continue;
    ranges.push(left <= right ? [left, right] : [right, left]);
  }
  if (ranges.length) return ranges;
  while ((match = numberPattern.exec(text)) !== null) {
    const value = wavelengthMicron(match[0]);
    if (value !== null) ranges.push([value, value]);
  }
  return ranges;
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

function firstPresent(...values) {
  return values.find((value) => value !== null && value !== undefined && value !== "") ?? "";
}

function formatTimestamp(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text
    .replace("T", " ")
    .replace(/\.\d+(?=$|Z)/, "")
    .replace(/Z$/, " UTC");
}

function formatTimestampShort(value) {
  return formatTimestamp(value).replace(/:\d{2}(?=\s|$)/, "");
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
  const removeButtons = options.saveImage === false ? ["toImage"] : [];
  return {
    responsive: true,
    displayModeBar: true,
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
