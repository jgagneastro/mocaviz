// Synthetic write transport only: no live database mutations.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.argv[2] || 'http://127.0.0.1:8077';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1500,height:1100}});
const errors=[], calls=[], frames=[];let review=null, releaseSubmit=null, releaseContext=null;
page.on('dialog',dialog=>dialog.accept());
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/spherex-review-wiseview*',async route=>{
  frames.push(route.request().url());assert(!route.request().headers()['x-moca-password']);
  await route.fulfill({contentType:'text/html',body:'<!doctype html><html><body>WiseView fixture</body></html>'});
});
await page.route('**/api/spherex-review/*',async route=>{
  const op=new URL(route.request().url()).pathname.split('/').at(-1), body=route.request().postDataJSON();
  calls.push({op,body}); let payload;
  if(op==='motion-preview') payload={ok:true,receipt:JSON.stringify(body)};
  else if(op==='motion-submit'){
    const target=JSON.parse(body.receipt);await new Promise(r=>releaseSubmit=r);
    review={classification_integer:6,classification:'clear motion, red detection',reviewer:'Test',comments:'saved'};
    payload={ok:true,review,object:target,undo_receipt:JSON.stringify(target)};
  }else if(op==='motion-undo'){review=null;payload={ok:true,undone:true};}
  else {
    assert(['context','queue','queue-count','analyze','motion-context'].includes(op),'Unexpected operation '+op);
    const response=await route.fetch({postData:JSON.stringify({...body,mock:true})});payload=await response.json();
    if(op==='context'){payload.role='management';payload.can_write=true;}
    if(op==='analyze'){payload.read_only=false;payload.object.ra=123+body.moca_oid/10000;payload.object.dec=-17.5;}
    if(op==='motion-context'){
      if(body.moca_oid===1001&&releaseContext!==null)await new Promise(r=>releaseContext=r);
      payload.revision='fake';payload.review=body.moca_oid===1001?review:null;
    }
  }
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload)});
});
try{
  await page.goto(origin+'/spherex-review',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>!document.querySelector('#load').disabled);
  await page.locator('#load').click();
  await page.waitForFunction(()=>document.querySelector('#motion-target').textContent.includes('1001')&&document.querySelector('#motion-classification').options.length>1);
  assert.equal(calls.filter(c=>c.op.startsWith('motion-')&&c.op!=='motion-context').length,0);
  assert(await page.locator('#motion-autoload').isChecked());
  await page.waitForFunction(()=>document.querySelector('#motion-frame').getAttribute('src'));
  const src=await page.locator('#motion-frame').getAttribute('src');
  assert(src.includes('ra=123.1001'));assert(!src.includes('user=')&&!src.includes('password='));
  assert.equal(await page.locator('#motion-frame').getAttribute('sandbox'),'allow-scripts');
  await page.locator('#write-enabled').check();
  await page.locator('#motion-classification').selectOption('6');
  await page.locator('#motion-save').click();
  await page.waitForFunction(()=>document.querySelector('#motion-last-action').textContent.includes('Saving'));
  await page.locator('#next').click();
  await page.waitForFunction(()=>document.querySelector('#motion-target').textContent.includes('1002'));
  while(!releaseSubmit)await new Promise(r=>setTimeout(r,20));releaseSubmit();
  await page.waitForFunction(()=>document.querySelector('#motion-last-action').textContent.includes('Saved motion 6 for OID 1001'));
  assert.equal(JSON.parse(calls.find(c=>c.op==='motion-submit').body.receipt).moca_oid,1001);
  await page.waitForFunction(()=>document.querySelector('#motion-stored').textContent.includes('No motion'));
  await page.locator('#previous').click();
  await page.waitForFunction(()=>document.querySelector('#motion-stored').textContent.includes('Stored motion: 6'));
  await page.locator('#motion-classification').selectOption('5');
  assert(await page.locator('#motion-save').isDisabled());
  await page.locator('#motion-replace').check();assert(await page.locator('#motion-save').isEnabled());
  await page.locator('#motion-classification').selectOption('');
  await page.locator('#motion-undo').click();
  await page.waitForFunction(()=>document.querySelector('#motion-stored').textContent==='No motion review stored.');
  assert(await page.locator('#motion-undo').isDisabled());
  const n=frames.length;await page.locator('#motion-autoload').uncheck();await page.locator('#next').click();
  await page.waitForFunction(()=>document.querySelector('#motion-target').textContent.includes('1002'));
  assert(await page.locator('#motion-frame').isHidden());assert.equal(frames.length,n);
  await page.locator('#motion-autoload').check();await page.waitForFunction(()=>!document.querySelector('#motion-frame').hidden);
  await page.locator('#motion-panel').screenshot({path:'/tmp/spherex_motion_feature/panel.png'});
  assert.deepEqual(errors,[]);console.log('Motion browser checks passed: no implicit writes, target-safe save, replacement, undo, autoload, opaque iframe.');
} catch(error) {console.error('Test failed:',error);console.error('Page errors:',errors);console.error('Last calls:',calls.slice(-5));throw error;} finally {await page.unrouteAll({behavior:'ignoreErrors'});await browser.close();}
