"""SUBLIME findings dashboard, using the shared SPHEREx fitter.

Launch with python -B -m mocaviz.sublime_findings --port 8901.
No application import starts jobs, queries the database, or writes files.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import pymysql
from flask import Blueprint, Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from . import spherex_review as sr
from . import sublime_findings_inspector as inspector
from . import sublime_findings_duplicates as duplicates

STATIC = Path(__file__).resolve().parent / 'static'
findings = Blueprint('sublime_findings', __name__)
SOURCES = {'sublime1': 'pcat_sublime_candidates', 'sublime2': 'pcat_sublime_candidates_v2',
           'redmovers': 'pcat_catwise2020_red_movers'}
CLAIM_TOKENS = ('yadu', 'tom', 'bickle', 'sarah', 'azul', 'eastonh')
MAX_OBJECTS = 100000
LANES = tuple(sr.LANES)
GOOD_QUALITY = ('good', 'contaminated_ucd', 'peculiar_ucd', 'good_plus_star')
GOOD_CANDIDATE_QUALITY = (*GOOD_QUALITY, 'good_candidate')
QUALITY_CLASSES = {
    'good': GOOD_CANDIDATE_QUALITY,
    'one_good': GOOD_QUALITY,
    'all_good': GOOD_QUALITY,
    'all_good_candidate': GOOD_CANDIDATE_QUALITY,
}
ALL_QUALITY = frozenset(('all_good', 'all_good_candidate'))
NUMERIC = {'min_spt', 'max_spt', 'min_detection_snr', 'max_detection_snr', 'min_cnn', 'max_cnn',
           'min_snr', 'max_snr', 'min_motion', 'max_motion', 'min_cutout',
           'min_spiff_spt', 'max_spiff_spt', 'min_spiffstacker_spt', 'max_spiffstacker_spt',
           'min_sublimeaperture_spt', 'max_sublimeaperture_spt', 'min_parallax_snr',
           'min_w2', 'max_w2', 'min_chi2', 'max_chi2'}
TRI = ('byw', 'byw_claim', 'yadu', 'azul', 'smdet', 'known')
TEXT = {'cnn_classes', 'motion_classes', 'cutout_classes'} | {
    prefix + lane for prefix in ('include_', 'exclude_') for lane in LANES}


def parse_filters(raw):
    if not isinstance(raw, dict):
        raise sr.ReviewError('Filters must be an object.')
    allowed = NUMERIC | set(TRI) | TEXT | {'sources', 'spt_source', 'snr_lane', 'duplicates', 'cutout_policy', 'distance_mode', 'synthetic_lane', 'quality_any'}
    if set(raw) - allowed:
        raise sr.ReviewError('Unknown dashboard filter.')
    out = dict(raw)
    sources = out.get('sources', ['sublime2'])
    if not isinstance(sources, list) or not sources or any(s not in {*SOURCES, 'other'} for s in sources):
        raise sr.ReviewError('Choose at least one valid sample.')
    out['sources'] = sorted(set(sources))
    for key in NUMERIC:
        val = out.get(key)
        if val in (None, ''):
            out[key] = None
            continue
        if isinstance(val, bool):
            raise sr.ReviewError('Numeric cuts must contain finite numbers.')
        try:
            out[key] = float(val)
            if not math.isfinite(out[key]):
                raise ValueError()
        except (ValueError, TypeError):
            raise sr.ReviewError('Numeric cuts must contain finite numbers.') from None
    for key in NUMERIC:
        if key.startswith('min_') and 'max_' + key[4:] in out:
            lo, hi = out[key], out['max_' + key[4:]]
            if lo is not None and hi is not None and lo > hi:
                raise sr.ReviewError(key + ' must not exceed the maximum.')
    for key in ('min_cnn', 'max_cnn'):
        if out[key] is not None and not 0 <= out[key] <= 1:
            raise sr.ReviewError('CNN probability must be between 0 and 1.')
    for key in TRI:
        out.setdefault(key, 'no')
        if out[key] not in ('yes', 'no', 'either'):
            raise sr.ReviewError('Membership filters must be yes, no, or either.')
    defaults = {'spt_source':'best', 'snr_lane':'spiffstacker', 'duplicates':'exclude',
                'cutout_policy':'all', 'distance_mode':'astrometric', 'synthetic_lane':'any', 'quality_any':'good'}
    options = {'spt_source': ('best', 'sublime2', 'adopted', 'published', *LANES), 'snr_lane': LANES,
               'duplicates': ('exclude', 'only', 'either'), 'cutout_policy': ('all', 'any'),
               'distance_mode': ('astrometric', 'include_photometric'), 'synthetic_lane': ('any', *LANES), 'quality_any': ('any',*QUALITY_CLASSES,'reviewed','unreviewed')}
    for key, default in defaults.items():
        out.setdefault(key, default)
        if out[key] not in options[key]:
            raise sr.ReviewError('Invalid ' + key + '.')
    for key in TEXT:
        val = out.get(key, '')
        if not isinstance(val, str) or len(val) > 1000:
            raise sr.ReviewError('Class lists must be comma-separated text.')
        out[key] = [v.strip().lower() for v in val.split(',') if v.strip()]
    # Requiring good in a specific reduction uses the same UCD family as the
    # global good modes. Exclusions remain the explicit classes entered.
    for lane in LANES:
        key = 'include_' + lane
        if 'good' in out[key]:
            out[key] = list(dict.fromkeys([*out[key], *GOOD_QUALITY[1:]]))
    return out


def fetch(cur, sql, params=()):
    cur.execute(sql, params)
    return list(cur.fetchall())



def known_expression(alias):
    """Published late-type status follows both sides of confirmed duplicate links."""
    oid=alias+'.moca_oid'
    published="d.public_adopted=1 AND d.photometric_estimate=0 AND d.spectral_type_number>=0"
    return '('+(' OR '.join((
        'EXISTS (SELECT 1 FROM data_spectral_types d WHERE d.moca_oid='+oid+' AND '+published+')',
        "EXISTS (SELECT 1 FROM pcat_duplicated_vetting dup JOIN data_spectral_types d ON d.moca_oid=dup.moca_oid WHERE dup.classification='y' AND dup.potential_duplicated_moca_oid="+oid+' AND '+published+')',
        "EXISTS (SELECT 1 FROM pcat_duplicated_vetting dup JOIN data_spectral_types d ON d.moca_oid=dup.potential_duplicated_moca_oid WHERE dup.classification='y' AND dup.moca_oid="+oid+' AND '+published+')'
    )))+')'



def quality_condition(mode, oid='mo.moca_oid'):
    """SQL quality semantics, including unreviewed active reductions for all modes."""
    def reviewed(cfg, classes=None):
        sql='EXISTS (SELECT 1 FROM `'+cfg['table']+'` q WHERE q.moca_oid='+oid
        if classes:
            sql+=' AND LOWER(q.classification) IN ('+','.join("'"+c+"'" for c in classes)+')'
        return sql+')'
    if mode=='any':return '1=1'
    if mode in ALL_QUALITY:
        available=[];passing=[]
        for cfg in sr.LANES.values():
            active='EXISTS (SELECT 1 FROM moca_spectra active_s WHERE active_s.moca_oid='+oid+' AND active_s.moca_specpackid='+str(cfg['pack'])+' AND active_s.ignored=0)'
            available.append(active)
            passing.append('(NOT '+active+' OR '+reviewed(cfg,QUALITY_CLASSES[mode])+')')
        return '('+' OR '.join(available)+') AND '+' AND '.join(passing)
    clauses=[reviewed(cfg,QUALITY_CLASSES.get(mode)) for cfg in sr.LANES.values()]
    return ('NOT ' if mode=='unreviewed' else '')+'('+' OR '.join(clauses)+')'


def selected_sql(f):
    """Keep the large catalogue union in SQL; never download an unfiltered catalogue."""
    unions = ['SELECT moca_oid, 0 AS is_other FROM `' + SOURCES[s] + '` WHERE moca_oid IS NOT NULL'
              for s in f['sources'] if s in SOURCES]
    if 'other' in f['sources']:
        if f['quality_any'] in QUALITY_CLASSES or f['quality_any']=='reviewed':
            classes=QUALITY_CLASSES.get(f['quality_any'])
            quality_where=' WHERE LOWER(classification) IN ('+','.join("'"+c+"'" for c in classes)+')' if classes else ''
            seed=' UNION '.join('SELECT moca_oid FROM `'+cfg['table']+'`'+quality_where for cfg in sr.LANES.values())
        else:
            methods = ','.join("'" + method + "'" for cfg in sr.LANES.values() for method in cfg['methods'])
            seed = ('SELECT DISTINCT moca_oid FROM data_spectral_types WHERE ignored=0 '
                    'AND spectral_type_number IS NOT NULL AND calculation_method IN (' + methods + ')')
        other_from = '(' + seed + ') eligible JOIN moca_objects mo ON mo.moca_oid=eligible.moca_oid'
        adopted_m0 = ('EXISTS (SELECT 1 FROM data_spectral_types private_type WHERE private_type.moca_oid=mo.moca_oid '
                      'AND private_type.adopted=1 AND private_type.ignored=0 AND private_type.spectral_type_number>=0)')
        unions.append('SELECT mo.moca_oid, 1 AS is_other FROM '+other_from+' WHERE mo.ignored=0 AND '+adopted_m0+
                      ' AND NOT '+known_expression('mo')+' AND ' +
                      ' AND '.join('mo.moca_oid NOT IN (SELECT c.moca_oid FROM `' + t + '` c WHERE c.moca_oid IS NOT NULL)' for t in SOURCES.values()))
    type_cols, type_joins = [], []
    for lane, config in sr.LANES.items():
        methods = ','.join("'" + m + "'" for m in config['methods'])
        type_joins.append('LEFT JOIN (SELECT moca_oid,MAX(id) AS id FROM data_spectral_types WHERE ignored=0 AND calculation_method IN ('+methods+') GROUP BY moca_oid) latest_'+lane+' ON latest_'+lane+'.moca_oid=mo.moca_oid LEFT JOIN data_spectral_types t_'+lane+' ON t_'+lane+'.id=latest_'+lane+'.id')
        type_cols.append('t_' + lane + '.spectral_type_number AS ' + lane + '_spt')
    type_joins.append('LEFT JOIN data_spectral_types ta ON ta.moca_oid=mo.moca_oid AND ta.adopted=1 AND ta.ignored=0')
    expressions = {'sublime2':'p2.autotype_spectral_type_number', 'adopted':'ta.spectral_type_number','published':'tp.spectral_type_number'}
    expressions.update({lane:'t_' + lane + '.spectral_type_number' for lane in LANES})
    expressions['best'] = 'COALESCE(t_spiffstacker.spectral_type_number,t_sublimeaperture.spectral_type_number,p2.autotype_spectral_type_number,t_spiff.spectral_type_number,tp.spectral_type_number)'
    type_joins.append('LEFT JOIN data_spectral_types tp ON tp.moca_oid=mo.moca_oid AND tp.public_adopted=1 AND tp.photometric_estimate=0 AND tp.spectral_type_number>=0')
    spt = expressions[f['spt_source']]
    # A union of potentially passing types is a safe superset of a COALESCE cut.
    # Apply it before catalogue joins to avoid hundreds of thousands of lookups.
    preselect = ''
    if f['min_spt'] is not None:
        threshold = str(float(f['min_spt']))
        if f['spt_source']=='published':
            candidates='SELECT d.moca_oid FROM data_spectral_types d WHERE d.public_adopted=1 AND d.photometric_estimate=0 AND d.spectral_type_number>='+threshold
        elif f['spt_source']=='adopted':
            candidates='SELECT d.moca_oid FROM data_spectral_types d WHERE d.adopted=1 AND d.ignored=0 AND d.spectral_type_number>='+threshold
        elif f['spt_source'] in LANES:
            methods=','.join("'"+m+"'" for m in sr.LANES[f['spt_source']]['methods'])
            candidates='SELECT DISTINCT d.moca_oid FROM data_spectral_types d WHERE d.ignored=0 AND d.calculation_method IN ('+methods+') AND d.spectral_type_number>='+threshold
        elif f['spt_source']=='sublime2':
            candidates='SELECT DISTINCT moca_oid FROM pcat_sublime_candidates_v2 WHERE autotype_spectral_type_number>='+threshold
        else:
            candidates='''SELECT DISTINCT d.moca_oid FROM data_spectral_types d WHERE d.ignored=0
                AND d.spectral_type_number>='''+threshold+''' AND (d.public_adopted=1 OR
                d.calculation_method IN ('spherex_autotype','spiff_stacker_autotype','sublimeaperture_autotype','spherex_sublimeap_autotype'))
                UNION SELECT moca_oid FROM pcat_sublime_candidates_v2 WHERE autotype_spectral_type_number>='''+threshold
        preselect='JOIN ('+candidates+') typed ON typed.moca_oid=sample.moca_oid'
    where, params = ['mo.ignored=0'], []
    if 'other' in f['sources']:
        lane_types = ','.join(expressions[lane] for lane in LANES)
        where.append('(sample.is_other=0 OR COALESCE(' + lane_types + ') IS NOT NULL)')
    def bound(expr, low, high=None):
        if f.get(low) is not None:
            where.append(expr + '>=%s'); params.append(f[low])
        if high and f.get(high) is not None:
            where.append(expr + '<=%s'); params.append(f[high])
    if f['quality_any']!='any':
        where.append('('+quality_condition(f['quality_any'])+')')
    if f['duplicates']!='either':
        where.append(('NOT ' if f['duplicates']=='exclude' else '')+"EXISTS (SELECT 1 FROM pcat_duplicated_vetting dup WHERE dup.potential_duplicated_moca_oid=mo.moca_oid AND dup.classification='y')")
    for lane,cfg in sr.LANES.items():
        for prefix,negative in (('include_',False),('exclude_',True)):
            classes=f[prefix+lane]
            if not classes:continue
            values=[c for c in classes if c!='none']
            conditions=[]
            if values:
                conditions.append('EXISTS (SELECT 1 FROM `'+cfg['table']+'` q WHERE q.moca_oid=mo.moca_oid AND LOWER(q.classification) IN ('+','.join(['%s']*len(values))+'))')
                params.extend(values)
            if 'none' in classes:conditions.append('NOT EXISTS (SELECT 1 FROM `'+cfg['table']+'` q WHERE q.moca_oid=mo.moca_oid)')
            where.append(('NOT ' if negative else '')+'('+' OR '.join(conditions)+')')
    if f['min_motion'] is not None or f['max_motion'] is not None:
        motion=['w.moca_oid=mo.moca_oid']
        for key,op in (('min_motion','>='),('max_motion','<=')):
            if f[key] is not None:motion.append('w.classification_integer'+op+'%s');params.append(f[key])
        where.append('EXISTS (SELECT 1 FROM pcat_wiseview_visual_vetting w WHERE '+' AND '.join(motion)+')')
    bound(spt, 'min_spt', 'max_spt')
    for lane in LANES:
        bound(expressions[lane], 'min_' + lane + '_spt', 'max_' + lane + '_spt')
    bound('COALESCE(p2.detection_snr,p1.detection_snr)', 'min_detection_snr', 'max_detection_snr')
    bound('p2.visual_nn_good_probability','min_cnn','max_cnn')
    bound('p2.autotype_reduced_chi2','min_chi2','max_chi2')
    if f['cnn_classes']:
        classes=[c for c in f['cnn_classes'] if c!='none']
        terms=[]
        if classes:
            terms.append('LOWER(p2.visual_nn_classification) IN ('+','.join(['%s']*len(classes))+')')
            params.extend(classes)
        if 'none' in f['cnn_classes']:terms.append('p2.visual_nn_classification IS NULL')
        where.append('('+' OR '.join(terms)+')')
    return '''SELECT mo.moca_oid,mo.designation,mo.ra,mo.`dec`,mo.is_public,
        ''' + spt + ''' AS spt,''' + ','.join(type_cols) + ''',
        p2.autotype_spectral_type_number AS sublime2_spt,ta.spectral_type_number AS adopted_spt,tp.spectral_type_number AS published_spt,
        CASE WHEN t_spiffstacker.spectral_type_number IS NOT NULL THEN 'spiffstacker'
             WHEN t_sublimeaperture.spectral_type_number IS NOT NULL THEN 'sublimeaperture'
             WHEN p2.autotype_spectral_type_number IS NOT NULL THEN 'sublime2'
             WHEN t_spiff.spectral_type_number IS NOT NULL THEN 'spiff' ELSE 'published' END AS best_spt_source,
        p1.id IS NOT NULL AS sublime1,p2.id IS NOT NULL AS sublime2,
        COALESCE(p2.detection_snr,p1.detection_snr) AS detection_snr,
        p2.visual_nn_good_probability AS cnn,p2.visual_nn_classification AS cnn_class,
        p2.autotype_reduced_chi2 AS chi2
        FROM (''' + ' UNION '.join(unions) + ''') sample
        ''' + preselect + '''
        JOIN moca_objects mo ON mo.moca_oid=sample.moca_oid
        LEFT JOIN (SELECT moca_oid,MAX(id) AS id FROM pcat_sublime_candidates GROUP BY moca_oid) latest_p1 ON latest_p1.moca_oid=mo.moca_oid
        LEFT JOIN pcat_sublime_candidates p1 ON p1.id=latest_p1.id
        LEFT JOIN (SELECT moca_oid,MAX(id) AS id FROM pcat_sublime_candidates_v2 GROUP BY moca_oid) latest_p2 ON latest_p2.moca_oid=mo.moca_oid
        LEFT JOIN pcat_sublime_candidates_v2 p2 ON p2.id=latest_p2.id
        ''' + '\n'.join(type_joins) + '\n WHERE ' + ' AND '.join(where) + ' ORDER BY mo.moca_oid LIMIT ' + str(MAX_OBJECTS + 1), tuple(params)


def enrich(cur, rows):
    """Bound queries to selected IDs. Every reduction lane and provenance stays distinct."""
    by_oid = {r['moca_oid']: r for r in rows}
    for start in range(0, len(rows), 1000):
        chunk = rows[start:start+1000]
        ids = tuple(r['moca_oid'] for r in chunk)
        ph = ','.join(['%s']*len(ids))
        for r in chunk:
            r.update(redmovers=False, byw=False, byw_claim=False, yadu=False, azul=False,
                     smdet=False, duplicate=False, known=False, cutout_scores=[], cutout_classes=[],
                     cutout_count=0, motion=None, motion_class=None)
        tables = {'redmovers':'pcat_catwise2020_red_movers','byw':'pcat_byw_mar9_2026',
                  'yadu':'pcat_kirkpatrick_yadu_2026_claim','azul':'pcat_azul_byw_sample_jul16_2026'}
        for field, table in tables.items():
            for r in fetch(cur, 'SELECT DISTINCT moca_oid FROM `' + table + '` WHERE moca_oid IN (' + ph + ')', ids):
                by_oid[r['moca_oid']][field] = True
        claim = ' OR '.join('LOWER(disc) LIKE %s' for _ in CLAIM_TOKENS)
        sql = 'SELECT DISTINCT moca_oid FROM pcat_byw_mar9_2026 WHERE moca_oid IN (' + ph + ') AND (' + claim + ') UNION SELECT moca_oid FROM pcat_schneider_claim_list_byw WHERE moca_oid IN (' + ph + ')'
        for r in fetch(cur, sql, (*ids, *('%'+t+'%' for t in CLAIM_TOKENS), *ids)):
            by_oid[r['moca_oid']]['byw_claim'] = True
        for r in fetch(cur, "SELECT DISTINCT moca_oid FROM mechanics_all_designations WHERE moca_oid IN (" + ph + ") AND designation LIKE 'SMDET%%'", ids):
            by_oid[r['moca_oid']]['smdet'] = True
        for r in fetch(cur, "SELECT DISTINCT potential_duplicated_moca_oid AS moca_oid FROM pcat_duplicated_vetting WHERE potential_duplicated_moca_oid IN (" + ph + ") AND classification='y'", ids):
            by_oid[r['moca_oid']]['duplicate'] = True
        known_sql = '''SELECT DISTINCT moca_oid FROM data_spectral_types WHERE moca_oid IN (''' + ph + ''') AND public_adopted=1 AND photometric_estimate=0 AND spectral_type_number>=0
        UNION SELECT dup.potential_duplicated_moca_oid FROM pcat_duplicated_vetting dup JOIN data_spectral_types d ON d.moca_oid=dup.moca_oid AND d.public_adopted=1 AND d.photometric_estimate=0 AND d.spectral_type_number>=0 WHERE dup.classification='y' AND dup.potential_duplicated_moca_oid IN (''' + ph + ''')
        UNION SELECT dup.moca_oid FROM pcat_duplicated_vetting dup JOIN data_spectral_types d ON d.moca_oid=dup.potential_duplicated_moca_oid AND d.public_adopted=1 AND d.photometric_estimate=0 AND d.spectral_type_number>=0 WHERE dup.classification='y' AND dup.moca_oid IN (''' + ph + ')'
        for r in fetch(cur, known_sql, ids*3):
            by_oid[r['moca_oid']]['known'] = True
        for r in fetch(cur, 'SELECT moca_oid,classification_integer,classification FROM pcat_wiseview_visual_vetting WHERE moca_oid IN (' + ph + ')', ids):
            by_oid[r['moca_oid']].update(motion=r['classification_integer'],motion_class=r['classification'])
        for r in fetch(cur, 'SELECT moca_oid,classification_integer,classification FROM pcat_spherex_cutout_visual_vetting WHERE moca_oid IN (' + ph + ') ORDER BY id', ids):
            target=by_oid[r['moca_oid']]
            target['cutout_count'] += 1
            target['cutout_scores'].append(r['classification_integer'])
            target['cutout_classes'].append(r['classification'])
        for lane, cfg in sr.LANES.items():
            for r in fetch(cur, 'SELECT moca_oid,classification FROM `' + cfg['table'] + '` WHERE moca_oid IN (' + ph + ')', ids):
                by_oid[r['moca_oid']][lane+'_quality'] = r['classification']
            for r in fetch(cur, '''SELECT s.moca_oid,s.moca_specid,s.median_snr_per_pix,s.ignored FROM moca_spectra s JOIN
                (SELECT moca_oid,COALESCE(MAX(CASE WHEN ignored=0 THEN moca_specid END),MAX(moca_specid)) AS moca_specid
                 FROM moca_spectra WHERE moca_oid IN (''' + ph + ''') AND moca_specpackid=%s GROUP BY moca_oid) latest
                ON latest.moca_specid=s.moca_specid''', (*ids,cfg['pack'])):
                by_oid[r['moca_oid']][lane+'_specid'] = r['moca_specid']
                by_oid[r['moca_oid']][lane+'_ignored'] = bool(r['ignored'])
                if not r['ignored']:
                    by_oid[r['moca_oid']][lane+'_snr'] = r['median_snr_per_pix']
    return rows


def passes(r, f):
    quality=[str(r.get(lane+'_quality') or '').lower() for lane in LANES]
    mode=f['quality_any']
    if mode in ALL_QUALITY:
        available=[str(r.get(lane+'_quality') or '').lower() for lane in LANES
                   if r.get(lane+'_specid') and not r.get(lane+'_ignored')]
        if not available or not all(v in QUALITY_CLASSES[mode] for v in available):return False
    elif mode in QUALITY_CLASSES and not any(v in QUALITY_CLASSES[mode] for v in quality):return False
    if f['quality_any']=='reviewed' and not any(quality):return False
    if f['quality_any']=='unreviewed' and any(quality):return False
    for key in TRI:
        if f[key] != 'either' and bool(r.get(key)) != (f[key]=='yes'):
            return False
    if f['duplicates'] != 'either' and bool(r['duplicate']) != (f['duplicates']=='only'):
        return False
    for field,lo,hi in ((f['snr_lane']+'_snr','min_snr','max_snr'), ('motion','min_motion','max_motion')):
        val=r.get(field)
        if f[lo] is not None and (val is None or val < f[lo]): return False
        if f[hi] is not None and (val is None or val > f[hi]): return False
    if f['motion_classes'] and str(r.get('motion_class') or 'none').lower() not in f['motion_classes']:
        return False
    for lane in LANES:
        quality = str(r.get(lane+'_quality') or 'none').lower()
        if f['include_'+lane] and quality not in f['include_'+lane]: return False
        if quality in f['exclude_'+lane]: return False
    scores=r['cutout_scores']
    if f['min_cutout'] is not None:
        checks=[s is not None and s>=f['min_cutout'] for s in scores]
        if not checks or not (all(checks) if f['cutout_policy']=='all' else any(checks)): return False
    if f['cutout_classes']:
        checks=[str(s).lower() in f['cutout_classes'] for s in r['cutout_classes']]
        if not checks:
            checks=['none' in f['cutout_classes']]
        if not (all(checks) if f['cutout_policy']=='all' else any(checks)): return False
    return True


def photometry(cur, rows, f):
    by_oid={r['moca_oid']:r for r in rows}
    for start in range(0,len(rows),1000):
        chunk=rows[start:start+1000]
        ids=tuple(r['moca_oid'] for r in chunk); ph=','.join(['%s']*len(ids))
        for r in fetch(cur, 'SELECT id,moca_oid,parallax_mas,parallax_mas_unc FROM data_parallaxes WHERE moca_oid IN ('+ph+') AND adopted=1 AND ignored=0 AND parallax_mas>0',ids):
            by_oid[r['moca_oid']].update(parallax_id=r['id'],parallax=r['parallax_mas'],parallax_unc=r['parallax_mas_unc'],
                 distance_pc=1000/float(r['parallax_mas']),distance_kind='parallax')
        dist_filter='' if f['distance_mode']=='include_photometric' else ' AND photometric_estimate=0'
        for r in fetch(cur, 'SELECT id,moca_oid,distance_pc,photometric_estimate FROM data_distances WHERE moca_oid IN ('+ph+') AND adopted=1 AND ignored=0 AND distance_pc>0'+dist_filter,ids):
            obj=by_oid[r['moca_oid']]
            if not obj.get('distance_pc'):
                obj.update(distance_id=r['id'],distance_pc=r['distance_pc'],distance_kind='photometric' if r['photometric_estimate'] else 'nonphotometric')
        data=fetch(cur, '''SELECT p.id,p.moca_oid,p.magnitude,p.magnitude_unc,p.is_synthetic,p.moca_specid,p.calculation_method,p.origin,s.moca_specpackid
            FROM data_photometry p LEFT JOIN moca_spectra s ON s.moca_specid=p.moca_specid
            WHERE p.moca_oid IN ('''+ph+''') AND p.system_band_simple='W2' AND p.ignored=0 AND p.magnitude IS NOT NULL
            AND (p.is_synthetic=0 OR (p.is_synthetic=1 AND ((s.moca_specpackid IN (55,62,76) AND s.ignored=0) OR (p.moca_specid IS NULL AND p.calculation_method='spherex_w2_synth'))))
            ORDER BY p.adopted_simpleband DESC,p.adopted DESC,p.id DESC''',ids)
        for p in data:
            obj=by_oid[p['moca_oid']]
            key='synthetic_w2' if p['is_synthetic'] else 'w2'
            # Synthetic measurements follow the selected reduction lane when present.
            if p['is_synthetic'] and f['synthetic_lane'] != 'any' and p['moca_specpackid'] != sr.LANES[f['synthetic_lane']]['pack']: continue
            if key in obj: continue
            obj[key]=p['magnitude'];obj[key+'_unc']=p['magnitude_unc'];obj[key+'_id']=p['id']
            if p['is_synthetic']:
                obj['synthetic_w2_pack']=p['moca_specpackid'];obj['synthetic_w2_specid']=p['moca_specid'];obj['synthetic_w2_method']=p['calculation_method'] or p['origin']
    result=[]
    for r in rows:
        r['other']=not any(r.get(s) for s in SOURCES) and not r['known']
        r['samples']=[s for s in (*SOURCES,'other') if r.get(s)]
        r['spt_source']=r['best_spt_source'] if f['spt_source']=='best' else f['spt_source']
        p,pu=r.get('parallax'),r.get('parallax_unc')
        r['parallax_snr']=float(p)/float(pu) if p and pu and pu>0 else None
        if f['min_parallax_snr'] is not None and (r['parallax_snr'] is None or r['parallax_snr']<f['min_parallax_snr']): continue
        if any(f[k] is not None and (r.get('w2') is None or (r['w2']<f[k] if k=='min_w2' else r['w2']>f[k])) for k in ('min_w2','max_w2')): continue
        d=r.get('distance_pc')
        for key in ('w2','synthetic_w2'):
            mag=r.get(key)
            r['M_'+key]=float(mag)-5*math.log10(float(d))+5 if mag is not None and d and d>0 else None
            err=r.get(key+'_unc')
            de=5/math.log(10)*float(pu)/float(p) if p and pu and pu>0 else None
            r['M_'+key+'_unc']=math.hypot(float(err),de) if err is not None and de is not None else None
        if r.get('w2') is not None and r.get('synthetic_w2') is not None:
            r['w2_difference']=float(r['synthetic_w2'])-float(r['w2'])
        else:r['w2_difference']=None
        result.append(r)
    return result


def load(cur,f):
    sql,params=selected_sql(f)
    rows=fetch(cur,sql,params)
    if len(rows)>MAX_OBJECTS:
        raise sr.ReviewError('More than 100,000 objects pass the initial sample/type cuts. Raise the minimum spectral type or select fewer samples; no partial dashboard was produced.',422)
    preliminary=len(rows)
    rows=[r for r in enrich(cur,rows) if passes(r,f)]
    rows=photometry(cur,rows,f)
    rows.sort(key=lambda r:(r['spt'] is None,-float(r['spt'] or 0),r['moca_oid']))
    return rows,preliminary


def demo_rows(f):
    rows=[]
    for i in range(180):
        r={'moca_oid':1001+i,'designation':'Demo J%04d'%i,'ra':(i*137.508)%360,'dec':-78+(i*19)%156,
           'spt':10+(i%24)*.9,'sublime1':i%3==0,'sublime2':i%3==1,'redmovers':i%3==2,'other':False,
           'detection_snr':7+i%30,'cnn':.7+(i%29)/100,'cnn_class':'good',
           'best_spt_source':'spiffstacker','motion':3+i%4,'motion_class':'clear motion, red detection',
           'cutout_scores':[3,4],'cutout_classes':['Good centered on PSF but crowded','Good centered on PSF and isolated'],
           'cutout_count':2,'chi2':1+i/20,'is_public':0}
        for j,k in enumerate(TRI):r[k]=False if k=='known' else i%(j+3)==0
        r['duplicate']=i%17==0
        for lane in LANES:r.update({lane+'_quality':'good',lane+'_spt':r['spt'],lane+'_snr':8+i%15,lane+'_specid':11001+i})
        r.update(sublime2_spt=r['spt'],adopted_spt=r['spt'],parallax=40+i,parallax_unc=2,parallax_snr=(40+i)/2,
                 distance_pc=1000/(40+i),distance_kind='parallax',spt_source='spiffstacker',
                 w2=14+i/40,synthetic_w2=14.1+i/40,w2_difference=.1,
                 M_w2=10+i/40,M_synthetic_w2=10.1+i/40,M_w2_unc=.1,M_synthetic_w2_unc=.12)
        r['samples']=[s for s in SOURCES if r[s]]
        if not any(r.get(s) for s in f['sources']):continue
        if f['min_spt'] is not None and r['spt']<f['min_spt']:continue
        if f['max_spt'] is not None and r['spt']>f['max_spt']:continue
        if passes(r,f):rows.append(r)
    return sorted(rows,key=lambda r:-r['spt'])


@findings.after_request
def private_response(response):
    response.headers.update({'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff',
                             'Content-Security-Policy':"frame-ancestors 'self'"})
    return response


@findings.get('/')
@findings.get('/sublime-findings')
def page():
    return send_from_directory(STATIC,'sublime_findings.html')


@findings.get('/assets/<name>')
def asset(name):
    if name not in ('sublime_findings.js','sublime_findings.css','spherex_review_plot.js'):
        raise sr.ReviewError('Unknown asset.',404)
    return send_from_directory(STATIC,name)


@findings.get('/assets/plotly.js')
def plotly_asset():
    import plotly
    return send_from_directory(Path(plotly.__file__).parent/'package_data','plotly.min.js')


@findings.post('/api/findings/<operation>')
def api(operation):
    try:
        if operation not in ('load','spectra','cutouts','survey','duplicate-matches','declare-duplicate','spectrum-positions'):raise sr.ReviewError('Unknown operation.',404)
        if request.content_length and request.content_length>32768:raise sr.ReviewError('Request too large.',413)
        if not request.is_json:raise sr.ReviewError('Provide JSON.',415)
        body=request.get_json()
        if not isinstance(body,dict):raise sr.ReviewError('Provide a JSON object.')
        mock=sr.boolean(body.get('mock',False))
        started=time.monotonic()
        if operation=='duplicate-matches':
            raw_ids=body.get('oids')
            if not isinstance(raw_ids,list) or len(raw_ids)>duplicates.BATCH_SIZE:
                raise sr.ReviewError(f'Request up to {duplicates.BATCH_SIZE} selected object IDs.')
            ids=sorted({sr.integer(value,'Object ID') for value in raw_ids})
            if mock:
                matches=[]
                for oid in ids[::7]:
                    target={'moca_oid':oid,'designation':'Demo J%04d'%(oid-1001),
                            'measurement_epoch_yr':2025.5,'pmra_masyr':240,'pmdec_masyr':-180}
                    known={'moca_oid':100000000+oid,'designation':'Demo published UCD',
                           'spectral_type':'L5', 'reference_name':'Synthetic reference','measurement_epoch_yr':2016,
                           'in_byw':True,'pmra_masyr':243,'pmdec_masyr':-175,'pmra_masyr_unc':4,'pmdec_masyr_unc':5}
                    matches.append({'target':target,'known':known,'separation_arcsec':oid%23+3.4})
                positioned=len(ids)
                can_write=True
            else:
                auth=sr.credentials()
                with sr.connection(auth) as (_,cur):
                    cur.execute('START TRANSACTION READ ONLY')
                    matches,positioned=duplicates.scan(cur,ids)
                can_write=auth['user']=='management'
            return jsonify(sr.clean({'ok':True,'matches':matches,'positioned':positioned,'can_write':can_write}))
        if operation=='declare-duplicate':
            oid=sr.integer(body.get('moca_oid'),'Selected object ID')
            primary=sr.integer(body.get('primary_oid'),'Counterpart object ID')
            if oid==primary:
                raise sr.ReviewError('Select two distinct MOCAdb objects.')
            if mock:
                decision={'moca_oid':primary,'potential_duplicated_moca_oid':oid,'classification':'y','applied':False}
            else:
                auth=sr.credentials()
                sr.require_management(auth)
                with sr.connection(auth) as (conn,cur):
                    decision=duplicates.declare(conn,cur,auth,oid,primary)
            return jsonify(ok=True,decision=decision)
        if operation=='spectrum-positions':
            oid=sr.integer(body.get('moca_oid'),'Object ID')
            raw_ids=body.get('specids')
            if not isinstance(raw_ids,dict) or set(raw_ids)-set(LANES):
                raise sr.ReviewError('Invalid spectrum lanes.')
            ids={lane:sr.integer(specid,'Spectrum ID') for lane,specid in raw_ids.items()}
            positions={}
            if not mock:
                with sr.connection(sr.credentials()) as (_,cur):
                    cur.execute('START TRANSACTION READ ONLY')
                    positions=inspector.astrometry.spectrum_positions(cur,oid,ids)
            return jsonify(sr.clean({'ok':True,'positions':positions}))
        if operation=='survey':
            if not mock:sr.credentials()
            try:
                result=inspector.survey(body.get('survey'),float(body.get('ra')),float(body.get('dec')),float(body.get('fov',60)),
                                        inspector.chart_positions(body.get('positions',{})))
                return jsonify(ok=True,available=True,**result)
            except (ValueError,TypeError):return jsonify(ok=True,available=False,error='Survey unavailable or no image coverage at this position.')
            except Exception:return jsonify(ok=True,available=False,error='Survey service is currently unavailable. Try this panel again later.')
        if operation=='cutouts':
            oid=sr.integer(body.get('moca_oid'),'Object ID')
            if mock:result={'images':[],'missing_cutouts':0,'source_keys':0}
            else:
                with sr.connection(sr.credentials()) as (conn,cur):
                    cur.execute('START TRANSACTION READ ONLY')
                    result=inspector.cutouts(cur,oid,inspector.chart_positions(body.get('positions',{})))
            return jsonify(sr.clean({'ok':True,**result}))
        if operation=='load':
            f=parse_filters(body.get('filters',{}))
            if mock:rows=demo_rows(f);preliminary=len(rows)
            else:
                with sr.connection(sr.credentials()) as (conn,cur):
                    cur.execute('START TRANSACTION READ ONLY')
                    rows,preliminary=load(cur,f)
            return jsonify(sr.clean({'ok':True,'rows':rows,'preliminary':preliminary,'elapsed':time.monotonic()-started,
                                     'mock':mock,'loaded_at':time.time(),'complete':True,'quality_definition_version':2,
                                     'other_sample_version':1}))
        items=body.get('items')
        if not isinstance(items,list) or len(items)>10:raise sr.ReviewError('Request up to ten spectra.')
        lane_key=body.get('lane','spiffstacker')
        if lane_key not in sr.LANES:raise sr.ReviewError('Invalid spectrum lane.')
        parsed=[(sr.integer(r.get('moca_oid'),'Object ID'),sr.integer(r.get('moca_specid'),'Spectrum ID')) for r in items if isinstance(r,dict)]
        if len(parsed)!=len(items):raise sr.ReviewError('Invalid spectrum requests.')
        results=[]
        if mock:
            results=[sr.demo_item({'moca_oid':oid,'moca_specid':specid,'lane':lane_key}) for oid,specid in parsed]
            for item in results:item['fit']['overlays']=item['fit'].get('overlays',[])[:1]
        else:
            with sr.connection(sr.credentials()) as (conn,cur):
                cur.execute('START TRANSACTION READ ONLY')
                templates=None
                for oid,specid in parsed:
                    try:
                        meta=sr.spectrum_metadata(cur,specid,oid,sr.LANES[lane_key])
                        spectrum=fetch(cur,'SELECT id AS data_spectra_id,wavelength_angstrom,flux_flambda,flux_flambda_unc,ignored FROM data_spectra WHERE moca_specid=%s ORDER BY wavelength_angstrom,id LIMIT 10001',(specid,))
                        if len(spectrum)>10000:raise sr.ReviewError('Spectrum exceeds interactive size limit.')
                        if templates is None:
                            templates=fetch(cur,'''SELECT t.moca_spherex_template_id,t.spectral_type,t.spectral_type_number,t.grid_type,dt.wavelength_angstrom,dt.flux_flambda
                                FROM moca_spherex_templates t JOIN data_spherex_templates dt ON dt.moca_spherex_template_id=t.moca_spherex_template_id
                                WHERE t.ignored=0 AND dt.ignored=0 AND dt.flux_flambda>0 AND dt.wavelength_angstrom IS NOT NULL
                                  AND t.spectral_type IS NOT NULL AND t.spectral_type_number IS NOT NULL
                                ORDER BY t.moca_spherex_template_id,dt.wavelength_angstrom LIMIT 200001''')
                            if len(templates)>200000:raise sr.ReviewError('Template grid exceeds interactive size limit.')
                        warning=None
                        try:
                            fit=sr.fit_spectrum(spectrum,templates,sr.fit_options({}))
                            fit['overlays']=fit.get('overlays',[])[:1]
                        except ValueError as exc:
                            fit=None;warning=str(exc)
                        results.append({'object':meta,'raw_spectrum':spectrum,'fit':fit,'warning':warning})
                    except (sr.ReviewError,ValueError) as exc:
                        results.append({'object':{'moca_oid':oid,'moca_specid':specid},'error':str(exc)})
        return jsonify(sr.clean({'ok':True,'items':results,'elapsed':time.monotonic()-started}))
    except sr.ReviewError as exc:return jsonify(ok=False,error=str(exc)),exc.status
    except HTTPException as exc:return jsonify(ok=False,error=exc.name),exc.code
    except pymysql.MySQLError:
        if operation=='declare-duplicate':
            return jsonify(ok=False,error='Could not verify the declaration. Rescan to check its status.'),503
        return jsonify(ok=False,error='Database request failed. Check the connection and retry; no database changes were made.'),503
    except Exception:
        if operation=='declare-duplicate':
            return jsonify(ok=False,error='Could not verify the declaration. Rescan to check its status.'),500
        return jsonify(ok=False,error='Dashboard request failed. No database changes were made.'),500


@findings.get('/wiseview-frame')
def wiseview_frame():
    from flask import Response
    try:return Response(inspector.wiseview_html(),mimetype='text/html')
    except Exception:return Response('<p>WiseView is unavailable. Open the external WiseView link to retry.</p>',mimetype='text/html',status=502)


@findings.get('/wiseview-assets/<name>')
def wiseview_asset(name):
    from flask import Response
    if name not in ('flash3.js','flash3-theme.css'):return jsonify(ok=False),404
    try:
        data=inspector.remote_text('http://byw.tools/static/'+name,limit=3_000_000)
        response=Response(data,mimetype='text/javascript' if name.endswith('.js') else 'text/css')
        response.headers['Access-Control-Allow-Origin']='*'
        return response
    except Exception:return jsonify(ok=False,error='WiseView asset unavailable.'),502


@findings.route('/pawnstars',methods=['GET','OPTIONS'])
@findings.route('/xref',methods=['GET','OPTIONS'])
def wiseview_public_lookup():
    # These two fixed public lookups support WiseView's opaque sandbox origin.
    # No credentials, arbitrary destinations or private database access cross it.
    cors={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET, OPTIONS',
          'Access-Control-Allow-Headers':'X-Requested-With, Content-Type'}
    if request.method=='OPTIONS':return ('',204,cors)
    try:
        if set(request.args)-{'ra','dec','size','_'}:raise ValueError()
        ra=float(request.args['ra']);dec=float(request.args['dec'])
        if not math.isfinite(ra) or not math.isfinite(dec) or not 0<=ra<360 or not -90<=dec<=90:raise ValueError()
        params={'ra':ra,'dec':dec}
        if request.path.endswith('/pawnstars'):
            size=sr.bounded_float(request.args.get('size',120),'Finder image size',32,4096)
            params['size']=size
        from urllib.parse import urlencode
        data=json.loads(inspector.remote_text('http://byw.tools/'+request.path.rsplit('/',1)[-1]+'?'+urlencode(params),limit=1_000_000))
        return jsonify(data),200,cors
    except (ValueError,KeyError,sr.ReviewError):return jsonify(error='Invalid public survey coordinates.'),400,cors
    except Exception:return jsonify(error='WiseView public lookup unavailable.'),502,cors


def create_app():
    app=Flask(__name__,static_folder=None)
    app.config['MAX_CONTENT_LENGTH']=32768
    app.register_blueprint(findings)
    return app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8901)
    args=parser.parse_args()
    print('SUBLIME Findings Dashboard: http://127.0.0.1:%d/'%args.port,flush=True)
    print('Catalog queries, on-demand template fits, and individual duplicate review.',flush=True)
    from werkzeug.serving import WSGIRequestHandler
    class QuietHandler(WSGIRequestHandler):
        def log_request(self,*args,**kwargs):pass
        def log_error(self,*args,**kwargs):pass
    create_app().run(host='127.0.0.1',port=args.port,debug=False,threaded=True,request_handler=QuietHandler)


if __name__=='__main__':main()
