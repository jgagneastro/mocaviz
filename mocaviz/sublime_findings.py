"""SUBLIME findings dashboard, using the shared SPHEREx fitter.

Launch with python -B -m mocaviz.sublime_findings --port 8901.
No application import starts jobs, queries the database, or writes files.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import gzip
from hashlib import sha256
from io import BytesIO
import json
import math
import time
from pathlib import Path

import pymysql
from flask import Blueprint, Flask, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException

from . import spherex_review as sr
from . import spectrum_quality as sq
from . import sublime_findings_inspector as inspector
from . import sublime_findings_duplicates as duplicates
from . import sublime_findings_diagnostics as diagnostics
from . import sublime_findings_completeness as completeness

STATIC = Path(__file__).resolve().parent / 'static'
findings = Blueprint('sublime_findings', __name__)
SOURCES = {'sublime1': 'pcat_sublime_candidates', 'sublime2': 'pcat_sublime_candidates_v2',
           'sublime3c': 'pcat_sublime_candidates_v3c', 'sublime4': 'pcat_sublime_candidates_v4',
           'moshpit': 'pcat_moshpit_candidates', 'redmovers': 'pcat_catwise2020_red_movers'}
CLAIM_TABLES = ('pcat_byw_mar9_2026','pcat_schneider_claim_list_byw',
                'pcat_kirkpatrick_yadu_2026_claim','pcat_azul_byw_sample_jul16_2026')
CLAIM_TOKENS = ('yadu', 'tom', 'bickle', 'sarah', 'azul', 'eastonh')
MAX_OBJECTS = 100000
LANES = ('spiff', 'spiffstacker', 'sublimeaperture')
LANE_CONFIG = {lane: sr.LANES[lane] for lane in LANES}
GOOD_QUALITY = sq.GOOD
GOOD_CANDIDATE_QUALITY = (*GOOD_QUALITY, 'good_candidate')
QUALITY_CLASSES = {
    'good': GOOD_CANDIDATE_QUALITY,
    'one_good': GOOD_QUALITY,
    'all_good': GOOD_QUALITY,
    'all_good_candidate': GOOD_CANDIDATE_QUALITY,
}
ALL_QUALITY = frozenset(('all_good', 'all_good_candidate'))
TYPE_LANE_ORDER = ('spiffstacker', 'spiff', 'sublimeaperture')
TYPE_QUALITY_ORDER = (
    ('good', 'peculiar_ucd', 'good_reddened'),
    ('contaminated_ucd', 'good_plus_star'),
    ('good_candidate',),
    ('incomplete_but_promising', 'late_m', 'weird'),
)
NUMERIC = {'min_spt', 'max_spt', 'min_detection_snr', 'max_detection_snr', 'min_cnn', 'max_cnn',
           'min_snr', 'max_snr', 'min_motion', 'max_motion', 'min_cutout',
           'min_spiff_spt', 'max_spiff_spt', 'min_spiffstacker_spt', 'max_spiffstacker_spt',
           'min_sublimeaperture_spt', 'max_sublimeaperture_spt', 'min_parallax_snr',
           'min_w2', 'max_w2', 'min_chi2', 'max_chi2'}
QUALITY_SWITCHES = {name: 'apply_known_'+name for name in ('detection', 'quality', 'snr', 'motion', 'cutout', 'chi2', *LANES)}
TRI = ('known_candidate', 'byw', 'byw_claim', 'yadu', 'azul', 'smdet', 'known')
TEXT = {'cnn_classes', 'motion_classes', 'cutout_classes'} | {
    prefix + lane for prefix in ('include_', 'exclude_') for lane in LANES}


def parse_filters(raw):
    if not isinstance(raw, dict):
        raise sr.ReviewError('Filters must be an object.')
    allowed = NUMERIC | set(TRI) | TEXT | set(QUALITY_SWITCHES.values()) | {'sublime3c_pass_only', 'sources', 'spt_source', 'snr_lane', 'duplicates', 'cutout_policy', 'distance_mode', 'synthetic_lane', 'quality_any'}
    if set(raw) - allowed:
        raise sr.ReviewError('Unknown dashboard filter.')
    out = dict(raw)
    out.setdefault('sublime3c_pass_only', True)
    if not isinstance(out['sublime3c_pass_only'], bool):
        raise sr.ReviewError('SUBLIME3C selection switch must be boolean.')
    for key in QUALITY_SWITCHES.values():
        value = out.get(key, False)
        if not isinstance(value, bool):
            raise sr.ReviewError('Known-source quality switches must be boolean.')
        out[key] = value
    sources = out.get('sources', [*SOURCES, 'other'])
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
        out.setdefault(key, 'either')
        if out[key] not in ('yes', 'no', 'either'):
            raise sr.ReviewError('Membership filters must be yes, no, or either.')
    defaults = {'spt_source':'best', 'snr_lane':'spiffstacker', 'duplicates':'exclude',
                'cutout_policy':'all', 'distance_mode':'astrometric', 'synthetic_lane':'any', 'quality_any':'good'}
    options = {'spt_source': ('best', 'sublime2', 'sublime3c', 'adopted', 'published', *LANES), 'snr_lane': LANES,
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
    published="d.public_adopted=1 AND d.photometric_estimate=0 AND d.ignored=0 AND d.spectral_type_number>=0"
    return '('+(' OR '.join((
        '(SELECT d.id FROM data_spectral_types d WHERE d.moca_oid='+oid+' AND '+published+' LIMIT 1) IS NOT NULL',
        "EXISTS (SELECT 1 FROM pcat_duplicated_vetting dup JOIN data_spectral_types d ON d.moca_oid=dup.moca_oid WHERE dup.classification='y' AND dup.potential_duplicated_moca_oid="+oid+' AND '+published+')',
        "EXISTS (SELECT 1 FROM pcat_duplicated_vetting dup JOIN data_spectral_types d ON d.moca_oid=dup.potential_duplicated_moca_oid WHERE dup.classification='y' AND dup.moca_oid="+oid+' AND '+published+')'
    )))+')'


def protected_expression(alias='mo'):
    """Same known/candidate/claim membership used by the browser's color classes."""
    oid = alias+'.moca_oid'
    terms = [known_expression(alias),
             '(SELECT d.id FROM data_spectral_types d WHERE d.moca_oid='+oid+
             ' AND d.public_adopted=1 AND d.photometric_estimate=1 AND d.ignored=0 AND d.spectral_type_number>=0 LIMIT 1) IS NOT NULL']
    for table in CLAIM_TABLES:
        terms.append('(SELECT 1 FROM '+table+' c WHERE c.moca_oid='+oid+' LIMIT 1) IS NOT NULL')
    terms.append("EXISTS (SELECT 1 FROM mechanics_all_designations c WHERE c.moca_oid="+oid+" AND c.designation LIKE 'SMDET%%')")
    return '('+' OR '.join(terms)+')'


def protected_source(row):
    return any(row.get(key) for key in ('known','known_candidate','byw','byw_claim','yadu','azul','smdet'))


def apply_quality(row, filters, group):
    return not protected_source(row) or filters[QUALITY_SWITCHES[group]]


def lane_reviews(cfg, canonical):
    return sq.reviews_sql(cfg['table'], cfg['pack'], canonical)


def quality_condition(mode, oid='mo.moca_oid', *, canonical=True):
    if mode == 'any':
        return '1=1'
    passing, incomplete = [], []
    labels = QUALITY_CLASSES.get(mode)
    for cfg in LANE_CONFIG.values():
        source = lane_reviews(cfg, canonical)
        match = f" AND LOWER(q.classification) IN ({sq.labels_sql(labels)})" if labels else ''
        passing.append(f"EXISTS (SELECT 1 FROM {source} q WHERE q.moca_oid={oid}{match})")
        if mode in ALL_QUALITY:
            incomplete.append(f"NOT EXISTS (SELECT 1 FROM moca_spectra s LEFT JOIN {source} q ON q.moca_specid=s.moca_specid "
                f"WHERE s.moca_oid={oid} AND s.moca_specpackid={cfg['pack']} AND {sq.displayable_sql('s','q')} "
                f"AND (q.classification IS NULL OR LOWER(q.classification) NOT IN ({sq.labels_sql(labels)})))")
    any_match = '('+' OR '.join(passing)+')'
    return ('NOT ' if mode == 'unreviewed' else '') + ' AND '.join([any_match,*incomplete])


def rank_sql(column):
    groups = [f"WHEN LOWER({column}) IN ({sq.labels_sql(labels)}) THEN {rank}"
              for rank,labels in enumerate(TYPE_QUALITY_ORDER)]
    return 'CASE '+' '.join(groups)+' ELSE 99 END'


def possible_types_sql(f):
    # A conservative prefilter for objects that can meet the selected type minimum.
    if f['min_spt'] is None:
        return None
    threshold = str(float(f['min_spt']))
    if f['spt_source']=='published':
        candidates='SELECT d.moca_oid FROM data_spectral_types d WHERE d.public_adopted=1 AND d.photometric_estimate=0 AND d.spectral_type_number>='+threshold
    elif f['spt_source']=='adopted':
        candidates='SELECT d.moca_oid FROM data_spectral_types d WHERE d.adopted=1 AND d.ignored=0 AND d.spectral_type_number>='+threshold
    elif f['spt_source'] in LANES:
        methods=','.join("'"+m+"'" for m in LANE_CONFIG[f['spt_source']]['methods'])
        candidates='SELECT DISTINCT d.moca_oid FROM data_spectral_types d WHERE d.ignored=0 AND d.calculation_method IN ('+methods+') AND d.spectral_type_number>='+threshold
    elif f['spt_source']=='sublime3c':
        candidates='SELECT DISTINCT moca_oid FROM pcat_sublime_candidates_v3c WHERE autotype_spectral_type_number>='+threshold
    elif f['spt_source']=='sublime2':
        candidates='SELECT DISTINCT moca_oid FROM pcat_sublime_candidates_v2 WHERE autotype_spectral_type_number>='+threshold
    else:
        eligible = (
            'd.adopted=1 AND d.photometric_estimate=0',
            'd.public_adopted=1',
            'd.calculation_method IN ('+','.join("'"+method+"'" for lane in LANE_CONFIG.values() for method in lane['methods'])+')',
        )
        candidates = ' UNION '.join(
            'SELECT d.moca_oid FROM data_spectral_types d WHERE d.ignored=0 AND d.spectral_type_number>='
            + threshold + ' AND '+predicate for predicate in eligible
        )
    return candidates


def reviewed_candidate_sql(f):
    """Select review matches and the possible exemptions before looking up types."""
    if f['quality_any'] not in QUALITY_CLASSES and f['quality_any']!='reviewed':
        return None
    classes = QUALITY_CLASSES.get(f['quality_any'])
    quality_where = ' WHERE LOWER(classification) IN ('+','.join("'"+c+"'" for c in classes)+')' if classes else ''
    seeds = ['SELECT DISTINCT moca_oid FROM '+lane_reviews(cfg,f.get('_canonical',True))+' q'+quality_where for cfg in LANE_CONFIG.values()]
    if not f['apply_known_quality']:
        types = possible_types_sql(f)
        if types is None:
            # Without a type threshold, seed from the catalogues to avoid sending all public IDs.
            return None
        seeds += [
            'SELECT typed.moca_oid FROM ('+types+') typed WHERE (SELECT id FROM data_spectral_types '
            'WHERE moca_oid=typed.moca_oid AND public_adopted=1 AND ignored=0 AND spectral_type_number>=0 LIMIT 1) IS NOT NULL',
            "SELECT moca_oid FROM pcat_duplicated_vetting WHERE classification='y'",
            "SELECT potential_duplicated_moca_oid FROM pcat_duplicated_vetting WHERE classification='y'",
            *('SELECT moca_oid FROM '+table for table in CLAIM_TABLES),
            "SELECT moca_oid FROM mechanics_all_designations WHERE designation LIKE 'SMDET%%'",
        ]
    return ' UNION '.join(seeds)


def selected_sql(f, candidate_ids=None, *, counts_only=False):
    """Retrieve ranked types and provenance for the requested catalog sample."""
    bounded = candidate_ids is not None
    pass_only = f['sublime3c_pass_only']
    pass_prefix = "SUBSTR(status,1,47)='AUTO_SELECTION_PASS[native_signed_student4_v1];'"
    catalog_tests = []
    for source, table in SOURCES.items():
        if source in f['sources']:
            match = '(SELECT 1 FROM `'+table+'` WHERE moca_oid=mo.moca_oid'
            catalog_tests.append(match + (' AND '+pass_prefix if source=='sublime3c' and pass_only else '') + ' LIMIT 1) IS NOT NULL')
    other_tests = [
        '(SELECT private_type.id FROM data_spectral_types private_type WHERE private_type.moca_oid=mo.moca_oid '
        'AND private_type.adopted=1 AND private_type.ignored=0 AND private_type.spectral_type_number>=0 LIMIT 1) IS NOT NULL',
        'NOT '+known_expression('mo'),
        *(('(SELECT 1 FROM `'+table+'` WHERE moca_oid=mo.moca_oid LIMIT 1) IS NULL' if bounded
           else 'mo.moca_oid NOT IN (SELECT c.moca_oid FROM `'+table+'` c WHERE c.moca_oid IS NOT NULL)')
          for table in SOURCES.values()),
    ]
    if bounded:
        origin, sample_join = 'moca_objects mo', ''
    else:
        unions = [
            'SELECT DISTINCT moca_oid, 0 AS is_other FROM `'+table+'` WHERE moca_oid IS NOT NULL'
            + (' AND '+pass_prefix if source=='sublime3c' and pass_only else '')
            for source, table in SOURCES.items() if source in f['sources']
        ]
        if 'other' in f['sources']:
            methods = ','.join("'" + method + "'" for cfg in LANE_CONFIG.values() for method in cfg['methods'])
            seed = ('SELECT DISTINCT moca_oid FROM data_spectral_types WHERE ignored=0 '
                    'AND spectral_type_number IS NOT NULL AND calculation_method IN (' + methods + ')')
            unions.append('SELECT mo.moca_oid, 1 AS is_other FROM ('+seed+') eligible '
                          'JOIN moca_objects mo ON mo.moca_oid=eligible.moca_oid WHERE mo.ignored=0 AND '
                          + ' AND '.join(other_tests))
        origin = '(' + ' UNION '.join(unions) + ') sample'
        sample_join = 'JOIN moca_objects mo ON mo.moca_oid=sample.moca_oid'
    type_cols, type_joins = [], []
    for lane, config in LANE_CONFIG.items():
        methods = ','.join("'" + m + "'" for m in config['methods'])
        source = lane_reviews(config, f.get('_canonical',True))
        bounds = []
        for prefix, op in (('min','>='),('max','<=')):
            limits = [f[prefix+'_'+lane+'_spt']]
            if f['spt_source'] == lane:
                limits.append(f[prefix+'_spt'])
            for limit in limits:
                if limit is not None:
                    bounds.append(' AND t.spectral_type_number'+op+str(float(limit)))
        type_joins.append(f"LEFT JOIN data_spectral_types t_{lane} ON t_{lane}.id=("
                         f"SELECT t.id FROM data_spectral_types t JOIN {source} q ON q.moca_specid=t.moca_specid "
                         f"WHERE t.moca_oid=mo.moca_oid AND t.ignored=0 AND t.calculation_method IN ({methods}) "
                         f"AND LOWER(q.classification) IN ({sq.labels_sql(sq.USABLE)}){''.join(bounds)} "
                         f"ORDER BY {rank_sql('q.classification')},t.id DESC LIMIT 1)")
        type_cols.append('t_' + lane + '.spectral_type_number AS ' + lane + '_spt')
    type_joins.append('LEFT JOIN data_spectral_types ta ON ta.id=(SELECT MAX(d.id) FROM data_spectral_types d WHERE d.moca_oid=mo.moca_oid AND d.adopted=1 AND d.ignored=0)')
    expressions = {'sublime3c':'p3.autotype_spectral_type_number', 'sublime2':'p2.autotype_spectral_type_number', 'adopted':'ta.spectral_type_number','published':'tp.spectral_type_number'}
    expressions.update({lane:'t_' + lane + '.spectral_type_number' for lane in LANES})
    type_joins.append('LEFT JOIN data_spectral_types tp ON tp.id=(SELECT MAX(d.id) FROM data_spectral_types d WHERE d.moca_oid=mo.moca_oid AND d.public_adopted=1 AND d.photometric_estimate=0 AND d.ignored=0)')
    type_joins.append('LEFT JOIN data_spectral_types tc ON tc.id=(SELECT MAX(d.id) FROM data_spectral_types d WHERE d.moca_oid=mo.moca_oid AND d.public_adopted=1 AND d.photometric_estimate=1 AND d.ignored=0)')
    type_choices = [
        ('ta.spectral_type_number IS NOT NULL AND ta.photometric_estimate=0 AND ta.calculation_method IS NULL', 'ta.spectral_type_number', 'adopted'),
        ('tp.spectral_type_number IS NOT NULL AND tp.calculation_method IS NULL', 'tp.spectral_type_number', 'published'),
    ]
    for lane in TYPE_LANE_ORDER:
        source = lane_reviews(LANE_CONFIG[lane],f.get('_canonical',True))
        type_joins.append(f"LEFT JOIN {source} quality_{lane} ON quality_{lane}.moca_specid=t_{lane}.moca_specid")
    for classes in TYPE_QUALITY_ORDER:
        accepted = ','.join("'"+value+"'" for value in classes)
        for lane in TYPE_LANE_ORDER:
            value = expressions[lane]
            condition = value+' IS NOT NULL AND LOWER(TRIM(quality_'+lane+'.classification)) IN ('+accepted+')'
            type_choices.append((condition, value, lane))
    for lane in TYPE_LANE_ORDER:
        type_choices.append((expressions[lane]+' IS NOT NULL', expressions[lane], lane))
    type_choices.append(('tp.spectral_type_number IS NOT NULL', 'tp.spectral_type_number', 'published'))
    type_choices.append(('tc.spectral_type_number IS NOT NULL', 'tc.spectral_type_number', 'published_candidate'))
    expressions['best'] = 'CASE '+' '.join('WHEN '+condition+' THEN '+value for condition,value,_ in type_choices)+' ELSE NULL END'
    best_source = 'CASE '+' '.join("WHEN "+condition+" THEN '"+lane+"'" for condition,_,lane in type_choices)+' ELSE NULL END'
    spt = expressions[f['spt_source']]
    # A union of potentially passing types safely covers the preferred-type cut.
    # Apply it before catalogue joins to avoid hundreds of thousands of lookups.
    preselect = ''
    if not bounded and (candidates := possible_types_sql(f)):
        preselect='JOIN ('+candidates+') typed ON typed.moca_oid=sample.moca_oid'
    where, params = ['mo.ignored=0'], []
    if candidate_ids is not None:
        where.append('mo.moca_oid IN ('+','.join(['%s']*len(candidate_ids))+')')
        params.extend(candidate_ids)
    lane_types = 'COALESCE(' + ','.join(expressions[lane] for lane in LANES) + ') IS NOT NULL'
    if bounded:
        if 'other' in f['sources']:
            catalog_tests.append('('+' AND '.join([*other_tests,lane_types])+')')
        where.append('('+' OR '.join(catalog_tests)+')')
    elif 'other' in f['sources']:
        where.append('(sample.is_other=0 OR '+lane_types+')')
    def exempt(condition, group):
        return condition if f[QUALITY_SWITCHES[group]] else '('+protected_expression()+' OR ('+condition+'))'
    def bound(expr, low, high=None, group=None):
        if f.get(low) is not None:
            where.append(exempt(expr + '>=%s', group) if group else expr + '>=%s'); params.append(f[low])
        if high and f.get(high) is not None:
            where.append(exempt(expr + '<=%s', group) if group else expr + '<=%s'); params.append(f[high])
    if f['quality_any']!='any':
        where.append(exempt('('+quality_condition(f['quality_any'],canonical=f.get('_canonical',True))+')', 'quality'))
    if f['duplicates']!='either':
        where.append(('NOT ' if f['duplicates']=='exclude' else '')+"EXISTS (SELECT 1 FROM pcat_duplicated_vetting dup WHERE dup.potential_duplicated_moca_oid=mo.moca_oid AND dup.classification='y')")
    for lane,cfg in LANE_CONFIG.items():
        for prefix,negative in (('include_',False),):
            classes=f[prefix+lane]
            if not classes:continue
            values=[c for c in classes if c!='none']
            conditions=[]
            if values:
                conditions.append('EXISTS (SELECT 1 FROM '+lane_reviews(cfg,f.get('_canonical',True))+' q WHERE q.moca_oid=mo.moca_oid AND LOWER(q.classification) IN ('+','.join(['%s']*len(values))+'))')
                params.extend(values)
            if 'none' in classes:conditions.append('NOT EXISTS (SELECT 1 FROM '+lane_reviews(cfg,f.get('_canonical',True))+' q WHERE q.moca_oid=mo.moca_oid)')
            where.append(exempt(('NOT ' if negative else '')+'('+' OR '.join(conditions)+')', lane))
    if f['min_motion'] is not None or f['max_motion'] is not None:
        motion=['w.moca_oid=mo.moca_oid']
        for key,op in (('min_motion','>='),('max_motion','<=')):
            if f[key] is not None:motion.append('w.classification_integer'+op+'%s');params.append(f[key])
        motion_review = 'EXISTS (SELECT 1 FROM pcat_wiseview_visual_vetting w WHERE ' + ' AND '.join(motion) + ')'
        where.append(exempt(motion_review, 'motion'))
    bound(spt, 'min_spt', 'max_spt')
    for lane in LANES:
        bound(expressions[lane], 'min_' + lane + '_spt', 'max_' + lane + '_spt')
    bound('COALESCE(p2.detection_snr,p1.detection_snr)', 'min_detection_snr', 'max_detection_snr', 'detection')
    bound('p2.visual_nn_good_probability','min_cnn','max_cnn','detection')
    bound('p2.autotype_reduced_chi2','min_chi2','max_chi2','chi2')
    if f['cnn_classes']:
        classes=[c for c in f['cnn_classes'] if c!='none']
        terms=[]
        if classes:
            terms.append('LOWER(p2.visual_nn_classification) IN ('+','.join(['%s']*len(classes))+')')
            params.extend(classes)
        if 'none' in f['cnn_classes']:terms.append('p2.visual_nn_classification IS NULL')
        where.append(exempt('('+' OR '.join(terms)+')', 'detection'))
    projection = '''mo.moca_oid,mo.designation,
        CASE WHEN mo.designation LIKE 'SUBLIME3C %%' THEN COALESCE(p3.ra_deg,mo.ra) ELSE mo.ra END AS ra,
        CASE WHEN mo.designation LIKE 'SUBLIME3C %%' THEN COALESCE(p3.dec_deg,mo.`dec`) ELSE mo.`dec` END AS `dec`,mo.is_public,
        ''' + spt + ''' AS spt,''' + ','.join(type_cols) + ''',
        p2.autotype_spectral_type_number AS sublime2_spt,ta.spectral_type_number AS adopted_spt,tp.spectral_type_number AS published_spt,tc.spectral_type_number AS published_candidate_spt,
        ''' + best_source + ''' AS best_spt_source,
        p1.id IS NOT NULL AS sublime1,p2.id IS NOT NULL AS sublime2,p3.id IS NOT NULL AS sublime3c,
        p3.autotype_spectral_type_number AS sublime3c_spt,p3.status AS sublime3c_selection,
        p3.ra_deg AS sublime3c_ra,p3.dec_deg AS sublime3c_dec,
        p3.cnn_acceptance_probability AS sublime3c_cnn_acceptance,p3.median_raw_snr AS sublime3c_median_snr,
        COALESCE(p2.detection_snr,p1.detection_snr) AS detection_snr,
        p2.detection_snr AS sublime2_detection_snr,
        p2.visual_nn_good_probability AS cnn,p2.visual_nn_classification AS cnn_class,
        p2.autotype_reduced_chi2 AS chi2
        '''
    if counts_only:
        projection = "mo.moca_oid,tc.spectral_type_number AS published_candidate_spt"
    sql = "SELECT " + projection + '''
        FROM ''' + origin + ' ' + preselect + ' ' + sample_join + '''
        LEFT JOIN pcat_sublime_candidates p1 ON p1.id=(SELECT MAX(id) FROM pcat_sublime_candidates WHERE moca_oid=mo.moca_oid)
        LEFT JOIN pcat_sublime_candidates_v2 p2 ON p2.id=(SELECT MAX(id) FROM pcat_sublime_candidates_v2 WHERE moca_oid=mo.moca_oid)
        LEFT JOIN pcat_sublime_candidates_v3c p3 ON p3.id=(
            SELECT COALESCE(MAX(CASE WHEN ''' + pass_prefix + ''' THEN id END),MAX(id))
            FROM pcat_sublime_candidates_v3c WHERE moca_oid=mo.moca_oid)
        ''' + '\n'.join(type_joins) + '\n WHERE ' + ' AND '.join(where)
    # Apply the safety limit before sorting so the optimizer starts with eligible IDs.
    sql += ' LIMIT ' + str(MAX_OBJECTS + 1)
    return 'SELECT * FROM ('+sql+') ranked ORDER BY moca_oid', tuple(params)


def preferred_spectrum_lane(row):
    """Use the preferred type's reduction, or rank available spectra for literature types."""
    available = [lane for lane in TYPE_LANE_ORDER if row.get(lane+'_specid')]
    source = row.get('best_spt_source')
    if source in available:
        return source
    ranks = {label:rank for rank,group in enumerate(TYPE_QUALITY_ORDER) for label in group}
    return min(available, key=lambda lane:ranks.get(str(row.get(lane+'_quality') or '').strip().lower(), len(TYPE_QUALITY_ORDER)),
               default=None)


def enrich(cur, rows, *, count_filters=None):
    """Bound queries to selected IDs. Query only fields used by the count filters when supplied."""
    full = count_filters is None
    need_cutouts = full or count_filters['min_cutout'] is not None or count_filters['cutout_classes']
    canonical = sq.has_spectrum_reviews(cur)
    by_oid = {r['moca_oid']: r for r in rows}
    batch_size = 1000 if full else 4000
    for start in range(0, len(rows), batch_size):
        chunk = rows[start:start+batch_size]
        ids = tuple(r['moca_oid'] for r in chunk)
        ph = ','.join(['%s']*len(ids))
        for r in chunk:
            r.update(sublime4=False, moshpit=False, redmovers=False, byw=False, byw_claim=False, yadu=False, azul=False,
                     smdet=False, duplicate=False, known=False, known_candidate=False, cutout_scores=[], cutout_classes=[],
                     cutout_count=0, motion=None, motion_class=None, pmtot_masyr=None)
        tables = {'byw':'pcat_byw_mar9_2026',
                  'yadu':'pcat_kirkpatrick_yadu_2026_claim','azul':'pcat_azul_byw_sample_jul16_2026'}
        if full:
            for source in ('sublime4', 'moshpit', 'redmovers'):
                tables[source] = SOURCES[source]
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
        known_sql = '''SELECT DISTINCT moca_oid FROM data_spectral_types WHERE moca_oid IN (''' + ph + ''') AND public_adopted=1 AND photometric_estimate=0 AND ignored=0 AND spectral_type_number>=0
        UNION SELECT dup.potential_duplicated_moca_oid FROM pcat_duplicated_vetting dup JOIN data_spectral_types d ON d.moca_oid=dup.moca_oid AND d.public_adopted=1 AND d.photometric_estimate=0 AND d.ignored=0 AND d.spectral_type_number>=0 WHERE dup.classification='y' AND dup.potential_duplicated_moca_oid IN (''' + ph + ''')
        UNION SELECT dup.moca_oid FROM pcat_duplicated_vetting dup JOIN data_spectral_types d ON d.moca_oid=dup.potential_duplicated_moca_oid AND d.public_adopted=1 AND d.photometric_estimate=0 AND d.ignored=0 AND d.spectral_type_number>=0 WHERE dup.classification='y' AND dup.moca_oid IN (''' + ph + ')'
        for r in fetch(cur, known_sql, ids*3):
            by_oid[r['moca_oid']]['known'] = True
        for r in chunk:
            r['known_candidate'] = not r['known'] and r.get('published_candidate_spt') is not None and r['published_candidate_spt'] >= 0
        for r in fetch(cur, 'SELECT moca_oid,classification_integer,classification FROM pcat_wiseview_visual_vetting WHERE moca_oid IN (' + ph + ')', ids):
            by_oid[r['moca_oid']].update(motion=r['classification_integer'],motion_class=r['classification'])
        if full:
            for r in fetch(cur, 'SELECT id,moca_oid,pmtot_masyr FROM data_proper_motions WHERE moca_oid IN (' + ph + ')'
                           ' AND adopted=1 AND ignored=0 AND pmtot_masyr IS NOT NULL', ids):
                by_oid[r['moca_oid']].update(proper_motion_id=r['id'], pmtot_masyr=r['pmtot_masyr'])
        if need_cutouts:
            for r in fetch(cur, 'SELECT moca_oid,classification_integer,classification FROM pcat_spherex_cutout_visual_vetting WHERE moca_oid IN (' + ph + ') ORDER BY id', ids):
                target=by_oid[r['moca_oid']]
                target['cutout_count'] += 1
                target['cutout_scores'].append(r['classification_integer'])
                target['cutout_classes'].append(r['classification'])
        for row in chunk:
            row.update(spectra=[],review_labels={},unreviewed_active=False)
        for lane,cfg in LANE_CONFIG.items():
            source = lane_reviews(cfg,canonical)
            methods = sq.labels_sql(cfg['methods'])
            query = f"""SELECT s.moca_oid,s.moca_specid,s.ignored,s.median_snr_per_pix,q.classification,
                (SELECT t.spectral_type_number FROM data_spectral_types t WHERE t.moca_specid=s.moca_specid
                 AND t.ignored=0 AND t.calculation_method IN ({methods}) ORDER BY t.id DESC LIMIT 1) AS spt
                FROM moca_spectra s LEFT JOIN {source} q ON q.moca_specid=s.moca_specid
                WHERE s.moca_oid IN ({ph}) AND s.moca_specpackid=%s
                ORDER BY {rank_sql('q.classification')},s.moca_specid DESC"""
            for spec in fetch(cur,query,(*ids,cfg['pack'])):
                row=by_oid[spec['moca_oid']]
                label=(spec['classification'] or '').lower()
                if label:
                    labels=row['review_labels'].setdefault(lane,[])
                    if label not in labels: labels.append(label)
                elif not spec['ignored']:
                    row['unreviewed_active']=True
                if label not in sq.USABLE:
                    continue
                row['spectra'].append(dict(lane=lane,specid=spec['moca_specid'],quality=label,
                                           snr=spec['median_snr_per_pix'],spt=spec['spt']))
                if not row.get(lane+'_specid'):
                    row.update({lane+'_specid':spec['moca_specid'],lane+'_snr':spec['median_snr_per_pix'],
                                lane+'_quality':label,lane+'_ignored':False})
        for row in chunk:
            row['good_spectrum_count']=sum(spec['quality'] in GOOD_QUALITY for spec in row['spectra'])
            for lane,labels in row['review_labels'].items():
                row.setdefault(lane+'_quality',labels[0])
    if full:
        for row in rows:
            row['preferred_spectrum_lane'] = preferred_spectrum_lane(row)
    return rows


def passes(r, f):
    if apply_quality(r, f, 'quality'):
        quality=([label for labels in r['review_labels'].values() for label in labels] if 'review_labels' in r else
                 [str(r.get(lane+'_quality') or '').lower() for lane in LANES])
        mode=f['quality_any']
        if mode in ALL_QUALITY:
            available=[str(r.get(lane+'_quality') or '').lower() for lane in LANES
                       if r.get(lane+'_specid') and not r.get(lane+'_ignored')]
            if 'spectra' in r:
                available=[spec['quality'] for spec in r['spectra']]
                if r['unreviewed_active']:return False
            if not available or not all(v in QUALITY_CLASSES[mode] for v in available):return False
        elif mode in QUALITY_CLASSES and not any(v in QUALITY_CLASSES[mode] for v in quality):return False
        if mode=='reviewed' and not any(quality):return False
        if mode=='unreviewed' and any(quality):return False
    for key in TRI:
        if f[key] != 'either' and bool(r.get(key)) != (f[key]=='yes'):return False
    if f['duplicates'] != 'either' and bool(r['duplicate']) != (f['duplicates']=='only'):return False
    numeric_cuts=[]
    if apply_quality(r, f, 'snr'):
        if 'spectra' in r and (f['min_snr'] is not None or f['max_snr'] is not None):
            if not any(spec['lane']==f['snr_lane'] and spec['snr'] is not None
                       and (f['min_snr'] is None or spec['snr']>=f['min_snr'])
                       and (f['max_snr'] is None or spec['snr']<=f['max_snr']) for spec in r['spectra']):return False
        else:
            numeric_cuts.append((f['snr_lane']+'_snr','min_snr','max_snr'))
    if apply_quality(r, f, 'motion'):
        numeric_cuts.append(('motion','min_motion','max_motion'))
        if f['motion_classes'] and str(r.get('motion_class') or 'none').lower() not in f['motion_classes']:return False
    for field,lo,hi in numeric_cuts:
        val=r.get(field)
        if f[lo] is not None and (val is None or val < f[lo]):return False
        if f[hi] is not None and (val is None or val > f[hi]):return False
    for lane in LANES:
        if not apply_quality(r, f, lane):continue
        quality = str(r.get(lane+'_quality') or 'none').lower()
        labels=set(r.get('review_labels',{}).get(lane,[quality]))
        usable=labels.intersection(sq.USABLE)
        effective=usable or labels
        if f['include_'+lane] and not effective.intersection(f['include_'+lane]):return False
        if effective.issubset(f['exclude_'+lane]):return False
    if apply_quality(r, f, 'cutout'):
        scores=r['cutout_scores']
        if f['min_cutout'] is not None:
            checks=[s is not None and s>=f['min_cutout'] for s in scores]
            if not checks or not (all(checks) if f['cutout_policy']=='all' else any(checks)):return False
        if f['cutout_classes']:
            checks=[str(s).lower() in f['cutout_classes'] for s in r['cutout_classes']]
            if not checks:checks=['none' in f['cutout_classes']]
            if not (all(checks) if f['cutout_policy']=='all' else any(checks)):return False
    return True


def trigonometric_magnitudes(row):
    """Keep parallax-based luminosities separate from optional photometric distances."""
    distance = uncertainty = None
    adopted = row.get('adopted_distance_pc')
    for key in ('trigonometric_distance_source', 'trigonometric_distance_id', 'trigonometric_parallax_id'):
        row.pop(key, None)
    if row.get('adopted_distance_kind') == 'trigonometric' and adopted is not None and adopted > 0:
        distance = float(adopted)
        uncertainty = row.get('adopted_distance_unc')
        row['trigonometric_distance_source'] = 'adopted parallax-linked distance'
        row['trigonometric_distance_id'] = row.get('adopted_distance_id')
    elif row.get('parallax') is not None and row['parallax'] > 0:
        parallax = float(row['parallax'])
        distance = 1000 / parallax
        error = row.get('parallax_unc')
        uncertainty = 1000 * float(error) / parallax**2 if error is not None and error >= 0 else None
        row['trigonometric_distance_source'] = 'inverse adopted parallax'
        row['trigonometric_parallax_id'] = row.get('parallax_id')
    row['trigonometric_distance_pc'] = distance
    row['trigonometric_distance_unc'] = uncertainty
    for band in ('gaia_g', 'w2'):
        magnitude, error = row.get(band), row.get(band+'_unc')
        key = 'M_'+band+'_trig'
        row[key] = float(magnitude)-5*math.log10(distance)+5 if magnitude is not None and distance else None
        row[key+'_unc'] = (math.hypot(float(error), 5/math.log(10)*float(uncertainty)/distance)
                          if row[key] is not None and error is not None and error >= 0
                          and uncertainty is not None and uncertainty >= 0 else None)
    return row


def adopted_parallaxes(cur, ids, ph):
    return fetch(cur, 'SELECT id,moca_oid,parallax_mas,parallax_mas_unc FROM data_parallaxes WHERE moca_oid IN ('+ph+') AND adopted=1 AND ignored=0 AND parallax_mas>0',ids)


def w2_measurements(cur, ids, ph, *, measured_only=False):
    selection = "p.is_synthetic=0" if measured_only else """(p.is_synthetic=0 OR
        (p.is_synthetic=1 AND ((s.moca_specpackid IN (55,62,76) )
          OR (p.moca_specid IS NULL AND p.calculation_method='spherex_w2_synth'))))"""
    columns = "p.moca_oid,p.magnitude"
    join = ""
    if not measured_only:
        columns = "p.id," + columns + ",p.magnitude_unc,p.is_synthetic,p.moca_specid,p.calculation_method,p.origin,s.moca_specpackid"
        join = "LEFT JOIN moca_spectra s ON s.moca_specid=p.moca_specid"
    return fetch(cur, "SELECT "+columns+" FROM data_photometry p "+join+"""
        WHERE p.moca_oid IN ("""+ph+""") AND p.system_band_simple='W2' AND p.ignored=0 AND p.magnitude IS NOT NULL
        AND """+selection+""" ORDER BY p.adopted_simpleband DESC,p.adopted DESC,p.id DESC""", ids)


def passes_photometry(row, f):
    p, pu = row.get('parallax'), row.get('parallax_unc')
    row['parallax_snr'] = float(p)/float(pu) if p and pu and pu>0 else None
    if f['min_parallax_snr'] is not None and (row['parallax_snr'] is None or row['parallax_snr']<f['min_parallax_snr']):
        return False
    w2 = row.get('w2')
    return not any(f[key] is not None and (w2 is None or (w2<f[key] if key=='min_w2' else w2>f[key]))
                   for key in ('min_w2', 'max_w2'))


def count_photometry(cur, rows, f):
    parallax_cut = f['min_parallax_snr'] is not None
    w2_cut = f['min_w2'] is not None or f['max_w2'] is not None
    if not (parallax_cut or w2_cut):
        return rows
    by_oid = {row['moca_oid']: row for row in rows}
    for start in range(0, len(rows), 1000):
        ids = tuple(row['moca_oid'] for row in rows[start:start+1000])
        ph = ','.join(['%s']*len(ids))
        if parallax_cut:
            for p in adopted_parallaxes(cur, ids, ph):
                by_oid[p['moca_oid']].update(parallax=p['parallax_mas'], parallax_unc=p['parallax_mas_unc'])
        if w2_cut:
            for p in w2_measurements(cur, ids, ph, measured_only=True):
                by_oid[p['moca_oid']].setdefault('w2', p['magnitude'])
    return [row for row in rows if passes_photometry(row, f)]


def photometry(cur, rows, f):
    by_oid={r['moca_oid']:r for r in rows}
    for start in range(0,len(rows),1000):
        chunk=rows[start:start+1000]
        ids=tuple(r['moca_oid'] for r in chunk); ph=','.join(['%s']*len(ids))
        for r in adopted_parallaxes(cur, ids, ph):
            by_oid[r['moca_oid']].update(parallax_id=r['id'],parallax=r['parallax_mas'],parallax_unc=r['parallax_mas_unc'],
                 distance_pc=1000/float(r['parallax_mas']),distance_kind='parallax')
        for r in fetch(cur, 'SELECT id,moca_oid,distance_pc,distance_pc_unc,photometric_estimate,parallax_id FROM data_distances'
                       ' WHERE moca_oid IN ('+ph+') AND adopted=1 AND ignored=0 AND distance_pc>0', ids):
            obj=by_oid[r['moca_oid']]
            photometric=bool(r['photometric_estimate'])
            kind='photometric' if photometric else ('trigonometric' if r['parallax_id'] is not None else 'nonphotometric')
            obj.update(adopted_distance_id=r['id'], adopted_distance_pc=r['distance_pc'],
                       adopted_distance_unc=r.get('distance_pc_unc'), adopted_distance_kind=kind)
            if not obj.get('distance_pc') and (not photometric or f['distance_mode']=='include_photometric'):
                obj.update(distance_id=r['id'],distance_pc=r['distance_pc'],distance_kind='photometric' if photometric else 'nonphotometric')
        gaia = fetch(cur, "SELECT id,moca_oid,moca_psid,magnitude,magnitude_unc FROM data_photometry"
                     " WHERE moca_oid IN ("+ph+") AND moca_psid IN ('gaiadr3_gmag','gaiadr2_gmag','gaiadr1_gmag')"
                     " AND ignored=0 AND is_synthetic=0 AND magnitude IS NOT NULL"
                     " ORDER BY adopted_simpleband DESC,adopted DESC,"
                     " CASE moca_psid WHEN 'gaiadr3_gmag' THEN 0 WHEN 'gaiadr2_gmag' THEN 1 ELSE 2 END,id DESC", ids)
        for measurement in gaia:
            obj = by_oid[measurement['moca_oid']]
            if obj.get('gaia_g') is not None:continue
            obj.update(gaia_g=measurement['magnitude'], gaia_g_unc=measurement['magnitude_unc'],
                       gaia_g_id=measurement['id'], gaia_g_psid=measurement['moca_psid'],
                       gaia_g_source='data_photometry')
        missing_gaia = tuple(oid for oid in ids if by_oid[oid].get('gaia_g') is None)
        if missing_gaia:
            missing_ph = ','.join(['%s']*len(missing_gaia))
            for measurement in fetch(cur, 'SELECT id,moca_oid,source_id,phot_g_mean_mag,phot_g_mean_flux_over_error'
                                     ' FROM cat_gaiadr3 WHERE moca_oid IN ('+missing_ph+') AND phot_g_mean_mag IS NOT NULL', missing_gaia):
                signal = measurement['phot_g_mean_flux_over_error']
                error = 2.5/math.log(10)/float(signal) if signal is not None and signal > 0 else None
                by_oid[measurement['moca_oid']].update(gaia_g=measurement['phot_g_mean_mag'], gaia_g_unc=error,
                    gaia_g_catalog_id=measurement['id'], gaia_g_source_id=measurement['source_id'],
                    gaia_g_psid='gaiadr3_gmag', gaia_g_source='cat_gaiadr3')
        data=w2_measurements(cur,ids,ph)
        for p in data:
            obj=by_oid[p['moca_oid']]
            key='synthetic_w2' if p['is_synthetic'] else 'w2'
            # Synthetic measurements follow the selected reduction lane when present.
            if p['is_synthetic'] and f['synthetic_lane'] != 'any' and p['moca_specpackid'] != LANE_CONFIG[f['synthetic_lane']]['pack']: continue
            if p['is_synthetic'] and 'spectra' in obj:
                extraction=next((s for s in obj['spectra'] if s['specid']==p['moca_specid']),None)
                if extraction is None:continue
                extraction.setdefault('synthetic_w2',p['magnitude'])
                extraction.setdefault('synthetic_w2_id',p['id'])
                extraction.setdefault('synthetic_w2_unc',p['magnitude_unc'])
            if key in obj: continue
            obj[key]=p['magnitude'];obj[key+'_unc']=p['magnitude_unc'];obj[key+'_id']=p['id']
            if p['is_synthetic']:
                obj['synthetic_w2_pack']=p['moca_specpackid'];obj['synthetic_w2_specid']=p['moca_specid'];obj['synthetic_w2_method']=p['calculation_method'] or p['origin']
    result=[]
    for r in rows:
        r['other']=not any(r.get(s) for s in SOURCES) and not r.get('known')
        r['samples']=[s for s in (*SOURCES,'other') if r.get(s)]
        r['spt_source']=r['best_spt_source'] if f['spt_source']=='best' else f['spt_source']
        p,pu=r.get('parallax'),r.get('parallax_unc')
        if not passes_photometry(r, f):continue
        trigonometric_magnitudes(r)
        d=r.get('distance_pc')
        for key in ('w2','synthetic_w2'):
            mag=r.get(key)
            r['M_'+key]=float(mag)-5*math.log10(float(d))+5 if mag is not None and d and d>0 else None
            err=r.get(key+'_unc')
            de=5/math.log(10)*float(pu)/float(p) if p and pu and pu>0 else None
            r['M_'+key+'_unc']=math.hypot(float(err),de) if err is not None and de is not None else None
        for spec in r.get('spectra',[]):
            err=spec.get('synthetic_w2_unc')
            if err is not None and de is not None:
                spec['absolute_w2_unc']=math.hypot(float(err),de)
        if r.get('w2') is not None and r.get('synthetic_w2') is not None:
            r['w2_difference']=float(r['synthetic_w2'])-float(r['w2'])
        else:r['w2_difference']=None
        result.append(r)
    return result


def selected_rows(cur, f, *, counts_only=False):
    f=dict(f,_canonical=sq.has_spectrum_reviews(cur))
    seed_sql = reviewed_candidate_sql(f)
    if seed_sql is None:
        batches = (None,)
    else:
        ids = [row['moca_oid'] for row in fetch(cur,seed_sql) if row['moca_oid'] is not None]
        # Bound the per-query joins and expression caches on MariaDB.
        batches = (ids[start:start+2000] for start in range(0,len(ids),2000))
    rows = []
    for batch in batches:
        sql,params=selected_sql(f,batch,counts_only=True) if counts_only else selected_sql(f,batch)
        rows.extend(fetch(cur,sql,params))
        if len(rows)>MAX_OBJECTS:
            raise sr.ReviewError('More than 100,000 objects pass the initial sample/type cuts. Raise the minimum spectral type or select fewer samples; no partial dashboard was produced.',422)
    return rows


def load(cur,f):
    rows=selected_rows(cur,f)
    rows=list({r['moca_oid']:r for r in rows}.values())
    preliminary=len(rows)
    rows=[r for r in enrich(cur,rows) if passes(r,f)]
    rows=photometry(cur,rows,f)
    rows.sort(key=lambda r:(r['spt'] is None,-float(r['spt'] or 0),r['moca_oid']))
    return rows,preliminary


def count_rows(cur, f):
    rows = list({r['moca_oid']: r for r in selected_rows(cur, f, counts_only=True)}.values())
    eligible = [r for r in enrich(cur, rows, count_filters=f) if passes(r, f)]
    return count_photometry(cur, eligible, f)


def count_groups(rows):
    # Group IDs by the inputs to the existing browser classifier, so a quick
    # refresh uses exactly the same labels and precedence as a full load.
    tags = ('known', 'known_candidate', 'byw', 'motion', 'motion_class',
            *(lane+'_quality' for lane in LANES))
    groups = {}
    for row in rows:
        key = (bool(row.get('known')), bool(row.get('known_candidate')),
               any(row.get(flag) for flag in ('byw', 'byw_claim', 'yadu', 'azul', 'smdet')),
               row.get('motion'), row.get('motion_class'),
               *(row.get(lane+'_quality') for lane in LANES))
        groups.setdefault(key, []).append(row['moca_oid'])
    return [{**dict(zip(tags, flags)), 'oids': ids} for flags, ids in groups.items()]


def demo_rows(f):
    rows=[]
    for i in range(180):
        r={'moca_oid':1001+i,'designation':'Demo J%04d'%i,'ra':(i*137.508)%360,'dec':-78+(i*19)%156,
           'spt':10+(i%24)*.9,'sublime1':i%5==0,'sublime2':i%5==1,'sublime3c':i%4==0,
           'redmovers':i%5==2,'sublime4':i%5==3,'moshpit':i%5==4 or i%23==0,'other':False,
           'detection_snr':7+i%30,'cnn':.7+(i%29)/100,'cnn_class':'good',
           'best_spt_source':'spiffstacker','motion':3+i%4,'motion_class':'clear motion, red detection',
           'cutout_scores':[3,4],'cutout_classes':['Good centered on PSF but crowded','Good centered on PSF and isolated'],
           'cutout_count':2,'chi2':1+i/20,'is_public':0,
           'pmtot_masyr':None if i%7==0 else 20+(i*53)%780}
        for j,k in enumerate(TRI):r[k]=False if k=='known' else i%(j+3)==0
        r['known'] = i % 11 == 0
        r['known_candidate'] = not r['known'] and i % 13 == 0
        r['published_spt'] = r['spt'] if r['known'] else None
        r['published_candidate_spt'] = r['spt'] if r['known_candidate'] else None
        r['duplicate']=i%17==0
        for j,lane in enumerate(LANES):r.update({lane+'_quality':'good',lane+'_spt':r['spt'],lane+'_snr':8+i%15,lane+'_specid':11001+i+1000*j})
        if i%19==0:r['spiffstacker_quality']='peculiar_ucd'
        r.update(sublime3c_spt=r['spt'],sublime3c_selection='AUTO_SELECTION_PASS[native_signed_student4_v1];',sublime2_spt=r['spt'],adopted_spt=r['spt'],parallax=40+i,parallax_unc=2,parallax_snr=(40+i)/2,
                 distance_pc=1000/(40+i),distance_kind='parallax',spt_source='spiffstacker',
                 w2=14+i/40,synthetic_w2=14.1+i/40,w2_difference=.1,
                 M_w2=10+i/40,M_synthetic_w2=10.1+i/40,M_w2_unc=.1,M_synthetic_w2_unc=.12)
        if i%7!=0:
            r.update(adopted_distance_pc=9+(i*11)%80,
                     adopted_distance_kind='photometric' if i%2 else 'trigonometric')
        r.update(gaia_g=None if i%4==0 else 18+i/50, gaia_g_unc=.02, gaia_g_psid='gaiadr3_gmag',
                 gaia_g_source='Synthetic demo', adopted_distance_unc=1.0)
        trigonometric_magnitudes(r)
        r['preferred_spectrum_lane']=preferred_spectrum_lane(r)
        r['sublime2_detection_snr']=r['detection_snr'] if r['sublime2'] else None
        r['samples']=[s for s in SOURCES if r[s]]
        if not any(r.get(s) for s in f['sources']):continue
        if f['min_spt'] is not None and r['spt']<f['min_spt']:continue
        if f['max_spt'] is not None and r['spt']>f['max_spt']:continue
        if passes(r,f):rows.append(r)
    return sorted(rows,key=lambda r:-r['spt'])


@findings.after_request
def private_response(response):
    if (request.endpoint or '').rsplit('.',1)[-1]!='plotly_asset' or response.status_code not in (200,304):
        response.headers['Cache-Control']='no-store'
    response.headers.update({'Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff',
                             'Content-Security-Policy':"frame-ancestors 'self'"})
    return response


@findings.get('/')
@findings.get('/sublime-findings')
def page():
    if request.blueprint != 'sublime_findings':
        from flask import Response
        try:
            auth=sr.credentials()
            with sr.connection(auth):pass
        except (sr.ReviewError,pymysql.MySQLError):
            return Response('Not found.',status=404,mimetype='text/plain')
        html=(STATIC/'sublime_findings.html').read_text()
        base=request.path if request.path.endswith('/') else request.path+'/'
        html=html.replace('<head>','<head><base href="'+base+'">',1)
        html=html.replace('href="/" aria-label="SUBLIME findings home"','href="'+base+'" aria-label="SUBLIME findings home"')
        html=html.replace('href="http://127.0.0.1:8799/"','href="/js/"').replace('Web Tools ↗','MOCAviz ↗')
        return Response(html,mimetype='text/html')
    return send_from_directory(STATIC,'sublime_findings.html')


@findings.get('/assets/<name>')
def asset(name):
    if name not in ('sublime_findings.js','sublime_findings.css','sublime_findings_completeness.js','spherex_review_plot.js'):
        raise sr.ReviewError('Unknown asset.',404)
    return send_from_directory(STATIC,name)


@lru_cache(maxsize=2)
def compressed_plotly(path, mtime_ns):
    data=gzip.compress(path.read_bytes(), compresslevel=6, mtime=0)
    return data, sha256(data).hexdigest()


@findings.get('/assets/plotly.js')
def plotly_asset():
    import plotly
    path=Path(plotly.__file__).parent/'package_data'/'plotly.min.js'
    if request.accept_encodings['gzip']>0:
        stamp=path.stat()
        data,etag=compressed_plotly(path,stamp.st_mtime_ns)
        response=send_file(BytesIO(data), mimetype='text/javascript', etag=etag,
                           last_modified=stamp.st_mtime, max_age=86400)
        response.headers['Content-Encoding']='gzip'
    else:
        response=send_file(path,mimetype='text/javascript',max_age=86400)
    response.vary.add('Accept-Encoding')
    return response


@findings.post('/api/findings/<operation>')
def api(operation):
    try:
        if operation not in ('load','counts','spectra','cutouts','survey','duplicate-matches','declare-duplicate','spectrum-positions','diagnostics','completeness'):raise sr.ReviewError('Unknown operation.',404)
        if request.content_length and request.content_length>32768:raise sr.ReviewError('Request too large.',413)
        if not request.is_json:raise sr.ReviewError('Provide JSON.',415)
        body=request.get_json()
        if not isinstance(body,dict):raise sr.ReviewError('Provide a JSON object.')
        mock=sr.boolean(body.get('mock',False))
        started=time.monotonic()
        if operation=='completeness':
            f=parse_filters(body.get('filters',{'sources':body.get('sources',list(SOURCES)), 'min_spt':10,'min_motion':1}))
            refresh=sr.boolean(body.get('refresh',False))
            if mock:
                reference=completeness.demo_reference()
                summaries=completeness.summarize(demo_rows(completeness.census_filters(f)), f['sources'])
            else:
                with sr.connection(sr.credentials()) as (_,cur):
                    cur.execute('START TRANSACTION READ ONLY')
                    reference=completeness.reference_data(cur,refresh,persist=request.blueprint=='sublime_findings')
                    summaries=completeness.census(cur,f)
            return jsonify(sr.clean({'ok':True,'reference':reference,'summaries':summaries,'elapsed':time.monotonic()-started}))
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
            if not isinstance(raw_ids,dict) or any(not inspector.astrometry.position_lane(key) for key in raw_ids):
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
        if operation=='diagnostics':
            items=diagnostics.parse_items(body.get('items'))
            if mock:result=diagnostics.demo(items)
            else:
                auth=sr.credentials()
                with sr.connection(auth) as (_,cur):
                    cur.execute('START TRANSACTION READ ONLY')
                    cache=diagnostics.DiagnosticCache(auth['database']+':'+auth['user']) if request.blueprint=='sublime_findings' else None
                    result=diagnostics.load(cur,items,cache)
            return jsonify(sr.clean({'ok':True,'items':result}))
        if operation=='counts':
            f=parse_filters(body.get('filters',{}))
            if mock:
                rows=demo_rows(f)
            else:
                with sr.connection(sr.credentials()) as (_,cur):
                    cur.execute('START TRANSACTION READ ONLY')
                    rows=count_rows(cur,f)
            return jsonify(sr.clean({'ok':True,'groups':count_groups(rows),
                                     'elapsed':time.monotonic()-started}))
        if operation=='load':
            f=parse_filters(body.get('filters',{}))
            if mock:
                rows=demo_rows(f);preliminary=len(rows)
                for row in rows:
                    row['spectra']=[dict(lane=lane,specid=row[lane+'_specid'],quality=row[lane+'_quality'],
                                         spt=row[lane+'_spt'],snr=row[lane+'_snr'],synthetic_w2=row['synthetic_w2'],
                                         absolute_w2_unc=row['M_synthetic_w2_unc']) for lane in LANES]
                    if row['moca_oid'] % 5 == 0:
                        row['spectra'].append(dict(row['spectra'][0],specid=90000+row['moca_oid']))
                    row['good_spectrum_count']=len(row['spectra'])
            else:
                with sr.connection(sr.credentials()) as (conn,cur):
                    cur.execute('START TRANSACTION READ ONLY')
                    rows,preliminary=load(cur,f)
            return jsonify(sr.clean({'ok':True,'rows':rows,'preliminary':preliminary,'elapsed':time.monotonic()-started,
                                     'mock':mock,'loaded_at':time.time(),'complete':True,'counts_version':1,'known_source_version':1,'quality_definition_version':3,
                                     'sublime3c_sample_version':1,'other_sample_version':1,'astrometry_plot_version':1,'type_priority_version':1,'spectral_diagnostics_version':1,'trigonometric_photometry_version':1}))
        items=body.get('items')
        if not isinstance(items,list) or len(items)>10:raise sr.ReviewError('Request up to ten spectra.')
        lane_key=body.get('lane','spiffstacker')
        if lane_key not in LANE_CONFIG:raise sr.ReviewError('Invalid spectrum lane.')
        parsed=[(sr.integer(r.get('moca_oid'),'Object ID'),sr.integer(r.get('moca_specid'),'Spectrum ID')) for r in items if isinstance(r,dict)]
        if len(parsed)!=len(items):raise sr.ReviewError('Invalid spectrum requests.')
        results=[]
        if mock:
            results=[sr.demo_item({'moca_oid':oid,'moca_specid':specid,'lane':lane_key}) for oid,specid in parsed]
            for item in results:item['fit']['overlays']=item['fit'].get('overlays',[])[:1]
        else:
            with sr.connection(sr.credentials()) as (conn,cur):
                cur.execute('START TRANSACTION READ ONLY')
                requested=[dict(lane=lane_key,moca_oid=oid,moca_specid=specid) for oid,specid in parsed]
                eligible={(s['moca_oid'],s['moca_specid']) for s in diagnostics.eligible_items(cur,requested)}
                templates=None
                for oid,specid in parsed:
                    try:
                        if (oid,specid) not in eligible:
                            raise sr.ReviewError('This extraction no longer has an eligible spectral review.')
                        meta=sr.spectrum_metadata(cur,specid,oid,LANE_CONFIG[lane_key])
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
