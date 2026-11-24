/* Optional object-level motion review; independent of the spectral write queue. */
(() => {
  'use strict';
  const MAX_TARGETS = 50, MAX_BYTES = 1_000_000_000, FRAME_OVERHEAD = 16 * 1024 ** 2;
  const LOAD_TIMEOUT = 30000;
  const key = object => object.candidate_id != null ? 'moshpit:' + object.candidate_id : object.moca_oid + ':' + object.moca_specid;
  const previewKey = object => object?.moca_oid ?? (object?.candidate_id ? 'moshpit-' + object.candidate_id : null);
  const hasCoordinates = object => Number.isFinite(object?.ra) && Number.isFinite(object?.dec);
  window.SpherexMotionReview = {create({api, writable, base, demo, preload = false}) {
    const $ = id => document.getElementById(id);
    let current = null, context = null, generation = 0, busy = false, closed = false;
    let undoState = null, loadTimer = null, frameSerial = 0, active = null;
    let upcoming = [], resolveObject, resolving = null, preloading = null, budgetReached = false;
    const cache = new Map(), skipped = new Set();
    const local = ['localhost', '127.0.0.1'].includes(new URL(base).hostname) ? window.LocalUnwisePreview?.create(base) : null;
    let useLocal = false, forceOnline = false, localImage = null, imageRequest = 0;
    const panel = $('motion-panel'), template = $('motion-frame');
    const epochs = window.MoshpitEpochCharts?.create();
    const classification = $('motion-classification'), scoreSix = $('motion-score-six');
    const sixChoice = () => context?.choices?.find(choice => choice.score === 6);
    const same = object => current && key(current.object) === key(object) && current.object.moca_oid === object.moca_oid;
    function update() {
      const ready = !!context && !busy && !closed && writable() && !current?.read_only;
      $('motion-save').disabled = !ready || !$('motion-classification').value ||
        (!!context?.review && !$('motion-replace').checked);
      classification.disabled = $('motion-comments').disabled = !ready;
      scoreSix.disabled = !ready || !sixChoice();
      $('motion-replace').disabled = !ready || !context?.review;
      $('motion-undo').disabled = !undoState || busy || closed || !writable();
      $('motion-reload').disabled = !current || busy || closed;
      $('motion-undo').textContent = 'Undo motion' + (undoState ? ' for OID ' + undoState.object.moca_oid : '') + ' [Alt+U]';
    }
    function discard(entry) {
      if (!entry) return;
      clearTimeout(entry.watchdog);
      if (cache.get(entry.key) === entry) cache.delete(entry.key);
      if (entry === preloading) preloading = null;
      entry.node.remove();
      if (entry === active) {
        active = null;
        template.id = 'motion-frame';
      }
    }
    function clear(keep = []) {
      ++generation;
      epochs?.clear();
      clearTimeout(loadTimer);
      ++imageRequest;
      localImage?.remove();
      localImage = null; useLocal = false; forceOnline = false;
      if (!keep.length) local?.setUpcoming(null, []);
      const button = $('motion-use-wiseview');
      if (button) button.hidden = true;
      discard(active);
      const keys = new Set(keep.map(key));
      // An uncached jump owns the next request. A cached jump can keep its
      // single in-flight successor, as long as it still belongs to the queue.
      if (!keep.length || !cache.has(key(keep[0]))) discard(preloading);
      for (const entry of cache.values()) if (!keys.has(entry.key)) discard(entry);
      for (const id of skipped) if (!keys.has(id)) skipped.delete(id);
      upcoming = []; resolveObject = resolving = null; budgetReached = false;
      current = context = null; panel.hidden = true;
      $('motion-classification').replaceChildren(new Option('No motion decision selected', ''));
      $('motion-comments').value = ''; $('motion-replace').checked = false;
      $('motion-stored').textContent = ''; $('motion-status').textContent = '';
      update();
    }
    function mount(object, background = false) {
      const node = template.cloneNode(false), token = 'motion-' + (++frameSerial);
      node.removeAttribute('id');
      const entry = {node, token, key:key(object), object, ready:false, bytes:FRAME_OVERHEAD};
      node.addEventListener('load', () => {
        node.contentWindow?.postMessage({kind:'wise-overlays', crosshairs:true, properMotion:false}, '*');
        if (entry === active) resume(entry);
      });
      const {ra, dec} = object;
      const url = new URL('spherex-review-wiseview', base);
      url.searchParams.set('frame', token);
      if (object.candidate_id != null && epochs?.local) url.searchParams.set('comparison', '1');
      if (background) url.searchParams.set('preload', '1');
      url.hash = new URLSearchParams({ra, dec, size:30, band:3, speed:500, minbright:-50,
        maxbright:500, window:5, diff_window:1, linear:1, color:'', zoom:40, border:0,
        gaia:1, invert:1, maxdyr:1, scandir:0, neowise:0, diff:0,
        outer_epochs:1, unique_window:1, smooth_scan:0, shift:0, pmra:0, pmdec:0});
      node.src = url.href;
      $('wiseview-cutout').append(node);
      return entry;
    }
    function resume(entry) {
      entry.node.contentWindow?.postMessage({kind:'spherex-motion-activate', frame:entry.token}, '*');
    }
    async function loadFrame(attempt = 0, refresh = false) {
      const request = ++imageRequest;
      clearTimeout(loadTimer);
      localImage?.remove();
      localImage = null;
      if (useLocal && !forceOnline && current && $('motion-autoload').checked) {
        discard(active);
        $('motion-status').textContent = 'Loading local unWISE animation…';
        const object = current.object;
        let image = await local.forDisplay(previewKey(object), refresh);
        if (!image && object.moca_oid && object.candidate_id && request === imageRequest)
          image = await local.forDisplay('moshpit-' + object.candidate_id, refresh);
        if (request !== imageRequest || closed) return;
        if (image) {
          localImage = image;
          $('wiseview-cutout').append(image);
          $('motion-use-wiseview').hidden = false;
          $('motion-use-wiseview').textContent = 'Use WiseView [Alt+V]';
          $('motion-status').textContent = 'Local unWISE animation · 50″ field · archive coadds';
          return;
        }
      }
      loadOnlineFrame(attempt, refresh);
    }
    function loadOnlineFrame(attempt, refresh) {
      clearTimeout(loadTimer);
      discard(active);
      if (!current || closed || !$('motion-autoload').checked) {
        $('motion-status').textContent = ''; return;
      }
      const object = current.object;
      if (!hasCoordinates(object)) {
        $('motion-status').textContent = 'No valid coordinates for WiseView.'; return;
      }
      if (demo) { $('motion-status').textContent = 'Demo: external cutouts are disabled.'; return; }
      let entry = cache.get(key(object));
      if (entry && (refresh || entry.object.ra !== object.ra || entry.object.dec !== object.dec)) {
        discard(entry); entry = null;
      }
      if (entry) {
        cache.delete(entry.key);
        if (entry === preloading) preloading = null;
      } else {
        discard(preloading);
        entry = mount(object);
      }
      active = entry;
      template.removeAttribute('id');
      entry.node.id = 'motion-frame'; entry.node.hidden = false;
      resume(entry);
      if (entry.ready) {
        $('motion-status').textContent = 'WiseView loaded.';
        void preloadNext();
        return;
      }
      $('motion-status').textContent = attempt ? 'Retrying WiseView cutout…' : 'Loading WiseView cutout…';
      clearTimeout(entry.watchdog);
      entry.watchdog = setTimeout(() => {
        if (entry !== active || !current || closed) return;
        if (attempt === 0) loadFrame(1);
        else $('motion-status').textContent = 'WiseView is taking longer than expected. Use Reload motion & cutout [Alt+W] to retry.';
      }, LOAD_TIMEOUT);
    }
    function scheduleFrame() {
      $('motion-status').textContent = $('motion-autoload').checked ? 'Waiting for target navigation to settle…' : '';
      loadTimer = setTimeout(() => loadFrame(), 300);
    }
    function cachedBytes() {
      return [...cache.values()].reduce((bytes, entry) => bytes + entry.bytes, 0);
    }
    async function preloadNext() {
      if (!preload || useLocal || closed || !active?.ready || preloading || resolving || budgetReached ||
          cache.size >= MAX_TARGETS || cachedBytes() + FRAME_OVERHEAD > MAX_BYTES) return;
      const candidate = upcoming.find(item => {
        const id = key(item);
        return id !== active.key && !cache.has(id) && !skipped.has(id);
      });
      if (!candidate) return;
      const request = resolving = {};
      let object;
      try {
        object = hasCoordinates(candidate) ? candidate : await resolveObject(candidate);
      } catch {
        // The fit or coordinate lookup failed. Let the user retry on navigation.
      }
      if (resolving !== request) return;
      resolving = null;
      if (!active?.ready) return;
      if (!hasCoordinates(object) || key(object) !== key(candidate)) {
        skipped.add(key(candidate));
        void preloadNext();
        return;
      }
      const entry = preloading = mount(object, true);
      cache.set(entry.key, entry);
      entry.watchdog = setTimeout(() => {
        discard(entry);
        skipped.add(entry.key);
        void preloadNext();
      }, LOAD_TIMEOUT);
    }
    window.addEventListener('message', event => {
      const message = event.data;
      const entry = [active, preloading].find(frame => frame && event.source === frame.node.contentWindow &&
        message?.frame === frame.token);
      // Accept shortcuts only from the active opaque iframe. This selects a draft.
      if (closed || !entry || event.origin !== 'null') return;
      if (message.kind === 'spherex-motion-score-six') {
        if (entry === active) scoreSix.click();
        return;
      }
      if (message.kind === 'wiseview-cutout-failed') {
        clearTimeout(entry.watchdog);
        if (entry === active) $('motion-status').textContent = 'WiseView could not load this animation. Use Reload motion & cutout [Alt+W] to retry.';
        else {
          discard(entry);
          skipped.add(entry.key);
          void preloadNext();
        }
        return;
      }
      if (message.kind !== 'spherex-motion-cutout' || message.state !== 'ready' || entry.ready) return;
      clearTimeout(entry.watchdog);
      entry.ready = true;
      if (entry === active) {
        $('motion-status').textContent = 'WiseView loaded.';
      } else {
        preloading = null;
        if (!Number.isSafeInteger(message.pixelBytes) || message.pixelBytes <= 0) {
          discard(entry);
          skipped.add(entry.key);
        } else {
          // Include decoded frames, projected overlay buffers, and per-frame
          // browser overhead. WebKit doesn't expose per-iframe resident memory.
          entry.bytes += message.pixelBytes;
          if (cachedBytes() > MAX_BYTES) {
            discard(entry);
            budgetReached = true;
          }
        }
      }
      void preloadNext();
    });
    async function refreshContext() {
      if (!current || current.read_only || current.object.moca_oid == null || closed) return;
      const gen = generation, item = current;
      context = null; update();
      $('motion-stored').textContent = 'Loading existing motion review…';
      try {
        const result = await api('motion-context', {lane:item.lane,
          moca_oid:item.object.moca_oid, moca_specid:item.object.moca_specid, candidate_id:item.object.candidate_id});
        if (gen !== generation || closed) return;
        if (result.motion_policy_version !== 1 || !same(result.object))
          throw new Error('Motion response does not match this spectrum. Reload the reviewer.');
        context = result;
        const options = [new Option('No motion decision selected', '')];
        for (const choice of result.choices) options.push(new Option(choice.score + ' · ' + choice.label, choice.key));
        $('motion-classification').replaceChildren(...options);
        const review = result.review;
        $('motion-stored').textContent = review ?
          'Stored motion: ' + review.classification_integer + ' · ' + review.classification +
          (review.reviewer ? ' · ' + review.reviewer : '') : 'No motion review stored.';
        $('motion-replace').checked = false;
        $('motion-comments').value = review?.comments || '';
      } catch (error) {
        if (gen === generation && !closed) $('motion-stored').textContent = 'Motion review unavailable: ' + error.message;
      }
      update();
    }
    async function preloadLocal() {
      if (!useLocal || !$('motion-autoload').checked) return;
      const gen = generation, id = previewKey(current.object);
      const ids = upcoming.map(previewKey).filter(Boolean).slice(0, 50);
      try {
        const response = await fetch(new URL('local-unwise/available', base), {
          method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids})
        });
        if (!response.ok) return;
        const data = await response.json();
        if (gen === generation && $('motion-autoload').checked) local.setUpcoming(id, data.ids);
      } catch {
        // The current target still uses the normal online fallback.
      }
    }
    function show(data, next = [], lookup) {
      if (closed || same(data.object)) return;
      if (current) clear([data.object, ...next]);
      current = data; upcoming = next; resolveObject = lookup; panel.hidden = false;
      epochs?.show(data);
      $('motion-target').textContent = (data.object.designation || 'Object') + (data.object.moca_oid == null ? ' · awaiting OID' : ' · OID ' + data.object.moca_oid);
      if (data.object.moca_oid == null) $('motion-stored').textContent = 'An OID is required to save an object-level motion score.';
      else if (data.read_only) $('motion-stored').textContent = 'Read-only spectrum; motion submissions are disabled.';
      useLocal = !!local && !demo && previewKey(data.object) != null;
      if (useLocal && $('motion-autoload').checked) {
        void loadFrame();
        void preloadLocal();
      } else if (cache.has(key(data.object))) loadFrame();
      else scheduleFrame();
      void refreshContext(); update();
    }
    async function save() {
      update(); if ($('motion-save').disabled) return;
      // Immutable target: advancing the spectral queue cannot redirect this write.
      const object = {...context.object};
      const body = {...object, revision:context.revision, classification:$('motion-classification').value,
        comments:$('motion-comments').value, allow_replace:$('motion-replace').checked};
      busy = true; update();
      $('motion-last-action').textContent = 'Saving motion for OID ' + object.moca_oid + '…';
      try {
        const preview = await api('motion-preview', body);
        if (closed || !writable()) throw new Error('Submissions disabled before motion was saved.');
        const saved = await api('motion-submit', {receipt:preview.receipt});
        undoState = {receipt:saved.undo_receipt, object};
        $('motion-last-action').textContent = 'Saved motion ' + saved.review.classification_integer +
          ' for OID ' + object.moca_oid + '.';
        if (same(object)) await refreshContext();
      } catch (error) {
        $('motion-last-action').textContent = 'Motion save for OID ' + object.moca_oid + ': ' + error.message +
          ' Reload motion to check the stored result before retrying.';
        if (same(object)) context = null;
      } finally { busy = false; update(); }
    }
    async function undo() {
      update(); if ($('motion-undo').disabled) return;
      busy = true; update(); const item = undoState;
      try {
        await api('motion-undo', {receipt:item.receipt}); undoState = null;
        $('motion-last-action').textContent = 'Undid motion review for OID ' + item.object.moca_oid + '.';
        if (same(item.object)) await refreshContext();
      } catch (error) { $('motion-last-action').textContent = 'Motion undo: ' + error.message; }
      finally { busy = false; update(); }
    }
    scoreSix.onclick = () => {
      classification.value = sixChoice().key;
      update();
    };
    $('motion-save').onclick = save; $('motion-undo').onclick = undo;
    $('motion-reload').onclick = () => { if (current) epochs?.show(current); loadFrame(0, true); void refreshContext(); };
    const wiseviewButton = $('motion-use-wiseview');
    if (wiseviewButton) wiseviewButton.onclick = () => {
      if (!current || !useLocal || !$('motion-autoload').checked) return;
      forceOnline = !forceOnline;
      wiseviewButton.textContent = forceOnline ? 'Use local animation [Alt+V]' : 'Use WiseView [Alt+V]';
      void loadFrame();
    };
    $('motion-classification').onchange = $('motion-replace').onchange = update;
    $('motion-autoload').onchange = () => {
      if (!$('motion-autoload').checked) {
        for (const entry of cache.values()) discard(entry);
        resolving = null; skipped.clear(); budgetReached = false;
      }
      if (useLocal && $('motion-autoload').checked) void preloadLocal();
      else if (useLocal) local.setUpcoming(null, []);
      if (wiseviewButton && !$('motion-autoload').checked) wiseviewButton.hidden = true;
      loadFrame();
    };
    document.addEventListener('keydown', event => {
      if (closed || event.defaultPrevented || event.repeat || event.isComposing || event.ctrlKey || event.metaKey ||
          ['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName) || event.target.isContentEditable) return;
      if (!event.altKey) {
        if ((event.key === '*' || event.code === 'NumpadMultiply') && !scoreSix.disabled) {
          event.preventDefault();
          scoreSix.click();
        }
        return;
      }
      const id = {KeyM:'motion-save', KeyU:'motion-undo', KeyW:'motion-reload', KeyV:'motion-use-wiseview'}[event.code];
      const button = id && $(id);
      if (button && !button.hidden) {event.preventDefault(); button.click();}
    });
    return {show, clear, update, pending:() => busy, close() {closed = true; undoState = null; clear();}};
  }};
})();
