# Rollback Plan for `/bd-colors-fast`

This document describes how to roll back the experimental `bd_colors_fast`
deployment if it causes problems with the existing Passenger-served Dash app.

The integration is intentionally isolated:

- The existing Dash pages still live under `pages/`.
- The fast JavaScript app lives under `bd_colors_fast/`.
- `app.py` mounts the fast app at `/bd-colors-fast`, `/bd_colors_fast`, and `/js` by wrapping
  `app.server.wsgi_app` with Werkzeug `DispatcherMiddleware`.

## Quick Health Check

After deployment, test these URLs:

```text
https://<deployment-host>/
https://<deployment-host>/bd-colors
https://<deployment-host>/bd-colors-fast/?mock=1
https://<deployment-host>/bd_colors_fast/?mock=1
https://<deployment-host>/js/
https://<deployment-host>/js/spectra?mock=1
https://<deployment-host>/bd-colors-fast/static/app.js
https://<deployment-host>/bd-colors-fast/api/bootstrap?mock=1
```

Expected results:

- `/` should still load the normal MOCAViz home page.
- `/bd-colors` should still load the legacy Dash brown-dwarf color page.
- `/bd-colors-fast/?mock=1` should load the new JavaScript page without querying
  MOCAdb.
- `/bd_colors_fast/?mock=1` should load the same page through the compatibility
  alias.
- `/js/` should load the JavaScript visualizations landing page.
- `/js/spectra?mock=1` should load one of the namespaced JavaScript tools.
- `/bd-colors-fast/static/app.js` should return JavaScript.
- `/bd-colors-fast/api/bootstrap?mock=1` should return JSON with `"ok": true`.

If the root Dash app fails to load, roll back immediately.

## Fastest Rollback: Git Revert

If the deployment commit only contains the `bd_colors_fast` integration, revert
that commit:

```bash
cd /path/to/mocaviz
git log --oneline -5
git revert <deployment_commit_sha>
git push
```

Then restart or reload the Passenger app using the normal deployment mechanism.

This removes:

- the `bd_colors_fast/` directory
- the `/bd-colors-fast`, `/bd_colors_fast`, and `/js` mounts in `app.py`

## Manual Emergency Rollback

Use this if you need to patch the deployed checkout directly before preparing a
proper Git revert.

1. Open `app.py`.

2. Remove this import:

```python
from werkzeug.middleware.dispatcher import DispatcherMiddleware
```

3. Remove the `bd_colors_fast` mount block:

```python
server = app.server

try:
    from bd_colors_fast.app import app as bd_colors_fast_app

    server.wsgi_app = DispatcherMiddleware(server.wsgi_app, {
        "/bd-colors-fast": bd_colors_fast_app,
        "/bd_colors_fast": bd_colors_fast_app,
        "/js": bd_colors_fast_app,
    })
    sys.stderr.write("[mocaviz:init] mounted bd_colors_fast at /bd-colors-fast, /bd_colors_fast, and /js\n")
    sys.stderr.flush()
except Exception as exc:
    sys.stderr.write(f"[mocaviz:init] bd_colors_fast mount failed: {type(exc).__name__}: {exc}\n")
    sys.stderr.flush()

application = server
```

4. Replace it with the original Passenger export:

```python
application = app.server
```

5. Keep the local run block at the end:

```python
if __name__ == '__main__':
    app.run_server(debug=True)
```

6. Move the `bd_colors_fast` directory out of the app tree:

```bash
mv bd_colors_fast /tmp/bd_colors_fast.disabled
```

7. Restart or reload Passenger.

8. Re-test:

```text
https://<deployment-host>/
https://<deployment-host>/bd-colors
```

The `/bd-colors-fast`, `/bd_colors_fast`, and `/js` URLs should now return 404 or the
deployment's normal not-found response.

## Passenger Restart Notes

The exact restart mechanism depends on the server configuration. Common options
are:

```bash
touch tmp/restart.txt
```

or using the hosting panel's Passenger restart button.

If `tmp/` does not exist:

```bash
mkdir -p tmp
touch tmp/restart.txt
```

## Local Verification Before Push

From the local `mocaviz` checkout:

```bash
cd /Users/jonathan/Documents/Python/Python_Packages/mocaviz
/opt/anaconda3-native/anaconda3/envs/mocaviz/bin/python -B -m py_compile app.py bd_colors_fast/app.py
```

Optional WSGI smoke test:

```bash
/opt/anaconda3-native/anaconda3/envs/mocaviz/bin/python -B -c "from werkzeug.test import Client; from werkzeug.wrappers import Response; import app; c=Client(app.application, Response); print(c.get('/').status_code); print(c.get('/bd-colors-fast/').status_code); print(c.get('/js/').status_code); print(c.get('/js/spectra?mock=1').status_code); print(c.get('/bd-colors-fast/static/app.js').status_code); print(c.get('/bd-colors-fast/api/bootstrap?mock=1').json.get('ok'))"
```

Expected output includes:

```text
200
200
200
True
```

## Low-Risk Disable Alternative

If you want to keep the files deployed but disable only the route, remove or
comment out this line in `app.py`:

```python
server.wsgi_app = DispatcherMiddleware(server.wsgi_app, {
    "/bd-colors-fast": bd_colors_fast_app,
    "/bd_colors_fast": bd_colors_fast_app,
    "/js": bd_colors_fast_app,
})
```

and leave:

```python
application = server
```

This keeps the existing Dash app behavior while making `/bd-colors-fast` and `/js`
unavailable.
