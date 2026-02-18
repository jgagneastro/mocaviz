from dash import Dash, html, dcc, page_registry
import dash
import importlib

#conda install python-dotenv or pip install python-dotenv
from dotenv import load_dotenv
load_dotenv()  # take environment variables from .env.

app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)

# ---- Preload astrometry page at startup (safe now that it registers after layout) ----
try:
    importlib.import_module("pages.astrometry")
except Exception as e:
    try:
        import sys
        sys.stderr.write(f"[mocaviz:init] astrometry preload failed: {e}\n")
        sys.stderr.flush()
    except Exception:
        pass

# ---- Ensure astrometry callbacks exist before serving layout/dependencies ----
@app.server.before_request
def _mocaviz_ensure_astrometry_callbacks():
    try:
        from flask import request
        path = request.path or ""
        if path in ("/_dash-layout", "/_dash-dependencies"):
            cb_keys = list(getattr(app, "callback_map", {}).keys())
            has_ast = any("astrometry-plot-ra" in k or "astrometry-plot-dec" in k for k in cb_keys)
            if not has_ast:
                try:
                    importlib.import_module("pages.astrometry")
                except Exception as e:
                    import sys
                    sys.stderr.write(f"[mocaviz:init] astrometry import before {path} failed: {e}\n")
                    sys.stderr.flush()
    except Exception:
        pass

# ---- Diagnostics: log app identity + callback count at startup ----
try:
    import sys
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

if __name__ == '__main__':
	app.run_server(debug=True)

# The following line is required by Phusion Passenger.
# It exposes the WSGI App using the application variable.
# by jmcouillard using this reference : https://community.plotly.com/t/deploying-dash-app-on-a-wsgi-service/57867
application = app.server
