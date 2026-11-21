/* Cutout readiness and keyboard events from the opaque WiseView frame. */
(() => {
  'use strict';
  const Original = window.WiseSwapper;
  if (typeof Original !== 'function') return;
  const params = new URLSearchParams(location.search);
  const frame = params.get('frame');
  if (params.get('comparison') === '1') {
    // The original fixed 280px sidebar would push the cutout off the side of its narrow iframe.
    document.addEventListener('DOMContentLoaded', () => {
      const controls = document.getElementById('nav-left');
      if (!controls) return;
      const options = document.createElement('details'), summary = document.createElement('summary');
      options.id = 'wiseview-options';
      summary.textContent = 'WiseView settings and links';
      controls.before(options);
      options.append(summary, controls);
      const style = document.createElement('style');
      style.textContent = `
        #wiseview-options {font:14px system-ui;color:white;background:#383838;}
        #wiseview-options summary {cursor:pointer;padding:6px 9px;}
        #wiseview-options #nav-left {position:static;width:min(100%,360px);height:auto;}
        #wiseview-options #tabs {height:30px;}
        #epoch-legend {float:none;margin:0;padding:0 6px;width:auto;height:auto;writing-mode:horizontal-tb;font-size:12px;}
        #image-field {float:none;margin:0;padding:0;}
        #image-field #verValue {font:600 17px system-ui;padding:2px 6px;}
        #image-field canvas, #pawnstars img {max-width:calc(100% - 6px);height:auto !important;}
      `;
      document.head.append(style);
    }, {once:true});
  }
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
  window.addEventListener('keydown', event => {
    if (background || window.parent === window || event.defaultPrevented || event.repeat || event.isComposing ||
        event.altKey || event.ctrlKey || event.metaKey ||
        ['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName) || event.target.isContentEditable ||
        (event.key !== '*' && event.code !== 'NumpadMultiply')) return;
    event.preventDefault();
    window.parent.postMessage({kind:'spherex-motion-score-six', frame}, '*');
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
