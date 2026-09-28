#!/usr/bin/env python3
"""Offline detector-count bounds for the compact RV grid. Public ITC inputs only.

No catalog credentials or native atmosphere grids are read. The source term is
conservatively bounded by the brightest unsmoothed model/flat-continuum ratio
anywhere in the recorded interval, with the spatial/slit losses removed. This
protects against seeing better than the requested condition bin. Maxima over
weather/airmass additionally protect Band 3 plans against improved transparency.
Only two count rates per timing row are added to the shared server cache.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip, hashlib, json, math, re, time
from io import StringIO
from pathlib import Path
import numpy as np
import requests
from bs4 import BeautifulSoup
from build_gnirs_rv_grid import BANDS, SLITS, MODES, filter_response


def synthetic_mag(sed,response):
    arr,zero=response;w=sed[:,0]/1000;keep=(w>=arr[0,0])&(w<=arr[-1,0]);x=w[keep]
    trans=np.interp(x,arr[:,0],arr[:,1]);integrate=getattr(np,"trapezoid",None) or np.trapz
    jy=integrate(sed[keep,1]*x*trans,x)/integrate(2.99792458e-12/x*trans,x)
    return float(-2.5*np.log10(jy/zero))


def fetch(inputs,path):
    identity=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    if path.exists():
        with np.load(path) as d:
            if str(d['identity'])!=identity:raise ValueError('Peak calibration identity mismatch')
            return d['signal'],d['background'],float(d['seeing'])
    for attempt in range(4):
        try:
            with requests.Session() as s:
                r=s.post('https://itc.gemini.edu/itc/servlet/calc',files=[(k,(None,str(v))) for k,v in inputs.items()],timeout=(15,90));r.raise_for_status()
                soup=BeautifulSoup(r.text,'html.parser');txt=soup.get_text(' ',strip=True);arrays={}
                for name in ['SignalData','BackgroundData']:
                    url=next(a['href'] for a in soup.select('a[href]') if 'filename='+name+'&' in a['href'] or 'filename='+name==a['href'].split('?')[-1])
                    r=s.get('https://itc.gemini.edu'+url,timeout=(15,60));r.raise_for_status();arrays[name]=np.loadtxt(StringIO(r.text))
                seeing=float(re.search(r'derived image size\(FWHM\) for a point source = ([0-9.]+)',txt)[1])
                peak=float(re.search(r'peak pixel signal \+ background is (\d+) e-',txt)[1])
                signal,background=arrays['SignalData'],arrays['BackgroundData']
                # ASCII plots are peak spatial row; independent maxima are an upper bound.
                assert signal[:,1].max()+np.square(background[:,1]).max()>=peak-2
                assert len(signal)>900 and np.isfinite(signal).all() and np.isfinite(background).all()
            np.savez_compressed(path,signal=signal,background=background,seeing=seeing,identity=identity)
            path.with_suffix('.json').write_text(json.dumps(dict(inputs=inputs,identity=identity,peak=peak,seeing=seeing,created_at=datetime.now(timezone.utc).isoformat()),indent=2))
            return signal,background,seeing
        except Exception:
            if attempt==3:raise
            time.sleep(2*(attempt+1))


def calibrate(job,base,args,models):
    cam,g,band,mode,x,slit=job;scale=.05 if cam=='long' else .15
    iq,cc,wv=MODES[mode]
    inputs={**base,'Distribution':'PLAW','powerIndex':'0','psSourceNorm':'1e-15','numExpA':'12','expTimeA':'300',
            'PixelScale':'PS_005' if cam=='long' else 'PS_015','Disperser':f'D_{g}',
            'SlitWidth':f'SW_{SLITS.index(slit)+1}','instrumentCentralWavelength':f'{BANDS[band]:.2f}',
            'ImageQuality':iq,'CloudCover':cc,'WaterVapor':wv,'Airmass':str(x)}
    signal,bg,seeing=fetch(inputs,args.output/'calibrations'/f'{cam}_{g}_{band}_{mode}_{x}_{slit}.npz')
    wave=signal[:,0]/1000;pixel=float(np.median(np.diff(wave)))
    # Gaussian point-source slit transmission times fraction in central spatial pixel.
    # Rounded ITC seeing: use +0.01 arcsec to err toward a larger count bound.
    fraction=math.erf(slit*math.sqrt(math.log(2))/(seeing+.01))*math.erf(scale*math.sqrt(math.log(2))/(seeing+.01))
    sky=float(np.square(bg[:,1]).max()/300)
    rates={}
    for n,model in models.items():
        sed=model['sed'];w=sed[:,0]/1000
        keep=(w>=wave[0]-6*pixel*slit/scale)&(w<=wave[-1]+6*pixel*slit/scale)
        ratio=float(np.max(sed[keep,1]/(1e-15*1.25/w[keep])))
        phot='j' if band=='h' else band
        q=10**(-.4*(16-model['magnitudes'][phot]))
        # Independent maxima and no spatial losses intentionally overestimate the peak.
        rates[n]=(float(signal[:,1].max()/300/fraction*ratio*q),sky)
    return job,rates


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['grid','source','j-filter','output']:p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--workers',type=int,default=3);a=p.parse_args();(a.output/'calibrations').mkdir(parents=True,exist_ok=True)
    raw=a.grid.read_bytes();grid=json.loads(gzip.decompress(raw) if raw.startswith(b'\x1f\x8b') else raw)
    old=json.loads((a.source/'grid.json').read_text());filters={'j':filter_response(a.j_filter),'k':filter_response(a.source/'2mass_Ks.xml')};models={}
    for m in old['models']:
        raw=(a.source/(m['spt']+'.sed')).read_bytes();assert hashlib.sha256(raw).hexdigest()==m['sed_sha256']
        sed=np.loadtxt(StringIO(raw.decode()));models[m['sptn']]={'sed':sed,'magnitudes':{b:synthetic_mag(sed,v) for b,v in filters.items()}}
    base=json.loads((a.source/'T0_b12_x1.5_f1_t300.json').read_text())['inputs']
    def key(r):return (r.get('camera','long'),r.get('grating',111),r['band'],r['mode'],float(r['airmass']),r['slit'])
    jobs=sorted({key(r) for r in grid['rows']});rates={};start=time.monotonic()
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(calibrate,j,base,a,models) for j in jobs]
        for i,f in enumerate(as_completed(futures),1):
            job,value=f.result();rates[job]=value
            if i%10==0 or i==len(jobs):print(f'{datetime.now().isoformat(timespec="seconds")} {i}/{len(jobs)} detector calibrations; elapsed {time.monotonic()-start:.0f}s',flush=True)
    # Enforce the brightest source/background across all sampled weather/airmass.
    bounds={}
    for (cam,g,b,m,x,s),values in rates.items():
        for n,(star,sky) in values.items():
            k=(cam,g,b,s,n);prior=bounds.get(k,(0,0));bounds[k]=(max(prior[0],star),max(prior[1],sky))
    for r in grid['rows']:
        r['peak_source_rate'],r['peak_sky_rate']=bounds[(r.get('camera','long'),r.get('grating',111),r['band'],r['slit'],r['sptn'])]
        r['peak_reference_magnitude']=16.;r['peak_limit_electrons']=50000
    grid.update(version=grid['version']+'-peak-v1',created_at=datetime.now(timezone.utc).isoformat(),
        peak_method='50,000 electron cap; unsmoothed template maximum, no Gaussian slit/spatial losses, maxima across weather/airmass; source rate normalized at magnitude 16 in timing photometry band',
        detector_reference='https://www.gemini.edu/instrumentation/gnirs/components')
    with gzip.open(a.output/'grid.json.gz','wt') as f:json.dump(grid,f,separators=(',',':'),allow_nan=False)
    print('Saved',len(grid['rows']),'rows with compact detector bounds',flush=True)
if __name__=='__main__':main()
