'use strict';
const $=x=>document.getElementById(x);
const months=['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
const state={operator:'ekialdebus',year:2026,month:10,dayType:'LJ',hourFrom:0,hourTo:1440,calendarFilter:'all',route:'',exactDate:'',activeMapDate:null};
const palette=['#237f75','#427d9f','#d17f4d','#8d79bd','#59a074','#ba7194','#c29a53','#6994bc'];
const OPERATOR_NAMES={ekialdebus:'Ekialdebus',irunbus:'Irunbus',euskotren:'Euskotren (tren · E1/E2)',errenteria_urbanoa:'Errenteria bus urbano'};
const operatorName=code=>OPERATOR_NAMES[code]||code||'Operador';
let map=null,layers=[],fallback=$('fallback-map');
let populationReference={loaded:false,total_population:null,sections:null};
const routeCatalogCache=new Map();
// A refresh can finish after the automatic isochrone preview has started.
// Keep a generation token so an old preview cannot paint curves over the
// newly selected map (the source of the intermittent/asynchronous-looking
// 5/10 minute curves).
let mapRenderToken=0;
let lastMapData=null;
let lastMapScope=null;
let isoRequestId=0;
let refreshController=null;
const responseCache=new Map();
async function cachedApi(endpoint,options={}){
 const hit=responseCache.get(endpoint);
 if(hit&&Date.now()-hit.at<300000){responseCache.delete(endpoint);responseCache.set(endpoint,hit);return hit.value;}
 const value=await api(endpoint,options);
 responseCache.set(endpoint,{at:Date.now(),value});
 while(responseCache.size>96)responseCache.delete(responseCache.keys().next().value);
 return value;
}
function ensureRouteScheduleUI(){
 const panel=$('route-insights');if(!panel||$('route-service-window'))return;
 const metrics=panel.querySelector('.route-metrics');
 if(metrics)metrics.insertAdjacentHTML('beforeend',`<div class="route-metric"><div class="label">Horario de servicio</div><strong id="route-service-window">—</strong><small id="route-service-window-detail">Primera–última expedición</small></div><div class="route-metric"><div class="label">Expediciones de la fecha</div><strong id="route-trips">—</strong><small id="route-trips-detail">Salidas con hora válida en la primera parada</small></div>`);
 const frequency=panel.querySelector('.frequency-wrap');
 if(frequency)frequency.insertAdjacentHTML('beforebegin',`<div class="route-schedule-compare"><div class="section-title" style="margin-bottom:8px">Lectura de evolución de la línea</div><div class="route-compare-controls"><label>Fecha base <input id="route-compare-old" type="date" value="2026-10-16"></label><label>Fecha nueva <input id="route-compare-new" type="date" value="2026-10-17"></label><button class="small-action" id="route-compare-run" type="button">Comparar horario y frecuencia</button></div><div class="route-compare-output" id="route-compare-output">Selecciona una línea para comparar su ventana de servicio y sus expediciones.</div></div>`);
 const style=document.createElement('style');style.textContent='.route-schedule-compare{padding:0 19px 16px;border-top:1px solid #eef1f0}.route-compare-controls{display:flex;align-items:end;gap:10px;flex-wrap:wrap}.route-compare-controls label{display:flex;flex-direction:column;gap:5px;font-size:10px;color:#728489;font-weight:700}.route-compare-controls input{border:1px solid #dfe5e3;border-radius:7px;padding:7px 8px;color:#233b45;background:#fafbf9;font:inherit}.route-compare-output{margin-top:10px;padding:10px 12px;border-radius:9px;background:#f2f7f5;color:#536d72;font-size:11px;line-height:1.45}.route-compare-output strong{display:block;color:#176958;font-size:12px;margin-bottom:3px}.frequency-cell small{font-size:9px;color:#849397;text-align:center;line-height:1.35}';document.head.appendChild(style);
 $('route-compare-run')?.addEventListener('click',()=>loadRouteComparison(refreshToken));
}
async function init(){
 await loadOperatorCatalog();
 ensureRouteScheduleUI();
 $('month').innerHTML=months.map((m,i)=>`<option value="${i+1}">${m}</option>`).join('');$('month').value='10';
 for(let n=0;n<=24;n++){
   $('hour-from').add(new Option(`${String(n).padStart(2,'0')}:00`,n*60));
   $('hour-to').add(new Option(`${String(n).padStart(2,'0')}:00`,n*60));
 }
 $('hour-from').value='0';$('hour-to').value='1440';
 ['operator','year','month','hour-from','hour-to','route','exact-date'].forEach(id=>$(id).addEventListener('change',()=>{
   state.operator=$('operator').value;state.year=Number($('year').value);state.month=Number($('month').value);state.hourFrom=Number($('hour-from').value);state.hourTo=Number($('hour-to').value);
   state.route=$('route').value;state.exactDate=$('exact-date').value;
   if(id==='operator'||id==='year'||id==='month'){state.route='';state.exactDate='';$('route').innerHTML='<option value="">Todas las líneas</option>'}
   refresh()
 }));
 [...$('day-radio').querySelectorAll('button')].forEach(b=>b.addEventListener('click',()=>{
   state.dayType=b.dataset.v;state.exactDate='';[...$('day-radio').querySelectorAll('button')].forEach(x=>x.classList.toggle('active',x===b));refresh()
 }));
 $('import-button').addEventListener('click',openModal);
 $('import-form').addEventListener('submit',importFeed);$('import-date').value=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);
 // Geographic basemap comes from geoEuskadi / Esri; transport geometry comes from the selected GTFS snapshot.
 window.reviewMap=new GeographicReviewMap(document.getElementById('map'), {viewStop,showIsochrone,onRoute:(code,op)=>{
   if(op && $('operator').value!==op){$('operator').value=op;state.operator=op;$('map-both').checked=false;}
   $('map-both').checked=false;$('route').value=code;state.route=code;refresh();
 }});
 fallback.style.display='none';
 $('map-both').addEventListener('change',refresh);
 const mapToggle=$('map-both')?.parentElement;
 if(mapToggle?.lastChild?.nodeType===Node.TEXT_NODE)mapToggle.lastChild.textContent=' Mostrar todos los operadores en el mapa';
 setQualityPanelVisible(false);
 refresh();updateVersions();
}
function openModal(){ $('import-modal').classList.add('open');$('import-operator').value=state.operator;updateVersions(); }
function closeModal(){ $('import-modal').classList.remove('open') }
window.openModal=openModal;window.closeModal=closeModal;
async function api(endpoint,options={}){const response=await fetch(endpoint,options);let out=await response.json();if(!response.ok){const detail=typeof out.detail==='string'?out.detail:(out.detail?JSON.stringify(out.detail):`HTTP ${response.status}`);throw Error(detail)}if(options.method&&options.method!=='GET'&&!endpoint.startsWith('/api/analysis/')){responseCache.clear();routeCatalogCache.clear();}return out}
function qs(endpoint,params){return endpoint+'?'+new URLSearchParams(params)}
function fmt(num,decimal=0){return typeof num==='number'?new Intl.NumberFormat('es-ES',{maximumFractionDigits:decimal}).format(num):'—'}
function setText(id,text){$(id).textContent=text}
function segmentState(seg){return seg?.state==='historical'?'Histórico programado':seg?.state==='planning'?'Planificación':'Sin datos'}
async function loadOperatorCatalog(){
 try{
   const catalog=await api('/api/data/requirements');
   const codes=Array.isArray(catalog.operators)?catalog.operators:[];
   const labels=catalog.operator_labels||{};
   Object.assign(OPERATOR_NAMES,labels);
   if(!codes.length)return;
   const selected=$('operator')?.value;
   const makeOptions=(includeBoth=false)=>{
     const first=includeBoth?'<option value="all">Todos los operadores sin duplicar población</option>':'';
     return first+codes.map(code=>`<option value="${escapeHTML(code)}">${escapeHTML(labels[code]||operatorName(code))}</option>`).join('');
   };
   for(const id of ['operator','import-operator']){
     const select=$(id);if(!select)continue;
     const value=select.value||selected||state.operator;
     select.innerHTML=makeOptions(false);
     select.value=codes.includes(value)?value:(codes.includes(state.operator)?state.operator:codes[0]);
   }
   const frequency=$('frequency-operator');
   if(frequency){const value=frequency.value||'all';frequency.innerHTML=makeOptions(true);frequency.value=(value==='all'||codes.includes(value))?value:'all';}
   state.operator=$('operator')?.value||state.operator;
    const years=Array.isArray(catalog.available_years)?catalog.available_years:[];
    if(years.length&&$('year')){
      const selected=Number($('year').value)||state.year;
      $('year').innerHTML=[...years].sort((a,b)=>b-a).map(year=>`<option value="${year}">${year}</option>`).join('');
      state.year=years.includes(selected)?selected:years[years.length-1];$('year').value=String(state.year);
    }
 }catch(_){
   // Static options remain a safe fallback for an older local server.
 }
}
function renderDateOptions(){
 let days=calendarDays(state.year,state.month,state.dayType);
 $('exact-date').innerHTML='<option value="">Automático · primera fecha con servicio</option>'+days.map(x=>`<option value="${x}">${x.split('-').reverse().join('/')}</option>`).join('');
 if(!days.includes(state.exactDate))state.exactDate='';
 $('exact-date').value=state.exactDate;
}
function selectMainSegment(result){return result?.segments?.find(s=>s.state==='historical'&&s.days_available)||result?.segments?.find(s=>s.days_available)||null}
function calendarDays(year,month,dayType){let d=[];const n=new Date(year,month,0).getDate();for(let i=1;i<=n;i++){const j=new Date(year,month-1,i).getDay();if((dayType==='LJ'&&j>=1&&j<=4)||(dayType==='V'&&j===5)||(dayType==='S'&&j===6)||(dayType==='D'&&j===0))d.push(`${year}-${String(month).padStart(2,'0')}-${String(i).padStart(2,'0')}`)}return d}
function chooseMapDate(result){let s=selectMainSegment(result);if(s){let item=s.daily.find(d=>d.trips!==null && d.trips>0)||s.daily.find(d=>d.trips!==null);if(item)return item.date}return calendarDays(state.year,state.month,state.dayType)[0]||`${state.year}-10-01`}
let refreshToken=0;
async function refresh(){const token=++refreshToken;
 refreshController?.abort();refreshController=new AbortController();const signal=refreshController.signal;
 setText('page-title',`${months[state.month-1]} de ${state.year}`);
 setText('page-sub',`${operatorName(state.operator)} · ${ {LJ:'lunes a jueves',V:'viernes',S:'sábados',D:'domingos'}[state.dayType]} · Horarios programados`);
 setText('year-label',state.year);renderDateOptions();
 try {
   const base={operator:state.operator,year:state.year,month:state.month,day_type:state.dayType,hour_start:state.hourFrom,hour_end:state.hourTo===1440?2880:state.hourTo,calendar_filter:state.calendarFilter};
   const route=state.route,exactDate=state.exactDate,allOperators=$('map-both').checked;
   const monthPromise=cachedApi(qs('/api/month',{...base,route_id:route}),{signal});
   const activityPromise=route?cachedApi(qs('/api/month',{...base,route_id:''}),{signal}):monthPromise;
   // Auxiliary panels render independently. A slow comparison must not gate the map.
   const coverageTask=cachedApi(qs('/api/coverage',{operator:base.operator,year:base.year}),{signal})
     .then(cov=>{if(token===refreshToken)renderCoverage(cov)});
   const comparisonTask=Promise.all([monthPromise,cachedApi(qs('/api/compare',{operator:base.operator,month:base.month,day_type:base.day_type,hour_start:base.hour_start,hour_end:base.hour_end,old_year:base.year-1,new_year:base.year}),{signal})])
     .then(([res,comparison])=>{if(token===refreshToken)renderCompare(res,comparison)});
   const mainTask=Promise.all([monthPromise,activityPromise]).then(([res,activity])=>{
     if(token===refreshToken)renderMain(res,null,null,activity);
   });
   const mapTask=(async()=>{
     const day=exactDate||chooseMapDate(await monthPromise);
     if(token!==refreshToken)return;
     state.activeMapDate=day;
     const geographic=await cachedApi(allOperators?qs('/api/map/both',{day,scope:'all'}):qs('/api/map',{operator:base.operator,day,route_id:route}),{signal});
     if(token!==refreshToken)return;
     renderMap(geographic);
     await loadRouteInsights(token,signal);
   })();
   const results=await Promise.allSettled([mapTask,mainTask,coverageTask,comparisonTask]);
   if(token!==refreshToken)return;
   for(const result of results)if(result.status==='rejected'&&result.reason.name!=='AbortError')console.error(result.reason);
   if(results[0].status==='rejected')throw results[0].reason;
  } catch(e){if(e.name!=='AbortError'){setText('page-sub',`Error de datos: ${e.message}`);console.error(e)}}
}
function renderMain(res,cov,other,routeActivity=res){let primary=selectMainSegment(res);const hasData=primary!==null;
 setText('kpi-trips',hasData?fmt(primary.average_trips_per_day,1):'—');
 setText('kpi-lines',hasData?fmt(primary.lines.length):'—');
 setText('kpi-days',hasData?`${primary.days_available}/${primary.days_total}`:'—');
 setText('kpi-trips-note',hasData?`${segmentState(primary)} · media por jornada`:'Sin información cargada');
 setText('kpi-days-note',hasData?`${primary.days_missing} sin fuente · ${primary.days_retrospective} retrospectivos · ${primary.days_explicit_exception||0} con excepción`:'Sin cobertura certificada');
 const periodSegments=res.segments.map(s=>`${segmentState(s)}: ${s.from} a ${s.to} (${s.days_available}/${s.days_total} jornadas con fuente)`).join(' · ');
 const selectedOperatorName=operatorName(state.operator);
 const routeLabel=state.route||'todas las líneas';
 $('quality-content').innerHTML=`<div class="notice ${hasData&&primary.days_missing?'warn':''}">${hasData?`Selección: <b>${escapeHTML(selectedOperatorName)}</b> · ${escapeHTML(routeLabel)} · ${escapeHTML({LJ:'lunes–jueves',V:'viernes',S:'sábado',D:'domingo'}[state.dayType])}. La fuente contiene horarios programados; no acredita servicio prestado.`:'No hay datos importados para esta selección. El sistema no convierte la ausencia de fuente en cero expediciones.'}</div>
 <div class="metric-row"><div><div class="label">Fuente actual</div><div class="detail">Estado temporal de la selección</div></div><strong>${hasData?segmentState(primary):'Sin datos'}</strong></div>
 <p class="hint">${escapeHTML(periodSegments||'Sin fuentes importadas')}</p>`;
 renderLines(primary);
 if(cov)renderCoverage(cov);
 if(other)renderCompare(res,other);
 updateRoutes(routeActivity);
}
function renderCoverage(coverage){
 if(!coverage?.months?.length){$('month-bars').innerHTML='<div class="empty-table" style="grid-column:1/-1">Sin cobertura de calendario para este operador.</div>';setText('coverage-note','No hay jornadas con fuente para la selección actual.');return}
 const totalDays=coverage.months.reduce((sum,r)=>sum+(r.with_source||0),0),availableMonths=coverage.months.filter(r=>r.with_source>0).length;
 $('month-bars').innerHTML=coverage.months.map((r,i)=>{
   const klass=r.with_source===0?'':r.state==='mixed'?'partial':r.state==='planning'?'plan':'ok';
   const stateLabel=r.with_source===0?'sin fuente':r.with_source===r.days?'completa':`${r.with_source}/${r.days} días`;
   return `<div class="coverage-chip ${klass}" title="${r.with_source}/${r.days} días con fuente; ${r.retrospective} retrospectivos"><strong>${months[i].slice(0,3)}</strong><span>${stateLabel}</span><small>${r.retrospective?`${r.retrospective} retrospectivos`:(r.state==='planning'?'planificación':'fuente GTFS')}</small></div>`;
 }).join('');
 setText('coverage-note',`${availableMonths}/12 meses con alguna fuente · ${totalDays} jornadas cubiertas. Disponibilidad GTFS no equivale a horario validado ni servicio prestado.`);
}
function renderLines(segment){const rows=segment?.lines||[];
 if(!rows.length){$('lines-body').innerHTML='<tr><td colspan="4" class="empty-table">No hay expediciones en las fechas y horas seleccionadas. Comprueba la cobertura de datos.</td></tr>';return}
 $('lines-body').innerHTML=rows.map(r=>`<tr><td class="route">${escapeHTML(r.name)}</td><td>${escapeHTML(r.long_name||'—')}</td><td>${fmt(r.trips_per_day,1)}</td><td>${r.median_interval===null?'—':`${fmt(r.median_interval,1)} min`}</td></tr>`).join('')}
function renderRouteMetrics(data){
 if(!state.route){setText('route-insights-title','Detalle de línea');setText('route-insights-state','Selecciona una línea');setText('route-length','—');setText('route-speed','—');setText('route-runtime','—');setText('route-runtime-detail','Mediana de expediciones del día');setText('route-service-window','—');setText('route-service-window-detail','Primera–última expedición');setText('route-trips','—');setText('route-trips-detail','Salidas con hora válida en la primera parada');return}
 setText('route-insights-title',data?.line_name?`${data.line_name} · detalle de línea`:`${state.route} · detalle de línea`);
 setText('route-insights-state',data?.status==='calculated'?'Estimación metodológica':'Sin datos suficientes');
 setText('route-length',data?.distance_km==null?'—':`${fmt(data.distance_km,2)} km`);
 setText('route-speed',data?.commercial_speed_kmh==null?'—':`${fmt(data.commercial_speed_kmh,1)} km/h`);
 setText('route-runtime',data?.runtime_min==null?'—':`${fmt(data.runtime_min,1)} min`);
 setText('route-runtime-detail',data?.first_departure&&data?.last_arrival?`Mediana; ventana ${data.first_departure}–${data.last_arrival}`:'Sin ventana horaria completa');
 setText('route-service-window',data?.first_departure&&data?.last_departure?`${data.first_departure}–${data.last_departure}`:'—');
 setText('route-service-window-detail',data?.service_span_label?`${data.service_span_label} de servicio programado`:'Sin ventana de servicio completa');
 setText('route-trips',data?.scheduled_trips==null?'—':fmt(data.scheduled_trips));
 setText('route-trips-detail',data?.day?`Expediciones con salida válida · ${data.day}`:'Salidas con hora válida en la primera parada');
}
function renderFrequency(data){
 const el=$('frequency-bars');
 if(!state.route||!data?.points?.length){el.innerHTML='<div class="empty-table" style="grid-column:1/-1">Selecciona una línea para consultar sus expediciones.</div>';setText('frequency-note','Se agrupan route_id con el mismo nombre público de línea, incluidos cambios de ID en fin de semana. La ventana muestra primera–última salida.');return}
 const vals=data.points.map(x=>x.trips_per_day||0),max=Math.max(...vals,1);
 el.innerHTML=data.points.map(x=>`<div class="frequency-cell"><strong>${x.trips_per_day==null?'—':fmt(x.trips_per_day,1)} exp./día</strong><div class="frequency-bar" style="height:${x.trips_per_day==null?3:Math.max(5,Math.round(x.trips_per_day/max*100))}%"></div><span>${escapeHTML(x.label)}</span><small>${x.first_departure&&x.last_departure?`${escapeHTML(x.first_departure)}–${escapeHTML(x.last_departure)}`:'Horario —'}${x.service_span_label?` · ${escapeHTML(x.service_span_label)}`:''}</small></div>`).join('');
 setText('frequency-note',`${data.method}. Agrupación de línea: ${data.grouped_route_ids?.join(', ')||state.route}.`);
}
function signedDelta(value,decimal=0){if(typeof value!=='number'||Number.isNaN(value))return '—';return `${value>0?'+':''}${fmt(value,decimal)}`}
function renderRouteComparison(data){
 const output=$('route-compare-output');if(!output)return;
 if(!state.route){output.textContent='Selecciona una línea para comparar su ventana de servicio y sus expediciones.';return}
 if(!data||data.status!=='calculated'){output.textContent=data?.reason||'No hay expediciones con hora válida en ambas fechas.';return}
 const cmp=data.comparison,old=data.old,newer=data.new;
 output.innerHTML=`<strong>${escapeHTML(cmp.label)}</strong><span>${escapeHTML(data.old_day)}: ${escapeHTML(old.first_departure||'—')}–${escapeHTML(old.last_departure||'—')} · ${fmt(old.scheduled_trips||0)} expediciones</span><br><span>${escapeHTML(data.new_day)}: ${escapeHTML(newer.first_departure||'—')}–${escapeHTML(newer.last_departure||'—')} · ${fmt(newer.scheduled_trips||0)} expediciones</span><br><span>Variación: ${signedDelta(cmp.scheduled_trips_delta)} expediciones · ${signedDelta(cmp.service_span_delta_min,1)} min de ventana.</span>`;
}
async function loadRouteComparison(token=refreshToken){
 if(!state.route){renderRouteComparison(null);return}
 const oldDay=$('route-compare-old')?.value,newDay=$('route-compare-new')?.value;
 if(!oldDay||!newDay){renderRouteComparison({status:'incomplete',reason:'Indica las dos fechas que quieres comparar.'});return}
 try{const data=await api(qs('/api/route/compare',{operator:state.operator,route_id:state.route,old_day:oldDay,new_day:newDay}));if(token===refreshToken)renderRouteComparison(data)}catch(e){if(token===refreshToken)renderRouteComparison({status:'incomplete',reason:'No se pudo comparar: '+e.message})}
}
async function loadRouteInsights(token,signal){
 if(!state.route){renderRouteMetrics(null);renderFrequency(null);renderRouteComparison(null);return}
 try{
  const params={operator:state.operator,route_id:state.route,day:state.activeMapDate,year:state.year,month:state.month};
  const [metrics,frequency]=await Promise.all([cachedApi(qs('/api/route/metrics',params),{signal}),cachedApi(qs('/api/route/frequency',params),{signal})]);
  if(token!==refreshToken)return;
  renderRouteMetrics(metrics);renderFrequency(frequency);await loadRouteComparison(token);
 }catch(e){if(token===refreshToken){renderRouteMetrics({status:'error'});renderFrequency(null);setText('route-insights-state','No disponible: '+e.message)}}
}
function renderCompare(r1,analysis){
 const old=analysis[String(analysis.old_year||2025)],newer=analysis[String(analysis.new_year||2026)];
 const oldLabel=$('compare-2025')?.closest('.kpi')?.querySelector('.name');if(oldLabel)oldLabel.textContent=`${analysis.old_year||2025} · expediciones/día`;
 const newLabel=$('compare-2026')?.closest('.kpi')?.querySelector('.name');if(newLabel)newLabel.textContent=`${analysis.new_year||2026} · expediciones/día`;
 setText('compare-2025',old&&analysis.comparable?fmt(old.average_trips_per_day,1):'—');
 setText('compare-2026',newer&&analysis.comparable?fmt(newer.average_trips_per_day,1):'—');
 if(!analysis.comparable){$('compare-note').textContent=analysis.reason+' · No se muestran diferencias numéricas para periodos incompletos.';return}
 let delta=analysis.delta_pct===null?'No calculable':`${analysis.delta_pct>=0?'+':''}${fmt(analysis.delta_pct,1)}%`;
 $('compare-note').textContent=`${analysis.period_window} · expediciones medias por jornada y categoría. Variación ${delta}. Datos GTFS programados, SIN certificación histórica. ${old.retrospective_days+newer.retrospective_days} jornadas con fuente retrospectiva.
`;
}

async function updateRoutes(res,selectionToken=refreshToken){
 const op=state.operator,year=state.year,month=state.month;
 const active=selectMainSegment(res)?.lines||[];
 const activeIds=new Set(active.map(x=>x.route_id));
 let choices=active.map(x=>({route_id:x.route_id,name:x.name}));
 try{
   const cacheKey=`${op}:${year}:${month}`;
   let catalog=routeCatalogCache.get(cacheKey);
   if(!catalog){
     catalog=await api(qs('/api/routes',{operator:op,year,month}));
     routeCatalogCache.set(cacheKey,catalog);
   }
   if(selectionToken!==refreshToken||op!==state.operator||year!==state.year||month!==state.month)return;
   if(catalog.routes?.length)choices=catalog.routes;
 }catch(e){
   // Older/demo servers may not expose /api/routes yet; retain the previous
   // catalog endpoint as a compatibility fallback, but never drop the active
   // selection from the list.
   try{
     const catalog=await api(qs('/api/demo/catalog',{operator:op,year,month}));
     if(catalog.routes?.length)choices=catalog.routes;
   }catch(ignore){ /* active lines remain a safe last resort */ }
 }
 if(selectionToken!==refreshToken||op!==state.operator||year!==state.year||month!==state.month)return;
 const select=$('route'),old=state.route;
 if(old&&!choices.some(x=>x.route_id===old))choices=[{route_id:old,name:old},...choices];
 select.innerHTML='<option value="">Todas las líneas con servicio este día</option>'+choices.map(x=>
  `<option value="${escapeHTML(x.route_id)}">${escapeHTML(x.name)}${activeIds.has(x.route_id)?'':' · Sin servicio para este tipo de día'}</option>`).join('');
 select.value=old;
}

function escapeHTML(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function clearMap(){if(map){layers.forEach(l=>map.removeLayer(l));layers=[];if(geoLayer){map.removeLayer(geoLayer);geoLayer=null}}fallback.innerHTML=''}
function renderMap(data){
 const scope=JSON.stringify([state.operator,state.route,$('map-both').checked]);
 if(data===lastMapData&&scope===lastMapScope)return;
 lastMapData=data;lastMapScope=scope;
 networkRequestId++;
 const renderToken=++mapRenderToken;
 // Invalidate an in-flight stop request from the previous map snapshot.
 isoRequestId++;
 setText('map-state',(data.state==='historical'?'Histórico programado':data.state==='planning'?'Planificación':'Sin fuente')+(data.missing_operators?.length?' · Falta: '+data.missing_operators.join(', '):''));
 const codes=new Set((data.routes||[]).map(r=>r.name));
 setText('map-count',`${codes.size} líneas · ${data.routes?.length||0} trazados · ${data.stops?.length||0} paradas`);
 setText('map-reference',`Base cartográfica real · recorridos y paradas GTFS · ${data.day}`);
 $('map-empty').style.display=data.stops?.length?'none':'block';
 window.reviewMap.render(data, !!state.route);
 // The first stop previews both accessibility bands; clicking another stop updates them.
 // Euskotren's feed contains the whole E1/E2 corridor, including Bilbao and
 // Donostia. Probe a few stops and preview the first one with a non-zero
 // target population; otherwise the first feed row can be Hendaia/Donostia
 // and make a working census join look like a missing result.
 const bounds=window.reviewMap?.bounds;
 const inMap=s=>Number.isFinite(s.lat)&&Number.isFinite(s.lon)&&(!bounds||
   (s.lon>=bounds.west&&s.lon<=bounds.east&&s.lat>=bounds.south&&s.lat<=bounds.north));
 const candidates=[...(data.stops||[]).filter(s=>s.id==='IR'||s.id==='ER'),...(data.stops||[]).filter(inMap),...(data.stops||[])].filter((s,i,a)=>inMap(s)&&a.findIndex(x=>x.id===s.id)===i);
 if(candidates.length) previewIsochrone(candidates,renderToken).finally(()=>{
   if(renderToken===mapRenderToken)computeNetworkPopulation({silent:true});
 });
 else if(renderToken===mapRenderToken)computeNetworkPopulation({silent:true});
}

async function previewIsochrone(candidates,renderToken){
 if(!candidates.length)return;
 let first=candidates[0];
 for(const candidate of candidates.slice(0,8)){
   if(renderToken!==mapRenderToken)return;
   try{
     const probe=await stopApi(qs('/api/geo/stop',{operator:candidate.operator||state.operator,day:state.activeMapDate,stop_id:candidate.id,minutes:10}));
     if(renderToken!==mapRenderToken)return;
     if(probe.status==='calculated'&&typeof probe.population==='number'&&probe.population>0){
       return showIsochrone(candidate,{auto:true,renderToken});
     }
     if(!first)first=candidate;
   }catch(_){/* Try the next corridor stop. */}
 }
 if(renderToken!==mapRenderToken)return;
 return showIsochrone(first,{auto:true,renderToken});
}

async function viewStop(stop){try{const data=await api(qs('/api/stop',{operator:stop.operator||state.operator,day:state.activeMapDate,stop_id:stop.id}));
 $('stop-panel').style.display='block';
 setText('stop-title',`${stop.name} · ${state.activeMapDate}`);
 setText('stop-state',`${data.departures.length} salidas · ${data.state==='planning'?'PLANIFICACIÓN':'HISTÓRICO PROGRAMADO'}`);
 $('stop-body').innerHTML=data.departures.length?data.departures.map(d=>`<tr><td><b>${escapeHTML(d.time||'—')}</b></td><td class="route">${escapeHTML(d.line||'?')}</td><td>${escapeHTML(d.destination||'—')}</td><td>${escapeHTML(d.direction||'—')}</td></tr>`).join(''):'<tr><td colspan="4" class="empty-table">No hay expediciones para esta parada y fecha</td></tr>';
 $('stop-panel').scrollIntoView({behavior:'smooth',block:'nearest'});
 }catch(e){alert(e.message)}}
function setQualityPanelVisible(visible){const panel=$('structural-quality');if(panel)panel.style.display=visible?'':'none'}
async function updateVersions(){try{let v=await api('/api/versions');$('version-list').innerHTML=v.length?v.map(s=>`<div><b>${escapeHTML(s.operator.toUpperCase())}</b> · Captura ${escapeHTML(s.snapshot_date)} · ${s.route_count} rutas · ${s.stop_count} paradas<br><span style="color:#829397">${escapeHTML(s.min_date)} → ${escapeHTML(s.max_date)} · ${escapeHTML(s.original_name)} · SHA ${s.sha256.slice(0,10)}…</span></div>`).join(''):'<div>No hay versiones cargadas.</div>';setQualityPanelVisible(v.length>0)}catch(e){setQualityPanelVisible(false);setText('import-status',e.message)}}
async function importFeed(e){e.preventDefault();const operator=$('import-operator').value,stamp=$('import-date').value,file=$('import-file').files[0];if(!operator||!stamp||!file)return;
 const form=new FormData();form.append('operator',operator);form.append('snapshot_date',stamp);form.append('file',file);
 const submit=$('upload-submit');submit.disabled=true;submit.textContent='Importando…';setText('import-status','Procesando archivos y calendario; puede tardar según el GTFS.');
 try{let resp=await fetch('/api/import',{method:'POST',body:form});let data=await resp.json();if(!resp.ok)throw Error(data.detail||'Fallo de importación');
 responseCache.clear();routeCatalogCache.clear();lastMapData=null;
 setText('import-status',data.already_imported?'Este GTFS ya estaba registrado.':`Importado: ${data.routes} rutas, ${data.stops} paradas, ${data.trips} viajes. Fuente ${data.min_date}–${data.max_date}.`);$('operator').value=operator;state.operator=operator;state.route='';await updateVersions();await refresh();await loadPublicationReadiness();await loadAuditMonthly();
 }catch(err){setText('import-status','No se pudo importar: '+err.message)}finally{submit.disabled=false;submit.textContent='Importar y analizar'}
}
document.addEventListener('DOMContentLoaded',init);

// Geographic analysis: no synthetic accessibility or demographic data.
let geoLayer=null;
function openGeo(){document.getElementById('geo-modal').classList.add('open')}
function closeGeo(){document.getElementById('geo-modal').classList.remove('open')}
function openSources(){document.getElementById('source-modal').classList.add('open')}
function closeSources(){document.getElementById('source-modal').classList.remove('open')}
async function loadGeoStatus(){
 try {let s=await api('/api/geo/status');
   setText('geo-walkways',s.walk_segments?`${fmt(s.walk_segments)} tramos`:'Sin red importada');
   setText('geo-census',s.census_sections?`${fmt(s.census_sections)} secciones`:'Sin geometrías · Eustat tabular');
   setText('geo-buildings',s.residential_buildings?`${fmt(s.residential_buildings)} edificios`:'Sin edificios residenciales');
   const accessReady=!!s.population_access_ready;
   const title=document.querySelector('#territorial-panel .panel-head h3');
   if(title)title.textContent=accessReady?'Accesibilidad peatonal · población estimada':'Accesibilidad peatonal · capas reales pendientes';
   setText('geo-method',accessReady
     ? `${fmt(s.resident_units)} anclajes poblacionales en la red · ${fmt(s.unallocated_population)} personas sin asignar · estimación no certificada e independiente del grosor visual.`
     : 'Falta la unión verificable entre secciones censales y red peatonal. No se mostrarán habitantes cubiertos inventados.');
   if(!accessReady){
     setText('geo-result',`Cobertura del recorrido pendiente · ${populationReferenceLabel()}`);
     setText('geo-stop-result',`Seleccione una parada · ${populationReferenceLabel()}`);
   } else {
     setText('geo-stop-result','Seleccione una parada para ver su población objetivo a 5 y 10 minutos.');
   }
 }catch(e){setText('geo-method','No se pudo consultar la base geográfica: '+e.message)}
}
async function importGeo(e){e.preventDefault();const file=$('geo-file').files[0];if(!file)return;
 const layer=$('geo-layer').value;const form=new FormData();form.append('layer',layer);form.append('file',file);
 $('geo-upload').disabled=true;setText('geo-upload-status','Procesando geometrías en la red local…');
 try{const response=await fetch('/api/geo/import',{method:'POST',body:form});const data=await response.json();if(!response.ok)throw Error(data.detail||'Error al importar');
 responseCache.clear();lastMapData=null;
 setText('geo-upload-status',`Capa procesada. ${data.walk_segments} tramos peatonales, ${data.census_sections} secciones y ${data.residential_buildings} edificios residenciales.`);await loadGeoStatus();await loadPublicationReadiness();}
 catch(e){setText('geo-upload-status','No se ha importado: '+e.message)}finally{$('geo-upload').disabled=false}
}
async function downloadSource(source,button){
 button.disabled=true;setText('source-status',`Solicitando ${source} a la fuente oficial…`);
 const endpoint=source==='buildings'?'/api/sources/buildings':source==='osm'?'/api/sources/osm':['ekialdebus','irunbus','euskotren','errenteria_urbanoa'].includes(source)?qs('/api/sources/refresh',{operator:source}):qs('/api/sources/reference',{name:source});
 try{const response=await fetch(endpoint,{method:'POST'});const result=await response.json();if(!response.ok)throw Error(result.detail||'Descarga fallida');
 responseCache.clear();routeCatalogCache.clear();lastMapData=null;
   setText('source-status',`${source}: obtenido y registrado. ${result.trips===undefined?'Referencia conservada; requiere transformación geográfica.':`${result.trips} expediciones base de GTFS`}`);
   await updateVersions();await loadGeoStatus();await refresh();}
 catch(e){setText('source-status',`${source}: no disponible — ${e.message}. Puedes importar el fichero manualmente si lo obtienes de la fuente.`)}finally{button.disabled=false}
}
function populationReferenceLabel(){
 return populationReference.loaded&&typeof populationReference.total_population==='number'
   ? `${fmt(populationReference.total_population)} hab. de referencia Eustat 2025 · Gipuzkoa`
   : 'referencia poblacional Eustat no cargada';
}
async function showIsochrone(stop,{auto=false,renderToken=null}={}){
 if(renderToken!==null&&renderToken!==mapRenderToken)return;
 const requestId=++isoRequestId;
 if(window.reviewMap)window.reviewMap.clearIsochrone();
 setText('geo-stop-result',`Calculando cobertura de ${stop.name}…`);
 try{
  const base={operator:stop.operator||state.operator,day:state.activeMapDate,stop_id:stop.id};
  const [iso5,iso10]=await Promise.all([
    stopApi(qs('/api/geo/stop',{...base,minutes:5})),
    stopApi(qs('/api/geo/stop',{...base,minutes:10}))
  ]);
  if(requestId!==isoRequestId||(renderToken!==null&&renderToken!==mapRenderToken))return;
  const geometries={};
  if(iso5.status==='calculated'&&iso5.geometry)geometries[5]=iso5.geometry;
  if(iso10.status==='calculated'&&iso10.geometry)geometries[10]=iso10.geometry;
  window.reviewMap.displayIsochrones(geometries);
  if(window.reviewMap && Number.isFinite(stop.lon) && Number.isFinite(stop.lat))window.reviewMap.focusOn(stop.lon,stop.lat,true);
  if(!Object.keys(geometries).length){
    const reason=iso5.status==='missing_pedestrian_network'||iso10.status==='missing_pedestrian_network'
      ? 'falta una red peatonal cargada'
      : 'la parada no está conectada a la red peatonal';
    setText('geo-stop-result',`${stop.name} · ${populationReferenceLabel()} · cobertura de parada no calculable: ${reason}.`);
    if(!auto){
      const kpiLabel=$('kpi-population')?.closest('.kpi')?.querySelector('.name');
      if(kpiLabel)kpiLabel.textContent='Población de referencia';
      setText('kpi-population',populationReference.loaded?fmt(populationReference.total_population):'—');
      setText('kpi-population-note',`Parada: ${stop.name} · no equivale a cobertura de la isócrona`);
    }
    setText('geo-method','La isócrona sólo es calculable cuando la parada se conecta a la red peatonal y la población censal está anclada a esa misma red.');
    return;
  }
  const formatPopulation=p=>typeof p==='number'?fmt(p)+' hab.':'no calculable';
  const method=(iso10.population_method||'').includes('network_anchor')
    ? 'asignación censal a la red peatonal'
    : 'asignación a edificios residenciales';
  setText('geo-stop-result',`${stop.name} · 5 min: ${formatPopulation(iso5.population)} · 10 min: ${formatPopulation(iso10.population)} · ${method}`);
  if(!auto){const kpiLabel=$('kpi-population')?.closest('.kpi')?.querySelector('.name');if(kpiLabel)kpiLabel.textContent=iso10.population===null?'Población base · Gipuzkoa':'Población cubierta · parada';setText('kpi-population',iso10.population===null?'—':fmt(iso10.population));
    setText('kpi-population-note',iso10.population===null
      ? `Parada: ${stop.name} · ${populationReferenceLabel()} · falta unión espacial`
      : `Parada: ${stop.name} · 10 min andando · ${method} · no demanda`);}
  setText('geo-method',`Parada: Dijkstra sobre red peatonal OSM real; naranja 5 min y azul 10 min. Población estimada por ${method}; no equivale a demanda ni está certificada.`);
 }catch(e){if(requestId===isoRequestId)setText('geo-stop-result','Error al calcular las isócronas: '+e.message)}
}
document.addEventListener('DOMContentLoaded',()=>{
 $('geo-import-button').addEventListener('click',openGeo);
 $('geo-network-button').addEventListener('click',computeNetworkPopulation);
 $('geo-close').addEventListener('click',closeGeo);
 $('source-button').addEventListener('click',openSources);
 $('source-close').addEventListener('click',closeSources);
 $('geo-form').addEventListener('submit',importGeo);
 document.querySelectorAll('.download-source').forEach(button=>button.addEventListener('click',()=>downloadSource(button.dataset.source,button)));
 loadGeoStatus();
});

let networkRequestId=0;
async function stopApi(endpoint){const result=await api(endpoint);return result.kind==='stop_isochrone'?waitForJob(result):result;}
async function waitForJob(job,isCurrent=()=>true){
 const until=Date.now()+905000;let delay=500;
 while(['pending','running'].includes(job.status)){
  if(!isCurrent())throw Error('Selección sustituida');
  if(Date.now()>until)throw Error('El cálculo sigue pendiente; vuelve a consultarlo');
  await new Promise(resolve=>setTimeout(resolve,delay));
  job=await api(`/api/analysis/jobs/${encodeURIComponent(job.id)}`);delay=Math.min(3000,delay*1.25);
 }
 if(job.status!=='complete')throw Error(job.error||`Trabajo ${job.status}`);
 return job.result;
}
async function runTask(kind,params){
 const job=await api('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,day:params.day||params.new_day||state.activeMapDate,...params})});
 return waitForJob(job);
}
async function computeNetworkPopulation({silent=false}={}){
 const requestId=++networkRequestId;
 const button=$('geo-network-button');button.disabled=true;setText('geo-result','Calculando cobertura única…');
 try{
  const queued=await api('/api/analysis/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operator:$('map-both').checked?'all':state.operator,day:state.activeMapDate,route_id:$('map-both').checked?'':state.route||'',minutes:10})});
  const data=await waitForJob(queued,()=>requestId===networkRequestId);
 if(requestId!==networkRequestId)return;
 if(data.population===null){
   setText('geo-result',data.status==='missing_gtfs'
     ? 'Falta GTFS de al menos un operador; no se puede asociar el recorrido a paradas.'
     : `Cobertura del recorrido no calculable · ${populationReferenceLabel()} · faltan geometrías censales y red peatonal.`);
   setText('kpi-population',populationReference.loaded?fmt(populationReference.total_population):'—');
   const kpiLabel=$('kpi-population')?.closest('.kpi')?.querySelector('.name');if(kpiLabel)kpiLabel.textContent='Población base · Gipuzkoa';
   setText('kpi-population-note',`${populationReferenceLabel()} · no equivale a cobertura del recorrido`);
   setText('geo-method','La suma de paradas no se usa: importa la geometría oficial de secciones Eustat y la red peatonal, o edificios residenciales para una estimación dasimétrica más precisa.');
   return;
 }
 const scope=data.route_id?`recorrido ${data.route_id}`:data.operator==='all'?'todos los operadores':`toda la red de ${operatorName(state.operator)}`;
 setText('geo-result',`${fmt(data.population)} habitantes únicos estimados · ${scope} · 10 min`);
 const kpiLabel=$('kpi-population')?.closest('.kpi')?.querySelector('.name');if(kpiLabel)kpiLabel.textContent='Población cubierta · recorrido';
 setText('kpi-population',fmt(data.population));
  const method=(data.population_method||'').includes('network_anchor')?'asignación censal a puntos de la red peatonal':(data.population_method||'').includes('residential')?'asignación a edificios residenciales':'modelo peatonal versionado';
 setText('kpi-population-note',`${scope} · ${data.stops_connected}/${data.stops} paradas · 10 min · cobertura única · ${method}`);
 setText('geo-method',`${data.stops_connected} paradas conectadas de ${data.stops}; población deduplicada entre isócronas mediante ${method}. ${fmt(data.unallocated_population||0)} habitantes sin asignación residencial. Estimación no certificada.`);
 }catch(e){if(requestId===networkRequestId)setText('geo-result','No calculable: '+e.message)}finally{button.disabled=false}
}

// Historical audit and provisional spatial stop matching: API data, no simulated results.
async function loadPublicationReadiness(){
  const capabilities=await api('/api/capabilities');if(!capabilities.local_admin||!capabilities.mutable)return;
 try{
  const r=await api('/api/audit/readiness');
  setText('audit-gate',r.data_gate_passed?'Datos verificados · pendiente aprobación de publicación':'PUBLICACIÓN BLOQUEADA');
  setText('audit-summary',`Histórico 01/01/2025–18/10/2026: ${r.target_days_per_operator} fechas exigidas por operador. La certificación requiere revisión documental de horarios y cobertura geográfica.`);
  $('audit-issues').innerHTML=Object.entries(r.operators).map(([op,x])=>
   `<div><b>${escapeHTML(op)}</b>: ${fmt(x.verified)} verificadas · ${fmt(x.located_unverified)} localizadas sin verificar · ${fmt(x.missing)} sin fuente · ${fmt(x.rejected)} rechazadas.</div>`).join('')+
   (r.geographic_gate_passed?'':'<div>Faltan capas o cobertura geográfica provincial completa de Gipuzkoa.</div>');
 }catch(e){setText('audit-gate','Auditoría no disponible: '+e.message)}
}
async function loadAuditMonthly(){
 const op=state.operator,yy=state.year;
 try{
  const grid=await api(qs('/api/audit/month-grid',{operator:op,year:yy}));
  if(op!==state.operator||yy!==state.year)return;
  $('audit-month-grid').innerHTML=grid.months.map((m,i)=>{
   const h=m.historical_days,p=m.planning_days,verified=m.states.verified||0,located=m.states.located_unverified||0;
   let col=h===0?'#dce9fa':verified===h?'#dff5e7':located?'#fcf0d6':'#edf0f2';
   let tx=h===0?'Plan':`${verified}/${h}`;
   return `<div style="text-align:center;border-radius:7px;padding:8px 2px;background:${col};font-size:11px" title="${months[i]}: ${verified} verificadas, ${located} sin verificar, ${m.states.missing||0} sin fuente, ${p} planificación"><b>${months[i].slice(0,3)}</b><br>${tx}${p&&h?' + P':''}</div>`;
  }).join('');
 }catch(e){setText('audit-month-grid','Auditoría mensual no disponible')}
}
async function compareStopsUI(){
 const button=$('diff-run');button.disabled=true;setText('diff-results','Calculando diferencias entre paradas…');
 try{
  const result=await runTask('compare_stops',{operator:state.operator,old_day:$('diff-old').value,new_day:$('diff-new').value,territorial_scope:$('diff-local').checked});
  if(!result.comparable){setText('diff-results',result.reason);return}
  setText('diff-results',`Fuente previa: ${result.counts.old} paradas; fuente posterior: ${result.counts.new}. Coincidencias espaciales: ${result.counts.matched}; posibles altas: ${result.counts.added}; posibles bajas: ${result.counts.removed}; desplazamientos >10 m: ${result.counts.moved_over_10m}. ${result.warning}`);
 }catch(e){setText('diff-results','No se puede comparar: '+e.message)}finally{button.disabled=false}
}
document.addEventListener('DOMContentLoaded',()=>{
 $('diff-run').addEventListener('click',compareStopsUI);
 ['operator','year'].forEach(id=>$(id).addEventListener('change',loadAuditMonthly));
 loadPublicationReadiness();loadAuditMonthly();
});

async function runFrequencyCoverage(){
 const button=$('frequency-run');button.disabled=true;
 setText('frequency-status','Calculando población única por frecuencia…');$('frequency-values').innerHTML='';
 try{
  const [start,end]=$('frequency-hours').value.split(',').map(Number);
  const d=await runTask('service_coverage',{operator:$('frequency-operator').value,
    day:$('frequency-date').value,hour_start:start,hour_end:end});
  if(d.status!=='estimated'){
    setText('frequency-status',d.status==='missing_gtfs'?'No calculable: falta GTFS de uno o varios operadores para esta fecha.':'No calculable: faltan capas geográficas verificables.');
    return;
  }
  setText('frequency-status',`${d.time_state==='planning'?'PLANIFICACIÓN':'HISTÓRICO PROGRAMADO'} · ${d.day} · Datos estimados, NO certificados. Los umbrales son acumulativos.`);
  $('frequency-values').innerHTML=[15,30,60].map(threshold=>{
    const x=d.population_by_frequency[String(threshold)];
    return `<div class="kpi" style="min-width:0"><div class="name">Intervalo máximo ≤ ${threshold} min</div><div class="number">${x.population===null?'—':fmt(x.population)}</div><div class="foot">Habitantes únicos · ${fmt(x.served_stops_in_study_area)} paradas</div></div>`;
  }).join('');
 }catch(e){setText('frequency-status','Error: '+e.message)}finally{button.disabled=false}
}
document.addEventListener('DOMContentLoaded',()=>{$('frequency-run').addEventListener('click',runFrequencyCoverage)});

// Version confirmation avoids opening a prior server tab by mistake.
async function confirmAppVersion(){
  try {
    const info=await api('/api/version');
    window.OBSERVATORIO_VERSION=info.version;
    setText('running-version',document.body.classList.contains('review-mode')?`DEMO · v${info.version}`:`v${info.version} · CORTE ${info.date_cutoff}`);
    setText('brand-version',`Gipuzkoa · ${document.body.classList.contains('review-mode')?'DEMO':'DATOS REALES'} · GTFS oficial`);
  } catch(error) { setText('running-version','VERSIÓN NO VERIFICABLE'); }
}
async function compareRoutesUI(){
  const button=$('routes-run');button.disabled=true;setText('route-diff-status','Calculando correspondencias por paradas…');
  try{
    const doc=await runTask('compare_routes',{operator:state.operator,old_day:$('routes-old').value,new_day:$('routes-new').value});
    if(!doc.comparable){setText('route-diff-status',doc.reason||'Sin GTFS para fechas seleccionadas');$('route-diff-body').innerHTML='<tr><td colspan="5" class="empty-table">Sin comparación disponible</td></tr>';return;}
    setText('route-diff-status',`${doc.old_routes} líneas antes · ${doc.new_routes} después · ${doc.pairs.length} correspondencias provisionales · ${doc.unmatched_old.length} sin pareja antigua y ${doc.unmatched_new.length} nuevas sin pareja. No certificado.`);
    $('route-diff-body').innerHTML=doc.pairs.length?doc.pairs.map(r=>`<tr><td class="route">${escapeHTML(r.old_route)}</td><td class="route">${escapeHTML(r.new_route)}</td><td>${fmt(r.shared_physical_stops)}</td><td>${fmt(r.stop_jaccard*100,1)}% · ${escapeHTML(r.matching_quality)}</td><td>${fmt(r.old_trips)} / ${fmt(r.new_trips)}</td></tr>`).join(''):'<tr><td colspan="5" class="empty-table">Sin correspondencias automáticas: requieren revisión humana</td></tr>';
  }catch(e){setText('route-diff-status',e.message)}finally{button.disabled=false}
}
document.addEventListener('DOMContentLoaded',()=>{
  confirmAppVersion();
  $('routes-run').addEventListener('click',compareRoutesUI);
});

async function runQuality(){
  const button=$('quality-run');button.disabled=true;
  setText('quality-output','Revisando versiones…');
  try {
    const q=await api('/api/quality');
    if(q.versions===0){setText('quality-output','Sin GTFS importados. No hay cifras de oferta reales para analizar.');return;}
    $('quality-output').innerHTML=q.feeds.map(f=>`<div><b>${escapeHTML(f.operator)} · ${escapeHTML(f.snapshot_date)}</b> — ${f.structurally_valid?'sin errores estructurales':'ERRORES ESTRUCTURALES'} · ${fmt(f.summary.routes)} líneas · ${fmt(f.summary.stops)} paradas · ${fmt(f.summary.trips)} expediciones base.<br>${f.issues.length?f.issues.map(x=>`${escapeHTML(x.severity)}: ${escapeHTML(x.description)} (${fmt(x.records)})`).join(' · '):'No se detectaron incidencias estructurales.'}<br><small>Histórico NO certificado</small></div>`).join('');
  }catch(e){setText('quality-output','Error en auditoría: '+e.message)}finally{button.disabled=false}
}
document.addEventListener('DOMContentLoaded',()=>$('quality-run').addEventListener('click',runQuality));


// Base oficial de Eustat cargada como referencia provincial; la cobertura de
// isócronas sigue dependiendo de las geometrías territoriales disponibles.
function renderEustatQuickReference(x){
  const kpis=document.querySelector('.kpis');if(!kpis)return;
  let card=$('eustat-quick-reference');
  if(!card){card=document.createElement('div');card.id='eustat-quick-reference';kpis.insertAdjacentElement('afterend',card)}
  card.className='notice';
  card.style.cssText='margin:-3px 0 17px;padding:12px 15px;line-height:1.5;border:1px solid #d9e9e4;background:#f1f8f5;color:#4f6d70;font-size:11px';
  if(!x.loaded){card.innerHTML='<b style="color:#8b5b18">Eustat 2025 pendiente de carga</b> · No hay una referencia censal disponible en esta instancia.';return;}
  const total=fmt(x.total_population),sections=fmt(x.sections),municipalities=fmt(x.municipality_count),bidasoa=fmt(x.by_region?.Bidasoaldea),oarso=fmt(x.by_region?.Oarsoaldea),rest=fmt(x.by_region?.['Resto de Gipuzkoa']);
  const spatial=x.geography_complete
    ? 'La geometría disponible cubre Gipuzkoa.'
    : 'La población es provincial; la geometría peatonal provincial todavía no está completa en esta instancia.';
  card.innerHTML=`<b style="color:#176958">Eustat 2025 · Gipuzkoa cargado</b> · ${total} habitantes en ${municipalities} municipios y ${sections} secciones · Bidasoaldea ${bidasoa} · Oarsoaldea ${oarso} · resto ${rest}. <span>${spatial}</span>`;
}
async function loadEustatPopulation(){
  try{
    const x=await api('/api/population/status');
    populationReference={loaded:!!x.loaded,total_population:x.total_population??null,sections:x.sections??null};
    const scopeNote=document.querySelector('aside .side-note');
    if(scopeNote)scopeNote.innerHTML=`<strong>Provincia de Gipuzkoa</strong>Población Eustat 2025: base total provincial. ${x.geography_complete?'La cobertura peatonal y censal provincial está disponible.':'La cobertura peatonal provincial sigue pendiente de completar.'}`;
    const populationTitle=document.querySelector('#eustat-population-panel .panel-head h3');
    if(populationTitle)populationTitle.textContent='Población Eustat 2025 · Gipuzkoa';
    const populationCard=document.querySelector('#eustat-population-panel .kpi .name');
    if(populationCard)populationCard.textContent='Población total · Gipuzkoa';
    if(!x.loaded){setText('eustat-validation','CSV no importado');setText('eustat-municipality-rows','Sin datos oficiales cargados');renderEustatQuickReference(x);return;}
    setText('eustat-validation',`${fmt(x.sections)} secciones · ${fmt(x.municipality_count)} municipios · CSV 2025 verificado`);
    setText('eustat-total',fmt(x.total_population));
    setText('eustat-bidasoa',fmt(x.by_region.Bidasoaldea));
    setText('eustat-oarso',fmt(x.by_region.Oarsoaldea));
    // Keep the route-coverage KPI honest while making the included population
    // data visible immediately on first load. It is a territorial reference,
    // never a claim that the whole population is reachable by the selected line.
    if($('kpi-population')?.textContent.trim()==='—'){
      const kpiLabel=$('kpi-population')?.closest('.kpi')?.querySelector('.name');if(kpiLabel)kpiLabel.textContent='Población de referencia';
      setText('kpi-population',fmt(x.total_population));
      setText('kpi-population-note','Base Eustat 2025 · Gipuzkoa · no equivale a cobertura del recorrido');
    }
    const order=Object.keys(x.municipalities||{}).sort((a,b)=>a.localeCompare(b,'es'));
    $('eustat-municipality-rows').innerHTML=order.map(name=>{
      const d=x.municipalities[name];return `<tr><td>${escapeHTML(name)}</td><td>${fmt(d.population)}</td><td>${fmt(d.sections)}</td></tr>`;
    }).join('');
    setText('eustat-note',`CSV original de Gipuzkoa conservado y verificado (SHA256: ${x.sha256.slice(0,12)}…). La población objetivo de las isócronas se estima donde existe geometría censal y red peatonal cargadas; ${x.geography_complete?'la cobertura espacial es provincial.':'la cobertura espacial provincial todavía está pendiente.'}`);
    renderEustatQuickReference(x);
    const stopText=$('geo-stop-result')?.textContent||'';
    if(stopText.includes('referencia poblacional Eustat no cargada'))setText('geo-stop-result',stopText.replace('referencia poblacional Eustat no cargada',populationReferenceLabel()));
    const routeText=$('geo-result')?.textContent||'';
    if(routeText.includes('referencia poblacional Eustat no cargada'))setText('geo-result',routeText.replace('referencia poblacional Eustat no cargada',populationReferenceLabel()));
  }catch(e){setText('eustat-validation','Error de datos');setText('eustat-note','Error al cargar Eustat: '+e.message)}
}
document.addEventListener('DOMContentLoaded',loadEustatPopulation);

document.addEventListener('DOMContentLoaded',async()=>{
 try{
  const c=await api('/api/capabilities');
  if(!c.mutable||!c.local_admin){
   for(const id of ['import-button','source-button','geo-import-button','eustat-import','quality-run']){
    const element=$(id);if(element)element.hidden=true;
   }
  }
  if(!c.local_admin||!c.mutable){
   $('quality-run')?.closest('.panel')?.setAttribute('hidden','');
   $('publication-audit')?.setAttribute('hidden','');
  }
 }catch(error){console.warn('No se pudieron consultar permisos',error)}
});

// Product-review flag comes from the server, not from the GTFS feed names.
document.addEventListener('DOMContentLoaded',async()=>{
  try{
    const res=await fetch('/api/demo/status',{cache:'no-store'});
    const cfg=await res.json();
    if(!cfg.demo){
      const banner=document.querySelector('.review-banner');
      if(banner)banner.innerHTML='<strong>DATOS REALES · GTFS IMPORTADO</strong> <span class="soft">— Instantáneas entregadas por el usuario. Horarios programados: no equivalen a servicio prestado. Eustat 2025 y las secciones oficiales permiten estimar la población dentro de las isócronas; los edificios residenciales mejoran la precisión.</span>';
      const head=document.querySelector('header .brand p');if(head)head.textContent=`Gipuzkoa · DATOS REALES v${cfg.version||window.OBSERVATORIO_VERSION||'?' } · GTFS oficial`;
      const tag=document.querySelector('header .tag');if(tag)tag.textContent=`DATOS REALES · v${cfg.version||'?'}`;
      const mapTitle=document.querySelector('.map-frame')?.closest('.panel')?.querySelector('.panel-head h3');if(mapTitle)mapTitle.textContent='Mapa geográfico real · Líneas GTFS';
      const legend=document.querySelector('.mini-legend');if(legend)legend.textContent='● Parada GTFS · ━ Recorrido según shape GTFS';
      const popNote=document.getElementById('kpi-population-note');if(popNote && popNote.textContent.includes('No calculable'))popNote.textContent='Base Eustat 2025 incluida · no equivale a cobertura del recorrido';
      const geoTitle=document.querySelector('#territorial-panel .panel-head h3');if(geoTitle)geoTitle.textContent='Accesibilidad peatonal · cobertura provincial';
    }
    if(cfg.demo){
      document.body.classList.add('review-mode');
      for(const id of ['import-button','source-button','geo-import-button','quality-run']){const el=document.getElementById(id);if(el)el.style.display='none';}
      const footprint=document.getElementById('geo-method');if(footprint)footprint.insertAdjacentText('afterbegin','ISÓCRONAS SINTÉTICAS · no cartografía oficial. ');
      const head=document.querySelector('header .brand p');if(head)head.textContent=`Gipuzkoa · DEMO v${cfg.version||window.OBSERVATORIO_VERSION||'?' } · Red peatonal OSM real`;
      const version=document.getElementById('running-version');if(version)version.textContent=`PRODUCT REVIEW · DEMO v${cfg.version||window.OBSERVATORIO_VERSION||'?'}`;
      const note=document.getElementById('quality-content');
      if(note)note.insertAdjacentHTML('afterbegin','<div class="notice warn" style="margin-bottom:9px"><b>DATOS DEMO</b> · Horarios, recorridos y paradas son ficticios. La población oficial Eustat 2025 es real, pero la cobertura accesible es simulada.</div>');
    }
  }catch(e){console.warn('No se pudo detectar el modo demo',e)}
});
