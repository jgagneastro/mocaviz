import threading
import time
import unittest
from unittest.mock import patch
import numpy as np
from mocaviz.astrometry_jobs import FitJobs, FitControl, FitBusy, FitCancelled, FitLimitReached, current_control
from mocaviz import app as api


def wait_done(jobs, owner, key):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        state=jobs.status(owner,key)
        if state['state'] in jobs.terminal:return state
        time.sleep(.002)
    raise AssertionError('fit did not stop')


class FitJobTests(unittest.TestCase):
    def test_identical_request_reattaches_and_single_worker_rejects_others(self):
        jobs=FitJobs();entered=threading.Event();release=threading.Event()
        def work():entered.set();release.wait(2);return {'fit':{'pmra':10}}
        first=jobs.start('owner',{'mode':'pm'},work);self.assertTrue(entered.wait(1))
        try:
            self.assertEqual(jobs.start('owner',{'mode':'pm'},work)['id'],first['id'])
            with self.assertRaises(FitBusy):jobs.start('owner',{'mode':'pm_plx'},work)
            with self.assertRaises(KeyError):jobs.status('someone-else',first['id'],cancel=True)
            self.assertEqual(jobs.status('owner',first['id'])['state'],'running')
        finally:release.set()
        done=wait_done(jobs,'owner',first['id'])
        self.assertEqual(done['result']['fit']['pmra'],10)
        elapsed=done['elapsedSeconds'];time.sleep(.003)
        self.assertEqual(jobs.status('owner',first['id'])['elapsedSeconds'],elapsed)

    def test_cancel_stops_the_actual_sampler_loop_and_returns_no_result(self):
        jobs=FitJobs();entered=threading.Event();stopped=threading.Event()
        def work():
            try:
                entered.set()
                while True:current_control().check(likelihood=True);time.sleep(.001)
            finally:stopped.set()
        job=jobs.start('owner',{},work);self.assertTrue(entered.wait(1))
        self.assertEqual(jobs.status('owner',job['id'],cancel=True)['state'],'cancelling')
        done=wait_done(jobs,'owner',job['id'])
        self.assertTrue(stopped.is_set());self.assertEqual(done['state'],'cancelled')
        self.assertIsNone(done['result']);self.assertGreater(done['likelihoodCalls'],0)

    def test_runtime_and_likelihood_limits_never_publish_partial_fit(self):
        for control in [FitControl(timeout=.01),FitControl(max_calls=5)]:
            jobs=FitJobs(control_factory=lambda:control)
            def work():
                while True:current_control().check(likelihood=True);time.sleep(.001)
            job=jobs.start('owner',{},work);done=wait_done(jobs,'owner',job['id'])
            self.assertEqual(done['state'],'incomplete');self.assertIsNone(done['result'])
            self.assertIn('limit',done['error'])

    def test_failure_releases_worker_for_next_fit_and_retention_is_bounded(self):
        jobs=FitJobs(capacity=2)
        def fail():raise RuntimeError('synthetic failure')
        job=jobs.start('owner',{},fail);done=wait_done(jobs,'owner',job['id'])
        self.assertEqual(done['state'],'failed');self.assertIsNone(done['result'])
        for i in range(4):
            job=jobs.start('owner',{'trial':i},lambda:{'fit':{}});wait_done(jobs,'owner',job['id'])
        self.assertLessEqual(len(jobs.jobs),2)

    def test_native_sampler_partial_return_is_rejected_at_call_limit(self):
        rows=[dict(id=i,plot_epoch_abs=2010+i,base_rel_ra=10*i,base_rel_dec=5*i,
                   ra_unc_mas=1,dec_unc_mas=1,single_epoch=1,pm_corrected=0,
                   plx_corrected=0,point_of_view='Earth') for i in range(5)]
        body=dict(mode='pm',fitter='scipy',outlierMixture=False,errorFloor=False,
                  reference=dict(ra=120,dec=-30,epoch=2015),fixedPlx=0,rows=rows)
        arrays=api._astrometry_fit_arrays(body)
        seed=api._astrometry_scipy_fit(arrays,outlier_mixture=False,error_floor=False)
        calls={}
        class PartialSampler:
            def __init__(self,**kwargs):pass
            def run(self,**kwargs):calls.update(kwargs);return {'ncall':kwargs['max_ncalls']}
        with patch('ultranest.ReactiveNestedSampler',PartialSampler):
            with self.assertRaises(FitLimitReached):api._astrometry_ultranest_fit(arrays,seed,False,False)
        self.assertEqual(calls['dlogz'],.5);self.assertEqual(calls['min_num_live_points'],300)
        self.assertGreater(calls['max_ncalls'],0)

    def test_status_polling_bypasses_shared_response_cache(self):
        jobs=FitJobs();entered=threading.Event();release=threading.Event()
        args={'user':'management','pwd':'synthetic','dbase':'mocadb_private_tables'}
        owner=api._astrometry_fit_job_owner(args)
        def work():entered.set();release.wait(2);return {'fit':{'pmra':10}}
        job=jobs.start(owner,{},work);self.assertTrue(entered.wait(1))
        try:
            with patch.object(api,'_ASTROMETRY_FIT_JOBS',jobs),patch.object(api,'ENCODED_RESPONSE_CACHE_SECONDS',60):
                client=api.app.test_client();url='/api/astrometry/fit/jobs/'+job['id']
                first=client.get(url,query_string=args)
                self.assertEqual(first.get_json()['job']['state'],'running')
                self.assertEqual(first.headers['Cache-Control'],'no-store')
                release.set();wait_done(jobs,owner,job['id'])
                second=client.get(url,query_string=args)
                self.assertEqual(second.get_json()['job']['state'],'complete')
                self.assertNotEqual(second.headers.get('X-MOCA-Response-Cache'),'HIT')
        finally:release.set()

    def test_job_headers_preserve_authenticated_owner_without_query_credentials(self):
        headers={'X-MOCA-User':'management','X-MOCA-Password':'synthetic',
                 'X-MOCA-Database':'mocadb_private_tables'}
        jobs=FitJobs()
        with patch.object(api,'_ASTROMETRY_FIT_JOBS',jobs),patch.object(api,'_astrometry_fit_arrays',return_value={}),patch.object(api,'_run_astrometry_fit',return_value={'fit':{'pmra':10}}):
            client=api.app.test_client()
            started=client.post('/api/astrometry/fit/jobs',headers=headers,json={'fitter':'ultranest'})
            self.assertEqual(started.status_code,202)
            key=started.get_json()['job']['id']
            self.assertEqual(client.get('/api/astrometry/fit/jobs/'+key,headers=headers).status_code,200)
            self.assertEqual(client.get('/api/astrometry/fit/jobs/'+key,headers={**headers,'X-MOCA-Password':'wrong'}).status_code,404)

    def test_capabilities_and_job_routes_validate_scope_and_inputs(self):
        jobs=FitJobs();args={'user':'management','pwd':'synthetic','dbase':'mocadb_private_tables'}
        rows=[dict(id=i,plot_epoch_abs=2010+i,base_rel_ra=10*i,base_rel_dec=5*i,
                   ra_unc_mas=1,dec_unc_mas=1,single_epoch=1,pm_corrected=0,
                   plx_corrected=0,point_of_view='Earth') for i in range(5)]
        body=dict(mode='pm',fitter='ultranest',reference=dict(ra=120,dec=-30,epoch=2015),fixedPlx=0,rows=rows)
        with patch.object(api,'_ASTROMETRY_FIT_JOBS',jobs),patch.object(api,'_run_astrometry_fit',return_value={'fit':{'pmra':10}}):
            client=api.app.test_client()
            self.assertEqual(client.post('/api/astrometry/fit/jobs',query_string={'user':'public','dbase':'mocadb'},json=body).status_code,403)
            r=client.post('/api/astrometry/fit/jobs',query_string=args,json=body)
            self.assertEqual(r.status_code,202);key=r.get_json()['job']['id']
            self.assertEqual(client.get('/api/astrometry/fit/jobs/'+key,query_string={**args,'pwd':'different'}).status_code,404)
            done=wait_done(jobs,api._astrometry_fit_job_owner(args),key)
            self.assertEqual(done['state'],'complete')
            self.assertEqual(client.get('/api/astrometry/fit/jobs/'+key,query_string=args).get_json()['job']['result']['fit']['pmra'],10)
            self.assertEqual(client.post('/api/astrometry/fit/jobs',query_string=args,json={}).status_code,400)
            self.assertEqual(client.post('/api/astrometry/fit/jobs',query_string=args,json=[1]).status_code,400)

if __name__=='__main__':unittest.main()
