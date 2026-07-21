#!/usr/bin/env node

import { writeFile } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.JS_PAGES_BENCHMARK_BASE_URL || "http://127.0.0.1:8118";
const outputPath = process.env.JS_PAGES_BENCHMARK_OUTPUT || "/private/tmp/mocaviz_js_pages_startup.json";
const timeoutMs = Number(process.env.JS_PAGES_BENCHMARK_TIMEOUT_MS || 120000);
const pages = [
  ["Brown Dwarf Photometry", "/bd-colors"],
  ["Brown Dwarf Evolution", "/bd-evolution"],
  ["Companion Explorer", "/companion-explorer"],
  ["Exoplanets Explorer", "/exoplanets-explorer"],
  ["Gaia CMD", "/gaia-cmd"],
  ["MOCA Explorer", "/moca-explorer"],
  ["BANYAN Sigma", "/banyan-sigma"],
  ["Group Hierarchy", "/group-hierarchy"],
  ["Spectral Typing", "/spectral-typing"],
  ["Spectral Explorer", "/spectra"],
  ["Spectral Index Explorer", "/spectral-index-explorer"],
  ["SED Explorer", "/sed"],
  ["Atmospheric Retrieval", "/retrieval-explorer"],
  ["Astrometric Explorer", "/astrometry"],
  ["Spatial-Kinematic", "/xyz"],
  ["Dual XYZ/UVW", "/xyz-dual"],
  ["Age PDF Explorer", "/age-pdfs"],
  ["MOCA Flows", "/moca-flows"],
  ["RVBAM Explorer", "/rvbam-explorer"],
  ["Moranta Rotation", "/moranta26-rotation"],
];

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : Math.round((sorted[middle - 1] + sorted[middle]) / 2);
}

async function measurePage(context, label, path, phase) {
  const page = await context.newPage();
  const apiStarted = new Map();
  const apiRequests = [];
  const pageErrors = [];
  const consoleErrors = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) apiStarted.set(request, performance.now());
  });
  page.on("response", (response) => {
    const request = response.request();
    if (!apiStarted.has(request)) return;
    apiRequests.push({
      url: response.url(),
      status: response.status(),
      elapsedMs: Math.round(performance.now() - apiStarted.get(request)),
    });
  });
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  const started = performance.now();
  let networkIdle = true;
  let navigationError = null;
  try {
    await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    await page.waitForLoadState("networkidle", { timeout: timeoutMs });
  } catch (error) {
    networkIdle = false;
    navigationError = String(error?.message || error);
  }
  await page.waitForTimeout(250);
  const elapsedMs = Math.round(performance.now() - started);
  const state = await page.evaluate(() => {
    const visible = (node) => {
      const style = window.getComputedStyle(node);
      return style.display !== "none" && style.visibility !== "hidden" && !node.hidden;
    };
    const statuses = Array.from(document.querySelectorAll(".status"))
      .filter(visible)
      .slice(0, 8)
      .map((node) => ({ text: String(node.textContent || "").trim(), loading: node.classList.contains("loading"), error: node.classList.contains("error") }));
    const plots = Array.from(document.querySelectorAll(".js-plotly-plot")).map((plot) => ({
      traces: Array.isArray(plot.data) ? plot.data.length : 0,
      points: (plot.data || []).reduce((sum, trace) => sum + (Array.isArray(trace.x) ? trace.x.length : 0), 0),
    }));
    return {
      title: document.title,
      statuses,
      plotCount: plots.length,
      traces: plots.reduce((sum, plot) => sum + plot.traces, 0),
      points: plots.reduce((sum, plot) => sum + plot.points, 0),
    };
  });
  await page.close();
  return {
    label,
    path,
    phase,
    elapsedMs,
    networkIdle,
    navigationError,
    apiRequests,
    pageErrors,
    consoleErrors,
    ...state,
  };
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (let index = 0; index < pages.length; index += 1) {
      const [label, path] = pages[index];
      process.stderr.write(`[${index + 1}/${pages.length}] ${label}: clearing caches\n`);
      const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
      const cleared = await context.request.post(`${baseUrl}/api/cache/clear`);
      if (!cleared.ok()) process.stderr.write(`  cache clear returned HTTP ${cleared.status()}\n`);
      const cold = await measurePage(context, label, path, "cold");
      process.stderr.write(`  cold ${cold.elapsedMs} ms, APIs ${cold.apiRequests.length}, errors ${cold.pageErrors.length + cold.consoleErrors.length}\n`);
      const hot = await measurePage(context, label, path, "hot");
      process.stderr.write(`  hot  ${hot.elapsedMs} ms, APIs ${hot.apiRequests.length}, errors ${hot.pageErrors.length + hot.consoleErrors.length}\n`);
      results.push({ label, path, cold, hot });
      await context.close();
    }
  } finally {
    await browser.close();
  }

  const coldValues = results.map((row) => row.cold.elapsedMs);
  const hotValues = results.map((row) => row.hot.elapsedMs);
  const report = {
    generatedAt: new Date().toISOString(),
    baseUrl,
    definition: "Fresh browser context and cleared server caches for cold; same context and populated server/browser caches for hot; elapsed through network idle plus 250 ms render settle.",
    summary: {
      pageCount: results.length,
      coldTotalMs: coldValues.reduce((sum, value) => sum + value, 0),
      hotTotalMs: hotValues.reduce((sum, value) => sum + value, 0),
      coldMedianMs: median(coldValues),
      hotMedianMs: median(hotValues),
      coldMaxMs: Math.max(...coldValues),
      hotMaxMs: Math.max(...hotValues),
    },
    results,
  };
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify({ outputPath, summary: report.summary }, null, 2)}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
