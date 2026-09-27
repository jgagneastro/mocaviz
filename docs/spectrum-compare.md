# Private reduction comparison

The existing reduction viewer is available within the production MoCaViz WSGI
application at `/spectrum-compare` (also `/js/spectrum-compare`). It is deliberately
absent from the public data-visualization index and has `noindex` response headers.
The unauthenticated page is an empty sign-in shell: every data request must
authenticate as `collaborators` or `management` against `mocadb_private_tables`.
Both accounts have **read-only behavior in this tool**. There are no database-write
routes or production mock mode.

## Credentials

Open the page and enter the username and password in its form, or provide them
through the URL. The preferred link format is:

```text
https://YOUR-MOCAVIZ-HOST/spectrum-compare#user=collaborators&pwd=URL_ENCODED_PASSWORD&dbase=mocadb_private_tables
```

Replace the placeholder with your actual, URL-encoded password only in your
browser. The `#` fragment is not sent to the web server. Existing MoCaViz-style
`?user=…&pwd=…&dbase=…` links also work, but their **initial page request can be
recorded by web-server access logs**; use the fragment or form to avoid this.
Aliases `username`, `password`, `db`, and `database` are accepted by the page.
Conflicting values are rejected. Custom database hosts/ports are not accepted.

The page preserves supplied credentials and other parameters in the visible URL
on load and refresh, so the same link can be reloaded or bookmarked. This also
means credentials remain in browser history/bookmarks; protect those links.
The page reads them into its JavaScript closure and sends them in `X-MOCA-*`
headers on same-origin API requests. API query strings never carry credentials and are
rejected if they do. Responses use `Cache-Control: no-store` and
`Referrer-Policy: no-referrer`. No cookies, local/session storage, browser
database, server session, saved credentials, environment credential fallbacks,
connection pools or cross-request response caches are used by this feature.
Explicit Sign out (`Q`) clears the data and credentials, removes credential
parameters from the URL, and cancels pending work. An authentication error keeps
the URL intact so it can be corrected. Reloading a credential-bearing URL signs
in again; credentials entered only in the form must be re-entered after reload.
An invalid password never falls back to public data.

Use HTTPS in production. Do not configure the front proxy to log authorization
headers. The repository contains no collaborator or management password for
this feature; tests use synthetic/generated strings only.

## Database connection and deployment

The feature is registered by `mocaviz/app.py`; no second service, local reduction
checkout, mounted archive or additional dependency is required. Start Passenger/
WSGI using the project's existing `app:application` entry point and environment.

By default, local development and deployment both connect directly to
`mocadb.ca:3306` through PyMySQL, using the same TLS options as the existing
MoCaViz private pages: `ssl={"verify_mode": False, "check_hostname": False}`.
Traffic is encrypted, but the self-signed server certificate and hostname are
not verified. This compatibility policy does not protect against server
impersonation. No SSH tunnel or socket setting is required. Credentials still
come only from the current request, and each connection is read-only and closed
after use; no credential-bearing connection pool is retained.

For local testing, start MoCaViz in its usual Python environment:

```bash
python -B app.py
```

If a previous workaround set `MOCAVIZ_COMPARE_UNIX_SOCKET`, unset it (and remove
it from your local `.env`, if present) to restore the default direct connection.

Optionally, on the machine that runs MariaDB, configure its existing Unix socket:

```text
MOCAVIZ_COMPARE_UNIX_SOCKET=/run/mysqld/mysqld.sock
PYTHONDONTWRITEBYTECODE=1
```

Confirm the real socket path with your database administrator. It must be an
absolute path accessible to the web application's account. This uses local IPC,
not a network connection; the supplied collaborator credentials must still pass
MariaDB authentication and `CURRENT_USER()` verification. No database credential
belongs in deployment configuration. Requests cannot override the socket.

This change does not modify MariaDB or the live deployment.

## No runtime files

This page reads database rows into memory and returns JSON. Plotting, line
overlays, velocity smoothing, normalization display, zoom and pan are browser
canvas/worker operations. It does not invoke Matplotlib, PNG rendering, FITS
downloads, pipeline code, temporary files, disk caches, job runners or file logs.
Static HTML and JS are read-only deployment assets. Every DB request has a fresh
read-only transaction that is rolled back and closed on success or failure.

The zero-file-write guarantee is for the feature's application code. Configure
Passenger/reverse-proxy access/error logging separately if the hosting requirement
also prohibits infrastructure log writes. Use `PYTHONDONTWRITEBYTECODE=1` when
starting workers to suppress Python import caches from startup onward. The new
module also disables bytecode writes before request-time lazy imports.

## Preserved reviewer behavior

The port retains all-camera selection; name/specid/OID/pipeline filtering; date
sorting; up to three legacy comparisons and same-object approximate fallback;
QA explanations; ignored points; scatter and S/N modes; OH/H/BD/atmosphere
overlays; micron readout; x-only zoom with automatic y range; and adaptive
velocity smoothing with a fast preview then robust polynomial worker refinement.
Wavelength bounds follow the main spectrum and normalization uses shared windows.
Navigation uses the arrow keys, Home/End; O opens the object report, W opens
WiseView where coordinates exist, R/M select y-range modes, Z resets zoom,
and Q signs out. No classification/undo workflow or database mutation is added.

The comparison algorithms and bundled reference assets were ported from
`moca-shared-tools/spectrum_compare` at `215df27`; atmospheric reference provenance
is retained in `static/spectrum_compare/atran_reference.js`.

## Verification

```bash
python -B -m unittest discover -s tests -p 'test_spectrum_compare*.py' -v
node --test tests/test_compare_*.js
```

The access tests exercise real root and `/js` WSGI routing with a synthetic DB,
reject unauthenticated requests even when environment credentials exist, verify
transaction cleanup/TLS, ensure responses bypass caches, and install a Python
audit hook that rejects filesystem mutation during HTML, asset and API requests.
They never authenticate to the real database. The separate localhost-only
`tests/serve_spectrum_compare_fixture.py` can drive `scripts/chromium_probe.mjs`
with synthetic spectra while the same file-write guard is active. That fixture
is never imported or exposed by production.
