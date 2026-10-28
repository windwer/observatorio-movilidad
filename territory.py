"""Pedestrian-network accessibility and residential dasymetric population allocation.

All areas in this module are computed from real *imported* geospatial features.
No radial buffer is used as a replacement for walking time. Dijkstra first
selects the reachable portion of each real network edge. Population access is
tested against that graph distance. The display polygon is a narrow union of
the reached network segments themselves; it is deliberately not a convex or
concave hull, so it cannot draw a straight line across a field, river, block or
other area where the pedestrian network does not exist. The 10-minute display
envelope is explicitly united with the 5-minute envelope so the two cartographic
levels remain nested.
"""
from __future__ import annotations
import hashlib
import heapq
import json
import os
import tempfile
import threading
from collections import Counter, defaultdict, OrderedDict
from dataclasses import dataclass
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, shape, mapping, LineString, Polygon, box
from shapely.ops import transform, unary_union, substring
from shapely.strtree import STRtree

TO_LOCAL = Transformer.from_crs('EPSG:4326','EPSG:25830', always_xy=True).transform
TO_WGS = Transformer.from_crs('EPSG:25830','EPSG:4326', always_xy=True).transform
INITIAL_MUNICIPALITIES = ('Irun','Hondarribia','Errenteria','Pasaia','Lezo','Oiartzun')
MUNICIPALITIES = (
    'Abaltzisketa','Aduna','Aia','Aizarnazabal','Albiztur','Alegia','Alkiza','Altzaga','Altzo','Amezketa',
    'Andoain','Anoeta','Antzuola','Arama','Aretxabaleta','Arrasate/Mondragón','Asteasu','Astigarraga','Ataun',
    'Azkoitia','Azpeitia','Baliarrain','Beasain','Beizama','Belauntza','Berastegi','Bergara','Berrobi',
    'Bidania-Goiatz','Deba','Eibar','Elduain','Elgeta','Elgoibar','Errenteria','Errezil','Eskoriatza',
    'Ezkio-Itsaso','Gabiria','Gaintza','Gaztelu','Getaria','Hernani','Hernialde','Hondarribia','Ibarra',
    'Idiazabal','Ikaztegieta','Irun','Irura','Itsasondo','Larraul','Lasarte-Oria','Lazkao','Leaburu',
    'Legazpi','Legorreta','Leintz Gatzaga','Lezo','Lizartza','Mendaro','Mutiloa','Mutriku','Oiartzun',
    'Olaberria','Ordizia','Orendain','Orexa','Orio','Ormaiztegi','Oñati','Pasaia','Segura',
    'Soraluze-Placencia de las Armas','Tolosa','Urnieta','Urretxu','Usurbil','Villabona','Zaldibia','Zarautz',
    'Zegama','Zerain','Zestoa','Zizurkil','Zumaia','Zumarraga','Donostia / San Sebastián'
)
RESIDENTIAL = {'residential','apartments','house','detached','semidetached_house','terrace','dormitory','bungalow','farm','static_caravan','cabin'}
ALLOW_FOOT = {'footway','pedestrian','path','living_street','residential','steps','service','unclassified','tertiary','secondary','primary','track','cycleway','bridleway'}
GIPUZKOA_LAT_LON_BOUNDS = (42.85,43.55,-2.75,-1.45)


def read_geojson(data:bytes, max_features=1_000_000):
    if len(data)>180_000_000: raise ValueError('GeoJSON supera el máximo de 180 MB')
    try: doc=json.loads(data)
    except (ValueError,UnicodeError) as e: raise ValueError('GeoJSON no válido') from e
    if doc.get('type')!='FeatureCollection' or not isinstance(doc.get('features'),list):
        raise ValueError('Se requiere un GeoJSON FeatureCollection')
    if len(doc['features'])>max_features:raise ValueError('Demasiadas entidades geográficas')
    return doc['features']


def valid_municipality(s):
    text=str(s or '').strip().lower()
    alias={'irún':'Irun','irun':'Irun','fuenterrabía':'Hondarribia','hondarribia':'Hondarribia','rentería':'Errenteria','renteria':'Errenteria','errenteria':'Errenteria','pasajes':'Pasaia','pasaia':'Pasaia','lezo':'Lezo','oyarzun':'Oiartzun','oiartzun':'Oiartzun'}
    if text in alias:return alias[text]
    for name in MUNICIPALITIES:
        if text==name.lower():return name
    return None


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
        # Las capas deben venir en WGS84 y estar realmente en el ámbito de Gipuzkoa.
        lon,lat=g.representative_point().x,g.representative_point().y
        if not (GIPUZKOA_LAT_LON_BOUNDS[0] <= lat <= GIPUZKOA_LAT_LON_BOUNDS[1] and GIPUZKOA_LAT_LON_BOUNDS[2] <= lon <= GIPUZKOA_LAT_LON_BOUNDS[3]):
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
            residents.append({'id':c['id']+'/'+b['id'], 'section_id':c['id'],
                              'municipality':c['municipality'], 'population':c['population']*b['weight']/total,
                              'point':b['point'],'allocation_method':'residential_building'})
    return residents,unallocated


def allocate_population_to_network(census,network,section_ids=None,max_anchors_per_section=240):
    """Put section totals on walk-network anchors, independent of map styling.

    This is a deterministic fallback when a section has no complete residential
    building layer.  It is still an estimate, but changing the visual buffer of
    an isochrone cannot alter its population.
    """
    allowed=set(section_ids) if section_ids is not None else None
    residents=[];unallocated=[]
    for section in census:
        if allowed is not None and section['id'] not in allowed:continue
        polygon=section['geometry'];candidates=[]
        edge_candidates=list(network.tree.query(polygon))
        # A dense urban section can contain tens of thousands of short OSM
        # segments. A deterministic spatial sample is enough for the census
        # proxy and keeps cold preparation bounded.
        cap=max_anchors_per_section*3
        if len(edge_candidates)>cap:
            step=len(edge_candidates)/cap
            edge_candidates=[edge_candidates[min(len(edge_candidates)-1,int(i*step))] for i in range(cap)]
        for raw_idx in edge_candidates:
            idx=int(raw_idx);line=network.geoms[idx]
            if not polygon.intersects(line):continue
            clipped=polygon.intersection(line)
            parts=[]
            if clipped.geom_type=='LineString':parts=[clipped]
            elif clipped.geom_type=='MultiLineString':parts=list(clipped.geoms)
            for part in parts:
                if part.length>.25:
                    candidates.append((idx,part.interpolate(.5,normalized=True),float(part.length)))
        if not candidates:
            unallocated.append({'section':section['id'],'municipality':section['municipality'],
                                'population':section['population'],'reason':'no_walk_network_in_section'})
            continue
        candidates.sort(key=lambda item:item[0])
        if len(candidates)>max_anchors_per_section:
            step=len(candidates)/max_anchors_per_section
            candidates=[candidates[min(len(candidates)-1,int(i*step))] for i in range(max_anchors_per_section)]
        total=sum(weight for _,_,weight in candidates) or len(candidates)
        for number,(edge_idx,point,weight) in enumerate(candidates):
            residents.append({'id':f"{section['id']}/network/{number}",'section_id':section['id'],
                              'municipality':section['municipality'],
                              'population':float(section['population'])*(weight or 1)/total,
                              'point':point,'edge_index':edge_idx,
                              'allocation_method':'census_walk_network_anchor'})
    return residents,unallocated


class WalkNetwork:
    def __init__(self,features):
        self.edges=[];self.graph=defaultdict(list);self.incident=defaultdict(list);self.geoms=[];self.osm_way_ids=set()
        def coord_ident(p,layer='0'):return ('xy',round(p[0],1),round(p[1],1),str(layer or '0'))
        # OSM ways contain many shape vertices that are not intersections.
        # Turning every one into a graph node made the provincial graph exceed
        # one million edges and delayed every process start.  Shared node ids,
        # endpoints and barriers are the only topological split points; the
        # complete intermediate geometry is retained in each LineString.
        node_use=Counter()
        for feat in features:
            props=feat.get('properties') or {}
            ids=props.get('node_ids')
            if isinstance(ids,list):node_use.update(str(value) for value in ids if value is not None)
        for feat in features:
            p=feat.get('properties') or {}
            highway=str(p.get('highway',p.get('type','footway'))).lower()
            foot=str(p.get('foot','')).lower();access=str(p.get('access','')).lower()
            if highway not in ALLOW_FOOT or foot in ('no','private') or access in ('private','no'):
                continue
            if p.get('osm_id'):self.osm_way_ids.add(str(p['osm_id']))
            layer=p.get('layer','0')
            node_ids=p.get('node_ids') if isinstance(p.get('node_ids'),list) else None
            blocked={str(x) for x in (p.get('blocked_node_ids') or [])}
            surface=str(p.get('surface','')).lower()
            factor=1.0
            if highway=='steps':factor=1.55
            elif highway in {'track','bridleway'}:factor=1.25
            elif surface in {'gravel','unpaved','ground','dirt','sand','mud'}:factor=max(factor,1.2)
            one_way=str(p.get('oneway:foot','')).lower() in {'yes','1','true'}
            try:g=shape(feat['geometry'])
            except Exception:continue
            if g.geom_type=='LineString': parts=[g]
            elif g.geom_type=='MultiLineString':parts=list(g.geoms)
            else:continue
            node_cursor=0
            for part in parts:
                local=transform(TO_LOCAL,part)
                coords=list(local.coords)
                part_ids=(node_ids[node_cursor:node_cursor+len(coords)] if node_ids else [])
                important={0,len(coords)-1}
                for position,value in enumerate(part_ids):
                    if value is not None and (node_use[str(value)]>1 or str(value) in blocked):important.add(position)
                ordered=sorted(important)
                for start,end in zip(ordered,ordered[1:]):
                    if end<=start:continue
                    raw_u=str(part_ids[start]) if start<len(part_ids) and part_ids[start] is not None else None
                    raw_v=str(part_ids[end]) if end<len(part_ids) and part_ids[end] is not None else None
                    if raw_u in blocked or raw_v in blocked:continue
                    u=('osm',raw_u) if raw_u else coord_ident(coords[start],layer)
                    v=('osm',raw_v) if raw_v else coord_ident(coords[end],layer)
                    if u==v:continue
                    ls=LineString(coords[start:end+1]);length=ls.length
                    if length<.25:continue
                    idx=len(self.edges)
                    cost=length*factor
                    self.edges.append((u,v,length,cost));self.geoms.append(ls)
                    self.graph[u].append((v,cost,idx))
                    if not one_way:self.graph[v].append((u,cost,idx))
                    self.incident[u].append(idx);self.incident[v].append(idx)
                node_cursor+=len(coords)
        if not self.edges:raise ValueError('No se han encontrado caminos peatonales conectables')
        self.tree=STRtree(self.geoms)

    def isochrone(self,lat,lon,minutes=10,speed_kmh=4.5,display_buffer_m=18,
                  max_snap_m=80,geometry=True):
        if not 0<minutes<=30:raise ValueError('Tiempo fuera de rango')
        point=Point(*TO_LOCAL(lon,lat))
        closest=int(self.tree.nearest(point));geom=self.geoms[closest]
        snap=geom.interpolate(geom.project(point));snap_dist=point.distance(snap)
        if snap_dist>max_snap_m:
            return {'status':'no_walkway_near_stop','snap_m':round(snap_dist,1),'polygon':None,'reached_nodes':0}
        limit=minutes*speed_kmh*1000/60
        u,v,length,cost=self.edges[closest];factor=cost/length;origin_factor=factor
        origin_offset=geom.project(snap)
        d0=snap_dist+origin_offset*factor
        d1=snap_dist+(length-origin_offset)*factor
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
        if not geometry:
            return {'status':'calculated','snap_m':round(snap_dist,1),'reached_nodes':len(distances),
                    '_node_distances':distances,'_limit_m':limit,'_origin_edge':closest,
                    '_origin_offset':origin_offset,'_origin_access_m':snap_dist,
                    '_search_geometry':point.buffer(limit+85)}
        fragments=[]
        # Only segments with at least one endpoint reachable contribute to the polygon.
        # Inspect only edges adjacent to reachable nodes. Iterating the entire
        # Gipuzkoa pedestrian network for every stop is unnecessarily costly.
        reachable_edges={edge_index for node in distances for edge_index in self.incident[node]}
        for edge_index in reachable_edges:
            a,b,length,cost=self.edges[edge_index];factor=cost/length
            ls=self.geoms[edge_index]
            da=distances.get(a,float('inf'));db=distances.get(b,float('inf'))
            reach_a=max(0,min(length,(limit-da)/factor))
            reach_b=max(0,min(length,(limit-db)/factor))
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
            local_budget=budget/origin_factor
            local_fragment=substring(geom,max(0,offset-local_budget),min(geom.length,offset+local_budget))
            if not local_fragment.is_empty:fragments.append(local_fragment)
        if not fragments:return {'status':'unreachable','snap_m':round(snap_dist,1),'polygon':None,'reached_nodes':len(distances)}
        # The graph search is the calculation. Render only reached edge
        # fragments with a small access band. Unlike a convex/concave hull,
        # this cannot bridge two branches through a field, park, river or block
        # where no OSM pedestrian way exists.
        edge_surfaces=[g.buffer(display_buffer_m,cap_style='round',join_style='round',quad_segs=4) for g in fragments if not g.is_empty]
        display=unary_union(edge_surfaces).simplify(1.5,preserve_topology=True) if edge_surfaces else None
        if display is None or display.is_empty:
            return {'status':'unreachable','snap_m':round(snap_dist,1),'polygon':None,'reached_nodes':len(distances)}
        return {'status':'calculated','snap_m':round(snap_dist,1),'polygon':display,
                'display_polygon':display,'reached_nodes':len(distances),
                'reached_network_m':round(sum(g.length for g in fragments),1),
                'analysis_area_m2':round(display.area,1),'display_area_m2':round(display.area,1),
                'travel_limit_m':round(limit,1),
                 'method':'Dijkstra sobre topología peatonal OSM; perfil con penalización de escaleras/superficies y banda sólo visual',
                 'population_geometry_independent':True,
                 '_node_distances':distances,'_limit_m':limit,
                 '_origin_edge':closest,'_origin_offset':origin_offset,'_origin_access_m':snap_dist}

    def walk_distance_to(self,point,distances,origin_edge=None,origin_offset=None,origin_access_m=0,edge_index=None):
        """Shortest graph distance from the origin to a point beside the network."""
        idx=int(edge_index) if edge_index is not None else int(self.tree.nearest(point));edge=self.geoms[idx]
        offset=edge.project(point);snap=edge.interpolate(offset);u,v,length,cost=self.edges[idx];factor=cost/length
        du=distances.get(u,float('inf'))+offset*factor
        dv=distances.get(v,float('inf'))+(length-offset)*factor
        direct=float('inf')
        if origin_edge==idx and origin_offset is not None:
            direct=origin_access_m+abs(offset-origin_offset)*factor
        return point.distance(snap)+min(du,dv,direct)


def calculate_population(iso, residents, network=None, municipalities=None):
    poly=iso.get('polygon')
    if poly is None:return {'population':None,'municipalities':{},'units_reached':0}
    seen=set();by_town=defaultdict(float)
    for r in residents:
        graph_reached=(network is not None and network.walk_distance_to(
            r['point'],iso.get('_node_distances',{}),iso.get('_origin_edge'),
            iso.get('_origin_offset'),iso.get('_origin_access_m',0),r.get('edge_index'))<=iso.get('_limit_m',0))
        if (municipalities is None or r['municipality'] in municipalities) and r['id'] not in seen and graph_reached:
            by_town[r['municipality']]+=r['population'];seen.add(r['id'])
    return {'population':round(sum(by_town.values())), 'municipalities':{k:round(v) for k,v in by_town.items()},'units_reached':len(seen)}


def calculate_population_by_census_area(iso, census, municipalities=None):
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
        if municipalities is not None and section['municipality'] not in municipalities:continue
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
    def __init__(self, directory,cache_entries=64,artifact_path=None):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.census=[];self.buildings=[];self.residents=[];self.unallocated=[];self.network=None
        self.changes={};self.load_errors=[];self._cache_entries=max(8,int(cache_entries))
        self._iso_cache=OrderedDict();self._cache_hits=0;self._cache_misses=0
        self._lock=threading.RLock();self._resident_tree=None;self._resident_points=[];self._load()
        self._artifact_path=artifact_path;self._artifacts=None;self._artifact_hits=0
        if artifact_path:
            from access_cache import AccessCache,fingerprint
            self._artifacts=AccessCache(artifact_path,fingerprint(self.directory))

    def _load(self):
        for layer in ('census','buildings','walkways'):
            f=self.directory/(layer+'.geojson')
            if f.exists():
                try:self._apply(layer,read_geojson(f.read_bytes()))
                except (ValueError,KeyError,TypeError) as exc:self.load_errors.append({'layer':layer,'error':str(exc)})
        if not self.buildings and self._load_population_anchors():
            self._index_residents()
        else:self._assign()

    def _load_population_anchors(self):
        path=self.directory/'population_anchors.json'
        if not path.is_file() or not self.census or not self.network:return False
        try:
            doc=json.loads(path.read_text(encoding='utf-8'))
            if doc.get('method_version')!='walk-network-anchors-v2':return False
            if int(doc.get('walk_segments',-1))!=len(self.network.edges):return False
            if round(sum(row['population'] for row in self.census))!=int(doc.get('census_population',-1)):return False
            rows=[]
            for row in doc.get('anchors',[]):
                ident,town,population,x,y,edge_index=row
                edge_index=int(edge_index)
                if not 0<=edge_index<len(self.network.edges):return False
                rows.append({'id':str(ident),'municipality':str(town),'population':float(population),
                             'point':Point(float(x),float(y)),'edge_index':edge_index,
                             'allocation_method':'census_walk_network_anchor'})
            if not rows:return False
            self.residents=rows;self.unallocated=list(doc.get('unallocated',[]));return True
        except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
            self.load_errors.append({'layer':'population_anchors','error':str(exc)});return False

    def save_population_anchors(self,path=None):
        if self.buildings:raise ValueError('El artefacto de anclajes sólo corresponde al fallback sin edificios')
        if not self.residents:raise ValueError('No hay anclajes calculados')
        destination=Path(path) if path else self.directory/'population_anchors.json'
        doc={'method_version':'walk-network-anchors-v2','walk_segments':len(self.network.edges),
             'census_population':round(sum(row['population'] for row in self.census)),
             'anchors':[[r['id'],r['municipality'],round(r['population'],8),round(r['point'].x,2),round(r['point'].y,2),r['edge_index']] for r in self.residents],
             'unallocated':self.unallocated}
        raw=json.dumps(doc,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        with tempfile.NamedTemporaryFile(dir=destination.parent,prefix=destination.name+'.',suffix='.pending',delete=False) as handle:
            pending=Path(handle.name);handle.write(raw);handle.flush();os.fsync(handle.fileno())
        os.replace(pending,destination)
        return {'path':str(destination),'anchors':len(self.residents),'bytes':len(raw),'unallocated_sections':len(self.unallocated)}

    def _apply(self,layer,features):
        if layer=='census':self.census=normalise_census(features)
        elif layer=='buildings':self.buildings=normalise_buildings(features)
        elif layer=='walkways':self.network=WalkNetwork(features);self._iso_cache.clear()
        else:raise ValueError('Capa no permitida')

    def _assign(self):
        self.residents=[];self.unallocated=[]
        if self.census and self.buildings:
            building_residents,missing=assign_population(self.census,self.buildings)
            self.residents.extend(building_residents)
            if self.network and missing:
                missing_ids={row['section'] for row in missing}
                anchors,still_missing=allocate_population_to_network(self.census,self.network,missing_ids)
                self.residents.extend(anchors);self.unallocated=still_missing
            else:self.unallocated=missing
        elif self.census and self.network:
            self.residents,self.unallocated=allocate_population_to_network(self.census,self.network)
        self._index_residents()
        self._iso_cache.clear()

    def _index_residents(self):
        self._resident_points=[row['point'] for row in self.residents]
        self._resident_tree=STRtree(self._resident_points) if self._resident_points else None

    def ingest(self,layer,raw):
        if layer not in ('census','buildings','walkways'):raise ValueError('Capa no válida')
        feats=read_geojson(raw)
        # Validate in isolation before publishing a complete immutable file.
        if layer=='census':normalise_census(feats)
        elif layer=='buildings':normalise_buildings(feats)
        else:WalkNetwork(feats)
        dest=self.directory/(layer+'.geojson')
        with tempfile.NamedTemporaryFile(dir=self.directory,prefix=layer+'.',suffix='.pending',delete=False) as handle:
            pending=Path(handle.name);handle.write(raw);handle.flush();os.fsync(handle.fileno())
        try:
            os.replace(pending,dest)
            with self._lock:
                self._apply(layer,feats);self._assign()
                if self._artifact_path:
                    from access_cache import AccessCache,fingerprint
                    self._artifacts=AccessCache(self._artifact_path,fingerprint(self.directory))
        finally:
            if pending.exists():pending.unlink()
        return self.status()

    def _isochrone(self,lat,lon,minutes):
        key=(round(float(lat),6),round(float(lon),6),int(minutes))
        with self._lock:
            cached=self._iso_cache.get(key)
            if cached is not None:
                self._cache_hits+=1;self._iso_cache.move_to_end(key);return cached
        result=self.network.isochrone(lat,lon,minutes=minutes)
        with self._lock:
            self._cache_misses+=1;self._iso_cache[key]=result;self._iso_cache.move_to_end(key)
            while len(self._iso_cache)>self._cache_entries:self._iso_cache.popitem(last=False)
        return result

    def cache_status(self):
        with self._lock:
            return {'loaded':True,'entries':len(self._iso_cache),'max_entries':self._cache_entries,
                    'hits':self._cache_hits,'misses':self._cache_misses,'artifact_hits':self._artifact_hits}

    def _reachable_indices(self,iso):
        if self._resident_tree is None or iso.get('status')!='calculated':return set()
        search=iso.get('_search_geometry')
        if search is None:
            if iso.get('polygon') is None:return set()
            search=iso['polygon'].buffer(85)
        reached=set()
        for raw_idx in self._resident_tree.query(search):
            idx=int(raw_idx);resident=self.residents[idx]
            distance=self.network.walk_distance_to(resident['point'],iso.get('_node_distances',{}),
                iso.get('_origin_edge'),iso.get('_origin_offset'),iso.get('_origin_access_m',0),resident.get('edge_index'))
            if distance<=iso.get('_limit_m',0):reached.add(idx)
        return reached

    def status(self):
        return {'census_sections':len(self.census),'residential_buildings':len(self.buildings),
          'resident_units':len(self.residents),'unallocated_sections':len(self.unallocated),
          'unallocated_population':round(sum(c['population'] for c in self.unallocated)),
          'walk_segments':len(self.network.edges) if self.network else 0,
          'walk_source':'OpenStreetMap contributors' if self.network and self.network.osm_way_ids else 'uploaded/unknown',
          'walk_osm_ways':len(self.network.osm_way_ids) if self.network else 0,
          'municipalities':sorted({c['municipality'] for c in self.census}),
          'census_population':round(sum(c['population'] for c in self.census)),
          'ready':bool(self.census and self.network and self.residents and not self.load_errors),
          'area_interpolation_ready':False,
          'population_access_ready':bool(self.census and self.network and self.residents),
          'population_method':('hybrid_residential_building_and_network_anchor' if self.buildings and self.residents else
             'census_walk_network_anchor' if self.residents else 'unavailable'),
          'method':'Residential buildings where complete; otherwise census totals allocated to deterministic walk-network anchors. Display-buffer independent.',
          'walk_method':'Dijkstra on walkable OSM graph; population by graph distance; union of reached network segments',
          'method_version':'walk-network-anchors-v2','load_errors':list(self.load_errors),
          'cache':self.cache_status(),
          'geography_scope':'Gipuzkoa provincial census and pedestrian network',
          'attribution':'Geometry: INE Secciones_2025; counts: Eustat 2025; walkways: OpenStreetMap contributors; verify source licences'}

    def stops_near_study_area(self,stops,max_distance_m=900):
        """Filter out distant route stops outside the census footprint + walking reach.

        This only reduces computation. Population itself is allocated to all
        loaded Gipuzkoa census sections and never approximated using a bounding rectangle.
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
        if not self.network or not self.residents:
            return {'status':'incomplete_geography','population':None,'stops':len(stops)}
        if len(stops)>2500:raise ValueError('Demasiadas paradas en una consulta')
        seen=set();snapped=0;outside=0
        for stop in stops:
            point=(round(float(stop['lat']),6),round(float(stop['lon']),6))
            access=self.reachable(*point,minutes)
            if access['status']!='calculated':
                outside+=1;continue
            snapped+=1;seen.update(access['indices'])
        by_municipality=defaultdict(float);methods=set()
        for i in seen:
            r=self.residents[i];by_municipality[r['municipality']]+=r['population'];methods.add(r.get('allocation_method'))
        return {'status':'estimated','stops':len(stops),'stops_connected':snapped,'stops_unconnected':outside,
                'population':round(sum(by_municipality.values())),
                'municipalities':{k:round(v) for k,v in by_municipality.items()},
                'units_reached':len(seen),
                'population_method':'+'.join(sorted(x for x in methods if x)) or self.status()['population_method'],
                'unallocated_population':round(sum(c['population'] for c in self.unallocated)),
                'method':f'unique population units on walk network + {minutes}-min graph access; display independent',
                'method_version':'walk-network-anchors-v2',
                'certified':False}

    def reachable(self,lat,lon,minutes=10):
        key=f'reach:{float(lat):.6f}:{float(lon):.6f}:{int(minutes)}'
        cached=self._artifacts.get(key) if self._artifacts else None
        if cached is not None:self._artifact_hits+=1;return cached
        iso=self.network.isochrone(lat,lon,minutes=minutes,geometry=False)
        result={'status':iso['status'],'indices':sorted(self._reachable_indices(iso))}
        if self._artifacts:self._artifacts.put(key,result)
        return result

    def stop(self,lat,lon,geometry=True,minutes=10):
        if not self.network:return {'status':'missing_pedestrian_network','population':None}
        if not 0 < minutes <= 30:raise ValueError('Minutos fuera de rango')
        artifact_key=f'stop:{float(lat):.6f}:{float(lon):.6f}:{int(minutes)}'
        cached=self._artifacts.get(artifact_key) if self._artifacts else None
        if cached is not None:
            self._artifact_hits+=1
            return cached if geometry else {**cached,'geometry':None}
        key=(round(float(lat),6),round(float(lon),6),int(minutes))
        result=self._isochrone(lat,lon,minutes)
        # Independent hull simplification can make a 5-minute envelope poke
        # outside the 10-minute envelope even though the underlying Dijkstra
        # reachable set is necessarily nested. Union the lower threshold into
        # the 10-minute display/analysis polygon so the visual levels cannot
        # contradict the travel-time semantics.
        if minutes==10 and result.get('polygon') is not None:
            inner_key=(round(float(lat),6),round(float(lon),6),5)
            inner=self._isochrone(lat,lon,5)
            if inner.get('polygon') is not None:
                nested=unary_union([result['polygon'],inner['polygon']])
                if not nested.is_empty:
                    result=dict(result)
                    result['polygon']=nested
                    result['display_polygon']=nested
                    result['analysis_area_m2']=round(nested.area,1)
                    result['display_area_m2']=round(nested.area,1)
                    result['geometry_nesting']='10-minute envelope includes the 5-minute envelope'
                    with self._lock:self._iso_cache[key]=result
        if self.residents:
            indices=self._reachable_indices(result)
            selected=[self.residents[i] for i in indices]
            methods=sorted({row.get('allocation_method') for row in selected if row.get('allocation_method')})
            pop={**calculate_population(result,selected,self.network),
                 'population_method':'+'.join(methods) or self.status()['population_method'],
                 'unallocated_population':round(sum(c['population'] for c in self.unallocated))}
        else:
            pop={'population':None,'units_reached':0,'municipalities':{},'population_method':'unavailable'}
        display=result.get('display_polygon',result.get('polygon'))
        geom=mapping(transform(TO_WGS,display)) if geometry and display is not None else None
        payload={**{k:v for k,v in result.items() if not k.startswith('_') and k not in ('polygon','display_polygon')},**pop,
                'geometry':geom,'minutes':minutes,
                'method_version':'walk-network-anchors-v2','population_certified':False}
        if self._artifacts and geometry:self._artifacts.put(artifact_key,payload)
        return payload
