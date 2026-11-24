/* Keep the decoded GIFs for the next 50 targets without mounting WiseView. */
(() => {
  'use strict';
  window.LocalUnwisePreview = {
    create(base) {
      const entries = new Map();
      let upcoming = [], active = null, pending = 0;
      const valid = id => /^(?:moshpit-)?[1-9][0-9]{0,17}$/.test(String(id));
      function pump() {
        for (const id of upcoming) {
          if (pending >= 4) break;
          if (!entries.has(id)) get(id);
        }
      }
      function get(id) {
        if (!valid(id)) return Promise.resolve(null);
        id = String(id);
        const cached = entries.get(id);
        if (cached) return cached;
        pending++;
        const image = new Image();
        image.alt = 'Two stacked unWISE epochs in WiseView colors';
        image.className = 'local-unwise-animation';
        const result = new Promise(resolve => {
          image.onload = () => image.decode().then(() => resolve(image), () => resolve(null));
          image.onerror = () => resolve(null);
        }).finally(() => {
          pending--;
          pump();
        });
        entries.set(id, result);
        image.src = new URL('local-unwise/' + id + '.gif', base);
        return result;
      }
      function setUpcoming(id, candidates) {
        active = valid(id) ? String(id) : null;
        upcoming = [...new Set(candidates.filter(valid).map(String))].filter(id => id !== active).slice(0, 50);
        const keep = new Set([active, ...upcoming]);
        for (const id of entries.keys()) if (!keep.has(id)) entries.delete(id);
        pump();
      }
      return {
        get, setUpcoming,
        async forDisplay(id, refresh = false) {
          if (refresh) entries.delete(String(id));
          if (!entries.has(String(id))) return get(id);
          const image = await get(id);
          if (image || !valid(id)) return image;
          // The batch builder may have filled this slot since it was prefetched.
          entries.delete(String(id));
          return get(id);
        }
      };
    }
  };
})();
