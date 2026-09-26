(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SpectrumMath = api;
})(typeof globalThis === 'undefined' ? this : globalThis, function () {
  'use strict';

  const SPEED_OF_LIGHT_KMS = 299_792.458;
  const finite = value => value !== null && value !== '' && Number.isFinite(Number(value));

  function median(values) {
    const sorted = values.filter(finite).map(Number).sort((a, b) => a - b);
    if (!sorted.length) return NaN;
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2
      ? sorted[middle]
      : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function quantile(values, fraction) {
    const sorted = values.filter(finite).map(Number).sort((a, b) => a - b);
    if (!sorted.length) return NaN;
    const position = Math.max(0, Math.min(1, fraction)) * (sorted.length - 1);
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    if (lower === upper) return sorted[lower];
    const weight = position - lower;
    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
  }

  function medianBoxSummary(points) {
    const values = points.map(point => point[1]).filter(finite).map(Number);
    if (!values.length) return { trend: [], sigma: NaN };
    if (values.length < 11) return { trend: values, sigma: 0 };

    // About 60 flux-resolution boxes across the visible wavelength range. The
    // overlapping samples retain broad molecular-band peaks without following
    // individual noisy pixels or narrow outliers.
    let boxWidth = Math.max(11, Math.floor(values.length / 60));
    if (boxWidth % 2 === 0) boxWidth += 1;
    if (boxWidth > values.length) boxWidth = values.length - (values.length + 1) % 2;
    const radius = Math.floor(boxWidth / 2);
    const sampleCount = Math.min(161, values.length);
    const trend = [];
    const localMads = [];

    for (let sample = 0; sample < sampleCount; sample += 1) {
      const center = sampleCount === 1
        ? 0
        : Math.round(sample * (values.length - 1) / (sampleCount - 1));
      const box = values.slice(
        Math.max(0, center - radius),
        Math.min(values.length, center + radius + 1),
      );
      const level = median(box);
      if (!finite(level)) continue;
      trend.push(level);
      localMads.push(median(box.map(value => Math.abs(value - level))));
    }

    return {
      trend,
      sigma: 1.4826 * median(localMads),
    };
  }

  function windowBounds(length, index, width) {
    const count = Math.min(width, length);
    const radius = Math.floor(count / 2);
    const first = Math.max(0, Math.min(index - radius, length - count));
    return [first, first + count];
  }

  function solveLinearSystem(matrix, vector) {
    const size = vector.length;
    const augmented = matrix.map((row, index) => [...row, vector[index]]);
    for (let column = 0; column < size; column += 1) {
      let pivot = column;
      for (let row = column + 1; row < size; row += 1) {
        if (Math.abs(augmented[row][column]) > Math.abs(augmented[pivot][column])) pivot = row;
      }
      if (!(Math.abs(augmented[pivot][column]) > 1e-12)) return null;
      [augmented[column], augmented[pivot]] = [augmented[pivot], augmented[column]];
      const divisor = augmented[column][column];
      for (let item = column; item <= size; item += 1) augmented[column][item] /= divisor;
      for (let row = 0; row < size; row += 1) {
        if (row === column) continue;
        const factor = augmented[row][column];
        for (let item = column; item <= size; item += 1) {
          augmented[row][item] -= factor * augmented[column][item];
        }
      }
    }
    return augmented.map(row => row[size]);
  }

  function localRobustWeights(values, width, tuning = 4.685, hardCutoff = false) {
    return values.map((value, index) => {
      if (!finite(value)) return 0;
      const [first, last] = windowBounds(values.length, index, width);
      const window = values.slice(first, last).filter(finite).map(Number);
      const center = median(window);
      const deviations = window.map(item => Math.abs(item - center));
      const scale = 1.4826 * median(deviations);
      const tolerance = 64 * Number.EPSILON
        * Math.max(1, ...window.map(item => Math.abs(item)));
      const deviation = Math.abs(Number(value) - center);
      if (!(scale > tolerance)) return deviation <= tolerance ? 1 : 0;
      const ratio = deviation / (Math.max(1, Number(tuning) || 4.685) * scale);
      if (!(ratio < 1)) return 0;
      if (hardCutoff) return 1;
      return (1 - ratio * ratio) ** 2;
    });
  }

  function localPolynomialSmooth(points, width, weights) {
    return points.map((point, index) => {
      const [first, last] = windowBounds(points.length, index, width);
      const targetX = Number(point?.[0]);
      const samples = [];
      for (let sampleIndex = first; sampleIndex < last; sampleIndex += 1) {
        const x = Number(points[sampleIndex]?.[0]);
        const y = Number(points[sampleIndex]?.[1]);
        const weight = Number(weights[sampleIndex]);
        if (Number.isFinite(x) && Number.isFinite(y) && weight > 0) {
          samples.push({ x, y, weight });
        }
      }
      if (!Number.isFinite(targetX) || !samples.length) return Number(point?.[1]);
      const scaleX = Math.max(1e-12, ...samples.map(sample => Math.abs(sample.x - targetX)));
      let order = Math.min(width >= 5 ? 2 : 1, samples.length - 1);
      while (order >= 0) {
        const matrix = Array.from({ length: order + 1 }, () => Array(order + 1).fill(0));
        const vector = Array(order + 1).fill(0);
        for (const sample of samples) {
          const coordinate = (sample.x - targetX) / scaleX;
          const powers = Array(2 * order + 1).fill(1);
          for (let power = 1; power < powers.length; power += 1) {
            powers[power] = powers[power - 1] * coordinate;
          }
          for (let row = 0; row <= order; row += 1) {
            vector[row] += sample.weight * sample.y * powers[row];
            for (let column = 0; column <= order; column += 1) {
              matrix[row][column] += sample.weight * powers[row + column];
            }
          }
        }
        const coefficients = solveLinearSystem(matrix, vector);
        if (coefficients && finite(coefficients[0])) return coefficients[0];
        order -= 1;
      }
      return Number(point?.[1]);
    });
  }

  function robustPolynomialSegment(points, width) {
    if (points.length < 2) return points.map(point => Number(point?.[1]));
    const values = points.map(point => Number(point?.[1]));
    const seedWeights = localRobustWeights(values, width, 6, true);
    let weights = seedWeights;
    let fitted = localPolynomialSmooth(points, width, weights);
    for (let iteration = 0; iteration < 2; iteration += 1) {
      const residuals = values.map((value, index) => value - fitted[index]);
      const residualWeights = localRobustWeights(residuals, width);
      const nextWeights = seedWeights.map((weight, index) => weight * residualWeights[index]);
      if (nextWeights.filter(weight => weight > 0).length < 2) break;
      weights = nextWeights;
      fitted = localPolynomialSmooth(points, width, weights);
    }
    return fitted;
  }

  function robustSmooth(points, windowSize = 1) {
    const input = Array.isArray(points) ? points : [];
    let width = Math.max(1, Math.floor(Number(windowSize) || 1));
    if (width % 2 === 0) width += 1;
    if (width === 1 || input.length < 2) return input.map(point => [...point]);

    const steps = [];
    for (let index = 1; index < input.length; index += 1) {
      const step = Number(input[index]?.[0]) - Number(input[index - 1]?.[0]);
      if (Number.isFinite(step) && step > 0) steps.push(step);
    }
    const typicalStep = median(steps);
    const gapLimit = Number.isFinite(typicalStep) && typicalStep > 0
      ? 8 * typicalStep
      : Infinity;
    const output = input.map(point => [...point]);

    let segmentStart = 0;
    for (let boundary = 1; boundary <= input.length; boundary += 1) {
      const step = boundary < input.length
        ? Number(input[boundary]?.[0]) - Number(input[boundary - 1]?.[0])
        : Infinity;
      const split = boundary === input.length
        || !Number.isFinite(step)
        || step <= 0
        || step > gapLimit;
      if (!split) continue;
      const segment = input.slice(segmentStart, boundary);
      const fitted = robustPolynomialSegment(segment, Math.min(width, segment.length));
      for (let index = segmentStart; index < boundary; index += 1) {
        if (finite(fitted[index - segmentStart])) output[index][1] = fitted[index - segmentStart];
      }
      segmentStart = boundary;
    }
    return output;
  }

  function medianSmooth(points, windowSize = 1) {
    const input = Array.isArray(points) ? points : [];
    let width = Math.max(1, Math.floor(Number(windowSize) || 1));
    if (width % 2 === 0) width += 1;
    if (width === 1 || input.length < 2) return input.map(point => [...point]);

    const steps = [];
    for (let index = 1; index < input.length; index += 1) {
      const step = Number(input[index]?.[0]) - Number(input[index - 1]?.[0]);
      if (Number.isFinite(step) && step > 0) steps.push(step);
    }
    const typicalStep = median(steps);
    const gapLimit = Number.isFinite(typicalStep) && typicalStep > 0
      ? 8 * typicalStep
      : Infinity;
    const output = input.map(point => [...point]);

    let segmentStart = 0;
    for (let boundary = 1; boundary <= input.length; boundary += 1) {
      const step = boundary < input.length
        ? Number(input[boundary]?.[0]) - Number(input[boundary - 1]?.[0])
        : Infinity;
      const split = boundary === input.length
        || !Number.isFinite(step)
        || step <= 0
        || step > gapLimit;
      if (!split) continue;
      const count = Math.min(width, boundary - segmentStart);
      const radius = Math.floor(count / 2);
      for (let index = segmentStart; index < boundary; index += 1) {
        const first = Math.max(segmentStart, Math.min(index - radius, boundary - count));
        const level = median(input.slice(first, first + count).map(point => point?.[1]));
        if (finite(level)) output[index][1] = level;
      }
      segmentStart = boundary;
    }
    return output;
  }

  function minmaxDownsample(points, maxPoints) {
    const input = Array.isArray(points) ? points : [];
    const requested = Math.floor(Number(maxPoints));
    const limit = Number.isFinite(requested) && requested > 1
      ? requested
      : input.length;
    if (input.length <= limit) return input.map(point => [...point]);
    const interior = input.slice(1, -1);
    const bucketCount = Math.max(1, Math.floor((limit - 2) / 2));
    const result = [[...input[0]]];
    for (let bucket = 0; bucket < bucketCount; bucket += 1) {
      const first = Math.floor(bucket * interior.length / bucketCount);
      const last = Math.floor((bucket + 1) * interior.length / bucketCount);
      const part = interior.slice(first, last);
      if (!part.length) continue;
      let minimum = 0;
      let maximum = 0;
      for (let index = 1; index < part.length; index += 1) {
        if (Number(part[index]?.[1]) < Number(part[minimum]?.[1])) minimum = index;
        if (Number(part[index]?.[1]) > Number(part[maximum]?.[1])) maximum = index;
      }
      for (const index of [...new Set([minimum, maximum])].sort((a, b) => a - b)) {
        result.push([...part[index]]);
      }
    }
    result.push([...input[input.length - 1]]);
    return result.slice(0, limit);
  }

  function logarithmicPixelVelocity(points) {
    const input = Array.isArray(points) ? points : [];
    const logSteps = [];
    for (let index = 1; index < input.length; index += 1) {
      const previous = Number(input[index - 1]?.[0]);
      const current = Number(input[index]?.[0]);
      const step = previous > 0 && current > previous
        ? Math.log(current / previous)
        : NaN;
      if (Number.isFinite(step) && step > 0) logSteps.push(step);
    }
    const typicalStep = median(logSteps);
    const supportedSteps = logSteps.filter(step =>
      Number.isFinite(typicalStep) && typicalStep > 0 && step <= 8 * typicalStep
    );
    const adoptedStep = median(supportedSteps.length ? supportedSteps : logSteps);
    return Number.isFinite(adoptedStep) && adoptedStep > 0
      ? SPEED_OF_LIGHT_KMS * adoptedStep
      : NaN;
  }

  function nativeVelocityResolution(
    points,
    resolvingPower,
    pixPerResolutionElement = 2.2,
  ) {
    const power = Number(resolvingPower);
    if (power > 0 && Number.isFinite(power)) {
      return SPEED_OF_LIGHT_KMS / power;
    }
    let sampling = Number(pixPerResolutionElement);
    if (!(sampling > 0) || !Number.isFinite(sampling)) sampling = 2.2;
    const pixelVelocity = logarithmicPixelVelocity(points);
    return Number.isFinite(pixelVelocity) && pixelVelocity > 0
      ? sampling * pixelVelocity
      : NaN;
  }

  function targetVelocityWindow(
    points,
    targetVelocityKms,
    resolvingPower,
    pixPerResolutionElement = 2.2,
  ) {
    const input = Array.isArray(points) ? points : [];
    const target = Math.max(0, Number(targetVelocityKms) || 0);
    if (!(target > 0) || input.length < 3) return 1;

    let sampling = Number(pixPerResolutionElement);
    if (!(sampling > 0) || !Number.isFinite(sampling)) sampling = 2.2;
    const nativeVelocity = nativeVelocityResolution(
      input,
      resolvingPower,
      sampling,
    );
    if (Number.isFinite(nativeVelocity) && target <= nativeVelocity) return 1;

    let pixelVelocity = logarithmicPixelVelocity(input);
    if (!(pixelVelocity > 0) && Number.isFinite(nativeVelocity)) {
      pixelVelocity = nativeVelocity / sampling;
    }
    if (!(pixelVelocity > 0)) return 1;

    const appliedVelocity = Number.isFinite(nativeVelocity)
      ? Math.sqrt(Math.max(0, target * target - nativeVelocity * nativeVelocity))
      : target;
    if (!(appliedVelocity > 0)) return 1;

    // A width of N samples spans N - 1 pixel intervals.  Choose the nearest
    // even interval count so the resulting local-polynomial window stays odd
    // and centred.  The quadrature width adds only the broadening needed to
    // reach the requested target velocity resolution from this trace's native
    // c/R; lower-resolution traces therefore remain unchanged until needed.
    const intervalCount = Math.max(
      2,
      2 * Math.round(appliedVelocity / pixelVelocity / 2),
    );
    const width = intervalCount + 1;
    const maximumOdd = input.length % 2 === 1 ? input.length : input.length - 1;
    return Math.max(1, Math.min(width, maximumOdd));
  }

  function smoothNativeForDisplay(
    points,
    targetVelocityKms,
    resolvingPower,
    pixPerResolutionElement,
    maxPoints,
  ) {
    const width = targetVelocityWindow(
      points,
      targetVelocityKms,
      resolvingPower,
      pixPerResolutionElement,
    );
    const nativeResolutionKms = nativeVelocityResolution(
      points,
      resolvingPower,
      pixPerResolutionElement,
    );
    return {
      points: minmaxDownsample(robustSmooth(points, width), maxPoints),
      windowSize: width,
      nativeResolutionKms,
      appliedVelocityKms: Number.isFinite(nativeResolutionKms)
        ? Math.sqrt(Math.max(
          0,
          Number(targetVelocityKms) ** 2 - nativeResolutionKms ** 2,
        ))
        : Math.max(0, Number(targetVelocityKms) || 0),
    };
  }

  function consumeSwipeDelta(remainder, delta, threshold = 18) {
    const limit = Math.max(1, Math.abs(Number(threshold) || 18));
    const total = (finite(remainder) ? Number(remainder) : 0)
      + (finite(delta) ? Number(delta) : 0);
    const steps = Math.trunc(total / limit);
    return {
      steps,
      remainder: total - steps * limit,
    };
  }

  function steppedRangeValue(value, steps, min = 0, max = 100, step = 1) {
    const lower = Math.min(Number(min), Number(max));
    const upper = Math.max(Number(min), Number(max));
    const increment = Math.abs(Number(step)) || 1;
    if (!Number.isFinite(lower) || !Number.isFinite(upper)) return Number(value);
    const current = finite(value) ? Number(value) : lower;
    const currentIndex = Math.round((current - lower) / increment);
    const maximumIndex = Math.floor((upper - lower) / increment + 1e-9);
    const nextIndex = Math.max(0, Math.min(
      maximumIndex,
      currentIndex + Math.trunc(Number(steps) || 0),
    ));
    return lower + nextIndex * increment;
  }

  function niceVelocityStep(value) {
    const requested = Math.max(1, Number(value) || 1);
    const magnitude = 10 ** Math.floor(Math.log10(requested));
    const normalized = requested / magnitude;
    const multiplier = normalized < 1.5 ? 1 : normalized < 3.5 ? 2 : normalized < 7.5 ? 5 : 10;
    return Math.max(1, multiplier * magnitude);
  }

  function adaptiveVelocityRange(nativeVelocities) {
    const velocities = (Array.isArray(nativeVelocities) ? nativeVelocities : [])
      .map(Number)
      .filter(value => Number.isFinite(value) && value > 0)
      .sort((left, right) => left - right);
    if (!velocities.length) return { startKms: 10, maxKms: 5_000, stepKms: 10 };

    // The highest-R trace has the smallest c/R and is the first one that can
    // benefit from smoothing.  Keep Off at zero, but make the first active
    // value its rounded native threshold.  The upper range covers either
    // twenty times that finest resolution or twice the broadest displayed
    // trace, without making high-R-only views needlessly enormous.
    const finest = velocities[0];
    const broadest = velocities[velocities.length - 1];
    const stepKms = niceVelocityStep(finest / 20);
    const startKms = (Math.floor(finest / stepKms) + 1) * stepKms;
    const requestedMaximum = Math.max(
      500,
      Math.min(5_000, 20 * finest),
      2 * broadest,
    );
    const maxKms = Math.max(
      startKms + stepKms,
      Math.ceil(requestedMaximum / stepKms) * stepKms,
    );
    return { startKms, maxKms, stepKms };
  }

  function steppedVelocityValue(value, steps, range) {
    const start = Math.max(0, Number(range?.startKms) || 0);
    const maximum = Math.max(start, Number(range?.maxKms) || start);
    const increment = Math.max(1, Number(range?.stepKms) || 1);
    const current = Math.max(0, Number(value) || 0);
    const count = Math.trunc(Number(steps) || 0);
    if (count > 0 && current < start) {
      return Math.min(maximum, start + (count - 1) * increment);
    }
    if (count < 0 && current <= start) return 0;
    return steppedRangeValue(current, count, 0, maximum, increment);
  }

  function significantWavelengthBounds(points, minimumSegmentFraction = 0.05) {
    const wavelengths = (Array.isArray(points) ? points : [])
      .filter(point => Array.isArray(point) && finite(point[0]) && finite(point[1]))
      .map(point => Number(point[0]))
      .sort((left, right) => left - right);
    if (!wavelengths.length) return null;
    if (wavelengths.length === 1) return [wavelengths[0], wavelengths[0]];

    const steps = [];
    for (let index = 1; index < wavelengths.length; index += 1) {
      const step = wavelengths[index] - wavelengths[index - 1];
      if (step > 0) steps.push(step);
    }
    const totalSpan = wavelengths.at(-1) - wavelengths[0];
    const typicalStep = median(steps);
    const gapThreshold = Math.max(
      finite(typicalStep) ? 50 * typicalStep : 0,
      0.01 * totalSpan,
    );
    const segments = [];
    let first = 0;
    for (let index = 1; index < wavelengths.length; index += 1) {
      if (wavelengths[index] - wavelengths[index - 1] > gapThreshold) {
        segments.push(wavelengths.slice(first, index));
        first = index;
      }
    }
    segments.push(wavelengths.slice(first));

    // Tiny, disconnected edge islands are commonly order fragments rather
    // than useful plotted coverage. They must not keep an otherwise empty
    // wavelength region open.
    const fraction = Math.max(0, Math.min(1, Number(minimumSegmentFraction) || 0));
    const minimumSamples = Math.max(2, Math.ceil(fraction * wavelengths.length));
    let retained = segments.filter(segment => segment.length >= minimumSamples);
    if (!retained.length) {
      retained = [segments.reduce((largest, segment) => (
        segment.length > largest.length ? segment : largest
      ), segments[0])];
    }
    return [
      Math.min(...retained.map(segment => segment[0])),
      Math.max(...retained.map(segment => segment.at(-1))),
    ];
  }

  function visibleWavelengthRange(traces, includeIgnored = true) {
    // The reviewed spectrum owns the viewing domain, even while its curve is
    // hidden. Exact and approximate legacy traces cannot extend that domain.
    const bounds = (Array.isArray(traces) ? traces : [])
      .filter(trace => trace?.kind === 'new')
      .map(trace => {
        const valid = trace?.smoothing_points || trace?.points || [];
        const ignored = includeIgnored ? (trace?.ignored_points || []) : [];
        return significantWavelengthBounds([...valid, ...ignored]);
      })
      .filter(Boolean);
    if (!bounds.length) return null;
    const lower = Math.min(...bounds.map(bound => bound[0]));
    const upper = Math.max(...bounds.map(bound => bound[1]));
    if (upper > lower) return [lower, upper];
    const padding = Math.max(0.5, Math.abs(lower) * 1e-6);
    return [lower - padding, upper + padding];
  }

  function yRange(series, mode = 'robust') {
    const values = series.flatMap(trace => trace.map(point => point[1])).filter(finite).map(Number);
    if (!values.length) return [0, 1];

    let lo;
    let hi;
    if (mode === 'minmax') {
      lo = Math.min(...values);
      hi = Math.max(...values);
    } else {
      const bounds = series.map(medianBoxSummary).filter(summary => summary.trend.length).map(summary => {
        const noise = finite(summary.sigma) ? 3 * summary.sigma : 0;
        return [
          quantile(summary.trend, 0.01) - noise,
          quantile(summary.trend, 0.99) + noise,
        ];
      });
      lo = bounds.length ? Math.min(...bounds.map(bound => bound[0])) : Math.min(...values);
      hi = bounds.length ? Math.max(...bounds.map(bound => bound[1])) : Math.max(...values);
    }

    if (!(hi > lo)) {
      lo -= 0.5;
      hi += 0.5;
    }
    const padding = 0.07 * (hi - lo);
    return [lo - padding, hi + padding];
  }

  function formatWavelengthMicrons(wavelengthAngstrom, tickSpacingAngstrom) {
    const wavelength = Number(wavelengthAngstrom) / 10_000;
    const spacing = Math.abs(Number(tickSpacingAngstrom)) / 10_000;
    if (!Number.isFinite(wavelength)) return '—';
    const digits = spacing >= 0.1 ? 2 : spacing >= 0.01 ? 3 : spacing >= 0.001 ? 4 : 5;
    return wavelength.toFixed(digits);
  }

  return {
    adaptiveVelocityRange,
    consumeSwipeDelta,
    finite,
    formatWavelengthMicrons,
    median,
    medianBoxSummary,
    medianSmooth,
    minmaxDownsample,
    nativeVelocityResolution,
    quantile,
    robustSmooth,
    SPEED_OF_LIGHT_KMS,
    smoothNativeForDisplay,
    significantWavelengthBounds,
    steppedRangeValue,
    steppedVelocityValue,
    targetVelocityWindow,
    visibleWavelengthRange,
    yRange,
  };
});
