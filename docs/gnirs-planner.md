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

## Local preview

Start from the mocaviz repository using the existing shared deployment cache:

```sh
python -B scripts/serve_gnirs_planner.py --cache-file /private/path/gnirs.sqlite
```

Then open `http://localhost:8796/js/gnirs-planner` and supply credentials in the
page or URL. This launcher checks the cache, catalog and RV/SXD timing grids
**before** opening the port. It disables request logging and binds only to
loopback. `--check` validates configuration without starting a server or writing
files. You can also supply the path through `MOCAVIZ_GNIRS_CACHE_FILE`.
Keep this command running while using the local preview.

If the page says the cache is not configured, the serving process has no
`MOCAVIZ_GNIRS_CACHE_FILE`. **Regenerate catalog cannot choose a server path or
recreate the offline timing-calibration bundle.** Point the process at the
existing initialized cache and restart it; no regeneration is needed for this
configuration error. For a fresh deployment, first import the seed below.
Regeneration stays disabled until the cache loads; **Reload cache** retries
after configuration is repaired. Repeated users share the same file.

### Existing local MOCAviz on port 8061

The compatibility launcher `python -B bd_colors_fast/app.py` also serves
`http://localhost:8061/js/gnirs-planner`. Put only the shared cache location in
the repository's ignored `.env` file, then restart that local server:

```dotenv
MOCAVIZ_GNIRS_CACHE_FILE=/private/path/gnirs.sqlite
```

An explicitly exported environment value takes precedence over `.env`. Both
8061 and the isolated 8796 preview can use the same file; neither creates a copy.
The compatibility launcher suppresses GNIRS request logging and disables
bytecode writes. Collaborator credentials are still supplied through the URL,
never `.env`. This local setup is independent of the live site's systemd service.

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

For a persistent Linux service, adapt `deploy/gnirs.service.example` to the
installed repository, virtual environment and existing service user. The unit
checks the shared cache before starting, restarts on failure, disables stdout
and stderr logs, and makes the filesystem read-only except for the single cache
file and RAM-backed Gunicorn worker heartbeats. Install it as
`/etc/systemd/system/mocaviz-gnirs.service`, then run:

```sh
systemd-analyze verify /etc/systemd/system/mocaviz-gnirs.service
systemctl daemon-reload
systemctl enable --now mocaviz-gnirs.service
```

Verify the loopback backend before adding the Nginx location. On a Passenger
site, explicitly set `passenger_enabled off` **inside that planner location**.
An updated Git deployment does not by itself set environment variables or
install the private cache. Existing Passenger workers can also retain older
Python code after the source files change. The dedicated GNIRS service owns
its cache setting independently of the other MOCAviz pages.

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


## RV band, slit and S/N coverage (2026-09-28)

The high-resolution RV mode supports J at 1.30 µm, H at 1.65 µm and K at
2.30 µm with selectable long-blue or short-blue camera and 10, 32 or 111 l/mm grating. Defaults are short blue, 111 l/mm and a fixed 0.30″ slit in all weather bands. The optional `auto` wavelength
selection uses K for types earlier than T3 (including T2.5) and J for T3 onward.
The additional `auto_h` choice uses the same K branch and H at 1.65 µm for T3 onward.
The default `auto_h_l8` choice uses K through L7.0 (numeric type ≤17) and H for every
type later than L7.0, including fractional types such as L7.1 and L7.5.
All choices resolve the band using the adopted numeric spectral type before
selecting the nearest template; the Band 3 comparison follows the same choice. Slits are
0.10, 0.15, 0.20, 0.30, 0.45, 0.675 and 1.0 arcsec; automatic means 0.15 arcsec
in Band 1/2 and 0.30 arcsec in Band 3. An explicit override stays fixed when
weather changes. SXD settings and timing intervals are unchanged.

RV S/N is always per detector pixel. Coverage choices are 25%, 50%, 75%, 90%
and 95%, default 75%. Required time is the order statistic at
`ceil(fraction * number_of_recorded_pixels) - 1`. Pixels may be disjoint;
invalid pixels remain in the denominator with infinite required time. Unsupported
coverage returns an explicit unavailable result rather than substituting 75%.
Between cached magnitudes the tighter of the two endpoint source/sky scaling
bounds is used, avoiding underestimation when the pixel defining a coverage
quantile changes. Bright/faint extrapolations remain flagged.
The Band 3 exclusion always compares the 0.30 arcsec slit, with the same chosen
camera, grating, wavelength setting, S/N, coverage, airmass and multiplier.

J/K estimates use the corresponding catalog photometry. The current catalog has
no H photometry: H estimates use measured J and the selected Sonora template's
spectral shape/color. This is stated beside the controls, in the target report,
and in the methods. CSV exports distinguish observing band from photometry band.
Unusual colors, gravity or cloud properties can bias the inferred H flux.

### Compact calibration publication

The server stores only timing curves, not atmosphere spectra. The offline
builder reuses the existing public, resampled Sonora input SEDs in RAM, uploads
only the normalization interval and selected wavelength region, and saves
one compressed set of detector noise coefficients per configuration locally.
Do not convolve inputs to GNIRS resolution before submitting them: the ITC
performs instrumental broadening. Do not copy native model grids onto the server.

Build on the development machine (paths are explicit CLI arguments):

```sh
python -B scripts/build_gnirs_rv_grid.py --source /path/to/rv_itc_20260924 --j-filter /path/to/2mass_J.xml --output /outside/repo/rv_jhk --workers 6
python -B scripts/publish_gnirs_rv_grid.py --cache /path/to/shared.sqlite --grid /outside/repo/rv_jhk/grid.json --check
python -B scripts/publish_gnirs_rv_grid.py --cache /path/to/shared.sqlite --grid /outside/repo/rv_jhk/grid.json
```

The publisher validates the full 1,512-configuration matrix before acquiring the
existing cache lease. It replaces only timing metadata and the catalog revision
in the same SQLite file, using an in-memory journal. Plain or gzipped JSON can
be piped on stdin, avoiding an upload file on the server. It does not regenerate
targets or copy the multi-gigabyte catalog. Run as the service account. All web
workers notice the new revision; restart workers when Python source changes.

Metadata responses omit RV/SXD curve data (empty row lists support older tabs). Timing and the fixed-slit Band 3
comparison are returned with each target, so increasing the number of cached
configurations does not increase the initial browser download proportionally.


## RV camera and grating controls (2026-09-28)

Camera/grating controls apply to RV longslit mode only. Gemini ITC supports 10 l/mm with long blue only; short blue offers 32 and 111 l/mm. Selecting short blue while 10 l/mm is active changes the grating to 111 with an explanatory message. SXD keeps its fixed
short-blue/32 l/mm/0.45 arcsec prescription. Camera and grating are dimensions
of every selection cache key and timing lookup, including the fixed 0.30 arcsec
Band 3 exclusion. Missing combinations fail explicitly. The target inspector and
CSV include camera, grating, spatial pixel scale and nominal slit-limited R.
The inspector flags slits projecting to fewer than two detector pixels: optical
broadening and pixel response determine their actual resolution/RV performance.

The offline camera builder covers 7,560 rows (five supported camera/grating combinations,
three bands, three weather setups, seven slits, two airmasses, twelve templates).
It calibrates source, sky and read noise using generic public flat-photon Gemini
ITC requests, then projects the existing compact Sonora SEDs through atmospheric
transmission and the nominal instrumental profile in memory. Original direct-ITC
long-blue/111 curves can be retained with `--existing-grid`. Independent direct
Sonora uploads should be used to check the approximation for each new mode.

Timing logarithms are stored as compact little-endian int32 arrays in base64,
rounded upward to 1e-5 in natural log time. Only the requested setup/coverage is
decoded. The server receives this timing table in the existing SQLite cache;
no spectra or per-user products are added. The initial browser metadata still
omits all timing rows. At low dispersion, part of the detector can fall outside
the blocking filter: an unattainable coverage fraction is reported as unsupported.

Build and publish on the development machine:

```sh
python -B scripts/build_gnirs_camera_grid.py \
  --source /path/to/rv_itc_20260924 --j-filter /path/to/2mass_J.xml \
  --atmosphere50 /path/to/mktrans_zm_16_15.dat \
  --atmosphere-any /path/to/mktrans_zm_50_15.dat \
  --existing-grid /path/to/previous-grid.json.gz \
  --output /outside/repo/camera-grid --workers 4
python -B scripts/publish_gnirs_rv_grid.py --cache /path/to/shared.sqlite \
  --grid /outside/repo/camera-grid/grid.json.gz --check
python -B scripts/publish_gnirs_rv_grid.py --cache /path/to/shared.sqlite \
  --grid /outside/repo/camera-grid/grid.json.gz
```

Deploy the decoder code before importing the compact table and restart existing
Python workers when installing it. The publication uses the same existing cache
file and its lease; it creates no disk-side journals or alternate catalog files.


## Minimum integration and detector limits (2026-09-28)

`minScienceMinutes` defaults to 20 for both GNIRS modes; 0 disables it.
The minimum applies to each target's total on-source science time, before
acquisition/calibration/read/nod overheads. The larger of the minimum and the
S/N requirement is rounded up to complete ABBA cycles. The same rule is used
in Band 3 comparisons, selection cutoffs, reports, and exports.

Each RV frame must remain at or below a conservative 50,000 electron
source-plus-background pixel estimate, below Gemini's published shallow-well
nonlinearity threshold (5,000 ADU × 13.5 electrons/ADU). The offline
`scripts/build_gnirs_peak_limits.py` augments the existing camera grid with two
count rates per row; publish its output with `scripts/publish_gnirs_rv_grid.py`.
An old grid without these fields cannot produce a safe RV plan. This is an
administrator/offline ITC update, separate from regenerating the catalog.

The count bound uses the brightest unsmoothed public template/flat-continuum
ratio across the detector, divides out Gaussian slit and spatial-pixel losses,
and takes independent maxima across the sampled weather/airmass conditions.
This deliberately allows for seeing/transparency better than the timing bin.
It is an upper estimate within the template/ITC model, not a guarantee about
unmodeled sources, variable sky, or actual detector behavior. Verify counts
and apply the appropriate detector corrections during observing/reduction.

Existing 60–300 s Very Faint curves remain unchanged. Shorter candidate frames
are 0.2/0.5 s (Very Bright), 1/2/5/10 s (Bright), and 20/40 s (Faint), all above
Gemini's hardware minima. Their S/N duration is conservatively bounded from
the 60 s curve by multiplying *all* noise terms by
`max(1, (read_noise/7)^2 * 60/frame_seconds)`. This safely bounds the changed
read term without storing more spectra or timing grids; the short-frame flag
is shown in the report. Read/write/nod costs follow the selected mode.
If even the shortest supported exposure fails, timing is unavailable.
SXD retains its independently calibrated read modes and 50,000 electron cap.

Public references: [GNIRS detector/read modes](https://www.gemini.edu/instrumentation/gnirs/components),
[ITC output conventions](https://www.gemini.edu/observing/resources/itc/itc-help).
No new server-side cache files or runtime ITC requests are introduced.


### Current RV defaults (2026-09-28)

The default wavelength rule is **K for L0–L7; H for L8+** (`auto_h_l8`):
K at 2.30 µm through numeric type 17 (L7.0), H at 1.65 µm for every later
type, including L7.1 and L7.5. The default S/N goal is **30 per detector pixel**
over at least 75% of recorded pixels; the science-time cutoff is **4 hours per
target**. The minimum remains 20 minutes. The cached S/N=50 reference curves
remain valid and are scaled by the requested S/N squared. SXD uses its separate
defaults. The RV standards list includes OIDs 11199, 11063, 369949, 7210, 371766.
