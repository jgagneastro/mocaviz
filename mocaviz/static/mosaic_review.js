"use strict";
const el = id => document.getElementById(id);
const colors = ["#11756d","#5369a1","#b04a6a","#a85a19","#00779b","#715097","#64712c","#1a819e"];
const plotConfig = {responsive:true,displaylogo:false,modeBarButtonsToRemove:["autoScale2d","lasso2d","select2d"]};
const state = {oids:[], reviews:new Map(), points:new Map(), skipped:new Set(), detail:null,
  index:0, writesReady:false, generation:0, targetRequest:0, busy:false, done:false, undo:[],
  prefetch:null, comparisonOffset:0};
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

function controls() {
  const end = state.oids.length - 1;
  for (const id of ["first","previous"]) el(id).disabled = state.busy || state.index <= 0;
  for (const id of ["next","last"]) el(id).disabled = state.busy || state.index >= end;
  for (const id of ["sample","show-reviewed","offsets","calibrated"]) el(id).disabled = state.busy;
  for (const id of ["adopt","reject"]) el(id).disabled = state.busy || !state.writesReady || !focusedFit();
  el("undo").disabled = state.busy || !state.writesReady || !state.undo.length;
  el("report").disabled = !state.detail;
  el("wise").disabled = !finite(state.detail?.coordinates?.ra) || !finite(state.detail?.coordinates?.dec);
  el("mode").disabled = state.busy || !state.detail?.fits?.pm_plx;
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

async function navigate(index) {
  const generation = state.generation, requestId = ++state.targetRequest;
  const oid = state.oids[index];
  state.detail = null;
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
    const detail = await (state.prefetch?.path === path ? state.prefetch.promise : json(path));
    if (generation !== state.generation || requestId !== state.targetRequest) return;
    state.detail = detail;
    if (detail.review) state.reviews.set(oid, detail.review);
    else state.reviews.delete(oid);
    el("target").textContent = (detail.target.designation || "OID " + oid)
      + (detail.target.designation ? "  ·  OID " + oid : "");
    if (detail.unavailable) {
      state.skipped.add(oid);
      showEmpty(detail.unavailable + " Use Next to continue.");
    } else {
      state.skipped.delete(oid);
      el("mode").options[1].disabled = !detail.fits.pm_plx;
      el("mode").value = detail.preferred;
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
    if (following) {
      const ahead = targetPath(following) + options();
      state.prefetch = {path:ahead, promise:json(ahead)};
      state.prefetch.promise.catch(() => {});
    }
  } catch (error) {
    if (generation === state.generation && requestId === state.targetRequest) {
      state.prefetch = null;
      showEmpty("Could not load this target. Use Next or press R to retry.");
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
  if (state.busy || !state.writesReady || !fit) return;
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
  showline:true,linecolor:"#8294a6",linewidth:1.3,ticks:"outside",zerolinecolor:"#9caec0",automargin:true});
const layout = extra => ({paper_bgcolor:"#fff",plot_bgcolor:"#fcfdff",font:{family:"system-ui, sans-serif",size:12,color:"#223b55"},
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
    + shifts + decision + (detail.parallaxReason ? " · " + detail.parallaxReason : ""));
  renderTrajectory(detail, fit);
  renderLiterature(el("motion"), detail.literature.pm, fit, false);
  el("parallax").hidden = !detail.fits.pm_plx;
  if (detail.fits.pm_plx) renderLiterature(el("parallax"), detail.literature.parallax, detail.fits.pm_plx, true);
  controls();
}

function renderTrajectory(detail, fit) {
  const residual = el("residual").value, showResidual = residual !== "none";
  const axes = ["ra","dec"], groups = new Map(), data = [];
  detail.measurements.forEach((row,i) => {
    if (!groups.has(row.mission)) groups.set(row.mission, []);
    groups.get(row.mission).push({row,i});
  });
  const domains = showResidual ? [[.67,.98],[.31,.62],[.17,.26],[.02,.11]] : [[.54,.98],[.03,.47]];
  axes.forEach((coordinate, axisIndex) => {
    const ref = axisIndex === 0 ? "y" : "y2", residualRef = axisIndex === 0 ? "y3" : "y4";
    data.push({type:"scatter",mode:"lines",name:"MOSAIC trajectory",legendgroup:"model",showlegend:axisIndex===0,
      x:fit.curve.year,y:fit.curve[coordinate],yaxis:ref,line:{color:"#192d45",width:2.3},
      hoverinfo:"skip"});
    let index = 0;
    for (const [mission, points] of groups) {
      const color = colors[index++ % colors.length];
      const shift = fit.surveyOffsets.values[mission]?.[coordinate === "ra" ? "raMas" : "decMas"] || 0;
      const hover = points.map(({row,i}) => escapeHtml(mission) + " · " + escapeHtml(row.moca_psid || "no band")
        + "<br>Epoch " + number(row.year,5) + " · row " + row.id + "<br>Position " + number(row[coordinate],2)
        + " mas<br>Fitted mission shift " + number(shift,2) + " mas<br>Fit weight " + number(fit.weights[i],2));
      const common = {type:"scatter",mode:"markers",name:mission,legendgroup:mission,
        x:points.map(({row}) => row.year),text:hover,hovertemplate:"%{text}<extra></extra>",
        marker:{size:points.map(({i}) => fit.weights[i] < .5 ? 5 : 7),color,
          symbol:points.map(({i}) => fit.weights[i] < .5 ? "circle-open" : "circle"),opacity:.82}};
      const uncertainty = points.map(({i}) => fit.effectiveUncertainties[axisIndex][i]);
      data.push({...common,showlegend:axisIndex===0,yaxis:ref,y:points.map(({row}) => row[coordinate] - shift),
        error_y:{type:"data",array:uncertainty,thickness:1,width:2,color:color+"72"}});
      if (showResidual) data.push({...common,showlegend:false,yaxis:residualRef,y:points.map(({row,i},j) =>
        (row[coordinate] - fit.model[axisIndex][i]) / (residual === "sigma" ? uncertainty[j] : 1))});
    }
  });
  const plotLayout = layout({height:500,margin:{l:67,r:18,t:42,b:48},
    legend:{orientation:"h",y:1.12,x:0,font:{size:11}},xaxis:{...axis("Epoch (year)"),anchor:showResidual?"y4":"y2"},
    yaxis:{...axis("Δ R.A.* (mas)"),domain:domains[0]},yaxis2:{...axis("Δ Decl. (mas)"),domain:domains[1]},
    uirevision:"oid-" + detail.target.moca_oid + "-" + fit.mode + "-" + residual});
  if (showResidual) {
    plotLayout.yaxis3 = {...axis(""),domain:domains[2],nticks:3};
    plotLayout.yaxis4 = {...axis(""),domain:domains[3],nticks:3};
    plotLayout.annotations = ["R.A.* residual","Decl. residual"].map((name,i) => ({
      x:1,y:domains[i+2][1],xref:"paper",yref:"paper",xanchor:"right",yanchor:"bottom",
      text:name + (residual === "sigma" ? " / σ" : " (mas)"),showarrow:false,font:{size:11,color:"#516376"}
    }));
  }
  Plotly.react(el("trajectory"), data, plotLayout, plotConfig);
}

function literatureLabel(row) {
  return escapeHtml(row.moca_pid || [row.mission_name,row.data_release].filter(Boolean).join(" ") || row.origin || "MOCAdb row " + row.id);
}

function renderLiterature(node, literature, fit, parallax) {
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
  const plotLayout = layout({height:Math.max(parallax?155:185,84+17*categories.length),
    margin:{l:88,r:14,t:parallax?21:16,b:48},
    xaxis:{...axis(names[0]),domain:parallax?[0,1]:[0,.46]},
    yaxis:{tickmode:"array",tickvals:y,ticktext:categories,range:[-categories.length+.5,.6],automargin:true,
      gridcolor:"#e6edf3",tickfont:{size:11}}});
  if (!parallax) plotLayout.xaxis2 = {...axis(names[1]),domain:[.54,1]};
  Plotly.react(node,traces,plotLayout,plotConfig);
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
    {label:"Unreviewed",color:"#acb7c4",symbol:"circle",size:5,opacity:.37,
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
  Plotly.react(el("population"), traces, layout({height:370,
    xaxis:graphAxis("Δ μα* (mas/yr, signed log)","dx"),yaxis:graphAxis("Δ μδ (mas/yr, signed log)","dy"),
    legend:{orientation:"h",x:0,y:1.1},margin:{l:67,r:20,t:39,b:53}}),plotConfig);
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
      "Only epochs with a stored recalibration method are eligible, except 2MASS PSC.",
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
  navigate(state.detail ? state.index : nextIndex(state.index,1)).then(() => {
    if (generation === state.generation) loadBackground(generation);
  });
};
el("mode").onchange = () => {renderTarget();renderPopulation();};
el("residual").onchange = () => {if (state.detail) renderTarget();};
const shortcuts = {Home:"first",End:"last",ArrowLeft:"previous",ArrowUp:"previous",ArrowRight:"next",
  ArrowDown:"next",Backspace:"undo",u:"undo",q:"quit",o:"report",w:"wise",1:"adopt",0:"reject"};
document.addEventListener("keydown",event=>{
  if (state.done || state.busy || event.altKey || event.target.matches("input,select,textarea,[contenteditable]")) return;
  if (event.repeat && ["1","0","Backspace","u"].includes(event.key)) return;
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  if (event.metaKey || event.ctrlKey) {
    if (key === "z") {event.preventDefault();el("undo").click();}
    return;
  }
  if (key === "r") {event.preventDefault();navigate(state.index);return;}
  const action = event.code === "Numpad1" ? "adopt" : event.code === "Numpad0" ? "reject" : shortcuts[key];
  if (action) {event.preventDefault();el(action).click();}
});
renderPolicy();
loadSample();
