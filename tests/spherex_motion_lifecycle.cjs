// Deterministic navigation/retry checks; no browser, network or database writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const events = {}, elements = new Map(), timers = new Map();
let clock = 0, serial = 0, frames = 0;
const schedule = (fn, delay) => {const id=++serial;timers.set(id,{fn,time:clock+delay});return id;};
function advance(ms) {
 const end=clock+ms;
 while (true) {
  const entry=[...timers].filter(([,t])=>t.time<=end).sort((a,b)=>a[1].time-b[1].time)[0];
  if (!entry) break;
  clock=entry[1].time;timers.delete(entry[0]);entry[1].fn();
 }
 clock=end;
}
function element(id) {
 const e={id,hidden:false,disabled:false,checked:true,value:'',textContent:'',attrs:{},contentWindow:{postMessage(){}},
  removeAttribute(k){delete this.attrs[k];},addEventListener(){},replaceChildren(){},
  cloneNode(){frames++;return element(id);},replaceWith(next){elements.set(id,next);}};
 Object.defineProperty(e,'src',{get(){return this.attrs.src;},set(value){this.attrs.src=value;}});
 return e;
}
const document={getElementById(id){if(!elements.has(id))elements.set(id,element(id));return elements.get(id);},addEventListener(){}};
const window={addEventListener(name,fn){events[name]=fn;}};
vm.runInNewContext(fs.readFileSync(path.join(root,'mocaviz/static/spherex_motion.js'),'utf8'),{
 window,document,URL,URLSearchParams,setTimeout:schedule,clearTimeout:id=>timers.delete(id),Option:function(){}});
const view=window.SpherexMotionReview.create({api:()=>{throw Error('Unexpected API call');},writable:()=>false,base:'http://localhost/',demo:false});
const get=id=>document.getElementById(id);
const target=id=>({read_only:true,lane:'sublimeaperture',object:{moca_oid:id,moca_specid:id,ra:id,dec:20}});
const ready=(frame,token)=>events.message({source:frame.contentWindow,data:{kind:'spherex-motion-cutout',frame:token,state:'ready'}});
const token=frame=>new URL(frame.src).searchParams.get('frame');
view.show(target(1));advance(100);view.show(target(2));advance(100);view.show(target(3));advance(299);
assert.equal(frames,0,'No cutouts requested while rapidly navigating');advance(1);
assert.equal(frames,1);let frame=get('motion-frame');const old=frame,oldToken=token(old);
let p=new URLSearchParams(new URL(frame.src).hash.slice(1));
assert.equal(p.get('ra'),'3');assert.equal(p.get('size'),'30');assert.equal(p.get('zoom'),'40');
assert.equal(p.get('speed'),'500');assert.equal(p.get('window'),'5');assert.equal(p.get('band'),'3');
view.show(target(4));advance(300);frame=get('motion-frame');
ready(old,oldToken);assert.equal(get('motion-status').textContent,'Loading WiseView cutout…');
ready(frame,oldToken);assert.equal(get('motion-status').textContent,'Loading WiseView cutout…');
advance(30000);assert.equal(frames,3,'One retry for current target');frame=get('motion-frame');
advance(30000);assert.match(get('motion-status').textContent,/taking longer/);
advance(60000);assert.equal(frames,3,'Retries stay bounded');
get('motion-reload').onclick();frame=get('motion-frame');ready(frame,token(frame));
assert.equal(get('motion-status').textContent,'WiseView loaded.');advance(60000);assert.equal(frames,4);
view.show(target(5));get('motion-autoload').checked=false;get('motion-autoload').onchange();advance(60000);
assert.equal(frames,4,'Autoload off cancels scheduled loads');
get('motion-autoload').checked=true;get('motion-autoload').onchange();assert.equal(frames,5);
view.close();advance(60000);assert.equal(frames,5,'Closing cancels retries');
// The frame must report actual decoded images, not merely returned metadata.
let poll,settings=[],messages=[];
const inner={parent:{postMessage:m=>messages.push(m)},WiseSwapper:function(){this.images=[];this.zoom_input={slider:(...args)=>settings.push(args)};}};
vm.runInNewContext(fs.readFileSync(path.join(root,'mocaviz/static/spherex_motion_frame.js'),'utf8'),{
 window:inner,URLSearchParams,location:{search:'?frame=motion-7'},setInterval:fn=>{poll=fn;return 1;},clearInterval(){}});
const swapper=new inner.WiseSwapper();assert.deepEqual(settings,[['option','max',40]]);
poll();assert.equal(messages.length,0);
swapper.images=[{complete:false,naturalWidth:0}];poll();assert.equal(messages.length,0);
swapper.images[0]={complete:true,naturalWidth:0};poll();assert.equal(messages.length,0);
swapper.images[0]={complete:true,naturalWidth:11};poll();
assert.equal(messages.length,1);assert.equal(messages[0].frame,'motion-7');assert.equal(messages[0].state,'ready');
console.log('Passed rapid navigation, stale-frame isolation, bounded retry, cancellation, actual-image readiness and zoom range.');
