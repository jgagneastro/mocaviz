# Fast MOCAviz Prototype

Standalone local prototype for a faster brown-dwarf color page.

This directory is intentionally isolated from the existing Dash app.

## Run Locally

From this directory:

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:8061/
```

The fast spectral typing prototype is served by the same process:

```text
http://127.0.0.1:8061/spectral-typing
```

The fast astrometric explorer prototype is also served by the same process:

```text
http://127.0.0.1:8061/astrometry
```

The fast spectral explorer prototype is served at:

```text
http://127.0.0.1:8061/spectra
```

The fast spatial-kinematic explorer prototype is served at:

```text
http://127.0.0.1:8061/xyzuvw
```

The fast TrueFlow age-PDF prototype is served at:

```text
http://127.0.0.1:8061/trueflow-age-pdfs
```

If another local copy is already using port 8061:

```bash
BD_COLORS_FAST_PORT=8062 python app.py
```

The server uses the same public MOCAdb defaults as `pages/bd_colors.py`, with
optional overrides through environment variables:

```bash
MOCA_HOST=... MOCA_USERNAME=... MOCA_PASSWORD=... MOCA_DBNAME=... python app.py
```

For a network-free smoke test, use:

```text
http://127.0.0.1:8061/?mock=1
http://127.0.0.1:8061/spectral-typing?mock=1&specid=450
http://127.0.0.1:8061/astrometry?mock=1&moca_oid=602
http://127.0.0.1:8061/spectra?mock=1&moca_specid=13510
http://127.0.0.1:8061/xyzuvw?mock=1&axes=xyz&asso=HYA,TWA
http://127.0.0.1:8061/trueflow-age-pdfs?mock=1&moca_oid=11266
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
  starting the spectral range before `L0` applies a safety cap of 1,000,000
  objects by default. Override with `BD_COLORS_FAST_MAX_OBJECTS=300000` or a URL
  parameter such as `?max_objects=300000`; use `max_objects=0` for an explicit
  uncapped query.
- The fast spectral typing page uses Flask JSON endpoints instead of Dash
  callbacks. The server caches the standards grid, raw spectra, and computed
  comparison payloads; the browser handles navigation, Plotly rendering, URL
  state, and cache clearing.
- The fast astrometry page loads one target's single-epoch astrometry,
  adopted PM/parallax, designations, and mission metadata through compact JSON
  endpoints; the browser handles mission toggles, residual transforms, binned
  display, selections, Plotly rendering, CSV export, URL state, and cache
  clearing.
- The fast spectral explorer loads selected spectra through compact JSON
  endpoints; the browser handles normalization, flux-unit conversion,
  low-resolution display styling, chemical feature overlays, selections,
  Plotly rendering, per-spectrum CSV downloads, URL state, and cache clearing.
- The fast spatial-kinematic explorer loads selected memberships, highlighted
  objects, and BANYAN model components through compact JSON endpoints; the
  browser handles 3D XYZUVW rendering, association filters, model wireframes,
  object selections, CSV export, URL state, and cache clearing.
- The fast TrueFlow age-PDF page loads object or association age rows, compact
  MOCAFlows PDF blobs, legacy PDF rows, and scalar Gaussian fallbacks through
  JSON endpoints; the browser handles source filters, HBM filtering, CDF/log
  display modes, visible-curve products, Plotly rendering, URL state, CSV
  export, and cache clearing.

## Database Indexes

Optional index recommendations are in `INDEX_RECOMMENDATIONS.md`, with
reviewable SQL in `recommended_indexes.sql`. They are not applied by this
prototype.
