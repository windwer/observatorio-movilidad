"""Pedestrian-network accessibility and residential dasymetric population allocation.

All areas in this module are computed from real *imported* geospatial features.
No radial buffer is used as a replacement for walking time. Dijkstra first
selects the reachable portion of each real network edge. Population access is
tested against that graph distance. A concave envelope of reached graph nodes,
with a narrow 25 m edge buffer, is generated only to render a legible polygon.
"""
from __future__ import annotations
import hashlib
import heapq
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from pyproj import Transformer
from shapely import concave_hull
from shapely.geometry import Point, MultiPoint, shape, mapping, LineString, Polygon, box
from shapely.ops import transform, unary_union, substring
from shapely.strtree import STRtree

TO_LOCAL = Transformer.from_crs('EPSG:4326','EPSG:25830', always_xy=True).transform
TO_WGS = Transformer.from_crs('EPSG:25830','EPSG:4326', always_xy=True).transform
MUNICIPALITIES = ('Irun','Hondarribia','Errenteria','Pasaia','Lezo','Oiartzun')
RESIDENTIAL = {'residential','apartments','house','detached','semidetached_house','terrace','dormitory','bungalow','farm','static_caravan','cabin'}
ALLOW_FOOT = {'footway','pedestrian','path','living_street','residential','steps','service','unclassified','tertiary','secondary','primary','track','cycleway','bridleway'}


def read_geojson(data:bytes, max_features=350_000):
    if len(data)>55_000_000: raise ValueError('GeoJSON supera el máximo de 55 MB')
    try: doc=json.loads(data)
    except (ValueError,UnicodeError) as e: raise ValueError('GeoJSON no válido') from e
    if doc.get('type')!='FeatureCollection' or not isinstance(doc.get('features'),list):
        raise ValueError('Se requiere un GeoJSON FeatureCollection')
    if len(doc['features'])>max_features:raise ValueError('Demasiadas entidades geográficas')
    return doc['features']


def valid_municipality(s):
    text=str(s or '').strip().lower()
    alias={'irún':'Irun','irun':'Irun','fuenterrabía':'Hondarribia','hondarribia':'Hondarribia','rentería':'Errenteria','renteria':'Errenteria','errenteria':'Errenteria','pasajes':'Pasaia','pasaia':'Pasaia','lezo':'Lezo','oyarzun':'Oiartzun','oiartzun':'Oiartzun'}
    return alias.get(text)


def normalise_census(features):
    out=[]
    for i,f in enumerate(features):
        p=f.get('properties') or {}
        town=valid_municipality(p.get('municipality',p.get('municipio',p.get('udalerria',p.get('city')))))
        if not town:continue
        num=p.get('population',p.get('poblacion',p.get('habitantes')))
        try:
            if isinstance(num,str):
                token=num.strip()
                if ',' in token:token=token.replace('.','').replace(',','.')
                elif token.count('.')==1 and len(token.rsplit('.',1)[1])==3:token=token.replace('.','')
                people=float(token)
            else:people=float(num)
        except (ValueError,TypeError):continue
        if people<0:continue
        g=shape(f['geometry'])
        if not g.is_valid:g=g.buffer(0)
        if g.is_empty or g.geom_type not in ('Polygon','MultiPolygon'):continue
        # Las capas deben venir en WGS84 y estar realmente en el ámbito de Gipuzkoa oriental.
        lon,lat=g.representative_point().x,g.representative_point().y
        if not (43.16 <= lat <= 43.49 and -2.18 <= lon <= -1.55):
            raise ValueError('Sección censal fuera del ámbito territorial o CRS distinto de EPSG:4326')
        ident=str(p.get('section_id',p.get('seccion',p.get('id',i))))
        out.append({'id':town+':'+ident, 'municipality':town,'population':people,'geometry':transform(TO_LOCAL,g)})
    if not out:raise ValueError('Ninguna sección con municipio, geometría y población reconocidos. Revisa los campos.')
    ids=[x['id'] for x in out]
    if len(ids)!=len(set(ids)):
        raise ValueError('Secciones censales duplicadas; se rechaza la capa para evitar sumar población dos veces')
    return out


def normalise_buildings(features):
    out=[]
    for i,f in enumerate(features):
        p=f.get('properties') or {}
        use=str(p.get('building',p.get('uso',p.get('residential','')))).strip().lower()
        if use not in RESIDENTIAL and str(p.get('residential','')).lower() not in ('yes','true'):
            continue
        g=shape(f['geometry'])
        if not g.is_valid:g=g.buffer(0)
        if g.is_empty or g.geom_type not in ('Polygon','MultiPolygon'):continue
        local=transform(TO_LOCAL,g)
        floors=p.get('building:levels',p.get('floors',p.get('plantas',1)))
        try:floors=max(1,min(40,float(floors)))
        except (ValueError,TypeError):floors=1
        weight=max(.1,local.area*floors)
        out.append({'id':str(p.get('id',f.get('id',i))), 'point':local.representative_point(), 'weight':weight})
    if not out:raise ValueError('No hay edificios etiquetados como residenciales; no se estimará población ficticia.')
    return out


def assign_population(census,buildings):
    """Allocate each census population only to residential buildings within its section."""
    polys=[c['geometry'] for c in census]
    tree=STRtree(polys)
    by_census=defaultdict(list)
    for b in buildings:
        for idx in tree.query(b['point']):
            if polys[int(idx)].covers(b['point']):
                by_census[int(idx)].append(b);break
    residents=[];unallocated=[]
    for i,c in enumerate(census):
        bs=by_census.get(i,[])
        if not bs:
            unallocated.append({'section':c['id'],'municipality':c['municipality'],'population':c['population']})
            continue
        total=sum(b['weight'] for b in bs)
        for b in bs:
            residents.append({'id':c['id']+'/'+b['id'], 'municipality':c['municipality'], 'population':c['population']*b['weight']/total,'point':b['point']})
    return residents,unallocated


class WalkNetwork:
    def __init__(self,features):
        self.edges=[];self.graph=defaultdict(list);self.geoms=[];self.osm_way_ids=set()
        def ident(p):return (round(p[0],1),round(p[1],1))
        for feat in features:
            p=feat.get('properties') or {}
            highway=str(p.get('highway',p.get('type','footway'))).lower()
            foot=str(p.get('foot','')).lower();access=str(p.get('access','')).lower()
            if highway not in ALLOW_FOOT or foot in ('no','private') or access in ('private','no'):
                continue
            if p.get('osm_id'):self.osm_way_ids.add(str(p['osm_id']))
            try:g=shape(feat['geometry'])
            except Exception:continue
            if g.geom_type=='LineString': parts=[g]
            elif g.geom_type=='MultiLineString':parts=list(g.geoms)
            else:continue
            for part in parts:
                local=transform(TO_LOCAL,part)
                for a,b in zip(list(local.coords),list(local.coords)[1:]):
                    u,v=ident(a),ident(b)
                    if u==v:continue
                    ls=LineString([u,v]);length=ls.length
                    if length<.25:continue
                    idx=len(self.edges)
                    self.edges.append((u,v,length));self.geoms.append(ls)
                    self.graph[u].append((v,length,idx));self.graph[v].append((u,length,idx))
        if not self.edges:raise ValueError('No se han encontrado caminos peatonales conectables')
        self.tree=STRtree(self.geoms)

    def isochrone(self,lat,lon,minutes=10,speed_kmh=4.5,access_buffer_m=25,
                  max_snap_m=100):
        if not 0<minutes<=30:raise ValueError('Tiempo fuera de rango')
        point=Point(*TO_LOCAL(lon,lat))
        closest=int(self.tree.nearest(point));geom=self.geoms[closest]
        snap=geom.interpolate(geom.project(point));snap_dist=point.distance(snap)
        if snap_dist>max_snap_m:
            return {'status':'no_walkway_near_stop','snap_m':round(snap_dist,1),'polygon':None,'reached_nodes':0}
        limit=minutes*speed_kmh*1000/60
        u,v,length=self.edges[closest]
        d0=snap_dist+snap.distance(Point(u))
        d1=snap_dist+snap.distance(Point(v))
        distances={};queue=[]
        for node,initial in ((u,d0),(v,d1)):
            if initial<=limit:
                distances[node]=initial;heapq.heappush(queue,(initial,node))
        while queue:
            d,node=heapq.heappop(queue)
            if d>distances.get(node,float('inf')):continue
            for dest,step,_edge_index in self.graph[node]:
                nxt=d+step
                if nxt<distances.get(dest,float('inf')) and nxt<=limit:
                    distances[dest]=nxt;heapq.heappush(queue,(nxt,dest))
        fragments=[]
        # Only segments with at least one endpoint reachable contribute to the polygon.
        # Inspect only edges adjacent to reachable nodes. Iterating the entire
        # Gipuzkoa pedestrian network for every stop is unnecessarily costly.
        reachable_edges={edge_index for node in distances for _,_,edge_index in self.graph[node]}
        for edge_index in reachable_edges:
            a,b,length=self.edges[edge_index]
            ls=self.geoms[edge_index]
            da=distances.get(a,float('inf'));db=distances.get(b,float('inf'))
            reach_a=max(0,min(length,limit-da))
            reach_b=max(0,min(length,limit-db))
            if reach_a<=0 and reach_b<=0:continue
            if reach_a+reach_b>=length-.01: fragments.append(ls)
            else:
                if reach_a>0:fragments.append(substring(ls,0,reach_a))
                if reach_b>0:fragments.append(substring(ls,length-reach_b,length))
        # A stop may snap to the middle of a long OSM edge with both endpoints
        # farther than 10 minutes. The segment around that snap point is still
        # walkable, even though the Dijkstra queue has no reachable endpoints.
        budget=max(0,limit-snap_dist)
        if budget>0:
            offset=geom.project(snap)
            local_fragment=substring(geom,max(0,offset-budget),min(geom.length,offset+budget))
            if not local_fragment.is_empty:fragments.append(local_fragment)
        if not fragments:return {'status':'unreachable','snap_m':round(snap_dist,1),'polygon':None,'reached_nodes':len(distances)}
        # The network search is the calculation.  The polygon is a concave
        # cartographic envelope of the reached graph nodes (plus the exact
        # frontier endpoints), not a radial time buffer around the stop.
        boundary=[]
        for g in fragments:
            if g.is_empty:continue
            boundary.extend((g.coords[0],g.coords[-1]))
        cloud=MultiPoint(list(distances)+boundary+[snap.coords[0]])
        display=concave_hull(cloud,ratio=.28,allow_holes=False) if len(cloud.geoms)>=3 else cloud.convex_hull
        display=display.buffer(access_buffer_m,cap_style='round',join_style='round').simplify(2.0,preserve_topology=True)
        return {'status':'calculated','snap_m':round(snap_dist,1),'polygon':display,
                'display_polygon':display,'reached_nodes':len(distances),
                'reached_network_m':round(sum(g.length for g in fragments),1),
                'analysis_area_m2':round(display.area,1),'display_area_m2':round(display.area,1),
                'travel_limit_m':round(limit,1),
                'method':'Dijkstra sobre red peatonal OSM; envolvente cóncava de nodos alcanzados',
                '_node_distances':distances,'_limit_m':limit}

    def walk_distance_to(self,point,distances):
        """Shortest graph distance from the origin to a point beside the network."""
        idx=int(self.tree.nearest(point));edge=self.geoms[idx]
        snap=edge.interpolate(edge.project(point));u,v,length=self.edges[idx]
        du=distances.get(u,float('inf'))+snap.distance(Point(u))
        dv=distances.get(v,float('inf'))+snap.distance(Point(v))
        return point.distance(snap)+min(du,dv)


def calculate_population(iso, residents, network=None, municipalities=MUNICIPALITIES):
    poly=iso.get('polygon')
    if poly is None:return {'population':None,'municipalities':{},'units_reached':0}
    seen=set();by_town=defaultdict(float)
    for r in residents:
        graph_reached=(network is not None and network.walk_distance_to(r['point'],iso.get('_node_distances',{}))<=iso.get('_limit_m',0))
        if r['municipality'] in municipalities and r['id'] not in seen and graph_reached:
            by_town[r['municipality']]+=r['population'];seen.add(r['id'])
    return {'population':round(sum(by_town.values())), 'municipalities':{k:round(v) for k,v in by_town.items()},'units_reached':len(seen)}


def calculate_population_by_census_area(iso, census, municipalities=MUNICIPALITIES):
    """Estimate population by areal interpolation when buildings are absent.

    The official Eustat count belongs to a census section, not to a point.  If
    residential building footprints are unavailable, intersecting the
    reachable polygon with official section polygons is the least-assumptive
    fallback: each section contributes its population in proportion to the
    reachable area.  It is explicitly an estimate and is never certified as
    observed demand.
    """
    poly=iso.get('polygon')
    if poly is None or not census:
        return {'population':None,'municipalities':{},'sections_reached':0,
                'population_method':'unavailable'}
    by_town=defaultdict(float);sections=0
    for section in census:
        if section['municipality'] not in municipalities:continue
        area=float(section['geometry'].area)
        if area<=0:continue
        intersection=poly.intersection(section['geometry'])
        if intersection.is_empty:continue
        share=min(1.0,max(0.0,float(intersection.area)/area))
        if share<=0:continue
        by_town[section['municipality']]+=float(section['population'])*share
        sections+=1
    return {'population':round(sum(by_town.values())),
            'municipalities':{k:round(v) for k,v in by_town.items()},
            'sections_reached':sections,
            'population_method':'census_section_area_interpolation'}


class TerritoryStore:
    """In-memory analysed layers, backed by original GeoJSON files for local persistence."""
    def __init__(self, directory):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.census=[];self.buildings=[];self.residents=[];self.unallocated=[];self.network=None
        self.changes={};self._iso_cache={};self._load()

    def _load(self):
        for layer in ('census','buildings','walkways'):
            f=self.directory/(layer+'.geojson')
            if f.exists():
                try:self._apply(layer,read_geojson(f.read_bytes()))
                except (ValueError,KeyError,TypeError):pass
        self._assign()

    def _apply(self,layer,features):
        if layer=='census':self.census=normalise_census(features)
        elif layer=='buildings':self.buildings=normalise_buildings(features)
        elif layer=='walkways':self.network=WalkNetwork(features);self._iso_cache={}
        else:raise ValueError('Capa no permitida')

    def _assign(self):
        if self.census and self.buildings:
            self.residents,self.unallocated=assign_population(self.census,self.buildings)
        else:self.residents=[];self.unallocated=[]

    def ingest(self,layer,raw):
        if layer not in ('census','buildings','walkways'):raise ValueError('Capa no válida')
        feats=read_geojson(raw)
        self._apply(layer,feats)
        self._assign()
        dest=self.directory/(layer+'.geojson');dest.write_bytes(raw)
        return self.status()

    def status(self):
        return {'census_sections':len(self.census),'residential_buildings':len(self.buildings),
          'resident_units':len(self.residents),'unallocated_sections':len(self.unallocated),
          'unallocated_population':round(sum(c['population'] for c in self.unallocated)),
          'walk_segments':len(self.network.edges) if self.network else 0,
          'walk_source':'OpenStreetMap contributors' if self.network and self.network.osm_way_ids else 'uploaded/unknown',
          'walk_osm_ways':len(self.network.osm_way_ids) if self.network else 0,
          'municipalities':sorted({c['municipality'] for c in self.census}),
          'census_population':round(sum(c['population'] for c in self.census)),
          'ready':bool(self.census and self.buildings and self.network and self.residents),
          'area_interpolation_ready':bool(self.census and self.network),
          'population_method':'residential_building_allocation' if self.residents else ('census_section_area_interpolation' if self.census and self.network else 'unavailable'),
          'method':'Residential building area × floors weighted within census sections; section-area interpolation fallback when buildings are absent',
          'walk_method':'Dijkstra on walkable OSM graph; population by graph distance; concave reached-node display envelope',
          'attribution':'Geometry: GeoEuskadi Secciones; counts: Eustat 2025; verify source licences'}

    def stops_near_study_area(self,stops,max_distance_m=900):
        """Filter out distant route stops outside the census footprint + walking reach.

        This only reduces computation. Population itself is always allocated to the
        six municipalities and never approximated using a bounding rectangle.
        """
        if not self.census:return stops
        from shapely.geometry import Point
        region=unary_union([c['geometry'] for c in self.census])
        result=[]
        for stop in stops:
            try:point=Point(*TO_LOCAL(float(stop['lon']),float(stop['lat'])))
            except (KeyError,ValueError,TypeError):continue
            if point.distance(region)<=max_distance_m:result.append(stop)
        return result

    def network_coverage(self,stops,minutes=10):
        """Population unique across all active stops; never sum stop populations."""
        if minutes not in (5,10):raise ValueError('Minutos fuera de rango')
        if not self.network or not (self.residents or self.census):
            return {'status':'incomplete_geography','population':None,'stops':len(stops)}
        if len(stops)>2500:raise ValueError('Demasiadas paradas en una consulta')
        seen=set();snapped=0;outside=0;statuses={}
        polygons=[]
        for stop in stops:
            point=(round(float(stop['lat']),6),round(float(stop['lon']),6))
            cache_key=(*point,minutes)
            if cache_key not in self._iso_cache:
                self._iso_cache[cache_key]=self.network.isochrone(*point,minutes=minutes)
            iso=self._iso_cache[cache_key]
            if iso['polygon'] is None:
                outside+=1;continue
            snapped+=1;poly=iso['polygon'];polygons.append(poly)
            distances=iso.get('_node_distances',{})
            limit=iso.get('_limit_m',0)
            for i,resident in enumerate(self.residents):
                if i in seen or resident['municipality'] not in MUNICIPALITIES:continue
                if self.network.walk_distance_to(resident['point'],distances)<=limit:
                    seen.add(i)
        if self.residents:
            by_municipality=defaultdict(float)
            for i in seen:
                r=self.residents[i];by_municipality[r['municipality']]+=r['population']
            return {'status':'estimated','stops':len(stops),'stops_connected':snapped,'stops_unconnected':outside,
                    'population':round(sum(by_municipality.values())),
                    'municipalities':{k:round(v) for k,v in by_municipality.items()},
                    'unallocated_population':round(sum(c['population'] for c in self.unallocated)),
                    'population_method':'residential_building_allocation',
                    'method':f'unique residential-building census allocation + {minutes}-min network access',
                    'certified':False}
        union=unary_union(polygons) if polygons else None
        interpolated=calculate_population_by_census_area({'polygon':union},self.census)
        return {'status':'estimated','stops':len(stops),'stops_connected':snapped,'stops_unconnected':outside,
                **interpolated,
                'unallocated_population':0,
                'method':f'unique section-area interpolation + {minutes}-min network access',
                'certified':False}

    def stop(self,lat,lon,geometry=True,minutes=10):
        if not self.network:return {'status':'missing_pedestrian_network','population':None}
        if not 0 < minutes <= 30:raise ValueError('Minutos fuera de rango')
        key=(round(float(lat),6),round(float(lon),6),int(minutes))
        if key not in self._iso_cache:self._iso_cache[key]=self.network.isochrone(lat,lon,minutes=minutes)
        result=self._iso_cache[key]
        if self.residents:
            pop={**calculate_population(result,self.residents,self.network),'population_method':'residential'}
        elif self.census:
            pop=calculate_population_by_census_area(result,self.census)
        else:
            pop={'population':None,'units_reached':0,'municipalities':{},'population_method':'unavailable'}
        display=result.get('display_polygon',result.get('polygon'))
        geom=mapping(transform(TO_WGS,display)) if geometry and display is not None else None
        return {**{k:v for k,v in result.items() if k not in ('polygon','display_polygon','_node_distances','_limit_m')},**pop,
                'geometry':geom,'minutes':minutes,
                'population_certified':False}
