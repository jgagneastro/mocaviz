// Pin the target to its sky coordinate on the science canvas, not the overlay midpoint.
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  if(root)root.TargetCrosshair=api;
})(typeof window==='object'?window:null,function(){
  'use strict';
  function imagePoint(image,x,y){
    if(!image?.offsetParent||!image.clientWidth||!image.clientHeight)return null;
    // Use layout coordinates shared by the image and marker. Safari can return
    // already-zoomed viewport coordinates for elements inside a zoomed iframe.
    return {left:image.offsetLeft+image.clientLeft+x*image.clientWidth,
      top:image.offsetTop+image.clientTop+y*image.clientHeight};
  }
  function worldPixel(swapper,target){
    if(!swapper||typeof swapper.__world_to_pix!=='function'||
       !target||target.ra_deg==null||target.dec_deg==null||
       !Number.isFinite(Number(target.ra_deg))||!Number.isFinite(Number(target.dec_deg))||
       !['CRVAL1','CRVAL2','CRPIX1','CRPIX2','NAXIS2'].every(key=>Number.isFinite(swapper[key])))return null;
    const p=swapper.__world_to_pix(Number(target.ra_deg),Number(target.dec_deg));
    return p&&Number.isFinite(p.px)&&Number.isFinite(p.py)?p:null;
  }
  function position(swapper,canvas,target){
    const p=worldPixel(swapper,target);
    if(!p||!canvas?.width||!canvas?.height||p.px<0||p.py<0||p.px>canvas.width||p.py>canvas.height)return null;
    return imagePoint(canvas,p.px/canvas.width,p.py/canvas.height);
  }
  // Native SPHEREx pixel width: 6.15 arcsec (IRSA); use that as the diameter.
  function apertureOutline(swapper,canvas,center){
    if(!worldPixel(swapper,center)||!canvas?.width||!canvas?.height||!canvas.clientWidth||!canvas.clientHeight)return null;
    const rad=Math.PI/180,lat=Number(center.dec_deg)*rad,ra=Number(center.ra_deg);
    const radius=6.15/2/3600*rad,points=[];
    for(let i=0;i<48;i++){
      const bearing=i*2*Math.PI/48;
      const dec=Math.asin(Math.max(-1,Math.min(1,Math.sin(lat)*Math.cos(radius)+Math.cos(lat)*Math.sin(radius)*Math.cos(bearing))));
      const deltaRa=Math.atan2(Math.sin(bearing)*Math.sin(radius)*Math.cos(lat),Math.cos(radius)-Math.sin(lat)*Math.sin(dec));
      const point=worldPixel(swapper,{ra_deg:(ra+deltaRa/rad+360)%360,dec_deg:dec/rad});
      if(!point)return null;
      points.push(`${point.px*canvas.clientWidth/canvas.width},${point.py*canvas.clientHeight/canvas.height}`);
    }
    return points.join(' ');
  }
  function motionEndpoints(windows,motion){
    if(!Array.isArray(windows)||windows.length<2||!motion)return null;
    const {reference_ra_deg:ra,reference_dec_deg:dec,reference_epoch_yr:epoch,pmra_masyr:east,pmdec_masyr:north}=motion;
    if(![ra,dec,epoch,east,north].every(Number.isFinite)||(east===0&&north===0))return null;
    const dates=[windows[0],windows.at(-1)];
    if(!dates.every(frame=>Array.isArray(frame)&&frame.length&&frame.every(Number.isFinite)))return null;
    // WiseView uses the mean MJD of each coadd for its own motion overlay.
    const mjds=dates.map(frame=>frame.reduce((sum,mjd)=>sum+mjd,0)/frame.length).sort((a,b)=>a-b);
    if(mjds[0]===mjds[1])return null;
    const rad=Math.PI/180,lat=dec*rad,bearing=Math.atan2(east,north);
    return mjds.map(mjd=>{
      const years=2000+(mjd-51544.5)/365.25-epoch;
      const distance=Math.hypot(east,north)*years*rad/3600000;
      const sinDec=Math.sin(lat)*Math.cos(distance)+Math.cos(lat)*Math.sin(distance)*Math.cos(bearing);
      const newDec=Math.asin(Math.max(-1,Math.min(1,sinDec)));
      const deltaRa=Math.atan2(Math.sin(bearing)*Math.sin(distance)*Math.cos(lat),Math.cos(distance)-Math.sin(lat)*Math.sin(newDec));
      return {ra_deg:(ra+deltaRa/rad+360)%360,dec_deg:newDec/rad};
    });
  }
  function motionArrowPath(x1,y1,x2,y2){
    const dx=x2-x1,dy=y2-y1,length=Math.hypot(dx,dy);
    const head=Math.min(8,length*0.6),ux=dx/length,uy=dy/length;
    const bx=x2-head*ux,by=y2-head*uy,wx=head*uy/2,wy=head*ux/2;
    return `M ${x1} ${y1} L ${x2} ${y2} M ${bx-wx} ${by+wy} L ${x2} ${y2} L ${bx+wx} ${by-wy}`;
  }
  function separation(a,b){
    const rad=Math.PI/180,da=(a.ra_deg-b.ra_deg)*rad,dd=(a.dec_deg-b.dec_deg)*rad;
    const h=Math.sin(dd/2)**2+Math.cos(a.dec_deg*rad)*Math.cos(b.dec_deg*rad)*Math.sin(da/2)**2;
    return 2*Math.asin(Math.sqrt(Math.max(0,Math.min(1,h))))/rad*3600;
  }
  function cutoutGroups(items,target){
    const groups=[];
    for(const item of Array.isArray(items)?items.slice(0,128):[]){
      if(!item||!Number.isInteger(item.cutout_index)||item.cutout_index<1||item.cutout_index>128||
          typeof item.ra_deg!=='number'||typeof item.dec_deg!=='number'||
          !Number.isFinite(item.ra_deg)||!Number.isFinite(item.dec_deg)||
          item.ra_deg<0||item.ra_deg>=360||Math.abs(item.dec_deg)>90)continue;
      let group=groups.find(group=>separation(group,item)<0.1);
      if(!group){group={ra_deg:item.ra_deg,dec_deg:item.dec_deg,indices:[]};groups.push(group);}
      if(!group.indices.includes(item.cutout_index))group.indices.push(item.cutout_index);
    }
    for(const group of groups)group.isTarget=!!target&&separation(group,target)<0.1;
    return groups;
  }
  function install(target){
    if(window.__targetCrosshairInstalled)return;
    window.__targetCrosshairInstalled=true;
    if(typeof window.WiseSwapper==='function'){
      const Original=window.WiseSwapper;
      window.WiseSwapper=function(...args){const instance=Reflect.construct(Original,args);window.__targetCrosshairSwapper=instance;return instance;};
      window.WiseSwapper.prototype=Original.prototype;
    }
    function marker(id,color='#ff3333',thickness=3,arm=18){
      const element=document.createElement('div');element.id=id;
      element.style.cssText='position:absolute;width:0;height:0;pointer-events:none;z-index:2147483647;display:none';
      const gap=8,half=thickness/2;
      for(const [left,top,width,height] of [[-half,-half,thickness,thickness],[-gap-arm,-half,arm,thickness],
          [gap,-half,arm,thickness],[-half,-gap-arm,thickness,arm],[-half,gap,thickness,arm]]){
        const part=document.createElement('div');
        part.style.cssText=`position:absolute;left:${left}px;top:${top}px;width:${width}px;height:${height}px;background:${color};box-shadow:0 0 2px #000`;
        element.appendChild(part);
      }
      return element;
    }
    const main=marker('wiseview-vetting-crosshair'),ps1=marker('wiseview-vetting-ps1-crosshair');
    main.dataset.anchor='wcs';
    let cutoutMarkers=[];
    // Wait for the parent settings so preloaded frames cannot flash a hidden overlay.
    let showWiseCrosshairs=false;
    let showProperMotion=false;
    let arrow=null;
    window.addEventListener('message',event=>{
      if(event.source!==window.parent)return;
      if(event.data?.kind==='wise-overlays'&&typeof event.data.crosshairs==='boolean'&&typeof event.data.properMotion==='boolean'){
        showWiseCrosshairs=event.data.crosshairs;
        showProperMotion=event.data.properMotion;
        draw();
        return;
      }
      if(event.data?.kind!=='sublime-cutout-positions')return;
      for(const item of cutoutMarkers)item.element.remove();cutoutMarkers=[];
      const groups=cutoutGroups(event.data.positions,target);
      cutoutMarkers=groups.map((group,i)=>{
        const namespace='http://www.w3.org/2000/svg';
        const element=document.createElementNS(namespace,'svg');element.id='wiseview-cutout-crosshair-'+(i+1);
        element.style.cssText='position:absolute;display:none;pointer-events:none;z-index:2147483647;overflow:hidden';
        element.setAttribute('aria-hidden','true');element.dataset.anchor='wcs';
        const outline=document.createElementNS(namespace,'polygon');
        outline.setAttribute('fill','none');outline.setAttribute('stroke','#ff9f32');
        outline.setAttribute('stroke-width','1.5');outline.setAttribute('vector-effect','non-scaling-stroke');
        element.appendChild(outline);
        element.dataset.cutoutIndices=group.indices.join(',');
        return {group,element};
      });
      draw();
    });
    function place(element,p,anchor){
      element.style.display=p?'block':'none';
      if(!p)return;
      element.style.left=p.left+'px';element.style.top=p.top+'px';
      if(element.parentNode!==anchor)anchor.appendChild(element);
    }
    function drawMotion(swapper,canvas){
      if(arrow)arrow.svg.style.display='none';
      const origin=showProperMotion&&imagePoint(canvas,0,0);
      const ends=origin&&canvas.width&&canvas.height&&motionEndpoints(swapper?.window_mjds,target.motion);
      if(!ends)return;
      const points=ends.map(end=>worldPixel(swapper,end));
      if(points.some(point=>!point))return;
      const scaleX=canvas.clientWidth/canvas.width,scaleY=canvas.clientHeight/canvas.height;
      const [[x1,y1],[x2,y2]]=points.map(({px,py})=>[px*scaleX,py*scaleY]);
      const dx=x2-x1,dy=y2-y1,length=Math.hypot(dx,dy);
      if(length<1e-6)return;
      if(!arrow){
        const namespace='http://www.w3.org/2000/svg';
        const svg=document.createElementNS(namespace,'svg');
        svg.id='wiseview-proper-motion-arrow';
        svg.style.cssText='position:absolute;pointer-events:none;z-index:2147483646;overflow:hidden';
        svg.setAttribute('aria-hidden','true');
        svg.setAttribute('fill','none');
        svg.setAttribute('stroke','#d020ff');
        svg.setAttribute('stroke-width','1');
        svg.setAttribute('stroke-linecap','round');
        svg.setAttribute('stroke-linejoin','round');
        const guide=document.createElementNS(namespace,'path'),path=document.createElementNS(namespace,'path');
        guide.setAttribute('opacity','0.4');
        guide.setAttribute('stroke-width','3');
        path.setAttribute('opacity','0.65');
        svg.appendChild(guide);
        svg.appendChild(path);
        arrow={svg,guide,path};
      }
      const {svg,guide,path}=arrow;
      svg.setAttribute('width',canvas.clientWidth);
      svg.setAttribute('height',canvas.clientHeight);
      const center=worldPixel(swapper,target);
      if(center){
        const x=center.px*scaleX,y=center.py*scaleY;
        // Normalize in WiseView image pixels so the guide scales with zoom.
        const imageLength=Math.hypot(dx/scaleX,dy/scaleY);
        const halfX=1.5*dx/imageLength,halfY=1.5*dy/imageLength;
        guide.setAttribute('d',motionArrowPath(x-halfX,y-halfY,x+halfX,y+halfY));
      }else guide.setAttribute('d','');
      path.setAttribute('d',motionArrowPath(x1,y1,x2,y2));
      place(svg,origin,canvas.offsetParent);
    }
    function draw(){
      const canvas=document.querySelector('#daCanvas');
      const swapper=window.__targetCrosshairSwapper;
      place(main,showWiseCrosshairs?position(swapper,canvas,target):null,canvas?.offsetParent);
      for(const {group,element} of cutoutMarkers){
        const points=showWiseCrosshairs&&apertureOutline(swapper,canvas,group);
        if(points){
          element.setAttribute('width',canvas.clientWidth);element.setAttribute('height',canvas.clientHeight);
          element.children[0].setAttribute('points',points);
        }
        place(element,points?imagePoint(canvas,0,0):null,canvas?.offsetParent);
      }
      drawMotion(swapper,canvas);
      const finder=document.querySelector('#pawnstars');
      if(finder&&finder.style.position!=='relative')finder.style.position='relative';
      const image=document.querySelector('#pawnstars img');
      const center=image?.complete&&image.naturalWidth>0?imagePoint(image,0.5,0.5):null;
      place(ps1,center,image?.offsetParent);
    }
    window.__wiseviewVettingPlaceCrosshair=draw;
    window.addEventListener('resize',draw,{passive:true});
    if(window.ResizeObserver){const observer=new ResizeObserver(draw),canvas=document.querySelector('#daCanvas');if(canvas)observer.observe(canvas);}
    // WCS, slider zoom changes and replacement finder images can arrive asynchronously.
    window.setInterval(draw,250);draw();
  }
  return {position,apertureOutline,cutoutGroups,motionEndpoints,install};
});
