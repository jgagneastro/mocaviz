// Decimal calendar years for the dates actually provided by survey cutouts.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.SurveyEpochs = api;
})(typeof window === 'object' ? window : null, function () {
  'use strict';
  function decimalYear(text) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(text).trim());
    if (!match) return null;
    const year = Number(match[1]), month = Number(match[2]), day = Number(match[3]);
    const date = new Date(Date.UTC(year, month - 1, day));
    if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
    const start = Date.UTC(year, 0, 1), end = Date.UTC(year + 1, 0, 1);
    return (year + (date.getTime() - start) / (end - start)).toFixed(3);
  }
  function formatTitle(title) {
    return String(title || '').replace(/\bepoch\s+(.+?)(?=\s+\(|$)/i, function (whole, epoch) {
      const dates = epoch.split('/').map(decimalYear);
      if (dates.length && dates.every(value => value !== null)) return 'epoch ' + dates.join(' / ');
      const period = /^(\d{4})-(\d{4})\s+coadd$/i.exec(epoch.trim());
      if (period) return `survey span ${period[1]}–${period[2]} (coadd; image epoch unavailable)`;
      if (/^(?:coadd|stack coadd|per-exposure|calibrated exposures|unknown)$/i.test(epoch.trim()))
        return `epoch unavailable (${epoch.trim()})`;
      return whole;
    });
  }
  function installNativePs1Label(doc) {
    const container = doc.querySelector('#pawnstars');
    if (!container || container.__epochLabelObserver) return;
    const watched = new WeakSet();
    function update() {
      const img = container.querySelector('img');
      let label = container.querySelector('[data-ps1-epoch-label]');
      const native = img && img.dataset.wiseviewFallbackCutout !== '1';
      if (native && !watched.has(img)) {
        watched.add(img);
        img.addEventListener('load', update, {once:true});
        img.addEventListener('error', update, {once:true});
      }
      if (!native || !img.complete || img.naturalWidth <= 20 || img.naturalHeight <= 20) {
        if (label) label.remove();
        return;
      }
      if (!label) {
        label = doc.createElement('div');
        label.dataset.ps1EpochLabel = '1';
        label.textContent = 'PS1 native stack · image epoch unavailable';
        Object.assign(label.style, {position:'absolute', top:'0', left:'0', zIndex:'10',
          background:'rgba(0,0,0,.8)', color:'white', font:'12px sans-serif', padding:'3px 4px', pointerEvents:'none'});
        if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
        container.appendChild(label);
      }
    }
    container.__epochLabelObserver = new MutationObserver(update);
    container.__epochLabelObserver.observe(container, {childList:true, subtree:true});
    update();
  }
  return {decimalYear, formatTitle, installNativePs1Label};
});
