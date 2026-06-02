const tfaDefaultOid = 11266;
const tfaDefaultAid = "ABDMG";
const tfaDefaultSources = ["Legacy", "Scalar Gaussian"];
const tfaUniverseAgeMyr = 13800;
const tfaTeamUsers = new Set(["collaborators", "management"]);
const tfaSourceIds = {
  "MOCAFlows": "tfa-source-mocaflows",
  "Legacy": "tfa-source-legacy",
  "Scalar Gaussian": "tfa-source-scalar",
};
const tfaColors = [
  "#2c7fb8",
  "#d95f0e",
  "#31a354",
  "#756bb1",
  "#c51b8a",
  "#636363",
  "#1b9e77",
  "#e6ab02",
  "#66a61e",
  "#a6761d",
];

const tfaState = {
  associations: [],
  associationFilter: "",
  payload: null,
  visibleCurves: [],
  focusedKey: null,
  searchTimer: null,
  loadToken: 0,
  designationCache: new Map(),
};

const tfaEl = {};

document.addEventListener("DOMContentLoaded", initTrueflowAgePdfs);

const tfaAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function tfaAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), tfaAppBaseUrl).toString();
}

function tfaRootUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), `${window.location.origin}/`).toString();
}

async function initTrueflowAgePdfs() {
  collectTrueflowAgeElements();
  readTrueflowAgeUrlState();
  applyTrueflowMocaflowsAccess();
  bindTrueflowAgeControls();
  updateTrueflowScopeControls();
  const optionsPromise = loadTrueflowAgeOptions();
  await loadTrueflowAgeData();
  await optionsPromise;
}

function collectTrueflowAgeElements() {
  [
    "tfa-status",
    "tfa-scope-object",
    "tfa-scope-association",
    "tfa-object-controls",
    "tfa-association-controls",
    "tfa-object-search",
    "tfa-object-results",
    "tfa-oid-input",
    "tfa-aid-filter",
    "tfa-aid-select",
    "tfa-load",
    "tfa-source-mocaflows-line",
    "tfa-mocaflows-options",
    "tfa-source-mocaflows",
    "tfa-source-legacy",
    "tfa-source-scalar",
    "tfa-posteriors",
    "tfa-hbm",
    "tfa-log-x",
    "tfa-log-y",
    "tfa-cdf",
    "tfa-combine",
    "tfa-plot",
    "tfa-plot-loader",
    "tfa-summary",
    "tfa-hint",
    "tfa-open-report",
    "tfa-export-csv",
    "tfa-export-tsv",
    "tfa-export-fits",
    "tfa-export-votable",
    "tfa-clear-cache",
    "tfa-clear-cache-bottom",
    "tfa-clear-cache-status",
    "tfa-table-title",
    "tfa-table-subtitle",
    "tfa-table",
  ].forEach((id) => {
    tfaEl[id] = document.getElementById(id);
  });
}

function readTrueflowAgeUrlState() {
  const params = new URLSearchParams(window.location.search);
  const scopeRaw = String(params.get("target") || params.get("scope") || params.get("mode") || "").toLowerCase();
  let scope = "association";
  if (scopeRaw === "object" || params.get("moca_oid") || params.get("oid")) scope = "object";
  if (scopeRaw === "association" || params.get("moca_aid") || params.get("aid")) scope = "association";
  tfaEl["tfa-scope-object"].checked = scope === "object";
  tfaEl["tfa-scope-association"].checked = scope === "association";
  tfaEl["tfa-oid-input"].value = parseInteger(params.get("moca_oid") || params.get("oid")) ?? tfaDefaultOid;
  const aid = String(params.get("moca_aid") || params.get("aid") || tfaDefaultAid).trim().toUpperCase();
  tfaEl["tfa-aid-select"].innerHTML = `<option value="${escapeHtml(aid)}">${escapeHtml(aid)}</option>`;
  tfaEl["tfa-aid-select"].value = aid;

  const sources = parseCsv(params.get("sources"), tfaDefaultSources);
  for (const [source, id] of Object.entries(tfaSourceIds)) {
    tfaEl[id].checked = sources.includes(source);
  }
  const checkbox = new Set(parseCsv(params.get("checkbox"), []));
  for (const key of ["posteriors", "hbm", "log_x", "log_y", "cdf", "combine"]) {
    if (asBool(params.get(key))) checkbox.add(key);
  }
  tfaEl["tfa-posteriors"].checked = checkbox.has("posteriors");
  tfaEl["tfa-hbm"].checked = checkbox.has("hbm") || !params.has("checkbox");
  tfaEl["tfa-log-x"].checked = checkbox.has("log_x") || !params.has("checkbox");
  tfaEl["tfa-log-y"].checked = checkbox.has("log_y");
  tfaEl["tfa-cdf"].checked = checkbox.has("cdf");
  tfaEl["tfa-combine"].checked = checkbox.has("combine");
}

function trueflowAgeUserRole() {
  const params = new URLSearchParams(window.location.search);
  const user = String(params.get("user") || params.get("username") || "").trim().toLowerCase();
  return tfaTeamUsers.has(user) ? user : "";
}

function canUseTrueflowMocaflows() {
  return Boolean(trueflowAgeUserRole());
}

function applyTrueflowMocaflowsAccess() {
  const canUseMocaflows = canUseTrueflowMocaflows();
  const mocaflowsLine = tfaEl["tfa-source-mocaflows-line"] || tfaEl["tfa-source-mocaflows"]?.closest("label");
  if (mocaflowsLine) mocaflowsLine.hidden = !canUseMocaflows;
  if (tfaEl["tfa-mocaflows-options"]) tfaEl["tfa-mocaflows-options"].hidden = !canUseMocaflows;

  for (const id of ["tfa-source-mocaflows", "tfa-posteriors", "tfa-hbm"]) {
    if (!tfaEl[id]) continue;
    tfaEl[id].disabled = !canUseMocaflows;
    if (!canUseMocaflows) tfaEl[id].checked = false;
  }
}

function bindTrueflowAgeControls() {
  tfaEl["tfa-scope-object"].addEventListener("change", () => {
    updateTrueflowScopeControls();
    loadTrueflowAgeData();
  });
  tfaEl["tfa-scope-association"].addEventListener("change", () => {
    updateTrueflowScopeControls();
    loadTrueflowAgeData();
  });
  tfaEl["tfa-oid-input"].addEventListener("change", loadTrueflowAgeData);
  tfaEl["tfa-object-search"].addEventListener("input", () => {
    const value = tfaEl["tfa-object-search"].value.trim();
    clearTimeout(tfaState.searchTimer);
    tfaState.searchTimer = setTimeout(() => searchTrueflowAgeObjects(value), 250);
  });
  tfaEl["tfa-object-search"].addEventListener("focus", () => {
    const value = tfaEl["tfa-object-search"].value.trim();
    if (value) searchTrueflowAgeObjects(value);
  });
  document.addEventListener("click", (event) => {
    if (!tfaEl["tfa-object-results"].contains(event.target) && event.target !== tfaEl["tfa-object-search"]) {
      tfaEl["tfa-object-results"].hidden = true;
    }
  });
  tfaEl["tfa-aid-filter"].addEventListener("input", () => {
    tfaState.associationFilter = tfaEl["tfa-aid-filter"].value.trim().toLowerCase();
    renderTrueflowAssociationOptions();
  });
  tfaEl["tfa-aid-select"].addEventListener("change", loadTrueflowAgeData);
  tfaEl["tfa-load"].addEventListener("click", loadTrueflowAgeData);
  tfaEl["tfa-posteriors"].addEventListener("change", loadTrueflowAgeData);
  for (const id of [
    "tfa-source-mocaflows",
    "tfa-source-legacy",
    "tfa-source-scalar",
    "tfa-hbm",
    "tfa-log-x",
    "tfa-log-y",
    "tfa-combine",
  ]) {
    tfaEl[id].addEventListener("change", () => {
      renderTrueflowAgePlot();
      updateTrueflowAgeUrl();
    });
  }
  tfaEl["tfa-cdf"].addEventListener("change", () => {
    if (tfaEl["tfa-cdf"].checked) tfaEl["tfa-log-y"].checked = false;
    renderTrueflowAgePlot();
    updateTrueflowAgeUrl();
  });
  tfaEl["tfa-export-csv"].addEventListener("click", () => exportTrueflowAge("csv"));
  tfaEl["tfa-export-tsv"].addEventListener("click", () => exportTrueflowAge("tsv"));
  tfaEl["tfa-export-fits"].addEventListener("click", () => exportTrueflowAge("fits"));
  tfaEl["tfa-export-votable"].addEventListener("click", () => exportTrueflowAge("votable"));
  tfaEl["tfa-open-report"].addEventListener("click", openTrueflowAgeReport);
  if (tfaEl["tfa-clear-cache"]) tfaEl["tfa-clear-cache"].addEventListener("click", clearTrueflowAgeCache);
  tfaEl["tfa-clear-cache-bottom"].addEventListener("click", clearTrueflowAgeCache);
  window.addEventListener("resize", debounce(() => {
    if (tfaState.payload) Plotly.Plots.resize(tfaEl["tfa-plot"]);
  }, 150));
}

function updateTrueflowScopeControls() {
  const scope = currentTrueflowScope();
  tfaEl["tfa-object-controls"].hidden = scope !== "object";
  tfaEl["tfa-association-controls"].hidden = scope !== "association";
  tfaEl["tfa-hbm"].disabled = scope !== "association";
  tfaEl["tfa-open-report"].disabled = scope !== "object" || !selectedTrueflowObjectOid();
}

async function loadTrueflowAgeOptions() {
  const params = trueflowApiParams();
  try {
    const payload = await fetchJsonUrl(tfaAppUrl(`api/trueflow-age-pdfs/options?${params.toString()}`));
    tfaState.associations = payload.associations || [];
  } catch (_error) {
    tfaState.associations = [];
  }
  renderTrueflowAssociationOptions();
}

function renderTrueflowAssociationOptions() {
  const current = String(tfaEl["tfa-aid-select"].value || tfaDefaultAid).toUpperCase();
  let rows = tfaState.associations;
  if (tfaState.associationFilter) {
    rows = rows.filter((row) => String(row.label || row.value).toLowerCase().includes(tfaState.associationFilter));
  }
  rows = rows.slice(0, 800);
  if (current && !rows.some((row) => row.value === current)) {
    rows = [{ value: current, label: current }, ...rows];
  }
  if (!rows.length) {
    rows = [{ value: current || tfaDefaultAid, label: current || tfaDefaultAid }];
  }
  tfaEl["tfa-aid-select"].innerHTML = rows.map((row) => {
    const value = row.value || "";
    const label = row.label || value;
    return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
  }).join("");
  if (rows.some((row) => row.value === current)) {
    tfaEl["tfa-aid-select"].value = current;
  }
}

async function searchTrueflowAgeObjects(query) {
  if (!query) {
    tfaEl["tfa-object-results"].hidden = true;
    return;
  }
  const params = trueflowApiParams();
  params.set("q", query);
  try {
    const payload = await fetchJsonUrl(tfaAppUrl(`api/trueflow-age-pdfs/search?${params.toString()}`));
    const options = payload.options || [];
    if (!options.length) {
      tfaEl["tfa-object-results"].innerHTML = '<div class="designation-result-note">No matches</div>';
      tfaEl["tfa-object-results"].hidden = false;
      return;
    }
    tfaEl["tfa-object-results"].innerHTML = options.map((option) => `
      <button type="button" class="designation-result" data-oid="${escapeHtml(option.value)}">
        <span>${escapeHtml(option.label || option.designation || option.value)}</span>
      </button>
    `).join("");
    tfaEl["tfa-object-results"].querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        tfaEl["tfa-oid-input"].value = button.dataset.oid;
        tfaEl["tfa-object-search"].value = "";
        tfaEl["tfa-object-results"].hidden = true;
        if (!tfaEl["tfa-scope-object"].checked) {
          tfaEl["tfa-scope-object"].checked = true;
          updateTrueflowScopeControls();
        }
        loadTrueflowAgeData();
      });
    });
    tfaEl["tfa-object-results"].hidden = false;
  } catch (error) {
    tfaEl["tfa-object-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(error.message)}</div>`;
    tfaEl["tfa-object-results"].hidden = false;
  }
}

async function loadTrueflowAgeData() {
  const token = ++tfaState.loadToken;
  setTrueflowAgeLoading(true);
  setTrueflowAgeStatus("Loading age PDFs", "loading");
  updateTrueflowScopeControls();
  updateTrueflowAgeUrl();
  const params = buildTrueflowAgeParams();
  try {
    const payload = await fetchJsonUrl(tfaAppUrl(`api/trueflow-age-pdfs/data?${params.toString()}`));
    if (token !== tfaState.loadToken) return;
    if (!payload.ok) {
      tfaState.payload = payload;
      setTrueflowAgeStatus(payload.error || "Could not load age PDFs", "error");
      renderEmptyTrueflowAge(payload.error || "Could not load age PDFs");
      return;
    }
    await hydrateTrueflowTargetDesignation(payload);
    tfaState.payload = payload;
    tfaState.focusedKey = null;
    renderTrueflowAgePlot();
    updateTrueflowAgeUrl();
  } catch (error) {
    if (token !== tfaState.loadToken) return;
    setTrueflowAgeStatus(error.message || "Could not load age PDFs", "error");
    renderEmptyTrueflowAge(error.message || "Could not load age PDFs");
  }
}

async function hydrateTrueflowTargetDesignation(payload) {
  const selection = payload?.selection || {};
  if ((selection.scope || currentTrueflowScope()) !== "object") return;
  payload.target = payload.target || {};
  if (String(payload.target.designation || "").trim()) return;
  const oid = selectedTrueflowObjectOid(payload);
  if (!oid) return;
  if (tfaState.designationCache.has(oid)) {
    const cachedDesignation = tfaState.designationCache.get(oid);
    if (cachedDesignation) payload.target.designation = cachedDesignation;
    return;
  }
  const params = new URLSearchParams();
  params.set("moca_oid", oid);
  try {
    const lookup = await fetchJsonUrl(tfaRootUrl(`api/astrometry/search?${params.toString()}`));
    const options = lookup.options || [];
    const match = options.find((option) => normalizedMocaOid(option.moca_oid || option.value) === oid) || options[0];
    const designation = String(match?.designation || "").trim();
    tfaState.designationCache.set(oid, designation);
    if (designation) {
      payload.target.designation = designation;
      payload.target.moca_oid = Number(oid);
    }
  } catch (_error) {
    tfaState.designationCache.set(oid, "");
  }
}

function renderTrueflowAgePlot() {
  const payload = tfaState.payload;
  if (!payload || !payload.curves) {
    renderEmptyTrueflowAge("No data loaded");
    return;
  }
  const curves = visibleTrueflowCurves(payload.curves);
  const showCdf = tfaEl["tfa-cdf"].checked;
  const useLogX = tfaEl["tfa-log-x"].checked;
  const useLogY = tfaEl["tfa-log-y"].checked && !showCdf;
  const traces = curves.map((curve, index) => trueflowCurveTrace(curve, index, { showCdf, useLogY }));
  if (tfaEl["tfa-combine"].checked) {
    const combined = combineTrueflowCurves(curves);
    if (combined) {
      traces.unshift(trueflowCurveTrace(combined, -1, { showCdf, useLogY }));
    }
  }
  tfaState.visibleCurves = traces.map((trace) => trace._curve).filter(Boolean);
  const title = trueflowTargetTitle(payload);
  const layout = trueflowAgeLayout(title, curves, { showCdf, useLogX, useLogY });
  Plotly.react(tfaEl["tfa-plot"], traces.map(({ _curve, ...trace }) => trace), layout, plotConfig("mocadb_trueflow_age_pdfs"));
  tfaEl["tfa-plot"].on("plotly_click", (event) => {
    const point = event?.points?.[0];
    const key = point?.data?.customdata?.[0];
    tfaState.focusedKey = key || null;
    renderTrueflowAgeTable();
  });
  renderTrueflowAgeTable();
  updateTrueflowAgeSummary(curves);
  setTrueflowAgeLoading(false);
}

function visibleTrueflowCurves(curves) {
  const sources = selectedTrueflowSources();
  const scope = currentTrueflowScope();
  const useHbm = tfaEl["tfa-hbm"].checked;
  return (curves || []).filter((curve) => {
    if (!sources.has(curve.source)) return false;
    if (scope === "association" && curve.source === "MOCAFlows") {
      return Boolean(curve.is_hbm_mocaflows) === Boolean(useHbm);
    }
    return true;
  });
}

function trueflowCurveTrace(curve, index, options) {
  let age = (curve.age_myr || []).map(Number);
  let y = options.showCdf ? cdfFromPdf(age, curve.pdf_age || []) : (curve.pdf_age || []).map(Number);
  const xOut = [];
  const yOut = [];
  for (let i = 0; i < age.length; i += 1) {
    const x = age[i];
    const value = y[i];
    if (!Number.isFinite(x) || x <= 0 || !Number.isFinite(value)) continue;
    if (options.useLogY && value <= 0) continue;
    xOut.push(x);
    yOut.push(value);
  }
  const source = curve.source || "";
  const style = curveStyle(source, index);
  return {
    x: xOut,
    y: yOut,
    type: "scatter",
    mode: "lines",
    name: curve.label || curve.key,
    line: style.line,
    opacity: style.opacity,
    customdata: xOut.map(() => curve.key),
    hovertemplate: [
      "Age: %{x:.4g} Myr",
      `${options.showCdf ? "CDF" : "PDF"}: %{y:.4g}`,
      `<extra>${escapeHtml(curve.label || curve.key)}</extra>`,
    ].join("<br>"),
    _curve: curve,
  };
}

function curveStyle(source, index) {
  if (source === "combined") {
    return { line: { width: 4, color: "#000000", dash: "solid" }, opacity: 0.9 };
  }
  const color = tfaColors[((index || 0) % tfaColors.length + tfaColors.length) % tfaColors.length];
  const mocaflowsVisible = Boolean(tfaEl["tfa-source-mocaflows"]?.checked);
  if (source === "Scalar Gaussian") {
    return { line: { width: 1.8, color, dash: mocaflowsVisible ? "dash" : "solid" }, opacity: 0.58 };
  }
  if (source === "MOCAFlows") {
    return { line: { width: 2.5, color, dash: "solid" }, opacity: 0.82 };
  }
  return { line: { width: 2.1, color, dash: mocaflowsVisible ? "dot" : "solid" }, opacity: 0.72 };
}

function trueflowAgeLayout(title, curves, options) {
  const axisRange = ageAxisRange(curves, options);
  const xaxis = {
    title: { text: "Age (Myr)", font: { size: 22 } },
    type: options.useLogX ? "log" : "linear",
    showline: true,
    linewidth: 2,
    linecolor: "black",
    mirror: true,
    ticks: "outside",
    showgrid: true,
    gridcolor: "rgba(0,0,0,0.12)",
    zeroline: false,
    automargin: true,
  };
  if (axisRange) {
    if (options.useLogX) {
      xaxis.range = [Math.log10(axisRange[0]), Math.log10(axisRange[1])];
      const ticks = plainLogTicks(axisRange[0], axisRange[1]);
      xaxis.tickmode = "array";
      xaxis.tickvals = ticks.values;
      xaxis.ticktext = ticks.text;
    } else {
      xaxis.range = axisRange;
    }
  }
  const yaxis = {
    title: { text: options.showCdf ? "CDF" : "Probability density", font: { size: 22 } },
    type: options.showCdf ? "linear" : (options.useLogY ? "log" : "linear"),
    showline: true,
    linewidth: 2,
    linecolor: "black",
    mirror: true,
    ticks: "outside",
    showgrid: true,
    gridcolor: "rgba(0,0,0,0.12)",
    zeroline: false,
    automargin: true,
  };
  if (options.showCdf) yaxis.range = [0, 1];
  if (!options.showCdf && !options.useLogY) yaxis.rangemode = "tozero";
  return {
    title: { text: title, x: 0.5, xanchor: "center", font: { size: 22 } },
    paper_bgcolor: "#e8e7ea",
    plot_bgcolor: "#ffffff",
    margin: { l: 76, r: 44, t: 68, b: 74 },
    xaxis,
    yaxis,
    showlegend: false,
    hovermode: "closest",
  };
}

function updateTrueflowAgeSummary(curves) {
  const payload = tfaState.payload;
  const meta = payload?.meta || {};
  const timing = meta.timings?.load_total;
  const sourceText = Object.entries(countBy(curves, (curve) => curve.source || "unknown"))
    .map(([source, count]) => `${source}: ${count}`)
    .join(", ") || "none";
  const target = trueflowTargetLabel(payload);
  const seconds = Number.isFinite(Number(timing)) ? ` in ${Number(timing).toFixed(1)}s` : "";
  const cacheText = payload?.cache?.hit ? " cache hit" : "";
  tfaEl["tfa-summary"].textContent = `Loaded ${meta.age_row_count || 0} scalar age rows and ${curves.length} visible curves for ${target}${seconds}${cacheText} (${sourceText}).`;
  setTrueflowAgeExportDisabled(curves.length === 0);
  tfaEl["tfa-open-report"].disabled = currentTrueflowScope() !== "object" || !selectedTrueflowObjectOid(payload);
  setTrueflowAgeStatus(`${curves.length} curves displayed`, curves.length ? "" : "error");
}

function renderTrueflowAgeTable() {
  const curves = tfaState.visibleCurves || [];
  const rows = curves.map((curve, index) => ({
    style: trueflowTableSwatch(curve, index),
    key: curve.key,
    ...(curve.summary || {}),
  }));
  const focused = tfaState.focusedKey ? rows.filter((row) => row.key === tfaState.focusedKey) : rows;
  tfaEl["tfa-table-title"].textContent = tfaState.focusedKey ? "Selected curve" : "Displayed curves";
  tfaEl["tfa-table-subtitle"].textContent = tfaState.focusedKey ? "Click empty plot space or reload to return to all curves." : `${rows.length} visible curve summaries.`;
  const columns = ["style", "curve", "source", "age", "calculation_method", "moca_pid", "adopted", "public_adopted", "comments"];
  tfaEl["tfa-table"].innerHTML = tableHtml(columns, focused, { htmlColumns: new Set(["style"]), labels: { style: "" } });
}

function trueflowTableSwatch(curve, index) {
  const style = curveStyle(curve.source || "", index);
  const line = style.line || {};
  const color = line.color || "#555555";
  const dashClass = line.dash === "dash" ? " is-dashed" : (line.dash === "dot" ? " is-dotted" : "");
  const width = Math.max(2, Number(line.width) || 2);
  return `<span class="curve-swatch${dashClass}" style="--swatch-color:${escapeHtml(color)};--swatch-width:${width}px"></span>`;
}

function renderEmptyTrueflowAge(message) {
  setTrueflowAgeLoading(false);
  tfaState.visibleCurves = [];
  const layout = {
    title: { text: message || "No age PDFs loaded", x: 0.5, xanchor: "center" },
    paper_bgcolor: "#e8e7ea",
    plot_bgcolor: "#ffffff",
    margin: { l: 76, r: 30, t: 68, b: 74 },
    xaxis: { title: "Age (Myr)", showline: true, linewidth: 2, linecolor: "black", mirror: true },
    yaxis: { title: "Probability density", showline: true, linewidth: 2, linecolor: "black", mirror: true },
  };
  Plotly.react(tfaEl["tfa-plot"], [], layout, plotConfig("mocadb_trueflow_age_pdfs_empty"));
  tfaEl["tfa-summary"].textContent = message || "No data loaded";
  tfaEl["tfa-table"].innerHTML = "";
  setTrueflowAgeExportDisabled(true);
}

function combineTrueflowCurves(curves) {
  const valid = curves.filter((curve) => {
    const age = curve.age_myr || [];
    const pdf = curve.pdf_age || [];
    return age.length > 1 && pdf.some((value) => Number(value) > 0);
  });
  if (!valid.length) return null;
  const allAges = valid.flatMap((curve) => curve.age_myr || []).map(Number).filter((value) => Number.isFinite(value) && value > 0);
  if (allAges.length < 2) return null;
  const logMin = Math.log10(Math.min(...allAges));
  const logMax = Math.log10(Math.max(...allAges));
  if (!Number.isFinite(logMin) || !Number.isFinite(logMax) || logMax <= logMin) return null;
  const n = 1200;
  const logGrid = Array.from({ length: n }, (_value, index) => logMin + (index * (logMax - logMin)) / (n - 1));
  const logSum = Array(n).fill(0);
  const covered = Array(n).fill(true);
  for (const curve of valid) {
    const pairs = [];
    for (let i = 0; i < (curve.age_myr || []).length; i += 1) {
      const age = Number(curve.age_myr[i]);
      const pdf = Number(curve.pdf_age[i]);
      if (Number.isFinite(age) && age > 0 && Number.isFinite(pdf) && pdf > 0) {
        pairs.push([Math.log10(age), Math.log(Math.max(pdf, 1e-300))]);
      }
    }
    if (pairs.length < 2) continue;
    pairs.sort((a, b) => a[0] - b[0]);
    for (let i = 0; i < n; i += 1) {
      const interp = interpSorted(logGrid[i], pairs);
      if (interp === null) {
        covered[i] = false;
      } else {
        logSum[i] += interp;
      }
    }
  }
  const maxLog = Math.max(...logSum.filter((_value, index) => covered[index]));
  if (!Number.isFinite(maxLog)) return null;
  const age = logGrid.map((value) => 10 ** value);
  const rawPdf = logSum.map((value, index) => covered[index] ? Math.exp(value - maxLog) : 0);
  const pdf = normalizePdf(age, rawPdf);
  if (!pdf.some((value) => value > 0)) return null;
  return {
    key: "combined-visible",
    label: "Product of visible curves",
    source: "combined",
    age_myr: age,
    pdf_age: pdf,
    is_hbm_mocaflows: false,
    summary: {
      curve: "Product of visible curves",
      source: "combined",
      age: percentileText(age, pdf),
      calculation_method: "",
      moca_pid: "",
      adopted: "",
      public_adopted: "",
      comments: `Product of ${valid.length} visible curves`,
    },
  };
}

function interpSorted(x, pairs) {
  if (x < pairs[0][0] || x > pairs[pairs.length - 1][0]) return null;
  let lo = 0;
  let hi = pairs.length - 1;
  while (hi - lo > 1) {
    const mid = Math.floor((lo + hi) / 2);
    if (pairs[mid][0] <= x) lo = mid;
    else hi = mid;
  }
  const [x0, y0] = pairs[lo];
  const [x1, y1] = pairs[hi];
  if (x1 === x0) return y0;
  return y0 + ((x - x0) / (x1 - x0)) * (y1 - y0);
}

function normalizePdf(age, pdf) {
  const out = pdf.map((value) => Math.max(Number(value) || 0, 0));
  let norm = 0;
  for (let i = 1; i < age.length; i += 1) {
    const x0 = Number(age[i - 1]);
    const x1 = Number(age[i]);
    if (Number.isFinite(x0) && Number.isFinite(x1) && x1 > x0) {
      norm += 0.5 * (out[i - 1] + out[i]) * (x1 - x0);
    }
  }
  if (!Number.isFinite(norm) || norm <= 0) return out.map(() => 0);
  return out.map((value) => value / norm);
}

function cdfFromPdf(age, pdf) {
  const normed = normalizePdf(age, pdf);
  const cdf = Array(normed.length).fill(0);
  let total = 0;
  for (let i = 1; i < age.length; i += 1) {
    const x0 = Number(age[i - 1]);
    const x1 = Number(age[i]);
    if (Number.isFinite(x0) && Number.isFinite(x1) && x1 > x0) {
      total += 0.5 * (normed[i - 1] + normed[i]) * (x1 - x0);
    }
    cdf[i] = total;
  }
  const last = cdf[cdf.length - 1] || 1;
  return cdf.map((value) => Math.max(0, Math.min(1, value / last)));
}

function percentileText(age, pdf) {
  const cdf = cdfFromPdf(age, pdf);
  const p16 = interpPercentile(age, cdf, 0.16);
  const p50 = interpPercentile(age, cdf, 0.5);
  const p84 = interpPercentile(age, cdf, 0.84);
  if (![p16, p50, p84].every(Number.isFinite)) return "";
  return `${formatSig(p50)} (+${formatSig(p84 - p50)}/-${formatSig(p50 - p16)}) Myr`;
}

function interpPercentile(age, cdf, p) {
  for (let i = 1; i < cdf.length; i += 1) {
    if (cdf[i] >= p) {
      const c0 = cdf[i - 1];
      const c1 = cdf[i];
      if (c1 === c0) return age[i];
      return age[i - 1] + ((p - c0) / (c1 - c0)) * (age[i] - age[i - 1]);
    }
  }
  return NaN;
}

function ageAxisRange(curves, options = {}) {
  const ages = curves.flatMap((curve) => curve.age_myr || []).map(Number).filter((value) => Number.isFinite(value) && value > 0);
  if (ages.length < 2) return null;
  const xmin = Math.min(...ages);
  const xmax = Math.max(...ages);
  if (!(xmax > xmin)) return null;
  const logPad = 0.06 * (Math.log10(xmax) - Math.log10(xmin));
  const lower = 10 ** (Math.log10(xmin) - logPad);
  const upper = 10 ** (Math.log10(xmax) + logPad);
  if (options.useLogX) return [lower, upper];
  const cappedUpper = Math.min(upper, tfaUniverseAgeMyr);
  return [Math.min(lower, cappedUpper * 0.999), cappedUpper];
}

function plainLogTicks(xmin, xmax) {
  const values = [];
  const lo = Math.floor(Math.log10(xmin)) - 1;
  const hi = Math.ceil(Math.log10(xmax)) + 1;
  for (let decade = lo; decade <= hi; decade += 1) {
    const base = 10 ** decade;
    for (let multiplier = 1; multiplier < 10; multiplier += 1) {
      const value = multiplier * base;
      if (value >= xmin && value <= xmax) values.push(value);
    }
  }
  return { values, text: values.map(formatPlainAgeTick) };
}

function formatPlainAgeTick(value) {
  if (value >= 100) return String(Math.round(value));
  if (value >= 10) return Math.abs(value - Math.round(value)) < 1e-8 ? String(Math.round(value)) : value.toFixed(1).replace(/\.0$/, "");
  if (value >= 1) return Math.abs(value - Math.round(value)) < 1e-8 ? String(Math.round(value)) : value.toPrecision(2);
  return value.toPrecision(2);
}

function selectedTrueflowSources() {
  const out = new Set();
  for (const [source, id] of Object.entries(tfaSourceIds)) {
    if (source === "MOCAFlows" && !canUseTrueflowMocaflows()) continue;
    if (tfaEl[id].checked) out.add(source);
  }
  return out;
}

function currentTrueflowScope() {
  return tfaEl["tfa-scope-association"].checked ? "association" : "object";
}

function buildTrueflowAgeParams() {
  const params = trueflowApiParams();
  const scope = currentTrueflowScope();
  params.set("target", scope);
  if (scope === "association") {
    params.set("moca_aid", String(tfaEl["tfa-aid-select"].value || tfaDefaultAid).toUpperCase());
  } else {
    const oid = parseInteger(tfaEl["tfa-oid-input"].value) ?? tfaDefaultOid;
    params.set("moca_oid", oid);
  }
  if (canUseTrueflowMocaflows() && tfaEl["tfa-posteriors"].checked) params.set("posteriors", "1");
  return params;
}

function trueflowApiParams() {
  const urlParams = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["mock", "host", "user", "username", "pwd", "password", "dbase", "db", "database", "port"]) {
    if (urlParams.has(key)) params.set(key, urlParams.get(key));
  }
  return params;
}

function updateTrueflowAgeUrl() {
  const params = new URLSearchParams(window.location.search);
  const scope = currentTrueflowScope();
  params.set("target", scope);
  if (scope === "association") {
    params.delete("moca_oid");
    params.delete("oid");
    params.set("moca_aid", String(tfaEl["tfa-aid-select"].value || tfaDefaultAid).toUpperCase());
  } else {
    params.delete("moca_aid");
    params.delete("aid");
    params.set("moca_oid", parseInteger(tfaEl["tfa-oid-input"].value) ?? tfaDefaultOid);
  }
  params.set("sources", Array.from(selectedTrueflowSources()).join(","));
  const checkbox = [];
  if (canUseTrueflowMocaflows() && tfaEl["tfa-posteriors"].checked) checkbox.push("posteriors");
  if (canUseTrueflowMocaflows() && tfaEl["tfa-hbm"].checked) checkbox.push("hbm");
  if (tfaEl["tfa-log-x"].checked) checkbox.push("log_x");
  if (tfaEl["tfa-log-y"].checked) checkbox.push("log_y");
  if (tfaEl["tfa-cdf"].checked) checkbox.push("cdf");
  if (tfaEl["tfa-combine"].checked) checkbox.push("combine");
  params.set("checkbox", checkbox.join(","));
  const next = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState({}, "", next);
}

function trueflowTargetTitle(payload) {
  const selection = payload?.selection || {};
  const target = payload?.target || {};
  if ((selection.scope || currentTrueflowScope()) === "association") {
    return `${trueflowTargetLabel(payload)} age PDFs`;
  }
  const oid = selectedTrueflowObjectOid(payload);
  const designation = String(target.designation || "").trim();
  return designation ? `${designation} (moca_oid=${oid || ""}) age PDFs` : `moca_oid=${oid || ""} age PDFs`;
}

function trueflowTargetLabel(payload) {
  const target = payload?.target || {};
  const selection = payload?.selection || {};
  if ((selection.scope || currentTrueflowScope()) === "association") {
    const aid = target.moca_aid || selection.moca_aid || selection.target || tfaEl["tfa-aid-select"].value || "association";
    return target.name ? `${aid}; ${target.name}` : String(aid);
  }
  const oid = selectedTrueflowObjectOid(payload);
  const designation = String(target.designation || "").trim();
  return designation ? `${designation} (moca_oid=${oid})` : `moca_oid=${oid || ""}`;
}

const trueflowAgeExportColumns = ["curve", "source", "age", "calculation_method", "moca_pid", "adopted", "public_adopted", "comments"];
const trueflowAgeNumericExportColumns = new Set(["age", "moca_pid", "adopted", "public_adopted"]);

function exportTrueflowAge(format) {
  const rows = (tfaState.visibleCurves || []).map((curve) => curve.summary || {});
  if (!rows.length) return;
  MocaExport.saveTable(format, {
    rows,
    columns: trueflowAgeExportColumns,
    numericColumns: trueflowAgeNumericExportColumns,
    filenameBase: "mocadb_trueflow_age_pdfs",
    tableName: "mocadb_trueflow_age_pdfs",
    resourceName: "MOCAdb Age PDF Explorer",
    extName: "AGE_PDFS",
  });
}

function setTrueflowAgeExportDisabled(disabled) {
  for (const id of ["tfa-export-csv", "tfa-export-tsv", "tfa-export-fits", "tfa-export-votable"]) {
    if (tfaEl[id]) tfaEl[id].disabled = disabled;
  }
}

function openTrueflowAgeReport() {
  const url = mocaReportUrl(selectedTrueflowObjectOid());
  if (url) window.open(url, "_blank", "noopener");
}

async function clearTrueflowAgeCache() {
  tfaEl["tfa-clear-cache-status"].textContent = "Clearing cache...";
  tfaEl["tfa-clear-cache-status"].classList.remove("error");
  try {
    const payload = await postJson("api/trueflow-age-pdfs/cache/clear", {});
    const count = payload.cleared?.trueflowAgePdfs || 0;
    tfaEl["tfa-clear-cache-status"].textContent = `Cleared ${count} cached payload${count === 1 ? "" : "s"}.`;
  } catch (error) {
    tfaEl["tfa-clear-cache-status"].textContent = error.message;
    tfaEl["tfa-clear-cache-status"].classList.add("error");
  }
}

function setTrueflowAgeStatus(message, state) {
  tfaEl["tfa-status"].textContent = message || "";
  tfaEl["tfa-status"].classList.toggle("loading", state === "loading");
  tfaEl["tfa-status"].classList.toggle("error", state === "error");
}

function setTrueflowAgeLoading(isLoading) {
  tfaEl["tfa-plot-loader"].classList.toggle("is-visible", Boolean(isLoading));
  tfaEl["tfa-load"].disabled = Boolean(isLoading);
}

async function fetchJsonUrl(url) {
  const response = await fetch(url);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function postJson(path, body) {
  const response = await fetch(tfaAppUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function tableHtml(columns, rows, options = {}) {
  if (!rows.length) return '<div class="empty-table">No rows to display</div>';
  const labels = options.labels || {};
  const header = columns.map((column) => `<th>${escapeHtml(labels[column] ?? column)}</th>`).join("");
  const htmlColumns = options.htmlColumns || new Set();
  const body = rows.map((row) => `<tr>${columns.map((column) => {
    const value = formatCell(row[column]);
    return `<td>${htmlColumns.has(column) ? value : escapeHtml(value)}</td>`;
  }).join("")}</tr>`).join("");
  return `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
}

function plotConfig(filename) {
  return {
    displaylogo: false,
    responsive: true,
    toImageButtonOptions: {
      format: "png",
      filename,
      height: 900,
      width: 1300,
      scale: 2,
    },
  };
}

function parseCsv(value, fallback = []) {
  if (!value) return [...fallback];
  return String(value).split(",").map((item) => item.trim()).filter(Boolean);
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function parseInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
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

function countBy(values, fn) {
  const out = {};
  for (const value of values) {
    const key = fn(value);
    out[key] = (out[key] || 0) + 1;
  }
  return out;
}

function selectedTrueflowObjectOid(payload = tfaState.payload) {
  const selection = payload?.selection || {};
  const target = payload?.target || {};
  if ((selection.scope || currentTrueflowScope()) !== "object") return "";
  return normalizedMocaOid(target.moca_oid || selection.moca_oid || selection.target || tfaEl["tfa-oid-input"].value);
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
