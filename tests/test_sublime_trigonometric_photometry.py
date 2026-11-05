"""Trigonometric luminosity calculations and stored Gaia selection; no live DB."""
import math
import sqlite3
import unittest
from unittest.mock import patch
from mocaviz import sublime_findings as sf


class TrigonometricPhotometryTests(unittest.TestCase):
    def test_distance_priority_and_uncertainties(self):
        row = {'adopted_distance_kind':'trigonometric', 'adopted_distance_pc':21,
               'adopted_distance_unc':1, 'adopted_distance_id':8,
               'parallax':50, 'parallax_unc':2, 'parallax_id':7,
               'gaia_g':18, 'gaia_g_unc':.02, 'w2':15, 'w2_unc':.1}
        sf.trigonometric_magnitudes(row)
        self.assertEqual(row['trigonometric_distance_pc'],21)
        self.assertEqual(row['trigonometric_distance_id'],8)
        self.assertAlmostEqual(row['M_gaia_g_trig'],18-5*math.log10(21)+5)
        self.assertAlmostEqual(row['M_w2_trig_unc'],math.hypot(.1,5/math.log(10)/21))
        row['adopted_distance_kind']='photometric'
        sf.trigonometric_magnitudes(row)
        self.assertEqual(row['trigonometric_distance_pc'],20)
        self.assertEqual(row['trigonometric_parallax_id'],7)
        self.assertNotIn('trigonometric_distance_id',row)
        self.assertAlmostEqual(row['trigonometric_distance_unc'],.8)

    def test_nontrigonometric_distances_and_missing_measurements_are_not_filled(self):
        for parallax in (None,0,-5):
            for kind in ('photometric','nonphotometric',None):
                row={'parallax':parallax,'distance_pc':20,'adopted_distance_pc':20,
                     'adopted_distance_kind':kind,'gaia_g':18,'w2':15}
                sf.trigonometric_magnitudes(row)
                self.assertIsNone(row['trigonometric_distance_pc'])
                self.assertIsNone(row['M_gaia_g_trig'])
                self.assertIsNone(row['M_w2_trig'])
        row={'parallax':50,'parallax_unc':None,'w2':15,'w2_unc':.1}
        sf.trigonometric_magnitudes(row)
        self.assertIsNotNone(row['M_w2_trig'])
        self.assertIsNone(row['M_w2_trig_unc'])
        self.assertIsNone(row['M_gaia_g_trig'])

    def test_photometry_selection_and_trigonometric_membership(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.executescript('''
                CREATE TABLE data_parallaxes(id INT,moca_oid INT,parallax_mas REAL,parallax_mas_unc REAL,adopted INT,ignored INT);
                CREATE TABLE data_distances(id INT,moca_oid INT,distance_pc REAL,distance_pc_unc REAL,photometric_estimate INT,parallax_id INT,adopted INT,ignored INT);
                CREATE TABLE data_photometry(id INT,moca_oid INT,moca_psid TEXT,magnitude REAL,magnitude_unc REAL,is_synthetic INT,moca_specid INT,calculation_method TEXT,origin TEXT,system_band_simple TEXT,ignored INT,adopted_simpleband INT,adopted INT);
                CREATE TABLE moca_spectra(moca_specid INT,moca_specpackid INT,ignored INT);
                CREATE TABLE cat_gaiadr3(id INT,moca_oid INT,source_id TEXT,phot_g_mean_mag REAL,phot_g_mean_flux_over_error REAL);
            ''')
            db.executemany('INSERT INTO data_parallaxes VALUES (?,?,?,?,?,?)',[
                (1,1,50,1,1,0),(2,2,25,1,1,0),(5,5,-3,2,1,0),
                (6,6,40,1,1,1),(7,7,100,1,1,0)])
            db.executemany('INSERT INTO data_distances VALUES (?,?,?,?,?,?,?,?)',[
                (11,1,21,1,0,1,1,0),(13,3,10,1,1,None,1,0),
                (14,4,20,1,0,None,1,0),(15,5,100,10,0,5,1,0),
                (16,6,25,1,0,6,1,1)])
            measurements=[(100+oid,oid,'wise_w2',15,.1,0,None,None,None,'W2',0,1,1) for oid in range(1,8)]
            measurements += [
                (1,1,'gaiadr3_gmag',18,.02,0,None,None,None,'G',0,0,1),
                (2,1,'gaiadr2_gmag',17,.03,0,None,None,None,'G',0,1,1),
                (3,2,'gaiadr3_gmag',16,.02,0,None,None,None,'G',1,1,1),
                (4,2,'gaiadr3_gmag',16,.02,1,None,None,None,'G',0,1,1),
                (5,2,'panstarrs_g',16,.02,0,None,None,None,'g',0,1,1),
            ]
            db.executemany('INSERT INTO data_photometry VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',measurements)
            db.executemany('INSERT INTO cat_gaiadr3 VALUES (?,?,?,?,?)',[(21,1,'gaia1',19,100),(22,2,'gaia2',20,50)])
            rows=[{'moca_oid':oid,'best_spt_source':'spiff','known':False} for oid in range(1,8)]
            def fetch(cur,sql,params=()):
                return [dict(r) for r in db.execute(sql.replace('%s','?'),params)]
            with patch.object(sf,'fetch',side_effect=fetch):
                result=sf.photometry(None,rows,sf.parse_filters({'distance_mode':'include_photometric'}))
            one,two,photo,other,negative,ignored,missing=result
            self.assertEqual(one['gaia_g'],17)
            self.assertEqual(one['gaia_g_psid'],'gaiadr2_gmag')
            self.assertEqual(one['distance_pc'],20)  # Original diagram is unchanged.
            self.assertEqual(one['trigonometric_distance_pc'],21)
            self.assertEqual(two['gaia_g'],20)
            self.assertEqual(two['gaia_g_source'],'cat_gaiadr3')
            self.assertAlmostEqual(two['gaia_g_unc'],2.5/math.log(10)/50)
            self.assertAlmostEqual(two['M_gaia_g_trig'],20-5*math.log10(40)+5)
            for row in (photo,other,ignored):
                self.assertIsNone(row['trigonometric_distance_pc'])
                self.assertIsNone(row['M_w2_trig'])
            self.assertEqual(negative['trigonometric_distance_pc'],100)
            self.assertIsNotNone(negative['M_w2_trig'])
            self.assertIsNone(missing['M_gaia_g_trig'])
            self.assertEqual(missing['M_w2_trig'],15)


if __name__=='__main__':unittest.main()
