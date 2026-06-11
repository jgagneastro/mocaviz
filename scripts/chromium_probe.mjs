#!/usr/bin/env node

import { chromium } from "playwright";

const DEFAULT_TIMEOUT_MS = 120000;
const DEFAULT_SETTLE_MS = 250;
const REPEATABLE_KEYS = new Set([
  "check",
  "click",
  "expect-count",
  "expect-hidden",
  "expect-plotly",
  "expect-selector",
  "expect-text",
  "expect-visible",
  "fill",
  "screenshot-selector",
  "select",
  "uncheck",
  "wait-for",
  "wait-hidden",
  "wait-js",
  "wait-text",
  "wait-visible",
]);

function parseArgs(argv) {
  const out = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      out._.push(arg);
      continue;
    }
    const eq = arg.indexOf("=");
    let key;
    let value;
    if (eq !== -1) {
      key = arg.slice(2, eq);
      value = arg.slice(eq + 1);
    } else {
      key = arg.slice(2);
      const next = argv[index + 1];
      if (next && !next.startsWith("--")) {
        value = next;
        index += 1;
      } else {
        value = true;
      }
    }
    if (REPEATABLE_KEYS.has(key)) {
      if (!Array.isArray(out[key])) out[key] = [];
      out[key].push(value);
    } else {
      out[key] = value;
    }
  }
  return out;
}

function usage() {
  return [
    "Usage:",
    "  node scripts/chromium_probe.mjs --url URL [options]",
    "",
    "Common options:",
    "  --headed                         Run a visible Chromium window.",
    "  --width 1400 --height 900        Browser viewport.",
    "  --timeout 120000                 Navigation/wait timeout in ms.",
    "  --settle 250                     Extra wait after actions/waits in ms.",
    "  --screenshot /path/page.png      Save a full-page screenshot.",
    "  --screenshot-selector SEL=>PNG   Save an element screenshot; repeatable.",
    "  --fail-on-warning                Treat console warnings as failures.",
    "  --allow-console-errors           Do not fail on console errors.",
    "",
    "Waits and actions:",
    "  --wait-for SEL                   Wait for selector to exist.",
    "  --wait-visible SEL               Wait for visible selector.",
    "  --wait-hidden SEL                Wait for hidden/detached selector.",
    "  --wait-text SEL=>TEXT            Wait for selector text to contain TEXT.",
    "  --wait-js EXPR                   Wait until JS expression returns truthy.",
    "  --click SEL                      Click selector; repeatable.",
    "  --fill SEL=>TEXT                 Fill input; repeatable.",
    "  --select SEL=>VALUE              Select option; repeatable.",
    "  --check SEL / --uncheck SEL      Toggle checkbox; repeatable.",
    "",
    "Assertions:",
    "  --expect-visible SEL             Require visible selector.",
    "  --expect-hidden SEL              Require hidden/detached selector.",
    "  --expect-text SEL=>TEXT          Require text to contain TEXT.",
    "  --expect-count 'SEL>=N'          Require selector count comparison.",
    "  --expect-plotly 'SEL::traces>=1,shapes>=0,points>=1'",
    "",
    "Examples:",
    "  node scripts/chromium_probe.mjs --url http://127.0.0.1:8074/js/spectral-index-explorer?mock=1 --wait-js \"document.querySelector('#sie-plot')?.data?.length > 0\" --expect-plotly '#sie-plot::traces>=1,shapes>=2' --expect-count '#sie-band-table tbody tr>=2'",
  ].join("\n");
}

function asArray(value) {
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

function asNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function boolArg(value) {
  return value === true || ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

function splitMapping(raw, optionName) {
  const text = String(raw ?? "");
  const delimiter = text.indexOf("=>");
  if (delimiter === -1) {
    throw new Error(`${optionName} must use SEL=>VALUE syntax: ${text}`);
  }
  const selector = text.slice(0, delimiter).trim();
  const value = text.slice(delimiter + 2);
  if (!selector) throw new Error(`${optionName} has an empty selector: ${text}`);
  return { selector, value };
}

function parseCountAssertion(raw) {
  const text = String(raw ?? "").trim();
  const match = text.match(/^(.+?)\s*(>=|<=|==|=|>|<)\s*([0-9]+)\s*$/);
  if (!match) {
    throw new Error(`--expect-count must look like 'selector>=N': ${text}`);
  }
  return {
    selector: match[1].trim(),
    operator: match[2],
    expected: Number(match[3]),
    raw: text,
  };
}

function parseNumericCondition(raw) {
  const text = String(raw ?? "").trim();
  const match = text.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|=|>|<)\s*(-?[0-9]+(?:\.[0-9]+)?)\s*$/);
  if (!match) throw new Error(`Bad numeric condition: ${text}`);
  return {
    key: match[1],
    operator: match[2],
    expected: Number(match[3]),
    raw: text,
  };
}

function parsePlotlyAssertion(raw) {
  const text = String(raw ?? "").trim();
  const delimiter = text.indexOf("::");
  const selector = (delimiter === -1 ? text : text.slice(0, delimiter)).trim();
  const conditionText = delimiter === -1 ? "traces>=1" : text.slice(delimiter + 2);
  if (!selector) throw new Error(`--expect-plotly has an empty selector: ${text}`);
  const conditions = conditionText
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map(parseNumericCondition);
  return { selector, conditions, raw: text };
}

function compare(actual, operator, expected) {
  if (operator === ">" ) return actual > expected;
  if (operator === ">=") return actual >= expected;
  if (operator === "<" ) return actual < expected;
  if (operator === "<=") return actual <= expected;
  return actual === expected;
}

function comparatorText(actual, operator, expected) {
  return `${actual} ${operator} ${expected}`;
}

function consoleMessageToText(message) {
  return `${message.type()}: ${message.text()}`;
}

async function waitForText(page, raw, timeoutMs) {
  const { selector, value } = splitMapping(raw, "--wait-text");
  await page.waitForFunction(
    ({ selector: waitSelector, value: waitValue }) => {
      const node = document.querySelector(waitSelector);
      return Boolean(node && String(node.textContent || "").includes(waitValue));
    },
    { selector, value },
    { timeout: timeoutMs },
  );
}

async function waitForJs(page, expression, timeoutMs) {
  await page.waitForFunction(
    (expr) => Boolean(Function(`return (${expr});`)()),
    String(expression),
    { timeout: timeoutMs },
  );
}

async function applyActions(page, args) {
  for (const selector of asArray(args.click)) {
    await page.locator(String(selector)).click();
  }
  for (const raw of asArray(args.fill)) {
    const { selector, value } = splitMapping(raw, "--fill");
    await page.locator(selector).fill(value);
  }
  for (const raw of asArray(args.select)) {
    const { selector, value } = splitMapping(raw, "--select");
    await page.locator(selector).selectOption(value);
  }
  for (const selector of asArray(args.check)) {
    await page.locator(String(selector)).setChecked(true);
  }
  for (const selector of asArray(args.uncheck)) {
    await page.locator(String(selector)).setChecked(false);
  }
}

async function applyWaits(page, args, timeoutMs) {
  for (const selector of asArray(args["wait-for"])) {
    await page.waitForSelector(String(selector), { timeout: timeoutMs });
  }
  for (const selector of asArray(args["wait-visible"])) {
    await page.locator(String(selector)).waitFor({ state: "visible", timeout: timeoutMs });
  }
  for (const selector of asArray(args["wait-hidden"])) {
    await page.locator(String(selector)).waitFor({ state: "hidden", timeout: timeoutMs });
  }
  for (const raw of asArray(args["wait-text"])) {
    await waitForText(page, raw, timeoutMs);
  }
  for (const expression of asArray(args["wait-js"])) {
    await waitForJs(page, expression, timeoutMs);
  }
}

async function collectPlotlyInfo(page, selector) {
  return page.locator(selector).evaluate((plot) => {
    const traces = Array.isArray(plot.data) ? plot.data : [];
    const layout = plot.layout || {};
    const pointCounts = traces.map((trace) => {
      const x = Array.isArray(trace.x) ? trace.x : [];
      return x.filter((value) => value !== null && value !== undefined).length;
    });
    return {
      selector: null,
      traces: traces.length,
      shapes: Array.isArray(layout.shapes) ? layout.shapes.length : 0,
      annotations: Array.isArray(layout.annotations) ? layout.annotations.length : 0,
      points: pointCounts.reduce((sum, value) => sum + value, 0),
      traceNames: traces.map((trace) => trace.name || ""),
      pointCounts,
    };
  });
}

async function runAssertions(page, args) {
  const failures = [];
  const assertions = {
    counts: [],
    texts: [],
    visibility: [],
    plotly: [],
  };

  for (const selector of asArray(args["expect-selector"]).concat(asArray(args["expect-visible"]))) {
    const count = await page.locator(String(selector)).count();
    const visible = count > 0 && await page.locator(String(selector)).first().isVisible().catch(() => false);
    assertions.visibility.push({ selector, expected: "visible", count, visible });
    if (!visible) failures.push(`Expected visible selector not found: ${selector}`);
  }

  for (const selector of asArray(args["expect-hidden"])) {
    const count = await page.locator(String(selector)).count();
    const visible = count > 0 && await page.locator(String(selector)).first().isVisible().catch(() => false);
    assertions.visibility.push({ selector, expected: "hidden", count, visible });
    if (visible) failures.push(`Expected selector to be hidden: ${selector}`);
  }

  for (const raw of asArray(args["expect-text"])) {
    const { selector, value } = splitMapping(raw, "--expect-text");
    const text = await page.locator(selector).first().textContent().catch(() => null);
    const ok = text !== null && text.includes(value);
    assertions.texts.push({ selector, expected: value, actual: text, ok });
    if (!ok) failures.push(`Expected text ${JSON.stringify(value)} in ${selector}; got ${JSON.stringify(text)}`);
  }

  for (const raw of asArray(args["expect-count"])) {
    const assertion = parseCountAssertion(raw);
    const count = await page.locator(assertion.selector).count();
    const ok = compare(count, assertion.operator, assertion.expected);
    assertions.counts.push({ ...assertion, actual: count, ok });
    if (!ok) failures.push(`Expected count ${assertion.raw}; got ${comparatorText(count, assertion.operator, assertion.expected)}`);
  }

  for (const raw of asArray(args["expect-plotly"])) {
    const assertion = parsePlotlyAssertion(raw);
    const count = await page.locator(assertion.selector).count();
    if (!count) {
      failures.push(`Expected Plotly element not found: ${assertion.selector}`);
      assertions.plotly.push({ ...assertion, found: false });
      continue;
    }
    const info = await collectPlotlyInfo(page, assertion.selector);
    info.selector = assertion.selector;
    const conditionResults = assertion.conditions.map((condition) => {
      const actual = Number(info[condition.key] ?? NaN);
      const ok = Number.isFinite(actual) && compare(actual, condition.operator, condition.expected);
      if (!ok) {
        failures.push(`Expected Plotly ${assertion.selector} ${condition.raw}; got ${condition.key}=${actual}`);
      }
      return { ...condition, actual, ok };
    });
    assertions.plotly.push({ selector: assertion.selector, info, conditions: conditionResults, raw: assertion.raw });
  }

  return { failures, assertions };
}

async function saveScreenshots(page, args, result) {
  if (args.screenshot) {
    const path = String(args.screenshot);
    await page.screenshot({ path, fullPage: !boolArg(args["viewport-screenshot"]) });
    result.screenshot = path;
  }
  const selectorShots = [];
  for (const raw of asArray(args["screenshot-selector"])) {
    const { selector, value: path } = splitMapping(raw, "--screenshot-selector");
    await page.locator(selector).first().screenshot({ path });
    selectorShots.push({ selector, path });
  }
  if (selectorShots.length) result.selectorScreenshots = selectorShots;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || args.h || (!args.url && !args._[0])) {
    console.log(usage());
    process.exit(args.help || args.h ? 0 : 2);
  }

  const url = String(args.url || args._[0]);
  const timeoutMs = asNumber(args.timeout, DEFAULT_TIMEOUT_MS);
  const settleMs = asNumber(args.settle, DEFAULT_SETTLE_MS);
  const width = asNumber(args.width, 1400);
  const height = asNumber(args.height, 900);
  const waitUntil = String(args["wait-until"] || "domcontentloaded");
  const failOnWarning = boolArg(args["fail-on-warning"]);
  const allowConsoleErrors = boolArg(args["allow-console-errors"]);
  const browser = await chromium.launch({ headless: !boolArg(args.headed) });

  try {
    const page = await browser.newPage({ viewport: { width, height } });
    const consoleMessages = [];
    const pageErrors = [];
    const requests = [];
    page.on("console", (message) => {
      const text = consoleMessageToText(message);
      consoleMessages.push(text);
    });
    page.on("pageerror", (error) => {
      pageErrors.push(error.message || String(error));
    });
    page.on("request", (request) => {
      if (!args["record-requests"]) return;
      requests.push({ method: request.method(), url: request.url() });
    });

    const started = Date.now();
    await page.goto(url, { waitUntil, timeout: timeoutMs });
    await applyActions(page, args);
    await applyWaits(page, args, timeoutMs);
    if (settleMs > 0) await page.waitForTimeout(settleMs);
    const assertionResult = await runAssertions(page, args);
    const title = await page.title().catch(() => "");
    const result = {
      ok: true,
      url: page.url(),
      title,
      elapsedMs: Date.now() - started,
      viewport: { width, height },
      failures: assertionResult.failures,
      assertions: assertionResult.assertions,
      consoleMessages,
      pageErrors,
    };
    if (requests.length) result.requests = requests;
    if (pageErrors.length) {
      result.failures.push(...pageErrors.map((message) => `Page error: ${message}`));
    }
    if (!allowConsoleErrors) {
      const errors = consoleMessages.filter((message) => message.startsWith("error:"));
      result.failures.push(...errors.map((message) => `Console error: ${message}`));
    }
    if (failOnWarning) {
      const warnings = consoleMessages.filter((message) => message.startsWith("warning:"));
      result.failures.push(...warnings.map((message) => `Console warning: ${message}`));
    }
    await saveScreenshots(page, args, result);
    result.ok = result.failures.length === 0;
    console.log(JSON.stringify(result, null, 2));
    if (!result.ok) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
