(function () {
  "use strict";

  const Plotly = window.Plotly;
  if (!Plotly || Plotly.__mocavizExportFixInstalled) return;

  const Snapshot = Plotly.Snapshot || {};
  if (
    typeof Plotly.downloadImage !== "function" &&
    typeof Plotly.toImage !== "function" &&
    typeof Snapshot.downloadImage !== "function" &&
    typeof Snapshot.toImage !== "function"
  ) {
    return;
  }

  Plotly.__mocavizExportFixInstalled = true;

  const settlingByPlot = new WeakMap();
  let exportDepth = 0;

  function plotDiv(gd) {
    if (typeof gd === "string") return document.getElementById(gd);
    return gd || null;
  }

  function frame() {
    return new Promise((resolve) => window.requestAnimationFrame(resolve));
  }

  async function ignoreFailures(promise) {
    try {
      await promise;
    } catch (_) {
      // Export should still proceed if Plotly refuses a resize/redraw.
    }
  }

  async function settlePlot(gd) {
    const div = plotDiv(gd);
    if (!div || !div._fullLayout) return;

    const existing = settlingByPlot.get(div);
    if (existing) {
      await existing;
      return;
    }

    const settle = Promise.resolve().then(async () => {
      if (Plotly.Plots && typeof Plotly.Plots.resize === "function") {
        await ignoreFailures(Plotly.Plots.resize(div));
      }

      await frame();
      await frame();

      if (typeof Plotly.redraw === "function") {
        await ignoreFailures(Plotly.redraw(div));
      }

      await frame();
      await frame();
    })();

    settlingByPlot.set(div, settle);
    try {
      await settle;
    } finally {
      settlingByPlot.delete(div);
    }
  }

  async function withSettledPlot(gd, fn, context, args) {
    if (exportDepth === 0) {
      await settlePlot(gd);
    }
    exportDepth += 1;
    try {
      return await fn.apply(context, args);
    } finally {
      exportDepth -= 1;
    }
  }

  function prewarmPlot(gd) {
    const div = plotDiv(gd);
    if (!div || !div._fullLayout || settlingByPlot.has(div)) return;
    window.clearTimeout(div.__mocavizExportPrewarmTimer);
    div.__mocavizExportPrewarmTimer = window.setTimeout(() => {
      if (div.isConnected) settlePlot(div);
    }, 100);
  }

  function wrapExport(owner, key, wrapperName) {
    if (!owner || typeof owner[key] !== "function") return;
    const original = owner[key];
    owner[key] = {
      [wrapperName]: function mocavizWrappedExport(gd) {
        return withSettledPlot(gd, original, this, arguments);
      },
    }[wrapperName];
  }

  wrapExport(Plotly, "downloadImage", "mocavizDownloadImage");
  wrapExport(Plotly, "toImage", "mocavizToImage");
  wrapExport(Snapshot, "downloadImage", "mocavizSnapshotDownloadImage");
  wrapExport(Snapshot, "toImage", "mocavizSnapshotToImage");

  document.addEventListener(
    "plotly_afterplot",
    (event) => {
      prewarmPlot(event.target);
    },
    true,
  );

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      () => document.querySelectorAll(".js-plotly-plot").forEach((div) => prewarmPlot(div)),
      { once: true },
    );
  } else {
    window.setTimeout(() => document.querySelectorAll(".js-plotly-plot").forEach((div) => prewarmPlot(div)), 0);
  }
})();
