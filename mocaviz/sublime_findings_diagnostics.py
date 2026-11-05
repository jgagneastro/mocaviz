"""Read-only, bounded spectral diagnostics for the Findings Atlas."""
from __future__ import annotations

import json
import math
import os
import re
import statistics
import time
from pathlib import Path

from . import spherex_review as sr

MAX_ITEMS = 96
BANDS = ('all', 'nir', 'mid', 'red')
ROOT = Path(os.environ.get('FINDINGS_AUTOTYPE_ROOT', '/Volumes/TData2/Documents/Science_Products/autotype_plots'))
_DIRECTORIES = {}


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def summarize(points):
    """Signed per-pixel F_lambda/sigma, using valid non-ignored measurements."""
    bands = {key: [] for key in BANDS}
    for point in points:
        wave, flux, error = (number(point.get(key)) for key in ('wavelength_angstrom', 'flux_flambda', 'flux_flambda_unc'))
        if point.get('ignored') or wave is None or wave <= 0 or flux is None or error is None or error <= 0:
            continue
        snr = number(flux / error)
        if snr is None:
            continue
        bands['all'].append(snr)
        wave /= 10000
        key = 'nir' if 1 <= wave < 2.5 else 'mid' if 2.5 <= wave < 4 else 'red' if 4 <= wave <= 5 else None
        if key:
            bands[key].append(snr)
    return {key: {'mean': statistics.fmean(values) if values else None,
                  'median': statistics.median(values) if values else None,
                  'count': len(values)} for key, values in bands.items()}


def parse_items(items):
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise sr.ReviewError(f'Request at most {MAX_ITEMS} spectral diagnostics.')
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or item.get('lane') not in sr.LANES:
            raise sr.ReviewError('Invalid diagnostic spectrum lane.')
        if any(isinstance(item.get(key), bool) for key in ('moca_oid', 'moca_specid')):
            raise sr.ReviewError('Invalid diagnostic spectrum ID.')
        oid, specid = (sr.integer(item.get(key), key) for key in ('moca_oid', 'moca_specid'))
        if oid <= 0 or specid <= 0:
            raise sr.ReviewError('Invalid diagnostic spectrum ID.')
        key = oid, specid, item['lane']
        if key not in seen:
            seen.add(key)
            result.append({'moca_oid': oid, 'moca_specid': specid, 'lane': item['lane']})
    return result


def comment_chi2(text):
    # Match a complete field, never a similarly named red-band diagnostic.
    for key in ('robust_reduced_chi2_10pct_cap', 'reduced_chi2_10pct_cap', 'reduced_chi2'):
        match = re.search(r'(?:^|;\s*)' + key + r'=([^;]+)', text or '')
        value = number(match[1]) if match else None
        if value is not None and value >= 0:
            return value
    return None


def candidate_directories(lane):
    root = ROOT / {'spiff': '', 'spiffstacker': 'autotype_spiffstacker', 'sublimeaperture': 'autotype_sublimeaperture'}[lane]
    cached = _DIRECTORIES.get(lane)
    if cached and cached[0] > time.monotonic() - 60:
        return cached[1]
    try:
        samples = [Path(entry.path) for entry in os.scandir(root)
                   if entry.is_dir() and not entry.name.startswith(('.', 'autotype_'))]
    except OSError:
        samples = []
    samples.sort(key=lambda path: (path.name != 'sublime', path.name != 'catwiseredmovers', path.name))
    classes = [name for name, _ in sr.CLASSIFICATIONS] + ['risky_andromeda', 'unclassified']
    directories = [root]
    for sample in samples:
        directories.append(sample)
        directories.extend(sample / name for name in classes)
    _DIRECTORIES[lane] = time.monotonic(), directories
    return directories


def sidecar_metrics(item):
    """Require exact object, spectrum, pack and generator-method provenance."""
    lane = sr.LANES[item['lane']]
    filename = f"spherex_autotype_moca_oid_{item['moca_oid']}.json"
    for directory in candidate_directories(item['lane']):
        try:
            path = directory / filename
            if path.stat().st_size > 2_000_000:
                continue
            payload = json.loads(path.read_text())
        except (OSError, ValueError, UnicodeError):
            continue
        if not isinstance(payload, dict) or payload.get('schema') != 'spherex_autotype_result' or payload.get('schema_version') != 1:
            continue
        source, generator = payload.get('source'), payload.get('generator')
        if not isinstance(source, dict) or not isinstance(generator, dict):
            continue
        if (source.get('moca_oid'), source.get('moca_specid'), source.get('moca_specpackid')) != (item['moca_oid'], item['moca_specid'], lane['pack']):
            continue
        if generator.get('calculation_method') not in lane['methods']:
            continue
        best, cnn = payload.get('best_match') or {}, payload.get('cnn') or {}
        if not isinstance(best, dict) or not isinstance(cnn, dict):
            continue
        chi2 = next((value for key in ('display_reduced_chi2', 'robust_reduced_chi2_10pct_cap', 'reduced_chi2_10pct_cap', 'reduced_chi2')
                     if (value := number(best.get(key))) is not None and value >= 0), None)
        probabilities = cnn.get('probabilities') or {}
        probability = number(probabilities.get('good')) if isinstance(probabilities, dict) else None
        if probability is not None and not 0 <= probability <= 1:
            probability = None
        return {'chi2': chi2, 'cnn': probability, 'fit_source': 'Exact-spectrum autotype JSON', 'cnn_source': 'Exact-spectrum autotype JSON'}
    return {'chi2': None, 'cnn': None, 'fit_source': None, 'cnn_source': None}


def load(cur, items):
    if not items:
        return []
    ids = sorted({item['moca_specid'] for item in items})
    placeholders = ','.join(['%s'] * len(ids))
    cur.execute('SELECT s.moca_specid,s.moca_oid,s.moca_specpackid FROM moca_spectra s '
                'JOIN moca_objects mo ON mo.moca_oid=s.moca_oid AND mo.ignored=0 '
                f'WHERE s.moca_specid IN ({placeholders}) AND s.ignored=0', tuple(ids))
    meta = {row['moca_specid']: row for row in cur.fetchall()}
    valid = [item for item in items if item['moca_specid'] in meta
             and meta[item['moca_specid']]['moca_oid'] == item['moca_oid']
             and meta[item['moca_specid']]['moca_specpackid'] == sr.LANES[item['lane']]['pack']]
    valid_ids = sorted({item['moca_specid'] for item in valid})
    if not valid_ids:
        return []
    placeholders = ','.join(['%s'] * len(valid_ids))
    cur.execute('SELECT moca_specid,wavelength_angstrom,flux_flambda,flux_flambda_unc FROM data_spectra '
                f'WHERE moca_specid IN ({placeholders}) AND ignored=0 LIMIT 1000001', tuple(valid_ids))
    points = list(cur.fetchall())
    if len(points) > 1_000_000:
        raise sr.ReviewError('Diagnostic batch exceeds the interactive sample limit.', 422)
    grouped = {specid: [] for specid in valid_ids}
    for point in points:
        grouped[point['moca_specid']].append(point)
    cur.execute('SELECT id,moca_specid,calculation_method,comments FROM data_spectral_types '
                f'WHERE moca_specid IN ({placeholders}) AND ignored=0 ORDER BY id DESC', tuple(valid_ids))
    types = list(cur.fetchall())
    result = []
    for item in valid:
        metrics = sidecar_metrics(item)
        if metrics['chi2'] is None:
            row = next((row for row in types if row['moca_specid'] == item['moca_specid']
                        and row['calculation_method'] in sr.LANES[item['lane']]['methods']), None)
            metrics['chi2'] = comment_chi2(row.get('comments')) if row else None
            if metrics['chi2'] is not None:
                metrics['fit_source'] = 'Exact-spectrum stored autotype comments'
        result.append({**item, **metrics, 'snr': summarize(grouped[item['moca_specid']])})
    return result


def demo(items):
    result = []
    for item in items:
        offset = list(sr.LANES).index(item['lane'])
        points = [{'wavelength_angstrom': wave * 10000, 'flux_flambda': 3 + (item['moca_oid'] % 17) + offset + i * i / 50, 'flux_flambda_unc': 1}
                  for i, wave in enumerate([.8, 1, 1.4, 2, 2.5, 3, 3.8, 4, 4.4, 5])]
        result.append({**item, 'snr': summarize(points), 'chi2': .3 + item['moca_oid'] % 23 / 3 + offset,
                       'cnn': .2 + item['moca_oid'] % 80 / 100, 'fit_source': 'Synthetic demo', 'cnn_source': 'Synthetic demo'})
    return result
