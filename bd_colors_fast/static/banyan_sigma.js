const bsigEl = {};
const bsigState = {
  model: null,
  object: null,
  stored: null,
  result: null,
  searchTimer: null,
  loadToken: 0,
};

const bsigFieldIds = [
  "name", "ra", "dec", "pmra", "pmdec", "epmra", "epmdec",
  "rv", "erv", "plx", "eplx", "dist", "edist",
  "psira", "psidec", "epsira", "epsidec",
];

document.addEventListener("DOMContentLoaded", initBanyanSigma);

const bsigAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function bsigAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), bsigAppBaseUrl).toString();
}

async function initBanyanSigma() {
  collectBanyanSigmaElements();
  bindBanyanSigmaControls();
  readBanyanSigmaUrlState();
  updateBanyanSigmaRangeControls();
  renderBanyanSigmaInputTable();
  await loadBanyanSigmaModel();
  const oid = currentBanyanSigmaOid();
  if (oid) await loadBanyanSigmaObject(oid);
  setBanyanSigmaLoader(false);
}

function collectBanyanSigmaElements() {
  [
    "bsig-status", "bsig-object-search", "bsig-object-results",
    "bsig-moca-oid", "bsig-load-object", "bsig-clear-object",
    "bsig-loaded-object", "bsig-name", "bsig-ra", "bsig-dec",
    "bsig-pmra", "bsig-pmdec", "bsig-epmra", "bsig-epmdec",
    "bsig-use-rv", "bsig-rv", "bsig-erv", "bsig-distance-mode",
    "bsig-plx", "bsig-eplx", "bsig-dist", "bsig-edist",
    "bsig-use-psi", "bsig-psira", "bsig-psidec", "bsig-epsira",
    "bsig-epsidec", "bsig-top-n", "bsig-limit-parallax-range",
    "bsig-use-manual-range", "bsig-range-min", "bsig-range-max", "bsig-unit-priors",
    "bsig-no-xyz", "bsig-run", "bsig-ya-prob", "bsig-best-hyp",
    "bsig-best-ya", "bsig-field-prob", "bsig-model-count",
    "bsig-prob-plot", "bsig-plot-loader", "bsig-summary",
    "bsig-subtitle", "bsig-export-csv", "bsig-export-tsv",
    "bsig-clear-cache", "bsig-result-subtitle", "bsig-results-table",
    "bsig-stored-subtitle", "bsig-stored-table", "bsig-input-subtitle",
    "bsig-input-table",
  ].forEach((id) => {
    bsigEl[id] = document.getElementById(id);
  });
}

function bindBanyanSigmaControls() {
  bsigEl["bsig-object-search"].addEventListener("input", () => scheduleBanyanSigmaObjectSearch());
  bsigEl["bsig-load-object"].addEventListener("click", () => {
    const oid = currentBanyanSigmaOid();
    if (oid) loadBanyanSigmaObject(oid);
  });
  bsigEl["bsig-clear-object"].addEventListener("click", () => clearBanyanSigmaObject());
  bsigEl["bsig-run"].addEventListener("click", () => runBanyanSigma());
  bsigEl["bsig-clear-cache"].addEventListener("click", () => clearBanyanSigmaCache());
  bsigEl["bsig-export-csv"].addEventListener("click", () => exportBanyanSigma("csv"));
  bsigEl["bsig-export-tsv"].addEventListener("click", () => exportBanyanSigma("tsv"));
  bsigEl["bsig-moca-oid"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      const oid = currentBanyanSigmaOid();
      if (oid) loadBanyanSigmaObject(oid);
    }
  });
  bsigEl["bsig-moca-oid"].addEventListener("change", () => updateBanyanSigmaUrl());
  for (const id of [
    "bsig-distance-mode", "bsig-use-rv", "bsig-use-psi",
    "bsig-limit-parallax-range", "bsig-use-manual-range",
    "bsig-range-min", "bsig-range-max", "bsig-unit-priors", "bsig-no-xyz", "bsig-top-n",
  ]) {
    bsigEl[id].addEventListener("change", () => {
      updateBanyanSigmaUrl();
      updateBanyanSigmaRangeControls();
      renderBanyanSigmaInputTable();
    });
  }
  for (const field of bsigFieldIds) {
    bsigEl[`bsig-${field}`].addEventListener("change", renderBanyanSigmaInputTable);
  }
  window.addEventListener("resize", debounce(() => {
    if (bsigState.result) Plotly.Plots.resize(bsigEl["bsig-prob-plot"]);
  }, 150));
}

function readBanyanSigmaUrlState() {
  const params = new URLSearchParams(window.location.search);
  const oid = firstParam(params, "oid", "moca_oid");
  if (oid) bsigEl["bsig-moca-oid"].value = oid;
  const topN = firstParam(params, "top", "top_n");
  if (topN) bsigEl["bsig-top-n"].value = topN;
}

async function loadBanyanSigmaModel() {
  try {
    const params = connectionParams();
    const payload = await fetchJsonUrl(bsigAppUrl(`api/banyan-sigma/model?${params.toString()}`));
    if (!payload.ok) throw new Error(payload.error || "Model unavailable");
    bsigState.model = payload.model;
    bsigEl["bsig-model-count"].textContent = formatBanyanSigmaHypothesisCount(payload.model || {});
    setBanyanSigmaStatus("Ready", "");
  } catch (error) {
    bsigEl["bsig-model-count"].textContent = "--";
    setBanyanSigmaStatus(error.message, "error");
  }
}

function scheduleBanyanSigmaObjectSearch() {
  clearTimeout(bsigState.searchTimer);
  bsigState.searchTimer = setTimeout(() => runBanyanSigmaObjectSearch(), 180);
}

async function runBanyanSigmaObjectSearch() {
  const query = bsigEl["bsig-object-search"].value.trim();
  if (!query) {
    bsigEl["bsig-object-results"].hidden = true;
    bsigEl["bsig-object-results"].innerHTML = "";
    return;
  }
  const params = connectionParams();
  params.set("q", query);
  try {
    const payload = await fetchJsonUrl(bsigAppUrl(`api/banyan-sigma/search?${params.toString()}`));
    const options = payload.options || [];
    bsigEl["bsig-object-results"].innerHTML = options.length
      ? options.map((row) => {
        const oid = Number(row.moca_oid || row.value);
        const label = row.label || row.designation || row.canonical_designation || `oid${oid}`;
        return `<button type="button" class="designation-result" data-oid="${oid}">${htmlEscape(label)} <span class="designation-result-note-inline">oid${oid}</span></button>`;
      }).join("")
      : `<div class="designation-result-note">No matches</div>`;
    bsigEl["bsig-object-results"].hidden = false;
    bsigEl["bsig-object-results"].querySelectorAll("button[data-oid]").forEach((button) => {
      button.addEventListener("click", () => {
        const oid = Number(button.dataset.oid);
        bsigEl["bsig-moca-oid"].value = Number.isFinite(oid) ? String(oid) : "";
        bsigEl["bsig-object-search"].value = "";
        bsigEl["bsig-object-results"].hidden = true;
        if (oid) loadBanyanSigmaObject(oid);
      });
    });
  } catch (error) {
    bsigEl["bsig-object-results"].innerHTML = `<div class="designation-result-note">${htmlEscape(error.message)}</div>`;
    bsigEl["bsig-object-results"].hidden = false;
  }
}

async function loadBanyanSigmaObject(oid) {
  const numericOid = Number(oid);
  if (!Number.isFinite(numericOid) || numericOid <= 0) return;
  const token = ++bsigState.loadToken;
  setBanyanSigmaStatus(`Loading oid${numericOid}`, "loading");
  setBanyanSigmaLoader(true);
  updateBanyanSigmaUrl();
  try {
    const params = connectionParams();
    const payload = await fetchJsonUrl(bsigAppUrl(`api/banyan-sigma/object/${Math.trunc(numericOid)}?${params.toString()}`));
    if (token !== bsigState.loadToken) return;
    if (!payload.ok) throw new Error(payload.error || "Object load failed");
    bsigState.object = payload.object || null;
    bsigState.stored = payload.stored || null;
    fillBanyanSigmaForm(payload.observables || {});
    renderBanyanSigmaStored(payload.stored || null);
    renderBanyanSigmaInputTable();
    const label = payload.object?.designation || payload.observables?.name || `oid${numericOid}`;
    bsigEl["bsig-loaded-object"].textContent = `${label} (oid${Math.trunc(numericOid)})`;
    setBanyanSigmaStatus("Object loaded", "");
  } catch (error) {
    setBanyanSigmaStatus(error.message, "error");
  } finally {
    setBanyanSigmaLoader(false);
  }
}

function clearBanyanSigmaObject() {
  bsigState.object = null;
  bsigState.stored = null;
  bsigEl["bsig-moca-oid"].value = "";
  bsigEl["bsig-loaded-object"].textContent = "No object loaded";
  renderBanyanSigmaStored(null);
  updateBanyanSigmaUrl();
}

async function runBanyanSigma() {
  const payload = buildBanyanSigmaPayload();
  setBanyanSigmaStatus("Running BANYAN Sigma", "loading");
  setBanyanSigmaLoader(true);
  bsigEl["bsig-run"].disabled = true;
  try {
    const params = connectionParams();
    const response = await postJson(bsigAppUrl(`api/banyan-sigma/run?${params.toString()}`), payload);
    if (!response.ok) throw new Error(response.error || "BANYAN Sigma run failed");
    bsigState.result = response.result || null;
    if (response.stored) {
      bsigState.stored = response.stored;
      renderBanyanSigmaStored(response.stored);
    }
    renderBanyanSigmaResult(response.result || null, response.cache || {});
    renderBanyanSigmaInputTable();
    setBanyanSigmaStatus(response.cache?.hit ? "Loaded cached run" : "Run complete", "");
  } catch (error) {
    setBanyanSigmaStatus(error.message, "error");
  } finally {
    bsigEl["bsig-run"].disabled = false;
    setBanyanSigmaLoader(false);
  }
}

function buildBanyanSigmaPayload() {
  return {
    moca_oid: currentBanyanSigmaOid(),
    observables: readBanyanSigmaForm(),
    options: {
      top_n: Number(bsigEl["bsig-top-n"].value) || 4,
      use_rv: bsigEl["bsig-use-rv"].checked,
      distance_mode: bsigEl["bsig-distance-mode"].value || "none",
      use_psi: bsigEl["bsig-use-psi"].checked,
      unit_priors: bsigEl["bsig-unit-priors"].checked,
      no_xyz: bsigEl["bsig-no-xyz"].checked,
      limit_parallax_5sigma: bsigEl["bsig-limit-parallax-range"].checked,
      use_manual_distance_range: bsigEl["bsig-use-manual-range"].checked,
      distance_range_min_pc: nullableNumber(bsigEl["bsig-range-min"].value),
      distance_range_max_pc: nullableNumber(bsigEl["bsig-range-max"].value),
    },
  };
}

function readBanyanSigmaForm() {
  const out = {};
  for (const field of bsigFieldIds) {
    const input = bsigEl[`bsig-${field}`];
    out[field] = input.type === "number" ? nullableNumber(input.value) : input.value.trim();
  }
  return out;
}

function fillBanyanSigmaForm(observables) {
  for (const field of bsigFieldIds) {
    const value = observables[field];
    bsigEl[`bsig-${field}`].value = value === null || value === undefined ? "" : String(value);
  }
  bsigEl["bsig-use-rv"].checked = finite(observables.rv) && finite(observables.erv);
  if (finite(observables.plx) && finite(observables.eplx)) {
    bsigEl["bsig-distance-mode"].value = "plx";
  } else if (finite(observables.dist) && finite(observables.edist)) {
    bsigEl["bsig-distance-mode"].value = "dist";
  } else {
    bsigEl["bsig-distance-mode"].value = "none";
  }
  bsigEl["bsig-use-psi"].checked = ["psira", "psidec", "epsira", "epsidec"].every((key) => finite(observables[key]));
}

function renderBanyanSigmaResult(result, cache) {
  if (!result) return;
  const summary = result.summary || {};
  const meta = result.meta || {};
  bsigEl["bsig-ya-prob"].textContent = formatPercent(summary.ya_probability_pct);
  bsigEl["bsig-best-hyp"].textContent = summary.best_hyp || "--";
  bsigEl["bsig-best-ya"].textContent = summary.best_ya || "--";
  bsigEl["bsig-field-prob"].textContent = formatPercent(summary.field_probability_pct);
  const hypothesisCount = formatBanyanSigmaHypothesisCount(meta);
  bsigEl["bsig-model-count"].textContent = hypothesisCount;
  bsigEl["bsig-summary"].textContent = `${result.used_observables?.join(", ") || "Inputs"}; ${hypothesisCount} hypotheses`;
  const subtitleParts = [
    `Global pass ${formatNumber(meta.lnp_seconds, 1)} s`,
    `details ${formatNumber(meta.detail_seconds, 2)} s`,
  ];
  const distanceFilter = formatBanyanSigmaDistanceFilter(meta.distance_filter);
  if (distanceFilter) subtitleParts.push(distanceFilter);
  const hypothesisFilterNote = formatBanyanSigmaHypothesisFilterNote(meta.hypothesis_filter);
  if (hypothesisFilterNote) subtitleParts.push(hypothesisFilterNote);
  if (cache?.hit) subtitleParts.push("cached");
  bsigEl["bsig-subtitle"].textContent = `${subtitleParts.join("; ")}.`;
  bsigEl["bsig-result-subtitle"].textContent = `${result.top_rows?.length || 0} displayed hypotheses`;
  bsigEl["bsig-export-csv"].disabled = !(result.top_rows || []).length;
  bsigEl["bsig-export-tsv"].disabled = !(result.top_rows || []).length;
  renderBanyanSigmaPlot(result.top_rows || []);
  renderBanyanSigmaResultsTable(result.top_rows || []);
}

function renderBanyanSigmaPlot(rows) {
  if (!rows.length) {
    Plotly.purge(bsigEl["bsig-prob-plot"]);
    return;
  }
  const displayRows = [...rows].reverse();
  const colors = displayRows.map((row) => row.is_field ? "#77717b" : row.rank === 1 ? "#0072b2" : "#009e73");
  const trace = {
    type: "bar",
    orientation: "h",
    x: displayRows.map((row) => row.probability_pct || 0),
    y: displayRows.map((row) => row.hypothesis || ""),
    marker: { color: colors },
    hovertemplate: "%{y}<br>%{x:.4g}%<extra></extra>",
  };
  const layout = {
    margin: { l: 92, r: 22, t: 24, b: 42 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    xaxis: { title: "Probability (%)", rangemode: "tozero" },
    yaxis: { automargin: true },
    font: { family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", size: 12 },
  };
  Plotly.react(bsigEl["bsig-prob-plot"], [trace], layout, plotConfig("banyan_sigma_probabilities"));
}

function renderBanyanSigmaResultsTable(rows) {
  const columns = [
    ["rank", "Rank"],
    ["hypothesis", "Hypothesis"],
    ["probability_pct", "Prob (%)"],
    ["d_opt", "D opt"],
    ["ed_opt", "eD opt"],
    ["rv_opt", "RV opt"],
    ["erv_opt", "eRV opt"],
    ["xyz_sep", "XYZ sep"],
    ["uvw_sep", "UVW sep"],
    ["xyz_sig", "XYZ sig"],
    ["uvw_sig", "UVW sig"],
    ["mahalanobis", "Mahalanobis"],
  ];
  bsigEl["bsig-results-table"].innerHTML = renderTable(rows, columns);
}

function renderBanyanSigmaStored(stored) {
  const summaries = stored?.summaries || [];
  const details = stored?.details || [];
  if (!summaries.length && !details.length) {
    bsigEl["bsig-stored-subtitle"].textContent = bsigState.object ? "No stored adopted result found" : "No object loaded";
    bsigEl["bsig-stored-table"].innerHTML = "";
    return;
  }
  bsigEl["bsig-stored-subtitle"].textContent = `${summaries.length} summary rows; ${details.length} detail rows`;
  const summaryColumns = [
    ["moca_bsmdid", "Model"],
    ["moca_aid", "Aid"],
    ["ya_prob", "YA(%)"],
    ["all_prob_yas", "all_prob_yas"],
    ["best_hyp", "Best hyp"],
    ["best_ya", "Best YA"],
    ["observables", "Obs"],
    ["d_opt", "D opt"],
    ["rv_opt", "RV opt"],
    ["nobs", "N obs"],
  ];
  const detailColumns = [
    ["cbs_id", "CBS id"],
    ["moca_aid", "Aid"],
    ["prob", "Prob (%)"],
    ["d_opt", "D opt"],
    ["rv_opt", "RV opt"],
    ["xyz_sep", "XYZ sep"],
    ["uvw_sep", "UVW sep"],
    ["mahalanobis", "Mahalanobis"],
  ];
  bsigEl["bsig-stored-table"].innerHTML = [
    summaries.length ? `<div class="bsig-subtable-title">Summary</div>${renderTable(summaries, summaryColumns)}` : "",
    details.length ? `<div class="bsig-subtable-title">Details</div>${renderTable(details.slice(0, 80), detailColumns)}` : "",
  ].join("");
}

function renderBanyanSigmaInputTable() {
  const obs = readBanyanSigmaForm();
  const rows = [
    ["Name", obs.name],
    ["RA", obs.ra],
    ["Dec", obs.dec],
    ["pmRA", obs.pmra],
    ["pmDec", obs.pmdec],
    ["e_pmRA", obs.epmra],
    ["e_pmDec", obs.epmdec],
    ["RV", bsigEl["bsig-use-rv"].checked ? obs.rv : ""],
    ["e_RV", bsigEl["bsig-use-rv"].checked ? obs.erv : ""],
    ["Distance mode", bsigEl["bsig-distance-mode"].value],
    ["Parallax", bsigEl["bsig-distance-mode"].value === "plx" ? obs.plx : ""],
    ["e_Parallax", bsigEl["bsig-distance-mode"].value === "plx" ? obs.eplx : ""],
    ["Distance", bsigEl["bsig-distance-mode"].value === "dist" ? obs.dist : ""],
    ["e_Distance", bsigEl["bsig-distance-mode"].value === "dist" ? obs.edist : ""],
    ["5-sigma parallax range", bsigEl["bsig-limit-parallax-range"].checked ? "on" : "off"],
    ["Manual distance range", bsigEl["bsig-use-manual-range"].checked ? formatBanyanSigmaManualRange() : "off"],
    ["PSI", bsigEl["bsig-use-psi"].checked ? "on" : "off"],
  ].map(([key, value]) => ({ key, value }));
  bsigEl["bsig-input-table"].innerHTML = renderTable(rows, [["key", "Input"], ["value", "Value"]]);
}

function updateBanyanSigmaRangeControls() {
  const enabled = bsigEl["bsig-use-manual-range"].checked;
  for (const id of ["bsig-range-min", "bsig-range-max"]) {
    bsigEl[id].disabled = !enabled;
    bsigEl[id].closest("label")?.classList.toggle("disabled-field", !enabled);
  }
}

function formatBanyanSigmaManualRange() {
  const minPc = nullableNumber(bsigEl["bsig-range-min"].value);
  const maxPc = nullableNumber(bsigEl["bsig-range-max"].value);
  if (!finite(minPc) && !finite(maxPc)) return "";
  return `${formatNumber(minPc, 2)}-${formatNumber(maxPc, 2)} pc`;
}

function formatBanyanSigmaDistanceFilter(filter) {
  if (!filter?.applied) return "";
  const sourceLabels = {
    parallax_5sigma: "5-sigma parallax range",
    manual: "manual distance range",
    "parallax_5sigma+manual": "combined distance range",
  };
  const label = sourceLabels[filter.source] || "distance range";
  if (filter.upper_unbounded) return `${label}: >= ${formatNumber(filter.min_pc, 2)} pc`;
  return `${label}: ${formatNumber(filter.min_pc, 2)}-${formatNumber(filter.max_pc, 2)} pc`;
}

function formatBanyanSigmaHypothesisCount(meta) {
  const filter = meta?.hypothesis_filter;
  const total = filter?.total_count ?? meta?.hypothesis_count ?? bsigState.model?.hypothesis_count;
  if (filter?.applied && finite(filter.tested_count) && finite(total)) {
    return `${formatInteger(filter.tested_count)}/${formatInteger(total)}*`;
  }
  return formatInteger(total);
}

function formatBanyanSigmaHypothesisFilterNote(filter) {
  if (!filter?.applied || !finite(filter.tested_count) || !finite(filter.total_count)) return "";
  const excluded = finite(filter.excluded_count) ? `; ${formatInteger(filter.excluded_count)} excluded` : "";
  return `*Model hypotheses shows tested/total after distance-range filtering (${formatInteger(filter.tested_count)}/${formatInteger(filter.total_count)}${excluded}); the field hypothesis is retained.`;
}

async function clearBanyanSigmaCache() {
  try {
    const params = connectionParams();
    const payload = await postJson(bsigAppUrl(`api/banyan-sigma/cache/clear?${params.toString()}`), {});
    const count = payload.cleared?.banyanSigma || 0;
    setBanyanSigmaStatus(`Cleared ${count} cached runs`, "");
  } catch (error) {
    setBanyanSigmaStatus(error.message, "error");
  }
}

function exportBanyanSigma(kind) {
  const rows = bsigState.result?.top_rows || [];
  if (!rows.length) return;
  const columns = ["rank", "hypothesis", "probability_pct", "d_opt", "ed_opt", "rv_opt", "erv_opt", "xyz_sep", "uvw_sep", "xyz_sig", "uvw_sig", "mahalanobis"];
  const delimiter = kind === "tsv" ? "\t" : ",";
  const text = [
    columns.join(delimiter),
    ...rows.map((row) => columns.map((column) => csvCell(row[column], delimiter)).join(delimiter)),
  ].join("\n");
  const blob = new Blob([text], { type: kind === "tsv" ? "text/tab-separated-values" : "text/csv" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `banyan_sigma_top.${kind}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function currentBanyanSigmaOid() {
  const value = Number(bsigEl["bsig-moca-oid"].value);
  return Number.isFinite(value) && value > 0 ? Math.trunc(value) : null;
}

function updateBanyanSigmaUrl() {
  const params = new URLSearchParams(window.location.search);
  for (const key of ["oid", "moca_oid", "top", "top_n"]) params.delete(key);
  const oid = currentBanyanSigmaOid();
  if (oid) params.set("oid", String(oid));
  const topN = Number(bsigEl["bsig-top-n"].value);
  if (Number.isFinite(topN) && topN > 0) params.set("top", String(Math.trunc(topN)));
  const next = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ""}${window.location.hash}`;
  window.history.replaceState({}, "", next);
}

function connectionParams() {
  const current = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "port", "user", "pwd", "dbase", "db", "database", "mock"]) {
    if (current.has(key)) params.set(key, current.get(key) || "");
  }
  return params;
}

function setBanyanSigmaStatus(text, mode) {
  bsigEl["bsig-status"].textContent = text;
  bsigEl["bsig-status"].classList.toggle("loading", mode === "loading");
  bsigEl["bsig-status"].classList.toggle("error", mode === "error");
}

function setBanyanSigmaLoader(visible) {
  bsigEl["bsig-plot-loader"].classList.toggle("is-visible", Boolean(visible));
}

function renderTable(rows, columns) {
  if (!rows.length) return `<div class="selection-empty">No rows</div>`;
  const head = columns.map(([, label]) => `<th>${htmlEscape(label)}</th>`).join("");
  const body = rows.map((row) => (
    `<tr>${columns.map(([key]) => `<td>${htmlEscape(formatCell(row[key]))}</td>`).join("")}</tr>`
  )).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function formatCell(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number") return formatNumber(value, Math.abs(value) >= 100 ? 2 : 4);
  return String(value);
}

function nullableNumber(value) {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function finite(value) {
  return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
}

function formatNumber(value, digits = 3) {
  if (!finite(value)) return "";
  return Number(value).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
    useGrouping: false,
  });
}

function formatPercent(value) {
  if (!finite(value)) return "--";
  const number = Number(value);
  const digits = number >= 10 ? 2 : number >= 1 ? 3 : 4;
  return `${formatNumber(number, digits)}%`;
}

function formatInteger(value) {
  if (!finite(value)) return "--";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function firstParam(params, ...keys) {
  for (const key of keys) {
    if (params.has(key)) return params.get(key) || "";
  }
  return "";
}

function csvCell(value, delimiter) {
  const text = formatCell(value);
  if (text.includes(delimiter) || text.includes("\n") || text.includes('"')) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function htmlEscape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function fetchJsonUrl(url) {
  const response = await fetch(url);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function plotConfig(name) {
  return {
    responsive: true,
    displaylogo: false,
    toImageButtonOptions: { filename: name, format: "png", scale: 2 },
  };
}

function debounce(fn, wait) {
  let timeout = null;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), wait);
  };
}
