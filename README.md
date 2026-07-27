# MOCAviz

MOCAviz contains the interactive visualization tools for the MOCA database.
The maintained Flask application is the production site. The former Dash
application is retained only as an unsupported archive under
`deprecated/dash/` and is never imported by the production entry point.

## Repository layout

- `app.py`: production WSGI entry point used by Passenger.
- `mocaviz/`: maintained Flask application package, static pages, and APIs.
- `bd_colors_fast/`: compatibility launcher for older local automation; it
  delegates to `mocaviz/` and contains no maintained application code.
- `sql/`: manually reviewed database indexes, schema changes, staging scripts,
  and views, grouped by purpose.
- `scripts/`: maintenance, browser-probe, and benchmark helpers.
- `tests/`: production regression tests.
- `deprecated/dash/`: retired Dash entry point, pages, assets, and helpers.

Production pages use canonical root-level URLs such as `/bd-colors`. Existing
`/js/...` bookmarks and API clients remain supported by mounting the same Flask
application at `/js`. Deprecated Dash-only URLs redirect to maintained
replacements where one exists; they do not start or import the Dash archive.

## Run locally

Create and activate a virtual environment, then install the production
dependencies:

```bash
python -m venv mocaviz-env
source mocaviz-env/bin/activate
pip install -r requirements.txt
```

Start the production entry point:

```bash
python app.py
```

Then open `http://127.0.0.1:8050/`. A network-free page check can use
`http://127.0.0.1:8050/bd-colors?mock=1`.

MOCAviz is tested with Python 3.11+.

## Batch spectral-typing chi-squared exports

`scripts/batch_spectral_typing_chi2.py` processes a CSV, TSV, or
one-value-per-line list of `moca_oid` values without opening browser tabs. It
resolves each object to its spectra, requests compact spectral-typing results,
and writes:

- one chi-squared CSV per comparison under `chi2/`;
- `combined_chi2.csv` containing every successful result;
- an append-only `manifest.csv` with successes, missing spectra, and errors;
- `run_config.json`, which prevents incompatible processing settings from
  being mixed in one output directory.

An input file may be as simple as:

```csv
moca_oid
602
10995
```

Run the private-database batch with:

```bash
python scripts/batch_spectral_typing_chi2.py moca_oids.csv \
  --user collaborators \
  --dbase mocadb_private_tables \
  --output-dir student_chi2
```

The command prompts for the password. For unattended execution, set
`MOCAVIZ_PASSWORD` in the environment; do not put the password in a command,
URL, or input file. The default `--spectrum-policy all` produces a separate
CSV for every spectrum belonging to an object. Use `--spectrum-policy
composite` to type all spectra from one object together, or
`--spectrum-policy first` to explicitly select its lowest numbered
`moca_specid`. Composite comparisons normally accept at most eight spectra.

Successful outputs are skipped automatically when the command is rerun.
Transient failures are retried, and failed comparisons remain eligible on the
next run. Start with the default single worker; use `--workers 2` only when
the server has capacity. See every processing and recovery option with:

```bash
python scripts/batch_spectral_typing_chi2.py --help
```

## Test

Run the unit suite from the repository root:

```bash
python -m unittest discover -s tests -v
```

For rendered-page checks, use `scripts/chromium_probe.mjs` as documented in
`AGENTS.md`.
