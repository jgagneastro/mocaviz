# Deprecated Dash application

This directory is an unsupported archive of the former MOCAviz Dash
application. Production does not import, mount, or deploy this application.
New features and fixes belong in `bd_colors_fast/`.

The archive includes every former Dash page, including the retired
`mcmc-rvs`, `oage-pdfs`, and `trueflow-age-pdfs` applications. The production
Flask app keeps migration redirects for these old URLs:

- `/mcmc-rvs` redirects to `/legacy-radial-velocities`.
- `/oage-pdfs` and `/trueflow-age-pdfs` redirect to `/age-pdfs`.
- Equivalent `/js/...` aliases redirect to the same canonical replacements.

## Layout

- `app.py`: standalone historical Dash entry point.
- `pages/`: pages that were registered by the former production Dash app.
- `assets/`: Dash-specific styles and browser assets.
- `utils/`: helpers imported only by archived Dash pages.
- `retired_pages/`: older experiments that were already deprecated.
- `notes/`: historical development artifacts.

## Historical local run

The archive is kept runnable for investigation, but it is not covered by the
production test suite or deployment support:

```bash
pip install -r deprecated/dash/requirements.txt
python deprecated/dash/app.py
```

Some pages require private MOCAdb credentials and historical database schema.
