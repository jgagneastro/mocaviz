// Gate synthetic requests to verify automatic paging; no database writes.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.argv[2]||'http://127.0.0.1:8061';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage();
const errors=[];let state;
page.on('pageerror',error=>errors.push(error.message));
page.on('dialog',dialog=>dialog.accept());
await page.route('**/api/spherex-review/*',async route=>{
  const scenario=state,op=new URL(route.request().url()).pathname.split('/').at(-1);
  const body=route.request().postDataJSON();scenario.requests.push({op,body});
  const send=async(payload,status=200)=>{
    try{await route.fulfill({status,contentType:'application/json',body:JSON.stringify({ok:status===200,...payload})});}
    catch(error){if(!scenario.ended)throw error;}
  };
  if(op==='preview')return send({receipt:String(body.moca_oid),row_counts:{vetting:1},plan:{operations:[]}});
  if(op==='undo'){scenario.undos++;return send({undone:true});}
  if(op==='submit'){
    const oid=Number(body.receipt);
    const outcome=scenario.holdSubmits?await new Promise(resolve=>scenario.submits.push({oid,resolve})):'ok';
    if(outcome==='fail'||(!scenario.failedOnce&&oid===scenario.failOid)){
      scenario.failedOnce=true;return send({error:'Synthetic submission failed'},503);
    }
    return send({submitted:true,undo_receipt:'synthetic-undo'});
  }
  if(op==='queue-count'){
    if(scenario.holdCount)await new Promise(resolve=>{scenario.releaseCount=resolve;});
    return send({total:5});
  }
  assert(['context','queue','analyze'].includes(op),'Unexpected API operation');
  if(op==='queue'&&body.after){
    if(scenario.holdNext)await new Promise(resolve=>{scenario.releaseNext=resolve;});
    if(scenario.failNext){scenario.failNext=false;return send({error:'Synthetic next batch failed'},503);}
  }
  const response=await route.fetch({postData:JSON.stringify({...body,mock:true})});
  const payload=await response.json();
  if(op==='context')Object.assign(payload,{can_write:true,role:'management'});
  if(op==='queue'){
    const all=payload.items.slice(0,5),after=body.after?.moca_oid||0;
    const available=all.filter(item=>item.moca_oid>after);
    payload.items=available.slice(0,body.limit);payload.has_more=available.length>body.limit;
    const last=payload.items.at(-1);
    payload.next_after=last?{moca_oid:last.moca_oid,galactic_bin:0,cnn_bin:0,spectral_subtype:20,snr_1_2:3}:null;
    if((scenario.emptyNext&&body.after)||scenario.emptyInitial){
      payload.items=[];payload.has_more=true;
      payload.next_after={moca_oid:1999,galactic_bin:0,cnn_bin:0,spectral_subtype:20,snr_1_2:3};
    }
  }
  return send(payload);
});
const url=origin+'/spherex-review?user=management&pwd=test-placeholder&dbase=mocadb_private_tables';
const queues=()=>state.requests.filter(request=>request.op==='queue');
async function until(check,label){
  const end=Date.now()+20000;
  while(!check()&&Date.now()<end)await new Promise(resolve=>setTimeout(resolve,20));
  assert(check(),label);
}
async function settle(){await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));}
async function target(oid){await page.waitForFunction(oid=>document.querySelector('#object-title').textContent.includes(String(oid))&&!document.querySelector('#report').disabled,oid);}
async function pending(count){await page.waitForFunction(count=>document.querySelector('#submitting').textContent.startsWith(count+' '),count);}
async function open(options={}){
  if(state){state.ended=true;state.releaseCount?.();state.releaseNext?.();for(const gate of state.submits)gate.resolve('ok');}
  state={requests:[],submits:[],undos:0,ended:false,...options};
  await page.goto(url);await page.waitForFunction(()=>!document.querySelector('#load').disabled);
  assert.equal(queues().length,0,'Opening the page must not auto-load an initial sample');
  await page.locator('#batch-size').fill('3');await page.locator('#load').click();
  if(!state.emptyInitial){await target(1001);await page.locator('#write-enabled').check();}
}
async function classify(oids){for(const oid of oids){await target(oid);await page.locator('[data-classification="good"]').click();}}
async function release(index,outcome='ok'){
  await until(()=>state.submits[index],'Missing synthetic submission '+index);
  state.submits[index].resolve(outcome);
}
try{
  // Wait for uploads and a held background download/count, then request once.
  await open({holdSubmits:true,holdCount:true,holdNext:true});
  const first={...queues()[0].body};
  await page.locator('#snr').fill('8');await page.locator('#queue-order').selectOption('oid_desc');
  await page.locator('#review-sample').selectOption('catwiseredmovers');
  await page.locator('#batch-size').fill('2');
  await classify([1001,1002,1003]);await pending(3);
  assert(await page.locator('#upload-draining').isVisible());assert.equal(queues().length,1);
  await release(0);await pending(2);assert.equal(queues().length,1);
  await release(1);await pending(1);assert.equal(queues().length,1);
  await release(2);await pending(0);await settle();
  assert.equal(queues().length,1,'Held background requests must finish before automatic paging');
  await until(()=>state.releaseCount,'Missing held count');state.releaseCount();
  await until(()=>queues().length===2&&state.releaseNext,'No automatic next batch');
  assert.equal(await page.locator('#status').innerText(),'Loading next batch automatically…');
  assert.deepEqual(queues()[1].body,{...first,limit:2,after:{moca_oid:1003,galactic_bin:0,cnn_bin:0,spectral_subtype:20,snr_1_2:3}});
  await settle();assert.equal(queues().length,2,'Only one automatic request may be in flight');
  state.releaseNext();await target(1004);
  assert.equal(state.requests.filter(request=>request.op==='queue-count').length,1);
  // Undo still returns to a record in the preceding batch.
  await page.locator('#undo').click();await target(1003);assert.equal(state.undos,1);
  await classify([1003,1004,1005]);await pending(3);
  for(const index of [3,4,5])await release(index);
  await pending(0);await settle();assert.equal(queues().length,2);
  assert.equal(await page.locator('#object-title').innerText(),'Queue complete');
  assert(await page.locator('#more').isDisabled());

  // A batch failure is attempted once; manual Next batch can retry.
  await open({failNext:true});await classify([1001,1002,1003]);
  await page.waitForFunction(()=>document.querySelector('#errors').textContent.includes('Synthetic next batch failed'));
  await settle();assert.equal(queues().length,2);
  await page.locator('#review-sample').selectOption('catwiseredmovers');await settle();assert.equal(queues().length,2);
  await page.locator('#more').click();await target(1004);assert.equal(queues().length,3);

  // Even a broken empty response with another cursor must not loop.
  await open({emptyNext:true});await classify([1001,1002,1003]);
  await page.waitForFunction(()=>document.querySelector('#object-meta').textContent.includes('No spectra returned'));
  await settle();assert.equal(queues().length,2);

  // Failed reviews are restored before paging; retry can resume the transition.
  await open({failOid:1002});await classify([1001,1002,1003]);await target(1002);await pending(0);
  assert.equal(queues().length,1,'A failed submission must stay available for review');
  await page.locator('#retry').click();await target(1004);assert.equal(queues().length,2);

  // Quit during draining must never schedule a later batch.
  await open({holdSubmits:true});await classify([1001,1002,1003]);await pending(3);
  state.ended=true;await page.locator('#quit').click();
  for(const gate of state.submits)gate.resolve('ok');await settle();
  assert.equal(queues().length,1);
  assert.equal(await page.locator('#object-title').innerText(),'Review session closed');

  await open({emptyInitial:true});
  await page.waitForFunction(()=>document.querySelector('#object-title').textContent==='No matching spectra');
  await settle();assert.equal(queues().length,1,'Empty initial results must not start a paging loop');
  assert.deepEqual(errors,[]);
  console.log('Passed: automatic paging waits for uploads/requests, uses loaded filters/current batch size, requests once, preserves Undo, stops at end/error/empty results, restores failed reviews, and respects Quit.');
}finally{
  if(state){state.ended=true;state.releaseCount?.();state.releaseNext?.();for(const gate of state.submits)gate.resolve('ok');}
  await page.unrouteAll({behavior:'wait'});await browser.close();
}
