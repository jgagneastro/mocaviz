/* Interactive plot adapted from the existing selector. */
const canvas=$('plot'),ctx=canvas.getContext('2d');
let plotGeometry=null;
function markerPath(x,y,size,shape){
  ctx.beginPath();
  if(shape==='star'){
    for(let i=0;i<10;i++){const radius=i%2===0?size:size*.44,angle=-Math.PI/2+i*Math.PI/5,px=x+Math.cos(angle)*radius,py=y+Math.sin(angle)*radius;if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);}ctx.closePath();
  }
  else if(shape==='diamond'){ctx.moveTo(x,y-size);ctx.lineTo(x+size,y);ctx.lineTo(x,y+size);ctx.lineTo(x-size,y);ctx.closePath();}
  else ctx.arc(x,y,size,0,2*Math.PI);
}
function draw(){
  if(!state.data)return;
  const rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
  canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);
  const W=rect.width,H=rect.height,p={l:66,r:73,t:26,b:51},w=W-p.l-p.r,h=H-p.t-p.b;
  if(w<30||h<30)return;
  const sptAxis=spectralYAxis(),field=yField(),{xlog,ylog}=axisModes(),tx=value=>xlog?Math.log10(value):value;
  const ty=value=>sptAxis?-Number(value):ylog?Math.log10(value):Number(value);
  const fromX=value=>xlog?10**value:value,fromY=value=>sptAxis?-value:ylog?10**value:value;
  const v=state.view,px=x=>p.l+(x-v.xmin)/(v.xmax-v.xmin)*w,py=y=>p.t+h-(y-v.ymin)/(v.ymax-v.ymin)*h;
  plotGeometry={p,w,h,px,py,W,H};ctx.fillStyle='#0d1117';ctx.fillRect(0,0,W,H);ctx.font='11px system-ui';
  const transitionValues=sptAxis?[LT_TRANSITION_EARLY_SPT,LT_TRANSITION_LATE_SPT]:[LT_TRANSITION_MAX_K,LT_TRANSITION_MIN_K];
  const transitionPixels=transitionValues.filter(value=>value!==null).map(value=>py(ty(value)));
  const transitionTop=transitionPixels.length===2?Math.min(...transitionPixels):-1,transitionBottom=transitionPixels.length===2?Math.max(...transitionPixels):-1;
  const visibleTransitionTop=Math.max(p.t,Math.min(p.t+h,transitionTop));
  const visibleTransitionBottom=Math.max(p.t,Math.min(p.t+h,transitionBottom));
  if(visibleTransitionBottom>visibleTransitionTop){ctx.fillStyle='#f0883e1c';ctx.fillRect(p.l,visibleTransitionTop,w,visibleTransitionBottom-visibleTransitionTop);}
  ctx.strokeStyle='#212831';ctx.lineWidth=1;ctx.fillStyle='#8b949e';
  let ages=[];
  if(xlog){for(let e=-2;e<7;e++)for(const m of [1,2,5])ages.push(m*10**e);}
  else ages=L.linearTicks(v.xmin,v.xmax,6);
  for(const age of ages){let x=px(tx(age));if(x<p.l||x>p.l+w)continue;ctx.beginPath();ctx.moveTo(x,p.t);ctx.lineTo(x,p.t+h);ctx.stroke();ctx.textAlign='center';ctx.fillText(fmt(age,age<10?1:0),x,p.t+h+19);}
  let ticks=[];
  if(sptAxis){
    const earliest=Math.max(0,Math.min(fromY(v.ymax),fromY(v.ymin))),latest=Math.min(35,Math.max(fromY(v.ymax),fromY(v.ymin)));
    const step=latest-earliest>14?2:latest-earliest>7?1:.5;
    for(let subtype=Math.ceil(earliest/step)*step;subtype<=latest+1e-9;subtype+=step)ticks.push(Number(subtype.toFixed(2)));
  }
  else if(ylog){
    const minTemp=fromY(v.ymin),maxTemp=fromY(v.ymax),temperatures=[];
    for(let exponent=Math.floor(v.ymin)-1;exponent<=Math.ceil(v.ymax)+1;exponent++)for(const multiplier of [1,1.25,1.5,2,3,4,5,7.5]){
      const temp=multiplier*10**exponent;if(temp>minTemp&&temp<maxTemp)temperatures.push(temp);
    }
    // Keep the displayed limits explicit and label useful logarithmic intervals in kelvin.
    ticks=[minTemp];let previousY=py(v.ymin);
    for(const temp of temperatures.sort((a,b)=>a-b)){const y=py(ty(temp));if(Math.abs(y-previousY)>=22&&Math.abs(y-py(v.ymax))>=18){ticks.push(temp);previousY=y;}}
    if(Math.abs(py(v.ymax)-previousY)>=18)ticks.push(maxTemp);
  }
  else ticks=L.linearTicks(v.ymin,v.ymax,6);
  for(const value of ticks){let y=py(ty(value));ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(p.l+w,y);ctx.stroke();ctx.textAlign='right';ctx.fillText(sptAxis?spt(value):fmt(value,0),p.l-10,y+4);}
  if(visibleTransitionBottom>visibleTransitionTop){
    ctx.save();ctx.beginPath();ctx.rect(p.l,p.t,w,h);ctx.clip();ctx.strokeStyle='#f0883e70';ctx.lineWidth=1;ctx.setLineDash([5,4]);
    for(const y of [transitionTop,transitionBottom]){ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(p.l+w,y);ctx.stroke();}
    ctx.setLineDash([]);ctx.fillStyle='#f0a05f';ctx.textAlign='left';ctx.font='10px system-ui';ctx.fillText('L/T transition',p.l+8,(visibleTransitionTop+visibleTransitionBottom)/2+4);ctx.restore();
  }
  ctx.save();ctx.beginPath();ctx.rect(p.l,p.t,w,h);ctx.clip();
  if($('tracks').checked){
    for(const track of state.data.mass_tracks.tracks){const highlighted=track.heavy||[5,50].includes(Number(track.mass));ctx.strokeStyle=highlighted?'#7990a080':'#57647140';ctx.lineWidth=highlighted?2.8:1;ctx.beginPath();let first=true;const converted=[];for(const [a,t] of track.points){const yValue=sptAxis?approxSpt(t):t;if(yValue===null){first=true;continue;}let x=px(tx(a)),y=py(ty(yValue));converted.push([a,yValue]);if(first){ctx.moveTo(x,y);first=false;}else ctx.lineTo(x,y);}ctx.stroke();
      if(highlighted){const visible=converted.filter(([a,yValue])=>px(tx(a))>p.l+30&&px(tx(a))<p.l+w-35&&py(ty(yValue))>p.t+10&&py(ty(yValue))<p.t+h-15);const pt=visible[Math.floor(visible.length*.72)];if(pt){ctx.fillStyle='#9aa9b6';ctx.textAlign='left';ctx.font='10px system-ui';ctx.fillText(`${track.mass} Mjup`,px(tx(pt[0]))+5,py(ty(pt[1]))-7);}}
    }
  }
  state.screen=[];
  // Draw more complete observations last so their brighter symbols remain visible.
  for(const r of [...state.rows].sort((a,b)=>observationCount(a)-observationCount(b))){
    if(!(r.age_myr>0)||r[field]===null||r[field]===undefined||!Number.isFinite(Number(r[field])))continue;
    let age=Number(r.age_myr),yValue=Number(r[field]);
    if($('jitter').checked){age*=10**(L.jitter(key(r),'age')*.024);yValue+=L.jitter(key(r),field)*(sptAxis ? .12 : 32);}
    const x=px(tx(age)),y=py(ty(yValue));if(x<p.l||x>p.l+w||y<p.t||y>p.t+h)continue;
    state.screen.push({r,x,y});
    const shape=L.markerShape(r),color=OBS_COLORS[observationCount(r)],size=shape==='star'?7:shape==='diamond'?6.3:5;
    ctx.fillStyle=color;ctx.strokeStyle=r.has_rv?'#7ee787':'#0d1117';ctx.lineWidth=r.has_rv?1.8:.85;
    markerPath(x,y,size,shape);ctx.fill();ctx.stroke();
    if(state.active&&key(state.active)===key(r)){ctx.strokeStyle='#ffffff';ctx.lineWidth=1.5;markerPath(x,y,size+4,shape);ctx.stroke();}
  }
  ctx.restore();ctx.strokeStyle='#57606a';ctx.lineWidth=1;ctx.strokeRect(p.l,p.t,w,h);
  const spectralAxis=state.data.spectral_type_axis;
  if(spectralAxis&&!sptAxis){
    ctx.font='11px system-ui';ctx.fillStyle='#8b949e';ctx.textAlign='left';
    let previousY=-Infinity;
    for(const tick of spectralAxis.ticks){
      const axisTeff=ty(tick.teff);if(axisTeff<v.ymin||axisTeff>v.ymax)continue;
      const y=py(axisTeff);
      ctx.beginPath();ctx.moveTo(p.l+w,y);ctx.lineTo(p.l+w+5,y);ctx.stroke();
      if(y-previousY>=18){ctx.fillText(spt(tick.sptn),p.l+w+9,y+4);previousY=y;}
    }
    ctx.save();ctx.fillStyle='#b1bac4';ctx.font='12px system-ui';ctx.textAlign='center';
    ctx.translate(W-13,p.t+h/2);ctx.rotate(Math.PI/2);ctx.fillText(spectralAxis.label,0,0);ctx.restore();
  }
  else if(spectralAxis&&sptAxis){
    ctx.font='11px system-ui';ctx.fillStyle='#8b949e';ctx.textAlign='left';let previousY=-Infinity;
    for(const subtype of ticks){const teff=approxTeff(subtype),y=py(ty(subtype));if(teff===null||y-previousY<18)continue;ctx.beginPath();ctx.moveTo(p.l+w,y);ctx.lineTo(p.l+w+5,y);ctx.stroke();ctx.fillText(`${fmt(teff,0)} K`,p.l+w+9,y+4);previousY=y;}
    ctx.save();ctx.fillStyle='#b1bac4';ctx.font='12px system-ui';ctx.textAlign='center';ctx.translate(W-13,p.t+h/2);ctx.rotate(Math.PI/2);ctx.fillText('Approx. Teff (K; young scale)',0,0);ctx.restore();
  }
  ctx.fillStyle='#b1bac4';ctx.font='12px system-ui';ctx.textAlign='center';ctx.fillText(`Adopted association age (Myr) · ${xlog?'log':'linear'} scale`,p.l+w/2,H-10);
  ctx.save();ctx.translate(17,p.t+h/2);ctx.rotate(-Math.PI/2);ctx.fillText(sptAxis?'Adopted spectral type':`Effective temperature (K) · ${ylog?'log':'linear'} scale`,0,0);ctx.restore();
  ctx.textAlign='left';ctx.font='10px system-ui';ctx.fillStyle='#8b949e';ctx.fillText($('tracks').checked?'Sonora Diamondback · hybrid-grav · solar metallicity':'',p.l+5,15);
  const yDescription=sptAxis?`spectral-type axis ${spt(fromY(v.ymax))} to ${spt(fromY(v.ymin))}; right axis gives approximate Teff from the young sequence`:`temperature axis ${ylog?'logarithmic':'linear'}, ${fmt(fromY(v.ymin),0)} to ${fmt(fromY(v.ymax),0)} K; right axis gives spectral type from the young sequence`;
  canvas.setAttribute('aria-label',`${sptAxis?'Spectral type':'Effective temperature'} versus age. The L/T transition ${sptAxis?'from L8 to T2':'from 1150 to 1250 K'} is shaded. Age axis ${xlog?'logarithmic':'linear'}, ${fmt(fromX(v.xmin),1)} to ${fmt(fromX(v.xmax),1)} Myr; ${yDescription}. Select a foreground point to inspect its target.`);
  $('plot-empty').hidden=state.rows.some(r=>Number(r.age_myr)>0&&r[field]!==null&&r[field]!==undefined&&Number.isFinite(Number(r[field])));
}
function nearest(event){const box=canvas.getBoundingClientRect(),x=event.clientX-box.left,y=event.clientY-box.top;let hit=null,best=17;for(const point of state.screen){const d=Math.hypot(point.x-x,point.y-y);if(d<best){hit=point;best=d;}}return {hit,x,y};}
let drag=null;
canvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,view:{...state.view},moved:false};canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{
  if(drag&&plotGeometry){let dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>4)drag.moved=true;if(drag.moved){state.view={xmin:drag.view.xmin-dx/plotGeometry.w*(drag.view.xmax-drag.view.xmin),xmax:drag.view.xmax-dx/plotGeometry.w*(drag.view.xmax-drag.view.xmin),ymin:drag.view.ymin+dy/plotGeometry.h*(drag.view.ymax-drag.view.ymin),ymax:drag.view.ymax+dy/plotGeometry.h*(drag.view.ymax-drag.view.ymin)};draw();$('tooltip').hidden=true;return;}}
  const {hit,x,y}=nearest(e);$('tooltip').hidden=!hit;
  if(hit){const r=hit.r,kind=filters().probKind;$('tooltip').innerHTML=`<strong>${esc(r.designation)}</strong><br>${esc(r.moca_aid)} · ${esc(r.spt)} · ${fmt(r.teff,0)} K<br>${esc(r.observables)} · ${observationCount(r)} observables<br>${fmt(r.age_myr,1)} Myr · ${kind==='summed'?'ΣP young':'P association'} ${fmt(kind==='summed'?r.summed_young_prob:r.individual_prob,1)}% · best X ${fmt(r.visibility?.best_airmass,2)}`;const box=canvas.getBoundingClientRect();$('tooltip').style.left=Math.min(x+14,box.width-260)+'px';$('tooltip').style.top=Math.max(4,y-76)+'px';}
});
canvas.addEventListener('pointerup',e=>{if(drag&&!drag.moved){const {hit}=nearest(e);if(hit)activate(hit.r);}drag=null;});
canvas.addEventListener('pointerleave',()=>{$('tooltip').hidden=true;});
canvas.addEventListener('wheel',e=>{e.preventDefault();if(!plotGeometry)return;const box=canvas.getBoundingClientRect(),g=plotGeometry,v=state.view,{xlog,ylog}=axisModes(),sptAxis=spectralYAxis();const fx=Math.max(0,Math.min(1,(e.clientX-box.left-g.p.l)/g.w)),fy=1-Math.max(0,Math.min(1,(e.clientY-box.top-g.p.t)/g.h));const cx=v.xmin+fx*(v.xmax-v.xmin),cy=v.ymin+fy*(v.ymax-v.ymin),scale=Math.exp(Math.sign(e.deltaY)*.13);let dx=Math.max(xlog ? .04 : 1,Math.min(xlog?6:1e7,(v.xmax-v.xmin)*scale)),dy=Math.max(sptAxis ? .5 : ylog ? .025 : 10,Math.min(sptAxis ? 40 : ylog ? 3 : 1e6,(v.ymax-v.ymin)*scale));state.view={xmin:cx-fx*dx,xmax:cx+(1-fx)*dx,ymin:cy-fy*dy,ymax:cy+(1-fy)*dy};draw();},{passive:false});
new ResizeObserver(draw).observe(canvas);
