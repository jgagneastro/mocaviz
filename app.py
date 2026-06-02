from dash import Dash, html, dcc, page_registry
import dash
import importlib
import sys
from werkzeug.middleware.dispatcher import DispatcherMiddleware

#conda install python-dotenv or pip install python-dotenv
from dotenv import load_dotenv
load_dotenv()  # take environment variables from .env.

app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)

# ---- Ensure astrometry page is imported before handling any request (per worker) ----
_ASTRO_WARMED = False

@app.server.before_request
def _mocaviz_warm_pages():
    global _ASTRO_WARMED
    if _ASTRO_WARMED:
        return
    try:
        importlib.import_module("pages.astrometry")
        _ASTRO_WARMED = True
    except Exception:
        # Keep trying on subsequent requests if it failed.
        _ASTRO_WARMED = False

# ---- Diagnostics: log app identity + callback count at startup ----
try:
    sys.stderr.write(
        f"[mocaviz:init] app id={id(app)} callbacks={len(getattr(app, 'callback_map', {}) or {})}\n"
    )
    sys.stderr.flush()
except Exception:
    pass

app.layout = html.Div([
	dash.page_container
])

# Print all registered pages
""" print("Registered pages:")
for page in page_registry.values():
    print(f"- Path: {page.get('path', 'N/A')}")
    print(f"  Module: {page.get('module_name', 'N/A')}")
    print(f"  Name: {page.get('name', 'N/A')}")
    print(f"  Keys: {list(page.keys())}")
    print() """

# The following line is required by Phusion Passenger.
# It exposes the WSGI App using the application variable.
# by jmcouillard using this reference : https://community.plotly.com/t/deploying-dash-app-on-a-wsgi-service/57867
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

if __name__ == '__main__':
	app.run(debug=True)
