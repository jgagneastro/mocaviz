/* Plot helpers adapted from the JWST selector. */
(function(root){
  function fitView(rows,xlog=true,ylog=true,yField='teff',invertY=false){
    const plotted=rows.filter(r=>Number(r.age_myr)>0&&r[yField]!==null&&r[yField]!==undefined&&Number.isFinite(Number(r[yField]))&&(yField!=='teff'||Number(r[yField])>0));
    if(!plotted.length)return null;
    const x=plotted.map(r=>xlog?Math.log10(Number(r.age_myr)):Number(r.age_myr));
    const y=plotted.map(r=>invertY?-Number(r[yField]):ylog?Math.log10(Number(r[yField])):Number(r[yField]));
    const xmin=Math.min(...x),xmax=Math.max(...x),ymin=Math.min(...y),ymax=Math.max(...y);
    const xpad=xlog ? .15 : Math.max((xmax-xmin)*.08,1),ypad=invertY ? .5 : ylog ? .04 : Math.max((ymax-ymin)*.08,25);
    return {xmin:xlog?xmin-xpad:Math.max(0,xmin-xpad),xmax:xmax+xpad,
      ymin:invertY?ymin-ypad:ylog?ymin-ypad:Math.max(0,ymin-ypad),ymax:ymax+ypad};
  }
  function interpolate(points,value,xKey,yKey){
    const usable=(points||[]).map(p=>[Number(p[xKey]),Number(p[yKey])]).filter(([x,y])=>Number.isFinite(x)&&Number.isFinite(y)).sort((a,b)=>a[0]-b[0]);
    const x=Number(value);if(!usable.length||!Number.isFinite(x)||x<usable[0][0]||x>usable[usable.length-1][0])return null;
    for(let i=1;i<usable.length;i++)if(x<=usable[i][0]){const [x0,y0]=usable[i-1],[x1,y1]=usable[i],f=x1===x0?0:(x-x0)/(x1-x0);return y0+f*(y1-y0);}
    return usable[usable.length-1][1];
  }
  const youngTeffForSpt=(points,sptn)=>interpolate(points,sptn,'sptn','teff');
  const youngSptForTeff=(points,teff)=>interpolate(points,teff,'teff','sptn');
  function linearTicks(min,max,count=6){
    if(!Number.isFinite(min)||!Number.isFinite(max)||max<=min)return [];
    const rough=(max-min)/Math.max(1,count),power=10**Math.floor(Math.log10(rough)),scaled=rough/power;
    const step=(scaled<=1?1:scaled<=2?2:scaled<=5?5:10)*power,ticks=[];
    for(let value=Math.ceil(min/step)*step;value<=max+step*1e-9;value+=step)ticks.push(Math.abs(value)<step*1e-9?0:value);
    return ticks;
  }
  function jitter(key,axis){let h=2166136261;for(const c of String(key)+axis)h=Math.imul(h^c.charCodeAt(0),16777619);return (h>>>0)/4294967295*2-1;}

  function markerShape(r){return Number(r.lowg_like)===1?'star':['HYA','CHYA'].includes(r.moca_aid)?'diamond':'circle';}
root.PlotLogic={fitView,linearTicks,interpolate,youngTeffForSpt,youngSptForTeff,jitter,markerShape};
})(window);
