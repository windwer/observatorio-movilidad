"""Provisional physical stop change detection between two GTFS service dates.

Matching is spatial and conservative: no inference that a service has been cut
merely because route codes changed. A municipality geometry can restrict scope.
"""
from __future__ import annotations
from datetime import date
import math
from collections import Counter
from pyproj import Transformer
import engine

METRIC=Transformer.from_crs('EPSG:4326','EPSG:25830',always_xy=True)


def compare_stops(conn,operator,old_day='2025-10-15',new_day='2026-10-15',max_match_metres=65,
                  allowed_area=None):
    if operator not in engine.OPERATORS:raise ValueError('Operador no válido')
    d0=date.fromisoformat(engine.clean_date(old_day));d1=date.fromisoformat(engine.clean_date(new_day))
    if not (date(2025,1,1)<=d0<d1<=engine.CUTOFF):
        raise ValueError('Comparación solo entre fechas históricas y en orden temporal')
    left=engine.map_data(conn,operator,d0.isoformat())
    right=engine.map_data(conn,operator,d1.isoformat())
    if left['quality']=='missing' or right['quality']=='missing':
        return {'comparable':False,'reason':'No hay feed válido para una o ambas fechas',
                'old_date':d0.isoformat(),'new_date':d1.isoformat(),
                'operator':operator,'changes':None,'certified':False}
    if not 10<=max_match_metres<=200:raise ValueError('Umbral espacial fuera de rango')
    def scoped(data):
        rows=[]
        for s in data['stops']:
            x,y=METRIC.transform(s['lon'],s['lat'])
            if allowed_area is not None and not allowed_area.covers(__import__('shapely').geometry.Point(x,y)):
                continue
            rows.append({**s,'x':x,'y':y})
        return rows
    a=scoped(left);b=scoped(right)
    choices=[]
    for i,s in enumerate(a):
        for j,t in enumerate(b):
            distance=math.hypot(t['x']-s['x'],t['y']-s['y'])
            if distance<=max_match_metres:
                # Matching is positional; ID and name similarity are supporting evidence only.
                identity=(s['id']==t['id'])
                choices.append((distance-(.1 if identity else 0),i,j,distance))
    choices.sort()
    left_matched=set();right_matched=set();pairs=[]
    for _,i,j,dist in choices:
        if i in left_matched or j in right_matched:continue
        left_matched.add(i);right_matched.add(j)
        pairs.append((i,j,dist))
    added=[b[j] for j in range(len(b)) if j not in right_matched]
    removed=[a[i] for i in range(len(a)) if i not in left_matched]
    moved=[{'before':a[i]['id'],'after':b[j]['id'],'distance_metres':round(dist,1),
       'before_name':a[i]['name'],'after_name':b[j]['name']} for i,j,dist in pairs if dist>10]
    renamed=[{'before':a[i]['name'],'after':b[j]['name'],'distance_metres':round(dist,1)}
      for i,j,dist in pairs if a[i]['name']!=b[j]['name']]
    return {'comparable':True,'certified':False,'operator':operator,
      'old_date':d0.isoformat(),'new_date':d1.isoformat(),
      'old_source':{'feed_id':left.get('feed_id'),'quality':left['quality']},
      'new_source':{'feed_id':right.get('feed_id'),'quality':right['quality']},
      'analysis_scope':'census_area' if allowed_area is not None else 'all_feed_stops',
      'match_method':f'Nearest mutually available unique stops within {max_match_metres} metres; provisional',
      'counts':{'old':len(a),'new':len(b),'matched':len(pairs),'added':len(added),'removed':len(removed),'moved_over_10m':len(moved)},
      'added':[{'id':s['id'],'name':s['name'],'lat':s['lat'],'lon':s['lon']} for s in added],
      'removed':[{'id':s['id'],'name':s['name'],'lat':s['lat'],'lon':s['lon']} for s in removed],
      'moved':moved,'renamed':renamed,
      'warning':'Una parada no emparejada puede indicar un cambio de código, alcance o geometría; requiere validación humana. No mide servicio prestado.'}
