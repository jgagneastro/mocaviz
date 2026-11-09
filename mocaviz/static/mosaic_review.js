"use strict";
const el = id => document.getElementById(id);
const colors = ["#11756d","#5369a1","#b04a6a","#a85a19","#00779b","#715097","#64712c","#1a819e"];
const trajectoryHeight = 565;
const plotConfig = {responsive:true,displaylogo:false,modeBarButtonsToRemove:["autoScale2d","lasso2d","select2d"]};
const state = {oids:[], reviews:new Map(), points:new Map(), skipped:new Set(), detail:null,
  index:0, writesReady:false, generation:0, targetRequest:0, busy:false, done:false, undo:[],
  prefetch:null, sourceToken:null, inputChoices:null, fitPending:false, selected:new Set(),
  filters:null, selectedComparison:null, comparisonOffset:0};
const finite = value => typeof value === "number" && Number.isFinite(value);
const number = (value, places=1) => finite(value) ? value.toFixed(places) : "—";
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);

async function json(path, options = {}) {
  const response = await fetch(path, {cache:"no-store", ...options});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Request failed (" + response.status + ").");
  return data;
}
const post = (path, body) => json(path, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
const options = () => "?offsets=" + Number(el("offsets").checked) + "&calibrated=" + Number(el("calibrated").checked);
const status = (text, error=false) => {el("status").textContent = text; el("status").classList.toggle("error", error);};
const targetPath = oid => "/api/target/" + oid;
const focusedFit = () => state.detail?.fits?.[el("mode").value];
const checked = id => el(id).checked;
const newFilters = () => ({missions:null,methods:null,bands:new Set(),excluded:new Set()});
const visibleMeasurements = () => {
  const detail = state.detail;
  return [...(detail?.measurements || []), ...(detail?.displayMeasurements || [])];
};
let refitTimer, searchTimer;
state.filters = newFilters();

function fitControls() {
  return {onlyRecalibrated:checked("only-recalibrated"),ignoreDuplicates:checked("ignore-duplicates"),
    adjustReference:checked("adjust-reference"),robustFit:checked("robust-fit"),extraFloor:checked("extra-floor"),
    raw:checked("raw"),merged:checked("merged")};
}

function useDefaultFitControls() {
  const fit = fitControls();
  return fit.onlyRecalibrated && fit.ignoreDuplicates && fit.adjustReference && fit.robustFit
    && !fit.extraFloor && !fit.raw && !fit.merged;
}

function fitRequest(path, refit) {
  if (!refit && useDefaultFitControls()) {
    return state.prefetch?.path === path ? state.prefetch.promise : json(path);
  }
  return post(path, {...fitControls(), sourceToken:state.sourceToken,
    missions:state.filters.missions ? [...state.filters.missions] : null,
    methods:state.filters.methods ? [...state.filters.methods] : null,
    bands:[...state.filters.bands].map(key => JSON.parse(key)), excluded:[...state.filters.excluded]});
}

function scheduleRefit() {
  if (!state.oids[state.index] || state.busy) return;
  state.fitPending = true;
  state.targetRequest++;
  state.prefetch = null;
  controls();
  status("Refitting selected measurements…");
  clearTimeout(refitTimer);
  refitTimer = setTimeout(() => navigate(state.index, {refit:true}), 110);
}

function controls() {
  const end = state.oids.length - 1;
  for (const id of ["first","previous"]) el(id).disabled = state.busy || state.index <= 0;
  for (const id of ["next","last"]) el(id).disabled = state.busy || state.index >= end;
  for (const id of ["sample","show-reviewed","offsets","calibrated"]) el(id).disabled = state.busy;
  for (const id of ["adopt","reject"]) el(id).disabled = state.busy || state.fitPending || !state.writesReady || !focusedFit();
  el("undo").disabled = state.busy || !state.writesReady || !state.undo.length;
  el("report").disabled = !state.detail;
  el("wise").disabled = !finite(state.detail?.coordinates?.ra) || !finite(state.detail?.coordinates?.dec);
  el("mode").disabled = state.busy || state.fitPending || !state.detail?.fits?.pm_plx;
  const hasSelection = state.selected.size > 0;
  el("toggle-pm").setAttribute("aria-pressed", String(checked("subtract-pm")));
  for (const id of ["lasso","select-points"]) el(id).disabled = state.busy || !focusedFit();
  for (const id of ["deselect-points","exclude-points","mark-ignored"]) {
    el(id).disabled = state.busy || state.fitPending || !hasSelection;
  }
  el("reset-exclusions").disabled = state.busy || !state.filters.excluded.size;
  for (const input of document.querySelectorAll(".review-sidebar input")) input.disabled = state.busy
    || input.dataset.parentOff === "true";
  el("jump-review").disabled = state.busy || !state.selectedComparison;
}

function renderInputChoices() {
  const choices = state.inputChoices, filters = state.filters;
  const missions = el("mission-list"), methods = el("method-list");
  const missionScroll = missions.scrollTop, methodScroll = methods.scrollTop;
  const label = (title, value, type, enabled, parentOff=false) => '<label><input type="checkbox" data-filter="'
    + type + '" value="' + escapeHtml(value) + '" data-parent-off="' + parentOff + '" '
    + (enabled ? 'checked ' : '') + (parentOff || state.busy ? 'disabled ' : '') + '><span>'
    + escapeHtml(title) + '</span></label>';
  missions.innerHTML = (choices?.missions || []).map(mission => {
    const enabled = filters.missions ? filters.missions.has(mission.label) : mission.default;
    const bands = mission.bands.map(band => {
      const key = JSON.stringify([mission.label,band.label]);
      return label((band.label || "No band recorded")+" ("+band.count+")",key,"band",!filters.bands.has(key),!enabled);
    }).join("");
    return '<div class="mission-filter">' + label(mission.label+" ("+mission.count+")",mission.label,"mission",enabled)
      + '<div class="band-list" role="group" aria-label="'+escapeHtml(mission.label)+' bands">'+bands+'</div></div>';
  }).join("") || "No eligible missions";
  methods.innerHTML = (choices?.methods || []).map(method=>label((method.label || "No calibration method")
    +" ("+method.count+")",method.label,"method",!filters.methods || filters.methods.has(method.label))).join("")
    || "No eligible calibration methods";
  missions.scrollTop = missionScroll;
  methods.scrollTop = methodScroll;
  for (const id of ["missions-all","missions-none","methods-all","methods-none"]) el(id).disabled = !choices || state.busy;
}

function changeInputChoice(event) {
  const input = event.target, key = input.value;
  const filters = state.filters;
  if (!input.dataset.filter || !state.inputChoices || state.busy) return;
  if (input.dataset.filter === "band") {
    if (input.checked) filters.bands.delete(key);
    else filters.bands.add(key);
  } else {
    const mission = input.dataset.filter === "mission";
    const field = mission ? "missions" : "methods";
    if (!filters[field]) {
      filters[field] = new Set(state.inputChoices[field].filter(item=>!mission || item.default).map(item=>item.label));
    }
    if (input.checked) filters[field].add(key);
    else filters[field].delete(key);
    if (mission) {
      for (const band of input.closest(".mission-filter").querySelectorAll('[data-filter="band"]')) {
        band.dataset.parentOff = String(!input.checked);
        band.disabled = !input.checked;
      }
    }
  }
  scheduleRefit();
}

function setChoiceGroup(field, enable) {
  if (!state.inputChoices || state.busy) return;
  state.filters[field] = new Set(enable ? state.inputChoices[field].map(item=>item.label) : []);
  if (field === "missions" && enable) state.filters.bands.clear();
  renderInputChoices();
  scheduleRefit();
}

function markedPointIndices(ids) {
  return state.selected.size ? ids.flatMap((id,index)=>state.selected.has(id)?[index]:[]) : null;
}

function refreshPointSelection() {
  const node = el("trajectory");
  if (node.data) {
    const traces = node.data.flatMap((trace,index)=>trace.customdata?[index]:[]);
    if (traces.length) Plotly.restyle(node,{selectedpoints:traces.map(index=>markedPointIndices(node.data[index].customdata))},traces);
  }
  renderSelectedTable();
  controls();
}

function renderSelectedTable() {
  const rows = visibleMeasurements().filter(row=>state.selected.has(row.id));
  el("selection-status").textContent = rows.length+" selected · "+state.filters.excluded.size+" excluded from fit";
  el("measurements-panel").hidden = !rows.length;
  el("measurement-count").textContent = rows.length+" selected";
  el("measurement-table").innerHTML = rows.length ? "<table><thead><tr>"
    + ["ID","Epoch","Mission","Band","Calibration","R.A. (°)","Decl. (°)","σ R.A.* (mas)","σ Decl. (mas)","Status"]
      .map(name=>"<th>"+name+"</th>").join("") + "</tr></thead><tbody>"
    + rows.map(row=>"<tr>"+[row.id,number(row.year,6),row.mission,row.moca_psid,row.calibration_method,
      number(row.raDeg,8),number(row.decDeg,8),number(row.sigmaRa,2),number(row.sigmaDec,2),row.kind||"Fit input"]
      .map(value=>"<td>"+escapeHtml(value ?? "—")+"</td>").join("")+"</tr>").join("") + "</tbody></table>" : "";
}

async function markIgnored() {
  if (state.busy || state.fitPending || !state.detail || !state.selected.size) return;
  const oid = state.detail.target.moca_oid;
  const ids = [...state.selected];
  const comments = el("ignore-comment").value;
  const endpoint = targetPath(oid)+"/ignore";
  state.busy = true;
  controls();
  el("ignore-status").textContent = "Previewing the selected rows…";
  try {
    const result = await post(endpoint,{ids,comments});
    if (!result.count) {
      el("ignore-status").textContent = "All selected rows are already ignored.";
      return;
    }
    const examples = result.ids.slice(0,12).join(", ")+(result.ids.length>12 ? ", …" : "");
    if (!window.confirm("Set ignored=1 in MOCAdb for "+result.count+" measurements of OID "+oid
      +"?\nSelected measurement IDs: "+examples)) {
      el("ignore-status").textContent = "Cancelled.";
      return;
    }
    const saved = await post(endpoint,{ids,comments,apply:true,revision:result.revision});
    el("ignore-comment").value = "";
    state.selected.clear();
    state.points.delete(oid);
    state.prefetch = null;
    await navigate(state.index,{refit:true,refresh:true});
    status(saved.updated+" measurements marked ignored in MOCAdb. "+el("status").textContent);
  } catch (error) {
    el("ignore-status").textContent = error.message;
  } finally {
    state.busy = false;
    controls();
  }
}

function jumpTo(oid) {
  const index = state.oids.indexOf(oid);
  if (state.busy || index < 0) return;
  if (state.reviews.has(oid)) el("show-reviewed").checked = true;
  navigate(index);
  document.querySelector(".review").scrollIntoView({block:"start"});
}

async function searchTargets() {
  const field = el("target-search"), query = field.value.trim(), sample = el("sample").value;
  const results = el("target-results");
  if (query.length < 2) {
    results.hidden = true;
    return;
  }
  try {
    const data = await json("/api/search?sample="+encodeURIComponent(sample)+"&q="+encodeURIComponent(query));
    if (field.value.trim() !== query || el("sample").value !== sample) return;
    results.replaceChildren(...data.targets.map(target => {
      const button = document.createElement("button");
      button.textContent = (target.designation || "OID") + " · " + target.moca_oid;
      button.onclick = () => {
        results.hidden = true;
        field.value = "";
        jumpTo(target.moca_oid);
      };
      return button;
    }));
    if (!data.targets.length) results.textContent = "No matches in this sample";
    results.hidden = false;
  } catch (error) {
    results.textContent = error.message;
    results.hidden = false;
  }
}

function showCounts() {
  const adopted = [...state.reviews.values()].filter(review => review.state === "adopt").length;
  const classified = state.reviews.size;
  const skipped = [...state.skipped].filter(oid => !state.reviews.has(oid)).length;
  el("counts").textContent = classified.toLocaleString() + " classified (" + adopted.toLocaleString()
    + " adopted) · " + (state.oids.length - classified - skipped).toLocaleString() + " remaining to check"
    + (skipped ? " · " + skipped.toLocaleString() + " no fit" : "");
}

function nextIndex(start, step) {
  for (let i = start; i >= 0 && i < state.oids.length; i += step) {
    if (el("show-reviewed").checked || !state.reviews.has(state.oids[i])) return i;
  }
  return -1;
}

function showEmpty(text) {
  el("inspector").hidden = true;
  el("empty").textContent = text;
}
async function loadSample() {
  const generation = ++state.generation;
  state.targetRequest++;
  clearTimeout(refitTimer);
  state.fitPending = false;
  state.selectedComparison = null;
  el("jump-review").firstChild.textContent = "Review selected target ";
  state.selected.clear();
  state.inputChoices = null;
  state.filters = newFilters();
  renderInputChoices();
  renderSelectedTable();
  state.oids = [];
  state.reviews.clear();
  state.points.clear();
  state.skipped.clear();
  state.prefetch = null;
  state.comparisonOffset = 0;
  state.detail = null;
  state.index = 0;
  el("counts").textContent = "Loading sample…";
  el("setup").hidden = true;
  el("position").textContent = "MOSAIC sample";
  el("target").textContent = "Loading sample…";
  showEmpty("Reading the sample and its saved decisions from MOCAdb.");
  status("");
  controls();
  renderPopulation();
  try {
    const queue = await json("/api/queue?sample=" + encodeURIComponent(el("sample").value));
    if (generation !== state.generation) return;
    state.oids = queue.oids;
    state.reviews = new Map(queue.reviews.map(row => [row.oid, row]));
    state.writesReady = queue.writesReady;
    el("setup").hidden = queue.writesReady;
    el("setup").textContent = "Read-only preview. Apply the proposed MOCAdb vetting table to enable Adopt, Reject and Undo.";
    showCounts();
    renderPopulation();
    await navigate(nextIndex(0, 1));
    if (generation === state.generation) loadBackground(generation);
  } catch (error) {
    if (generation !== state.generation) return;
    showEmpty("The sample could not be loaded.");
    status(error.message, true);
  }
}

async function navigate(index, {refit=false, refresh=false} = {}) {
  clearTimeout(refitTimer);
  const previousMode = refit ? el("mode").value : null;
  if (!refit) {
    state.filters = newFilters();
    state.inputChoices = null;
    state.selected.clear();
    el("ignore-status").textContent = "";
    renderInputChoices();
  }
  if (!refit || refresh) state.sourceToken = null;
  const generation = state.generation, requestId = ++state.targetRequest;
  const oid = state.oids[index];
  state.detail = null;
  state.fitPending = Boolean(oid);
  renderSelectedTable();
  if (!oid) {
    state.index = 0;
    el("position").textContent = "Sample complete";
    el("target").textContent = "No pending target";
    status("");
    showEmpty("Use Include reviewed to revisit saved decisions.");
    controls();
    return;
  }
  state.index = index;
  el("position").textContent = "Target " + (index + 1).toLocaleString() + " / " + state.oids.length.toLocaleString();
  el("target").textContent = "OID " + oid;
  showEmpty("Fitting this target with SciPy…");
  status("");
  controls();
  const path = targetPath(oid) + options();
  try {
    const detail = await fitRequest(path, refit);
    if (generation !== state.generation || requestId !== state.targetRequest) return;
    state.detail = detail;
    state.fitPending = false;
    state.sourceToken = detail.sourceToken;
    const choicesChanged = JSON.stringify(state.inputChoices) !== JSON.stringify(detail.inputChoices);
    state.inputChoices = detail.inputChoices;
    if (choicesChanged) renderInputChoices();
    const displayed = new Set(visibleMeasurements().map(row => row.id));
    state.selected = new Set([...state.selected].filter(id => displayed.has(id)));
    renderSelectedTable();
    if (detail.review) state.reviews.set(oid, detail.review);
    else state.reviews.delete(oid);
    el("target").textContent = (detail.target.designation || "OID " + oid)
      + (detail.target.designation ? "  ·  OID " + oid : "");
    if (detail.unavailable) {
      if (!refit && useDefaultFitControls()) state.skipped.add(oid);
      showEmpty(detail.unavailable + " Change the fit selection or use Next.");
    } else {
      state.skipped.delete(oid);
      el("mode").options[1].disabled = !detail.fits.pm_plx;
      el("mode").value = detail.fits[previousMode] ? previousMode : detail.preferred;
      el("empty").textContent = "";
      el("inspector").hidden = false;
      renderTarget();
      const fit = focusedFit();
      if (!detail.review && finite(detail.comparison?.pmra_masyr) && finite(detail.comparison?.pmdec_masyr)) {
        state.points.set(oid, {oid, dx:fit.pmra-detail.comparison.pmra_masyr, dy:fit.pmdec-detail.comparison.pmdec_masyr});
      }
    }
    showCounts();
    renderPopulation();
    controls();
    const following = state.oids[nextIndex(index + 1, 1)];
    if (following && useDefaultFitControls() && !refit) {
      const ahead = targetPath(following) + options();
      state.prefetch = {path:ahead, promise:json(ahead)};
      state.prefetch.promise.catch(() => {});
    }
  } catch (error) {
    if (generation === state.generation && requestId === state.targetRequest) {
      state.prefetch = null;
      state.fitPending = false;
      controls();
      showEmpty("Could not load this target. Use Next or press Shift+R to retry.");
      status(error.message, true);
    }
  }
}

function go(direction) {
  const starts = {first:0,previous:state.index-1,next:state.index+1,last:state.oids.length-1};
  const index = nextIndex(starts[direction], direction === "previous" || direction === "last" ? -1 : 1);
  if (index >= 0 && index !== state.index) navigate(index);
}

async function decide(action) {
  const detail = state.detail, fit = focusedFit();
  if (state.busy || state.fitPending || !state.writesReady || !fit) return;
  const oid = detail.target.moca_oid;
  const requestId = state.failedDecision?.token === detail.token && state.failedDecision.mode === fit.mode
    && state.failedDecision.action === action ? state.failedDecision.requestId : crypto.randomUUID();
  state.busy = true;
  controls();
  status(action === "adopt" ? "Saving the review and proper motion…" : "Saving the rejection…");
  try {
    const result = await post(targetPath(oid) + "/decision", {decision:action, mode:fit.mode,
      token:detail.token, expected:detail.review?.id ?? null, requestId});
    state.failedDecision = null;
    state.reviews.set(oid, result.review);
    state.undo.push({id:result.review.id,oid});
    state.prefetch = null;
    showCounts();
    renderPopulation();
    const ahead = nextIndex(state.index + 1, 1);
    const behind = nextIndex(state.index - 1, -1);
    await navigate(ahead >= 0 ? ahead : behind);
  } catch (error) {
    state.failedDecision = {token:detail.token, mode:fit.mode, action, requestId};
    status(error.message, true);
  } finally {
    state.busy = false;
    controls();
  }
}

async function undo() {
  if (state.busy || !state.undo.length || !state.writesReady) return;
  const last = state.undo.at(-1);
  state.busy = true;
  controls();
  status("Restoring the previous review state…");
  try {
    const result = await post(targetPath(last.oid) + "/undo", {id:last.id});
    state.undo.pop();
    if (result.review) state.reviews.set(last.oid, result.review);
    else state.reviews.delete(last.oid);
    state.prefetch = null;
    showCounts();
    renderPopulation();
    if (state.oids.includes(last.oid)) {
      if (result.review) el("show-reviewed").checked = true;
      await navigate(state.oids.indexOf(last.oid));
    }
  } catch (error) {
    status(error.message, true);
  } finally {
    state.busy = false;
    controls();
  }
}

const axis = title => ({title:{text:title,standoff:8},showgrid:true,gridcolor:"#e5edf3",mirror:true,
  showline:true,linecolor:"#52677d",linewidth:2,tickwidth:1.7,ticks:"outside",zerolinecolor:"#9caec0",automargin:true});
const layout = extra => ({paper_bgcolor:"#fff",plot_bgcolor:"#fcfdff",font:{family:"system-ui, sans-serif",size:14,color:"#223b55"},
  margin:{l:63,r:20,t:18,b:52},hovermode:"closest",...extra});

function renderTarget() {
  const detail = state.detail, fit = focusedFit();
  if (!fit) return;
  const values = fit.surveyOffsets.values;
  const shiftCount = Object.keys(values).length;
  const shifts = shiftCount ? " · " + shiftCount + " mission shifts (anchor " + fit.surveyOffsets.anchor + ")" :
    el("offsets").checked ? " · no second dataset with " + fit.surveyOffsets.minimumGroups + " independent groups" : "";
  const decision = detail.review ? " · " + (detail.review.state === "adopt" ? "Adopted in review" : "Rejected in review") : "";
  status(detail.nRows + " measurements · " + detail.nGroups + " independent groups · χ²ᵣ " + number(fit.reducedChi2,2)
    + shifts + decision + (detail.inputChoices?.recalibratedFallback ? " · using available unrecalibrated astrometry" : "")
    + (detail.parallaxReason ? " · " + detail.parallaxReason : ""));
  renderTrajectory(detail, fit);
  const parallaxFit = detail.fits.pm_plx;
  el("parallax").hidden = !parallaxFit;
  renderLiterature(el("motion"), detail.literature.pm, fit, false, parallaxFit ? 0 : trajectoryHeight);
  if (parallaxFit) renderLiterature(el("parallax"), detail.literature.parallax, parallaxFit, true);
  renderPrecision(detail.literature, fit, parallaxFit);
  controls();
}

function trajectoryX(epoch) {
  return checked("phase") ? ((epoch % 1) + 1) % 1 : epoch;
}

function trajectoryFrame(detail, fit, coordinate, axisIndex) {
  const masPerDegree = 3600000 * (axisIndex === 0 ? Math.max(1e-9, Math.cos(detail.reference.dec * Math.PI / 180)) : 1);
  const motion = fit[axisIndex === 0 ? "pmra" : "pmdec"];
  const parallax = fit.plx ?? fit.fixedPlx ?? 0;
  const y = (value, year, parallaxMotion=0) => {
    const subtracted = value - (checked("subtract-pm") ? motion * (year - fit.t0) : 0)
      - (checked("subtract-plx") ? parallaxMotion : 0);
    return checked("absolute") ? detail.reference[coordinate] + subtracted/masPerDegree : subtracted;
  };
  const catalog = row => {
    let diff = row[coordinate+"Deg"] - detail.reference[coordinate];
    if (axisIndex === 0) diff = ((diff+540)%360)-180;
    return y(diff*masPerDegree, row.year, parallax*(row.parallaxFactors?.[axisIndex] ?? 0));
  };
  return {y,catalog,sigma: value => checked("absolute") ? value/masPerDegree : value};
}

function fittedCurve(fit, coordinate, frame) {
  const x = [], y = [];
  fit.curve.year.forEach((year,i) => {
    const phase = trajectoryX(year);
    if (checked("phase") && x.length && phase < x.at(-1)) {
      x.push(null);
      y.push(null);
    }
    x.push(phase);
    y.push(frame.y(fit.curve[coordinate][i], year, fit.curve[coordinate === "ra" ? "parallaxRa" : "parallaxDec"]?.[i]));
  });
  return {x,y};
}

function displayBins(detail, fit, axisIndex, frame) {
  const coordinate = axisIndex === 0 ? "ra" : "dec";
  const bins = new Map();
  detail.measurements.forEach((row,i) => {
    const shift = fit.surveyOffsets.values[row.mission]?.[axisIndex === 0 ? "raMas" : "decMas"] ?? 0;
    const value = frame.y(row[coordinate]-shift,row.year,fit.parallaxMotion?.[axisIndex][i]);
    const weight = 1/Math.max(frame.sigma(fit.effectiveUncertainties[axisIndex][i])**2,1e-24);
    const night = Math.floor(row.year*365.25+.5);
    const bin = bins.get(night) || {weight:0,value:0,year:0};
    bin.weight += weight;
    bin.value += weight*value;
    bin.year += weight*row.year;
    bins.set(night,bin);
  });
  return [...bins.values()].map(bin=>({x:trajectoryX(bin.year/bin.weight),y:bin.value/bin.weight,sigma:Math.sqrt(1/bin.weight)}));
}

function renderTrajectory(detail, fit) {
  const residual = el("residual").value, showResidual = residual !== "none";
  const axes = ["ra","dec"], groups = new Map(), data = [];
  const symbolScale = Number(el("symbol-size").value)/100;
  detail.measurements.forEach((row,i) => {
    if (!groups.has(row.mission)) groups.set(row.mission, []);
    groups.get(row.mission).push({row,i});
  });
  const domains = showResidual ? [[.71,.99],[.41,.69],[.21,.35],[.01,.15]] : [[.54,.98],[.03,.47]];
  axes.forEach((coordinate, axisIndex) => {
    const ref = axisIndex === 0 ? "y" : "y2", residualRef = axisIndex === 0 ? "y3" : "y4";
    const frame = trajectoryFrame(detail,fit,coordinate,axisIndex);
    data.push({type:"scatter",mode:"lines",name:"MOSAIC trajectory",legendgroup:"model",showlegend:axisIndex===0,
      ...fittedCurve(fit,coordinate,frame),yaxis:ref,line:{color:"#192d45",width:2.5},hoverinfo:"skip"});
    let index = 0;
    for (const [mission, points] of groups) {
      const color = colors[index++ % colors.length];
      const shift = fit.surveyOffsets.values[mission]?.[axisIndex === 0 ? "raMas" : "decMas"] || 0;
      const hover = points.map(({row,i}) => escapeHtml(mission) + " · " + escapeHtml(row.moca_psid || "no band")
        + "<br>Epoch " + number(row.year,5) + " · row " + row.id + "<br>Position " + number(row[coordinate],2)
        + " mas<br>Fitted mission shift " + number(shift,2) + " mas<br>Fit weight " + number(fit.weights[i],2));
      const common = {type:"scatter",mode:"markers",name:mission,legendgroup:mission,
        x:points.map(({row}) => trajectoryX(row.year)),customdata:points.map(({row}) => row.id),
        text:hover,hovertemplate:"%{text}<extra></extra>",
        marker:{size:points.map(({i}) => symbolScale*(fit.weights[i] < .5 ? 5 : 7)),color,
          symbol:points.map(({i}) => fit.weights[i] < .5 ? "circle-open" : "circle"),opacity:.82},
        selectedpoints:markedPointIndices(points.map(({row})=>row.id)),selected:{marker:{opacity:1,color:"#d97818"}},
        unselected:{marker:{opacity:.38}}};
      const uncertainty = points.map(({i}) => fit.effectiveUncertainties[axisIndex][i]);
      data.push({...common,showlegend:axisIndex===0,yaxis:ref,y:points.map(({row,i}) =>
        frame.y(row[coordinate]-shift,row.year,fit.parallaxMotion?.[axisIndex][i])),
        error_y:{type:"data",array:uncertainty.map(frame.sigma),thickness:1.15,width:2,color:color+"72"}});
      if (showResidual) data.push({...common,showlegend:false,yaxis:residualRef,y:points.map(({row,i},j) =>
        (row[coordinate] - fit.model[axisIndex][i]) / (residual === "sigma" ? uncertainty[j] : 1))});
    }
    const extras = detail.displayMeasurements || [];
    for (const [kind,symbol,color] of [["Merged astrometry","diamond-open","#74489a"],["Ignored in MOCAdb","x","#b45528"]]) {
      const points = extras.filter(row => row.kind===kind && [row.year,row.raDeg,row.decDeg].every(finite));
      if (!points.length) continue;
      const ids = points.map(row => row.id);
      data.push({type:"scatter",mode:"markers",name:kind,legendgroup:kind,showlegend:axisIndex===0,
        x:points.map(row=>trajectoryX(row.year)),y:points.map(frame.catalog),yaxis:ref,customdata:ids,
        selectedpoints:markedPointIndices(ids),selected:{marker:{color:"#d97818",opacity:1}},
        unselected:{marker:{opacity:.38}},marker:{color,symbol,size:8*symbolScale},
        text:points.map(row=>escapeHtml(row.mission)+" · OID row "+row.id),
        hovertemplate:"%{text}<extra>"+kind+"</extra>"});
    }
    const reference = detail.referenceMeasurement;
    if (checked("show-reference") && reference && [reference.year,reference.raDeg,reference.decDeg].every(finite)) {
      data.push({type:"scatter",mode:"markers",name:"Adopted reference",legendgroup:"reference",showlegend:axisIndex===0,
        x:[trajectoryX(reference.year)],y:[frame.catalog(reference)],yaxis:ref,
        marker:{symbol:"star",color:"#d7912a",size:11*symbolScale},hovertemplate:"Adopted reference<extra></extra>"});
    }
    if (checked("bin")) {
      const bins = displayBins(detail,fit,axisIndex,frame);
      data.push({type:"scatter",mode:"markers",name:"Nightly bins",legendgroup:"binned",showlegend:axisIndex===0,
        x:bins.map(bin=>bin.x),y:bins.map(bin=>bin.y),yaxis:ref,
        marker:{symbol:"circle-open",color:"#243b53",size:8*symbolScale},
        error_y:{type:"data",array:bins.map(bin=>bin.sigma),thickness:1,width:2}});
    }
  });
  const absolute = checked("absolute");
  const plotLayout = layout({height:trajectoryHeight,margin:{l:73,r:18,t:56,b:51},
    legend:{orientation:"h",y:1.13,x:0,font:{size:12}},dragmode:state.lasso?"lasso":"zoom",
    xaxis:{...axis(checked("phase")?"Yearly phase":"Epoch (year)"),anchor:showResidual?"y4":"y2"},
    yaxis:{...axis(absolute?"R.A. (°)":"Δ R.A.* (mas)"),domain:domains[0]},
    yaxis2:{...axis(absolute?"Decl. (°)":"Δ Decl. (mas)"),domain:domains[1]},
    uirevision:[detail.target.moca_oid,fit.mode,residual,checked("subtract-pm"),checked("subtract-plx"),checked("phase"),absolute].join("-")});
  if (showResidual) {
    plotLayout.yaxis3 = {...axis(""),domain:domains[2],nticks:4};
    plotLayout.yaxis4 = {...axis(""),domain:domains[3],nticks:4};
    plotLayout.annotations = ["R.A.* residual","Decl. residual"].map((name,i) => ({
      x:1,y:domains[i+2][1],xref:"paper",yref:"paper",xanchor:"right",yanchor:"bottom",
      text:name + (residual === "sigma" ? " / σ" : " (mas)"),showarrow:false,font:{size:12,color:"#516376"}
    }));
  }
  const node = el("trajectory");
  Plotly.react(node,data,plotLayout,{...plotConfig,modeBarButtonsToRemove:["autoScale2d"]}).then(() => {
    if (node.mosaicSelectionBound) return;
    node.mosaicSelectionBound = true;
    node.on("plotly_click", event => {
      const id = event.points.find(point=>point.customdata!=null)?.customdata;
      if (id==null || state.fitPending || state.busy) return;
      if (state.selected.has(id)) state.selected.delete(id);
      else state.selected.add(id);
      refreshPointSelection();
    });
    node.on("plotly_selected", event => {
      if (!event?.points?.length || state.fitPending || state.busy) return;
      state.selected = new Set(event.points.map(point=>point.customdata).filter(id=>id!=null));
      refreshPointSelection();
    });
    node.on("plotly_deselect", () => {
      if (state.busy || !state.selected.size) return;
      state.selected.clear();
      refreshPointSelection();
    });
  });
}

function literatureLabel(row) {
  return escapeHtml(row.moca_pid || [row.mission_name,row.data_release].filter(Boolean).join(" ") || row.origin || "MOCAdb row " + row.id);
}

function literatureGuides(xref, adoptedValue, adoptedUnc, fitValue, fitUnc) {
  const span = {xref,yref:"y domain",y0:0,y1:1,layer:"below"};
  const guides = [];
  const line = (x, color, width, dash) => ({
    ...span,type:"line",x0:x,x1:x,line:{color,width,dash}
  });
  if (finite(adoptedValue)) {
    if (finite(adoptedUnc) && adoptedUnc > 0) {
      guides.push({...span,type:"rect",x0:adoptedValue-adoptedUnc,x1:adoptedValue+adoptedUnc,
        fillcolor:"rgba(168,90,25,.17)",line:{width:0}});
    } else {
      guides.push(line(adoptedValue,"#a85a19",1,"solid"));
    }
  }
  if (finite(fitValue) && finite(fitUnc) && fitUnc > 0) {
    guides.push(line(fitValue-fitUnc,"#11756d",1.3,"dash"), line(fitValue+fitUnc,"#11756d",1.3,"dash"));
  }
  return guides;
}

function renderLiterature(node, literature, fit, parallax, minimumHeight=0) {
  const names = parallax ? ["Parallax (mas)"] : ["μα* (mas/yr)","μδ (mas/yr)"];
  const columns = parallax ? ["parallax_mas"] : ["pmra_masyr","pmdec_masyr"];
  const fields = parallax ? ["plx"] : ["pmra","pmdec"];
  const rows = literature.filter(row => columns.some(key => finite(row[key])));
  const categories = rows.map(row => (row.adopted ? "★ " : "") + literatureLabel(row));
  categories.unshift("<b>MOSAIC</b>");
  const y = categories.map((_, i) => -i);
  const traces = columns.map((col,i) => ({
    type:"scatter",mode:"markers",xaxis:i===0?"x":"x2",y,
    x:[fit[fields[i]],...rows.map(row => row[col])],
    error_x:{type:"data",array:[fit[fields[i]+"Unc"],...rows.map(row => row[col+"_unc"])],width:3,thickness:1.2,color:"#506880"},
    marker:{symbol:["diamond",...rows.map(row => row.adopted ? "star" : "circle")],
      size:[11,...rows.map(row => row.adopted ? 13 : 7)],color:["#11756d",...rows.map(row => row.adopted ? "#a85a19" : "#5369a1")]},
    text:categories,hovertemplate:"%{text}<br>%{x:.3f}<extra></extra>",showlegend:false
  }));
  const adopted = rows.find(row => row.adopted);
  const shapes = columns.flatMap((col,i) => literatureGuides(i===0?"x":"x2",
    adopted?.[col],adopted?.[col+"_unc"],fit[fields[i]],fit[fields[i]+"Unc"]));
  const plotLayout = layout({height:Math.max(minimumHeight,parallax?155:185,84+17*categories.length),shapes,
    margin:{l:88,r:14,t:parallax?21:16,b:48},
    xaxis:{...axis(names[0]),domain:parallax?[0,1]:[0,.46]},
    yaxis:{tickmode:"array",tickvals:y,ticktext:categories,range:[-categories.length+.5,.6],automargin:true,
      showline:true,linecolor:"#52677d",linewidth:2,mirror:true,zeroline:false,
      gridcolor:"#e6edf3",tickfont:{size:12}}});
  if (!parallax) plotLayout.xaxis2 = {...axis(names[1]),domain:[.54,1]};
  Plotly.react(node,traces,plotLayout,plotConfig);
}

function renderPrecision(literature, fit, parallaxFit) {
  const pm = literature.pm.find(row=>row.adopted) || {};
  const plx = literature.parallax.find(row=>row.adopted) || {};
  const comparisons = [
    {label:"PM R.A.*",mosaic:fit.pmraUnc,adopted:pm.pmra_masyr_unc,unit:"mas/yr"},
    {label:"PM Decl.",mosaic:fit.pmdecUnc,adopted:pm.pmdec_masyr_unc,unit:"mas/yr"},
    {label:"Parallax",mosaic:parallaxFit?.plxUnc,adopted:plx.parallax_mas_unc,unit:"mas"},
  ].filter(item=>finite(item.mosaic)&&item.mosaic>0&&finite(item.adopted)&&item.adopted>0);
  el("precision-panel").hidden = !comparisons.length;
  if (!comparisons.length) return;
  const ratio = comparisons.map(item=>item.mosaic/item.adopted);
  const index = comparisons.map((_,i)=>-i);
  const segments = {type:"scatter",mode:"lines",hoverinfo:"skip",showlegend:false,
    x:ratio.flatMap(value=>[1,value,null]),y:index.flatMap(i=>[i,i,null]),line:{color:"#aac6c0",width:2.5}};
  const points = {type:"scatter",mode:"markers",x:ratio,y:index,showlegend:false,
    marker:{symbol:"diamond",size:10,color:ratio.map(value=>value<1?"#11756d":"#b2533f")},
    text:comparisons.map((item,i)=>item.label+" · "+number(ratio[i],2)+"×<br>MOSAIC σ "+number(item.mosaic,3)
      +" "+item.unit+"<br>Adopted σ "+number(item.adopted,3)+" "+item.unit),
    hovertemplate:"%{text}<extra></extra>"};
  const limit = Math.max(.3,...ratio.map(value=>Math.abs(Math.log10(value)))) * 1.18;
  Plotly.react(el("precision"),[segments,points],layout({height:115+25*comparisons.length,
    margin:{l:74,r:16,t:12,b:53},xaxis:{...axis("MOSAIC σ / adopted σ"),type:"log",range:[-limit,limit]},
    yaxis:{...axis(""),tickmode:"array",tickvals:index,ticktext:comparisons.map(item=>item.label),
      range:[-comparisons.length+.55,.45],zeroline:false},
    shapes:[{type:"line",xref:"x",x0:1,x1:1,yref:"paper",y0:0,y1:1,line:{color:"#62758a",width:1.5,dash:"dash"}}]
  }),plotConfig);
}

const signedLog = value => Math.sign(value) * Math.log10(1 + Math.abs(value));
function renderPopulation() {
  const currentFit = focusedFit(), detail = state.detail;
  const active = [];
  if (currentFit && finite(detail.comparison?.pmra_masyr) && finite(detail.comparison.pmdec_masyr)) {
    active.push({oid:detail.target.moca_oid,dx:currentFit.pmra-detail.comparison.pmra_masyr,
      dy:currentFit.pmdec-detail.comparison.pmdec_masyr});
  }
  const groups = [
    {label:"Unreviewed",color:"#8797a8",symbol:"circle",size:8,opacity:.63,
      points:[...state.points.values()].filter(point => !state.reviews.has(point.oid))},
    {label:"Adopted",color:"#087c64",symbol:"diamond",size:8,opacity:.9,
      points:[...state.reviews.values()].filter(point => point.state === "adopt")},
    {label:"Rejected",color:"#b53e53",symbol:"x",size:9,opacity:.85,
      points:[...state.reviews.values()].filter(point => point.state === "reject")},
    {label:"Current fit",color:"#125faa",symbol:"circle-open",size:12,opacity:1,points:active}
  ];
  const visible = groups.map(group => group.points.filter(point => finite(point.dx) && finite(point.dy)));
  el("comparison-count").textContent = visible[0].length + " unreviewed previews · "
    + visible[1].length + " adopted · " + visible[2].length + " rejected";
  const forRange = [...visible[0], ...visible[1], ...visible[3].filter(point => state.reviews.get(point.oid)?.state !== "reject")];
  const scale = key => {
    const extent = forRange.reduce((max, point) => Math.max(max, Math.abs(signedLog(point[key]))), .45);
    return [-1.08*extent,1.08*extent];
  };
  const rawTicks = [-1e5,-1e4,-1e3,-100,-10,-1,0,1,10,100,1e3,1e4,1e5];
  const graphAxis = (name,key) => ({...axis(name),range:scale(key),tickmode:"array",
    tickvals:rawTicks.map(signedLog),ticktext:rawTicks.map(String)});
  const traces = groups.map(({label,color,symbol,size,opacity}, i) => ({
    type:"scatter",mode:"markers",name:label,customdata:visible[i].map(point => point.oid),
    x:visible[i].map(point => signedLog(point.dx)),y:visible[i].map(point => signedLog(point.dy)),
    text:visible[i].map(point => "OID " + point.oid + "<br>Δμα* " + number(point.dx,3) + "<br>Δμδ " + number(point.dy,3)),
    hovertemplate:"%{text}<extra></extra>",marker:{color,symbol,size,opacity}
  }));
  const node = el("population");
  const selected = visible.flat().find(point => point.oid === state.selectedComparison);
  if (selected) traces.push({type:"scatter",mode:"markers",showlegend:false,
    x:[signedLog(selected.dx)],y:[signedLog(selected.dy)],customdata:[selected.oid],
    marker:{color:"#bb701a",symbol:"circle-open",size:17,line:{width:2}},hoverinfo:"skip"});
  Plotly.react(node, traces, layout({height:node.clientWidth || 650,
    xaxis:graphAxis("Δ μα* (mas/yr, signed log)","dx"),yaxis:graphAxis("Δ μδ (mas/yr, signed log)","dy"),
    legend:{orientation:"h",x:0,y:1.08},margin:{l:69,r:20,t:38,b:51},
    uirevision:"comparison-" + state.generation}),{...plotConfig,doubleClick:"reset"}).then(() => {
      if (node.mosaicClickBound) return;
      node.mosaicClickBound = true;
      node.on("plotly_click",event=>{
        const oid = event.points[0]?.customdata;
        if (!state.oids.includes(oid)) return;
        state.selectedComparison = oid;
        el("jump-review").firstChild.textContent = "Review OID "+oid+" ";
        controls();
        renderPopulation();
      });
    });
}

async function loadBackground(generation) {
  const candidates = state.oids.filter(oid => !state.reviews.has(oid));
  const limit = 288, stride = Math.max(1, Math.floor(candidates.length/limit));
  const preview = candidates.filter((_,i) => i%stride===0).slice(0,limit);
  const query = options();
  for (let start = 0; start < preview.length && generation === state.generation && !state.done; start += 12) {
    try {
      const data = await json("/api/comparison" + query + "&oids=" + preview.slice(start,start+12).join(","));
      if (generation !== state.generation || state.done) break;
      data.points.forEach(point => state.points.set(point.oid,point));
      if (start%36===0 || start+12>=preview.length) renderPopulation();
    } catch {
      if (generation === state.generation) el("comparison-count").textContent += " · preview load paused";
      break;
    }
    await new Promise(resolve => setTimeout(resolve, 120));
  }
}

async function renderPolicy() {
  const optionsAtStart = options();
  try {
    const data = await json("/api/calibrations" + optionsAtStart);
    if (optionsAtStart !== options()) return;
    const container = el("policy");
    const exclusions = data.selection.concat([
      "Input policy v" + data.inputPolicy.version + ". Rejected moca_psid values: " + data.excludedPsids.join(", ") + ".",
      "Legacy releases: " + data.inputPolicy.legacy_data_releases.map(item => item.mission_name + " " + item.data_release).join(", ") + ".",
      "Legacy labels: " + data.inputPolicy.deprecated_field_labels.map(item => item.label).join(", ") + ".",
      "Hard-rejected releases: " + data.inputPolicy.hard_rejected_releases.map(item => item.mission_name + " " + item.data_release).join(", ") + ".",
      "Recalibrated epochs and 2MASS PSC are preferred by default. The fit sidebar can include other uncalibrated rows.",
      data.airmass,
    ]);
    container.innerHTML = "<ul>" + exclusions.map(text => "<li>"+escapeHtml(text)+"</li>").join("") + "</ul>"
      + "<details><summary>Coordinate bias models and coefficients</summary>" + data.models.map(model =>
        "<p><strong>"+escapeHtml(model.mission)+"</strong> · "+escapeHtml(model.version)+" · "
        +(model.enabled ? "Applied to eligible rows" : "Off under current policy")
        +"</p><pre>"+escapeHtml(JSON.stringify(model.models || model.parameters,null,2))+"</pre>").join("")+"</details>"
      +"<details><summary>Catalog error floors in mas ("+escapeHtml(data.floors.version)+")</summary>"
      +"<table><thead><tr><th>Mission</th><th>Band / PSID</th><th>R.A.*</th><th>Decl.</th></tr></thead><tbody>"
      +data.floors.terms.map(term=>"<tr><td>"+escapeHtml(term.mission)+"</td><td>"+escapeHtml(term.band)
        +"</td><td>"+number(term.ra_mas,2)+"</td><td>"+number(term.dec_mas,2)+"</td></tr>").join("")
      +"</tbody></table></details>";
  } catch (error) {
    el("policy").textContent = error.message;
  }
}

const wiseDefaults = "size=75&band=3&speed=500&minbright=-50.0000&maxbright=500.0000&window=5&diff_window=1&linear=1&color=&zoom=9&border=0&gaia=1&invert=1&maxdyr=1&scandir=0&neowise=0&diff=0&outer_epochs=1&unique_window=1&smooth_scan=0&shift=0&pmra=0&pmdec=0&synth_a=0&synth_a_sub=0&synth_a_ra=&synth_a_dec=&synth_a_w1=&synth_a_w2=&synth_a_pmra=0&synth_a_pmdec=0&synth_a_mjd=&synth_b=0&synth_b_sub=0&synth_b_ra=&synth_b_dec=&synth_b_w1=&synth_b_w2=&synth_b_pmra=0&synth_b_pmdec=0&synth_b_mjd=";
for (const name of ["first","previous","next","last"]) el(name).onclick = () => go(name);
el("report").onclick = () => window.open("https://mocadb.ca/search/results?search-query=oid%28"
  + state.detail.target.moca_oid + "%29&search-type=star","_blank","noopener");
el("wise").onclick = () => window.open("http://byw.tools/wiseview-v2#ra=" + state.detail.coordinates.ra
  + "&dec=" + state.detail.coordinates.dec + "&" + wiseDefaults,"_blank","noopener");
el("quit").onclick = () => {
  if (state.busy) return;
  state.done = true;
  state.generation++;
  state.detail = null;
  el("target").textContent = "Review closed";
  status("Saved decisions are in MOCAdb. Reload the page to resume.");
  showEmpty("You can close this tab.");
  for (const control of document.querySelectorAll("button, select, input")) control.disabled = true;
  window.close();
};
el("adopt").onclick = () => decide("adopt");
el("reject").onclick = () => decide("reject");
el("undo").onclick = undo;
el("sample").onchange = loadSample;
el("show-reviewed").onchange = () => {
  const next = nextIndex(state.index,1);
  navigate(next >= 0 ? next : nextIndex(state.index-1,-1));
};
for (const id of ["offsets","calibrated"]) el(id).onchange = () => {
  const generation = ++state.generation;
  state.points.clear();
  state.prefetch = null;
  renderPopulation();
  renderPolicy();
  const index = state.oids[state.index] ? state.index : nextIndex(state.index,1);
  navigate(index,{refit:Boolean(state.detail)}).then(() => {
    if (generation === state.generation) loadBackground(generation);
  });
};
el("mode").onchange = () => {renderTarget();renderPopulation();};
el("residual").onchange = () => {if (focusedFit()) renderTarget();};
for (const id of ["subtract-pm","subtract-plx","phase","bin","absolute","show-reference"]) {
  el(id).onchange = () => {
    if (focusedFit()) renderTrajectory(state.detail,focusedFit());
    controls();
  };
}
el("toggle-pm").onclick = () => {
  el("subtract-pm").checked = !checked("subtract-pm");
  el("subtract-pm").onchange();
};
el("symbol-size").oninput = () => {
  el("symbol-value").textContent = el("symbol-size").value+"%";
  if (focusedFit()) renderTrajectory(state.detail,focusedFit());
};
for (const id of ["adjust-reference","only-recalibrated","ignore-duplicates","raw","merged","robust-fit","extra-floor"]) {
  el(id).onchange = scheduleRefit;
}
el("mission-list").onchange = changeInputChoice;
el("method-list").onchange = changeInputChoice;
for (const field of ["missions","methods"]) {
  el(field+"-all").onclick = () => setChoiceGroup(field,true);
  el(field+"-none").onclick = () => setChoiceGroup(field,false);
}
el("target-search").oninput = () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(searchTargets,240);
};
el("target-search").onkeydown = event => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  const oid = Number(el("target-search").value.trim());
  if (state.oids.includes(oid)) {
    el("target-results").hidden = true;
    el("target-search").value = "";
    jumpTo(oid);
  } else if (!el("target-results").hidden) {
    el("target-results").querySelector("button")?.click();
  }
};
el("lasso").onclick = () => {
  state.lasso = !state.lasso;
  el("lasso").setAttribute("aria-pressed",String(state.lasso));
  Plotly.relayout(el("trajectory"),{dragmode:state.lasso?"lasso":"zoom"});
};
el("select-points").onclick = () => {
  state.selected = new Set(visibleMeasurements().map(row=>row.id));
  refreshPointSelection();
};
el("deselect-points").onclick = () => {
  state.selected.clear();
  refreshPointSelection();
};
el("exclude-points").onclick = () => {
  for (const row of state.detail.measurements || []) if (state.selected.has(row.id)) state.filters.excluded.add(row.id);
  state.selected.clear();
  renderSelectedTable();
  scheduleRefit();
};
el("reset-exclusions").onclick = () => {
  state.filters.excluded.clear();
  renderSelectedTable();
  scheduleRefit();
};
el("mark-ignored").onclick = markIgnored;
el("jump-review").onclick = () => jumpTo(state.selectedComparison);
let resizeTimer;
window.addEventListener("resize",()=>{
  clearTimeout(resizeTimer);
  resizeTimer=setTimeout(renderPopulation,120);
});
const shortcuts = {Home:"first",End:"last",ArrowLeft:"previous",ArrowUp:"previous",ArrowRight:"next",
  ArrowDown:"next",Backspace:"undo",u:"undo",q:"quit",o:"report",w:"wise",1:"adopt",0:"reject",
  a:"adopt",r:"reject",p:"toggle-pm",l:"lasso",j:"jump-review"};
document.addEventListener("keydown",event=>{
  if (state.done || state.busy || event.altKey || event.target.matches("input,select,textarea,[contenteditable]")) return;
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  if (event.repeat && ["1","0","Backspace","u","a","r","p","l","j"].includes(key)) return;
  if (event.metaKey || event.ctrlKey) {
    if (key === "z") {event.preventDefault();el("undo").click();}
    return;
  }
  if (key === "r" && event.shiftKey) {event.preventDefault();navigate(state.index,{refit:true,refresh:true});return;}
  const action = event.code === "Numpad1" ? "adopt" : event.code === "Numpad0" ? "reject" : shortcuts[key];
  if (action) {event.preventDefault();el(action).click();}
});
renderPolicy();
loadSample();
