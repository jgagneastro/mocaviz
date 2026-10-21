const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({URL, URLSearchParams, console,
  document:{currentScript:{src:'http://localhost/static/astrometry.js'},addEventListener(){}},
  window:{location:{search:''}}});
vm.runInContext(fs.readFileSync(require.resolve('../mocaviz/static/astrometry.js'),'utf8'),context);
const row={point_of_view:'jwst',measurement_epoch_yr:2024.,observer:{body:'jwst',origin:'ssb',frame:'icrf',
  epoch_mjd_utc:51544.5+24*365.25,position_au:[1,0,0],velocity_au_per_day:[0,.017,0]}};
context.row=row;
test('JWST factor uses saved state and Earth path is unchanged',()=>{
  assert.equal(vm.runInContext('astrometryObserverEligible(row)',context),true);
  assert.equal(vm.runInContext('rowParallaxMotion(90,0,2024,row).ra',context),1);
  assert.equal(vm.runInContext('rowParallaxMotion(90,0,2024,{point_of_view:"earth"}).ra === parallaxMotion(90,0,2024).ra',context),true);
});
test('stale/absent states never silently become Earth',()=>{
  assert.equal(vm.runInContext('astrometryObserverEligible({...row,measurement_epoch_yr:2025})',context),false);
  assert.equal(vm.runInContext('astrometryObserverEligible({...row,observer:null})',context),false);
  assert.equal(vm.runInContext('Number.isNaN(rowParallaxMotion(90,0,2024,{...row,observer:null}).ra)',context),true);
});
