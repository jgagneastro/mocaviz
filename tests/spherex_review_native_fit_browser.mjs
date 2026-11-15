// Current-fit cuts use the rendered fit, never the object's stored adopted type.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';
const origin=process.argv[2]||'http://127.0.0.1:8061';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage();
const errors=[], requests=[];
if(process.env.REVIEW_STATIC_ROOT){
  await page.route(/spherex_review\.(js|html)(\?.*)?$/,async route=>{
    const name=new URL(route.request().url()).pathname.split('/').at(-1);
    await route.fulfill({status:200,contentType:name.endsWith('.js')?'application/javascript':'text/html',
      body:await readFile(process.env.REVIEW_STATIC_ROOT+'/'+name+'.stage','utf8')});
  });
  await page.route('**/spherex-review?*',async route=>{
    await route.fulfill({status:200,contentType:'text/html',body:await readFile(process.env.REVIEW_STATIC_ROOT+'/spherex_review.html.stage','utf8')});
  });
}
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/spherex-review/*',async route=>{
  const op=new URL(route.request().url()).pathname.split('/').at(-1);
  const body=route.request().postDataJSON(); requests.push({op,body});
  assert(['context','queue','queue-count','analyze'].includes(op),'No vetting write is permitted');
  const response=await route.fetch({postData:JSON.stringify({...body,mock:true})});
  const payload=await response.json();
  if(op==='queue'&&!body.moca_specid){
    const after=body.after?.moca_oid||0;
    const available=payload.items.slice(0,5).filter(item=>item.moca_oid>after);
    payload.items=available.slice(0,body.limit);payload.has_more=available.length>body.limit;
    payload.next_after=payload.items.length?{moca_oid:payload.items.at(-1).moca_oid}:null;
  }
  if(op==='analyze'){
    const oid=payload.object.moca_oid;
    payload.object.adopted_spectral_type='T1';
    const number={1001:-10,1002:10,1004:10,1005:9.5}[oid];
    if(oid===1003)payload.fit=null;
    else {
      Object.assign(payload.fit.best,{spectral_type_number:number,spectral_type:number===10?'L0':number<0?'K0':'M0',display_type:number===10?'L0':number<0?'K0':'M0'});
      payload.fit.overlays[0].label=payload.fit.best.display_type;
      payload.fit.fit_version="native_signed_student4_v1";
      payload.fit.delta_early_minus_late=oid===1002?1.999:2.0;
    }
  }
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload)});
});
try{
  await page.goto(origin+'/spherex-review?mock=1');
  await page.waitForFunction(()=>!document.querySelector('#load').disabled);
  await page.locator('#review-sample').selectOption('sublime3c');
  assert.equal(await page.locator('#current-fit-sptn').inputValue(),'10');
  assert.equal(await page.locator('#current-fit-gap').inputValue(),'2');
  assert(await page.locator('#sublime3c-selection-pass').isChecked());
  assert(await page.locator('#sublime3c-selection-controls').isVisible());
  await page.locator('#batch-size').fill('3');await page.locator('#load').click();
  await page.waitForFunction(()=>document.querySelector('#object-title').textContent.includes('1004')&&!document.querySelector('#report').disabled);
  assert((await page.locator('#object-title').textContent()).includes('Current fit L0 · Adopted T1'));
  assert((await page.locator('#fit-filter-info').textContent()).startsWith('3 spectra skipped'));
  assert((await page.locator('#queue-total').textContent()).includes('before current-fit cut'));
  assert.equal(requests.filter(x=>x.op==='queue').length,2,'All-rejected first batch must advance automatically');
  await page.locator('#next').click();
  await page.waitForFunction(()=>document.querySelector('#fit-filter-info').textContent.startsWith('4 spectra skipped'));
  assert((await page.locator('#object-title').textContent()).includes('1004'),'Last retained object remains visible at the end');
  assert((await page.locator('#fit-filter-info').textContent()).startsWith('4 spectra skipped'));
  assert(requests.filter(x=>['queue','queue-count'].includes(x.op)).every(x=>x.body.sublime3c_selection_pass_only===true));
  await page.locator('#sublime3c-selection-pass').uncheck();
  await page.locator('#load').click();
  await page.waitForFunction(()=>!document.querySelector('#load').disabled);
  assert.equal(requests.filter(x=>x.op==='queue').at(-1).body.sublime3c_selection_pass_only,false);
  await page.locator('#review-sample').selectOption('all');
  assert(await page.locator('#sublime3c-selection-controls').isHidden());
  assert.equal(await page.locator('#current-fit-sptn').inputValue(),'');
  await page.locator('#specid').fill('11001');await page.locator('#load').click();
  await page.waitForFunction(()=>document.querySelector('#object-title').textContent.includes('Current fit K0')&&!document.querySelector('#report').disabled);
  await page.screenshot({path:'/tmp/s3c-native-fit-reviewer.png',fullPage:false});
  assert.deepEqual(errors,[]);
  console.log('Passed: native K0 and ambiguous L0 are skipped, missing fits fail, L0 boundary passes, M9.5 fails, automatic batching and direct-ID inspection work; no writes.');
}catch(e){console.log(JSON.stringify({requests:requests.map(r=>({op:r.op,after:r.body.after,oid:r.body.moca_oid})),errors,text:await page.locator('body').innerText()}));throw e;}finally{await page.unrouteAll({behavior:'wait'});await browser.close();}
