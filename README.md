# MOCAviz

MOCAviz contains the interactive visualization tools for the MOCA database.
The maintained Flask application is the production site. The former Dash
application is retained only as an unsupported archive under
`deprecated/dash/` and is never imported by the production entry point.

## Repository layout

- `app.py`: production WSGI entry point used by Passenger.
- `bd_colors_fast/`: maintained Flask application, static pages, and APIs.
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

## Test

Run the unit suite from the repository root:

```bash
python -m unittest discover -s tests -v
```

For rendered-page checks, use `scripts/chromium_probe.mjs` as documented in
`AGENTS.md`.
