"""Reproducible structural GTFS integrity audit, independent of manual source certification.

A clean structural audit is necessary but never sufficient for publishing historical claims.
"""
from collections import Counter
import engine

def validate_feed(conn, feed_id):
    info=conn.execute('SELECT * FROM feeds WHERE id=?',(feed_id,)).fetchone()
    if not info:raise ValueError('No existe la versión GTFS')
    def count(sql):return conn.execute(sql,(feed_id,)).fetchone()[0]
    issues=[]
    def issue(kind,code,total,explanation):
        if total:issues.append({'severity':kind,'code':code,'records':total,'description':explanation})
    invalid_coords=count('''SELECT COUNT(*) FROM stops WHERE feed_id=? AND (
        lat IS NULL OR lon IS NULL OR lat NOT BETWEEN -90 AND 90 OR lon NOT BETWEEN -180 AND 180)''')
    issue('error','invalid_coordinates',invalid_coords,'Paradas sin coordenadas válidas')
    out_region=count('''SELECT COUNT(*) FROM stops WHERE feed_id=? AND lat IS NOT NULL AND lon IS NOT NULL
        AND (lat NOT BETWEEN 42.5 AND 44 OR lon NOT BETWEEN -3.5 AND -1.3)''')
    issue('warning','outside_region',out_region,'Paradas alejadas del territorio esperado; pueden ser errores de origen')
    missing_route=count('''SELECT COUNT(*) FROM trips t LEFT JOIN routes r
        ON t.feed_id=r.feed_id AND t.route_id=r.route_id
        WHERE t.feed_id=? AND r.route_id IS NULL''')
    issue('error','trip_without_route',missing_route,'Expediciones asociadas a líneas inexistentes')
    missing_services=count('''SELECT COUNT(*) FROM trips t WHERE t.feed_id=? AND NOT EXISTS
        (SELECT 1 FROM services s WHERE s.feed_id=t.feed_id AND s.service_id=t.service_id)
        AND NOT EXISTS (SELECT 1 FROM exceptions e WHERE e.feed_id=t.feed_id AND e.service_id=t.service_id AND e.exception_type=1)''')
    issue('error','trip_without_service',missing_services,'Expediciones sin calendario ni alta excepcional')
    orphan_stops=count('''SELECT COUNT(*) FROM stop_times st LEFT JOIN stops s ON
        st.feed_id=s.feed_id AND st.stop_id=s.stop_id WHERE st.feed_id=? AND s.stop_id IS NULL''')
    issue('error','stop_event_without_stop',orphan_stops,'Paso por parada no definida')
    orphan_trips=count('''SELECT COUNT(*) FROM stop_times st LEFT JOIN trips t ON
        st.feed_id=t.feed_id AND st.trip_id=t.trip_id WHERE st.feed_id=? AND t.trip_id IS NULL''')
    issue('error','stop_event_without_trip',orphan_trips,'Paso sin expedición')
    missing_timetables=count('''SELECT COUNT(*) FROM trips t WHERE t.feed_id=? AND NOT EXISTS (
        SELECT 1 FROM stop_times st WHERE st.feed_id=t.feed_id AND st.trip_id=t.trip_id)''')
    issue('error','trip_without_stop_times',missing_timetables,'Expediciones sin pasos horarios')
    invalid_times=count('''SELECT COUNT(*) FROM stop_times WHERE feed_id=? AND (dep_min IS NULL AND arr_min IS NULL)''')
    issue('warning','stop_event_without_times',invalid_times,'Pasos sin horas de salida ni llegada; puede ser tiempo interpolado GTFS')
    n_routes=count('SELECT COUNT(*) FROM routes WHERE feed_id=?')
    n_trips=count('SELECT COUNT(*) FROM trips WHERE feed_id=?')
    n_stops=count('SELECT COUNT(*) FROM stops WHERE feed_id=?')
    n_events=count('SELECT COUNT(*) FROM stop_times WHERE feed_id=?')
    issue('error','empty_core_dataset',int(not (n_routes and n_stops and n_trips and n_events)),
          'El GTFS no contiene red, expediciones y horarios completos')
    errors=sum(x['records'] for x in issues if x['severity']=='error')
    return {'feed_id':feed_id,'operator':info['operator'],'snapshot_date':info['snapshot_date'],
       'historical_cutoff':engine.CUTOFF.isoformat(),'structurally_valid':errors==0,
       'historically_certified':False,
       'summary':{'routes':n_routes,'trips':n_trips,'stops':n_stops,'stop_events':n_events},
       'issues':issues,'notice':'Validación estructural automatizada, no cotejo documental ni servicio observado.'}

def validate_all(conn):
    ids=[r['id'] for r in conn.execute('SELECT id FROM feeds ORDER BY snapshot_date DESC')]
    return {'feeds':[validate_feed(conn,i) for i in ids],
         'versions':len(ids),'cutoff':engine.CUTOFF.isoformat()}
