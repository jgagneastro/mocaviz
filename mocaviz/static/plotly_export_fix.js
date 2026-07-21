(function () {
  "use strict";

  const Plotly = window.Plotly;
  if (!Plotly || Plotly.__mocavizExportFixInstalled) return;

  function selectionPixel(axis, value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return Number.NaN;
    try {
      if (typeof axis?.d2p === "function") return Number(axis.d2p(numeric));
    } catch (_) {
      // Fall through to the range approximation.
    }
    if (!Array.isArray(axis?.range) || axis.range.length !== 2 || !Number.isFinite(Number(axis?._length))) {
      return Number.NaN;
    }
    const scaled = axis.type === "log" && numeric > 0 ? Math.log10(numeric) : numeric;
    const start = Number(axis.range[0]);
    const end = Number(axis.range[1]);
    return Number.isFinite(scaled) && Number.isFinite(start) && Number.isFinite(end) && end !== start
      ? (scaled - start) * Number(axis._length) / (end - start)
      : Number.NaN;
  }

  function isDegenerateSelection(plot, event, minSpanPx = 6, minAreaPx2 = 24) {
    const xAxis = plot?._fullLayout?.xaxis;
    const yAxis = plot?._fullLayout?.yaxis;
    const xRange = event?.range?.x;
    const yRange = event?.range?.y;
    if (Array.isArray(xRange) && xRange.length >= 2 && Array.isArray(yRange) && yRange.length >= 2) {
      const pixels = [
        selectionPixel(xAxis, xRange[0]), selectionPixel(xAxis, xRange[1]),
        selectionPixel(yAxis, yRange[0]), selectionPixel(yAxis, yRange[1]),
      ];
      if (pixels.every(Number.isFinite)) {
        return Math.abs(pixels[1] - pixels[0]) < minSpanPx
          || Math.abs(pixels[3] - pixels[2]) < minSpanPx;
      }
    }
    const lassoX = event?.lassoPoints?.x;
    const lassoY = event?.lassoPoints?.y;
    if (!Array.isArray(lassoX) && !Array.isArray(lassoY)) return false;
    if (!Array.isArray(lassoX) || !Array.isArray(lassoY)) return true;
    const points = [];
    for (let index = 0; index < Math.min(lassoX.length, lassoY.length); index += 1) {
      const x = selectionPixel(xAxis, lassoX[index]);
      const y = selectionPixel(yAxis, lassoY[index]);
      if (Number.isFinite(x) && Number.isFinite(y)) points.push([x, y]);
    }
    if (points.length < 3) return true;
    const xs = points.map((point) => point[0]);
    const ys = points.map((point) => point[1]);
    if (Math.max(...xs) - Math.min(...xs) < minSpanPx || Math.max(...ys) - Math.min(...ys) < minSpanPx) return true;
    let twiceArea = 0;
    points.forEach((point, index) => {
      const next = points[(index + 1) % points.length];
      twiceArea += point[0] * next[1] - next[0] * point[1];
    });
    return Math.abs(twiceArea) / 2 < minAreaPx2;
  }

  window.MocaPlotlySelection = Object.freeze({ isDegenerate: isDegenerateSelection });

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
