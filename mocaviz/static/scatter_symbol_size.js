(() => {
  "use strict";

  const inputSelector = "[data-scatter-symbol-size]";
  const outputSelector = "[data-scatter-symbol-size-output]";
  const defaultPercent = 100;
  const traceBaselines = new WeakMap();
  const graphBaselines = new WeakMap();
  const threeMaterials = new Map();
  let originalRestyle = null;
  let inputFrame = 0;

  function symbolPercent() {
    const value = Number(document.querySelector(inputSelector)?.value);
    return Number.isFinite(value) && value > 0 ? value : defaultPercent;
  }

  function symbolScale() {
    return symbolPercent() / defaultPercent;
  }

  function copySize(size) {
    return Array.isArray(size) ? size.map(copySize) : size;
  }

  function scaledSize(size, scale = symbolScale()) {
    if (Array.isArray(size)) return size.map((item) => scaledSize(item, scale));
    const value = Number(size);
    return Number.isFinite(value) ? Math.max(0.1, value * scale) : size;
  }

  function markerTrace(trace) {
    const type = String(trace?.type || "scatter").toLowerCase();
    const mode = String(trace?.mode || "").toLowerCase();
    return (type === "scatter" || type === "scattergl" || type === "scatter3d")
      && mode.includes("markers")
      && trace?.marker?.size !== undefined;
  }

  function traceBaseline(trace) {
    if (!markerTrace(trace)) return null;
    const cached = traceBaselines.get(trace);
    if (cached) return cached;
    const baseline = {
      marker: copySize(trace.marker.size),
      selected: trace.selected?.marker?.size === undefined
        ? undefined
        : copySize(trace.selected.marker.size),
      unselected: trace.unselected?.marker?.size === undefined
        ? undefined
        : copySize(trace.unselected.marker.size),
    };
    traceBaselines.set(trace, baseline);
    return baseline;
  }

  function scaleTrace(trace, baseline, scale) {
    if (!baseline) return;
    trace.marker.size = scaledSize(baseline.marker, scale);
    if (baseline.selected !== undefined) {
      trace.selected = trace.selected || {};
      trace.selected.marker = trace.selected.marker || {};
      trace.selected.marker.size = scaledSize(baseline.selected, scale);
    }
    if (baseline.unselected !== undefined) {
      trace.unselected = trace.unselected || {};
      trace.unselected.marker = trace.unselected.marker || {};
      trace.unselected.marker.size = scaledSize(baseline.unselected, scale);
    }
  }

  function preparePlot(graph, traces) {
    if (!Array.isArray(traces)) return;
    const scale = symbolScale();
    const baselines = traces.map((trace) => {
      const baseline = traceBaseline(trace);
      scaleTrace(trace, baseline, scale);
      return baseline;
    });
    const graphElement = resolveGraph(graph);
    if (graphElement) graphBaselines.set(graphElement, baselines);
  }

  function normalizeTraceIndexes(graph, indexes) {
    if (Array.isArray(indexes)) return indexes.map(Number).filter(Number.isInteger);
    if (Number.isInteger(Number(indexes))) return [Number(indexes)];
    return Array.from({ length: graph?.data?.length || 0 }, (_value, index) => index);
  }

  function restyleValue(values, position, traceCount) {
    if (!Array.isArray(values)) return values;
    if (traceCount > 1) return values[position];
    return values.length === 1 ? values[0] : values;
  }

  function prepareRestyle(graph, update, indexes) {
    const graphElement = resolveGraph(graph);
    if (!graphElement || !update || typeof update !== "object") return;
    const traceIndexes = normalizeTraceIndexes(graphElement, indexes);
    if (!traceIndexes.length) return;
    const baselines = graphBaselines.get(graphElement) || [];
    const scale = symbolScale();

    if (Object.prototype.hasOwnProperty.call(update, "marker")) {
      const markers = traceIndexes.map((_traceIndex, position) => (
        restyleValue(update.marker, position, traceIndexes.length)
      ));
      const markerSizes = markers.map((marker) => (
        marker?.size === undefined ? undefined : copySize(marker.size)
      ));
      markers.forEach((marker, position) => {
        if (!marker || markerSizes[position] === undefined) return;
        const traceIndex = traceIndexes[position];
        const baseline = baselines[traceIndex] || {};
        baseline.marker = markerSizes[position];
        baselines[traceIndex] = baseline;
        marker.size = scaledSize(baseline.marker, scale);
      });
      update.marker = markers;
    }

    for (const [key, baselineKey] of [
      ["marker.size", "marker"],
      ["selected.marker.size", "selected"],
      ["unselected.marker.size", "unselected"],
    ]) {
      if (!Object.prototype.hasOwnProperty.call(update, key)) continue;
      const sizes = traceIndexes.map((_traceIndex, position) => (
        restyleValue(update[key], position, traceIndexes.length)
      ));
      update[key] = sizes.map((size, position) => {
        const traceIndex = traceIndexes[position];
        const baseline = baselines[traceIndex] || {};
        baseline[baselineKey] = copySize(size);
        baselines[traceIndex] = baseline;
        return scaledSize(size, scale);
      });
    }
    graphBaselines.set(graphElement, baselines);
  }

  function prepareAddedTraces(graph, traces, indexes) {
    const graphElement = resolveGraph(graph);
    if (!graphElement) return;
    const incoming = Array.isArray(traces) ? traces : [traces];
    const scale = symbolScale();
    const incomingBaselines = incoming.map((trace) => {
      const baseline = traceBaseline(trace);
      scaleTrace(trace, baseline, scale);
      return baseline;
    });
    const baselines = graphBaselines.get(graphElement) || [];
    const requested = Array.isArray(indexes)
      ? indexes.map(Number)
      : Number.isInteger(Number(indexes))
        ? [Number(indexes)]
        : [];
    incomingBaselines.forEach((baseline, position) => {
      const requestedIndex = requested[position];
      const index = Number.isInteger(requestedIndex)
        ? Math.max(0, Math.min(requestedIndex, baselines.length))
        : baselines.length;
      baselines.splice(index, 0, baseline);
    });
    graphBaselines.set(graphElement, baselines);
  }

  function removeTraceBaselines(graph, indexes) {
    const graphElement = resolveGraph(graph);
    if (!graphElement) return;
    const baselines = graphBaselines.get(graphElement);
    if (!baselines) return;
    normalizeTraceIndexes(graphElement, indexes)
      .sort((left, right) => right - left)
      .forEach((index) => baselines.splice(index, 1));
  }

  function resolveGraph(graph) {
    if (typeof graph === "string") return document.getElementById(graph);
    return graph?.nodeType === 1 ? graph : null;
  }

  function installPlotlyHooks() {
    if (!window.Plotly || window.Plotly.__mocaScatterSymbolSizeInstalled) return;
    const plotly = window.Plotly;
    originalRestyle = plotly.restyle.bind(plotly);
    for (const method of ["newPlot", "react"]) {
      const original = plotly[method]?.bind(plotly);
      if (!original) continue;
      plotly[method] = (graph, traces, ...args) => {
        preparePlot(graph, traces);
        return original(graph, traces, ...args);
      };
    }
    plotly.restyle = (graph, update, indexes) => {
      prepareRestyle(graph, update, indexes);
      return originalRestyle(graph, update, indexes);
    };
    const originalAddTraces = plotly.addTraces?.bind(plotly);
    if (originalAddTraces) {
      plotly.addTraces = (graph, traces, indexes) => {
        prepareAddedTraces(graph, traces, indexes);
        return originalAddTraces(graph, traces, indexes);
      };
    }
    const originalDeleteTraces = plotly.deleteTraces?.bind(plotly);
    if (originalDeleteTraces) {
      plotly.deleteTraces = (graph, indexes) => {
        removeTraceBaselines(graph, indexes);
        return originalDeleteTraces(graph, indexes);
      };
    }
    plotly.__mocaScatterSymbolSizeInstalled = true;
  }

  function applyPlotlyScale() {
    if (!originalRestyle) return;
    const scale = symbolScale();
    for (const graph of document.querySelectorAll(".js-plotly-plot")) {
      const baselines = graphBaselines.get(graph);
      if (!baselines) continue;
      baselines.forEach((baseline, index) => {
        if (!baseline) return;
        const update = { "marker.size": [scaledSize(baseline.marker, scale)] };
        if (baseline.selected !== undefined) {
          update["selected.marker.size"] = [scaledSize(baseline.selected, scale)];
        }
        if (baseline.unselected !== undefined) {
          update["unselected.marker.size"] = [scaledSize(baseline.unselected, scale)];
        }
        const result = originalRestyle(graph, update, [index]);
        if (result?.catch) result.catch(() => null);
      });
    }
  }

  function registerThreeMaterial(material, baseSize = material?.size) {
    const size = Number(baseSize);
    if (!material || !Number.isFinite(size)) return material;
    threeMaterials.set(material, size);
    material.size = scaledSize(size);
    material.needsUpdate = true;
    return material;
  }

  function unregisterThreeMaterial(material) {
    threeMaterials.delete(material);
  }

  function applyThreeScale() {
    const scale = symbolScale();
    for (const [material, baseSize] of threeMaterials) {
      material.size = scaledSize(baseSize, scale);
      material.needsUpdate = true;
    }
  }

  function syncOutput() {
    const output = document.querySelector(outputSelector);
    if (output) output.textContent = `${Math.round(symbolPercent())}%`;
  }

  function applyAllScales() {
    syncOutput();
    applyPlotlyScale();
    applyThreeScale();
    document.dispatchEvent(new CustomEvent("scatter-symbol-size-change", {
      detail: { percent: symbolPercent(), scale: symbolScale() },
    }));
  }

  function handleInput() {
    syncOutput();
    if (inputFrame) cancelAnimationFrame(inputFrame);
    inputFrame = requestAnimationFrame(() => {
      inputFrame = 0;
      applyAllScales();
    });
  }

  function initializeControl() {
    const input = document.querySelector(inputSelector);
    if (!input || input.dataset.scatterSymbolSizeReady === "1") return;
    input.dataset.scatterSymbolSizeReady = "1";
    input.addEventListener("input", handleInput);
    input.addEventListener("change", applyAllScales);
    syncOutput();
  }

  installPlotlyHooks();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeControl, { once: true });
  } else {
    initializeControl();
  }

  window.ScatterSymbolSize = {
    getPercent: symbolPercent,
    getScale: symbolScale,
    scaleSize: scaledSize,
    registerThreeMaterial,
    unregisterThreeMaterial,
  };
})();
