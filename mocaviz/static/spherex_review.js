(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const auth = window.__spherexURLAuth || {};
  delete window.__spherexURLAuth;
  const params = new URLSearchParams(location.search);
  const demo = params.get("mock") === "1";
  const base = new URL("./", location.href);
  const fitHidden = new Set();
  const cache = new Map(), controllers = new Set(), jobs = [], history = [], hidden = new Set();
  let items = [], index = -1, current = null, context = null, generation = 0;
  let queueLane = "spiffstacker", queueRequest = {}, nextAfter = null, hasMore = false;
  let draining = false, closed = false, busyUndo = false, loading = false, lastClass = "good";
  let plotShown = false;
  const motionReview = window.SpherexMotionReview.create({api, writable, base, demo,
    preload: window.__spherexNativeVetting === true});
  const queueFilterFields = ["lane", "review-sample", "sublime3c-selection-pass", "sublime3c-priority-high", "sublime3c-psf-morphology", "adopted-spt-source", "adopted-spt-moca-pids",
    "queue-order", "cnn-priority-source", "spectral-cnn-probability", "batch-size", "missing-vetting", "vetting-classification",
    "wiseview-score", "no-wiseview-score", "sublime2-snr", "max-sublime2-snr", "cnn-probability", "galactic-latitude",
    "snr-wavelength-range", "snr", "max-snr", "max-chi2", "sptn", "current-fit-sptn", "current-fit-gap", "no-known", "exclude-duplicates", "oids"];
  let updatePresetButtons;
  let cnnFilterSample = "all";
  const catalogCnnBySample = new Map();
  const LOOKAHEAD = 50, FIT_CACHE_LIMIT = LOOKAHEAD + 14;
  let analyzing = false;
  const analysisQueue = [];
  let autoNextTimer = null, autoNextAttempt = null;

  function cancelQueuedAnalysis() {
    // An in-flight fit finishes once; obsolete queued work never reaches the server.
    for (const job of analysisQueue.splice(0)) {
      if (cache.get(job.key) === job) cache.delete(job.key);
      job.reject(new Error("Queued fit superseded."));
    }
  }
  function resetAnalysis() { cancelQueuedAnalysis(); cache.clear(); }
  async function drainAnalysis() {
    if (analyzing || closed) return;
    analyzing = true;
    try {
      while (analysisQueue.length && !closed) {
        const job = analysisQueue.shift();
        job.state = "running";
        try {
          const data = await api("analyze", {...job.item, lane: job.lane, options: job.options,
            adopted_spt_source: job.adoptedSptSource});
          if (Number(data.object?.moca_specid) !== Number(job.item.moca_specid) ||
              Number(data.object?.moca_oid) !== Number(job.item.moca_oid) ||
              (job.item.lane && data.lane !== job.lane) ||
              typeof data.read_only !== "boolean" || !Object.hasOwn(data.object, "spectral_cnn_probability")) {
            throw new Error("The server returned a different spectrum or an outdated response. " +
              "The review service may need to be restarted after deployment. No fit was loaded.");
          }
          job.state = "ready"; job.resolve(data);
        } catch (e) {
          if (cache.get(job.key) === job) cache.delete(job.key);
          job.reject(e);
        }
        updateCacheStatus();
        // Let navigation/rendering reprioritize the queue before starting another fit.
        await Promise.resolve();
      }
    } finally { analyzing = false; scheduleAutoNextBatch(); }
  }

  function status(text) { $("status").textContent = text; }
  let submissionErrorTimer = null, submissionErrorJob = null;
  function error(text, failedJob = null) {
    clearTimeout(submissionErrorTimer); submissionErrorTimer = null;
    submissionErrorJob = failedJob;
    $("errors").hidden = !text; $("errors").textContent = text || "";
    if (text && failedJob) submissionErrorTimer = setTimeout(() => {
      if (submissionErrorJob === failedJob) error("");
    }, Math.max(0, failedJob.errorExpiresAt - Date.now()));
  }
  function resolveSubmissionErrors(job) {
    job.errorMessage = null;
    job.errorExpiresAt = 0;
    if (submissionErrorJob === job) {
      const other = [...jobs].reverse().find(previous =>
        previous.errorMessage && previous.errorExpiresAt > Date.now());
      error(other?.errorMessage || "", other || null);
      if (!other) status("Submission for moca_oid=" + job.item.moca_oid + " saved.");
    }
  }
  function key(item, lane = item.lane ?? queueLane) { return lane + ":" + item.moca_oid + ":" + item.moca_specid; }
  function pendingCount() { return jobs.filter((j) => ["queued", "submitting"].includes(j.state)).length; }
  function failedCount() { return jobs.filter(job => job.state === "failed").length; }
  function moveToSubmissionTail(job) {
    jobs.splice(jobs.indexOf(job), 1);
    jobs.push(job);
  }
  function updateUploadStatus() {
    const pending = pendingCount();
    const uploading = jobs.filter((job) => job.state === "submitting").length;
    const panel = $("upload-draining");
    panel.hidden = closed || plotShown || pending === 0;
    const remaining = pending + (pending === 1 ? " result remaining" : " results remaining");
    const counts = uploading + " uploading · " + (pending - uploading) + " waiting";
    if ($("upload-remaining").textContent !== remaining) $("upload-remaining").textContent = remaining;
    if ($("upload-counts").textContent !== counts) $("upload-counts").textContent = counts;
  }
  function canAutoNextBatch() {
    return hasMore && nextAfter != null && nextAfter !== 0 && items.length > 0 &&
      !queueRequest.moca_specid && !closed && !loading && !busyUndo && !draining &&
      !analyzing && analysisQueue.length === 0 && controllers.size === 0 &&
      pendingCount() === 0 && !plotShown && visibleIndices().length === 0;
  }
  function scheduleAutoNextBatch() {
    if (autoNextTimer !== null || !canAutoNextBatch()) return;
    const request = queueRequest, cursor = JSON.stringify(nextAfter);
    if (autoNextAttempt?.request === request && autoNextAttempt.cursor === cursor) return;
    autoNextTimer = setTimeout(() => {
      autoNextTimer = null;
      if (queueRequest !== request || JSON.stringify(nextAfter) !== cursor || !canAutoNextBatch()) return;
      // One automatic attempt per cursor. A failed request needs manual retry.
      autoNextAttempt = {request, cursor};
      void loadQueue(true, true);
    }, 0);
  }
  function batchSize() {
    const value = $("batch-size").valueAsNumber;
    if (!Number.isInteger(value) || value < 1 || value > 500)
      throw new Error("Batch size must be a whole number between 1 and 500.");
    return value;
  }
  function options() {
    return {drop_worst_n: Number($("drop").value), chi2_sigma_cap: Number($("cap").value),
      nonfield_odds_k: Number($("odds").value), nonfield_extreme_odds_k: Number($("extreme").value)};
  }
  function policyReady() { return (context?.write_policy_version ?? 0) >= 1; }
  function writable() { return Boolean(policyReady() && context?.can_write && $("write-enabled").checked && !closed && !busyUndo); }
  function canReview() { return Boolean(current && !current.read_only); }
  function updateControls() {
    const pending = pendingCount();
    updateUploadStatus();
    const failed = failedCount();
    $("submitting").textContent = pending + " results currently submitting to mocadb" +
      (failed ? " · " + failed + " awaiting retry" : "");
    updateCacheStatus();
    $("fit-filter-info").textContent = fitHidden.size ? fitHidden.size + " spectra skipped by current-fit cuts; no vetting saved" : "";
    $("load").disabled = !context || closed || busyUndo || loading || pending > 0;
    $("specid").disabled = closed || busyUndo || loading || pending > 0;
    for (const name of queueFilterFields)
      $(name).disabled = closed || busyUndo || loading || pending > 0;
    $("sample-hint").hidden = $("review-sample").value !== "public-ucd";
    const sample = $("review-sample").value;
    $("sublime3c-selection-controls").hidden = sample !== "sublime3c";
    $("sublime3c-selection-pass").disabled ||= sample !== "sublime3c";
    $("sublime3c-priority-high").disabled ||= sample !== "sublime3c";
    $("sublime3c-psf-morphology").disabled ||= sample !== "sublime3c";
    if (sample !== cnnFilterSample) {
      catalogCnnBySample.set(cnnFilterSample, $("cnn-probability").value);
      $("cnn-probability").value = catalogCnnBySample.get(sample) ?? (["all", "sublime2"].includes(sample) ? "0.8" : "");
      cnnFilterSample = sample;
    }
    const sublime2Cuts = ["all", "sublime2"].includes($("review-sample").value);
    $("sublime2-cuts").hidden = !sublime2Cuts;
    $("sublime2-cuts-hint").textContent = sublime2Cuts ?
      "SUBLIME2 detection cut applies to All objects and SUBLIME2." :
      "SUBLIME2 detection cut is not applied to this sample.";
    for (const field of ["sublime2-snr", "max-sublime2-snr"]) $(field).disabled ||= !sublime2Cuts;
    $("wiseview-score").disabled ||= $("no-wiseview-score").checked;
    $("more").disabled = closed || busyUndo || loading || pending > 0 || !hasMore;
    updatePresetButtons?.();
    if (current?.read_only) $("write-enabled").checked = false;
    $("write-enabled").disabled = !context?.can_write || !policyReady() || current?.read_only || closed;
    $("preview").disabled = !context?.can_write || !policyReady() || !canReview() || closed;
    $("save-type").disabled = !writable() || !canReview() || !current?.fit;
    $("bad-pixels").disabled = !writable() || !canReview() || !current?.fit?.bad_pixel_ids?.length;
    $("undo").disabled = !history.length || busyUndo || loading || closed;
    $("refit").disabled = !current || loading || closed;
    for (const name of ["first", "previous", "next", "last"]) $(name).disabled = loading || closed;
    $("retry").disabled = !writable() || failed === 0;
    $("report").disabled = !current || closed;
    $("wiseview").disabled = !current || !Number.isFinite(current.object.ra) || !Number.isFinite(current.object.dec) || closed;
    document.querySelectorAll("#classifications button").forEach((b) => {
      b.disabled = !writable() || !canReview() || hidden.has(key(current.object, current.lane));
    });
    $("write-hint").textContent = demo ? "Demonstration only — database writes are disabled." :
      context?.can_write && !policyReady() ? "Restart the review service and reload to enable automatic photometric/ignored flags." :
      current?.read_only ? "Read-only spectrum: outside SPIFF, SPIFFStacker and SUBLIMEaperture. Template fitting is available; database writes are disabled." :
      writable() ? "Choose a quality label to submit and advance immediately. Undo restores the last decision." :
      context?.can_write ? "Enable submissions to classify. Preview is available without enabling writes." :
      "Read-only access. Management URL credentials are required to submit.";
    motionReview.update();
    scheduleAutoNextBatch();
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
    } finally { clearTimeout(timeout); controllers.delete(controller); scheduleAutoNextBatch(); }
  }
  function ids() {
    const text = $("oids").value.trim();
    if (!text) return [];
    const values = text.split(/[\s,;]+/).map(Number);
    if (values.some((v) => !Number.isSafeInteger(v) || v <= 0) || values.length > 500)
      throw new Error("Enter at most 500 positive integer object IDs.");
    return [...new Set(values)];
  }
  function spectrumId(value) {
    let text = value.trim();
    // Only extract the ID. Never navigate to a pasted URL or reuse its credentials.
    for (let depth = 0; depth < 3; depth++) {
      if (/^[0-9]+$/.test(text) && Number.isSafeInteger(Number(text)) && Number(text) > 0)
        return Number(text);
      try {
        const url = new URL(text);
        if (!["http:", "https:"].includes(url.protocol)) break;
        text = (url.searchParams.get("specid") || url.searchParams.get("moca_specid") || "").trim();
      } catch { break; }
    }
    throw new Error("Enter a positive integer spectrum ID or a URL containing specid.");
  }
  function requiredQueueFilterVersion(request) {
    if (request.moca_specid) return request.adopted_spt_source === "public" ? 9 : 0;
    if (request.sublime3c_selection_pass_only || request.sublime3c_priority_high_only) return 22;
    if (request.lane === "all" || request.vetting_classification) return 21;
    if (request.queue_order === "snr_bin_spt") return 19;
    if (request.sublime3c_psf_morphology && request.sublime3c_psf_morphology !== "all") return 18;
    if (request.missing_vetting === "both") return 16;
    if (request.queue_order === "gal_cnn_snr_bin_spt") return 14;
    if (request.max_snr != null || request.max_sublime2_snr != null) return 12;
    if (request.cnn_priority_source === "combined" && ["gal_cnn_spt_snr", "cnn_spt_snr"].includes(request.queue_order)) return 11;
    if (request.min_spectral_cnn_probability != null || ["gal_cnn_spt_snr", "cnn_spt_snr"].includes(request.queue_order)) return 10;
    if (request.adopted_spt_source || request.adopted_spt_moca_pids?.length) return 9;
    if (request.queue_order === "gal_cnn_spt_snr") return 7;
    if (request.queue_order === "cnn_spt_snr") return 6;
    if (request.queue_order !== "oid_asc" || request.no_known || request.exclude_duplicates || request.no_wiseview_score ||
        !["all", "public-ucd"].includes(request.review_sample) ||
        ["min_sublime2_snr", "min_cnn_probability", "min_abs_galactic_latitude", "max_reduced_chi2", "min_snr"].some((name) => request[name] != null)) return 5;
    if (request.public_ucd_only) return 4;
    if (request.missing_vetting === "viable_elsewhere") return 2;
    return request.min_wiseview_score !== null || !["lane", "all"].includes(request.missing_vetting) ? 1 : 0;
  }
  async function showQueueTotal(request) {
    const label = $("queue-total");
    label.textContent = "Counting all matches…";
    try {
      const {total, queue_filter_version} = await api("queue-count", request);
      if (request.missing_vetting === "both" && (queue_filter_version ?? 0) < 16)
        throw new Error("The review service needs to be restarted to include SUBLIME aperture vettings.");
      if (request.sublime3c_psf_morphology && request.sublime3c_psf_morphology !== "all" && (queue_filter_version ?? 0) < 18)
        throw new Error("The review service needs to be restarted to count PSF morphology passes.");
      if ((request.sublime3c_selection_pass_only || request.sublime3c_priority_high_only) && (queue_filter_version ?? 0) < 22)
        throw new Error("The review service needs to be restarted to count updated-selection passes.");
      if ((request.max_snr != null || request.max_sublime2_snr != null) && (queue_filter_version ?? 0) < 12)
        throw new Error("The review service needs to be restarted to count these S/N filters.");
      if (!closed && queueRequest === request) label.textContent = total.toLocaleString() + ((request.min_current_fit_sptn != null || request.min_current_fit_gap != null) ? " database matches before current-fit cut" : " total matches at load");
    } catch {
      if (!closed && queueRequest === request) label.textContent = "Total match count unavailable";
    }
  }
  let otherSampleVetting = $("missing-vetting").value, previousSample = $("review-sample").value;
  let otherSampleFitMinimum = $("current-fit-sptn").value;
  let otherSampleFitGap = $("current-fit-gap").value;
  let otherSampleSptSource = $("adopted-spt-source").value;
  function sublime4SampleDefaults() {
    // The SUBLIME2 image classifier and legacy stored-fit defaults can
    // otherwise exclude every new spectrum before the reviewer fits it.
    for (const id of ["cnn-probability", "max-chi2"]) {
      const field = $(id);
      if (field.value === field.defaultValue) field.value = "";
    }
  }
  $("review-sample").addEventListener("change", () => {
    const vetting = $("missing-vetting");
    if ($("review-sample").value === "public-ucd" && previousSample !== "public-ucd") {
      otherSampleVetting = vetting.value;
      otherSampleSptSource = $("adopted-spt-source").value;
      vetting.value = "all";
      $("adopted-spt-source").value = "public";
    } else if ($("review-sample").value !== "public-ucd" && previousSample === "public-ucd") {
      vetting.value = otherSampleVetting;
      $("adopted-spt-source").value = otherSampleSptSource;
    }
    if ($("review-sample").value === "sublime4") {
      $("lane").value = "sublimeaperture";
      $("lane").dispatchEvent(new Event("change"));
      $("review-sample").value = "sublime4";
      sublime4SampleDefaults();
    }
    if ($("review-sample").value === "sublime3c" && previousSample !== "sublime3c") {
      otherSampleFitMinimum = $("current-fit-sptn").value;
      otherSampleFitGap = $("current-fit-gap").value;
      $("current-fit-sptn").value = "10";
      $("current-fit-gap").value = "2";
      $("lane").value = "sublimeaperture";
      $("adopted-spt-source").value = "private";
      $("queue-order").value = "oid_asc";
      for (const id of ["snr", "max-snr", "max-chi2", "sptn", "galactic-latitude", "cnn-probability", "spectral-cnn-probability"])
        $(id).value = "";
    }
    if (previousSample === "sublime3c" && $("review-sample").value !== "sublime3c") {
      $("current-fit-sptn").value = otherSampleFitMinimum;
      $("current-fit-gap").value = otherSampleFitGap;
    }
    previousSample = $("review-sample").value;
    updateControls();
  });
  $("no-wiseview-score").addEventListener("change", updateControls);
  $("vetting-classification").addEventListener("change", () => {
    if ($("vetting-classification").value) $("missing-vetting").value = "all";
    updateControls();
  });
  function setDatasetTitle(name) {
    const title = $("dataset-title");
    title.textContent = title.title = name;
    title.hidden = !name;
  }
  async function loadQueue(more = false, automatic = false, datasetName = "") {
    if (pendingCount() || loading || closed || busyUndo) return;
    if (more) autoNextAttempt = {request: queueRequest, cursor: JSON.stringify(nextAfter)};
    error("");
    try {
      if (!more) {
        const specid = $("specid").value.trim();
        const sublime2Cuts = ["all", "sublime2"].includes($("review-sample").value);
        const request = specid ? {moca_specid: spectrumId(specid), adopted_spt_source: $("adopted-spt-source").value} :
          {lane: $("lane").value, moca_oids: ids(), pending_only: $("missing-vetting").value !== "all",
            missing_vetting: $("missing-vetting").value,
            vetting_classification: $("vetting-classification").value || null,
            min_wiseview_score: $("no-wiseview-score").checked ? null : $("wiseview-score").value || null,
            no_wiseview_score: $("no-wiseview-score").checked, review_sample: $("review-sample").value,
            sublime3c_selection_pass_only: $("review-sample").value === "sublime3c" && $("sublime3c-selection-pass").checked,
            sublime3c_priority_high_only: $("review-sample").value === "sublime3c" && $("sublime3c-priority-high").checked,
            sublime3c_psf_morphology: $("review-sample").value === "sublime3c" ? $("sublime3c-psf-morphology").value : "all",
            queue_order: $("queue-order").value, cnn_priority_source: $("cnn-priority-source").value,
            min_spectral_cnn_probability: $("spectral-cnn-probability").value || null,
            adopted_spt_source: $("adopted-spt-source").value,
            adopted_spt_moca_pids: [...new Set($("adopted-spt-moca-pids").value.trim().split(/[\s,;]+/).filter(Boolean))],
            min_sublime2_snr: sublime2Cuts ? $("sublime2-snr").value || null : null,
            max_sublime2_snr: sublime2Cuts ? $("max-sublime2-snr").value || null : null,
            min_cnn_probability: $("cnn-probability").value || null,
            min_abs_galactic_latitude: $("galactic-latitude").value || null,
            max_reduced_chi2: $("max-chi2").value || null,
            snr_wavelength_range: $("snr-wavelength-range").value,
            min_snr: $("snr").value || null, max_snr: $("max-snr").value || null,
            min_sptn: $("sptn").value || null,
            min_current_fit_sptn: $("current-fit-sptn").value || null,
            min_current_fit_gap: $("current-fit-gap").value || null,
            exclude_duplicates: $("exclude-duplicates").checked,
            no_known: $("no-known").checked, public_ucd_only: $("review-sample").value === "public-ucd", limit: batchSize()};
        if ((context?.queue_filter_version ?? 0) < requiredQueueFilterVersion(request))
          throw new Error("The review service needs to be restarted to enable these queue filters. No queue was loaded.");
        if (request.min_current_fit_sptn != null && (!Number.isFinite(Number(request.min_current_fit_sptn)) ||
            Number(request.min_current_fit_sptn) < -60 || Number(request.min_current_fit_sptn) > 40))
          throw new Error("Current fitted type must be a number from -60 to 40.");
        if (request.min_current_fit_gap != null && !Number.isFinite(Number(request.min_current_fit_gap)))
          throw new Error("Native DR1 fit separation must be a finite number.");
        queueLane = $("lane").value;
        queueRequest = request; autoNextAttempt = null;
        hidden.clear(); fitHidden.clear();
        for (const job of jobs) {
          if (job.state === "failed") hidden.add(key(job.item, job.lane));
        }
        setDatasetTitle("");
        resetAnalysis(); motionReview.clear(); items = []; current = null; index = -1; generation++;
        hasMore = false; nextAfter = null;
        $("queue-info").textContent = "";
        $("queue-total").textContent = "";
        $("preview-output").textContent = ""; $("preview-panel").open = false;
        clearTarget();
      }
      const requestBody = {...queueRequest, after: more ? nextAfter : 0};
      if (!queueRequest.moca_specid) requestBody.limit = batchSize();
      loading = true; updateControls();
      status(automatic ? "Loading next batch automatically…" : "Loading spectra from MOCAdb…");
      const data = await api("queue", requestBody);
      if (closed) return;
      if ((data.queue_filter_version ?? 0) < requiredQueueFilterVersion(queueRequest))
        throw new Error("The review service needs to be restarted to apply these queue filters. No queue was loaded.");
      if (queueRequest.moca_specid && (data.items?.length !== 1 ||
          Number(data.items[0].moca_specid) !== queueRequest.moca_specid ||
          !Object.hasOwn(data, "lane") || typeof data.read_only !== "boolean")) {
        throw new Error("The server did not return spectrum " + queueRequest.moca_specid +
          ". The review service may need to be restarted after deployment. No spectrum was loaded.");
      }
      if (Object.hasOwn(data, "lane")) {
        queueLane = data.lane;
        if (queueLane) $("lane").value = queueLane;
      }
      const start = items.length;
      items.push(...data.items); hasMore = data.has_more; nextAfter = data.next_after;
      if (!more) setDatasetTitle(datasetName);
      if (more && data.items.length === 0)
        autoNextAttempt = {request: queueRequest, cursor: JSON.stringify(nextAfter)};
      $("queue-info").textContent = queueRequest.moca_specid ? "Spectrum " + queueRequest.moca_specid +
        (data.read_only ? " · read only" : " · " + queueLane) :
        items.length + (queueLane === "all" ? " spectra loaded" : " objects loaded") +
          (hasMore ? " · more available" : " · end of queue");
      if (!more && !queueRequest.moca_specid && (data.queue_filter_version ?? 0) >= 3) {
        void showQueueTotal(queueRequest);
      }
      await show(start < items.length ? start : Math.max(0, items.length - 1));
      if (more && data.items.length === 0 && hasMore)
        $("object-meta").textContent = "No spectra returned. Use Next batch to retry.";
    } catch (e) { if (!closed) {
      error(e.message); status("Spectra could not be loaded.");
      if (automatic) $("object-meta").textContent = "Automatic next-batch loading stopped. Use Next batch to retry.";
    } }
    finally { loading = false; if (!closed) updateControls(); }
  }
  function visibleIndices() { return items.map((_, i) => i).filter((i) => !hidden.has(key(items[i])) && !fitHidden.has(key(items[i]))); }
  function upcomingItems() {
    if (index < 0) return [];
    const upcoming = [];
    for (let i = index + 1; i < items.length && upcoming.length < LOOKAHEAD; i++) {
      if (!hidden.has(key(items[i])) && !fitHidden.has(key(items[i]))) upcoming.push(items[i]);
    }
    return upcoming;
  }
  function fitCacheKey(item, lane, fitOptions, adoptedSptSource = queueRequest.adopted_spt_source || "private") {
    return key(item, lane) + ":" + adoptedSptSource + ":" + JSON.stringify(fitOptions);
  }
  function updateCacheStatus() {
    const fitOptions = options();
    const ready = upcomingItems().filter(item => cache.get(fitCacheKey(item, item.lane ?? queueLane, fitOptions))?.state === "ready");
    const message = "Cached " + ready.length + " next spectra in queue";
    const counter = $("cached-next");
    if (counter.textContent !== message) counter.textContent = message;
  }
  function analysis(item, fitOptions = options(), refresh = false, background = false) {
    const lane = item.lane ?? queueLane;
    const adoptedSptSource = queueRequest.adopted_spt_source || "private";
    const k = fitCacheKey(item, lane, fitOptions, adoptedSptSource);
    if (refresh) cache.delete(k);
    let job = cache.get(k);
    if (!job) {
      job = {key: k, item, lane, options: fitOptions, adoptedSptSource, state: "queued"};
      job.promise = new Promise((resolve, reject) => { job.resolve = resolve; job.reject = reject; });
      job.promise.catch(() => { if (cache.get(k) === job) cache.delete(k); });
      if (background) analysisQueue.push(job);
      else analysisQueue.unshift(job);
    } else if (!background && job.state === "queued") {
      analysisQueue.splice(analysisQueue.indexOf(job), 1);
      analysisQueue.unshift(job);
    }
    // Keep the current and upcoming fits, plus recent fits for back navigation.
    cache.delete(k); cache.set(k, job);
    while (cache.size > FIT_CACHE_LIMIT) {
      const oldest = [...cache].find(([, entry]) => entry.state === "ready");
      if (!oldest) break;
      cache.delete(oldest[0]);
    }
    void drainAnalysis();
    return job.promise;
  }
  function clearFit() {
    $("best-type").textContent = "No fit loaded"; $("fit-detail").textContent = "";
    $("matches").replaceChildren(); $("stored").textContent = "";
    Plotly.purge($("plot"));
    plotShown = false; updateUploadStatus();
  }
  function clearTarget() {
    $("object-title").textContent = ""; $("object-meta").textContent = ""; $("position").textContent = "";
    clearFit();
  }
  async function show(nextIndex, refresh = false) {
    if (closed) return;
    if (refresh) fitHidden.clear();
    const gen = ++generation;
    cancelQueuedAnalysis();
    const fitOptions = options();
    current = null;
    const visible = visibleIndices();
    if (!visible.length) {
      motionReview.clear();
      index = -1;
      clearTarget();
      $("object-title").textContent = items.length ? "Queue complete" : "No matching spectra";
      $("object-meta").textContent = hasMore ? (items.length ?
        "The next batch will load when pending requests finish. Next batch is also available manually." :
        "Use Next batch to continue.") : "";
      status(pendingCount() ? "All loaded objects are queued for submission." : "");
      updateControls(); return;
    }
    index = visible.includes(nextIndex) ? nextIndex : (visible.find((v) => v >= nextIndex) ?? visible.at(-1));
    const item = items[index], upcoming = upcomingItems();
    motionReview.clear(refresh ? [] : [item, ...upcoming]);
    $("object-title").textContent = item.designation || "moca_oid=" + item.moca_oid;
    $("object-meta").textContent = "";
    $("position").textContent = (visible.indexOf(index) + 1) + " / " + visible.length + " remaining in loaded queue";
    const hasFitCut = [queueRequest.min_current_fit_sptn, queueRequest.min_current_fit_gap]
      .some(value => value != null && value !== "");
    status(hasFitCut ? "Checking current-fit cuts… " + fitHidden.size +
      " spectra skipped by these cuts; no classifications saved by filtering." : "Fitting spectrum…");
    updateControls();
    try {
      const data = await analysis(item, fitOptions, refresh);
      if (gen !== generation || closed) return;
      const minimum = queueRequest.min_current_fit_sptn;
      const fittedType = data.fit?.best?.spectral_type_number;
      const gapMinimum = queueRequest.min_current_fit_gap;
      const gap = data.fit?.delta_early_minus_late;
      const failsGap = data.fit?.fit_version === "native_signed_student4_v1" && gapMinimum != null && gapMinimum !== "" &&
        (typeof gap !== "number" || !Number.isFinite(gap) || gap < Number(gapMinimum));
      if (failsGap || (minimum != null && minimum !== "" &&
          (typeof fittedType !== "number" || !Number.isFinite(fittedType) || fittedType < Number(minimum)))) {
        fitHidden.add(key(item));
        clearFit(); updateControls();
        await show(index + 1);
        return;
      }
      current = data; render(data);
      motionReview.show(data, upcoming, async candidate =>
        (await analysis(candidate, fitOptions, false, true)).object);
      status(data.warning || "Ready to review."); updateControls();
      for (const candidate of upcoming)
        analysis(candidate, fitOptions, false, true).catch(() => {});
      updateCacheStatus();
    } catch (e) {
      if (gen !== generation || closed) return;
      if (e.status === 404) {
        hidden.add(key(item));
        error("Removed vanished spectrum for moca_oid=" + item.moca_oid + " from this queue.");
        await show(index + 1);
        return;
      }
      clearFit();
      $("object-meta").textContent = "Spectrum " + item.moca_specid + " could not be loaded.";
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
    const name = obj.designation || "Object " + obj.moca_oid;
    const type = obj.adopted_spectral_type, reference = obj.adopted_spectral_type_reference;
    const typeLabel = obj.adopted_spt_source === "public" ? "Public-adopted" : "Adopted";
    const fittedLabel = fit?.best?.display_type || fit?.best?.spectral_type;
    $("object-title").textContent = name + (fittedLabel ? ` · Current fit ${fittedLabel}` : "") + (type ? ` · ${typeLabel} ${type}${reference ? ` (${reference})` : ""}` : "");
    const source = data.read_only ? "Read only · package=" + (obj.moca_specpackid ?? "none") : data.lane;
    $("object-meta").textContent = source + " · moca_oid=" + obj.moca_oid + " · spectrum=" + obj.moca_specid +
      " · S/N=" + Number(obj.median_snr_per_pix || 0).toFixed(1) + (obj.ignored ? " · spectrum currently ignored" : "");
    const finite = (value) => typeof value === "number" && Number.isFinite(value);
    const probability = obj.spectral_cnn_probability;
    const chi2 = [fit?.overlays?.[0]?.display_reduced_chi2, fit?.best?.robust_reduced_chi2_10pct_cap,
      fit?.best?.reduced_chi2_10pct_cap, fit?.best?.reduced_chi2].find(finite);
    const cnn = document.createElement("span"), fitQuality = document.createElement("span");
    cnn.id = "header-cnn";
    cnn.title = "Stored spectral autotype CNN P(good) for this exact spectrum and lane" +
      (obj.spectral_cnn?.model ? " · " + obj.spectral_cnn.model : "") + ". Not recomputed by live template refits.";
    cnn.textContent = "Spectral CNN P(good)=" + (finite(probability) && probability >= 0 && probability <= 1 ?
      (100 * probability).toFixed(1) + "%" : "—");
    fitQuality.id = "header-chi2";
    fitQuality.title = "Best displayed fit reduced chi squared; prefers robust 10% capped, then capped, then raw.";
    fitQuality.textContent = "χ²ᵣ=" + (finite(chi2) ? chi2.toFixed(2) : "—");
    const catalogCNN = document.createElement("span");
    catalogCNN.id = "header-sublime2-cnn";
    catalogCNN.title = "Highest SUBLIME2 catalog CNN good probability for this object; independent of spectral autotype CNN.";
    catalogCNN.textContent = "SUBLIME2 CNN P=" + (finite(obj.sublime2_cnn_probability) && obj.sublime2_cnn_probability >= 0 && obj.sublime2_cnn_probability <= 1 ?
      (100 * obj.sublime2_cnn_probability).toFixed(1) + "%" : "—");
    $("object-meta").append(" · ", cnn, " · ", catalogCNN, " · ", fitQuality);
    if (fit?.fit_version === "native_signed_student4_v1")
      $("object-meta").append(" · Native DR1 fit · " + fit.best.n_used + " channels · early/late separation=" + (finite(fit.delta_early_minus_late) ? fit.delta_early_minus_late.toFixed(2) : "—"));
    const morphology = obj.sublime3c_morphology;
    if (morphology) {
      const priority = {priority_high_motion_v1: "high", priority_normal_motion_v1: "normal"}[morphology.review_priority];
      if (priority) {
        const score = Number(morphology.review_priority_score);
        $("object-meta").append(" · CNN review priority " + priority +
          (morphology.review_priority_score != null && Number.isFinite(score) ? " (" + score.toFixed(3) + ")" : ""));
      }
      const flag = document.createElement("span");
      const status = ["pass", "fail"].includes(morphology.status) ? morphology.status : "undefined";
      flag.id = "header-psf-morphology";
      flag.className = "psf-morphology-flag " + status;
      flag.textContent = "PSF morphology: " + ({pass: "passing", fail: "poor", undefined: "undefined"}[status]);
      const reasons = Object.entries(morphology.bands || {}).map(([band, result]) =>
        band + ": " + (result.status || "undefined") + (result.reason ? " (" + String(result.reason).replaceAll("_", " ").replaceAll("|", ", ") + ")" : ""));
      flag.title = (morphology.scope || "SUBLIME3C detection") +
        (morphology.candidate_id ? " · candidate " + morphology.candidate_id : " · no matching detection") +
        (reasons.length ? "\n" + reasons.join("\n") : "\nNo conclusive measurement available.") +
        "\nDiagnostic flag only; human vetting is unchanged.";
      $("object-meta").append(" · ", flag);
    }
    const origin = document.createElement("div");
    origin.textContent = "Object origin: " + (obj.object_origin?.trim() || "—");
    $("object-meta").append(origin);
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
    const count = Number($("match-count").value);
    if (fit && (fit.overlays?.length || 0) < Math.min(count, fit.matches?.length || 0))
      $("fit-detail").textContent += " · Restart the review service and reload to show more matches.";
    const figure = SpherexReviewPlot.figure(data, key(obj, data.lane) + ":" + count, $("plot").clientWidth, count);
    Plotly.react($("plot"), figure.traces, figure.layout,
      {responsive: true, displaylogo: false, modeBarButtonsToRemove: ["toImage"]});
    plotShown = figure.traces.some((trace) => trace.x?.length && trace.y?.length);
    updateUploadStatus();
  }
  function decisionBody(item, action, classification) {
    return {lane: item.lane, moca_oid: item.object.moca_oid, moca_specid: item.object.moca_specid,
      options: item.fit?.options || options(), revision: item.revision, data_revision: item.data_revision,
      action, classification, is_public: Number($("visibility").value), rls: $("rls").value,
      sources: $("sources").value, allow_replace: $("replace").checked};
  }
  async function preview(action = "upsert_spt") {
    if (!canReview() || !context?.can_write || !policyReady()) return;
    try {
      const result = await api("preview", decisionBody(current, action, lastClass));
      $("preview-output").textContent = JSON.stringify({row_counts: result.row_counts,
        operations: result.plan.operations, warning: result.warning}, null, 2);
      $("preview-panel").open = true; status("Preview only — no database changes.");
    } catch (e) { error(e.message); }
  }
  function enqueue(action, classification = null) {
    if (!writable() || !canReview() || hidden.has(key(current.object, current.lane))) return;
    if (classification) lastClass = classification;
    const job = {body: decisionBody(current, action, classification), item: {...current.object, lane: current.lane},
      lane: current.lane, state: "queued", undoReceipt: null};
    jobs.push(job); history.push(job); hidden.add(key(job.item, job.lane));
    const oldIndex = index;
    show(oldIndex + 1); updateControls(); drain();
  }
  async function drain() {
    if (draining || closed) return;
    draining = true;
    try {
      while (!closed) {
        const job = jobs.find(candidate => candidate.state === "queued");
        if (!job) break;
        job.state = "submitting"; job.controller = new AbortController(); updateControls();
        job.promise = (async () => {
          try {
            const prepared = await api("preview", job.body, job.controller);
            if (closed || job.state === "cancelled") return;
            const result = await api("submit", {receipt: prepared.receipt}, job.controller);
            if (closed) return;
            job.undoReceipt = result.undo_receipt; job.state = "submitted";
            resolveSubmissionErrors(job);
          } catch (e) {
            if (closed || job.state === "cancelled") return;
            const temporary = !e.status || e.status >= 500 || [408, 429].includes(e.status) ||
              (e.status === 409 && e.message.startsWith("The database is busy."));
            const retry = temporary && !job.autoRetried && !job.undoRequested;
            job.state = retry ? "queued" : "failed";
            if (retry) {
              job.autoRetried = true;
              moveToSubmissionTail(job);
            }
            const recovery = retry ? "Queued at the end for one automatic retry." :
              "Result kept in this tab. Use Retry failed to submit it again.";
            job.errorMessage = "Submission for moca_oid=" + job.item.moca_oid + " failed. " + recovery + "\n" + e.message;
            job.errorExpiresAt = Date.now() + 20000;
            error(job.errorMessage, job);
          } finally {
            if (!closed) updateControls();
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
    job.undoRequested = true;
    try {
      if (job.state === "queued") job.state = "cancelled";
      if (job.state === "submitting") { status("Waiting for this submission before undoing it…"); await job.promise; }
      if (job.state === "submitted") await api("undo", {receipt: job.undoReceipt});
      if (closed) return;
      history.pop(); job.state = "undone"; job.undoReceipt = null; hidden.delete(key(job.item, job.lane));
      resolveSubmissionErrors(job);
      if (queueLane !== "all" && queueLane !== job.lane) { queueLane = job.lane; $("lane").value = job.lane; items = [job.item]; hasMore = false; }
      else if (!items.some((i) => key(i) === key(job.item))) items.push(job.item);
      // Undo can change pixels and adopted-type metadata for this object.
      for (const [fitKey, fit] of cache) {
        if (Number(fit.item.moca_oid) === Number(job.item.moca_oid)) cache.delete(fitKey);
      }
      await show(items.findIndex((i) => key(i) === key(job.item)));
      status("Last decision undone.");
    } catch (e) { if (!closed) error(e.message); }
    finally { job.undoRequested = false; busyUndo = false; if (!closed) updateControls(); }
  }
  function retryFailed() {
    if (!writable()) return;
    for (const job of jobs.filter(job => job.state === "failed")) {
      job.state = "queued";
      moveToSubmissionTail(job);
    }
    updateControls(); void drain();
  }
  function quit() {
    if (motionReview.pending()) { error("Wait for the motion submission to finish before quitting."); return; }
    const count = pendingCount() + failedCount();
    if (count && !confirm("Quit and discard " + count + " pending submissions? Requests already sent may still commit; check MOCAdb before reviewing them again.")) return;
    closed = true; motionReview.close(); clearTimeout(autoNextTimer); autoNextTimer = null;
    for (const job of jobs) if (job.state === "queued") job.state = "cancelled";
    for (const controller of controllers) controller.abort();
    for (const name of Object.keys(auth)) auth[name] = "";
    resetAnalysis(); history.length = 0; jobs.length = 0; items = []; current = null;
    generation++; hidden.clear(); Plotly.purge($("plot"));
    $("matches").replaceChildren(); $("stored").textContent = ""; $("preview-output").textContent = "";
    $("object-title").textContent = "Review session closed"; $("object-meta").textContent = "";
    $("position").textContent = ""; $("best-type").textContent = ""; $("fit-detail").textContent = "";
    error(""); status("Review data and in-memory credentials cleared. Credentials remain in the address bar; close the tab to hide them.");
    document.querySelectorAll("button,input,select,textarea").forEach((el) => el.disabled = true);
    $("submitting").textContent = "Session closed";
    updateCacheStatus();
    plotShown = false; updateUploadStatus();
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
  const datasetStorageKey = "spherex-review-datasets-v1";
  const motionDatasetName = "Good_Motion_Candidate_Spectra";
  const motionDataset = {
    "lane": "all", "review-sample": "all", "sublime3c-selection-pass": false, "sublime3c-priority-high": false,
    "sublime3c-psf-morphology": "all", "adopted-spt-source": "private", "adopted-spt-moca-pids": "",
    "queue-order": "snr_bin_spt", "cnn-priority-source": "combined", "spectral-cnn-probability": "",
    "batch-size": "100", "missing-vetting": "all", "vetting-classification": "good_candidate",
    "wiseview-score": "5", "no-wiseview-score": false, "sublime2-snr": "", "max-sublime2-snr": "",
    "cnn-probability": "", "galactic-latitude": "", "snr-wavelength-range": "all", "snr": "",
    "max-snr": "", "max-chi2": "", "sptn": "10", "current-fit-sptn": "", "current-fit-gap": "",
    "no-known": false, "exclude-duplicates": false, "oids": "", "replace": true,
  };
  // Update the existing Vetting preset once, preserving its other filters.
  if (window.__spherexNativeVetting === true) {
    const key = datasetStorageKey;
    const migration = key + ":all-s3c-snr-order-v1";
    try {
      if (!localStorage.getItem(migration)) {
        const presets = new Map(JSON.parse(localStorage.getItem(key) || "[]"));
        const preset = presets.get("ALL_S3C");
        if (preset?.["review-sample"] === "sublime3c") {
          presets.set("ALL_S3C", {...preset, "queue-order": "snr_bin_spt"});
          localStorage.setItem(key, JSON.stringify([...presets]));
          localStorage.setItem(migration, "1");
        }
      }
    } catch {
      // The reviewer remains usable if local storage is unavailable.
    }
  }
  updatePresetButtons = window.installReviewPresets(datasetStorageKey, [...queueFilterFields, "replace"], {
    initial: {[motionDatasetName]: motionDataset},
    canLoad: () => !$("load").disabled,
    newestFirst: true,
    apply(datasetName, preset) {
      $("replace").checked = preset.replace === true;
      if (!Object.hasOwn(preset, "vetting-classification")) $("vetting-classification").value = "";
      const sample = $("review-sample").value;
      cnnFilterSample = previousSample = sample;
      catalogCnnBySample.set(sample, $("cnn-probability").value);
      if (sample !== "public-ucd") {
        otherSampleVetting = $("missing-vetting").value;
        otherSampleSptSource = $("adopted-spt-source").value;
      }
      $("specid").value = "";
      updateControls();
      void loadQueue(false, false, datasetName);
    },
  });
  $("load").onclick = () => loadQueue(); $("more").onclick = () => loadQueue(true);
  $("specid").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); loadQueue(); }
  });
  for (const field of ["drop", "cap", "odds", "extreme"])
    $(field).addEventListener("input", updateCacheStatus);
  $("refit").onclick = () => { resetAnalysis(); show(index, true); };
  $("match-count").onchange = () => { if (current) render(current); };
  for (const name of ["first", "previous", "next", "last"]) $(name).onclick = () => navigate(name);
  $("undo").onclick = undoLast; $("report").onclick = openReport; $("wiseview").onclick = openWiseView;
  $("quit").onclick = quit; $("retry").onclick = retryFailed; $("preview").onclick = () => preview();
  $("save-type").onclick = () => enqueue("upsert_spt"); $("bad-pixels").onclick = () => enqueue("bad_pixels");
  $("write-enabled").onchange = () => {
    if ($("write-enabled").checked && !confirm("Enable database submissions? Quality labels update visual vetting and photometric/ignored flags. Good and candidate classes reactivate this lane's autotypes and spectra; rejected classes ignore both. New spectral types use the selected visibility and RLS. Undo is available within this tab."))
      $("write-enabled").checked = false;
    updateControls();
  };
  window.addEventListener("beforeunload", (event) => {
    if (!closed && (pendingCount() || failedCount() || motionReview.pending())) { event.preventDefault(); event.returnValue = ""; }
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
    $("specid").value = params.get("specid") || params.get("moca_specid") || "";
    if (params.has("batch_size")) $("batch-size").value = params.get("batch_size");
    if (params.has("min_snr")) $("snr").value = params.get("min_snr");
    if (params.has("min_sptn")) $("sptn").value = params.get("min_sptn");
    if (params.has("sublime3c_priority_high_only"))
      $("sublime3c-priority-high").checked = !["0", "false"].includes(params.get("sublime3c_priority_high_only"));
    if (params.has("sublime3c_selection_pass_only"))
      $("sublime3c-selection-pass").checked = !["0", "false"].includes(params.get("sublime3c_selection_pass_only"));
    $("current-fit-gap").value = params.has("min_current_fit_gap") ? params.get("min_current_fit_gap") : params.get("review_sample") === "sublime3c" ? "2" : "";
    $("current-fit-sptn").value = params.has("min_current_fit_sptn") ? params.get("min_current_fit_sptn") :
      params.get("review_sample") === "sublime3c" ? "10" : "";
    for (const [param, id] of Object.entries({sublime3c_psf_morphology: "sublime3c-psf-morphology", review_sample: "review-sample", queue_order: "queue-order", min_sublime2_snr: "sublime2-snr",
      min_cnn_probability: "cnn-probability", min_abs_galactic_latitude: "galactic-latitude",
      max_reduced_chi2: "max-chi2", snr_wavelength_range: "snr-wavelength-range",
      max_snr: "max-snr", max_sublime2_snr: "max-sublime2-snr",
      adopted_spt_moca_pids: "adopted-spt-moca-pids"})) {
      if (params.has(param)) $(id).value = params.get(param);
    }
    $("no-wiseview-score").checked = ["1", "true"].includes(params.get("no_wiseview_score"));
    if (params.has("exclude_duplicates")) $("exclude-duplicates").checked = !["0", "false"].includes(params.get("exclude_duplicates"));
    if (params.get("review_sample") === "public-ucd") {
      $("missing-vetting").value = "all";
      $("adopted-spt-source").value = "public";
    }
    if (["private", "public"].includes(params.get("adopted_spt_source")))
      $("adopted-spt-source").value = params.get("adopted_spt_source");
    previousSample = $("review-sample").value;
    if (location.pathname.endsWith("spherex-autotype")) $("missing-vetting").value = "all";
    if (params.has("missing_vetting")) $("missing-vetting").value = params.get("missing_vetting");
    if (params.has("min_wiseview_score")) $("wiseview-score").value = params.get("min_wiseview_score");
    if ($("review-sample").value === "sublime4") {
      sublime4SampleDefaults();
      if (params.has("max_reduced_chi2")) $("max-chi2").value = params.get("max_reduced_chi2");
    }
    updateControls();
    try {
      if (auth.host !== "mocadb.ca" || auth.port !== "3306") throw new Error("These tools connect only to mocadb.ca:3306.");
      context = await api("context");
      if ((context.queue_filter_version ?? 0) < 14 && !params.has("queue_order") &&
          $("queue-order").value === "gal_cnn_snr_bin_spt") {
        // Keep fresh loads usable if the static page is newer than the running worker.
        $("queue-order").value = "gal_cnn_spt_snr";
      }
      $("access").textContent = demo ? "Demo · read only" : context.can_write ? "Management · writes disabled until enabled" : "Collaborator · read only";
      for (const [label] of context.classifications)
        $("vetting-classification").add(new Option(label, label));
      const usable = new Set(["good", "good_candidate", "peculiar_ucd", "contaminated_ucd",
        "incomplete_but_promising", "good_plus_star", "good_reddened", "weird", "late_M"]);
      for (const [label, shortcut] of context.classifications) {
        const button = document.createElement("button");
        button.textContent = label.replaceAll("_", " ") + " [" + shortcut.toUpperCase() + "]";
        button.dataset.classification = label; button.className = usable.has(label) ? "usable" : "reject";
        button.onclick = () => enqueue("classify", label); $("classifications").append(button);
      }
      status("Ready. Choose a sample, then select Load spectrum / queue [Alt+L].");
      updateControls();
    } catch (e) {
      $("access").textContent = "Credentials required"; status("Open the original credential-bearing URL to begin.");
      error(e.message); updateControls();
    }
  }
  start();
})();
