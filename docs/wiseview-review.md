# WiseView x SUBLIME in MOCAviz

The maintained hosted entry point is `/wiseview-review/`, also available at
`/js/wiseview-review/`. The Findings Dashboard is mounted at
`/sublime-findings/` and `/js/sublime-findings/`. Both cards are rendered in the
home response only after successful collaborator or management authentication
against `mocadb_private_tables`; their URLs are absent from the public home
HTML. Supplying only a username or database name does not reveal the cards.

The reviewer package includes the browser assets and headless query/survey
helpers ported from `sublime/wiseview_web` and the SPHEREx pipeline. It requires
neither checkout at runtime. Existing MOCAviz dependencies supply Flask,
PyMySQL, NumPy and Plotly; no desktop GUI or scientific worker is started.

Queue IDs, review context and Undo receipts stay in browser memory. Signed,
expiring receipts preserve the original displayed snapshots and work across
Passenger workers. Every request uses its supplied MOCAdb account, never a
server environment credential. Classification, duplicate declarations and Undo
require management; collaborators may load and inspect. Writes preserve the
existing atomic transactions, concurrent-change checks and MOCAdb changelog.
Undo receipts are checked for size before committing a review.

WiseView runs in a sandbox with an opaque origin and receives no database
credentials or review token. Its fixed vendor assets and two public lookups are
proxied to avoid HTTPS mixed content; other public survey images load directly.
The browser integration check loads one object, spectra and the image canvas
without submitting classifications.

No server file or configuration changes are needed besides the normal Git
deployment and Passenger restart file. Hosted queue state, figures and reference
caches are kept in memory. Local cutout files and Gaia crowding indexes are not
uploaded by deployment. Optional existing server files can be selected through
`MOCAVIZ_SUBLIME_CUTOUT_ROOT`, `MOCAVIZ_SUBLIME_CUTOUT_FALLBACK`, and
`MOCAVIZ_GAIA_CROWDING_CACHE`; the reviewer only reads them. Missing cutouts are
reported as unavailable. An enabled crowding cut excludes objects without a
verified cache entry. The standalone local services and their current sessions
are independent of the production Passenger restart.

Discovery summaries count each active, nonduplicated, new object once, excluding
known spectroscopic M0+ objects and claimed objects. SUBLIME2 types use the latest
catalog row and must be L0+. Across SPIFF, SPIFFStacker and SUBLIMEaperture,
`good`, `peculiar_ucd`, `contaminated_ucd` and `good_reddened` qualify for confirmed
with motion 5–6, and candidate with motion 1–4. `good_candidate` remains candidate
with a nonnegative or missing motion review. M-type motion 1.5 and negative
motion reviews do not qualify. Unvetted spectra do not enter either count; a
qualifying confirmed lane takes precedence over a candidate lane. Pending-motion
counters keep their separately documented broader quality family.

Run focused checks with:

```sh
python -B -m unittest discover -s tests -p 'test_wiseview_review_hosted.py'
python -B -m unittest discover -s tests/wiseview_transactions -t tests
node --check mocaviz/wiseview_review/app.js
MOCAVIZ_TEST_BASE=http://127.0.0.1:8089 node tests/wiseview_review_browser.mjs
```

The optional browser check reads a private Web Tools connection profile locally,
does not print or persist its credentials, and blocks classification submissions.
Set `MOCAVIZ_TEST_PROFILE=management` to check the management interface. Its
Findings data check uses the synthetic demo; scientific selections are covered
by the existing Findings regression tests.

Survey finders appear as soon as their images finish loading. Successful finders
show PS1 first, immediately below WiseView and SUBLIME cutouts, then the other
surveys in their usual order, including DES last. Below the images, pending
finders are compact, single-spaced loading lines; unavailable or empty results
follow as compact status lines. A later success moves back into the image grid
in survey order. Metadata refreshes cannot restore an older finder layout.

Drag the **Resize spectrum** handle to change the SPHEREx panel's height and its
share of the two-column layout. Focus the handle and use arrow keys for keyboard
resizing. The chosen size remains in this tab when moving between objects.
**Hide WiseView controls [V]** hides the embedded RA/Dec/settings sidebar and
reclaims its space; the same button restores it. The choice applies to prefetched
frames as well as the current one.
