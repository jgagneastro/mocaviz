/* Public cutout readiness only; this frame has an opaque sandbox origin. */
(() => {
  'use strict';
  const Original = window.WiseSwapper;
  if (typeof Original !== 'function') return;
  const frame = new URLSearchParams(location.search).get('frame');
  let swapper;
  window.WiseSwapper = function (...args) {
    swapper = Reflect.construct(Original, args);
    // Preserve the native slider step and every other image setting.
    swapper.zoom_input.slider('option', 'max', 40);
    return swapper;
  };
  window.WiseSwapper.prototype = Original.prototype;
  const timer = setInterval(() => {
    const images = swapper?.images;
    if (!images?.length || !images.every(image => image.complete && image.naturalWidth > 0)) return;
    clearInterval(timer);
    if (window.parent !== window)
      window.parent.postMessage({kind:'spherex-motion-cutout', frame, state:'ready'}, '*');
  }, 250);
})();
