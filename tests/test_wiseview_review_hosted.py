import dataclasses
from contextlib import contextmanager
import unittest
from unittest.mock import MagicMock, patch

import pymysql
from flask import Flask

from mocaviz import spherex_review as sr
from mocaviz.wiseview_review import routes, counts
from mocaviz.wiseview_review.context import AUTH


def auth(role='management'):
    return dict(user=role,password='fixture',database='mocadb_private_tables')


def headers(role='management'):
    value=auth(role)
    return {'X-MOCA-User':role,'X-MOCA-Password':'fixture','X-MOCA-Database':value['database'],
            'X-Review-Token':sr.seal(value,'wiseview-session',{},lifetime=60)}


@contextmanager
def connection(identity):
    if identity['password']!='fixture':raise pymysql.OperationalError(1045,'denied')
    yield MagicMock(),MagicMock()


class CountTests(unittest.TestCase):
    def count(self,quality,motion=6,**extra):
        return counts.summarize_discoveries([dict(moca_oid=1,autotype_spectral_type_number=12,
            motion=motion,spectral_class=quality,**extra)],set(),set())

    def test_only_four_good_classes_confirm_with_clear_motion(self):
        for quality in ('good','peculiar_ucd','contaminated_ucd','good_reddened'):
            self.assertEqual(self.count(quality)['confirmed_l0'],1)
            self.assertEqual(self.count(quality,3)['candidate_l0'],1)
        for quality in (None,'','bad','good_plus_star','incomplete_but_promising'):
            self.assertEqual(sum(self.count(quality).values()),0)

    def test_candidate_never_promoted_by_clear_motion(self):
        self.assertEqual(self.count('good_candidate')['confirmed_l0'],0)
        self.assertEqual(self.count('good_candidate')['candidate_l0'],1)
        self.assertEqual(self.count('good_candidate',None)['candidate_l0'],1)
        self.assertEqual(sum(self.count('good_candidate',-1).values()),0)
        self.assertEqual(sum(self.count('good_candidate',1.5).values()),0)

    def test_any_lane_confirmed_precedence_and_distinct_objects(self):
        row=dict(moca_oid=7,autotype_spectral_type_number=21,motion=5,
            spiff_class='good_candidate',spiffstacker_class='peculiar_ucd')
        result=counts.summarize_discoveries([row,row],set(),set())
        self.assertEqual(result,dict(confirmed_l0=1,confirmed_t0=1,candidate_l0=0,candidate_t0=0))
        self.assertEqual(sum(counts.summarize_discoveries([row],{7},set()).values()),0)


class HostedTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.app.register_blueprint(routes.review)
        self.app.register_blueprint(routes.review,url_prefix='/js',name='compat')
        self.client=self.app.test_client()
        self.patch=patch.object(sr,'connection',side_effect=connection)
        self.patch.start();self.addCleanup(self.patch.stop)

    def post(self,operation,body=None,role='management',**extra):
        return self.client.post('/wiseview-review/api/'+operation,json=body or {},headers={**headers(role),**extra})

    def test_pages_reject_public_or_invalid_credentials(self):
        for root in ('/wiseview-review/','/js/wiseview-review/'):
            self.assertEqual(self.client.get(root).status_code,404)
            self.assertEqual(self.client.get(root,headers={**headers(),'X-MOCA-Password':'wrong'}).status_code,404)
            for role in ('management','collaborators'):
                response=self.client.get(root,headers=headers(role))
                self.assertEqual(response.status_code,200)
                self.assertIn(('base href="'+root+'"').encode(),response.data)
                self.assertNotIn(b'fixture',response.data)
                self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_management_only_writes_and_csrf(self):
        for operation in routes.WRITES:
            self.assertEqual(self.post(operation,role='collaborators').status_code,403)
        self.assertEqual(self.post('queue',Origin='https://attacker.invalid').status_code,403)
        response=self.client.post('/wiseview-review/api/queue',json={},headers={**headers(),'X-Review-Token':'fake'})
        self.assertEqual(response.status_code,409)

    def test_queue_is_returned_to_browser_and_not_stored(self):
        with patch.object(routes.rt,'optimized_queue',return_value={8,4}),patch.object(routes.rt,'order_review_oids',return_value=[8,4]):
            response=self.post('queue',{'filters':{},'mode':'sublime'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['oids'],[8,4])
        self.assertFalse(hasattr(routes.rt,'SESSIONS'))

    def test_portable_object_receipt_retains_extra_fields(self):
        obj=routes.rt.review.ReviewObject(7,12.,8.,'Fixture')
        obj.adopted_pm={'pmtot_masyr':20}
        obj.heading_spectral_types=[{'spectral_type':'L2'}]
        def get(session,index):
            session['snapshots'][7]=None;session['spectral_snapshots'][7]={'spiff':None}
            return 7,obj
        with patch.object(routes.rt,'get_object',side_effect=get):
            result=self.post('object',{'oid':7,'index':5,'filters':{}})
        self.assertEqual(result.status_code,200)
        token=result.json['object_token']
        state=routes.empty_session(routes.rt.parse_filters({}),'sublime',7)
        restored=routes.object_context(auth(),{'object_token':token},state,7)
        self.assertEqual(restored.heading_spectral_types,[{'spectral_type':'L2'}])
        self.assertEqual(state['spectral_snapshots'][7],{'spiff':None})
        with self.assertRaises(sr.ReviewError):
            routes.object_context(auth(),{'object_token':token+'x'},state,7)

    def test_receipts_preserve_original_snapshot_on_classify_and_undo(self):
        obj=dict(moca_oid=7,ra_deg=12.,dec_deg=8.,designation='Fixture',adopted_pm={})
        token=sr.seal(auth(),'wiseview-object',dict(oid=7,object=obj,snapshot={'classification':'old'},spectral={}))
        def save(session,*args):
            self.assertEqual(session['snapshots'][7],{'classification':'old'})
            session['undo'].append(dict(oid=7,before=None,after={'classification':'new'},index=0))
            return dict(saved='new',oid=7)
        body=dict(oid=7,index=5,filters={},object_token=token,key='6')
        with patch.object(routes.rt,'save_decision',side_effect=save):
            result=self.post('classify',body)
        self.assertEqual(result.status_code,200)
        receipt=result.json['undo_token']
        def undo(session):
            self.assertEqual(session['undo'][0]['index'],5)
            return dict(oid=7,index=5)
        with patch.object(routes.rt,'undo_decision',side_effect=undo):
            result=self.post('undo',dict(filters={},undo_token=receipt))
        self.assertEqual(result.json,dict(oid=7,index=5))

    def test_readonly_context_is_request_scoped(self):
        with patch.object(routes.rt,'sublime_stats',side_effect=lambda:dict(role=AUTH.get()['user'])):
            self.assertEqual(self.post('stats',role='collaborators').json,dict(role='collaborators'))
            self.assertEqual(self.post('stats').json,dict(role='management'))
        with self.assertRaises(LookupError):AUTH.get()


class ProductionMountTests(unittest.TestCase):
    def setUp(self):
        from mocaviz.app import app
        self.client=app.test_client()
        self.patch=patch.object(sr,'connection',side_effect=connection)
        self.patch.start();self.addCleanup(self.patch.stop)

    def test_private_home_contains_both_links_and_public_response_neither(self):
        for url in ('/','/js/','/static/js_index.html'):
            for hdr in ({},{**headers(),'X-MOCA-Password':'wrong'}):
                response=self.client.get(url,headers=hdr)
                self.assertNotIn(b'/wiseview-review',response.data)
                self.assertNotIn(b'/sublime-findings',response.data)
        for role in ('collaborators','management'):
            for url in ('/','/js/'):
                response=self.client.get(url,headers=headers(role))
                self.assertIn(b'href="/wiseview-review/"',response.data)
                self.assertIn(b'href="/sublime-findings/"',response.data)

    def test_findings_mounts_authenticate_and_keep_relative_assets_and_api(self):
        for url in ('/sublime-findings/','/js/sublime-findings/'):
            self.assertEqual(self.client.get(url).status_code,404)
            response=self.client.get(url,headers=headers('collaborators'))
            self.assertEqual(response.status_code,200)
            self.assertIn(('base href="'+url+'"').encode(),response.data)
            self.assertNotIn(b'127.0.0.1:8799',response.data)
            self.assertEqual(self.client.get(url+'assets/sublime_findings.js').status_code,200)
            result=self.client.post(url+'api/findings/load',json={'mock':True,'filters':{'sources':['sublime2']}})
            self.assertEqual(result.status_code,200)
            self.assertTrue(result.json['ok'])

    def test_hosted_reference_cache_never_touches_disk(self):
        from mocaviz import sublime_findings_completeness as completeness
        import time
        cached={'cached_at':time.time(),'version':completeness.VERSION}
        with patch.object(completeness,'MEMORY_REFERENCE',cached),patch.object(completeness,'CACHE') as disk:
            self.assertEqual(completeness.reference_data(None,persist=False),cached)
            disk.read_text.assert_not_called()
            disk.parent.mkdir.assert_not_called()


if __name__=='__main__':unittest.main()
