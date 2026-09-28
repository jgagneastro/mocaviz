#!/usr/bin/env python3
"""Offline camera/grating expansion using public Gemini response calibrations.

No catalog or credentials are read. Models are the existing compact public SEDs;
no native model grids are copied. Only the final compact timing table is installed
into the web server's single shared SQLite file.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
from io import StringIO
import json
from pathlib import Path
import re
import time
import numpy as np
import requests
from bs4 import BeautifulSoup
from scipy.integrate import cumulative_trapezoid
from scipy.ndimage import gaussian_filter1d
if __package__:
    from .build_gnirs_rv_grid import BANDS, SLITS, FRACTIONS, FRAMES, MODES, sample_times, filter_response, synthetic_mag
else:
    from build_gnirs_rv_grid import BANDS, SLITS, FRACTIONS, FRAMES, MODES, sample_times, filter_response, synthetic_mag

SCALE=100000
NULL=2147483647


def pack_curves(curves):
    values=[NULL if x is None else int(np.ceil(np.nextafter(x*SCALE,-np.inf)))
            for c in curves for fraction in FRACTIONS for x in c['log_seconds'][str(fraction)]]
    return base64.b64encode(np.asarray(values,dtype='<i4').tobytes()).decode()


def fetch(inputs, path, reuse):
    identity=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    if path.exists():
        with np.load(path) as data:
            if str(data['identity'])!=identity:raise ValueError('Calibration identity mismatch: '+path.name)
            return data['snr'],float(data['seeing'])
    prior=reuse.get(identity)
    if prior:
        with np.load(prior.with_suffix('.npz')) as data:arr=data['FinalS2NData']
        seeing=json.loads(prior.read_text())['seeing_fwhm']
        return arr,seeing
    for attempt in range(4):
        try:
            with requests.Session() as session:
                response=session.post('https://itc.gemini.edu/itc/servlet/calc',
                    files=[(k,(None,str(v))) for k,v in inputs.items()],timeout=(15,90))
                response.raise_for_status();soup=BeautifulSoup(response.text,'html.parser')
                text=soup.get_text(' ',strip=True)
                link=next((a['href'] for a in soup.select('a[href]') if 'filename=FinalS2NData' in a['href']),None)
                if link is None:raise ValueError('ITC omitted S/N: '+text[-500:])
                response=session.get('https://itc.gemini.edu'+link,timeout=(15,60));response.raise_for_status()
                arr=np.loadtxt(StringIO(response.text))
                if len(arr)<900:raise ValueError('Incomplete detector')
                match=re.search(r'derived image size\(FWHM\) for a point source = ([0-9.]+)',text)
                if not match:raise ValueError('ITC omitted seeing')
                seeing=float(match.group(1))
            np.savez_compressed(path,snr=arr,seeing=seeing,identity=identity)
            path.with_suffix('.json').write_text(json.dumps(dict(inputs=inputs,identity=identity,seeing_fwhm=seeing,
                created_at=datetime.now(timezone.utc).isoformat()),indent=2))
            return arr,seeing
        except Exception:
            if attempt==3:raise
            time.sleep(2*(attempt+1))


def convolved_ratio(sed, wave, pixel, slit, scale, atmosphere):
    # Match the ITC nominal slit-filled Gaussian width, then integrate pixels.
    # The input SED is already the compact public source used by the old grid.
    fwhm=pixel*slit/scale
    sigma=fwhm/2.354820045
    step=min(pixel/12,sigma/6)
    x=np.arange(wave[0]-max(6*sigma,3*pixel),wave[-1]+max(6*sigma,3*pixel)+step,step)
    transmission=np.interp(x,atmosphere[:,0],atmosphere[:,1])
    star=np.interp(x,sed[:,0]/1000,sed[:,1],left=0,right=0)
    actual=gaussian_filter1d(star*transmission,sigma/step,mode='nearest',truncate=6)
    reference=gaussian_filter1d(1e-15*1.25/x*transmission,sigma/step,mode='nearest',truncate=6)
    edges=np.r_[wave-pixel/2,wave[-1]+pixel/2]
    def pixels(y):return np.diff(np.interp(edges,x,cumulative_trapezoid(y,x,initial=0)))/np.diff(edges)
    a,b=pixels(actual),pixels(reference)
    return np.divide(a,b,out=np.zeros_like(a),where=b>0)


def calibration(job,args,base,reuse,models,atmospheres):
    camera,grating,band,mode,airmass,slit=job
    scale=.05 if camera=='long' else .15
    iq,cc,wv=MODES[mode]
    inputs={**base,'Distribution':'PLAW','powerIndex':'0','psSourceNorm':'1e-15',
        'PixelScale':'PS_005' if camera=='long' else 'PS_015','Disperser':f'D_{grating}',
        'SlitWidth':f'SW_{SLITS.index(slit)+1}','instrumentCentralWavelength':f'{BANDS[band]:.2f}',
        'ImageQuality':iq,'CloudCover':cc,'WaterVapor':wv,'Airmass':str(airmass)}
    name=f'{camera}_g{grating}_{band}_{mode}_x{airmass}_s{slit}'
    arrays=[]
    for factor,frame in [(1,300),(5,300),(1,60)]:
        data={**inputs,'psSourceNorm':str(1e-15*factor),'numExpA':str(3600//frame),'expTimeA':str(frame)}
        arr,seeing=fetch(data,args.output/'calibrations'/f'{name}_f{factor}_t{frame}.npz',reuse)
        arrays.append(arr)
    a,b,c=arrays
    if not np.allclose(a[:,0],b[:,0]) or not np.allclose(a[:,0],c[:,0]):raise ValueError('Wavelength mismatch')
    wave=a[:,0]/1000;pixel=float(np.median(np.diff(wave)))
    valid=(a[:,1]>.01)&(b[:,1]>.01)&(c[:,1]>.01)
    v1=1/np.maximum(a[:,1],.001)**2;v5=25/np.maximum(b[:,1],.001)**2;v60=1/np.maximum(c[:,1],.001)**2
    shot=np.maximum((v5-v1)/4,0);background=np.maximum(v1-shot,0)
    read=np.clip((v60-v1)/4,0,background);sky=background-read
    rows=[]
    for model in models:
        q=convolved_ratio(model['array'],wave,pixel,slit,scale,atmospheres[wv])
        ok=valid&np.isfinite(q)&(q>0)
        denom=np.maximum(q,1e-100)
        phot='j' if band=='h' else band
        reference=model['magnitudes'][phot]
        curves=sample_times(shot/denom,sky/denom**2,read/denom**2,ok,reference)
        rows.append(dict(spt=model['spt'],sptn=model['sptn'],teff=model['teff'],mode=mode,band=band,
            photometry_band=phot,camera=camera,grating=grating,pixel_scale=scale,airmass=airmass,slit=slit,
            center_um=BANDS[band],resolving_power=BANDS[band]/(pixel*slit/scale),
            spectral_slit_pixels=slit/scale,wavelength_range_um=[float(wave[0]),float(wave[-1])],
            seeing_fwhm=seeing,slit_seeing_ratio=slit/seeing,valid_fraction=float(ok.mean()),
            timing_log_i32=pack_curves(curves)))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--j-filter',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--atmosphere50',type=Path,required=True)
    p.add_argument('--atmosphere-any',type=Path,required=True);p.add_argument('--reuse',type=Path)
    p.add_argument('--existing-grid',type=Path,help='Preserve calibrated long/111 rows from this JSON/gzip grid')
    p.add_argument('--workers',type=int,default=3);p.add_argument('--cameras',nargs='+',choices=['long','short'],default=['long','short'])
    p.add_argument('--gratings',nargs='+',type=int,choices=[10,32,111],default=[10,32,111]);p.add_argument('--slits',nargs='+',type=float,choices=SLITS,default=SLITS)
    p.add_argument('--bands',nargs='+',choices=list(BANDS),default=list(BANDS));p.add_argument('--modes',nargs='+',choices=list(MODES),default=list(MODES))
    p.add_argument('--airmasses',nargs='+',type=float,choices=[1.5,2.0],default=[1.5,2.0])
    args=p.parse_args();(args.output/'calibrations').mkdir(parents=True,exist_ok=True)
    old=json.loads((args.source/'grid.json').read_text());filters={'j':filter_response(args.j_filter),'k':filter_response(args.source/'2mass_Ks.xml')}
    models=[]
    for meta in old['models']:
        data=(args.source/(meta['spt']+'.sed')).read_bytes()
        if hashlib.sha256(data).hexdigest()!=meta['sed_sha256']:raise ValueError('Public model checksum mismatch')
        sed=np.loadtxt(StringIO(data.decode()))
        models.append({**meta,'array':sed,'magnitudes':{b:synthetic_mag(sed,f) for b,f in filters.items()}})
    base=json.loads((args.source/'T0_b12_x1.5_f1_t300.json').read_text())['inputs']
    atmospheres={'PERCENT_50':np.loadtxt(args.atmosphere50),'ANY':np.loadtxt(args.atmosphere_any)}
    reuse={}
    if args.reuse:
        for f in args.reuse.glob('*.json'):
            d=json.loads(f.read_text())
            if 'inputs' in d and f.with_suffix('.npz').exists():reuse[hashlib.sha256(json.dumps(d['inputs'],sort_keys=True).encode()).hexdigest()]=f
    preserved=[]
    if args.existing_grid:
        data=args.existing_grid.read_bytes();existing=json.loads(gzip.decompress(data) if data.startswith(b'\x1f\x8b') else data)
        for r in existing['rows']:
            if 'long' not in args.cameras or 111 not in args.gratings:continue
            if r.get('camera','long')!='long' or r.get('grating',111)!=111:continue
            if r['band'] not in args.bands or r['slit'] not in args.slits or r['mode'] not in args.modes or r['airmass'] not in args.airmasses:continue
            preserved.append({**{k:v for k,v in r.items() if k!='curves'},'camera':'long','grating':111,'pixel_scale':.05,
                'spectral_slit_pixels':r['slit']/.05,'timing_log_i32':pack_curves(r['curves'])})
    known={(r['camera'],r['grating'],r['band'],r['mode'],r['airmass'],r['slit']) for r in preserved}
    jobs=[(cam,g,b,m,x,s) for cam in args.cameras for g in args.gratings for b in args.bands
          for m in args.modes for x in args.airmasses for s in args.slits
          if not (cam=='short' and g==10) and (cam,g,b,m,x,s) not in known]
    rows=preserved;failed=[];start=time.monotonic()
    print(f'{datetime.now().isoformat(timespec="seconds")} Starting {len(jobs)} public calibrations; preserving {len(preserved)} existing rows',flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(calibration,j,args,base,reuse,models,atmospheres):j for j in jobs}
        for i,f in enumerate(as_completed(futures),1):
            try:rows.extend(f.result())
            except Exception as e:failed.append((futures[f],str(e)));print('FAILED',futures[f],str(e)[:300],flush=True)
            if i%5==0 or i==len(jobs):print(f'{datetime.now().isoformat(timespec="seconds")} {i}/{len(jobs)} calibrated; {len(failed)} failures; elapsed {time.monotonic()-start:.0f}s',flush=True)
    if failed:raise RuntimeError(f'{len(failed)} failures; rerun reuses completed calibrations')
    rows.sort(key=lambda r:(r['camera'],r['grating'],r['mode'],r['band'],r['slit'],r['airmass'],r['sptn']))
    grid={**{k:v for k,v in old.items() if k not in ['rows','camera','grating']},'version':'2026-09-28-rv-cameras-gratings-v3',
        'created_at':datetime.now(timezone.utc).isoformat(),'cameras':args.cameras,'gratings':args.gratings,
        'camera_gratings':{cam:[g for g in args.gratings if not (cam=='short' and g==10)] for cam in args.cameras},
        'magnitude_start':8.,'magnitude_step':.25,'magnitude_count':65,'coverage_fractions':FRACTIONS,
        'frames':FRAMES,'timing_encoding':'base64-i32-le-ceil','timing_log_scale':SCALE,'timing_null':NULL,'slits':args.slits,
        'calibration_method':'Gemini flat-photon noise coefficients, public Sonora SEDs convolved and integrated over detector pixels; original long/111 direct-ITC rows retained',
        'rows':rows}
    path=args.output/'grid.json.gz'
    with gzip.open(path,'wt',compresslevel=6) as out:json.dump(grid,out,separators=(',',':'),allow_nan=False)
    print(f'{datetime.now().isoformat(timespec="seconds")} Wrote {len(rows)} rows; {path.stat().st_size/1e6:.2f} MB gzip',flush=True)


if __name__=='__main__':main()
