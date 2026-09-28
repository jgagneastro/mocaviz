"""Cached wavelength-resolved GNIRS RV timing and complete-ABBA accounting."""
from bisect import bisect_right
import math
import zlib
from . import sxd_timing
from .rv_grid import row_curves

MODES={'b12':.15,'b3high':.30,'b3cloud':.30}

def curves(grid,mode,slit='auto',coverage=.75,camera='long',grating=111):
    if grid.get('cross_dispersed'):return sxd_timing.curves(grid,mode)
    mode='b3high' if mode=='b3wide' else mode
    width=MODES[mode] if slit=='auto' else float(slit)
    result={}
    for original in grid['rows']:
        if (original['mode']!=mode or abs(original['slit']-width)>1e-6
                or original.get('camera','long')!=camera or original.get('grating',111)!=int(grating)):continue
        frames=[]
        for c in row_curves(grid,original,coverage):
            if 'log_seconds' in c:
                logs=c['log_seconds'].get(str(float(coverage)))
                if not logs or any(x is None for x in logs):continue
                start=grid.get('magnitude_start',8);step=grid.get('magnitude_step',.25)
                points=[[start+i*step,math.exp(x)] for i,x in enumerate(logs)]
            else:
                if coverage!=.75:continue
                points=c['points'];logs=[math.log(p[1]) for p in points]
            frames.append({**c,'points':points,'log_times':logs})
        row={**original,'curves':frames}
        result.setdefault((row['band'],row['airmass']),[]).append(row)
    if not result:raise ValueError('No cached RV exposure grid for this camera, grating, slit and weather setup')
    return result

def interpolate(mag,points):
    if mag is None or len(points)<2:return None
    if mag<points[0][0]:return points[0][1]*10**(.4*(mag-points[0][0]))
    if mag>points[-1][0]:
        exponent=.8*(mag-points[-1][0])
        return math.inf if exponent>100 else points[-1][1]*10**exponent
    i=max(0,min(len(points)-2,bisect_right([p[0] for p in points],mag)-1))
    x,y=points[i];x2,y2=points[i+1]
    # Source and background variances scale as 10**(.4*m) and 10**(.8*m).
    # Either endpoint therefore provides an upper bound, even when the pixel
    # defining the coverage quantile changes between sampled magnitudes.
    return min(y*10**(.8*(mag-x)),y2*10**(-.4*(x2-mag)))

def setup(r,f,model):
    band=f.get('rvBand','auto')
    if band in ('auto','auto_h'):band='k' if r['sptn']<23 else ('h' if band=='auto_h' else 'j')
    airmass=(1.5 if (r['win15'] or 0)>=max(f['minWindow'],.5) else 2) if f['airmass']=='auto' else float(f['airmass'])
    choices=model.get((band,airmass),[])
    row=min(choices,key=lambda p:(abs(p['sptn']-r['sptn']),p['sptn'])) if choices else None
    return band,airmass,row

def exposure_plan(mag,f,row):
    if mag is None or row is None:return None
    plans=[]
    for c in row['curves']:
        if 8<=mag<=24:
            index=min(63,int((mag-8)*4));weight=(mag-8)*4-index
            logs=c['log_times']
            raw=math.exp(min(logs[index]+math.log(10)*.8*.25*weight,
                logs[index+1]-math.log(10)*.4*.25*(1-weight)))
        else:raw=interpolate(mag,c['points'])
        seconds=raw*(f['snr']/50)**2*f['margin']
        if not math.isfinite(seconds) or seconds>1e9:continue
        frame=c['frame_seconds'];n=max(4,4*math.ceil(seconds/(4*frame)))
        science=n*frame
        plans.append((science+n*34.3,n,frame,science))
    if not plans:return None
    _,n,frame,science=min(plans)
    return n,frame,science

def band3_science_seconds(r,f,model):
    if model.get('_sxd'):return sxd_timing.estimate(r,f,model)['science']
    band,airmass,row=setup(r,f,model)
    plan=exposure_plan(r[row.get('photometry_band',band)] if row else None,f,row)
    return plan[2] if plan else None

def estimate(r,f,model):
    if model.get('_sxd'):return sxd_timing.estimate(r,f,model)
    band,airmass,row=setup(r,f,model)
    phot_band=row.get('photometry_band',band) if row else ('j' if band=='h' else band)
    mag=r[phot_band]
    points=row['curves'][0]['points'] if row and row['curves'] else []
    t=dict(science=None,program=None,telescope=None,visits=None,band=band,mag=mag,photometry_band=phot_band,
        model_color_normalization=phot_band!=band,
        camera=row.get('camera','long') if row else f.get('rvCamera','long'),
        grating=row.get('grating',111) if row else int(f.get('rvGrating',111)),
        pixel_scale=row.get('pixel_scale',.05) if row else None,
        spectral_slit_pixels=row.get('spectral_slit_pixels',row['slit']/.05) if row else None,
        slit=row['slit'] if row else None,
        center_um=row['center_um'] if row else None,
        resolving_power=row['resolving_power'] if row else None,
        wavelength_range_um=row['wavelength_range_um'] if row else None,
        template_spt=row['spt'] if row else None,template_family=('diamondback' if row['sptn']<=22 else 'elf-owl') if row else None,template_teff=row['teff'] if row else None,
        template_approximate=bool(row and r['sptn']!=row['sptn']),
        template_outside_grid=bool(row and (r['sptn']<10 or r['sptn']>30)),
        seeing_fwhm=row['seeing_fwhm'] if row else None,
        slit_seeing_ratio=row['slit_seeing_ratio'] if row else None,
        coverage_fraction=f.get('coverageFraction',.75),
        extrapolated=mag is not None and bool(points) and (mag<points[0][0] or mag>points[-1][0]),
        reason=None,fit=False,airmass=airmass)
    if mag is None or row is None:t['reason']='No usable '+phot_band.upper()+' photometry / RV ITC grid';return t
    if not row['curves']:t['reason']='Requested S/N coverage is unsupported by the cached detector pixels';return t
    plan=exposure_plan(mag,f,row)
    if plan is None:t['reason']='Exposure exceeds supported planning range';return t
    n,frame,science=plan;cycles=n//4
    t.update(science=science,frames=n,frame_seconds=frame,brightReadmodeReview=mag<11)
    window=r['win15'] if airmass==1.5 else r['win2'];capacity=min(f['maxVisit'],window)*3600
    cycle_seconds=4*(frame+34.3)
    per_visit=min(cycles,max(0,math.floor((capacity-900)/cycle_seconds)))
    def duration(c):return 900+c*cycle_seconds+math.floor(c*4*frame/2700)*360
    while per_visit>0 and duration(per_visit)>capacity+1e-6:per_visit-=1
    if not per_visit:t['reason']='No full ABBA sequence + acquisition fits the night window';return t
    full,remainder=divmod(cycles,per_visit);visits=full+bool(remainder)
    program=full*duration(per_visit)+(duration(remainder) if remainder else 0);longest=duration(per_visit)
    hist=zlib.decompress(r['hist15'] if airmass==1.5 else r['hist2'])
    eligible=sum(hist[math.ceil((longest-1e-6)/300):])
    shorter=sum(hist[math.ceil((duration(remainder)-1e-6)/300):]) if remainder else eligible
    fit=eligible>=full and shorter>=visits
    t.update(program=program,telescope=program+visits*f['calibrationMinutes']*60,visits=visits,
        longest_visit=longest,window=window,eligible_nights=eligible,fit=fit,
        reason=None if fit else 'Too few sampled nights fit all planned visits')
    return t
