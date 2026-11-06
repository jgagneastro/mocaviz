# SPHEREx review queue performance

The CatWISE queue must support large samples even when the stored-type minimum
is blank. With SPIFFStacker, missing vetting in the selected lane, |b| ≥15°,
median spectrum S/N ≥2, stored reduced χ² ≤1.5, and known/duplicate exclusions,
the November 6, 2026 check found 174,912 spectra before the S/N cut and 60,161
after it. These counts are a changing database snapshot, not fixed samples.

The previous query put candidate selection inside a CTE referenced by both its
pixel-window calculation and final selection. MariaDB merged/repeated that
selection. Its plan estimated about 99 million intermediate rows for the exact
count, and roughly twice that work when computing both filter and ordering
bands. The CatWISE and SUBLIME2 object-ID indexes already existed.

The current implementation finishes spectrum selection before pixel reads.
Pixel queries use bound spectrum-ID batches of at most 4,000; there are no
temporary database tables, schema changes, files, or persistent caches.

The median-S/N threshold uses a linear aggregate. More than half the valid
pixels at or above the threshold implies a passing median; fewer implies a
failure. On an exact even split, the average of the largest value below and
smallest value above is the exact median. Missing spectra fail an enabled cut.
Flagged pixels, invalid uncertainties, signed flux, and wavelength boundaries
follow the original selection rules.

For priority ordering, candidate metadata is grouped by latitude, CNN bin, and
rounded subtype. The true 1–2 µm median is calculated only for groups needed to
fill the requested page plus its lookahead item. A boundary group is ranked in
full; it is never truncated before its S/N is known. Existing keyset cursors
continue through that group before advancing. Count requests ignore cursors
and sort-only metadata and apply the same S/N threshold to all eligible spectra.

An isolated local HTTP check loaded consecutive 100-object pages in 23.4 and
21.3 seconds, with no overlap. Its exact count finished in 48.2 seconds and
remains asynchronous in the GUI. On a bounded 200-spectrum reference, the old
SQL and new queue returned exactly the same spectra, S/N values and ordering.
The standard scientific/filter/transaction tests and added median-equivalence
tests require no live database.

Manual live browser verification is available with:

```sh
MOCAVIZ_TEST_BASE=http://127.0.0.1:8089 node tests/spherex_review_live_queue_browser.mjs
```

It reads the existing private collaborator profile locally, blocks all review
submission routes, loads the CatWISE queue and count, and checks a rendered
spectrum. Credentials and retrieved science data are not written by the test.

## Initial page and sample controls

Opening the reviewer performs only its authentication/context check. Opening
the page or changing filters does not load a queue, count objects, or fit spectra.
Applicable filters remain editable while that check is pending; Load becomes
available once it completes. CatWISE, SUBLIME1 and public-candidate samples hide
the SUBLIME2-only detection control. Spectral and catalog CNN minima are
independent controls available for all samples; the catalog minimum defaults
to blank outside All objects/SUBLIME2 and retains each sample's chosen value.
