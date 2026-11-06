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

test('L1-L5 scaling is the median multiplicative horizon-to-count ratio',()=>{
 const rows=[2,4,8,16,32,64].map((factor,i)=>({lo:10+i,r_count:10,d_union:10*factor}));
 rows.push({lo:16,r_count:1,d_union:99999},{lo:9,r_count:1,d_union:99999});
 assert.deepEqual(C.normalization(rows,true),{factor:16,bins:5,available:true});
 assert.equal(C.normalization(rows,false).factor,1);
 assert.equal(rows[0].r_count,10);
});
test('L1-L5 normalization excludes zero counts and missing predictions',()=>{
 assert.deepEqual(C.normalization([{lo:11,r_count:0,d_union:100},{lo:12,r_count:10,d_union:null}],true),{factor:1,bins:0,available:false});
 assert.equal(C.normalization([{lo:11,r_count:5,d_union:10},{lo:12,r_count:5,d_union:15},{lo:13,r_count:5,d_union:100}],true).factor,3);
});

test('count normalization uses count ratios independently of distance normalization',()=>{
 const rows=[2,4,8,16,32].map((factor,i)=>({lo:11+i,n:10,expected:10*factor,r_count:10,d_union:20}));
 rows.push({lo:10,n:1,expected:1e9},{lo:16,n:1,expected:1e9});
 assert.equal(C.normalization(rows,true,'counts').factor,8);
 assert.equal(C.normalization(rows,true).factor,2);
 assert.equal(C.normalization(rows,false,'counts').factor,1);
 assert.equal(C.normalization([{lo:11,n:0,expected:10}],true,'counts').available,false);
 assert.equal(rows[0].n,10);
});
