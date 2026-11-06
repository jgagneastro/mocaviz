// Gate synthetic fits to check request ordering, reuse and cancellation; no DB access.
import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const origin = process.argv[2] || 'http://127.0.0.1:8061';
const browser = await chromium.launch({headless: true});
const page = await browser.newPage();
const fits = [], errors = [];
let queueSize = 30, active = 0, maxActive = 0, closing = false;
page.on('pageerror', e => errors.push(e.message));
await page.route('**/api/spherex-review/*', async route => {
  const body = route.request().postDataJSON();
  const op = new URL(route.request().url()).pathname.split('/').at(-1);
  assert(['context', 'queue', 'queue-count', 'analyze'].includes(op), 'Unexpected database write');
  const fulfill = (payload, status = 200) => route.fulfill({status, contentType: 'application/json',
    body: JSON.stringify({ok: status === 200, ...payload})});
  if (op === 'queue') return fulfill({queue_filter_version: 7,
    items: Array.from({length: queueSize}, (_, i) => ({moca_oid: 1001 + i,
      moca_specid: 11001 + i, designation: 'Synthetic ' + (1001 + i)})),
    has_more: false, next_after: null});
  if (op === 'queue-count') return fulfill({total: queueSize});
  let fit;
  if (op === 'analyze') {
    active++; maxActive = Math.max(maxActive, active);
    fit = {body, done: false};
    const gate = new Promise(resolve => { fit.release = resolve; });
    fits.push(fit);
    const outcome = closing ? 'ok' : await gate;
    if (outcome === 'fail') {
      active--; fit.done = true;
      return fulfill({error: 'Synthetic missing spectrum'}, 404);
    }
  }
  try {
    const response = await route.fetch({postData: JSON.stringify({...body, mock: true})});
    const payload = await response.json();
    if (fit) { active--; fit.done = true; }
    return await fulfill(payload);
  } catch (e) { if (!closing) throw e; }
});
async function until(check, label) {
  const end = Date.now() + 15000;
  while (!check() && Date.now() < end) await new Promise(resolve => setTimeout(resolve, 20));
  assert(check(), label);
}
async function nextFit(oid, start = 0) {
  await until(() => fits.slice(start).some(f => f.body.moca_oid === oid), 'No fit for ' + oid);
  return fits.slice(start).find(f => f.body.moca_oid === oid);
}
async function target(oid) {
  await page.waitForFunction(oid => document.querySelector('#object-title').textContent.includes(String(oid)) &&
    !document.querySelector('#report').disabled, oid);
}
async function finish(fit, outcome = 'ok') {
  fit.release(outcome);
  await until(() => fit.done, 'Fit did not finish');
}
try {
  await page.goto(origin + '/spherex-autotype?mock=1');
  await page.waitForFunction(() => !document.querySelector('#load').disabled);
  assert.equal(fits.length, 0, 'Opening the page must not start fitting');
  await page.locator('#load').click();
  const first = await nextFit(1001);
  assert.equal(fits.length, 1, 'Look-ahead must wait for the displayed fit');
  await finish(first); await target(1001);
  for (let oid = 1002; oid <= 1011; oid++) await finish(await nextFit(oid));
  await page.waitForLoadState('networkidle');
  assert.deepEqual(fits.map(f => f.body.moca_oid), Array.from({length: 11}, (_, i) => 1001 + i));
  assert.equal(maxActive, 1, 'Fits must run sequentially');

  // Keep a background fit running while rapidly navigating through the ten cached results.
  await page.locator('#next').click(); await target(1002);
  const twelfth = await nextFit(1012);
  for (let oid = 1003; oid <= 1011; oid++) {
    await page.keyboard.press('ArrowRight'); await target(oid);
  }
  assert.equal(fits.length, 12, 'Cached navigation must not refit or overlap the running fit');
  await finish(twelfth);
  const thirteenth = await nextFit(1013);
  await page.keyboard.press('End');
  await page.waitForFunction(() => document.querySelector('#object-title').textContent.includes('1030'));
  assert.equal(fits.length, 13);
  await finish(thirteenth);
  await finish(await nextFit(1030)); await target(1030);
  await page.waitForLoadState('networkidle');
  assert.deepEqual(fits.slice(12).map(f => f.body.moca_oid), [1013, 1030],
    'A jump must discard obsolete look-ahead and prioritize the displayed object');

  // Refitting invalidates results/options and queues the selected target after any running fit.
  queueSize = 4;
  let start = fits.length;
  await page.locator('#load').click(); await finish(await nextFit(1001, start)); await target(1001);
  const oldBackground = await nextFit(1002, start);
  await page.locator('#drop').fill('7');
  await page.locator('#refit').click();
  await finish(oldBackground);
  const refit = await nextFit(1001, start + 2);
  assert.equal(refit.body.options.drop_worst_n, 7);
  await finish(refit); await target(1001);
  for (const oid of [1002, 1003, 1004]) {
    const fit = await nextFit(oid, start + 2);
    assert.equal(fit.body.options.drop_worst_n, 7);
    await finish(fit);
  }
  await page.waitForLoadState('networkidle');

  // A failed speculative fit does not stall the queue, and navigation retries it.
  start = fits.length;
  await page.locator('#load').click(); await finish(await nextFit(1001, start)); await target(1001);
  await finish(await nextFit(1002, start), 'fail');
  await finish(await nextFit(1003, start)); await finish(await nextFit(1004, start));
  await page.waitForLoadState('networkidle');
  assert(await page.locator('#errors').isHidden(), 'Speculative errors must not replace the displayed result');
  await page.locator('#next').click();
  await finish(await nextFit(1002, start + 4)); await target(1002);
  await page.waitForLoadState('networkidle');

  // Reload while a background fit is running: only the new lane/options survive.
  start = fits.length;
  await page.locator('#load').click(); await finish(await nextFit(1001, start)); await target(1001);
  const previousLane = await nextFit(1002, start);
  await page.locator('#lane').selectOption('spiff');
  await page.locator('#load').click();
  await finish(previousLane);
  for (const oid of [1001, 1002, 1003, 1004]) {
    const fit = await nextFit(oid, start + 2);
    assert.equal(fit.body.lane, 'spiff'); await finish(fit);
  }
  await target(1001); await page.waitForLoadState('networkidle');

  // Quit clears queued fits while allowing no additional speculative requests.
  start = fits.length;
  await page.locator('#load').click(); await finish(await nextFit(1001, start)); await target(1001);
  const last = await nextFit(1002, start);
  await page.locator('#quit').click();
  closing = true; last.release('ok');
  await page.waitForLoadState('networkidle');
  assert.equal(fits.length, start + 2);
  assert.equal(await page.locator('#object-title').textContent(), 'Review session closed');
  assert.equal(maxActive, 1); assert.deepEqual(errors, []);
  console.log('Passed: sequential ten-object look-ahead, cached rapid navigation, jump priority, refit/options, failed-fit retry, lane reload and quit; no database writes.');
} finally {
  closing = true;
  for (const fit of fits) fit.release('ok');
  await page.unrouteAll({behavior: 'wait'}); await browser.close();
}
