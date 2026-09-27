# Private GNIRS planner — 2026-09-27

The existing GNIRS RV and SXD interface now runs in MOCAviz. Its layout, controls,
science defaults, timing interpolation, target reports and browser canvas plot
are retained. There is no link in either public dataviz index.

## Access

Open `/gnirs-planner` or `/js/gnirs-planner` to enter the collaborator account and
password, or supply the usual URL parameters:

```text
https://mocadb.ca/js/gnirs-planner?user=collaborators&pwd=YOUR_URL_ENCODED_PASSWORD
```

`username`/`password` aliases are accepted. Optional `dbase` must be
`mocadb_private_tables`; `management` also works when explicitly supplied.
Use `&mode=sxd` to open the SXD view. The example contains a placeholder, never
a working password. Do not put working URLs in tickets, scripts or documents.

Every page/API request opens a new MOCAdb connection using only that request's
credentials and checks `CURRENT_USER()`. Public, missing, invalid or conflicting
credentials are rejected, including against a warm cache. The planner never
uses the main application's public account, credential environment variables,
`.env`, auth files, saved database engines, cookies, localStorage or sessionStorage.

The browser preserves all supplied URL parameters, including the username and
password, on load and when switching observing modes. Reloading reuses the
credentials in the URL. Subsequent POST APIs use credentials held in page memory
as request headers.
Responses have `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.
Regeneration keeps its submitted credentials in memory only for that operation;
errors are sanitized. The application does not save credentials to server files.

## Exactly one shared persistent data file

Set **one path for all workers and users**:

```sh
export MOCAVIZ_GNIRS_CACHE_FILE=/var/lib/mocaviz/gnirs.sqlite
export PYTHONDONTWRITEBYTECODE=1
```

This is configuration, not authentication. Install the SQLite file outside
every web/static root, owned by the web-service user with mode `0600`. Do not
use a network filesystem, user-specific path, per-worker copy, or symlink.
The application rejects its own static directory as a cache location; the
administrator must also keep it outside any other configured web root.

The file contains catalog rows, visibility summaries, both calibrated timing
grids, model tracks, provenance, refresh status and the rebuild lease. Selection
results are bounded to four RAM entries per worker. APIs carry filter state so
requests can move between workers without sticky sessions or persisted jobs.
The plot is limited to 12,000 sampled display points when necessary; selection
counts, totals and exports still include every selected object.

Normal browsing, filters, target inspection, detailed visibility, cache reload
and CSV export open SQLite read-only and create no files. Canvas plots are
rendered in the browser; exports use memory and browser downloads. No PNGs,
temporary exports, per-user caches, logs, session files or ITC downloads are
created by the planner.

**Regenerate catalog** is the one interactive cache-writing operation. It reads
MOCAdb in pages using a consistent read-only database transaction and updates
this same file. A lease stored in SQLite serializes users/processes; each batch
renews it, and an expired owner cannot continue writing. Published data remain
available during collection. A candidate table inside the same file is swapped
in atomically. Ordinary failures roll back publication and retain the previous
catalog. SQLite uses RAM journals and temporary stores, never WAL, SHM, disk
journals or separate lock files. Auto-vacuum releases obsolete table pages.

The complete M5+ seed has **870,418 objects and occupies 2.97 GiB** (2026-09-27).
User count does not multiply this disk use. A refresh temporarily holds the old
and candidate tables *inside that same file* and needs roughly twice the catalog
disk space. Final publication/indexing can also require substantial RAM for the
in-memory journal and sorts; allow several GiB of headroom and avoid refreshes
during peak use. This is an explicit consequence of the one-file requirement.
An OS crash/power loss while writing a RAM-journal database can corrupt this
rebuildable cache: re-import the seed if integrity fails. No automatic backup
copies are written to the server.

Catalog refresh reuses the deployed RV/SXD calibrations and historical archive
audit/component-photometry overrides. It queries current MOCAdb photometry,
membership, astrometry, RVs, spectral types and GNIRS coverage. It does not
rerun the public Gemini archive audit or the Gemini ITC. Recompute timing grids
on the development machine and replace the single deployment bundle when the
instrument prescription changes. The local tool's ITC-regeneration button is
therefore hidden in this server version.

## Build and install the seed

On the development machine, using the repo's dependencies (Python 3.11+):

```sh
PYTHONDONTWRITEBYTECODE=1 python -B scripts/import_gnirs_planner_cache.py \
  --source /path/to/gnirs_target_selector \
  --output /private/path/gnirs.sqlite
```

The output must not already exist. The importer follows the source's current
catalog pointer and copies an explicit allowlist of scientific metadata and
the RV/SXD timing grids. It never reads `.auth.json`, `access.txt`, `.env`, logs
or credential URLs. The seed is private data: **do not commit it or put it in
static assets**. Transfer just this one file to the server, set ownership and
permissions, and set the shared path above. Stop planner workers before
replacing an existing seed; do not replace it underneath a running rebuild.

## Web-server configuration is part of the no-file guarantee

Application code cannot suppress an upstream server's access logs or response
spooling. URL credentials accompany page loads and remain in the address bar.
The hosting configuration must disable credential-bearing request
logging/tracing and request/response disk buffering for these routes.

The supplied strict deployment option keeps the planner in this repository,
using `gnirs_wsgi.py` with `deploy/gnirs.gunicorn.py` and
`deploy/gnirs.nginx.conf.example`. It proxies only the planner page, API and
assets; other MOCAviz pages can retain the existing Passenger deployment.

```sh
# In the deployed mocaviz repository, using its installed requirements:
gunicorn --config deploy/gnirs.gunicorn.py gnirs_wsgi:application
```

This Linux profile uses a loopback upstream, no access/error-log files, bounded
request bodies, no proxy caching/spooling, and shared-memory worker heartbeats.
The isolated entry points Astropy at the shipped read-only configuration
directory, so first use does not create a home-directory configuration/cache.
Merge the example into the HTTPS virtual host, check location precedence and
run `nginx -t` before reloading. If Passenger is globally enabled, ensure this
location is handled by `proxy_pass`, not the Passenger application handler.
Also disable any outer proxy/CDN/APM request capture for these paths. Keep
debuggers off. A read-only application mount with only the existing SQLite
file writable provides additional enforcement; its directory need not be
writable during use.

Do not claim the strict server guarantee merely from `passenger_buffer_response
off`: Passenger documents an additional always-on disk-backed buffer. Use the
unbuffered Gunicorn upstream for this requirement. See the official
[Passenger buffering reference](https://www.phusionpassenger.com/library/config/nginx/reference/#passenger_response_buffer_high_watermark),
[Nginx proxy buffering controls](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering),
[request-body controls](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_body_buffer_size),
and [access-log controls](https://nginx.org/en/docs/http/ngx_http_log_module.html#access_log).

Source integration and local verification do not deploy or reconfigure the live
MOCAdb web server. Install the cache and hosting configuration before sharing a
working password-bearing URL.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests -p test_gnirs_planner.py -v
PYTHONDONTWRITEBYTECODE=1 python -B scripts/check_gnirs_no_files.py
```

Tests use explicitly synthetic credentials, verify access denial with a warm
cache, both modes and all read/export APIs, cross-worker selection recovery,
rollback across DROP/RENAME, concurrent refresh requests, cross-process leases,
stale-worker fencing and the absence of sidecar files. The no-file audit rejects
filesystem mutation attempts during browsing and export, including writable
SQLite connections. Chromium checks verify both modes, plot and
target-report rendering with the original styling. No live database password is
needed for these tests; live server authentication and full online regeneration
still require a deployment smoke test with credentials entered by the user.
