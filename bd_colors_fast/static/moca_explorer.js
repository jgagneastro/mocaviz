const mexDefaultAids = ["ABDMG", "BPMG", "TWA", "THA"];
const mexDefaultMtids = ["BF", "HM", "CM"];
const mexPalette = [
  "#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00",
  "#56b4e9", "#6b5b95", "#8a7f2d", "#b54a4a", "#3d7f6f",
  "#6f63a8", "#b05f20", "#3b7a57", "#8f3f71", "#4f6f9f",
  "#947200", "#a24b3c", "#2f6f73", "#6c5b7b", "#b06b2f",
];

const mexViewSpecs = {
  cmd: { label: "CMD", type: "cmd" },
  xyz: { label: "XYZ", type: "3d", axes: ["x", "y", "z"], title: "Galactic XYZ coordinates" },
  uvw: { label: "UVW", type: "3d", axes: ["u", "v", "w"], title: "Galactic UVW velocities" },
  projections: { label: "XYZUVW projections", type: "projections", title: "XYZUVW projections" },
  prot: { label: "Rotation", type: "science", xDefault: "br", y: "prot_days", sequenceKey: "prot", title: "Rotation periods", yTitle: "Rotation period (days)", yRange: [0.1, 25] },
  gaiaAct: { label: "Gaia Act", type: "science", xDefault: "br", y: "gaia_act", sequenceKey: "gaiaAct", title: "Gaia DR3 activity index", yTitle: "Gaia DR3 activity index", yRange: [-0.05, 0.2], yLogRange: [0.001, 0.2] },
  ewha: { label: "H-alpha", type: "science", xDefault: "br", y: "ewha", sequenceKey: "ewha", title: "H-alpha equivalent widths", yTitle: "H-alpha EW in emission (A)", yRange: [-5, 15], yTransform: (value) => -Number(value) },
  ewli: { label: "Lithium", type: "science", xDefault: "br", y: "ewli", sequenceKey: "ewli", title: "Lithium equivalent widths", yTitle: "Lithium EW (mA)", yRange: [-100, 750], yLogRange: [0.001, 750] },
};

const mexProjectionPanels = [
  { key: "xy", axes: ["x", "y"], title: "XY" },
  { key: "yz", axes: ["y", "z"], title: "YZ" },
  { key: "uv", axes: ["u", "v"], title: "UV" },
  { key: "uw", axes: ["u", "w"], title: "UW" },
];

const mexExportColumns = [
  "row_type", "designation", "moca_aid", "moca_mtid", "spt", "moca_oid",
  "gmag", "bmag", "rmag", "plx", "dmod", "dr3_ruwe", "gr", "br", "m_g",
  "x", "y", "z", "u", "v", "w", "x_opt", "y_opt", "z_opt", "u_opt",
  "v_opt", "w_opt", "prot_days", "gaia_act", "ewli", "ewha", "report_url",
];
const mexNumericExportColumns = new Set(mexExportColumns.filter((column) => !["row_type", "designation", "moca_aid", "moca_mtid", "spt", "report_url"].includes(column)));

const mexEl = {};
const mexState = {
  options: null,
  selectedAids: [],
  selectedMtids: [],
  selectedHighlightObjects: [],
  payload: null,
  members: [],
  objects: [],
  rows: [],
  selectedOids: new Set(),
  activeView: "cmd",
  aidSearchTimer: null,
  objectSearchTimer: null,
  loadToken: 0,
  suppressDeselectUntil: 0,
  pending3dSelectionTimer: null,
};

document.addEventListener("DOMContentLoaded", initMocaExplorer);

const mexAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function mexAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), mexAppBaseUrl).toString();
}

async function initMocaExplorer() {
  collectMocaExplorerElements();
  bindMocaExplorerControls();
  await loadMocaExplorerOptions();
  readMocaExplorerUrlState();
  renderMocaExplorerSelections();
  await loadMocaExplorerData();
}

function collectMocaExplorerElements() {
  [
    "mex-status", "mex-aids-default", "mex-aids-clear", "mex-aid-search",
    "mex-aid-results", "mex-selected-aids", "mex-mtid-list",
    "mex-object-search", "mex-object-results", "mex-selected-objects",
    "mex-highlight-oids", "mex-hover", "mex-cmd-field", "mex-cmd-sequences",
    "mex-cmd-br", "mex-models", "mex-assmem", "mex-asscen",
    "mex-science-sequences", "mex-science-log", "mex-science-br",
    "mex-max-objects", "mex-load", "mex-viewbar", "mex-plot",
    "mex-plot-loader", "mex-summary", "mex-subtitle", "mex-clear-selection",
    "mex-export-csv", "mex-export-tsv", "mex-export-fits",
    "mex-export-votable", "mex-table-title", "mex-table-subtitle",
    "mex-table", "mex-clear-cache-bottom", "mex-clear-cache-status",
  ].forEach((id) => {
    mexEl[id] = document.getElementById(id);
  });
}

function bindMocaExplorerControls() {
  mexEl["mex-load"].addEventListener("click", () => loadMocaExplorerData());
  mexEl["mex-aids-default"].addEventListener("click", () => {
    mexState.selectedAids = defaultAids();
    renderMocaExplorerSelections();
    loadMocaExplorerData();
  });
  mexEl["mex-aids-clear"].addEventListener("click", () => {
    mexState.selectedAids = [];
    renderMocaExplorerSelections();
    loadMocaExplorerData();
  });
  mexEl["mex-aid-search"].addEventListener("input", () => scheduleMocaExplorerAssociationSearch());
  mexEl["mex-object-search"].addEventListener("input", () => scheduleMocaExplorerObjectSearch());
  mexEl["mex-highlight-oids"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadMocaExplorerData();
  });
  mexEl["mex-highlight-oids"].addEventListener("change", () => loadMocaExplorerData());
  mexEl["mex-max-objects"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadMocaExplorerData();
  });
  mexEl["mex-max-objects"].addEventListener("change", () => loadMocaExplorerData());
  for (const id of [
    "mex-hover", "mex-cmd-field", "mex-cmd-sequences", "mex-cmd-br",
    "mex-models", "mex-assmem", "mex-asscen", "mex-science-sequences",
    "mex-science-log", "mex-science-br",
  ]) {
    mexEl[id].addEventListener("change", () => renderMocaExplorerPlot());
  }
  mexEl["mex-viewbar"].querySelectorAll("button[data-view]").forEach((button) => {
    button.addEventListener("click", () => setMocaExplorerView(button.dataset.view));
  });
  mexEl["mex-clear-selection"].addEventListener("click", () => clearMocaExplorerSelection());
  mexEl["mex-export-csv"].addEventListener("click", () => exportMocaExplorer("csv"));
  mexEl["mex-export-tsv"].addEventListener("click", () => exportMocaExplorer("tsv"));
  mexEl["mex-export-fits"].addEventListener("click", () => exportMocaExplorer("fits"));
  mexEl["mex-export-votable"].addEventListener("click", () => exportMocaExplorer("votable"));
  mexEl["mex-clear-cache-bottom"].addEventListener("click", () => clearMocaExplorerCache());
  window.addEventListener("resize", debounce(() => {
    if (mexEl["mex-plot"] && mexState.payload) Plotly.Plots.resize(mexEl["mex-plot"]);
  }, 150));
}

async function loadMocaExplorerOptions() {
  const params = connectionParams();
  try {
    const payload = await fetchJsonUrl(mexAppUrl(`api/moca-explorer/options?${params.toString()}`));
    mexState.options = payload;
  } catch (error) {
    mexState.options = {
      associations: defaultAids().map((aid) => ({ value: aid, label: aid })),
      mtids: mexDefaultMtids.map((mtid) => ({ value: mtid, label: mtid })),
      meta: { default: { aids: mexDefaultAids, mtids: mexDefaultMtids } },
    };
    setMocaExplorerStatus(`Options unavailable: ${error.message}`, "error");
  }
  renderMocaExplorerMtidList();
}

function readMocaExplorerUrlState() {
  const params = new URLSearchParams(window.location.search);
  const first = (...keys) => {
    for (const key of keys) {
      if (params.has(key)) return params.get(key) || "";
    }
    return "";
  };
  const aids = parseCsv(first("asso", "association", "moca_aid", "aid"));
  mexState.selectedAids = aids.length ? aids : defaultAids();
  const mtids = parseCsv(first("mtid", "moca_mtid"));
  mexState.selectedMtids = mtids.length ? mtids : defaultMtids();
  const oids = parseOidList(first("oid", "oids", "moca_oid", "moca_oids"));
  mexState.selectedHighlightObjects = oids.map((oid) => ({
    value: oid,
    moca_oid: oid,
    designation: `oid${oid}`,
    label: `oid${oid}`,
  }));
  mexEl["mex-highlight-oids"].value = oids.join(",");
  const maxObjects = first("max_objects", "limit");
  if (maxObjects) mexEl["mex-max-objects"].value = maxObjects;
}

function defaultAids() {
  return [...(mexState.options?.meta?.default?.aids || mexDefaultAids)];
}

function defaultMtids() {
  return [...(mexState.options?.meta?.default?.mtids || mexDefaultMtids)];
}

function renderMocaExplorerMtidList() {
  const mtids = mexState.options?.mtids?.length
    ? mexState.options.mtids
    : mexDefaultMtids.map((mtid) => ({ value: mtid, label: mtid }));
  mexEl["mex-mtid-list"].innerHTML = mtids.map((row) => {
    const value = htmlEscape(row.value || "");
    const label = htmlEscape(row.label || row.value || "");
    return `<label class="checkline"><input type="checkbox" value="${value}" data-mtid="${value}"><span>${label}</span></label>`;
  }).join("");
  mexEl["mex-mtid-list"].querySelectorAll("input[data-mtid]").forEach((input) => {
    input.checked = mexState.selectedMtids.includes(input.value);
    input.addEventListener("change", () => {
      mexState.selectedMtids = Array.from(mexEl["mex-mtid-list"].querySelectorAll("input[data-mtid]:checked")).map((item) => item.value);
      updateMocaExplorerUrl();
      loadMocaExplorerData();
    });
  });
}

function renderMocaExplorerSelections() {
  renderMocaExplorerAidChips();
  renderMocaExplorerObjectChips();
  renderMocaExplorerMtidList();
  updateMocaExplorerUrl();
}

function renderMocaExplorerAidChips() {
  mexEl["mex-selected-aids"].innerHTML = mexState.selectedAids.map((aid) => (
    `<span class="designation-chip"><span>${htmlEscape(aid)}</span><button type="button" data-aid="${htmlEscape(aid)}" aria-label="Remove ${htmlEscape(aid)}">x</button></span>`
  )).join("");
  mexEl["mex-selected-aids"].querySelectorAll("button[data-aid]").forEach((button) => {
    button.addEventListener("click", () => {
      mexState.selectedAids = mexState.selectedAids.filter((aid) => aid !== button.dataset.aid);
      renderMocaExplorerSelections();
      loadMocaExplorerData();
    });
  });
}

function renderMocaExplorerObjectChips() {
  mexState.selectedHighlightObjects = mexState.selectedHighlightObjects.filter((row) => coerceMocaOid(row.moca_oid ?? row.value) !== null);
  mexEl["mex-selected-objects"].innerHTML = mexState.selectedHighlightObjects.map((row) => {
    const oid = coerceMocaOid(row.moca_oid ?? row.value);
    const label = row.label || row.designation || `oid${oid}`;
    return `<span class="designation-chip"><span>${htmlEscape(label)}</span><button type="button" data-oid="${oid}" aria-label="Remove oid${oid}">x</button></span>`;
  }).join("");
  mexEl["mex-selected-objects"].querySelectorAll("button[data-oid]").forEach((button) => {
    button.addEventListener("click", () => {
      const oid = coerceMocaOid(button.dataset.oid);
      mexState.selectedHighlightObjects = mexState.selectedHighlightObjects.filter((row) => coerceMocaOid(row.moca_oid ?? row.value) !== oid);
      mexEl["mex-highlight-oids"].value = mexState.selectedHighlightObjects
        .map((row) => coerceMocaOid(row.moca_oid ?? row.value))
        .filter((value) => value !== null)
        .join(",");
      renderMocaExplorerSelections();
      loadMocaExplorerData();
    });
  });
}

function syncDirectOidInput() {
  const existing = parseOidList(mexEl["mex-highlight-oids"].value);
  const selected = mexState.selectedHighlightObjects
    .map((row) => coerceMocaOid(row.moca_oid ?? row.value))
    .filter((oid) => oid !== null);
  mexEl["mex-highlight-oids"].value = uniqueNumbers([...existing, ...selected]).join(",");
}

function scheduleMocaExplorerAssociationSearch() {
  clearTimeout(mexState.aidSearchTimer);
  mexState.aidSearchTimer = setTimeout(() => runMocaExplorerAssociationSearch(), 180);
}

async function runMocaExplorerAssociationSearch() {
  const query = mexEl["mex-aid-search"].value.trim();
  if (!query) {
    mexEl["mex-aid-results"].hidden = true;
    mexEl["mex-aid-results"].innerHTML = "";
    return;
  }
  const params = connectionParams();
  params.set("q", query);
  try {
    const payload = await fetchJsonUrl(mexAppUrl(`api/moca-explorer/associations/search?${params.toString()}`));
    const options = payload.options || [];
    mexEl["mex-aid-results"].innerHTML = options.length
      ? options.map((row) => `<button type="button" class="designation-result" data-aid="${htmlEscape(row.value)}">${htmlEscape(row.label || row.value)}</button>`).join("")
      : `<div class="designation-result-note">No matches</div>`;
    mexEl["mex-aid-results"].hidden = false;
    mexEl["mex-aid-results"].querySelectorAll("button[data-aid]").forEach((button) => {
      button.addEventListener("click", () => {
        const aid = button.dataset.aid;
        if (aid && !mexState.selectedAids.includes(aid)) mexState.selectedAids.push(aid);
        mexEl["mex-aid-search"].value = "";
        mexEl["mex-aid-results"].hidden = true;
        renderMocaExplorerSelections();
        loadMocaExplorerData();
      });
    });
  } catch (error) {
    mexEl["mex-aid-results"].innerHTML = `<div class="designation-result-note">${htmlEscape(error.message)}</div>`;
    mexEl["mex-aid-results"].hidden = false;
  }
}

function scheduleMocaExplorerObjectSearch() {
  clearTimeout(mexState.objectSearchTimer);
  mexState.objectSearchTimer = setTimeout(() => runMocaExplorerObjectSearch(), 180);
}

async function runMocaExplorerObjectSearch() {
  const query = mexEl["mex-object-search"].value.trim();
  if (!query) {
    mexEl["mex-object-results"].hidden = true;
    mexEl["mex-object-results"].innerHTML = "";
    return;
  }
  const params = connectionParams();
  params.set("q", query);
  try {
    const payload = await fetchJsonUrl(mexAppUrl(`api/moca-explorer/search?${params.toString()}`));
    const options = payload.options || [];
    const validOptions = options
      .map((row) => ({ ...row, _oid: coerceMocaOid(row.moca_oid ?? row.value) }))
      .filter((row) => row._oid !== null);
    mexEl["mex-object-results"].innerHTML = validOptions.length
      ? validOptions.map((row) => `<button type="button" class="designation-result" data-oid="${row._oid}" data-label="${htmlEscape(row.label || row.designation || "")}">${htmlEscape(row.label || row.designation || `oid${row._oid}`)}</button>`).join("")
      : `<div class="designation-result-note">No matches</div>`;
    mexEl["mex-object-results"].hidden = false;
    mexEl["mex-object-results"].querySelectorAll("button[data-oid]").forEach((button) => {
      button.addEventListener("click", () => {
        const oid = coerceMocaOid(button.dataset.oid);
        if (oid !== null && !mexState.selectedHighlightObjects.some((row) => coerceMocaOid(row.moca_oid ?? row.value) === oid)) {
          mexState.selectedHighlightObjects.push({ value: oid, moca_oid: oid, label: button.dataset.label || `oid${oid}` });
        }
        syncDirectOidInput();
        mexEl["mex-object-search"].value = "";
        mexEl["mex-object-results"].hidden = true;
        renderMocaExplorerSelections();
        loadMocaExplorerData();
      });
    });
  } catch (error) {
    mexEl["mex-object-results"].innerHTML = `<div class="designation-result-note">${htmlEscape(error.message)}</div>`;
    mexEl["mex-object-results"].hidden = false;
  }
}

async function loadMocaExplorerData() {
  const token = ++mexState.loadToken;
  setMocaExplorerLoading(true);
  setMocaExplorerStatus("Loading MOCA Explorer", "loading");
  const params = dataParams();
  try {
    const payload = await fetchJsonUrl(mexAppUrl(`api/moca-explorer/data?${params.toString()}`));
    if (token !== mexState.loadToken) return;
    if (!payload.ok) throw new Error(payload.error || "MOCAdb query failed");
    mexState.payload = payload;
    mexState.members = (payload.members || []).map((row, index) => enrichMocaExplorerRow(row, "member", index));
    mexState.objects = (payload.objects || []).map((row, index) => enrichMocaExplorerRow(row, "highlight", mexState.members.length + index));
    mexState.rows = [...mexState.members, ...mexState.objects];
    pruneSelectionToLoadedRows();
    renderMocaExplorerPlot();
    renderMocaExplorerTable();
    setMocaExplorerExportDisabled(mexState.rows.length === 0);
    updateMocaExplorerSummary();
    updateMocaExplorerUrl();
    setMocaExplorerStatus(`${payload.source || "MOCAdb"}: ${mexState.members.length.toLocaleString()} members`, "");
  } catch (error) {
    if (token !== mexState.loadToken) return;
    mexState.payload = null;
    mexState.members = [];
    mexState.objects = [];
    mexState.rows = [];
    setMocaExplorerExportDisabled(true);
    renderMocaExplorerEmptyPlot(error.message);
    renderMocaExplorerTable();
    setMocaExplorerStatus(error.message, "error");
  } finally {
    if (token === mexState.loadToken) setMocaExplorerLoading(false);
  }
}

function dataParams() {
  const params = connectionParams();
  if (mexState.selectedAids.length) params.set("asso", mexState.selectedAids.join(","));
  if (mexState.selectedMtids.length) params.set("mtid", mexState.selectedMtids.join(","));
  const oids = selectedHighlightOids();
  if (oids.length) params.set("oid", oids.join(","));
  const maxObjects = Number(mexEl["mex-max-objects"].value);
  if (Number.isFinite(maxObjects) && maxObjects > 0) params.set("max_objects", String(Math.floor(maxObjects)));
  return params;
}

function connectionParams() {
  const current = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "port", "user", "pwd", "dbase", "db", "database", "mock"]) {
    if (current.has(key)) params.set(key, current.get(key) || "");
  }
  return params;
}

function updateMocaExplorerUrl() {
  const params = new URLSearchParams(window.location.search);
  for (const key of ["asso", "moca_aid", "aid", "mtid", "moca_mtid", "oid", "oids", "moca_oid", "moca_oids", "max_objects", "limit"]) {
    params.delete(key);
  }
  if (mexState.selectedAids.length) params.set("asso", mexState.selectedAids.join(","));
  if (mexState.selectedMtids.length) params.set("mtid", mexState.selectedMtids.join(","));
  const oids = selectedHighlightOids();
  if (oids.length) params.set("oid", oids.join(","));
  const maxObjects = Number(mexEl["mex-max-objects"].value);
  if (Number.isFinite(maxObjects) && maxObjects > 0) params.set("max_objects", String(Math.floor(maxObjects)));
  const next = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ""}${window.location.hash}`;
  window.history.replaceState({}, "", next);
}

function selectedHighlightOids() {
  return uniqueNumbers([
    ...parseOidList(mexEl["mex-highlight-oids"].value),
    ...mexState.selectedHighlightObjects
      .map((row) => coerceMocaOid(row.moca_oid ?? row.value))
      .filter((oid) => oid !== null),
  ]);
}

function enrichMocaExplorerRow(row, rowType, index) {
  const oid = coerceMocaOid(row.moca_oid);
  return {
    ...row,
    row_type: rowType,
    _plotIndex: index,
    _oid: oid,
    _reportUrl: row.report_url || (oid !== null ? `https://mocadb.ca/search/results?search-query=oid%28${oid}%29&search-type=star` : null),
  };
}

function setMocaExplorerView(view) {
  if (!mexViewSpecs[view]) return;
  mexState.activeView = view;
  mexEl["mex-viewbar"].querySelectorAll("button[data-view]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === view);
  });
  renderMocaExplorerPlot();
}

function renderMocaExplorerPlot() {
  if (!mexState.payload) {
    renderMocaExplorerEmptyPlot("No data loaded");
    return;
  }
  const spec = mexViewSpecs[mexState.activeView] || mexViewSpecs.cmd;
  let plot;
  if (spec.type === "cmd") plot = buildMocaExplorerCmdPlot();
  else if (spec.type === "3d") plot = buildMocaExplorer3dPlot(spec);
  else if (spec.type === "projections") plot = buildMocaExplorerProjectionPlot(spec);
  else if (spec.type === "2d") plot = buildMocaExplorer2dPlot(spec);
  else plot = buildMocaExplorerSciencePlot(spec);
  clearTimeout(mexState.pending3dSelectionTimer);
  clearPlotSelectionEventListeners();
  mexState.suppressDeselectUntil = performance.now() + 600;
  Plotly.react(mexEl["mex-plot"], plot.traces, plot.layout, plotConfig(`moca_explorer_${mexState.activeView}`));
  bindPlotSelectionEvents();
  updateMocaExplorerSummary();
}

function clearPlotSelectionEventListeners() {
  const plot = mexEl["mex-plot"];
  plot.removeAllListeners?.("plotly_selected");
  plot.removeAllListeners?.("plotly_deselect");
  plot.removeAllListeners?.("plotly_click");
}

function bindPlotSelectionEvents() {
  const plot = mexEl["mex-plot"];
  clearPlotSelectionEventListeners();
  plot.on?.("plotly_click", (event) => {
    const oids = selectedOidsFromEventPoints(event?.points || []);
    if (!oids.length) return;
    applyMocaExplorerSelection(oids.slice(0, 1), event?.event || null, "click");
  });
  plot.on?.("plotly_selected", (event) => {
    const spec = mexViewSpecs[mexState.activeView] || mexViewSpecs.cmd;
    if (spec.type === "3d") return;
    const oids = selectedOidsFromEventPoints(event?.points || []);
    applyMocaExplorerSelection(oids, event?.event || null, "range");
  });
}

function selectedOidsFromEventPoints(points) {
  const oids = [];
  for (const point of points || []) {
    const oid = coerceMocaOid(point.customdata);
    if (oid !== null) oids.push(oid);
  }
  return uniqueNumbers(oids);
}

function applyMocaExplorerSelection(oids, nativeEvent = null, mode = "range") {
  const clean = uniqueNumbers((oids || []).map(coerceMocaOid).filter((oid) => oid !== null));
  if (!clean.length) {
    if (mode === "range") clearMocaExplorerSelection();
    return;
  }
  const additive = Boolean(nativeEvent?.shiftKey || nativeEvent?.ctrlKey || nativeEvent?.metaKey);
  if (mode === "click" && additive) {
    const next = new Set(mexState.selectedOids);
    for (const oid of clean) {
      if (next.has(oid)) next.delete(oid);
      else next.add(oid);
    }
    mexState.selectedOids = next;
  } else if (additive) {
    mexState.selectedOids = new Set([...mexState.selectedOids, ...clean]);
  } else {
    mexState.selectedOids = new Set(clean);
  }
  const spec = mexViewSpecs[mexState.activeView] || mexViewSpecs.cmd;
  renderMocaExplorerSelectionChange({ defer3d: spec.type === "3d" });
}

function renderMocaExplorerSelectionChange(options = {}) {
  const spec = mexViewSpecs[mexState.activeView] || mexViewSpecs.cmd;
  if (options.defer3d && spec.type === "3d") {
    scheduleCurrent3dSelectionTraceUpdate();
  } else if (!updateCurrentPlotSelectedPoints()) {
    renderMocaExplorerPlot();
  }
  renderMocaExplorerTable();
  updateMocaExplorerSummary();
}

function updateCurrentPlotSelectedPoints() {
  const plot = mexEl["mex-plot"];
  if (!plot?.data?.length || typeof Plotly === "undefined") return false;
  const spec = mexViewSpecs[mexState.activeView] || mexViewSpecs.cmd;
  if (spec.type === "3d") return updateCurrent3dSelectionTrace(plot, spec.axes || []);
  const traceIndices = [];
  const selectedpoints = [];
  const unselectedOpacities = [];
  const selectionActive = mexState.selectedOids.size > 0;
  plot.data.forEach((trace, traceIndex) => {
    const customdata = Array.isArray(trace.customdata) ? trace.customdata : [];
    if (!customdata.length) return;
    const indices = [];
    customdata.forEach((value, pointIndex) => {
      const oid = Number(value);
      if (Number.isFinite(oid) && mexState.selectedOids.has(oid)) indices.push(pointIndex);
    });
    traceIndices.push(traceIndex);
    selectedpoints.push(selectionActive ? indices : null);
    unselectedOpacities.push(unselectedOpacityForTrace(trace, selectionActive));
  });
  if (!traceIndices.length) return false;
  mexState.suppressDeselectUntil = performance.now() + 600;
  const update = {
    selectedpoints,
    "unselected.marker.opacity": unselectedOpacities,
  };
  Plotly.restyle(plot, update, traceIndices);
  return true;
}

function unselectedOpacityForTrace(trace, selectionActive) {
  if (!selectionActive) return trace.name === "Highlighted OIDs" ? 1 : 0.82;
  return trace.name === "Highlighted OIDs" ? 1 : 0.12;
}

function scheduleCurrent3dSelectionTraceUpdate() {
  clearTimeout(mexState.pending3dSelectionTimer);
  mexState.pending3dSelectionTimer = setTimeout(() => {
    const spec = mexViewSpecs[mexState.activeView] || mexViewSpecs.cmd;
    if (spec.type !== "3d") return;
    updateCurrent3dSelectionTrace(mexEl["mex-plot"], spec.axes || []);
  }, 80);
}

function updateCurrent3dSelectionTrace(plot, axes) {
  if (!plot?.data?.length) return false;
  const traceIndex = plot.data.findIndex((trace) => trace.type === "scatter3d" && trace.name === "Selected OIDs");
  if (traceIndex < 0) return false;
  const rows = selectedRowsFor3dAxes(axes);
  mexState.suppressDeselectUntil = performance.now() + 600;
  Plotly.restyle(plot, {
    x: [rows.map((row) => axisValue(row, axes[0], mexEl["mex-assmem"].checked))],
    y: [rows.map((row) => axisValue(row, axes[1], mexEl["mex-assmem"].checked))],
    z: [rows.map((row) => axisValue(row, axes[2], mexEl["mex-assmem"].checked))],
    text: [rows.map((row) => hoverText(row))],
    customdata: [rows.map((row) => row._oid)],
  }, [traceIndex]);
  return true;
}

function buildMocaExplorerCmdPlot() {
  const traces = [];
  const useBr = mexEl["mex-cmd-br"].checked;
  const xKey = useBr ? "br" : "gr";
  const xTitle = useBr ? "Gaia DR3 G_BP - G_RP color (mag)" : "Gaia DR3 G - G_RP color (mag)";
  if (!useBr && mexEl["mex-cmd-field"].checked) addFieldScatterTrace(traces, mexState.payload.sequences?.cmdField || []);
  addGroupedMemberTraces(traces, mexState.members, xKey, "m_g", "markers");
  if (!useBr && mexEl["mex-cmd-sequences"].checked) addSequenceLineTraces(traces, mexState.payload.sequences?.cmd || []);
  addHighlightedTrace(traces, xKey, "m_g");
  const layout = base2dLayout("Gaia DR3 color-magnitude diagram", xTitle, "Gaia DR3 absolute G-band magnitude (mag)");
  layout.xaxis.range = useBr ? [-0.5, 3.5] : [-0.5, 2.5];
  layout.yaxis.range = [20, -2];
  addSptTopAxis(layout, useBr ? "sptn_bprp_gaiaedr3_field" : "sptn_grp_gaiaedr3_field", layout.xaxis.range);
  return { traces, layout };
}

function buildMocaExplorer2dPlot(spec) {
  const traces = [];
  const [xAxis, yAxis] = spec.axes;
  const assume = mexEl["mex-assmem"].checked;
  addGroupedMemberTraces(traces, mexState.members, xAxis, yAxis, "markers", assume);
  if (mexEl["mex-models"].checked) add2dModelTraces(traces, xAxis, yAxis);
  addHighlightedTrace(traces, xAxis, yAxis);
  addSunTrace2d(traces, xAxis, yAxis);
  const layout = base2dLayout(spec.title, axisTitle(xAxis), axisTitle(yAxis));
  layout.xaxis.range = defaultRangeForAxis(xAxis);
  layout.yaxis.range = defaultRangeForAxis(yAxis);
  return { traces, layout };
}

function buildMocaExplorerProjectionPlot(spec) {
  const traces = [];
  const assume = mexEl["mex-assmem"].checked;
  mexProjectionPanels.forEach((panel, index) => {
    const [xAxis, yAxis] = panel.axes;
    const traceOptions = {
      axisRefs: subplotAxisRefs(index),
      legendSuffix: panel.key,
      showMemberLegend: index === 0,
      showObjectLegend: index === 0,
      showSunLegend: index === 0,
    };
    addGroupedMemberTraces(traces, mexState.members, xAxis, yAxis, "markers", assume, traceOptions);
    if (mexEl["mex-models"].checked) add2dModelTraces(traces, xAxis, yAxis, traceOptions);
    addHighlightedTrace(traces, xAxis, yAxis, traceOptions);
    addSunTrace2d(traces, xAxis, yAxis, traceOptions);
  });

  const layout = {
    title: { text: spec.title, font: { size: 16 } },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    clickmode: "event",
    dragmode: "lasso",
    uirevision: "moca-explorer-projections",
    hovermode: "closest",
    margin: { l: 70, r: 34, t: 78, b: 58 },
    legend: { orientation: "h", x: 0, y: -0.08, yanchor: "top" },
    annotations: [
      ...watermarkAnnotations("right"),
      ...mexProjectionPanels.map((panel, index) => ({
        text: panel.title,
        x: subplotTitleX(index),
        y: subplotTitleY(index),
        xref: "paper",
        yref: "paper",
        showarrow: false,
        font: { size: 13, color: "#252329" },
      })),
    ],
  };
  mexProjectionPanels.forEach((panel, index) => {
    const [xAxis, yAxis] = panel.axes;
    const xLayoutKey = index === 0 ? "xaxis" : `xaxis${index + 1}`;
    const yLayoutKey = index === 0 ? "yaxis" : `yaxis${index + 1}`;
    layout[xLayoutKey] = {
      title: axisTitle(xAxis),
      range: defaultRangeForAxis(xAxis),
      domain: subplotXDomain(index),
      zeroline: false,
      anchor: index === 0 ? "y" : `y${index + 1}`,
    };
    layout[yLayoutKey] = {
      title: axisTitle(yAxis),
      range: defaultRangeForAxis(yAxis),
      domain: subplotYDomain(index),
      zeroline: false,
      anchor: index === 0 ? "x" : `x${index + 1}`,
    };
  });
  return { traces, layout };
}

function buildMocaExplorer3dPlot(spec) {
  const traces = [];
  const axes = spec.axes;
  const assume = mexEl["mex-assmem"].checked;
  if (mexEl["mex-asscen"].checked) addAssociationLabelTrace3d(traces, axes);
  addGroupedMemberTraces3d(traces, mexState.members, axes, assume);
  if (mexEl["mex-models"].checked) add3dModelWireTraces(traces, axes);
  addHighlightedTrace3d(traces, axes);
  addSunTrace3d(traces, axes);
  addSelectedTrace3d(traces, axes);
  const layout = {
    title: { text: spec.title, font: { size: 16 } },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    clickmode: "event",
    margin: { l: 0, r: 0, t: 42, b: 0 },
    uirevision: "moca-explorer",
    hovermode: "closest",
    legend: { orientation: "h", x: 0, y: -0.02, yanchor: "top" },
    scene: {
      xaxis: { title: axisTitle(axes[0]), range: defaultRangeForAxis(axes[0]) },
      yaxis: { title: axisTitle(axes[1]), range: defaultRangeForAxis(axes[1]) },
      zaxis: { title: axisTitle(axes[2]), range: defaultRangeForAxis(axes[2]) },
      aspectmode: "cube",
    },
    annotations: watermarkAnnotations("left"),
  };
  return { traces, layout };
}

function buildMocaExplorerSciencePlot(spec) {
  const traces = [];
  const xKey = mexEl["mex-science-br"].checked ? "br" : "gr";
  const xTitle = mexEl["mex-science-br"].checked ? "Gaia DR3 G_BP - G_RP color (mag)" : "Gaia DR3 G - G_RP color (mag)";
  addGroupedScienceTraces(traces, mexState.members, xKey, spec);
  if (mexEl["mex-science-sequences"].checked && mexEl["mex-science-br"].checked) {
    addSequenceLineTraces(traces, mexState.payload.sequences?.[spec.sequenceKey] || [], spec.yTransform);
  }
  addHighlightedScienceTrace(traces, xKey, spec);
  const layout = base2dLayout(spec.title, xTitle, spec.yTitle);
  layout.xaxis.range = mexEl["mex-science-br"].checked ? [0.2, spec.sequenceKey === "ewli" ? 4.0 : 3.2] : [0.2, spec.sequenceKey === "ewli" ? 2.5 : 1.5];
  const logY = mexEl["mex-science-log"].checked;
  if (logY) {
    const range = spec.yLogRange || [Math.max(0.001, spec.yRange[0]), spec.yRange[1]];
    layout.yaxis.type = "log";
    layout.yaxis.range = [Math.log10(range[0]), Math.log10(range[1])];
  } else {
    layout.yaxis.range = spec.yRange;
  }
  return { traces, layout };
}

function addGroupedMemberTraces(traces, rows, xKey, yKey, mode = "markers", assume = false, traceOptions = {}) {
  for (const aid of associationOrder(rows)) {
    const subset = rows.filter((row) => row.moca_aid === aid && finite(axisValue(row, xKey, assume)) && finite(axisValue(row, yKey, assume)));
    if (!subset.length) continue;
    traces.push(scatterTraceForRows(subset, aid, xKey, yKey, colorForAssociation(aid), mode, assume, {
      ...traceOptions,
      legendgroup: `members-${aid}`,
      showlegend: traceOptions.showMemberLegend,
    }));
  }
}

function scatterTraceForRows(rows, name, xKey, yKey, color, mode, assume = false, traceOptions = {}) {
  const selectedpoints = selectedPointIndices(rows);
  return {
    type: "scattergl",
    mode,
    name,
    ...(traceOptions.axisRefs || {}),
    legendgroup: traceOptions.legendgroup,
    showlegend: traceOptions.showlegend,
    x: rows.map((row) => axisValue(row, xKey, assume)),
    y: rows.map((row) => axisValue(row, yKey, assume)),
    text: rows.map((row) => hoverText(row)),
    customdata: rows.map((row) => row._oid),
    hovertemplate: mexEl["mex-hover"].checked ? "%{text}<extra></extra>" : undefined,
    hoverinfo: mexEl["mex-hover"].checked ? undefined : "none",
    selectedpoints,
    marker: { color, size: 6, opacity: 0.82 },
    selected: { marker: { opacity: 1, size: 8 } },
    unselected: { marker: { opacity: mexState.selectedOids.size ? 0.12 : 0.82 } },
  };
}

function addGroupedMemberTraces3d(traces, rows, axes, assume = false) {
  for (const aid of associationOrder(rows)) {
    const subset = rows.filter((row) => axes.every((axis) => finite(axisValue(row, axis, assume))));
    const aidRows = subset.filter((row) => row.moca_aid === aid);
    if (!aidRows.length) continue;
    traces.push({
      type: "scatter3d",
      mode: "markers",
      name: aid,
      x: aidRows.map((row) => axisValue(row, axes[0], assume)),
      y: aidRows.map((row) => axisValue(row, axes[1], assume)),
      z: aidRows.map((row) => axisValue(row, axes[2], assume)),
      text: aidRows.map((row) => hoverText(row)),
      customdata: aidRows.map((row) => row._oid),
      hovertemplate: mexEl["mex-hover"].checked ? "%{text}<extra></extra>" : undefined,
      hoverinfo: mexEl["mex-hover"].checked ? undefined : "none",
      marker: { color: colorForAssociation(aid), size: 2.7, opacity: 0.42 },
    });
  }
}

function addGroupedScienceTraces(traces, rows, xKey, spec) {
  for (const aid of associationOrder(rows)) {
    const subset = rows.filter((row) => row.moca_aid === aid && finite(row[xKey]) && scienceY(row, spec) !== null);
    if (!subset.length) continue;
    const selectedpoints = selectedPointIndices(subset);
    traces.push({
      type: "scatter",
      mode: "markers",
      name: aid,
      x: subset.map((row) => row[xKey]),
      y: subset.map((row) => scienceY(row, spec)),
      text: subset.map((row) => hoverText(row)),
      customdata: subset.map((row) => row._oid),
      hovertemplate: mexEl["mex-hover"].checked ? "%{text}<extra></extra>" : undefined,
      hoverinfo: mexEl["mex-hover"].checked ? undefined : "none",
      selectedpoints,
      marker: { color: colorForAssociation(aid), size: 6, opacity: 0.82 },
      selected: { marker: { opacity: 1, size: 8 } },
      unselected: { marker: { opacity: mexState.selectedOids.size ? 0.12 : 0.82 } },
    });
  }
}

function addHighlightedTrace(traces, xKey, yKey, traceOptions = {}) {
  const rows = mexState.objects.filter((row) => finite(axisValue(row, xKey, false)) && finite(axisValue(row, yKey, false)));
  if (!rows.length) return;
  traces.push({
    type: "scattergl",
    mode: "markers",
    name: "Highlighted OIDs",
    ...(traceOptions.axisRefs || {}),
    legendgroup: "highlighted-oids",
    showlegend: traceOptions.showObjectLegend,
    x: rows.map((row) => axisValue(row, xKey, false)),
    y: rows.map((row) => axisValue(row, yKey, false)),
    text: rows.map((row) => hoverText(row)),
    customdata: rows.map((row) => row._oid),
    hovertemplate: mexEl["mex-hover"].checked ? "%{text}<extra></extra>" : undefined,
    hoverinfo: mexEl["mex-hover"].checked ? undefined : "none",
    selectedpoints: selectedPointIndices(rows),
    marker: { color: "#ffd23f", size: 24, symbol: "star", line: { width: 3.2, color: "#111111" } },
    selected: { marker: { opacity: 1, size: 28 } },
    unselected: { marker: { opacity: 1 } },
  });
}

function addHighlightedTrace3d(traces, axes) {
  const rows = mexState.objects.filter((row) => axes.every((axis) => finite(axisValue(row, axis, false))));
  if (!rows.length) return;
  traces.push({
    type: "scatter3d",
    mode: "markers",
    name: "Highlighted OIDs",
    x: rows.map((row) => axisValue(row, axes[0], false)),
    y: rows.map((row) => axisValue(row, axes[1], false)),
    z: rows.map((row) => axisValue(row, axes[2], false)),
    text: rows.map((row) => hoverText(row)),
    customdata: rows.map((row) => row._oid),
    hovertemplate: mexEl["mex-hover"].checked ? "%{text}<extra></extra>" : undefined,
    hoverinfo: mexEl["mex-hover"].checked ? undefined : "none",
    marker: {
      color: "#ffd23f",
      size: 15,
      opacity: 1,
      symbol: "cross",
      line: { width: 3.5, color: "#111111" },
    },
  });
}

function addSelectedTrace3d(traces, axes) {
  const rows = selectedRowsFor3dAxes(axes);
  traces.push({
    type: "scatter3d",
    mode: "markers",
    name: "Selected OIDs",
    showlegend: false,
    x: rows.map((row) => axisValue(row, axes[0], mexEl["mex-assmem"].checked)),
    y: rows.map((row) => axisValue(row, axes[1], mexEl["mex-assmem"].checked)),
    z: rows.map((row) => axisValue(row, axes[2], mexEl["mex-assmem"].checked)),
    text: rows.map((row) => hoverText(row)),
    customdata: rows.map((row) => row._oid),
    hovertemplate: mexEl["mex-hover"].checked ? "%{text}<extra></extra>" : undefined,
    hoverinfo: mexEl["mex-hover"].checked ? undefined : "none",
    marker: {
      color: "#ffd23f",
      size: 17,
      symbol: "cross",
      opacity: 1,
      line: { width: 3.5, color: "#111111" },
    },
  });
}

function addHighlightedScienceTrace(traces, xKey, spec) {
  const rows = mexState.objects.filter((row) => finite(row[xKey]) && scienceY(row, spec) !== null);
  if (!rows.length) return;
  traces.push({
    type: "scatter",
    mode: "markers",
    name: "Highlighted OIDs",
    x: rows.map((row) => row[xKey]),
    y: rows.map((row) => scienceY(row, spec)),
    text: rows.map((row) => hoverText(row)),
    customdata: rows.map((row) => row._oid),
    hovertemplate: mexEl["mex-hover"].checked ? "%{text}<extra></extra>" : undefined,
    hoverinfo: mexEl["mex-hover"].checked ? undefined : "none",
    selectedpoints: selectedPointIndices(rows),
    marker: { color: "#ffd23f", size: 21, symbol: "star", line: { width: 3, color: "#111111" } },
    selected: { marker: { opacity: 1, size: 25 } },
    unselected: { marker: { opacity: 1 } },
  });
}

function addSequenceLineTraces(traces, sequences, yTransform = null) {
  for (const sequence of sequences || []) {
    traces.push({
      type: "scattergl",
      mode: "lines",
      name: sequence.tag || sequence.moca_seqid || "Sequence",
      x: sequence.x || [],
      y: (sequence.y || []).map((value) => yTransform ? yTransform(value) : value),
      line: {
        color: sequence.color || "#444444",
        width: Number(sequence.width || 2),
        dash: sequence.style || "solid",
      },
      hoverinfo: "skip",
    });
  }
}

function addFieldScatterTrace(traces, sequences) {
  for (const sequence of sequences || []) {
    traces.push({
      type: "scattergl",
      mode: "markers",
      name: sequence.tag || "Field stars",
      x: sequence.x || [],
      y: sequence.y || [],
      marker: { color: colorWithAlpha(sequence.color || "#6f7882", 0.22), size: 3 },
      hoverinfo: "skip",
      showlegend: false,
    });
  }
}

function add2dModelTraces(traces, xAxis, yAxis, traceOptions = {}) {
  for (const model of mexState.payload?.models || []) {
    const points = covarianceEllipsePoints(model, xAxis, yAxis);
    if (!points) continue;
    traces.push({
      type: "scattergl",
      mode: "lines",
      name: `${model.moca_aid} model`,
      ...(traceOptions.axisRefs || {}),
      legendgroup: `model-${model.moca_aid}`,
      x: points.x,
      y: points.y,
      line: { color: colorForAssociation(model.moca_aid), width: 1.8 },
      opacity: 0.55,
      hoverinfo: "skip",
      showlegend: false,
    });
  }
}

function add3dModelWireTraces(traces, axes) {
  for (const model of mexState.payload?.models || []) {
    const center = axes.map((axis) => Number(model[`${axis}_cen`]));
    const radius = axes.map((axis) => Math.sqrt(Math.max(0, Number(model[`${axis}${axis}_covar`] || 0))) * 1.557);
    if (!center.every(Number.isFinite) || !radius.every((value) => Number.isFinite(value) && value > 0)) continue;
    const color = colorForAssociation(model.moca_aid);
    for (const plane of [[0, 1], [0, 2], [1, 2]]) {
      const line = { x: [], y: [], z: [] };
      for (let i = 0; i <= 72; i += 1) {
        const theta = (i / 72) * Math.PI * 2;
        const values = [...center];
        values[plane[0]] += Math.cos(theta) * radius[plane[0]];
        values[plane[1]] += Math.sin(theta) * radius[plane[1]];
        line.x.push(values[0]);
        line.y.push(values[1]);
        line.z.push(values[2]);
      }
      traces.push({
        type: "scatter3d",
        mode: "lines",
        name: `${model.moca_aid} model`,
        x: line.x,
        y: line.y,
        z: line.z,
        line: { color, width: 3 },
        opacity: 0.32,
        hoverinfo: "skip",
        showlegend: false,
      });
    }
  }
}

function addAssociationLabelTrace3d(traces, axes) {
  const labels = (mexState.payload?.labels || []).filter((row) => axes.every((axis) => finite(row[axis])));
  if (!labels.length) return;
  traces.push({
    type: "scatter3d",
    mode: "text",
    name: "Association labels",
    x: labels.map((row) => row[axes[0]]),
    y: labels.map((row) => row[axes[1]]),
    z: labels.map((row) => row[axes[2]]),
    text: labels.map((row) => row.moca_aid),
    textfont: { color: "#252329", size: 11 },
    opacity: 0.42,
    hoverinfo: "skip",
  });
}

function addSunTrace2d(traces, xAxis, yAxis, traceOptions = {}) {
  traces.push({
    type: "scattergl",
    mode: "markers",
    name: "Sun",
    ...(traceOptions.axisRefs || {}),
    legendgroup: "sun",
    showlegend: traceOptions.showSunLegend,
    x: [0],
    y: [0],
    marker: { color: "#000000", size: 10, symbol: "cross" },
    text: ["Sun"],
    hovertemplate: mexEl["mex-hover"].checked ? "%{text}<extra></extra>" : undefined,
    hoverinfo: mexEl["mex-hover"].checked ? undefined : "none",
  });
}

function addSunTrace3d(traces, axes) {
  traces.push({
    type: "scatter3d",
    mode: "markers",
    name: "Sun",
    x: [0],
    y: [0],
    z: [0],
    marker: { color: "#000000", size: 5, symbol: "cross" },
    text: ["Sun"],
    hovertemplate: mexEl["mex-hover"].checked ? "%{text}<extra></extra>" : undefined,
    hoverinfo: mexEl["mex-hover"].checked ? undefined : "none",
  });
}

function base2dLayout(title, xTitle, yTitle) {
  return {
    title: { text: title, font: { size: 16 } },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    clickmode: "event",
    dragmode: "lasso",
    uirevision: `moca-explorer-${mexState.activeView}`,
    hovermode: "closest",
    margin: { l: 78, r: 28, t: 70, b: 62 },
    xaxis: { title: xTitle, zeroline: false },
    yaxis: { title: yTitle, zeroline: false },
    legend: { orientation: "h", x: 0, y: -0.22, yanchor: "top" },
    annotations: watermarkAnnotations("right"),
  };
}

function subplotAxisRefs(index) {
  if (index === 0) return {};
  return { xaxis: `x${index + 1}`, yaxis: `y${index + 1}` };
}

function subplotXDomain(index) {
  return index % 2 === 0 ? [0.06, 0.47] : [0.58, 0.99];
}

function subplotYDomain(index) {
  return index < 2 ? [0.58, 0.95] : [0.08, 0.45];
}

function subplotTitleX(index) {
  const [left, right] = subplotXDomain(index);
  return (left + right) / 2;
}

function subplotTitleY(index) {
  const [_bottom, top] = subplotYDomain(index);
  return top + 0.035;
}

function watermarkAnnotations(side) {
  return [{
    x: side === "right" ? 1 : 0,
    y: 1,
    xref: "paper",
    yref: "paper",
    text: "MOCAdb",
    showarrow: false,
    align: side,
    opacity: 0.55,
    font: { family: "Courier New, monospace", size: 15, color: "rgb(150,156,166)" },
  }];
}

function addSptTopAxis(layout, seqid, xrange) {
  const rows = (mexState.payload?.sptAxis || [])
    .filter((row) => row.moca_seqid === seqid && finite(row.xdata) && finite(row.ydata))
    .sort((a, b) => Number(a.xdata) - Number(b.xdata));
  if (rows.length < 2) return;
  const sptn = rows.map((row) => Number(row.xdata));
  const colors = rows.map((row) => Number(row.ydata));
  const minSpt = Math.ceil(Math.min(...sptn) / 5) * 5;
  const maxSpt = Math.floor(Math.max(...sptn) / 5) * 5;
  const tickSptn = [];
  for (let value = minSpt; value <= maxSpt; value += 5) tickSptn.push(value);
  const pairs = tickSptn.map((value) => [interp1d(value, sptn, colors), formatSptNumber(value)])
    .filter(([color, label]) => finite(color) && label && color >= Math.min(...xrange) && color <= Math.max(...xrange));
  if (pairs.length < 2) return;
  layout.xaxis2 = {
    title: "Field spectral type",
    overlaying: "x",
    side: "top",
    matches: "x",
    tickmode: "array",
    tickvals: pairs.map((pair) => pair[0]),
    ticktext: pairs.map((pair) => pair[1]),
    showgrid: false,
    zeroline: false,
    ticks: "outside",
    range: xrange,
  };
}

function covarianceEllipsePoints(model, xAxis, yAxis) {
  const cx = Number(model[`${xAxis}_cen`]);
  const cy = Number(model[`${yAxis}_cen`]);
  const a = Number(model[covarianceKey(xAxis, xAxis)]);
  const b = Number(model[covarianceKey(xAxis, yAxis)]);
  const d = Number(model[covarianceKey(yAxis, yAxis)]);
  if (![cx, cy, a, b, d].every(Number.isFinite)) return null;
  const trace = a + d;
  const term = Math.sqrt((a - d) * (a - d) + 4 * b * b);
  const lambda1 = Math.max(0, 0.5 * (trace + term));
  const lambda2 = Math.max(0, 0.5 * (trace - term));
  if (lambda1 <= 0 || lambda2 <= 0) return null;
  const angle = 0.5 * Math.atan2(2 * b, a - d);
  const r1 = Math.sqrt(lambda1) * 1.3605;
  const r2 = Math.sqrt(lambda2) * 1.3605;
  const xs = [];
  const ys = [];
  for (let i = 0; i <= 96; i += 1) {
    const theta = (i / 96) * Math.PI * 2;
    const x = r1 * Math.cos(theta);
    const y = r2 * Math.sin(theta);
    xs.push(cx + x * Math.cos(angle) - y * Math.sin(angle));
    ys.push(cy + x * Math.sin(angle) + y * Math.cos(angle));
  }
  return { x: xs, y: ys };
}

function covarianceKey(axis1, axis2) {
  const order = ["x", "y", "z", "u", "v", "w"];
  const [a, b] = [axis1, axis2].sort((left, right) => order.indexOf(left) - order.indexOf(right));
  return `${a}${b}_covar`;
}

function scienceY(row, spec) {
  const raw = row[spec.y];
  if (!finite(raw)) return null;
  const value = spec.yTransform ? spec.yTransform(raw) : Number(raw);
  return finite(value) ? value : null;
}

function axisValue(row, axis, assume = false) {
  if (assume && row.row_type === "member") {
    const optKey = `${axis}_opt`;
    if (finite(row[optKey])) return Number(row[optKey]);
  }
  return finite(row[axis]) ? Number(row[axis]) : null;
}

function selectedPointIndices(rows) {
  if (!mexState.selectedOids.size) return null;
  const indices = [];
  rows.forEach((row, index) => {
    if (mexState.selectedOids.has(row._oid)) indices.push(index);
  });
  return indices.length ? indices : [];
}

function selectedRowsFor3dAxes(axes) {
  if (!mexState.selectedOids.size || !axes?.length) return [];
  const assume = mexEl["mex-assmem"].checked;
  return mexState.rows.filter((row) => (
    row._oid !== null
    && mexState.selectedOids.has(row._oid)
    && axes.every((axis) => finite(axisValue(row, axis, assume)))
  ));
}

function pruneSelectionToLoadedRows() {
  if (!mexState.selectedOids.size) return;
  const loaded = new Set(mexState.rows.map((row) => row._oid).filter((oid) => oid !== null));
  mexState.selectedOids = new Set([...mexState.selectedOids].filter((oid) => loaded.has(oid)));
}

function clearMocaExplorerSelection(rerender = true) {
  mexState.selectedOids = new Set();
  if (rerender) {
    renderMocaExplorerSelectionChange();
  }
}

function renderMocaExplorerTable() {
  const rows = sortedTableRows();
  const maxRows = 900;
  const shown = rows.slice(0, maxRows);
  mexEl["mex-table-title"].textContent = mexState.selectedOids.size
    ? `${mexState.selectedOids.size.toLocaleString()} selected objects`
    : "Displayed members";
  mexEl["mex-table-subtitle"].textContent = rows.length > maxRows
    ? `Showing ${maxRows.toLocaleString()} of ${rows.length.toLocaleString()} rows.`
    : `${rows.length.toLocaleString()} rows.`;
  if (!shown.length) {
    mexEl["mex-table"].innerHTML = `<div class="selection-table">No rows loaded.</div>`;
    return;
  }
  const columns = ["designation", "moca_aid", "moca_mtid", "spt", "moca_oid", "gmag", "bmag", "rmag", "plx", "dr3_ruwe", "x", "y", "z", "u", "v", "w", "prot_days", "gaia_act", "ewli", "ewha"];
  const header = columns.map((column) => `<th>${htmlEscape(column)}</th>`).join("");
  const body = shown.map((row) => {
    const selected = mexState.selectedOids.has(row._oid);
    const cells = columns.map((column) => {
      if (column === "designation" && row._reportUrl) {
        return `<td><a class="report-link" href="${htmlEscape(row._reportUrl)}" target="_blank" rel="noopener">${htmlEscape(row.designation || row._oid || "")}</a></td>`;
      }
      return `<td>${htmlEscape(formatCell(row[column]))}</td>`;
    }).join("");
    return `<tr class="${selected ? "is-selected" : ""}">${cells}</tr>`;
  }).join("");
  mexEl["mex-table"].innerHTML = `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
}

function sortedTableRows() {
  const selected = [];
  const unselected = [];
  for (const row of mexState.rows) {
    if (mexState.selectedOids.has(row._oid)) selected.push(row);
    else unselected.push(row);
  }
  const sorter = (a, b) => (
    String(a.moca_aid || "").localeCompare(String(b.moca_aid || ""))
    || mtidRank(a.moca_mtid) - mtidRank(b.moca_mtid)
    || String(a.spt || "").localeCompare(String(b.spt || ""))
    || Number(a.moca_oid || 0) - Number(b.moca_oid || 0)
  );
  selected.sort(sorter);
  unselected.sort(sorter);
  return [...selected, ...unselected];
}

function mtidRank(value) {
  const order = ["BF", "HM", "CM", "LM", "AM", "R"];
  const index = order.indexOf(String(value || ""));
  return index >= 0 ? index : 99;
}

function updateMocaExplorerSummary() {
  const payload = mexState.payload;
  if (!payload) {
    mexEl["mex-summary"].textContent = "No data loaded";
    mexEl["mex-subtitle"].textContent = "Selection: none";
    mexEl["mex-clear-selection"].disabled = true;
    return;
  }
  const meta = payload.meta || {};
  const cache = payload.cache?.hit ? "cache hit" : "fresh query";
  const truncated = meta.truncated ? ", truncated" : "";
  mexEl["mex-summary"].textContent = `${(meta.member_count || 0).toLocaleString()} members, ${(meta.object_count || 0).toLocaleString()} highlighted OIDs, ${(meta.model_count || 0).toLocaleString()} model rows (${cache}${truncated})`;
  mexEl["mex-subtitle"].textContent = mexState.selectedOids.size
    ? `Selection: ${mexState.selectedOids.size.toLocaleString()} object(s)`
    : "Selection: none";
  mexEl["mex-clear-selection"].disabled = mexState.selectedOids.size === 0;
}

function renderMocaExplorerEmptyPlot(message) {
  const layout = base2dLayout("MOCA Explorer", "", "");
  layout.annotations = [{
    text: htmlEscape(message || "No data loaded"),
    x: 0.5,
    y: 0.5,
    xref: "paper",
    yref: "paper",
    showarrow: false,
    font: { size: 16, color: "#5f5864" },
  }];
  clearPlotSelectionEventListeners();
  Plotly.react(mexEl["mex-plot"], [], layout, plotConfig("moca_explorer_empty"));
}

function exportMocaExplorer(format) {
  if (!window.MocaExport || !mexState.rows.length) return;
  MocaExport.saveTable(format, {
    rows: mexState.rows,
    columns: mexExportColumns,
    numericColumns: mexNumericExportColumns,
    filenameBase: "moca_explorer_rows",
    tableName: "moca_explorer_rows",
    resourceName: "MOCAdb Explorer rows",
    extName: "MOCA_EXPLORER",
  });
}

function setMocaExplorerExportDisabled(disabled) {
  for (const id of ["mex-export-csv", "mex-export-tsv", "mex-export-fits", "mex-export-votable"]) {
    if (mexEl[id]) mexEl[id].disabled = disabled;
  }
}

async function clearMocaExplorerCache() {
  mexEl["mex-clear-cache-bottom"].disabled = true;
  mexEl["mex-clear-cache-status"].classList.remove("error");
  mexEl["mex-clear-cache-status"].textContent = "Clearing cache";
  try {
    const payload = await fetchJsonUrl(mexAppUrl("api/moca-explorer/cache/clear"), { method: "POST" });
    mexEl["mex-clear-cache-status"].textContent = `Cleared ${payload.cleared?.mocaExplorer ?? 0} entries.`;
  } catch (error) {
    mexEl["mex-clear-cache-status"].classList.add("error");
    mexEl["mex-clear-cache-status"].textContent = error.message;
  } finally {
    mexEl["mex-clear-cache-bottom"].disabled = false;
  }
}

function setMocaExplorerLoading(loading) {
  mexEl["mex-plot-loader"].classList.toggle("is-visible", loading);
  mexEl["mex-load"].disabled = loading;
}

function setMocaExplorerStatus(text, type) {
  mexEl["mex-status"].textContent = text;
  mexEl["mex-status"].classList.toggle("loading", type === "loading");
  mexEl["mex-status"].classList.toggle("error", type === "error");
}

function plotConfig(name) {
  return {
    responsive: true,
    displaylogo: false,
    scrollZoom: true,
    toImageButtonOptions: { format: "png", filename: name || "moca_explorer", scale: 3 },
  };
}

async function fetchJsonUrl(url, options = {}) {
  const response = await fetch(url, options);
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function associationOrder(rows) {
  const order = [];
  for (const aid of mexState.selectedAids) {
    if (rows.some((row) => row.moca_aid === aid) && !order.includes(aid)) order.push(aid);
  }
  for (const row of rows) {
    if (row.moca_aid && !order.includes(row.moca_aid)) order.push(row.moca_aid);
  }
  return order;
}

function colorForAssociation(aid) {
  const order = mexState.selectedAids.length ? mexState.selectedAids : associationOrder(mexState.members);
  const index = Math.max(0, order.indexOf(aid));
  return mexPalette[index % mexPalette.length];
}

function hoverText(row) {
  const oid = row.moca_oid ?? "";
  const parts = [
    `MOCA OID: ${oid}`,
    `Designation: ${row.designation || ""}`,
    `Membership: ${row.moca_mtid || ""}${row.moca_aid ? ` in ${row.moca_aid}` : ""}`,
    `SPT: ${row.spt || ""}`,
    `RUWE: ${formatCell(row.dr3_ruwe)}`,
  ];
  return parts.map(htmlEscape).join("<br>");
}

function axisTitle(axis) {
  return {
    x: "X (pc)", y: "Y (pc)", z: "Z (pc)",
    u: "U (km/s)", v: "V (km/s)", w: "W (km/s)",
  }[axis] || axis;
}

function defaultRangeForAxis(axis) {
  if (["x", "y", "z"].includes(axis)) return [-150, 150];
  if (axis === "u") return [-80, 70];
  if (["v", "w"].includes(axis)) return [-70, 20];
  return undefined;
}

function formatSptNumber(value) {
  const classes = ["O", "B", "A", "F", "G", "K", "M", "L", "T", "Y"];
  const adjusted = Number(value) + 60;
  const classIndex = Math.floor(adjusted / 10);
  if (classIndex < 0 || classIndex >= classes.length) return "";
  const subclass = adjusted - classIndex * 10;
  return `${classes[classIndex]}${Number(subclass.toFixed(1)).toString()}`;
}

function interp1d(value, xs, ys) {
  if (value < xs[0] || value > xs[xs.length - 1]) return null;
  for (let index = 0; index < xs.length - 1; index += 1) {
    if (value >= xs[index] && value <= xs[index + 1]) {
      const span = xs[index + 1] - xs[index];
      if (span === 0) return ys[index];
      const frac = (value - xs[index]) / span;
      return ys[index] + frac * (ys[index + 1] - ys[index]);
    }
  }
  return null;
}

function parseCsv(value) {
  return String(value || "")
    .replace(/;/g, ",")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item, index, array) => array.indexOf(item) === index);
}

function parseOidList(value) {
  return uniqueNumbers(String(value || "")
    .replace(/;/g, ",")
    .split(",")
    .map(coerceMocaOid)
    .filter((oid) => oid !== null));
}

function coerceMocaOid(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const number = Number(text);
  if (!Number.isInteger(number) || number <= 0) return null;
  return number;
}

function uniqueNumbers(values) {
  const seen = new Set();
  const out = [];
  for (const value of values) {
    const number = Number(value);
    if (Number.isFinite(number) && !seen.has(number)) {
      seen.add(number);
      out.push(number);
    }
  }
  return out;
}

function finite(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value));
}

function formatCell(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "";
    return Math.abs(value) >= 1000 ? value.toFixed(1) : Number(value.toFixed(5)).toString();
  }
  return String(value);
}

function colorWithAlpha(hex, alpha) {
  const value = String(hex || "").replace("#", "");
  if (value.length !== 6) return `rgba(80,80,80,${alpha})`;
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function htmlEscape(value) {
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
