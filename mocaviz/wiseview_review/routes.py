"""Stateless Passenger routes: queues and signed review receipts live in the tab.

No local pipeline checkout, shared sessions, generated figures, or cache writes.
Each request can run in a different Passenger worker. Writes retain the original
reviewer's transaction and optimistic-conflict checks and require management.
"""
from __future__ import annotations

import dataclasses
import json
import secrets
import threading
from pathlib import Path
from urllib.parse import urlsplit

import pymysql
from flask import Blueprint, Response, jsonify, request, send_file

from .. import spherex_review as sr
from . import runtime as rt
from .context import AUTH

review = Blueprint('wiseview_review', __name__)
ROOT = Path(__file__).parent
MODES = {'sublime', 'redmovers', 'public_ucd'}
WRITES = {'classify', 'duplicate', 'undo'}
OPERATIONS = {'spectral-options', 'cutout-options', 'queue', 'gaia-cache-status',
              'stats', 'object', 'spectra', 'spectrum', 'frame', 'surveys', 'cutouts', *WRITES}
STATIC = {'app.js':'text/javascript', 'style.css':'text/css', 'favicon.png':'image/png'}


@review.after_request
def private_headers(response):
    response.headers.update({'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer',
        'X-Content-Type-Options':'nosniff', 'X-Robots-Tag':'noindex, nofollow, noarchive',
        'Content-Security-Policy':"frame-ancestors 'self'"})
    return response


def authenticated():
    auth = sr.credentials()
    with sr.connection(auth):
        pass
    return auth


@review.get('/wiseview-review')
@review.get('/wiseview-review/')
def page():
    try:
        auth = authenticated()
    except (sr.ReviewError, pymysql.MySQLError):
        return Response('Not found.',status=404,mimetype='text/plain')
    base = request.path.rstrip('/')+'/'
    html = (ROOT/'index.html').read_text().replace('<head>', '<head><base href="'+base+'">',1)
    html = html.replace('__SESSION_TOKEN__',sr.seal(auth,'wiseview-session',{},lifetime=43200))
    html = html.replace('<body>', '<body data-can-write="'+str(auth['user']=='management').lower()+'">',1)
    return Response(html,mimetype='text/html')


@review.get('/wiseview-review/<name>')
def asset(name):
    if name in STATIC:
        return send_file(ROOT/name,mimetype=STATIC[name])
    if name=='spectrum-plot.js':
        return send_file(ROOT.parent/'static'/'spherex_review_plot.js',mimetype='text/javascript')
    if name=='plotly.min.js':
        import plotly
        return send_file(Path(plotly.__file__).parent/'package_data'/'plotly.min.js',mimetype='text/javascript')
    return Response('Not found.',status=404)


@review.get('/wiseview-review/wiseview-assets/<name>')
def wiseview_asset(name):
    try:
        data,mime=rt.wiseview_asset(name)
        if name=='flash3.js':
            base=request.path.split('/wiseview-assets/')[0]
            data=data.replace(b'"/pawnstars"',json.dumps(base+'/pawnstars').encode()).replace(b'"/xref"',json.dumps(base+'/xref').encode())
        return Response(data,mimetype=mime,headers={'Access-Control-Allow-Origin':'*'})
    except ValueError:
        return Response('Not found.',status=404)
    except Exception:
        return Response('WiseView asset unavailable.',status=502)


@review.route('/wiseview-review/pawnstars',methods=['GET','OPTIONS'])
@review.route('/wiseview-review/xref',methods=['GET','OPTIONS'])
def public_lookup():
    from ..sublime_findings import wiseview_public_lookup
    return wiseview_public_lookup()


def args_for(body):
    mode=body.get('mode','sublime')
    if mode not in MODES:raise ValueError('Invalid review sample')
    filters=body.get('filters',{})
    args=rt.parse_filters(filters)
    if args.table!=rt.review.WISEVIEW_VETTING_TABLE or args.source_table not in (
            'pcat_sublime_candidates_v2','pcat_sublime_candidates',rt.REDMOVER_SOURCE,rt.PUBLIC_UCD_SOURCE):
        raise ValueError('Choose a supported review table')
    if mode=='public_ucd':args.source_table=rt.PUBLIC_UCD_SOURCE
    return args,mode


def empty_session(args,mode,oid):
    return dict(lock=threading.RLock(),state='ready',args=args,mode=mode,oids=[oid],
        object_cache={},fit_cache={},snapshots={},spectral_snapshots={},cutout_snapshots={},undo=[])


def object_context(auth,body,session,oid):
    raw=sr.unseal(auth,body.get('object_token'),'wiseview-object')
    if raw['oid']!=oid:raise ValueError('Displayed object changed; reload it')
    fields={field.name for field in dataclasses.fields(rt.review.ReviewObject)}
    obj=rt.review.ReviewObject(**{key:value for key,value in raw['object'].items() if key in fields})
    obj.__dict__.update(raw['object'])
    session['object_cache'][oid]=obj
    session['snapshots'][oid]=raw['snapshot']
    session['spectral_snapshots'][oid]=raw['spectral']
    return obj


@review.post('/wiseview-review/api/<operation>')
def api(operation):
    if operation not in OPERATIONS:return jsonify(error='Not found.'),404
    context=None
    try:
        origin=request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site')=='cross-site' or (
                origin and urlsplit(origin).netloc.lower()!=request.host.lower()):
            raise sr.ReviewError('Cross-origin access denied.',403)
        if not request.is_json or (request.content_length or 0)>sr.MAX_BODY:
            raise sr.ReviewError('Provide a bounded JSON request.',415)
        body=json.loads(request.stream.read(sr.MAX_BODY+1))
        if not isinstance(body,dict):raise ValueError('Object expected')
        auth=authenticated()
        sr.unseal(auth,request.headers.get('X-Review-Token'),'wiseview-session')
        if operation in WRITES:sr.require_management(auth)
        context=AUTH.set(auth)
        return jsonify(sr.clean(dispatch(operation,auth,body)))
    except sr.ReviewError as exc:
        return jsonify(error=str(exc)),exc.status
    except (ValueError,TypeError,KeyError,json.JSONDecodeError):
        return jsonify(error='Invalid or changed review state. Reload the target before retrying.'),400
    except pymysql.MySQLError:
        return jsonify(error='Database request failed. Reload to verify the current state before retrying.'),503
    except Exception:
        return jsonify(error='Review request failed. Reload to verify the current state before retrying.'),500
    finally:
        if context is not None:AUTH.reset(context)


def dispatch(operation,auth,body):
    if operation=='spectral-options':
        return dict(options=rt.review._autotype_review().BUTTON_SPECS,queue_orders=list(rt.QUEUE_ORDERS))
    if operation=='cutout-options':
        return dict(options=[(s.key,s.classification,s.classification_integer) for s in rt.cutout_vetting.CLASSIFICATION_SPECS])
    mode=body.get('mode','sublime')
    if mode not in MODES:raise ValueError('Invalid sample')
    if operation=='stats':
        return rt.sublime_stats() if mode=='sublime' else rt.redmover_stats(body.get('lane','spiffstacker'))
    if operation=='gaia-cache-status':
        return rt.gaia_crowding.status(sample_mask=2 if mode=='redmovers' else 1)
    args,mode=args_for(body)
    if operation=='queue':
        oids=rt.order_review_oids(rt.optimized_queue(args,mode),args.queue_order)
        if args.limit is not None:oids=oids[:args.limit]
        return dict(state='ready',oids=oids,total=len(oids),start=oids.index(args.start_oid) if args.start_oid in oids else 0,
                    gaia_cache_missing=getattr(args,'gaia_cache_missing',0))
    if operation=='undo':
        item=sr.unseal(auth,body.get('undo_token'),'wiseview-undo')
        oid=sr.integer(item['oid'],'Object ID')
        session=empty_session(args,mode,oid)
        session['undo']=[item]
        return rt.undo_decision(session)
    oid=sr.integer(body.get('oid'),'Object ID')
    session=empty_session(args,mode,oid)
    if operation=='object':
        _,obj=rt.get_object(session,0)
        matches=getattr(obj,'nearby_spectroscopic_l_dwarfs',[])
        alerts=getattr(obj,'nearby_ucd_candidates_and_claims',[])
        primary=rt.duplicate_primary(matches,alerts)
        raw=rt.clean(vars(obj))
        pm=obj.adopted_pm
        raw.update(adopted_pmtot_masyr=pm.get('pmtot_masyr'),duplicate_primary_oid=int(primary['moca_oid']) if primary else None,
                   gaia_neighbors_30=None)
        token=sr.seal(auth,'wiseview-object',dict(oid=oid,object=raw,snapshot=session['snapshots'][oid],
            spectral=session['spectral_snapshots'][oid]),lifetime=43200)
        return dict(object=raw,object_token=token,index=body.get('index',0),wiseview_url=rt.build_wiseview_url(ra_deg=obj.ra_deg,dec_deg=obj.dec_deg))
    obj=object_context(auth,body,session,oid)
    if operation in ('spectra','spectrum'):
        if operation=='spectrum':return rt.spectrum_data(session,oid,body.get('lane','spiffstacker'))
        results={}
        for lane in rt.SPECPACKS:
            try:results[lane]=rt.spectrum_data(session,oid,lane)
            except Exception:results[lane]=dict(lane=lane,error='Spectrum unavailable; retry this object.')
        return dict(version=1,spectra=results)
    if operation=='cutouts':
        result=rt.cutout_data(oid)
        rows=result.pop('vetting_rows')
        context=dict(images=[{key:image[key] for key in ('source_key','cutout_path','source_tables')} for image in result['images']],rows=rows)
        result['cutout_token']=sr.seal(auth,'wiseview-cutouts',dict(oid=oid,context=context),lifetime=43200)
        return result
    if operation in ('frame','surveys'):
        key=secrets.token_urlsafe(24)
        motion={name:obj.adopted_pm.get(name) for name in ('reference_ra_deg','reference_dec_deg','reference_epoch_yr','pmra_masyr','pmdec_masyr')}
        with rt.FRAME_LOCK:rt.FRAMES[key]=(oid,float(obj.ra_deg),float(obj.dec_deg),rt.clean(rt.nearby_marker_items(obj)),motion)
        try:
            if operation=='surveys':return dict(script=rt.survey_script(key).decode())
            html=rt.wiseview_frame(key).decode().replace('<base href="./">','<base href="'+request.path.split('/api/')[0]+'/">')
            return dict(html=html,fragment=rt.build_wiseview_url(ra_deg=obj.ra_deg,dec_deg=obj.dec_deg).split('#',1)[1])
        finally:
            with rt.FRAME_LOCK:rt.FRAMES.pop(key,None)
    if body.get('cutout_token'):
        cutouts=sr.unseal(auth,body['cutout_token'],'wiseview-cutouts')
        if cutouts['oid']!=oid:raise ValueError('Cutouts changed')
        session['cutout_snapshots'][oid]=cutouts['context']
    if operation=='classify':
        def validate_undo(item):
            item={**item,'index':sr.integer(body.get('index',0),'Queue index',0,10000000)}
            session['undo_token']=sr.seal(auth,'wiseview-undo',item,lifetime=43200)
        session['validate_undo']=validate_undo
        result=rt.save_decision(session,0,str(body.get('key','')),str(body.get('comments','')),
            body.get('spectral_classification'),body.get('spectral_lane'),body.get('spectral_specid'),
            body.get('cutout_key'),body.get('cutout_paths'),body.get('spectral_reviews'))
    elif operation=='duplicate':
        def validate_undo(item):
            item={**item,'index':sr.integer(body.get('index',0),'Queue index',0,10000000)}
            session['undo_token']=sr.seal(auth,'wiseview-undo',item,lifetime=43200)
        session['validate_undo']=validate_undo
        result=rt.save_duplicate(session,0,str(body.get('comments','')),body.get('primary_oid'),
            include_sublime_neighbors=body.get('include_sublime_neighbors',True))
    else:raise ValueError('Unknown operation')
    item=session['undo'][-1]
    item['index']=sr.integer(body.get('index',0),'Queue index',0,10000000)
    result['undo_token']=session.get('undo_token') or sr.seal(auth,'wiseview-undo',item,lifetime=43200)
    return result
