const gcmdAgeColorscale = [
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

const gcmdSequenceColors = {
  field: "#3f3d46",
  mel5: "#d55e00",
  abdmg: "#0072b2",
  tha: "#009e73",
  bpmg: "#cc79a7",
  twa: "#e69f00",
  etac: "#56b4e9",
};

const gcmdSequenceLegendOrder = ["etac", "twa", "bpmg", "tha", "abdmg", "mel5", "field"];

const gcmdSequenceLegendLabels = {
  etac: "η Cha (~7 Myr)",
  twa: "TW Hya (~11 Myr)",
  bpmg: "β Pic (~26 Myr)",
  tha: "Tuc-Hor (~40 Myr)",
  abdmg: "AB Dor (~130 Myr)",
  mel5: "MELANGE-5 (~200 Myr)",
  field: "Field",
};

const gcmdDefaultAssociations = [
  { value: "THA", label: "THA - Tucana-Horologium association" },
];

const gcmdAssociationPalette = [
  "#0072b2",
  "#d55e00",
  "#009e73",
  "#cc79a7",
  "#e69f00",
  "#56b4e9",
  "#6b5b95",
  "#8a7f2d",
  "#b54a4a",
  "#3d7f6f",
  "#6f63a8",
  "#b05f20",
];

const gcmdBandByPsid = {
  gaiadr1_gmag: "G",
  gaiadr2_bpmag: "GBP",
  gaiadr2_gmag: "G",
  gaiadr2_rpmag: "GRP",
  gaiadr3_bpmag: "GBP",
  gaiadr3_gmag: "G",
  gaiadr3_grvsmag: "GRVS",
  gaiadr3_rpmag: "GRP",
};

const gcmdBandLabels = {
  G: "G",
  GBP: "G_BP",
  GRP: "G_RP",
  GRVS: "G_RVS",
};

const gcmdBandSelectLabels = {
  G: "G",
  GBP: "G_BP",
  GRP: "G_RP",
  GRVS: "G_RVS",
};

const gcmdBandHtmlLabels = {
  G: "G",
  GBP: "G<sub>BP</sub>",
  GRP: "G<sub>RP</sub>",
  GRVS: "G<sub>RVS</sub>",
};

const gcmdAbsMagHtmlLabels = {
  G: "M<sub><i>G</i></sub>",
  GBP: "M<sub><i>G</i><sub>BP</sub></sub>",
  GRP: "M<sub><i>G</i><sub>RP</sub></sub>",
  GRVS: "M<sub><i>G</i><sub>RVS</sub></sub>",
};

const gcmdAxisBandHtmlLabels = {
  G: "<i>G</i>",
  GBP: "<i>G</i><sub>BP</sub>",
  GRP: "<i>G</i><sub>RP</sub>",
  GRVS: "<i>G</i><sub>RVS</sub>",
};

const gcmdSptClasses = ["O", "B", "A", "F", "G", "K", "M", "L", "T", "Y"];
const gcmdSptAxisRequiredTicks = [3, 7, 8, 9, 10];
const gcmdDefaultYRange = [16.2, -0.2];
const gcmdDefaultXRangeByColor = {
  bprp: [0, 4.5],
  grp: [-0.05, 1.8],
};

const gcmdState = {
  options: { simple: [], advanced: [] },
  associationOptions: [],
  selectedAids: [],
  selectedHighlightObjects: [],
  privateDb: false,
  payload: null,
  rows: [],
  selectedRows: [],
  loadToken: 0,
  aidSearchTimer: null,
  objectSearchTimer: null,
};

const gcmdEl = {};

document.addEventListener("DOMContentLoaded", initGaiaCmd);

const gcmdAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function gcmdAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), gcmdAppBaseUrl).toString();
}

async function initGaiaCmd() {
  collectGaiaCmdElements();
  bindGaiaCmdControls();
  await loadGaiaCmdOptions();
  readGaiaCmdUrlState();
  renderGaiaCmdAssociationList();
  await loadGaiaCmdData();
}

function collectGaiaCmdElements() {
  [
    "gcmd-status",
    "gcmd-x1",
    "gcmd-x2",
    "gcmd-y",
    "gcmd-ruwe",
    "gcmd-aids-clear",
    "gcmd-aid-search",
    "gcmd-aid-results",
    "gcmd-selected-aids",
    "gcmd-object-search",
    "gcmd-object-results",
    "gcmd-selected-objects",
    "gcmd-highlight-oids",
    "gcmd-color-age",
    "gcmd-raw-gaia",
    "gcmd-extcorr-only",
    "gcmd-extcorr-vectors",
    "gcmd-display-errors",
    "gcmd-highlight-binaries",
    "gcmd-show-sequences",
    "gcmd-field-hover",
    "gcmd-load",
    "gcmd-plot",
    "gcmd-plot-loader",
    "gcmd-summary",
    "gcmd-hint",
    "gcmd-export-csv",
    "gcmd-export-tsv",
    "gcmd-export-fits",
    "gcmd-export-votable",
    "gcmd-clear-cache",
    "gcmd-clear-cache-bottom",
    "gcmd-clear-cache-status",
    "gcmd-table-title",
    "gcmd-table-subtitle",
    "gcmd-table",
  ].forEach((id) => {
    gcmdEl[id] = document.getElementById(id);
  });
}

function bindGaiaCmdControls() {
  gcmdEl["gcmd-load"].addEventListener("click", () => loadGaiaCmdData());
  for (const id of ["gcmd-x1", "gcmd-x2", "gcmd-y", "gcmd-color-age", "gcmd-raw-gaia", "gcmd-extcorr-only", "gcmd-extcorr-vectors", "gcmd-show-sequences"]) {
    gcmdEl[id].addEventListener("change", () => loadGaiaCmdData());
  }
  gcmdEl["gcmd-highlight-binaries"].addEventListener("change", () => {
    renderGaiaCmdPlot();
    updateGaiaCmdUrl();
    if (gcmdState.payload?.selection) {
      gcmdEl["gcmd-hint"].innerHTML = axisSummaryHtml(gcmdState.payload.selection);
    }
  });
  gcmdEl["gcmd-field-hover"].addEventListener("change", () => {
    renderGaiaCmdPlot();
    updateGaiaCmdUrl();
  });
  gcmdEl["gcmd-display-errors"].addEventListener("change", () => {
    renderGaiaCmdPlot();
    updateGaiaCmdUrl();
    if (gcmdState.payload?.selection) {
      gcmdEl["gcmd-hint"].innerHTML = axisSummaryHtml(gcmdState.payload.selection);
    }
  });
  for (const id of ["gcmd-ruwe", "gcmd-highlight-oids"]) {
    gcmdEl[id].addEventListener("keydown", (event) => {
      if (event.key === "Enter") loadGaiaCmdData();
    });
  }
  gcmdEl["gcmd-highlight-oids"].addEventListener("change", () => loadGaiaCmdData());
  gcmdEl["gcmd-aids-clear"].addEventListener("click", () => {
    gcmdState.selectedAids = [];
    renderGaiaCmdAssociationList();
    loadGaiaCmdData();
  });
  gcmdEl["gcmd-aid-search"].addEventListener("input", () => {
    const value = gcmdEl["gcmd-aid-search"].value.trim();
    clearTimeout(gcmdState.aidSearchTimer);
    gcmdState.aidSearchTimer = setTimeout(() => searchGaiaCmdAssociations(value), 180);
  });
  gcmdEl["gcmd-aid-search"].addEventListener("focus", () => {
    const value = gcmdEl["gcmd-aid-search"].value.trim();
    if (value) searchGaiaCmdAssociations(value);
  });
  gcmdEl["gcmd-object-search"].addEventListener("input", () => {
    const value = gcmdEl["gcmd-object-search"].value.trim();
    clearTimeout(gcmdState.objectSearchTimer);
    gcmdState.objectSearchTimer = setTimeout(() => searchGaiaCmdObjects(value), 220);
  });
  gcmdEl["gcmd-object-search"].addEventListener("focus", () => {
    const value = gcmdEl["gcmd-object-search"].value.trim();
    if (value) searchGaiaCmdObjects(value);
  });
  document.addEventListener("click", (event) => {
    if (!gcmdEl["gcmd-aid-results"].contains(event.target) && event.target !== gcmdEl["gcmd-aid-search"]) {
      gcmdEl["gcmd-aid-results"].hidden = true;
    }
    if (!gcmdEl["gcmd-object-results"].contains(event.target) && event.target !== gcmdEl["gcmd-object-search"]) {
      gcmdEl["gcmd-object-results"].hidden = true;
    }
  });
  window.addEventListener("resize", debounce(() => {
    if (!gcmdEl["gcmd-aid-results"].hidden) positionGaiaCmdAssociationPopup();
    if (!gcmdEl["gcmd-object-results"].hidden) positionGaiaCmdObjectPopup();
  }, 150));
  gcmdEl["gcmd-export-csv"].addEventListener("click", () => exportGaiaCmd("csv"));
  gcmdEl["gcmd-export-tsv"].addEventListener("click", () => exportGaiaCmd("tsv"));
  gcmdEl["gcmd-export-fits"].addEventListener("click", () => exportGaiaCmd("fits"));
  gcmdEl["gcmd-export-votable"].addEventListener("click", () => exportGaiaCmd("votable"));
  if (gcmdEl["gcmd-clear-cache"]) gcmdEl["gcmd-clear-cache"].addEventListener("click", clearGaiaCmdCache);
  gcmdEl["gcmd-clear-cache-bottom"].addEventListener("click", clearGaiaCmdCache);
}

async function loadGaiaCmdOptions() {
  try {
    const params = backendPassthroughParams();
    const payload = await fetchJsonUrl(gcmdAppUrl(`api/gaia-cmd/options?${params.toString()}`));
    if (!payload.ok) throw new Error(payload.error || "Could not load Gaia CMD options");
    gcmdState.options = payload.photometry || { simple: [], advanced: [] };
    gcmdState.privateDb = Boolean(payload.meta?.private_db);
  } catch (error) {
    setGaiaCmdStatus(error.message || String(error), "error");
    gcmdState.options = { simple: [], advanced: [] };
  }
  fillGaiaCmdSelects({ x1: "gaiadr3_bpmag", x2: "gaiadr3_rpmag", y: "gaiadr3_gmag" });
}

function fillGaiaCmdSelects(current = {}) {
  const fallback = [
    { value: "gaiadr3_bpmag", label: "G_BP", moca_psid: "gaiadr3_bpmag" },
    { value: "gaiadr3_gmag", label: "G", moca_psid: "gaiadr3_gmag" },
    { value: "gaiadr3_rpmag", label: "G_RP", moca_psid: "gaiadr3_rpmag" },
    { value: "gaiadr3_grvsmag", label: "G_RVS", moca_psid: "gaiadr3_grvsmag" },
  ];
  const rows = gcmdState.options.simple?.length ? gcmdState.options.simple : fallback;
  for (const [id, defaultValue] of [["gcmd-x1", "gaiadr3_bpmag"], ["gcmd-x2", "gaiadr3_rpmag"], ["gcmd-y", "gaiadr3_gmag"]]) {
    const select = gcmdEl[id];
    const desired = current[id.replace("gcmd-", "")] || select.value || defaultValue;
    select.innerHTML = rows.map((row) => `<option value="${escapeHtml(row.value)}">${escapeHtml(bandSelectLabel(row.value, row.label || row.value))}</option>`).join("");
    select.value = rows.some((row) => row.value === desired) ? desired : defaultValue;
  }
}

function readGaiaCmdUrlState() {
  const params = new URLSearchParams(window.location.search);
  fillGaiaCmdSelects({
    x1: normalizeGaiaCmdBand(params.get("x1") || params.get("xaxis_value_1") || "gaiadr3_bpmag"),
    x2: normalizeGaiaCmdBand(params.get("x2") || params.get("xaxis_value_2") || "gaiadr3_rpmag"),
    y: normalizeGaiaCmdBand(params.get("y") || params.get("yaxis_value_1") || "gaiadr3_gmag"),
  });
  if (params.has("ruwe") || params.has("ruwe_max")) gcmdEl["gcmd-ruwe"].value = params.get("ruwe") || params.get("ruwe_max") || "";
  const oidValue = params.get("oid") || params.get("oids") || params.get("moca_oid") || params.get("moca_oids") || "";
  gcmdEl["gcmd-highlight-oids"].value = oidValue;
  gcmdEl["gcmd-color-age"].checked = truthyParam(params.get("color_age") || params.get("color_by_age") || params.get("age"));
  gcmdEl["gcmd-raw-gaia"].checked = truthyParam(params.get("raw_gaia") || params.get("raw_photometry") || params.get("use_raw_gaia"));
  gcmdEl["gcmd-extcorr-only"].checked = truthyParam(params.get("extinction_corrected") || params.get("extcorr") || params.get("extinction_corrected_only"));
  gcmdEl["gcmd-extcorr-vectors"].checked = truthyParam(params.get("extinction_vectors") || params.get("extcorr_vectors") || params.get("show_extinction_vectors"));
  gcmdEl["gcmd-display-errors"].checked = truthyParam(params.get("display_errors") || params.get("errors") || params.get("phot_errors") || params.get("show_errors"));
  gcmdEl["gcmd-highlight-binaries"].checked = truthyParam(params.get("binaries") || params.get("highlight_binaries") || params.get("known_binaries"));
  gcmdEl["gcmd-field-hover"].checked = truthyParam(params.get("field_hover") || params.get("field_hovertext") || params.get("hover_field"));
  const sequenceValue = params.get("sequences") ?? params.get("display_sequences") ?? params.get("age_sequences") ?? params.get("show_sequences");
  gcmdEl["gcmd-show-sequences"].checked = sequenceValue === null ? true : !falsyParam(sequenceValue);
  const associationParam = firstPresentParam(params, ["asso", "association", "associations", "moca_aid", "aid"]);
  const selectedAssociations = associationParam === null
    ? gcmdDefaultAssociations.map((association) => association.value)
    : parseCsv(associationParam);
  gcmdDefaultAssociations.forEach(upsertGaiaCmdAssociationOption);
  gcmdState.selectedAids = selectedAssociations;
  gcmdState.selectedAids.forEach((aid) => {
    if (!gcmdState.associationOptions.some((row) => String(row.value) === String(aid))) {
      upsertGaiaCmdAssociationOption({ value: aid, label: aid });
    }
  });
  renderGaiaCmdHighlightList();
}

function firstPresentParam(params, keys) {
  for (const key of keys) {
    if (params.has(key)) return params.get(key) || "";
  }
  return null;
}

function normalizeGaiaCmdBand(value) {
  const raw = String(value || "").trim();
  const aliases = {
    G: "gaiadr3_gmag",
    GBP: "gaiadr3_bpmag",
    BP: "gaiadr3_bpmag",
    GRP: "gaiadr3_rpmag",
    RP: "gaiadr3_rpmag",
    GRVS: "gaiadr3_grvsmag",
  };
  const normalized = raw.toUpperCase().replace(/^SIMPLE:/, "");
  return aliases[normalized] || raw.toLowerCase();
}

async function loadGaiaCmdData() {
  updateGaiaCmdUrl();
  const token = ++gcmdState.loadToken;
  setGaiaCmdStatus("Loading Gaia CMD", "loading");
  setGaiaCmdLoader(true);
  gcmdEl["gcmd-load"].disabled = true;
  const params = gaiaCmdApiParams();
  try {
    const payload = await fetchJsonUrl(gcmdAppUrl(`api/gaia-cmd/data?${params.toString()}`));
    if (token !== gcmdState.loadToken) return;
    if (!payload.ok) throw new Error(payload.error || "Could not load Gaia CMD");
    gcmdState.payload = payload;
    const highlightOids = new Set(combinedHighlightOids().map(String));
    const ruweMax = parseRuweMax(payload.selection?.ruwe_max);
    gcmdState.rows = (payload.rows || []).filter((row) => finite(row.x) && finite(row.y));
    gcmdState.rows.forEach((row, index) => {
      row._plotIndex = index;
      row._sample = row.moca_aid || row.sample || "Field";
      row._highlighted = Number(row.highlighted || 0) === 1 || (row.moca_oid !== null && row.moca_oid !== undefined && highlightOids.has(String(Math.trunc(Number(row.moca_oid)))));
      row._deemphasized = ruweMax !== null && finite(row.ruwe) && Number(row.ruwe) > ruweMax;
      row._isBinary = Number(row.is_binary || 0) === 1;
      row._xError = gaiaCmdXError(row);
      row._yError = gaiaCmdYError(row);
    });
    gcmdState.selectedRows = [];
    renderGaiaCmdPlot();
    renderGaiaCmdDefaultTable();
    const cacheText = payload.cache?.hit ? " from cache" : "";
    const trunc = payload.meta?.truncated ? `, capped at ${Number(payload.meta.max_objects || 0).toLocaleString()} per source` : "";
    const deemphCount = gcmdState.rows.filter((row) => row._deemphasized).length;
    setGaiaCmdStatus(`${gcmdState.rows.length.toLocaleString()} Gaia CMD objects${cacheText}`, "");
    gcmdEl["gcmd-summary"].textContent = `${gcmdState.rows.length.toLocaleString()} objects plotted${trunc}; ${deemphCount.toLocaleString()} de-emphasized by RUWE; ${Number(payload.sequences?.length || 0).toLocaleString()} sequence overlays`;
    gcmdEl["gcmd-hint"].innerHTML = axisSummaryHtml(payload.selection);
    setGaiaCmdExportDisabled(gcmdState.rows.length === 0);
  } catch (error) {
    if (token !== gcmdState.loadToken) return;
    setGaiaCmdStatus(error.message || String(error), "error");
    renderEmptyGaiaCmd(error.message || "Could not load Gaia CMD");
  } finally {
    if (token === gcmdState.loadToken) {
      setGaiaCmdLoader(false);
      gcmdEl["gcmd-load"].disabled = false;
    }
  }
}

function gaiaCmdApiParams() {
  const params = backendPassthroughParams();
  params.set("x1", gcmdEl["gcmd-x1"].value);
  params.set("x2", gcmdEl["gcmd-x2"].value);
  params.set("y", gcmdEl["gcmd-y"].value);
  if (gcmdEl["gcmd-ruwe"].value !== "") params.set("ruwe", gcmdEl["gcmd-ruwe"].value);
  const oids = combinedHighlightOids();
  if (oids.length) params.set("oid", oids.join(","));
  if (gcmdState.selectedAids.length) params.set("asso", gcmdState.selectedAids.join(","));
  if (gcmdEl["gcmd-color-age"].checked) params.set("color_age", "1");
  if (gcmdEl["gcmd-raw-gaia"].checked) params.set("raw_gaia", "1");
  if (gcmdEl["gcmd-extcorr-only"].checked) params.set("extinction_corrected", "1");
  if (gcmdEl["gcmd-extcorr-vectors"].checked) params.set("extinction_vectors", "1");
  if (!gcmdEl["gcmd-show-sequences"].checked) params.set("sequences", "0");
  return params;
}

function updateGaiaCmdUrl() {
  const params = gaiaCmdApiParams();
  params.delete("moca_aid");
  params.delete("aid");
  params.delete("moca_oid");
  params.delete("oids");
  params.delete("moca_oids");
  params.set("binaries", gcmdEl["gcmd-highlight-binaries"].checked ? "1" : "0");
  params.set("field_hover", gcmdEl["gcmd-field-hover"].checked ? "1" : "0");
  if (!gcmdEl["gcmd-color-age"].checked) {
    params.delete("color_age");
    params.delete("color_by_age");
    params.delete("age");
  }
  if (!gcmdEl["gcmd-raw-gaia"].checked) {
    params.delete("raw_gaia");
    params.delete("raw_photometry");
    params.delete("use_raw_gaia");
  }
  if (!gcmdEl["gcmd-extcorr-only"].checked) {
    params.delete("extinction_corrected");
    params.delete("extcorr");
    params.delete("extinction_corrected_only");
  }
  if (!gcmdEl["gcmd-extcorr-vectors"].checked) {
    params.delete("extinction_vectors");
    params.delete("extcorr_vectors");
    params.delete("show_extinction_vectors");
  }
  if (gcmdEl["gcmd-display-errors"].checked) {
    params.set("display_errors", "1");
  } else {
    params.delete("display_errors");
    params.delete("errors");
    params.delete("phot_errors");
    params.delete("show_errors");
  }
  const query = params.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}

function combinedHighlightOids() {
  const seen = new Set();
  const out = [];
  for (const object of gcmdState.selectedHighlightObjects) {
    const oid = Number(object.moca_oid ?? object.value);
    if (Number.isInteger(oid) && !seen.has(oid)) {
      seen.add(oid);
      out.push(oid);
    }
  }
  for (const oid of parseOids(gcmdEl["gcmd-highlight-oids"].value)) {
    if (!seen.has(oid)) {
      seen.add(oid);
      out.push(oid);
    }
  }
  return out;
}

function backendPassthroughParams() {
  const input = new URLSearchParams(window.location.search);
  const output = new URLSearchParams();
  for (const key of ["host", "user", "pwd", "dbase", "port", "mock"]) {
    if (input.has(key)) output.set(key, input.get(key));
  }
  return output;
}

function renderGaiaCmdAssociationList() {
  const selected = gcmdState.selectedAids;
  if (!selected.length) {
    gcmdEl["gcmd-selected-aids"].innerHTML = `<div class="designation-result-note">No associations selected</div>`;
    return;
  }
  gcmdEl["gcmd-selected-aids"].innerHTML = selected.map((aid) => `
    <span class="designation-chip association-chip">
      <span title="${escapeHtml(gaiaCmdAssociationLabel(aid))}">${escapeHtml(gaiaCmdAssociationLabel(aid))}</span>
      <button type="button" data-aid="${escapeHtml(aid)}" aria-label="Remove ${escapeHtml(aid)}">x</button>
    </span>
  `).join("");
  gcmdEl["gcmd-selected-aids"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const aid = button.dataset.aid;
      gcmdState.selectedAids = gcmdState.selectedAids.filter((value) => value !== aid);
      renderGaiaCmdAssociationList();
      loadGaiaCmdData();
    });
  });
}

async function searchGaiaCmdAssociations(query) {
  query = String(query || "").trim();
  if (!query) {
    gcmdEl["gcmd-aid-results"].hidden = true;
    return;
  }
  const params = backendPassthroughParams();
  params.set("q", query);
  const payload = await fetchJsonUrl(gcmdAppUrl(`api/gaia-cmd/associations/search?${params.toString()}`));
  if (!payload.ok) {
    gcmdEl["gcmd-aid-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
    showGaiaCmdAssociationPopup();
    return;
  }
  const results = (payload.options || []).filter((result) => result.value);
  if (!results.length) {
    gcmdEl["gcmd-aid-results"].innerHTML = `<div class="designation-result-note">No associations found</div>`;
    showGaiaCmdAssociationPopup();
    return;
  }
  results.forEach(upsertGaiaCmdAssociationOption);
  gcmdEl["gcmd-aid-results"].innerHTML = results.map((result, index) => {
    const value = String(result.value);
    const selected = gcmdState.selectedAids.includes(value);
    const label = result.label || value;
    return `
      <button class="designation-result association-result" type="button" data-index="${index}" ${selected ? "disabled" : ""}>
        <span>${selected ? "Selected: " : ""}${escapeHtml(label)}</span>
      </button>
    `;
  }).join("");
  gcmdEl["gcmd-aid-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const result = results[Number(button.dataset.index)];
      const aid = String(result.value || "").trim();
      if (aid && !gcmdState.selectedAids.includes(aid)) {
        upsertGaiaCmdAssociationOption(result);
        gcmdState.selectedAids.push(aid);
        renderGaiaCmdAssociationList();
        loadGaiaCmdData();
      }
      gcmdEl["gcmd-aid-search"].value = "";
      gcmdEl["gcmd-aid-results"].hidden = true;
    });
  });
  showGaiaCmdAssociationPopup();
}

function showGaiaCmdAssociationPopup() {
  positionGaiaCmdAssociationPopup();
  gcmdEl["gcmd-aid-results"].hidden = false;
}

function positionGaiaCmdAssociationPopup() {
  const input = gcmdEl["gcmd-aid-search"];
  const popup = gcmdEl["gcmd-aid-results"];
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

function gaiaCmdAssociationLabel(aid) {
  const option = gcmdState.associationOptions.find((row) => String(row.value) === String(aid));
  return option?.label || String(aid);
}

function upsertGaiaCmdAssociationOption(option) {
  if (!option?.value) return;
  const value = String(option.value);
  const label = option.label || value;
  const existing = gcmdState.associationOptions.find((row) => String(row.value) === value);
  if (existing) {
    existing.label = label;
  } else {
    gcmdState.associationOptions.push({ value, label });
  }
}

function renderGaiaCmdHighlightList() {
  const selected = gcmdState.selectedHighlightObjects;
  if (!selected.length) {
    gcmdEl["gcmd-selected-objects"].innerHTML = `<div class="designation-result-note">No highlighted objects selected</div>`;
    return;
  }
  gcmdEl["gcmd-selected-objects"].innerHTML = selected.map((object) => {
    const oid = Number(object.moca_oid ?? object.value);
    const label = object.label || (object.designation ? `oid${oid}: ${object.designation}` : `oid${oid}`);
    return `
      <span class="designation-chip">
        <span title="${escapeHtml(label)}">${escapeHtml(label)}</span>
        <button type="button" data-remove-oid="${escapeHtml(oid)}" aria-label="Remove ${escapeHtml(label)}">x</button>
      </span>
    `;
  }).join("");
  gcmdEl["gcmd-selected-objects"].querySelectorAll("button[data-remove-oid]").forEach((button) => {
    button.addEventListener("click", () => {
      const oid = Number(button.dataset.removeOid);
      gcmdState.selectedHighlightObjects = gcmdState.selectedHighlightObjects.filter((object) => Number(object.moca_oid ?? object.value) !== oid);
      renderGaiaCmdHighlightList();
      loadGaiaCmdData();
    });
  });
}

async function searchGaiaCmdObjects(query) {
  query = String(query || "").trim();
  if (!query) {
    gcmdEl["gcmd-object-results"].hidden = true;
    return;
  }
  if (searchableDesignation(query).length < 2 && !/^\d+$/.test(query)) {
    gcmdEl["gcmd-object-results"].innerHTML = `<div class="designation-result-note">Type at least 2 characters.</div>`;
    showGaiaCmdObjectPopup();
    return;
  }
  const params = backendPassthroughParams();
  params.set("q", query);
  const payload = await fetchJsonUrl(gcmdAppUrl(`api/gaia-cmd/search?${params.toString()}`));
  if (!payload.ok) {
    gcmdEl["gcmd-object-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
    showGaiaCmdObjectPopup();
    return;
  }
  const results = (payload.options || []).filter((result) => result.moca_oid !== null && result.moca_oid !== undefined);
  if (!results.length) {
    gcmdEl["gcmd-object-results"].innerHTML = `<div class="designation-result-note">No objects found</div>`;
    showGaiaCmdObjectPopup();
    return;
  }
  gcmdEl["gcmd-object-results"].innerHTML = results.map((result, index) => {
    const oid = Number(result.moca_oid ?? result.value);
    const selected = gcmdState.selectedHighlightObjects.some((object) => Number(object.moca_oid ?? object.value) === oid);
    const label = result.label || (result.designation ? `oid${oid}: ${result.designation}` : `oid${oid}`);
    return `
      <button type="button" class="designation-result" data-index="${index}" ${selected ? "disabled" : ""}>
        ${selected ? "Selected: " : ""}${escapeHtml(label)}
      </button>
    `;
  }).join("");
  gcmdEl["gcmd-object-results"].querySelectorAll("button[data-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const result = results[Number(button.dataset.index)];
      selectGaiaCmdHighlightObject(result);
      gcmdEl["gcmd-object-search"].value = "";
      gcmdEl["gcmd-object-results"].hidden = true;
    });
  });
  showGaiaCmdObjectPopup();
}

function selectGaiaCmdHighlightObject(result) {
  const oid = Number(result?.moca_oid ?? result?.value);
  if (!Number.isInteger(oid)) return;
  if (!gcmdState.selectedHighlightObjects.some((object) => Number(object.moca_oid ?? object.value) === oid)) {
    gcmdState.selectedHighlightObjects.push({
      value: oid,
      moca_oid: oid,
      designation: result.designation || "",
      label: result.label || (result.designation ? `oid${oid}: ${result.designation}` : `oid${oid}`),
    });
  }
  renderGaiaCmdHighlightList();
  loadGaiaCmdData();
}

function showGaiaCmdObjectPopup() {
  positionGaiaCmdObjectPopup();
  gcmdEl["gcmd-object-results"].hidden = false;
}

function positionGaiaCmdObjectPopup() {
  const input = gcmdEl["gcmd-object-search"];
  const popup = gcmdEl["gcmd-object-results"];
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

function renderGaiaCmdPlot() {
  const payload = gcmdState.payload || {};
  const traces = [];
  const colorByAge = Boolean(payload.selection?.color_by_age);
  const nonHighlightRows = gcmdState.rows.filter((row) => !row._highlighted);
  const highlightRows = gcmdState.rows.filter((row) => row._highlighted);

  if (colorByAge) {
    addAgeTraces(traces, nonHighlightRows, "Gaia CMD");
  } else {
    addPlainTrace(traces, nonHighlightRows.filter((row) => !row.moca_aid), "Field", "#000000", 4.4, "field", {
      opacity: 0.05,
      deemphasizedOpacity: 0.02,
      hover: fieldHoverEnabled(),
    });
    for (const aid of associationOrder(nonHighlightRows)) {
      addPlainTrace(traces, nonHighlightRows.filter((row) => row.moca_aid === aid), gaiaCmdAssociationLegendLabel(aid), colorForAssociation(aid), 6.1, `aid:${aid}`, {
        opacity: 0.84,
        deemphasizedOpacity: 0.2,
      });
    }
  }
  addBinaryOverlayTrace(traces, gcmdState.rows);
  addHighlightTrace(traces, highlightRows);
  addSequenceTraces(traces, payload.sequences || []);
  addSptAxisReferenceTrace(traces, payload.spt_axis || null, gcmdState.rows);

  const layout = gaiaCmdLayout(payload.selection || {}, payload.spt_axis || null, gcmdState.rows);
  if (payload.selection?.show_extinction_vectors) {
    layout.annotations = extinctionVectorAnnotations(gcmdState.rows);
  }
  Plotly.react(gcmdEl["gcmd-plot"], traces, layout, plotConfig("mocadb_gaia_cmd"));
  bindPlotEventsOnce();
}

function addPlainTrace(traces, rows, name, color, size, legendgroup, options = {}) {
  if (!rows.length) return;
  const normal = rows.filter((row) => !row._deemphasized);
  const deemph = rows.filter((row) => row._deemphasized);
  if (normal.length) {
    traces.push(markerTrace(normal, {
      name,
      color,
      size,
      opacity: options.opacity ?? 0.72,
      legendgroup,
      showlegend: true,
      hover: options.hover,
    }));
  }
  if (deemph.length) {
    traces.push(markerTrace(deemph, {
      name: `${name} (high RUWE)`,
      color,
      size,
      opacity: options.deemphasizedOpacity ?? 0.16,
      legendgroup,
      showlegend: normal.length === 0,
      hover: options.hover,
    }));
  }
}

function markerTrace(rows, options) {
  const errors = traceErrorBars(rows, options.errorColor || options.color, options.opacity, options.errors !== false);
  return {
    type: errors ? "scatter" : "scattergl",
    mode: "markers",
    name: options.name,
    legendgroup: options.legendgroup,
    showlegend: options.showlegend,
    x: rows.map((row) => row.x),
    y: rows.map((row) => row.y),
    text: rows.map((row) => hoverText(row)),
    customdata: rows.map((row) => row._plotIndex),
    ...(options.hover === false ? { hoverinfo: "none" } : { hovertemplate: "%{text}<extra></extra>" }),
    ...(errors || {}),
    marker: {
      size: options.size,
      color: options.color,
      opacity: options.opacity,
      line: { width: 0, color: options.color },
    },
  };
}

function traceErrorBars(rows, color, opacity = 0.45, enabled = true) {
  if (!enabled || !gaiaCmdDisplayErrors()) return null;
  const xErrors = rows.map((row) => errorBarValue(row._xError !== undefined ? row._xError : gaiaCmdXError(row)));
  const yErrors = rows.map((row) => errorBarValue(row._yError !== undefined ? row._yError : gaiaCmdYError(row)));
  const props = {};
  if (xErrors.some((value) => value > 0)) {
    props.error_x = errorBarConfig(xErrors, color, opacity);
  }
  if (yErrors.some((value) => value > 0)) {
    props.error_y = errorBarConfig(yErrors, color, opacity);
  }
  return Object.keys(props).length ? props : null;
}

function errorBarConfig(values, color, opacity) {
  const alpha = Math.max(0.18, Math.min(0.66, Number(opacity) * 0.72 || 0.42));
  return {
    type: "data",
    array: values,
    visible: true,
    color: colorWithAlpha(color || "#333333", alpha),
    thickness: 0.8,
    width: 1.5,
  };
}

function errorBarValue(value) {
  return finite(value) && Number(value) > 0 ? Number(value) : 0;
}

function gaiaCmdDisplayErrors() {
  return Boolean(gcmdEl["gcmd-display-errors"]?.checked);
}

function gaiaCmdXError(row) {
  const x1 = nonnegativeFiniteNumber(row?.x1_mag_unc);
  const x2 = nonnegativeFiniteNumber(row?.x2_mag_unc);
  return x1 === null || x2 === null ? null : Math.hypot(x1, x2);
}

function gaiaCmdYError(row) {
  const yMag = nonnegativeFiniteNumber(row?.y_mag_unc);
  if (yMag === null) return null;
  const terms = [yMag];
  const distanceTerm = distanceModulusError(row?.distance_pc, row?.distance_pc_unc);
  if (distanceTerm !== null) terms.push(distanceTerm);
  return Math.hypot(...terms);
}

function distanceModulusError(distancePc, distanceUnc) {
  const distance = Number(distancePc);
  const unc = nonnegativeFiniteNumber(distanceUnc);
  if (!Number.isFinite(distance) || distance <= 0 || unc === null) return null;
  return Math.abs(5 * unc / (Math.log(10) * distance));
}

function nonnegativeFiniteNumber(value) {
  if (!finite(value)) return null;
  const number = Number(value);
  return number >= 0 ? number : null;
}

function addAgeTraces(traces, rows, name) {
  if (!rows.length) return;
  const withAge = rows.filter((row) => finite(row.age_myr) && Number(row.age_myr) > 0);
  const noAge = rows.filter((row) => !finite(row.age_myr) || Number(row.age_myr) <= 0);
  addPlainTrace(traces, noAge.filter((row) => !row.moca_aid), "Field (no age)", "#000000", 4.8, "field-no-age", {
    opacity: 0.05,
    deemphasizedOpacity: 0.02,
    hover: fieldHoverEnabled(),
  });
  addPlainTrace(traces, noAge.filter((row) => row.moca_aid), `${name} (no age)`, "#858a8d", 4.8, "no-age", {
    opacity: 0.38,
    deemphasizedOpacity: 0.07,
  });
  const normal = withAge.filter((row) => !row._deemphasized);
  const deemph = withAge.filter((row) => row._deemphasized);
  let showScale = true;
  if (normal.length) {
    traces.push(ageTrace(normal, name, 0.82, true));
    showScale = false;
  }
  if (deemph.length) {
    traces.push(ageTrace(deemph, `${name} (high RUWE)`, 0.18, showScale));
  }
}

function fieldHoverEnabled() {
  return Boolean(gcmdEl["gcmd-field-hover"]?.checked);
}

function ageTrace(rows, name, opacity, showScale) {
  const errors = traceErrorBars(rows, "#4a4a4a", opacity, true);
  return {
    type: errors ? "scatter" : "scattergl",
    mode: "markers",
    name,
    legendgroup: "age",
    showlegend: showScale,
    x: rows.map((row) => row.x),
    y: rows.map((row) => row.y),
    text: rows.map((row) => hoverText(row)),
    customdata: rows.map((row) => row._plotIndex),
    hovertemplate: "%{text}<extra></extra>",
    ...(errors || {}),
    marker: {
      size: 6.0,
      color: rows.map((row) => Math.log10(Number(row.age_myr))),
      cmin: 0,
      cmax: 3.2,
      colorscale: gcmdAgeColorscale,
      opacity,
      showscale: showScale,
      colorbar: showScale ? {
        title: { text: "Age", font: { size: 14 } },
        x: 1.04,
        xanchor: "left",
        y: 0.5,
        yanchor: "middle",
        len: 0.75,
        thickness: 20,
        outlinecolor: "#111111",
        outlinewidth: 2.5,
        ticks: "outside",
        ticklen: 8,
        tickwidth: 2,
        tickcolor: "#111111",
        tickfont: { size: 12 },
        tickvals: [0, 1, 2, 3],
        ticktext: ["1 Myr", "10 Myr", "100 Myr", "1 Gyr"],
      } : undefined,
      line: { width: 0 },
    },
  };
}

function addHighlightTrace(traces, rows) {
  if (!rows.length) return;
  const highlightGold = "#ffd23f";
  const highlightEdge = "#4a3300";
  const errors = traceErrorBars(rows, highlightEdge, 0.9, true);
  traces.push({
    type: "scatter",
    mode: "markers",
    name: "Highlighted OIDs",
    legendgroup: "highlighted",
    showlegend: true,
    x: rows.map((row) => row.x),
    y: rows.map((row) => row.y),
    text: rows.map((row) => hoverText(row)),
    customdata: rows.map((row) => row._plotIndex),
    hovertemplate: "%{text}<extra></extra>",
    ...(errors || {}),
    marker: {
      size: 21,
      color: highlightGold,
      opacity: 1,
      symbol: "star",
      line: { width: 1.8, color: highlightEdge },
    },
  });
}

function addBinaryOverlayTrace(traces, rows) {
  if (!gcmdEl["gcmd-highlight-binaries"]?.checked) return;
  const binaryRows = rows.filter((row) => row._isBinary);
  if (!binaryRows.length) return;
  const colorByAge = Boolean(gcmdState.payload?.selection?.color_by_age);
  const colors = binaryRows.map((row) => colorByAge ? ageColorForGaiaRow(row) : sampleColorForGaiaRow(row));
  traces.push({
    type: "scattergl",
    mode: "markers",
    name: "Binaries",
    legendgroup: "binaries",
    showlegend: true,
    x: binaryRows.map((row) => row.x),
    y: binaryRows.map((row) => row.y),
    text: binaryRows.map((row) => hoverText(row)),
    customdata: binaryRows.map((row) => row._plotIndex),
    hovertemplate: "%{text}<extra></extra>",
    marker: {
      size: binaryRows.map((row) => row.moca_aid ? 9.2 : 7.4),
      color: colors,
      opacity: binaryRows.map((row) => row._deemphasized ? 0.28 : 0.95),
      symbol: "circle-open",
      line: { width: 2.1, color: colors },
    },
  });
}

function addSequenceTraces(traces, sequences) {
  for (const sequence of orderedGaiaCmdSequences(sequences)) {
    const suffix = String(sequence.moca_seqid || "").split("_").pop();
    const label = sequenceLegendLabel(sequence, suffix);
    traces.push({
      type: "scattergl",
      mode: "lines",
      name: label,
      legendrank: 500 + gcmdSequenceLegendOrder.indexOf(suffix),
      x: sequence.x || [],
      y: sequence.y || [],
      hoverinfo: "skip",
      line: {
        width: suffix === "field" ? 2.4 : 2,
        color: gcmdSequenceColors[suffix] || "#444444",
        dash: suffix === "field" ? "solid" : "dash",
      },
    });
  }
}

function addSptAxisReferenceTrace(traces, sptAxis, rows) {
  const ticks = gaiaCmdSptAxisTicks(sptAxis);
  if (!ticks.tickvals.length) return;
  const yValues = rows.map((row) => Number(row.y)).filter((value) => Number.isFinite(value));
  const yAnchor = yValues.length ? yValues[Math.floor(yValues.length / 2)] : 0;
  traces.push({
    type: "scatter",
    mode: "markers",
    xaxis: "x2",
    yaxis: "y",
    x: ticks.tickvals,
    y: ticks.tickvals.map(() => yAnchor),
    marker: { size: 1, color: "rgba(0,0,0,0)" },
    opacity: 0,
    hoverinfo: "skip",
    showlegend: false,
    name: "Spectral type axis reference",
  });
}

function orderedGaiaCmdSequences(sequences) {
  const bySuffix = new Map();
  for (const sequence of sequences || []) {
    const suffix = String(sequence.moca_seqid || "").split("_").pop();
    if (gcmdSequenceLegendOrder.includes(suffix) && !bySuffix.has(suffix)) {
      bySuffix.set(suffix, sequence);
    }
  }
  return gcmdSequenceLegendOrder.map((suffix) => bySuffix.get(suffix)).filter(Boolean);
}

function sequenceLegendLabel(sequence, suffix) {
  return gcmdSequenceLegendLabels[suffix] || sequence.name || sequence.moca_seqid || suffix;
}

function extinctionVectorAnnotations(rows) {
  const annotations = [];
  const colorByAge = Boolean(gcmdState.payload?.selection?.color_by_age);
  for (const row of rows) {
    if (!finite(row.x_original) || !finite(row.y_original) || !finite(row.x) || !finite(row.y)) continue;
    const dx = Number(row.x) - Number(row.x_original);
    const dy = Number(row.y) - Number(row.y_original);
    if (Math.hypot(dx, dy) <= 1e-5) continue;
    const pointColor = colorByAge ? ageColorForGaiaRow(row) : sampleColorForGaiaRow(row);
    const arrowAlpha = row._highlighted ? 0.82 : (row._deemphasized ? 0.18 : 0.56);
    annotations.push({
      x: Number(row.x),
      y: Number(row.y),
      ax: Number(row.x_original),
      ay: Number(row.y_original),
      xref: "x",
      yref: "y",
      axref: "x",
      ayref: "y",
      text: "",
      showarrow: true,
      arrowhead: 2,
      arrowsize: 0.75,
      arrowwidth: row._highlighted ? 1.6 : 1.05,
      arrowcolor: colorWithAlpha(pointColor, arrowAlpha),
      opacity: 1,
      standoff: 0,
      startstandoff: 0,
      hovertext: hoverText(row),
      hoverlabel: { bgcolor: "#ffffff" },
    });
  }
  return annotations;
}

function associationOrder(rows) {
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    const aid = row.moca_aid;
    if (aid && !seen.has(aid)) {
      seen.add(aid);
      out.push(aid);
    }
  }
  return out.sort();
}

function colorForAssociation(aid) {
  const suffix = String(aid || "").toLowerCase();
  if (gcmdSequenceColors[suffix]) return gcmdSequenceColors[suffix];
  let hash = 0;
  for (const char of String(aid || "")) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return gcmdAssociationPalette[hash % gcmdAssociationPalette.length];
}

function sampleColorForGaiaRow(row) {
  return row.moca_aid ? colorForAssociation(row.moca_aid) : "#000000";
}

function ageColorForGaiaRow(row) {
  if (!finite(row.age_myr) || Number(row.age_myr) <= 0) return row.moca_aid ? "#858a8d" : "#000000";
  const t = Math.max(0, Math.min(1, Math.log10(Number(row.age_myr)) / 3.2));
  for (let i = 1; i < gcmdAgeColorscale.length; i += 1) {
    const [rightStop, rightColor] = gcmdAgeColorscale[i];
    const [leftStop, leftColor] = gcmdAgeColorscale[i - 1];
    if (t <= rightStop) {
      const span = Math.max(rightStop - leftStop, 1e-9);
      return interpolateRgb(leftColor, rightColor, (t - leftStop) / span);
    }
  }
  return gcmdAgeColorscale[gcmdAgeColorscale.length - 1][1];
}

function interpolateRgb(left, right, fraction) {
  const a = parseRgb(left);
  const b = parseRgb(right);
  if (!a || !b) return right;
  const f = Math.max(0, Math.min(1, fraction));
  const values = a.map((value, index) => Math.round(value + (b[index] - value) * f));
  return `rgb(${values[0]},${values[1]},${values[2]})`;
}

function colorWithAlpha(color, alpha) {
  const rgb = parseRgb(color) || parseHexColor(color);
  if (!rgb) return color;
  const a = Math.max(0, Math.min(1, Number(alpha)));
  return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`;
}

function parseRgb(value) {
  const match = String(value || "").match(/rgb\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)/i);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

function parseHexColor(value) {
  const match = String(value || "").trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (!match) return null;
  const hex = match[1].length === 3
    ? match[1].split("").map((char) => `${char}${char}`).join("")
    : match[1];
  return [0, 2, 4].map((index) => parseInt(hex.slice(index, index + 2), 16));
}

function gaiaCmdLayout(selection, sptAxis, rows = []) {
  const xLabel = `Gaia DR3 ${axisBandHtmlLabel(selection.x1, selection.x1_label)} - ${axisBandHtmlLabel(selection.x2, selection.x2_label)} color`;
  const yLabel = `Absolute Gaia DR3 ${absoluteMagnitudeHtmlLabel(selection.y, selection.y_label)} magnitude`;
  const colorByAge = Boolean(selection?.color_by_age);
  const sptAxisConfig = gaiaCmdSptAxisConfig(sptAxis);
  const axisRanges = gaiaCmdInitialRanges(selection, rows);
  const axisBoxStyle = {
    showline: true,
    linecolor: "#000000",
    linewidth: 3,
    mirror: true,
    ticks: "outside",
    ticklen: 8,
    tickwidth: 2,
    tickcolor: "#000000",
  };
  return {
    autosize: true,
    paper_bgcolor: "#dedde1",
    plot_bgcolor: "#ffffff",
    margin: { l: 82, r: colorByAge ? 330 : 150, t: sptAxisConfig ? 82 : 20, b: 76 },
    hovermode: "closest",
    dragmode: "select",
    legend: {
      orientation: "v",
      x: colorByAge ? 1.18 : 1.01,
      y: 1,
      xanchor: "left",
      bgcolor: "rgba(255,255,255,0.78)",
      bordercolor: "rgba(0,0,0,0)",
      font: { size: 10 },
    },
    xaxis: {
      ...axisBoxStyle,
      title: { text: xLabel, font: { size: 22 } },
      zeroline: false,
      showgrid: true,
      gridcolor: "#e2e2e2",
      automargin: true,
      tickfont: { size: 15 },
      ...(axisRanges.x ? { range: axisRanges.x } : {}),
    },
    ...(sptAxisConfig ? { xaxis2: sptAxisConfig } : {}),
    yaxis: {
      ...axisBoxStyle,
      title: { text: yLabel, font: { size: 22 } },
      zeroline: false,
      showgrid: true,
      gridcolor: "#e2e2e2",
      automargin: true,
      tickfont: { size: 15 },
      range: axisRanges.y,
    },
  };
}

function gaiaCmdInitialRanges(selection, rows) {
  const xRange = gaiaCmdDefaultXRange(selection);
  const relevantRows = (rows || []).filter((row) => row?.moca_aid || row?._highlighted);
  return {
    x: xRange ? expandLinearRange(xRange, relevantRows.map((row) => row.x), { minPad: 0.02, padFraction: 0.025 }) : null,
    y: expandReversedMagnitudeRange(gcmdDefaultYRange, relevantRows.map((row) => row.y)),
  };
}

function gaiaCmdDefaultXRange(selection) {
  const x1 = bandKeyForPsid(selection?.x1);
  const x2 = bandKeyForPsid(selection?.x2);
  if (x1 === "GBP" && x2 === "GRP") return [...gcmdDefaultXRangeByColor.bprp];
  if (x1 === "G" && x2 === "GRP") return [...gcmdDefaultXRangeByColor.grp];
  return null;
}

function expandLinearRange(baseRange, values, options = {}) {
  const finiteValues = values.map(Number).filter(Number.isFinite);
  if (!finiteValues.length) return [...baseRange];
  let [left, right] = baseRange;
  const span = Math.max(Math.abs(right - left), 1e-9);
  const pad = Math.max(options.minPad ?? 0, span * (options.padFraction ?? 0));
  const minValue = Math.min(...finiteValues);
  const maxValue = Math.max(...finiteValues);
  if (minValue < left) left = minValue - pad;
  if (maxValue > right) right = maxValue + pad;
  return [Number(left.toFixed(4)), Number(right.toFixed(4))];
}

function expandReversedMagnitudeRange(baseRange, values) {
  const finiteValues = values.map(Number).filter(Number.isFinite);
  if (!finiteValues.length) return [...baseRange];
  let faintLimit = baseRange[0];
  let brightLimit = baseRange[1];
  const span = Math.max(Math.abs(faintLimit - brightLimit), 1e-9);
  const pad = Math.max(0.05, span * 0.025);
  const minValue = Math.min(...finiteValues);
  const maxValue = Math.max(...finiteValues);
  if (maxValue > faintLimit) faintLimit = maxValue + pad;
  if (minValue < brightLimit) brightLimit = minValue - pad;
  return [Number(faintLimit.toFixed(4)), Number(brightLimit.toFixed(4))];
}

function gaiaCmdSptAxisConfig(sptAxis) {
  const ticks = gaiaCmdSptAxisTicks(sptAxis);
  if (!ticks.tickvals.length) return null;
  return {
    title: { text: "Spectral type", font: { size: 22 }, standoff: 8 },
    anchor: "y",
    overlaying: "x",
    side: "top",
    matches: "x",
    tickmode: "array",
    tickvals: ticks.tickvals,
    ticktext: ticks.ticktext,
    showline: true,
    linecolor: "#000000",
    linewidth: 3,
    showgrid: false,
    zeroline: false,
    ticks: "outside",
    ticklen: 8,
    tickwidth: 2,
    tickcolor: "#000000",
    tickfont: { size: 15 },
    automargin: true,
  };
}

function gaiaCmdSptAxisTicks(sptAxis) {
  const pairs = (sptAxis?.sptn || [])
    .map((sptn, index) => ({ sptn: Number(sptn), color: Number(sptAxis.color?.[index]) }))
    .filter((row) => finite(row.sptn) && finite(row.color))
    .sort((a, b) => a.sptn - b.sptn);
  if (pairs.length < 2) return { tickvals: [], ticktext: [] };

  const clean = [];
  for (const pair of pairs) {
    if (clean.length && Math.abs(clean[clean.length - 1].sptn - pair.sptn) < 1e-8) {
      clean[clean.length - 1] = pair;
    } else {
      clean.push(pair);
    }
  }
  if (clean.length < 2) return { tickvals: [], ticktext: [] };

  const sptMin = clean[0].sptn;
  const sptMax = clean[clean.length - 1].sptn;
  let sptTicks = [];
  for (let value = Math.ceil(sptMin / 5) * 5; value <= Math.floor(sptMax / 5) * 5 + 1e-6; value += 5) {
    sptTicks.push(value);
  }
  if (sptTicks.length < 2) {
    const count = Math.min(6, clean.length);
    sptTicks = Array.from({ length: count }, (_, index) => sptMin + (sptMax - sptMin) * index / Math.max(1, count - 1));
  }
  if (sptTicks.length > 9) {
    const last = sptTicks.length - 1;
    const indices = Array.from(new Set(Array.from({ length: 9 }, (_, index) => Math.round(index * last / 8))));
    sptTicks = indices.map((index) => sptTicks[index]);
  }
  sptTicks = Array.from(new Set([...sptTicks, ...gcmdSptAxisRequiredTicks])).sort((a, b) => a - b);

  const tickvals = [];
  const ticktext = [];
  for (const sptn of sptTicks) {
    const label = gaiaCmdSptLabel(sptn);
    const color = interpolateGaiaCmdSptColor(clean, sptn);
    if (!label || !finite(color)) continue;
    tickvals.push(Number(color.toFixed(4)));
    ticktext.push(label);
  }
  return tickvals.length >= 2 ? { tickvals, ticktext } : { tickvals: [], ticktext: [] };
}

function interpolateGaiaCmdSptColor(pairs, sptn) {
  if (sptn <= pairs[0].sptn) {
    const left = pairs[0];
    const right = pairs[1] || pairs[0];
    const fraction = (sptn - left.sptn) / Math.max(1e-12, right.sptn - left.sptn);
    return left.color + (right.color - left.color) * fraction;
  }
  for (let index = 1; index < pairs.length; index += 1) {
    const left = pairs[index - 1];
    const right = pairs[index];
    if (sptn <= right.sptn) {
      const fraction = (sptn - left.sptn) / Math.max(1e-12, right.sptn - left.sptn);
      return left.color + (right.color - left.color) * fraction;
    }
  }
  const left = pairs[pairs.length - 2] || pairs[pairs.length - 1];
  const right = pairs[pairs.length - 1];
  const fraction = (sptn - left.sptn) / Math.max(1e-12, right.sptn - left.sptn);
  return left.color + (right.color - left.color) * fraction;
}

function gaiaCmdSptLabel(value) {
  if (!finite(value)) return "";
  const adjusted = Number(value) + 60;
  const classIndex = Math.floor(adjusted / 10);
  if (classIndex < 0 || classIndex >= gcmdSptClasses.length) return "";
  const subtype = adjusted - classIndex * 10;
  const subtypeText = subtype.toFixed(1).replace(/\.0$/, "");
  return `${gcmdSptClasses[classIndex]}${subtypeText}`;
}

function bindPlotEventsOnce() {
  const plot = gcmdEl["gcmd-plot"];
  if (plot.dataset.gcmdBound === "1") return;
  plot.dataset.gcmdBound = "1";
  plot.on("plotly_click", (event) => {
    const row = rowFromPoint(event?.points?.[0]);
    gcmdState.selectedRows = row ? [row] : [];
    renderGaiaCmdSelection();
  });
  plot.on("plotly_selected", (event) => {
    const rows = (event?.points || []).map(rowFromPoint).filter(Boolean);
    gcmdState.selectedRows = uniqueRows(rows);
    renderGaiaCmdSelection();
  });
  plot.on("plotly_deselect", () => {
    gcmdState.selectedRows = [];
    renderGaiaCmdSelection();
  });
}

function rowFromPoint(point) {
  const index = Number(point?.customdata);
  if (!Number.isInteger(index)) return null;
  return gcmdState.rows[index] || null;
}

function uniqueRows(rows) {
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    const key = rowKey(row);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(row);
  }
  return out;
}

function rowKey(row) {
  if (row?.moca_oid !== null && row?.moca_oid !== undefined && row?.moca_oid !== "") return `oid:${intText(row.moca_oid)}`;
  if (row?.source_id) return `source:${row.source_id}`;
  return `row:${row?._plotIndex ?? Math.random()}`;
}

function renderGaiaCmdSelection() {
  if (!gcmdState.selectedRows.length) {
    renderGaiaCmdDefaultTable();
    return;
  }
  const rows = listedGaiaCmdTableRows(gcmdState.selectedRows);
  renderGaiaCmdTable(rows, `${rows.length.toLocaleString()} selected listed object${rows.length === 1 ? "" : "s"}`, "Field-sample objects are omitted from this table.");
}

function renderGaiaCmdDefaultTable() {
  const rows = listedGaiaCmdTableRows(gcmdState.rows);
  renderGaiaCmdTable(rows.slice(0, 100), "Displayed listed objects", `Showing the first ${Math.min(rows.length, 100).toLocaleString()} association or highlighted rows; field-sample objects are omitted.`);
}

function listedGaiaCmdTableRows(rows) {
  return (rows || []).filter((row) => row.moca_aid || row._highlighted);
}

function renderGaiaCmdTable(rows, title, subtitle) {
  gcmdEl["gcmd-table-title"].textContent = title;
  gcmdEl["gcmd-table-subtitle"].textContent = subtitle;
  const columns = ["plot", "sample", "moca_oid", "designation", "source_id", "x", "y", "y_mag", "distance_pc", "ruwe", "binary", "ya_prob", "age_myr", "photometry_source", "report"];
  const tableRows = rows.map((row) => {
    const reportUrl = mocaReportUrl(row.moca_oid);
    return {
      plot: gaiaCmdTableMarkerHtml(row),
      sample: row.moca_aid || row.sample || "",
      moca_oid: normalizedMocaOid(row.moca_oid),
      designation: row.designation || "",
      source_id: row.source_id || "",
      x: formatNumber(row.x, 3),
      y: formatNumber(row.y, 3),
      y_mag: magText(row.y_mag, row.y_mag_unc),
      distance_pc: distanceText(row.distance_pc, row.distance_pc_unc),
      ruwe: formatNumber(row.ruwe, 3),
      binary: row._isBinary ? "yes" : "",
      ya_prob: finite(row.ya_prob) ? formatNumber(row.ya_prob, 1) : "",
      age_myr: finite(row.age_myr) ? formatNumber(row.age_myr, 1) : "",
      photometry_source: row.photometry_source || "",
      report: reportUrl ? `<a class="report-link" href="${reportUrl}" target="_blank" rel="noopener">Report</a>` : "",
    };
  });
  gcmdEl["gcmd-table"].innerHTML = tableHtml(columns, tableRows, new Set(["plot", "report"]));
}

function gaiaCmdAssociationLegendLabel(aid) {
  return String(aid || "");
}

function gaiaCmdTableColor(row) {
  return gcmdEl["gcmd-color-age"]?.checked ? ageColorForGaiaRow(row) : sampleColorForGaiaRow(row);
}

function gaiaCmdTableMarkerHtml(row) {
  const color = gaiaCmdTableColor(row);
  const isHighlighted = Boolean(row._highlighted);
  const isBinaryOverlay = Boolean(gcmdEl["gcmd-highlight-binaries"]?.checked && row._isBinary);
  const open = isHighlighted || isBinaryOverlay;
  const markerClass = isHighlighted ? "is-star" : "is-circle";
  const fill = isHighlighted ? "#ffd23f" : (open ? "none" : color);
  const stroke = isHighlighted ? "#4a3300" : (open ? color : "rgba(255,255,255,0.82)");
  const strokeWidth = isHighlighted ? 1.8 : (open ? 2.1 : 1.4);
  const size = isHighlighted ? 20 : (row.moca_aid ? 12.8 : 10.4);
  const opacity = isHighlighted ? 1 : (row._deemphasized ? 0.35 : (row.moca_aid ? 0.95 : 0.45));
  return `<span class="plot-table-marker-wrap"><span class="plot-table-marker ${markerClass}${!isHighlighted && open ? " is-open" : ""}" style="--marker-size: ${size}px; --marker-color: ${escapeHtml(color)}; --marker-fill: ${escapeHtml(fill)}; --marker-edge: ${escapeHtml(stroke)}; --marker-border-width: ${escapeHtml(strokeWidth)}px; --marker-opacity: ${opacity};"></span></span>`;
}

function renderEmptyGaiaCmd(message) {
  Plotly.react(gcmdEl["gcmd-plot"], [], {
    paper_bgcolor: "#dedde1",
    plot_bgcolor: "#ffffff",
    margin: { l: 80, r: 20, t: 30, b: 70 },
    annotations: [{ text: escapeHtml(message), x: 0.5, y: 0.5, xref: "paper", yref: "paper", showarrow: false }],
    xaxis: { visible: false },
    yaxis: { visible: false },
  }, plotConfig("mocadb_gaia_cmd_empty"));
  renderGaiaCmdTable([], "Displayed objects", "No plotted rows.");
  gcmdEl["gcmd-summary"].textContent = "No data loaded";
  setGaiaCmdExportDisabled(true);
}

function hoverText(row) {
  const designation = row.designation || (row.moca_oid ? `oid${intText(row.moca_oid)}` : row.source_id || "Gaia source");
  const parts = [
    `<b>${escapeHtml(designation)}</b>`,
    row.moca_oid !== null && row.moca_oid !== undefined ? `OID: ${intText(row.moca_oid)}` : null,
    row.moca_aid ? `Association: ${escapeHtml(row.moca_aid)}` : `Sample: ${escapeHtml(row.sample || "Field")}`,
    finite(row.ya_prob) ? `BANYAN probability: ${formatNumber(row.ya_prob, 1)}%` : null,
    row.source_id ? `Gaia DR3 source: ${escapeHtml(row.source_id)}` : null,
    row._isBinary ? "Known binary" : null,
    `x: ${formatNumber(row.x, 3)}`,
    `y: ${formatNumber(row.y, 3)}`,
    `${bandLabel(row.x1_psid)}: ${magText(row.x1_mag, row.x1_mag_unc)}`,
    `${bandLabel(row.x2_psid)}: ${magText(row.x2_mag, row.x2_mag_unc)}`,
    `${bandLabel(row.y_psid)}: ${magText(row.y_mag, row.y_mag_unc)}`,
    finite(row.x1_extinction_a) ? `A(${bandLabel(row.x1_psid)}): ${formatNumber(row.x1_extinction_a, 3)} mag` : null,
    finite(row.x2_extinction_a) ? `A(${bandLabel(row.x2_psid)}): ${formatNumber(row.x2_extinction_a, 3)} mag` : null,
    finite(row.y_extinction_a) ? `A(${bandLabel(row.y_psid)}): ${formatNumber(row.y_extinction_a, 3)} mag` : null,
    finite(row.x_original) && finite(row.y_original) ? `Uncorrected CMD position: ${formatNumber(row.x_original, 3)}, ${formatNumber(row.y_original, 3)}` : null,
    finite(row._xError) ? `x error: +/- ${formatNumber(row._xError, 3)} mag` : null,
    finite(row._yError) ? `y error: +/- ${formatNumber(row._yError, 3)} mag` : null,
    `Distance: ${distanceText(row.distance_pc, row.distance_pc_unc)}`,
    finite(row.ruwe) ? `RUWE: ${formatNumber(row.ruwe, 3)}${row._deemphasized ? " (de-emphasized)" : ""}` : null,
    finite(row.age_myr) ? `Age: ${formatNumber(row.age_myr, 1)} Myr` : null,
    row.photometry_source ? `Photometry: ${escapeHtml(row.photometry_source)}` : null,
  ].filter(Boolean);
  return parts.join("<br>");
}

function tableHtml(columns, rows, htmlColumns = new Set()) {
  if (!rows.length) return `<div class="designation-result-note">No rows to display</div>`;
  const head = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
  const body = rows.map((row) => `<tr>${columns.map((column) => {
    const value = row[column] ?? "";
    return `<td>${htmlColumns.has(column) ? value : escapeHtml(value)}</td>`;
  }).join("")}</tr>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

const gaiaCmdExportColumns = ["sample", "moca_aid", "moca_oid", "designation", "source_id", "is_binary", "x", "y", "x_original", "y_original", "x1_mag", "x1_extinction_a", "x2_mag", "x2_extinction_a", "y_mag", "y_extinction_a", "distance_pc", "distance_pc_unc", "ruwe", "ya_prob", "age_myr", "photometry_source"];
const gaiaCmdNumericExportColumns = new Set(["moca_oid", "is_binary", "x", "y", "x_original", "y_original", "x1_mag", "x1_extinction_a", "x2_mag", "x2_extinction_a", "y_mag", "y_extinction_a", "distance_pc", "distance_pc_unc", "ruwe", "ya_prob", "age_myr"]);

function exportGaiaCmd(format) {
  if (!gcmdState.rows.length) return;
  MocaExport.saveTable(format, {
    rows: gcmdState.rows,
    columns: gaiaCmdExportColumns,
    numericColumns: gaiaCmdNumericExportColumns,
    filenameBase: "mocadb_gaia_cmd",
    tableName: "mocadb_gaia_cmd",
    resourceName: "MOCAdb Gaia CMD Explorer",
    extName: "GAIA_CMD",
  });
}

function setGaiaCmdExportDisabled(disabled) {
  for (const id of ["gcmd-export-csv", "gcmd-export-tsv", "gcmd-export-fits", "gcmd-export-votable"]) {
    if (gcmdEl[id]) gcmdEl[id].disabled = disabled;
  }
}

async function clearGaiaCmdCache() {
  gcmdEl["gcmd-clear-cache-status"].textContent = "Clearing cache";
  gcmdEl["gcmd-clear-cache-status"].classList.remove("error");
  try {
    const payload = await postJson(gcmdAppUrl("api/gaia-cmd/cache/clear"), {});
    const count = payload.cleared?.gaiaCmd || 0;
    gcmdEl["gcmd-clear-cache-status"].textContent = `Cleared ${count} cached Gaia CMD payload${count === 1 ? "" : "s"}.`;
  } catch (error) {
    gcmdEl["gcmd-clear-cache-status"].textContent = error.message || String(error);
    gcmdEl["gcmd-clear-cache-status"].classList.add("error");
  }
}

function axisSummaryHtml(selection) {
  if (!selection) return "Click or box-select points to inspect objects.<br>Double-click an empty region of the plot to reset Plotly selection";
  const ruwe = selection.ruwe_max === null || selection.ruwe_max === undefined ? "no RUWE de-emphasis" : `RUWE > ${selection.ruwe_max} de-emphasized`;
  const phot = selection.raw_gaia ? "raw Gaia photometry for associations" : "adopted MOCAdb photometry for associations";
  const extcorr = !selection.raw_gaia && selection.extinction_corrected_only ? "; extinction-corrected MOCAdb photometry only" : "";
  const vectors = selection.show_extinction_vectors ? "; extinction vectors shown when available" : "";
  const errors = gaiaCmdDisplayErrors() ? "; CMD errors shown where available" : "";
  const binaries = gcmdEl["gcmd-highlight-binaries"]?.checked ? "; binaries highlighted" : "";
  const sequences = selection.show_sequences === false ? "; empirical age sequences hidden" : "";
  const aids = selection.associations?.length ? `${selection.associations.length} association${selection.associations.length === 1 ? "" : "s"} added` : "field stars only";
  return `${axisBandHtmlLabel(selection.x1, selection.x_label)} - ${axisBandHtmlLabel(selection.x2, selection.x2_label)} vs ${absoluteMagnitudeHtmlLabel(selection.y, selection.y_label)}; ${aids}; ${phot}${extcorr}${vectors}${errors}${binaries}${sequences}; ${ruwe}.<br>Double-click an empty region of the plot to reset Plotly selection`;
}

function bandLabel(psid) {
  return bandHtmlLabel(psid, psid);
}

function bandKeyForPsid(psid) {
  return gcmdBandByPsid[String(psid || "").toLowerCase()] || null;
}

function bandSelectLabel(psid, fallback = "") {
  const band = bandKeyForPsid(psid);
  return gcmdBandSelectLabels[band] || fallback || psid || "";
}

function bandHtmlLabel(psid, fallback = "") {
  const band = bandKeyForPsid(psid);
  return gcmdBandHtmlLabels[band] || shortBandLabel(fallback || psid || "");
}

function absoluteMagnitudeHtmlLabel(psid, fallback = "") {
  const band = bandKeyForPsid(psid);
  return gcmdAbsMagHtmlLabels[band] || `M<sub>${bandHtmlLabel(psid, fallback)}</sub>`;
}

function axisBandHtmlLabel(psid, fallback = "") {
  const band = bandKeyForPsid(psid);
  return gcmdAxisBandHtmlLabels[band] || bandHtmlLabel(psid, fallback);
}

function bandTextLabel(psid, fallback = "") {
  const band = gcmdBandByPsid[String(psid || "").toLowerCase()];
  return gcmdBandSelectLabels[band] || shortBandLabel(fallback || psid || "");
}

function shortBandLabel(label) {
  return String(label || "").replace(/\s*\(.*?\)\s*$/, "");
}

function magText(value, unc) {
  if (!finite(value)) return "";
  const base = `${formatNumber(value, 3)} mag`;
  return finite(unc) ? `${base} +/- ${formatNumber(unc, 3)}` : base;
}

function distanceText(value, unc) {
  if (!finite(value)) return "";
  const base = `${formatNumber(value, 2)} pc`;
  const err = finite(unc) ? ` +/- ${formatNumber(unc, 2)}` : "";
  return `${base}${err}`;
}

function setGaiaCmdStatus(text, mode) {
  gcmdEl["gcmd-status"].textContent = text;
  gcmdEl["gcmd-status"].classList.toggle("loading", mode === "loading");
  gcmdEl["gcmd-status"].classList.toggle("error", mode === "error");
}

function setGaiaCmdLoader(visible) {
  gcmdEl["gcmd-plot-loader"].classList.toggle("is-visible", Boolean(visible));
}

function parseRuweMax(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

function parseCsv(value) {
  const out = [];
  for (const item of String(value || "").replace(/;/g, ",").split(",")) {
    const clean = item.trim();
    if (clean && !out.includes(clean)) out.push(clean);
  }
  return out;
}

function parseOids(value) {
  return parseCsv(value).filter((item) => /^\d+$/.test(item)).map((item) => Number(item));
}

function searchableDesignation(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function finite(value) {
  if (value === null || value === undefined || value === "") return false;
  return Number.isFinite(Number(value));
}

function formatNumber(value, digits = 3) {
  if (!finite(value)) return "";
  const number = Number(value);
  return number.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0, useGrouping: false });
}

function intText(value) {
  if (!finite(value)) return "";
  return String(Math.trunc(Number(value)));
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

function truthyParam(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

function falsyParam(value) {
  return ["0", "false", "no", "off", "hide", "hidden"].includes(String(value || "").trim().toLowerCase());
}

function debounce(fn, wait) {
  let timeout = null;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), wait);
  };
}

async function fetchJsonUrl(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function plotConfig(name) {
  return {
    responsive: true,
    displaylogo: false,
    toImageButtonOptions: {
      filename: name,
      format: "png",
      scale: 2,
    },
  };
}

function csvCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
