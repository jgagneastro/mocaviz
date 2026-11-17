/* Public cutout readiness only; this frame has an opaque sandbox origin. */
(() => {
  'use strict';
  const Original = window.WiseSwapper;
  if (typeof Original !== 'function') return;
  const params = new URLSearchParams(location.search);
  const frame = params.get('frame');
  let background = params.get('preload') === '1', parked = false, swapper;
  window.WiseSwapper = function (...args) {
    swapper = Reflect.construct(Original, args);
    // Preserve the native slider step and every other image setting.
    swapper.zoom_input.slider('option', 'max', 40);
    return swapper;
  };
  window.WiseSwapper.prototype = Original.prototype;
  window.addEventListener('message', event => {
    if (event.source !== window.parent || event.data?.kind !== 'spherex-motion-activate' ||
        event.data.frame !== frame) return;
    background = false;
    if (!parked) return;
    parked = false;
    swapper.updateSpeed();
  });
  const timer = setInterval(async () => {
    const images = swapper?.images;
    if (!images?.length || !images.every(image => image.complete && image.naturalWidth > 0)) return;
    clearInterval(timer);
    try {
      await Promise.all(images.map(image => image.decode()));
    } catch {
      return; // A broken image should use the parent panel's timeout/retry.
    }
    if (swapper.images !== images) return;
    if (background) {
      // The first frame is ready to paint. Avoid animating dozens of hidden panels.
      clearInterval(swapper.interval);
      swapper.frame();
      parked = true;
    }
    const areas = images.map(image => image.naturalWidth * image.naturalHeight);
    const maxArea = Math.max(...areas);
    const overlayArea = maxArea * (swapper.overlay_scale || 1) ** 2;
    // Budget two pixel buffers per image and canvas. Gaia overlays can finish
    // later, so reserve their full per-epoch projection before admitting the frame.
    const pixelBytes = 8 * (areas.reduce((sum, area) => sum + area, 0) +
      maxArea + overlayArea * (images.length + 3));
    if (window.parent !== window)
      window.parent.postMessage({kind:'spherex-motion-cutout', frame, state:'ready', pixelBytes}, '*');
  }, 250);
})();
