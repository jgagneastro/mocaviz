'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  filterAndSort,
  isCurrentSpectrumLoad,
  matchesFilter,
  mocadbReportUrl,
  navigationDelta,
  qaWarningExplanation,
  qaWarningText,
  sortRows,
  spectrumDrawMode,
  startSpectrumLoad,
  traceDrawOrder,
} = require('../mocaviz/static/spectrum_compare/spectrum_index.js');

const rows = [
  {
    moca_specid: 30,
    moca_oid: 300,
    object_name: 'Late T dwarf',
    spectrum_name: 'new reduction',
    data_reduction_pipeline_version: '1.3.0',
    modification_date: '2026-08-26T10:00:00',
    observing_night: '2022-03-03',
    moca_specpackid: 109,
    moca_instid: 'fire_magellan',
    instrument_mode_name: 'SXD',
    legacy_count: 1,
  },
  {
    moca_specid: 10,
    moca_oid: 100,
    object_name: 'Earlier object',
    spectrum_name: 'older reduction',
    data_reduction_pipeline_version: '1.2.0',
    modification_date: '2026-08-25T09:00:00',
    observing_night: '2023-01-01',
    instrument_mode_name: 'Prism',
    legacy_count: 0,
  },
  {
    moca_specid: 20,
    moca_oid: 200,
    object_name: 'Undated object',
    spectrum_name: 'undated reduction',
    data_reduction_pipeline_version: null,
    modification_date: null,
    observing_night: '2024-01-01',
    instrument_mode_name: 'ECHELLE',
    legacy_count: 1,
  },
];

test('pipeline version is searchable', () => {
  assert.equal(matchesFilter(rows[0], '1.3.0'), true);
  assert.equal(matchesFilter(rows[1], '1.3.0'), false);
});

test('camera and package are searchable in the all-cameras view', () => {
  assert.equal(matchesFilter(rows[0], 'fire'), true);
  assert.equal(matchesFilter(rows[0], '109'), true);
  assert.equal(matchesFilter(rows[0], 'gnirs'), false);
});

test('modification date sorts in both directions with missing dates last', () => {
  assert.deepEqual(sortRows(rows, 'modified-asc').map(row => row.moca_specid), [10, 30, 20]);
  assert.deepEqual(sortRows(rows, 'modified-desc').map(row => row.moca_specid), [30, 10, 20]);
});

test('legacy filtering and version search compose with sorting', () => {
  const result = filterAndSort(rows, '1.3', true, 'modified-desc');
  assert.deepEqual(result.map(row => row.moca_specid), [30]);
});

test('menu count follows search, legacy filters, camera replacement, and empty results', () => {
  const html = require('node:fs').readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  const render = html.slice(html.indexOf('function renderIndex(){'), html.indexOf('async function loadPackages(){'));
  const elements = {
    filter: { value: '' }, 'only-legacy': { checked: false }, sort: { value: 'modified-desc' },
    'filter-count': {}, prev: {}, next: {}, first: {}, last: {}, wiseview: {}, 'open-report': {},
    spectra: { replaceChildren(...children) { this.children = children; } },
  };
  const state = { index: rows, active: -1 };
  const context = require('node:vm').createContext({
    state, $: id => elements[id], filterAndSort, mocadbReportUrl, wiseviewURL: () => null, fmt: value => String(value ?? ''),
    document: { createElement: () => ({ append() {} }) },
  });
  require('node:vm').runInContext(render, context);
  const check = expected => {
    context.renderIndex();
    assert.equal(elements['filter-count'].textContent, expected);
    assert.equal(elements.spectra.children.length, state.filtered.length);
  };
  check('3 spectra shown');
  elements.filter.value = '1.3.0';
  check('1 spectrum shown');
  elements.filter.value = 'no match';
  check('0 spectra shown');
  elements.filter.value = '';
  elements['only-legacy'].checked = true;
  check('2 spectra shown');
  state.index = [rows[1]];
  check('0 spectra shown');
  elements['only-legacy'].checked = false;
  check('1 spectrum shown');
  state.index = [];
  check('0 spectra shown');
  assert.match(html, /id="filter"[^>]*>\s*<div id="filter-count"/);
});

test('horizontal and vertical arrow keys share previous/next navigation', () => {
  assert.equal(navigationDelta('ArrowLeft'), -1);
  assert.equal(navigationDelta('ArrowUp'), -1);
  assert.equal(navigationDelta('ArrowRight'), 1);
  assert.equal(navigationDelta('ArrowDown'), 1);
  assert.equal(navigationDelta('PageDown'), 0);
});

test('revealing the active spectrum scrolls only its list, not the mobile document', () => {
  const html = require('node:fs').readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  const source = html.slice(html.indexOf('function revealActiveSpectrum(){'), html.indexOf('async function loadSpectrum('));
  let itemRect = { top: 450, bottom: 520 };
  const item = { getBoundingClientRect: () => itemRect };
  const list = {
    scrollTop: 200, clientTop: 1, clientHeight: 300,
    getBoundingClientRect: () => ({ top: 100 }),
    querySelector: () => item,
  };
  const context = require('node:vm').createContext({ $: () => list });
  require('node:vm').runInContext(source, context);
  context.revealActiveSpectrum();
  assert.equal(list.scrollTop, 319);
  itemRect = { top: 75, bottom: 150 };
  context.revealActiveSpectrum();
  assert.equal(list.scrollTop, 293);
  itemRect = { top: 120, bottom: 200 };
  context.revealActiveSpectrum();
  assert.equal(list.scrollTop, 293);
  itemRect = { top: 150, bottom: 650 }; // An oversized item aligns its top.
  context.revealActiveSpectrum();
  assert.equal(list.scrollTop, 342);
  list.querySelector = () => null;
  context.revealActiveSpectrum();
  assert.equal(list.scrollTop, 342);
  assert.doesNotMatch(source, /\.scrollIntoView\(/);
  assert.match(html, /revealActiveSpectrum\(\);/);
});

test('scatter mode replaces line primitives with point primitives', () => {
  assert.equal(spectrumDrawMode(false), 'line');
  assert.equal(spectrumDrawMode(true), 'scatter');
});

test('QA warning subtitle explains each code on its own line and preserves quiet states', () => {
  assert.equal(
    qaWarningText(['TCSHQA=WARNING', 'TCSELQA=WARNING', 'TCSHQA=WARNING']),
    'QA warnings:\nTCSHQA=WARNING — The science/standard wavelength-shift search reached its boundary, or its quality check could not be evaluated.\nTCSELQA=WARNING — The selected telluric standard has metadata or selection caveats, such as uncertain stellar type, airmass, or saturation assessment.',
  );
  assert.equal(qaWarningText([], 'loading…'), 'QA warnings: loading…');
  assert.equal(qaWarningText(null), 'QA warnings: none');
});

test('QA explanations support compact aliases, code-valued warnings, and unknown flags', () => {
  assert.equal(qaWarningExplanation('RV_WCS_QA=WARN'), qaWarningExplanation('RVWCSQA=WARN'));
  assert.equal(qaWarningExplanation('SEEING_QA=WARN'), qaWarningExplanation('SEEQA=WARN'));
  assert.equal(qaWarningExplanation(' tcshqa = warning '), qaWarningExplanation('TCSHQA=WARNING'));
  assert.match(qaWarningExplanation('TELLURIC_QA=QA_FAILED'), /Earth’s atmosphere/);
  assert.match(qaWarningExplanation('CALIBRATION_WARNING=DROPPED_INVALID_ECHELLE_ORDERS'), /arc-tilt/);
  assert.match(qaWarningExplanation('TELLURIC_SHIFT_SEARCH_QA_UNAVAILABLE'), /insufficient/);
  assert.match(qaWarningExplanation('TELLURIC_SHIFT_SEARCH_BOUNDARY'), /zero-shift fallback/);
  assert.match(qaWarningExplanation('EXSCQA=WARNING'), /exposure flux scales.*no usable samples/);
  assert.match(qaWarningExplanation('F2RSPQA=WARNING'), /quality warnings do not add pixel masks/);
  assert.match(qaWarningExplanation('FUTUREQA=WARNING'), /No explanation is available/);
  assert.equal(qaWarningText(['relative flux calibration is uncertain']), 'QA warnings:\nrelative flux calibration is uncertain');
  assert.equal(qaWarningText([' ', null, '', 'SCIQA=NEEDS_REVIEW', 'SCIQA=NEEDS_REVIEW']).split('\n').length, 2);
});

test('metadata renders explanations as safe text and clears them when changing spectra', () => {
  const html = require('node:fs').readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  const source = html.slice(html.indexOf('function setMeta('), html.indexOf('function renderIndex('));
  let hasWarnings;
  const elements = {
    'meta-primary': {},
    'meta-warnings': { classList: { toggle: (name, value) => { hasWarnings = value; } } },
  };
  const context = require('node:vm').createContext({ $: id => elements[id], qaWarningText });
  require('node:vm').runInContext(source, context);
  context.setMeta('Example spectrum', ['TCSHQA=WARNING', '<img src=x onerror=alert(1)>']);
  assert.match(elements['meta-warnings'].textContent, /wavelength-shift search/);
  assert.match(elements['meta-warnings'].textContent, /<img src=x onerror=alert\(1\)>/);
  assert.equal(elements['meta-warnings'].title, elements['meta-warnings'].textContent);
  assert.equal(hasWarnings, true);
  assert.doesNotMatch(source, /innerHTML/);
  context.setMeta('Next spectrum', null, 'loading…');
  assert.equal(elements['meta-warnings'].textContent, 'QA warnings: loading…');
  assert.equal(hasWarnings, false);
  context.setMeta('Next spectrum', [], 'none');
  assert.equal(elements['meta-warnings'].textContent, 'QA warnings: none');
  assert.match(html, /#meta-warnings \{[^}]*white-space:pre-line;[^}]*overflow-wrap:anywhere;[^}]*overflow:auto;/);
  assert.match(html, /id="meta-warnings" tabindex="0"/);
});

test('arrow keys scroll focused warning explanations without changing spectra', () => {
  const html = require('node:fs').readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  const source = html.slice(html.indexOf("window.addEventListener('keydown'"), html.indexOf("  const canvas=$('plot');"));
  let listener, steps = 0, prevented = false;
  const context = require('node:vm').createContext({
    window: { addEventListener: (name, callback) => { listener = callback; } },
    $: () => ({open: false}),
    navigationDelta, step: delta => { steps += delta; }, openMocadbReport() {},
  });
  require('node:vm').runInContext(source, context);
  const event = { key: 'ArrowDown', target: { matches: () => false, closest: () => ({}) }, preventDefault: () => { prevented = true; } };
  listener(event);
  assert.equal(steps, 0);
  assert.equal(prevented, false);
  event.target.closest = () => null;
  listener(event);
  assert.equal(steps, 1);
  assert.equal(prevented, true);
});

test('GUI cache-busts the QA helper and retains a stale-helper fallback', () => {
  const html = require('node:fs').readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /spectrum_index\.js\?v=20260910-qa-explanations-1/);
  assert.match(html, /typeof indexQaWarningText==='function'/);
});

test('new reductions draw after exact and approximate legacy comparators', () => {
  const traces = [
    { kind: 'new' },
    { kind: 'legacy' },
    { kind: 'approximate_legacy' },
    { kind: 'new' },
  ];
  assert.deepEqual(traceDrawOrder(traces), [1, 2, 0, 3]);
});

test('starting a load immediately removes the previous spectrum', () => {
  const state = {
    active: 10,
    loading: false,
    loadRequestId: 4,
    traces: [{ metadata: { moca_specid: 10 } }],
    xFull: [8000, 25000],
    xView: [9000, 20000],
  };
  const requestId = startSpectrumLoad(state, 20);
  assert.equal(requestId, 5);
  assert.equal(state.active, 20);
  assert.equal(state.loading, true);
  assert.deepEqual(state.traces, []);
  assert.equal(state.xFull, null);
  assert.equal(state.xView, null);
});

test('API requests time out with an actionable retry message', () => {
  const html = require('node:fs').readFileSync('./mocaviz/templates/spectrum_compare.html', 'utf8');
  assert.match(html, /new AbortController\(\)/);
  assert.match(html, /setTimeout\(\(\)=>controller\.abort\(\),timeoutMs\)/);
  assert.match(html, /Request timed out; tap the spectrum to retry\./);
  assert.match(html, /finally \{ clearTimeout\(timer\); controllers.delete\(controller\); \}/);
});

test('only the newest spectrum request may update the plot', () => {
  const state = { loadRequestId: 0 };
  const first = startSpectrumLoad(state, 10);
  const second = startSpectrumLoad(state, 20);
  assert.equal(isCurrentSpectrumLoad(state, first), false);
  assert.equal(isCurrentSpectrumLoad(state, second), true);
});

test('MOCAdb report URL uses the active numeric OID', () => {
  assert.equal(
    mocadbReportUrl(4323580),
    'https://mocadb.ca/search/results?search-query=oid%284323580%29&search-type=star',
  );
  assert.equal(mocadbReportUrl(null), null);
  assert.equal(mocadbReportUrl('not-an-oid'), null);
});
