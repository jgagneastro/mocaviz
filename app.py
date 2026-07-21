"""Production WSGI entry point for MOCAviz.

The maintained Flask application owns the canonical root URLs.  Mounting the
same application at ``/js`` keeps existing bookmarks and API clients working
without maintaining a second implementation.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

load_dotenv()

from bd_colors_fast.app import app as production_app


# Phusion Passenger imports this module and serves ``application``.
application = DispatcherMiddleware(
    production_app,
    {
        "/js": production_app,
    },
)

# Retain familiar names for shells and tools that import the entry point.
app = production_app
server = production_app


if __name__ == "__main__":
    port = int(os.environ.get("MOCAVIZ_PORT", os.environ.get("PORT", "8050")))
    run_simple(
        "127.0.0.1",
        port,
        application,
        use_debugger=True,
        use_reloader=False,
    )
