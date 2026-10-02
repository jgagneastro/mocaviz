// Stateful browser checks beyond chromium_probe's basic render/navigation checks.
// All API traffic is intercepted or explicitly converted to synthetic demo reads.
import assert from "node:assert/strict";
import { chromium } from "playwright";

const origin = process.argv[2] || "http://127.0.0.1:8079";
const browser = await chromium.launch({headless: true});
const page = await browser.newPage();
const dialogs = [], apiRequests = [], errors = [];
let submitMode = "success", submissions = 0, undos = 0, staleMode = null;
page.on("pageerror", (e) => errors.push(e.message));
page.on("dialog", async (dialog) => { dialogs.push(dialog.message()); await dialog.accept(); });
await page.route("**/api/spherex-review/*", async (route) => {
  const request = route.request(), op = new URL(request.url()).pathname.split("/").at(-1);
  const body = request.postDataJSON();
  apiRequests.push({url: request.url(), headers: request.headers(), op, body});
  const fulfill = (payload, status = 200) => route.fulfill({
    status, contentType: "application/json", body: JSON.stringify({ok: status === 200, ...payload}),
  });
  if (op === "context") {
    const response = await route.fetch({postData: JSON.stringify({mock: true})});
    return fulfill({...await response.json(), role: "management", can_write: true});
  }
  if (op === "queue" && staleMode === "queue")
    return route.fulfill({response: await route.fetch({postData: JSON.stringify({mock: true})})});
  if (op === "queue" && staleMode === "queue-metadata")
    return fulfill({items: [{moca_oid: 1001, moca_specid: body.moca_specid}], has_more: false, next_after: null});
  if (op === "analyze" && staleMode) {
    const response = await route.fetch({postData: JSON.stringify({...body, mock: true})});
    const payload = await response.json();
    if (staleMode === "analyze-specid") payload.object.moca_specid++;
    if (staleMode === "analyze-oid") payload.object.moca_oid++;
    if (staleMode === "analyze-metadata") delete payload.read_only;
    return fulfill(payload);
  }
  if (op === "queue" && [11002, 11003].includes(body.moca_specid))
    return fulfill({items: [{moca_oid: 1001, moca_specid: body.moca_specid, designation: "Demonstration 1001"}],
      lane: "spiff", read_only: false, has_more: false, next_after: null});
  if (op === "queue" && body.moca_specid === 999999)
    return fulfill({error: "Spectrum not found for an active object. Check the spectrum ID."}, 404);
  if (op === "queue" || op === "analyze")
    return route.fulfill({response: await route.fetch({postData: JSON.stringify({...body, mock: true})})});
  if (op === "preview") return fulfill({receipt: "test-plan", row_counts: {vetting: 1}, plan: {operations: []}});
  if (op === "undo") { undos++; return fulfill({undone: true}); }
  if (op === "submit") {
    submissions++;
    const mode = submitMode;
    await new Promise((resolve) => setTimeout(resolve, mode === "hold" ? 1500 : 650));
    try {
      if (mode === "fail") return await fulfill({error: "Simulated connection failure."}, 503);
      return await fulfill({submitted: true, undo_receipt: "test-undo"});
    } catch { /* Quit may have aborted this intercepted request. */ }
  }
});
async function title(value) {
  await page.waitForFunction((text) => document.querySelector("#object-title").textContent.includes(text) &&
    !document.querySelector("#report").disabled, value);
}
async function pending(n) {
  await page.waitForFunction((count) => document.querySelector("#submitting").textContent.startsWith(count + " "), n);
}
try {
  // Retain every supplied parameter verbatim, including aliases and encoded values.
  // Fragment values still override matching query keys, without rewriting either.
  for (const suffix of [
    "/spherex-review?username=management&password=%74est-placeholder&db=mocadb_private_tables&host=mocadb.ca&port=3306&lane=spiff&extra=keep%20me",
    "/js/spherex-autotype?lane=sublimeaperture#username=management&password=test-placeholder&database=mocadb_private_tables&host=mocadb.ca&port=3306&extra=keep",
    "/spherex-autotype?user=ignored&pwd=wrong&dbase=mocadb#user=management&pwd=test-placeholder&dbase=mocadb_private_tables",
  ]) {
    const suppliedURL = origin + suffix;
    await page.goto(suppliedURL); await title("1001");
    assert.equal(page.url(), suppliedURL);
    await page.reload(); await title("1001");
    assert.equal(page.url(), suppliedURL);
    assert(await page.locator("#write-enabled").isEnabled());
    assert(!await page.locator("#write-enabled").isChecked());
  }
  const reviewURL = origin + "/spherex-review?user=management&pwd=test-placeholder&dbase=mocadb_private_tables";
  // New static assets with old Python workers must never show an unrelated spectrum.
  for (const mode of ["queue", "queue-metadata", "analyze-specid", "analyze-oid", "analyze-metadata"]) {
    staleMode = mode;
    const before = apiRequests.length;
    await page.goto(reviewURL + "&specid=2860761");
    await page.waitForFunction(() => document.querySelector("#errors").textContent.includes("restarted after deployment"));
    assert.equal(await page.locator("#specid").evaluate((el) => el.closest("label").textContent), "Spectrum ID");
    assert(await page.locator("#report").isDisabled());
    assert(await page.locator("#preview").isDisabled());
    assert.equal(await page.locator("#classifications button:enabled").count(), 0);
    assert.equal(await page.locator("#plot").evaluate((el) => el.data?.length || 0), 0);
    if (mode.startsWith("queue")) assert(!apiRequests.slice(before).some((r) => r.op === "analyze"));
  }
  staleMode = null;
  const pastedURL = "https://dataviz.mocadb.ca/js/spectral-typing?specid=2860761&user=collaborators&pwd=ignored-nested-password";
  for (const suffix of ["&specid=2860761", "&moca_specid=2860761",
    "&specid=" + encodeURIComponent(pastedURL), "&specid=" + pastedURL]) {
    await page.goto(reviewURL + suffix); await title("1001");
    await page.waitForFunction(() => document.querySelector("#plot").data?.length >= 9);
    assert((await page.locator("#object-meta").textContent()).includes("spectrum=2860761"));
    assert((await page.locator("#write-hint").textContent()).includes("Read-only spectrum"));
    for (const selector of ["#write-enabled", "#preview", "#save-type", "#bad-pixels"])
      assert(await page.locator(selector).isDisabled(), selector);
    assert.equal(await page.locator("#classifications button:enabled").count(), 0);
    assert(await page.locator("#refit").isEnabled());
    const writesBefore = apiRequests.filter((r) => ["preview", "submit", "undo"].includes(r.op)).length;
    await page.locator("#object-title").click();
    for (const key of ["1", "Numpad2", "Alt+p", "Alt+s", "Alt+b"]) await page.keyboard.press(key);
    await page.locator("#refit").click(); await title("1001");
    assert.equal(apiRequests.filter((r) => ["preview", "submit", "undo"].includes(r.op)).length, writesBefore);
    assert.equal(apiRequests.filter((r) => r.op === "analyze").at(-1).body.moca_specid, 2860761);
    await page.reload(); await title("1001");
    assert((await page.locator("#object-meta").textContent()).includes("spectrum=2860761"));
  }
  // Exact ID wins over queue filters; supported packages select their own lane.
  await page.locator("#oids").fill("invalid queue IDs are ignored for exact spectra");
  await page.locator("#snr").fill("9999");
  for (const specid of [11002, 11003]) {
    await page.locator("#specid").fill(String(specid)); await page.locator("#specid").press("Enter");
    await page.waitForFunction((id) => document.querySelector("#object-meta").textContent.includes("spectrum=" + id) &&
      !document.querySelector("#refit").disabled, specid);
    assert.equal(await page.locator("#lane").inputValue(), "spiff");
    assert(await page.locator("#write-enabled").isEnabled());
    assert(await page.locator("#preview").isEnabled());
  }
  await page.locator("#write-enabled").check();
  await page.locator("#specid").fill(pastedURL); await page.locator("#load").click(); await title("1001");
  assert(await page.locator("#write-enabled").isDisabled());
  assert(!await page.locator("#write-enabled").isChecked());
  staleMode = "analyze-specid";
  await page.locator("#refit").click();
  await page.waitForFunction(() => document.querySelector("#errors").textContent.includes("restarted after deployment"));
  assert.equal(await page.locator("#plot").evaluate((el) => el.data?.length || 0), 0);
  assert.equal(await page.locator("#best-type").textContent(), "No fit loaded");
  staleMode = null;
  // Invalid/missing IDs never silently fall back to the ordinary review queue.
  const requestsBefore = apiRequests.length;
  await page.locator("#specid").fill("not-a-spectrum"); await page.locator("#load").click();
  assert((await page.locator("#errors").textContent()).includes("positive integer spectrum ID"));
  assert.equal(apiRequests.length, requestsBefore);
  await page.locator("#specid").fill("999999"); await page.locator("#load").click();
  await page.waitForFunction(() => document.querySelector("#errors").textContent.includes("Spectrum not found"));
  assert(await page.locator("#report").isDisabled());
  assert(await page.locator("#preview").isDisabled());
  await page.locator("#specid").fill(""); await page.locator("#oids").fill(""); await page.locator("#snr").fill("");
  await page.locator("#load").click(); await title("1001");
  assert(await page.locator("#write-enabled").isEnabled());
  assert(!await page.locator("#write-enabled").isChecked());
  await page.goto(reviewURL);
  await title("1001");
  await page.waitForFunction(() => document.querySelector("#plot").data?.length >= 9);
  const plotStyle = await page.evaluate(() => {
    const plot = document.querySelector("#plot");
    return {curves: plot.data.filter((t) => t.meta?.role === "template-curve").length,
      hidden: plot.data.some((t) => t.visible === "legendonly"), baselines: plot.layout.shapes.length,
      boxed: plot.layout.xaxis.showline && plot.layout.yaxis.mirror,
      square: Math.abs(plot.clientWidth - plot.clientHeight) <= 1};
  });
  assert.deepEqual(plotStyle, {curves: 3, hidden: false, baselines: 3, boxed: true, square: true});
  assert.equal(page.url(), reviewURL);
  assert(await page.locator("#write-enabled").isEnabled());
  await page.locator("#write-enabled").check();
  await page.locator("#object-title").click();
  await page.keyboard.press("1");
  await title("1002"); await pending(1);
  assert.equal(submissions, 1);
  await pending(0);
  await page.keyboard.press("Backspace");
  await title("1001"); assert.equal(undos, 1);
  // NumLock-independent keypad binding.
  submitMode = "fail";
  await page.locator("#object-title").click();
  await page.keyboard.press("Numpad2");
  await title("1002"); await pending(1); await pending(0);
  assert((await page.locator("#errors").textContent()).includes("1001"));
  assert(await page.locator("#retry").isEnabled());
  submitMode = "success";
  await page.locator("#retry").click(); await pending(1); await pending(0);
  await page.locator("#object-title").click();
  await page.evaluate(() => {
    window.testOpened = [];
    window.open = (url) => { window.testOpened.push(url); return null; };
  });
  await page.keyboard.press("w"); await page.keyboard.press("o");
  const urls = await page.evaluate(() => window.testOpened);
  assert.equal(new URLSearchParams(new URL(urls[0]).hash.slice(1)).get("zoom"), "20.0");
  assert.equal(new URLSearchParams(new URL(urls[0]).hash.slice(1)).get("size"), "30");
  assert(!urls.join("").includes("test-placeholder"));
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
  assert.equal((await page.context().cookies()).length, 0);
  assert(apiRequests.every((r) => !r.url.includes("pwd") && !r.url.includes("test-placeholder")));
  assert(apiRequests.every((r) => r.headers["x-moca-password"] === "test-placeholder"));
  assert(apiRequests.every((r) => r.headers["x-moca-user"] === "management" &&
    r.headers["x-moca-database"] === "mocadb_private_tables" && !r.headers.referer));
  // Two pending decisions and explicit quit confirmation.
  submitMode = "hold";
  await page.keyboard.press("1"); await title("1003");
  await page.keyboard.press("2"); await title("1004"); await pending(2);
  await page.keyboard.press("q");
  await page.waitForFunction(() => document.querySelector("#submitting").textContent === "Session closed");
  assert(dialogs.some((text) => text.includes("discard 2 pending")));
  assert.equal(await page.locator("#classifications button:enabled").count(), 0);
  assert.equal(page.url(), reviewURL);
  assert((await page.locator("#status").textContent()).includes("Credentials remain in the address bar"));
  assert.deepEqual(errors, []);
  console.log("Passed: stale-worker and spectrum-identity guards, exact spectrum IDs and pasted URLs, package detection, read-only controls/shortcuts, refit, invalid/missing IDs, queue restoration, URL retention, credential transport, immediate advance, numpad, failure recovery, retry, undo, object links and quit.");
} finally {
  // Prefetches may still be resolving when Quit aborts browser requests.
  await page.unrouteAll({behavior: "ignoreErrors"});
  await browser.close();
}
