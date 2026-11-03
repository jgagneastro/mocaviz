# SUBLIME Findings Dashboard

Run from the maintained mocaviz checkout:

```sh
/opt/anaconda3-native/anaconda3/envs/mocaviz/bin/python -B -m mocaviz.sublime_findings --port 8901
```

Open through **Web Tools → SPHEREx → SUBLIME Findings Dashboard → Start & open**.
The dashboard uses the private management connection supplied by the launcher.
It also accepts the existing SPHEREx tool's URL/fragment credential conventions.
A credential-free synthetic demo is at `http://127.0.0.1:8901/?mock=1`.

This is a separate read-only Flask entry point, sharing MOCAviz's existing
SPHEREx fitter and browser renderer. The already-running MOCAviz and SUBLIME
reviewer services do not need to restart. It starts no scientific workers.

## Selection

- Combine SUBLIME1, SUBLIME2, CatWISE red movers, and other active
  MOCAdb objects outside those catalogs without a public nonphotometric M0+
  classification, including confirmed duplicate links. Public catalog identifiers
  do not by themselves make an object a published late-type discovery. Catalog unions count each OID once.
- Latest candidate rows and latest non-ignored stored lane autotypes are used.
  The default type order is SPIFFStacker, SUBLIME aperture, SUBLIME2 candidate,
  SPIFF, then public spectroscopic type. Adopted type is an explicit alternative.
- Default catalog: **SUBLIME2 only**. All five catalog/claim membership
  selectors (BYW, BYW claims, Yadu, Azul, SMDET) default to **Absent / no**.
- Other defaults: L0+, unpublished, not the duplicate side of confirmed duplicate
  pairs, with `good` or `good_candidate` spectral quality in at least one lane.
  This last cut is visible and can be disabled. It keeps the initial catalog
  load focused on visually vetted findings.
- Global spectral-quality modes include **At least one good**, which requires
  the exact `good` class in one or more reductions, and **All available good**
  / **All available good/good candidate**. The all-available modes require at
  least one active spectrum and an accepted review in every reduction that has
  an active spectrum. Missing reductions are skipped; available but unreviewed
  spectra fail. Existing any-good/candidate and reviewed/unreviewed modes remain.
- **Recovered known** uses public nonphotometric spectral types, L0+, and
  removes the global spectral-quality requirement. Publication status includes
  public-adopted M0+ types across confirmed duplicate links, as in the reviewer.
  M/L/T/Y type is a proxy for the requested population, not a mass confirmation.
- Numeric cuts require a value when enabled; blank cuts retain missing values.
  Independent lane type ranges and include/exclude visual classes combine with
  AND. `none` selects missing visual vetting. Motion scores/class names and
  per-cutout scores/classes follow the reviewer. Cutout all/any applies to
  stored reviews, not a claim that every source image has been reviewed.
- BYW membership, BYW claims, Yadu, Azul and SMDET each have yes/no/either.
  BYW claims use `pcat_schneider_claim_list_byw` plus the reviewer's BYW `disc`
  name tokens: yadu, tom, bickle, sarah, azul, eastonh. Yadu is
  `pcat_kirkpatrick_yadu_2026_claim`; Azul is
  `pcat_azul_byw_sample_jul16_2026`. No fuzzy positional memberships are added.
- Only active objects are used, even in the include-duplicates mode. Confirmed
  duplicate exclusion removes `potential_duplicated_moca_oid` for `y` pairs.

## Science views

Histogram, RA/Dec or Mollweide sky projection, spectral type versus absolute
W2, synthetic-minus-measured W2, motion versus type, and overlapping recovery
counts by catalog. Each scatter-plot point opens the same inspector, also
available from the object table and flipbook cards.

Absolute magnitudes use a positive adopted parallax first, then an adopted
nonphotometric distance. Photometric distances are an explicit opt-in and their
count is reported. W2 picks non-ignored measured photometry, preferring
adopted_simpleband then adopted then newest ID. Synthetic W2 uses stored
SPHEREx-linked measurements (packs 55/62/76) or the explicit
`spherex_w2_synth` method when its spectrum link is absent. A synthetic lane can
be selected independently. Both use the same distance. No synthetic photometry
or distance is invented when absent. Magnitude-plus-parallax uncertainties are
propagated when both exist; distance-only error bars are not fabricated.
CSV includes measurement IDs, spectrum IDs, distance provenance and all flags.

The flipbook has ten objects per page, decreasing stored selected SPT, with
reduction selector and optional omission of objects lacking active spectra.
Its plots are 75% of their original height; inspector plots retain their size.
Inspector: **three plots**, SPIFFStacker / SPIFF / SUBLIME aperture, with
one best-fit template each. Fits are recomputed with the existing autotype
options and can differ from stored types used for filtering and ordering.
Fits use only non-ignored pixels and the shared MOCAdb template grid. A missing
reduction keeps its own explicit empty panel.

Inspector cutouts follow the reviewer's source-key paths, including PNG.bz2,
under the local SUBLIME cutout tree and Phoenix_A fallback. Files are read only,
not unpacked on disk. Missing disks/files are reported. The on-disk cutout PNGs
may themselves contain the original extraction's plotted spectrum.
WiseView uses the reviewer's 30 arcsec / maxdyr=1 settings in a sandboxed frame
with no database credentials. Its fixed vendor JS/CSS and public pawnstars/xref lookups are proxied for the
opaque-origin frame. The lookup routes validate coordinates and cannot request
arbitrary upstream URLs or read private data. Missing survey coverage is a
normal panel result, not a failed dashboard load. Finder charts use 2MASS IRSA Finder Chart, PS1 i/z/y cutouts, and NSC DR2 SIA
previews, as in the reviewer. Requests include only coordinates and field size.
2MASS/PS1 show a center crosshair; NSC's per-exposure previews are not assumed
to be centered. No proper-motion epoch propagation is claimed.

## Runtime and safeguards

All database request paths use explicit read-only transactions, rollback and
close. There are no submit, classify or write endpoints. Credentials are passed
per request in memory and never written to cache, catalog, scientific files,
browser storage or logs. No request URL logging is enabled by the launcher.
Data live in tab memory; fits have a 90-entry tab-memory bound. Survey previews
settle independently. Old page/selection requests are cancelled and stale
responses cannot replace a newer object's panels.

SQL applies catalog, type and global/per-lane quality cuts before enrichment.
The app fails visibly if more than 100,000 objects pass the initial cuts,
instead of presenting partial scientific totals. Narrow type or quality cuts
for exceptionally broad unreviewed selections. All returned chart totals are
complete for a successfully applied filter set; there is no random subsampling.

Offline checks:

```sh
/opt/anaconda3-native/anaconda3/envs/mocaviz/bin/python -B -m unittest discover -s tests -p 'test_sublime_findings.py' -v
node --check mocaviz/static/sublime_findings.js
node scripts/chromium_probe.mjs --url 'http://127.0.0.1:8901/?mock=1' --wait-js 'window.SublimeFindings?.rows.length>0' --expect-plotly '#cmd::traces>=2,points>=1'
```
