from dash import Dash, html, dcc, page_registry
import dash
import importlib
from pathlib import Path

#conda install python-dotenv or pip install python-dotenv
from dotenv import load_dotenv
load_dotenv()  # take environment variables from .env.

app = Dash(__name__, use_pages=True, suppress_callback_exceptions=True)

# ---- Preload all page modules to ensure callbacks are registered in every worker ----
try:
    pages_dir = Path(__file__).parent / "pages"
    if pages_dir.is_dir():
        for py_file in sorted(pages_dir.glob("*.py")):
            if py_file.name.startswith("_") or py_file.name == "__init__.py":
                continue
            importlib.import_module(f"pages.{py_file.stem}")
except Exception:
    # If anything goes wrong, fall back to Dash's lazy discovery.
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
