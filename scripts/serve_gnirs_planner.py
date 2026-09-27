"""Run a local private planner with an explicitly configured shared cache.

Credentials come only from the browser, never this command or the environment.
No access logs, debugger, reloader, PID files or per-user caches are created.
"""
import argparse
import logging
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-file', help='Existing shared SQLite deployment bundle; defaults to MOCAVIZ_GNIRS_CACHE_FILE.')
    parser.add_argument('--port', type=int, default=8796)
    parser.add_argument('--check', action='store_true', help='Validate the cache read-only and exit without starting a server.')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    if args.cache_file is not None:
        os.environ['MOCAVIZ_GNIRS_CACHE_FILE'] = args.cache_file

    from gnirs_wsgi import application, app
    from mocaviz.gnirs_planner import cache
    from werkzeug.serving import WSGIRequestHandler, run_simple

    try:
        path = cache.cache_path()
        meta = cache.validate_ready(path)
    except (cache.CacheUnavailable, OSError) as exc:
        parser.exit(2, f'GNIRS startup stopped: {exc}\nSupply --cache-file /private/path/gnirs.sqlite or set MOCAVIZ_GNIRS_CACHE_FILE.\n')

    print(f'Shared GNIRS cache ready: {meta["catalog_count"]:,} objects.', flush=True)
    if args.check:
        return 0

    class QuietHandler(WSGIRequestHandler):
        def log(self, *args, **kwargs):
            pass  # Request URLs can contain credentials.

    logging.getLogger('werkzeug').disabled = True
    app.logger.disabled = True
    print(f'Open http://localhost:{args.port}/js/gnirs-planner', flush=True)
    run_simple('127.0.0.1', args.port, application, threaded=True,
               use_debugger=False, use_reloader=False, request_handler=QuietHandler)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
