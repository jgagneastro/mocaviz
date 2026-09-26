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

On opening the page, credentials move into tab memory and are removed from the
current browser-history URL before assets load. API requests carry them in
X-MOCA-User, X-MOCA-Password and X-MOCA-Database headers over HTTPS. No cookies,
localStorage, sessionStorage, environment fallback, saved config, database
connection pool, application session, or credential cache is used by these
tools. Refreshing requires reopening the original credential-bearing URL.
Credentials are cleared when using Quit.

Only mocadb.ca:3306 and mocadb_private_tables are accepted. Collaborators can
read spectra and calculate fits. The API authenticates the supplied account
against the database for every request. Management credentials are required for
preview, submission, bad-pixel changes and undo; hiding buttons is not the
authorization boundary. No management/collaborator password is shipped in code.

A synthetic, fully offline demo is available at /spherex-review?mock=1.
Demo requests can never write, even if management credentials are also supplied.

## Workflows and data

| Lane | Reduced spectrum pack | Vetting table | Autotype calculation method |
| --- | --- | --- | --- |
| SPIFF | 55 | pcat_spherex_visual_vetting | spherex_autotype |
| SPIFFStacker | 62 | pcat_spherex_spiffstacker_visual_vetting | spiff_stacker_autotype |
| SUBLIMEaperture | 76 | pcat_spherex_sublimeaperture_visual_vetting | sublimeaperture_autotype |

Existing legacy spherex_sublimeap_autotype rows remain supported. The queue selects
the newest spectrum in the chosen lane for each active object. It supports
explicit object IDs, minimum S/N, minimum **stored** autotype number, pending-only,
and exclusion of already known nonphotometric M/L/T/Y spectral types.
It pages in batches of 100 (API maximum 500), using an object-ID cursor.
The next two fits are prefetched into a bounded browser-memory cache.

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

## Database actions

Submissions are off until explicitly enabled in the tab. New spectral-type
measurements have an explicit visibility selector and private RLS input
(defaults match the desktop workflow: private, gagne). Replacing a stored review
or explicitly replacing an autotype fit requires the replacement checkbox.

- Quality classification upserts the lane's vetting table. Existing autotype
  values are preserved; their ignored state is updated. If there is no existing
  autotype and fitting succeeds, the fitted spectral type is inserted.
- Rejected classes also set ignored=1 on spectra in this lane, matching the
  desktop review policy. Usable classes do not automatically unignore spectra.
- Save type explicitly upserts the current best-fit autotype spectral type.
  An unvetted/non-usable spectrum's new type remains ignored.
- Flag bad pixels updates only the newly flagged points in the selected spectrum.
- Every successful action and undo adds a moca_changelog entry in the same
  transaction. DB worker triggers remain enabled; adopted/public_adopted fields
  are never assigned.

Preview is a dry run: it returns row counts and the complete prepared rows, with
no writes or commit. Queue submissions obtain that same server-computed preview
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

With a local mocaviz server:

    node scripts/chromium_probe.mjs --url 'http://127.0.0.1:8050/spherex-review?mock=1' --wait-js "document.querySelector('#plot')?.data?.length > 0" --expect-count '#classifications button==19'
    node tests/spherex_review_browser.mjs http://127.0.0.1:8050

The browser regression test intercepts every API call and uses only synthetic
reads or simulated writes. It checks credential scrubbing, absence of browser
storage, immediate transitions, pending counts, numpad decisions, failure
recovery, retry, undo, object links and quitting with queued requests.
