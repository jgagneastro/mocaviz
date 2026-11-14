# Current fitted type versus adopted type

The spectral review queue now has two independent type cuts:

- **Adopted type >=** queries the object's selected private/public adopted database type.
- **Current fitted type >=** evaluates the best template fit returned for the exact spectrum being displayed, using the current fit options. An earlier or unavailable fit is skipped locally without writing a vetting or changing a database type. Blank disables this cut. Direct spectrum-ID loads bypass queue cuts.

Selecting SUBLIME3C defaults the current-fit minimum to **10 (L0)**. The header names both the current fit and adopted type. Database queue totals are labeled as counts before the runtime fit cut, and a separate counter reports skipped spectra. Skipped objects are separate from submitted/hidden review decisions; paging continues when an entire batch fails. Navigation remains bounds-safe when the last candidate fails but an earlier retained object is still unreviewed.

This addresses the 2026-11-14 cases where provisional campaign T labels admitted objects whose plotted best fit was K0/M0. It does not establish that the current fitting algorithm is accurate on native DR1 cubes. The SUBLIME3C audit also found limited wavelength matching in the existing reviewer; bulk scientific reclassification and campaign resumption remain held pending native-grid validation. Existing human vettings and adopted literature classifications are preserved.

The change is static: reload the review page to activate it; services need no restart. Existing loaded queues use their original filters until a new queue is loaded. Regression: `node tests/spherex_review_current_fit_browser.mjs`; all API requests are synthetic/read-only and write operations are forbidden in the test. `REVIEW_STATIC_ROOT` optionally tests isolated staging copies named `spherex_review.js.stage` and `spherex_review.html.stage`.
