"""Effective scheduled stop headways and population exposure by service thresholds.

Conservative thresholds use maximum gaps INCLUDING the edges of the queried
window; two clustered departures cannot masquerade as frequent service.
Services stay separated by route, direction and headsign.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from statistics import median
import engine


def stop_service_offer(conn,operator,day,hour_start=7*60,hour_end=9*60):
    if operator not in engine.OPERATORS:raise ValueError('Operador desconocido')
    day=engine.clean_date(day)
    if not 0<=hour_start<hour_end<=2880:raise ValueError('Intervalo horario incorrecto')
    v,source_quality=engine.pick_version(conn,operator,day)
    if v is None:
        return {'status':'missing_gtfs','operator':operator,'day':day,'stops':[], 'source_quality':'missing'}
    active=engine.active_services(conn,v['id'],day)
    if not active:
        return {'status':'source_available','operator':operator,'day':day,'stops':[],
               'source_quality':source_quality,'feed_id':v['id'],'source_sha256':v['sha256']}
    marks=','.join('?' for _ in active)
    sql=f'''SELECT st.stop_id,st.dep_min,t.route_id,t.direction_id,t.headsign,
        s.lat,s.lon,s.name AS stop_name
        FROM stop_times st JOIN trips t ON t.feed_id=st.feed_id AND t.trip_id=st.trip_id
        JOIN stops s ON s.feed_id=st.feed_id AND s.stop_id=st.stop_id
        WHERE st.feed_id=? AND t.service_id IN ({marks})
          AND st.dep_min>=? AND st.dep_min<? AND st.dep_min IS NOT NULL
        ORDER BY st.stop_id,st.dep_min'''
    groups=defaultdict(list);loc={}
    for r in conn.execute(sql,(v['id'],*active,hour_start,hour_end)):
        if r['lat'] is None or r['lon'] is None:continue
        ident=r['stop_id'];loc[ident]={'id':ident,'name':r['stop_name'],'lat':r['lat'],'lon':r['lon']}
        groups[(ident,r['route_id'],r['direction_id'] or '',r['headsign'] or '')].append(r['dep_min'])
    qualifies=defaultdict(set);pattern_count=0
    for (sid,route,direction,headsign),departures in groups.items():
        ordered=sorted(set(departures))
        if len(ordered)<2:continue
        gaps=[ordered[0]-hour_start] + [b-a for a,b in zip(ordered,ordered[1:])] + [hour_end-ordered[-1]]
        longest=max(gaps)
        pattern_count+=1
        for threshold in (15,30,60):
            if longest<=threshold:qualifies[threshold].add(sid)
    return {'status':'source_available','operator':operator,'day':day,
        'time_state':'historical' if day<=engine.CUTOFF.isoformat() else 'planning',
        'source_quality':source_quality,'feed_id':v['id'],'source_sha256':v['sha256'],
        'interval_definition':'Maximum gap between departures INCLUDING beginning and end of window, >=2 distinct departures, per line+direction+headsign',
        'hour_start':hour_start,'hour_end':hour_end,
        'all_stops':list(loc.values()),'pattern_count':pattern_count,
        'threshold_stops':{t:[loc[sid] for sid in ids] for t,ids in qualifies.items()}}
