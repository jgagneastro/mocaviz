const assert=require('node:assert/strict');
const {test}=require('node:test');
const {classify,annotate,groups,definitions}=require('../mocaviz/static/sublime_findings.js');
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
});
test('unreviewed and other spectral labels remain Others, even with clear motion',()=>{
  for(const quality of [null,undefined,'','bad','good_reddened','weird','late_M','incomplete_but_promising'])
    assert.equal(classify({spiff_quality:quality,motion:6}),'others');
  assert.equal(classify({spiff_quality:'bad',spiffstacker_quality:' CONTAMINATED_UCD ',sublimeaperture_quality:'bad',motion:5}),'confirmed');
  assert.equal(classify({spiff_quality:'good',motion:''}),'others');
});
test('each filtered object belongs to exactly one class and all plots use the class color',()=>{
  const rows=[{known:true},{spiff_quality:'good',motion:6},{spiffstacker_quality:'good_candidate',motion:3},{sublimeaperture_quality:'peculiar_ucd',motion:2},{motion:6}].map((r,i)=>annotate({...r,moca_oid:i+1}));
  assert.equal(new Set(definitions.map(d=>d.color)).size,5);
  const traces=groups(rows,(data,name,color)=>({name,marker:{color},ids:data.map(r=>r.moca_oid)}));
  assert.deepEqual(traces.flatMap(t=>t.ids).sort(),[1,2,3,4,5]);
  assert.equal(traces.length,5);
  for(const [i,trace] of traces.entries()) {
    assert.equal(trace.name,definitions[i].label);
    assert.equal(trace.marker.color,definitions[i].color);
    assert.equal(trace.meta.plot_class,definitions[i].key);
    assert.equal(rows[i].plot_class_label,trace.name);
  }
});
