(() => {
  'use strict';
  const wiseImage = document.getElementById('image');
  if (!wiseImage) return;

  const style = document.createElement('style');
  style.textContent = `
    #image-field { display: flex; flex-direction: column; align-items: flex-start; }
    #pawnstarsLink:has(img[data-wiseview-fallback-cutout][alt^="DES "]) { order: 1; }
    #wiseview-top-row {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      gap: 8px;
      width: max(280px, calc(100vw - 284px));
    }
    #wiseview-top-row > #image { flex: none; }
    #sublime-cutouts {
      flex: 1 1 180px;
      min-width: 0;
      max-width: 440px;
      font: 13px/1.35 system-ui, sans-serif;
      color: #edf5fc;
      background: #080c12;
    }
    #sublime-cutouts header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
      padding: 5px 8px;
    }
    #sublime-cutouts h2 { margin: 0; font-size: 13px; }
    #sublime-cutouts .cutout-navigation:not([hidden]) { display: flex; align-items: center; gap: 6px; }
    #sublime-cutouts .cutout-position {
      min-width: 3.5ch;
      color: #a6dfcb;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
      text-align: center;
      white-space: nowrap;
    }
    #sublime-cutouts img { display: block; width: 100%; max-height: 440px; object-fit: contain; }
    #sublime-cutouts [hidden] { display: none; }
    #sublime-cutouts button { color: inherit; background: #182535; border: 1px solid #38516c; border-radius: 3px; }
    #sublime-cutouts p { margin: 0; padding: 5px 8px; overflow-wrap: anywhere; }
  `;
  document.head.appendChild(style);

  const row = document.createElement('div');
  row.id = 'wiseview-top-row';
  wiseImage.before(row);
  row.append(wiseImage);

  const panel = document.createElement('section');
  panel.id = 'sublime-cutouts';
  panel.hidden = true;
  panel.innerHTML = `<header><h2>SUBLIME cutouts</h2><div class="cutout-navigation" hidden>
    <button type="button" aria-label="Previous SUBLIME cutout">‹</button>
    <span class="cutout-position"></span>
    <button type="button" aria-label="Next SUBLIME cutout">›</button>
    </div></header><img alt="SPHEREx source cutout" hidden><p></p>`;
  row.append(panel);
  const controls = panel.querySelector('.cutout-navigation');
  const position = controls.querySelector('.cutout-position');
  const [previous, next] = controls.querySelectorAll('button');
  const image = panel.querySelector('img');
  const caption = panel.querySelector('p');
  let images = [], index = 0, active = false, timer;

  function showCutout() {
    const current = images[index];
    image.src = current.data;
    position.textContent = `${index + 1}/${images.length}`;
    const decimal = value => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(3);
    const epochs = (current.epochs || []).map(({sample, epoch_yr, min_epoch, max_epoch}) => {
      if (epoch_yr == null && min_epoch == null && max_epoch == null) return `${sample}: epoch unavailable`;
      const span = min_epoch != null && max_epoch != null ? ` (span ${decimal(min_epoch)}–${decimal(max_epoch)})` : '';
      return `${sample}: mean epoch ${decimal(epoch_yr)}${span}`;
    });
    caption.textContent = `${current.source_key} · ${epochs.join(' · ') || 'epoch unavailable'}`;
  }

  function step(direction) {
    index = (index + direction + images.length) % images.length;
    showCutout();
  }

  function startCarousel() {
    clearInterval(timer);
    if (active && images.length > 1) timer = setInterval(() => step(1), 2300);
  }

  previous.onclick = () => step(-1);
  next.onclick = () => step(1);
  window.addEventListener('message', event => {
    if (event.source !== parent) return;
    if (event.data?.kind === 'sublime-cutout-active') {
      active = true;
      startCarousel();
    } else if (event.data?.kind === 'sublime-cutouts') {
      images = event.data.images || [];
      active = active || event.data.active === true;
      index = 0;
      panel.hidden = false;
      image.hidden = !images.length;
      controls.hidden = images.length < 2;
      if (images.length) showCutout();
      else caption.textContent = event.data.error || 'No available SUBLIME cutouts for this object.';
      startCarousel();
    }
  });
})();
