"""Worker-only operations; request handlers do not parse GTFS or build geography."""
import json
from pathlib import Path
import engine,settings,territory,offer,changes,network_compare,audit,data_quality,population_reference

PUBLIC_KINDS={'network_coverage','service_coverage','compare_routes','compare_stops'}
ADMIN_KINDS={'quality','publication_audit','import_gtfs','import_geo','import_population'}
_STORE=None;_STAMP=None

def store():
    global _STORE,_STAMP
    directory=settings.SETTINGS.geography_dir
    stamp=tuple((p.name,p.stat().st_mtime_ns,p.stat().st_size) for p in sorted(directory.glob('*')) if p.suffix in ('.json','.geojson'))
    if _STORE is None or _STAMP!=stamp:
        _STORE=territory.TerritoryStore(directory,cache_entries=settings.SETTINGS.cache_entries,
            artifact_path=settings.SETTINGS.state_db.with_name('access-cache.sqlite3'));_STAMP=stamp
    return _STORE

def network_coverage(conn,params):
    operator=params['operator'];day=engine.clean_date(params['day']);route=params.get('route_id','')
    ops=engine.CORE_OPERATORS if operator=='both' else tuple(engine.OPERATORS) if operator=='all' else (operator,)
    records={op:engine.map_data(conn,op,day,route) for op in ops}
    missing=[op for op,row in records.items() if row['quality']=='missing']
    available={op:row for op,row in records.items() if row['quality']!='missing'}
    if not available:return {'status':'missing_gtfs','population':None,'missing_operators':missing}
    stops=[{**s,'operator':op} for op,row in available.items() for s in row['stops']]
    result={'operator':operator,'day':day,'route_id':route or None,'minutes':params.get('minutes',10),
            'time_state':'historical' if day<=engine.CUTOFF.isoformat() else 'planning',
            'source_quality':{op:row['quality'] for op,row in available.items()},'missing_operators':missing,
            **store().network_coverage(stops,params.get('minutes',10))}
    if missing:result['status']='partial_sources'
    return result

def service_coverage(conn,params):
    operator=params.get('operator','both');day=params['day'];start=params.get('hour_start',420);end=params.get('hour_end',540)
    ops=engine.CORE_OPERATORS if operator=='both' else tuple(engine.OPERATORS) if operator=='all' else (operator,)
    sources=[offer.stop_service_offer(conn,op,day,start,end) for op in ops]
    if any(x['status']=='missing_gtfs' for x in sources):
        return {'status':'missing_gtfs','population_by_frequency':None,'missing_operators':[s['operator'] for s in sources if s['status']=='missing_gtfs']}
    geo=store()
    if not geo.status()['population_access_ready']:return {'status':'incomplete_geography','population_by_frequency':None}
    values={}
    for threshold in (15,30,60):
        stops=[stop for src in sources for stop in src['threshold_stops'].get(threshold,[])]
        selected=geo.stops_near_study_area(stops)
        values[str(threshold)]={**geo.network_coverage(selected),'served_stops_total':len(stops),'served_stops_in_study_area':len(selected)}
    return {'status':'estimated','operator':operator,'day':day,'hour_start':start,'hour_end':end,
            'time_state':sources[0]['time_state'],'population_by_frequency':values,
            'source_versions':{s['operator']:s.get('feed_id') for s in sources},'certified':False}

def _uploaded(params):
    path=Path(params['upload_path']).resolve();root=(settings.SETTINGS.state_db.parent/'uploads').resolve()
    if path.parent!=root or not path.is_file():raise ValueError('Archivo de staging inválido')
    return path

def execute(kind,params):
    if kind=='stop_isochrone':
        result=store().stop(params['lat'],params['lon'],minutes=params['minutes'])
        return {**{k:v for k,v in params.items() if k not in ('lat','lon')},
                'time_state':'historical' if params['day']<=engine.CUTOFF.isoformat() else 'planning',**result}
    if kind in {'import_gtfs','import_geo','import_population'}:
        if settings.SETTINGS.immutable_data:raise PermissionError('Las cargas sólo se permiten en staging')
        path=_uploaded(params)
        try:
            if kind=='import_gtfs':
                conn=engine.connect(settings.SETTINGS.db)
                try:return engine.ingest(conn,path.read_bytes(),params['operator'],params['snapshot_date'],params['filename'])
                finally:conn.close()
            if kind=='import_geo':return store().ingest(params['layer'],path.read_bytes())
            return population_reference.ingest(settings.SETTINGS.db,path.read_bytes(),source_name=params['filename'])
        finally:path.unlink(missing_ok=True)
    conn=engine.connect(settings.SETTINGS.db,readonly=True,initialize=False)
    try:
        if kind=='network_coverage':return network_coverage(conn,params)
        if kind=='service_coverage':return service_coverage(conn,params)
        if kind=='quality':return data_quality.validate_all(conn)
        if kind=='publication_audit':return audit.readiness(conn,store().status())
        if kind=='compare_routes':return network_compare.compare_routes(conn,params['operator'],params['old_day'],params['new_day'])
        if kind=='compare_stops':
            region=None
            if params.get('territorial_scope',True):
                from shapely.ops import unary_union
                if not store().census:raise ValueError('No hay cartografía censal')
                region=unary_union([s['geometry'] for s in store().census])
            return changes.compare_stops(conn,params['operator'],params['old_day'],params['new_day'],65,region)
        raise ValueError('Operación no permitida')
    finally:conn.close()
