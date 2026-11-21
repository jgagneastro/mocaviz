// A slow local image response must never relabel the next candidate's field.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const nodes = new Map(), calls = [], timers = new Map(), retired = [];
function element(id) {
  if (!nodes.has(id)) nodes.set(id, {hidden:true, classList:{add(){}, remove(){}},
    removeAttribute(name){delete this[name];}, focus(){},
    replaceChildren(...options){this.options=options;this.value=String(options[0].value);},
    get selectedOptions(){return this.options.filter(o=>String(o.value)===String(this.value));},
    showModal(){this.open=true;}, close(){this.open=false;}});
  return nodes.get(id);
}
const window = {}, document = {getElementById:element,createElement(){return {};},addEventListener(){}};
let serial = 0;
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../mocaviz/static/spherex_moshpit_epochs.js'),'utf8'), {
  window, document, location:{origin:'http://127.0.0.1:8061'}, AbortController,
  setTimeout(fn,delay){timers.set(++serial,{fn,delay});return serial;},clearTimeout(id){timers.delete(id);},
  URL:{createObjectURL(blob){return 'blob:'+blob.field;},revokeObjectURL(url){retired.push(url);}},
  fetch(url,options){return new Promise(resolve=>calls.push({resolve,body:JSON.parse(options.body)}));}
});
const pending = {status:202,json:async()=>({state:'building'})};
const image = field => ({status:200, headers:{get:()=> 'image/png'}, blob:async()=>({field})});
const obj = (id,number)=>({lane:'moshpit',object:{candidate_id:id,designation:'MOSHPIT '+number,ra:21,dec:32}});
async function run() {
  const view=window.MoshpitEpochCharts.create(), tick=()=>new Promise(r=>setImmediate(r));
  view.show(obj(1,9)); view.show(obj(2151,2151));
  assert.deepEqual(calls.map(c=>[c.body.id,c.body.number]),[[1,9],[2151,2151]]);
  calls[0].resolve(image('old')); await tick();
  assert.equal(element('epoch-chart').src,undefined);
  calls[1].resolve(pending); await tick();
  assert.match(element('epoch-status').textContent,/Building/);
  [...timers.values()].find(t=>t.delay===8000).fn();
  calls[2].resolve(image('current')); await tick();
  assert.equal(element('epoch-chart').src,'blob:current');
  element('epoch-enlarge').onclick();assert.equal(element('epoch-dialog').open,true);
  view.show({lane:'spiffstacker',object:{}});
  assert.equal(element('moshpit-epochs').hidden,true);
  assert.equal(element('epoch-chart').src,undefined);
  assert.equal(element('epoch-dialog').open,false);
  assert.deepEqual(retired,['blob:current']);assert.equal(calls.length,3);
  view.show(obj(1,9)); calls[3].resolve(image('candidate9')); await tick();
  element('epoch-references').onclick();
  calls[4].resolve({status:200,json:async()=>[{index:1,designation:'First dwarf',spt:'L0'},{index:2,designation:'Second dwarf',spt:'T8'}]});
  await tick(); assert.equal(calls[5].body.index,1);
  element('epoch-reference-choice').value='2';element('epoch-reference-choice').onchange();
  assert.equal(calls[6].body.index,2);
  calls[5].resolve(image('wrong-reference'));calls[6].resolve(image('reference2'));await tick();
  assert.equal(element('epoch-full').src,'blob:reference2');assert.match(element('epoch-full').alt,/02  Second dwarf/);
  assert.equal(element('epoch-chart').src,'blob:candidate9');
  view.clear();assert(!element('epoch-dialog').open);assert(retired.includes('blob:reference2'));
  console.log('Passed MOSHPIT chart identity, late replies, automatic refresh and lane changes.');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
