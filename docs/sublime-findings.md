# SUBLIME Findings Dashboard

Run from the maintained mocaviz checkout:

```sh
/opt/anaconda3-native/anaconda3/envs/mocaviz/bin/python -B -m mocaviz.sublime_findings --port 8901
```

Open through **Web Tools → SPHEREx → SUBLIME Findings Dashboard → Start & open**.
The dashboard uses the private management connection supplied by the launcher.
It also accepts the existing SPHEREx tool's URL/fragment credential conventions.
A credential-free synthetic demo is at `http://127.0.0.1:8901/?mock=1`.

This separate Flask entry point shares MOCAviz's SPHEREx fitter and browser renderer.

## Selection

- Combine SUBLIME1, SUBLIME2, CatWISE red movers, and other active MOCAdb objects.
  **Other unpublished MOCAdb objects** requires an active M0+ type with
  `adopted=1` in private MOCAdb and a numeric stored SPHEREx autotype in at
  least one lane. The dashboard applies its selected type, quality, and other
  filters to this sample. It excludes the other three catalogs and objects
  with a public nonphotometric M0+ classification, including confirmed
  duplicate links. Catalog unions count each OID once.
- Latest candidate rows and latest non-ignored stored lane autotypes are used.
  The default type order is SPIFFStacker, SUBLIME aperture, SUBLIME2 candidate,
  SPIFF, then public spectroscopic type. Adopted type is an explicit alternative.
- All four catalogs are selected by default. The five catalog and claim
  selectors (BYW, BYW claims, Yadu, Azul, SMDET) default to **Either**, and
  the published spectroscopic type filter defaults to **Both populations**.
- **Trigger SUBLIME2 discoveries only** selects just SUBLIME2, sets all five
  membership selectors to **Absent / no** and selects **Unpublished**. It
  immediately applies those settings with the other current cuts.
  **Reset to default filter** restores and applies the dashboard defaults.
- Minimum WiseView motion quality defaults to **1** (inclusive). Clear the minimum to disable this cut.
- The default sample includes L0+ objects outside the duplicate side of
  confirmed pairs, with good-family or `good_candidate` spectral quality in at least one lane.
  This last cut is visible and can be disabled. It keeps the initial catalog
  load focused on visually vetted findings.
- In quality requirements, **good** includes `good`, `contaminated_ucd`,
  `peculiar_ucd`, and `good_plus_star`. **Good/candidate** also includes
  `good_candidate`. This applies to the global modes and per-lane `good`
  include lists; explicit exclusion lists retain their literal classes.
- Global spectral-quality modes include **At least one good** and **All available good**
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

The flipbook offers 10, 20, 30, 40 or 50 objects per page (default 50),
decreasing stored selected SPT, with optional omission of objects without
stored spectra in any lane. The flipbook and inspector show the newest active
spectrum in each reduction, falling back to the newest ignored spectrum
when needed and labeling it as ignored. Larger pages render progressively in batches
of ten, retaining the bounded API requests and cancellation on page changes.
Its taller cards contain three vertically stacked panels; inspector plots retain their size.
Inspector: **three plots**, SPIFFStacker / SPIFF / SUBLIME aperture, with
one best-fit template each. Fits are recomputed with the existing autotype
options and can differ from stored types used for filtering and ordering.
Fits use only non-ignored pixels and the shared MOCAdb template grid. A missing
reduction keeps its own explicit empty panel.

The inspector uses each spectrum’s stored reference coordinates, or the exact
SPIFF reduction record or local SPIFFStacker manifest when needed. The legend
shows the coordinate source and epoch, and labels missing references.

The SUBLIME panel uses the science pixels and WCS from the matching FITS cutout
when available. Finder panels use calibrated 2MASS J, PS1 z, and NSC DR2 FITS
cutouts. If calibration is unavailable, the original preview remains available
where there is coverage. The crosshairs propagate with proper motion when the
reference epoch, motion, and image epoch are available. Pan-STARRS uses its
stack header epoch. WiseView uses the median epoch of the displayed frames and
reports its canvas WCS to the inspector from the sandboxed frame.

## Potential duplicates

The tab scans the selected sample for other active MOCAdb objects with published,
nonphotometric spectroscopic L0+ types within 100 arcseconds. It compares stored
positions at their catalog epochs and shows the spectral type and ADS reference,
adopted proper motions for both objects, and existing duplicate decisions.

With management access, **Declare potential duplicate** confirms the pair from the
chosen row and saves a `y` decision in `pcat_duplicated_vetting` with a changelog entry.
The endpoint checks the current positions, counterpart type and prior decisions
before committing. The entry starts with `applied=0`.

## Runtime and safeguards

Exploration and duplicate scans use read-only transactions. Credentials are passed
per request in memory and never written to cache, catalog, scientific files,
browser storage or logs. No request URL logging is enabled by the launcher.
Data live in tab memory; fits have a 180-entry tab-memory bound. Survey previews
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


## Plot color classes

All overview plots use the same mutually exclusive categories, in this order:

1. **Known recovered** (ochre): the existing published-spectroscopic status,
   including confirmed duplicate links, regardless of motion or spectral quality.
2. **Claimed UCDs** (muted rose): BYW membership, a BYW, Yadu or Azul claim,
   or an SMDET designation. This class takes precedence over the motion categories.
3. **New motion-confirmed** (teal): an accepted review in SPIFFStacker, SPIFF or
   SUBLIMEaperture and a WiseView motion score ≥5.
4. **New candidate** (blue): the same spectral-quality requirement and a motion
   score ≥3 and <5.
5. **Still candidates** (purple): the same quality requirement and a score in
   [1,2], including 1.5.
6. **Others** (gray): every other object admitted by the current filters.

Accepted reviews are exactly `good`, `good_candidate`, `contaminated_ucd`,
`peculiar_ucd`, and `good_plus_star`. For the motion categories, missing or nonfinite scores, scores between
2 and 3, and missing or nonqualifying spectral reviews fall into Others.
The motion categories use the stored visual-vetting labels. Existing sample filters remain independent of the
color classes. Measured and synthetic W2 share class colors; synthetic points
use open diamonds (open triangles for photometric distances). The on-page legend
shows class counts and hover definitions. CSV exports include `plot_class` and
`plot_class_label`; the object table and inspector show the same class labels.

Each flipbook card now stacks SPIFFStacker, SPIFF and SUBLIMEaperture vertically. Each lane shows its own best template: red, blue and bright purple respectively, matching the WiseView reviewer. Missing lanes remain explicitly labelled. Requests are bounded to ten spectra per lane and cards render progressively.
