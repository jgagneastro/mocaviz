from contextlib import contextmanager
import unittest
from unittest.mock import MagicMock, patch

import pymysql

from mocaviz.app import app
from mocaviz.association_audit import audit, routes


def headers(role='management', password='fixture'):
    return {'X-MOCA-User':role,'X-MOCA-Password':password,'X-MOCA-Database':'mocadb_private_tables'}


@contextmanager
def verify(auth):
    if auth['password'] != 'fixture':
        raise pymysql.OperationalError(1045,'Access denied')
    yield MagicMock(), MagicMock()


class AssociationAuditAccessTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.connection = patch.object(routes.auth_api, 'connection', side_effect=verify)
        self.connection.start()
        self.addCleanup(self.connection.stop)

    def test_home_only_lists_audit_after_private_authentication(self):
        for url in ('/', '/js/', '/static/js_index.html'):
            result = self.client.get(url,buffered=True)
            self.assertEqual(result.status_code,200)
            self.assertNotIn(b'Association Audit', result.data)
            self.assertNotIn(b'/association-audit',result.data)
        self.assertNotIn(b'/association-audit',self.client.get('/', headers=headers(password='wrong'),buffered=True).data)
        for url in ('/','/js/'):
            private = self.client.get(url,headers=headers('collaborators'))
            self.assertIn(b'href="/association-audit"', private.data)
            self.assertEqual(private.headers['Cache-Control'],'no-store')

    def test_private_page_and_catalog_cannot_bypass_authentication(self):
        for prefix in ('', '/js'):
            root = prefix+'/association-audit'
            self.assertEqual(self.client.get(root).status_code,404)
            self.assertEqual(self.client.get(root,headers=headers(password='wrong')).status_code,404)
            self.assertEqual(self.client.get(root+'/api/catalog').status_code,403)
            result = self.client.get(root,headers=headers())
            self.assertEqual(result.status_code,200)
            self.assertIn(b'Association Audit',result.data)
            self.assertIn(b'/plotly.min.js',result.data)
            self.assertEqual(result.headers['Cache-Control'],'no-store')

    def test_management_preview_receipt_and_cross_origin_rejection(self):
        base = '/association-audit/api/'
        auth = headers()
        session = self.client.get(base+'session',headers=auth).get_json()
        self.assertTrue(session['can_write'])
        auth['X-Audit-Token'] = session['token']
        plan={'id':2,'row':{'moca_aid':'THEIA1','parent_aid':'THEIA2'},'revision':'fixture'}
        with patch.object(routes.service,'make_preview',return_value=plan) as preview, \
             patch.object(routes.service,'apply_plan',return_value={'saved':True,'id':2}) as apply, \
             patch.object(routes,'STORES',{'management':MagicMock(),'collaborators':MagicMock()}):
            result=self.client.post(base+'preview',json={},headers={**auth,'Origin':'https://other.example'})
            self.assertEqual(result.status_code,403)
            preview.assert_not_called()
            receipt=self.client.post(base+'preview',json={},headers=auth).get_json()['token']
            result=self.client.post(base+'apply',json={'confirm':True,'token':receipt+'x'},headers=auth)
            self.assertEqual(result.status_code,409)
            apply.assert_not_called()
            collab=headers('collaborators')
            session=self.client.get(base+'session',headers=collab).get_json()
            self.assertFalse(session['can_write'])
            collab['X-Audit-Token']=session['token']
            self.assertEqual(self.client.post(base+'apply',json={'confirm':True,'token':receipt},headers=collab).status_code,403)
            apply.assert_not_called()
            result=self.client.post(base+'apply',json={'confirm':True,'token':receipt},headers=auth)
            self.assertEqual(result.get_json(),{'saved':True,'id':2})
            self.assertEqual(apply.call_args[0][-1],plan)


class AssociationAuditGeometryTests(unittest.TestCase):
    def test_full_phase_space_scoring_runs_on_host_python(self):
        point={'x_pc':10,'y_pc':20,'z_pc':30,'u_kms':1,'v_kms':2,'w_kms':3}
        first=audit.robust_group_summary([{**point,'x_pc':10+i/10} for i in range(5)],{})
        second=audit.robust_group_summary([{**point,'x_pc':12+i/10} for i in range(5)],{})
        result=audit.phase_space_metrics(first,second)
        self.assertAlmostEqual(result['position_separation_pc'],2.0)
