// Read-only captured fixture + real anonymous WiseView request. No database writes.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {chromium} from 'playwright';
const [origin, fixturePath]=process.argv.slice(2);
const fixture=JSON.parse(fs.readFileSync(fixturePath,'utf8'));
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1600,height:1100}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/spherex-review/*',async route=>{
 const op=new URL(route.request().url()).pathname.split('/').at(-1);
 assert(['context','queue','queue-count','analyze','motion-context'].includes(op),'Unexpected write');
 let payload;
 if(op==='analyze')payload=fixture.analysis;
 else if(op==='motion-context')payload=fixture.motion;
 else{
  const r=await route.fetch({postData:JSON.stringify({...route.request().postDataJSON(),mock:true})});payload=await r.json();
  if(op==='queue')payload={...payload,items:[fixture.analysis.object],has_more:false,next_after:null};
 }
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(payload)});
});
try{
 await page.goto(origin+'/spherex-review',{waitUntil:'domcontentloaded'});
 await page.locator('#load').click();
 await page.waitForFunction(()=>document.querySelector('#motion-stored').textContent.includes('Stored motion: 6'));
 await page.locator('#motion-panel').scrollIntoViewIfNeeded();
 const handle=await page.locator('#motion-frame').elementHandle();const frame=await handle.contentFrame();
 await frame.waitForFunction(()=>window.__targetCrosshairSwapper?.window_mjds?.length>1,{},{timeout:55000});
 await frame.waitForFunction(()=>{const c=document.querySelector('#daCanvas'); if(!c||c.width<20||c.height<20)return false; try {const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data; return p.some((v,i)=>i%4!==3&&v>10);} catch(error) {return error.name==='SecurityError';}},{},{timeout:55000});
 await frame.waitForFunction(()=>{const c=document.querySelector('#wiseview-vetting-crosshair');return c&&c.style.display!=='none'&&parseFloat(c.style.left)>40;},{},{timeout:10000});
 assert.equal(await page.locator('#motion-frame').getAttribute('sandbox'),'allow-scripts');
 await page.locator('#motion-panel').screenshot({path:'/tmp/spherex_motion_feature/integrated_wiseview.png'});
 assert.deepEqual(errors,[]);console.log('Real WiseView epochs, target crosshair and stored motion score verified in sandboxed spectral panel.');
}finally{await page.unrouteAll({behavior:'ignoreErrors'});await browser.close();}
