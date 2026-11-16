// Delayed and failed mock responses exercise visible refresh states without DB access.
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const origin=process.argv[2]||'http://127.0.0.1:8901';
const screenshots=process.argv[3];
if(screenshots)await mkdir(screenshots,{recursive:true});
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
await page.emulateMedia({reducedMotion:'no-preference'});
const errors=[],controls=new Set();
let closing=false,loadControl=null,diagnosticControl=null,failLoad=false,failDiagnostic=false,diagnosticRequests=0;
function gate(){let release;const promise=new Promise(resolve=>{release=resolve;});const control={promise,release,retired:false};controls.add(control);return control;}
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/findings/*',async route=>{
 const op=new URL(route.request().url()).pathname.split('/').at(-1);
 const control=op==='load'?loadControl:op==='diagnostics'?diagnosticControl:null;
 if(op==='diagnostics')diagnosticRequests++;
 try{
  const body=route.request().postDataJSON();
  assert.equal(body.mock,true,'Browser checks must never query the live database');
  if((op==='load'&&failLoad)||(op==='diagnostics'&&failDiagnostic)){
   if(op==='load')failLoad=false;else failDiagnostic=false;
   return await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({ok:false,error:'Synthetic refresh failure'})});
  }
  const response=await route.fetch();
  if(control)await control.promise;
  if(op==='load' && response.ok()){
   assert.equal(body.filters.min_motion,undefined,'Default minimum motion is disabled');
   const json=await response.json();
   Object.assign(json.rows[0],{motion:null,motion_class:null});
   return await route.fulfill({status:response.status(),json});
  }
  await route.fulfill({response});
 }catch(e){if(!closing&&!control?.retired)throw e;}
});
const state=async wanted=>page.waitForFunction(value=>document.querySelector('#refresh-state')?.dataset.state===value,wanted);
const title=async text=>page.waitForFunction(value=>document.querySelector('#refresh-state-title')?.textContent===value,text);
async function complete(){await state('done');assert.equal(await page.locator('#refresh-state-title').textContent(),'Refresh complete');assert.equal(await page.locator('#refresh-state-icon').textContent(),'✓');assert(await page.locator('#refresh').isEnabled());assert.equal(await page.locator('#refresh').getAttribute('aria-busy'),'false');}
async function snapshot(name){if(screenshots)await page.locator('#refresh-state').screenshot({path:screenshots+'/'+name+'.png'});}
try{
 loadControl=gate();
 const url=new URL(origin);url.searchParams.set('mock','1');url.searchParams.set('filters',JSON.stringify({sources:['sublime2'],min_spt:20}));
 await page.goto(url.href,{waitUntil:'domcontentloaded'});
 await state('loading');await title('Refreshing data…');
 assert(await page.locator('#refresh').isDisabled());
 assert.equal(await page.locator('#refresh-button-label').textContent(),'Refreshing…');
 assert.equal(await page.locator('#refresh-state-icon').evaluate(node=>getComputedStyle(node).animationName),'findings-refresh-spin');
 loadControl.release();loadControl=null;await complete();
 const count=await page.evaluate(()=>window.SublimeFindings.rows.length);assert(count>0);
 assert.equal(await page.locator('input[name="min_motion"]').inputValue(),'');
 assert.equal(await page.locator('.sample-metrics .metric').count(),3);
 assert.equal(await page.getByText('With absolute W2',{exact:true}).count(),0);
 await page.waitForFunction(()=>['histogram','motion','cmd'].every(id=>
  document.getElementById(id)?.data?.some(trace=>trace.name==='No motion vetting'&&trace.showlegend)));
 assert.ok(await page.locator('#motion').evaluate(plot=>plot.layout.yaxis.ticktext.includes('No motion vetting')));

 // The catalog and S/N histogram are available before diagnostics are requested.
 await page.waitForFunction(()=>document.getElementById('snr-histogram')?.layout?.yaxis.type==='log');
 const histogram=await page.locator('#snr-histogram').evaluate(node=>({
  axes:[node.layout.xaxis.type,node.layout.yaxis.type],
  objects:node.data.reduce((sum,t)=>sum+t.y.reduce((n,c)=>n+c,0),0),
  expected:window.SublimeFindings.rows.filter(r=>r.spiffstacker_snr>0).length,
 }));
 assert.deepEqual(histogram.axes,['log','log']);assert(histogram.objects>0);
 assert.equal(histogram.objects,histogram.expected);
 assert.equal(diagnosticRequests,0);
 await snapshot('catalog-ready');

 // Entering the diagnostics section starts background work and leaves catalog controls available.
 failDiagnostic=true;
 const spectra=gate();diagnosticControl=spectra;
 await page.locator('#diagnostics-status').scrollIntoViewIfNeeded();
 await page.waitForFunction(()=>document.querySelector('#diagnostics-status').textContent.includes('active spectra checked'));
 await complete();assert(diagnosticRequests>0);
 spectra.release();diagnosticControl=null;
 await page.locator('#load-diagnostics').waitFor({state:'visible'});
 assert((await page.locator('#diagnostics-status').textContent()).includes('failed'));
 await page.locator('#load-diagnostics').click();
 await page.waitForFunction(()=>document.querySelector('#snr-spiffstacker')?.data?.some(t=>t.x.length));
 await page.waitForFunction(()=>!document.querySelector('#diagnostics-status').textContent.includes('failed'));

 // A catalog failure retains the previous data and exposes an error, then retries.
 failLoad=true;await page.locator('#refresh').click();await state('error');
 assert.equal(await page.locator('#refresh-state-title').textContent(),'Refresh failed');
 assert((await page.locator('#refresh-state-detail').textContent()).includes('previous sample'));
 assert.equal(await page.evaluate(()=>window.SublimeFindings.rows.length),count);
 assert(await page.locator('#refresh').isEnabled());await snapshot('refresh-failed');
 await page.locator('#refresh').click();await complete();assert(await page.locator('#error').isHidden());

 // An aborted earlier request cannot clear a newer catalog request's busy indicator.
 const old=gate();loadControl=old;await page.locator('#refresh').click();await title('Refreshing data…');
 old.retired=true;
 const current=gate();loadControl=current;
 await page.locator('#apply').click();old.release();
 await page.waitForTimeout(150);
 assert.equal(await page.locator('#refresh-state').getAttribute('data-state'),'loading');
 assert(await page.locator('#refresh').isDisabled());
 current.release();loadControl=null;await complete();

 // Make all legend classes visible in this mock fixture and verify no overlap.
 await page.evaluate(()=>{const definitions=window.SublimeFindings.plotClasses;window.SublimeFindings.rows.slice(0,definitions.length).forEach((row,i)=>{row.plot_class=definitions[i].key;row.plot_class_label=definitions[i].label;});});
 await page.locator('#hist-bin').selectOption('2');
 await page.waitForFunction(()=>document.querySelectorAll('#histogram .legend .traces').length===window.SublimeFindings.plotClasses.length);
 const legendChecks=[];
 for(const width of [1440,1180,760]){
  await page.setViewportSize({width,height:1000});
  await page.waitForTimeout(350);
  const bounds=await page.locator('#histogram').evaluate(node=>{
   const legend=node.querySelector('.legend').getBoundingClientRect(),size=node._fullLayout._size,chart=node.getBoundingClientRect();
   return {legendTop:legend.top-chart.top,legendBottom:legend.bottom-chart.top,plotTop:size.t,plotHeight:size.h};
  });
  assert(bounds.legendBottom<=bounds.plotTop,JSON.stringify({width,...bounds}));
  assert(bounds.legendTop>=-1,JSON.stringify({width,...bounds}));
  assert(bounds.plotHeight>=140,JSON.stringify({width,...bounds}));
  legendChecks.push({width,...bounds});
 }
 if(screenshots)await page.locator('#histogram').screenshot({path:screenshots+'/histogram-legend.png'});
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({ok:true,checks:['catalog busy','log-log S/N histogram','lazy diagnostics and retry','catalog failure and retry','superseded request','histogram legend geometry'],legendChecks},null,2));
}finally{
 closing=true;for(const control of controls)control.release();await browser.close();
}
