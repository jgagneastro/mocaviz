// Mark the actual catalog coordinate, at its measured epoch, on WiseView's WCS.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.NearbyMarkers = api;
})(typeof window === 'object' ? window : null, function () {
  'use strict';
  function position(swapper, canvas, item) {
    const ra = item.ra_deg, dec = item.dec_deg;
    if (ra == null || dec == null || !Number.isFinite(Number(ra)) || !Number.isFinite(Number(dec)) ||
        !swapper || typeof swapper.__world_to_pix !== 'function' ||
        !Number.isFinite(swapper.CRVAL1) || !Number.isFinite(swapper.CRVAL2) ||
        !Number.isFinite(swapper.CRPIX1) || !Number.isFinite(swapper.CRPIX2) ||
        !Number.isFinite(swapper.NAXIS2) || !canvas.width || !canvas.height ||
        !canvas.offsetParent || !canvas.clientWidth || !canvas.clientHeight) return null;
    // The metadata may arrive before the cutout replaces the placeholder canvas.
    if ((Number.isFinite(swapper.NAXIS1) && swapper.NAXIS1 !== canvas.width) ||
        swapper.NAXIS2 !== canvas.height) return null;
    const pixel = swapper.__world_to_pix(Number(ra), Number(dec));
    if (!pixel || !Number.isFinite(pixel.px) || !Number.isFinite(pixel.py)) return null;
    const outside = pixel.px < 0 || pixel.py < 0 || pixel.px > canvas.width || pixel.py > canvas.height;
    // Share the canvas's layout coordinate system, as the target crosshairs do.
    // Viewport rectangles can already include Safari's iframe/page zoom.
    const x = pixel.px / canvas.width * canvas.clientWidth;
    const y = pixel.py / canvas.height * canvas.clientHeight;
    return {left: canvas.offsetLeft + canvas.clientLeft + x,
      top: canvas.offsetTop + canvas.clientTop + y, outside,
      rightHalf: x > canvas.clientWidth / 2, bottomHalf: y > canvas.clientHeight / 2};
  }
  function label(item, outside) {
    const epoch = item.position_epoch_yr;
    const year = epoch != null && Number.isFinite(Number(epoch)) ? Number(epoch).toFixed(2) : 'unknown';
    return `OID ${item.moca_oid} · epoch ${year}${outside ? ' · outside image' : ''}`;
  }
  function install(items) {
    if (!Array.isArray(items) || typeof window.WiseSwapper !== 'function') return;
    const Original = window.WiseSwapper;
    window.WiseSwapper = function (...args) {
      const instance = Reflect.construct(Original, args);
      window.__nearbyMarkerSwapper = instance;
      return instance;
    };
    window.WiseSwapper.prototype = Original.prototype;
    let markers=[];
    function setItems(items) {
      for(const {marker} of markers)marker.remove();
      markers=items.filter(item=>item && Number.isSafeInteger(Number(item.moca_oid)) && Number(item.moca_oid)>0 &&
        item.ra_deg!=null && item.dec_deg!=null && Number.isFinite(Number(item.ra_deg)) && Number.isFinite(Number(item.dec_deg)))
        .slice(0,256).map(item => {
          const marker = document.createElement('div');
          marker.style.cssText = 'position:absolute;display:none;pointer-events:none;z-index:2147483646;width:0;height:0;color:#ff3333;font:bold 12px sans-serif';
          const symbol = document.createElement('div');
          symbol.style.cssText = 'position:absolute;left:-7px;top:-7px;width:12px;height:12px;border:2px solid #ff3333;border-radius:50%;box-shadow:0 0 2px black';
          const text = document.createElement('div');
          text.style.cssText = 'position:absolute;white-space:nowrap;background:rgba(0,0,0,.8);padding:2px 4px;text-shadow:0 0 2px black';
          marker.append(symbol, text); document.documentElement.appendChild(marker);
          return {item, marker, text, symbol};
        });
    }
    setItems(items);
    // Parent settings arrive on load, including for background-preloaded frames.
    let lastVisibility=null,showNearbyMarkers=false,includeSublimeNeighbors=false;
    window.addEventListener('message', event => {
      if(event.source!==window.parent)return;
      if(event.data?.kind==='nearby-marker-items' && Array.isArray(event.data.items)){
        setItems(event.data.items);
        draw();
        return;
      }
      if(event.data?.kind!=='wise-overlays' || typeof event.data.nearbyMarkers!=='boolean')return;
      showNearbyMarkers=event.data.nearbyMarkers;
      if(typeof event.data.includeSublimeNeighbors==='boolean')includeSublimeNeighbors=event.data.includeSublimeNeighbors;
      draw();
    });
    function draw() {
      const canvas = document.querySelector('#daCanvas'), visibility=[];
      for (const {item, marker, text, symbol} of markers) {
        if(!includeSublimeNeighbors && /^SUBLIME/i.test(String(item.designation||''))){marker.style.display='none';continue;}
        const p = canvas && position(window.__nearbyMarkerSwapper, canvas, item);
        if (p) visibility.push({moca_oid:Number(item.moca_oid),outside:p.outside});
        if (!showNearbyMarkers || !p || p.outside) { marker.style.display = 'none'; continue; }
        if(marker.parentNode!==canvas.offsetParent)canvas.offsetParent.appendChild(marker);
        marker.style.display = 'block'; marker.style.left = `${p.left}px`; marker.style.top = `${p.top}px`;
        text.textContent = label(item, p.outside);
        text.style.left = p.rightHalf ? 'auto' : '10px'; text.style.right = p.rightHalf ? '10px' : 'auto';
        text.style.top = p.bottomHalf ? 'auto' : '10px'; text.style.bottom = p.bottomHalf ? '10px' : 'auto';
      }
      const signature=JSON.stringify(visibility);
      if(signature!==lastVisibility){
        lastVisibility=signature;
        window.parent.postMessage({kind:'nearby-marker-visibility',items:visibility},'*');
      }
    }
    window.addEventListener('resize', draw, {passive:true});
    window.addEventListener('scroll', draw, {passive:true});
    window.setInterval(draw, 500);
    draw();
  }
  return {position, label, install};
});
