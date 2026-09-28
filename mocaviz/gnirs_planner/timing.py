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
    if band=='auto_h_l8':band='k' if r['sptn']<=17 else 'h'
    elif band in ('auto','auto_h'):band='k' if r['sptn']<23 else ('h' if band=='auto_h' else 'j')
    airmass=(1.5 if (r['win15'] or 0)>=max(f['minWindow'],.5) else 2) if f['airmass']=='auto' else float(f['airmass'])
    choices=model.get((band,airmass),[])
    row=min(choices,key=lambda p:(abs(p['sptn']-r['sptn']),p['sptn'])) if choices else None
    return band,airmass,row

# Recommended read modes from Gemini GNIRS components. Short-frame S/N uses
# a rigorous upper bound on the existing 60-s curve: scaling all variance by
# max(1, (RN/7)^2 * 60/frame) bounds the changed read term at every pixel.
SHORT_FRAMES=[(.2,'VERY_BRIGHT',155,.7),(.5,'VERY_BRIGHT',155,.7),
              (1,'BRIGHT',30,.7),(2,'BRIGHT',30,.7),(5,'BRIGHT',30,.7),
              (10,'BRIGHT',30,.7),(20,'FAINT',10,11.14),(40,'FAINT',10,11.14)]

def detector_rate(mag,row):
    if not row or mag is None:return None
    values=[row.get(k) for k in ('peak_source_rate','peak_sky_rate','peak_reference_magnitude','peak_limit_electrons')]
    if any(v is None or not math.isfinite(v) for v in values):return None
    star,sky,reference,limit=values
    if star<0 or sky<0 or limit<=0 or limit>50000:return None
    exponent=-.4*(mag-reference)
    if abs(exponent)>100:return None
    return star*10**exponent+sky

def exposure_plan(mag,f,row):
    rate=detector_rate(mag,row)
    if rate is None:return None
    options=[{**c,'read_mode':'VERY_FAINT','overhead':34.3,'noise_bound':1.} for c in row['curves']]
    base=next((c for c in row['curves'] if c['frame_seconds']==60),None)
    if base:
        options += [{**base,'frame_seconds':frame,'read_mode':mode,'overhead':read+8.56+3.5,
                     'noise_bound':max(1.,(rn/7)**2*60/frame)} for frame,mode,rn,read in SHORT_FRAMES]
    plans=[];minimum=f.get('minScienceMinutes',20)*60
    for c in options:
        frame=c['frame_seconds'];peak=rate*frame
        if peak>row['peak_limit_electrons']:continue
        raw=interpolate(mag,c['points'])
        required=raw*(f['snr']/50)**2*f['margin']*c['noise_bound']
        seconds=max(required,minimum)
        if not math.isfinite(seconds) or seconds>1e9:continue
        n=max(4,4*math.ceil(seconds/(4*frame)));science=n*frame
        info=dict(read_mode=c['read_mode'],frame_overhead_seconds=c['overhead'],
                  peak_pixel_upper_bound=peak,peak_limit_electrons=row['peak_limit_electrons'],
                  minimum_science_seconds=minimum,minimum_applied=minimum>required,
                  short_frame_snr_bound=c['noise_bound']>1)
        plans.append((science+n*c['overhead'],n,frame,science,info))
    if not plans:return None
    _,n,frame,science,info=min(plans,key=lambda p:p[:4])
    return n,frame,science,info

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
    if plan is None:
        t['reason']='No detector-count calibration; regenerate the offline ITC grid' if detector_rate(mag,row) is None else 'No safe exposure within the supported read modes / planning range'
        return t
    n,frame,science,info=plan;cycles=n//4
    t.update(science=science,frames=n,frame_seconds=frame,**info)
    window=r['win15'] if airmass==1.5 else r['win2'];capacity=min(f['maxVisit'],window)*3600
    cycle_seconds=4*(frame+info['frame_overhead_seconds'])
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
