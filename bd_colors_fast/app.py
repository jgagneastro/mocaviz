"""Compatibility launcher for local tools using the former package path.

Maintained application code lives in :mod:`mocaviz.app`. This module delegates
attribute access there and preserves ``python bd_colors_fast/app.py`` for older
shell helpers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from werkzeug.serving import WSGIRequestHandler


sys.dont_write_bytecode = True
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
# Match the production entry point: local configuration contains paths, while
# private GNIRS authentication still comes only from each browser request.
load_dotenv(REPOSITORY_ROOT / ".env", override=False)
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from mocaviz import app as _production  # noqa: E402


app = _production.app
server = app


def __getattr__(name: str) -> Any:
    """Delegate legacy module attributes to the maintained implementation."""

    return getattr(_production, name)


class PrivatePlannerRequestHandler(WSGIRequestHandler):
    """Keep credential-bearing GNIRS URLs out of the local access log."""

    def log(self, *args: Any, **kwargs: Any) -> None:
        path = getattr(self, "path", "").split("?", 1)[0]
        if path.startswith("/js/"):
            path = path[3:]
        if path.rstrip("/") == "/gnirs-planner" or path.startswith(("/api/gnirs/", "/static/gnirs_planner/")):
            return
        super().log(*args, **kwargs)


if __name__ == "__main__":
    port = int(
        os.environ.get(
            "BD_COLORS_FAST_PORT",
            os.environ.get("MOCAVIZ_PORT", "8061"),
        )
    )
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False,
            request_handler=PrivatePlannerRequestHandler)
