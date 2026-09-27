const assert = require("node:assert/strict");
const {test} = require("node:test");
const {figure} = require("../mocaviz/static/spherex_review_plot.js");

function fixture() {
  return {lane: "spiffstacker", object: {designation: "Fixture", moca_oid: 42, moca_specid: 43},
    fit: {spectrum: {wavelength_um: [1, 2, 3, 4, 5], flux: [2, 4, 100, -2, null],
      error: [10, 1, 1, 1, null], flagged: [false, true, false, false, false]},
      overlays: [0, 1, 2].map((i) => ({label: "L" + i, grid: "field",
        wavelength_um: [1, 2, 3], flux: [1, 2, 3],
        curve_wavelength_um: [1, 1.5, 2, 2.5, 3], curve_flux: [1, 1.5, 2, 2.5, 3]})),
      matches: [0, 1, 2].map((i) => ({robust_reduced_chi2_10pct_cap: 1.2 + i}))}};
}
const close = (a, b) => assert(Math.abs(a - b) < 1e-12, a + " != " + b);
const byRole = (plot, role) => plot.traces.filter((t) => t.meta.role === role);

test("all three matches are stacked, visible, and styled like the PNG", () => {
  const plot = figure(fixture(), "42");
  assert.equal(byRole(plot, "template-curve").length, 3);
  assert.equal(byRole(plot, "template-points").length, 3);
  assert(plot.traces.every((t) => t.visible !== "legendonly"));
  assert(byRole(plot, "template-curve").every((t) => t.line.color === "red" && t.x.length === 5));
  assert(byRole(plot, "template-points").every((t) => t.marker.color === "red"));
  assert(byRole(plot, "data").every((t) => t.marker.color === "white" && t.marker.line.color === "#666666"));
  assert.equal(byRole(plot, "flagged")[0].opacity, 0.2);
  assert.equal(byRole(plot, "flagged")[0].marker.symbol, "x-thin");
  assert.deepEqual(plot.layout.annotations.map((a) => a.text), [
    "<b>L0  χ²<sub>r</sub>=1.2</b>", "<b>L1  χ²<sub>r</sub>=2.2</b>", "<b>L2  χ²<sub>r</sub>=3.2</b>"]);
  close(plot.layout.shapes[0].y0, 4.6); close(plot.layout.shapes[1].y0, 2.3);
  close(plot.layout.shapes[2].y0, 0);
  assert.equal(plot.layout.xaxis.mirror, true);
  assert.equal(plot.layout.yaxis.showline, true);
});

test("template-based limits ignore outliers and match the desktop padding", () => {
  const plot = figure(fixture(), "42");
  close(plot.layout.yaxis.range[0], 0.67); close(plot.layout.yaxis.range[1], 7.93);
  close(plot.layout.xaxis.range[0], 0.88); close(plot.layout.xaxis.range[1], 5.12);
  const rows = byRole(plot, "data");
  assert.deepEqual(rows[0].customdata, [2, 100]); // best row has no upper clip
  assert.deepEqual(rows[2].customdata, [2]); // negative/overflow/missing points hidden
  close(rows[2].error_y.array[0], 0.3);
  close(rows[2].error_y.arrayminus[0], 2);
  assert.equal(rows[2].error_y.width, 0); // no error-bar caps
  assert.equal(rows[2].error_y.symmetric, false);
});

test("scientific multiplier preserves physical flux instead of median normalization", () => {
  const data = fixture();
  for (const key of ["flux", "error"]) data.fit.spectrum[key] = data.fit.spectrum[key].map((v) => v === null ? v : v * 1e-17);
  for (const overlay of data.fit.overlays) {
    overlay.flux = overlay.flux.map((f) => f * 1e-17);
    overlay.curve_flux = overlay.curve_flux.map((f) => f * 1e-17);
  }
  const plot = figure(data, "42");
  assert.equal(plot.layout.annotations.at(-1).text, "1e−17");
  close(byRole(plot, "data")[2].y[0], 2);
  assert.equal(byRole(plot, "data")[2].customdata[0], 2e-17);
});

test("no-fit and empty spectra stay reviewable with finite axes", () => {
  for (const raw of [[], [{wavelength_angstrom: 12000, flux_flambda: -1, flux_flambda_unc: 2, ignored: 1}]]) {
    const plot = figure({object: {}, raw_spectrum: raw}, "no-fit");
    assert(plot.layout.xaxis.range.every(Number.isFinite));
    assert(plot.layout.yaxis.range.every(Number.isFinite));
    if (raw.length) assert.deepEqual(byRole(plot, "flagged")[0].customdata, [-1]);
  }
});

test("labels escape data HTML and render narrow layouts without a long title line", () => {
  const data = fixture();
  data.object.designation = "<img src=x>";
  data.fit.overlays[0].label = "<b>Injected</b>";
  const plot = figure(data, "42", 380);
  assert(plot.layout.title.text.includes("&lt;img src=x&gt;"));
  assert(plot.layout.title.text.includes("Autotype:<br>"));
  assert(plot.layout.annotations[0].text.includes("&lt;b&gt;Injected&lt;/b&gt;"));
  assert.equal(plot.layout.uirevision, "42");
});

test("figure construction never mutates a prefetched fit", () => {
  const data = fixture(), before = JSON.stringify(data);
  figure(data, "42"); figure(data, "42");
  assert.equal(JSON.stringify(data), before);
});
