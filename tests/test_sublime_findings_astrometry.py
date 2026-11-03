import io
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from mocaviz import sublime_findings_astrometry as astro


class SpectrumAstrometryTests(unittest.TestCase):
    def test_crosshairs_follow_proper_motion_and_fits_orientation(self):
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
        wcs.wcs.crval = [359.9999, 0]
        wcs.wcs.crpix = [11, 11]
        wcs.wcs.cdelt = [-1/3600, 1/3600]
        data = io.BytesIO()
        fits.PrimaryHDU(np.arange(441).reshape(21,21),wcs.to_header()).writeto(data)
        points = {'spiff':astro.position(359.9999,0,2010,1000,500),
                  'sublimeaperture':astro.position(359.9999,0),
                  'spiffstacker':astro.position(180,0)}
        chart = astro.fits_chart(data.getvalue(),points,2014)
        marks = {mark['lane']:mark for mark in chart['markers']}
        self.assertEqual(set(marks), {'spiff','sublimeaperture'})
        self.assertAlmostEqual(marks['spiff']['x'],6.5/21,places=6)
        self.assertAlmostEqual(marks['spiff']['y'],8.5/21,places=6)
        self.assertTrue(marks['spiff']['projected'])
        self.assertAlmostEqual(marks['sublimeaperture']['x'],.5,places=6)
        self.assertFalse(marks['sublimeaperture']['projected'])

    def test_only_exact_spectrum_metadata_can_supply_a_reference(self):
        common = {'moca_oid':3,'telescope_object_name':None,'telescope_ra':None,'telescope_dec':None,
                  'pmra_masyr':50,'pmdec_masyr':25}
        specs = [{**common,'moca_specid':8,'moca_specpackid':55},
                 {**common,'moca_specid':9,'moca_specpackid':62},
                 {**common,'moca_specid':10,'moca_specpackid':76,'telescope_ra':12,'telescope_dec':-1,
                  'telescope_object_name':'SUBLIME2 64'}]
        ref = {'reference_ra_deg':10,'reference_dec_deg':-2,'reference_crd_epoch_yr':2016,
               'reference_pmra_masyr':0,'reference_pmdec_masyr':0}
        with patch.object(astro.sr,'rows',side_effect=[specs,[ref],[{'epoch_yr':2025.7}]]) as rows, \
             patch.object(astro,'stacker_manifest',return_value=None):
            result=astro.spectrum_positions(MagicMock(),3,{'spiff':8,'spiffstacker':9,'sublimeaperture':10})
        self.assertNotIn('spiffstacker',result)
        self.assertEqual(rows.call_args_list[1][0][2],(8,3))
        self.assertEqual(result['spiff']['epoch'],2016)
        self.assertEqual(result['spiff']['pmra'],0)
        self.assertEqual(result['sublimeaperture']['epoch'],2025.7)
        self.assertEqual(result['sublimeaperture']['pmra'],50)
