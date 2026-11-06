import copy
import unittest

from mocaviz import spherex_review as sr
from mocaviz.spherex_cnn_metadata import append_comments, parse_comments


CNN=dict(status='classified',probabilities=dict(good=.9012345678901234,good_candidate=.08,contaminant=.0187654321098766),
         model_path='/models/test.joblib')


class StoredSpectralCnnTests(unittest.TestCase):
    def row(self, row_id, specid, probability):
        cnn={**CNN,'probabilities':{**CNN['probabilities'],'good':probability}}
        return dict(id=row_id,moca_specid=specid,ignored=1,comments=append_comments('Original fit',cnn,source='backfill.py',sha256='a'*64))

    def test_latest_exact_spectrum_only_including_unreviewed_ignored_types(self):
        state=dict(spt=[self.row(1,34,.8),self.row(2,34,0),self.row(3,999,.99)])
        result=sr.stored_spectral_cnn(state,34)
        self.assertEqual(result['spectral_cnn_probability'],0)
        self.assertEqual(result['spectral_cnn_spt_id'],2)
        self.assertEqual(result['spectral_cnn']['model'],'test.joblib')
        self.assertIsNone(sr.stored_spectral_cnn(state,9999)['spectral_cnn_probability'])
        state['spt'].append(dict(id=4,moca_specid=34,comments='New autotype without CNN'))
        self.assertIsNone(sr.stored_spectral_cnn(state,34)['spectral_cnn_probability'])

    def test_web_spt_upsert_retains_stored_probabilities_and_provenance(self):
        state=dict(spt=[self.row(1,34,CNN['probabilities']['good'])])
        meta=sr.stored_spectral_cnn(state,34)
        item=dict(state=dict(spt=[]),object=dict(moca_oid=12,moca_specid=34,**meta),fit=dict(best=dict(
            spectral_type='L5',spectral_type_number=15,grid_type='field',moca_spherex_template_id=17,
            reduced_chi2=1,selection_score=3)))
        row=sr.make_spt(item,sr.LANES['spiffstacker'],0,0,'gagne')
        parsed=parse_comments(row['comments'])
        self.assertEqual(parsed['probabilities'],CNN['probabilities'])
        self.assertEqual(parsed['model'],'test.joblib')
        self.assertEqual(parsed['source'],'backfill.py')
        self.assertEqual(parsed['json_sha256'],'a'*64)
        self.assertEqual(row['ignored'],0)


if __name__=='__main__':unittest.main()
