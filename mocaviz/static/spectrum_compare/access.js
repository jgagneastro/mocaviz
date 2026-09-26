(function (root) {
  'use strict';
  const fields = {
    user: ['user', 'username'], password: ['pwd', 'password'],
    database: ['dbase', 'db', 'database'], host: ['host'], port: ['port'],
  };
  function fromURL(href) {
    const url = new URL(href), fragment = new URLSearchParams(url.hash.slice(1));
    const values = {}, errors = [];
    for (const [field, aliases] of Object.entries(fields)) {
      const supplied = aliases.flatMap(key => [...url.searchParams.getAll(key), ...fragment.getAll(key)]);
      if (new Set(supplied).size > 1) errors.push('Conflicting URL credentials. Enter them below.');
      values[field] = supplied[0] || '';
      for (const key of aliases) { url.searchParams.delete(key); fragment.delete(key); }
    }
    url.hash = fragment.toString();
    if ((values.database && values.database !== 'mocadb_private_tables') ||
        (values.host && values.host !== 'mocadb.ca') || (values.port && values.port !== '3306'))
      errors.push('This tool requires the private database at mocadb.ca.');
    const error = errors[0] || '';
    let user = error ? '' : values.user, password = error ? '' : values.password;
    return {
      cleanURL: url.pathname + url.search + url.hash,
      error,
      ready: () => ['collaborators', 'management'].includes(user) && Boolean(password),
      headers: () => ({'X-MOCA-User': user, 'X-MOCA-Password': password, 'X-MOCA-Database': 'mocadb_private_tables'}),
      set(nextUser, nextPassword) { user = nextUser; password = nextPassword; },
      clear() { user = ''; password = ''; },
    };
  }
  if (typeof module === 'object' && module.exports) module.exports = {fromURL};
  else root.SpectrumCompareAccess = {fromURL};
})(globalThis);
