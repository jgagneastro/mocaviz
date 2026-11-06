// Tab-local display preferences: no requests or review decisions.
(() => {
  'use strict';
  const pool=document.getElementById('wise-pool'),button=document.getElementById('toggle-wise-controls');
  let hidden=false;
  function send(frame){frame.contentWindow?.postMessage({kind:'wise-controls',hidden},'*');}
  function watch(frame){if(frame.tagName==='IFRAME'){frame.addEventListener('load',()=>send(frame));send(frame);}}
  for(const frame of pool.children)watch(frame);
  new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes)watch(node);})
    .observe(pool,{childList:true});
  button.onclick=()=>{
    hidden=!hidden;button.textContent=(hidden?'Show':'Hide')+' WiseView controls [V]';
    button.setAttribute('aria-pressed',String(hidden));
    for(const frame of pool.children)send(frame);
  };
  document.addEventListener('keydown',event=>{
    if(event.ctrlKey||event.metaKey||event.altKey||event.shiftKey||event.repeat||
      event.target.closest('input,textarea,select,[contenteditable=true]'))return;
    if(event.key.toLowerCase()==='v'){event.preventDefault();button.click();}
  });
  const science=document.querySelector('.science'),grid=document.querySelector('.review-grid');
  const plot=document.getElementById('plot'),handle=document.getElementById('spectrum-resize');
  let manual=false,scheduled=false;
  function fit(){
    scheduled=false;
    const graph=plot.firstElementChild;
    if(!manual||!graph?._fullLayout||!window.Plotly)return;
    const width=Math.round(plot.clientWidth),height=Math.round(plot.clientHeight);
    if(width>0&&height>0&&(graph._fullLayout.width!==width||graph._fullLayout.height!==height))
      Plotly.relayout(graph,{width,height});
  }
  function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(fit);}}
  new ResizeObserver(schedule).observe(plot);
  window.addEventListener('resize',()=>{if(grid.clientWidth<600)grid.style.gridTemplateColumns='';schedule();});
  new MutationObserver(()=>{
    const graph=plot.firstElementChild;
    if(graph?.on)graph.on('plotly_afterplot',schedule);
    schedule();
  }).observe(plot,{childList:true});
  function resize(width,height){
    manual=true;science.classList.add('spectrum-sized');
    science.style.height=Math.max(280,Math.min(2200,height))+'px';
    const columns=getComputedStyle(grid).gridTemplateColumns.split(' ').length;
    if(columns>1){
      const maximum=Math.max(280,grid.clientWidth-294);
      grid.style.gridTemplateColumns=`minmax(280px,1fr) ${Math.max(280,Math.min(maximum,width))}px`;
    }
    grid.style.minHeight='';schedule();
  }
  handle.addEventListener('pointerdown',event=>{
    if(event.button!==0)return;
    event.preventDefault();handle.setPointerCapture(event.pointerId);
    const rect=science.getBoundingClientRect(),x=event.clientX,y=event.clientY;
    const move=next=>resize(rect.width+next.clientX-x,rect.height+next.clientY-y);
    const done=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',done);handle.removeEventListener('pointercancel',done);};
    handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',done);handle.addEventListener('pointercancel',done);
  });
  handle.addEventListener('keydown',event=>{
    const delta={ArrowLeft:[-40,0],ArrowRight:[40,0],ArrowUp:[0,-40],ArrowDown:[0,40]}[event.key];
    if(!delta)return;event.preventDefault();event.stopPropagation();
    const rect=science.getBoundingClientRect();resize(rect.width+delta[0],rect.height+delta[1]);
  });
})();
