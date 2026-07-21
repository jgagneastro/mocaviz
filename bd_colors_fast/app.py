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


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from mocaviz import app as _production  # noqa: E402


app = _production.app
server = app


def __getattr__(name: str) -> Any:
    """Delegate legacy module attributes to the maintained implementation."""

    return getattr(_production, name)


if __name__ == "__main__":
    port = int(
        os.environ.get(
            "BD_COLORS_FAST_PORT",
            os.environ.get("MOCAVIZ_PORT", "8061"),
        )
    )
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)
