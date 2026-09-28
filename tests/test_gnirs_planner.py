"""Private planner access, cross-worker selection and single-file guarantees.

All credentials/data below are synthetic; no live database connection is used.
Run: PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_gnirs_planner.py
"""
from contextlib import contextmanager
import hashlib
import io
import gzip
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
import zlib

from flask import Flask
import pymysql
import mocaviz.gnirs_planner as planner
from mocaviz.gnirs_planner import cache, builder, schema, visibility


def seed(path):
    fd = cache.acquire_rebuild(path, create=True)
    try:
        cache.initialize(path)
        points = [[8 + i / 4, 60 * 10 ** (.3 * (i / 4 - 8))] for i in range(65)]
        grid_rows, sxd_rows = [], []
        for mode in ('b12', 'b3high', 'b3cloud'):
            for band, spt, n in [('k', 'L5', 15), ('j', 'T5', 25)]:
                for airmass in (1.5, 2):
                    row = dict(mode=mode, band=band, spt=spt, sptn=n, teff=1500,
                               airmass=airmass, slit=.15 if mode=='b12' else .30, center_um=2.3,
                               resolving_power=12500, wavelength_range_um=[2.268, 2.332],
                               seeing_fwhm=.4, slit_seeing_ratio=.375)
                    grid_rows.append({**row, 'curves': [dict(frame_seconds=60, points=points)]})
                    grid_rows.append({**row, 'camera':'short', 'grating':111, 'slit':.3,
                                      'pixel_scale':.15, 'spectral_slit_pixels':2,
                                      'curves':[dict(frame_seconds=60, points=points)]})
                    sxd_rows.append({**row, 'family': 'synthetic test', 'peak_source_rate': .01,
                                     'peak_sky_rate': .01, 'curves': [dict(frame_seconds=60,
                                      read_seconds=22.3, read_mode='VERY_FAINT',
                                      criteria={f'{unit}:{fraction}': points for unit in ('pixel','resolution') for fraction in ('0.5','0.75','0.9')})]})
        config = json.loads(Path(visibility.__file__).with_name('semester.json').read_text())
        config['last_evening'] = '2027-02-02'
        meta = dict(grid={'rows': grid_rows, 'version': 'synthetic-test', 'created_at': '2026-09-26'},
                    sxd_grid={'rows': sxd_rows, 'version': 'synthetic-test', 'cross_dispersed': True, 'cache_key': 'test', 'created_at': '2026-09-26'},
                    semester=config, manifest={'target_count': 2, 'collected_at': '2026-09-26', 'parent_scope': 'Synthetic test objects'},
                    mass_tracks={'source':'https://example.com', 'tracks': []},
                    spectral_type_axis={'points': [{'sptn':10, 'teff':2200}, {'sptn':30, 'teff':400}]},
                    rv_definition='Test', visibility_method='Test')
        with cache.writer(path) as db:
            db.execute(schema.SCHEMA.replace('targets', 'staging_targets', 1))
            cols = [r[1] for r in db.execute('PRAGMA table_info(staging_targets)')]
            for oid, spt, n in ((1, 'L5', 15), (2, 'T5', 25)):
                hist = bytearray(169); hist[120] = 100
                summary = {'best_airmass':1.1, 'best_utc':'2027-02-02T10:00:00+00:00', 'best_evening':'2027-02-01',
                           'astrometry':'test', 'windows':{k:{'max_hours':10, 'duration_counts':[[120,100]], 'nights_1h':100,
                            'first_evening':'2027-02-01','last_evening':'2027-07-31','monthly_1h':{}} for k in ('1.5','2','2.5')}}
                phot = {band:{'magnitude':16., 'magnitude_unc':.1, 'system_band':'2MASS', 'moca_pid':'synthetic'} for band in ('j','k')}
                payload = dict(moca_oid=oid, designation=f'Test target {oid}', moca_aid='TEST', spt=spt,sptn=n,
                               age_myr=100, teff=1500, distance_pc=25, individual_prob=99, summed_young_prob=99,
                               photometry=phot, rv=None, has_rv=False, rv_measurements=[], host_rv_measurements=[],
                               spectra=[], archive_matches=[], ra=150., dec=20., coord_frame='ICRS',
                               measurement_epoch_yr=None, pmra_masyr=None, pmdec_masyr=None,
                               observables='pm+plx', lowg_like=1, report_url='https://example.com', host_separation=None)
                row = dict.fromkeys(cols, 0)
                row.update(oid=oid,name=payload['designation'],aid='TEST',obs='pm+plx',spt=spt,sptn=n,
                           lowg=1,quality='good',host=None,real='1',individual=99,summed=99,uvw=1,loose=1,
                           age=100,distance=25,assoc_distance=25,teff=1500,rv_unc=None,ra=150,dec=20,
                           ra_accessible=1,best_airmass=1.1,j=16,k=16,win15=10,win2=10,
                           hist15=zlib.compress(bytes(hist)),hist2=zlib.compress(bytes(hist)),
                           payload=visibility.pack(payload),visibility=visibility.pack(summary))
                db.execute('INSERT INTO staging_targets VALUES (' + ','.join('?' for _ in cols) + ')', [row[c] for c in cols])
            builder.publish(db, meta)
    finally:
        cache.release_rebuild(fd)


def try_lock(path, queue):
    fd = cache.acquire_rebuild(Path(path))
    queue.put(fd is None)
    if fd is not None:cache.release_rebuild(fd)


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'shared.sqlite'
        seed(self.path)
        self.env = patch.dict(os.environ, {'MOCAVIZ_GNIRS_CACHE_FILE':str(self.path),
                                         'MOCA_USER':'management', 'MOCA_PASSWORD':'ignored-test-only'})
        self.env.start(); self.addCleanup(self.env.stop)
        planner._catalog = None
        self.app = Flask(__name__)
        self.app.register_blueprint(planner.planner)
        self.app.register_blueprint(planner.planner, url_prefix='/js', name='gnirs_planner_compat')
        self.client = self.app.test_client()
        self.headers = {'X-MOCA-User':'collaborators','X-MOCA-Password':'synthetic-test-only'}
        self.auth_calls = []
        @contextmanager
        def auth(values):
            self.auth_calls.append(dict(values))
            if values['password'] != 'synthetic-test-only':raise pymysql.OperationalError('denied')
            yield None
        self.auth = patch.object(planner, 'connection', auth)
        self.auth.start(); self.addCleanup(self.auth.stop)

    def post(self, operation, body=None, **kwargs):
        return self.client.post('/api/gnirs/' + operation, json=body or {}, headers=kwargs.pop('headers', self.headers), **kwargs)

    def test_access_requires_explicit_verified_credentials_even_when_warm(self):
        self.assertEqual(self.post('meta').status_code, 200)
        for headers in ({}, {'X-MOCA-User':'public','X-MOCA-Password':'synthetic-test-only'},
                        {**self.headers,'X-MOCA-Password':'wrong'}):
            response = self.post('meta', headers=headers)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn('catalog_count', response.get_json())
        self.assertEqual(self.client.get('/gnirs-planner').status_code, 403)
        response = self.client.get('/gnirs-planner?user=collaborators&pwd=synthetic-test-only')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('synthetic-test-only', response.get_data(as_text=True))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(self.client.get('/api/gnirs/meta').status_code, 405)
        for query in ('user=collaborators&user=management&pwd=synthetic-test-only',
                      'user=collaborators&pwd=synthetic-test-only&dbase=public',
                      'user=collaborators&pwd=synthetic-test-only&host=other.example'):
            self.assertEqual(self.client.get('/gnirs-planner?' + query).status_code, 403)

    def test_all_interactions_read_only_and_cross_worker(self):
        before = self.path.read_bytes()
        for mode in ('rv','sxd'):
            filters = {'observingMode':mode}
            response = self.post('selection', {'filters':filters})
            self.assertEqual(response.status_code, 200, response.get_json())
            selection = response.get_json()
            self.assertEqual(selection['result']['count'], 2)
            planner._catalog = None  # Simulate dispatch to another WSGI worker.
            body = {'id':selection['id'], 'filters':filters, 'oid':1}
            for operation in ('selection','list','target','navigate','export','windows','regenerate','meta'):
                response = self.post(operation, body)
                self.assertEqual(response.status_code, 200, (operation,response.get_data(as_text=True)[:200]))
                self.assertNotIn('synthetic-test-only', response.get_data(as_text=True))
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            result = self.post('export', body).get_data(as_text=True)
            self.assertIn('telescope_h', result)
            self.assertIn('Test target 1', result)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ['shared.sqlite'])
        self.assertGreater(len(self.auth_calls), 18)
        self.assertEqual(self.client.post('/js/api/gnirs/meta', json={}, headers=self.headers).status_code, 200)

    def test_atomic_publish_and_single_file(self):
        before = cache.metadata(self.path)['revision']
        with self.assertRaisesRegex(RuntimeError, 'interrupt'):
            with cache.writer(self.path) as db:
                self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'memory')
                self.assertEqual(db.execute('PRAGMA temp_store').fetchone()[0], 2)
                self.assertEqual(db.execute('PRAGMA auto_vacuum').fetchone()[0], 1)
                db.execute('CREATE TABLE staging_targets AS SELECT * FROM targets')
                builder.publish(db, cache.get(db, 'catalog'))
                raise RuntimeError('interrupt after DROP/RENAME')
        self.assertEqual(before, cache.metadata(self.path)['revision'])
        with cache.reader(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM targets').fetchone()[0], 2)
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')
        self.assertEqual(len(list(self.path.parent.iterdir())), 1)

    def test_cross_process_regeneration_lock_and_failed_refresh(self):
        fd = cache.acquire_rebuild(self.path)
        ctx = multiprocessing.get_context('spawn')
        queue = ctx.Queue()
        child = ctx.Process(target=try_lock, args=(str(self.path),queue))
        child.start(); self.assertTrue(queue.get(timeout=15)); child.join(timeout=15)
        self.assertEqual(child.exitcode, 0)
        @contextmanager
        def failed(auth):
            raise pymysql.OperationalError('synthetic-test-only must not leak')
            yield
        auth = dict(user='collaborators', password='synthetic-test-only')
        revision = cache.revision(self.path)
        builder.rebuild(self.path, auth, fd, failed)
        self.assertEqual(auth, {})
        self.assertEqual(cache.status(self.path)['phase'], 'error')
        self.assertEqual(cache.revision(self.path), revision)
        self.assertNotIn(b'synthetic-test-only', self.path.read_bytes())
        self.assertEqual(len(list(self.path.parent.iterdir())), 1)

    def test_authenticated_role_and_connection_cleanup(self):
        self.auth.stop()
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = {'authenticated_user':'public@%'}
        with patch.object(planner.pymysql, 'connect', return_value=conn) as connect:
            response = self.post('meta')
            self.assertEqual(response.status_code, 403)
            self.assertEqual(connect.call_args.kwargs['user'], 'collaborators')
            conn.rollback.assert_called()
            conn.close.assert_called_once()

    def test_successful_refresh_and_expired_worker_cannot_publish(self):
        old = cache.acquire_rebuild(self.path)
        with cache.writer(self.path) as db:
            held = cache.get(db, 'lease'); held['expires'] = time.time() - 1
            cache.put(db, 'lease', held)
        fresh = cache.acquire_rebuild(self.path)
        self.assertIsNotNone(fresh)
        with self.assertRaises(cache.CacheUnavailable):
            with cache.writer(self.path, lease=old):pass
        cache.release_rebuild(old)
        self.assertIsNone(cache.acquire_rebuild(self.path))
        prior = cache.revision(self.path)
        with cache.writer(self.path, lease=fresh) as db:
            db.execute('CREATE TABLE staging_targets AS SELECT * FROM targets')
            builder.publish(db, cache.get(db, 'catalog'))
        cache.release_rebuild(fresh)
        self.assertNotEqual(cache.revision(self.path), prior)
        self.assertEqual(cache.status(self.path)['phase'], 'complete')
        self.assertEqual(len(list(self.path.parent.iterdir())), 1)

    def test_simultaneous_regenerate_requests_share_one_background_job(self):
        with patch.object(planner.threading, 'Thread') as thread:
            self.assertEqual(self.post('regenerate', {'action':'start'}).status_code, 202)
            self.assertEqual(self.post('regenerate', {'action':'start'}).status_code, 202)
            thread.assert_called_once()
            thread.return_value.start.assert_called_once()
            lease = thread.call_args.kwargs['args'][2]
        self.assertEqual(cache.status(self.path)['phase'], 'queued')
        cache.release_rebuild(lease)

    def test_startup_validation_and_regeneration_without_configuration(self):
        from scripts.serve_gnirs_planner import main
        before = self.path.read_bytes()
        with patch.dict(os.environ, {'MOCAVIZ_GNIRS_CACHE_FILE':''}), patch('werkzeug.serving.run_simple') as serve:
            for operation, body in (('meta', {}), ('regenerate', {'action':'start'})):
                response = self.post(operation, body)
                self.assertEqual(response.status_code, 503)
                self.assertIn('MOCAVIZ_GNIRS_CACHE_FILE', response.get_json()['error'])
                self.assertIn('timing-calibration bundle', response.get_json()['error'])
            with patch('sys.stderr', new=io.StringIO()), self.assertRaises(SystemExit) as stopped:
                main([])
            self.assertEqual(stopped.exception.code, 2)
            serve.assert_not_called()
            with patch('sys.stdout', new=io.StringIO()):
                self.assertEqual(main(['--cache-file', str(self.path), '--check']), 0)
            serve.assert_not_called()
            missing = self.path.with_name('missing.sqlite')
            with patch('sys.stderr', new=io.StringIO()), self.assertRaises(SystemExit):
                main(['--cache-file', str(missing), '--check'])
            self.assertFalse(missing.exists())
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ['shared.sqlite'])

    def test_startup_requires_imported_timing_grids(self):
        with cache.writer(self.path) as db:
            meta = cache.get(db, 'catalog')
            meta.pop('grid')
            cache.put(db, 'catalog', meta)
        with self.assertRaisesRegex(cache.CacheUnavailable, 'timing-calibration bundle'):
            cache.validate_ready(self.path)

    def test_bounded_selection_memory(self):
        for snr in range(30, 42):
            self.assertEqual(self.post('selection', {'filters':{'snr':snr}}).status_code, 200)
        self.assertEqual(len(planner._catalog.jobs), 4)
        self.assertEqual(self.post('meta', headers={**self.headers, 'Origin':'https://other.example'}).status_code, 403)

    def test_grid_transport_compressed_without_persistent_response_cache(self):
        before = self.path.read_bytes()
        response = self.post('meta', headers={**self.headers, 'Accept-Encoding':'gzip'})
        self.assertEqual(response.headers['Content-Encoding'], 'gzip')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        meta=json.loads(gzip.decompress(response.data))
        self.assertEqual(meta['catalog_count'], 2)
        self.assertEqual(meta['grid']['rows'],[])
        self.assertNotIn('models',meta['grid'])
        self.assertEqual(meta['sxd_grid']['rows'],[])
        self.assertEqual(before, self.path.read_bytes())


if __name__ == '__main__':unittest.main()
