"""Cached nightly, five-minute GNIRS visibility, including coordinate epochs.

The analytic hour-angle intersections give the same sampled windows as a full
five-minute altitude grid, without forming a targets × nights × times cube.
Apparent CIRS coordinates are evaluated at each night's midpoint; the within-
night variation is negligible relative to the five-minute planning resolution.
"""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import json
import warnings
import zlib

import numpy as np

VERSION=5

def pack(value):return zlib.compress(json.dumps(value,separators=(',',':')).encode(),3)
def unpack(value):return json.loads(zlib.decompress(value)) if isinstance(value,bytes) else json.loads(value)

@lru_cache(maxsize=1)
def astronomy():
    # Normal catalog browsing needs no astronomy imports. Keep registration of
    # this optional page from breaking other MOCAviz pages on older runtimes.
    from astropy import units as u
    from astropy.coordinates import AltAz,CIRS,EarthLocation,SkyCoord,get_sun
    from astropy.time import Time
    from astropy.utils import iers
    return u,AltAz,CIRS,EarthLocation,SkyCoord,get_sun,Time,iers

@lru_cache(maxsize=2)
def grid(config_json):
    u,AltAz,CIRS,EarthLocation,SkyCoord,get_sun,Time,iers=astronomy()
    config=json.loads(config_json)
    iers.conf.auto_download=False;iers.conf.auto_max_age=None;iers.conf.iers_degraded_accuracy='warn'
    start=date.fromisoformat(config['first_evening']);end=date.fromisoformat(config['last_evening'])
    evenings=[start+timedelta(days=i) for i in range((end-start).days+1)]
    minutes=np.arange(0,14*60+1,config['step_minutes'])
    stamps=[[datetime.combine(d+timedelta(days=1),datetime.min.time(),timezone.utc)+timedelta(hours=4,minutes=int(m)) for m in minutes] for d in evenings]
    times=Time(stamps)
    site=EarthLocation.from_geodetic(config['site']['longitude_deg']*u.deg,config['site']['latitude_deg']*u.deg,config['site']['height_m']*u.m)
    frame=AltAz(obstime=times,location=site,pressure=0*u.hPa)
    dark=get_sun(times).transform_to(frame).alt.deg<config['sun_altitude_max_deg']
    for i,d in enumerate(evenings):
        if any(date.fromisoformat(a)<=d<=date.fromisoformat(b) for a,b in config['unavailable_evenings']):dark[i]=False
    era=np.unwrap(times.earth_rotation_angle(longitude=site.lon).rad,axis=1)
    lo=np.argmax(dark,axis=1);hi=dark.shape[1]-1-np.argmax(dark[:,::-1],axis=1)
    hi[~dark.any(axis=1)]=-1
    return evenings,stamps,times,site,dark,era,lo,hi

def summaries(rows,config,with_details=False):
    if not rows:return []
    valid=[r for r in rows if r.get('ra') is not None and r.get('dec') is not None]
    if len(valid)!=len(rows):
        computed=iter(summaries(valid,config,with_details))
        empty={'best_airmass':None,'best_utc':None,'best_evening':None,'astrometry':'Missing coordinates','windows':{
            key:{'max_hours':0,'best_start_utc':None,'best_end_utc':None,'first_evening':None,'last_evening':None,
                 'nights_1h':0,'duration_counts':[],'monthly_1h':{}} for key in ('1.5','2','2.5')}}
        return [next(computed) if r.get('ra') is not None and r.get('dec') is not None else (empty,{}) for r in rows]
    u,AltAz,CIRS,EarthLocation,SkyCoord,get_sun,Time,iers=astronomy()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        evenings,stamps,times,site,dark,era,lo,hi=grid(json.dumps(config,sort_keys=True))
        # strftime consults the macOS locale on every call; doing it for every
        # object/night dominated large-catalog builds. These dates are shared.
        months=[evening.isoformat()[:7] for evening in evenings]
        mid=times[:,len(times[0])//2];lat=site.lat.rad
        epochs=np.array([r.get('measurement_epoch_yr') or 2000 for r in rows])
        have_pm=np.array([r.get('measurement_epoch_yr') is not None and r.get('pmra_masyr') is not None and r.get('pmdec_masyr') is not None for r in rows])
        pmra=np.array([r.get('pmra_masyr') or 0 for r in rows])*have_pm
        pmdec=np.array([r.get('pmdec_masyr') or 0 for r in rows])*have_pm
        coords=SkyCoord(ra=np.array([r['ra'] for r in rows])[:,None]*u.deg,
            dec=np.array([r['dec'] for r in rows])[:,None]*u.deg,
            pm_ra_cosdec=pmra[:,None]*u.mas/u.yr,pm_dec=pmdec[:,None]*u.mas/u.yr,
            obstime=Time(epochs[:,None],format='jyear'),frame='icrs')
        propagated=coords.apply_space_motion(new_obstime=mid[None,:])
        directions=SkyCoord(ra=propagated.ra,dec=propagated.dec,frame='icrs')
        apparent=directions.transform_to(CIRS(obstime=mid[None,:],location=site))
        dec=apparent.dec.rad;ra=apparent.ra.rad
        aa=np.sin(lat)*np.sin(dec);bb=np.cos(lat)*np.cos(dec)
        era0=era[:,0];step=np.median(np.diff(era,axis=1),axis=1)
        center=era0+(lo+hi)/2*step
        transit=ra+2*np.pi*np.rint((center-ra)/(2*np.pi))
        best_index=np.clip(np.rint((transit-era0)/step),lo,np.maximum(lo,hi)).astype(int)
        best_sin=aa+bb*np.cos(era0+best_index*step-ra)
        best_sin[:,hi<lo]=-1
        best_night=best_sin.argmax(axis=1)
        windows={}
        for ceiling in [1.5,2.0,2.5]:
            ratio=np.divide(1/ceiling-aa,bb,out=np.full_like(aa,2),where=np.abs(bb)>1e-15)
            radius=np.arccos(np.clip(ratio,-1,1))
            starts=[];ends=[];lengths=[]
            for shift in [-2*np.pi,0,2*np.pi]:
                start=np.maximum(lo,np.ceil((transit+shift-radius-era0)/step-1e-9)).astype(int)
                end=np.minimum(hi,np.floor((transit+shift+radius-era0)/step+1e-9)).astype(int)
                length=np.maximum(0,end-start);length[ratio>1]=0
                starts.append(start);ends.append(end);lengths.append(length)
            choose=np.argmax(lengths,axis=0)[None,:,:]
            starts=np.take_along_axis(np.array(starts),choose,axis=0)[0]
            ends=np.take_along_axis(np.array(ends),choose,axis=0)[0]
            length=np.take_along_axis(np.array(lengths),choose,axis=0)[0]
            windows[f'{ceiling:g}']=(starts,ends,length)
        results=[]
        for b,row in enumerate(rows):
            ni=int(best_night[b]);ti=int(best_index[b,ni]);sin=float(best_sin[b,ni])
            visible=sin>=np.sin(np.radians(config['horizon_deg']))
            summary={'best_airmass':round(1/sin,5) if visible else None,
                'best_utc':stamps[ni][ti].isoformat() if visible else None,
                'best_evening':evenings[ni].isoformat() if visible else None,
                'windows':{},'astrometry':'Reference coordinates propagated nightly with adopted PM' if have_pm[b] else 'Reference/catalog coordinates; no PM propagation (missing epoch or PM)'}
            details={}
            for ceiling,(starts,ends,lengths) in windows.items():
                nn=np.flatnonzero(lengths[b]>0);length=lengths[b,nn]
                best=int(nn[np.argmax(length)]) if len(nn) else None
                histogram=Counter(map(int,length));monthly=Counter(months[int(n)] for n in nn if lengths[b,n]*config['step_minutes']>=60)
                summary['windows'][ceiling]={'max_hours':float(lengths[b,best])*config['step_minutes']/60 if best is not None else 0,
                    'best_start_utc':stamps[best][int(starts[b,best])].isoformat() if best is not None else None,
                    'best_end_utc':stamps[best][int(ends[b,best])].isoformat() if best is not None else None,
                    'first_evening':evenings[int(nn[0])].isoformat() if len(nn) else None,
                    'last_evening':evenings[int(nn[-1])].isoformat() if len(nn) else None,
                    'nights_1h':sum(count for n,count in histogram.items() if n*config['step_minutes']>=60),
                    'duration_counts':sorted([n,c] for n,c in histogram.items()),'monthly_1h':dict(monthly)}
                if with_details:details[ceiling]=[[int(n),int(starts[b,n]),int(ends[b,n])] for n in nn]
            results.append((summary,details))
        return results

def target_windows(row,config):
    _,details=summaries([row],config,True)[0]
    start=date.fromisoformat(config['first_evening']);result={}
    for key,entries in details.items():
        result[key]=[]
        for night,a,b in entries:
            evening=start+timedelta(days=night)
            base=datetime.combine(evening+timedelta(days=1),datetime.min.time(),timezone.utc)+timedelta(hours=4)
            result[key].append({'evening_hst':evening.isoformat(),'start_utc':(base+timedelta(minutes=a*config['step_minutes'])).isoformat(),'end_utc':(base+timedelta(minutes=b*config['step_minutes'])).isoformat(),'hours':(b-a)*config['step_minutes']/60})
    return result
