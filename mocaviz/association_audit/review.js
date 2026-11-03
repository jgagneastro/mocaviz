(() => {
'use strict';
const $=id=>document.getElementById(id), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const params=new URLSearchParams(location.search);
const param=(...names)=>names.map(name=>params.get(name)).find(value=>value!==null)||'';
const auth={'X-MOCA-User':param('user','username'),'X-MOCA-Password':param('pwd','password'),
            'X-MOCA-Database':param('dbase','db','database')};
const scope=auth['X-MOCA-User'];
const KEY='moca-association-review:v2:'+scope, PREF='moca-association-review:prefs:'+scope;
let canWrite=false;
let sampleCatalog={samples:[],warnings:[]},samplesLoaded=false;
const requestedSample=new URLSearchParams(location.search).get('sample');
let token='', catalog=null, relationIndex=new Map(), groups=[], gi=0, audit=null, candidates=[], ci=0, epoch=0, busy=false, closed=false, targetOnTop=false;
let staged={}, history=[], selectedRow=null, pairRevision=null, write=null, trayKeys=[], trayIndex=0;
try { staged=JSON.parse(localStorage.getItem(KEY)||'{}'); } catch { staged={}; }
try { const p=JSON.parse(localStorage.getItem(PREF)||'{}'); $('public').value=p.public??''; $('rls').value=p.rls||''; } catch {}
function status(s){$('status').textContent=s;} function fail(e){$('error').hidden=!e;$('error').textContent=e?.message||e||'';}
async function api(path,body){
  const headers={...auth};
  if(body)Object.assign(headers,{'Content-Type':'application/json','X-Audit-Token':token});
  const response=await fetch(location.pathname.replace(/\/$/,'')+'/api/'+path,{
    method:body?'POST':'GET',headers,body:body?JSON.stringify(body):undefined,
    cache:'no-store',referrerPolicy:'no-referrer'
  });
  const data=await response.json();
  if(!response.ok)throw Error(data.error||'Request failed');
  return data;
}
const nat=(a,b)=>a.localeCompare(b,undefined,{numeric:true,sensitivity:'base'});
const pairKey=(a,b)=>[a,b].sort().join('|');
const current=()=>candidates[ci];
function active(rows){return rows.filter(r=>!r.ignored);}
function relationStats(aid){const rows=relationIndex.get(aid)||[];return {rows,children:active(rows).filter(r=>r.parent_aid===aid).length,parents:active(rows).filter(r=>r.moca_aid===aid).length,publication:rows.map(r=>r.moca_pid||'').sort(nat)[0]||'',linked:active(rows).length,partial:active(rows).filter(r=>r.partial_subgroup_overlap).length,complete:active(rows).filter(r=>r.complete_parent_overlap).length,ignored:rows.filter(r=>r.ignored).length,recent:rows.reduce((m,r)=>r.modified_timestamp>m?r.modified_timestamp:m,'')};}
function save(){localStorage.setItem(KEY,JSON.stringify(staged));$('stage-count').textContent=Object.keys(staged).length;}
function prefs(){localStorage.setItem(PREF,JSON.stringify({public:$('public').value,rls:$('rls').value}));}
function rowText(r){return `${r.moca_aid} → ${r.parent_aid??'(none)'} · partial ${r.partial_subgroup_overlap} · complete ${r.complete_parent_overlap}${r.ignored?' · ignored':''}`;}
function sampleSelection(){return sampleCatalog.samples.find(s=>s.id===$('sample').value);}
function updateSampleNote(){const s=sampleSelection();$('focus').disabled=!!s;if(s){const known=new Set(catalog.groups.map(g=>g.moca_aid)),missing=s.ids.filter(a=>!known.has(a));$('sample-note').textContent=`${s.ids.length-missing.length} of ${s.ids.length} sample groups available. ${s.note}${missing.length?' Missing: '+missing.join(', '):''}`;$('sample-note').title=s.source.path+'\nSHA-256: '+s.source.sha256;}else{$('sample-note').textContent=sampleCatalog.warnings.join(' ')||'Samples restrict the target queue; comparison candidates still span MOCAdb.';$('sample-note').title='';}}
function filteredGroups(){const previous=groups[gi]?.moca_aid;const chosen=sampleSelection(),sampleIds=chosen?new Set(chosen.ids):null;const focus=$('focus').value, search=$('search').value.trim().toLowerCase(),filter=$('group-filter').value,sort=$('group-sort').value;
 groups=catalog.groups.filter(g=>{const prefix=g.moca_aid.match(/^[A-Za-z]+/)?.[0].toUpperCase();return (sampleIds?sampleIds.has(g.moca_aid):(focus==='all'||(focus==='focus'?['THEIA','HURE','CRIUS','RHEA'].includes(prefix):prefix===focus)))&&(!search||(g.moca_aid+' '+g.name+' '+(g.aliases||'')+' '+(relationIndex.get(g.moca_aid)||[]).map(r=>[r.moca_aid,r.parent_aid,r.moca_pid,r.comments].join(' ')).join(' ')).toLowerCase().includes(search));}).map(g=>({...g,stats:relationStats(g.moca_aid)})).filter(g=>filter==='all'||(filter==='unlinked'?!g.stats.linked:!!g.stats[filter]));
 groups.sort((a,b)=>{let n=0;if(sort==='publication')n=nat(a.stats.publication,b.stats.publication);else if(sort==='unlinked')n=a.stats.linked-b.stats.linked;else if(sort==='members')n=b.members-a.members;else if(sort==='recent')n=nat(b.stats.recent,a.stats.recent);else if(sort!=='natural')n=b.stats[sort]-a.stats[sort];return n||nat(a.moca_aid,b.moca_aid);});
 $('groups').replaceChildren(...groups.map(g=>new Option(`${g.moca_aid} · ${g.stats.linked} active / ${g.members} members`,g.moca_aid)));
 $('group-count').textContent=`${groups.length} associations · direct row counts include both directions`;
 gi=Math.max(0,groups.findIndex(g=>g.moca_aid===previous));$('groups').value=groups[gi]?.moca_aid||'';
}
async function loadCatalog(refresh=false){fail('');status('Loading association and relationship inventory…');try{catalog=await api(refresh?'refresh':'catalog',refresh?{}:null);const previousSample=$('sample').value;sampleCatalog=await api('samples');$('sample').replaceChildren(new Option('All database associations','all'),...sampleCatalog.samples.map(s=>new Option(`${s.name} (${s.ids.length})`,s.id)));const wanted=samplesLoaded?previousSample:requestedSample;samplesLoaded=true;if(wanted&&wanted!=='all'){if(!sampleCatalog.samples.some(s=>s.id===wanted))throw Error('Requested sample is unavailable. Check the manuscript files and reload.');$('sample').value=wanted;}updateSampleNote();relationIndex=new Map();for(const r of catalog.relationships){for(const aid of new Set([r.moca_aid,r.parent_aid].filter(Boolean))){if(!relationIndex.has(aid))relationIndex.set(aid,[]);relationIndex.get(aid).push(r);}}$('freshness').textContent='Database list: '+new Date(catalog.fetched_at).toLocaleString();$('all-groups').replaceChildren(...catalog.groups.map(g=>new Option(g.name||g.moca_aid,g.moca_aid)));filteredGroups();await loadGroup(gi);}catch(e){fail(e);status('Unable to load database list.');}}
async function getAudit(aid,extra,requestEpoch){const path='audit?aid='+encodeURIComponent(aid)+(extra?'&extra='+encodeURIComponent(extra):'');for(let n=0;n<300;n++){if(closed)throw Error('Review closed.');if(requestEpoch!==epoch)throw Error('Selection changed.');const r=await api(path);if(r.state==='ready')return r.audit;if(requestEpoch===epoch)status(`${aid} · ${r.phase||'Loading…'} · ${Math.round(r.elapsed_seconds||0)} s`);await new Promise(resolve=>setTimeout(resolve,400));}throw Error('This group is taking longer than expected. Try again; its query may still be running.');}
async function loadGroup(index,extra=null,preferred=null){if(closed)return;const n=++epoch;$('retry-load').hidden=true;gi=Math.max(0,Math.min(groups.length-1,index));const aid=groups[gi]?.moca_aid;audit=null;candidates=[];ci=0;busy=true;controls();$('pairs').replaceChildren();$('metrics').replaceChildren();$('target').textContent=aid||'No matching groups';$('candidate').textContent='—';$('names').textContent='';$('groups').value=aid||'';$('editor').open=false;Plotly.purge('plots');if(!aid){busy=false;status('No associations match these filters.');controls();return;}
 status('Loading '+aid+' · fetching and caching member samples…');fail('');
 try{const data=await getAudit(aid,extra,n);if(n!==epoch)return;audit=data;busy=false;filterPairs(preferred||extra);status(`${aid} ready · ${data.seconds}s initial preparation · samples cached for five minutes`);if(groups[gi+1])api('audit?aid='+encodeURIComponent(groups[gi+1].moca_aid)).catch(()=>{});}catch(e){if(n===epoch){fail(e);busy=false;$('retry-load').hidden=false;status('Group could not be loaded. Retry without reloading the page.');}}finally{if(n===epoch)controls();}}
function filterPairs(preferred=current()?.candidate_aid){if(!audit)return;const filter=$('pair-filter').value,sort=$('pair-sort').value;
 candidates=audit.candidates.filter(c=>{const rows=c.direct_rows,live=active(rows);return filter==='all'||(filter==='unrecorded'?!live.length:filter==='direct'?!!rows.length:filter==='derived'?!live.length&&c.known_relationships.some(r=>r.relationship_source==='derived'):filter==='pending'?!staged[pairKey(audit.target_aid,c.candidate_aid)]:filter==='ignored'?rows.some(r=>r.ignored):live.some(r=>r[filter==='partial'?'partial_subgroup_overlap':'complete_parent_overlap']));});
 const recent=c=>c.direct_rows.reduce((m,r)=>r.modified_timestamp>m?r.modified_timestamp:m,'');
 candidates.sort((a,b)=>{let n=0;const ac=active(a.direct_rows),bc=active(b.direct_rows);if(sort==='direct')n=bc.length-ac.length;if(sort==='unrecorded')n=ac.length-bc.length;if(sort==='shared')n=b.membership_overlap.overlap_n-a.membership_overlap.overlap_n;if(sort==='score')n=(a.phase_space.best_relationship_score??Infinity)-(b.phase_space.best_relationship_score??Infinity);if(sort==='partial'||sort==='complete'){const f=sort==='partial'?'partial_subgroup_overlap':'complete_parent_overlap';n=Number(bc.some(r=>r[f]))-Number(ac.some(r=>r[f]));}if(sort==='recent')n=nat(recent(b),recent(a));if(sort==='publication')n=nat(a.direct_rows.map(r=>r.moca_pid||'').sort(nat)[0]||'',b.direct_rows.map(r=>r.moca_pid||'').sort(nat)[0]||'');if(sort==='ignored')n=b.direct_rows.filter(r=>r.ignored).length-a.direct_rows.filter(r=>r.ignored).length;return n||(a.rank-b.rank)||nat(a.candidate_aid,b.candidate_aid);});
 ci=Math.max(0,candidates.findIndex(c=>c.candidate_aid===preferred));$('pairs').replaceChildren(...candidates.map((c,i)=>new Option(`${c.candidate_aid} · ${c.direct_rows.length?'direct '+c.direct_rows.length:c.priority}${staged[pairKey(audit.target_aid,c.candidate_aid)]?' · staged':''}`,i)));render();}
function controls(){for(const id of ['first','prev','next','last','flip','edit','stage-row'])$(id).disabled=busy||closed||!current();document.querySelectorAll('[data-action]').forEach(b=>b.disabled=busy||closed||!current());$('undo').disabled=!history.length||closed;$('prev-group').disabled=closed||gi<=0;$('next-group').disabled=closed||gi>=groups.length-1;}
const fmt=(v,d=2)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toFixed(d);
function render(){const c=current();controls();if(!c){$('candidate').textContent='No comparisons';$('metrics').replaceChildren();Plotly.purge('plots');return;}
 $('pairs').value=ci;$('target').textContent=audit.target_aid;$('candidate').textContent=c.candidate_aid;$('names').textContent=(audit.target_name||'')+' / '+(c.candidate_name||'');$('position').textContent=`Group ${gi+1}/${groups.length} · comparison ${ci+1}/${candidates.length}`;
 const p=c.phase_space,o=c.membership_overlap;
 const labels={equivalent:'Equivalent [1]',child:audit.target_aid+' subgroup of '+c.candidate_aid+' [2]',parent:c.candidate_aid+' subgroup of '+audit.target_aid+' [3]','partial-child':audit.target_aid+' partly in '+c.candidate_aid+' [4]','partial-parent':c.candidate_aid+' partly in '+audit.target_aid+' [5]',none:'No relationship [0]'};
 document.querySelectorAll('[data-action]').forEach(b=>{b.textContent=labels[b.dataset.action];});

 $('metrics').innerHTML=[['Best geometry hypothesis',(p.best_hypothesis||'Insufficient coordinates').replace('target-as-subgroup',audit.target_aid+' as subgroup').replace('candidate-as-subgroup',c.candidate_aid+' as subgroup'),fmt(p.best_relationship_score)],['XYZ / UVW separation',fmt(p.position_separation_pc,1)+' pc / '+fmt(p.velocity_separation_kms,1)+' km/s','Robust member medians'],['Shared direct members',o.overlap_n,fmt(100*o.target_containment,1)+'% of '+audit.target_aid+' · '+fmt(100*o.candidate_containment,1)+'% of '+c.candidate_aid],['Existing relationships',active(c.direct_rows).length+' active · '+c.direct_rows.filter(r=>r.ignored).length+' ignored',c.known_relationships.some(r=>r.relationship_source==='derived')?'Includes derived hierarchy':'Direct database rows']].map(([l,v,s])=>`<div class="metric"><small>${esc(l)}</small><strong>${esc(v)}</strong><small>${esc(s)}</small></div>`).join('');
 for(const b of document.querySelectorAll('[data-action]')){b.classList.toggle('recommended',({equivalent:'duplicate/equivalent',child:'target-as-subgroup',parent:'candidate-as-subgroup'})[b.dataset.action]===p.best_hypothesis);}
 const saved=staged[pairKey(audit.target_aid,c.candidate_aid)];$('decision-status').textContent=saved?(saved.applied?'Applied to MOCAdb':saved.action==='none'?'Reviewed: no relationship':'Staged locally'):'';
 $('record').replaceChildren(new Option('New directed row',''),...c.direct_rows.map(r=>new Option('#'+r.id+' · '+rowText(r),r.id)));
 selectedRow=null;pairRevision=c.row_revision;
 const only=c.direct_rows.filter(r=>r.moca_aid===audit.target_aid);
 if(only.length===1){$('record').value=only[0].id;fillRow(only[0]);}else fillRow(null);
 drawPlots(c);
}
function fillRow(row){const c=current();if(!c)return;selectedRow=row;
 $('child').value=row?.moca_aid||audit.target_aid;$('parent').value=row?row.parent_aid||'':c.candidate_aid;$('pid').value=row?.moca_pid||'';$('comments').value=row?.comments||'';for(const [id,k] of [['partial','partial_subgroup_overlap'],['complete','complete_parent_overlap'],['ignored','ignored']])$(id).checked=!!row?.[k];
 if(row){$('public').value=row.is_public;$('rls').value=row.rls;}$('existing-details').textContent=row?JSON.stringify(row,null,2):c.direct_rows.length?c.direct_rows.map(rowText).join('\n'):'No direct database rows for this pair.';$('editor-state').textContent='';}
function editRow(){const c=current();if(!c)throw Error('Choose a comparison first.');const vis=$('public').value;if(vis==='')throw Error('Choose public or private visibility in the row editor before staging.');return {moca_aid:$('child').value.trim(),parent_aid:$('parent').value.trim()||null,moca_pid:$('pid').value.trim()||null,partial_subgroup_overlap:Number($('partial').checked),complete_parent_overlap:Number($('complete').checked),ignored:Number($('ignored').checked),comments:$('comments').value||null,is_public:Number(vis),rls:vis==='1'?'public':$('rls').value.trim()};}
function remember(entry){const k=pairKey(entry.target,entry.candidate),old=staged[k];staged[k]=entry;try{save();}catch(e){if(old)staged[k]=old;else delete staged[k];throw Error('Browser storage is full. Export a backup before continuing.');}history.push({key:k,previous:old,target:entry.target,candidate:entry.candidate});controls();}
async function classify(action){if(busy||!current()||closed)return;fail('');try{const c=current();let entry={target:audit.target_aid,candidate:c.candidate_aid,action,at:new Date().toISOString(),revision:pairRevision,id:selectedRow?.id||null};if(action!=='none'){
 const child=['parent','partial-parent'].includes(action)?c.candidate_aid:audit.target_aid,parent=child===audit.target_aid?c.candidate_aid:audit.target_aid;
 const matches=c.direct_rows.filter(r=>r.moca_aid===child&&r.parent_aid===parent);if(matches.length>1&&(!selectedRow||!matches.some(r=>r.id===selectedRow.id)))throw Error('Several rows exist for that direction. Select the intended row in the editor.');
 const row=selectedRow&&matches.some(r=>r.id===selectedRow.id)?selectedRow:matches[0];if(row){$('record').value=row.id;fillRow(row);}else {fillRow(null);$('child').value=child;$('parent').value=parent;}
 $('partial').checked=action.startsWith('partial');$('complete').checked=action==='equivalent';$('ignored').checked=false;
 entry.row=editRow();entry.id=selectedRow?.id||null;entry.revision=c.row_revision;
 }remember(entry);prefs();await advance();}catch(e){$('editor').open=true;fail(e);}}
async function stageEditor(){try{const row=editRow();if(!pairRevision)throw Error('Inspect this directed pair before staging.');if(!row.is_public&&!row.rls)throw Error('Choose a private RLS.');remember({target:row.moca_aid,candidate:row.parent_aid||'(no parent)',action:'custom',row,id:selectedRow?.id||null,revision:pairRevision,at:new Date().toISOString()});prefs();status('Edited relationship staged locally.');render();}catch(e){fail(e);}}
async function advance(){if(!$('advance').checked){render();return;}if(ci<candidates.length-1){ci++;render();}else if(gi<groups.length-1)await loadGroup(gi+1);else{render();status('End of the selected queue. Your decisions are staged locally.');}}
async function undo(){const h=history.pop();if(!h)return;if(h.previous)staged[h.key]=h.previous;else delete staged[h.key];save();const i=groups.findIndex(g=>g.moca_aid===h.target);if(i>=0){if(audit?.target_aid===h.target){filterPairs(h.candidate);}else await loadGroup(i,null,h.candidate);}status('Last local classification undone. Applied database rows are not changed by local undo.');}
function navigate(n){if(!current()||busy)return;ci=Math.max(0,Math.min(candidates.length-1,n));render();}
function highlightTray(){const rows=$('staged-list').querySelectorAll('.staged-row');rows.forEach((r,i)=>r.classList.toggle('selected',i===trayIndex));rows[trayIndex]?.scrollIntoView({block:'nearest'});}
function tray(){write=null;$('write-preview').hidden=true;const entries=Object.entries(staged);trayKeys=entries.map(([k])=>k).reverse();trayIndex=Math.max(0,Math.min(trayIndex,trayKeys.length-1));$('staged-list').replaceChildren();for(const [key,e] of entries.reverse()){
 const el=document.createElement('div');el.className='staged-row';const text=document.createElement('span');text.textContent=e.target+' / '+e.candidate;const sub=document.createElement('small');sub.textContent=e.action==='none'?'No relationship · local only':rowText(e.row)+(e.applied?' · applied #'+e.applied:'');text.append(sub);el.append(text);
 if(e.row&&!e.applied){const b=document.createElement('button');b.textContent='Preview [P]';b.onclick=()=>{trayIndex=trayKeys.indexOf(key);highlightTray();preview(key);};b.onfocus=()=>{trayIndex=trayKeys.indexOf(key);highlightTray();};el.append(b);}const remove=document.createElement('button');remove.textContent='Unstage [Delete]';remove.onclick=()=>{delete staged[key];save();tray();};remove.onfocus=()=>{trayIndex=trayKeys.indexOf(key);highlightTray();};el.append(remove);$('staged-list').append(el);
 }if(!entries.length)$('staged-list').textContent='No staged decisions yet.';if(!$('tray').open)$('tray').showModal();highlightTray();}
async function preview(key){$('write-preview').hidden=false;$('confirm').checked=false;$('apply').disabled=true;$('write-status').textContent='Checking current database state…';try{const e=staged[key];const d=await api('preview',{row:e.row,id:e.id,revision:e.revision});write={key,...d};$('preview-data').textContent=JSON.stringify({operation:d.plan.operation,id:d.plan.id,before:d.plan.before,after:d.plan.row,row_counts:d.row_counts},null,2);$('write-status').textContent='Preview only. This will change one relationship row and add one changelog entry.';$('apply').disabled=false;}catch(e){write=null;$('write-status').textContent=e.message;}}
async function apply(){if(!canWrite){$('write-status').textContent='Management access is required to apply a relationship.';return;}if(!write||!$('confirm').checked){$('write-status').textContent='Review the preview and check the confirmation box first.';return;}$('apply').disabled=true;const pending=write;try{const d=await api('apply',{token:pending.token,confirm:true});staged[pending.key].applied=d.id;save();write=null;$('write-status').textContent='Saved to MOCAdb as row #'+d.id+'. Refresh the database list before editing this pair again.';$('confirm').checked=false;}catch(e){write=null;$('write-status').textContent=e.message+' Create a fresh preview before retrying.';}}
function exportJSON(){const blob=new Blob([JSON.stringify({version:2,exported_at:new Date().toISOString(),decisions:staged},null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='association-audit-decisions.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}

  const colors={target:"#2563eb",candidate:"#c34432"};
  const uvwFields = ["avg_u_kms", "avg_v_kms", "avg_w_kms"];
  const uvwSphereRadius = 3;
  const uvwSphereOffsets = [[0, 0, -uvwSphereRadius], [0, 0, uvwSphereRadius]];
  for (let ring = 1; ring < 12; ring++) {
    const polar = Math.PI * ring / 12;
    const radial = uvwSphereRadius * Math.sin(polar);
    const z = uvwSphereRadius * Math.cos(polar);
    for (let step = 0; step < 24; step++) {
      const azimuth = Math.PI * step / 12;
      uvwSphereOffsets.push([radial * Math.cos(azimuth), radial * Math.sin(azimuth), z]);
    }
  }
  function plotPointRows(aid) {
    return audit.points[aid] || [];
  }

  function validRows(rows, indices) {
    return rows.filter((row) => indices.every((index) => row[index] !== null && Number.isFinite(Number(row[index]))));
  }

  function addThreeDimensionalTrace(traces, aid, rows, indices, scene, role, showLegend) {
    const valid = validRows(rows, indices);
    traces.push({
      type: "scatter3d",
      mode: "markers",
      scene,
      name: `<span style="color:${colors[role]};font-weight:700">${esc(aid)}</span>`,
      legendgroup: role,
      showlegend: showLegend,
      x: valid.map((row) => row[indices[0]]),
      y: valid.map((row) => row[indices[1]]),
      z: valid.map((row) => row[indices[2]]),
      hoverinfo: "skip",
      marker: {
        color: colors[role],
        size: role === "target" ? 3.0 : 2.1,
        opacity: 0.72,
        symbol: role === "target" ? "circle" : "diamond",
      },
    });
  }

  function centerCoordinates(summary, fields) {
    const values = fields.map((field) => summary[field]);
    if (values.some((value) => value == null || !Number.isFinite(Number(value)))) return null;
    return values.map(Number);
  }

  function addCenterTrace(traces, values, scene, role) {
    if (!values) return;
    traces.push({
      type: "scatter3d",
      mode: "markers",
      scene,
      showlegend: false,
      x: [values[0]], y: [values[1]], z: [values[2]],
      hoverinfo: "skip",
      marker: { color: colors[role], size: 8, symbol: "cross", line: { color: "#ffffff", width: 1 } },
    });
  }

  function addUvwSphere(traces, [u, v, w], role) {
    traces.push({
      type: "mesh3d",
      scene: "scene2",
      x: uvwSphereOffsets.map(([du]) => u + du),
      y: uvwSphereOffsets.map(([, dv]) => v + dv),
      z: uvwSphereOffsets.map(([, , dw]) => w + dw),
      alphahull: 0,
      color: colors[role],
      opacity: 0.17,
      lighting: { ambient: 0.9, diffuse: 0.45, specular: 0.08 },
      hoverinfo: "skip",
      showlegend: false,
    });
  }

  function addTwoDimensionalTrace(traces, aid, rows, indices, axes, role) {
    const valid = validRows(rows, indices);
    traces.push({
      type: "scattergl",
      mode: "markers",
      xaxis: axes[0],
      yaxis: axes[1],
      showlegend: false,
      x: valid.map((row) => row[indices[0]]),
      y: valid.map((row) => row[indices[1]]),
      hoverinfo: "skip",
      marker: {
        color: colors[role],
        size: role === "target" ? 4 : 4.5,
        opacity: 0.58,
        symbol: role === "target" ? "circle" : "diamond",
      },
    });
  }

  function addTwoDimensionalCenter(traces, summary, fields, axes, role) {
    const values = fields.map((field) => summary[field]);
    if (!values.every((value) => value !== null && value !== undefined && Number.isFinite(Number(value)))) return;
    traces.push({
      type: "scattergl",
      mode: "markers",
      xaxis: axes[0], yaxis: axes[1], showlegend: false,
      x: [values[0]], y: [values[1]],
      hoverinfo: "skip",
      marker: { color: colors[role], size: 12, symbol: "cross", line: { color: "#ffffff", width: 1 } },
    });
  }

  function quantile(sortedValues, fraction) {
    if (!sortedValues.length) return null;
    const position = (sortedValues.length - 1) * fraction;
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    if (lower === upper) return sortedValues[lower];
    const weight = position - lower;
    return sortedValues[lower] * (1 - weight) + sortedValues[upper] * weight;
  }

  function centralRange(groups, index) {
    const values = groups
      .flatMap((group) => group.rows.filter(row => row[index] !== null && row[index] !== undefined).map((row) => Number(row[index])))
      .filter((value) => Number.isFinite(value))
      .sort((left, right) => left - right);
    if (!values.length) return undefined;
    const lower = quantile(values, 0.025);
    const upper = quantile(values, 0.975);
    const span = Math.max(upper - lower, Math.abs(lower) * 0.02, 0.5);
    const padding = 0.08 * span;
    return [lower - padding, upper + padding];
  }

  function sceneAspectRatio(...axisRanges) {
    if (axisRanges.some((range) => !range)) return undefined;
    const [x, y, z] = axisRanges.map(([lower, upper]) => upper - lower);
    // Normalize the box diagonal so elongated groups fit at the same camera distance.
    const scale = Math.sqrt(3) / Math.hypot(x, y, z);
    return { x: x * scale, y: y * scale, z: z * scale };
  }

  const plot = $("plots");
  const sceneNames = ["scene", "scene2"];
  const sceneSelector = "#scene, #scene2";
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const orbitPeriod = 60_000;
  const orbitInterval = 50;
  const activePointers = new Set();
  let orbitResumeAt = 0;
  let lastOrbitTick = performance.now();
  let plotUpdate = null;
  let plotWidth = 0;

  function trackPlotUpdate(update) {
    plotUpdate = update;
    const finish = () => {
      if (plotUpdate === update) plotUpdate = null;
    };
    update.then(finish, finish);
  }

  function delayOrbit() {
    orbitResumeAt = performance.now() + 1500;
  }

  function delayOrbitInScene(event) {
    if (event.target.closest(sceneSelector)) delayOrbit();
  }

  plot.addEventListener("pointermove", delayOrbitInScene, { passive: true });
  plot.addEventListener("wheel", delayOrbitInScene, { capture: true, passive: true });
  plot.addEventListener("pointerdown", (event) => {
    if (event.target.closest(sceneSelector)) activePointers.add(event.pointerId);
  }, true);
  for (const event of ["pointerup", "pointercancel"]) {
    window.addEventListener(event, (release) => {
      if (activePointers.delete(release.pointerId)) delayOrbit();
    }, true);
  }
  window.addEventListener("blur", () => {
    activePointers.clear();
    delayOrbit();
  });

  setInterval(() => {
    const now = performance.now();
    const elapsed = Math.min(now - lastOrbitTick, 2 * orbitInterval);
    lastOrbitTick = now;
    if (closed || !current() || plotUpdate || document.hidden || reducedMotion.matches ||
        activePointers.size || now < orbitResumeAt) return;
    const visibleScene = [...plot.querySelectorAll("#scene canvas, #scene2 canvas")].some((canvas) => {
      const { top, bottom } = canvas.getBoundingClientRect();
      return bottom > 0 && top < window.innerHeight;
    });
    if (!visibleScene) return;

    // Orbit around each scene's vertical axis at the current tilt and zoom.
    const angle = 2 * Math.PI * elapsed / orbitPeriod;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const updates = {};
    for (const scene of sceneNames) {
      const camera = plot.layout[scene].camera;
      const { eye, center } = camera;
      const { x: centerX = 0, y: centerY = 0 } = center ?? {};
      const x = eye.x - centerX;
      const y = eye.y - centerY;
      updates[`${scene}.camera.eye`] = {
        x: centerX + x * cos - y * sin,
        y: centerY + x * sin + y * cos,
        z: eye.z,
      };
    }
    trackPlotUpdate(Plotly.relayout(plot, updates));
  }, orbitInterval);

  new ResizeObserver(() => {
    const candidate = current();
    if (candidate && plot.clientWidth !== plotWidth) drawPlots(candidate);
  }).observe(plot);

  function drawPlots(candidate) {
    plotWidth = plot.clientWidth;
    const targetAid = audit.target_aid;
    const candidateAid = candidate.candidate_aid;
    const targetRows = plotPointRows(targetAid);
    const candidateRows = plotPointRows(candidateAid);
    const baseGroups = [
      { aid: targetAid, rows: targetRows, summary: audit.target_robust_summary || audit.target_summary, role: "target" },
      { aid: candidateAid, rows: candidateRows, summary: candidate.robust_summary || candidate.summary, role: "candidate" },
    ];
    const groups = targetOnTop ? [baseGroups[1], baseGroups[0]] : baseGroups;
    const ranges = Object.fromEntries(
      [2, 3, 4, 5, 6, 7].map((index) => [index, centralRange(baseGroups, index)])
    );
    const uvwRanges = [ranges[5], ranges[6], ranges[7]];
    const sphereExtent = uvwSphereRadius * 1.08;
    const traces = [];
    const panels = [
      { indices: [2, 3], fields: ["avg_x_pc", "avg_y_pc"], axes: ["x", "y"] },
      { indices: [2, 4], fields: ["avg_x_pc", "avg_z_pc"], axes: ["x2", "y2"] },
      { indices: [3, 4], fields: ["avg_y_pc", "avg_z_pc"], axes: ["x3", "y3"] },
      { indices: [5, 6], fields: ["avg_u_kms", "avg_v_kms"], axes: ["x4", "y4"] },
      { indices: [5, 7], fields: ["avg_u_kms", "avg_w_kms"], axes: ["x5", "y5"] },
      { indices: [6, 7], fields: ["avg_v_kms", "avg_w_kms"], axes: ["x6", "y6"] },
    ];

    groups.forEach((group) => {
      const uvwCenter = centerCoordinates(group.summary, uvwFields);
      if (uvwCenter) {
        addUvwSphere(traces, uvwCenter, group.role);
        // Fit the whole sphere in 3D while keeping the 2D velocity ranges.
        uvwCenter.forEach((value, axis) => {
          const [lower, upper] = uvwRanges[axis] ?? [Infinity, -Infinity];
          uvwRanges[axis] = [Math.min(lower, value - sphereExtent), Math.max(upper, value + sphereExtent)];
        });
      }
      addThreeDimensionalTrace(traces, group.aid, group.rows, [2, 3, 4], "scene", group.role, true);
      addThreeDimensionalTrace(traces, group.aid, group.rows, [5, 6, 7], "scene2", group.role, false);
      addCenterTrace(traces, centerCoordinates(group.summary, ["avg_x_pc", "avg_y_pc", "avg_z_pc"]), "scene", group.role);
      addCenterTrace(traces, uvwCenter, "scene2", group.role);
      panels.forEach((panel) => {
        addTwoDimensionalTrace(traces, group.aid, group.rows, panel.indices, panel.axes, group.role);
        addTwoDimensionalCenter(traces, group.summary, panel.fields, panel.axes, group.role);
      });
    });

    const axisStyle = { gridcolor: "#cbd5e155", zerolinecolor: "#94a3b877", showbackground: true, backgroundcolor: "#fbfdff" };
    const axis2dStyle = { gridcolor: "#cbd5e177", zerolinecolor: "#94a3b899" };
    const margin = { l: 10, r: 10, t: 46, b: 54 };
    const innerWidth = Math.max(1, plotWidth - margin.l - margin.r);
    const stackScenes = innerWidth < 620;
    const sceneWidth = stackScenes ? innerWidth : innerWidth * 0.49;
    const sceneHeight = Math.round(sceneWidth * (sceneWidth < 420 ? 0.72 : 0.92));
    const sceneGap = 16;
    const projectionHeight = 180;
    const projectionGap = 70;
    const projectionRows = 2 * (projectionHeight + projectionGap);
    const uvwBottom = projectionRows;
    const xyzBottom = stackScenes ? uvwBottom + sceneHeight + sceneGap : uvwBottom;
    const innerHeight = xyzBottom + sceneHeight;
    const domainY = (bottom, height) => [bottom / innerHeight, (bottom + height) / innerHeight];
    // Only the projections need an outer gutter for their 2D axis labels.
    const projectionLeft = 48;
    const projectionWidth = innerWidth - projectionLeft - 20;
    const projectionX = (left, right) => [left, right].map((x) => (projectionLeft + x * projectionWidth) / innerWidth);
    const xyzProjectionY = domainY(projectionHeight + projectionGap, projectionHeight);
    const uvwProjectionY = domainY(0, projectionHeight);
    const defaultCamera = { eye: { x: 1.43, y: 1.43, z: 1.14 } };
    const revision = `${targetAid}:${candidateAid}`;
    const previousLayout = plot.layout?.uirevision === revision ? plot.layout : null;
    const layout = {
      width: plotWidth,
      height: innerHeight + margin.t + margin.b,
      margin,
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#fbfdff",
      font: { color: getComputedStyle(document.documentElement).getPropertyValue("--text").trim() },
      hovermode: false,
      legend: { orientation: "h", x: 0.5, xanchor: "center", y: 1, yanchor: "bottom" },
      uirevision: revision,
      scene: {
        domain: { x: [0, stackScenes ? 1 : 0.49], y: domainY(xyzBottom, sceneHeight) },
        xaxis: { title: "X [pc]", range: ranges[2], ...axisStyle }, yaxis: { title: "Y [pc]", range: ranges[3], ...axisStyle }, zaxis: { title: "Z [pc]", range: ranges[4], ...axisStyle },
        aspectratio: sceneAspectRatio(ranges[2], ranges[3], ranges[4]),
        camera: previousLayout?.scene.camera ?? defaultCamera,
      },
      scene2: {
        domain: { x: [stackScenes ? 0 : 0.51, 1], y: domainY(uvwBottom, sceneHeight) },
        xaxis: { title: "U [km/s]", range: uvwRanges[0], ...axisStyle }, yaxis: { title: "V [km/s]", range: uvwRanges[1], ...axisStyle }, zaxis: { title: "W [km/s]", range: uvwRanges[2], ...axisStyle },
        aspectratio: sceneAspectRatio(...uvwRanges),
        camera: previousLayout?.scene2.camera ?? defaultCamera,
      },
      xaxis: { domain: projectionX(0, 0.31), anchor: "y", title: "X [pc]", range: ranges[2], ...axis2dStyle }, yaxis: { domain: xyzProjectionY, anchor: "x", title: "Y [pc]", range: ranges[3], ...axis2dStyle },
      xaxis2: { domain: projectionX(0.345, 0.655), anchor: "y2", title: "X [pc]", range: ranges[2], ...axis2dStyle }, yaxis2: { domain: xyzProjectionY, anchor: "x2", title: "Z [pc]", range: ranges[4], ...axis2dStyle },
      xaxis3: { domain: projectionX(0.69, 1), anchor: "y3", title: "Y [pc]", range: ranges[3], ...axis2dStyle }, yaxis3: { domain: xyzProjectionY, anchor: "x3", title: "Z [pc]", range: ranges[4], ...axis2dStyle },
      xaxis4: { domain: projectionX(0, 0.31), anchor: "y4", title: "U [km/s]", range: ranges[5], ...axis2dStyle }, yaxis4: { domain: uvwProjectionY, anchor: "x4", title: "V [km/s]", range: ranges[6], ...axis2dStyle },
      xaxis5: { domain: projectionX(0.345, 0.655), anchor: "y5", title: "U [km/s]", range: ranges[5], ...axis2dStyle }, yaxis5: { domain: uvwProjectionY, anchor: "x5", title: "W [km/s]", range: ranges[7], ...axis2dStyle },
      xaxis6: { domain: projectionX(0.69, 1), anchor: "y6", title: "V [km/s]", range: ranges[6], ...axis2dStyle }, yaxis6: { domain: uvwProjectionY, anchor: "x6", title: "W [km/s]", range: ranges[7], ...axis2dStyle },
    };
    trackPlotUpdate(Plotly.react(plot, traces, layout, { displayModeBar: false, scrollZoom: true }));
  }

$('sample').onchange=()=>{updateSampleNote();const url=new URL(location.href);if($('sample').value==='all')url.searchParams.delete('sample');else url.searchParams.set('sample',$('sample').value);window.history.replaceState(null,'',url);filteredGroups();loadGroup(gi);};
$('retry-load').onclick=()=>loadGroup(gi);
$('groups').onchange=()=>loadGroup(groups.findIndex(g=>g.moca_aid===$('groups').value));
for(const id of ['focus','group-filter','group-sort'])$(id).onchange=()=>{filteredGroups();loadGroup(gi);};
let searchTimer;$('search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{filteredGroups();loadGroup(gi);},300);};
for(const id of ['pair-filter','pair-sort'])$(id).onchange=()=>filterPairs();
$('pairs').onchange=()=>{ci=Number($('pairs').value);render();};
$('prev-group').onclick=()=>loadGroup(gi-1);$('next-group').onclick=()=>loadGroup(gi+1);
$('refresh').onclick=()=>loadCatalog(true);$('compare').onclick=()=>{const other=$('manual').value.trim();if(!catalog.groups.some(g=>g.moca_aid===other)){fail('Choose an exact association identifier.');return;}loadGroup(gi,other,other);};
$('first').onclick=()=>navigate(0);$('last').onclick=()=>navigate(candidates.length-1);$('prev').onclick=()=>navigate(ci-1);$('next').onclick=()=>navigate(ci+1);$('undo').onclick=undo;
$('flip').onclick=()=>{targetOnTop=!targetOnTop;if(current())drawPlots(current());};$('edit').onclick=()=>{$('editor').open=!$('editor').open;if($('editor').open)$('record').focus();};
$('record').onchange=()=>{const row=current().direct_rows.find(r=>r.id===Number($('record').value));pairRevision=current().row_revision;fillRow(row||null);};
for(const id of ['child','parent'])$(id).oninput=()=>{selectedRow=null;pairRevision=null;$('editor-state').textContent='Pair changed. Inspect before staging.';};
$('inspect').onclick=async()=>{try{const child=$('child').value.trim(),parent=$('parent').value.trim();const d=await api('pair?child='+encodeURIComponent(child)+(parent?'&parent='+encodeURIComponent(parent):''));pairRevision=d.revision;const matching=d.rows.filter(r=>r.moca_aid===child&&r.parent_aid===(parent||null));if(matching.length===1){fillRow(matching[0]);}else if(matching.length>1){throw Error('Multiple directed rows found. Use the matching comparison and select a row from its existing-row list.');}else selectedRow=null;$('existing-details').textContent=JSON.stringify(d.rows,null,2);$('editor-state').textContent='Directed pair inspected.';}catch(e){fail(e);}};
$('stage-row').onclick=stageEditor;document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>classify(b.dataset.action));
$('tray-button').onclick=tray;$('close-tray').onclick=()=>$('tray').close();$('export').onclick=exportJSON;$('apply').onclick=apply;
$('import').onchange=async()=>{try{const file=$('import').files[0];if(!file||file.size>5000000)throw Error('Choose a JSON backup smaller than 5 MB.');const d=JSON.parse(await file.text());if(d.version!==2||!d.decisions||typeof d.decisions!=='object'||Array.isArray(d.decisions))throw Error('Not a version 2 review backup.');for(const e of Object.values(d.decisions))if(!e||typeof e.target!=='string'||typeof e.candidate!=='string'||!['none','equivalent','child','parent','partial-child','partial-parent','custom'].includes(e.action))throw Error('Invalid review decision.');staged={...staged,...d.decisions};save();tray();}catch(e){$('write-preview').hidden=false;$('write-status').textContent=e.message;}};
function quit(){closed=true;epoch++;busy=false;save();status('Review closed. Decisions are saved locally; reload to resume.');controls();}
$('quit').onclick=quit;
document.addEventListener('keydown',ev=>{const k=ev.key.toLowerCase(),typing=ev.target.matches('input,textarea,select,[contenteditable]');
 if($('tray').open){if(!typing&&!ev.altKey){if(['arrowup','arrowdown','home','end'].includes(k)){ev.preventDefault();trayIndex=k==='home'?0:k==='end'?trayKeys.length-1:Math.max(0,Math.min(trayKeys.length-1,trayIndex+(k==='arrowup'?-1:1)));highlightTray();}if(k==='p'&&staged[trayKeys[trayIndex]]?.row&&!staged[trayKeys[trayIndex]].applied){ev.preventDefault();preview(trayKeys[trayIndex]);}if(k==='delete'&&trayKeys[trayIndex]){ev.preventDefault();delete staged[trayKeys[trayIndex]];save();tray();}}if(ev.altKey&&k==='e'){ev.preventDefault();exportJSON();}if(ev.altKey&&ev.key==='Enter'){ev.preventDefault();apply();}return;}
 if(ev.altKey){const map={r:'refresh',c:'compare',i:'inspect',s:'stage-row',l:'retry-load'};if(map[k]){ev.preventDefault();$(map[k]).click();}return;}
 if(typing)return;if((ev.ctrlKey||ev.metaKey)&&k==='z'){ev.preventDefault();undo();return;}if(ev.ctrlKey||ev.metaKey)return;
 const digit=ev.code.match(/^Numpad([0-5])$/)?.[1]??k;
 const actions={'0':'none','1':'equivalent','2':'child','3':'parent','4':'partial-child','5':'partial-parent'};
 if(actions[digit]){ev.preventDefault();classify(actions[digit]);return;}
 const keys={'arrowleft':'prev','arrowup':'prev','arrowright':'next','arrowdown':'next',home:'first',end:'last',u:'undo',backspace:'undo',f:'flip',e:'edit',d:'tray-button',q:'quit','[':'prev-group',']':'next-group'};
 if(keys[k]){ev.preventDefault();$(keys[k]).click();}if(k==='/'){ev.preventDefault();$('search').focus();}
});
(async()=>{try{const session=await api('session');token=session.token;canWrite=session.can_write;
if(!canWrite)$('apply').hidden=true;
save();await loadCatalog();}catch(e){fail(e);}})();
})();
