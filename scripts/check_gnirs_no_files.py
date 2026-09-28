"""Deny filesystem mutations throughout GNIRS browsing, plotting data and export.

Fixture creation and cleanup happen outside the guard. No real credentials,
network requests, production cache changes, or figure files are involved.
"""
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import gnirs_wsgi  # Apply the production service's read-only astronomy config.
from test_gnirs_planner import PlannerTests

active = False
violations = []


def audit(event, args):
    if not active:return
    # os.makedirs(exist_ok=True) may call mkdir on an existing directory. That
    # can only raise EEXIST; it cannot create or modify a filesystem entry.
    if event == 'os.mkdir' and Path(args[0]).is_dir():return
    mutation = event in {'os.mkdir','os.rename','os.remove','os.rmdir','os.link',
                        'os.symlink','os.truncate','tempfile.mkstemp','tempfile.mkdtemp'}
    if event == 'open':
        mode, flags = args[1:3]
        mutation = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
    if event == 'sqlite3.connect':
        mutation = 'mode=ro' not in str(args[0])
    if mutation:
        violations.append((event, str(args[0]) if args else ''))
        raise AssertionError('Filesystem mutation during planner use: ' + event)


sys.addaudithook(audit)
case = PlannerTests('test_all_interactions_read_only_and_cross_worker')
case.setUp()
try:
    active = True
    case.test_all_interactions_read_only_and_cross_worker()
    case.test_access_requires_explicit_verified_credentials_even_when_warm()
    case.test_grid_transport_compressed_without_persistent_response_cache()
    active = False
    # Seed compact synthetic camera/grating rows outside the mutation guard;
    # exercise their API selection and export inside it.
    import csv, io
    import mocaviz.gnirs_planner as planner
    from mocaviz.gnirs_planner import cache
    from test_gnirs_camera_settings import CameraSettingsTests
    CameraSettingsTests.setUpClass()
    with cache.writer(case.path) as db:
        meta=cache.get(db,'catalog')
        meta['grid']={**CameraSettingsTests.grid,'version':'compact-camera-test'}
        cache.put(db,'catalog',meta)
    planner._catalog=None
    active=True
    selections=set()
    for camera,grating in [('long',10),('long',32),('long',111),('short',32),('short',111)]:
        filters={'rvCamera':camera,'rvGrating':str(grating)}
        response=case.post('selection',{'filters':filters})
        case.assertEqual(response.status_code,200,response.get_json())
        selection=response.get_json();selections.add(selection['id'])
        body={'id':selection['id'],'filters':filters,'oid':1}
        target=case.post('target',body).get_json()['_timing']
        case.assertEqual((target['camera'],target['grating']),(camera,grating))
        response=case.post('export',body);case.assertEqual(response.status_code,200)
        rows=list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        case.assertTrue(rows)
        case.assertTrue(all(r['camera']==camera and int(r['grating_lmm'])==grating for r in rows))
    case.assertEqual(len(selections),5)
finally:
    active = False
    case.doCleanups()
print('Filesystem mutation attempts:', len(violations))
if violations:print('Blocked operations:', violations)
raise SystemExit(1 if violations else 0)
