'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const overlays = require('../mocaviz/static/spectral_line_overlays.js');

function rgbaOpacity(color) {
  const match = String(color).match(/,\s*([0-9.]+)\)$/);
  return match ? Number(match[1]) : Number.NaN;
}

test('OH catalogue is ordered in vacuum wavelength and opacity follows strength', () => {
  assert.equal(overlays.OH_SOURCE.wavelengthMedium, 'vacuum');
  assert.equal(overlays.OH_LINES.length, 154);
  assert.ok(overlays.OH_LINES.every((line, index) => (
    index === 0 || line.wavelengthMicron > overlays.OH_LINES[index - 1].wavelengthMicron
  )));

  const shapes = overlays.plotlySpectralLineShapes([1, 2.6], { showOh: true });
  assert.equal(shapes.length, overlays.OH_LINES.length);
  const weakestIndex = overlays.OH_LINES.reduce((best, line, index, lines) => (
    line.relativeAmplitude < lines[best].relativeAmplitude ? index : best
  ), 0);
  const strongestIndex = overlays.OH_LINES.reduce((best, line, index, lines) => (
    line.relativeAmplitude > lines[best].relativeAmplitude ? index : best
  ), 0);
  assert.ok(rgbaOpacity(shapes[strongestIndex].line.color) > 6 * rgbaOpacity(shapes[weakestIndex].line.color));
  assert.ok(shapes.every(shape => shape.layer === 'below' && shape.yref === 'paper'));
});

test('hydrogen catalogue contains Paschen and Brackett only, including Br gamma', () => {
  assert.equal(overlays.HYDROGEN_LINES.length, 53);
  assert.deepEqual(new Set(overlays.HYDROGEN_LINES.map(line => line.series)), new Set(['Paschen', 'Brackett']));
  const brGamma = overlays.HYDROGEN_LINES.find(line => line.label === 'Brγ');
  assert.ok(Math.abs(brGamma.wavelengthMicron - 2.166128667) < 1e-9);

  const shapes = overlays.plotlySpectralLineShapes([2.15, 2.18], { showHydrogen: true });
  const annotations = overlays.plotlySpectralLineAnnotations([2.15, 2.18], { showHydrogen: true });
  assert.equal(shapes.length, 1);
  assert.equal(annotations.length, 1);
  assert.equal(annotations[0].text, 'Brγ');
});

test('hydrogen line opacity follows the expected depth order within a series', () => {
  const paAlpha = overlays.HYDROGEN_LINES.find(line => line.label === 'Paα');
  const paBeta = overlays.HYDROGEN_LINES.find(line => line.label === 'Paβ');
  const pa20 = overlays.HYDROGEN_LINES.find(line => line.label === 'Pa20');
  assert.ok(overlays.hydrogenLineOpacity(paAlpha) > overlays.hydrogenLineOpacity(paBeta));
  assert.ok(overlays.hydrogenLineOpacity(paBeta) > overlays.hydrogenLineOpacity(pa20));
  assert.ok(overlays.hydrogenLineOpacity(paAlpha) > 0.70);
  assert.ok(overlays.hydrogenLineOpacity(pa20) < 0.22);

  const shapes = overlays.plotlySpectralLineShapes([0.82, 1.88], { showHydrogen: true });
  const alphaShape = shapes.find(shape => Math.abs(shape.x0 - paAlpha.wavelengthMicron) < 1e-12);
  const betaShape = shapes.find(shape => Math.abs(shape.x0 - paBeta.wavelengthMicron) < 1e-12);
  assert.ok(rgbaOpacity(alphaShape.line.color) > rgbaOpacity(betaShape.line.color));
});

test('line overlays remain empty while both page controls are off', () => {
  assert.deepEqual(overlays.plotlySpectralLineShapes([0.4, 5], {}), []);
  assert.deepEqual(overlays.plotlySpectralLineAnnotations([0.4, 5], {}), []);
});
