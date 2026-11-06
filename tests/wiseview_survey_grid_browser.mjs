// Deliberately complete synthetic finder requests out of order; no API or network reads.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {fileURLToPath} from 'node:url';
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:900,height:700}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.setContent('<div id="panel" style="display:grid;grid-template-columns:220px 220px;gap:6px;font:12px sans-serif"></div>');
  await page.addScriptTag({path:fileURLToPath(new URL('../mocaviz/wiseview_review/survey_images.js',import.meta.url))});
  await page.evaluate(()=>{
    const pending=Array.from({length:7},()=>{
      const job={};job.promise=new Promise(resolve=>{job.resolve=resolve;});return job;
    });
    function card(label,image=false,unavailable=false,order=0){
      const card=document.createElement('div');card.dataset.label=label;card.style.order=String(order);
      const title=document.createElement('div');title.textContent=label;card.append(title);
      if(image){const canvas=document.createElement('canvas');canvas.width=200;canvas.height=120;card.append(canvas);}
      else{const message=document.createElement('div');message.textContent='No coverage';message.style.minHeight='120px';card.append(message);}
      if(unavailable)card.dataset.surveyState='unavailable';return card;
    }
    const labels=['A','DES DR2 IRG','C','No coverage','Metadata','PS1 DR2 IZY','PS1 DR2 IRG'];
    const panel=document.querySelector('#panel');
    window.fixture={pending,card,labels,panel};
    window.finished=SurveyImages.render(panel,pending.map(job=>job.promise),{labels});
  });
  const ready=()=>page.locator('#panel > [data-survey-state=ready]').evaluateAll(cards=>cards.map(card=>card.dataset.label));
  assert.equal(await page.locator('[data-survey-state=loading]').count(),7);
  await page.evaluate(()=>fixture.pending[2].resolve(fixture.card('C',true)));
  await page.waitForFunction(()=>document.querySelectorAll('[data-survey-state=ready]').length===1);
  assert.deepEqual(await ready(),['C']);
  await page.evaluate(()=>{
    fixture.pending[3].resolve(fixture.card('No coverage',false,true));
    fixture.pending[1].resolve(fixture.card('DES DR2 IRG',true,false,1));
    fixture.pending[0].resolve(fixture.card('A',true));
    fixture.pending[4].resolve(fixture.card('Metadata'));
  });
  await page.evaluate(()=>fixture.pending[6].resolve(fixture.card('PS1 DR2 IRG',true)));
  await page.waitForFunction(()=>document.querySelectorAll('[data-survey-state=ready]').length===4);
  assert.deepEqual(await ready(),['PS1 DR2 IRG','A','C','DES DR2 IRG']);
  await page.evaluate(()=>fixture.pending[5].resolve(fixture.card('PS1 DR2 IZY',true)));
  await page.evaluate(()=>window.finished);
  assert.deepEqual(await ready(),['PS1 DR2 IZY','PS1 DR2 IRG','A','C','DES DR2 IRG']);
  assert.equal(await page.locator('[data-survey-state=loading]').count(),1);
  assert.match(await page.locator('[data-survey-state=loading]').innerText(),/Metadata.*Loading/);
  const geometry=await page.evaluate(()=>{
    const box=selector=>{const rect=document.querySelector(selector).getBoundingClientRect();return {top:rect.top,bottom:rect.bottom,height:rect.height};};
    return {last:box('[data-label="DES DR2 IRG"]'),loading:box('[data-survey-state=loading]'),missing:box('[data-survey-state=unavailable]')};
  });
  assert(geometry.last.bottom<=geometry.loading.top);
  assert(geometry.loading.bottom<=geometry.missing.top);
  assert(geometry.loading.height<25&&geometry.missing.height<25,'Status lines must not reserve image squares');
  await page.evaluate(()=>SurveyImages.render(fixture.panel,fixture.pending.map(job=>job.promise),{labels:fixture.labels,final:true}));
  assert.equal(await page.locator('[data-survey-state=loading]').count(),0);
  assert.equal(await page.locator('[data-survey-state=unavailable]').count(),2);
  assert.deepEqual(await ready(),['PS1 DR2 IZY','PS1 DR2 IRG','A','C','DES DR2 IRG']);
  await page.evaluate(async()=>{
    let release;
    const old=new Promise(resolve=>{release=resolve;});
    const previous=SurveyImages.render(fixture.panel,[old],{labels:['Obsolete']});
    await SurveyImages.render(fixture.panel,[Promise.resolve(fixture.card('Fresh',true))],{labels:['Fresh']});
    release(fixture.card('Obsolete',true));await previous;
  });
  assert.deepEqual(await ready(),['Fresh']);
  await page.evaluate(()=>SurveyImages.render(fixture.panel,[Promise.reject(new Error('Offline'))],{labels:['Failed request']}));
  assert.match(await page.locator('[data-survey-state=unavailable]').innerText(),/Failed request.*Offline/);
  await page.evaluate(async()=>{
    const link=document.createElement('a');link.id='pawnstarsLink';
    const holder=document.createElement('div');holder.id='pawnstars';link.append(holder);
    const image=new Image();image.src='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="60" height="60"/>';
    await image.decode();holder.append(image);fixture.panel.before(link);
    await SurveyImages.render(fixture.panel,[Promise.resolve(fixture.card('A',true))],{labels:['A']});
  });
  let positions=await page.evaluate(()=>[...fixture.panel.children].map(node=>node.id||node.dataset.label));
  assert.deepEqual(positions,['pawnstarsLink','A']);
  await page.evaluate(()=>{
    const image=document.querySelector('#pawnstars img');image.dataset.wiseviewFallbackCutout='1';image.alt='DES DR2 ColorIRG epoch coadd';
  });
  await page.waitForFunction(()=>document.querySelector('#panel').firstElementChild.dataset.label==='A');
  await page.evaluate(()=>{
    window.__wiseviewVettingPs1FallbackState={failed:true};document.querySelector('#pawnstars').textContent='No cutout found';
  });
  await page.waitForFunction(()=>document.querySelector('#pawnstarsLink').hidden);
  assert.equal(await page.locator('[data-survey-status-group=unavailable]').count(),1);
  assert.deepEqual(errors,[]);
  console.log('Finder grid: stable successful order, compact loading/unavailable rows, metadata completion and stale-result isolation passed.');
} finally {await browser.close();}
