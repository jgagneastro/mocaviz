"""Private MOCAviz entry point for the Association Audit reviewer."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from urllib.parse import urlsplit

import pymysql
from flask import Blueprint, Response, jsonify, request

from .. import spherex_review as auth_api
from . import service


review = Blueprint('association_audit', __name__)
ASSETS = Path(__file__).parent
STORES = {role: service.Store() for role in ('collaborators', 'management')}
MAX_BODY = 100_000


@review.after_request
def private_headers(response):
    response.headers.update({
        'Cache-Control': 'no-store',
        'Referrer-Policy': 'no-referrer',
        'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "frame-ancestors 'self'; base-uri 'none'",
    })
    return response


def private_home_card():
    # Public requests never receive this markup. A username and schema alone
    # are insufficient, including when the server has an environment account.
    try:
        auth = auth_api.credentials()
        with auth_api.connection(auth):
            pass
    except (auth_api.ReviewError, pymysql.MySQLError):
        return ''
    return '''<li>
          <a data-js-page href="/association-audit">Association Audit · A/A</a>
          <p class="js-tool-description">Review association relationships using membership overlap, XYZ/UVW plots, and staged database decisions.</p>
        </li>'''


@review.get('/association-audit')
def page():
    try:
        auth = auth_api.credentials()
        with auth_api.connection(auth):
            pass
    except (auth_api.ReviewError, pymysql.MySQLError):
        return Response('Not found.', status=404, mimetype='text/plain')
    html = (ASSETS / 'review.html').read_text(encoding='utf-8')
    css = (ASSETS / 'review.css').read_text(encoding='utf-8')
    js = (ASSETS / 'review.js').read_text(encoding='utf-8')
    return Response(html.replace('<!-- audit-style -->', '<style>'+css+'</style>')
                    .replace('<!-- audit-script -->', '<script>'+js+'</script>'), mimetype='text/html')


class ReadDatabase:
    def __init__(self, cursor):
        self.cursor = cursor

    def query(self, sql, params=None):
        self.cursor.execute(sql, params)
        return list(self.cursor.fetchall())


@contextmanager
def read_db(auth):
    with auth_api.connection(auth) as (_, cur):
        cur.execute('START TRANSACTION READ ONLY')
        yield ReadDatabase(cur)


def make_reader(auth):
    def read(load, report=None):
        return service.read_transaction(lambda: read_db(auth), load, report)
    return read


def request_body(auth):
    origin = request.headers.get('Origin')
    if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (
            origin and urlsplit(origin).netloc.lower() != request.host.lower()):
        raise service.Problem('Cross-origin access denied.', 403)
    auth_api.unseal(auth, request.headers.get('X-Audit-Token'), 'association-audit-session')
    if not request.is_json or (request.content_length or 0) > MAX_BODY:
        raise service.Problem('Expected a small JSON request.', 415)
    raw = request.stream.read(MAX_BODY+1)
    if len(raw) > MAX_BODY:
        raise service.Problem('Request too large.', 413)
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise service.Problem('Expected a JSON object.')
    return body


@review.route('/association-audit/api/<operation>', methods=['GET','POST'])
def api(operation):
    reads = {'session', 'samples', 'catalog', 'pair', 'audit'}
    writes = {'refresh', 'preview', 'apply'}
    if operation not in (reads if request.method == 'GET' else writes):
        return jsonify(error='Not found.'), 404
    try:
        auth = auth_api.credentials()
        with auth_api.connection(auth) as (conn, cur):
            return dispatch(operation, auth, conn, cur)
    except (auth_api.ReviewError, service.Problem) as exc:
        return jsonify(error=str(exc)), exc.status
    except pymysql.MySQLError as exc:
        if exc.args and exc.args[0] in (1044, 1045):
            return jsonify(error='Private MOCAdb authentication failed.'), 403
        return jsonify(error='Database request failed. Refresh to verify the current state before retrying.'), 503
    except (ValueError, TypeError):
        return jsonify(error='Invalid request.'), 400
    except Exception:
        return jsonify(error='Unable to complete this request. Retry or refresh the database list.'), 500


def dispatch(operation, auth, conn, cur):
    store = STORES[auth['user']]
    read = make_reader(auth)
    if operation == 'session':
        return jsonify(token=auth_api.seal(auth, 'association-audit-session', {}, lifetime=3600),
                       can_write=auth['user']=='management')
    if operation == 'samples':
        return jsonify(samples=[], warnings=['Manuscript sample presets are available in the local reviewer.'])
    if operation == 'catalog':
        return jsonify(service.clean(store.public_catalog(read)))
    if operation == 'audit':
        aid, extra = request.args.get('aid',''), request.args.get('extra')
        if not aid or len(aid)>40 or (extra is not None and len(extra)>40):
            raise service.Problem('Choose valid association identifiers.')
        return jsonify(service.clean(store.request_audit(read, aid, extra)))
    if operation == 'pair':
        cur.execute('START TRANSACTION READ ONLY')
        data = service.pair_snapshot(cur, request.args.get('child',''), request.args.get('parent'))
        return jsonify(rows=data, revision=service.digest(data))

    body = request_body(auth)
    if operation == 'refresh':
        return jsonify(service.clean(store.public_catalog(read, refresh=True)))
    if operation == 'preview':
        cur.execute('START TRANSACTION READ ONLY')
        plan = service.make_preview(cur, body)
        return jsonify(plan=plan, token=auth_api.seal(auth, 'association-audit-preview', plan),
                       row_counts={'data_association_relationships':1,'moca_changelog':1})

    auth_api.require_management(auth)
    if body.get('confirm') is not True:
        raise service.Problem('Confirm the previewed change before applying it.')
    plan = auth_api.unseal(auth, body.get('token'), 'association-audit-preview')
    result = service.apply_plan(conn, cur, plan)
    for current in STORES.values():
        current.invalidate()
    return jsonify(result)
