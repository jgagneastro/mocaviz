const {test}=require('node:test');const assert=require('node:assert/strict');
const C=require('../mocaviz/static/sublime_findings_completeness.js');
const seq=m=>({valid_xrange_min:10,valid_xrange_max:30,points:[[10,m,0],[30,m,0]],yscatter:0});
const bin={lo:10,hi:11,rho:.001,rho_minus:.0001,rho_plus:.0001};
const ref={bins:[bin],sequences:{j:seq(15),w2:seq(15)}};
test('OR uses maximum radius, not sum of volumes; magnitude systems use matched Vega',()=>{
 const p=C.expectation(bin,ref,{j:15,w2:15,sky:1});
 assert.ok(Math.abs(p.d_union-10)<1e-10);assert.ok(Math.abs(p.expected-4*Math.PI/3)<1e-10);
 const deep=C.expectation(bin,ref,{j:20,w2:15,sky:.5});assert.ok(Math.abs(deep.d_union-100)<1e-10);
 assert.ok(Math.abs(deep.expected/p.expected-500)<1e-10);
});
test('zero-count upper limits survive, density conversion and fsky are consistent',()=>{
 const zero={bins:[{n:0,secure:0,interval:[0,1.841],known:0}]};
 const r=C.evaluate(ref,zero,{j:15,w2:15,sky:.5})[0];
 assert.equal(r.r_count,0);assert.ok(r.r_high>0);assert.ok(r.ratio_high>0);
 const sample={bins:[{n:10,secure:5,interval:[7,14]}]};
 const a=C.evaluate(ref,sample,{j:15,w2:15,sky:1})[0],b=C.evaluate(ref,sample,{j:15,w2:15,sky:.5})[0];
 assert.equal(a.v_count,10000);assert.ok(Math.abs(b.r_count/a.r_count-2**(1/3))<1e-10);
 assert.ok(a.ratio>1);assert.equal(b.ratio,2*a.ratio);
});
test('no extrapolation and no silent partial-bin predictions',()=>{
 assert.equal(C.interpolate(seq(15),31),null);
 assert.equal(C.expectation({...bin,lo:30,hi:31},ref,{j:15,w2:15,sky:1}).expected,null);
 const r={...ref,sequences:{j:seq(15),w2:{...seq(16),valid_xrange_max:33,points:[[10,16,0],[33,16,0]]}}};
 const p=C.expectation({...bin,lo:31,hi:32},r,{j:15,w2:16,sky:1});assert.equal(p.d_j,null);assert.ok(Math.abs(p.d_union-10)<1e-10);
});
test('invalid footprint rejected',()=>{for(const sky of [0,-1,2,NaN])assert.throws(()=>C.evaluate(ref,{bins:[]},{j:15,w2:15,sky}));});
