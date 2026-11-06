// Image requests inside a credential-free WiseView frame.
(function(root) {
  'use strict';
  function create(win) {
    const waiting=[], cards=new Map(); let active=0,cdsActive=0;
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
    return {load,card};
  }
  if(typeof module!=='undefined' && module.exports) module.exports={create};
  else root.SurveyImages ||= create(root);
})(typeof window==='undefined'?globalThis:window);
