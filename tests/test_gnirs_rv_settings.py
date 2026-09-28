"""RV setting selection, pixel coverage and server/browser timing parity."""
import copy
import json
import math
from pathlib import Path
import subprocess
import unittest
import zlib
import numpy as np
from mocaviz.gnirs_planner import catalog, timing
from scripts.build_gnirs_rv_grid import sample_times


def synthetic_grid():
    rows=[]
    for mode in ('b12','b3high','b3cloud'):
        for slit in (.1,.15,.2,.3,.45,.675,1.):
            for band,center in [('j',1.3),('h',1.65),('k',2.3)]:
                for x in (1.5,2.):
                    for sptn in (15,25):
                        row=dict(mode=mode,band=band,photometry_band='j' if band=='h' else band,
                            spt='L5' if sptn==15 else 'T5',sptn=sptn,teff=1600 if sptn==15 else 1000,
                            airmass=x,slit=slit,center_um=center,resolving_power=12000*.15/slit,
                            wavelength_range_um=[center-.025,center+.025],seeing_fwhm=.7,slit_seeing_ratio=slit/.7)
                        factor={'j':1.,'h':2.,'k':3.}[band]*.15/slit*(1 if mode=='b12' else 1.5)
                        row['curves']=[dict(frame_seconds=frame,log_seconds={str(f):[math.log(1200*factor*f/.75*10**(.6*(m-16))) for m in np.arange(8,24.01,.25)] for f in (.25,.5,.75,.9,.95)}) for frame in (60,120,180,240,300)]
                        rows.append(row)
    return {'rows':rows,'magnitude_start':8,'magnitude_step':.25}


class RVSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.grid=synthetic_grid()

    def target(self,sptn=15):
        hist=bytearray(169);hist[120]=100
        return dict(sptn=sptn,j=16.,k=15.,win15=10,win2=10,hist15=zlib.compress(bytes(hist)),hist2=zlib.compress(bytes(hist)))

    def test_defaults_and_validation(self):
        f=catalog.normalized_filters({})
        self.assertEqual((f['rvBand'],f['rvSlit'],f['coverageFraction']),('auto','0.3',.75))
        for fraction in (.25,.5,.75,.9,.95):
            f=catalog.normalized_filters({'coverageFraction':fraction,'snrUnit':'resolution'})
            self.assertEqual(f['coverageFraction'],fraction);self.assertEqual(f['snrUnit'],'pixel')
        for setting in ({'rvBand':'x'},{'rvSlit':.22},{'coverageFraction':.8},{'observingMode':'sxd','coverageFraction':.95}):
            with self.assertRaises(ValueError):catalog.normalized_filters(setting)
        self.assertEqual(catalog.normalized_filters({'observingMode':'sxd'})['snrUnit'],'resolution')

    def test_explicit_settings_defaults_and_fixed_band3_slit(self):
        for mode,width in [('b12',.15),('b3high',.3),('b3cloud',.3)]:
            f=catalog.normalized_filters({'mode':mode,'rvCamera':'long','rvSlit':'auto'})
            for n,band in [(15,'k'),(25,'j')]:
                t=timing.estimate(self.target(n),f,timing.curves(self.grid,mode))
                self.assertEqual((t['band'],t['slit']),(band,width))
        f=catalog.normalized_filters({'rvBand':'h','rvSlit':.675,'coverageFraction':.95})
        t=timing.estimate(self.target(),f,timing.curves(self.grid,f['mode'],f['rvSlit'],f['coverageFraction']))
        self.assertEqual((t['center_um'],t['slit'],t['coverage_fraction']),(1.65,.675,.95))
        self.assertEqual(t['photometry_band'],'j');self.assertTrue(t['model_color_normalization'])
        fixed=timing.curves(self.grid,'b3high',.3,.95)
        self.assertEqual(timing.setup(self.target(),f,fixed)[2]['slit'],.3)

    def test_disjoint_pixels_and_failures_in_denominator(self):
        # Every fourth pixel fails: surviving 75% is fragmented across detector.
        shot=np.ones(100)/3600/50**2;sky=np.zeros(100);read=np.zeros(100);valid=np.arange(100)%4!=0
        output=sample_times(shot,sky,read,valid,16)[0]['log_seconds']
        self.assertIsNotNone(output['0.5'][32])
        self.assertAlmostEqual(math.exp(output['0.75'][32]),1.)
        self.assertIsNone(output['0.95'][32])
        valid[0]=True
        output=sample_times(shot,sky,read,valid,16)[0]['log_seconds']
        self.assertAlmostEqual(math.exp(output['0.75'][32]),1.)
        self.assertIsNone(output['0.95'][32])

    def test_interpolation_bounds_pixel_quantiles(self):
        rng=np.random.default_rng(7)
        source=10**rng.uniform(-3,3,101);background=10**rng.uniform(-3,3,101)
        def required(m,f):
            q=10**(.4*(m-16));values=np.sort(source*q+background*q*q)
            return float(values[int(np.ceil(f*len(values)))-1])
        for f in (.25,.5,.75,.9,.95):
            points=[[m,required(m,f)] for m in np.arange(8,24.001,.25)]
            for m in np.arange(8.025,24,.05):
                self.assertGreaterEqual(timing.interpolate(m,points)+1e-9,required(m,f))

    def test_unsupported_coverage_does_not_fall_back(self):
        grid=copy.deepcopy(self.grid)
        for row in grid['rows']:
            for c in row['curves']:c['log_seconds']['0.95']=[None]*65
        f=catalog.normalized_filters({'coverageFraction':.95})
        t=timing.estimate(self.target(),f,timing.curves(grid,'b12','auto',.95))
        self.assertIsNone(t['science']);self.assertIn('unsupported',t['reason'])

    def test_python_js_agree_across_bands_slits_and_coverage(self):
        cases=[];hist={'windows':{k:{'max_hours':10,'duration_counts':[[120,100]]} for k in ('1.5','2')}}
        for band,slit,frac,n in [('auto','auto',.75,15),('auto','auto',.75,25),('auto','0.3',.75,22.5),('auto','0.3',.75,23),('auto_h','0.3',.75,22),('auto_h','0.3',.75,22.5),('auto_h','0.3',.75,23),('auto_h','0.3',.75,25),('j',.1,.25,15),('h',.675,.95,25),('k',1.,.5,25),('h',.2,.9,15)]:
            f=catalog.normalized_filters({'rvCamera':'long','rvBand':band,'rvSlit':slit,'coverageFraction':frac})
            r=self.target(n);expected=timing.estimate(r,f,timing.curves(self.grid,'b12',f['rvSlit'],frac))
            if band in ('auto','auto_h'):
                resolved='k' if n<23 else ('h' if band=='auto_h' else 'j')
                self.assertEqual(expected['band'],resolved)
                explicit={**f,'rvBand':resolved}
                direct=timing.estimate(r,explicit,timing.curves(self.grid,'b12',f['rvSlit'],frac))
                self.assertEqual(expected,direct)
            browser=dict(sptn=n,photometry={b:{'magnitude':r[b]} for b in ('j','k')},visibility=hist)
            cases.append(dict(filters=f,target=browser,expected=expected))
        logic=Path(__file__).resolve().parents[1]/'mocaviz/static/gnirs_planner/logic.js'
        js="const fs=require('fs'),G=require(process.argv[1]);const d=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(d.cases.map(c=>G.timing(c.target,c.filters,d.grid))));"
        out=subprocess.run(['node','-e',js,str(logic)],input=json.dumps(dict(grid=self.grid,cases=cases)),text=True,capture_output=True,check=True)
        for case,actual in zip(cases,json.loads(out.stdout)):
            for key in ('science','program','telescope','band','photometry_band','slit','coverage_fraction','fit'):
                self.assertEqual(actual[key],case['expected'][key],key)

if __name__=='__main__':unittest.main()
