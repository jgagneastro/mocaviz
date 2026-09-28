/* Pure GNIRS selection and time accounting. Units are seconds and percentages. */
(function(root){
  'use strict';
  const SXD=typeof module!=='undefined'?require('./sxd-logic.js'):root.GNIRSSXD;
  const finite=v=>v!==null&&v!==undefined&&Number.isFinite(Number(v));
  const MODES=Object.freeze({
    b12:{label:'Band 1/2 · IQ70 / CC50 / WV50',slit:.15},
    b3high:{label:'Band 3 · IQ85 / CC70 / WVAny',slit:.30},
    b3cloud:{label:'Band 3 · IQ85 / CC80 / WVAny',slit:.30}
  });
  const DEFAULT_AID_EXCLUSIONS=['CRIUS','OCSN','HSC','CWNU','HURE'];
  const defaultAidSelected=value=>!['COH23','CUMA','CVUL'].includes(value)&&!DEFAULT_AID_EXCLUSIONS.some(prefix=>value.startsWith(prefix));
  const defaultObservableSelected=value=>value!=='pm';
  const DEFAULTS=Object.freeze({observingMode:'rv',snrUnit:'pixel',coverageFraction:.75,timeMetric:'science',rvBand:'auto_h_l8',rvSlit:'0.3',rvCamera:'short',rvGrating:'111',rvMode:'none',referenceBypass:true,rvMaxErrorEnabled:false,rvMaxError:3,
    membershipEnabled:true,probKind:'summed',prob:85,realAssociation:true,uncontaminated:true,
    uvwEnabled:true,uvw:6,uvwLooseEnabled:true,uvwLoose:4.2,
    ageEnabled:false,ageMin:0,ageMax:300,unknownAge:'include',
    distanceEnabled:false,distanceMax:80,unknownDistance:'include',associationDistanceEnabled:true,associationDistanceMax:120,
    sptMin:10,sptMax:35,teffEnabled:false,teffMin:100,teffMax:3000,
    excludePhotometricSpt:true,excludePhotometricDistance:false,excludeBadSpiff:false,
    rejectDuplicates:true,ignoreMultiples:false,excludeSubdwarfs:true,requireLowg:false,
    conditionalLowg:true,lowgSpt:19,lowgAge:200,hostMin:0,
    quality:'all',manualTypesOnly:false,excludeArchive:true,archiveResolution:2700,excludePlanned:true,
    mode:'b12',snr:30,airmass:'auto',timeEnabled:true,maxScience:4,excludeFastBand3:false,margin:1,minScienceMinutes:20,
    calibrationMinutes:20,maxVisit:2,bestAirmassEnabled:true,bestAirmass:1.6,
    requireVisitFit:true,minWindow:1,restrictDec:true,restrictRa:true,excludeRestrictedAccess:true,
    includeOids:[],bypassNoMeasuredRvOids:[11199,11063,369949,7210,371766],excludeOids:[],aids:null,observables:null});
  const parseOidList=v=>[...new Set(String(v??'').split(/[\s,;]+/).filter(x=>/^\d+$/.test(x)).map(Number))];
  const aid=r=>r.moca_aid||'FIELD / unknown';
  const sptLabel=n=>{if(!finite(n))return 'unknown';const c=['M','L','T','Y'];return (c[Math.floor(n/10)]||'?')+Number((n%10).toFixed(1));};
  function rowCurves(grid,row,coverage){
    if(!row.timing_log_i32)return row.curves;
    if(grid.timing_encoding!=='base64-i32-le-ceil')throw Error('Unsupported timing encoding');
    const binary=typeof Buffer!=='undefined'?Buffer.from(row.timing_log_i32,'base64'):Uint8Array.from(atob(row.timing_log_i32),c=>c.charCodeAt(0));
    const data=new DataView(binary.buffer,binary.byteOffset,binary.byteLength),n=grid.magnitude_count,fi=grid.coverage_fractions.indexOf(coverage);
    if(fi<0||data.byteLength!==4*grid.frames.length*grid.coverage_fractions.length*n)throw Error('Incomplete packed timing row');
    return grid.frames.map((frame,j)=>({frame_seconds:frame,log_seconds:{[String(coverage)]:Array.from({length:n},(_,i)=>{
      const value=data.getInt32(4*((j*grid.coverage_fractions.length+fi)*n+i),true);
      return value===grid.timing_null?null:value/grid.timing_log_scale;
    })}}));
  }
  function curve(grid,mode,band,airmass,sptn,slit='auto',coverage=.75,camera='long',grating=111){
    mode=mode==='b3wide'?'b3high':mode;
    const width=slit==='auto'?MODES[mode].slit:Number(slit);
    const choices=grid.rows.filter(r=>r.mode===mode&&r.band===band&&r.airmass===airmass&&Math.abs(r.slit-width)<1e-6&&(r.camera||'long')===camera&&(r.grating??111)===Number(grating));
    const row=choices.sort((a,b)=>Math.abs(a.sptn-sptn)-Math.abs(b.sptn-sptn)||a.sptn-b.sptn)[0];
    if(!row)return null;
    return {...row,curves:rowCurves(grid,row,coverage).flatMap(c=>{
      if(!c.log_seconds)return coverage===.75?[c]:[];
      const logs=c.log_seconds[String(coverage)];
      return logs?.length&&logs.every(v=>v!==null)?[{...c,points:logs.map((v,i)=>[(grid.magnitude_start??8)+i*(grid.magnitude_step??.25),Math.exp(v)])}]:[];
    })};
  }
  function interpolateTime(mag,points){
    if(!finite(mag)||points.length<2)return null;
    const first=points[0],last=points.at(-1);
    if(mag<first[0])return first[1]*10**(.4*(mag-first[0]));
    if(mag>last[0])return last[1]*10**(.8*(mag-last[0]));
    for(let i=1;i<points.length;i++)if(mag<=points[i][0]){
      const [x,y]=points[i-1],[x2,y2]=points[i];
      return Math.min(y*10**(.8*(mag-x)),y2*10**(-.4*(x2-mag)));
    }
    return last[1];
  }
  function timing(r,f,grid){
    if(f.observingMode==='sxd')return SXD.timing(r,f,grid);
    if(f.airmass==='auto')f={...f,airmass:(r.visibility?.windows?.['1.5']?.max_hours||0)>=Math.max(f.minWindow,.5)?1.5:2};
    else f={...f,airmass:Number(f.airmass)};
    const setting=f.rvBand||'auto';
    const band=setting==='auto_h_l8'?(r.sptn<=17?'k':'h'):['auto','auto_h'].includes(setting)?(r.sptn<23?'k':setting==='auto_h'?'h':'j'):setting;
    const row=curve(grid,f.mode,band,f.airmass,r.sptn,f.rvSlit??'auto',f.coverageFraction??.75,f.rvCamera??'long',f.rvGrating??111),points=row?.curves[0]?.points||[];
    const photBand=row?.photometry_band||(band==='h'?'j':band),phot=r.photometry?.[photBand],mag=phot?.magnitude;
    const base={science:null,program:null,telescope:null,visits:null,band,mag:mag??null,photometry_band:photBand,model_color_normalization:photBand!==band,
      slit:row?.slit??null,center_um:row?.center_um??null,resolving_power:row?.resolving_power??null,
      camera:row?.camera??f.rvCamera??'long',grating:row?.grating??Number(f.rvGrating??111),pixel_scale:row?.pixel_scale??.05,
      spectral_slit_pixels:row?.spectral_slit_pixels??(row?row.slit/.05:null),
      wavelength_range_um:row?.wavelength_range_um??null,template_spt:row?.spt??null,
      template_teff:row?.teff??null,template_family:row?(row.sptn<=22?'diamondback':'elf-owl'):null,template_approximate:!!row&&r.sptn!==row.sptn,
      template_outside_grid:!!row&&(r.sptn<10||r.sptn>30),
      seeing_fwhm:row?.seeing_fwhm??null,slit_seeing_ratio:row?.slit_seeing_ratio??null,coverage_fraction:f.coverageFraction??.75,
      extrapolated:finite(mag)&&points.length>0&&(mag<points[0][0]||mag>points.at(-1)[0]),
      reason:null,fit:false,photometry:phot||null,airmass:f.airmass};
    if(!finite(mag)||!row)return {...base,reason:'No usable '+photBand.toUpperCase()+' photometry / RV ITC grid'};
    if(!row.curves.length)return {...base,reason:'Requested S/N coverage is unsupported by the cached detector pixels'};
    const safety=[row.peak_source_rate,row.peak_sky_rate,row.peak_reference_magnitude,row.peak_limit_electrons];
    if(safety.some(v=>!finite(v))||safety[0]<0||safety[1]<0||safety[3]<=0||safety[3]>50000||Math.abs(-.4*(mag-safety[2]))>100)
      return {...base,reason:'No detector-count calibration; regenerate the offline ITC grid'};
    const rate=safety[0]*10**(-.4*(mag-safety[2]))+safety[1],minimum=(f.minScienceMinutes??20)*60;
    const options=row.curves.map(c=>({...c,read_mode:'VERY_FAINT',overhead:34.3,noise_bound:1}));
    const reference=row.curves.find(c=>c.frame_seconds===60);
    if(reference)for(const [frame,mode,rn,read] of [[.2,'VERY_BRIGHT',155,.7],[.5,'VERY_BRIGHT',155,.7],[1,'BRIGHT',30,.7],[2,'BRIGHT',30,.7],[5,'BRIGHT',30,.7],[10,'BRIGHT',30,.7],[20,'FAINT',10,11.14],[40,'FAINT',10,11.14]])
      options.push({...reference,frame_seconds:frame,read_mode:mode,overhead:read+8.56+3.5,noise_bound:Math.max(1,(rn/7)**2*60/frame)});
    const plans=options.map(c=>{
      const frame=c.frame_seconds,peak=rate*frame;
      if(peak>row.peak_limit_electrons)return null;
      const required=interpolateTime(mag,c.points)*(f.snr/50)**2*f.margin*c.noise_bound,seconds=Math.max(required,minimum);
      if(!Number.isFinite(seconds)||seconds>1e9)return null;
      const n=Math.max(4,4*Math.ceil(seconds/(4*frame))),science=n*frame;
      return {n,frame,science,required,c,peak,cost:science+n*c.overhead};
    }).filter(Boolean).sort((a,b)=>a.cost-b.cost||a.n-b.n||a.frame-b.frame);
    if(!plans.length)return {...base,reason:'No safe exposure within the supported read modes / planning range'};
    const {n,frame,science,required,c,peak}=plans[0],cycles=n/4;
    Object.assign(base,{read_mode:c.read_mode,frame_overhead_seconds:c.overhead,peak_pixel_upper_bound:peak,
      peak_limit_electrons:row.peak_limit_electrons,minimum_science_seconds:minimum,minimum_applied:minimum>required,short_frame_snr_bound:c.noise_bound>1});
    const v=r.visibility,win=v?.windows?.[String(f.airmass)],window=win?.max_hours||0;
    const capacity=Math.min(f.maxVisit,window)*3600;
    const cycleSeconds=4*(frame+c.overhead);
    let cyclesPerVisit=Math.min(cycles,Math.max(0,Math.floor((capacity-900)/cycleSeconds)));
    const visitSeconds=c=>900+c*cycleSeconds+Math.floor(c*4*frame/2700)*360;
    while(cyclesPerVisit>0&&visitSeconds(cyclesPerVisit)>capacity+1e-6)cyclesPerVisit--;
    if(!cyclesPerVisit)return {...base,science,frames:n,frame_seconds:frame,reason:'No full ABBA sequence + acquisition fits the night window'};
    const visits=Math.ceil(cycles/cyclesPerVisit),full=Math.floor(cycles/cyclesPerVisit),remainder=cycles%cyclesPerVisit;
    const program=full*visitSeconds(cyclesPerVisit)+(remainder?visitSeconds(remainder):0),longest=visitSeconds(cyclesPerVisit);
    const eligible=(win?.duration_counts||[]).filter(w=>w[0]*300>=longest-1e-6).reduce((sum,w)=>sum+w[1],0);
    const shorter=remainder?(win?.duration_counts||[]).filter(w=>w[0]*300>=visitSeconds(remainder)-1e-6).reduce((sum,w)=>sum+w[1],0):eligible;
    const fit=eligible>=full&&shorter>=visits;
    return {...base,science,program,telescope:program+visits*f.calibrationMinutes*60,visits,
      frames:n,frame_seconds:frame,longest_visit:longest,window,eligible_nights:eligible,fit,
      reason:fit?null:'Too few sampled nights fit all planned visits'};
  }
  function filterFailures(r,f,t,ignoreAid=false){
    const failures=[],oid=Number(r.moca_oid);
    if(f.excludeOids.includes(oid))return ['Manually excluded OID'];
    if(f.includeOids.includes(oid))return [];
    if(f.rvMode==='none'&&r.has_rv&&!f.bypassNoMeasuredRvOids.includes(oid))failures.push('Measured RV available');
    if(f.rvMode==='measured'&&!r.has_rv)failures.push('No non-ignored measured RV');
    if(f.rvMaxErrorEnabled&&(!finite(r.rv?.radial_velocity_kms_unc)||r.rv.radial_velocity_kms_unc>f.rvMaxError))failures.push('RV uncertainty exceeds cutoff or is unknown');
    const refBypass=f.referenceBypass&&f.rvMode!=='none'&&r.has_rv;
    const standardBypass=f.bypassNoMeasuredRvOids.includes(oid);
    if(!ignoreAid&&!standardBypass&&f.aids&&!f.aids.includes(aid(r)))failures.push('Association disabled: '+aid(r));
    if(f.observables&&!f.observables.includes(r.observables||'unknown'))failures.push('Observable combination disabled');
    if(!refBypass&&!standardBypass){
      const prob=f.probKind==='summed'?r.summed_young_prob:r.individual_prob;
      if(f.membershipEnabled&&(!finite(prob)||prob<f.prob))failures.push(`${f.probKind==='summed'?'Summed young':'Individual association'} probability below ${f.prob}% or unknown`);
      if(f.realAssociation&&String(r.is_real)!=='1')failures.push('Association is not confirmed real');
      if(f.uncontaminated&&(!finite(r.highly_contaminated)||Number(r.highly_contaminated)!==0))failures.push('Association contamination unknown / high');
      if(f.uvwEnabled&&(!finite(r.uvw_sep)||r.uvw_sep>f.uvw))failures.push('Regular UVW separation above cutoff or unknown');
      if(f.uvwLooseEnabled&&(!finite(r.uvw_sep_loose)||r.uvw_sep_loose>f.uvwLoose))failures.push('Loose UVW separation above cutoff or unknown');
      if(f.ageEnabled){
        if(!finite(r.age_myr)){if(f.unknownAge==='exclude')failures.push('Unknown association age');}
        else if(r.age_myr<f.ageMin||r.age_myr>f.ageMax)failures.push('Age outside selected range');
      }
      if(f.associationDistanceEnabled&&(!finite(r.association_mean_distance_pc)||r.association_mean_distance_pc>f.associationDistanceMax))failures.push('Association mean distance above cutoff or unknown');
    }
    if(f.distanceEnabled){if(!finite(r.distance_pc)){if(f.unknownDistance==='exclude')failures.push('Unknown distance');}else if(r.distance_pc>f.distanceMax)failures.push('Distance above cutoff');}
    if(!finite(r.sptn)||r.sptn<f.sptMin||r.sptn>f.sptMax)failures.push('Spectral type outside selected range');
    if(f.teffEnabled&&(!finite(r.teff)||r.teff<f.teffMin||r.teff>f.teffMax))failures.push('Teff outside selected range or unknown');
    if(f.excludePhotometricSpt&&Number(r.photometric_estimate)===1)failures.push('Photometric spectral type');
    if(f.excludePhotometricDistance&&Number(r.distance_photometric_estimate)===1)failures.push('Photometric distance');
    if(f.excludeBadSpiff&&Number(r.photometric_estimate)===1&&['early','unclear','bad','late_m','star','scatter','reddened','galaxy','snr','weird','giant','risky_andromeda'].includes(String(r.spiff_vetting_classification).toLowerCase()))failures.push('Rejected SPIFF photometric classification');
    if(f.rejectDuplicates&&r.likely_duplicate)failures.push('Likely duplicate');
    if(f.ignoreMultiples&&String(r.spt).includes('+'))failures.push('Unresolved multiple (+ type)');
    if(f.excludeSubdwarfs&&Number(r.subdwarf_like)===1)failures.push('Subdwarf flag');
    if(f.requireLowg&&Number(r.lowg_like)!==1)failures.push('Low-gravity flag required');
    if(f.conditionalLowg&&r.sptn<=f.lowgSpt&&finite(r.age_myr)&&r.age_myr<f.lowgAge&&Number(r.lowg_like)!==1)failures.push('Conditional low-gravity requirement');
    if(f.hostMin>0&&finite(r.host_separation)&&r.host_separation/1000<f.hostMin)failures.push('Host separation below cutoff');
    if(f.quality!=='all'&&!f.quality.includes(r.spt_quality||'?'))failures.push('Spectral-type quality excluded');
    if(f.manualTypesOnly&&r.spt_calculation_method!==null&&r.spt_calculation_method!==undefined)failures.push('Automated spectral classification');
    if(f.excludeArchive&&(r.archive_max_R||0)>=f.archiveResolution)failures.push('Existing GNIRS archival coverage');
    if(f.excludePlanned&&r.planned_reduction_highres)failures.push('High-resolution data in planned reductions');
    if(f.restrictDec&&(!finite(r.dec)||r.dec<=-37||r.dec>=90))failures.push('Outside Gemini North published declination range');
    if(f.restrictRa&&!r.ra_accessible)failures.push('Outside published 2027A GNIRS RA range');
    if(f.excludeRestrictedAccess&&r.restricted_access)failures.push('Restricted 2027A RA / declination access');
    if(f.bestAirmassEnabled&&(!finite(r.visibility?.best_airmass)||r.visibility.best_airmass>f.bestAirmass))failures.push('No night-time opportunity below maximum best airmass');
    if(f.minWindow>0&&(r.visibility?.windows?.[String(t?.airmass||2)]?.max_hours||0)<f.minWindow)failures.push('Useful night window too short');
    const metric=f.timeMetric||'science';
    if(f.timeEnabled&&(!finite(t?.[metric])||t[metric]>=f.maxScience*3600))failures.push(`${metric[0].toUpperCase()+metric.slice(1)} time at / above limit or unknown`);
    if(f.excludeFastBand3&&finite(t?.band3Science)&&t.band3Science<f.maxScience*3600)failures.push('Band 3 (0.30″) science integration below limit');
    if(f.requireVisitFit&&!t?.fit)failures.push(t?.reason||'Visit cannot fit semester visibility');
    return failures;
  }
  function totals(rows,timings){
    const out={science:0,program:0,telescope:0,visits:0,unknown:0,n:rows.length};
    for(const r of rows){const t=timings.get(r.moca_oid);for(const k of ['science','program','telescope','visits'])if(finite(t?.[k]))out[k]+=t[k];if(!finite(t?.telescope))out.unknown++;}
    return out;
  }
  function associationOrder(values,selected,counts){const checked=new Set(selected);return [...values].sort((a,b)=>Number(checked.has(b))-Number(checked.has(a))||(counts[b]||0)-(counts[a]||0)||a.localeCompare(b));}
  const api={DEFAULTS,MODES,SXD,defaultAidSelected,defaultObservableSelected,finite,aid,sptLabel,parseOidList,curve,interpolateTime,timing,filterFailures,totals,associationOrder};
  if(typeof module!=='undefined')module.exports=api;else root.GNIRSLogic=api;
})(typeof window!=='undefined'?window:globalThis);
