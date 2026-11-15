/* Optional object-level motion review; independent of the spectral write queue. */
(() => {
  'use strict';
  window.SpherexMotionReview = {create({api, writable, base, demo}) {
    const $ = id => document.getElementById(id);
    let current = null, context = null, generation = 0, busy = false, closed = false;
    let undoState = null;
    const panel = $('motion-panel'), frame = $('motion-frame');
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
    function clear() {
      ++generation; current = context = null; panel.hidden = true;
      frame.removeAttribute('src'); frame.hidden = true;
      $('motion-classification').replaceChildren(new Option('No motion decision selected', ''));
      $('motion-comments').value = ''; $('motion-replace').checked = false;
      $('motion-stored').textContent = ''; $('motion-status').textContent = '';
      update();
    }
    function loadFrame() {
      frame.removeAttribute('src'); frame.hidden = true;
      if (!current || closed || !$('motion-autoload').checked) return;
      const {ra, dec} = current.object;
      if (!Number.isFinite(ra) || !Number.isFinite(dec)) {
        $('motion-status').textContent = 'No valid coordinates for WiseView.'; return;
      }
      if (demo) { $('motion-status').textContent = 'Demo: external cutouts are disabled.'; return; }
      const url = new URL('spherex-review-wiseview', base);
      url.hash = new URLSearchParams({ra, dec, size:75, band:3, speed:500, minbright:-50,
        maxbright:500, window:5, diff_window:1, linear:1, color:'', zoom:9, border:0,
        gaia:1, invert:1, maxdyr:1, scandir:0, neowise:0, diff:0,
        outer_epochs:1, unique_window:1, smooth_scan:0, shift:0, pmra:0, pmdec:0});
      frame.src = url.href; frame.hidden = false;
    }
    frame.addEventListener('load', () => {
      // Opaque frame: only public overlay settings, never credentials or IDs.
      frame.contentWindow?.postMessage({kind:'wise-overlays', crosshairs:true, properMotion:false}, '*');
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
    function show(data) {
      if (closed || same(data.object)) return;
      clear(); current = data; panel.hidden = false;
      $('motion-target').textContent = (data.object.designation || 'Object') + ' · OID ' + data.object.moca_oid;
      if (data.read_only) $('motion-stored').textContent = 'Read-only spectrum; motion submissions are disabled.';
      loadFrame(); void refreshContext(); update();
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
    $('motion-reload').onclick = () => { loadFrame(); void refreshContext(); };
    $('motion-classification').onchange = $('motion-replace').onchange = update;
    $('motion-autoload').onchange = loadFrame;
    document.addEventListener('keydown', event => {
      if (closed || event.repeat || !event.altKey || event.ctrlKey || event.metaKey ||
          ['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName) || event.target.isContentEditable) return;
      const id = {KeyM:'motion-save', KeyU:'motion-undo', KeyW:'motion-reload'}[event.code];
      if (id) {event.preventDefault(); $(id).click();}
    });
    return {show, clear, update, pending:() => busy, close() {closed = true; undoState = null; clear();}};
  }};
})();
