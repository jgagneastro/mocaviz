"""Camera/grating isolation, compact timing and browser/server agreement."""
import copy
import json
from pathlib import Path
import subprocess
import unittest
import numpy as np
from mocaviz.gnirs_planner import catalog, timing
from mocaviz.gnirs_planner.rv_grid import row_curves
from scripts.build_gnirs_camera_grid import pack_curves
import test_gnirs_rv_settings as rv_tests


class CameraSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original=rv_tests.synthetic_grid();rows=[]
        for camera in ['long','short']:
            for grating in [10,32,111]:
                if camera=='short' and grating==10:continue
                for old in original['rows']:
                    r=copy.deepcopy(old);factor=(1 if camera=='long' else .6)*grating/111
                    for curve in r['curves']:
                        for values in curve['log_seconds'].values():
                            for i,v in enumerate(values):values[i]=v+np.log(factor)
                    curves=r.pop('curves');scale=.05 if camera=='long' else .15
                    rows.append({**r,'camera':camera,'grating':grating,'pixel_scale':scale,
                                 'spectral_slit_pixels':r['slit']/scale,'timing_log_i32':pack_curves(curves)})
        cls.grid={**original,'rows':rows,'cameras':['long','short'],'gratings':[10,32,111],
                  'timing_encoding':'base64-i32-le-ceil','timing_log_scale':100000,'timing_null':2147483647,
                  'magnitude_count':65,'frames':[60,120,180,240,300],'coverage_fractions':[.25,.5,.75,.9,.95]}

    def test_default_validation_and_missing_setup(self):
        f=catalog.normalized_filters({})
        self.assertEqual((f['rvCamera'],f['rvGrating']),('long','111'))
        for bad in [{'rvCamera':'red'},{'rvGrating':'111 or 32'},{'rvGrating':64},{'rvCamera':'short','rvGrating':'10'}]:
            with self.assertRaises(ValueError):catalog.normalized_filters(bad)
        # A missing camera must not silently use a long-camera calibration.
        with self.assertRaises(ValueError):timing.curves(rv_tests.synthetic_grid(),'b12',camera='short')

    def test_compact_round_trip_and_nulls(self):
        r=copy.deepcopy(self.grid['rows'][0]);decoded=row_curves(self.grid,r)
        self.assertEqual(pack_curves(decoded),r['timing_log_i32'])
        decoded[0]['log_seconds']['0.95']=[None]*65;r['timing_log_i32']=pack_curves(decoded)
        self.assertEqual(row_curves(self.grid,r,.95)[0]['log_seconds']['0.95'],[None]*65)
        with self.assertRaises(ValueError):row_curves(self.grid,{**r,'timing_log_i32':r['timing_log_i32'][:-4]})

    def test_every_camera_grating_and_coverage_matches_js(self):
        cases=[];hist={'windows':{k:{'max_hours':10,'duration_counts':[[120,100]]} for k in ('1.5','2')}}
        for camera in ['long','short']:
            for grating in [10,32,111]:
                if camera=='short' and grating==10:continue
                for coverage in [.25,.5,.75,.9,.95]:
                    f=catalog.normalized_filters({'rvCamera':camera,'rvGrating':grating,'rvBand':'h','rvSlit':'.3','coverageFraction':coverage})
                    target=rv_tests.RVSettingsTests.target(self,15)
                    model=timing.curves(self.grid,'b12',f['rvSlit'],coverage,camera,grating)
                    self.assertEqual({r['camera'] for rows in model.values() for r in rows},{camera})
                    self.assertEqual({r['grating'] for rows in model.values() for r in rows},{grating})
                    expected=timing.estimate(target,f,model)
                    browser=dict(sptn=15,photometry={b:{'magnitude':target[b]} for b in ('j','k')},visibility=hist)
                    cases.append(dict(filters=f,target=browser,expected=expected))
        logic=Path(__file__).resolve().parents[1]/'mocaviz/static/gnirs_planner/logic.js'
        js="const fs=require('fs'),G=require(process.argv[1]);const d=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(d.cases.map(c=>G.timing(c.target,c.filters,d.grid))));"
        proc=subprocess.run(['node','-e',js,str(logic)],input=json.dumps(dict(grid=self.grid,cases=cases)),text=True,capture_output=True,check=True)
        for case,actual in zip(cases,json.loads(proc.stdout)):
            for key in ['science','program','telescope','camera','grating','pixel_scale','spectral_slit_pixels','band','slit','coverage_fraction','fit']:
                self.assertEqual(actual[key],case['expected'][key],key)


if __name__=='__main__':unittest.main()
