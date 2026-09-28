#!/usr/bin/env python3
"""Offline RV grid expansion from public Sonora SEDs and Gemini ITC responses.

Run only on the development machine. Inputs are the previous public RV calibration
bundle and the 2MASS J response. No catalog, passwords or native models are read.
Only compressed per-detector-pixel noise coefficients and compact timing curves
are saved. The web server receives the final timing table, never model spectra.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
import numpy as np
import requests
from bs4 import BeautifulSoup

BANDS={'j':1.30,'h':1.65,'k':2.30}
SLITS=[.10,.15,.20,.30,.45,.675,1.0]
FRACTIONS=[.25,.5,.75,.9,.95]
FRAMES=[60,120,180,240,300]
MODES={'b12':('PERCENT_70','PERCENT_50','PERCENT_50'),
       'b3high':('PERCENT_85','PERCENT_70','ANY'),
       'b3cloud':('PERCENT_85','PERCENT_80','ANY')}

def filter_response(path):
    tree=ET.parse(path)
    pars={e.attrib['name']:e.attrib.get('value') for e in tree.iter() if e.tag.endswith('PARAM')}
    arr=np.array([[float(c.text) for c in e if c.tag.endswith('TD')] for e in tree.iter() if e.tag.endswith('TR')]);arr[:,0]/=1e4
    return arr,float(pars['ZeroPoint'])

def synthetic_mag(sed,response):
    arr,zero=response;w=sed[:,0]/1000;keep=(w>=arr[0,0])&(w<=arr[-1,0]);x=w[keep]
    trans=np.interp(x,arr[:,0],arr[:,1])
    jy=np.trapz(sed[keep,1]*x*trans,x)/np.trapz(2.99792458e-12/x*trans,x)
    return float(-2.5*np.log10(jy/zero))

def sample_times(shot,sky,read,valid,reference_mag):
    output=[];mags=np.arange(8.,24.001,.25)
    q=10**(-.4*(mags-reference_mag))[:,None]
    indices=[max(0,int(np.ceil(f*len(valid)))-1) for f in FRACTIONS]
    for frame in FRAMES:
        with np.errstate(invalid='ignore'):
            required=3600*50**2*(shot[None,:]/q+(sky[None,:]+read[None,:]*300/frame)/q**2)
        required[:,~valid]=np.inf
        # Exact order statistic: ceil(fraction * ALL recorded pixels) must pass.
        # Sorting by required time allows any disjoint union of qualifying pixels.
        selected=np.sort(required,axis=1)[:,indices]
        values={str(f):[float(np.ceil(np.log(t)*1e7)/1e7) if np.isfinite(t) and t>0 else None for t in selected[:,i]] for i,f in enumerate(FRACTIONS)}
        output.append(dict(frame_seconds=frame,log_seconds=values))
    return output

def request(inputs,sed,factor,frame):
    data={**inputs,'psSourceNorm':str(float(inputs['psSourceNorm'])*factor),'numExpA':str(3600//frame),'expTimeA':str(frame)}
    for attempt in range(4):
        try:
            with requests.Session() as session:
                files=[(k,(None,str(v))) for k,v in data.items()]+[('specUserDef',('public-sonora.sed',sed,'text/plain'))]
                r=session.post('https://itc.gemini.edu/itc/servlet/calc',files=files,timeout=(15,90));r.raise_for_status()
                soup=BeautifulSoup(r.text,'html.parser');text=soup.get_text(' ',strip=True)
                link=next((a['href'] for a in soup.select('a[href]') if 'filename=FinalS2NData' in a['href']),None)
                if link is None:raise ValueError(text[-1200:])
                q=session.get('https://itc.gemini.edu'+link,timeout=(15,60));q.raise_for_status()
                arr=np.loadtxt(StringIO(q.text))
                if len(arr)<900:raise ValueError('Incomplete detector spectrum')
                return arr,text
        except Exception:
            if attempt==3:raise
            time.sleep(2*(attempt+1))

def build(job,args,models,old_rows):
    spt,band,mode,airmass,slit=job;model=models[spt]
    name=f'{spt}_{band}_{mode}_x{airmass}_s{slit}'
    path=args.output/(name+'.npz')
    original=next((r for r in old_rows if r['spt']==spt and r['band']==band and r['mode']==mode and r['airmass']==airmass and r['slit']==slit),None)
    old_noise=args.source/f'{spt}_{mode}_x{airmass}_noise.npz'
    iq,cc,wv=MODES[mode]
    inputs={**model['inputs'],'SlitWidth':f'SW_{SLITS.index(slit)+1}',
        'instrumentCentralWavelength':f'{BANDS[band]:.2f}','ImageQuality':iq,'CloudCover':cc,'WaterVapor':wv,'Airmass':str(airmass)}
    digest=hashlib.sha256(json.dumps(dict(inputs=inputs,sed=model['sed_hash']),sort_keys=True).encode()).hexdigest()
    if original and old_noise.exists():
        with np.load(old_noise) as noise: arrays={k:noise[k] for k in noise.files}
        seeing=original['seeing_fwhm']
    elif path.exists():
        with np.load(path) as noise:
            if str(noise['identity'])!=digest:raise ValueError('Calibration identity mismatch: '+name)
            arrays={k:noise[k] for k in ['wavelength_nm','shot','sky','read','valid']};seeing=float(noise['seeing'])
    else:
        payload=model['uploads'][band]
        a,text=request(inputs,payload,1,300);b,_=request(inputs,payload,5,300);c,_=request(inputs,payload,1,60)
        if not np.allclose(a[:,0],b[:,0]) or not np.allclose(a[:,0],c[:,0]):raise ValueError('Mismatched wavelengths')
        valid=(a[:,1]>.01)&(b[:,1]>.01)&(c[:,1]>.01)
        v1=np.divide(1.,a[:,1]**2,out=np.full(len(a),np.inf),where=valid)
        v5=np.divide(25.,b[:,1]**2,out=np.full(len(a),np.inf),where=valid)
        v60=np.divide(1.,c[:,1]**2,out=np.full(len(a),np.inf),where=valid)
        with np.errstate(invalid='ignore'):
            shot=np.maximum((v5-v1)/4,0);background=np.maximum(v1-shot,0)
            read=np.clip((v60-v1)/4,0,background);sky=background-read
        arrays=dict(wavelength_nm=a[:,0],shot=shot,sky=sky,read=read,valid=valid)
        match=re.search(r'derived image size\(FWHM\) for a point source = ([0-9.]+)',text)
        if not match:raise ValueError('ITC omitted seeing')
        seeing=float(match.group(1))
        temporary=path.with_suffix('.building.npz')
        np.savez_compressed(temporary,**arrays,seeing=seeing,identity=digest,uploaded_sed_sha256=hashlib.sha256(payload.encode()).hexdigest())
        temporary.replace(path)
    phot_band='j' if band=='h' else band
    reference_mag=16. if phot_band==model['native_band'] else model['magnitudes'][phot_band]
    curves=sample_times(arrays['shot'],arrays['sky'],arrays['read'],arrays['valid'],reference_mag)
    wave=arrays['wavelength_nm']/1000;center=BANDS[band]
    # Slit-filled nominal R from the ITC detector dispersion and 0.05 arcsec/pixel.
    resolution=center/(float(np.median(np.diff(wave)))*slit/.05)
    result=dict(spt=spt,sptn=model['sptn'],teff=model['teff'],mode=mode,band=band,photometry_band=phot_band,
        airmass=airmass,slit=slit,center_um=center,resolving_power=original['resolving_power'] if original else resolution,
        wavelength_range_um=[float(wave[0]),float(wave[-1])],seeing_fwhm=seeing,slit_seeing_ratio=slit/seeing,
        valid_fraction=float(arrays['valid'].mean()),curves=curves)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--j-filter',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--types',nargs='*');parser.add_argument('--slits',nargs='*',type=float,default=SLITS)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if any(s not in SLITS for s in args.slits):raise ValueError('Unsupported slit')
    old=json.loads((args.source/'grid.json').read_text());models={}
    filters={'j':filter_response(args.j_filter),'k':filter_response(args.source/'2mass_Ks.xml')}
    for m in old['models']:
        if args.types and m['spt'] not in args.types:continue
        sed=(args.source/(m['spt']+'.sed')).read_text();arr=np.loadtxt(StringIO(sed))
        info=json.loads((args.source/f"{m['spt']}_b12_x1.5_f1_t300.json").read_text())
        if hashlib.sha256(sed.encode()).hexdigest()!=m['sed_sha256'] or m['sed_sha256']!=info['sed_sha256']:
            raise ValueError('Public SED differs from its original calibration: '+m['spt'])
        # Read existing modest input spectra once into RAM; no native grid or
        # per-configuration spectrum copies. ITC applies instrumental broadening.
        # Keep the complete J normalization interval plus a generous margin around
        # the requested detector window. No resolution smoothing is added.
        # A comparison with the original full-range upload returned identical S/N.
        wave=arr[:,0]/1000;lines=sed.splitlines(keepends=True);uploads={}
        for band,(lo,hi) in {'j':(1.10,1.40),'h':(1.60,1.70),'k':(2.24,2.36)}.items():
            keep=((wave>=1.10)&(wave<=1.40))|((wave>=lo)&(wave<=hi));keep[0]=keep[-1]=True
            uploads[band]=''.join(line for line,use in zip(lines,keep) if use)
        models[m['spt']]={**m,'uploads':uploads,'inputs':info['inputs'],'sed_hash':hashlib.sha256(sed.encode()).hexdigest(),
            'native_band':m['band'].lower(),'magnitudes':{b:synthetic_mag(arr,v) for b,v in filters.items()}}
    jobs=[(s,b,m,x,slit) for slit in args.slits for b in BANDS for s in models for m in MODES for x in [1.5,2.0]]
    rows=[];failures=[];start=time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending={pool.submit(build,j,args,models,old['rows']):j for j in jobs}
        for future in as_completed(pending):
            try:rows.append(future.result())
            except Exception as exc:failures.append((pending[future],str(exc)));print('FAILED',pending[future],str(exc)[:300],flush=True)
            if (len(rows)+len(failures))%10==0:print(f'{len(rows)} complete; {len(failures)} failed / {len(jobs)}; {time.monotonic()-start:.0f}s',flush=True)
    if failures:raise RuntimeError(f'{len(failures)} configurations failed; rerun to resume from coefficients')
    rows.sort(key=lambda r:(r['mode'],r['band'],r['slit'],r['airmass'],r['sptn']))
    grid={**old,'version':'2026-09-28-rv-jhk-slits-coverage-v2','created_at':datetime.now(timezone.utc).isoformat(),
        'interpolation':'conservative source/background endpoint envelope','magnitude_start':8.,'magnitude_step':.25,'coverage_fractions':FRACTIONS,'slits':args.slits,
        'upload_windows':'J normalization 1.10–1.40 µm plus H 1.60–1.70 or K 2.24–2.36; native sampled flux retained, no extra instrumental convolution',
        'h_normalization':'J photometry and the selected Sonora template color; H photometry is not in the current catalog cache.',
        'rows':rows}
    path=args.output/'grid.json';path.write_text(json.dumps(grid,separators=(',',':'),allow_nan=False))
    print(f'Wrote {path}: {path.stat().st_size} bytes',flush=True)

if __name__=='__main__':main()
