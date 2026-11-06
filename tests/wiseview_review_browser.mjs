// Read-only integration check of a mounted reviewer and Findings page.
// Optional private profile is read locally; no credential is printed or persisted.
import {chromium} from 'playwright';
import fs from 'node:fs';
import os from 'node:os';
import assert from 'node:assert/strict';

const base=process.env.MOCAVIZ_TEST_BASE||'http://127.0.0.1:8089';
const profile=JSON.parse(fs.readFileSync(process.env.MOCAVIZ_TEST_SETTINGS||`${os.homedir()}/Library/Application Support/Web Tools/settings.json`,'utf8')).profiles[process.env.MOCAVIZ_TEST_PROFILE||'collaborators'];
const params=new URLSearchParams({user:profile.username,pwd:profile.password,dbase:profile.database||'mocadb_private_tables'});
const browser=await chromium.launch({headless:true});
let diagnosticPage;
try {
  const context=await browser.newContext({viewport:{width:1450,height:1000}});
  context.setDefaultTimeout(90000);
  const page=await context.newPage(),errors=[],writes=[];diagnosticPage=page;
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/wiseview-review/api/{classify,duplicate,undo}',route=>{writes.push('write blocked');return route.abort();});
  await page.goto(base+'/js/wiseview-review/?'+params,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>!document.querySelector('#queue-order').disabled,{timeout:60000});
  await page.locator('[name=moca_oids]').fill(process.env.MOCAVIZ_TEST_OID||'5007257');
  await page.locator('[name=reclass]').check();
  // Clear scientific cuts to load precisely the requested object.
  await page.evaluate(()=>{
    const form=document.querySelector('#filter-form');
    for(const field of form.elements){
      if(field.type==='number')field.value='';
      if(field.name?.includes('viz')||['any_lane_include','any_lane_exclude','sublime2cnn'].includes(field.name))field.value='';
      if(['no_known','nophotoknown','queue','souleymane','skip_missing_w2'].includes(field.name))field.checked=false;
    }
    for(const name of ['claims','byw_mode','duplicate_mode'])if(form.elements[name])form.elements[name].value='either';
  });
  await page.locator('#load').click();
  await page.waitForFunction(()=>document.querySelector('#object-ident').textContent.includes('OID '),{timeout:90000});
  assert.match(await page.locator('#object-ident').innerText(),new RegExp(process.env.MOCAVIZ_TEST_OID||'5007257'));
  await page.waitForFunction(()=>document.querySelector('#wise-pool iframe')?.src.startsWith('data:text/html'),{timeout:60000});
  await page.frameLocator('#wise-pool iframe').first().locator('canvas').first().waitFor({timeout:90000});
  const frame=page.frames().find(f=>f.url().startsWith('data:text/html'));
  assert.ok(frame,'credential-free frame exists');
  await page.waitForFunction(()=>document.querySelector('#plot .js-plotly-plot')?.data?.length>0,{timeout:90000});
  assert.equal(writes.length,0);
  assert.deepEqual(errors,[]);
  console.log('WiseView: single-object queue, object metadata, spectra and sandboxed image frame passed. No writes.');
  const findings=await context.newPage();
  await findings.goto(base+'/js/sublime-findings/?'+params+'&mock=1',{waitUntil:'domcontentloaded'});
  await findings.waitForFunction(()=>window.SublimeFindings?.rows?.length>0,{timeout:60000});
  assert.ok(await findings.locator('.js-plotly-plot').count()>0);
  console.log('Findings: mounted assets, API, synthetic sample and plots passed.');
  const home=await context.request.get(base+'/js/?'+params);
  const privateHtml=await home.text();
  assert.ok(privateHtml.includes('href="/wiseview-review/"')&&privateHtml.includes('href="/sublime-findings/"'));
  const publicHtml=await (await context.request.get(base+'/js/')).text();
  assert.ok(!publicHtml.includes('/wiseview-review')&&!publicHtml.includes('/sublime-findings'));
  console.log('Home: both private links present; neither URL in the public response.');
} catch(error) {
  if(diagnosticPage){console.error('Notice:',await diagnosticPage.locator('#notice').innerText().catch(()=>''));for(const frame of diagnosticPage.frames().slice(1)){console.error('Frame:',await frame.evaluate(()=>({title:document.title,jquery:typeof window.jQuery,canvas:document.querySelectorAll('canvas').length,body:document.body.innerText.slice(0,180)})).catch(()=>({unavailable:true})));}}
  const safe=String(error.message).replaceAll(profile.password,'[redacted]').replace(/([?&](?:pwd|password)=)[^&\s"']+/g,'$1[redacted]');
  console.error(safe);process.exitCode=1;
} finally {
  await browser.close();
}
