const xuvAxes = [
  { value: "x", label: "X", unit: "pc" },
  { value: "y", label: "Y", unit: "pc" },
  { value: "z", label: "Z", unit: "pc" },
  { value: "u", label: "U", unit: "km/s" },
  { value: "v", label: "V", unit: "km/s" },
  { value: "w", label: "W", unit: "km/s" },
];

const xuvDefaultAids = ["HYA", "TWA", "CBER", "PERI", "BL1", "BPMG"];
const xuvDefaultMtids = ["BF", "HM", "CM"];
const xuvDefaultAxes = ["x", "y", "z"];
const xuvCleanReferenceRadii = [10, 100, 1000];
const xuvCleanVelocityReferenceRadii = [10, 50, 100];
const xuvDefaultCameraReferencePc = Math.max(...xuvCleanReferenceRadii);
const xuvDefaultCameraDistancePc = 500;
const xuvDefaultCamera = cameraFromReferenceDistance(
  { x: 1.55, y: 1.55, z: 1.25 },
  xuvDefaultCameraDistancePc / xuvDefaultCameraReferencePc,
);
const xuvCleanSceneBackground = "#08090c";
const xuvCleanCircleColor = "#00a8ff";
const xuvCleanReferenceColor = "rgba(0,168,255,0.29)";
const xuvCleanMinorReferenceColor = "rgba(0,168,255,0.145)";
const xuvCleanPlaneColor = "#73c9ff";
const xuvVerticalAspectScale = 0.25;
const xuvDualMode = document.body?.classList.contains("xyz2-page");
const xuvDualPanels = [
  { key: "xyz", axes: ["x", "y", "z"], plotId: "xuv-plot-xyz", label: "XYZ" },
  { key: "uvw", axes: ["u", "v", "w"], plotId: "xuv-plot-uvw", label: "UVW" },
];
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
const xuvAgeColorscale = [
  [0, "rgb(150,0,90)"],
  [0.125, "rgb(0,0,200)"],
  [0.25, "rgb(0,25,255)"],
  [0.375, "rgb(0,152,255)"],
  [0.5, "rgb(44,255,150)"],
  [0.625, "rgb(151,255,0)"],
  [0.75, "rgb(255,234,0)"],
  [0.875, "rgb(255,111,0)"],
  [1, "rgb(255,0,0)"],
];
const xuvNoAgeColor = "#858a8d";

const xuvState = {
  options: { associations: [], mtids: [], versions: [] },
  selectedAids: [...xuvDefaultAids],
  selectedMtids: [...xuvDefaultMtids],
  selectedOids: [],
  payload: null,
  payloads: {},
  displayedRows: [],
  selectedRows: [],
  camera: xuvDefaultCamera,
  panelCameras: {
    main: xuvDefaultCamera,
    xyz: xuvDefaultCamera,
    uvw: xuvDefaultCamera,
  },
  aidSearchTimer: null,
  cValue: 8,
  searchTimer: null,
  loadToken: 0,
  pendingCameraRestore: null,
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
    "xuv-show-axes",
    "xuv-likely",
    "xuv-subgroups",
    "xuv-color-age",
    "xuv-asscen",
    "xuv-load",
    "xuv-plot",
    "xuv-plot-xyz",
    "xuv-plot-uvw",
    "xuv-plot-loader",
    "xuv-summary",
    "xuv-hint",
    "xuv-open-report",
    "xuv-export-csv",
    "xuv-export-tsv",
    "xuv-export-fits",
    "xuv-export-votable",
    "xuv-download-frozen",
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
  const hasCheckboxParam = params.has("checkbox");
  const checkbox = new Set(parseCsv(params.get("checkbox"), []));
  for (const key of ["models", "errors", "assmem", "hover", "likely", "asscen", "subgroups", "agecolor"]) {
    if (asBool(params.get(key))) checkbox.add(key);
  }
  if (["color_age", "color_by_age", "age_color"].some((key) => asBool(params.get(key)))) checkbox.add("agecolor");
  if (["age", "color_age", "color-by-age", "color_by_age", "colorbyage"].some((key) => checkbox.has(key))) checkbox.add("agecolor");
  if (!hasCheckboxParam && !params.has("models")) checkbox.add("models");
  if (!hasCheckboxParam && !params.has("likely")) checkbox.add("likely");
  if (!hasCheckboxParam && !params.has("assmem")) checkbox.add("assmem");
  if (!hasCheckboxParam && !params.has("subgroups")) checkbox.add("subgroups");
  xuvEl["xuv-models"].checked = checkbox.has("models");
  xuvEl["xuv-errors"].checked = checkbox.has("errors");
  xuvEl["xuv-assmem"].checked = checkbox.has("assmem");
  xuvEl["xuv-hover"].checked = checkbox.has("hover");
  xuvEl["xuv-show-axes"].checked = params.has("showaxes") ? asBool(params.get("showaxes")) : false;
  xuvEl["xuv-likely"].checked = checkbox.has("likely");
  xuvEl["xuv-subgroups"].checked = checkbox.has("subgroups");
  xuvEl["xuv-color-age"].checked = checkbox.has("agecolor");
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
  for (const id of ["xuv-assmem", "xuv-hover", "xuv-show-axes"]) {
    xuvEl[id].addEventListener("change", () => {
      renderXyzuvw();
      updateXyzuvwUrl();
    });
  }
  xuvEl["xuv-errors"].addEventListener("change", loadXyzuvwData);
  for (const id of ["xuv-likely", "xuv-subgroups", "xuv-color-age", "xuv-asscen"]) {
    xuvEl[id].addEventListener("change", loadXyzuvwData);
  }
  xuvEl["xuv-load"].addEventListener("click", loadXyzuvwData);
  xuvEl["xuv-export-csv"].addEventListener("click", () => exportXyzuvw("csv"));
  xuvEl["xuv-export-tsv"].addEventListener("click", () => exportXyzuvw("tsv"));
  xuvEl["xuv-export-fits"].addEventListener("click", () => exportXyzuvw("fits"));
  xuvEl["xuv-export-votable"].addEventListener("click", () => exportXyzuvw("votable"));
  xuvEl["xuv-download-frozen"].addEventListener("click", downloadFrozenXyzuvwPlotlyScene);
  xuvEl["xuv-open-report"].addEventListener("click", openSelectedXyzuvwReport);
  if (xuvEl["xuv-clear-cache"]) xuvEl["xuv-clear-cache"].addEventListener("click", clearXyzuvwCache);
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
  if (xuvDualMode) {
    const payloadEntries = await Promise.all(xuvDualPanels.map(async (panel) => {
      const params = buildXyzuvwParams(panel.axes);
      const payload = await fetchJsonUrl(xuvAppUrl(`api/xyzuvw/data?${params.toString()}`));
      return [panel.key, payload];
    }));
    if (token !== xuvState.loadToken) return;
    xuvState.payloads = Object.fromEntries(payloadEntries);
    const failedPayload = payloadEntries.map((entry) => entry[1]).find((payload) => !payload.ok);
    if (failedPayload) {
      xuvState.payload = failedPayload;
      setXyzuvwStatus(failedPayload.error || "Could not load XYZUVW data", "error");
      renderEmptyXyzuvw(failedPayload.error || "Could not load XYZUVW data");
      return;
    }
    xuvState.payload = xuvState.payloads.xyz;
    xuvState.cValue = Number(xuvState.payloads.xyz?.meta?.c_value || xuvState.payloads.uvw?.meta?.c_value || 8);
    xuvState.selectedRows = [];
    renderXyzuvw();
    updateXyzuvwUrl();
    return;
  }
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
  if (xuvDualMode) {
    renderXyz2();
    return;
  }
  if (!xuvState.payload) {
    renderEmptyXyzuvw("No data loaded");
    return;
  }
  const axes = selectedAxes();
  if (new Set(axes).size !== 3) {
    renderEmptyXyzuvw("Please select distinct axes");
    return;
  }
  const showAxes = xuvEl["xuv-show-axes"].checked;
  setXyzuvwLoading(true);
  const rows = preparedMemberRows(axes);
  const overlayRows = preparedOverlayRows(axes);
  xuvState.displayedRows = [...rows, ...overlayRows];
  const colormap = xyzuvwAssociationColors([xuvState.payload], rows);
  const memberAids = new Set(rows.map((row) => String(row.moca_aid || "Unassigned")));
  const contextTraces = [];
  if (xuvEl["xuv-models"].checked) contextTraces.push(...modelTraces(axes, colormap));
  if (xuvEl["xuv-errors"].checked) contextTraces.push(...errorTraces(axes, rows, colormap));
  const referenceContext = cleanReferenceContext(axes, xuvState.displayedRows, contextTraces);
  let ranges = xyzuvwRanges(axes, xuvState.displayedRows, showAxes, referenceContext);
  const traces = [];
  traces.push(...referenceTraces(axes, showAxes, referenceContext));
  traces.push(...contextTraces);
  traces.push(...memberTraces(rows, colormap));
  if (xuvEl["xuv-asscen"].checked) traces.push(...labelTraces(axes, colormap, memberAids, showAxes));
  traces.push(...overlayTraces(axes, overlayRows));
  traces.push(...associationCenterLabelTraces(rows, colormap, ranges, showAxes));
  const layout = xyzuvwLayout(axes, xuvState.displayedRows, ranges, showAxes);
  Plotly.react(xuvEl["xuv-plot"], traces, layout, plotConfig("mocadb_xyzuvw_fast"));
  bindXyzuvwPlotEvents();
  const cacheText = xuvState.payload.cache?.hit ? " from cache" : "";
  const truncatedText = xuvState.payload.meta?.truncated ? `, truncated at ${Number(xuvState.payload.meta.max_objects || 0).toLocaleString()}` : "";
  setXyzuvwStatus(`${rows.length.toLocaleString()} members loaded${cacheText}`, "");
  xuvEl["xuv-summary"].textContent = `${rows.length.toLocaleString()} members, ${(xuvState.payload.models || []).length.toLocaleString()} model components, ${overlayRows.length.toLocaleString()} highlighted objects${truncatedText}`;
  renderXyzuvwHint();
  setXyzuvwExportDisabled(xuvState.displayedRows.length === 0);
  renderXyzuvwTable();
  setXyzuvwLoading(false);
}

function renderXyz2() {
  if (!xuvState.payloads.xyz || !xuvState.payloads.uvw) {
    renderEmptyXyzuvw("No data loaded");
    return;
  }
  const showAxes = xuvEl["xuv-show-axes"].checked;
  setXyzuvwLoading(true);
  const colormap = xyzuvwAssociationColors(Object.values(xuvState.payloads || {}));
  const panelOutputs = xuvDualPanels.map((panel) => {
    const payload = xuvState.payloads[panel.key];
    const output = buildXyzuvwPanel(panel.axes, payload, showAxes, colormap, panel.key);
    const plotEl = xuvEl[panel.plotId];
    Plotly.react(plotEl, output.traces, output.layout, plotConfig(`mocadb_xyz2_${panel.key}`));
    bindXyzuvwPlotEvents(plotEl, panel.key, panel.axes);
    return { ...panel, ...output };
  });
  const xyzOutput = panelOutputs.find((panel) => panel.key === "xyz") || panelOutputs[0];
  xuvState.payload = xuvState.payloads.xyz;
  xuvState.displayedRows = [...xyzOutput.rows, ...xyzOutput.overlayRows];
  const cacheText = xuvState.payloads.xyz?.cache?.hit && xuvState.payloads.uvw?.cache?.hit ? " from cache" : "";
  const truncatedText = xuvState.payloads.xyz?.meta?.truncated ? `, truncated at ${Number(xuvState.payloads.xyz.meta.max_objects || 0).toLocaleString()}` : "";
  setXyzuvwStatus(`${xyzOutput.rows.length.toLocaleString()} members loaded${cacheText}`, "");
  const uvwOutput = panelOutputs.find((panel) => panel.key === "uvw") || { rows: [], overlayRows: [] };
  xuvEl["xuv-summary"].textContent = `XYZ: ${xyzOutput.rows.length.toLocaleString()} members, ${(xuvState.payloads.xyz.models || []).length.toLocaleString()} model components; UVW: ${uvwOutput.rows.length.toLocaleString()} members, ${(xuvState.payloads.uvw.models || []).length.toLocaleString()} model components; ${xyzOutput.overlayRows.length.toLocaleString()} highlighted objects${truncatedText}`;
  renderXyzuvwHint();
  setXyzuvwExportDisabled(xuvState.displayedRows.length === 0);
  renderXyzuvwTable();
  setXyzuvwLoading(false);
}

function buildXyzuvwPanel(axes, payload, showAxes, colormap, panelKey = "main") {
  const rows = preparedMemberRows(axes, payload);
  const overlayRows = preparedOverlayRows(axes, payload);
  const memberAids = new Set(rows.map((row) => String(row.moca_aid || "Unassigned")));
  const contextTraces = [];
  if (xuvEl["xuv-models"].checked) contextTraces.push(...modelTraces(axes, colormap, payload));
  if (xuvEl["xuv-errors"].checked) contextTraces.push(...errorTraces(axes, rows, colormap));
  const displayedRows = [...rows, ...overlayRows];
  const referenceContext = cleanReferenceContext(axes, displayedRows, contextTraces);
  let ranges = xyzuvwRanges(axes, displayedRows, showAxes, referenceContext);
  const traces = [];
  traces.push(...referenceTraces(axes, showAxes, referenceContext));
  traces.push(...contextTraces);
  traces.push(...memberTraces(rows, colormap));
  if (xuvEl["xuv-asscen"].checked) traces.push(...labelTraces(axes, colormap, memberAids, showAxes, payload));
  traces.push(...overlayTraces(axes, overlayRows));
  traces.push(...associationCenterLabelTraces(rows, colormap, ranges, showAxes));
  const layout = xyzuvwLayout(axes, displayedRows, ranges, showAxes, panelKey);
  return { rows, overlayRows, traces, layout };
}

function renderXyzuvwHint() {
  const lines = [
    xuvEl["xuv-assmem"].checked
      ? "Assumed-membership coordinates are used when available."
      : "Empirical XYZUVW coordinates are used.",
  ];
  if (xuvEl["xuv-models"].checked) {
    lines.push("BANYAN Σ models are displayed as 68%, 95% and 99% probability isodensity surfaces.");
  }
  xuvEl["xuv-hint"].innerHTML = lines.map(escapeHtml).join("<br>");
}

function preparedMemberRows(axes, payload = xuvState.payload) {
  const assume = xuvEl["xuv-assmem"].checked;
  return plottedRowsForAxes(payload?.members || [], axes, assume, "member");
}

function preparedOverlayRows(axes, payload = xuvState.payload) {
  return (payload?.objects || []).map((row) => {
    const out = withPlotValues(row, axes, false, "highlight");
    out.rvLine = axes.some((axis, index) => !finite(out[`plot${index}`]) && ["u", "v", "w"].includes(axis))
      ? rvLineForObject(row, axes)
      : null;
    return out;
  }).filter((row) => axes.every((_axis, index) => finite(row[`plot${index}`])) || row.rvLine);
}

function plottedRowsForAxes(rows, axes, assumeMembership = xuvEl["xuv-assmem"].checked, kind = null) {
  return (rows || []).map((row) => withPlotValues(row, axes, assumeMembership, kind))
    .filter((row) => axes.every((_axis, index) => finite(row[`plot${index}`])));
}

function withPlotValues(row, axes, assumeMembership, kind = null) {
  const out = {
    ...row,
    kind: kind || row.kind,
    label: row.label || row.designation || `oid${row.moca_oid}`,
  };
  axes.forEach((axis, index) => {
    out[`plot${index}`] = rowValue(row, axis, assumeMembership);
  });
  return out;
}

function memberTraces(rows, colormap) {
  const hoverinfo = xuvEl["xuv-hover"].checked ? "text" : "none";
  const traces = [];
  const rowsByAid = new Map();
  rows.forEach((row) => {
    const aid = String(row.moca_aid || "Unassigned");
    if (!rowsByAid.has(aid)) rowsByAid.set(aid, []);
    rowsByAid.get(aid).push(row);
  });
  const orderedAids = [
    ...xuvState.selectedAids.filter((aid) => rowsByAid.has(String(aid))),
    ...[...rowsByAid.keys()].filter((aid) => !xuvState.selectedAids.includes(aid)),
  ];
  let ageScaleShown = false;
  orderedAids.forEach((aid) => {
    const aidRows = rowsByAid.get(String(aid)) || [];
    if (!aidRows.length) return;
    const age = ageForRows(aidRows);
    const colorByAge = colorByAgeEnabled() && finite(age) && Number(age) > 0;
    const marker = colorByAge ? {
      color: aidRows.map(() => Math.log10(Number(age))),
      cmin: 0,
      cmax: 3.2,
      colorscale: xuvAgeColorscale,
      showscale: !ageScaleShown,
      colorbar: !ageScaleShown ? xuvAgeColorbar() : undefined,
      size: 3.4,
      opacity: 1,
      line: { width: 0 },
    } : {
      color: colorByAgeEnabled() ? xuvNoAgeColor : (colormap[aid] || "#555"),
      size: 3.4,
      opacity: 1,
      line: { width: 0 },
    };
    if (colorByAge) ageScaleShown = true;
    traces.push({
      type: "scatter3d",
      mode: "markers",
      name: colorByAgeEnabled() ? ageLegendName(aid, age) : aid,
      legendgroup: aid,
      showlegend: true,
      x: aidRows.map((row) => row.plot0),
      y: aidRows.map((row) => row.plot1),
      z: aidRows.map((row) => row.plot2),
      customdata: aidRows,
      text: aidRows.map(hoverTextForRow),
      hoverinfo,
      marker,
    });
  });
  return traces;
}

function associationCenterLabelTraces(rows, colormap, ranges, showAxes) {
  const rowsByAid = new Map();
  rows.forEach((row) => {
    const aid = String(row.moca_aid || "Unassigned");
    if (!rowsByAid.has(aid)) rowsByAid.set(aid, []);
    rowsByAid.get(aid).push(row);
  });
  const verticalOffset = associationLabelVerticalOffset(ranges);
  const fontSize = xyzuvwSunFontSize(showAxes);
  return [...rowsByAid.entries()].map(([aid, aidRows]) => {
    const center = [0, 1, 2].map((index) => robustMedian(aidRows.map((row) => row[`plot${index}`]).filter(finite).map(Number)));
    center[2] += verticalOffset;
    return {
      type: "scatter3d",
      mode: "text",
      name: `${aid} label`,
      legendgroup: aid,
      showlegend: false,
      x: [center[0]],
      y: [center[1]],
      z: [center[2]],
      text: [aid],
      textposition: "middle center",
      textfont: { color: colormap[aid] || "#555", size: fontSize },
      hoverinfo: "skip",
    };
  }).filter((trace) => trace.x.every(finite) && trace.y.every(finite) && trace.z.every(finite));
}

function associationLabelVerticalOffset(ranges) {
  const range = ranges?.[2];
  if (!Array.isArray(range) || !finite(range[0]) || !finite(range[1])) return 0;
  return Math.max(0, Number(range[1]) - Number(range[0])) * 0.035;
}

function xyzuvwSunFontSize(showAxes) {
  return showAxes ? 12 : 9;
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

function modelTraces(axes, colormap, payload = xuvState.payload) {
  const surfaceRows = payload?.modelSurfaces || payload?.model_surfaces || [];
  if (surfaceRows.length) {
    const visibleModelLegends = new Set();
    return surfaceRows.map((surface) => {
      const aid = surface.moca_aid || "model";
      const color = colormap[aid] || "#555";
      const showlegend = !visibleModelLegends.has(aid);
      visibleModelLegends.add(aid);
      return {
        type: "mesh3d",
        name: `${aid} model`,
        legendgroup: `${aid}-model`,
        showlegend,
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
  for (const model of payload?.models || []) {
    const aid = model.moca_aid;
    if (!aid) continue;
    if (!modelsByAid.has(aid)) modelsByAid.set(aid, []);
    modelsByAid.get(aid).push(model);
  }
  for (const [aid, models] of modelsByAid.entries()) {
    const color = colormap[aid] || "#555";
    const grid = gmmDensityGrid(models, axes);
    if (!grid) continue;
    let hasModelLegend = false;
    for (const level of levels) {
      const threshold = densityThreshold(grid.values, level.contour);
      if (!finite(threshold) || threshold <= 0 || threshold >= grid.maxValue) continue;
      const showlegend = !hasModelLegend;
      hasModelLegend = true;
      traces.push({
        type: "isosurface",
        name: `${aid} model`,
        legendgroup: `${aid}-model`,
        showlegend,
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

function labelTraces(axes, colormap, excludeAids = new Set(), showAxes = false, payload = xuvState.payload) {
  const labels = payload?.labels || [];
  if (!labels.length) return [];
  const rows = labels.map((row) => ({
    ...row,
    plot0: Number(row[axes[0]]),
    plot1: Number(row[axes[1]]),
    plot2: Number(row[axes[2]]),
  })).filter((row) => (
    finite(row.plot0)
    && finite(row.plot1)
    && finite(row.plot2)
    && !excludeAids.has(String(row.moca_aid || "Unassigned"))
  ));
  if (!rows.length) return [];
  return [{
    type: "scatter3d",
    mode: "text",
    name: "Association labels",
    x: rows.map((row) => row.plot0),
    y: rows.map((row) => row.plot1),
    z: rows.map((row) => row.plot2),
    text: rows.map((row) => row.moca_aid),
    textfont: { color: rows.map((row) => colormap[row.moca_aid] || "#555"), size: xyzuvwSunFontSize(showAxes) },
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

function cleanReferenceContext(axes, rows, traces) {
  const plane = cleanReferencePlaneSpec(axes);
  if (!plane) return { plane: null, radius: 0, majorRadii: [], minorRadii: [] };
  const radius = plane.dynamicRadius ? cleanReferenceRadius(axes, rows, traces, plane) : plane.fallbackRadius;
  return {
    plane,
    radius,
    majorRadii: plane.majorRadii.filter((value) => referencePlanePlotRadius(plane, value) <= radius + 1e-9),
    minorRadii: cleanMinorReferenceRadii(plane, radius),
  };
}

function cleanReferencePlaneSpec(axes) {
  if (axes.includes("x") && axes.includes("y")) {
    return {
      kind: "spatial",
      axes: ["x", "y"],
      labels: ["X", "Y"],
      unit: "pc",
      radiusScale: 1,
      majorRadii: xuvCleanReferenceRadii,
      fallbackRadius: Math.max(...xuvCleanReferenceRadii),
      dynamicRadius: true,
    };
  }
  if (axes.includes("u") && axes.includes("v")) {
    return {
      kind: "velocity",
      axes: ["u", "v"],
      labels: ["U", "V"],
      unit: "km/s",
      radiusScale: velocityReferenceScale(),
      majorRadii: xuvCleanVelocityReferenceRadii,
      fallbackRadius: Math.max(...xuvCleanVelocityReferenceRadii) * velocityReferenceScale(),
      dynamicRadius: true,
    };
  }
  return null;
}

function velocityReferenceScale() {
  const scale = Number(xuvState.cValue);
  return finite(scale) && scale > 0 ? scale : 1;
}

function cleanReferenceRadius(axes, rows, traces, plane) {
  let radius = 0;
  rows.forEach((row) => {
    radius = Math.max(radius, referenceRadiusFromRow(row, axes, plane));
  });
  traces.forEach((trace) => {
    radius = Math.max(radius, referenceRadiusFromTrace(trace, axes, plane));
  });
  const minRadius = referencePlanePlotRadius(plane, plane.majorRadii[0] || 10);
  return finite(radius) && radius > 0 ? Math.max(minRadius, radius) : plane.fallbackRadius;
}

function cleanMinorReferenceRadii(plane, radius) {
  if (!plane) return [];
  if (plane.kind === "velocity") return cleanVelocityMinorReferenceRadii(plane, radius);
  const majorRadii = new Set(plane.majorRadii);
  const maxMinor = Math.floor((Number(radius) + 1e-9) / 100) * 100;
  const radii = [];
  for (let value = 200; value <= maxMinor; value += 100) {
    if (!majorRadii.has(value)) radii.push(value);
  }
  return radii;
}

function cleanVelocityMinorReferenceRadii(plane, radius) {
  const majorRadii = new Set(plane.majorRadii);
  const maxMajor = Math.max(...plane.majorRadii);
  const maxVelocity = Math.min(maxMajor, Math.floor((Number(radius) / referencePlanePlotRadius(plane, 1) + 1e-9) / 10) * 10);
  const radii = [];
  for (let value = 10; value <= maxVelocity; value += 10) {
    if (!majorRadii.has(value)) radii.push(value);
  }
  return radii;
}

function spatialRadiusFromRow(row, axes) {
  const values = ["x", "y", "z"].map((axis) => {
    const plotIndex = axes.indexOf(axis);
    if (plotIndex >= 0) return row[`plot${plotIndex}`];
    return row[axis];
  }).filter(finite).map(Number);
  return values.length ? Math.hypot(...values) : 0;
}

function spatialRadiusFromTrace(trace, axes) {
  if (!trace || !trace.x || !trace.y || !trace.z) return 0;
  const arrays = [trace.x, trace.y, trace.z];
  const length = Math.min(arrays[0].length || 0, arrays[1].length || 0, arrays[2].length || 0);
  let radius = 0;
  for (let index = 0; index < length; index += 1) {
    const values = [];
    axes.forEach((axis, axisIndex) => {
      if (["x", "y", "z"].includes(axis) && finite(arrays[axisIndex][index])) {
        values.push(Number(arrays[axisIndex][index]));
      }
    });
    if (values.length) radius = Math.max(radius, Math.hypot(...values));
  }
  return radius;
}

function referenceRadiusFromRow(row, axes, plane) {
  if (!plane) return 0;
  if (plane.kind === "spatial") return spatialRadiusFromRow(row, axes);
  const values = plane.axes.map((axis) => {
    const plotIndex = axes.indexOf(axis);
    if (plotIndex >= 0) return row[`plot${plotIndex}`];
    return row[axis];
  }).filter(finite).map(Number);
  return values.length ? Math.hypot(...values) : 0;
}

function referenceRadiusFromTrace(trace, axes, plane) {
  if (!plane) return 0;
  if (plane.kind === "spatial") return spatialRadiusFromTrace(trace, axes);
  if (!trace || !trace.x || !trace.y || !trace.z) return 0;
  const arrays = [trace.x, trace.y, trace.z];
  const length = Math.min(arrays[0].length || 0, arrays[1].length || 0, arrays[2].length || 0);
  let radius = 0;
  for (let index = 0; index < length; index += 1) {
    const values = [];
    axes.forEach((axis, axisIndex) => {
      if (plane.axes.includes(axis) && finite(arrays[axisIndex][index])) {
        values.push(Number(arrays[axisIndex][index]));
      }
    });
    if (values.length) radius = Math.max(radius, Math.hypot(...values));
  }
  return radius;
}

function referencePlanePlotRadius(plane, radius) {
  const scale = finite(plane?.radiusScale) ? Number(plane.radiusScale) : 1;
  return Number(radius) * scale;
}

function referenceTraces(axes, showAxes, referenceContext = null) {
  const context = referenceContext || cleanReferenceContext(axes, [], []);
  const traces = [];
  if (!showAxes && context.plane) traces.push(...xyPlaneReferencePlaneTraces(axes, context));
  traces.push({
    type: "scatter3d",
    mode: "markers+text",
    name: "Sun",
    x: [0],
    y: [0],
    z: [0],
    text: ["Sun"],
    textposition: "top center",
    textfont: { color: showAxes ? "#111111" : xuvCleanCircleColor, size: xyzuvwSunFontSize(showAxes) },
    marker: { color: showAxes ? "#111111" : xuvCleanCircleColor, size: 5, symbol: "cross" },
    showlegend: false,
    hoverinfo: "skip",
  });
  const hasSpatialOnly = axes.every((axis) => ["x", "y", "z"].includes(axis));
  if (showAxes) {
    if (hasSpatialOnly) traces.push(...xyPlaneCircleTraces(axes, [25], "rgba(0,0,0,0.35)", 2));
  } else {
    if (context.plane) {
      traces.push(...xyPlaneAxisGuideTraces(axes, context));
      traces.push(...xyPlaneCircleTraces(axes, context.minorRadii, xuvCleanMinorReferenceColor, 1, { labelRadii: false, showlegend: false, plane: context.plane }));
      traces.push(...xyPlaneCircleTraces(axes, context.majorRadii, xuvCleanReferenceColor, 4, { labelRadii: true, showlegend: false, plane: context.plane }));
    }
  }
  return traces;
}

function xyPlaneAxisGuideTraces(axes, context) {
  const { plane, radius } = context;
  if (!plane) return [];
  const axisGuides = plane.axes.map((axis, index) => ({ axis, label: plane.labels[index] }));
  const verticalAxis = axes.find((axis) => !plane.axes.includes(axis));
  if (verticalAxis) axisGuides.push({ axis: verticalAxis, label: verticalAxis.toUpperCase() });
  return axisGuides.map((guide) => {
    const coordinates = axes.map((axis) => {
      if (axis === guide.axis) return [0, radius];
      return [0, 0];
    });
    return {
      type: "scatter3d",
      mode: "lines+text",
      name: `${guide.label} guide`,
      showlegend: false,
      x: coordinates[0],
      y: coordinates[1],
      z: coordinates[2],
      text: ["", guide.label],
      textposition: "top center",
      textfont: { color: xuvCleanReferenceColor, size: 13 },
      line: { color: xuvCleanReferenceColor, width: 2 },
      hoverinfo: "skip",
    };
  });
}

function xyPlaneReferencePlaneTraces(axes, context) {
  const { plane, radius } = context;
  if (!plane || !plane.axes.every((axis) => axes.includes(axis))) return [];
  const segments = 144;
  const disk = [null];
  for (let index = 0; index < segments; index += 1) {
    const angle = 2 * Math.PI * index / segments;
    disk.push(angle);
  }
  const coordinates = axes.map((axis) => disk.map((angle) => {
    if (angle === null) return 0;
    return referencePlaneCoordinate(axis, plane, radius, angle);
  }));
  const triangles = Array.from({ length: segments }, (_value, index) => ({
    i: 0,
    j: index + 1,
    k: index === segments - 1 ? 1 : index + 2,
  }));
  return [{
    type: "mesh3d",
    name: `${plane.labels.join("")} plane`,
    showlegend: false,
    x: coordinates[0],
    y: coordinates[1],
    z: coordinates[2],
    i: triangles.map((triangle) => triangle.i),
    j: triangles.map((triangle) => triangle.j),
    k: triangles.map((triangle) => triangle.k),
    color: xuvCleanPlaneColor,
    opacity: 0.12,
    flatshading: true,
    hoverinfo: "skip",
  }];
}

function xyPlaneCircleTraces(axes, radii, color, width, options = {}) {
  const plane = options.plane || cleanReferencePlaneSpec(axes);
  if (!plane || !plane.axes.every((axis) => axes.includes(axis)) || !radii.length) return [];
  const labelRadii = options.labelRadii ?? radii.length > 1;
  const circle = Array.from({ length: 145 }, (_value, index) => 2 * Math.PI * index / 144);
  const traces = radii.map((radius) => {
    const plotRadius = referencePlanePlotRadius(plane, radius);
    const coordinates = axes.map((axis) => circle.map((angle) => referencePlaneCoordinate(axis, plane, plotRadius, angle)));
    return {
      type: "scatter3d",
      mode: "lines",
      name: `${radius} ${plane.unit}`,
      x: coordinates[0],
      y: coordinates[1],
      z: coordinates[2],
      line: { color, width },
      showlegend: options.showlegend ?? radii.length === 1,
      opacity: options.opacity ?? 1,
      hoverinfo: "skip",
    };
  });
  if (labelRadii) traces.push(xyPlaneCircleLabelTrace(axes, radii, color, plane));
  return traces;
}

function xyPlaneCircleLabelTrace(axes, radii, color, plane) {
  const labelAngle = -Math.PI / 2;
  const coordinates = axes.map((axis) => radii.map((radius) => referencePlaneCoordinate(axis, plane, referencePlanePlotRadius(plane, radius), labelAngle)));
  return {
    type: "scatter3d",
    mode: "text",
    name: "Reference radius labels",
    showlegend: false,
    x: coordinates[0],
    y: coordinates[1],
    z: coordinates[2],
    text: radii.map((radius) => `${radius} ${plane.unit}`),
    textposition: "bottom center",
    textfont: { color, size: 9 },
    hoverinfo: "skip",
  };
}

function referencePlaneCoordinate(axis, plane, radius, angle) {
  if (axis === plane.axes[0]) return radius * Math.cos(angle);
  if (axis === plane.axes[1]) return radius * Math.sin(angle);
  return 0;
}

function xyzuvwLayout(axes, rows, ranges = null, showAxes = true, panelKey = "main") {
  const axisRanges = ranges || xyzuvwRanges(axes, rows, showAxes, cleanReferenceContext(axes, rows, []));
  const axisTitles = axes.map((axis) => `${axis.toUpperCase()} (${axisUnit(axis)})`);
  const backgroundColor = showAxes ? "#eeeeef" : xuvCleanSceneBackground;
  const annotations = showAxes ? cleanAxesWatermarkAnnotations(axes) : [];
  const camera = xuvDualMode
    ? (xuvState.panelCameras[panelKey] || xuvDefaultCamera)
    : (xuvState.camera || xuvDefaultCamera);
  return {
    uirevision: `xyzuvw-view-${panelKey}`,
    paper_bgcolor: backgroundColor,
    plot_bgcolor: showAxes ? "#ffffff" : backgroundColor,
    margin: showAxes ? { l: 18, r: 18, t: 18, b: 18 } : { l: 0, r: 0, t: 0, b: 0 },
    hovermode: "closest",
    legend: {
      orientation: "h",
      yanchor: "bottom",
      y: 0,
      xanchor: "right",
      x: 1,
      bgcolor: showAxes ? "rgba(238,238,239,0.86)" : "rgba(8,9,12,0.72)",
      font: showAxes ? { size: 12 } : { size: 12, color: "#e8edf4" },
      groupclick: "togglegroup",
    },
    scene: {
      uirevision: `xyzuvw-scene-${panelKey}`,
      bgcolor: showAxes ? "#ffffff" : backgroundColor,
      xaxis: showAxes ? sceneAxis(axisTitles[0], axisRanges[0]) : cleanSceneAxis(axisRanges[0]),
      yaxis: showAxes ? sceneAxis(axisTitles[1], axisRanges[1]) : cleanSceneAxis(axisRanges[1]),
      zaxis: showAxes ? sceneAxis(axisTitles[2], axisRanges[2]) : cleanSceneAxis(axisRanges[2]),
      aspectmode: "manual",
      aspectratio: xyzuvwAspectRatio(axisRanges),
      camera,
    },
    annotations,
  };
}

function xyzuvwAspectRatio(axisRanges) {
  const spans = [0, 1, 2].map((index) => {
    const range = axisRanges?.[index];
    const span = Array.isArray(range) ? Math.abs(Number(range[1]) - Number(range[0])) : NaN;
    return finite(span) && span > 0 ? span : 1;
  });
  spans[2] *= xuvVerticalAspectScale;
  const normalizer = Math.max(...spans, 1);
  return {
    x: spans[0] / normalizer,
    y: spans[1] / normalizer,
    z: spans[2] / normalizer,
  };
}

function cleanAxesWatermarkAnnotations(axes) {
  return [
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
  ];
}

function sceneAxis(title, range) {
  return {
    title: { text: title, font: { size: 18, color: "#111111" } },
    titlefont: { size: 18, color: "#111111" },
    range,
    showspikes: false,
    visible: true,
    showbackground: true,
    backgroundcolor: "#ffffff",
    showgrid: true,
    gridcolor: "#e5e5e5",
    zeroline: true,
    zerolinecolor: "#bdbdbd",
    showline: true,
    linecolor: "#111111",
    linewidth: 4,
    showticklabels: true,
    ticks: "outside",
    tickcolor: "#111111",
    tickfont: { size: 11, color: "#111111" },
  };
}

function cleanSceneAxis(range) {
  return {
    range,
    visible: false,
    showbackground: false,
    showgrid: false,
    zeroline: false,
    showline: false,
    showspikes: false,
    showticklabels: false,
    ticks: "",
    title: { text: "" },
  };
}

function xyzuvwRanges(axes, rows, showAxes, referenceContext = null) {
  const ranges = cubicRange(rows);
  return showAxes ? ranges : expandRangesForCleanReferences(axes, ranges, referenceContext);
}

function expandRangesForCleanReferences(axes, ranges, referenceContext = null) {
  const plane = referenceContext?.plane || cleanReferencePlaneSpec(axes);
  if (!plane) return ranges;
  const maxRadius = referenceContext?.radius || plane.fallbackRadius;
  return ranges.map((range, index) => {
    const axis = axes[index];
    if (plane.axes.includes(axis)) return [Math.min(range[0], -maxRadius), Math.max(range[1], maxRadius)];
    return [Math.min(range[0], 0), Math.max(range[1], 0)];
  });
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

function selectXyzuvwPlotRows(rows) {
  xuvState.selectedRows = (rows || []).filter((row) => row && normalizedMocaOid(row.moca_oid));
  renderXyzuvwTable();
}

function bindXyzuvwPlotEvents(plotEl = xuvEl["xuv-plot"], panelKey = "main", axes = selectedAxes()) {
  if (!plotEl || plotEl.dataset.bound === "1" || typeof plotEl.on !== "function") return;
  plotEl.dataset.bound = "1";
  plotEl.on("plotly_click", (event) => {
    selectXyzuvwPlotRows((event?.points || []).map((point) => point.customdata));
  });
  plotEl.on("plotly_selected", (event) => {
    selectXyzuvwPlotRows((event?.points || []).map((point) => point.customdata));
  });
  plotEl.on("plotly_deselect", () => {
    xuvState.selectedRows = [];
    renderXyzuvwTable();
  });
  plotEl.on("plotly_relayout", (event) => {
    updateXyzuvwCamera(event, panelKey);
  });
  plotEl.on("plotly_legendclick", () => {
    preserveXyzuvwCameraAfterLegendToggle(plotEl, panelKey);
  });
  plotEl.on("plotly_legenddoubleclick", () => {
    preserveXyzuvwCameraAfterLegendToggle(plotEl, panelKey);
  });
  plotEl.on("plotly_restyle", () => {
    restorePendingXyzuvwCamera();
  });
  plotEl.dataset.axes = axes.join("");
}

function updateXyzuvwCamera(event, panelKey = "main") {
  const directCamera = event?.["scene.camera"];
  if (directCamera && typeof directCamera === "object") {
    setStoredXyzuvwCamera(panelKey, directCamera);
    return;
  }
  const current = clonePlainObject(storedXyzuvwCamera(panelKey));
  let changed = false;
  Object.entries(event || {}).forEach(([key, value]) => {
    if (!key.startsWith("scene.camera.")) return;
    const path = key.replace("scene.camera.", "").split(".");
    let target = current;
    for (let index = 0; index < path.length - 1; index += 1) {
      const part = path[index];
      if (!target[part] || typeof target[part] !== "object") target[part] = {};
      target = target[part];
    }
    target[path[path.length - 1]] = value;
    changed = true;
  });
  if (changed) setStoredXyzuvwCamera(panelKey, current);
}

function preserveXyzuvwCameraAfterLegendToggle(plotEl = xuvEl["xuv-plot"], panelKey = "main") {
  const camera = currentXyzuvwCamera(plotEl, panelKey);
  if (!camera) return;
  setStoredXyzuvwCamera(panelKey, camera);
  xuvState.pendingCameraRestore = { panelKey, camera: clonePlainObject(camera) };
  window.setTimeout(restorePendingXyzuvwCamera, 0);
  window.setTimeout(restorePendingXyzuvwCamera, 80);
  window.setTimeout(() => {
    xuvState.pendingCameraRestore = null;
  }, 250);
}

function restorePendingXyzuvwCamera() {
  const pending = xuvState.pendingCameraRestore;
  if (!pending || typeof Plotly?.relayout !== "function") return;
  const plotEl = plotForXyzuvwPanel(pending.panelKey);
  if (!plotEl) return;
  Plotly.relayout(plotEl, { "scene.camera": pending.camera });
  setStoredXyzuvwCamera(pending.panelKey, pending.camera);
}

function currentXyzuvwCamera(plotEl = xuvEl["xuv-plot"], panelKey = "main") {
  const camera = plotEl?._fullLayout?.scene?.camera || plotEl?.layout?.scene?.camera || storedXyzuvwCamera(panelKey);
  return camera ? clonePlainObject(camera) : null;
}

function storedXyzuvwCamera(panelKey = "main") {
  return xuvDualMode ? (xuvState.panelCameras[panelKey] || xuvDefaultCamera) : (xuvState.camera || xuvDefaultCamera);
}

function setStoredXyzuvwCamera(panelKey = "main", camera = xuvDefaultCamera) {
  const cleanCamera = clonePlainObject(camera);
  if (xuvDualMode) xuvState.panelCameras[panelKey] = cleanCamera;
  else xuvState.camera = cleanCamera;
}

function plotForXyzuvwPanel(panelKey = "main") {
  if (!xuvDualMode || panelKey === "main") return xuvEl["xuv-plot"];
  const panel = xuvDualPanels.find((candidate) => candidate.key === panelKey);
  return panel ? xuvEl[panel.plotId] : null;
}

function clonePlainObject(value) {
  return JSON.parse(JSON.stringify(value || {}));
}

function renderXyzuvwTable() {
  const rows = xuvState.selectedRows.length ? xuvState.selectedRows : xuvState.displayedRows.slice(0, 500);
  xuvEl["xuv-table-title"].textContent = xuvState.selectedRows.length ? `${xuvState.selectedRows.length} selected objects` : "Displayed objects";
  xuvEl["xuv-table-subtitle"].textContent = xuvState.selectedRows.length ? "Click Open selected report for a single selected object." : "Showing the first 500 displayed rows.";
  xuvEl["xuv-open-report"].disabled = xuvState.selectedRows.length !== 1 || !mocaReportUrl(xuvState.selectedRows[0]?.moca_oid);
  if (!rows.length) {
    xuvEl["xuv-table"].innerHTML = `<div class="selection-table">No objects to display.</div>`;
    return;
  }
  const axes = xuvDualMode ? ["x", "y", "z", "u", "v", "w"] : selectedAxes();
  const columns = ["moca_oid", "designation", "moca_aid", "moca_mtid", "spt", ...axes, "ya_prob", "age_myr", "report"];
  const tableRows = rows.map((row) => {
    const reportUrl = mocaReportUrl(row.moca_oid);
    const out = {
      moca_oid: normalizedMocaOid(row.moca_oid),
      designation: row.designation || "",
      moca_aid: row.moca_aid || "",
      moca_mtid: row.moca_mtid || "",
      spt: row.spt || "",
      ya_prob: finite(row.ya_prob) ? formatNumber(row.ya_prob, 1) : "",
      age_myr: finite(row.age_myr) ? formatNumber(row.age_myr, 1) : "",
      report: reportUrl ? `<a class="report-link" href="${reportUrl}" target="_blank" rel="noopener">Report</a>` : "",
    };
    axes.forEach((axis, index) => {
      out[axis] = formatNumber(tableAxisValue(row, axis, index), 2);
    });
    return out;
  });
  xuvEl["xuv-table"].innerHTML = tableHtml(columns, tableRows, { htmlColumns: new Set(["report"]) });
}

function tableAxisValue(row, axis, index) {
  if (!xuvDualMode && finite(row[`plot${index}`])) return row[`plot${index}`];
  return rowValue(row, axis, xuvEl["xuv-assmem"].checked);
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
  if (xuvDualMode) {
    xuvDualPanels.forEach((panel) => {
      const panelLayout = {
        ...layout,
        annotations: [{ ...layout.annotations[0], text: `${panel.label}: ${message}` }],
      };
      if (xuvEl[panel.plotId]) Plotly.react(xuvEl[panel.plotId], [], panelLayout, plotConfig(`mocadb_xyz2_${panel.key}_empty`));
    });
  } else {
    Plotly.react(xuvEl["xuv-plot"], [], layout, plotConfig("mocadb_xyzuvw_empty"));
  }
  xuvEl["xuv-summary"].textContent = message;
  xuvEl["xuv-table"].innerHTML = "";
  setXyzuvwExportDisabled(true);
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
    `Age: ${finite(row.age_myr) ? `${formatNumber(row.age_myr, 1)} Myr` : "N/A"}`,
  ].join("<br>");
}

function selectedAxes() {
  if (xuvDualMode) return ["x", "y", "z"];
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

function xyzuvwAssociationColors(payloads = [], rows = []) {
  const aids = [
    ...xuvState.selectedAids,
    ...(rows || []).map((row) => String(row.moca_aid || "Unassigned")),
  ];
  for (const payload of payloads || []) {
    aids.push(...(payload?.members || []).map((row) => String(row.moca_aid || "Unassigned")));
    aids.push(...(payload?.models || []).map((row) => String(row.moca_aid || "model")));
    aids.push(...(payload?.modelSurfaces || payload?.model_surfaces || []).map((row) => String(row.moca_aid || "model")));
  }
  const uniqueAids = [...new Set(aids.filter(Boolean))];
  if (!colorByAgeEnabled()) return associationColors(uniqueAids);

  const ages = associationAgeMap(payloads, rows);
  const out = {};
  uniqueAids.forEach((aid) => {
    out[aid] = ageColorForAge(ages.get(String(aid)));
  });
  return out;
}

function associationAgeMap(payloads = [], rows = []) {
  const ages = new Map();
  const add = (row) => {
    const aid = String(row?.moca_aid || "");
    const age = Number(row?.age_myr);
    if (aid && finite(age) && age > 0 && !ages.has(aid)) ages.set(aid, age);
  };
  (rows || []).forEach(add);
  for (const payload of payloads || []) {
    (payload?.members || []).forEach(add);
    (payload?.models || []).forEach(add);
    (payload?.modelSurfaces || payload?.model_surfaces || []).forEach(add);
  }
  return ages;
}

function ageForRows(rows) {
  const row = (rows || []).find((candidate) => finite(candidate?.age_myr) && Number(candidate.age_myr) > 0);
  return row ? Number(row.age_myr) : null;
}

function colorByAgeEnabled() {
  return Boolean(xuvEl["xuv-color-age"]?.checked);
}

function ageColorForAge(age) {
  const numeric = Number(age);
  if (!finite(numeric) || numeric <= 0) return xuvNoAgeColor;
  const t = Math.max(0, Math.min(1, Math.log10(numeric) / 3.2));
  for (let index = 1; index < xuvAgeColorscale.length; index += 1) {
    const [rightStop, rightColor] = xuvAgeColorscale[index];
    const [leftStop, leftColor] = xuvAgeColorscale[index - 1];
    if (t <= rightStop) {
      const span = Math.max(rightStop - leftStop, 1e-9);
      return interpolateRgb(leftColor, rightColor, (t - leftStop) / span);
    }
  }
  return xuvAgeColorscale[xuvAgeColorscale.length - 1][1];
}

function ageLegendName(aid, age) {
  return finite(age) && Number(age) > 0 ? `${aid} (${formatNumber(age, 1)} Myr)` : `${aid} (no age)`;
}

function xuvAgeColorbar() {
  return {
    title: { text: "Age", font: { size: 13 } },
    x: 1.04,
    xanchor: "left",
    y: 0.5,
    yanchor: "middle",
    len: 0.72,
    thickness: 18,
    outlinecolor: "#111111",
    outlinewidth: 2,
    ticks: "outside",
    tickvals: [0, 1, 2, 3],
    ticktext: ["1 Myr", "10 Myr", "100 Myr", "1 Gyr"],
  };
}

function interpolateRgb(left, right, fraction) {
  const a = parseRgb(left);
  const b = parseRgb(right);
  if (!a || !b) return right;
  const f = Math.max(0, Math.min(1, fraction));
  const values = a.map((value, index) => Math.round(value + (b[index] - value) * f));
  return `rgb(${values[0]},${values[1]},${values[2]})`;
}

function parseRgb(value) {
  const match = String(value || "").match(/rgb\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)/i);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

function buildXyzuvwParams(axesOverride = null) {
  const params = apiParams();
  const axes = axesOverride || selectedAxes();
  params.set("axes", axes.join(""));
  params.set("asso", xuvState.selectedAids.join(","));
  params.set("mtid", xuvState.selectedMtids.join(","));
  if (xuvState.selectedOids.length) params.set("oid", xuvState.selectedOids.join(","));
  params.set("bsmdid", xuvEl["xuv-bsmdid"].value || "latest");
  const checkbox = checkboxValues();
  if (checkbox.length) params.set("checkbox", checkbox.join(","));
  if (!xuvEl["xuv-likely"].checked) params.set("likely", "0");
  return params;
}

function checkboxValues() {
  const out = [];
  if (xuvEl["xuv-models"].checked) out.push("models");
  if (xuvEl["xuv-errors"].checked) out.push("errors");
  if (xuvEl["xuv-assmem"].checked) out.push("assmem");
  if (xuvEl["xuv-hover"].checked) out.push("hover");
  if (xuvEl["xuv-likely"].checked) out.push("likely");
  if (xuvEl["xuv-subgroups"].checked) out.push("subgroups");
  if (xuvEl["xuv-color-age"].checked) out.push("agecolor");
  if (xuvEl["xuv-asscen"].checked) out.push("asscen");
  return out;
}

function updateXyzuvwUrl() {
  const params = new URLSearchParams(window.location.search);
  if (xuvDualMode) params.delete("axes");
  else params.set("axes", selectedAxes().join(""));
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
  if (xuvEl["xuv-show-axes"].checked) params.set("showaxes", "1");
  else params.delete("showaxes");
  const checkbox = checkboxValues();
  if (checkbox.length) params.set("checkbox", checkbox.join(","));
  else params.delete("checkbox");
  for (const key of ["models", "errors", "assmem", "hover", "asscen", "subgroups", "agecolor", "color_age", "color_by_age", "age_color"]) params.delete(key);
  if (xuvEl["xuv-likely"].checked) params.delete("likely");
  else params.set("likely", "0");
  window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}

const xyzuvwNumericExportColumns = new Set(["moca_oid", "x", "y", "z", "u", "v", "w", "ya_prob", "age_myr", "dr3_ruwe"]);

function exportXyzuvw(format) {
  const rows = xuvState.selectedRows.length ? xuvState.selectedRows : xuvState.displayedRows;
  if (!rows.length) return;
  const axes = xuvDualMode ? ["x", "y", "z", "u", "v", "w"] : selectedAxes();
  const columns = ["moca_oid", "designation", "moca_aid", "moca_mtid", "spt", ...axes, "ya_prob", "age_myr", "dr3_ruwe"];
  const exportRows = rows.map((row) => {
    const out = {
      moca_oid: normalizedMocaOid(row.moca_oid),
      designation: row.designation || "",
      moca_aid: row.moca_aid || "",
      moca_mtid: row.moca_mtid || "",
      spt: row.spt || "",
      ya_prob: row.ya_prob ?? "",
      age_myr: row.age_myr ?? "",
      dr3_ruwe: row.dr3_ruwe ?? "",
    };
    axes.forEach((axis, index) => {
      out[axis] = tableAxisValue(row, axis, index);
    });
    return out;
  });
  MocaExport.saveTable(format, {
    rows: exportRows,
    columns,
    numericColumns: xyzuvwNumericExportColumns,
    filenameBase: "mocadb_xyzuvw_fast",
    tableName: "mocadb_xyzuvw_fast",
    resourceName: "MOCAdb Spatial-Kinematic Explorer",
    extName: "XYZUVW",
  });
}

async function downloadFrozenXyzuvwPlotlyScene() {
  if (!xuvState.displayedRows.length) return;
  const button = xuvEl["xuv-download-frozen"];
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Preparing standalone HTML...";
  try {
    const snapshot = buildFrozenPlotlySceneSnapshot();
    const html = await buildFrozenPlotlyStandaloneHtml(snapshot);
    MocaExport.downloadBlob(html, `${snapshot.slug}.html`, "text/html;charset=utf-8");
  } catch (error) {
    console.error(error);
    setXyzuvwStatus(`Frozen scene export failed: ${error.message}`, "error");
  } finally {
    button.textContent = originalText;
    setXyzuvwExportDisabled(xuvState.displayedRows.length === 0);
  }
}

function buildFrozenPlotlySceneSnapshot() {
  const slug = `mocadb_${xuvDualMode ? "xyz_dual_plotly" : "xyz_plotly"}_frozen_scene_${frozenDateStamp()}`;
  return jsonClean({
    version: 1,
    renderer: "plotly",
    title: xuvDualMode ? "MOCAdb Plotly Dual XYZ/UVW Frozen Scene" : "MOCAdb Plotly Spatial-Kinematic Frozen Scene",
    slug,
    exportedAt: new Date().toISOString(),
    dual: xuvDualMode,
    assumeMembership: Boolean(xuvEl["xuv-assmem"].checked),
    selectedOid: xuvState.selectedRows.length === 1 ? normalizedMocaOid(xuvState.selectedRows[0]?.moca_oid) : "",
    summaryText: xuvEl["xuv-summary"]?.textContent || "",
    hintHtml: xuvEl["xuv-hint"]?.innerHTML || "",
    table: buildFrozenPlotlyTableSnapshot(),
    panels: frozenPlotlyPanelSnapshots(),
  });
}

function frozenPlotlyPanelSnapshots() {
  if (xuvDualMode) {
    return xuvDualPanels.map((panel) => buildFrozenPlotlyPanelSnapshot(
      panel.key,
      panel.label,
      panel.axes,
      xuvEl[panel.plotId],
      `mocadb_${panel.key}_plotly_frozen`,
    )).filter(Boolean);
  }
  return [buildFrozenPlotlyPanelSnapshot("main", selectedAxes().map((axis) => axis.toUpperCase()).join(""), selectedAxes(), xuvEl["xuv-plot"], "mocadb_xyz_plotly_frozen")].filter(Boolean);
}

function buildFrozenPlotlyPanelSnapshot(key, label, axes, plotEl, filename) {
  if (!plotEl?.data?.length) return null;
  const layout = clonePlainObject(plotEl.layout || {});
  const camera = currentXyzuvwCamera(plotEl, key);
  if (camera) layout.scene = { ...(layout.scene || {}), camera };
  layout.autosize = true;
  return {
    key,
    label,
    axes,
    data: clonePlainObject(plotEl.data || []),
    layout,
    config: plotConfig(filename),
  };
}

function buildFrozenPlotlyTableSnapshot() {
  const axes = xuvDualMode ? ["x", "y", "z", "u", "v", "w"] : selectedAxes();
  const sourceRows = xuvState.selectedRows.length ? xuvState.selectedRows : xuvState.displayedRows.slice(0, 500);
  const columns = ["moca_oid", "designation", "moca_aid", "moca_mtid", "spt", ...axes, "ya_prob", "age_myr", "report"];
  return {
    title: xuvState.selectedRows.length ? `${xuvState.selectedRows.length} selected objects` : "Displayed objects",
    subtitle: xuvState.selectedRows.length ? "Frozen selected object table." : "Showing the first 500 displayed rows from the exported scene.",
    axes,
    columns,
    rows: sourceRows.map((row) => frozenPlotlyTableRow(row, axes)),
  };
}

function frozenPlotlyTableRow(row, axes) {
  const reportUrl = mocaReportUrl(row.moca_oid);
  const out = {
    moca_oid: normalizedMocaOid(row.moca_oid),
    designation: row.designation || "",
    moca_aid: row.moca_aid || "",
    moca_mtid: row.moca_mtid || "",
    spt: row.spt || "",
    ya_prob: finite(row.ya_prob) ? formatNumber(row.ya_prob, 1) : "",
    age_myr: finite(row.age_myr) ? formatNumber(row.age_myr, 1) : "",
    report: reportUrl,
  };
  axes.forEach((axis, index) => {
    out[axis] = formatNumber(tableAxisValue(row, axis, index), 2);
  });
  return out;
}

async function buildFrozenPlotlyStandaloneHtml(snapshot) {
  const [styleSource, plotlySource] = await Promise.all([
    fetchFrozenAssetText("static/styles.css"),
    fetchFrozenAssetText("plotly.min.js"),
  ]);
  return frozenPlotlySceneHtml(snapshot, styleSource, plotlySource);
}

function frozenPlotlySceneHtml(snapshot, styleSource, plotlySource) {
  const dualClass = snapshot.dual ? " xyz2-page" : "";
  const stage = snapshot.dual ? `
        <div class="xyz2-plot-grid">
          ${snapshot.panels.map((panel) => `
          <section class="xyz2-panel" aria-label="${escapeHtml(panel.label)} figure">
            <h2 class="xyz2-panel-title">${escapeHtml(panel.label)}</h2>
            <div class="plot-frame xyzuvw-plot-frame xyz2-plot-frame">
              <div class="xuv-frozen-plot" data-frozen-plot="${escapeHtml(panel.key)}"></div>
            </div>
          </section>`).join("")}
        </div>` : `
        <div class="plot-frame xyzuvw-plot-frame">
          <div class="xuv-frozen-plot" data-frozen-plot="${escapeHtml(snapshot.panels[0]?.key || "main")}"></div>
        </div>`;
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(snapshot.title)}</title>
  <style>${styleSafeText(styleSource)}</style>
  <style>.xuv-frozen-plot{min-width:0;min-height:0;width:100%;height:100%;background:var(--plot-bg);}</style>
</head>
<body class="xyzuvw-page xyzuvw-frozen-page${dualClass}">
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">${escapeHtml(snapshot.title)}</div>
      <div id="xuv-status" class="status">Frozen scene</div>
    </header>
    <main class="workspace xyzuvw-workspace xyzuvw-frozen-workspace">
      <section id="xuv-visual-area" class="visual-area xyzuvw-visual-area${snapshot.dual ? " xyz2-visual-area" : ""}">
${stage}
        <div class="xyzuvw-toolbar">
          <div class="xyzuvw-summary">
            <div id="xuv-summary">Loading frozen scene</div>
            <div id="xuv-hint" class="plot-hint"></div>
          </div>
        </div>
        <div class="selection-area xyzuvw-table-area">
          <div class="table-toolbar">
            <div>
              <strong id="xuv-table-title">Displayed objects</strong>
              <div id="xuv-table-subtitle" class="plot-hint">Selections appear here.</div>
            </div>
          </div>
          <div id="xuv-table" class="table-scroll"></div>
        </div>
      </section>
    </main>
  </div>
  <script>${scriptSafeText(plotlySource)}</script>
  <script>${scriptSafeText(`window.MOCAVIZ_FROZEN_PLOTLY_XYZ_SCENE = ${JSON.stringify(snapshot)};`)}</script>
  <script>${scriptSafeText(frozenPlotlyViewerScript())}</script>
</body>
</html>
`;
}

function frozenPlotlyViewerScript() {
  return `(${function initFrozenPlotlyScene() {
    const scene = window.MOCAVIZ_FROZEN_PLOTLY_XYZ_SCENE || {};
    const state = { selectedRows: [] };

    function init() {
      renderSummary();
      renderTable();
      (scene.panels || []).forEach((panel) => {
        const plotEl = document.querySelector('[data-frozen-plot="' + cssEscape(panel.key) + '"]');
        if (!plotEl || !window.Plotly) return;
        window.Plotly.newPlot(plotEl, panel.data || [], panel.layout || {}, panel.config || { responsive: true, displaylogo: false }).then(() => {
          bindPlotEvents(plotEl);
        });
      });
      window.addEventListener("resize", debounce(() => {
        (scene.panels || []).forEach((panel) => {
          const plotEl = document.querySelector('[data-frozen-plot="' + cssEscape(panel.key) + '"]');
          if (plotEl && window.Plotly) window.Plotly.Plots.resize(plotEl);
        });
      }, 120));
    }

    function bindPlotEvents(plotEl) {
      if (!plotEl || typeof plotEl.on !== "function") return;
      plotEl.on("plotly_click", (event) => selectRows((event && event.points || []).map((point) => point.customdata)));
      plotEl.on("plotly_selected", (event) => selectRows((event && event.points || []).map((point) => point.customdata)));
      plotEl.on("plotly_deselect", () => {
        state.selectedRows = [];
        renderTable();
      });
    }

    function selectRows(rows) {
      const seen = new Set();
      state.selectedRows = (rows || []).filter((row) => {
        const oid = normalizedMocaOid(row && row.moca_oid);
        if (!oid || seen.has(oid)) return false;
        seen.add(oid);
        return true;
      });
      renderTable();
    }

    function renderSummary() {
      const summary = document.getElementById("xuv-summary");
      const hint = document.getElementById("xuv-hint");
      const status = document.getElementById("xuv-status");
      if (status) status.textContent = "Frozen scene";
      if (summary) summary.textContent = scene.summaryText || "Frozen Plotly scene";
      if (hint) {
        hint.innerHTML = scene.hintHtml || ("Frozen export created " + escapeHtml(scene.exportedAt || "") + ".");
      }
    }

    function renderTable() {
      const tableData = scene.table || { columns: [], rows: [] };
      const title = document.getElementById("xuv-table-title");
      const subtitle = document.getElementById("xuv-table-subtitle");
      const table = document.getElementById("xuv-table");
      const rows = state.selectedRows.length ? state.selectedRows.map((row) => tableRowForData(row, tableData.axes || [])) : (tableData.rows || []);
      if (title) title.textContent = state.selectedRows.length ? (state.selectedRows.length + " selected objects") : (tableData.title || "Displayed objects");
      if (subtitle) subtitle.textContent = state.selectedRows.length ? "Click another point or box-select to update the frozen table." : (tableData.subtitle || "");
      if (!table) return;
      table.innerHTML = rows.length ? tableHtml(tableData.columns || [], rows, new Set(["report"])) : '<div class="selection-table">No objects to display.</div>';
    }

    function tableRowForData(row, axes) {
      const out = {
        moca_oid: normalizedMocaOid(row && row.moca_oid),
        designation: row && row.designation || "",
        moca_aid: row && row.moca_aid || "",
        moca_mtid: row && row.moca_mtid || "",
        spt: row && row.spt || "",
        ya_prob: finite(row && row.ya_prob) ? formatNumber(row.ya_prob, 1) : "",
        report: mocaReportUrl(row && row.moca_oid),
      };
      axes.forEach((axis, index) => {
        out[axis] = formatNumber(tableAxisValue(row || {}, axes, axis, index), 2);
      });
      return out;
    }

    function tableAxisValue(row, axes, axis, index) {
      if (!scene.dual && finite(row["plot" + index])) return row["plot" + index];
      const optKey = axis + "_opt";
      if (scene.assumeMembership && finite(row[optKey])) return Number(row[optKey]);
      return finite(row[axis]) ? Number(row[axis]) : null;
    }

    function tableHtml(columns, rows, htmlColumns) {
      return '<div class="selection-table"><table><thead><tr>' +
        columns.map((column) => '<th>' + escapeHtml(column) + '</th>').join("") +
        '</tr></thead><tbody>' +
        rows.map((row) => '<tr>' + columns.map((column) => '<td>' + (htmlColumns.has(column) ? reportCell(row[column]) : escapeHtml(row[column] == null ? "" : row[column])) + '</td>').join("") + '</tr>').join("") +
        '</tbody></table></div>';
    }

    function reportCell(url) {
      return url ? '<a class="report-link" href="' + escapeHtml(url) + '" target="_blank" rel="noopener">Report</a>' : "";
    }

    function mocaReportUrl(oid) {
      const normalized = normalizedMocaOid(oid);
      return normalized ? "https://mocadb.ca/search/results?search-query=oid%28" + encodeURIComponent(normalized) + "%29&search-type=star" : "";
    }

    function normalizedMocaOid(oid) {
      if (oid === null || oid === undefined) return "";
      const text = String(oid).trim();
      if (!text) return "";
      const number = Number(text);
      if (!Number.isFinite(number) || number <= 0) return "";
      return number.toFixed(0);
    }

    function finite(value) {
      if (value === null || value === undefined) return false;
      if (typeof value === "string" && value.trim() === "") return false;
      return Number.isFinite(Number(value));
    }

    function formatNumber(value, digits) {
      return finite(value) ? Number(value).toFixed(digits) : "";
    }

    function escapeHtml(value) {
      return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      }[char]));
    }

    function cssEscape(value) {
      if (window.CSS && window.CSS.escape) return window.CSS.escape(String(value));
      return String(value).replace(/[^a-zA-Z0-9_-]/g, "\\\\$&");
    }

    function debounce(fn, delay) {
      let timer = null;
      return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
      };
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
  }.toString()})();`;
}

async function fetchFrozenAssetText(path) {
  const response = await fetch(xuvAppUrl(path));
  if (!response.ok) throw new Error(`Could not read ${path}`);
  return response.text();
}

function frozenDateStamp() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

function jsonClean(value) {
  return JSON.parse(JSON.stringify(value));
}

function scriptSafeText(value) {
  return String(value ?? "").replace(/<\/script/gi, "<\\/script").replace(/<!--/g, "<\\!--");
}

function styleSafeText(value) {
  return String(value ?? "").replace(/<\/style/gi, "<\\/style");
}

function setXyzuvwExportDisabled(disabled) {
  for (const id of ["xuv-export-csv", "xuv-export-tsv", "xuv-export-fits", "xuv-export-votable", "xuv-download-frozen"]) {
    if (xuvEl[id]) xuvEl[id].disabled = disabled;
  }
}

function openSelectedXyzuvwReport() {
  if (xuvState.selectedRows.length !== 1) return;
  const url = mocaReportUrl(xuvState.selectedRows[0].moca_oid);
  if (url) window.open(url, "_blank", "noopener");
}

async function clearXyzuvwCache() {
  if (xuvEl["xuv-clear-cache"]) xuvEl["xuv-clear-cache"].disabled = true;
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
    if (xuvEl["xuv-clear-cache"]) xuvEl["xuv-clear-cache"].disabled = false;
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

function cameraFromReferenceDistance(direction, distance) {
  const length = Math.hypot(Number(direction.x), Number(direction.y), Number(direction.z));
  const scale = finite(length) && length > 0 ? Number(distance) / length : 1;
  return {
    eye: {
      x: Number(direction.x) * scale,
      y: Number(direction.y) * scale,
      z: Number(direction.z) * scale,
    },
  };
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
