'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const {
  adaptiveVelocityRange,
  consumeSwipeDelta,
  formatWavelengthMicrons,
  medianBoxSummary,
  medianSmooth,
  minmaxDownsample,
  nativeVelocityResolution,
  robustSmooth,
  SPEED_OF_LIGHT_KMS,
  significantWavelengthBounds,
  smoothNativeForDisplay,
  steppedRangeValue,
  steppedVelocityValue,
  targetVelocityWindow,
  visibleWavelengthRange,
  yRange,
} = require('../mocaviz/static/spectrum_compare/spectrum_math.js');

test('median-box range retains broad late-T-dwarf peaks but rejects spikes', () => {
  const points = [];
  for (let index = 0; index < 6000; index += 1) {
    const firstPeak = 14 * Math.exp(-0.5 * ((index - 1900) / 260) ** 2);
    const secondPeak = 10 * Math.exp(-0.5 * ((index - 4100) / 340) ** 2);
    const noise = 0.18 * Math.sin(index * 0.73) + 0.11 * Math.sin(index * 1.91);
    points.push([index, 0.15 + firstPeak + secondPeak + noise]);
  }
  points[75][1] = 450;
  points[5700][1] = -90;

  const [lo, hi] = yRange([points], 'robust');
  assert.ok(lo < 0, `expected room below the troughs, received ${lo}`);
  assert.ok(hi > 13, `expected the broad peak to remain visible, received ${hi}`);
  assert.ok(hi < 30, `expected isolated spikes to be rejected, received ${hi}`);
});

test('min/max range still includes every finite sample', () => {
  const points = [[1, -4], [2, 2], [3, 100]];
  const [lo, hi] = yRange([points], 'minmax');
  assert.ok(lo < -4);
  assert.ok(hi > 100);
});

test('median-box summary uses a broad trend instead of an isolated outlier', () => {
  const points = Array.from({ length: 1200 }, (_, index) => [index, 2 + 0.1 * Math.sin(index)]);
  points[600][1] = 1000;
  const summary = medianBoxSummary(points);
  assert.ok(Math.max(...summary.trend) < 3);
});

test('wavelength ticks convert Angstroms to microns with zoom-aware precision', () => {
  assert.equal(formatWavelengthMicrons(10_000, 2_000), '1.00');
  assert.equal(formatWavelengthMicrons(12_345, 100), '1.234');
  assert.equal(formatWavelengthMicrons(12_345, 10), '1.2345');
});

test('wavelength bounds discard insignificant disconnected edge fragments', () => {
  const opticalFragments = [
    ...Array.from({ length: 4 }, (_, index) => [4_500 + index, 1]),
    ...Array.from({ length: 2 }, (_, index) => [5_450 + index, 1]),
  ];
  const nir = [
    ...Array.from({ length: 50 }, (_, index) => [10_000 + index, 1]),
    ...Array.from({ length: 44 }, (_, index) => [14_000 + index, 1]),
  ];
  assert.deepEqual(
    significantWavelengthBounds([...opticalFragments, ...nir]),
    [10_000, 14_043],
  );
});

test('reviewed spectrum fixes the wavelength range regardless of comparison coverage or visibility', () => {
  const nir = Array.from({ length: 100 }, (_, index) => [10_000 + index, 1]);
  const opticalArm = Array.from({ length: 100 }, (_, index) => [5_300 + index, 1]);
  const longerWavelengths = Array.from({ length: 100 }, (_, index) => [20_000 + index, 1]);
  const traces = [
    { kind: 'legacy', visible: true, smoothing_points: opticalArm, ignored_points: [] },
    { kind: 'new', visible: true, smoothing_points: nir, ignored_points: [] },
    { kind: 'approximate_legacy', visible: true, smoothing_points: longerWavelengths, ignored_points: [] },
  ];
  assert.deepEqual(visibleWavelengthRange(traces), [10_000, 10_099]);
  for (const trace of traces) {
    trace.visible = false;
    assert.deepEqual(visibleWavelengthRange(traces), [10_000, 10_099]);
  }
});

test('only the reviewed spectrum contributes ignored samples to wavelength bounds', () => {
  const traces = [
    { kind: 'new', points: [[10_001, 1], [10_002, 1]], ignored_points: [[10_000, 2], [10_003, 2]] },
    { kind: 'legacy', points: [[5_000, 1], [30_000, 1]], ignored_points: [[4_000, 2], [40_000, 2]] },
  ];
  assert.deepEqual(visibleWavelengthRange(traces, true), [10_000, 10_003]);
  assert.deepEqual(visibleWavelengthRange(traces, false), [10_001, 10_002]);
  traces[0].points = [[NaN, 1], [10_001, NaN]];
  assert.equal(visibleWavelengthRange(traces, false), null);
});

test('robust local-polynomial smoothing rejects an isolated spectral outlier', () => {
  const points = [[1, 1], [2, 1], [3, 1000], [4, 1], [5, 1]];
  assert.deepEqual(robustSmooth(points, 5), [[1, 1], [2, 1], [3, 1], [4, 1], [5, 1]]);
  assert.equal(points[2][1], 1000, 'input samples must not be mutated');
});

test('fast median preview rejects an outlier without mutating its input', () => {
  const points = [[1, 1], [2, 1], [3, 1000], [4, 1], [5, 1]];
  assert.deepEqual(medianSmooth(points, 5), [[1, 1], [2, 1], [3, 1], [4, 1], [5, 1]]);
  assert.equal(points[2][1], 1000);
});

test('robust smoothing preserves quadratic structure without median plateaus', () => {
  const expected = Array.from({ length: 25 }, (_, index) => 2 + 0.4 * index + 0.03 * index ** 2);
  const points = expected.map((value, index) => [index, value]);
  points[12][1] += 500;
  const smoothed = robustSmooth(points, 9).map(point => point[1]);
  for (let index = 0; index < smoothed.length; index += 1) {
    assert.ok(Math.abs(smoothed[index] - expected[index]) < 1e-7, `quadratic mismatch at ${index}`);
  }
  assert.ok(new Set(smoothed.map(value => value.toFixed(6))).size > 20);
});

test('full one-sided polynomial windows prevent defects at spectrum edges', () => {
  const expected = Array.from({ length: 25 }, (_, index) => 4 - 0.2 * index + 0.015 * index ** 2);
  const points = expected.map((value, index) => [index, value]);
  points[0][1] += 800;
  points[points.length - 1][1] -= 800;
  const smoothed = robustSmooth(points, 9).map(point => point[1]);
  assert.ok(Math.abs(smoothed[0] - expected[0]) < 1e-7);
  assert.ok(Math.abs(smoothed.at(-1) - expected.at(-1)) < 1e-7);
});

test('robust polynomial smoothing never crosses a large wavelength gap', () => {
  const points = [[1, 0], [2, 0], [3, 0], [100, 10], [101, 10], [102, 10]];
  assert.deepEqual(robustSmooth(points, 5).map(point => point[1]), [0, 0, 0, 10, 10, 10]);
});

test('one-pixel smoothing is an unchanged copy', () => {
  const points = [[1, 2], [2, 3]];
  const smoothed = robustSmooth(points, 1);
  assert.deepEqual(smoothed, points);
  assert.notEqual(smoothed, points);
});

function logarithmicGrid(resolvingPower, pixelsPerResolutionElement, length = 201) {
  return Array.from({ length }, (_, index) => [
    12_000 * Math.exp(index / (resolvingPower * pixelsPerResolutionElement)),
    index,
  ]);
}

test('target velocity smooths only the higher-resolution trace at first', () => {
  const highResolution = logarithmicGrid(10_000, 3);
  const lowResolution = logarithmicGrid(1_000, 3);

  assert.ok(Math.abs(nativeVelocityResolution(highResolution, 10_000, 3) - 29.9792458) < 1e-8);
  assert.ok(Math.abs(nativeVelocityResolution(lowResolution, 1_000, 3) - 299.792458) < 1e-8);
  assert.equal(targetVelocityWindow(highResolution, 100, 10_000, 3), 11);
  assert.equal(targetVelocityWindow(lowResolution, 100, 1_000, 3), 1);
});

test('lower-resolution trace joins smoothing after its native c over R threshold', () => {
  const highResolution = logarithmicGrid(10_000, 3);
  const lowResolution = logarithmicGrid(1_000, 3);

  assert.equal(targetVelocityWindow(highResolution, 400, 10_000, 3), 41);
  assert.equal(targetVelocityWindow(lowResolution, 400, 1_000, 3), 3);
  assert.equal(
    targetVelocityWindow(lowResolution, SPEED_OF_LIGHT_KMS / 1_000, 1_000, 3),
    1,
  );
});

test('native velocity resolution falls back to wavelength sampling metadata', () => {
  const points = logarithmicGrid(2_000, 4);
  assert.ok(Math.abs(nativeVelocityResolution(points, null, 4) - SPEED_OF_LIGHT_KMS / 2_000) < 1e-8);
});

test('velocity slider range adapts to the highest-R displayed trace', () => {
  assert.deepEqual(
    adaptiveVelocityRange([2_498.3]),
    { startKms: 2_500, maxKms: 5_000, stepKms: 100 },
  );
  assert.deepEqual(
    adaptiveVelocityRange([238.6, 2_498.3]),
    { startKms: 240, maxKms: 5_000, stepKms: 10 },
  );
  assert.deepEqual(
    adaptiveVelocityRange([6.66]),
    { startKms: 7, maxKms: 500, stepKms: 1 },
  );
});

test('first velocity swipe skips the inactive interval below c over R', () => {
  const prismRange = { startKms: 2_500, maxKms: 5_000, stepKms: 100 };
  assert.equal(steppedVelocityValue(0, 1, prismRange), 2_500);
  assert.equal(steppedVelocityValue(0, 2, prismRange), 2_600);
  assert.equal(steppedVelocityValue(2_500, -1, prismRange), 0);
  assert.equal(steppedVelocityValue(2_600, -1, prismRange), 2_500);
});

test('native smoothing is completed before display downsampling', () => {
  const expected = Array.from({ length: 201 }, (_, index) => 3 + 0.02 * index + 0.0004 * index ** 2);
  const points = expected.map((value, index) => [12_000 + 0.5 * index, value]);
  points[100][1] += 500;
  const result = smoothNativeForDisplay(points, 500, 6_000, 2.2, 40);

  assert.equal(result.windowSize, 41);
  assert.ok(Math.abs(result.nativeResolutionKms - SPEED_OF_LIGHT_KMS / 6_000) < 1e-10);
  assert.ok(result.appliedVelocityKms > 497 && result.appliedVelocityKms < 498);
  assert.ok(result.points.length <= 40);
  assert.equal(result.points[0][0], 12_000);
  assert.ok(Math.abs(result.points[0][1] - expected[0]) < 1e-10);
  assert.equal(result.points.at(-1)[0], 12_100);
  assert.ok(Math.abs(result.points.at(-1)[1] - expected.at(-1)) < 1e-10);
  assert.equal(points[100][1], expected[100] + 500, 'native input must not be mutated');
});

test('extrema-preserving downsampling retains endpoints and its point budget', () => {
  const points = Array.from({ length: 200 }, (_, index) => [index, Math.sin(index)]);
  const result = minmaxDownsample(points, 40);
  assert.ok(result.length <= 40);
  assert.deepEqual(result[0], points[0]);
  assert.deepEqual(result.at(-1), points.at(-1));
});

test('GUI exposes a default-off target-velocity smoothing slider', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  const tag = html.match(/<input id="smooth-velocity"[^>]*>/)?.[0] || '';
  assert.match(tag, /type="range"/);
  assert.match(tag, /min="0"/);
  assert.match(tag, /max="5000"/);
  assert.match(tag, /step="10"/);
  assert.match(tag, /value="0"/);
  assert.match(tag, /aria-label="Target smoothing resolution in km\/s"/);
  assert.match(html, /function smoothingTargetKms\(\)/);
  assert.match(html, /targetVelocityWindow\(points,smoothingTargetKms\(\)/);
  assert.match(html, /function configureSmoothingVelocityRange\(\)/);
  assert.match(html, /adaptiveVelocityRange\(velocities\)/);
  assert.match(html, /slider\.dataset\.startKms=String\(state\.smoothingRange\.startKms\)/);
  assert.match(html, /smoothedTracePoints\(trace\)/);
  assert.match(html, /function handleSmoothingInput\(\)/);
});

test('legend rows toggle traces and recompute the visible wavelength range', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /label\.className='legend-item'/);
  assert.match(html, /check\.id=`legend-trace-\$\{index\}`;label\.htmlFor=check\.id/);
  assert.match(html, /check\.onchange=\(\)=>\{trace\.visible=check\.checked;recomputeVisibleXRange\(\);configureSmoothingVelocityRange\(\);handleSmoothingInput\(\);\}/);
  assert.match(html, /function recomputeVisibleXRange\(\)\{/);
  assert.match(html, /state\.xFull=visibleWavelengthRange\(state\.traces,\$\('show-ignored'\)\.checked\)/);
  assert.match(html, /#legend \.legend-item \{[^}]*padding:6px 8px[^}]*cursor:pointer/);
});

test('GUI previews immediately then atomically installs native worker results', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /medianSmooth\(trace\.points,trace\._previewPixelWindow\)/);
  assert.match(html, /function createSmoothingWorker\(\)/);
  assert.match(html, /new Blob\(\[source\],\{type:'text\/javascript'\}\)/);
  assert.match(html, /new Worker\(objectUrl\)/);
  assert.match(html, /SpectrumMath\.smoothNativeForDisplay\(trace\.points,targetKms,trace\.resolvingPower,trace\.pixPerResolutionElement,maxPoints\)/);
  assert.match(html, /points:trace\.smoothing_points/);
  assert.match(html, /setTimeout\(startSmoothingRefinement,180\)/);
  assert.match(html, /prepared\.forEach\(\(result,index\)=>\{state\.traces\[index\]\._refinedTargetKms=targetKms/);
  assert.match(html, /setSmoothingPhase\('refined'\);draw\(\)/);
  assert.match(html, />temporary smoothing currently shown<\/span>/);
  assert.match(html, /label\.style\.visibility=temporary\?'visible':'hidden'/);
});

test('changing spectra cancels refinement and resets smoothing to off', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /function resetSmoothing\(\)\{\s*cancelSmoothingRefinement\(\);\$\('smooth-velocity'\)\.value='0';setSmoothingPhase\('off'\)/);
  assert.match(html, /async function loadSpectrum\(specid\)\{\s*resetSmoothing\(\);const requestId=startSpectrumLoad/);
  assert.match(html, /async function loadIndex\(packageId\)\{\s*const generation=\+\+indexGeneration;\s*resetSmoothing\(\);setStatus/);
});

test('horizontal swipe deltas accumulate into stable smoothing steps', () => {
  const first = consumeSwipeDelta(0, 10, 18);
  assert.deepEqual(first, { steps: 0, remainder: 10 });
  const second = consumeSwipeDelta(first.remainder, 30, 18);
  assert.deepEqual(second, { steps: 2, remainder: 4 });
  const reversed = consumeSwipeDelta(0, -40, 18);
  assert.deepEqual(reversed, { steps: -2, remainder: -4 });
});

test('swipe steps keep the smoothing velocity bounded in 10 km/s steps', () => {
  assert.equal(steppedRangeValue(0, 1, 0, 5_000, 10), 10);
  assert.equal(steppedRangeValue(90, -2, 0, 5_000, 10), 70);
  assert.equal(steppedRangeValue(4_990, 20, 0, 5_000, 10), 5_000);
  assert.equal(steppedRangeValue(30, -20, 0, 5_000, 10), 0);
});

test('GUI draws the blue reduction last and with heavier line and points', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /drawIndices=traceDrawOrder\(enabled\)/);
  assert.match(html, /ctx\.lineWidth=trace\.kind==='new'\?1\.65:1/);
  assert.match(html, /const size=trace\.kind==='new'\?2\.6:2/);
  assert.match(html, /ctx\.lineWidth=trace\.kind==='new'\?1\.35:0\.9/);
});

test('GUI routes horizontal wheel gestures to smoothing before plot zoom', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /function adjustSmoothingFromSwipe\(event\)/);
  assert.match(html, /Math\.abs\(event\.deltaX\)>Math\.abs\(event\.deltaY\)/);
  assert.match(html, /document\.querySelector\('\.smoothing-control'\)\.addEventListener\('wheel'/);
  assert.match(html, /canvas\.addEventListener\('wheel',event=>\{if\(adjustSmoothingFromSwipe\(event\)\)/);
  assert.match(html, /slider\.dispatchEvent\(new Event\('input'/);
  assert.match(html, /steppedVelocityValue\(current,consumed\.steps,state\.smoothingRange\)/);
});

test('GUI clearly labels and dashes approximate legacy comparators', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /APPROXIMATE LEGACY/);
  assert.match(html, /function approximateLegacyStatus\(metadata\)/);
  assert.match(html, /else if\(payload\.approximate_legacy\) setStatus/);
  assert.match(html, /trace\.kind==='approximate_legacy'\?\[7,4\]:\[\]/);
  assert.match(html, /\.swatch\.approximate/);
});
