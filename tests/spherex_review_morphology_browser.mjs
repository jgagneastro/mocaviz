// Queue transport and rendered morphology flags; all write endpoints forbidden.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.argv[2]||'http://127.0.0.1:8077';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1100}});
const requests=[],errors=[];
page.on('pageerror',error=>errors.push(error.message));
const statuses={1001:'pass',1002:'fail',1003:'undefined'};
await page.route('**/api/spherex-review/*',async route=>{
 const op=new URL(route.request().url()).pathname.split('/').at(-1);
 const body=route.request().postDataJSON();requests.push({op,body});
 assert(['context','queue','queue-count','analyze'].includes(op),'No write endpoint allowed');
 const response=await route.fetch({postData:JSON.stringify({...body,mock:true})});
 const data=await response.json();
 const mode=body.sublime3c_psf_morphology||'all';
 const selected=Object.keys(statuses).map(Number).filter(oid=>mode==='all'||(mode==='not_pass'?statuses[oid]!=='pass':statuses[oid]===mode));
 if(op==='queue'&&!body.moca_specid){
  data.items=selected.map(oid=>({moca_oid:oid,moca_specid:oid+10000}));data.has_more=false;data.next_after=null;
 }
 if(op==='queue-count')data.total=selected.length;
 if(op==='analyze'){
  const oid=data.object.moca_oid,status=statuses[oid];
  data.object.sublime3c_morphology={status,candidate_id:oid,scope:'This native cube detection',
   bands:{deep:{status:status==='undefined'?'undetermined':status,reason:status==='fail'?'elongated|non_psf_residual':status==='undefined'?'low_snr_or_unconverged':'point_source'}}};
 }
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
});
try{
 await page.goto(origin+'/spherex-review?mock=1&review_sample=sublime3c&min_current_fit_sptn=&min_current_fit_gap=&sublime3c_psf_morphology=pass');
 await page.waitForFunction(()=>!document.querySelector('#load').disabled);
 assert.equal(await page.locator('#sublime3c-psf-morphology').inputValue(),'pass');
 for(const [mode,title,count] of [['pass','passing',1],['fail','poor',1],['undefined','undefined',1],['not_pass','poor',2],['all','passing',3]]){
  await page.locator('#sublime3c-psf-morphology').selectOption(mode);
  await page.locator('#load').click();
  await page.waitForFunction(([title,count])=>document.querySelector('#header-psf-morphology')?.textContent==='PSF morphology: '+title&&document.querySelector('#queue-total').textContent===count+' total matches at load',[title,count]);
  assert.equal(requests.filter(r=>r.op==='queue').at(-1).body.sublime3c_psf_morphology,mode);
  assert.equal(requests.filter(r=>r.op==='queue-count').at(-1).body.sublime3c_psf_morphology,mode);
  if(mode==='fail'){
   assert.match(await page.locator('#header-psf-morphology').getAttribute('title'),/elongated, non psf residual/);
   await page.screenshot({path:'/tmp/s3c-psf-poor-reviewer.png',fullPage:false});
  }
 }
 await page.locator('#review-sample').selectOption('all');
 assert(await page.locator('#sublime3c-selection-controls').isHidden());
 await page.locator('#load').click();await page.waitForFunction(()=>!document.querySelector('#load').disabled);
 assert.equal(requests.filter(r=>r.op==='queue').at(-1).body.sublime3c_psf_morphology,'all');
 assert.deepEqual(errors,[]);
 console.log('Passed: all five morphology modes, matching counts and requests, URL setting, header flags and reasons, non-S3C isolation; no database writes.');
}finally{await page.unrouteAll({behavior:'wait'});await browser.close();}
