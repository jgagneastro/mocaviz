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
    return outcome==='fail'?fulfill({error:'Database request failed. Reload to check its state before retrying; no submission is assumed successful.'},503):
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
  const failed=await classify();await target(1002);await finish(failed,'fail');
  assert.match(await page.locator('#errors').innerText(),/5058867 failed/);
  await page.locator('#first').click();await target(5058867);
  const replacement=await classify('good_candidate');await target(1002);
  assert(await page.locator('#errors').isVisible(),'Keep the error until the replacement upload succeeds');
  await finish(replacement);
  assert(await page.locator('#errors').isHidden(),'A new classification must clear the earlier failed job’s message');
  assert(await page.locator('#retry').isDisabled(),'A successful replacement must supersede the old failed decision');

  // Fixing one target must preserve another target’s still-current failure.
  await open();
  const first=await classify();await target(1002);await finish(first,'fail');
  const second=await classify();await target(1003);await finish(second,'fail');
  await page.locator('#first').click();await target(5058867);
  await finish(await classify('good_candidate'));await target(1002);
  assert.match(await page.locator('#errors').innerText(),/1002 failed/);
  assert(await page.locator('#retry').isEnabled());
  await page.waitForLoadState('networkidle');await page.clock.fastForward(20000);
  assert(await page.locator('#errors').isHidden(),'Submission banners expire within twenty seconds');
  assert(await page.locator('#retry').isEnabled(),'An expired banner must not discard its failed upload');
  const retry=gates.length;await page.locator('#retry').click();await pending(1);
  for(let n=0;n<100&&!gates[retry];n++)await new Promise(resolve=>setTimeout(resolve,20));
  assert(gates[retry]);await finish(retry);
  assert(await page.locator('#errors').isHidden());assert(await page.locator('#retry').isDisabled());

  // A previous timer cannot dismiss a newer failure banner.
  await open();
  const old=await classify();await target(1002);await finish(old,'fail');
  await page.waitForLoadState('networkidle');await page.clock.fastForward(15000);
  const latest=await classify();await target(1003);await finish(latest,'fail');
  await page.waitForLoadState('networkidle');await page.clock.fastForward(6000);
  assert.match(await page.locator('#errors').innerText(),/1002 failed/);
  await page.clock.fastForward(14000);
  assert(await page.locator('#errors').isHidden());

  // A classification replaces an earlier classification, not a separate failed Save type operation.
  await open();const save=gates.length;await page.locator('#save-type').click();await pending(1);await target(1002);
  for(let n=0;n<100&&!gates[save];n++)await new Promise(resolve=>setTimeout(resolve,20));
  assert(gates[save]);await finish(save,'fail');
  await page.locator('#first').click();await target(5058867);await finish(await classify());await target(1002);
  assert(await page.locator('#errors').isHidden());
  assert(await page.locator('#retry').isEnabled(),'Keep a different failed action available to retry');

  // The expiry belongs to submission failures, not unrelated validation errors.
  await open();const validation=await classify();await target(1002);await finish(validation,'fail');
  await page.locator('#batch-size').fill('0');await page.locator('#load').click();
  await page.waitForFunction(()=>document.querySelector('#errors').textContent.includes('Batch size'));
  await page.clock.fastForward(20000);
  assert.match(await page.locator('#errors').innerText(),/Batch size/);
  assert.deepEqual(errors,[]);
  console.log('Submission errors: successful reclassification/retry, twenty-second expiry, retained retry state and newer/unrelated banner protection passed.');
} finally {
  closing=true;for(const resolve of gates)resolve('ok');
  await page.unrouteAll({behavior:'ignoreErrors'});await browser.close();
}
