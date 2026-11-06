// Image requests inside a credential-free WiseView frame.
(function(root) {
  'use strict';
  function create(win) {
    const waiting=[], cards=new Map(), renders=new WeakMap(); let active=0,cdsActive=0;
    function pump() {
      while(active<4 && waiting.length) {
        // A stalled CDS host must leave room for independent IRSA/NSC/PS1
        // images, even when many HiPS cutouts are queued before them.
        const index=waiting.findIndex(job=>!job.cds || cdsActive<2);
        if(index<0) break;
        const job=waiting.splice(index,1)[0]; active++; if(job.cds) cdsActive++;
        job.run().finally(()=>{active--;if(job.cds) cdsActive--;pump();});
      }
    }
    function attempt(src, options) {
      return new Promise((resolve,reject)=>{
        const image=new win.Image(), url=new URL(src);
        // IRSA's RGB PNG is displayed directly, never read back into a canvas,
        // so it does not need CORS or access to the image's pixels.
        const irsa=url.hostname==='irsa.ipac.caltech.edu' && url.pathname==='/applications/finderchart/servlet/api';
        if(!irsa && options?.crossOrigin!==false) image.crossOrigin='anonymous';
        let timer;
        const finish=(error)=>{
          win.clearTimeout(timer); image.onload=null; image.onerror=null;
          if(error) {image.src='';reject(error);} else resolve(image);
        };
        timer=win.setTimeout(()=>finish(new Error('image load timed out: '+url.hostname)), irsa?60000:20000);
        image.onload=()=>finish(image.naturalWidth>20 && image.naturalHeight>20 ? null : new Error('loaded image is empty'));
        image.onerror=()=>finish(new Error('image load failed: '+url.hostname));
        image.src=src;
      });
    }
    async function withMirror(src,options) {
      try {return await attempt(src,options);}
      catch(error) {
        const url=new URL(src);
        if(url.hostname!=='alasky.cds.unistra.fr' || url.pathname!=='/hips-image-services/hips2fits') throw error;
        url.hostname='alaskybis.cds.unistra.fr';
        try {return await attempt(url.href,options);}
        catch {throw new Error('CDS image service unavailable (primary and mirror)');}
      }
    }
    function load(src,options) {
      return new Promise((resolve,reject)=>{
        const cds=['alasky.cds.unistra.fr','alaskybis.cds.unistra.fr'].includes(new URL(src).hostname);
        waiting.push({cds,run:async()=>{try {resolve(await withMirror(src,options));} catch(error) {reject(error);}}});
        pump();
      });
    }
    function card(key,build) {
      // Resolving NSC updates the panel's payload. Reuse unchanged survey cards
      // rather than launching a second copy of all their image requests.
      if(!cards.has(key)) {
        const promise=Promise.resolve().then(build).catch(error=>{cards.delete(key);throw error;});
        cards.set(key,promise);
        if(cards.size>48) cards.delete(cards.keys().next().value);
      }
      return cards.get(key);
    }
    function render(panel,promises,{labels=[],final=false}={}) {
      const entries=promises.map((promise,index)=>({promise,index,label:labels[index]||'Survey',state:'loading'}));
      renders.get(panel)?.dispose?.();
      renders.set(panel,entries);
      const primary=win.document.getElementById('pawnstarsLink');
      let primaryEntry;
      function updatePrimary() {
        if(!primaryEntry)return;
        const image=primary.querySelector('img'),fallback=image?.dataset.wiseviewFallbackCutout==='1';
        const loaded=image?.complete && image.naturalWidth>20 && image.naturalHeight>20;
        primaryEntry.label=fallback?(image.alt.split(' epoch ')[0]||'Survey finder'):'PS1 finder';
        primaryEntry.state=loaded?'ready':win.__wiseviewVettingPs1FallbackState?.failed?'unavailable':'loading';
        primaryEntry.detail=loaded?'':primary.textContent.trim().replace(/\s+/g,' ');
        primary.hidden=!loaded;
        primary.style.display=loaded?'block':'none';
        primary.style.gridColumn='1 / -1';
        primary.style.order=fallback&&/^DES\b/.test(primaryEntry.label)?'1':loaded&&!fallback?'-2':'0';
      }
      if(primary) {
        primaryEntry={index:-1,card:primary,primary:true};entries.unshift(primaryEntry);updatePrimary();
      }
      const groups={};
      for(const state of ['loading','unavailable']) {
        const group=win.document.createElement('div');
        group.dataset.surveyStatusGroup=state;
        Object.assign(group.style,{gridColumn:'1 / -1',order:state==='loading'?'2':'3',
          minHeight:'0',lineHeight:'1.2',padding:'0 4px'});
        groups[state]=group;
      }
      function redraw() {
        if(renders.get(panel)!==entries)return;
        const priority=entry=>/^PS1(?:\s|$)/i.test(entry.label)?-1:Number(entry.card.style.order)||0;
        const ready=entries.filter(entry=>entry.state==='ready')
          .sort((a,b)=>priority(a)-priority(b)||a.index-b.index);
        for(const entry of ready)entry.card.style.order=String(priority(entry));
        const children=ready.map(entry=>entry.card);
        for(const state of ['loading','unavailable']) {
          const group=groups[state],lines=[];
          for(const entry of entries.filter(entry=>entry.state===state)) {
            const line=win.document.createElement('div');
            line.dataset.surveyState=state;
            line.textContent=entry.label+' · '+(state==='loading'?'Loading…':'Unavailable')+
              (state==='unavailable'&&entry.detail?' · '+entry.detail:'');
            Object.assign(line.style,{margin:'0',padding:'0',minHeight:'0',overflowWrap:'anywhere'});
            lines.push(line);
          }
          group.replaceChildren(...lines);
          if(lines.length)children.push(group);
        }
        if(primaryEntry?.state!=='ready'&&primary)children.push(primary);
        panel.replaceChildren(...children);
      }
      if(primary) {
        const changed=()=>{updatePrimary();redraw();};
        const observer=new win.MutationObserver(changed);
        observer.observe(primary,{childList:true,subtree:true,characterData:true,attributes:true,
          attributeFilter:['src','alt','data-wiseview-fallback-cutout']});
        primary.addEventListener('load',changed,true);primary.addEventListener('error',changed,true);
        entries.dispose=()=>{observer.disconnect();primary.removeEventListener('load',changed,true);primary.removeEventListener('error',changed,true);};
      }
      redraw();
      return Promise.allSettled(entries.map(async entry=>{
        if(entry.primary)return;
        try {
          entry.card=await entry.promise;
          const hasImage=Boolean(entry.card.querySelector('img,canvas'));
          entry.state=hasImage?'ready':final||entry.card.dataset.surveyState==='unavailable'?'unavailable':'loading';
          entry.detail=entry.card.lastElementChild?.textContent?.trim().replace(/\s+/g,' ');
          if(hasImage)entry.card.dataset.surveyState='ready';
        } catch(error) {
          entry.state='unavailable';entry.detail=String(error.message||error).replace(/\s+/g,' ');
        }
        redraw();
      }));
    }
    return {load,card,render};
  }
  if(typeof module!=='undefined' && module.exports) module.exports={create};
  else root.SurveyImages ||= create(root);
})(typeof window==='undefined'?globalThis:window);
