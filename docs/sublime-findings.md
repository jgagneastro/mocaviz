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
  Known UCDs, known UCD candidates, and claimed sources bypass quality cuts by default; each quality group has an opt-in checkbox.
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
  selects the public-spectroscopic subset. Known-source quality opt-ins remain available. Publication status includes
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
W2, synthetic-minus-measured W2, WiseView motion score and adopted total
proper motion versus spectral type, adopted distance versus spectral type,
and overlapping recovery counts by catalog. Each scatter-plot point opens the same inspector, also
available from the object table and flipbook cards. Scatter plots shift each
object horizontally by up to 0.2 spectral subtype to separate overlapping
points. Hover labels show the actual subtype. The proper-motion plot
uses the selected spectral type and the adopted, non-ignored MOCAdb
`data_proper_motions.pmtot_masyr` value. The CSV includes the measurement ID.

The proper-motion and distance plots use logarithmic vertical axes.
The distance plot uses positive, adopted, non-ignored `data_distances.distance_pc`
values. Triangles mark photometric estimates, circles mark parallax-linked
distances, and diamonds mark nonphotometric distances without a parallax link.
The CSV includes the adopted distance ID and method category. The W2 distance
setting controls the absolute-magnitude plot independently.

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

1. **Known UCDs** (ochre): the existing published-spectroscopic status,
   including confirmed duplicate links, regardless of motion or spectral quality.
2. **Known UCD candidates** (gold): a direct public-adopted photometric spectral-type join; spectroscopy takes precedence.
3. **Claimed UCDs** (muted rose): BYW membership, a BYW, Yadu or Azul claim,
   or an SMDET designation. This class takes precedence over the motion categories.
4. **New motion-confirmed** (teal): an accepted review in SPIFFStacker, SPIFF or
   SUBLIMEaperture and a WiseView motion score ≥5.
5. **New candidate** (blue): the same spectral-quality requirement and a motion
   score ≥3 and <5.
6. **Still candidates** (purple): the same quality requirement and a score in
   [1,2], including 1.5.
7. **Others** (gray): every other object admitted by the current filters.

Accepted reviews are exactly `good`, `good_candidate`, `contaminated_ucd`,
`peculiar_ucd`, and `good_plus_star`. For the motion categories, missing or nonfinite scores, scores between
2 and 3, and missing or nonqualifying spectral reviews fall into Others.
The motion categories use the stored visual-vetting labels. Existing sample filters remain independent of the
color classes. Measured and synthetic W2 share class colors; synthetic points
use open diamonds (open triangles for photometric distances). The on-page legend
shows class counts and hover definitions. CSV exports include `plot_class` and
`plot_class_label`; the object table and inspector show the same class labels.

Each flipbook card now stacks SPIFFStacker, SPIFF and SUBLIMEaperture vertically. Each lane shows its own best template: red, blue and bright purple respectively, matching the WiseView reviewer. Missing lanes remain explicitly labelled. Requests are bounded to ten spectra per lane and cards render progressively.


## Known-source quality switches (2026-11-06)

SUBLIME1 and SUBLIME2 membership is joined by `moca_oid` to active
`data_spectral_types` rows with `public_adopted=1`. `photometric_estimate=0`
provides the known spectroscopic population; `photometric_estimate=1`
provides **Known UCD candidates**. Existing published-status propagation
across confirmed duplicate links remains for spectroscopy. Types are selected
with the existing preferred-type ranking; published photometric types are a
fallback when no ranked spectroscopic/autotype value is available. Latest
adopted/public rows and catalog rows are selected once, and catalog unions
are deduplicated by OID before enrichment.

Each quality group has **Also apply filter to known sources**, default off.
Here “known sources” includes both known classes and all claimed-source flags.
The groups are detection/CNN, global spectral quality, spectrum S/N, motion,
SUBLIME cutouts, each lane's visual classes, and SUBLIME2 fit chi-square.
The same exemptions apply before SQL selection and during Python filtering.
Catalog selection, type ranges, publication/claim selectors, duplicate
selection, and apparent-photometry/parallax cuts remain explicit selections.
Checkboxes round-trip through copied filter links. Defaults include both
publication populations; the discoveries preset excludes known candidates too.

## Volume completeness

The tab immediately after Potential duplicates uses a separate census of the
selected input catalogs. It retains applied **quality** settings and their
known-source opt-ins, clears publication/claim selectors, and uses preferred
L0+ types across all density bins without brightness cuts. This keeps known
recoveries in the census even when a discoveries-only preset is active.
Duplicates and inactive objects are excluded. Each input catalog is counted
individually; the union counts an OID once. Memberships overlap, so individual
catalog counts must not be added. Catalog records without a preferred type
are not counted. Choosing no global quality cut admits more unvetted sources.

Density calibration: [Best et al. 2024, ApJ 967, 115, Table 3](https://ui.adsabs.harvard.edu/abs/2024ApJ...967..115B/abstract),
individual `[L0,L1)`, …, `[Y1,Y2)` bins and the Y2 point, with the published
Poisson uncertainties. The numerical values in that table are multiplied by
`1e-3` to obtain pc^-3. This is the latest directly usable spectral-type census
found in a literature search on 2026-11-06. Kirkpatrick (2024) was also checked;
its principal density table is in effective-temperature bins and is not
remapped to spectral type here. Best's close binaries count once as unresolved
sources; resolved components in MOCAdb can introduce a population mismatch.
The sparse Y2 calibration is shown but no magnitude relation is extrapolated.

`V_count = N/rho` and `r_count = (3 V_count / (4 pi fsky))^(1/3)` are
**count-equivalent** quantities, not a demonstrated complete spatial boundary.
The distance axis is labeled **Volume-complete distance (pc)**. All three
completeness plots have independent **Log y-axis** checkboxes, on by default;
unchecking one switches only that plot to a linear axis. Zero counts remain
explicit in the table when logarithmic axes omit them.
Both the inclusive quality-selected count and a conservative subset (published
spectroscopy or good-family spectral review plus motion >=5) are plotted.
Claimed and photometric candidates are not assumed confirmed. Garwood 68.27%
count intervals preserve nonzero upper limits for zero-count bins; combining
their extrema with density errors gives an envelope, not a joint 68% interval.

Magnitude sequences are read from MOCAdb `moca_sequences` and
`data_astro_sequences`: `sptn_mj_field` (mixed-system J) and
`sptn_mw2_aw_field` (AllWISE W2). Values and available scatter are interpolated
only inside the stored validity range. For each of 40 integration points per
type bin, `d_band=10^((m_3sigma-M_band+5)/5)`, and the OR rule takes
`max(d_J,d_W2)` before averaging volume. Missing relation coverage is reported;
when neither band covers part of a bin, its expected count is unavailable.
Missing W2 scatter is not fabricated. Expected-count envelopes include density
errors and available relation scatter, not uncertainty in the sky footprint.

Current synthetic SPHEREx J/W2 errors supply an empirical default depth:
`m_3sigma = m - 2.5 log10(3 sigma_m ln(10)/2.5)`. Only active objects/spectra,
nonignored synthetic photometry linked to packs 55/62/76, and finite magnitude
errors >0 are used. The newest valid measurement per object/band is selected;
no quality or detection S/N cut is imposed. The cache reports median and
16th/84th percentiles. On 2026-11-06 these medians were J=18.633 and W2=15.745
Vega mag, based on 9271/9270 unique objects. Positive-flux selection, source
noise and spatially varying coverage can bias these sample-conditioned depths.
They are not a measured sky selection function. Limits and sky fraction are
editable; sky fractions are remembered separately for each catalog and its
union during the session, defaulting explicitly to 1.

[Bock et al. 2026](https://ui.adsabs.harvard.edu/abs/2026ApJ...999..139B/abstract)
provides flight-based per-channel sensitivity projected over four surveys;
this is cited for context, not substituted for current synthetic-band depth.
There is no automatic proof of missing late-T dwarfs: footprint, selection,
contamination, unresolved multiplicity, extinction, relation scatter and local
density gradients must be considered. A radial completeness claim needs a
sky/depth selection function and distance-dependent recovery tests.

Reference/depth cache: `~/Library/Caches/MOCAviz/sublime-completeness-v1.json`
(or `MOCAVIZ_COMPLETENESS_CACHE`), versioned and refreshed after seven days or
on request. It contains the density table, sequence values/provenance and
aggregate depths only—no credentials or object records. Requests authenticate
with MOCAdb even when the cache is warm; every census uses a read-only
transaction. The tab has independent failure/retry state and exports the
chosen catalog's bins, uncertainties, limits, sky fraction and references as CSV.


**Scale curves to L1-L5** (off by default) normalizes the two observed distance
curves and the all-source distance error bars by the same factor: the median
of `d_(J or W2) / r_count` over finite, positive L1 through L5 bins (inclusive).
The selected catalog and current depth/sky inputs determine the factor, which
is shown with the number of usable bins. Empty/zero-count bins and unavailable
predictions are skipped; if no bin is usable, the curves remain unscaled with
an explicit message. This is a shape comparison only: sensitivity curves,
counts, tabulated volumes/distances, other plots and CSV values remain physical
and unscaled.


The **Observed and expected counts** plot has its own independent **Scale curves
to L1-L5** checkbox, also off by default. It multiplies both observed count
curves by the median `N_expected / N_all` in usable L1–L5 bins. The expected
curve/error envelope, underlying counts, table, export and distance plot are
unaffected. The count and distance factors are computed separately in their
respective units and displayed beside their checkboxes.


## Median S/N versus fit chi-square

The overview's **Median S/N vs. fit χ²** plot pairs the median signed Fλ/σ
from valid, nonignored pixels in **1 ≤ wavelength ≤ 5 µm** with stored reduced
chi-square from the **same active spectrum**. This fixed range is independent
of the other S/N panels' statistic/wavelength selectors; it excludes 0.75–1 µm.
The existing exact-spectrum fit provenance rules apply (autotype JSON first,
then matching stored autotype comments), with no new template fit performed.
Automatic lane selection ranks reviews across SPIFFStacker, SPIFF and
SUBLIMEaperture, with SPIFFStacker winning ties; forced selections never fall
back to another lane. Missing paired values are omitted and counted.

Open diamonds identify objects marked **peculiar_ucd in any reduction**; hover
lists which reductions carry that label, alongside the plotted reduction,
spectrum ID, valid-pixel count, selected-lane review and fit provenance.
Colors retain the atlas population classes; clicking a point opens the object
inspector. Independent logarithmic-axis toggles allow signed/nonpositive values
to be displayed on linear axes (both axes default logarithmic).


## Refresh feedback

**Refresh data** displays a sticky status banner with a spinning indicator and
elapsed time. It first shows **Refreshing data…** for the catalog/review/photometry
query, then **Refreshing spectra…** with actual diagnostic progress. The button
is disabled and reads **Refreshing…** until both phases finish. A persistent
checkmark and **Refresh complete** identify success; failures show **Refresh
failed**, and unsuccessful diagnostic batches produce **Refresh completed with
gaps** with a retry message. All outcomes re-enable the refresh button.

Applying another filter set cancels the previous refresh and starts a new one;
responses from earlier requests cannot stop or overwrite the current indicator.
The feedback has accessible status text and honors reduced-motion preferences.

The spectral-type histogram reserves space above the axes for its wrapping
legend, keeping every legend entry clear of the bars on narrower cards.
