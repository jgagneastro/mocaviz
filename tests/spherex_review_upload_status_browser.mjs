// Hold synthetic submissions to exercise the exhausted-queue state without DB writes.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.argv[2]||'http://127.0.0.1:8061';
const screenshot=process.argv[3];
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const requests=[],gates=[],errors=[];
let empty=false,closing=false;
page.on('pageerror',e=>errors.push(e.message));
page.on('dialog',dialog=>dialog.accept());
await page.emulateMedia({reducedMotion:'no-preference'});
await page.route('**/api/spherex-review/*',async route=>{
  const op=new URL(route.request().url()).pathname.split('/').at(-1),body=route.request().postDataJSON();
  requests.push({op,body});
  const fulfill=(payload,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify({ok:status===200,...payload})});
  if(op==='preview')return fulfill({receipt:'synthetic-plan',row_counts:{vetting:1},plan:{operations:[]}});
  if(op==='undo')return fulfill({undone:true});
  if(op==='submit'){
    const outcome=closing?'ok':await new Promise(resolve=>gates.push(resolve));
    try{return await (outcome==='fail'?fulfill({error:'Synthetic upload failure'},503):fulfill({submitted:true,undo_receipt:'synthetic-undo'}));}
    catch(e){if(!closing)throw e;return;}
  }
  assert(['context','queue','queue-count','analyze'].includes(op),'Unexpected API operation');
  const response=await route.fetch({postData:JSON.stringify({...body,mock:true})});
  const payload=await response.json();
  if(op==='context')Object.assign(payload,{can_write:true,role:'management'});
  if(op==='queue'&&!body.moca_specid){
    const all=empty?[]:payload.items.slice(0,3);
    const after=body.after?.moca_oid||0;
    const available=all.filter(row=>row.moca_oid>after);
    payload.items=available.slice(0,body.limit);payload.has_more=available.length>body.limit;
    const last=payload.items.at(-1);
    payload.next_after=last?{moca_oid:last.moca_oid,galactic_bin:0,cnn_bin:0,spectral_subtype:20,snr_1_2:3}:null;
  }
  if(op==='queue-count')payload.total=empty?0:3;
  return fulfill(payload);
});
const url=origin+'/spherex-review?user=management&pwd=test-placeholder&dbase=mocadb_private_tables';
async function target(oid){await page.waitForFunction(n=>document.querySelector('#object-title').textContent.includes(String(n))&&!document.querySelector('#report').disabled,oid);}
async function count(n){await page.waitForFunction(n=>document.querySelector('#submitting').textContent.startsWith(n+' '),n);}
async function release(index,outcome='ok'){
  const end=Date.now()+20000;
  while(!gates[index]&&Date.now()<end)await new Promise(resolve=>setTimeout(resolve,20));
  assert(gates[index],'Synthetic submit request never arrived');gates[index](outcome);
}
const lastQueue=()=>requests.filter(r=>r.op==='queue').at(-1).body;
try{
  empty=true;await page.goto(url);
  await page.waitForFunction(()=>document.querySelector('#object-title').textContent==='No matching spectra');
  assert(await page.locator('#upload-draining').isHidden());
  empty=false;await page.goto(url);await target(1001);
  assert.equal(await page.locator('#batch-size').inputValue(),'300');assert.equal(lastQueue().limit,300);
  assert(await page.locator('#upload-draining').isHidden());
  await page.locator('#batch-size').fill('2');await page.locator('#load').click();await target(1001);
  assert.equal(lastQueue().limit,2);
  await page.locator('#batch-size').fill('5');await page.locator('#more').click();await target(1003);
  assert.equal(lastQueue().limit,5);assert.equal(lastQueue().after.moca_oid,1002);
  for(const value of ['0','501','1.5','']){
    await page.locator('#batch-size').fill(value);const before=requests.filter(r=>r.op==='queue').length;
    await page.locator('#load').click();await page.waitForFunction(()=>document.querySelector('#errors').textContent.includes('Batch size'));
    assert.equal(requests.filter(r=>r.op==='queue').length,before);
  }
  await page.locator('#batch-size').fill('300');await page.locator('#load').click();await target(1001);
  await page.locator('#write-enabled').check();
  for(const oid of [1001,1002,1003]){
    await target(oid);await page.locator('[data-classification="good"]').click();
    if(oid<1003){await target(oid+1);assert(await page.locator('#upload-draining').isHidden());}
  }
  await count(3);await page.waitForSelector('#upload-draining',{state:'visible'});
  assert.equal(await page.locator('#upload-draining strong').textContent(),'Upload queue emptying...');
  assert.equal(await page.locator('#upload-remaining').textContent(),'3 results remaining');
  assert.equal(await page.locator('#upload-counts').textContent(),'1 uploading · 2 waiting');
  assert(await page.locator('#plot').evaluate(el=>!el.data?.length));
  assert.equal(await page.locator('.upload-spinner').evaluate(el=>getComputedStyle(el).animationName),'upload-spin');
  assert(await page.locator('#batch-size').isDisabled());
  const title=await page.locator('#upload-draining strong').boundingBox(),stage=await page.locator('.spectrum-stage').boundingBox();
  assert(Math.abs(title.x+title.width/2-stage.x-stage.width/2)<2);
  assert(await page.locator('#upload-draining strong').evaluate(el=>parseFloat(getComputedStyle(el).fontSize)>=24));
  if(screenshot)await page.locator('.spectrum-stage').screenshot({path:screenshot,animations:'disabled'});
  await release(0);await count(2);
  await page.waitForFunction(()=>document.querySelector('#upload-counts').textContent==='1 uploading · 1 waiting');
  assert.equal(await page.locator('#upload-remaining').textContent(),'2 results remaining');
  await release(1,'fail');await target(1002);await count(1);
  assert(await page.locator('#upload-draining').isHidden()); // a restored plot must stay unobscured
  await release(2);await count(0);
  assert(await page.locator('#upload-draining').isHidden());
  await page.locator('#retry').click();await count(1);await page.waitForSelector('#upload-draining',{state:'visible'});
  assert.equal(await page.locator('#upload-remaining').textContent(),'1 result remaining');
  await release(3);await count(0);await page.waitForSelector('#upload-draining',{state:'hidden'});
  assert(await page.locator('#load').isEnabled());assert(await page.locator('#batch-size').isEnabled());
  await page.goto(url+'&batch_size=7');await target(1001);assert.equal(lastQueue().limit,7);
  await page.locator('#write-enabled').check();
  for(const oid of [1001,1002,1003]){await target(oid);await page.locator('[data-classification="good"]').click();}
  await page.waitForSelector('#upload-draining',{state:'visible'});
  closing=true;await page.locator('#quit').click();
  await page.waitForFunction(()=>document.querySelector('#submitting').textContent==='Session closed');
  assert(await page.locator('#upload-draining').isHidden());
  assert.deepEqual(errors,[]);
  console.log('Passed: batch sizing and validation, next-batch resizing, upload spinner/counts, completion, failed-item restoration, retry and quit.');
}finally{
  closing=true;for(const resolve of gates)resolve('ok');
  await page.unrouteAll({behavior:'wait'});await browser.close();
}
