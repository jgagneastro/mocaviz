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
  const imageWarmupByPlot = new WeakMap();
  let exportDepth = 0;

  function plotDiv(gd) {
    if (typeof gd === "string") return document.getElementById(gd);
    return gd || null;
  }

  function frame() {
    return new Promise((resolve) => window.requestAnimationFrame(resolve));
  }

  function timeout(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
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
      await timeout(80);
    });

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

  function plotUsesWebGl(div) {
    return (div?.data || []).some((trace) => {
      const type = String(trace?.type || "scatter").toLowerCase();
      return type.includes("gl") || type.includes("3d") || type === "surface" || type === "mesh3d";
    });
  }

  function imageWarmupSignature(div) {
    const traces = (div?.data || []).map((trace) => {
      const x = Array.isArray(trace?.x) ? trace.x.length : 0;
      const y = Array.isArray(trace?.y) ? trace.y.length : 0;
      const z = Array.isArray(trace?.z) ? trace.z.length : 0;
      return `${trace?.type || "scatter"}:${x}:${y}:${z}`;
    }).join("|");
    return `${traces};${div?.clientWidth || 0}x${div?.clientHeight || 0}`;
  }

  function compactImageOptions(div, args) {
    const original = (args && args[1] && typeof args[1] === "object") ? args[1] : {};
    const width = Math.max(80, Math.min(360, Number(original.width) || div?.clientWidth || 360));
    const height = Math.max(80, Math.min(260, Number(original.height) || div?.clientHeight || 260));
    return {
      ...original,
      format: "png",
      filename: "__mocaviz_export_warmup__",
      width,
      height,
      scale: 1,
    };
  }

  async function warmImageExport(gd, context, args, toImageFn, timeoutMs) {
    if (typeof toImageFn !== "function") return;
    const div = plotDiv(gd);
    if (!div || !div._fullLayout) return;

    const imageArgs = Array.prototype.slice.call(args);
    imageArgs[0] = div;
    imageArgs[1] = compactImageOptions(div, imageArgs);
    try {
      await Promise.race([
        toImageFn.apply(context, imageArgs),
        timeout(timeoutMs),
      ]);
      await frame();
      await frame();
    } catch (_) {
      // The real download should still run if a hidden warm-up export fails.
    }
  }

  function originalToImageFor(owner) {
    if (owner === Plotly && typeof originalPlotlyToImage === "function") return originalPlotlyToImage;
    if (owner === Snapshot && typeof originalSnapshotToImage === "function") return originalSnapshotToImage;
    return null;
  }

  async function prewarmImageExport(gd) {
    const div = plotDiv(gd);
    if (!div || !div._fullLayout || !plotUsesWebGl(div)) return;
    const signature = imageWarmupSignature(div);
    const existing = imageWarmupByPlot.get(div);
    if (existing?.signature === signature) {
      await existing.promise;
      return;
    }

    const promise = Promise.resolve().then(async () => {
      await settlePlot(div);
      await warmImageExport(
        div,
        Plotly,
        [div, compactImageOptions(div, [div, div._context?.toImageButtonOptions || {}])],
        originalPlotlyToImage,
        8000,
      );
    });
    imageWarmupByPlot.set(div, { signature, promise });
    await promise;
  }

  function prewarmPlot(gd) {
    const div = plotDiv(gd);
    if (!div || !div._fullLayout || settlingByPlot.has(div)) return;
    window.clearTimeout(div.__mocavizExportPrewarmTimer);
    div.__mocavizExportPrewarmTimer = window.setTimeout(() => {
      if (div.isConnected) {
        settlePlot(div)
          .then(() => prewarmImageExport(div))
          .catch(() => {});
      }
    }, 100);
  }

  function wrapExport(owner, key, wrapperName) {
    if (!owner || typeof owner[key] !== "function") return;
    const original = owner[key];
    owner[key] = {
      [wrapperName]: function mocavizWrappedExport(gd) {
        const args = arguments;
        return withSettledPlot(gd, async function mocavizSettledExport() {
          if (/download/i.test(key)) {
            await warmImageExport(gd, this, args, originalToImageFor(owner), 12000);
          }
          return original.apply(this, args);
        }, this, args);
      },
    }[wrapperName];
  }

  const originalPlotlyToImage = Plotly.toImage;
  const originalSnapshotToImage = Snapshot.toImage;

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
