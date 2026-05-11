const xuvAxes = [
  { value: "x", label: "X", unit: "pc" },
  { value: "y", label: "Y", unit: "pc" },
  { value: "z", label: "Z", unit: "pc" },
  { value: "u", label: "U", unit: "km/s" },
  { value: "v", label: "V", unit: "km/s" },
  { value: "w", label: "W", unit: "km/s" },
];

const xuvDefaultAids = ["HYA", "CBER", "TWA", "THA"];
const xuvDefaultMtids = ["BF", "HM", "CM"];
const xuvDefaultAxes = ["x", "y", "z"];
const xuvDefaultCamera = { eye: { x: 1.55, y: 1.55, z: 1.25 } };
const xuvRvRange = Array.from({ length: 50 }, (_value, index) => -50 + index * (100 / 49));
const xuvKappa = 0.004743717361;
const xuvTgal = [
  [-0.0548755604, -0.8734370902, -0.4838350155],
  [0.4941094279, -0.44482963, 0.7469822445],
  [-0.867666149, -0.1980763734, 0.4559837762],
];

const xuvPalette = [
  "#e52638", "#1ed46b", "#bc337d", "#9ee5a4", "#db2bee",
  "#167b2b", "#f2b0f6", "#bce333", "#710c9e", "#d9c771",
  "#5e3966", "#65e6f9", "#9e4302", "#389eaa", "#f19189",
  "#214a65", "#ded1d4", "#1b48bc", "#fd8f2f", "#4c93e9",
];

const xuvState = {
  options: { associations: [], mtids: [], versions: [] },
  selectedAids: [...xuvDefaultAids],
  selectedMtids: [...xuvDefaultMtids],
  selectedOids: [],
  payload: null,
  displayedRows: [],
  selectedRows: [],
  camera: xuvDefaultCamera,
  aidSearchTimer: null,
  cValue: 8,
  searchTimer: null,
  loadToken: 0,
};

const xuvEl = {};

document.addEventListener("DOMContentLoaded", initXyzuvw);

const xuvAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function xuvAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), xuvAppBaseUrl).toString();
}

async function initXyzuvw() {
  collectXyzuvwElements();
  populateAxisSelects();
  readXyzuvwUrlState();
  bindXyzuvwControls();
  renderOidChips();
  await loadXyzuvwOptions();
  await loadXyzuvwData();
}

function collectXyzuvwElements() {
  [
    "xuv-status",
    "xuv-axis-1",
    "xuv-axis-2",
    "xuv-axis-3",
    "xuv-aids-default",
    "xuv-aids-clear",
    "xuv-aid-search",
    "xuv-aid-results",
    "xuv-selected-aids",
    "xuv-mtid-list",
    "xuv-object-search",
    "xuv-object-results",
    "xuv-oid-input",
    "xuv-selected-oids",
    "xuv-bsmdid",
    "xuv-models",
    "xuv-errors",
    "xuv-assmem",
    "xuv-hover",
    "xuv-likely",
    "xuv-asscen",
    "xuv-load",
    "xuv-plot",
    "xuv-plot-loader",
    "xuv-summary",
    "xuv-hint",
    "xuv-open-report",
    "xuv-export-csv",
    "xuv-clear-cache",
    "xuv-clear-cache-bottom",
    "xuv-clear-cache-status",
    "xuv-table-title",
    "xuv-table-subtitle",
    "xuv-table",
  ].forEach((id) => {
    xuvEl[id] = document.getElementById(id);
  });
}

function populateAxisSelects() {
  for (const id of ["xuv-axis-1", "xuv-axis-2", "xuv-axis-3"]) {
    xuvEl[id].innerHTML = xuvAxes.map((axis) => `<option value="${axis.value}">${axis.label}</option>`).join("");
  }
}

function readXyzuvwUrlState() {
  const params = new URLSearchParams(window.location.search);
  const axes = String(params.get("axes") || "xyz").toLowerCase().split("").filter((axis) => xuvAxes.some((row) => row.value === axis));
  const cleanAxes = axes.length === 3 && new Set(axes).size === 3 ? axes : xuvDefaultAxes;
  xuvEl["xuv-axis-1"].value = cleanAxes[0];
  xuvEl["xuv-axis-2"].value = cleanAxes[1];
  xuvEl["xuv-axis-3"].value = cleanAxes[2];
  xuvState.selectedAids = parseCsv(params.get("asso") || params.get("moca_aid") || params.get("aid"), xuvDefaultAids);
  xuvState.selectedMtids = parseCsv(params.get("mtid"), xuvDefaultMtids);
  xuvState.selectedOids = parseOids(params.get("oid") || params.get("moca_oid"));
  xuvEl["xuv-oid-input"].value = xuvState.selectedOids.join(",");
  const checkbox = new Set(parseCsv(params.get("checkbox"), []));
  for (const key of ["models", "errors", "assmem", "hover", "likely", "asscen"]) {
    if (asBool(params.get(key))) checkbox.add(key);
  }
  xuvEl["xuv-models"].checked = checkbox.has("models");
  xuvEl["xuv-errors"].checked = checkbox.has("errors");
  xuvEl["xuv-assmem"].checked = checkbox.has("assmem");
  xuvEl["xuv-hover"].checked = checkbox.has("hover");
  xuvEl["xuv-likely"].checked = checkbox.has("likely");
  xuvEl["xuv-asscen"].checked = checkbox.has("asscen");
}

function bindXyzuvwControls() {
  for (const id of ["xuv-axis-1", "xuv-axis-2", "xuv-axis-3"]) {
    xuvEl[id].addEventListener("change", () => {
      if (xuvEl["xuv-errors"].checked || xuvEl["xuv-models"].checked) {
        loadXyzuvwData();
      } else {
        renderXyzuvw();
        updateXyzuvwUrl();
      }
    });
  }
  xuvEl["xuv-aids-default"].addEventListener("click", () => {
    xuvState.selectedAids = [...xuvDefaultAids];
    renderAssociationList();
    loadXyzuvwData();
  });
  xuvEl["xuv-aids-clear"].addEventListener("click", () => {
    xuvState.selectedAids = [];
    renderAssociationList();
    renderEmptyXyzuvw("Select at least one association");
    updateXyzuvwUrl();
  });
  xuvEl["xuv-aid-search"].addEventListener("input", () => {
    const value = xuvEl["xuv-aid-search"].value.trim();
    clearTimeout(xuvState.aidSearchTimer);
    xuvState.aidSearchTimer = setTimeout(() => searchXyzuvwAssociations(value), 180);
  });
  xuvEl["xuv-aid-search"].addEventListener("focus", () => {
    const value = xuvEl["xuv-aid-search"].value.trim();
    if (value) searchXyzuvwAssociations(value);
  });
  xuvEl["xuv-oid-input"].addEventListener("change", () => {
    xuvState.selectedOids = parseOids(xuvEl["xuv-oid-input"].value);
    renderOidChips();
    loadXyzuvwData();
  });
  xuvEl["xuv-object-search"].addEventListener("input", () => {
    const value = xuvEl["xuv-object-search"].value.trim();
    clearTimeout(xuvState.searchTimer);
    xuvState.searchTimer = setTimeout(() => searchXyzuvwObjects(value), 250);
  });
  xuvEl["xuv-object-search"].addEventListener("focus", () => {
    const value = xuvEl["xuv-object-search"].value.trim();
    if (value) searchXyzuvwObjects(value);
  });
  document.addEventListener("click", (event) => {
    if (!xuvEl["xuv-object-results"].contains(event.target) && event.target !== xuvEl["xuv-object-search"]) {
      xuvEl["xuv-object-results"].hidden = true;
    }
    if (!xuvEl["xuv-aid-results"].contains(event.target) && event.target !== xuvEl["xuv-aid-search"]) {
      xuvEl["xuv-aid-results"].hidden = true;
    }
  });
  xuvEl["xuv-bsmdid"].addEventListener("change", loadXyzuvwData);
  xuvEl["xuv-models"].addEventListener("change", () => {
    if (xuvEl["xuv-models"].checked) {
      loadXyzuvwData();
    } else {
      renderXyzuvw();
      updateXyzuvwUrl();
    }
  });
  for (const id of ["xuv-assmem", "xuv-hover"]) {
    xuvEl[id].addEventListener("change", () => {
      renderXyzuvw();
      updateXyzuvwUrl();
    });
  }
  xuvEl["xuv-errors"].addEventListener("change", loadXyzuvwData);
  for (const id of ["xuv-likely", "xuv-asscen"]) {
    xuvEl[id].addEventListener("change", loadXyzuvwData);
  }
  xuvEl["xuv-load"].addEventListener("click", loadXyzuvwData);
  xuvEl["xuv-export-csv"].addEventListener("click", exportXyzuvwCsv);
  xuvEl["xuv-open-report"].addEventListener("click", openSelectedXyzuvwReport);
  xuvEl["xuv-clear-cache"].addEventListener("click", clearXyzuvwCache);
  xuvEl["xuv-clear-cache-bottom"].addEventListener("click", clearXyzuvwCache);
  window.addEventListener("resize", debounce(() => {
    if (!xuvEl["xuv-object-results"].hidden) positionObjectPopup();
    if (!xuvEl["xuv-aid-results"].hidden) positionAssociationPopup();
    if (xuvState.payload) renderXyzuvw();
  }, 150));
}

async function loadXyzuvwOptions() {
  setXyzuvwStatus("Loading options", "loading");
  const params = apiParams();
  params.set("asso", xuvState.selectedAids.join(","));
  const payload = await fetchJsonUrl(xuvAppUrl(`api/xyzuvw/options?${params.toString()}`));
  if (!payload.ok) {
    setXyzuvwStatus(payload.error || "Could not load options", "error");
    xuvState.options = { associations: [], mtids: [], versions: [{ value: "latest", label: "Latest available" }] };
  } else {
    xuvState.options = {
      associations: payload.associations || [],
      mtids: payload.mtids || [],
      versions: payload.versions || [{ value: "latest", label: "Latest available" }],
    };
  }
  renderAssociationList();
  renderMtidList();
  renderBsmdidOptions();
}

async function loadXyzuvwData() {
  if (!xuvState.selectedAids.length || !xuvState.selectedMtids.length) {
    renderEmptyXyzuvw("Select at least one association and membership type");
    return;
  }
  const token = ++xuvState.loadToken;
  setXyzuvwLoading(true);
  setXyzuvwStatus("Loading XYZUVW data", "loading");
  const params = buildXyzuvwParams();
  const payload = await fetchJsonUrl(xuvAppUrl(`api/xyzuvw/data?${params.toString()}`));
  if (token !== xuvState.loadToken) return;
  if (!payload.ok) {
    xuvState.payload = payload;
    setXyzuvwStatus(payload.error || "Could not load XYZUVW data", "error");
    renderEmptyXyzuvw(payload.error || "Could not load XYZUVW data");
    return;
  }
  xuvState.payload = payload;
  xuvState.cValue = Number(payload.meta?.c_value || 8);
  xuvState.selectedRows = [];
  renderXyzuvw();
  updateXyzuvwUrl();
}

function renderAssociationList() {
  const selected = xuvState.selectedAids;
  if (!selected.length) {
    xuvEl["xuv-selected-aids"].innerHTML = `<div class="designation-result-note">No associations selected</div>`;
    return;
  }
  xuvEl["xuv-selected-aids"].innerHTML = selected.map((aid) => `
    <span class="designation-chip association-chip">
      <span title="${escapeHtml(associationLabel(aid))}">${escapeHtml(associationLabel(aid))}</span>
      <button type="button" data-aid="${escapeHtml(aid)}" aria-label="Remove ${escapeHtml(aid)}">x</button>
    </span>
  `).join("");
  xuvEl["xuv-selected-aids"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const aid = button.dataset.aid;
      xuvState.selectedAids = xuvState.selectedAids.filter((value) => value !== aid);
      renderAssociationList();
      if (xuvState.selectedAids.length) loadXyzuvwData();
      else {
        renderEmptyXyzuvw("Select at least one association");
        updateXyzuvwUrl();
      }
    });
  });
}

async function searchXyzuvwAssociations(query) {
  query = String(query || "").trim();
  if (!query) {
    xuvEl["xuv-aid-results"].hidden = true;
    return;
  }
  const params = apiParams();
  params.set("q", query);
  const payload = await fetchJsonUrl(xuvAppUrl(`api/xyzuvw/associations/search?${params.toString()}`));
  if (!payload.ok) {
    xuvEl["xuv-aid-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
    showAssociationPopup();
    return;
  }
  const results = (payload.options || []).filter((result) => result.value);
  if (!results.length) {
    xuvEl["xuv-aid-results"].innerHTML = `<div class="designation-result-note">No associations found</div>`;
    showAssociationPopup();
    return;
  }
  results.forEach(upsertAssociationOption);
  xuvEl["xuv-aid-results"].innerHTML = results.map((result, index) => {
    const value = String(result.value);
    const selected = xuvState.selectedAids.includes(value);
    const label = result.label || value;
    return `
      <button class="designation-result association-result" type="button" data-index="${index}" ${selected ? "disabled" : ""}>
        <span>${selected ? "Selected: " : ""}${escapeHtml(label)}</span>
      </button>
    `;
  }).join("");
  xuvEl["xuv-aid-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const result = results[Number(button.dataset.index)];
      const aid = String(result.value || "").trim();
      if (aid && !xuvState.selectedAids.includes(aid)) {
        upsertAssociationOption(result);
        xuvState.selectedAids.push(aid);
        renderAssociationList();
        loadXyzuvwData();
      }
      xuvEl["xuv-aid-search"].value = "";
      xuvEl["xuv-aid-results"].hidden = true;
    });
  });
  showAssociationPopup();
}

function showAssociationPopup() {
  positionAssociationPopup();
  xuvEl["xuv-aid-results"].hidden = false;
}

function positionAssociationPopup() {
  const input = xuvEl["xuv-aid-search"];
  const popup = xuvEl["xuv-aid-results"];
  if (!input || !popup) return;
  const rect = input.getBoundingClientRect();
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - 340));
  const available = Math.max(300, window.innerWidth - left - 16);
  const width = Math.min(620, available);
  popup.style.position = "fixed";
  popup.style.left = `${left}px`;
  popup.style.top = `${rect.bottom + 4}px`;
  popup.style.width = `${Math.max(rect.width, width)}px`;
}

function associationLabel(aid) {
  const option = xuvState.options.associations.find((row) => String(row.value) === String(aid));
  return option?.label || String(aid);
}

function upsertAssociationOption(option) {
  if (!option?.value) return;
  const value = String(option.value);
  const label = option.label || value;
  const existing = xuvState.options.associations.find((row) => String(row.value) === value);
  if (existing) {
    existing.label = label;
  } else {
    xuvState.options.associations.push({ value, label });
  }
}

function renderMtidList() {
  const options = xuvState.options.mtids.length
    ? xuvState.options.mtids
    : xuvDefaultMtids.map((mtid) => ({ value: mtid, label: mtid }));
  xuvEl["xuv-mtid-list"].innerHTML = options.map((option) => `
    <label class="checkline xyzuvw-check">
      <input type="checkbox" value="${escapeHtml(option.value)}" ${xuvState.selectedMtids.includes(option.value) ? "checked" : ""}>
      <span title="${escapeHtml(option.description || option.label || option.value)}">${escapeHtml(option.label || option.value)}</span>
    </label>
  `).join("");
  xuvEl["xuv-mtid-list"].querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked && !xuvState.selectedMtids.includes(input.value)) xuvState.selectedMtids.push(input.value);
      if (!input.checked) xuvState.selectedMtids = xuvState.selectedMtids.filter((mtid) => mtid !== input.value);
      loadXyzuvwData();
    });
  });
}

function renderBsmdidOptions() {
  const versions = xuvState.options.versions.length ? xuvState.options.versions : [{ value: "latest", label: "Latest available" }];
  const params = new URLSearchParams(window.location.search);
  const selected = params.get("bsmdid") || "latest";
  xuvEl["xuv-bsmdid"].innerHTML = versions.map((version) => `<option value="${escapeHtml(version.value)}">${escapeHtml(version.label)}</option>`).join("");
  xuvEl["xuv-bsmdid"].value = versions.some((version) => String(version.value) === selected) ? selected : "latest";
}

async function searchXyzuvwObjects(query) {
  if (!query) {
    xuvEl["xuv-object-results"].hidden = true;
    return;
  }
  if (query.length < 2 && !/^\d+$/.test(query)) {
    xuvEl["xuv-object-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    showObjectPopup();
    return;
  }
  const params = apiParams();
  params.set("q", query);
  const payload = await fetchJsonUrl(xuvAppUrl(`api/xyzuvw/search?${params.toString()}`));
  if (!payload.ok) {
    xuvEl["xuv-object-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
    showObjectPopup();
    return;
  }
  const results = payload.options || [];
  if (!results.length) {
    xuvEl["xuv-object-results"].innerHTML = `<div class="designation-result-note">No objects found</div>`;
    showObjectPopup();
    return;
  }
  xuvEl["xuv-object-results"].innerHTML = results.map((result, index) => (
    `<button class="designation-result" type="button" data-index="${index}"><span>${escapeHtml(result.label || `oid${result.value}`)}</span></button>`
  )).join("");
  xuvEl["xuv-object-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const result = results[Number(button.dataset.index)];
      const oid = parseInteger(result.value ?? result.moca_oid);
      if (oid !== null && !xuvState.selectedOids.includes(oid)) {
        xuvState.selectedOids.push(oid);
        syncOidInput();
        renderOidChips();
        loadXyzuvwData();
      }
      xuvEl["xuv-object-search"].value = "";
      xuvEl["xuv-object-results"].hidden = true;
    });
  });
  showObjectPopup();
}

function showObjectPopup() {
  positionObjectPopup();
  xuvEl["xuv-object-results"].hidden = false;
}

function positionObjectPopup() {
  const input = xuvEl["xuv-object-search"];
  const popup = xuvEl["xuv-object-results"];
  if (!input || !popup) return;
  const rect = input.getBoundingClientRect();
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - 340));
  const available = Math.max(300, window.innerWidth - left - 16);
  const width = Math.min(780, available);
  popup.style.position = "fixed";
  popup.style.left = `${left}px`;
  popup.style.top = `${rect.bottom + 4}px`;
  popup.style.width = `${Math.max(rect.width, width)}px`;
}

function renderOidChips() {
  if (!xuvState.selectedOids.length) {
    xuvEl["xuv-selected-oids"].innerHTML = "";
    return;
  }
  xuvEl["xuv-selected-oids"].innerHTML = xuvState.selectedOids.map((oid) => `
    <span class="designation-chip">
      <span>oid${oid}</span>
      <button type="button" data-oid="${oid}" aria-label="Remove oid ${oid}">x</button>
    </span>
  `).join("");
  xuvEl["xuv-selected-oids"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const oid = Number(button.dataset.oid);
      xuvState.selectedOids = xuvState.selectedOids.filter((value) => value !== oid);
      syncOidInput();
      renderOidChips();
      loadXyzuvwData();
    });
  });
}

function renderXyzuvw() {
  if (!xuvState.payload) {
    renderEmptyXyzuvw("No data loaded");
    return;
  }
  const axes = selectedAxes();
  if (new Set(axes).size !== 3) {
    renderEmptyXyzuvw("Please select distinct axes");
    return;
  }
  setXyzuvwLoading(true);
  const rows = preparedMemberRows(axes);
  const overlayRows = preparedOverlayRows(axes);
  xuvState.displayedRows = [...rows, ...overlayRows];
  const colormap = associationColors(xuvState.selectedAids);
  const traces = [];
  if (xuvEl["xuv-asscen"].checked) traces.push(...labelTraces(axes, colormap));
  if (xuvEl["xuv-models"].checked) traces.push(...modelTraces(axes, colormap));
  if (xuvEl["xuv-errors"].checked) traces.push(...errorTraces(axes, rows, colormap));
  const ranges = cubicRange(xuvState.displayedRows);
  traces.push(...memberTraces(rows, colormap));
  traces.push(...overlayTraces(axes, overlayRows));
  traces.push(...referenceTraces(axes));
  const layout = xyzuvwLayout(axes, xuvState.displayedRows, ranges);
  Plotly.react(xuvEl["xuv-plot"], traces, layout, plotConfig("mocadb_xyzuvw_fast"));
  bindXyzuvwPlotEvents();
  const cacheText = xuvState.payload.cache?.hit ? " from cache" : "";
  const truncatedText = xuvState.payload.meta?.truncated ? `, truncated at ${Number(xuvState.payload.meta.max_objects || 0).toLocaleString()}` : "";
  setXyzuvwStatus(`${rows.length.toLocaleString()} members loaded${cacheText}`, "");
  xuvEl["xuv-summary"].textContent = `${rows.length.toLocaleString()} members, ${(xuvState.payload.models || []).length.toLocaleString()} model components, ${overlayRows.length.toLocaleString()} highlighted objects${truncatedText}`;
  xuvEl["xuv-hint"].textContent = xuvEl["xuv-assmem"].checked ? "Assumed-membership coordinates are used when available." : "Empirical XYZUVW coordinates are used.";
  xuvEl["xuv-export-csv"].disabled = xuvState.displayedRows.length === 0;
  renderXyzuvwTable();
  setXyzuvwLoading(false);
}

function preparedMemberRows(axes) {
  const assume = xuvEl["xuv-assmem"].checked;
  return (xuvState.payload.members || []).map((row) => {
    const out = { ...row, kind: "member", label: row.designation || `oid${row.moca_oid}` };
    axes.forEach((axis, index) => {
      out[`plot${index}`] = rowValue(row, axis, assume);
    });
    return out;
  }).filter((row) => axes.every((_axis, index) => finite(row[`plot${index}`])));
}

function preparedOverlayRows(axes) {
  return (xuvState.payload.objects || []).map((row) => {
    const out = { ...row, kind: "highlight", label: row.designation || `oid${row.moca_oid}` };
    axes.forEach((axis, index) => {
      out[`plot${index}`] = rowValue(row, axis, false);
    });
    out.rvLine = axes.some((axis, index) => !finite(out[`plot${index}`]) && ["u", "v", "w"].includes(axis))
      ? rvLineForObject(row, axes)
      : null;
    return out;
  }).filter((row) => axes.every((_axis, index) => finite(row[`plot${index}`])) || row.rvLine);
}

function memberTraces(rows, colormap) {
  const hoverinfo = xuvEl["xuv-hover"].checked ? "text" : "none";
  const traces = [];
  if (rows.length) {
    traces.push({
      type: "scatter3d",
      mode: "markers",
      name: "Members",
      showlegend: false,
      x: rows.map((row) => row.plot0),
      y: rows.map((row) => row.plot1),
      z: rows.map((row) => row.plot2),
      customdata: rows,
      text: rows.map(hoverTextForRow),
      hoverinfo,
      marker: {
        color: rows.map((row) => colormap[row.moca_aid] || "#555"),
        size: 3.4,
        opacity: 1,
        line: { width: 0 },
      },
    });
  }
  for (const aid of xuvState.selectedAids) {
    traces.push({
      type: "scatter3d",
      mode: "markers",
      name: aid,
      legendgroup: aid,
      x: [null],
      y: [null],
      z: [null],
      hoverinfo: "skip",
      marker: { color: colormap[aid] || "#555", size: 7, opacity: 1, line: { width: 0 } },
    });
  }
  return traces;
}

function overlayTraces(axes, rows) {
  const traces = [];
  const hoverinfo = xuvEl["xuv-hover"].checked ? "text" : "none";
  rows.forEach((row) => {
    if (row.rvLine) {
      traces.push({
        type: "scatter3d",
        mode: "lines",
        name: `${row.label} (unknown RV)`,
        x: row.rvLine.x,
        y: row.rvLine.y,
        z: row.rvLine.z,
        line: { color: "#111111", width: 6 },
        customdata: row.rvLine.x.map(() => row),
        text: row.rvLine.x.map(() => hoverTextForRow(row)),
        hoverinfo,
      });
    } else {
      traces.push({
        type: "scatter3d",
        mode: "markers",
        name: row.label,
        x: [row.plot0],
        y: [row.plot1],
        z: [row.plot2],
        customdata: [row],
        text: [hoverTextForRow(row)],
        hoverinfo,
        marker: { color: "#111111", size: 8, symbol: "diamond", line: { color: "#ffffff", width: 1.5 } },
      });
    }
  });
  return traces;
}

function modelTraces(axes, colormap) {
  const surfaceRows = xuvState.payload.modelSurfaces || xuvState.payload.model_surfaces || [];
  if (surfaceRows.length) {
    return surfaceRows.map((surface) => {
      const aid = surface.moca_aid || "model";
      const label = surface.label || `${Math.round(Number(surface.contour || 0) * 100)}%`;
      const color = colormap[aid] || "#555";
      return {
        type: "mesh3d",
        name: `${aid} model (${label})`,
        legendgroup: `${aid}-model`,
        showlegend: true,
        x: surface.x || [],
        y: surface.y || [],
        z: surface.z || [],
        i: surface.i || [],
        j: surface.j || [],
        k: surface.k || [],
        color,
        opacity: Number(surface.opacity || 0.18),
        flatshading: false,
        lighting: { ambient: 0.82, diffuse: 0.55, specular: 0.08, roughness: 0.9, fresnel: 0.05 },
        hoverinfo: "skip",
      };
    });
  }

  const traces = [];
  const levels = [
    { label: "99%", contour: 0.99, opacity: 0.07 },
    { label: "95%", contour: 0.95, opacity: 0.15 },
    { label: "68%", contour: 0.68, opacity: 0.3 },
  ];
  const modelsByAid = new Map();
  for (const model of xuvState.payload.models || []) {
    const aid = model.moca_aid;
    if (!aid) continue;
    if (!modelsByAid.has(aid)) modelsByAid.set(aid, []);
    modelsByAid.get(aid).push(model);
  }
  for (const [aid, models] of modelsByAid.entries()) {
    const color = colormap[aid] || "#555";
    const grid = gmmDensityGrid(models, axes);
    if (!grid) continue;
    for (const level of levels) {
      const threshold = densityThreshold(grid.values, level.contour);
      if (!finite(threshold) || threshold <= 0 || threshold >= grid.maxValue) continue;
      traces.push({
        type: "isosurface",
        name: `${aid} model (${level.label})`,
        legendgroup: `${aid}-model-${level.label}`,
        showlegend: true,
        x: grid.x,
        y: grid.y,
        z: grid.z,
        value: grid.values,
        isomin: threshold,
        isomax: grid.maxValue,
        surface: { count: 1, fill: 1, pattern: "all" },
        caps: { x: { show: false }, y: { show: false }, z: { show: false } },
        colorscale: [[0, color], [1, color]],
        showscale: false,
        opacity: level.opacity,
        lighting: { ambient: 0.8, diffuse: 0.55, specular: 0.08, roughness: 0.9, fresnel: 0.05 },
        hoverinfo: "skip",
      });
    }
  }
  return traces;
}

function gmmDensityGrid(models, axes) {
  const components = models.map((model) => gmmComponent(model, axes)).filter(Boolean);
  if (!components.length) return null;
  const spatialOnly = axes.every((axis) => ["x", "y", "z"].includes(axis));
  const gridSize = spatialOnly ? 40 : 34;
  const bounds = [0, 1, 2].map((axisIndex) => {
    let minValue = Infinity;
    let maxValue = -Infinity;
    components.forEach((component) => {
      const sigma = Math.sqrt(Math.max(component.covariance[axisIndex][axisIndex], 1e-6));
      minValue = Math.min(minValue, component.mean[axisIndex] - 4.5 * sigma);
      maxValue = Math.max(maxValue, component.mean[axisIndex] + 4.5 * sigma);
    });
    if (!finite(minValue) || !finite(maxValue) || minValue === maxValue) return [-1, 1];
    const pad = 0.04 * (maxValue - minValue);
    return [minValue - pad, maxValue + pad];
  });

  const x = [];
  const y = [];
  const z = [];
  const values = [];
  let maxValue = 0;
  for (let ix = 0; ix < gridSize; ix += 1) {
    const px = lerp(bounds[0][0], bounds[0][1], ix / (gridSize - 1));
    for (let iy = 0; iy < gridSize; iy += 1) {
      const py = lerp(bounds[1][0], bounds[1][1], iy / (gridSize - 1));
      for (let iz = 0; iz < gridSize; iz += 1) {
        const pz = lerp(bounds[2][0], bounds[2][1], iz / (gridSize - 1));
        const density = gmmDensityAt([px, py, pz], components);
        x.push(px);
        y.push(py);
        z.push(pz);
        values.push(density);
        if (density > maxValue) maxValue = density;
      }
    }
  }
  if (!finite(maxValue) || maxValue <= 0) return null;
  return { x, y, z, values, maxValue };
}

function gmmComponent(model, axes) {
  const mean = axes.map((axis) => modelCenter(model, axis));
  const covariance = axes.map((axis1) => axes.map((axis2) => modelCovariance(model, axis1, axis2)));
  if (mean.some((value) => !finite(value)) || covariance.flat().some((value) => !finite(value))) return null;
  const inverse = inverseSymmetric3(covariance);
  if (!inverse) return null;
  const weight = finite(model.coeff_amplitude) ? Math.max(0, Number(model.coeff_amplitude)) : 1;
  return {
    mean,
    covariance,
    inverse: inverse.matrix,
    norm: weight / Math.sqrt(Math.max(inverse.det, 1e-30)),
  };
}

function gmmDensityAt(point, components) {
  let density = 0;
  components.forEach((component) => {
    const dx = point.map((value, index) => value - component.mean[index]);
    const inv = component.inverse;
    const q = (
      dx[0] * (inv[0][0] * dx[0] + inv[0][1] * dx[1] + inv[0][2] * dx[2])
      + dx[1] * (inv[1][0] * dx[0] + inv[1][1] * dx[1] + inv[1][2] * dx[2])
      + dx[2] * (inv[2][0] * dx[0] + inv[2][1] * dx[1] + inv[2][2] * dx[2])
    );
    if (finite(q) && q < 100) density += component.norm * Math.exp(-0.5 * Math.max(0, q));
  });
  return density;
}

function densityThreshold(values, contour) {
  const sorted = values.filter((value) => value > 0 && finite(value)).sort((a, b) => b - a);
  if (!sorted.length) return null;
  const total = sorted.reduce((sum, value) => sum + value, 0);
  if (!finite(total) || total <= 0) return null;
  let cumulative = 0;
  for (const value of sorted) {
    cumulative += value;
    if (cumulative / total >= contour) return value;
  }
  return sorted[sorted.length - 1];
}

function inverseSymmetric3(matrix) {
  const a = Number(matrix[0][0]);
  const b = Number(matrix[0][1]);
  const c = Number(matrix[0][2]);
  const d = Number(matrix[1][1]);
  const e = Number(matrix[1][2]);
  const f = Number(matrix[2][2]);
  const det = a * (d * f - e * e) - b * (b * f - c * e) + c * (b * e - c * d);
  if (!finite(det) || det <= 1e-18) return null;
  return {
    det,
    matrix: [
      [(d * f - e * e) / det, (c * e - b * f) / det, (b * e - c * d) / det],
      [(c * e - b * f) / det, (a * f - c * c) / det, (b * c - a * e) / det],
      [(b * e - c * d) / det, (b * c - a * e) / det, (a * d - b * b) / det],
    ],
  };
}

function lerp(start, end, t) {
  return start + (end - start) * t;
}

function labelTraces(axes, colormap) {
  const labels = xuvState.payload.labels || [];
  if (!labels.length) return [];
  const rows = labels.map((row) => ({
    ...row,
    plot0: Number(row[axes[0]]),
    plot1: Number(row[axes[1]]),
    plot2: Number(row[axes[2]]),
  })).filter((row) => finite(row.plot0) && finite(row.plot1) && finite(row.plot2));
  if (!rows.length) return [];
  return [{
    type: "scatter3d",
    mode: "text",
    name: "Association labels",
    x: rows.map((row) => row.plot0),
    y: rows.map((row) => row.plot1),
    z: rows.map((row) => row.plot2),
    text: rows.map((row) => row.moca_aid),
    textfont: { color: rows.map((row) => colormap[row.moca_aid] || "#555"), size: 12 },
    opacity: 0.45,
    hoverinfo: "skip",
  }];
}

function errorTraces(axes, rows, colormap) {
  const sourceRows = xuvState.selectedRows.length
    ? rows.filter((row) => xuvState.selectedRows.some((selected) => Number(selected.moca_oid) === Number(row.moca_oid)))
    : rows.slice(0, 1200);
  const byAid = new Map();
  sourceRows.forEach((row) => {
    const segments = covarianceSegments(row, axes);
    if (!segments) return;
    if (!byAid.has(row.moca_aid)) byAid.set(row.moca_aid, { x: [], y: [], z: [] });
    const out = byAid.get(row.moca_aid);
    segments.forEach((segment) => {
      out.x.push(segment[0][0], segment[1][0], null);
      out.y.push(segment[0][1], segment[1][1], null);
      out.z.push(segment[0][2], segment[1][2], null);
    });
  });
  return [...byAid.entries()].map(([aid, values]) => ({
    type: "scatter3d",
    mode: "lines",
    name: `${aid} errors`,
    legendgroup: aid,
    showlegend: false,
    x: values.x,
    y: values.y,
    z: values.z,
    line: { color: colormap[aid] || "#555", width: 3 },
    opacity: 0.2,
    hoverinfo: "skip",
  }));
}

function referenceTraces(axes) {
  const origin = [0, 0, 0];
  const traces = [{
    type: "scatter3d",
    mode: "markers+text",
    name: "Sun",
    x: [0],
    y: [0],
    z: [0],
    text: ["Sun"],
    textposition: "top center",
    marker: { color: "#111111", size: 5, symbol: "cross" },
    hoverinfo: "skip",
  }];
  const hasSpatialOnly = axes.every((axis) => ["x", "y", "z"].includes(axis));
  if (hasSpatialOnly) {
    const radius = 25;
    const circle = Array.from({ length: 97 }, (_value, index) => 2 * Math.PI * index / 96);
    traces.push({
      type: "scatter3d",
      mode: "lines",
      name: "25 pc",
      x: circle.map((t) => radius * Math.cos(t)),
      y: circle.map((t) => radius * Math.sin(t)),
      z: circle.map(() => 0),
      line: { color: "rgba(0,0,0,0.35)", width: 2 },
      hoverinfo: "skip",
    });
  }
  return traces;
}

function xyzuvwLayout(axes, rows, ranges = null) {
  const axisRanges = ranges || cubicRange(rows);
  const axisTitles = axes.map((axis) => `${axis.toUpperCase()} (${axisUnit(axis)})`);
  return {
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { l: 0, r: 0, t: 0, b: 0 },
    hovermode: "closest",
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 0,
      xanchor: "right",
      x: 1,
      bgcolor: "rgba(238,238,239,0.86)",
      font: { size: 12 },
    },
    scene: {
      xaxis: sceneAxis(axisTitles[0], axisRanges[0]),
      yaxis: sceneAxis(axisTitles[1], axisRanges[1]),
      zaxis: sceneAxis(axisTitles[2], axisRanges[2]),
      aspectmode: "data",
      camera: xuvState.camera || xuvDefaultCamera,
    },
    annotations: [
      {
        text: "MOCAdb",
        x: 0,
        y: 1,
        xref: "paper",
        yref: "paper",
        showarrow: false,
        align: "left",
        font: { family: "Courier New, monospace", size: 16, color: "rgb(150,154,162)" },
        opacity: 0.8,
      },
      {
        text: `${axes.map((axis) => axis.toUpperCase()).join("")} Galactic coordinates`,
        x: 0,
        y: 0,
        xref: "paper",
        yref: "paper",
        showarrow: false,
        align: "left",
        font: { family: "Courier New, monospace", size: 16, color: "rgb(150,154,162)" },
        opacity: 0.8,
      },
    ],
  };
}

function sceneAxis(title, range) {
  return {
    title: { text: title, font: { size: 18 } },
    range,
    showspikes: false,
    showbackground: true,
    backgroundcolor: "#ffffff",
    gridcolor: "#e5e5e5",
    zerolinecolor: "#bdbdbd",
    tickfont: { size: 11 },
  };
}

function cubicRange(rows) {
  const values = [0, 1, 2].map((index) => rows.map((row) => row[`plot${index}`]).filter(finite).map(Number));
  if (values.every((axisValues) => !axisValues.length)) return [[-500, 500], [-500, 500], [-500, 500]];
  const medians = values.map((axisValues) => axisValues.length ? robustMedian(axisValues) : 0);
  const center = medians.some((value) => Math.abs(value) > 2000 / 3) ? medians : [0, 0, 0];
  let extent = 500;
  values.forEach((axisValues, index) => {
    axisValues.forEach((value) => {
      extent = Math.max(extent, Math.abs(value - center[index]));
    });
  });
  extent = Math.min(Math.max(extent * 1.08, 20), 2000);
  return center.map((value) => [value - extent, value + extent]);
}

function bindXyzuvwPlotEvents() {
  if (xuvEl["xuv-plot"].dataset.bound === "1" || typeof xuvEl["xuv-plot"].on !== "function") return;
  xuvEl["xuv-plot"].dataset.bound = "1";
  xuvEl["xuv-plot"].on("plotly_click", (event) => {
    xuvState.selectedRows = (event?.points || []).map((point) => point.customdata).filter((row) => row && row.moca_oid);
    renderXyzuvwTable();
  });
  xuvEl["xuv-plot"].on("plotly_selected", (event) => {
    xuvState.selectedRows = (event?.points || []).map((point) => point.customdata).filter((row) => row && row.moca_oid);
    renderXyzuvwTable();
  });
  xuvEl["xuv-plot"].on("plotly_deselect", () => {
    xuvState.selectedRows = [];
    renderXyzuvwTable();
  });
}

function renderXyzuvwTable() {
  const rows = xuvState.selectedRows.length ? xuvState.selectedRows : xuvState.displayedRows.slice(0, 500);
  xuvEl["xuv-table-title"].textContent = xuvState.selectedRows.length ? `${xuvState.selectedRows.length} selected objects` : "Displayed objects";
  xuvEl["xuv-table-subtitle"].textContent = xuvState.selectedRows.length ? "Click Open selected report for a single selected object." : "Showing the first 500 displayed rows.";
  xuvEl["xuv-open-report"].disabled = xuvState.selectedRows.length !== 1;
  if (!rows.length) {
    xuvEl["xuv-table"].innerHTML = `<div class="selection-table">No objects to display.</div>`;
    return;
  }
  const axes = selectedAxes();
  const columns = ["moca_oid", "designation", "moca_aid", "moca_mtid", "spt", axes[0], axes[1], axes[2], "ya_prob", "report"];
  const tableRows = rows.map((row) => ({
    moca_oid: Number(row.moca_oid).toFixed(0),
    designation: row.designation || "",
    moca_aid: row.moca_aid || "",
    moca_mtid: row.moca_mtid || "",
    spt: row.spt || "",
    [axes[0]]: formatNumber(row.plot0, 2),
    [axes[1]]: formatNumber(row.plot1, 2),
    [axes[2]]: formatNumber(row.plot2, 2),
    ya_prob: finite(row.ya_prob) ? formatNumber(row.ya_prob, 1) : "",
    report: `<a class="report-link" href="${mocaReportUrl(row.moca_oid)}" target="_blank" rel="noopener">Report</a>`,
  }));
  xuvEl["xuv-table"].innerHTML = tableHtml(columns, tableRows, { htmlColumns: new Set(["report"]) });
}

function renderEmptyXyzuvw(message) {
  const layout = {
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    scene: {
      xaxis: { visible: false },
      yaxis: { visible: false },
      zaxis: { visible: false },
    },
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
  Plotly.react(xuvEl["xuv-plot"], [], layout, plotConfig("mocadb_xyzuvw_empty"));
  xuvEl["xuv-summary"].textContent = message;
  xuvEl["xuv-table"].innerHTML = "";
  xuvEl["xuv-export-csv"].disabled = true;
  setXyzuvwLoading(false);
}

function rowValue(row, axis, assumeMembership) {
  const optKey = `${axis}_opt`;
  if (assumeMembership && finite(row[optKey])) return Number(row[optKey]);
  return finite(row[axis]) ? Number(row[axis]) : null;
}

function covarianceSegments(row, axes) {
  const matrix = axes.map((axis1) => axes.map((axis2) => scaledCovariance(row, axis1, axis2)));
  if (matrix.flat().some((value) => !finite(value))) return null;
  const eig = jacobiEigen3(matrix);
  if (!eig) return null;
  const center = [row.plot0, row.plot1, row.plot2].map(Number);
  const segments = [];
  for (let component = 0; component < 3; component += 1) {
    const sigma = Math.sqrt(Math.max(0, eig.values[component]));
    if (!finite(sigma) || sigma <= 0) continue;
    const vector = [eig.vectors[0][component], eig.vectors[1][component], eig.vectors[2][component]];
    segments.push([
      center.map((value, axisIndex) => value - vector[axisIndex] * sigma),
      center.map((value, axisIndex) => value + vector[axisIndex] * sigma),
    ]);
  }
  return segments;
}

function modelCenter(model, axis) {
  const key = `${axis}_cen`;
  const value = model[key];
  if (!finite(value)) return null;
  return ["u", "v", "w"].includes(axis) ? Number(value) * xuvState.cValue : Number(value);
}

function modelCovariance(model, axis1, axis2) {
  const key = covarianceKey(axis1, axis2);
  return scaleCovariance(axis1, axis2, model[key]);
}

function scaledCovariance(row, axis1, axis2) {
  const key = covarianceKey(axis1, axis2);
  return scaleCovariance(axis1, axis2, row[key]);
}

function scaleCovariance(axis1, axis2, value) {
  if (!finite(value)) return 0;
  const kin1 = ["u", "v", "w"].includes(axis1);
  const kin2 = ["u", "v", "w"].includes(axis2);
  if (kin1 && kin2) return Number(value) * xuvState.cValue * xuvState.cValue;
  if (kin1 || kin2) return Number(value) * xuvState.cValue;
  return Number(value);
}

function covarianceKey(axis1, axis2) {
  const order = ["x", "y", "z", "u", "v", "w"];
  const sorted = [axis1, axis2].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  return `${sorted[0]}${sorted[1]}_covar`;
}

function jacobiEigen3(input) {
  const a = input.map((row) => row.map(Number));
  let v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  for (let iter = 0; iter < 50; iter += 1) {
    let p = 0;
    let q = 1;
    let max = Math.abs(a[0][1]);
    for (const pair of [[0, 2], [1, 2]]) {
      const value = Math.abs(a[pair[0]][pair[1]]);
      if (value > max) {
        max = value;
        p = pair[0];
        q = pair[1];
      }
    }
    if (max < 1e-10) break;
    const theta = 0.5 * Math.atan2(2 * a[p][q], a[q][q] - a[p][p]);
    const c = Math.cos(theta);
    const s = Math.sin(theta);
    const app = c * c * a[p][p] - 2 * s * c * a[p][q] + s * s * a[q][q];
    const aqq = s * s * a[p][p] + 2 * s * c * a[p][q] + c * c * a[q][q];
    a[p][q] = 0;
    a[q][p] = 0;
    a[p][p] = app;
    a[q][q] = aqq;
    for (let r = 0; r < 3; r += 1) {
      if (r === p || r === q) continue;
      const arp = a[r][p];
      const arq = a[r][q];
      a[r][p] = c * arp - s * arq;
      a[p][r] = a[r][p];
      a[r][q] = s * arp + c * arq;
      a[q][r] = a[r][q];
    }
    for (let r = 0; r < 3; r += 1) {
      const vrp = v[r][p];
      const vrq = v[r][q];
      v[r][p] = c * vrp - s * vrq;
      v[r][q] = s * vrp + c * vrq;
    }
  }
  const values = [a[0][0], a[1][1], a[2][2]];
  if (values.some((value) => !finite(value))) return null;
  return { values, vectors: v };
}

function rvLineForObject(row, axes) {
  if (!finite(row.ra) || !finite(row.dec) || !finite(row.pmra_masyr) || !finite(row.pmdec_masyr) || !finite(row.distance_pc)) return null;
  const uvw = equatorialUVW(Number(row.ra), Number(row.dec), Number(row.pmra_masyr), Number(row.pmdec_masyr), xuvRvRange, Number(row.distance_pc));
  const output = { x: [], y: [], z: [] };
  xuvRvRange.forEach((_rv, index) => {
    const point = axes.map((axis) => {
      if (axis === "u") return uvw.u[index] * xuvState.cValue;
      if (axis === "v") return uvw.v[index] * xuvState.cValue;
      if (axis === "w") return uvw.w[index] * xuvState.cValue;
      return rowValue(row, axis, false);
    });
    if (point.every(finite)) {
      output.x.push(point[0]);
      output.y.push(point[1]);
      output.z.push(point[2]);
    }
  });
  return output.x.length ? output : null;
}

function equatorialUVW(ra, dec, pmra, pmdec, rvArray, dist) {
  const cosRa = Math.cos(rad(ra));
  const cosDec = Math.cos(rad(dec));
  const sinRa = Math.sin(rad(ra));
  const sinDec = Math.sin(rad(dec));
  const t1 = xuvTgal[0][0] * cosRa * cosDec + xuvTgal[0][1] * sinRa * cosDec + xuvTgal[0][2] * sinDec;
  const t2 = -xuvTgal[0][0] * sinRa + xuvTgal[0][1] * cosRa;
  const t3 = -xuvTgal[0][0] * cosRa * sinDec - xuvTgal[0][1] * sinRa * sinDec + xuvTgal[0][2] * cosDec;
  const t4 = xuvTgal[1][0] * cosRa * cosDec + xuvTgal[1][1] * sinRa * cosDec + xuvTgal[1][2] * sinDec;
  const t5 = -xuvTgal[1][0] * sinRa + xuvTgal[1][1] * cosRa;
  const t6 = -xuvTgal[1][0] * cosRa * sinDec - xuvTgal[1][1] * sinRa * sinDec + xuvTgal[1][2] * cosDec;
  const t7 = xuvTgal[2][0] * cosRa * cosDec + xuvTgal[2][1] * sinRa * cosDec + xuvTgal[2][2] * sinDec;
  const t8 = -xuvTgal[2][0] * sinRa + xuvTgal[2][1] * cosRa;
  const t9 = -xuvTgal[2][0] * cosRa * sinDec - xuvTgal[2][1] * sinRa * sinDec + xuvTgal[2][2] * cosDec;
  const reducedDist = xuvKappa * dist;
  return {
    u: rvArray.map((rv) => t1 * rv + t2 * pmra * reducedDist + t3 * pmdec * reducedDist),
    v: rvArray.map((rv) => t4 * rv + t5 * pmra * reducedDist + t6 * pmdec * reducedDist),
    w: rvArray.map((rv) => t7 * rv + t8 * pmra * reducedDist + t9 * pmdec * reducedDist),
  };
}

function hoverTextForRow(row) {
  return [
    `<b>${escapeHtml(row.designation || `oid${row.moca_oid}`)}</b>`,
    `MOCA OID: ${escapeHtml(row.moca_oid)}`,
    `Association: ${escapeHtml(row.moca_aid || "")}`,
    `Membership: ${escapeHtml(row.moca_mtid || "")}`,
    `SPT: ${escapeHtml(row.spt || "")}`,
    `RUWE: ${finite(row.dr3_ruwe) ? formatNumber(row.dr3_ruwe, 2) : "N/A"}`,
    `YA prob: ${finite(row.ya_prob) ? `${formatNumber(row.ya_prob, 1)}%` : "N/A"}`,
  ].join("<br>");
}

function selectedAxes() {
  return [xuvEl["xuv-axis-1"].value, xuvEl["xuv-axis-2"].value, xuvEl["xuv-axis-3"].value];
}

function axisUnit(axis) {
  return ["u", "v", "w"].includes(axis) ? "km/s" : "pc";
}

function associationColors(aids) {
  const out = {};
  aids.forEach((aid, index) => {
    out[aid] = xuvPalette[index % xuvPalette.length];
  });
  return out;
}

function buildXyzuvwParams() {
  const params = apiParams();
  params.set("axes", selectedAxes().join(""));
  params.set("asso", xuvState.selectedAids.join(","));
  params.set("mtid", xuvState.selectedMtids.join(","));
  if (xuvState.selectedOids.length) params.set("oid", xuvState.selectedOids.join(","));
  params.set("bsmdid", xuvEl["xuv-bsmdid"].value || "latest");
  const checkbox = checkboxValues();
  if (checkbox.length) params.set("checkbox", checkbox.join(","));
  return params;
}

function checkboxValues() {
  const out = [];
  if (xuvEl["xuv-models"].checked) out.push("models");
  if (xuvEl["xuv-errors"].checked) out.push("errors");
  if (xuvEl["xuv-assmem"].checked) out.push("assmem");
  if (xuvEl["xuv-hover"].checked) out.push("hover");
  if (xuvEl["xuv-likely"].checked) out.push("likely");
  if (xuvEl["xuv-asscen"].checked) out.push("asscen");
  return out;
}

function updateXyzuvwUrl() {
  const params = new URLSearchParams(window.location.search);
  params.set("axes", selectedAxes().join(""));
  if (xuvState.selectedAids.length) params.set("asso", xuvState.selectedAids.join(","));
  else params.delete("asso");
  params.delete("moca_aid");
  params.delete("aid");
  if (xuvState.selectedMtids.length) params.set("mtid", xuvState.selectedMtids.join(","));
  else params.delete("mtid");
  if (xuvState.selectedOids.length) params.set("oid", xuvState.selectedOids.join(","));
  else params.delete("oid");
  params.delete("moca_oid");
  if (xuvEl["xuv-bsmdid"].value && xuvEl["xuv-bsmdid"].value !== "latest") params.set("bsmdid", xuvEl["xuv-bsmdid"].value);
  else params.delete("bsmdid");
  const checkbox = checkboxValues();
  if (checkbox.length) params.set("checkbox", checkbox.join(","));
  else params.delete("checkbox");
  for (const key of ["models", "errors", "assmem", "hover", "likely", "asscen"]) params.delete(key);
  window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}

function exportXyzuvwCsv() {
  const rows = xuvState.selectedRows.length ? xuvState.selectedRows : xuvState.displayedRows;
  if (!rows.length) return;
  const axes = selectedAxes();
  const columns = ["moca_oid", "designation", "moca_aid", "moca_mtid", "spt", axes[0], axes[1], axes[2], "ya_prob", "dr3_ruwe"];
  const csvRows = rows.map((row) => [
    Number(row.moca_oid).toFixed(0),
    row.designation || "",
    row.moca_aid || "",
    row.moca_mtid || "",
    row.spt || "",
    row.plot0,
    row.plot1,
    row.plot2,
    row.ya_prob ?? "",
    row.dr3_ruwe ?? "",
  ]);
  const csv = [columns.join(","), ...csvRows.map((row) => row.map(csvCell).join(","))].join("\n");
  downloadBlob(csv, "mocadb_xyzuvw_fast.csv", "text/csv;charset=utf-8");
}

function openSelectedXyzuvwReport() {
  if (xuvState.selectedRows.length !== 1) return;
  window.open(mocaReportUrl(xuvState.selectedRows[0].moca_oid), "_blank", "noopener");
}

async function clearXyzuvwCache() {
  xuvEl["xuv-clear-cache"].disabled = true;
  xuvEl["xuv-clear-cache-bottom"].disabled = true;
  xuvEl["xuv-clear-cache-status"].textContent = "Clearing...";
  xuvEl["xuv-clear-cache-status"].classList.remove("error");
  try {
    const payload = await postXyzuvwJson("api/xyzuvw/cache/clear", {});
    if (!payload.ok) throw new Error(payload.error || "Cache clear failed");
    const cleared = payload.cleared?.xyzuvw || 0;
    xuvEl["xuv-clear-cache-status"].textContent = `Cleared ${cleared} cached payload${cleared === 1 ? "" : "s"}.`;
    await loadXyzuvwOptions();
    await loadXyzuvwData();
  } catch (error) {
    xuvEl["xuv-clear-cache-status"].textContent = error.message;
    xuvEl["xuv-clear-cache-status"].classList.add("error");
  } finally {
    xuvEl["xuv-clear-cache"].disabled = false;
    xuvEl["xuv-clear-cache-bottom"].disabled = false;
  }
}

function setXyzuvwStatus(text, mode = "") {
  xuvEl["xuv-status"].textContent = text;
  xuvEl["xuv-status"].className = `status${mode ? ` ${mode}` : ""}`;
}

function setXyzuvwLoading(loading) {
  xuvEl["xuv-plot-loader"].classList.toggle("is-visible", Boolean(loading));
}

function syncOidInput() {
  xuvEl["xuv-oid-input"].value = xuvState.selectedOids.join(",");
}

function parseCsv(raw, fallback = []) {
  if (!raw) return [...fallback];
  return String(raw).split(",").map((item) => item.trim()).filter(Boolean);
}

function parseOids(raw) {
  const seen = new Set();
  const out = [];
  String(raw || "").split(",").forEach((item) => {
    const oid = parseInteger(item.trim());
    if (oid !== null && !seen.has(oid)) {
      seen.add(oid);
      out.push(oid);
    }
  });
  return out;
}

function apiParams() {
  const source = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "user", "pwd", "dbase", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  return params;
}

async function fetchJsonUrl(url) {
  const response = await fetch(url);
  return response.json();
}

async function postXyzuvwJson(path, body) {
  const params = apiParams();
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(xuvAppUrl(`${path}${params.toString() ? `${separator}${params.toString()}` : ""}`), {
    method: "POST",
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
      height: 1100,
      width: 1500,
      scale: 2,
      filename,
    },
  };
}

function tableHtml(columns, rows, options = {}) {
  const htmlColumns = options.htmlColumns || new Set();
  return `
    <div class="selection-table">
      <table>
        <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>${columns.map((column) => `<td>${htmlColumns.has(column) ? (row[column] || "") : escapeHtml(row[column] ?? "")}</td>`).join("")}</tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function mocaReportUrl(oid) {
  return `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(Number(oid).toFixed(0))}%29&search-type=star`;
}

function robustMedian(values) {
  const clean = values.map(Number).filter(finite).sort((a, b) => a - b);
  if (!clean.length) return NaN;
  const mid = Math.floor(clean.length / 2);
  return clean.length % 2 ? clean[mid] : 0.5 * (clean[mid - 1] + clean[mid]);
}

function finite(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" && value.trim() === "") return false;
  return Number.isFinite(Number(value));
}

function parseInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function asBool(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

function formatNumber(value, digits) {
  return finite(value) ? Number(value).toFixed(digits) : "";
}

function rad(value) {
  return Number(value) * Math.PI / 180;
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
