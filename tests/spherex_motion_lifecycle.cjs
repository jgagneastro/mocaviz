// Deterministic navigation, retry and preload checks without database or network access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = name => fs.readFileSync(path.join(root, 'mocaviz/static/', name), 'utf8');
const target = id => ({read_only:true, lane:'sublimeaperture', object:{moca_oid:id, moca_specid:id, ra:id, dec:20}});
const objects = (first, last) => Array.from({length:last - first + 1}, (_, index) => target(first + index).object);
const url = frame => new URL(frame.src);
const token = frame => url(frame).searchParams.get('frame');
const coordinate = frame => Number(new URLSearchParams(url(frame).hash.slice(1)).get('ra'));
const BACKGROUND = 'preload';
const FRAME_OVERHEAD = 16 * 1024 ** 2;

function fixture(preload = false) {
  const events = {}, elements = new Map(), timers = new Map(), frames = [];
  let clock = 0, serial = 0;
  function setTimeout(fn, delay) {
    const id = ++serial;
    timers.set(id, {fn, time: clock + delay});
    return id;
  }
  function advance(ms) {
    const end = clock + ms;
    while (true) {
      const entry = [...timers].filter(([, t]) => t.time <= end).sort((a,b) => a[1].time - b[1].time)[0];
      if (!entry) break;
      clock = entry[1].time;
      timers.delete(entry[0]);
      entry[1].fn();
    }
    clock = end;
  }
  function element(id) {
    const messages = [];
    return {id, hidden:true, disabled:false, checked:true, value:'', textContent:'', messages,
      contentWindow:{postMessage(message) { messages.push(message); }},
      removeAttribute(name) { delete this[name]; },
      addEventListener() {},
      replaceChildren() {},
      cloneNode() { return element(id); },
      append(node) { frames.push(node); },
      remove() { this.removed = true; }};
  }
  const get = id => {
    if (id === 'motion-frame' && frames.length)
      return frames.find(frame => frame.id === id && !frame.removed);
    if (!elements.has(id)) elements.set(id, element(id));
    return elements.get(id);
  };
  const document = {getElementById:get, addEventListener() {}};
  const window = {addEventListener(name, fn) { events[name] = fn; }};
  vm.runInNewContext(source('spherex_motion.js'), {
    window, document, URL, URLSearchParams, setTimeout, clearTimeout:id => timers.delete(id), Option:function() {},
  });
  const view = window.SpherexMotionReview.create({
    api:() => { throw Error('Unexpected API call'); }, writable:() => false, base:'http://localhost/', demo:false, preload,
  });
  const ready = (frame, {id = token(frame), pixelBytes = 3_000_000, origin = 'null'} = {}) =>
    events.message({source:frame.contentWindow, origin, data:{kind:'spherex-motion-cutout', frame:id, state:'ready', pixelBytes}});
  return {view, get, advance, ready, frames};
}

function checkCurrentLifecycle() {
  const {view, get, advance, ready, frames} = fixture();
  view.show(target(1)); advance(100); view.show(target(2)); advance(100); view.show(target(3)); advance(299);
  assert.equal(frames.length, 0, 'No requests during rapid navigation');
  advance(1);
  const old = get('motion-frame');
  const params = new URLSearchParams(url(old).hash.slice(1));
  assert.deepEqual(['ra','size','zoom','speed','window','band'].map(k => params.get(k)), ['3','30','40','500','5','3']);
  view.show(target(4), objects(5, 8)); advance(300);
  let frame = get('motion-frame');
  ready(old);
  ready(frame, {id:token(old)});
  ready(frame, {origin:'http://localhost'});
  assert.equal(get('motion-status').textContent, 'Loading WiseView cutout…');
  advance(30000);
  assert.equal(frames.length, 3, 'One retry for current target');
  advance(30000);
  assert.match(get('motion-status').textContent, /taking longer/);
  advance(60000);
  assert.equal(frames.length, 3, 'Retries stay bounded');
  get('motion-reload').onclick();
  frame = get('motion-frame');
  ready(frame);
  assert.equal(get('motion-status').textContent, 'WiseView loaded.');
  advance(60000);
  assert.equal(frames.length, 4, 'The standard web reviewer still loads only the current panel');
  view.show(target(5));
  get('motion-autoload').checked = false;
  get('motion-autoload').onchange();
  advance(60000);
  assert.equal(frames.length, 4, 'Autoload off cancels scheduled loads');
  get('motion-autoload').checked = true;
  get('motion-autoload').onchange();
  assert.equal(frames.length, 5);
  view.close();
  advance(60000);
  assert.equal(frames.length, 5, 'Closing cancels retries');
}

function checkSequentialLoading() {
  const {view, get, advance, ready, frames} = fixture(true);
  view.show(target(1), objects(2, 6));
  advance(300);
  assert.equal(frames.length, 1, 'Preloading waits for the current cutout');
  ready(frames[0]);
  assert.equal(frames.length, 2);
  assert.equal(coordinate(frames[1]), 2);
  assert.equal(url(frames[1]).searchParams.get(BACKGROUND), '1');
  assert.equal(frames[1].hidden, true);
  ready(frames[0]);
  assert.equal(frames.length, 2, 'Stay at one background load until it is ready');

  view.clear(objects(2, 6));
  view.show(target(2), objects(3, 6));
  assert.equal(get('motion-frame'), frames[1], 'Adopt an in-flight cutout without reloading');
  assert.equal(frames.length, 2);
  assert.equal(frames[1].messages.at(-1).kind, 'spherex-motion-activate');
  ready(frames[1]);
  assert.equal(coordinate(frames[2]), 3);
  ready(frames[2]);
  assert.equal(coordinate(frames[3]), 4);
  view.clear(objects(3, 6));
  view.show(target(3), objects(4, 6));
  assert.equal(get('motion-frame'), frames[2], 'Reveal the already loaded frame');
  assert.equal(get('motion-status').textContent, 'WiseView loaded.');
  advance(30000);
  assert.ok(frames[3].removed, 'A stuck background load is released');
  assert.equal(coordinate(frames[4]), 5, 'A background timeout does not stall remaining targets');

  view.clear(objects(90, 92));
  view.show(target(90), objects(91, 92));
  ready(frames[4]);
  assert.ok(frames.slice(0, 5).every(frame => frame.removed), 'Changing queues releases old cutouts');
  advance(300);
  assert.equal(coordinate(get('motion-frame')), 90);
  ready(frames[5]);
  get('motion-autoload').checked = false;
  get('motion-autoload').onchange();
  assert.ok(frames.every(frame => frame.removed));
  advance(60000);
  assert.equal(frames.length, 7, 'Turning autoload off clears the cache and stops background loading');
}

function checkCaps() {
  const count = fixture(true);
  count.view.show(target(1), objects(2, 80));
  count.advance(300);
  for (let i = 0; i <= 50; i++) count.ready(count.frames[i], {pixelBytes:1_000_000});
  assert.equal(count.frames.length, 51, 'At most 50 cached targets plus the visible target');
  count.view.clear(objects(2, 80)); count.view.show(target(2), objects(3, 80));
  assert.equal(count.frames.length, 52, 'Preloading refills the freed slot');
  assert.equal(coordinate(count.frames.at(-1)), 52);
  count.view.close();
  assert.ok(count.frames.every(frame => frame.removed));

  const memory = fixture(true);
  memory.view.show(target(1), objects(2, 12));
  memory.advance(300);
  memory.ready(memory.frames[0]);
  // The third prospective cached target would push retained bytes over 1 GB.
  const threeHundredFiftyMB = 350_000_000 - FRAME_OVERHEAD;
  memory.ready(memory.frames[1], {pixelBytes:threeHundredFiftyMB});
  memory.ready(memory.frames[2], {pixelBytes:threeHundredFiftyMB});
  memory.ready(memory.frames[3], {pixelBytes:threeHundredFiftyMB});
  assert.ok(memory.frames[3].removed);
  assert.equal(memory.frames.length, 4, 'Stop filling at the memory cap even with count slots available');
  memory.view.clear(objects(2, 12)); memory.view.show(target(2), objects(3, 12));
  assert.equal(coordinate(memory.frames.at(-1)), 4, 'Resume the ordered list once memory is available');
  assert.ok(!memory.frames.at(-1).removed);
}

async function checkBridge() {
  let poll, receive, resumed = 0;
  const cleared = [], settings = [], messages = [], parent = {postMessage:message => messages.push(message)};
  const window = {parent, addEventListener(name, handler) { if (name === 'message') receive = handler; },
    WiseSwapper:function() {
      this.images = []; this.interval = 9; this.overlay_scale = 10;
      this.zoom_input = {slider:(...args) => settings.push(args)};
      this.updateSpeed = () => { resumed++; };
      this.frame = () => {};
    }};
  vm.runInNewContext(source('spherex_motion_frame.js'), {
    window, URLSearchParams, location:{search:'?frame=motion-7&preload=1'},
    setInterval:fn => { poll = fn; return 1; }, clearInterval:id => cleared.push(id),
  });
  const swapper = new window.WiseSwapper();
  assert.deepEqual(settings, [['option','max',40]]);
  await poll();
  assert.equal(messages.length, 0);
  let finish;
  swapper.images = [{complete:true, naturalWidth:11, naturalHeight:13, decode:() => new Promise(resolve => { finish = resolve; })}];
  const decoding = poll();
  assert.equal(messages.length, 0, 'Readiness waits for decoding');
  finish();
  await decoding;
  assert.deepEqual(cleared, [1,9]);
  assert.equal(messages[0].frame, 'motion-7');
  assert.equal(messages[0].state, 'ready');
  assert.equal(messages[0].pixelBytes, 8 * (143 + 143 + 4 * 14300));
  const activate = {kind:'spherex-motion-activate', frame:'motion-7'};
  receive({source:{}, data:activate});
  assert.equal(resumed, 0);
  receive({source:parent, data:activate});
  assert.equal(resumed, 1);
}

function checkUnassignedCandidates() {
  const {view, get, advance, ready} = fixture();
  const candidate = id => ({lane:'moshpit',read_only:false,
    object:{candidate_id:id,moca_oid:null,moca_specid:null,ra:100+id,dec:20}});
  view.show(candidate(1)); advance(300);
  const first = get('motion-frame');
  ready(first);
  view.show(candidate(2)); advance(300);
  const next = get('motion-frame');
  assert.equal(coordinate(first),101);
  assert.equal(coordinate(next),102);
  assert.notEqual(token(first),token(next));
  ready(first);
  assert.equal(get('motion-status').textContent,'Loading WiseView cutout…');
  ready(next);
  assert.equal(get('motion-status').textContent,'WiseView loaded.');
  assert.equal(get('motion-save').disabled,true);
}

async function checkQueuedCoordinates() {
  const {view, advance, ready, frames} = fixture(true);
  const pending = [];
  const lookup = candidate => new Promise(resolve => { pending.push(() => resolve(target(candidate.moca_oid).object)); });
  view.show(target(1), [{moca_oid:2, moca_specid:2}], lookup);
  advance(300);
  ready(frames[0]);
  assert.equal(pending.length, 1, 'Coordinates come from the existing prefetched spectral fit');
  view.clear();
  view.show(target(10), objects(11, 11));
  pending.shift()();
  await Promise.resolve();
  assert.equal(frames.length, 1, 'A late fit lookup cannot start a stale cutout');
  advance(300);
  ready(frames[1]);
  assert.equal(coordinate(frames[2]), 11);
}

(async () => {
  checkCurrentLifecycle();
  checkUnassignedCandidates();
  checkSequentialLoading();
  checkCaps();
  await checkBridge();
  await checkQueuedCoordinates();
  console.log('Passed WiseView navigation, readiness, sequential reuse, cache limits, cancellation and overlay budgeting.');
})().catch(error => { console.error(error); process.exitCode = 1; });
