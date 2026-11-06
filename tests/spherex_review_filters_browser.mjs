// Filter transport and controls: all API reads use synthetic data; writes fail.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.argv[2] || 'http://127.0.0.1:8079';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:900}});
const requests=[],errors=[];
let contextVersion=10,queueVersion=10,contextGate=null;
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/spherex-review/*',async route=>{
  const op=new URL(route.request().url()).pathname.split('/').at(-1);
  const body=route.request().postDataJSON();requests.push({op,body});
  assert(['context','queue','queue-count','analyze'].includes(op),'Unexpected write request');
  if(op==='context'&&contextGate)await contextGate;
  const response=await route.fetch({postData:JSON.stringify({...body,mock:true})});
  const payload=await response.json();
  if(op==='context')payload.queue_filter_version=contextVersion;
  if(op==='queue'){
    payload.queue_filter_version=queueVersion;
    if(!body.moca_specid){
      payload.items=payload.items.slice(body.after ? 3 : 0,body.after ? 6 : 3);
      payload.has_more=!body.after;
      payload.next_after=body.after ? null : {moca_oid:1003,galactic_bin:0,cnn_bin:0,spectral_subtype:20,snr_1_2:3.5};
    }
  }
  if(op==='analyze'){
    payload.object.adopted_spt_source=body.adopted_spt_source;
    payload.object.adopted_spectral_type=body.adopted_spt_source==='public'?'M7':'T8';
    payload.object.adopted_spectral_type_reference=body.adopted_spt_source==='public'?'PubM7':'PrivateT8';
  }
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload)});
});
const url=origin+'/spherex-review?mock=1';
async function ready(){await page.waitForFunction(()=>document.querySelector('#object-title').textContent.includes('1001')&&!document.querySelector('#load').disabled&&!document.querySelector('#refit').disabled);}
async function load(){await page.locator('#load').click();await ready();}
const last=op=>requests.filter(r=>r.op===op).at(-1).body;
try{
  // A slow authentication response must not lock filter editing or start a queue.
  let releaseContext;contextGate=new Promise(resolve=>{releaseContext=resolve;});
  await page.goto(url,{waitUntil:'domcontentloaded'});
  await page.locator('#review-sample').selectOption('catwiseredmovers');
  assert(await page.locator('#sublime2-cuts').isHidden());
  assert.match(await page.locator('#sublime2-cuts-hint').innerText(),/not applied/);
  assert(await page.locator('#load').isDisabled());
  await page.locator('#snr').fill('3');
  assert.equal(await page.locator('#snr').inputValue(),'3');
  assert(requests.every(r=>r.op==='context'));
  releaseContext();contextGate=null;
  await page.waitForFunction(()=>!document.querySelector('#load').disabled);
  assert(requests.every(r=>r.op==='context'),'Opening the reviewer must not load a queue');
  await page.locator('#review-sample').selectOption('sublime2');
  assert(await page.locator('#sublime2-cuts').isVisible());
  await page.locator('#sublime2-snr').fill('9');
  await page.locator('#review-sample').selectOption('catwiseredmovers');
  assert(await page.locator('#sublime2-cuts').isHidden());
  await page.locator('#review-sample').selectOption('sublime2');
  assert.equal(await page.locator('#sublime2-snr').inputValue(),'9');
  await page.locator('#sublime2-snr').fill('');
  assert.equal(await page.locator('#sublime2-snr').inputValue(),'');
  assert(requests.every(r=>r.op==='context'),'Editing sample cuts must not request spectra');
  await page.locator('#sublime2-snr').fill('7');await page.locator('#snr').fill('2');
  await page.locator('#spectral-cnn-probability').fill('0.85');
  await page.locator('#cnn-priority-source').selectOption('spectral');
  await page.locator('#review-sample').selectOption('all');
  await load();
  assert.equal(await page.locator('#adopted-spt-source').inputValue(),'private');
  assert.match(await page.locator('#object-title').innerText(),/Adopted T8 \(PrivateT8\)/);
  for(const [id,value] of Object.entries({'sublime2-snr':'7','cnn-probability':'0.8','galactic-latitude':'15',snr:'2','snr-wavelength-range':'all','max-chi2':'1.5','queue-order':'gal_cnn_spt_snr'}))
    assert.equal(await page.locator('#'+id).inputValue(),value,id);
  assert(await page.locator('#exclude-duplicates').isChecked());
  const initial=last('queue');
  assert.equal(initial.cnn_priority_source,'spectral');assert.equal(initial.min_spectral_cnn_probability,'0.85');
  assert.equal(initial.exclude_duplicates,true);assert.equal(initial.min_sublime2_snr,'7');
  assert.equal(initial.min_cnn_probability,'0.8');assert.equal(initial.min_abs_galactic_latitude,'15');
  assert.equal(initial.min_snr,'2');assert.equal(initial.max_reduced_chi2,'1.5');
  assert.equal(initial.queue_order,'gal_cnn_spt_snr');
  await page.waitForFunction(()=>document.querySelector('#queue-total').textContent==='6 total matches at load');
  const {after,...cuts}=initial;assert.deepEqual(last('queue-count'),cuts);
  for(const sample of ['sublime2','catwiseredmovers','sublime1','public-ucd','all']){
    await page.locator('#review-sample').selectOption(sample);await load();
    const body=last('queue'),s2=['all','sublime2'].includes(sample);
    assert.equal(body.review_sample,sample);
    assert.equal(body.min_spectral_cnn_probability,'0.85');assert(await page.locator('#spectral-cnn-probability').isEnabled());
    assert.equal(body.min_sublime2_snr,s2?'7':null);assert.equal(body.min_cnn_probability,s2?'0.8':null);
    assert.equal(await page.locator('#sublime2-snr').isDisabled(),!s2);
    assert(await page.locator('#cnn-probability').isEnabled());
    assert.equal(await page.locator('#sublime2-cuts').isVisible(),s2);
    assert.equal(body.public_ucd_only,sample==='public-ucd');
    assert.equal(body.adopted_spt_source,sample==='public-ucd'?'public':'private');
    assert.match(await page.locator('#object-title').innerText(),sample==='public-ucd'?/Public-adopted M7 \(PubM7\)/:/Adopted T8 \(PrivateT8\)/);
  }
  // Public defaults can be overridden; the loaded queue retains its source for refits.
  await page.locator('#review-sample').selectOption('public-ucd');
  await page.locator('#adopted-spt-moca-pids').fill('PubM7, PubL5\nPubM7; Ref2025');
  await page.locator('#sptn').fill('7');await load();
  assert.deepEqual(last('queue').adopted_spt_moca_pids,['PubM7','PubL5','Ref2025']);
  assert.equal(last('queue').min_sptn,'7');
  await page.locator('#adopted-spt-source').selectOption('private');
  await page.locator('#refit').click();
  await page.waitForFunction(()=>!document.querySelector('#refit').disabled && document.querySelector('#object-title').textContent.includes('Public-adopted M7'));
  assert.equal(last('analyze').adopted_spt_source,'public');
  assert.match(await page.locator('#object-title').innerText(),/Public-adopted M7/);
  await load();assert.equal(last('queue').adopted_spt_source,'private');
  assert.match(await page.locator('#object-title').innerText(),/Adopted T8/);
  await page.locator('#review-sample').selectOption('all');
  assert.equal(await page.locator('#adopted-spt-source').inputValue(),'private');
  await page.locator('#adopted-spt-moca-pids').fill('');await page.locator('#sptn').fill('');
  // A catalog CNN cut can also be enabled independently for CatWISE matches.
  await page.locator('#review-sample').selectOption('catwiseredmovers');
  await page.locator('#cnn-probability').fill('0.4');await load();
  assert.equal(last('queue').min_cnn_probability,'0.4');
  assert.equal(last('queue').min_spectral_cnn_probability,'0.85');
  await page.locator('#review-sample').selectOption('all');
  assert.equal(await page.locator('#cnn-probability').inputValue(),'0.8');
  await page.locator('#review-sample').selectOption('catwiseredmovers');
  assert.equal(await page.locator('#cnn-probability').inputValue(),'0.4');
  await page.locator('#cnn-probability').fill('');
  // Ordinary sample switches retain the chosen missing-vetting scope.
  await page.locator('#missing-vetting').selectOption('both');
  await page.locator('#review-sample').selectOption('sublime1');
  await page.locator('#review-sample').selectOption('sublime2');
  assert.equal(await page.locator('#missing-vetting').inputValue(),'both');
  await page.locator('#cnn-priority-source').selectOption('sublime2');
  await page.locator('#wiseview-score').fill('4');
  await page.locator('#no-wiseview-score').check();assert(await page.locator('#wiseview-score').isDisabled());
  await page.locator('#snr-wavelength-range').selectOption('2.5-4');await load();
  assert.equal(last('queue').no_wiseview_score,true);assert.equal(last('queue').min_wiseview_score,null);
  assert.equal(last('queue').snr_wavelength_range,'2.5-4');
  await page.waitForFunction(()=>document.querySelector('#queue-total').textContent==='6 total matches at load');
  const loaded=last('queue');assert.equal(loaded.cnn_priority_source,'sublime2');
  await page.locator('#queue-order').selectOption('oid_desc');
  await page.locator('#snr-wavelength-range').selectOption('4-5');
  await page.locator('#adopted-spt-source').selectOption('public');
  await page.locator('#adopted-spt-moca-pids').fill('NewFilter');
  await page.locator('#more').click();
  await page.waitForFunction(()=>document.querySelector('#more').disabled&&!document.querySelector('#load').disabled);
  assert.deepEqual(last('queue'),{...loaded,after:{moca_oid:1003,galactic_bin:0,cnn_bin:0,spectral_subtype:20,snr_1_2:3.5}});
  await page.locator('#no-wiseview-score').uncheck();assert(await page.locator('#wiseview-score').isEnabled());
  assert.equal(await page.locator('#wiseview-score').inputValue(),'4');
  // Fresh loads honor each explicit ordering and blank numeric cuts.
  for(const order of ['spt_asc','oid_asc','oid_desc']){
    await page.locator('#queue-order').selectOption(order);await load();assert.equal(last('queue').queue_order,order);
  }
  for(const id of ['sublime2-snr','cnn-probability','spectral-cnn-probability','galactic-latitude','snr','max-chi2'])await page.locator('#'+id).fill('');
  await page.locator('#exclude-duplicates').uncheck();await load();
  for(const key of ['min_sublime2_snr','min_cnn_probability','min_spectral_cnn_probability','min_abs_galactic_latitude','min_snr','max_reduced_chi2'])assert.equal(last('queue')[key],null);
  assert.equal(last('queue').exclude_duplicates,false);
  // Old workers must never silently ignore new default cuts or sorting.
  for(const stale of ['context','queue']){
    contextVersion=stale==='context'?9:10;queueVersion=stale==='queue'?9:10;
    await page.goto(url);await page.waitForFunction(()=>!document.querySelector('#load').disabled);
    const before=requests.length;await page.locator('#load').click();
    await page.waitForFunction(()=>document.querySelector('#errors').textContent.includes('restarted'));
    assert(!requests.slice(before).some(r=>r.op==='analyze'));
  }
  // Exact-spectrum requests continue to bypass every queue filter.
  await page.goto(url+'&specid=2860761');await load();
  assert.deepEqual(last('queue'),{moca_specid:2860761,adopted_spt_source:'private',after:0,mock:true});
  assert.deepEqual(errors,[]);
  console.log('SPHEREx queue filter browser checks passed.');
}finally{await page.waitForLoadState('networkidle');await page.unrouteAll({behavior:'wait'});await browser.close();}
