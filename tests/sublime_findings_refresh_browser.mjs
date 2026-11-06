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
let closing=false,loadControl=null,diagnosticControl=null,failLoad=false,failDiagnostic=false;
function gate(){let release;const promise=new Promise(resolve=>{release=resolve;});const control={promise,release,retired:false};controls.add(control);return control;}
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/findings/*',async route=>{
 const op=new URL(route.request().url()).pathname.split('/').at(-1);
 const control=op==='load'?loadControl:op==='diagnostics'?diagnosticControl:null;
 try{
  const body=route.request().postDataJSON();
  assert.equal(body.mock,true,'Browser checks must never query the live database');
  if((op==='load'&&failLoad)||(op==='diagnostics'&&failDiagnostic)){
   if(op==='load')failLoad=false;else failDiagnostic=false;
   return await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({ok:false,error:'Synthetic refresh failure'})});
  }
  const response=await route.fetch();
  if(control)await control.promise;
  await route.fulfill({response});
 }catch(e){if(!closing&&!control?.retired)throw e;}
});
const state=async wanted=>page.waitForFunction(value=>document.querySelector('#refresh-state')?.dataset.state===value,wanted);
const title=async text=>page.waitForFunction(value=>document.querySelector('#refresh-state-title')?.textContent===value,text);
async function complete(){await state('done');assert.equal(await page.locator('#refresh-state-title').textContent(),'Refresh complete');assert.equal(await page.locator('#refresh-state-icon').textContent(),'✓');assert(await page.locator('#refresh').isEnabled());assert.equal(await page.locator('#refresh').getAttribute('aria-busy'),'false');assert(await page.locator('#refresh-state-progress').isHidden());}
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

 // A visible busy state spans both the catalog request and progressive diagnostics.
 const catalog=gate(),spectra=gate();loadControl=catalog;diagnosticControl=spectra;
 await page.locator('#refresh').click();await title('Refreshing data…');
 await page.waitForFunction(()=>document.querySelector('#refresh-state-elapsed').textContent!=='0 s');
 await snapshot('refreshing-data');
 catalog.release();loadControl=null;
 await title('Refreshing spectra…');
 assert(await page.locator('#refresh-state-progress').isVisible());
 assert(await page.locator('#refresh').isDisabled());
 await snapshot('refreshing-spectra');
 spectra.release();diagnosticControl=null;await complete();await snapshot('refresh-complete');

 // Diagnostic failures end the spinner with an explicit partial outcome.
 failDiagnostic=true;await page.locator('#refresh').click();await state('partial');
 assert((await page.locator('#refresh-state-detail').textContent()).includes('failed'));
 assert(await page.locator('#refresh').isEnabled());

 // A catalog failure retains the previous data and exposes an error, then retries.
 failLoad=true;await page.locator('#refresh').click();await state('error');
 assert.equal(await page.locator('#refresh-state-title').textContent(),'Refresh failed');
 assert((await page.locator('#refresh-state-detail').textContent()).includes('previous sample'));
 assert.equal(await page.evaluate(()=>window.SublimeFindings.rows.length),count);
 assert(await page.locator('#refresh').isEnabled());await snapshot('refresh-failed');
 await page.locator('#refresh').click();await complete();assert(await page.locator('#error').isHidden());

 // An aborted earlier request cannot clear a newer refresh's busy indicator.
 const old=gate();loadControl=old;await page.locator('#refresh').click();await title('Refreshing data…');
 old.retired=true;loadControl=null;
 const current=gate();diagnosticControl=current;
 await page.locator('#apply').click();await title('Refreshing spectra…');old.release();
 await page.waitForTimeout(150);
 assert.equal(await page.locator('#refresh-state').getAttribute('data-state'),'loading');
 assert(await page.locator('#refresh').isDisabled());
 current.release();diagnosticControl=null;await complete();

 // Make all legend classes visible in this mock fixture and verify no overlap.
 await page.evaluate(()=>{const definitions=window.SublimeFindings.plotClasses;window.SublimeFindings.rows.slice(0,definitions.length).forEach((row,i)=>{row.plot_class=definitions[i].key;row.plot_class_label=definitions[i].label;});});
 await page.locator('#hist-bin').selectOption('2');
 await page.waitForFunction(()=>document.querySelectorAll('#histogram .legend .traces').length===7);
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
 console.log(JSON.stringify({ok:true,checks:['catalog busy','spectral busy/progress','completed','partial failure','catalog failure and retry','superseded request','histogram legend geometry'],legendChecks},null,2));
}finally{
 closing=true;for(const control of controls)control.release();await browser.close();
}
