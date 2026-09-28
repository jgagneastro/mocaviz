'use strict';
const $=id=>document.getElementById(id),G=GNIRSLogic,L=PlotLogic;
let currentMode=new URLSearchParams(location.search).get('mode')==='sxd'?'sxd':'rv';
const modeFilters={},isSxd=()=>currentMode==='sxd',modeInfo=()=>isSxd()?G.SXD.MODES:G.MODES;
const modeDefaults=()=>state.data?.mode_defaults?.[currentMode]||G.DEFAULTS;
const aidDefault=value=>isSxd()||G.defaultAidSelected(value),observableDefault=value=>isSxd()||G.defaultObservableSelected(value);
const snrDescription=f=>`S/N ≥${f.snr}/${f.snrUnit==='resolution'?'resolution element':'pixel'} over ≥${Math.round(f.coverageFraction*100)}% of ${isSxd()?'1.20–1.30 µm':'all recorded pixels (disjoint allowed)'}`;
const fmt=(x,n=2)=>!G.finite(x)?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:n,minimumFractionDigits:n});
const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hours=x=>G.finite(x)?`${fmt(x/3600)} h`:'unknown';
const PROPOSAL_TIERS=[{key:'snapshot',label:'Snapshot',below:5},{key:'focused',label:'Focused',below:10},{key:'broad',label:'Broad',below:20},{key:'large',label:'Large',below:40},{key:'very-large',label:'Very large',below:Infinity}];
function renderProposalSize(total,count){
  const box=$('proposal-size'),known=total.program/3600,missing=total.unknown||0;
  if(!count){box.dataset.tier='none';$('proposal-tier').textContent='No targets selected';$('proposal-hours').textContent='';$('proposal-size-note').textContent='Select targets to estimate a proposal size.';box.setAttribute('aria-label','CanTAC GNIRS proposal planning scale: no targets selected');return;}
  const tier=PROPOSAL_TIERS.find(t=>known<t.below);
  const share=Math.round(known/161*100);
  box.dataset.tier=missing&&tier.key!=='very-large'?'unknown':tier.key;
  $('proposal-tier').textContent=missing?`${tier.key==='very-large'?'At least very large':'Size uncertain'}`:tier.label;
  $('proposal-hours').textContent=`${missing?'At least ':''}${fmt(known,1)} h program time${missing?` · ${missing} target${missing===1?'':'s'} untimed`:''}`;
  $('proposal-size-note').textContent=`Planning bands, not CanTAC limits · ≈${share}% of Canada's 161 h Gemini North allocation (all instruments)${missing?' · timing incomplete':''} · PIT adds baseline calibrations.`;
  box.setAttribute('aria-label',`CanTAC GNIRS proposal planning scale: ${$('proposal-tier').textContent}; ${$('proposal-hours').textContent}. Snapshot below 5 hours, focused from 5 to 10, broad from 10 to 20, large from 20 to 40, very large from 40 hours. These are illustrative, not official CanTAC categories.`);
}
const spt=G.sptLabel,key=r=>String(r.moca_oid);
const DEFAULT_LIMITS={xmin:5,xmax:2000,ymin:200,ymax:2600},DEFAULT_SPT_LIMITS={ymin:9.5,ymax:34.5};
const LT_TRANSITION_MIN_K=1150,LT_TRANSITION_MAX_K=1250,LT_TRANSITION_EARLY_SPT=18,LT_TRANSITION_LATE_SPT=22;
const spectralYAxis=()=>$('y-axis').value==='spt',yField=()=>spectralYAxis()?'sptn':'teff';
const axisModes=()=>({xlog:$('xlog').checked,ylog:!spectralYAxis()&&$('ylog').checked});
function defaultView(){const {xlog,ylog}=axisModes();return {xmin:xlog?Math.log10(DEFAULT_LIMITS.xmin):DEFAULT_LIMITS.xmin,xmax:xlog?Math.log10(DEFAULT_LIMITS.xmax):DEFAULT_LIMITS.xmax,ymin:spectralYAxis()?-DEFAULT_SPT_LIMITS.ymax:ylog?Math.log10(DEFAULT_LIMITS.ymin):DEFAULT_LIMITS.ymin,ymax:spectralYAxis()?-(isSxd()?4.5:DEFAULT_SPT_LIMITS.ymin):ylog?Math.log10(isSxd()?3200:DEFAULT_LIMITS.ymax):(isSxd()?3200:DEFAULT_LIMITS.ymax)};}
const plotStyles=getComputedStyle(document.documentElement),OBS_COLORS=[0,1,2,3].map(n=>plotStyles.getPropertyValue(`--obs-${n}`).trim()||'#8b949e');
const observationCount=r=>['pm','plx','rv'].filter(k=>(r.observables||'').split('+').includes(k)).length;
const state={data:null,cacheReady:false,rows:[],active:null,screen:[],view:defaultView(),timings:new Map(),timingKey:null,windows:new Map()};
const youngPoints=()=>state.data?.spectral_type_axis?.points||[];
const approxTeff=n=>L.youngTeffForSpt(youngPoints(),n),approxSpt=t=>L.youngSptForTeff(youngPoints(),t);
function fitCurrent(){const {xlog,ylog}=axisModes();return L.fitView(state.rows,xlog,ylog,yField(),spectralYAxis())||defaultView();}
const controlSpecs=[];
function check(name,label){controlSpecs.push({name,type:'check'});return `<label class="check"><input id="${name}" name="${name}" type="checkbox">${label}</label>`;}
function number(name,label,min,max,step=1){controlSpecs.push({name,type:'number'});return `<label class="control" for="${name}">${label}<input id="${name}" name="${name}" type="number" min="${min}" max="${max}" step="${step}"></label>`;}
function select(name,label,options,wide=false){controlSpecs.push({name,type:'select'});return `<label class="${wide?'label-block':'control'}" for="${name}">${label}<select id="${name}" name="${name}" ${wide?'class="wide"':''}>${options.map(([v,l])=>`<option value="${v}">${esc(l)}</option>`).join('')}</select></label>`;}
function section(title,body,open=true){return `<details class="control-section" ${open?'open':''}><summary>${title}</summary>${body}</details>`;}
function createControls(){
  $('control-groups').innerHTML=
  section('RV status & membership',
    select('rvMode','Measured radial velocity',[['none','No measured RV (science)'],['measured','Measured RV available (references)'],['all','Either / all']])+
    check('referenceBypass','RV references bypass membership, UVW, association-distance and age cuts')+
    check('rvMaxErrorEnabled','Require RV uncertainty ≤ cutoff')+number('rvMaxError','RV uncertainty (km/s)',.01,100,.1)+
    '<p class="tiny">Direct, non-ignored RV measurements only. Host-derived RVs are shown separately. Precision alone does not establish RV stability.</p>'+
    check('membershipEnabled','Apply BANYAN probability threshold')+
    select('probKind','Probability',[['individual','Individual current association'],['summed','Sum over young associations']])+number('prob','Probability ≥ (%)',0,100,.1)+
    check('realAssociation','Require confirmed real association')+check('uncontaminated','Exclude highly contaminated associations')+
    check('associationDistanceEnabled','Limit association mean distance')+number('associationDistanceMax','Association distance ≤ (pc)',1,5000,10))+
  section('GNIRS setup & time',
    select('mode','Configuration and conditions',Object.entries(G.MODES).map(([k,v])=>[k,v.label]),true)+
    '<p id="setup-description" class="tiny"></p>'+
    select('rvCamera','RV camera',[['long','Long blue · 0.05″/pixel'],['short','Short blue · 0.15″/pixel']],true)+
    select('rvGrating','RV grating',[['111','111 l/mm'],['32','32 l/mm'],['10','10 l/mm · long blue only']],true)+
    '<p id="rv-camera-note" class="tiny" role="status"></p>'+
    select('rvBand','RV wavelength setting',[['auto','Automatic: K for L0–T2; J for T3+'],['j','J band · 1.30 µm'],['h','H band · 1.65 µm'],['k','K band · 2.30 µm']],true)+
    select('rvSlit','RV slit width',[['auto','Automatic: 0.15″ Band 1/2; 0.30″ Band 3'],...['0.1','0.15','0.2','0.3','0.45','0.675','1'].map(v=>[v,`${v}″`])],true)+
    '<p id="rv-coverage-description" class="tiny">S/N is per detector pixel. Some low-dispersion settings extend beyond the blocking filter and cannot meet the higher coverage fractions. Qualifying pixels may be disjoint; all recorded pixels count toward the required fraction. H timing uses J photometry and the Sonora model color.</p>'+
    number('snr','S/N threshold',5,300,5)+select('snrUnit','S/N units',[['resolution','Per resolution element (3 pixels)'],['pixel','Per detector pixel']])+
    select('coverageFraction','Pixels meeting S/N',[['0.25','At least 25%'],['0.5','At least 50%'],['0.75','At least 75%'],['0.9','At least 90%'],['0.95','At least 95%']])+
    select('airmass','ITC / window airmass',[['auto','Auto: 1.5, else 2.0'],['1.5','1.5'],['2','2.0']])+
    number('margin','Exposure multiplier',1,3,.05)+check('timeEnabled','Apply per-target time cutoff')+
    select('timeMetric','Cutoff applies to',[['science','Science integration'],['program','Charged program time'],['telescope','Total telescope time']])+number('maxScience','Time strictly below (h)',.05,100,.25)+
    check('excludeFastBand3','Exclude targets doable in Band 3 (0.30″) below this science-time limit')+
    '<p id="band3-description" class="tiny">Band 3 comparison uses the same wavelength setting, pixel fraction, S/N, airmass and exposure multiplier. Only the RV 0.30″ setup counts. This exclusion uses the hour limit even when the main science-time limit is off.</p>'+
    number('maxVisit','Maximum visit block (h)',.5,12,.25)+number('calibrationMinutes','Calibration allowance / visit (min)',0,60,5)+
    '<p class="tiny">Program = science + read/nod/recenter + acquisition. Telescope adds the provisional allowance. Enter program time in PIT; do not add this allowance again to PIT baseline calibrations.</p>')+
  section('2027A visibility',
    check('bestAirmassEnabled','Limit best attainable night-time airmass')+number('bestAirmass','Maximum best airmass',1,2.9,.05)+
    number('minWindow','Minimum continuous window (h)',0,12,.25)+check('requireVisitFit','Require all visits to fit available nights')+
    check('restrictDec','Apply North declination access (−37° to +90°)')+check('restrictRa','Apply published RA access (04h–01h)')+
    check('excludeRestrictedAccess','Exclude restricted-access targets')+
    '<p class="tiny">Every night, five-minute steps; astronomical darkness; April 12–29 closure excluded. The optional restricted-access cut removes RA 04–06h / 23–01h and declination −37° to −30° / +73° to +90° targets.</p>')+
  section('Spectral type & quality',
    number('sptMin','Earliest SpT (M5 = 5, L0 = 10)',5,35,.5)+number('sptMax','Latest SpT number (T0 = 20)',5,35,.5)+'<p id="spt-range" class="tiny"></p>'+
    check('excludePhotometricSpt','Exclude photometric spectral types')+select('quality','SpT quality',[['all','All qualities / unknown'],['ABC','A, B or C'],['AB','A or B'],['A','A only']])+
    check('manualTypesOnly','Literature/manual types only (no calculation method)')+check('ignoreMultiples','Exclude unresolved multiples (+ type)')+check('excludeSubdwarfs','Exclude subdwarf-like')+
    check('requireLowg','Require adopted lowg_like = 1')+check('conditionalLowg','Require lowg_like for early types at young ages')+
    number('lowgSpt','Conditional SpT ≤ number',5,35,.5)+number('lowgAge','Conditional age younger than (Myr)',1,1000,10)+check('excludeBadSpiff','Exclude rejected SPIFF photometric classifications'))+
  section('Age, temperature & distance',
    check('ageEnabled','Apply association-age range')+number('ageMin','Minimum age (Myr)',0,15000,1)+number('ageMax','Maximum age (Myr)',0,15000,10)+
    select('unknownAge','Unknown ages',[['include','Include'],['exclude','Exclude when age cut is on']])+
    check('teffEnabled','Apply effective-temperature range')+number('teffMin','Minimum Teff (K)',50,5000,50)+number('teffMax','Maximum Teff (K)',50,5000,50)+
    check('distanceEnabled','Limit target distance')+number('distanceMax','Distance ≤ (pc)',1,10000,10)+select('unknownDistance','Unknown distances',[['include','Include'],['exclude','Exclude when distance cut is on']])+
    check('excludePhotometricDistance','Exclude photometric distances'),false)+
  section('Kinematics, crowding & coverage',
    check('uvwEnabled','Apply regular UVW separation limit')+number('uvw','UVW ≤ (km/s)',.1,100,.1)+check('uvwLooseEnabled','Apply loose UVW separation limit')+number('uvwLoose','Loose UVW ≤ (km/s)',.1,100,.1)+
    check('rejectDuplicates','Reject likely duplicated MOCA entries')+number('hostMin','Minimum host separation (arcsec)',0,120, .1)+
    check('excludeArchive','Exclude any GNIRS data above R threshold')+number('archiveResolution','Archive resolving power ≥',100,100000,100)+check('excludePlanned','Exclude planned reductions with R ≥ 2700')+
    '<p class="tiny">NULL host separations pass. Archive and planned-reduction flags use the saved September audit, plus current MOCAdb spectra. A spectrum is not an RV measurement.</p>',false)+
  section('Manual OIDs','<label class="label-block" for="excludeOids">Exclude OIDs</label><input class="oid-input" id="excludeOids" type="text" placeholder="Comma or space separated"><label class="label-block" for="includeOids">Force include OIDs</label><input class="oid-input" id="includeOids" type="text" placeholder="Comma or space separated"><label class="label-block" for="bypassNoMeasuredRvOids">Bypass no-measured-RV status and membership selection (RV standards)</label><input class="oid-input" id="bypassNoMeasuredRvOids" type="text" placeholder="Comma or space separated"><p class="tiny">Exclusion wins. Force inclusion bypasses all selection cuts. RV standards bypass RV status and membership selection, including association checkboxes, BANYAN probability, UVW, age and association distance. Other cuts still apply.</p>',false);
  resetValues();
  let timer;for(const el of $('filter-form').querySelectorAll('input,select'))el.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(update,90);});
  $('filter-form').addEventListener('submit',e=>e.preventDefault());
}
function resetValues(values=modeDefaults()){for(const s of controlSpecs){const el=$(s.name),v=values[s.name];if(s.type==='check')el.checked=!!v;else el.value=v;}for(const id of ['includeOids','bypassNoMeasuredRvOids','excludeOids'])$(id).value=values[id].join(', ');}
function filters(){const f={...modeDefaults(),observingMode:currentMode};for(const s of controlSpecs){const el=$(s.name);f[s.name]=s.type==='check'?el.checked:s.type==='number'?Number(el.value):el.value;}f.coverageFraction=Number(f.coverageFraction);for(const id of ['includeOids','bypassNoMeasuredRvOids','excludeOids'])f[id]=G.parseOidList($(id).value);f.aids=[...$('aids').querySelectorAll('input:checked')].map(e=>e.value);f.observables=[...$('observables').querySelectorAll('input:checked')].map(e=>e.value);return f;}
function choices(id,values,prior){const fragment=document.createDocumentFragment();for(const value of values){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=value;input.checked=prior?prior.includes(value):(id==='aids'?aidDefault(value):observableDefault(value));input.onchange=update;label.append(input,document.createTextNode(value));const count=document.createElement('span');count.className='choice-count';label.append(count);fragment.append(label);}$(id).replaceChildren(fragment);}
function configureMode(){
  $('observing-mode').value=currentMode;document.body.dataset.observingMode=currentMode;
  $('refresh-sxd').hidden=true;
  const prior=$('mode').value;$('mode').innerHTML=Object.entries(modeInfo()).map(([k,v])=>`<option value="${k}">${esc(v.label)}</option>`).join('');$('mode').value=prior||'b12';
  $('snrUnit').disabled=!isSxd();$('snrUnit').closest('label').hidden=!isSxd();
  $('timeMetric').disabled=!isSxd();
  for(const id of ['rvCamera','rvGrating','rvBand','rvSlit'])$(id).closest('label').hidden=isSxd();
  $('rv-coverage-description').hidden=isSxd();
  $('rv-camera-note').hidden=isSxd();
  $('coverageFraction').innerHTML=(isSxd()?[.5,.75,.9]:[.25,.5,.75,.9,.95]).map(f=>`<option value="${f}">At least ${Math.round(f*100)}%</option>`).join('');
  for(const id of ['excludeFastBand3','referenceBypass'])$(id).closest('label').hidden=isSxd();
  $('band3-description').hidden=isSxd();
  updateSetupDescription();
}
function updateSetupDescription(){
  if(isSxd()){
    $('setup-description').textContent='32 l/mm · short-blue 0.15″/pixel · SXD 0.45″ × 7″ slit · 1.65 µm setting · 0.85–2.5 µm simultaneously. R ≈1070 in J, ≈1130 in H/K. Timing uses only J 1.20–1.30 µm; the S/N goal is not guaranteed over all orders. Natural seeing, SBAny. Queue band and weather are separate planning choices.';
    $('mode-summary').textContent='M5+ candidates · photometric + spectroscopic · independent selection and SXD timing';
  }else{
    const available=state.data?.grid?.camera_gratings||(state.data?{long:[111],short:[]}:null);
    if(available){
      for(const option of $('rvCamera').options)option.disabled=!available[option.value]?.length;
      if(!available[$('rvCamera').value]?.length)$('rvCamera').value='long';
    }
    const short=$('rvCamera').value==='short',ten=$('rvGrating').querySelector('option[value="10"]');
    ten.disabled=short;
    const switched=short&&$('rvGrating').value==='10';if(switched)$('rvGrating').value='111';
    if(available){
      for(const option of $('rvGrating').options)option.disabled=!available[$('rvCamera').value]?.includes(Number(option.value));
      if($('rvGrating').selectedOptions[0]?.disabled)$('rvGrating').value='111';
    }
    $('rv-camera-note').textContent=switched?'10 l/mm requires long blue; switched to 111 l/mm.':short?'Short blue supports 32 and 111 l/mm. Narrow slits may be undersampled.':'10, 32 and 111 l/mm are available with long blue.';
    const camera=$('rvCamera').value==='short'?'Short blue':'Long blue',grating=$('rvGrating').value||'111';
    $('setup-description').textContent=`${camera} / ${grating} l/mm · longslit · natural seeing · SBAny. Camera and grating change the detector coverage, nominal resolution and exposure time. Automatic band: K 2.30 µm for L0–T2; J 1.30 µm for T3+. Automatic slit: 0.15″ Band 1/2; 0.30″ Band 3. Check slit/FWHM against your 0.40 goal.`;
    $('mode-summary').textContent=`L0+ RV science and standards · ${camera} · ${grating} l/mm`;
  }
}
async function switchMode(){
  if(!state.data)return;modeFilters[currentMode]=filters();currentMode=$('observing-mode').value;
  const next=modeFilters[currentMode]||state.data.mode_defaults[currentMode];configureMode();resetValues(next);
  choices('aids',state.data.associations,next.aids);choices('observables',state.data.observables,next.observables);
  state.timings.clear();state.active=null;$('target-name').textContent='Select a target';$('target-telescope-time').textContent='—';$('details').replaceChildren();
  const url=new URL(location.href);url.searchParams.set('mode',currentMode);history.replaceState(null,'',url);
  renderMethods();await update();
}
let selectionRevision=0,listRevision=0,activeRevision=0;
async function update(){
  updateSetupDescription();
  if(!state.data)return;const revision=++selectionRevision,f=filters();
  $('spt-range').textContent=`${spt(f.sptMin)} – ${spt(f.sptMax)} · temperature cut ${f.teffEnabled?'on':'off'}`;
  $('ylog').disabled=spectralYAxis();$('ylog-label').classList.toggle('subtle',spectralYAxis());
  $('notice').textContent='Updating selection from the indexed catalog…';
  try{
    const response=await GNIRSAccess.fetch('/api/selection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filters:f})});
    if(!response.ok)throw Error((await response.json()).error);const {id}=await response.json();
    for(;;){
      if(revision!==selectionRevision)return;
      const response=await GNIRSAccess.fetch(`/api/selection?id=${id}`);const result=await response.json();
      if(!response.ok||result.status==='error')throw Error(result.error||`HTTP ${response.status}`);
      if(result.status==='complete'){
        if(revision!==selectionRevision)return;
        state.job=id;state.selection=result.result;state.rows=result.result.plot;state.offset=0;state.timings.clear();
        const total=state.selection.totals;
        $('count').textContent=`${state.selection.count.toLocaleString()} / ${state.selection.total_count.toLocaleString()}`;
        for(const k of ['science','program','telescope'])$(k).textContent=`${fmt(total[k]/3600,1)} h${total.unknown?' + ?':''}`;
        renderProposalSize(total,state.selection.count);
        const labels=new Map([...$('aids').querySelectorAll('input')].map(el=>[el.value,el.parentElement]));
        for(const [aid,label] of labels)label.querySelector('.choice-count').textContent=state.selection.association_counts[aid]||0;
        $('aids').append(...G.associationOrder([...labels.keys()],f.aids,state.selection.association_counts).map(a=>labels.get(a)));
        const missing=spectralYAxis()?total.unplotted_age:total.unplotted_teff;
        $('unplotted').textContent=(missing?`${missing.toLocaleString()} without plottable age / ${spectralYAxis()?'SpT':'Teff'}`:'')+(state.selection.plot_sampled?' · plot shows a 12,000-point sample; counts/totals use all selected objects':'');
        $('notice').textContent=`2027A · ${total.visits.toLocaleString()} planned visits · ${modeInfo()[f.mode].label} · ${snrDescription(f)}${total.unknown?` · ${total.unknown.toLocaleString()} targets have incomplete timing`:''} · ${fmt(state.selection.elapsed_seconds,2)} s cached calculation · calibration allowance is provisional.`;
        $('notice').className=total.unknown?'warning':'';
        $('rv-summary').textContent=`${total.measured_rv.toLocaleString()} measured RV · ${total.gnirs_data.toLocaleString()} with GNIRS data · ${total.planned.toLocaleString()} planned reductions`;
        await renderList();
        if(state.active)await activate({moca_oid:state.active.moca_oid},false);
        if(revision!==selectionRevision)return;
        state.view=fitCurrent();
        draw();break;
      }
      $('notice').textContent=`Updating selection… ${result.scanned?result.scanned.toLocaleString()+' candidates evaluated':'checking cached results'}`;
      await new Promise(resolve=>setTimeout(resolve,400));
    }
  }catch(e){if(revision===selectionRevision){$('notice').textContent='Selection failed: '+e.message;$('notice').className='warning';}}
}
async function renderList(reset=false){
  if(!state.job)return;if(reset)state.offset=0;const revision=++listRevision;
  const query=new URLSearchParams({id:state.job,q:$('search').value.trim(),sort:$('list-sort').value,offset:state.offset||0,gnirs_only:$('gnirs-only').checked?'1':'0'});
  const response=await GNIRSAccess.fetch('/api/list?'+query);const data=await response.json();if(revision!==listRevision)return;
  if(!response.ok){$('rvlist').textContent=data.error;return;}
  const f=filters(),fragment=document.createDocumentFragment();
  for(const r of data.rows){const t=r._timing;state.timings.set(r.moca_oid,t);const failures=G.filterFailures(r,f,t),button=document.createElement('button');button.className='target-item'+(state.active?.moca_oid===r.moca_oid?' active':'');button.dataset.oid=r.moca_oid;
    button.innerHTML=`<span class="name">${esc(r.designation)}</span><span class="meta">${esc(G.aid(r))} · ${esc(r.spt)} · OID ${r.moca_oid}<br>${(t.photometry_band||t.band).toUpperCase()} ${fmt(t.mag)} · best X ${fmt(r.visibility?.best_airmass)} · ${hours(isSxd()?t.telescope:t.program)} ${isSxd()?'telescope':'program'}</span><span class="badges">${Number(r.photometric_estimate)===1?'<span class="badge warn">Photometric SpT</span>':''}<span class="badge ${r.has_rv?'spec':'good'}">${r.has_rv?'RV measured':'No measured RV'}</span>${Number(r.archive_max_R)>0?`<span class="badge spec">GNIRS data · R ≈ ${fmt(r.archive_max_R,0)}</span>`:''}${r.planned_reduction_highres?'<span class="badge spec">Planned reduction</span>':''}${f.rvMode==='none'&&r.has_rv&&f.bypassNoMeasuredRvOids.includes(Number(r.moca_oid))?'<span class="badge spec">RV standard</span>':''}${t.extrapolated?'<span class="badge warn">ITC extrapolation</span>':''}${r.restricted_access?'<span class="badge warn">Restricted access</span>':''}</span>${failures.length?`<span class="filter-misses">Excluded: ${esc(failures.join(' · '))}</span>`:''}`;
    button.onclick=()=>activate(r);fragment.append(button);
  }
  $('rvlist').replaceChildren(fragment);$('rvcount').textContent=data.count.toLocaleString();
  if(!data.rows.length)$('rvlist').innerHTML=`<p class="empty">${$('gnirs-only').checked?'No selected targets with recorded GNIRS data. Uncheck both coverage exclusions under Kinematics, crowding & coverage to include them.':'No matching targets.'} Numeric OIDs search all ${state.data.catalog_count.toLocaleString()} loaded objects.</p>`;
  $('list-page').textContent=data.count?`${data.offset+1}–${Math.min(data.offset+100,data.count)} of ${data.count.toLocaleString()}`:'0';
  $('list-prev').disabled=data.offset===0;$('list-next').disabled=data.offset+100>=data.count;
}
async function navigateTarget(direction){
  if(!state.job)return;const q=new URLSearchParams({id:state.job,oid:state.active?.moca_oid||0,step:direction});
  const response=await GNIRSAccess.fetch('/api/navigate?'+q),data=await response.json();if(data.row){state.navIndex=data.index;await activate(data.row);}
}
async function activate(r,scroll=true){
  const revision=++activeRevision;
  if(!r._detail){const response=await GNIRSAccess.fetch(`/api/target?id=${state.job}&oid=${r.moca_oid}`);r=await response.json();if(!response.ok||!r)return;}
  if(revision!==activeRevision)return;state.active=r;state.timings.set(r.moca_oid,r._timing);
  if(scroll)$('inspector').scrollTop=0;renderInspector();
  for(const el of $('rvlist').querySelectorAll('.target-item'))el.classList.toggle('active',Number(el.dataset.oid)===r.moca_oid);
  draw();
}
function detail(label,value,wide=false){return `<div class="detail${wide?' wide':''}"><span>${esc(label)}</span><strong>${value}</strong></div>`;}
const boolLabel=v=>v===null||v===undefined?'unknown':Number(v)===1?'yes':'no';
function reference(ref,bibcode){return bibcode?`<a target="_blank" rel="noopener" href="https://ui.adsabs.harvard.edu/abs/${encodeURIComponent(bibcode)}/abstract">${esc(ref||bibcode)}</a>`:esc(ref);}
function renderInspector(){
  const r=state.active,n=state.selection?.count||0;$('target-position').textContent=`${n.toLocaleString()} selected`;$('previous-target').disabled=!n;$('next-target').disabled=!n;if(!r)return;
  const f=filters(),t=state.timings.get(r.moca_oid),v=r.visibility,win=v?.windows?.[String(t.airmass)],rv=r.rv;
  const failures=G.filterFailures(r,f,t);
  $('target-name').textContent=r.designation;$('target-telescope-time').textContent=hours(t.telescope);$('report').href=r.report_url;
  $('details').innerHTML=
    detail('OID · selection',`${r.moca_oid} · ${failures.length?'excluded':'selected'}${f.includeOids.includes(r.moca_oid)?' (forced)':''}${f.bypassNoMeasuredRvOids.includes(r.moca_oid)?' (RV standard bypass)':''}`)+
    detail('Current BANYAN association',`${esc(G.aid(r))} · best overall: ${esc(r.best_hyp)}`)+
    detail('Individual / summed young probability',`${fmt(r.individual_prob,3)}% / ${fmt(r.summed_young_prob,3)}%${r.membership_detail_note?' · '+esc(r.membership_detail_note):''}`)+
    detail('Regular / loose UVW separation',`${fmt(r.uvw_sep)} / ${fmt(r.uvw_sep_loose)} km/s`)+
    detail('BANYAN U, V, W',`${fmt(r.u_opt)}, ${fmt(r.v_opt)}, ${fmt(r.w_opt)} km/s`)+
    detail('Observables · association quality',`${esc(r.observables)} · real ${esc(r.is_real)} · highly contaminated ${boolLabel(r.highly_contaminated)}`)+
    detail('Adopted spectral type',`${esc(r.spt)} · quality ${esc(r.spt_quality)} · ${reference(r.spt_ref,r.spt_bibcode)}`)+
    detail('Spectral-type origin',`${esc(r.spt_origin)} · method ${esc(r.spt_calculation_method)}`,true)+
    detail('Adopted flags',`Photometric ${boolLabel(r.photometric_estimate)} · lowg_like ${boolLabel(r.lowg_like)} · subdwarf_like ${boolLabel(r.subdwarf_like)} · duplicate ${boolLabel(r.likely_duplicate)}`,true)+
    detail('Teff',`${fmt(r.teff,0)} ± ${fmt(r.teff_unc,0)} K · ${esc(r.teff_source)} · ${reference(r.teff_ref,r.teff_bibcode)}`,true)+
    detail('Association age',G.finite(r.age_myr)?`${esc(r.age_label||fmt(r.age_myr,1))} Myr · ${reference(r.age_ref,r.age_bibcode)}${r.association_age_is_conditional?' · conditional on association membership; FIELD is favored':''}`:'Unknown; no age assigned',true)+
    detail('Adopted distance',`${fmt(r.distance_pc)} ± ${fmt(r.distance_pc_unc)} pc · photometric ${boolLabel(r.distance_photometric_estimate)} · ${esc(r.distance_ref)}`)+
    detail('Association mean distance',`${fmt(r.association_mean_distance_pc,1)} pc · current model${r.association_distance_public_fallback?' (public model properties)':''}`)+
    detail('Host separation',`${fmt(r.host_separation===null?null:r.host_separation/1000,3)} arcsec · ${esc(r.host_separation_source)}`,true)+
    detail('Measured RV status',`${r.has_rv?'Direct measurement available':'No direct non-ignored measurement'} · ${r.rv_measurements.length} measurements · ${r.host_rv_measurements.length} host-derived rows`,true)+
    detail('Adopted / displayed RV',rv?`${fmt(rv.radial_velocity_kms)} ± ${fmt(rv.radial_velocity_kms_unc)} km/s · ${esc(rv.adoption)} · ${esc((rv.references||[]).join(', '))}`:'—',true)+
    detail('BANYAN predicted RV (not a measurement)',`${fmt(r.rv_opt)} ± ${fmt(r.erv_opt)} km/s`)+
    detail('RV reference suitability',`${esc(r.rv_reference_audit||'Not in the prior reference audit')} · check binarity, epoch scatter and flags`,true)+
    detail('Individual RV provenance',rvTable(r.rv_measurements),true)+
    (r.host_rv_measurements.length?detail('Host-derived RV context',rvTable(r.host_rv_measurements),true):'')+
    detail('GNIRS configuration',`${esc(modeInfo()[f.mode].label)}<br>${isSxd()?'Short-blue · 32 l/mm · SXD · 7″ slit length':`${t.camera==='short'?'Short-blue':'Long-blue'} · ${esc(t.grating)} l/mm · longslit`} · setting ${fmt(t.center_um,2)} µm · ${t.wavelength_range_um?.map(x=>fmt(x,4)).join('–')||'unknown'} µm<br>slit ${t.slit}″ · nominal R ≈ ${fmt(t.resolving_power,0)} · airmass ${fmt(t.airmass,1)} · ${snrDescription(f)}`,true)+
    (isSxd()?'':detail('Detector sampling',`${fmt(t.pixel_scale,2)}″/pixel · slit projects to ${fmt(t.spectral_slit_pixels,2)} pixels${t.spectral_slit_pixels<2?' · undersampled slit: effective resolving power and RV accuracy depend on the optical profile and pixel response; nominal R is not a measured resolution':''}`,true))+
    detail('Seeing and slit',`ITC FWHM ${fmt(t.seeing_fwhm,2)}″ · slit/FWHM ${fmt(t.slit_seeing_ratio,2)}${isSxd()?' · nominal resolution assumes slit-filling illumination; use average parallactic angle':' · upper-limit goal 0.40; check actual acquisition seeing'}`,true)+
    detail('Atmosphere template',`${esc(t.template_spt)} · ${fmt(t.template_teff,0)} K · ${isSxd()?(t.template_family==='library'?'Gemini T2800K late-M proxy':t.template_family==='diamondback'?'Sonora Diamondback, fsed=2, log g=4':'Sonora Elf Owl, log g=4, local release unverified'):(t.template_family==='diamondback'?'Sonora Diamondback, fsed=2, log g=5':'Sonora Elf Owl, log g=5, local release unverified')} · solar metallicity${t.template_approximate?' · nearest spectral-type template':''}`,true)+
    detail('Adopted time-model photometry',`${(t.photometry_band||t.band).toUpperCase()} ${fmt(t.mag)} ± ${fmt(t.photometry?.magnitude_unc,3)} · ${esc(t.photometry?.moca_psid)} · ${esc(t.photometry?.moca_pid)}${t.photometry?.component_override?' · resolved-companion override':''}${t.model_color_normalization?' · H-band flux inferred from J and the selected Sonora template color':''}${isSxd()&&t.photometry&&!/(2mass|tmass)/i.test(t.photometry.moca_psid||'')?' · non-2MASS J: system conversion is approximate':''}`,true)+
    detail('Science / program / telescope',`${hours(t.science)} / ${hours(t.program)} / ${hours(t.telescope)}`,true)+
    (isSxd()?'':detail('Band 3 (0.30″) science comparison',`${hours(t.band3Science)} · ${G.finite(t.band3Science)?t.band3Science<f.maxScience*3600?'below':'at / above':'cannot compare with'} ${fmt(f.maxScience)} h limit${f.excludeFastBand3?' · exclusion on':''}`,true))+
    detail('Exposure / visit plan',`${t.frames??'—'} × ${t.frame_seconds??'—'} s${t.read_mode?' · '+esc(t.read_mode):''} · ${t.visits??'—'} visits · longest ${hours(t.longest_visit)} · ${t.eligible_nights??0} nights can fit it`,true)+
    detail('Timing assumptions / flags',`${t.extrapolated?'Outside ITC magnitude grid; extrapolated. ':''}${t.brightReadmodeReview?'Bright target: read-mode/frame saturation review required. ':''}${esc(t.reason||'Visit durations fit the sampled windows.')} ${t.template_outside_grid?'Outside representative template range; nearest template used.':''}`,true)+
    detail('Best night-time airmass',v?.best_airmass?`${fmt(v.best_airmass,4)} · ${esc(v.best_utc)}<br>Hawaii evening ${esc(v.best_evening)}`:'Never above the planning horizon during usable darkness',true)+
    detail(`Longest window at X ≤ ${t.airmass}`,`${fmt(win?.max_hours)} h · ${esc(win?.best_start_utc)} to ${esc(win?.best_end_utc)}<br>${win?.nights_1h??0} nights with ≥1 h · ${esc(win?.first_evening)}–${esc(win?.last_evening)} (Hawaii evenings)`,true)+
    detail('Coordinates / epoch',`${fmt(r.ra,7)}°, ${fmt(r.dec,7)}° · ${esc(r.coord_frame||'ICRS assumed from object catalog')} · epoch ${fmt(r.measurement_epoch_yr,3)} · ${esc(r.coordinate_ref)}<br>${esc(v?.astrometry)}`,true)+
    detail('Published access',`${r.ra_accessible?'Within 04h–01h RA range':'Outside published RA range'} · ${r.restricted_access?'restricted seasonal/declination zone':'unrestricted RA/declination zone'}`)+
    detail('Existing GNIRS data',`${(r.spectra||[]).filter(s=>String(s.instrument_name).toUpperCase()==='GNIRS').length} MOCAdb spectra · ${(r.archive_matches||[]).length} matched archive frames · maximum recorded R ≈ ${fmt(r.archive_max_R,0)}${r.archive_identity_review?' · archive identity review pending':''}. Planned reduction at R≥2700: ${r.planned_reduction_highres?'yes':'no'} (separate from recorded data)`,true)+
    detail('All semester windows',`<button id="load-windows" type="button">Show useful nights at X ≤ ${t.airmass}</button><div id="windows-result"></div>`,true)+
    detail('Current filter failures',failures.length?`<span class="warning-text">${esc(failures.join(' · '))}</span>`:'<span class="success-text">Passes all active cuts</span>',true);
  $('load-windows').onclick=()=>loadWindows(r,t);
}
function rvTable(rows){if(!rows.length)return 'None';return `<details><summary>${rows.length} non-ignored row${rows.length===1?'':'s'} — values, sources and flags</summary><table><thead><tr><th>RV ± σ (km/s)</th><th>Reference / epoch</th><th>Origin / flags / comments</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${fmt(r.radial_velocity_kms)} ± ${fmt(r.radial_velocity_kms_unc)}<br>#${r.rv_id}</td><td>${reference(r.reference||r.moca_pid,r.bibcode)}<br>${fmt(r.epoch,2)}</td><td>${esc(r.origin)}<br>${esc(r.flags)} · ${esc(r.comments)}</td></tr>`).join('')}</tbody></table></details>`;}
async function loadWindows(r,t){const el=$('windows-result');el.textContent='Loading…';try{let windows=state.windows.get(r.moca_oid);if(!windows){const response=await GNIRSAccess.fetch(`/api/windows?oid=${r.moca_oid}`);if(!response.ok)throw Error(`HTTP ${response.status}`);windows=await response.json();state.windows.set(r.moca_oid,windows);}if(state.active?.moca_oid!==r.moca_oid)return;const rows=windows[String(t.airmass)]||[];el.innerHTML=`<div class="window-table"><table><thead><tr><th>Hawaii evening</th><th>Start UTC</th><th>End UTC</th><th>Hours</th><th>Visit fits</th></tr></thead><tbody>${rows.map(w=>`<tr><td>${w.evening_hst}</td><td>${w.start_utc.replace('T',' ').replace('+00:00','')}</td><td>${w.end_utc.replace('T',' ').replace('+00:00','')}</td><td>${fmt(w.hours)}</td><td>${G.finite(t.longest_visit)&&w.hours*3600>=t.longest_visit?'yes':'no'}</td></tr>`).join('')}</tbody></table></div>`;}catch(e){el.textContent=e.message;}}
function renderMethods(){const d=state.data;if(isSxd())return renderSxdMethods(d); $('methods-body').innerHTML=`
  <h3>Parent catalog and adopted data</h3><p>${esc(d.manifest.parent_scope)}. ${d.catalog_count.toLocaleString()} unique active OIDs, read from MOCAdb on ${esc(d.manifest.collected_at)}. The GNIRS parent is independent of the JWST proposal selection. The loaded parent scope is explicit: excluded rows can be found with numeric OID search. Unknown-age targets stay in the list and totals but cannot be plotted on an age axis.</p>
  <p>SpT and flags come from adopted, non-ignored spectral types. Teff uses adopted data_teff with public-adopted fallback, then the young SpT–Teff sequence. Association ages match the current private, maximum-observables BANYAN association and adopted model. Ages remain conditional on membership; no generic field age is assigned. Individual detail probabilities are stored as fractions and multiplied by 100; the summed young probability is already in percent. Regular and loose UVW are separate; for a photometric distance the loose value uses the smaller separation after omitting parallax when available.</p>
  <h3>Measured radial velocities</h3><p>${esc(d.rv_definition)} The displayed adopted estimate is the private combined RV when supported by direct measurements without host propagation. Otherwise the inspector labels its individual fallback. All individual measurement provenance and flags remain available. Old small error bars do not establish stability through 2027. Manual RV-standard OIDs bypass the “No measured RV” status and membership selection, including BANYAN probability and UVW limits. Spectral, quality, access, timing and other cuts still apply.</p>
  <h3>GNIRS RV exposure prescription — 2026-09-28</h3><p>Gemini legacy ITC wavelength-resolved calculations with public Sonora spectra. Select long blue (0.05″/pixel) or short blue (0.15″/pixel), and 10, 32 or 111 l/mm, in longslit mode without cross dispersion. Natural seeing, Very Faint read mode, optimal extraction, ABBA. Defaults remain long blue and 111 l/mm. The target inspector and CSV report the selected camera, grating, detector coverage and nominal slit-limited resolution. Narrow slits with the short camera can be undersampled; nominal resolving power is not a measurement of the actual instrumental profile. Automatic band selection uses K centered at 2.30 µm for L0–T2, and J centered at 1.30 µm for T3 and later. J, H (1.65 µm) and K can also be selected explicitly; wavelength coverage depends on the camera and grating. The default is Band 1/2 with a 0.15″ slit; Band 3 uses 0.30″. The operational goal is slit/FWHM ≤0.4; the displayed ratio uses the ITC condition-bin FWHM, and actual acquisition seeing must be checked.</p>
  <p>The S/N threshold (default 50 per detector pixel) must be reached in at least the selected fraction (25%, 50%, 75%, 90% or 95%; default 75%) of all detector pixels across the full recorded wavelength interval, including molecular absorption, telluric absorption and sky-line noise. Qualifying pixels may be disjoint; there is no contiguous-interval requirement. Failed pixels remain in the denominator. It is not a continuum-point or median-S/N criterion. Each curve uses the nearest spectral-type template: Diamondback through T2 (fsed=2), Elf Owl from T3, solar metallicity and log g=5. Local Elf Owl release provenance is unverified and is not claimed to be v2. Types later than Y0 use the Y0 template and are flagged. This is a planning model, not an RV-accuracy guarantee.</p>
  <p>Templates are normalized using synthetic 2MASS J or Ks photometry. Explicit J, H (1.65 µm), and K settings and seven slit widths are selectable for RV mode. H uses measured J normalization and the template J–H color because the current catalog cache contains only J/K photometry; unusual colors can bias this estimate. Separate calculations cover each band, slit, condition set and airmass. Two brightnesses and two frame durations determine source, sky and read-noise terms per pixel. Cached magnitude curves solve the selected qualifying-pixel fraction for 60/120/180/240/300 s frames; the planner chooses the least science-plus-read/nod overhead cost after rounding to complete ABBA sequences. S/N² and the exposure multiplier apply at fixed frame length. Magnitude interpolation uses a conservative source/sky scaling bound between cached points, with flagged extrapolation outside 8–24 mag. Bright targets still need saturation/read-mode review. Model mismatch, unusual colors, gravity and K/Ks differences remain uncertainties. All interactive timing uses compact curves in the shared cache. No atmosphere spectra are deployed or downloaded to the browser; instrumental convolution is performed once by the ITC during offline calibration. Each API request verifies your credentials with MOCAdb; catalog queries run only during regeneration. No ITC requests run on this server.</p>
  <h3>Time accounting and visits</h3><p>Complete ABBA cycles using 60, 120, 180, 240 or 300 s frames. Per frame: 34.3 s read/write/nod allowance. Per visit: 15 min acquisition, plus 6 min recentering per 45 min science. Each visit contains whole ABBA cycles and must fit the actual continuous window and selected maximum block. Program totals include these overheads. Telescope totals add the adjustable provisional calibration allowance (default 20 min/visit); this is not an official PIT charge. PIT automatically adds baseline calibrations: enter program time and do not add this provisional allowance twice. Only displayed selected targets contribute; there are no hidden standards.</p>
  <h3>CanTAC GNIRS proposal scale</h3><p>The five header bands are a planning guide, not official CanTAC proposal categories or limits. They use selected-target program time, including acquisition and read/nod/recentering overheads, before PIT's baseline calibrations: Snapshot &lt;5 h, Focused 5–10 h, Broad 10–20 h, Large 20–40 h, and Very large ≥40 h. Exact boundary values enter the higher band. If any target has incomplete timing, the displayed hours are a lower bound and the category remains uncertain unless the known subtotal already reaches 40 h. The <a href="https://www.gemini.edu/observing/schedules-and-queue/queue-summary-bands-dd-lp-ft-pw" target="_blank" rel="noopener">Gemini North 2025A queue summary</a> lists Canadian GNIRS allocations of 2.97 h (GN-2025A-Q-117), 3.95 h (GN-2025A-FT-108), and 4.25 h (GN-2025A-FT-202). The <a href="https://webarchive.gemini.edu/20221122-observing--schedules-and-queue--2022a-gn-queue-band-1-3/" target="_blank" rel="noopener">2022A queue summary</a> includes Canadian GNIRS allocations of 3.00, 4.00, 4.30, and 21.12 h. These examples show that small requests are common and some standard programs exceed 20 h; they do not establish a formal typical size. The <a href="https://nrc.canada.ca/en/research-development/products-services/technical-advisory-services/gemini-canadian-specific-information-phase-i" target="_blank" rel="noopener">Canadian 2027A call</a> gives Canada 161 h in total at Gemini North across all instruments, including GNIRS. A 40 h request would consume about a quarter of that total.</p>
  <h3>Semester visibility</h3><p>${esc(d.visibility_method)} The 20° horizon is a planning assumption; instrument, guide-star, zenith tracking and queue scheduling checks remain Phase II work. Each interval has both five-minute endpoints within darkness and the requested airmass, so window durations are conservative. Best airmass is the best sample over the whole semester. Acquisition must fit on target; the separate telluric/calibration allowance can occur outside that target's window.</p>
  <p>${esc(d.semester.availability_note)} The April 12–29 closure is provisional. The NRC maintenance sentence is inconsistent; dates follow the Korean Gemini Office and Subaru official partner calls. Restricted RA/declination regions are flagged; enable “Exclude restricted-access targets” to remove them from the selection. The cut uses RA outside 06h–23h or declination outside −30° to +73° and can still be bypassed with Force include OIDs. No weather, lunar exclusion (SBAny), or queue allocation is simulated.</p>
  <h3>Coverage and quality</h3><p>Current non-ignored MOCAdb GNIRS spectra are combined with the saved public archive audit, using its inferred resolving powers. The GNIRS data badge and list toggle require recorded coverage with a resolving-power estimate; a raw archive frame is not necessarily a reduced spectrum. Planned-reduction metadata identify R≥2700 data separately, without claiming a successful reduction or an RV. The archive snapshot is September 2026. Duplicate and classification filters are independent. No JWST-only low-gravity overrides or manual exclusion lists are inherited.</p>
  <h3>Tracks and sources</h3><p>Sonora Diamondback hybrid-grav solar-metallicity tracks and young SpT–Teff axes reuse the existing selector's calibrated cache. Display jitter changes no values or selection. <a href="${esc(d.mass_tracks.source)}" target="_blank" rel="noopener">Track source</a>.</p><ul>${d.semester.sources.map(s=>`<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a></li>`).join('')}</ul>`;}
function renderSxdMethods(d){$('methods-body').innerHTML=`
  <h3>SXD setup and S/N</h3><p>32 l/mm grating, short-blue camera (0.15″/pixel), 0.45″ × 7″ slit, SXD prism, 1.65 µm setting, natural seeing with PWFS. Simultaneous nominal 0.85–2.5 µm coverage; strong telluric bands and low blue throughput remain. Nominal slit-filled R≈1070 at 1.25 µm, ≈1130 at 1.65 and 2.20 µm. The 0.675″ slit would give lower R≈710–760 and is not this setup. Use average parallactic angle for broad spectral shape. Guide-star availability and acquisition references still require Phase II checking.</p>
  <p>The editable S/N criterion applies only to 1.20–1.30 µm in order 5. It is not a guarantee for all SXD orders. Per-resolution-element S/N sums three detector pixels and propagates their independent variances; per-pixel S/N is a separate choice. The selected 50%, 75% or 90% coverage includes the absorption and sky noise in that interval. Resampling covariance and telluric-correction residuals are not simulated.</p>
  <h3>Independent candidates</h3><p>${esc(d.manifest.parent_scope)}. ${d.catalog_count.toLocaleString()} active OIDs. The M5 boundary admits young brown-dwarf candidates, but also stars; substellar status requires age/mass assessment. Objects earlier than M5, objects without an adopted numeric type, and objects absent from MOCAdb are outside this parent. Photometric types, pm-only cases and measured RVs are included by default. No RV standards bypass the membership cuts. Archive, planned high-resolution reductions, low-gravity and association-quality exclusions start off. Default summed association probability is ≥80%, regular UVW ≤6 km/s, association age ≤300 Myr (unknown included), best night-time airmass ≤1.8. Every cut is editable; individual associations start enabled.</p>
  <p>BANYAN associations and ages remain hypotheses. A photometric type or a conditional age is not spectroscopic youth confirmation. The optional archive cut excludes any recorded GNIRS data at or above the chosen R; it does not establish complete 0.85–2.5 µm coverage or sufficient S/N. Archive matching is a snapshot and not a new exhaustive archive search.</p>
  <h3>Cached sensitivity model</h3><p>${esc(d.sxd_grid?.model_assumptions||'SXD grid not published.')} Sonora templates are normalized to synthetic 2MASS J=16; the M6 proxy uses the ITC J Vega convention. Other J systems are used as approximate J and flagged in reports. Only public model spectra are uploaded to Gemini. Generic ITC responses are keyed by every request field, spectrum hash and refresh epoch, then compiled with a versioned instrument/noise/overhead specification. Changing a UI control uses the cached catalog and timing grid; each request validates your MOCAdb credentials.</p>
  <p>The source/sky/read-noise coefficients come from fresh SXD requests at two brightnesses and two frame lengths. The grid spans J=8–24 in 0.25 mag steps; interpolation is logarithmic and outside magnitudes remain untimed. Frame options are 2/5/10 s (Bright), 20/40 s (Faint), and 60/120/180/200 s (Very Faint), rounded to complete on-slit ABBA cycles. The H-band sky limit bounds exposures at 200 s. A conservative 50,000-electron bound checks all six orders using peak-row source counts and per-pixel sky, including a median-weather check. Bright objects still merit individual acquisition and saturation review. The two shorter read-mode noise terms use the documented 30/10 e− noises relative to the calibrated 7 e− mode.</p>
  <h3>Time accounting</h3><p>Science is on-source integration. Charged program time adds a conservative 15 min acquisition per visit (matching the live ITC; the Gemini web table lists 12 min), 6 min recentering after each 45 min of science when more science follows, readout of 0.70/11.14/22.30 s per frame by mode, 8.56 s file write per frame and 7 s per nod (two nods per ABBA). A new visit starts no later than two hours of science. Total telescope time adds the editable baseline-calibration allowance, provisionally 20 min per visit. This allowance is not an official PIT charge. PIT adds baseline calibrations; do not double-count them.</p>
  <p>Unlike the RV mode, the SXD visit-fit calculation conservatively includes the calibration allowance inside the selected block and target window. Default per-target cutoff is total telescope time strictly below one hour. S/N, weather conditions and this cutoff are provisional user-editable planning choices. Queue bands do not by themselves specify seeing or transparency.</p>
  <h3>Visibility and cache maintenance</h3><p>${esc(d.visibility_method)} The existing semester closure and access limits apply. Catalog data, visibility summaries and timing grids share one private server cache file. Regenerate catalog refreshes the shared database snapshot; Reload cache rereads the published version. Figures are drawn in your browser and exports are downloaded without server files. Timing grids are updated by the server administrator through the deployment cache import. The previous complete timing grid stays usable on failure. Grid built ${esc(d.sxd_grid?.created_at)}; key ${esc(d.sxd_grid?.cache_key?.slice(0,16))}.</p>
  <p><a href="https://www.gemini.edu/instrumentation/gnirs/capability" target="_blank" rel="noopener">Gemini capability and resolving powers</a> · <a href="https://www.gemini.edu/instrumentation/gnirs/observation-preparation" target="_blank" rel="noopener">Observing and overheads</a> · <a href="https://www.gemini.edu/instrumentation/gnirs/exposure-time-estimation" target="_blank" rel="noopener">Exposure limits / ITC caveats</a> · <a href="https://www.gemini.edu/instrumentation/gnirs/calibrations" target="_blank" rel="noopener">Calibrations</a></p>`;}
async function exportCsv(){
  if(!state.job)return;
  try{const response=await GNIRSAccess.fetch('/api/export?id='+state.job);
    if(!response.ok)throw Error((await response.json()).error);
    const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');
    a.href=url;a.download=`gnirs_${currentMode}_2027A_selection.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){$('notice').textContent='Export failed: '+e.message;}
}
async function load(first=false){
  first=first||!state.data;
  clearTimeout(rebuildTimer);
  state.cacheReady=false;
  $('regenerate').disabled=true;
  try{
    const response=await GNIRSAccess.fetch('/api/meta');
    if(!response.ok)throw Error((await response.json()).error||`HTTP ${response.status}`);
    const data=await response.json(),old=first?null:filters();
    state.data=data;state.windows.clear();state.timings.clear();state.timingKey=null;
    configureMode();resetValues(old||modeDefaults());
    choices('aids',data.associations,old?.aids);choices('observables',data.observables,old?.observables);
    const collectedAt=new Date(data.manifest.collected_at).toLocaleString(undefined,{year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',timeZoneName:'short'});
    $('cache-status').textContent=`${data.catalog_count.toLocaleString()} cached OIDs · MOCAdb ${collectedAt}${data.catalog_complete?'':' · cache build in progress'} · RV grid ${new Date(data.grid.created_at).toLocaleString()} · SXD grid ${data.sxd_grid?new Date(data.sxd_grid.created_at).toLocaleString():'not published'}`;
    renderMethods();await update();
    state.cacheReady=true;
    await pollRebuild();
  }catch(e){
    state.cacheReady=false;$('regenerate').disabled=true;
    $('notice').textContent='Could not load GNIRS cache: '+e.message;$('notice').className='warning';
    $('rebuild-status').textContent='Regeneration is unavailable until the shared cache loads. After the server configuration is fixed, use Reload cache.';
  }
}
let rebuildTimer=null,rebuildAwaiting=false;
let itcTimer=null,itcAwaiting=false;
async function pollItc(){
  clearTimeout(itcTimer);
  try{
    const response=await GNIRSAccess.fetch('/api/regenerate-itc');if(!response.ok)return;
    const status=await response.json(),active=['queued','starting','building'].includes(status.phase);
    $('refresh-sxd').disabled=active;$('itc-status').textContent=status.phase==='idle'?'':status.message;
    if(active){itcAwaiting=true;itcTimer=setTimeout(pollItc,4000);}
    else if(status.phase==='complete'&&itcAwaiting){itcAwaiting=false;await load();}
    else itcAwaiting=false;
  }catch(e){$('itc-status').textContent='Timing-cache status unavailable';}
}
async function refreshSxd(){
  $('refresh-sxd').disabled=true;$('itc-status').textContent='Starting an independent public-model ITC refresh…';
  try{const response=await GNIRSAccess.fetch('/api/regenerate-itc',{method:'POST'});const result=await response.json();if(!response.ok)throw Error(result.error);itcAwaiting=true;await pollItc();}
  catch(e){$('itc-status').textContent=e.message;$('refresh-sxd').disabled=false;}
}
async function pollRebuild(){
  clearTimeout(rebuildTimer);
  if(!state.cacheReady)return;
  try{
    const response=await GNIRSAccess.fetch('/api/regenerate');if(!response.ok)throw Error((await response.json()).error||`HTTP ${response.status}`);
    if(!state.cacheReady)return;
    const status=await response.json(),active=['queued','starting','collecting','building','publishing'].includes(status.phase);
    $('regenerate').disabled=active;
    $('rebuild-status').textContent=status.phase==='idle'?'':active?`Regenerating: ${status.message}. Current catalog remains available.`:status.phase==='complete'?`Last full regeneration ${new Date(status.updated_at*1000).toLocaleDateString()}: ${status.message.replace(/^Updated catalog: /,'')}`:status.message;
    if(active)rebuildAwaiting=true;
    if(active)rebuildTimer=setTimeout(pollRebuild,3000);
    else if(status.phase==='complete'&&rebuildAwaiting){rebuildAwaiting=false;await load();}
    else if(status.phase==='error'||status.phase==='interrupted')rebuildAwaiting=false;
  }catch(e){$('rebuild-status').textContent='Could not check cache regeneration: '+e.message;$('regenerate').disabled=true;if(state.cacheReady)rebuildTimer=setTimeout(pollRebuild,10000);}
}
async function regenerateCache(){
  if(!state.cacheReady)return;
  $('regenerate').disabled=true;$('rebuild-status').textContent='Starting cache regeneration…';
  try{
    const response=await GNIRSAccess.fetch('/api/regenerate',{method:'POST'});
    const status=await response.json();if(!response.ok)throw Error(status.error||`HTTP ${response.status}`);
    rebuildAwaiting=true;await pollRebuild();
  }catch(e){$('regenerate').disabled=!state.cacheReady;$('rebuild-status').textContent='Could not start cache regeneration: '+e.message;}
}
function setup(){createControls();configureMode();$('observing-mode').onchange=switchMode;$('reload').onclick=()=>load();$('regenerate').onclick=regenerateCache;$('export').onclick=exportCsv;$('methods').onclick=()=>$('methods-dialog').showModal();$('close-methods').onclick=()=>$('methods-dialog').close();$('search').oninput=()=>renderList(true);$('list-sort').onchange=()=>renderList(true);$('list-prev').onclick=()=>{state.offset=Math.max(0,(state.offset||0)-100);renderList();};$('list-next').onclick=()=>{state.offset=(state.offset||0)+100;renderList();};$('previous-target').onclick=()=>navigateTarget(-1);$('next-target').onclick=()=>navigateTarget(1);$('reset-filters').onclick=()=>{resetValues();for(const input of document.querySelectorAll('#aids input'))input.checked=aidDefault(input.value);for(const input of document.querySelectorAll('#observables input'))input.checked=observableDefault(input.value);update();};for(const which of ['all','none'])$('aids-'+which).onclick=()=>{for(const input of $('aids').querySelectorAll('input'))input.checked=which==='all';update();};$('fit').onclick=()=>{state.view=fitCurrent();draw();};$('reset-view').onclick=()=>{state.view=defaultView();draw();};for(const id of ['tracks','jitter'])$(id).onchange=draw;for(const id of ['xlog','ylog','y-axis'])$(id).onchange=()=>{state.view=fitCurrent();$('ylog').disabled=spectralYAxis();draw();};
  $('gnirs-only').onchange=()=>renderList(true);
  document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)||$('methods-dialog').open||document.activeElement===$('inspector-resizer'))return;if(e.key.toLowerCase()==='o'&&state.active){e.preventDefault();$('report').click();}else if(['ArrowUp','ArrowLeft'].includes(e.key)){e.preventDefault();navigateTarget(-1);}else if(['ArrowDown','ArrowRight'].includes(e.key)){e.preventDefault();navigateTarget(1);}});
  const inspector=$('inspector'),handle=$('inspector-resizer');let drag=null;function resize(height){const max=inspector.getBoundingClientRect().height+document.querySelector('.plot-area').getBoundingClientRect().height-140;inspector.style.height=Math.max(130,Math.min(max,height))+'px';}handle.onpointerdown=e=>{drag={y:e.clientY,h:inspector.getBoundingClientRect().height};handle.setPointerCapture(e.pointerId);};handle.onpointermove=e=>{if(drag)resize(drag.h+drag.y-e.clientY);};handle.onpointerup=()=>drag=null;handle.onpointercancel=()=>drag=null;handle.ondblclick=()=>inspector.style.removeProperty('height');handle.onkeydown=e=>{if(['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();resize(inspector.getBoundingClientRect().height+(e.key==='ArrowUp'?20:-20));}};
  $('refresh-sxd').onclick=refreshSxd;load(true);pollItc();
}
document.addEventListener('DOMContentLoaded',setup);
