# MOCAviz Flask Application

This directory contains the maintained production application. It is
intentionally isolated from the archived Dash app in `deprecated/dash/`.

## Run Locally

From the repository root:

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:8050/
```

The MOCAdb spectral typing app is served by the same process:

```text
http://127.0.0.1:8050/spectral-typing
```

The astrometric explorer is also served by the same process:

```text
http://127.0.0.1:8050/astrometry
```

The spectral explorer is served at:

```text
http://127.0.0.1:8050/spectra
```

The spatial-kinematic explorer is served at:

```text
http://127.0.0.1:8050/xyzuvw
```

The age-PDF explorer is served at:

```text
http://127.0.0.1:8050/age-pdfs
```

The legacy MCMC radial-velocity diagnostics prototype is served at:

```text
http://127.0.0.1:8050/legacy-radial-velocities
```

The RVBAM radial-velocity explorer is served at:

```text
http://127.0.0.1:8050/rvbam-explorer
```

If another local copy is already using port 8050:

```bash
MOCAVIZ_PORT=8051 python app.py
```

The server uses the same public MOCAdb defaults as the archived
`deprecated/dash/pages/bd_colors.py`, with optional overrides through
environment variables:

```bash
MOCA_HOST=... MOCA_USERNAME=... MOCA_PASSWORD=... MOCA_DBNAME=... python app.py
```

For a network-free smoke test, use:

```text
http://127.0.0.1:8050/?mock=1
http://127.0.0.1:8050/spectral-typing?mock=1&specid=450
http://127.0.0.1:8050/astrometry?mock=1&moca_oid=602
http://127.0.0.1:8050/spectra?mock=1&moca_specid=13510
http://127.0.0.1:8050/xyzuvw?mock=1&axes=xyz&asso=HYA,TWA
http://127.0.0.1:8050/age-pdfs?mock=1&moca_oid=11266
http://127.0.0.1:8050/legacy-radial-velocities?mock=1
http://127.0.0.1:8050/rvbam-explorer?mock=1
```

## Design

- Flask serves one HTML page, static JS/CSS, and a compact JSON bootstrap API.
- The browser computes axis values, filters, highlighting, Plotly rendering,
  table selection, and CSV export without Dash callbacks.
- The initial bootstrap only loads objects, non-photometric distances, the
  photometry bands needed by the current axes, median colors, and sequence
  overlays matching the current axes. Extra photometry bands, photometric
  distances, spectral-index rows, equivalent-width rows, and BANYAN age rows
  are loaded lazily when the corresponding control is used.
- The MOCAdb bootstrap payload is cached in memory for 15 minutes by default.
  Set `BD_COLORS_FAST_CACHE_SECONDS` to change this.
- The default live query is uncapped, but it only loads adopted
  spectroscopic spectral types from `L2+` onward
  (`photometric_estimate = 0`). That path uses MOCAdb's existing
  `quicklook_adopted_sptn2` composite index.
- Broader source queries are opt-in. Including photometric spectral types or
  starting the spectral range before `L0` applies a safety cap of 5,000 objects
  by default. Numeric `max_objects` requests above that broad-query cap are
  clamped; use `max_objects=0` for an explicit uncapped query.
- The MOCAdb spectral typing page uses Flask JSON endpoints instead of Dash
  callbacks. The server caches the standards grid, raw spectra, and computed
  comparison payloads; the browser handles navigation, Plotly rendering, URL
  state, and cache clearing. Batch clients can request `summary_only` compare
  payloads that retain chi-squared and fit metadata while omitting spectral
  arrays.
- The astrometry page loads one target's single-epoch astrometry,
  adopted PM/parallax, designations, and mission metadata through compact JSON
  endpoints; the browser handles mission toggles, residual transforms, binned
  display, selections, Plotly rendering, CSV export, URL state, and cache
  clearing.
- Ignored astrometric measurements (`ignored=1`) remain available as labelled
  × markers and table rows. They do not enter SciPy/UltraNest fits, binned
  measurements, reference-coordinate adjustment, or automatic x/y ranges.
  Points outside the initial view can be inspected by panning or zooming.
  The measurement table and exports include mission name, data release,
  `moca_psid`, airmass, and the ignored flag. **Export table as CSV** exports the
  selected measurements, or all filtered measurements when nothing is selected.
- **Auto-detect and ignore duplicated measurements** is enabled by default.
  It retains one usable copy when both offsets, absolute epoch, R.A./Decl.
  uncertainties, and epoch uncertainty match exactly, without rounding.
  Duplicate copies are hidden from plots, the measurement table, and exports,
  and excluded from fits, binning, reference adjustment, and automatic ranges. Detection
  follows the selected raw/recalibrated coordinates and current filters;
  turning it off restores the copies. Database `ignored` flags are unchanged. Use
  `ignore_duplicates=0` in a URL to disable detection across reloads.
- Management users can select measurements in either plot and use **Mark
  currently selected entries as ignored=1 in MOCAdb** below the table. The
  optional **Append comments** field preserves existing text. A read-only
  preview validates the target and selected IDs before confirmation; a changed
  selection or database revision requires a new review. Updates and changelog
  records commit together, preserve source visibility/RLS, and are read back
  before commit. The explorer then reloads the measurements and clears stale fits.
- The spectral explorer loads selected spectra through compact JSON
  endpoints; the browser handles normalization, flux-unit conversion,
  low-resolution display styling, chemical feature overlays, selections,
  Plotly rendering, per-spectrum CSV downloads, URL state, and cache clearing.
- The spatial-kinematic explorer loads selected memberships, highlighted
  objects, and BANYAN model components through compact JSON endpoints; the
  browser handles 3D XYZUVW rendering, association filters, model wireframes,
  object selections, CSV export, URL state, and cache clearing.
- The TrueFlow age-PDF page loads object or association age rows, compact
  MOCAFlows PDF blobs, legacy PDF rows, and scalar Gaussian fallbacks through
  JSON endpoints; the browser handles source filters, HBM filtering, CDF/log
  display modes, visible-curve products, Plotly rendering, URL state, CSV
  export, and cache clearing.
- The legacy MCMC radial-velocity page loads the dataset list once, then loads
  one selected `pcat_mcmc_rv_pipeline` dataset with all segment diagnostics and
  file URLs in one cached JSON payload. The browser handles the quality cuts,
  weighted averages, Plotly selection, segment details, diagnostic images, URL
  state, exports, and cache clearing.
- The RVBAM explorer loads `pcat_rv_sampling_runs` by primary key, then loads
  segment metadata, RVBAM figure URLs, sampling parameters, and payload metadata
  through compact JSON endpoints. Full posterior blobs in
  `pcat_sampling_payloads` are decoded only when requested, then downsampled or
  summarized server-side before Plotly receives them.

## Database Indexes

Optional index recommendations are in `INDEX_RECOMMENDATIONS.md`, with
reviewable SQL in `../sql/indexes/`. They are never applied automatically by
the application.


### Astrometry UltraNest progress and cancellation (2026-10-26)

UltraNest runs as a bounded background fit with one active job per web process.
The page polls short status requests, showing the current moving/stationary
model, elapsed time, and likelihood evaluations. **Cancel fit** requests a real
sampler stop, acknowledged before reporting cancellation. **Retry status**
reattaches after a connection failure without starting a second sampler. Identical
active requests reuse the same job. Changing fit inputs discards a late result
and cancels that page's previous job.

The default combined fit budget is 900 seconds and 2,000,000 likelihood calls,
configurable server-side with `ASTROMETRY_FIT_TIMEOUT_SECONDS` (up to 7200) and
`ASTROMETRY_ULTRANEST_MAX_NCALLS` (up to 20,000,000). Limits are checked during
prior/likelihood evaluation; the native sampler also receives the remaining
call budget. Limit exits are **incomplete** with no usable fit/evidence returned.
Native live-point, evidence, posterior, and mixture-model criteria are retained.
SciPy fitting and database push controls retain their existing separate routes.

Jobs use `/api/astrometry/fit/jobs`, with GET status and POST cancellation at
`/<job_id>` and `/<job_id>/cancel`. Tokens are scoped to a hash of the connection
credentials, which are never stored in job responses or receipts. Completed
jobs expire after an hour, and at most 32 are retained in memory. Reloading the
web service clears in-memory jobs; it does not write measurements or fitted
values to MOCAdb. UltraNest point stores are closed on cancellation and errors.
