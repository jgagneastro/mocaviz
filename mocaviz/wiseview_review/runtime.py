#!/usr/bin/env python3
"""Local WiseView review server. No database writes occur until a decision is made."""
from __future__ import annotations

import base64
import dataclasses
import json
import math
import re
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
import time
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlencode

ROOT = Path(__file__).resolve().parent
from . import review_helpers as review
from .cutout_io import read_cutout_bytes
from . import gaia_crowding, spectral_vetting, cutout_vetting
from .context import current_auth
from .. import spherex_autotype_core as core

WEB_CLASSIFICATION_SPECS = (*review.CLASSIFICATION_SPECS,
                            review.ClassificationSpec('e', 'good but M-type', Decimal('1.5')),
                            review.ClassificationSpec('r', 'risky - reddened region', Decimal('-1')))

SPECPACKS = {'spiff': 55, 'spiffstacker': 62, 'sublimeaperture': 76}
NEARBY_UCD_RADIUS_ARCSEC = 50.0
SNR_WAVELENGTH_RANGES = {'1-5': (1., 5.), '1-2.5': (1., 2.5), '2.5-4': (2.5, 4.), '4-5': (4., 5.)}
REDMOVER_SOURCE = 'pcat_catwise2020_red_movers'
PUBLIC_UCD_SOURCE = 'data_spectral_types'
SPECTRAL_VETTING = {'spiff':'pcat_spherex_visual_vetting',
                    'spiffstacker':'pcat_spherex_spiffstacker_visual_vetting'}
TEMPLATE_CACHE = {'time': 0, 'rows': None}
TEMPLATE_LOCK = threading.Lock()
FRAME_LOCK = threading.Lock()
FRAMES = {}
WISEVIEW_HTML = {'text': None, 'time': 0}
WISEVIEW_ASSETS = {}
WISEVIEW_ASSET_LOCK = threading.Lock()
STATS_LOCK = threading.Lock()
STATS_FETCH_LOCK = threading.Lock()
STATS_CACHE = {'entries': {}, 'generation': 0}
RED_SAMPLE_CACHE = {}


def invalidate_sublime_stats():
    with STATS_LOCK:
        STATS_CACHE['generation'] += 1
        STATS_CACHE['entries'].clear()


from .counts import summarize_discoveries


PENDING_GOOD_CLASSES = ('good', 'peculiar_ucd', 'contaminated_ucd', 'good_plus_star', 'good_reddened')
PENDING_CANDIDATE_CLASSES = (*PENDING_GOOD_CLASSES, 'good_candidate')


def pending_spectral_rows(cur, source_table):
    """Positive reviews in any lane, with no motion review at all; one row per lane."""
    if source_table not in ('pcat_sublime_candidates_v2', REDMOVER_SOURCE):
        raise ValueError('Invalid pending-spectrum sample')
    ph=','.join(['%s']*len(PENDING_CANDIDATE_CLASSES))
    reviews=' UNION ALL '.join(
        f"SELECT moca_oid,LOWER(TRIM(classification)) AS spectral_class FROM `{table}` "
        f"WHERE LOWER(TRIM(classification)) IN ({ph})"
        for table,_,_ in spectral_vetting.LANES.values())
    cur.execute('WITH pending_reviews AS ('+reviews+""")
        SELECT v.moca_oid,v.spectral_class FROM pending_reviews v
        JOIN moca_objects mo ON mo.moca_oid=v.moca_oid AND mo.ignored=0
        WHERE EXISTS (SELECT 1 FROM `"""+source_table+"""` p WHERE p.moca_oid=v.moca_oid)
          AND NOT EXISTS (SELECT 1 FROM pcat_wiseview_visual_vetting w WHERE w.moca_oid=v.moca_oid)
          AND NOT EXISTS (SELECT 1 FROM pcat_duplicated_vetting dup
                          WHERE dup.potential_duplicated_moca_oid=v.moca_oid AND dup.classification='y')""",
        PENDING_CANDIDATE_CLASSES*len(spectral_vetting.LANES))
    return list(cur.fetchall())


def summarize_pending_spectra(rows, known, claimed):
    """Each new object counts once; the candidate counter includes the good counter."""
    good, candidate = set(), set()
    for row in rows:
        oid=int(row['moca_oid'])
        if oid in known or oid in claimed:continue
        quality=str(row.get('spectral_class') or '').strip().lower()
        if quality in PENDING_GOOD_CLASSES:good.add(oid)
        if quality in PENDING_CANDIDATE_CLASSES:candidate.add(oid)
    return {'pending_good_spectra':len(good), 'pending_candidate_spectra':len(candidate)}


def sublime_stats():
    # Serialize refreshes; the results are global, independent of queue filters.
    with STATS_FETCH_LOCK:
        with STATS_LOCK:
            cached=STATS_CACHE['entries'].get('sublime')
            if cached and time.time()-cached['time'] < 45: return cached['value']
            generation=STATS_CACHE['generation']
        conn=review._connect_db()
        try:
            with conn.cursor() as cur:
                cur.execute('''SELECT COUNT(DISTINCT p.moca_oid) AS total,
                    COUNT(DISTINCT CASE WHEN w.moca_oid IS NOT NULL THEN p.moca_oid END) AS classified,
                    COUNT(DISTINCT CASE WHEN w.classification_integer <= 0 THEN p.moca_oid END) AS rejected
                    FROM pcat_sublime_candidates_v2 p
                    JOIN moca_objects mo ON mo.moca_oid=p.moca_oid AND mo.ignored=0
                    LEFT JOIN pcat_wiseview_visual_vetting w ON w.moca_oid=p.moca_oid
                    WHERE NOT EXISTS (SELECT 1 FROM pcat_duplicated_vetting dup
                                      WHERE dup.potential_duplicated_moca_oid=p.moca_oid AND dup.classification='y')''')
                progress=cur.fetchone()
                cur.execute('''SELECT p.moca_oid,p.autotype_spectral_type_number,
                    v.classification AS sublimeaperture_class,
                    vs.classification AS spiff_class,vk.classification AS spiffstacker_class,
                    w.classification_integer AS motion
                    FROM (SELECT moca_oid,MAX(id) AS id FROM pcat_sublime_candidates_v2
                          WHERE moca_oid IS NOT NULL GROUP BY moca_oid) latest
                    JOIN pcat_sublime_candidates_v2 p ON p.id=latest.id
                    JOIN moca_objects mo ON mo.moca_oid=p.moca_oid AND mo.ignored=0
                    LEFT JOIN pcat_spherex_sublimeaperture_visual_vetting v ON v.moca_oid=p.moca_oid
                    LEFT JOIN pcat_spherex_visual_vetting vs ON vs.moca_oid=p.moca_oid
                    LEFT JOIN pcat_spherex_spiffstacker_visual_vetting vk ON vk.moca_oid=p.moca_oid
                    LEFT JOIN pcat_wiseview_visual_vetting w ON w.moca_oid=p.moca_oid
                    WHERE NOT EXISTS (SELECT 1 FROM pcat_duplicated_vetting dup
                                      WHERE dup.potential_duplicated_moca_oid=p.moca_oid AND dup.classification='y')
                      AND p.autotype_spectral_type_number >= 10
                      AND (w.classification_integer >= 0 OR w.classification_integer IS NULL)
                      AND (v.classification IN ('good','good_candidate','peculiar_ucd','contaminated_ucd','good_reddened')
                           OR vs.classification IN ('good','good_candidate','peculiar_ucd','contaminated_ucd','good_reddened')
                           OR vk.classification IN ('good','good_candidate','peculiar_ucd','contaminated_ucd','good_reddened'))''')
                rows=list(cur.fetchall())
                pending=pending_spectral_rows(cur,'pcat_sublime_candidates_v2')
        finally: conn.close()
        aut=review._autotype_review()
        oids={int(row['moca_oid']) for row in [*rows,*pending]}
        known=aut.fetch_known_nonphotometric_late_type_oids(source_oids=oids) if oids else set()
        claimed=aut.fetch_claimed_oids() if oids else set()
        result={**summarize_discoveries(rows,known,claimed,require_good_spectrum_for_confirmed=False),
                **summarize_pending_spectra(pending,known,claimed),
                **{key:int(progress[key] or 0) for key in ('total','classified','rejected')}}
        with STATS_LOCK:
            if generation==STATS_CACHE['generation']:
                STATS_CACHE['entries']['sublime']={'value':result,'time':time.time()}
        return result


def redmover_stats(lane):
    if lane not in ('spiff','spiffstacker'): raise ValueError('Invalid CatWISE spectrum lane')
    methods = {'spiff':'spherex_autotype','spiffstacker':'spiff_stacker_autotype'}
    pack = SPECPACKS[lane]
    with STATS_FETCH_LOCK:
        with STATS_LOCK:
            cached=STATS_CACHE['entries'].get(lane)
            if cached and time.time()-cached['time'] < 45: return cached['value']
            generation=STATS_CACHE['generation']
        sample=RED_SAMPLE_CACHE.get(lane)
        if not sample or time.time()-sample['time'] >= 600:
            sample={'oids':redmover_oids(pack, include_reviewed_ignored=True),'time':time.time()}
            RED_SAMPLE_CACHE[lane]=sample
        oids=sample['oids'] - fetch_duplicate_oids()
        conn=review._connect_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT moca_oid,classification_integer FROM pcat_wiseview_visual_vetting')
                motion_rows=list(cur.fetchall())
                by_oid={}
                # The selected spectrum takes precedence if both have reviews.
                for spectral_lane in (lane, 'spiff' if lane=='spiffstacker' else 'spiffstacker'):
                    table=SPECTRAL_VETTING[spectral_lane]
                    cur.execute(f'''SELECT v.moca_oid,v.classification AS spectral_class,
                        d.spectral_type_number AS autotype_spectral_type_number,
                        w.classification_integer AS motion
                        FROM `{table}` v
                        JOIN moca_objects mo ON mo.moca_oid=v.moca_oid AND mo.ignored=0
                        LEFT JOIN pcat_wiseview_visual_vetting w ON w.moca_oid=v.moca_oid
                        LEFT JOIN data_spectral_types d ON d.id=(
                            SELECT MAX(d2.id) FROM data_spectral_types d2
                            WHERE d2.moca_oid=v.moca_oid AND d2.calculation_method=%s AND d2.ignored=0)
                        WHERE EXISTS (SELECT 1 FROM pcat_catwise2020_red_movers c WHERE c.moca_oid=v.moca_oid)
                          ''', (methods[spectral_lane],))
                    for row in cur.fetchall():
                        if row['moca_oid'] is not None:
                            target=by_oid.setdefault(int(row['moca_oid']),row)
                            target[spectral_lane+'_class']=row.get('spectral_class')
                spectral_rows=list(by_oid.values())
                pending=[row for row in pending_spectral_rows(cur,REDMOVER_SOURCE) if int(row['moca_oid']) in oids]
        finally: conn.close()
        spectral_rows=[row for row in spectral_rows if row['moca_oid'] is not None and int(row['moca_oid']) in oids]
        aut=review._autotype_review()
        discovery_oids={int(row['moca_oid']) for row in spectral_rows
                        if row.get('spectral_class') in ('good','good_candidate')
                        and row.get('autotype_spectral_type_number') is not None
                        and float(row['autotype_spectral_type_number']) >= 10}
        discovery_oids.update(int(row['moca_oid']) for row in pending)
        known=aut.fetch_known_nonphotometric_late_type_oids(source_oids=discovery_oids) if discovery_oids else set()
        claimed=aut.fetch_claimed_oids() if discovery_oids else set()
        matches=[row for row in motion_rows if row['moca_oid'] is not None and int(row['moca_oid']) in oids]
        classified={int(row['moca_oid']) for row in matches} | {int(row['moca_oid']) for row in spectral_rows}
        rejected={int(row['moca_oid']) for row in matches
                  if row['classification_integer'] is not None and row['classification_integer'] <= 0}
        rejected.update(int(row['moca_oid']) for row in spectral_rows
                        if str(row.get('spectral_class') or '').lower().split('/')[0] in
                        {'bad','galaxy','halo','reddened','snr','scatter','star','giant','early'})
        result={**summarize_discoveries(spectral_rows,known,claimed,spectral_only_confirmed=True),
                **summarize_pending_spectra(pending,known,claimed),
                'total':len(oids),'classified':len(classified),'rejected':len(rejected)}
        with STATS_LOCK:
            if generation==STATS_CACHE['generation']:
                STATS_CACHE['entries'][lane]={'value':result,'time':time.time()}
        return result


def build_wiseview_url(*, ra_deg, dec_deg):
    """Web-review defaults, independent of other tools using the shared pipeline."""
    base, _, fragment = review.build_wiseview_url(ra_deg=ra_deg,dec_deg=dec_deg).partition('#')
    params = parse_qs(fragment, keep_blank_values=True)
    params['size'] = ['50']
    return base+'#'+urlencode(params,doseq=True)


def web_survey_js(script, *, final=False):
    script=script.replace('title.textContent = titleText;',
                          'title.textContent = window.SurveyEpochs.formatTitle(titleText);\n'
                          '    if (titleText.startsWith("DES DR2 ")) card.style.order = "1";')
    script=script.replace('title.textContent = resolved.title;', 'title.textContent = window.SurveyEpochs.formatTitle(resolved.title);')
    # Both generated viewers share bounded requests, correct CORS handling,
    # cancellation on timeout, and the documented CDS mirror.
    script=re.sub(r'  function loadImage\(src(?:, options)?\) \{\n.*?\n  \}\n',
                  '  function loadImage(src, options) { return window.SurveyImages.load(src, options); }\n',
                  script,flags=re.S)
    for name in ('buildIrgCard()', 'buildYziCard()', 'buildSurveyCard(source)'):
        key='source' if name.startswith('buildSurvey') else json.dumps(name)
        script=script.replace(name+'.catch',
            'window.SurveyImages.card(JSON.stringify([payload.moca_oid,'+key+']), () => '+name+').catch')
    old="""      const cards = await Promise.all(cardPromises);
      panel.replaceChildren();
      for (const card of cards) {
        panel.appendChild(card);
      }
      state.done = true;"""
    new="""      panel.replaceChildren();
      for (const promise of cardPromises) {
        const placeholder = makeInfoCard("Survey", "Loading…");
        panel.appendChild(placeholder);
        promise.then(card => { if (placeholder.isConnected) placeholder.replaceWith(card); });
      }
      state.done = true;"""
    script=script.replace(old,new)
    if final:
        script=script.replace('`${source.label || source.survey} resolving`','`${source.label || source.survey} unavailable`')
        script=script.replace('SIA preview is still resolving','Survey unavailable or no coverage')
    return (ROOT/'survey_images.js').read_text()+'\n'+(ROOT/'survey_epochs.js').read_text()+'\n'+script


def wiseview_asset(name):
    """Proxy only the two fixed HTTP-only vendor assets for HTTPS browsers."""
    types={'flash3.js':'text/javascript; charset=utf-8','flash3-theme.css':'text/css; charset=utf-8'}
    if name not in types: raise ValueError('Unknown WiseView asset')
    with WISEVIEW_ASSET_LOCK:
        cached=WISEVIEW_ASSETS.get(name)
        if not cached or time.time()-cached['time']>3600:
            with urllib.request.urlopen('http://byw.tools/static/'+name,timeout=15) as response:
                data=response.read(3_000_001)
                if len(data)>3_000_000: raise ValueError('WiseView asset is too large')
            cached=WISEVIEW_ASSETS[name]={'data':data,'time':time.time()}
        return cached['data'],types[name]


def wiseview_frame(key):
    with FRAME_LOCK:
        entry = FRAMES.get(key)
    if not entry: raise ValueError('Frame expired')
    if WISEVIEW_HTML['text'] is None or time.time() - WISEVIEW_HTML['time'] > 3600:
        with urllib.request.urlopen('http://byw.tools/wiseview-v2', timeout=12) as response:
            WISEVIEW_HTML.update(text=response.read(1_000_000).decode('utf-8'), time=time.time())
    oid,ra,dec=entry[:3]
    neighbors=entry[3] if len(entry)>3 else []
    motion=entry[4] if len(entry)>4 else None
    kwargs={'moca_oid':oid,'ra_deg':ra,'dec_deg':dec}
    initial = web_survey_js(review.build_wiseview_ps1_fallback_cutout_js(**kwargs) + review.build_wiseview_des_supplement_cutouts_js(**kwargs)) + '\nwindow.SurveyEpochs.installNativePs1Label(document);'
    # This frame is sandboxed to an opaque origin. It receives no session token
    # or database credentials, even though the vendor scripts execute inside it.
    marker_data=json.dumps(neighbors, allow_nan=False).replace('<', '\\u003c')
    marker_script=(ROOT/'nearby_markers.js').read_text()
    crosshair_script=(ROOT/'target_crosshair.js').read_text()
    cutout_layout_script=(ROOT/'cutout_layout.js').read_text()
    target_data=json.dumps({'ra_deg':ra,'dec_deg':dec,'motion':motion},allow_nan=False)
    script = '<script>' + marker_script + '\nwindow.NearbyMarkers.install(' + marker_data + ');\n' + crosshair_script + '\nwindow.TargetCrosshair.install(' + target_data + ');</script>' + '<script>window.addEventListener("load",()=>{function install(){' + initial + '} setTimeout(install,600);setTimeout(install,2000);});window.addEventListener("message",e=>{if(e.source!==parent||!e.data||e.data.kind!=="resolved-surveys")return;const run=()=>{(new Function(e.data.script))()};setTimeout(run,100);setTimeout(run,6500);});</script>'
    html=WISEVIEW_HTML['text'].replace('<head>','<head><base href="./">',1)
    for name in ('flash3.js','flash3-theme.css'):
        html=html.replace('static/'+name,'wiseview-assets/'+name)
    return html.replace('</body>',script+'<script>'+cutout_layout_script+'</script></body>',1).encode()


def survey_script(key):
    with FRAME_LOCK: entry=FRAMES.get(key)
    if not entry: raise ValueError('Frame expired')
    oid,ra,dec=entry[:3]
    sources={review._source_key(s):s for s in review._iter_sia_sources((review.WISEVIEW_PS1_FALLBACK_CUTOUT_SOURCES,review.WISEVIEW_DES_SUPPLEMENT_SURVEY_ROWS))}
    def get(item):
        key,source=item
        try: return key,review.resolve_sia_preview_source(source,ra_deg=ra,dec_deg=dec,timeout=12)
        except Exception as exc: return key,{**source,'type':'pending_sia','message':'No image or survey service unavailable: '+str(exc)[:120]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        resolved={k:v for k,v in pool.map(get,sources.items())}
    kwargs={'moca_oid':oid,'ra_deg':ra,'dec_deg':dec,'resolved_sia_sources':resolved}
    return web_survey_js(review.build_wiseview_ps1_fallback_cutout_js(**kwargs)+review.build_wiseview_des_supplement_cutouts_js(**kwargs),final=True).encode()

MAX_BODY = 32_768

# Filter list mirrors review_wiseview_vetting.parse_args, and each value is
# passed to that parser rather than converted into SQL here.
BOOL_FILTERS = {'reclass','stacker','sublimeaperture','queue','souleymane','noclaim','claimed_only','nogaia','gaia_only','no_known','known','nophotoknown','photoknown','skip_missing_w2'}
VALUE_FLAGS = {
 'source_table':'--source-table','moca_oids':'--moca-oids','limit':'--limit','start_oid':'--start-oid','reviewer':'--reviewer',
 'nearpublicphotobd':'--nearpublicphotobd','nearpublicbd':'--nearpublicbd','nearphotobd':'--nearphotobd','nearbd':'--nearbd',
 'spiffviz':'--spiffviz','notspiffviz':'--notspiffviz','spiffstackerviz':'--spiffstackerviz','notspiffstackerviz':'--notspiffstackerviz',
 'sublimeapertureviz':'--sublimeapertureviz','notsublimeapertureviz':'--notsublimeapertureviz',
 'sublime2cnn':'--sublime2cnn','sublime2snr':'--sublime2snr','sublime2cnnprob':'--sublime2cnnprob','sublime2sptn':'--sublime2sptn',
 'min_w2':'--min-w2','max_w2':'--max-w2',
 'median_snr':'--median-snr','max_median_snr':'--max-median-snr','chi2_max':'--chi2','chi2_min':'--min-chi2',
 'min_abs_galactic_latitude':'--min-abs-gb','spectral_type_number_min':'--spectral-type-number-min','spectral_type_number_max':'--spectral-type-number-max'}
BOOL_FLAGS = {name: '--' + name.replace('_','-') for name in BOOL_FILTERS}
BOOL_FLAGS['no_known'] = '--noknown'
BOOL_FLAGS['claimed_only'] = '--claimed-only'
BOOL_FLAGS['gaia_only'] = '--gaia-only'
QUEUE_ORDERS = ('pm_sig_bins', 'spt_asc', 'spt_desc', 'oid_asc', 'oid_desc')
ANY_LANE_FILTERS = ('any_lane_include', 'any_lane_exclude')
PM_RANGE_FILTERS = ('min_total_pm', 'max_total_pm', 'min_pm_sigma', 'max_pm_sigma')
WEB_ONLY_FILTERS = {'queue_order', 'max_gaia_neighbors_30', 'exclude_spectrum_reviewed',
                    'duplicate_mode', 'byw_mode', 'use_spiffstacker_types', 'exclude_pm_sources', 'snr_wavelength_range', *ANY_LANE_FILTERS, *PM_RANGE_FILTERS}


def clean(obj):
    if dataclasses.is_dataclass(obj): return clean(dataclasses.asdict(obj))
    if isinstance(obj, dict): return {str(k): clean(v) for k,v in obj.items()}
    if isinstance(obj, (tuple,list)): return [clean(v) for v in obj]
    if isinstance(obj, Decimal): return float(obj)
    if isinstance(obj, float) and not math.isfinite(obj): return None
    if hasattr(obj, 'item'):
        try: return clean(obj.item())
        except (ValueError, TypeError): pass
    if hasattr(obj, 'isoformat'): return obj.isoformat()
    return obj


def parse_filters(filters):
    if not isinstance(filters, dict) or set(filters) - (BOOL_FILTERS | set(VALUE_FLAGS) | WEB_ONLY_FILTERS):
        raise ValueError('Unknown filter')
    argv = []
    for key, val in filters.items():
        if key in WEB_ONLY_FILTERS: continue
        if key in BOOL_FILTERS:
            if not isinstance(val, bool): raise ValueError(f'{key} must be true or false')
            if val: argv.append(BOOL_FLAGS[key])
        elif val is not None and str(val).strip():
            value = str(val).strip()
            if len(value) > 4096 or value.startswith('--'): raise ValueError(f'Invalid {key}')
            if key == 'source_table' and not value.startswith('pcat_'): raise ValueError('Source table must be a pcat_ table')
            argv.extend((VALUE_FLAGS[key], value))
    args = review.parse_args(argv)
    review.validate_args(args)
    args.snr_wavelength_range=filters.get('snr_wavelength_range','1-5')
    if not isinstance(args.snr_wavelength_range,str) or args.snr_wavelength_range not in SNR_WAVELENGTH_RANGES:
        raise ValueError('Choose a valid S/N wavelength range')
    if any(value is not None and not math.isfinite(value) for value in (args.median_snr,args.max_median_snr)):
        raise ValueError('S/N bounds must be finite numbers')
    value=filters.get('max_gaia_neighbors_30')
    if value is None or str(value).strip()=='': args.max_gaia_neighbors_30=None
    else:
        if isinstance(value,bool) or not str(value).strip().isdigit():raise ValueError('Maximum Gaia neighbors must be a non-negative whole number')
        args.max_gaia_neighbors_30=int(str(value).strip())
        if args.max_gaia_neighbors_30>1000000:raise ValueError('Maximum Gaia neighbors is too large')
    value=filters.get('exclude_spectrum_reviewed',True)
    if not isinstance(value,bool): raise ValueError('exclude_spectrum_reviewed must be true or false')
    args.exclude_spectrum_reviewed=value
    args.duplicate_mode=filters.get('duplicate_mode','ignore')
    if args.duplicate_mode not in ('ignore','only','either'): raise ValueError('Invalid duplicate filter')
    args.byw_mode=filters.get('byw_mode','ignore')
    if args.byw_mode not in ('ignore','only','either'): raise ValueError('Invalid BYW filter')
    value=filters.get('use_spiffstacker_types',False)
    if not isinstance(value,bool): raise ValueError('use_spiffstacker_types must be true or false')
    args.use_spiffstacker_types=value
    for key in ANY_LANE_FILTERS:
        value = filters.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > 4096):
            raise ValueError(f'Invalid {key.replace("_", " ")} classes')
        setattr(args, key, (value or '').strip() or None)
    for key in PM_RANGE_FILTERS:
        value=filters.get(key)
        if value is None or (isinstance(value,str) and not value.strip()):
            setattr(args,key,None)
            continue
        try:
            bound=float(value) if not isinstance(value,bool) else math.nan
        except (TypeError,ValueError,OverflowError):
            bound=math.nan
        if not math.isfinite(bound) or bound<0:
            label='PM sigma' if key.endswith('pm_sigma') else 'Total PM'
            raise ValueError(f'{label} bounds must be finite, non-negative numbers')
        setattr(args,key,bound)
    for lower,upper,label in ((args.min_total_pm,args.max_total_pm,'total PM'),
                              (args.min_pm_sigma,args.max_pm_sigma,'PM sigma')):
        if lower is not None and upper is not None and lower>upper:
            raise ValueError(f'Minimum {label} must be at most the maximum')
    value=filters.get('exclude_pm_sources', '')
    if not isinstance(value,str) or len(value)>4096:
        raise ValueError('Excluded PM sources must be a comma-separated list of strings')
    args.exclude_pm_sources=tuple(dict.fromkeys(token.strip().lower() for token in re.split(r'[,;\n]',value) if token.strip()))
    args.queue_order=filters.get('queue_order','pm_sig_bins')
    if not isinstance(args.queue_order,str) or args.queue_order not in QUEUE_ORDERS:
        raise ValueError('Choose a valid queue order')
    args.gaia_cache_missing=0
    return args


def filter_gaia_crowding(oids, maximum):
    """Require verified 30-arcsecond counts; unknown and stale never pass."""
    if not oids:return set(),0
    if not gaia_crowding.CACHE_PATH.is_file():return set(),len(oids)
    sqlite=gaia_crowding.open_readonly()
    db=None
    try:
        counts={}
        cached=gaia_crowding.completed_oids(sqlite,oids)
        if cached:
            db=review._connect_db()
            with db.cursor() as cur:
                for specs in gaia_crowding.fetch_current_specs(cur,cached):
                    counts.update(gaia_crowding.available_counts(sqlite,specs))
        return {oid for oid,count in counts.items() if count<=maximum},len(oids)-len(counts)
    finally:
        if db is not None:db.close()
        sqlite.close()


def redmover_oids(pack, requested=None, *, include_reviewed_ignored=False):
    """Selected active spectra, optionally including historical reviews in either lane."""
    if requested is not None and not requested: return set()
    conn = review._connect_db()
    try:
        with conn.cursor() as cur:
            found=set()
            chunks = review._chunked(sorted(requested), 1000) if requested is not None else [None]
            for chunk in chunks:
                restriction = ' AND sample.moca_oid IN (' + ','.join(['%s']*len(chunk)) + ')' if chunk is not None else ''
                cur.execute('''SELECT DISTINCT sample.moca_oid
                    FROM pcat_catwise2020_red_movers sample
                    JOIN moca_objects mo ON mo.moca_oid=sample.moca_oid AND mo.ignored=0
                    JOIN moca_spectra sp ON sp.moca_oid=sample.moca_oid
                    WHERE sp.moca_specpackid=%s AND sp.ignored=0''' + restriction, (pack, *(chunk or ())))
                found.update(int(row['moca_oid']) for row in cur.fetchall())
                if include_reviewed_ignored:
                    for spectral_lane,table in SPECTRAL_VETTING.items():
                        cur.execute(f'''SELECT DISTINCT sample.moca_oid
                            FROM `{table}` v
                            JOIN pcat_catwise2020_red_movers sample ON sample.moca_oid=v.moca_oid
                            JOIN moca_objects mo ON mo.moca_oid=sample.moca_oid AND mo.ignored=0
                            WHERE 1=1''' + restriction,tuple(chunk or ()))
                        found.update(int(row['moca_oid']) for row in cur.fetchall())
            return found
    finally: conn.close()


def exclude_spectral_reviews(oids):
    """Exclude both historical lanes, using a catalog join for large queues."""
    if not oids: return set()
    if len(oids) <= 20000:
        return review.fetch_missing_visual_vetting_oids(oids,visual_vetting_tables=tuple(SPECTRAL_VETTING.values()))
    conn=review._connect_db()
    try:
        reviewed=set()
        with conn.cursor() as cur:
            for table in SPECTRAL_VETTING.values():
                cur.execute(f'''SELECT DISTINCT v.moca_oid FROM `{table}` v
                    WHERE EXISTS (SELECT 1 FROM pcat_catwise2020_red_movers c WHERE c.moca_oid=v.moca_oid)''')
                reviewed.update(int(row['moca_oid']) for row in cur.fetchall() if row['moca_oid'] is not None)
        return oids-reviewed
    finally: conn.close()


def fetch_duplicate_oids():
    """Return the duplicate side of confirmed duplicate-vetting pairs."""
    conn=review._connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT potential_duplicated_moca_oid AS moca_oid FROM pcat_duplicated_vetting WHERE classification='y'")
            return {int(row['moca_oid']) for row in cur.fetchall() if row['moca_oid'] is not None}
    finally: conn.close()


def fetch_byw_oids():
    """Union the user's three BYW membership indicators by exact MOCAdb ID."""
    conn=review._connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute('''SELECT moca_oid FROM moca_objects
                WHERE origin=%s AND ignored=0
                UNION SELECT moca_oid FROM pcat_backyard_worlds WHERE moca_oid IS NOT NULL
                UNION SELECT moca_oid FROM pcat_backyard_worlds_early_Ls WHERE moca_oid IS NOT NULL''',
                ('db_add_sources.pro from backyard_worlds table',))
            return {int(row['moca_oid']) for row in cur.fetchall() if row['moca_oid'] is not None}
    finally: conn.close()


def filter_spiffstacker_type(oids, *, spt_min, spt_max):
    """Apply inclusive numeric bounds to non-ignored SPIFFStacker autotypes."""
    if not oids or (spt_min is None and spt_max is None): return set(oids)
    conn=review._connect_db()
    try:
        kept=set()
        with conn.cursor() as cur:
            for chunk in review._chunked(sorted(oids),1000):
                placeholders=','.join(['%s']*len(chunk))
                clauses=[f'moca_oid IN ({placeholders})',"calculation_method='spiff_stacker_autotype'",'ignored=0','spectral_type_number IS NOT NULL']
                values=list(chunk)
                if spt_min is not None:clauses.append('spectral_type_number >= %s');values.append(float(spt_min))
                if spt_max is not None:clauses.append('spectral_type_number <= %s');values.append(float(spt_max))
                cur.execute('SELECT moca_oid FROM data_spectral_types WHERE '+' AND '.join(clauses),tuple(values))
                kept.update(int(row['moca_oid']) for row in cur.fetchall() if row['moca_oid'] is not None)
        return kept
    finally:conn.close()


def filter_sublime_type(oids, *, spt_min, spt_max):
    """Filter by each object's latest SUBLIME2 row without regrouping it per chunk."""
    if not oids or (spt_min is None and spt_max is None): return set(oids)
    if len(oids) <= 1000:
        return review.filter_oids_by_sublime_autotype_sptn(oids,spt_min=spt_min,spt_max=spt_max)
    clauses=['psc.autotype_spectral_type_number IS NOT NULL']
    values=[]
    if spt_min is not None:clauses.append('psc.autotype_spectral_type_number >= %s');values.append(float(spt_min))
    if spt_max is not None:clauses.append('psc.autotype_spectral_type_number <= %s');values.append(float(spt_max))
    conn=review._connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute('''SELECT DISTINCT psc.moca_oid
                FROM pcat_sublime_candidates_v2 psc
                JOIN (SELECT moca_oid,MAX(id) AS id FROM pcat_sublime_candidates_v2
                      WHERE moca_oid IS NOT NULL GROUP BY moca_oid) latest ON latest.id=psc.id
                WHERE '''+' AND '.join(clauses),tuple(values))
            matched={int(row['moca_oid']) for row in cur.fetchall() if row['moca_oid'] is not None}
        return set(oids) & matched
    finally:conn.close()


def filter_total_proper_motion(oids, *, minimum=None, maximum=None, min_sigma=None, max_sigma=None):
    """Apply inclusive bounds to the same adopted motion displayed in the reviewer."""
    clauses=['adopted=1','ignored=0']
    values=[]
    if minimum is not None:
        clauses.append('pmtot_masyr >= %s');values.append(minimum)
    if maximum is not None:
        clauses.append('pmtot_masyr <= %s');values.append(maximum)
    if min_sigma is not None or max_sigma is not None:
        # A zero/missing/negative uncertainty cannot define a significance.
        clauses.extend(['pmtot_masyr IS NOT NULL','pmtot_masyr_unc > 0'])
        for bound,operator in ((min_sigma,'>='),(max_sigma,'<=')):
            if bound is not None:
                clauses.append(f'pmtot_masyr / NULLIF(pmtot_masyr_unc,0) {operator} %s')
                values.append(bound)
    kept=set()
    conn=review._connect_db()
    try:
        with conn.cursor() as cur:
            for chunk in review._chunked(sorted(oids),5000):
                placeholders=','.join(['%s']*len(chunk))
                cur.execute('SELECT moca_oid FROM data_proper_motions WHERE '+' AND '.join(clauses)
                            +f' AND moca_oid IN ({placeholders})',(*values,*chunk))
                kept.update(int(row['moca_oid']) for row in cur.fetchall())
    finally: conn.close()
    return kept


def exclude_proper_motion_sources(oids, sources):
    """Exclude adopted motions whose origin or publication contains a listed string."""
    matches = ["LOCATE(%s,LOWER(COALESCE(origin,''))) > 0 OR LOCATE(%s,LOWER(COALESCE(moca_pid,''))) > 0"
               for _ in sources]
    values = tuple(value for source in sources for value in (source, source))
    excluded = set()
    conn = review._connect_db()
    try:
        with conn.cursor() as cur:
            for chunk in review._chunked(sorted(oids), 5000):
                placeholders = ','.join(['%s'] * len(chunk))
                cur.execute('SELECT moca_oid FROM data_proper_motions WHERE adopted=1 AND ignored=0 AND ('
                            + ' OR '.join(matches) + ') AND moca_oid IN (' + placeholders + ')',
                            (*values, *chunk))
                excluded.update(int(row['moca_oid']) for row in cur.fetchall())
    finally:
        conn.close()
    return set(oids) - excluded


def public_ucd_oids(requested, *, spt_min=None, spt_max=None):
    """Select active public photometric M7+ candidates with reviewable sky positions."""
    if requested is not None and not requested:
        return set()
    clauses = ['d.public_adopted=1', 'd.photometric_estimate=1', 'd.ignored=0', 'd.spectral_type_number>=7']
    params = []
    if spt_min is not None:
        clauses.append('d.spectral_type_number >= %s')
        params.append(spt_min)
    if spt_max is not None:
        clauses.append('d.spectral_type_number <= %s')
        params.append(spt_max)
    if requested is not None:
        clauses.append('d.moca_oid IN (' + ','.join(['%s'] * len(requested)) + ')')
        params.extend(sorted(requested))
    conn = review._connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT DISTINCT d.moca_oid FROM {PUBLIC_UCD_SOURCE} d
                JOIN moca_objects mo ON mo.moca_oid=d.moca_oid AND mo.ignored=0
                JOIN data_equatorial_coordinates e ON e.moca_oid=d.moca_oid AND e.adopt_as_reference=1
                    AND e.ra IS NOT NULL AND e.`dec` IS NOT NULL
                WHERE """ + ' AND '.join(clauses), tuple(params))
            return {int(row['moca_oid']) for row in cur.fetchall()}
    finally:
        conn.close()


def filter_spectrum_snr(oids, *, snr_min, snr_max, moca_specpackid, wavelength_range):
    """Median flux/uncertainty in the chosen band of each latest active spectrum."""
    if not oids or (snr_min is None and snr_max is None):
        return set(oids)
    low,high=SNR_WAVELENGTH_RANGES[wavelength_range]
    bounds=[]; values=[]
    if snr_min is not None:
        bounds.append('median_snr >= %s'); values.append(snr_min)
    if snr_max is not None:
        bounds.append('median_snr <= %s'); values.append(snr_max)
    conn=review._connect_db()
    try:
        kept=set()
        with conn.cursor() as cur:
            for chunk in review._chunked(sorted(oids),1000):
                placeholders=','.join(['%s']*len(chunk))
                cur.execute(f"""WITH latest AS (
                    SELECT moca_oid,MAX(moca_specid) AS moca_specid FROM moca_spectra
                    WHERE moca_oid IN ({placeholders}) AND moca_specpackid=%s AND ignored=0
                    GROUP BY moca_oid
                ), samples AS (
                    SELECT s.moca_oid,d.flux_flambda/d.flux_flambda_unc AS snr,
                        ROW_NUMBER() OVER (PARTITION BY s.moca_oid ORDER BY d.flux_flambda/d.flux_flambda_unc) AS sample_rank,
                        COUNT(*) OVER (PARTITION BY s.moca_oid) AS sample_count
                    FROM latest s JOIN data_spectra d ON d.moca_specid=s.moca_specid
                    WHERE d.ignored=0 AND d.wavelength_angstrom BETWEEN %s AND %s
                        AND d.flux_flambda IS NOT NULL AND d.flux_flambda_unc>0
                ), medians AS (
                    SELECT moca_oid,AVG(snr) AS median_snr FROM samples
                    WHERE sample_rank IN (FLOOR((sample_count+1)/2),FLOOR((sample_count+2)/2))
                    GROUP BY moca_oid
                ) SELECT moca_oid FROM medians WHERE """+' AND '.join(bounds),
                    (*chunk,moca_specpackid,low*10000,high*10000,*values))
                kept.update(int(row['moca_oid']) for row in cur.fetchall())
        return kept
    finally:
        conn.close()


def optimized_queue(args, mode='sublime'):
    """Apply the desktop's intersecting filters early, before expensive known-BD queries."""
    aut = review._autotype_review()
    base = aut._parse_id_list(args.moca_oids)
    if mode == 'redmovers':
        if args.source_table != REDMOVER_SOURCE or args.sublimeaperture:
            raise ValueError('Red movers require the CatWISE sample and SPIFF or SPIFFStacker')
        if any((args.sublime2cnn, args.sublime2snr is not None, args.sublime2cnnprob is not None,
                args.sublime2sptn is not None,
                (not args.use_spiffstacker_types and (args.spectral_type_number_min is not None or
                                                      args.spectral_type_number_max is not None)))):
            raise ValueError('SUBLIME2 selection filters do not apply to red movers')
        oids = redmover_oids(SPECPACKS['spiffstacker' if args.stacker else 'spiff'], base)
    elif mode == 'public_ucd':
        oids = public_ucd_oids(base,
            spt_min=None if args.use_spiffstacker_types else args.spectral_type_number_min,
            spt_max=None if args.use_spiffstacker_types else args.spectral_type_number_max)
    elif mode == 'sublime':
        oids = set(base) if base is not None else review.fetch_source_oids(args.source_table)
    else: raise ValueError('Invalid review sample')
    if args.byw_mode != 'either' and oids:
        byw=fetch_byw_oids()
        oids = oids - byw if args.byw_mode == 'ignore' else oids & byw
    if args.duplicate_mode != 'either' and oids:
        duplicated=fetch_duplicate_oids()
        oids = oids - duplicated if args.duplicate_mode == 'ignore' else oids & duplicated
    if not args.reclass: oids -= review.fetch_existing_vetting_oids(args.table)
    if mode == 'redmovers' and args.exclude_spectrum_reviewed and oids:
        oids=exclude_spectral_reviews(oids)
    if args.queue: oids &= aut.fetch_queue_oids(stacker=bool(args.stacker), sublimeaperture=bool(args.sublimeaperture))
    if args.souleymane: oids &= aut.fetch_souleymane_oids()
    vetting = review.default_spiffviz_vetting_tables(stacker=bool(args.stacker), sublimeaperture=bool(args.sublimeaperture))
    all_vetting_tables = tuple(config[0] for config in spectral_vetting.LANES.values())
    for value, name, tables, exclude in (
        (args.any_lane_include,'Any lane include',all_vetting_tables,False),
        (args.any_lane_exclude,'Any lane exclude',all_vetting_tables,True),
        (args.spiffviz,'--spiffviz',vetting,False), (args.notspiffviz,'--notspiffviz',vetting,True),
        (args.spiffstackerviz,'--spiffstackerviz',(review.STACKER_VISUAL_VETTING_TABLE,),False),
        (args.notspiffstackerviz,'--notspiffstackerviz',(review.STACKER_VISUAL_VETTING_TABLE,),True),
        (args.sublimeapertureviz,'--sublimeapertureviz',(review.SUBLIMEAPERTURE_VISUAL_VETTING_TABLE,),False),
        (args.notsublimeapertureviz,'--notsublimeapertureviz',(review.SUBLIMEAPERTURE_VISUAL_VETTING_TABLE,),True)):
        classes=aut.parse_spiffviz_class_list(value,option_name=name)
        if classes and oids: oids=review.apply_visual_vetting_filter(oids,classes,exclude=exclude,option_name=name,visual_vetting_tables=tables)
    if not oids: return set()
    sublime_spt_min=args.sublime2sptn if mode == 'sublime' and not args.use_spiffstacker_types else None
    if mode == 'sublime' and (args.sublime2cnn or args.sublime2snr is not None or args.sublime2cnnprob is not None or sublime_spt_min is not None):
        oids &= aut.fetch_sublime2_oids(cnn_classes=aut.parse_spiffviz_class_list(args.sublime2cnn,option_name='--sublime2cnn'),snr_min=args.sublime2snr,cnnprob_min=args.sublime2cnnprob,sptn_min=sublime_spt_min)
    if args.use_spiffstacker_types:
        sublime_min=args.sublime2sptn if mode == 'sublime' else None
        minimums=[v for v in (sublime_min,args.spectral_type_number_min) if v is not None]
        oids=filter_spiffstacker_type(oids,spt_min=max(minimums) if minimums else None,spt_max=args.spectral_type_number_max)
    elif mode == 'sublime':
        oids=filter_sublime_type(oids,spt_min=args.spectral_type_number_min,spt_max=args.spectral_type_number_max)
    if args.skip_missing_w2 or args.min_w2 is not None or args.max_w2 is not None: oids=review.filter_oids_by_valid_w2mag(oids,min_w2=args.min_w2,max_w2=args.max_w2)
    if oids and any(getattr(args,key) is not None for key in PM_RANGE_FILTERS):
        oids=filter_total_proper_motion(oids,minimum=args.min_total_pm,maximum=args.max_total_pm,
                                      min_sigma=args.min_pm_sigma,max_sigma=args.max_pm_sigma)
    if oids and args.exclude_pm_sources:
        oids=exclude_proper_motion_sources(oids,args.exclude_pm_sources)
    oids=review.filter_oids_by_min_abs_galactic_latitude(oids,args.min_abs_galactic_latitude)
    if not oids: return set()
    if args.noclaim: oids -= aut.fetch_claimed_oids()
    if args.claimed_only: oids &= aut.fetch_claimed_oids()
    if args.nogaia: oids -= aut.fetch_gaia_catalog_oids(source_oids=oids)
    if args.gaia_only: oids &= aut.fetch_gaia_catalog_oids(source_oids=oids)
    # Scope lookups to the already-filtered list when it saves round trips.
    scope=oids if len(oids) <= 20000 else None
    if args.known: oids &= aut.fetch_known_nonphotometric_late_type_oids(source_oids=scope)
    if args.no_known: oids -= aut.fetch_known_nonphotometric_late_type_oids(source_oids=scope)
    if args.photoknown: oids &= aut.fetch_known_photometric_late_type_oids(source_oids=scope)
    if args.nophotoknown: oids -= aut.fetch_known_photometric_late_type_oids(source_oids=scope)
    for spec,radius in review.iter_nearby_bd_filter_args(args):
        if not oids: break
        oids &= review.fetch_sublime_oids_for_nearby_bd_filter(spec,radius_arcsec=radius,source_oids=oids)
    if oids and (args.median_snr is not None or args.max_median_snr is not None):
        oids = filter_spectrum_snr(oids,snr_min=args.median_snr,snr_max=args.max_median_snr,
            moca_specpackid=aut._review_reduced_specpackid(stacker=bool(args.stacker),sublimeaperture=bool(args.sublimeaperture)),
            wavelength_range=args.snr_wavelength_range)
    if oids and (args.chi2_min is not None or args.chi2_max is not None):
        oids &= aut.fetch_autotype_chi2_oids(chi2_max=float(args.chi2_max) if args.chi2_max is not None else None,chi2_min=float(args.chi2_min) if args.chi2_min is not None else None,stacker=bool(args.stacker),sublimeaperture=bool(args.sublimeaperture))
    if oids and getattr(args,'max_gaia_neighbors_30',None) is not None:
        oids,args.gaia_cache_missing=filter_gaia_crowding(oids,args.max_gaia_neighbors_30)
    return oids


def pm_significance_band(value):
    if value is None or not math.isfinite(value):return 3
    if value>10:return 0
    if value>=5:return 1
    if value>=1:return 2
    return 3


def galactic_latitude_band(value):
    if value is None or not math.isfinite(value) or abs(value)>90:return 3
    if abs(value)>15:return 0
    if abs(value)>10:return 1
    return 2


def order_review_oids(oids, order='pm_sig_bins'):
    """Default: latitude band, PM significance band, adopted subtype, significance."""
    if order not in QUEUE_ORDERS:
        raise ValueError('Choose a valid queue order')
    ids=sorted(set(oids))
    if not ids or order=='oid_asc':return ids
    if order=='oid_desc':return ids[::-1]
    types={};significances={};latitude_bands={}
    conn=review._connect_db()
    try:
        with conn.cursor() as cur:
            for chunk in review._chunked(ids,5000):
                placeholders=','.join(['%s']*len(chunk))
                cur.execute('SELECT moca_oid,spectral_type_number FROM data_spectral_types '
                            'WHERE adopted=1 AND ignored=0 AND moca_oid IN ('+placeholders+') ORDER BY id DESC',tuple(chunk))
                for row in cur.fetchall():
                    try:value=float(row['spectral_type_number'])
                    except (TypeError,ValueError,OverflowError):continue
                    if math.isfinite(value):types.setdefault(int(row['moca_oid']),value)
                cur.execute('SELECT moca_oid,pmtot_masyr,pmtot_masyr_unc FROM data_proper_motions '
                            'WHERE adopted=1 AND ignored=0 AND pmtot_masyr IS NOT NULL AND pmtot_masyr_unc>0 '
                            'AND moca_oid IN ('+placeholders+') ORDER BY id DESC',tuple(chunk))
                for row in cur.fetchall():
                    try:value,error=float(row['pmtot_masyr']),float(row['pmtot_masyr_unc'])
                    except (TypeError,ValueError,OverflowError):continue
                    if not (math.isfinite(value) and value>=0 and math.isfinite(error) and error>0):continue
                    significance=value/error
                    if math.isfinite(significance):significances.setdefault(int(row['moca_oid']),significance)
                if order=='pm_sig_bins':
                    cur.execute('SELECT moca_oid,gb FROM calc_galactic_coordinates '
                                'WHERE adopt_as_reference=1 AND gb BETWEEN -90 AND 90 '
                                'AND moca_oid IN ('+placeholders+')',tuple(chunk))
                    for row in cur.fetchall():
                        try:band=galactic_latitude_band(float(row['gb']))
                        except (TypeError,ValueError,OverflowError):continue
                        oid=int(row['moca_oid'])
                        latitude_bands[oid]=min(latitude_bands.get(oid,3),band)
    finally:conn.close()
    if order=='pm_sig_bins':
        return sorted(ids,key=lambda oid:(latitude_bands.get(oid,3),pm_significance_band(significances.get(oid)),
            oid not in types,types.get(oid,0),oid not in significances,-significances.get(oid,0),oid))
    direction=-1 if order=='spt_desc' else 1
    return sorted(ids,key=lambda oid:(oid not in types,direction*types.get(oid,0),
                                      oid not in significances,-significances.get(oid,0),oid))


def queue_worker(session, filters, mode='sublime'):
    try:
        args = parse_filters(filters)
        if mode == 'public_ucd':
            args.source_table = PUBLIC_UCD_SOURCE
        oids = order_review_oids(optimized_queue(args, mode),args.queue_order)
        if args.limit is not None: oids = oids[:args.limit]
        start = oids.index(args.start_oid) if args.start_oid in oids else 0
        with session['lock']:
            session.update(args=args, mode=mode, oids=oids, start=start, state='ready', error='', object_cache={}, fit_cache={}, snapshots={}, spectral_snapshots={}, cutout_snapshots={}, undo=[])
    except Exception as exc:
        with session['lock']: session.update(state='error', error=str(exc))


def nearby_spectroscopic_l_dwarfs(cur, oid, ra, dec):
    """Nearby active objects with a literature/visual, non-photometric L0+ type."""
    blocks=[]; params=[]
    for rectangle in review._coord_query_rectangles(float(ra),float(dec),NEARBY_UCD_RADIUS_ARCSEC):
        blocks.append('''SELECT mo.moca_oid,mo.designation,
            CASE WHEN de.ra IS NOT NULL AND de.`dec` IS NOT NULL THEN de.ra ELSE mo.ra END AS ra_deg,
            CASE WHEN de.ra IS NOT NULL AND de.`dec` IS NOT NULL THEN de.`dec` ELSE mo.`dec` END AS dec_deg,
            CASE WHEN de.ra IS NOT NULL AND de.`dec` IS NOT NULL THEN de.measurement_epoch_yr END AS position_epoch_yr,
            angular_distance(%s,%s,mo.ra,mo.`dec`) AS separation_arcsec,
            s.spectral_type,s.spectral_type_number,s.moca_pid,s.origin,
            EXISTS(SELECT 1 FROM pcat_byw_mar9_2026 b WHERE b.moca_oid=mo.moca_oid)
              OR EXISTS(SELECT 1 FROM pcat_backyard_worlds b WHERE b.moca_oid=mo.moca_oid) AS in_byw
            FROM moca_objects mo
            LEFT JOIN data_equatorial_coordinates de ON de.moca_oid=mo.moca_oid AND de.adopt_as_reference=1
            JOIN data_spectral_types s ON s.id=(SELECT d.id FROM data_spectral_types d
                WHERE d.moca_oid=mo.moca_oid AND d.ignored=0 AND d.photometric_estimate=0
                  AND d.spectral_type_number>=10 AND d.spectral_type IS NOT NULL
                  AND d.calculation_method IS NULL
                ORDER BY d.adopted DESC,d.public_adopted DESC,d.id DESC LIMIT 1)
            WHERE mo.ignored=0 AND mo.moca_oid<>%s AND mo.ra IS NOT NULL AND mo.`dec` IS NOT NULL
              AND mo.spatial_coord IS NOT NULL AND MBRIntersects(mo.spatial_coord,ST_GeomFromText(%s,4326))
              AND angular_distance(%s,%s,mo.ra,mo.`dec`)<=%s''')
        params.extend((float(ra)%360.0,float(dec),int(oid),review._spatial_rectangle_wkt(*rectangle),float(ra)%360.0,float(dec),NEARBY_UCD_RADIUS_ARCSEC))
    cur.execute(' UNION '.join(blocks)+' ORDER BY moca_oid',tuple(params))
    return list(cur.fetchall())


def nearby_ucd_candidates_and_claims(cur, oid, ra, dec):
    """Find active neighbors with an adopted UCD estimate or a claim-list entry."""
    blocks, params = [], []
    ra, dec = float(ra) % 360, float(dec)
    for rectangle in review._coord_query_rectangles(ra, dec, NEARBY_UCD_RADIUS_ARCSEC):
        blocks.append('''SELECT mo.moca_oid,mo.designation,
                   CASE WHEN de.ra IS NOT NULL AND de.`dec` IS NOT NULL THEN de.ra ELSE mo.ra END AS ra_deg,
                   CASE WHEN de.ra IS NOT NULL AND de.`dec` IS NOT NULL THEN de.`dec` ELSE mo.`dec` END AS dec_deg,
                   CASE WHEN de.ra IS NOT NULL AND de.`dec` IS NOT NULL THEN de.measurement_epoch_yr END AS position_epoch_yr,
                   angular_distance(%s,%s,mo.ra,mo.`dec`) AS separation_arcsec
            FROM moca_objects mo
            LEFT JOIN data_equatorial_coordinates de
                ON de.moca_oid=mo.moca_oid AND de.adopt_as_reference=1 AND de.ignored=0
            WHERE mo.ignored=0 AND mo.moca_oid<>%s AND mo.spatial_coord IS NOT NULL
              AND MBRIntersects(mo.spatial_coord,ST_GeomFromText(%s,4326))
            HAVING separation_arcsec<=%s''')
        params.extend((ra, dec, int(oid), review._spatial_rectangle_wkt(*rectangle), NEARBY_UCD_RADIUS_ARCSEC))
    claim_tokens = review._autotype_review().NOCLAIM_DISC_TOKENS
    byw_disc = ' OR '.join('LOWER(b.disc) LIKE %s' for _ in claim_tokens)
    params.extend(f'%{token}%' for token in claim_tokens)
    cur.execute('WITH neighbors AS (' + ' UNION '.join(blocks) + f'''), alerts AS (
        SELECT n.*,s.spectral_type,
            EXISTS(SELECT 1 FROM pcat_duplicated_vetting dup
                   WHERE dup.potential_duplicated_moca_oid=n.moca_oid AND dup.classification='y') AS already_duplicate,
            ((s.spectral_type_number>=7 AND (s.photometric_estimate=1 OR s.calculation_method IS NOT NULL))
              OR EXISTS(SELECT 1 FROM pcat_zerj25_euclid_q1_ucd_candidates e WHERE e.moca_oid=n.moca_oid)) AS ucd_candidate,
            EXISTS(SELECT 1 FROM pcat_kirkpatrick_yadu_2026_claim y WHERE y.moca_oid=n.moca_oid) AS yadu,
            (EXISTS(SELECT 1 FROM pcat_schneider_claim_list_byw b WHERE b.moca_oid=n.moca_oid)
              OR EXISTS(SELECT 1 FROM pcat_byw_mar9_2026 b WHERE b.moca_oid=n.moca_oid AND ({byw_disc}))) AS byw,
            EXISTS(SELECT 1 FROM pcat_azul_byw_sample_jul16_2026 a WHERE a.moca_oid=n.moca_oid) AS azul,
            EXISTS(SELECT 1 FROM mechanics_all_designations d
                   WHERE d.moca_oid=n.moca_oid AND d.designation LIKE 'SMDET%%') AS smdet
        FROM neighbors n
        LEFT JOIN data_spectral_types s ON s.moca_oid=n.moca_oid AND s.adopted=1 AND s.ignored=0
    ) SELECT * FROM alerts WHERE ucd_candidate OR yadu OR byw OR azul OR smdet
      ORDER BY separation_arcsec,moca_oid''', tuple(params))
    return list(cur.fetchall())


def nearby_marker_items(obj):
    """Show every listed neighbor once, using its measured reference position."""
    neighbors = [*getattr(obj, 'nearby_ucd_candidates_and_claims', []),
                 *getattr(obj, 'nearby_spectroscopic_l_dwarfs', [])]
    by_oid = {int(row['moca_oid']): row for row in neighbors}
    return list(by_oid.values())


def duplicate_primary(spectroscopic, alerts):
    if spectroscopic:
        return min(spectroscopic, key=lambda row: int(row['moca_oid']))
    # Alerts are ordered by angular separation, then object ID.
    return next((row for row in alerts if row.get('ucd_candidate') and not row.get('already_duplicate')), None)


def heading_spectral_types(rows):
    """Prefer the public-adopted type, expanding an adopted SPHEREx estimate."""
    available = []
    for row in rows:
        label = str(row.get('spectral_type') or row.get('complete_spectral_type') or '').strip()
        number = row.get('spectral_type_number')
        if not label and number is not None and math.isfinite(float(number)):
            label = review._spectral_type_number_to_text(float(number))
        if label:
            available.append({**row, 'spectral_type': label})
    primary = next((row for row in available if row['public_adopted']), None)
    if primary is None:
        primary = next((row for row in available if row['adopted']), None)
    if primary is None:
        return []
    if primary['public_adopted'] or 'spherex' not in str(primary.get('origin') or '').lower():
        return [primary]
    return [primary, *(row for row in available if row['id'] != primary['id'] and not row['ignored'])]


def adopted_coordinates(cur, oid):
    """Provenance of the active MOCAdb reference coordinate, independent of PM."""
    cur.execute("""SELECT id,ra AS ra_deg,`dec` AS dec_deg,measurement_epoch_yr,
                          moca_pid,origin,mission_name,data_release
                   FROM data_equatorial_coordinates
                   WHERE moca_oid=%s AND adopt_as_reference=1 AND ignored=0""",(oid,))
    return cur.fetchone() or {}


def get_object(session, index):
    with session['lock']:
        if session['state'] != 'ready': raise ValueError('Load a queue first')
        if index < 0 or index >= len(session['oids']): raise ValueError('Object index outside queue')
        oid = session['oids'][index]
        existing = session['object_cache'].get(oid)
    if existing is None:
        rows = review.fetch_review_objects([oid], table=review.WISEVIEW_VETTING_TABLE)
        if not rows: raise ValueError(f'Object {oid} no longer available')
        existing = rows[0]
        conn = review._connect_db()
        try:
            with conn.cursor() as cur:
                existing_snapshot = snapshot(cur,oid,lock=False)
                existing.spectral_vetting=clean(spectral_vetting.rows_for_object(cur,oid))
                cur.execute("""SELECT id,spectral_type,complete_spectral_type,spectral_type_number,
                                      moca_pid,origin,calculation_method,photometric_estimate,is_public,
                                      public_adopted,adopted,ignored
                               FROM data_spectral_types WHERE moca_oid=%s
                               ORDER BY public_adopted DESC,adopted DESC,id DESC""",(oid,))
                type_rows=list(cur.fetchall())
                type_details=next((row for row in type_rows if row['adopted']), {})
                existing.heading_spectral_types=clean(heading_spectral_types(type_rows))
                cur.execute('''SELECT p.pmtot_masyr,p.pmtot_masyr_unc,p.pmra_masyr,p.pmdec_masyr,p.moca_pid,p.mission_name,
                                      e.ra AS reference_ra_deg,e.`dec` AS reference_dec_deg,e.measurement_epoch_yr AS reference_epoch_yr
                               FROM data_proper_motions p LEFT JOIN data_equatorial_coordinates e
                                 ON e.moca_oid=p.moca_oid AND e.adopt_as_reference=1 AND e.ignored=0
                               WHERE p.moca_oid=%s AND p.adopted=1 AND p.ignored=0''',(oid,))
                existing.adopted_pm=clean(cur.fetchone() or {})
                existing.adopted_coordinates=clean(adopted_coordinates(cur,oid))
                cur.execute('SELECT source_id FROM cat_gaiadr3 WHERE moca_oid=%s AND source_id IS NOT NULL',(oid,))
                existing.gaia_match_ids=[str(row['source_id']) for row in cur.fetchall()]
                existing.nearby_spectroscopic_l_dwarfs=clean(nearby_spectroscopic_l_dwarfs(cur,oid,existing.ra_deg,existing.dec_deg))
                existing.nearby_ucd_candidates_and_claims=clean(nearby_ucd_candidates_and_claims(cur,oid,existing.ra_deg,existing.dec_deg))
            existing.adopted_type_details = clean(type_details)
        finally: conn.close()
        with session['lock']:
            session['object_cache'][oid] = existing
            while len(session['object_cache']) > 64:
                session['object_cache'].pop(next(iter(session['object_cache'])))
            session.setdefault('snapshots',{})[oid] = existing_snapshot
            session.setdefault('spectral_snapshots',{})[oid] = existing.spectral_vetting
    return oid, existing


def fetch_templates(cur):
    with TEMPLATE_LOCK:
        if TEMPLATE_CACHE['rows'] is not None and time.time() - TEMPLATE_CACHE['time'] < 1800:
            return TEMPLATE_CACHE['rows']
        cur.execute('''SELECT t.moca_spherex_template_id,t.spectral_type,t.spectral_type_number,t.grid_type,
            dt.wavelength_angstrom,dt.flux_flambda FROM moca_spherex_templates t
            JOIN data_spherex_templates dt ON dt.moca_spherex_template_id=t.moca_spherex_template_id
            WHERE t.ignored=0 AND dt.ignored=0 AND dt.flux_flambda>0 AND dt.wavelength_angstrom IS NOT NULL
            AND t.spectral_type IS NOT NULL AND t.spectral_type_number IS NOT NULL
            ORDER BY t.moca_spherex_template_id,dt.wavelength_angstrom LIMIT 200001''')
        rows = list(cur.fetchall())
        if len(rows) > 200000: raise ValueError('Template grid exceeds interactive limit')
        TEMPLATE_CACHE.update(rows=rows, time=time.time())
        return rows


def spectrum_data(session, oid, lane):
    pack = SPECPACKS.get(lane)
    if pack is None: raise ValueError('Invalid spectrum lane')
    with session['lock']:
        cached = session['fit_cache'].get((oid, pack))
    if cached is not None: return cached
    conn = review._connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute('''SELECT moca_specid,median_snr_per_pix FROM moca_spectra
               WHERE moca_oid=%s AND moca_specpackid=%s AND ignored=0 ORDER BY moca_specid DESC LIMIT 1''', (oid,pack))
            meta = cur.fetchone()
            if not meta: return {'missing': True, 'lane': lane}
            cur.execute('''SELECT id AS data_spectra_id,wavelength_angstrom,flux_flambda,flux_flambda_unc,ignored
               FROM data_spectra WHERE moca_specid=%s ORDER BY wavelength_angstrom,id LIMIT 10001''', (meta['moca_specid'],))
            rows = list(cur.fetchall())
            if len(rows)>10000: raise ValueError('Spectrum exceeds interactive limit')
            templates = fetch_templates(cur)
            try: fit, warning = core.fit_spectrum(rows, templates), None
            except ValueError as exc: fit, warning = None, str(exc)
            if fit:
                fit['overlays'] = fit['overlays'][:1]
                fit['matches'] = fit['matches'][:1]
            result = clean({'lane':lane,'specid':meta['moca_specid'],'fit':fit,'raw_spectrum':rows,'warning':warning})
    finally: conn.close()
    with session['lock']:
        session['fit_cache'][(oid,pack)] = result
        while len(session['fit_cache']) > 32:
            session['fit_cache'].pop(next(iter(session['fit_cache'])))
    return result


def cutout_position(source_key):
    """The plotted cutout center is encoded in its tile:RA:Dec source key."""
    parts=str(source_key).split(':')
    if len(parts)!=3:return None
    try:ra,dec=map(float,parts[1:])
    except (ValueError,TypeError):return None
    if not math.isfinite(ra) or not math.isfinite(dec) or not 0<=ra<360 or not -90<=dec<=90:return None
    return {'ra_deg':ra,'dec_deg':dec}


def cutout_data(oid):
    conn = review._connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute('''SELECT source_key,epoch_yr,min_epoch,max_epoch,'SUBLIME2' AS sample
                           FROM pcat_sublime_candidates_v2 WHERE moca_oid=%s AND source_key IS NOT NULL
                           UNION ALL SELECT source_key,epoch_yr,min_epoch,max_epoch,'SUBLIME1' AS sample
                           FROM pcat_sublime_candidates WHERE moca_oid=%s AND source_key IS NOT NULL''', (oid,oid))
            epochs_by_key = {}
            for row in cur.fetchall():
                key = row['source_key']
                epochs_by_key.setdefault(key, []).append({name:clean(row.get(name))
                    for name in ('sample','epoch_yr','min_epoch','max_epoch')})
            vetting_rows=clean(cutout_vetting.rows_for_object(cur,oid))
            per_path_ready=cutout_vetting.per_path_ready(cur)
    finally: conn.close()
    images = [];seen_paths=set()
    for key, epochs in epochs_by_key.items():
        try:
            path = review._autotype_review().sublime_cutout_path_from_source_key(key)
            canonical=cutout_vetting.canonical_path(path)
            if canonical in seen_paths:continue
            if not path.is_file() and not path.with_name(path.name+'.bz2').is_file(): continue
            data = read_cutout_bytes(path)
            if len(data)>20_000_000 or not data.startswith(b'\x89PNG\r\n\x1a\n'): continue
            source_tables=list(dict.fromkeys('pcat_sublime_candidates_v2' if row['sample']=='SUBLIME2' else 'pcat_sublime_candidates' for row in epochs))
            saved=cutout_vetting.selected_rows(vetting_rows,[canonical])[canonical]
            images.append({'source_key':key,'epochs':epochs,'cutout_path':canonical,'source_tables':source_tables,
                'position':cutout_position(key),'vetting':saved,'data':'data:image/png;base64,'+base64.b64encode(data).decode('ascii')})
            seen_paths.add(canonical)
        except (OSError,ValueError,EOFError): continue
    return {'images': images,'vetting_rows':vetting_rows,'per_path_ready':per_path_ready}


def snapshot(cur, oid, *, lock=True):
    cur.execute('''SELECT classification,classification_integer,comments,reviewer,ra_deg,dec_deg,wiseview_url,source_table,origin
                   FROM pcat_wiseview_visual_vetting WHERE moca_oid=%s''' + (' FOR UPDATE' if lock else ''),(oid,))
    return clean(cur.fetchone())


def save_decision(session, index, key, comments, spectral_classification=None, spectral_lane=None, spectral_specid=None,
                  cutout_key=None,cutout_paths=None,spectral_reviews=None):
    oid, obj = get_object(session,index)
    if session.get('mode') == 'redmovers' and key == 'm':
        raise ValueError('Mis-centered SPHEREx classification is unavailable for red movers')
    spec = next((s for s in WEB_CLASSIFICATION_SPECS if s.key == key),None)
    if spec is None or len(comments)>4000: raise ValueError('Invalid classification or comments')
    if spectral_reviews is None:
        spectral_reviews=[] if spectral_classification is None else [{
            'classification':spectral_classification,'lane':spectral_lane,'specid':spectral_specid}]
    elif spectral_classification is not None:
        raise ValueError('Use either legacy or multiple spectral choices')
    if not isinstance(spectral_reviews,list) or len(spectral_reviews)>3:
        raise ValueError('Provide at most three spectral choices')
    allowed={item[0] for item in review._autotype_review().BUTTON_SPECS} if spectral_reviews else set()
    seen=set()
    for choice in spectral_reviews:
        if (not isinstance(choice,dict) or set(choice)!={'lane','classification','specid'} or
                not isinstance(choice['lane'],str) or choice['lane'] not in spectral_vetting.LANES or
                not isinstance(choice['classification'],str) or choice['classification'] not in allowed or
                choice['lane'] in seen):raise ValueError('Invalid spectral classification or lane')
        if isinstance(choice['specid'],bool) or not isinstance(choice['specid'],int) or choice['specid']<1:
            raise ValueError('A loaded spectrum is required for spectral classification')
        seen.add(choice['lane'])
    args = session['args']
    spectral_changes=[];cutout_change=None;cutout_context=None
    if cutout_key is not None:
        cutout_spec=next((s for s in cutout_vetting.CLASSIFICATION_SPECS if s.key==cutout_key),None)
        if not cutout_spec or session.get('mode')=='redmovers':raise ValueError('Invalid cutout classification for this sample')
        if not isinstance(cutout_paths,list) or not cutout_paths or len(cutout_paths)>128 or any(
                not isinstance(path,str) or len(path)>4096 for path in cutout_paths):
            raise ValueError('Loaded cutout paths are required')
        with session['lock']:cutout_context=session.get('cutout_snapshots',{}).get(oid)
        if not cutout_context or set(cutout_paths)!={image['cutout_path'] for image in cutout_context['images']}:
            raise ValueError('Displayed cutouts changed; reload the target before saving')
        cutout_paths=sorted(set(cutout_paths))
    conn = review._connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT moca_oid FROM moca_objects WHERE moca_oid=%s AND ignored=0 FOR UPDATE',(oid,))
            if not cur.fetchone(): raise ValueError('Object is no longer active')
            before = snapshot(cur,oid)
            with session['lock']:
                expected = session.setdefault('snapshots',{}).get(oid, '__missing__')
            if expected != '__missing__' and before != expected: raise ValueError('Classification changed since it was displayed; reload the queue')
            if expected == '__missing__' and before is not None and not args.reclass:
                raise ValueError('Object was already classified; reload or enable reclassification')
            for choice in spectral_reviews:
                lane=choice['lane']
                spectral_before=clean(spectral_vetting.snapshot(cur,oid,lane))
                with session['lock']:
                    expected_spectral=session.get('spectral_snapshots',{}).get(oid,{}).get(lane,'__missing__')
                if expected_spectral=='__missing__' or spectral_before['vetting']!=expected_spectral:
                    raise ValueError('Spectral review changed; reload the object before saving classifications')
                spectral_changes.append({'lane':lane,'before':spectral_before,'choice':choice})
            for change in spectral_changes:
                choice=change['choice'];lane=change['lane']
                change['nrows']=spectral_vetting.apply(cur,oid,lane,choice['classification'],choice['specid'],args.reviewer,change['before'])
                change['after']=clean(spectral_vetting.snapshot(cur,oid,lane))
            if cutout_context:
                cutout_before=clean(cutout_vetting.selected_rows(cutout_vetting.rows_for_object(cur,oid,lock=True),cutout_paths))
                expected_cutouts=cutout_vetting.selected_rows(cutout_context['rows'],cutout_paths)
                if cutout_before!=expected_cutouts:raise ValueError('Cutout review changed; reload the target before saving')
                cutout_vetting.apply(cur,oid,cutout_spec,cutout_context['images'],obj,args,comments)
                cutout_change={'before':cutout_before,'paths':cutout_paths,
                    'after':clean(cutout_vetting.selected_rows(cutout_vetting.rows_for_object(cur,oid,lock=True),cutout_paths))}
            values = (oid,spec.classification,spec.classification_integer,comments.strip() or None,args.reviewer or None,
                      obj.ra_deg,obj.dec_deg,build_wiseview_url(ra_deg=obj.ra_deg,dec_deg=obj.dec_deg),args.source_table,'wiseview_web/server.py')
            cur.execute('''INSERT INTO pcat_wiseview_visual_vetting
                (moca_oid,classification,classification_integer,comments,reviewer,ra_deg,dec_deg,wiseview_url,source_table,origin)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE
                classification=VALUES(classification),classification_integer=VALUES(classification_integer),comments=VALUES(comments),
                reviewer=VALUES(reviewer),ra_deg=VALUES(ra_deg),dec_deg=VALUES(dec_deg),wiseview_url=VALUES(wiseview_url),
                source_table=VALUES(source_table),origin=VALUES(origin)''',values)
            after = snapshot(cur,oid)
            cur.execute('''INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls)
                VALUES (%s,%s,1,%s,0,'gagne')''',(current_auth()['user'],'pcat_wiseview_visual_vetting',f'wiseview_web/server.py: review moca_oid={oid}'))
            for change in spectral_changes:
                cur.execute('''INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls)
                    VALUES (%s,%s,%s,%s,0,'gagne')''',(current_auth()['user'],
                    spectral_vetting.LANES[change['lane']][0]+',data_spectral_types,moca_spectra',change['nrows'],
                    f"wiseview_web/server.py: paired spectral review moca_oid={oid}; lane={change['lane']}; classification={change['choice']['classification']}"))
            if cutout_change:
                cur.execute('''INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls)
                    VALUES (%s,%s,%s,%s,0,'gagne')''',(current_auth()['user'],cutout_vetting.TABLE,len(cutout_paths),
                    f'wiseview_web/server.py: paired cutout review moca_oid={oid}; classification={cutout_spec.classification}'))
        undo_item={'oid':oid,'before':before,'after':after,'index':index,
            'spectral_reviews':spectral_changes,'spectral':spectral_changes[0] if len(spectral_changes)==1 else None,'cutout':cutout_change}
        if session.get('validate_undo'):session['validate_undo'](undo_item)
        conn.commit()
        invalidate_sublime_stats()
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
    with session['lock']:
        session.setdefault('snapshots',{})[oid]=after
        session['undo'].append({'oid':oid,'before':before,'after':after,'index':index,
            'spectral_reviews':spectral_changes,'spectral':spectral_changes[0] if len(spectral_changes)==1 else None,'cutout':cutout_change})
        for change in spectral_changes:
            session.setdefault('spectral_snapshots',{}).setdefault(oid,{})[change['lane']]=change['after']['vetting']
            session['fit_cache'].pop((oid,SPECPACKS[change['lane']]),None)
        session['object_cache'].pop(oid,None)
        session.get('cutout_snapshots',{}).pop(oid,None)
    return {'saved':spec.classification,'oid':oid,
            'spectral_saved':spectral_reviews[0]['classification'] if len(spectral_reviews)==1 else None,
            'spectral_lane':spectral_reviews[0]['lane'] if len(spectral_reviews)==1 else None,
            'spectral_saved_reviews':spectral_reviews,
            'cutouts_saved':len(cutout_change['paths']) if cutout_change else 0}


def duplicate_snapshot(cur, primary_oid, duplicate_oid, *, lock=True):
    cur.execute('''SELECT moca_oid,potential_duplicated_moca_oid,classification,applied,
        original_designation,potential_duplicated_designation,original_spectral_type,
        potential_duplicated_spectral_type,comments,created_timestamp,modified_timestamp
        FROM pcat_duplicated_vetting WHERE moca_oid=%s AND potential_duplicated_moca_oid=%s''' +
        (' FOR UPDATE' if lock else ''),(primary_oid,duplicate_oid))
    return clean(cur.fetchone())


def visible_nearby(rows, include_sublime):
    """Use only moca_objects.designation; SUBLIME aliases do not hide a neighbor."""
    if not isinstance(include_sublime,bool):raise ValueError('Invalid nearby SUBLIME option')
    return [row for row in rows if include_sublime or not str(row.get('designation') or '').upper().startswith('SUBLIME')]


def save_duplicate(session,index,comments,primary_oid=None,*,include_sublime_neighbors=True):
    oid,obj=get_object(session,index)
    if len(comments)>4000: raise ValueError('Comments are too long')
    shown=duplicate_primary(visible_nearby(getattr(obj,'nearby_spectroscopic_l_dwarfs',[]),include_sublime_neighbors),
                            visible_nearby(getattr(obj,'nearby_ucd_candidates_and_claims',[]),include_sublime_neighbors))
    if not shown: raise ValueError('No nearby eligible spectroscopic L0+ object or UCD candidate')
    expected=int(shown['moca_oid'])
    if primary_oid is not None and primary_oid!=expected:
        raise ValueError('The displayed duplicate target changed; reload the target before declaring a duplicate')
    conn=review._connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute('''SELECT mo.moca_oid,de.ra,de.`dec` FROM moca_objects mo
                JOIN data_equatorial_coordinates de ON de.moca_oid=mo.moca_oid AND de.adopt_as_reference=1
                WHERE mo.moca_oid=%s AND mo.ignored=0 FOR UPDATE''',(oid,))
            target=cur.fetchone()
            if not target or target['ra'] is None or target['dec'] is None:
                raise ValueError('Target reference coordinates are unavailable; reload the queue')
            if abs(float(target['ra'])-float(obj.ra_deg))>1e-9 or abs(float(target['dec'])-float(obj.dec_deg))>1e-9:
                raise ValueError('Target reference coordinates changed; reload the queue')
            candidates=visible_nearby(nearby_spectroscopic_l_dwarfs(cur,oid,target['ra'],target['dec']),include_sublime_neighbors)
            alerts=[] if candidates else visible_nearby(nearby_ucd_candidates_and_claims(cur,oid,target['ra'],target['dec']),include_sublime_neighbors)
            primary=duplicate_primary(candidates,alerts)
            if not primary or int(primary['moca_oid'])!=expected:
                raise ValueError('Nearby eligible objects changed; reload the target before declaring a duplicate')
            cur.execute('''SELECT moca_oid,classification FROM pcat_duplicated_vetting
                WHERE potential_duplicated_moca_oid=%s AND (classification='y' OR moca_oid=%s) FOR UPDATE''',(oid,expected))
            if cur.fetchall(): raise ValueError('A duplicate decision already exists for this target; no existing decision was changed')
            cur.execute('''INSERT INTO pcat_duplicated_vetting
                (moca_oid,potential_duplicated_moca_oid,classification,original_designation,
                 potential_duplicated_designation,original_spectral_type,potential_duplicated_spectral_type,comments)
                VALUES (%s,%s,'y',%s,%s,%s,%s,%s)''',
                (expected,oid,primary.get('designation'),getattr(obj,'designation',None),
                 primary.get('spectral_type'),getattr(obj,'adopted_spectral_type',None),comments.strip() or None))
            after=duplicate_snapshot(cur,expected,oid)
            cur.execute('''INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls)
                VALUES (%s,%s,1,%s,0,'gagne')''',(current_auth()['user'],'pcat_duplicated_vetting',
                f'wiseview_web/server.py: duplicate {oid} of {expected}'))
        undo_item={'kind':'duplicate','oid':oid,'primary_oid':expected,'after':after,'index':index}
        if session.get('validate_undo'):session['validate_undo'](undo_item)
        conn.commit();invalidate_sublime_stats()
    except Exception: conn.rollback();raise
    finally: conn.close()
    with session['lock']:
        session['undo'].append({'kind':'duplicate','oid':oid,'primary_oid':expected,'after':after,'index':index})
        session['object_cache'].pop(oid,None)
    return {'oid':oid,'primary_oid':expected}


def undo_duplicate(session,item):
    oid=item['oid'];primary=item['primary_oid'];conn=review._connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT moca_oid FROM moca_objects WHERE moca_oid=%s AND ignored=0 FOR UPDATE',(oid,))
            if not cur.fetchone(): raise ValueError('Object no longer active; duplicate undo refused')
            current=duplicate_snapshot(cur,primary,oid)
            if current!=item['after'] or not current or current.get('applied'):
                raise ValueError('Duplicate decision changed or was applied; undo refused')
            cur.execute('DELETE FROM pcat_duplicated_vetting WHERE moca_oid=%s AND potential_duplicated_moca_oid=%s',(primary,oid))
            cur.execute('''INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls)
                VALUES (%s,%s,1,%s,0,'gagne')''',(current_auth()['user'],'pcat_duplicated_vetting',
                f'wiseview_web/server.py: undo duplicate {oid} of {primary}'))
        conn.commit();invalidate_sublime_stats()
    except Exception:conn.rollback();raise
    finally:conn.close()
    with session['lock']:
        session['undo'].pop();session['object_cache'].pop(oid,None)
    return {'index':item['index'],'oid':oid}


def undo_decision(session):
    with session['lock']:
        if not session['undo']: raise ValueError('Nothing to undo')
        item=session['undo'][-1]
    if item.get('kind')=='duplicate': return undo_duplicate(session,item)
    oid=item['oid']; conn=review._connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT moca_oid FROM moca_objects WHERE moca_oid=%s AND ignored=0 FOR UPDATE',(oid,))
            if not cur.fetchone(): raise ValueError('Object no longer active')
            if snapshot(cur,oid)!=item['after']: raise ValueError('Classification changed since this review; undo refused')
            spectral_changes=item.get('spectral_reviews')
            if spectral_changes is None:spectral_changes=[item['spectral']] if item.get('spectral') else []
            cutout_change=item.get('cutout')
            if cutout_change:
                current_cutouts=clean(cutout_vetting.selected_rows(cutout_vetting.rows_for_object(cur,oid,lock=True),cutout_change['paths']))
                if current_cutouts!=cutout_change['after']:raise ValueError('Cutout review changed; undo refused')
            for change in spectral_changes:
                if clean(spectral_vetting.snapshot(cur,oid,change['lane']))!=change['after']:
                    raise ValueError('Spectral review or spectrum state changed; undo refused')
            for change in spectral_changes:
                spectral_vetting.restore(cur,oid,change['lane'],change['before'],change['after'])
            if cutout_change:cutout_vetting.restore(cur,oid,cutout_change['before'],cutout_change['after'])
            before=item['before']
            if before is None: cur.execute('DELETE FROM pcat_wiseview_visual_vetting WHERE moca_oid=%s',(oid,))
            else:
                cols=['classification','classification_integer','comments','reviewer','ra_deg','dec_deg','wiseview_url','source_table','origin']
                cur.execute('UPDATE pcat_wiseview_visual_vetting SET '+','.join('`'+c+'`=%s' for c in cols)+' WHERE moca_oid=%s',tuple(before[c] for c in cols)+(oid,))
            restored=snapshot(cur,oid)
            cur.execute('''INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls)
                VALUES (%s,%s,1,%s,0,'gagne')''',(current_auth()['user'],'pcat_wiseview_visual_vetting',f'wiseview_web/server.py: undo moca_oid={oid}'))
            for change in spectral_changes:
                lane=change['lane']
                cur.execute('''INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls)
                    VALUES (%s,%s,%s,%s,0,'gagne')''',(current_auth()['user'],
                    spectral_vetting.LANES[lane][0]+',data_spectral_types,moca_spectra',change['nrows'],
                    f'wiseview_web/server.py: undo paired spectral review moca_oid={oid}; lane={lane}'))
            if cutout_change:
                cur.execute('''INSERT INTO moca_changelog (`user`,modified_tables,nrows_modified,user_description,is_public,rls)
                    VALUES (%s,%s,%s,%s,0,'gagne')''',(current_auth()['user'],cutout_vetting.TABLE,len(cutout_change['paths']),
                    f'wiseview_web/server.py: undo paired cutout review moca_oid={oid}'))
        conn.commit()
        invalidate_sublime_stats()
    except Exception: conn.rollback(); raise
    finally: conn.close()
    with session['lock']:
        session['undo'].pop(); session.setdefault('snapshots',{})[oid]=restored; session['object_cache'].pop(oid,None)
        session.get('cutout_snapshots',{}).pop(oid,None)
        for change in spectral_changes:
            session.setdefault('spectral_snapshots',{}).setdefault(oid,{})[change['lane']]=change['before']['vetting']
            session['fit_cache'].pop((oid,SPECPACKS[change['lane']]),None)
    return {'index':item['index'],'oid':oid}
