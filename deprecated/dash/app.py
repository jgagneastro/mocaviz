"""Standalone entry point for the unsupported MOCAviz Dash archive.

This module is intentionally isolated from the production WSGI application.
Do not import or mount it from the repository-level ``app.py``.
"""

from __future__ import annotations

from pathlib import Path

from dash import Dash, html, page_container
from dotenv import load_dotenv


ARCHIVE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ARCHIVE_ROOT.parents[1]

load_dotenv(REPOSITORY_ROOT / ".env")

app = Dash(
    __name__,
    use_pages=True,
    pages_folder=str(ARCHIVE_ROOT / "pages"),
    assets_folder=str(ARCHIVE_ROOT / "assets"),
    suppress_callback_exceptions=True,
)
app.layout = html.Div([page_container])

server = app.server
application = server


if __name__ == "__main__":
    app.run(debug=True)
