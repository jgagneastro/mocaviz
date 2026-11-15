// Read-only captured fixture + real anonymous WiseView request. No database writes.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {chromium} from 'playwright';
const [origin, fixturePath, screenshot='/tmp/spherex_motion_feature/integrated_wiseview.png']=process.argv.slice(2);
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
 await page.waitForFunction(()=>document.querySelector('#motion-status').textContent==='WiseView loaded.',{},{timeout:70000});
 await page.locator('#motion-panel').scrollIntoViewIfNeeded();
 const src=await page.locator('#motion-frame').getAttribute('src');
 const params=new URLSearchParams(new URL(src).hash.slice(1));
 assert.equal(params.get('size'),'30');assert.equal(params.get('zoom'),'40');
 const handle=await page.locator('#motion-frame').elementHandle();const frame=await handle.contentFrame();
 assert.equal(await frame.locator('#zoomValue').textContent(),'40.0');
 await frame.waitForFunction(()=>window.__targetCrosshairSwapper?.window_mjds?.length>1,{},{timeout:55000});
 await frame.waitForFunction(()=>{const c=document.querySelector('#daCanvas'); if(!c||c.width<2||c.height<2)return false; try {const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data; return p.some((v,i)=>i%4!==3&&v>10);} catch(error) {return error.name==='SecurityError';}},{},{timeout:55000});
 await frame.waitForFunction(()=>{const c=document.querySelector('#wiseview-vetting-crosshair');return c&&c.style.display!=='none'&&parseFloat(c.style.left)>40;},{},{timeout:10000});
 assert.equal(await page.locator('#motion-frame').getAttribute('sandbox'),'allow-scripts');
 await page.locator('#motion-panel').screenshot({path:screenshot});
 assert.deepEqual(errors,[]);console.log('Real WiseView images, target crosshair, 30 arcsec view and zoom 40 verified in sandboxed spectral panel.');
}finally{await page.unrouteAll({behavior:'ignoreErrors'});await browser.close();}
