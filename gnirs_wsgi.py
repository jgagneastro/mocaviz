"""Optional isolated WSGI entry for strict no-disk GNIRS deployment.

The same blueprint is also registered in the main MOCAviz application. This
entry avoids unrelated page initialization and supports a separate, unbuffered
upstream for the private planner without changing its public URL structure.
"""
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True

# Astropy may otherwise create ~/.astropy on its first use. Point this isolated
# service at an existing, shipped config directory; keep it mounted read-only.
# Visibility disables downloads and needs no persistent astronomy cache.
_astronomy_config = str(Path(__file__).resolve().parent / 'deploy' / 'gnirs-readonly')
os.environ['XDG_CONFIG_HOME'] = _astronomy_config
os.environ['XDG_CACHE_HOME'] = _astronomy_config

from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from mocaviz.gnirs_planner import STATIC, planner

app = Flask(__name__, static_folder=str(STATIC), static_url_path='/static/gnirs_planner')
app.register_blueprint(planner)
application = DispatcherMiddleware(app, {'/js': app})
