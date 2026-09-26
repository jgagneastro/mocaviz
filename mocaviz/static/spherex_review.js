(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const auth = window.__spherexURLAuth || {};
  delete window.__spherexURLAuth;
  const params = new URLSearchParams(location.search);
  const demo = params.get("mock") === "1";
  const base = new URL("./", location.href);
  const cache = new Map(), controllers = new Set(), jobs = [], history = [], hidden = new Set();
  let items = [], index = -1, current = null, context = null, generation = 0;
  let queueLane = "spiffstacker", queueRequest = {}, nextAfter = null, hasMore = false;
  let draining = false, closed = false, busyUndo = false, lastClass = "good";

  function status(text) { $("status").textContent = text; }
  function error(text) { $("errors").hidden = !text; $("errors").textContent = text || ""; }
  function key(item, lane = queueLane) { return lane + ":" + item.moca_oid; }
  function pendingCount() { return jobs.filter((j) => ["queued", "submitting"].includes(j.state)).length; }
  function options() {
    return {drop_worst_n: Number($("drop").value), chi2_sigma_cap: Number($("cap").value),
      nonfield_odds_k: Number($("odds").value), nonfield_extreme_odds_k: Number($("extreme").value)};
  }
  function writable() { return Boolean(context?.can_write && $("write-enabled").checked && !closed && !busyUndo); }
  function updateControls() {
    const pending = pendingCount();
    $("submitting").textContent = pending + " results currently submitting to mocadb";
    $("load").disabled = closed || busyUndo || pending > 0;
    $("lane").disabled = closed || busyUndo || pending > 0;
    $("more").disabled = closed || busyUndo || pending > 0 || !hasMore;
    $("write-enabled").disabled = !context?.can_write || closed;
    $("preview").disabled = !context?.can_write || !current || closed;
    $("save-type").disabled = !writable() || !current?.fit;
    $("bad-pixels").disabled = !writable() || !current?.fit?.bad_pixel_ids?.length;
    $("undo").disabled = !history.length || busyUndo || closed;
    $("retry").disabled = !writable() || !jobs.some((j) => j.state === "failed");
    $("report").disabled = !current || closed;
    $("wiseview").disabled = !current || !Number.isFinite(current.object.ra) || !Number.isFinite(current.object.dec) || closed;
    document.querySelectorAll("#classifications button").forEach((b) => {
      b.disabled = !writable() || !current || hidden.has(key(current.object));
    });
    $("write-hint").textContent = demo ? "Demonstration only — database writes are disabled." :
      writable() ? "Choose a quality label to submit and advance immediately. Undo restores the last decision." :
      context?.can_write ? "Enable submissions to classify. Preview is available without enabling writes." :
      "Read-only access. Management URL credentials are required to submit.";
  }
  async function api(operation, body = {}, suppliedController = null) {
    const controller = suppliedController || new AbortController();
    controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 90000);
    try {
      const url = new URL("api/spherex-review/" + operation, base);
      // URL-supplied credentials travel in headers, never repeated API URLs.
      const headers = {"Content-Type": "application/json"};
      if (!demo) {
        headers["X-MOCA-User"] = auth.user || "";
        headers["X-MOCA-Password"] = auth.password || "";
        headers["X-MOCA-Database"] = auth.database || "";
      }
      const response = await fetch(url, {method: "POST", headers, body: JSON.stringify({...body, mock: demo}),
        signal: controller.signal, cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer"});
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        const failure = new Error(payload.error || "Request failed.");
        failure.status = response.status;
        throw failure;
      }
      return payload;
    } finally { clearTimeout(timeout); controllers.delete(controller); }
  }
  function ids() {
    const text = $("oids").value.trim();
    if (!text) return [];
    const values = text.split(/[\s,;]+/).map(Number);
    if (values.some((v) => !Number.isSafeInteger(v) || v <= 0) || values.length > 500)
      throw new Error("Enter at most 500 positive integer object IDs.");
    return [...new Set(values)];
  }
  async function loadQueue(more = false) {
    if (pendingCount()) return;
    error("");
    try {
      if (!more) {
        queueLane = $("lane").value;
        queueRequest = {lane: queueLane, moca_oids: ids(), pending_only: $("pending-only").checked,
          min_snr: $("snr").value || null, min_sptn: $("sptn").value || null,
          no_known: $("no-known").checked, limit: 100};
        hidden.clear(); cache.clear(); items = []; current = null; index = -1; generation++;
      }
      status("Loading spectra from MOCAdb…"); $("load").disabled = true;
      const data = await api("queue", {...queueRequest, after: more ? nextAfter : 0});
      const start = items.length;
      items.push(...data.items); hasMore = data.has_more; nextAfter = data.next_after;
      $("queue-info").textContent = items.length + " objects loaded" + (hasMore ? " · more available" : " · end of queue");
      await show(start < items.length ? start : Math.max(0, items.length - 1));
    } catch (e) { error(e.message); status("Queue could not be loaded."); }
    finally { updateControls(); }
  }
  function visibleIndices() { return items.map((_, i) => i).filter((i) => !hidden.has(key(items[i]))); }
  function analysis(item, lane = queueLane, fitOptions = options(), refresh = false) {
    const k = key(item, lane) + ":" + JSON.stringify(fitOptions);
    if (refresh) cache.delete(k);
    if (!cache.has(k)) {
      const promise = api("analyze", {...item, lane, options: fitOptions});
      cache.set(k, promise); promise.catch(() => cache.delete(k));
      while (cache.size > 6) cache.delete(cache.keys().next().value);
    }
    return cache.get(k);
  }
  async function show(nextIndex, refresh = false) {
    if (closed) return;
    const gen = ++generation;
    current = null;
    const visible = visibleIndices();
    if (!visible.length) {
      index = -1;
      $("object-title").textContent = items.length ? "Queue complete" : "No matching spectra";
      $("object-meta").textContent = hasMore ? "Load the next batch to continue." : "";
      $("position").textContent = ""; $("best-type").textContent = "No fit loaded"; $("fit-detail").textContent = "";
      $("matches").replaceChildren(); $("stored").textContent = "";
      Plotly.purge($("plot"));
      status(pendingCount() ? "All loaded objects are queued for submission." : "Ready.");
      updateControls(); return;
    }
    index = visible.includes(nextIndex) ? nextIndex : (visible.find((v) => v >= nextIndex) ?? visible.at(-1));
    const item = items[index];
    $("object-title").textContent = item.designation || "moca_oid=" + item.moca_oid;
    $("object-meta").textContent = "Loading spectrum " + item.moca_specid + "…";
    $("position").textContent = (visible.indexOf(index) + 1) + " / " + visible.length + " remaining";
    status("Fitting spectrum…"); updateControls();
    try {
      const data = await analysis(item, queueLane, options(), refresh);
      if (gen !== generation || closed) return;
      current = data; render(data); status(data.warning || "Ready to review."); updateControls();
      for (const i of visible.slice(visible.indexOf(index) + 1, visible.indexOf(index) + 3))
        analysis(items[i]).catch(() => {});
    } catch (e) {
      if (gen !== generation || closed) return;
      if (e.status === 404) {
        hidden.add(key(item));
        error("Removed vanished spectrum for moca_oid=" + item.moca_oid + " from this queue.");
        await show(index + 1);
        return;
      }
      status("This spectrum could not be loaded; use Next to continue."); error(e.message); updateControls();
    }
  }
  function navigate(where) {
    const v = visibleIndices();
    if (!v.length) return;
    const pos = v.indexOf(index);
    const next = where === "first" ? 0 : where === "last" ? v.length - 1 :
      Math.max(0, Math.min(v.length - 1, pos + (where === "next" ? 1 : -1)));
    show(v[next]);
  }
  function render(data) {
    const obj = data.object, fit = data.fit;
    $("object-title").textContent = obj.designation || "Object " + obj.moca_oid;
    $("object-meta").textContent = queueLane + " · moca_oid=" + obj.moca_oid + " · spectrum=" + obj.moca_specid +
      " · S/N=" + Number(obj.median_snr_per_pix || 0).toFixed(1) + (obj.ignored ? " · spectrum currently ignored" : "");
    $("best-type").textContent = fit ? fit.best.display_type : "No valid fit";
    $("fit-detail").textContent = fit ? fit.best.grid_type + " · score " + fit.best.selection_score.toFixed(2) +
      " · " + fit.best.n_used + " points · " + fit.bad_pixel_ids.length + " newly flagged pixels" : data.warning || "";
    $("stored").textContent = JSON.stringify(data.state, null, 2); $("matches").replaceChildren();
    for (const row of (fit?.matches || []).slice(0, 15)) {
      const tr = document.createElement("tr");
      for (const value of [row.display_type, row.grid_type, row.selection_score?.toFixed(2),
        row.robust_reduced_chi2_10pct_cap?.toFixed(3), row.n_used]) {
        const td = document.createElement("td"); td.textContent = value ?? "—"; tr.append(td);
      }
      $("matches").append(tr);
    }
    const raw = data.raw_spectrum || [];
    const spectrum = fit?.spectrum || {wavelength_um: raw.map((r) => r.wavelength_angstrom / 1e4),
      flux: raw.map((r) => r.flux_flambda), error: raw.map((r) => r.flux_flambda_unc),
      flagged: raw.map((r) => Boolean(r.ignored))};
    const goodFlux = spectrum.flux.filter((f) => Number.isFinite(f) && f > 0).sort((a, b) => a - b);
    const norm = goodFlux[Math.floor(goodFlux.length / 2)] || 1;
    const traces = [{x: spectrum.wavelength_um, y: spectrum.flux.map((f) => f / norm),
      error_y: {type: "data", array: spectrum.error.map((e) => e / norm), visible: true, thickness: 1, width: 2},
      type: "scatter", mode: "markers", name: "SPHEREx",
      marker: {size: 5, color: spectrum.flagged.map((f) => f ? "#c15c43" : "#203f55")}}];
    const colors = ["#008a7a", "#d18a19", "#9c67ab"];
    for (const [i, overlay] of (fit?.overlays || []).entries()) traces.push({
      x: overlay.wavelength_um, y: overlay.flux.map((f) => f / norm), type: "scatter", mode: "lines",
      name: (i + 1) + ". " + overlay.label + " (" + overlay.grid + ")",
      line: {color: colors[i], width: i ? 1.5 : 2.5}, visible: i ? "legendonly" : true});
    Plotly.react($("plot"), traces, {
      margin: {l: 65, r: 15, t: 18, b: 65}, font: {family: "system-ui", color: "#264151", size: 13},
      xaxis: {title: "Wavelength (µm)", showgrid: true, gridcolor: "#e5ebef", mirror: true, linecolor: "#7a919e", linewidth: 2},
      yaxis: {title: "Fλ / median Fλ", showgrid: true, gridcolor: "#e5ebef", mirror: true, linecolor: "#7a919e", linewidth: 2},
      legend: {orientation: "h", y: -0.18}, paper_bgcolor: "#fff", plot_bgcolor: "#fff", uirevision: key(obj),
    }, {responsive: true, displaylogo: false, modeBarButtonsToRemove: ["toImage"]});
  }
  function decisionBody(item, action, classification) {
    return {lane: item.lane, moca_oid: item.object.moca_oid, moca_specid: item.object.moca_specid,
      options: item.fit?.options || options(), revision: item.revision, data_revision: item.data_revision,
      action, classification, is_public: Number($("visibility").value), rls: $("rls").value,
      sources: $("sources").value, allow_replace: $("replace").checked};
  }
  async function preview(action = "upsert_spt") {
    if (!current || !context?.can_write) return;
    try {
      const result = await api("preview", decisionBody(current, action, lastClass));
      $("preview-output").textContent = JSON.stringify({row_counts: result.row_counts,
        operations: result.plan.operations, warning: result.warning}, null, 2);
      $("preview-panel").open = true; status("Preview only — no database changes.");
    } catch (e) { error(e.message); }
  }
  function enqueue(action, classification = null) {
    if (!writable() || !current || hidden.has(key(current.object))) return;
    if (classification) lastClass = classification;
    const job = {body: decisionBody(current, action, classification), item: {...current.object},
      lane: current.lane, state: "queued", undoReceipt: null};
    jobs.push(job); history.push(job); hidden.add(key(job.item, job.lane));
    const oldIndex = index;
    show(oldIndex + 1); updateControls(); drain();
  }
  async function drain() {
    if (draining || closed) return;
    draining = true;
    try {
      for (const job of jobs) {
        if (job.state !== "queued" || closed) continue;
        job.state = "submitting"; job.controller = new AbortController(); updateControls();
        job.promise = (async () => {
          try {
            const prepared = await api("preview", job.body, job.controller);
            if (closed || job.state === "cancelled") return;
            const result = await api("submit", {receipt: prepared.receipt}, job.controller);
            job.undoReceipt = result.undo_receipt; job.state = "submitted";
          } catch (e) {
            if (closed || job.state === "cancelled") return;
            job.state = "failed"; hidden.delete(key(job.item, job.lane));
            error("Submission for moca_oid=" + job.item.moca_oid + " failed. It is back in the review queue.\n" + e.message);
          } finally {
            if (!closed) {
              updateControls();
              if (index === -1 && visibleIndices().length) show(visibleIndices()[0], true);
            }
          }
        })();
        await job.promise;
      }
    } finally { draining = false; if (!closed) updateControls(); }
  }
  async function undoLast() {
    if (!history.length || busyUndo || closed) return;
    busyUndo = true; updateControls();
    const job = history.at(-1);
    try {
      if (job.state === "queued") job.state = "cancelled";
      if (job.state === "submitting") { status("Waiting for this submission before undoing it…"); await job.promise; }
      if (job.state === "submitted") await api("undo", {receipt: job.undoReceipt});
      if (closed) return;
      history.pop(); job.state = "undone"; job.undoReceipt = null; hidden.delete(key(job.item, job.lane));
      if (queueLane !== job.lane) { queueLane = job.lane; $("lane").value = job.lane; items = [job.item]; hasMore = false; }
      else if (!items.some((i) => key(i) === key(job.item))) items.push(job.item);
      cache.clear(); await show(items.findIndex((i) => key(i) === key(job.item)), true); status("Last decision undone.");
    } catch (e) { if (!closed) error(e.message); }
    finally { busyUndo = false; if (!closed) updateControls(); }
  }
  async function retryFailed() {
    if (!writable()) return;
    for (const job of jobs.filter((j) => j.state === "failed")) {
      try {
        const latest = await analysis(job.item, job.lane, job.body.options, true);
        job.body.revision = latest.revision; job.body.data_revision = latest.data_revision;
        job.state = "queued"; hidden.add(key(job.item, job.lane));
      } catch (e) { error("moca_oid=" + job.item.moca_oid + ": " + e.message); }
    }
    if (current && hidden.has(key(current.object))) show(index + 1);
    updateControls(); drain();
  }
  function quit() {
    const count = pendingCount();
    if (count && !confirm("Quit and discard " + count + " pending submissions? Requests already sent may still commit; check MOCAdb before reviewing them again.")) return;
    closed = true;
    for (const job of jobs) if (job.state === "queued") job.state = "cancelled";
    for (const controller of controllers) controller.abort();
    for (const name of Object.keys(auth)) auth[name] = "";
    cache.clear(); history.length = 0; jobs.length = 0; items = []; current = null;
    generation++; hidden.clear(); Plotly.purge($("plot"));
    $("matches").replaceChildren(); $("stored").textContent = ""; $("preview-output").textContent = "";
    $("object-title").textContent = "Review session closed"; $("object-meta").textContent = "";
    $("position").textContent = ""; $("best-type").textContent = ""; $("fit-detail").textContent = "";
    error(""); status("Credentials and review data cleared from this tab. You can close the window.");
    document.querySelectorAll("button,input,select,textarea").forEach((el) => el.disabled = true);
    $("submitting").textContent = "Session closed";
  }
  function openReport() {
    if (current) window.open("https://mocadb.ca/search/results?search-query=" +
      encodeURIComponent("oid(" + current.object.moca_oid + ")") + "&search-type=star", "_blank", "noopener,noreferrer");
  }
  function openWiseView() {
    if (!current || $("wiseview").disabled) return;
    const p = new URLSearchParams({ra: current.object.ra, dec: current.object.dec, size: 30, band: 3,
      speed: 313, minbright: "-50.0000", maxbright: "500.0000", window: 2.64664, diff_window: 1,
      linear: 1, color: "", zoom: "20.0", border: 0, gaia: 1, invert: 1, maxdyr: 1, scandir: 0,
      neowise: 0, diff: 0, outer_epochs: 1, unique_window: 1, smooth_scan: 0, shift: 0, pmra: 0, pmdec: 0});
    window.open("http://byw.tools/wiseview-v2#" + p, "_blank", "noopener,noreferrer");
  }
  $("load").onclick = () => loadQueue(); $("more").onclick = () => loadQueue(true);
  $("refit").onclick = () => { cache.clear(); show(index, true); };
  for (const name of ["first", "previous", "next", "last"]) $(name).onclick = () => navigate(name);
  $("undo").onclick = undoLast; $("report").onclick = openReport; $("wiseview").onclick = openWiseView;
  $("quit").onclick = quit; $("retry").onclick = retryFailed; $("preview").onclick = () => preview();
  $("save-type").onclick = () => enqueue("upsert_spt"); $("bad-pixels").onclick = () => enqueue("bad_pixels");
  $("write-enabled").onchange = () => {
    if ($("write-enabled").checked && !confirm("Enable database submissions? Quality labels update visual vetting and autotype ignored state; rejected classes also ignore this lane's spectra. New spectral types use the selected visibility and RLS. Undo is available within this tab."))
      $("write-enabled").checked = false;
    updateControls();
  };
  window.addEventListener("beforeunload", (event) => {
    if (!closed && pendingCount()) { event.preventDefault(); event.returnValue = ""; }
  });
  document.addEventListener("keydown", (event) => {
    if (closed || event.repeat) return;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) || event.target.isContentEditable) return;
    const k = event.key.toLowerCase();
    if ((event.ctrlKey || event.metaKey) && k === "z") { event.preventDefault(); undoLast(); return; }
    if (event.ctrlKey || event.metaKey) return;
    const alt = {l: "load", n: "more", f: "refit", p: "preview", s: "save-type", b: "bad-pixels", r: "retry"};
    if (event.altKey) { if (alt[k]) { event.preventDefault(); $(alt[k]).click(); } return; }
    const button = {arrowleft: "previous", arrowup: "previous", arrowright: "next", arrowdown: "next",
      home: "first", end: "last", backspace: "undo", u: "undo", q: "quit", o: "report", w: "wiseview"}[k];
    // Numpad event.code also works when NumLock is off.
    const digit = /^Numpad[0-9]$/.test(event.code) ? event.code.slice(-1) : k;
    const decision = context?.classifications?.find(([, shortcut]) => shortcut === digit);
    if (decision) { event.preventDefault(); enqueue("classify", decision[0]); }
    else if (button) { event.preventDefault(); $(button).click(); }
  });
  async function start() {
    if (params.has("lane")) $("lane").value = params.get("lane");
    if (!$("lane").value) $("lane").value = "spiffstacker";
    if (params.has("moca_oid")) $("oids").value = params.get("moca_oid");
    if (params.has("min_snr")) $("snr").value = params.get("min_snr");
    if (params.has("min_sptn")) $("sptn").value = params.get("min_sptn");
    if (location.pathname.endsWith("spherex-autotype")) $("pending-only").checked = false;
    try {
      if (auth.host !== "mocadb.ca" || auth.port !== "3306") throw new Error("These tools connect only to mocadb.ca:3306.");
      context = await api("context");
      $("access").textContent = demo ? "Demo · read only" : context.can_write ? "Management · writes disabled until enabled" : "Collaborator · read only";
      const usable = new Set(["good", "good_candidate", "peculiar_ucd", "contaminated_ucd",
        "incomplete_but_promising", "good_plus_star", "good_reddened", "weird", "giant", "late_M"]);
      for (const [label, shortcut] of context.classifications) {
        const button = document.createElement("button");
        button.textContent = label.replaceAll("_", " ") + " [" + shortcut.toUpperCase() + "]";
        button.dataset.classification = label; button.className = usable.has(label) ? "usable" : "reject";
        button.onclick = () => enqueue("classify", label); $("classifications").append(button);
      }
      updateControls(); await loadQueue();
    } catch (e) {
      $("access").textContent = "Credentials required"; status("Open the original credential-bearing URL to begin.");
      error(e.message); updateControls();
    }
  }
  start();
})();
