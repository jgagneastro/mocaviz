const ghNatureColors = {
  "moving group": "#0072B2",
  "association": "#009E73",
  "cluster": "#CC79A7",
  "complex": "#6B5B95",
  "collection": "#8A7F2D",
  "stream": "#56B4E9",
  "": "#7C7682",
};

const ghState = {
  rows: [],
  rowById: new Map(),
  rowByAid: new Map(),
  options: [],
  directChildren: {},
  descendants: {},
  selectedAid: "ALL",
  centerAid: "ALL",
  payload: null,
  loadToken: 0,
  nativeClickBound: false,
};

const ghEl = {};

document.addEventListener("DOMContentLoaded", initGroupHierarchy);

const ghAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function ghAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), ghAppBaseUrl).toString();
}

async function initGroupHierarchy() {
  collectGroupHierarchyElements();
  renderGroupHierarchyLegend();
  bindGroupHierarchyControls();
  readGroupHierarchyUrlState();
  renderGroupHierarchyEmpty();
  await loadGroupHierarchyCatalog();
}

function collectGroupHierarchyElements() {
  [
    "gh-status",
    "gh-aid-search",
    "gh-aid-options",
    "gh-center",
    "gh-root",
    "gh-selected-summary",
    "gh-branch-stats",
    "gh-color-legend",
    "gh-reload",
    "gh-clear-cache",
    "gh-clear-cache-status",
    "gh-link-list",
    "gh-plot",
    "gh-plot-loader",
    "gh-summary",
    "gh-hint",
    "gh-report-link",
    "gh-xyz-link",
    "gh-members-link",
    "gh-detail-title",
    "gh-detail-subtitle",
    "gh-details",
  ].forEach((id) => {
    ghEl[id] = document.getElementById(id);
  });
}

function bindGroupHierarchyControls() {
  ghEl["gh-center"].addEventListener("click", () => {
    const aid = resolveGroupHierarchyInput(ghEl["gh-aid-search"].value);
    if (aid) selectGroupHierarchyAid(aid, { center: true });
  });
  ghEl["gh-aid-search"].addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      const aid = resolveGroupHierarchyInput(ghEl["gh-aid-search"].value);
      if (aid) selectGroupHierarchyAid(aid, { center: true });
    }
  });
  ghEl["gh-root"].addEventListener("click", () => selectGroupHierarchyAid("ALL", { center: true }));
  ghEl["gh-reload"].addEventListener("click", () => loadGroupHierarchyCatalog({ clearCache: false }));
  ghEl["gh-clear-cache"].addEventListener("click", clearGroupHierarchyCache);
  window.addEventListener("resize", () => {
    if (ghEl["gh-plot"]) Plotly.Plots.resize(ghEl["gh-plot"]);
  });
}

function readGroupHierarchyUrlState() {
  const params = new URLSearchParams(window.location.search);
  const aid = cleanAid(params.get("node") || params.get("asso") || params.get("aid") || params.get("moca_aid") || "ALL");
  ghState.selectedAid = aid || "ALL";
  ghState.centerAid = ghState.selectedAid;
  if (ghState.selectedAid !== "ALL") ghEl["gh-aid-search"].value = ghState.selectedAid;
}

async function loadGroupHierarchyCatalog(options = {}) {
  const token = ++ghState.loadToken;
  setGroupHierarchyLoading(true);
  setGroupHierarchyStatus("Loading association hierarchy", "loading");
  try {
    if (options.clearCache) await postGroupHierarchyJson("api/group-hierarchy/cache/clear");
    const params = groupHierarchyConnectionParams();
    const payload = await fetchGroupHierarchyJson(`api/group-hierarchy/catalog?${params.toString()}`);
    if (token !== ghState.loadToken) return;
    ghState.payload = payload;
    ghState.rows = Array.isArray(payload.rows) ? payload.rows : [];
    ghState.directChildren = payload.direct_children || {};
    ghState.descendants = payload.descendants || {};
    ghState.options = Array.isArray(payload.options) ? payload.options : [];
    ghState.rowById = new Map(ghState.rows.map((row) => [String(row.id), row]));
    ghState.rowByAid = new Map();
    for (const row of ghState.rows) {
      const aid = String(row.original_aid || row.aid || row.id || "");
      if (aid && !ghState.rowByAid.has(aid)) ghState.rowByAid.set(aid, row);
    }
    ghState.centerAid = resolveGroupHierarchyNodeId(ghState.centerAid) || "ALL";
    ghState.selectedAid = resolveGroupHierarchyNodeId(ghState.selectedAid) || ghState.centerAid;
    populateGroupHierarchyOptions();
    renderGroupHierarchyPlot();
    renderGroupHierarchySelection();
    const meta = payload.meta || {};
    const cacheText = payload.cache?.hit ? "cache" : `${formatNumber(meta.query_seconds, 1)} s`;
    setGroupHierarchyStatus(`${ghState.rows.length.toLocaleString()} hierarchy nodes from ${cacheText}`, "");
  } catch (error) {
    setGroupHierarchyStatus(error.message || String(error), "error");
    renderGroupHierarchyEmpty(error.message || "Unable to load association hierarchy.");
  } finally {
    setGroupHierarchyLoading(false);
  }
}

function populateGroupHierarchyOptions() {
  ghEl["gh-aid-options"].innerHTML = "";
  for (const option of ghState.options) {
    const node = document.createElement("option");
    node.value = option.value;
    node.label = option.label || option.value;
    ghEl["gh-aid-options"].appendChild(node);
  }
}

function renderGroupHierarchyLegend() {
  const entries = [
    ["All associations", "#4A4650"],
    ["Moving group", ghNatureColors["moving group"]],
    ["Association", ghNatureColors.association],
    ["Cluster", ghNatureColors.cluster],
    ["Complex", ghNatureColors.complex],
    ["Collection", ghNatureColors.collection],
    ["Stream", ghNatureColors.stream],
    ["Unknown type", ghNatureColors[""]],
    ["Suboptimal grouping", "#A5A0AA"],
  ];
  ghEl["gh-color-legend"].innerHTML = entries.map(([label, color]) => `
    <div class="group-hierarchy-legend-item">
      <span class="group-hierarchy-legend-swatch" style="background: ${escapeHtml(color)}"></span>
      <span>${escapeHtml(label)}</span>
    </div>
  `).join("");
}

function renderGroupHierarchyPlot() {
  if (!ghState.rows.length) {
    return renderGroupHierarchyEmpty("No association hierarchy rows were returned.");
  }
  const rows = ghState.rows;
  const trace = {
    type: "sunburst",
    ids: rows.map((row) => row.id),
    labels: rows.map((row) => row.label || row.id),
    parents: rows.map((row) => row.parent_id || ""),
    customdata: rows.map((row) => row.id),
    hovertext: rows.map(groupHierarchyHoverText),
    hoverinfo: "text",
    hovertemplate: "%{hovertext}<extra></extra>",
    branchvalues: "remainder",
    insidetextorientation: "radial",
    marker: {
      colors: rows.map(groupHierarchyColor),
      line: { color: "#ffffff", width: 1 },
    },
  };
  trace.level = groupHierarchyPlotLevel(ghState.centerAid);
  const layout = {
    margin: { l: 4, r: 4, t: 4, b: 4 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    uniformtext: { minsize: 8 },
    transition: { duration: 520, easing: "cubic-in-out" },
    uirevision: `group-hierarchy-${ghState.centerAid}`,
  };
  const drawPromise = Plotly.react(ghEl["gh-plot"], [trace], layout, groupHierarchyPlotConfig()).then(() => {
    bindGroupHierarchyPlotEvents();
    Plotly.Plots.resize(ghEl["gh-plot"]);
  });
  updateGroupHierarchySummary();
  return drawPromise;
}

function bindGroupHierarchyPlotEvents() {
  if (!ghState.nativeClickBound) {
    ghEl["gh-plot"].on("plotly_sunburstclick", handleGroupHierarchySunburstClick);
    ghState.nativeClickBound = true;
  }
}

function groupHierarchyPlotLevel(aid) {
  const resolved = resolveGroupHierarchyNodeId(aid) || "ALL";
  return ghState.rowById.has(resolved) ? resolved : "ALL";
}

function syncGroupHierarchyFromPlotLevel() {
  const plot = ghEl["gh-plot"];
  const level = cleanAid(plot?.data?.[0]?.level || plot?._fullData?.[0]?.level || "ALL");
  const resolved = resolveGroupHierarchyNodeId(level) || "ALL";
  if (!ghState.rowById.has(resolved)) return;
  if (resolved === ghState.centerAid && resolved === ghState.selectedAid) return;
  ghState.centerAid = resolved;
  ghState.selectedAid = resolved;
  const row = ghState.rowById.get(resolved);
  const associationAid = row?.original_aid || row?.aid || resolved;
  ghEl["gh-aid-search"].value = associationAid === "ALL" ? "" : associationAid;
  updateGroupHierarchyUrl();
  updateGroupHierarchySummary();
  renderGroupHierarchySelection();
}

function handleGroupHierarchySunburstClick(event) {
  const nextLevel = cleanAid(event?.nextLevel || "");
  if (!nextLevel) return;
  const resolved = resolveGroupHierarchyNodeId(nextLevel);
  if (!resolved || !ghState.rowById.has(resolved)) return;
  window.setTimeout(() => {
    selectGroupHierarchyAid(resolved, { center: true, render: false });
  }, 820);
}

function updateGroupHierarchySummary() {
  const centerRow = ghState.rowById.get(ghState.centerAid);
  const centered = ghState.centerAid === "ALL" ? "all associations" : (centerRow?.original_aid || centerRow?.aid || ghState.centerAid);
  ghEl["gh-summary"].textContent = `${ghState.rows.length.toLocaleString()} hierarchy nodes displayed; centered on ${centered}`;
}

function renderGroupHierarchySelection() {
  const row = ghState.rowById.get(ghState.selectedAid) || ghState.rowById.get(ghState.centerAid) || ghState.rowById.get("ALL");
  if (!row) {
    ghEl["gh-selected-summary"].textContent = "No association selected";
    ghEl["gh-branch-stats"].innerHTML = "";
    ghEl["gh-detail-title"].textContent = "Selected association";
    ghEl["gh-details"].innerHTML = "";
    disableGroupHierarchyLinks();
    return;
  }
  ghState.selectedAid = row.id;
  const direct = ghState.directChildren[row.id] || [];
  const associationAid = row.original_aid || row.aid || row.id;
  const descendants = ghState.descendants[associationAid] || [];
  const branchAids = groupHierarchyBranchAids(associationAid);
  ghEl["gh-selected-summary"].innerHTML = `
    <strong>${escapeHtml(associationAid)}</strong>
    <span>${escapeHtml(row.name || row.label || "")}</span>
  `;
  ghEl["gh-branch-stats"].innerHTML = `
    <div><strong>${direct.length.toLocaleString()}</strong><span>direct children</span></div>
    <div><strong>${descendants.length.toLocaleString()}</strong><span>descendants</span></div>
    <div><strong>${branchAids.length.toLocaleString()}</strong><span>XYZ branch AIDs</span></div>
  `;
  ghEl["gh-detail-title"].textContent = associationAid === "ALL" ? "All associations" : `${associationAid}: ${row.name || row.label || ""}`;
  ghEl["gh-detail-subtitle"].textContent = row.parent_id ? `Parent: ${row.parent_id}` : "Root node";
  ghEl["gh-details"].innerHTML = groupHierarchyDetailsHtml(row, direct, descendants);
  updateGroupHierarchyLinks(row, branchAids);
}

function groupHierarchyDetailsHtml(row, direct, descendants) {
  const fields = [
    ["Display label", row.label],
    ["Other names", row.alternate_names],
    ["Physical nature", row.physical_nature],
    ["Age", row.age_myr ? `${row.age_myr} Myr${row.age_ref ? `, ${row.age_ref}` : ""}` : ""],
    ["Average distance", finite(row.avg_dist) ? `${formatNumber(row.avg_dist, 1)} pc` : ""],
    ["Branch", row.branch],
    ["Members", finite(row.nobj) ? formatNumber(row.nobj, 0) : ""],
    ["Suboptimal grouping", Number(row.suboptimal_grouping || 0) ? "yes" : "no"],
    ["Overlap", groupHierarchyOverlapText(row)],
    ["Relationship comments", row.relationship_comments],
    ["Comments", row.comments],
  ].filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "");
  const fieldHtml = fields.map(([label, value]) => `
    <div class="group-hierarchy-field">
      <dt>${escapeHtml(label)}</dt>
      <dd>${formatLongText(value)}</dd>
    </div>
  `).join("");
  const childHtml = direct.length
    ? direct.slice(0, 80).map((aid) => `<button type="button" class="gh-chip" data-aid="${escapeHtml(aid)}">${escapeHtml(aid)}</button>`).join("")
    : `<span class="plot-hint">No direct children in the current hierarchy.</span>`;
  const descendantNote = descendants.length > direct.length
    ? `<div class="plot-hint">${(descendants.length - direct.length).toLocaleString()} additional deeper descendants are included in the branch link.</div>`
    : "";
  window.requestAnimationFrame(() => {
    ghEl["gh-details"].querySelectorAll(".gh-chip").forEach((button) => {
      button.addEventListener("click", () => selectGroupHierarchyAid(button.dataset.aid, { center: true }));
    });
  });
  return `
    <dl class="group-hierarchy-fields">${fieldHtml}</dl>
    <div class="group-hierarchy-children">
      <strong>Direct children</strong>
      <div class="gh-chip-list">${childHtml}</div>
      ${descendantNote}
    </div>
  `;
}

function groupHierarchyOverlapText(row) {
  const bits = [];
  if (Number(row.partial_subgroup_overlap || 0)) bits.push("partial subgroup overlap");
  if (Number(row.complete_parent_overlap || 0)) bits.push("complete parent overlap");
  return bits.join("; ");
}

function selectGroupHierarchyAid(aid, options = {}) {
  const resolved = resolveGroupHierarchyNodeId(aid);
  if (!resolved || !ghState.rowById.has(resolved)) return;
  ghState.selectedAid = resolved;
  if (options.center) ghState.centerAid = resolved;
  const row = ghState.rowById.get(resolved);
  const associationAid = row?.original_aid || row?.aid || resolved;
  ghEl["gh-aid-search"].value = associationAid === "ALL" ? "" : associationAid;
  updateGroupHierarchyUrl();
  if (options.render !== false) renderGroupHierarchyPlot();
  else updateGroupHierarchySummary();
  renderGroupHierarchySelection();
}

function resolveGroupHierarchyInput(value) {
  const text = cleanAid(value);
  if (!text) return "";
  const direct = resolveGroupHierarchyNodeId(text);
  if (direct) return direct;
  const lower = text.toLowerCase();
  const option = ghState.options.find((candidate) => {
    return String(candidate.value || "").toLowerCase() === lower
      || String(candidate.label || "").toLowerCase().includes(lower)
      || String(candidate.name || "").toLowerCase().includes(lower);
  });
  return option?.value || "";
}

function resolveGroupHierarchyNodeId(value) {
  const text = cleanAid(value);
  if (!text) return "";
  if (ghState.rowById.has(text)) return text;
  const byAid = ghState.rowByAid.get(text);
  if (byAid) return byAid.id;
  const lower = text.toLowerCase();
  for (const [aid, row] of ghState.rowByAid.entries()) {
    if (String(aid).toLowerCase() === lower) return row.id;
  }
  return "";
}

function updateGroupHierarchyUrl() {
  const url = new URL(window.location.href);
  const row = ghState.rowById.get(ghState.centerAid);
  const associationAid = row?.original_aid || row?.aid || row?.id || "";
  if (associationAid && associationAid !== "ALL") url.searchParams.set("asso", associationAid);
  else url.searchParams.delete("asso");
  if (row?.id && row.id !== associationAid) url.searchParams.set("node", row.id);
  else url.searchParams.delete("node");
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function updateGroupHierarchyLinks(row, branchAids) {
  const associationAid = row.original_aid || row.aid || row.id;
  const reportUrl = associationAid === "ALL" ? "" : `https://mocadb.ca/search/results?search-query=${encodeURIComponent(associationAid)}&search-type=association`;
  const xyzUrl = associationAid === "ALL" ? "" : groupHierarchyXyzUrl(branchAids);
  const memberUrl = associationAid === "ALL" ? "" : groupHierarchyMemberQueryUrl(associationAid);
  setActionLink(ghEl["gh-report-link"], reportUrl);
  setActionLink(ghEl["gh-xyz-link"], xyzUrl);
  setActionLink(ghEl["gh-members-link"], memberUrl);
  ghEl["gh-link-list"].innerHTML = associationAid === "ALL"
    ? `<div class="plot-hint">Select an association to build branch links.</div>`
    : `
      <a href="${escapeHtml(reportUrl)}" target="_blank" rel="noopener">Open MOCAdb report</a>
      <a href="${escapeHtml(xyzUrl)}" target="_blank" rel="noopener">Open JS XYZ map for ${branchAids.length.toLocaleString()} AIDs</a>
      <a href="${escapeHtml(memberUrl)}" target="_blank" rel="noopener">Open member query</a>
    `;
}

function groupHierarchyBranchAids(aid) {
  if (!aid || aid === "ALL") return [];
  return [aid, ...(ghState.descendants[aid] || [])].filter((value, index, array) => value && array.indexOf(value) === index);
}

function groupHierarchyXyzUrl(branchAids) {
  const url = new URL("xyz", ghAppBaseUrl);
  url.searchParams.set("axes", "xyz");
  url.searchParams.set("asso", branchAids.join(","));
  url.searchParams.set("mtid", "BF,HM,CM");
  addConnectionParams(url.searchParams);
  return sameOriginPath(url);
}

function groupHierarchyMemberQueryUrl(aid) {
  const safeAid = String(aid || "").replace(/'/g, "''");
  const query = `SELECT sam.* FROM summary_all_members sam LEFT JOIN moca_membership_types mmt ON(mmt.moca_mtid=sam.moca_mtid) WHERE moca_aid='${safeAid}' ORDER BY mmt.level DESC,sam.sptn ASC`;
  const url = new URL("https://mocadb.ca/query");
  url.searchParams.set("query", query);
  return url.toString();
}

function setActionLink(link, href) {
  if (!href) {
    link.href = "#";
    link.classList.add("is-disabled");
    link.setAttribute("aria-disabled", "true");
    return;
  }
  link.href = href;
  link.classList.remove("is-disabled");
  link.removeAttribute("aria-disabled");
}

function disableGroupHierarchyLinks() {
  for (const id of ["gh-report-link", "gh-xyz-link", "gh-members-link"]) setActionLink(ghEl[id], "");
  ghEl["gh-link-list"].innerHTML = `<div class="plot-hint">Select an association to build branch links.</div>`;
}

async function clearGroupHierarchyCache() {
  ghEl["gh-clear-cache"].disabled = true;
  ghEl["gh-clear-cache-status"].textContent = "Clearing cache...";
  try {
    const payload = await postGroupHierarchyJson("api/group-hierarchy/cache/clear");
    ghEl["gh-clear-cache-status"].textContent = `Cleared ${payload.cleared?.groupHierarchy ?? 0} cached entries.`;
    await loadGroupHierarchyCatalog();
  } catch (error) {
    ghEl["gh-clear-cache-status"].textContent = error.message || String(error);
  } finally {
    ghEl["gh-clear-cache"].disabled = false;
  }
}

function renderGroupHierarchyEmpty(message = "No association hierarchy is loaded.") {
  const layout = {
    annotations: [{
      text: message,
      x: 0.5,
      y: 0.5,
      xref: "paper",
      yref: "paper",
      showarrow: false,
      font: { size: 16, color: "#5f5864" },
    }],
    xaxis: { visible: false },
    yaxis: { visible: false },
    margin: { l: 12, r: 12, t: 12, b: 12 },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
  };
  const drawPromise = Plotly.react(ghEl["gh-plot"], [], layout, groupHierarchyPlotConfig());
  ghEl["gh-summary"].textContent = message;
  ghEl["gh-details"].innerHTML = "";
  disableGroupHierarchyLinks();
  return drawPromise;
}

function groupHierarchyHoverText(row) {
  const associationAid = row.original_aid || row.aid || row.id;
  const lines = [
    `<b>${escapeHtml(row.name || associationAid)}</b>`,
    `AID: ${escapeHtml(associationAid)}`,
    row.id !== associationAid ? `Node: ${escapeHtml(row.id)}` : "",
    row.alternate_names ? `Other names: ${escapeHtml(row.alternate_names)}` : "",
    row.physical_nature ? `Type: ${escapeHtml(row.physical_nature)}` : "",
    row.age_myr ? `Age: ${escapeHtml(row.age_myr)} Myr${row.age_ref ? `, ${escapeHtml(row.age_ref)}` : ""}` : "",
    finite(row.avg_dist) ? `Distance: ${formatNumber(row.avg_dist, 1)} pc` : "",
    Number(row.partial_subgroup_overlap || 0) ? "Only a subset of this group overlaps with parent" : "",
    Number(row.complete_parent_overlap || 0) ? "Complete overlap with parent" : "",
  ].filter(Boolean);
  return lines.join("<br>");
}

function groupHierarchyColor(row) {
  if ((row.original_aid || row.aid || row.id) === "ALL") return "#4A4650";
  if (Number(row.suboptimal_grouping || 0)) return "#A5A0AA";
  const nature = String(row.physical_nature || "").toLowerCase();
  for (const [key, color] of Object.entries(ghNatureColors)) {
    if (key && nature.includes(key)) return color;
  }
  return ghNatureColors[""];
}

function groupHierarchyPlotConfig() {
  return {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d"],
    toImageButtonOptions: {
      format: "png",
      filename: "mocadb_group_hierarchy",
      width: 1600,
      height: 1100,
      scale: 3,
    },
  };
}

function groupHierarchyConnectionParams() {
  const params = new URLSearchParams();
  addConnectionParams(params);
  return params;
}

function addConnectionParams(params) {
  const source = new URLSearchParams(window.location.search);
  for (const key of ["host", "port", "user", "pwd", "dbase", "mock"]) {
    const value = source.get(key);
    if (value) params.set(key, value);
  }
}

async function fetchGroupHierarchyJson(path) {
  const response = await fetch(ghAppUrl(path));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function postGroupHierarchyJson(path) {
  const response = await fetch(ghAppUrl(path), { method: "POST" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function setGroupHierarchyStatus(message, kind = "") {
  ghEl["gh-status"].textContent = message;
  ghEl["gh-status"].classList.toggle("loading", kind === "loading");
  ghEl["gh-status"].classList.toggle("error", kind === "error");
}

function setGroupHierarchyLoading(active) {
  ghEl["gh-plot-loader"].classList.toggle("is-visible", Boolean(active));
  ghEl["gh-reload"].disabled = Boolean(active);
}

function cleanAid(value) {
  return String(value || "").trim();
}

function finite(value) {
  return Number.isFinite(Number(value));
}

function formatNumber(value, digits = 1) {
  if (!finite(value)) return "";
  return Number(value).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });
}

function formatLongText(value) {
  return escapeHtml(String(value || ""))
    .replace(/\. /g, ".<br>")
    .replace(/al\.<br> /g, "al. ");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sameOriginPath(url) {
  return url.origin === window.location.origin
    ? `${url.pathname}${url.search}${url.hash}`
    : url.toString();
}
