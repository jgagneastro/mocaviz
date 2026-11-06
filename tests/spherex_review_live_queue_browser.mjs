// Manual, read-only CatWISE integration check. Private credentials stay in memory.
import {chromium} from 'playwright';
import fs from 'node:fs';
import os from 'node:os';
import assert from 'node:assert/strict';

const base=process.env.MOCAVIZ_TEST_BASE||'http://127.0.0.1:8089';
const profile=JSON.parse(fs.readFileSync(`${os.homedir()}/Library/Application Support/Web Tools/settings.json`,'utf8')).profiles.collaborators;
const params=new URLSearchParams({user:profile.username,pwd:profile.password,dbase:profile.database||'mocadb_private_tables'});
const browser=await chromium.launch({headless:true});
try {
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  context.setDefaultTimeout(85000);
  const page=await context.newPage(),writes=[],errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/spherex-review/*',route=>{
    const operation=new URL(route.request().url()).pathname.split('/').at(-1);
    if(!['context','queue','queue-count','analyze'].includes(operation)){writes.push(operation);return route.abort();}
    return route.continue();
  });
  await page.goto(base+'/spherex-review?'+params,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>!document.querySelector('#load').disabled);
  await page.locator('#lane').selectOption('spiffstacker');
  await page.locator('#review-sample').selectOption('catwiseredmovers');
  await page.locator('#queue-order').selectOption('gal_cnn_spt_snr');
  for(const [id,value] of Object.entries({'batch-size':'100','sptn':'','galactic-latitude':'15','snr':'2','max-chi2':'1.5'}))await page.locator('#'+id).fill(value);
  await page.locator('#snr-wavelength-range').selectOption('all');
  await page.locator('#missing-vetting').selectOption('lane');
  await page.locator('#no-known').check();await page.locator('#exclude-duplicates').check();
  const started=Date.now();
  await page.locator('#load').click();
  await page.waitForFunction(()=>document.querySelector('#plot')?.data?.length>0);
  console.log('CatWISE first spectrum rendered in',((Date.now()-started)/1000).toFixed(1),'seconds.');
  await page.waitForFunction(()=>document.querySelector('#queue-total').textContent.includes('total matches at load'));
  console.log('Queue:',await page.locator('#queue-info').innerText());
  console.log('Count:',await page.locator('#queue-total').innerText());
  assert.equal(await page.locator('#errors').isVisible(),false);
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  console.log('Live queue, exact count and rendered spectrum passed; no review submissions.');
} catch(error) {
  console.error(String(error.message).replaceAll(profile.password,'[redacted]').replace(/([?&](?:pwd|password)=)[^&\s"']+/g,'$1[redacted]'));
  process.exitCode=1;
} finally {await browser.close();}
