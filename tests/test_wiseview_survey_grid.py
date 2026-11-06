"""Check the generated survey scripts use the status-aware shared grid."""
import unittest
from mocaviz.wiseview_review import runtime


class SurveyGridTests(unittest.TestCase):
    def test_initial_and_final_scripts_keep_named_statuses_and_error_states(self):
        kwargs=dict(moca_oid=1,ra_deg=56.04,dec_deg=1.61)
        raw=(runtime.review.build_wiseview_ps1_fallback_cutout_js(**kwargs)+
             runtime.review.build_wiseview_des_supplement_cutouts_js(**kwargs))
        for final in (False,True):
            with self.subTest(final=final):
                script=runtime.web_survey_js(raw,final=final)
                self.assertIn('window.SurveyImages.render(panel, cardPromises, {labels, final: '+str(final).lower()+'})',script)
                self.assertIn('card.dataset.surveyState = "unavailable"',script)
                self.assertIn('payload.irg.label, payload.yzi.label',script)
                self.assertNotIn('const cards = await Promise.all(cardPromises)',script)
                self.assertEqual(script.count('return window.SurveyImages.load(src, options);'),2)
