// Runs inside the sandboxed WiseView frame; only its parent can change visibility.
(() => {
  const style=document.createElement('style');
  style.textContent=`
    body.wise-controls-hidden #nav-left { display:none !important; }
    body.wise-controls-hidden #image-field,body.wise-controls-hidden #epoch-legend { margin-left:8px !important; }
    body.wise-controls-hidden #wiseview-top-row { width:max(280px,calc(100vw - 24px)); }
  `;
  document.head.append(style);
  window.addEventListener('message',event=>{
    if(event.source!==parent||event.data?.kind!=='wise-controls')return;
    document.body.classList.toggle('wise-controls-hidden',event.data.hidden===true);
    window.dispatchEvent(new Event('resize'));
  });
})();
