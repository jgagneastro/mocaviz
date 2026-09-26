'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {randomBytes} = require('node:crypto');
const {fromURL} = require('../mocaviz/static/spectrum_compare/access.js');

test('query and fragment aliases decode credentials and remove them from browser URL', () => {
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
