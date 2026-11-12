// Synthetic failures and saves exercise real UI recovery; no database writes.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.argv[2]||'http://127.0.0.1:8061';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage(),gates=[],errors=[];
let closing=false;
page.on('pageerror',error=>errors.push(error.message));
page.on('dialog',dialog=>dialog.accept());
await page.clock.install();
await page.route('**/api/spherex-review/*',async route=>{
  const body=route.request().postDataJSON(),op=new URL(route.request().url()).pathname.split('/').at(-1);
  const fulfill=(payload,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify({ok:status===200,...payload})});
  if(op==='preview')return fulfill({receipt:'synthetic-plan',row_counts:{vetting:1},plan:{operations:[]}});
  if(op==='submit'){
    const outcome=closing?'ok':await new Promise(resolve=>gates.push(resolve));
    if(outcome==='fail')return fulfill({error:'Synthetic temporary failure.'},503);
    return outcome==='conflict'?fulfill({error:'Synthetic revision conflict.'},409):
      fulfill({submitted:true,undo_receipt:'synthetic-undo'});
  }
  assert(['context','queue','queue-count','analyze'].includes(op),'Unexpected API operation');
  const response=await route.fetch({postData:JSON.stringify({...body,mock:true})});
  const payload=await response.json();
  if(op==='context')Object.assign(payload,{can_write:true,role:'management',queue_filter_version:999});
  if(op==='queue')Object.assign(payload,{queue_filter_version:999,has_more:false,next_after:null,items:[
    {moca_oid:5058867,moca_specid:11001,designation:'Synthetic 5058867'},
    {moca_oid:1002,moca_specid:11002,designation:'Synthetic 1002'},
    {moca_oid:1003,moca_specid:11003,designation:'Synthetic 1003'}]});
  if(op==='queue-count')payload.total=3;
  return fulfill(payload);
});
const url=origin+'/spherex-autotype?user=management&pwd=test-placeholder&dbase=mocadb_private_tables';
async function target(oid){await page.waitForFunction(oid=>document.querySelector('#object-title').textContent.includes(String(oid))&&!document.querySelector('#report').disabled,oid);}
async function pending(n){await page.waitForFunction(n=>document.querySelector('#submitting').textContent.startsWith(n+' '),n);}
async function open(){
  await page.goto(url);await page.waitForFunction(()=>!document.querySelector('#load').disabled);
  await page.locator('#load').click();await target(5058867);await page.locator('#write-enabled').check();
}
async function classify(label='good'){
  const gate=gates.length;
  await page.locator(`[data-classification="${label}"]`).click();
  await pending(1);
  for(let n=0;n<100&&!gates[gate];n++)await new Promise(resolve=>setTimeout(resolve,20));
  assert(gates[gate],'Synthetic submission did not start');return gate;
}
async function finish(gate,outcome='ok'){gates[gate](outcome);await pending(0);}
try {
  await open();
  const failed=await classify('good_candidate');await target(1002);await finish(failed,'conflict');
  assert.match(await page.locator('#errors').innerText(),/5058867 failed/);
  assert.match(await page.locator('#submitting').innerText(),/1 awaiting retry/);
  await page.locator('#first').click();await target(1002);
  await page.locator('#load').click();await target(1002);
  await page.waitForLoadState('networkidle');await page.clock.fastForward(20000);
  assert(await page.locator('#errors').isHidden());
  assert(await page.locator('#retry').isEnabled(),'An expired banner must not discard its failed upload');
  const retry=gates.length;await page.locator('#retry').click();await pending(1);
  for(let n=0;n<100&&!gates[retry];n++)await new Promise(resolve=>setTimeout(resolve,20));
  assert(gates[retry]);await finish(retry);
  assert(await page.locator('#retry').isDisabled());

  // Undo during a failed request restores the decision without scheduling a retry.
  await open();
  const duringUndo=await classify();await target(1002);
  await page.locator('#undo').click();await finish(duringUndo,'fail');
  await target(5058867);
  assert.equal(gates.length,duringUndo+1);
  assert(await page.locator('#retry').isDisabled());

  // A previous timer cannot dismiss a newer failure banner.
  await open();
  const old=await classify();await target(1002);await finish(old,'conflict');
  await page.waitForLoadState('networkidle');await page.clock.fastForward(15000);
  const latest=await classify();await target(1003);await finish(latest,'conflict');
  await page.waitForLoadState('networkidle');await page.clock.fastForward(6000);
  assert.match(await page.locator('#errors').innerText(),/1002 failed/);
  await page.clock.fastForward(14000);
  assert(await page.locator('#errors').isHidden());

  // The expiry belongs to submission failures, not unrelated validation errors.
  await open();const validation=await classify();await target(1002);await finish(validation,'conflict');
  await page.locator('#batch-size').fill('0');await page.locator('#load').click();
  await page.waitForFunction(()=>document.querySelector('#errors').textContent.includes('Batch size'));
  await page.clock.fastForward(20000);
  assert.match(await page.locator('#errors').innerText(),/Batch size/);
  assert.deepEqual(errors,[]);
  console.log('Submission errors: retained decisions, manual retry, undo during failure, twenty-second expiry and newer/unrelated banner protection passed.');
} finally {
  closing=true;for(const resolve of gates)resolve('ok');
  await page.unrouteAll({behavior:'ignoreErrors'});await browser.close();
}
