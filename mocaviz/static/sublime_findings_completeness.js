/* Count-equivalent volumes; explicit band union and no relation extrapolation. */
const FindingCompleteness = (() => {
  const sphere=4*Math.PI/3;
  function interpolate(sequence,x) {
    const points=sequence?.points;
    if(!points?.length || x<sequence.valid_xrange_min || x>sequence.valid_xrange_max || x<points[0][0] || x>points.at(-1)[0])return null;
    let hi=points.findIndex(p=>p[0]>=x);
    if(hi===0)return {m:points[0][1],scatter:points[0][2]??sequence.yscatter};
    const a=points[hi-1],b=points[hi],t=(x-a[0])/(b[0]-a[0]);
    return {m:a[1]+t*(b[1]-a[1]),scatter:a[2]!=null&&b[2]!=null?a[2]+t*(b[2]-a[2]):sequence.yscatter};
  }
  function expectation(bin,reference,options) {
    const sums={j:0,w2:0,union:0,low:0,high:0},valid={j:0,w2:0,union:0};
    let missingScatter=false;
    const n=bin.hi-bin.lo<.001?1:40;
    for(let i=0;i<n;i++) {
      const type=n===1?bin.lo:bin.lo+(i+.5)*(bin.hi-bin.lo)/n;
      const horizons={},low=[],high=[];
      for(const band of ['j','w2']) {
        const relation=interpolate(reference.sequences[band],type);
        if(!relation)continue;
        const d=10**((options[band]-relation.m+5)/5);
        const scatter=relation.scatter??0;
        missingScatter ||= relation.scatter==null;
        horizons[band]=d;sums[band]+=d**3;valid[band]++;
        low.push(d*10**(-scatter/5));high.push(d*10**(scatter/5));
      }
      if(Object.keys(horizons).length) {
        sums.union+=Math.max(...Object.values(horizons))**3;
        sums.low+=Math.max(...low)**3;sums.high+=Math.max(...high)**3;valid.union++;
      }
    }
    const result={missingScatter,partialJ:valid.j<n,partialW2:valid.w2<n};
    for(const band of ['j','w2'])result['d_'+band]=valid[band]===n?(sums[band]/n)**(1/3):null;
    if(valid.union!==n)return {...result,d_union:null,expected:null,expected_low:null,expected_high:null};
    const volume=options.sky*sphere*sums.union/n;
    return {...result,d_union:(sums.union/n)**(1/3),volume,expected:bin.rho*volume,
      expected_low:(bin.rho-bin.rho_minus)*options.sky*sphere*sums.low/n,
      expected_high:(bin.rho+bin.rho_plus)*options.sky*sphere*sums.high/n};
  }
  function evaluate(reference,summary,options) {
    if(![options.j,options.w2,options.sky].every(Number.isFinite)||options.sky<=0||options.sky>1)throw Error('Enter finite J/W2 limits and a sky fraction greater than 0 and at most 1.');
    return reference.bins.map((bin,i)=>{
      const counts=summary.bins[i],prediction=expectation(bin,reference,options);
      const volume=counts.n/bin.rho,secureVolume=counts.secure/bin.rho;
      const vlow=counts.interval[0]/(bin.rho+bin.rho_plus),vhigh=counts.interval[1]/(bin.rho-bin.rho_minus);
      const radius=v=>(v/(sphere*options.sky))**(1/3);
      return {...bin,...counts,...prediction,v_count:volume,r_count:radius(volume),r_low:radius(vlow),r_high:radius(vhigh),
        r_secure:radius(secureVolume),ratio:prediction.expected>0?counts.n/prediction.expected:null,
        ratio_secure:prediction.expected>0?counts.secure/prediction.expected:null,
        ratio_low:prediction.expected_high>0?counts.interval[0]/prediction.expected_high:null,
        ratio_high:prediction.expected_low>0?counts.interval[1]/prediction.expected_low:null,
        comparison:prediction.expected==null?'Outside relation range':
          counts.interval[1]<prediction.expected_low?'Below prediction':
          counts.interval[0]>prediction.expected_high?'Above prediction':'Within uncertainty envelope'};
    });
  }
  return {interpolate,expectation,evaluate};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=FindingCompleteness;
