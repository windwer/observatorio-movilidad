'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/app.js','utf8');
const refresh=source.slice(source.indexOf('async function refresh(){'),source.indexOf('function renderMain('));
const cache=source.slice(source.indexOf('const responseCache='),source.indexOf('function ensureRouteScheduleUI'));
const tick=()=>new Promise(resolve=>setImmediate(resolve));

function context(){
 const nodes=new Map(),calls=[],renders=[];
 let resolveCoverage,resolveCompare;
 const coverage=new Promise(r=>resolveCoverage=r),compare=new Promise(r=>resolveCompare=r);
 const ctx={console,AbortController,Date,Promise,Map,qs:(endpoint,params)=>endpoint+'?'+new URLSearchParams(params),
   state:{operator:'irunbus',year:2026,month:10,dayType:'LJ',hourFrom:0,hourTo:1440,route:'',calendarFilter:'all',exactDate:''},
   months:Array(12).fill('Mes'),refreshToken:0,refreshController:null,
   $:id=>{if(!nodes.has(id))nodes.set(id,{checked:false});return nodes.get(id)},
   setText:()=>{},operatorName:x=>x,renderDateOptions:()=>{},chooseMapDate:()=> '2026-10-16',
   renderMap:data=>renders.push(data),loadRouteInsights:async()=>{},renderMain:()=>{},renderCoverage:()=>{},renderCompare:()=>{},
   api:async endpoint=>{
     calls.push(endpoint);
     if(endpoint.startsWith('/api/coverage'))return coverage;
     if(endpoint.startsWith('/api/compare'))return compare;
     return {endpoint,segments:[]};
   }};
 vm.createContext(ctx);vm.runInContext(cache+refresh,ctx);
 return {ctx,calls,renders,resolveCoverage,resolveCompare};
}

test('map renders while comparison and annual calendar are still pending',async()=>{
 const c=context();const pending=c.ctx.refresh();await tick();
 assert.equal(c.renders.length,1);
 assert(c.renders[0].endpoint.startsWith('/api/map'));
 c.resolveCoverage({});c.resolveCompare({});await pending;
});

test('changing line reuses annual calendar, comparison and unfiltered month',async()=>{
 const c=context();c.resolveCoverage({});c.resolveCompare({});await c.ctx.refresh();
 c.ctx.state.route='r1';await c.ctx.refresh();
 assert.equal(c.calls.filter(x=>x.startsWith('/api/coverage')).length,1);
 assert.equal(c.calls.filter(x=>x.startsWith('/api/compare')).length,1);
 assert.equal(c.calls.filter(x=>x.startsWith('/api/month')&&x.endsWith('route_id=')).length,1);
});

test('late result from a previous selection cannot paint the current map',async()=>{
 const c=context();let releaseFirst;
 const api=c.ctx.api;
 c.ctx.api=endpoint=>endpoint.startsWith('/api/month')&&endpoint.includes('route_id=old')
   ?new Promise(r=>releaseFirst=r):api(endpoint);
 c.ctx.state.route='old';const first=c.ctx.refresh();await tick();
 c.ctx.state.route='new';const second=c.ctx.refresh();await tick();
 assert.equal(c.renders.length,1);assert(c.renders[0].endpoint.includes('route_id=new'));
 releaseFirst({segments:[]});c.resolveCoverage({});c.resolveCompare({});await Promise.all([first,second]);
 assert.equal(c.renders.length,1);
});

test('zoom simplification preserves endpoints and significant bends',()=>{
 const ctx={window:{}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/offline_map.js','utf8'),ctx);
 const map=Object.create(ctx.window.GeographicReviewMap.prototype);map.projected=new WeakMap();map.project=p=>p;
 const coordinates=[[0,0],[1,.01],[2,0],[3,0],[4,5],[5,0],[6,0]];
 const coarse=map.routePoints(coordinates,.6),fine=map.routePoints(coordinates,.001);
 assert(coarse.startsWith('0.000,0.000'));assert(coarse.endsWith('6.000,0.000'));
 assert(coarse.includes('4.000,5.000'));assert(fine.split(' ').length>coarse.split(' ').length);
 assert.deepEqual(coordinates[0],[0,0]);
});

test('province and focused views request a bounded nonempty tile grid',()=>{
 const ctx={window:{}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/offline_map.js','utf8'),ctx);
 const map=Object.create(ctx.window.GeographicReviewMap.prototype);
 map.z0=12;map.origin={x:519000,y:383000};map.base={w:2700,h:2050};
 for(const width of [2700,82,42,10800]){
   map.view={x:0,y:0,w:width,h:width*map.base.h/map.base.w};
   const grid=map.tileGrid(),count=(grid.x2-grid.x1+1)*(grid.y2-grid.y1+1);
   assert(count>0&&count<=110,`${width}: ${count} tiles`);
 }
});

test('a late catalogue cannot replace line activity for the current day type',async()=>{
 const start=source.indexOf('async function updateRoutes('),end=source.indexOf('function escapeHTML(');
 let releaseOld;let calls=0;
 const select={innerHTML:'',value:''},catalog={routes:[{route_id:'r1',name:'R1'},{route_id:'r2',name:'R2'}]};
 const ctx={state:{operator:'irunbus',year:2026,month:10,route:''},refreshToken:1,
   routeCatalogCache:new Map(),$:()=>select,selectMainSegment:res=>res,
   qs:x=>x,escapeHTML:x=>x,api:()=>++calls===1?new Promise(r=>releaseOld=r):Promise.resolve(catalog)};
 vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
 const previous=ctx.updateRoutes({lines:[{route_id:'r1',name:'R1'}]});
 ctx.refreshToken=2;
 await ctx.updateRoutes({lines:[{route_id:'r2',name:'R2'}]});
 const currentMarkup=select.innerHTML;
 releaseOld(catalog);await previous;
 assert.equal(select.innerHTML,currentMarkup);
 assert(currentMarkup.includes('value="r2">R2</option>'));
});
