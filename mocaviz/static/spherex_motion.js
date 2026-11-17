/* Optional object-level motion review; independent of the spectral write queue. */
(() => {
  'use strict';
  const MAX_TARGETS = 50, MAX_BYTES = 1_000_000_000, FRAME_OVERHEAD = 16 * 1024 ** 2;
  const LOAD_TIMEOUT = 30000;
  const key = object => object.moca_oid + ":" + object.moca_specid;
  const hasCoordinates = object => Number.isFinite(object?.ra) && Number.isFinite(object?.dec);
  window.SpherexMotionReview = {create({api, writable, base, demo, preload = false}) {
    const $ = id => document.getElementById(id);
    let current = null, context = null, generation = 0, busy = false, closed = false;
    let undoState = null, loadTimer = null, frameSerial = 0, active = null;
    let upcoming = [], resolveObject, resolving = null, preloading = null, budgetReached = false;
    const cache = new Map(), skipped = new Set();
    const panel = $('motion-panel'), template = $('motion-frame');
    const same = object => current && Number(current.object.moca_oid) === Number(object.moca_oid) &&
      Number(current.object.moca_specid) === Number(object.moca_specid);
    function update() {
      const ready = !!context && !busy && !closed && writable() && !current?.read_only;
      $('motion-save').disabled = !ready || !$('motion-classification').value ||
        (!!context?.review && !$('motion-replace').checked);
      $('motion-classification').disabled = $('motion-comments').disabled = !ready;
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
      clearTimeout(loadTimer);
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
      if (background) url.searchParams.set('preload', '1');
      url.hash = new URLSearchParams({ra, dec, size:30, band:3, speed:500, minbright:-50,
        maxbright:500, window:5, diff_window:1, linear:1, color:'', zoom:40, border:0,
        gaia:1, invert:1, maxdyr:1, scandir:0, neowise:0, diff:0,
        outer_epochs:1, unique_window:1, smooth_scan:0, shift:0, pmra:0, pmdec:0});
      node.src = url.href;
      panel.append(node);
      return entry;
    }
    function resume(entry) {
      entry.node.contentWindow?.postMessage({kind:'spherex-motion-activate', frame:entry.token}, '*');
    }
    function loadFrame(attempt = 0, refresh = false) {
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
      if (!preload || closed || !active?.ready || preloading || resolving || budgetReached ||
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
      // The opaque frame sends no credentials, IDs or classification data.
      if (closed || !entry || event.origin !== 'null' || message.kind !== 'spherex-motion-cutout' ||
          message.state !== 'ready' || entry.ready) return;
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
      if (!current || current.read_only || closed) return;
      const gen = generation, item = current;
      context = null; update();
      $('motion-stored').textContent = 'Loading existing motion review…';
      try {
        const result = await api('motion-context', {lane:item.lane,
          moca_oid:item.object.moca_oid, moca_specid:item.object.moca_specid});
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
    function show(data, next = [], lookup) {
      if (closed || same(data.object)) return;
      if (current) clear([data.object, ...next]);
      current = data; upcoming = next; resolveObject = lookup; panel.hidden = false;
      $('motion-target').textContent = (data.object.designation || 'Object') + ' · OID ' + data.object.moca_oid;
      if (data.read_only) $('motion-stored').textContent = 'Read-only spectrum; motion submissions are disabled.';
      if (cache.has(key(data.object))) loadFrame();
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
    $('motion-save').onclick = save; $('motion-undo').onclick = undo;
    $('motion-reload').onclick = () => { loadFrame(0, true); void refreshContext(); };
    $('motion-classification').onchange = $('motion-replace').onchange = update;
    $('motion-autoload').onchange = () => {
      if (!$('motion-autoload').checked) {
        for (const entry of cache.values()) discard(entry);
        resolving = null; skipped.clear(); budgetReached = false;
      }
      loadFrame();
    };
    document.addEventListener('keydown', event => {
      if (closed || event.repeat || !event.altKey || event.ctrlKey || event.metaKey ||
          ['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName) || event.target.isContentEditable) return;
      const id = {KeyM:'motion-save', KeyU:'motion-undo', KeyW:'motion-reload'}[event.code];
      if (id) {event.preventDefault(); $(id).click();}
    });
    return {show, clear, update, pending:() => busy, close() {closed = true; undoState = null; clear();}};
  }};
})();
