/* Read-only findings atlas. Credentials and scientific data stay in tab memory. */
const FindingClasses = (() => {
  'use strict';
  const accepted = new Set(['good', 'good_candidate', 'contaminated_ucd', 'peculiar_ucd', 'good_plus_star']);
  const qualityRule = 'At least one SPIFFStacker, SPIFF or SUBLIMEaperture review is good, good_candidate, contaminated_ucd, peculiar_ucd or good_plus_star';
  const definitions = [
    {key:'known', label:'Known recovered', color:'#bc7a3d', detail:'Existing published spectroscopic status, including confirmed duplicate links; takes precedence over the other classes.'},
    {key:'confirmed', label:'New motion-confirmed', color:'#257d76', detail:qualityRule+'; WiseView score ≥ 5; not known recovered.'},
    {key:'candidate', label:'New candidate', color:'#397ac1', detail:qualityRule+'; WiseView score ≥ 3 and < 5; not known recovered.'},
    {key:'still', label:'Still candidates', color:'#9266b3', detail:qualityRule+'; WiseView score from 1 through 2 inclusive; not known recovered.'},
    {key:'others', label:'Others', color:'#939f99', detail:'Every other object allowed by the current filters, including missing or nonqualifying reviews.'},
  ];
  function classify(row) {
    if(row.known) return 'known';
    const qualifies=['spiffstacker','spiff','sublimeaperture'].some(lane=>accepted.has(String(row[lane+'_quality']??'').trim().toLowerCase()));
    const score=row.motion===null || row.motion===undefined || row.motion==='' ? NaN : Number(row.motion);
    if(!qualifies || !Number.isFinite(score)) return 'others';
    if(score>=5) return 'confirmed';
    if(score>=3) return 'candidate';
    if(score>=1 && score<=2) return 'still';
    return 'others';
  }
  function annotate(row) {
    const key=classify(row), definition=definitions.find(d=>d.key===key);
    return {...row,plot_class:key,plot_class_label:definition.label};
  }
  function groups(data,build) {
    return definitions.map(def=>{
      const selected=data.filter(row=>(row.plot_class || classify(row))===def.key);
      const trace=build(selected,def.label,def.color);
      return {...trace,legendgroup:def.key,showlegend:trace.showlegend??selected.length>0,
        meta:{...trace.meta,plot_class:def.key}};
    });
  }
  return {definitions,classify,annotate,groups};
})();
if(typeof module!=='undefined' && module.exports) module.exports=FindingClasses;
if(typeof document!=='undefined') (() => {
'use strict';
const $=id=>document.getElementById(id), esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const finite=Number.isFinite, fmt=(v,n=2)=>v==null||!finite(Number(v))?'—':Number(v).toFixed(n), num=v=>Number(v).toLocaleString();
const laneNames={spiffstacker:'SPIFFStacker',spiff:'SPIFF',sublimeaperture:'SUBLIME aperture'};
const sourceNames={sublime1:'SUBLIME1',sublime2:'SUBLIME2',redmovers:'CatWISE red movers',other:'Other unpublished'};
const spt=v=>!finite(Number(v))||v==null?'—':(v<0?'K'+fmt(10+Number(v),1):v<10?'M'+fmt(v,1):v<20?'L'+fmt(v-10,1):v<30?'T'+fmt(v-20,1):'Y'+fmt(v-30,1)).replace('.0','');
const ticks=Array.from({length:9},(_,i)=>i*5-5),ticktext=ticks.map(spt);
const classDefinitions=FindingClasses.definitions;
const url=new URL(location.href), params=new URLSearchParams(url.search), fragment=new URLSearchParams(location.hash.slice(1));
const mock=params.get('mock')==='1';
const getAuth=(keys)=>{for(const key of keys){const v=fragment.get(key)??params.get(key);if(v!==null)return v;}return '';};
const auth={'X-MOCA-User':getAuth(['user','username']),'X-MOCA-Password':getAuth(['pwd','password']),'X-MOCA-Database':getAuth(['dbase','db','database'])};
let rows=[],byId=new Map(),filters={},dataGeneration=0,loadController=null,tab='overview',flipPage=0,objectPage=0,flipGeneration=0,flipController=null;
let inspectorGeneration=0,inspectController=null,current=null,cutouts=[],cutIndex=0;
const fitCache=new Map();
const defaults={sources:['sublime2'],min_spt:10,min_motion:1,known:'no',byw:'no',byw_claim:'no',yadu:'no',azul:'no',smdet:'no',duplicates:'exclude',spt_source:'best',snr_lane:'spiffstacker',cutout_policy:'all',distance_mode:'astrometric',synthetic_lane:'any',quality_any:'good'};
function select(name,label,options){return `<label>${esc(label)}<select name="${name}">${options.map(o=>`<option value="${esc(o[0])}">${esc(o[1])}</option>`).join('')}</select></label>`;}
function input(name,label,placeholder='',step='any'){return `<label>${esc(label)}<input name="${name}" type="${step==='text'?'text':'number'}" ${step==='text'?'':`step="${step}"`} placeholder="${esc(placeholder)}"></label>`;}
function range(key,label){return `<label>${esc(label)}</label><div class="range">${input('min_'+key,'Minimum')}${input('max_'+key,'Maximum')}</div>`;}
function fs(title,html){return `<fieldset><legend>${esc(title)}</legend>${html}</fieldset>`;}
const laneOptions=Object.entries(laneNames).map(([k,v])=>[k,v]);
const triOptions=[['either','Either'],['yes','Present / yes'],['no','Absent / no']];
$('plot-classes').innerHTML=classDefinitions.map(d=>`<span class="plot-class" title="${esc(d.detail)}"><i style="background:${d.color}"></i>${esc(d.label)} <b id="class-count-${d.key}">—</b></span>`).join('');
$('filter-fields').innerHTML=
fs('Publication & duplicates',select('known','Published spectroscopic M0+ type',[['no','Unpublished candidates'],['yes','Known recovered'],['either','Both populations']])+select('duplicates','Confirmed duplicate entries',[['exclude','Exclude duplicates'],['either','Include all active entries'],['only','Duplicates only']]))+
fs('Spectral types',select('spt_source','Type used in plots & sorting',[['best','Best available (priority order)'],...laneOptions,['sublime2','SUBLIME2 candidate autotype'],['adopted','MOCAdb adopted type'],['published','Public spectroscopic type']])+range('spt','Selected spectral type number')+'<p class="hint">M0 = 0 · L0 = 10 · T0 = 20 · Y0 = 30</p>')+
fs('Detection & CNN',range('detection_snr','SUBLIME detection S/N')+range('cnn','SUBLIME2 CNN good probability')+input('cnn_classes','CNN classes','good, none','text'))+
fs('Spectral quality',select('quality_any','Across reductions',[['good','At least one good / good_candidate'],['one_good','At least one good'],['all_good','All available good'],['all_good_candidate','All available good/good candidate'],['any','No global spectral-quality cut'],['reviewed','At least one reviewed spectrum'],['unreviewed','Unreviewed in all three lanes']])+'<p class="hint">“Good” also includes contaminated_ucd, peculiar_ucd and good_plus_star, including per-lane include lists. Good/candidate also allows good_candidate. “All available” requires a passing review in every active reduction; missing reductions are skipped and unreviewed spectra fail.</p>')+
fs('Spectrum S/N',select('snr_lane','Reduction lane',laneOptions)+range('snr','Median S/N per pixel'))+
fs('Motion quality',range('motion','WiseView motion score')+input('motion_classes','Include motion classes','none = no review','text')+'<p class="hint">5–6 clear motion · 3–4 potential · 1–2 still · 1.5 M-type · 0.5 undetected · 0 unclear · −1 bad</p>')+
fs('SUBLIME cutout quality',input('min_cutout','Minimum cutout score','4 = centered & isolated')+select('cutout_policy','Combine reviewed cutouts',[['all','All reviewed cutouts must pass'],['any','At least one reviewed cutout passes']])+input('cutout_classes','Include cutout classes','none = no cutout review','text')+'<p class="hint">4 centered & isolated · 3 centered & crowded · 2 off-center & isolated · 1 off-center & crowded · −1 halo</p>')+
fs('Catalog & claim membership',select('byw','In BYW',triOptions)+select('byw_claim','In BYW claimlists',triOptions)+select('yadu',"In Yadu’s claimlist",triOptions)+select('azul',"In Azul’s July 16, 2026 table",triOptions)+select('smdet','Has an SMDET designation',triOptions))+
'<details class="filters-more" open><summary>Typing & visual-quality cuts by reduction</summary>'+Object.entries(laneNames).map(([k,v])=>fs(v,range(k+'_spt','Stored autotype number')+input('include_'+k,'Include visual classes','good, good_candidate, none','text')+input('exclude_'+k,'Exclude visual classes','bad, snr, scatter','text'))).join('')+'</details>'+
'<details class="filters-more"><summary>Photometry, distance & fit quality</summary>'+fs('Absolute W2',select('distance_mode','Distance selection',[['astrometric','Parallax / nonphotometric only'],['include_photometric','Allow photometric distances']])+input('min_parallax_snr','Minimum parallax S/N')+select('synthetic_lane','SPHEREx synthetic W2 reduction',[['any','Any available SPHEREx reduction'],...laneOptions])+range('w2','Measured apparent W2'))+fs('SUBLIME2 fit',range('chi2','Stored reduced χ²'))+'</details>';
function setFilters(f){$('filters').reset();for(const el of $('filters').elements){if(!el.name)continue;if(el.name==='sources'){el.checked=(f.sources||defaults.sources).includes(el.value);}else if(f[el.name]!==undefined&&f[el.name]!==null)el.value=String(f[el.name]);} $('dirty').textContent='Cuts combine with AND; blank cuts are disabled.';}
function readFilters(){const f={sources:[]};for(const el of $('filters').elements){if(!el.name)continue;if(el.name==='sources'){if(el.checked)f.sources.push(el.value);}else if(el.value!=='')f[el.name]=el.type==='number'?Number(el.value):el.value.trim();}return f;}
async function api(op,body,signal){const response=await fetch('api/findings/'+op,{method:'POST',headers:{'Content-Type':'application/json',...auth},body:JSON.stringify({...body,mock}),signal,cache:'no-store',referrerPolicy:'no-referrer'});let data;try{data=await response.json();}catch{throw Error('The server returned an unreadable response.');}if(!response.ok||!data.ok)throw Error(data.error||'Request failed.');return data;}
function safeLink(f){const u=new URL(location.href);u.search='';u.hash='';u.searchParams.set('filters',JSON.stringify(f));if(mock)u.searchParams.set('mock','1');return u.href;}
function showError(message){$('error').textContent=message;$('error').hidden=false;}
function purgePlots(root){for(const el of root.querySelectorAll('.js-plotly-plot'))Plotly.purge(el);}
async function load(){
 const f=readFilters();if(!f.sources.length){showError('Select at least one catalog.');return;}
 const seq=++dataGeneration;loadController?.abort();loadController=new AbortController();flipController?.abort();closeInspector();
 $('apply').disabled=true;$('download').disabled=true;$('error').hidden=true;$('status').textContent='Querying MOCAdb and loading the selected sample…';
 const timer=setInterval(()=>{if(seq===dataGeneration)$('status').textContent='Still loading: catalog selection, review flags, and photometry. Previous plots remain labeled below until the new sample is ready.';},15000);
 try{const result=await api('load',{filters:f},loadController.signal);if(seq!==dataGeneration)return;
  if(result.quality_definition_version!==2)throw Error('Restart the Findings Dashboard service to apply the expanded good spectral-quality categories.');
  rows=result.rows.map(FindingClasses.annotate);filters=f;byId=new Map(rows.map(r=>[r.moca_oid,r]));fitCache.clear();flipPage=0;objectPage=0;
  $('download').disabled=false; $('status').textContent=`${num(rows.length)} unique objects · ${num(result.preliminary)} passed initial type/catalog cuts · loaded in ${fmt(result.elapsed,1)} s${mock?' · synthetic demo':''}`;
  $('dirty').textContent='Filters applied. Blank cuts are disabled.';$('loaded-at').textContent='Updated '+new Date(result.loaded_at*1000).toLocaleString();
  for(const def of classDefinitions)$('class-count-'+def.key).textContent=num(rows.filter(r=>r.plot_class===def.key).length);
  $('count-total').textContent=num(rows.length);$('count-known').textContent=num(rows.filter(r=>r.known).length);$('count-new').textContent=num(rows.filter(r=>!r.known).length);
  const m=rows.filter(r=>finite(r.M_w2)).length,s=rows.filter(r=>finite(r.M_synthetic_w2)).length;
  $('count-mw2').textContent=num(m);$('count-mw2-note').textContent=`Measured: ${num(m)} · synthetic: ${num(s)}`;
  if(tab==='overview')renderCharts();else if(tab==='spectra')renderFlipbook();else renderObjects();
 }catch(e){if(e.name!=='AbortError'&&seq===dataGeneration){showError(e.message);$('status').textContent=rows.length?'Load failed. Plots still show the previously applied sample.':'Load failed. Adjust filters or check your Web Tools connection.';}}
 finally{clearInterval(timer);if(seq===dataGeneration)$('apply').disabled=false;}
}
function baseLayout(xlabel,ylabel){const axis={showgrid:true,gridcolor:'#e7ede8',showline:true,mirror:true,linecolor:'#48635d',linewidth:1.5,ticks:'outside',tickfont:{size:11},zeroline:false,automargin:true};return {paper_bgcolor:'#fff',plot_bgcolor:'#fff',font:{family:'DM Sans, system-ui, sans-serif',size:11,color:'#36534b'},margin:{l:62,r:21,t:24,b:57},xaxis:{...axis,title:{text:xlabel,standoff:12}},yaxis:{...axis,title:{text:ylabel,standoff:10}},legend:{orientation:'h',x:0,y:1.13,font:{size:10}},hovermode:'closest',uirevision:JSON.stringify(filters)};}
const plotConfig={responsive:true,displaylogo:false,modeBarButtonsToRemove:['select2d','lasso2d'],toImageButtonOptions:{format:'png',scale:2}};
function plot(id,traces,layout,clickable=true){const el=$(id);Plotly.react(el,traces,layout,plotConfig).then(()=>{el.removeAllListeners('plotly_click');if(clickable)el.on('plotly_click',event=>{const id=event.points?.[0]?.customdata?.[0];if(id&&byId.has(id))openInspector(byId.get(id));});});}
function spectralAxis(layout){layout.xaxis.tickmode='array';layout.xaxis.tickvals=ticks;layout.xaxis.ticktext=ticktext;return layout;}
function scatterTrace(data,x,y,name,color,extra={}){return {type:'scattergl',mode:'markers',x:data.map(x),y:data.map(y),name,marker:{size:7,color,opacity:.76,line:{color:'white',width:.5}},customdata:data.map(r=>[r.moca_oid,r.designation,spt(r.spt)]),text:data.map(r=>esc(r.designation)),hovertemplate:'%{text}<br>Object %{customdata[0]} · %{customdata[2]}<br>x: %{x:.3f} · y: %{y:.3f}<extra>'+name+'</extra>',...extra};}
function groups(data,fn){return FindingClasses.groups(data,fn);}
function emptyNote(layout,count){if(count)return;layout.annotations=[{text:'No objects with the required data under these cuts',showarrow:false,x:.5,y:.5,xref:'paper',yref:'paper',font:{color:'#7d8d85',size:12}}];}
function mollweide(ra,dec){const lon=(((ra-180+540)%360)-180)*Math.PI/180,lat=dec*Math.PI/180;let theta=lat;for(let i=0;i<20;i++){const d=2+2*Math.cos(2*theta);if(Math.abs(d)<1e-8)break;const step=(2*theta+Math.sin(2*theta)-Math.PI*Math.sin(lat))/d;theta-=step;if(Math.abs(step)<1e-9)break;}return [-2*Math.SQRT2/Math.PI*lon*Math.cos(theta),Math.SQRT2*Math.sin(theta)];}
function renderCharts(){
 const typed=rows.filter(r=>finite(r.spt)),bin=Number($('hist-bin').value),lo=typed.length?Math.min(...typed.map(r=>r.spt)):-5,hi=typed.length?Math.max(...typed.map(r=>r.spt)):35,start=Math.min(-5,Math.floor(lo/bin)*bin),end=Math.max(35,Math.ceil((hi+1)/bin)*bin),centers=[];for(let x=start;x<end;x+=bin)centers.push(x+bin/2);
 const hist=groups(typed,(data,name,color)=>{const count=centers.map(()=>0);for(const r of data){const i=Math.floor((r.spt-start)/bin);if(i>=0&&i<count.length)count[i]++;}return {type:'bar',x:centers,y:count,name,marker:{color},width:bin*.86,hovertemplate:'%{x}: %{y} objects<extra>'+name+'</extra>'};});
 let l=spectralAxis(baseLayout('Spectral type','Unique objects'));l.xaxis.range=[9,32];l.xaxis.tickvals=[9,10,15,20,25,30,32];l.xaxis.ticktext=l.xaxis.tickvals.map(spt);l.barmode='stack';emptyNote(l,typed.length);plot('histogram',hist,l,false);$('hist-note').textContent=`${num(typed.length)} typed objects · ${num(rows.length-typed.length)} without a selected type`;
 const skyRows=rows.filter(r=>finite(r.ra)&&finite(r.dec)),moll=$('sky-projection').value==='mollweide';
 l=baseLayout(moll?'Right ascension (ICRS)':'Right ascension (deg)','Declination (deg)');l.xaxis.range=moll?[-2.91,2.91]:[360,0];l.yaxis.range=moll?[-1.48,1.48]:[-90,90];
 let skyTraces=groups(skyRows,(d,n,c)=>scatterTrace(d,r=>moll?mollweide(r.ra,r.dec)[0]:r.ra,r=>moll?mollweide(r.ra,r.dec)[1]:r.dec,n,c,{hovertemplate:'%{text}<br>Object %{customdata[0]} · %{customdata[2]}<extra>'+n+'</extra>'}));
 if(moll){l.yaxis.tickvals=[-60,-30,0,30,60].map(d=>mollweide(180,d)[1]);l.yaxis.ticktext=['−60°','−30°','0°','30°','60°'];l.xaxis.tickvals=[360,300,240,180,120,60,0].map(r=>r===360?-2*Math.SQRT2:r===0?2*Math.SQRT2:mollweide(r,0)[0]);l.xaxis.ticktext=['360°','300°','240°','180°','120°','60°','0°'];l.yaxis.scaleanchor='x';const graticule=[];for(let d=-60;d<=60;d+=30){const p=Array.from({length:121},(_,i)=>mollweide(i*3,d));graticule.push({type:'scatter',mode:'lines',x:p.map(v=>v[0]),y:p.map(v=>v[1]),line:{color:'#dce5df',width:1},hoverinfo:'skip',showlegend:false});}skyTraces=[...graticule,...skyTraces];l.xaxis.showgrid=false;l.yaxis.showgrid=false;}
 emptyNote(l,skyRows.length);plot('sky',skyTraces,l);
 const measured=rows.filter(r=>finite(r.spt)&&finite(r.M_w2)),synthetic=rows.filter(r=>finite(r.spt)&&finite(r.M_synthetic_w2));
 const errors=(data,key)=>$('show-errors').checked?{type:'data',array:data.map(r=>r[key+'_unc']),visible:true,color:'#b5c4be',thickness:1,width:0}:{visible:false};
 const traces=groups(measured,(d,n,c)=>scatterTrace(d,r=>r.spt,r=>r.M_w2,n,c,{marker:{size:7,color:c,opacity:.8,symbol:d.map(r=>r.distance_kind==='photometric'?'triangle-up':'circle')},error_y:errors(d,'M_w2')}));
 if($('show-synth').checked)traces.push(...groups(synthetic,(d,n,c)=>scatterTrace(d,r=>r.spt,r=>r.M_synthetic_w2,n,c,{showlegend:d.length>0&&!measured.some(r=>r.plot_class_label===n),marker:{size:8,color:c,symbol:d.map(r=>r.distance_kind==='photometric'?'triangle-up-open':'diamond-open'),opacity:.85,line:{width:1.5}},error_y:errors(d,'M_synthetic_w2'),hovertemplate:'%{text}<br>SPHEREx synthetic W2<br>Object %{customdata[0]} · %{customdata[2]}<br>x: %{x:.3f} · y: %{y:.3f}<extra>'+n+'</extra>'})));
 l=spectralAxis(baseLayout('Spectral type','Absolute W2 (mag)'));l.yaxis.autorange='reversed';emptyNote(l,measured.length+($('show-synth').checked?synthetic.length:0));plot('cmd',traces,l);
 $('cmd-note').textContent=`${num(measured.length)} measured and ${num(synthetic.length)} synthetic points · ${num(rows.length-measured.length)} lack measured absolute W2 · ${rows.filter(r=>r.distance_kind==='photometric').length} use photometric distances (triangles) · error bars require magnitude and parallax uncertainties`;
 const paired=rows.filter(r=>finite(r.spt)&&finite(r.w2_difference));l=spectralAxis(baseLayout('Spectral type','Synthetic − measured W2 (mag)'));l.shapes=[{type:'line',xref:'paper',x0:0,x1:1,y0:0,y1:0,line:{color:'#c0ccc5',dash:'dot'}}];emptyNote(l,paired.length);plot('w2-residual',groups(paired,(d,n,c)=>scatterTrace(d,r=>r.spt,r=>r.w2_difference,n,c)),l);$('residual-note').textContent=`${num(paired.length)} objects have both W2 measurements. Useful for spotting calibration or contamination outliers.`;
 const moving=rows.filter(r=>finite(r.spt)&&finite(r.motion));l=spectralAxis(baseLayout('Spectral type','WiseView motion score'));l.yaxis.dtick=1;emptyNote(l,moving.length);plot('motion',groups(moving,(d,n,c)=>scatterTrace(d,r=>r.spt,r=>r.motion,n,c)),l);
 l=baseLayout('','Selected catalog memberships');l.margin={l:155,r:22,t:25,b:48};l.barmode='stack';l.yaxis.autorange='reversed';plot('recovery',groups(rows,(d,n,c)=>({type:'bar',orientation:'h',y:Object.values(sourceNames),x:Object.keys(sourceNames).map(k=>d.filter(r=>r[k]).length),name:n,marker:{color:c},hovertemplate:'%{y}<br>%{x} objects<extra>'+n+'</extra>'})),l,false);
}
function setTab(value){tab=value;document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===value));for(const name of ['overview','spectra','objects'])$('view-'+name).hidden=name!==value;if(value==='overview')renderCharts();if(value==='spectra')renderFlipbook();if(value==='objects')renderObjects();}
function fitKey(r,lane){return lane+':'+r.moca_oid+':'+r[lane+'_specid'];}
async function getFits(data,lane,signal){const missing=data.filter(r=>r[lane+'_specid']&&!fitCache.has(fitKey(r,lane)));if(missing.length){const result=await api('spectra',{lane,items:missing.map(r=>({moca_oid:r.moca_oid,moca_specid:r[lane+'_specid']}))},signal);for(const item of result.items){const r=byId.get(item.object.moca_oid)||data.find(r=>r.moca_oid===item.object.moca_oid);if(r){fitCache.set(fitKey(r,lane),item);while(fitCache.size>180)fitCache.delete(fitCache.keys().next().value);}}}return data.map(r=>fitCache.get(fitKey(r,lane)));}
function spectrumCard(r,lane,plotId,inspect=false){return `<article class="card spectrum-card"><div class="card-head"><div><h3>${inspect?esc(laneNames[lane]):esc(r.designation)}</h3><span class="badge">${esc(spt(r.spt))}</span></div>${inspect?'':`<button data-inspect="${r.moca_oid}">Inspect ↗</button>`}</div><div class="spec-meta">${inspect?'':'OID '+r.moca_oid+' · '}${esc(laneNames[lane])} · spectrum ${r[lane+'_specid']||'unavailable'} · stored type ${esc(spt(r[lane+'_spt']))} · ${esc(r[lane+'_quality']||'unreviewed')}</div><div id="${plotId}" class="spec-plot"><div class="spec-empty">${r[lane+'_specid']?'Loading spectrum & best-fit template…':'No active spectrum in this reduction.'}</div></div></article>`;}
function renderFit(el,item,lane){if(!item){el.innerHTML='<div class="spec-empty">No active spectrum in this reduction.</div>';return;}if(item.error){el.innerHTML='<div class="spec-empty">'+esc(item.error)+'</div>';return;}const best=item.fit?.overlays?.[0];const meta=el.previousElementSibling;let label=meta?.querySelector('.fit-label');if(meta&&!label){label=document.createElement('div');label.className='fit-label';meta.append(label);}if(label)label.textContent=best?'Best template: '+best.label+' · χ²r = '+fmt(best.display_reduced_chi2,2):'No valid template fit'+(item.warning?' · '+item.warning:'');const figure=SpherexReviewPlot.figure(item,String(item.object.moca_specid),el.clientWidth,1,SpherexReviewPlot.lanes.find(v=>v.key===lane)?.color);figure.layout.height=Math.round(Math.min(510,Math.max(290,el.clientWidth))*(el.closest('#flipbook')?0.75:1));el.replaceChildren();Plotly.newPlot(el,figure.traces,figure.layout,plotConfig);}
function comparisonCard(r,plotId){
 const meta=SpherexReviewPlot.lanes.map(lane=>`<span style="color:${lane.color}">${esc(lane.label)}</span>: ${r[lane.key+'_specid']?'#'+r[lane.key+'_specid']:'unavailable'} · ${esc(spt(r[lane.key+'_spt']))} · ${esc(r[lane.key+'_quality']||'unreviewed')}`).join('<br>');
 return `<article class="card spectrum-card comparison-card"><div class="card-head"><div><h3>${esc(r.designation)}</h3><span class="badge">${esc(spt(r.spt))}</span></div><button data-inspect="${r.moca_oid}">Inspect ↗</button></div><div class="spec-meta">OID ${r.moca_oid}<br>${meta}</div><div id="${plotId}" class="spec-plot"><div class="spec-empty">Loading available spectra & their best templates…</div></div></article>`;
}
function renderComparison(el,r,items,errors){
 const available=Object.fromEntries(SpherexReviewPlot.lanes.filter(lane=>items[lane.key]&&!items[lane.key].error).map(lane=>[lane.key,items[lane.key]]));
 const first=Object.keys(available)[0],comparison={...available};delete comparison[first];
 const figure=SpherexReviewPlot.comparisonFigure({...available[first],lane:first||null,comparison,comparison_errors:errors},String(r.moca_oid),el.clientWidth,1,false);
 figure.layout.height=720;el.replaceChildren();Plotly.newPlot(el,figure.traces,figure.layout,plotConfig);
}
async function renderFlipbook(){
 const generation=++flipGeneration;flipController?.abort();flipController=new AbortController();
 const signal=flipController.signal,pageSize=Math.min(50,Math.max(1,parseInt($('flip-page-size').value,10)||50));
 const lanes=SpherexReviewPlot.lanes.map(lane=>lane.key);
 const data=$('available-only').checked?rows.filter(r=>lanes.some(lane=>r[lane+'_specid'])):rows;
 const pages=Math.ceil(data.length/pageSize);flipPage=Math.max(0,Math.min(flipPage,Math.max(0,pages-1)));
 const selected=data.slice(flipPage*pageSize,(flipPage+1)*pageSize);$('spectra-count').textContent=num(data.length);
 for(const suffix of ['','-bottom']){
  $('flip-position'+suffix).textContent=data.length?`${flipPage*pageSize+1}–${Math.min(data.length,(flipPage+1)*pageSize)} / ${num(data.length)} · page ${flipPage+1} of ${pages}`:'No spectra under these cuts';
  $('flip-prev'+suffix).textContent=`← Previous ${pageSize}`;$('flip-next'+suffix).textContent=`Next ${pageSize} →`;
  $('flip-prev'+suffix).disabled=flipPage===0;$('flip-next'+suffix).disabled=flipPage>=pages-1;
 }
 purgePlots($('flipbook'));$('flipbook').innerHTML=selected.map((r,i)=>comparisonCard(r,'flip-plot-'+i)).join('');
 if(!selected.length){$('flipbook').innerHTML='<p class="hint">No objects with available spectra under these cuts. Try disabling “Available spectra only”.</p>';return;}
 // Three bounded ten-spectrum requests per batch; render progressively.
 for(let offset=0;offset<selected.length;offset+=10){
  const batch=selected.slice(offset,offset+10);
  const results=await Promise.allSettled(lanes.map(lane=>getFits(batch,lane,signal)));
  if(generation!==flipGeneration)return;
  batch.forEach((r,i)=>{
   const items={},errors={};results.forEach((result,j)=>{
    const lane=lanes[j];
    if(result.status==='fulfilled'){items[lane]=result.value[i];if(items[lane]?.error)errors[lane]=items[lane].error;}
    else if(result.reason.name!=='AbortError')errors[lane]=result.reason.message;
   });renderComparison($('flip-plot-'+(offset+i)),r,items,errors);
  });
 }
}
function renderObjects(){const q=$('object-search').value.toLowerCase();const data=rows.filter(r=>(r.designation+' '+r.moca_oid).toLowerCase().includes(q));const pages=Math.ceil(data.length/50);objectPage=Math.max(0,Math.min(objectPage,Math.max(0,pages-1)));$('object-rows').innerHTML=data.slice(objectPage*50,objectPage*50+50).map(r=>`<tr data-inspect="${r.moca_oid}" tabindex="0" role="button" aria-label="Inspect ${esc(r.designation)}"><td>${esc(r.designation)}<small>OID ${r.moca_oid}</small></td><td>${esc(spt(r.spt))}<small>${esc(r.spt_source)}</small></td><td>${esc(spt(r.published_spt))}<small>${esc(r.plot_class_label)}</small></td><td>${r.samples.map(s=>esc(sourceNames[s])).join('<br>')}</td><td>${fmt(r.motion,1)}</td><td>${fmt(r.cnn)}</td><td>${fmt(r.w2)}</td><td>${fmt(r.M_w2)}</td><td>${r.byw?'BYW':'—'}<small>${[r.byw_claim?'BYW claim':'',r.yadu?'Yadu':'',r.azul?'Azul':'',r.smdet?'SMDET':''].filter(Boolean).join(' · ')||'no listed claims'}</small></td></tr>`).join('');$('objects-position').textContent=`${num(data.length)} objects · page ${pages?objectPage+1:0} / ${pages}`;$('objects-prev').disabled=objectPage===0;$('objects-next').disabled=objectPage>=pages-1;}
function wiseHash(r){return new URLSearchParams({ra:r.ra,dec:r.dec,size:30,band:3,speed:313,minbright:-50,maxbright:500,window:2.64664,diff_window:1,linear:1,color:'',zoom:20,border:0,gaia:1,invert:1,maxdyr:1,scandir:0,neowise:0,diff:0}).toString();}
function closeInspector(){inspectorGeneration++;inspectController?.abort();if($('inspector').open)$('inspector').close();$('wise-frame').src='about:blank';purgePlots($('inspect-spectra'));}
async function openInspector(r){
 closeInspector();current=r;cutouts=[];cutIndex=0;const generation=++inspectorGeneration;inspectController=new AbortController();const signal=inspectController.signal;
 $('wise-frame').removeAttribute('srcdoc');
 $('inspect-title').textContent=r.designation+' · '+spt(r.spt);$('inspect-meta').textContent=`OID ${r.moca_oid} · RA ${fmt(r.ra,6)}° · Dec ${fmt(r.dec,6)}° · ${r.plot_class_label} · ${r.samples.map(s=>sourceNames[s]).join(', ')}`;
 $('inspect-report').href='https://mocadb.ca/search/results?search-query=oid%28'+r.moca_oid+'%29&search-type=star';
 $('inspect-wise-link').href='http://byw.tools/wiseview-v2#'+wiseHash(r);
 $('inspect-spectra').innerHTML=['spiffstacker','spiff','sublimeaperture'].map(lane=>spectrumCard(r,lane,'inspect-'+lane,true)).join('');
 $('cutout-content').innerHTML='<div class="spec-empty">Loading locally available SUBLIME cutouts…</div>';$('cut-label').textContent='';$('cut-prev').disabled=true;$('cut-next').disabled=true;
 $('inspector').showModal();$('inspector').scrollTop=0;
 if(!mock&&finite(r.ra)&&finite(r.dec)){$('wise-frame').removeAttribute('srcdoc');$('wise-frame').src='wiseview-frame#'+wiseHash(r);}else $('wise-frame').srcdoc='<p style="font:14px system-ui;padding:20px">WiseView is unavailable in the synthetic demo.</p>';
 for(const lane of ['spiffstacker','spiff','sublimeaperture']){
  if(!r[lane+'_specid'])continue;
  getFits([r],lane,signal).then(items=>{if(generation===inspectorGeneration)renderFit($('inspect-'+lane),items[0],lane);}).catch(e=>{if(e.name!=='AbortError'&&generation===inspectorGeneration)$('inspect-'+lane).innerHTML='<div class="spec-empty">'+esc(e.message)+'</div>';});
 }
 api('cutouts',{moca_oid:r.moca_oid},signal).then(result=>{if(generation!==inspectorGeneration)return;cutouts=result.images;showCutout();if(!cutouts.length)$('cut-label').textContent=`${result.source_keys||0} catalog source keys · ${result.missing_cutouts||0} files unavailable locally`;}).catch(e=>{if(e.name!=='AbortError'&&generation===inspectorGeneration)$('cutout-content').innerHTML='<div class="spec-empty">'+esc(e.message)+'</div>';});
 renderFinders(generation,signal);
}
function showCutout(){$('cut-prev').disabled=cutouts.length<2;$('cut-next').disabled=cutouts.length<2;if(!cutouts.length){$('cutout-content').innerHTML='<div class="spec-empty">No SUBLIME cutout is available locally.<br>The source may belong only to another catalog, or its cutout disk may be unavailable.</div>';return;}const image=cutouts[cutIndex];$('cut-label').textContent=`${cutIndex+1} / ${cutouts.length} · ${image.source_key} · ${image.epochs.map(e=>e.sample+' '+fmt(e.epoch_yr,2)).join(' / ')}`;$('cutout-content').innerHTML='<img alt="SUBLIME source cutout" src="'+image.data+'">';}
let finderGeneration=0;
function renderFinders(generation=inspectorGeneration,signal=inspectController?.signal){
 const fgen=++finderGeneration,r=current;if(!r)return;
 $('finders').innerHTML=['2mass','ps1','nsc'].map(s=>`<article class="card"><div class="card-head"><h3>${{ '2mass':'2MASS',ps1:'PS1',nsc:'NSC DR2'}[s]}</h3></div><div class="image-content" id="finder-${s}"><div class="spec-empty">${mock?'Finder charts are disabled in demo mode.':'Resolving survey coverage…'}</div></div><p class="hint" id="finder-note-${s}"></p></article>`).join('');
 if(mock)return;
 for(const survey of ['2mass','ps1','nsc'])api('survey',{survey,ra:r.ra,dec:r.dec,fov:Number($('finder-fov').value)},signal).then(result=>{
  if(generation!==inspectorGeneration||fgen!==finderGeneration)return;
  if(!result.url){$('finder-'+survey).innerHTML='<div class="spec-empty">'+esc(result.error||'No survey coverage returned.')+'</div>';return;}
  const el=$('finder-'+survey),img=document.createElement('img');img.alt=result.label;img.referrerPolicy='no-referrer';img.src=result.url;if(result.flip_x)img.style.transform='scaleX(-1)';let settled=false;
  const timer=setTimeout(()=>{if(!settled&&el.isConnected){settled=true;el.innerHTML='<div class="spec-empty">Image service did not finish. <a target="_blank" rel="noreferrer" href="'+esc(result.url)+'">Open image ↗</a></div>';}},survey==='2mass'?60000:30000);
  img.onload=()=>{if(generation!==inspectorGeneration||fgen!==finderGeneration||settled)return;settled=true;clearTimeout(timer);el.replaceChildren(img);if(result.crosshair){const marker=document.createElement('span');marker.className='finder-crosshair';el.append(marker);}};
  img.onerror=()=>{if(generation!==inspectorGeneration||fgen!==finderGeneration||settled)return;settled=true;clearTimeout(timer);el.innerHTML='<div class="spec-empty">Image unavailable or no coverage.</div>';};
  $('finder-note-'+survey).textContent=result.label+' · '+result.orientation+(result.note?' · '+result.note:'');
 }).catch(e=>{if(e.name!=='AbortError'&&generation===inspectorGeneration&&fgen===finderGeneration)$('finder-'+survey).innerHTML='<div class="spec-empty">'+esc(e.message)+'</div>';});
}
function csvCell(v){let s=Array.isArray(v)?v.join('; '):v==null?'':String(v);if(typeof v==='string'&&/^[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}
function exportCSV(){const keys=[...new Set(rows.flatMap(Object.keys))];const content='\ufeff'+[keys.map(csvCell).join(','),...rows.map(r=>keys.map(k=>csvCell(r[k])).join(','))].join('\r\n');const blob=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=blob;a.download='sublime-findings-'+new Date().toISOString().slice(0,10)+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(blob),1000);}
$('filters').onsubmit=e=>{e.preventDefault();load();};$('filters').oninput=()=>{$('dirty').textContent='Filters changed — apply to update the sample.';};$('reset').onclick=()=>{setFilters(defaults);$('dirty').textContent='Filters reset — apply to update the sample.';};
$('refresh').onclick=load;$('download').onclick=exportCSV;
for(const [id,known] of [['preset-new','no'],['preset-known','yes'],['preset-all','either']])$(id).onclick=()=>{const f=readFilters();f.known=known;if(known==='yes'){f.spt_source='published';f.min_spt=10;f.quality_any='any';}else if(f.spt_source==='published')f.spt_source='best';setFilters(f);load();};
$('copy-cuts').onclick=async()=>{try{await navigator.clipboard.writeText(safeLink(readFilters()));$('copy-cuts').textContent='Filter link copied ✓';setTimeout(()=>$('copy-cuts').textContent='Copy filter link',2000);}catch{$('status').textContent='Could not copy automatically. Filter link: '+safeLink(readFilters());}};
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>setTab(b.dataset.tab));
for(const id of ['hist-bin','sky-projection','show-synth','show-errors'])$(id).onchange=renderCharts;
for(const id of ['available-only','flip-page-size'])$(id).onchange=()=>{flipPage=0;renderFlipbook();};
for(const suffix of ['','-bottom']){$('flip-prev'+suffix).onclick=()=>{flipPage--;renderFlipbook();};$('flip-next'+suffix).onclick=()=>{flipPage++;renderFlipbook();};}
$('object-search').oninput=()=>{objectPage=0;renderObjects();};$('objects-prev').onclick=()=>{objectPage--;renderObjects();};$('objects-next').onclick=()=>{objectPage++;renderObjects();};
document.addEventListener('click',e=>{const target=e.target.closest('[data-inspect]');if(target){const r=byId.get(Number(target.dataset.inspect));if(r)openInspector(r);}});
$('object-rows').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){const target=e.target.closest('[data-inspect]');if(target){e.preventDefault();target.click();}}});
$('inspect-close').onclick=closeInspector;$('inspector').addEventListener('cancel',e=>{e.preventDefault();closeInspector();});$('finder-fov').onchange=()=>renderFinders();
$('cut-prev').onclick=()=>{if(cutouts.length){cutIndex=(cutIndex+cutouts.length-1)%cutouts.length;showCutout();}};$('cut-next').onclick=()=>{if(cutouts.length){cutIndex=(cutIndex+1)%cutouts.length;showCutout();}};
window.addEventListener('keydown',e=>{if($('inspector').open||/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;if(tab==='spectra'&&(e.key==='ArrowRight'||e.key==='ArrowLeft')){const b=$(e.key==='ArrowRight'?'flip-next':'flip-prev');if(!b.disabled){e.preventDefault();b.click();}}});
window.addEventListener('resize',()=>{document.querySelectorAll('.js-plotly-plot').forEach(el=>{if(el.offsetWidth)Plotly.Plots.resize(el);});});
let initial={...defaults};try{if(params.has('filters'))initial={...defaults,...JSON.parse(params.get('filters'))};}catch{showError('The saved filter link is invalid. Default filters were restored.');}
setFilters(initial);$('demo-banner').hidden=!mock;
if(mock||auth['X-MOCA-Password'])load();else{$('status').textContent='Open this dashboard through Web Tools → Start & open to use your private MOCAdb connection.';$('apply').disabled=false;}
// Small, read-only hooks let the maintained browser probe exercise Plotly selection.
window.SublimeFindings={get rows(){return rows;},openObject:id=>{const r=byId.get(Number(id));if(r)openInspector(r);},spt,mollweide,plotClasses:classDefinitions,classify:FindingClasses.classify};
})();
