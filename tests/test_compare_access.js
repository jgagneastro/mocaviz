'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {randomBytes} = require('node:crypto');
const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const {fromURL} = require('../mocaviz/static/spectrum_compare/access.js');
const html = readFileSync(require.resolve('../mocaviz/templates/spectrum_compare.html'), 'utf8');

test('query and fragment aliases decode credentials and provide a URL for explicit sign-out', () => {
  for (const delimiter of ['?', '#']) {
    const password = randomBytes(12).toString('base64') + '&+#%=';
    const params = new URLSearchParams({username: 'collaborators', password, database: 'mocadb_private_tables', specid: '42'});
    const access = fromURL('https://example.invalid/js/spectrum-compare' + delimiter + params);
    assert.equal(access.ready(), true);
    assert.equal(access.headers()['X-MOCA-Password'], password);
    assert.equal(access.cleanURL, '/js/spectrum-compare' + delimiter + 'specid=42');
    access.clear();
    assert.equal(access.ready(), false);
    assert.equal(access.headers()['X-MOCA-Password'], '');
  }
});

test('page startup preserves supplied query and fragment credentials through reloads', () => {
  const startup = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
  for (const delimiter of ['?', '#']) {
    const password = randomBytes(12).toString('base64') + '&+#%=';
    const params = new URLSearchParams({user: 'collaborators', pwd: password,
      dbase: 'mocadb_private_tables', host: 'mocadb.ca', port: '3306', specid: '42'});
    const href = 'https://example.invalid/js/spectrum-compare' + delimiter + params;
    // Each load gets a fresh access closure, just like a full browser reload.
    for (let load = 0; load < 2; load++) {
      const replacements = [];
      const context = {window: {}, location: {href}, SpectrumCompareAccess: {fromURL},
        history: {replaceState: (...args) => replacements.push(args)}};
      runInNewContext(startup, context);
      assert.deepEqual(replacements, []);
      assert.equal(context.location.href, href);
      assert.equal(context.window.comparisonAccess.headers()['X-MOCA-Password'], password);
      assert.equal(context.window.comparisonAccess.ready(), true);
    }
  }
});

test('only explicit sign-out clears credentials from the browser URL', () => {
  assert.match(html, /if\(clearURL\)history\.replaceState\(null,'',access\.cleanURL\)/);
  assert.match(html, /\$\('quit'\)\.onclick=\(\)=>signOut\(undefined,true\)/);
  assert.match(html, /if\(response\.status===401\|\|response\.status===403\)signOut\(data\.error\|\|'Credentials were rejected\.'\)/);
  assert.equal((html.match(/history\.replaceState/g) || []).length, 1);
});

test('conflicting credentials, public database, and arbitrary hosts fail closed', () => {
  for (const suffix of ['?user=collaborators&user=management&pwd=x',
    '?user=collaborators&pwd=x#password=y', '?user=collaborators&pwd=x&dbase=mocadb',
    '?user=collaborators&pwd=x&host=other.invalid', '?user=collaborators&pwd=x&port=3307']) {
    const access = fromURL('https://example.invalid/spectrum-compare' + suffix);
    assert.equal(access.ready(), false);
    assert.ok(access.error);
    assert.equal(access.cleanURL, '/spectrum-compare');
  }
});

test('absent or public credentials cannot load the tool; explicit form entry can', () => {
  const access = fromURL('https://example.invalid/spectrum-compare');
  assert.equal(access.ready(), false);
  access.set('public', 'not-a-real-password');
  assert.equal(access.ready(), false);
  access.set('collaborators', '');
  assert.equal(access.ready(), false);
  access.set('collaborators', randomBytes(16).toString('hex'));
  assert.equal(access.ready(), true);
});
