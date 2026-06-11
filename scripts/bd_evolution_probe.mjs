#!/usr/bin/env node

import { chromium } from "playwright";

const DEFAULT_URL = process.env.BD_EVOLUTION_PROBE_URL || "http://127.0.0.1:8099/bd-evolution";
const DEFAULT_TIMEOUT_MS = 120000;
const DEFAULT_SETTLE_MS = 900;
const EXPECTED_CLASS_EDGE = "rgba(255,255,255,0.88)";
const EXPECTED_COMPANION_EDGE = "#111111";

function parseArgs(argv) {
  const out = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      out._.push(arg);
      continue;
    }
    const eq = arg.indexOf("=");
    if (eq !== -1) {
      out[arg.slice(2, eq)] = arg.slice(eq + 1);
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

function asNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const url = args.url || args._[0] || DEFAULT_URL;
  const timeoutMs = asNumber(args.timeout || process.env.BD_EVOLUTION_PROBE_TIMEOUT_MS, DEFAULT_TIMEOUT_MS);
  const settleMs = asNumber(args.settle || process.env.BD_EVOLUTION_PROBE_SETTLE_MS, DEFAULT_SETTLE_MS);
  const width = asNumber(args.width, 1400);
  const height = asNumber(args.height, 900);
  const browser = await chromium.launch({ headless: !args.headed });

  try {
    const page = await browser.newPage({ viewport: { width, height } });
    let dataRequests = 0;
    const dataRequestUrls = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/bd-evolution/data")) {
        dataRequests += 1;
        dataRequestUrls.push(request.url());
      }
    });

    await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    await page.waitForFunction(
      () => document.querySelector("#bde-summary")?.textContent?.includes("sample:"),
      null,
      { timeout: timeoutMs },
    );

    const checkbox = page.locator("#bde-remove-companions");
    const initialChecked = await checkbox.isChecked();
    const initialRequests = dataRequests;
    const initialSummary = await page.locator("#bde-summary").textContent();

    await checkbox.setChecked(true);
    await page.waitForTimeout(settleMs);
    const afterCheck = await checkbox.isChecked();
    const afterCheckRequests = dataRequests;
    const checkedSummary = await page.locator("#bde-summary").textContent();

    await checkbox.setChecked(false);
    await page.waitForTimeout(settleMs);
    const afterUncheck = await checkbox.isChecked();
    const afterUncheckRequests = dataRequests;
    const finalSummary = await page.locator("#bde-summary").textContent();

    const ignoreGroups = page.locator("#bde-ignore-aids");
    const initialIgnoreGroups = await ignoreGroups.inputValue();
    await ignoreGroups.fill("");
    await page.waitForTimeout(settleMs);
    const afterClearIgnoreGroups = await ignoreGroups.inputValue();
    const afterClearIgnoreRequests = dataRequests;
    const clearedIgnoreSummary = await page.locator("#bde-summary").textContent();

    await ignoreGroups.fill(initialIgnoreGroups || "OCTN,CUMA");
    await page.waitForTimeout(settleMs);
    const afterRestoreIgnoreGroups = await ignoreGroups.inputValue();
    const afterRestoreIgnoreRequests = dataRequests;
    const restoredIgnoreSummary = await page.locator("#bde-summary").textContent();

    const traces = await page.evaluate(() => {
      const plot = document.querySelector("#bde-plot");
      return (plot?.data || [])
        .filter((trace) => trace.meta?.bdeRole === "object" || trace.meta?.bdeRole === "companion-legend")
        .map((trace) => ({
          name: trace.name,
          showlegend: trace.showlegend,
          role: trace.meta?.bdeRole,
          category: trace.meta?.bdeCategory,
          kind: trace.meta?.bdeTraceKind,
          lineColor: trace.marker?.line?.color,
          legendgroup: trace.legendgroup,
          n: Array.isArray(trace.x) ? trace.x.filter((value) => value !== null && value !== undefined).length : 0,
        }));
    });

    const failures = [];
    if (!afterCheck) failures.push("Remove companions did not stay checked after checking.");
    if (afterUncheck) failures.push("Remove companions re-checked itself after unchecking.");
    if (afterCheckRequests !== initialRequests) failures.push("Checking Remove companions triggered an API data request.");
    if (afterUncheckRequests !== initialRequests) failures.push("Unchecking Remove companions triggered an API data request.");
    if (afterClearIgnoreRequests !== initialRequests) failures.push("Clearing Ignore groups triggered an API data request.");
    if (afterRestoreIgnoreRequests !== initialRequests) failures.push("Restoring Ignore groups triggered an API data request.");

    const badClassLegendEdges = traces.filter((trace) => (
      trace.role === "object"
      && trace.showlegend === true
      && trace.lineColor !== EXPECTED_CLASS_EDGE
    ));
    if (badClassLegendEdges.length) {
      failures.push(`Measurement-class legend traces with non-white edge: ${badClassLegendEdges.map((trace) => trace.name).join(",")}`);
    }

    const badCompanionEdges = traces.filter((trace) => (
      (trace.role === "companion-legend" || trace.kind === "companion")
      && trace.lineColor !== EXPECTED_COMPANION_EDGE
    ));
    if (badCompanionEdges.length) {
      failures.push(`Companion traces with non-black edge: ${badCompanionEdges.map((trace) => trace.name).join(",")}`);
    }

    let targetCheck = null;
    const targetOid = asNumber(args["target-oid"] || process.env.BD_EVOLUTION_PROBE_TARGET_OID, null);
    if (targetOid !== null) {
      const targetUrl = new URL(url);
      targetUrl.searchParams.set("moca_oid", String(Math.trunc(targetOid)));
      targetUrl.searchParams.set("ya_prob_min", targetUrl.searchParams.get("ya_prob_min") || "80");
      const beforeTargetRequests = dataRequests;
      await page.goto(targetUrl.toString(), { waitUntil: "domcontentloaded", timeout: timeoutMs });
      await page.waitForFunction(
        () => document.querySelector("#bde-summary")?.textContent?.includes("sample:"),
        null,
        { timeout: timeoutMs },
      );
      await page.waitForTimeout(settleMs);
      const afterTargetRequests = dataRequests;
      targetCheck = await page.evaluate((oid) => {
        const plot = document.querySelector("#bde-plot");
        const targetTrace = (plot?.data || []).find((trace) => trace.meta?.bdeRole === "target-oid");
        const targetOids = (targetTrace?.customdata || []).map((value) => Number(value)).filter(Number.isFinite);
        return {
          url: window.location.href,
          summary: document.querySelector("#bde-summary")?.textContent || "",
          chipText: document.querySelector("#bde-selected-objects")?.textContent || "",
          directOidValue: document.querySelector("#bde-highlight-oids")?.value || "",
          targetTraceName: targetTrace?.name || "",
          targetTraceCount: targetOids.length,
          targetTraceIncludesOid: targetOids.includes(Number(oid)),
        };
      }, Math.trunc(targetOid));
      targetCheck.beforeTargetRequests = beforeTargetRequests;
      targetCheck.afterTargetRequests = afterTargetRequests;
      targetCheck.targetRequestUrl = dataRequestUrls[dataRequestUrls.length - 1] || "";
      if (!targetCheck.chipText.includes(`oid${Math.trunc(targetOid)}`)) {
        failures.push(`Target OID ${Math.trunc(targetOid)} did not appear as a selected target chip.`);
      }
      if (!targetCheck.targetTraceIncludesOid) {
        failures.push(`Target OID ${Math.trunc(targetOid)} did not appear in the Target OID plot trace.`);
      }
      if (!targetCheck.targetRequestUrl.includes(`moca_oid=${Math.trunc(targetOid)}`)) {
        failures.push(`Target OID ${Math.trunc(targetOid)} was not sent to the data API.`);
      }
    }

    const result = {
      ok: failures.length === 0,
      failures,
      url: page.url(),
      initialChecked,
      afterCheck,
      afterUncheck,
      initialIgnoreGroups,
      afterClearIgnoreGroups,
      afterRestoreIgnoreGroups,
      initialRequests,
      afterCheckRequests,
      afterUncheckRequests,
      afterClearIgnoreRequests,
      afterRestoreIgnoreRequests,
      initialSummary,
      checkedSummary,
      finalSummary,
      clearedIgnoreSummary,
      restoredIgnoreSummary,
      dataRequestUrls,
      traces,
      targetCheck,
    };
    console.log(JSON.stringify(result, null, 2));
    if (failures.length) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
