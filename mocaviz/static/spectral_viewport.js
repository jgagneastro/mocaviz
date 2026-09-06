(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.mocaSpectralViewport = api;
})(typeof globalThis === 'undefined' ? this : globalThis, function () {
  'use strict';

  const finite = value => value !== null && value !== '' && Number.isFinite(Number(value));
  const bindings = new WeakMap();

  // Axis ranges use log10 coordinates in Plotly; trace samples remain in data units.
  function visibleYRange(traces, xaxis, yaxis, options = {}) {
    if (!xaxis?.range?.every(finite)) return null;
    const xRange = xaxis.range.map(value => xaxis.type === 'log' ? 10 ** value : Number(value));
    const low = Math.min(...xRange);
    const high = Math.max(...xRange);
    const log = yaxis?.type === 'log';
    const values = [];
    const add = value => {
      if (finite(value) && (!log || Number(value) > 0)) values.push(Number(value));
    };
    for (const trace of traces || []) {
      if (trace.visible === false || trace.visible === 'legendonly' || trace.opacity === 0) continue;
      if ((trace.xaxis && trace.xaxis !== 'x') || (trace.yaxis && trace.yaxis !== 'y')) continue;
      const error = trace.error_y;
      for (let index = 0; index < Math.min(trace.x?.length || 0, trace.y?.length || 0); index += 1) {
        const x = trace.x[index];
        const y = trace.y[index];
        if (!finite(x) || !finite(y) || x < low || x > high) continue;
        add(y);
        if (error?.visible && error.type === 'data') {
          const plus = error.array?.[index] ?? error.value;
          const minus = error.symmetric === false ? (error.arrayminus?.[index] ?? error.valueminus) : plus;
          if (finite(plus) && plus >= 0) add(Number(y) + Number(plus));
          if (finite(minus) && minus >= 0) add(Number(y) - Number(minus));
        }
      }
    }
    // In an empty wavelength gap retain the last valid range, never invent flux.
    if (!values.length) return null;
    const customRange = options.rangeForValues?.(values, log);
    if (customRange) return customRange;
    let min = Infinity;
    let max = -Infinity;
    for (const value of values) {
      const scaled = log ? Math.log10(value) : value;
      min = Math.min(min, scaled);
      max = Math.max(max, scaled);
    }
    const fraction = options.padFraction ?? 0.08;
    const pad = log
      ? Math.max(0.015, (max - min) * fraction)
      : Math.max((max - min) * fraction, Math.abs(max || min) * (max === min ? fraction : 1e-6), 1e-300);
    return [min - pad, max + pad];
  }

  function sameRange(left, right) {
    if (!left || !right) return false;
    const tolerance = Math.max(...right.map(Math.abs), Math.abs(right[1] - right[0]), 1e-300) * 1e-10;
    return left.length === 2 && left.every((value, index) => Math.abs(value - right[index]) <= tolerance);
  }

  function bind(plot, Plotly, options = {}) {
    if (!plot || typeof plot.on !== 'function') return;
    const existing = bindings.get(plot);
    if (existing) {
      existing.options = options;
      existing.schedule();
      return;
    }
    const state = { options, frame: null, updating: false };
    const schedule = () => {
      if (state.frame !== null) return;
      state.frame = requestAnimationFrame(() => {
        state.frame = null;
        if (state.updating) return;
        const layout = plot._fullLayout;
        if (!layout) return;
        const range = visibleYRange(plot._fullData || plot.data, layout.xaxis, layout.yaxis, state.options);
        if (!range || sameRange(layout.yaxis?.range, range)) return;
        state.updating = true;
        Promise.resolve().then(() => Plotly.relayout(plot, {
          'yaxis.autorange': false,
          'yaxis.range': range,
          ...(state.options.yTicks?.(range) || {}),
        })).then(() => {
          state.updating = false;
          // Catch a newer zoom/render that arrived while relayout was running.
          schedule();
        }).catch(error => {
          state.updating = false;
          console.warn('Unable to fit the visible spectral flux range', error);
        });
      });
    };
    state.schedule = schedule;
    bindings.set(plot, state);
    plot.on('plotly_afterplot', schedule);
    plot.on('plotly_relayout', schedule);
    plot.on('plotly_restyle', schedule);
    schedule();
  }

  return Object.freeze({ bind, visibleYRange });
});
