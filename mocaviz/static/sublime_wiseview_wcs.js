// The sandboxed WiseView frame reports only its public WCS, layout and frame epochs.
(() => {
  const Original = window.WiseSwapper;
  if (typeof Original !== 'function' || window.parent === window) return;
  const frame = new URLSearchParams(location.search).get('frame');
  let swapper, previous;
  window.WiseSwapper = function (...args) {
    swapper = Reflect.construct(Original, args);
    return swapper;
  };
  window.WiseSwapper.prototype = Original.prototype;

  function report() {
    const canvas = document.querySelector('#daCanvas');
    if (!canvas || !swapper) return;
    const keys = ['CRVAL1','CRVAL2','CRPIX1','CRPIX2','NAXIS2'];
    if (!keys.every(key => Number.isFinite(swapper[key])) || !canvas.width || !canvas.height) return;
    const frameTimes = (swapper.window_mjds || []).filter(Array.isArray).map(times => {
      const valid = times.filter(t => Number.isFinite(t) && t > 35000 && t < 90000);
      return valid.length ? valid.reduce((a,b) => a+b,0)/valid.length : null;
    }).filter(Number.isFinite).sort((a,b) => a-b);
    const mid = Math.floor(frameTimes.length/2);
    const median = frameTimes.length ? (frameTimes[mid]+frameTimes[Math.floor((frameTimes.length-1)/2)])/2 : null;
    const rect = canvas.getBoundingClientRect();
    const message = {kind:'sublime-wiseview-wcs',frame,wcs:keys.map(key=>swapper[key]),
      bounds:[rect.left,rect.top,rect.width,rect.height],size:[canvas.width,canvas.height],
      epoch:median===null ? null : 2000+(median-51544.5)/365.25};
    const serialized = JSON.stringify(message);
    if (serialized === previous) return;
    previous = serialized;
    window.parent.postMessage(message,'*');
  }
  window.addEventListener('scroll',report,{passive:true,capture:true});
  window.addEventListener('resize',report,{passive:true});
  window.setInterval(report,250);
})();
