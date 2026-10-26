const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../mocaviz/static/astrometry.js'),'utf8');
function fixture(fetch) {
 const events=[];
 const c=vm.createContext({URL,URLSearchParams,AbortController,TypeError,console,
  setTimeout:(fn,ms)=>setTimeout(fn,ms===1000?0:ms),clearTimeout,fetch,
  document:{currentScript:{src:'http://localhost/static/astrometry.js'},addEventListener(){}},
  window:{location:{search:''}},events});
 vm.runInContext(source,c);
 vm.runInContext(`
  atmState.payload={};atmState.selectedOid=602;
  atmEl['atm-fit-method']={value:'ultranest'};
  atmEl['atm-cancel-fit']={hidden:true};atmEl['atm-retry-fit']={hidden:true};
  prepareAstrometryRows=()=>({rows:[1,2,3]});
  buildAstrometryFitRequest=(mode)=>({mode,fitter:'ultranest',rows:[1,2,3]});
  setAstrometryFitBusy=(busy,message)=>{atmState.fitBusy=busy;if(message)events.push(message);updateAstrometryFitJobControls()};
  updateAstrometryFitSummary=(s)=>events.push(s);
  setAstrometryStatus=(s)=>events.push(s);
  setAstrometryLoading=(v)=>events.push('loading:'+v);
  updateAstrometryFitControlState=()=>{};updateAstrometryManagementVisibility=()=>{};
  renderAstrometry=()=>events.push('rendered');
 `,c);
 return {c,events,run:code=>vm.runInContext(code,c)};
}
const response=(job,status=200)=>({ok:status<400,status,json:async()=>status<400?{ok:true,job}:{error:'Fit job unavailable'}});
const running={id:'test-job',state:'running',phase:'Sampling stationary-source model (2/2)',elapsedSeconds:123,likelihoodCalls:12345,timeoutSeconds:900};
test('UltraNest job reports stage/elapsed/calls and only applies completed result',async()=>{
 let polls=0,starts=0;
 const f=fixture(async(url,options)=>{
  if(options.method==='POST'){starts++;return response(running,202)}
  return response(++polls===1?running:{...running,state:'complete',result:{fit:{pmra:12,fitterLabel:'UltraNest'}}});
 });
 await f.run('runAstrometryFit("pm")');
 assert.equal(starts,1);assert.equal(f.run('atmState.fitResult.pmra'),12);
 assert.ok(f.events.some(s=>/2\/2.*2m 03s.*12,345.*15 min limit/.test(s)));
 assert.equal(f.run('atmState.fitBusy'),false);
});
test('incomplete sampling never applies a partial result',async()=>{
 const f=fixture(async(url,options)=>response(options.method==='POST'?running:{...running,state:'incomplete',error:'Runtime limit; sampling incomplete',result:{fit:{pmra:999}}}));
 await f.run('runAstrometryFit("pm_plx")');
 assert.equal(f.run('atmState.fitResult'),null);assert.equal(f.run('atmState.fitBusy'),false);
 assert.ok(f.events.includes('Runtime limit; sampling incomplete'));
});
test('lost status connection can reconnect to the same job without starting a second fit',async()=>{
 let connected=false,starts=0;
 const f=fixture(async(url,options)=>{
  if(options.method==='POST'){starts++;return response(running,202)}
  if(!connected)throw new TypeError('network down');
  return response({...running,state:'complete',result:{fit:{pmra:12}}});
 });
 await f.run('runAstrometryFit("pm")');
 assert.equal(f.run('atmState.fitTask.disconnected'),true);
 assert.equal(f.run('atmEl["atm-retry-fit"].hidden'),false);
 assert.ok(f.events.includes('loading:false'));
 connected=true;await f.run('executeAstrometryFitTask(atmState.fitTask)');
 assert.equal(starts,1);assert.equal(f.run('atmState.fitResult.pmra'),12);
});
test('cancel waits for sampler acknowledgement and discards any unfinished values',async()=>{
 let cancel=false;
 const f=fixture(async(url,options)=>{
  if(url.includes('/cancel')){cancel=true;return response({...running,state:'cancelling'})}
  if(options.method==='POST')return response(running,202);
  return response(cancel?{...running,state:'cancelled',error:'Fit cancelled'}:running);
 });
 const promise=f.run('runAstrometryFit("pm")');
 for(let i=0;i<30&&!f.run('atmState.fitTask?.id');i++)await new Promise(r=>setTimeout(r,1));
 await f.run('cancelAstrometryFit()');await promise;
 assert.ok(cancel);assert.equal(f.run('atmState.fitResult'),null);
 assert.equal(f.run('atmState.fitBusy'),false);
});
test('changing selected inputs discards a late result and cancels its own job',async()=>{
 let release,cancel=false;
 const f=fixture(async(url,options)=>{
  if(url.includes('/cancel')){cancel=true;return response({...running,state:'cancelling'})}
  if(options.method==='POST')return response(running,202);
  return new Promise(r=>{release=()=>r(response({...running,state:'complete',result:{fit:{pmra:999}}}))});
 });
 const promise=f.run('runAstrometryFit("pm")');
 for(let i=0;i<30&&!release;i++)await new Promise(r=>setTimeout(r,1));
 f.run('abandonAstrometryFitTask();atmState.selectedOid=603');release();await promise;
 assert.ok(cancel);assert.equal(f.run('atmState.fitResult'),null);
});

test('a late job-start response is cancelled after the user changes inputs',async()=>{
 let release,cancel=false;
 const f=fixture(async(url,options)=>{
  if(url.includes('/cancel')){cancel=true;return response({...running,state:'cancelling'})}
  return new Promise(r=>{release=()=>r(response(running,202))});
 });
 const promise=f.run('runAstrometryFit("pm")');
 for(let i=0;i<30&&!release;i++)await new Promise(r=>setTimeout(r,1));
 f.run('abandonAstrometryFitTask()');release();await promise;
 assert.ok(cancel);assert.equal(f.run('atmState.fitResult'),null);
});
