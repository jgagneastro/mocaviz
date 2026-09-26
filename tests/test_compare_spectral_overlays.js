'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

require('../mocaviz/static/spectrum_compare/brown_dwarf_spectral_features.js');
const AtranReference = require('../mocaviz/static/spectrum_compare/atran_reference.js');
const {
  HYDROGEN_LINES,
  OH_LINES,
  OH_MAX_RELATIVE_AMPLITUDE,
  OH_SOURCE,
  hydrogenLineOpacity,
  itemsInMicronRange,
  ohLineOpacity,
  pointsInMicronRange,
} = require('../mocaviz/static/spectrum_compare/spectral_overlays.js');

test('brown-dwarf overlay carries the complete MoCaVis feature catalogue', () => {
  const bands = globalThis.mocaBrownDwarfSpectralFeatureBands;
  assert.equal(bands.length, 63);
  assert.deepEqual(bands[0].range, [0.4215, 0.424]);
  assert.deepEqual(bands.at(-1).range, [20, 50]);
  assert.ok(bands.some(band => band.formula === 'CH4' && band.range[0] === 1.6));
  assert.ok(bands.some(band => band.formula === 'NH3' && band.range[0] === 10));
});

test('OH overlay uses the ordered vacuum strong-line catalogue', () => {
  assert.equal(OH_SOURCE.wavelengthMedium, 'vacuum');
  assert.equal(OH_LINES.length, 154);
  assert.ok(OH_LINES.every((line, index) => index === 0 || line.wavelengthMicron > OH_LINES[index - 1].wavelengthMicron));
  assert.ok(Math.abs(OH_LINES[0].wavelengthMicron - 1.083425126) < 1e-9);
  assert.ok(Math.abs(OH_LINES.at(-1).wavelengthMicron - 2.498093096) < 1e-9);
});

test('OH opacity is stable and strongly ordered by catalogue intensity', () => {
  const weakest = Math.min(...OH_LINES.map(line => line.relativeAmplitude));
  const weakOpacity = ohLineOpacity(weakest);
  const strongOpacity = ohLineOpacity(OH_MAX_RELATIVE_AMPLITUDE);
  assert.ok(weakOpacity > 0.025 && weakOpacity < 0.12);
  assert.ok(strongOpacity > 0.70 && strongOpacity < 0.75);
  assert.ok(strongOpacity > 6 * weakOpacity);
  assert.equal(ohLineOpacity(null), 0.025);
});

test('hydrogen overlay includes vacuum Balmer, Paschen, and Brackett series', () => {
  const hAlpha = HYDROGEN_LINES.find(line => line.label === 'Hα');
  const paAlpha = HYDROGEN_LINES.find(line => line.label === 'Paα');
  const brGamma = HYDROGEN_LINES.find(line => line.label === 'Brγ');
  assert.equal(HYDROGEN_LINES.length, 81);
  assert.ok(Math.abs(hAlpha.wavelengthMicron - 0.656469606) < 1e-9);
  assert.ok(Math.abs(paAlpha.wavelengthMicron - 1.875627447) < 1e-9);
  assert.ok(Math.abs(brGamma.wavelengthMicron - 2.166128667) < 1e-9);
  assert.equal(HYDROGEN_LINES.filter(line => line.series === 'Balmer').length, 28);
  assert.equal(HYDROGEN_LINES.filter(line => line.series === 'Paschen').length, 27);
  assert.equal(HYDROGEN_LINES.filter(line => line.series === 'Brackett').length, 26);
});

test('hydrogen line opacity follows the expected depth order within a series', () => {
  const paAlpha = HYDROGEN_LINES.find(line => line.label === 'Paα');
  const paBeta = HYDROGEN_LINES.find(line => line.label === 'Paβ');
  const pa20 = HYDROGEN_LINES.find(line => line.label === 'Pa20');
  assert.ok(hydrogenLineOpacity(paAlpha) > hydrogenLineOpacity(paBeta));
  assert.ok(hydrogenLineOpacity(paBeta) > hydrogenLineOpacity(pa20));
  assert.ok(hydrogenLineOpacity(paAlpha) > 0.70);
  assert.ok(hydrogenLineOpacity(pa20) < 0.22);
  assert.equal(hydrogenLineOpacity(null), 0.10);
});

test('reference atmosphere is the verified vacuum PySpextool curve', () => {
  assert.equal(AtranReference.sha256, '7365d6ec2bc6dd429183da9b89303e252b51bfdf6825437849d58c03b51a571b');
  assert.equal(AtranReference.wavelengthMedium, 'vacuum');
  assert.equal(AtranReference.referenceAirmass, 1.2);
  assert.equal(AtranReference.resolvingPower, 4000);
  assert.equal(AtranReference.originalPointCount, 236728);
  assert.equal(AtranReference.points.length, 3491);
  assert.deepEqual(AtranReference.points[0], [0.605034, 1]);
  assert.deepEqual(AtranReference.points.at(-1), [5.59998, 0]);
  assert.ok(AtranReference.points.every((point, index) => (
    point[1] >= 0 && point[1] <= 1
    && (index === 0 || point[0] > AtranReference.points[index - 1][0])
  )));
});

test('overlay range helpers retain only visible lines and bracket curves', () => {
  const lines = itemsInMicronRange(OH_LINES, [1.5, 1.51]);
  assert.ok(lines.length > 0);
  assert.ok(lines.every(line => line.wavelengthMicron >= 1.5 && line.wavelengthMicron <= 1.51));

  const points = [[1, 0.9], [2, 0.8], [3, 0.7], [4, 0.6]];
  assert.deepEqual(pointsInMicronRange(points, [2.2, 3.2]), [[2, 0.8], [3, 0.7], [4, 0.6]]);
});

test('all five new overlay checkboxes are off by default', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  for (const id of ['show-snr', 'show-bd-features', 'show-oh-lines', 'show-hydrogen', 'show-transmission']) {
    const tag = html.match(new RegExp(`<input id="${id}"[^>]*>`))?.[0];
    assert.ok(tag, `missing ${id}`);
    assert.doesNotMatch(tag, /\bchecked\b/);
  }
});

test('Earth transmission track uses twenty percent of the usable plot height', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /trackHeight=h\*\.20/);
  assert.doesNotMatch(html, /Math\.min\(82,h\*\.20\)/);
});

test('cursor wavelength readout is subtle, plot-bounded, and zoom-aware', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /id="cursor-readout" aria-hidden="true"/);
  assert.match(html, /#cursor-readout \{[^}]*pointer-events:none/);
  assert.match(html, /formatWavelengthMicrons\(wavelength,\(transform\.xr\[1\]-transform\.xr\[0\]\)\/100\)/);
  assert.match(html, /canvas\.addEventListener\('pointerleave',hideCursorReadout\)/);
});

test('feature and line overlays suppress the canvas background grid', () => {
  const html = fs.readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /showBackgroundGrid=!\(\$\('show-bd-features'\)\.checked\|\|\$\('show-oh-lines'\)\.checked\|\|\$\('show-hydrogen'\)\.checked\)/);
  assert.match(html, /if\(showBackgroundGrid\)\{ctx\.beginPath\(\);ctx\.moveTo\(pad\.l,yy\)/);
  assert.match(html, /if\(showBackgroundGrid\)\{ctx\.beginPath\(\);ctx\.moveTo\(xx,pad\.t\)/);
});
