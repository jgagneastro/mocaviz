"""Minimum integration must not increase individual exposures beyond safe counts."""
import copy,json,subprocess
from pathlib import Path
import unittest
from mocaviz.gnirs_planner import catalog,timing,sxd_timing
from test_gnirs_rv_settings import synthetic_grid
import test_gnirs_rv_settings as rv_tests

class MinimumTests(unittest.TestCase):
    def setUp(self):
        self.grid=synthetic_grid();self.f=catalog.normalized_filters({'rvCamera':'long','rvBand':'k'})
        self.target=rv_tests.RVSettingsTests.target(self,15);self.target['k']=10
    def estimate(self,**values):
        f={**self.f,**values}
        return timing.estimate(self.target,f,timing.curves(self.grid,'b12',f['rvSlit']))
    def test_minimum_and_disable(self):
        for minimum in [0,20,23,60]:
            t=self.estimate(minScienceMinutes=minimum)
            self.assertGreaterEqual(t['science'],minimum*60)
            self.assertEqual(t['frames']%4,0)
            self.assertEqual(t['science'],t['frames']*t['frame_seconds'])
            self.assertLessEqual(t['peak_pixel_upper_bound'],50000)
        self.assertLess(self.estimate(minScienceMinutes=0)['science'],1200)
        self.assertEqual(self.estimate()['science'],1200)
        self.target['k']=19
        self.assertGreater(self.estimate()['science'],1200)
    def test_bright_source_and_background_force_shorter_frames(self):
        for source,sky in [(10,0),(0,3000)]:
            for r in self.grid['rows']:r.update(peak_source_rate=source,peak_sky_rate=sky)
            t=self.estimate();self.assertLess(t['frame_seconds'],60)
            self.assertGreaterEqual(t['science'],1200)
            self.assertEqual(t['frames']%4,0);self.assertLessEqual(t['peak_pixel_upper_bound'],50000)
            self.assertTrue(t['short_frame_snr_bound'])
        for r in self.grid['rows']:r['peak_sky_rate']=1e7
        self.assertIsNone(self.estimate()['science'])
    def test_missing_invalid_calibration_and_duration_rejected(self):
        for invalid in [-1,1441,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):catalog.normalized_filters({'minScienceMinutes':invalid})
        for r in self.grid['rows']:r.pop('peak_source_rate')
        self.assertIsNone(self.estimate()['science'])
        self.assertIn('calibration',self.estimate()['reason'])
    def test_short_readmode_python_js_parity_and_band3(self):
        for r in self.grid['rows']:r.update(peak_source_rate=12.,peak_sky_rate=1500.)
        expected=self.estimate(minScienceMinutes=23)
        hist={'windows':{k:{'max_hours':10,'duration_counts':[[120,100]]} for k in ('1.5','2')}}
        target=dict(sptn=15,photometry={b:{'magnitude':self.target[b]} for b in ('j','k')},visibility=hist)
        logic=Path(__file__).resolve().parents[1]/'mocaviz/static/gnirs_planner/logic.js'
        script="const G=require(process.argv[1]),d=JSON.parse(require('fs').readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(G.timing(d.target,d.filters,d.grid)));"
        f={**self.f,'minScienceMinutes':23}
        p=subprocess.run(['node','-e',script,str(logic)],input=json.dumps(dict(target=target,filters=f,grid=self.grid)),text=True,capture_output=True,check=True)
        actual=json.loads(p.stdout)
        for k in ['frames','frame_seconds','science','program','telescope','visits','read_mode','peak_pixel_upper_bound','minimum_science_seconds','short_frame_snr_bound']:
            if isinstance(expected[k],float):self.assertAlmostEqual(actual[k],expected[k],places=8,msg=k)
            else:self.assertEqual(actual[k],expected[k],k)
        self.assertGreaterEqual(timing.band3_science_seconds(self.target,f,timing.curves(self.grid,'b3high',.3)),23*60)
    def test_sxd_minimum_preserves_peak_gate(self):
        row=dict(peak_source_rate=0,peak_sky_rate=1000,curves=[dict(frame_seconds=t,read_seconds=11.14,read_mode='FAINT',logs={'pixel:0.75':[0.]*65}) for t in [20,40,60,200]])
        plan=sxd_timing.exposure_plan(16,dict(snrUnit='pixel',coverageFraction=.75,snr=30,margin=1,minScienceMinutes=20),row)
        _,n,frame,science,c,peak=plan
        self.assertEqual(n%4,0);self.assertGreaterEqual(science,1200);self.assertLessEqual(peak,50000);self.assertLess(frame,60)

if __name__=='__main__':unittest.main()
