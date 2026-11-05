const assert=require('node:assert/strict');
const {test}=require('node:test');
const {classify,annotate,groups,definitions,isConfirmed,markerSymbol}=require('../mocaviz/static/sublime_findings.js');
const accepted=['good','good_candidate','contaminated_ucd','peculiar_ucd','good_plus_star'];
test('every accepted review in any reduction qualifies at the requested motion boundaries',()=>{
  const boundaries=[[-1,'others'],[0,'others'],[0.5,'others'],[1,'still'],[1.5,'still'],[2,'still'],[2.5,'others'],[3,'candidate'],[4,'candidate'],[4.99,'candidate'],[5,'confirmed'],[6,'confirmed'],[null,'others'],[undefined,'others'],[NaN,'others'],[Infinity,'others']];
  for(const lane of ['spiff','spiffstacker','sublimeaperture'])
    for(const quality of accepted)
      for(const [motion,expected] of boundaries)
        assert.equal(classify({[lane+'_quality']:quality,motion}),expected,`${lane} ${quality} ${motion}`);
});
test('known recovered takes precedence even without an acceptable spectrum or score',()=>{
  for(const motion of [null,-1,1,3,5,6]) assert.equal(classify({known:true,spiff_quality:'good',motion}),'known');
  assert.equal(classify({known:true}),'known');
  assert.equal(classify({known:true,byw_claim:true}),'known');
});
test('any claim indicator takes precedence over the motion classes',()=>{
  for(const indicator of ['byw','byw_claim','yadu','azul','smdet']) {
    for(const motion of [1,3,6]) assert.equal(classify({[indicator]:true,spiff_quality:'good',motion}),'claimed');
    assert.equal(classify({[indicator]:true}),'claimed');
  }
});
test('unreviewed and other spectral labels remain Others, even with clear motion',()=>{
  for(const quality of [null,undefined,'','bad','good_reddened','weird','late_M','incomplete_but_promising'])
    assert.equal(classify({spiff_quality:quality,motion:6}),'others');
  assert.equal(classify({spiff_quality:'bad',spiffstacker_quality:' CONTAMINATED_UCD ',sublimeaperture_quality:'bad',motion:5}),'confirmed');
  assert.equal(classify({spiff_quality:'good',motion:''}),'others');
});
test('each filtered object belongs to exactly one class and all plots use the class color',()=>{
  const rows=[{known:true},{smdet:true},{spiff_quality:'good',motion:6},{spiffstacker_quality:'good_candidate',motion:3},{sublimeaperture_quality:'peculiar_ucd',motion:2},{motion:6}].map((r,i)=>annotate({...r,moca_oid:i+1}));
  assert.equal(new Set(definitions.map(d=>d.color)).size,6);
  const traces=groups(rows,(data,name,color)=>({name,marker:{color},ids:data.map(r=>r.moca_oid)}));
  assert.deepEqual(traces.flatMap(t=>t.ids).sort(),[1,2,3,4,5,6]);
  assert.equal(traces.length,6);
  for(const [i,trace] of traces.entries()) {
    assert.equal(trace.name,definitions[i].label);
    assert.equal(trace.marker.color,definitions[i].color);
    assert.equal(trace.meta.plot_class,definitions[i].key);
    assert.equal(rows[i].plot_class_label,trace.name);
  }
});

test('strict and inclusive confirmation remain independent of claim and publication colors',()=>{
  for(const membership of [{},{known:true},{byw_claim:true},{known:true,smdet:true}]){
    for(const lane of ['spiff','spiffstacker','sublimeaperture']){
      for(const quality of accepted){
        const row={...membership,[lane+'_quality']:quality,motion:5};
        assert.equal(isConfirmed(row,'good'),quality!=='good_candidate');
        assert.equal(isConfirmed(row,'good_candidate'),true);
        const before=classify(row);
        markerSymbol(row,'circle','good');markerSymbol(row,'circle','good_candidate');
        assert.equal(classify(row),before);
      }
    }
  }
  for(const motion of [null,undefined,'',NaN,Infinity,0,4,4.99]){
    assert.equal(isConfirmed({motion,spiff_quality:'good'},'good_candidate'),false);
  }
  assert.equal(isConfirmed({motion:6,spiff_quality:'bad'},'good_candidate'),false);
  assert.equal(isConfirmed({motion:5,spiff_quality:' GOOD_CANDIDATE ',spiffstacker_quality:'good'},'good'),true);
});
test('confirmed symbols preserve synthetic and distance conventions under both standards',()=>{
  const row={motion:6,spiff_quality:'good_candidate'};
  for(const [base,star] of [['circle','star'],['diamond','star-diamond'],['triangle-up','star-triangle-up'],
                           ['diamond-open','star-diamond-open'],['triangle-up-open','star-triangle-up-open']]){
    assert.equal(markerSymbol(row,base,'good'),base);
    assert.equal(markerSymbol(row,base,'good_candidate'),star);
    assert.equal(markerSymbol({...row,spiff_quality:'good'},base,'good'),star);
  }
});
