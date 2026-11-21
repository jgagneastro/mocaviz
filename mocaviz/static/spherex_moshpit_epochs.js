/* Only the local MOSHPIT watcher handles these native-image products. */
window.MoshpitEpochCharts = {create() {
  "use strict";
  const $ = id => document.getElementById(id);
  const pane = $("moshpit-epochs"), chart = $("epoch-chart"), dialog = $("epoch-dialog");
  const enlarge = $("epoch-enlarge"), message = $("epoch-status"), full = $("epoch-full");
  const local = ["http://127.0.0.1:8061", "http://localhost:8061"].includes(location.origin);
  let serial = 0, active = null, timer, request, objectURL;
  const picker = $("epoch-reference-picker"), choice = $("epoch-reference-choice");
  const refStatus = $("epoch-reference-status");
  let references, refRequest, refURL;
  function resetReference() {
    refRequest?.abort(); refRequest = null;
    if (refURL) URL.revokeObjectURL(refURL);
    refURL = null;
    picker.hidden = true; refStatus.textContent = "";
  }
  function post(path, body, signal) {
    return fetch("http://127.0.0.1:8967/" + path, {
      method:"POST", credentials:"omit", referrerPolicy:"no-referrer", cache:"no-store",
      headers:{"Content-Type":"application/json"}, body:JSON.stringify(body), signal
    });
  }
  function clear() {
    resetReference();
    serial++;
    active = null;
    clearTimeout(timer);
    request?.abort();
    if (dialog.open) dialog.close();
    pane.hidden = chart.hidden = enlarge.hidden = true;
    $("motion-images").classList.remove("has-epochs");
    chart.removeAttribute("src"); full.removeAttribute("src");
    if (objectURL) URL.revokeObjectURL(objectURL);
    objectURL = null;
    message.textContent = "";
  }
  async function load(gen) {
    if (!active || gen !== serial) return;
    const controller = request = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4500);
    let retry = 8000;
    try {
      const response = await post("chart", active, controller.signal);
      if (gen !== serial) return;
      if (response.status === 200 && response.headers.get("Content-Type") === "image/png") {
        const blob = await response.blob();
        if (gen !== serial) return;
        objectURL = URL.createObjectURL(blob);
        chart.src = objectURL;
        chart.hidden = enlarge.hidden = false;
        message.textContent = "";
        return;
      }
      if (response.status !== 202) throw new Error();
      const {state} = await response.json();
      if (gen !== serial) return;
      const status = {awaiting:"Waiting for the watcher to register this position.",
        queued:"Queued with priority for the displayed candidate.", building:"Building the W1 and W2 comparisons…",
        retry:"The watcher will retry this field."};
      message.textContent = status[state] || "Waiting for the local image watcher.";
      if (state === "awaiting" || state === "retry") retry = 20000;
    } catch {
      if (gen !== serial) return;
      message.textContent = "The local image watcher is unavailable. Reconnecting…";
      retry = 15000;
    } finally {clearTimeout(timeout);}
    if (gen === serial) timer = setTimeout(() => load(gen), retry);
  }
  function show(data) {
    clear();
    if (!local || data?.lane !== "moshpit") return;
    const obj = data.object, name = /^MOSHPIT ([1-9]\d*)$/.exec(obj.designation);
    if (!name || !Number.isSafeInteger(obj.candidate_id) || !Number.isFinite(obj.ra) || !Number.isFinite(obj.dec)) return;
    active = {id:obj.candidate_id, number:Number(name[1]), ra:obj.ra, dec:obj.dec};
    pane.hidden = false;
    $("motion-images").classList.add("has-epochs");
    chart.alt = obj.designation + ", native W1 and W2 late-minus-early images using five comparisons";
    $("epoch-full-title").textContent = obj.designation + " · unWISE epoch differences";
    message.textContent = "Checking the local chart cache…";
    void load(serial);
  }
  function expand() {
    if (objectURL && !dialog.open) {
      resetReference();
      $("epoch-full-title").textContent = "MOSHPIT " + active.number + " · unWISE epoch differences";
      full.src = objectURL; full.alt = chart.alt; dialog.showModal();
    }
  }
  async function referenceImage() {
    refRequest?.abort();
    const controller = refRequest = new AbortController();
    if (refURL) URL.revokeObjectURL(refURL);
    refURL = null; full.removeAttribute("src"); full.alt = "";
    refStatus.textContent = "Loading the reference image…";
    try {
      const index = Number(choice.value);
      const response = await post("references", {index}, controller.signal);
      if (response.status !== 200 || response.headers.get("Content-Type") !== "image/png") throw Error();
      const blob = await response.blob();
      if (refRequest !== controller) return;
      refURL = URL.createObjectURL(blob);
      full.alt = choice.selectedOptions[0].textContent + ", signed unWISE differences and catalog motion";
      full.src = refURL;
      refStatus.textContent = "";
    } catch {
      if (refRequest === controller) refStatus.textContent = "Could not load this reference. Select it again to retry.";
    }
  }
  async function openReferences() {
    if (!active || dialog.open) return;
    resetReference();
    full.removeAttribute("src"); full.alt = "";
    $("epoch-full-title").textContent = "Known Galactic-plane dwarfs";
    refStatus.textContent = "Loading the reference set…";
    dialog.showModal();
    const controller = refRequest = new AbortController();
    try {
      if (!references) {
        const response = await post("references", {}, controller.signal);
        if (response.status !== 200) throw Error();
        const items = await response.json();
        if (refRequest !== controller) return;
        references = items;
        choice.replaceChildren(...items.map(item => {
          const option = document.createElement("option");
          option.value = item.index;
          option.textContent = String(item.index).padStart(2, "0") + "  " + item.designation + " · " + item.spt;
          return option;
        }));
      }
      picker.hidden = false;
      choice.focus();
      await referenceImage();
    } catch {
      if (refRequest === controller) refStatus.textContent = "Could not load the reference set. Close and reopen to retry.";
    }
  }
  choice.onchange = referenceImage;
  $("epoch-references").onclick = openReferences;
  dialog.onclose = () => { if (!dialog.open) { resetReference(); full.removeAttribute("src"); } };
  enlarge.onclick = expand;
  $("epoch-close").onclick = () => dialog.close();
  document.addEventListener("keydown", event => {
    if (dialog.open) {
      event.stopImmediatePropagation();
      if (event.key === "Escape") { event.preventDefault(); dialog.close(); }
      return;
    }
    if (event.altKey && ["KeyI","KeyK"].includes(event.code) && !event.repeat && !pane.hidden &&
        !event.metaKey && !event.ctrlKey && !event.target.isContentEditable &&
        !["INPUT","TEXTAREA","SELECT"].includes(event.target.tagName)) {
      event.preventDefault(); event.stopImmediatePropagation();
      if (event.code === "KeyK") void openReferences(); else expand();
    }
  }, true);
  return {show,clear,local};
}};
