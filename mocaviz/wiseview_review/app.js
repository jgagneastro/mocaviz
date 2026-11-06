(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const token = document.querySelector('meta[name="review-token"]').content;
  const classes = [
    ['6','Moving · red'],['5','Moving · black'],['4','Maybe moving · red'],['3','Maybe moving · black'],
    ['2','Still · red'],['1','Still · black'],['n','No detection'],['0','Cannot determine'],['b','Bad'],['g','Bad / galaxy'],
    ['i','Bad / giant'],['h','Bad / halo'],['d','Bad / should be detected'],['c','Source confusion'],['m','Mis-centered SPHEREx but red'],['e','Good but M-type'],['r','Risky - reddened region']
  ];
  let index=0,total=0,current=null,serial=0,spectrumSerial=0,statsSerial=0,cacheSerial=0,statsKey='',working=false,cutouts=[],previewController=null,frameUrl='',activeMode='sublime',sublimeSource='pcat_sublime_candidates_v2',sublimeLane='sublimeaperture';
  const PRELOAD_AHEAD=5, PRELOAD_CONCURRENCY=2, preloads=new Map();
  let activeEntry=null, preloadRunning=0;
  let spectralOptions=[],pendingSpectral={},loadedSpectra={},activeSpectralLane=null;
  let cutoutOptions=[],pendingCutout=null,cutoutStorageReady=false;
  const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  function formatCount(value){const n=Number(value);return n>9999?(n/1000).toFixed(1)+'k':n.toLocaleString();}
  function message(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error);}
  const authParams=new URLSearchParams(location.search), authHash=new URLSearchParams(location.hash.slice(1));
  const getAuth=(...keys)=>keys.map(k=>authHash.get(k)??authParams.get(k)).find(v=>v!=null)||'';
  const auth={'X-MOCA-User':getAuth('user','username'),'X-MOCA-Password':getAuth('pwd','password'),'X-MOCA-Database':getAuth('dbase','db','database')};
  const canWrite=document.body.dataset.canWrite==='true';
  if(!canWrite)$('decision-table').textContent='Read-only collaborator view. Management credentials are required to save reviews.';
  let queueOids=[], queueState=null, queueFilters={}, queueMode='sublime';
  const objectTokens=new Map(),cutoutTokens=new Map(),undoTokens=[];
  async function api(route,body={},signal){
    if(route==='status')return queueState||{state:'idle',total:0};
    if(['classify','duplicate','undo'].includes(route)&&!canWrite)throw Error('Management credentials are required to save reviews.');
    const target=Number(body.index??index),oid=queueOids[target];
    if(route!=='queue')body={filters:queueFilters,mode:queueMode,...body};
    if(oid!=null)body={...body,oid,object_token:objectTokens.get(target),cutout_token:cutoutTokens.get(target)};
    if(route==='undo')body.undo_token=undoTokens.at(-1);

    const response=await fetch('api/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':token,...auth},body:JSON.stringify(body),signal});
    const data=await response.json(); if(!response.ok) throw new Error(data.error||'Request failed');
    if(route==='queue'){queueOids=data.oids;queueState=data;queueFilters=body.filters;queueMode=body.mode;objectTokens.clear();cutoutTokens.clear();undoTokens.length=0;}
    if(data.object_token)objectTokens.set(target,data.object_token);
    if(data.cutout_token)cutoutTokens.set(target,data.cutout_token);
    if(data.undo_token){undoTokens.push(data.undo_token);objectTokens.delete(target);cutoutTokens.delete(target);}
    if(route==='undo')undoTokens.pop();
    return route==='object'?{...data,total:queueOids.length}:data;
  }
  function disposeEntry(entry){
    if(!entry||entry.disposed)return;entry.disposed=true;entry.controller.abort();
    if(entry.element)entry.element.remove();
  }
  function resetPreloads(){for(const entry of preloads.values())disposeEntry(entry);preloads.clear();}
  function syncWiseOverlays(frame){
    frame.contentWindow?.postMessage({kind:'wise-overlays',crosshairs:$('show-wise-crosshairs').checked,
      properMotion:$('show-wise-pm').checked,nearbyMarkers:$('show-wise-nearby').checked,includeSublimeNeighbors:$('include-sublime-neighbors').checked},'*');
  }
  function nearbyLists(object){
    const visible=row=>$('include-sublime-neighbors').checked||!/^SUBLIME/i.test(String(row.designation||''));
    return {matches:(object?.nearby_spectroscopic_l_dwarfs||[]).filter(visible),
      alerts:(object?.nearby_ucd_candidates_and_claims||[]).filter(visible)};
  }
  function syncNearbyMarkers(frame,object){
    const items=new Map();
    const {matches,alerts}=nearbyLists(object);
    for(const row of [...alerts,...matches]){
      const oid=Number(row.moca_oid),ra=Number(row.ra_deg),dec=Number(row.dec_deg);
      if(!Number.isSafeInteger(oid)||oid<=0||row.ra_deg==null||row.dec_deg==null||!Number.isFinite(ra)||!Number.isFinite(dec))continue;
      items.set(oid,{moca_oid:oid,designation:row.designation||'',ra_deg:ra,dec_deg:dec,position_epoch_yr:row.position_epoch_yr??null});
    }
    frame.contentWindow?.postMessage({kind:'nearby-marker-items',items:[...items.values()]},'*');
  }
  function createEntry(target,mode){return {index:target,mode,controller:new AbortController(),started:false,disposed:false};}
  function startEntry(entry,background){
    if(entry.started)return;entry.started=true;if(background)preloadRunning++;
    const body={index:entry.index}, signal=entry.controller.signal;
    const markFailure=error=>{if(error.name!=='AbortError')entry.failed=true;throw error;};
    entry.object=api('object',body,signal).catch(error=>{if(error.name==='AbortError')throw error;return api('object',body,signal);}).catch(markFailure);
    entry.spectrum=entry.object.then(()=>api('spectra',body,signal));
    entry.cutouts=entry.mode!=='redmovers'?entry.object.then(()=>api('cutouts',body,signal).catch(error=>{
      if(error.name==='AbortError')throw error;
      return api('cutouts',body,signal);
    })):Promise.resolve({images:[]});
    entry.surveys=entry.object.then(()=>api('surveys',body,signal));
    entry.frame=entry.object.then(()=>api('frame',body,signal)).then(data=>{
      if(entry.disposed)throw new DOMException('Preload cancelled','AbortError');
      const frame=document.createElement('iframe');entry.element=frame;frame.className='wise-frame';
      frame.title='WiseView and survey images';frame.setAttribute('sandbox','allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads');frame.referrerPolicy='no-referrer';
      frame.onload=()=>{
        if(!entry.disposed)syncWiseOverlays(frame);
        entry.object.then(data=>{if(!entry.disposed)syncNearbyMarkers(frame,data.object);}).catch(()=>{});
        entry.surveys.then(s=>{if(!entry.disposed)frame.contentWindow.postMessage({kind:'resolved-surveys',script:s.script},'*');}).catch(()=>{});
        if(entry.mode!=='redmovers')entry.cutouts.then(data=>{
          if(entry.disposed)return;
          const images=data.images||[];
          frame.contentWindow.postMessage({kind:'sublime-cutout-positions',positions:
            images.map((image,i)=>({...image.position,cutout_index:i+1})).filter(item=>item.ra_deg!=null&&item.dec_deg!=null)},'*');
          frame.contentWindow.postMessage({kind:'sublime-cutouts',active:frame.style?.display==='block',
            images:images.filter(image=>image.data).map(({data,source_key,epochs})=>({data,source_key,epochs}))},'*');
        }).catch(()=>{
          if(!entry.disposed)frame.contentWindow.postMessage({kind:'sublime-cutouts',error:'Could not load SUBLIME cutouts.'},'*');
        });
      };
      const base=new URL('.',document.baseURI).href;
      const html=data.html.replace(/<base href="[^"]*">/,'<base href="'+base+'">');
      frame.src='data:text/html;base64,'+btoa(unescape(encodeURIComponent(html)))+'#'+data.fragment;
      $('wise-pool').appendChild(frame);return {element:frame,url:'#'+data.fragment};
    });
    for(const key of ['spectrum','cutouts','surveys','frame'])entry[key]=entry[key].catch(markFailure);
    // Each promise is also consumed independently when the target is shown.
    const done=Promise.allSettled([entry.object,entry.spectrum,entry.cutouts,entry.surveys,entry.frame]);
    if(background)done.then(()=>{preloadRunning--;pumpPreloads();});
  }
  function pumpPreloads(){
    if(preloadRunning>=PRELOAD_CONCURRENCY)return;
    for(const entry of preloads.values()){
      if(preloadRunning>=PRELOAD_CONCURRENCY)break;
      if(!entry.started&&!entry.disposed)startEntry(entry,true);
    }
  }
  function schedulePreloads(){
    const end=Math.min(total-1,index+PRELOAD_AHEAD);
    for(const [i,entry] of preloads){
      if(i<=index||i>end||entry.mode!==activeMode){disposeEntry(entry);preloads.delete(i);}
    }
    for(let i=index+1;i<=end;i++)if(!preloads.has(i))preloads.set(i,createEntry(i,activeMode));
    pumpPreloads();
  }
  function takeEntry(target){
    let entry=preloads.get(target);
    if(entry&&(entry.mode!==activeMode||entry.failed)){disposeEntry(entry);entry=null;}
    preloads.delete(target);
    if(!entry)entry=createEntry(target,activeMode);
    startEntry(entry,false);return entry;
  }
  async function refreshStats(){
    const request=++statsSerial, mode=$('review-mode').value, lane=$('filter-form').lane.value;
    const publicUcd=mode==='public_ucd';
    document.querySelector('.summary').hidden=publicUcd;
    if(publicUcd)return;
    const key=mode==='redmovers'?mode+':'+lane:mode;
    if(key!==statsKey){for(const el of document.querySelectorAll('.metric strong'))el.textContent='—';statsKey=key;}
    const sample=mode==='redmovers' ? `CatWISE red movers · ${lane==='spiff'?'SPIFF':'SPIFFStacker'}` : 'All active SUBLIME2 objects';
    $('summary-note').textContent=sample+' · loading counts…';
    $('count-confirmed-l0').parentElement.title=mode==='redmovers'?'Good spectrum without a motion review, or moving [5–6], excluding known and claimed objects':'Moving [5–6], L0+ autotype and good, peculiar_ucd, contaminated_ucd or good_reddened in any spectral lane; excluding known and claimed objects';
    $('count-classified').parentElement.title=mode==='redmovers'?'Distinct objects with a motion or spectral review / total':'Distinct objects with a WiseView decision / total';
    $('count-rejected').parentElement.title=mode==='redmovers'?'Distinct objects with a non-positive motion decision or bad spectral review / total':'Distinct objects with a non-positive WiseView decision / total';
    $('summary-definitions').textContent=mode==='redmovers'
      ? 'New excludes known spectroscopic M0+ objects and both claim lists. A good spectrum without a motion review, or with moving [5–6], is confirmed; a good spectrum with still or maybe moving [1–4], or good_candidate without a negative motion review, is a candidate. Negative motion reviews override positive spectrum classifications. M-type [e] is excluded from L0+/T0+ discoveries. T0+ is included in L0+. Classified counts any motion or spectral review; rejected counts non-positive motion decisions (including [0] cannot determine) or bad spectral classifications. Confirmed MOCAdb duplicates are excluded from every count. Counts are distinct objects, independent of queue filters. Both SPIFF and SPIFFStacker reviews are considered; if both exist, the selected lane takes precedence. Historical reviewed spectra marked ignored are included in totals.'
      : 'New excludes public-adopted spectroscopic M0+ objects (including confirmed duplicates) and both claim lists. Confirmed: moving [5–6] and good, peculiar_ucd, contaminated_ucd or good_reddened in any spectral lane. Candidate: one of those four spectral classes with still or maybe moving [1–4], or good_candidate without a negative motion decision, including objects not yet motion-vetted. Unreviewed spectra do not count. A qualifying confirmed lane takes precedence over good_candidate in another lane. Types use the latest SUBLIME2 autotype. M-type [e] is excluded from L0+/T0+ discoveries. T0+ is included in L0+. Classified means any WiseView decision. Rejected means a non-positive WiseView value, including [0] cannot determine, source confusion and mis-centered SPHEREx. Confirmed MOCAdb duplicates are excluded from every count. Counts are distinct active objects, independent of queue filters.';
    $('summary-definitions').textContent+=' Pending motion counters count each new object once across SPIFF, SPIFFStacker and SUBLIMEaperture, with no WiseView review and no spectral-type threshold. Good includes good, peculiar_ucd, contaminated_ucd, good_plus_star and good_reddened. Candidate includes all of those plus good_candidate.';
    try{
      const data=await api('stats',{mode,lane});if(request!==statsSerial)return;
      for(const [id,key] of [['count-confirmed-l0','confirmed_l0'],['count-confirmed-t0','confirmed_t0'],['count-candidate-l0','candidate_l0'],['count-candidate-t0','candidate_t0']]){const element=$(id);element.textContent=formatCount(data[key]);element.title=Number(data[key]).toLocaleString();}
      for(const [id,key] of [['count-pending-good','pending_good_spectra'],['count-pending-candidate','pending_candidate_spectra']]){
        const value=data[key],element=$(id),available=Number.isFinite(value);
        element.textContent=available?formatCount(value):'—';
        element.title=available?Number(value).toLocaleString():'Restart the reviewer to load pending-spectrum counts';
      }
      const progress=n=>{const pct=data.total?100*n/data.total:0;const digits=pct>0&&pct<0.001?4:pct>0&&pct<0.01?3:pct>0&&pct<0.1?2:1;return `${formatCount(n)} / ${formatCount(data.total)} (${pct.toFixed(digits)}%)`;};
      $('count-classified').textContent=progress(data.classified);$('count-rejected').textContent=progress(data.rejected);
      for(const [id,value] of [['count-classified',data.classified],['count-rejected',data.rejected]])$(id).title=`${Number(value).toLocaleString()} / ${Number(data.total).toLocaleString()}`;
      $('summary-note').textContent=sample+' · independent of queue filters';
    }catch(e){if(request===statsSerial)$('summary-note').textContent=sample+' · counts unavailable: '+e.message;}
  }
  async function refreshGaiaCache(){
    const request=++cacheSerial,mode=$('review-mode').value;
    if(mode==='public_ucd'){
      $('gaia-cache-status').textContent='The Gaia cache was built for SUBLIME and CatWISE; other candidates may have no cached count.';
      return;
    }
    try{
      const data=await api('gaia-cache-status',{mode});if(request!==cacheSerial)return;
      const problems=data.error+data.invalid;
      const suffix=data.indexing?' · indexing sample':data.building?' · building in background':'';
      $('gaia-cache-status').textContent=`Gaia cache: ${data.complete.toLocaleString()} / ${data.indexed.toLocaleString()} indexed objects complete${suffix}${problems?` · ${problems.toLocaleString()} need attention`:''}`;
    }catch(e){if(request===cacheSerial)$('gaia-cache-status').textContent='Gaia cache unavailable: '+e.message;}
  }
  function filterValues(){
    const form=$('filter-form'), values={};
    for(const el of form.elements){if(el.disabled||!el.name||el.name==='lane'||el.name==='claim_mode'||el.name==='gaia_mode')continue;if(el.type==='checkbox')values[el.name]=el.checked;else if(el.value.trim())values[el.name]=el.value.trim();}
    values.stacker=form.lane.value==='spiffstacker'; values.sublimeaperture=form.lane.value==='sublimeaperture'; values.noclaim=form.claim_mode.value==='exclude'; values.claimed_only=form.claim_mode.value==='only'; values.nogaia=form.gaia_mode.value==='exclude'; values.gaia_only=form.gaia_mode.value==='only'; return values;
  }
  function appendCoordinateOffsetComment(){
    if(!current||working)return;
    const note='SPHEREx coordinates are offset from the real UCD position',field=$('comments');
    if(!field.value.includes(note))field.value+=`${field.value&&!field.value.endsWith('\n')?'\n':''}${note}`;
  }
  function addNearbyVisibility(row,item){
    const status=document.createElement('span');status.dataset.nearbyOid=String(item.moca_oid);
    row.appendChild(status);
  }
  function renderNearbyVisibility(){
    for(const status of $('nearby-known').querySelectorAll('[data-nearby-oid]')){
      status.textContent=activeEntry?.nearbyVisibility?.get(status.dataset.nearbyOid)===true?' · Outside WiseView cutout':'';
    }
  }
  // The sandboxed frame has an opaque origin: authenticate by its live window.
  window.addEventListener('message',event=>{
    if(event.data?.kind!=='nearby-marker-visibility'||!Array.isArray(event.data.items))return;
    const entry=[activeEntry,...preloads.values()].find(item=>item&&!item.disposed&&item.element?.contentWindow===event.source);
    if(!entry)return;
    entry.nearbyVisibility=new Map(event.data.items.slice(0,256)
      .filter(item=>Number.isInteger(item?.moca_oid)&&typeof item.outside==='boolean')
      .map(item=>[String(item.moca_oid),item.outside]));
    if(entry===activeEntry)renderNearbyVisibility();
  });
  function renderNearbyWarnings(){
      const {matches,alerts}=nearbyLists(current),warning=$('nearby-known');
      warning.replaceChildren();warning.hidden=!matches.length&&!alerts.length;
      if(matches.length){const title=document.createElement('strong');title.textContent='Known spectroscopic L0+ within 50″';warning.appendChild(title);
        for(const item of matches){const row=document.createElement('div');row.textContent=`OID ${item.moca_oid}${item.designation?' · '+item.designation:''} · ${Number(item.separation_arcsec).toFixed(1)}″ · ${item.spectral_type} · moca_pid: ${item.moca_pid||'—'} · origin: ${item.origin||'—'} · BYW: ${item.in_byw?'yes':'no'}`;addNearbyVisibility(row,item);warning.appendChild(row);}
      }
      if(alerts.length){
        const title=document.createElement('strong');
        title.textContent='Nearby UCD candidates and claimed objects';
        const group=document.createElement('div');
        group.appendChild(title);
        for(const item of alerts){
          const sources=[['ucd_candidate','UCD candidate'],['yadu','Yadu claim'],['byw','BYW claim'],['azul','Azul claim'],['smdet','SMDET']]
            .filter(([field])=>item[field]).map(([,label])=>label);
          const row=document.createElement('div');
          row.textContent=`OID ${item.moca_oid}${item.designation?' · '+item.designation:''} · ${Number(item.separation_arcsec).toFixed(1)}″${item.spectral_type?' · '+item.spectral_type:''} · ${sources.join(', ')}`;
          addNearbyVisibility(row,item);group.appendChild(row);
        }
        warning.appendChild(group);
      }
      renderNearbyVisibility();
      const primaryOid=duplicatePrimaryOid();
      if(primaryOid!==null){
        const choice=document.createElement('div');
        choice.textContent=`[U] marks this target as a duplicate of OID ${primaryOid}.`;
        warning.appendChild(choice);
      }
  }
  function duplicatePrimaryOid(){
    const {matches,alerts}=nearbyLists(current);
    if(matches.length)return Math.min(...matches.map(item=>Number(item.moca_oid)));
    const primary=alerts.find(item=>item.ucd_candidate&&!item.already_duplicate);
    return primary?Number(primary.moca_oid):null;
  }
  function buttons(){
    for(const btn of document.querySelectorAll('#classes button'))btn.disabled=!canWrite||!current||working;
    for(const name of ['first','prev','next','last','open-wise','open-report','open-astrometry','undo','coordinate-offset-comment']) $(name).disabled=!current||working;
    $('position').disabled=!total||working;
    $('position').setAttribute('aria-label',`${total?index+1:0} of ${total}; jump to queue position [J]`);
    $('declare-duplicate').disabled=!canWrite||working||duplicatePrimaryOid()===null;
    $('load').disabled=working;$('review-mode').disabled=working;
    renderSpectralSelection();
    renderCutoutSelection();
    if(!canWrite){$('undo').disabled=true;for(const btn of document.querySelectorAll('.spectral-choices button,#cutout-classes button'))btn.disabled=true;}
  }
  const laneName=lane=>({spiff:'SPIFF',spiffstacker:'SPIFFStacker',sublimeaperture:'SUBLIME aperture'}[lane]||lane);
  const spectralLanes=['spiffstacker','spiff','sublimeaperture'];
  const laneColors={spiffstacker:'red',spiff:'#2563eb',sublimeaperture:'#d020ff'};
  function buildSpectralSections(){
    const container=$('spectral-sections');container.replaceChildren();
    for(const [i,lane] of spectralLanes.entries()){
      if(!loadedSpectra[lane])continue;
      const section=document.createElement('section');section.className='panel spectral-classify';section.dataset.lane=lane;
      section.style.setProperty('--lane-color',laneColors[lane]);
      section.innerHTML=`<div class="panel-head"><div><h3>${laneName(lane)} · Spectral classification · optional</h3><p id="spectral-label-${lane}"></p></div><div class="spectral-actions"><button type="button" class="spectral-focus">Use shortcuts [Ctrl+Shift+${i+1}]</button><button type="button" class="spectral-clear">Clear choice</button></div></div><p id="spectral-pending-${lane}" class="hint" role="status" aria-live="polite"></p><div id="spectral-classes-${lane}" class="class-grid spectral-choices"></div>`;
      section.querySelector('.spectral-focus').onclick=()=>focusSpectral(lane);
      section.querySelector('.spectral-clear').onclick=()=>clearSpectral(lane);
      const ordered=[...spectralOptions.filter(item=>item[0]!=='bad'),...spectralOptions.filter(item=>item[0]==='bad')];
      for(const [classification,key,label] of ordered){
        const button=document.createElement('button');button.type='button';button.dataset.classification=classification;
        const shortcut=document.createElement('span');shortcut.className='key';shortcut.textContent=`[Shift+${key.toUpperCase()}]`;
        const saved=document.createElement('span');
        saved.className='spectral-saved-badge';saved.textContent='Saved';saved.hidden=true;
        button.append(shortcut,document.createTextNode(label.replaceAll('_',' ')),saved);
        button.onclick=()=>chooseSpectral(classification,lane);section.querySelector('.spectral-choices').appendChild(button);
      }container.appendChild(section);
    }
    renderSpectralSelection();
  }
  function focusSpectral(lane){if(!working&&loadedSpectra[lane]){activeSpectralLane=lane;renderSpectralSelection();}}
  function renderSpectralSelection(){
    for(const section of $('spectral-sections').querySelectorAll('.spectral-classify')){
      const lane=section.dataset.lane,choice=pendingSpectral[lane],existing=current?.spectral_vetting?.[lane]?.classification;
      section.classList.toggle('shortcut-active',activeSpectralLane===lane);
      $('spectral-label-'+lane).textContent=`Current spectral label: ${existing||'unclassified'} · spectrum ${loadedSpectra[lane]?.specid}`;
      $('spectral-pending-'+lane).textContent=choice?`${choice.classification.replaceAll('_',' ')} selected. Saves with your next motion decision.`:'No spectral change selected. Choose a label, then press a motion button to save.';
      for(const button of section.querySelectorAll('.spectral-choices button')){
        const selected=button.dataset.classification===choice?.classification;
        const saved=button.dataset.classification===existing;
        button.classList.toggle('saved',saved);
        button.querySelector('.spectral-saved-badge').hidden=!saved;
        button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));
        button.disabled=!current||working||!loadedSpectra[lane];
      }
      const focus=section.querySelector('.spectral-focus');focus.disabled=working;
      focus.setAttribute('aria-pressed',String(activeSpectralLane===lane));
      section.querySelector('.spectral-clear').disabled=working||!choice;
    }
  }
  function chooseSpectral(classification,lane=activeSpectralLane){
    if(!current||working||!loadedSpectra[lane])return;
    activeSpectralLane=lane;
    if(pendingSpectral[lane]?.classification===classification)delete pendingSpectral[lane];
    else pendingSpectral[lane]={classification,lane,specid:loadedSpectra[lane].specid};
    renderSpectralSelection();
  }
  function clearSpectral(lane=null){if(lane)delete pendingSpectral[lane];else pendingSpectral={};renderSpectralSelection();}
  async function loadSpectralOptions(){
    try{const data=await api('spectral-options');spectralOptions=data.options;buildSpectralSections();
      const ready=Array.isArray(data.queue_orders)&&['pm_sig_bins','spt_desc','spt_asc','oid_asc','oid_desc'].every(key=>data.queue_orders.includes(key));
      $('queue-order').disabled=!ready;
      $('queue-order-hint').textContent=ready?'Default: |gb| >15°, then 10° < |gb| ≤15°, then |gb| ≤10°. Within each latitude group: PM significance >10, 5–10, 1–<5, then <1 or unavailable; earliest adopted subtype first within each PM band. Missing latitude goes last. Load queue to apply.':'Restart WiseView to enable queue ordering.';
    }
    catch(e){message('Spectral choices unavailable: '+e.message,true);}
  }
  function renderCutoutSelection(){
    $('cutout-classify').hidden=activeMode!=='sublime';
    const n=cutouts.length;
    $('cutout-scope').textContent=n?`Applies to all ${n} available cutout path${n===1?'':'s'} shown for this target.`:'No cutouts loaded for this target.';
    $('cutout-pending').textContent=n&&!cutoutStorageReady?'Per-cutout storage requires the database migration.':pendingCutout
      ? `${pendingCutout.label} selected for ${n} cutout${n===1?'':'s'}. Saves with your next motion decision.`
      : 'No cutout change selected. Choose a label, then press a motion button to save.';
    for(const button of $('cutout-classes').querySelectorAll('button')){
      const selected=button.dataset.key===pendingCutout?.key;
      button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));
      button.disabled=working||!current||!n||!cutoutStorageReady;
    }
    $('cutout-clear').disabled=working||!pendingCutout;
    $('cutout-reviews').replaceChildren();
    for(const [i,image] of cutouts.entries()){
      const row=document.createElement('div'),path=document.createElement('code'),saved=document.createElement('span');
      path.textContent=image.cutout_path;saved.textContent=' · saved: '+(image.vetting?.classification||'unclassified');
      row.append(document.createTextNode(`Cutout ${i+1} · `),path,saved);$('cutout-reviews').appendChild(row);
    }
  }
  function chooseCutout(key){
    if(!current||working||activeMode==='redmovers'||!cutouts.length||!cutoutStorageReady)return;
    const choice=cutoutOptions.find(item=>item[0]===key);if(!choice)return;
    pendingCutout=pendingCutout?.key===key?null:{key,label:choice[1],paths:cutouts.map(image=>image.cutout_path)};
    renderCutoutSelection();
  }
  function clearCutout(){pendingCutout=null;renderCutoutSelection();}
  async function loadCutoutOptions(){
    try{const data=await api('cutout-options');cutoutOptions=data.options;
      for(const [key,label] of cutoutOptions){const button=document.createElement('button');button.type='button';button.dataset.key=key;
        const shortcut=document.createElement('span');shortcut.className='key';shortcut.textContent=`[Alt+${key.toUpperCase()}]`;
        button.append(shortcut,document.createTextNode(label));button.onclick=()=>chooseCutout(key);$('cutout-classes').appendChild(button);
      }renderCutoutSelection();
    }catch(e){$('cutout-pending').textContent='Cutout choices unavailable: '+e.message;}
  }
  function preserveReviewLayout(){
    // Do not let temporary loading placeholders shorten the page underneath
    // the reviewer: browsers otherwise clamp the scroll position upward.
    for(const selector of ['.objectbar','.review-grid']){
      const element=document.querySelector(selector);
      if(element){const height=element.getBoundingClientRect().height;if(height)element.style.minHeight=`${height}px`;}
    }
  }
  function resetReviewLayout(){
    for(const selector of ['.objectbar','.review-grid']){
      const element=document.querySelector(selector);if(element)element.style.minHeight='';
    }
  }
  function clearTarget(){
    preserveReviewLayout();
    renderAdoptedProperMotion();
    pendingSpectral={};loadedSpectra={};activeSpectralLane=null;buildSpectralSections();pendingCutout=null;cutoutStorageReady=false;
    $('object-title').textContent='No target selected';
    $('object-origin').textContent='';$('coordinate-source').textContent='';
    spectrumSerial++;current=null;frameUrl='';$('known-type').hidden=true;$('nearby-known').hidden=true;$('nearby-known').replaceChildren();cutouts=[];
    disposeEntry(activeEntry);activeEntry=null;$('frame-placeholder').style.display='flex';
    $('plot').innerHTML='';$('spectrum-message').style.display='flex';$('spectrum-message').textContent='Loading spectrum…';buttons();
  }
  async function loadQueue(){
    if(working)return;working=true;buttons();resetPreloads();resetReviewLayout();clearTarget();$('object-title').textContent='Preparing queue';$('object-ident').textContent='';$('object-w2').textContent='';
    try{
      const filters=filterValues();
      activeMode=$('review-mode').value;await api('queue',{filters,mode:activeMode});message('Loading candidates and applying filters…');
      let status;do{await pause(700);status=await api('status');}while(status.state==='loading');
      if(status.state==='error')throw new Error(status.error);
      total=status.total;index=status.start||0;$('position').textContent=`${total?index+1:0} / ${total}`;
      const missing=status.gaia_cache_missing?` ${status.gaia_cache_missing.toLocaleString()} objects excluded because their Gaia counts are missing or stale.`:'';
      if(!total){$('object-title').textContent='No matching candidates';message('No objects match these filters.'+missing);}
      else{message(`${total.toLocaleString()} candidates ready.`+missing);working=false;await show(index);return;}
    }catch(e){$('object-title').textContent='Queue unavailable';message(e.message,true);}
    finally{working=false;buttons();}
  }
  async function loadCutouts(seq,entry){
    try{
      const data=await entry.cutouts;
      if(seq!==serial)return;
      cutouts=(data.images||[]).filter(image=>image.data);
      cutoutStorageReady=data.per_path_ready===true;
      renderCutoutSelection();
    }catch(e){if(seq===serial&&e.name!=='AbortError')renderCutoutSelection();}
  }
  async function loadSpectrum(seq,entry=null){
    const request=++spectrumSerial;
    const outdated=()=>seq!==serial||request!==spectrumSerial;
    preserveReviewLayout();loadedSpectra={};activeSpectralLane=null;buildSpectralSections();
    $('spectrum-message').style.display='flex';$('spectrum-message').textContent='Rebuilding all available spectra and fitting their best templates…';$('plot').innerHTML='';
    try{const load=entry?entry.spectrum.catch(()=>api('spectra',{index:entry.index},entry.controller.signal)):api('spectra',{index},previewController.signal);
      const data=await load;if(outdated())return;
      if(data.version!==1)throw new Error('Restart the reviewer to activate the three-lane spectrum API');
      const available=Object.fromEntries(spectralLanes.filter(lane=>data.spectra[lane]?.specid&&!data.spectra[lane].missing&&!data.spectra[lane].error).map(lane=>[lane,data.spectra[lane]]));
      const errors=spectralLanes.filter(lane=>data.spectra[lane]?.error).map(lane=>laneName(lane)+': '+data.spectra[lane].error);
      if(!Object.keys(available).length){$('spectrum-message').textContent=errors.join(' · ')||'No non-ignored spectra in any lane.';return;}
      if(!window.Plotly||!window.SpherexReviewPlot)throw new Error('Spectrum renderer unavailable');
      const fig=window.SpherexReviewPlot.laneStackFigure(available,String(current?.moca_oid||index),$('plot').clientWidth||600);
      fig.layout.height=Math.round(fig.layout.height*0.75);
      const graph=document.createElement('div');$('plot').replaceChildren(graph);
      await Plotly.react(graph,fig.traces,fig.layout,{responsive:true,displaylogo:false});if(outdated())return;
      $('spectrum-message').style.display=errors.length?'flex':'none';$('spectrum-message').textContent=errors.join(' · ');
      loadedSpectra=available;activeSpectralLane=Object.keys(available)[0];buildSpectralSections();
    }catch(e){if(outdated()||e.name==='AbortError')return;$('spectrum-message').textContent='Spectra unavailable: '+e.message;}
  }
  function renderAdoptedProperMotion(pm={}){
    const {pmtot_masyr:total,pmtot_masyr_unc:uncertainty,pmra_masyr:ra,pmdec_masyr:dec}=pm;
    const source=pm.moca_pid?.trim()||pm.mission_name?.trim();
    const errorText=Number.isFinite(uncertainty)?` ± ${Number(uncertainty.toPrecision(2))}`:'';
    const sourceText=source?` · ${source}`:'';
    for(const [id,label,value,error='',reference=''] of [
      ['adopted-pm','Adopted total PM',total,errorText,sourceText],['adopted-pmra','PMRA',ra],['adopted-pmdec','PMDec',dec]
    ]){
      const line=$(id);
      line.hidden=!Number.isFinite(value);
      line.textContent=line.hidden?'':`${label} ${value.toFixed(1)}${error} mas/yr${reference}`;
    }
  }
  async function show(target){
    if(!total||working)return; index=Math.max(0,Math.min(total-1,target));serial++;const seq=serial;
    const entry=takeEntry(index);clearTarget();activeEntry=entry;previewController=entry.controller;$('position').textContent=`${index+1} / ${total}`;
    $('object-title').textContent='Loading target…';
    try{
      const data=await entry.object.catch(()=>api('object',{index:entry.index},entry.controller.signal));if(seq!==serial)return;current=data.object;
      const details=current.adopted_type_details||{};
      const adopted=current.adopted_spectral_type?.trim();
      const name=current.designation||`Object ${current.moca_oid}`;
      const types=current.heading_spectral_types ?? (adopted?[{...details,spectral_type:adopted}]:[]);
      const labels=types.map(row=>{
        const reference=row.moca_pid?.trim()||row.origin?.trim();
        return row.spectral_type+(reference?` (${reference})`:'');
      });
      $('object-title').textContent=[name,...labels].join(' · ');
      const sampleType=activeMode==='public_ucd' ? current.public_adopted_spectral_type : activeMode==='sublime' ? current.sublime_autotype_spectral_type : '';
      $('object-ident').textContent=`OID ${current.moca_oid} · RA ${current.ra_deg.toFixed(6)} · Dec ${current.dec_deg.toFixed(6)}${sampleType?' · type '+sampleType:''}`;
      $('object-origin').textContent='Object origin: '+(current.object_origin?.trim()||'—');
      const coordinates=current.adopted_coordinates||{};
      const coordinateSource=coordinates.moca_pid?.trim()||coordinates.origin?.trim();
      const coordinateMission=[coordinates.mission_name,coordinates.data_release].map(value=>String(value??'').trim()).filter(Boolean).join(' ');
      $('coordinate-source').textContent='Adopted coordinates: '+[coordinateSource,coordinateMission].filter(Boolean).join(' · ');
      if(!coordinateSource&&!coordinateMission)$('coordinate-source').textContent='Adopted coordinates: source unavailable';
      const w2=current.wise_w2mag;$('object-w2').textContent=`W2 ${w2==null?'—':Number(w2).toFixed(3)}`;$('object-w2').title=w2==null?'No adopted W2 magnitude':`Adopted W2: ${w2}`;
      renderAdoptedProperMotion(current.adopted_pm);
      const spn=details.spectral_type_number;
      const auto=String(details.calculation_method||'').toLowerCase().includes('autotype');
      const label=spn!=null&&spn>=10 ? (auto?'Adopted L0+ · automatic type':details.photometric_estimate?'Adopted L0+ · photometric estimate':'Known L0+ · adopted spectral type') : current.adopted_spectral_type ? 'Adopted spectral type' : 'No adopted spectral type';
      const block=$('known-type');block.replaceChildren();const headline=document.createElement('strong');headline.textContent=label+': '+(current.adopted_spectral_type||'—');block.appendChild(headline);
      const meta=document.createElement('div');meta.className='line';meta.textContent='moca_pid: '+(details.moca_pid||'—')+' · type origin: '+(details.origin||'—')+' · method: '+(details.calculation_method||'—');block.appendChild(meta);block.hidden=false;
      const nearby=document.createElement('div');nearby.className='line';
      const other1=current.nearby_nonsublime_100arcsec_count, other2=current.nearby_sublime_100arcsec_count, l0=current.mocadb_l0plus_100arcsec_count;
      nearby.textContent=other1==null||other2==null?'Nearby MOCAdb entries within 100″: unavailable':`Within 100″: ${other1+other2} other active MOCAdb entries · ${l0==null?'?':l0} with adopted L0+ types`;
      block.appendChild(nearby);
      const gaia=document.createElement('div');gaia.className='line';gaia.textContent=`Gaia DR3 within 30″: ${current.gaia_neighbors_30==null?'not yet cached':current.gaia_neighbors_30+' sources (matched source excluded)'}`;block.appendChild(gaia);
      renderNearbyWarnings();

      $('comments').value=current.comments||'';buttons();
      entry.frame.then(d=>{
        if(seq!==serial)return;
        frameUrl=d.url;
        d.element.style.display='block';
        $('frame-placeholder').style.display='none';
        if(entry.mode!=='redmovers')d.element.contentWindow?.postMessage({kind:'sublime-cutout-active'},'*');
      }).catch(e=>{if(seq===serial&&e.name!=='AbortError')$('frame-placeholder').textContent='WiseView unavailable: '+e.message;});
      if(activeMode!=='redmovers')loadCutouts(seq,entry);loadSpectrum(seq,entry);
      schedulePreloads();
    }catch(e){if(seq!==serial||e.name==='AbortError')return;$('object-title').textContent='Target unavailable';message(e.message,true);}
  }
  function openQueueJump(){
    if(!total||working)return;
    $('jump-range').textContent=`Choose a position from 1 to ${total.toLocaleString()}.`;
    $('jump-position').max=String(total);$('jump-position').value=String(index+1);
    $('jump-error').hidden=true;
    $('jump-dialog').showModal();$('jump-position').focus();$('jump-position').select();
  }
  function submitQueueJump(event){
    event.preventDefault();
    const value=Number($('jump-position').value);
    if(!Number.isSafeInteger(value)||value<1||value>total){
      $('jump-error').textContent=`Enter a whole number from 1 to ${total.toLocaleString()}.`;
      $('jump-error').hidden=false;$('jump-position').focus();return;
    }
    $('jump-dialog').close();
    if(value!==index+1)show(value-1);
  }
  async function classify(key){
    if(!current||working)return;working=true;buttons();const currentIndex=index;
    try{const body={index:currentIndex,key,comments:$('comments').value};
      if(Object.keys(pendingSpectral).length)body.spectral_reviews=Object.values(pendingSpectral);
      if(pendingCutout)Object.assign(body,{cutout_key:pendingCutout.key,cutout_paths:pendingCutout.paths});
      const result=await api('classify',body);message(`Saved “${result.saved}”${(result.spectral_saved_reviews||[]).map(choice=>` + “${choice.classification}” (${laneName(choice.lane)})`).join('')}${result.cutouts_saved?` + ${result.cutouts_saved} cutout review${result.cutouts_saved===1?'':'s'}`:''} for OID ${result.oid}.`);refreshStats();working=false;if(currentIndex<total-1)await show(currentIndex+1);else await show(currentIndex);}
    catch(e){message('Could not save: '+e.message,true);}finally{working=false;buttons();}
  }
  async function declareDuplicate(){
    const primaryOid=duplicatePrimaryOid();
    if(working||primaryOid===null)return;
    working=true;buttons();const currentIndex=index;
    try{const result=await api('duplicate',{index:currentIndex,primary_oid:primaryOid,comments:$('comments').value,include_sublime_neighbors:$('include-sublime-neighbors').checked});
      message(`Saved duplicate: OID ${result.oid} is a duplicate of OID ${result.primary_oid}.`);refreshStats();
      working=false;if(currentIndex<total-1)await show(currentIndex+1);else await show(currentIndex);
    }catch(e){message('Could not save duplicate: '+e.message,true);}finally{working=false;buttons();}
  }
  async function undo(){
    if(working)return;working=true;buttons();try{const data=await api('undo');message(`Undid classification for OID ${data.oid}.`);refreshStats();working=false;await show(data.index);}catch(e){message(e.message,true);}finally{working=false;buttons();}
  }
  for(const [key,label] of classes){const b=document.createElement('button');b.type='button';if(key==='m'){b.className='miscentered';b.hidden=true;}b.innerHTML=`<span class="key">[${key}]</span>${label}`;b.onclick=()=>classify(key);$('classes').appendChild(b);}
  function updateSpectralTypeControls(){
    const form=$('filter-form'),red=$('review-mode').value==='redmovers',stacker=form.use_spiffstacker_types.checked;
    $('spt-range').hidden=red&&!stacker;
    for(const el of $('spt-range').querySelectorAll('input'))el.disabled=red&&!stacker;
    $('spt-filter-hint').textContent=stacker?'Type bounds use active SPIFFStacker autotypes; objects without one are excluded when a bound is set.':red?'Enable SPIFFStacker types to filter CatWISE by spectral type.':$('review-mode').value==='public_ucd'?'Type bounds use the public-adopted photometric type.':'Type bounds use the latest SUBLIME2 autotype.';
  }
  let otherSampleFilters=null;
  function setMode(mode){
    const form=$('filter-form'), red=mode==='redmovers', publicUcd=mode==='public_ucd';
    const fields=Array.from(form.elements).filter(el=>el.name);
    if(publicUcd && !otherSampleFilters){
      otherSampleFilters=fields.map(el=>{
        const prop=el.type==='checkbox'?'checked':'value';
        return [el,prop,el[prop]];
      });
      form.reset();
      $('review-mode').value=mode;
      form.lane.value='spiffstacker';
      form.reclass.checked=true;
      form.no_known.checked=false;
      form.use_spiffstacker_types.checked=false;
      form.claim_mode.value='all';
      form.byw_mode.value=form.duplicate_mode.value='either';
      for(const name of ['min_w2','max_w2','spectral_type_number_max','any_lane_include','median_snr','chi2_max'])
        form.elements[name].value='';
    }else if(!publicUcd && otherSampleFilters){
      for(const [el,prop,value] of otherSampleFilters)el[prop]=value;
      otherSampleFilters=null;
    }
    if(red){if(form.source_table.value!== 'pcat_catwise2020_red_movers'){sublimeSource=form.source_table.value;sublimeLane=form.lane.value;}form.source_table.value='pcat_catwise2020_red_movers';form.lane.value='spiffstacker';}
    else if(form.source_table.value==='pcat_catwise2020_red_movers'){form.source_table.value=sublimeSource;form.lane.value=sublimeLane;}
    form.source_table.readOnly=red;
    form.source_table.disabled=publicUcd;
    $('source-table-label').hidden=publicUcd;
    $('public-ucd-hint').hidden=!publicUcd;
    $('sublime2-filters').hidden=red||publicUcd;
    updateSpectralTypeControls();
    $('exclude-spectrum-review-label').hidden=!red;
    for(const el of $('sublime2-filters').querySelectorAll('input'))el.disabled=red||publicUcd;
    $('cutout-classify').hidden=red;
    $('decision-table').textContent=red?'CatWISE motion decisions save to pcat_wiseview_visual_vetting. SPIFF spectral-quality vettings are separate.':'Saves motion decisions to pcat_wiseview_visual_vetting.';
    form.lane.querySelector('option[value="sublimeaperture"]').hidden=red;
    document.querySelector('#classes .miscentered').hidden=true;
  }
  $('review-mode').onchange=()=>{serial++;resetPreloads();clearTarget();resetReviewLayout();total=0;index=0;$('position').textContent='0 / 0';$('object-title').textContent='No target selected';$('object-ident').textContent='';$('object-w2').textContent='';setMode($('review-mode').value);refreshStats();refreshGaiaCache();message('Sample changed. Load a queue to begin.');};
  $('filter-form').use_spiffstacker_types.onchange=updateSpectralTypeControls;
  $('filter-form').lane.onchange=()=>{if($('review-mode').value==='redmovers')refreshStats();};
  $('load').onclick=loadQueue;$('reset').onclick=()=>{otherSampleFilters=null;$('filter-form').reset();$('review-mode').onchange();};$('filters-toggle').onclick=()=>document.querySelector('main').classList.toggle('no-filters');
  $('declare-duplicate').onclick=declareDuplicate;
  $('coordinate-offset-comment').onclick=appendCoordinateOffsetComment;
  $('show-wise-crosshairs').onchange=$('show-wise-pm').onchange=$('show-wise-nearby').onchange=()=>{
    for(const frame of $('wise-pool').children)syncWiseOverlays(frame);
  };
  $('include-sublime-neighbors').onchange=()=>{
    renderNearbyWarnings();buttons();
    for(const frame of $('wise-pool').children)syncWiseOverlays(frame);
    for(const entry of [activeEntry,...preloads.values()]){
      if(!entry||entry.disposed||!entry.started)continue;
      Promise.all([entry.frame,entry.object]).then(([frame,data])=>{
        if(!entry.disposed)syncNearbyMarkers(frame.element,data.object);
      }).catch(()=>{});
    }
  };
  $('first').onclick=()=>show(0);$('prev').onclick=()=>show(index-1);$('next').onclick=()=>show(index+1);$('last').onclick=()=>show(total-1);$('undo').onclick=undo;
  $('position').onclick=openQueueJump;$('jump-form').onsubmit=submitQueueJump;
  $('jump-cancel').onclick=()=>$('jump-dialog').close();
  $('jump-position').oninput=()=>{$('jump-error').hidden=true;};
  $('cutout-clear').onclick=clearCutout;
  $('open-report').onclick=()=>{if(current)window.open(`https://mocadb.ca/search/results?search-query=oid%28${current.moca_oid}%29&search-type=star`,'_blank','noopener,noreferrer');};
  $('open-astrometry').onclick=()=>{
    if(current)window.open(`/js/astrometry?moca_oid=${encodeURIComponent(current.moca_oid)}#`+new URLSearchParams({user:auth['X-MOCA-User'],pwd:auth['X-MOCA-Password'],dbase:auth['X-MOCA-Database']}),'_blank','noopener,noreferrer');
  };
  $('open-wise').onclick=()=>{if(current&&frameUrl){const hash=frameUrl.includes('#')?frameUrl.slice(frameUrl.indexOf('#')):'';window.open('http://byw.tools/wiseview-v2'+hash,'_blank','noopener,noreferrer');}};
  document.addEventListener('keydown',e=>{
    if($('jump-dialog').open)return;
    const typing=e.target.matches('input,textarea,select,[contenteditable="true"]');
    if(!e.ctrlKey&&!e.metaKey&&!e.altKey&&(e.key==='*'||(e.shiftKey&&e.code==='Digit8')||e.code==='NumpadMultiply')&&(!typing||e.target===$('comments'))){
      e.preventDefault();if(!e.repeat)appendCoordinateOffsetComment();return;
    }
    if(typing)return;
    const key=e.key.toLowerCase();if(e.ctrlKey||e.metaKey){if(e.shiftKey&&/^Digit[123]$/.test(e.code)){e.preventDefault();focusSpectral(spectralLanes[Number(e.code.slice(-1))-1]);return;}if(key==='z'){e.preventDefault();undo();}return;}
    if(key==='escape'){e.preventDefault();if(!e.altKey)clearSpectral(e.shiftKey?activeSpectralLane:null);if(!e.shiftKey)clearCutout();return;}
    if(e.altKey&&!e.shiftKey){const cutoutKey=e.code.replace(/^(?:Digit|Numpad|Key)/,'').toLowerCase();
      if(cutoutOptions.some(item=>item[0]===cutoutKey)){e.preventDefault();chooseCutout(cutoutKey);return;}}
    if(e.altKey)return;
    if(key==='a'&&!e.shiftKey){e.preventDefault();if(!e.repeat)$('open-astrometry').click();return;}
    if(e.shiftKey&&!e.altKey){const spectralKey=e.code.replace(/^(?:Digit|Numpad|Key)/,'').toLowerCase(),choice=spectralOptions.find(item=>item[1]===spectralKey);
      if(choice){e.preventDefault();chooseSpectral(choice[0]);return;}}
    if(key!=='m'&&classes.some(c=>c[0]===key)){e.preventDefault();classify(key);return;}
    const actions={j:openQueueJump,u:declareDuplicate,arrowleft:()=>show(index-1),arrowup:()=>show(index-1),arrowright:()=>show(index+1),arrowdown:()=>show(index+1),home:()=>show(0),end:()=>show(total-1),backspace:undo,o:()=>$('open-report').click(),w:()=>$('open-wise').click(),q:()=>{serial++;resetPreloads();clearTarget();message('Review closed. Load a queue to start again.');}};
    if(actions[key]){e.preventDefault();actions[key]();}
  });updateSpectralTypeControls();buttons();loadSpectralOptions();loadCutoutOptions();refreshStats();refreshGaiaCache();setInterval(refreshStats,60000);setInterval(refreshGaiaCache,30000);
})();
