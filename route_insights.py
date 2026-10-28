"""Route-level analytical metrics for the selected GTFS snapshot.

The calculations deliberately use only imported GTFS data: no live Transitland
or external transport API is involved. Schedule-window fields use departures
from the first stop of each trip, so the first/last times are not confused with
the final arrival used for running-time estimates.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date

import engine


def _haversine(a, b):
    lat1, lon1 = math.radians(float(a[0])), math.radians(float(a[1]))
    lat2, lon2 = math.radians(float(b[0])), math.radians(float(b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))


def _span_label(minutes):
    if minutes is None:
        return None
    total = max(0, int(round(float(minutes))))
    hours, mins = divmod(total, 60)
    return f'{hours} h {mins:02d} min' if hours else f'{mins} min'


def _route_context(conn, operator, route_id, day, line_name=None):
    version, quality = engine.pick_version(conn, operator, engine.clean_date(day))
    if not version:
        return None, quality, [], None
    if line_name:
        selected = conn.execute(
            '''SELECT r.route_id,r.short_name,r.long_name,
                      COALESCE(e.public_line_id,NULLIF(r.short_name,''),r.route_id) public_line_id
               FROM routes r LEFT JOIN route_equivalences e
                 ON e.feed_id=r.feed_id AND e.route_id=r.route_id
              WHERE r.feed_id=? AND COALESCE(e.public_line_id,NULLIF(r.short_name,''),r.route_id)=?
              ORDER BY r.route_id LIMIT 1''',
            (version['id'], line_name),
        ).fetchone()
    else:
        selected = conn.execute(
            '''SELECT r.route_id,r.short_name,r.long_name,
                      COALESCE(e.public_line_id,NULLIF(r.short_name,''),r.route_id) public_line_id
               FROM routes r LEFT JOIN route_equivalences e
                 ON e.feed_id=r.feed_id AND e.route_id=r.route_id
              WHERE r.feed_id=? AND r.route_id=?''',
            (version['id'], route_id),
        ).fetchone()
    if not selected:
        return version, quality, [], None
    # A public line may use a different GTFS route_id on weekend service.
    name = selected['public_line_id'] or selected['short_name'] or route_id
    grouped = [r['route_id'] for r in conn.execute(
        '''SELECT r.route_id FROM routes r LEFT JOIN route_equivalences e
             ON e.feed_id=r.feed_id AND e.route_id=r.route_id
           WHERE r.feed_id=? AND COALESCE(e.public_line_id,NULLIF(r.short_name,''),r.route_id)=?''',
        (version['id'], name),
    )]
    return version, quality, grouped or [route_id], dict(selected)


def _shape_lengths(conn, feed_id, route_ids, services):
    marks = ','.join('?' for _ in services)
    shapes = [r['shape_id'] for r in conn.execute(
        f'''SELECT DISTINCT shape_id FROM trips
            WHERE feed_id=? AND route_id IN ({','.join('?' for _ in route_ids)})
            AND service_id IN ({marks}) AND COALESCE(shape_id,'')<>'' ''',
        (feed_id, *route_ids, *services),
    )]
    lengths = {}
    for shape_id in shapes:
        pts = conn.execute(
            'SELECT lat,lon FROM shapes WHERE feed_id=? AND shape_id=? ORDER BY seq',
            (feed_id, shape_id),
        ).fetchall()
        coords = [(p['lat'], p['lon']) for p in pts if p['lat'] is not None and p['lon'] is not None]
        lengths[shape_id] = sum(_haversine(a, b) for a, b in zip(coords, coords[1:]))
    return lengths


def _route_metrics_from_context(conn, operator, route_id, day, version, quality, route_ids, selected):
    if not version or not selected:
        return {'status': 'missing', 'route_id': route_id, 'day': day, 'quality': quality}
    services = engine.active_services(conn, version['id'], day)
    if not services:
        return {'status': 'no_service', 'route_id': route_id, 'day': day, 'quality': quality,
                'line_name': selected['short_name'] or route_id, 'grouped_route_ids': route_ids,
                'scheduled_trips': 0, 'service_span_min': None, 'service_span_label': None}
    marks = ','.join('?' for _ in services)
    route_marks = ','.join('?' for _ in route_ids)
    lengths = _shape_lengths(conn, version['id'], route_ids, services)
    if engine.has_trip_summary(conn,version['id']):
        rows=conn.execute(f'''SELECT t.trip_id,t.shape_id,s.first_dep,s.last_arr
            FROM trips t JOIN trip_summaries s ON s.feed_id=t.feed_id AND s.trip_id=t.trip_id
            WHERE t.feed_id=? AND t.route_id IN ({route_marks}) AND t.service_id IN ({marks})''',
            (version['id'],*route_ids,*services)).fetchall()
    else:
        rows = conn.execute(
        f'''SELECT t.trip_id,t.shape_id,
              (SELECT st.dep_min FROM stop_times st WHERE st.feed_id=t.feed_id AND st.trip_id=t.trip_id ORDER BY st.seq LIMIT 1) AS first_dep,
              (SELECT COALESCE(st.arr_min,st.dep_min) FROM stop_times st WHERE st.feed_id=t.feed_id AND st.trip_id=t.trip_id ORDER BY st.seq DESC LIMIT 1) AS last_arr
            FROM trips t WHERE t.feed_id=? AND t.route_id IN ({route_marks}) AND t.service_id IN ({marks})''',
        (version['id'], *route_ids, *services),
    ).fetchall()
    durations, speeds = [], []
    for row in rows:
        if row['first_dep'] is None or row['last_arr'] is None:
            continue
        duration = float(row['last_arr']) - float(row['first_dep'])
        length = lengths.get(row['shape_id'])
        if duration <= 0 or not length or length <= 0:
            continue
        durations.append(duration)
        speeds.append(length / duration * 60)
    distance = statistics.median(lengths.values()) if lengths else None
    departures = [float(r['first_dep']) for r in rows if r['first_dep'] is not None]
    arrivals = [float(r['last_arr']) for r in rows if r['last_arr'] is not None]
    first_dep = min(departures) if departures else None
    last_dep = max(departures) if departures else None
    span = round(last_dep - first_dep, 1) if first_dep is not None and last_dep is not None else None
    return {
        'status': 'calculated' if speeds or distance else 'insufficient_geometry',
        'operator': operator, 'route_id': route_id, 'day': day, 'quality': quality,
        'line_name': selected['short_name'] or route_id, 'long_name': selected['long_name'] or '',
        'grouped_route_ids': route_ids, 'distance_km': round(distance, 2) if distance else None,
        'commercial_speed_kmh': round(statistics.median(speeds), 1) if speeds else None,
        'runtime_min': round(statistics.median(durations), 1) if durations else None,
        'first_departure': engine.fmt_minutes(first_dep) if first_dep is not None else None,
        'last_departure': engine.fmt_minutes(last_dep) if last_dep is not None else None,
        'last_arrival': engine.fmt_minutes(max(arrivals)) if arrivals else None,
        'first_departure_min': first_dep, 'last_departure_min': last_dep,
        'service_span_min': span, 'service_span_label': _span_label(span),
        'scheduled_trips': len(departures), 'sample_trips': len(rows),
        'method': 'shape GTFS, ventana primera–última salida y mediana de tiempos cabecera–última parada',
    }


def route_metrics(conn, operator, route_id, day):
    day = engine.clean_date(day)
    version, quality, route_ids, selected = _route_context(conn, operator, route_id, day)
    return _route_metrics_from_context(conn, operator, route_id, day, version, quality, route_ids, selected)


def route_frequency_week(conn, operator, route_id, year, month, day):
    """Average scheduled expeditions by weekly day class, grouping route IDs."""
    day = engine.clean_date(day)
    _, quality, fallback_ids, selected = _route_context(conn, operator, route_id, day)
    if not selected:
        return {'status': 'missing', 'route_id': route_id, 'points': []}
    public_line_id = selected['public_line_id'] or selected['short_name'] or route_id
    line_name = selected['short_name'] or public_line_id
    observations = defaultdict(list)
    departure_cache={}
    ids_seen = set()
    for d in sorted(date(year, month, n) for n in range(1, __import__('calendar').monthrange(year, month)[1] + 1)):
        version, _, ids, _ = _route_context(conn, operator, route_id, d.isoformat(), line_name=public_line_id)
        if not version:
            continue
        services = engine.active_services(conn, version['id'], d.isoformat())
        if not services:
            # A valid source that explicitly schedules no service is a measured
            # zero, not a missing observation. This distinction is essential
            # when comparing weekend or holiday frequency.
            observations[engine.day_category(d)].append({'trips': 0, 'first': None, 'last': None})
            continue
        ids = ids or fallback_ids
        ids_seen.update(ids)
        marks, rmarks = ','.join('?' for _ in services), ','.join('?' for _ in ids)
        cache_key=(version['id'],tuple(sorted(ids)),tuple(sorted(services)))
        if cache_key not in departure_cache:
            if engine.has_trip_summary(conn,version['id']):
                rows=conn.execute(f'''SELECT s.first_dep FROM trips t JOIN trip_summaries s
                    ON s.feed_id=t.feed_id AND s.trip_id=t.trip_id
                    WHERE t.feed_id=? AND t.route_id IN ({rmarks}) AND t.service_id IN ({marks})''',
                    (version['id'],*ids,*services)).fetchall()
            else:
                rows = conn.execute(
                    f'''SELECT (SELECT st.dep_min FROM stop_times st
                                WHERE st.feed_id=t.feed_id AND st.trip_id=t.trip_id
                                ORDER BY st.seq LIMIT 1) AS first_dep
                        FROM trips t WHERE t.feed_id=? AND t.route_id IN ({rmarks}) AND t.service_id IN ({marks})''',
                    (version['id'], *ids, *services),
                ).fetchall()
            departure_cache[cache_key]=[float(r['first_dep']) for r in rows if r['first_dep'] is not None]
        departures=departure_cache[cache_key]
        observations[engine.day_category(d)].append({
            'trips': len(departures),
            'first': min(departures) if departures else None,
            'last': max(departures) if departures else None,
        })
    labels = [('LJ', 'Lunes–jueves'), ('V', 'Viernes'), ('S', 'Sábado'), ('D', 'Domingo')]
    points = []
    for key, label in labels:
        items = observations[key]
        firsts = [x['first'] for x in items if x['first'] is not None]
        lasts = [x['last'] for x in items if x['last'] is not None]
        first = statistics.median(firsts) if firsts else None
        last = statistics.median(lasts) if lasts else None
        span = round(last - first, 1) if first is not None and last is not None else None
        points.append({'key': key, 'label': label,
                       'trips_per_day': round(statistics.mean([x['trips'] for x in items]), 1) if items else None,
                       'first_departure': engine.fmt_minutes(first) if first is not None else None,
                       'last_departure': engine.fmt_minutes(last) if last is not None else None,
                       'service_span_min': span, 'service_span_label': _span_label(span),
                       'dates': len(items)})
    return {'status': 'calculated', 'operator': operator, 'route_id': route_id, 'line_name': line_name,
            'public_line_id':public_line_id,
            'grouped_route_ids': sorted(ids_seen or set(fallback_ids)), 'quality': quality, 'points': points,
            'method': 'media de expediciones y mediana de la ventana primera–última salida por categoría de día en el mes seleccionado'}


def _compare_labels(old, new):
    """Classify schedule-window and frequency changes without hiding trade-offs."""
    eps = 0.5
    frequency_delta = new.get('scheduled_trips', 0) - old.get('scheduled_trips', 0)
    span_delta = (new.get('service_span_min') or 0) - (old.get('service_span_min') or 0)
    if span_delta > eps:
        schedule_state = 'Más horario'
    elif span_delta < -eps:
        schedule_state = 'Menos horario'
    else:
        schedule_state = 'Mismo horario'
    if frequency_delta > eps:
        frequency_state = 'Más frecuencias'
    elif frequency_delta < -eps:
        frequency_state = 'Menos frecuencias'
    else:
        frequency_state = 'Mismas frecuencias'
    if schedule_state == 'Mismo horario' and frequency_state == 'Mismas frecuencias':
        label = 'Sin cambio material'
    elif schedule_state == 'Mismo horario':
        label = f'{frequency_state}, mismo horario'
    elif frequency_state == 'Mismas frecuencias':
        label = f'{schedule_state}, mismas frecuencias'
    elif schedule_state == 'Más horario' and frequency_state == 'Menos frecuencias':
        label = 'Más horario, menos frecuencias'
    elif schedule_state == 'Menos horario' and frequency_state == 'Más frecuencias':
        label = 'Más frecuencias, menos horario'
    elif schedule_state == 'Más horario' and frequency_state == 'Más frecuencias':
        label = 'Más frecuencias y más horario'
    elif schedule_state == 'Menos horario' and frequency_state == 'Menos frecuencias':
        label = 'Menos frecuencias y menos horario'
    else:
        label = f'{frequency_state}, {schedule_state.lower()}'
    return {'label': label, 'schedule_state': schedule_state, 'frequency_state': frequency_state,
            'scheduled_trips_delta': frequency_delta, 'service_span_delta_min': round(span_delta, 1),
            'first_departure_delta_min': round((new.get('first_departure_min') or 0) - (old.get('first_departure_min') or 0), 1),
            'last_departure_delta_min': round((new.get('last_departure_min') or 0) - (old.get('last_departure_min') or 0), 1)}


def route_comparison(conn, operator, route_id, old_day, new_day):
    """Compare two dates for a public line, tolerating route_id changes."""
    old_day, new_day = engine.clean_date(old_day), engine.clean_date(new_day)
    new_context = _route_context(conn, operator, route_id, new_day)
    old_context = _route_context(conn, operator, route_id, old_day)
    identity=(new_context[3] or old_context[3] or {})
    line_name=(identity.get('public_line_id') or identity.get('short_name')) if identity else None
    if line_name:
        if not new_context[3]:
            new_context = _route_context(conn, operator, route_id, new_day, line_name=line_name)
        if not old_context[3]:
            old_context = _route_context(conn, operator, route_id, old_day, line_name=line_name)
    old = _route_metrics_from_context(conn, operator, route_id, old_day, *old_context)
    new = _route_metrics_from_context(conn, operator, route_id, new_day, *new_context)
    if old.get('status') != 'calculated' or new.get('status') != 'calculated':
        return {'status': 'incomplete', 'operator': operator, 'route_id': route_id, 'line_name': line_name or route_id,
                'old_day': old_day, 'new_day': new_day, 'old': old, 'new': new,
                'reason': 'Se necesitan expediciones con hora válida en ambas fechas.'}
    return {'status': 'calculated', 'operator': operator, 'route_id': route_id,
            'line_name': line_name or new.get('line_name') or old.get('line_name') or route_id,
            'old_day': old_day, 'new_day': new_day, 'old': old, 'new': new,
            'comparison': _compare_labels(old, new),
            'method': 'comparación de salidas programadas en la primera parada y ventana de servicio GTFS'}
