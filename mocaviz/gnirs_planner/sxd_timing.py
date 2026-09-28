"""Local interpolation of independently calibrated SXD noise and visit costs."""
from bisect import bisect_right
import math
import zlib

def curves(grid,mode):
    rows=[r for r in grid['rows'] if r['mode']==mode]
    if not rows:raise ValueError('No SXD ITC grid for '+mode)
    for row in rows:
        for c in row['curves']:
            c['logs']={k:[math.log(p[1]) for p in pts] for k,pts in c['criteria'].items()}
    return {'_sxd':True,'rows':rows,'cache_key':grid['cache_key']}

def setup(r,f,model):
    x=(1.5 if (r['win15'] or 0)>=max(f['minWindow'],.5) else 2.) if f['airmass']=='auto' else float(f['airmass'])
    rows=[row for row in model['rows'] if row['airmass']==x]
    type_proxy=6 if r['sptn']<8.5 else r['sptn']
    row=min(rows,key=lambda p:(abs(p['sptn']-type_proxy),p['sptn'])) if rows else None
    return x,row

def exposure_plan(mag,f,row):
    if mag is None or row is None or not 8<=mag<=24:return None
    criterion=f"{f['snrUnit']}:{f['coverageFraction']:g}"
    q=10**(-.4*(mag-16));plans=[]
    for c in row['curves']:
        frame=c['frame_seconds']
        peak=(row['peak_source_rate']*q+row['peak_sky_rate'])*frame
        if not math.isfinite(peak) or peak<0 or peak>50000:continue
        logs=c['logs'][criterion];index=min(63,int((mag-8)*4));weight=(mag-8)*4-index
        seconds=math.exp(logs[index]+weight*(logs[index+1]-logs[index]))*(f['snr']/30)**2*f['margin']
        if not math.isfinite(seconds) or seconds>1e9:continue
        n=max(4,4*math.ceil(max(seconds,f.get('minScienceMinutes',20)*60)/(4*frame)))
        science=n*frame;frame_overhead=c['read_seconds']+8.56+7/2
        plans.append((science+n*frame_overhead,n,frame,science,c,peak))
    return min(plans,key=lambda p:p[:4]) if plans else None

def estimate(r,f,model):
    x,row=setup(r,f,model);mag=r['j']
    t=dict(science=None,program=None,telescope=None,visits=None,band='j',mag=mag,
        slit=.45,center_um=1.65,resolving_power=1600*.3/.45,wavelength_range_um=[.85,2.5],
        timing_interval_um=[1.2,1.3],snr_unit=f['snrUnit'],coverage_fraction=f['coverageFraction'],
        template_spt=row['spt'] if row else None,template_teff=row['teff'] if row else None,
        template_family=row['family'] if row else None,
        template_approximate=bool(row and row['sptn']!=r['sptn']),
        template_outside_grid=bool(row and (r['sptn']<6 or r['sptn']>30)),
        seeing_fwhm=row['seeing_fwhm'] if row else None,
        slit_seeing_ratio=row['slit_seeing_ratio'] if row else None,
        extrapolated=False,fit=False,reason=None,airmass=x,grid_key=model['cache_key'],
        brightReadmodeReview=mag is not None and mag<12)
    if mag is None or row is None:
        t['reason']='No usable J photometry / SXD ITC grid';return t
    if not 8<=mag<=24:
        t['reason']='J magnitude outside validated SXD grid (8–24); no extrapolation';return t
    plan=exposure_plan(mag,f,row)
    if plan is None:
        t['reason']='No unsaturated frame / supported integration in SXD grid';return t
    _,n,frame,science,c,peak=plan;cycles=n//4
    frame_overhead=c['read_seconds']+8.56+7/2
    cycle_seconds=4*(frame+frame_overhead)
    # 15 min acquisition matches the live ITC, conservatively above the
    # 12 min web-table value. Each new visit starts with an acquisition.
    def duration(count):
        s=count*4*frame
        return 900+count*cycle_seconds+max(0,math.ceil(s/2700)-1)*360
    window=r['win15'] if x==1.5 else r['win2']
    capacity=min(f['maxVisit'],window or 0)*3600
    # Allow baseline calibration time in the window and block budget as well.
    allowance=f['calibrationMinutes']*60
    per_visit=min(cycles,7200//(4*frame),max(0,math.floor((capacity-900-allowance)/cycle_seconds)))
    while per_visit>0 and duration(per_visit)+allowance>capacity+1e-6:per_visit-=1
    t.update(science=science,frames=n,frame_seconds=frame,read_mode=c['read_mode'],
             peak_pixel_upper_bound=peak,peak_limit_electrons=50000,minimum_science_seconds=f.get('minScienceMinutes',20)*60,acquisition_seconds=900,frame_overhead_seconds=frame_overhead)
    if not per_visit:
        t['reason']='No full ABBA + acquisition + calibration allowance fits the night window';return t
    full,remainder=divmod(cycles,int(per_visit));visits=full+bool(remainder)
    program=full*duration(per_visit)+(duration(remainder) if remainder else 0)
    longest=duration(per_visit)+allowance
    hist=zlib.decompress(r['hist15'] if x==1.5 else r['hist2'])
    eligible=sum(hist[math.ceil((longest-1e-6)/300):])
    shorter=sum(hist[math.ceil((duration(remainder)+allowance-1e-6)/300):]) if remainder else eligible
    fit=eligible>=full and shorter>=visits
    t.update(program=program,telescope=program+visits*allowance,visits=visits,
        longest_visit=longest,window=window,eligible_nights=eligible,fit=fit,
        reason=None if fit else 'Too few sampled nights fit all planned visits')
    return t
