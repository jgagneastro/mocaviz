// Stateful browser checks beyond chromium_probe's basic render/navigation checks.
// All API traffic is intercepted or explicitly converted to synthetic demo reads.
import assert from "node:assert/strict";
import { chromium } from "playwright";

const origin = process.argv[2] || "http://127.0.0.1:8079";
const browser = await chromium.launch({headless: true});
const page = await browser.newPage();
const dialogs = [], apiRequests = [], errors = [];
let submitMode = "success", submissions = 0, undos = 0;
page.on("pageerror", (e) => errors.push(e.message));
page.on("dialog", async (dialog) => { dialogs.push(dialog.message()); await dialog.accept(); });
await page.route("**/api/spherex-review/*", async (route) => {
  const request = route.request(), op = new URL(request.url()).pathname.split("/").at(-1);
  const body = request.postDataJSON();
  apiRequests.push({url: request.url(), headers: request.headers()});
  const fulfill = (payload, status = 200) => route.fulfill({
    status, contentType: "application/json", body: JSON.stringify({ok: status === 200, ...payload}),
  });
  if (op === "context") {
    const response = await route.fetch({postData: JSON.stringify({mock: true})});
    return fulfill({...await response.json(), role: "management", can_write: true});
  }
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
  console.log("Passed: query/fragment URL retention, reload, credential transport, immediate advance, queue count, numpad, failure recovery, retry, undo, object links and quit.");
} finally {
  // Prefetches may still be resolving when Quit aborts browser requests.
  await page.unrouteAll({behavior: "ignoreErrors"});
  await browser.close();
}
