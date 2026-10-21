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
     'atm-display-absolute', 'atm-bin', 'atm-ignore-duplicates'].forEach(id => atmEl[id] = {checked: false});
    atmEl['atm-adjust-reference'].checked = true;
    atmEl['atm-bin'].checked = true;
    atmEl['atm-ignore-duplicates'].checked = true;
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

test('ignored calibrated rows do not suppress the fallback to active uncalibrated measurements', () => {
  const f = fixture();
  f.run('atmEl["atm-only-recalibrated"].checked = true');
  const before = plain(f.run('prepareAstrometryRows()'));
  f.context.payload.rows.push({...f.rows[0], id:'ignored', ignored:1, calibration_method:'ignored-only calibration'});
  const after = plain(f.run('prepareAstrometryRows()'));
  assert.deepEqual(after.rows, before.rows);
  assert.deepEqual(after.model, before.model);
  assert.equal(after.usedFallbackRecalibration, true);
});

test('table marks ignored measurements and includes all requested metadata', () => {
  const f = fixture();
  f.context.payload.rows.push({...f.rows[0], id:'ignored', ignored:1, airmass:null, measurement_epoch_yr:2020});
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
  f.context.payload.rows.push({...f.rows[0], id:'ignored', ignored:1, mission_name:'Survey, North', airmass:null, measurement_epoch_yr:2020});
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

test('duplicate detection keeps one deterministic copy without changing reference, bins, fits, or ranges', () => {
  const f = fixture();
  const before = plain(f.run('prepareAstrometryRows()'));
  const fit = plain(f.run('computeAstrometryFit("pm", prepareAstrometryRows())'));
  f.context.payload.rows.unshift({...f.rows[0], id:99});
  const after = plain(f.run('prepareAstrometryRows()'));
  assert.equal(after.rows.length, 6);
  const duplicate = after.rows.find(row => row.auto_duplicate);
  assert.equal(duplicate.id, 99);
  assert.equal(duplicate.duplicate_of_id, 1);
  assert.equal(duplicate.ignored, 0);
  assert.deepEqual(after.reference, before.reference);
  assert.deepEqual(after.binned, before.binned);
  assert.deepEqual(after.model, before.model);
  assert.deepEqual(plain(f.run('computeAstrometryFit("pm", prepareAstrometryRows())')), fit);
  assert.equal(f.run('buildAstrometryFitRequest("pm", prepareAstrometryRows()).rows.length'), 5);
  f.run('renderAstrometryPlot("ra", prepareAstrometryRows()); atmState.processedRows = prepareAstrometryRows().rows; renderAstrometryTable()');
  assert.ok(f.plots.ra.traces.every(t => !t.customdata?.includes(99)));
  assert.ok(!f.plots.ra.traces.some(t => t.legendgroup === 'astrometry-duplicates'));
  assert.doesNotMatch(f.run('atmEl["atm-table"].innerHTML'), /<td>99<\/td>/);
  let exported;
  f.context.MocaExport = {saveTable(format, options) { exported = plain(options); }};
  f.run('exportAstrometry("csv")');
  assert.equal(exported.rows.length, 5);
  assert.ok(exported.rows.every(row => row.id !== 99));
  f.run('atmEl["atm-ignore-duplicates"].checked = false');
  assert.equal(f.run('prepareAstrometryRows().rows.filter(r => r.auto_duplicate).length'), 0);
  assert.equal(f.run('buildAstrometryFitRequest("pm", prepareAstrometryRows()).rows.length'), 6);
  f.run('atmState.processedRows = prepareAstrometryRows().rows; renderAstrometryTable(); exportAstrometry("csv")');
  assert.match(f.run('atmEl["atm-table"].innerHTML'), /<td>99<\/td>/);
  assert.equal(exported.rows.length, 6);
});

test('duplicate comparisons use exact positions, absolute epochs, and all uncertainties', () => {
  for (const key of ['ra','dec','measurement_epoch_yr','ra_unc_mas','dec_unc_mas','measurement_epoch_yr_unc']) {
    const f = fixture();
    const original = {...f.rows[0], measurement_epoch_yr_unc:0.01};
    const near = {...original, id:2, [key]: original[key] + Math.abs(original[key]) * Number.EPSILON * 2};
    const rows = [original, near];
    f.context.comparisonRows = rows;
    f.run('markDuplicatedAstrometryRows(comparisonRows, false)');
    assert.ok(rows.every(row => row.auto_duplicate === 0), `${key} must match exactly`);
  }
  const f = fixture();
  f.context.comparisonRows = [
    {...f.rows[0], id:1, ra_unc_mas:null}, {...f.rows[0], id:2, ra_unc_mas:null},
  ];
  f.run('markDuplicatedAstrometryRows(comparisonRows, false)');
  assert.ok(f.context.comparisonRows.every(row => row.auto_duplicate === 0));
  f.context.payload.rows = [{...f.rows[0], id:1, measurement_epoch_yr:2010.25},
    {...f.rows[0], id:2, measurement_epoch_yr:2011.25}];
  f.run('atmEl["atm-phase-yearly"].checked = true');
  assert.equal(f.run('prepareAstrometryRows().rows.filter(r => r.auto_duplicate).length'), 0);
});

test('ignored, manually rejected, or fit-ineligible copies cannot displace the usable representative', () => {
  const f = fixture();
  f.context.payload.rows = [
    {...f.rows[0], id:1, ignored:1}, {...f.rows[0], id:2, single_epoch:0},
    {...f.rows[0], id:3}, {...f.rows[0], id:4}, {...f.rows[0], id:5},
  ];
  f.run('atmState.manualRejectedIds.add("3")');
  const rows = plain(f.run('prepareAstrometryRows().rows'));
  assert.deepEqual(rows.filter(row => row.auto_duplicate).map(row => row.id), [1,2,3,5]);
  assert.ok(rows.filter(row => row.auto_duplicate).every(row => row.duplicate_of_id === 4));
  assert.deepEqual(plain(f.run('buildAstrometryFitRequest("pm", prepareAstrometryRows()).rows.map(r => r.id)')), [4]);
});

test('raw-coordinate and mission filters recompute which copies are duplicates', () => {
  const f = fixture();
  f.context.payload.rows = [{...f.rows[0], id:1, raw_ra:119, raw_dec:-30},
    {...f.rows[0], id:2, raw_ra:118, raw_dec:-30, mission:'Other survey'}];
  f.run('atmState.selectedMissions.add("Other survey")');
  assert.equal(f.run('prepareAstrometryRows().rows.filter(r => r.auto_duplicate).length'), 1);
  f.run('atmEl["atm-revert-raw"].checked = true');
  assert.equal(f.run('prepareAstrometryRows().rows.filter(r => r.auto_duplicate).length'), 0);
  f.run('atmEl["atm-revert-raw"].checked = false; atmState.selectedMissions = new Set(["Other survey"])');
  const rows = plain(f.run('prepareAstrometryRows().rows'));
  assert.equal(rows.length, 1);
  assert.equal(rows[0].auto_duplicate, 0);
  assert.equal(rows[0].id, 2);
});

test('an unadopted server fallback reference is recomputed from unique measurements', () => {
  const f = fixture();
  f.run('atmEl["atm-adjust-reference"].checked = false');
  const baseline = plain(f.run('prepareAstrometryRows().reference'));
  f.context.payload.reference = {...f.rows[0], fallback:true};
  f.context.payload.rows.push({...f.rows[0], id:99});
  const actual = plain(f.run('prepareAstrometryRows().reference'));
  assert.equal(actual.ra, baseline.ra);
  assert.equal(actual.dec, baseline.dec);
  assert.equal(actual.epoch, baseline.epoch);
});

function ignoreActionFixture() {
  const f = fixture();
  f.run(`
    atmEl['atm-ignore-tools'] = {hidden:true};
    atmEl['atm-ignore-selected'] = {disabled:true};
    atmEl['atm-ignore-comments'] = {value:'  Added note  '};
    atmEl['atm-ignore-selection-note'] = {};
    atmEl['atm-ignore-status'] = {classList:{toggle() {}}};
    atmState.authContext = {role:'management', private_db:true};
    atmState.selectedOid = 432;
    atmState.processedRows = prepareAstrometryRows().rows;
    atmState.selectedIds = new Set([1]);
    setAstrometryFitDisabled = () => {};
    clearAstrometryFit = () => { atmState.fitResult = null; };
    loadAstrometryObject = async () => {};
  `);
  const calls = [];
  f.context.rpc = async (path, body) => {
    calls.push({path, body:plain(body)});
    return body.dryRun
      ? {ok:true, wouldUpdateCount:1, selectedCount:1, selectedIds:[1], alreadyIgnoredCount:0, revision:'preview-state'}
      : {ok:true, updatedCount:1, newlyIgnoredCount:1};
  };
  f.run('postAstrometryJson = rpc');
  return {...f, calls};
}

test('database ignore controls are management-only and require selected rows', async () => {
  const f = ignoreActionFixture();
  f.run('atmState.authContext.role = "collaborators"; updateAstrometryManagementVisibility()');
  assert.equal(f.run('atmEl["atm-ignore-tools"].hidden'), true);
  assert.equal(f.run('atmEl["atm-ignore-selected"].disabled'), true);
  await f.run('runAstrometryIgnoreSelected()');
  assert.equal(f.calls.length, 0);
  f.run('atmState.authContext.role = "management"; updateAstrometryManagementVisibility()');
  assert.equal(f.run('atmEl["atm-ignore-tools"].hidden'), false);
  assert.equal(f.run('atmEl["atm-ignore-selected"].disabled'), false);
  f.run('atmState.selectedIds.clear(); updateAstrometryIgnoreControls()');
  assert.equal(f.run('atmEl["atm-ignore-selected"].disabled'), true);
});

test('cancelling the reviewed selection never sends an apply request', async () => {
  const f = ignoreActionFixture();
  f.context.window.confirm = () => false;
  await f.run('runAstrometryIgnoreSelected()');
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].body.dryRun, true);
  assert.match(f.run('atmEl["atm-ignore-status"].textContent'), /Cancelled/);
  assert.equal(f.run('atmState.ignoreBusy'), false);
});

test('confirmed ignore requests apply the same target, IDs, comments, and preview state', async () => {
  const f = ignoreActionFixture();
  let confirmation;
  f.context.window.confirm = text => { confirmation = text; return true; };
  await f.run('runAstrometryIgnoreSelected()');
  assert.equal(f.calls.length, 2);
  const {dryRun, expectedRevision, ...applied} = f.calls[1].body;
  assert.equal(dryRun, false);
  assert.equal(expectedRevision, 'preview-state');
  const {dryRun: previewOnly, ...previewBody} = f.calls[0].body;
  assert.deepEqual(applied, previewBody);
  assert.equal(applied.moca_oid, '432');
  assert.deepEqual(applied.selectedIds, ['1']);
  assert.equal(applied.appendComments, 'Added note');
  assert.match(confirmation, /oid432/);
  assert.match(confirmation, /Added note/);
  assert.equal(f.run('atmState.selectedIds.size'), 0);
  assert.equal(f.run('atmEl["atm-ignore-comments"].value'), '');
  assert.match(f.run('atmEl["atm-ignore-status"].textContent'), /Updated 1 entries/);
});

test('changing the selection during preview requires a new review', async () => {
  const f = ignoreActionFixture();
  let confirmations = 0;
  f.context.window.confirm = () => { confirmations++; return true; };
  const original = f.context.rpc;
  f.context.rpc = async (path, body) => {
    const response = await original(path, body);
    f.run('atmState.selectedIds = new Set([2])');
    return response;
  };
  f.run('postAstrometryJson = rpc');
  await f.run('runAstrometryIgnoreSelected()');
  assert.equal(f.calls.length, 1);
  assert.equal(confirmations, 0);
  assert.match(f.run('atmEl["atm-ignore-status"].textContent'), /selection or target changed/);
});
