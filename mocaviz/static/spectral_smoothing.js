(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.mocaSpectralSmoothing = api;
})(typeof globalThis === 'undefined' ? this : globalThis, function () {
  'use strict';

  const finite = value => value !== null && value !== '' && Number.isFinite(Number(value));

  function medianSorted(values) {
    if (!values.length) return NaN;
    const middle = Math.floor(values.length / 2);
    return values.length % 2
      ? values[middle]
      : 0.5 * (values[middle - 1] + values[middle]);
  }

  function lowerBound(values, target) {
    let low = 0;
    let high = values.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (values[middle] < target) low = middle + 1;
      else high = middle;
    }
    return low;
  }

  function insertSorted(values, value) {
    if (!finite(value)) return;
    const number = Number(value);
    values.splice(lowerBound(values, number), 0, number);
  }

  function removeSorted(values, value) {
    if (!finite(value)) return;
    const number = Number(value);
    const index = lowerBound(values, number);
    if (index < values.length && values[index] === number) values.splice(index, 1);
  }

  function normalizedSmoothingWindow(value) {
    let width = Math.max(1, Math.floor(Number(value) || 1));
    if (width % 2 === 0) width += 1;
    return width;
  }

  function contiguousGroups(points, options = {}) {
    if (!points.length) return [];
    const xKey = options.xKey || 'lam';
    const gapFactor = Math.max(1, Number(options.gapFactor) || 10);
    const steps = [];
    for (let index = 1; index < points.length; index += 1) {
      const step = Number(points[index]?.[xKey]) - Number(points[index - 1]?.[xKey]);
      if (Number.isFinite(step) && step > 0) steps.push(step);
    }
    steps.sort((left, right) => left - right);
    const typicalStep = medianSorted(steps);
    const gapLimit = Number.isFinite(typicalStep) && typicalStep > 0
      ? gapFactor * typicalStep
      : Infinity;
    const groups = [];
    let current = [points[0]];
    for (let index = 1; index < points.length; index += 1) {
      const step = Number(points[index]?.[xKey]) - Number(points[index - 1]?.[xKey]);
      if (!Number.isFinite(step) || step <= 0 || step > gapLimit) {
        groups.push(current);
        current = [];
      }
      current.push(points[index]);
    }
    if (current.length) groups.push(current);
    return groups;
  }

  function smoothGroup(points, width, options = {}) {
    if (!points.length) return [];
    const yKey = options.yKey || 'y';
    const count = Math.min(width, points.length);
    const radius = Math.floor(count / 2);
    const maxStart = points.length - count;
    const sorted = [];
    for (let index = 0; index < count; index += 1) insertSorted(sorted, points[index]?.[yKey]);
    let windowStart = 0;
    return points.map((point, index) => {
      const desiredStart = Math.max(0, Math.min(index - radius, maxStart));
      while (windowStart < desiredStart) {
        removeSorted(sorted, points[windowStart]?.[yKey]);
        insertSorted(sorted, points[windowStart + count]?.[yKey]);
        windowStart += 1;
      }
      const level = medianSorted(sorted);
      if (!finite(level)) return { ...point };
      const custom = point?.custom && typeof point.custom === 'object'
        ? { ...point.custom, [yKey]: level, robustSmoothed: true, smoothingPixels: width }
        : point?.custom;
      return { ...point, [yKey]: level, ...(custom ? { custom } : {}) };
    });
  }

  function robustMedianSmoothPoints(points, windowSize = 1, options = {}) {
    const input = Array.isArray(points) ? points : [];
    const width = normalizedSmoothingWindow(windowSize);
    if (width === 1 || input.length < 2) return input.slice();
    return contiguousGroups(input, options)
      .flatMap(group => smoothGroup(group, width, options));
  }

  return Object.freeze({
    contiguousGroups,
    normalizedSmoothingWindow,
    robustMedianSmoothPoints,
  });
});
