/* Independent SXD time accounting; seconds throughout, no network calls. */
(function(root){
  'use strict';
  const MODES={b12:{label:'Band 1/2 planning · 0.45″ · IQ70 / CC50 / WV50'},b3high:{label:'Band 3 planning · 0.45″ · IQ85 / CC70 / WVAny'},b3cloud:{label:'Band 3 planning · 0.45″ · IQ85 / CC80 / WVAny'}};
  function timing(r,f,grid){
    const x=f.airmass==='auto'?((r.visibility?.windows?.['1.5']?.max_hours||0)>=Math.max(f.minWindow,.5)?1.5:2):Number(f.airmass);
    const phot=r.photometry?.j,mag=phot?.magnitude??null;
    const typeProxy=r.sptn<8.5?6:r.sptn;
    const row=(grid?.rows||[]).filter(v=>v.mode===f.mode&&v.airmass===x).sort((a,b)=>Math.abs(a.sptn-typeProxy)-Math.abs(b.sptn-typeProxy)||a.sptn-b.sptn)[0];
    const t={science:null,program:null,telescope:null,visits:null,band:'j',mag,photometry:phot||null,
      slit:.45,center_um:1.65,resolving_power:1600*.3/.45,wavelength_range_um:[.85,2.5],
      timing_interval_um:[1.2,1.3],snr_unit:f.snrUnit,coverage_fraction:f.coverageFraction,
      template_spt:row?.spt??null,template_teff:row?.teff??null,template_family:row?.family??null,
      template_approximate:!!row&&row.sptn!==r.sptn,template_outside_grid:!!row&&(r.sptn<6||r.sptn>30),
      seeing_fwhm:row?.seeing_fwhm??null,slit_seeing_ratio:row?.slit_seeing_ratio??null,
      extrapolated:false,fit:false,reason:null,airmass:x,grid_key:grid?.cache_key,
      brightReadmodeReview:mag!==null&&mag<12};
    if(mag===null||!row)return {...t,reason:'No usable J photometry / SXD ITC grid'};
    if(mag<8||mag>24)return {...t,reason:'J magnitude outside validated SXD grid (8–24); no extrapolation'};
    const q=10**(-.4*(mag-16)),criterion=`${f.snrUnit}:${f.coverageFraction}`;
    const plans=row.curves.map(c=>{
      const frame=c.frame_seconds,peak=(row.peak_source_rate*q+row.peak_sky_rate)*frame;
      if(peak>50000)return null;
      const p=c.criteria[criterion],i=Math.min(63,Math.floor((mag-8)*4)),weight=(mag-8)*4-i;
      const seconds=Math.exp(Math.log(p[i][1])+weight*(Math.log(p[i+1][1])-Math.log(p[i][1])))*(f.snr/30)**2*f.margin;
      if(!Number.isFinite(seconds)||seconds>1e9)return null;
      const n=Math.max(4,4*Math.ceil(seconds/(4*frame))),science=n*frame,overhead=c.read_seconds+8.56+7/2;
      return {c,frame,peak,n,science,overhead,cost:science+n*overhead};
    }).filter(Boolean).sort((a,b)=>a.cost-b.cost||a.n-b.n||a.frame-b.frame);
    if(!plans.length)return {...t,reason:'No unsaturated frame / supported integration in SXD grid'};
    const {c,frame,peak,n,science,overhead}=plans[0],cycles=n/4,cycleSeconds=4*(frame+overhead);
    Object.assign(t,{science,frames:n,frame_seconds:frame,read_mode:c.read_mode,peak_pixel_upper_bound:peak,acquisition_seconds:900,frame_overhead_seconds:overhead});
    const duration=count=>900+count*cycleSeconds+Math.max(0,Math.ceil(count*4*frame/2700)-1)*360;
    const win=r.visibility?.windows?.[String(x)],window=win?.max_hours||0,capacity=Math.min(f.maxVisit,window)*3600,allowance=f.calibrationMinutes*60;
    let perVisit=Math.min(cycles,Math.floor(7200/(4*frame)),Math.max(0,Math.floor((capacity-900-allowance)/cycleSeconds)));
    while(perVisit>0&&duration(perVisit)+allowance>capacity+1e-6)perVisit--;
    if(!perVisit)return {...t,reason:'No full ABBA + acquisition + calibration allowance fits the night window'};
    const full=Math.floor(cycles/perVisit),remainder=cycles%perVisit,visits=full+Number(!!remainder);
    const program=full*duration(perVisit)+(remainder?duration(remainder):0),longest=duration(perVisit)+allowance;
    const countNights=seconds=>(win?.duration_counts||[]).filter(w=>w[0]*300>=seconds-1e-6).reduce((sum,w)=>sum+w[1],0);
    const eligible=countNights(longest),shorter=remainder?countNights(duration(remainder)+allowance):eligible;
    const fit=eligible>=full&&shorter>=visits;
    return {...t,program,telescope:program+visits*allowance,visits,longest_visit:longest,window,eligible_nights:eligible,fit,reason:fit?null:'Too few sampled nights fit all planned visits'};
  }
  const api={MODES,timing};if(typeof module!=='undefined')module.exports=api;else root.GNIRSSXD=api;
})(typeof window!=='undefined'?window:globalThis);
