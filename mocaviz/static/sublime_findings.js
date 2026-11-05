/* SUBLIME findings atlas. Credentials and scientific data stay in tab memory. */
const FindingClasses = (() => {
  'use strict';
  const accepted = new Set(['good', 'good_candidate', 'contaminated_ucd', 'peculiar_ucd', 'good_plus_star']);
  const qualityRule = 'At least one SPIFFStacker, SPIFF or SUBLIMEaperture review is good, good_candidate, contaminated_ucd, peculiar_ucd or good_plus_star';
  const definitions = [
    {key:'known', label:'Known recovered', color:'#bc7a3d', detail:'Existing published spectroscopic status, including confirmed duplicate links; takes precedence over the other classes.'},
    {key:'claimed', label:'Claimed UCDs', color:'#b14e5a', detail:'BYW membership, a BYW, Yadu or Azul claim, or an SMDET designation. Applies after Known recovered and before the motion categories.'},
    {key:'confirmed', label:'New motion-confirmed', color:'#257d76', detail:qualityRule+'. WiseView score ≥ 5. Excludes known and claimed objects.'},
    {key:'candidate', label:'New candidate', color:'#397ac1', detail:qualityRule+'. WiseView score ≥ 3 and < 5. Excludes known and claimed objects.'},
    {key:'still', label:'Still candidates', color:'#9266b3', detail:qualityRule+'. WiseView score from 1 through 2 inclusive. Excludes known and claimed objects.'},
    {key:'others', label:'Others', color:'#939f99', detail:'Every other object allowed by the current filters, including missing or nonqualifying reviews.'},
  ];
  function classify(row) {
    if(row.known) return 'known';
    if(row.byw || row.byw_claim || row.yadu || row.azul || row.smdet) return 'claimed';
    const qualifies=['spiffstacker','spiff','sublimeaperture'].some(lane=>accepted.has(String(row[lane+'_quality']??'').trim().toLowerCase()));
    const score=row.motion===null || row.motion===undefined || row.motion==='' ? NaN : Number(row.motion);
    if(!qualifies || !Number.isFinite(score)) return 'others';
    if(score>=5) return 'confirmed';
    if(score>=3) return 'candidate';
    if(score>=1 && score<=2) return 'still';
    return 'others';
  }
  function isConfirmed(row,standard='good') {
    const score=row.motion==null || row.motion==='' ? NaN : Number(row.motion);
    return Number.isFinite(score) && score>=5 && ['spiffstacker','spiff','sublimeaperture'].some(lane=>{
      const quality=String(row[lane+'_quality']??'').trim().toLowerCase();
      return accepted.has(quality) && (standard==='good_candidate' || quality!=='good_candidate');
    });
  }
  function markerSymbol(row,base='circle',standard='good') {
    if(!isConfirmed(row,standard))return base;
    const open=base.endsWith('-open'),shape=open?base.slice(0,-5):base;
    const star={circle:'star',diamond:'star-diamond','triangle-up':'star-triangle-up'}[shape]||'star';
    return star+(open?'-open':'');
  }
  function diagnosticLane(row,choice='auto') {
    const lanes=['spiffstacker','spiff'].filter(lane=>row[lane+'_specid']&&!row[lane+'_ignored']);
    if(choice!=='auto')return lanes.includes(choice)?choice:null;
    const ranks=[['good','peculiar_ucd','late_m'],['contaminated_ucd','good_plus_star'],['good_candidate'],['incomplete_but_promising']];
    const rank=lane=>{const label=String(row[lane+'_quality']||'').trim().toLowerCase(),i=ranks.findIndex(group=>group.includes(label));return i<0?ranks.length:i;};
    return lanes.sort((a,b)=>rank(a)-rank(b))[0]||null;
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
  return {definitions,classify,annotate,groups,isConfirmed,markerSymbol,diagnosticLane};
})();
const FindingProbability = {
  epsilon:1e-6,
  logit(value) {
    if(!Number.isFinite(value)||value<0||value>1)return NaN;
    const p=Math.min(1-this.epsilon,Math.max(this.epsilon,value));
    return Math.log10(p)-Math.log10(1-p);
  },
};
const FindingSky = (() => {
  const systems = {
    radec:{x:'Right ascension (deg)',y:'Declination (deg)',note:'ICRS · east to the left'},
    galactic:{x:'Galactic longitude gl (deg)',y:'Galactic latitude gb (deg)',note:'Galactic · longitude increases to the left'},
    ecliptic:{x:'Ecliptic longitude λ (deg)',y:'Ecliptic latitude β (deg)',note:'Mean ecliptic J2000 · longitude increases to the left'},
  };
  // ICRS Cartesian rotations, generated with Astropy Galactic and
  // BarycentricMeanEcliptic(equinox=J2000); no observer parallax or epoch propagation.
  const rotations = {
    galactic:[[-0.054875657712591654,-0.8734370519556158,-0.48383507361671546],
              [0.49410943719272676,-0.4448297212232952,0.7469821839866675],
              [-0.8676661375596576,-0.19807633727300053,0.4559838136873016]],
    ecliptic:[[0.9999999999999941,-7.078368960971556e-8,8.056213977613186e-8],
              [3.2897004077419646e-8,0.9174821299149584,0.39777699944404793],
              [-1.0207044725484355e-7,-0.39777699944404304,0.9174821299149556]],
  };
  function transform(ra,dec,system='radec') {
    if(system==='radec')return [ra,dec];
    const rad=Math.PI/180,alpha=ra*rad,delta=dec*rad;
    const v=[Math.cos(delta)*Math.cos(alpha),Math.cos(delta)*Math.sin(alpha),Math.sin(delta)];
    const [x,y,z]=rotations[system].map(axis=>axis.reduce((sum,c,i)=>sum+c*v[i],0));
    return [(Math.atan2(y,x)/rad+360)%360,Math.atan2(z,Math.hypot(x,y))/rad];
  }
  return {systems,transform};
})();
if(typeof module!=='undefined' && module.exports) module.exports={...FindingClasses,skyCoordinates:FindingSky.transform,probabilityLogit:value=>FindingProbability.logit(value)};
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
let hasAstrometryPlots=false;
let inspectorGeneration=0,inspectController=null,current=null,cutouts=[],cutIndex=0;
const fitCache=new Map();
let diagnosticController=null,diagnosticDone=0,diagnosticTotal=0,diagnosticFailed=0,diagnosticRenderTimer=null;
const defaults={sources:Object.keys(sourceNames),min_spt:10,min_motion:1,known:'no',byw:'either',byw_claim:'either',yadu:'either',azul:'either',smdet:'either',duplicates:'exclude',spt_source:'best',snr_lane:'spiffstacker',cutout_policy:'all',distance_mode:'astrometric',synthetic_lane:'any',quality_any:'good'};
function select(name,label,options){return `<label>${esc(label)}<select name="${name}">${options.map(o=>`<option value="${esc(o[0])}">${esc(o[1])}</option>`).join('')}</select></label>`;}
function input(name,label,placeholder='',step='any'){return `<label>${esc(label)}<input name="${name}" type="${step==='text'?'text':'number'}" ${step==='text'?'':`step="${step}"`} placeholder="${esc(placeholder)}"></label>`;}
function range(key,label){return `<label>${esc(label)}</label><div class="range">${input('min_'+key,'Minimum')}${input('max_'+key,'Maximum')}</div>`;}
function fs(title,html){return `<fieldset><legend>${esc(title)}</legend>${html}</fieldset>`;}
const laneOptions=Object.entries(laneNames).map(([k,v])=>[k,v]);
const triOptions=[['either','Either'],['yes','Present / yes'],['no','Absent / no']];
$('plot-classes').innerHTML=classDefinitions.map(d=>`<span class="plot-class" title="${esc(d.detail)}"><i style="background:${d.color}"></i>${esc(d.label)} <b id="class-count-${d.key}">—</b></span>`).join('');
$('filter-fields').innerHTML=
fs('Publication & duplicates',select('known','Published spectroscopic M0+ type',[['no','Unpublished'],['yes','Known recovered'],['either','Both populations']])+select('duplicates','Confirmed duplicate entries',[['exclude','Exclude duplicates'],['either','Include all active entries'],['only','Duplicates only']]))+
fs('Spectral types',select('spt_source','Type used in plots & sorting',[['best','Preferred type (ranked)'],...laneOptions,['sublime2','SUBLIME2 candidate autotype'],['adopted','MOCAdb adopted type'],['published','Public spectroscopic type']])+range('spt','Selected spectral type number')+'<p class="hint">M0 = 0 · L0 = 10 · T0 = 20 · Y0 = 30</p>')+
fs('Detection & CNN',range('detection_snr','SUBLIME detection S/N')+range('cnn','SUBLIME2 CNN good probability')+input('cnn_classes','CNN classes','good, none','text'))+
fs('Spectral quality',select('quality_any','Across reductions',[['good','At least one good / good_candidate'],['one_good','At least one good'],['all_good','All available good'],['all_good_candidate','All available good/good candidate'],['any','No global spectral-quality cut'],['reviewed','At least one reviewed spectrum'],['unreviewed','Unreviewed in all three lanes']])+'<p class="hint">“Good” also includes contaminated_ucd, peculiar_ucd and good_plus_star, including per-lane include lists. Good/candidate also allows good_candidate. “All available” requires a passing review in every active reduction; missing reductions are skipped and unreviewed spectra fail.</p>')+
fs('Spectrum S/N',select('snr_lane','Reduction lane',laneOptions)+range('snr','Median S/N per pixel'))+
fs('Motion quality',range('motion','WiseView motion score')+input('motion_classes','Include motion classes','none = no review','text')+'<p class="hint">5–6 clear motion · 3–4 potential · 1–2 still · 1.5 M-type · 0.5 undetected · 0 unclear · −1 bad</p><p class="hint">Known recovered objects bypass these cuts.</p>')+
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
 const seq=++dataGeneration;diagnosticController?.abort();loadController?.abort();loadController=new AbortController();flipController?.abort();closeInspector();
 $('apply').disabled=false;$('download').disabled=true;$('error').hidden=true;$('status').textContent='Querying MOCAdb and loading the selected sample… You can change cuts and Apply again while this loads.';
 const timer=setInterval(()=>{if(seq===dataGeneration)$('status').textContent='Still loading: catalog selection, review flags, and photometry. You can change cuts and Apply again; previous plots stay labeled until the new sample is ready.';},15000);
 try{const result=await api('load',{filters:f},loadController.signal);if(seq!==dataGeneration)return;
  if(result.quality_definition_version!==2)throw Error('Restart the Findings Dashboard service to apply the expanded good spectral-quality categories.');
  if((f.spt_source||'best')==='best' && result.type_priority_version!==1)throw Error('Restart the Findings Dashboard service to apply the adopted and review-ranked type priority.');
  if(f.sources.includes('other') && result.other_sample_version!==1)throw Error('Restart the Findings Dashboard service to load the updated Other unpublished MOCAdb sample.');
  hasAstrometryPlots=result.astrometry_plot_version===1;
  rows=result.rows.map(FindingClasses.annotate);filters=f;byId=new Map(rows.map(r=>[r.moca_oid,r]));fitCache.clear();flipPage=0;objectPage=0;resetDuplicates();
  $('download').disabled=false; $('status').textContent=`${num(rows.length)} unique objects · ${num(result.preliminary)} passed initial type/catalog cuts · loaded in ${fmt(result.elapsed,1)} s${mock?' · synthetic demo':''}`;
  $('dirty').textContent='Filters applied. Blank cuts are disabled.';$('loaded-at').textContent='Updated '+new Date(result.loaded_at*1000).toLocaleString();
  for(const def of classDefinitions)$('class-count-'+def.key).textContent=num(rows.filter(r=>r.plot_class===def.key).length);
  $('count-total').textContent=num(rows.length);$('count-known').textContent=num(rows.filter(r=>r.known).length);$('count-new').textContent=num(rows.filter(r=>!r.known).length);
  const m=rows.filter(r=>finite(r.M_w2)).length,s=rows.filter(r=>finite(r.M_synthetic_w2)).length;
  $('count-mw2').textContent=num(m);$('count-mw2-note').textContent=`Measured: ${num(m)} · synthetic: ${num(s)}`;
  setTab(tab);if(result.spectral_diagnostics_version===1)loadDiagnostics(seq);else $('diagnostics-status').textContent='Restart the Findings Dashboard service to load spectral diagnostics.';
 }catch(e){if(e.name!=='AbortError'&&seq===dataGeneration){showError(e.message);$('status').textContent=rows.length?'Load failed. Plots still show the previously applied sample.':'Load failed. Adjust filters or check your Web Tools connection.';}}
 finally{clearInterval(timer);if(seq===dataGeneration)$('apply').disabled=false;}
}
function baseLayout(xlabel,ylabel){const axis={showgrid:true,gridcolor:'#e7ede8',showline:true,mirror:true,linecolor:'#48635d',linewidth:1.5,ticks:'outside',tickfont:{size:11},zeroline:false,automargin:true};return {paper_bgcolor:'#fff',plot_bgcolor:'#fff',font:{family:'DM Sans, system-ui, sans-serif',size:11,color:'#36534b'},margin:{l:62,r:21,t:24,b:57},xaxis:{...axis,title:{text:xlabel,standoff:12}},yaxis:{...axis,title:{text:ylabel,standoff:10}},legend:{orientation:'h',x:0,y:1.13,font:{size:10}},hovermode:'closest',uirevision:JSON.stringify(filters)};}
const plotConfig={responsive:true,displaylogo:false,modeBarButtonsToRemove:['select2d','lasso2d'],toImageButtonOptions:{format:'png',scale:2}};
function plot(id,traces,layout,clickable=true){const el=$(id);Plotly.react(el,traces,layout,plotConfig).then(()=>{el.removeAllListeners('plotly_click');if(clickable)el.on('plotly_click',event=>{const id=event.points?.[0]?.customdata?.[0];if(id&&byId.has(id))openInspector(byId.get(id));});});}
function spectralAxis(layout){layout.xaxis.tickmode='array';layout.xaxis.tickvals=ticks;layout.xaxis.ticktext=ticktext;return layout;}
function confirmationStandard(){return $('confirmation-standard').value;}
function isConfirmed(row){return FindingClasses.isConfirmed(row,confirmationStandard());}
function pointSymbol(row,base='circle'){return FindingClasses.markerSymbol(row,base,confirmationStandard());}
function pointSize(row,base=7){return base+(isConfirmed(row)?3:0);}
function scatterTrace(data,x,y,name,color,extra={}){return {type:'scattergl',mode:'markers',x:data.map(x),y:data.map(y),name,marker:{size:data.map(r=>pointSize(r)),color,opacity:.76,symbol:data.map(r=>pointSymbol(r)),line:{color:'white',width:.5}},customdata:data.map(r=>[r.moca_oid,r.designation,spt(r.spt)]),text:data.map(r=>esc(r.designation)),hovertemplate:'%{text}<br>Object %{customdata[0]} · %{customdata[2]}<br>x: %{x:.3f} · y: %{y:.3f}<extra>'+name+'</extra>',...extra};}
function jitteredSpectralType(row){
 const hash=Math.imul(row.moca_oid,0x9e3779b1)>>>0;
 return row.spt+(hash/0x100000000-.5)*.4;
}
function spectralScatterTrace(data,y,name,color,extra={}){
 return scatterTrace(data,jitteredSpectralType,y,name,color,{
  hovertemplate:'%{text}<br>Object %{customdata[0]} · %{customdata[2]}<br>y: %{y:.3f}<extra>'+name+'</extra>',
  ...extra
 });
}
function groups(data,fn){return FindingClasses.groups(data,fn);}
function emptyNote(layout,count,text='No objects with the required data under these cuts'){if(count)return;layout.annotations=[{text,showarrow:false,x:.5,y:.5,xref:'paper',yref:'paper',font:{color:'#7d8d85',size:12}}];}
function renderCharts(){
 const typed=rows.filter(r=>finite(r.spt)),bin=Number($('hist-bin').value);
 const lo=typed.length?Math.min(...typed.map(r=>r.spt)):-5;
 const hi=typed.length?Math.max(...typed.map(r=>r.spt)):35;
 // Integer subtypes are centered in their bins, with edges at half subtypes.
 const binEdge=type=>Math.floor((type+0.5)/bin)*bin-0.5;
 const start=binEdge(Math.min(-5,lo)),last=binEdge(Math.max(35,hi)),centers=[];
 for(let edge=start;edge<=last;edge+=bin)centers.push(edge+bin/2);
 const hist=groups(typed,(data,name,color)=>{const count=centers.map(()=>0);for(const r of data){const i=Math.floor((r.spt-start)/bin);if(i>=0&&i<count.length)count[i]++;}return {type:'bar',x:centers,y:count,name,marker:{color},width:bin*.86,hovertemplate:'%{x}: %{y} objects<extra>'+name+'</extra>'};});
 let l=spectralAxis(baseLayout('Spectral type','Unique objects'));l.xaxis.range=[binEdge(9),binEdge(32)+bin];l.xaxis.tickvals=[9,10,15,20,25,30,32];l.xaxis.ticktext=l.xaxis.tickvals.map(spt);
 l.yaxis.type=$('hist-ylog').checked?'log':'linear';
 l.yaxis.uirevision=l.uirevision+':'+l.yaxis.type;
 l.barmode='stack';emptyNote(l,typed.length);plot('histogram',hist,l,false);$('hist-note').textContent=`${num(typed.length)} typed objects · ${num(rows.length-typed.length)} without a selected type`;
 const skySystem=$('sky-projection').value,skyFrame=FindingSky.systems[skySystem];
 const skyRows=rows.filter(r=>finite(r.ra)&&finite(r.dec)).map(r=>({...r,skyCoordinates:FindingSky.transform(r.ra,r.dec,skySystem)}));
 l=baseLayout(skyFrame.x,skyFrame.y);l.uirevision+=':sky:'+skySystem;
 l.xaxis.range=[360,0];l.xaxis.dtick=60;l.yaxis.range=[-90,90];l.yaxis.dtick=30;
 const skyTraces=groups(skyRows,(d,n,c)=>scatterTrace(d,r=>r.skyCoordinates[0],r=>r.skyCoordinates[1],n,c,{
  hovertemplate:'%{text}<br>Object %{customdata[0]} · %{customdata[2]}<br>'+skyFrame.x+': %{x:.3f}<br>'+skyFrame.y+': %{y:.3f}<extra>'+n+'</extra>'
 }));
 $('sky-note').textContent=skyFrame.note+' · color shows object class';
 emptyNote(l,skyRows.length);plot('sky',skyTraces,l);
 const measured=rows.filter(r=>finite(r.spt)&&finite(r.M_w2)),synthetic=rows.filter(r=>finite(r.spt)&&finite(r.M_synthetic_w2));
 const errors=(data,key)=>$('show-errors').checked?{type:'data',array:data.map(r=>r[key+'_unc']),visible:true,color:'#b5c4be',thickness:1,width:0}:{visible:false};
 const traces=groups(measured,(d,n,c)=>spectralScatterTrace(d,r=>r.M_w2,n,c,{marker:{size:d.map(r=>pointSize(r)),color:c,opacity:.8,symbol:d.map(r=>pointSymbol(r,r.distance_kind==='photometric'?'triangle-up':'circle'))},error_y:errors(d,'M_w2')}));
 if($('show-synth').checked)traces.push(...groups(synthetic,(d,n,c)=>spectralScatterTrace(d,r=>r.M_synthetic_w2,n,c,{showlegend:d.length>0&&!measured.some(r=>r.plot_class_label===n),marker:{size:d.map(r=>pointSize(r,8)),color:c,symbol:d.map(r=>pointSymbol(r,r.distance_kind==='photometric'?'triangle-up-open':'diamond-open')),opacity:.85,line:{width:1.5}},error_y:errors(d,'M_synthetic_w2'),hovertemplate:'%{text}<br>SPHEREx synthetic W2<br>Object %{customdata[0]} · %{customdata[2]}<br>y: %{y:.3f}<extra>'+n+'</extra>'})));
 l=spectralAxis(baseLayout('Spectral type','Absolute W2 (mag)'));l.yaxis.autorange='reversed';emptyNote(l,measured.length+($('show-synth').checked?synthetic.length:0));plot('cmd',traces,l);
 $('cmd-note').textContent=`${num(measured.length)} measured and ${num(synthetic.length)} synthetic points · ${num(rows.length-measured.length)} lack measured absolute W2 · ${rows.filter(r=>r.distance_kind==='photometric').length} use photometric distances (triangle / star-triangle markers) · error bars require magnitude and parallax uncertainties`;
 const paired=rows.filter(r=>finite(r.spt)&&finite(r.w2_difference));l=spectralAxis(baseLayout('Spectral type','Synthetic − measured W2 (mag)'));l.shapes=[{type:'line',xref:'paper',x0:0,x1:1,y0:0,y1:0,line:{color:'#c0ccc5',dash:'dot'}}];emptyNote(l,paired.length);plot('w2-residual',groups(paired,(d,n,c)=>spectralScatterTrace(d,r=>r.w2_difference,n,c)),l);$('residual-note').textContent=`${num(paired.length)} objects have both W2 measurements. Useful for spotting calibration or contamination outliers.`;
 const detections=rows.filter(r=>r.sublime2&&finite(r.spt)&&finite(r.sublime2_detection_snr)),detected=detections.filter(r=>r.sublime2_detection_snr>0);
 l=spectralAxis(baseLayout('Spectral type','SUBLIME2 detection S/N'));l.yaxis.type='log';emptyNote(l,detected.length);
 plot('sublime2-detection-snr',groups(detected,(d,n,c)=>spectralScatterTrace(d,r=>r.sublime2_detection_snr,n,c,{
  type:'scatter',hovertemplate:'%{text}<br>Object %{customdata[0]} · %{customdata[2]}<br>SUBLIME2 detection S/N: %{y:.2f}<extra>'+n+'</extra>'
 })),l);
 $('sublime2-detection-snr-note').textContent=`${num(detected.length)} SUBLIME2 objects · ${num(rows.filter(r=>r.sublime2&&finite(r.spt)).length-detections.length)} missing detection S/N · SUBLIME2 catalog measurement · log y-axis${detections.length>detected.length?' · '+num(detections.length-detected.length)+' nonpositive values omitted':''}`;
 const moving=rows.filter(r=>finite(r.spt)&&finite(r.motion));l=spectralAxis(baseLayout('Spectral type','WiseView motion score'));l.yaxis.dtick=1;emptyNote(l,moving.length);plot('motion',groups(moving,(d,n,c)=>spectralScatterTrace(d,r=>r.motion,n,c)),l);
 const astrometryNote=hasAstrometryPlots?undefined:'Restart the Findings Dashboard service to load astrometry data.';
 const withProperMotion=typed.filter(r=>finite(r.pmtot_masyr));
 const positiveProperMotion=withProperMotion.filter(r=>r.pmtot_masyr>0);
 l=spectralAxis(baseLayout('Spectral type','Total proper motion (mas/yr)'));
 l.yaxis.type='log';
 emptyNote(l,positiveProperMotion.length,astrometryNote);
 plot('proper-motion',groups(positiveProperMotion,(d,n,c)=>spectralScatterTrace(d,r=>r.pmtot_masyr,n,c,{
  hovertemplate:'%{text}<br>Object %{customdata[0]} · %{customdata[2]}<br>Adopted total proper motion: %{y:.1f} mas/yr<extra>'+n+'</extra>'
 })),l);
 const nonpositiveCount=withProperMotion.length-positiveProperMotion.length;
 const nonpositiveNote=nonpositiveCount?` · ${num(nonpositiveCount)} nonpositive values omitted`:'';
 $('proper-motion-note').textContent=astrometryNote??`${num(positiveProperMotion.length)} plotted on a log scale · ${num(typed.length-withProperMotion.length)} typed objects without a measurement${nonpositiveNote}`;
 const distances=typed.filter(r=>finite(r.adopted_distance_pc)&&r.adopted_distance_pc>0);
 const distanceSymbols={photometric:'triangle-up',trigonometric:'circle',nonphotometric:'diamond'};
 l=spectralAxis(baseLayout('Spectral type','Adopted distance (pc)'));
 l.yaxis.type='log';
 emptyNote(l,distances.length,astrometryNote);
 plot('adopted-distance',groups(distances,(d,n,c)=>spectralScatterTrace(d,r=>r.adopted_distance_pc,n,c,{
  marker:{size:d.map(r=>pointSize(r,8)),color:c,opacity:.76,symbol:d.map(r=>pointSymbol(r,distanceSymbols[r.adopted_distance_kind]||'circle')),line:{color:'white',width:.5}},
  text:d.map(r=>esc(r.designation)+'<br>'+r.adopted_distance_kind+' distance'),
  hovertemplate:'%{text}<br>Object %{customdata[0]} · %{customdata[2]}<br>Adopted distance: %{y:.2f} pc<extra>'+n+'</extra>'
 })),l);
 const otherDistance=distances.some(r=>r.adopted_distance_kind==='nonphotometric')?' · ◆ Nonphotometric, no parallax link':'';
 $('adopted-distance-note').textContent=astrometryNote??`▲ Photometric · ● Trigonometric${otherDistance} · star-shaped variants pass the selected confirmation standard · ${num(distances.length)} plotted on a log scale`;
 l=baseLayout('','Selected catalog memberships');l.margin={l:155,r:22,t:25,b:48};l.barmode='stack';l.yaxis.autorange='reversed';plot('recovery',groups(rows,(d,n,c)=>({type:'bar',orientation:'h',y:Object.values(sourceNames),x:Object.keys(sourceNames).map(k=>d.filter(r=>r[k]).length),name:n,marker:{color:c},hovertemplate:'%{y}<br>%{x} objects<extra>'+n+'</extra>'})),l,false);
 renderDiagnostics();
}
function renderDiagnostics(){
 const statistic=$('snr-statistic').value,band=$('snr-band').value;
 const names={all:'all wavelengths',nir:'1–2.5 µm',mid:'2.5–4 µm',red:'4–5 µm'};
 for(const lane of ['sublimeaperture','spiffstacker','spiff']){
  const available=rows.filter(r=>finite(r.spt)&&finite(r.diagnostics?.[lane]?.snr?.[band]?.[statistic])),data=available.filter(r=>r.diagnostics[lane].snr[band][statistic]>0);
  const layout=spectralAxis(baseLayout('Spectral type',`${statistic==='mean'?'Mean':'Median'} S/N per pixel`));layout.yaxis.type='log';
  emptyNote(layout,data.length,diagnosticDone<diagnosticTotal?'Loading spectral diagnostics…':'No valid spectral S/N in this range');
  plot('snr-'+lane,groups(data,(d,n,c)=>spectralScatterTrace(d,r=>r.diagnostics[lane].snr[band][statistic],n,c,{
   type:'scatter',text:d.map(r=>esc(r.designation)+'<br>'+laneNames[lane]+' #'+r.diagnostics[lane].moca_specid+' · '+r.diagnostics[lane].snr[band].count+' valid pixels · '+names[band])
  })),layout);
  $('snr-'+lane+'-note').textContent=`${num(data.length)} objects · ${names[band]} · ${statistic==='mean'?'arithmetic mean':'median'} of valid Fλ / uncertainty values · log y-axis${available.length>data.length?' · '+num(available.length-data.length)+' nonpositive values omitted':''}`;
 }
 for(const metric of ['chi2','cnn']){
  const choice=$(metric+'-lane').value;
  const data=rows.map(r=>{const lane=FindingClasses.diagnosticLane(r,choice),value=r.diagnostics?.[lane]?.[metric];return {...r,diagnostic_lane:lane,diagnostic_value:value};})
    .filter(r=>finite(r.spt)&&finite(r.diagnostic_value)&&(metric!=='cnn'||(r.diagnostic_value>=0&&r.diagnostic_value<=1)));
  const layout=spectralAxis(baseLayout('Spectral type',metric==='chi2'?'Stored reduced χ²':'CNN P(good)'));
  if(metric==='cnn'){
   layout.yaxis.title.text='CNN P(good) · log-odds scale';
   layout.yaxis.range=[-6.12,6.12];layout.yaxis.uirevision=layout.uirevision+':cnn-logit';
   layout.yaxis.tickmode='array';
   layout.yaxis.tickvals=[1e-6,1e-4,.01,.1,.5,.9,.99,.9999,1-1e-6].map(p=>FindingProbability.logit(p));
   layout.yaxis.ticktext=['≤0.000001','0.0001','0.01','0.1','0.5','0.9','0.99','0.9999','≥0.999999'];
  }
  emptyNote(layout,data.length,diagnosticDone<diagnosticTotal?'Loading spectral diagnostics…':'No matching stored '+(metric==='chi2'?'fit χ²':'CNN probabilities'));
  plot('fit-'+metric,groups(data,(d,n,c)=>spectralScatterTrace(d,r=>metric==='cnn'?FindingProbability.logit(r.diagnostic_value):r.diagnostic_value,n,c,{
   ...(metric==='cnn'?{customdata:d.map(r=>[r.moca_oid,r.designation,spt(r.spt),r.diagnostic_value]),hovertemplate:'%{text}<br>Object %{customdata[0]} · %{customdata[2]}<br>CNN P(good): %{customdata[3]:.8g}<extra>'+n+'</extra>'}:{}),
   type:'scatter',text:d.map(r=>esc(r.designation)+'<br>'+laneNames[r.diagnostic_lane]+' #'+r.diagnostics[r.diagnostic_lane].moca_specid+'<br>'+esc(r.diagnostics[r.diagnostic_lane][metric==='chi2'?'fit_source':'cnn_source']||''))
  })),layout);
  $(metric+'-note').textContent=`${num(data.length)} plotted · ${num(rows.filter(r=>finite(r.spt)).length-data.length)} missing for the selected lane · `+(choice==='auto'?'automatic classification ranking; SPIFFStacker wins ties':laneNames[choice])+(metric==='cnn'?' · log-odds scale stretches both probability tails; values ≤0.000001 or ≥0.999999 share the edges (including exact 0 and 1). Hover shows the stored probability.':'');
 }
 $('diagnostics-status').textContent=`Spectral diagnostics: ${num(diagnosticDone)} / ${num(diagnosticTotal)} active spectra checked${diagnosticFailed?' · '+num(diagnosticFailed)+' requests failed; Apply filters to retry':''}. Values update progressively. Missing measurements are omitted.`;
}
function queueDiagnosticRender(){if(diagnosticRenderTimer)return;diagnosticRenderTimer=setTimeout(()=>{diagnosticRenderTimer=null;if(tab==='overview')renderDiagnostics();},300);}
async function loadDiagnostics(seq){
 diagnosticController?.abort();diagnosticController=new AbortController();
 const signal=diagnosticController.signal,items=[];
 for(const r of rows){r.diagnostics={};for(const lane of Object.keys(laneNames))if(r[lane+'_specid']&&!r[lane+'_ignored'])items.push({moca_oid:r.moca_oid,moca_specid:r[lane+'_specid'],lane});}
 diagnosticDone=0;diagnosticFailed=0;diagnosticTotal=items.length;
 if(tab==='overview')renderDiagnostics();
 let cursor=0;
 const worker=async()=>{while(cursor<items.length&&!signal.aborted&&seq===dataGeneration){
  const batch=items.slice(cursor,cursor+96);cursor+=batch.length;
  try{
   const result=await api('diagnostics',{items:batch},signal);if(seq!==dataGeneration||signal.aborted)return;
   for(const item of result.items){const r=byId.get(item.moca_oid);if(r&&r[item.lane+'_specid']===item.moca_specid)r.diagnostics[item.lane]=item;}
  }catch(error){if(error.name==='AbortError')return;diagnosticFailed++;}
  diagnosticDone+=batch.length;queueDiagnosticRender();
 }};
 await Promise.all([worker(),worker()]);
}
function setTab(value){tab=value;document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===value));for(const name of ['overview','spectra','objects','duplicates'])$('view-'+name).hidden=name!==value;if(value==='overview')renderCharts();if(value==='spectra')renderFlipbook();if(value==='objects')renderObjects();if(value==='duplicates'){if(duplicateRows===null)scanDuplicates();else renderDuplicates();}}
function fitKey(r,lane){return lane+':'+r.moca_oid+':'+r[lane+'_specid'];}
async function getFits(data,lane,signal){const missing=data.filter(r=>r[lane+'_specid']&&!fitCache.has(fitKey(r,lane)));if(missing.length){const result=await api('spectra',{lane,items:missing.map(r=>({moca_oid:r.moca_oid,moca_specid:r[lane+'_specid']}))},signal);for(const item of result.items){const r=byId.get(item.object.moca_oid)||data.find(r=>r.moca_oid===item.object.moca_oid);if(r){fitCache.set(fitKey(r,lane),item);while(fitCache.size>180)fitCache.delete(fitCache.keys().next().value);}}}return data.map(r=>fitCache.get(fitKey(r,lane)));}
function spectrumLabel(r,lane){
 const id=r[lane+'_specid'];
 return id?'#'+id+(r[lane+'_ignored']?' · Ignored':''):'unavailable';
}
function reviewContext(r){
 const provenance=(Array.isArray(r.samples)?r.samples:Object.keys(sourceNames).filter(key=>r[key])).map(key=>sourceNames[key]||key).join(', ')||'not available';
 const claims=[['byw','BYW'],['byw_claim','BYW claimlist'],['yadu','Yadu claimlist'],['azul','Azul claimlist'],['smdet','SMDET designation']].filter(([key])=>r[key]).map(([,label])=>label);
 const status=[r.known?'Known recovered':'',claims.length?'Claimed UCD ('+claims.join(', ')+')':'',isConfirmed(r)?'Motion + spectrum confirmed':'Candidate / other under selected confirmation standard'].filter(Boolean);
 const score=r.motion!=null && r.motion!=='' && finite(Number(r.motion))?fmt(Number(r.motion),1):null;
 const motion=[r.motion_class,score==null?'':'score '+score].filter(Boolean).join(' · ')||'unreviewed';
 const classes=Array.isArray(r.cutout_classes)?r.cutout_classes:[],scores=Array.isArray(r.cutout_scores)?r.cutout_scores:[];
 const cutouts=Array.from({length:Math.max(classes.length,scores.length)},(_,i)=>{
  const value=scores[i],score=value!=null && value!=='' && finite(Number(value))?' [score '+fmt(Number(value),1)+']':'';
  return `${i+1}: ${classes[i]||'classification unavailable'}${score}`;
 }).join('; ')||'unreviewed';
 return `<div class="review-context"><div class="catalog-provenance"><b>Provenance:</b> ${esc(provenance)}</div><div class="membership-status"><b>Status:</b> ${esc(status.join(' · ')||r.plot_class_label||'Candidate / other')}</div><div class="motion-review"><b>Motion check:</b> ${esc(motion)}</div><div class="cutout-reviews"><b>SUBLIME cutout checks:</b> ${esc(cutouts)}</div></div>`;
}
function spectrumCard(r,lane,plotId,inspect=false){return `<article class="card spectrum-card"><div class="card-head"><div><h3>${inspect?esc(laneNames[lane]):esc(r.designation)}</h3><span class="badge">${esc(spt(r.spt))}</span></div>${inspect?'':`<button data-inspect="${r.moca_oid}">Inspect ↗</button>`}</div><div class="spec-meta">${inspect?'':'OID '+r.moca_oid+' · '}${esc(laneNames[lane])} · spectrum ${spectrumLabel(r,lane)} · stored type ${esc(spt(r[lane+'_spt']))} · ${esc(r[lane+'_quality']||'unreviewed')}${reviewContext(r)}</div><div id="${plotId}" class="spec-plot"><div class="spec-empty">${r[lane+'_specid']?'Loading spectrum & best-fit template…':'No stored spectrum in this reduction.'}</div></div></article>`;}
function renderFit(el,item,lane){if(!item){el.innerHTML='<div class="spec-empty">No stored spectrum in this reduction.</div>';return;}if(item.error){el.innerHTML='<div class="spec-empty">'+esc(item.error)+'</div>';return;}const best=item.fit?.overlays?.[0];const meta=el.previousElementSibling;let label=meta?.querySelector('.fit-label');if(meta&&!label){label=document.createElement('div');label.className='fit-label';meta.append(label);}if(label)label.textContent=best?'Best template: '+best.label+' · χ²r = '+fmt(best.display_reduced_chi2,2):'No valid template fit'+(item.warning?' · '+item.warning:'');const figure=SpherexReviewPlot.figure(item,String(item.object.moca_specid),el.clientWidth,1,SpherexReviewPlot.lanes.find(v=>v.key===lane)?.color);figure.layout.height=Math.round(Math.min(510,Math.max(290,el.clientWidth))*(el.closest('#flipbook')?0.75:1));el.replaceChildren();Plotly.newPlot(el,figure.traces,figure.layout,plotConfig);}
function comparisonCard(r,plotId,preferredOnly=false){
 const chosen=preferredOnly?r.preferred_spectrum_lane:null;
 const meta=SpherexReviewPlot.lanes.filter(lane=>!preferredOnly||lane.key===chosen).map(lane=>`<span style="color:${lane.color}">${esc(lane.label)}</span>: ${spectrumLabel(r,lane.key)} · ${esc(spt(r[lane.key+'_spt']))} · ${esc(r[lane.key+'_quality']||'unreviewed')}`).join('<br>');
 return `<article class="card spectrum-card ${preferredOnly?'':'comparison-card'}" data-oid="${r.moca_oid}" data-confirmed="${isConfirmed(r)}"><div class="card-head"><div><h3>${esc(r.designation)}</h3><span class="badge">${esc(spt(r.spt))}</span></div><div class="spectrum-card-actions"><button data-inspect="${r.moca_oid}">Inspect ↗</button><button type="button" data-open-mocadb="${r.moca_oid}">Open MOCAdb ↗</button></div></div><div class="spec-meta">OID ${r.moca_oid}<br>${meta}${reviewContext(r)}</div><div id="${plotId}" class="spec-plot"><div class="spec-empty">Loading available spectra & their best templates…</div></div></article>`;
}
function renderComparison(el,r,items,errors){
 const available=Object.fromEntries(SpherexReviewPlot.lanes.filter(lane=>items[lane.key]&&!items[lane.key].error).map(lane=>[lane.key,items[lane.key]]));
 const first=Object.keys(available)[0],comparison={...available};delete comparison[first];
 const missing=Object.fromEntries(SpherexReviewPlot.lanes.filter(lane=>!r[lane.key+'_specid']).map(lane=>[lane.key,`No stored ${lane.label} spectrum`]));
 const figure=SpherexReviewPlot.comparisonFigure({...available[first],lane:first||null,comparison,comparison_errors:{...missing,...errors}},String(r.moca_oid),el.clientWidth,1,false);
 figure.layout.height=720;el.replaceChildren();Plotly.newPlot(el,figure.traces,figure.layout,plotConfig);
}
async function renderFlipbook(){
 const generation=++flipGeneration;flipController?.abort();flipController=new AbortController();
 const signal=flipController.signal,pageSize=Math.min(50,Math.max(1,parseInt($('flip-page-size').value,10)||50));
 const lanes=SpherexReviewPlot.lanes.map(lane=>lane.key),preferredOnly=$('preferred-lane-only').checked;
 const data=rows.filter(r=>(!$('available-only').checked||lanes.some(lane=>r[lane+'_specid']))&&(!$('confirmed-only').checked||isConfirmed(r)));
 const pages=Math.ceil(data.length/pageSize);flipPage=Math.max(0,Math.min(flipPage,Math.max(0,pages-1)));
 const selected=data.slice(flipPage*pageSize,(flipPage+1)*pageSize);$('spectra-count').textContent=num(data.length);
 for(const suffix of ['','-bottom']){
  $('flip-position'+suffix).textContent=data.length?`${flipPage*pageSize+1}–${Math.min(data.length,(flipPage+1)*pageSize)} / ${num(data.length)} · page ${flipPage+1} of ${pages}`:'No spectra under these cuts';
  $('flip-prev'+suffix).textContent=`← Previous ${pageSize}`;$('flip-next'+suffix).textContent=`Next ${pageSize} →`;
  $('flip-prev'+suffix).disabled=flipPage===0;$('flip-next'+suffix).disabled=flipPage>=pages-1;
 }
 purgePlots($('flipbook'));$('flipbook').innerHTML=selected.map((r,i)=>comparisonCard(r,'flip-plot-'+i,preferredOnly)).join('');
 if(!selected.length){$('flipbook').innerHTML='<p class="hint">No objects match the flipbook filters. Adjust the confirmation standard, disable “Confirmed only” or “Available spectra only”, or change the sample cuts.</p>';return;}
 // Three bounded ten-spectrum requests per batch; render progressively.
 for(let offset=0;offset<selected.length;offset+=10){
  const batch=selected.slice(offset,offset+10);
  const results=await Promise.allSettled(lanes.map(async lane=>{
   const selected=preferredOnly?batch.filter(r=>r.preferred_spectrum_lane===lane):batch;
   const fits=await getFits(selected,lane,signal);
   return new Map(selected.map((r,i)=>[r.moca_oid,fits[i]]));
  }));
  if(generation!==flipGeneration)return;
  batch.forEach((r,i)=>{
   const items={},errors={};results.forEach((result,j)=>{
    const lane=lanes[j];
    if(result.status==='fulfilled'){items[lane]=result.value.get(r.moca_oid);if(items[lane]?.error)errors[lane]=items[lane].error;}
    else if(result.reason.name!=='AbortError')errors[lane]=result.reason.message;
   });
   const plot=$('flip-plot-'+(offset+i));
   if(preferredOnly){
    const lane=r.preferred_spectrum_lane;
    renderFit(plot,items[lane]||(errors[lane]?{error:errors[lane]}:null),lane);
   }else renderComparison(plot,r,items,errors);
  });
 }
}
function renderObjects(){const q=$('object-search').value.toLowerCase();const data=rows.filter(r=>(r.designation+' '+r.moca_oid).toLowerCase().includes(q));const pages=Math.ceil(data.length/50);objectPage=Math.max(0,Math.min(objectPage,Math.max(0,pages-1)));$('object-rows').innerHTML=data.slice(objectPage*50,objectPage*50+50).map(r=>`<tr data-inspect="${r.moca_oid}" tabindex="0" role="button" aria-label="Inspect ${esc(r.designation)}"><td>${esc(r.designation)}<small>OID ${r.moca_oid}</small></td><td>${esc(spt(r.spt))}<small>${esc(r.spt_source)}</small></td><td>${esc(spt(r.published_spt))}<small>${esc(r.plot_class_label)}</small></td><td>${r.samples.map(s=>esc(sourceNames[s])).join('<br>')}</td><td>${fmt(r.motion,1)}</td><td>${fmt(r.cnn)}</td><td>${fmt(r.w2)}</td><td>${fmt(r.M_w2)}</td><td>${r.byw?'BYW':'—'}<small>${[r.byw_claim?'BYW claim':'',r.yadu?'Yadu':'',r.azul?'Azul':'',r.smdet?'SMDET':''].filter(Boolean).join(' · ')||'no listed claims'}</small></td></tr>`).join('');$('objects-position').textContent=`${num(data.length)} objects · page ${pages?objectPage+1:0} / ${pages}`;$('objects-prev').disabled=objectPage===0;$('objects-next').disabled=objectPage>=pages-1;}
const DUPLICATE_BATCH_SIZE=1500;
let duplicateRows=null,duplicatePage=0,duplicateScan=null,duplicateCanWrite=false,duplicateSaving=false;

function resetDuplicates(){
 duplicateScan?.abort();duplicateScan=null;duplicateRows=null;duplicatePage=0;
 $('duplicates-count').textContent='';$('duplicate-status').textContent='';
}
function reportLink(object){
 const oid=Number(object.moca_oid);
 if(mock)return esc(object.designation||'OID '+oid);
 return `<a href="https://mocadb.ca/search/results?search-query=oid%28${oid}%29&amp;search-type=star" target="_blank" rel="noreferrer">${esc(object.designation||'OID '+oid)} ↗</a>`;
}
function duplicateMotion(object){
 const component=(value,unc)=>value==null?'—':fmt(value,1)+(unc==null?'':' ± '+fmt(unc,1));
 const source=[object.pm_mission,object.pm_release].filter(Boolean).join(' ');
 return `${component(object.pmra_masyr,object.pmra_masyr_unc)} / ${component(object.pmdec_masyr,object.pmdec_masyr_unc)}<small>${esc([source,object.pm_pid].filter(Boolean).join(' · '))}</small>`;
}
function duplicateReference(known){
 const label=esc(known.reference_name||known.moca_pid||'—');
 const cite=known.bibcode?`<a href="https://ui.adsabs.harvard.edu/abs/${encodeURIComponent(known.bibcode)}/abstract" target="_blank" rel="noreferrer">${label} ↗</a>`:label;
 const provenance=[known.reference_name&&known.moca_pid,known.origin].filter(Boolean).join(' · ');
 return `${cite}<small>${esc(provenance)}</small>`;
}
function duplicateDecision(pair){
 if(pair.decision?.classification==='y')return pair.decision.applied?'Duplicate applied':'Declared duplicate';
 if(pair.decision)return `Existing decision (${pair.decision.classification})`;
 if(pair.target_decision)return `Already declared against OID ${pair.target_decision.moca_oid}`;
 if(pair.known_decision)return `Counterpart is a duplicate of OID ${pair.known_decision.moca_oid}`;
 return '';
}
function renderDuplicates(){
 const matches=duplicateRows||[],pageSize=50;
 const pages=Math.ceil(matches.length/pageSize);
 duplicatePage=Math.max(0,Math.min(duplicatePage,pages-1));
 $('duplicate-rows').innerHTML=matches.slice(duplicatePage*pageSize,(duplicatePage+1)*pageSize).map((pair,i)=>{
  const {target,known,separation_arcsec}=pair,record=byId.get(target.moca_oid);
  const decision=duplicateDecision(pair);
  const epoch=object=>object.measurement_epoch_yr==null?'epoch unavailable':`epoch ${fmt(object.measurement_epoch_yr,2)}`;
  return `<tr><td><button class="text-button" data-inspect="${target.moca_oid}">${esc(target.designation||'OID '+target.moca_oid)}</button><small>OID ${target.moca_oid} · ${esc(record?spt(record.spt):(target.adopted_type||'—'))} · ${epoch(target)}</small></td>
   <td>${reportLink(known)}<small>OID ${known.moca_oid} · ${epoch(known)}${known.in_byw?' · BYW':''}</small></td>
   <td>${fmt(separation_arcsec,1)}″</td><td>${esc(known.spectral_type)}</td><td>${duplicateReference(known)}</td>
   <td>${duplicateMotion(target)}</td><td>${duplicateMotion(known)}</td>
   <td>${decision?`<span class="duplicate-decision">${esc(decision)}</span>`:`<button type="button" data-declare-pair="${duplicatePage*pageSize+i}" ${!duplicateCanWrite||duplicateSaving||duplicateScan?'disabled':''}>Declare potential duplicate</button>`}</td></tr>`;
 }).join('');
 $('duplicate-position').textContent=matches.length?`Page ${duplicatePage+1} of ${pages}`:'';
 $('duplicate-prev').disabled=!duplicatePage;$('duplicate-next').disabled=duplicatePage>=pages-1;
 $('duplicate-rescan').disabled=Boolean(duplicateScan)||duplicateSaving;
}
async function scanDuplicates(){
 if(duplicateScan||duplicateSaving)return;
 if(!rows.length){$('duplicate-status').textContent='Apply filters to select objects to scan.';renderDuplicates();return;}
 const controller=new AbortController();duplicateScan=controller;
 const sample=rows, matches=[];
 let positioned=0;
 $('duplicate-error').hidden=true;renderDuplicates();
 try{
  for(let i=0;i<sample.length;i+=DUPLICATE_BATCH_SIZE){
   $('duplicate-status').textContent=`Checking ${num(sample.length)} selected objects… ${num(i)} checked`;
   const result=await api('duplicate-matches',{oids:sample.slice(i,i+DUPLICATE_BATCH_SIZE).map(r=>r.moca_oid)},controller.signal);
   if(duplicateScan!==controller)return;
   positioned+=result.positioned;duplicateCanWrite=result.can_write;matches.push(...result.matches);
  }
  matches.sort((a,b)=>a.separation_arcsec-b.separation_arcsec||a.target.moca_oid-b.target.moca_oid||a.known.moca_oid-b.known.moca_oid);
  duplicateRows=matches;duplicatePage=0;
  const count=new Set(matches.map(pair=>pair.target.moca_oid)).size;
  $('duplicates-count').textContent=num(count);
  const skipped=sample.length-positioned;
  $('duplicate-status').textContent=`${num(matches.length)} pairs across ${num(count)} selected objects${skipped?` · ${num(skipped)} unavailable or missing a reference position`:''}${duplicateCanWrite?'':' · Management access required to declare a duplicate'}`;
 }catch(e){
  if(e.name!=='AbortError'&&duplicateScan===controller){
   $('duplicate-error').textContent=e.message;$('duplicate-error').hidden=false;
   $('duplicate-status').textContent='Scan failed. Use Rescan to try again.';
  }
 }finally{
  if(duplicateScan===controller){duplicateScan=null;renderDuplicates();}
 }
}
async function declareDuplicate(pair){
 if(!pair||duplicateDecision(pair)||duplicateSaving||!duplicateCanWrite||duplicateScan)return;
 const {target,known}=pair;
 if(!confirm(`Declare ${target.designation||'OID '+target.moca_oid} as a potential duplicate of ${known.designation||'OID '+known.moca_oid}?`))return;
 duplicateSaving=true;$('duplicate-error').hidden=true;renderDuplicates();
 try{
  const {decision}=await api('declare-duplicate',{moca_oid:target.moca_oid,primary_oid:known.moca_oid});
  for(const match of duplicateRows||[]){
   if(match.target.moca_oid===target.moca_oid){
    match.target_decision=decision;
    if(match.known.moca_oid===known.moca_oid)match.decision=decision;
   }
   if(match.known.moca_oid===target.moca_oid)match.known_decision=decision;
  }
  $('duplicate-status').textContent=`${mock?'Demo declaration':'Declared potential duplicate'} · OID ${target.moca_oid} → OID ${known.moca_oid}`;
 }catch(e){$('duplicate-error').textContent=e.message;$('duplicate-error').hidden=false;}
 finally{
  duplicateSaving=false;renderDuplicates();
  if(tab==='duplicates'&&duplicateRows===null)scanDuplicates();
 }
}
$('duplicate-rescan').onclick=scanDuplicates;
$('duplicate-prev').onclick=()=>{duplicatePage--;renderDuplicates();};
$('duplicate-next').onclick=()=>{duplicatePage++;renderDuplicates();};
$('duplicate-rows').onclick=e=>{
 const button=e.target.closest('[data-declare-pair]');
 if(button)declareDuplicate(duplicateRows?.[Number(button.dataset.declarePair)]);
};

function wiseHash(r){return new URLSearchParams({ra:r.ra,dec:r.dec,size:30,band:3,speed:313,minbright:-50,maxbright:500,window:2.64664,diff_window:1,linear:1,color:'',zoom:20,border:0,outer_epochs:1,gaia:1,invert:1,maxdyr:1,scandir:0,neowise:0,diff:0}).toString();}
let inspectorPositions=null, wiseAstrometry=null;

function skyCrosshairs(container, markers) {
 let overlay=container.querySelector(':scope > .spectrum-crosshairs');
 if(!overlay){overlay=document.createElement('div');overlay.className='spectrum-crosshairs';overlay.setAttribute('aria-hidden','true');container.append(overlay);}
 overlay.replaceChildren();
 for(const {lane,x,y} of markers){
  const i=SpherexReviewPlot.lanes.findIndex(entry=>entry.key===lane);
  if(i<0||![x,y].every(v=>finite(v)&&v>=0&&v<=1))continue;
  const crosshair=document.createElement('span');
  crosshair.className='spectrum-crosshair';crosshair.dataset.lane=lane;
  crosshair.style.left=`${100*x}%`;crosshair.style.top=`${100*y}%`;
  crosshair.style.setProperty('--marker-color',SpherexReviewPlot.lanes[i].color);
  crosshair.style.setProperty('--marker-gap',`${2+i*6}px`);
  for(let arm=0;arm<4;arm++)crosshair.append(document.createElement('i'));
  overlay.append(crosshair);
 }
}
function calibratedImage(container, image, alt) {
 const holder=document.createElement('div');holder.className='calibrated-image';
 const img=document.createElement('img');img.alt=alt;img.src=image.data;
 holder.append(img);skyCrosshairs(holder,image.markers);container.replaceChildren(holder);
}
function imageEpochNote(image) {
 if(!Array.isArray(image.markers))return '';
 const label=image.label?.includes('stack coadd')?'stack header epoch':'image epoch';
 const epoch=image.image_epoch==null?`${label} unavailable`:`${label} ${fmt(image.image_epoch,3)}`;
 return ` · ${epoch}${image.markers.length?'':' · no spectrum position inside this field'}`;
}
function renderAstrometryLegend() {
 $('inspect-astrometry').innerHTML=SpherexReviewPlot.lanes.map(lane=>{
  const point=inspectorPositions?.[lane.key];
  const detail=point?`${fmt(point.ra,6)}°, ${fmt(point.dec,6)}° · ${point.epoch==null?'reference epoch unavailable':`epoch ${fmt(point.epoch,3)}`} · ${point.source}`:'reference position unavailable';
  return `<span><b style="color:${lane.color}">${esc(lane.label)}</b> <small>${esc(detail)}</small></span>`;
 }).join('');
}
function atEpoch(point, epoch) {
 const rad=Math.PI/180,ra=point.ra*rad,dec=point.dec*rad;
 if(![epoch,point.epoch,point.pmra,point.pmdec].every(finite))return [ra,dec];
 const bearing=Math.atan2(point.pmra,point.pmdec);
 const distance=Math.hypot(point.pmra,point.pmdec)*(epoch-point.epoch)*rad/3600000;
 const lat=Math.asin(Math.max(-1,Math.min(1,Math.sin(dec)*Math.cos(distance)+Math.cos(dec)*Math.sin(distance)*Math.cos(bearing))));
 const lon=ra+Math.atan2(Math.sin(bearing)*Math.sin(distance)*Math.cos(dec),Math.cos(distance)-Math.sin(dec)*Math.sin(lat));
 return [lon,lat];
}
function renderWiseAstrometry() {
 if(!wiseAstrometry||!inspectorPositions)return;
 const {wcs,bounds,size,epoch}=wiseAstrometry;
 const [ra0,dec0,crpix1,crpix2,naxis2]=wcs;
 const [left,top,width,height]=bounds,[nx,ny]=size;
 const frame=$('wise-frame').getBoundingClientRect();
 const rad=Math.PI/180,lon0=ra0*rad,lat0=dec0*rad,scale=3600/2.75/rad;
 const markers=[];
 for(const [lane,point] of Object.entries(inspectorPositions)){
  const [lon,lat]=atEpoch(point,epoch),delta=lon-lon0;
  const den=Math.sin(lat0)*Math.sin(lat)+Math.cos(lat0)*Math.cos(lat)*Math.cos(delta);
  if(den<=0)continue;
  const px=crpix1-.5-scale*Math.cos(lat)*Math.sin(delta)/den;
  const py=naxis2-crpix2+.5-scale*(Math.cos(lat0)*Math.sin(lat)-Math.sin(lat0)*Math.cos(lat)*Math.cos(delta))/den;
  if(px<0||px>nx||py<0||py>ny)continue;
  markers.push({lane,x:(left+px/nx*width)/frame.width,y:(top+py/ny*height)/frame.height});
 }
 skyCrosshairs($('wise-image-content'),markers);
 $('wise-epoch').textContent=epoch===null?'WISE epoch unavailable':`Median WISE frame epoch ${fmt(epoch,3)}`;
}
window.addEventListener('message',event=>{
 const message=event.data;
 if(event.source!==$('wise-frame').contentWindow||message?.kind!=='sublime-wiseview-wcs'||message.frame!==String(inspectorGeneration)||!$('inspector').open)return;
 const {wcs,bounds,size,epoch}=message;
 if(![[wcs,5],[bounds,4],[size,2]].every(([v,n])=>Array.isArray(v)&&v.length===n&&v.every(finite)))return;
 if(size.some(v=>v<=0)||bounds[2]<=0||bounds[3]<=0||(epoch!==null&&!finite(epoch)))return;
 wiseAstrometry=message;renderWiseAstrometry();
});

function closeInspector(){inspectorGeneration++;inspectController?.abort();if($('inspector').open)$('inspector').close();$('wise-frame').src='about:blank';purgePlots($('inspect-spectra'));}
async function openInspector(r){
 closeInspector();current=r;cutouts=[];cutIndex=0;inspectorPositions=null;wiseAstrometry=null;
 $('inspect-astrometry').textContent='Loading spectrum reference positions…';$('wise-epoch').textContent='';skyCrosshairs($('wise-image-content'),[]);
 const generation=++inspectorGeneration;inspectController=new AbortController();const signal=inspectController.signal;
 $('wise-frame').removeAttribute('srcdoc');
 $('inspect-title').textContent=r.designation+' · '+spt(r.spt);$('inspect-meta').textContent=`OID ${r.moca_oid} · RA ${fmt(r.ra,6)}° · Dec ${fmt(r.dec,6)}° · ${r.plot_class_label} · ${r.samples.map(s=>sourceNames[s]).join(', ')}`;
 $('inspect-report').href='https://mocadb.ca/search/results?search-query=oid%28'+r.moca_oid+'%29&search-type=star';
 $('inspect-wise-link').href='http://byw.tools/wiseview-v2#'+wiseHash(r);
 $('inspect-spectra').innerHTML=['spiffstacker','spiff','sublimeaperture'].map(lane=>spectrumCard(r,lane,'inspect-'+lane,true)).join('');
 $('cutout-content').innerHTML='<div class="spec-empty">Loading locally available SUBLIME cutouts…</div>';$('cut-label').textContent='';$('cut-prev').disabled=true;$('cut-next').disabled=true;
 $('inspector').showModal();$('inspector').scrollTop=0;
 if(!mock&&finite(r.ra)&&finite(r.dec)){$('wise-frame').removeAttribute('srcdoc');$('wise-frame').src='wiseview-frame?frame='+generation+'#'+wiseHash(r);}else $('wise-frame').srcdoc='<p style="font:14px system-ui;padding:20px">WiseView is unavailable in the synthetic demo.</p>';
 for(const lane of ['spiffstacker','spiff','sublimeaperture']){
  if(!r[lane+'_specid'])continue;
  getFits([r],lane,signal).then(items=>{if(generation===inspectorGeneration)renderFit($('inspect-'+lane),items[0],lane);}).catch(e=>{if(e.name!=='AbortError'&&generation===inspectorGeneration)$('inspect-'+lane).innerHTML='<div class="spec-empty">'+esc(e.message)+'</div>';});
 }
 renderFinders(generation,signal);
 const specids=Object.fromEntries(SpherexReviewPlot.lanes.filter(lane=>r[lane.key+'_specid']).map(lane=>[lane.key,r[lane.key+'_specid']]));
 try{
  const result=await api('spectrum-positions',{moca_oid:r.moca_oid,specids},signal);
  if(generation!==inspectorGeneration)return;
  inspectorPositions=result.positions;
 }catch(e){
  if(generation!==inspectorGeneration||e.name==='AbortError')return;
  inspectorPositions={};
 }
 renderAstrometryLegend();renderWiseAstrometry();renderFinders(generation,signal);
 try{
  const result=await api('cutouts',{moca_oid:r.moca_oid,positions:inspectorPositions},signal);
  if(generation!==inspectorGeneration)return;
  cutouts=result.images;showCutout();
  if(!cutouts.length)$('cut-label').textContent=`${result.source_keys||0} catalog source keys · ${result.missing_cutouts||0} unavailable`;
 }catch(e){if(e.name!=='AbortError'&&generation===inspectorGeneration)$('cutout-content').innerHTML='<div class="spec-empty">'+esc(e.message)+'</div>';}

}
function showCutout(){$('cut-prev').disabled=cutouts.length<2;$('cut-next').disabled=cutouts.length<2;if(!cutouts.length){$('cutout-content').innerHTML='<div class="spec-empty">No SUBLIME cutout is available locally.<br>The source may belong only to another catalog, or its cutout disk may be unavailable.</div>';return;}const image=cutouts[cutIndex];$('cut-label').textContent=`${cutIndex+1} / ${cutouts.length} · ${image.source_key} · ${image.epochs.map(e=>e.sample+' '+fmt(e.epoch_yr,2)).join(' / ')}`;if(Array.isArray(image.markers)){
  calibratedImage($('cutout-content'),image,'SUBLIME science cutout');$('cut-label').textContent+=imageEpochNote(image);
 }else{
  $('cutout-content').innerHTML='<img alt="SUBLIME source cutout" src="'+image.data+'">';
  if(Object.keys(inspectorPositions||{}).length)$('cut-label').textContent+=' · FITS WCS unavailable for spectrum overlays';
 }}
let finderGeneration=0;
function renderFinders(generation=inspectorGeneration,signal=inspectController?.signal){
 const fgen=++finderGeneration,r=current;if(!r)return;
 $('finders').innerHTML=['2mass','ps1','nsc'].map(s=>`<article class="card"><div class="card-head"><h3>${{ '2mass':'2MASS',ps1:'PS1',nsc:'NSC DR2'}[s]}</h3></div><div class="image-content" id="finder-${s}"><div class="spec-empty">${mock?'Finder charts are disabled in demo mode.':'Resolving survey coverage…'}</div></div><p class="hint" id="finder-note-${s}"></p></article>`).join('');
 if(mock||inspectorPositions===null)return;
 for(const survey of ['2mass','ps1','nsc'])api('survey',{survey,ra:r.ra,dec:r.dec,fov:Number($('finder-fov').value),positions:inspectorPositions},signal).then(result=>{
  if(generation!==inspectorGeneration||fgen!==finderGeneration)return;
  if(result.data){
   calibratedImage($('finder-'+survey),result,result.label);
   $('finder-note-'+survey).textContent=result.label+' · '+result.orientation+imageEpochNote(result);return;
  }
  if(!result.url){$('finder-'+survey).innerHTML='<div class="spec-empty">'+esc(result.error||'No survey coverage returned.')+'</div>';return;}
  const el=$('finder-'+survey),img=document.createElement('img');img.alt=result.label;img.referrerPolicy='no-referrer';img.src=result.url;if(result.flip_x)img.style.transform='scaleX(-1)';let settled=false;
  const timer=setTimeout(()=>{if(!settled&&el.isConnected){settled=true;el.innerHTML='<div class="spec-empty">Image service did not finish. <a target="_blank" rel="noreferrer" href="'+esc(result.url)+'">Open image ↗</a></div>';}},survey==='2mass'?60000:30000);
  img.onload=()=>{if(generation!==inspectorGeneration||fgen!==finderGeneration||settled)return;settled=true;clearTimeout(timer);el.replaceChildren(img);};
  img.onerror=()=>{if(generation!==inspectorGeneration||fgen!==finderGeneration||settled)return;settled=true;clearTimeout(timer);el.innerHTML='<div class="spec-empty">Image unavailable or no coverage.</div>';};
  $('finder-note-'+survey).textContent=result.label+' · '+result.orientation+(result.note?' · '+result.note:'');
 }).catch(e=>{if(e.name!=='AbortError'&&generation===inspectorGeneration&&fgen===finderGeneration)$('finder-'+survey).innerHTML='<div class="spec-empty">'+esc(e.message)+'</div>';});
}
function csvCell(v){let s=Array.isArray(v)?v.join('; '):v==null?'':String(v);if(typeof v==='string'&&/^[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}
function exportCSV(){const keys=[...new Set(rows.flatMap(Object.keys))];const content='\ufeff'+[keys.map(csvCell).join(','),...rows.map(r=>keys.map(k=>csvCell(r[k])).join(','))].join('\r\n');const blob=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=blob;a.download='sublime-findings-'+new Date().toISOString().slice(0,10)+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(blob),1000);}
$('filters').onsubmit=e=>{e.preventDefault();load();};$('filters').oninput=()=>{$('dirty').textContent='Filters changed — apply to update the sample.';};$('reset').onclick=()=>{setFilters(defaults);load();};
for(const [id,confirmations] of [['preset-sublime2',false],['preset-sublime2-confirmations',true]])$(id).onclick=()=>{
 const cuts={...readFilters(),sources:['sublime2'],known:'no',
  byw:'no',byw_claim:'no',yadu:'no',azul:'no',smdet:'no'};
 if(confirmations){
  cuts.quality_any='one_good';cuts.min_motion=5;
  if(cuts.max_motion!=null&&cuts.max_motion<5)delete cuts.max_motion;
 }
 setFilters(cuts);load();
};
$('refresh').onclick=load;$('download').onclick=exportCSV;
for(const [id,known] of [['preset-new','no'],['preset-known','yes'],['preset-all','either']])$(id).onclick=()=>{const f=readFilters();f.known=known;if(known==='yes'){f.spt_source='published';f.min_spt=10;f.quality_any='any';}else if(f.spt_source==='published')f.spt_source='best';setFilters(f);load();};
$('copy-cuts').onclick=async()=>{try{await navigator.clipboard.writeText(safeLink(readFilters()));$('copy-cuts').textContent='Filter link copied ✓';setTimeout(()=>$('copy-cuts').textContent='Copy filter link',2000);}catch{$('status').textContent='Could not copy automatically. Filter link: '+safeLink(readFilters());}};
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>setTab(b.dataset.tab));
for(const id of ['snr-statistic','snr-band','chi2-lane','cnn-lane'])$(id).onchange=renderDiagnostics;
for(const id of ['hist-bin','hist-ylog','sky-projection','show-synth','show-errors'])$(id).onchange=renderCharts;
$('confirmation-standard').onchange=()=>{renderCharts();flipPage=0;if(tab==='spectra')renderFlipbook();};
for(const id of ['available-only','confirmed-only','preferred-lane-only','flip-page-size'])$(id).onchange=()=>{flipPage=0;renderFlipbook();};
for(const suffix of ['','-bottom']){$('flip-prev'+suffix).onclick=()=>{flipPage--;renderFlipbook();};$('flip-next'+suffix).onclick=()=>{flipPage++;renderFlipbook();};}
$('object-search').oninput=()=>{objectPage=0;renderObjects();};$('objects-prev').onclick=()=>{objectPage--;renderObjects();};$('objects-next').onclick=()=>{objectPage++;renderObjects();};
document.addEventListener('click',e=>{const target=e.target.closest('[data-inspect]');if(target){const r=byId.get(Number(target.dataset.inspect));if(r)openInspector(r);}});
$('flipbook').addEventListener('click',e=>{
 const button=e.target.closest('[data-open-mocadb]');
 if(button)window.open('https://mocadb.ca/search/results?search-query=oid%28'+encodeURIComponent(button.dataset.openMocadb)+'%29&search-type=star','_blank','noopener,noreferrer');
});
$('object-rows').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){const target=e.target.closest('[data-inspect]');if(target){e.preventDefault();target.click();}}});
$('inspect-close').onclick=closeInspector;$('inspector').addEventListener('cancel',e=>{e.preventDefault();closeInspector();});$('finder-fov').onchange=()=>renderFinders();
$('cut-prev').onclick=()=>{if(cutouts.length){cutIndex=(cutIndex+cutouts.length-1)%cutouts.length;showCutout();}};$('cut-next').onclick=()=>{if(cutouts.length){cutIndex=(cutIndex+1)%cutouts.length;showCutout();}};
window.addEventListener('keydown',e=>{if($('inspector').open||/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;if(tab==='spectra'&&(e.key==='ArrowRight'||e.key==='ArrowLeft')){const b=$(e.key==='ArrowRight'?'flip-next':'flip-prev');if(!b.disabled){e.preventDefault();b.click();}}});
window.addEventListener('resize',()=>{document.querySelectorAll('.js-plotly-plot').forEach(el=>{if(el.offsetWidth)Plotly.Plots.resize(el);});});
let initial={...defaults};try{if(params.has('filters'))initial={...defaults,...JSON.parse(params.get('filters'))};}catch{showError('The saved filter link is invalid. Default filters were restored.');}
function fitFilterSidebar(){
 const sidebar=document.querySelector('.sidebar');
 const offset=Math.max(0,sidebar.getBoundingClientRect().top);
 sidebar.style.setProperty('--sidebar-top',offset+'px');
}
window.addEventListener('scroll',fitFilterSidebar,{passive:true});
window.addEventListener('resize',fitFilterSidebar);
setFilters(initial);$('demo-banner').hidden=!mock;fitFilterSidebar();
if(mock||auth['X-MOCA-Password'])load();else{$('status').textContent='Open this dashboard through Web Tools → Start & open to use your private MOCAdb connection.';$('apply').disabled=false;}
// Small, read-only hooks let the maintained browser probe exercise Plotly selection.
window.SublimeFindings={get rows(){return rows;},openObject:id=>{const r=byId.get(Number(id));if(r)openInspector(r);},spt,skyCoordinates:FindingSky.transform,plotClasses:classDefinitions,classify:FindingClasses.classify};
})();
