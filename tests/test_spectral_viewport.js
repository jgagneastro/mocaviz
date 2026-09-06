const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const viewport = require('../mocaviz/static/spectral_viewport.js');

test('only finite visible flux inside the wavelength window determines the range', () => {
  const traces = [
    { x: [0, 1, 2, 3, 4], y: [1000, 1, 3, null, NaN] },
    { x: [1], y: [9000], visible: 'legendonly' },
    { x: [1], y: [-9000], visible: false },
    { x: [1], y: [-9000], opacity: 0 },
    { x: [1], y: [-9000], yaxis: 'y2' },
  ];
  assert.deepEqual(viewport.visibleYRange(traces, { range: [1, 4] }, {}), [0.84, 3.16]);
  assert.deepEqual(viewport.visibleYRange(traces, { range: [4, 1] }, {}), [0.84, 3.16]);
});

test('logarithmic axes use data wavelengths and produce padded log flux bounds', () => {
  const trace = { x: [0.1, 1, 2, 3, 10, 100], y: [1e10, 10, 0, -5, 100, 1e10] };
  assert.deepEqual(viewport.visibleYRange([trace], { type: 'log', range: [0, 1] }, { type: 'log' }), [0.92, 2.08]);
});

test('visible error bars contribute, but hidden errors do not', () => {
  const trace = { x: [1], y: [10], error_y: { type: 'data', visible: true, array: [2], arrayminus: [1], symmetric: false } };
  assert.deepEqual(viewport.visibleYRange([trace], { range: [0, 2] }, {}), [8.76, 12.24]);
  trace.error_y.visible = false;
  assert.deepEqual(viewport.visibleYRange([trace], { range: [0, 2] }, {}), [9.2, 10.8]);
});

test('gaps have no inferred range; flat tiny fluxes receive proportional padding', () => {
  const trace = { x: [1, 2, 3], y: [1e-20, 1e-20, null] };
  assert.equal(viewport.visibleYRange([trace], { range: [2.1, 4] }, {}), null);
  const range = viewport.visibleYRange([trace], { range: [1, 2] }, {});
  assert.ok(range[0] > 0 && range[0] < 1e-20);
  assert.ok(range[1] > 1e-20 && range[1] < 2e-20);
});

test('page-specific robust range calculation receives only the displayed window', () => {
  const result = viewport.visibleYRange([{ x: [0, 1, 2], y: [1000, 1, 3] }], { range: [1, 2] }, {}, {
    rangeForValues(values, log) {
      assert.deepEqual(values, [1, 3]);
      assert.equal(log, false);
      return [0.5, 3.5];
    },
  });
  assert.deepEqual(result, [0.5, 3.5]);
});

test('binding is idempotent, follows zoom and trace visibility, and settles without a relayout loop', async () => {
  const frames = [];
  const originalFrame = global.requestAnimationFrame;
  global.requestAnimationFrame = callback => { frames.push(callback); return frames.length; };
  try {
    const plot = new EventEmitter();
    plot._fullLayout = { xaxis: { range: [0, 3] }, yaxis: { range: [0, 100] } };
    plot._fullData = [
      { x: [0, 1, 2], y: [100, 1, 3] },
      { x: [1], y: [20] },
    ];
    const updates = [];
    const Plotly = { relayout: async (_plot, update) => {
      updates.push(update);
      plot._fullLayout.yaxis.range = update['yaxis.range'];
      plot.emit('plotly_afterplot');
    } };
    const flush = async () => {
      for (let step = 0; frames.length && step < 10; step += 1) {
        frames.shift()();
        await new Promise(resolve => setImmediate(resolve));
      }
      assert.equal(frames.length, 0, 'range updates must settle');
    };
    viewport.bind(plot, Plotly);
    viewport.bind(plot, Plotly);
    assert.equal(plot.listenerCount('plotly_afterplot'), 1);
    await flush();
    assert.ok(plot._fullLayout.yaxis.range[1] > 100);
    plot._fullLayout.xaxis.range = [1, 2];
    plot.emit('plotly_relayout', { 'xaxis.range': [1, 2] });
    await flush();
    assert.ok(plot._fullLayout.yaxis.range[1] < 22);
    plot._fullData[1].visible = 'legendonly';
    plot.emit('plotly_restyle');
    await flush();
    assert.deepEqual(plot._fullLayout.yaxis.range, [0.84, 3.16]);
    assert.equal(updates.length, 3);
    assert.ok(updates.every(update => !Object.keys(update).some(key => key.startsWith('xaxis'))));
  } finally {
    global.requestAnimationFrame = originalFrame;
  }
});
