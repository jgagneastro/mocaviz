'use strict';
// URL credentials are held only in this closure for the lifetime of the page.
// No cookies, localStorage, sessionStorage, logs or credential-bearing exports.
const GNIRSAccess=(()=>{
  const url=new URL(location.href),params=url.searchParams;
  const one=(keys,fallback='')=>{const values=keys.flatMap(k=>params.getAll(k));
    if(new Set(values).size>1)throw Error('Conflicting URL credentials.');return values[0]||fallback;};
  const headers={'X-MOCA-User':one(['user','username']),
    'X-MOCA-Password':one(['pwd','password']),
    'X-MOCA-Database':one(['dbase','db','database'],'mocadb_private_tables'),
    'Content-Type':'application/json'};
  for(const key of ['user','username','pwd','password','dbase','db','database','host','port'])params.delete(key);
  history.replaceState(null,'',url.pathname+url.search+url.hash);
  const prefix=location.pathname.replace(/\/gnirs-planner\/?$/,'');
  const selections=new Map();
  async function api(path,options={}){
    const requestUrl=new URL(path,location.origin);
    const operation=requestUrl.pathname.replace('/api/','');
    if(!/^[a-z-]+$/.test(operation))throw Error('Unsupported planner operation.');
    const body={...Object.fromEntries(requestUrl.searchParams),...(options.body?JSON.parse(options.body):{})};
    if(body.id){
      if(!selections.has(body.id))throw Error('Selection expired. Change a filter to recalculate.');
      body.filters=selections.get(body.id);
    }
    if(options.method==='POST'&&operation.startsWith('regenerate'))body.action='start';
    const response=await fetch(prefix+'/api/gnirs/'+operation,{
      method:'POST',headers,body:JSON.stringify(body),cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',
    });
    if(response.ok&&operation==='selection'&&!body.id){
      const result=await response.clone().json();selections.set(result.id,body.filters||{});
      while(selections.size>12)selections.delete(selections.keys().next().value);
    }
    return response;
  }
  return Object.freeze({fetch:api});
})();
