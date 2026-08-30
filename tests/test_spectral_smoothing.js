'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  normalizedSmoothingWindow,
  robustMedianSmoothPoints,
} = require('../mocaviz/static/spectral_smoothing.js');

test('robust spectral smoothing rejects an isolated outlier', () => {
  const points = [1, 1, 1000, 1, 1].map((y, index) => ({
    lam: index + 1,
    y,
    custom: { y, rowIndex: index },
  }));
  const smoothed = robustMedianSmoothPoints(points, 5);
  assert.deepEqual(smoothed.map(point => point.y), [1, 1, 1, 1, 1]);
  assert.deepEqual(smoothed.map(point => point.custom.y), [1, 1, 1, 1, 1]);
  assert.equal(points[2].y, 1000, 'input points must remain unchanged');
  assert.ok(smoothed.every(point => point.custom.robustSmoothed && point.custom.smoothingPixels === 5));
});

test('robust spectral smoothing keeps wavelength gaps separate', () => {
  const points = [
    { lam: 1, y: 0 }, { lam: 2, y: 0 }, { lam: 3, y: 0 },
    { lam: 100, y: 10 }, { lam: 101, y: 10 }, { lam: 102, y: 10 },
  ];
  assert.deepEqual(
    robustMedianSmoothPoints(points, 5).map(point => point.y),
    [0, 0, 0, 10, 10, 10],
  );
});

test('one pixel is off and even inputs normalize to the next odd window', () => {
  const points = [{ lam: 1, y: 2 }, { lam: 2, y: 3 }];
  const unchanged = robustMedianSmoothPoints(points, 1);
  assert.deepEqual(unchanged, points);
  assert.notEqual(unchanged, points);
  assert.equal(normalizedSmoothingWindow(4), 5);
});
