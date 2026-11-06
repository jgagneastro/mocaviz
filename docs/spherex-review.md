# SPHEREx autotype and visual quality review

The maintained Flask application serves:

- /spherex-autotype — inspect and refit reduced spectra, including previously reviewed objects.
- /spherex-review — start with unclassified reduced spectra and review a queue.
- Both paths also work under /js/.

These pages are self-contained in mocaviz. They do not need spherex_pipeline,
T3_ext, local figures, OCR, sidecar JSONs, or local CNN weights.

## Open a page

Use the same account/database parameter names as the other mocaviz pages:

    /spherex-review?lane=spiffstacker#user=collaborators&pwd=URL_ENCODED_PASSWORD&dbase=mocadb_private_tables

For database submissions, supply user=management and that account's password.
Encode the password using URLSearchParams or percent-encoding (especially &, #,
+, % and =). Existing ?user=...&pwd=...&dbase=... URLs also work.

The fragment (#) form is preferred: the browser never sends the fragment to the
web server. Query-string credentials necessarily reach the initial web request
and may be recorded by an upstream proxy unless its logging is disabled.

The supplied URL is kept unchanged on load, including credentials in either
the query string or fragment, so refreshing can reuse them. Credentials are
also read into tab memory. API requests carry them in
X-MOCA-User, X-MOCA-Password and X-MOCA-Database headers over HTTPS. No cookies,
localStorage, sessionStorage, environment fallback, saved config, database
connection pool, application session, or credential cache is used by these
tools. Unlike those storage mechanisms, the URL remains visible and may be
saved in browser history or bookmarks; do not share credential-bearing links.
Quit clears the in-memory credentials and review data, but leaves the supplied
URL intact. Refreshing starts a new review session with submissions disabled.

Only mocadb.ca:3306 and mocadb_private_tables are accepted. Collaborators can
read spectra and calculate fits. The API authenticates the supplied account
against the database for every request. Management credentials are required for
preview, submission, bad-pixel changes and undo; hiding buttons is not the
authorization boundary. No management/collaborator password is shipped in code.

A synthetic, fully offline demo is available at /spherex-review?mock=1.
Demo requests can never write, even if management credentials are also supplied.

### Open one spectrum

Supply `specid=2860761` (or `moca_specid=2860761`) in the page query string,
or enter it in **Spectrum ID** and press Enter / **Load [Alt+L]**.
A pasted spectral-typing URL is also accepted: only its spectrum ID is used,
never its credentials. When embedding a full URL as the `specid` query value,
percent-encode it with `URLSearchParams`; a plain numeric ID is simpler.

The exact spectrum takes precedence over the reduction lane, object IDs,
pending-only and other queue filters, including for older or ignored spectra.
Its object must still be active. Clear the spectrum field to resume queue loading.
SPIFF, SPIFFStacker and SUBLIMEaperture spectra automatically select their lane
and retain the usual management review workflow. Spectra in other packages (or
with no package) display the spectrum and template matches in **read-only** mode.
Refitting remains available, but classification, write previews, saving spectral
types and flagging pixels are disabled. The server rejects write previews for
these spectra and continues to verify package membership on submission and undo.

## Workflows and data

| Lane | Reduced spectrum pack | Vetting table | Autotype calculation method |
| --- | --- | --- | --- |
| SPIFF | 55 | pcat_spherex_visual_vetting | spherex_autotype |
| SPIFFStacker | 62 | pcat_spherex_spiffstacker_visual_vetting | spiff_stacker_autotype |
| SUBLIMEaperture | 76 | pcat_spherex_sublimeaperture_visual_vetting | sublimeaperture_autotype |

Existing legacy spherex_sublimeap_autotype rows remain supported. The queue selects
the newest spectrum in the chosen lane for each active object. It supports
explicit object IDs, minimum S/N, minimum **adopted** spectral-type number, adopted-type publication IDs, missing
spectral-vetting scope, a minimum WiseView motion score, and exclusion of already
known nonphotometric M/L/T/Y spectral types.

**Missing spectral vetting** defaults to the selected reduction lane on the
review page, and to **No restriction** on the autotype page. Other choices are
SPIFF, SPIFFStacker, **either missing** (OR), **both missing** (AND), and
**Unreviewed here · viable elsewhere**.
“Missing” means no row in the corresponding visual-vetting table, regardless
of the class stored in any existing row. A missing-vetting filter selects
non-ignored spectra, taking the latest active spectrum in the chosen reduction
lane. **No restriction** retains the previous include-reviewed behavior,
including ignored spectra. The API's existing `pending_only` option remains
supported when `missing_vetting` is omitted.

The viable option requires no review in the selected lane and at least one
review of **good**, **good candidate**, **peculiar UCD**, **contaminated UCD**,
**incomplete but promising**, **good plus star**, **good reddened**, **weird**,
or **late M** in either companion lane.

**WiseView score ≥** uses `pcat_wiseview_visual_vetting.classification_integer`.
Blank disables this filter; a number from −1 through 6 applies an inclusive
threshold, so 4 selects scores 4, 5, and 6, and 6 selects score 6. Objects without
a numeric motion review do not pass a nonblank threshold. Both filters combine
with the other queue filters and persist for **Next batch**. They select objects;
**Reduction lane** still determines which spectrum loads and which table gets
reviewed. For example, choose SPIFFStacker, missing SPIFFStacker, and score ≥4
to review unvetted stacked spectra of objects with a motion score of at least 4.

The query parameters `missing_vetting=lane|spiff|spiffstacker|either|both|viable_elsewhere|all`
and `min_wiseview_score=4` can preset these controls. Exact spectrum-ID mode
continues to bypass every queue filter. No classification or spectral-type
write behavior changes. New filters fail visibly against outdated API workers
rather than silently loading an unfiltered queue.
It pages in configurable batches (default 300; range 1–500), using the selected queue order’s cursor.
Loading a new queue also counts all objects matching its filters. The total
is shown separately from the objects loaded into the tab.
After the displayed spectrum finishes fitting, the next ten visible objects in
this loaded queue are fitted sequentially in the background. Advancing reuses
those fits and replenishes the ten-object look-ahead. Navigation takes priority
over queued background work; a fit already running finishes before the newly
selected target starts. Cached fits include the reduction lane, exact spectrum
ID, adopted SPT source and fitting options. Reload, Refit, Undo and Quit discard queued work and
stale results. Up to 24 fits stay in this tab's memory for forward/back navigation;
background fitting never submits classifications or spectral types.

Fits use database moca_spherex_templates/data_spherex_templates and
moca_spectra/data_spectra. The numerical functions were ported from
spherex_pipeline/spherex_autotype.py at e570730: 100 Å nearest-bin matching,
10% flux uncertainty floor, capped weights and residuals, robust trimming,
non-field odds penalties, two-pass bad-pixel rejection, and pec/gravity labels.
Unlike the desktop fallback, the web tool will not fit DB-ignored pixels when
too few usable pixels remain. Quality rejection still works without a valid fit.
Templates and fits are never written to disk or shared between users.

Raw SPIFF reductions, local CSV uploads, cutout browsing, PNG deletion/movement,
OCR, binary fitting, local CNN inference, bulk classification and sample-folder
filters are not part of these pages. They operate on reduced spectra already
stored in MOCAdb. There is no database migration or new table.

Plots are browser Plotly traces; the Python request path does not import
Matplotlib or create images, temporary files, JSONs, ledgers or disk caches.
Python bytecode writing is disabled before review code can trigger lazy imports.

The figure follows the desktop PNG's default square, three-row layout: best
match at the top, repeated hollow gray measurements with uncapped error bars,
faint orange crosses for flagged pixels, red template samples and the same
1000-point interpolating cubic curve, pale-blue zero baselines, and red type/χ²
labels. Template spans set the row spacing and y limits; lower-row points and
error bars are clipped at the adjacent baseline. Flux retains the PNG's units
(with a scientific multiplier), not median normalization. Black boxed axes,
light grids and typography match the original. Both review pages and all three
lanes share this renderer. Optional desktop CNN/binned overlays remain outside
the web tool's scope.
The tool title and object details stay in the surrounding UI, not repeated
inside the plot; the top margin only reserves room for the flux multiplier.

## Database actions

Submissions are off until explicitly enabled in the tab. New spectral-type
measurements have an explicit visibility selector and private RLS input
(defaults match the desktop workflow: private, gagne). Replacing a stored review
or explicitly replacing an autotype fit requires the replacement checkbox.

- Quality classification upserts the lane's vetting table and updates only
  differing photometric/ignored flags on its existing autotypes, preserving fit
  values and visibility. If there is no autotype and fitting succeeds, it inserts
  the fitted type with the same classification flags.
- `good`, `peculiar_ucd`, `contaminated_ucd`, `good_reddened` and `good_plus_star`
  set `photometric_estimate=0, ignored=0`. `good_candidate`,
  `incomplete_but_promising` and `weird` set `photometric_estimate=1, ignored=0`.
  Other classes are rejected and set `ignored=1`, including `giant` and legacy
  `risky_andromeda`; their photometric flag is preserved. The existing `late_M`
  category remains usable and retains its photometric flag.
- Good and candidate decisions explicitly reactivate ignored spectra in the
  selected lane; rejected decisions ignore that lane's spectra. Other lanes,
  literature spectral types and ignored spectral pixels are unaffected.
- Save type explicitly upserts the current best-fit autotype and applies the
  stored classification's photometric/ignored policy to it and the lane's spectra.
  An unvetted/non-usable spectrum's new type remains ignored.
- Flag bad pixels updates only the newly flagged points in the selected spectrum.
- Every successful action and undo adds a moca_changelog entry in the same
  transaction. DB worker triggers remain enabled; adopted/public_adopted fields
  are never assigned.

Preview is a dry run: it returns row counts and the complete prepared rows, with
no writes or commit. The browser requires the current write-policy capability;
old prepared receipts are rejected after a policy change. Queue submissions obtain that same server-computed preview
before committing. The browser cannot invent a best-fit row, pixel list or SQL
table: it must submit a signed, expiring preview receipt.

Each action uses one database transaction. The object, review rows and selected
spectrum pixels are locked and checked against the displayed revisions before
writing. The shared template grid is read without FOR UPDATE. Disappeared
spectra and changed results cause a conflict, not a stale foreign-key upsert.
Any error before commit rolls back vetting, spectral-type/pixel changes and the
changelog together.

Results advance immediately while submissions run serially from a browser queue.
The pending counter includes queued and active requests. Failures return to the
review queue, with a manual retry button. Write requests are not blindly retried
after connection loss because the commit outcome can be uncertain.

Undo receipts hold the before/after state in tab memory, signed using a
domain-separated HMAC key derived from the supplied management password. The
server stores neither the receipt nor a session secret. This works across
workers, expires after 24 hours, and refuses to overwrite newer database changes.
Navigation and shortcut bindings include numeric keypad equivalents, arrows,
Home/End, Backspace/U/Ctrl-Z/Cmd-Z, O (object report), W (WiseView), and Q.
WiseView uses a 30 arcsec FOV, maxdyr=1, a 2.64664-year window and zoom=20.0.

Quit confirms pending work and cancels browser-queued requests. Closing a tab
also triggers the browser's pending-work warning. An HTTP request already sent
may still commit even after its browser fetch is aborted; check the database
before reclassifying such an object. Successful commits are durable; unsent
decisions and tab-only undo history are lost on closing/refreshing.

## Deployment: retain the no-file-write contract

Install the normal mocaviz dependencies and deploy the existing WSGI application.
No pipeline dependency or writable output directory is needed. Set
PYTHONDONTWRITEBYTECODE=1 at process startup as well. Run production without Flask
debugging or a request/response recorder.

Restart the application's Passenger/Gunicorn workers after deploying Python
changes. Updated static assets can otherwise be served alongside old API code.
The browser checks the returned spectrum ID and review metadata, and refuses to
display a mismatched or outdated response instead of falling back to the queue.
As a credential-free deployment check, POST
`{"mock": true, "moca_specid": 2860761}` to `/js/api/spherex-review/queue`:
the response must contain exactly one item with that spectrum ID, `lane: null`
and `read_only: true`, rather than the six-item demo queue.

The application performs no request-time filesystem writes. Web-server,
Passenger/Gunicorn, reverse-proxy, monitoring and operating-system logging are
separate deployment settings: do not enable file access/error logs or capture
URL query strings, credential headers, JSON bodies or tracebacks for these
routes. Also disable request/response disk buffering at the reverse proxy.
The included nginx example lists both pages, their API, and their only assets.
Apply equivalent settings to the actual upstream/Passenger configuration;
these repository changes do not change the running production server.

For a strict deployment, make application files read-only to its service user
and run a filesystem audit/read-only container test after proxy configuration.
Database persistence and database-internal transaction logs are naturally needed
for explicitly authorized database changes; the zero-file rule concerns the
web application's files, figures, caches, request logs and temporary output.

## Verification

Run without production credentials:

    PYTHONDONTWRITEBYTECODE=1 python -B scripts/check_spherex_no_files.py
    PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_root_routing.py
    node --check mocaviz/static/spherex_review.js
    node --test tests/spherex_review_plot.cjs

With a local mocaviz server:

    node scripts/chromium_probe.mjs --url 'http://127.0.0.1:8050/spherex-review?mock=1' --wait-js "document.querySelector('#plot')?.data?.length > 0" --expect-count '#classifications button==19'
    node tests/spherex_review_browser.mjs http://127.0.0.1:8050
    node tests/spherex_review_prefetch_browser.mjs http://127.0.0.1:8050

The browser regression test intercepts every API call and uses only synthetic
reads or simulated writes. It checks query/fragment URL retention and reload,
absence of cookies and Web Storage, immediate transitions, pending counts, numpad decisions, failure
recovery, retry, undo, object links and quitting with queued requests.


### Catalog and quality queue cuts

Review sample can select All objects, SUBLIME2 (`pcat_sublime_candidates_v2`),
SUBLIME1 (`pcat_sublime_candidates`), CatWISE red movers
(`pcat_catwise2020_red_movers`), or the existing public UCD candidate sample.
Membership materializes distinct object IDs once, so multiple catalog apertures
cannot duplicate a queue item or trigger repeated scans of unindexed catalogs.

The page defaults are SUBLIME2 detection S/N/pix >= 7, SUBLIME2 CNN good
probability >= 0.8, absolute Galactic latitude >= 15 degrees, spectrum median
S/N/pix >= 2 across all wavelengths, and stored autotype reduced chi-squared <= 1.5.
The SUBLIME2 detection cut applies to All objects/SUBLIME2 and is hidden for
other samples. The spectral autotype CNN minimum is independent and defaults
to blank. The separately labelled SUBLIME2 catalog CNN minimum defaults to 0.8
for All objects/SUBLIME2 and blank for other samples. Both CNN controls remain
available for every sample, preserve per-sample catalog choices, and can be
enabled together. A catalog CNN cut requires a SUBLIME2 counterpart.
Numeric blanks disable individual cuts. Missing values fail enabled cuts.

Spectrum S/N is the median of signed flux/positive uncertainty in non-ignored
pixels of the selected spectrum, with a valid positive wavelength. Choose all
wavelengths, 1–5, 1–2.5, 2.5–4, or 4–5 microns; interval endpoints are inclusive,
as in WiseView. Catalog detection S/N is a separate quantity. Reduced chi-squared
uses the latest non-ignored stored autotype for the exact selected spectrum and
lane, preferring robust_reduced_chi2_10pct_cap, reduced_chi2_10pct_cap, then
reduced_chi2 in its comments; no refits or sidecar reads are needed to load a queue.
Galactic latitude uses calc_galactic_coordinates.adopt_as_reference=1.

Only objects without WiseView scores accepts objects with no review row or a
NULL classification_integer. Zero and negative recorded scores are still scores.
The minimum-score control is disabled while this option is checked.
Exclude declared duplicates is checked by default and excludes an ID when
pcat_duplicated_vetting.potential_duplicated_moca_oid matches it and
classification='y'; other duplicate judgments do not exclude it.

Exclude known M/L/T/Y types includes every non-ignored, non-photometric M0+
published (is_public=1) or public-adopted type, including SPHEREx autotypes,
plus the existing
non-autotype spectroscopic types. Unpublished SPHEREx auto classifications are
still eligible for review.

Queue and total COUNT use identical cuts. Next batch retains the cuts at load;
loading an exact spectrum ID continues to bypass all queue cuts. Queue filter
version 9 prevents new pages from silently loading unfiltered results from old
workers; restart the local service after deploying the Python update.


Queue ordering defaults to `gal_cnn_spt_snr`: latitude bands take precedence
in the order |gb|>15, 10<|gb|<=15, |gb|<=10, then unavailable latitude. This
uses calc_galactic_coordinates.adopt_as_reference=1; 15 degrees belongs to the
middle band and 10 degrees to the low band. The minimum-latitude filter remains
15 degrees by default; lower bands appear when it is lowered or cleared.
Within each latitude band, first the selected CNN P(good)>=0.8 bin, then the
below-0.8/unavailable bin. Within each CNN bin, the selected adopted types
(private: adopted=1; public: public_adopted=1; both require ignored=0) are rounded to the nearest integer subtype and sorted
latest-to-earliest; half subtypes round away from zero. Within each rounded
subtype, sort by decreasing median signed flux/uncertainty over valid,
non-ignored pixels at 1–2 microns (inclusive) in the selected reduction lane.
This fixed sorting band is independent of the spectrum S/N filter's chosen band.
Untyped objects sort last in each CNN bin; missing 1–2 micron S/N sorts last
within a subtype. Object ID breaks remaining ties. CNN priority source defaults
to the mean of the spectral autotype and highest valid SUBLIME2 catalog
probabilities when both are available, otherwise the single available value.
Zero is an available probability; when both are missing, use the lower-priority
bin. The source can still be set to either CNN individually. The selected value
is not used as a continuous rank inside a bin.
The former `cnn_spt_snr` order, exact-type and object-ID
ordering choices remain available.

The cursor carries the latitude bin, CNN bin, rounded subtype, median 1–2 micron S/N and
object ID, rather than an offset, so classifying objects between batches does
not skip the next pending objects. Total COUNT ignores this cursor and avoids
sort-only pixel calculations. Other queue filters continue to select the sample;
a minimum CNN probability of 0.8 excludes the lower-priority bin until cleared.
Legacy API requests omitting queue_order retain object-ID order.

**Adopted SPT source** defaults to **Private-adopted**. Choosing **Public UCD
candidates** switches it to **Public-adopted**; leaving that sample restores
the previous source. Either source can be selected manually in any sample.
The selected source controls **Adopted type ≥**, exact and rounded type ordering,
and the adopted SPT and publication/origin beside the object name. Missing public
types never fall back to private types. Public UCD sample membership still requires
a public-adopted photometric M7+ type, even when the source is manually changed.

**Adopted-type moca_pid(s)** accepts publication IDs separated by commas, spaces,
semicolons or new lines. Any listed ID may match, but it must belong to the
selected, non-ignored adopted type; an unrelated measurement does not qualify.
Blank disables this filter. The API accepts `adopted_spt_source=private|public`
and `adopted_spt_moca_pids` as a list of up to 500 IDs. The page also accepts
these query parameters (publication IDs as separated text). Source and publication
filters stay fixed for **Next batch** until a new queue is loaded. Exact spectrum
ID mode bypasses queue filters and retains the selected source for its header.

The optional user-run [SUBLIME2 object-ID index](sql/sublime2_oid_index.sql)
improves direct object lookups. The queue does not require this schema change.


The object header separately shows stored spectral CNN P(good), SUBLIME2
catalog CNN P (highest valid probability across the object's catalog apertures),
and the current fit's reduced chi-squared. Spectral CNN metadata comes from
versioned `spectral_cnn_*` fields in the latest stored autotype comments for the
exact object, spectrum, and reduction method. An ignored autotype can still
provide its CNN before visual review. No local JSON or model is needed by the
web server. Missing/malformed values show — and fail an enabled minimum.

Live template refits update chi-squared but do not recompute the CNN. Its model
and source remain available in the header tooltip/API metadata, and an explicit
web SPT upsert carries its probabilities and provenance forward. An unrelated
spectrum, adopted literature type or SUBLIME2 catalog probability never supplies
a missing spectral CNN value. `min_spectral_cnn_probability` and the existing
`min_cnn_probability` (catalog) API cuts are independent; `cnn_priority_source`
selects `combined` (default), `spectral`, or `sublime2`. The combined source
averages available values before the existing 80% priority-bin split; it does
not change either independent minimum filter.


When every loaded spectrum has been classified and the plot is cleared while
submissions remain, the spectrum area displays a large centered “Upload queue
emptying...” message, a spinner, the remaining count, and uploading/waiting
counts. It updates as jobs finish and disappears when uploads finish, a plot
returns (including a failed submission restored for review), or the session
closes. It does not cover a displayed spectrum. Reduced-motion preferences
retain the loading ring without animation.

When the loaded review queue is exhausted and more results exist, the next
batch loads automatically after pending submissions, fits, and data requests
finish. It keeps the loaded filters, order, and cursor, uses the current batch
size, and preserves Undo history across batches. Failed submissions return to
review before advancing. A failed or empty next-batch response stops automatic
attempts at that cursor; use **Next batch** to retry. Initial page opening,
empty initial results, exact-spectrum mode, and a closed session do not trigger
automatic loading.

Batch size defaults to 300 and accepts integers from 1 through 500. The current
value applies to both Load and Next batch, so changing it need not reset the
loaded queue. Next batch retains the loaded sample filters and sorting cursor.
`batch_size=...` in the page URL can override the default. Exact spectrum IDs
continue to bypass queue filters and batch-size validation.
