// Synthetic reads check policy capability and classification button semantics.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.argv[2]||'http://127.0.0.1:8061';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage(),errors=[];
let version=0;
page.on('pageerror',error=>errors.push(error.message));
await page.route('**/api/spherex-review/*',async route=>{
  const op=new URL(route.request().url()).pathname.split('/').at(-1),body=route.request().postDataJSON();
  assert(['context','queue','queue-count','analyze'].includes(op),'Unexpected write request');
  const response=await route.fetch({postData:JSON.stringify({...body,mock:true})});
  const payload=await response.json();
  if(op==='context')Object.assign(payload,{can_write:true,role:'management',write_policy_version:version});
  await route.fulfill({json:payload});
});
try{
  const url=origin+'/spherex-autotype?user=management&pwd=test-placeholder&dbase=mocadb_private_tables';
  await page.goto(url);await page.waitForFunction(()=>!document.querySelector('#load').disabled);
  assert(await page.locator('#write-enabled').isDisabled());
  assert.match(await page.locator('#write-hint').innerText(),/Restart.*automatic/);
  version=1;await page.reload();await page.waitForFunction(()=>!document.querySelector('#load').disabled);
  assert(await page.locator('#write-enabled').isEnabled());
  assert.equal(await page.locator('[data-classification=giant]').getAttribute('class'),'reject');
  for(const label of ['good','good_candidate','good_plus_star','incomplete_but_promising','weird'])
    assert.equal(await page.locator(`[data-classification=${label}]`).getAttribute('class'),'usable');
  assert.match(await page.locator('#write-settings .hint').innerText(),/reactivate autotypes and spectra/);
  assert.deepEqual(errors,[]);
  console.log('Automatic flag policy: stale-service write guard, updated instructions and giant/accepted button states passed.');
}finally{await page.unrouteAll({behavior:'ignoreErrors'});await browser.close();}
