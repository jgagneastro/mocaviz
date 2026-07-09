#!/usr/bin/env node

import { chromium } from "playwright";

const DEFAULT_URL = process.env.GAIA_CMD_BENCHMARK_URL || "http://127.0.0.1:8118/js/gaia-cmd?asso=THA";
const DEFAULT_TIMEOUT_MS = 120000;

function parseArgs(argv) {
  const out = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      out._.push(arg);
      continue;
    }
    const equals = arg.indexOf("=");
    if (equals !== -1) {
      out[arg.slice(2, equals)] = arg.slice(equals + 1);
      continue;
    }
    const key = arg.slice(2);
    const next = argv[index + 1];
    if (next && !next.startsWith("--")) {
      out[key] = next;
      index += 1;
    } else {
      out[key] = true;
    }
  }
  return out;
}

async function waitForSettledGaia(page, aid = null, timeout = DEFAULT_TIMEOUT_MS) {
  await page.waitForFunction((expectedAid) => {
    const status = document.querySelector("#gcmd-status");
    const plot = document.querySelector("#gcmd-plot");
    if (!status || status.classList.contains("loading") || status.classList.contains("error")) return false;
    const names = (plot?.data || []).map((trace) => String(trace.name || ""));
    if (!names.includes("Field")) return false;
    return expectedAid ? names.some((name) => name.startsWith(expectedAid)) : true;
  }, aid, { timeout });
}

async function addAssociation(page, aid, label, timeout) {
  await page.locator("#gcmd-aid-search").fill(aid);
  const result = page.getByRole("button", { name: label, exact: true });
  await result.waitFor({ state: "visible", timeout });
  const started = performance.now();
  await result.evaluate((button) => button.click());
  await waitForSettledGaia(page, aid, timeout);
  return Math.round(performance.now() - started);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const url = args.url || args._[0] || DEFAULT_URL;
  const timeout = Number(args.timeout || DEFAULT_TIMEOUT_MS);
  const browser = await chromium.launch({ headless: !args.headed });
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    const requests = [];
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(String(error)));
    page.on("request", (request) => {
      if (request.url().includes("/api/gaia-cmd/data")) requests.push(request.url());
    });

    const loadStarted = performance.now();
    await page.goto(url, { waitUntil: "domcontentloaded", timeout });
    await waitForSettledGaia(page, null, timeout);
    const initialLoadMs = Math.round(performance.now() - loadStarted);
    const initialRequestCount = requests.length;

    const addMs = await addAssociation(page, "ABDMG", "ABDMG - AB Doradus moving group", timeout);
    const afterAddRequestCount = requests.length;
    const addMode = await page.locator("#gcmd-plot").getAttribute("data-update-mode");

    const removeButton = page.locator('#gcmd-selected-aids button[data-aid="ABDMG"]');
    const removeStarted = performance.now();
    await removeButton.click();
    await page.waitForFunction(() => {
      const status = document.querySelector("#gcmd-status");
      const plot = document.querySelector("#gcmd-plot");
      return status
        && !status.classList.contains("loading")
        && !status.classList.contains("error")
        && !(plot?.data || []).some((trace) => String(trace.name || "").startsWith("ABDMG"));
    }, null, { timeout });
    const removeMs = Math.round(performance.now() - removeStarted);
    const afterRemoveRequestCount = requests.length;

    const readdMs = await addAssociation(page, "ABDMG", "ABDMG - AB Doradus moving group", timeout);
    const afterReaddRequestCount = requests.length;
    const readdMode = await page.locator("#gcmd-plot").getAttribute("data-update-mode");

    const plot = await page.evaluate(() => {
      const node = document.querySelector("#gcmd-plot");
      return {
        traces: (node?.data || []).length,
        points: (node?.data || []).reduce((sum, trace) => sum + (Array.isArray(trace.x) ? trace.x.length : 0), 0),
        visibleNames: (node?.data || []).map((trace) => trace.name).filter(Boolean),
      };
    });
    const result = {
      ok: true,
      url: page.url(),
      timingsMs: { initialLoadMs, addMs, removeMs, readdMs },
      requestCounts: {
        initial: initialRequestCount,
        addedByAdd: afterAddRequestCount - initialRequestCount,
        addedByRemove: afterRemoveRequestCount - afterAddRequestCount,
        addedByReadd: afterReaddRequestCount - afterRemoveRequestCount,
      },
      updateModes: { add: addMode, readd: readdMode },
      plot,
      pageErrors,
    };
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
