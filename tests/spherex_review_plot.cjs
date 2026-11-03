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

test("labels escape data HTML without repeating UI headings inside the plot", () => {
  const data = fixture();
  data.object.designation = "<img src=x>";
  data.fit.overlays[0].label = "<b>Injected</b>";
  for (const width of [380, 1000]) {
    const plot = figure(data, "42", width);
    assert.equal(plot.layout.title.text, "");
    assert.equal(plot.layout.margin.t, 26);
    assert(plot.layout.annotations[0].text.includes("&lt;b&gt;Injected&lt;/b&gt;"));
    assert.equal(plot.layout.uirevision, "42");
  }
});

test("figure construction never mutates a prefetched fit", () => {
  const data = fixture(), before = JSON.stringify(data);
  figure(data, "42"); figure(data, "42");
  assert.equal(JSON.stringify(data), before);
});


test("selected number of ranked matches is drawn without mutating the fit", () => {
  const data = fixture();
  data.fit.overlays = Array.from({length: 10}, (_, i) => ({...data.fit.overlays[i % 3], label: "L" + i}));
  data.fit.matches = Array.from({length: 10}, (_, i) => ({reduced_chi2: i}));
  const original = JSON.stringify(data);
  for (const count of [1, 3, 10]) {
    const plot = figure(data, "42", 800, count);
    assert.equal(byRole(plot, "template-curve").length, count);
    assert.equal(plot.layout.shapes.length, count);
  }
  assert.equal(JSON.stringify(data), original);
});


test("three reduction panels use distinct template colors and independent flux axes", () => {
  const primary = fixture(); primary.read_only = false;
  primary.comparison = {spiff: {...fixture(), lane: "spiff"}, sublimeaperture: {...fixture(), lane: "sublimeaperture"}};
  const before = JSON.stringify(primary);
  const {comparisonFigure, lanes} = require("../mocaviz/static/spherex_review_plot.js");
  const plot = comparisonFigure(primary, "object", 800, 3);
  assert.equal(byRole(plot, "template-curve").length, 9);
  for (const [index, lane] of lanes.entries()) {
    const curves = byRole(plot, "template-curve").filter(t => t.meta.lane === lane.key);
    assert.equal(curves.length, 3);
    assert(curves.every(t => t.line.color === lane.color && t.yaxis === "y" + (index ? index + 1 : "")));
  }
  assert.deepEqual(plot.layout.xaxis.range, plot.layout.xaxis3.range);
  assert(plot.layout.yaxis.domain[0] > plot.layout.yaxis2.domain[1]);
  assert(plot.layout.yaxis2.domain[0] > plot.layout.yaxis3.domain[1]);
  assert(plot.layout.annotations.some(a => a.text.includes("SPIFFStacker · review lane")));
  assert.equal(JSON.stringify(primary), before);
});

test("missing reduction spectra keep their labeled slots and exact read-only spectra stay exact", () => {
  const {comparisonFigure} = require("../mocaviz/static/spherex_review_plot.js");
  const primary = {...fixture(), read_only:false, comparison:{}};
  const plot = comparisonFigure(primary, "object", 800, 1);
  assert.equal(byRole(plot, "template-curve").length, 1);
  assert(plot.layout.annotations.some(a => a.text === "No active SPIFF spectrum"));
  assert(plot.layout.annotations.some(a => a.text === "No active SUBLIMEaperture spectrum"));
  const exact = comparisonFigure({...primary, read_only:true}, "exact");
  assert.equal(byRole(exact, "template-curve").length, 3);
  assert(!exact.layout.xaxis2);
});

test("WiseView stacks each lane's own data and single best template in fixed colors", () => {
  const {laneStackFigure,lanes}=require('../mocaviz/static/spherex_review_plot.js');
  const available=Object.fromEntries(lanes.map((lane,i)=>{
    const item=fixture();item.fit.spectrum.flux=[1.1+i,1.2+i,1.3+i,1.4+i,1.5+i];
    item.fit.spectrum.flagged=[false,false,false,false,false];
    item.fit.spectrum.wavelength_um=[1+i*.01,2,3,4,5];
    item.fit.overlays[0].label='Best '+lane.label;
    return [lane.key,item];
  }));
  const before=structuredClone(available),plot=laneStackFigure(available,'42',700);
  assert.equal(byRole(plot,'template-curve').length,3);
  assert.equal(plot.layout.yaxis2,undefined); // Existing one-figure format.
  lanes.forEach((lane,i)=>{
    const curve=byRole(plot,'template-curve').find(t=>t.meta.lane===lane.key);
    assert.equal(curve.line.color,lane.color);
    assert(curve.name.includes('Best '+lane.label));
    const data=byRole(plot,'data').find(t=>t.meta.lane===lane.key);
    assert.deepEqual(data.customdata,available[lane.key].fit.spectrum.flux);
    assert.equal(data.x[0],1+i*.01);
  });
  assert.deepEqual(available,before);
});

test("unfitted lanes retain their own raw data and missing lanes add no fake rows", () => {
  const {laneStackFigure,comparisonFigure}=require('../mocaviz/static/spherex_review_plot.js');
  const raw={raw_spectrum:[{wavelength_angstrom:15000,flux_flambda:2,flux_flambda_unc:.1,ignored:0}]};
  const plot=laneStackFigure({spiffstacker:fixture(),spiff:raw,sublimeaperture:{missing:true}},'raw');
  assert.equal(byRole(plot,'template-curve').length,1);
  const data=byRole(plot,'data').find(t=>t.meta.lane==='spiff');
  assert.deepEqual(data.x,[1.5]);assert.deepEqual(data.customdata,[2]);
  assert(plot.layout.annotations.some(a=>a.text.includes('SPIFF · no valid fit')));
  assert(!plot.traces.some(t=>t.meta.lane==='sublimeaperture'));
  const atlas=comparisonFigure({lane:null,comparison:{},comparison_errors:{spiff:'Example <error>'}},'empty',500,1,false);
  assert.equal(atlas.traces.length,0);
  assert(atlas.layout.annotations.some(a=>a.text==='Example &lt;error&gt;'));
  assert(!atlas.layout.annotations.some(a=>a.text.includes('review lane')));
});
