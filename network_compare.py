"""Conservative route/corridor comparison independent of E/OR/BI route codes.

This compares two *specified, equally-classified weekdays* in archived GTFS.
It can suggest candidates, not certify route equivalence or service actually run.
"""
from collections import defaultdict
from datetime import date
from math import hypot
import engine
from pyproj import Transformer

PROJECT = Transformer.from_crs('EPSG:4326','EPSG:25830',always_xy=True)

def _routes(conn,operator,day):
    feed, quality=engine.pick_version(conn,operator,day)
    if not feed:return None,quality
    services=engine.active_services(conn,feed['id'],day)
    if not services:return {},quality
    marks=','.join('?' for _ in services)
    sql=f'''SELECT t.trip_id,t.route_id,r.short_name,r.long_name
      FROM trips t JOIN routes r ON (r.feed_id=t.feed_id AND r.route_id=t.route_id)
      WHERE t.feed_id=? AND t.service_id IN ({marks})'''
    routes={}; by_trip={}
    for t in conn.execute(sql,(feed['id'],*services)):
        k=t['route_id'];
        if k not in routes:routes[k]={'route_id':k,'name':t['short_name'] or k,'long_name':t['long_name'] or '', 'trip_count':0,'stops':{}}
        routes[k]['trip_count']+=1;by_trip[t['trip_id']]=k
    if not by_trip:return {},quality
    sql=f'''SELECT t.route_id, s.stop_id, s.lat, s.lon
        FROM stop_times st JOIN trips t ON st.feed_id=t.feed_id AND st.trip_id=t.trip_id
        JOIN stops s ON s.feed_id=st.feed_id AND s.stop_id=st.stop_id
        WHERE t.feed_id=? AND t.service_id IN ({marks}) AND s.lat IS NOT NULL AND s.lon IS NOT NULL
        GROUP BY t.route_id, s.stop_id'''
    for s in conn.execute(sql,(feed['id'],*services)):
        x,y=PROJECT.transform(s['lon'],s['lat'])
        routes[s['route_id']]['stops'][s['stop_id']]=(x,y)
    return routes,quality

def _similarity(a,b,metres=65):
    x=list(a['stops'].values());y=list(b['stops'].values())
    if not x or not y:return 0.0,0
    edges=[]
    for i,(ax,ay) in enumerate(x):
        for j,(bx,by) in enumerate(y):
            dist=hypot(bx-ax,by-ay)
            if dist<=metres:edges.append((dist,i,j))
    edges.sort()
    used_a=set();used_b=set();n=0
    for _,i,j in edges:
        if i not in used_a and j not in used_b:
            n+=1;used_a.add(i);used_b.add(j)
    return round(n/(len(x)+len(y)-n),4),n

def compare_routes(conn,operator,old_day='2025-10-16',new_day='2026-10-15'):
    if operator not in engine.OPERATORS:raise ValueError('Operador no permitido')
    d0=date.fromisoformat(engine.clean_date(old_day));d1=date.fromisoformat(engine.clean_date(new_day))
    if not (date(2025,1,1)<=d0<d1<=engine.CUTOFF):raise ValueError('Comparación fuera del histórico')
    if engine.day_category(d0)!=engine.day_category(d1):
        raise ValueError('Selecciona fechas de la misma categoría de día: lunes–jueves, viernes, sábado o domingo')
    before,q0=_routes(conn,operator,d0.isoformat());after,q1=_routes(conn,operator,d1.isoformat())
    if before is None or after is None:
        return {'comparable':False,'old_day':old_day,'new_day':new_day,'reason':'Falta GTFS para una o ambas fechas','certified':False,'pairs':[]}
    candidates=[]
    for k,a in before.items():
        for n,b in after.items():
            similarity,matched=_similarity(a,b)
            if similarity>=.2:
                candidates.append((similarity,matched,k,n))
    candidates.sort(reverse=True)
    used_old=set();used_new=set();pairs=[]
    for score,matches,old,new in candidates:
        if old in used_old or new in used_new:continue
        a=before[old];b=after[new]
        used_old.add(old);used_new.add(new)
        pairs.append({'old_route':a['name'],'new_route':b['name'],
          'old_id':old,'new_id':new,'shared_physical_stops':matches,
          'stop_jaccard':score,'matching_quality':'alta' if score>=.8 else 'media' if score>=.5 else 'baja',
          'old_trips':a['trip_count'],'new_trips':b['trip_count'],
          'delta_trips':b['trip_count']-a['trip_count'],
          'old_stops':len(a['stops']),'new_stops':len(b['stops']),
          'renumbered':a['name']!=b['name']})
    pairs.sort(key=lambda x:(-x['stop_jaccard'],x['old_route']))
    def summary(r):return {'code':r['name'],'route_id':r['route_id'],'trips':r['trip_count'],'stops':len(r['stops'])}
    return {'comparable':True,'certified':False,'operator':operator,
      'old_day':d0.isoformat(),'new_day':d1.isoformat(),
      'old_source_quality':q0,'new_source_quality':q1,
      'old_routes':len(before),'new_routes':len(after),
      'pairs':pairs,
      'unmatched_old':[summary(a) for k,a in before.items() if k not in used_old],
      'unmatched_new':[summary(a) for k,a in after.items() if k not in used_new],
      'method':'Emparejamiento conservador por paradas físicas a <=65 m; Jaccard; un emparejamiento por ruta y fecha.',
      'warning':'Coincidencia provisional de corredores, no equivalencia oficial ni prueba de supresión. Redes divididas/fusionadas requieren revisión; las expediciones no representan viajeros ni ejecución real.'}
