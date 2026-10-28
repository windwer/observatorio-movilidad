/** Geographic review map. Basemap: authentic web cartography, never invented roads.
 * Layers from geoEuskadi / Esri are separate from the DEMO route and stop data.
 * No calls to transit-data APIs or volunteer-run tile servers.
 */
'use strict';
function euskadiExportTile(z,x,y){
  // GeoEuskadi publishes the official base through an ArcGIS MapServer. The
  // export request below uses the same Web-Mercator tile bounds as the SVG
  // renderer, avoiding the blank tiles produced by the legacy WMTS tile path
  // in some browsers while retaining a real official raster source.
  const half=20037508.342789244,span=(half*2)/Math.pow(2,z);
  const xmin=-half+x*span,xmax=xmin+span;
  const ymax=half-y*span,ymin=ymax-span;
  return `https://www.geo.euskadi.eus/geoeuskadi/rest/services/U11/WMTS_KARTO/MapServer/export?bbox=${xmin.toFixed(2)}%2C${ymin.toFixed(2)}%2C${xmax.toFixed(2)}%2C${ymax.toFixed(2)}&bboxSR=3857&imageSR=3857&size=256%2C256&format=png&transparent=false&f=image`;
}
class GeographicReviewMap {
  constructor(container, handlers={}) {
    this.container=container; this.handlers=handlers;
    this.ns='http://www.w3.org/2000/svg';
    this.z0=12; this.worldSize=256*Math.pow(2,this.z0);
    // Province-wide cartographic extent (derived from the 544 official
    // Gipuzkoa census sections), not only the original eastern demo window.
    this.bounds={west:-2.630,east:-1.700,north:43.420,south:42.910};
    const nw=this.mercator([this.bounds.west,this.bounds.north]);
    const se=this.mercator([this.bounds.east,this.bounds.south]);
    this.origin={x:nw[0],y:nw[1]};
    this.base={x:0,y:0,w:se[0]-nw[0],h:se[1]-nw[1]};
    this.view={...this.base}; this.drag=null; this.isoFeatures={}; this.isoVisible={5:true,10:true};
    this.basemapReady=false;this.errorTiles=new Set();this.tileElements=new Map();
    this.routeNodes=new Map();this.stopNodes=new Map();this.projected=new WeakMap();this.viewFrame=null;this.lastTolerance=null;
    // Prefer the official regional base. Esri remains an explicit fallback
    // when a browser/network cannot reach GeoEuskadi.
    this.tileProvider='euskadi';
    this.providers={
      euskadi:{name:'GeoEuskadi',url:euskadiExportTile},
      esri:{name:'Esri World Topographic Map',url:(z,x,y)=>`https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/${z}/${y}/${x}`}
    };
    this.svg=document.createElementNS(this.ns,'svg');
    this.svg.setAttribute('role','img');
    this.svg.setAttribute('aria-label','Mapa cartográfico georreferenciado de Gipuzkoa, con capas de recorridos, paradas e isócronas de cinco y diez minutos.');
    this.svg.setAttribute('preserveAspectRatio','xMidYMid meet');
    this.svg.style.background='#edf2f0';this.container.append(this.svg);
    this.tiles=this.g('basemap');this.geo=this.g('routes');this.drawIso=this.g('isochrones');this.points=this.g('stops');
    this.syncView();
    this.buildControls();
    this.popup=document.createElement('div');this.popup.className='offline-map-popup';this.container.append(this.popup);
    this.svg.addEventListener('wheel',e=>{e.preventDefault();this.zoom(e.deltaY>0?1.19:.84)}, {passive:false});
    this.svg.addEventListener('pointerdown',e=>{
      if(e.button!==0 || e.target.closest('.stop-point,.route-path'))return;
      this.drag={x:e.clientX,y:e.clientY,view:{...this.view}};
      this.svg.setPointerCapture(e.pointerId);this.hidePopup();
    });
    this.svg.addEventListener('pointermove',e=>{
      if(!this.drag)return;
      const scale=this.getScreenScale(this.svg.getBoundingClientRect());
      this.view.x=this.drag.view.x-(e.clientX-this.drag.x)/scale;
      this.view.y=this.drag.view.y-(e.clientY-this.drag.y)/scale;
      this.syncView();
    });
    for(const event of ['pointerup','pointercancel','lostpointercapture'])this.svg.addEventListener(event,()=>{this.drag=null});
    this.svg.addEventListener('dblclick',e=>{e.preventDefault();this.reset()});
    this.refreshTiles();
  }
  mercator([lon,lat]){
    const p=Math.max(-85.05113,Math.min(85.05113,lat))*Math.PI/180;
    return [(lon+180)/360*this.worldSize,(1-Math.asinh(Math.tan(p))/Math.PI)/2*this.worldSize];
  }
  project(point){const [x,y]=this.mercator(point);return [x-this.origin.x,y-this.origin.y]}
  element(tag,attrs={},parent=this.svg){const e=document.createElementNS(this.ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));parent.append(e);return e}
  g(id){return this.element('g',{'data-layer':id})}
  getScreenScale(rect){return Math.min(rect.width/this.view.w,rect.height/this.view.h)}
  syncView(){
    this.svg.setAttribute('viewBox',`${this.view.x} ${this.view.y} ${this.view.w} ${this.view.h}`);
    if(this.viewFrame===null)this.viewFrame=requestAnimationFrame(()=>{
      this.viewFrame=null;this.refreshTiles();this.updateRouteDetail();
    });
  }
  routePoints(coords,tolerance){
    let points=this.projected.get(coords);
    if(!points){points=coords.map(p=>this.project(p));this.projected.set(coords,points);}
    // Iterative Douglas-Peucker: bounded screen-space error, preserving endpoints.
    if(points.length<3)return points.map(p=>p.join(',')).join(' ');
    const keep=new Uint8Array(points.length);keep[0]=keep[points.length-1]=1;
    const stack=[[0,points.length-1]],limit=tolerance*tolerance;
    while(stack.length){
      const [first,last]=stack.pop(),a=points[first],b=points[last];
      const dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy;
      let maximum=limit,index=-1;
      for(let i=first+1;i<last;i++){
        const p=points[i],t=length?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)):0;
        const distance=(p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2;
        if(distance>maximum){maximum=distance;index=i;}
      }
      if(index!==-1){keep[index]=1;stack.push([first,index],[index,last]);}
    }
    return points.filter((_,i)=>keep[i]).map(p=>p.map(n=>n.toFixed(3)).join(',')).join(' ');
  }
  updateRouteDetail(force=false){
    if(!this.routeNodes?.size)return;
    const scale=this.getScreenScale(this.svg.getBoundingClientRect());
    if(!scale)return;
    const tolerance=.6/scale;
    if(!force&&this.lastTolerance&&Math.abs(tolerance/this.lastTolerance-1)<.2)return;
    this.lastTolerance=tolerance;
    for(const node of this.routeNodes.values()){
      const points=this.routePoints(node.route.coordinates,tolerance);
      node.poly.setAttribute('points',points);node.line.setAttribute('points',points);
    }
  }
  reset(){this.view={...this.base};this.syncView();this.hidePopup()}
  zoom(factor){
    const w=Math.min(this.base.w*4,Math.max(42,this.view.w*factor));
    const h=w*this.base.h/this.base.w;
    this.view.x+=(this.view.w-w)/2;this.view.y+=(this.view.h-h)/2;
    this.view.w=w;this.view.h=h;this.syncView();this.hidePopup();
  }
  setBasemap(provider){if(!this.providers[provider])return;this.tileProvider=provider;this.tileElements.clear();this.tiles.replaceChildren();this.errorTiles.clear();this.basemapReady=false;this.updateBasemapStatus('Cargando cartografía · '+this.providers[provider].name,false);this.refreshTiles()}
  tileGrid(){
    const scale=this.base.w/this.view.w;
    let z=Math.max(9,Math.min(17,this.z0+Math.floor(Math.log2(Math.max(.25,scale))+.4)));
    while(true){
      const size=256/Math.pow(2,z-this.z0);
      const x1=Math.max(0,Math.floor((this.view.x+this.origin.x)/size)-1);
      const x2=Math.min(Math.pow(2,z)-1,Math.ceil((this.view.x+this.view.w+this.origin.x)/size)+1);
      const y1=Math.max(0,Math.floor((this.view.y+this.origin.y)/size)-1);
      const y2=Math.min(Math.pow(2,z)-1,Math.ceil((this.view.y+this.view.h+this.origin.y)/size)+1);
      if((x2-x1+1)*(y2-y1+1)<=110||z===9)return {z,size,x1,x2,y1,y2};
      z--;
    }
  }
  refreshTiles(){
    if(!this.tiles || !this.view)return;
    const {z,size,x1,x2,y1,y2}=this.tileGrid();
    const needed=new Set();
    for(let x=x1;x<=x2;x++)for(let y=y1;y<=y2;y++){
      const key=`${z}/${x}/${y}/${this.tileProvider}`;needed.add(key);
      if(this.tileElements.has(key))continue;
      const im=this.element('image',{x:x*size-this.origin.x,y:y*size-this.origin.y,width:size+.1,height:size+.1,'preserveAspectRatio':'none'},this.tiles);
      const primary=this.providers[this.tileProvider].url(z,x,y);
      const alternate=this.providers[this.tileProvider==='euskadi'?'esri':'euskadi'].url(z,x,y);
      let fallback=false,timer;
      const useAlternate=()=>{if(!fallback&&im.isConnected){fallback=true;im.setAttribute('href',alternate);}};
      timer=setTimeout(useAlternate,6000);
      im.addEventListener('load',()=>{clearTimeout(timer);this.basemapReady=true;this.updateBasemapStatus('Cartografía real · '+(fallback?'servidor alternativo':this.providers[this.tileProvider].name),false)});
      im.addEventListener('error',()=>{
        clearTimeout(timer);
        if(!fallback)useAlternate();
        else{this.errorTiles.add(key);im.remove();this.updateBasemapStatus('Mapa base no disponible. Comprueba conexión y cambia de proveedor.',true)}
      });
      im.setAttribute('href',primary);this.tileElements.set(key,im);
    }
    for(const [key,image] of this.tileElements){if(!needed.has(key)){image.remove();this.tileElements.delete(key)}}
  }
  buildControls(){
    const tools=document.createElement('div');tools.className='map-tools';
    for(const [label,title,cb] of [['+','Acercar',()=>this.zoom(.73)],['−','Alejar',()=>this.zoom(1.36)],['⌂','Vista completa',()=>this.reset()]]){
      const b=document.createElement('button');b.type='button';b.textContent=label;b.title=title;b.setAttribute('aria-label',title);b.addEventListener('click',cb);tools.append(b)
    }this.container.append(tools);
    const picker=document.createElement('div');picker.className='map-basemap-picker';
    const lbl=document.createElement('label');lbl.textContent='Mapa base';lbl.htmlFor='map-basemap';
    this.basemapSelect=document.createElement('select');this.basemapSelect.id='map-basemap';
    for(const [k,v] of Object.entries(this.providers)){const op=document.createElement('option');op.value=k;op.textContent=v.name;this.basemapSelect.append(op)}
    this.basemapSelect.value=this.tileProvider;
    this.basemapSelect.addEventListener('change',()=>this.setBasemap(this.basemapSelect.value));picker.append(lbl,this.basemapSelect);this.container.append(picker);
    this.status=document.createElement('div');this.status.className='map-tile-status';this.status.textContent='Cargando cartografía oficial…';this.container.append(this.status);
    const legend=document.createElement('div');legend.className='map-iso-selector';
    const h=document.createElement('strong');h.textContent='Accesibilidad peatonal';legend.append(h);
    for(const [minutes,color] of [[5,'#e69b32'],[10,'#3a8ed0']]){
      const label=document.createElement('label');
      const input=document.createElement('input');input.type='checkbox';input.checked=true;input.dataset.iso=String(minutes);
      input.addEventListener('change',()=>{this.isoVisible[minutes]=input.checked;this.drawIsochrones()});
      const swatch=document.createElement('span');swatch.className='map-iso-swatch';swatch.style.background=color;
      label.append(input,swatch,document.createTextNode(`${minutes} min`));legend.append(label)
    }
    const note=document.createElement('small');note.textContent='Alcance por red OSM real · no radio euclídeo. Haz clic en otra parada';legend.append(note);this.container.append(legend);
    this.credit=document.createElement('div');this.credit.className='map-source-credit';this.container.append(this.credit);this.updateBasemapCredit();
  }
  updateBasemapCredit(fallback=false){
    if(!this.credit)return;
    const provider=this.providers[this.tileProvider];
    this.credit.textContent=fallback
      ? `Mapa base: ${provider.name} no disponible · usando Esri World Topographic Map`
      : `Mapa base: ${provider.name} · © ${this.tileProvider==='euskadi'?'Eusko Jaurlaritza / Gobierno Vasco':'Esri y colaboradores'}`;
  }
  updateBasemapStatus(text,isError){this.status.textContent=text;this.status.classList.toggle('error',!!isError);this.updateBasemapCredit(text.includes('servidor alternativo'))}
  hidePopup(){this.popup.style.display='none';this.popup.replaceChildren()}
  openPopup(name,detail,actions,clientX,clientY){
    this.popup.replaceChildren();const b=document.createElement('b');b.textContent=name;
    const p=document.createElement('p');p.textContent=detail;this.popup.append(b,p);
    for(const [label,callback] of actions){const btn=document.createElement('button');btn.type='button';btn.textContent=label;btn.addEventListener('click',()=>{this.hidePopup();callback()});this.popup.append(btn)}
    const rect=this.container.getBoundingClientRect();
    this.popup.style.left=Math.max(15,Math.min(rect.width-260,clientX-rect.left+10))+'px';
    this.popup.style.top=Math.max(15,Math.min(rect.height-135,clientY-rect.top+10))+'px';
    this.popup.style.display='block';
  }
  displayIsochrones(data){this.isoFeatures=data||{};this.drawIsochrones()}
  displayIsochrone(geometry){this.displayIsochrones({10:geometry})}
  clearIsochrone(){this.isoFeatures={};this.drawIso.replaceChildren()}
  drawIsochrones(){
    this.drawIso.replaceChildren();
    // Larger isochrone first: the 5-minute area must remain visible on top.
    for(const [minutes,color,opacity] of [[10,'#3a8ed0',.30],[5,'#e69b32',.48]]){
      const geometry=this.isoFeatures[minutes];if(!this.isoVisible[minutes]||!geometry)continue;
      // The API normally returns Polygon/MultiPolygon. Keep the renderer
      // defensive for a union that becomes a GeometryCollection and build
      // explicit SVG commands instead of relying on string replacement.
      const polygons=[];
      const collect=g=>{
        if(!g)return;
        if(g.type==='Feature')return collect(g.geometry);
        if(g.type==='Polygon')polygons.push(g.coordinates);
        else if(g.type==='MultiPolygon')g.coordinates.forEach(rings=>polygons.push(rings));
        else if(g.type==='GeometryCollection')(g.geometries||[]).forEach(collect);
      };
      collect(geometry);
      for(const rings of polygons){
        const parts=rings.map(r=>{
          const points=r.filter(p=>Array.isArray(p)&&Number.isFinite(p[0])&&Number.isFinite(p[1]))
            .map(p=>{const [x,y]=this.project(p);return `${x.toFixed(2)},${y.toFixed(2)}`});
          return points.length>=3?`M ${points.join(' L ')} Z`:'';
        }).filter(Boolean);
        if(!parts.length)continue;
        this.element('path',{d:parts.join(' '),fill:color,'fill-rule':'evenodd','fill-opacity':opacity,stroke:color,'stroke-width':2.1,'vector-effect':'non-scaling-stroke','stroke-linejoin':'round','pointer-events':'none','data-iso-minutes':minutes,'aria-label':`${minutes} minutos andando`},this.drawIso);
      }
    }
  }
  focusOn(lon,lat,focusIso=false){
    const [x,y]=this.project([lon,lat]);
    if(focusIso){this.view.w=Math.min(this.view.w,82);this.view.h=this.view.w*this.base.h/this.base.w;}
    this.view.x=x-this.view.w/2;this.view.y=y-this.view.h/2;this.syncView();
  }
  render(data,filtered){
    this.clearIsochrone();this.hidePopup();
    const paths=data.routes||[],stops=data.stops||[];const dense=paths.length>24;
    const activeRoutes=new Set(),activeStops=new Set();
    for(const r of paths){
      if(!r.coordinates?.length)continue;
      const key=JSON.stringify([r.operator,r.id,r.shape_id,r.direction]);activeRoutes.add(key);
      const col={ekialdebus:'#067f72',irunbus:'#cc7734',euskotren:'#6f56a8',errenteria_urbanoa:'#2d7ca4'}[r.operator]||'#067f72';
      let node=this.routeNodes.get(key);
      if(!node){
        const group=this.element('g',{},this.geo),poly=this.element('polyline',{fill:'none',stroke:'#fff','vector-effect':'non-scaling-stroke','pointer-events':'none'},group);
        const line=this.element('polyline',{fill:'none','vector-effect':'non-scaling-stroke',class:'route-path'},group);
        const title=this.element('title',{},line);node={group,poly,line,title,route:r};this.routeNodes.set(key,node);
        line.addEventListener('click',e=>{const route=node.route;e.stopPropagation();this.openPopup(route.name||route.id,'Recorrido según shape GTFS; la cartografía base es independiente del recorrido',[['Filtrar línea',()=>this.handlers.onRoute(route.id||route.name,route.operator||null)]],e.clientX,e.clientY)});
      }
      node.route=r;node.title.textContent=(r.name||r.id)+' · geometría según shape GTFS';
      node.poly.setAttribute('stroke-width',filtered?7:4.4);node.poly.setAttribute('opacity',filtered?.93:.67);
      node.line.setAttribute('stroke',col);node.line.setAttribute('stroke-width',filtered?4.4:(dense?1.5:2.1));node.line.setAttribute('opacity',filtered?.95:(dense?.32:.65));
    }
    for(const [key,node] of this.routeNodes)if(!activeRoutes.has(key)){node.group.remove();this.routeNodes.delete(key);}
    for(const s of stops){
      if(typeof s.lat!=='number'||typeof s.lon!=='number')continue;
      const key=JSON.stringify([s.operator,s.id]);activeStops.add(key);
      const [x,y]=this.project([s.lon,s.lat]);
      // Keep the stop symbol a cartographic point at the focused zoom. The
      // previous 4.8 map-unit radius became a large centroid disk on screen.
      const fill={ekialdebus:'#067f72',irunbus:'#be8148',euskotren:'#6f56a8',errenteria_urbanoa:'#2d7ca4'}[s.operator]||'#067f72';
      let node=this.stopNodes.get(key);
      if(!node){
        const marker=this.element('circle',{r:.8,stroke:'#fff','stroke-width':.35,'vector-effect':'non-scaling-stroke',class:'stop-point'},this.points);
        const title=this.element('title',{},marker);node={marker,title,stop:s};this.stopNodes.set(key,node);
        marker.addEventListener('click',e=>{const stop=node.stop;e.stopPropagation();this.openPopup(stop.name,'Parada GTFS · isócronas sobre red peatonal OSM real',[
          ['Ver horarios',()=>this.handlers.viewStop(stop)],['Isócronas OSM 5 y 10 min',()=>this.handlers.showIsochrone(stop)]],e.clientX,e.clientY)});
      }
      node.stop=s;node.marker.setAttribute('cx',x);node.marker.setAttribute('cy',y);node.marker.setAttribute('fill',fill);node.title.textContent=s.name+' · parada GTFS';
    }
    for(const [key,node] of this.stopNodes)if(!activeStops.has(key)){node.marker.remove();this.stopNodes.delete(key);}
    this.updateRouteDetail(true);
  }
}
window.GeographicReviewMap=GeographicReviewMap;
