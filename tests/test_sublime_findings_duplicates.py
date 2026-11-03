import unittest
from unittest.mock import MagicMock, patch

from mocaviz import sublime_findings as sf
from mocaviz import sublime_findings_duplicates as dup


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.target = {'moca_oid':12, 'ra':359.99, 'dec':0, 'designation':'Selected', 'adopted_type':'L4'}
        self.known = {'moca_oid':34, 'ra':0.01, 'dec':0, 'designation':'Known', 'spectral_type':'L5'}
        self.auth = {'user':'management'}
        self.client = sf.create_app().test_client()

    def test_scan_wraps_ra_excludes_self_and_reports_existing_decisions(self):
        far = {'moca_oid':56, 'ra':0.03, 'dec':0}
        existing = {'moca_oid':34,'potential_duplicated_moca_oid':12,'classification':'n','applied':False}
        with patch.object(dup,'targets',return_value=[self.target]), \
             patch.object(dup,'known_details',return_value=[self.known]) as details, \
             patch.object(dup.sr,'rows',side_effect=[[self.target,self.known,far],[existing]]):
            matches, positioned = dup.scan(MagicMock(),[12])
        self.assertEqual(positioned,1)
        self.assertEqual(len(matches),1)
        self.assertAlmostEqual(matches[0]['separation_arcsec'],72)
        self.assertEqual(matches[0]['decision'],existing)
        self.assertEqual(details.call_args[0][1],[34])

    def test_declaration_writes_the_selected_pair_and_changelog_once(self):
        conn,cur=MagicMock(),MagicMock()
        with patch.object(dup,'targets',return_value=[self.target]), \
             patch.object(dup,'known_details',return_value=[self.known]), \
             patch.object(dup.sr,'rows',side_effect=[[{'moca_oid':12},{'moca_oid':34}],[]]):
            result=dup.declare(conn,cur,self.auth,12,34)
        self.assertEqual(result['potential_duplicated_moca_oid'],12)
        self.assertEqual(result['moca_oid'],34)
        self.assertEqual(cur.execute.call_count,2)
        insert,log=cur.execute.call_args_list
        self.assertIn('INSERT INTO pcat_duplicated_vetting',insert[0][0])
        self.assertEqual(insert[0][1],(34,12,'Known','Selected','L5','L4'))
        self.assertIn('INSERT INTO moca_changelog',log[0][0])
        conn.commit.assert_called_once()

    def test_stale_pair_and_existing_review_prevent_writes(self):
        for known,decisions in [({**self.known,'ra':0.5},[]),(self.known,[{'moca_oid':34}])]:
            with self.subTest(known=known,decisions=decisions):
                conn,cur=MagicMock(),MagicMock()
                with patch.object(dup,'targets',return_value=[self.target]), \
                     patch.object(dup,'known_details',return_value=[known]), \
                     patch.object(dup.sr,'rows',side_effect=[[{'moca_oid':12},{'moca_oid':34}],decisions]):
                    with self.assertRaises(dup.sr.ReviewError) as error:
                        dup.declare(conn,cur,self.auth,12,34)
                self.assertEqual(error.exception.status,409)
                cur.execute.assert_not_called()
                conn.commit.assert_not_called()

    def test_demo_and_collaborator_cannot_write(self):
        with patch.object(sf.sr,'connection') as connect:
            url='/api/findings/declare-duplicate'
            body={'moca_oid':12,'primary_oid':34}
            response=self.client.post(url,json={**body,'mock':True})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.get_json()['decision']['classification'],'y')
            headers={'X-MOCA-User':'collaborators','X-MOCA-Password':'test',
                     'X-MOCA-Database':'mocadb_private_tables'}
            response=self.client.post(url,json=body,headers=headers)
            self.assertEqual(response.status_code,403)
            connect.assert_not_called()
