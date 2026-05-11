const atmDefaultOid = 602;
const atmMissionColors = ["#377EB8", "#E41A1C", "#4DAF4A", "#984EA3", "#FF7F00", "#A65628", "#F781BF", "#999999", "#66C2A5", "#FC8D62"];
const atmBinSizeDays = 50;
const atmPhaseBinSizeDays = 20;

const atmState = {
  selectedOid: null,
  selectedTargetLabel: "",
  payload: null,
  selectedMissions: new Set(),
  selectedIds: new Set(),
  processedRows: [],
  searchTimer: null,
  hasUserMissionChoice: false,
  initialMissions: [],
};

const atmEl = {};

document.addEventListener("DOMContentLoaded", initAstrometry);

const atmAppBaseUrl = (() => {
  const scriptUrl = document.currentScript?.src;
  if (scriptUrl) return new URL("../", scriptUrl).toString();
  const path = window.location.pathname.endsWith("/") ? window.location.pathname : `${window.location.pathname}/`;
  return new URL(path, window.location.origin).toString();
})();

function atmAppUrl(path) {
  return new URL(String(path || "").replace(/^\/+/, ""), atmAppBaseUrl).toString();
}

async function initAstrometry() {
  collectAstrometryElements();
  readAstrometryUrlState();
  bindAstrometryControls();
  if (atmState.selectedOid === null) atmState.selectedOid = atmDefaultOid;
  atmEl["atm-target-search"].value = `oid${atmState.selectedOid}`;
  await searchAstrometryTargets("", { selectedOid: atmState.selectedOid, quiet: true });
  await loadAstrometryObject();
}

function collectAstrometryElements() {
  [
    "atm-status",
    "atm-target-search",
    "atm-target-results",
    "atm-selected-target-text",
    "atm-clear-target",
    "atm-open-report",
    "atm-missions-all",
    "atm-missions-none",
    "atm-mission-list",
    "atm-subtract-pm",
    "atm-subtract-plx",
    "atm-phase-yearly",
    "atm-bin",
    "atm-adjust-reference",
    "atm-only-recalibrated",
    "atm-revert-raw",
    "atm-ra-plot",
    "atm-dec-plot",
    "atm-plot-loader",
    "atm-summary",
    "atm-export-csv",
    "atm-clear-cache",
    "atm-table-title",
    "atm-table-subtitle",
    "atm-table",
  ].forEach((id) => {
    atmEl[id] = document.getElementById(id);
  });
}

function readAstrometryUrlState() {
  const params = new URLSearchParams(window.location.search);
  atmState.selectedOid = parseInteger(params.get("moca_oid") || params.get("oid"));
  atmState.initialMissions = (params.get("missions") || "").split(",").map((item) => item.trim()).filter(Boolean);
  atmEl["atm-subtract-pm"].checked = asBool(params.get("subtract_pm"));
  atmEl["atm-subtract-plx"].checked = asBool(params.get("subtract_plx"));
  atmEl["atm-phase-yearly"].checked = asBool(params.get("phase"));
  atmEl["atm-bin"].checked = asBool(params.get("bin"));
  atmEl["atm-adjust-reference"].checked = !asFalse(params.get("adjust_ref"));
  atmEl["atm-only-recalibrated"].checked = !asFalse(params.get("only_recalibrated"));
  atmEl["atm-revert-raw"].checked = asBool(params.get("revert_raw"));
}

function bindAstrometryControls() {
  atmEl["atm-target-search"].addEventListener("input", () => {
    const value = atmEl["atm-target-search"].value.trim();
    clearTimeout(atmState.searchTimer);
    atmState.searchTimer = setTimeout(() => searchAstrometryTargets(value), 250);
  });
  atmEl["atm-target-search"].addEventListener("focus", () => {
    const value = atmEl["atm-target-search"].value.trim();
    if (value) searchAstrometryTargets(value);
  });
  document.addEventListener("click", (event) => {
    if (!atmEl["atm-target-results"].contains(event.target) && event.target !== atmEl["atm-target-search"]) {
      atmEl["atm-target-results"].hidden = true;
    }
  });
  atmEl["atm-clear-target"].addEventListener("click", () => {
    atmState.selectedOid = null;
    atmState.selectedTargetLabel = "";
    atmState.payload = null;
    atmState.selectedIds.clear();
    atmEl["atm-target-search"].value = "";
    updateSelectedTargetDisplay();
    updateAstrometryUrl();
    renderEmptyAstrometry("Select a target");
    atmEl["atm-target-search"].focus();
  });
  atmEl["atm-open-report"].addEventListener("click", () => {
    if (atmState.selectedOid !== null) window.open(mocaReportUrl(atmState.selectedOid), "_blank", "noopener");
  });
  atmEl["atm-missions-all"].addEventListener("click", () => {
    atmState.selectedMissions = new Set((atmState.payload?.missions || []).map((row) => row.value));
    atmState.hasUserMissionChoice = true;
    renderMissionList();
    renderAstrometry();
  });
  atmEl["atm-missions-none"].addEventListener("click", () => {
    atmState.selectedMissions.clear();
    atmState.hasUserMissionChoice = true;
    renderMissionList();
    renderAstrometry();
  });
  for (const id of ["atm-subtract-pm", "atm-subtract-plx", "atm-phase-yearly", "atm-bin", "atm-adjust-reference", "atm-only-recalibrated", "atm-revert-raw"]) {
    atmEl[id].addEventListener("change", () => {
      renderAstrometry();
      updateAstrometryUrl();
    });
  }
  atmEl["atm-export-csv"].addEventListener("click", exportAstrometryCsv);
  atmEl["atm-clear-cache"].addEventListener("click", clearAstrometryCache);
  window.addEventListener("resize", debounce(() => {
    if (!atmEl["atm-target-results"].hidden) positionAstrometrySearchPopup();
    if (atmState.payload) renderAstrometry();
  }, 150));
}

async function searchAstrometryTargets(query, options = {}) {
  const selectedOid = options.selectedOid ?? null;
  const quiet = Boolean(options.quiet);
  if (!query && selectedOid === null) {
    atmEl["atm-target-results"].hidden = true;
    return;
  }
  if (!quiet && query.length < 2 && !/^\d+$/.test(query)) {
    atmEl["atm-target-results"].innerHTML = `<div class="designation-result-note">Type at least two characters</div>`;
    showAstrometrySearchPopup();
    return;
  }
  const params = apiParams();
  if (query) params.set("q", query);
  if (selectedOid !== null) params.set("moca_oid", selectedOid);
  const payload = await fetchJsonUrl(atmAppUrl(`api/astrometry/search?${params.toString()}`));
  if (!payload.ok) {
    if (!quiet) {
      atmEl["atm-target-results"].innerHTML = `<div class="designation-result-note">${escapeHtml(payload.error || "Search failed")}</div>`;
      showAstrometrySearchPopup();
    }
    return;
  }
  const results = payload.options || [];
  if (selectedOid !== null && results.length) {
    selectAstrometryTarget(results[0], { deferLoad: true });
    return;
  }
  renderAstrometrySearchResults(results);
}

function renderAstrometrySearchResults(results) {
  if (!results.length) {
    atmEl["atm-target-results"].innerHTML = `<div class="designation-result-note">No targets found</div>`;
    showAstrometrySearchPopup();
    return;
  }
  atmEl["atm-target-results"].innerHTML = results.map((result, index) => (
    `<button class="designation-result" type="button" data-index="${index}"><span>${escapeHtml(result.label || `oid${result.value}`)}</span></button>`
  )).join("");
  atmEl["atm-target-results"].querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      const result = results[Number(button.dataset.index)];
      selectAstrometryTarget(result);
      atmEl["atm-target-results"].hidden = true;
      await loadAstrometryObject();
    });
  });
  showAstrometrySearchPopup();
}

function showAstrometrySearchPopup() {
  positionAstrometrySearchPopup();
  atmEl["atm-target-results"].hidden = false;
}

function positionAstrometrySearchPopup() {
  const input = atmEl["atm-target-search"];
  const popup = atmEl["atm-target-results"];
  if (!input || !popup) return;
  const rect = input.getBoundingClientRect();
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - 320));
  const available = Math.max(280, window.innerWidth - left - 16);
  const width = Math.min(760, available);
  popup.style.left = `${left}px`;
  popup.style.top = `${rect.bottom + 4}px`;
  popup.style.width = `${Math.max(rect.width, width)}px`;
}

function selectAstrometryTarget(option, options = {}) {
  const oid = parseInteger(option.value ?? option.moca_oid);
  if (oid === null) return;
  const changed = atmState.selectedOid !== oid;
  atmState.selectedOid = oid;
  atmState.selectedTargetLabel = option.label || `oid${oid}`;
  if (changed) {
    atmState.payload = null;
    atmState.selectedIds.clear();
    atmState.selectedMissions.clear();
    atmState.initialMissions = [];
    atmState.hasUserMissionChoice = false;
  }
  atmEl["atm-target-search"].value = atmState.selectedTargetLabel;
  updateSelectedTargetDisplay();
  if (!options.deferLoad) updateAstrometryUrl();
}

async function loadAstrometryObject() {
  if (atmState.selectedOid === null) {
    renderEmptyAstrometry("Select a target");
    return;
  }
  setAstrometryLoading(true);
  setAstrometryStatus("Loading astrometry", "loading");
  const payload = await fetchAstrometryJson(`api/astrometry/object/${atmState.selectedOid}`);
  setAstrometryLoading(false);
  if (!payload.ok) {
    atmState.payload = null;
    setAstrometryStatus(payload.error || "Could not load astrometry", "error");
    renderEmptyAstrometry(payload.error || "Could not load astrometry");
    return;
  }
  atmState.payload = payload;
  atmState.selectedTargetLabel = targetLabel(payload.target);
  atmEl["atm-target-search"].value = atmState.selectedTargetLabel;
  updateSelectedTargetDisplay();
  initializeMissionSelection();
  renderMissionList();
  renderAstrometry();
  setAstrometryStatus(`${payload.meta?.row_count || 0} astrometric measurements loaded${payload.cache?.hit ? " from cache" : ""}`, "");
}

function initializeMissionSelection() {
  const available = new Set((atmState.payload?.missions || []).map((row) => row.value));
  if (atmState.hasUserMissionChoice) {
    atmState.selectedMissions = new Set([...atmState.selectedMissions].filter((mission) => available.has(mission)));
    return;
  }
  if (atmState.initialMissions.length) {
    atmState.selectedMissions = new Set(atmState.initialMissions.filter((mission) => available.has(mission)));
  } else {
    atmState.selectedMissions = new Set(available);
  }
}

function renderMissionList() {
  const missions = atmState.payload?.missions || [];
  if (!missions.length) {
    atmEl["atm-mission-list"].innerHTML = `<div class="plot-hint">No missions loaded</div>`;
    return;
  }
  atmEl["atm-mission-list"].innerHTML = missions.map((mission) => (
    `<label class="checkline mission-check">
      <input type="checkbox" value="${escapeHtml(mission.value)}" ${atmState.selectedMissions.has(mission.value) ? "checked" : ""}>
      <span>${escapeHtml(mission.label || mission.value)}</span>
    </label>`
  )).join("");
  atmEl["atm-mission-list"].querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) atmState.selectedMissions.add(input.value);
      else atmState.selectedMissions.delete(input.value);
      atmState.hasUserMissionChoice = true;
      renderAstrometry();
      updateAstrometryUrl();
    });
  });
}

function updateSelectedTargetDisplay() {
  const hasTarget = atmState.selectedOid !== null;
  atmEl["atm-selected-target-text"].textContent = hasTarget ? atmState.selectedTargetLabel || `oid${atmState.selectedOid}` : "No target selected";
  atmEl["atm-clear-target"].hidden = !hasTarget;
  atmEl["atm-open-report"].disabled = !hasTarget;
}

function renderAstrometry() {
  if (!atmState.payload) {
    renderEmptyAstrometry("No target loaded");
    return;
  }
  const prepared = prepareAstrometryRows();
  atmState.processedRows = prepared.rows;
  renderAstrometryPlot("ra", prepared);
  renderAstrometryPlot("dec", prepared);
  renderAstrometrySummary(prepared);
  renderAstrometryTable();
  updateAstrometryUrl();
  atmEl["atm-export-csv"].disabled = !atmState.processedRows.length;
}

function prepareAstrometryRows() {
  const payload = atmState.payload;
  const allRows = (payload.rows || []).map((row) => ({ ...row }));
  const recalFiltered = atmEl["atm-only-recalibrated"].checked
    ? allRows.filter((row) => row.calibration_method || Number(row.include_in_recalibrated_display) === 1)
    : allRows;
  const baseRows = recalFiltered.length ? recalFiltered : allRows;
  const missionRows = baseRows.filter((row) => atmState.selectedMissions.has(String(row.mission || "No mission")));
  const rows = missionRows.filter((row) => finite(row.measurement_epoch_yr));
  const useRaw = atmEl["atm-revert-raw"].checked;
  const reference = normalizedReference(payload.reference, rows, useRaw);
  const pm = payload.pm || {};
  const plx = payload.parallax || {};
  const pmra = finite(pm.pmra_masyr) ? Number(pm.pmra_masyr) : 0;
  const pmdec = finite(pm.pmdec_masyr) ? Number(pm.pmdec_masyr) : 0;
  const pmraUnc = finite(pm.pmra_masyr_unc) ? Number(pm.pmra_masyr_unc) : 0;
  const pmdecUnc = finite(pm.pmdec_masyr_unc) ? Number(pm.pmdec_masyr_unc) : 0;
  const plxValue = finite(plx.parallax_mas) ? Number(plx.parallax_mas) : 0;
  const plxUnc = finite(plx.parallax_mas_unc) ? Number(plx.parallax_mas_unc) : 0;
  let refRa = reference.ra;
  let refDec = reference.dec;
  let refEpoch = reference.epoch;
  if (atmEl["atm-adjust-reference"].checked && rows.length) {
    const epochs = rows.map((row) => Number(row.measurement_epoch_yr)).filter(finite);
    const targetEpoch = mean(epochs);
    if (finite(targetEpoch)) {
      const finitePositions = rows.map((row) => astrometryPosition(row, useRaw)).filter((pos) => finite(pos.ra) && finite(pos.dec));
      const meanRa = mean(finitePositions.map((pos) => pos.ra));
      const meanDec = mean(finitePositions.map((pos) => pos.dec));
      const raCandidates = [];
      const decCandidates = [];
      rows.forEach((row) => {
        const pos = astrometryPosition(row, useRaw);
        const epoch = Number(row.measurement_epoch_yr);
        if (!finite(pos.ra) || !finite(pos.dec) || !finite(epoch)) return;
        const cosDec = Math.cos(rad(pos.dec));
        if (!finite(cosDec) || Math.abs(cosDec) < 1e-9) return;
        const pf = finite(meanRa) && finite(meanDec) ? parallaxMotion(meanRa, meanDec, epoch) : { ra: 0, dec: 0 };
        let raObserved = pos.ra * cosDec * 3600 * 1000;
        let decObserved = pos.dec * 3600 * 1000;
        raObserved -= pmra * (epoch - targetEpoch);
        decObserved -= pmdec * (epoch - targetEpoch);
        raObserved -= plxValue * pf.ra;
        decObserved -= plxValue * pf.dec;
        raCandidates.push(raObserved / (cosDec * 3600 * 1000));
        decCandidates.push(decObserved / (3600 * 1000));
      });
      const candidateRa = median(raCandidates);
      const candidateDec = median(decCandidates);
      if (finite(candidateRa) && finite(candidateDec)) {
        refRa = candidateRa;
        refDec = candidateDec;
      }
      refEpoch = targetEpoch;
    }
  }
  const processed = rows.map((row) => {
    const pos = astrometryPosition(row, useRaw);
    const ra = pos.ra;
    const dec = pos.dec;
    const epoch = Number(row.measurement_epoch_yr);
    const pf = parallaxMotion(refRa, refDec, epoch);
    let relRa = (ra - refRa) * Math.cos(rad(refDec)) * 3600 * 1000;
    let relDec = (dec - refDec) * 3600 * 1000;
    if (atmEl["atm-subtract-pm"].checked) {
      relRa -= pmra * (epoch - refEpoch);
      relDec -= pmdec * (epoch - refEpoch);
    }
    if (atmEl["atm-subtract-plx"].checked) {
      relRa -= plxValue * pf.ra;
      relDec -= plxValue * pf.dec;
    }
    const x = atmEl["atm-phase-yearly"].checked ? yearlyPhase(epoch) : epoch;
    return {
      ...row,
      plot_x: x,
      plot_epoch_abs: epoch,
      rel_ra: relRa,
      rel_dec: relDec,
      plot_ra: ra,
      plot_dec: dec,
    };
  }).filter((row) => finite(row.rel_ra) && finite(row.rel_dec));
  const xValues = processed.map((row) => row.plot_x).filter(finite);
  const xRange = paddedRange(xValues, atmEl["atm-phase-yearly"].checked ? [0, 1] : null);
  const model = buildAstrometryModel({
    xRange,
    rows: processed,
    refRa,
    refDec,
    refEpoch,
    pmra,
    pmdec,
    pmraUnc,
    pmdecUnc,
    plxValue,
    plxUnc,
  });
  const binned = atmEl["atm-bin"].checked ? binAstrometryRows(processed) : [];
  return {
    rows: processed,
    binned,
    model,
    reference: { ra: refRa, dec: refDec, epoch: refEpoch },
    pm: { pmra, pmdec, pmraUnc, pmdecUnc, reference: pm.reference },
    parallax: { value: plxValue, uncertainty: plxUnc, reference: plx.reference },
    usedFallbackRecalibration: atmEl["atm-only-recalibrated"].checked && !recalFiltered.length && allRows.length > 0,
  };
}

function astrometryPosition(row, useRaw) {
  const rawRa = useRaw ? row.raw_ra : row.ra;
  const rawDec = useRaw ? row.raw_dec : row.dec;
  const ra = finite(rawRa) ? Number(rawRa) : Number(row.ra);
  const dec = finite(rawDec) ? Number(rawDec) : Number(row.dec);
  return { ra, dec };
}

function normalizedReference(reference, rows, useRaw) {
  let ra = finite(useRaw ? reference?.raw_ra : reference?.ra) ? Number(useRaw ? reference.raw_ra : reference.ra) : NaN;
  let dec = finite(useRaw ? reference?.raw_dec : reference?.dec) ? Number(useRaw ? reference.raw_dec : reference.dec) : NaN;
  let epoch = finite(reference?.measurement_epoch_yr) ? Number(reference.measurement_epoch_yr) : NaN;
  if (!finite(ra) || !finite(dec) || !finite(epoch)) {
    const usable = rows.filter((row) => {
      const pos = astrometryPosition(row, useRaw);
      return finite(pos.ra) && finite(pos.dec) && finite(row.measurement_epoch_yr);
    });
    if (usable.length) {
      const sorted = [...usable].sort((a, b) => Number(a.measurement_epoch_yr) - Number(b.measurement_epoch_yr));
      const mid = sorted[Math.floor(sorted.length / 2)];
      const pos = astrometryPosition(mid, useRaw);
      ra = Number(pos.ra);
      dec = Number(pos.dec);
      epoch = Number(mid.measurement_epoch_yr);
    }
  }
  return { ra, dec, epoch };
}

function buildAstrometryModel({ xRange, rows, refRa, refDec, refEpoch, pmra, pmdec, pmraUnc, pmdecUnc, plxValue, plxUnc }) {
  if (!rows.length || !finite(xRange[0]) || !finite(xRange[1]) || xRange[0] === xRange[1]) {
    return { x: [], ra: [], dec: [], raUpper: [], raLower: [], decUpper: [], decLower: [] };
  }
  const n = 500;
  const centerEpoch = mean(rows.map((row) => Number(row.plot_epoch_abs)).filter(finite));
  const roundedCenter = Math.round(centerEpoch || refEpoch || 0);
  const x = [];
  const ra = [];
  const dec = [];
  const raUpper = [];
  const raLower = [];
  const decUpper = [];
  const decLower = [];
  for (let index = 0; index < n; index += 1) {
    const frac = n <= 1 ? 0 : index / (n - 1);
    const xv = xRange[0] + frac * (xRange[1] - xRange[0]);
    const epoch = atmEl["atm-phase-yearly"].checked ? xv + roundedCenter : xv;
    const dt = epoch - refEpoch;
    const pf = parallaxMotion(refRa, refDec, epoch);
    let modelRa = atmEl["atm-subtract-pm"].checked ? 0 : pmra * dt;
    let modelDec = atmEl["atm-subtract-pm"].checked ? 0 : pmdec * dt;
    if (!atmEl["atm-subtract-plx"].checked) {
      modelRa += plxValue * pf.ra;
      modelDec += plxValue * pf.dec;
    }
    const pmRaSigma = atmEl["atm-subtract-pm"].checked ? 0 : Math.abs(dt * pmraUnc);
    const pmDecSigma = atmEl["atm-subtract-pm"].checked ? 0 : Math.abs(dt * pmdecUnc);
    const plxRaSigma = atmEl["atm-subtract-plx"].checked ? 0 : Math.abs(pf.ra * plxUnc);
    const plxDecSigma = atmEl["atm-subtract-plx"].checked ? 0 : Math.abs(pf.dec * plxUnc);
    const sigRa = Math.sqrt(pmRaSigma ** 2 + plxRaSigma ** 2);
    const sigDec = Math.sqrt(pmDecSigma ** 2 + plxDecSigma ** 2);
    x.push(xv);
    ra.push(modelRa);
    dec.push(modelDec);
    raLower.push(modelRa - sigRa);
    raUpper.push(modelRa + sigRa);
    decLower.push(modelDec - sigDec);
    decUpper.push(modelDec + sigDec);
  }
  return { x, ra, dec, raUpper, raLower, decUpper, decLower };
}

function binAstrometryRows(rows) {
  const phase = atmEl["atm-phase-yearly"].checked;
  const binWidth = (phase ? atmPhaseBinSizeDays : atmBinSizeDays) / 365.25;
  const groups = new Map();
  rows.forEach((row) => {
    const key = Math.floor(Number(row.plot_x) / binWidth) * binWidth;
    const label = Number(key.toFixed(6));
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(row);
  });
  return [...groups.entries()].map(([x, group]) => {
    const ra = weightedAverage(group, "rel_ra", "ra_unc_mas");
    const dec = weightedAverage(group, "rel_dec", "dec_unc_mas");
    return {
      id: `bin-${x}`,
      plot_x: x,
      rel_ra: ra.value,
      rel_dec: dec.value,
      ra_unc_mas: ra.uncertainty,
      dec_unc_mas: dec.uncertainty,
      ndata: group.length,
      mission: "Binned data",
    };
  }).filter((row) => finite(row.rel_ra) && finite(row.rel_dec));
}

function weightedAverage(rows, valueKey, errorKey) {
  const values = rows
    .map((row) => ({ value: Number(row[valueKey]), error: Math.max(Number(row[errorKey]) || 1, 1e-6) }))
    .filter((item) => finite(item.value) && finite(item.error));
  if (!values.length) return { value: NaN, uncertainty: NaN };
  if (values.length === 1) return { value: values[0].value, uncertainty: values[0].error };
  const weights = values.map((item) => 1 / item.error ** 2);
  const weightSum = weights.reduce((sum, value) => sum + value, 0);
  const meanValue = values.reduce((sum, item, index) => sum + item.value * weights[index], 0) / weightSum;
  const variance = values.reduce((sum, item, index) => sum + weights[index] * (item.value - meanValue) ** 2, 0) / weightSum;
  return { value: meanValue, uncertainty: Math.sqrt(Math.max(variance, 0)) };
}

function renderAstrometryPlot(axis, prepared) {
  const isRa = axis === "ra";
  const plotEl = isRa ? atmEl["atm-ra-plot"] : atmEl["atm-dec-plot"];
  const traces = [];
  const modelY = isRa ? prepared.model.ra : prepared.model.dec;
  const lower = isRa ? prepared.model.raLower : prepared.model.decLower;
  const upper = isRa ? prepared.model.raUpper : prepared.model.decUpper;
  traces.push({
    x: prepared.model.x,
    y: modelY,
    type: "scatter",
    mode: "lines",
    line: { color: "rgba(55,126,184,0.72)", width: 4 },
    name: "MOCAdb solution",
    hoverinfo: "skip",
  });
  traces.push({
    x: prepared.model.x,
    y: lower,
    type: "scatter",
    mode: "lines",
    line: { width: 0 },
    showlegend: false,
    hoverinfo: "skip",
  });
  traces.push({
    x: prepared.model.x,
    y: upper,
    type: "scatter",
    mode: "lines",
    line: { width: 0 },
    fill: "tonexty",
    fillcolor: "rgba(55,126,184,0.16)",
    name: "Model +/-1 sigma",
    showlegend: isRa,
    hoverinfo: "skip",
  });
  const missions = [...new Set(prepared.rows.map((row) => String(row.mission || "No mission")))];
  missions.forEach((mission, index) => {
    const rows = prepared.rows.filter((row) => String(row.mission || "No mission") === mission);
    traces.push({
      x: rows.map((row) => row.plot_x),
      y: rows.map((row) => isRa ? row.rel_ra : row.rel_dec),
      customdata: rows.map((row) => row.id),
      text: rows.map((row) => hoverText(row)),
      type: "scatter",
      mode: "markers",
      marker: {
        size: atmEl["atm-bin"].checked ? 7 : 8,
        color: atmMissionColors[index % atmMissionColors.length],
        opacity: atmEl["atm-bin"].checked ? 0.36 : 0.9,
        line: { width: 1.4, color: "rgba(255,255,255,0.82)" },
      },
      error_y: {
        type: "data",
        array: rows.map((row) => Number(isRa ? row.ra_unc_mas : row.dec_unc_mas) || 0),
        visible: true,
        color: "rgba(0,0,0,0.25)",
        thickness: 1.2,
        width: 2,
      },
      name: mission,
      legendgroup: mission,
      hovertemplate: "%{text}<extra></extra>",
    });
  });
  if (prepared.binned.length) {
    traces.push({
      x: prepared.binned.map((row) => row.plot_x),
      y: prepared.binned.map((row) => isRa ? row.rel_ra : row.rel_dec),
      text: prepared.binned.map((row) => `Binned data<br>N=${row.ndata}<br>${isRa ? "R.A." : "Decl."} offset: ${formatNumber(isRa ? row.rel_ra : row.rel_dec, 1)} mas`),
      type: "scatter",
      mode: "markers",
      marker: { size: 11, color: "white", line: { width: 2.5, color: "black" } },
      error_y: {
        type: "data",
        array: prepared.binned.map((row) => Number(isRa ? row.ra_unc_mas : row.dec_unc_mas) || 0),
        visible: true,
        color: "rgba(0,0,0,0.35)",
        thickness: 1.5,
        width: 2,
      },
      name: "Binned data",
      hovertemplate: "%{text}<extra></extra>",
    });
  }
  const yValues = [
    ...prepared.rows.map((row) => isRa ? row.rel_ra : row.rel_dec),
    ...modelY,
  ].filter(finite);
  const layout = {
    title: {
      text: `${isRa ? "R.A." : "Decl."} offsets for ${escapeHtml(targetShortName(atmState.payload.target))}`,
      x: 0.5,
      xanchor: "center",
      y: 0.98,
      yanchor: "top",
    },
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    margin: { t: 58, r: 220, b: 76, l: 72 },
    xaxis: {
      title: { text: atmEl["atm-phase-yearly"].checked ? "Yearly phase" : "Epoch (year)", font: { size: 20 }, standoff: 18 },
      tickfont: { size: 15 },
      tickformat: atmEl["atm-phase-yearly"].checked ? ".2f" : ".1f",
      separatethousands: false,
      automargin: true,
      range: paddedRange(prepared.rows.map((row) => row.plot_x).filter(finite), atmEl["atm-phase-yearly"].checked ? [0, 1] : null),
      zeroline: false,
    },
    yaxis: {
      title: { text: `${isRa ? "R.A." : "Decl."} offset (mas)`, font: { size: 20 } },
      tickfont: { size: 15 },
      range: paddedRange(yValues, null),
      zeroline: true,
      zerolinecolor: "#c8c5cc",
    },
    legend: {
      orientation: "v",
      x: 1.02,
      xanchor: "left",
      y: 1,
      yanchor: "top",
      font: { size: 11 },
      bgcolor: "rgba(255,255,255,0.86)",
      groupclick: "togglegroup",
    },
    annotations: isRa ? [summaryAnnotation(prepared)] : [],
  };
  Plotly.react(plotEl, traces, layout, plotConfig(`astrometry_${axis}_oid_${atmState.selectedOid || "unknown"}`));
  plotEl.on("plotly_selected", (event) => handleAstrometrySelection(event));
  plotEl.on("plotly_click", (event) => handleAstrometryClick(event));
}

function summaryAnnotation(prepared) {
  const pm = prepared.pm;
  const plx = prepared.parallax;
  return {
    xref: "paper",
    yref: "paper",
    x: 0.01,
    y: 0.99,
    xanchor: "left",
    yanchor: "top",
    text: `<b>PMRA:</b> ${formatValueError(pm.pmra, pm.pmraUnc, "mas/yr")} | <b>PMDEC:</b> ${formatValueError(pm.pmdec, pm.pmdecUnc, "mas/yr")} | <b>Parallax:</b> ${formatValueError(plx.value, plx.uncertainty, "mas")}`,
    showarrow: false,
    font: { size: 13, color: "#252329" },
    bgcolor: "rgba(255,255,255,0.72)",
  };
}

function handleAstrometrySelection(event) {
  const ids = (event?.points || []).map((point) => point.customdata).filter((id) => id !== undefined && id !== null);
  atmState.selectedIds = new Set(ids);
  renderAstrometryTable();
}

function handleAstrometryClick(event) {
  const point = event?.points?.[0];
  if (!point || point.customdata === undefined || point.customdata === null) return;
  atmState.selectedIds = new Set([point.customdata]);
  renderAstrometryTable();
}

function renderAstrometrySummary(prepared) {
  const target = atmState.payload.target || {};
  const rows = prepared.rows;
  const missionCount = new Set(rows.map((row) => row.mission)).size;
  const recalcNote = prepared.usedFallbackRecalibration ? " Recalibrated-only filter had no rows, so all rows are shown." : "";
  atmEl["atm-summary"].innerHTML = [
    `<strong>${escapeHtml(targetShortName(target))}</strong>`,
    `oid${target.moca_oid}`,
    `${rows.length} measurements`,
    `${missionCount} missions`,
    `reference epoch ${formatNumber(prepared.reference.epoch, 4)}`,
    recalcNote,
  ].filter(Boolean).join(" | ");
}

function renderAstrometryTable() {
  const selected = atmState.selectedIds.size
    ? atmState.processedRows.filter((row) => atmState.selectedIds.has(row.id))
    : atmState.processedRows;
  const rows = selected.slice(0, 350);
  atmEl["atm-table-title"].textContent = atmState.selectedIds.size ? "Selected measurements" : "Measurements";
  atmEl["atm-table-subtitle"].textContent = `${selected.length} row${selected.length === 1 ? "" : "s"}${selected.length > rows.length ? `, showing first ${rows.length}` : ""}`;
  if (!rows.length) {
    atmEl["atm-table"].innerHTML = `<div class="empty-table">No measurements to show.</div>`;
    return;
  }
  atmEl["atm-table"].innerHTML = `
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Mission</th>
          <th>Epoch</th>
          <th>R.A. offset</th>
          <th>Decl. offset</th>
          <th>R.A.</th>
          <th>Decl.</th>
          <th>Origin</th>
          <th>Calibration</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.id)}</td>
            <td>${escapeHtml(row.mission || "")}</td>
            <td>${formatNumber(row.measurement_epoch_yr, 5)}</td>
            <td>${formatNumber(row.rel_ra, 2)} +/- ${formatNumber(row.ra_unc_mas, 2)} mas</td>
            <td>${formatNumber(row.rel_dec, 2)} +/- ${formatNumber(row.dec_unc_mas, 2)} mas</td>
            <td>${formatNumber(row.plot_ra, 8)}</td>
            <td>${formatNumber(row.plot_dec, 8)}</td>
            <td>${escapeHtml(row.origin || row.moca_pid || "")}</td>
            <td>${escapeHtml(row.calibration_method || "")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>`;
}

function hoverText(row) {
  return [
    `<b>ID:</b> ${escapeHtml(row.id)}`,
    `<b>Mission:</b> ${escapeHtml(row.mission || "N/A")}`,
    `<b>Epoch:</b> ${formatNumber(row.measurement_epoch_yr, 5)} yr`,
    `<b>R.A. offset:</b> ${formatNumber(row.rel_ra, 2)} +/- ${formatNumber(row.ra_unc_mas, 2)} mas`,
    `<b>Decl. offset:</b> ${formatNumber(row.rel_dec, 2)} +/- ${formatNumber(row.dec_unc_mas, 2)} mas`,
    `<b>R.A.:</b> ${formatNumber(row.plot_ra, 8)} deg`,
    `<b>Decl.:</b> ${formatNumber(row.plot_dec, 8)} deg`,
    `<b>Reference:</b> ${escapeHtml(row.moca_pid || "N/A")}`,
    `<b>Origin:</b> ${escapeHtml(row.origin || "N/A")}`,
    `<b>Bandpass:</b> ${escapeHtml(row.moca_psid || "N/A")}`,
    `<b>Calibration:</b> ${escapeHtml(row.calibration_method || "N/A")}`,
    `<b>Comments:</b> ${escapeHtml(row.comments || "")}`,
  ].join("<br>");
}

function renderEmptyAstrometry(message) {
  const layout = {
    paper_bgcolor: "#eeeeef",
    plot_bgcolor: "#ffffff",
    xaxis: { visible: false },
    yaxis: { visible: false },
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
  Plotly.react(atmEl["atm-ra-plot"], [], layout, plotConfig("astrometry_ra_empty"));
  Plotly.react(atmEl["atm-dec-plot"], [], layout, plotConfig("astrometry_dec_empty"));
  atmEl["atm-summary"].textContent = message;
  atmEl["atm-table"].innerHTML = "";
  atmEl["atm-export-csv"].disabled = true;
  setAstrometryLoading(false);
}

function exportAstrometryCsv() {
  const rows = atmState.selectedIds.size
    ? atmState.processedRows.filter((row) => atmState.selectedIds.has(row.id))
    : atmState.processedRows;
  if (!rows.length) return;
  const columns = ["id", "mission", "measurement_epoch_yr", "rel_ra", "rel_dec", "ra_unc_mas", "dec_unc_mas", "plot_ra", "plot_dec", "origin", "moca_pid", "calibration_method", "comments"];
  const csv = [
    columns.join(","),
    ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(",")),
  ].join("\n");
  downloadBlob(csv, `moca_astrometry_oid_${atmState.selectedOid || "unknown"}.csv`, "text/csv;charset=utf-8");
}

async function clearAstrometryCache() {
  atmEl["atm-clear-cache"].disabled = true;
  try {
    await postAstrometryJson("api/astrometry/cache/clear", {});
    if (atmState.selectedOid !== null) await loadAstrometryObject();
  } finally {
    atmEl["atm-clear-cache"].disabled = false;
  }
}

function parallaxMotion(raDeg, decDeg, epoch) {
  const epochs = Array.isArray(epoch) ? epoch : [epoch];
  const ra = rad(raDeg);
  const dec = rad(decDeg);
  const cosRa = Math.cos(ra);
  const sinRa = Math.sin(ra);
  const cosDec = Math.cos(dec);
  const sinDec = Math.sin(dec);
  const out = epochs.map((value) => {
    const n = (Number(value) - 2000.0) * 365.25;
    const meanLong = rad(normalizeDegrees(280.460 + 0.9856474 * n));
    const anomaly = rad(normalizeDegrees(357.528 + 0.9856003 * n));
    const sunLong = meanLong + rad(1.915) * Math.sin(anomaly) + rad(0.020) * Math.sin(2 * anomaly);
    const obliquity = rad(23.439 - 0.0000004 * n);
    const cosObl = Math.cos(obliquity);
    const sinObl = Math.sin(obliquity);
    const cosSun = Math.cos(sunLong);
    const sinSun = Math.sin(sunLong);
    return {
      ra: (cosRa * cosObl * sinSun - sinRa * cosSun) * cosDec,
      dec: cosDec * sinObl * sinSun - cosRa * sinDec * cosSun - sinRa * sinDec * cosObl * sinSun,
    };
  });
  return Array.isArray(epoch) ? out : out[0];
}

function normalizeDegrees(value) {
  return ((value % 360) + 360) % 360;
}

function yearlyPhase(epoch) {
  return ((Number(epoch) % 1) + 1) % 1;
}

function paddedRange(values, fixed) {
  if (fixed) return fixed;
  const finiteValues = values.filter(finite);
  if (!finiteValues.length) return undefined;
  const min = Math.min(...finiteValues);
  const max = Math.max(...finiteValues);
  if (min === max) return [min - 1, max + 1];
  const pad = 0.06 * (max - min);
  return [min - pad, max + pad];
}

function targetLabel(target) {
  return `oid${target?.moca_oid || atmState.selectedOid}: ${targetShortName(target)}`;
}

function targetShortName(target) {
  return target?.designation || target?.designations?.[0] || `oid${target?.moca_oid || atmState.selectedOid || ""}`;
}

function setAstrometryStatus(text, mode = "") {
  atmEl["atm-status"].textContent = text;
  atmEl["atm-status"].className = `status${mode ? ` ${mode}` : ""}`;
}

function setAstrometryLoading(loading) {
  atmEl["atm-plot-loader"].classList.toggle("is-visible", Boolean(loading));
}

function updateAstrometryUrl() {
  const params = new URLSearchParams(window.location.search);
  if (atmState.selectedOid !== null) {
    params.set("moca_oid", atmState.selectedOid);
    params.delete("oid");
  } else {
    params.delete("moca_oid");
    params.delete("oid");
  }
  if (atmState.hasUserMissionChoice && atmState.selectedMissions.size) params.set("missions", [...atmState.selectedMissions].join(","));
  else params.delete("missions");
  setBoolParam(params, "subtract_pm", atmEl["atm-subtract-pm"].checked);
  setBoolParam(params, "subtract_plx", atmEl["atm-subtract-plx"].checked);
  setBoolParam(params, "phase", atmEl["atm-phase-yearly"].checked);
  setBoolParam(params, "bin", atmEl["atm-bin"].checked);
  setBoolParam(params, "revert_raw", atmEl["atm-revert-raw"].checked);
  if (!atmEl["atm-adjust-reference"].checked) params.set("adjust_ref", "0");
  else params.delete("adjust_ref");
  if (!atmEl["atm-only-recalibrated"].checked) params.set("only_recalibrated", "0");
  else params.delete("only_recalibrated");
  const nextUrl = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", nextUrl);
}

function setBoolParam(params, key, checked) {
  if (checked) params.set(key, "1");
  else params.delete(key);
}

function apiParams() {
  const source = new URLSearchParams(window.location.search);
  const params = new URLSearchParams();
  for (const key of ["host", "user", "pwd", "dbase", "mock"]) {
    if (source.has(key)) params.set(key, source.get(key));
  }
  return params;
}

async function fetchAstrometryJson(path) {
  const params = apiParams();
  const separator = path.includes("?") ? "&" : "?";
  return fetchJsonUrl(atmAppUrl(`${path}${params.toString() ? `${separator}${params.toString()}` : ""}`));
}

async function postAstrometryJson(path, body) {
  const params = apiParams();
  const separator = path.includes("?") ? "&" : "?";
  const response = await fetch(atmAppUrl(`${path}${params.toString() ? `${separator}${params.toString()}` : ""}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return response.json();
}

async function fetchJsonUrl(url) {
  const response = await fetch(url);
  return response.json();
}

function plotConfig(filename) {
  return {
    responsive: true,
    displaylogo: false,
    toImageButtonOptions: {
      format: "png",
      height: 700,
      width: 1900,
      scale: 2,
      filename,
    },
  };
}

function mocaReportUrl(oid) {
  return `https://mocadb.ca/search/results?search-query=oid%28${encodeURIComponent(oid)}%29&search-type=star`;
}

function formatValueError(value, error, unit) {
  if (!finite(value)) return "N/A";
  if (!finite(error) || Number(error) <= 0) return `${formatNumber(value, 2)} ${unit}`;
  return `${formatNumber(value, 2)} +/- ${formatNumber(error, 2)} ${unit}`;
}

function formatNumber(value, digits) {
  return finite(value) ? Number(value).toFixed(digits) : "N/A";
}

function mean(values) {
  const finiteValues = values.filter(finite).map(Number);
  if (!finiteValues.length) return NaN;
  return finiteValues.reduce((sum, value) => sum + value, 0) / finiteValues.length;
}

function median(values) {
  const finiteValues = values.filter(finite).map(Number).sort((a, b) => a - b);
  if (!finiteValues.length) return NaN;
  const mid = Math.floor(finiteValues.length / 2);
  return finiteValues.length % 2 ? finiteValues[mid] : 0.5 * (finiteValues[mid - 1] + finiteValues[mid]);
}

function finite(value) {
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

function asFalse(value) {
  return ["0", "false", "no", "off"].includes(String(value || "").toLowerCase());
}

function rad(value) {
  return Number(value) * Math.PI / 180;
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

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function debounce(fn, delay) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
