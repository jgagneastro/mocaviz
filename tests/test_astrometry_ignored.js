const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(require.resolve('../mocaviz/static/astrometry.js'), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));

function fixture() {
  const plots = {};
  const context = vm.createContext({URL, URLSearchParams, console,
    document: {currentScript: {src: 'http://localhost/static/astrometry.js'}, addEventListener() {}},
    window: {location: {search: ''}},
    Plotly: {react(plot, traces, layout, config) { plots[plot.id] = {traces, layout, config}; }},
  });
  vm.runInContext(source, context);
  vm.runInContext(`
    ['atm-display-merged', 'atm-only-recalibrated', 'atm-revert-raw', 'atm-adjust-reference',
     'atm-display-reference', 'atm-subtract-pm', 'atm-subtract-plx', 'atm-phase-yearly',
     'atm-display-absolute', 'atm-bin'].forEach(id => atmEl[id] = {checked: false});
    atmEl['atm-adjust-reference'].checked = true;
    atmEl['atm-bin'].checked = true;
    atmEl['atm-fit-method'] = {value: 'scipy'};
    atmEl['atm-ra-plot'] = {id:'ra', on() {}};
    atmEl['atm-dec-plot'] = {id:'dec', on() {}};
    atmEl['atm-table'] = {};
    atmEl['atm-table-title'] = {};
    atmEl['atm-table-subtitle'] = {};
    atmState.selectedMissions = new Set(['Survey DR1']);
    atmState.selectedCalibrationMethods = new Set(['__none__']);
  `, context);
  const rows = Array.from({length: 5}, (_, i) => ({id:i + 1, ignored:0,
    ra:120 + 7 * i / 3600000, dec:-30 - 3 * i / 3600000,
    measurement_epoch_yr:2010 + i, mission:'Survey DR1', mission_name:'Survey',
    data_release:'DR1', moca_psid:'J', airmass:1.234, single_epoch:1,
    pm_corrected:0, plx_corrected:0, point_of_view:'earth', ra_unc_mas:1, dec_unc_mas:1}));
  context.payload = {rows, target:{moca_oid:432}, reference:{}, pm:{pmra_masyr:0, pmdec_masyr:0}, parallax:{parallax_mas:0}};
  vm.runInContext('atmState.payload = payload', context);
  return {context, plots, rows, run: code => vm.runInContext(code, context)};
}

test('ignored extremes do not affect reference, binning, or ranges in any display mode', () => {
  for (const phase of [false, true]) for (const absolute of [false, true]) {
    const f = fixture();
    f.run(`atmEl['atm-phase-yearly'].checked = ${phase}; atmEl['atm-display-absolute'].checked = ${absolute};`);
    const before = plain(f.run('prepareAstrometryRows()'));
    f.run('renderAstrometryPlot("ra", prepareAstrometryRows()); renderAstrometryPlot("dec", prepareAstrometryRows())');
    const ranges = ['ra','dec'].map(axis => plain(f.plots[axis].layout));
    f.context.payload.rows.push({...f.rows[0], id:'ignored', ignored:'1', ra:200, dec:60, measurement_epoch_yr:2300.3});
    const after = plain(f.run('prepareAstrometryRows()'));
    assert.equal(after.rows.length, before.rows.length + 1);
    assert.deepEqual(after.reference, before.reference);
    assert.deepEqual(after.binned, before.binned);
    assert.deepEqual(after.model, before.model);
    f.run('renderAstrometryPlot("ra", prepareAstrometryRows()); renderAstrometryPlot("dec", prepareAstrometryRows())');
    for (const [index, axis] of ['ra','dec'].entries()) {
      const plot = f.plots[axis];
      assert.deepEqual(plain(plot.layout.xaxis.range), ranges[index].xaxis.range);
      assert.deepEqual(plain(plot.layout.yaxis.range), ranges[index].yaxis.range);
      const ignored = plot.traces.find(t => t.legendgroup === 'astrometry-ignored');
      assert.equal(ignored.marker.symbol, 'x');
      assert.deepEqual(plain(ignored.customdata), ['ignored']);
      assert.match(ignored.text[0], /ignored=1.*excluded from fits/);
      assert.ok(!plot.traces.find(t => t.name === 'Survey DR1').customdata.includes('ignored'));
      assert.equal(plot.config.doubleClick, 'reset');
      assert.ok(plot.config.modeBarButtonsToRemove.includes('autoScale2d'));
      plot.config.modeBarButtonsToAdd[0].click(f.run(`atmEl['atm-${axis}-plot']`));
      assert.deepEqual(plain(f.plots[axis].layout.xaxis.range), ranges[index].xaxis.range);
      assert.deepEqual(plain(f.plots[axis].layout.yaxis.range), ranges[index].yaxis.range);
    }
  }
});

test('ignored rows never enter client fits, requests, fit counts, or fitted curves', () => {
  const f = fixture();
  const baseline = plain(f.run('computeAstrometryFit("pm", prepareAstrometryRows())'));
  f.context.payload.rows.push({...f.rows[0], id:'ignored', ignored:true, ra:200, dec:60, measurement_epoch_yr:2300});
  const actual = plain(f.run('computeAstrometryFit("pm", prepareAstrometryRows())'));
  assert.deepEqual(actual, baseline);
  const body = plain(f.run('buildAstrometryFitRequest("pm", prepareAstrometryRows())'));
  assert.equal(body.rows.length, 5);
  assert.ok(body.rows.every(row => !row.ignored));
  assert.equal(f.run('manualAstrometryFitRows(prepareAstrometryRows().rows).length'), 5);
  f.run('atmState.fitResult = computeAstrometryFit("pm", prepareAstrometryRows())');
  const curve = plain(f.run('buildAstrometryFitCurve(atmState.fitResult, prepareAstrometryRows())'));
  assert.ok(Math.max(...curve.x) < 2020);
});

test('table marks ignored measurements and includes all requested metadata', () => {
  const f = fixture();
  f.context.payload.rows.push({...f.rows[0], id:'ignored', ignored:1, airmass:null});
  f.run('atmState.processedRows = prepareAstrometryRows().rows; renderAstrometryTable()');
  const html = f.run('atmEl["atm-table"].innerHTML');
  for (const label of ['Mission name','Data release','moca_psid','Airmass']) assert.ok(html.includes(`<th>${label}</th>`));
  for (const value of ['Survey','DR1','J','1.234','N/A']) assert.ok(html.includes(`<td>${value}</td>`));
  assert.match(html, /class="astrometry-ignored-row"/);
  assert.match(html, /Ignored \(ignored=1\)/);
  assert.match(html, /Excluded from fits, binning, reference adjustment and automatic ranges/);
  assert.match(html, /aria-label="Ignored measurement">×/);
});

test('only ignored data cannot set the fallback reference or activate Plotly autorange', () => {
  const f = fixture();
  f.context.payload.rows = [{...f.rows[0], ignored:1, ra:200, dec:60, measurement_epoch_yr:2300}];
  const prepared = plain(f.run('prepareAstrometryRows()'));
  assert.equal(prepared.rows.length, 1);
  assert.equal(prepared.reference.ra, 0);
  assert.equal(prepared.reference.epoch, 2000);
  f.run('renderAstrometryPlot("ra", prepareAstrometryRows())');
  assert.deepEqual(plain(f.plots.ra.layout.xaxis.range), [1999,2001]);
  assert.deepEqual(plain(f.plots.ra.layout.yaxis.range), [-1,1]);
  assert.equal(f.run('buildAstrometryFitRequest("pm", prepareAstrometryRows()).rows.length'), 0);
});

test('CSV exports include ignored flags and metadata and respect the table selection', async () => {
  const f = fixture();
  f.context.payload.rows.push({...f.rows[0], id:'ignored', ignored:1, mission_name:'Survey, North', airmass:null});
  let blob;
  const link = {click() {}, remove() {}};
  f.context.Blob = Blob;
  f.context.URL = class extends URL {
    static createObjectURL(value) { blob = value; return 'blob:test'; }
    static revokeObjectURL() {}
  };
  f.context.document.createElement = () => link;
  f.context.document.body = {appendChild() {}};
  vm.runInContext(fs.readFileSync(require.resolve('../mocaviz/static/export_utils.js'), 'utf8'), f.context);
  f.run('MocaExport = window.MocaExport; atmState.selectedOid = 432; atmState.processedRows = prepareAstrometryRows().rows; exportAstrometry("csv")');
  let csv = await blob.text();
  assert.equal(link.download, 'moca_astrometry_oid_432.csv');
  assert.match(csv.split('\n')[0], /ignored,mission,mission_name,data_release,moca_psid,airmass/);
  assert.equal(csv.split('\n').length, 7);
  assert.match(csv, /"Survey, North",DR1,J,,/);
  f.run('atmState.selectedIds = new Set(["ignored"]); exportAstrometry("csv")');
  csv = await blob.text();
  assert.equal(csv.split('\n').length, 2);
  assert.match(csv.split('\n')[1], /^ignored,1,/);
});
