// Exercise tab-local sizing and sandboxed WiseView controls without API requests.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const asset=name=>fileURLToPath(new URL('../mocaviz/wiseview_review/'+name,import.meta.url));
const browser=await chromium.launch({headless:true});
try {
  const page=await browser.newPage({viewport:{width:1450,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.setContent(`<div class="review-grid" style="width:1000px"><section class="panel motion"><button id="toggle-wise-controls">Hide WiseView controls [V]</button><div id="wise-pool"></div></section><section class="panel science"><div class="panel-head">SPHEREx spectrum</div><div id="plot"><div id="graph"></div></div><div id="spectrum-resize" role="separator" tabindex="0">Resize spectrum ↘</div></section></div>`);
  await page.addStyleTag({path:asset('style.css')});
  await page.evaluate(()=>{
    const graph=document.querySelector('#graph');graph._fullLayout={width:350,height:260};
    window.relayouts=0;window.Plotly={relayout(graph,size){graph._fullLayout={...size};graph.style.width=size.width+'px';graph.style.height=size.height+'px';window.relayouts++;}};
  });
  await page.addScriptTag({path:asset('review_layout.js')});
  const frameSource='<style>#nav-left{display:block;width:250px}#image-field{margin-left:280px}</style><div id="nav-left">RA, Dec, sliding window</div><div id="image-field">WiseView</div><script>'+fs.readFileSync(asset('wiseview_controls.js'),'utf8')+'</script>';
  await page.evaluate(source=>{const frame=document.createElement('iframe');frame.srcdoc=source;document.querySelector('#wise-pool').append(frame);},frameSource);
  const frame=page.frameLocator('#wise-pool iframe').first();
  await frame.locator('#nav-left').waitFor();
  await page.locator('#toggle-wise-controls').click();
  await frame.locator('#nav-left').waitFor({state:'hidden'});
  assert.equal(await frame.locator('#image-field').evaluate(el=>getComputedStyle(el).marginLeft),'8px');
  assert.equal(await page.locator('#toggle-wise-controls').getAttribute('aria-pressed'),'true');
  await page.evaluate(source=>{const frame=document.createElement('iframe');frame.srcdoc=source;document.querySelector('#wise-pool').append(frame);},frameSource);
  await page.frameLocator('#wise-pool iframe').nth(1).locator('body.wise-controls-hidden').waitFor();
  await page.locator('body').click({position:{x:1200,y:950}});await page.keyboard.press('v');
  await frame.locator('#nav-left').waitFor({state:'visible'});
  const before=await page.locator('.science').boundingBox();
  const handle=page.locator('#spectrum-resize');await handle.focus();
  await page.keyboard.press('ArrowDown');await page.keyboard.press('ArrowRight');
  await page.waitForFunction(()=>window.relayouts>0);
  const sized=await page.locator('.science').boundingBox();
  assert(sized.height>=Math.max(280,before.height+40));assert(sized.width>before.width);
  const grip=await handle.boundingBox();await page.mouse.move(grip.x+grip.width/2,grip.y+grip.height/2);
  await page.mouse.down();await page.mouse.move(grip.x+grip.width/2+20,grip.y+grip.height/2+80);await page.mouse.up();
  const dragged=await page.locator('.science').boundingBox();assert(dragged.height>=sized.height+75);
  await page.evaluate(()=>{
    const graph=document.createElement('div');graph._fullLayout={width:1,height:1};document.querySelector('#plot').replaceChildren(graph);
  });
  await page.waitForFunction(()=>document.querySelector('#plot').firstElementChild._fullLayout.height>100);
  assert.deepEqual(errors,[]);
  console.log('WiseView layout: sidebar toggle, V shortcut, preloaded-frame preference, keyboard/drag spectrum resizing and new-plot sizing passed.');
} finally {await browser.close();}
