// Header values must follow navigation/refits; every API read is synthetic.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.argv[2]||'http://127.0.0.1:8061';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage();
const errors=[];let refitted=false;
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/spherex-review/*',async route=>{
  const op=new URL(route.request().url()).pathname.split('/').at(-1);
  const body=route.request().postDataJSON();
  assert(['context','queue','queue-count','analyze'].includes(op),'Unexpected write request');
  const response=await route.fetch({postData:JSON.stringify({...body,mock:true})});
  const payload=await response.json();
  if(op==='analyze'){
    const oid=payload.object.moca_oid;
    payload.object.sublime2_cnn_probability=.95;
    payload.object.spectral_cnn_probability=oid===1001?.87654:oid===1002?0:null;
    payload.object.spectral_cnn={model:"test-model.joblib"};
    if(oid===1001){
      const chi2=refitted?.8:1.234;
      payload.fit.overlays[0].display_reduced_chi2=chi2;
    }else if(oid===1002){
      delete payload.fit.overlays[0].display_reduced_chi2;
      payload.fit.best.robust_reduced_chi2_10pct_cap=null;
      payload.fit.best.reduced_chi2_10pct_cap=2.75;
      payload.fit.matches[0]={...payload.fit.best};
    }else if(oid===1003){payload.fit=null;payload.warning='Synthetic missing fit';}
    else if(oid===1004){payload.object.spectral_cnn_probability=null;delete payload.object.spectral_cnn;}
    else if(oid===1006){delete payload.object.spectral_cnn_probability;}
  }
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload)});
});
async function target(oid){await page.waitForFunction(n=>document.querySelector('#object-title').textContent.includes(String(n))&&!document.querySelector('#refit').disabled,oid);}
async function values(cnn,chi2){
  assert.equal(await page.locator('#header-cnn').textContent(),'Spectral CNN P(good)='+cnn);
  assert.equal(await page.locator('#header-chi2').textContent(),'χ²ᵣ='+chi2);
}
try{
  await page.goto(origin+'/spherex-review?mock=1');await page.locator('#load').click();await target(1001);await values('87.7%','1.23');
  assert((await page.locator('#header-cnn').getAttribute('title')).includes('test-model.joblib'));
  assert.equal(await page.locator('#header-sublime2-cnn').textContent(),'SUBLIME2 CNN P=95.0%');
  await page.locator('#next').click();await target(1002);await values('0.0%','2.75');
  await page.locator('#next').click();await target(1003);await values('—','—');
  await page.locator('#next').click();await target(1004);assert.equal(await page.locator('#header-cnn').textContent(),'Spectral CNN P(good)=—');
  await page.locator('#first').click();await target(1001);await values('87.7%','1.23');
  refitted=true;await page.locator('#refit').click();
  await page.waitForFunction(()=>document.querySelector('#header-chi2')?.textContent==='χ²ᵣ=0.80');
  await values('87.7%','0.80');
  await page.locator('#last').click();
  await page.waitForFunction(()=>document.querySelector('#errors').textContent.includes('outdated response'));
  assert.equal(await page.locator('#plot').evaluate(el=>el.data?.length||0),0);
  assert.deepEqual(errors,[]);
  console.log('Passed: header percentages, zero/missing values, chi-squared fallback, navigation and refit.');
}finally{await page.waitForLoadState('networkidle');await page.unrouteAll({behavior:"wait"});await browser.close();}
